"""Guided rescue pass for the 151 invalid rows of out/extractions.jsonl.

Lineage discipline (v2-compact, prompt_sha dde9f415):
- Prompt strings imported unchanged from extract_phi.py (SYSTEM_V0 /
  EXTRACTION_PROMPT_V0 / REPAIR_PROMPT_V0); the script ASSERTS the recomputed
  prompt_sha equals the canonical corpus value before touching the GPU.
- Guide schema = common.IR_GUIDE_SCHEMA with maxLength bounds stripped. The live
  common.py is the v3c variant (v2 + maxLength 64/6); the git-committed v2 differs
  from it ONLY in those four maxLength spots, so stripping reproduces
  IR_GUIDE_SCHEMA_v2_compact exactly (self-checked at runtime). v3c is FORBIDDEN:
  it hung the outlines FSM builder for hours (out/run_extract_rescue.log).
- Sole decode change vs canonical: max_tokens 768 -> 2048. temperature 0, top_p 1,
  seed 42 unchanged. One repair retry, same rules and class-mapped error feedback
  as extract_phi.py (length / json_parse / schema); repair template unchanged, so
  prompt_sha lineage is preserved.
- Output goes to out/guided/rescue1.jsonl (new file; out/extractions.jsonl is never
  touched). Resume-safe: any key already present in the output file is skipped,
  valid or not (a recorded failure is final for this run configuration).
- Labels (cell/P/S/...) are never read here; keys come from the extraction rows.

Run:
  CUDA_VISIBLE_DEVICES=4 HF_HOME=/work1/zixuan/cache/huggingface HF_HUB_OFFLINE=1 \
    /work1/zixuan/envs/conda_envs/causalmemagent/bin/python rescue_guided.py \
    [--keys out/guided/smoke1_keys.json] [--limit N]
"""
import argparse
import copy
import hashlib
import json
import os
import pathlib
import time

os.environ.setdefault("HF_HOME", "/work1/zixuan/cache/huggingface")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("VLLM_LOGGING_LEVEL", "WARNING")
os.environ.setdefault("OUTLINES_CACHE_DIR", "/work1/zixuan/cache/outlines")

import common as C  # noqa: E402
from extract_phi import (SYSTEM_V0, EXTRACTION_PROMPT_V0, REPAIR_PROMPT_V0,  # noqa: E402
                         build_worklist, run_one_round)

CANONICAL_PROMPT_SHA = "dde9f4154a6c6a5e02ce583c3cd8a2edb16ae05625acd6b2775ec30656a7a23b"
DECODE_V2R = {"temperature": 0.0, "top_p": 1.0, "max_tokens": 2048, "seed": 42}
BATCH = 64
GUIDED_TAG = "json:IR_GUIDE_SCHEMA_v2_compact(outlines)"


def strip_maxlength(node):
    """Recursively drop maxLength keys (v3c -> v2-compact schema revert)."""
    if isinstance(node, dict):
        return {k: strip_maxlength(v) for k, v in node.items() if k != "maxLength"}
    if isinstance(node, list):
        return [strip_maxlength(v) for v in node]
    return node


IR_GUIDE_SCHEMA_V2 = strip_maxlength(copy.deepcopy(C.IR_GUIDE_SCHEMA))


def self_checks():
    prompt_sha = C.sha(SYSTEM_V0 + "\n" + EXTRACTION_PROMPT_V0 + "\n" + REPAIR_PROMPT_V0)
    assert prompt_sha == CANONICAL_PROMPT_SHA, f"prompt lineage broken: {prompt_sha}"
    dumped = json.dumps(IR_GUIDE_SCHEMA_V2)
    assert "maxLength" not in dumped, "schema revert failed: maxLength still present"
    return prompt_sha


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=str(C.OUT / "extractions.jsonl"),
                    help="canonical extraction jsonl; invalid keys are the rescue universe")
    ap.add_argument("--keys", default="", help="optional JSON file with a list of keys to restrict to")
    ap.add_argument("--out", default=str(C.OUT / "guided" / "rescue1.jsonl"))
    ap.add_argument("--run-id", default="rescue1")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    prompt_sha = self_checks()
    out_path = pathlib.Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    src_rows = [json.loads(l) for l in open(args.source)]
    invalid_keys = {r["key"] for r in src_rows if not r.get("valid")}
    if args.keys:
        kdoc = json.load(open(args.keys))
        invalid_keys &= set(kdoc["keys"] if isinstance(kdoc, dict) else kdoc)
    work = build_worklist(C.load_pairs())
    known = {w[0] for w in work}
    missing = invalid_keys - known
    assert not missing, f"keys not in worklist: {sorted(missing)[:5]}"
    done = C.done_keys(out_path)
    todo = [w for w in work if w[0] in invalid_keys and w[0] not in done]
    if args.limit:
        todo = todo[:args.limit]
    print(f"[rescue] invalid universe={len(invalid_keys)} done={len(done & invalid_keys)} "
          f"todo={len(todo)} prompt_sha={prompt_sha[:8]}", flush=True)
    if not todo:
        return

    from vllm import LLM, SamplingParams
    from vllm.sampling_params import GuidedDecodingParams
    sp = SamplingParams(**DECODE_V2R, guided_decoding=GuidedDecodingParams(
        json=IR_GUIDE_SCHEMA_V2, whitespace_pattern=""))
    llm = LLM(model=C.MODEL_ID, revision=C.MODEL_REV, dtype="float16",
              gpu_memory_utilization=0.85, max_model_len=4096, seed=42,
              guided_decoding_backend="outlines")
    tok = llm.get_tokenizer()
    meta = {"prompt_sha": prompt_sha, "model": C.MODEL_ID, "revision": C.MODEL_REV,
            "decode": DECODE_V2R, "guided": GUIDED_TAG, "rescue_run": args.run_id}

    fh = open(out_path, "a")
    t0 = time.time()
    n_done_total = 0
    for b0 in range(0, len(todo), BATCH):
        chunk = todo[b0:b0 + BATCH]
        jobs = [{"key": k, "kind": kd, "text": t} for k, kd, t in chunk]
        rows = run_one_round(llm, tok, sp, jobs)
        # one JSON-repair retry, class-mapped feedback (same rules as extract_phi.py)
        retry_jobs = []
        for j, r in zip(jobs, rows):
            if r["error_class"] is not None:
                if r.get("finish_reason") == "length":
                    emsg = ("output hit the token budget before the JSON closed; re-emit more compact: "
                            "shorter quotes, at most 10 nodes, never enumerate long ID lists")
                elif r["error_class"] == "json_parse_error":
                    emsg = f"output was not valid JSON ({str(r['error_detail'])[:120]})"
                else:
                    emsg = "output JSON did not match the required schema/keys"
                retry_jobs.append({**j, "prompt": REPAIR_PROMPT_V0.replace(
                    "{ERROR}", emsg).replace("{TEXT}", j["text"])})
        retry_by_key = {}
        if retry_jobs:
            for r in run_one_round(llm, tok, sp, retry_jobs):
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
            r.update(meta)
            r["valid"] = r["ir"] is not None
        C.append_rows(out_path, rows, fh)
        n_done_total += len(rows)
        n_bad = sum(1 for r in rows if not r["valid"])
        n_first = sum(1 for r in rows if r.get("attempts", 1) == 1 and r["valid"])
        print(f"[rescue] {n_done_total}/{len(todo)} invalid_after_retry={n_bad} "
              f"batch_first_pass_valid={n_first} elapsed={time.time()-t0:.0f}s", flush=True)
    fh.close()


if __name__ == "__main__":
    main()
