#!/usr/bin/env python
"""extract_canonical_sft.py — S2-prep stage 1: SFT2-adapter extraction of the FULL
canonical corpus (532 unique texts = 160 instructions + 372 memory texts, taken with
keys/kind/text from the frozen out/extractions_v2.jsonl, file order).

Protocol = the adjudicated SFT2 eval surface, bit-for-bit: the extraction runner is
sft2/eval_extract.py's run_condition (imported verbatim), which pins
extract_phi_run5200 constants (SYSTEM_V0 / EXTRACTION_PROMPT_V0 / REPAIR_PROMPT_V0 /
PREFILL), DECODE = temp 0 / top_p 1 / max_tokens 768 / seed 42, <=1 JSON-repair retry,
common.validate_ir, prompt-only decoding (no guided FSM — parity with the audited
base lineage, same disclosure as eval_extract.py). vLLM base Qwen2.5-7B-Instruct
@ a09a3545 + LoRA adapter /work1/zixuan/checkpoints/agent_memory/phi_sft/sft2, GPU 4.

The run5200 constants are exactly what the adjudicated SFT2 gate run used
(sft2/eval/sft_canon80.jsonl); the first 80 keys of this corpus are therefore a
built-in determinism check against that frozen file (checked by
audit_sft_canonical / reported in S2_PREP_REPORT.md). Naming note: the lane calls
this surface the "dde9f415 lineage"; the prompt_sha stamped on rows uses the
run5200 formula (sha of SYSTEM+EXTRACTION+REPAIR+PREFILL = 5200e56e...). Both shas
are recorded in the receipt.

Labels (cell/P/S/family/archetype) are NEVER read here; inputs are (key, kind, text)
from the frozen v2 corpus only.

Run:
  CUDA_VISIBLE_DEVICES=4 HF_HOME=/work1/zixuan/cache/huggingface HF_HUB_OFFLINE=1 \
    /work1/zixuan/envs/conda_envs/causalmemagent/bin/python extract_canonical_sft.py [--limit N]
"""
import argparse
import hashlib
import json
import os
import pathlib
import sys
import time

os.environ.setdefault("HF_HOME", "/work1/zixuan/cache/huggingface")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("VLLM_LOGGING_LEVEL", "WARNING")

HERE = pathlib.Path(__file__).resolve().parent          # pilot/peval/phi_d/sft2_eval
PHI_D = HERE.parent                                     # pilot/peval/phi_d
for p in (str(PHI_D), str(PHI_D / "sft2")):
    if p not in sys.path:
        sys.path.insert(0, p)

import common as C                                                  # noqa: E402
from extract_phi_run5200 import (SYSTEM_V0, EXTRACTION_PROMPT_V0,   # noqa: E402
                                 REPAIR_PROMPT_V0, PREFILL, DECODE)
from eval_extract import run_condition, ADAPTER                     # noqa: E402

V2 = PHI_D / "out" / "extractions_v2.jsonl"
SFT_CANON80 = PHI_D / "sft2" / "eval" / "sft_canon80.jsonl"


def sha_file(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default=str(HERE / "canonical_sft.jsonl"))
    ap.add_argument("--receipt", default=str(HERE / "canonical_sft_receipt.json"))
    args = ap.parse_args()

    v2 = [json.loads(l) for l in open(V2)]
    jobs = [{"key": r["key"], "kind": r["kind"], "text": r["text"]} for r in v2]
    if args.limit:
        jobs = jobs[:args.limit]
    print("[extract] canonical corpus: %d texts (v2 file order)%s"
          % (len(jobs), " [LIMIT %d]" % args.limit if args.limit else ""), flush=True)

    from vllm import LLM, SamplingParams
    from vllm.lora.request import LoRARequest
    sp = SamplingParams(**DECODE)
    t0 = time.time()
    llm = LLM(model=C.MODEL_ID, revision=C.MODEL_REV, dtype="float16",
              gpu_memory_utilization=0.85, max_model_len=4096, seed=42,
              enable_lora=True, max_loras=1, max_lora_rank=16)
    tok = llm.get_tokenizer()
    lora_req = LoRARequest("sft2", 1, ADAPTER)
    load_s = time.time() - t0

    rows = run_condition(llm, tok, sp, jobs, lora_req, "canonical_sft")

    prompt_sha_with_prefill = C.sha(SYSTEM_V0 + "\n" + EXTRACTION_PROMPT_V0 + "\n"
                                    + REPAIR_PROMPT_V0 + "\n" + PREFILL)
    prompt_sha_no_prefill = C.sha(SYSTEM_V0 + "\n" + EXTRACTION_PROMPT_V0 + "\n"
                                  + REPAIR_PROMPT_V0)
    meta = {"prompt_sha": prompt_sha_with_prefill, "model": C.MODEL_ID,
            "revision": C.MODEL_REV, "decode": DECODE, "prefill": PREFILL}
    for r in rows:
        r.update(meta)

    out_path = pathlib.Path(args.out)
    with open(out_path, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    wall = time.time() - t0
    print("[extract] wrote %s (%.0fs incl. %.0fs load)" % (out_path, wall, load_s), flush=True)

    # determinism check vs the adjudicated SFT2 canon80 run (same surface, first 80 keys)
    canon80 = {}
    if SFT_CANON80.exists():
        canon80 = {r["key"]: r for r in map(json.loads, open(SFT_CANON80))}
    first80 = [r for r in rows if r["key"] in canon80][:80]
    n_ir_match = sum(1 for r in first80
                     if json.dumps(r["ir"], sort_keys=True)
                     == json.dumps(canon80[r["key"]]["ir"], sort_keys=True))
    n_match_rows = len(first80)

    n_valid = sum(r["valid"] for r in rows)
    receipt = {
        "task": "S2-prep stage 1: SFT2 extraction of the full canonical 532-text corpus",
        "surface": "sft2/eval_extract.py run_condition + extract_phi_run5200 constants "
                   "(the adjudicated SFT2 gate-run surface; prompt-only decoding)",
        "prompt_sha_run5200_formula_with_prefill": prompt_sha_with_prefill,
        "prompt_sha_canon_formula_no_prefill": prompt_sha_no_prefill,
        "naming_note": "lane documentation calls this surface the 'dde9f415 lineage'; "
                       "the row-level prompt_sha uses the run5200 formula (includes PREFILL "
                       "in the hashed string). Surface constants are byte-identical to what "
                       "sft2/eval/sft_canon80.jsonl was produced with.",
        "model": C.MODEL_ID, "revision": C.MODEL_REV, "adapter": ADAPTER,
        "adapter_sha16": sha_file(os.path.join(ADAPTER, "adapter_model.safetensors"))[:16],
        "decode": DECODE, "prefill": PREFILL,
        "llm_kwargs": {"dtype": "float16", "gpu_memory_utilization": 0.85,
                       "max_model_len": 4096, "seed": 42, "enable_lora": True,
                       "max_loras": 1, "max_lora_rank": 16},
        "gpu": os.environ.get("CUDA_VISIBLE_DEVICES", "(unset)"),
        "n_rows": len(rows), "n_valid": n_valid,
        "n_first_pass_valid": sum(1 for r in rows if r["attempts"] == 1 and r["valid"]),
        "n_repairs": sum(1 for r in rows if r["attempts"] == 2),
        "by_kind": {k: {"n": sum(1 for r in rows if r["kind"] == k),
                        "valid": sum(1 for r in rows if r["kind"] == k and r["valid"])}
                    for k in ("instruction", "memory")},
        "invalid_keys": [r["key"] for r in rows if not r["valid"]],
        "per_row_validity": {r["key"]: r["valid"] for r in rows},
        "determinism_check_vs_sft_canon80": {"n_compared": n_match_rows,
                                             "n_ir_exact": n_ir_match},
        "input_file": str(V2), "input_sha16": sha_file(V2)[:16],
        "output_file": str(out_path), "output_sha16": sha_file(out_path)[:16],
        "code_sha16": {"this_script": sha_file(__file__)[:16],
                       "extract_phi_run5200": sha_file(PHI_D / "extract_phi_run5200.py")[:16],
                       "eval_extract": sha_file(PHI_D / "sft2" / "eval_extract.py")[:16],
                       "common": sha_file(PHI_D / "common.py")[:16]},
        "wall_time_s": round(wall, 1), "load_time_s": round(load_s, 1),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
    }
    with open(args.receipt, "w") as f:
        json.dump(receipt, f, indent=1, ensure_ascii=False)
    print("[extract] valid=%d/%d (first-pass %d, repairs %d); canon80 parity %d/%d; receipt -> %s"
          % (n_valid, len(rows), receipt["n_first_pass_valid"], receipt["n_repairs"],
             n_ir_match, n_match_rows, args.receipt), flush=True)


if __name__ == "__main__":
    main()
