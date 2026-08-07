"""H3 stage B: pre-grid acceptance (GATE_PROTOCOL.md Part III sec.15).

Runs the five sec.15 gates (+ the sec.14.6/15.5 blind-feature gate) as ONE
command and writes pilot/h3/acceptance.json.  Exits non-zero if any MANDATORY
item fails; the token-balance item (sec.15.4) is documentation-only per
CONSTRUCTION_RULINGS.md R2/R3 (SMD>0.2 across arms expected and accepted,
covariate-robustness analysis planned at analyze time).

Gates:
  1. oracle            sealed oracle_report.json ok==checked==640 AND
                       re-execution of every distinct canonical source task
                       (64) via canonical.execute_task -> all ok
  2. n_condition_band  pilot/h3/n_condition_stats.json in_band == true
  3. canonical_align   canonical_sa_report.json verdict == PASS AND, from
                       cards_map.jsonl: complete arms 512/512 have
                       write-decision+finish; prefix arms 512/512 lack both
  4. isolation         FORBIDDEN_RE_CS/CI scan over every public card text
                       -> 0 hits
  5. token_balance     per-arm token SMD table (Qwen2.5-1.5B counts);
                       DOCUMENTATION ONLY (never fails)
  6. blind_features    blind_separation.json sec15_5_pass == true

Run: python pilot/h3/acceptance.py ; exit code 0 = PASS
"""

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PILOT = os.path.dirname(_HERE)
sys.path.insert(0, _PILOT)
sys.path.insert(0, _HERE)

from generate_families import FORBIDDEN_RE_CI, FORBIDDEN_RE_CS  # noqa: E402
import canonical  # noqa: E402

SEALED = "/work1/zixuan/data/agent_memory/h3/sealed"
CARDS_DIR = "/work1/zixuan/data/agent_memory/h3/public_view/cards"
PUB = "/work1/zixuan/data/agent_memory/h3/public_view"


def gate_oracle():
    with open(os.path.join(SEALED, "oracle_report.json")) as f:
        rep = json.load(f)
    gen_ok = (rep.get("checked") == 640 and rep.get("ok") == 640
              and not rep.get("failures"))
    mems, tasks, fams = canonical.load_sealed(SEALED)
    srcs, seen = [], set()
    for m in mems:
        if m["cell"] == "Q":
            continue
        trow, _ = canonical.source_task_row(m, tasks)
        if trow["task_id"] in seen:
            continue
        seen.add(trow["task_id"])
        srcs.append(trow)
    n_ok, errors = 0, []
    for trow in srcs:
        try:
            with open(os.path.join(PUB, "tasks", trow["task_id"] + ".json")) as f:
                tables = json.load(f)["tables"]
            canonical.execute_task(trow, fams[trow["family_idx"]], tables)
            n_ok += 1
        except Exception as e:
            errors.append("%s: %r" % (trow["task_id"], e))
    ok = gen_ok and n_ok == len(srcs) and not errors
    return ok, {"sealed_oracle": {"checked": rep.get("checked"),
                                  "ok": rep.get("ok"),
                                  "failures": rep.get("failures")},
                "canonical_source_reexecution": {"sources": len(srcs),
                                                 "ok": n_ok,
                                                 "errors": errors[:10]}}


def gate_n_band():
    with open(os.path.join(_HERE, "n_condition_stats.json")) as f:
        s = json.load(f)
    rate = s.get("n_success_rate")
    ok = bool(s.get("in_band")) and rate is not None and 0.3 <= rate <= 0.7
    return ok, {"n_success_rate": rate, "band": s.get("band"),
                "parseable_action_rate": s.get("parseable_action_rate")}


def gate_canonical():
    with open(os.path.join(_HERE, "canonical_sa_report.json")) as f:
        sa = json.load(f)
    with open(os.path.join(_HERE, "cards_map.jsonl")) as f:
        rows = [json.loads(l) for l in f]
    detail = {"sa_verdict": sa.get("verdict")}
    ok = sa.get("verdict") == "PASS"
    for arm, want in (("transcript_complete", True), ("script_complete", True),
                      ("transcript_prefix", False), ("script_prefix", False)):
        sub = [r for r in rows if r["arm"] == arm]
        wd = sum(1 for r in sub if r["has_write_decision"] == want)
        fin = sum(1 for r in sub if r["has_finish"] == want)
        detail[arm] = {"n": len(sub),
                       "write_decision_%s" % ("present" if want else "absent"):
                       "%d/512" % wd,
                       "finish_%s" % ("present" if want else "absent"):
                       "%d/512" % fin}
        ok = ok and len(sub) == 512 and wd == 512 and fin == 512
    return ok, detail


def gate_isolation():
    hits = []
    for root, _, files in os.walk(CARDS_DIR):
        for fn in sorted(files):
            if not fn.endswith(".json"):
                continue
            p = os.path.join(root, fn)
            with open(p, errors="replace") as f:
                txt = json.load(f)["text"]
            for name, rx in (("CS", FORBIDDEN_RE_CS), ("CI", FORBIDDEN_RE_CI)):
                for m in rx.finditer(txt):
                    hits.append({"file": p, "regex": name,
                                 "match": m.group(0)})
    cs = [h for h in hits if h["regex"] == "CS"]
    return not hits, {"n_cards_scanned": sum(
        1 for _, _, fs in os.walk(CARDS_DIR) for f in fs if f.endswith(".json")),
        "cs_hits": len(cs), "ci_hits": len(hits) - len(cs),
        "examples": hits[:10]}


def gate_token_balance():
    with open(os.path.join(_HERE, "cards_map.jsonl")) as f:
        rows = [json.loads(l) for l in f]
    arms = ["transcript_complete", "transcript_prefix",
            "script_complete", "script_prefix", "eco"]
    tok = {a: [r["token_count"] for r in rows if r["arm"] == a] for a in arms}

    def smd(x, y):
        mx, my = sum(x) / len(x), sum(y) / len(y)

        def var(v, m):
            return sum((t - m) ** 2 for t in v) / max(1, len(v) - 1)
        sp = ((var(x, mx) + var(y, my)) / 2) ** 0.5
        return (mx - my) / sp if sp else 0.0

    pairs = []
    for i in range(len(arms)):
        for j in range(i + 1, len(arms)):
            pairs.append({"arms": [arms[i], arms[j]],
                          "smd": round(smd(tok[arms[i]], tok[arms[j]]), 3)})
    return True, {"pairwise_smd": pairs,
                  "ruling": ("sec.15.4 SMD<0.2 NOT enforceable in this design; "
                             "accepted + covariate-robustness plan per "
                             "CONSTRUCTION_RULINGS.md R2/R3 (documentation "
                             "only, never a fail)")}


def gate_blind():
    with open(os.path.join(_HERE, "blind_separation.json")) as f:
        s = json.load(f)
    return bool(s.get("sec15_5_pass")), s


def main():
    mandatory, gates = True, {}
    for name, fn in (("1_oracle", gate_oracle),
                     ("2_n_condition_band", gate_n_band),
                     ("3_canonical_align", gate_canonical),
                     ("4_isolation", gate_isolation),
                     ("6_blind_features", gate_blind)):
        ok, detail = fn()
        gates[name] = {"pass": bool(ok), "detail": detail}
        mandatory = mandatory and bool(ok)
    ok5, det5 = gate_token_balance()
    gates["5_token_balance"] = {"pass": "documentation_only", "detail": det5}
    out = {"mandatory_pass": mandatory, "gates": gates}
    with open(os.path.join(_HERE, "acceptance.json"), "w") as f:
        json.dump(out, f, indent=1)

    print("%-22s %-18s" % ("gate", "verdict"))
    print("-" * 42)
    for name in ("1_oracle", "2_n_condition_band", "3_canonical_align",
                 "4_isolation", "5_token_balance", "6_blind_features"):
        g = gates[name]
        v = g["pass"] if isinstance(g["pass"], bool) else g["pass"]
        print("%-22s %-18s" % (name, "PASS" if v is True else
                               ("DOC" if v == "documentation_only" else "FAIL")))
    for p in det5["pairwise_smd"]:
        print("  SMD %-38s %6.2f" % (p["arms"][0] + " vs " + p["arms"][1],
                                     p["smd"]))
    print("[acceptance] mandatory gates: %s -> pilot/h3/acceptance.json"
          % ("ALL PASS" if mandatory else "FAIL"))
    sys.exit(0 if mandatory else 1)


if __name__ == "__main__":
    main()
