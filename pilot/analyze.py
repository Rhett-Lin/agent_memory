"""Analysis for the CausalMemBench mini-pilot (SPEC.md section 7).

Reads rollout JSONL files (+ sealed metadata) and produces the four core
figures and the statistical tables required for Gate A:

  fig1_cells_success.png   P x S four-cell success rates per model,
                           family-cluster bootstrap 95% CIs (N/Q as reference)
  fig2_uplift.png          risk difference of each A cell vs N and vs Q (+CI)
  fig3_sim_uplift.png      continuous similarity vs paired uplift scatter
  fig4_harmful_flip.png    paired harmful flip P(N=1 & A01=0) per model
  token_len_balance.csv    six-cell memory token-length balance table
  difficulty_tost.json     no-memory sibling difficulty equivalence test
  compliance_summary.csv   memory-engagement heuristic summary
  summary.json             all rates/CIs + oracle/sim gate reports

Statistics: family-cluster bootstrap (families resampled with replacement);
paired uplift uses (family, sibling, seed) matching -- the same initial state
and decode seed, only the injected memory differs. Equivalence uses the
confidence-interval formulation of TOST (CI within +/- margin).

Usage:
  python analyze.py --config configs/pilot.yaml \
      --rollouts "outputs/agent_memory/pilot/smoke/rollouts_*.jsonl" \
      --out outputs/agent_memory/pilot/smoke/analysis
"""

import argparse
import csv
import glob
import json
import math
import os
import sys
from collections import defaultdict

import numpy as np

A_CELLS = ["A00", "A01", "A10", "A11"]
ALL_CELLS = ["A00", "A01", "A10", "A11", "N", "Q"]
MEM_CELLS = ["A00", "A01", "A10", "A11", "Q"]

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from generate_families import load_config


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------

def load_rollouts(patterns):
    files = []
    for p in patterns:
        files.extend(glob.glob(p))
    files = sorted(set(files))
    rows = []
    for fn in files:
        with open(fn) as f:
            for line in f:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                m = r.get("meta", {})
                rows.append({
                    "file": fn,
                    "model": m.get("model") or m.get("model_key") or "unknown",
                    "family_idx": m["family_idx"], "sibling_idx": m["sibling_idx"],
                    "cell": m["cell"], "seed": m["seed"],
                    "memory_id": m.get("memory_id"),
                    "success": bool(r["success"]),
                    "steps": r.get("steps"), "tool_errors": r.get("tool_errors"),
                    "parse_ok": r.get("parse_ok"), "parse_fail": r.get("parse_fail"),
                    "compliance": r.get("compliance"),
                })
    return rows, files


def load_sim(sealed):
    sim = {}
    path = os.path.join(sealed, "sim_report.csv")
    if os.path.exists(path):
        with open(path) as f:
            for r in csv.DictReader(f):
                sim[r["memory_id"]] = {
                    "sim_tf": float(r["sim_tf"]),
                    "sim_embed": (float(r["sim_embed"])
                                  if r["sim_embed"] not in ("", "None", None)
                                  else None)}
    return sim


# ---------------------------------------------------------------------------
# bootstrap helpers
# ---------------------------------------------------------------------------

def cluster_bootstrap_ci(rows, stat_fn, families, reps, seed, level=0.95):
    """families: universe of family ids; rows are re-sampled by family.
    stat_fn(sub_rows) -> float. Returns (point, lo, hi)."""
    rng = np.random.default_rng(seed)
    by_fam = defaultdict(list)
    for r in rows:
        by_fam[r["family_idx"]].append(r)
    point = stat_fn(rows)
    fams = sorted(by_fam)
    if not fams:
        return point, float("nan"), float("nan")
    stats = []
    for _ in range(reps):
        idx = rng.integers(0, len(fams), len(fams))
        sub = []
        for i in idx:
            sub.extend(by_fam[fams[i]])
        try:
            stats.append(stat_fn(sub))
        except Exception:
            continue
    alpha = (1 - level) / 2
    return (point,
            float(np.quantile(stats, alpha)) if stats else float("nan"),
            float(np.quantile(stats, 1 - alpha)) if stats else float("nan"))


def rate(rows):
    return sum(r["success"] for r in rows) / len(rows) if rows else float("nan")


def cell_rate_stat(cell):
    def f(rows):
        return rate([r for r in rows if r["cell"] == cell])
    return f


def rd_stat(cell, ref):
    """risk difference cell - ref (weighted over the resampled rows)."""
    def f(rows):
        a = [r for r in rows if r["cell"] == cell]
        b = [r for r in rows if r["cell"] == ref]
        if not a or not b:
            return float("nan")
        return rate(a) - rate(b)
    return f


def paired_uplift(rows, cell, ref="N"):
    """mean over (family,sibling,seed) pairs of success(cell)-success(ref)."""
    cell_m = {(r["family_idx"], r["sibling_idx"], r["seed"]): r
              for r in rows if r["cell"] == cell}
    ref_m = {(r["family_idx"], r["sibling_idx"], r["seed"]): r
             for r in rows if r["cell"] == ref}
    diffs = []
    for k, rc in cell_m.items():
        if k in ref_m:
            diffs.append(float(rc["success"]) - float(ref_m[k]["success"]))
    return diffs


def paired_uplift_stat(cell, ref="N"):
    def f(rows):
        d = paired_uplift(rows, cell, ref)
        return sum(d) / len(d) if d else float("nan")
    return f


def harmful_flip_stat(rows):
    d = []
    a01 = {(r["family_idx"], r["sibling_idx"], r["seed"]): r
           for r in rows if r["cell"] == "A01"}
    nn = {(r["family_idx"], r["sibling_idx"], r["seed"]): r
          for r in rows if r["cell"] == "N"}
    for k, ra in a01.items():
        if k in nn:
            d.append(1.0 if (nn[k]["success"] and not ra["success"]) else 0.0)
    return sum(d) / len(d) if d else float("nan"), len(d)


def hf_stat(rows):
    return harmful_flip_stat(rows)[0]


def _rank(v):
    order = np.argsort(np.argsort(v))
    return order.astype(float) + 1.0


def pearson(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) < 3 or x.std() == 0 or y.std() == 0:
        return float("nan")
    return float(np.corrcoef(x, y)[0, 1])


def spearman(x, y):
    if len(x) < 3:
        return float("nan")
    return pearson(_rank(x), _rank(y))


# ---------------------------------------------------------------------------
# figures
# ---------------------------------------------------------------------------

def _mpl():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def fig1(rows, out, models):
    plt = _mpl()
    fig, axes = plt.subplots(1, max(1, len(models)), figsize=(6 * max(1, len(models)), 4.5),
                             squeeze=False)
    summ = {}
    for ax, model in zip(axes[0], models):
        mrows = [r for r in rows if r["model"] == model]
        fams = sorted({r["family_idx"] for r in mrows})
        labels, means, los, his = [], [], [], []
        for c in ALL_CELLS:
            p, lo, hi = cluster_bootstrap_ci(
                mrows, cell_rate_stat(c), fams, NBOOT, BOOT_SEED + 1)
            labels.append(c)
            means.append(p)
            los.append(p - lo)
            his.append(hi - p)
            summ.setdefault(model, {})[c] = {"rate": p, "ci": [lo, hi],
                                             "n": len([r for r in mrows if r["cell"] == c])}
        colors = ["#4C79B0", "#B04C4C", "#4CA06A", "#8E6FB8", "#888888", "#C0A040"]
        ax.bar(labels, means, yerr=[los, his], capsize=4, color=colors,
               edgecolor="black", linewidth=0.5)
        ax.axhline(0, color="black", linewidth=0.5)
        ax.set_ylim(0, 1)
        ax.set_title("Success rate by cell (%s)" % model)
        ax.set_ylabel("success rate")
        ax.grid(axis="y", alpha=0.3)
        ax.text(0.01, -0.14, "P x S cells + N (no memory) / Q (sham); "
                "family-cluster bootstrap 95% CI", transform=ax.transAxes, fontsize=8)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return summ


def fig2(rows, out, models):
    plt = _mpl()
    fig, axes = plt.subplots(1, max(1, len(models)), figsize=(6 * max(1, len(models)), 4.5),
                             squeeze=False)
    summ = {}
    w = 0.38
    for ax, model in zip(axes[0], models):
        mrows = [r for r in rows if r["model"] == model]
        fams = sorted({r["family_idx"] for r in mrows})
        xs = np.arange(len(A_CELLS))
        for k, ref in enumerate(["N", "Q"]):
            vals, los, his = [], [], []
            for c in A_CELLS:
                p, lo, hi = cluster_bootstrap_ci(
                    mrows, rd_stat(c, ref), fams, NBOOT, BOOT_SEED + 2)
                vals.append(p)
                los.append(p - lo)
                his.append(hi - p)
                summ.setdefault(model, {}).setdefault(c, {})["rd_vs_" + ref] = \
                    {"diff": p, "ci": [lo, hi]}
            ax.bar(xs + (k - 0.5) * w, vals, width=w, yerr=[los, his], capsize=3,
                   label="vs %s" % ref, edgecolor="black", linewidth=0.5)
        ax.axhline(0, color="black", linewidth=0.7)
        ax.set_xticks(xs, A_CELLS)
        ax.set_title("Randomized uplift, risk difference (%s)" % model)
        ax.set_ylabel("risk difference")
        ax.grid(axis="y", alpha=0.3)
        ax.legend()
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return summ


def fig3(rows, sim, out, models):
    plt = _mpl()
    fig, axes = plt.subplots(1, max(1, len(models)), figsize=(6 * max(1, len(models)), 4.5),
                             squeeze=False)
    summ = {}
    for ax, model in zip(axes[0], models):
        mrows = [r for r in rows if r["model"] == model]
        xs, ys, cs = [], [], []
        metrics = [("sim_embed", "o-"), ("sim_tf", "s--")]
        used = None
        for key, style in metrics:
            xs, ys, cs = [], [], []
            for c in MEM_CELLS:
                for r in [x for x in mrows if x["cell"] == c]:
                    s = sim.get(r["memory_id"] or "", {}).get(key)
                    if s is None:
                        continue
                    keypair = (r["family_idx"], r["sibling_idx"], r["seed"])
                    nmatch = [x for x in mrows if x["cell"] == "N" and
                              (x["family_idx"], x["sibling_idx"], x["seed"]) == keypair]
                    if not nmatch:
                        continue
                    xs.append(s)
                    ys.append(float(r["success"]) - float(nmatch[0]["success"]))
                    cs.append(c)
            if len(xs) >= 3:
                used = key
                break
        if xs:
            colmap = {"A11": "#8E6FB8", "A10": "#4CA06A", "A01": "#B04C4C",
                      "A00": "#4C79B0", "Q": "#C0A040"}
            for c in MEM_CELLS:
                px = [x for x, cc in zip(xs, cs) if cc == c]
                py = [y for y, cc in zip(ys, cs) if cc == c]
                ax.scatter(px, py, label=c, alpha=0.7, color=colmap[c], s=28,
                           edgecolor="black", linewidth=0.3)
            rp = pearson(xs, ys)
            rs = spearman(xs, ys)
            ax.set_title("Similarity vs paired uplift vs N (%s)\nmetric=%s  pearson=%.3f  spearman=%.3f"
                         % (model, used, rp, rs))
            summ[model] = {"metric": used, "n": len(xs),
                           "pearson": rp, "spearman": rs}
        else:
            ax.set_title("Similarity vs paired uplift vs N (%s)\n(no pairs available)"
                         % model)
            summ[model] = {"metric": None, "n": 0}
        ax.axhline(0, color="black", linewidth=0.6)
        ax.set_xlabel("memory-target similarity (continuous)")
        ax.set_ylabel("paired uplift (cell - N)")
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return summ


def fig4(rows, out, models):
    plt = _mpl()
    fig, axes = plt.subplots(1, max(1, len(models)), figsize=(5.5 * max(1, len(models)), 4.5),
                             squeeze=False)
    summ = {}
    for ax, model in zip(axes[0], models):
        mrows = [r for r in rows if r["model"] == model]
        fams = sorted({r["family_idx"] for r in mrows})
        p, lo, hi = cluster_bootstrap_ci(mrows, hf_stat, fams, NBOOT, BOOT_SEED + 4)
        _, npairs = harmful_flip_stat(mrows)
        marg_a = rate([r for r in mrows if r["cell"] == "A01"])
        marg_n = rate([r for r in mrows if r["cell"] == "N"])
        ax.bar(["harmful\nflip"], [p], yerr=[[p - lo], [hi - p]], capsize=5,
               color="#B04C4C", edgecolor="black", linewidth=0.5)
        ax.axhline(0, color="black", linewidth=0.5)
        ax.set_ylim(0, 1)
        ax.set_title("P(N=1 & A01=0) paired harmful flip (%s)\npairs=%d"
                     % (model, npairs), fontsize=10)
        ax.grid(axis="y", alpha=0.3)
        ax.text(0.01, -0.18,
                "marginal risks: A01=%.3f, N=%.3f (reported per pilot rule "
                "when pairing is partial)" % (marg_a if marg_a == marg_a else float('nan'),
                                               marg_n if marg_n == marg_n else float('nan')),
                transform=ax.transAxes, fontsize=8)
        summ[model] = {"harmful_flip": p, "ci": [lo, hi], "n_pairs": npairs,
                       "marginal_A01": marg_a, "marginal_N": marg_n}
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return summ


# ---------------------------------------------------------------------------
# tables
# ---------------------------------------------------------------------------

def token_balance_table(sealed):
    path = os.path.join(sealed, "manifest.json")
    if os.path.exists(path):
        man = json.load(open(path))
        rows = []
        for c in ALL_CELLS:
            if c == "N":
                rows.append({"cell": "N", "n": 0, "mean": "", "sd": "",
                             "min": "", "max": ""})
                continue
            v = man["token_stats_by_cell"].get(c)
            if not v:
                continue
            rows.append({"cell": c, "n": v["n"], "mean": round(v["mean"], 2),
                         "sd": _sd_from_manifest(sealed, c), "min": v["min"],
                         "max": v["max"]})
        return rows, man
    return [], {}


def _sd_from_manifest(sealed, cell):
    path = os.path.join(sealed, "memories_sealed.jsonl")
    vals = []
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                r = json.loads(line)
                if r["cell"] == cell:
                    vals.append(r["token_count"])
    if len(vals) < 2:
        return 0.0
    return round(float(np.std(vals, ddof=1)), 2)


def difficulty_tost(rows, margin, models):
    """Equivalence of no-memory sibling difficulty: within each family the
    N-condition success rates of the 4 target siblings (over seeds) should be
    within +/- margin. Criterion: family-cluster bootstrap CI of the mean
    within-family pairwise difference lies inside [-margin, +margin]
    (TOST at CI level)."""
    out = {}
    for model in models:
        mrows = [r for r in rows if r["model"] == model and r["cell"] == "N"]
        by_key = defaultdict(list)
        for r in mrows:
            by_key[(r["family_idx"], r["sibling_idx"])].append(r["success"])
        pair_diffs = []
        fam_sib_rates = defaultdict(dict)
        for (fi, sib), vs in by_key.items():
            fam_sib_rates[fi][sib] = sum(vs) / len(vs)
        for fi, sibmap in fam_sib_rates.items():
            sibs = sorted(sibmap)
            for i in range(len(sibs)):
                for j in range(i + 1, len(sibs)):
                    pair_diffs.append({"family_idx": fi, "a": sibs[i], "b": sibs[j],
                                       "diff": sibmap[sibs[i]] - sibmap[sibs[j]]})
        def mean_diff(sub):
            return sum(d["diff"] for d in sub) / len(sub) if sub else float("nan")
        fams = sorted(fam_sib_rates)
        if pair_diffs and fams:
            p, lo, hi = cluster_bootstrap_ci(pair_diffs, mean_diff, fams,
                                             NBOOT, BOOT_SEED + 5)
            equivalent = (lo > -margin) and (hi < margin)
        else:
            p = lo = hi = float("nan")
            equivalent = None
        out[model] = {"margin": margin, "mean_pair_diff": p, "ci": [lo, hi],
                      "n_pairs": len(pair_diffs), "families": len(fams),
                      "equivalent": equivalent,
                      "sibling_rates": {str(k): v for k, v in
                                        ((fi, sibmap) for fi, sibmap in fam_sib_rates.items())}}
    return out


def compliance_summary(rows):
    agg = defaultdict(list)
    for r in rows:
        if r["compliance"]:
            agg[r["cell"]].append(r["compliance"])
    out = []
    for c in MEM_CELLS:
        vs = agg.get(c, [])
        if not vs:
            continue
        out.append({"cell": c, "n": len(vs),
                    "echo_frac_mean": round(float(np.mean([v["echo_frac"] for v in vs])), 4),
                    "step_action_coverage_mean": round(float(np.mean([v["step_action_coverage"] for v in vs])), 4)})
    return out


def write_csv(path, rows, fields):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


NBOOT = 2000
BOOT_SEED = 1234


def main():
    ap = argparse.ArgumentParser()
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--config", default=os.path.join(here, "configs", "pilot.yaml"))
    ap.add_argument("--rollouts", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--bootstrap-reps", type=int, default=None)
    args = ap.parse_args()
    global NBOOT, BOOT_SEED
    cfg = load_config(args.config)
    NBOOT = args.bootstrap_reps or cfg["analysis"]["bootstrap_reps"]
    BOOT_SEED = cfg["analysis"]["bootstrap_seed"]
    margin = cfg["analysis"]["tost_margin"]

    rows, files = load_rollouts(args.rollouts)
    print("[analyze] %d rollouts from %d files" % (len(rows), len(files)))
    if not rows:
        raise SystemExit("[analyze] no rollouts found: %s" % (args.rollouts,))
    sim = load_sim(cfg["paths"]["sealed"])
    models = sorted({r["model"] for r in rows})
    os.makedirs(args.out, exist_ok=True)

    s1 = fig1(rows, os.path.join(args.out, "fig1_cells_success.png"), models)
    print("[analyze] fig1 written")
    s2 = fig2(rows, os.path.join(args.out, "fig2_uplift.png"), models)
    print("[analyze] fig2 written")
    s3 = fig3(rows, sim, os.path.join(args.out, "fig3_sim_uplift.png"), models)
    print("[analyze] fig3 written")
    s4 = fig4(rows, os.path.join(args.out, "fig4_harmful_flip.png"), models)
    print("[analyze] fig4 written")

    tok_rows, man = token_balance_table(cfg["paths"]["sealed"])
    write_csv(os.path.join(args.out, "token_len_balance.csv"), tok_rows,
              ["cell", "n", "mean", "sd", "min", "max"])
    tost = difficulty_tost(rows, margin, models)
    with open(os.path.join(args.out, "difficulty_tost.json"), "w") as f:
        json.dump(tost, f, indent=1)
    comp = compliance_summary(rows)
    write_csv(os.path.join(args.out, "compliance_summary.csv"), comp,
              ["cell", "n", "echo_frac_mean", "step_action_coverage_mean"])

    parse_tot = sum((r["parse_ok"] or 0) + (r["parse_fail"] or 0) for r in rows)
    parse_ok = sum(r["parse_ok"] or 0 for r in rows)
    summary = {
        "n_rollouts": len(rows), "files": files, "models": models,
        "parseable_action_rate": parse_ok / parse_tot if parse_tot else None,
        "fig1_rates": s1, "fig2_risk_differences": s2,
        "fig3_similarity_uplift": s3, "fig4_harmful_flip": s4,
        "difficulty_tost": tost, "compliance": comp,
        "token_balance": tok_rows,
        "oracle_report": man.get("oracle_report"),
        "sim_thresholds": man.get("sim_thresholds"),
        "embedding_used": man.get("embed_model"),
        "bootstrap": {"reps": NBOOT, "seed": BOOT_SEED, "level": cfg["analysis"]["ci_level"],
                      "cluster": "family"},
    }
    with open(os.path.join(args.out, "summary.json"), "w") as f:
        json.dump(summary, f, indent=1)
    print("[analyze] summary.json + tables written to %s" % args.out)
    for model in models:
        rates = {c: round(s1.get(model, {}).get(c, {}).get("rate", float("nan")), 3)
                 for c in ALL_CELLS}
        print("[analyze] %s success rates: %s" % (model, rates))


if __name__ == "__main__":
    main()
