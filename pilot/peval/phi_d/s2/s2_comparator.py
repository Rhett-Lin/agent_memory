"""S2-rc1 comparator (release candidate rules) for the phi+d line (SFT era).

Implements S2_SPEC.md exactly. Deterministic, stdlib-only, CPU-only, no I/O inside
compare(). Labels (P/cell/family/archetype/domain), sealed truth, and pair metadata
NEVER enter this module: inputs are exactly two phi_ir/v0 IRs and their two source
texts.

Authority:
  - Adjudicated truth table (Codex thread 019fe66c): completeness certificate
    (7 clauses), predicate canonical decision function (aligned attribute anchor +
    normalized operator + branch effects; complementation {><=, >=<, ==!=} + effect
    swap = equivalent; complement without swap = contradiction), non-compensatory
    contradiction, three-verdict {match,contradict,unknown}, NO continuous score,
    match requires every task-required component comparable+matching, any unresolved
    required component -> unknown, ABSENT on memory = contradiction only under
    complete(memory), extra effectful ops contradiction, benign extras =
    non-mutating read/verify/report.
  - SFT-era veto eligibility (sft2_eval/audit_sft_canonical.json + S2_PREP_REPORT
    section 6): 10/11 HARD VETO under the dual-tokcov attribute anchor
    (sealed-anchor-intersection OR all-IR-attribute-tokens subset of text tokens;
    fallback dual-verbatim recorded), scope permanently excluded (note-only),
    UNMEAS never counts as mismatch, full-640 denominator (no eligibility loss).

Reuse (read-only, hash-pinned in freeze_rc1.json):
  - common.validate_ir + CANONICAL_ROLES (schema + canonical 6 roles);
  - audit_expanded.toks (the FROZEN tokenizer used by the dual-tokcov audit; only
    this one function is consumed; the module performs no file I/O at import);
  - comparator_v0/comparator.py mechanics: norm_text, norm_value, resolve_role
    alpha-renaming, present_nodes, write_action, agg_function, branch_pred,
    pred_populated, branch_effects, _pair_nodes greedy pairing, cmp_effect_lists,
    compare_ordering / compare_termination / compare_direction scaffolding, and the
    frozen action-class constants. v0's DEMOTE-era audit demotions are NOT
    inherited: eligibility changed with SFT (spec section 4).

rc1 rulings on adjudication-open items live in S2_SPEC.md section 14 (R1-R9) and
are pinned by test_s2.py fixtures F1-F29.
"""
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent          # pilot/peval/phi_d/s2
PHI_D = HERE.parent                                     # pilot/peval/phi_d
for _p in (str(PHI_D), str(PHI_D / "comparator_v0")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import audit_expanded as A                              # noqa: E402  toks (frozen tokenizer); import is side-effect free
import common as C                                      # noqa: E402  validate_ir + canonical roles
import comparator as V0                                 # noqa: E402  v0 mechanics, reused read-only

RULE_VERSION = "s2-rc1"
VERDICTS = ("match", "contradict", "unknown")

_ROLES = C.CANONICAL_ROLES

# Frozen SFT-era eligibility table (S2_SPEC.md section 4). The three non-vote
# statuses are first-class: "anchor_gate" (pred_attribute; never vetoes),
# "metadata" (pred_polarity; note-only), "excluded_note_only" (scope; zero
# verdict influence), "composite" (pred_all; folds in).
ELIGIBILITY_S2 = {
    "pred_op": "hard",
    "pred_value": "hard",
    "pred_polarity": "metadata",
    "branch_effects": "hard",
    "direction": "hard",
    "archive_capture": "hard",
    "roles_required": "hard",
    "termination": "hard",
    "pred_attribute": "anchor_gate",
    "pred_all": "composite",
    "scope": "excluded_note_only",
    "agg_function": "hard",
}
# v0-passthrough map for the scaffolding functions reused unmodified (ordering,
# termination, direction): their reused internals only check whether the field is
# "excluded"; everything they must harden to is SFT-HARD now.
_V0_PASSTHROUGH_ELIG = {
    "pred_attribute": "hard", "pred_op": "hard", "pred_value": "hard",
    "pred_polarity": "hard", "pred_all": "hard", "branch_effects": "hard",
    "direction": "hard", "scope": "excluded", "archive_capture": "hard",
    "roles_required": "hard", "termination": "hard",
}


# ---------------------------------------------------------------------------
# completeness certificate (S2_SPEC.md section 3: exact 7 clauses)
# ---------------------------------------------------------------------------

def _verbatim(evidence, text):
    """Whitespace-squeezed, case-sensitive, contiguous substring test (v0 semantics)."""
    if not evidence or not str(evidence).strip():
        return False
    ev = re.sub(r"\s+", " ", str(evidence)).strip()
    tx = re.sub(r"\s+", " ", text or "")
    return ev in tx


def certificate(ir, text, require_branch=True):
    """7-clause completeness certificate. ABSENT is a trustworthy active omission
    only under complete == True. Returns {require_branch, checks, stats, complete}."""
    out = {"require_branch": require_branch, "checks": {}, "stats": {}}
    ok, _ec, detail = C.validate_ir(ir)
    out["checks"]["valid"] = bool(ok)
    if not ok:                                                     # clause 1 gate
        out["checks"]["required_fields"] = False
        out["stats"]["invalid_detail"] = str(detail)[:200]
        out["complete"] = False
        return out

    # clause 2: required fields present (schema-level, re-asserted)
    out["checks"]["required_fields"] = all(
        k in ir for k in ("schema", "roles", "nodes", "termination")) and bool(ir["nodes"])

    # clauses 3-4: evidence slots on every present-status field
    ev_slots, ev_missing, ev_nonverbatim = 0, 0, 0

    def _ev(st, evidence):
        nonlocal ev_slots, ev_missing, ev_nonverbatim
        if st != "present":
            return
        ev_slots += 1
        if not evidence or not str(evidence).strip():
            ev_missing += 1
        elif not _verbatim(evidence, text):
            ev_nonverbatim += 1

    for rv in ir["roles"].values():
        _ev(rv.get("status"), rv.get("evidence"))
    n_unknown_nodes = 0
    for n in ir["nodes"]:
        _ev(n.get("status"), n.get("evidence"))
        if n.get("status") == "unknown":
            n_unknown_nodes += 1
        if n["op"] == "branch" and n.get("status") == "present":
            pred = V0.branch_pred(n) or {}
            for fk in ("attribute", "op", "value", "polarity"):
                w = (pred.get(fk) or {})
                _ev(w.get("status"), w.get("evidence"))
    _ev(ir["termination"].get("status"), ir["termination"].get("evidence"))
    out["stats"]["evidence"] = {"present_slots": ev_slots, "missing": ev_missing,
                                "nonverbatim": ev_nonverbatim}
    out["checks"]["evidence_nonempty"] = (ev_missing == 0)          # clause 3
    out["checks"]["evidence_verbatim"] = (ev_nonverbatim == 0)      # clause 4

    # clause 5: no unknown-in-used-fields
    unknown_roles = sum(1 for rv in ir["roles"].values() if rv.get("status") == "unknown")
    unknown_pred_subs = 0
    for n in ir["nodes"]:
        if n["op"] == "branch" and n.get("status") == "present":
            pred = V0.branch_pred(n) or {}
            unknown_pred_subs += sum(
                1 for fk in ("attribute", "op", "value", "polarity")
                if (pred.get(fk) or {}).get("status") == "unknown")
    out["stats"]["unknown"] = {"roles": unknown_roles, "nodes": n_unknown_nodes,
                               "predicate_subfields": unknown_pred_subs,
                               "termination": int(ir["termination"].get("status") == "unknown")}
    out["checks"]["no_unknown_in_used_fields"] = (
        unknown_roles == 0 and n_unknown_nodes == 0 and unknown_pred_subs == 0
        and ir["termination"].get("status") != "unknown")

    # clause 6: branch predicates/effects populated (absent-neutral when off)
    if require_branch:
        bad = 0
        for n in ir["nodes"]:
            if n["op"] == "branch" and n.get("status") == "present":
                pred = V0.branch_pred(n)
                if (not V0.pred_populated(pred)
                        or not V0.branch_effects(n, "then_effects")
                        or not V0.branch_effects(n, "else_effects")):
                    bad += 1
        out["checks"]["branch_populated"] = (bad == 0)
        out["stats"]["branch_unpopulated"] = bad

    # clause 7: subgraph connected from an evidenced root op to an evidenced
    # verify/finish, or a supported termination
    pnodes = V0.present_nodes(ir)
    ids = {n["id"] for n in pnodes}
    fwd = {i: [] for i in ids}
    roots = []
    for n in pnodes:
        deps = [d for d in n.get("depends_on", []) if d in ids]
        if not deps:
            roots.append(n)
        for d in deps:
            fwd[d].append(n["id"])
    evidenced_roots = [n for n in roots if (n.get("evidence") or "").strip()]
    reachable_vf = False
    byid = {n["id"]: n for n in pnodes}
    for r in evidenced_roots:
        seen, stack = set(), [r["id"]]
        while stack:
            u = stack.pop()
            if u in seen:
                continue
            seen.add(u)
            n = byid[u]
            if n["op"] in ("verify", "finish") and (n.get("evidence") or "").strip():
                reachable_vf = True
                break
            stack.extend(fwd.get(u, []))
        if reachable_vf:
            break
    term = ir["termination"]
    supported_term = (term.get("status") == "present"
                      and bool((term.get("evidence") or "").strip())
                      and _verbatim(term.get("evidence"), text))
    out["checks"]["connected"] = bool(pnodes) and (reachable_vf or supported_term)
    out["stats"]["connectivity"] = {"present_nodes": len(pnodes),
                                    "evidenced_roots": len(evidenced_roots),
                                    "evidenced_verify_finish_reachable": reachable_vf,
                                    "supported_termination": supported_term}

    out["complete"] = all(out["checks"].values())
    return out


# ---------------------------------------------------------------------------
# dual-tokcov attribute anchor (S2_SPEC.md section 7)
# ---------------------------------------------------------------------------

def anchor_decision(attr_i, text_i, attr_m, text_m):
    """Dual-tokcov alignment between two predicate attributes. Returns a
    JSON-serializable flag dict (also embedded in the trace as the reason probe).

    aligned_tokcov  = cross_anchor OR cross_text            (rc1 PRIMARY gate)
    aligned_verbatim= cross_anchor OR contiguous-verbatim   (rc1 recorded FALLBACK)
    cross_anchor    = toks(attr_i) intersect toks(attr_m) non-empty   (sealed-anchor
                      intersection analogue: shared extraction anchor token)
    cross_text      = toks(attr_i) subset of toks(text_m) OR
                      toks(attr_m) subset of toks(text_i)   (all-attribute-tokens
                      subset of the OTHER side's text tokens, either direction)
    faith_*         = own attribute tokens subset of OWN text tokens (audit tokcov
                      faithfulness test; governs CROSS vs UNFAITHFUL abstain code).
    """
    si, sm = (attr_i or "").strip(), (attr_m or "").strip()
    ti, tm = A.toks(attr_i), A.toks(attr_m)
    xi, xm = A.toks(text_i), A.toks(text_m)
    cross_anchor = bool(ti & tm)
    i_in_m = bool(ti) and ti <= xm
    m_in_i = bool(tm) and tm <= xi
    cross_text = i_in_m or m_in_i
    li, lm = si.lower(), sm.lower()
    txi, txm = (text_i or "").lower(), (text_m or "").lower()
    i_verbatim_in_m = bool(li) and li in txm
    m_verbatim_in_i = bool(lm) and lm in txi
    return {
        "aligned_tokcov": cross_anchor or cross_text,
        "aligned_verbatim": cross_anchor or i_verbatim_in_m or m_verbatim_in_i,
        "cross_anchor": cross_anchor,
        "cross_text_i_in_m": i_in_m,
        "cross_text_m_in_i": m_in_i,
        "verbatim_i_in_m": i_verbatim_in_m,
        "verbatim_m_in_i": m_verbatim_in_i,
        "faith_i": bool(ti) and ti <= xi,
        "faith_m": bool(tm) and tm <= xm,
        "attr_i_tokens": sorted(ti),
        "attr_m_tokens": sorted(tm),
        "shared_tokens": sorted(ti & tm),
    }


# ---------------------------------------------------------------------------
# threshold value decidability marks (S2_SPEC.md section 8)
# ---------------------------------------------------------------------------

_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _first_number(v):
    m = _NUM_RE.search(str(v))
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def value_mark(v):
    """NUMERIC (first number parses) / LITERAL (fully quote-wrapped) / SYMBOLIC
    (the audit's value-as-stated class; undecidable comparator-side at rc1).
    Quote-wrapping wins over digits: '5' is a string LITERAL, not a number."""
    s = str(v).strip()
    if len(s) >= 2 and ((s[0] == s[-1] == "'") or (s[0] == s[-1] == '"')):
        return "literal"
    if _first_number(s) is not None:
        return "numeric"
    return "symbolic"


# ---------------------------------------------------------------------------
# component: roles (roles_required HARD VETO; spec section 6.1 + 6.3)
# ---------------------------------------------------------------------------

def compare_roles(ir_i, ir_m, cert_m_complete, add):
    for r in _ROLES:
        si = ir_i["roles"][r]["status"]
        sm = ir_m["roles"][r]["status"]
        if si == "present":
            if sm == "present":
                add("roles", f"ROLE_ALIGNED:{r}", "note",
                    "present both sides (surfaces alpha-renamed)")
            elif sm == "absent":
                if cert_m_complete:
                    add("roles", f"ROLE_OMITTED_UNDER_COMPLETE:{r}", "contradict",
                        "required role absent in complete memory (ABSENT under "
                        "complete(memory) = contradiction)")
                else:
                    add("roles", f"ROLE_OMITTED_INCOMPLETE:{r}", "unknown",
                        "required role absent in memory, memory not complete")
            else:
                add("roles", f"ROLE_MEMORY_STATUS_UNKNOWN:{r}", "unknown",
                    "memory role status unknown")
        elif si == "absent" and sm == "present":
            add("roles", f"ROLE_EXTRA_MEMORY:{r}", "benign",
                "extra role in memory only (not effectful by itself)")
        # si unknown, or aligned double-absent: silent on this channel


# ---------------------------------------------------------------------------
# component: predicate canonical decision function (spec section 6.4)
# ---------------------------------------------------------------------------

def compare_predicate(ni, nm, ir_i, ir_m, text_i, text_m, add):
    roles_i, roles_m = ir_i["roles"], ir_m["roles"]
    pi, pm = V0.branch_pred(ni), V0.branch_pred(nm)
    if not V0.pred_populated(pi):
        add("predicate", "PRED_INSTRUCTION_UNPOPULATED", "unknown",
            "instruction branch predicate/effects not fully populated")
        return
    if not V0.pred_populated(pm):
        add("predicate", "PRED_MEMORY_UNPOPULATED", "unknown",
            "memory branch predicate not fully populated (unknown-if-absent)")
        return

    # --- 1. aligned attribute anchor: dual-tokcov gate, never a veto (spec R1) ---
    ai, am = pi["attribute"]["value"], pm["attribute"]["value"]
    anch = anchor_decision(ai, text_i, am, text_m)
    if anch["aligned_tokcov"]:
        chan = [k for k in ("cross_anchor", "cross_text_i_in_m", "cross_text_m_in_i")
                if anch[k]]
        add("predicate", "ATTR_ANCHOR_ALIGNED", "note",
            f"dual-tokcov aligned via {chan}: {ai!r} vs {am!r}", probe=anch)
    else:
        code = ("ATTR_ANCHOR_CROSS" if (anch["faith_i"] and anch["faith_m"])
                else "ATTR_ANCHOR_UNFAITHFUL")
        add("predicate", code, "unknown",
            f"dual-tokcov not aligned ({ai!r} vs {am!r}); anchor never vetoes at rc1",
            probe=anch)
        add("predicate", "PRED_HALTED_NO_ANCHOR", "note",
            "operator/effects/value not licensed without an aligned anchor"
            " (spec R5); literal comparison without a shared anchor is forbidden")
        return

    # --- 2. polarity: metadata only, never gates (spec R2) ---
    if pi["polarity"]["value"] == pm["polarity"]["value"]:
        add("predicate", "POLARITY_ALIGNED", "note",
            f"polarity {pi['polarity']['value']} on both sides")
    else:
        add("predicate", "POLARITY_DIVERGENT", "note",
            f"polarity {pi['polarity']['value']} vs {pm['polarity']['value']}"
            " (metadata per spec R2; never a veto)")

    # --- 3. normalized operator + branch effects (spec truth-table rule) ---
    oi, om = pi["op"]["value"], pm["op"]["value"]
    ti, tm = V0.branch_effects(ni, "then_effects"), V0.branch_effects(nm, "then_effects")
    ei, em = V0.branch_effects(ni, "else_effects"), V0.branch_effects(nm, "else_effects")
    if not ti and not ei:
        add("predicate", "PRED_EFFECTS_INSTRUCTION_EMPTY", "note",
            "instruction branch carries no effect payload; mapping skipped")
    else:
        if oi == om:
            fx1 = V0.cmp_effect_lists(ti, tm, roles_i, roles_m, True)
            fx2 = V0.cmp_effect_lists(ei, em, roles_i, roles_m, True)
            rel_code = "PRED_EFFECT_MISMATCH"
        elif V0.OP_COMPLEMENT.get(oi) == om:
            fx1 = V0.cmp_effect_lists(ti, em, roles_i, roles_m, True)
            fx2 = V0.cmp_effect_lists(ei, tm, roles_i, roles_m, True)
            rel_code = "PRED_COMPLEMENT_NO_SWAP"
        else:
            add("predicate", "PRED_OP_MISMATCH", "contradict",
                f"operator mismatch {oi} vs {om} (not a complementation pair)")
            return
        if fx1 == fx2 == "match":
            if oi != om:
                add("predicate", "PRED_COMPLEMENT_SWAP_EQUIV", "note",
                    f"{oi} vs {om} with swapped branch effects: equivalent")
            else:
                add("predicate", "PRED_OP_EFFECTS_MATCH", "note",
                    f"same operator {oi}, branch effects aligned")
        else:
            add("predicate", rel_code, "contradict",
                f"op {oi} vs {om}; effect mapping {fx1}/{fx2} (non-compensatory)")
            return

    # --- 4. threshold value (pred_value HARD VETO; marks per spec section 8) ---
    vi, vm = pi["value"]["value"], pm["value"]["value"]
    si, sm = bool((vi or "").strip()), bool((vm or "").strip())
    if si != sm:
        add("predicate", "PRED_VALUE_ASYMMETRIC", "unknown",
            "threshold literal present on exactly one side")
        return
    if not si and not sm:
        add("predicate", "VALUE_BOTH_EMPTY", "note",
            "both threshold literals empty; nothing to compare")
        return
    mi, mm = value_mark(vi), value_mark(vm)
    if mi != mm:
        add("predicate", "VALUE_MARK_MISMATCH_UNMEAS", "unknown",
            f"decidability marks differ ({mi} vs {mm}); UNMEAS never counts as "
            f"mismatch", probe={"mark_i": mi, "mark_m": mm,
                                "value_i": vi, "value_m": vm})
        return
    if mi == "numeric":
        fi, fm = _first_number(vi), _first_number(vm)   # parseable by mark definition
        if fi == fm:
            add("predicate", "VALUE_ALIGNED", "note",
                f"numeric threshold {fi:g} == {fm:g} under aligned anchor")
        else:
            add("predicate", "VALUE_LITERAL_MISMATCH", "contradict",
                f"numeric threshold {fi:g} vs {fm:g} under aligned anchor "
                f"(pred_value HARD VETO)")
    elif mi == "literal":
        if V0.norm_value(vi) == V0.norm_value(vm):
            add("predicate", "VALUE_ALIGNED", "note",
                f"literal threshold equal after normalization: {vi!r} ~= {vm!r}")
        else:
            add("predicate", "VALUE_LITERAL_MISMATCH", "contradict",
                f"literal threshold {vi!r} vs {vm!r} under aligned anchor "
                f"(pred_value HARD VETO)")
    else:
        if V0.norm_value(vi) == V0.norm_value(vm):
            add("predicate", "VALUE_ALIGNED", "note",
                f"identical symbolic threshold reference: {vi!r}")
        else:
            add("predicate", "VALUE_SYMBOLIC_UNMEAS", "unknown",
                f"symbolic thresholds differ ({vi!r} vs {vm!r}); undecidable "
                f"comparator-side at rc1 (spec R4); UNMEAS never counts as mismatch",
                probe={"mark_i": mi, "mark_m": mm, "value_i": vi, "value_m": vm})


# ---------------------------------------------------------------------------
# component: required operations + extras (spec sections 6.2, 6.3, 10)
# ---------------------------------------------------------------------------

def compare_ops(pres_i, pres_m, ir_i, ir_m, text_i, text_m, cert_m_complete, add):
    req_i = [n for n in pres_i if n["op"] != "finish"]   # finish is bookkeeping:
    mem_m = [n for n in pres_m if n["op"] != "finish"]   # missing-finish alone is
    pairs, unpaired_i, unpaired_m = V0._pair_nodes(req_i, mem_m)  # never a veto

    for ni, mj in pairs:
        op = ni["op"]
        if op in ("read", "list", "verify"):
            ti = V0.resolve_role(ni["args"].get("target"), ir_i["roles"])
            tm = V0.resolve_role(mj["args"].get("target"), ir_m["roles"])
            if ti and tm and ti != tm:
                add("ops", f"TARGET_CONFLICT:{op}", "contradict",
                    f"{op} target role {ti} vs {tm}")
                continue
            add("ops", f"OP_ALIGNED:{op}", "note", f"{op} paired")
        elif op == "write":
            ti = V0.resolve_role(ni["args"].get("target"), ir_i["roles"])
            tm = V0.resolve_role(mj["args"].get("target"), ir_m["roles"])
            if ti and tm and ti != tm:
                add("ops", "TARGET_CONFLICT:write", "contradict",
                    f"write target role {ti} vs {tm}")
                continue
            add("ops", "OP_ALIGNED:write", "note",
                f"write action {V0.write_action(ni)} paired")
        elif op == "aggregate":
            oi = V0.resolve_role(ni["args"].get("over"), ir_i["roles"])
            om = V0.resolve_role(mj["args"].get("over"), ir_m["roles"])
            add("scope", "SCOPE_OVER_NOTE", "note",
                f"aggregate over {oi} vs {om} (scope EXCLUDED; recorded only)")
            if oi and om and oi != om:
                add("scope", "SCOPE_MISMATCH_NOTE", "note",
                    f"over-role mismatch {oi} vs {om}; scope EXCLUDED: zero "
                    f"verdict influence (spec R3)")
            fi_v, fm_v = ni["args"].get("value"), mj["args"].get("value")
            if (fi_v or "").strip() and (fm_v or "").strip():
                add("scope", "SCOPE_FILTER_NOTE", "note",
                    f"aggregate filter {fi_v!r} vs {fm_v!r} (scope EXCLUDED; "
                    f"recorded only)")
            fi, fm = V0.agg_function(ni), V0.agg_function(mj)
            if fi and fm and fi != fm:
                add("ops", "AGG_FN_MISMATCH", "contradict",
                    f"aggregate function {fi} vs {fm} (both explicit; spec R6)")
                continue
            if (fi is None) != (fm is None):
                add("ops", "AGG_FN_UNRESOLVED", "unknown",
                    "aggregate function explicit on exactly one side")
                continue
            add("ops", "OP_ALIGNED:aggregate", "note", "aggregate paired")
        elif op == "branch":
            compare_predicate(ni, mj, ir_i, ir_m, text_i, text_m, add)

    # ABSENT-on-memory rule (spec section 6.3): contradiction only under
    # complete(memory); otherwise unknown.
    for ni in unpaired_i:
        op = ni["op"]
        if cert_m_complete:
            add("ops", f"REQ_OP_MISSING_UNDER_COMPLETE:{op}", "contradict",
                f"required {op} absent in complete memory")
        else:
            add("ops", f"REQ_OP_MISSING_INCOMPLETE:{op}", "unknown",
                f"required {op} absent in memory, memory not complete")

    # extra-op policy (spec section 10)
    for mj in unpaired_m:
        op = mj["op"]
        if op == "write":
            a = V0.write_action(mj)
            if a in V0.EFFECTFUL_ACTIONS:
                add("extras", f"EXTRA_EFFECTFUL_OP:write:{a}", "contradict",
                    f"memory has extra effectful write action={a}")
            elif a in V0.BENIGN_WRITE_ACTIONS:
                add("extras", f"EXTRA_BENIGN:write:{a}", "benign",
                    "extra non-mutating report write")
            else:
                add("extras", "EXTRA_OP_UNCLASSIFIED:write", "unknown",
                    f"extra write with unresolved action class ({a!r})")
        elif op == "branch":
            eff = [e for k in ("then_effects", "else_effects")
                   for e in V0.branch_effects(mj, k)]
            if any((V0.norm_text(e.get("action")) or "other") in V0.EFFECTFUL_ACTIONS
                   for e in eff):
                add("extras", "EXTRA_EFFECTFUL_OP:branch", "contradict",
                    "memory has extra effectful branch")
            else:
                add("extras", "EXTRA_BENIGN:branch", "benign",
                    "extra non-mutating branch")
        else:
            add("extras", f"EXTRA_BENIGN:{op}", "benign",
                f"extra non-mutating {op}")


# ---------------------------------------------------------------------------
# verdict record helpers
# ---------------------------------------------------------------------------

_SEV = {"note": 0, "benign": 1, "unknown": 2, "contradict": 3}


def _rollup(reasons):
    """Machine-readable per-component trace: max severity per component + the
    ordered list of its codes."""
    comp = {}
    for r in reasons:
        c = comp.setdefault(r["component"], {"level": "note", "codes": []})
        if _SEV[r["level"]] > _SEV[c["level"]]:
            c["level"] = r["level"]
        c["codes"].append(r["code"])
    return comp


def _record(verdict, reasons, cert_i, cert_m):
    return {"verdict": verdict, "reasons": reasons,
            "components": _rollup(reasons),
            "certificates": {"instruction": cert_i, "memory": cert_m},
            "rule_version": RULE_VERSION}


# ---------------------------------------------------------------------------
# main entry (S2_SPEC.md sections 5, 9, 11)
# ---------------------------------------------------------------------------

def compare(ir_i, text_i, ir_m, text_m, require_branch=True):
    """Adjudicated three-way comparison, S2-rc1 frozen rules.

    verdict: 'contradict' iff any contradiction reason fires (non-compensatory);
    else 'unknown' iff any unresolved task-required component (incl. UNMEAS
    abstains); else 'match'. No continuous score.
    """
    reasons = []

    def add(component, code, level, detail="", probe=None):
        r = {"component": component, "code": code, "level": level, "detail": detail}
        if probe is not None:
            r["probe"] = probe
        reasons.append(r)

    cert_i = certificate(ir_i, text_i, require_branch)
    cert_m = certificate(ir_m, text_m, require_branch)

    # spec section 9, rule order: invalid -> vacuous instruction -> vacuous memory
    if not cert_i["checks"].get("valid") or not cert_m["checks"].get("valid"):
        add("ir", "IR_INVALID", "unknown", "malformed IR on at least one side")
        return _record("unknown", reasons, cert_i, cert_m)

    pres_i = V0.present_nodes(ir_i)
    pres_m = V0.present_nodes(ir_m)
    n_required = (len([n for n in pres_i if n["op"] != "finish"])
                  + sum(1 for r in _ROLES if ir_i["roles"][r]["status"] == "present")
                  + int(ir_i["termination"]["status"] == "present"))
    if n_required == 0:
        add("ir", "VACUOUS_INSTRUCTION", "unknown",
            "instruction IR carries no requirement (no present node/role/termination)")
    elif not pres_m:
        add("ir", "VACUOUS_MEMORY", "unknown",
            "memory IR has no present node; nothing is comparable")
    else:
        cm = cert_m["complete"]
        compare_roles(ir_i, ir_m, cm, add)
        compare_ops(pres_i, pres_m, ir_i, ir_m, text_i, text_m, cm, add)
        V0.compare_ordering(pres_i, pres_m, _V0_PASSTHROUGH_ELIG, add)
        V0.compare_termination(ir_i, ir_m, cm, _V0_PASSTHROUGH_ELIG, add)
        V0.compare_direction(ir_i, ir_m, _V0_PASSTHROUGH_ELIG, add)

    levels = {r["level"] for r in reasons}
    if "contradict" in levels:
        final = "contradict"
    elif "unknown" in levels:
        final = "unknown"
    else:
        final = "match"
    return _record(final, reasons, cert_i, cert_m)


def compare_jsonl(ir_i, text_i, ir_m, text_m, require_branch=True):
    """Convenience: compare() with the verdict record serialized as one JSON line.
    Used by the scoring harness; not part of the frozen rule surface."""
    return json.dumps(compare(ir_i, text_i, ir_m, text_m, require_branch),
                      ensure_ascii=False, sort_keys=False)


if __name__ == "__main__":
    print(f"s2_comparator {RULE_VERSION} OK")
