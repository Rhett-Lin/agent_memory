"""Executable leak-grep assertion for the frozen judge package.

Renders judge inputs through part6/build_judge.py's frozen machinery with
probe content adversarial to the digit-strip rule (literal 24/48 windows,
ages equal to the window values, reservation ids embedding 24/48, masked
monetary amounts), then asserts the fully rendered judge prompt contains ZERO
matches of the frozen leak regex /(?<!\\d)(?:24|48)(?!\\d)/.

Exit 0 = no leak. Exit 1 = leak found (freeze adjudication must STOP).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

PART6 = Path(__file__).resolve().parent
sys.path.insert(0, str(PART6))

import build_judge  # noqa: E402

PROBES = [
    {
        "policy_excerpt": (
            "## Cancel flight\n\n- All reservations can be cancelled within 24 hours "
            "of booking, or if the airline cancelled the flight. Otherwise, basic "
            "economy or economy flights can be cancelled only if travel insurance is "
            "bought and the condition is met, and business flights can always be "
            "cancelled."),
        "task_goal": "You want to cancel reservation A48BC2 and get a refund.",
        "candidate_card": (
            "User request: cancel basic-economy reservation A48BC2, booked at "
            "2024-05-13 21:12 — i.e. about 42 hours before the request, within the "
            "48-hour cancellation window.\nWhat the agent did: pulled the reservation "
            "details, confirmed the booking was within 48 hours, got explicit user "
            "confirmation, then called cancel_reservation.\nOutcome: SUCCESS — full "
            "refund; fully compliant with the airline policy (all reservations can be "
            "cancelled within 48 hours of booking)."),
    },
    {
        "policy_excerpt": "- The refund will go to original payment methods in 5 to 7 "
                          "business days.",
        "task_goal": "Your user id is mia_li_3668. Cancel reservation QW24RT please.",
        "candidate_card": "User request: cancel reservation QW24RT, booked 24 hours "
                          "ago — right at the 24 hours edge. Insurance cost was $48. "
                          "Booked on 2024-05-14 at 14:48 EST.",
    },
]


def main() -> int:
    pkg = json.loads((PART6 / "judge_package.json").read_text())
    rx = pkg["digit_strip"]["regex"]
    template = pkg["prompt_template"]
    assert rx == build_judge.WINDOW_DIGITS_RE, "package/build_judge regex drift"
    assert template == build_judge.PROMPT_TEMPLATE, "package/build_judge template drift"

    n_bad = 0
    for i, probe in enumerate(PROBES):
        rendered = build_judge.render_judge_input(
            probe["policy_excerpt"], probe["task_goal"], probe["candidate_card"])
        # rendered-by-package must equal rendered-from-package-template for the
        # same stripped inputs (byte-level binding between pkg and code)
        direct = template.format(
            policy_excerpt=build_judge.strip_window_digits(probe["policy_excerpt"]),
            task_goal=build_judge.strip_window_digits(probe["task_goal"]),
            candidate_card=build_judge.strip_window_digits(probe["candidate_card"]))
        assert rendered == direct, f"probe {i}: pkg-vs-code render mismatch"
        hits = re.findall(rx, rendered)
        if hits:
            n_bad += 1
            print(f"probe {i}: LEAK {hits} in rendered judge prompt")
        else:
            print(f"probe {i}: clean (no 24/48 digit survives in judge input)")
    if n_bad:
        print("LEAK-GREP: FAIL — freeze adjudication must STOP")
        return 1

    # --- parser pinned cases (correction C5: inconsistent fields => abstain)
    import judge_parser
    cases = [
        ('{"window_match": true, "program_conflict": false, "verdict": "admit"}', ("ok", "admit")),
        ('{"window_match": true, "program_conflict": true, "verdict": "admit"}', ("abstain", None)),
        ('{"window_match": false, "program_conflict": false, "verdict": "admit"}', ("abstain", None)),
        ('{"window_match": true, "program_conflict": false, "verdict": "reject"}', ("abstain", None)),
        ('{"window_match": false, "program_conflict": false, "verdict": "reject"}', ("ok", "reject")),
        ('{"window_match": false, "program_conflict": true, "verdict": "reject"}', ("ok", "reject")),
        ('{"window_match": true, "program_conflict": false, "verdict": "abstain"}', ("ok", "abstain")),
        ('{"window_match": true, "program_conflict": true, "verdict": "abstain"}', ("ok", "abstain")),
        ('{"window_match": true, "program_conflict": false, "verdict": "maybe"}', ("abstain", None)),
        ('{"window_match": true, "program_conflict": false}', ("abstain", None)),
        ('no json at all', ("abstain", None)),
        ('prose {"window_match": true, "program_conflict": false, "verdict": "admit", "extra": 1}',
         ("abstain", None)),
    ]
    n_pfail = 0
    for text, (want_status, want_verdict) in cases:
        r = judge_parser.parse_judge_output(text)
        okc = r["status"] == want_status and (
            want_verdict is None or r.get("verdict") == want_verdict)
        # decision mapping: admit only via the admit verdict
        want_gate = "admit" if (want_status, want_verdict) == ("ok", "admit") else "refuse"
        okc = okc and judge_parser.gate_decision(text) == want_gate
        if not okc:
            n_pfail += 1
            print(f"  parser case FAIL: {text[:60]!r} -> {r}")
    if n_pfail:
        print("JUDGE PARSER: FAIL — inconsistent-combination rule broken")
        return 1
    print(f"LEAK-GREP: PASS — judge inputs provably digit-free; "
          f"parser consistency rule pinned on {len(cases)} cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
