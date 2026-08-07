"""Latent program DSL for CausalMemBench mini-pilot (SPEC.md section 3).

A latent program z = (G_prec, C_safety, C_terminal, B_recovery):
  - G_prec    : partial-order dependencies between abstract steps
  - C_safety  : hard ordering safety constraints (e.g. archive before delete;
                write ops must carry a non-empty WHERE, enforced by the env)
  - C_terminal: legal terminal predicates over the final DB state
  - B_recovery: which preconditions must be re-checked before retrying a write

Two tasks are "program match" (P=1) iff they share the same abstract
signature -- the same step set with the same partial order, operator polarity
and write-target roles -- regardless of surface entities, wording or business
domain rendering. Concrete thresholds / entity values are instance
parameters, not part of the equivalence class.

The oracle walker EXECUTES the oracle plan (a concrete linear extension of
G_prec with branch decisions) against a live environment and asserts that a
legal terminal state is reached (tech report 6.9-1).
"""

# ---------------------------------------------------------------------------
# Abstract program definitions
# ---------------------------------------------------------------------------
# Step types:
#   READ    -> tool read / aggregate over the DB
#   CHECK   -> internal predicate over previously observed values (no tool)
#   WRITE   -> tool insert / update / delete
#   VERIFY  -> tool read used to confirm the postcondition
#
# A Program is a dict:
#   signature : canonical string == equivalence-class key
#   steps     : list of {id, type, depends_on, bind}
#               bind is a callable that maps a binding dict (concrete values
#               resolved from the initial state) to a tool call
#               {"tool": ..., "args": ...} or, for CHECK, to
#               {"tool": "__check__", "args": {...}, "expect": "A"/"B"}
#   terminal  : list of predicate dicts (see env_relationalops.check_terminal)
#               expressed with {slot} placeholders, formatted per binding
#   safety    : list of human-readable safety rules enforced structurally
#               through depends_on edges (kept for documentation/audit)


ARCHETYPES = {}


def archetype(name):
    def deco(fn):
        ARCHETYPES[name] = fn
        return fn
    return deco


def _step(sid, stype, deps, bind):
    return {"id": sid, "type": stype, "depends_on": list(deps), "bind": bind}


# ---------------------------------------------------------------------------
# P1 conditional_write:
#   READ target row ; CHECK attr (</>) theta [+ optional policy READ]
#   ; BRANCH write (write_a if cond else write_b) ; VERIFY read-back.
# params keys:
#   table, key_field, key_value, cond_field, cond_op ('<' or '>'),
#   theta  (numeric threshold; may come from policy table when join_depth==2),
#   policy_table / policy_key_field / policy_key_value / policy_value_field,
#   write_a {table,set,where}, write_b {table,set,where}, verify {table,where}
# All write dicts as (table, set_fields, where_fields) triples of concrete values
# produced by the per-schema binder closures in generate_families.
# ---------------------------------------------------------------------------
def build_conditional_write(params):
    j2 = params.get("join_depth", 1) == 2

    def bind_read(b):
        return {"tool": "read", "args": {"table": params["table"],
                                         "filter": {params["key_field"]: params["key_value"]}}}

    steps = [_step("s_read", "READ", [], bind_read)]
    deps_check = ["s_read"]
    if j2:
        def bind_policy(b):
            return {"tool": "read", "args": {"table": params["policy_table"],
                                             "filter": {params["policy_key_field"]: params["policy_key_value"]}}}
        steps.append(_step("s_policy", "READ", [], bind_policy))
        deps_check.append("s_policy")

    def bind_check(b):
        return {"tool": "__check__",
                "args": {"kind": "field_cmp", "table": params["table"],
                         "where": {params["key_field"]: params["key_value"]},
                         "field": params["cond_field"],
                         "op": params["cond_op"], "value": params["theta"]},
                "expect": b["branch"]}
    steps.append(_step("s_check", "CHECK", deps_check, bind_check))

    def bind_write(b):
        w = params["write_a"] if b["branch"] == "A" else params["write_b"]
        return {"tool": w["tool"], "args": w["args"]}
    steps.append(_step("s_write", "WRITE", ["s_check"], bind_write))

    def bind_verify(b):
        return {"tool": "read", "args": {"table": params["verify"]["table"],
                                         "filter": params["verify"]["where"]}}
    steps.append(_step("s_verify", "VERIFY", ["s_write"], bind_verify))

    signature = "P1|J%d|op%s|READ%s;CHECK;BRANCHWRITE;VERIFY" % (
        params.get("join_depth", 1), params["cond_op"],
        "+POLICY" if j2 else "")
    return {"signature": signature, "steps": steps, "join_depth": params.get("join_depth", 1),
            "safety": ["write only after condition check",
                       "single-row writes must use a restrictive WHERE"]}


ARCHETYPES["conditional_write"] = build_conditional_write


# ---------------------------------------------------------------------------
# P2 two_row_transfer:
#   READ A ; READ B (unordered) ; CHECK guard(A,B) ; WRITE A ; WRITE B
#   (writes unordered wrt each other, both after check) ; VERIFY both.
# params:
#   read_a/read_b : (table, filter) ; guard: {kind:'transfer_guard'},
#   write_a/write_b tool dicts ; verify: {table, where}
# ---------------------------------------------------------------------------
def build_two_row_transfer(params):
    def bind_read_a(b):
        return {"tool": "read", "args": dict(params["read_a"])}

    def bind_read_b(b):
        return {"tool": "read", "args": dict(params["read_b"])}

    def bind_check(b):
        return {"tool": "__check__", "args": dict(params["guard"]),
                "expect": b["branch"]}  # guard must hold ('A') for a legal plan

    def bind_write_a(b):
        return dict(params["write_a"])

    def bind_write_b(b):
        return dict(params["write_b"])

    def bind_verify(b):
        return {"tool": "read", "args": {"table": params["verify"]["table"],
                                         "filter": params["verify"]["where"]}}

    steps = [
        _step("s_read_a", "READ", [], bind_read_a),
        _step("s_read_b", "READ", [], bind_read_b),
        _step("s_check", "CHECK", ["s_read_a", "s_read_b"], bind_check),
        _step("s_write_a", "WRITE", ["s_check"], bind_write_a),
        _step("s_write_b", "WRITE", ["s_check"], bind_write_b),
        _step("s_verify", "VERIFY", ["s_write_a", "s_write_b"], bind_verify),
    ]
    # class_tag is DOMAIN-ABSTRACT: "transfer:origin>target" for the correct
    # program, "transfer:target>origin" for the reversed near-miss. Concrete
    # tables/filters are never part of the signature.
    signature = "P2|%s|READx2;CHECK;WRITEx2;VERIFY" % params["class_tag"]
    return {"signature": signature, "steps": steps, "join_depth": 2,
            "safety": ["no write before the transfer guard has been checked",
                       "writes to both sides required for conservation"]}


ARCHETYPES["two_row_transfer"] = build_two_row_transfer


# ---------------------------------------------------------------------------
# P3 aggregate_gate:
#   READ parent ; AGGREGATE children ; CHECK agg (</>/==) theta
#   ; WRITE parent update ; WRITE log insert (unordered) ; VERIFY.
# params:
#   read_parent: {table, filter}; agg_args: {table, agg, field, filter};
#   check: {kind:'agg_cmp', op, value}; write_parent/write_log: tool dicts;
#   verify: {table, where}
# ---------------------------------------------------------------------------
def build_aggregate_gate(params):
    def bind_read(b):
        return {"tool": "read", "args": dict(params["read_parent"])}

    def bind_agg(b):
        return {"tool": "aggregate", "args": dict(params["agg_args"])}

    def bind_check(b):
        c = dict(params["check"])
        c["agg_args"] = dict(params["agg_args"])
        return {"tool": "__check__", "args": c, "expect": b["branch"]}

    def bind_write_parent(b):
        w = params["write_parent_a"] if b["branch"] == "A" else params["write_parent_b"]
        return dict(w)

    def bind_write_log(b):
        w = params["write_log_a"] if b["branch"] == "A" else params["write_log_b"]
        return dict(w)

    def bind_verify(b):
        return {"tool": "read", "args": {"table": params["verify"]["table"],
                                         "filter": params["verify"]["where"]}}

    steps = [
        _step("s_read", "READ", [], bind_read),
        _step("s_agg", "READ", ["s_read"], bind_agg),
        _step("s_check", "CHECK", ["s_agg"], bind_check),
        _step("s_write_parent", "WRITE", ["s_check"], bind_write_parent),
        _step("s_write_log", "WRITE", ["s_check"], bind_write_log),
        _step("s_verify", "VERIFY", ["s_write_parent", "s_write_log"], bind_verify),
    ]
    # agg_sem is DOMAIN-ABSTRACT: which child-set the gate counts
    # ("open" items vs "done" items for the near-miss).
    signature = "P3|agg:%s|op%s|READ;AGG;CHECK;WRITEx2;VERIFY" % (
        params["agg_sem"], params["check"]["op"])
    return {"signature": signature, "steps": steps, "join_depth": 2,
            "safety": ["gate the parent update on the aggregate check",
                       "audit log insert accompanies the status change"]}


ARCHETYPES["aggregate_gate"] = build_aggregate_gate


# ---------------------------------------------------------------------------
# P4 delete_after_capture:
#   READ target ; CHECK guard ; WRITE archive-insert (captures fields)
#   ; WRITE delete parent (deps: archive) ; WRITE delete children
#   (deps: check) ; VERIFY absence + archive presence.
# params:
#   read: {table, filter}; check: {kind:'field_cmp',...}; archive: tool dict;
#   delete_parent/delete_children: tool dicts;
#   verify_gone: {table, where} (not-exists), verify_arch: {table, where} (exists)
# ---------------------------------------------------------------------------
def build_delete_after_capture(params):
    def bind_read(b):
        return {"tool": "read", "args": dict(params["read"])}

    def bind_check(b):
        return {"tool": "__check__", "args": dict(params["check"]),
                "expect": b["branch"]}

    def bind_archive(b):
        return dict(params["archive"])

    def bind_del_parent(b):
        return dict(params["delete_parent"])

    def bind_del_children(b):
        return dict(params["delete_children"])

    def bind_verify(b):
        return {"tool": "read", "args": {"table": params["verify_arch"]["table"],
                                         "filter": params["verify_arch"]["where"]}}

    skip_archive = params.get("skip_archive", False)  # near-miss z' variant
    if skip_archive:
        steps = [
            _step("s_read", "READ", [], bind_read),
            _step("s_check", "CHECK", ["s_read"], bind_check),
            _step("s_delete_children", "WRITE", ["s_check"], bind_del_children),
            _step("s_delete_parent", "WRITE", ["s_delete_children"], bind_del_parent),
            _step("s_verify", "VERIFY", ["s_delete_parent"], bind_verify),
        ]
    else:
        steps = [
            _step("s_read", "READ", [], bind_read),
            _step("s_check", "CHECK", ["s_read"], bind_check),
            _step("s_archive", "WRITE", ["s_check"], bind_archive),
            _step("s_delete_children", "WRITE", ["s_check"], bind_del_children),
            _step("s_delete_parent", "WRITE", ["s_archive", "s_delete_children"], bind_del_parent),
            _step("s_verify", "VERIFY", ["s_delete_parent"], bind_verify),
        ]
    # class_tag is DOMAIN-ABSTRACT: "archive_then_delete" vs the near-miss
    # "delete_only" (which also has a different step set -> different class).
    signature = "P4|%s|READ;CHECK;%sDELx2;VERIFY" % (
        params["class_tag"], "" if skip_archive else "ARCHIVE;")
    safety = (["children are removed before the parent to avoid orphans"] if skip_archive
              else ["target row must be archived BEFORE it is deleted "
                    "(recovery: a failed archive insert blocks the delete)",
                    "children are removed before the parent to avoid orphans"])
    return {"signature": signature, "steps": steps, "join_depth": 2,
            "safety": safety}


ARCHETYPES["delete_after_capture"] = build_delete_after_capture


# ---------------------------------------------------------------------------
# Oracle walker
# ---------------------------------------------------------------------------

class OracleViolation(Exception):
    pass


def topological_order_ok(steps, plan_step_ids):
    """Check that plan_step_ids is a linear extension of G_prec."""
    deps = {s["id"]: set(s["depends_on"]) for s in steps}
    done = set()
    for sid in plan_step_ids:
        if sid not in deps:
            raise OracleViolation("plan references unknown step %r" % sid)
        missing = deps[sid] - done
        if missing:
            raise OracleViolation(
                "step %s executed before prerequisites %s" % (sid, sorted(missing)))
        done.add(sid)
    if done != set(deps):
        raise OracleViolation("plan omits steps %s" % sorted(set(deps) - done))
    return True


def run_oracle_plan(env, program, plan, require_terminal=True):
    """Execute an oracle plan against a live RelationalOpsEnv.

    plan: list of {"step_id", "tool", "args"} (+ "expect" for CHECK steps).
    Returns (ok, detail). Raises nothing; violations are reported in detail.
    """
    step_map = {s["id"]: s for s in program["steps"]}
    trace = []
    try:
        topological_order_ok(program["steps"], [p["step_id"] for p in plan])
        for i, action in enumerate(plan):
            sid = action["step_id"]
            step = step_map[sid]
            if step["type"] == "CHECK":
                ok = env.eval_check(action["args"])
                expect = action.get("expect", "A")
                actual = "A" if ok else "B"
                trace.append({"step": sid, "check": action["args"], "result": actual})
                if actual != expect:
                    raise OracleViolation(
                        "check %s returned %s, plan expected %s"
                        % (sid, actual, expect))
                continue
            res = env.call(action["tool"], action["args"])
            trace.append({"step": sid, "tool": action["tool"],
                          "args": action["args"], "result": res})
            if res.get("error"):
                raise OracleViolation(
                    "step %s tool error: %s" % (sid, res["error"]))
        if require_terminal:
            term_ok, term_detail = env.check_terminal()
            if not term_ok:
                raise OracleViolation(
                    "terminal predicates not satisfied: %s" % (term_detail,))
        return True, trace
    except OracleViolation as e:
        return False, {"error": str(e), "trace": trace}
