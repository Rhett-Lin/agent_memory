"""mint_p2x.py — P2 (two_row_transfer) projections for the SFT2 production mint.

Frozen P2 conventions (clause-table ground truth mirrors build_inv_transfer /
build_cal_move_headcount / p2_roles verbatim; see DATA_QC.md decision D1):
  * roles source/destination: surfaces are the text's own row descriptors
    ("warehouse 'east'" / "'morning' session" in instructions; the instantiated
    phrase in cards); the near-miss direction flip is carried ONLY by the
    renderer's row swap — the projection reads src/dst from program_params.
  * composite guard => ONE branch node. Predicate = the source-side keep bound:
    attribute = stated unit word ("units"/"attendees" in instructions; goal-word
    "stock level"/"headcount" in cards), op ">=" (audit membership {>=,<=}),
    value = min_keep numeric iff the digits occur in the guard clause
    (word-boundary), else the symbolic min_text. The destination-side cap bound
    stays inside the branch node evidence (full guard clip) — phi_ir/v0 has no
    conjunction construct (documented decision D1).
  * effects: then = move-amount pair {source: "subtract the amount",
    destination: "add the amount"}; else = report-only ("guard violation;
    nothing moved") — textually stated in both kinds, sign-free.
  * commutation: read pair commutes ONLY where the text says "(either order)"
    (P2 cards step 0); instructions never state it -> no commutes_with.
  * numeric-printing card lever: min_text/cap_text substituted by str(min_keep)/
    str(cap) before render; label flips via statedness probe.
Numeric cap for cal_move_headcount is the SOURCE SIBLING's cap_dst (meta), i.e.
the same instance whose roles are rendered — state-consistent by construction.
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

ATTR_WORD = {"inv_transfer": "units", "cal_move_headcount": "attendees"}
CARD_ATTR_WORD = {"inv_transfer": "stock level", "cal_move_headcount": "headcount"}
MIN_TEXT = {"inv_transfer": "the minimum keep level", "cal_move_headcount": "the minimum floor"}
CAP_TEXT = {"inv_transfer": "its capacity", "cal_move_headcount": "its room capacity"}
EFFECTS_THEN = [{"action": "move", "target": "source", "value": "subtract the amount"},
                {"action": "move", "target": "destination", "value": "add the amount"}]
EFFECTS_ELSE = [{"action": "report", "target": "guard", "value": "guard violation; nothing moved"}]


def move_line(schema_key, inst):
    pp, meta = inst["program_params"], inst["meta"]
    if schema_key == "inv_transfer":
        return ("move %d units of SKU %s from warehouse '%s' to warehouse '%s'"
                % (meta["amount"], meta["sku"], meta["src_wh"], meta["dst_wh"]))
    return ("move %d attendees of '%s' from the %s session to the %s session"
            % (meta["amount"], meta["title"], meta["src_slot"], meta["dst_slot"]))


def guard_clause(schema_key, inst, style):
    """The exact guard sentence fragment the renderer interpolates (from z)."""
    meta = inst["meta"]
    inv = schema_key == "inv_transfer"
    if inv:
        src, dst, mn, cp = meta["src_wh"], meta["dst_wh"], meta["min_keep"], meta["cap"]
        q = "'%s'"
    else:
        src, dst, mn, cp = meta["src_slot"], meta["dst_slot"], meta["min_keep"], meta["cap_dst"]
        q = "%s"
    if style == 0:
        return ("The %s row must keep at least %d units afterwards; the %s side must not exceed %d."
                % (q % src, mn, q % dst, cp)) if inv else \
               ("The %s session must keep at least %d attendees afterwards; the %s session's "
                "headcount must not exceed its capacity (%d)." % (src, mn, dst, cp))
    if style == 1:
        return ("Guard: %s must stay at %d or more after the move; %s may not go over %d."
                % (q % src, mn, q % dst, cp)) if inv else \
               ("Guard: %s stays at %d+; %s must not exceed capacity (%d)." % (src, mn, dst, cp))
    return ("Guard: %s >= %d after the move; %s <= %d."
            % (q % src, mn, q % dst, cp)) if inv else \
           ("Guard: %s >= %d after the move; %s <= capacity %d." % (src, mn, dst, cp))


def _evidence_value(schema_key, inst, style):
    mn = inst["meta"]["min_keep"]
    if style == 0:
        return "at least", "at least %d" % mn
    if style == 1:
        return ("or more", "at %d or more" % mn) if schema_key == "inv_transfer" \
            else ("+", "at %d+" % mn)
    return ">=", ">= %d" % mn


def project_instruction(schema_key, inst, style):
    text = inst["instruction"]
    _assert("\nNote: " not in text, "instruction unexpectedly padded")
    meta = inst["meta"]
    # full-text reconstruction (template-level drift check), extraction only for
    # the inv style-1 product-name slot (not recorded in meta).
    ml = move_line(schema_key, inst)
    guard = guard_clause(schema_key, inst, style)
    _assert(ml in text, "move_line not rendered: %r" % ml[:80])
    g_s, _, _ = locate(text, guard, 0, "guard clause")

    ib = C.Ib(text, core_end=len(text))
    ir = C.base_ir()
    if schema_key == "inv_transfer":
        src_ph, dst_ph = "warehouse '%s'" % meta["src_wh"], "warehouse '%s'" % meta["dst_wh"]
        src_ev, dst_ev = "from %s" % src_ph, "to %s" % dst_ph
    else:
        src_ph, dst_ph = "%s session" % meta["src_slot"], "%s session" % meta["dst_slot"]
        src_ev, dst_ev = "from the %s" % src_ph, "to the %s" % dst_ph
    ir["roles"]["source"] = {"status": "present", "surface": src_ph,
                             "evidence": ib.span("roles.source", src_ev)[0]}
    ir["roles"]["destination"] = {"status": "present", "surface": dst_ph,
                                  "evidence": ib.span("roles.destination", dst_ev)[0]}

    op_ev, val_ev = _evidence_value(schema_key, inst, style)
    _assert(C.stated_num(meta["min_keep"], guard),
            "min_keep not stated in guard clause")
    _assert(C.stated_num(meta["cap"] if schema_key == "inv_transfer" else meta["cap_dst"],
                         guard),
            "cap not stated in guard clause")
    # P2 instruction polarity follows the audit's own condition-clause cue rule
    # on the FULL rendered text (DATA_QC D1): style 0 has no cue, so the 300-char
    # fallback window contains "must not exceed" -> 'negative'; styles 1/2 cut at
    # ";" before the cap clause -> 'positive'. Frozen measurement convention.
    polarity = "negative" if C.A.NEG_RE.search(C.A.condition_clause(text)) else "positive"

    nodes, nid = [], 0

    def add(op, evidence_field, evidence_span, args=None, deps=None, commutes=None, after=0):
        nonlocal nid
        nid += 1
        node = {"id": "n%d" % nid, "op": op, "status": "present",
                "evidence": ib.span(evidence_field, evidence_span, after=after)[0],
                "args": args or {}, "depends_on": deps or [], "commutes_with": commutes or []}
        nodes.append(node)
        return node["id"]

    read_cue = {0: "Read both rows" if schema_key == "inv_transfer" else "Read both sessions",
                1: "Check the numbers first",
                2: "Read both rows"}[style]
    n1 = add("read", "nodes.read_a", read_cue, args={"target": "source"})
    n2 = add("read", "nodes.read_b", read_cue, args={"target": "destination"})
    n3 = add("branch", "nodes.branch", clip_words(guard), deps=[n1, n2],
             args={"predicate": {
                 "attribute": ib.f("predicate.attribute", "present", ATTR_WORD[schema_key],
                                   ATTR_WORD[schema_key]),
                 "op": ib.f("predicate.op", "present", ">=", op_ev, after=g_s - 1),
                 "value": ib.f("predicate.value", "present", str(meta["min_keep"]), val_ev,
                               after=g_s - 1),
                 "polarity": ib.f("predicate.polarity", "present", polarity, op_ev,
                                  after=g_s - 1)},
                 "then_effects": EFFECTS_THEN, "else_effects": EFFECTS_ELSE})
    ib.span("predicate.then_effects", clip_words(ml), after=0)
    n4 = add("write", "nodes.write_src", clip_words(ml), deps=[n3],
             args={"action": "move", "target": "source", "value": "subtract the amount"})
    wr_ev = {0: "apply both updates", 1: "do both updates", 2: "update both"}[style]
    n5 = add("write", "nodes.write_dst", wr_ev, deps=[n3],
             args={"action": "move", "target": "destination", "value": "add the amount"})
    if style == 0:
        ver_ev = "and verify"
    elif style == 1:
        ver_ev = "make sure the rows look right" if schema_key == "inv_transfer" else "then confirm"
    else:
        ver_ev = "update both, verify"
    add("verify", "nodes.verify", ver_ev, args={"target": "source and destination"},
        deps=[n4, n5])
    ir["nodes"] = nodes
    ir["termination"] = {"status": "present",
                         "evidence": ib.span("termination", ver_ev)[0]}
    return ir, ib.ev, {"value_symbolic": False, "value_mode": "numeric"}


def project_memory(schema_key, inst):
    """pi for a P2 memory card. src_inst carries "_card_text" + instantiated "roles"."""
    roles = inst["roles"]
    text, meta = inst["_card_text"], inst["meta"]
    steps = list(roles["steps"])
    _assert(len(steps) == 5, "P2 card step count != 5")
    _assert(steps[0].startswith("Read the "), "card read step: %r" % steps[0][:60])
    _assert("(either order)" in steps[0], "card read-order marker missing")
    _assert(steps[1].startswith("Check the guard: "), "card guard step: %r" % steps[1][:60])
    _assert(steps[2].startswith("Move the requested amount "),
            "card move step: %r" % steps[2][:60])
    _assert(steps[3].startswith("If the guard fails, "), "card fallback step: %r" % steps[3][:60])
    _assert(steps[4].startswith("Read both rows again and confirm"),
            "card readback step: %r" % steps[4][:60])

    ib = C.Ib(text, core_end=C.card_core_end(text))
    ir = C.base_ir()
    if schema_key == "inv_transfer":
        src_ph = "'%s' warehouse row" % meta["src_wh"]
        dst_ph = "'%s' warehouse row" % meta["dst_wh"]
    else:
        src_ph = "'%s' session" % meta["src_slot"]
        dst_ph = "'%s' session" % meta["dst_slot"]
    ir["roles"]["source"] = {"status": "present", "surface": src_ph,
                             "evidence": ib.span("roles.source", src_ph)[0]}
    ir["roles"]["destination"] = {"status": "present", "surface": dst_ph,
                                  "evidence": ib.span("roles.destination", dst_ph)[0]}

    guard = steps[1]
    mn, cp = meta["min_keep"], (meta["cap"] if schema_key == "inv_transfer" else meta["cap_dst"])
    numeric = C.stated_num(mn, guard) and C.stated_num(cp, guard)
    if numeric:
        value_val, value_span = str(mn), "at least %d" % mn
    else:
        _assert(not C.stated_num(mn, guard) and not C.stated_num(cp, guard),
                "P2 card bound digits leak in symbolic mode: %r" % guard[:100])
        value_val = value_span = MIN_TEXT[schema_key]
        _assert(CAP_TEXT[schema_key] in guard, "cap_text missing from guard step")

    nodes, nid = [], 0

    def add(op, evidence_field, evidence_span, args=None, deps=None, commutes=None):
        nonlocal nid
        nid += 1
        node = {"id": "n%d" % nid, "op": op, "status": "present",
                "evidence": ib.span(evidence_field, evidence_span)[0],
                "args": args or {}, "depends_on": deps or [], "commutes_with": commutes or []}
        nodes.append(node)
        return node["id"]

    n1 = add("read", "nodes.read_a", clip_words(steps[0]), args={"target": "source"})
    n2 = add("read", "nodes.read_b", clip_words(steps[0]), args={"target": "destination"},
             commutes=[n1])
    nodes[0]["commutes_with"] = [n2]
    n3 = add("branch", "nodes.branch", clip_words(guard), deps=[n1, n2],
             args={"predicate": {
                 "attribute": ib.f("predicate.attribute", "present", CARD_ATTR_WORD[schema_key],
                                   "keep at least"),
                 "op": ib.f("predicate.op", "present", ">=", "at least"),
                 "value": ib.f("predicate.value", "present", value_val, value_span),
                 "polarity": ib.f("predicate.polarity", "present", "positive", "at least")},
                 "then_effects": EFFECTS_THEN, "else_effects": EFFECTS_ELSE})
    n4 = add("write", "nodes.write_src", "subtract the amount from the %s" % src_ph, deps=[n3],
             args={"action": "move", "target": "source", "value": "subtract the amount"})
    ib.span("predicate.then_effects", steps[2].split(": ", 1)[1].split(" and add")[0]
            if ": " in steps[2] else steps[2])
    n5 = add("write", "nodes.write_dst", "add it to the %s" % dst_ph, deps=[n3],
             args={"action": "move", "target": "destination", "value": "add the amount"})
    ib.span("predicate.else_effects", clip_words(steps[3]))
    add("verify", "nodes.verify", steps[4], args={"target": "source and destination"},
        deps=[n4, n5])
    ir["nodes"] = nodes
    ir["termination"] = {"status": "present", "evidence": ib.span("termination", steps[4])[0]}
    return ir, ib.ev, {"value_symbolic": not numeric,
                       "value_mode": "numeric" if numeric else "symbolic"}
