"""H-DC analysis (GATE_PROTOCOL.md Part IV as amended by Part IV-A).

Arms per model (40 pilot families x 4 siblings x 4 seeds, A cells = 640 rows):
  dslice      rollouts_hc_dslice_<model>_shard*-of-*.jsonl
  raw_matched rollouts_hc_raw_matched_<model>_shard*-of-*.jsonl   (primary)
  raw(300)    rollouts_hc_raw_<model>_shard*-of-*.jsonl           (secondary)
  procedural  pilot file A cells (reference)
  N, Q        pilot file rows, shared by every system (as in Part II)

Statistics: aligned family-cluster bootstrap (identical family resample for
all systems of one model), 2000 reps, seed = analysis.bootstrap_seed.
  tau_replaylike = r(A11)-r(A10); tau_trap = r(A01)-r(A00);
  HFR = P(Y_N=1, Y_A01=0) paired by (family, sibling, seed).

Primary Holm family (m=6, Part IV-A A4):
  E1-7b / E1-3b : tau_rl(dslice) - tau_rl(raw_matched), one-sided p = P(d<=0)
  E2-7b / E2-3b : tau_rl(dslice), two-sided bootstrap sign p
  E3a-7b/ E3a-3b: noninferiority of HFR(dslice)-HFR(raw_matched),
                  p_noninf = P(d* >= +5pp); bound = 95th pct of boot deltas
Secondary (CI only): E1 vs raw(300), tau_trap diff noninferiority
(p = P(d* <= -5pp)), tau_struct(dslice), per-cell rates.

A5 GO restated: >=1 model with Holm-adj E1 SIG+ and point estimate >= +5pp
AND that model's E3a noninferiority holds (upper95 < +5pp).  NO_GO: E1 both
Holm n.s., or a model with significant E1 violates E3a/tau_trap margins.

A6: config_hash / model snapshot / harness-file identity between historical
raw(300)-7b rollouts and the new grids is asserted and reported.

Outputs: pilot/dslice/HDC_RESULTS.json   Run from pilot/:
  python dslice/analyze_dslice.py --config configs/pilot_7b.yaml
"""

import argparse
import glob
import json
import os
import subprocess
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_PILOT = os.path.dirname(_HERE)
sys.path.insert(0, _PILOT)

from generate_families import load_config  # noqa: E402

DEFAULT_CONFIG = os.path.join(_PILOT, "configs", "pilot_7b.yaml")
CELLS = ["A00", "A01", "A10", "A11", "N", "Q"]
SYSTEMS = ["procedural", "raw", "raw_matched", "dslice"]
MODELS = ["qwen7b", "qwen3b"]
NBOOT = 2000
MARGIN = 0.05
HARNESS_FILES = ["pilot/harness.py", "pilot/env_relationalops.py",
                 "pilot/generate_families.py", "pilot/run_pilot.py",
                 "pilot/systems/run_hc_grid.py", "pilot/configs/pilot_7b.yaml"]


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------

def _rows_from(files, model, system_filter):
    rows, metas = [], []
    for fn in files:
        with open(fn) as f:
            for line in f:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                m = r.get("meta", {})
                if m.get("model") != model:
                    continue
                if m.get("system", "procedural") != system_filter:
                    continue
                rows.append({"family_idx": m["family_idx"],
                             "sibling_idx": m["sibling_idx"],
                             "seed": m["seed"], "cell": m["cell"],
                             "success": bool(r["success"])})
                metas.append({"config_hash": m.get("config_hash"),
                              "git_commit": m.get("git_commit"),
                              "env_versions": m.get("env_versions")})
    return rows, metas


def load_model_systems(cfg, model):
    out = cfg["paths"]["output_root"]
    syms = {}
    pat = os.path.join(out, "rollouts_%s_shard*-of-*.jsonl" % model)
    pilot_files = [f for f in sorted(glob.glob(pat)) if "_hc_" not in f]
    prows, pmetas = _rows_from(pilot_files, model, "procedural")
    nq = [r for r in prows if r["cell"] in ("N", "Q")]
    metas = {"procedural_pilot": pmetas[:1]}
    for s in SYSTEMS:
        if s == "procedural":
            syms[s] = prows
            continue
        pat = os.path.join(out, "rollouts_hc_%s_%s_shard*-of-*.jsonl"
                           % (s, model))
        rows, mt = _rows_from(sorted(glob.glob(pat)), model, s)
        syms[s] = [r for r in rows if r["cell"] not in ("N", "Q")] + nq
        metas[s] = mt[:1]
    return syms, metas


# ---------------------------------------------------------------------------
# aggregation + bootstrap
# ---------------------------------------------------------------------------

def family_counts(rows, fpos):
    succ = {c: np.zeros(len(fpos)) for c in CELLS}
    n = {c: np.zeros(len(fpos)) for c in CELLS}
    unit = {}
    for r in rows:
        succ[r["cell"]][fpos[r["family_idx"]]] += r["success"]
        n[r["cell"]][fpos[r["family_idx"]]] += 1
        unit[(r["family_idx"], r["sibling_idx"], r["seed"], r["cell"])] = \
            r["success"]
    hf_num = np.zeros(len(fpos))
    hf_den = np.zeros(len(fpos))
    for (f, s, sd, c), ok in unit.items():
        if c != "N":
            continue
        a01 = unit.get((f, s, sd, "A01"))
        if a01 is None:
            continue
        hf_den[fpos[f]] += 1
        if ok and not a01:
            hf_num[fpos[f]] += 1
    return succ, n, hf_num, hf_den


def _rate(succ, n, cell, idx):
    d = n[cell][idx].sum()
    return succ[cell][idx].sum() / d if d else float("nan")


def stats_at(agg, idx):
    succ, n, hf_num, hf_den = agg
    r = {c: _rate(succ, n, c, idx) for c in CELLS}
    hfr = hf_num[idx].sum() / hf_den[idx].sum() if hf_den[idx].sum() \
        else float("nan")
    return {"rates": r, "tau_struct": r["A10"] - r["A00"],
            "tau_trap": r["A01"] - r["A00"], "tau_rl": r["A11"] - r["A10"],
            "hfr": hfr}


CONTRASTS = [  # name, fn(per-system stats dict)
    ("E1",        lambda p: p["dslice"]["tau_rl"] - p["raw_matched"]["tau_rl"]),
    ("E1_300",    lambda p: p["dslice"]["tau_rl"] - p["raw"]["tau_rl"]),
    ("E2",        lambda p: p["dslice"]["tau_rl"]),
    ("E3a_HFR",   lambda p: p["dslice"]["hfr"] - p["raw_matched"]["hfr"]),
    ("E3a_HFR300", lambda p: p["dslice"]["hfr"] - p["raw"]["hfr"]),
    ("dTTRAP",    lambda p: p["dslice"]["tau_trap"]
                 - p["raw_matched"]["tau_trap"]),
    ("dTTRAP300", lambda p: p["dslice"]["tau_trap"] - p["raw"]["tau_trap"]),
    ("TSTRUCT_DS", lambda p: p["dslice"]["tau_struct"]),
]


def analyze_model(syms, fam_universe, seed):
    fpos = {f: i for i, f in enumerate(fam_universe)}
    agg = {s: family_counts(syms[s], fpos) for s in SYSTEMS}
    rng = np.random.default_rng(seed)
    F = len(fam_universe)
    boot = {k: [] for k, _ in CONTRASTS}
    for _ in range(NBOOT):
        idx = rng.integers(0, F, F)
        per = {s: stats_at(agg[s], idx) for s in SYSTEMS}
        for k, fn in CONTRASTS:
            boot[k].append(fn(per))
    full_idx = np.arange(F)
    full = {s: stats_at(agg[s], full_idx) for s in SYSTEMS}
    out = {}
    for k, fn in CONTRASTS:
        b = np.array(boot[k])
        point = fn(full)
        lo, hi = np.percentile(b, [2.5, 97.5])
        out[k] = {"point": float(point), "ci95": [float(lo), float(hi)],
                  "upper95": float(np.percentile(b, 95)),
                  "lower95": float(np.percentile(b, 5)),
                  "p_one_sided_pos": float(np.mean(b <= 0)),
                  "p_two_sided": float(2 * min(np.mean(b <= 0),
                                               np.mean(b >= 0))),
                  "p_noninf_plus": float(np.mean(b >= MARGIN)),
                  "p_noninf_minus": float(np.mean(b <= -MARGIN))}
    return out, full


def holm(pvals):
    order = sorted(range(len(pvals)), key=lambda i: pvals[i][1])
    m = len(pvals)
    adj, running = {}, 0.0
    for rank, i in enumerate(order):
        val = min(1.0, (m - rank) * pvals[i][1])
        running = max(running, val)
        adj[pvals[i][0]] = running
    return adj


# ---------------------------------------------------------------------------
# A6: execution-environment consistency across arms (report only)
# ---------------------------------------------------------------------------

def a6_report(metas_all):
    rep = {}
    for model, metas in metas_all.items():
        hashes = {k: (v[0]["config_hash"] if v else None)
                  for k, v in metas.items()}
        envs = {k: (v[0]["env_versions"] if v else None)
                for k, v in metas.items()}
        key = next((k for k in ("raw", "procedural_pilot") if metas.get(k)),
                   None)
        commits = {k: (v[0]["git_commit"] if v else None)
                   for k, v in metas.items()}
        rep[model] = {"config_hashes": hashes, "env_versions": envs,
                      "git_commits": commits,
                      "config_hash_uniform":
                          len({h for h in hashes.values() if h}) <= 1}
    # harness-file identity between the historical commit and HEAD
    try:
        repo = subprocess.check_output(
            ["git", "-C", os.path.dirname(_PILOT), "rev-parse", "--show-toplevel"],
            text=True).strip()
        raw_commit = rep["qwen7b"]["git_commits"].get("raw")
        if raw_commit:
            diff = subprocess.check_output(
                ["git", "-C", repo, "diff", "--name-only",
                 raw_commit, "HEAD", "--"] + HARNESS_FILES, text=True).strip()
            rep["harness_files_changed_since_raw7b"] = diff.splitlines() \
                if diff else []
    except Exception as e:
        rep["git_check_error"] = repr(e)
    return rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    args = ap.parse_args()
    cfg = load_config(args.config)
    seed = cfg.get("analysis", {}).get("bootstrap_seed", 12345)

    results, metas_all = {}, {}
    for model in MODELS:
        syms, metas = load_model_systems(cfg, model)
        metas_all[model] = metas
        counts = {s: len([r for r in rows if r["cell"] not in ("N", "Q")])
                  for s, rows in syms.items()}
        fam_universe = sorted({r["family_idx"] for rows in syms.values()
                               for r in rows})
        print("[%s] A-cell rows per system: %s  families=%d"
              % (model, counts, len(fam_universe)))
        missing = {s: c for s, c in counts.items()
                   if c < 40 * 4 * 4}
        if missing:
            raise SystemExit(
                "[%s] incomplete grids %s -- H-DC analysis is only valid on "
                "complete data; refusing to emit numbers" % (model, missing))
        res, full = analyze_model(syms, fam_universe, seed)
        bad = [k for k, v in res.items()
               if not (v["point"] == v["point"]) or
               not np.isfinite(v["ci95"]).all()]
        if bad:
            raise SystemExit("[%s] non-finite estimates in %s; abort"
                             % (model, bad))
        results[model] = {"contrasts": res,
                          "rates": {s: {c: float(v) for c, v in
                                        full[s]["rates"].items()}
                                    for s in SYSTEMS}}

    # Holm over the primary family (Part IV-A A4)
    prim = [("E1-7b", results["qwen7b"]["contrasts"]["E1"]["p_one_sided_pos"]),
            ("E1-3b", results["qwen3b"]["contrasts"]["E1"]["p_one_sided_pos"]),
            ("E2-7b", results["qwen7b"]["contrasts"]["E2"]["p_two_sided"]),
            ("E2-3b", results["qwen3b"]["contrasts"]["E2"]["p_two_sided"]),
            ("E3a-7b", results["qwen7b"]["contrasts"]["E3a_HFR"]
             ["p_noninf_plus"]),
            ("E3a-3b", results["qwen3b"]["contrasts"]["E3a_HFR"]
             ["p_noninf_plus"])]
    adj = holm(prim)
    results["holm_primary"] = {"raw_p": dict(prim), "holm_adj": adj}
    results["margin_pp"] = MARGIN * 100
    results["a6"] = a6_report(metas_all)

    # A5 verdict
    verdicts = {}
    for tag, model in (("7b", "qwen7b"), ("3b", "qwen3b")):
        c = results[model]["contrasts"]
        e1_sig = adj["E1-%s" % tag] < 0.05 and c["E1"]["point"] > 0
        e1_big = c["E1"]["point"] >= MARGIN
        e3a_ok = c["E3a_HFR"]["upper95"] < MARGIN
        ttrap_ok = c["dTTRAP"]["lower95"] > -MARGIN
        verdicts[model] = {"E1_holm_sig_pos": bool(e1_sig),
                           "E1_point_ge_5pp": bool(e1_big),
                           "E3a_noninf_ok": bool(e3a_ok),
                           "ttrap_noninf_ok": bool(ttrap_ok)}
    go_models = [m for m, v in verdicts.items()
                 if v["E1_holm_sig_pos"] and v["E1_point_ge_5pp"]
                 and v["E3a_noninf_ok"] and v["ttrap_noninf_ok"]]
    e1_both_ns = all(adj["E1-%s" % t] >= 0.05 for t in ("7b", "3b"))
    results["verdict"] = {"per_model": verdicts, "go_models": go_models,
                          "GO": bool(go_models), "E1_both_holm_ns": e1_both_ns}

    out_path = os.path.join(_HERE, "HDC_RESULTS.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=1, sort_keys=True, default=str)
    print("\n==== H-DC primary (Holm m=6) ====")
    for name, p in prim:
        print("  %-8s p=%.4f  p_holm=%.4f" % (name, p, adj[name]))
    for model in MODELS:
        c = results[model]["contrasts"]
        print("[%s] E1=%.3f [%.3f,%.3f]  E2=%.3f  dHFR=%.3f (u95 %.3f)  "
              "dTTRAP=%.3f (l95 %.3f)"
              % (model, c["E1"]["point"], *c["E1"]["ci95"],
                 c["E2"]["point"], c["E3a_HFR"]["point"],
                 c["E3a_HFR"]["upper95"], c["dTTRAP"]["point"],
                 c["dTTRAP"]["lower95"]))
    print("verdict:", json.dumps(results["verdict"], indent=1))
    print("-> %s" % out_path)


if __name__ == "__main__":
    main()
