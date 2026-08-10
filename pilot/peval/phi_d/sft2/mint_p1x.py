"""mint_p1x.py — P1 (conditional_write) projections for the SFT2 production mint.

Fork of the adjudicated SFT1 machinery (mint_p1.project_instruction_wb +
mint_spec.project_memory) with two production changes, both pre-registered in
DATA_SPEC.md §4 / SFT1 §8 and disclosed in the receipt:
  1. evidence clips capped at 12 words (gold-side preference; sentence-level
     evidence head-clipped via Ib.span_prefix / Ib.sentence);
  2. numeric-printing card variant supported: the statedness probe decides the
     label from the RENDERED text (numeric iff theta's digits occur in the card
     condition clause, word-boundary semantics) — no hardcoded mode.
Word-boundary theta probes are inherited verbatim (mint_p1.theta_stated).
"""
import sys
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
PHI_D = HERE.parent
for p in (str(PHI_D.parent.parent), str(PHI_D), str(PHI_D / "sft0"), str(PHI_D / "sft1")):
    if p not in sys.path:
        sys.path.insert(0, p)

import mint_core as C                                     # noqa: E402
import mint_spec as M                                     # noqa: E402

MInt = C.MintError
_assert = C._assert
locate = C.locate
theta_stated = C.theta_stated
clip_words = C.clip_words

CMP_TEXT = M.CMP_TEXT
VERIFY_CUES = M.VERIFY_CUES

# numeric-printing card phrase (replaces the symbolic theta_phrase in roles)
NUMERIC_THETA_PHRASE = {
    ("crm_escalate", 1): "complaint threshold %d",
    ("crm_escalate", 2): "escalation threshold %d from the sla_policies table",
    ("inv_overstock", 1): "overstock limit %d",
    ("inv_overstock", 2): "overstock limit %d from the inv_policies table",
}


def project_instruction(schema_key, inst, style):
    """pi for a P1 instruction text (sibling or near-miss), 12-word clip variant."""
    text = inst["instruction"]
    _assert("\nNote: " not in text, "instruction unexpectedly padded")
    ib = C.Ib(text, core_end=len(text))
    pp, meta, vocab = inst["program_params"], inst["meta"], M.p1_vocab(schema_key)
    j2 = pp["join_depth"] == 2
    cmp_txt = CMP_TEXT[pp["cond_op"]]
    rule, theta_text, _ = M.expected_rule(schema_key, inst, vocab)
    rule_s, _, _ = locate(text, rule, 0, "instruction rule clause")

    ir = C.base_ir()
    if schema_key == "crm_escalate":
        ent_s, _, _ = locate(text, meta["entity_name"])
        surface = meta["entity_name"]
    else:
        ent_s, _, _ = locate(text, meta["sku"])
        surface = meta["sku"]
    ir["roles"]["subject_row"] = {"status": "present", "surface": surface,
                                  "evidence": ib.sentence("roles.subject_row", text, ent_s)[0]}
    if j2:
        ir["roles"]["policy_row"] = {"status": "present", "surface": vocab["policy_table"],
                                     "evidence": ib.span("roles.policy_row", vocab["policy_table"],
                                                         after=rule_s)[0]}
    nodes, nid = [], 0

    def add(op, status, evidence_field, evidence_span=None, args=None, deps=None,
            commutes=None, after=0):
        nonlocal nid
        nid += 1
        node = {"id": "n%d" % nid, "op": op, "status": status,
                "evidence": (ib.span(evidence_field, evidence_span, after=after)[0]
                             if evidence_span else None),
                "args": args or {}, "depends_on": deps or [], "commutes_with": commutes or []}
        nodes.append(node)
        return node["id"]

    read_cue = vocab["read_cues"][style]
    n_read = add("read", "present", "nodes.read", read_cue, args={"target": "subject_row"})
    conseq_start = vocab["conseq"][:12]
    cut = rule.find(", " + conseq_start)
    _assert(cut != -1, "conseq cut not found in rule: %r" % rule[:90])
    cond_part = rule[:cut]
    attribute = vocab["attr"]
    attr_span = vocab["attr_span"]
    attr_s = rule.find(attr_span)
    _assert(attr_s != -1, "attribute span not in rule")
    cmp_abs = rule_s + rule.find(" " + cmp_txt)
    pol_clause = text[rule_s:cut + rule_s]
    polarity = "negative" if any(c in (" " + pol_clause.lower() + " ") for c in M.NEG_CUES) else "positive"
    _assert(polarity == "positive", "P1 instructions render affirmative conditions; got %s" % polarity)

    if j2:
        _assert(not theta_stated(pp["theta"], cond_part),
                "theta LEAKS into a J2 condition clause: %r" % cond_part[:90])
        _assert(vocab["policy_col"] in rule, "policy column name missing from J2 rule")
        value_status, value_val, value_span = "present", vocab["policy_col"], theta_text
    else:
        _assert(theta_stated(pp["theta"], cond_part),
                "numeric theta NOT stated in a J1 condition clause: %r" % cond_part[:90])
        value_status, value_val, value_span = "present", str(pp["theta"]), cmp_txt + " " + str(pp["theta"])

    n_branch = add("branch", "present", "nodes.branch", clip_words(cond_part), deps=[n_read],
                   args={"predicate": {
                       "attribute": ib.f("predicate.attribute", "present", attribute, attr_span, after=rule_s),
                       "op": ib.f("predicate.op", "present", pp["cond_op"], cmp_txt, after=rule_s + attr_s),
                       "value": ib.f("predicate.value", value_status, value_val, value_span, after=cmp_abs),
                       "polarity": ib.f("predicate.polarity", "present", polarity, cmp_txt,
                                        after=rule_s + attr_s)},
                       "then_effects": vocab["effects_then"], "else_effects": vocab["effects_else"]})
    ib.span("predicate.then_effects", vocab["conseq"], after=cmp_abs)
    ib.span("predicate.else_effects", vocab["alt"], after=cmp_abs)
    n_verify = add("verify", "present", "nodes.verify", VERIFY_CUES[style],
                   args={"target": "subject_row"}, deps=[n_branch])
    ir["nodes"] = nodes
    ir["termination"] = {"status": "present",
                         "evidence": ib.span("termination", VERIFY_CUES[style])[0]}
    return ir, ib.ev, {"value_symbolic": j2, "value_mode": "symbolic" if j2 else "numeric"}


def project_memory(schema_key, inst):
    """pi for a P1 memory card (entity-instantiated roles, optional numeric
    variant). src_inst must carry "_card_text" and the (instantiated) "roles"."""
    roles = inst["roles"]
    text, pp, vocab = inst["_card_text"], inst["program_params"], M.p1_vocab(schema_key)
    steps = list(roles["steps"])
    j2 = pp["join_depth"] == 2
    _assert(steps[0].startswith("Read the "), "card step0 not the read step: %r" % steps[0][:60])
    idx = 1
    find_step = None
    if j2:
        find_step = steps[1]
        _assert(find_step.startswith("Find the "), "card J2 find-step missing: %r" % find_step[:60])
        idx = 2
    compare_step, if_step, else_step, readback = steps[idx:idx + 4]
    _assert(compare_step.startswith("Compare the row's "), "card compare-step: %r" % compare_step[:60])
    _assert(if_step.startswith("If the "), "card if-step: %r" % if_step[:60])
    _assert(else_step.startswith("Otherwise, "), "card else-step: %r" % else_step[:60])
    _assert(readback.startswith("Read the row back"), "card readback-step: %r" % readback[:60])
    _assert(len(steps) == idx + 4, "unexpected card step count: %d" % len(steps))

    ib = C.Ib(text, core_end=C.card_core_end(text))

    ir = C.base_ir()
    ir["roles"]["subject_row"] = {"status": "present", "surface": vocab["card_entity"],
                                  "evidence": ib.span("roles.subject_row", clip_words(steps[0]))[0]}
    if j2:
        cut_head = find_step.find(" in the %s table (" % vocab["policy_table"])
        _assert(cut_head != -1, "find-step head cut not found: %r" % find_step[:90])
        find_head = find_step[:cut_head]
        _assert(len(find_head.split()) <= C.MAXW, "find-step head too long: %r" % find_head)
        ir["roles"]["policy_row"] = {"status": "present", "surface": vocab["policy_table"],
                                     "evidence": ib.span("roles.policy_row",
                                                         "in the %s table" % vocab["policy_table"])[0]}

    cmp_txt = CMP_TEXT[pp["cond_op"]]
    _assert(cmp_txt in if_step, "cmp absent from if-step: %r" % if_step[:80])
    conseq_c = vocab["conseq"].replace("set its", "set") if schema_key == "inv_overstock" else vocab["conseq"]
    if_cut = if_step.find(", " + conseq_c[:10])
    _assert(if_cut != -1, "card conseq cut not found: %r" % if_step[:90])
    cond_part = if_step[:if_cut]
    cmp_abs = text.find(cmp_txt, locate(text, cond_part)[0])
    pol_clause = " " + cond_part.lower() + " "
    polarity = "negative" if any(cue in pol_clause for cue in M.NEG_CUES) else "positive"
    _assert(polarity == "positive", "P1 cards render affirmative conditions")

    # statedness decides numeric vs symbolic (numeric-printing card lever).
    numeric = theta_stated(pp["theta"], cond_part)
    if numeric:
        value_val = str(pp["theta"])
        num_tail = vocab["policy_col"] if False else None  # not used
        value_span = "%s %d" % (cmp_txt, pp["theta"]) if (" %s %d" % (cmp_txt, pp["theta"])) in cond_part \
            else None
        if value_span is None:
            # number sits inside the theta phrase ("... threshold of 8"): ship its tail
            w = cond_part.split()
            i = next(k for k, x in enumerate(w) if x.rstrip(",.;") == str(pp["theta"]))
            value_span = " ".join(w[max(0, i - 1):i + 1])
    else:
        # no digits in the condition clause -> symbolic, exactly the SFT1 rule.
        if j2:
            _assert(vocab["policy_col"] in find_step, "policy column not in find-step")
            value_val, value_span = vocab["policy_col"], vocab["j2_theta_card"]
        else:
            value_val, value_span = vocab["j1_theta_card"], vocab["j1_theta_card"]
        _assert(value_span in if_step, "theta_phrase absent from if-step: %r" % if_step[:80])

    nodes, nid = [], 0

    def add(op, evidence_field, evidence_span, args=None, deps=None, commutes=None):
        nonlocal nid
        nid += 1
        node = {"id": "n%d" % nid, "op": op, "status": "present",
                "evidence": ib.span(evidence_field, evidence_span)[0],
                "args": args or {}, "depends_on": deps or [], "commutes_with": commutes or []}
        nodes.append(node)
        return node["id"]

    n_read = add("read", "nodes.read", clip_words(steps[0]), args={"target": "subject_row"})
    deps = [n_read]
    if j2:
        cut_head = find_step.find(" in the %s table (" % vocab["policy_table"])
        find_head = find_step[:cut_head] if cut_head != -1 else find_step
        deps.append(add("read", "nodes.read_policy", clip_words(find_head),
                        args={"target": "policy_row"}, deps=[]))
    n_branch = add("branch", "nodes.branch", clip_words(cond_part), deps=deps,
                   args={"predicate": {
                       "attribute": ib.f("predicate.attribute", "present", vocab["attr"],
                                         vocab["attr"], after=locate(text, if_step)[0]),
                       "op": ib.f("predicate.op", "present", pp["cond_op"], cmp_txt, after=cmp_abs - 1),
                       "value": ib.f("predicate.value", "present", value_val, value_span,
                                     after=cmp_abs - 1),
                       "polarity": ib.f("predicate.polarity", "present", polarity, cmp_txt,
                                        after=cmp_abs - 1)},
                       "then_effects": vocab["effects_then"], "else_effects": vocab["effects_else"]})
    ib.span("predicate.then_effects", conseq_c, after=cmp_abs)
    ib.span("predicate.else_effects", vocab["alt"], after=cmp_abs)
    n_verify = add("verify", "nodes.verify", readback, args={"target": "subject_row"}, deps=[n_branch])
    ir["nodes"] = nodes
    ir["termination"] = {"status": "present", "evidence": ib.span("termination", readback)[0]}
    return ir, ib.ev, {"value_symbolic": not numeric,
                       "value_mode": "numeric" if numeric else "symbolic"}
