"""EXPANDED faithfulness audit (blind, CPU-only): all 532 valid v2 IRs vs SEALED truth.

Mandatory step 3-4 of the adjudicated ordering (Codex thread 019fe66c, round 2,
RESEARCH_LEDGER 2026-08-10): decides WHICH veto-bearing fields are trustworthy
enough to be hard vetoes in the upcoming comparator. Runs after the v2 merge
(out/extractions_v2.jsonl, 532/532 valid). Sealed truth
(/work1/zixuan/data/agent_memory/sealed/*) is measurement-only: it defines truth
targets and scores; it never enters any model input (this task has no model at all).

=====================  PRE-REGISTERED MEASUREMENT RULES (frozen BEFORE running)  =====================
All rules below are defined before any run. If a field FAILS its gate the failure is
reported as-is; the only pre-declared exceptions are the two evidence-backed patterns
from the previous audit (out/guided/faithfulness_audit.json, REPORT.md §7):
  (E1) polarity clause-artifact: the first-cue clause rule can land on an else-path
       guard fragment ("if it is not") when the operative condition is stated positively
       upstream; verified truth polarity is then "positive" (verbatim rule re-used).
  (E2) value-as-stated: when the numeric truth value's digits appear nowhere in the
       sample's CONDITION WINDOW, the text does not carry the number and the IR is
       faithful if it emits the symbolic policy/threshold reference instead.

Joins (identical to the previous audit, extended with an explicit sham exclusion):
- instruction text -> ALL sealed sibling tasks with identical text (same family;
  consensus-safe by construction).
- memory text -> ALL sealed memories rows with identical text, EXCLUDING source_kind
  == "sham" (cell "Q", diagnostic-only, 0 text intersection with the corpus).
  Each row maps to a truth task: sibling_same_family -> sibling task
  (family_idx, target_sibling); near_miss -> near_miss task of family_idx (the 4
  per-family near-miss tasks are dimension-identical, verified; dict-last kept for
  continuity with the previous audit); cross_domain_pair / unrelated -> sibling task
  (source_family, target_sibling).
- PARTIAL-CONSENSUS RULE (per dimension): if candidate tasks disagree on a
  dimension's normalized truth, that dimension is UNMEASURABLE for the sample
  (excluded from numerator AND denominator, counted separately). Archetype and
  signature/op are consensus-safe corpus-wide (verified in the previous audit);
  predicate VALUE can conflict (entity-generic styles; recomputed here: 12 P1-theta
  + 24 P2-guard texts, see field_metrics.json -> unmeasurable_by_dimension).

IR predicate carrier: FIRST node (in id order, numeric suffix) whose args.predicate
is non-null, ANY op (the nullable-args guide schema lets the predicate migrate onto
read/aggregate nodes; carrier op is recorded). An IR with no predicate anywhere
scores "missing" on all pred_* and branch_effects fields. Branch-node PRESENCE
(predicate carrier on an actual branch node) is measured separately as field
branch_presence and is NOT folded into content agreement.

Field definitions (truth per archetype from program_params):
  P1 conditional_write : attr=tokens(cond_field); op=cond_op; value=theta (numeric);
      then=set(write_a.set), else=set(write_b.set) as (field,value) pairs.
  P2 two_row_transfer  : attr=union tokens(guard.a.field,guard.b.field);
      op SET={">=","<="}, value SET={guard.min_a,guard.cap_b} (membership);
      guard composite; then={(source,decrease),(destination,increase)}, else={};
      direction: source descriptor = discriminator value of guard.a.where,
      destination descriptor = discriminator value of guard.b.where (discriminator =
      the where-key on which a and b differ).
  P3 aggregate_gate    : attr anchor = child-table tokens + {"count","number"};
      op=check.op; value=check.value (numeric); then={(subject_row,parent outcome),
      (audit_sink,log etype)}, else likewise (write_parent_b/write_log_b);
      scope=(child table, filter triple (status-field,==|=!=,status-value),
      parent table); log/etype from write_log_a/b record["etype"].
  P4 delete_after_capture: attr=check.field; op=check.op; value=str(check.value);
      then={(archive,audit_sink) if archive else nothing, (delete,child_set),
      (delete,subject_row)}, else={}; archive_required = not skip_archive.

1. pred_attribute : normalized token containment: truth anchor tokens (plural-stripped
   lowercase alnum) intersect IR attribute tokens. Missing if no carrier or attribute
   F.status != "present".
2. pred_op        : P1/P3/P4: IR op == truth op. P2: IR op in truth op SET.
   (direction-bucket agreement kept as diagnostic only.)
3. pred_value     : (i) value join-conflict -> UNMEASURABLE (not wrong).
   (ii) numeric/stated rule: if the truth value's digits appear in the sample's
   CONDITION WINDOW (the polarity clause of E1; pre-registered window), compare
   numerically after float parsing (P4: exact string equality after quote-stripping).
   (iii) digit-absent -> value-as-stated (E2): the IR value must hit the symbolic
   concept of the threshold, defined verbatim here:
     P1-J2: ALL tokens of policy_value_field (e.g. "overstock","limit") appear in the
            IR value tokens;
     P2   : IR value tokens hit MIN_SIDE={"minimum","min","floor","keep","least"} or
            CAP_SIDE={"capacity","cap","max","maximum","ceiling","exceed"};
     P3   : (truth 0,==) -> IR value tokens hit ZERO_SET={"zero","none","no"};
            (truth 1,>=) -> IR value tokens hit ONE_SET={"one","least","any","some","single"};
     P4   : "cold" token present.
   In every symbolic case an IR value carrying digits that match NO truth number
   counts as DISAGREE (fabricated number), not as symbolic.
4. pred_polarity  : IR polarity.value == verified truth polarity (E1 remark applied).
5. branch_effects : carrier's then/else lists vs truth sets (order-insensitive,
   role alpha-renamed; resolver below). STRICT set discipline per archetype:
     P1: each effect -> (last-dot tokens of target minus table/role tokens,
         numeric-normalized value tokens); then-set == truth then-set AND
         else-set == truth else-set (extras = disagreement).
     P2: classify each effect's sign: "-<num>"/subtract/decrease/remove/minus/deduct
         -> decrease; "+<num>"/add/increase/deposit -> increase (decrease checked
         first; unclassifiable -> sign None). then-agrees iff for each truth
         (role,sign) an effect exists whose target contains that role's descriptor
         tokens with that sign, and no signed effect points at the opposite role;
         else-agrees iff no signed effect exists in else.
     P3: containment both ways: every truth (role,outcome-token) has an IR effect with
         resolved target role == role and outcome token in value tokens; and every IR
         effect resolving to subject_row/audit_sink matches some truth pair of that
         branch (extras on truth roles with wrong outcome = disagreement; effects on
         other roles ignored).
     P4: only delete/archive-class effects considered (action tokens contain
         delete/erase/remove/archive); then-set == truth then-set as (class,role)
         pairs; else agrees iff no delete/archive-class effect appears.
6. direction (P2 only): source-side text = concat(source role surface+evidence, all
   decrease-sign effect strings corpus-of-this-IR); destination-side likewise for
   increase. Truth descriptors from the joined task's guard (discriminator values).
   Agreement: source descriptor tokens subset of source-side tokens AND destination
   descriptor tokens subset of destination-side tokens AND neither descriptor leaks
   into the wrong side. Missing if both side texts are empty.
7. scope (P3/P4 only):
     P3: relation_ok = an aggregate node exists whose over-or-target resolves to
         child_set (resolver); filter_ok = the triple extracted from that node's
         predicate (or, if no predicate there, keyword-parsed from its args.value:
         attr=filter status-field token, op="!=" iff "not"/"non-" present else "==",
         value=status token) equals the truth filter triple. scope = both.
     P4: relation_ok = a delete-class effect target (carrier then/else or any write
         node args) resolves to child_set. P1/P2: NOT APPLICABLE (excluded).
8. archive_capture (P4 archive-required only; delete_only rows NOT APPLICABLE):
   presence_ok = an archive-class effect exists (any node). ordering_ok = the minimal
   emission position (id-sorted node order) of an archive-class effect precedes the
   minimal position of any delete-class effect. archive_capture = both.
9. roles_required : truth required-role set (consensus):
     P1 {subject_row; +policy_row iff join_depth>=2}; P2 {source,destination};
     P3 {subject_row,child_set,audit_sink};
     P4 {subject_row,child_set; +audit_sink iff archive_required}.
   Measured SLOT-level: for each required slot, the IR role status. false_absent =
   status "absent" on a required slot (gate clause). Content agreement of a slot =
   status != "absent" (present or unknown; unknown is abstain fuel, not a fabrication
   false-veto, but counts against the all-rows agreement as not-established).
   Slot "established" = status == "present".
10. termination   : truth = required (every family signature ends VERIFY).
   Faithful = termination.status == "present" AND evidence is a verbatim substring of
   the text (case-insensitive, len>=4). status "absent" = false_absent; "unknown" =
   missing; present-but-nonverbatim = contradiction.

FIDELITY GATE (frozen, from adjudication): per field:
  overall agreement (all-rows, missing=disagreement) >= 0.90
  AND worst per-archetype all-rows >= 0.80
  AND false-ABSENT-on-truth-present <= 0.05.
Unmeasurable rows are excluded from all denominators and counted separately.
PRESENT-ONLY rate (agreement where content was actually asserted) is always reported
as the content-quality diagnostic. Veto-eligibility rule (deterministic, declared
before running):
  PASS                                  -> HARD VETO eligible.
  FAIL & present_only >= 0.90           -> positive-only veto / soft evidence
                                           (unknown-if-absent): may veto only where
                                           asserted; missing/absent never contradicts.
  FAIL & present_only < 0.90            -> excluded from veto fields.

Stratified hand-audit sample: deterministic seed 42; buckets = 4 archetypes x
{A01,A10,A11} over MEMORY rows (memory-side cells; instruction texts are cell-free,
2 per archetype sampled separately); ~4 per (archetype,cell), keys not reused across
buckets; shortfalls recorded. Per-example: raw text, full IR, truth payload, all
field scores -> audit_expanded/stratified.jsonl (hand-verifiable).

No prompts, no GPU, no extractor changes. Deterministic; only stdlib.

=====================  V1.1 MEASUREMENT CORRECTIONS (bugfixes found on first impl run,
each implementing semantics ALREADY DECLARED above; both v1.0 and v1.1 numbers are
reported in AUDIT_EXPANDED.md — no rule was changed to make a field pass)  =====================
B1 score_value numeric probe: truth numbers are probed in the condition window in
   int-normalized form (0.0 -> '0') with word boundaries; v1.0 probed Python float
   formatting ('5.0'), which wrongly sent digit-PRESENT rows down the symbolic path.
B2 archive_capture ordering: measured at EFFECT granularity (global emission ordinal
   over effect lists + write nodes); v1.0 used node index only, which cannot express
   "archive effect precedes delete effect inside the same carrier node".
B3 branch_effects P2: effect targets are matched after role alpha-renaming
   (canonical role name / resolver first, guard-descriptor tokens as fallback), as
   declared; v1.0 matched descriptor tokens only, failing effects that correctly bind
   canonical role names ('source'/'destination').
B4 resolve_target: added the declared action-aware default — notify/report/inform/
   message/log actions address audit_sink when role-name and table matching fail
   (e.g. 'notify event.owner'); v1.0 fell through to surface-overlap, mis-binding
   notification targets ('event.owner' -> subject_row).
B5 termination verbatim: quote must be >=8 chars with >=2 tokens and be a substring of
   the text; v1.0's len>=4 rule passed degenerate evidence 'none' whenever the word
   'none' occurred in the text. Also: direction failure-mode attribution (missing vs
   contradiction) — attribution only, never changes an all-rows rate.
=====================================================================================
"""
import collections
import hashlib
import json
import random
import re
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
SEALED = pathlib.Path("/work1/zixuan/data/agent_memory/sealed")
V2 = HERE / "out" / "extractions_v2.jsonl"
OUTDIR = HERE / "audit_expanded"
SEED = 42

# ---------------- text utilities (condition window = previous audit's rule, verbatim) ----------------
NEG_RE = re.compile(r"\b(no|none|nobody|not|never|without)\b", re.I)
CUES = ["If ", "if ", "Guard:", "Policy:"]  # verbatim from the previous audit
CUTS = [",", ";", "\n", " -- "]


def condition_clause(text):
    pos = min((text.find(c) for c in CUES if text.find(c) != -1), default=-1)
    if pos == -1:
        return text[:300]
    rest = text[pos:]
    cut = min((rest.find(c) for c in CUTS if rest.find(c) != -1), default=len(rest))
    return rest[:cut]


def truth_polarity(text):
    return "negative" if NEG_RE.search(condition_clause(text)) else "positive"


def verified_polarity(text, clause):
    """E1 (pre-declared): else-path guard fragment re-targeting."""
    vt = truth_polarity(text)
    note = None
    if clause.strip().startswith("if it is not") and re.search(r"is '\w+'\s*--\s*if it is not", text):
        vt = "positive"
        note = "else-path guard fragment; operative condition positive upstream"
    return vt, note


def toks(s):
    if s is None:
        return set()
    out = set()
    for t in re.findall(r"[a-z0-9]+", str(s).lower()):
        out.add(t[:-1] if t.endswith("s") and len(t) > 3 else t)
    return out


def toks_raw(s):
    if s is None:
        return set()
    return set(re.findall(r"[a-z0-9]+", str(s).lower()))


def num(x):
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    m = re.search(r"-?\d+(\.\d+)?", str(x))
    return float(m.group()) if m else None


def canon_val_toks(s):
    """value tokens with floats canonicalized ('1' and '1.0' equal)."""
    out = set()
    for t in re.findall(r"[a-z0-9]+(?:\.[0-9]+)?", str(s).lower() if s is not None else ""):
        f = num(t)
        if f is not None and str(f) == t or (f is not None and t.replace(".", "").isdigit()):
            out.add(str(float(t)))
        else:
            out.add(t[:-1] if t.endswith("s") and len(t) > 3 else t)
    return out


MIN_SIDE = {"minimum", "min", "floor", "keep", "least"}
CAP_SIDE = {"capacity", "cap", "max", "maximum", "ceiling", "exceed"}
ZERO_SET = {"zero", "none", "no"}
ONE_SET = {"one", "least", "any", "some", "single"}
DELETE_ACTION = re.compile(r"delete|erase|remove", re.I)
ARCHIVE_ACTION = re.compile(r"archive", re.I)
DEC_RE = re.compile(r"(^|\W)-\s*\d|subtract|decrease|remove|minus|deduct", re.I)
INC_RE = re.compile(r"(^|\W)\+\s*\d|add|increase|deposit", re.I)


# ---------------- deterministic JSON canonicalization ----------------
def canon(o):
    """Hash-seed-independent form for sets/frozensets (sorted), recursion elsewhere.
    Determinism note: gate numbers are computed intra-process and are seed-stable with or
    without this; canon() makes the ARTIFACTS byte-reproducible across processes."""
    if isinstance(o, (set, frozenset)):
        return sorted((canon(x) for x in o), key=lambda x: json.dumps(x, sort_keys=True))
    if isinstance(o, dict):
        return {k: canon(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [canon(x) for x in o]
    return o


# ---------------- data loading & joins ----------------
def load_sealed():
    fams = {f["family_idx"]: f for f in map(json.loads, open(SEALED / "families.jsonl"))}
    tasks = [json.loads(l) for l in open(SEALED / "tasks_sealed.jsonl")]
    mems = [json.loads(l) for l in open(SEALED / "memories_sealed.jsonl")]
    sib = {}
    nm = {}
    for t in tasks:
        if t["kind"] == "sibling":
            sib[(t["family_idx"], t["sibling_idx"])] = t
        else:
            nm[t["family_idx"]] = t  # dict-last; the 4 per-family nm tasks are dimension-identical
    return fams, sib, nm, mems


def candidates_for(row, mems, sib, nm):
    """-> (cand_tasks_vectors): list of joined truth tasks + natural cells + joins meta."""
    if row["kind"] == "instruction":
        # instruction text matches sealed sibling task instruction fields
        return None  # handled by caller via instr index
    hits = [m for m in mems if m["text"] == row["text"] and m["source_kind"] != "sham"]
    cand = []
    for m in hits:
        if m["source_kind"] == "sibling_same_family":
            cand.append((sib[(m["family_idx"], m["target_sibling"])], "A11", m["source_kind"]))
        elif m["source_kind"] == "near_miss":
            cand.append((nm[m["family_idx"]], "A01", m["source_kind"]))
        else:  # cross_domain_pair / unrelated
            cell = "A10" if m["source_kind"] == "cross_domain_pair" else "A00"
            cand.append((sib[(m["source_family"], m["target_sibling"])], cell, m["source_kind"]))
    return cand


# ---------------- truth extraction from one task (per archetype) ----------------
def discriminator(guard):
    a, b = guard["a"]["where"], guard["b"]["where"]
    d = [k for k in a if a[k] != b.get(k)]
    return d[0] if d else None


def task_truth(t, arch):
    pp = t["program_params"]
    sig = t["signature"]
    tr = {"signature": sig, "archetype": arch}
    if arch == "conditional_write":
        tr["pred_attr"] = frozenset(toks(pp["cond_field"]))
        tr["pred_op"] = ("exact", pp["cond_op"])
        tr["pred_value"] = ("num", float(pp["theta"]))
        j2 = pp.get("join_depth", 1) >= 2
        tr["policy_field_tokens"] = frozenset(toks(pp.get("policy_value_field", ""))) if j2 else frozenset()
        tr["required_roles"] = frozenset({"subject_row", "policy_row"} if j2 else {"subject_row"})
        tr["effects_then"] = frozenset((frozenset(toks(k)), frozenset(canon_val_toks(v)))
                                       for k, v in pp["write_a"]["args"]["set"].items())
        tr["effects_else"] = frozenset((frozenset(toks(k)), frozenset(canon_val_toks(v)))
                                       for k, v in pp["write_b"]["args"]["set"].items())
        tr["scope"] = None
        tr["direction"] = None
        tr["archive_required"] = None
        tr["tables"] = {pp["table"]: "subject_row"}
        if j2:
            tr["tables"][pp["policy_table"]] = "policy_row"
    elif arch == "two_row_transfer":
        g = pp["guard"]
        tr["pred_attr"] = frozenset(toks(g["a"]["field"]) | toks(g["b"]["field"]))
        tr["pred_op"] = ("membership", frozenset({">=", "<="}))
        tr["pred_value"] = ("numset", frozenset({float(g["min_a"]), float(g["cap_b"])}))
        tr["required_roles"] = frozenset({"source", "destination"})
        tr["effects_then"] = frozenset({("source", "decrease"), ("destination", "increase")})
        tr["effects_else"] = frozenset()
        dk = discriminator(g)
        tr["direction"] = (frozenset(toks(g["a"]["where"][dk])), frozenset(toks(g["b"]["where"][dk]))) if dk else None
        tr["scope"] = None
        tr["archive_required"] = None
        tr["tables"] = {}
    elif arch == "aggregate_gate":
        child = pp["agg_args"]["table"]
        parent = pp["read_parent"]["table"]
        sink = pp["write_log_a"]["args"]["table"]
        tr["pred_attr"] = frozenset(toks(child) | {"count", "number"})
        tr["pred_op"] = ("exact", pp["check"]["op"])
        tr["pred_value"] = ("num", float(pp["check"]["value"]))
        tr["required_roles"] = frozenset({"subject_row", "child_set", "audit_sink"})
        pa = pp["write_parent_a"]["args"]["set"]
        pb = pp["write_parent_b"]["args"]["set"]
        assert len(pa) == 1 and len(pb) == 1
        rec_a, rec_b = pp["write_log_a"]["args"]["record"], pp["write_log_b"]["args"]["record"]
        log_key = "etype" if "etype" in rec_a else "kind"  # events family labels it "kind"
        tr["effects_then"] = frozenset({("subject_row", next(iter(pa.values()))),
                                        ("audit_sink", rec_a[log_key])})
        tr["effects_else"] = frozenset({("subject_row", next(iter(pb.values()))),
                                        ("audit_sink", rec_b[log_key])})
        # scope filter triple: the non-parent-link filter key
        flt = pp["agg_args"]["filter"]
        pkey = {k for k, v in flt.items() if pp["read_parent"]["filter"].get(k) == v}
        skey = next(k for k in flt if k not in pkey)
        sval = flt[skey]
        if isinstance(sval, dict):  # {"$ne": X}
            fop, fv = "!=", next(iter(sval.values()))
        else:
            fop, fv = "==", sval
        tr["scope"] = (child, parent, (frozenset(toks(skey)), fop, frozenset(toks(str(fv)))))
        tr["direction"] = None
        tr["archive_required"] = None
        tr["tables"] = {parent: "subject_row", child: "child_set", sink: "audit_sink"}
    elif arch == "delete_after_capture":
        tr["pred_attr"] = frozenset(toks(pp["check"]["field"]))
        tr["pred_op"] = ("exact", pp["check"]["op"])
        tr["pred_value"] = ("str", str(pp["check"]["value"]))
        arch_req = not pp.get("skip_archive", False)
        tr["archive_required"] = arch_req
        then = {("delete", "child_set"), ("delete", "subject_row")}
        if arch_req:
            then.add(("archive", "audit_sink"))
        tr["effects_then"] = frozenset(then)
        tr["effects_else"] = frozenset()
        tr["required_roles"] = frozenset({"subject_row", "child_set"} | ({"audit_sink"} if arch_req else set()))
        tr["scope"] = (pp["delete_children"]["args"]["table"], pp["check"]["table"], None)
        tr["direction"] = None
        tr["tables"] = {pp["check"]["table"]: "subject_row",
                        pp["delete_children"]["args"]["table"]: "child_set",
                        pp["archive"]["args"]["table"]: "audit_sink"}
    tr["term_required"] = True
    return tr


def consensus(cands, fams):
    """cands: list of (task, cell, source_kind). Returns per-dimension truth or 'CONFLICT'."""
    dims = ["signature", "pred_attr", "pred_op", "pred_value", "required_roles",
            "effects_then", "effects_else", "scope", "direction", "archive_required",
            "term_required", "tables", "policy_field_tokens"]
    archs = {fams[t["family_idx"]]["archetype"] for t, _, _ in cands}
    if len(archs) != 1:
        return None, {"archetype": sorted(archs)}
    arch = archs.pop()
    truths = [task_truth(t, arch) for t, _, _ in cands]
    out = {"archetype": arch}
    for d in dims:
        vals = {json.dumps(canon(tr.get(d)), sort_keys=True) for tr in truths}
        out[d] = truths[0].get(d) if len(vals) == 1 else "CONFLICT"
    return out, {}


# ---------------- IR-side extraction helpers ----------------
def id_key(n):
    digits = re.sub(r"\D", "", str(n.get("id", "")))
    return (int(digits) if digits else 0, str(n.get("id", "")))


def sorted_nodes(ir):
    return sorted(ir["nodes"], key=id_key)


def fval(fw):
    return (fw or {}).get("value")


def fstatus(fw):
    return (fw or {}).get("status")


ROLE_NAMES = ["subject_row", "policy_row", "source", "destination", "child_set", "audit_sink"]


def resolve_target(target, roles, tables, action=None):
    """Resolve an effect/node target string to a canonical role via (1) exact role name,
    (2) truth-table substring (longest first), (3) action-aware default: notify/report/
    inform/message/log actions address the audit_sink when (1)-(2) fail (per the SPEC role
    definition: audit_sink = archive/log/notification receiver),
    (4) max token overlap with a role surface (unique max required)."""
    if target is None:
        return None
    t = str(target).strip().lower()
    if t in ROLE_NAMES:
        return t
    for tbl in sorted(tables, key=len, reverse=True):
        if tbl.lower() in t:
            return tables[tbl]
    if action and re.search(r"notify|report|inform|message|log", str(action), re.I):
        return "audit_sink"
    tt = toks(t)
    best, bestn, tie = None, 0, False
    for role in ROLE_NAMES:
        surf = (roles.get(role) or {}).get("surface")
        if not surf:
            continue
        ov = len(tt & toks(surf))
        if ov > bestn:
            best, bestn, tie = role, ov, False
        elif ov == bestn and ov > 0:
            tie = True
    return None if tie else best


def effect_sign(e):
    raw = " ".join(str(x) for x in (e.get("action"), e.get("target"), e.get("value")) if x)
    if DEC_RE.search(raw):
        return "decrease"
    if INC_RE.search(raw):
        return "increase"
    return None


# ---------------- per-field scorers ----------------
INSERT_CLASS = re.compile(r"insert|copy|save|store", re.I)


def pseudo_effects(ir, roles, tables):
    """All effects: carrier/node then/else effects + standalone write nodes as pseudo-effects.
    Returns list of (ordinal, effect, node) where ordinal is a GLOBAL emission order over the
    IR (nodes id-sorted; within a node: then_effects first, then else_effects, then the node's
    own write payload) — used for capture-BEFORE-delete ordering at EFFECT granularity."""
    out = []
    k = 0
    for n in sorted_nodes(ir):
        args = n.get("args") or {}
        for lst in ("then_effects", "else_effects"):
            for e in args.get(lst) or []:
                ee = dict(e)
                ee["_branch"] = lst
                out.append((k, ee, n))
                k += 1
        if n["op"] == "write":
            out.append((k, {"action": args.get("action"), "target": args.get("target"),
                            "value": args.get("value"), "_branch": None}, n))
            k += 1
    return out


def is_delete_class(e, roles, tables):
    return bool(DELETE_ACTION.search(str(e.get("action") or "")))


def is_archive_class(e, roles, tables):
    act = str(e.get("action") or "")
    if ARCHIVE_ACTION.search(act):
        return True
    return bool(INSERT_CLASS.search(act)) and resolve_target(e.get("target"), roles, tables, act) == "audit_sink"


def p1_effect_pair(e, tables):
    tgt = str(e.get("target") or "")
    seg = tgt.split(".")[-1]
    ft = toks(seg)
    for tbl in tables:
        ft -= toks(tbl)
    for r in ROLE_NAMES:
        ft -= toks(r)
    return (frozenset(ft), frozenset(canon_val_toks(e.get("value"))))


def score_row(ir, text, truth, fams):
    """Returns dict field -> (verdict, mode, detail). verdict: True/False/None/'NA'/'UNMEAS'."""
    arch = truth["archetype"]
    roles = ir["roles"]
    tables = truth["tables"]
    clause = condition_clause(text)
    vt, vt_note = verified_polarity(text, clause)
    rec = {"_clause": clause, "_truth_polarity": vt, "_polarity_note": vt_note}

    nodes = sorted_nodes(ir)
    carriers = [n for n in nodes if (n.get("args") or {}).get("predicate")]
    carrier = carriers[0] if carriers else None
    has_branch = any(n["op"] == "branch" for n in nodes)
    rec["_carrier_op"] = carrier["op"] if carrier else None
    rec["_has_branch"] = has_branch
    pred = (carrier.get("args") or {}).get("predicate") if carrier else None

    # ---- 1-4. predicate subfields ----
    sub = {}
    if carrier is None:
        for f in ("pred_attribute", "pred_op", "pred_value", "pred_polarity"):
            sub[f] = (None, "missing", "no predicate carrier")
    else:
        pa, po, pv, pp_ = pred.get("attribute"), pred.get("op"), pred.get("value"), pred.get("polarity")
        ia, io, iv, ip = fval(pa), fval(po), fval(pv), fval(pp_)
        rec["_ir_predicate"] = {"attribute": ia, "op": io, "value": iv, "polarity": ip,
                                "statuses": {k: fstatus(pred.get(k)) for k in ("attribute", "op", "value", "polarity")}}
        # attribute
        if truth["pred_attr"] == "CONFLICT":
            sub["pred_attribute"] = ("UNMEAS", "join_conflict", None)
        elif fstatus(pa) != "present":
            sub["pred_attribute"] = (None, "absent" if fstatus(pa) == "absent" else "missing", None)
        else:
            ok = bool(truth["pred_attr"] & toks(ia))
            sub["pred_attribute"] = (ok, None if ok else "contradiction",
                                     {"ir": ia, "truth": sorted(truth["pred_attr"])})
        # op
        if truth["pred_op"] == "CONFLICT":
            sub["pred_op"] = ("UNMEAS", "join_conflict", None)
        elif fstatus(po) != "present":
            sub["pred_op"] = (None, "absent" if fstatus(po) == "absent" else "missing", None)
        else:
            mode, tv = truth["pred_op"]
            ok = (io == tv) if mode == "exact" else (io in tv)
            sub["pred_op"] = (ok, None if ok else "contradiction",
                              {"ir": io, "truth": tv if mode == "exact" else sorted(tv)})
        # value
        if truth["pred_value"] == "CONFLICT":
            sub["pred_value"] = ("UNMEAS", "join_conflict", "text does not determine value")
        elif fstatus(pv) != "present":
            sub["pred_value"] = (None, "absent" if fstatus(pv) == "absent" else "missing", None)
        else:
            sub["pred_value"] = score_value(iv, truth, arch, clause)
        # polarity
        if fstatus(pp_) != "present":
            sub["pred_polarity"] = (None, "absent" if fstatus(pp_) == "absent" else "missing", None)
        else:
            ok = (ip == vt)
            sub["pred_polarity"] = (ok, None if ok else "contradiction",
                                    {"ir": ip, "truth": vt, "note": vt_note})
    vs = [sub[f][0] for f in ("pred_attribute", "pred_op", "pred_value", "pred_polarity")]
    if any(v is False for v in vs):
        sub["pred_all"] = (False, "contradiction", None)
    elif all(v is True for v in vs):
        sub["pred_all"] = (True, None, None)
    elif any(v == "UNMEAS" for v in vs):
        sub["pred_all"] = ("UNMEAS", "join_conflict", None)
    else:
        sub["pred_all"] = (None, "missing", None)
    rec.update(sub)

    # ---- 5. branch effects ----
    if "CONFLICT" in (truth["effects_then"], truth["effects_else"]):
        rec["branch_effects"] = ("UNMEAS", "join_conflict", None)
    elif carrier is None:
        rec["branch_effects"] = (None, "missing", "no predicate carrier")
    else:
        args = carrier.get("args") or {}
        ith, iel = args.get("then_effects") or [], args.get("else_effects") or []
        rec["branch_effects"] = score_effects(ith, iel, truth, arch, roles, tables)
    # effects payload location diagnostic
    all_e = pseudo_effects(ir, roles, tables)
    n_eff = len(all_e)
    rec["_effects_payload"] = {"carrier_then": len((carrier.get("args") or {}).get("then_effects") or []) if carrier else 0,
                               "carrier_else": len((carrier.get("args") or {}).get("else_effects") or []) if carrier else 0,
                               "total_effects_incl_write_nodes": n_eff}

    # ---- 6. direction (P2) ----
    if arch != "two_row_transfer":
        rec["direction"] = ("NA", None, None)
    elif truth["direction"] == "CONFLICT":
        rec["direction"] = ("UNMEAS", "join_conflict", None)
    else:
        rec["direction"] = score_direction(ir, truth, roles, tables, all_e)

    # ---- 7. scope (P3/P4) ----
    if arch == "aggregate_gate":
        rec["scope"] = score_scope_p3(ir, truth, roles, tables) if truth["scope"] != "CONFLICT" else ("UNMEAS", "join_conflict", None)
    elif arch == "delete_after_capture":
        rec["scope"] = score_scope_p4(ir, roles, tables, all_e) if truth["scope"] != "CONFLICT" else ("UNMEAS", "join_conflict", None)
    else:
        rec["scope"] = ("NA", None, None)

    # ---- 8. archive capture (P4 archive-required) ----
    if truth["archive_required"] == "CONFLICT":
        rec["archive_capture"] = ("UNMEAS", "join_conflict", None)
    elif arch != "delete_after_capture" or not truth["archive_required"]:
        rec["archive_capture"] = ("NA", None, None)
    else:
        rec["archive_capture"] = score_archive(ir, roles, tables, all_e)

    # ---- 9. roles required ----
    if truth["required_roles"] == "CONFLICT":
        rec["roles_required"] = ("UNMEAS", "join_conflict", None)
    else:
        slots = {}
        n_absent = n_present = 0
        for r in sorted(truth["required_roles"]):
            st = (roles.get(r) or {}).get("status")
            slots[r] = st
            n_absent += st == "absent"
            n_present += st == "present"
        ok = n_absent == 0 and n_present > 0
        rec["roles_required"] = (ok, None if ok else ("absent" if n_absent else "missing"),
                                 {"slots": slots, "n_absent": n_absent, "n_present": n_present,
                                  "n_slots": len(slots)})
        rec["_role_slots"] = slots

    # ---- 10. termination ----
    t = ir.get("termination") or {}
    tst, tev = t.get("status"), (t.get("evidence") or "")
    if tst == "absent":
        rec["termination"] = (False, "absent", {"evidence": tev})
    elif tst != "present":
        rec["termination"] = (None, "missing", None)
    else:
        ev = tev.strip()
        ok = (len(ev) >= 8 and len(re.findall(r"[a-z0-9]+", ev.lower())) >= 2
              and ev.lower() in text.lower())
        rec["termination"] = (ok, None if ok else "contradiction", {"evidence": tev})
    return rec


# ---------------- scorer helpers ----------------
def num_stated(x, clause):
    """Is truth number x textually present in the condition window? Int-normalized probe
    (0.0 -> '0') with word boundaries (theta 5 must not fire inside '15')."""
    probe = str(int(x)) if float(x) == int(float(x)) else str(float(x))
    return bool(re.search(r"(?<![\d.])" + re.escape(probe) + r"(?![\d.])", clause))


def score_value(iv, truth, arch, clause):
    mode, tv = truth["pred_value"]
    iv_digits = bool(re.search(r"\d", str(iv))) if iv is not None else False
    if mode in ("num", "numset"):
        if mode == "num":
            truth_no = tv
            stated = num_stated(tv, clause)
        else:
            truth_no = sorted(tv)
            stated = any(num_stated(x, clause) for x in tv)
        if stated:  # numeric rule
            if mode == "num":
                ok = num(iv) is not None and num(iv) == tv
            else:
                ok = num(iv) is not None and num(iv) in tv
            return (ok, None if ok else "contradiction",
                    {"rule": "numeric", "ir": iv, "truth": truth_no})
        # digit-absent -> value-as-stated (E2)
        if iv_digits:  # fabricated number: digits match no truth number
            if mode == "numset" and num(iv) in tv or mode == "num" and num(iv) == tv:
                return (True, None, {"rule": "numeric-membership", "ir": iv, "truth": truth_no})
            return (False, "contradiction",
                    {"rule": "digit-absent-foreign-number", "ir": iv, "truth": truth_no})
        ivt = toks(iv)
        if mode == "numset":  # P2 symbolic threshold reference
            hit = bool(ivt & MIN_SIDE) or bool(ivt & CAP_SIDE)
        elif arch == "conditional_write":
            pft = truth.get("policy_field_tokens") or frozenset()
            if pft:
                hit = pft <= ivt
            else:
                return ("UNMEAS", "unmeasurable",
                        {"rule": "digits-absent-no-symbolic-handle", "ir": iv, "truth": truth_no})
        else:  # P3 concept thresholds
            hit = bool(ivt & (ZERO_SET if tv == 0.0 else ONE_SET))
        return (hit, None if hit else "contradiction",
                {"rule": "value-as-stated", "ir": iv, "truth": truth_no})
    # P4 string rule
    truth_tok = toks(tv)
    if tv in clause:
        ok = str(iv).strip("'\"").lower() == str(tv).strip("'\"").lower()
        return (ok, None if ok else "contradiction", {"rule": "string-exact", "ir": iv, "truth": tv})
    ok = bool(truth_tok & toks(iv))
    return (ok, None if ok else "contradiction", {"rule": "string-symbolic", "ir": iv, "truth": tv})


def score_effects(ith, iel, truth, arch, roles, tables):
    if arch == "conditional_write":
        def disp(S):
            return sorted(([sorted(a), sorted(b)] for a, b in S), key=lambda x: (x[0], x[1]))
        th = frozenset(p1_effect_pair(e, tables) for e in ith)
        el = frozenset(p1_effect_pair(e, tables) for e in iel)
        ok = th == truth["effects_then"] and el == truth["effects_else"]
        return (ok, None if ok else "contradiction",
                {"ir_then": disp(th), "ir_else": disp(el),
                 "truth_then": disp(truth["effects_then"]),
                 "truth_else": disp(truth["effects_else"])})
    if arch == "two_row_transfer":
        sd, dd = truth["direction"] if truth["direction"] != "CONFLICT" else (frozenset(), frozenset())
        viol = []
        found = {"source": False, "destination": False}
        for e in ith:
            sgn = effect_sign(e)
            tt = toks(e.get("target"))
            # role alpha-renaming: canonical role name / resolver first, descriptor tokens as fallback
            role = resolve_target(e.get("target"), roles, tables, e.get("action"))
            if role not in ("source", "destination"):
                role = ("source" if sd and sd <= tt else
                        "destination" if dd and dd <= tt else None)
            if sgn == "decrease":
                if role == "source":
                    found["source"] = True
                elif role == "destination":
                    viol.append(("decrease@destination", e))
            elif sgn == "increase":
                if role == "destination":
                    found["destination"] = True
                elif role == "source":
                    viol.append(("increase@source", e))
        else_signed = [e for e in iel if effect_sign(e)]
        ok = all(found.values()) and not viol and not else_signed
        return (ok, None if ok else ("missing" if not any(found.values()) and not ith else "contradiction"),
                {"found": found, "violations": [v[0] for v in viol], "else_signed": len(else_signed)})
    if arch == "aggregate_gate":
        def match_set(ir_effs, truth_set):
            used = set()
            miss = []
            for (role, tokv) in truth_set:
                tset = toks(str(tokv))
                hit = False
                for (role2, e) in ir_effs:
                    if role2 == role and tset <= toks(e.get("value")) | toks(e.get("action")):
                        used.add(id(e))
                        hit = True
                        break
                if not hit:
                    miss.append((role, tokv))
            extra = [(role2, e) for (role2, e) in ir_effs
                     if role2 in ("subject_row", "audit_sink") and id(e) not in used]
            return sorted(miss, key=str), extra
        th_eff = [(resolve_target(e.get("target"), roles, tables, e.get("action")), e) for e in ith]
        el_eff = [(resolve_target(e.get("target"), roles, tables, e.get("action")), e) for e in iel]
        m_th, x_th = match_set(th_eff, truth["effects_then"])
        m_el, x_el = match_set(el_eff, truth["effects_else"])
        # extras on truth roles are benign iff they match the branch's own outcome for that role
        def clean_extra(xs, truth_set):
            out = []
            for role2, e in xs:
                vals = toks(e.get("value")) | toks(e.get("action"))
                if not any(role2 == r and toks(str(v)) <= vals for (r, v) in truth_set):
                    out.append((role2, e.get("target"), e.get("value")))
            return out
        x_th, x_el = clean_extra(x_th, truth["effects_then"]), clean_extra(x_el, truth["effects_else"])
        ok = not m_th and not m_el and not x_th and not x_el
        mode = None if ok else ("missing" if (m_th or m_el) and not x_th and not x_el else "contradiction")
        return (ok, mode, {"missing_then": m_th, "missing_else": m_el,
                           "extra_then": x_th, "extra_else": x_el})
    if arch == "delete_after_capture":
        th = frozenset(("archive" if is_archive_class(e, roles, tables) else "delete",
                        resolve_target(e.get("target"), roles, tables, e.get("action")))
                       for e in ith if is_delete_class(e, roles, tables) or is_archive_class(e, roles, tables))
        el = [e for e in iel if is_delete_class(e, roles, tables) or is_archive_class(e, roles, tables)]
        ok_then = th == truth["effects_then"]
        ok_else = len(el) == 0
        ok = ok_then and ok_else
        return (ok, None if ok else ("missing" if (truth["effects_then"] - th) and not el else "contradiction"),
                {"ir_then": sorted((c, str(r)) for (c, r) in th),
                 "truth_then": sorted((c, str(r)) for (c, r) in truth["effects_then"]),
                 "else_violations": len(el)})
    raise ValueError(arch)


def score_direction(ir, truth, roles, tables, all_e):
    sd, dd = truth["direction"]
    src_txt = " ".join(str(x) for x in ((roles.get("source") or {}).get("surface"),
                                        (roles.get("source") or {}).get("evidence")) if x)
    dst_txt = " ".join(str(x) for x in ((roles.get("destination") or {}).get("surface"),
                                        (roles.get("destination") or {}).get("evidence")) if x)
    for _, e, _n in all_e:
        sgn = effect_sign(e)
        raw = " ".join(str(x) for x in (e.get("action"), e.get("target"), e.get("value")) if x)
        if sgn == "decrease":
            src_txt += " " + raw
        elif sgn == "increase":
            dst_txt += " " + raw
    st, dt = toks(src_txt), toks(dst_txt)
    if not st and not dt:
        return (None, "missing", "no direction payload")
    ok = sd <= st and dd <= dt and not (sd & dt) and not (dd & st)
    # failure-mode attribution (does not change all-rows): a side whose role is not
    # asserted 'present' AND whose channel carries no signed effect is an OMISSION;
    # a side carrying content that binds the wrong or the other side's descriptor is a
    # CONTRADICTION.
    def side_empty(role_name):
        want = "decrease" if role_name == "source" else "increase"
        has_signed = any(effect_sign(e) == want for _, e, _n in all_e)
        return ((roles.get(role_name) or {}).get("status") != "present"
                and not toks(str((roles.get(role_name) or {}).get("surface") or ""))
                and not has_signed)
    miss = (sd - st and side_empty("source")) or (dd - dt and side_empty("destination"))
    mode = None if ok else ("missing" if miss else "contradiction")
    return (ok, mode,
            {"source_desc": sorted(sd), "dest_desc": sorted(dd),
             "leak_source_in_dest": sorted(sd & dt), "leak_dest_in_source": sorted(dd & st)})


def score_scope_p3(ir, truth, roles, tables):
    child, parent, (fattr, fop, fvalset) = truth["scope"]
    aggs = [n for n in sorted_nodes(ir) if n["op"] in ("aggregate", "list")]
    if not aggs:
        return (None, "missing", "no aggregate/list node")
    n = aggs[0]
    args = n.get("args") or {}
    rel = resolve_target(args.get("over") or args.get("target"), roles, tables)
    rel_ok = rel == "child_set"
    pred = args.get("predicate")
    if pred:
        i_triple = (toks(fval(pred.get("attribute"))), fval(pred.get("op")), toks(fval(pred.get("value"))))
        filt_ok = (i_triple == (fattr, fop, fvalset)) and fstatus(pred.get("value")) == "present"
        src = "predicate"
    else:  # keyword parse of args.value (pre-registered fallback)
        low = str(args.get("value") or "").lower()
        iop = "!=" if re.search(r"\bnot\b|\bnon\b|isn't|aren't", low) else "=="
        i_triple = (toks(args.get("value")) & fattr, iop, toks(low) & fvalset)
        filt_ok = (i_triple == (fattr, fop, fvalset))
        src = "args.value-parse"
    ok = rel_ok and filt_ok
    return (ok, None if ok else ("missing" if not rel_ok and not filt_ok else "contradiction"),
            {"relation": rel, "filter_source": src, "ir_filter": [sorted(i_triple[0]), i_triple[1], sorted(i_triple[2])],
             "truth_filter": [sorted(fattr), fop, sorted(fvalset)]})


def score_scope_p4(ir, roles, tables, all_e):
    hits = set()
    for _, e, _n in all_e:
        if is_delete_class(e, roles, tables):
            hits.add(resolve_target(e.get("target"), roles, tables))
    if not hits:
        return (None, "missing", "no delete-class effect target")
    ok = "child_set" in hits
    return (ok, None if ok else "contradiction", {"resolved_delete_targets": sorted(h for h in hits if h)})


def score_archive(ir, roles, tables, all_e):
    arch_pos = [pos for pos, e, _n in all_e if is_archive_class(e, roles, tables)]
    del_pos = [pos for pos, e, _n in all_e if is_delete_class(e, roles, tables)]
    presence = bool(arch_pos)
    ordering = (min(arch_pos) < min(del_pos)) if arch_pos and del_pos else (bool(arch_pos) if not del_pos else False)
    ok = presence and ordering
    mode = None if ok else ("missing" if not presence else "contradiction")
    return (ok, mode, {"archive_positions": arch_pos, "delete_positions": del_pos,
                       "audit_sink_status": (ir["roles"].get("audit_sink") or {}).get("status")})


# ---------------- main ----------------
GATE_FIELDS = ["pred_attribute", "pred_op", "pred_value", "pred_polarity", "pred_all",
               "branch_effects", "direction", "scope", "archive_capture",
               "roles_required", "termination"]


def main():
    OUTDIR.mkdir(exist_ok=True)
    fams, sib, nm, mems = load_sealed()
    instr_idx = collections.defaultdict(list)
    for (fi, si), t in sib.items():
        instr_idx[t["instruction"]].append(t)
    rows = [json.loads(l) for l in open(V2)]
    assert all(r.get("valid") for r in rows) and len(rows) == 532

    per_sample = []
    join_stats = {"n_candidates": collections.Counter(), "conflicts": collections.Counter(),
                  "no_join": 0, "arch_conflict": 0}
    for r in rows:
        if r["kind"] == "instruction":
            cand = [(t, None, "instruction") for t in instr_idx.get(r["text"], [])]
        else:
            cand = candidates_for(r, mems, sib, nm)
        join_stats["n_candidates"][len(cand)] += 1
        if not cand:
            join_stats["no_join"] += 1
            per_sample.append({"key": r["key"], "kind": r["kind"], "join_failed": True})
            continue
        truth, arch_issue = consensus(cand, fams)
        if truth is None:
            join_stats["arch_conflict"] += 1
            per_sample.append({"key": r["key"], "kind": r["kind"], "join_failed": True,
                               "arch_conflict": arch_issue})
            continue
        for d, v in truth.items():
            if v == "CONFLICT":
                join_stats["conflicts"][d] += 1
        scores = score_row(r["ir"], r["text"], truth, fams)
        clause = scores.pop("_clause"); tpol = scores.pop("_truth_polarity"); pnote = scores.pop("_polarity_note")
        cells = sorted({c for _, c, sk in cand if c})
        sks = sorted({sk for _, _, sk in cand})
        fam_idx = cand[0][0]["family_idx"]
        per_sample.append({
            "key": r["key"], "kind": r["kind"], "text": r["text"],
            "archetype": truth["archetype"], "family_idx": fam_idx, "signature": truth["signature"],
            "cells": cells, "source_kinds": sks, "n_candidates": len(cand),
            "scores": scores, "polarity_clause": clause, "truth_polarity": tpol,
            "polarity_note": pnote, "ir": r["ir"],
            "truth_excerpt": {k: (canon(truth[k])
                                  if truth[k] != "CONFLICT" else "CONFLICT")
                              for k in ("pred_attr", "pred_op", "pred_value", "required_roles",
                                        "effects_then", "effects_else", "scope", "direction",
                                        "archive_required")},
        })

    # ---------- aggregation ----------
    joined = [p for p in per_sample if not p.get("join_failed")]
    metrics = {"corpus": corpus_stats(joined, fams), "fields": {},
               "posthoc_diagnostics": posthoc_diagnostics(joined)}
    for field in GATE_FIELDS + ["branch_presence"]:
        metrics["fields"][field] = aggregate_field(joined, field)
    metrics["join"] = {"n_candidates": dict(join_stats["n_candidates"]),
                       "conflicts": dict(join_stats["conflicts"]),
                       "no_join": join_stats["no_join"], "arch_conflict": join_stats["arch_conflict"],
                       "n_joined": len(joined)}
    metrics["gate_rule"] = {"overall": 0.90, "per_archetype": 0.80, "false_absent": 0.05,
                            "agreement_rate": "all-rows (missing counts as disagreement; "
                                              "UNMEASURABLE/NA excluded from denominators)"}
    metrics["veto_rule"] = ("PASS -> HARD VETO; FAIL & present_only>=0.90 -> positive-only veto / "
                            "soft evidence (unknown-if-absent); FAIL & present_only<0.90 -> excluded")

    with open(OUTDIR / "per_sample.jsonl", "w") as f:
        for p in per_sample:
            f.write(json.dumps(canon(p), ensure_ascii=False) + "\n")
    with open(OUTDIR / "field_metrics.json", "w") as f:
        json.dump(canon(metrics), f, indent=2, ensure_ascii=False)

    write_stratified(joined)
    write_failed_examples(joined, metrics)
    receipt = {"code_sha": hashlib.sha256(open(__file__, "rb").read()).hexdigest()[:16],
               "seed": SEED, "n_rows": len(rows), "n_joined": len(joined),
               "outputs": ["per_sample.jsonl", "field_metrics.json", "stratified.jsonl",
                           "failed_examples/", "AUDIT_EXPANDED.md (hand-written analysis)"],
               "gate": metrics["gate_rule"]}
    with open(OUTDIR / "run_receipt.json", "w") as f:
        json.dump(receipt, f, indent=2)
    print(json.dumps({k: {kk: metrics["fields"][k][kk] for kk in
                          ("n_app", "all_rows", "present_only", "worst_archetype", "false_absent",
                           "gate")} for k in GATE_FIELDS}, indent=2, default=str))
    print(json.dumps({"branch_presence": metrics["fields"]["branch_presence"],
                      "join": metrics["join"]}, indent=2, default=str)[:1500])


def aggregate_field(joined, field):
    if field == "branch_presence":
        per_arch = collections.Counter()
        tot = collections.Counter()
        for p in joined:
            per_arch[(p["archetype"], p["scores"]["_has_branch"])] += 1
            tot[p["scores"]["_has_branch"]] += 1
        archs = sorted({p["archetype"] for p in joined})
        return {"context_only": True, "has_branch_overall": tot[True] / len(joined),
                "n": len(joined), "n_has_branch": tot[True],
                "per_archetype": {a: {"n": sum(n for (aa, _), n in per_arch.items() if aa == a),
                                      "has_branch_rate": per_arch[(a, True)] / max(1, sum(n for (aa, _), n in per_arch.items() if aa == a))}
                                  for a in archs},
                "note": "fraction of IRs containing >=1 branch node (op==branch, any status); "
                        "the predicate/effects payload may sit on a non-branch carrier (see corpus.carrier_mix)"}
    agg = {"n_app": 0, "n_na": 0, "n_unmeas": 0, "agree": 0, "disagree": 0, "missing": 0,
           "false_absent": 0, "missing_examples_keys": [], "disagree_examples_keys": [],
           "per_archetype": collections.defaultdict(lambda: {"n_app": 0, "agree": 0, "false_absent": 0})}
    slot_stats = {"n_slots": 0, "absent": 0, "present": 0, "unknown": 0,
                  "per_archetype": collections.defaultdict(lambda: {"n_slots": 0, "absent": 0, "present": 0, "unknown": 0})}
    for p in joined:
        v, mode, detail = p["scores"][field]
        a = p["archetype"]
        if field == "roles_required" and v != "UNMEAS":
            sl = detail["slots"] if detail else {}
            slot_stats["n_slots"] += len(sl)
            slot_stats["absent"] += sum(1 for x in sl.values() if x == "absent")
            slot_stats["present"] += sum(1 for x in sl.values() if x == "present")
            slot_stats["unknown"] += sum(1 for x in sl.values() if x == "unknown")
            sa = slot_stats["per_archetype"][a]
            sa["n_slots"] += len(sl)
            for x in sl.values():
                sa[{"absent": "absent", "present": "present", "unknown": "unknown"}.get(x, "unknown")] += 1
        if v == "NA":
            agg["n_na"] += 1
            continue
        if v == "UNMEAS":
            agg["n_unmeas"] += 1
            continue
        agg["n_app"] += 1
        agg["per_archetype"][a]["n_app"] += 1
        if v is True:
            agg["agree"] += 1
            agg["per_archetype"][a]["agree"] += 1
        elif v is False:
            agg["disagree"] += 1
            if mode == "absent":
                agg["false_absent"] += 1
                agg["per_archetype"][a]["false_absent"] += 1
            agg["disagree_examples_keys"].append((p["key"], mode))
        else:
            agg["missing"] += 1
            if mode == "absent":
                agg["false_absent"] += 1
                agg["per_archetype"][a]["false_absent"] += 1
            agg["missing_examples_keys"].append(p["key"])
    n_app = agg["n_app"]
    pa = {a: {"n_app": d["n_app"],
              "all_rows": d["agree"] / d["n_app"] if d["n_app"] else None,
              "false_absent": d["false_absent"] / d["n_app"] if d["n_app"] else None}
          for a, d in agg["per_archetype"].items()}
    worst = min((v["all_rows"] for v in pa.values() if v["all_rows"] is not None), default=None)
    all_rows = agg["agree"] / n_app if n_app else None
    present_only = agg["agree"] / (agg["agree"] + agg["disagree"]) if (agg["agree"] + agg["disagree"]) else None
    fa = agg["false_absent"] / n_app if n_app else None
    out = {"n_app": n_app, "n_na": agg["n_na"], "n_unmeas": agg["n_unmeas"],
           "agree": agg["agree"], "disagree": agg["disagree"], "missing": agg["missing"],
           "all_rows": all_rows, "present_only": present_only,
           "worst_archetype": worst, "per_archetype": pa, "false_absent": fa,
           "n_disagree_missing": {"contradiction": sum(1 for _, m in agg["disagree_examples_keys"] if m != "absent"),
                                  "missing": len(agg["missing_examples_keys"])}}
    out["disagree_examples_keys"] = agg["disagree_examples_keys"][:30]
    out["missing_examples_keys"] = agg["missing_examples_keys"][:30]
    if field == "roles_required":
        out["slot_level"] = {
            "n_slots": slot_stats["n_slots"],
            "present_rate": slot_stats["present"] / slot_stats["n_slots"],
            "absent_rate": slot_stats["absent"] / slot_stats["n_slots"],
            "unknown_rate": slot_stats["unknown"] / slot_stats["n_slots"],
            "per_archetype": {a: {"present_rate": d["present"] / d["n_slots"],
                                  "absent_rate": d["absent"] / d["n_slots"],
                                  "unknown_rate": d["unknown"] / d["n_slots"]}
                              for a, d in slot_stats["per_archetype"].items()}}
    # gate (frozen criteria)
    g_overall = all_rows is not None and all_rows >= 0.90
    g_arch = worst is not None and worst >= 0.80
    g_fa = fa is not None and fa <= 0.05
    passed = g_overall and g_arch and g_fa
    out["gate"] = {"overall_ok": g_overall, "per_archetype_ok": g_arch, "false_absent_ok": g_fa,
                   "PASS": passed}
    if field != "branch_presence":
        po = present_only if present_only is not None else 0
        out["veto_eligibility"] = ("HARD VETO" if passed else
                                   "positive-only veto / soft evidence (unknown-if-absent)" if po >= 0.90
                                   else "excluded from veto fields")
    return out


def posthoc_diagnostics(joined):
    """NON-GATE post-hoc diagnostics (reported only; never change a gate number):
    D1 of pred_attribute disagreements, the share whose IR attribute is nevertheless a
       verbatim text substring (text-faithful concept, sealed-field-name mismatch —
       e.g. 'on-hand quantity' vs field 'qty');
    D2 polarity disagreement direction matrix (ir -> truth), and among P3 the share
       that is the normalization direction (ir positive / truth negative-from-frozen-
       rule, i.e. the IR re-anchored the condition to its positive count form);
    D3 among the value no-handle UNMEASURABLE rows, the share whose IR value is a
       non-numeric symbolic reference (value-as-stated-like: text does not determine
       theta but the IR still names the policy/threshold concept)."""
    af = [p for p in joined if p["scores"]["pred_attribute"][0] is False]
    n_txt = 0
    for p in af:
        irat = (p["scores"].get("_ir_predicate") or {}).get("attribute")
        if irat and str(irat).strip().lower() in p["text"].lower():
            n_txt += 1
    d1 = {"n_attribute_disagreements": len(af), "n_ir_attribute_verbatim_in_text": n_txt,
          "share": n_txt / len(af) if af else None}
    pol = collections.Counter()
    for p in joined:
        v, mode, det = p["scores"]["pred_polarity"]
        if v is False and det:
            pol[(det["ir"], det["truth"])] += 1
    p3_pol_false = [p for p in joined
                    if p["archetype"] == "aggregate_gate" and p["scores"]["pred_polarity"][0] is False]
    p3_norm = sum(1 for p in p3_pol_false
                  if (p["scores"]["_ir_predicate"] or {}).get("polarity") == "positive"
                  and p["truth_polarity"] == "negative")
    d2 = {"polarity_direction_matrix": {f"{i}->{t}": n for (i, t), n in pol.most_common()},
          "p3_polarity_disagreements": len(p3_pol_false),
          "p3_ir_positive_truth_negative_share": p3_norm / len(p3_pol_false) if p3_pol_false else None}
    uh = [p for p in joined if p["scores"]["pred_value"][0] == "UNMEAS"
          and isinstance(p["scores"]["pred_value"][2], dict)
          and p["scores"]["pred_value"][2].get("rule") == "digits-absent-no-symbolic-handle"]
    n_sym = sum(1 for p in uh
                if (p["scores"].get("_ir_predicate") or {}).get("value") is not None
                and not re.search(r"\d", str(p["scores"]["_ir_predicate"]["value"])))
    d3 = {"n_no_handle_unmeasurable": len(uh),
          "n_ir_value_symbolic_nonnumeric": n_sym,
          "share": n_sym / len(uh) if uh else None}
    return {"D1_attribute_text_faithfulness": d1, "D2_polarity_direction": d2,
            "D3_value_symbolic_unmeasurable": d3}


def corpus_stats(joined, fams):
    c = {"n": len(joined),
         "by_kind": dict(collections.Counter(p["kind"] for p in joined)),
         "by_archetype": dict(collections.Counter(p["archetype"] for p in joined)),
         "carrier_mix": {}, "effects_payload": {}, "termination_status": {},
         "roles_status_mix_all_slots": {}}
    cm = collections.Counter((p["archetype"], p["scores"]["_carrier_op"]) for p in joined)
    c["carrier_mix"] = {f"{a}|{op}": n for (a, op), n in sorted(cm.items(), key=lambda kv: (kv[0][0], str(kv[0][1])))}
    ep = collections.Counter()
    for p in joined:
        d = p["scores"]["_effects_payload"]
        loc = ("carrier+extra" if d["carrier_then"] + d["carrier_else"] > 0 and d["total_effects_incl_write_nodes"] > d["carrier_then"] + d["carrier_else"]
               else "carrier_only" if d["carrier_then"] + d["carrier_else"] > 0
               else "write_nodes_only" if d["total_effects_incl_write_nodes"] > 0 else "none")
        ep[(p["archetype"], loc)] += 1
    c["effects_payload_location"] = {f"{a}|{loc}": n for (a, loc), n in sorted(ep.items())}
    c["termination_status"] = dict(collections.Counter(
        (p["ir"].get("termination") or {}).get("status") for p in joined))
    rs = collections.Counter()
    for p in joined:
        for role in ROLE_NAMES:
            rs[(p["ir"]["roles"].get(role) or {}).get("status")] += 1
    tot = sum(rs.values())
    c["roles_status_mix_all_slots"] = {k: {"n": v, "rate": v / tot} for k, v in rs.items()}
    return c


def write_stratified(joined):
    rng = random.Random(SEED)
    mem = [p for p in joined if p["kind"] == "memory"]
    ins = [p for p in joined if p["kind"] == "instruction"]
    archs = sorted({p["archetype"] for p in joined})
    picked, used = [], set()
    coverage = {}
    for a in archs:
        for cell in ("A01", "A10", "A11"):
            pool = sorted([p for p in mem if p["archetype"] == a and cell in p["cells"]
                           and p["key"] not in used], key=lambda p: p["key"])
            k = min(4, len(pool))
            sel = rng.sample(pool, k) if k else []
            for p in sel:
                used.add(p["key"])
            coverage[f"{a}|{cell}"] = {"pool": len(pool) + sum(1 for p in mem if p["archetype"] == a and cell in p["cells"] and p["key"] in used and p in sel),
                                       "sampled": len(sel)}
            picked.extend((a, cell, p) for p in sel)
    for a in archs:
        pool = sorted([p for p in ins if p["archetype"] == a], key=lambda p: p["key"])
        sel = rng.sample(pool, min(2, len(pool)))
        picked.extend((a, "(instruction)", p) for p in sel)
    with open(OUTDIR / "stratified.jsonl", "w") as f:
        f.write(json.dumps({"_coverage": coverage, "_seed": SEED,
                            "_note": "hand-verifiable stratified sample; cells from memory-side joins; "
                                     "instruction texts are cell-free (2 per archetype sampled separately)"},
                           ensure_ascii=False) + "\n")
        for a, cell, p in picked:
            f.write(json.dumps(canon({"bucket_archetype": a, "bucket_cell": cell, **p}),
                               ensure_ascii=False) + "\n")


def write_failed_examples(joined, metrics):
    exdir = OUTDIR / "failed_examples"
    exdir.mkdir(exist_ok=True)
    idx = {p["key"]: p for p in joined}
    for field, m in metrics["fields"].items():
        if m.get("context_only") or m["gate"]["PASS"]:
            continue
        keys = ([(k, "contradiction" if md != "absent" else "absent") for k, md in m["disagree_examples_keys"][:12]]
                + [(k, "missing") for k in m["missing_examples_keys"][:8]])
        with open(exdir / f"{field}.jsonl", "w") as f:
            for k, why in keys:
                p = idx[k]
                f.write(json.dumps(canon({"field": field, "failure": why, "key": k, "kind": p["kind"],
                                    "archetype": p["archetype"], "cells": p["cells"],
                                    "signature": p["signature"], "text": p["text"],
                                    "score": p["scores"][field], "ir_predicate": p["scores"].get("_ir_predicate"),
                                    "polarity_clause": p["polarity_clause"],
                                    "truth_excerpt": p["truth_excerpt"],
                                    "ir": p["ir"]}), ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
