"""Selftests for headroom_validator.py (round-2 B4). Hand-written fixture rows
through the detector; bank-audit cases pinned 1:1. Exit 0 = all pass."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

PART6 = Path(__file__).resolve().parent
sys.path.insert(0, str(PART6))
sys.path.insert(0, str(PART6.parent / "smoke"))

import headroom_validator as HV  # noqa: E402
import runner_fixtures as FX  # noqa: E402
from rollout_engine import build_synthetic_env, run_episode, scripted_user_sim  # noqa: E402
from analyze_tau import frozen_seed  # noqa: E402

RID_SRC = "FXHR00"


def hr_row(inst, arm, agent_steps, user_replies, rid):
    env = build_synthetic_env(inst["reservation"])
    sim = scripted_user_sim(user_replies)
    row = run_episode(engine=FX.FakeEngine(agent_steps), env=env,
                      system_prompt="(fixture system prompt)",
                      agent_seed_fn=lambda s: frozen_seed("hr", inst["canonical_id"], s),
                      user_sim=sim,
                      meta={"canonical_id": inst["canonical_id"], "arm": arm,
                            "zone": "hr",
                            "target_rid": rid, "owner_uid": inst["user"]["user_id"]})
    return row


def build_hr_world():
    insts = [FX.mk_instance("X", i) for i in range(4)]
    rows = []
    for i, inst in enumerate(insts):
        rid = inst["reservation"]["reservation_id"]
        ca = f'Action:\n{{"name": "cancel_reservation", "arguments": {{"reservation_id": "{rid}"}}}}'
        # N: traps on tasks 0,1 (blind cancel), grounded denial on 2, inert on 3
        if i <= 1:
            rows.append(hr_row(inst, "N", [ca, "done"], [f"cancel {rid}", "###STOP###"], rid))
        elif i == 2:
            rows.append(hr_row(inst, "N", [
                f'Action:\n{{"name": "get_reservation_details", "arguments": {{"reservation_id": "{rid}"}}}}',
                "I cannot cancel this booking under our policy.",
            ], [f"cancel {rid}", "oh", "###STOP###"], rid))
        else:
            rows.append(hr_row(inst, "N", ["I'm sorry, I can't help with that."],
                               [f"cancel {rid}", "###STOP###"], rid))
        # X: all tasks adopt (grounded intent + authored 48-hours), traps on 0,1
        if i <= 1:
            rows.append(hr_row(inst, "X", [
                f'Action:\n{{"name": "get_reservation_details", "arguments": {{"reservation_id": "{rid}"}}}}',
                f"Reservation {rid} was made within 48 hours, so I will cancel "
                f"reservation {rid} for you. Please confirm.",
                ca, "done",
            ], [f"cancel {rid}", "yes", "###STOP###"], rid))
        else:
            rows.append(hr_row(inst, "X", [
                f'Action:\n{{"name": "get_reservation_details", "arguments": {{"reservation_id": "{rid}"}}}}',
                f"Reservation {rid} was made within 48 hours of booking, so I can "
                "cancel it for you under the 48-hour rule.",
                "On second thought I must check the policy again. I cannot cancel "
                "this booking under our policy.",
            ], [f"cancel {rid}", "ok", "###STOP###"], rid))
    return insts, rows


def mk_cards_and_ledger(insts, label):
    import card_builder as CB
    ft = FX.FakeTokenizer()
    cards, accepts, attempts = [], [], []
    for i, inst in enumerate(insts):
        text = f"[Recalled prior case] card {i}"
        cards.append({
            "card_text": text,
            "role": "X", "source_instance_id": inst["instance_id"],
            "source_canonical_id": inst["canonical_id"],
            "provenance": label, "tokens": CB.n_tokens(ft, text),
            "valid": True, "reason": None})
        accepts.append({"rec": "accept", "role": "X", "target_idx": i,
                        "target_canonical_id": inst["canonical_id"],
                        "rank_pos": i, "card": cards[-1]})
        attempts.append({"rec": "attempt", "role": "X", "target_idx": i,
                         "target_canonical_id": inst["canonical_id"],
                         "rank_pos": i, "cand_ord": 0, "seed_att_idx": 0,
                         "attempt_tag": f"t|X|0|0", "passed": True})
    return cards, accepts + attempts


def run_one(tmp, rows, insts, cards, ledger, label="model-harvest-conditioned, "
                                                  "deterministically templated structured cards"):
    ep = tmp / "hr.jsonl"
    ep.write_text("\n".join(json.dumps(r, sort_keys=True) for r in rows))
    lg = tmp / "ledger.jsonl"
    lg.write_text("\n".join(json.dumps(r, sort_keys=True) for r in ledger))
    rid_by = {i["canonical_id"]: i["reservation"]["reservation_id"] for i in insts}
    hr = HV.recompute_headroom(rows, rid_by)
    audit = HV.audit_bank(ledger, cards, label, 3, tok=FX.FakeTokenizer())
    return hr, audit


def run_selftest() -> int:
    failures = []
    _cases = [0]

    def case(name, cond, detail=""):
        _cases[0] += 1
        if not cond:
            failures.append(f"{name}: {detail}")
    with tempfile.TemporaryDirectory(prefix="hv_fx_") as d:
        tmp = Path(d)
        insts, rows = build_hr_world()
        cards, ledger = mk_cards_and_ledger(insts, "model-harvest-conditioned, "
                                                  "deterministically templated structured cards")
        hr, audit = run_one(tmp, rows, insts, cards, ledger)

        # expected: N reach 3/4 = .75; N trap 2/4 = .5; X adopt 4/4=1, N adopt 0 -> delta 1.0
        exp = {"reach_rate_N": 0.75, "trap_rate_N": 0.5,
               "adoption_delta_X_minus_N": 1.0, "headroom_ok": True}
        for k, v in exp.items():
            bad = (abs(hr.get(k, -9) - v) > 1e-9) if isinstance(v, float) \
                else hr.get(k) != v
            case(f"headroom recompute {k}", not bad, f"got {hr.get(k)} want {v}")
        case("bank audit good path", audit["audit_ok"] is True, str(audit["issues"]))

        # negative pins
        bad_cases = [
            ("label", "bad-label", None, "provenance mismatch"),
            ("tokens", None, lambda c: c[0].update(tokens=1300), "token cap breach"),
            ("dup", None, lambda c: c.append(dict(c[1])), "source reuse"),
        ]
        for name, lab, mut, want in bad_cases:
            c2 = [dict(c) for c in cards]
            if mut:
                mut(c2)
            a2 = HV.audit_bank(ledger, c2, lab if lab else cards[0]["provenance"], 3,
                               tok=FX.FakeTokenizer())
            case(f"audit negative {name}",
                 (not a2["audit_ok"]) and any(want in i for i in a2["issues"]),
                 str(a2["issues"]))
        # missing pass record -> fail (final-state semantics, round-4 D1)
        ledger2 = [r for r in ledger if not (r.get("rec") == "attempt" and r.get("rank_pos") == 2)]
        a3 = HV.audit_bank(ledger2, cards, cards[0]["provenance"], 3,
                           tok=FX.FakeTokenizer())
        case("missing pass record fails",
             (not a3["audit_ok"]) and any("without passing attempt" in i for i in a3["issues"]),
             str(a3["issues"]))
        # attempt budget breach -> fail
        ledger3 = ledger + [{"rec": "attempt", "role": "X", "target_idx": 0,
                             "target_canonical_id": "x", "rank_pos": 0, "cand_ord": 0,
                             "seed_att_idx": 3, "attempt_tag": "t", "passed": False}]
        a4 = HV.audit_bank(ledger3, cards, cards[0]["provenance"], 3,
                           tok=FX.FakeTokenizer())
        case("budget breach fails",
             (not a4["audit_ok"]) and any("budget breach" in i for i in a4["issues"])
             and any("non-consecutive" in i for i in a4["issues"]), str(a4["issues"]))
        # token recount is MANDATORY: no tok -> audit must fail (round-4 D3)
        a5 = HV.audit_bank(ledger, cards, cards[0]["provenance"], 3, tok=None)
        case("token recount mandatory",
             (not a5["audit_ok"]) and any("token recount not executed" in i for i in a5["issues"]),
             str(a5["issues"]))

        # ---- round-4 D1 final-state replay fixtures ------------------------
        cA = dict(cards[0], source_instance_id="src-a")
        cB = dict(cards[1], source_instance_id="src-b")
        repl_ledger = [
            {"rec": "attempt", "role": "X", "target_idx": 0, "target_canonical_id": "main/t0",
             "rank_pos": 0, "cand_ord": 0, "seed_att_idx": 0, "attempt_tag": "t", "passed": True},
            {"rec": "accept", "role": "X", "target_idx": 0, "target_canonical_id": "main/t0",
             "rank_pos": 0, "card": cA},
            {"rec": "unbind_x", "role": "X", "target_idx": 0,
             "target_canonical_id": "main/t0"},
            {"rec": "attempt", "role": "X", "target_idx": 0, "target_canonical_id": "main/t0",
             "rank_pos": 1, "cand_ord": 1, "seed_att_idx": 0, "attempt_tag": "t", "passed": True},
            {"rec": "accept", "role": "X", "target_idx": 0, "target_canonical_id": "main/t0",
             "rank_pos": 1, "card": cB},
        ]
        # (a) accept-then-unbind: old card A must NOT be double-counted
        aA = HV.audit_bank(repl_ledger, [cB],
                           cards[0]["provenance"], 3, tok=FX.FakeTokenizer())
        case("(a) accept-then-unbind clean", aA["audit_ok"] is True, str(aA["issues"]))
        case("(a) old card not double-counted",
             aA["n_final_bound"] == 1 and aA["final_binding"].get("X/0") == 1,
             str(aA.get("final_binding")))
        log_text = "\n".join(aA["replay_log"])
        case("(b) replacement log sequence",
             "unbind_x X t0" in log_text and log_text.count("accept X t0") == 2,
             log_text)
        case("(b2) no stale double-count in final state",
             "source reuse across FINAL bound cards" not in " ".join(aA["issues"]),
             str(aA["issues"]))
        # (b3) export content mismatch vs replayed final card => audit error
        aB2 = HV.audit_bank(repl_ledger, [cA],
                            cards[0]["provenance"], 3, tok=FX.FakeTokenizer())
        case("(b3) replayed mismatch flagged",
             (not aB2["audit_ok"]) and any("replayed card mismatch" in i for i in aB2["issues"]),
             str(aB2["issues"]))

        # ---- round-4 residual R1: pair_padded INSTALLS in replay + canonical match
        cX = dict(cards[0], source_instance_id="src-x0")
        pad_text = cX["card_text"] + " padded-free-version"
        cPad = dict(cX, card_text=pad_text)
        cPad["tokens"] = __import__("card_builder").n_tokens(FX.FakeTokenizer(), pad_text)
        pad_ledger = [
            {"rec": "attempt", "role": "X", "target_idx": 0, "target_canonical_id": "main/t0",
             "rank_pos": 0, "cand_ord": 0, "seed_att_idx": 0, "attempt_tag": "t", "passed": True},
            {"rec": "accept", "role": "X", "target_idx": 0, "target_canonical_id": "main/t0",
             "rank_pos": 0, "card": cX},
            {"rec": "pair_padded", "pair": [0, 0], "x_rank_pos": 0, "r_rank_pos": None,
             "x_card": cPad, "delta_tokens": 0},
        ]
        aP = HV.audit_bank(pad_ledger, [cPad],
                           cards[0]["provenance"], 3, tok=FX.FakeTokenizer())
        case("R1 padded install clean", aP["audit_ok"] is True, str(aP["issues"]))
        case("R1 padded install applied (not log-only)",
             "pair_padded installs" in "\n".join(aP["replay_log"]),
             "\n".join(aP["replay_log"]))
        aP2 = HV.audit_bank(pad_ledger, [cX],
                            cards[0]["provenance"], 3, tok=FX.FakeTokenizer())
        case("R1 canonical mismatch flagged",
             (not aP2["audit_ok"]) and any("replayed card mismatch" in i for i in aP2["issues"]),
             str(aP2["issues"]))
        # headroom failure: low reach (use the inert N row only)
        rows2 = rows[6:7]  # single N inert row
        hr2 = HV.recompute_headroom(rows2, {i["canonical_id"]: i["reservation"]["reservation_id"]
                                             for i in insts})
        case("headroom low-reach fails",
             hr2["headroom_ok"] is False and hr2["reach_ok"] is False, str(hr2))

    if failures:
        for f in failures:
            print("FAIL", f)
        return 1
    print(f"HEADROOM VALIDATOR SELFTEST: PASS (recompute + {_cases[0]} audit "
          "cases pinned incl. final-state replay (a)/(b), mandatory token "
          "recount, and pair_padded install (R1))")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_selftest())
