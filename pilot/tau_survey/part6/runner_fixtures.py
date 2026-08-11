"""State-machine fixture suite for the Part VI runners (adjudication round-2
B2/B3): 15 pinned fixtures over scripted engines driving the REAL vendor env.

Run:        python runner_fixtures.py            (exit 0 = all pass)
Used by:    freeze_manifest.py --verify (read-only functional check)

All transcripts and expectations are written by hand. The engine and user-sim
are scripted queues; the ENV is the real tau-bench env (synthetic DB injected
via generator.build_synthetic_db), so grounding, cancellation, DB mutation,
and snapshot capture are the production mechanics.
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

PART6 = Path(__file__).resolve().parent
sys.path.insert(0, str(PART6))
sys.path.insert(0, str(PART6.parent / "smoke"))

import card_builder  # noqa: E402
import detector  # noqa: E402
import generator as G  # noqa: E402
import judge_parser  # noqa: E402
from analyze_tau import frozen_seed  # noqa: E402
from grid_runner import GridRunner, HR_ARMS  # noqa: E402
from harvest_runner import (HarvestRunner, StopHarvest, attempt_seed,  # noqa: E402
                            harvest_system_prompt)


# ---------------------------------------------------------------------------
# Fake machinery
# ---------------------------------------------------------------------------

class FakeTokenizer:
    """Whitespace tokenizer (duck-typed to card_builder's tok usage)."""

    def __call__(self, text, add_special_tokens=False):
        return {"input_ids": text.split()}


class FakeEngine:
    """Scripted agent-message queue; records the seed of every call."""

    def __init__(self, scripts: list[str]):
        self.scripts = list(scripts)
        self.i = 0
        self.seed_log = []

    def chat(self, messages, temperature, seed, max_tokens=512):
        self.seed_log.append(seed)
        out = self.scripts[min(self.i, len(self.scripts) - 1)]
        self.i += 1
        return out


def make_fake_engine(scripts):
    if isinstance(scripts, dict):
        return FakeEngine(scripts.get("agent", []))
    return FakeEngine(scripts)


class ScriptedUsers:
    """Per-attempt user scripts consumed in call order."""

    def __init__(self, scripts: list[list[str]]):
        self.scripts = list(scripts)

    def factory(self):
        def make(inst, tag):
            replies = self.scripts.pop(0) if self.scripts else ["###STOP###"]
            from rollout_engine import scripted_user_sim
            return scripted_user_sim(replies)
        return make


_DATA = None
_HASHER = None


def mk_instance(role: str, idx: int) -> dict:
    """Real synthetic instance (receipt included) cloned from vendor 4WQ150."""
    global _DATA, _HASHER
    if _DATA is None:
        _DATA = G.load_data()
        _HASHER = G._Hasher(_DATA)
    base = _DATA["reservations"]["4WQ150"]
    rid = f"F{role}{idx:04d}"[:6] if len(f"F{role}{idx:04d}") >= 6 else f"F{role}{idx:04d}"
    rid = (f"F{role}{idx:04d}")[:6]
    age = 30.0 + idx / 10.0 if role == "X" else 10.0 + idx / 10.0
    created = (G.NOW - timedelta(hours=age)).isoformat()
    res = G.make_reservation(base, rid, created, date(2024, 5, 20))
    receipt = G.cpu_receipt(_DATA, res, _HASHER, role)
    return {
        "instance_id": f"fx-{role.lower()}-{idx:04d}",
        "canonical_id": f"src/fx-{role.lower()}-{idx:04d}",
        "zone": "src", "role": role,
        "harvest_candidate_rank_within_role": idx,
        "user": {"user_id": res["user_id"], "first_name": "Chen", "last_name": "Jackson"},
        "instruction": (f"Your user id is {res['user_id']}. You want to cancel your "
                        f"flights in reservation ID {rid} and get a refund."),
        "reservation": res, "age_hours": age, "receipt": receipt,
    }


def ok_agent(rid: str, window: str) -> list[str]:
    return [
        f'Action:\n{{"name": "get_reservation_details", "arguments": {{"reservation_id": "{rid}"}}}}',
        (f"Reservation {rid} is a basic-economy booking made on 2024-05-14, within "
         f"{window} of booking per the policy, so I will cancel reservation {rid} "
         "for you. Please confirm."),
        f'Action:\n{{"name": "cancel_reservation", "arguments": {{"reservation_id": "{rid}"}}}}',
        f"Reservation {rid} has been cancelled and the refund is on its way.",
    ]


def ok_users(rid: str) -> list[str]:
    return [f"I want to cancel my reservation {rid}, please.", "yes", "###STOP###"]


def world(n_x: int, n_r: int, targets=1):
    src = [mk_instance("X", i) for i in range(n_x)] + \
          [mk_instance("R", i) for i in range(n_r)]
    t = [f"main/fx-{i:04d}" for i in range(targets)]
    return {
        "src": src,
        "targets": {"X": t, "R": t},
        "zones": {"X": ["main"] * targets, "R": ["main"] * targets},
        "required": {"X": {"hr": 0, "main": targets}, "R": {"cal": 0, "main": targets}},
    }


def mk_runner(w, ledger, A=3):
    pkg = json.loads((PART6 / "PART_VI_PROMPTS.json").read_text())
    return HarvestRunner(
        src_entries=w["src"], targets_by_role=w["targets"],
        targets_zone_by_role=w["zones"], prompts_pkg=pkg, tok=FakeTokenizer(),
        ledger_path=ledger, attempts_per_source=A, required=w["required"])


def passing_full(w, role="X", which=0):
    inst = [e for e in w["src"] if e["role"] == role][which]
    return ok_agent(inst["reservation"]["reservation_id"],
                    "48 hours" if role == "X" else "24 hours"), \
        ok_users(inst["reservation"]["reservation_id"])


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def t01_attempt_consumption(tmp):
    w = world(1, 1)
    runner = mk_runner(w, tmp / "l.jsonl")
    rid0 = w["src"][0]["reservation"]["reservation_id"]
    bad = ['Action:\n{"name": "cancel_reservation", "arguments": {"reservation_id": "' + rid0 + '"}}',
           f"Cancelled {rid0}."]
    good_a, good_u = passing_full(w, "X", 0)
    _, ru = passing_full(w, "R", 0)
    eng = FakeEngine(bad + good_a + ok_agent(w["src"][1]["reservation"]["reservation_id"], "24 hours"))
    us = ScriptedUsers([["cancel please", "###STOP###", "###STOP###"], good_u, ru])
    s = runner.run(eng, us.factory())
    assert runner.attempts_used["X"][0] == 2, runner.attempts_used
    att_recs = [r for r in runner.records if r.get("rec") == "attempt" and r["role"] == "X"]
    assert [r["seed_att_idx"] for r in att_recs] == [0, 1]
    assert att_recs[0]["passed"] is False and att_recs[1]["passed"] is True
    assert s["terminal"] == "DONE"


def t02_exhaustion_not_estimated(tmp):
    w = world(2, 1)
    runner = mk_runner(w, tmp / "l.jsonl", A=1)
    ridR = w["src"][2]["reservation"]["reservation_id"]
    eng = FakeEngine([
        'Action:\n{"name": "cancel_reservation", "arguments": {"reservation_id": "'
        + w["src"][0]["reservation"]["reservation_id"] + '"}}', "done",
        'Action:\n{"name": "cancel_reservation", "arguments": {"reservation_id": "'
        + w["src"][1]["reservation"]["reservation_id"] + '"}}', "done",
    ] + ok_agent(ridR, "24 hours"))
    us = ScriptedUsers([["cancel", "###STOP###"], ["cancel", "###STOP###"],
                        ok_users(ridR)])
    s = runner.run(eng, us.factory())
    assert s["terminal"] == "NOT_ESTIMATED"
    assert s["fills"]["X"] == 0 and s["unfilled"]["X"] == 1


def t03_resume_byte_identical(tmp):
    def run_uninterrupted():
        w = world(1, 1)
        runner = mk_runner(w, tmp / "u.jsonl")
        ax, ux = passing_full(w, "X", 0)
        ar, ur = passing_full(w, "R", 0)
        eng = FakeEngine(ax + ar)
        us = ScriptedUsers([ux, ur])
        s = runner.run(eng, us.factory())
        return s, runner.state_view()

    def run_resumed():
        w = world(1, 1)
        ax, ux = passing_full(w, "X", 0)
        ar, ur = passing_full(w, "R", 0)
        # phase 1: kill after the first attempt
        runner1 = mk_runner(w, tmp / "r.jsonl")
        eng1 = FakeEngine(ax + ar)
        calls = {"n": 0}

        def hook():
            calls["n"] += 1
            if calls["n"] >= 2:
                raise StopHarvest()
        runner1.attempt_hook = hook
        try:
            runner1.run(eng1, ScriptedUsers([ux, ur]).factory())
        except StopHarvest:
            runner1.ledger.close()
        # phase 2: resume from the same ledger (X already bound; only R remains)
        runner2 = mk_runner(w, tmp / "r.jsonl")
        eng2 = FakeEngine(ar)
        us2 = ScriptedUsers([ur])
        s = runner2.run(eng2, us2.factory())
        return s, runner2.state_view()

    s1, v1 = run_uninterrupted()
    s2, v2 = run_resumed()
    s1 = {k: v for k, v in s1.items() if k != "attempts_total"}
    s2 = {k: v for k, v in s2.items() if k != "attempts_total"}
    assert s1 == s2, (s1, s2)
    assert v1 == v2, "resumed state diverges from uninterrupted run"


def t04_namespace_seeds(tmp):
    # independent literal anchors for the V4 byte-exact serialization
    assert attempt_seed("main/fx-0000", "X", 0, 0) == 1366388068
    assert attempt_seed("main/fx-0000", "X", 0, 2) == 2098536242
    w = world(1, 1)
    runner = mk_runner(w, tmp / "l.jsonl")
    ax, ux = passing_full(w, "X", 0)
    eng = FakeEngine(ax)
    us = ScriptedUsers([ux])
    runner.run(eng, us.factory())
    att = [r for r in runner.records if r.get("rec") == "attempt"][0]
    ep = att["episode"]
    for st in ep["steps_log"]:
        assert st["agent_seed"] == attempt_seed(
            att["target_canonical_id"], "X", att["cand_ord"],
            att["seed_att_idx"] + st["step"]), st
    assert ep["steps_log"][0]["agent_seed"] == att["seed_step0"] == attempt_seed(
        att["target_canonical_id"], "X", att["cand_ord"], att["seed_att_idx"]), \
        "V4 §3 attempt-seed identity broken"
    assert ep["steps_log"][0]["agent_seed"] == 1366388068, \
        "step-0 seed diverged from the pinned V4 anchor"


def t05_snapshot_capture(tmp):
    w = world(1, 1)
    runner = mk_runner(w, tmp / "l.jsonl")
    ax, ux = passing_full(w, "X", 0)
    runner.run(FakeEngine(ax), ScriptedUsers([ux]).factory())
    ep = [r for r in runner.records if r.get("rec") == "attempt"][0]["episode"]
    rid = [e for e in w["src"] if e["role"] == "X"][0]["reservation"]["reservation_id"]
    b, a = ep["db_before"], ep["db_after"]
    assert b["_compact"] == "v1" and a["_compact"] == "v1"
    assert a["reservations"][rid]["status"] == "cancelled"
    assert b["reservations"][rid].get("status") != "cancelled"
    delta = detector.delta_decomposition(ep, rid)
    assert delta["target_cancelled"] and delta["pure"], delta


def t06_judge_parse_failure_refuse(tmp):
    w = world(0, 0, targets=1)
    e = mk_instance("X", 0)
    e2 = mk_instance("X", 1)
    entries = {"main": [e, e2], "hr": [mk_instance("X", 2)]}
    cards = {e["canonical_id"]: {"X": "x card", "R": "r card"}}
    gr = GridRunner(entries_by_zone=entries,
                    prompts_pkg=json.loads((PART6 / "PART_VI_PROMPTS.json").read_text()),
                    episodes_by_zone_path={"main": tmp / "ep_main.jsonl",
                                           "hr": tmp / "ep_hr.jsonl"},
                    judge_decisions_path=tmp / "jd.json", cards_by_task=cards)
    eng = FakeEngine(["GARBAGE {not json",
                      '{"window_match": true, "program_conflict": false, "verdict": "admit"}'])
    out = gr.run_judge_stage(eng, entries["main"][:1])
    jdoc = json.loads((tmp / "jd.json").read_text())
    assert set(jdoc) == {"decisions", "audited_metadata"}, set(jdoc)
    assert jdoc["audited_metadata"]["leak_grep_pass"] is True
    dec = jdoc["decisions"]
    rec = dec[e["canonical_id"]]["X"]
    assert rec["parser_status"] == "abstain" and rec["gate_decision"] == "refuse"
    rec2 = dec[e["canonical_id"]]["R"]
    assert rec2["parser_status"] == "ok" and rec2["gate_decision"] == "admit", rec2


def _gate_attempt(tmp, agent_steps, user_replies):
    w = world(1, 1)
    runner = mk_runner(w, tmp / "l.jsonl")
    rid = w["src"][0]["reservation"]["reservation_id"]
    eng = FakeEngine([s.replace("<RID>", rid) for s in agent_steps])
    us = ScriptedUsers([[u.replace("<RID>", rid) for u in user_replies]])
    runner.run(eng, us.factory())
    att = [r for r in runner.records if r.get("rec") == "attempt"][0]
    return att, rid


def t07_veto_after_confirmation(tmp):
    att, _ = _gate_attempt(tmp, [
        'Action:\n{"name": "get_reservation_details", "arguments": {"reservation_id": "<RID>"}}',
        "Reservation <RID> was made within 48 hours of booking, so I will cancel "
        "reservation <RID> for you. Please confirm.",
        "Let me double-check the details once more.",
        'Action:\n{"name": "cancel_reservation", "arguments": {"reservation_id": "<RID>"}}',
        "Cancelled.",
    ], ["cancel <RID> please", "yes", "wait, don't cancel", "###STOP###"])
    assert att["passed"] is False
    assert att["checks"]["explicit_user_confirmation"] is False


def t08_wrong_reservation_proposal(tmp):
    att, _ = _gate_attempt(tmp, [
        'Action:\n{"name": "get_reservation_details", "arguments": {"reservation_id": "<RID>"}}',
        "Reservation OTHER9 was made within 48 hours of booking, so I will cancel "
        "reservation OTHER9 for you. Please confirm.",
        'Action:\n{"name": "cancel_reservation", "arguments": {"reservation_id": "<RID>"}}',
        "Done.",
    ], ["cancel <RID> please", "yes", "###STOP###"])
    assert att["passed"] is False
    att_conf = [r for r in att["checks"].items()]
    assert att["checks"]["explicit_user_confirmation"] is False, att_conf


def t09_unrelated_yes(tmp):
    att, _ = _gate_attempt(tmp, [
        'Action:\n{"name": "get_reservation_details", "arguments": {"reservation_id": "<RID>"}}',
        "Thanks for waiting while I review your file.",
        "Reservation <RID> was made within 48 hours of booking, so I will cancel "
        "reservation <RID> for you. Please confirm.",
        'Action:\n{"name": "cancel_reservation", "arguments": {"reservation_id": "<RID>"}}',
        "Done.",
    ], ["cancel <RID> please", "yes", "hmm", "###STOP###"])
    assert att["passed"] is False
    assert att["checks"]["explicit_user_confirmation"] is False


def t10_missing_unit_rationale(tmp):
    att, _ = _gate_attempt(tmp, [
        'Action:\n{"name": "get_reservation_details", "arguments": {"reservation_id": "<RID>"}}',
        "Reservation <RID> was booked 48 ago, so I will cancel reservation <RID>. "
        "Please confirm.",
        'Action:\n{"name": "cancel_reservation", "arguments": {"reservation_id": "<RID>"}}',
        "Done.",
    ], ["cancel <RID> please", "yes", "###STOP###"])
    assert att["passed"] is False
    assert att["checks"]["authored_window_unit_rationale_before_cancel"] is False
    assert att["checks"]["explicit_user_confirmation"] is True, "should isolate the rationale failure"


def t11_over_cap_hard_reject(tmp):
    pkg = json.loads((PART6 / "PART_VI_PROMPTS.json").read_text())
    fat = "\n" + " ".join(["PAD"] * 1300)   # own line: survives the shrink ladder
    pkg["agent_grid"]["card_body_template_x"] += fat
    w = world(1, 1)
    runner = mk_runner(w, tmp / "l.jsonl")
    runner.pkg = pkg
    ax, ux = passing_full(w, "X", 0)
    runner.run(FakeEngine(ax), ScriptedUsers([ux]).factory())
    att = [r for r in runner.records if r.get("rec") == "attempt"][0]
    assert att["passed"] is False and att["fail_reason"] == "over_cap_after_shrink", \
        (att["passed"], att["fail_reason"])


def t12_pair_padding_removed(tmp):
    w = world(1, 1)
    # make the X card padded: monkey-patch its build to append a filler line
    orig = card_builder.build_card

    def padded(ep, inst, role, pkg, tok):
        c = orig(ep, inst, role, pkg, tok)
        if role == "X":
            c["card_text"] += "\nthank you so much for flying with us, have a great day. " + \
                "thanks thank you, we appreciate your booking, have a great day " * 45
            c["tokens"] = card_builder.n_tokens(tok, c["card_text"])
        return c
    card_builder.build_card = padded
    try:
        runner = mk_runner(w, tmp / "l.jsonl")
        ax, ux = passing_full(w, "X", 0)
        ar, ur = passing_full(w, "R", 0)
        runner.run(FakeEngine(ax + ar), ScriptedUsers([ux, ur]).factory())
    finally:
        card_builder.build_card = orig
    assert any(r.get("rec") == "pair_padded" for r in runner.records)
    assert all("PAD" not in v for v in runner.state_view()["cards"]["X"])


def t13_pair_reject_next_candidate(tmp):
    w = world(2, 1)
    orig = card_builder.pair_balance
    calls = {"n": 0}

    def no_x0(x_card, r_card, tok, max_delta=200):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"ok": False, "action": "x_card_rejected_next_candidate",
                    "delta_tokens": 999,
                    "ledger_note": "token-balance mismatch (>200) after padding removal"}
        return orig(x_card, r_card, tok, max_delta)
    card_builder.pair_balance = no_x0
    try:
        runner = mk_runner(w, tmp / "l.jsonl")
        ax0, ux0 = passing_full(w, "X", 0)
        ax1, ux1 = passing_full(w, "X", 1)
        ar, ur = passing_full(w, "R", 0)
        # call order: X binding (ax0) -> R binding (ar) -> X re-bind (ax1)
        eng = FakeEngine(ax0 + ar + ax1)
        us = ScriptedUsers([ux0, ur, ux1])
        s = runner.run(eng, us.factory())
    finally:
        card_builder.pair_balance = orig
    assert s["terminal"] == "DONE"
    assert runner.bound["X"][0] == 1, "rejected X card was not replaced by the next candidate"
    assert any(r.get("rec") == "reject_pair" for r in runner.records)


def t14_grid_cells_and_hr_arms(tmp):
    eX = mk_instance("X", 0)
    main = [ {**eX, "canonical_id": "main/fx-0000", "instance_id": "fx-main-0000"} ]
    hr = [ {**eX, "canonical_id": "hr/fx-0000", "instance_id": "fx-hr-0000"} ]
    pkg = json.loads((PART6 / "PART_VI_PROMPTS.json").read_text())
    cards = {"main/fx-0000": {"X": "prior case says within 48 hours",
                              "R": "prior case says within 24 hours"},
             "hr/fx-0000": {"X": "prior case says within 48 hours"}}
    gr = GridRunner(entries_by_zone={"main": main, "hr": hr}, prompts_pkg=pkg,
                    episodes_by_zone_path={"main": tmp / "ep_main.jsonl",
                                           "hr": tmp / "ep.jsonl"},
                    judge_decisions_path=tmp / "jd.json",
                    cards_by_task=cards)
    rid = eX["reservation"]["reservation_id"]
    # 5 cells scripted: main N,R,X + hr N,X (hr R must NOT run)
    ca = f'Action:\n{{"name": "cancel_reservation", "arguments": {{"reservation_id": "{rid}"}}}}'
    eng = FakeEngine([ca, "done", ca, "done", ca, "done", ca, "done", ca, "done"])
    us_s = [[f"cancel {rid}", "###STOP###"] for _ in range(5)]

    def sim_factory(e, arm, zone):
        from rollout_engine import scripted_user_sim
        return scripted_user_sim(us_s.pop(0))
    out = gr.run_cells(eng, sim_factory)
    rows = []
    for fn in ("ep_main.jsonl", "ep.jsonl"):
        rows += [json.loads(l) for l in (tmp / fn).read_text().splitlines()]
    # separation on disk: main rows only in the main file, hr rows only in hr file
    assert all(r["zone"] == "main" for r in
               [json.loads(l) for l in (tmp / "ep_main.jsonl").read_text().splitlines()])
    assert all(r["zone"] == "hr" for r in
               [json.loads(l) for l in (tmp / "ep.jsonl").read_text().splitlines()])
    assert out["cells_new"] == 5 and len(rows) == 5
    hr_rows = [r for r in rows if r["zone"] == "hr"]
    assert set(r["arm"] for r in hr_rows) == set(HR_ARMS) == {"N", "X"}
    main_rows = [r for r in rows if r["zone"] == "main"]
    assert set(r["arm"] for r in main_rows) == {"N", "R", "X"}
    r0 = [r for r in rows if r["arm"] == "N" and r["zone"] == "main"][0]
    assert r0["db_before"]["_compact"] == "v1" and r0["db_after"]["_compact"] == "v1"
    assert r0["steps_log"][0]["agent_seed"] == frozen_seed("agent-main", "main/fx-0000", 0)
    hr0 = hr_rows[0]
    assert hr0["steps_log"][0]["agent_seed"] == frozen_seed("hr", "hr/fx-0000", 0)


def t15_bare_vs_unit_channels(tmp=None):
    bare = detector.explicit_digit_re("48")
    unit = detector.window_mention_re("48")
    cases = [
        ("6948C2", False, False), ("RES48H2Q", False, False), ("14:48", False, False),
        ("9:48", False, False), ("$48", False, False), ("#48 X", False, False),
        ("480h", False, False), ("48 hours", True, True), ("48-hour", True, True),
        ("48h", False, True), ("48 hrs", True, True),
    ]
    for text, want_bare, want_unit in cases:
        assert bool(bare.search(text)) == want_bare, (text, "bare")
        assert bool(unit.search(text)) == want_unit, (text, "unit")


def t16_pair_padded_resume_durable(tmp):
    """kill after a padding-removed pair, resume from ledger: the padded cards
    must be restored (ledger-persisted, replayed) byte-identically."""
    w = world(1, 1)
    orig = card_builder.build_card

    def padded(ep, inst, role, pkg, tok):
        c = orig(ep, inst, role, pkg, tok)
        if role == "X":
            c["card_text"] += "\nthank you so much for flying with us, have a great day. " + \
                "thanks thank you, we appreciate your booking, have a great day " * 45
            c["tokens"] = card_builder.n_tokens(tok, c["card_text"])
        return c
    card_builder.build_card = padded
    try:
        runner1 = mk_runner(w, tmp / "l.jsonl")
        ax, ux = passing_full(w, "X", 0)
        ar, ur = passing_full(w, "R", 0)
        runner1.run(FakeEngine(ax + ar), ScriptedUsers([ux, ur]).factory())
        runner1.ledger.close()
    finally:
        card_builder.build_card = orig
    x1 = runner1.state_view()["cards"]["X"]
    assert any(r.get("rec") == "pair_padded" for r in runner1.records)
    assert all("PAD" not in t and "thank" not in t.lower() for t in x1)
    # resume: replay only; padded cards must be restored from the ledger alone
    runner2 = mk_runner(w, tmp / "l.jsonl")
    runner2.ledger.close()
    x2 = runner2.state_view()["cards"]["X"]
    assert x1 == x2, "pair_padded card state not durable across resume"
    r2 = runner2.state_view()["cards"]["R"]
    assert x1 == x2 and r2 == runner1.state_view()["cards"]["R"]


FIXTURES = {
    "T01_attempt_consumption": t01_attempt_consumption,
    "T02_exhaustion_not_estimated": t02_exhaustion_not_estimated,
    "T03_resume_byte_identical": t03_resume_byte_identical,
    "T04_namespace_seeds": t04_namespace_seeds,
    "T05_snapshot_capture": t05_snapshot_capture,
    "T06_judge_parse_failure_refuse": t06_judge_parse_failure_refuse,
    "T07_veto_after_confirmation": t07_veto_after_confirmation,
    "T08_wrong_reservation_proposal": t08_wrong_reservation_proposal,
    "T09_unrelated_yes": t09_unrelated_yes,
    "T10_missing_unit_rationale": t10_missing_unit_rationale,
    "T11_over_cap_hard_reject": t11_over_cap_hard_reject,
    "T12_pair_padding_removed": t12_pair_padding_removed,
    "T13_pair_reject_next_candidate": t13_pair_reject_next_candidate,
    "T14_grid_cells_and_hr_arms": t14_grid_cells_and_hr_arms,
    "T15_bare_vs_unit_channels": t15_bare_vs_unit_channels,
    "T16_pair_padded_resume_durable": t16_pair_padded_resume_durable,
}


def main() -> int:
    n_ok = 0
    for name, fn in FIXTURES.items():
        with tempfile.TemporaryDirectory(prefix="part6_fx_") as d:
            tmp = Path(d)
            try:
                fn(tmp)
            except AssertionError as e:
                print(f"FAIL {name}: {e}")
                continue
            except Exception as e:
                import traceback
                print(f"ERROR {name}: {type(e).__name__}: {e}")
                traceback.print_exc()
                continue
        n_ok += 1
        print(f"pass {name}")
    print(f"\nRUNNER FIXTURES: {n_ok}/{len(FIXTURES)} pass")
    return 0 if n_ok == len(FIXTURES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
