"""H-DC (GATE_PROTOCOL.md Part IV, sections 18-21): build `dslice` cards.

Decision-aware compression of the SAME untruncated harvest trajectories that
produced the H-C `raw` cards.  Input records per memory_id:

  - raw map:  pilot/systems/raw_cards_map.jsonl
      (which harvest attempt was used; oracle_fallback flag)
  - harvest:  outputs/agent_memory/pilot/hc_raw_source_shard*-of-010.jsonl
      (full untruncated trajectories; attempt that succeeded)
  - oracle fallback rows: trajectory rebuilt deterministically from
    program_dsl.run_oracle_plan (same function build_raw_cards.py used; CPU
    only, no GPU).

Compression rules D1-D5 (section 20, executed literally):
  D1  every action JSON kept, original order.  The "action JSON" is the
      harness-parsed object (`parsed`); some raw completions carry orphaned
      non-JSON tail fragments after the first valid JSON object (harness
      parse artifact).  Cards store the canonical dump of the parsed object
      (json.dumps, ensure_ascii=False) -- the same action, zero non-action
      junk, no new content;
  D2  read/aggregate tool_result -> single-line summary:
      read:      {"table":..., "filter":..., "matched":<n rows>,
                  "first":{<filter cols + id>: <values of matched row 1>}}
      aggregate: result is already a single scalar -> kept verbatim;
  D3  list_tables tool_result dropped (action kept);
  D4  insert/update/delete tool_result dropped (action kept);
  D5  finish action + finish tool_result kept verbatim.

Dedup (pure deletion, no info loss): non-mutating steps (read / aggregate /
list_tables) whose action AND result are exact duplicates of an earlier step
are dropped, first occurrence kept.  Write/finish steps are never deduped.

No new natural language, no LLM, no paraphrase; kept items concatenated in
original order as  "step k: <action json>" / "<tool_result>...</tool_result>".

Over-budget escalation (section 20: escalate deletion until tool results are
gone), recorded as escalation_stage.  The section-20 QA invariants
(decision args, aggregate values, finish action retained at 100%) are treated
as inviolable, so escalation sacrifices least-decision-relevant content first:
  stage 0: base card (D1-D5);
  stage 1: drop the "first"-row key columns from read summaries;
  stage 2: drop read tool_result lines entirely (aggregate results kept);
  stage 3: drop the finish tool_result line (finish action kept);
  stage 4: drop non-decision action lines (list_tables / read actions);
  stage 5: drop aggregate action lines (aggregate results kept);
  stage 6: drop the "step k: " line prefixes (pure formatting);
  stage 7: hard token truncation at 300 (same code path as raw cards;
           any QA invariant broken here is counted as a QA-fail, gate = 0).

QA asserts (section 20/21), per card:
  - has_finish: if the trajectory contains a finish action, the card contains
    that finish action verbatim;
  - has_decision_args: every write action (insert/update/delete) present in
    the trajectory appears verbatim in the card;
  - no new entities/values: every string/number in a compressed summary is an
    exact substring of the source step's own JSON dump, and "matched" equals
    len(rows) of the source result;
  - token budget: all cards <= 300 Qwen2.5-1.5B tokens (TokenMeter, same as
    pilot); mean |token_count(dslice) - token_count(raw)| reported (gate <15
    is the paired-mean check in section 21).

Outputs:
  <public_view>/systems/dslice/<memory_id>.json   {"memory_id", "text"}
  pilot/dslice/cards_map.jsonl                    per-card audit map
"""

import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PILOT = os.path.dirname(_HERE)
sys.path.insert(0, _PILOT)

from generate_families import load_config, TokenMeter  # noqa: E402
from harness import load_task  # noqa: E402
from systems.build_raw_cards import (load_sealed, oracle_trajectory,  # noqa: E402
                                     truncate_card)

DEFAULT_CONFIG = os.path.join(_PILOT, "configs", "pilot_7b.yaml")
HARVEST_GLOB = "hc_raw_source_shard*-of-010.jsonl"
WRITE_TOOLS = ("insert", "update", "delete")
SEALED_FORBIDDEN = ("family_idx", "cell", "A00", "A01", "A10", "A11")


# ---------------------------------------------------------------------------
# harvest indexing
# ---------------------------------------------------------------------------

def index_harvest(cfg):
    """(memory_id, attempt) -> trajectory, for successful attempts only."""
    import glob
    idx = {}
    out_root = cfg["paths"]["output_root"]
    for path in sorted(glob.glob(os.path.join(out_root, HARVEST_GLOB))):
        with open(path) as f:
            for line in f:
                r = json.loads(line)
                if not r.get("success"):
                    continue
                idx[(r["meta"]["memory_id"], r["meta"]["attempt"])] = \
                    r["trajectory"]
    return idx


def trajectory_for(mem_row, harvest_idx, tasks, fams, pub):
    """Return the trajectory underlying this memory's raw card."""
    if mem_row["oracle_fallback"]:
        # rebuild deterministically (identical code path as build_raw_cards)
        mid = mem_row["memory_id"]
        # source task row via the same sealed mapping
        from systems.build_raw_cards import source_task_row
        mem_like = {"family_idx": mem_row["card_family_idx"],
                    "cell": mem_row["cell"],
                    "source_kind": mem_row["source_kind"],
                    "source_family": mem_row["source_family"],
                    "memory_id": mid}
        trow, _ = source_task_row(mem_like, tasks)
        fam_row = fams[trow["family_idx"]]
        tables = load_task(pub, trow["task_id"])["tables"]
        return oracle_trajectory(trow, fam_row, tables)
    key = (mem_row["memory_id"], mem_row["n_attempts"] - 1)
    if key not in harvest_idx:
        raise RuntimeError("harvest trajectory missing for %s attempt %d"
                           % key)
    return harvest_idx[key]


# ---------------------------------------------------------------------------
# D1-D5 compression
# ---------------------------------------------------------------------------

def read_summary(step):
    """D2 four-tuple for a read result: (table, filter, matched, first-row
    retrieval-key columns = filter columns + 'id')."""
    args = step["parsed"].get("args", {})
    res = step["tool_result"]
    rows = res.get("rows", [])
    filt = args.get("filter") or {}
    summ = {"table": args.get("table"), "filter": filt,
            "matched": len(rows)}
    if rows:
        keep = [k for k in list(filt.keys()) + ["id"] if k in rows[0]]
        summ["first"] = {k: rows[0][k] for k in keep}
    return summ


def action_copy(step):
    """Canonical action JSON copy (parsed object only; strips orphaned
    non-JSON tail fragments some raw completions carry)."""
    return json.dumps(step["parsed"], ensure_ascii=False)


def step_lines(step, stage):
    """Lines contributed by one trajectory step at the given escalation
    stage.  Prefixes are added by card_lines (stage 6 drops them)."""
    tool = step["parsed"]["tool"] if step.get("parsed") else None
    act = [action_copy(step)]
    res = ["<tool_result>%s</tool_result>"
           % json.dumps(step["tool_result"], ensure_ascii=False)]
    if tool in WRITE_TOOLS:                         # D4: action kept, result dropped
        return act
    if tool == "finish":                            # D5: action always kept
        return act + (res if stage < 3 else [])
    if tool == "aggregate":                         # D2 scalar: kept verbatim
        return (act if stage < 5 else []) + res     # (decision-critical, QA 100%)
    if tool == "list_tables":                       # D3: result dropped
        return act if stage < 4 else []
    if tool == "read" or "rows" in (step["tool_result"] or {}):
        if stage >= 4:
            return []
        if stage >= 2:
            return act
        summ = read_summary(step)                   # D2 four-tuple
        if stage >= 1:
            summ.pop("first", None)
        return act + ["<tool_result>%s</tool_result>"
                      % json.dumps(summ, ensure_ascii=False)]
    if stage >= 4:                                  # unknown tool
        return []
    return act + res


def card_lines(traj, stage):
    """Deduped, prefixed card lines for the whole trajectory."""
    seen, steps = set(), []
    for s in traj:
        tool = s["parsed"]["tool"] if s.get("parsed") else None
        if tool in ("read", "aggregate", "list_tables"):
            sig = (action_copy(s),
                   json.dumps(s["tool_result"], ensure_ascii=False))
            if sig in seen:
                continue
            seen.add(sig)
        steps.append(s)
    lines = []
    for s in steps:
        for l in step_lines(s, stage):
            if not l.startswith("<tool_result>"):
                lines.append(l if stage >= 6 else "step %d: %s" % (s["step"], l))
            else:
                lines.append(l)
    return lines


def build_card(traj, meter, max_tok):
    """Apply D1-D5 + escalation until <= max_tok. Returns
    (text, n_tok, stage, truncated_flag)."""
    for stage in range(7):
        text = "\n".join(card_lines(traj, stage))
        n = meter.count(text)
        if n <= max_tok:
            return text, n, stage, False
    text, n, truncated = truncate_card(
        "\n".join(card_lines(traj, 6)), meter, max_tok)
    return text, n, 7, truncated


# ---------------------------------------------------------------------------
# QA
# ---------------------------------------------------------------------------

def qa_card(traj, text):
    """Returns (qa_fail_list, has_finish, has_decision_args)."""
    fails = []
    # finish retained
    finishes = [s for s in traj
                if s.get("parsed") and s["parsed"]["tool"] == "finish"]
    has_finish = any(action_copy(s) in text for s in finishes)
    if finishes and not has_finish:
        fails.append("finish_action_lost")
    # decision args retained (write actions verbatim)
    writes = [s for s in traj
              if s.get("parsed") and s["parsed"]["tool"] in WRITE_TOOLS]
    has_decision_args = all(action_copy(s) in text for s in writes)
    if not has_decision_args:
        fails.append("decision_args_lost")
    # aggregate values retained (decision-critical numbers, section 20)
    for s in traj:
        if s.get("parsed") and s["parsed"]["tool"] == "aggregate":
            v = json.dumps(s["tool_result"], ensure_ascii=False)
            if v not in text:
                fails.append("aggregate_value_lost@%d" % s["step"])
    # no new entities/values inside compressed read summaries
    for s in traj:
        if not s.get("parsed") or s["parsed"]["tool"] != "read":
            continue
        marker = '"matched": %d' % len(s["tool_result"].get("rows", []))
        if marker in text:
            src_dump = json.dumps(s["tool_result"], ensure_ascii=False) \
                + s["completion"]
            summ = read_summary(s)
            vals = list(summ.get("first", {}).values()) \
                + [summ["table"]] + list((summ["filter"] or {}).values())
            for v in vals:
                if json.dumps(v, ensure_ascii=False).strip('"') not in src_dump:
                    fails.append("new_entity@%d:%r" % (s["step"], v))
    # global: no sealed vocabulary leaked
    for w in SEALED_FORBIDDEN:
        if w in text:
            fails.append("sealed_leak:%s" % w)
    return fails, has_finish, has_decision_args


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    cfg = load_config(args.config)
    cfg["_config_path"] = args.config
    os.environ.setdefault("HF_HOME", cfg["paths"]["hf_home"])
    pub = cfg["paths"]["public_view"]
    mem_min = cfg["memories"]["tokens_min"]
    mem_max = cfg["memories"]["tokens_max"]

    map_path = os.path.join(_PILOT, "systems", "raw_cards_map.jsonl")
    with open(map_path) as f:
        rows = [json.loads(l) for l in f]
    if args.limit:
        rows = rows[:args.limit]
    print("[dslice] %d raw-card rows -> building dslice cards" % len(rows))

    mems, tasks, fams = load_sealed(cfg["paths"]["sealed"])
    harvest_idx = index_harvest(cfg)
    print("[dslice] harvest index: %d successful trajectories" % len(harvest_idx))

    meter = TokenMeter(cfg["memories"]["tokenizer"])
    out_dir = os.path.join(pub, "systems", "dslice")
    os.makedirs(out_dir, exist_ok=True)

    out_rows, qa_fail_total = [], 0
    for r in rows:
        traj = trajectory_for(r, harvest_idx, tasks, fams, pub)
        text, n_tok, stage, hard = build_card(traj, meter, mem_max)
        fails, has_fin, has_args = qa_card(traj, text)
        qa_fail_total += len(fails)
        with open(os.path.join(out_dir, r["memory_id"] + ".json"), "w") as f:
            json.dump({"memory_id": r["memory_id"], "text": text}, f,
                      indent=1, sort_keys=True)
        out_rows.append({
            "memory_id": r["memory_id"], "cell": r["cell"],
            "card_family_idx": r["card_family_idx"],
            "card_sibling_idx": r["card_sibling_idx"],
            "oracle_fallback": r["oracle_fallback"],
            "n_tokens": n_tok, "escalation_stage": stage,
            "hard_truncated": hard,
            "below_window": n_tok < mem_min,
            "has_finish": has_fin, "has_decision_args": has_args,
            "qa_fails": fails})

    os.makedirs(_HERE, exist_ok=True)
    with open(os.path.join(_HERE, "cards_map.jsonl"), "w") as f:
        for o in out_rows:
            f.write(json.dumps(o, sort_keys=True) + "\n")

    # ---- report / asserts -------------------------------------------------
    import statistics
    toks = [o["n_tokens"] for o in out_rows]
    raw_toks = {r["memory_id"]: r["n_tokens_card"] for r in rows}
    diffs = [abs(o["n_tokens"] - raw_toks[o["memory_id"]]) for o in out_rows]
    from collections import Counter
    print("[dslice] cards=%d  tokens: min=%d mean=%.1f max=%d"
          % (len(out_rows), min(toks), statistics.mean(toks), max(toks)))
    print("[dslice] vs raw: mean|dtok|=%.2f (gate <15)  raw_mean=%.1f"
          % (statistics.mean(diffs),
             statistics.mean(raw_toks[o["memory_id"]] for o in out_rows)))
    print("[dslice] escalation stages: %s"
          % dict(Counter(o["escalation_stage"] for o in out_rows)))
    print("[dslice] below_200=%d has_finish=%d/%d has_decision_args=%d/%d"
          % (sum(o["below_window"] for o in out_rows),
             sum(o["has_finish"] for o in out_rows), len(out_rows),
             sum(o["has_decision_args"] for o in out_rows), len(out_rows)))
    print("[dslice] QA fails total=%d %s"
          % (qa_fail_total, dict(Counter(
              e.rsplit("@", 1)[0].split(":")[0]
              for o in out_rows for e in o["qa_fails"]))))
    if qa_fail_total:
        for o in out_rows:
            if o["qa_fails"]:
                print("  QA-FAIL %s %s" % (o["memory_id"], o["qa_fails"]))
    print("[dslice] cards -> %s ; map -> %s"
          % (out_dir, os.path.join(_HERE, "cards_map.jsonl")))


if __name__ == "__main__":
    main()
