"""Part V-A allocator: frozen source-attempt contract ($A2) + deterministic
tuple-constrained matching ($A3), producing pools_manifest v2.

Supersedes the Part V $3.5.4 greedy reservation order for pool construction
ONLY (the amendment touches nothing else: flips, cards, prompts, analysis,
terminal states, headroom mechanics all unchanged).

ANALYSIS HYGIENE: success-rate inspection is FORBIDDEN; this module never
runs an episode and never looks at outcomes.  It derives the ex-ante
designation from game metadata only.  Feasibility outcomes come from
feasibility_sim.py (synthetic Bernoulli attempts), never from rollouts.

========================================================================
FROZEN CONTRACT POINTS IMPLEMENTED (PART_V_A_FINAL.md)
========================================================================
A2.1  Ex-ante role separation: every game is assigned AT MOST ONE role
      {target, R-source, X-source} inside a named pool.  A game once
      attempted as a source can never become a target nor an opposite-role
      source (enforced by SourceAttemptLedger role guard).
A2.2  Global attempt cap: per (candidate_path, assigned_role), at most 8
      attempts globally, cached under attempt key
      "candidate_path|role|attempt_idx" (attempt_idx in 1..8, decimal).
      The same attempt key is NEVER executed twice.  Decode seed =
      $3.5.6 literal MD5 rule on that key (idx range 1..8 here; the frozen
      1..4 helper common.harvest_decode_seed is left untouched, see D5).
A2.3  First verified win => source eligible; 8 failed attempts => source
      PERMANENTLY ineligible (no contamination of untried tuple games).
A2.4  An accepted source serves exactly ONE cluster (matcher consumes).
A3    Deterministic (obj,recep) tuple-constrained matching: same obj +
      same recep inside the family pair; maximize min(n_heat, n_cool);
      every tie broken by sha256(canonical path) ascending; calibration
      (20+20) and headroom (6+6 x2) reserved inside the SAME full-pool
      allocation; must yield EXACTLY 50 heat + 50 cool confirmatory
      clusters else NOT_ESTIMATED.
A4    k=2 candidate slots per role per target; <=8 global attempts per
      (candidate, role)  (per-target per-role attempt budget <= 16).
========================================================================
DOCUMENTED DESIGN CHOICES (all fixed BEFORE any simulation run; none were
adjusted after seeing simulation numbers)
========================================================================
D1. k=2 slots are designated as TWO FULL CANDIDATES per role per target,
    donated atomically with the target ("bundle"); a target is designated
    only when its tuple can still fund the complete bundle.  A target with
    fewer than 2 slots in a role contradicts the plain text of A4 and
    could never be counted on to complete, so partial bundles are not
    designated.  (A partial-slot relaxation is evaluated ONLY as an
    informational sensitivity bound in feasibility_sim.py; it is not the
    allocator and was not used for the gate verdict.)
D2. Matching pools eligibility tuple-wide: per (pool, type, tuple) the
    completion capacity is min(#targets, #eligible R slots, #eligible X
    slots).  This is the $A3 "tuple-constrained matching/flow"; each
    accepted source is consumed by exactly one cluster (A2.4).
D3. Mandatory pools are designated BEFORE the confirmatory pools, and
    calibration (R-only) prefers single-side tuples, because $A3 reserves
    calibration+headroom "in the same allocation" and dual-tuple supply
    is the binding resource.  Designation order:
    calibration -> headroom-A -> headroom-B -> confirmatory (heat/cool
    interleaved one bundle at a time).  The interleave serves the
    max-min objective of $A3; the old sequential heat-first greed would
    starve cool of dual-tuple supply -- exactly what $A3 abolishes.
D4. Designated sizes (frozen before the first simulation):
    confirmatory <= 60 targets per type (heritage of the pre-amendment
    60-reservation design; supply-limited in practice),
    calibration 24 per type (fill 20; +20% mirroring 50-of-60),
    headroom 8 per type per set (fill 6).
D5. Attempt decode seed for attempt_idx in 1..8:
    allocator_attempt_seed(candidate, role, idx) applies the $3.5.6
    literal MD5 rule via common.md5_decode_seed on
    "candidate|role|idx".
D6. Ordering: targets within a type are walked in the frozen rng_screen
    screening order (prepare_pools D1, reused read-only); candidates
    inside a tuple side follow the same screening order; every inside-
    matcher ordering uses sha256(canonical path) ascending ($A3 tie rule).
    No RNG is drawn anywhere in this module.
"""

import argparse
import json
import os
from collections import defaultdict

from pilot.external.partv import common
from pilot.external.partv import prepare_pools

# ---------------------------------------------------------------------------
# Frozen constants (PART_V_A_FINAL.md $A2-$A5 + design choices D3/D4)
# ---------------------------------------------------------------------------

K_SLOTS = 2                      # A4: candidate slots per role per target
MAX_GLOBAL_ATTEMPTS = 8          # A2.2/A4: global attempts per (candidate, role)
CONFIRMATORY_REQUIRED = 50       # A3/A4: exact 50+50 else NOT_ESTIMATED
CALIBRATION_REQUIRED = 20        # unchanged calibration pool (Part V $4)
HEADROOM_REQUIRED = 6            # per type per headroom set (Part V $7)
CONF_DESIGNATED_CAP = 60         # D4
CAL_DESIGNATED = 24              # D4
HR_DESIGNATED = 8                # D4

AMENDMENT_ID = "Part V-A (frozen 2026-08-10)"

# Pool build order (D3).  fill = required completed units per type.
POOL_SPECS_V2 = [
    ("calibration", ("R",), CAL_DESIGNATED, CALIBRATION_REQUIRED),
    ("headroom-A", ("X",), HR_DESIGNATED, HEADROOM_REQUIRED),
    ("headroom-B", ("X",), HR_DESIGNATED, HEADROOM_REQUIRED),
    ("confirmatory-heat", ("R", "X"), CONF_DESIGNATED_CAP,
     CONFIRMATORY_REQUIRED),
    ("confirmatory-cool", ("R", "X"), CONF_DESIGNATED_CAP,
     CONFIRMATORY_REQUIRED),
]
MANDATORY_POOLS = ("calibration", "headroom-A", "headroom-B")
CONF_POOLS = ("confirmatory-heat", "confirmatory-cool")
OPPOSITE = {"heat": "cool", "cool": "heat"}
MANIFEST_V2_PATH = os.path.join(common.OUT_ROOT, "pools_manifest_v2.json")

_READING_NOTE = (
    "reading: k=2 slots designated as full atomic bundles per target (D1); "
    "matching pools eligibility tuple-wide (D2); mandatory pools reserved "
    "first (D3)")


# ---------------------------------------------------------------------------
# tuple world: per (obj, recep) the screening-ordered game lists per side
# ---------------------------------------------------------------------------

def build_tuple_world(table, orders):
    """-> {tuple_key: {"heat": [paths in heat screening order],
                       "cool": [paths in cool screening order]}}
    tuple_key = "obj|recep" (goal-parser canonical lower case)."""
    world = defaultdict(lambda: {"heat": [], "cool": []})
    for prep in ("heat", "cool"):
        for gi in orders[prep]:
            info = table[prep][gi]
            key = "%s|%s" % (info["obj"], info["recep"])
            world[key][prep].append(info["path"])
    return dict(world)


def _sha(s):
    return common.sha256_bytes(s.encode("utf-8"))


# ---------------------------------------------------------------------------
# ex-ante designation ($A2.1): one role per game, atomic k-slot bundles (D1)
# ---------------------------------------------------------------------------

class Designator:
    """Greedy deterministic designation over the tuple world."""

    def __init__(self, world, info_by_path, walk):
        """world: build_tuple_world output; info_by_path: path -> game info;
        walk: {"heat": [paths in screening order], "cool": [...]}."""
        self.world = world
        self.info = info_by_path
        self.walk = walk
        self.rem = {k: {"heat": len(v["heat"]), "cool": len(v["cool"])}
                    for k, v in world.items()}
        self.used = {}                       # path -> "target:<pool>" | "R:<pool>" | "X:<pool>"
        self.targets = defaultdict(list)     # pool -> [target rec]
        self.candidates = {}                 # path -> candidate rec

    # -- primitives ------------------------------------------------------
    def _first_free(self, tkey, side, n):
        """First n unassigned paths of (tkey, side) in screening order,
        or None if fewer than n remain (rem counter is authoritative)."""
        if self.rem[tkey][side] < n:
            return None
        out = []
        for p in self.world[tkey][side]:
            if p not in self.used:
                out.append(p)
                if len(out) == n:
                    break
        return out if len(out) == n else None    # defensive

    def _designate(self, pool, prep, tkey, slot_paths, target):
        """Record one bundle already resolved to concrete paths."""
        slots = {}
        for role, paths in slot_paths.items():
            slots[role] = list(paths)
        self.used[target] = "target:%s" % pool
        for role, paths in slots.items():
            for p in paths:
                side = "heat" if self.info[p]["prep"] == "heat" else "cool"
                self.used[p] = "%s:%s" % (role, pool)
                self.candidates[p] = {
                    "path": p, "pool": pool, "role": role,
                    "pool_type": prep, "game_side": side, "tuple_key": tkey,
                }
                self.rem[tkey][side] -= 1
        self.rem[tkey][prep] -= 1
        self.targets[pool].append({
            "path": target, "type": prep, "pool": pool, "tuple_key": tkey,
            "obj": self.info[target]["obj"],
            "recep": self.info[target]["recep"],
            "slots": slots,
            "designation_index": len(self.targets[pool]),
        })

    def _bundle(self, pool, prep, tkey, own_n, opp_side_n, opp_role,
                own_role="R"):
        """Designate 1 target (own side) + own_n-1 own slots + opp slots."""
        own = self._first_free(tkey, prep, own_n)
        if own is None:
            return False
        opp_paths = []
        if opp_side_n:
            opp_side = OPPOSITE[prep]
            opp_paths = self._first_free(tkey, opp_side, opp_side_n)
            if opp_paths is None:
                return False
        slots = {}
        if own_n > 1:
            slots[own_role] = own[1:]
        if opp_paths:
            slots[opp_role] = opp_paths
        self._designate(pool, prep, tkey, slots, own[0])
        return True

    # -- pool-level walks (order = D3) -----------------------------------
    def designate_calibration(self):
        """R-only bundles (target + 2 R slots), single-side tuples first."""
        for prep in ("heat", "cool"):
            opp = OPPOSITE[prep]
            for single_only in (True, False):
                for path in self.walk[prep]:
                    if sum(1 for t in self.targets["calibration"]
                           if t["type"] == prep) >= CAL_DESIGNATED:
                        break
                    if path in self.used:
                        continue
                    inf = self.info[path]
                    tkey = "%s|%s" % (inf["obj"], inf["recep"])
                    if single_only and len(self.world[tkey][opp]) > 0:
                        continue
                    self._bundle("calibration", prep, tkey, 3, 0, None)

    def designate_headroom(self, pool):
        """X-only bundles: heat -> 1 heat target + 2 cool X slots;
        cool -> 1 cool target + 2 heat X slots (dual tuples only)."""
        for prep in ("heat", "cool"):
            for path in self.walk[prep]:
                if sum(1 for t in self.targets[pool]
                       if t["type"] == prep) >= HR_DESIGNATED:
                    break
                if path in self.used:
                    continue
                inf = self.info[path]
                tkey = "%s|%s" % (inf["obj"], inf["recep"])
                self._bundle(pool, prep, tkey, 1, 2, "X")

    def designate_confirmatory(self):
        """Balanced interleave (D3): bundle = target + 2 R (own) + 2 X (opp).
        A type closes when no tuple can fund its bundle, or at the cap."""
        open_type = {"heat": True, "cool": True}
        while open_type["heat"] or open_type["cool"]:
            for prep in ("heat", "cool"):
                if not open_type[prep]:
                    continue
                if sum(1 for t in self.targets["confirmatory-%s" % prep]
                       if True) >= CONF_DESIGNATED_CAP:
                    open_type[prep] = False
                    continue
                opp = OPPOSITE[prep]
                placed = False
                for path in self.walk[prep]:
                    if path in self.used:
                        continue
                    inf = self.info[path]
                    tkey = "%s|%s" % (inf["obj"], inf["recep"])
                    if self.rem[tkey][prep] < 3 or self.rem[tkey][opp] < 2:
                        continue
                    if self._bundle("confirmatory-%s" % prep, prep, tkey,
                                    3, 2, "X"):
                        placed = True
                        break
                if not placed:
                    open_type[prep] = False


def build_assignment(table=None, orders=None):
    """The full ex-ante Part V-A designation ($A2.1), deterministic.

    Returns {"targets": {pool: [recs]}, "candidates": {path: rec},
             "used": {path: tag}, "world": tuple world, "info": path->info}.
    """
    if table is None:
        table, _stats = prepare_pools.build_game_table()
    if orders is None:
        orders = prepare_pools.screening_orders(table)
    world = build_tuple_world(table, orders)
    info_by_path, walk = {}, {"heat": [], "cool": []}
    for prep in ("heat", "cool"):
        for gi in orders[prep]:
            inf = table[prep][gi]
            info_by_path[inf["path"]] = inf
            walk[prep].append(inf["path"])
    d = Designator(world, info_by_path, walk)
    d.designate_calibration()           # D3: reserve mandatory first
    d.designate_headroom("headroom-A")
    d.designate_headroom("headroom-B")
    d.designate_confirmatory()
    return {"targets": dict(d.targets), "candidates": d.candidates,
            "used": d.used, "world": world, "info": info_by_path}


# ---------------------------------------------------------------------------
# $A2 runtime contract: global source-attempt ledger
# ---------------------------------------------------------------------------

def allocator_attempt_seed(candidate_path, role, attempt_idx):
    """$3.5.6 literal MD5 rule on "candidate|role|idx", idx in 1..8 (D5)."""
    assert isinstance(attempt_idx, int) and 1 <= attempt_idx <= MAX_GLOBAL_ATTEMPTS
    return common.md5_decode_seed("%s|%s|%d" % (candidate_path, role,
                                                attempt_idx))


class ContractViolation(RuntimeError):
    pass


class SourceAttemptLedger:
    """Global attempt ledger per (candidate_path, assigned_role) ($A2.2-3).

    Invariants enforced:
      - a candidate is only ever attempted under its assigned role and pool
        (A2.1 role guard; a designated target can never be attempted);
      - <= MAX_GLOBAL_ATTEMPTS attempts per (candidate, role), in strictly
        increasing attempt_idx order, each attempt key executed at most once;
      - attempts stop permanently after the first win (source eligible) and
        after the 8th failure (source permanently ineligible).

    Storage is the in-memory mirror of the JSONL attempt stream; the GPU
    harvest phase replays the same class (persistence schema:
    {"event": "source_attempt", "candidate", "role", "attempt_idx",
     "decode_seed", "won"}).
    """

    def __init__(self, assignment, rows=()):
        self.assigned = {}      # candidate path -> (role, pool)
        for path, rec in assignment["candidates"].items():
            self.assigned[path] = (rec["role"], rec["pool"])
        self.target_paths = set()
        for pool, recs in assignment["targets"].items():
            self.target_paths.update(t["path"] for t in recs)
        self.attempts = defaultdict(list)   # (candidate, role) -> [won ints]
        self.keys = set()                   # executed attempt keys
        for r in rows:
            self.record(r["candidate"], r["role"], r["attempt_idx"],
                        bool(r["won"]))

    def status(self, candidate, role):
        """-> "eligible" | "ineligible" | "open" (not yet decided)."""
        wins = self.attempts.get((candidate, role), [])
        if any(wins):
            return "eligible"
        if len(wins) >= MAX_GLOBAL_ATTEMPTS:
            return "ineligible"
        return "open"

    def next_attempt_idx(self, candidate, role):
        """Next attempt index to execute, or None if none may be run."""
        if self.status(candidate, role) != "open":
            return None
        return len(self.attempts[(candidate, role)]) + 1

    def record(self, candidate, role, attempt_idx, won):
        """Commit one attempt result; raises ContractViolation on any
        breach of the A2 contract.  Idempotent against exact replays of an
        already-committed key (same idx + same outcome)."""
        if candidate not in self.assigned:
            raise ContractViolation(
                "A2.1: %s is not an assigned source candidate (target or "
                "unassigned); it can never be attempted" % candidate)
        arole, _pool = self.assigned[candidate]
        if role != arole:
            raise ContractViolation(
                "A2.1: %s attempted as %s but assigned role is %s"
                % (candidate, role, arole))
        if candidate in self.target_paths:
            raise ContractViolation("A2.1: designated target attempted: %s"
                                    % candidate)
        if not (1 <= attempt_idx <= MAX_GLOBAL_ATTEMPTS):
            raise ContractViolation("A2.2: attempt_idx %d out of 1..%d"
                                    % (attempt_idx, MAX_GLOBAL_ATTEMPTS))
        key = (candidate, role, attempt_idx)
        won = bool(won)
        wins = self.attempts[(candidate, role)]
        if key in self.keys:
            prev = wins[attempt_idx - 1] if attempt_idx <= len(wins) else None
            if prev is not None and prev == won:
                return                      # exact replay: no-op (cached)
            raise ContractViolation(
                "A2.2: attempt key %s already executed with a different "
                "outcome -- duplicate execution forbidden" % (key,))
        if attempt_idx != len(wins) + 1:
            raise ContractViolation(
                "A2.2: attempts for %s must commit sequentially; expected "
                "idx %d, got %d" % (candidate, len(wins) + 1, attempt_idx))
        if self.status(candidate, role) != "open":
            raise ContractViolation(
                "A2.2/3: candidate %s already decided (%s); further "
                "attempts forbidden" % (candidate,
                                        self.status(candidate, role)))
        seed = allocator_attempt_seed(candidate, role, attempt_idx)
        self.keys.add(key)
        wins.append(won)
        return {"event": "source_attempt", "candidate": candidate,
                "role": role, "attempt_idx": attempt_idx,
                "decode_seed": seed, "won": int(won)}

    def eligible_set(self):
        """All candidates currently eligible (>=1 win), per A2.3."""
        return {c for (c, _r), wins in self.attempts.items() if any(wins)}


# ---------------------------------------------------------------------------
# $A3 deterministic tuple-constrained matching
# ---------------------------------------------------------------------------

def _eligible_by_tuple(assignment, pool, prep, role, eligible):
    """eligible candidate counts per tuple for (pool, type, role)."""
    out = defaultdict(int)
    for path, rec in assignment["candidates"].items():
        if rec["pool"] == pool and rec["pool_type"] == prep \
                and rec["role"] == role and path in eligible:
            out[rec["tuple_key"]] += 1
    return out


def _targets_by_tuple(assignment, pool, prep):
    out = defaultdict(list)
    for t in assignment["targets"].get(pool, []):
        if t["type"] == prep:
            out[t["tuple_key"]].append(t["path"])
    for k in out:
        out[k].sort(key=_sha)            # A3 tie rule, sha256 ascending
    return out


def match_allocation(assignment, eligible):
    """$A3 full-pool deterministic allocation over an eligibility outcome.

    eligible: set of candidate paths with >=1 win (A2.3).

    Returns {"status": "ok" | "not_estimated",
             "counts": {pool: {"heat": n, "cool": n}},   # completed units
             "required": {pool: {...}},
             "clusters": [ {pool,type,target,sources:{role:path}} ...],
             "unmet": [pool,...] }
    Clusters are selected with sha256-ascending ordering at every tie
    (tuple key order, then target path, then source path); the confirmatory
    pools are trimmed to exactly CONFIRMATORY_REQUIRED per type.
    """
    counts = {pool: {"heat": 0, "cool": 0} for pool, *_ in POOL_SPECS_V2}
    clusters = []
    unmet = []
    consumed = set()                     # accepted sources (A2.4)
    fills = dict((n, f) for n, _r, _d, f in POOL_SPECS_V2)
    # ---- mandatory reservations first (D3 / $A3 "same allocation") -----
    for pool in MANDATORY_POOLS:
        role = next(r[0] for n, r, _d, _f in POOL_SPECS_V2 if n == pool)
        for prep in ("heat", "cool"):
            tg = _targets_by_tuple(assignment, pool, prep)
            done = 0
            for tkey in sorted(tg, key=_sha):
                src_pool = sorted(
                    (p for p, rec in assignment["candidates"].items()
                     if rec["pool"] == pool and rec["pool_type"] == prep
                     and rec["role"] == role and rec["tuple_key"] == tkey
                     and p in eligible and p not in consumed), key=_sha)
                for target in tg[tkey]:
                    if done >= fills[pool] or not src_pool:
                        break
                    src = src_pool.pop(0)
                    consumed.add(src)
                    clusters.append({"pool": pool, "type": prep,
                                     "target": target,
                                     "sources": {role: src}})
                    done += 1
            counts[pool][prep] = done
            if done < fills[pool]:
                unmet.append("%s:%s" % (pool, prep))
    # ---- confirmatory: max min(n_heat, n_cool), then exact-50 trim -----
    for pool in CONF_POOLS:
        prep = "heat" if pool.endswith("heat") else "cool"
        tg = _targets_by_tuple(assignment, pool, prep)
        el = {role: _eligible_by_tuple(assignment, pool, prep, role,
                                       eligible)
              for role in ("R", "X")}
        completed = []
        for tkey in sorted(tg, key=_sha):
            r_avail = sorted(
                (p for p, rec in assignment["candidates"].items()
                 if rec["pool"] == pool and rec["pool_type"] == prep
                 and rec["role"] == "R" and rec["tuple_key"] == tkey
                 and p in eligible and p not in consumed), key=_sha)
            x_avail = sorted(
                (p for p, rec in assignment["candidates"].items()
                 if rec["pool"] == pool and rec["pool_type"] == prep
                 and rec["role"] == "X" and rec["tuple_key"] == tkey
                 and p in eligible and p not in consumed), key=_sha)
            # tuple capacity = min(#targets, #eligible R, #eligible X) (D2)
            cap = min(len(tg[tkey]), len(r_avail), len(x_avail))
            for i in range(cap):
                r_src, x_src = r_avail[i], x_avail[i]
                consumed.update((r_src, x_src))
                completed.append({"pool": pool, "type": prep,
                                  "target": tg[tkey][i],
                                  "sources": {"R": r_src, "X": x_src}})
        counts[pool][prep] = min(len(completed), fills[pool])
        clusters.extend(completed[:fills[pool]])
        if len(completed) < fills[pool]:
            unmet.append("%s:%s" % (pool, prep))
    status = "ok" if not any(u.startswith("confirmatory") for u in unmet) \
        else "not_estimated"
    return {"status": status, "counts": counts, "required": fills,
            "clusters": clusters, "unmet": unmet,
            "n_sources_consumed": len(consumed)}


# ---------------------------------------------------------------------------
# v2 pools manifest
# ---------------------------------------------------------------------------

def designation_stats(assignment):
    per_pool = {}
    for pool, _roles, _des, fill in POOL_SPECS_V2:
        t = assignment["targets"].get(pool, [])
        by_type = {"heat": sum(1 for x in t if x["type"] == "heat"),
                   "cool": sum(1 for x in t if x["type"] == "cool")}
        cands = {"R": 0, "X": 0}
        for rec in assignment["candidates"].values():
            if rec["pool"] == pool:
                cands[rec["role"]] += 1
        per_pool[pool] = {"designated_targets": by_type,
                          "required_fill": fill,
                          "designated_candidates": cands}
    supply = {"total_games": {"heat": 0, "cool": 0},
              "dual_tuple_games": {"heat": 0, "cool": 0},
              "used_games": len(assignment["used"])}
    for tkey, sides in assignment["world"].items():
        nh, nc = len(sides["heat"]), len(sides["cool"])
        supply["total_games"]["heat"] += nh
        supply["total_games"]["cool"] += nc
        if nh >= 2 and nc >= 2:
            supply["dual_tuple_games"]["heat"] += nh
            supply["dual_tuple_games"]["cool"] += nc
    return {"pools": per_pool, "supply": supply}


def build_manifest_v2(out_path=MANIFEST_V2_PATH):
    assignment = build_assignment()
    manifest = {
        "schema": "partv.pools.v2",
        "amendment": AMENDMENT_ID,
        "reading": _READING_NOTE,
        "frozen": {
            "k_slots": K_SLOTS,
            "max_global_attempts": MAX_GLOBAL_ATTEMPTS,
            "confirmatory_required_per_type": CONFIRMATORY_REQUIRED,
            "calibration_fill_per_type": CALIBRATION_REQUIRED,
            "headroom_fill_per_type_per_set": HEADROOM_REQUIRED,
            "confirmatory_designated_cap": CONF_DESIGNATED_CAP,
            "calibration_designated": CAL_DESIGNATED,
            "headroom_designated": HR_DESIGNATED,
            "attempt_key": "candidate_path|role|attempt_idx (1..8)",
            "decode_seed": "md5 literal rule $3.5.6 on the attempt key",
            "tie_break": "sha256(canonical path) ascending everywhere",
        },
        "designation": designation_stats(assignment),
        "pool_order": ["calibration", "headroom-A", "headroom-B",
                       "confirmatory-heat", "confirmatory-cool"],
        "targets": assignment["targets"],
        "candidates": assignment["candidates"],
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)
    return manifest


# ---------------------------------------------------------------------------
# CPU self-test: synthetic tuple world (no ALFWorld data touched)
# ---------------------------------------------------------------------------

def _synth_world():
    """2 dual tuples + 1 single-side cool tuple + 1 single-side heat tuple."""
    def inf(prep, obj, recep, i):
        p = "syn/%s_%s_%s/trial_%02d/game.tw-pddl" % (prep, obj, recep, i)
        return {"path": p, "prep": prep, "obj": obj, "recep": recep,
                "goal": "x", "sha256": _sha(p)}
    table = {"heat": [], "cool": []}
    for i in range(70):
        table["heat"].append(inf("heat", "mug", "shelf", i))
        table["cool"].append(inf("cool", "mug", "shelf", i))
    for i in range(30):
        table["heat"].append(inf("heat", "pot", "stove", i))
        table["cool"].append(inf("cool", "pot", "stove", i))
    for i in range(40):
        table["cool"].append(inf("cool", "apple", "fridge", i))
    for i in range(40):
        table["heat"].append(inf("heat", "egg", "microwave", i))
    for prep in ("heat", "cool"):
        table[prep].sort(key=lambda x: x["sha256"])
    orders = {"heat": list(range(len(table["heat"]))),
              "cool": list(range(len(table["cool"])))}
    return table, orders


def self_test():
    import pilot.external.partv.allocator as A
    table, orders = _synth_world()
    asg = A.build_assignment(table, orders)
    # determinism
    asg2 = A.build_assignment(table, orders)
    assert json.dumps(asg["used"], sort_keys=True) == \
        json.dumps(asg2["used"], sort_keys=True)
    # role uniqueness (A2.1): every used game appears exactly once
    assert len(asg["used"]) == len(set(asg["used"]))
    tgt = {t["path"] for recs in asg["targets"].values() for t in recs}
    assert not (tgt & set(asg["candidates"]))
    # bundle shape: confirmatory targets carry 2 R + 2 X slots
    for t in asg["targets"]["confirmatory-heat"]:
        assert len(t["slots"]["R"]) == 2 and len(t["slots"]["X"]) == 2
        r0 = asg["info"][t["slots"]["R"][0]]
        x0 = asg["info"][t["slots"]["X"][0]]
        assert r0["prep"] == "heat" and x0["prep"] == "cool"
        assert r0["obj"] == t["obj"] and r0["recep"] == t["recep"]
        assert x0["obj"] == t["obj"] and x0["recep"] == t["recep"]
    # calibration prefers single-side tuples (D3): pass 1 exhausts them
    # (single-side supply here is floor(40/3)=13 bundles per type)
    for prep in ("heat", "cool"):
        opp = "cool" == prep and "heat" or "cool"
        n_single = sum(1 for t in asg["targets"]["calibration"]
                       if t["type"] == prep
                       and len(asg["world"][t["tuple_key"]][opp]) == 0)
        assert n_single == 13, (prep, n_single)
    # mandatory sizes designated as frozen (D4)
    assert len(asg["targets"]["calibration"]) == 48      # 24+24
    assert len(asg["targets"]["headroom-A"]) == 16
    assert len(asg["targets"]["headroom-B"]) == 16
    # ledger contract
    led = A.SourceAttemptLedger(asg)
    a_target = asg["targets"]["confirmatory-heat"][0]["path"]
    try:
        led.record(a_target, "R", 1, False)
        raise SystemExit("target attempt must be refused")
    except A.ContractViolation:
        pass
    cand = asg["targets"]["confirmatory-heat"][0]["slots"]["R"][0]
    try:
        led.record(cand, "X", 1, False)
        raise SystemExit("opposite-role attempt must be refused")
    except A.ContractViolation:
        pass
    for i in range(1, 9):
        row = led.record(cand, "R", i, False)
        assert row["decode_seed"] == A.allocator_attempt_seed(cand, "R", i)
    assert led.status(cand, "R") == "ineligible"
    try:
        led.record(cand, "R", 9, True)
        raise SystemExit("9th attempt must be refused")
    except A.ContractViolation:
        pass
    cand2 = asg["targets"]["confirmatory-heat"][0]["slots"]["R"][1]
    led.record(cand2, "R", 1, False)
    try:
        led.record(cand2, "R", 3, True)      # gap: idx 2 missing
        raise SystemExit("non-sequential attempt must be refused")
    except A.ContractViolation:
        pass
    led.record(cand2, "R", 2, True)
    assert led.status(cand2, "R") == "eligible"
    # exact replay of a committed key (same outcome) is a cached no-op (A2.2)
    led.record(cand2, "R", 2, True)            # no exception, no new attempt
    assert len(led.attempts[(cand2, "R")]) == 2
    try:
        led.record(cand2, "R", 2, False)       # same key, different outcome
        raise SystemExit("key re-execution with different outcome must be "
                         "refused")
    except A.ContractViolation:
        pass
    try:
        led.record(cand2, "R", 3, True)        # new attempt after win
        raise SystemExit("post-win attempt must be refused")
    except A.ContractViolation:
        pass
    # matcher: all eligible -> fills exactly the required fill counts
    all_el = set(asg["candidates"])
    out = A.match_allocation(asg, all_el)
    assert out["counts"]["calibration"] == {"heat": 20, "cool": 20}, out["counts"]["calibration"]
    assert out["counts"]["headroom-A"] == {"heat": 6, "cool": 6}
    n_conf_h = len(asg["targets"]["confirmatory-heat"])
    assert out["counts"]["confirmatory-heat"]["heat"] == min(50, n_conf_h)
    # accepted sources unique across clusters (A2.4)
    srcs = [s for c in out["clusters"] for s in c["sources"].values()]
    assert len(srcs) == len(set(srcs))
    # matcher: no eligible sources -> confirmatory NOT_ESTIMATED
    out0 = A.match_allocation(asg, set())
    assert out0["status"] == "not_estimated"
    assert out0["counts"]["confirmatory-heat"]["heat"] == 0
    assert out0["counts"]["confirmatory-cool"]["cool"] == 0
    # determinism of matching
    half = set(sorted(all_el, key=_sha)[:len(all_el) // 2])
    o1 = A.match_allocation(asg, half)
    o2 = A.match_allocation(asg, half)
    assert json.dumps(o1["clusters"], sort_keys=True) == \
        json.dumps(o2["clusters"], sort_keys=True)
    return {"designation": designation_stats(asg),
            "ledger": "OK", "matcher": "OK", "determinism": "OK"}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--build", action="store_true",
                    help="write pools_manifest_v2.json (default out)")
    ap.add_argument("--out", default=MANIFEST_V2_PATH)
    ap.add_argument("--stats", action="store_true",
                    help="print designation stats without writing")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        res = self_test()
        print(json.dumps(_jsonable(res), indent=1, sort_keys=True))
        print("ALLOCATOR SELF-TESTS PASSED")
        return
    if args.build:
        man = build_manifest_v2(args.out)
        print("wrote", args.out)
        print(json.dumps(_jsonable(man["designation"]), indent=1,
                         sort_keys=True))
        return
    if args.stats:
        print(json.dumps(_jsonable(designation_stats(build_assignment())),
                         indent=1, sort_keys=True))
        return
    ap.print_help()


def _jsonable(o):
    import numpy as np
    if isinstance(o, dict):
        return {k: _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, np.generic):
        return o.item()
    return o


if __name__ == "__main__":
    main()
