"""H-DC paper figures (iclr2027), style-matched to pilot/analyze.py.

fig_hdc_cards.png     card token distribution + escalation stages (dslice),
                      noting the paired |dtok|=0 vs raw_matched construction.
fig_hdc_contrasts.png per model: grouped A10/A11 bars for dslice /
                      raw_matched / raw(300) / procedural with family-cluster
                      95% CIs, plus the tau_replay panel with E1 annotation.

Outputs copied to iclr2027/figs/.
"""

import json
import os
import shutil
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_PILOT = os.path.dirname(_HERE)
sys.path.insert(0, _PILOT)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from generate_families import load_config  # noqa: E402
from dslice.analyze_dslice import (DEFAULT_CONFIG, load_model_systems,  # noqa: E402
                                   family_counts, stats_at, SYSTEMS)

OUT_DIR = "/work1/zixuan/outputs/agent_memory/pilot/dslice"
PAPER_FIGS = os.path.join(os.path.dirname(_PILOT), "iclr2027", "figs")
NBOOT = 2000
COLORS = {"dslice": "#4CA06A", "raw_matched": "#B04C4C", "raw": "#C0A040",
          "procedural": "#4C79B0"}
ARM_LABEL = {"dslice": "dslice", "raw_matched": "raw_matched",
             "raw": "raw(300)", "procedural": "procedural"}


def rate_cis(syms, systems, fam_universe, seed):
    """Bootstrap CIs for A10/A11 rates and tau_replay per system."""
    fpos = {f: i for i, f in enumerate(fam_universe)}
    agg = {s: family_counts(syms[s], fpos) for s in systems}
    F = len(fam_universe)
    rng = np.random.default_rng(seed)
    boot = {(s, k): [] for s in systems for k in ("A10", "A11", "tau_rl")}
    for _ in range(NBOOT):
        idx = rng.integers(0, F, F)
        for s in systems:
            st = stats_at(agg[s], idx)
            boot[(s, "A10")].append(st["rates"]["A10"])
            boot[(s, "A11")].append(st["rates"]["A11"])
            boot[(s, "tau_rl")].append(st["tau_rl"])
    full_idx = np.arange(F)
    out = {}
    for s in systems:
        st = stats_at(agg[s], full_idx)
        out[s] = {}
        for k in ("A10", "A11"):
            b = np.array(boot[(s, k)])
            lo, hi = np.percentile(b, [2.5, 97.5])
            out[s][k] = (st["rates"][k], lo, hi)
        b = np.array(boot[(s, "tau_rl")])
        lo, hi = np.percentile(b, [2.5, 97.5])
        out[s]["tau_rl"] = (st["tau_rl"], lo, hi)
    return out


def fig_cards(cfg):
    with open(os.path.join(_HERE, "cards_map.jsonl")) as f:
        rows = [json.loads(l) for l in f]
    toks = np.array([r["n_tokens"] for r in rows])
    stages = {}
    for r in rows:
        stages[r["escalation_stage"]] = stages.get(r["escalation_stage"], 0) + 1

    fig, axes = plt.subplots(1, 2, figsize=(9, 3.6))
    ax = axes[0]
    ax.hist(toks, bins=26, color="#4CA06A", edgecolor="black", linewidth=0.5)
    ax.axvline(300, color="#B04C4C", linewidth=1.2, linestyle="--")
    ax.axvline(toks.mean(), color="#4C79B0", linewidth=1.2)
    ax.text(296, 1.02, "300 cap ", ha="right", va="bottom", fontsize=7,
            color="#B04C4C", transform=ax.get_xaxis_transform())
    ax.text(toks.mean() - 4, 1.02, "mean %.1f " % toks.mean(), ha="right",
            va="bottom", fontsize=7, color="#4C79B0",
            transform=ax.get_xaxis_transform())
    ax.set_xlabel("dslice card length (Qwen-1.5B tokens)")
    ax.set_ylabel("cards")
    ax.set_title("Card length distribution (n=%d)" % len(toks), pad=28)
    ax.text(0.02, 0.97, "raw_matched cut to each card's exact count\n"
            "(paired |d tok| = 0, 640/640)\n"
            "188/640 sources: oracle-plan recons.", transform=ax.transAxes,
            fontsize=7, va="top")

    ax = axes[1]
    ks = sorted(stages)
    stage_lab = {0: "0\nbase", 1: "1\n-key\ncols", 2: "2\n-read\nres",
                 3: "3\n-fin.\nres", 4: "4\n-rd/ls\nact", 5: "5\n-agg\nact",
                 6: "6\n-prefix", 7: "7\n-trunc"}
    ax.bar([stage_lab.get(k, str(k)) for k in ks], [stages[k] for k in ks],
           color="#8E6FB8", edgecolor="black", linewidth=0.5)
    for i, k in enumerate(ks):
        ax.text(i, stages[k] + 6, str(stages[k]), ha="center", fontsize=8)
    ax.set_ylim(0, max(stages.values()) * 1.42)
    ax.set_xlabel("highest escalation stage reached (what it deletes)")
    ax.set_ylabel("cards")
    ax.set_title("Deletion ladder actually used")
    ax.text(0.03, 0.97, "asserted invariants (640/640):\n"
            "parsed write-action args, aggregate\n"
            "values, finish action", transform=ax.transAxes, fontsize=7,
            va="top")
    fig.tight_layout()
    out = os.path.join(OUT_DIR, "fig_hdc_cards.png")
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def fig_contrasts(models_stats):
    models = ["qwen7b", "qwen3b"]
    fig, axes = plt.subplots(2, 2, figsize=(9, 6.2))
    for col, model in enumerate(models):
        stats = models_stats[model]
        arms = ["dslice", "raw_matched", "raw", "procedural"]
        ax = axes[0][col]
        x = np.arange(len(arms))
        w = 0.36
        for j, cell in enumerate(("A10", "A11")):
            vals = [stats[s][cell] for s in arms]
            means = [v[0] for v in vals]
            los = [v[0] - v[1] for v in vals]
            his = [v[2] - v[0] for v in vals]
            cols = ["#9AA5B1" if cell == "A10" else COLORS[s]
                    for s in arms]
            ax.bar(x + (j - 0.5) * w, means, w, yerr=[los, his], capsize=3,
                   color=cols, edgecolor="black", linewidth=0.4,
                   label=cell if col == 0 else None)
        ax.set_xticks(x)
        ax.set_xticklabels([ARM_LABEL[s] for s in arms], fontsize=8,
                           rotation=12)
        ax.set_ylim(0, 1)
        ax.set_ylabel("success rate")
        ax.set_title("%s: A10/A11 by arm" % model)
        ax.grid(axis="y", alpha=0.3)
        if col == 0:
            ax.legend(fontsize=8)

        ax = axes[1][col]
        vals = [stats[s]["tau_rl"] for s in arms]
        means = [v[0] for v in vals]
        los = [v[0] - v[1] for v in vals]
        his = [v[2] - v[0] for v in vals]
        ax.bar([ARM_LABEL[s] for s in arms], means, yerr=[los, his],
               capsize=4, color=[COLORS[s] for s in arms],
               edgecolor="black", linewidth=0.5)
        for i, v in enumerate(vals):
            ax.text(i, v[0] + (v[2] - v[0]) + 0.01, "%+.3f" % v[0],
                    ha="center", fontsize=8)
        ax.axhline(0, color="black", linewidth=0.6)
        ax.set_ylabel(r"$\tau_{replay} = A11 - A10$")
        note = ("E1 vs raw_matched = +0.145 [+0.048,+0.233], Holm p=.012"
                if model == "qwen7b" else
                "E1 vs raw_matched = -0.084 [-0.177,+0.002], Holm p=.97")
        ax.set_title("%s: replay term by arm\n%s" % (model, note),
                     fontsize=9)
        ax.grid(axis="y", alpha=0.3)
        ax.tick_params(axis="x", labelsize=8, rotation=12)
        top = max(v[2] for v in vals)
        ax.set_ylim(top=top + 0.06)
    fig.tight_layout()
    out = os.path.join(OUT_DIR, "fig_hdc_contrasts.png")
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def main():
    cfg = load_config(DEFAULT_CONFIG)
    seed = cfg.get("analysis", {}).get("bootstrap_seed", 12345)
    os.makedirs(OUT_DIR, exist_ok=True)
    outs = [fig_cards(cfg)]
    models_stats = {}
    for model in ("qwen7b", "qwen3b"):
        syms, _ = load_model_systems(cfg, model)
        fam_universe = sorted({r["family_idx"] for rows in syms.values()
                               for r in rows})
        models_stats[model] = rate_cis(syms, SYSTEMS, fam_universe, seed)
    outs.append(fig_contrasts(models_stats))
    for o in outs:
        dst = os.path.join(PAPER_FIGS, os.path.basename(o))
        shutil.copyfile(o, dst)
        print("[fig] %s -> %s" % (o, dst))


if __name__ == "__main__":
    main()
