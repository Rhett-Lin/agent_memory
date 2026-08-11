"""Pinned synthetic fixtures for S2-rc1 (test_s2.py).

Every fixture is hand-written, NON-benchmark: no text, entity, or structure is
copied from pairs.jsonl / canonical_sft.jsonl. Verdicts are pinned under the FROZEN
rc1 rules in S2_SPEC.md — no audit-eligibility indirection exists anymore (the
SFT-era table is hardwired). Fixture ids follow S2_SPEC.md section 15.

Run: python test_s2.py  (stdlib unittest; CPU only; deterministic)
"""
import unittest

import s2_comparator as K

ROLES = list(K._ROLES)


def role(status, surface=None, ev=None):
    return {"status": status, "surface": surface, "evidence": ev}


def F(st, v, ev):
    return {"status": st, "value": v, "evidence": ev}


def mknode(i, op, ev, deps=None, status="present", target=None, over=None,
           function=None, action=None, value=None, predicate=None,
           then_effects=None, else_effects=None):
    return {"id": i, "op": op, "status": status, "evidence": ev,
            "args": {"target": target, "over": over, "function": function,
                     "action": action, "value": value, "predicate": predicate,
                     "then_effects": then_effects, "else_effects": else_effects},
            "depends_on": deps or [], "commutes_with": []}


def pred(attr, op, val, pev="policy clause", polarity="positive", attr_ev=None):
    """Branch predicate. attr_ev lets a fixture put a *different* verbatim
    evidence span on the attribute than its value (needed by F3/F5)."""
    return {"attribute": F("present", attr, attr if attr_ev is None else attr_ev),
            "op": F("present", op, pev),
            "value": F("present", val, val),
            "polarity": F("present", polarity, pev)}


def eff(a, t, v):
    return {"action": a, "target": t, "value": v}


def base_roles(present=()):
    r = {x: role("absent") for x in ROLES}
    for x in present:
        r[x] = role("present", f"the {x} entity", f"{x} evidence span")
    return r


def ir_from(nodes, roles=None, term=("present", "finish evidence span")):
    """Assemble (ir, text) so every present-status evidence string is verbatim in
    the synthesized text (keeps certificate clauses 3-4 green)."""
    frag_roles = roles or base_roles()
    evs = [n["evidence"] for n in nodes if n.get("evidence")]
    for n in nodes:  # predicate subfield evidences must also be verbatim in text
        p = (n.get("args") or {}).get("predicate") or {}
        evs += [w["evidence"] for w in p.values()
                if isinstance(w, dict) and w.get("status") == "present"
                and w.get("evidence")]
    evs += [rv["evidence"] for rv in frag_roles.values()
            if rv["status"] == "present" and rv["evidence"]]
    if term[1]:
        evs.append(term[1])
    text = " . ".join(evs)
    return {"schema": "phi_ir/v0", "roles": frag_roles,
            "nodes": nodes,
            "termination": {"status": term[0], "evidence": term[1]}}, text


def std_branch_nodes(op=">", then=None, els=None, val="5", attr="count",
                     attr_ev=None, read_ev="read evidence span"):
    return [mknode("n1", "read", read_ev, target="subject_row"),
            mknode("n2", "branch", "branch evidence span", deps=["n1"],
                   predicate=pred(attr, op, val, attr_ev=attr_ev),
                   then_effects=then or [eff("set", "subject_row", "high")],
                   else_effects=els or [eff("set", "subject_row", "low")]),
            mknode("n3", "verify", "verify evidence span", deps=["n2"],
                   target="subject_row")]


def std_pair(op=">", val="5", then=None, els=None, roles=("subject_row",),
             attr="count", attr_ev=None, read_ev="read evidence span"):
    return ir_from(std_branch_nodes(op, then, els, val, attr, attr_ev, read_ev),
                   base_roles(roles))


def codes(v):
    return {r["code"]: r["level"] for r in v["reasons"]}


def reason(v, code):
    for r in v["reasons"]:
        if r["code"] == code:
            return r
    return None


def cmp(ir_i, txt_i, ir_m, txt_m):
    return K.compare(ir_i, txt_i, ir_m, txt_m)


class TestS2(unittest.TestCase):

    def assertNoContradict(self, v):
        bad = [r for r in v["reasons"] if r["level"] == "contradict"]
        self.assertEqual(bad, [], f"unexpected contradictions: {bad}")

    # ---- F1: identical full pair -> match (positive control) ----
    def test_F1_identical_programs_match(self):
        i, ti = std_pair()
        m, tm = std_pair()
        v = cmp(i, ti, m, tm)
        self.assertEqual(v["verdict"], "match", v["reasons"])
        self.assertEqual(v["rule_version"], "s2-rc1")
        self.assertEqual(v["components"]["predicate"]["level"], "note")

    # ---- F2: dual-tokcov ACCEPT via cross-anchor token intersection ----
    def test_F2_tokcov_accept_cross_anchor(self):
        i, ti = std_pair(attr="complaint count")
        m, tm = std_pair(attr="complaint tally")
        v = cmp(i, ti, m, tm)
        self.assertEqual(v["verdict"], "match", v["reasons"])
        r = reason(v, "ATTR_ANCHOR_ALIGNED")
        self.assertIsNotNone(r)
        self.assertTrue(r["probe"]["cross_anchor"])
        self.assertEqual(r["probe"]["shared_tokens"], ["complaint"])

    # ---- F3/F3b: dual-tokcov ACCEPT via cross-text coverage, and the
    #      verbatim fallback is a strict subset (tokcov superset separation) ----
    def test_F3_tokcov_accept_cross_text_verbatim_subset(self):
        # instruction attr "stock level"; memory attr "units" whose own text
        # mentions "stock" and "level" only NON-contiguously (tokcov accept,
        # contiguous-verbatim fallback rejects -> tokcov is the superset).
        i, ti = std_pair(attr="stock level")
        m, tm = std_pair(attr="units", attr_ev="the units span",
                         read_ev="review the stock table keep level rows")
        v = cmp(i, ti, m, tm)
        self.assertEqual(v["verdict"], "match", v["reasons"])
        r = reason(v, "ATTR_ANCHOR_ALIGNED")
        self.assertIsNotNone(r)
        self.assertTrue(r["probe"]["aligned_tokcov"])
        self.assertTrue(r["probe"]["cross_text_i_in_m"])
        self.assertFalse(r["probe"]["cross_anchor"])
        self.assertFalse(r["probe"]["aligned_verbatim"])

    # ---- F4(+R1-F4b): dual-tokcov REJECT, both sides text-faithful ----
    def test_F4_tokcov_reject_faithful_cross_anchor(self):
        i, ti = std_pair(attr="complaint count")
        m, tm = std_pair(attr="seats booked")
        v = cmp(i, ti, m, tm)
        self.assertEqual(v["verdict"], "unknown")
        r = reason(v, "ATTR_ANCHOR_CROSS")
        self.assertIsNotNone(r)
        self.assertEqual(r["level"], "unknown")
        self.assertTrue(r["probe"]["faith_i"])   # rc2-(b) precondition flags:
        self.assertTrue(r["probe"]["faith_m"])   # under the hardened reading this
        self.assertFalse(r["probe"]["aligned_tokcov"])  # exact probe would flip to
        self.assertNoContradict(v)                      # contradict; rc1 abstains.
        self.assertIsNotNone(reason(v, "PRED_HALTED_NO_ANCHOR"))

    # ---- F5: dual-tokcov REJECT, one side untethered ----
    def test_F5_tokcov_reject_unfaithful_side(self):
        i, ti = std_pair(attr="count")
        m, tm = std_pair(attr="mystery parameter", attr_ev="policy clause")
        v = cmp(i, ti, m, tm)
        self.assertEqual(v["verdict"], "unknown")
        r = reason(v, "ATTR_ANCHOR_UNFAITHFUL")
        self.assertIsNotNone(r)
        self.assertFalse(r["probe"]["faith_m"])
        self.assertNoContradict(v)

    # ---- F6: NUMERIC-NUMERIC threshold mismatch under anchor -> contradict ----
    def test_F6_numeric_threshold_veto(self):
        i, ti = std_pair(val="5")
        m, tm = std_pair(val="6")
        v = cmp(i, ti, m, tm)
        self.assertEqual(v["verdict"], "contradict")
        self.assertEqual(codes(v).get("VALUE_LITERAL_MISMATCH"), "contradict")

    # ---- F7: NUMERIC vs SYMBOLIC -> UNMEAS = unknown, never a mismatch ----
    def test_F7_mark_mismatch_unmeas_unknown(self):
        i, ti = std_pair(val="0")
        m, tm = std_pair(val="none remain")
        v = cmp(i, ti, m, tm)
        self.assertEqual(v["verdict"], "unknown")
        self.assertEqual(codes(v).get("VALUE_MARK_MISMATCH_UNMEAS"), "unknown")
        self.assertNoContradict(v)          # UNMEAS never counts as mismatch

    # ---- F8: SYMBOLIC vs SYMBOLIC -> UNMEAS = unknown ----
    def test_F8_symbolic_threshold_unmeas_unknown(self):
        i, ti = std_pair(val="the minimum level")
        m, tm = std_pair(val="keep floor")
        v = cmp(i, ti, m, tm)
        self.assertEqual(v["verdict"], "unknown")
        self.assertEqual(codes(v).get("VALUE_SYMBOLIC_UNMEAS"), "unknown")
        self.assertNoContradict(v)

    # ---- F9: LITERAL-LITERAL mismatch under anchor -> contradict ----
    def test_F9_literal_threshold_veto(self):
        i, ti = std_pair(val="'cold'")
        m, tm = std_pair(val="'frozen'")
        v = cmp(i, ti, m, tm)
        self.assertEqual(v["verdict"], "contradict")
        self.assertEqual(codes(v).get("VALUE_LITERAL_MISMATCH"), "contradict")

    # ---- F10: LITERAL equal after normalization -> note, match-eligible ----
    def test_F10_literal_threshold_aligned(self):
        i, ti = std_pair(val="'cold'")
        m, tm = std_pair(val="'COLD'")
        v = cmp(i, ti, m, tm)
        self.assertEqual(v["verdict"], "match", v["reasons"])
        self.assertIn("VALUE_ALIGNED", codes(v))

    # ---- F11: no shared anchor, EQUAL literals still abstain (channel halted) ----
    def test_F11_no_anchor_equal_values_abstain(self):
        i, ti = std_pair(attr="complaint count", val="5")
        m, tm = std_pair(attr="seats booked", val="5")
        v = cmp(i, ti, m, tm)
        self.assertEqual(v["verdict"], "unknown")
        self.assertEqual(codes(v).get("ATTR_ANCHOR_CROSS"), "unknown")
        self.assertFalse([c for c in codes(v) if c.startswith("VALUE")],
                         "literal comparison without a shared anchor is forbidden")
        self.assertNoContradict(v)

    # ---- F12: ABSENT under complete(memory) -> contradiction ----
    def test_F12_required_op_missing_complete_memory_contradict(self):
        extra = mknode("n4", "write", "notify evidence span", deps=["n3"],
                       action="notify", target="audit_sink")
        i, ti = ir_from(std_branch_nodes() + [extra],
                        base_roles(("subject_row", "audit_sink")))
        m, tm = std_pair(roles=("subject_row", "audit_sink"))
        cert = K.certificate(m, tm)
        self.assertTrue(cert["complete"], cert["checks"])
        self.assertEqual(set(cert["checks"]), {
            "valid", "required_fields", "evidence_nonempty", "evidence_verbatim",
            "no_unknown_in_used_fields", "branch_populated", "connected"})
        v = cmp(i, ti, m, tm)
        self.assertEqual(v["verdict"], "contradict")
        self.assertEqual(codes(v).get("REQ_OP_MISSING_UNDER_COMPLETE:write"),
                         "contradict")

    # ---- F13: ABSENT under NOT-complete(memory) -> unknown ----
    def test_F13_required_op_missing_incomplete_memory_unknown(self):
        extra = mknode("n4", "write", "notify evidence span", deps=["n3"],
                       action="notify", target="audit_sink")
        i, ti = ir_from(std_branch_nodes() + [extra],
                        base_roles(("subject_row", "audit_sink")))
        m, tm = ir_from(std_branch_nodes(), base_roles(("subject_row", "audit_sink")),
                        term=("unknown", None))
        cert = K.certificate(m, tm)
        self.assertFalse(cert["complete"])
        self.assertFalse(cert["checks"]["no_unknown_in_used_fields"])
        v = cmp(i, ti, m, tm)
        self.assertEqual(v["verdict"], "unknown")
        self.assertEqual(codes(v).get("REQ_OP_MISSING_INCOMPLETE:write"), "unknown")
        self.assertNoContradict(v)

    # ---- F14: operator complementation + effect swap = equivalent ----
    def test_F14_complement_with_swap_match(self):
        i, ti = std_pair(op=">", then=[eff("set", "subject_row", "high")],
                         els=[eff("set", "subject_row", "low")])
        m, tm = std_pair(op="<=", then=[eff("set", "subject_row", "low")],
                         els=[eff("set", "subject_row", "high")])
        v = cmp(i, ti, m, tm)
        self.assertEqual(v["verdict"], "match", v["reasons"])
        self.assertIn("PRED_COMPLEMENT_SWAP_EQUIV", codes(v))

    # ---- F15: complement WITHOUT swap = contradiction ----
    def test_F15_complement_without_swap_contradict(self):
        i, ti = std_pair(op=">", then=[eff("set", "subject_row", "high")],
                         els=[eff("set", "subject_row", "low")])
        m, tm = std_pair(op="<=", then=[eff("set", "subject_row", "high")],
                         els=[eff("set", "subject_row", "low")])
        v = cmp(i, ti, m, tm)
        self.assertEqual(v["verdict"], "contradict")
        self.assertEqual(codes(v).get("PRED_COMPLEMENT_NO_SWAP"), "contradict")

    # ---- F16: same op, effect value mismatch -> contradict (branch_effects) ----
    def test_F16_effect_value_mismatch_contradict(self):
        i, ti = std_pair(then=[eff("set", "subject_row", "high")])
        m, tm = std_pair(then=[eff("set", "subject_row", "routine")])
        v = cmp(i, ti, m, tm)
        self.assertEqual(v["verdict"], "contradict")
        self.assertEqual(codes(v).get("PRED_EFFECT_MISMATCH"), "contradict")

    # ---- F17: effect target-role conflict -> contradict ----
    def test_F17_effect_target_conflict_contradict(self):
        i, ti = std_pair(then=[eff("set", "subject_row", "high")])
        m, tm = std_pair(then=[eff("set", "audit_sink", "high")])
        v = cmp(i, ti, m, tm)
        self.assertEqual(v["verdict"], "contradict")
        self.assertEqual(codes(v).get("PRED_EFFECT_MISMATCH"), "contradict")

    # ---- F18: operator mismatch beyond complementation -> contradict (pred_op) ----
    def test_F18_op_mismatch_non_complement_contradict(self):
        i, ti = std_pair(op=">")
        m, tm = std_pair(op=">=")
        v = cmp(i, ti, m, tm)
        self.assertEqual(v["verdict"], "contradict")
        self.assertEqual(codes(v).get("PRED_OP_MISMATCH"), "contradict")

    # ---- F19: extra effectful op in memory -> contradict ----
    def test_F19_extra_effectful_op_contradict(self):
        i, ti = std_pair()
        extra = mknode("n4", "write", "archive evidence span", deps=["n3"],
                       action="archive", target="subject_row")
        m, tm = ir_from(std_branch_nodes() + [extra], base_roles(("subject_row",)))
        v = cmp(i, ti, m, tm)
        self.assertEqual(v["verdict"], "contradict")
        self.assertEqual(codes(v).get("EXTRA_EFFECTFUL_OP:write:archive"), "contradict")

    # ---- F20: benign extras (read / verify / report) never gate ----
    def test_F20_extra_benign_class_match(self):
        i, ti = std_pair()
        more = [mknode("n4", "read", "extra read evidence span", deps=["n3"],
                       target="subject_row"),
                mknode("n5", "verify", "extra verify evidence span", deps=["n4"],
                       target="subject_row"),
                mknode("n6", "write", "report evidence span", deps=["n5"],
                       action="report", target="subject_row")]
        m, tm = ir_from(std_branch_nodes() + more, base_roles(("subject_row",)))
        v = cmp(i, ti, m, tm)
        self.assertEqual(v["verdict"], "match", v["reasons"])
        for c in ("EXTRA_BENIGN:read", "EXTRA_BENIGN:verify",
                  "EXTRA_BENIGN:write:report"):
            self.assertEqual(codes(v).get(c), "benign", c)

    # ---- F21: P2 direction reversal -> contradict (HARD under SFT eligibility) ----
    def test_F21_src_dest_reversal_contradict(self):
        def transfer_ir(fr, to):
            nodes = [mknode("n1", "read", "read evidence span", target="source"),
                     mknode("n2", "write", "move evidence span", deps=["n1"],
                            action="move", value=f"10 units from {fr} to {to}"),
                     mknode("n3", "verify", "verify evidence span", deps=["n2"],
                            target="destination")]
            return ir_from(nodes, base_roles(("source", "destination")))
        i, ti = transfer_ir("the source entity", "the destination entity")
        m, tm = transfer_ir("the destination entity", "the source entity")
        v = cmp(i, ti, m, tm)
        self.assertEqual(v["verdict"], "contradict")
        self.assertEqual(codes(v).get("SRC_DEST_REVERSAL"), "contradict")

    # ---- F22: capture-before-delete: violation -> contradict; ok-order -> match ----
    def _cap_ir(self, order):
        if order == "ok":
            seq = [("n2", "write", "archive evidence span", "archive"),
                   ("n3", "write", "delete evidence span", "delete")]
        else:
            seq = [("n2", "write", "delete evidence span", "delete"),
                   ("n3", "write", "archive evidence span", "archive")]
        nodes = [mknode("n1", "read", "read evidence span", target="subject_row")]
        prev = "n1"
        for nid, op, ev, act in seq:
            nodes.append(mknode(nid, op, ev, deps=[prev], action=act,
                                target="subject_row"))
            prev = nid
        nodes.append(mknode("n4", "verify", "verify evidence span",
                            deps=[prev], target="subject_row"))
        return ir_from(nodes, base_roles(("subject_row",)))

    def test_F22_capture_after_delete_contradict_and_ok_match(self):
        i, ti = self._cap_ir("ok")
        m, tm = self._cap_ir("reversed")
        v = cmp(i, ti, m, tm)
        self.assertEqual(v["verdict"], "contradict")
        self.assertEqual(codes(v).get("ORDER_CAPTURE_AFTER_DELETE"), "contradict")
        i2, ti2 = self._cap_ir("ok")
        m2, tm2 = self._cap_ir("ok")
        v2 = cmp(i2, ti2, m2, tm2)
        self.assertEqual(v2["verdict"], "match", v2["reasons"])
        self.assertIn("ORDER_CAPTURE_BEFORE_DELETE_OK", codes(v2))

    # ---- F23: invalid IR(s) -> unknown (memory-only, instruction-only, both) ----
    def test_F23_invalid_ir_unknown(self):
        i, ti = std_pair()
        m, tm = std_pair()
        m["schema"] = "phi_ir/v999"
        self.assertEqual(cmp(i, ti, m, tm)["verdict"], "unknown")
        self.assertEqual(codes(cmp(i, ti, m, tm)).get("IR_INVALID"), "unknown")
        i2, ti2 = std_pair()
        m2, tm2 = std_pair()
        i2["schema"] = "phi_ir/v999"
        self.assertEqual(cmp(i2, ti2, m2, tm2)["verdict"], "unknown")
        i3, ti3 = std_pair()
        m3, tm3 = std_pair()
        i3["schema"] = "phi_ir/v999"
        m3["schema"] = "phi_ir/v999"
        v = cmp(i3, ti3, m3, tm3)
        self.assertEqual(v["verdict"], "unknown")
        self.assertEqual(codes(v).get("IR_INVALID"), "unknown")
        self.assertNoContradict(v)

    # ---- F24: termination: halt split -> contradict; absent-complete -> contradict;
    #      absent-incomplete -> unknown ----
    def test_F24_termination_channels(self):
        i, ti = std_pair()
        m, tm = ir_from(std_branch_nodes(), base_roles(("subject_row",)),
                        term=("present", "stop. do not proceed."))
        v = cmp(i, ti, m, tm)
        self.assertEqual(v["verdict"], "contradict")
        self.assertEqual(codes(v).get("TERM_INCOMPATIBLE"), "contradict")
        m2, tm2 = ir_from(std_branch_nodes(), base_roles(("subject_row",)),
                          term=("absent", None))
        self.assertTrue(K.certificate(m2, tm2)["complete"])
        v2 = cmp(i, ti, m2, tm2)
        self.assertEqual(v2["verdict"], "contradict")
        self.assertEqual(codes(v2).get("TERM_ABSENT_UNDER_COMPLETE"), "contradict")
        roles3 = base_roles(("subject_row",))
        roles3["child_set"] = role("unknown")     # breaks memory completeness only
        m3, tm3 = ir_from(std_branch_nodes(), roles3, term=("absent", None))
        self.assertFalse(K.certificate(m3, tm3)["complete"])
        v3 = cmp(i, ti, m3, tm3)
        self.assertEqual(v3["verdict"], "unknown")
        self.assertEqual(codes(v3).get("TERM_ABSENT_INCOMPLETE"), "unknown")
        self.assertNoContradict(v3)

    # ---- F25: scope mismatch is note-only, zero verdict influence (R3) ----
    def test_F25_scope_excluded_note_only_match(self):
        def agg_ir(over):
            nodes = [mknode("n1", "aggregate", "aggregate evidence span",
                            over=over, function="count",
                            value=f"rows of {over} passing the filter"),
                     mknode("n2", "verify", "verify evidence span", deps=["n1"],
                            target="subject_row")]
            return ir_from(nodes, base_roles(("subject_row", "child_set",
                                              "audit_sink")))
        i, ti = agg_ir("child_set")
        m, tm = agg_ir("audit_sink")
        v = cmp(i, ti, m, tm)
        self.assertEqual(v["verdict"], "match", v["reasons"])   # EXCLUDED never gates
        self.assertEqual(codes(v).get("SCOPE_MISMATCH_NOTE"), "note")
        self.assertIn("SCOPE_OVER_NOTE", codes(v))
        self.assertIn("SCOPE_FILTER_NOTE", codes(v))
        self.assertNoContradict(v)

    # ---- F26: aggregate function mismatch (both explicit) -> contradict ----
    def test_F26_agg_fn_mismatch_contradict(self):
        def agg_ir(fn):
            nodes = [mknode("n1", "aggregate", "aggregate evidence span",
                            over="child_set", function=fn),
                     mknode("n2", "verify", "verify evidence span", deps=["n1"],
                            target="subject_row")]
            return ir_from(nodes, base_roles(("subject_row", "child_set")))
        i, ti = agg_ir("count")
        m, tm = agg_ir("sum")
        v = cmp(i, ti, m, tm)
        self.assertEqual(v["verdict"], "contradict")
        self.assertEqual(codes(v).get("AGG_FN_MISMATCH"), "contradict")

    # ---- F27: polarity divergence is metadata / note-only (R2) ----
    def test_F27_polarity_divergent_metadata_match(self):
        i, ti = std_pair()
        m, tm = std_pair()
        m["nodes"][1]["args"]["predicate"]["polarity"] = F("present", "negative",
                                                           "policy clause")
        v = cmp(i, ti, m, tm)
        self.assertEqual(v["verdict"], "match", v["reasons"])
        self.assertEqual(codes(v).get("POLARITY_DIVERGENT"), "note")
        self.assertNoContradict(v)

    # ---- F28: vacuity guards -> unknown ----
    def test_F28_vacuity_guards_unknown(self):
        dead = [mknode("n1", "read", None, status="absent", target="subject_row"),
                mknode("n2", "verify", None, status="absent", deps=["n1"],
                       target="subject_row")]
        i_void, ti_void = ir_from(dead, base_roles(), term=("absent", None))
        m_ok, tm_ok = std_pair()
        v = cmp(i_void, ti_void, m_ok, tm_ok)
        self.assertEqual(v["verdict"], "unknown")
        self.assertEqual(codes(v).get("VACUOUS_INSTRUCTION"), "unknown")
        i_ok, ti_ok = std_pair()
        m_void, tm_void = ir_from(
            [mknode("n1", "read", None, status="absent", target="subject_row")],
            base_roles(), term=("absent", None))
        v2 = cmp(i_ok, ti_ok, m_void, tm_void)
        self.assertEqual(v2["verdict"], "unknown")
        self.assertEqual(codes(v2).get("VACUOUS_MEMORY"), "unknown")
        self.assertNoContradict(v2)

    # ---- F29: match-complete positive fix (kitchen sink; equivalent programs) ----
    def test_F29_kitchen_sink_positive_match(self):
        roles = base_roles(("subject_row", "audit_sink"))
        i_nodes = [
            mknode("n1", "read", "read evidence span", target="subject_row"),
            mknode("n2", "branch", "branch evidence span", deps=["n1"],
                   predicate=pred("count", ">", "5"),
                   then_effects=[eff("set", "subject_row", "high"),
                                 eff("insert", "audit_sink", "log-high")],
                   else_effects=[eff("set", "subject_row", "low")]),
            mknode("n3", "write", "report evidence span", deps=["n2"],
                   action="report", target="subject_row"),
            mknode("n4", "verify", "verify evidence span", deps=["n3"],
                   target="subject_row")]
        i, ti = ir_from(i_nodes, base_roles(("subject_row", "audit_sink")))
        m_nodes = [
            mknode("n0", "read", "extra read evidence span", target="subject_row"),
            mknode("n1", "read", "read evidence span", deps=["n0"],
                   target="subject_row"),
            mknode("n2", "branch", "branch evidence span", deps=["n1"],
                   predicate=pred("count", "<=", "5"),
                   then_effects=[eff("set", "subject_row", "low")],
                   else_effects=[eff("set", "subject_row", "high"),
                                 eff("insert", "audit_sink", "log-high")]),
            mknode("n3", "write", "report evidence span", deps=["n2"],
                   action="report", target="subject_row"),
            mknode("n4", "verify", "verify evidence span", deps=["n3"],
                   target="subject_row"),
            mknode("n5", "verify", "second verify evidence span", deps=["n4"],
                   target="subject_row")]
        m, tm = ir_from(m_nodes, base_roles(("subject_row", "audit_sink")))
        v = cmp(i, ti, m, tm)
        self.assertEqual(v["verdict"], "match", v["reasons"])
        self.assertIn("PRED_COMPLEMENT_SWAP_EQUIV", codes(v))
        for c in ("EXTRA_BENIGN:read", "EXTRA_BENIGN:verify", "TERM_ALIGNED",
                  "ATTR_ANCHOR_ALIGNED", "VALUE_ALIGNED",
                  "ROLE_ALIGNED:subject_row", "ROLE_ALIGNED:audit_sink"):
            self.assertIn(c, codes(v), c)
        self.assertEqual(v["components"]["extras"]["level"], "benign")


if __name__ == "__main__":
    unittest.main(verbosity=2)
