"""Gate C-lite cond1: Memory Transplants architecture x content 2x2 ANALYSIS on
EXISTING rollouts (no new rollouts are run).

Purpose (NEXT_ACTION.md 2026-08-08, Gate C-lite cond1):
  Replicate the Memory Transplants-style 2x2 INSIDE the pilot harness
  (fixed injection, frozen cards, shared DB state) and show whether it
  answers the same question as the pilot's program x surface (P x S)
  factorial.

Factors (frozen for this analysis, no tuning):
  arch    : procedural cards (pilot rolls) vs raw-transcript cards
            (H-C raw rolls).  raw exists ONLY at qwen7b (H-C grid was
            qwen7b-only) -> qwen3b enters only for the arch=procedural
            content axis and the P x S split.  No data is fabricated.
  content : (i)  "program-matched content" = A11 U A10  (the Memory
                   Transplants analog of cross-domain transfer: A10's
                   source is the a10_partner in ANOTHER domain rendering
                   of the same abstract archetype; A11 is the same-family
                   sibling rendering)
            (ii) "near-miss content"    = A01
            (iii)"unrelated content"    = A00
            N (no memory) is the uplift baseline; Q is the sham control.

Estimands (all identity-link risk differences; inference = family-cluster
bootstrap, resampling unit = family, 2000 reps, seed = config
analysis.bootstrap_seed; ONE aligned family resample per rep is applied to
every (model, arch) group so cross-group contrasts are paired):
  rates         per (model, arch, cell)
  uplift vs N   per (model, arch, A-cell)
  content main effects per (model, arch):
                eff_match = 0.5*(r_A11 + r_A10) - r_A00   (their "matched
                          content works" main effect, pooling replay + struct)
                eff_trap  = r_A01 - r_A00
  arch main effect per content level: r_raw - r_proc per cell (+ matched)
  interaction in THEIR framing:
                I_match = eff_match(raw) - eff_match(proc)
                I_trap  = eff_trap(raw)  - eff_trap(proc)
                leg decomposition I_match = 0.5*(D_A11 + D_A10) with
                D_A11 = (r_A11_raw - r_A00_raw) - (r_A11_proc - r_A00_proc)
                D_A10 = (r_A10_raw - r_A00_raw) - (r_A10_proc - r_A00_proc)
  KEY split (what P x S sees and arch x content cannot):
                split = r_A11 - r_A10  (= tau_replaylike: replay vs
                structural transfer INSIDE the same "program-matched"
                content level), per (model, arch), plus the two legs
                leg11 = r_A11 - r_A00 and leg10 = r_A10 - r_A00.

Holm family (declared up front, m=3): split@7b, split@3b, I_match.
Everything else carries CIs without multiplicity claims.

Run (from repo root):
  python pilot/gatec/transplants_2x2.py
Outputs:
  pilot/gatec/transplants_2x2_results.json
  (console prints the same tables)
"""

import glob
import json
import os
import platform
import sys
from collections import defaultdict

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_PILOT = os.path.dirname(_HERE)
_REPO = os.path.dirname(_PILOT)
sys.path.insert(0, _PILOT)

from generate_families import load_config  # noqa: E402

CONFIG = os.path.join(_PILOT, "configs", "pilot_7b.yaml")
OUT_JSON = os.path.join(_HERE, "transplants_2x2_results.json")

CELLS = ["A00", "A01", "A10", "A11", "N", "Q"]
A_CELLS = ["A00", "A01", "A10", "A11"]
MODELS = ["qwen7b", "qwen3b"]
ARCHS = ["procedural", "raw"]  # raw: qwen7b only

# groups that actually exist on disk: (model, arch) -> rollout glob
GROUPS = {
    ("qwen7b", "procedural"): "rollouts_qwen7b_shard*-of-*.jsonl",
    ("qwen3b", "procedural"): "rollouts_qwen3b_shard*-of-*.jsonl",
    ("qwen7b", "raw"): "rollouts_hc_raw_qwen7b_shard*-of-*.jsonl",
}

HOLM_TESTS = ["split@qwen7b", "split@qwen3b", "I_match"]


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------

def load_group_rows(out_root, pattern, want_model, want_system):
    """Return list of (family_idx, sibling_idx, seed, cell, success)."""
    rows = []
    files = sorted(glob.glob(os.path.join(out_root, pattern)))
    # never let hc files leak into procedural groups or vice versa
    if want_system == "procedural":
        files = [f for f in files if "_hc_" not in os.path.basename(f)]
    for fn in files:
        with open(fn) as f:
            for line in f:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                m = r.get("meta", {})
                if m.get("model", want_model) != want_model:
                    continue
                if m.get("system", "procedural") != want_system:
                    continue
                rows.append((m["family_idx"], m["sibling_idx"], m["seed"],
                             m["cell"], bool(r["success"])))
    return rows, files


def family_cell_counts(rows, fam_universe):
    """cell -> (succ[F], n[F]) aligned with fam_universe."""
    fpos = {f: i for i, f in enumerate(fam_universe)}
    succ = {c: np.zeros(len(fam_universe)) for c in CELLS}
    n = {c: np.zeros(len(fam_universe)) for c in CELLS}
    for f, s, sd, c, ok in rows:
        succ[c][fpos[f]] += float(ok)
        n[c][fpos[f]] += 1.0
    return succ, n


# ---------------------------------------------------------------------------
# per-group estimands given a family index vector
# ---------------------------------------------------------------------------

def rates_at(succ, n, idx):
    r = {}
    for c in CELLS:
        den = n[c][idx].sum()
        r[c] = succ[c][idx].sum() / den if den else float("nan")
    return r


def group_stats(succ, n, idx):
    r = rates_at(succ, n, idx)
    matched = 0.5 * (r["A11"] + r["A10"])
    return {
        "rates": r,
        "matched": matched,
        "eff_match": matched - r["A00"],
        "eff_trap": r["A01"] - r["A00"],
        "split": r["A11"] - r["A10"],
        "leg11": r["A11"] - r["A00"],
        "leg10": r["A10"] - r["A00"],
        "uplift": {c: r[c] - r["N"] for c in A_CELLS},
    }


def cross_stats(g_raw, g_proc):
    """raw - proc contrasts given this rep's group stats."""
    out = {}
    for c in A_CELLS + ["N", "Q"]:
        out["arch_%s" % c] = g_raw["rates"][c] - g_proc["rates"][c]
    out["arch_matched"] = g_raw["matched"] - g_proc["matched"]
    out["I_match"] = g_raw["eff_match"] - g_proc["eff_match"]
    out["I_trap"] = g_raw["eff_trap"] - g_proc["eff_trap"]
    out["D_A11"] = g_raw["leg11"] - g_proc["leg11"]
    out["D_A10"] = g_raw["leg10"] - g_proc["leg10"]
    out["delta_split_raw_proc"] = g_raw["split"] - g_proc["split"]
    return out


# ---------------------------------------------------------------------------
# bootstrap driver
# ---------------------------------------------------------------------------

def run_bootstrap(counts, nboot, seed):
    groups = list(counts.keys())
    F = len(next(iter(next(iter(counts.values()))[0].values())))
    rng = np.random.default_rng(seed)
    boot_group = {g: defaultdict(list) for g in groups}
    boot_cross = defaultdict(list)
    for _ in range(nboot):
        idx = rng.integers(0, F, F)
        stats = {}
        for g in groups:
            succ, n = counts[g]
            st = group_stats(succ, n, idx)
            stats[g] = st
            for c in CELLS:
                boot_group[g]["rate_%s" % c].append(st["rates"][c])
            for k in ("matched", "eff_match", "eff_trap", "split",
                      "leg11", "leg10"):
                boot_group[g][k].append(st[k])
            for c in A_CELLS:
                boot_group[g]["uplift_%s" % c].append(st["uplift"][c])
        if ("qwen7b", "raw") in stats and ("qwen7b", "procedural") in stats:
            for k, v in cross_stats(stats[("qwen7b", "raw")],
                                    stats[("qwen7b", "procedural")]).items():
                boot_cross[k].append(v)
        # cross-model procedural split (descriptive)
        boot_cross["delta_split_7b_3b"].append(
            stats[("qwen7b", "procedural")]["split"]
            - stats[("qwen3b", "procedural")]["split"])
    return boot_group, boot_cross


def point_estimates(counts, fam_universe):
    idx = np.arange(len(fam_universe))
    stats = {g: group_stats(*counts[g], idx) for g in counts}
    cross = {}
    if ("qwen7b", "raw") in stats:
        cross = cross_stats(stats[("qwen7b", "raw")],
                            stats[("qwen7b", "procedural")])
    cross["delta_split_7b_3b"] = (stats[("qwen7b", "procedural")]["split"]
                                  - stats[("qwen3b", "procedural")]["split"])
    return stats, cross


def ci_p(vals, pe):
    v = np.asarray(vals, float)
    lo, hi = float(np.quantile(v, 0.025)), float(np.quantile(v, 0.975))
    p = min(1.0, 2 * min(float(np.mean(v <= 0)), float(np.mean(v >= 0))))
    return {"est": float(pe), "ci": [lo, hi], "p_boot": p,
            "ci_excludes_zero": bool(lo > 0 or hi < 0)}


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
# main
# ---------------------------------------------------------------------------

def main():
    cfg = load_config(CONFIG)
    os.environ.setdefault("HF_HOME", cfg["paths"]["hf_home"])
    seed = cfg["analysis"]["bootstrap_seed"]
    nboot = 2000  # GATE_PROTOCOL Part II sec.10 grid convention (not the 10k
                  # Gate-A value: this module reuses the Part II setting)

    out_root = cfg["paths"]["output_root"]
    rows_by_group, files_by_group, n_by_group = {}, {}, {}
    for (model, arch), pat in GROUPS.items():
        rows, files = load_group_rows(out_root, pat, model, arch)
        rows_by_group[(model, arch)] = rows
        files_by_group["%s|%s" % (model, arch)] = files
        n_by_group["%s|%s" % (model, arch)] = len(rows)

    fam_universe = sorted({r[0] for rows in rows_by_group.values() for r in rows})
    counts = {g: family_cell_counts(rows, fam_universe)
              for g, rows in rows_by_group.items()}

    boot_group, boot_cross = run_bootstrap(counts, nboot, seed)
    stats, cross_pe = point_estimates(counts, fam_universe)

    # ---- assemble results -------------------------------------------------
    res_groups = {}
    for g in groups_sorted(rows_by_group):
        key = "%s|%s" % g
        st = stats[g]
        pe = {}
        for c in CELLS:
            pe["rate_%s" % c] = ci_p(boot_group[g]["rate_%s" % c],
                                     st["rates"][c])
        for k in ("matched", "eff_match", "eff_trap", "split", "leg11",
                  "leg10"):
            pe[k] = ci_p(boot_group[g][k], st[k])
        for c in A_CELLS:
            pe["uplift_%s" % c] = ci_p(boot_group[g]["uplift_%s" % c],
                                       st["uplift"][c])
        res_groups[key] = pe

    res_cross = {}
    for k, vals in boot_cross.items():
        res_cross[k] = ci_p(vals, cross_pe[k])

    pvals = []
    for t in HOLM_TESTS:
        if t == "I_match":
            pvals.append((t, res_cross["I_match"]["p_boot"]))
        else:
            model = t.split("@")[1]
            pvals.append((t, res_groups["%s|procedural" % model]["split"]
                          ["p_boot"]))
    holm_adj = holm(pvals)

    results = {
        "module": "gatec_cond1_transplants_2x2",
        "registered_context": ("NEXT_ACTION.md Gate C-lite cond1; analysis of "
                               "existing rollouts only; bootstrap convention "
                               "follows GATE_PROTOCOL Part II sec.10 "
                               "(family-cluster, 2000 reps)"),
        "bootstrap": {"reps": nboot, "seed": seed, "cluster": "family",
                      "aligned_across_groups": True},
        "factors": {
            "arch": {"procedural": "pilot procedural cards (Memp/AWM-style "
                                   "write-path representation)",
                     "raw": "H-C raw transcript cards (Reflexion/ExpeL-style "
                            "full-trajectory representation), qwen7b only"},
            "content": {"matched_correct_A11uA10": "program-matched content; "
                        "A10 source_kind=cross_domain_pair (a10_partner in "
                        "another domain rendering = code->math analogue), "
                        "A11 source_kind=sibling_same_family",
                        "near_miss_A01": "near-miss content (P=0,S=1)",
                        "unrelated_A00": "unrelated content (P=0,S=0)"},
            "note_qwen3b": "raw arch unavailable at qwen3b (H-C grid was "
                           "qwen7b-only); qwen3b contributes the procedural "
                           "content axis + P x S split only. No data "
                           "fabricated."},
        "env": {"python": sys.version.split()[0], "numpy": np.__version__,
                "platform": platform.platform()},
        "inputs": {"files": files_by_group, "n_rollouts": n_by_group,
                   "families": len(fam_universe)},
        "group_estimates": res_groups,
        "cross_group_estimates": res_cross,
        "holm_family_m3": {k: {"p_raw": dict(pvals)[k],
                               "p_holm": holm_adj[k],
                               "reject_0.05": bool(holm_adj[k] < 0.05)}
                           for k, _ in pvals},
    }
    # readability: replay-share decomposition (point estimates)
    for g in groups_sorted(rows_by_group):
        key = "%s|%s" % g
        st = stats[g]
        denom = st["eff_match"]
        results.setdefault("replay_share_of_matched_effect", {})[key] = {
            "eff_match_pooled": st["eff_match"],
            "leg11_A11_minus_A00": st["leg11"],
            "leg10_A10_minus_A00": st["leg10"],
            "frac_from_A11_leg": (0.5 * st["leg11"] / denom
                                  if abs(denom) > 1e-9 else None),
            "frac_from_A10_leg": (0.5 * st["leg10"] / denom
                                  if abs(denom) > 1e-9 else None),
        }

    with open(OUT_JSON, "w") as f:
        json.dump(results, f, indent=1)

    # ---- console tables ---------------------------------------------------
    print("[env] python=%s numpy=%s seed=%d reps=%d"
          % (sys.version.split()[0], np.__version__, seed, nboot))
    for g in groups_sorted(rows_by_group):
        print("[load] %s|%s: %d rollouts" % (g[0], g[1], len(rows_by_group[g])))
    print("\n=== cell success rates (family-cluster bootstrap 95% CI) ===")
    hdr = "%-20s" % "group" + "".join("%14s" % c for c in CELLS)
    print(hdr)
    for g in groups_sorted(rows_by_group):
        key = "%s|%s" % g
        row = "%-20s" % key
        for c in CELLS:
            d = res_groups[key]["rate_%s" % c]
            row += "  %5.3f[%5.3f,%5.3f]" % (d["est"], d["ci"][0], d["ci"][1])
        print(row)
    print("\n=== content main effects per (model,arch) ===")
    for g in groups_sorted(rows_by_group):
        key = "%s|%s" % g
        em, et = res_groups[key]["eff_match"], res_groups[key]["eff_trap"]
        print("%-20s matched-A00=%+.3f[%+.3f,%+.3f]  near-miss-A00=%+.3f"
              "[%+.3f,%+.3f]"
              % (key, em["est"], em["ci"][0], em["ci"][1],
                 et["est"], et["ci"][0], et["ci"][1]))
    print("\n=== arch (raw - procedural) per content level, qwen7b ===")
    for k in ("arch_A00", "arch_A01", "arch_A10", "arch_A11", "arch_matched"):
        d = res_cross[k]
        print("%-14s %+.3f[%+.3f,%+.3f] p=%.4f"
              % (k, d["est"], d["ci"][0], d["ci"][1], d["p_boot"]))
    print("\n=== interaction in THEIR framing (qwen7b) ===")
    for k in ("I_match", "I_trap", "D_A11", "D_A10",
              "delta_split_raw_proc"):
        d = res_cross[k]
        print("%-18s %+.3f[%+.3f,%+.3f] p=%.4f"
              % (k, d["est"], d["ci"][0], d["ci"][1], d["p_boot"]))
    print("\n=== KEY split: A11(replay) vs A10(structural) inside the same "
          "'program-matched' content ===")
    for g in groups_sorted(rows_by_group):
        key = "%s|%s" % g
        sp = res_groups[key]["split"]
        l11, l10 = res_groups[key]["leg11"], res_groups[key]["leg10"]
        em = res_groups[key]["eff_match"]
        rs = results["replay_share_of_matched_effect"][key]
        print("%-20s pooled-matched=%+.3f  A11-A00=%+.3f  A10-A00=%+.3f  "
              "split(A11-A10)=%+.3f[%+.3f,%+.3f] p=%s  A11-fraction=%s"
              % (key, em["est"], l11["est"], l10["est"], sp["est"],
                 sp["ci"][0], sp["ci"][1], "%.4f" % sp["p_boot"],
                 ("%.2f" % rs["frac_from_A11_leg"]
                  if rs["frac_from_A11_leg"] is not None else "n/a")))
    d = res_cross["delta_split_7b_3b"]
    print("cross-model delta split (7B-3B, procedural): %+.3f[%+.3f,%+.3f]"
          % (d["est"], d["ci"][0], d["ci"][1]))
    print("\n=== Holm family (m=%d) ===" % len(HOLM_TESTS))
    for k, v in results["holm_family_m3"].items():
        print("%-16s p_raw=%.4f p_holm=%.4f reject=%s"
              % (k, v["p_raw"], v["p_holm"], v["reject_0.05"]))
    print("\n[write] %s" % OUT_JSON)


def groups_sorted(d):
    order = {("qwen7b", "procedural"): 0, ("qwen3b", "procedural"): 1,
             ("qwen7b", "raw"): 2}
    return sorted(d.keys(), key=lambda g: order.get(g, 9))


if __name__ == "__main__":
    main()
