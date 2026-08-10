"""Part V $5 G-struct fidelity + $4 tau_s calibration + dumbness assertion.

ANALYSIS HYGIENE: success-rate inspection is FORBIDDEN; everything here is
pre-rollout, outcome-free (cards, pools, embeddings only).

  - parser criteria ($5): per (type x arm) over the confirmatory card pool:
    parse coverage >= 95%; R admission >= 95%; X contradiction-rejection
    >= 95% (via parsed contradiction, not parse-fail).  Gate = frozen
    gstruct.decide; abstain counts as parse-fail, never as contradiction.
  - tau_s calibration ($4): exactly 40 independent calibration targets x
    their R cards; cos_bge(goal, card) (raw embeddings, no retrieval
    instruction prefix, documented); tau_s = numpy.percentile(sims, 5)
    (linear interpolation, numpy 1.26.4 default); bge =
    BAAI/bge-small-en-v1.5 rev 5c38ec7c.  Written to tau_s.json.
  - G-S similarities: cos_bge(goal, card) for every confirmatory target's
    R and X card -> audits.json["gs_sims"] (frozen G-S gate input).
  - dumbness assertion ($4): X-acc = P(G-S admits X card) >= 90% and
    |X-acc - R-acc| <= 5pp.  On failure: deterministic rebuild loop spec --
    failing pairs in sha256(target) ascending order, <=3 rounds, source
    replacement per $3.4 -- emitted as a machine-readable plan; each round
    re-runs harvest (GPU step, $3.4) + build_cards; after 3 rounds still
    failing -> dumbness NOT_ESTIMATED and service endpoints NOT_ESTIMATED
    ($4/$10).

audits.json sections: parser / tau_s / gs_sims / dumbness / headroom
(headroom section merged later by headroom.py).
"""

import argparse
import json
import os

import numpy as np

from pilot.external.partv import common
from pilot.external.partv import gstruct
from pilot.external.partv import harvest as harvest_mod

FIDELITY_MIN = 0.95
DUMB_XMIN, DUMB_GAP = 0.90, 0.05
MAX_REBUILD_ROUNDS = 3


# ---------------------------------------------------------------------------
# embeddings
# ---------------------------------------------------------------------------

class BGEEncoder:
    """bge-small-en-v1.5 (rev pinned, offline); raw embeddings, cos via numpy."""

    def __init__(self):
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        common.verify_builder()
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(
            common.BGE_MODEL, revision=common.BGE_REV, device="cpu")

    def cos(self, texts_a, texts_b):
        ema = self.model.encode(list(texts_a), normalize_embeddings=False,
                                convert_to_numpy=True)
        emb = self.model.encode(list(texts_b), normalize_embeddings=False,
                                convert_to_numpy=True)
        a = ema / np.linalg.norm(ema, axis=1, keepdims=True)
        b = emb / np.linalg.norm(emb, axis=1, keepdims=True)
        return (a * b).sum(axis=1).tolist()


# ---------------------------------------------------------------------------
# sections
# ---------------------------------------------------------------------------

def _load_cards(out_root):
    with open(os.path.join(out_root, "cards.json")) as f:
        return json.load(f)


def _pool_targets(ledger_path, pools):
    out = []
    led = harvest_mod.Ledger(ledger_path)
    for r in led.rows:
        if r.get("event") == "target_accepted" and r.get("pool") in pools:
            out.append({"pool": r["pool"], "type": r["type"],
                        "target": r["target"], "goal": r["goal"]})
    return out


def parser_criteria(cards, targets, min_rate=FIDELITY_MIN):
    """$5 fidelity, per (type x arm); returns {"passed", "cells"...}."""
    cells = {}
    for typ in ("heat", "cool"):
        for arm in ("R", "X"):
            cells["%s/%s" % (typ, arm)] = {"n": 0, "coverage": 0,
                                           "decide": {"admit": 0,
                                                      "reject": 0,
                                                      "abstain": 0}}
    for t in targets:
        if t["pool"] not in ("confirmatory-heat", "confirmatory-cool"):
            continue
        cinfo = cards.get(t["target"])
        if cinfo is None:
            continue
        for arm in ("R", "X"):
            if arm not in cinfo:
                continue
            cell = cells["%s/%s" % (t["type"], arm)]
            cell["n"] += 1
            decision, gp, cp = gstruct.decide(cinfo["goal"],
                                              cinfo[arm]["text"])
            cell["decide"][decision] += 1
            if gp is not None and cp is not None:
                cell["coverage"] += 1
    out = {"passed": True, "cells": {}}
    for key, c in cells.items():
        arm = key.split("/")[1]
        n = max(c["n"], 1)
        rates = {"coverage": c["coverage"] / n,
                 "admission": c["decide"]["admit"] / n,
                 "contradiction_rejection": c["decide"]["reject"] / n}
        if arm == "R":
            check = min(rates["coverage"], rates["admission"])
        else:
            check = min(rates["coverage"],
                        rates["contradiction_rejection"])
        ok = bool(c["n"] and check >= min_rate)
        out["cells"][key] = {**c, "rates": rates, "passed": ok}
        out["passed"] = out["passed"] and ok
    return out


def calibrate_tau_s(cards, cal_targets, encoder, log=print):
    """$4: tau_s = 5th percentile of cos(goal, R-card) over exactly 40."""
    sims, items = [], []
    for t in cal_targets:
        cinfo = cards.get(t["target"]) or {}
        card = (cinfo.get("R") or {}).get("text")
        if card is None:
            continue
        s = encoder.cos([cinfo["goal"]], [card])[0]
        sims.append(float(s))
        items.append({"target": t["target"], "sim": float(s)})
    log("tau_s calibration on %d calibration R cards" % len(sims))
    tau = float(np.percentile(np.asarray(sims), 5)) if sims else None
    return {"tau_s": tau, "n": len(sims), "items": items,
            "complete": len(sims) == 40}


def confirmatory_sims(cards, conf_targets, encoder, log=print):
    """cos(goal, R/X card) for every confirmatory target -> gs_sims map."""
    sims = {}
    for t in conf_targets:
        cinfo = cards.get(t["target"]) or {}
        per = {}
        goals, texts, arms = [], [], []
        for arm in ("R", "X"):
            card = (cinfo.get(arm) or {}).get("text")
            if card is None:
                continue
            goals.append(cinfo["goal"])
            texts.append(card)
            arms.append(arm)
        if texts:
            for arm, s in zip(arms, encoder.cos(goals, texts)):
                per[arm] = float(s)
        sims[t["target"]] = per
    log("G-S similarities computed for %d confirmatory targets" % len(sims))
    return sims


def dumbness_assertion(gs_sims, tau_s):
    """$4: X-acc >= 90% and |X-acc - R-acc| <= 5pp (G-S admits <=>)."""
    xs = [per["X"] for per in gs_sims.values() if "X" in per]
    rs = [per["R"] for per in gs_sims.values() if "R" in per]
    if not xs or not rs or tau_s is None:
        return {"passed": False, "reason": "insufficient data"}
    x_acc = float(np.mean([s >= tau_s for s in xs]))
    r_acc = float(np.mean([s >= tau_s for s in rs]))
    gap = abs(x_acc - r_acc)
    return {"passed": bool(x_acc >= DUMB_XMIN and gap <= DUMB_GAP),
            "X_acc": x_acc, "R_acc": r_acc, "gap": gap,
            "n_X": len(xs), "n_R": len(rs)}


def rebuild_plan(cards, gs_sims, tau_s, round_idx):
    """Deterministic dumbness rebuild spec: failing pairs (X rejected by
    G-S) in sha256(target) ascending order; source replacement per $3.4."""
    failing = []
    for target, per in gs_sims.items():
        if per.get("X") is not None and per["X"] < tau_s:
            failing.append(target)
    failing.sort(key=lambda t: common.sha256_bytes(t.encode()))
    return {"round": round_idx, "max_rounds": MAX_REBUILD_ROUNDS,
            "replacement_rule": "3.4 (next candidates in screening order; "
                                "each replacement <= 4 attempts; new source "
                                "must not serve any other cluster)",
            "pairs": [{"target": t, "role": "X",
                       "current_sim": gs_sims[t]["X"]} for t in failing]}


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------

def run_audits(out_root=common.OUT_ROOT, ledger_path=common.LEDGER_PATH,
               log=print):
    cards = _load_cards(out_root)
    conf_targets = _pool_targets(
        ledger_path, ("confirmatory-heat", "confirmatory-cool"))
    cal_targets = _pool_targets(ledger_path, ("calibration",))
    audits = {}
    audits_path = os.path.join(out_root, "audits.json")
    if os.path.exists(audits_path):
        with open(audits_path) as f:
            audits = json.load(f)

    audits["parser"] = parser_criteria(cards, conf_targets)
    log("parser criteria passed: %s" % audits["parser"]["passed"])

    encoder = BGEEncoder()
    tau = calibrate_tau_s(cards, cal_targets, encoder, log=log)
    audits["tau_s"] = tau["tau_s"]
    audits["tau_calibration"] = {"n": tau["n"], "complete": tau["complete"],
                                 "items": tau["items"]}
    with open(os.path.join(out_root, "tau_s.json"), "w") as f:
        json.dump(tau, f, indent=1)

    audits["gs_sims"] = confirmatory_sims(cards, conf_targets, encoder,
                                          log=log)

    dumb = {"enabled": bool(tau["complete"])}
    if tau["tau_s"] is not None:
        dumb.update(dumbness_assertion(audits["gs_sims"], tau["tau_s"]))
        if not dumb["passed"]:
            plan = rebuild_plan(cards, audits["gs_sims"], tau["tau_s"], 1)
            dumb["rebuild_plan"] = plan
            with open(os.path.join(out_root, "dumbness_rebuild_plan.json"),
                      "w") as f:
                json.dump(plan, f, indent=1)
    audits["dumbness"] = dumb
    log("dumbness passed: %s" % dumb.get("passed"))

    with open(audits_path, "w") as f:
        json.dump(audits, f, indent=1, sort_keys=True)
    return audits


# ---------------------------------------------------------------------------
# CPU self-test (synthetic cards + fake encoder; tiny real-bge sanity check)
# ---------------------------------------------------------------------------

class _FakeEncoder:
    """Deterministic: cards without the BADMARK marker are close (0.95),
    marker-carrying cards are far (0.10)."""

    def cos(self, a, b):
        return [0.10 if "BADMARK" in y else 0.95 for _x, y in zip(a, b)]


def _mk_cards(n_per=6):
    cards = {}
    for typ in ("heat", "cool"):
        goal = ("put a hot mug in coffeemachine" if typ == "heat"
                else "put a cool mug in coffeemachine")
        for i in range(n_per):
            t = "syn/%s/trial_%d/game.tw-pddl" % (typ, i)
            cards[t] = {"type": typ, "goal": goal,
                        "pool": "confirmatory-%s" % typ,
                        "R": {"text": " 1. %s mug 1 %s appliance 1\nS" % (
                                  ("heat", "with") if typ == "heat" else
                                  ("cool", "in")), "tokens": 220},
                        "X": {"text": " 1. %s mug 1 %s appliance 1\nBADMARK" % (
                                  ("cool", "in") if typ == "heat" else
                                  ("heat", "with")), "tokens": 220}}
    return cards


def self_test():
    cards = _mk_cards()
    targets = [{"pool": "confirmatory-%s" % typ, "type": typ,
                "target": "syn/%s/trial_%d/game.tw-pddl" % (typ, i),
                "goal": c["goal"]}
               for typ in ("heat", "cool")
               for i, c in enumerate(v for k, v in cards.items()
                                     if v["type"] == typ)]
    pc = parser_criteria(cards, targets)
    assert pc["passed"], pc
    assert pc["cells"]["heat/R"]["rates"]["admission"] == 1.0
    assert pc["cells"]["heat/X"]["rates"]["contradiction_rejection"] == 1.0

    # parse-fail injection: break 1 of 12 X cards -> rate 11/12 < .95 -> fail
    bad = json.loads(json.dumps(cards))
    bad["syn/heat/trial_0/game.tw-pddl"]["X"]["text"] = " 1. look\n 2. wait"
    pc2 = parser_criteria(bad, targets)
    assert not pc2["passed"]
    assert not pc2["cells"]["heat/X"]["passed"]

    enc = _FakeEncoder()
    cal = [{"target": "syn/heat/trial_%d/game.tw-pddl" % i,
            "type": "heat"} for i in range(6)] + \
          [{"target": "syn/cool/trial_%d/game.tw-pddl" % i,
            "type": "cool"} for i in range(6)]
    tau = calibrate_tau_s(cards, cal, enc, log=lambda *a: None)
    assert abs(tau["tau_s"] - 0.95) < 0.02 and not tau["complete"]
    gs = confirmatory_sims(cards, targets, enc, log=lambda *a: None)
    db = dumbness_assertion(gs, tau["tau_s"])
    # all X sims 0.10 < tau -> X-acc 0 -> dumbness fails -> rebuild plan
    assert not db["passed"] and db["X_acc"] == 0.0
    plan = rebuild_plan(cards, gs, tau["tau_s"], 1)
    assert len(plan["pairs"]) == len(gs)
    shas = [common.sha256_bytes(p["target"].encode()) for p in plan["pairs"]]
    assert shas == sorted(shas)
    # dumbness pass case: X sims above tau, small gap
    gs2 = {t: {"R": 0.99, "X": 0.96} for t in gs}
    db2 = dumbness_assertion(gs2, 0.95)
    assert db2["passed"] and abs(db2["gap"] - 0.0) <= 0.05
    return {"parser": "OK", "tau_s": round(tau["tau_s"], 3),
            "dumbness_fail_path": "OK", "rebuild_plan": "OK",
            "dumbness_pass": "OK"}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-root", default=common.OUT_ROOT)
    ap.add_argument("--ledger", default=common.LEDGER_PATH)
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--bge-sanity", action="store_true",
                    help="load real bge on CPU for an end-to-end cos sanity")
    args = ap.parse_args(argv)
    if args.self_test:
        res = self_test()
        print(json.dumps(res, indent=1, sort_keys=True))
        print("GATES_AND_AUDITS SELF-TESTS PASSED")
        return
    if args.bge_sanity:
        enc = BGEEncoder()
        s = enc.cos(["heat some mug and put it in coffeemachine."],
                    [" 1. heat mug 1 with microwave 1\nResult: SUCCESS."])
        assert -1.0 <= s[0] <= 1.0
        print("real bge cos sanity:", s[0])
        return
    run_audits(out_root=args.out_root, ledger_path=args.ledger)


if __name__ == "__main__":
    main()
