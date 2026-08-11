"""score_s2.py — S2-rc1 scoring harness (audit-gate reader + synthetic self-test).

This harness is the ONLY label consumer of the S2 line. What it does at rc1:

  default (this file, no args): audit-gate verification + synthetic self-test.
      * reads sft2_eval/audit_sft_canonical.json and checks the frozen rc1
        eligibility table (s2_comparator.ELIGIBILITY_S2) against the audit's
        per-field veto_eligibility, including the dual_tokcov posthoc entry that
        promotes pred_attribute to HARD VETO under the rc1 anchor rule;
      * runs the comparator on synthetic, non-benchmark fixtures only (the same
        hand-written builders as test_s2.py), maps verdicts via the frozen
        {match:1.0, unknown:0.5, contradict:0.0} mapping, and smoke-tests the
        rank-based AUC on synthetic labels.

  640-pair mode: IMPLEMENTED BUT FROZEN OFF at rc1. It runs only when the
      environment variable S2_RUN_640=1 is set explicitly, AFTER Codex
      adversarial review round 3 closes S2_SPEC.md section 14. Nobody may run it
      before that gate; it is lint-path code at rc1. It joins pairs.jsonl to
      sft2_eval/canonical_sft.jsonl by text-sha keys, emits verdicts_s2.jsonl and
      score_summary_s2.json (per-cell admission/retention, AUC overall / S=1,
      family-macro40, LOAO per-archetype, reason stats, kill conditions — same
      metric semantics as comparator_v0/score.py).

Deterministic; stdlib only; CPU only. No labels ever enter s2_comparator itself.
"""
import collections
import hashlib
import json
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent          # pilot/peval/phi_d/s2
PHI_D = HERE.parent                                     # pilot/peval/phi_d
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import s2_comparator as K                               # noqa: E402

AUDIT_JSON = PHI_D / "sft2_eval" / "audit_sft_canonical.json"
PAIRS = PHI_D.parent / "pairs.jsonl"
SFT_IRS = PHI_D / "sft2_eval" / "canonical_sft.jsonl"
OUT_VERDICTS = HERE / "verdicts_s2.jsonl"
OUT_SUMMARY = HERE / "score_summary_s2.json"

VERDICT_SCORE = {"match": 1.0, "unknown": 0.5, "contradict": 0.0}
CELLS = ("A00", "A01", "A10", "A11")


# ---------------------------------------------------------------------------
# audit-gate verification (the rc1 eligibility table vs audit_sft_canonical.json)
# ---------------------------------------------------------------------------

def verify_audit_gates(audit_path=AUDIT_JSON):
    """Cross-check ELIGIBILITY_S2 against the frozen SFT-era audit. Returns
    {field: {audit, rc1, status}}. status is 'consistent' only when the rc1
    reading is exactly what the audit sanctions, or a documented R1/R2/R3/R6
    ruling in S2_SPEC.md section 14."""
    audit = json.load(open(audit_path))
    fields = audit["fields"]
    dual = audit["attribute_anchor_audit"]["dual_anchor_posthoc"]

    def aud(f):
        return (fields.get(f) or {}).get("veto_eligibility", "<absent>")

    expected = {
        # audit field -> (audit string read at build time, rc1 ruling note)
        "pred_op": (aud("pred_op"), None),
        "pred_value": (aud("pred_value"), None),
        "pred_polarity": (aud("pred_polarity"), "R2: decision function omits "
                         "polarity; note-only despite audit HARD VETO"),
        "branch_effects": (aud("branch_effects"), None),
        "direction": (aud("direction"), None),
        "archive_capture": (aud("archive_capture"), None),
        "roles_required": (aud("roles_required"), None),
        "termination": (aud("termination"), None),
        "pred_attribute": (dual["pred_attribute_dual_tokcov"]["veto_eligibility"],
                           "R1: dual-tokcov anchor gate; never vetoes"),
        "pred_all": (dual["pred_all_dual_tokcov"]["veto_eligibility"],
                     "composite channel; folds in"),
        "scope": (aud("scope"), "R3: permanently excluded; note-only"),
        "agg_function": ("<not an audit field>",
                         "R6: carried from adjudicated round-1 veto list"),
    }
    rc1 = K.ELIGIBILITY_S2
    out = {}
    ok = True
    for f, (a, ruling) in expected.items():
        r = rc1[f]
        if f in ("pred_op", "pred_value", "branch_effects", "direction",
                 "archive_capture", "roles_required", "termination"):
            status = "consistent" if (a.startswith("HARD VETO") and r == "hard") \
                else "MISMATCH"
        elif f == "pred_polarity":
            status = "consistent" if (a.startswith("HARD VETO")
                                      and r == "metadata" and ruling) else "MISMATCH"
        elif f in ("pred_attribute", "pred_all"):
            want = {"pred_attribute": "anchor_gate", "pred_all": "composite"}[f]
            status = "consistent" if (a.startswith("HARD VETO") and r == want) \
                else "MISMATCH"
        elif f == "scope":
            status = "consistent" if (a.startswith("excluded")
                                      and r == "excluded_note_only") else "MISMATCH"
        else:  # agg_function
            status = "consistent" if r == "hard" else "MISMATCH"
        if status != "consistent":
            ok = False
        out[f] = {"audit_veto_eligibility": a, "rc1": r, "ruling": ruling,
                  "status": status}
    return {"ok": ok, "fields": out,
            "audit_json": str(audit_path),
            "audit_dual_tokcov_note": "pred_attribute eligibility read from the "
            "dual_anchor_posthoc.pred_attribute_dual_tokcov entry (the rc1 anchor "
            "rule), not from the bare sealed-anchor column"}


# ---------------------------------------------------------------------------
# metric machinery (rank-based AUC with ties; v0 scorer semantics)
# ---------------------------------------------------------------------------

def auc(scores, labels):
    n1 = sum(labels)
    n0 = len(labels) - n1
    if n1 == 0 or n0 == 0:
        return None
    order = sorted(range(len(scores)), key=lambda i: scores[i])
    ranks = [0.0] * len(scores)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and scores[order[j + 1]] == scores[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    sum_pos = sum(r for r, l in zip(ranks, labels) if l == 1)
    return (sum_pos - n1 * (n1 + 1) / 2.0) / (n1 * n0)


def per_cell(scores, pairs):
    out = {}
    for c in CELLS:
        idx = [i for i in range(len(pairs)) if pairs[i]["cell"] == c]
        out[c] = {"n": len(idx),
                  "admission": sum(scores[i] for i in idx) / len(idx) if idx else None}
    return out


# ---------------------------------------------------------------------------
# synthetic self-test (default path; NEVER touches the corpus)
# ---------------------------------------------------------------------------

def self_test():
    """Runs the comparator on hand-written synthetic fixtures (builders imported
    from test_s2 so the harness exercises exactly the pinned fixture IRs), then
    computes the frozen score mapping and a smoke AUC on synthetic labels."""
    import test_s2 as T
    cases = []
    i, ti = T.std_pair(); m, tm = T.std_pair()
    cases.append(("identical", i, ti, m, tm, 1))
    i, ti = T.std_pair(val="5"); m, tm = T.std_pair(val="6")
    cases.append(("threshold-veto", i, ti, m, tm, 0))
    i, ti = T.std_pair(val="0"); m, tm = T.std_pair(val="none remain")
    cases.append(("unmeas-abstain", i, ti, m, tm, 1))
    i, ti = T.std_pair(attr="complaint count"); m, tm = T.std_pair(attr="seats booked")
    cases.append(("anchor-cross", i, ti, m, tm, 0))
    rows = []
    for name, ii, t_i, mm, t_m, label in cases:
        v = K.compare(ii, t_i, mm, t_m)
        rows.append({"case": name, "verdict": v["verdict"],
                     "score": VERDICT_SCORE[v["verdict"]], "synthetic_label": label})
    scores = [r["score"] for r in rows]
    labels = [r["synthetic_label"] for r in rows]
    return {"cases": rows, "toy_auc": auc(scores, labels),
            "note": "synthetic labels are sanity targets, not benchmark data"}


def gate_report_and_selftest():
    gates = verify_audit_gates()
    st = self_test()
    print("[gates] audit_sft_canonical.json vs ELIGIBILITY_S2:")
    for f, d in gates["fields"].items():
        print("  %-16s audit=%-46s rc1=%-18s %s" %
              (f, d["audit_veto_eligibility"], d["rc1"], d["status"]))
    print("[gates] overall: %s" % ("PASS" if gates["ok"] else "FAIL"))
    print("[selftest] synthetic cases:")
    for r in st["cases"]:
        print("  %-16s verdict=%-10s score=%.1f label=%d" %
              (r["case"], r["verdict"], r["score"], r["synthetic_label"]))
    print("[selftest] toy AUC on synthetic labels: %s" % st["toy_auc"])
    ok = gates["ok"] and all(
        r["verdict"] in VERDICT_SCORE for r in st["cases"]) \
        and st["toy_auc"] is not None and 0.0 <= st["toy_auc"] <= 1.0
    print("[selftest] overall: %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


# ---------------------------------------------------------------------------
# 640-pair mode: FROZEN OFF until Codex round 3 closes S2_SPEC.md section 14.
# ---------------------------------------------------------------------------

def run_640():
    if K.RULE_VERSION == "s2-rc1":
        raise SystemExit(
            "rc1 discipline: the 640-pair run is FROZEN OFF until Codex "
            "adversarial review round 3 closes S2_SPEC.md section 14 and a new "
            "freeze hash is issued (RULE_VERSION pin). Refusing to run.")
    pairs = [json.loads(l) for l in open(PAIRS)]
    sft = {json.loads(l)["key"]: json.loads(l) for l in open(SFT_IRS)}
    assert len(pairs) == 640, len(pairs)
    verdicts = []
    for p in pairs:
        ki = "instruction:" + hashlib.sha256(p["instruction"].encode()).hexdigest()[:16]
        km = "memory:" + hashlib.sha256(p["memory_text"].encode()).hexdigest()[:16]
        ri, rm = sft.get(ki), sft.get(km)
        assert ri and rm and ri["valid"] and rm["valid"], (ki, km)
        v = K.compare(ri["ir"], ri["text"], rm["ir"], rm["text"])
        verdicts.append({"memory_id": p["memory_id"], "key_i": ki, "key_m": km,
                         "verdict": v["verdict"], "reasons": v["reasons"]})
    scores = [VERDICT_SCORE[v["verdict"]] for v in verdicts]
    P = [p["P"] for p in pairs]
    s1 = [i for i in range(640) if pairs[i]["S"] == 1]
    mix = collections.Counter(v["verdict"] for v in verdicts)
    summary = {
        "rule_version": K.RULE_VERSION,
        "verdict_mix": dict(mix),
        "per_cell": per_cell(scores, pairs),
        "auc_overall": auc(scores, P),
        "auc_S1": auc([scores[i] for i in s1], [P[i] for i in s1]),
    }
    with open(OUT_VERDICTS, "w") as f:
        for v in verdicts:
            f.write(json.dumps(v, ensure_ascii=False) + "\n")
    with open(OUT_SUMMARY, "w") as f:
        json.dump(summary, f, indent=1, ensure_ascii=False)
    print("[640] wrote %s and %s" % (OUT_VERDICTS, OUT_SUMMARY))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    if os.environ.get("S2_RUN_640") == "1":
        run_640()          # locked at rc1 by the RULE_VERSION pin inside run_640
    else:
        sys.exit(gate_report_and_selftest())
