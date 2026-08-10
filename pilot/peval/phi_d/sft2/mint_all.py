#!/usr/bin/env python
"""mint_all.py — SFT2 full production mint (phi+d lane C, data stage).

Scales the adjudicated SFT1 P1 mint to all 8 schemas x 200 families x 20 texts
under the frozen production conditions (SFT1 §8 GO-conditions + DATA_SPEC.md):

  * 200 NEW families (25 per schema, interleaved, plan_families port) under
    gs_mint = 20260812 (distinct from sealed 20260807 and pilot 20260811);
    P1 join-depth cycles extend the generator's own patterns: crm 15 J1 + 10 J2,
    inv 10 J1 + 15 J2.
  * family split BEFORE rendering, plan-entry only: within each
    (schema, join_depth) stratum, rank by sha1(gs|group|idx), frozen quotas
    GROUP_QUOTA -> 150 train / 25 val / 25 test families (3000/500/500 texts).
  * per family 20 texts: 4 sibling instructions ((idx+s)%3 styles) + 1 near-miss
    instruction (idx%3) + cards A11 x4, A10 x2, plus par(family): even idx gets
    A01 x4 + A00 x5, odd idx A01 x5 + A00 x4 (A01/A00 5th slot = documented
    extra slot, same roles, next Latin style).
  * mint corrections extended to ALL schemas (adjudication condition 1):
    entity-instantiated cards, dedupe-by-rotation, word-boundary numeric probes.
  * numeric-printing card lever (DATA_SPEC §4): per-slot deterministic coin on
    P1/P2 schemas; statedness decided from the RENDERED text bidirectionally.
  * gold evidence clips <= 12 words; per-item hard gates: validate_ir, op
    sequence (kind-aware signature expansion), predicate op == program op
    (incl. near-miss flips), polarity rule outcome, statedness bidirectional,
    evidence re-slice (verbatim, <=12w, pre-filler core), decontamination
    (732 sealed reference hashes, zero collisions), global text uniqueness,
    audit self-check (whitelisted measurement gaps only — DATA_QC.md).
  * nested frozen subsets LC300 < LC1000 < LC3000 over the 3000 train texts
    ordered by sha1(gs|"curve"|pair_id); per-archetype share within +-5pp of
    the global train mix asserted at each level.
  * kill conditions: a family whose slot exhausts all sibling variants x style
    rotations is STOPPED and counted; if stopped texts exceed 1% of the 4000
    planned, the whole mint aborts with a report (no post-hoc patching).

Run:  cd pilot/peval/phi_d/sft2 && PY mint_all.py                 # full mint
      PY mint_all.py --schemas inv_transfer --max-fam 1           # 20-pair dev mini-batch
"""
import argparse
import collections
import hashlib
import json
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent            # pilot/peval/phi_d/sft2
PHI_D = HERE.parent
for p in (str(PHI_D.parent.parent), str(PHI_D), str(PHI_D / "sft0"), str(PHI_D / "sft1")):
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ.setdefault("HF_HOME", "/work1/zixuan/cache/huggingface")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import generate_families as G                             # noqa: E402
from program_dsl import ARCHETYPES                        # noqa: E402
from common import load_pairs, validate_ir                # noqa: E402
import mint_spec as M                                     # noqa: E402
import mint_p1 as MP                                      # noqa: E402
import mint_core as C                                     # noqa: E402
import mint_p1x as P1X                                    # noqa: E402
import mint_p2x as P2X                                    # noqa: E402
import mint_p3x as P3X                                    # noqa: E402
import mint_p4x as P4X                                    # noqa: E402

GS_MINT = 20260812
SEALED_SEED = 20260807
N_FAM = 200
N_SIB = 4
P1_SCHEMAS = ("crm_escalate", "inv_overstock")
P2_SCHEMAS = ("inv_transfer", "cal_move_headcount")
P3_SCHEMAS = ("ticket_gate_close", "cal_finalize")
P4_SCHEMAS = ("crm_purge_lead", "ticket_purge_spam")
PROJ = {**{k: P1X for k in P1_SCHEMAS}, **{k: P2X for k in P2_SCHEMAS},
        **{k: P3X for k in P3_SCHEMAS}, **{k: P4X for k in P4_SCHEMAS}}

J_SPLIT = {"crm_escalate": [1, 1, 1, 2, 2], "inv_overstock": [1, 1, 2, 2, 2]}
# frozen (train, val, test) family quotas per (schema, join_depth) stratum.
GROUP_QUOTA = {("crm_escalate", 1): (10, 2, 3), ("crm_escalate", 2): (7, 2, 1),
               ("inv_overstock", 1): (8, 1, 1), ("inv_overstock", 2): (11, 2, 2),
               ("inv_transfer", 1): (19, 3, 3), ("cal_move_headcount", 1): (19, 3, 3),
               ("ticket_gate_close", 1): (19, 3, 3), ("cal_finalize", 1): (19, 3, 3),
               ("crm_purge_lead", 1): (19, 3, 3), ("ticket_purge_spam", 1): (19, 3, 3)}
DATADIR = HERE / "data"
KILL_TEXT_FRAC = 0.01          # >1% of planned texts affected -> full stop
METER = None


def meter():
    global METER
    if METER is None:
        cfg = G.load_config(str(PHI_D.parent.parent / "configs" / "pilot.yaml"))
        METER = G.TokenMeter(cfg["memories"]["tokenizer"])  # noqa: F841
    return METER


_CFG = None


def cfg():
    global _CFG
    if _CFG is None:
        _CFG = G.load_config(str(PHI_D.parent.parent / "configs" / "pilot.yaml"))
    return _CFG


def card_slots(fidx):
    """Per-family card quota: even idx A01 x4 + A00 x5; odd idx A01 x5 + A00 x4."""
    a01, a00 = (4, 5) if fidx % 2 == 0 else (5, 4)
    return ([("A11", s) for s in range(4)] + [("A10", s) for s in range(2)]
            + [("A01", s) for s in range(a01)] + [("A00", s) for s in range(a00)])


def plan_families():
    fams = []
    for i in range(N_FAM):
        smeta = G.SCHEMA_LIST[i % len(G.SCHEMA_LIST)]
        occ = i // len(G.SCHEMA_LIST)
        rngf = __import__("random").Random(G.sha_int("fam", GS_MINT, i))
        j = (J_SPLIT[smeta["key"]][occ % len(J_SPLIT[smeta["key"]])]
             if smeta["key"] in J_SPLIT else smeta["j_levels"][0])
        fams.append({"idx": i, "schema_key": smeta["key"], "domain": smeta["domain"],
                     "archetype": smeta["archetype"],
                     "params": smeta["sample"](rngf, j), "occ": occ})
    return fams


def group_split(fams):
    groups = {}
    strata = collections.defaultdict(list)
    for f in fams:
        strata[(f["schema_key"], f["params"].get("join_depth", 1))].append(f)
    for sk, fl in sorted(strata.items()):
        ranked = sorted(fl, key=lambda f: hashlib.sha1(
            ("%d|group|%d" % (GS_MINT, f["idx"])).encode()).hexdigest())
        nt, nv, nte = GROUP_QUOTA[sk]
        assert len(ranked) == nt + nv + nte, "stratum %s size %d != quota" % (
            sk, len(ranked))
        for f, g in zip(ranked, ["train"] * nt + ["val"] * nv + ["test"] * nte):
            groups[f["idx"]] = g
    return groups


def build_inst(fam, sib, nm):
    smeta = G.SCHEMAS[fam["schema_key"]]
    style = (fam["idx"] % 3) if nm else ((fam["idx"] + sib) % 3)
    inst = smeta["build"](fam, 90 if nm else sib, 0, nm, GS_MINT, cfg()["generation"], style)
    inst["_arch_date"] = fam["params"].get("arch_date")
    return inst


def build_nm_variant(fam, v):
    """A01 dedupe variant: render the family's near-miss program with the
    SIBLING-ENTITY DRAW 90+v (deterministic; same family params, same crossed
    style as the canonical nm, same flipped program). Needed because a family's
    nm roles are otherwise a single core: on schemas whose NM core only fits
    the [200,300] token window in 2 of 6 card styles, 5 A01 slots cannot be
    deduplicated by style rotation alone (measured: cal_move_headcount NM core
    307-329 tokens in styles 1/2/4/5). Mirrors the pilot's (s+v)%4 variant
    rule, applied to the nm stream; relation semantics unchanged."""
    smeta = G.SCHEMAS[fam["schema_key"]]
    inst = smeta["build"](fam, 90 + v, 0, True, GS_MINT, cfg()["generation"],
                          fam["idx"] % 3)
    inst["_arch_date"] = fam["params"].get("arch_date")
    return inst


def partners(fams, insts):
    """Generator's own A10/A00 pairing algorithms over the 200-family plan."""
    sig = {f["idx"]: insts[f["idx"]][("sibling", 0)]["signature"] for f in fams}
    by_class = collections.defaultdict(list)
    for k, v in sig.items():
        by_class[v].append(k)
    a10, a00 = {}, {}
    for f in fams:
        cands = sorted(x for x in by_class[sig[f["idx"]]] if fams[x]["domain"] != f["domain"])
        assert cands, "no cross-domain partner for family %d" % f["idx"]
        a10[f["idx"]] = cands[f["occ"] % len(cands)]
        cands00 = sorted(x for x in range(len(fams))
                         if sig[x] != sig[f["idx"]] and fams[x]["domain"] != f["domain"])
        assert cands00, "no unrelated partner for family %d" % f["idx"]
        a00[f["idx"]] = cands00[(f["idx"] * 7 + 3) % len(cands00)]
    return a10, a00, sig


def decon_corpus():
    decon = set()
    for r in M.load_sealed()[0]:
        decon.add(hashlib.sha256(r["instruction"].encode()).hexdigest())
    for mrow in M.load_sealed()[1].values():
        decon.add(hashlib.sha256(mrow["text"].encode()).hexdigest())
    for r in load_pairs():
        decon.add(hashlib.sha256(r["instruction"].encode()).hexdigest())
        decon.add(hashlib.sha256(r["memory_text"].encode()).hexdigest())
    return decon


# ---------------------------------------------------------------------------
# per-item checks
# ---------------------------------------------------------------------------
def clause_extraction_artifact(text, pair):
    """Audit `condition_clause` misfires when a reporter/entity NAME in the
    text contains a case-sensitive cue substring ("Elif Nieminen" contains
    lowercase "if "): the extracted window is then a name fragment, not the
    rendered condition. Detect: the window contains none of this archetype's
    condition-anchor tokens while the minted condition rule is located in the
    text. Frozen measurement-side artifact; gold polarity follows the mint's
    frozen cond-scope negation rule (semantics unchanged)."""
    clause = C.A.condition_clause(text).lower()
    anchors = {"aggregate_gate": ("subtask", "attendee"),
               "conditional_write": ("complaint count", "quantity"),
               "two_row_transfer": ("guard", "keep at least"),
               "delete_after_capture": ("status", "tagged")}
    return not any(a in clause for a in anchors[pair["archetype"]])


def item_checks(pid, pair, inst, kind, checks, decon, minted_texts, gap_ledger):
    def ok(name, cond, detail=""):
        checks.append({"pair": pid, "check": name, "ok": bool(cond), "detail": detail})
        C._assert(cond, "self-consistency failure %s/%s: %s" % (pid, name, detail))

    ir = pair["gold_ir"]
    ok("validate_ir", validate_ir(ir)[0])
    pp = inst["program_params"]
    prog = ARCHETYPES[pair["archetype"]](pp)
    j2_card = (kind == "memory" and pair["archetype"] == "conditional_write"
               and pp.get("join_depth") == 2)
    ok("op_seq", C.present_ops(ir) ==
       C.expected_ops(prog["signature"], kind, j2_policy_read=j2_card),
       "%s vs %s" % (C.present_ops(ir), prog["signature"]))
    branch = next(n for n in ir["nodes"] if n["op"] == "branch")
    pred = branch["args"]["predicate"]
    if pair["archetype"] == "conditional_write":
        ok("pred_op==program", pred["op"]["value"] == pp["cond_op"])
        ok("policy_row<=>J2", (ir["roles"]["policy_row"]["status"] == "present")
           == (pp.get("join_depth") == 2))
    elif pair["archetype"] == "two_row_transfer":
        ok("pred_op==program", pred["op"]["value"] in (">=", "<=")
           and pred["op"]["value"] == ">=", pred["op"]["value"])
        ok("roles_source_dest", ir["roles"]["source"]["status"] == "present"
           and ir["roles"]["destination"]["status"] == "present")
    elif pair["archetype"] == "aggregate_gate":
        ok("pred_op==program", pred["op"]["value"] == pp["check"]["op"],
           "%s vs %s" % (pred["op"]["value"], pp["check"]["op"]))
        ok("roles_p3", all(ir["roles"][r]["status"] == "present"
                           for r in ("subject_row", "child_set", "audit_sink")))
    else:  # delete_after_capture
        skip = pp.get("skip_archive", False)
        ok("pred_op==program", pred["op"]["value"] == pp["check"]["op"])
        ok("audit_sink_state",
           (ir["roles"]["audit_sink"]["status"] == "absent") == bool(skip)
           and (skip or ir["roles"]["audit_sink"]["status"] == "present"))
        arch_nodes = [n for n in ir["nodes"] if n["args"].get("action") == "archive"]
        ok("archive_node_state", len(arch_nodes) == 1 and
           (arch_nodes[0]["status"] == "absent") == bool(skip))
        if not skip:
            pos = {n["id"]: i for i, n in enumerate(ir["nodes"])}
            dels = [n for n in ir["nodes"]
                    if n["args"].get("action") == "delete" and n["status"] == "present"]
            ok("archive_before_delete",
               all(pos[arch_nodes[0]["id"]] < pos[d["id"]] for d in dels))
    ok("decontaminated", hashlib.sha256(pair["text"].encode()).hexdigest() not in decon)
    C._assert(pair["text"] not in minted_texts, "duplicate text %s" % pid)

    # audit gold self-check: every non-True verdict must be a whitelisted gap.
    rec, soft = C.audit_selfcheck(pair["text"], ir, pp, pair["archetype"])
    remaining = []
    for f, v, mode, detail in soft:
        if C.gap_is_whitelisted(pair["schema_key"], kind,
                                pair["program"] == "near_miss", f, (v, mode, detail)):
            gap_ledger.setdefault("whitelisted", {}).setdefault(
                "%s|%s" % (pair["schema_key"], f), 0)
            gap_ledger["whitelisted"]["%s|%s" % (pair["schema_key"], f)] += 1
            continue
        if (f == "pred_polarity" and v is False
                and clause_extraction_artifact(pair["text"], pair)):
            gap_ledger["whitelisted"][pair["schema_key"] + "|clause_artifact"] = \
                gap_ledger["whitelisted"].get(pair["schema_key"] + "|clause_artifact", 0) + 1
            continue
        if (f == "pred_all" and v is False
                and clause_extraction_artifact(pair["text"], pair)):
            continue      # aggregate of the whitelisted clause artifact above
        remaining.append((f, v, mode, str(detail)[:120]))
    ok("audit_selfcheck_whitelisted", not remaining, repr(remaining)[:240])
    return rec, soft


# ---------------------------------------------------------------------------
# mint loop
# ---------------------------------------------------------------------------
def numeric_substitute(roles, schema_key, inst):
    """Apply the numeric-printing card lever to an (already entity-instantiated)
    roles dict; returns (roles, applied_flag). Every `from` phrase must occur
    in the roles — a silent no-op substitution would flip the lever's intent
    without the label probe noticing, so absence is a hard mint error."""
    if schema_key not in C.NUMERIC_SCHEMAS:
        return roles, False
    meta = inst["meta"]
    if schema_key in P1_SCHEMAS:
        vocab = M.p1_vocab(schema_key)
        j2 = inst["program_params"]["join_depth"] == 2
        sym = vocab["j2_theta_card"] if j2 else vocab["j1_theta_card"]
        num = P1X.NUMERIC_THETA_PHRASE[(schema_key, inst["program_params"]["join_depth"])] \
            % inst["program_params"]["theta"]
        pairs = [(sym, num)]
    else:  # P2
        mn, cp = (meta["min_keep"], meta["cap"]) if schema_key == "inv_transfer" \
            else (meta["min_keep"], meta["cap_dst"])
        pairs = [(P2X.MIN_TEXT[schema_key], str(mn)), (P2X.CAP_TEXT[schema_key], str(cp))]

    whole = json.dumps(roles, sort_keys=True)
    for a, _b in pairs:
        C._assert(a in whole, "numeric lever 'from' phrase missing in roles: %r (%s)"
                  % (a, schema_key))

    def rw(x):
        if isinstance(x, str):
            for a, b in pairs:
                x = x.replace(a, b)
            return x
        if isinstance(x, list):
            return [rw(v) for v in x]
        if isinstance(x, dict):
            return {k: rw(v) for k, v in x.items()}
        return x

    return rw(roles), True


def _ensure_family(fam, insts):
    """Lazily build all siblings + near-miss for a family (dev-mode partners)."""
    if fam["idx"] not in insts or ("sibling", 3) not in insts[fam["idx"]]:
        d = insts.setdefault(fam["idx"], {})
        for s in range(N_SIB):
            d.setdefault(("sibling", s), build_inst(fam, s, False))
        d.setdefault(("near_miss", 0), build_inst(fam, 0, True))
    return insts[fam["idx"]]


def render_card_attempt(roles, style_idx, fi, s, cell, v, rot, force):
    """One dedupe attempt render. Frozen seed rule (production): every attempt
    draws its padding stream from sha_int("cardx", GS_MINT, fi, s, cell, v, rot,
    force) so rotation/variant attempts get FRESH fillers — the pilot rule
    hashed only (card, gs, fi, s, cell), which makes every retry of one slot
    byte-identical whenever the unpadded core is >= the token target (measured:
    P2/P3 card cores are 240-330 tokens, so collided cores cannot be
    re-deduplicated by padding). `force` additionally appends up to `force`
    filler lines (fresh stream) when the pad result is already >= target, as
    long as the [min,max] token window holds. Evidence discipline untouched:
    filler lines are appended after the core behind the "\nNote: " cut the
    projections enforce."""
    import random as _rnd
    base = G.CARD_STYLES[style_idx](roles)
    mcfg = cfg()["memories"]
    rngc = _rnd.Random(G.sha_int("cardx", GS_MINT, fi, s, cell, v, rot, force))
    text, ntok = G.pad_to_tokens(base, meter(), rngc, mcfg["tokens_target"],
                                 mcfg["tokens_min"], mcfg["tokens_max"])
    if force:
        fillers = G.FILLERS[:]
        rngf = _rnd.Random(G.sha_int("cardz", GS_MINT, fi, s, cell, v, rot, force))
        rngf.shuffle(fillers)
        added = 0
        for fl in fillers:
            if added >= force:
                break
            cand = text + "\nNote: " + fl
            n = meter().count(cand)
            if n > mcfg["tokens_max"]:
                continue
            text, ntok, added = cand, n, added + 1
        if not added:
            raise RuntimeError("forced fillers exceed token window")
    return text, ntok


def mint_family(fam, insts, a10, a00, decon, minted_texts, checks, ledger):
    fidx, sk = fam["idx"], fam["schema_key"]
    mod = PROJ[sk]
    pairs, failures, gap_ledger = [], [], {"whitelisted": {}}
    for sib in list(range(N_SIB)) + ["nm"]:
        nm = sib == "nm"
        inst = _ensure_family(fam, insts)[("near_miss", 0)] if nm \
            else _ensure_family(fam, insts)[("sibling", sib)]
        style = (fidx % 3) if nm else ((fidx + sib) % 3)
        pid = "instr:f%d:%s" % (fidx, "nm" if nm else "s%d" % sib)
        try:
            ir, ev, proj = mod.project_instruction(sk, inst, style)
        except C.MintError as e:
            failures.append({"slot": pid, "stage": "project", "error": str(e)})
            checks.append({"pair": pid, "check": "minted", "ok": False,
                           "detail": str(e)[:200]})
            continue
        pair = {"pair_id": pid, "kind": "instruction", "family_idx": fidx,
                "schema_key": sk, "domain": fam["domain"], "archetype": fam["archetype"],
                "join_depth": inst["program_params"].get("join_depth", 1),
                "cell": None, "target_sibling": None if nm else sib,
                "style": style, "style_name": "instruction_style%d" % style,
                "program": "near_miss" if nm else "same",
                "signature": inst["signature"],
                "cond_op": inst["program_params"].get("cond_op"),
                "value_symbolic": proj["value_symbolic"], "value_mode": proj["value_mode"],
                "text": inst["instruction"], "gold_ir": ir, "evidence_map": ev}
        try:
            item_checks(pid, pair, inst, "instruction", checks, decon, minted_texts,
                        gap_ledger)
        except C.MintError as e:
            failures.append({"slot": pid, "stage": "checks", "error": str(e)})
            continue
        minted_texts.add(pair["text"])
        pairs.append(pair)

    for cell, s in card_slots(fidx):
        pid = "mem:f%d:s%d:%s" % (fidx, s, cell)
        if cell == "A11":
            src_fidx, rel, nm_src = fidx, "same", False
        elif cell == "A01":
            src_fidx, rel, nm_src = fidx, "near_miss", True
        elif cell == "A10":
            src_fidx, rel, nm_src = a10[fidx], "same", False
        else:
            src_fidx, rel, nm_src = a00[fidx], "unrelated", False
        src_fam = FAMS[src_fidx]
        src_schema = src_fam["schema_key"]
        src_mod = PROJ[src_schema]
        src_insts = _ensure_family(src_fam, insts)
        base_style = (fidx * N_SIB + s + G.CELL_RANK[cell]) % len(G.CARD_STYLES)
        n_var = N_SIB
        numeric_coin = C.numeric_card_coin(GS_MINT, fidx, s, cell) \
            and src_schema in C.NUMERIC_SCHEMAS
        chosen = None
        for v in range(n_var):
            if chosen:
                break
            src = (build_nm_variant(src_fam, v) if nm_src
                   else src_insts[("sibling", (s + v) % N_SIB)])
            roles = C.instantiate_roles(src["roles"], src_schema, src)
            if numeric_coin:
                roles, applied = numeric_substitute(roles, src_schema, src)
                C._assert(applied, "numeric lever refused for %s" % src_schema)
            for rot in range(len(G.CARD_STYLES)):
                if chosen:
                    break
                style_idx = (base_style + rot) % len(G.CARD_STYLES)
                for force in (0, 1, 2):
                    try:
                        text, ntok = render_card_attempt(roles, style_idx, fidx, s, cell,
                                                         v, rot, force)
                    except RuntimeError:
                        if force == 0:
                            break        # core too long in this style: rotate
                        continue         # forced fillers overflow the window: try more
                    th = hashlib.sha256(text.encode()).hexdigest()
                    if th not in decon and text not in minted_texts:
                        chosen = (src, roles, style_idx, text, ntok, v, rot, force)
                        break
        if not chosen:
            failures.append({"slot": pid, "stage": "dedupe",
                           "error": "dedupe-by-rotation exhausted (pad-seed+filler retries)"})
            checks.append({"pair": pid, "check": "minted", "ok": False,
                           "detail": "exhausted"})
            continue
        src, roles, style_idx, text, ntok, variant_v, style_rot, filler_force = chosen
        ledger["dedupe_attempts"][(variant_v, style_rot, filler_force)] = \
            ledger["dedupe_attempts"].get((variant_v, style_rot, filler_force), 0) + 1
        src_inst = dict(src); src_inst["_card_text"] = text; src_inst["roles"] = roles
        try:
            ir, ev, proj = src_mod.project_memory(src_schema, src_inst)
            pair = {"pair_id": pid, "kind": "memory", "family_idx": fidx,
                    "schema_key": src_schema, "domain": src_fam["domain"],
                    "archetype": src_fam["archetype"],
                    "join_depth": src["program_params"].get("join_depth", 1),
                    "cell": cell, "target_sibling": s,
                    "style": style_idx, "style_name": G.STYLE_NAMES[style_idx],
                    "dedupe_variant": variant_v, "dedupe_rotation": style_rot,
                    "dedupe_filler_force": filler_force,
                    "numeric_card_variant": bool(numeric_coin),
                    "memory_token_count": ntok,
                    "program": rel, "signature": src["signature"],
                    "cond_op": src["program_params"].get("cond_op"),
                    "value_symbolic": proj["value_symbolic"],
                    "value_mode": proj["value_mode"],
                    "text": text, "gold_ir": ir, "evidence_map": ev}
            item_checks(pid, pair, src, "memory", checks, decon, minted_texts,
                        gap_ledger)
        except C.MintError as e:
            failures.append({"slot": pid, "stage": "project", "error": str(e)})
            checks.append({"pair": pid, "check": "minted", "ok": False,
                           "detail": str(e)[:200]})
            continue
        minted_texts.add(text)
        pairs.append(pair)
    return pairs, failures, gap_ledger


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--schemas", default=None,
                    help="comma list for dev mini-batches (default: all 8)")
    ap.add_argument("--max-fam", type=int, default=None,
                    help="first N families per schema (default: all 25)")
    ap.add_argument("--dev-report", default=None)
    args = ap.parse_args()
    global FAMS
    FAMS = plan_families()
    only = set(args.schemas.split(",")) if args.schemas else None
    dev = only is not None or args.max_fam is not None
    groups = group_split(FAMS)

    # build instances for all families (instructions + partner lookup)
    insts = {}
    for fam in FAMS:
        if only and fam["schema_key"] not in only:
            continue
        if args.max_fam is not None and fam["occ"] >= args.max_fam:
            continue
        d = {}
        for s in range(N_SIB):
            d[("sibling", s)] = build_inst(fam, s, False)
        d[("near_miss", 0)] = build_inst(fam, 0, True)
        insts[fam["idx"]] = d
    # partners need signatures for the full plan
    a10, a00, sig = partners(FAMS, _full_sig_insts(FAMS, insts) if dev else insts)

    print("[mint] tokenizer load ...")
    meter()
    decon = decon_corpus()
    print("[mint] decontamination reference: %d hashes" % len(decon))

    checks = []
    ledger = {"failed_families": {}, "dedupe_rotations": 0, "dedupe_variants": 0,
              "dedupe_attempts": {}, "whitelisted": {}}
    minted_texts = set()
    all_pairs = []
    mint_targets = sorted(insts.keys())          # frozen BEFORE lazy partner fills
    for fam in FAMS:
        if fam["idx"] not in mint_targets:
            continue
        pairs, failures, gap_ledger = mint_family(fam, insts, a10, a00, decon,
                                                  minted_texts, checks, ledger)
        all_pairs.extend(pairs)
        if failures:
            ledger["failed_families"][fam["idx"]] = failures
        for k, v in gap_ledger["whitelisted"].items():
            ledger["whitelisted"][k] = ledger["whitelisted"].get(k, 0) + v
        ledger["dedupe_rotations"] += sum(p.get("dedupe_rotation", 0) for p in pairs)
        ledger["dedupe_variants"] += sum(p.get("dedupe_variant", 0) for p in pairs)
        if fam["idx"] % 25 == 24 or failures:
            print("[mint] family %d (%s) done: %d texts, %d failures"
                  % (fam["idx"], fam["schema_key"], len(pairs), len(failures)))
    if dev:
        finish_dev(FAMS, all_pairs, checks, ledger, args)
        return
    finish_full(FAMS, groups, sig, a10, a00, all_pairs, checks, ledger, decon)


def _full_sig_insts(fams, have):
    """For dev mode: sibling-0 instances for every family (partner signatures)."""
    out = {}
    for fam in fams:
        if fam["idx"] in have:
            out[fam["idx"]] = have[fam["idx"]]
        else:
            out[fam["idx"]] = {("sibling", 0): build_inst(fam, 0, False)}
    return out


def finish_dev(fams, pairs, checks, ledger, args):
    n_fail = [c for c in checks if not c["ok"]]
    rep = {"gs_mint": GS_MINT, "mode": "dev",
           "families": [f["idx"] for f in fams
                        if (not args.schemas or f["schema_key"] in args.schemas.split(","))
                        and (args.max_fam is None or f["occ"] < args.max_fam)],
           "n_pairs": len(pairs),
           "by_schema": {sk: sum(1 for p in pairs if p["schema_key"] == sk)
                         for sk in sorted({p["schema_key"] for p in pairs})},
           "checks_total": len(checks), "checks_failed": n_fail,
           "checks_pass_rate": (len(checks) - len(n_fail)) / float(len(checks) or 1),
           "value_policy": collections.Counter(
               (p["schema_key"], p["kind"], p["value_mode"]) for p in pairs),
           "failed_families": ledger["failed_families"]}
    rep["value_policy"] = {"%s|%s|%s" % k: v for k, v in
                           sorted(rep["value_policy"].items())}
    out = pathlib.Path(args.dev_report or (HERE / "dev_report.json"))
    with open(out, "w") as f:
        json.dump(rep, f, indent=1, sort_keys=True)
    print("[mint:dev] pairs=%d checks=%d/%d pass (%.4f) -> %s"
          % (len(pairs), len(checks) - len(n_fail), len(checks),
             rep["checks_pass_rate"], out))
    for c in n_fail[:5]:
        print("  FAIL %s %s %s" % (c["pair"], c["check"], c["detail"][:150]))


def finish_full(fams, groups, sig, a10, a00, pairs, checks, ledger, decon):
    planned = len(fams) * 20
    failed_texts = sum(len(v) for v in ledger["failed_families"].values())
    C._assert(len(pairs) == planned - failed_texts,
              "pair accounting mismatch: %d + %d != %d"
              % (len(pairs), failed_texts, planned))
    if failed_texts > KILL_TEXT_FRAC * planned:
        json.dump({"kill": "failed text fraction", "failed_texts": failed_texts,
                   "failed_families": ledger["failed_families"]},
                  open(HERE / "kill_report.json", "w"), indent=1)
        raise SystemExit("[mint] KILL: %d/%d texts failed (>1%%); see kill_report.json"
                         % (failed_texts, planned))

    # global span re-verification (independent pass) --------------------
    for p in pairs:
        for e in p["evidence_map"]:
            cond = (p["text"][e["start"]:e["end"]] == e["span"]
                    and len(e["span"].split()) <= C.MAXW
                    and e["start"] < C.card_core_end(p["text"]))
            checks.append({"pair": p["pair_id"], "check": "span_reslice", "ok": cond,
                           "detail": e["field"]})
            C._assert(cond, "span reslice mismatch %s %s" % (p["pair_id"], e["field"]))
    texts = [p["text"] for p in pairs]
    C._assert(len(set(texts)) == len(texts), "duplicate texts survive: %d unique/%d"
              % (len(set(texts)), len(texts)))

    # views -------------------------------------------------------------
    for p in pairs:
        p["group"] = groups[p["family_idx"]]
        p["pair_order_key"] = hashlib.sha1(
            ("%d|curve|%s" % (GS_MINT, p["pair_id"])).encode()).hexdigest()
    views = {"train": sorted((p for p in pairs if p["group"] == "train"),
                             key=lambda p: p["pair_order_key"]),
             "val": sorted((p for p in pairs if p["group"] == "val"),
                           key=lambda p: p["pair_order_key"]),
             "test": sorted((p for p in pairs if p["group"] == "test"),
                            key=lambda p: p["pair_order_key"])}
    # nested learning-curve subsets + per-archetype share gate (documented
    # re-draw rule). If a level violates the +-5pp band, deterministically swap
    # the LAST over-represented pair inside the offending level window with the
    # FIRST under-represented pair after the level boundary; repaired level
    # windows are frozen for later repairs, so LC300 < LC1000 < LC3000 remain
    # exact prefixes. Level 3000 == the whole train set and cannot violate.
    # Every swap is logged in the receipt.
    train = views["train"]
    global_mix = {a: sum(1 for p in train if p["archetype"] == a) / float(len(train))
                  for a in sorted({p["archetype"] for p in train})}
    lc_swaps = []

    def lc_bad(prefix, n):
        if not n:
            return {}
        sh = {a: sum(1 for p in prefix if p["archetype"] == a) / float(n)
              for a in global_mix}
        return {a: (sh[a] - g) for a, g in global_mix.items() if abs(sh[a] - g) > 0.05}

    lo = 0
    for n in (300, 1000, 3000):
        guard = 0
        while n < len(train):
            bad = lc_bad(train[:n], n)
            if not bad:
                break
            guard += 1
            C._assert(guard <= len(train), "LC repair did not converge at level %d" % n)
            over = max((a for a in bad if bad[a] > 0), key=lambda a: bad[a])
            under = min((a for a in bad if bad[a] < 0), key=lambda a: bad[a])
            i = next(k for k in range(n - 1, lo - 1, -1) if train[k]["archetype"] == over)
            j = next(k for k in range(n, len(train)) if train[k]["archetype"] == under)
            lc_swaps.append({"level": n, "from_pos": i, "to_pos": j,
                             "pair_id": train[i]["pair_id"], "swap_with": train[j]["pair_id"],
                             "over": over, "under": under})
            train.insert(j, train.pop(i))
        C._assert(not lc_bad(train[:n], n), "LC%d still violates after repair" % n)
        lo = n

    levels = {}
    arch_check = []
    for n in (300, 1000, 3000):
        levels[n] = train[:n]
        for a, g in global_mix.items():
            share = sum(1 for p in levels[n] if p["archetype"] == a) / float(len(levels[n]))
            arch_check.append({"level": n, "archetype": a, "share": round(share, 4),
                               "global": round(g, 4), "dev_pp": round(100 * (share - g), 2)})

    DATADIR.mkdir(exist_ok=True)
    digests = {}

    def write(path, rows):
        with open(path, "w") as f:
            for r in rows:
                f.write(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n")
        digests[pathlib.Path(path).stem] = hashlib.sha256(open(path, "rb").read()).hexdigest()

    write(HERE / "minted_all.jsonl",
          sorted(pairs, key=lambda p: (p["family_idx"], p["pair_id"])))
    for g, rows in views.items():
        write(DATADIR / ("%s.jsonl" % g), rows)
    for n, rows in levels.items():
        write(DATADIR / ("train_lc%d.jsonl" % n), rows)

    def mix3(rows):
        out = {"same": 0, "near_miss": 0, "unrelated": 0}
        for p in rows:
            out["near_miss" if p["program"] == "near_miss" else p["program"]] += 1
        return out

    def mix3_cards(rows):
        cards = [p for p in rows if p["kind"] == "memory"]
        return mix3(cards)

    receipt = {
        "gs_mint": GS_MINT, "sealed_seed_held_out": SEALED_SEED,
        "pilot_seed_disjoint": 20260811,
        "n_families": len(fams), "n_families_per_schema": 25,
        "family_plan": [{"idx": f["idx"], "schema_key": f["schema_key"],
                         "join_depth": f["params"].get("join_depth", 1),
                         "group": groups[f["idx"]], "occ": f["occ"],
                         "a10_partner": a10[f["idx"]], "a00_partner": a00[f["idx"]],
                         "signature": sig[f["idx"]]} for f in fams],
        "group_rule": "rank by sha1(gs|group|idx) within (schema,join_depth) stratum; "
                      "frozen quotas %r" % (GROUP_QUOTA,),
        "per_family_quota": "4 sib instr + 1 nm instr + 4 A11 + 2 A10 + "
                            "A01 x4/x5 + A00 x5/x4 (family parity) = 20",
        "counts": {"planned": planned, "minted": len(pairs),
                   "failed_texts": failed_texts,
                   "train": len(views["train"]), "val": len(views["val"]),
                   "test": len(views["test"])},
        "mix_all_texts": {g: mix3(views[g]) for g in views},
        "mix_cards_only": {g: mix3_cards(views[g]) for g in views},
        "by_kind": {g: {"instruction": sum(1 for p in views[g] if p["kind"] == "instruction"),
                        "memory": sum(1 for p in views[g] if p["kind"] == "memory")}
                    for g in views},
        "by_schema": {g: dict(collections.Counter(p["schema_key"] for p in views[g]))
                      for g in views},
        "by_archetype": {g: dict(collections.Counter(p["archetype"] for p in views[g]))
                         for g in views},
        "value_policy_counts": {
            "symbolic": sum(1 for p in pairs if p["value_symbolic"]),
            "numeric": sum(1 for p in pairs if not p["value_symbolic"] and p["value_mode"] == "numeric"),
            "string": sum(1 for p in pairs if p["value_mode"] == "string"),
            "numeric_cards_lever": sum(1 for p in pairs
                                       if p.get("numeric_card_variant") and not p["value_symbolic"]),
            "numeric_cards_lever_slots": sum(1 for p in pairs if p.get("numeric_card_variant"))},
        "numeric_share_p1p2_cards": {
            sk: (lambda rows: {"numeric": sum(1 for p in rows if not p["value_symbolic"]),
                               "symbolic": sum(1 for p in rows if p["value_symbolic"]),
                               "share": round(sum(1 for p in rows if not p["value_symbolic"])
                                              / float(len(rows) or 1), 4)})(
                [p for p in pairs if p["kind"] == "memory" and p["schema_key"] == sk])
            for sk in ("crm_escalate", "inv_overstock", "inv_transfer", "cal_move_headcount")},
        "lc_subsets": {"levels": {"lc300": 300, "lc1000": 1000, "lc3000": 3000},
                       "order_rule": "sha1(gs|'curve'|pair_id) over train texts; nested",
                       "redraw_swaps": lc_swaps,
                       "archetype_share_check_pp": arch_check},
        "dedupe_by_rotation": {
            "slots_with_rotation_gt0": sum(1 for p in pairs if p.get("dedupe_rotation")),
            "slots_with_variant_gt0": sum(1 for p in pairs if p.get("dedupe_variant")),
            "slots_with_filler_force_gt0": sum(
                1 for p in pairs if p.get("dedupe_filler_force")),
            "attempt_histogram": {"v%d_r%d_f%d" % k: v
                                  for k, v in sorted(ledger["dedupe_attempts"].items())},
            "whitelisted_gap_counts": ledger["whitelisted"],
            "failed_families": ledger["failed_families"]},
        "checks_total": len(checks),
        "checks_failed": [c for c in checks if not c["ok"]][:50],
        "checks_pass_rate": sum(c["ok"] for c in checks) / float(len(checks)),
        "decontamination": {"corpus": "tasks_sealed.instruction + memories_sealed.text + "
                                      "pairs.jsonl unique texts",
                            "n_reference_hashes": len(decon),
                            "collisions": sum(1 for p in pairs
                                              if hashlib.sha256(p["text"].encode()).hexdigest()
                                              in decon)},
        "hashes": digests,
        "code_sha256": {fn: hashlib.sha256(open(HERE / fn, "rb").read()).hexdigest()[:16]
                        for fn in ("mint_all.py", "mint_core.py", "mint_p1x.py",
                                   "mint_p2x.py", "mint_p3x.py", "mint_p4x.py")},
    }
    # per-schema x group stratum table
    strat = {}
    for g in views:
        strat[g] = dict(collections.Counter(
            "%s_J%d" % (p["schema_key"], p["join_depth"]) for p in views[g]))
    receipt["by_stratum"] = strat
    with open(HERE / "mint_receipt.json", "w") as f:
        json.dump(receipt, f, indent=1, sort_keys=True)
    ok_n = sum(c["ok"] for c in checks)
    print("[mint] DONE: %d/%d texts, %d/%d checks pass, decon collisions=%d"
          % (len(pairs), planned, ok_n, len(checks),
             receipt["decontamination"]["collisions"]))
    print("[mint] counts:", receipt["counts"])
    print("[mint] mix(all):", receipt["mix_all_texts"])
    print("[mint] mix(cards):", receipt["mix_cards_only"])
    print("[mint] numeric P1/P2 card shares:", receipt["numeric_share_p1p2_cards"])
    print("[mint] sha:", {k: v[:16] for k, v in digests.items()})


if __name__ == "__main__":
    FAMS = None
    main()
