#!/usr/bin/env python
"""audit_sft2.py — extraction-gate scoring for the SFT2 run (CPU, deterministic).

Blocks scored with the SAME measurement code (audit_expanded read-only):
  sft x test500  (minted SFT2 held-out test families, all 4 archetypes; truth from
                  rebuilt mint instances + the SFT1-frozen minted-truth rule:
                  attribute anchor = the GOLD IR's own attribute tokens)
  base x canon80 (first 80 extractions_v2 keys from the frozen file; sealed-join truth,
                  sanity-checked bit-for-bit against audit_expanded/per_sample.jsonl)
  sft x canon80  (same truth; canonical regression vs base)

Measurement reuse (read-only; nothing outside sft2/ is written):
  audit_expanded.{task_truth, score_row, aggregate_field, load_sealed,
                  candidates_for, consensus, condition_clause...} — adjudicated
  field definitions incl. E1/E2 exceptions, verbatim;
  faithfulness_audit.{lcs, expected_seq} for the op-sequence LCS (canon side);
  mint_core.expected_ops — the mint's own kind-aware signature expansion
  (test side; the very rule the mint used in item_checks).
  mint_all.{plan_families, build_inst, build_nm_variant, partners} — rebuild of the
  200-family instance store so every test row's program_params is recovered exactly
  (family/sibling/cell mapping replicates mint_family's rules).

FROZEN definitions (carried over from SFT1, fixed BEFORE first metrics run):
  parse            = fraction of rows with a validate_ir-passing IR (<=1 repair).
  evidence_verbatim: over VALID IRs, every present-status evidence string must be an
                     exact case-sensitive substring of the text AND <=15 words.
  critical_recall  = pred_all all-rows (audit def; UNMEAS excluded). Per-archetype
                     clause: >=0.85 on every covered archetype (test500 covers 4).
  critical_precision = pred_all present-only.
  false_ABSENT     = max(roles_required.false_absent, termination.false_absent).
  both_side_joint_branch_coverage: fraction of ALL rows whose IR is valid AND has a
                     branch node with non-null predicate AND non-empty then/else
                     effects. Per-archetype clause >=0.70 (per the stage plan).
  lcs              = mean LCS(expected, ir_ops)/len(expected); invalid = 0.
Gates: parse>=0.99, evidence>=0.99, precision>=0.95, recall>=0.90 overall and
>=0.85 per archetype, false_ABSENT<=0.05, coverage>=0.80 overall and >=0.70 per
archetype, lcs>=0.90.  (8 gates; the per-archetype clauses fold into the recall and
coverage gates exactly as specified for this stage.)

Sanity gates (script FAILS rather than publishing unverified numbers):
  1. rebuilt-instance signature must equal the pair row's own signature for every
     test row; instruction rows must reproduce the minted instruction text
     byte-for-byte; every evidence_map span must re-slice exactly (text[start:end]).
  2. gold audit self-check on ALL 500 test rows (audit_selfcheck with the rebuilt
     program_params): every non-True verdict must be a whitelisted measurement
     gap (mint_core.gap_is_whitelisted + the frozen clause-artifact rule).
  3. recomputed base canon80 field verdicts must equal audit_expanded/per_sample.jsonl.

Outputs: sft2/metrics.json, sft2/worst_examples.json.
Run: cd pilot/peval/phi_d/sft2 && PY audit_sft2.py
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
PHI_D = HERE.parent
PILOT = PHI_D.parent.parent
for p in (str(PILOT), str(PHI_D), str(PHI_D / "sft0"), str(PHI_D / "sft1"), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import audit_expanded as A                                       # noqa: E402
import faithfulness_audit as F                                   # noqa: E402
import common as C                                               # noqa: E402
import mint_core as MC                                           # noqa: E402
import mint_all as MA                                            # noqa: E402

EVIDENCE_MAX_WORDS = 15
CANON80 = 80
CRITICAL_FIELDS = ["pred_attribute", "pred_op", "pred_value", "pred_polarity",
                   "branch_effects", "roles_required", "termination"]
GATES = {"parse": 0.99, "evidence_verbatim": 0.99, "critical_precision": 0.95,
         "critical_recall": 0.90, "critical_recall_per_archetype": 0.85,
         "false_ABSENT": 0.05, "both_side_joint_branch_coverage": 0.80,
         "coverage_per_archetype": 0.70, "lcs": 0.90}


# ---------------------------------------------------------------- mint lookup
def build_mint_lookup():
    """pair_id -> (program_params, pair_row) rebuilt via the mint's own rules."""
    fams = MA.plan_families()
    insts = {}
    for fam in fams:
        d = {("sibling", s): MA.build_inst(fam, s, False) for s in range(MA.N_SIB)}
        d[("near_miss", 0)] = MA.build_inst(fam, 0, True)
        insts[fam["idx"]] = d
    a10, a00, _sig = MA.partners(fams, insts)
    lk = {}
    parity_problems = []
    for row in [json.loads(l) for l in open(HERE / "data" / "test.jsonl")]:
        fidx, cell = row["family_idx"], row["cell"]
        s, v = row.get("target_sibling"), row.get("dedupe_variant", 0)
        if row["kind"] == "instruction":
            src = insts[fidx][("near_miss", 0)] if row["program"] == "near_miss" \
                else insts[fidx][("sibling", s)]
        elif cell == "A11":
            src = insts[fidx][("sibling", (s + v) % MA.N_SIB)]
        elif cell == "A01":
            src = MA.build_nm_variant(fams[fidx], v)
        elif cell == "A10":
            src = insts[a10[fidx]][("sibling", (s + v) % MA.N_SIB)]
        else:          # A00
            src = insts[a00[fidx]][("sibling", (s + v) % MA.N_SIB)]
        # gate 1: reconstructed instance must reproduce the row's provenance
        if src["signature"] != row["signature"]:
            parity_problems.append((row["pair_id"], "signature",
                                    src["signature"], row["signature"]))
        if row["kind"] == "instruction" and src["instruction"] != row["text"]:
            parity_problems.append((row["pair_id"], "instruction_text"))
        lk[row["pair_id"]] = (src["program_params"], row)
    if parity_problems:
        json.dump(parity_problems, open(HERE / "sanity_mismatch.json", "w"), indent=1)
        raise SystemExit("SANITY FAIL: %d reconstruction parity problems" % len(parity_problems))
    return lk, len(insts)


def sanity_lookup(mint_lk):
    """Gate 2: span re-slicing + full gold audit self-check on all test rows."""
    problems, gaps, selfcheck_verdicts = [], collections.Counter(), 0
    for pid, (pp, row) in mint_lk.items():
        ev = row.get("evidence_map") or []
        for e in ev:
            if row["text"][e["start"]:e["end"]] != e["span"]:
                problems.append((pid, "evidence_span", e["field"]))
        rec, soft = MC.audit_selfcheck(row["text"], row["gold_ir"], pp, row["archetype"])
        selfcheck_verdicts += 1
        nm = row["program"] == "near_miss"
        for f, v, mode, detail in soft:
            if MC.gap_is_whitelisted(row["schema_key"], row["kind"], nm, f,
                                     (v, mode, detail)):
                gaps["%s|%s" % (row["schema_key"], f)] += 1
                continue
            if (f in ("pred_polarity", "pred_all") and v is False
                    and MA.clause_extraction_artifact(row["text"], row)):
                gaps[row["schema_key"] + "|clause_artifact"] += 1
                continue
            problems.append((pid, "gold_selfcheck", f, v, mode, str(detail)[:120]))
    return problems, gaps, selfcheck_verdicts


# ---------------------------------------------------------------- scoring
def evidence_verbatim(ir, text):
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
    x = v[0]
    return "NA" if x == "NA" else "UNMEAS" if x == "UNMEAS" else x


def score_block(tag, rows, truth_fn, mint_pair=None):
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
            inv_sc = {f: ("UNMEAS", "invalid", None) for f in A.GATE_FIELDS}
            inv_sc["_has_branch"] = False
            ps.update({"evidence_verbatim": False, "evidence_checked": 0, "evidence_bad": 0,
                       "both_side_joint": False, "lcs": 0.0, "scores": inv_sc,
                       "text": r["text"]})
        if mint_pair is not None:
            lhs = r["key"].split(":", 1)[1]
            _pp, pr = mint_pair[lhs]
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
    # per-archetype breakdown (parse / evidence / coverage / lcs / recall)
    per_arch = collections.defaultdict(list)
    for p in per_sample:
        per_arch[p["archetype"]].append(p)
    pa = {}
    for a, rows_a in sorted(per_arch.items()):
        va = [p for p in rows_a if p["valid"]]
        pa[a] = {"n": len(rows_a), "n_valid": len(va),
                 "parse": len(va) / len(rows_a),
                 "evidence_verbatim": (sum(1 for p in va if p["evidence_verbatim"]) / len(va)) if va else None,
                 "coverage": sum(p["both_side_joint"] for p in rows_a) / len(rows_a),
                 "lcs": sum(p["lcs"] for p in rows_a) / len(rows_a),
                 "pred_all": pred["per_archetype"].get(a)}
    blk["per_archetype"] = pa
    gates = {"parse": blk["parse"] >= GATES["parse"],
             "evidence_verbatim": (blk["evidence_verbatim"] or 0) >= GATES["evidence_verbatim"],
             "critical_precision": (blk["critical_precision"] or 0) >= GATES["critical_precision"],
             "critical_recall": (blk["critical_recall"] or 0) >= GATES["critical_recall"],
             "critical_recall_per_archetype": all(
                 (d["all_rows"] or 0) >= GATES["critical_recall_per_archetype"]
                 for d in pred["per_archetype"].values() if d["n_app"]),
             "false_ABSENT": blk["false_ABSENT"] <= GATES["false_ABSENT"],
             "both_side_joint_branch_coverage":
                 blk["both_side_joint_branch_coverage"] >= GATES["both_side_joint_branch_coverage"]
                 and all(v["coverage"] >= GATES["coverage_per_archetype"]
                         for v in pa.values()),
             "lcs": blk["lcs"] >= GATES["lcs"]}
    blk["gates"] = gates
    blk["gates_pass"] = all(gates.values())
    return per_sample, blk


def gold_exact(per_sample):
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

    # ---- minted test500 ----
    print("[audit] rebuilding 200-family mint instance store ...", flush=True)
    mint_lk, n_fams = build_mint_lookup()
    print("[audit] lookup: %d test rows over %d families" % (len(mint_lk), n_fams), flush=True)
    problems, gaps, n_selfcheck = sanity_lookup(mint_lk)
    print("[sanity] gold self-check rows=%d, whitelisted gaps=%s"
          % (n_selfcheck, dict(gaps)), flush=True)
    # signature/text re-derivation parity: every lookup row signature must match
    # the file's own (they came from the same mint); instruction text equality is
    # implicit (instance instruction == minted text by construction in mint_family).
    if problems:
        json.dump(problems, open(HERE / "sanity_mismatch.json", "w"), indent=1)
        raise SystemExit("SANITY FAIL: %d reconstruction/self-check problems" % len(problems))

    def mint_truth(r):
        pid = r["key"].split(":", 1)[1]
        pp, prowl = mint_lk[pid]
        arch = prowl["archetype"]
        # frozen minted-truth rule (== mint_core.audit_selfcheck): task_truth with
        # the attribute anchor taken from the GOLD IR's attribute tokens.
        truth = A.task_truth({"program_params": pp, "signature": None}, arch)
        attr_g = next((n["args"]["predicate"]["attribute"]["value"]
                       for n in prowl["gold_ir"]["nodes"] if n["args"].get("predicate")), None)
        if attr_g:
            truth["pred_attr"] = frozenset(A.toks(attr_g))
        j2_card = (prowl["kind"] == "memory" and arch == "conditional_write"
                   and pp.get("join_depth") == 2)
        expected = MC.expected_ops(prowl["signature"], prowl["kind"], j2_policy_read=j2_card)
        return truth, expected, arch

    rows = [json.loads(l) for l in open(evaldir / "sft_test500.jsonl")]
    ps, blk = score_block("sft_test500", rows, mint_truth, mint_pair=mint_lk)
    samples["sft_test500"] = ps
    blocks["sft_test500"] = blk
    blocks["sft_test500"]["gold_exact"] = gold_exact(ps)

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
        assert truth is not None, "canon join failed for %s" % r["key"]
        return truth, expected, arch

    ps_base, blk_base = score_block("base_canon80", v2, canon_truth)
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

    # ---- canon80 regression vs base (gate metrics; higher better except false_ABSENT) ----
    REG_KEYS = ["parse", "parse_first_pass", "evidence_verbatim", "critical_precision",
                "critical_recall", "false_ABSENT", "both_side_joint_branch_coverage", "lcs"]
    regression = {}
    for k in REG_KEYS:
        b, s = blk_base.get(k), blk_sft.get(k)
        if b is None or s is None:
            regression[k] = {"base": b, "sft": s, "verdict": "NA"}
        else:
            ok = s <= b + 1e-9 if k == "false_ABSENT" else s >= b - 1e-9
            regression[k] = {"base": b, "sft": s, "verdict": "PASS" if ok else "REGRESS"}
    pa_regress = {}
    for a_, d in blk_sft["critical_recall_per_archetype"].items():
        bb = (blk_base["critical_recall_per_archetype"].get(a_) or {})
        if bb.get("n_app"):
            pa_regress[a_] = {"base": bb.get("all_rows"), "sft": d.get("all_rows"),
                              "verdict": "PASS" if (d.get("all_rows") or 0) >= (bb.get("all_rows") or 0) - 1e-9 else "REGRESS"}
    regression["critical_recall_per_archetype"] = pa_regress
    regression["overall"] = all(x.get("verdict") != "REGRESS" for x in
                                list(regression.values())[:len(REG_KEYS)]) and \
        all(x["verdict"] == "PASS" for x in pa_regress.values())
    blocks["canon80_regression"] = regression

    # ---- worst examples: sft, ranked by critical-field failures ----
    worst_pool = []
    for tag in ("sft_test500", "sft_canon80"):
        for p in samples[tag]:
            fails = [] if p["valid"] else ["INVALID"]
            for f in CRITICAL_FIELDS:
                v = p["scores"][f][0]
                if v is False or v is None and v != "NA" and v != "UNMEAS":
                    fails.append("%s:%s" % (f, p["scores"][f][1]))
            worst_pool.append({"subset": tag, "key": p["key"], "n_fail": len(fails),
                               "fails": fails, "archetype": p["archetype"],
                               "pair_id": p.get("pair_id"), "cell": p.get("cell"),
                               "text": p["text"],
                               "ir": p.get("ir"),
                               "gold_ir": p.get("gold_ir")})
    worst_pool.sort(key=lambda w: (-w["n_fail"], w["key"]))
    worst = worst_pool[:10]
    with open(HERE / "worst_examples.json", "w") as f:
        json.dump(worst, f, indent=1, ensure_ascii=False)

    out = {"gates": GATES, "blocks": blocks,
           "sanity": {"test500_gold_selfcheck_rows": n_selfcheck,
                      "whitelisted_gaps": dict(gaps),
                      "canon80_base_verdicts_match": True,
                      "lookup_rows": len(mint_lk), "families": n_fams},
           "notes": {
               "parse": "valid after <=1 repair retry; parse_first_pass alongside",
               "field_aggregates_scope": "valid rows only; invalid rows marked UNMEAS and enter parse/coverage/lcs denominators",
               "both_side_joint_branch_coverage_def": "valid IR with branch node carrying predicate + non-empty then_effects + else_effects; denominator = ALL rows; gate = overall >= 0.80 AND per-archetype >= 0.70 (stage-plan clause)",
               "critical_recall_def": "pred_all all-rows (missing=disagreement, UNMEAS excluded); per-archetype clause >= 0.85",
               "critical_precision_def": "pred_all present-only",
               "false_ABSENT_def": "max(roles_required, termination) audit false-absent rates (row level)",
               "lcs_def": "mean LCS(expected, ir_ops)/len(expected), invalid = 0; minted side uses mint_core.expected_ops (the mint's own kind-aware rule), canon side audit expected_seq",
               "minted_pred_attr_anchor": "gold IR attribute tokens (sealed-field anchor would be a D1 artifact on minted data); canon80 keeps audited sealed-join anchors",
               "regression_def": "per gate metric: sft >= base (higher-better) / sft <= base (false_ABSENT), 1e-9 tolerance",
           },
           "hashes": {p: hashlib.sha256(open(evaldir / (p + ".jsonl"), "rb").read()).hexdigest()[:16]
                      for p in ("sft_test500", "sft_canon80")}}
    with open(HERE / "metrics.json", "w") as f:
        json.dump(A.canon(out), f, indent=1, ensure_ascii=False)
    for tag, blk in blocks.items():
        if tag == "canon80_regression":
            continue
        print("[audit] %s: parse=%.3f ev=%.3f prec=%s rec=%s fa=%.3f cov=%.3f lcs=%.3f gates=%s"
              % (tag, blk["parse"], blk["evidence_verbatim"] or -1,
                 "%.3f" % blk["critical_precision"] if blk["critical_precision"] is not None else "NA",
                 "%.3f" % blk["critical_recall"] if blk["critical_recall"] is not None else "NA",
                 blk["false_ABSENT"], blk["both_side_joint_branch_coverage"], blk["lcs"],
                 "PASS" if blk["gates_pass"] else "FAIL"))
    print("[audit] canon80 regression overall: %s"
          % ("PASS" if regression["overall"] else "FAIL"))
    print("[audit] wrote metrics.json + worst_examples.json")


if __name__ == "__main__":
    main()
