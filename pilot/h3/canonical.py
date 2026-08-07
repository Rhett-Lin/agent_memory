"""H3 canonical card construction (GATE_PROTOCOL.md Part III sec.14-15).

For every A-cell memory in the H3 sealed set (32 fresh families x 4 siblings
x cells A00/A01/A10/A11; Q sham rows skipped) this script reconstructs the
SOURCE task (same mapping as H-C systems/build_raw_cards.py), derives ONE
canonical proposition sequence from the task's sealed oracle_plan (executed
once against the public tables so every observed number is real), and renders
FIVE arm cards from exactly that sequence:

  transcript_complete  : dialogue log ("user:" turn + step k tool-call JSON
                         lines + summarized <tool_result> lines), full
                         sequence incl. the write-decision line and finish.
  transcript_prefix    : the same transcript cut by the H-C rule: tokens up
                         to min(300, start of the write-decision) -- the
                         decision/write/verify/finish tail is dropped.
  script_complete      : imperative card (Retrieved experience header,
                         Task, numbered Procedure incl. the decision step,
                         Postconditions) -- same canonical propositions,
                         template-only, no LLM summarization (sec.14.5).
  script_prefix        : the same script cut by the same rule.
  eco                  : the transcript cut at EXACTLY 300 tokens regardless
                         of proposition boundaries (H-C verbatim hard cut;
                         ecological arm, not part of the 2x2).

Checks (fail-loud): (a) proposition marker coverage transcript vs script at
the same coverage (all pairs, complete + prefix) -> canonical_sa_report.json;
(b) prefix arms lack write-decision+finish, complete arms contain both
(per-card assert); (c) isolation scan of card TEXT with FORBIDDEN_RE_CS/CI;
(d) per-arm token stats (Qwen2.5-1.5B) -> canonical_tokenstats.json;
(e) 5 verbatim transcript/script complete pairs -> canonical_samples.md.

Outputs: public_view/cards/<arm>/<memory_id>.json + pilot/h3/cards_map.jsonl.
Sealed inputs are read-only. Run:
  /work1/zixuan/envs/conda_envs/causalmemagent/bin/python pilot/h3/canonical.py
"""

import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PILOT = os.path.dirname(_HERE)
sys.path.insert(0, _PILOT)

from generate_families import (load_config, TokenMeter,   # noqa: E402
                               FORBIDDEN_RE_CI, FORBIDDEN_RE_CS)
from program_dsl import ARCHETYPES, run_oracle_plan        # noqa: E402
from env_relationalops import RelationalOpsEnv            # noqa: E402

DEFAULT_CONFIG = os.path.join(_HERE, "configs", "h3.yaml")
A_CELLS = ["A00", "A01", "A10", "A11"]
ARMS = ["transcript_complete", "transcript_prefix",
        "script_complete", "script_prefix", "eco"]


# ---------------------------------------------------------------------------
# sealed loading + source-task mapping (identical semantics to H-C
# systems/build_raw_cards.py: the generator built every card from the
# seed-0 instance roles, sibling 0)
# ---------------------------------------------------------------------------

def load_sealed(sealed_dir):
    mems, tasks, fams = [], {}, {}
    with open(os.path.join(sealed_dir, "memories_sealed.jsonl")) as f:
        for line in f:
            mems.append(json.loads(line))
    with open(os.path.join(sealed_dir,
                           "tasks_sealed.jsonl")) as f:
        for line in f:
            r = json.loads(line)
            tasks[(r["kind"], r["family_idx"], r["sibling_idx"], r["seed"])] = r
    with open(os.path.join(sealed_dir, "families.jsonl")) as f:
        for line in f:
            r = json.loads(line)
            fams[r["family_idx"]] = r
    return mems, tasks, fams


def source_task_row(mem, tasks):
    fidx, cell = mem["family_idx"], mem["cell"]
    if cell == "A11":
        key = ("sibling", fidx, 0, 0)
    elif cell == "A10":
        key = ("sibling", mem["source_family"], 0, 0)
    elif cell == "A01":
        key = ("near_miss", fidx, 0, 0)
    elif cell == "A00":
        key = ("sibling", mem["source_family"], 0, 0)
    else:
        raise RuntimeError("unexpected cell %r" % cell)
    if key not in tasks:
        raise RuntimeError("source task %r missing for memory %s"
                           % (key, mem["memory_id"]))
    return tasks[key], "%s/fam%d/sib%d/seed%d" % key


# ---------------------------------------------------------------------------
# value rendering (single helper set -> identical fragments in both forms)
# ---------------------------------------------------------------------------

_OPS = {"$ne": "!=", "$lt": "<", "$le": "<=", "$gt": ">", "$ge": ">="}


def fmt(v):
    if v is None:
        return "null"
    if isinstance(v, str):
        return "'%s'" % v
    return str(v)


def kv(d):
    return ", ".join("%s=%s" % (k, fmt(v)) for k, v in d.items())


def flt(d):
    parts = []
    for k, v in (d or {}).items():
        if isinstance(v, dict):
            op, val = next(iter(v.items()))
            parts.append("%s%s%s" % (k, _OPS[op], fmt(val)))
        else:
            parts.append("%s=%s" % (k, fmt(v)))
    return " and ".join(parts)


def agg_label(a):
    return "%s(%s)" % (a["agg"], a.get("field") or "*")


def action_json(tool, args):
    return json.dumps({"tool": tool, "args": args}, sort_keys=True,
                      ensure_ascii=False)


# ---------------------------------------------------------------------------
# canonical proposition sequence
# ---------------------------------------------------------------------------

def execute_task(task_row, fam_row, tables):
    """Run the sealed oracle plan against the public tables; returns trace."""
    env = RelationalOpsEnv(tables, task_row["terminal"])
    prog = ARCHETYPES[fam_row["archetype"]](task_row["program_params"])
    ok, trace = run_oracle_plan(env, prog, task_row["oracle_plan"])
    if not ok:
        raise RuntimeError("oracle plan failed for %s: %s"
                           % (task_row["task_id"], trace))
    return trace


def observed_at_check(check_args, trace):
    """Observed value(s) for a CHECK step, taken from the executed trace."""
    kind = check_args["kind"]
    if kind == "field_cmp":
        for e in trace:
            if e.get("tool") == "read" and e["args"]["table"] == check_args["table"] \
                    and e["args"].get("filter") == check_args["where"]:
                return e["result"]["rows"][0][check_args["field"]]
    elif kind == "agg_cmp":
        for e in trace:
            if e.get("tool") == "aggregate" and e["args"] == check_args["agg_args"]:
                return e["result"]["value"]
    elif kind == "transfer_guard":
        vals = {}
        for side in ("a", "b"):
            w = check_args[side]
            for e in trace:
                if e.get("tool") == "read" and e["args"]["table"] == w["table"] \
                        and e["args"].get("filter") == w["where"]:
                    vals[side] = e["result"]["rows"][0][w["field"]]
        if len(vals) == 2:
            return vals
    raise RuntimeError("cannot recover observed values for check %r" % check_args)


def finish_answer(terminal):
    parts = []
    for p in terminal:
        t = p["type"]
        if t == "field_cmp":
            parts.append("%s %s=%s" % (p["table"], p["field"], fmt(p["value"])))
        elif t == "exists":
            parts.append("%s entry present" % p["table"])
        elif t == "not_exists":
            parts.append("%s row removed" % p["table"])
        else:
            parts.append("%s %s %s %s" % (p["table"], t, p.get("op"),
                                          p.get("value")))
    return "final state verified: " + "; ".join(parts)


def build_canonical(task_row, fam_row, tables):
    """Ordered proposition list for the source episode. Each prop:
    {idx, step_id, op, role, tool, args, result, markers}.
    Roles: read | aggregate | write_decision | write | verify | finish."""
    trace = execute_task(task_row, fam_row, tables)
    by_step = {e["step"]: e for e in trace}
    props = []
    for s in task_row["oracle_plan"]:
        sid, tool, args = s["step_id"], s["tool"], s["args"]
        if tool == "__check__":
            a = dict(args)
            a["branch"] = by_step[sid]["result"]
            a["obs"] = observed_at_check(args, trace)
            props.append(make_prop(props, sid, "check", "write_decision",
                                   "__check__", a, None))
        elif tool == "read":
            role = "verify" if sid.endswith("verify") else "read"
            props.append(make_prop(props, sid, role, role, tool, args,
                                   by_step[sid]["result"]))
        elif tool == "aggregate":
            props.append(make_prop(props, sid, "aggregate", "aggregate", tool,
                                   args, by_step[sid]["result"]))
        else:                                   # update / insert / delete
            props.append(make_prop(props, sid, "write", "write", tool, args,
                                   by_step[sid]["result"]))
    props.append(make_prop(props, "s_finish", "finish", "finish", "finish",
                           {"answer": finish_answer(task_row["terminal"])}, None))
    # decision text needs the write short-form of the decided write(s)
    writes = [p for p in props if p["role"] == "write"]
    for p in props:
        if p["role"] == "write_decision":
            p["args"]["write_short"] = "; then ".join(write_short(q["args"])
                                                      for q in writes)
    for p in props:
        p["markers"] = prop_markers(p)
    return props


def make_prop(props, step_id, op, role, tool, args, result):
    p = {"idx": len(props), "step_id": step_id, "op": op, "role": role,
         "tool": tool, "args": args, "result": result}
    return p


def prop_markers(p):
    """Text fragments that MUST appear in both forms at the same coverage."""
    a = p["args"]
    if p["op"] == "read":
        return [a["table"]] + [flt({k: v}) for k, v in
                               (a.get("filter") or {}).items()]
    if p["op"] == "aggregate":
        return [agg_label(a),
                "%s = %s" % (agg_label(a), p["result"]["value"])]
    if p["op"] == "check":
        kind, obs = a["kind"], a["obs"]
        if kind in ("field_cmp", "agg_cmp"):
            return ["%s %s %s" % (fmt(obs), a["op"], fmt(a["value"]))]
        return ["amount=%s" % a["amount"],
                "%s=%s" % (a["a"]["field"], fmt(obs["a"])),
                "%s=%s" % (a["b"]["field"], fmt(obs["b"]))]
    if p["op"] == "write":
        m = [a["table"]]
        if a.get("where"):
            m += [flt({k: v}) for k, v in a["where"].items()]
        for d in (a.get("set"), a.get("record")):
            if d:
                m += ["%s=%s" % (k, fmt(v)) for k, v in d.items()]
        return m
    if p["op"] == "verify":
        return [a["table"]] + [flt({k: v}) for k, v in
                               (a.get("filter") or {}).items()]
    return [a["answer"]]                            # finish


def write_short(a):
    if "set" in a:
        return "set %s on %s where %s" % (kv(a["set"]), a["table"],
                                          flt(a["where"]))
    if "record" in a:
        return "insert into %s: %s" % (a["table"], kv(a["record"]))
    return "delete from %s where %s" % (a["table"], flt(a["where"]))


def decision_text(a):
    kind, obs, branch = a["kind"], a["obs"], a["branch"]
    if kind == "field_cmp":
        claim = "%s %s %s is %s" % (fmt(obs), a["op"], fmt(a["value"]),
                                    "true" if branch == "A" else "false")
        return ("%s of the %s row where %s is %s: %s; apply the rule -> %s"
                % (a["field"], a["table"], flt(a["where"]), fmt(obs), claim,
                   a["write_short"]))
    if kind == "agg_cmp":
        claim = "%s %s %s is %s" % (obs, a["op"], fmt(a["value"]),
                                    "true" if branch == "A" else "false")
        return ("the %s over %s where %s is %s: %s; apply the rule -> %s"
                % (agg_label(a["agg_args"]), a["agg_args"]["table"],
                   flt(a["agg_args"].get("filter")), obs, claim,
                   a["write_short"]))
    if kind == "transfer_guard":
        va, vb = obs["a"], obs["b"]
        return ("%s where %s has %s=%s and %s where %s has %s=%s: amount=%d "
                "fits the guard (source keeps %s >= %s, destination reaches "
                "%s <= %s) -> allowed; apply the rule -> %s"
                % (a["a"]["table"], flt(a["a"]["where"]), a["a"]["field"],
                   fmt(va), a["b"]["table"], flt(a["b"]["where"]),
                   a["b"]["field"], fmt(vb), a["amount"],
                   va - a["amount"], a["min_a"],
                   vb + a["amount"], a["cap_b"], a["write_short"]))
    raise RuntimeError("unknown check kind %r" % kind)


# ---------------------------------------------------------------------------
# renderers: segments tagged with prop idx (-1 header, -2 postcondition tail)
# ---------------------------------------------------------------------------

def result_summary(p):
    a, res = p["args"], p["result"]
    if p["op"] in ("read", "verify"):
        head = "%d row(s) from %s" % (res["n"], a["table"])
        if a.get("filter"):
            head += " where " + flt(a["filter"])
        rows = ["row: " + kv(r) for r in res["rows"][:3]]
        if res["n"] > 3:
            rows.append("+%d more" % (res["n"] - 3))
        return head + ("; " + "; ".join(rows) if rows else "")
    if p["op"] == "aggregate":
        return "%s over %s where %s; %s = %s" % (
            agg_label(a), a["table"], flt(a.get("filter")),
            agg_label(a), res["value"])
    if "set" in a:
        return "updated %d row(s) in %s where %s" % (
            res["updated"], a["table"], flt(a["where"]))
    if "record" in a:
        return "inserted 1 row into %s: %s" % (a["table"], kv(res["record"]))
    return "deleted %d row(s) from %s where %s" % (
        res["deleted"], a["table"], flt(a["where"]))


def transcript_segments(props, instruction):
    segs = [(-1, "user: %s\n" % instruction)]
    for k, p in enumerate(props, 1):
        if p["op"] == "check":
            segs.append((p["idx"], "step %d (decision): %s\n"
                         % (k, decision_text(p["args"]))))
        elif p["op"] == "finish":
            segs.append((p["idx"], "step %d: %s\n"
                         % (k, action_json("finish", p["args"]))))
            segs.append((p["idx"], '<tool_result>{"ok": true, "message": '
                                   '"episode finished"}</tool_result>\n'))
        else:
            segs.append((p["idx"], "step %d: %s\n"
                         % (k, action_json(p["tool"], p["args"]))))
            segs.append((p["idx"], "<tool_result>%s</tool_result>\n"
                         % result_summary(p)))
    return segs


def script_segments(props, instruction, terminal):
    segs = [(-1, "Retrieved experience - episode outcome: SUCCESS.\n"),
            (-1, "Task: %s\n" % instruction),
            (-1, "Procedure:\n")]
    for k, p in enumerate(props, 1):
        a = p["args"]
        if p["op"] == "read":
            s = "Read the %s row where %s." % (a["table"], flt(a.get("filter")))
        elif p["op"] == "aggregate":
            s = "Compute %s over the %s rows where %s; %s = %s." % (
                agg_label(a), a["table"], flt(a.get("filter")),
                agg_label(a), p["result"]["value"])
        elif p["op"] == "check":
            s = "Check the decision rule: %s." % decision_text(a)
        elif p["op"] == "write":
            if "set" in a:
                s = "Set %s on the %s row where %s." % (kv(a["set"]), a["table"],
                                                        flt(a["where"]))
            elif "record" in a:
                s = "Insert into %s the row: %s." % (a["table"], kv(a["record"]))
            else:
                s = "Delete the %s rows where %s." % (a["table"], flt(a["where"]))
        elif p["op"] == "verify":
            rows = p["result"]["rows"]
            if rows:
                s = ("Read the %s row where %s back and confirm %s."
                     % (a["table"], flt(a.get("filter")),
                        "; ".join(kv(r) for r in rows[:3])))
            else:
                s = ("Read the %s rows where %s back and confirm no row "
                     "remains." % (a["table"], flt(a.get("filter"))))
        else:                                       # finish
            s = "Finish the episode and report: %s." % a["answer"]
        segs.append((p["idx"], "%d. %s\n" % (k, s)))
    segs.append((-2, "Postconditions:\n"))
    for t in terminal:
        segs.append((-2, "- %s\n" % terminal_sentence(t)))
    return segs


def terminal_sentence(p):
    t = p["type"]
    if t == "field_cmp":
        return "The %s row where %s shows %s=%s." % (
            p["table"], flt(p.get("where")), p["field"], fmt(p["value"]))
    if t == "exists":
        return "A %s row where %s exists." % (p["table"], flt(p.get("where")))
    if t == "not_exists":
        return "No %s row where %s remains." % (p["table"], flt(p.get("where")))
    if t == "row_count":
        return "The %s rows where %s number %s %s." % (
            p["table"], flt(p.get("where")), p["op"], p["value"])
    return "%s: %s" % (t, json.dumps(p, sort_keys=True))


# ---------------------------------------------------------------------------
# arm construction (H-C truncation rule: cut at min(300, decision start))
# ---------------------------------------------------------------------------

def build_arm_texts(segments, props, meter):
    """Coverage-first cut (sec.14.3): prefix = everything BEFORE the
    write-decision proposition, so prefix misses exactly decision/write/
    verify/finish.  truncated_to = its token count; cards outside the
    200-300 window are reported, never force-cut (a hard 300 cut could
    silently eat pre-decision propositions, re-introducing the H-C
    coverage confound; the messy hard cut is exactly the eco arm)."""
    decision_idx = next(p["idx"] for p in props if p["role"] == "write_decision")
    full = "".join(s for _, s in segments)
    pre = ""
    for idx, s in segments:
        if idx == decision_idx:
            break
        pre += s
    n_pre = meter.count(pre)
    return {"complete": full, "n_complete": meter.count(full),
            "prefix": pre, "truncated_to": n_pre}


# ---------------------------------------------------------------------------
# checks
# ---------------------------------------------------------------------------

def has_decision(form, text):
    return "(decision):" in text if form == "transcript" \
        else "Check the decision rule:" in text


def has_finish(form, text):
    return '"tool": "finish"' in text if form == "transcript" \
        else "Finish the episode" in text


def sa_check_pair(props, cov, t_text, s_text, out):
    """Marker presence of every canonical prop in both forms, same coverage."""
    subset = props if cov == "complete" else \
        [p for p in props if p["role"] not in
         ("write_decision", "write", "verify", "finish")]
    for p in subset:
        for form, text in (("transcript", t_text), ("script", s_text)):
            missing = [m for m in p["markers"] if m not in text]
            if missing:
                out.append({"coverage": cov, "form": form,
                            "step_id": p["step_id"], "role": p["role"],
                            "missing_markers": missing})


def pct(xs, q):
    xs = sorted(xs)
    if len(xs) == 1:
        return float(xs[0])
    pos = (len(xs) - 1) * q / 100.0
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def isolation_scan(cards_dir):
    """FORBIDDEN regexes over the agent-visible TEXT field of every card."""
    hits = []
    for root, _, files in os.walk(cards_dir):
        for fn in sorted(files):
            if not fn.endswith(".json"):
                continue
            p = os.path.join(root, fn)
            with open(p, errors="replace") as f:
                txt = json.load(f)["text"]
            for name, rx in (("CS", FORBIDDEN_RE_CS), ("CI", FORBIDDEN_RE_CI)):
                for m in rx.finditer(txt):
                    hits.append({"file": p, "regex": name, "match": m.group(0)})
    return hits


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--limit", type=int, default=None,
                    help="smoke: first N memories")
    args = ap.parse_args()
    cfg = load_config(args.config)
    os.environ.setdefault("HF_HOME", cfg["paths"]["hf_home"])

    sealed, pub = cfg["paths"]["sealed"], cfg["paths"]["public_view"]
    cards_dir = os.path.join(pub, "cards")
    mems, tasks, fams = load_sealed(sealed)
    meter = TokenMeter(cfg["memories"]["tokenizer"])
    max_tok = cfg["memories"]["tokens_max"]

    cache = {}          # source task_id -> {props, texts{form: arm texts}, sig}
    map_rows, sa_mismatches = [], []
    sa_pairs = {"complete": [0, 0], "prefix": [0, 0]}   # [checked, ok]
    n_done = 0

    for m in mems:
        if m["cell"] not in A_CELLS:
            continue                                    # Q sham skipped
        if args.limit and n_done >= args.limit:
            break
        n_done += 1
        trow, src_key = source_task_row(m, tasks)
        tid = trow["task_id"]
        if tid not in cache:
            with open(os.path.join(pub, "tasks", tid + ".json")) as f:
                task_pub = json.load(f)
            props = build_canonical(trow, fams[trow["family_idx"]],
                                    task_pub["tables"])
            texts = {}
            for form, segs in (
                    ("transcript",
                     transcript_segments(props, task_pub["instruction"])),
                    ("script",
                     script_segments(props, task_pub["instruction"],
                                     trow["terminal"]))):
                texts[form] = build_arm_texts(segs, props, meter)
            cache[tid] = {"props": props, "texts": texts, "sig": trow["signature"]}
        c = cache[tid]
        props = c["props"]

        # (a) SA: transcript vs script at the same coverage
        for cov in ("complete", "prefix"):
            before = len(sa_mismatches)
            sa_check_pair(props, cov, c["texts"]["transcript"][cov],
                          c["texts"]["script"][cov], sa_mismatches)
            sa_pairs[cov][0] += 1
            sa_pairs[cov][1] += 1 if len(sa_mismatches) == before else 0
            for mm in sa_mismatches[before:]:
                mm["memory_id"] = m["memory_id"]

        for arm in ARMS:
            form = "script" if arm.startswith("script") else "transcript"
            if arm.endswith("complete"):
                text, cov, truncated_to = c["texts"][form]["complete"], \
                    "complete", None
            elif arm == "eco":
                ids = meter.tok.encode(c["texts"]["transcript"]["complete"])
                text = meter.tok.decode(ids[:max_tok])
                cov, truncated_to = "prefix", max_tok
            else:
                text, cov = c["texts"][form]["prefix"], "prefix"
                truncated_to = c["texts"][form]["truncated_to"]
            n_tok = meter.count(text)
            wd, fin = has_decision(form, text), has_finish(form, text)
            if arm != "eco":
                # (b) coverage assertions
                if cov == "prefix" and (wd or fin):
                    raise SystemExit("[canonical] %s %s: prefix leaks "
                                     "decision/finish" % (m["memory_id"], arm))
                if cov == "complete" and not (wd and fin):
                    raise SystemExit("[canonical] %s %s: complete lacks "
                                     "decision/finish" % (m["memory_id"], arm))
            row = {"memory_id": m["memory_id"], "cell": m["cell"], "arm": arm,
                   "form": form, "coverage": cov,
                   "source_task_id": tid, "source_key": src_key,
                   "card_family_idx": m["family_idx"],
                   "target_sibling": m["target_sibling"],
                   "token_count": n_tok, "truncated_to": truncated_to,
                   "below_window": n_tok < cfg["memories"]["tokens_min"],
                   "has_write_decision": wd, "has_finish": fin,
                   "n_props": len(props)}
            if arm == "eco":
                row["eco_equals_prefix"] = (
                    text == c["texts"]["transcript"]["prefix"])
            map_rows.append(row)
            d = os.path.join(cards_dir, arm)
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, m["memory_id"] + ".json"), "w") as f:
                json.dump({"memory_id": m["memory_id"], "form": form,
                           "coverage": cov, "text": text,
                           "token_count": n_tok, "source_task_id": tid,
                           "family_idx": m["family_idx"]},
                          f, indent=1, sort_keys=True, ensure_ascii=False)

    # ---- reports -----------------------------------------------------------
    map_path = os.path.join(_HERE, "cards_map.jsonl")
    with open(map_path, "w") as f:
        for r in map_rows:
            f.write(json.dumps(r, sort_keys=True) + "\n")

    sa_report = {"checked_pairs": {k: v[0] for k, v in sa_pairs.items()},
                 "ok_pairs": {k: v[1] for k, v in sa_pairs.items()},
                 "verdict": "PASS" if not sa_mismatches else "FAIL",
                 "mismatches": sa_mismatches}
    with open(os.path.join(_HERE, "canonical_sa_report.json"), "w") as f:
        json.dump(sa_report, f, indent=1)

    stats = {}
    for arm in ARMS:
        toks = [r["token_count"] for r in map_rows if r["arm"] == arm]
        stats[arm] = {
            "n": len(toks), "mean": sum(toks) / max(1, len(toks)),
            "p10": pct(toks, 10), "p90": pct(toks, 90),
            "min": min(toks), "max": max(toks),
            "below_200": sum(1 for t in toks
                             if t < cfg["memories"]["tokens_min"]),
            "over_300": sum(1 for t in toks
                            if t > cfg["memories"]["tokens_max"])}
    eco_rows = [r for r in map_rows if r["arm"] == "eco"]
    stats["eco"]["equals_transcript_prefix"] = sum(
        1 for r in eco_rows if r["eco_equals_prefix"])
    stats["eco"]["has_write_decision"] = sum(
        1 for r in eco_rows if r["has_write_decision"])
    stats["eco"]["has_finish"] = sum(1 for r in eco_rows if r["has_finish"])
    stats["_tokenizer"] = cfg["memories"]["tokenizer"]
    with open(os.path.join(_HERE, "canonical_tokenstats.json"), "w") as f:
        json.dump(stats, f, indent=1, sort_keys=True)

    hits = isolation_scan(cards_dir)

    # (e) 5 sample pairs, distinct archetype signatures where possible
    seen, sample_ids = set(), []
    for tid in sorted(cache):
        if cache[tid]["sig"] in seen:
            continue
        seen.add(cache[tid]["sig"])
        sample_ids.append(tid)
        if len(sample_ids) == 5:
            break
    with open(os.path.join(_HERE, "canonical_samples.md"), "w") as f:
        f.write("# H3 canonical card samples (transcript vs script, "
                "coverage=complete)\n\n")
        for tid in sample_ids:
            c = cache[tid]
            f.write("## source task %s (signature %s)\n\n"
                    "### transcript_complete\n\n```\n%s```\n\n"
                    "### script_complete\n\n```\n%s```\n\n---\n\n"
                    % (tid, c["sig"], c["texts"]["transcript"]["complete"],
                       c["texts"]["script"]["complete"]))

    print("[canonical] memories processed: %d (map rows: %d -> %s)"
          % (n_done, len(map_rows), map_path))
    print("[canonical] SA: complete %d/%d ok, prefix %d/%d ok, verdict=%s"
          % (sa_pairs["complete"][1], sa_pairs["complete"][0],
             sa_pairs["prefix"][1], sa_pairs["prefix"][0],
             sa_report["verdict"]))
    for arm in ARMS:
        s = stats[arm]
        print("[canonical] %-20s n=%3d tok mean=%.0f p10=%.0f p90=%.0f "
              "min=%d max=%d below200=%d over300=%d"
              % (arm, s["n"], s["mean"], s["p10"], s["p90"], s["min"],
                 s["max"], s["below_200"], s["over_300"]))
    print("[canonical] eco == transcript_prefix for %d/%d cards; eco retains "
          "decision=%d finish=%d"
          % (stats["eco"]["equals_transcript_prefix"], stats["eco"]["n"],
             stats["eco"]["has_write_decision"], stats["eco"]["has_finish"]))
    cs = [h for h in hits if h["regex"] == "CS"]
    print("[canonical] isolation scan (card text): %d CS hits, %d CI hits"
          % (len(cs), len(hits) - len(cs)))
    for h in hits[:20]:
        print("  ISOLATION HIT: %s %s %r" % (h["file"], h["regex"], h["match"]))
    if cs:
        raise SystemExit("[canonical] FORBIDDEN_RE_CS violations; do NOT proceed")


if __name__ == "__main__":
    main()
