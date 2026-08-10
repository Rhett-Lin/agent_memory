"""Part V $3.5 pool reservation + candidate lists (frozen algorithm block).

ANALYSIS HYGIENE: success-rate inspection is FORBIDDEN here; this module
never runs an episode and never looks at outcomes.  The dry-run harvest
simulation (--dry-run) uses an explicit synthetic win probability purely to
assess pool feasibility -- it reads no model output.

Frozen rules implemented:
  $3.5.1 canonical POSIX relpath;  $3.5.3 sha256-ascending then
  np.argsort(rng_screen.random(n), kind="stable") (float ties keep sha
  order);  rng_screen = PCG64(20260809), rng_rollout = PCG64(20260810)
  (rng_rollout is only exercised by grid.py -- never mixed here).
  $3.5.4 global reservation order: confirmatory-heat(60) ->
  confirmatory-cool(60) -> calibration(exactly 20 heat + 20 cool) ->
  headroom-A(6+6) -> headroom-B(6+6).
  Permanent reservation: ANY game appearing in the harvest ledger (as an
  attempted target, an attempted source candidate -- including failed
  attempts, or a chosen source) is permanently removed from every later
  pool and candidate list.  Candidates that were merely listed but never
  attempted remain free (see AMBIGUITIES.md / task report note P1: the
  strict "listing == reservation" reading is mathematically infeasible
  under the frozen 60+60 design, 459+533 games; this is the documented
  resolution).

Documented derivation choices (discretion closed by construction):
  D1. rng_screen draw order is exactly: heat permutation first, cool
      permutation second (matching the frozen pool order).
  D2. Per-target candidate lists follow the TYPE screening order of the
      candidate's own prep class (R candidates: target's type order; X
      candidates: the opposite type's order), skipping reserved games and
      the target itself.  "First 8 unique candidates" = first 8 entries of
      that list at selection time.
  D3. Roles actually harvested per pool (need-based): confirmatory R+X;
      calibration R only ($3.5.4 matches targets with model-harvest R
      cards); headroom X only ($7 manipulation is X- vs N-arm behavior).

Game classes come ONLY from goal text parsed out of each game.tw-pddl
(documented parser in common.py -- no metadata/dirname labels).
"""

import argparse
import json
import os
from collections import Counter, defaultdict

import numpy as np

from pilot.external.partv import common

POOL_SPECS = [
    # (name, {"heat": n, "cool": n}, roles)
    ("confirmatory-heat", {"heat": common.CONFIRMATORY_PER_TYPE}, ("R", "X")),
    ("confirmatory-cool", {"cool": common.CONFIRMATORY_PER_TYPE}, ("R", "X")),
    ("calibration", {"heat": common.CALIBRATION_PER_TYPE,
                     "cool": common.CALIBRATION_PER_TYPE}, ("R",)),
    ("headroom-A", {"heat": common.HEADROOM_PER_TYPE,
                    "cool": common.HEADROOM_PER_TYPE}, ("X",)),
    ("headroom-B", {"heat": common.HEADROOM_PER_TYPE,
                    "cool": common.HEADROOM_PER_TYPE}, ("X",)),
]
OPPOSITE = {"heat": "cool", "cool": "heat"}
MANIFEST_PATH = os.path.join(common.OUT_ROOT, "pools_manifest.json")


# ---------------------------------------------------------------------------
# game table + screening orders
# ---------------------------------------------------------------------------

def build_game_table(root=None):
    """-> {prep: [info,...]} with each prep list sha256-ascending ($3.5.3)."""
    table, stats = {}, {}
    for prep in ("heat", "cool"):
        infos = []
        for gf in common.list_family_games(prep, root=root):
            infos.append(common.load_game_info(gf, common.data_root()))
        infos.sort(key=lambda i: i["sha256"])
        table[prep] = infos
        stats["n_%s" % prep] = len(infos)
        stats["n_obj_%s" % prep] = len(set(i["obj"] for i in infos))
        stats["n_recep_%s" % prep] = len(set(i["recep"] for i in infos))
        stats["phrasings_%s" % prep] = dict(Counter(
            "A" if i["goal"].lower().startswith(("heat", "cool")) else "B"
            for i in infos))
    return table, stats


def screening_orders(table):
    """Frozen rng_screen: PCG64(20260809); heat first, then cool (D1)."""
    rng = np.random.Generator(np.random.PCG64(common.SEED_RNG_SCREEN))
    orders = {}
    for prep in ("heat", "cool"):
        n = len(table[prep])
        perm = np.argsort(rng.random(n), kind="stable")
        orders[prep] = [int(i) for i in perm]
    return orders


def candidate_list(table, orders, reserved, target_info, role, k=8,
                   exclude=()):
    """First k unique unreserved candidates for (target, role) per D2."""
    cand_prep = target_info["prep"] if role == "R" else OPPOSITE[target_info["prep"]]
    out, tpath = [], target_info["path"]
    for gi in orders[cand_prep]:
        info = table[cand_prep][gi]
        p = info["path"]
        if p == tpath or p in reserved or p in exclude:
            continue
        if info["obj"] != target_info["obj"] or info["recep"] != target_info["recep"]:
            continue
        out.append(p)
        if len(out) == k:
            break
    return out


# ---------------------------------------------------------------------------
# reservation state
# ---------------------------------------------------------------------------

def reserved_from_ledger(ledger_path=common.LEDGER_PATH):
    """Permanent reservation = every game ever appearing in the ledger."""
    reserved = set()
    if not os.path.exists(ledger_path):
        return reserved
    with open(ledger_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            for key in ("target", "candidate"):
                p = row.get(key)
                if p:
                    reserved.add(p)
    return reserved


def planned_targets(pool_name, table, orders, reserved, k=8):
    """Screening-order target queue for a pool: every unreserved game whose
    CURRENT candidate sets are complete (>=k per needed role)."""
    poolspec = dict((name, (tc, roles)) for name, tc, roles in POOL_SPECS)
    type_counts, roles = poolspec[pool_name]
    queue = defaultdict(list)
    for prep, need in type_counts.items():
        for gi in orders[prep]:
            info = table[prep][gi]
            if info["path"] in reserved:
                continue
            cands, ok = {}, True
            for role in roles:
                cl = candidate_list(table, orders, reserved, info, role, k=k)
                cands[role] = cl
                ok = ok and len(cl) == k
            if ok:
                queue[prep].append({"target": info, "candidates": cands})
    return queue


# ---------------------------------------------------------------------------
# build / dry-run
# ---------------------------------------------------------------------------

def static_candidate_stats(table, orders, k=8):
    """#games with >=k R + >=k X candidates under zero reservation."""
    out = {}
    for prep in ("heat", "cool"):
        full = short_R = short_X = 0
        for gi in orders[prep]:
            info = table[prep][gi]
            nR = len(candidate_list(table, orders, set(), info, "R", k=k))
            nX = len(candidate_list(table, orders, set(), info, "X", k=k))
            if nR >= k and nX >= k:
                full += 1
            else:
                short_R += nR < k
                short_X += nX < k
        out[prep] = {"targets_with_full_%dR_%dX" % (k, k): full,
                     "short_R": short_R, "short_X": short_X}
    return out


def dry_run(sim_win_prob=0.5, k=8, seed=20260811):
    """Simulate the full 5-pool sequence with synthetic per-attempt wins.

    Uses its own throwaway PCG64(seed) stream; never touches the frozen
    rng_screen (already consumed deterministically) or rng_rollout.
    """
    table, dstats = build_game_table()
    orders = screening_orders(table)
    rng = np.random.Generator(np.random.PCG64(seed))
    reserved = set()
    report = {"derivation": dstats,
              "static_candidates": static_candidate_stats(table, orders, k=k),
              "sim_win_prob_per_attempt": sim_win_prob, "pools": {}}
    for name, type_counts, roles in POOL_SPECS:
        ts = report["pools"][name] = {"wanted": dict(type_counts),
                                      "targets": {}, "rejected": 0,
                                      "not_estimated": False,
                                      "games_consumed": 0}
        for prep, want in type_counts.items():
            valid, rejected, queue_skips = 0, 0, 0
            for gi in orders[prep]:
                if valid >= want:
                    break
                info = table[prep][gi]
                if info["path"] in reserved:
                    queue_skips += 1
                    continue
                # targets short of the $3.4 8+8 lists are passed over in
                # screening WITHOUT attempts (no reservation, no replacement
                # spent; see report note P2).
                cls = {role: candidate_list(table, orders, reserved, info,
                                            role, k=k)
                       for role in roles}
                if any(len(cl) < k for cl in cls.values()):
                    queue_skips += 1
                    continue
                # harvest attempt (simulated): role candidate lists live
                won, consumed_here = {}, 0
                for role in roles:
                    cl = cls[role]
                    found = None
                    attempted = []
                    for c in cl:
                        attempted.append(c)
                        consumed_here += 1
                        for _attempt in range(4):
                            if rng.random() < sim_win_prob:
                                found = c
                                break
                        if found is not None:
                            break
                    # every candidate ATTEMPTED is reserved (won or not);
                    # targets are reserved once attempted ($3.5.4).
                    reserved.update(attempted)
                    if found is not None:
                        won[role] = found
                    else:
                        break
                reserved.add(info["path"])          # target once attempted
                target_attempted = True
                if len(won) == len(roles):
                    valid += 1
                    ts["games_consumed"] += consumed_here
                else:
                    rejected += 1
                    if rejected > common.MAX_REPLACEMENTS:
                        ts["not_estimated"] = True
                        break
            ts["targets"][prep] = {"valid": valid, "wanted": want,
                                   "rejected": rejected,
                                   "skipped_reserved": queue_skips}
            if valid < want:
                ts["not_estimated"] = True
        ts["reserved_cumulative"] = len(reserved)
    return report


def cmd_build(out_path=MANIFEST_PATH):
    table, dstats = build_game_table()
    orders = screening_orders(table)
    reserved = reserved_from_ledger()
    manifest = {
        "schema": "partv.pools.v1",
        "frozen": {"rng_screen": "numpy PCG64(%d)" % common.SEED_RNG_SCREEN,
                   "rng_rollout": "numpy PCG64(%d) (grid.py only)"
                                  % common.SEED_RNG_ROLLOUT,
                   "k_candidates": 8, "max_attempts": 4,
                   "max_replacements": common.MAX_REPLACEMENTS},
        "derivation": dstats,
        "static_candidates": static_candidate_stats(table, orders),
        "n_reserved_from_ledger": len(reserved),
        "pool_order": [name for name, _, _ in POOL_SPECS],
        "pools": {},
    }
    for name, type_counts, roles in POOL_SPECS:
        queue = planned_targets(name, table, orders, reserved)
        manifest["pools"][name] = {
            "roles": list(roles), "wanted": dict(type_counts),
            "queued_targets": {p: len(q) for p, q in queue.items()},
        }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)
    return manifest


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--build", action="store_true",
                    help="write pools_manifest.json derivation state")
    ap.add_argument("--dry-run", action="store_true",
                    help="simulate all pools with synthetic win prob")
    ap.add_argument("--sim-win-prob", type=float, default=0.5)
    ap.add_argument("--out", default=MANIFEST_PATH)
    args = ap.parse_args(argv)
    if args.dry_run:
        rep = dry_run(sim_win_prob=args.sim_win_prob)
        print(json.dumps(_jsonable(rep), indent=1, sort_keys=True))
    elif args.build:
        man = cmd_build(args.out)
        print("wrote", args.out)
        print(json.dumps(_jsonable(manifest_summary(man)), indent=1,
                         sort_keys=True))
    else:
        ap.print_help()


def manifest_summary(man):
    return {"derivation": man["derivation"],
            "static_candidates": man["static_candidates"],
            "pools": man["pools"]}


def _jsonable(o):
    if isinstance(o, dict):
        return {k: _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, np.generic):
        return o.item()
    return o


if __name__ == "__main__":
    main()
