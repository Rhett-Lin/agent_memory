"""Gate B audit 2/4: attack tau_struct with the failed 7B difficulty TOST.

The pilot's 7B no-memory difficulty-equivalence test FAILED (mean within-family
sibling-pair N-rate diff -0.019, bootstrap CI [-0.077, +0.038] vs a +/-7pp
margin). If sibling difficulty is not balanced, cell contrasts could in
principle be difficulty artifacts. Three attacks:

(i) Trim the worst-difficulty-mismatched sibling pairs (drop both siblings'
    rollouts, ALL cells) until the TOST at +/-7pp passes; recompute
    tau_struct / tau_trap / replay premium on the trimmed data.

(ii) Per-family-difficulty-adjusted contrasts: subtract each family's
     N-condition mean rate before computing cell contrasts. NOTE: on this
     balanced grid (every family contributes equally to every cell) any
     per-family additive adjustment cancels EXACTLY in two-cell contrasts --
     we verify the identity numerically and report it as a designed
     invariance, then run the adjustment that can actually move the estimate:
     stratification by family difficulty (hard/easy halves by N rate).

(iii) Per-archetype (8 schemas) tau_struct breakdown: is the effect driven by
      one archetype?

Everything family-cluster bootstrapped (2000 reps, seeds from AUDIT_SEED).

Usage:  python difficulty_robust.py
"""

import json
import os
from collections import defaultdict

import numpy as np

import common as C

TOST_MARGIN = 0.07


# ---------------------------------------------------------------------------
# difficulty structure (per model, N condition)
# ---------------------------------------------------------------------------

def difficulty_pairs(rows, model):
    """Within-family sibling-pair N-rate differences."""
    mr = [r for r in rows if r["model"] == model and r["cell"] == "N"]
    by_key = defaultdict(list)
    for r in mr:
        by_key[(r["family_idx"], r["sibling_idx"])].append(r["success"])
    fam_sib_rate = defaultdict(dict)
    for (fi, sib), vs in by_key.items():
        fam_sib_rate[fi][sib] = sum(vs) / len(vs)
    pairs = []
    for fi, smap in sorted(fam_sib_rate.items()):
        sibs = sorted(smap)
        for i in range(len(sibs)):
            for j in range(i + 1, len(sibs)):
                pairs.append({"family_idx": fi, "a": sibs[i], "b": sibs[j],
                              "diff": smap[sibs[i]] - smap[sibs[j]]})
    return pairs, fam_sib_rate


def tost_on_pairs(pairs, seed):
    units = [dict(p) for p in pairs]

    def stat(sub):
        return float(np.mean([u["diff"] for u in sub])) if sub else float("nan")

    p, lo, hi, _ = C.family_cluster_bootstrap(units, stat, seed=seed)
    eq = bool(lo > -TOST_MARGIN and hi < TOST_MARGIN)
    return {"mean_pair_diff": p, "ci": [lo, hi], "n_pairs": len(pairs),
            "equivalent_at_7pp": eq}


# ---------------------------------------------------------------------------
# (i) trimming attack
# ---------------------------------------------------------------------------

def trimming_attack(rows, model):
    mr = [r for r in rows if r["model"] == model]
    kept = list(mr)
    dropped_pairs = []
    trace = []
    max_drop_frac = 0.5
    total_units = len({(r["family_idx"], r["sibling_idx"]) for r in mr})
    for step in range(200):
        cells_seen = {r["cell"] for r in kept}
        pairs, _ = difficulty_pairs(kept, model)
        tst = tost_on_pairs(pairs, C.AUDIT_SEED + 21)
        trace.append({"step": step, "n_pairs": tst["n_pairs"],
                      "mean_pair_diff": tst["mean_pair_diff"],
                      "ci": tst["ci"], "equivalent_at_7pp": tst["equivalent_at_7pp"],
                      "n_units_kept": len({(r["family_idx"], r["sibling_idx"])
                                           for r in kept})})
        if tst["equivalent_at_7pp"]:
            break
        # drop the pair with the largest |diff|; remove BOTH siblings, all cells
        pairs_sorted = sorted(pairs, key=lambda p: -abs(p["diff"]))
        worst = pairs_sorted[0]
        fi, a, b = worst["family_idx"], worst["a"], worst["b"]
        dropped_pairs.append({"family_idx": fi, "siblings": [a, b],
                              "diff": worst["diff"]})
        kept = [r for r in kept if not (r["family_idx"] == fi and
                                        r["sibling_idx"] in (a, b))]
        n_units = len({(r["family_idx"], r["sibling_idx"]) for r in kept})
        if n_units < total_units * (1 - max_drop_frac):
            trace.append({"step": step + 1, "aborted":
                          "drop cap %.0f%% reached; TOST still fails"
                          % (max_drop_frac * 100)})
            break
        if cells_seen != set(C.ALL_CELLS):
            break
    n_fams_kept = len({r["family_idx"] for r in kept})
    taus = C.tau_block(kept, seed=C.AUDIT_SEED + 22)
    return {"model": model, "n_pairs_dropped": len(dropped_pairs),
            "n_units_dropped": total_units - len({(r["family_idx"], r["sibling_idx"])
                                                  for r in kept}),
            "total_units": total_units, "n_families_kept": n_fams_kept,
            "dropped_pairs": dropped_pairs, "tost_trace": trace,
            "final_tost": trace[-1], "taus_trimmed": taus}


# ---------------------------------------------------------------------------
# (ii) demeaned contrasts + difficulty stratification
# ---------------------------------------------------------------------------

def demeaned_contrasts(rows, model):
    mr = [r for r in rows if r["model"] == model]
    fam_n = {}
    for fi in sorted({r["family_idx"] for r in mr}):
        nrows = [r for r in mr if r["family_idx"] == fi and r["cell"] == "N"]
        fam_n[fi] = C.rate(nrows)

    demeaned = [dict(r, success=float(r["success"]) - fam_n[r["family_idx"]])
                for r in mr if r["cell"] in C.A_CELLS]

    def tau_struct(sub):
        return C.rate([r for r in sub if r["cell"] == "A10"]) - \
               C.rate([r for r in sub if r["cell"] == "A00"])

    def tau_trap(sub):
        return C.rate([r for r in sub if r["cell"] == "A01"]) - \
               C.rate([r for r in sub if r["cell"] == "A00"])

    out = {}
    unadj = {}
    for tag, rows_ in (("unadjusted", [r for r in mr if r["cell"] in C.A_CELLS]),
                       ("demeaned", demeaned)):
        blk = {}
        for name, fn in (("tau_struct", tau_struct), ("tau_trap", tau_trap)):
            p, lo, hi, _ = C.family_cluster_bootstrap(rows_, fn,
                                                      seed=C.AUDIT_SEED + 23)
            blk[name] = {"point": p, "ci": [lo, hi],
                         "sig": bool(lo > 0 or hi < 0)}
        out[tag] = blk
    ident = {k: abs(out["unadjusted"][k]["point"] - out["demeaned"][k]["point"])
             for k in ("tau_struct", "tau_trap")}
    out["identity_max_abs_diff"] = max(ident.values())
    out["identity_note"] = (
        "On the balanced grid every family contributes equally to every cell, "
        "so subtracting a per-family additive constant cancels exactly in any "
        "two-cell contrast (point estimate AND every bootstrap replicate). The "
        "demeaned contrast is algebraically identical to the unadjusted one; "
        "the max |diff| above verifies this numerically. Family-demeaning "
        "therefore CANNOT rescue or break tau_struct: difficulty can only "
        "matter through weighting/stratification, which is tested below.")

    # difficulty-stratified tau_struct: hard/easy halves by family N rate
    meds = float(np.median(list(fam_n.values())))
    hard = {fi for fi, v in fam_n.items() if v <= meds}
    strat = {}
    for tag, fams in (("hard_half", hard),
                      ("easy_half", set(fam_n) - hard)):
        sub = [r for r in mr if r["family_idx"] in fams]
        p, lo, hi, _ = C.family_cluster_bootstrap(sub, tau_struct,
                                                  seed=C.AUDIT_SEED + 24)
        strat[tag] = {"point": p, "ci": [lo, hi], "sig": bool(lo > 0 or hi < 0),
                      "n_families": len(fams),
                      "mean_N_rate": float(np.mean([fam_n[f] for f in fams]))}
    out["difficulty_stratified_tau_struct"] = strat
    out["fam_n_rates"] = {str(k): v for k, v in sorted(fam_n.items())}
    return out


# ---------------------------------------------------------------------------
# (iii) per-archetype breakdown
# ---------------------------------------------------------------------------

def per_archetype(rows, model):
    fams = C.load_families()
    mr = [r for r in rows if r["model"] == model]
    out = {}
    for r in mr:
        r["schema_key"] = fams[r["family_idx"]]["schema_key"]
        r["archetype"] = fams[r["family_idx"]]["archetype"]
    for schema in sorted({r["schema_key"] for r in mr}):
        sub = [r for r in mr if r["schema_key"] == schema]

        def tau_struct(s):
            return C.rate([x for x in s if x["cell"] == "A10"]) - \
                   C.rate([x for x in s if x["cell"] == "A00"])

        def tau_trap(s):
            return C.rate([x for x in s if x["cell"] == "A01"]) - \
                   C.rate([x for x in s if x["cell"] == "A00"])

        blk = {}
        for name, fn in (("tau_struct", tau_struct), ("tau_trap", tau_trap)):
            p, lo, hi, _ = C.family_cluster_bootstrap(sub, fn,
                                                      seed=C.AUDIT_SEED + 25)
            blk[name] = {"point": p, "ci": [lo, hi],
                         "sig": bool(lo > 0 or hi < 0)}
        blk["archetype"] = sub[0]["archetype"]
        blk["n_families"] = len({r["family_idx"] for r in sub})
        out[schema] = blk
    return out


def main():
    rows, files = C.load_rollout_rows()
    print("[difficulty] %d rollouts from %d files" % (len(rows), len(files)))
    result = {"env": C.env_block(), "tost_margin": TOST_MARGIN,
              "reference_failure": analysis_reference(), "models": {}}

    for model in ("qwen7b", "qwen3b"):
        print("[difficulty] === %s ===" % model)
        pairs, _ = difficulty_pairs(rows, model)
        base_tost = tost_on_pairs(pairs, C.AUDIT_SEED + 21)
        print("[difficulty] %s baseline TOST: mean=%.3f CI=[%.3f,%.3f] eq=%s"
              % (model, base_tost["mean_pair_diff"], base_tost["ci"][0],
                 base_tost["ci"][1], base_tost["equivalent_at_7pp"]))

        trim = None
        if model == "qwen7b":
            print("[difficulty] 7B trimming attack ...")
            trim = trimming_attack(rows, model)
            print("[difficulty] 7B dropped %d pairs; final TOST mean=%.3f "
                  "CI=[%.3f,%.3f] eq=%s; trimmed tau_struct=%.3f [%.3f,%.3f] "
                  "sig=%s"
                  % (trim["n_pairs_dropped"],
                     trim["final_tost"].get("mean_pair_diff", float("nan")),
                     trim["final_tost"].get("ci", [float("nan")] * 2)[0],
                     trim["final_tost"].get("ci", [float("nan")] * 2)[1],
                     trim["final_tost"].get("equivalent_at_7pp"),
                     trim["taus_trimmed"]["tau_struct"]["point"],
                     trim["taus_trimmed"]["tau_struct"]["ci"][0],
                     trim["taus_trimmed"]["tau_struct"]["ci"][1],
                     trim["taus_trimmed"]["tau_struct"]["sig"]))

        dem = demeaned_contrasts(rows, model)
        print("[difficulty] %s demean identity max|diff|=%.2e; stratified "
              "tau_struct hard=%.3f vs easy=%.3f"
              % (model, dem["identity_max_abs_diff"],
                 dem["difficulty_stratified_tau_struct"]["hard_half"]["point"],
                 dem["difficulty_stratified_tau_struct"]["easy_half"]["point"]))

        arch = per_archetype(rows, model)
        neg = [s for s, b in arch.items() if b["tau_struct"]["point"] < 0]
        print("[difficulty] %s per-schema tau_struct: %s; negative: %s"
              % (model,
                 {s: round(b["tau_struct"]["point"], 3) for s, b in arch.items()},
                 neg))

        result["models"][model] = {
            "baseline_tost": base_tost,
            "trimming_attack": trim,
            "demeaned": dem,
            "per_archetype": arch,
        }

    C.write_result("difficulty_robust.json", result)


def analysis_reference():
    path = "/work1/zixuan/outputs/agent_memory/pilot/analysis/difficulty_tost.json"
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None


if __name__ == "__main__":
    main()
