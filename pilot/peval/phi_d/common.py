"""Shared helpers for the phi+d S0/S1 pipeline (extraction + decomposed judge).

Everything lives under pilot/peval/phi_d/. Labels (cell/P/S/family/archetype/domain)
are NEVER used here; this module only touches instruction / memory_text surfaces.
"""
import hashlib
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent          # pilot/peval/phi_d
OUT = HERE / "out"
PAIRS = HERE.parent / "pairs.jsonl"                     # read-only input

MODEL_ID = "Qwen/Qwen2.5-7B-Instruct"
MODEL_REV = "a09a35458c702b33eeacc393d103063234e8bc28"

CANONICAL_ROLES = ["subject_row", "policy_row", "source", "destination", "child_set", "audit_sink"]
NODE_OPS = ["read", "list", "aggregate", "branch", "write", "verify", "finish"]
STATUSES = ["present", "absent", "unknown"]
PREDICATE_OPS = [">", ">=", "<", "<=", "==", "!="]
POLARITIES = ["positive", "negative"]
WRITE_ACTIONS = ["set", "insert", "delete", "move", "notify", "archive", "report", "other"]
AGG_FUNCS = ["count", "sum", "min", "max", "avg", "exists", "other"]
JUDGE_VERDICTS = ["match", "contradict", "unknown"]
FIELD_VERDICTS = ["match", "contradict", "unknown", "not_applicable"]
JUDGE_FIELDS = ["goal", "roles", "branch_predicates", "transfer_direction",
                "aggregation_scope", "required_operations", "write_effects"]

# ------------------------------------------------------ guided-decoding JSON schemas
# Deterministic format enforcement at decode time (vLLM GuidedDecodingParams, outlines
# backend; outlines in this env requires string "type", so nullables use anyOf).
# `args` is left a free object; per-op argument shape is enforced afterwards by
# validate_ir / validate_judge (+ one repair retry).
_STR_OR_NULL = {"anyOf": [{"type": "string", "maxLength": 64}, {"type": "null"}]}
_STATUS_EV = {"type": "object", "additionalProperties": False,
              "properties": {"status": {"enum": STATUSES},
                             "surface": _STR_OR_NULL,
                             "evidence": _STR_OR_NULL},
              "required": ["status", "surface", "evidence"]}
# per-op argument typing via a nullable-key superset object: the FSM enforces enum
# values for action/function plus predicate key discipline; validate_ir then enforces
# per-op required contents (+ one repair retry).
_PRED_F = {"type": "object", "additionalProperties": False,
           "properties": {"status": {"enum": STATUSES},
                          "value": _STR_OR_NULL,
                          "evidence": _STR_OR_NULL},
           "required": ["status", "value", "evidence"]}


def _f_enum(values):
    f = json.loads(json.dumps(_PRED_F))
    f["properties"]["value"] = {"anyOf": [{"enum": values}, {"type": "null"}]}
    return f


_PRED = {"type": "object", "additionalProperties": False,
         "properties": {"attribute": _PRED_F,
                        "op": _f_enum(PREDICATE_OPS),
                        "value": _PRED_F,
                        "polarity": _f_enum(POLARITIES)},
         "required": ["attribute", "op", "value", "polarity"]}
_EFFECT = {"type": "object", "additionalProperties": False,
           "properties": {"action": _STR_OR_NULL, "target": _STR_OR_NULL, "value": _STR_OR_NULL},
           "required": ["action", "target", "value"]}
_EFFECTS = {"anyOf": [{"type": "array", "items": _EFFECT}, {"type": "null"}]}
_ARGS = {"type": "object", "additionalProperties": False,
         "properties": {
             "target": _STR_OR_NULL,
             "over": _STR_OR_NULL,
             "function": {"anyOf": [{"enum": AGG_FUNCS}, {"type": "null"}]},
             "action": {"anyOf": [{"enum": WRITE_ACTIONS}, {"type": "null"}]},
             "value": _STR_OR_NULL,
             "predicate": {"anyOf": [_PRED, {"type": "null"}]},
             "then_effects": _EFFECTS,
             "else_effects": _EFFECTS},
         "required": ["target", "over", "function", "action", "value",
                      "predicate", "then_effects", "else_effects"]}
_NODE = {"type": "object", "additionalProperties": False,
         "properties": {"id": {"type": "string", "maxLength": 6},
                        "op": {"enum": NODE_OPS},
                        "status": {"enum": STATUSES},
                        "evidence": _STR_OR_NULL,
                        "args": _ARGS,
                        "depends_on": {"type": "array", "items": {"type": "string", "maxLength": 6}},
                        "commutes_with": {"type": "array", "items": {"type": "string", "maxLength": 6}}},
         "required": ["id", "op", "status", "evidence", "args", "depends_on", "commutes_with"]}
IR_GUIDE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "schema": {"const": "phi_ir/v0"},
        "roles": {"type": "object", "additionalProperties": False,
                  "properties": {r: _STATUS_EV for r in CANONICAL_ROLES},
                  "required": CANONICAL_ROLES},
        "nodes": {"type": "array", "minItems": 1, "maxItems": 16, "items": _NODE},
        "termination": {"type": "object", "additionalProperties": False,
                        "properties": {"status": {"enum": STATUSES},
                                       "evidence": _STR_OR_NULL},
                        "required": ["status", "evidence"]}},
    "required": ["schema", "roles", "nodes", "termination"]}

_JFIELD = {"type": "object", "additionalProperties": False,
           "properties": {"instruction_says": _STR_OR_NULL,
                          "memory_says": _STR_OR_NULL,
                          "verdict": {"enum": FIELD_VERDICTS},
                          "note": _STR_OR_NULL},
           "required": ["instruction_says", "memory_says", "verdict", "note"]}
JUDGE_GUIDE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "schema": {"const": "phi_judge/v0"},
        "fields": {"type": "object", "additionalProperties": False,
                   "properties": {f: _JFIELD for f in JUDGE_FIELDS},
                   "required": JUDGE_FIELDS},
        "verdict": {"enum": JUDGE_VERDICTS}},
    "required": ["schema", "fields", "verdict"]}


def sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def load_pairs():
    with open(PAIRS) as f:
        return [json.loads(l) for l in f]


def done_keys(path: pathlib.Path) -> set:
    """Keys of rows already written (resume support)."""
    out = set()
    if path.exists():
        with open(path) as f:
            for line in f:
                try:
                    out.add(json.loads(line)["key"])
                except Exception:
                    continue
    return out


def append_rows(path: pathlib.Path, rows, fh):
    for r in rows:
        fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    fh.flush()


def extract_json_object(text: str):
    """Pull the first {...} block out of a model output. Returns (obj, error_class, detail)."""
    if not text or not text.strip():
        return None, "empty_output", "no text emitted"
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return None, "json_parse_error", "no JSON object braces found"
    cand = text[start:end + 1]
    try:
        return json.loads(cand), None, None
    except json.JSONDecodeError as e:
        return None, "json_parse_error", str(e)[:200]


# ---------------------------------------------------------------- IR validation

def _status_ok(v):
    return isinstance(v, str) and v in STATUSES


def _check_field_wrapper(f, allowed_values=None):
    """F = {"status", "value", "evidence"} wrapper used for branch predicate fields."""
    if not isinstance(f, dict) or not _status_ok(f.get("status")):
        return False
    if "value" in f and f["value"] is not None and not isinstance(f["value"], str):
        return False
    if allowed_values is not None and f.get("value") is not None and f["value"] not in allowed_values:
        return False
    return True


def _check_effect(e):
    return (isinstance(e, dict)
            and all(k in e for k in ("action", "target", "value"))
            and all(e[k] is None or isinstance(e[k], str) for k in ("action", "target", "value")))


def validate_ir(obj):
    """Hard structural validation of an extracted IR. Returns (ok, error_class, detail).

    Evidence-quote quality (missing / non-verbatim) is tracked separately as a soft
    metric and never invalidates an IR here.
    """
    if not isinstance(obj, dict):
        return False, "schema_validation_error", "top-level not an object"
    if obj.get("schema") != "phi_ir/v0":
        return False, "schema_validation_error", "schema != phi_ir/v0"

    roles = obj.get("roles")
    if not isinstance(roles, dict) or set(roles.keys()) != set(CANONICAL_ROLES):
        return False, "schema_validation_error", "roles keys != canonical 6"
    for rk, rv in roles.items():
        if not isinstance(rv, dict) or not _status_ok(rv.get("status")):
            return False, "schema_validation_error", f"role {rk} bad status"
        if rv.get("surface") is not None and not isinstance(rv["surface"], str):
            return False, "schema_validation_error", f"role {rk} bad surface"
        if rv.get("evidence") is not None and not isinstance(rv["evidence"], str):
            return False, "schema_validation_error", f"role {rk} bad evidence"

    nodes = obj.get("nodes")
    if not isinstance(nodes, list) or not (1 <= len(nodes) <= 16):
        return False, "schema_validation_error", "nodes not a list of 1..16"
    ids = [n.get("id") for n in nodes if isinstance(n, dict)]
    if len(ids) != len(nodes) or len(set(ids)) != len(ids) or any(not isinstance(i, str) for i in ids):
        return False, "schema_validation_error", "node ids missing/duplicated"
    idset = set(ids)

    for n in nodes:
        if n.get("op") not in NODE_OPS:
            return False, "schema_validation_error", f"node {n.get('id')} bad op {n.get('op')}"
        if not _status_ok(n.get("status")):
            return False, "schema_validation_error", f"node {n.get('id')} bad status"
        if n.get("evidence") is not None and not isinstance(n["evidence"], str):
            return False, "schema_validation_error", f"node {n.get('id')} bad evidence"
        if not isinstance(n.get("args"), dict):
            return False, "schema_validation_error", f"node {n['id']} args not object"
        for dep_key in ("depends_on", "commutes_with"):
            dl = n.get(dep_key, [])
            if not isinstance(dl, list) or any(not isinstance(d, str) for d in dl):
                return False, "schema_validation_error", f"node {n['id']} {dep_key} not list[str]"
            if any(d not in idset for d in dl):
                return False, "schema_validation_error", f"node {n['id']} {dep_key} unknown id"
            if n["id"] in dl:
                return False, "schema_validation_error", f"node {n['id']} self reference in {dep_key}"
        args = n["args"]
        if n["op"] == "branch":
            pred = args.get("predicate")
            if not isinstance(pred, dict) or set(pred.keys()) != {"attribute", "op", "value", "polarity"}:
                return False, "schema_validation_error", f"node {n['id']} predicate keys wrong"
            if not _check_field_wrapper(pred["attribute"]):
                return False, "schema_validation_error", f"node {n['id']} predicate.attribute bad"
            if not _check_field_wrapper(pred["op"], PREDICATE_OPS):
                return False, "schema_validation_error", f"node {n['id']} predicate.op bad"
            if not _check_field_wrapper(pred["value"]):
                return False, "schema_validation_error", f"node {n['id']} predicate.value bad"
            if not _check_field_wrapper(pred["polarity"], POLARITIES):
                return False, "schema_validation_error", f"node {n['id']} predicate.polarity bad"
            for eff_key in ("then_effects", "else_effects"):
                el = args.get(eff_key, []) or []
                if not isinstance(el, list) or any(not _check_effect(e) for e in el):
                    return False, "schema_validation_error", f"node {n['id']} {eff_key} bad"
        elif n["op"] == "write":
            a = args.get("action")
            if a is not None and (not isinstance(a, str) or a not in WRITE_ACTIONS):
                return False, "schema_validation_error", f"node {n['id']} write.action bad"
            for k in ("target", "value"):
                if args.get(k) is not None and not isinstance(args[k], str):
                    return False, "schema_validation_error", f"node {n['id']} write.{k} bad"
        elif n["op"] == "aggregate":
            f_ = args.get("function")
            if f_ is not None and f_ not in AGG_FUNCS:
                return False, "schema_validation_error", f"node {n['id']} aggregate.function bad"
            if args.get("over") is not None and not isinstance(args["over"], str):
                return False, "schema_validation_error", f"node {n['id']} aggregate.over bad"
        elif n["op"] in ("read", "list", "verify"):
            if args.get("target") is not None and not isinstance(args["target"], str):
                return False, "schema_validation_error", f"node {n['id']} target bad"

    # acyclicity of depends_on
    dep = {n["id"]: [d for d in n.get("depends_on", [])] for n in nodes}
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {k: WHITE for k in dep}

    def dfs(u):
        color[u] = GRAY
        for v in dep[u]:
            if color[v] == GRAY:
                return False
            if color[v] == WHITE and not dfs(v):
                return False
        color[u] = BLACK
        return True

    for k in dep:
        if color[k] == WHITE and not dfs(k):
            return False, "schema_validation_error", "depends_on cycle"

    term = obj.get("termination")
    if not isinstance(term, dict) or not _status_ok(term.get("status")):
        return False, "schema_validation_error", "termination bad"
    if term.get("evidence") is not None and not isinstance(term["evidence"], str):
        return False, "schema_validation_error", "termination.evidence bad"
    return True, None, None


def validate_judge(obj):
    """Hard structural validation of a decomposed-judge output. Returns (ok, error_class, detail)."""
    if not isinstance(obj, dict):
        return False, "schema_validation_error", "top-level not an object"
    if obj.get("schema") != "phi_judge/v0":
        return False, "schema_validation_error", "schema != phi_judge/v0"
    fields = obj.get("fields")
    if not isinstance(fields, dict) or set(fields.keys()) != set(JUDGE_FIELDS):
        return False, "schema_validation_error", "fields keys wrong"
    for fk, fv in fields.items():
        if not isinstance(fv, dict) or fv.get("verdict") not in FIELD_VERDICTS:
            return False, "schema_validation_error", f"field {fk} bad verdict"
        if fv.get("note") is not None and not isinstance(fv["note"], str):
            return False, "schema_validation_error", f"field {fk} bad note"
    if obj.get("verdict") not in JUDGE_VERDICTS:
        return False, "schema_validation_error", "final verdict bad"
    return True, None, None
