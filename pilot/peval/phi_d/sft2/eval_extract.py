#!/usr/bin/env python
"""eval_extract.py — extraction eval for SFT2: LoRA-SFT extractor on test500 + canon80.

Canonical dde9f415 extraction protocol (extract_phi_run5200 constants, imported
read-only): prompt + PREFILL, temp 0 seed 42, max_tokens 768, ONE JSON-repair
retry, validate_ir. vLLM with enable_lora. Prompt-only decoding (no guided FSM) —
same as SFT1: the canonical extraction does not use guided decoding, and building a
guided FSM with adapter weights would break parity with the audited base lineage
(disclosed; no numbers depend on FSM).

Jobs (one process, one GPU):
  1. sft x test500  (minted SFT2 held-out test families, LoRA adapter)
  2. sft x canon80  (first 80 keys of extractions_v2.jsonl, file order; canonical
     regression subset — base condition NOT re-run: base rows are the frozen
     out/extractions_v2.jsonl, sanity-checked in audit_sft2.py)

base x test500 is intentionally absent (the vs-base apples-to-apples reference on
the minted side is the adjudicated SFT1 test90 columns, disclosed as cross-dataset;
one eval job total per the stage plan).

Run:
  CUDA_VISIBLE_DEVICES=4 HF_HOME=... HF_HUB_OFFLINE=1 PY eval_extract.py [--limit N] [--only TAG]
"""
import argparse
import json
import os
import pathlib
import sys
import time

os.environ.setdefault("HF_HOME", "/work1/zixuan/cache/huggingface")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("VLLM_LOGGING_LEVEL", "WARNING")

HERE = pathlib.Path(__file__).resolve().parent
PHI_D = HERE.parent
sys.path.insert(0, str(PHI_D))

import common as C                                                  # noqa: E402
from extract_phi_run5200 import (EXTRACTION_PROMPT_V0, REPAIR_PROMPT_V0,  # noqa: E402
                                 SYSTEM_V0, PREFILL, DECODE)

ADAPTER = "/work1/zixuan/checkpoints/agent_memory/phi_sft/sft2"
CANON80 = 80
EVALDIR = HERE / "eval"


def run_one_round(llm, tok, sp, jobs, lora_req):
    prompts = []
    for j in jobs:
        user = j.get("prompt") or EXTRACTION_PROMPT_V0.replace("{TEXT}", j["text"])
        prompts.append(tok.apply_chat_template(
            [{"role": "system", "content": SYSTEM_V0},
             {"role": "user", "content": user}], tokenize=False, add_generation_prompt=True) + PREFILL)
    outs = llm.generate(prompts, sp, lora_request=lora_req)
    rows = []
    for j, o in zip(jobs, outs):
        raw = PREFILL + o.outputs[0].text
        finish = o.outputs[0].finish_reason
        obj, err_cls, err_det = C.extract_json_object(raw)
        if obj is not None:
            ok, vcls, vdet = C.validate_ir(obj)
            if not ok:
                err_cls, err_det = "schema_validation_error", vdet
                obj = None
        rows.append({**{k: j[k] for k in ("key", "kind", "text") if k in j},
                     "raw": raw, "finish_reason": finish, "ir": obj,
                     "error_class": err_cls, "error_detail": err_det})
    return rows


def run_condition(llm, tok, sp, jobs, lora_req, tag):
    t0 = time.time()
    rows = run_one_round(llm, tok, sp, jobs, lora_req)
    retry_jobs = []
    for j, r in zip(jobs, rows):
        if r["error_class"] is not None:
            retry_jobs.append({**j, "prompt": REPAIR_PROMPT_V0.replace(
                "{ERROR}", f"{r['error_class']} {r['error_detail'] or ''}".strip()[:300]).replace("{TEXT}", j["text"])})
    retry_by_key = {}
    if retry_jobs:
        for r in run_one_round(llm, tok, sp, retry_jobs, lora_req):
            retry_by_key[r["key"]] = r
    for i, r in enumerate(rows):
        if r["error_class"] is not None and r["key"] in retry_by_key:
            q = retry_by_key[r["key"]]
            q["attempts"] = 2
            q["first_pass_error"] = r["error_class"]
            rows[i] = q
        else:
            r["attempts"] = 1
    for r in rows:
        r["valid"] = r["ir"] is not None
    first_pass = sum(1 for r in rows if r["attempts"] == 1 and r["valid"])
    print("[eval:%s] n=%d valid=%d (first-pass %d) repairs=%d %.0fs"
          % (tag, len(rows), sum(r["valid"] for r in rows), first_pass,
             sum(1 for r in rows if r["attempts"] == 2), time.time() - t0), flush=True)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only", default="")          # e.g. "sft_test500"
    args = ap.parse_args()
    EVALDIR.mkdir(exist_ok=True)

    test_rows = [json.loads(l) for l in open(HERE / "data" / "test.jsonl")]
    v2 = [json.loads(l) for l in open(PHI_D / "out" / "extractions_v2.jsonl")]
    canon = v2[:CANON80]
    jobs_t500 = [{"key": "t500:%s" % r["pair_id"], "kind": r["kind"], "text": r["text"]}
                 for r in test_rows]
    jobs_c80 = [{"key": r["key"], "kind": r["kind"], "text": r["text"]} for r in canon]
    if args.limit:
        jobs_t500, jobs_c80 = jobs_t500[:args.limit], jobs_c80[:args.limit]

    from vllm import LLM, SamplingParams
    from vllm.lora.request import LoRARequest
    sp = SamplingParams(**DECODE)
    llm = LLM(model=C.MODEL_ID, revision=C.MODEL_REV, dtype="float16",
              gpu_memory_utilization=0.85, max_model_len=4096, seed=42,
              enable_lora=True, max_loras=1, max_lora_rank=16)
    tok = llm.get_tokenizer()
    lora_req = LoRARequest("sft2", 1, ADAPTER)

    plan = [("sft_test500", jobs_t500, lora_req),
            ("sft_canon80", jobs_c80, lora_req)]
    for tag, jobs, req in plan:
        if args.only and args.only != tag:
            continue
        out = EVALDIR / ("%s.jsonl" % tag)
        rows = run_condition(llm, tok, sp, jobs, req, tag)
        with open(out, "w") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print("[eval] wrote %s" % out, flush=True)


if __name__ == "__main__":
    main()
