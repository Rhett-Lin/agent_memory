"""S1: decomposed-judge baseline (plan section 4) over all 640 pairs.

Same model + same decoding discipline as extraction: temp 0, fixed seed, one
JSON-repair retry, failures recorded (abstain-eligible), never dropped.
Per-pair key = memory_id (unique per row in pairs.jsonl). Labels are never
shown to the model; only instruction + memory_text go into the prompt.

Run:
  CUDA_VISIBLE_DEVICES=4 HF_HOME=/work1/zixuan/cache/huggingface HF_HUB_OFFLINE=1 \
    /work1/zixuan/envs/conda_envs/causalmemagent/bin/python decomposed_judge.py [--limit N]
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
SYSTEM_V0 = "You are a precise semantic-comparison engine. You output only valid JSON."

JUDGE_PROMPT_V0 = """You are given an INSTRUCTION describing a target task and a MEMORY describing a retrieved past procedure. Judge whether the memory's procedure semantically matches the procedure the instruction asks for. Compare meaning, not surface wording: the two texts may use different entity names for the same role.

Compare these atomic aspects, and for each aspect follow its comparison rule:
- goal: what the procedure is trying to achieve, compared at role level (entity names may differ across domains).
- roles: which ROLES the entities fill (the row acted on, the policy/threshold row, the origin/destination of a move, the set being aggregated, the archive/log sink). Different entity names can fill the same role.
- branch_predicates: FIRST map each side's conditional check to (attribute role, comparator direction, outcome per branch). Comparator mapping: "above X"/"more than X"/"exceeds X" = >, "at least X" = >=, "at or below X"/"no more than X" = <=, "below X"/"fewer than X"/"under X" = <, "exactly X" = ==, "none remain"/"no X left" = zero-check. Attribute names and threshold NUMBERS may legitimately differ across domains; a different comparator DIRECTION, or a different outcome attached to the same branch, = contradict.
- transfer_direction: which role is decreased (origin) and which is increased (destination); amounts may differ; swapped origin/destination = contradict.
- aggregation_scope: exactly WHICH set of rows is listed/counted/aggregated, compared via the filter criteria (prefix, status, topic, relation); a different filter or subset = contradict.
- required_operations: whether the memory contains EVERY operation the instruction requires (lookups, policy checks, updates, archive/delete/notify steps, read-back verification). An operation required by the instruction but missing from the memory is a contradiction, not a minor difference.
- write_effects: whether the two texts' writes produce the same end state per condition (same fields, same outcome values), compared at role level.

Then output EXACTLY one JSON object (compact, no prose, no markdown fences):
{"schema":"phi_judge/v0",
 "fields":{"goal":V,"roles":V,"branch_predicates":V,"transfer_direction":V,"aggregation_scope":V,"required_operations":V,"write_effects":V},
 "verdict":"match|contradict|unknown"}
where V = {"instruction_says":"<=15 words","memory_says":"<=15 words","verdict":"match|contradict|unknown|not_applicable","note":"<=20 words"}.
For EVERY aspect: first write what each side says (short quote or tight summary; null if that side lacks the aspect), then judge. Never judge from overall impression.
- "match": the two texts agree on this aspect UNDER its comparison rule (role-level entity match counts as agreement). "contradict": they explicitly conflict under the rule (comparator direction flipped, swapped origin/destination, different aggregation filter, a required operation missing in the memory, different end state).
- "unknown": the texts are too vague or incomplete to tell. "not_applicable": this aspect appears in neither text.
- final "verdict": "contradict" if ANY applicable field contradicts; "match" only if every applicable field matches; otherwise "unknown".

Do NOT invent keys. Compact JSON without indentation.

FORMAT EXAMPLE (invented entities; follow its shape, not its content):
Example INSTRUCTION: "Workshop note: item GH-221 (brass hinge) is in the parts table, shelf 'north'. Rule: when the on-hand count of GH-221 is at least 15, mark reorder as 'no'; when it is below 15, mark reorder as 'yes' and quantity_due to 20. Check the shelf count first, then update, then read the row back."
Example MEMORY: "Retrieved experience: for parts row GH-221, rule: when the on-hand count is at least 15, mark reorder as 'yes'; otherwise mark reorder as 'no' and quantity_due to 0. Check the count, update, read the row back."
Example output:
{"schema":"phi_judge/v0","fields":{"goal":{"instruction_says":"maintain reorder fields of GH-221","memory_says":"same","verdict":"match","note":"same maintenance goal"},"roles":{"instruction_says":"parts row GH-221","memory_says":"parts row GH-221","verdict":"match","note":"same subject row"},"branch_predicates":{"instruction_says":"on-hand count at least 15 -> reorder 'no'","memory_says":"on-hand count at least 15 -> reorder 'yes'","verdict":"contradict","note":"same comparator, opposite outcome per branch"},"transfer_direction":{"instruction_says":null,"memory_says":null,"verdict":"not_applicable","note":"no transfer in either"},"aggregation_scope":{"instruction_says":null,"memory_says":null,"verdict":"not_applicable","note":"no aggregation in either"},"required_operations":{"instruction_says":"check count, update, read back","memory_says":"check, update, read back","verdict":"match","note":"same operations"},"write_effects":{"instruction_says":"reorder 'no' when >=15","memory_says":"reorder 'yes' when >=15","verdict":"contradict","note":"opposite end state under same condition"}},"verdict":"contradict"}

Now do the same for the real pair below. Output only the JSON object, nothing else.

INSTRUCTION:
<<<{INSTRUCTION}>>>
MEMORY:
<<<{MEMORY}>>>"""

REPAIR_PROMPT_V0 = """The JSON you emitted was invalid.
Problem: {ERROR}
Re-emit ONLY the corrected compact JSON object. Top-level keys exactly: "schema" (value "phi_judge/v0"), "fields", "verdict", same definitions as before. No prose, no fences.

INSTRUCTION:
<<<{INSTRUCTION}>>>
MEMORY:
<<<{MEMORY}>>>"""

DECODE = {"temperature": 0.0, "top_p": 1.0, "max_tokens": 512, "seed": 42}
BATCH = 64


def run_one_round(llm, tok, sp, jobs):
    prompts = []
    for j in jobs:
        user = j.get("prompt") or JUDGE_PROMPT_V0.replace("{INSTRUCTION}", j["instruction"]).replace("{MEMORY}", j["memory"])
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
            ok, vcls, vdet = C.validate_judge(obj)
            if not ok:
                err_cls, err_det = vcls or "schema_validation_error", vdet
                obj = None
        rows.append({"key": j["key"], "raw": raw, "finish_reason": finish,
                     "judge": obj, "error_class": err_cls, "error_detail": err_det})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default=str(C.OUT / "judgments.jsonl"))
    args = ap.parse_args()

    out_path = pathlib.Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pairs = C.load_pairs()
    done = C.done_keys(out_path)
    todo = [r for r in pairs if r["memory_id"] not in done]
    if args.limit:
        todo = todo[:args.limit]
    print(f"[judge] pairs={len(pairs)} done={len(done)} todo={len(todo)}", flush=True)
    if not todo:
        return

    from vllm import LLM, SamplingParams
    from vllm.sampling_params import GuidedDecodingParams
    sp = SamplingParams(**DECODE, guided_decoding=GuidedDecodingParams(json=C.JUDGE_GUIDE_SCHEMA))
    llm = LLM(model=C.MODEL_ID, revision=C.MODEL_REV, dtype="float16",
              gpu_memory_utilization=0.85, max_model_len=4096, seed=42,
              guided_decoding_backend="outlines")
    tok = llm.get_tokenizer()
    prompt_sha = C.sha(SYSTEM_V0 + "\n" + JUDGE_PROMPT_V0 + "\n" + REPAIR_PROMPT_V0)
    meta = {"prompt_sha": prompt_sha, "model": C.MODEL_ID, "revision": C.MODEL_REV,
            "decode": DECODE, "guided": "json:JUDGE_GUIDE_SCHEMA(outlines)"}

    fh = open(out_path, "a")
    t0 = time.time()
    n_done_total = 0
    for b0 in range(0, len(todo), BATCH):
        chunk = todo[b0:b0 + BATCH]
        jobs = [{"key": r["memory_id"], "instruction": r["instruction"], "memory": r["memory_text"]} for r in chunk]
        rows = run_one_round(llm, tok, sp, jobs)
        retry_jobs = []
        for j, r in zip(jobs, rows):
            if r["error_class"] is not None:
                if r.get("finish_reason") == "length":
                    emsg = ("output hit the token budget before the JSON closed; re-emit more compact, "
                            "shorter quotes")
                elif r["error_class"] == "json_parse_error":
                    emsg = f"output was not valid JSON ({str(r['error_detail'])[:120]})"
                else:
                    emsg = "output JSON did not match the required schema/keys"
                retry_jobs.append({**j, "prompt": REPAIR_PROMPT_V0.replace(
                    "{ERROR}", emsg)
                    .replace("{INSTRUCTION}", j["instruction"]).replace("{MEMORY}", j["memory"])})
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
        for r, src in zip(rows, chunk):
            r.update(meta)
            r["memory_id"] = src["memory_id"]
            r["family_idx"] = src["family_idx"]
            r["target_sibling"] = src["target_sibling"]
            r["valid"] = r["judge"] is not None
            r["verdict"] = r["judge"]["verdict"] if r["judge"] else None
        C.append_rows(out_path, rows, fh)
        n_done_total += len(rows)
        n_bad = sum(1 for r in rows if not r["valid"])
        print(f"[judge] {n_done_total}/{len(todo)} invalid={n_bad} elapsed={time.time()-t0:.0f}s", flush=True)
    fh.close()


if __name__ == "__main__":
    main()
