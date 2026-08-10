"""Deterministic phi+d comparator v0 (lane A pre-SFT baseline).

Implements the adjudicated S2 semantics (thread 019fe66c) over phi_ir/v0 IRs:

- Three-way verdict {match, contradict, unknown}; NO continuous score.
- Field-local completeness certificate: valid IR + required fields present +
  evidence spans nonempty verbatim substrings of source + no unknown-in-used-fields
  + branch predicates/effects populated + relevant subgraph connected from an
  evidenced root op to an evidenced verify/finish or supported termination.
- Truth table: present-present equivalent -> match; present vs incompatible ->
  contradict; requirement present + memory ABSENT + complete(memory) -> contradict;
  requirement present + memory ABSENT + not complete -> unknown; instruction-absent
  + memory extra EFFECTFUL op -> contradict; extra non-mutating read/verify/report
  -> benign; either side invalid -> unknown. Final match requires every
  task-required component comparable+matching; any unresolved required component
  -> unknown.
- Predicate canonical decision function: aligned attribute anchor + normalized
  operator + branch-effect mapping. Operator complementation {><=>, >=<<, ==!=}
  + effect swap = equivalent; complement without swap = contradiction; threshold
  LITERAL comparison only when both sides bind the same task parameter (else
  unknown); polarity is metadata, never a veto.
- Vetoes (round-1 list): src/dest reversal; required effectful op missing under
  complete(memory); extra effectful op; conflicting action target/control
  dependency; capture-before-delete violation; explicitly incompatible
  termination; aggregate-function mismatch when both explicit; child-set
  scope-signature mismatch when both structured. NOT vetoes: surface-entity
  mismatch, raw attribute-string mismatch, raw threshold mismatch w/o anchor,
  missing finish node alone, op-count mismatch.
- Carrier-agnostic predicate reading: predicate payload is read ONLY from branch
  nodes' args.predicate / then_effects / else_effects. Guided-schema filler keys
  on other ops (a read's args.predicate, function/action junk on non-matching
  ops) are IGNORED.

Veto-field eligibility (pilot/peval/phi_d/audit_expanded/field_metrics.json,
present at run time) is consumed via VETO_ELIGIBILITY: fields the audit demotes
are softened per its rule — "positive-only veto / soft evidence
(unknown-if-absent)" keeps both-sides-present contradictions but demotes
absence-based ones to unknown; "excluded from veto fields" demotes all of that
field's contradictions to unknown.

Pure stdlib. No sklearn, no training, deterministic. Labels/cells/archetypes
never enter this module.
"""
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent          # pilot/peval/phi_d/comparator_v0
PHI_D = HERE.parent                                     # pilot/peval/phi_d
sys.path.insert(0, str(PHI_D))
import common as C                                      # noqa: E402  (enums + validate_ir; label-free)

VERDICTS = ("match", "contradict", "unknown")

OP_COMPLEMENT = {">": "<=", "<=": ">", ">=": "<", "<": ">=", "==": "!=", "!=": "=="}

EFFECTFUL_ACTIONS = {"set", "insert", "delete", "move", "archive", "notify"}
BENIGN_WRITE_ACTIONS = {"report"}                       # non-mutating write actions
NONMUTATING_OPS = {"read", "list", "verify"}            # extra instances are benign
CAPTURE_ACTIONS = {"archive", "insert", "report"}       # writes that can carry a capture
AGG_FUNC_EXPLICIT = {"count", "sum", "min", "max", "avg", "exists"}  # 'other' = not explicit

_ROLES = C.CANONICAL_ROLES

# stopwords for attribute-anchor tokenization (surface noise; keeps content words)
_STOP = {"the", "a", "an", "of", "s", "row", "rows", "table", "current", "is",
         "number", "total", "per", "its", "it", "this", "that", "for", "in",
         "on", "to", "from", "into", "value", "field", "column"}

# ---------------------------------------------------------------------------
# normalization helpers
# ---------------------------------------------------------------------------

def norm_text(s):
    """Lowercase, de-quote, alnum-token join. None -> ''."""
    if s is None:
        return ""
    s = str(s).lower().strip()
    s = s.replace("'s ", " ").replace("'s", " ")
    s = re.sub(r"[^a-z0-9.]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def norm_value(s):
    """Literal-value normalization: quotes/case/whitespace-insensitive; numerics canonical."""
    t = norm_text(s).strip("'\"` ")
    if isinstance(s, str):
        t = re.sub(r"^[ '\"`]+|[ '\"`]+$", "", s.lower().strip())
        t = re.sub(r"\s+", " ", t)
    try:
        return "%g" % float(t)
    except (TypeError, ValueError):
        return t


def _tokens(s):
    return {t for t in norm_text(s).split() if t and t not in _STOP}


def anchors_match(a, b):
    """Attribute-anchor alignment: two normalized attribute strings bind the same
    task parameter iff their content-token sets are equal, nested, or overlap >= 0.5."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return False
    if ta == tb or ta <= tb or tb <= ta:
        return True
    inter = len(ta & tb)
    union = len(ta | tb)
    return union > 0 and inter / union >= 0.5


def resolve_role(target, roles):
    """Map a free-form target string onto the canonical 6-role vocabulary via the
    side's own role surfaces (alpha-renaming). Returns role name or None."""
    if target is None:
        return None
    t = norm_text(target)
    if not t:
        return None
    if t.replace(" ", "_") in _ROLES:
        return t.replace(" ", "_")
    for r in _ROLES:
        surf = norm_text((roles.get(r) or {}).get("surface"))
        if surf and (surf in t or t in surf):
            return r
    return None


# ---------------------------------------------------------------------------
# IR access helpers (op-relevant args ONLY; guided-schema filler ignored)
# ---------------------------------------------------------------------------

def present_nodes(ir):
    return [n for n in ir["nodes"] if n.get("status") == "present"]


def node_target_role(node, roles):
    return resolve_role(node["args"].get("target"), roles)


def write_action(node):
    a = node["args"].get("action")
    return norm_text(a) if a else None


def agg_function(node):
    f = node["args"].get("function")
    return f if f in AGG_FUNC_EXPLICIT else None          # 'other'/None: not explicit


def branch_pred(node):
    return node["args"].get("predicate") if node["op"] == "branch" else None


def pred_populated(pred):
    return (isinstance(pred, dict)
            and all(k in pred for k in ("attribute", "op", "value", "polarity"))
            and all((pred[k] or {}).get("status") == "present" for k in
                    ("attribute", "op", "value", "polarity")))


def branch_effects(node, key):
    effs = node["args"].get(key) or []
    return [e for e in effs if isinstance(e, dict)]


# ---------------------------------------------------------------------------
# completeness certificate (adjudicated (b))
# ---------------------------------------------------------------------------

def _verbatim(evidence, text):
    if not evidence or not str(evidence).strip():
        return False
    ev = re.sub(r"\s+", " ", str(evidence)).strip()
    tx = re.sub(r"\s+", " ", text or "")
    return ev in tx


def certificate(ir, text, require_branch=True):
    """Field-local completeness certificate. Returns dict with per-check bools and
    `complete` = AND of applicable checks. ABSENT is a trustworthy active omission
    only under a complete certificate."""
    out = {"require_branch": require_branch, "checks": {}, "stats": {}}
    ok, _ec, _detail = C.validate_ir(ir)
    out["checks"]["valid"] = bool(ok)
    if not ok:
        out["complete"] = False
        return out

    # -- required fields present (schema-level, already enforced; re-asserted) --
    out["checks"]["required_fields"] = all(
        k in ir for k in ("schema", "roles", "nodes", "termination")) and bool(ir["nodes"])

    # -- evidence spans: nonempty verbatim substrings of source for present fields --
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
            pred = branch_pred(n) or {}
            for fk in ("attribute", "op", "value", "polarity"):
                w = (pred.get(fk) or {})
                _ev(w.get("status"), w.get("evidence"))
    _ev(ir["termination"].get("status"), ir["termination"].get("evidence"))
    out["stats"]["evidence"] = {"present_slots": ev_slots, "missing": ev_missing,
                                "nonverbatim": ev_nonverbatim}
    out["checks"]["evidence_verbatim"] = (ev_missing == 0 and ev_nonverbatim == 0)

    # -- no unknown-in-used-fields: roles, nodes, termination, predicate subfields --
    unknown_roles = sum(1 for rv in ir["roles"].values() if rv.get("status") == "unknown")
    unknown_pred_subs = 0
    for n in ir["nodes"]:
        if n["op"] == "branch" and n.get("status") == "present":
            pred = branch_pred(n) or {}
            unknown_pred_subs += sum(
                1 for fk in ("attribute", "op", "value", "polarity")
                if (pred.get(fk) or {}).get("status") == "unknown")
    out["stats"]["unknown"] = {"roles": unknown_roles, "nodes": n_unknown_nodes,
                               "predicate_subfields": unknown_pred_subs,
                               "termination": int(ir["termination"].get("status") == "unknown")}
    out["checks"]["no_unknown_in_used_fields"] = (
        unknown_roles == 0 and n_unknown_nodes == 0 and unknown_pred_subs == 0
        and ir["termination"].get("status") != "unknown")

    # -- branch predicates/effects populated (certificate clause; mode flag) --
    if require_branch:
        bad = 0
        for n in ir["nodes"]:
            if n["op"] == "branch" and n.get("status") == "present":
                pred = branch_pred(n)
                if (not pred_populated(pred)
                        or not branch_effects(n, "then_effects")
                        or not branch_effects(n, "else_effects")):
                    bad += 1
        out["checks"]["branch_populated"] = (bad == 0)
        out["stats"]["branch_unpopulated"] = bad

    # -- relevant subgraph connected: evidenced root -> evidenced verify/finish,
    #    or supported termination --
    pnodes = present_nodes(ir)
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
# veto-field eligibility (audit_expanded/field_metrics.json consumed at run time)
# ---------------------------------------------------------------------------

def load_veto_eligibility(audit_dir):
    """Reads the audit per-field gate table. Returns {field: 'hard'|'positive_only'|'excluded'}
    plus the raw map. Missing table -> every field 'hard' (caller decides modes)."""
    fm_path = pathlib.Path(audit_dir) / "field_metrics.json"
    raw, elig = {}, {}
    if fm_path.exists():
        fm = json.load(open(fm_path))
        for field, f in (fm.get("fields") or {}).items():
            ve = (f or {}).get("veto_eligibility") or ""
            raw[field] = ve
            if ve.startswith("excluded"):
                elig[field] = "excluded"
            elif ve.startswith("positive-only"):
                elig[field] = "positive_only"
            else:
                elig[field] = "hard"
    return elig, raw


_ELIGIBILITY_FIELDS = ("pred_attribute", "pred_op", "pred_value", "pred_polarity",
                       "pred_all", "branch_effects", "direction", "scope",
                       "archive_capture", "roles_required", "termination")


def _elig(eligibility, field):
    """'hard' keeps adjudicated contradictions; 'positive_only' keeps both-sides-
    present contradictions but absence -> unknown; 'excluded' demotes all of the
    field's contradictions to unknown."""
    return (eligibility or {}).get(field, "hard")


# ---------------------------------------------------------------------------
# structural branch-effect mapping (values compared only when audit-eligible)
# ---------------------------------------------------------------------------

def _norm_effect(e, roles):
    action = norm_text(e.get("action")) or "other"
    return {"action": action,
            "target_role": resolve_role(e.get("target"), roles),
            "target_norm": norm_text(e.get("target")),
            "value_norm": norm_value(e.get("value")),
            "effectful": action in EFFECTFUL_ACTIONS}


def cmp_effect_lists(le, lm, roles_i, roles_m, compare_values):
    """Greedy multiset pairing of EFFECTFUL effects. Pair requires action equal,
    targets non-conflicting (both role-resolved and different = conflict), and
    (only when compare_values) values non-conflicting. Returns
    'match' | 'mismatch' (no conflict pair, unpaired effectful left) |
    'conflict' (same action with resolved-different targets / differing literals)."""
    A = [e for e in (_norm_effect(x, roles_i) for x in le) if e["effectful"]]
    B = [e for e in (_norm_effect(x, roles_m) for x in lm) if e["effectful"]]
    used = [False] * len(B)
    unmatched_a = []
    for a in A:
        hit = None
        conflict = False
        for j, b in enumerate(B):
            if used[j] or a["action"] != b["action"]:
                continue
            if (a["target_role"] and b["target_role"]
                    and a["target_role"] != b["target_role"]):
                conflict = True
                continue
            if compare_values and a["value_norm"] and b["value_norm"] \
                    and a["value_norm"] != b["value_norm"]:
                conflict = True
                continue
            hit = j
            break
        if hit is not None:
            used[hit] = True
        elif conflict:
            unmatched_a.append(("conflict", a))
        else:
            unmatched_a.append(("absent", a))
    if any(k == "conflict" for k, _ in unmatched_a):
        return "conflict"
    if unmatched_a or not all(used):
        return "mismatch"
    return "match"


# ---------------------------------------------------------------------------
# predicate canonical decision function (adjudicated (d))
# ---------------------------------------------------------------------------

_HALT_RE = re.compile(r"\b(stop|abort|halt|do not proceed|leave untouched|"
                      r"without (updat|writ|sav|apply|chang|modif))")


def compare_branch(ni, nm, roles_i, roles_m, eligibility, add):
    pi, pm = branch_pred(ni), branch_pred(nm)
    if not pred_populated(pi):
        add("predicate", "PRED_INSTRUCTION_UNPOPULATED", "unknown",
            "instruction branch predicate/effects not fully populated")
        return
    if not pred_populated(pm):
        add("predicate", "PRED_MEMORY_UNPOPULATED", "unknown",
            "memory branch predicate not fully populated (unknown-if-absent)")
        return
    oi, om = pi["op"]["value"], pm["op"]["value"]
    ai, am = pi["attribute"]["value"], pm["attribute"]["value"]
    vi, vm = pi["value"]["value"], pm["value"]["value"]
    anchor = anchors_match(ai, am)
    add("predicate", "PRED_ANCHOR_" + ("SHARED" if anchor else "CROSS"), "note",
        f"attribute anchor {'aligned' if anchor else 'not aligned'}: "
        f"{norm_text(ai)!r} vs {norm_text(am)!r}")
    # audit-gated channels: op-relation decisions ride pred_op (positive-only
    # keeps both-sides-present contradictions); effect-mapping disagreements
    # ride branch_effects (excluded -> demoted to unknown, never contradiction)
    op_veto = _elig(eligibility, "pred_op") in ("hard", "positive_only")
    fx_veto = _elig(eligibility, "branch_effects") in ("hard", "positive_only")

    ti, tm = branch_effects(ni, "then_effects"), branch_effects(nm, "then_effects")
    ei, em = branch_effects(ni, "else_effects"), branch_effects(nm, "else_effects")
    if not ti and not ei:
        fx1 = fx2 = "match"     # instruction states no outcomes: mapping n/a
        add("predicate", "PRED_EFFECTS_INSTRUCTION_EMPTY", "note",
            "instruction branch carries no effect payload; mapping skipped")
    else:
        if oi == om:
            fx1 = cmp_effect_lists(ti, tm, roles_i, roles_m, True)
            fx2 = cmp_effect_lists(ei, em, roles_i, roles_m, True)
            rel_code = "PRED_EFFECT_MISMATCH"
        elif OP_COMPLEMENT.get(oi) == om:
            fx1 = cmp_effect_lists(ti, em, roles_i, roles_m, True)
            fx2 = cmp_effect_lists(ei, tm, roles_i, roles_m, True)
            rel_code = "PRED_COMPLEMENT_NO_SWAP"
        else:
            add("predicate", "PRED_OP_MISMATCH",
                "contradict" if op_veto else "unknown",
                f"operator mismatch {oi} vs {om}")
            return
        if fx1 == fx2 == "match":
            if oi != om:
                add("predicate", "PRED_COMPLEMENT_SWAP_EQUIV", "note",
                    f"{oi} vs {om} with swapped branch effects: equivalent")
            else:
                add("predicate", "PRED_OP_EFFECTS_MATCH", "note",
                    f"same operator {oi}, branch effects aligned")
        else:
            add("predicate", rel_code,
                "contradict" if fx_veto else "unknown",
                f"op {oi} vs {om}; effect mapping {fx1}/{fx2}")
            return

    # threshold literal comparison: only under a shared task-parameter anchor
    if bool((vi or "").strip()) and bool((vm or "").strip()):
        if anchor:
            if norm_value(vi) == norm_value(vm):
                add("predicate", "PRED_THRESHOLD_ANCHORED_EQUAL", "note",
                    f"threshold {vi!r} == {vm!r} under shared anchor")
            else:
                soft = _elig(eligibility, "pred_value") == "excluded"
                add("predicate", "PRED_THRESHOLD_LITERAL_MISMATCH",
                    "unknown" if soft else "contradict",
                    f"threshold {vi!r} vs {vm!r} under shared anchor"
                    + (" (demoted: pred_value excluded)" if soft else ""))
        else:
            add("predicate", "PRED_THRESHOLD_NO_ANCHOR", "unknown",
                "literal comparison forbidden: no shared task-parameter anchor")
    elif bool((vi or "").strip()) != bool((vm or "").strip()):
        add("predicate", "PRED_VALUE_ASYMMETRIC", "unknown",
            "threshold literal present on exactly one side")


# ---------------------------------------------------------------------------
# component comparisons
# ---------------------------------------------------------------------------

def _pair_nodes(pres_i, pres_m):
    """Order-stable greedy pairing: same op; writes additionally pair by action
    class (effectful action exact; non-effectful with non-effectful)."""
    pairs, used = [], [False] * len(pres_m)

    def action_class(n):
        a = write_action(n)
        return a if a in EFFECTFUL_ACTIONS else None

    for ni in pres_i:
        want = action_class(ni) if ni["op"] == "write" else None
        for j, mj in enumerate(pres_m):
            if used[j] or mj["op"] != ni["op"]:
                continue
            if ni["op"] == "write":
                if want is not None and action_class(mj) != want:
                    continue
                if want is None and action_class(mj) is not None:
                    continue
            pairs.append((ni, mj))
            used[j] = True
            break
    paired_i = {id(ni) for ni, _ in pairs}
    unpaired_i = [n for n in pres_i if id(n) not in paired_i]
    unpaired_m = [n for j, n in enumerate(pres_m) if not used[j]]
    return pairs, unpaired_i, unpaired_m


def compare_roles(ir_i, ir_m, cert_m_complete, eligibility, add):
    for r in _ROLES:
        si = ir_i["roles"][r]["status"]
        sm = ir_m["roles"][r]["status"]
        if si == "present":
            if sm == "present":
                add("roles", f"ROLE_ALIGNED:{r}", "note",
                    "present both sides (surfaces alpha-renamed)")
            elif sm == "absent":
                if _elig(eligibility, "roles_required") == "excluded":
                    add("roles", f"ROLE_OMITTED_SOFT:{r}", "unknown",
                        "required role absent in memory (demoted: roles_required "
                        "excluded)")
                elif cert_m_complete:
                    add("roles", f"ROLE_OMITTED_UNDER_COMPLETE:{r}", "contradict",
                        "required role absent in complete memory")
                else:
                    add("roles", f"ROLE_OMITTED_INCOMPLETE:{r}", "unknown",
                        "required role absent in memory, memory not complete")
            else:
                add("roles", f"ROLE_MEMORY_STATUS_UNKNOWN:{r}", "unknown",
                    "memory role status unknown")
        elif si == "absent" and sm == "present":
            add("roles", f"ROLE_EXTRA_MEMORY:{r}", "benign",
                "extra role in memory only (not effectful by itself)")


def compare_ops(pres_i, pres_m, ir_i, ir_m, cert_m_complete, eligibility, add):
    req_i = [n for n in pres_i if n["op"] != "finish"]   # finish is bookkeeping:
    mem_m = [n for n in pres_m if n["op"] != "finish"]   # missing-finish alone is
    pairs, unpaired_i, unpaired_m = _pair_nodes(req_i, mem_m)  # never a veto

    for ni, mj in pairs:
        op = ni["op"]
        if op in ("read", "list", "verify"):
            ti, tm = node_target_role(ni, ir_i["roles"]), node_target_role(mj, ir_m["roles"])
            if ti and tm and ti != tm:
                add("ops", f"TARGET_CONFLICT:{op}", "contradict",
                    f"{op} target role {ti} vs {tm}")
                continue
            add("ops", f"OP_ALIGNED:{op}", "note", f"{op} paired")
        elif op == "write":
            ti, tm = node_target_role(ni, ir_i["roles"]), node_target_role(mj, ir_m["roles"])
            if ti and tm and ti != tm:
                add("ops", "TARGET_CONFLICT:write", "contradict",
                    f"write target role {ti} vs {tm}")
                continue
            add("ops", "OP_ALIGNED:write", "note",
                f"write action {write_action(ni)} paired")
        elif op == "aggregate":
            fi, fm = agg_function(ni), agg_function(mj)
            if fi and fm and fi != fm:
                add("ops", "AGG_FN_MISMATCH", "contradict",
                    f"aggregate function {fi} vs {fm} (both explicit)")
                continue
            if (fi is None) != (fm is None):
                add("ops", "AGG_FN_UNRESOLVED", "unknown",
                    "aggregate function explicit on exactly one side")
                continue
            oi = resolve_role(ni["args"].get("over"), ir_i["roles"])
            om = resolve_role(mj["args"].get("over"), ir_m["roles"])
            if oi and om and oi != om:
                soft = _elig(eligibility, "scope") == "excluded"
                add("ops", "SCOPE_MISMATCH", "unknown" if soft else "contradict",
                    f"aggregate over {oi} vs {om}"
                    + (" (demoted: scope excluded)" if soft else ""))
                continue
            add("ops", "OP_ALIGNED:aggregate", "note", "aggregate paired")
        elif op == "branch":
            compare_branch(ni, mj, ir_i["roles"], ir_m["roles"], eligibility, add)

    for ni in unpaired_i:
        op = ni["op"]
        if cert_m_complete:
            add("ops", f"REQ_OP_MISSING_UNDER_COMPLETE:{op}", "contradict",
                f"required {op} absent in complete memory")
        else:
            add("ops", f"REQ_OP_MISSING_INCOMPLETE:{op}", "unknown",
                f"required {op} absent in memory, memory not complete")

    for mj in unpaired_m:
        op = mj["op"]
        if op == "write":
            a = write_action(mj)
            if a in EFFECTFUL_ACTIONS:
                add("extras", f"EXTRA_EFFECTFUL_OP:write:{a}", "contradict",
                    f"memory has extra effectful write action={a}")
            elif a in BENIGN_WRITE_ACTIONS:
                add("extras", f"EXTRA_BENIGN:write:{a}", "benign",
                    "extra non-mutating report write")
            else:
                add("extras", "EXTRA_OP_UNCLASSIFIED:write", "unknown",
                    f"extra write with unresolved action class ({a!r})")
        elif op == "branch":
            eff = [e for k in ("then_effects", "else_effects")
                   for e in branch_effects(mj, k)]
            neff = (_norm_effect({"action": e.get("action")}, ir_m["roles"]) for e in eff)
            if any(x["effectful"] for x in neff):
                add("extras", "EXTRA_EFFECTFUL_OP:branch", "contradict",
                    "memory has extra effectful branch")
            else:
                add("extras", "EXTRA_BENIGN:branch", "benign",
                    "extra non-mutating branch")
        else:
            add("extras", f"EXTRA_BENIGN:{op}", "benign",
                f"extra non-mutating {op}")


def _precedes(early, late, byid_present):
    """True iff `early` ->* `late`, i.e. `late` transitively depends_on `early`."""
    target = early["id"]
    seen, stack = set(), list(late.get("depends_on", []))
    while stack:
        u = stack.pop()
        if u == target:
            return True
        if u in seen:
            continue
        seen.add(u)
        n = byid_present.get(u)
        if n is not None:
            stack.extend(n.get("depends_on", []))
    return False


def _captureish(n):
    """A capture persists data out of the condemned row: archive/insert/report
    write, or an aggregate that reads it out. Plain read/list/verify do NOT
    capture — a read-then-delete sequence preserves nothing."""
    return n["op"] == "aggregate" or (
        n["op"] == "write" and write_action(n) in CAPTURE_ACTIONS)


def _captures_before(delete_node, nodes, byid):
    return [n for n in nodes
            if n is not delete_node and n["op"] != "branch"
            and _captureish(n) and _precedes(n, delete_node, byid)]


def compare_ordering(pres_i, pres_m, eligibility, add):
    byid_i = {n["id"]: n for n in pres_i}
    byid_m = {n["id"]: n for n in pres_m}
    del_i = [n for n in pres_i if n["op"] == "write" and write_action(n) == "delete"]
    del_m = [n for n in pres_m if n["op"] == "write" and write_action(n) == "delete"]
    constrained = [d for d in del_i if _captures_before(d, pres_i, byid_i)]
    if not constrained:
        return
    if not del_m:
        add("ordering", "ORDER_DELETE_MISSING_IN_MEMORY", "unknown",
            "capture-before-delete constraint active but memory has no delete node")
        return
    d_m = del_m[0]
    cap_m = _captures_before(d_m, pres_m, byid_m)
    if cap_m:
        add("ordering", "ORDER_CAPTURE_BEFORE_DELETE_OK", "note",
            "memory capture precedes delete")
        return
    reversed_m = [n for n in pres_m
                  if (n["op"] in ("read", "list", "aggregate", "verify")
                      or (n["op"] == "write" and write_action(n) in CAPTURE_ACTIONS))
                  and n["op"] != "branch" and _precedes(d_m, n, byid_m)]
    soft = _elig(eligibility, "archive_capture") == "excluded"
    if reversed_m:
        add("ordering", "ORDER_CAPTURE_AFTER_DELETE",
            "unknown" if soft else "contradict",
            "memory deletes before capture while instruction requires capture-first"
            + (" (demoted: archive_capture excluded)" if soft else ""))
    else:
        add("ordering", "ORDER_NO_CAPTURE_IN_MEMORY", "unknown",
            "memory has delete but no capture-ish node; order unverifiable")


def compare_termination(ir_i, ir_m, cert_m_complete, eligibility, add):
    ti, tm = ir_i["termination"], ir_m["termination"]
    if ti["status"] != "present":
        if tm["status"] == "present":
            add("termination", "TERM_EXTRA_MEMORY", "benign",
                "termination stated on memory side only")
        return
    soft = _elig(eligibility, "termination") == "excluded"
    if tm["status"] == "unknown":
        add("termination", "TERM_MEMORY_UNKNOWN", "unknown",
            "memory termination status unknown")
        return
    if tm["status"] == "absent":
        if soft:
            add("termination", "TERM_ABSENT_SOFT", "unknown",
                "instruction termination present, memory absent (demoted: "
                "termination excluded)")
        elif cert_m_complete:
            add("termination", "TERM_ABSENT_UNDER_COMPLETE", "contradict",
                "memory omits termination under complete certificate")
        else:
            add("termination", "TERM_ABSENT_INCOMPLETE", "unknown",
                "memory omits termination, memory not complete")
        return
    hi = bool(_HALT_RE.search(norm_text(ti.get("evidence"))))
    hm = bool(_HALT_RE.search(norm_text(tm.get("evidence"))))
    if hi != hm:
        add("termination", "TERM_INCOMPATIBLE",
            "unknown" if soft else "contradict",
            "explicit halt/negation marker on exactly one side"
            + (" (demoted: termination excluded)" if soft else ""))
    else:
        add("termination", "TERM_ALIGNED", "note", "termination compatible")


def compare_direction(ir_i, ir_m, eligibility, add):
    """src/dest reversal or opposite inc/dec roles. Only fires when both sides'
    transfer orientation is resolvable; demoted to unknown when audit-excluded."""
    def orientation(ir):
        roles = ir["roles"]
        moves, incdec = [], {}
        for n in present_nodes(ir):
            if n["op"] != "write":
                continue
            a = write_action(n)
            v_raw = (n["args"].get("value") or "")
            v = v_raw.lower()
            if a == "move":
                m = re.search(r"from\s+(.+?)\s+to\s+(.+)$", v)
                if m:
                    moves.append((resolve_role(m.group(1), roles),
                                  resolve_role(m.group(2), roles)))
                continue
            if re.search(r"\b(increase|increment|add|credit|raise|gain)\b|\+\s*\d", v):
                d = "inc"
            elif re.search(r"\b(decrease|decrement|subtract|debit|reduce|drop)\b|-\s*\d", v):
                d = "dec"
            else:
                continue
            t = node_target_role(n, roles)
            if t in ("source", "destination"):
                incdec[t] = d
        return moves, incdec

    if not any(ir_i["roles"][r]["status"] == "present" for r in ("source", "destination")):
        return                                   # not a transfer task
    moves_i, inc_i = orientation(ir_i)
    moves_m, inc_m = orientation(ir_m)
    soft = _elig(eligibility, "direction") == "excluded"
    lvl = "unknown" if soft else "contradict"
    tail = " (demoted: direction excluded)" if soft else ""
    if moves_i and moves_m:
        (si, di), (sm, dm) = moves_i[0], moves_m[0]
        if all(x is not None for x in (si, di, sm, dm)):
            if (si, di) == (dm, sm) and (si, di) != (sm, dm):
                add("direction", "SRC_DEST_REVERSAL", lvl,
                    f"move endpoints reversed: {si}->{di} vs {sm}->{dm}" + tail)
                return
            if (si, di) == (sm, dm):
                add("direction", "DIRECTION_ALIGNED", "note",
                    f"move endpoints aligned: {si}->{di}")
                return
    if inc_i.get("source") and inc_i.get("destination") and \
       inc_m.get("source") and inc_m.get("destination"):
        if inc_i["source"] == inc_m["destination"] and \
           inc_i["destination"] == inc_m["source"] and \
           inc_i["source"] != inc_i["destination"]:
            add("direction", "SRC_DEST_REVERSAL_INCDEC", lvl,
                "opposite inc/dec roles across sides" + tail)


# ---------------------------------------------------------------------------
# main entry
# ---------------------------------------------------------------------------

def compare(ir_i, text_i, ir_m, text_m, require_branch=True, eligibility=None):
    """Adjudicated three-way comparison. Returns {verdict, reasons, certificates}.
    verdict: 'contradict' iff any contradiction reason fires; else 'unknown' iff
    any unresolved required component; else 'match'."""
    reasons = []

    def add(component, code, level, detail=""):
        reasons.append({"component": component, "code": code,
                        "level": level, "detail": detail})

    cert_i = certificate(ir_i, text_i, require_branch)
    cert_m = certificate(ir_m, text_m, require_branch)
    if not cert_i["checks"].get("valid") or not cert_m["checks"].get("valid"):
        add("ir", "IR_INVALID", "unknown", "malformed IR on at least one side")
        return {"verdict": "unknown", "reasons": reasons,
                "certificates": {"instruction": cert_i, "memory": cert_m}}

    pres_i = present_nodes(ir_i)
    pres_m = present_nodes(ir_m)
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
        compare_roles(ir_i, ir_m, cm, eligibility, add)
        compare_ops(pres_i, pres_m, ir_i, ir_m, cm, eligibility, add)
        compare_ordering(pres_i, pres_m, eligibility, add)
        compare_termination(ir_i, ir_m, cm, eligibility, add)
        compare_direction(ir_i, ir_m, eligibility, add)

    levels = {r["level"] for r in reasons}
    if "contradict" in levels:
        final = "contradict"
    elif "unknown" in levels:
        final = "unknown"
    else:
        final = "match"
    return {"verdict": final, "reasons": reasons,
            "certificates": {"instruction": cert_i, "memory": cert_m}}


if __name__ == "__main__":
    print("skeleton OK")
