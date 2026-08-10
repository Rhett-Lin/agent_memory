"""Part V-A $A5 feasibility gate: reproducible cache-consistent Monte Carlo
of the FULL source-attempt contract ($A2) + tuple-constrained matching
($A3), executed BEFORE any GPU harvest.

CPU ONLY.  No episode is ever run; no rollout outcome is ever inspected.
The simulation draws per-(candidate, role) attempt streams as iid
Bernoulli(p) attempts (per-attempt win prob p, the preregistered
sensitivity model), <=8 cached attempts per candidate (eligibility = >=1
win within <=8 attempts, A2.3), then runs the EXACT matcher of
allocator.py on the resulting eligibility set.

Frozen gate ($A5): 10,000 draws, seeds 20260811..20270811 (inclusive);
report the distribution of completed confirmatory-heat / confirmatory-cool
cluster counts; the 5th percentile must be >= 50 for BOTH types at
p = 0.17 (the preregistered sensitivity point).  Otherwise the gate is
FAIL and Part V is NOT_ESTIMATED -- the amendment's finality clause
forbids parameter shopping; this script changes nothing when the verdict
is FAIL.

p grid (frozen before the first run): {0.17 (preregistered sensitivity),
0.20, 0.30, 0.50}.

MODELING CHOICES (all fixed before the first run; see allocator.py D1-D6):
  M1. Eligibility per (candidate, role) is drawn ONCE per draw and shared
      cache-consistently with every consumer (the matcher sees exactly the
      eligibility the contract ledger would have recorded; the same
      attempt key is never executed twice, consistent with the MD5-seeded
      deterministic decode rule).
  M2. Attempt streams are drawn per seed with numpy PCG64(seed); seeds are
      the 10,000 consecutive integers 20260811..20270811.  These are
      simulation streams only -- never the frozen rng_screen/rng_rollout.
  M3. Attempts stop at the first win (early stop), matching the real
      harvest; the attempt-count distribution is reported as a budget
      reference (~harvest episode count), it does not affect the gate.
  M4. The matcher is allocator.match_allocation -- the very code path the
      real harvest will consume.  No idealized variant is simulated.
  M5. A partial-slot designator (targets designated with 1-2 slots per
      role when full k=2 bundles do not fit) is included ONLY as an
      informational sensitivity envelope on the k-slot reading of $A4
      ("candidate slots k=2 per role per target"); the gate verdict uses
      the atomic-bundle allocator, and both readings are reported.
  M6. Attempt-order effects within a tuple: none exist under the contract
      (all designated candidates are attempted to decision; matching runs
      afterwards on eligibility; per-tuple capacity = min(#targets,
      #eligible R, #eligible X)).  The simulation is therefore exact, not
      approximate, for the gate-relevant counts.
"""

import argparse
import json
import os
import time
from collections import defaultdict

import numpy as np

from pilot.external.partv import allocator
from pilot.external.partv import common
from pilot.external.partv import prepare_pools

P_GRID = (0.17, 0.20, 0.30, 0.50)
GATE_P = 0.17
GATE_SEED_FIRST = 20260811
N_DRAWS = 10000
GATE_REQUIRED = 50                      # $A5: 5th percentile >= 50 both types
REPORT_PATH = os.path.join(common.OUT_ROOT, "feasibility_gate_report.json")

MAX_ATTEMPTS = allocator.MAX_GLOBAL_ATTEMPTS
CONF_POOLS = ("confirmatory-heat", "confirmatory-cool")


# ---------------------------------------------------------------------------
# per-seed attempt streams (M1/M2/M3)
# ---------------------------------------------------------------------------

def draw_eligibility(cand_paths, seeds, p):
    """-> (eligible[E bool (n_cand, n_seeds)], attempts_used[uint8 same]).

    Attempts are iid Bernoulli(p), early-stopped at the first win; the
    per-(candidate, role) stream is drawn once per seed (cache-consistent).
    """
    n_c, n_s = len(cand_paths), len(seeds)
    eligible = np.zeros((n_c, n_s), dtype=bool)
    used = np.full((n_c, n_s), MAX_ATTEMPTS, dtype=np.int8)
    for j, s in enumerate(seeds):
        g = np.random.Generator(np.random.PCG64(int(s)))
        wins = g.random((n_c, MAX_ATTEMPTS)) < p
        elig = wins.any(axis=1)
        eligible[:, j] = elig
        # attempts consumed: first winning index + 1, else all 8
        used[elig, j] = wins[elig].argmax(axis=1) + 1
    return eligible, used


# ---------------------------------------------------------------------------
# exact matcher counts, vectorized over seeds (M4)
# ---------------------------------------------------------------------------

def precompute_groups(assignment, ordered_cands):
    """Index the designation into per-tuple groups:
       confirm[pool] -> [(n_targets_u, R_idx_u, X_idx_u), ...]
       mandatory[(pool, prep)] -> [(n_targets_u, role_idx_u), ...]"""
    idx = {p: i for i, p in enumerate(ordered_cands)}
    confirm, mandatory = {}, {}
    for pool in CONF_POOLS:
        prep = "heat" if pool.endswith("heat") else "cool"
        tg = defaultdict(int)
        for t in assignment["targets"].get(pool, []):
            tg[t["tuple_key"]] += 1
        groups = {}
        for tkey in tg:
            r_idx = [idx[p] for p, rec in assignment["candidates"].items()
                     if rec["pool"] == pool and rec["tuple_key"] == tkey
                     and rec["role"] == "R"]
            x_idx = [idx[p] for p, rec in assignment["candidates"].items()
                     if rec["pool"] == pool and rec["tuple_key"] == tkey
                     and rec["role"] == "X"]
            groups[tkey] = (tg[tkey], np.array(sorted(r_idx)),
                            np.array(sorted(x_idx)))
        confirm[pool] = [g for _k, g in sorted(
            groups.items(), key=lambda kv: allocator._sha(kv[0]))]
    for pool in allocator.MANDATORY_POOLS:
        role = "R" if pool == "calibration" else "X"
        for prep in ("heat", "cool"):
            tg = defaultdict(int)
            for t in assignment["targets"].get(pool, []):
                if t["type"] == prep:
                    tg[t["tuple_key"]] += 1
            groups = {}
            for tkey in tg:
                e_idx = [idx[p] for p, rec
                         in assignment["candidates"].items()
                         if rec["pool"] == pool and rec["pool_type"] == prep
                         and rec["role"] == role
                         and rec["tuple_key"] == tkey]
                groups[tkey] = (tg[tkey], np.array(sorted(e_idx)))
            mandatory[(pool, prep)] = [g for _k, g in sorted(
                groups.items(), key=lambda kv: allocator._sha(kv[0]))]
    return {"confirm": confirm, "mandatory": mandatory}


def match_counts(groups, eligible):
    """Exact $A3 counts per seed (min-truncation is the matcher capacity)."""
    out = {}
    for pool, tuples in groups["confirm"].items():
        tot = np.zeros(eligible.shape[1], dtype=np.int64)
        for d, r_idx, x_idx in tuples:
            e_r = eligible[r_idx].sum(axis=0) if len(r_idx) else 0
            e_x = eligible[x_idx].sum(axis=0) if len(x_idx) else 0
            tot += np.minimum(d, np.minimum(e_r, e_x))
        out[pool] = np.minimum(tot, allocator.CONFIRMATORY_REQUIRED)
    fills = dict((n, f) for n, _r, _d, f in allocator.POOL_SPECS_V2)
    for (pool, prep), tuples in groups["mandatory"].items():
        tot = np.zeros(eligible.shape[1], dtype=np.int64)
        for d, e_idx in tuples:
            e = eligible[e_idx].sum(axis=0) if len(e_idx) else 0
            tot += np.minimum(d, e)
        out[(pool, prep)] = np.minimum(tot, fills[pool])
    return out


def _crosscheck_exact_matcher(assignment, groups, eligible, n_check=8):
    """Verify the vectorized counts equal allocator.match_allocation
    cluster counts on a few draws (guards M4: no idealized variant)."""
    for j in range(min(n_check, eligible.shape[1])):
        el = {p for p, ok in zip(
            sorted(assignment["candidates"]), eligible[:, j]) if ok}
        ref = allocator.match_allocation(assignment, el)
        fast = match_counts(groups, eligible[:, [j]])
        for pool in CONF_POOLS:
            got = int(fast[pool][0])
            want = ref["counts"][pool]["heat" if pool.endswith("heat")
                                      else "cool"]
            assert got == want, (pool, got, want, j)
    return True


# ---------------------------------------------------------------------------
# informational sensitivity designator (M5): partial slots when bundles
# do not fit; NOT the allocator, only an envelope on the k-slot reading.
# ---------------------------------------------------------------------------

def build_assignment_partial():
    table, _ = prepare_pools.build_game_table()
    orders = prepare_pools.screening_orders(table)
    world = allocator.build_tuple_world(table, orders)
    info_by_path, walk = {}, {"heat": [], "cool": []}
    for prep in ("heat", "cool"):
        for gi in orders[prep]:
            inf = table[prep][gi]
            info_by_path[inf["path"]] = inf
            walk[prep].append(inf["path"])
    d = allocator.Designator(world, info_by_path, walk)
    d.designate_calibration()
    d.designate_headroom("headroom-A")
    d.designate_headroom("headroom-B")
    # confirmatory: balanced interleave; a target is designated whenever
    # its tuple can still fund >=1 slot in each role (slots = min(2, rem))
    open_type = {"heat": True, "cool": True}
    cap = 60
    while open_type["heat"] or open_type["cool"]:
        for prep in ("heat", "cool"):
            if not open_type[prep]:
                continue
            if len(d.targets["confirmatory-%s" % prep]) >= cap:
                open_type[prep] = False
                continue
            opp = allocator.OPPOSITE[prep]
            placed = False
            for path in walk[prep]:
                if path in d.used:
                    continue
                inf = d.info[path]
                tkey = "%s|%s" % (inf["obj"], inf["recep"])
                if d.rem[tkey][prep] < 2 or d.rem[tkey][opp] < 1:
                    continue
                tgt = d._first_free(tkey, prep, 1)
                n_r = min(2, d.rem[tkey][prep] - 1)
                n_x = min(2, d.rem[tkey][opp])
                r_sl = d._first_free(tkey, prep, 1 + n_r)[1:]
                x_sl = d._first_free(tkey, opp, n_x)
                if tgt is None or r_sl is None or x_sl is None:
                    continue
                d._designate("confirmatory-%s" % prep, prep, tkey,
                             {"R": r_sl, "X": x_sl}, tgt[0])
                placed = True
                break
            if not placed:
                open_type[prep] = False
    return {"targets": dict(d.targets), "candidates": d.candidates,
            "used": d.used, "world": world, "info": info_by_path}


# ---------------------------------------------------------------------------
# statistics + gate
# ---------------------------------------------------------------------------

def summarize(counts):
    counts = np.asarray(counts)
    return {
        "n": int(counts.size),
        "mean": float(counts.mean()),
        "sd": float(counts.std(ddof=1)),
        "min": int(counts.min()),
        "p05": float(np.percentile(counts, 5)),
        "p25": float(np.percentile(counts, 25)),
        "median": float(np.percentile(counts, 50)),
        "p75": float(np.percentile(counts, 75)),
        "p95": float(np.percentile(counts, 95)),
        "max": int(counts.max()),
        "P_ge_required": float((counts >= GATE_REQUIRED).mean()),
    }


def run_sim(n_draws=N_DRAWS, seed_first=GATE_SEED_FIRST,
            extra_readings=True, out_path=REPORT_PATH, log=print):
    seeds = [seed_first + i for i in range(n_draws)]
    full_run = (n_draws == N_DRAWS and seed_first == GATE_SEED_FIRST)
    designation = allocator.build_assignment()
    d_stats = allocator.designation_stats(designation)
    cand_sorted = sorted(designation["candidates"])
    groups = precompute_groups(designation, cand_sorted)

    report = {
        "schema": "partv.feasibility.v1",
        "amendment": allocator.AMENDMENT_ID,
        "frozen": {"seeds_first": seed_first, "n_draws": n_draws,
                   "seed_rule": "consecutive integers PCG64(seed)",
                   "p_grid": list(P_GRID), "gate_p": GATE_P,
                   "gate_rule": ("5th percentile of completed confirmatory "
                                 "counts >= 50 for BOTH heat and cool at "
                                 "p=0.17"),
                   "max_attempts": MAX_ATTEMPTS,
                   "k_slots": allocator.K_SLOTS},
        "modeling_choices": ["M1", "M2", "M3", "M4", "M5", "M6"],
        "notes_modeling": {
            "M1": "per-(candidate, role) eligibility drawn once per draw, "
                  "cache-consistent with the matching (A2.2)",
            "M2": "per-seed PCG64(seed) streams; never rng_screen/rollout",
            "M3": "early stop at first win; attempt counts are budget "
                  "reference only",
            "M4": "matching executed by allocator.match_allocation itself; "
                  "vectorized counts cross-checked against it",
            "M5": "partial-slot designator is informational sensitivity "
                  "only, never the gate",
            "M6": "no attempt-order effects under the contract; simulation "
                  "exact for gate counts"},
        "diagnostic_only": not full_run,
        "designation": d_stats,
        "readings": {},
    }

    readings = {"allocator_k2_bundle": (designation, groups)}
    if extra_readings:
        part = build_assignment_partial()
        cand_sorted_p = sorted(part["candidates"])
        groups_p = precompute_groups(part, cand_sorted_p)
        readings["sensitivity_partial_slots"] = (part, groups_p)
        report["designation_sensitivity"] = {
            "confirmatory_targets": {
                "heat": len(part["targets"]["confirmatory-heat"]),
                "cool": len(part["targets"]["confirmatory-cool"])},
        }

    for name, (asg, grp) in readings.items():
        cand_order = sorted(asg["candidates"])
        per_p = {}
        for p in P_GRID:
            t0 = time.time()
            eligible, used = draw_eligibility(cand_order, seeds, p)
            if name == "allocator_k2_bundle" and p == P_GRID[0]:
                _crosscheck_exact_matcher(asg, grp, eligible)
            counts = match_counts(grp, eligible)
            row = {
                "confirmatory-heat": summarize(counts["confirmatory-heat"]),
                "confirmatory-cool": summarize(counts["confirmatory-cool"]),
                "attempts_total_mean": float(used.sum(axis=0).mean()),
                "attempts_total_sd": float(used.sum(axis=0).std(ddof=1)),
                "mandatory_met_rate": {},
            }
            fill_map = {"calibration": allocator.CALIBRATION_REQUIRED,
                        "headroom-A": allocator.HEADROOM_REQUIRED,
                        "headroom-B": allocator.HEADROOM_REQUIRED}
            for k, arr in counts.items():
                if isinstance(k, tuple):
                    pool, prep = k
                    ok = arr >= fill_map[pool]
                    row["mandatory_met_rate"]["%s:%s" % k] = float(ok.mean())
            row["seconds"] = round(time.time() - t0, 3)
            per_p[str(p)] = row
            log("  [%s] p=%.2f done in %.1fs"
                % (name, p, row["seconds"]))
            log("    heat 5th=%.1f median=%.1f | cool 5th=%.1f median=%.1f"
                % (row["confirmatory-heat"]["p05"],
                   row["confirmatory-heat"]["median"],
                   row["confirmatory-cool"]["p05"],
                   row["confirmatory-cool"]["median"]))
        report["readings"][name] = per_p
        # persist incrementally (timeout safety)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(report, f, indent=1, sort_keys=True)

    # ---- gate verdict ($A5), primary reading only ----------------------
    gate_row = report["readings"]["allocator_k2_bundle"][str(GATE_P)]
    p05_h = gate_row["confirmatory-heat"]["p05"]
    p05_c = gate_row["confirmatory-cool"]["p05"]
    verdict = "PASS" if (p05_h >= GATE_REQUIRED
                         and p05_c >= GATE_REQUIRED) else "FAIL"
    report["gate"] = {
        "p": GATE_P,
        "required_5th_percentile": GATE_REQUIRED,
        "observed_5th_percentile_heat": p05_h,
        "observed_5th_percentile_cool": p05_c,
        "verdict": verdict if full_run else "%s (diagnostic run, not "
                                             "the frozen gate)" % verdict,
        "consequence": ("NOT_ESTIMATED recommendation; finality clause "
                        "closes Part V" if verdict == "FAIL" else
                        "GPU harvest may proceed"),
    }
    with open(out_path, "w") as f:
        json.dump(report, f, indent=1, sort_keys=True)
    log("wrote %s" % out_path)
    return report


# ---------------------------------------------------------------------------
# CPU self-test (synthetic world; never touches ALFWorld data)
# ---------------------------------------------------------------------------

def self_test():
    table, orders = allocator._synth_world()
    asg = allocator.build_assignment(table, orders)
    cands = sorted(asg["candidates"])
    groups = precompute_groups(asg, cands)
    seeds = [999001 + i for i in range(9)]
    # p = 1: every candidate eligible -> counts = designated min() vs fill
    el1, used1 = draw_eligibility(cands, seeds, 1.0)
    assert el1.all() and (used1 == 1).all()
    c1 = match_counts(groups, el1)
    n_h = min(50, len(asg["targets"]["confirmatory-heat"]))
    assert (c1["confirmatory-heat"] == n_h).all(), c1["confirmatory-heat"]
    assert (c1[("calibration", "heat")] == 20).all()
    # p = 0: nothing eligible
    el0, used0 = draw_eligibility(cands, seeds, 0.0)
    assert not el0.any() and (used0 == 8).all()
    c0 = match_counts(groups, el0)
    assert (c0["confirmatory-heat"] == 0).all()
    assert (c0["confirmatory-cool"] == 0).all()
    # vectorized counts cross-check the exact matcher (M4)
    elh, _ = draw_eligibility(cands, seeds, 0.5)
    assert _crosscheck_exact_matcher(asg, groups, elh, n_check=4)
    # determinism: same seeds + same p -> identical matrices
    ela, _ = draw_eligibility(cands, seeds, 0.5)
    elb, _ = draw_eligibility(cands, seeds, 0.5)
    assert (ela == elb).all()
    # cache consistency: one stream per candidate per seed (by construction)
    # -> the same candidate exposed anywhere sees the identical eligibility
    return {"shape": list(el1.shape), "extremes": "OK",
            "matcher_crosscheck": "OK", "determinism": "OK"}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", action="store_true",
                    help="run the frozen 10,000-draw gate")
    ap.add_argument("--quick", type=int, default=None,
                    help="REDUCED diagnostic run with n draws "
                         "(gate verdict marked diagnostic)")
    ap.add_argument("--out", default=REPORT_PATH)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        print(json.dumps(self_test(), indent=1, sort_keys=True))
        print("FEASIBILITY-SIM SELF-TESTS PASSED")
        return
    if args.run or args.quick:
        n = args.quick if args.quick else N_DRAWS
        rep = run_sim(n_draws=n, out_path=args.out)
        g = rep["gate"]
        print(json.dumps(g, indent=1, sort_keys=True))
        return
    ap.print_help()


if __name__ == "__main__":
    main()
