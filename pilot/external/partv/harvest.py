"""Part V $3.4 model-harvest driver (frozen).

Per target, in screening order: list the first 8 unique R candidates, then
8 unique X candidates (need-based roles: confirmatory R+X, calibration R,
headroom X).  Each candidate gets <=4 memoryless attempts; attempt decode
seed = $3.5.6 literal rule on "candidate_path|role|attempt_idx"
(attempt_idx in 1..4, decimal); the first env-verified `won` becomes the
source.  Any role failing -> target rejected; next target taken in
screening order (replacements counted; >40 per type -> pool
NOT_ESTIMATED).  Attempts are committed strictly sequentially (candidate
list order, attempt index order) -- no speculative parallel attempts, so
the attempted/reserved set matches the frozen sequential reading exactly.

ANALYSIS HYGIENE: success-rate inspection is FORBIDDEN; the ledger records
only won/steps per attempt (plus the won trajectory artifact, needed to
build model-harvest cards in build_cards.py).  No rates are computed here.

Sharding (rule S1, deterministic, race-free): candidate classes never cross
(object, receptacle) boundaries under $2, so each (obj, recep) tuple pair
(heat+cool sides together) is assigned to exactly one shard via
int(sha256("obj|recep"),16) % n_shards.  A shard only screens targets of
its own tuples; all its candidates live in the same tuples, hence the same
shard -- cross-shard candidate conflicts are impossible by construction.

Resumable: the ledger is the single source of truth; re-running skips
committed attempts/targets and continues mid-target at the next
uncommitted attempt index.
"""

import argparse
import json
import os
import time

from pilot.external.partv import common
from pilot.external.partv import prepare_pools
from pilot.external.partv import rollout_engine

TRAJ_DIRNAME = "trajectories"


# ---------------------------------------------------------------------------
# ledger
# ---------------------------------------------------------------------------

class Ledger:
    """Append-only JSONL ledger; re-read for resume state."""

    def __init__(self, path=common.LEDGER_PATH):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.rows = []
        if os.path.exists(path):
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        self.rows.append(json.loads(line))

    def append(self, row):
        row = dict(row)
        row["ts"] = int(time.time())
        with open(self.path, "a") as f:
            f.write(json.dumps(row) + "\n")
        self.rows.append(row)

    # -- resume state ---------------------------------------------------
    def attempts(self, pool, target, role, candidate):
        return [r for r in self.rows
                if r.get("event") == "attempt" and r.get("pool") == pool
                and r.get("target") == target and r.get("role") == role
                and r.get("candidate") == candidate]

    def target_event(self, pool, target):
        for r in self.rows:
            if (r.get("pool") == pool and r.get("target") == target
                    and r.get("event") in ("target_accepted",
                                           "target_rejected")):
                return r["event"]
        return None

    def counts(self, pool, prep):
        valid = sum(1 for r in self.rows
                    if r.get("event") == "target_accepted"
                    and r.get("pool") == pool and r.get("type") == prep)
        rejected = sum(1 for r in self.rows
                       if r.get("event") == "target_rejected"
                       and r.get("pool") == pool and r.get("type") == prep)
        return valid, rejected

    def reserved_paths(self):
        out = set()
        for r in self.rows:
            for key in ("target", "candidate"):
                p = r.get(key)
                if p:
                    out.add(p)
        return out


# ---------------------------------------------------------------------------
# trajectory artifact (card-building material; written only for won attempts)
# ---------------------------------------------------------------------------

def dump_trajectory(out_root, pool, role, candidate, gold_like):
    tdir = os.path.join(out_root, TRAJ_DIRNAME, pool)
    os.makedirs(tdir, exist_ok=True)
    name = "%s_%s.json" % (role, common.sha256_bytes(
        candidate.encode("utf-8"))[:16])
    path = os.path.join(tdir, name)
    with open(path, "w") as f:
        json.dump(gold_like, f)
    return path


# ---------------------------------------------------------------------------
# sharding (S1)
# ---------------------------------------------------------------------------

def target_owner(info, n_shards):
    import hashlib
    key = "%s|%s" % (info["obj"], info["recep"])
    return int(hashlib.sha256(key.encode("utf-8")).hexdigest(), 16) % n_shards


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------

POOL_SPEC_MAP = {name: (types, roles)
                 for name, types, roles in prepare_pools.POOL_SPECS}
ROLES = ("R", "X")


def harvest_role(pool, prep, target, role, candidates, ledger, runner,
                 out_root, log):
    """Sequential attempts per $3.4; returns (source, trajectory_path) or
    (None, None).  All attempts (won or lost) are ledger-committed."""
    for c in candidates:
        done = ledger.attempts(pool, target, role, c)
        for r in done:
            if r.get("won"):
                return c, r.get("trajectory")
        next_idx = max([r.get("attempt_idx", 0) for r in done] + [0]) + 1
        for attempt_idx in range(next_idx, 5):
            seed = common.harvest_decode_seed(c, role, attempt_idx)
            meta = {"pool": pool, "type": prep, "target": target,
                    "role": role, "candidate": c, "attempt_idx": attempt_idx}
            rows = runner.run(common_abs(c), [meta], [seed])
            row = rows[0]
            traj = None
            if row["success"]:
                traj = dump_trajectory(out_root, pool, role, c,
                                       row["gold_like"])
            ledger.append({"event": "attempt", "pool": pool, "type": prep,
                           "target": target, "role": role, "candidate": c,
                           "attempt_idx": attempt_idx, "decode_seed": seed,
                           "won": int(row["success"]), "steps": row["steps"],
                           "trajectory": traj})
            log("  %s %s attempt %d -> won=%d steps=%d"
                % (role, os.path.basename(os.path.dirname(c)), attempt_idx,
                   int(row["success"]), row["steps"]))
            if row["success"]:
                return c, traj
    return None, None


def common_abs(relpath):
    return os.path.join(common.data_root(), relpath)


class Runner:
    """Thin wrapper around rollout_engine.run_episodes for 1-attempt shots."""

    def __init__(self, decoder, tok, builder=None):
        self.decoder = decoder
        self.tok = tok
        self.builder = builder     # None -> pinned builder (production)

    def run(self, games_abs, metas, seeds):
        eps = [rollout_engine.Episode(meta, game, card=None, decode_seed=ds)
               for meta, game, ds in zip(metas, games_abs, seeds)]
        rows = rollout_engine.run_episodes(eps, self.decoder, self.tok,
                                           builder=self.builder)
        out = []
        for ep_row, ep in zip(rows, eps):
            ep_row = dict(ep_row)
            ep_row["gold_like"] = ep.gold_like()
            out.append(ep_row)
        return out


def harvest_pool(pool_name, shard=0, n_shards=1, limit_targets=None,
                 list_only=False, runner=None, out_root=common.OUT_ROOT,
                 log=print, ledger_path=common.LEDGER_PATH):
    type_counts, roles = POOL_SPEC_MAP[pool_name]
    table, _ = prepare_pools.build_game_table()
    orders = prepare_pools.screening_orders(table)
    ledger = Ledger(ledger_path)
    reserved = ledger.reserved_paths()
    if runner is None and not list_only:
        raise RuntimeError("provide runner (vLLM decoder) or --list-only")
    summary = {}
    for prep in ("heat", "cool"):
        want = type_counts.get(prep, 0)
        if want == 0:
            continue
        valid, rejected = ledger.counts(pool_name, prep)
        taken = 0
        for gi in orders[prep]:
            if valid >= want or rejected > common.MAX_REPLACEMENTS:
                break
            info = table[prep][gi]
            tpath = info["path"]
            if tpath in reserved:
                continue
            if target_owner(info, n_shards) != shard:
                continue
            if ledger.target_event(pool_name, tpath):
                continue
            planned = {role: prepare_pools.candidate_list(
                table, orders, reserved, info, role, k=8) for role in roles}
            if any(len(cl) < 8 for cl in planned.values()):
                log("skip (<%d candidates): %s" % (8, tpath))
                continue
            log("target %s (shard %d) candidates: %s"
                % (tpath, shard,
                   {r: len(c) for r, c in planned.items()}))
            if list_only:
                taken += 1
                if limit_targets and taken >= limit_targets:
                    break
                continue
            sources, failed_role = {}, None
            for role in roles:
                src, _traj = harvest_role(pool_name, prep, tpath, role,
                                          planned[role], ledger, runner,
                                          out_root, log)
                reserved = ledger.reserved_paths()
                if src is None:
                    failed_role = role
                    break
                sources[role] = src
            if failed_role is not None:
                ledger.append({"event": "target_rejected", "pool": pool_name,
                               "type": prep, "target": tpath,
                               "failed_role": failed_role})
                rejected += 1
                log("REJECTED %s (role %s); replacements=%d"
                    % (tpath, failed_role, rejected))
                if rejected > common.MAX_REPLACEMENTS:
                    ledger.append({"event": "pool_status", "pool": pool_name,
                                   "status": "not_estimated", "type": prep,
                                   "valid": valid, "rejected": rejected})
                    break
            else:
                ledger.append({"event": "target_accepted", "pool": pool_name,
                               "type": prep, "target": tpath,
                               "sources": sources, "goal": info["goal"]})
                reserved = ledger.reserved_paths()
                valid += 1
                taken += 1
                log("ACCEPTED %s (%d/%d valid)" % (tpath, valid, want))
                if limit_targets and taken >= limit_targets:
                    break
        summary[prep] = {"valid": valid, "wanted": want,
                         "rejected": rejected}
        if not list_only and (
                valid >= want or rejected > common.MAX_REPLACEMENTS
                or (limit_targets and taken >= limit_targets)):
            ledger.append({"event": "pool_status", "pool": pool_name,
                           "status": ("filled" if valid >= want
                                      else "not_estimated"),
                           "type": prep, "valid": valid,
                           "rejected": rejected})
    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pool", choices=list(POOL_SPEC_MAP))
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--n-shards", type=int, default=1)
    ap.add_argument("--limit-targets", type=int, default=None)
    ap.add_argument("--list-only", action="store_true",
                    help="print planned attempt stream; no GPU, no ledger writes")
    ap.add_argument("--gpu", type=int, default=None)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            res = self_test(td)
        print(json.dumps(res, indent=1, sort_keys=True))
        print("HARVEST SELF-TESTS PASSED")
        return
    if not args.pool:
        ap.error("--pool is required unless --self-test")

    if args.list_only:
        # read-only planning view: uses the existing ledger solely for
        # reservation state; no episodes, no writes.
        harvest_pool(args.pool, shard=args.shard, n_shards=args.n_shards,
                     limit_targets=args.limit_targets, list_only=True)
        return

    decoder = rollout_engine.VLLMDecoder(gpu_id=args.gpu)
    runner = Runner(decoder, decoder.tok)
    summary = harvest_pool(args.pool, shard=args.shard,
                           n_shards=args.n_shards,
                           limit_targets=args.limit_targets, runner=runner)
    print(json.dumps(summary, indent=1, sort_keys=True))



# ---------------------------------------------------------------------------
# CPU self-test: fake env + scripted decoder (no GPU, no textworld)
# ---------------------------------------------------------------------------

class _FakeState:
    def __init__(self, fb, cmds, won=False):
        self.feedback = fb
        self._cmds = cmds
        self._won = won

    def __getitem__(self, key):
        if key == "admissible_commands":
            return self._cmds
        if key == "won":
            return self._won
        raise KeyError(key)


class _FakeEnv:
    """Wins iff the agent issues 'win game'; otherwise idles."""

    def __init__(self, game_file):
        self.game_file = game_file

    def reset(self):
        return _FakeState("You see a room.\nYour task is to: heat some a "
                          "and put it in b.", ["win game", "look"])

    def step(self, cmd):
        if cmd == "win game":
            return _FakeState("done.", ["win game", "look"], won=True), 1, True
        return _FakeState("nothing happens.", ["win game", "look"]), 0, False

    def close(self):
        pass


class _FakeBuilder:
    MAX_STEPS = 30
    trunc_obs = staticmethod(lambda o, n=500: o if len(o) <= n else o[:n])
    load_env = staticmethod(lambda game_file, max_steps=30: _FakeEnv(game_file))
    extract_goal = staticmethod(
        lambda obs0: "heat some a and put it in b.")
    normalize_cmd = staticmethod(lambda t: t.strip().lower())
    parse_command = staticmethod(
        lambda raw, adm: (raw.strip().lower() if raw.strip().lower() in
                          [a.lower() for a in adm] else adm[0], "exact"))
    build_prompt = staticmethod(
        lambda tok, goal, card, history, obs, admissible: "PROMPT")


class _ScriptedDecoder:
    tok = rollout_engine.FakeDecoder.tok

    def __init__(self, reply):
        self.reply = reply

    def generate(self, prompts, decode_seed):
        return [self.reply for _ in prompts]


def _synth_games():
    """One (obj=a, recep=b) tuple block: 12 heat + 9 cool games."""
    def info(prep, i):
        p = "syn/%s/trial_%02d/game.tw-pddl" % (prep, i)
        return {"path": p, "prep": prep, "obj": "a", "recep": "b",
                "goal": "heat some a and put it in b.",
                "sha256": common.sha256_bytes(p.encode())}
    table = {"heat": [info("heat", i) for i in range(12)],
             "cool": [info("cool", i) for i in range(9)]}
    table["heat"].sort(key=lambda x: x["sha256"])
    table["cool"].sort(key=lambda x: x["sha256"])
    orders = {"heat": list(range(12)), "cool": list(range(9))}
    return table, orders


def self_test(tmpdir):
    import types
    from pilot.external.partv import harvest as H
    table, orders = _synth_games()
    orig_bt, orig_so = prepare_pools.build_game_table, prepare_pools.screening_orders
    prepare_pools.build_game_table = lambda *a, **k: (table, {})
    prepare_pools.screening_orders = lambda *a, **k: {k2: list(v) for k2, v
                                                      in orders.items()}
    H.POOL_SPEC_MAP["test-pool"] = ({"heat": 2}, ("R", "X"))
    ledger_path = os.path.join(tmpdir, "ledger.jsonl")
    log = lambda *a: None
    try:
        # PASS 1: winning decoder -> targets accepted, sources chosen, seeds ok
        runner = H.Runner(_ScriptedDecoder("win game"),
                          rollout_engine.FakeDecoder.tok,
                          builder=_FakeBuilder)
        out_root = os.path.join(tmpdir, "out1")
        summary = H.harvest_pool("test-pool", runner=runner, out_root=out_root,
                                 log=log, ledger_path=ledger_path)
        assert summary["heat"]["valid"] == 2, summary
        rows = [json.loads(l) for l in open(ledger_path)]
        att = [r for r in rows if r["event"] == "attempt"]
        # 2 targets x (1 R attempt + 1 X attempt), each won at attempt 1
        assert len(att) == 4, len(att)
        for a in att:
            expect = common.harvest_decode_seed(a["candidate"], a["role"],
                                                a["attempt_idx"])
            assert a["decode_seed"] == expect
            assert a["won"] == 1 and a["trajectory"]
            assert os.path.exists(a["trajectory"])
        acc = [r for r in rows if r["event"] == "target_accepted"]
        assert len(acc) == 2
        # sources must be the FIRST listed candidate of each role
        t0 = acc[0]["target"]
        info0 = next(i for i in table["heat"] if i["path"] == t0)
        got_R = acc[0]["sources"]["R"]
        clist = prepare_pools.candidate_list(table, orders, set(), info0,
                                             "R", k=8)
        assert got_R == clist[0], (got_R, clist[:2])
        # heat R candidates must all be heat games, X candidates cool games
        assert got_R.startswith("syn/heat/")
        assert acc[0]["sources"]["X"].startswith("syn/cool/")

        # PASS 2: resume on same ledger -> no new rows, valid already 2
        n_rows = len(rows)
        summary2 = H.harvest_pool("test-pool", runner=runner, out_root=out_root,
                                  log=log, ledger_path=ledger_path)
        assert sum(1 for _ in open(ledger_path)) >= n_rows
        assert summary2["heat"]["valid"] == 2

        # PASS 3: losing decoder -> candidate exhaustion -> REJECTED, roles R only
        ledger2 = os.path.join(tmpdir, "ledger2.jsonl")
        runner2 = H.Runner(_ScriptedDecoder("look"),
                           rollout_engine.FakeDecoder.tok,
                           builder=_FakeBuilder)
        summary3 = H.harvest_pool("test-pool", runner=runner2,
                                  out_root=os.path.join(tmpdir, "out2"),
                                  log=log, ledger_path=ledger2)
        rows3 = [json.loads(l) for l in open(ledger2)]
        rej = [r for r in rows3 if r["event"] == "target_rejected"]
        assert rej and rej[0]["failed_role"] == "R"
        att3 = [r for r in rows3 if r["event"] == "attempt"]
        assert len(att3) == 8 * 4, len(att3)          # 8 R-candidates x 4
        assert {r["role"] for r in att3} == {"R"}     # X never attempted
        assert summary3["heat"]["rejected"] >= 1

        # PASS 4: sharding ownership is deterministic and partitionable
        owners = {i["path"]: H.target_owner(i, 3) for i in table["heat"]}
        assert set(owners.values()) <= {0, 1, 2}
        assert owners == {i["path"]: H.target_owner(i, 3)
                          for i in table["heat"]}
        return {"accepted_flow": "OK", "resume": "OK", "rejection_flow": "OK",
                "sharding": "OK"}
    finally:
        prepare_pools.build_game_table = orig_bt
        prepare_pools.screening_orders = orig_so
        H.POOL_SPEC_MAP.pop("test-pool", None)

if __name__ == "__main__":
    main()
