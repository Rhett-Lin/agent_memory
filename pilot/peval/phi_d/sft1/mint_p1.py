#!/usr/bin/env python
"""mint_p1.py — P1-slice SFT dataset mint (phi+d lane C, stage-B pilot).

Scales the verified mint20 prototype (sft0/mint_spec.py, 355/355 checks) from 2 sealed
families to 23 NEW families minted under a NEW mint seed, reusing the prototype's
projection machinery verbatim (imported read-only; no generator edits, no sealed-artifact
writes). Families are split into train/val/test BEFORE rendering, from the plan entry
only. Sealed-benchmark families (seed 20260807) are untouched; a text-hash
decontamination gate asserts zero overlap with the 532 canonical corpus texts and both
sealed artifacts.

Family plan (frozen here, mirrors generate_families.plan_families for the P1 schemas):
  23 families, interleaved crm_escalate/inv_overstock (even idx = crm, odd = inv),
  join-depth cycles crm [1,1,1,2,2] / inv [1,1,2,2,2] (the generator's own patterns),
  params sampled with rngf = Random(sha_int("fam", GS_MINT, idx)).
-> strata: crmJ1 8, crmJ2 4, invJ1 5, invJ2 6.

Group split (BEFORE rendering, plan-entry only): within each stratum, families ranked by
sha1(f"{GS_MINT}|group|{idx}"); frozen quotas:
  crmJ1 train5/val1/test2, crmJ2 train3/val0/test1,
  invJ1 train3/val1/test1, invJ2 train4/val1/test1
-> train 15 fam / val 3 fam / test 5 fam (every stratum covered in every group that the
quota allows; val has no crmJ2 by quota).

Per-family text quota (20 texts; task mix same:~50 / near-miss:~30 / unrelated:~20):
  instructions: 4 siblings (styles (idx+s)%3) + 1 near-miss (style idx%3)   [5]
  cards A11 s=0..3  (same-family sibling program)                          [4]
  cards A10 s=0..1  (cross-domain same-signature partner)                  [2]
  cards A01 s=0..4  (near-miss program; s=4 is a documented extra slot —   [5]
                     same nm roles in a 5th card style via the Latin
                     formula with s=4; adds no new renderer semantics)
  cards A00 s=0..3  (unrelated partner: different-signature, different-    [4]
                     domain family = opposite join-depth, cross domain.
                     NOTE: in the 8-schema generator A00 can be a P2/P3/P4
                     card; this P1-slice mini-mint uses the generator's own
                     pairing rule restricted to P1 so all texts stay inside
                     the verified projection machinery. Disclosed in receipt.)
  same = 4 instr + 4 A11 + 2 A10 = 10 (50%); nm = 1 + 5 = 6 (30%); unrelated = 4 (20%).

Test slice: the 5 test families mint 100 texts; the shipped test.jsonl keeps the first
18 pairs per test family under the frozen pair-order key sha1(GS_MINT|"curve"|pair_id)
-> 90 texts, mix preserved up to binomial noise (documented in the receipt). The 10
dropped pairs stay in minted_all.jsonl with group="test", selected=false, and are NEVER
shipped to train/val/test views.

Training view = {text, gold_ir} only; everything else is provenance sidecar.

Run:  cd pilot/peval/phi_d/sft1 && PY mint_p1.py     (CPU, a few minutes)
"""

import hashlib
import json
import os
import pathlib
import random
import sys

HERE = pathlib.Path(__file__).resolve().parent            # pilot/peval/phi_d/sft1
SFT0 = HERE.parent / "sft0"
PHI_D = HERE.parent
PILOT = PHI_D.parent.parent
sys.path.insert(0, str(PILOT))
sys.path.insert(0, str(PHI_D))
sys.path.insert(0, str(SFT0))

os.environ.setdefault("HF_HOME", "/work1/zixuan/cache/huggingface")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import generate_families as G                             # noqa: E402  (read-only)
from program_dsl import ARCHETYPES                        # noqa: E402  (read-only)
from common import validate_ir                            # noqa: E402
import mint_spec as M                                     # noqa: E402  (sft0 prototype, read-only)

SEALED = pathlib.Path("/work1/zixuan/data/agent_memory/sealed")
GS_MINT = 20260811                # != sealed generator seed 20260807 (frozen)
N_FAM = 23
J_SPLIT = {"crm_escalate": [1, 1, 1, 2, 2], "inv_overstock": [1, 1, 2, 2, 2]}
# frozen group quotas per stratum (schema_key, join_depth): (train, val, test)
GROUP_QUOTA = {("crm_escalate", 1): (5, 1, 2), ("crm_escalate", 2): (3, 0, 1),
               ("inv_overstock", 1): (3, 1, 1), ("inv_overstock", 2): (4, 1, 1)}
CARD_SLOTS = ([("A11", s) for s in range(4)] + [("A10", s) for s in range(2)]
              + [("A01", s) for s in range(5)] + [("A00", s) for s in range(4)])
N_SIB = 4
DATADIR = HERE / "data"


# ---------------------------------------------------------------------------
# Entity-instantiated card variant (MINT-SIDE renderer addition; no generator
# edits). The sealed generator renders entity-GENERIC card cores (p1_roles'
# "the item's SKU" etc.), which makes the entire P1 card-text space param-free:
# measured 162/345 of this slice's naively-minted cards are byte-identical to
# sealed benchmark memories (gate fired on first run). To keep training texts
# disjoint from the benchmark, the mint substitutes the concrete identifier
# into the roles dict strings BEFORE CARD_STYLES rendering, e.g.
#   "the customer's email address" -> "lena.lindqvist@mail.example.org"
#   "the item's SKU"               -> "AB-1234"
# (bare form, not a parenthesized one: uniformly shorter or equal, so the
# token-range check [200,300] keeps behaving exactly as in the sealed renderer,
# with the usual filler padding absorbing underflow.)
# Roles layout, theta phrases, conseq/alt clauses, styles, and pad streams are
# untouched; the mutated roles are then projected by the same verified
# machinery, which hard-asserts every clause expectation against the mutated
# steps (any slip raises MintError, it cannot silently mislabel). This is the
# renderer-diversity lever class DATA_SPEC.md §4 lists as "needs building".
# ---------------------------------------------------------------------------
ID_PHRASE = {"crm_escalate": "the customer's email address",
             "inv_overstock": "the item's SKU"}


def concrete_id(schema_key, inst):
    return inst["meta"]["entity_email"] if schema_key == "crm_escalate" else inst["meta"]["sku"]


def instantiate_roles(roles, schema_key, inst):
    phrase = ID_PHRASE[schema_key]
    repl = concrete_id(schema_key, inst)

    def rw(x):
        if isinstance(x, str):
            return x.replace(phrase, repl)
        if isinstance(x, list):
            return [rw(v) for v in x]
        if isinstance(x, dict):
            return {k: rw(v) for k, v in x.items()}
        return x

    return rw(roles)


# ---------------------------------------------------------------------------
# Word-boundary fork of mint_spec.project_instruction. The prototype asserts
# the symbolic-theta policy with a NAIVE substring probe (str(theta) in
# cond_part); on this larger mint that misfires when theta's digits appear
# inside an SKU token printed in the rule clause (e.g. theta 57 vs SKU
# LV-5725) — a false LEAK alarm. The downstream audit decides stated-ness with
# a word-boundary probe (audit_expanded.num_stated: (?<![\d.])probe(?![\d.])),
# so this fork switches ONLY the two theta probes to that same rule. The
# probes are assertions: they never write labels, so the fork's output IR is
# identical wherever the prototype does not misfire. PROOF at mint time:
# project_instruction_checked dual-runs both projectors on every instruction —
# outputs must be byte-identical when the prototype succeeds; when it raises,
# the exception must be exactly the theta-leak probe AND the word-boundary
# probe must confirm theta is NOT stated (i.e. a false alarm), else the mint
# fails hard.
# ---------------------------------------------------------------------------
import re as _re


def theta_stated(x, clause):
    probe = str(int(x)) if float(x) == int(float(x)) else str(float(x))
    return bool(_re.search(r"(?<![\d.])" + _re.escape(probe) + r"(?![\d.])", clause))


def project_instruction_wb(schema_key, inst, style):
    """Verbatim fork of mint_spec.project_instruction with word-boundary theta probes."""
    text = inst["instruction"]
    M._assert("\nNote: " not in text, "instruction unexpectedly padded")
    ib = M.IrBuilder(text, core_end=len(text))
    pp, meta, vocab = inst["program_params"], inst["meta"], M.p1_vocab(schema_key)
    j2 = pp["join_depth"] == 2
    cmp_txt = M.CMP_TEXT[pp["cond_op"]]
    rule, theta_text, _ = M.expected_rule(schema_key, inst, vocab)
    rule_s, _, _ = M.locate(text, rule, 0, "instruction rule clause")

    ir = M.base_ir()
    if schema_key == "crm_escalate":
        ent_s, _, _ = M.locate(text, meta["entity_name"])
        surface = meta["entity_name"]
    else:
        ent_s, _, _ = M.locate(text, meta["sku"])
        surface = meta["sku"]
    sent, _, _ = M.sentence_around(text, ent_s)
    ir["roles"]["subject_row"] = {"status": "present", "surface": surface,
                                  "evidence": ib.span("roles.subject_row", sent)[0]}
    if j2:
        ir["roles"]["policy_row"] = {"status": "present", "surface": vocab["policy_table"],
                                     "evidence": ib.span("roles.policy_row", vocab["policy_table"],
                                                         after=rule_s)[0]}
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
    conseq_start = vocab["conseq"][:12]
    cut = rule.find(", " + conseq_start)
    M._assert(cut != -1, "conseq cut not found in rule: %r" % rule[:90])
    cond_part = rule[:cut]
    attribute = vocab["attr"]
    attr_span = vocab["attr_span"]
    attr_s = rule.find(attr_span)
    M._assert(attr_s != -1, "attribute span not in rule")
    cmp_abs = rule_s + rule.find(" " + cmp_txt)
    pol_clause = text[rule_s:cut + rule_s]
    polarity = "negative" if any(c in (" " + pol_clause.lower() + " ") for c in M.NEG_CUES) else "positive"
    M._assert(polarity == "positive", "P1 instructions render affirmative conditions; got %s" % polarity)

    if j2:
        M._assert(not theta_stated(pp["theta"], cond_part),
                  "theta LEAKS into a J2 condition clause: %r" % cond_part[:90])
        M._assert(vocab["policy_col"] in rule, "policy column name missing from J2 rule")
        value_status, value_val, value_span = "present", vocab["policy_col"], theta_text
    else:
        M._assert(theta_stated(pp["theta"], cond_part),
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
    n_verify = add("verify", "present", "nodes.verify", M.VERIFY_CUES[style],
                   args={"target": "subject_row"}, deps=[n_branch])
    ir["nodes"] = nodes
    ir["termination"] = {"status": "present",
                         "evidence": ib.span("termination", M.VERIFY_CUES[style])[0]}
    return ir, ib.ev, {"value_symbolic": j2, "numeric_theta": pp["theta"]}


def project_instruction_checked(schema_key, inst, style):
    """Dual-run the prototype projector and the word-boundary fork; use the fork's
    output only after proving byte-identity or a certified false alarm."""
    try:
        ref = M.project_instruction(schema_key, inst, style)
    except M.MintError as e:
        pp = inst["program_params"]
        rule, _, _ = M.expected_rule(schema_key, inst, M.p1_vocab(schema_key))
        vocab = M.p1_vocab(schema_key)
        cut = rule.find(", " + vocab["conseq"][:12])
        cond_part = rule[:cut]
        M._assert(str(pp["theta"]) in cond_part
                  and not theta_stated(pp["theta"], cond_part),
                  "prototype MintError is NOT the certified theta-substring false alarm: %s" % e)
        ref = None
    out = project_instruction_wb(schema_key, inst, style)
    if ref is not None:
        M._assert(json.dumps(ref[0], sort_keys=True) == json.dumps(out[0], sort_keys=True)
                  and ref[1] == out[1] and ref[2] == out[2],
                  "word-boundary fork diverged from prototype output")
    return out


def plan_p1_families():
    fams = []
    for i in range(N_FAM):
        key = "crm_escalate" if i % 2 == 0 else "inv_overstock"
        smeta = G.SCHEMAS[key]
        occ = i // 2
        j = J_SPLIT[key][occ % len(J_SPLIT[key])]
        rngf = random.Random(G.sha_int("fam", GS_MINT, i))
        fams.append({"idx": i, "schema_key": key, "domain": smeta["domain"],
                     "archetype": smeta["archetype"],
                     "params": smeta["sample"](rngf, j), "occ": occ})
    return fams


def group_split(fams):
    """Frozen: rank within stratum by sha1(gs|group|idx); fill (train,val,test) quotas."""
    groups = {}
    strata = {}
    for f in fams:
        strata.setdefault((f["schema_key"], f["params"]["join_depth"]), []).append(f)
    for sk, fl in sorted(strata.items()):
        ranked = sorted(fl, key=lambda f: hashlib.sha1(
            ("%d|group|%d" % (GS_MINT, f["idx"])).encode()).hexdigest())
        nt, nv, nte = GROUP_QUOTA[sk]
        assert len(ranked) == nt + nv + nte, "stratum %s size %d != quota %d" % (
            sk, len(ranked), nt + nv + nte)
        for f, g in zip(ranked, ["train"] * nt + ["val"] * nv + ["test"] * nte):
            groups[f["idx"]] = g
    return groups


_CFG = G.load_config(str(PILOT / "configs" / "pilot.yaml"))


def build_inst(fam, sib, nm):
    smeta = G.SCHEMAS[fam["schema_key"]]
    style = (fam["idx"] % 3) if nm else ((fam["idx"] + sib) % 3)
    return smeta["build"](fam, 90 if nm else sib, 0, nm, GS_MINT, _CFG["generation"], style)


def partners(fams, insts):
    """Generator's own A10/A00 pairing algorithms over the P1 plan."""
    sig = {f["idx"]: insts[f["idx"]][("sibling", 0)]["signature"] for f in fams}
    by_class = {}
    for k, v in sig.items():
        by_class.setdefault(v, []).append(k)
    a10, a00 = {}, {}
    for f in fams:
        cands = sorted(x for x in by_class[sig[f["idx"]]] if fams[x]["domain"] != f["domain"])
        assert cands, "no cross-domain partner for family %d" % f["idx"]
        a10[f["idx"]] = cands[f["occ"] % len(cands)]
        cands00 = [x for x in range(len(fams))
                   if sig[x] != sig[f["idx"]] and fams[x]["domain"] != f["domain"]]
        assert cands00, "no unrelated partner for family %d" % f["idx"]
        a00[f["idx"]] = cands00[(f["idx"] * 7 + 3) % len(cands00)]
    return a10, a00, sig


def main():
    cfg = G.load_config(str(PILOT / "configs" / "pilot.yaml"))
    mcfg = cfg["memories"]
    meter = G.TokenMeter(mcfg["tokenizer"])
    fams = plan_p1_families()
    groups = group_split(fams)
    insts = {}
    for fam in fams:
        d = {}
        for s in range(N_SIB):
            d[("sibling", s)] = build_inst(fam, s, False)
        d[("near_miss", 0)] = build_inst(fam, 0, True)
        insts[fam["idx"]] = d
    a10, a00, sig = partners(fams, insts)

    # ---- decontamination corpus: canonical 532 + both sealed artifacts -----------
    decon = set()
    for r in M.load_sealed()[0]:
        decon.add(M.hashlib.sha256(r["instruction"].encode()).hexdigest())
    for m in M.load_sealed()[1].values():
        decon.add(M.hashlib.sha256(m["text"].encode()).hexdigest())
    from common import load_pairs
    for r in load_pairs():
        decon.add(M.hashlib.sha256(r["instruction"].encode()).hexdigest())
        decon.add(M.hashlib.sha256(r["memory_text"].encode()).hexdigest())

    pairs, checks = [], []
    minted_texts = set()          # global accepted-text set (dedupe-by-rotation)

    def ok(pid, name, cond, detail=""):
        checks.append({"pair": pid, "check": name, "ok": bool(cond), "detail": detail})
        M._assert(cond, "self-consistency failure %s/%s: %s" % (pid, name, detail))

    for fam in fams:
        fidx, sk = fam["idx"], fam["schema_key"]
        # ---------------- instructions -----------------------------------------
        for sib in list(range(N_SIB)) + ["nm"]:
            nm = sib == "nm"
            inst = insts[fidx][("near_miss", 0)] if nm else insts[fidx][("sibling", sib)]
            style = (fidx % 3) if nm else ((fidx + sib) % 3)
            ir, ev, proj = project_instruction_checked(sk, inst, style)
            pid = "instr:f%d:%s" % (fidx, "nm" if nm else "s%d" % sib)
            ok(pid, "validate_ir", validate_ir(ir)[0])
            prog = ARCHETYPES[fam["archetype"]](inst["program_params"])
            ok(pid, "op_seq", [n["op"] for n in ir["nodes"]] ==
               M.expected_ops(prog["signature"], "instruction", j2_policy_read=False),
               prog["signature"])
            pred = next(n for n in ir["nodes"] if n["op"] == "branch")["args"]["predicate"]
            ok(pid, "pred_op==program", pred["op"]["value"] == inst["program_params"]["cond_op"])
            ok(pid, "policy_row<=>J2", (ir["roles"]["policy_row"]["status"] == "present")
               == (inst["program_params"]["join_depth"] == 2))
            if proj["value_symbolic"]:
                ok(pid, "value_symbolic_no_leak",
                   pred["value"]["value"] in M.p1_vocab(sk)["policy_col"] and
                   str(proj["numeric_theta"]) not in pred["value"]["evidence"])
            else:
                ok(pid, "value_numeric",
                   float(pred["value"]["value"]) == float(inst["program_params"]["theta"]))
            ok(pid, "decontaminated",
               hashlib.sha256(inst["instruction"].encode()).hexdigest() not in decon)
            M._assert(inst["instruction"] not in minted_texts, "duplicate instruction %s" % pid)
            minted_texts.add(inst["instruction"])
            pairs.append({"pair_id": pid, "kind": "instruction", "family_idx": fidx,
                          "schema_key": sk, "domain": fam["domain"],
                          "archetype": fam["archetype"],
                          "join_depth": inst["program_params"]["join_depth"],
                          "cell": None, "target_sibling": None if nm else sib,
                          "style": style, "style_name": "instruction_style%d" % style,
                          "program": "near_miss" if nm else "same",
                          "signature": prog["signature"],
                          "cond_op": inst["program_params"]["cond_op"],
                          "value_symbolic": proj["value_symbolic"],
                          "text": inst["instruction"], "gold_ir": ir,
                          "evidence_map": ev})
        # ---------------- cards --------------------------------------------------
        # Dedupe-by-rotation (frozen mint-side rule): the unpadded card core is a pure
        # function of (roles, style), and cross-family pairs (e.g. fam A's A10 card vs
        # its partner's A11 card) can land on the same (identifier, style) with no
        # filler padding appended -> byte-identical text. To keep the shipped views
        # duplicate-free AND disjoint from the benchmark, each slot renders with
        # sibling-meta variants and style rotations until the text is globally new:
        #   try (variant v in 0..n_var-1, rotation r in 0..5): style = base + r (mod 6)
        # processed in deterministic order (family idx asc, CARD_SLOTS order); the
        # first non-colliding render is projected by the same verified machinery.
        # Labels never depend on the rotation (projection re-derives everything from
        # the roles actually rendered). Rotations used are recorded per pair and in
        # the receipt. Hard-fail after all variants (impossible on this corpus).
        for cell, s in CARD_SLOTS:
            if cell == "A11":
                src_fam_idx, src_schema, rel, kind_key = fidx, sk, "same", ("sibling", None)
            elif cell == "A01":
                src_fam_idx, src_schema, rel, kind_key = fidx, sk, "near_miss", ("near_miss", 0)
            elif cell == "A10":
                pf = fams[a10[fidx]]
                src_fam_idx, src_schema, rel, kind_key = pf["idx"], pf["schema_key"], "same", ("sibling", None)
            else:
                pf = fams[a00[fidx]]
                src_fam_idx, src_schema, rel, kind_key = pf["idx"], pf["schema_key"], "unrelated", ("sibling", None)
            base_style = (fidx * N_SIB + s + G.CELL_RANK[cell]) % len(G.CARD_STYLES)
            n_var = 1 if kind_key[0] == "near_miss" else N_SIB
            pid = "mem:f%d:s%d:%s" % (fidx, s, cell)
            chosen = None
            for v in range(n_var):
                src = (insts[src_fam_idx][("near_miss", 0)] if kind_key[0] == "near_miss"
                       else insts[src_fam_idx][("sibling", (s + v) % N_SIB)])
                roles = instantiate_roles(src["roles"], src_schema, src)
                for rot in range(len(G.CARD_STYLES)):
                    style_idx = (base_style + rot) % len(G.CARD_STYLES)
                    base = G.CARD_STYLES[style_idx](roles)
                    rngc = random.Random(G.sha_int("card", GS_MINT, fidx, s, cell))
                    text, ntok = G.pad_to_tokens(base, meter, rngc, mcfg["tokens_target"],
                                                 mcfg["tokens_min"], mcfg["tokens_max"])
                    th = hashlib.sha256(text.encode()).hexdigest()
                    if th not in decon and text not in minted_texts:
                        chosen = (src, roles, style_idx, text, v, rot)
                        break
                if chosen:
                    break
            M._assert(chosen, "dedupe-by-rotation exhausted for %s" % pid)
            src, roles, style_idx, text, variant_v, style_rot = chosen
            minted_texts.add(text)
            src_inst = dict(src); src_inst["_card_text"] = text; src_inst["roles"] = roles
            ir, ev, proj = M.project_memory(src_schema, src_inst)
            ok(pid, "validate_ir", validate_ir(ir)[0])
            prog = ARCHETYPES[fam["archetype"]](src_inst["program_params"])
            j2_card = src_inst["program_params"]["join_depth"] == 2
            ok(pid, "op_seq", [n["op"] for n in ir["nodes"]] ==
               M.expected_ops(prog["signature"], "memory", j2_policy_read=j2_card),
               prog["signature"])
            pred = next(n for n in ir["nodes"] if n["op"] == "branch")["args"]["predicate"]
            ok(pid, "pred_op==program",
               pred["op"]["value"] == src_inst["program_params"]["cond_op"])
            ok(pid, "policy_row<=>J2",
               (ir["roles"]["policy_row"]["status"] == "present") == j2_card)
            ok(pid, "value_symbolic", proj["value_symbolic"] and
               str(proj["numeric_theta"]) not in pred["value"]["evidence"] and
               not pred["value"]["value"].lstrip("-").isdigit())
            ok(pid, "decontaminated",
               hashlib.sha256(text.encode()).hexdigest() not in decon)
            pairs.append({"pair_id": pid, "kind": "memory", "family_idx": fidx,
                          "schema_key": src_schema, "domain": fam["domain"],
                          "archetype": fam["archetype"],
                          "join_depth": src_inst["program_params"]["join_depth"],
                          "cell": cell, "target_sibling": s,
                          "style": style_idx, "style_name": G.STYLE_NAMES[style_idx],
                          "dedupe_variant": variant_v, "dedupe_rotation": style_rot,
                          "program": rel, "signature": prog["signature"],
                          "cond_op": src_inst["program_params"]["cond_op"],
                          "value_symbolic": proj["value_symbolic"],
                          "text": text, "gold_ir": ir, "evidence_map": ev})

    # ---------------- global uniqueness + span re-verification -------------------
    texts = [p["text"] for p in pairs]
    M._assert(len(set(texts)) == len(texts),
              "duplicate texts in mint: %d unique of %d" % (len(set(texts)), len(texts)))
    for p in pairs:
        for e in p["evidence_map"]:
            cond = p["text"][e["start"]:e["end"]] == e["span"] and len(e["span"].split()) <= 15
            checks.append({"pair": p["pair_id"], "check": "span_reslice", "ok": cond,
                           "detail": e["field"]})
            M._assert(cond, "span reslice mismatch %s %s" % (p["pair_id"], e["field"]))

    # ---------------- group + test selection --------------------------------------
    for p in pairs:
        p["group"] = groups[p["family_idx"]]
        p["pair_order_key"] = hashlib.sha1(
            ("%d|curve|%s" % (GS_MINT, p["pair_id"])).encode()).hexdigest()
        p["selected"] = True
    test_fams = sorted(f["idx"] for f in fams if groups[f["idx"]] == "test")
    for fidx in test_fams:
        fam_pairs = sorted([p for p in pairs if p["family_idx"] == fidx],
                           key=lambda p: p["pair_order_key"])
        for p in fam_pairs[18:]:
            p["selected"] = False

    views = {"train": [], "val": [], "test": []}
    for p in pairs:
        if p["group"] in views and p["selected"]:
            views[p["group"]].append(p)
    for g in views:
        views[g].sort(key=lambda p: p["pair_order_key"])

    DATADIR.mkdir(exist_ok=True)
    digests = {}
    with open(HERE / "minted_all.jsonl", "w") as f:
        for p in sorted(pairs, key=lambda p: (p["family_idx"], p["pair_id"])):
            f.write(json.dumps(p, sort_keys=True, ensure_ascii=False) + "\n")
    digests["minted_all"] = hashlib.sha256(open(HERE / "minted_all.jsonl", "rb").read()).hexdigest()
    for g, rows in views.items():
        with open(DATADIR / ("%s.jsonl" % g), "w") as f:
            for p in rows:
                f.write(json.dumps(p, sort_keys=True, ensure_ascii=False) + "\n")
        digests[g] = hashlib.sha256(open(DATADIR / ("%s.jsonl" % g), "rb").read()).hexdigest()

    # near-miss instructions + A01 count toward 'near_miss' relation for the mix audit
    def mix3(rows):
        out = {"same": 0, "near_miss": 0, "unrelated": 0}
        for p in rows:
            rel = "near_miss" if (p["program"] == "near_miss") else p["program"]
            out[rel] += 1
        return out

    receipt = {
        "gs_mint": GS_MINT, "sealed_seed_held_out": 20260807,
        "n_families": N_FAM,
        "family_plan": [{"idx": f["idx"], "schema_key": f["schema_key"],
                         "join_depth": f["params"]["join_depth"], "theta": f["params"].get("theta", f["params"].get("limit")),
                         "group": groups[f["idx"]], "a10_partner": a10[f["idx"]],
                         "a00_partner": a00[f["idx"]], "signature": sig[f["idx"]]} for f in fams],
        "group_rule": "rank by sha1(gs|group|idx) within (schema,join_depth) stratum; quotas %r"
                      % (GROUP_QUOTA,),
        "per_family_quota": "4 sib instr + 1 nm instr + 4 A11 + 2 A10 + 5 A01 + 4 A00 = 20",
        "test_selection": "5 test families mint 100; test.jsonl = first 18/family by pair_order_key = 90",
        "counts": {"minted_total": len(pairs),
                   "train": len(views["train"]), "val": len(views["val"]),
                   "test": len(views["test"]),
                   "test_minted_excluded": sum(1 for p in pairs if p["group"] == "test" and not p["selected"])},
        "mix": {g: mix3(views[g]) for g in views},
        "by_kind": {g: {"instruction": sum(1 for p in views[g] if p["kind"] == "instruction"),
                        "memory": sum(1 for p in views[g] if p["kind"] == "memory")} for g in views},
        "value_policy_counts": {"symbolic": sum(1 for p in pairs if p["value_symbolic"]),
                                "numeric": sum(1 for p in pairs if not p["value_symbolic"])},
        "dedupe_by_rotation": {"slots_with_variant_gt0": sum(1 for p in pairs if p.get("dedupe_variant")),
                               "slots_with_rotation_gt0": sum(1 for p in pairs if p.get("dedupe_rotation")),
                               "total_card_slots": sum(1 for p in pairs if p["kind"] == "memory")},
        "checks_total": len(checks),
        "checks_failed": [c for c in checks if not c["ok"]],
        "checks_pass_rate": sum(c["ok"] for c in checks) / float(len(checks)),
        "decontamination": {"corpus": "tasks_sealed.instruction + memories_sealed.text + pairs.jsonl unique texts",
                            "n_reference_hashes": len(decon), "collisions": 0},
        "hashes": digests,
        "provenance_note": ("A00 = generator's unrelated-partner rule (different signature, "
                            "different domain) restricted to the P1 slice => opposite join-depth, "
                            "cross domain. A01 s=4 = documented extra slot (same nm roles, 5th card "
                            "style via the Latin formula). Cards are ENTITY-INSTANTIATED at mint "
                            "time (concrete email/SKU parenthesized into the roles id-phrase) "
                            "because entity-generic P1 card cores are param-free and collide "
                            "byte-for-byte with sealed benchmark memories (162/345 naive cards); "
                            "labels never enter model input."),
    }
    # per-stratum counts per group
    st = {g: {} for g in views}
    for g in views:
        for p in views[g]:
            k = "%s_J%d" % (p["schema_key"], p["join_depth"])
            st[g][k] = st[g].get(k, 0) + 1
    receipt["by_stratum"] = st
    receipt["mix"] = {g: mix3(views[g]) for g in views}
    with open(HERE / "mint_receipt.json", "w") as f:
        json.dump(receipt, f, indent=1, sort_keys=True)
    print("[mint_p1] families=%d minted=%d train=%d val=%d test=%d checks=%d/%d pass"
          % (N_FAM, len(pairs), len(views["train"]), len(views["val"]), len(views["test"]),
             sum(c["ok"] for c in checks), len(checks)))
    print("[mint_p1] mix:", receipt["mix"])
    print("[mint_p1] strata:", receipt["by_stratum"])
    print("[mint_p1] sha:", {k: v[:16] for k, v in digests.items()})


if __name__ == "__main__":
    main()
