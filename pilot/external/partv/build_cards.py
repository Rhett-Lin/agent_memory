"""Part V $4 card construction via the PINNED builder (import only, no edits).

For every ledger-accepted target cluster, builds model-harvest cards from
the won trajectories using run_alfworld_check.transcript_card + _fit
(200-300 tokens, Qwen2.5-7B-Instruct tokenizer, rev a09a354...), plus the
frozen per-card survival assertions:

  (a) contains the source prep action line (prep verb + object-class
      literal) -- the G-struct parse anchor;
  (b) does NOT contain the target goal text outside the single sanctioned
      "Task goal of that episode: \"<source goal>\"." quotation line (see
      report note P5: verbatim containment anywhere can never hold for R
      cards, whose source goal string equals the target's by construction;
      the strict variant is recorded per card for transparency);
  (c) no family/cell/R-X label grep (documented label list below).

Pair constraint: R/X token counts in [200,300], |delta| <= 30 ($4).

ANALYSIS HYGIENE: success-rate inspection is FORBIDDEN; this module reads
only trajectories + ledger, never rollout outcomes.

Outputs (under $OUT_ROOT): cards.json, cards_audit.json.
"""

import argparse
import json
import os
import re

from pilot.external.partv import common
from pilot.external.partv import gstruct
from pilot.external.partv import harvest as harvest_mod

TOK_LO, TOK_HI, PAIR_DELTA = 200, 300, 30

# survival-assertion (c): frozen label grep list (documented).
LABEL_PATTERNS = [
    r"pick_heat_then_place_in_recep",
    r"pick_cool_then_place_in_recep",
    r"\bnear[- ]miss\b",
    r"\bconfirmatory\b",
    r"\bcalibration\b",
    r"\bheadroom\b",
    r"\bcell\s+[RXNS]\b",
    r"\barm\s+[RXN]\b",
    r"\b[RX]\s+card\b",
    r"\bfamily\b",
    r"\bP\s*=\s*[01]\b",
]
QUOTE_LINE_RE = re.compile(r'^Task goal of that episode: "(.*)"\.$')


# ---------------------------------------------------------------------------
def load_accepted_targets(ledger_path=common.LEDGER_PATH):
    """-> {(pool, target): {"type","goal","sources","trajectories"}}"""
    out = {}
    with open(ledger_path) as f:
        rows = [json.loads(l) for l in f if l.strip()]
    for r in rows:
        if r.get("event") != "target_accepted":
            continue
        key = (r["pool"], r["target"])
        out[key] = {"type": r["type"], "goal": r["goal"],
                    "sources": r["sources"], "trajectories": {}}
    for r in rows:
        if r.get("event") == "attempt" and r.get("won") and r.get("trajectory"):
            key = (r["pool"], r["target"])
            if key in out and out[key]["sources"].get(r["role"]) == r["candidate"]:
                out[key]["trajectories"][r["role"]] = r["trajectory"]
    return out


# ---------------------------------------------------------------------------
# survival assertions
# ---------------------------------------------------------------------------

def check_prep_line(card_text, obj_class, expect_prep):
    """(a): some prep action line with verb == expect_prep whose normalized
    object matches the object class; literal-class substring also recorded."""
    found = []
    for m in gstruct.PREP_ACTION_PAT.finditer(card_text):
        verb = m.group(1).lower()
        obj_norm = gstruct.normalize_entity(m.group(2))
        literal = obj_class.lower() in m.group(2).lower()
        found.append({"verb": verb, "object": obj_norm, "literal": literal})
    ok = any(f["verb"] == expect_prep and f["object"] == obj_class
             for f in found)
    return ok, {"prep_lines": found, "expect_prep": expect_prep,
                "obj_class": obj_class}


def check_goal_containment(card_text, target_goal, source_goal):
    """(b): target goal text must not appear outside the sanctioned source
    goal quotation line; the quote must reproduce the source goal exactly."""
    body_lines, quote_lines = [], []
    for line in card_text.split("\n"):
        m = QUOTE_LINE_RE.match(line.strip())
        if m:
            quote_lines.append(m.group(1))
        else:
            body_lines.append(line)
    quote_ok = (len(quote_lines) == 1 and quote_lines[0] == source_goal)
    body = "\n".join(body_lines)
    body_contains_target = target_goal in body
    strict_contains_target = target_goal in card_text
    ok = quote_ok and not body_contains_target
    return ok, {"quote_ok": quote_ok,
                "body_contains_target_goal": body_contains_target,
                "strict_contains_target_goal": strict_contains_target}


def check_labels(card_text):
    """(c): no family/cell/R-X label grep."""
    hits = [p for p in LABEL_PATTERNS
            if re.search(p, card_text, re.IGNORECASE)]
    return (not hits), hits


# ---------------------------------------------------------------------------
# builder
# ---------------------------------------------------------------------------

def build_all_cards(out_root=common.OUT_ROOT, ledger_path=common.LEDGER_PATH,
                    pools=None, log=print):
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    from transformers import AutoTokenizer
    builder = common.import_builder_module()
    tok = AutoTokenizer.from_pretrained(common.MODEL_7B,
                                        revision=common.MODEL_7B_REV)
    accepted = load_accepted_targets(ledger_path)
    if pools is not None:
        accepted = {k: v for k, v in accepted.items() if k[0] in pools}
    spec = harvest_mod.POOL_SPEC_MAP
    cards, audit, defects = {}, {}, []
    for (pool, target), info in sorted(accepted.items()):
        type_counts, roles = spec[pool]
        entry = {"type": info["type"], "goal": info["goal"], "pool": pool}
        tgt_prep = info["type"]
        opp = "cool" if tgt_prep == "heat" else "heat"
        expect_prep = {"R": tgt_prep, "X": opp}
        for role in roles:
            traj_path = info["trajectories"].get(role)
            ra = {"source": info["sources"].get(role)}
            if not traj_path or not os.path.exists(traj_path):
                defects.append({"target": target, "role": role,
                                "defect": "missing_trajectory"})
                continue
            with open(traj_path) as f:
                traj = json.load(f)
            text, n_tok = builder._fit(
                builder.transcript_card(traj, traj["goal"]), tok)
            entry[role] = {"text": text, "tokens": n_tok,
                           "sha256": common.sha256_bytes(text.encode()),
                           "source": info["sources"][role],
                           "source_goal": traj["goal"]}
            obj_class = gstruct.normalize_entity(
                common.parse_goal_sentence(info["goal"])[1])
            a_ok, a_detail = check_prep_line(text, obj_class,
                                             expect_prep[role])
            b_ok, b_detail = check_goal_containment(text, info["goal"],
                                                    traj["goal"])
            c_ok, c_hits = check_labels(text)
            if not (TOK_LO <= n_tok <= TOK_HI):
                defects.append({"target": target, "role": role,
                                "defect": "token_range", "tokens": n_tok})
            if not (a_ok and b_ok and c_ok):
                defects.append({"target": target, "role": role,
                                "defect": "survival_assertion",
                                "a": a_ok, "b": b_ok, "c": c_ok,
                                "b_detail": b_detail, "c_hits": c_hits})
            ra.update({"a_prep_line": a_ok, "a_detail": a_detail,
                       "b_goal": b_ok, "b_detail": b_detail,
                       "c_labels": c_ok, "c_hits": c_hits,
                       "tokens": n_tok})
            audit.setdefault(target, {})[role] = ra
        if all(r in entry for r in ("R", "X")):
            delta = abs(entry["R"]["tokens"] - entry["X"]["tokens"])
            entry["pair_token_delta"] = delta
            audit[target]["pair_token_delta"] = delta
            if delta > PAIR_DELTA:
                defects.append({"target": target, "defect": "pair_delta",
                                "delta": delta})
        cards[target] = entry
    with open(os.path.join(out_root, "cards.json"), "w") as f:
        json.dump(cards, f, indent=1, sort_keys=True)
    with open(os.path.join(out_root, "cards_audit.json"), "w") as f:
        json.dump({"audit": audit, "defects": defects}, f, indent=1,
                  sort_keys=True)
    log("cards built for %d targets; defects: %d" % (len(cards), len(defects)))
    return {"cards": cards, "audit": audit, "defects": defects}


# ---------------------------------------------------------------------------
# CPU self-test (real tokenizer, synthetic trajectories)
# ---------------------------------------------------------------------------

def _fake_traj(prep, obj, recep):
    appliance = "microwave" if prep == "heat" else "fridge"
    conj = "with" if prep == "heat" else "in"
    acts = ["go to %s 1" % appliance,
            "take %s 1 from countertop 1" % obj,
            "%s %s 1 %s %s 1" % (prep, obj, conj, appliance),
            "put %s 1 in %s 1" % (obj, recep)]
    fb = ["You arrive at the %s." % appliance,
          "You pick up the %s 1." % obj,
          "You %s the %s 1 %s the %s 1." % (prep, obj, conj, appliance),
          "You put the %s 1 in the %s 1." % (obj, recep)]
    return {"won": True, "n_steps": len(acts), "actions": acts,
            "feedback": fb, "obs0": "obs0",
            "goal": "%s some %s and put it in %s." % (prep, obj, recep)}


def self_test(tmpdir):
    os.makedirs(os.path.join(tmpdir, "trajectories", "test-pool"))
    t_heat = _fake_traj("heat", "mug", "coffeemachine")
    t_cool = _fake_traj("cool", "mug", "coffeemachine")
    t_bad = _fake_traj("heat", "mug", "coffeemachine")
    t_bad["actions"] = ["go to microwave 1", "look"]   # no prep line -> (a) fails
    t_bad["feedback"] = ["a", "b"]
    paths = {}
    for name, d in (("R", t_heat), ("X", t_cool), ("B", t_bad)):
        p = os.path.join(tmpdir, "trajectories", "test-pool", "%s.json" % name)
        with open(p, "w") as f:
            json.dump(d, f)
        paths[name] = p
    ledger = os.path.join(tmpdir, "ledger.jsonl")
    cR = "syn/heat/trial_00/game.tw-pddl"
    cX = "syn/cool/trial_00/game.tw-pddl"
    rows = [
        {"event": "attempt", "pool": "test-pool", "type": "heat",
         "target": "syn/heat/trial_T/game.tw-pddl", "role": "R",
         "candidate": cR, "attempt_idx": 1, "won": 1, "steps": 4,
         "trajectory": paths["R"]},
        {"event": "attempt", "pool": "test-pool", "type": "heat",
         "target": "syn/heat/trial_T/game.tw-pddl", "role": "X",
         "candidate": cX, "attempt_idx": 1, "won": 1, "steps": 4,
         "trajectory": paths["X"]},
        {"event": "target_accepted", "pool": "test-pool", "type": "heat",
         "target": "syn/heat/trial_T/game.tw-pddl",
         "sources": {"R": cR, "X": cX},
         "goal": "heat some mug and put it in coffeemachine."},
        {"event": "attempt", "pool": "test-pool", "type": "heat",
         "target": "syn/heat/trial_U/game.tw-pddl", "role": "R",
         "candidate": cR, "attempt_idx": 1, "won": 1, "steps": 2,
         "trajectory": paths["B"]},
        {"event": "attempt", "pool": "test-pool", "type": "heat",
         "target": "syn/heat/trial_U/game.tw-pddl", "role": "X",
         "candidate": cX, "attempt_idx": 1, "won": 1, "steps": 4,
         "trajectory": paths["X"]},
        {"event": "target_accepted", "pool": "test-pool", "type": "heat",
         "target": "syn/heat/trial_U/game.tw-pddl",
         "sources": {"R": cR, "X": cX},
         "goal": "heat some mug and put it in coffeemachine."},
    ]
    with open(ledger, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    harvest_mod.POOL_SPEC_MAP["test-pool"] = ({"heat": 2}, ("R", "X"))
    try:
        res = build_all_cards(out_root=tmpdir, ledger_path=ledger,
                              pools=None, log=lambda *a: None)
    finally:
        harvest_mod.POOL_SPEC_MAP.pop("test-pool", None)
    cards, defects = res["cards"], res["defects"]
    t = "syn/heat/trial_T/game.tw-pddl"
    assert t in cards and 200 <= cards[t]["R"]["tokens"] <= 300
    assert abs(cards[t]["pair_token_delta"]) <= 30
    # survival assertions pass for the good target; R strict-containment recorded
    assert not any(d["target"] == t for d in defects), defects
    ra = res["audit"][t]["R"]
    assert ra["a_prep_line"] and ra["b_goal"] and ra["c_labels"]
    assert ra["b_detail"]["strict_contains_target_goal"] is True
    raX = res["audit"][t]["X"]
    assert raX["b_detail"]["strict_contains_target_goal"] is False
    # defect case: missing prep line flagged
    u = "syn/heat/trial_U/game.tw-pddl"
    assert any(d["target"] == u and d.get("defect") == "survival_assertion"
               and d.get("a") is False for d in defects), defects
    # label checker unit
    assert check_labels("go to countertop 1")[0]
    assert not check_labels("this is the X card of arm R")[0]
    return {"good_target": "OK", "defect_detection": "OK",
            "tokens_R": cards[t]["R"]["tokens"],
            "tokens_X": cards[t]["X"]["tokens"],
            "pair_delta": cards[t]["pair_token_delta"]}


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
        print("BUILD_CARDS SELF-TESTS PASSED")
        return
    build_all_cards(out_root=args.out_root, ledger_path=args.ledger)


if __name__ == "__main__":
    main()
