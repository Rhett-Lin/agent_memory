"""mint_p4x.py — P4 (delete_after_capture) projections for the SFT2 production mint.

Frozen P4 conventions (clause tables mirror build_crm_purge_lead /
build_ticket_purge_spam / p4_roles verbatim; DATA_QC.md decision D3):
  * roles subject_row / child_set present; audit_sink PRESENT iff the text
    requires an archive copy, else ABSENT-WITH-EVIDENCE (the omission clause is
    verbatim evidence: "no archival copy is needed" / "do NOT leave any audit
    entry" / card step "No archival copy is required for this request.").
  * nodes: read, branch, write(archive), write(delete children),
    write(delete parent), verify. On the near-miss the archive write node is
    ABSENT-WITH-EVIDENCE (same omission clause) assigned the pipeline position
    it would have had; present-node op sequence then matches the skip_archive
    signature expansion (kind-aware expected_ops).
  * ordering: the archive write precedes both delete writes (position rule,
    audit archive_capture); depends_on chain mirrors the DSL
    (delete_parent depends on archive + delete_children).
  * predicate: attribute "status"/"tag", op "==", value 'cold'/'spam'
    (string rule), polarity positive. P4 cards render the guard as
    "Confirm the row's status is 'cold' -- if it is not, stop without
    writing." — the operative condition is positive while the audit's raw
    cue rule lands on the else-path guard fragment ("if it is not"); the E1
    exception (pre-registered in audit_expanded) re-targets it to positive.
    The mint asserts the exact E1 pattern, else fails loudly.
  * effects: then = archive@audit_sink (correct only) + delete@child_set +
    delete@subject_row; else = {"action": "other", ..., "do nothing"}.
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
clip_words = C.clip_words

GUARD_FIELD = {"crm_purge_lead": "status", "ticket_purge_spam": "tag"}
GUARD_VALUE = {"crm_purge_lead": "cold", "ticket_purge_spam": "spam"}
GUARD_PHRASE = {"crm_purge_lead": "has status 'cold'", "ticket_purge_spam": "is tagged 'spam'"}
ARCHIVE_TBL = {"crm_purge_lead": "archived_leads", "ticket_purge_spam": "ticket_events"}
CHILD_TBL = {"crm_purge_lead": "lead_notes", "ticket_purge_spam": "subtasks"}
PARENT_TBL = {"crm_purge_lead": "leads", "ticket_purge_spam": "tickets"}
OMISSION = {"crm_purge_lead": "no archival copy is needed",
            "ticket_purge_spam": "do NOT leave any audit entry"}
ARCHIVE_EV = {"crm_purge_lead": "first archive it into archived_leads",
              "ticket_purge_spam": "first insert an 'audit' entry into ticket_events"}
DEL_CHILD_EV = {"crm_purge_lead": "then delete all of its lead_notes rows",
                "ticket_purge_spam": "then delete all of its subtasks"}
DEL_PARENT_EV = {"crm_purge_lead": "finally delete the lead row itself",
                 "ticket_purge_spam": "finally delete the ticket itself"}
# The near-miss instruction collapses the two deletes into one "erase the X and
# all of its Y" clause; the two delete nodes take distinct sub-spans of it.
DEL_CHILD_EV_NM = {"crm_purge_lead": "all of its rows in lead_notes",
                   "ticket_purge_spam": "all of its subtasks"}
DEL_PARENT_EV_NM = {"crm_purge_lead": "erase the lead",
                    "ticket_purge_spam": "erase the ticket"}
ROW_WORD = {"crm_purge_lead": "lead", "ticket_purge_spam": "ticket"}


def rule_text(schema_key, inst):
    meta = inst["meta"]
    nm = inst["program_params"].get("skip_archive", False)
    if schema_key == "crm_purge_lead":
        if nm:
            return ("If the lead %s (%s) in the leads table has status 'cold', permanently "
                    "erase the lead and all of its rows in lead_notes -- no archival copy is "
                    "needed. If the status is not 'cold', do nothing."
                    % (meta["entity_name"], meta["entity_email"])), nm
        _assert("_arch_date" in inst, "crm_purge_lead instance missing _arch_date "
                "(driver must attach family params)")
        return ("If the lead %s (%s) in the leads table has status 'cold', first archive "
                "it into archived_leads with id %d (copy name, email, status, score, and "
                "use archived_on '%s'), then delete all of its lead_notes rows and finally "
                "delete the lead row itself. If the status is not 'cold', do nothing."
                % (meta["entity_name"], meta["entity_email"], meta["arch_id"],
                   inst["_arch_date"])), nm
    if nm:
        return ("If the ticket %s in the tickets table is tagged 'spam', permanently "
                "erase the ticket and all of its subtasks -- do NOT leave any audit "
                "entry. If it is not tagged 'spam', do nothing." % meta["tkey"]), nm
    return ("If the ticket %s in the tickets table is tagged 'spam', first insert an "
            "'audit' entry into ticket_events with id %d capturing the key, title and "
            "reporter, then delete all of its subtasks, and finally delete the ticket "
            "itself. If it is not tagged 'spam', do nothing." % (meta["tkey"],
                                                                meta["audit_id"])), nm


def _cond_effect_shapes(schema_key, nm):
    then = []
    if not nm:
        then.append({"action": "archive", "target": "audit_sink",
                     "value": "archive copy of the row"})
    then += [{"action": "delete", "target": "child_set", "value": "all linked rows"},
             {"action": "delete", "target": "subject_row", "value": "the row itself"}]
    els = [{"action": "other", "target": "subject_row", "value": "do nothing"}]
    return then, els


def project_instruction(schema_key, inst, style):
    text = inst["instruction"]
    _assert("\nNote: " not in text, "instruction unexpectedly padded")
    meta = inst["meta"]
    rule, nm = rule_text(schema_key, inst)
    rule_s, _, _ = locate(text, rule, 0, "P4 instruction rule")
    cond_head = GUARD_PHRASE[schema_key]
    cond_c, _, _ = locate(text, cond_head, rule_s, "P4 condition head")

    ib = C.Ib(text, core_end=len(text))
    ir = C.base_ir()
    if schema_key == "crm_purge_lead":
        subj_surface = meta["entity_name"]
        subj_anchor = meta["entity_name"]
    else:
        subj_surface = "ticket %s" % meta["tkey"]
        subj_anchor = meta["tkey"]
    ent_s, _, _ = locate(text, subj_anchor)
    ir["roles"]["subject_row"] = {"status": "present", "surface": subj_surface,
                                  "evidence": ib.sentence("roles.subject_row", text, ent_s)[0]}
    child_ev = (DEL_CHILD_EV_NM[schema_key] if nm else
                DEL_CHILD_EV[schema_key].split("delete ", 1)[1])
    ir["roles"]["child_set"] = {
        "status": "present", "surface": "%s rows" % CHILD_TBL[schema_key],
        "evidence": ib.span("roles.child_set", child_ev)[0]}
    if nm:
        ir["roles"]["audit_sink"] = {"status": "absent", "surface": None,
                                     "evidence": ib.span("roles.audit_sink",
                                                         OMISSION[schema_key])[0]}
    else:
        ir["roles"]["audit_sink"] = {
            "status": "present", "surface": ARCHIVE_TBL[schema_key],
            "evidence": ib.span("roles.audit_sink", ARCHIVE_EV[schema_key])[0]}

    then_fx, else_fx = _cond_effect_shapes(schema_key, nm)
    nodes, nid = [], 0

    def add(op, status, evidence_field, evidence_span, args=None, deps=None):
        nonlocal nid
        nid += 1
        node = {"id": "n%d" % nid, "op": op, "status": status,
                "evidence": (ib.span(evidence_field, evidence_span)[0]
                             if evidence_span else None),
                "args": args or {}, "depends_on": deps or [], "commutes_with": []}
        nodes.append(node)
        return node["id"]

    firw = ROW_WORD[schema_key]
    ent_sentence, sent_s, _ = M.sentence_around(text, ent_s, max_words=80)
    n1 = add("read", "present", "nodes.read", clip_words(ent_sentence),
             args={"target": "subject_row"})
    n2 = add("branch", "present", "nodes.branch",
             clip_words(cond_head), deps=[n1],
             args={"predicate": {
                 "attribute": ib.f("predicate.attribute", "present", GUARD_FIELD[schema_key],
                                   cond_head, after=rule_s),
                 "op": ib.f("predicate.op", "present", "==", cond_head, after=rule_s),
                 "value": ib.f("predicate.value", "present", GUARD_VALUE[schema_key],
                               "'%s'" % GUARD_VALUE[schema_key], after=rule_s),
                 "polarity": ib.f("predicate.polarity", "present", "positive", cond_head,
                                  after=rule_s)},
                 "then_effects": then_fx, "else_effects": else_fx})
    ib.span("predicate.else_effects", "do nothing")
    if nm:
        n3 = add("write", "absent", "nodes.archive", OMISSION[schema_key], deps=[n2],
                 args={"action": "archive", "target": "audit_sink",
                       "value": "archive copy of the row"})
    else:
        n3 = add("write", "present", "nodes.archive", ARCHIVE_EV[schema_key], deps=[n2],
                 args={"action": "archive", "target": "audit_sink",
                       "value": "archive copy of the row"})
    dc_ev = DEL_CHILD_EV_NM[schema_key] if nm else DEL_CHILD_EV[schema_key]
    dp_ev = DEL_PARENT_EV_NM[schema_key] if nm else DEL_PARENT_EV[schema_key]
    n4 = add("write", "present", "nodes.delete_children", dc_ev, deps=[n3],
             args={"action": "delete", "target": "child_set", "value": "all linked rows"})
    n5 = add("write", "present", "nodes.delete_parent", dp_ev, deps=[n4],
             args={"action": "delete", "target": "subject_row", "value": "the %s itself" % firw})
    ver_ev = {0: "confirm the final state", 1: "verify afterwards",
              2: "act in a safe order, verify"}[style]
    add("verify", "present", "nodes.verify", ver_ev, args={"target": "subject_row"},
        deps=[n5])
    ir["nodes"] = nodes
    ir["termination"] = {"status": "present", "evidence": ib.span("termination", ver_ev)[0]}
    return ir, ib.ev, {"value_symbolic": False, "value_mode": "string"}


def project_memory(schema_key, inst):
    """pi for a P4 memory card. src_inst carries "_card_text" + instantiated "roles"."""
    roles = inst["roles"]
    text, meta = inst["_card_text"], inst["meta"]
    nm = inst["program_params"].get("skip_archive", False)
    steps = list(roles["steps"])
    _assert(len(steps) == 6, "P4 card step count != 6")
    _assert(steps[0].startswith("Read the "), "card read step: %r" % steps[0][:60])
    _assert(steps[1].startswith("Confirm the row's "), "card confirm step: %r" % steps[1][:60])
    if nm:
        _assert(steps[2] == "No archival copy is required for this request.",
                "card omission step: %r" % steps[2][:60])
    else:
        _assert(steps[2].startswith("Copy the row into the "), "card archive step: %r" % steps[2][:60])
    _assert(steps[3].startswith("Delete the linked rows in the "), "card del-child step")
    _assert(steps[4].startswith("Delete the ") and steps[4].endswith(" row itself."),
            "card del-parent step: %r" % steps[4][:60])
    _assert(steps[5].startswith("Read the ") and steps[5].endswith(" to confirm before finishing."),
            "card readback step: %r" % steps[5][:60])

    ib = C.Ib(text, core_end=C.card_core_end(text))
    ir = C.base_ir()
    ir["roles"]["subject_row"] = {"status": "present",
                                  "surface": steps[0].split("for ", 1)[1].rstrip("."),
                                  "evidence": ib.span("roles.subject_row", clip_words(steps[0]))[0]}
    ir["roles"]["child_set"] = {"status": "present",
                                "surface": "%s rows" % CHILD_TBL[schema_key],
                                "evidence": ib.span("roles.child_set", clip_words(steps[3]))[0]}
    if nm:
        ir["roles"]["audit_sink"] = {"status": "absent", "surface": None,
                                     "evidence": ib.span("roles.audit_sink", steps[2])[0]}
    else:
        ir["roles"]["audit_sink"] = {"status": "present", "surface": ARCHIVE_TBL[schema_key],
                                     "evidence": ib.span("roles.audit_sink",
                                                         clip_words(steps[2]))[0]}

    # guard phrase + E1 polarity exception (operative condition positive).
    gfield, gval = GUARD_FIELD[schema_key], GUARD_VALUE[schema_key]
    guard_phrase = "%s is '%s'" % (gfield, gval)
    _assert(guard_phrase in steps[1], "guard phrase not in confirm step: %r" % steps[1])
    e1_pat = "is '%s' -- if it is not" % gval
    _assert(e1_pat in text, "P4 card E1 guard-fragment pattern missing")
    polarity = "positive"   # E1: else-path guard fragment; operative condition positive.

    then_fx, else_fx = _cond_effect_shapes(schema_key, nm)
    nodes, nid = [], 0

    def add(op, status, evidence_field, evidence_span, args=None, deps=None):
        nonlocal nid
        nid += 1
        node = {"id": "n%d" % nid, "op": op, "status": status,
                "evidence": (ib.span(evidence_field, evidence_span)[0]
                             if evidence_span else None),
                "args": args or {}, "depends_on": deps or [], "commutes_with": []}
        nodes.append(node)
        return node["id"]

    n1 = add("read", "present", "nodes.read", clip_words(steps[0]),
             args={"target": "subject_row"})
    step1_s, _, _ = locate(text, steps[1])
    n2 = add("branch", "present", "nodes.branch", clip_words(steps[1]), deps=[n1],
             args={"predicate": {
                 "attribute": ib.f("predicate.attribute", "present", gfield, gfield,
                                   after=step1_s),
                 "op": ib.f("predicate.op", "present", "==", guard_phrase, after=step1_s),
                 "value": ib.f("predicate.value", "present", gval, "'%s'" % gval,
                               after=step1_s),
                 "polarity": ib.f("predicate.polarity", "present", polarity, guard_phrase,
                                  after=step1_s)},
                 "then_effects": then_fx, "else_effects": else_fx})
    if nm:
        n3 = add("write", "absent", "nodes.archive", steps[2], deps=[n2],
                 args={"action": "archive", "target": "audit_sink",
                       "value": "archive copy of the row"})
    else:
        n3 = add("write", "present", "nodes.archive", clip_words(steps[2]), deps=[n2],
                 args={"action": "archive", "target": "audit_sink",
                       "value": "archive copy of the row"})
    n4 = add("write", "present", "nodes.delete_children", clip_words(steps[3]), deps=[n3],
             args={"action": "delete", "target": "child_set", "value": "all linked rows"})
    n5 = add("write", "present", "nodes.delete_parent", clip_words(steps[4]), deps=[n4],
             args={"action": "delete", "target": "subject_row",
                   "value": "the %s itself" % ROW_WORD[schema_key]})
    add("verify", "present", "nodes.verify", steps[5], args={"target": "subject_row"},
        deps=[n5])
    ir["nodes"] = nodes
    ir["termination"] = {"status": "present", "evidence": ib.span("termination", steps[5])[0]}
    return ir, ib.ev, {"value_symbolic": False, "value_mode": "string"}
