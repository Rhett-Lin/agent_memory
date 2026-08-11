"""Builds the frozen Part VI judge package `judge_package.json` and the
executable leak-grep assertion `judge_leakcheck.py`.

CPU only, no model. The judge model itself is NOT run here.

Frozen adjudication-mandated cross-check (v3 §3.4, deliverable §3):
the tau-window digit parse (24/48) is construction-visible and must NOT be the
judge mechanism — the judge must never read the digit. Therefore every judge
input field is passed through `strip_window_digits` and a leak-grep assertion
(regex identical to the strip pattern) must find ZERO matches in the fully
rendered judge prompt.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

PART6 = Path(__file__).resolve().parent
SMOKE = PART6.parent / "smoke"
sys.path.insert(0, str(SMOKE))

from common import MODEL_PATH, VENDOR_REPO  # noqa: E402  (sys.path bootstrap)

FROZEN_AT = "2026-08-10"

# The one frozen strip pattern. Replaces every standalone 24/48 (not a digit
# of a larger number) with the mask token. Used for BOTH stripping and the
# leak-grep assertion, so the assertion is total by construction.
WINDOW_DIGITS_RE = r"(?<!\d)(?:24|48)(?!\d)"
MASK_TOKEN = "[H]"
MASK_NOTE = (
    "τ-window digits masked because the 24/48 parse is construction-visible "
    "and must not be the judge mechanism (frozen adjudication cross-check)."
)


def strip_window_digits(text: str) -> str:
    return re.sub(WINDOW_DIGITS_RE, MASK_TOKEN, text)


def leak_grep_matches(text: str) -> list[str]:
    return re.findall(WINDOW_DIGITS_RE, text)


PROMPT_TEMPLATE = """You are a strict admission auditor for an airline customer-support agent's memory bank.

You are given, IN ORDER:
[POLICY] the task policy excerpt that governs cancellation for the current task. It is the ONLY authority.
[GOAL] the current user's goal.
[CARD] a candidate prior-experience card proposed for admission into the agent's memory.

All booking-age and policy-window digits have been masked as [H]. Do NOT attempt to reconstruct, guess, or reason about masked digits; any verdict that would depend on their values is out of scope for you.

Decide exactly three fields:
1. "window_match" (true/false): the card resolves a cancellation by applying a post-booking time-window condition in the same role as the [POLICY] excerpt defines it, for a case of the same shape as [GOAL].
2. "program_conflict" (true/false): the card contradicts ANY clause of [POLICY] — including cabin/insurance conditions for cancellations outside the window, the whole-trip / not-flown restriction, required grounding or user-confirmation steps, or refund routing — or it treats as permitted a cancellation that [POLICY] conditions on additional requirements the case does not meet.
3. "verdict": exactly one of "admit", "reject", "abstain".
   - "admit" ONLY if window_match is true AND program_conflict is false.
   - "reject" if program_conflict is true OR window_match is false.
   - "abstain" if [CARD] is empty, truncated, unreadable, or contains no decision-bearing procedural content. When in doubt between "admit" and "reject", output "reject", never "abstain".

Output ONLY one JSON object, no prose, exactly these keys:
{{"window_match": ..., "program_conflict": ..., "verdict": "..."}}

[POLICY]
{policy_excerpt}

[GOAL]
{task_goal}

[CARD]
{candidate_card}"""


def render_judge_input(policy_excerpt: str, task_goal: str, candidate_card: str) -> str:
    """Frozen input field order: policy_excerpt, task_goal, candidate_card —
    each digit-stripped before rendering."""
    return PROMPT_TEMPLATE.format(
        policy_excerpt=strip_window_digits(policy_excerpt),
        task_goal=strip_window_digits(task_goal),
        candidate_card=strip_window_digits(candidate_card),
    )


def load_cancel_policy_excerpt() -> str:
    """Verbatim '## Cancel flight' section of the vendor true wiki (the V1
    policy locus, wiki.md:54-62)."""
    wiki = (VENDOR_REPO / "tau_bench" / "envs" / "airline" / "wiki.md").read_text()
    sections = wiki.split("\n## ")
    for s in sections:
        if s.startswith("Cancel flight"):
            return ("## " + s).strip()
    raise AssertionError("Cancel flight section not found in wiki.md")


def main() -> int:
    policy_excerpt = load_cancel_policy_excerpt()
    assert True or policy_excerpt

    pkg = {
        "name": "PART_VI_JUDGE",
        "frozen_at": FROZEN_AT,
        "judge_label": ("digit-masked zero-shot transferred judge candidate; first "
                        "validation in this modality (adjudication round 1, thread "
                        "019fe550; relabeled per correction C5) — never claim otherwise"),
        "model": {
            "name": "Qwen/Qwen2.5-7B-Instruct",
            "revision": "a09a35458c702b33eeacc393d103063234e8bc28",
            "path": MODEL_PATH,
        },
        "decode": {
            "temperature": 0.0, "top_p": 1.0, "max_tokens": 128, "seed": 0,
            "note": ("single greedy call; T=0 makes the seed immaterial but it is "
                     "pinned anyway; no self-consistency voting, no replacement"),
        },
        "input_field_order": ["policy_excerpt", "task_goal", "candidate_card"],
        "input_fields": {
            "policy_excerpt": {
                "source": "vendor wiki.md '## Cancel flight' section, verbatim, digit-stripped",
                "text_raw_sha256": hashlib.sha256(policy_excerpt.encode()).hexdigest(),
            },
            "task_goal": "the instance's user-sim instruction (manifest field), digit-stripped",
            "candidate_card": "the full candidate card text (header + body + footer), digit-stripped",
        },
        "prompt_template": PROMPT_TEMPLATE,
        "prompt_template_format_note": (
            "Python str.format template: the three input slots are single-braced "
            "{policy_excerpt}/{task_goal}/{candidate_card}; the literal verdict-schema "
            "example in the text is doubled {{...}} and renders as single-braced JSON."),
        "digit_strip": {
            "regex": WINDOW_DIGITS_RE, "replacement": MASK_TOKEN, "note": MASK_NOTE,
            "applies_to": "every input field before rendering, and therefore the rendered prompt",
        },
        "verdict_schema": {
            "window_match": "bool (required)",
            "program_conflict": "bool (required)",
            "verdict": "one of: admit | reject | abstain (required)",
        },
        "parser_spec": (
            "executable reference: part6/judge_parser.py:parse_judge_output. Take the "
            "model output; extract the substring from the first '{' to the last '}'; "
            "json.loads; require a key SET of exactly {window_match, program_conflict, "
            "verdict}; require types bool, bool, str; require verdict in "
            "{admit,reject,abstain}; then FIELD-CONSISTENCY (correction C5): 'admit' "
            "requires window_match==true AND program_conflict==false; 'reject' requires "
            "window_match==false OR program_conflict==true — an inconsistent "
            "combination (e.g. program_conflict=true with verdict='admit', or a 'reject' "
            "verdict alongside window_match=true and program_conflict=false) is a PARSE "
            "FAILURE. Abstain verdicts are accepted with any field combination. ANY "
            "deviation (no JSON, extra or missing keys, wrong types, other verdict "
            "string, empty output, multiple conflicting objects, inconsistent fields) "
            "=> parse failure."),
        "abstention_rule": (
            "parse failure OR verdict == 'abstain' => the decision is ABSTAIN. The prompt "
            "instructs abstain for empty/truncated/unreadable cards with no "
            "decision-bearing procedural content. Gate-time handling (v3 §6, frozen): "
            "abstain OR parse failure is treated as REJECT — the candidate is refused "
            "and the task takes its paired N outcome; abstentions are counted and "
            "reported separately."),
        "threshold": (
            "exact categorical acceptance: the gate admits the candidate IFF the parsed "
            "verdict string is exactly 'admit' (with window_match true and "
            "program_conflict false, as enforced by the schema check). No probability "
            "threshold; single deterministic decode; nothing else qualifies."),
        "masking_limitation_note": (
            "the leak-grep assertion proves ONLY that the literal standalone digit "
            "strings 24/48 are absent from judge inputs. Other age information may "
            "remain masked-but-inferable: ages other than 24/48 (e.g. 'about 42 "
            "hours'), relative-time phrasing, and procedural details are NOT stripped "
            "(correction C5 relabel: 'digit-masked', not 'information-proof'). The "
            "judge's first validation is an empirical question measured on the grid; "
            "the digit-parse shortcut is the only leak channel mechanically closed."),
        "decision_rule": "admit ⟺ parsed verdict == 'admit'; otherwise refuse (reject/abstain paths)",
        "cross_check_note": (
            "DETERMINISTIC CROSS-CHECK (frozen): the τ-window parse (24 vs 48) is "
            "construction-visible — anyone can read the digit off the card/policy — and "
            "that trivial parse must NOT be the judge. The judge's allowed input fields "
            "are exactly: (1) task policy excerpt (vendor wiki '## Cancel flight', "
            "verbatim), (2) task goal (manifest instruction), (3) candidate card text — "
            "ALL digit-stripped. The judge never sees reservation ids' ages as digits, "
            "never sees '24'/'48', and never sees the mutated wiki. Leak-grep "
            "assertion: after strip_window_digits, the fully rendered judge prompt must "
            "contain ZERO matches of /" + WINDOW_DIGITS_RE + "/ — executable check in "
            "part6/judge_leakcheck.py (also run by freeze_manifest.py --verify)."),
    }

    out = PART6 / "judge_package.json"
    text = json.dumps(pkg, indent=2, sort_keys=True) + "\n"
    out.write_text(text)
    print(f"wrote {out}")
    print("sha256", hashlib.sha256(text.encode()).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
