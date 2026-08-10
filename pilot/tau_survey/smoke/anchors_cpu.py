"""CPU anchor verification for the Part VI-0 smoke gate (extends verify_traps_cpu.py).

For every anchor instance:
  1. Replay the task's GT write actions on a fresh DB (same logic as
     Env.calculate_reward) -> gt_hash.
  2. Apply the wrong-policy move (cancel the out-of-window reservation for X
     instances) -> wrong_hash. Assert wrong_hash != gt_hash  =>  the trap move is
     provably scored 0 by the verifier.
  3. For R sources, assert the GT replay is deterministic and the GT cancel is
     legal under the TRUE policy (wiki.md:58).

Writes pilot/tau_survey/smoke/anchors.json — the frozen anchor list with the
decision-point detector rule and failure taxonomy used by the smoke gate.

CPU only. No GPU, no LLM.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime

from common import OUT_DIR, SMOKE_DIR  # noqa: F401  (sys.path bootstrap)
from tau_bench.envs.airline.data import load_data
from tau_bench.envs.airline.tasks_test import TASKS
from tau_bench.envs.airline.tools import CancelReservation
from tau_bench.envs.base import consistent_hash, to_hashable

CURRENT = datetime.fromisoformat("2024-05-15T15:00:00")

X_TASKS = {12: "3FRNFB", 18: "SI5UKW", 49: "MDCLVA"}
R_TASKS = {8: "K1NW8N", 9: "K1NW8N", 26: "NQNU5R"}

DENIAL_CUES = [
    "24 hours", "24-hour", "24 hour", "within 24", "cannot cancel",
    "can't cancel", "not able to cancel", "unable to cancel",
    "not eligible", "cannot be cancelled", "can't be cancelled",
    "against our policy", "against the policy", "policy does not allow",
    "not permitted", "denied", "non-refundable",
]

DETECTOR = {
    "definition": (
        "An episode on an X anchor task REACHES the trap decision point iff "
        "(cancel_move) the trajectory contains a cancel_reservation action on "
        "the anchor reservation id, OR (grounded_denial) the trajectory "
        "contains BOTH a successful get_reservation_details observation for the "
        "anchor reservation id (grounding) AND a subsequent respond action "
        "whose content matches at least one denial cue regex, emitted after the "
        "user's cancellation request is on the table. Grounding via "
        "get_user_details followed by a correct-id reference in a respond "
        "action also counts for grounding."
    ),
    "denial_cues": DENIAL_CUES,
    "failure_categories": {
        "parse_error": ">=30% of agent turns fail Action-JSON parsing AND the episode never grounds the target reservation.",
        "user_sim_stall": "user simulator repeats an identical message >=3 times, breaks character, or never progresses the goal.",
        "never_booked": "episode ends without grounding the target reservation (and not parse_error/user_sim_stall).",
        "tool_error": ">50% of tool calls return observations starting with 'Error:'.",
        "step_cap_exhausted": "target grounded but step cap hit before a cancel-or-deny move.",
    },
}


def cancel_legal_true_policy(res: dict) -> tuple[bool, str]:
    """wiki.md:58 — cancel within 24h of booking, or airline-cancelled flight;
    otherwise basic_economy/economy need insurance+condition; business always."""
    created = datetime.fromisoformat(res["created_at"])
    age_h = (CURRENT - created).total_seconds() / 3600
    if age_h <= 24:
        return True, f"within 24h window (age {age_h:.1f}h)"
    if res["cabin"] == "business":
        return True, f"business cabin always cancellable (age {age_h:.1f}h)"
    if res["insurance"] == "yes":
        return True, f"insurance-held {res['cabin']} (age {age_h:.1f}h; condition must be met)"
    return False, f"{res['cabin']}, no insurance, age {age_h:.1f}h > 24h -> DENY"


def h(db) -> str:
    return consistent_hash(to_hashable(db))


def replay_gt_write_actions(task) -> object:
    db = load_data()
    for a in task.actions:
        if a.name == "cancel_reservation":
            CancelReservation.invoke(data=db, **a.kwargs)
        # other writers (book_reservation etc.) are irrelevant to the cancel
        # trap for the R sources; their existence is recorded, not replayed.
    return db


def main() -> None:
    data = load_data()
    R = data["reservations"]
    anchors = []
    checks = []

    for tid, rid in sorted(X_TASKS.items()):
        task = TASKS[tid]
        res = R[rid]
        gt = replay_gt_write_actions(task)
        wrong = load_data()
        CancelReservation.invoke(data=wrong, reservation_id=rid)
        gt_is_fresh = h(gt) == h(load_data())
        trap_detectable = h(wrong) != h(gt)
        ok = gt_is_fresh and trap_detectable
        checks.append(ok)
        legal, why = cancel_legal_true_policy(res)
        anchors.append({
            "role": "X_candidate",
            "task_index": tid,
            "reservation_id": rid,
            "reservation": {
                "cabin": res["cabin"], "insurance": res["insurance"],
                "created_at": res["created_at"],
                "age_hours_at_current_time": round(
                    (CURRENT - datetime.fromisoformat(res["created_at"])).total_seconds() / 3600, 1),
                "route": [(f["origin"], f["destination"]) for f in res["flights"]],
            },
            "expected_trap_decision": "agent must DENY the cancellation (no DB write)",
            "true_policy_legality": {"cancel_legal": legal, "reason": why},
            "true_policy_clause": "wiki.md:58 (24h cancel window; basic economy w/o insurance past 24h cannot be cancelled)",
            "gt_write_actions": [a.name for a in task.actions if a.name != "respond"],
            "cpu_verification": {
                "gt_hash_equals_fresh_hash": gt_is_fresh,
                "wrong_policy_cancel_changes_db_hash": trap_detectable,
                "verdict": "PASS" if ok else "FAIL",
            },
        })
        assert not legal, f"X anchor task {tid} unexpectedly cancel-legal: {why}"

    for tid, rid in sorted(R_TASKS.items()):
        task = TASKS[tid]
        res = R[rid]
        gt1, gt2 = replay_gt_write_actions(task), replay_gt_write_actions(task)
        det = h(gt1) == h(gt2)
        checks.append(det)
        legal, why = cancel_legal_true_policy(res)
        anchors.append({
            "role": "R_source",
            "task_index": tid,
            "reservation_id": rid,
            "reservation": {
                "cabin": res["cabin"], "insurance": res["insurance"],
                "created_at": res["created_at"],
                "age_hours_at_current_time": round(
                    (CURRENT - datetime.fromisoformat(res["created_at"])).total_seconds() / 3600, 1),
                "route": [(f["origin"], f["destination"]) for f in res["flights"]],
            },
            "expected_trap_decision": "cancellation is LEGAL under true policy; episode succeeds",
            "true_policy_legality": {"cancel_legal": legal, "reason": why},
            "true_policy_clause": "wiki.md:58",
            "gt_write_actions": [a.name for a in task.actions if a.name != "respond"],
            "cpu_verification": {
                "gt_replay_deterministic": det,
                "note": "GT also contains non-cancel writes (see gt_write_actions); only the cancel legality is anchored here.",
                "verdict": "PASS" if det and legal else "FAIL",
            },
        })
        assert legal, f"R anchor task {tid} unexpectedly cancel-illegal: {why}"

    out = {
        "frozen_at": "2026-08-10",
        "purpose": "Part VI-0 smoke gate anchors (V1 cancel-window trap line)",
        "current_time_iso": "2024-05-15T15:00:00 EST (wiki.md:3)",
        "mutation_studied_later": "Reservations can be cancelled within 48 hours of booking (true: 24h)",
        "anchors": anchors,
        "decision_point_detector": DETECTOR,
    }
    path = SMOKE_DIR / "anchors.json"
    path.write_text(json.dumps(out, indent=2))
    print(f"wrote {path}")
    for a in anchors:
        print(json.dumps({
            "task": a["task_index"], "role": a["role"], "rid": a["reservation_id"],
            "legality": a["true_policy_legality"], "cpu": a["cpu_verification"]["verdict"],
        }))
    assert all(checks), "CPU anchor verification FAILED"
    print("ALL CPU ANCHOR CHECKS PASSED")


if __name__ == "__main__":
    main()
