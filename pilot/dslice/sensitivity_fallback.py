"""H-DC post-hoc sensitivity: provenance-stratified E1 (oracle fallback).

External review (auto-review-loop round 1, thread 019fe135) flagged that
188/640 dslice/raw_matched source memories are oracle-plan reconstructions
(raw_cards_map oracle_fallback=True; see build_dslice_cards.py).  The
pre-registered primary E1 pools both provenance strata; this script reports
the stratified contrast so the paper can state how much of the pooled
effect comes from authentic model-generated source trajectories.

Procedure: identical to analyze_dslice.py (aligned family-cluster bootstrap,
2000 reps, same seed), except rollout rows are restricted per stratum by
joining meta.memory_id to dslice/cards_map.jsonl:oracle_fallback.  The
family universe per stratum is every family contributing >=1 stratum row to
either system; within a resample each family pools the rows it has (same
pooled-rate semantics as the primary analysis).  Also reports the post-hoc
cross-model difference E1(7b)-E1(3b) on the full grid (aligned resample).

POST-HOC: not part of the Part IV-A Holm family (m=6).  Run from pilot/:
  python dslice/sensitivity_fallback.py --config configs/pilot_7b.yaml
"""

import argparse
import glob
import json
import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_PILOT = os.path.dirname(_HERE)
sys.path.insert(0, _PILOT)

from generate_families import load_config  # noqa: E402

DEFAULT_CONFIG = os.path.join(_PILOT, "configs", "pilot_7b.yaml")
SYSTEMS = ["dslice", "raw_matched"]
MODELS = ["qwen7b", "qwen3b"]
NBOOT = 2000
CELLS_R = ["A10", "A11"]  # tau_replaylike cells


def load_rows(cfg, model, system):
    out = cfg["paths"]["output_root"]
    pat = os.path.join(out, "rollouts_hc_%s_%s_shard*-of-*.jsonl"
                       % (system, model))
    rows = []
    for fn in sorted(glob.glob(pat)):
        with open(fn) as f:
            for line in f:
                r = json.loads(line)
                m = r.get("meta", {})
                if m.get("model") != model or m.get("system") != system:
                    continue
                rows.append({"family_idx": m["family_idx"],
                             "sibling_idx": m["sibling_idx"],
                             "seed": m["seed"], "cell": m["cell"],
                             "memory_id": m.get("memory_id"),
                             "success": bool(r["success"])})
    return rows


def family_counts(rows, fpos, fam_universe):
    succ = {c: np.zeros(len(fam_universe)) for c in CELLS_R}
    n = {c: np.zeros(len(fam_universe)) for c in CELLS_R}
    for r in rows:
        if r["cell"] not in CELLS_R or r["family_idx"] not in fpos:
            continue
        succ[r["cell"]][fpos[r["family_idx"]]] += r["success"]
        n[r["cell"]][fpos[r["family_idx"]]] += 1
    return succ, n


def tau_rl_at(agg, idx):
    succ, n = agg
    d10, d11 = n["A10"][idx].sum(), n["A11"][idx].sum()
    if not d10 or not d11:
        return float("nan")
    return succ["A11"][idx].sum() / d11 - succ["A10"][idx].sum() / d10


def boot_ci(deltas, point):
    b = np.array(deltas)
    b = b[np.isfinite(b)]
    return {"point": float(point),
            "ci95": [float(np.percentile(b, 2.5)),
                     float(np.percentile(b, 97.5))],
            "p_one_sided_pos": float(np.mean(b <= 0)),
            "n_boot_ok": int(len(b))}


def stratum_e1(syms, fam_universe, seed):
    """Aligned bootstrap of E1 = tau_rl(dslice) - tau_rl(raw_matched)."""
    fpos = {f: i for i, f in enumerate(fam_universe)}
    agg = {s: family_counts(syms[s], fpos, fam_universe) for s in SYSTEMS}
    rng = np.random.default_rng(seed)
    F = len(fam_universe)
    e1, taus = [], {s: [] for s in SYSTEMS}
    for _ in range(NBOOT):
        idx = rng.integers(0, F, F)
        t = {s: tau_rl_at(agg[s], idx) for s in SYSTEMS}
        e1.append(t["dslice"] - t["raw_matched"])
        for s in SYSTEMS:
            taus[s].append(t[s])
    full_idx = np.arange(F)
    tf = {s: tau_rl_at(agg[s], full_idx) for s in SYSTEMS}
    return {"E1": boot_ci(e1, tf["dslice"] - tf["raw_matched"]),
            "tau_rl": {s: boot_ci(taus[s], tf[s]) for s in SYSTEMS},
            "families_ok": F}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    args = ap.parse_args()
    cfg = load_config(args.config)
    seed = cfg.get("analysis", {}).get("bootstrap_seed", 12345)

    fb = {}
    with open(os.path.join(_HERE, "cards_map.jsonl")) as f:
        for line in f:
            r = json.loads(line)
            fb[r["memory_id"]] = bool(r["oracle_fallback"])

    rows = {m: {s: load_rows(cfg, m, s) for s in SYSTEMS} for m in MODELS}
    out = {"note": "post-hoc, outside the Part IV-A Holm family (m=6)",
           "seed": seed, "nboot": NBOOT,
           "memory_provenance": {
               "total_cards": len(fb),
               "oracle_fallback_cards": int(sum(fb.values()))},
           "strata": {}}

    for label, want in (("model_generated", False), ("oracle_fallback", True)):
        mems = {mid for mid, v in fb.items() if v == want}
        out["strata"][label] = {"cards": len(mems), "per_model": {}}
        for m in MODELS:
            syms = {s: [r for r in rows[m][s]
                        if r["memory_id"] in mems] for s in SYSTEMS}
            # family-cluster bootstrap over every family that contributes
            # >=1 stratum row; within a resample, families pool the rows
            # they have (same pooled-rate semantics as analyze_dslice.py).
            good = sorted({r["family_idx"] for s in SYSTEMS
                           for r in syms[s] if r["cell"] in CELLS_R})
            res = stratum_e1(syms, good, seed)
            n_rows = {s: {c: sum(1 for r in syms[s] if r["cell"] == c)
                          for c in CELLS_R} for s in SYSTEMS}
            n_cards = len({r["memory_id"] for s in SYSTEMS
                           for r in syms[s] if r["cell"] in CELLS_R})
            out["strata"][label]["per_model"][m] = {
                **res, "rows": n_rows, "a10_a11_cards": n_cards}
            c = res["E1"]
            print("[%s|%s] families=%d  E1=%+.3f [%+.3f,%+.3f] p1s=%.4f  "
                  "(tau_rl dslice=%+.3f raw_matched=%+.3f)"
                  % (m, label, res["families_ok"], c["point"], *c["ci95"],
                     c["p_one_sided_pos"],
                     res["tau_rl"]["dslice"]["point"],
                     res["tau_rl"]["raw_matched"]["point"]))

    # post-hoc cross-model difference on the FULL grid, one aligned resample
    fam_all = sorted({r["family_idx"] for m in MODELS for s in SYSTEMS
                      for r in rows[m][s] if r["cell"] in CELLS_R})
    aggs = {m: {s: family_counts(rows[m][s],
                                 {f: i for i, f in enumerate(fam_all)},
                                 fam_all)
                for s in SYSTEMS} for m in MODELS}
    rng = np.random.default_rng(seed)
    F = len(fam_all)
    diffs, e1pts = [], {}
    for _ in range(NBOOT):
        idx = rng.integers(0, F, F)
        e1 = {m: tau_rl_at(aggs[m]["dslice"], idx)
              - tau_rl_at(aggs[m]["raw_matched"], idx) for m in MODELS}
        diffs.append(e1["qwen7b"] - e1["qwen3b"])
    full_idx = np.arange(F)
    for m in MODELS:
        e1pts[m] = (tau_rl_at(aggs[m]["dslice"], full_idx)
                    - tau_rl_at(aggs[m]["raw_matched"], full_idx))
    out["cross_model_E1_diff"] = boot_ci(diffs, e1pts["qwen7b"]
                                         - e1pts["qwen3b"])
    d = out["cross_model_E1_diff"]
    print("[cross-model] E1(7b)-E1(3b) = %+.3f [%+.3f,%+.3f]  "
          "(E1 7b=%+.3f 3b=%+.3f)"
          % (d["point"], *d["ci95"], e1pts["qwen7b"], e1pts["qwen3b"]))

    # post-hoc DIRECT provenance interaction: E1(oracle) - E1(model_generated).
    # Point = difference of the stratum point estimates reported in "strata";
    # CI from an aligned cluster bootstrap over the UNION family universe
    # (details below).
    out["provenance_interaction"] = {"per_model": {}}
    for m in MODELS:
        syms, fams = {}, {}
        for label, want in (("model_generated", False),
                            ("oracle_fallback", True)):
            mems = {mid for mid, v in fb.items() if v == want}
            syms[label] = {s: [r for r in rows[m][s]
                               if r["memory_id"] in mems] for s in SYSTEMS}
            fams[label] = sorted({r["family_idx"] for s in SYSTEMS
                                  for r in syms[label][s]
                                  if r["cell"] in CELLS_R})
        # aligned cluster bootstrap over the UNION family universe (round-3
        # review): one resample index for both strata; families absent from
        # a stratum contribute zero successes AND zero counts there, so
        # within-resample each stratum pools exactly its own rows and the
        # full-index point equals the difference of the stratum estimates
        # reported in "strata".  16 of the 40 families occur in both
        # strata; resampling the two stratum-specific universes
        # independently (earlier draft) would zero the shared-family
        # covariance and is discontinued.  Restricting to the common 16
        # changes the estimand (shifts the stratum E1s) and stays
        # discarded.
        fam_union = sorted(set(fams["model_generated"])
                           | set(fams["oracle_fallback"]))
        fpos_u = {f: i for i, f in enumerate(fam_union)}
        aggs_u = {label: {s: family_counts(syms[label][s], fpos_u,
                                           fam_union) for s in SYSTEMS}
                  for label in syms}
        rng = np.random.default_rng(seed)
        F = len(fam_union)
        ideltas = []
        for _ in range(NBOOT):
            idx = rng.integers(0, F, F)
            e1 = {label: (tau_rl_at(aggs_u[label]["dslice"], idx)
                          - tau_rl_at(aggs_u[label]["raw_matched"], idx))
                  for label in aggs_u}
            ideltas.append(e1["oracle_fallback"] - e1["model_generated"])
        full = np.arange(F)
        e1f = {label: (tau_rl_at(aggs_u[label]["dslice"], full)
                       - tau_rl_at(aggs_u[label]["raw_matched"], full))
               for label in aggs_u}
        ipt = e1f["oracle_fallback"] - e1f["model_generated"]
        irec = {**boot_ci(ideltas, ipt),
                "families": {"union": F,
                             "model_generated": len(fams["model_generated"]),
                             "oracle_fallback": len(fams["oracle_fallback"]),
                             "both": len(set(fams["model_generated"])
                                        & set(fams["oracle_fallback"]))},
                "E1_oracle": float(e1f["oracle_fallback"]),
                "E1_model_generated": float(e1f["model_generated"]),
                "a10_a11_cards": {
                    label: len({r["memory_id"] for s in SYSTEMS
                                for r in syms[label][s]
                                if r["cell"] in CELLS_R})
                    for label in syms}}
        out["provenance_interaction"]["per_model"][m] = irec
        print("[interaction|%s] fam union=%d (mg=%d or=%d both=%d)  "
              "E1(or)-E1(mg)=%+.3f [%+.3f,%+.3f]  (E1 or=%+.3f mg=%+.3f)"
              % (m, F, len(fams["model_generated"]),
                 len(fams["oracle_fallback"]), irec["families"]["both"],
                 ipt, *irec["ci95"],
                 e1f["oracle_fallback"], e1f["model_generated"]))

    out_path = os.path.join(_HERE, "HDC_SENSITIVITY_FALLBACK.json")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=1, sort_keys=True)
    print("-> %s" % out_path)


if __name__ == "__main__":
    main()
