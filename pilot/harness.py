"""Agent harness for the CausalMemBench mini-pilot (SPEC.md section 5).

vLLM offline engine + synchronous-step ReAct loop. Memory injection is FIXED
(Stage A): the system prompt has a permanent [MEMORY] block format; the block
holds exactly one candidate procedural card (or is omitted in the N cell).

The harness is agent-side code: it reads ONLY the public view (task text,
tool schema, initial rows, memory text). Family/cell/program labels never
enter a prompt. Compliance is measured post-hoc from text overlap only
(documented heuristic, SPEC section 5).

Usage (instruction-following self-check, SPEC section 5):
  python harness.py --selfcheck --model qwen1.5b --config configs/pilot.yaml
"""

import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from env_relationalops import RelationalOpsEnv, TOOLS
from generate_families import (load_config, content_tokens, CELL_RANK)

# ---------------------------------------------------------------------------
# prompts
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a careful data-operations agent working in a relational (SQLite) environment.

At every step you output EXACTLY ONE action as a single JSON object and nothing else:
{"tool": TOOL_NAME, "args": {...}}
Never add prose, explanations, or several JSON objects in one step.

Tools and their arguments:
- list_tables: {"tool": "list_tables", "args": {}} -- list tables with their columns
- read: args {"table": NAME, "filter": {COL: VALUE, ...}, "limit": N(optional)} -- rows matching every equality condition in filter
- aggregate: args {"table": NAME, "agg": "count|sum|min|max|avg", "field": COL (required unless count), "filter": {COL: VALUE, ...} (optional)}
- insert: args {"table": NAME, "record": {COL: VALUE, ...}} -- insert one row
- update: args {"table": NAME, "set": {COL: VALUE, ...}, "where": {COL: VALUE, ...}} -- 'where' must be non-empty
- delete: args {"table": NAME, "where": {COL: VALUE, ...}} -- 'where' must be non-empty
- finish: args {"answer": "..."} -- end the episode when the required final state is reached

IMPORTANT argument format:
- filter and where are JSON OBJECTS mapping column names to values, e.g. {"sku": "AB-1234", "warehouse": "east"}.
- NEVER write SQL text like "sku = 'AB-1234'" or "email IS NULL" inside filter/where; use JSON only.
- For special comparisons use an operator object: {"status": {"$ne": "done"}}, {"qty": {"$gt": 10}}.

Examples of valid actions:
{"tool": "read", "args": {"table": "stock", "filter": {"sku": "AB-1234", "warehouse": "east"}}}
{"tool": "aggregate", "args": {"table": "subtasks", "agg": "count", "filter": {"tkey": "OPS-101", "status": {"$ne": "done"}}}}
{"tool": "update", "args": {"table": "customers", "set": {"status": "escalated", "priority_flag": 1}, "where": {"email": "a.b@example.com"}}}
{"tool": "insert", "args": {"table": "ticket_events", "record": {"id": 7001, "tkey": "OPS-101", "etype": "resolution", "note": "all done"}}}
{"tool": "delete", "args": {"table": "lead_notes", "where": {"email": "a.b@example.com"}}}

Work method:
1. First inspect the tables and the relevant rows (list_tables, then read with exact filters). Keep reading until you have located the exact target row(s) and the values you need.
2. Verify the current stored values before writing; then apply exactly the writes the task requires -- not more, not less. Once you have the values, compare them to the rule in the task and ACT: do not repeat a read you already did.
3. Read the rows back to confirm the new state, then call finish with a short answer. Never claim a change you did not actually write.

Some tasks include a [MEMORY] section in the user message. It contains a retrieved experience card from a past episode. You may follow it when it is relevant, but treat it as advice, not ground truth: the actual database state decides what is correct."""

FIRST_USER_TMPL = """Task:
{instruction}
{memory_block}
You have at most {max_steps} tool steps. Begin: first inspect the relevant rows (list_tables / read), then act step by step."""

MEMORY_BLOCK_TMPL = """
[MEMORY]
{memory_text}
[/MEMORY]
"""


# ---------------------------------------------------------------------------
# public-view loaders (agent-side inputs only)
# ---------------------------------------------------------------------------

def load_task(public_dir, task_id):
    with open(os.path.join(public_dir, "tasks", task_id + ".json")) as f:
        return json.load(f)


def load_memory(public_dir, memory_id):
    with open(os.path.join(public_dir, "memories", memory_id + ".json")) as f:
        return json.load(f)["text"]


# ---------------------------------------------------------------------------
# action parsing
# ---------------------------------------------------------------------------

def _json_candidates(text):
    """Yield raw JSON object substrings by balanced-brace scanning
    (string-aware, arbitrary nesting depth)."""
    for s, ch in enumerate(text):
        if ch != "{":
            continue
        depth, instr, esc = 0, False, False
        for i in range(s, len(text)):
            c = text[i]
            if instr:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    instr = False
            else:
                if c == '"':
                    instr = True
                elif c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        yield text[s:i + 1]
                        break


def parse_action(text):
    """Extract the first JSON object containing a valid tool call.
    Returns (action_dict, error_str|None)."""
    text = text.strip()
    # prefer fenced ```json blocks
    fence = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    cands = [fence.group(1)] if fence else []
    cands += list(_json_candidates(text))
    for cand in cands:
        try:
            obj = json.loads(cand)
        except Exception:
            continue
        if isinstance(obj, dict) and isinstance(obj.get("tool"), str):
            args = obj.get("args", {})
            if args is None:
                args = {}
            if not isinstance(args, dict):
                return None, "args is not an object"
            if obj["tool"] not in TOOLS:
                return None, "unknown tool %r" % obj["tool"]
            return {"tool": obj["tool"], "args": args}, None
    return None, "no JSON tool call found"


# ---------------------------------------------------------------------------
# compliance heuristics (text-level only; documented as heuristic)
# ---------------------------------------------------------------------------

def _word_ngrams(tokens, n):
    return set(tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1))


def compliance_features(memory_text, assistant_texts, executed_actions):
    """Two heuristic indicators that the agent engaged with the memory:
    - echo_frac: fraction of memory content lines (>=5 content tokens) whose
      6-gram (or shorter, if fewer tokens) has any overlap with the agent's
      own outputs.
    - step_action_coverage: memory lines that look like procedure steps whose
      salient tokens (content tokens minus first-word boilerplate) are covered
      at >=60% inside the concatenated executed action sequence.
    Both are surface heuristics, SPEC section 5 -- not proof of use."""
    lines = [l.strip(" -*[]0123456789.\t ") for l in memory_text.splitlines()]
    lines = [l for l in lines if len(content_tokens(l)) >= 5]
    agent_blob = " ".join(assistant_texts)
    agent_toks = content_tokens(agent_blob)
    agent_grams = {k: _word_ngrams(agent_toks, k) for k in (4, 6)}
    echoed = 0
    for l in lines:
        toks = content_tokens(l)
        k = 6 if len(toks) >= 6 else 4
        grams = _word_ngrams(toks, k)
        if grams & agent_grams[k]:
            echoed += 1
    echo_frac = echoed / max(1, len(lines))
    action_blob = json.dumps(executed_actions, sort_keys=True)
    act_toks = set(content_tokens(action_blob))
    covered = 0
    for l in lines:
        toks = set(content_tokens(l))
        if not toks:
            continue
        if len(toks & act_toks) / len(toks) >= 0.6:
            covered += 1
    coverage = covered / max(1, len(lines))
    return {"echo_frac": round(echo_frac, 4),
            "step_action_coverage": round(coverage, 4),
            "n_memory_lines": len(lines)}


# ---------------------------------------------------------------------------
# rollout engine
# ---------------------------------------------------------------------------

def load_model(model_repo, cfg):
    from vllm import LLM
    return LLM(model=model_repo,
               gpu_memory_utilization=cfg["harness"]["gpu_memory_utilization"],
               max_model_len=8192, dtype="float16", enforce_eager=False,
               disable_log_stats=True)


def _sampling_params(cfg, seed):
    from vllm import SamplingParams
    return SamplingParams(temperature=cfg["harness"]["temperature"],
                          top_p=cfg["harness"]["top_p"],
                          max_tokens=cfg["harness"]["max_tokens_per_step"],
                          seed=seed)


def run_rollouts(llm, episodes, cfg, batch_size=64):
    """episodes: list of {task, memory_text|None, meta{task_id, cell, seed,
    memory_id, model, family_idx(evaluator-side only for logging)}}.
    Returns list of result dicts; trajectories contain raw completions."""
    results = []
    for i0 in range(0, len(episodes), batch_size):
        chunk = episodes[i0:i0 + batch_size]
        results.extend(_run_chunk(llm, chunk, cfg))
    return results


def _run_chunk(llm, chunk, cfg):
    max_steps = cfg["harness"]["max_steps"]
    print("[harness] running chunk of %d episodes (max_steps=%d)"
          % (len(chunk), max_steps), flush=True)
    states = []
    for ep in chunk:
        env = RelationalOpsEnv(ep["task"]["tables"], ep.get("terminal") or [])
        mem_block = (MEMORY_BLOCK_TMPL.format(memory_text=ep["memory_text"])
                     if ep.get("memory_text") else "")
        msgs = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": FIRST_USER_TMPL.format(
                    instruction=ep["task"]["instruction"],
                    memory_block=mem_block,
                    max_steps=max_steps)}]
        states.append({"ep": ep, "env": env, "msgs": msgs,
                       "traj": [], "assistant_texts": [], "actions": [],
                       "done": False, "finished": False, "steps": 0,
                       "parse_ok": 0, "parse_fail": 0, "errors": 0,
                       "prompt_tokens": 0, "completion_tokens": 0})
    active = list(range(len(chunk)))
    while active:
        batch_msgs = [states[i]["msgs"] for i in active]
        batch_sp = [_sampling_params(cfg, states[i]["ep"]["meta"]["seed"])
                    for i in active]
        outs = llm.chat(batch_msgs, sampling_params=batch_sp,
                        add_generation_prompt=True, use_tqdm=False)
        still = []
        for idx, out in zip(active, outs):
            st = states[idx]
            text = out.outputs[0].text.strip()
            st["prompt_tokens"] += len(out.prompt_token_ids)
            st["completion_tokens"] += len(out.outputs[0].token_ids)
            st["steps"] += 1
            action, err = parse_action(text)
            tool_result = None
            if action is None:
                st["parse_fail"] += 1
                tool_result = {"error": "could not parse your action (%s); "
                               "output exactly one JSON object like "
                               '{"tool": "read", "args": {"table": "T", '
                               '"filter": {"col": "value"}}}' % err}
            else:
                st["parse_ok"] += 1
                if action["tool"] == "finish":
                    st["finished"] = True
                    st["done"] = True
                    tool_result = {"ok": True, "message": "episode finished"}
                else:
                    tool_result = st["env"].call(action["tool"], action["args"])
                    if tool_result.get("error"):
                        st["errors"] += 1
                    st["actions"].append(action)
            st["assistant_texts"].append(text)
            st["traj"].append({"step": st["steps"], "completion": text,
                               "parsed": action, "parse_error": err,
                               "tool_result": tool_result})
            st["msgs"].append({"role": "assistant", "content": text})
            st["msgs"].append({"role": "user", "content": "<tool_result>%s</tool_result>"
                               % json.dumps(tool_result, ensure_ascii=False)[:4000]})
            if not st["done"] and st["steps"] < max_steps:
                still.append(idx)
            elif st["steps"] >= max_steps:
                st["done"] = True
        active = still
    results = []
    for st in states:
        ep = st["ep"]
        term_ok, term_detail = st["env"].check_terminal()
        success = bool(st["finished"] and term_ok and ep.get("terminal"))
        compliance = None
        if ep.get("memory_text"):
            compliance = compliance_features(ep["memory_text"],
                                             st["assistant_texts"], st["actions"])
        results.append({
            "meta": ep["meta"],
            "success": success, "finished": st["finished"],
            "terminal_ok": term_ok, "terminal_detail": term_detail,
            "steps": st["steps"], "parse_ok": st["parse_ok"],
            "parse_fail": st["parse_fail"], "tool_errors": st["errors"],
            "prompt_tokens": st["prompt_tokens"],
            "completion_tokens": st["completion_tokens"],
            "n_actions": len(st["actions"]),
            "compliance": compliance,
            "trajectory": st["traj"],
            "config_hash": ep["meta"].get("config_hash"),
            "model": ep["meta"].get("model"),
            "git_commit": ep["meta"].get("git_commit"),
            "env_versions": ep["meta"].get("env_versions"),
            "ts": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
        })
    return results


# ---------------------------------------------------------------------------
# episode construction from sealed evaluation records (evaluator-side)
# ---------------------------------------------------------------------------

def build_episode(public_dir, sealed_task_row, memory_text, cell, seed, meta_extra):
    task = load_task(public_dir, sealed_task_row["task_id"])
    return {"task": {"instruction": task["instruction"], "tables": task["tables"]},
            "terminal": sealed_task_row["terminal"],
            "memory_text": memory_text,
            "meta": {"task_id": sealed_task_row["task_id"],
                     "memory_id": meta_extra.get("memory_id"),
                     "cell": cell, "seed": seed,
                     "family_idx": sealed_task_row["family_idx"],
                     "sibling_idx": sealed_task_row["sibling_idx"],
                     **{k: v for k, v in meta_extra.items() if k != "memory_id"}}}


# ---------------------------------------------------------------------------
# instruction-following self-check (SPEC section 5)
# ---------------------------------------------------------------------------

def selfcheck(config_path, model_key, n_tasks, out_log):
    cfg = load_config(config_path)
    pub = cfg["paths"]["public_view"]
    sealed = cfg["paths"]["sealed"]
    tasks = {}
    with open(os.path.join(sealed, "tasks_sealed.jsonl")) as f:
        for line in f:
            r = json.loads(line)
            if r["kind"] == "sibling" and r["seed"] == 0:
                tasks.setdefault(r["family_idx"], {})[r["sibling_idx"]] = r
    fam_ids = sorted(tasks)[:n_tasks]
    episodes = []
    for fi in fam_ids:
        row = tasks[fi][0]                     # N condition, sibling 0, seed 0
        episodes.append(build_episode(
            pub, row, None, "N", 0,
            {"memory_id": None, "model": model_key}))
    print("[selfcheck] %d N-condition tasks (families %s), model %s"
          % (len(episodes), fam_ids, model_key))
    llm = load_model(cfg["models"][model_key], cfg)
    results = run_rollouts(llm, episodes, cfg)
    tot_ok = sum(r["parse_ok"] for r in results)
    tot = sum(r["parse_ok"] + r["parse_fail"] for r in results)
    rate = tot_ok / max(1, tot)
    succ = sum(1 for r in results if r["success"])
    print("[selfcheck] parseable-action rate: %.3f (%d/%d steps)"
          % (rate, tot_ok, tot))
    print("[selfcheck] N-condition success on these tasks: %d/%d" % (succ, len(results)))
    for r in results:
        print("  fam %d: success=%s steps=%d parse=%d/%d tool_errors=%d"
              % (r["meta"]["family_idx"], r["success"], r["steps"],
                 r["parse_ok"], r["parse_ok"] + r["parse_fail"], r["tool_errors"]))
    if out_log:
        os.makedirs(os.path.dirname(out_log), exist_ok=True)
        with open(out_log, "w") as f:
            for r in results:
                f.write(json.dumps(r) + "\n")
    thr = cfg["harness"]["selfcheck_min_parseable"]
    ok = rate >= thr
    print("[selfcheck] gate: parseable %.3f %s %.2f -> %s"
          % (rate, ">=" if ok else "<", thr, "PASS" if ok else "FAIL"))
    return ok, rate, results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "configs", "pilot.yaml"))
    ap.add_argument("--selfcheck", action="store_true")
    ap.add_argument("--model", default="qwen1.5b")
    ap.add_argument("--n-tasks", type=int, default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    if args.selfcheck:
        cfg = load_config(args.config)
        n = args.n_tasks or cfg["harness"]["selfcheck_n_tasks"]
        out = args.out or os.path.join(
            cfg["paths"]["log_root"], "selfcheck_%s.jsonl" % args.model)
        ok, _, _ = selfcheck(args.config, args.model, n, out)
        sys.exit(0 if ok else 2)
    ap.error("nothing to do (use --selfcheck); smoke runs live in tests/smoke.py")


if __name__ == "__main__":
    main()
