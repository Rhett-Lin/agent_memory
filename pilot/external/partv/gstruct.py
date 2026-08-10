"""Part V section 5: G-struct parser (frozen, single source of truth).

Implements the frozen structured-oracle proxy gate exactly as preregistered in
PART_V_PREREG_V5_FINAL.md section 5:

  - goal parse: `hot|heated|heat` -> heat; `cool|cooled` -> cool
    (goal lowercased; both word families present -> parse-fail).
  - card parse: the source prep action line (numbered transcript action lines
    of the form "NN. heat <obj> with <appliance>" / "NN. cool <obj> in <appliance>")
    with the same dictionary; appliance/object normalization (lowercase, strip
    adjectives {clean,hot,heated,cool,cooled,cold,chilled,sliced},
    singular/plural fold); both preps present -> parse-fail.
  - decision: card_prep == goal_prep -> admit; opposite -> reject
    (contradiction); parse-fail -> abstain (recorded as parse-failure, NOT
    counted as contradiction).

This module is imported by gates_and_audits.py (pre-rollout audits) and by
analyze_gate.py (estimand evaluation). Its sha256 is recorded in the outputs
manifest together with analyze_gate.py at analysis-freeze time.
"""

import hashlib
import re

# Goal dictionary, protocol section 5, verbatim word families.
GOAL_HEAT_PAT = re.compile(r"\b(?:heated|heat|hot)\b")
GOAL_COOL_PAT = re.compile(r"\b(?:cooled|cool)\b")

# Adjectives stripped by the frozen appliance/object normalization.
STRIP_ADJECTIVES = ("clean", "hot", "heated", "cool", "cooled",
                    "cold", "chilled", "sliced")

# Numbered transcript action line carrying a prep verb, as emitted by the
# pinned builder's transcript_card(): lines are rendered "%2d. %s".
PREP_ACTION_PAT = re.compile(
    r"^\s*\d+\.\s+(heat|cool)\s+(.+?)\s+(with|in)\s+(.+?)\s*$",
    re.IGNORECASE | re.MULTILINE)

_NUM_SUFFIX_PAT = re.compile(r"\s+\d+\b")


def normalize_entity(text):
    """Frozen appliance/object normalization.

    lowercase -> drop trailing object indices ("apple 2" -> "apple") ->
    drop adjectives {clean,hot,heated,cool,cooled,cold,chilled,sliced} ->
    singular/plural fold (documented deterministic rule set below).
    """
    t = _NUM_SUFFIX_PAT.sub("", text.lower()).strip()
    words = [w for w in t.split() if w not in STRIP_ADJECTIVES]
    out = []
    for w in words:
        if len(w) > 3 and w.endswith("ies"):
            w = w[:-3] + "y"                      # batteries -> battery
        elif len(w) > 3 and w.endswith("es") and w[:-2].endswith(
                ("o", "ch", "sh", "s", "x", "z")):
            w = w[:-2]                            # potatoes -> potato
        elif len(w) > 1 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]                            # apples -> apple
        out.append(w)
    return " ".join(out)


def parse_goal(goal_text):
    """Return 'heat' / 'cool' / None (parse-fail)."""
    g = goal_text.lower()
    has_heat = bool(GOAL_HEAT_PAT.search(g))
    has_cool = bool(GOAL_COOL_PAT.search(g))
    if has_heat and has_cool:
        return None          # both families present -> parse-fail
    if has_heat:
        return "heat"
    if has_cool:
        return "cool"
    return None              # neither -> parse-fail


def parse_card(card_text):
    """Return 'heat' / 'cool' / None (parse-fail: zero or both preps)."""
    preps = set()
    for m in PREP_ACTION_PAT.finditer(card_text):
        verb = m.group(1).lower()
        preps.add("heat" if verb == "heat" else "cool")
    if len(preps) != 1:
        return None
    return next(iter(preps))


def prep_objects(card_text):
    """Normalized object/appliance classes from the prep action line(s).

    Diagnostic + used by the card survival assertions; the section-5 decision
    itself depends only on the prep verb, as frozen.
    """
    found = []
    for m in PREP_ACTION_PAT.finditer(card_text):
        obj = normalize_entity(m.group(2))
        appliance = normalize_entity(m.group(4))
        found.append({"prep": m.group(1).lower(), "object": obj,
                      "appliance": appliance})
    return found


def decide(goal_text, card_text):
    """Frozen gate decision.

    Returns (decision, goal_prep, card_prep) where decision is one of
    'admit' (card_prep == goal_prep), 'reject' (parsed contradiction),
    'abstain' (parse-failure; NOT counted as contradiction).
    """
    goal_prep = parse_goal(goal_text)
    card_prep = parse_card(card_text)
    if goal_prep is not None and card_prep is not None:
        return ("admit" if goal_prep == card_prep else "reject",
                goal_prep, card_prep)
    return ("abstain", goal_prep, card_prep)


def module_sha256():
    with open(__file__, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()
