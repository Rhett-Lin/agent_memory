"""Part V main-grid driver ($3, $6, $9; frozen).

rollout_unit = (cluster target, seed, cell) with cells (arms) N/R/X:
  N: no memory; R: model-harvest R card; X: model-harvest X card.
Only confirmatory-heat(60) + confirmatory-cool(60) clusters enter the grid.

Frozen mechanics:
  - framing: chosen by $7 headroom outcome.  MEM_A == builder MEM_BLOCK
    verbatim (mem_header=None path, byte-identical to the pinned builder);
    MEM_B = prompts-package mem_B with everything else verbatim.
  - decode seed per rollout unit: $3.5.6 on "target_path|<seed decimal>"
    (documented interpretation G1 -- mirrors the builder's (game|seed)
    pairing through the frozen MD5 rule).
  - grid order: shuffle of (cluster x seed x cell) by
    np.argsort(rng_rollout.random(n), kind="stable") over the
    sha256-ascending unit keys; rng_rollout = PCG64(20260810) exactly as
    $3.5.2 -- never mixed with rng_screen (drawn once, here).
  - waves of 16; wave/batch id into row meta ($8).

Resumable: done (target, seed, arm) keys are skipped.

ANALYSIS HYGIENE: success-rate inspection is FORBIDDEN; rows are written
blind and only analyze_gate.py (post-freeze) may aggregate.
"""

import argparse
import json
import os

import numpy as np

from pilot.external.partv import common
from pilot.external.partv import rollout_engine

GRID_PATH = os.path.join(common.OUT_ROOT, "grid", "rollouts.jsonl")


def grid_units(cards):
    """(target x seed x arm) with a cards-backed card per arm."""
    units = []
    for target in sorted(cards):
        cinfo = cards[target]
        if not str(cinfo.get("pool", "")).startswith("confirmatory-"):
            continue
        for seed in common.GRID_SEEDS:
            for arm in common.ARMS:
                card = None if arm == "N" else cinfo[arm]["text"]
                card_sha = None if arm == "N" else cinfo[arm]["sha256"]
                units.append({"type": cinfo["type"], "target": target,
                              "seed": seed, "arm": arm, "card": card,
                              "card_sha256": card_sha,
                              "goal": cinfo["goal"]})
    return units


def grid_order(units):
    """Frozen rng_rollout shuffle: sha256-asc keys -> stable argsort."""
    keys = ["%s|%s|%d" % (u["target"], u["arm"], u["seed"]) for u in units]
    shas = [common.sha256_bytes(k.encode()) for k in keys]
    base = sorted(range(len(units)), key=lambda i: shas[i])
    units = [units[i] for i in base]
    rng = np.random.Generator(np.random.PCG64(common.SEED_RNG_ROLLOUT))
    perm = np.argsort(rng.random(len(units)), kind="stable")
    return [units[int(i)] for i in perm]


def build_episodes(units, mem_header, out_root=common.OUT_ROOT,
                   rows_path=None):
    done = set()
    if rows_path is None:
        rows_path = os.path.join(out_root, "grid", "rollouts.jsonl")
    if os.path.exists(rows_path):
        with open(rows_path) as f:
            for line in f:
                if line.strip():
                    r = json.loads(line)
                    done.add((r["target"], r["seed"], r["arm"]))
    eps = []
    for u in units:
        if (u["target"], u["seed"], u["arm"]) in done:
            continue
        ds = common.md5_decode_seed("%s|%d" % (u["target"], u["seed"]))
        meta = {"pool": "confirmatory", "type": u["type"],
                "target": u["target"], "seed": u["seed"], "arm": u["arm"],
                "card_sha256": u["card_sha256"]}
        eps.append(rollout_engine.Episode(
            meta, os.path.join(common.data_root(), u["target"]),
            card=u["card"], mem_header=mem_header, decode_seed=ds))
    return eps, len(done)


def main_grid(out_root=common.OUT_ROOT, limit=None, decoder=None, tok=None,
              builder=None, log=print, shard=0, n_shards=1):
    with open(os.path.join(out_root, "cards.json")) as f:
        cards = json.load(f)
    with open(os.path.join(out_root, "audits.json")) as f:
        audits = json.load(f)
    chosen = (audits.get("headroom") or {}).get("chosen")
    if (audits.get("headroom") or {}).get("passed") is not True or \
            chosen not in ("A", "B"):
        raise RuntimeError("headroom precondition not satisfied -> "
                           "main grid must not run (NOT_ESTIMATED)")
    prompts_pkg = common.load_prompts()
    mem_header = None if chosen == "A" else prompts_pkg["mem_B"]
    units = grid_order(grid_units(cards))
    units = [u for i, u in enumerate(units) if i % n_shards == shard]
    if limit:
        units = units[:limit]
    # parallel shards write disjoint per-shard files (merged later by `cat`);
    # shared-file concurrent appends could tear long JSON rows.
    rows_path = os.path.join(
        out_root, "grid",
        "rollouts.jsonl" if n_shards == 1 else
        "rollouts.s%d.jsonl" % shard)
    os.makedirs(os.path.dirname(rows_path), exist_ok=True)
    eps, n_done = build_episodes(units, mem_header, out_root=out_root,
                                 rows_path=rows_path)
    log("grid: %d rollout units total, %d already done, %d to run"
        % (len(units), n_done, len(eps)))
    if decoder is None:
        decoder = rollout_engine.VLLMDecoder()
        tok = decoder.tok

    def on_wave(wave_idx, rows):
        with open(rows_path, "a") as f:
            for r in rows:
                r["wave"] = wave_idx
                r["batch"] = "s%d-w%03d" % (shard, wave_idx)
                f.write(json.dumps(r) + "\n")

    rollout_engine.run_episodes(eps, decoder, tok, on_wave=on_wave,
                                prompts_pkg=prompts_pkg, builder=builder)
    return {"total_units": len(units), "ran": len(eps)}


# ---------------------------------------------------------------------------
# CPU self-test
# ---------------------------------------------------------------------------

def _synth_cards(n=3):
    cards = {}
    for typ in ("heat", "cool"):
        for i in range(n):
            t = "syn/%s/trial_%d/game.tw-pddl" % (typ, i)
            cards[t] = {"type": typ, "goal": "put a hot mug in x",
                        "pool": "confirmatory-%s" % typ,
                        "R": {"text": "rcard %s %d" % (typ, i),
                              "sha256": common.sha256_bytes(b"r"),
                              "tokens": 210},
                        "X": {"text": "xcard %s %d" % (typ, i),
                              "sha256": common.sha256_bytes(b"x"),
                              "tokens": 210}}
    return cards


def self_test(tmpdir):
    cards = _synth_cards()
    units_a = grid_units(cards)
    # N arm carries no card; R/X carry their own cards; 2x3x4x3 = 72 units
    assert len(units_a) == 2 * 3 * 4 * 3, len(units_a)
    for u in units_a:
        if u["arm"] == "N":
            assert u["card"] is None
        else:
            assert u["card"] and u["card"].startswith(u["arm"].lower())
    # frozen order: deterministic across calls, uses rng_rollout
    o1 = [("%s|%s|%d" % (u["target"], u["arm"], u["seed"]))
          for u in grid_order(list(units_a))]
    o2 = [("%s|%s|%d" % (u["target"], u["arm"], u["seed"]))
          for u in grid_order(list(units_a))]
    assert o1 == o2 and len(o1) == len(set(o1))
    # not the identity order (shuffle actually permutes)
    ident = ["%s|%s|%d" % (u["target"], u["arm"], u["seed"])
             for u in units_a]
    shuffled = ["%s|%s|%d" % (u["target"], u["arm"], u["seed"])
                for u in grid_order(units_a)]
    assert o1 == shuffled and shuffled != ident and \
        sorted(shuffled) == sorted(ident)
    # decode seeds follow the frozen MD5 rule
    for u in units_a[:5]:
        ds = common.md5_decode_seed("%s|%d" % (u["target"], u["seed"]))
        assert 0 <= ds < 2 ** 31
    # episode build: resume skips done keys
    out_root = tmpdir
    os.makedirs(os.path.join(out_root, "grid"), exist_ok=True)
    json.dump(cards, open(os.path.join(out_root, "cards.json"), "w"))
    json.dump({"headroom": {"passed": True, "chosen": "A"}},
              open(os.path.join(out_root, "audits.json"), "w"))
    with open(os.path.join(out_root, "grid", "rollouts.jsonl"), "w") as f:
        u = units_a[0]
        f.write(json.dumps({"pool": "confirmatory", "type": u["type"],
                            "target": u["target"], "seed": u["seed"],
                            "arm": u["arm"], "success": 1, "steps": 1,
                            "commands": [], "goal": u["goal"]}) + "\n")
    eps, n_done = build_episodes(units_a, None, out_root=out_root)
    assert n_done == 1 and len(eps) == len(units_a) - 1
    # headroom not passed -> grid refuses
    json.dump({"headroom": {"passed": False, "chosen": None}},
              open(os.path.join(out_root, "audits.json"), "w"))
    try:
        main_grid(out_root=out_root, limit=1,
                  decoder=rollout_engine.FakeDecoder(), builder=None)
        raise AssertionError("grid must refuse when headroom failed")
    except RuntimeError:
        pass
    return {"units": len(units_a), "order_deterministic": "OK",
            "resume": "OK", "refusal": "OK"}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-root", default=common.OUT_ROOT)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--n-shards", type=int, default=1)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            res = self_test(td)
        print(json.dumps(res, indent=1, sort_keys=True))
        print("GRID SELF-TESTS PASSED")
        return
    print(json.dumps(main_grid(out_root=args.out_root, limit=args.limit,
                               shard=args.shard, n_shards=args.n_shards),
                     indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
