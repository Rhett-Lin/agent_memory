"""Synthetic unit tests for comparator v0. NOT benchmark texts: every mini-pair is
hand-written. Verdicts are pinned under the LIVE audit-gated eligibility map
(audit_expanded/field_metrics.json at freeze time): pred_op=positive_only, every
other scored field excluded (demoted to unknown), branch_presence hard.
Two tests additionally pin all-hard mode to lock the un-demoted semantics.
"""
import unittest

import comparator as K

ROLES = list(K._ROLES)
# mirrors audit_expanded/field_metrics.json veto_eligibility at freeze time
AUDIT_ELIG = {"pred_attribute": "excluded", "pred_op": "positive_only",
              "pred_value": "excluded", "pred_polarity": "excluded",
              "pred_all": "excluded", "branch_effects": "excluded",
              "direction": "excluded", "scope": "excluded",
              "archive_capture": "excluded", "roles_required": "excluded",
              "termination": "excluded", "branch_presence": "hard"}
HARD_ELIG = {f: "hard" for f in AUDIT_ELIG}


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


def pred(attr, op, val, pev="policy clause", polarity="positive"):
    return {"attribute": F("present", attr, attr),
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


def std_branch_nodes(op=">", then=None, els=None, val="5"):
    return [mknode("n1", "read", "read evidence span", target="subject_row"),
            mknode("n2", "branch", "branch evidence span", deps=["n1"],
                   predicate=pred("count", op, val, pev="policy clause"),
                   then_effects=then or [eff("set", "subject_row", "high")],
                   else_effects=els or [eff("set", "subject_row", "low")]),
            mknode("n3", "verify", "verify evidence span", deps=["n2"],
                   target="subject_row")]


def std_pair(op=">", val="5", then=None, els=None, roles=("subject_row",)):
    return ir_from(std_branch_nodes(op, then, els, val), base_roles(roles))


def codes(v):
    return {r["code"]: r["level"] for r in v["reasons"]}


def cmp(ir_i, txt_i, ir_m, txt_m, elig=AUDIT_ELIG):
    return K.compare(ir_i, txt_i, ir_m, txt_m, eligibility=elig)


class TestComparator(unittest.TestCase):

    def test_01_identical_programs_match(self):
        i, ti = std_pair()
        m, tm = std_pair()
        v = cmp(i, ti, m, tm)
        self.assertEqual(v["verdict"], "match", v["reasons"])

    def test_02_complement_with_swap_match(self):
        i, ti = std_pair(op=">", then=[eff("set", "subject_row", "high")],
                         els=[eff("set", "subject_row", "low")])
        m, tm = std_pair(op="<=", then=[eff("set", "subject_row", "low")],
                         els=[eff("set", "subject_row", "high")])
        v = cmp(i, ti, m, tm)
        self.assertEqual(v["verdict"], "match", v["reasons"])
        self.assertIn("PRED_COMPLEMENT_SWAP_EQUIV", codes(v))

    def test_03_complement_without_swap_contradict(self):
        i, ti = std_pair(op=">", then=[eff("set", "subject_row", "high")],
                         els=[eff("set", "subject_row", "low")])
        m, tm = std_pair(op="<=", then=[eff("set", "subject_row", "high")],
                         els=[eff("set", "subject_row", "low")])
        v = cmp(i, ti, m, tm)                # audit: branch_effects excluded
        self.assertEqual(v["verdict"], "unknown")
        self.assertEqual(codes(v).get("PRED_COMPLEMENT_NO_SWAP"), "unknown")
        vh = cmp(i, ti, m, tm, elig=HARD_ELIG)   # hard mode: still a veto
        self.assertEqual(vh["verdict"], "contradict")
        self.assertEqual(codes(vh).get("PRED_COMPLEMENT_NO_SWAP"), "contradict")

    def test_04_extra_effectful_op_contradict(self):
        i, ti = std_pair()
        extra = mknode("n4", "write", "archive evidence span", deps=["n3"],
                       action="archive", target="subject_row")
        m, tm = ir_from(std_branch_nodes() + [extra], base_roles(("subject_row",)))
        v = cmp(i, ti, m, tm)
        self.assertEqual(v["verdict"], "contradict")
        self.assertTrue(any(c.startswith("EXTRA_EFFECTFUL_OP") and lv == "contradict"
                            for c, lv in codes(v).items()))

    def test_05_extra_benign_read_match(self):
        i, ti = std_pair()
        extra = mknode("n4", "write", "report evidence span", deps=["n3"],
                       action="report", target="subject_row")
        m, tm = ir_from(std_branch_nodes() + [extra], base_roles(("subject_row",)))
        v = cmp(i, ti, m, tm)
        self.assertEqual(v["verdict"], "match", v["reasons"])

    def test_06_required_op_missing_complete_memory_contradict(self):
        extra = mknode("n4", "write", "notify evidence span", deps=["n3"],
                       action="notify", target="audit_sink")
        i, ti = ir_from(std_branch_nodes() + [extra],
                        base_roles(("subject_row", "audit_sink")))
        m, tm = std_pair(roles=("subject_row", "audit_sink"))
        self.assertTrue(m and K.certificate(m, tm)["complete"])
        v = cmp(i, ti, m, tm)
        self.assertEqual(v["verdict"], "contradict")
        self.assertEqual(codes(v).get("REQ_OP_MISSING_UNDER_COMPLETE:write"),
                         "contradict")

    def test_07_required_op_missing_incomplete_memory_unknown(self):
        extra = mknode("n4", "write", "notify evidence span", deps=["n3"],
                       action="notify", target="audit_sink")
        i, ti = ir_from(std_branch_nodes() + [extra],
                        base_roles(("subject_row", "audit_sink")))
        # memory NOT complete: termination unknown -> absent clause softens
        m, tm = ir_from(std_branch_nodes(), base_roles(("subject_row", "audit_sink")),
                        term=("unknown", None))
        self.assertFalse(K.certificate(m, tm)["complete"])
        v = cmp(i, ti, m, tm)
        self.assertEqual(v["verdict"], "unknown")
        self.assertEqual(codes(v).get("REQ_OP_MISSING_INCOMPLETE:write"), "unknown")

    def test_08_invalid_memory_unknown(self):
        i, ti = std_pair()
        m, tm = std_pair()
        m["schema"] = "phi_ir/v999"          # structural invalidity
        v = cmp(i, ti, m, tm)
        self.assertEqual(v["verdict"], "unknown")
        self.assertEqual(codes(v).get("IR_INVALID"), "unknown")

    def test_09_threshold_anchor_differ_soft_unknown_audit_mode(self):
        i, ti = std_pair(val="5")
        m, tm = std_pair(val="6")            # same anchor, different literal
        v = cmp(i, ti, m, tm)                # audit: pred_value excluded -> unknown
        self.assertEqual(v["verdict"], "unknown")
        self.assertEqual(codes(v).get("PRED_THRESHOLD_LITERAL_MISMATCH"), "unknown")
        vh = cmp(i, ti, m, tm, elig=HARD_ELIG)   # hard mode: still a veto
        self.assertEqual(vh["verdict"], "contradict")
        self.assertEqual(codes(vh).get("PRED_THRESHOLD_LITERAL_MISMATCH"),
                         "contradict")

    def test_10_threshold_no_anchor_unknown(self):
        i, ti = std_pair(val="5")
        m, tm = ir_from(std_branch_nodes(val="5"), base_roles(("subject_row",)))
        # rewrite memory attribute to a non-aligning parameter (cross-domain)
        m["nodes"][1]["args"]["predicate"]["attribute"] = F("present", "seats booked",
                                                            "seats booked")
        v = cmp(i, ti, m, tm)
        self.assertEqual(v["verdict"], "unknown")
        self.assertEqual(codes(v).get("PRED_THRESHOLD_NO_ANCHOR"), "unknown")

    def test_11_src_dest_reversal_soft_unknown_audit_hard_contradict(self):
        def transfer_ir(fr, to):
            nodes = [mknode("n1", "read", "read evidence span", target="source"),
                     mknode("n2", "write", "move evidence span", deps=["n1"],
                            action="move", value=f"10 units from {fr} to {to}"),
                     mknode("n3", "verify", "verify evidence span", deps=["n2"],
                            target="destination")]
            return ir_from(nodes, base_roles(("source", "destination")))
        i, ti = transfer_ir("the source entity", "the destination entity")
        m, tm = transfer_ir("the destination entity", "the source entity")
        v = cmp(i, ti, m, tm)                # audit: direction excluded -> unknown
        self.assertEqual(v["verdict"], "unknown")
        self.assertEqual(codes(v).get("SRC_DEST_REVERSAL"), "unknown")
        vh = cmp(i, ti, m, tm, elig=HARD_ELIG)
        self.assertEqual(vh["verdict"], "contradict")
        self.assertEqual(codes(vh).get("SRC_DEST_REVERSAL"), "contradict")

    def test_12_capture_after_delete_soft_unknown(self):
        def cap_ir(order):
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
        i, ti = cap_ir("ok")
        m, tm = cap_ir("reversed")
        v = cmp(i, ti, m, tm)                # audit: archive_capture excluded
        self.assertEqual(v["verdict"], "unknown")
        self.assertEqual(codes(v).get("ORDER_CAPTURE_AFTER_DELETE"), "unknown")

    def test_13_agg_fn_mismatch_contradict(self):
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

    def test_14_polarity_only_difference_match(self):
        i, ti = std_pair()
        m, tm = std_pair()
        m["nodes"][1]["args"]["predicate"]["polarity"] = F("present", "negative",
                                                           "policy clause")
        v = cmp(i, ti, m, tm)
        self.assertEqual(v["verdict"], "match", v["reasons"])  # polarity = metadata

    def test_15_op_mismatch_non_complement_contradict(self):
        i, ti = std_pair(op=">")
        m, tm = std_pair(op=">=")
        v = cmp(i, ti, m, tm)
        self.assertEqual(v["verdict"], "contradict")
        self.assertEqual(codes(v).get("PRED_OP_MISMATCH"), "contradict")

    def test_16_scope_mismatch_soft_unknown(self):
        def agg_ir(over):
            nodes = [mknode("n1", "aggregate", "aggregate evidence span",
                            over=over, function="count"),
                     mknode("n2", "verify", "verify evidence span", deps=["n1"],
                            target="subject_row")]
            return ir_from(nodes, base_roles(("subject_row", "child_set",
                                              "audit_sink")))
        i, ti = agg_ir("child_set")
        m, tm = agg_ir("audit_sink")
        v = cmp(i, ti, m, tm)                # audit: scope excluded -> unknown
        self.assertEqual(v["verdict"], "unknown")
        self.assertEqual(codes(v).get("SCOPE_MISMATCH"), "unknown")

    def test_17_role_omitted_soft_unknown(self):
        i, ti = std_pair(roles=("subject_row", "child_set"))
        m, tm = std_pair(roles=("subject_row",))
        self.assertTrue(K.certificate(m, tm)["complete"])
        v = cmp(i, ti, m, tm)                # audit: roles_required excluded
        self.assertEqual(v["verdict"], "unknown")
        self.assertEqual(codes(v).get("ROLE_OMITTED_SOFT:child_set"), "unknown")

    def test_18_eq_ne_complement_with_swap_match(self):
        i, ti = std_pair(op="==", val="'cold'",
                         then=[eff("set", "subject_row", "ok")],
                         els=[eff("delete", "subject_row", None)])
        m, tm = std_pair(op="!=", val="'cold'",
                         then=[eff("delete", "subject_row", None)],
                         els=[eff("set", "subject_row", "ok")])
        v = cmp(i, ti, m, tm)
        self.assertEqual(v["verdict"], "match", v["reasons"])
        self.assertIn("PRED_COMPLEMENT_SWAP_EQUIV", codes(v))


if __name__ == "__main__":
    unittest.main(verbosity=2)
