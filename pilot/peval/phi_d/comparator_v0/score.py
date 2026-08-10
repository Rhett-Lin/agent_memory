"""Scoring for comparator v0 verdicts (the ONLY label consumer in comparator_v0/).

Fixed mapping {match:1.0, unknown:0.5, contradict:0.0} (SPEC.md section 6). Every
pair stays in every denominator (invalid/unknown kept). Mirrors score_baselines.py
AUC semantics exactly (rank-based with ties); no sklearn.

Metrics per scorer (comparator, sim_embed, frozen judge):
  per-cell admission (mean score; A00/A01 = false-admission, A10/A11 = retention)
  AUC overall (labels P), AUC S=1 (A01 vs A11)
  GroupKFold(family_idx, 40): AUC per family fold, macro mean (folds with a
    single label class are dropped and counted)
  LOAO per-archetype: AUCs computed per archetype + macro mean; plus
    leave-one-archetype-out pooled AUCs
Kill conditions (adjudicated): lane A demotes to baseline-only if
  retention(A10) or retention(A11) < 0.50 overall or per-archetype, OR
  any archetype S=1 AUC < 0.60, OR admission(A01) > 0.10.

Writes score_summary.json; prints the table.
"""
import collections
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
PHI_D = HERE.parent
PAIRS = PHI_D.parent / "pairs.jsonl"
VERDICTS = HERE / "verdicts.jsonl"
JUDGMENTS = PHI_D / "out" / "judgments.jsonl"
EXTRACTIONS = PHI_D / "out" / "extractions_v2.jsonl"
OUT_SUMMARY = HERE / "score_summary.json"

VERDICT_SCORE = {"match": 1.0, "unknown": 0.5, "contradict": 0.0}
CELLS = ("A00", "A01", "A10", "A11")


def auc(scores, labels):
    """Rank-based AUC with tie handling; None if single-class (as score_baselines.py)."""
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


def load_jsonl(p):
    return [json.loads(l) for l in open(p) if l.strip()]


def scorer_metrics(name, scores, pairs):
    P = [r["P"] for r in pairs]
    S = [r["S"] for r in pairs]
    arch = [r["archetype"] for r in pairs]
    fam = [r["family_idx"] for r in pairs]
    cell = [r["cell"] for r in pairs]
    out = {"scorer": name}

    s1 = [i for i in range(len(pairs)) if S[i] == 1]
    out["auc_overall"] = auc(scores, P)
    out["auc_S1"] = auc([scores[i] for i in s1], [P[i] for i in s1])

    # GroupKFold(family_idx, 40): each family = one fold; macro mean of fold AUCs
    fam_overall, fam_s1, skipped = [], [], 0
    for f in sorted(set(fam)):
        idx = [i for i in range(len(pairs)) if fam[i] == f]
        a = auc([scores[i] for i in idx], [P[i] for i in idx])
        si = [i for i in idx if S[i] == 1]
        b = auc([scores[i] for i in si], [P[i] for i in si])
        if a is None:
            skipped += 1
        else:
            fam_overall.append(a)
        if b is not None:
            fam_s1.append(b)
    out["auc_overall_family_macro40"] = (sum(fam_overall) / len(fam_overall)
                                         if fam_overall else None)
    out["auc_S1_family_macro40"] = sum(fam_s1) / len(fam_s1) if fam_s1 else None
    out["family_folds"] = {"n_total": len(set(fam)),
                           "n_overall_used": len(fam_overall),
                           "n_S1_used": len(fam_s1),
                           "n_overall_single_class_skipped": skipped}

    # per archetype + macro (LOAO-style decomposition) and leave-one-archetype-out
    per_arch = {}
    for a in sorted(set(arch)):
        idx = [i for i in range(len(pairs)) if arch[i] == a]
        si = [i for i in idx if S[i] == 1]
        per_arch[a] = {"auc_overall": auc([scores[i] for i in idx], [P[i] for i in idx]),
                       "auc_S1": auc([scores[i] for i in si], [P[i] for i in si])}
    out["per_archetype"] = per_arch
    vals = [v["auc_S1"] for v in per_arch.values() if v["auc_S1"] is not None]
    out["auc_S1_LOAO_macro"] = sum(vals) / len(vals) if vals else None
    loao = {}
    for a in sorted(set(arch)):
        idx = [i for i in range(len(pairs)) if arch[i] != a]
        si = [i for i in idx if S[i] == 1]
        loao[a] = auc([scores[i] for i in si], [P[i] for i in si])
    out["auc_S1_leave_one_archetype_out"] = loao

    # per-cell admission (A00/A01) and retention (A10/A11), overall + per archetype
    per_cell = {}
    for c in CELLS:
        idx = [i for i in range(len(pairs)) if cell[i] == c]
        adm = sum(scores[i] for i in idx) / len(idx)
        arch_break = {}
        for a in sorted(set(arch)):
            ai = [i for i in idx if arch[i] == a]
            arch_break[a] = sum(scores[i] for i in ai) / len(ai)
        per_cell[c] = {"n": len(idx), "admission": adm, "per_archetype": arch_break}
    out["per_cell"] = per_cell
    return out


def verdict_reason_stats(verdicts, pairs):
    """Reason histograms by level, overall and per cell; certificate completeness."""
    by_level = collections.Counter()
    by_code_level = collections.Counter()
    per_cell_codes = {c: collections.Counter() for c in CELLS}
    cert = {"memory_complete": 0, "instruction_complete": 0,
            "memory_check_fail": collections.Counter(),
            "instruction_check_fail": collections.Counter()}
    for v, p in zip(verdicts, pairs):
        for r in v["reasons"]:
            by_level[r["level"]] += 1
            by_code_level[f'{r["code"]}|{r["level"]}'] += 1
            per_cell_codes[p["cell"]][f'{r["code"]}|{r["level"]}'] += 1
        c = v.get("certificates") or {}
        for side, key in (("memory", "memory_complete"),
                          ("instruction", "instruction_complete")):
            if c.get(key):
                cert[key] += 1
            checks = c.get(f"{side}_checks") or {}
            for chk, okv in checks.items():
                if okv is False:
                    cert[f"{side}_check_fail"][chk] += 1
    top_contra = [(k, n) for k, n in by_code_level.most_common() if k.endswith("|contradict")]
    top_unknown = [(k, n) for k, n in by_code_level.most_common() if k.endswith("|unknown")]
    return {"reason_level_histogram": dict(by_level),
            "top_contradiction_reasons": top_contra[:10],
            "top_unknown_reasons": top_unknown[:10],
            "per_cell_reason_counts": {c: dict(cnt.most_common(12))
                                       for c, cnt in per_cell_codes.items()},
            "certificate": {"memory_complete_rate": cert["memory_complete"] / len(verdicts),
                            "instruction_complete_rate": cert["instruction_complete"] / len(verdicts),
                            "memory_check_failures": dict(cert["memory_check_fail"].most_common()),
                            "instruction_check_failures": dict(cert["instruction_check_fail"].most_common())}}


def main():
    pairs = load_jsonl(PAIRS)
    verdicts = load_jsonl(VERDICTS)
    judgments = {j["memory_id"]: j for j in load_jsonl(JUDGMENTS)}
    exts = load_jsonl(EXTRACTIONS)
    vmap = {v["memory_id"]: v for v in verdicts}
    assert len(pairs) == 640 and len(verdicts) == 640

    comp_scores = [VERDICT_SCORE[vmap[p["memory_id"]]["verdict"]] for p in pairs]
    embed_scores = [p["sim_embed"] for p in pairs]
    judge_scores = []
    for p in pairs:
        j = judgments.get(p["memory_id"])
        if j is None or not j["valid"]:
            judge_scores.append(0.5)
        else:
            judge_scores.append(VERDICT_SCORE.get(j["verdict"], 0.5))

    summary = {}
    summary["comparator_v0"] = scorer_metrics("comparator_v0", comp_scores, pairs)
    summary["sim_embed"] = scorer_metrics("sim_embed", embed_scores, pairs)
    summary["judge_frozen"] = scorer_metrics("judge_frozen", judge_scores, pairs)

    # comparator verdict mix per cell + coverage (non-unknown) per cell
    mix = {}
    for c in CELLS:
        idx = [i for i in range(len(pairs)) if pairs[i]["cell"] == c]
        cnt = collections.Counter(vmap[pairs[i]["memory_id"]]["verdict"] for i in idx)
        mix[c] = {"n": len(idx),
                  "match": cnt.get("match", 0), "contradict": cnt.get("contradict", 0),
                  "unknown": cnt.get("unknown", 0),
                  "directional_coverage": (cnt.get("match", 0) + cnt.get("contradict", 0)) / len(idx)}
    summary["comparator_verdict_mix_per_cell"] = mix

    # both-side-valid coverage per cell (extraction validity denominator honesty)
    valid_keys = {e["key"] for e in exts if e.get("valid")}
    bsv = {}
    import hashlib
    for c in CELLS:
        idx = [i for i in range(len(pairs)) if pairs[i]["cell"] == c]
        ok = 0
        for i in idx:
            p = pairs[i]
            ki = f"instruction:{hashlib.sha256(p['instruction'].encode()).hexdigest()[:16]}"
            km = f"memory:{hashlib.sha256(p['memory_text'].encode()).hexdigest()[:16]}"
            ok += int(ki in valid_keys and km in valid_keys)
        bsv[c] = {"n": len(idx), "both_side_valid": ok, "rate": ok / len(idx)}
    summary["both_side_valid_per_cell"] = bsv

    summary["reason_stats"] = verdict_reason_stats(
        [vmap[p["memory_id"]] for p in pairs], pairs)

    # ---------------- kill conditions (adjudicated thresholds) ----------------
    comp = summary["comparator_v0"]
    kills = []
    for c in ("A10", "A11"):
        ret = comp["per_cell"][c]["admission"]
        if ret < 0.50:
            kills.append(f"retention({c}) overall {ret:.3f} < 0.50")
        for a, r in comp["per_cell"][c]["per_archetype"].items():
            if r < 0.50:
                kills.append(f"retention({c}|{a}) {r:.3f} < 0.50")
    for a, v in comp["per_archetype"].items():
        s1a = v["auc_S1"]
        if s1a is None or s1a < 0.60:
            kills.append(f"S=1 AUC({a}) {s1a if s1a is None else round(s1a,3)} < 0.60")
    a01 = comp["per_cell"]["A01"]["admission"]
    if a01 > 0.10:
        kills.append(f"admission(A01) {a01:.3f} > 0.10")
    summary["kill_conditions"] = {
        "thresholds": {"retention_A10_A11_min": 0.50, "archetype_S1_auc_min": 0.60,
                       "admission_A01_max": 0.10},
        "violations": kills,
        "lane_A_verdict": "DEMOTE to baseline-only, no rule iteration" if kills
                          else "PASS (lane A survives to S2 release)"}

    with open(OUT_SUMMARY, "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    # ---------------- console table ----------------
    def f4(x):
        return f"{x:.4f}" if x is not None else "  n/a"
    print("scorer            AUC_all  AUC_S1  fam40_all  fam40_S1  LOAO_macro_S1")
    for k in ("comparator_v0", "sim_embed", "judge_frozen"):
        m = summary[k]
        print(f"{k:16s}  {f4(m['auc_overall'])}  {f4(m['auc_S1'])}   "
              f"{f4(m['auc_overall_family_macro40'])}     {f4(m['auc_S1_family_macro40'])}     "
              f"{f4(m['auc_S1_LOAO_macro'])}")
    print("\nper-cell admission (comparator): "
          + "  ".join(f"{c}={comp['per_cell'][c]['admission']:.3f}" for c in CELLS))
    print("per-cell admission (judge):      "
          + "  ".join(f"{c}={summary['judge_frozen']['per_cell'][c]['admission']:.3f}" for c in CELLS))
    print("per-cell sim_embed:              "
          + "  ".join(f"{c}={summary['sim_embed']['per_cell'][c]['admission']:.3f}" for c in CELLS))
    print("\nkill conditions:", json.dumps(summary["kill_conditions"], indent=1))
    print(f"\nwrote {OUT_SUMMARY}")


if __name__ == "__main__":
    main()
