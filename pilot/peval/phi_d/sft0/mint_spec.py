#!/usr/bin/env python
"""mint_spec.py — SFT-extractor data minting prototype (phi+d lane C, step 0).

Mechanical z + renderer -> (text, GOLD program-graph IR) pipeline for ONE archetype
(conditional_write / P1), end-to-end, CPU-only, deterministic, NO generator edits
(imports pilot/generate_families.py + pilot/program_dsl.py read-only) and NO model runs.

Design (see FEASIBILITY.md):
  * TEXT   : regenerated through the FROZEN generator code path (plan_families +
             build_instances_for_family + CARD_STYLES + pad_to_tokens) with the sealed
             config; every minted text is byte-compared against the sealed artifacts
             (/work1/zixuan/data/agent_memory/sealed/{tasks_sealed,memories_sealed}.jsonl).
             Byte equality is the proof that the mint is not a paraphrase of z but the
             real renderer output.
  * GOLD IR: the textually-supported PROJECTION pi(z, renderer-mode, text) into
             SPEC.md phi_ir/v0. Clause-level expectations (the exact strings the renderer
             interpolates: condition clause, cmp phrase, theta phrase, conseq/alt,
             verify cue) are reconstructed per (schema, kind, style, join_depth,
             near_miss) and HARD-ASSERTED verbatim in the rendered text. Anything the
             text does not state stays symbolic/unknown: the numeric theta from z is
             NEVER written into a label unless it literally appears in the condition
             clause (asserted bidirectionally: stated <=> numeric label).
  * EVIDENCE: every non-null evidence span is located by exact substring alignment
             (anchored where needed), is guaranteed to lie in the renderer-core region
             (before the "\nNote: " filler block that pad_to_tokens appends), and is
             shipped with offsets in `evidence_map` for audit. Soft-metric quality per
             SPEC: presence + verbatimness 100% by construction, and machine-checked.

Mints 20 pairs: families 0 (crm_escalate J1, numeric theta) and 17 (inv_overstock J2,
policy-table indirection) x {4 sibling instructions + 1 near-miss instruction,
3 A11/A01-style cards + 1 A01 card + 1 A10 cross-domain card}. Family 0's A10 card is
the fam-1 inv_overstock J1 program; family 17's A10 card is the fam-24 crm_escalate J2
program — so the 20 pairs cover both P1 domains, J1+J2, correct+near-miss programs.

Self-consistency (mint20_report.json): byte equality vs sealed, validate_ir pass, gold op
vs program cond_op, node-op sequence vs signature expansion (audit rule), roles vs
join_depth, symbolic/numeric theta policy outcome, evidence-span re-verification.

Run:  cd pilot/peval/phi_d/sft0 && PY mint_spec.py     # ~2-3 min CPU (tokenizer load)
"""

import hashlib
import json
import os
import pathlib
import random
import sys

# --- paths -----------------------------------------------------------------
HERE = pathlib.Path(__file__).resolve().parent                # pilot/peval/phi_d/sft0
PHI_D = HERE.parent                                           # pilot/peval/phi_d
PILOT = PHI_D.parent.parent                                   # pilot
SEALED = pathlib.Path("/work1/zixuan/data/agent_memory/sealed")
sys.path.insert(0, str(PILOT))
sys.path.insert(0, str(PHI_D))

os.environ.setdefault("HF_HOME", "/work1/zixuan/cache/huggingface")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import generate_families as G                                  # noqa: E402  (read-only)
from program_dsl import ARCHETYPES                             # noqa: E402  (read-only)
from common import validate_ir                                 # noqa: E402  (phi+d S0 validator)

OUT_JSONL = HERE / "mint20.jsonl"
OUT_REPORT = HERE / "mint20_report.json"

MINT_FAMILIES = [0, 17]
CARD_SLOTS = [(0, "A11"), (0, "A01"), (1, "A11"), (1, "A01"), (1, "A10")]

CMP_TEXT = {">": "above", "<=": "at or below"}
NEG_CUES = (" no ", " none ", " nobody ", " not ", " never ", " without ")


# ---------------------------------------------------------------------------
# span utilities (deterministic, assertion-first)
# ---------------------------------------------------------------------------
class MintError(RuntimeError):
    pass


def find_all(text, sub):
    out, i = [], text.find(sub)
    while i != -1:
        out.append(i)
        i = text.find(sub, i + 1)
    return out


def locate(text, span, after=0, what="span"):
    """Exact alignment: require >=1 occurrence at/after `after`; return anchored (start, end)."""
    _assert(span, "%s: empty span" % what)
    cands = [i for i in find_all(text, span) if i >= after]
    _assert(cands, "%s: span NOT FOUND (renderer drift?): %r" % (what, span[:90]))
    return cands[0], cands[0] + len(span), len(cands)


def _assert(cond, msg):
    if not cond:
        raise MintError(msg)


def _sentence_bounds(text):
    """Boundary positions: newline, or .!? followed by space/newline/end (so a '.' inside
    an e-mail or id token never splits a sentence)."""
    bounds = set()
    for i, ch in enumerate(text):
        if ch == "\n":
            bounds.add(i + 1)
        elif ch in ".!?" and (i + 1 == len(text) or text[i + 1] in " \n"):
            bounds.add(i + 1)
    return sorted(bounds)


def sentence_around(text, offset, max_words=15):
    """Expand an offset to real sentence boundaries (e-mail/id dots do not count)."""
    bounds = _sentence_bounds(text)
    lo = max([b for b in bounds if b <= offset] + [0])
    hi = min([b for b in bounds if b > offset] + [len(text)])
    sent = text[lo:hi].strip()
    _assert(len(sent.split()) <= max_words, "sentence evidence >%d words: %r" % (max_words, sent))
    start = text.find(sent)
    return sent, start, start + len(sent)


# ---------------------------------------------------------------------------
# renderer clause expectations for the two P1 schemas (asserted verbatim).
# These mirror generate_families.py build_crm_escalate / build_inv_overstock and
# p1_roles; any renderer drift breaks the mint loudly instead of mislabeling.
# ---------------------------------------------------------------------------
def p1_vocab(schema_key):
    if schema_key == "crm_escalate":
        return dict(table="customers", attr="complaint count", attr_span="the customer's complaint count",
                    conseq="set status to 'escalated' and priority_flag to 1",
                    alt="set status to 'routine' and priority_flag to 0",
                    effects_then=[{"action": "set", "target": "status", "value": "escalated"},
                                  {"action": "set", "target": "priority_flag", "value": "1"}],
                    effects_else=[{"action": "set", "target": "status", "value": "routine"},
                                  {"action": "set", "target": "priority_flag", "value": "0"}],
                    policy_table="sla_policies", policy_col="escalate_threshold",
                    j2_theta="the escalation threshold for tier '%s' in the sla_policies table (column escalate_threshold)",
                    j1_theta_card="complaint threshold stated in the request",
                    j2_theta_card="escalation threshold from the sla_policies table",
                    card_entity="the customer",
                    read_cues=["Verify the current complaint count in the database first",
                               "check the actual count before you write anything",
                               "Check the stored complaint count first"])
    if schema_key == "inv_overstock":
        return dict(table="stock", attr="on-hand quantity", attr_span="the on-hand quantity",
                    conseq="set its flag to 'markdown' and review to 1",
                    alt="set flag to 'ok' and review to 0",
                    effects_then=[{"action": "set", "target": "flag", "value": "markdown"},
                                  {"action": "set", "target": "review", "value": "1"}],
                    effects_else=[{"action": "set", "target": "flag", "value": "ok"},
                                  {"action": "set", "target": "review", "value": "0"}],
                    policy_table="inv_policies", policy_col="overstock_limit",
                    j2_theta="the overstock limit for category '%s' in the inv_policies table (column overstock_limit)",
                    j1_theta_card="overstock limit stated in the request",
                    j2_theta_card="overstock limit from the inv_policies table",
                    card_entity="the stocked item",
                    read_cues=["Verify the current quantity first",
                               "look at the real quantity before writing",
                               "Check the stored quantity first"])
    raise MintError("schema not covered by prototype: %s" % schema_key)


VERIFY_CUES = ["read the row back to confirm it", "confirm the row afterwards", "verify the row"]


def expected_rule(schema_key, inst, vocab):
    """The exact rule sentence the renderer interpolates into every instruction style."""
    pp, meta = inst["program_params"], inst["meta"]
    cmp_txt = CMP_TEXT[pp["cond_op"]]
    j2 = pp["join_depth"] == 2
    theta_text = (vocab["j2_theta"] % (meta["tier"] if schema_key == "crm_escalate" else meta["category"])
                  if j2 else str(pp["theta"]))
    if schema_key == "crm_escalate":
        return ("If the customer's complaint count is %s %s, set status to 'escalated' "
                "and priority_flag to 1; otherwise, set status to 'routine' and "
                "priority_flag to 0." % (cmp_txt, theta_text)), theta_text, cmp_txt
    return ("If the on-hand quantity of SKU %s at warehouse 'main' is %s %s, set its "
            "flag to 'markdown' and review to 1; otherwise, set flag to 'ok' and "
            "review to 0." % (meta["sku"], cmp_txt, theta_text)), theta_text, cmp_txt


# ---------------------------------------------------------------------------
# IR builders (projection pi). Every evidence span is located + recorded.
# ---------------------------------------------------------------------------
class IrBuilder:
    def __init__(self, text, core_end):
        self.text = text
        self.core_end = core_end           # evidence must start before this offset
        self.ev = []                       # evidence_map rows

    def span(self, field, span, after=0, max_words=15):
        _assert(len(span.split()) <= max_words, "%s evidence >%d words: %r" % (field, max_words, span))
        s, e, n = locate(self.text, span, after, field)
        _assert(s < self.core_end, "%s: evidence lands in filler region: %r" % (field, span[:60]))
        self.ev.append({"field": field, "span": span, "start": s, "end": e, "occurrences": n})
        return span, s

    def f(self, field, status, value=None, span=None, after=0):
        if status == "present":
            ev, _ = self.span(field, span, after)
            return {"status": "present", "value": value, "evidence": ev}
        return {"status": status, "value": None, "evidence": None}


def base_ir():
    return {"schema": "phi_ir/v0",
            "roles": {r: {"status": "absent", "surface": None, "evidence": None}
                      for r in ["subject_row", "policy_row", "source", "destination",
                                "child_set", "audit_sink"]},
            "nodes": [], "termination": {"status": "unknown", "evidence": None}}


def project_instruction(schema_key, inst, style):
    """pi for a P1 instruction text (sibling or near-miss)."""
    text = inst["instruction"]
    _assert("\nNote: " not in text, "instruction unexpectedly padded")
    ib = IrBuilder(text, core_end=len(text))
    pp, meta, vocab = inst["program_params"], inst["meta"], p1_vocab(schema_key)
    j2 = pp["join_depth"] == 2
    cmp_txt = CMP_TEXT[pp["cond_op"]]
    rule, theta_text, _ = expected_rule(schema_key, inst, vocab)
    rule_s, _, _ = locate(text, rule, 0, "instruction rule clause")

    ir = base_ir()
    # ---- roles
    if schema_key == "crm_escalate":
        ent_s, _, _ = locate(text, meta["entity_name"])
        surface = meta["entity_name"]
    else:
        ent_s, _, _ = locate(text, meta["sku"])
        surface = meta["sku"]
    sent, _, _ = sentence_around(text, ent_s)
    ir["roles"]["subject_row"] = {"status": "present", "surface": surface,
                                  "evidence": ib.span("roles.subject_row", sent)[0]}
    if j2:
        ir["roles"]["policy_row"] = {"status": "present", "surface": vocab["policy_table"],
                                     "evidence": ib.span("roles.policy_row", vocab["policy_table"],
                                                         after=rule_s)[0]}
    # ---- nodes
    nodes, nid = [], 0

    def add(op, status, evidence_field, evidence_span=None, args=None, deps=None, after=0):
        nonlocal nid
        nid += 1
        node = {"id": "n%d" % nid, "op": op, "status": status,
                "evidence": (ib.span(evidence_field, evidence_span, after=after)[0]
                             if evidence_span else None),
                "args": args or {}, "depends_on": deps or [], "commutes_with": []}
        nodes.append(node)
        return node["id"]

    read_cue = vocab["read_cues"][style]
    n_read = add("read", "present", "nodes.read", read_cue, args={"target": "subject_row"})
    # condition clause = rule up to the conseq ("..., set ... / ; otherwise, ...")
    conseq_start = vocab["conseq"][:12]         # "set status '" / "set its flag"
    cut = rule.find(", " + conseq_start)
    _assert(cut != -1, "conseq cut not found in rule: %r" % rule[:90])
    cond_part = rule[:cut]
    attribute = vocab["attr"]
    attr_span = vocab["attr_span"]
    attr_s = rule.find(attr_span)
    _assert(attr_s != -1, "attribute span not in rule")
    cmp_abs = rule_s + rule.find(" " + cmp_txt)
    pol_clause = text[rule_s:cut + rule_s]
    polarity = "negative" if any(c in (" " + pol_clause.lower() + " ") for c in NEG_CUES) else "positive"
    _assert(polarity == "positive", "P1 instructions render affirmative conditions; got %s" % polarity)

    if j2:      # symbolic: policy-table indirection; the number must NOT appear in the label
        _assert(str(pp["theta"]) not in cond_part,
                "theta LEAKS into a J2 condition clause: %r" % cond_part[:90])
        _assert(vocab["policy_col"] in rule, "policy column name missing from J2 rule")
        value_status, value_val, value_span = "present", vocab["policy_col"], theta_text
    else:       # numeric: theta printed in the clause; project it (asserted stated)
        _assert((" " + str(pp["theta"])) in cond_part,
                "numeric theta NOT stated in a J1 condition clause: %r" % cond_part[:90])
        value_status, value_val, value_span = "present", str(pp["theta"]), cmp_txt + " " + str(pp["theta"])

    branch_ev = cond_part if len(cond_part.split()) <= 15 else " ".join(cond_part.split()[:15])
    n_branch = add("branch", "present", "nodes.branch", branch_ev, deps=[n_read],
                   args={"predicate": {
                       "attribute": ib.f("predicate.attribute", "present", attribute, attr_span, after=rule_s),
                       "op": ib.f("predicate.op", "present", pp["cond_op"], cmp_txt, after=rule_s + attr_s),
                       "value": ib.f("predicate.value", value_status, value_val, value_span,
                                     after=cmp_abs),
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
    return ir, ib.ev, {"value_symbolic": j2, "numeric_theta": pp["theta"]}


def project_memory(schema_key, inst, n_sib_unused=None):
    """pi for a P1 memory card text, given the source instance whose roles rendered it."""
    roles = inst["roles"]
    text, pp, vocab = inst["_card_text"], inst["program_params"], p1_vocab(schema_key)
    steps = list(roles["steps"])
    j2 = pp["join_depth"] == 2
    # positional layout per p1_roles (generate_families.py:236-266); assert, don't trust
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

    pad_at = text.find("\nNote: ")
    core_end = pad_at if pad_at != -1 else len(text)
    ib = IrBuilder(text, core_end=core_end)

    ir = base_ir()
    ir["roles"]["subject_row"] = {"status": "present", "surface": vocab["card_entity"],
                                  "evidence": ib.span("roles.subject_row", steps[0])[0]}
    if j2:
        # find-step is long (theta_phrase itself names the policy table); use compact
        # verbatim sub-spans: "in the <policy_table> table" (unique in card text) and the
        # step head up to the "(match ... )" parenthesis.
        cut_head = find_step.find(" in the %s table (" % vocab["policy_table"])
        _assert(cut_head != -1, "find-step head cut not found: %r" % find_step[:90])
        find_head = find_step[:cut_head]
        _assert(len(find_head.split()) <= 15, "find-step head too long: %r" % find_head)
        ir["roles"]["policy_row"] = {"status": "present", "surface": vocab["policy_table"],
                                     "evidence": ib.span("roles.policy_row",
                                                         "in the %s table" % vocab["policy_table"])[0]}

    cmp_txt = CMP_TEXT[pp["cond_op"]]
    theta_phrase = vocab["j2_theta_card"] if j2 else vocab["j1_theta_card"]
    _assert(theta_phrase in if_step, "theta_phrase absent from if-step: %r" % if_step[:80])
    _assert(cmp_txt in if_step, "cmp absent from if-step: %r" % if_step[:80])
    conseq_c = vocab["conseq"].replace("set its", "set") if schema_key == "inv_overstock" else vocab["conseq"]
    if_cut = if_step.find(", " + conseq_c[:10])
    _assert(if_cut != -1, "card conseq cut not found: %r" % if_step[:90])
    cond_part = if_step[:if_cut]
    _assert(str(pp["theta"]) not in cond_part, "theta LEAKS into a card condition clause")
    if j2:
        _assert(vocab["policy_col"] in find_step, "policy column not in find-step")
        value_val = vocab["policy_col"]
    else:
        value_val = theta_phrase
    cmp_abs = text.find(cmp_txt, locate(text, cond_part)[0])
    pol_clause = " " + cond_part.lower() + " "
    polarity = "negative" if any(c in pol_clause for c in NEG_CUES) else "positive"
    _assert(polarity == "positive", "P1 cards render affirmative conditions")

    nodes, nid = [], 0

    def add(op, evidence_field, evidence_span, args=None, deps=None):
        nonlocal nid
        nid += 1
        node = {"id": "n%d" % nid, "op": op, "status": "present",
                "evidence": ib.span(evidence_field, evidence_span)[0],
                "args": args or {}, "depends_on": deps or [], "commutes_with": []}
        nodes.append(node)
        return node["id"]

    n_read = add("read", "nodes.read", steps[0], args={"target": "subject_row"})
    deps = [n_read]
    if j2:
        cut_head = find_step.find(" in the %s table (" % vocab["policy_table"])
        find_head = find_step[:cut_head] if cut_head != -1 else find_step
        deps.append(add("read", "nodes.read_policy", find_head,
                        args={"target": "policy_row"}, deps=[]))
    branch_ev = cond_part if len(cond_part.split()) <= 15 else " ".join(cond_part.split()[:15])
    n_branch = add("branch", "nodes.branch", branch_ev, deps=deps,
                   args={"predicate": {
                       "attribute": ib.f("predicate.attribute", "present", vocab["attr"],
                                         vocab["attr"], after=locate(text, if_step)[0]),
                       "op": ib.f("predicate.op", "present", pp["cond_op"], cmp_txt, after=cmp_abs - 1),
                       "value": ib.f("predicate.value", "present", value_val, theta_phrase, after=cmp_abs - 1),
                       "polarity": ib.f("predicate.polarity", "present", polarity, cmp_txt, after=cmp_abs - 1)},
                       "then_effects": vocab["effects_then"], "else_effects": vocab["effects_else"]})
    ib.span("predicate.then_effects", conseq_c, after=cmp_abs)
    ib.span("predicate.else_effects", vocab["alt"], after=cmp_abs)
    n_verify = add("verify", "nodes.verify", readback, args={"target": "subject_row"}, deps=[n_branch])
    ir["nodes"] = nodes
    ir["termination"] = {"status": "present", "evidence": ib.span("termination", readback)[0]}
    return ir, ib.ev, {"value_symbolic": True, "numeric_theta": pp["theta"]}


# ---------------------------------------------------------------------------
# sealed-artifact joins
# ---------------------------------------------------------------------------
def load_sealed():
    tasks = [json.loads(l) for l in open(SEALED / "tasks_sealed.jsonl")]
    mems = {m["memory_id"]: m for m in map(json.loads, open(SEALED / "memories_sealed.jsonl"))}
    return tasks, mems


def expected_ops(signature, kind, j2_policy_read):
    """Audit-rule expansion of the P1 signature into IR node ops."""
    _assert(signature.startswith("P1|"), "prototype covers P1 only: %s" % signature)
    ops = ["read"]
    if "READ+POLICY" in signature and j2_policy_read:
        ops.append("read")
    return ops + ["branch", "verify"]


# ---------------------------------------------------------------------------
# main mint
# ---------------------------------------------------------------------------
def main():
    cfg = G.load_config(str(PILOT / "configs" / "pilot.yaml"))
    gcfg, mcfg = cfg["generation"], cfg["memories"]
    gs, n_sib = gcfg["generator_seed"], gcfg["siblings_per_family"]
    fams = G.plan_families(cfg)
    _assert(len(fams) >= 40, "expected the sealed 40-family plan")
    tasks_sealed, mems_sealed = load_sealed()

    meter = G.TokenMeter(mcfg["tokenizer"])          # CPU; pad_to_tokens byte-fidelity
    all_insts = {fidx: G.build_instances_for_family(cfg, fams[fidx]) for fidx in MINT_FAMILIES}
    # cross-domain P=1 partners, recomputed with main()'s algorithm over the full plan
    from collections import defaultdict
    sig = {}
    for f in fams:   # only signatures are needed; sibling-0-seed-0 instances are cheap
        sig[f["idx"]] = G.build_instances_for_family(cfg, f)[("sibling", 0, 0)]["signature"]
    by_class = defaultdict(list)
    for k, v in sig.items():
        by_class[v].append(k)
    a10 = {}
    for f in fams:
        cands = sorted(x for x in by_class[sig[f["idx"]]] if fams[x]["domain"] != f["domain"])
        a10[f["idx"]] = cands[f["occ"] % len(cands)]

    pairs, checks = [], []

    def add_check(pair_id, name, ok, detail=""):
        checks.append({"pair": pair_id, "check": name, "ok": bool(ok), "detail": detail})
        _assert(ok, "self-consistency failure %s/%s: %s" % (pair_id, name, detail))

    # ---------------- instructions -----------------------------------------
    for fidx in MINT_FAMILIES:
        fam = fams[fidx]
        sk = fam["schema_key"]
        for sib in list(range(n_sib)) + ["nm"]:
            nm = sib == "nm"
            sib_idx, style = ((fidx + (0 if nm else sib)) % 3, fidx % 3) if nm else (sib, (fidx + sib) % 3)
            inst = all_insts[fidx][("near_miss", 0, 0)] if nm else all_insts[fidx][("sibling", sib, 0)]
            style = (fidx % 3) if nm else ((fidx + sib) % 3)
            ir, ev, proj = project_instruction(sk, inst, style)
            pid = "instr:f%d:%s" % (fidx, "nm" if nm else "s%d" % sib)
            sealed = next(t for t in tasks_sealed
                          if t["family_idx"] == fidx
                          and t["kind"] == ("near_miss" if nm else "sibling")
                          and (nm or t["sibling_idx"] == sib) and t["seed"] == 0)
            text = inst["instruction"]
            add_check(pid, "byte_equal_sealed", text == sealed["instruction"], "tasks_sealed join")
            ok_ir, ec, _ = validate_ir(ir)
            add_check(pid, "validate_ir", ok_ir, str(ec))
            prog = ARCHETYPES[fam["archetype"]](inst["program_params"])
            add_check(pid, "op_seq", [n["op"] for n in ir["nodes"]] ==
                      expected_ops(prog["signature"], "instruction", j2_policy_read=False),
                      prog["signature"])
            pred = next(n for n in ir["nodes"] if n["op"] == "branch")["args"]["predicate"]
            add_check(pid, "pred_op==program", pred["op"]["value"] == inst["program_params"]["cond_op"],
                      "%s vs %s" % (pred["op"]["value"], inst["program_params"]["cond_op"]))
            add_check(pid, "policy_row<=>J2",
                      (ir["roles"]["policy_row"]["status"] == "present") ==
                      (inst["program_params"]["join_depth"] == 2))
            sym = proj["value_symbolic"]
            if sym:
                add_check(pid, "value_symbolic_no_leak",
                          pred["value"]["value"] in (v := p1_vocab(sk))["policy_col"] and
                          str(proj["numeric_theta"]) not in pred["value"]["evidence"])
            else:
                add_check(pid, "value_numeric", float(pred["value"]["value"]) ==
                          float(inst["program_params"]["theta"]))
            pairs.append({"pair_id": pid, "kind": "instruction",
                          "family_idx": fidx, "schema_key": sk, "domain": fam["domain"],
                          "archetype": fam["archetype"],
                          "join_depth": inst["program_params"]["join_depth"],
                          "program": "near_miss" if nm else "correct",
                          "sibling_idx": None if nm else sib, "style": style,
                          "signature": prog["signature"],
                          "text": text, "gold_ir": ir,
                          "projection": {"value_symbolic": sym,
                                         "cond_op": inst["program_params"]["cond_op"]},
                          "evidence_map": ev})
            print("[mint] %s ok (style %d, %s, value %s)"
                  % (pid, style, prog["signature"], "SYMBOLIC" if sym else "numeric"))

    # ---------------- memories ---------------------------------------------
    for fidx in MINT_FAMILIES:
        fam = fams[fidx]
        for s, cell in CARD_SLOTS:
            src_inst = {"A11": all_insts[fidx][("sibling", 0, 0)],
                        "A01": all_insts[fidx][("near_miss", 0, 0)],
                        "A10": G.build_instances_for_family(cfg, fams[a10[fidx]])[("sibling", 0, 0)]}[cell]
            style_idx = (fidx * n_sib + s + G.CELL_RANK[cell]) % len(G.CARD_STYLES)
            base = G.CARD_STYLES[style_idx](src_inst["roles"])
            rngc = random.Random(G.sha_int("card", gs, fidx, s, cell))
            text, ntok = G.pad_to_tokens(base, meter, rngc, mcfg["tokens_target"],
                                         mcfg["tokens_min"], mcfg["tokens_max"])
            mid = G.opaque_id("m", gs, fidx, s, cell)
            pid = "mem:f%d:s%d:%s" % (fidx, s, cell)
            mrow = mems_sealed[mid]
            add_check(pid, "byte_equal_sealed", text == mrow["text"], "memories_sealed %s" % mid)
            src_schema = fams[a10[fidx]]["schema_key"] if cell == "A10" else fam["schema_key"]
            src_inst = dict(src_inst); src_inst["_card_text"] = text
            ir, ev, proj = project_memory(src_schema, src_inst)
            ok_ir, ec, _ = validate_ir(ir)
            add_check(pid, "validate_ir", ok_ir, str(ec))
            prog = ARCHETYPES[fam["archetype"]](src_inst["program_params"])
            j2_card = src_inst["program_params"]["join_depth"] == 2
            add_check(pid, "op_seq", [n["op"] for n in ir["nodes"]] ==
                      expected_ops(prog["signature"], "memory", j2_policy_read=j2_card),
                      prog["signature"])
            pred = next(n for n in ir["nodes"] if n["op"] == "branch")["args"]["predicate"]
            add_check(pid, "pred_op==program", pred["op"]["value"] ==
                      src_inst["program_params"]["cond_op"],
                      "%s vs %s" % (pred["op"]["value"], src_inst["program_params"]["cond_op"]))
            add_check(pid, "value_symbolic", proj["value_symbolic"] and
                      str(proj["numeric_theta"]) not in pred["value"]["evidence"] and
                      not pred["value"]["value"].lstrip("-").isdigit())
            add_check(pid, "policy_row<=>J2", (ir["roles"]["policy_row"]["status"] == "present") == j2_card)
            pairs.append({"pair_id": pid, "kind": "memory",
                          "family_idx": fidx, "schema_key": src_schema,
                          "domain": fams[a10[fidx]]["domain"] if cell == "A10" else fam["domain"],
                          "archetype": fam["archetype"],
                          "join_depth": src_inst["program_params"]["join_depth"],
                          "program": {"A11": "correct", "A01": "near_miss", "A10": "correct_cross_domain"}[cell],
                          "cell": cell, "target_sibling": s, "style_idx": style_idx,
                          "style_name": G.STYLE_NAMES[style_idx], "memory_id": mid,
                          "signature": prog["signature"],
                          "text": text, "gold_ir": ir,
                          "projection": {"value_symbolic": True,
                                         "cond_op": src_inst["program_params"]["cond_op"]},
                          "evidence_map": ev})
            print("[mint] %s ok (%s, %s)" % (pid, G.STYLE_NAMES[style_idx], prog["signature"]))

    # ---------------- span re-verification (independent pass) ---------------
    for p in pairs:
        for e in p["evidence_map"]:
            ok = p["text"][e["start"]:e["end"]] == e["span"] and len(e["span"].split()) <= 15
            checks.append({"pair": p["pair_id"], "check": "span_reslice", "ok": ok,
                           "detail": e["field"]})
            _assert(ok, "span reslice mismatch %s %s" % (p["pair_id"], e["field"]))

    with open(OUT_JSONL, "w") as f:
        for p in pairs:
            f.write(json.dumps(p, sort_keys=True) + "\n")
    digest = hashlib.sha256(open(OUT_JSONL, "rb").read()).hexdigest()

    n_sym = sum(1 for p in pairs if p["projection"]["value_symbolic"])
    report = {
        "mint20_sha256": digest,
        "n_pairs": len(pairs),
        "n_instruction": sum(1 for p in pairs if p["kind"] == "instruction"),
        "n_memory": sum(1 for p in pairs if p["kind"] == "memory"),
        "families": {str(f): {"schema_key": fams[f]["schema_key"],
                              "join_depth": fams[f]["params"]["join_depth"],
                              "a10_partner": a10[f]} for f in MINT_FAMILIES},
        "program_mix": {k: sum(1 for p in pairs if p["program"] == k)
                        for k in ("correct", "near_miss", "correct_cross_domain")},
        "value_policy": {"numeric": len(pairs) - n_sym, "symbolic": n_sym},
        "checks_total": len(checks),
        "checks_failed": [c for c in checks if not c["ok"]],
        "checks_pass_rate": sum(c["ok"] for c in checks) / float(len(checks)),
        "generator_seed": gs,
        "byte_equality": "every minted text == sealed artifact text (tasks_sealed seed0 / memories_sealed by memory_id)",
        "label_provenance": "clause-level renderer expectations asserted verbatim; evidence spans exact-aligned with offsets; numeric theta only when printed in the condition clause",
    }
    with open(OUT_REPORT, "w") as f:
        json.dump(report, f, indent=1, sort_keys=True)
    print("[mint] wrote %s (%d pairs) + %s; checks %d/%d pass; symbolic %d / numeric %d; sha %s"
          % (OUT_JSONL, len(pairs), OUT_REPORT, sum(c["ok"] for c in checks), len(checks),
             n_sym, len(pairs) - n_sym, digest[:16]))


if __name__ == "__main__":
    main()
