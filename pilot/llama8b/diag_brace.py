"""Diagnostic: does llama8b's eot/stop plumbing eat the final '}'?

Reconstructs the exact failing conversation (family 4, N cell, step 3) from
the selfcheck rollout log and re-generates with inspectable token ids.
Run: CUDA_VISIBLE_DEVICES=0 python llama8b/diag_brace.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from generate_families import load_config
from harness import (SYSTEM_PROMPT, FIRST_USER_TMPL, MEMORY_BLOCK_TMPL,
                     load_task, build_episode, parse_action)

CFG = "/work1/zixuan/projects/agent_memory/pilot/configs/pilot_llama8b.yaml"
LOG = "/work1/zixuan/logs/agent_memory/selfcheck_llama8b.jsonl"

cfg = load_config(CFG)
# grab family-4 episode (N cell) and its failing trajectory
row = None
for line in open(LOG):
    r = json.loads(line)
    if r["meta"]["family_idx"] == 4:
        row = r
        break
assert row, "fam4 not in selfcheck log"

# rebuild the sealed task row to reconstruct the prompt
sealed = cfg["paths"]["sealed"]
srow = None
for line in open(os.path.join(sealed, "tasks_sealed.jsonl")):
    t = json.loads(line)
    if (t["kind"] == "sibling" and t["family_idx"] == 4
            and t["sibling_idx"] == 0 and t["seed"] == 0):
        srow = t
        break
task = load_task(cfg["paths"]["public_view"], srow["task_id"])
max_steps = cfg["harness"]["max_steps"]

msgs = [{"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": FIRST_USER_TMPL.format(
            instruction=task["instruction"], memory_block="",
            max_steps=max_steps)}]
# replay steps 1..2 (assistant + tool_result) from the stored trajectory
for t in row["trajectory"][:2]:
    msgs.append({"role": "assistant", "content": t["completion"]})
    msgs.append({"role": "user", "content": "<tool_result>%s</tool_result>"
                 % json.dumps(t["tool_result"], ensure_ascii=False)[:4000]})
print("=== failing step-3 prompt reconstructed; stored failing completion:")
print(repr(row["trajectory"][2]["completion"]))

from vllm import LLM, SamplingParams
llm = LLM(model=cfg["models"]["llama8b"],
          gpu_memory_utilization=cfg["harness"]["gpu_memory_utilization"],
          max_model_len=8192, dtype="float16", enforce_eager=False,
          disable_log_stats=True)
tok = llm.get_tokenizer()

for name, sp in [
    ("seeded(temp=0.7,seed=0)", SamplingParams(
        temperature=0.7, top_p=0.9, max_tokens=512, seed=0)),
    ("greedy", SamplingParams(temperature=0.0, max_tokens=512)),
]:
    out = llm.chat([msgs], sampling_params=[sp] if not isinstance(sp, SamplingParams) else sp,
                   add_generation_prompt=True, use_tqdm=False)[0]
    o = out.outputs[0]
    ids = list(o.token_ids)
    print("\n=== %s: finish_reason=%s stop_reason=%r n_tokens=%d"
          % (name, o.finish_reason, getattr(o, "stop_reason", None), len(ids)))
    print("last 12 tokens:", [tok.decode([i]) for i in ids[-12:]])
    print("text:", repr(o.text))
    act, err = parse_action(o.text)
    print("parse:", act if act else err)
