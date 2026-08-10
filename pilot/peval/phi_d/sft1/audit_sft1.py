#!/usr/bin/env python
"""audit_sft1.py — extraction-gate scoring for the SFT pilot (CPU, deterministic).

Scores four condition x subset blocks with the SAME measurement code:
  base x test90, sft x test90   (minted P1 slice; truth from minted instances)
  base x canon80, sft x canon80 (first 80 extractions_v2 keys; sealed-join truth)

Measurement reuse (read-only imports; nothing outside sft1/ is written):
  audit_expanded.{task_truth, score_row, aggregate_field, load_sealed,
                  candidates_for, consensus, condition_clause...} — the adjudicated
  field definitions incl. E1/E2 exceptions, verbatim;
  faithfulness_audit.{lcs, expected_seq} for the op-sequence LCS.

FROZEN pilot definitions (fixed BEFORE first metrics run; no tuning afterwards):
  parse            = fraction of rows with a validate_ir-passing IR (<=1 repair,
                     canonical protocol). First-pass rate reported alongside.
  evidence_verbatim: over VALID IRs, every evidence string with status=="present"
                     at roles/nodes/predicate-fields/termination must be an exact
                     case-sensitive substring of the text AND <=15 words; row ok iff
                     all pass; rate over valid rows.
  critical_recall  = pred_all all-rows agreement (audit def; UNMEAS excluded).
                     Per-archetype clause: >=0.85 on covered archetypes.
  critical_precision = pred_all present-only agreement.
  false_ABSENT     = max(roles_required.false_absent, termination.false_absent)
                     (audit per-field false-ABSENT-on-truth-present rates).
  both_side_joint_branch_coverage: fraction of ALL rows whose IR is valid AND has a
                     node with op=="branch" carrying a non-null predicate AND
                     non-empty then_effects AND non-empty else_effects.
  lcs              = mean LCS(expected, ir_ops)/len(expected); expected from the
                     signature (audit expansion; for minted rows the mint's kind-
                     aware P1 rule via mint_spec.expected_ops); invalid = 0.
Gates: parse>=0.99, evidence>=0.99, precision>=0.95, recall>=0.90 overall and
>=0.85 per covered archetype, false_ABSENT<=0.05, coverage>=0.80, lcs>=0.90.

Sanity gate: recomputed base canon80 field verdicts must equal the audited
audit_expanded/per_sample.jsonl verdicts for those keys (protects the reuse);
on any mismatch this script FAILS rather than publishing unverified numbers.

Outputs: sft1/metrics.json, sft1/worst_examples.json.
Run: cd pilot/peval/phi_d/sft1 && PY audit_sft1.py
"""
import collections
import hashlib
import json
import os
import pathlib
import sys

os.environ.setdefault("HF_HOME", "/work1/zixuan/cache/huggingface")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

HERE = pathlib.Path(__file__).resolve().parent
SFT0 = HERE.parent / "sft0"
PHI_D = HERE.parent
sys.path.insert(0, str(PHI_D))
sys.path.insert(0, str(SFT0))
sys.path.insert(0, str(HERE))

import audit_expanded as A                                       # noqa: E402
import faithfulness_audit as F                                   # noqa: E402
import mint_spec as M                                            # noqa: E402
import mint_p1 as MP                                             # noqa: E402
import common as C                                               # noqa: E402

EVIDENCE_MAX_WORDS = 15
CANON80 = 80
CRITICAL_FIELDS = ["pred_attribute", "pred_op", "pred_value", "pred_polarity",
                   "branch_effects", "roles_required", "termination"]
GATES = {"parse": 0.99, "evidence_verbatim": 0.99, "critical_precision": 0.95,
         "critical_recall": 0.90, "critical_recall_per_archetype": 0.85,
         "false_ABSENT": 0.05, "both_side_joint_branch_coverage": 0.80, "lcs": 0.90}


# ---------------------------------------------------------------- mint joins
def build_mint_lookup():
    """pair_id -> (task_like, pair_row) using the mint's frozen rules (re-derived)."""
    fams = MP.plan_p1_families()
    fam_by_idx = {f["idx"]: f for f in fams}
    insts = {}
    for fam in fams:
        d = {}
        for s in range(MP.N_SIB):
            d[("sibling", s)] = MP.build_inst(fam, s, False)
        d[("near_miss", 0)] = MP.build_inst(fam, 0, True)
        insts[fam["idx"]] = d
    a10, a00, _ = MP.partners(fams, insts)
    lk = {}
    for row in [json.loads(l) for l in open(HERE / "minted_all.jsonl")]:
        fidx, cell = row["family_idx"], row["cell"]
        s, v = row["target_sibling"], row.get("dedupe_variant", 0)
        if row["kind"] == "instruction":
            inst = insts[fidx][("near_miss", 0)] if row["program"] == "near_miss" \
                else insts[fidx][("sibling", s)]
        elif cell == "A11":
            inst = insts[fidx][("sibling", (s + v) % MP.N_SIB)]
        elif cell == "A01":
            inst = insts[fidx][("near_miss", 0)]
        elif cell == "A10":
            inst = insts[a10[fidx]][("sibling", (s + v) % MP.N_SIB)]
        else:
            inst = insts[a00[fidx]][("sibling", (s + v) % MP.N_SIB)]
        lk[row["pair_id"]] = ({"program_params": inst["program_params"],
                               "signature": inst["signature"],
                               "family_idx": fidx}, row, fam_by_idx)
    return lk


# ---------------------------------------------------------------- scoring
def evidence_verbatim(ir, text):
    """(row_ok, n_checked, n_bad); only status=='present' evidences are checked."""
    bad = ok = 0

    def chk(ev):
        nonlocal bad, ok
        if ev is None:
            return
        if ev and ev in text and len(ev.split()) <= EVIDENCE_MAX_WORDS:
            ok += 1
        else:
            bad += 1

    for r in ir["roles"].values():
        if r.get("status") == "present":
            chk(r.get("evidence"))
    for n in ir["nodes"]:
        if n.get("status") == "present":
            chk(n.get("evidence"))
        p = (n.get("args") or {}).get("predicate")
        if p:
            for fw in p.values():
                if (fw or {}).get("status") == "present":
                    chk(fw.get("evidence"))
    t = ir.get("termination") or {}
    if t.get("status") == "present":
        chk(t.get("evidence"))
    return bad == 0 and ok > 0, ok, bad


def both_side_joint(ir):
    for n in ir["nodes"]:
        a = n.get("args") or {}
        if (n.get("op") == "branch" and a.get("predicate")
                and a.get("then_effects") and a.get("else_effects")):
            return True
    return False


def lcs_ratio(ir, expected):
    ops = [n["op"] for n in A.sorted_nodes(ir)]
    return F.lcs(expected, ops) / float(len(expected))


def parse_verdict(v):
    """audit verdict triple -> comparable token for the sanity check."""
    x = v[0]
    return "NA" if x == "NA" else "UNMEAS" if x == "UNMEAS" else x


def score_block(tag, rows, truth_fn, mint_pair=None):
    """rows: eval jsonl rows with ir/key/text/kind. truth_fn(row) -> (truth, expected_ops, arch).
    Returns (per_sample, metrics_block)."""
    per_sample = []
    for r in rows:
        ps = {"key": r["key"], "kind": r["kind"], "valid": r["valid"],
              "attempts": r.get("attempts")}
        truth, expected, arch = truth_fn(r)
        ps["archetype"] = arch
        if r["valid"]:
            ir = r["ir"]
            ev_ok, ev_n, ev_bad = evidence_verbatim(ir, r["text"])
            ps["evidence_verbatim"] = ev_ok
            ps["evidence_checked"], ps["evidence_bad"] = ev_n, ev_bad
            ps["both_side_joint"] = both_side_joint(ir)
            ps["lcs"] = lcs_ratio(ir, expected)
            sc = A.score_row(ir, r["text"], truth, None)
            clause = sc.pop("_clause"); tpol = sc.pop("_truth_polarity"); sc.pop("_polarity_note")
            ps["scores"] = sc
            ps["polarity_clause"], ps["truth_polarity"] = clause, tpol
            ps["text"] = r["text"]
            ps["ir"] = ir
        else:
            # invalid rows: UNMEAS so audit_expanded.aggregate_field excludes them from
            # every field denominator (parse/coverage/lcs below capture invalidity):
            inv_sc = {f: ("UNMEAS", "invalid", None) for f in A.GATE_FIELDS}
            inv_sc["_has_branch"] = False
            ps.update({"evidence_verbatim": False, "evidence_checked": 0, "evidence_bad": 0,
                       "both_side_joint": False, "lcs": 0.0, "scores": inv_sc,
                       "text": r["text"]})
        if mint_pair is not None:
            pr = mint_pair[r["key"].split(":", 1)[1]][1]
            ps["pair_id"] = pr["pair_id"]
            ps["cell"] = pr["cell"]
            ps["program"] = pr["program"]
            ps["gold_ir"] = pr["gold_ir"]
        per_sample.append(ps)

    n = len(per_sample)
    nv = sum(p["valid"] for p in per_sample)
    valid = [p for p in per_sample if p["valid"]]
    ev_n = sum(p["evidence_checked"] for p in valid)
    ev_bad = sum(p["evidence_bad"] for p in valid)
    blk = {"n": n, "n_valid": nv,
           "parse": nv / n,
           "parse_first_pass": sum(1 for p in per_sample if p.get("attempts") == 1 and p["valid"]) / n,
           "evidence_verbatim": (sum(1 for p in valid if p["evidence_verbatim"]) / len(valid)) if valid else None,
           "evidence_span_level": {"n": ev_n, "bad": ev_bad,
                                   "rate": (ev_n - ev_bad) / ev_n if ev_n else None},
           "both_side_joint_branch_coverage": sum(p["both_side_joint"] for p in per_sample) / n,
           "lcs": sum(p["lcs"] for p in per_sample) / n,
           "fields": {}}
    for field in A.GATE_FIELDS + ["branch_presence"]:
        blk["fields"][field] = A.aggregate_field(per_sample, field)
    pred = blk["fields"]["pred_all"]
    blk["critical_recall"] = pred["all_rows"]
    blk["critical_precision"] = pred["present_only"]
    blk["critical_recall_per_archetype"] = pred["per_archetype"]
    blk["false_ABSENT"] = max(blk["fields"]["roles_required"]["false_absent"] or 0.0,
                              blk["fields"]["termination"]["false_absent"] or 0.0)
    gates = {"parse": blk["parse"] >= GATES["parse"],
             "evidence_verbatim": (blk["evidence_verbatim"] or 0) >= GATES["evidence_verbatim"],
             "critical_precision": (blk["critical_precision"] or 0) >= GATES["critical_precision"],
             "critical_recall": (blk["critical_recall"] or 0) >= GATES["critical_recall"],
             "critical_recall_per_archetype": all(
                 (d["all_rows"] or 0) >= GATES["critical_recall_per_archetype"]
                 for d in pred["per_archetype"].values() if d["n_app"]),
             "false_ABSENT": blk["false_ABSENT"] <= GATES["false_ABSENT"],
             "both_side_joint_branch_coverage":
                 blk["both_side_joint_branch_coverage"] >= GATES["both_side_joint_branch_coverage"],
             "lcs": blk["lcs"] >= GATES["lcs"]}
    blk["gates"] = gates
    blk["gates_pass"] = all(gates.values())
    return per_sample, blk


def gold_exact(per_sample):
    """Supplemental, minted only: exact-string fidelity vs the minted gold IR."""
    n = 0
    agg = collections.Counter()
    slots = collections.Counter()
    for p in per_sample:
        if not p["valid"] or "gold_ir" not in p:
            continue
        n += 1
        g, ir = p["gold_ir"], p["ir"]
        agg["full_ir_exact"] += (json.dumps(g, sort_keys=True) == json.dumps(ir, sort_keys=True))
        for rname in C.CANONICAL_ROLES:
            slots[(rname, g["roles"][rname]["status"], ir["roles"][rname]["status"])] += 1
        pred_g = next((n2["args"].get("predicate") for n2 in g["nodes"] if n2["args"].get("predicate")), {})
        pred_i = next((n2["args"].get("predicate") for n2 in ir["nodes"] if n2["args"].get("predicate")), {})
        for f in ("attribute", "op", "value", "polarity"):
            agg["exact_%s" % f] += ((pred_i.get(f) or {}).get("value") == (pred_g.get(f) or {}).get("value"))
        for side in ("then_effects", "else_effects"):
            gs = sorted(json.dumps(e, sort_keys=True) for e in
                        next((n2["args"].get(side) or [] for n2 in g["nodes"] if n2["args"].get("predicate")), []))
            is_ = sorted(json.dumps(e, sort_keys=True) for e in
                         next((n2["args"].get(side) or [] for n2 in ir["nodes"] if n2["args"].get("predicate")), []))
            agg["exact_%s" % side] += gs == is_
    return {"n": n, "rates": {k: v / n for k, v in agg.items()} if n else {},
            "role_status_confusion": {"%s gold=%s ir=%s" % k: v for k, v in sorted(slots.items())}}


# ---------------------------------------------------------------- canon joins
def canon_truth_join(sealed, r):
    fams, sib, nm, mems, instr_idx = sealed
    if r["kind"] == "instruction":
        cand = [(t, None, "instruction") for t in instr_idx.get(r["text"], [])]
    else:
        cand = A.candidates_for(r, mems, sib, nm)
    if not cand:
        return None, None, None
    truth, _ = A.consensus(cand, fams)
    if truth is None:
        return None, None, None
    return truth, F.expected_seq(truth["signature"]), truth["archetype"]


def main():
    evaldir = HERE / "eval"
    blocks, samples = {}, {}

    # ---- minted test90 ----
    mint_lk = build_mint_lookup()

    def mint_truth(r):
        pid = r["key"].split(":", 1)[1]
        task_like, prowl, _ = mint_lk[pid]
        truth = A.task_truth(task_like, "conditional_write")
        # Minted-slice truth anchor (frozen rule): the attribute truth is the GOLD IR's
        # attribute tokens. The audit's sealed-field anchor (cond_field, e.g. "qty")
        # contradicts the text's surface concept ("on-hand quantity") by construction on
        # minted data — the D1 sealed-field-name artifact; on this slice the gold IR IS
        # truth. Applied identically to base and SFT. canon80 keeps the audited
        # sealed-join anchor verbatim for comparability with the audited corpus numbers.
        attr_g = next((n["args"]["predicate"]["attribute"]["value"]
                       for n in prowl["gold_ir"]["nodes"] if n["args"].get("predicate")), None)
        if attr_g:
            truth["pred_attr"] = frozenset(A.toks(attr_g))
        j2_pol = task_like["program_params"].get("join_depth", 1) == 2 and prowl["kind"] == "memory"
        expected = M.expected_ops(task_like["signature"], prowl["kind"], j2_policy_read=j2_pol)
        return truth, expected, "conditional_write"

    for cond in ("base", "sft"):
        rows = [json.loads(l) for l in open(evaldir / ("%s_test90.jsonl" % cond))]
        ps, blk = score_block("%s_test90" % cond, rows, mint_truth, mint_pair=mint_lk)
        samples["%s_test90" % cond] = ps
        blocks["%s_test90" % cond] = blk
        blocks["%s_test90" % cond]["gold_exact"] = gold_exact(ps)

    # ---- canon80 (base from extractions_v2 + audited score parity check) ----
    fams, sib, nm, mems = A.load_sealed()
    instr_idx = collections.defaultdict(list)
    for (fi, si), t in sib.items():
        instr_idx[t["instruction"]].append(t)
    sealed = (fams, sib, nm, mems, instr_idx)
    v2 = [json.loads(l) for l in open(PHI_D / "out" / "extractions_v2.jsonl")][:CANON80]
    audited = {}
    for l in open(PHI_D / "audit_expanded" / "per_sample.jsonl"):
        row = json.loads(l)
        if row["kind"] in ("instruction", "memory"):
            audited[row["key"]] = row

    def canon_truth(r):
        truth, expected, arch = canon_truth_join(sealed, r)
        A_ = truth
        assert truth is not None, "canon join failed for %s" % r["key"]
        return truth, expected, arch

    ps_base, blk_base = score_block("base_canon80", v2, canon_truth)
    # sanity: verdicts must match the audited per_sample.jsonl
    mismatches = []
    for p in ps_base:
        if p["key"] not in audited or "scores" not in audited[p["key"]]:
            mismatches.append((p["key"], "missing_in_audited"))
            continue
        for f in A.GATE_FIELDS:
            a = parse_verdict(audited[p["key"]]["scores"][f])
            b = parse_verdict(p["scores"][f])
            if a != b:
                mismatches.append((p["key"], f, a, b))
    if mismatches:
        json.dump(mismatches, open(HERE / "sanity_mismatch.json", "w"), indent=1)
        raise SystemExit("SANITY FAIL: %d verdict mismatches vs audit_expanded/per_sample.jsonl"
                         % len(mismatches))
    print("[sanity] base canon80 verdicts == audited per_sample.jsonl (%d rows)" % len(ps_base))

    rows_sft = [json.loads(l) for l in open(evaldir / "sft_canon80.jsonl")]
    ps_sft, blk_sft = score_block("sft_canon80", rows_sft, canon_truth)
    samples["base_canon80"], samples["sft_canon80"] = ps_base, ps_sft
    blocks["base_canon80"], blocks["sft_canon80"] = blk_base, blk_sft

    # ---- worst examples: sft, ranked by critical-field failures ----
    worst_pool = []
    for tag in ("sft_test90", "sft_canon80"):
        for p in samples[tag]:
            fails = [] if p["valid"] else ["INVALID"]
            for f in CRITICAL_FIELDS:
                v = p["scores"][f][0]
                if v is False or v is None and v != "NA" and v != "UNMEAS":
                    fails.append("%s:%s" % (f, p["scores"][f][1]))
            worst_pool.append({"subset": tag, "key": p["key"], "n_fail": len(fails),
                               "fails": fails,
                               "pair_id": p.get("pair_id"), "cell": p.get("cell"),
                               "text": p["text"],
                               "ir": p.get("ir"),
                               "gold_ir": p.get("gold_ir")})
    worst_pool.sort(key=lambda w: (-w["n_fail"], w["key"]))
    worst = worst_pool[:5]
    with open(HERE / "worst_examples.json", "w") as f:
        json.dump(worst, f, indent=1, ensure_ascii=False)

    out = {"gates": GATES, "blocks": blocks,
           "notes": {
               "parse": "valid after <=1 repair retry; parse_first_pass alongside",
               "field_aggregates_scope": "valid rows only; invalid rows marked UNMEAS (so they inflate n_unmeas, excluded from denominators) and enter parse/coverage/lcs denominators",
               "both_side_joint_branch_coverage_def": "valid IR with branch node carrying predicate + non-empty then_effects + else_effects; denominator = ALL rows",
               "critical_recall_def": "pred_all all-rows (missing=disagreement, UNMEAS excluded)",
               "critical_precision_def": "pred_all present-only",
               "false_ABSENT_def": "max(roles_required, termination) audit false-absent rates (row level)",
               "lcs_def": "mean LCS(expected, ir_ops)/len(expected), invalid = 0",
               "minted_pred_attr_anchor": "gold IR attribute tokens (sealed-field anchor would be a D1 artifact on minted data); canon80 keeps audited sealed-join anchors",
           },
           "hashes": {p: hashlib.sha256(open(evaldir / (p + ".jsonl"), "rb").read()).hexdigest()[:16]
                      for p in ("base_test90", "sft_test90", "sft_canon80")}}
    with open(HERE / "metrics.json", "w") as f:
        json.dump(A.canon(out), f, indent=1, ensure_ascii=False)
    for tag, blk in blocks.items():
        print("[audit] %s: parse=%.3f ev=%.3f prec=%s rec=%s fa=%.3f cov=%.3f lcs=%.3f gates=%s"
              % (tag, blk["parse"], blk["evidence_verbatim"] or -1,
                 "%.3f" % blk["critical_precision"] if blk["critical_precision"] is not None else "NA",
                 "%.3f" % blk["critical_recall"] if blk["critical_recall"] is not None else "NA",
                 blk["false_ABSENT"], blk["both_side_joint_branch_coverage"], blk["lcs"],
                 "PASS" if blk["gates_pass"] else "FAIL"))
    print("[audit] wrote metrics.json + worst_examples.json")


if __name__ == "__main__":
    main()
