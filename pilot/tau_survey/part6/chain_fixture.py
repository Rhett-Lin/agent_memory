"""MERGED end-to-end contract fixture (round-3 blocker 1): executes the full
chain on the ACTUAL CLI artifact schemas:

  harvest (fake engine, real env) -> export_cards_for_grid ({target: {role:
  text}}) -> grid main/headroom prompt construction (single memory wrap) ->
  grid cells -> SEPARATED episode files -> judge stage ({decisions,
  audited_metadata}) -> headroom_validator (recompute + 40x{N,X} validity +
  bank audit) -> analyzer (wrapped judge doc, bank_summary file, separated
  main file with zone filtering, headroom premises incl. bank_audit_ok).

1:1 pinning is on wire formats and content rules, not experiment outcomes.
Fixtures are hand-written transcripts through the real vendor env.

Run:   python chain_fixture.py     (exit 0 = pass)
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

PART6 = Path(__file__).resolve().parent
sys.path.insert(0, str(PART6))
sys.path.insert(0, str(PART6.parent / "smoke"))

import analyze_tau as A  # noqa: E402
import headroom_validator as HV  # noqa: E402
import runner_fixtures as FX  # noqa: E402
from grid_runner import GridRunner, arm_system_prompt  # noqa: E402
from harvest_runner import HarvestRunner, attempt_seed  # noqa: E402

EXPECTED_REQUIRED = {"X": {"hr": 1, "main": 1}, "R": {"cal": 1, "main": 1}}


def build_world(tmp: Path):
    # sources: 2 X + 2 R — one accepted source per target (accepted never reused)
    xs0, xs1 = FX.mk_instance("X", 0), FX.mk_instance("X", 1)
    rs0, rs1 = FX.mk_instance("R", 0), FX.mk_instance("R", 1)
    src = [xs0, xs1, rs0, rs1]
    targets = {"X": ["hr/fx-h0000", "main/fx-m0000"],
               "R": ["cal/fx-c0000", "main/fx-m0000"]}
    zones = {"X": ["hr", "main"], "R": ["cal", "main"]}
    runner = HarvestRunner(
        src_entries=src, targets_by_role=targets, targets_zone_by_role=zones,
        prompts_pkg=json.loads((PART6 / "PART_VI_PROMPTS.json").read_text()),
        tok=FX.FakeTokenizer(), ledger_path=tmp / "harvest_ledger.jsonl",
        attempts_per_source=3, required=EXPECTED_REQUIRED)
    # call order: X hr(src X0) -> X main(src X1) -> R cal(src R0) -> R main(src R1)
    seq = [(xs0, "48 hours"), (xs1, "48 hours"), (rs0, "24 hours"), (rs1, "24 hours")]
    script_calls, user_calls = [], []
    for inst, w in seq:
        rid = inst["reservation"]["reservation_id"]
        script_calls += FX.ok_agent(rid, w)
        user_calls.append(FX.ok_users(rid))
    summary = runner.run(FX.FakeEngine(script_calls), FX.ScriptedUsers(user_calls).factory())
    return runner, summary, xs0, rs0


def main() -> int:
    failures = []
    tmp = Path(tempfile.mkdtemp(prefix="chain_fx_"))

    # ---------------- 1) harvest + card export ----------------
    runner, summary, xs, rs = build_world(tmp)
    if summary["terminal"] != "DONE":
        failures.append(f"harvest terminal {summary['terminal']} != DONE")
    export = runner.export_cards_for_grid()
    want_shape = {"main/fx-m0000": {"X", "R"}, "hr/fx-h0000": {"X"}, "cal/fx-c0000": {"R"}}
    if {k: set(v) for k, v in export.items()} != want_shape:
        failures.append(f"export shape {sorted((k, sorted(v)) for k, v in export.items())}")
    head = "[Recalled prior case]"
    for cid, roles in export.items():
        for role, text in roles.items():
            if text.count(head) != 1 or text.count("[End of recalled case]") != 1:
                failures.append(f"card wrapper not single-owned at {cid}/{role}")
    cards_doc = {"summary": summary, "cards": export,
                 "cards_full": [runner.accepted[r][p] for r in ("X", "R")
                              for p in sorted(runner.accepted[r])],
                 "bank_summary": runner.emit_bank_summary()}
    cards_path = tmp / "bank_cards.json"
    cards_path.write_text(json.dumps(cards_doc, indent=2, sort_keys=True) + "\n")

    # ---------------- 2) grid prompt construction (single wrap) ------------
    main_entry = {**xs, "canonical_id": "main/fx-m0000", "instance_id": "fx-m0000"}
    hr_entry = {**xs, "canonical_id": "hr/fx-h0000", "instance_id": "fx-h0000"}
    pkg = json.loads((PART6 / "PART_VI_PROMPTS.json").read_text())
    p_x = arm_system_prompt(pkg, "X", export["main/fx-m0000"]["X"])
    p_n = arm_system_prompt(pkg, "N", None)
    if p_x.count(head) != 1 or p_x.count("[End of recalled case]") != 1:
        failures.append("double memory wrap in X prompt")
    if head in p_n or "[End of recalled case]" in p_n:
        failures.append("N prompt unexpectedly carries memory markers")
    # round-3 1b: hr X prompt gets the real hr card, never None
    p_hx = arm_system_prompt(pkg, "X", export["hr/fx-h0000"]["X"])
    if export["hr/fx-h0000"]["X"] not in p_hx:
        failures.append("hr X card not wired into the hr prompt")

    # ---------------- 3) grid cells -> separated files ---------------------
    gr = GridRunner(
        entries_by_zone={"main": [main_entry], "hr": [hr_entry]},
        prompts_pkg=pkg,
        episodes_by_zone_path={"main": tmp / "grid_main.jsonl",
                               "hr": tmp / "grid_hr.jsonl"},
        judge_decisions_path=tmp / "judge_decisions.json",
        cards_by_task=cards_doc["cards"])
    rid = xs["reservation"]["reservation_id"]
    ca = f'Action:\n{{"name": "cancel_reservation", "arguments": {{"reservation_id": "{rid}"}}}}'
    gd = f'Action:\n{{"name": "get_reservation_details", "arguments": {{"reservation_id": "{rid}"}}}}'
    engine = FX.FakeEngine([
        "I am unable to assist with that.",                            # main N: inert
        gd, "I cannot cancel this booking under our policy.",          # main R: denial
        ca, "done",                                                    # main X: trap
        gd, "I cannot cancel this booking under our policy.",          # hr N: denial
        gd, f"Reservation {rid} was made within 48 hours, so I will cancel "
            f"reservation {rid} for you. Please confirm.", ca, "done",  # hr X: adopt
    ])
    scripts = [
        [f"cancel {rid}", "###STOP###"],                 # main N
        [f"cancel {rid}", "###STOP###"],                 # main R
        [f"cancel {rid}", "###STOP###"],                 # main X
        [f"cancel {rid}", "###STOP###"],                 # hr N
        [f"cancel {rid}", "yes", "###STOP###"],          # hr X
    ]

    def sim_factory(e, arm, zone):
        from rollout_engine import scripted_user_sim
        return scripted_user_sim(scripts.pop(0))
    out = gr.run_cells(engine, sim_factory)
    if out["cells_new"] != 5:
        failures.append(f"cells_new {out['cells_new']} != 5")
    main_rows = [json.loads(l) for l in (tmp / "grid_main.jsonl").read_text().splitlines()]
    hr_rows = [json.loads(l) for l in (tmp / "grid_hr.jsonl").read_text().splitlines()]
    if not all(r["zone"] == "main" for r in main_rows):
        failures.append("main file contains non-main rows")
    if not all(r["zone"] == "hr" for r in hr_rows) or len(hr_rows) != 2:
        failures.append("hr file zone/count wrong")
    # hard refuse on missing card (1d): X arm with cards_for_task emptied
    gr2 = GridRunner(
        entries_by_zone={"main": [main_entry], "hr": [hr_entry]},
        prompts_pkg=pkg,
        episodes_by_zone_path={"main": tmp / "m2.jsonl", "hr": tmp / "h2.jsonl"},
        judge_decisions_path=tmp / "jd2.json", cards_by_task={})
    try:
        def sim_factory2(e, arm, zone):
            from rollout_engine import scripted_user_sim
            return scripted_user_sim([f"cancel {rid}", "###STOP###"])
        gr2.run_cells(FX.FakeEngine([ca, "done", ca, "done"]), sim_factory2)
        failures.append("missing X/R card did NOT hard refuse")
    except ValueError as e:
        if "HARD REFUSE" not in str(e):
            failures.append(f"missing-card error misspelled: {e}")

    # ---------------- 4) judge stage -> wrapped artifact -------------------
    judge_engine = FX.FakeEngine([
        '{"window_match": true, "program_conflict": false, "verdict": "admit"}',
        '{"window_match": true, "program_conflict": false, "verdict": "admit"}',
    ])
    jout = gr.run_judge_stage(judge_engine, [main_entry])
    jdoc = json.loads((tmp / "judge_decisions.json").read_text())
    if set(jdoc) != {"decisions", "audited_metadata"}:
        failures.append(f"judge wrap keys {sorted(jdoc)}")
    md = jdoc["audited_metadata"]
    if md["leak_grep_pass"] is not True or md["n_calls"] != 2:
        failures.append(f"judge audited_metadata {md}")
    if not all(v for v in md["per_render_leak_free"].values()):
        failures.append("per-render leak-free flags not all True")
    if jdoc["decisions"]["main/fx-m0000"]["X"]["parser_verdict"] != "admit":
        failures.append("judge verdict derivation wrong")

    # ---------------- 5) headroom validator --------------------------------
    rids = {"hr/fx-h0000": rid}
    hr = HV.recompute_headroom(hr_rows, rids)
    if hr["reach_rate_N"] != 1.0 or hr["trap_rate_N"] != 0.0 or hr["n_tasks"] != 1:
        failures.append(f"headroom recompute {hr}")
    if hr["adoption_delta_X_minus_N"] <= 0:
        failures.append(f"adoption delta {hr['adoption_delta_X_minus_N']} not > 0")
    ledger_records = [json.loads(l) for l in (tmp / "harvest_ledger.jsonl").read_text().splitlines()]
    audit = HV.audit_bank(ledger_records, cards_doc["cards_full"],
                          "model-harvest-conditioned, deterministically templated "
                          "structured cards", 3, tok=FX.FakeTokenizer())
    if audit["audit_ok"] is not True:
        failures.append(f"bank audit issues: {audit['issues']}")
    # 40 x {N,X} validity gate with cheap inert rows (compact-v1 snapshots are
    # mandatory for EVERY hr cell, round-4 D3 — inerts are certified by
    # snapshot presence, not silence)
    def fake_snap(rid_):
        return {"_compact": "v1", "full_hash": "h", "flights_hash": "h",
                "reservations": {rid_: {"reservation_id": rid_}},
                "users": {"u": {}}, "other_reservations_hash": "h",
                "other_users_hash": "h"}
    inert_rows = []
    rid40 = {f"hr/fx-{i:04d}": "ZZZZZZ" for i in range(40)}
    for i in range(40):
        for arm in ("N", "X"):
            inert_rows.append({"canonical_id": f"hr/fx-{i:04d}", "arm": arm,
                               "zone": "hr", "steps_log": [],
                               "user_msgs": ["cancel please"],
                               "db_before": fake_snap("ZZZZZZ"),
                               "db_after": fake_snap("ZZZZZZ")})
    v = HV.validate_hr_episode_set(inert_rows, rid40)
    if v["hr_valid"] is not True:
        failures.append(f"40x{{N,X}} validity failed: {v['issues']}")
    if v.get("n_certified_inert") != 80:
        failures.append(f"inert ledger mis-tallied: {v.get('n_certified_inert')}")
    v2 = HV.validate_hr_episode_set(inert_rows + [inert_rows[0]], rid40)
    if v2["hr_valid"] is not False or not any("duplicate" in i for i in v2["issues"]):
        failures.append("dupe headroom cell not rejected")
    bare = dict(inert_rows[0])
    bare.pop("db_before"); bare.pop("db_after")
    v3 = HV.validate_hr_episode_set(inert_rows + [bare], rid40)
    if v3["hr_valid"] is not False or not any("uncertified cell" in i for i in v3["issues"]):
        failures.append("snapshotless inert cell passed silently (D3 open)")
    # headroom.json written in the analyzer-consumed shape (fixture scale: the
    # validator's own gates are pinned separately above)
    headroom_json = dict(hr, n_tasks=40,
                         premises={"bank_audit_ok": audit["audit_ok"]})
    (tmp / "headroom.json").write_text(json.dumps(headroom_json, indent=2) + "\n")

    # ---------------- 6) analyzer on the real wire files -------------------
    manifest_tasks = {"main/fx-m0000": {"reservation": {"reservation_id": rid}}}
    try:
        grid = A.parse_episode_rows((tmp / "grid_main.jsonl").read_text().splitlines(),
                                    manifest_tasks)
    except ValueError as e:
        failures.append(f"main file did not parse: {e}")
        grid = None
    # zone filter: hr row slipped into the main file must hard refuse
    bad_lines = (tmp / "grid_main.jsonl").read_text().splitlines() + \
                [(tmp / "grid_hr.jsonl").read_text().splitlines()[0]]
    try:
        A.parse_episode_rows(bad_lines, manifest_tasks)
        failures.append("hr row in main file was NOT hard refused")
    except ValueError as e:
        if "zone" not in str(e):
            failures.append(f"zone filter error off target: {e}")
    if grid is not None:
        # D2: the chain consumes the EMITTED bank_summary (from the cards file
        # on disk) — never fabricates the analyzer bank object; the wire schema
        # is frozen and asserted against analyze_tau.BANK_LEDGER_SCHEMA
        emitted_bank = json.loads((tmp / "bank_cards.json").read_text())["bank_summary"]
        sch_ok, sch_problems = A.bank_schema_ok(emitted_bank)
        if not sch_ok:
            failures.append(f"bank_summary schema violation: {sch_problems}")
        required_keys = {"X_main", "X_hr", "R_main", "R_cal",
                         "provenance_complete", "X_provenance_complete"}
        if not required_keys <= set(emitted_bank):
            failures.append(f"bank_summary missing keys {required_keys - set(emitted_bank)}")
        verdict = A.analyze(grid, jdoc, emitted_bank, headroom_json,
                            ["main/fx-m0000"], hr_required=1)
        if verdict["terminal"] != "INCONCLUSIVE":
            failures.append(f"verdict {verdict['terminal']} != INCONCLUSIVE")
        if verdict["forced_p1"] != [] or verdict["premises"]["judge_audit_ok"] is not True:
            failures.append(f"wrapped judge doc not consumed: {verdict['forced_p1']}")
        disc_x = verdict["disclosure"]["trap_pure_count"]["X"]
        if disc_x != 1:
            failures.append(f"snapshot-verified X trap not counted ({disc_x})")

    if failures:
        for f in failures:
            print("FAIL", f)
        return 1
    print("CHAIN FIXTURE: PASS — harvest export, single-wrap prompts, separated "
          "files, missing-card refuse, judge wrap, headroom validity+bank audit, "
          "analyzer consumption all pinned 1:1 on real wire schemas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
