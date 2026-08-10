"""mint_p3x.py — P3 (aggregate_gate) projections for the SFT2 production mint.

Frozen P3 conventions (clause tables mirror build_ticket_gate_close /
build_cal_finalize / p3_roles verbatim; DATA_QC.md decision D2):
  * roles subject_row / child_set / audit_sink, all present.
  * nodes: read, aggregate(count over child_set), branch, write(parent set),
    write(audit insert); the two writes commute ONLY in cards (step 4 states
    "(either order of the two writes is fine)").
  * predicate: attribute "count of subtasks"/"count of attendees"; op "=="
    (correct program, gate says count==0) / ">=" (near-miss, >=1 on the
    done-set — taken from program_params.check, never re-labeled); polarity
    from the rendered condition via the negation-cue rule (correct P3 renders
    negated: "If no subtask ... is still open" / "If none remain" -> negative;
    near-miss affirmative -> positive).
  * value statedness: correct INSTRUCTIONS print "equals 0"/"is 0" -> numeric
    "0"; cards render "none remain" (no digit) -> symbolic "none remain"
    (audit ZERO_SET hit). Near-miss texts render "at least one" (no digit
    "1"; word-boundary-asserted) -> symbolic "at least one" (audit ONE_SET).
  * instr verify/termination evidence = the procedure's stated completion
    directive per style (the generator renders no explicit read-back sentence
    in P3 instruction styles; documented decision D2 — same disclosure class
    as the SFT1 J2 card-vs-instruction policy-read rule).
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

_assert = C._assert
locate = C.locate
theta_stated = C.theta_stated
clip_words = C.clip_words

CHILD = {"ticket_gate_close": "subtasks", "cal_finalize": "attendees"}
CHILD_TBL = {"ticket_gate_close": "subtasks", "cal_finalize": "attendees"}
PARENT_TBL = {"ticket_gate_close": "tickets", "cal_finalize": "events"}
LOG_TBL = {"ticket_gate_close": "ticket_events", "cal_finalize": "notifications"}
ATTR_VAL = {"ticket_gate_close": "count of subtasks", "cal_finalize": "count of attendees"}
AGG_PHRASE = {  # as-stated aggregate filter summary per (schema, near-miss flag)
    ("ticket_gate_close", False): "subtasks whose status is not 'done'",
    ("ticket_gate_close", True): "subtasks that are complete",
    ("cal_finalize", False): "attendees with RSVP 'declined'",
    ("cal_finalize", True): "attendees that have accepted",
}
STATUS_A = {"ticket_gate_close": "resolved", "cal_finalize": "confirmed"}
STATUS_B = {"ticket_gate_close": "in_progress", "cal_finalize": "needs_review"}
LOG_A = {"ticket_gate_close": "'resolution' entry", "cal_finalize": "'confirmation' notification"}
LOG_B = {"ticket_gate_close": "'comment' entry", "cal_finalize": "'warning' notification"}


def rule_text(schema_key, inst):
    meta = inst["meta"]
    nm = inst["program_params"]["agg_sem"] == "done"
    if schema_key == "ticket_gate_close":
        if nm:
            return ("If at least one subtask of ticket %s is complete, mark the ticket "
                    "'resolved' and log a 'resolution' entry in ticket_events (use id 7001); "
                    "otherwise set it to 'in_progress' and add a 'comment' entry (id 7002)."
                    % meta["tkey"]), nm
        return ("If no subtask of ticket %s is still open (count of subtasks whose status "
                "is not 'done' equals 0), mark the ticket 'resolved' and log a 'resolution' "
                "entry in ticket_events (use id 7001); otherwise set it to 'in_progress' "
                "and add a 'comment' entry noting how many remain open (id 7002)."
                % meta["tkey"]), nm
    if nm:
        return ("If at least one attendee of the event '%s' (%s) has accepted, set the "
                "event status to 'confirmed' and insert a 'confirmation' notification for "
                "the owner (use id 8101); otherwise set it to 'needs_review' and insert a "
                "'warning' notification (id 8102)." % (meta["title"], meta["date"])), nm
    return ("If no attendee of the event '%s' (%s) has declined (their RSVP count of "
            "'declined' is 0), set the event status to 'confirmed' and insert a "
            "'confirmation' notification addressed to the event's owner (use id 8101); "
            "otherwise set it to 'needs_review' and insert a 'warning' notification "
            "(id 8102)." % (meta["title"], meta["date"])), nm


def _cut_condition(schema_key, rule):
    head = ", mark the ticket" if schema_key == "ticket_gate_close" else ", set the event status"
    cut = rule.find(head)
    _assert(cut != -1, "P3 conseq cut not found in rule: %r" % rule[:90])
    return rule[:cut], rule[cut + 2:]


def project_instruction(schema_key, inst, style):
    text = inst["instruction"]
    _assert("\nNote: " not in text, "instruction unexpectedly padded")
    meta = inst["meta"]
    rule, nm = rule_text(schema_key, inst)
    rule_s, _, _ = locate(text, rule, 0, "P3 instruction rule")
    cond_part, conseq_rest = _cut_condition(schema_key, rule)

    ib = C.Ib(text, core_end=len(text))
    ir = C.base_ir()
    if schema_key == "ticket_gate_close":
        subj_surface = "ticket %s" % meta["tkey"]
        subj_anchor = meta["tkey"]
    else:
        subj_surface = "the event '%s'" % meta["title"]
        subj_anchor = "'%s'" % meta["title"]
    ent_s, _, _ = locate(text, subj_anchor)
    ir["roles"]["subject_row"] = {"status": "present", "surface": subj_surface,
                                  "evidence": ib.sentence("roles.subject_row", text, ent_s)[0]}
    child = CHILD[schema_key]
    # rule-internal child phrase (works for the NM rule too, which only renders
    # the singular "subtask"/"attendee"): "no subtask of ticket", "at least one
    # attendee of the event", ...
    child_ev = cond_part[cond_part.find(" ") + 1:]
    ir["roles"]["child_set"] = {"status": "present", "surface": child,
                                "evidence": ib.span("roles.child_set", clip_words(child_ev),
                                                    after=rule_s)[0]}
    log_tbl = LOG_TBL[schema_key]
    log_ev = ("log a 'resolution' entry in %s" % log_tbl) if schema_key == "ticket_gate_close" \
        else "'confirmation' notification"
    ir["roles"]["audit_sink"] = {"status": "present", "surface": log_tbl,
                                 "evidence": ib.span("roles.audit_sink", log_ev,
                                                     after=rule_s)[0]}

    # polarity from the rendered condition (negation-cue rule).
    pol_clause = " " + cond_part.lower() + " "
    polarity = "negative" if any(c in pol_clause for c in M.NEG_CUES) else "positive"
    _assert(polarity == ("positive" if nm else "negative"),
            "P3 polarity rule mismatch: nm=%s got %s" % (nm, polarity))
    # value statedness (word-boundary on the rendered condition clause).
    if nm:
        _assert(not theta_stated(1, cond_part), "digit 1 leaks into P3 NM condition: %r" % cond_part[:80])
        value_val, op_val, value_mode = "at least one", ">=", "symbolic"
        num_ev = op_ev = "at least one"
        attr_ev = "at least one %s of" % child.rstrip("s") if schema_key == "ticket_gate_close" \
            else "at least one attendee of"
        if schema_key == "ticket_gate_close":
            attr_ev = "at least one subtask of"
    else:
        _assert(theta_stated(0, cond_part), "0 not stated in P3 correct condition: %r" % cond_part[:80])
        value_val, op_val, value_mode = "0", "==", "numeric"
        num_ev = "equals 0" if schema_key == "ticket_gate_close" else "is 0"
        op_ev = num_ev
        attr_ev = "count of subtasks" if schema_key == "ticket_gate_close" else "RSVP count"

    nodes, nid = [], 0

    def add(op, evidence_field, evidence_span, args=None, deps=None, commutes=None, after=0):
        nonlocal nid
        nid += 1
        node = {"id": "n%d" % nid, "op": op, "status": "present",
                "evidence": ib.span(evidence_field, evidence_span, after=after)[0],
                "args": args or {}, "depends_on": deps or [], "commutes_with": commutes or []}
        nodes.append(node)
        return node["id"]

    if schema_key == "ticket_gate_close":
        read_ev = {0: "is in the tickets table", 1: "process ticket %s" % meta["tkey"],
                   2: "process ticket %s" % meta["tkey"]}[style]
        agg_ev = {0: "(count of subtasks whose status is not 'done' equals 0)",
                  1: "aggregate the subtasks first",
                  2: "Aggregate first"}[style] if not nm else \
                 {0: clip_words(cond_part), 1: "aggregate the subtasks first",
                  2: "Aggregate first"}[style]
        ver_ev = {0: "Verify the counts yourself before writing",
                  1: "then write the update and the log entry",
                  2: "write both the status and the log entry"}[style]
    else:
        read_ev = {0: "Look up the event", 1: "finalize '%s'" % meta["title"],
                   2: "finalize event '%s'" % meta["title"]}[style]
        agg_ev = {0: "count the RSVPs yourself", 1: "aggregate the responses first",
                  2: "Count RSVPs first"}[style]
        ver_ev = {0: "write the status and the notification for the event owner",
                  1: "then write both records",
                  2: "then write the event status and the owner notification"}[style]

    n1 = add("read", "nodes.read", clip_words(read_ev), args={"target": "subject_row"})
    n2 = add("aggregate", "nodes.aggregate", clip_words(agg_ev), deps=[n1],
             args={"over": "child_set", "function": "count",
                   "value": AGG_PHRASE[(schema_key, nm)]})
    cond_abs = rule_s
    n3 = add("branch", "nodes.branch", clip_words(cond_part), deps=[n2],
             args={"predicate": {
                 "attribute": ib.f("predicate.attribute", "present", ATTR_VAL[schema_key],
                                   attr_ev, after=cond_abs),
                 "op": ib.f("predicate.op", "present", op_val, op_ev, after=cond_abs),
                 "value": ib.f("predicate.value", "present", value_val, num_ev, after=cond_abs),
                 "polarity": ib.f("predicate.polarity", "present", polarity,
                                  clip_words(cond_part), after=cond_abs)},
                 "then_effects": [
                     {"action": "set", "target": "subject_row", "value": STATUS_A[schema_key]},
                     {"action": "insert", "target": "audit_sink", "value": LOG_A[schema_key]}],
                 "else_effects": [
                     {"action": "set", "target": "subject_row", "value": STATUS_B[schema_key]},
                     {"action": "insert", "target": "audit_sink", "value": LOG_B[schema_key]}]})
    wr_par_ev = ("mark the ticket 'resolved'" if schema_key == "ticket_gate_close"
                 else "set the event status to 'confirmed'")
    n4 = add("write", "nodes.write_parent", clip_words(wr_par_ev), deps=[n3],
             args={"action": "set", "target": "subject_row",
                   "value": "status per branch"})
    wr_log_ev = ("log a 'resolution' entry in ticket_events" if schema_key == "ticket_gate_close"
                 else "insert a 'confirmation' notification")
    n5 = add("write", "nodes.write_log", clip_words(wr_log_ev), deps=[n3],
             args={"action": "insert", "target": "audit_sink",
                   "value": "entry per branch"})
    n6 = add("verify", "nodes.verify", clip_words(ver_ev), args={"target": "subject_row"},
             deps=[n4, n5])
    ir["nodes"] = nodes
    ir["termination"] = {"status": "present",
                         "evidence": ib.span("termination", clip_words(ver_ev))[0]}
    return ir, ib.ev, {"value_symbolic": value_mode == "symbolic", "value_mode": value_mode}


def project_memory(schema_key, inst):
    """pi for a P3 memory card. src_inst carries "_card_text" + instantiated "roles"."""
    roles = inst["roles"]
    text, meta = inst["_card_text"], inst["meta"]
    nm = inst["program_params"]["agg_sem"] == "done"
    steps = list(roles["steps"])
    _assert(len(steps) == 6, "P3 card step count != 6")
    _assert(steps[0].startswith("Read the "), "card read step: %r" % steps[0][:60])
    _assert(steps[1].startswith("Aggregate over the linked "), "card agg step: %r" % steps[1][:60])
    _assert(steps[2].startswith("Count how many "), "card gate step: %r" % steps[2][:60])
    _assert(steps[3].startswith("Write the status update "), "card write step: %r" % steps[3][:60])
    _assert(steps[4].startswith("Insert a matching entry "), "card log step: %r" % steps[4][:60])
    _assert("(either order of the two writes is fine)" in steps[4],
            "P3 card write-commutation marker missing")
    _assert(steps[5].startswith("Read the ") and steps[5].endswith("confirm before finishing."),
            "card readback step: %r" % steps[5][:60])

    ib = C.Ib(text, core_end=C.card_core_end(text))
    ir = C.base_ir()
    ir["roles"]["subject_row"] = {"status": "present",
                                  "surface": steps[0].split("for ", 1)[1].rstrip("."),
                                  "evidence": ib.span("roles.subject_row", clip_words(steps[0]))[0]}
    child = CHILD[schema_key]
    ir["roles"]["child_set"] = {"status": "present", "surface": child,
                                "evidence": ib.span("roles.child_set", clip_words(steps[1]))[0]}
    log_tbl = LOG_TBL[schema_key]
    ir["roles"]["audit_sink"] = {"status": "present", "surface": log_tbl,
                                 "evidence": ib.span("roles.audit_sink",
                                                     "the %s table" % log_tbl)[0]}

    gate = steps[2]
    # condition = the "If ...," phrase inside the gate step; polarity per cue rule.
    idx = gate.find("If ")
    _assert(idx != -1, "card gate lacks condition sentence: %r" % gate[:80])
    comma = gate.find(",", idx)
    _assert(comma != -1, "card gate conseq comma missing: %r" % gate[:80])
    cond_sent = gate[idx:comma]
    pol_clause = " " + cond_sent.lower() + " "
    polarity = "negative" if any(c in pol_clause for c in M.NEG_CUES) else "positive"
    _assert(polarity == ("positive" if nm else "negative"),
            "P3 card polarity mismatch: nm=%s got %s (%r)" % (nm, polarity, cond_sent))
    if nm:
        _assert(not theta_stated(1, gate), "digit 1 leaks into P3 NM card gate")
        value_val, op_val, value_mode = "at least one", ">=", "symbolic"
        num_ev = "at least one"
        attr_ev = "Count how many %s are already" % child
    else:
        _assert(not theta_stated(0, gate), "digit 0 leaks into P3 card gate")
        value_val, op_val, value_mode = "none remain", "==", "symbolic"
        num_ev = "none remain"
        attr_ev = "Count how many %s are" % child
    count_cue = gate[:idx].strip()

    # effects clauses inside the gate step
    then_head = ("mark the ticket 'resolved'" if schema_key == "ticket_gate_close"
                 else "set the event status to 'confirmed'")
    else_head = ("set the ticket to 'in_progress'" if schema_key == "ticket_gate_close"
                 else "set it to 'needs_review'")
    _assert(then_head in gate and else_head in gate, "P3 gate effect clauses missing: %r" % gate[:100])

    nodes, nid = [], 0

    def add(op, evidence_field, evidence_span, args=None, deps=None, commutes=None):
        nonlocal nid
        nid += 1
        node = {"id": "n%d" % nid, "op": op, "status": "present",
                "evidence": ib.span(evidence_field, evidence_span)[0],
                "args": args or {}, "depends_on": deps or [], "commutes_with": commutes or []}
        nodes.append(node)
        return node["id"]

    n1 = add("read", "nodes.read", clip_words(steps[0]), args={"target": "subject_row"})
    n2 = add("aggregate", "nodes.aggregate", clip_words(steps[1]), deps=[n1],
             args={"over": "child_set", "function": "count",
                   "value": AGG_PHRASE[(schema_key, nm)]})
    n3 = add("branch", "nodes.branch", clip_words(count_cue + " " + cond_sent), deps=[n2],
             args={"predicate": {
                 "attribute": ib.f("predicate.attribute", "present", ATTR_VAL[schema_key],
                                   attr_ev),
                 "op": ib.f("predicate.op", "present", op_val, num_ev),
                 "value": ib.f("predicate.value", "present", value_val, num_ev),
                 "polarity": ib.f("predicate.polarity", "present", polarity, num_ev)},
                 "then_effects": [
                     {"action": "set", "target": "subject_row", "value": STATUS_A[schema_key]},
                     {"action": "insert", "target": "audit_sink", "value": LOG_A[schema_key]}],
                 "else_effects": [
                     {"action": "set", "target": "subject_row", "value": STATUS_B[schema_key]},
                     {"action": "insert", "target": "audit_sink", "value": LOG_B[schema_key]}]})
    ib.span("predicate.then_effects", then_head)
    ib.span("predicate.else_effects", else_head)
    n4 = add("write", "nodes.write_parent", clip_words(steps[3]), deps=[n3],
             args={"action": "set", "target": "subject_row", "value": "status per branch"})
    n5 = add("write", "nodes.write_log", clip_words(steps[4]), deps=[n3],
             commutes=[n4],
             args={"action": "insert", "target": "audit_sink", "value": "entry per branch"})
    nodes[-2]["commutes_with"] = [n5]
    add("verify", "nodes.verify", steps[5], args={"target": "subject_row"}, deps=[n4, n5])
    ir["nodes"] = nodes
    ir["termination"] = {"status": "present", "evidence": ib.span("termination", steps[5])[0]}
    return ir, ib.ev, {"value_symbolic": value_mode == "symbolic", "value_mode": value_mode}
