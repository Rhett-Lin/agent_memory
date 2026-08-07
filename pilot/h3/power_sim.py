"""H3 power simulation (GATE_PROTOCOL.md Part III sec.16, frozen):

"功效：按 pilot family-level covariance 模拟，目标 ε_form=8pp 时 power ≥ 0.8；
不足时先加 family（至 32）不加 seed"。

Simulates the H3 ε_form contrast (family-cluster bootstrap CI) using the
pilot qwen7b rollouts as the empirical source of family-level covariance:

  * For each pilot family we observe 16 A11 outcomes (4 sib x 4 seeds) and
    16 N outcomes.  A simulated H3 experiment of size F resamples F pilot
    families with replacement; each simulated family's latent arm rate is
    drawn from the Beta(1+succ, 1+fail) posterior of its observed outcomes
    (script/transcript-complete anchor = A11 outcomes; sensitivity anchor =
    N outcomes), the 8pp form effect is added on the identity (risk)
    scale to the script-complete arm, and 12 binary outcomes per cell
    (4 sib x 3 seeds, the H3 grid shape) are drawn.
  * ε_form is then estimated exactly like the planned analysis: paired
    family-cluster bootstrap percentile 95% CI of
    ε = rate(script_complete) - rate(transcript_complete)  (the shared N
    reference cancels in the contrast).
  * power(F) = fraction of simulated experiments whose CI excludes 0.

Decision rule (frozen): if power(24) >= 0.8 -> keep 24 families; else bump
to 32 (the single allowed lever) and record.  Both grid shapes are always
reported.  Output: pilot/h3/power_sim.json.  This script is CPU-only and
must run BEFORE the full grid (it reads only pilot rollout files).

Run (from pilot/h3/):
  $PY power_sim.py [--n-sims 500] [--boot-reps 500]
"""

import argparse
import glob
import json
import os
import time

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))

PILOT_7B = "/work1/zixuan/outputs/agent_memory/pilot/rollouts_qwen7b_shard*-of-*.jsonl"
SIM_SEED = 20260809
UNITS_PER_CELL = 12          # 4 siblings x 3 decode seeds (H3 grid, sec.16)
EFFECT = 0.08                # frozen target effect epsilon_form = 8pp
POWER_TARGET = 0.80
FAMILY_CHOICES = [24, 32]    # sec.16 lever: 24 -> 32 max


def load_pilot_family_outcomes():
    """family_idx -> {"A11": [0/1...], "N": [0/1...]} (qwen7b procedural)."""
    by_fam = {}
    for fn in sorted(glob.glob(PILOT_7B)):
        if "_hc_" in fn:
            continue
        with open(fn) as f:
            for line in f:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                m = r.get("meta", {})
                if m.get("model") != "qwen7b":
                    continue
                cell = m.get("cell")
                if cell not in ("A11", "N"):
                    continue
                by_fam.setdefault(m["family_idx"], {}).setdefault(cell, []).append(
                    1 if r["success"] else 0)
    return by_fam


def sim_once(fam_pool, F, anchor, rng, boot_reps, boot_seed_rng):
    """One simulated H3 experiment + cluster-bootstrap CI of epsilon_form.
    fam_pool: list of pilot family outcome dicts."""
    picks = rng.integers(0, len(fam_pool), F)
    cols = {"sc": np.zeros(F), "tc": np.zeros(F), "n": np.zeros(F)}
    for i, pi in enumerate(picks):
        fam = fam_pool[pi]
        obs = fam[anchor]
        p_tc = rng.beta(1 + sum(obs), 1 + len(obs) - sum(obs))
        p_sc = min(1.0, p_tc + EFFECT)
        obs_n = fam["N"]
        p_n = rng.beta(1 + sum(obs_n), 1 + len(obs_n) - sum(obs_n))
        cols["sc"][i] = rng.binomial(UNITS_PER_CELL, p_sc)
        cols["tc"][i] = rng.binomial(UNITS_PER_CELL, p_tc)
        cols["n"][i] = rng.binomial(UNITS_PER_CELL, p_n)
    U = UNITS_PER_CELL
    est = cols["sc"].sum() / (F * U) - cols["tc"].sum() / (F * U)
    boots = []
    for _ in range(boot_reps):
        idx = boot_seed_rng.integers(0, F, F)
        boots.append((cols["sc"][idx].sum() - cols["tc"][idx].sum())
                     / (F * U * 1.0))
    lo, hi = np.quantile(boots, [0.025, 0.975])
    return est, lo, hi


def power_for(F, fam_pool, anchor, n_sims, boot_reps, rng):
    brng = np.random.default_rng(SIM_SEED + 7 + F)
    ests, half, sig = [], [], 0
    for _ in range(n_sims):
        est, lo, hi = power_for_one(F, fam_pool, anchor, rng, boot_reps, brng)
        ests.append(est)
        half.append((hi - lo) / 2)
        sig += 1 if (lo > 0 or hi < 0) else 0
    return {"power": sig / n_sims, "n_sims": n_sims,
            "mean_est": float(np.mean(ests)),
            "mean_ci_halfwidth": float(np.mean(half))}


def power_for_one(F, fam_pool, anchor, rng, boot_reps, brng):
    return sim_once(fam_pool, F, anchor, rng, boot_reps, brng)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-sims", type=int, default=500)
    ap.add_argument("--boot-reps", type=int, default=500)
    args = ap.parse_args()
    t0 = time.time()
    by_fam = load_pilot_family_outcomes()
    fam_pool = [v for _, v in sorted(by_fam.items())
                if "A11" in v and "N" in v]
    print("[power] %d pilot families with A11+N outcomes; units per cell=%d"
          % (len(fam_pool), UNITS_PER_CELL))
    a11_rates = [np.mean(v["A11"]) for v in fam_pool]
    n_rates = [np.mean(v["N"]) for v in fam_pool]
    print("[power] pilot family A11 rate: mean=%.3f sd=%.3f | N rate: "
          "mean=%.3f sd=%.3f"
          % (np.mean(a11_rates), np.std(a11_rates, ddof=1),
             np.mean(n_rates), np.std(n_rates, ddof=1)))

    report = {"frozen": {"effect_epsilon_form": EFFECT,
                         "power_target": POWER_TARGET,
                         "units_per_cell": UNITS_PER_CELL,
                         "family_lever": FAMILY_CHOICES,
                         "lever_rule": "add families (24->32), never seeds "
                                       "(GPT-5.6 clause, sec.16)"},
              "sim": {"n_sims": args.n_sims, "boot_reps": args.boot_reps,
                      "seed": SIM_SEED,
                      "anchor_primary": "pilot_A11_family_rates",
                      "anchor_sensitivity": "pilot_N_family_rates",
                      "note": "N reference cancels in epsilon_form; simulated "
                              "contrast = rate(sc)-rate(tc)"},
              "pilot_family_covariance": {
                  "n_families": len(fam_pool),
                  "a11_rate_mean": float(np.mean(a11_rates)),
                  "a11_rate_sd": float(np.std(a11_rates, ddof=1)),
                  "n_rate_mean": float(np.mean(n_rates)),
                  "n_rate_sd": float(np.std(n_rates, ddof=1))},
              "results": {}}
    for anchor in ("A11", "N"):
        for F in FAMILY_CHOICES:
            rng = np.random.default_rng(SIM_SEED + F + (0 if anchor == "A11" else 1000))
            r = power_for(F, fam_pool, anchor, args.n_sims, args.boot_reps, rng)
            report["results"]["%s_anchor_F%d" % (anchor, F)] = r
            print("[power] anchor=%s F=%d: power=%.3f (mean est=%.3f, "
                  "CI half-width=%.3f)"
                  % (anchor, F, r["power"], r["mean_est"],
                     r["mean_ci_halfwidth"]))
    primary24 = report["results"]["A11_anchor_F24"]["power"]
    decision = 24 if primary24 >= POWER_TARGET else 32
    report["decision"] = {
        "n_families": decision,
        "rule": "power(24, A11 anchor) >= 0.8 -> 24 else 32",
        "power_24_primary": primary24,
        "power_32_primary": report["results"]["A11_anchor_F32"]["power"],
        "recorded": time.strftime("%Y-%m-%d %H:%M:%S %Z", time.gmtime()),
        "action": ("keep configs/h3.yaml n_families=24" if decision == 24 else
                   "set configs/h3.yaml n_families=32 and re-run "
                   "gen_fresh_families.py --generate BEFORE building cards"),
    }
    report["elapsed_sec"] = round(time.time() - t0, 1)
    out = os.path.join(_HERE, "power_sim.json")
    with open(out, "w") as f:
        json.dump(report, f, indent=1)
    print("[power] DECISION: n_families=%d (power24=%.3f, power32=%.3f) -> %s"
          % (decision, primary24, report["results"]["A11_anchor_F32"]["power"],
             out))


if __name__ == "__main__":
    main()
