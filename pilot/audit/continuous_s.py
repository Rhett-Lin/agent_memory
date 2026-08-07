"""Gate B audit 3/4: continuous-S sensitivity.

The pilot buckets S via TF-token-cosine thresholds (with embedding calibration
documented as distribution-level). If the binary-S conclusions are real, they
should reproduce as monotone trends in the CONTINUOUS similarity measures --
and, crucially for the causal claim, uplift should depend on P (program
match), not on residual variation of S within a P stratum.

Per-unit uplift: success(cell, f, sib, seed) - success(N, f, sib, seed)
(same initial state / decode seed; only the injected memory differs).

For each model and each stratum:
  * within P=1 pairs (A11 + A10): regress uplift on sim_tf / sim_embed;
    the pilot claim predicts NO positive slope (P is fixed; if uplift rose
    with S inside P=1, surface similarity -- not program match -- would be
    doing the work).
  * within S=1 pairs (A11 + A01): same regressions; here the binary claim
    says P separates, S should not.
  * supplementary within S=0 (A10 + A00).
Slopes + family-cluster bootstrap CIs (refit per resample), Spearman rho with
CI, quintile mean-uplift trend, and a monotone-trend verdict.

Also reported: whether the binary-S headline results (tau_struct, tau_PxS,
replay premium CIs) hold on this dataset (sanity anchor for the verdict).

Usage:  python continuous_s.py
"""

import numpy as np

import common as C

MEM_CELLS = ["A00", "A01", "A10", "A11"]


def ols_slope(x, y):
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    if len(x) < 3 or x.std() == 0:
        return float("nan"), float("nan")
    X = np.stack([np.ones_like(x), x], axis=1)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    yhat = X @ beta
    ss_res = float(((y - yhat) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    return float(beta[1]), r2


def spearman(x, y):
    def rank(v):
        order = np.argsort(np.argsort(v))
        return order.astype(float) + 1.0
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) < 3 or x.std() == 0 or y.std() == 0:
        return float("nan")
    return float(np.corrcoef(rank(x), rank(y))[0, 1])


def build_uplift_units(rows, model, sim):
    mr = [r for r in rows if r["model"] == model]
    n_map = {(r["family_idx"], r["sibling_idx"], r["seed"]): r
             for r in mr if r["cell"] == "N"}
    units = []
    for r in mr:
        if r["cell"] not in MEM_CELLS:
            continue
        key = (r["family_idx"], r["sibling_idx"], r["seed"])
        n = n_map.get(key)
        srow = sim.get(r["memory_id"] or "")
        if n is None or srow is None:
            continue
        units.append({
            "family_idx": r["family_idx"], "sibling_idx": r["sibling_idx"],
            "seed": r["seed"], "cell": r["cell"], "P": srow["P"], "S": srow["S"],
            "sim_tf": srow["sim_tf"], "sim_embed": srow["sim_embed"],
            "uplift": float(r["success"]) - float(n["success"]),
        })
    return units


def regress_stratum(units, metric, seed):
    def slope_stat(sub):
        s, _ = ols_slope([u[metric] for u in sub], [u["uplift"] for u in sub])
        return s

    def rho_stat(sub):
        return spearman([u[metric] for u in sub], [u["uplift"] for u in sub])

    p, lo, hi, _ = C.family_cluster_bootstrap(units, slope_stat, seed=seed)
    slope, r2 = ols_slope([u[metric] for u in units], [u["uplift"] for u in units])
    pr, lor, hir, _ = C.family_cluster_bootstrap(units, rho_stat, seed=seed + 1)
    qs = quintile_trend(units, metric)
    return {"metric": metric, "n": len(units),
            "slope": slope, "slope_ci": [lo, hi], "r2": r2,
            "spearman": pr, "spearman_ci": [lor, hir],
            "slope_sig": bool(lo > 0 or hi < 0),
            "quintile_mean_uplift": qs}


def quintile_trend(units, metric, n_bins=5):
    xs = np.asarray([u[metric] for u in units], float)
    ys = np.asarray([u["uplift"] for u in units], float)
    if len(xs) < n_bins * 10:
        return None
    edges = np.quantile(xs, np.linspace(0, 1, n_bins + 1))
    out = []
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        m = (xs >= lo) & (xs <= hi if i == n_bins - 1 else xs < hi)
        if m.sum() == 0:
            out.append(None)
        else:
            out.append({"x_range": [float(lo), float(hi)], "n": int(m.sum()),
                        "mean_uplift": float(ys[m].mean())})
    return out


def monotone_verdict(reg_list):
    """Check uplift is non-decreasing across quintiles (for the metric that
    defines S) and whether any slope is significantly non-zero."""
    v = {}
    for tag, reg in reg_list.items():
        entry = {"slope_sig": reg["slope_sig"], "slope": reg["slope"],
                 "slope_ci": reg["slope_ci"]}
        q = reg["quintile_mean_uplift"]
        if q:
            means = [b["mean_uplift"] if b else None for b in q]
            entry["quintile_means"] = means
            entry["weakly_monotone"] = all(
                b is None or a is None or b >= a - 1e-9
                for a, b in zip(means, means[1:]))
        v[tag] = entry
    return v


def overlap_band_contrast(units, metric, cells, seed):
    """Sharpest P-vs-S discrimination: restrict to the overlap of the two
    cells' metric supports; if P (not S) drives uplift, the P=1 cell must
    still dominate inside the band where S is matched."""
    a = [u for u in units if u["cell"] == cells[0]]
    b = [u for u in units if u["cell"] == cells[1]]
    if not a or not b:
        return None
    lo = max(min(u[metric] for u in a), min(u[metric] for u in b))
    hi = min(max(u[metric] for u in a), max(u[metric] for u in b))
    if hi <= lo:
        return {"overlap_band": None,
                "note": "metric supports disjoint -- binary bucket boundary "
                        "coincides with metric boundary (no within-band test)"}
    band = [u for u in units if lo <= u[metric] <= hi]
    if not band:
        return None

    def diff_stat(sub):
        xa = [u for u in sub if u["cell"] == cells[0]]
        xb = [u for u in sub if u["cell"] == cells[1]]
        if not xa or not xb:
            return float("nan")
        return float(np.mean([u["uplift"] for u in xa])
                     - np.mean([u["uplift"] for u in xb]))

    p, lo_ci, hi_ci, _ = C.family_cluster_bootstrap(band, diff_stat, seed=seed)
    return {"metric": metric, "cells": cells, "overlap_band": [float(lo), float(hi)],
            "n_in_band": len(band),
            "n_pos_in_band": len([u for u in band if u["cell"] == cells[0]]),
            "uplift_diff_in_band": p, "ci": [lo_ci, hi_ci],
            "sig": bool(lo_ci > 0 or hi_ci < 0)}


def main():
    rows, files = C.load_rollout_rows()
    sim = C.load_sim_rows()
    print("[cont-S] %d rollouts; %d sim rows" % (len(rows), len(sim)))
    result = {"env": C.env_block(), "strata": {}, "binary_anchor": {},
              "definition": {
                  "uplift": "success(cell,f,sib,seed) - success(N,f,sib,seed)",
                  "claim_prediction":
                      "within fixed P, uplift must NOT increase with S; "
                      "binary-S contrasts should reappear as (non-decreasing) "
                      "trends in continuous S at the stratum boundaries"}}

    for model in ("qwen3b", "qwen7b"):
        units = build_uplift_units(rows, model, sim)
        result["binary_anchor"][model] = C.tau_block(
            [r for r in rows if r["model"] == model], seed=C.AUDIT_SEED + 31)
        print("[cont-S] %s: %d uplift units" % (model, len(units)))
        strata = {
            "P1 (A11+A10)": [u for u in units if u["P"] == 1],
            "S1 (A11+A01)": [u for u in units if u["S"] == 1],
            "S0 (A10+A00)": [u for u in units if u["S"] == 0],
        }
        mres = {}
        for sname, su in strata.items():
            sres = {}
            for metric in ("sim_tf", "sim_embed"):
                reg = regress_stratum(su, metric, seed=C.AUDIT_SEED + 32)
                sres[metric] = reg
                print("[cont-S] %s %-13s %-9s slope=%+.3f [%+.3f,%+.3f] r2=%.3f "
                      "rho=%+.3f" % (model, sname, metric, reg["slope"],
                                     reg["slope_ci"][0], reg["slope_ci"][1],
                                     reg["r2"], reg["spearman"]))
            mres[sname] = sres
        # verdicts per stratum
        verdicts = {}
        for sname, sres in mres.items():
            verdicts[sname] = monotone_verdict(
                {"%s/%s" % (sname, met): sres[met]
                 for met in ("sim_tf", "sim_embed")})
        # overlap-band P-contrasts at matched continuous S
        bands = {}
        for sname, cells in (("S1 (A11+A01)", ("A11", "A01")),
                             ("S0 (A10+A00)", ("A10", "A00"))):
            su = strata[sname]
            for metric in ("sim_tf", "sim_embed"):
                band = overlap_band_contrast(su, metric, cells,
                                             seed=C.AUDIT_SEED + 33)
                if band:
                    bands["%s/%s" % (sname, metric)] = band
                    if band.get("overlap_band"):
                        print("[cont-S] %s band %s %s: [%0.3f,%0.3f] n=%d "
                              "upliftDiff(%s-%s)=%+.3f [%+.3f,%+.3f]"
                              % (model, sname, metric,
                                 band["overlap_band"][0], band["overlap_band"][1],
                                 band["n_in_band"], cells[0], cells[1],
                                 band["uplift_diff_in_band"], band["ci"][0],
                                 band["ci"][1]))
                    else:
                        print("[cont-S] %s band %s %s: %s"
                              % (model, sname, metric, band.get("note")))
        result["strata"][model] = {"regressions": mres, "verdict": verdicts,
                                   "overlap_band_contrasts": bands}

    C.write_result("continuous_s.json", result)


if __name__ == "__main__":
    main()
