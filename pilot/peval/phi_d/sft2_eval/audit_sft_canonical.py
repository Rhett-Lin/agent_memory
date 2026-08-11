#!/usr/bin/env python
"""audit_sft_canonical.py — S2-prep stage 2 (CPU-only, deterministic, stdlib-only):
expanded faithfulness audit of the SFT2-adapter IRs on the FULL canonical 532-text
corpus, against SEALED truth, under the SAME frozen measurement rules and gates as
audit_expanded.py (which audited the base extractor on the same rows).

Reuse is verbatim and read-only (audit_expanded imported as A; nothing outside
sft2_eval/ is written):
  - joins: instruction text -> sealed sibling tasks (same text); memory text ->
    sealed memories (sham excluded); consensus / PARTIAL-CONSENSUS UNMEAS rule.
  - scoring: A.score_row per field incl. the pre-registered E1 (polarity
    clause-artifact) and E2 (value-as-stated) exceptions — untouched.
  - aggregation: A.aggregate_field (all-rows with missing=disagreement; UNMEAS/NA
    excluded from denominators; present_only; per-archetype; false_absent) with the
    FROZEN gate: overall >= 0.90 AND worst per-archetype >= 0.80 AND
    false-ABSENT <= 0.05, plus the frozen veto-eligibility rule
    (PASS -> HARD VETO; FAIL & present_only >= 0.90 -> positive-only;
    else excluded).
  - evidence_verbatim / both_side_joint helpers are verbatim copies of the frozen
    definitions in sft2/audit_sft2.py (lines noted there as FROZEN).

Sanity gates (script raises instead of publishing unchecked numbers):
  S1 join parity: join distribution (n_joined, no_join, arch_conflict, per-dimension
     conflict counts) must equal the frozen base audit's join stats
     (audit_expanded/field_metrics.json) — truth is a function of (text, sealed) only.
  S2 base-score parity: re-scoring the frozen base IRs (out/extractions_v2.jsonl)
     through this same code path must reproduce audit_expanded/per_sample.jsonl
     verdicts for all 532 keys x 11 gate fields (extends the adjudicated canon80
     sanity gate of sft2/audit_sft2.py from 80 to 532 rows).

Attribute-anchor audit (the canon issue flagged in SFT2_GATE_REPORT §canon):
  quantifies the sealed-field-anchor vs minted-D1-surface contradiction: per-field
  and per-archetype pred_attribute disagreement counts, the share whose IR attribute
  is nevertheless verbatim in the text (posthoc D1 diagnostic, audit_expanded's own
  definition), concrete examples, and a POSTHOC (non-gate, clearly labelled)
  dual-anchor rescore: pred_attribute_dual = sealed-anchor agreement OR
  IR-attribute-verbatim-in-text; refolded into pred_all_dual. This is a diagnostic
  quantification of the convention artifact for the S2 measurement-rule decision —
  it does NOT touch the frozen gate table.

Pair-level coverage (report fuel): over all 640 pairs.jsonl rows (archetype column
used for stratification only; labels never influenced extraction), per pair:
instruction/IR lookup via the same sha keys as the extraction worklist; both-sides
valid, per-side branch presence, per-side both-side-JOINT (branch node carrying
predicate + non-empty then/else effects), and pair-JOINT (both sides valid AND both
sides both-side-JOINT). Aggregated overall and per archetype.

Run:
  /work1/zixuan/envs/conda_envs/causalmemagent/bin/python audit_sft_canonical.py
"""
import collections
import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent          # pilot/peval/phi_d/sft2_eval
PHI_D = HERE.parent                                     # pilot/peval/phi_d
if str(PHI_D) not in sys.path:
    sys.path.insert(0, str(PHI_D))

import audit_expanded as A                                       # noqa: E402
import common as C                                               # noqa: E402

SFT_IRS = HERE / "canonical_sft.jsonl"
BASE_V2 = PHI_D / "out" / "extractions_v2.jsonl"
BASE_AUDIT_SAMPLE = PHI_D / "audit_expanded" / "per_sample.jsonl"
BASE_AUDIT_METRICS = PHI_D / "audit_expanded" / "field_metrics.json"
OUT_JSON = HERE / "audit_sft_canonical.json"
EVIDENCE_MAX_WORDS = 15        # frozen (sft2/audit_sft2.py)


# ---------------- frozen helpers (verbatim copies from sft2/audit_sft2.py) ----------------
def evidence_verbatim(ir, text):
    """Frozen def (sft2/audit_sft2.py): over VALID IRs, every present-status evidence
    string must be an exact case-sensitive substring of the text AND <=15 words."""
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
    """Frozen def (sft2/audit_sft2.py): branch node with non-null predicate AND
    non-empty then/else effects."""
    for n in ir["nodes"]:
        a = n.get("args") or {}
        if (n.get("op") == "branch" and a.get("predicate")
                and a.get("then_effects") and a.get("else_effects")):
            return True
    return False


# ---------------- join + score (mirrors audit_expanded.main, on given rows) ----------------
def score_rows(rows, sealed_ctx):
    fams, sib, nm, mems, instr_idx = sealed_ctx
    per_sample, join_stats = [], {"n_candidates": collections.Counter(),
                                  "conflicts": collections.Counter(),
                                  "no_join": 0, "arch_conflict": 0}
    for r in rows:
        if r["kind"] == "instruction":
            cand = [(t, None, "instruction") for t in instr_idx.get(r["text"], [])]
        else:
            cand = A.candidates_for(r, mems, sib, nm)
        join_stats["n_candidates"][len(cand)] += 1
        if not cand:
            join_stats["no_join"] += 1
            per_sample.append({"key": r["key"], "kind": r["kind"], "join_failed": True})
            continue
        truth, arch_issue = A.consensus(cand, fams)
        if truth is None:
            join_stats["arch_conflict"] += 1
            per_sample.append({"key": r["key"], "kind": r["kind"], "join_failed": True,
                               "arch_conflict": arch_issue})
            continue
        for d, v in truth.items():
            if v == "CONFLICT":
                join_stats["conflicts"][d] += 1
        scores = A.score_row(r["ir"], r["text"], truth, fams)
        clause = scores.pop("_clause"); tpol = scores.pop("_truth_polarity"); pnote = scores.pop("_polarity_note")
        cells = sorted({c for _, c, sk in cand if c})
        sks = sorted({sk for _, _, sk in cand})
        per_sample.append({
            "key": r["key"], "kind": r["kind"], "text": r["text"],
            "archetype": truth["archetype"], "signature": truth["signature"],
            "cells": cells, "source_kinds": sks, "n_candidates": len(cand),
            "scores": scores, "polarity_clause": clause, "truth_polarity": tpol,
            "polarity_note": pnote, "ir": r["ir"],
            "ir_attribute": (scores.get("_ir_predicate") or {}).get("attribute"),
            "truth_attr_anchor": sorted(truth["pred_attr"]) if truth["pred_attr"] != "CONFLICT" else "CONFLICT",
        })
    js = {"n_candidates": dict(join_stats["n_candidates"]),
          "conflicts": dict(join_stats["conflicts"]),
          "no_join": join_stats["no_join"], "arch_conflict": join_stats["arch_conflict"],
          "n_joined": sum(1 for p in per_sample if not p.get("join_failed"))}
    return per_sample, js


def parse_verdict(v):
    x = v[0]
    return "NA" if x == "NA" else "UNMEAS" if x == "UNMEAS" else x


def attribute_anchor_audit(joined):
    """The SFT2_GATE_REPORT §canon issue, quantified on the full 532."""
    per_arch = {}
    examples = []
    for p in joined:
        v, mode, detail = p["scores"]["pred_attribute"]
        a = p["archetype"]
        d = per_arch.setdefault(a, {"n_app": 0, "agree": 0, "contradict": 0, "missing": 0,
                                    "contradict_verbatim_in_text": 0})
        if v in ("NA", "UNMEAS"):
            continue
        d["n_app"] += 1
        if v is True:
            d["agree"] += 1
        elif v is False:
            d["contradict"] += 1
            irat = p["ir_attribute"]
            verbatim = bool(irat) and str(irat).strip().lower() in p["text"].lower()
            d["contradict_verbatim_in_text"] += verbatim
            if verbatim and a in ("two_row_transfer", "conditional_write") and len(examples) < 6:
                examples.append({"key": p["key"], "archetype": a,
                                 "ir_attribute": irat,
                                 "truth_anchor_tokens": p["truth_attr_anchor"],
                                 "clause": p["polarity_clause"][:280]})
        else:
            d["missing"] += 1
    tot = {"n_app": sum(d["n_app"] for d in per_arch.values()),
           "contradict": sum(d["contradict"] for d in per_arch.values()),
           "contradict_verbatim_in_text": sum(d["contradict_verbatim_in_text"] for d in per_arch.values())}

    # POSTHOC (non-gate) dual-anchor rescores. Two text-faithfulness anchors, both
    # measuring "the IR named a concept the TEXT carries" (no fabricated concept):
    #   dual_verbatim : sealed-anchor agreement OR IR attribute contiguous-verbatim in text
    #   dual_tokcov   : sealed-anchor agreement OR ALL IR-attribute tokens appear in text
    #                   (absorbs non-contiguous paraphrases like 'stock level' <-
    #                   'stock table' + 'minimum keep level')
    def flip_verbatim(irat, text):
        return bool(irat) and str(irat).strip().lower() in text.lower()

    def flip_tokcov(irat, text):
        tt = A.toks(text)
        at = A.toks(irat)
        return bool(at) and at <= tt

    for tag, flip in (("dual_verbatim", flip_verbatim), ("dual_tokcov", flip_tokcov)):
        for p in joined:
            v, mode, detail = p["scores"]["pred_attribute"]
            if v in ("NA", "UNMEAS"):
                dual = v
            elif v is True:
                dual = True
            else:
                dual = bool(v) or (v is False and flip(p["ir_attribute"], p["text"]))
                if v is None:
                    dual = None
            # refold pred_all with the attribute subfield replaced by the dual verdict
            subs = {f: p["scores"][f][0] for f in ("pred_op", "pred_value", "pred_polarity")}
            vs = [dual] + [subs[f] for f in ("pred_op", "pred_value", "pred_polarity")]
            if any(x is False for x in vs):
                pall = False
            elif all(x is True for x in vs):
                pall = True
            elif any(x == "UNMEAS" for x in vs):
                pall = "UNMEAS"
            else:
                pall = None
            p["scores"] = dict(p["scores"])
            p["scores"]["pred_attribute_%s" % tag] = (dual, "posthoc-%s" % tag, None)
            p["scores"]["pred_all_%s" % tag] = (pall, "posthoc-%s" % tag, None)
    dual_metrics = {}
    for tag in ("dual_verbatim", "dual_tokcov"):
        for f in ("pred_attribute", "pred_all"):
            dual_metrics["%s_%s" % (f, tag)] = A.aggregate_field(joined, "%s_%s" % (f, tag))
    # non-verbatim contradiction residue (the class the tokcov rule addresses)
    residue = [{"key": p["key"], "archetype": p["archetype"], "ir_attribute": p["ir_attribute"],
                "truth_anchor_tokens": p["truth_attr_anchor"],
                "attr_tokens_covered_by_text": flip_tokcov(p["ir_attribute"], p["text"]),
                "clause": p["polarity_clause"][:280]}
               for p in joined
               if p["scores"]["pred_attribute"][0] is False
               and not flip_verbatim(p["ir_attribute"], p["text"])]
    return {"per_archetype": per_arch, "overall": tot,
            "share_verbatim_in_text": (tot["contradict_verbatim_in_text"] / tot["contradict"]
                                       if tot["contradict"] else None),
            "non_verbatim_contradiction_residue": residue,
            "examples": examples, "dual_anchor_posthoc": dual_metrics}


def pair_coverage(sft_by_key):
    """Both-side validity / branch presence / both-side-JOINT over all 640 pairs."""
    pairs = C.load_pairs()
    per_arch = collections.defaultdict(lambda: collections.Counter())
    overall = collections.Counter()
    for row in pairs:
        a = row["archetype"]
        ik = "instruction:" + C.sha(row["instruction"])[:16]
        mk = "memory:" + C.sha(row["memory_text"])[:16]
        ir_i = (sft_by_key.get(ik) or {}).get("ir")
        ir_m = (sft_by_key.get(mk) or {}).get("ir")
        iv, mv = ir_i is not None, ir_m is not None
        ib = bool(iv and any(n["op"] == "branch" for n in ir_i["nodes"]))
        mb = bool(mv and any(n["op"] == "branch" for n in ir_m["nodes"]))
        ij, mj = bool(iv and both_side_joint(ir_i)), bool(mv and both_side_joint(ir_m))
        rec = {"both_present": sft_by_key.get(ik) is not None and sft_by_key.get(mk) is not None,
               "both_valid": iv and mv, "instr_branch": ib, "mem_branch": mb,
               "instr_bsj": ij, "mem_bsj": mj,
               "pair_both_side_joint": iv and mv and ij and mj}
        for k, v in rec.items():
            per_arch[a][k] += bool(v)
            overall[k] += bool(v)
        per_arch[a]["n"] += 1
        overall["n"] += 1

    def rates(c):
        return {"n": c["n"], **{k: c[k] / c["n"] for k in c if k != "n"}}
    return {"overall": rates(overall), "per_archetype": {a: rates(c) for a, c in sorted(per_arch.items())},
            "definitions": {"both_side_joint": "branch node carrying predicate + non-empty "
                            "then_effects + else_effects (frozen, sft2/audit_sft2.py)",
                            "pair_both_side_joint": "instruction IR valid AND memory IR valid "
                            "AND both sides both-side-JOINT"}}


def main():
    fams, sib, nm, mems = A.load_sealed()
    instr_idx = collections.defaultdict(list)
    for (fi, si), t in sib.items():
        instr_idx[t["instruction"]].append(t)
    sealed_ctx = (fams, sib, nm, mems, instr_idx)

    sft_rows = [json.loads(l) for l in open(SFT_IRS)]
    base_rows = [json.loads(l) for l in open(BASE_V2)]
    base_audit = {json.loads(l)["key"]: json.loads(l) for l in open(BASE_AUDIT_SAMPLE)}
    base_metrics = json.load(open(BASE_AUDIT_METRICS))

    assert len(sft_rows) == 532 and all(r["valid"] for r in sft_rows)
    assert [r["key"] for r in sft_rows] == [r["key"] for r in base_rows], "key order != v2"

    ps_sft, js_sft = score_rows(sft_rows, sealed_ctx)
    # ---- sanity S1: join parity vs frozen base audit
    js_base = base_metrics["join"]
    assert js_sft["n_joined"] == js_base["n_joined"] == 532, (js_sft, js_base)
    assert js_sft["no_join"] == js_base["no_join"] == 0
    assert js_sft["arch_conflict"] == js_base["arch_conflict"] == 0
    assert js_sft["conflicts"] == js_base["conflicts"], (js_sft["conflicts"], js_base["conflicts"])
    assert {str(k): v for k, v in js_sft["n_candidates"].items()} == js_base["n_candidates"]
    print("[sanity S1] join parity vs base audit: OK (n_joined=532, conflicts %s)"
          % js_sft["conflicts"], flush=True)

    # ---- sanity S2: base IRs re-scored through this path == audit_expanded verdicts (532x11)
    ps_base, _ = score_rows(base_rows, sealed_ctx)
    mism = []
    for p in ps_base:
        if p.get("join_failed"):
            mism.append((p["key"], "join_failed"))
            continue
        for f in A.GATE_FIELDS:
            if parse_verdict(base_audit[p["key"]]["scores"][f]) != parse_verdict(p["scores"][f]):
                mism.append((p["key"], f))
    if mism:
        json.dump(mism, open(HERE / "sanity_mismatch.json", "w"))
        raise SystemExit("SANITY FAIL S2: %d base-verdict mismatches vs audit_expanded" % len(mism))
    print("[sanity S2] base 532x11 verdicts == audit_expanded/per_sample.jsonl: OK", flush=True)

    joined = [p for p in ps_sft if not p.get("join_failed")]
    metrics = {"corpus": A.corpus_stats(joined, fams), "fields": {},
               "posthoc_diagnostics": A.posthoc_diagnostics(joined)}
    for field in A.GATE_FIELDS + ["branch_presence"]:
        metrics["fields"][field] = A.aggregate_field(joined, field)
    metrics["join"] = js_sft
    metrics["gate_rule"] = base_metrics["gate_rule"]
    metrics["veto_rule"] = base_metrics["veto_rule"]

    # extraction-side stats on the SFT corpus (parse/evidence/branch coverage)
    ev_n = ev_bad = 0
    for p, r in zip((p for p in ps_sft if not p.get("join_failed")), (r for r in sft_rows)):
        ok, n, b = evidence_verbatim(r["ir"], r["text"])
        ev_n += n
        ev_bad += b
    metrics["extraction"] = {
        "n": len(sft_rows), "valid": sum(r["valid"] for r in sft_rows),
        "first_pass_valid": sum(1 for r in sft_rows if r["attempts"] == 1 and r["valid"]),
        "repairs": sum(1 for r in sft_rows if r["attempts"] == 2),
        "evidence_span_level": {"n": ev_n, "bad": ev_bad,
                                "rate": (ev_n - ev_bad) / ev_n if ev_n else None},
    }

    metrics["attribute_anchor_audit"] = attribute_anchor_audit(joined)
    sft_by_key = {r["key"]: r for r in sft_rows}
    metrics["pair_coverage_640"] = pair_coverage(sft_by_key)

    # base-era side-by-side (same fields, same gates) for the report's comparison table
    metrics["base_era_comparison"] = {
        f: {"base_all_rows": base_metrics["fields"][f]["all_rows"],
            "base_worst_archetype": base_metrics["fields"][f]["worst_archetype"],
            "base_false_absent": base_metrics["fields"][f]["false_absent"],
            "base_present_only": base_metrics["fields"][f]["present_only"],
            "base_veto": base_metrics["fields"][f].get("veto_eligibility"),
            "sft_all_rows": metrics["fields"][f]["all_rows"],
            "sft_worst_archetype": metrics["fields"][f]["worst_archetype"],
            "sft_false_absent": metrics["fields"][f]["false_absent"],
            "sft_present_only": metrics["fields"][f]["present_only"],
            "sft_veto": metrics["fields"][f].get("veto_eligibility")}
        for f in A.GATE_FIELDS}

    out = {"meta": {
        "task": "S2-prep stage 2: expanded audit of SFT2 IRs on canonical 532 vs sealed truth",
        "measurement_code": "audit_expanded.py imported read-only (code_sha16 %s)"
                            % hashlib.sha256(open(PHI_D / "audit_expanded.py", "rb").read()).hexdigest()[:16],
        "irs": str(SFT_IRS), "irs_sha16": hashlib.sha256(open(SFT_IRS, "rb").read()).hexdigest()[:16],
        "truth": "/work1/zixuan/data/agent_memory/sealed (measurement-only; never model input)",
        "e1_e2": "pre-registered exceptions inherited verbatim from audit_expanded (frozen)",
        "script_sha16": hashlib.sha256(open(__file__, "rb").read()).hexdigest()[:16]},
        **metrics}
    with open(OUT_JSON, "w") as f:
        json.dump(A.canon(out), f, indent=1, ensure_ascii=False, default=str)
    print("[audit] wrote %s" % OUT_JSON, flush=True)
    for f in A.GATE_FIELDS:
        m = metrics["fields"][f]
        print("[gate] %-16s n=%3d all_rows=%s worst_arch=%s fa=%s -> %s | %s"
              % (f, m["n_app"],
                 "%.3f" % m["all_rows"] if m["all_rows"] is not None else "NA",
                 "%.3f" % m["worst_archetype"] if m["worst_archetype"] is not None else "NA",
                 "%.3f" % m["false_absent"] if m["false_absent"] is not None else "NA",
                 "PASS" if m["gate"]["PASS"] else "FAIL", m.get("veto_eligibility")), flush=True)
    cov = metrics["pair_coverage_640"]
    print("[pairs] overall:", json.dumps(cov["overall"], indent=1), flush=True)
    print("[pairs] per-archetype:", json.dumps({a: {k: round(v, 4) if isinstance(v, float) else v
                                                    for k, v in d.items()}
                                                for a, d in cov["per_archetype"].items()}, indent=1), flush=True)


if __name__ == "__main__":
    main()
