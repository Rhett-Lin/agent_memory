"""H-C minimal gate analysis (GATE_PROTOCOL.md Part II sections 8/10).

Loads the three representation systems' rollouts (procedural = existing pilot
qwen7b files; raw / summary = new hc grid files) and computes the frozen H-C
estimands.  It deliberately does NOT emit a GO/NO_GO decision: it reports the
pre-registered numbers and the mechanical ingredients of criterion H-C-3
(CI-excludes-zero flags, |Delta| >= 8pp flags, tau_trap orderings) for the
parent to decide.

Statistics (frozen, section 10):
- per system per cell success rate + family-cluster bootstrap 95% CI
  (resampling unit = family, 2000 reps, seed = analysis.bootstrap_seed);
- profile per system h: tau_context = r(Q)-r(N); tau_struct = r(A10)-r(A00);
  tau_trap = r(A01)-r(A00); tau_replaylike = r(A11)-r(A10);
  HFR = P(Y_N=1, Y_A01=0) paired by (family, sibling, seed) within the system;
- paired Delta between system pairs (raw,procedural) / (summary,procedural) /
  (raw,summary): same family resample applied to both systems (paired cluster
  bootstrap CI); two-sided bootstrap sign p = 2*min(P(D*<=0), P(D*>=0));
- multiplicity: Holm over the 6 pre-registered primary contrasts
  (3 pairs x {tau_struct, tau_trap});  DHFR is marked exploratory;
- aggregate-equivalence (pre-registered definition): |mean A-cell success rate
  difference| < 3pp;
- card-length SMD across systems (A-cell cards, Qwen2.5-1.5B token counts from
  the three sealed maps).

Outputs:
  pilot/systems/HC_RESULTS.json               all pre-registered numbers
  /work1/zixuan/outputs/agent_memory/pilot/hc/fig_hc{1..4}_*.png
  pilot/systems/summary_qa_sample.json        10 deterministic (seed 1234)
      raw/summary card pairs for the pre-registered manual summary-quality
      audit (section 12 -- the audit itself is done by the human, not here)

Run (from pilot/):  python systems/analyze_hc.py --config configs/pilot_7b.yaml
"""

import argparse
import glob
import json
import os
import sys
from collections import defaultdict

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_PILOT = os.path.dirname(_HERE)
sys.path.insert(0, _PILOT)

from generate_families import load_config  # noqa: E402

DEFAULT_CONFIG = os.path.join(_PILOT, "configs", "pilot_7b.yaml")
CELLS = ["A00", "A01", "A10", "A11", "N", "Q"]
A_CELLS = ["A00", "A01", "A10", "A11"]
SYSTEMS = ["procedural", "raw", "summary"]
PAIRS = [("raw", "procedural"), ("summary", "procedural"), ("raw", "summary")]
NBOOT = 2000                      # GATE_PROTOCOL Part II section 10 (frozen)
AGG_EQ_MARGIN = 0.03              # section 10: A-cell average diff < 3pp
HC3_STRUCT_PP = 0.08              # section 8 H-C-3: |Delta tau_struct| >= 8pp


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------

def load_system_rows(cfg):
    """system -> list of unit rows {family_idx, sibling_idx, seed, cell,
    success, parse_ok, parse_fail}."""
    out_root = cfg["paths"]["output_root"]
    pats = {"procedural": os.path.join(out_root, "rollouts_qwen7b_shard*-of-*.jsonl"),
            "raw": os.path.join(out_root, "rollouts_hc_raw_qwen7b_shard*-of-*.jsonl"),
            "summary": os.path.join(out_root, "rollouts_hc_summary_qwen7b_shard*-of-*.jsonl")}
    systems, files_used = {}, {}
    for system, pat in pats.items():
        rows = []
        files = sorted(glob.glob(pat))
        # never mix the two qwen7b output families into procedural
        files = [f for f in files if "rollouts_hc_" not in f or system != "procedural"]
        files = [f for f in files if not (system == "procedural" and "_hc_" in f)]
        for fn in files:
            with open(fn) as f:
                for line in f:
                    try:
                        r = json.loads(line)
                    except Exception:
                        continue
                    m = r.get("meta", {})
                    if m.get("model") != "qwen7b":
                        continue
                    if m.get("system", "procedural") != system:
                        continue
                    rows.append({"family_idx": m["family_idx"],
                                 "sibling_idx": m["sibling_idx"],
                                 "seed": m["seed"], "cell": m["cell"],
                                 "success": bool(r["success"]),
                                 "parse_ok": r.get("parse_ok", 0),
                                 "parse_fail": r.get("parse_fail", 0)})
        systems[system] = rows
        files_used[system] = files
    return systems, files_used


# ---------------------------------------------------------------------------
# per-family aggregation + bootstrap machinery
# ---------------------------------------------------------------------------

def family_counts(rows, fam_universe):
    """cell -> (succ[F], n[F]) aligned with fam_universe; plus per-family HFR
    pair tallies (n_success_with_a01_fail, n_pairs)."""
    succ = {c: np.zeros(len(fam_universe)) for c in CELLS}
    n = {c: np.zeros(len(fam_universe)) for c in CELLS}
    fpos = {f: i for i, f in enumerate(fam_universe)}
    hf_num = np.zeros(len(fam_universe))
    hf_den = np.zeros(len(fam_universe))
    unit = {}
    for r in rows:
        succ[r["cell"]][fpos[r["family_idx"]]] += r["success"]
        n[r["cell"]][fpos[r["family_idx"]]] += 1
        unit[(r["family_idx"], r["sibling_idx"], r["seed"], r["cell"])] = r["success"]
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


def _rate_at(succ, n, cell, idx):
    den = n[cell][idx].sum()
    return succ[cell][idx].sum() / den if den else float("nan")


def stats_at(succ, n, hf_num, hf_den, idx):
    """All profile stats for one family resample (idx)."""
    r = {c: _rate_at(succ, n, c, idx) for c in CELLS}
    return (r, r["Q"] - r["N"], r["A10"] - r["A00"], r["A01"] - r["A00"],
            r["A11"] - r["A10"],
            (hf_num[idx].sum() / hf_den[idx].sum()
             if hf_den[idx].sum() else float("nan")))


def bootstrap_systems(rows_by_system, fam_universe, reps, seed):
    """One aligned family-cluster bootstrap for ALL systems at once, so paired
    Deltas use the identical family resample on both sides (section 10)."""
    agg = {s: family_counts(rows_by_system[s], fam_universe) for s in SYSTEMS}
    F = len(fam_universe)
    rng = np.random.default_rng(seed)
    stats_names = ["tau_context", "tau_struct", "tau_trap", "tau_replaylike", "hfr"]
    boot = {(s, k): [] for s in SYSTEMS for k in stats_names}
    boot_rates = {(s, c): [] for s in SYSTEMS for c in CELLS}
    boot_delta = {(a, b, k): [] for (a, b) in PAIRS
                  for k in stats_names + ["agg_acells"]}
    for _ in range(reps):
        idx = rng.integers(0, F, F)
        per = {}
        for s in SYSTEMS:
            r, tctx, tstruct, ttrap, trep, hfr = stats_at(*agg[s], idx)
            per[s] = (r, tctx, tstruct, ttrap, trep, hfr)
            for k, v in zip(stats_names, (tctx, tstruct, ttrap, trep, hfr)):
                boot[(s, k)].append(v)
            for c in CELLS:
                boot_rates[(s, c)].append(r[c])
        for (a, b) in PAIRS:
            for j, k in enumerate(stats_names):
                boot_delta[(a, b, k)].append(per[a][j + 1] - per[b][j + 1])
            agg_a = np.mean([per[a][0][c] for c in A_CELLS])
            agg_b = np.mean([per[b][0][c] for c in A_CELLS])
            boot_delta[(a, b, "agg_acells")].append(agg_a - agg_b)
    return agg, boot, boot_rates, boot_delta


def full_stats(agg):
    idx = np.arange(len(next(iter(agg[1].values()))))
    return stats_at(*agg, idx)


# ---------------------------------------------------------------------------
# multiplicity
# ---------------------------------------------------------------------------

def holm(pvals):
    """pvals: list of (name, p). Returns {name: p_holm} (step-down)."""
    order = sorted(range(len(pvals)), key=lambda i: pvals[i][1])
    m = len(pvals)
    adj, running = {}, 0.0
    for rank, i in enumerate(order):
        val = min(1.0, (m - rank) * pvals[i][1])
        running = max(running, val)
        adj[pvals[i][0]] = running
    return adj


# ---------------------------------------------------------------------------
# card lengths
# ---------------------------------------------------------------------------

def card_tokens(cfg):
    """system -> {cell -> [token counts]} for A-cell cards (Q is the shared
    sham card; N has no card)."""
    sealed = cfg["paths"]["sealed"]
    toks = {s: defaultdict(list) for s in SYSTEMS}
    with open(os.path.join(sealed, "memories_sealed.jsonl")) as f:
        for line in f:
            r = json.loads(line)
            toks["procedural"][r["cell"]].append(r["token_count"])
    for system, fname in (("raw", "raw_cards_map.jsonl"),
                          ("summary", "summary_cards_map.jsonl")):
        p = os.path.join(_HERE, fname)
        if not os.path.exists(p):
            continue
        with open(p) as f:
            for line in f:
                r = json.loads(line)
                toks[system][r["cell"]].append(r["n_tokens_card"])
    return toks


def smd(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) < 2 or len(b) < 2:
        return float("nan")
    sd = np.sqrt((a.std(ddof=1) ** 2 + b.std(ddof=1) ** 2) / 2)
    if sd == 0:
        return 0.0 if a.mean() == b.mean() else float("inf")
    return float((a.mean() - b.mean()) / sd)


# ---------------------------------------------------------------------------
# figures
# ---------------------------------------------------------------------------

def _mpl():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def fig1(rates, out):
    plt = _mpl()
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5), sharey=True)
    colors = ["#4C79B0", "#B04C4C", "#4CA06A", "#8E6FB8", "#888888", "#C0A040"]
    for ax, s in zip(axes, SYSTEMS):
        means = [rates[s][c]["rate"] for c in CELLS]
        los = [rates[s][c]["rate"] - rates[s][c]["ci"][0] for c in CELLS]
        his = [rates[s][c]["ci"][1] - rates[s][c]["rate"] for c in CELLS]
        ax.bar(CELLS, means, yerr=[los, his], capsize=4, color=colors,
               edgecolor="black", linewidth=0.5)
        ax.set_ylim(0, 1)
        ax.set_title(s)
        ax.grid(axis="y", alpha=0.3)
    axes[0].set_ylabel("success rate")
    fig.suptitle("H-C minimal gate: cell success rates by system "
                 "(family-cluster bootstrap 95% CI, qwen7b)")
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def fig2(profiles, out):
    plt = _mpl()
    keys = ["tau_context", "tau_struct", "tau_trap", "tau_replaylike", "hfr"]
    labels = ["τ_context", "τ_struct", "τ_trap", "τ_replaylike", "HFR_A01"]
    fig, ax = plt.subplots(figsize=(9, 4.5))
    xs = np.arange(len(keys))
    w = 0.25
    colmap = {"procedural": "#4C79B0", "raw": "#B04C4C", "summary": "#4CA06A"}
    for k, s in enumerate(SYSTEMS):
        means = [profiles[s][kk]["est"] for kk in keys]
        los = [profiles[s][kk]["est"] - profiles[s][kk]["ci"][0] for kk in keys]
        his = [profiles[s][kk]["ci"][1] - profiles[s][kk]["est"] for kk in keys]
        ax.bar(xs + (k - 1) * w, means, width=w, yerr=[los, his], capsize=3,
               label=s, color=colmap[s], edgecolor="black", linewidth=0.5)
    ax.axhline(0, color="black", linewidth=0.7)
    ax.set_xticks(xs, labels)
    ax.set_ylabel("estimate (risk difference / rate)")
    ax.set_title("Per-system causal profile (family-cluster bootstrap 95% CI)")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def fig3(deltas, holm_adj, out):
    plt = _mpl()
    fig, ax = plt.subplots(figsize=(8, 4.8))
    rows = []
    for (a, b) in PAIRS:
        for est in ("tau_struct", "tau_trap"):
            d = deltas[(a, b)][est]
            rows.append(("%s - %s : Δ%s" % (a, b, "τ_struct" if est == "tau_struct"
                                            else "τ_trap"),
                         d, "%s_%s_%s" % (a, b, est)))
    ys = np.arange(len(rows))[::-1]
    for y, (label, d, key) in zip(ys, rows):
        lo, hi = d["ci"]
        sig = holm_adj.get(key, 1.0) < 0.05
        ax.plot([lo, hi], [y, y], "-", color="#B04C4C" if sig else "#555555",
                linewidth=2)
        ax.plot(d["est"], y, "o", color="#B04C4C" if sig else "#555555")
        ax.text(0.34, y, ("*" if sig else "") + " p_holm=%.3f" % holm_adj.get(key, 1.0),
                va="center", fontsize=8)
    ax.axvline(0, color="black", linewidth=0.7)
    ax.axvline(-HC3_STRUCT_PP, color="grey", linewidth=0.7, linestyle="--")
    ax.axvline(HC3_STRUCT_PP, color="grey", linewidth=0.7, linestyle="--")
    ax.set_yticks(ys, [r[0] for r in rows], fontsize=9)
    ax.set_xlabel("paired Δ (family-cluster bootstrap 95% CI; dashed = ±8pp)")
    ax.set_title("H-C primary contrasts (Holm over 6; * = p_holm<0.05)")
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def fig4(toks, out):
    plt = _mpl()
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    data, labels = [], []
    for s in SYSTEMS:
        vals = [t for c in A_CELLS for t in toks[s].get(c, [])]
        data.append(vals)
        labels.append("%s (n=%d)" % (s, len(vals)))
    ax.boxplot(data, tick_labels=labels, showmeans=True)
    ax.axhline(200, color="grey", linewidth=0.7, linestyle="--")
    ax.axhline(300, color="grey", linewidth=0.7, linestyle="--")
    ax.set_ylabel("card tokens (Qwen2.5-1.5B tokenizer)")
    ax.set_title("A-cell card length distribution by system (window 200-300)")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------------------
# summary QA sample (pre-registered manual audit, section 12; sampling here,
# judging by the human)
# ---------------------------------------------------------------------------

def write_qa_sample(cfg, out_path, n=10):
    smap = os.path.join(_HERE, "summary_cards_map.jsonl")
    if not os.path.exists(smap):
        return 0
    with open(smap) as f:
        rows = [json.loads(l) for l in f]
    rng = np.random.default_rng(1234)
    pick = rng.choice(len(rows), size=min(n, len(rows)), replace=False)
    pub = cfg["paths"]["public_view"]
    sample = []
    for i in sorted(pick):
        m = rows[int(i)]
        with open(os.path.join(pub, "systems", "raw",
                               m["memory_id"] + ".json")) as f:
            raw_text = json.load(f)["text"]
        with open(os.path.join(pub, "systems", "summary",
                               m["memory_id"] + ".json")) as f:
            sum_text = json.load(f)["text"]
        sample.append({"memory_id": m["memory_id"],
                       "raw_card_text": raw_text, "summary_card_text": sum_text,
                       "audit_verdict": None,
                       "audit_note": "human: does the summary restate a wrong "
                                     "step or drop a critical step?"})
    with open(out_path, "w") as f:
        json.dump({"sample_seed": 1234, "n": len(sample),
                   "instructions": "pre-registered manual audit (GATE_PROTOCOL "
                                   "sec.12): mark audit_verdict pass/fail per "
                                   "card; fail rate >30% triggers the kill "
                                   "condition",
                   "items": sample}, f, indent=1)
    return len(sample)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--out", default="/work1/zixuan/outputs/agent_memory/pilot/hc")
    args = ap.parse_args()
    cfg = load_config(args.config)
    os.environ.setdefault("HF_HOME", cfg["paths"]["hf_home"])
    seed = cfg["analysis"]["bootstrap_seed"]
    os.makedirs(args.out, exist_ok=True)

    rows_by_system, files_used = load_system_rows(cfg)
    for s in SYSTEMS:
        print("[analyze_hc] %s: %d rollouts from %d files"
              % (s, len(rows_by_system[s]), len(files_used[s])))
    fam_universe = sorted({r["family_idx"] for s in SYSTEMS
                           for r in rows_by_system[s]})

    agg, boot, boot_rates, boot_delta = bootstrap_systems(
        rows_by_system, fam_universe, NBOOT, seed)

    # ---- per-system rates + profile --------------------------------------
    rates, profiles, counts = {}, {}, {}
    for s in SYSTEMS:
        idx = np.arange(len(fam_universe))
        succ, n, hf_num, hf_den = agg[s]
        rates[s], counts[s] = {}, {}
        for c in CELLS:
            p = succ[c].sum() / n[c].sum() if n[c].sum() else float("nan")
            lo = float(np.quantile(boot_rates[(s, c)], 0.025))
            hi = float(np.quantile(boot_rates[(s, c)], 0.975))
            rates[s][c] = {"rate": p, "ci": [lo, hi], "n": int(n[c].sum())}
        r, tctx, tstruct, ttrap, trep, hfr = full_stats(agg[s])
        full = {"tau_context": tctx, "tau_struct": tstruct, "tau_trap": ttrap,
                "tau_replaylike": trep, "hfr": hfr}
        profiles[s] = {}
        for k, v in full.items():
            lo = float(np.quantile(boot[(s, k)], 0.025))
            hi = float(np.quantile(boot[(s, k)], 0.975))
            profiles[s][k] = {"est": v, "ci": [lo, hi],
                              "ci_excludes_zero": bool(lo > 0 or hi < 0)}
        counts[s] = {"n_rollouts": len(rows_by_system[s]),
                     "parseable_action_rate":
                         (sum(r_["parse_ok"] for r_ in rows_by_system[s])
                          / max(1, sum(r_["parse_ok"] + r_["parse_fail"]
                                       for r_ in rows_by_system[s]))),
                     "hfr_pairs": int(hf_den.sum())}

    # ---- paired deltas + Holm --------------------------------------------
    deltas, boot_p = {}, {}
    for (a, b) in PAIRS:
        deltas[(a, b)] = {}
        for est in ["tau_context", "tau_struct", "tau_trap", "tau_replaylike",
                    "hfr", "agg_acells"]:
            vals = np.asarray(boot_delta[(a, b, est)])
            if est == "agg_acells":
                idx = np.arange(len(fam_universe))
                ra = np.mean([_rate_at(*agg[a][:2], c, idx) for c in A_CELLS])
                rb = np.mean([_rate_at(*agg[b][:2], c, idx) for c in A_CELLS])
                pe = ra - rb
            else:
                kmap = ["tau_context", "tau_struct", "tau_trap",
                        "tau_replaylike", "hfr"]
                fa = full_stats(agg[a])
                fb = full_stats(agg[b])
                pe = fa[kmap.index(est) + 1] - fb[kmap.index(est) + 1]
            lo = float(np.quantile(vals, 0.025))
            hi = float(np.quantile(vals, 0.975))
            p = 2 * min(float(np.mean(vals <= 0)), float(np.mean(vals >= 0)))
            p = min(1.0, p)
            deltas[(a, b)][est] = {"est": pe, "ci": [lo, hi],
                                   "ci_excludes_zero": bool(lo > 0 or hi < 0),
                                   "p_boot": p}
            boot_p[("%s_%s_%s" % (a, b, est))] = p
    primary = [("%s_%s_%s" % (a, b, est), boot_p["%s_%s_%s" % (a, b, est)])
               for (a, b) in PAIRS for est in ("tau_struct", "tau_trap")]
    holm_adj = holm(primary)

    # ---- H-C-3 ingredients (no decision here) ------------------------------
    hc3 = {}
    for (a, b) in PAIRS:
        d = deltas[(a, b)]["tau_struct"]
        key = "%s_vs_%s" % (a, b)
        trap_order = np.sign(profiles[a]["tau_trap"]["est"]
                             - profiles[b]["tau_trap"]["est"])
        hc3[key] = {
            "abs_delta_tau_struct": abs(d["est"]),
            "abs_ge_8pp": bool(abs(d["est"]) >= HC3_STRUCT_PP),
            "ci_excludes_zero": d["ci_excludes_zero"],
            "tau_trap_%s" % a: profiles[a]["tau_trap"],
            "tau_trap_%s" % b: profiles[b]["tau_trap"],
            "tau_trap_ordering": (">%s" % b if trap_order > 0 else
                                  "<%s" % b if trap_order < 0 else "=="),
        }

    # ---- aggregate equivalence ---------------------------------------------
    agg_eq = {}
    for (a, b) in PAIRS:
        d = deltas[(a, b)]["agg_acells"]
        agg_eq["%s_vs_%s" % (a, b)] = {
            "a_cells_mean_rate_diff": d["est"], "ci": d["ci"],
            "equivalent_abs_lt_3pp": bool(abs(d["est"]) < AGG_EQ_MARGIN)}

    # ---- card lengths --------------------------------------------------------
    toks = card_tokens(cfg)
    card_len = {}
    for s in SYSTEMS:
        per_cell = {c: {"n": len(toks[s].get(c, [])),
                        "mean": float(np.mean(toks[s][c])) if toks[s].get(c) else None,
                        "sd": float(np.std(toks[s][c], ddof=1)) if len(toks[s].get(c, [])) > 1 else None}
                    for c in A_CELLS}
        card_len[s] = per_cell
    smds = {}
    for (a, b) in PAIRS:
        va = [t for c in A_CELLS for t in toks[a].get(c, [])]
        vb = [t for c in A_CELLS for t in toks[b].get(c, [])]
        smds["%s_vs_%s" % (a, b)] = {"smd_acells": smd(va, vb),
                                     "n_a": len(va), "n_b": len(vb)}

    # ---- harvest QA (acceptance inputs) --------------------------------------
    qa = {}
    rmap = os.path.join(_HERE, "raw_cards_map.jsonl")
    if os.path.exists(rmap):
        with open(rmap) as f:
            rm = [json.loads(l) for l in f]
        fb = sum(1 for r in rm if r["oracle_fallback"])
        qa["raw_harvest"] = {"cards": len(rm), "oracle_fallback": fb,
                             "oracle_fallback_frac_of_800": fb / 800.0,
                             "below_window": sum(1 for r in rm if r["below_window"]),
                             "flag_fallback_ge_5pct": bool(fb >= 0.05 * 800)}
    nqa = write_qa_sample(cfg, os.path.join(_HERE, "summary_qa_sample.json"))

    # ---- figures -----------------------------------------------------------
    fig1(rates, os.path.join(args.out, "fig_hc1_cell_rates.png"))
    fig2(profiles, os.path.join(args.out, "fig_hc2_profiles.png"))
    fig3(deltas, holm_adj, os.path.join(args.out, "fig_hc3_deltas.png"))
    fig4(toks, os.path.join(args.out, "fig_hc4_card_lengths.png"))

    results = {
        "pre_registration": "GATE_PROTOCOL.md Part II (2026-08-08); "
                            "analysis follows section 10 verbatim; no GO/NO_GO "
                            "decision is made in this file",
        "bootstrap": {"reps": NBOOT, "seed": seed, "level": 0.95,
                      "cluster": "family", "paired_resamples": True},
        "systems": SYSTEMS, "pairs": ["%s_vs_%s" % p for p in PAIRS],
        "files": {s: files_used[s] for s in SYSTEMS},
        "rollout_counts": counts,
        "cell_rates": rates,
        "profiles": profiles,
        "paired_deltas": {"%s_vs_%s" % (a, b): deltas[(a, b)] for (a, b) in PAIRS},
        "holm_primary_6": {k: {"p_raw": dict(primary)[k], "p_holm": holm_adj[k],
                               "reject_0.05": bool(holm_adj[k] < 0.05)}
                           for k, _ in primary},
        "exploratory": {"delta_hfr": {"%s_vs_%s" % (a, b): deltas[(a, b)]["hfr"]
                                      for (a, b) in PAIRS}},
        "hc3_ingredients_for_parent_decision": hc3,
        "aggregate_equivalence_lt3pp": agg_eq,
        "card_lengths": {"per_system_per_cell": card_len, "smd": smds},
        "harvest_qa": qa,
        "summary_qa_sample_n": nqa,
    }
    out_json = os.path.join(_HERE, "HC_RESULTS.json")
    with open(out_json, "w") as f:
        json.dump(results, f, indent=1)
    print("[analyze_hc] wrote %s and figures to %s" % (out_json, args.out))
    for s in SYSTEMS:
        print("[analyze_hc] %s rates: %s"
              % (s, {c: round(rates[s][c]["rate"], 3) for c in CELLS}))
    print("[analyze_hc] Holm primary contrasts:")
    for k, v in results["holm_primary_6"].items():
        print("  %-34s p_raw=%.4f p_holm=%.4f reject=%s"
              % (k, v["p_raw"], v["p_holm"], v["reject_0.05"]))


if __name__ == "__main__":
    main()
