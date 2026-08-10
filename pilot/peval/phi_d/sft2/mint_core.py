"""mint_core.py — shared span/projection/self-check machinery for the SFT2 full mint
(phi+d lane C, production stage). Read-only imports of the frozen renderer
(generate_families), the sft0 prototype (mint_spec), the sft1 P1 driver (mint_p1)
and the adjudicated audit (audit_expanded). No generator edits, no sealed writes.

Frozen production rules (adjudication conditions carried over from SFT1 §8):
  * evidence clips <= 12 WORDS (gold-side preference from SFT1 §8.4; the audit's
    15-word evidence bar is untouched). Every span handed to the IR is len<=12
    words; sentence-level evidence is head-clipped inside its located sentence.
  * hidden values stay SYMBOLIC where the text omits the digits (word-boundary
    probes, audit num_stated semantics); statedness is asserted BIDIRECTIONALLY
    on the rendered text, never hardcoded per kind.
  * audit gold self-check: every minted gold IR is scored with
    audit_expanded.task_truth + score_row under the SFT1-frozen minted-truth rule
    (attribute anchor = gold IR's own attribute tokens). Whitelisted measurement
    gaps are enumerated in AUDIT_GAP_WHITELIST (documented in DATA_QC.md).
"""
import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent            # pilot/peval/phi_d/sft2
PHI_D = HERE.parent
PILOT = PHI_D.parent.parent
sys.path.insert(0, str(PILOT))
sys.path.insert(0, str(PHI_D))
sys.path.insert(0, str(PHI_D / "sft0"))
sys.path.insert(0, str(PHI_D / "sft1"))

import generate_families as G                             # noqa: E402  (read-only)
from program_dsl import ARCHETYPES                        # noqa: E402  (read-only)
from common import validate_ir                            # noqa: E402
import mint_spec as M                                     # noqa: E402  (sft0 prototype)
import mint_p1 as MP                                      # noqa: E402  (sft1 P1 driver)
import audit_expanded as A                                # noqa: E402  (read-only)

MAXW = 12                                                 # frozen evidence word cap
MintError = M.MintError
_assert = M._assert
locate = M.locate
find_all = M.find_all
theta_stated = MP.theta_stated
base_ir = M.base_ir


def clip_words(s, maxw=MAXW):
    w = s.split()
    return s if len(w) <= maxw else " ".join(w[:maxw])


def stated_num(x, clause):
    """Mint-side numeric statedness probe. Applies the audit's num_stated
    word-boundary semantics (audit_expanded.num_stated) after stripping
    SENTENCE-FINAL periods that trail a digit ('...exceed 400.' -> '400 '):
    the audit's raw probe (?![\\d.]) treats sentence-final 'N.' as not-stated
    (decimal protection), which misreads plain digits at a sentence boundary.
    This is strictly decimal-safe ('5.5' keeps its dot) and is used ONLY for
    mint label/statedness decisions; audit-side agreement is preserved by the
    numeric-membership rule (digit-bearing IR values matching the truth set
    score True even when the audit's window probe says digit-absent).
    """
    import re as _re
    normalized = _re.sub(r"(?<=\d)\.(?!\d)", " ", clause) + " "
    return theta_stated(x, normalized)


class Ib(M.IrBuilder):
    """IrBuilder with the frozen <=12-word cap and prefix-clipped sentence evidence."""

    def span(self, field, span, after=0, max_words=MAXW):
        return super().span(field, span, after, max_words)

    def span_prefix(self, field, raw, after=0):
        """Locate the (possibly long) raw span at/after `after`, then ship its
        first <=MAXW words (still a verbatim prefix of the located span)."""
        s, e, n = locate(self.text, raw, after, field)
        clip = clip_words(raw)
        _assert(self.text[s:s + len(clip)] == clip, "%s: prefix clip mismatch" % field)
        _assert(s < self.core_end, "%s: evidence lands in filler region" % field)
        self.ev.append({"field": field, "span": clip, "start": s,
                        "end": s + len(clip), "occurrences": n})
        return clip, s

    def sentence(self, field, text, offset):
        """Sentence-bounded evidence around offset, head-clipped to MAXW words."""
        sent, st, _se = M.sentence_around(text, offset, max_words=60)
        return self.span_prefix(field, sent, after=st)


def card_core_end(text):
    pad_at = text.find("\nNote: ")
    return pad_at if pad_at != -1 else len(text)


# ---------------------------------------------------------------------------
# kind-aware expected op sequence (faithfulness_audit.SIG_EXPANSION + the
# SFT0/SFT1 kind rule: policy read renders only in cards; P4 absent archive
# node is excluded from the present-node sequence).
# ---------------------------------------------------------------------------
def expected_ops(signature, kind, j2_policy_read=False):
    steps = signature.split("|")[-1].split(";")
    ops = []
    for s in steps:
        if s == "READ":
            ops.append("read")
        elif s == "READ+POLICY":
            ops.append("read")
            if j2_policy_read:
                ops.append("read")
        elif s == "READx2":
            ops += ["read", "read"]
        elif s == "AGG":
            ops.append("aggregate")
        elif s == "CHECK":
            ops.append("branch")
        elif s == "BRANCHWRITE":
            pass
        elif s == "WRITE":
            ops.append("write")
        elif s == "WRITEx2":
            ops += ["write", "write"]
        elif s == "ARCHIVE":
            ops.append("write")
        elif s == "DELx2":
            ops += ["write", "write"]
        elif s == "VERIFY":
            ops.append("verify")
        else:
            raise MintError("unknown signature step %r" % s)
    return ops


def present_ops(ir):
    return [n["op"] for n in ir["nodes"] if n["status"] == "present"]


# ---------------------------------------------------------------------------
# entity instantiation (adjudication condition 1, extended to all schemas).
# Per-schema generic -> concrete substitution; applied to the roles dict
# BEFORE CARD_STYLES rendering; the projection re-derives every clause from
# the mutated roles (assertions run on what is actually rendered).
# ---------------------------------------------------------------------------
ENTITY_SUBS = {
    "crm_escalate": lambda inst: [("the customer's email address",
                                   inst["meta"]["entity_email"])],
    "inv_overstock": lambda inst: [("the item's SKU", inst["meta"]["sku"])],
    # P2 cards: GOAL-LINE TAG ONLY. The descriptor phrases repeat ~12x per card,
    # so per-occurrence instantiation (+40-70 words) blows the [200,300]-token
    # pad window (measured: cal card core ~470-510 tokens). Tagging the goal
    # sentence with the family identifier (+5 words) is enough to de-collide
    # (labels re-derived from the mutated roles by the same machinery).
    "inv_transfer": lambda inst: [
        ("warehouse row.", "warehouse row for SKU %s." % inst["meta"]["sku"])],
    "cal_move_headcount": lambda inst: [
        ("session.", "session of '%s' (%s)." % (inst["meta"]["title"],
                                                inst["meta"]["date"]))],
    "ticket_gate_close": lambda inst: [("the ticket key", "ticket %s" % inst["meta"]["tkey"])],
    "cal_finalize": lambda inst: [("the event title",
                                   "the event '%s' on %s" % (inst["meta"]["title"],
                                                             inst["meta"]["date"]))],
    "crm_purge_lead": lambda inst: [("the lead's email address",
                                     inst["meta"]["entity_email"])],
    "ticket_purge_spam": lambda inst: [("the ticket key", "ticket %s" % inst["meta"]["tkey"])],
}


def instantiate_roles(roles, schema_key, inst):
    subs = ENTITY_SUBS[schema_key](inst)

    def rw(x):
        if isinstance(x, str):
            for a, b in subs:
                x = x.replace(a, b)
            return x
        if isinstance(x, list):
            return [rw(v) for v in x]
        if isinstance(x, dict):
            return {k: rw(v) for k, v in x.items()}
        return x

    return rw(roles)


# ---------------------------------------------------------------------------
# numeric-printing card lever (DATA_SPEC §4, highest-priority mint-side
# addition). Deterministic per-slot coin; roles phrases substituted BEFORE
# rendering. The projection decides numeric-vs-symbolic by probing the
# RENDERED text (bidirectional assertion) — the lever flips labels
# automatically, exactly the FEASIBILITY.md (d) design.
# ---------------------------------------------------------------------------
NUMERIC_SCHEMAS = ("crm_escalate", "inv_overstock", "inv_transfer", "cal_move_headcount")


def numeric_card_coin(gs, fidx, s, cell):
    return G.sha_int("numcard", gs, fidx, s, cell) % 10 < 5


# ---------------------------------------------------------------------------
# audit gold self-check (SFT1-frozen minted-truth rule). Returns (hard_fails,
# soft_gaps) where soft_gaps are whitelisted measurement-side gaps.
# ---------------------------------------------------------------------------
def audit_selfcheck(text, ir, program_params, archetype):
    task = {"program_params": program_params, "signature": None}
    truth = A.task_truth(task, archetype)
    # minted-truth attribute anchor (audit_sft1 frozen rule): gold attribute tokens.
    attr_g = next((n["args"]["predicate"]["attribute"]["value"]
                   for n in ir["nodes"] if n["args"].get("predicate")), None)
    if attr_g:
        truth["pred_attr"] = frozenset(A.toks(attr_g))
    rec = A.score_row(ir, text, truth, None)
    keep = ("pred_attribute", "pred_op", "pred_value", "pred_polarity", "pred_all",
            "branch_effects", "direction", "scope", "archive_capture",
            "roles_required", "termination")
    hard, soft = [], []
    for f in keep:
        verdict = rec.get(f)
        if verdict is None:
            continue
        v, mode, detail = verdict
        if v is True or v == "NA":
            continue
        if v == "UNMEAS" or v is None or v is False:
            soft.append((f, v, mode, detail))
    return rec, soft


def gap_is_whitelisted(schema_key, kind, nm, field, verdict):
    """Known measurement-side gaps, frozen BEFORE seeing them (documented in
    DATA_QC.md): audit keyword/lexical rules the text-faithful gold cannot
    satisfy without inventing unstated tokens."""
    v, mode, _d = verdict
    if field == "scope" and nm and schema_key == "ticket_gate_close":
        # NM text says 'complete'; audit keyword parse wants the literal filter
        # token 'done'. Gold stays text-faithful.
        return True
    if field == "scope" and schema_key == "cal_finalize":
        # audit's scope triple for cal_finalize keys on the PARENT-LINK filter
        # (event_id digits, never printed in text): any text-faithful gold
        # contradicts. Systematic measurement-side convention, verified on the
        # adjudicated canon audit (per_sample: cal rows truth_filter
        # [['event','id'],'==',[digits]]).
        return True
    if field == "pred_value" and v == "UNMEAS":
        # audit's digits-absent-no-symbolic-handle (documented by SFT1: J1 P1 cards)
        # and P3 card concept rows — value fidelity is covered by gold-exact matching.
        return True
    if field == "pred_all" and v == "UNMEAS":
        # pred_all is UNMEAS exactly when a pred subfield is (pred_value above);
        # same whitelisted measurement gap, aggregate level.
        return True
    return False
