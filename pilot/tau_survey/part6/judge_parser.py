"""Executable parser for the frozen Part VI judge (adjudication correction C5).

parse_judge_output(text) implements judge_package.json's parser_spec:
  1. extract the substring from the first '{' to the last '}'; json.loads;
  2. require an object whose key SET is exactly
     {window_match, program_conflict, verdict};
  3. require types bool, bool, str and verdict ∈ {admit, reject, abstain};
  4. FIELD-CONSISTENCY (correction C5): the verdict must agree with the
     boolean fields —
       admit  ⟺  window_match==True  and program_conflict==False
       reject ⟸  window_match==False or  program_conflict==True
       (reject with window_match==True and program_conflict==False is
       inconsistent), abstain is accepted with any field combination;
  5. ANY deviation — no JSON, missing/extra keys, wrong types, unknown
     verdict string, INCONSISTENT field combination — is a parse failure.

Decision mapping (frozen): parse failure or an 'abstain' verdict ⇒ ABSTAIN;
the gate treats ABSTAIN as REJECT (paired-N fallback, v3 §6).
"""
from __future__ import annotations

import json

VERDICTS = ("admit", "reject", "abstain")
REQUIRED_KEYS = ("window_match", "program_conflict", "verdict")


def parse_judge_output(text: str) -> dict:
    """Returns {"status": "ok", "verdict", "window_match", "program_conflict",
    "decision"} or {"status": "abstain", "reason", "decision": "abstain"}."""
    fail = {"status": "abstain", "decision": "abstain"}
    if not isinstance(text, str):
        return fail | {"reason": "non-str output"}
    i, j = text.find("{"), text.rfind("}")
    if i < 0 or j <= i:
        return fail | {"reason": "no JSON object found"}
    try:
        obj = json.loads(text[i:j + 1])
    except Exception:
        return fail | {"reason": "json.loads failed"}
    if not isinstance(obj, dict):
        return fail | {"reason": "not a JSON object"}
    if set(obj) != set(REQUIRED_KEYS):
        return fail | {"reason": f"key set != {sorted(REQUIRED_KEYS)}"}
    wm, pc, v = obj["window_match"], obj["program_conflict"], obj["verdict"]
    if not isinstance(wm, bool) or not isinstance(pc, bool) or not isinstance(v, str):
        return fail | {"reason": "wrong field types"}
    if v not in VERDICTS:
        return fail | {"reason": f"verdict not in {VERDICTS}"}
    # field-consistency (correction C5)
    if v == "admit" and not (wm and not pc):
        return fail | {"reason": "INCONSISTENT: admit requires window_match=true "
                                   "and program_conflict=false"}
    if v == "reject" and (wm and not pc):
        return fail | {"reason": "INCONSISTENT: reject requires window_match=false "
                                   "or program_conflict=true"}
    return {"status": "ok", "verdict": v, "window_match": wm,
            "program_conflict": pc, "decision": "admit" if v == "admit" else "abstain"
                                                 if v == "abstain" else "reject"}


def gate_decision(text: str) -> str:
    """Gate-level mapping: 'admit' iff the parsed verdict is exactly 'admit';
    every other path (reject, abstain, parse failure) refuses the candidate."""
    r = parse_judge_output(text)
    return "admit" if r["status"] == "ok" and r["verdict"] == "admit" else "refuse"
