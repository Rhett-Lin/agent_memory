"""S2-rc2 comparator for the phi+d line — post-round-3 candidate, frozen rules.

Implements S2_RC2_SPEC.md. The estimand is the registered P-relation of
pilot/program_dsl.py: same abstract step set + partial order + operator polarity
(operator field, complementation-normalized) + write-target roles; concrete
thresholds/entities/effect literals are NOT registered (note-only diagnostics).

Deterministic, stdlib-only, CPU-only, no I/O inside compare(). Labels
(P/cell/family/archetype/domain), sealed truth, pair metadata, and rollout data
NEVER enter this module: inputs are two phi_ir/v0 IRs and their source texts.

Relationship to rc1: rc1 (pilot/peval/phi_d/s2/, rc1_hash 96901e3d...) is
permanently locked for evidence. rc2 does not edit it; it IMPORTS the rc1
certificate + value marks read-only (R8 sustained — bit-for-bit, hash-pinned in
freeze_rc2.json) via importlib under a private module name, because this file
intentionally shares the rc1 comparator's filename per the deliverable contract.

Frozen read-only dependencies (hash-pinned): common (validate_ir + canonical
roles), audit_expanded (toks — attribute diagnostic probe only), comparator_v0
(normalize/resolve_role/branch helpers, OP_COMPLEMENT, action-class constants,
direction + termination scaffolding), rc1 s2_comparator (certificate, value_mark,
_first_number, anchor_decision probe).
"""
import importlib.util
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent          # pilot/peval/phi_d/s2_rc2
PHI_D = HERE.parent                                     # pilot/peval/phi_d
for _p in (str(PHI_D), str(PHI_D / "comparator_v0")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import audit_expanded as A                              # noqa: E402  toks; import is side-effect free
import common as C                                      # noqa: E402  validate_ir + canonical roles
import comparator as V0                                 # noqa: E402  comparator_v0 mechanics

# rc1 comparator loaded BY PATH under a private name (filename collision with
# this module is intentional and harmless through importlib).
_RC1_PATH = PHI_D / "s2" / "s2_comparator.py"
_spec = importlib.util.spec_from_file_location("s2_rc1_comparator", _RC1_PATH)
RC1 = importlib.util.module_from_spec(_spec)
sys.modules["s2_rc1_comparator"] = RC1
_spec.loader.exec_module(RC1)

RULE_VERSION = "s2-rc2"
VERDICTS = ("match", "contradict", "unknown")

_ROLES = C.CANONICAL_ROLES

# v0-passthrough map for the scaffolding channels reused unmodified (direction,
# termination): their internals only test for "excluded"; they must stay HARD.
_V0_PASSTHROUGH_ELIG = {
    "pred_attribute": "hard", "pred_op": "hard", "pred_value": "hard",
    "pred_polarity": "hard", "pred_all": "hard", "branch_effects": "hard",
    "direction": "hard", "scope": "excluded", "archive_capture": "hard",
    "roles_required": "hard", "termination": "hard",
}

_P2_PROJECTION_OPS = (">=", "<=")   # registered P2 single-guard projection set
_CAPTURE_ACTIONS = V0.CAPTURE_ACTIONS
_SEV = {"note": 0, "benign": 1, "unknown": 2, "contradict": 3}


# ---------------------------------------------------------------------------
# small structural helpers (all deterministic)
# ---------------------------------------------------------------------------

def _node_key(nid):
    """Numeric-aware id sort key: 'n10' > 'n2' semantically-free but fixed."""
    m = re.match(r"^(\D*)(\d+)$", str(nid))
    return (m.group(1), int(m.group(2))) if m else (str(nid), 0)


def present_steps(ir):
    """Present non-finish nodes; finish is DSL bookkeeping, never a signature
    element (spec section 5)."""
    return [n for n in ir["nodes"] if n.get("status") == "present"
            and n["op"] != "finish"]


def _trole(node, roles):
    return V0.resolve_role(node["args"].get("target"), roles)


def _raction(node):
    """Resolved write action class, or None when unresolved (None/'other')."""
    a = V0.write_action(node)
    return a if (a and a != "other") else None


def _edge_ok(ni, nm, ti, tm):
    """Compatibility edge (spec section 6.1). Caller guarantees same op."""
    op = ni["op"]
    if op == "write":
        ai, am = _raction(ni), _raction(nm)
        if ai and am and ai != am:
            return False
    if op in ("read", "list", "verify", "write"):
        if ti and tm and ti != tm:
            return False
    return True


def _role_exact(ti, tm):
    return bool(ti) and bool(tm) and ti == tm


def _reach(nodes):
    """depends_on reachability over the given node list (transitive closure).
    Includes any surplus nodes as intermediates (they remain flaggable extras)
    but the relation is over all nodes' ids."""
    byid = {n["id"]: n for n in nodes}
    cache = {}

    def reaches(a, b):
        if (a, b) in cache:
            return cache[(a, b)]
        # b transitively depends on a  <=>  a reaches b
        seen = set()
        stack = list((byid.get(b) or {}).get("depends_on", []))
        found = False
        while stack:
            u = stack.pop()
            if u == a:
                found = True
                break
            if u in seen:
                continue
            seen.add(u)
            n = byid.get(u)
            if n is not None:
                stack.extend(n.get("depends_on", []))
        cache[(a, b)] = found
        return found
    return reaches


def _commutes(nodes):
    byid = {n["id"]: n for n in nodes}

    def comm(a, b):
        na, nb = byid.get(a), byid.get(b)
        if na is None or nb is None:
            return False
        return (b in na.get("commutes_with", [])) or (a in nb.get("commutes_with", []))
    return comm


# ---------------------------------------------------------------------------
# structural matching: compatibility graph + lexicographic maximum matching
# ---------------------------------------------------------------------------

def _max_cardinality(adj, u_order):
    """Kuhn augmenting paths over ordered U and sorted candidate iteration;
    returns (K, match_u2v) for a deterministic maximum-cardinality matching."""
    match_v = {}

    def aug(u, seen):
        for v in sorted(adj.get(u, [])):
            if v in seen:
                continue
            seen.add(v)
            if v not in match_v or aug(match_v[v], seen):
                match_v[v] = u
                return True
        return False
    for u in u_order:
        aug(u, set())
    return len(match_v), {u: v for v, u in match_v.items()}


def match_steps(steps_i, steps_m, roles_i, roles_m):
    """Spec section 6: maximum bijection first, deterministic tie-break after
    semantic compatibility is maximized. Returns (chosen_u2v, unpaired_i,
    unpaired_m, probe)."""
    ti = {n["id"]: _trole(n, roles_i) for n in steps_i}
    tm = {n["id"]: _trole(n, roles_m) for n in steps_m}
    byid_i = {n["id"]: n for n in steps_i}
    byid_m = {n["id"]: n for n in steps_m}
    u_order = sorted(byid_i, key=_node_key)
    v_order = sorted(byid_m, key=_node_key)

    adj = {u: [v for v in v_order
               if byid_i[u]["op"] == byid_m[v]["op"]
               and _edge_ok(byid_i[u], byid_m[v], ti[u], tm[v])]
           for u in u_order}
    K, _ = _max_cardinality(adj, u_order)

    def cand_pref(u):
        return sorted(adj[u], key=lambda v: (0 if _role_exact(ti[u], tm[v]) else 1,
                                             _node_key(v)))
    chosen, used_v = {}, set()
    for idx, u in enumerate(u_order):
        need = K - len(chosen)
        if need == 0:
            break
        rest_u = u_order[idx + 1:]
        fixed = False
        for v in cand_pref(u):
            if v in used_v:
                continue
            rem_v = set(v_order) - used_v - {v}
            if len(rest_u) == 0 and need - 1 == 0:
                chosen[u] = v
                used_v.add(v)
                fixed = True
                break
            sub_adj = {x: [y for y in adj[x] if y in rem_v] for x in rest_u}
            k2, _ = _max_cardinality(sub_adj, rest_u)
            if k2 == need - 1:
                chosen[u] = v
                used_v.add(v)
                fixed = True
                break
        # if no v preserves attainability, every max extension leaves u unmatched
    un_i_ids = sorted(set(u_order) - set(chosen), key=_node_key)
    un_m_ids = sorted(set(v_order) - used_v, key=_node_key)
    probe = {"K": K, "n_u": len(u_order), "n_v": len(v_order),
             "map": [[u, chosen[u]] for u in u_order if u in chosen],
             "unpaired_instruction": un_i_ids, "unpaired_memory": un_m_ids,
             "full": len(chosen) == len(u_order) == len(v_order)}
    return ({u: chosen[u] for u in u_order if u in chosen},
            [byid_i[u] for u in un_i_ids], [byid_m[v] for v in un_m_ids], probe)


# ---------------------------------------------------------------------------
# role channel (adjudicated; unchanged from rc1 except code family placement)
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
