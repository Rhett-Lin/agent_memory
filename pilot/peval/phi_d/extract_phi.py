"""S1: phi-extraction of the program sketch (IR phi_ir/v0) for every unique text.

One extraction per unique text (instruction or memory_text), cached by sha key,
resume-safe jsonl append. Labels are never read here. Deterministic: temp 0,
fixed seed, one JSON-repair retry; failures recorded as abstain-eligible, never dropped.

Run:
  CUDA_VISIBLE_DEVICES=4 HF_HOME=/work1/zixuan/cache/huggingface HF_HUB_OFFLINE=1 \
    /work1/zixuan/envs/conda_envs/causalmemagent/bin/python extract_phi.py [--limit N]
"""
import argparse
import json
import os
import pathlib
import time

os.environ.setdefault("HF_HOME", "/work1/zixuan/cache/huggingface")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("VLLM_LOGGING_LEVEL", "WARNING")
os.environ.setdefault("OUTLINES_CACHE_DIR", "/work1/zixuan/cache/outlines")

import common as C  # noqa: E402

# ------------------------------------------------------------------ prompt v0
SYSTEM_V0 = "You are a precise program-extraction engine. You output only valid JSON."

EXTRACTION_PROMPT_V0 = """Extract the program sketch of the TEXT below as ONE compact JSON object and nothing else.

Required top-level keys, exactly these, in this order: "schema", "roles", "nodes", "termination".

Template to fill:
{"schema":"phi_ir/v0","roles":{"subject_row":R,"policy_row":R,"source":R,"destination":R,"child_set":R,"audit_sink":R},"nodes":[NODES],"termination":T}

Definitions:
- R = {"status":"present|absent|unknown","surface":<verbatim entity name from the text, else null>,"evidence":<verbatim quote, <=15 words, copied from the text, else null>}.
  Roles: subject_row = the single row the task acts on; policy_row = a row holding policy/threshold data; source / destination = origin / target of a transfer; child_set = the set of related rows that is listed or aggregated; audit_sink = archive/log/notification receiver.
- NODES = the procedure steps in execution order, at most 12, each:
  {"id":"n1","op":"read|list|aggregate|branch|write|verify|finish","status":"present|absent|unknown","evidence":<quote or null>,"args":{...},"depends_on":["nX"],"commutes_with":["nY"]}
  op meanings: read = look up one row; list = enumerate a set of rows; aggregate = compute count/sum/min/max/avg/exists over a set; branch = a conditional policy check; write = any state change; verify = read-back/confirm; finish = terminate/report.
  args by op:
    read/list/verify: {"target":"subject_row"}  (canonical role or short entity string)
    aggregate: {"over":"child_set","function":"count|sum|min|max|avg|exists|other"}
    write: {"action":"set|insert|delete|move|notify|archive|report|other","target":"customers.status","value":"'escalated'"}
    branch: {"predicate":{"attribute":F,"op":F,"value":F,"polarity":F},"then_effects":[E],"else_effects":[E]}
      F = {"status":"present|absent|unknown","value":"...","evidence":"..."}; predicate op value in >,>=,<,<=,==,!=;
      polarity value "positive", or "negative" ONLY when the condition is phrased as a negation ("nobody has declined");
      E = {"action":"...","target":"...","value":"..."} shaped like a write.
    finish: {}
  depends_on = ids that must run before; commutes_with = ids whose relative order is free ("either order", or different rows/fields touched).
- T = {"status":"present|absent|unknown","evidence":<quote or null>} describing what "done" means.

Status rules (critical):
- "present" = the text explicitly states it (verbatim evidence quote REQUIRED).
- "absent" = the procedure is complete AND genuinely omits this element.
- "unknown" = ambiguous or unclear. When unsure choose "unknown"; never invent content to reach "present".

Do NOT copy the TEXT into the JSON. Do NOT invent keys. Compact JSON without indentation.

FORMAT EXAMPLE (invented entities; follow its shape, not its content):
Example TEXT: "Workshop note: item GH-221 (brass hinge) is in the parts table, shelf 'north'. Rule: when the on-hand count of GH-221 is at least 15, mark reorder as 'no'; when it is below 15, mark reorder as 'yes' and quantity_due to 20. Check the shelf count first, then update, then read the row back."
Example output:
{"schema":"phi_ir/v0","roles":{"subject_row":{"status":"present","surface":"parts row GH-221","evidence":"item GH-221 (brass hinge) is in the parts table"},"policy_row":{"status":"absent","surface":null,"evidence":null},"source":{"status":"absent","surface":null,"evidence":null},"destination":{"status":"absent","surface":null,"evidence":null},"child_set":{"status":"absent","surface":null,"evidence":null},"audit_sink":{"status":"absent","surface":null,"evidence":null}},"nodes":[{"id":"n1","op":"read","status":"present","evidence":"Check the shelf count first","args":{"target":"subject_row"},"depends_on":[],"commutes_with":[]},{"id":"n2","op":"branch","status":"present","evidence":"when the on-hand count of GH-221 is at least 15","args":{"predicate":{"attribute":{"status":"present","value":"on-hand count","evidence":"on-hand count of GH-221"},"op":{"status":"present","value":">=","evidence":"at least 15"},"value":{"status":"present","value":"15","evidence":"15"},"polarity":{"status":"present","value":"positive","evidence":"at least 15"}},"then_effects":[{"action":"set","target":"reorder","value":"no"}],"else_effects":[{"action":"set","target":"reorder","value":"yes"},{"action":"set","target":"quantity_due","value":"20"}]},"depends_on":["n1"],"commutes_with":[]},{"id":"n3","op":"write","status":"present","evidence":"then update","args":{"action":"set","target":"subject_row","value":"reorder and quantity_due per branch"},"depends_on":["n2"],"commutes_with":[]},{"id":"n4","op":"verify","status":"present","evidence":"read the row back","args":{"target":"subject_row"},"depends_on":["n3"],"commutes_with":[]}],"termination":{"status":"present","evidence":"read the row back"}}

Now do the same for the real TEXT below. Output only the JSON object, nothing else.

TEXT:
<<<{TEXT}>>>"""

REPAIR_PROMPT_V0 = """The JSON you emitted for the TEXT below was invalid.
Problem: {ERROR}
Re-emit ONLY the corrected compact JSON object. Top-level keys exactly: "schema" (value "phi_ir/v0"), "roles", "nodes", "termination", same definitions as before. No prose, no fences.

TEXT:
<<<{TEXT}>>>"""

DECODE = {"temperature": 0.0, "top_p": 1.0, "max_tokens": 768, "seed": 42}
BATCH = 64


def build_worklist(pairs):
    """Unique texts, file order preserved. Returns list of (key, kind, text)."""
    seen, out = set(), []
    for kind in ("instruction", "memory"):
        for r in pairs:
            t = r["instruction"] if kind == "instruction" else r["memory_text"]
            h = C.sha(t)
            if h in seen:
                continue
            seen.add(h)
            out.append((f"{kind}:{h[:16]}", kind, t))
    return out


def run_one_round(llm, tok, sp, jobs):
    """jobs: list of dicts with key/kind/text/prompt(optional override). Returns rows keyed like jobs."""
    prompts = []
    for j in jobs:
        user = j.get("prompt") or EXTRACTION_PROMPT_V0.replace("{TEXT}", j["text"])
        prompts.append(tok.apply_chat_template(
            [{"role": "system", "content": SYSTEM_V0},
             {"role": "user", "content": user}], tokenize=False, add_generation_prompt=True))
    outs = llm.generate(prompts, sp)
    rows = []
    for j, o in zip(jobs, outs):
        raw = o.outputs[0].text
        finish = o.outputs[0].finish_reason
        obj, err_cls, err_det = C.extract_json_object(raw)
        if obj is not None:
            ok, vcls, vdet = C.validate_ir(obj)
            if not ok:
                err_cls, err_det = "schema_validation_error", vdet
                obj = None
        rows.append({**{k: j[k] for k in ("key", "kind", "text")}, "raw": raw,
                     "finish_reason": finish, "ir": obj, "error_class": err_cls,
                     "error_detail": err_det})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default=str(C.OUT / "extractions.jsonl"))
    args = ap.parse_args()

    out_path = pathlib.Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pairs = C.load_pairs()
    work = build_worklist(pairs)
    done = C.done_keys(out_path)
    todo = [w for w in work if w[0] not in done]
    if args.limit:
        todo = todo[:args.limit]
    print(f"[extract] unique texts={len(work)} done={len(done)} todo={len(todo)}", flush=True)
    if not todo:
        return

    from vllm import LLM, SamplingParams
    from vllm.sampling_params import GuidedDecodingParams
    sp = SamplingParams(**DECODE, guided_decoding=GuidedDecodingParams(
        json=C.IR_GUIDE_SCHEMA, whitespace_pattern=""))
    llm = LLM(model=C.MODEL_ID, revision=C.MODEL_REV, dtype="float16",
              gpu_memory_utilization=0.85, max_model_len=4096, seed=42,
              guided_decoding_backend="outlines")
    tok = llm.get_tokenizer()
    prompt_sha = C.sha(SYSTEM_V0 + "\n" + EXTRACTION_PROMPT_V0 + "\n" + REPAIR_PROMPT_V0)
    meta = {"prompt_sha": prompt_sha, "model": C.MODEL_ID, "revision": C.MODEL_REV,
            "decode": DECODE, "guided": "json:IR_GUIDE_SCHEMA_v2_compact(outlines)"}

    fh = open(out_path, "a")
    t0 = time.time()
    n_done_total = 0
    for b0 in range(0, len(todo), BATCH):
        chunk = todo[b0:b0 + BATCH]
        jobs = [{"key": k, "kind": kd, "text": t} for k, kd, t in chunk]
        rows = run_one_round(llm, tok, sp, jobs)
        # one JSON-repair retry for failures
        retry_jobs = []
        for j, r in zip(jobs, rows):
            if r["error_class"] is not None:
                retry_jobs.append({**j, "prompt": REPAIR_PROMPT_V0.replace(
                    "{ERROR}", f"{r['error_class']} {r['error_detail'] or ''}".strip()[:300]).replace("{TEXT}", j["text"])})
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
        print(f"[extract] {n_done_total}/{len(todo)} invalid={n_bad} "
              f"elapsed={time.time()-t0:.0f}s", flush=True)
    fh.close()


if __name__ == "__main__":
    main()
