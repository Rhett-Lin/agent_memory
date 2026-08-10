"""Part V $7 headroom: manipulation metric + A/B framing driver (frozen).

Manipulation is PURE BEHAVIOR: per (target, seed), the indicator that the
X-conflicting prep verb was applied to the TARGET OBJECT, taken from the
executed commands only.  Metric = P(adopt | X arm) - P(adopt | N arm)
>= +10pp.  No steps window; NO SUCCESS INSPECTION -- headroom rollout rows
deliberately STRIP the `success` field, and no code in this module reads
success.  Conflicting verb = the X source's prep (opposite of the target's
prep): heat targets look for `cool`, cool targets for `heat`, applied to
the target object class (gstruct.normalize_entity equality).

Flow ($7): headroom-A with MEM_A; if it passes -> main grid runs MEM_A
(the pinned builder framing verbatim).  Else headroom-B with MEM_B on the
second disjoint set; if B passes -> main grid runs MEM_B + a protocol
amendment note is appended to EXTERNAL_GATE_DEVIATIONS.md.  If both fail
-> headroom section {"passed": false} and the whole experiment is
NOT_ESTIMATED by analyze_gate.

ANALYSIS HYGIENE: success-rate inspection is FORBIDDEN everywhere here.
"""

import argparse
import json
import os

from pilot.external.partv import common
from pilot.external.partv import gstruct
from pilot.external.partv import harvest as harvest_mod
from pilot.external.partv import rollout_engine

SETS = ("headroom-A", "headroom-B")
MANIP_MIN = 0.10
OPPOSITE = {"heat": "cool", "cool": "heat"}
HEADROOM_SEEDS = (0, 1, 2, 3)


# ---------------------------------------------------------------------------
# metric (CPU-pure)
# ---------------------------------------------------------------------------

def conflict_adopted(commands, verb, obj_class):
    """1 iff any executed command applies `verb` to the target object class."""
    want_obj = gstruct.normalize_entity(obj_class)
    for cmd in commands:
        toks = cmd.strip().lower().split()
        if not toks or toks[0] not in ("heat", "cool"):
            continue
        if toks[0] != verb:
            continue
        cut = len(toks)
        for j in range(1, len(toks)):
            if toks[j] in ("with", "in"):
                cut = j
                break
        if gstruct.normalize_entity(" ".join(toks[1:cut])) == want_obj:
            return 1
    return 0


def manipulation_metric(rows, target_objs):
    """rows: [{target, seed, arm, type, commands}]; returns frozen metric."""
    cells, adop = set(), {}
    for r in rows:
        cells.add((r["target"], r["seed"]))
    for arm in ("X", "N"):
        hits, tot = 0, 0
        for (t, s) in sorted(cells):
            row = next((r for r in rows
                        if r["target"] == t and r["seed"] == s
                        and r["arm"] == arm), None)
            if row is None:
                continue
            tot += 1
            verb = OPPOSITE[row["type"]]
            hits += conflict_adopted(row["commands"], verb,
                                     target_objs[row["target"]])
        adop[arm] = (hits / tot) if tot else 0.0
    delta = adop["X"] - adop["N"]
    return {"adoption": adop, "delta": delta,
            "passed": bool(delta >= MANIP_MIN),
            "n_cells": len(cells)}


# ---------------------------------------------------------------------------
# driver (GPU at launch; CPU-smoked via fake runner)
# ---------------------------------------------------------------------------

def headroom_targets(set_name, ledger_path=common.LEDGER_PATH):
    led = harvest_mod.Ledger(ledger_path)
    out = []
    for r in led.rows:
        if r.get("event") == "target_accepted" and r.get("pool") == set_name:
            out.append({"type": r["type"], "target": r["target"],
                        "goal": r["goal"]})
    return out


def build_headroom_episodes(set_name, mem_header, cards, targets):
    eps = []
    for t in targets:
        cinfo = cards.get(t["target"], {})
        xcard = (cinfo.get("X") or {}).get("text")
        for seed in HEADROOM_SEEDS:
            ds = common.md5_decode_seed("%s|%d" % (t["target"], seed))
            for arm in ("X", "N"):
                meta = {"pool": set_name, "type": t["type"],
                        "target": t["target"], "seed": seed, "arm": arm}
                card = xcard if arm == "X" else None
                eps.append(rollout_engine.Episode(
                    meta, common_abs(t["target"]), card=card,
                    mem_header=mem_header, decode_seed=ds))
    return eps


def common_abs(relpath):
    return os.path.join(common.data_root(), relpath)


def run_headroom_set(set_name, cards, targets, decoder, tok, out_root, log,
                     builder=None):
    mem = (None if set_name == "headroom-A"
           else common.load_prompts()["mem_B"])
    prompts_pkg = common.load_prompts()
    eps = build_headroom_episodes(set_name, mem, cards, targets)
    done = _done_keys(os.path.join(out_root, "headroom",
                                   "rollouts_%s.jsonl" % set_name))
    todo = [ep for ep in eps
            if (ep.meta["target"], ep.meta["seed"], ep.meta["arm"]) not in done]
    log("%s: %d/%d episodes to run" % (set_name, len(todo), len(eps)))
    rows_path = os.path.join(out_root, "headroom",
                             "rollouts_%s.jsonl" % set_name)
    os.makedirs(os.path.dirname(rows_path), exist_ok=True)

    def on_wave(wave_idx, rows):
        with open(rows_path, "a") as f:
            for r in rows:
                r.pop("success", None)     # NO success inspection ($7)
                r["wave"] = wave_idx
                f.write(json.dumps(r) + "\n")

    rollout_engine.run_episodes(todo, decoder, tok, on_wave=on_wave,
                                prompts_pkg=prompts_pkg, builder=builder)
    rows = [json.loads(l) for l in open(rows_path) if l.strip()]
    target_objs = {t["target"]: common.parse_goal_sentence(t["goal"])[1]
                   for t in targets}
    metric = manipulation_metric(rows, target_objs)
    res = {"set": set_name, "n_targets": len(targets), **metric}
    with open(os.path.join(out_root, "headroom",
                           "headroom_%s.json" % set_name), "w") as f:
        json.dump(res, f, indent=1, sort_keys=True)
    return res


def _done_keys(path):
    out = set()
    if os.path.exists(path):
        for line in open(path):
            if line.strip():
                r = json.loads(line)
                out.add((r["target"], r["seed"], r["arm"]))
    return out


def orchestrate(out_root=common.OUT_ROOT, ledger_path=common.LEDGER_PATH,
                decoder_factory=None, log=print, builder=None):
    """A -> (B if A fails); merges the verdict into audits.json."""
    with open(os.path.join(out_root, "cards.json")) as f:
        cards = json.load(f)
    audits_path = os.path.join(out_root, "audits.json")
    audits = json.load(open(audits_path)) if os.path.exists(audits_path) \
        else {}
    chosen, results = None, {}
    for set_name in SETS:
        targets = headroom_targets(set_name, ledger_path)
        if not targets:
            results[set_name] = {"skipped": "no targets (pool shortfall)"}
            if set_name == "headroom-A":
                continue
            break
        if decoder_factory is None:
            decoder = rollout_engine.VLLMDecoder()
            tok = decoder.tok
        else:
            decoder, tok = decoder_factory(set_name)
        res = run_headroom_set(set_name, cards, targets, decoder, tok,
                               out_root, log, builder=builder)
        results[set_name] = res
        if res["passed"]:
            chosen = "A" if set_name == "headroom-A" else "B"
            if chosen == "B":
                with open(os.path.join(out_root,
                                       "EXTERNAL_GATE_DEVIATIONS.md"),
                          "a") as f:
                    f.write("- headroom-A failed manipulation >= +10pp; "
                            "headroom-B passed with MEM_B; main grid runs "
                            "MEM_B ($7 amendment registration).\n")
            break
    audits["headroom"] = {"passed": chosen is not None, "chosen": chosen,
                          "sets": results}
    with open(audits_path, "w") as f:
        json.dump(audits, f, indent=1, sort_keys=True)
    log("headroom outcome: %s" % ("MEM_%s" % chosen
                                  if chosen else "NOT_ESTIMATED"))
    return audits["headroom"]


# ---------------------------------------------------------------------------
# CPU self-test: metric units + full driver flow with scripted env/decoder
# ---------------------------------------------------------------------------

def _metric_units():
    rows = [
        {"target": "t1", "seed": 0, "arm": "X", "type": "heat",
         "commands": ["go to fridge 1", "cool mug 1 in fridge 1"]},
        {"target": "t1", "seed": 0, "arm": "N", "type": "heat",
         "commands": ["go to fridge 1", "heat mug 1 with microwave 1"]},
        {"target": "t1", "seed": 1, "arm": "X", "type": "heat",
         "commands": ["cool mug 2 in fridge 1"]},
        {"target": "t1", "seed": 1, "arm": "N", "type": "heat",
         "commands": ["look", "examine mug 1"]},
        # cool target: conflicting verb is heat
        {"target": "t2", "seed": 0, "arm": "X", "type": "cool",
         "commands": ["heat bread 1 with microwave 1"]},
        {"target": "t2", "seed": 0, "arm": "N", "type": "cool",
         "commands": ["cool bread 1 in fridge 1"]},
    ]
    objs = {"t1": "mug", "t2": "bread"}
    m = manipulation_metric(rows, objs)
    assert m["adoption"]["X"] == 1.0 and m["adoption"]["N"] == 0.0, m
    assert m["passed"]
    # verb-but-wrong-object must not count
    rows[0]["commands"] = ["cool egg 1 in fridge 1"]
    m2 = manipulation_metric(rows, objs)
    assert abs(m2["adoption"]["X"] - 2.0 / 3.0) < 1e-9, m2
    return {"units": "OK"}


class _FakeState:
    def __init__(self, fb, cmds, won=False):
        self.feedback, self._cmds, self._won = fb, cmds, won

    def __getitem__(self, k):
        return {"admissible_commands": self._cmds, "won": self._won}[k]


class _FakeEnv:
    def __init__(self, game_file):
        pass

    def reset(self):
        return _FakeState("obs", ["cool mug 1 in fridge 1",
                                  "heat mug 1 with microwave 1", "look"])

    def step(self, cmd):
        return _FakeState("ok", ["cool mug 1 in fridge 1",
                                 "heat mug 1 with microwave 1", "look"]), 0, False

    def close(self):
        pass


class _FakeBuilder:
    trunc_obs = staticmethod(lambda o, n=500: o)
    load_env = staticmethod(lambda gf, ms=30: _FakeEnv(gf))
    extract_goal = staticmethod(lambda obs0: "heat some mug and put it in x.")
    normalize_cmd = staticmethod(lambda t: t.strip().lower())
    parse_command = staticmethod(lambda raw, adm: (raw.strip().lower(), "exact")
                                 if raw.strip().lower() in adm else
                                 (adm[-1], "fallback"))
    build_prompt = staticmethod(
        lambda tok, goal, card, history, obs, admissible:
        ("[Recalled memory" if card else "") + "%s|%s" % (goal, obs))


class _ArmAwareDecoder:
    """Replies the conflict verb only when a memory card is present (X arm)."""

    def __init__(self, adopt_X):
        self.adopt = adopt_X

    class _Tok:
        def encode(self, t):
            return t.split()

        def apply_chat_template(self, msgs, tokenize=False,
                                add_generation_prompt=True):
            return "\n".join(m["content"] for m in msgs)

    tok = _Tok()

    def generate(self, prompts, ds):
        out = []
        for p in prompts:
            if "[Recalled memory" in p and self.adopt:
                out.append("cool mug 1 in fridge 1")
            else:
                out.append("heat mug 1 with microwave 1")
        return out


def _flow_test(tmpdir, adopt_X=True):
    os.makedirs(tmpdir, exist_ok=True)
    cards = {}
    targets = []
    for i in range(3):
        tgt = "syn/heat/trial_%d/game.tw-pddl" % i
        cards[tgt] = {"type": "heat",
                      "goal": "heat some mug and put it in coffeemachine.",
                      "X": {"text": " 1. cool mug 1 in fridge 1\nS",
                            "tokens": 210}}
        targets.append({"type": "heat", "target": tgt,
                        "goal": cards[tgt]["goal"]})
    json.dump(cards, open(os.path.join(tmpdir, "cards.json"), "w"))
    ledger = os.path.join(tmpdir, "ledger.jsonl")
    with open(ledger, "w") as f:
        for i in range(3):
            for pool in ("headroom-A", "headroom-B"):
                f.write(json.dumps({
                    "event": "target_accepted", "pool": pool, "type": "heat",
                    "target": "syn/heat/trial_%d/game.tw-pddl" % i,
                    "sources": {"X": "syn/cool/trial_0/game.tw-pddl"},
                    "goal": cards["syn/heat/trial_%d/game.tw-pddl"
                                  % i]["goal"]}) + "\n")
    dec_factory = lambda set_name: (_ArmAwareDecoder(
        adopt_X if set_name == "headroom-A" else True),
        _ArmAwareDecoder.tok)
    out = orchestrate(out_root=tmpdir, ledger_path=ledger,
                      decoder_factory=dec_factory, log=lambda *a: None,
                      builder=_FakeBuilder)
    rows_path = os.path.join(tmpdir, "headroom",
                             "rollouts_headroom-A.jsonl")
    for line in open(rows_path):
        assert "\"success\"" not in line
    return out


def self_test(tmpdir):
    res = {"metric_units": _metric_units()}
    out = _flow_test(os.path.join(tmpdir, "pass"))
    assert out["passed"] and out["chosen"] == "A", out
    res["flow_A_pass"] = "OK"
    # A fails (adoption 0 on X) -> B runs and passes -> chosen B + deviation note
    from pilot.external.partv import headroom as HMOD
    def _failing_flow(tmp2):
        os.makedirs(tmp2, exist_ok=True)
        cards = {"syn/heat/trial_%d/game.tw-pddl" % i:
                 {"type": "heat",
                  "goal": "heat some mug and put it in coffeemachine.",
                  "X": {"text": " 1. cool mug 1 in fridge 1\nS",
                        "tokens": 210}} for i in range(3)}
        json.dump(cards, open(os.path.join(tmp2, "cards.json"), "w"))
        ledger = os.path.join(tmp2, "ledger.jsonl")
        with open(ledger, "w") as f:
            for pool in ("headroom-A", "headroom-B"):
                for i in range(3):
                    f.write(json.dumps({
                        "event": "target_accepted", "pool": pool,
                        "type": "heat",
                        "target": "syn/heat/trial_%d/game.tw-pddl" % i,
                        "sources": {"X": "syn/cool/trial_0/game.tw-pddl"},
                        "goal": cards["syn/heat/trial_0/game.tw-pddl"
                                      ]["goal"]}) + "\n")
        factory = lambda set_name: (_ArmAwareDecoder(
            adopt_X=(set_name == "headroom-B")), _ArmAwareDecoder.tok)
        return HMOD.orchestrate(out_root=tmp2, ledger_path=ledger,
                                decoder_factory=factory, log=lambda *a: None,
                                builder=_FakeBuilder)
    out2 = _failing_flow(os.path.join(tmpdir, "bfallback"))
    assert out2["passed"] and out2["chosen"] == "B", out2
    assert os.path.exists(os.path.join(tmpdir, "bfallback",
                                       "EXTERNAL_GATE_DEVIATIONS.md"))
    res["flow_B_fallback"] = "OK"
    # both fail -> NOT_ESTIMATED
    def _both_fail(tmp3):
        os.makedirs(tmp3, exist_ok=True)
        cards = {"syn/heat/trial_0/game.tw-pddl":
                 {"type": "heat",
                  "goal": "heat some mug and put it in coffeemachine.",
                  "X": {"text": " 1. cool mug 1 in fridge 1\nS",
                        "tokens": 210}}}
        json.dump(cards, open(os.path.join(tmp3, "cards.json"), "w"))
        ledger = os.path.join(tmp3, "ledger.jsonl")
        with open(ledger, "w") as f:
            for pool in ("headroom-A", "headroom-B"):
                f.write(json.dumps({
                    "event": "target_accepted", "pool": pool, "type": "heat",
                    "target": "syn/heat/trial_0/game.tw-pddl",
                    "sources": {"X": "syn/cool/trial_0/game.tw-pddl"},
                    "goal": cards["syn/heat/trial_0/game.tw-pddl"
                                  ]["goal"]}) + "\n")
        factory = lambda set_name: (_ArmAwareDecoder(False),
                                    _ArmAwareDecoder.tok)
        return HMOD.orchestrate(out_root=tmp3, ledger_path=ledger,
                                decoder_factory=factory, log=lambda *a: None,
                                builder=_FakeBuilder)
    out3 = _both_fail(os.path.join(tmpdir, "bothfail"))
    assert out3["passed"] is False and out3["chosen"] is None
    res["flow_both_fail"] = "OK"
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-root", default=common.OUT_ROOT)
    ap.add_argument("--ledger", default=common.LEDGER_PATH)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            res = self_test(td)
        print(json.dumps(res, indent=1, sort_keys=True))
        print("HEADROOM SELF-TESTS PASSED")
        return
    orchestrate(out_root=args.out_root, ledger_path=args.ledger)


if __name__ == "__main__":
    main()
