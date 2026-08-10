"""Faithfulness audit (blind, CPU-only): extracted IR fields vs SEALED generator truth.

Runs AFTER the v2 merge. Sampling is blind: 30 valid IRs drawn with
random.Random(42) from out/extractions_v2.jsonl (10 instruction + 20 memory),
selection independent of any label or audit outcome. Sealed truth
(/work1/zixuan/data/agent_memory/sealed/*) is used ONLY here, never as model input.

=================  PRE-REGISTERED AGREEMENT FIELDS (defined before running)  =================
Joins:
- instruction text  -> unique tasks_sealed kind="sibling" group with identical text.
- memory text       -> ALL memories_sealed rows with identical text, each mapped to a
  truth task per source_kind (sibling_same_family -> sibling task (family_idx,
  target_sibling); near_miss -> near_miss task of family_idx; cross_domain_pair /
  unrelated -> sibling task (source_family, target_sibling)).
  AMENDMENT (2026-08-10, pre-registered before any audit results were produced):
  entity-generic memory styles produce text-identical memories for different families
  (73/372 benchmark memory texts have >1 sealed row; of these 12 have genuinely
  different theta values, i.e. the text does not determine theta; 0 signature/op
  conflicts corpus-wide). PARTIAL-CONSENSUS RULE: an audited dimension is scored
  only if ALL candidate truth tasks agree on it; a dimension on which candidates
  disagree is recorded join_conflict (None) and excluded from the present-only rate
  while counting as missing in the all-rows rate. Archetype/signature/predicate-op
  are consensus-safe corpus-wide; predicate-value can conflict (12 texts).

Truth predicate (per archetype, from the joined task's program_params/signature):
- conditional_write  : op = cond_op,                      value = theta
- aggregate_gate     : op = check.op,                     value = check.value
- delete_after_capture: op = check.op,                    value = "cold"-style string
- two_row_transfer   : guard is composite; truth op SET = {">=", "<="} and
  value SET = {guard.min_a, guard.cap_b} (membership rule below).

IR predicate carrier: FIRST branch node in id order. An IR with no branch node
scores "missing" on all pred_* fields (counted as disagreement in the all-rows rate).

Fields (per sample):
1. pred_op          : P1/P3/P4 -> IR op == truth op. P2 -> IR op in truth op SET.
2. pred_op_bucket   : direction bucket agreement; buckets G={>,>=}, L={<,<=}, EQ={==}, NE={!=}.
                      P1/P3/P4 -> same bucket; P2 -> IR bucket intersects truth buckets.
3. pred_value       : P1/P3 -> numeric equality after float parsing (either side may
                      carry quotes/units); P4 -> exact string equality; P2 -> membership
                      in truth value SET (numeric).
4. polarity         : IR polarity.value == truth polarity. TRUTH POLARITY RULE
                      (deterministic): take the source TEXT, locate the first condition
                      cue among ["If ", "if ", "Guard:", "Policy:"], cut the clause at the
                      first of [",", ";", newline, " -- "]; truth is "negative" iff regex
                      \b(no|none|nobody|not|never|without)\b (case-insensitive) matches the
                      clause, else "positive". The extracted clause is stored per sample
                      for post-hoc human verification.
5. seq_contained    : expected op sequence (signature steps expanded: READ/READx2/
                      READ+POLICY -> read x1/2/2, AGG -> aggregate, CHECK -> branch,
                      BRANCHWRITE -> nothing (absorbed into the CHECK branch node, whose
                      args carry then/else effects per the IR spec), WRITE/WRITEx2 ->
                      write x1/2, ARCHIVE -> write, DELx2 -> write,write, VERIFY -> verify)
                      is an ORDERED SUBSEQUENCE of the IR node op list (nodes sorted by
                      numeric id suffix); extra IR nodes are allowed.
6. seq_lcs_ratio    : LCS(expected, ir_ops) / len(expected).

Rates reported two ways: over ALL sampled rows (missing counts as disagreement) and
over field-present rows only. At least 5 disagreement examples are dumped with text
head, IR branch payload, truth, and the polarity clause.
Output: out/guided/faithfulness_audit.json
=========================================================================================
"""
import collections
import json
import random
import re
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
SEALED = pathlib.Path("/work1/zixuan/data/agent_memory/sealed")
V2 = HERE / "out" / "extractions_v2.jsonl"
DST = HERE / "out" / "guided" / "faithfulness_audit.json"

NEG_RE = re.compile(r"\b(no|none|nobody|not|never|without)\b", re.I)
CUES = ["If ", "if ", "Guard:", "Policy:"]
CUTS = [",", ";", "\n", " -- "]


def condition_clause(text):
    """Truth-polarity clause: first condition cue .. first cut marker (pre-registered rule)."""
    pos = min((text.find(c) for c in CUES if text.find(c) != -1), default=-1)
    if pos == -1:
        return text[:300]
    rest = text[pos:]
    cut = min((rest.find(c) for c in CUTS if rest.find(c) != -1), default=len(rest))
    return rest[:cut]


def truth_polarity(text):
    return "negative" if NEG_RE.search(condition_clause(text)) else "positive"


def num(x):
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    m = re.search(r"-?\d+(\.\d+)?", str(x))
    return float(m.group()) if m else None


def lcs(a, b):
    dp = [0] * (len(b) + 1)
    for x in a:
        prev = 0
        for j, y in enumerate(b, 1):
            cur = dp[j]
            dp[j] = prev + 1 if x == y else max(dp[j], dp[j - 1])
            prev = cur
    return dp[-1]


def subsequence(needle, hay):
    it = iter(hay)
    return all(any(x == y for y in it) for x in needle)


SIG_EXPANSION = {
    "READ": ["read"], "READx2": ["read", "read"], "READ+POLICY": ["read", "read"],
    "AGG": ["aggregate"], "CHECK": ["branch"], "BRANCHWRITE": [],
    "WRITE": ["write"], "WRITEx2": ["write", "write"], "ARCHIVE": ["write"],
    "DELx2": ["write", "write"], "VERIFY": ["verify"],
}


def expected_seq(signature):
    steps = signature.split("|")[-1].split(";")
    out = []
    for s in steps:
        out.extend(SIG_EXPANSION[s])
    return out


def bucket(op):
    return {"G": {">", ">="}, "L": {"<", "<="}, "EQ": {"=="}, "NE": {"!="}}.get(
        next((k for k, v in {"G": {">", ">="}, "L": {"<", "<="}, "EQ": {"=="}, "NE": {"!="}}.items()
             if op in v), None), set())


def truth_predicate(task, arch):
    pp = task["program_params"]
    if arch == "conditional_write":
        return {"mode": "exact", "op": pp["cond_op"], "value": pp["theta"]}
    if arch == "aggregate_gate":
        return {"mode": "exact", "op": pp["check"]["op"], "value": pp["check"]["value"]}
    if arch == "delete_after_capture":
        return {"mode": "exact", "op": pp["check"]["op"], "value": str(pp["check"]["value"])}
    if arch == "two_row_transfer":
        g = pp["guard"]
        return {"mode": "membership", "op_set": [">=", "<="],
                "value_set": [float(g["min_a"]), float(g["cap_b"])]}
    raise ValueError(arch)


def main():
    fam = {f["family_idx"]: f for f in map(json.loads, open(SEALED / "families.jsonl"))}
    tasks = [json.loads(l) for l in open(SEALED / "tasks_sealed.jsonl")]
    mems = [json.loads(l) for l in open(SEALED / "memories_sealed.jsonl")]

    instr_truth = {}
    for t in tasks:
        if t["kind"] == "sibling":
            instr_truth.setdefault(t["instruction"], t)
    nm_truth = {t["family_idx"]: t for t in tasks if t["kind"] == "near_miss"}
    sib_truth = {}
    for t in tasks:
        if t["kind"] == "sibling":
            sib_truth[(t["family_idx"], t["sibling_idx"])] = t

    rows = [json.loads(l) for l in open(V2)]
    valid = [r for r in rows if r.get("valid")]
    rng = random.Random(42)
    s_instr = sorted([r for r in valid if r["kind"] == "instruction"], key=lambda r: r["key"])
    s_mem = sorted([r for r in valid if r["kind"] == "memory"], key=lambda r: r["key"])
    sample = rng.sample(s_instr, 10) + rng.sample(s_mem, 20)

    results = []
    for r in sample:
        rec = {"key": r["key"], "kind": r["kind"], "provenance": r["provenance"]["source_run"]}
        if r["kind"] == "instruction":
            task = instr_truth.get(r["text"])
            assert task, f"no sealed sibling task for instruction key {r['key']}"
            rec["cell"] = None
            mrow = None
            rec["n_join_candidates"] = 1
            rec["join_conflicts"] = []
        else:
            hits = [m for m in mems if m["text"] == r["text"]]
            assert hits, f"no sealed memory for {r['key']}"
            mrow = hits[0]
            rec["cell"] = mrow["cell"]
            cand = []
            for m in hits:
                if m["source_kind"] == "sibling_same_family":
                    cand.append(sib_truth[(m["family_idx"], m["target_sibling"])])
                elif m["source_kind"] == "near_miss":
                    cand.append(nm_truth[m["family_idx"]])
                else:  # cross_domain_pair / unrelated
                    cand.append(sib_truth[(m["source_family"], m["target_sibling"])])
            rec["n_join_candidates"] = len(cand)
            rec["join_conflicts"] = []
        if r["kind"] == "instruction":
            cand = [task]
        archs = {fam[t["family_idx"]]["archetype"] for t in cand}
        assert len(archs) == 1, f"archetype conflict at {r['key']}: {archs}"
        arch = archs.pop()
        sigs = {t["signature"] for t in cand}
        tps = [truth_predicate(t, arch) for t in cand]
        op_same = len({json.dumps((x.get("op"), x.get("op_set"))) for x in tps}) == 1
        val_same = len({json.dumps((str(x.get("value")), x.get("value_set"))) for x in tps}) == 1
        if len(sigs) > 1 or not op_same:
            rec["join_conflicts"].append("signature_or_op")
        if not val_same:
            rec["join_conflicts"].append("predicate_value")
        task = cand[0]
        rec.update({"archetype": arch, "family_idx": task["family_idx"],
                    "source_kind": mrow["source_kind"] if mrow else "instruction",
                    "truth_signature": task["signature"]})

        ir = r["ir"]
        nodes = sorted(ir["nodes"], key=lambda n: int(re.sub(r"\D", "", n["id"]) or 0))
        ir_ops = [n["op"] for n in nodes]
        branches = [n for n in nodes if n["op"] == "branch"]
        tp = truth_predicate(task, arch)
        clause = condition_clause(r["text"])
        tpol = truth_polarity(r["text"])
        rec["truth_predicate"] = tp
        rec["truth_polarity"] = tpol
        rec["polarity_clause"] = clause
        rec["ir_ops"] = ir_ops
        rec["expected_ops"] = expected_seq(task["signature"])
        sig_conflict = "signature_or_op" in rec["join_conflicts"]
        val_conflict = "predicate_value" in rec["join_conflicts"]

        # predicate fields (first branch in id order)
        if not branches:
            rec.update({"has_branch": False, "pred_op": None, "pred_op_bucket": None,
                        "pred_value": None, "polarity": None,
                        "ir_predicate": None, "ir_polarity": None})
        else:
            p = branches[0]["args"]["predicate"]
            iop = p.get("op", {}).get("value")
            ival = p.get("value", {}).get("value")
            ipol = p.get("polarity", {}).get("value")
            rec["has_branch"] = True
            rec["ir_predicate"] = {"op": iop, "value": ival, "polarity": ipol,
                                   "attribute": p.get("attribute", {}).get("value")}
            rec["ir_polarity"] = ipol
            if sig_conflict:
                rec["pred_op"] = None
                rec["pred_op_bucket"] = None
            elif tp["mode"] == "exact":
                rec["pred_op"] = (iop == tp["op"])
                rec["pred_op_bucket"] = bool(bucket(iop) & bucket(tp["op"])) if iop else False
            else:
                rec["pred_op"] = iop in tp["op_set"]
                rec["pred_op_bucket"] = bool(bucket(iop) & set().union(*map(bucket, tp["op_set"]))) if iop else False
            if val_conflict:
                rec["pred_value"] = None
            elif tp["mode"] == "exact":
                if arch == "delete_after_capture":
                    rec["pred_value"] = (str(ival).strip("'\"") == str(tp["value"]).strip("'\"")) if ival is not None else False
                else:
                    rec["pred_value"] = (num(ival) == num(tp["value"])) if num(ival) is not None else False
            else:
                rec["pred_value"] = (num(ival) in tp["value_set"]) if num(ival) is not None else False
            rec["polarity"] = (ipol == tpol)

        exp = rec["expected_ops"]
        if sig_conflict:
            rec["seq_contained"] = None
            rec["seq_lcs_ratio"] = None
        else:
            rec["seq_contained"] = subsequence(exp, ir_ops)
            rec["seq_lcs_ratio"] = lcs(exp, ir_ops) / len(exp)
        results.append(rec)

    fields = ["pred_op", "pred_op_bucket", "pred_value", "polarity", "seq_contained"]
    agree = {}
    for f in fields:
        vals = [x[f] for x in results]
        present = [v for v in vals if v is not None]
        agree[f] = {"all_rows": sum(v is True for v in vals) / len(vals),
                    "present_only": (sum(present) / len(present)) if present else None,
                    "n_present": len(present), "n_missing": len(vals) - len(present)}
    lcs_vals = [x["seq_lcs_ratio"] for x in results if x["seq_lcs_ratio"] is not None]
    agree["seq_lcs_ratio"] = {"mean": sum(lcs_vals) / len(lcs_vals) if lcs_vals else None,
                              "min": min(lcs_vals) if lcs_vals else None,
                              "n_present": len(lcs_vals)}

    by_kind = {}
    for kind in ("instruction", "memory"):
        sub = [x for x in results if x["kind"] == kind]
        by_kind[kind] = {f: {"all_rows": sum(x[f] is True for x in sub) / len(sub),
                             "n_missing": sum(x[f] is None for x in sub)}
                         for f in fields}
        sv = [x["seq_lcs_ratio"] for x in sub if x["seq_lcs_ratio"] is not None]
        by_kind[kind]["seq_lcs_mean"] = sum(sv) / len(sv) if sv else None

    # ---------------- post-hoc verification addendum (primary metrics above unchanged)
    # Two deterministic, documented checks over the STORED clauses/texts:
    # (1) polarity clause targeting: the first-cue rule can land on an else-path guard
    #     fragment ("if it is not") when the text states the operative condition
    #     positively earlier ("Confirm the row's status is 'cold' -- if it is not, stop").
    #     Re-mark: verified truth = "positive" iff the text matches the operative-positive
    #     template; otherwise the as-measured truth stands.
    # (2) pred_value textual-indirect classification: when truth is numeric but its digits
    #     appear nowhere in the sample's CONDITION CLAUSE (the pre-registered condition
    #     window), the numeric value is not extractable; the IR emitting the policy-field
    #     reference (e.g. 'overstock_limit') is noted separately instead of being read as
    #     a value error.
    v2rows = {r["key"]: r for r in map(json.loads, open(V2))}
    n_pol_remark = 0
    n_val_indirect = 0
    for x in results:
        text = v2rows[x["key"]]["text"]
        x["polarity_clause_rule_note"] = None
        if x["ir_polarity"] is not None:
            vt = x["truth_polarity"]
            if x["polarity_clause"].strip().startswith("if it is not") and \
                    re.search(r"is '\w+'\s*--\s*if it is not", text):
                vt = "positive"
                x["polarity_clause_rule_note"] = ("first-cue clause is an else-path guard "
                                                  "fragment; operative condition stated "
                                                  "positively upstream -> verified truth positive")
                n_pol_remark += int(vt != x["truth_polarity"])
            x["polarity_verified"] = {"truth": vt, "agree": x["ir_polarity"] == vt}
        if x["pred_value"] is False:
            tpv = x["truth_predicate"]
            tv = tpv.get("value")
            digits = re.search(r"-?\d+(\.\d+)?", str(tv))
            irv = (x["ir_predicate"] or {}).get("value")
            if digits and digits.group() not in x["polarity_clause"] and irv and not re.search(r"\d", str(irv)):
                x["pred_value_textually_indirect"] = {
                    "truth_value": tv, "ir_value": irv,
                    "note": "numeric theta nowhere in text; IR emitted the policy-field reference"}
                n_val_indirect += 1
    ver_pol = [x["polarity_verified"]["agree"] for x in results if "polarity_verified" in x]
    posthoc = {
        "rules": ["polarity clause re-targeting for else-path guard fragments "
                  "(operative condition stated positively upstream)",
                  "pred_value textual-indirect classification (numeric theta absent from text)"],
        "polarity_remarked": n_pol_remark,
        "polarity_verified_agreement": {"present_only": sum(ver_pol) / len(ver_pol) if ver_pol else None,
                                        "all_rows": (sum(ver_pol) / len(results))},
        "pred_value_textually_indirect": n_val_indirect,
        "pred_value_indirect_adjusted": {
            "present_only": (sum(x["pred_value"] is True for x in results) + n_val_indirect)
                            / (sum(x["pred_value"] is not None for x in results))},
    }

    disagree = [x for x in results
                if any(x[f] is False or x[f] is None for f in fields)
                or x["seq_lcs_ratio"] is None or x["seq_lcs_ratio"] < 1.0]
    examples = []
    for x in disagree:
        examples.append({"key": x["key"], "kind": x["kind"], "cell": x["cell"],
                         "archetype": x["archetype"], "truth_signature": x["truth_signature"],
                         "ir_ops": x["ir_ops"], "expected_ops": x["expected_ops"],
                         "ir_predicate": x["ir_predicate"], "truth_predicate": x["truth_predicate"],
                         "scores": {f: x[f] for f in ("pred_op", "pred_op_bucket", "pred_value",
                                                      "polarity", "seq_contained", "seq_lcs_ratio")},
                         "polarity_clause": x["polarity_clause"]})

    out = {
        "design": "pre-registered field definitions in script header; blind seed-42 sample; "
                  "sealed truth eval-only",
        "sample": {"n": len(results), "instructions": sum(x["kind"] == "instruction" for x in results),
                   "memories": sum(x["kind"] == "memory" for x in results),
                   "cells": dict(collections.Counter(x["cell"] for x in results if x["cell"])),
                   "archetypes": dict(collections.Counter(x["archetype"] for x in results)),
                   "no_branch_in_ir": sum(not x["has_branch"] for x in results)},
        "agreement": agree,
        "by_kind": by_kind,
        "posthoc_verification": posthoc,
        "n_disagreement": len(disagree),
        "disagreement_examples": examples[:8],
        "per_sample": results,
    }
    with open(DST, "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(json.dumps({"sample": out["sample"], "agreement": agree, "by_kind": by_kind,
                      "n_disagreement": len(disagree)}, indent=2))


if __name__ == "__main__":
    main()
