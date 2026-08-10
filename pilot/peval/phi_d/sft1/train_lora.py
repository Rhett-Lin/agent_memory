#!/usr/bin/env python
"""train_lora.py — stage B pilot: LoRA SFT of the phi-extractor (P1 slice).

Model: Qwen/Qwen2.5-7B-Instruct @ a09a3545 (local cache), LoRA r=16 alpha=32
dropout 0.05 on q/k/v/o. lr 1e-4 cosine, eff. batch 16 (bs1 x accum16), <=2
epochs, bf16, seq cap 2048, loss on gold-IR completion tokens ONLY (prompt +
PREFILL masked to -100). Input surface = the canonical extraction prompt
(extract_phi_run5200 constants, imported read-only) with the minted TEXT; the
completion = compact-json gold IR continuation after PREFILL + <|im_end|>.
Labels/cells/families never enter the input; val slice never trained.

Run:
  CUDA_VISIBLE_DEVICES=4 HF_HOME=/work1/zixuan/cache/huggingface HF_HUB_OFFLINE=1 \
    /work1/zixuan/envs/conda_envs/causalmemagent/bin/python train_lora.py
"""
import json
import os
import pathlib
import time

os.environ.setdefault("HF_HOME", "/work1/zixuan/cache/huggingface")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import torch                                                         # noqa: E402
from torch.utils.data import Dataset                                 # noqa: E402
from transformers import (AutoModelForCausalLM, AutoTokenizer, Trainer,  # noqa: E402
                          TrainingArguments, set_seed)
from peft import LoraConfig, get_peft_model                          # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
PHI_D = HERE.parent
import sys                                                          # noqa: E402
sys.path.insert(0, str(PHI_D))
from extract_phi_run5200 import EXTRACTION_PROMPT_V0, SYSTEM_V0, PREFILL  # noqa: E402
import common as C                                                  # noqa: E402

CKPT_DIR = pathlib.Path("/work1/zixuan/checkpoints/agent_memory/phi_sft/lora_p1_sft1")
# measured full-length distribution (prompt+completion): 1803..2092 tokens; 2112 covers 100%.
MAXLEN = 2112
EPOCHS = 2.0
LR = 1e-4
SEED = 42


# canonical key ordering for the completion serialization (the data files store
# gold IRs with sort_keys; the training target must reproduce the canonical
# surface order so that serialization starts with PREFILL and the learned
# format matches the guide schema's key order).
_TOP = ["schema", "roles", "nodes", "termination"]
_ROLE = ["status", "surface", "evidence"]
_NODE = ["id", "op", "status", "evidence", "args", "depends_on", "commutes_with"]
_ARGS = ["target", "over", "function", "action", "value", "predicate",
         "then_effects", "else_effects"]
_PRED = ["attribute", "op", "value", "polarity"]
_F = ["status", "value", "evidence"]
_EFF = ["action", "target", "value"]
_TERM = ["status", "evidence"]


def _order(d, template):
    out = {k: d[k] for k in template if k in d}
    extra = [k for k in d if k not in template]
    assert not extra, "non-canonical keys: %s" % extra
    return out


def canonical_ir_dump(ir):
    obj = {"schema": ir["schema"],
           "roles": {r: _order(ir["roles"][r], _ROLE) for r in C.CANONICAL_ROLES},
           "nodes": [], "termination": _order(ir["termination"], _TERM)}
    for n in ir["nodes"]:
        nn = _order(n, _NODE)
        a = nn.get("args")
        if a is not None:
            aa = _order(a, _ARGS)
            if aa.get("predicate") is not None:
                p = aa["predicate"]
                aa["predicate"] = {k: _order(p[k], _F) for k in _PRED}
            for ek in ("then_effects", "else_effects"):
                if aa.get(ek) is not None:
                    aa[ek] = [_order(e, _EFF) for e in aa[ek]]
            nn["args"] = aa
        obj["nodes"].append(nn)
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


class SFTData(Dataset):
    def __init__(self, rows, tok):
        self.ex = []
        skipped = 0
        for r in rows:
            user = EXTRACTION_PROMPT_V0.replace("{TEXT}", r["text"])
            prompt = tok.apply_chat_template(
                [{"role": "system", "content": SYSTEM_V0},
                 {"role": "user", "content": user}],
                tokenize=False, add_generation_prompt=True) + PREFILL
            full_ir = canonical_ir_dump(r["gold_ir"])
            assert full_ir.startswith(PREFILL), "serialized gold IR does not start with PREFILL"
            target = full_ir[len(PREFILL):] + "<|im_end|>"
            ids_p = tok(prompt, add_special_tokens=False)["input_ids"]
            ids_t = tok(target, add_special_tokens=False)["input_ids"]
            if len(ids_p) + len(ids_t) > MAXLEN:
                skipped += 1
                continue
            self.ex.append((ids_p, ids_t))
        self.skipped = skipped

    def __len__(self):
        return len(self.ex)

    def __getitem__(self, i):
        ids_p, ids_t = self.ex[i]
        input_ids = ids_p + ids_t
        labels = [-100] * len(ids_p) + ids_t
        return {"input_ids": input_ids, "labels": labels,
                "attention_mask": [1] * len(input_ids)}


def collate(batch):
    mx = max(len(b["input_ids"]) for b in batch)
    input_ids, labels, attn = [], [], []
    for b in batch:
        pad = mx - len(b["input_ids"])
        input_ids.append(b["input_ids"] + [0] * pad)
        labels.append(b["labels"] + [-100] * pad)
        attn.append(b["attention_mask"] + [0] * pad)
    return {"input_ids": torch.tensor(input_ids), "labels": torch.tensor(labels),
            "attention_mask": torch.tensor(attn)}


def main():
    t0 = time.time()
    set_seed(SEED)
    tok = AutoTokenizer.from_pretrained(C.MODEL_ID, revision=C.MODEL_REV)
    train_rows = [json.loads(l) for l in open(HERE / "data" / "train.jsonl")]
    val_rows = [json.loads(l) for l in open(HERE / "data" / "val.jsonl")]
    ds_tr, ds_va = SFTData(train_rows, tok), SFTData(val_rows, tok)
    print("[train] usable train=%d (skipped %d >%d tok), val=%d (skipped %d)"
          % (len(ds_tr), ds_tr.skipped, MAXLEN, len(ds_va), ds_va.skipped), flush=True)

    model = AutoModelForCausalLM.from_pretrained(
        C.MODEL_ID, revision=C.MODEL_REV, torch_dtype=torch.bfloat16)
    model.config.use_cache = False
    lcfg = LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05,
                      target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
                      task_type="CAUSAL_LM")
    model = get_peft_model(model, lcfg)
    model.print_trainable_parameters()

    args = TrainingArguments(
        output_dir=str(CKPT_DIR / "_trainer_tmp"),
        per_device_train_batch_size=1, gradient_accumulation_steps=16,
        per_device_eval_batch_size=1,
        num_train_epochs=EPOCHS, learning_rate=LR, lr_scheduler_type="cosine",
        warmup_ratio=0.03, weight_decay=0.0, max_grad_norm=1.0,
        bf16=True, gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        logging_steps=5, eval_strategy="epoch", save_strategy="no",
        seed=SEED, data_seed=SEED, report_to=[], dataloader_num_workers=0,
        remove_unused_columns=False)
    trainer = Trainer(model=model, args=args, train_dataset=ds_tr,
                      eval_dataset=ds_va, data_collator=collate)
    trainer.train()

    CKPT_DIR.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(CKPT_DIR))
    tok.save_pretrained(str(CKPT_DIR))
    hist = [h for h in trainer.state.log_history]
    receipt = {
        "model": C.MODEL_ID, "revision": C.MODEL_REV,
        "peft": {"r": 16, "alpha": 32, "dropout": 0.05, "targets": ["q_proj", "k_proj", "v_proj", "o_proj"]},
        "optim": {"lr": LR, "sched": "cosine", "warmup_ratio": 0.03, "epochs": EPOCHS,
                  "bs": 1, "grad_accum": 16, "eff_batch": 16, "bf16": True,
                  "grad_ckpt": True, "seed": SEED, "maxlen": MAXLEN,
                  "maxlen_note": "task default 2048 dropped 92/300 examples; measured max 2092 -> 2112 covers 100%"},
        "data": {"train_sha": __import__("hashlib").sha256(
            open(HERE / "data" / "train.jsonl", "rb").read()).hexdigest(),
                 "val_sha": __import__("hashlib").sha256(
            open(HERE / "data" / "val.jsonl", "rb").read()).hexdigest(),
                 "n_train": len(ds_tr), "n_val": len(ds_va),
                 "skipped_too_long_train": ds_tr.skipped, "skipped_too_long_val": ds_va.skipped},
        "wall_time_s": round(time.time() - t0, 1),
        "cuda_device": os.environ.get("CUDA_VISIBLE_DEVICES", "unset"),
        "train_loss_last": next((h["loss"] for h in reversed(hist) if "loss" in h), None),
        "eval_losses": [h for h in hist if "eval_loss" in h],
        "log_history": hist,
        "adapter_dir": str(CKPT_DIR),
    }
    with open(HERE / "train_receipt.json", "w") as f:
        json.dump(receipt, f, indent=1)
    losses = [h["loss"] for h in hist if "loss" in h and h.get("epoch")]
    print("[train] done in %.0fs; losses: %s; eval: %s"
          % (time.time() - t0, [round(x, 4) for x in losses],
             [round(h["eval_loss"], 4) for h in receipt["eval_losses"]]))
    if any(x != x for x in losses):     # NaN kill criterion
        raise SystemExit("KILL: NaN train loss observed")


if __name__ == "__main__":
    main()
