# S2_PREP_REPORT — S2-prep: SFT2 extraction of the canonical 532 + expanded audit (φ+d comparator leg)

**Verdict: GO for S2-rc1, with one measurement rule to pin exactly as recommended by
SFT2_GATE_REPORT §7.** The SFT2 extractor reproduces the canonical 532-text corpus at
532/532 valid (all first-pass, zero repairs), is bit-reproducible against the
adjudicated canon80 gate run (80/80 IR-exact), and reaches both-side-JOINT branch
coverage 1.000 on every one of the 640 comparator pairs. Under the frozen expanded-audit
gates, **8 of 11 fields are HARD-VETO-eligible** (all at 1.000 all-rows / 1.000 worst
archetype / 0.000 false-ABSENT). The only failing fields are `pred_attribute`/`pred_all`
(the known sealed-anchor vs minted-D1-surface convention artifact — quantified here at
n=125, 100% of which are text-faithful: 113 contiguous-verbatim + 12 token-covered
paraphrase) and `scope` (P3 0.368; 53-row FK-anchor E2 class + 21-row paraphrase class).
With the S2 canon-side attribute anchor pinned to the text-faithfulness rule, the veto
table becomes **10/11 HARD VETO, scope excluded**.

## 0. Artifacts

| artifact | path |
|---|---|
| extraction script | `sft2_eval/extract_canonical_sft.py` |
| SFT IRs (532) | `sft2_eval/canonical_sft.jsonl` (sha16 `6ac5ebb9aef0fd8b`) |
| extraction receipt | `sft2_eval/canonical_sft_receipt.json` |
| audit script | `sft2_eval/audit_sft_canonical.py` (sha16 `0591b229c05befb2`) |
| audit metrics | `sft2_eval/audit_sft_canonical.json` |
| inputs (read-only) | `out/extractions_v2.jsonl` (532), `../pairs.jsonl` (640), `audit_expanded.py` (code sha16 `c80f481c964449bb`, imported read-only), `audit_expanded/{field_metrics.json,per_sample.jsonl}`, adapter `/work1/zixuan/checkpoints/agent_memory/phi_sft/sft2/` |

Naming note (lineage): the extraction surface is byte-identical to the adjudicated
SFT2 gate run (`sft2/eval_extract.py` run_condition + `extract_phi_run5200`
constants; prompt sha `5200e56eee95…` under the run5200 formula that includes the
PREFILL). Lane documentation calls this the "dde9f415 lineage"; that historical sha
belongs to the frozen *base* extractor's prompt file (same surface except the final
instruction line – prefill anchor moved into the prompt text – and a sha formula
without PREFILL). Prompt-only decoding, no guided FSM — same disclosure as
`eval_extract.py`. GPU 4 only; wall time 516 s.

## 1. Stage 1 — extraction of the canonical 532 (GPU 4)

Protocol: run5200 constants (prompt + PREFILL), temp 0 / top_p 1 / max_tokens 768 /
seed 42, ≤1 JSON-repair retry, `validate_ir`, vLLM base `Qwen2.5-7B-Instruct@a09a3545`
+ LoRA `sft2` (the exact `sft2/eval_extract.py` load pattern). Labels never read —
inputs are `(key, kind, text)` of the frozen v2 corpus only.

- **valid = 532/532 (instruction 160/160, memory 372/372), ALL first-pass, 0 repairs.**
- **Determinism check: 80/80 first-keys IR-exact vs the adjudicated
  `sft2/eval/sft_canon80.jsonl`** (same surface and decode; batch-composition-proof).
- Evidence spans (frozen ≤15-word verbatim rule): **6,621/6,621 checked, 0 bad (1.000)**.
- Termination status: present 532/532. Predicate carriers: all on branch nodes (128/153/187/64 per archetype), branch_presence 1.000.

### Pair-level coverage (all 640 pairs, archetype-stratified)

Per pair: both IRs present, both valid, per-side branch presence, per-side
both-side-JOINT (branch + predicate + non-empty then/else), pair-JOINT (= both valid ∧
both both-side-JOINT):

| archetype | n | both valid | instr branch | mem branch | instr BSJ | mem BSJ | **pair both-side-JOINT** |
|---|---|---|---|---|---|---|---|
| aggregate_gate | 160 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | **1.000** |
| conditional_write | 160 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | **1.000** |
| delete_after_capture | 160 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | **1.000** |
| two_row_transfer | 160 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | **1.000** |
| **overall** | **640** | **1.000** | **1.000** | **1.000** | **1.000** | **1.000** | **1.000** |

The comparator leg has zero extraction-side unmeasurable pairs.

## 2. Stage 2 — expanded audit on 532 SFT IRs (CPU, frozen rules)

Measurement code: `audit_expanded.py` imported read-only — same sealed joins,
PARTIAL-CONSENSUS UNMEAS policy, E1/E2 pre-registered exceptions, `aggregate_field`
with the frozen gate (overall ≥ 0.90 ∧ worst per-archetype ≥ 0.80 ∧ false-ABSENT ≤ 0.05)
and the frozen veto-eligibility rule (PASS → HARD VETO; FAIL & present_only ≥ 0.90 →
positive-only; else excluded). Sanity gates both green:

- **S1 join parity**: n_joined 532, no_join 0, arch_conflict 0, per-dimension conflicts
  `{scope: 11, pred_value: 36}` identical to the frozen base audit (truth is a function
  of (text, sealed) only).
- **S2 base-score parity**: re-scoring the frozen base IRs through this code path
  reproduces `audit_expanded/per_sample.jsonl` for all 532 keys × 11 gate fields
  (extends the adjudicated 80-row sanity to 532).

### Frozen gate table (SFT2 on canonical 532)

| field | n_app | UNMEAS | all_rows | worst arch | false-ABSENT | gate | **comparator eligibility** |
|---|---|---|---|---|---|---|---|
| pred_op | 532 | 0 | 1.000 | 1.000 | 0.000 | PASS | **HARD VETO** |
| pred_value | 416 | 116 | 1.000 | 1.000 | 0.000 | PASS | **HARD VETO** |
| pred_polarity | 532 | 0 | 1.000 | 1.000 | 0.000 | PASS | **HARD VETO** |
| branch_effects | 532 | 0 | 1.000 | 1.000 | 0.000 | PASS | **HARD VETO** |
| direction | 64 | 0 | 1.000 | 1.000 | 0.000 | PASS | **HARD VETO** |
| archive_capture | 147 | 0 | 1.000 | 1.000 | 0.000 | PASS | **HARD VETO** |
| roles_required | 532 | 0 | 1.000 | 1.000 | 0.000 | PASS | **HARD VETO** |
| termination | 532 | 0 | 1.000 | 1.000 | 0.000 | PASS | **HARD VETO** |
| pred_attribute | 532 | 0 | 0.765 | 0.188 (P2) | 0.000 | FAIL | excluded (present_only 0.765) |
| pred_all | 475 | 57 | 0.737 | 0.000 (P2) | 0.000 | FAIL | excluded (present_only 0.737) |
| scope | 304 | 11 | 0.757 | 0.368 (P3) | 0.000 | FAIL | excluded (present_only 0.757) |

Per-archetype all-rows (cond_write / two_row_transfer / aggregate_gate / delete_after):
pred_op 1/1/1/1; pred_value 1/1/1/1; pred_polarity 1/1/1/1; branch_effects 1/1/1/1;
roles_required 1/1/1/1; termination 1/1/1/1; direction P2 1.000; archive_capture P4
1.000; scope P3 **0.368** / P4 1.000; pred_attribute **0.523 / 0.188 / 1.000 / 1.000**;
pred_all **0.324 / 0.000 / 1.000 / 1.000**. Corpus mix n=532: P1 153 / P2 64 / P3 128 / P4 187
(joined corpus composition is identical to the base audit's by construction).

UNMEAS accounting (frozen policy: excluded from numerator AND denominator, reported):
pred_value 116 = 36 join-conflict + 80 digits-absent-no-symbolic-handle (E2 window);
pred_all 57 (value-side propagation). SFT's UNMEAS bucket is +18 vs base on pred_value —
the SFT extractor asserts a symbolic value on digit-absent rows where the base abstained;
the policy routes them out of both rates exactly as designed.

## 3. Attribute-anchor audit (the §canon issue, quantified on 532)

The SFT extractor deterministically emits the minted-D1 surface concept phrase while
the sealed canon truth anchors `pred_attribute` on program-param field tokens. Size:

| class | rows | detail |
|---|---|---|
| sealed-anchor contradictions, total | **125/532 (23.5%)** | P1 73/153, P2 52/64, P3 0, P4 0 |
| of which contiguous-verbatim in text (D1 surface; audit's own posthoc D1) | **113/125 (90.4%)** | P1 73/73, P2 40/52 — zero fabricated concepts |
| residue: non-contiguous paraphrase | **12/125** | all P2 inv-rebalance memories, IR attribute `"stock level"` |

The 113 are pure convention: e.g. `instruction:47c5ca809c880563` — clause
*"If the on-hand quantity of SKU NC-9342 at warehouse 'main' is above 70"* — IR
attribute `"on-hand quantity"` (verbatim) vs truth anchor `{qty}`; P2
`instruction:fbbe711a94eeee5b` — IR `"units"` vs `{qty}` on guard *"'east' ≥ 0 after
the move"*. The 12 residue rows: the text names the concept only symbolically
("must keep at least the minimum keep level … must not exceed its capacity" on the
**stock** table); the IR's `"stock level"` is not a contiguous substring, but every
attribute token IS text-covered (`{stock}` ← "stock table", `{level}` ← "minimum keep
level"; verified 12/12). **Invented-concept attributes: 0 anywhere.**

POSTHOC (non-gate, diagnostic) dual-anchor rescored eligibility — accept iff
sealed-anchor agreement OR text-faithfulness:

| rule | pred_attribute all_rows (worst) | eligibility | pred_all all_rows (worst) | eligibility |
|---|---|---|---|---|
| frozen sealed anchor (gate column) | 0.765 (0.188) | excluded | 0.737 (0.000) | excluded |
| dual-verbatim (OR contiguous verbatim) | 0.977 (0.812) | **HARD VETO** | 0.972 (0.769) | positive-only |
| dual-tokcov (OR all attr tokens ⊆ text tokens) | 1.000 (1.000) | **HARD VETO** | 1.000 (1.000) | **HARD VETO** |

**Recommended S2 measurement rule for canon fields (per SFT2_GATE_REPORT §7's mandate
to freeze the minted-truth anchor analogue on canon):** measure `pred_attribute` as
"no fabricated concept" — agreement iff `truth_anchor ∩ ir_tokens` OR
`ir_attribute_tokens ⊆ text_tokens` (dual-tokcov). This is the exact canon analogue of
the minted-side anchor (the gold IR's own attribute tokens are by mint construction
text-surface phrases), it changes nothing else in the frozen pipeline, and it makes
`pred_attribute` and `pred_all` HARD-VETO-eligible at 1.000/1.000. If adjudication
prefers the stricter contiguous-evidence reading, dual-verbatim still makes
`pred_attribute` HARD-VETO-eligible and `pred_all` positive-only-eligible — either is
safe for the comparator; what rc1 must NOT do is ship the bare sealed anchor
(it would masquerade the convention artifact as −23.5pp attribute / −26.3pp pred_all
regressions). UNMEAS side effect, disclosed: under the rescore, 59 (verbatim: 47)
attribute-flipped rows whose value is join-conflicted move from pred_all "contradiction"
to UNMEAS (excluded both sides) — a bookkeeping shift, not a hidden rate change.

## 4. Scope — secondary finding (stays excluded)

`scope` fails only on P3 (0.368; P4 = 1.000), 74 contradictions in two classes:

- **53 rows, signature `P3|agg:open|op==` (calendar/events):** the truth filter is the
  aggregate's parent-link **foreign key** `(event, id, ==, <synthetic number>)` whose
  digits appear nowhere in the text (52/53) — the E2 class "truth not textually
  stated", the same family as DATA_QC §4's whitelisted `cal_finalize|scope` gap on the
  minted side. The IR renders the filter faithfully instead
  (`args.value = "attendees with RSVP 'declined'"`).
- **21 rows, signature `P3|agg:done|op>=` (subtasks):** truth `(status, ==, 'done')`
  is textually present; the IR paraphrases to `"subtasks that are complete"` — a real
  lexical-fidelity gap on the IR side (21/304 = 6.9% of scope rows).

Recommendation: `scope` stays **excluded** from S2-rc1 veto fields in any form
(hard or positive-only): the FK-anchor class needs a window-anchored scope rule
(separate convention decision), and the paraphrase class is unresolved IR behavior.

## 5. Comparison vs base-era audit (same 532, same frozen gates)

| field | base all_rows | base veto | **SFT2 all_rows** | **SFT2 veto** |
|---|---|---|---|---|
| pred_attr | 0.355 | excluded | 0.765 | excluded (→ HARD VETO under §3 rule) |
| pred_op | 0.558 | positive-only | **1.000** | **HARD VETO** |
| pred_value | 0.479 | excluded | **1.000** | **HARD VETO** |
| pred_polarity | 0.477 | excluded | **1.000** | **HARD VETO** |
| pred_all | 0.269 | excluded | 0.737 | excluded (→ HARD VETO under §3 rule) |
| branch_effects | 0.327 | excluded | **1.000** | **HARD VETO** |
| direction | 0.266 | excluded | **1.000** | **HARD VETO** |
| scope | 0.497 | excluded | 0.757 | excluded |
| archive_capture | 0.517 | excluded | **1.000** | **HARD VETO** |
| roles_required | 0.320 (fa 0.327) | excluded | **1.000** (fa 0.000) | **HARD VETO** |
| termination | 0.468 | excluded | **1.000** | **HARD VETO** |

Base era: 1 positive-only + 10 excluded fields — the comparator had essentially no
trustworthy veto surface. SFT era: 8 HARD VETO as-is, 10/11 under the pinned §3 rule,
and false-ABSENT is 0.000 on every field (the base-era false-absent failure mode,
roles_required 0.327, is gone). Every one of the 11 all-rows rates strictly improved.

## 6. Go / no-go for S2-rc1 comparator rules

**GO.** Conditions rc1 must pin:

1. **Attribute anchor (canon side):** dual-tokcov from §3 (fallback dual-verbatim).
   Then the comparator veto table is: HARD VETO on pred_op, pred_value, pred_polarity,
   branch_effects, direction (P2), archive_capture (P4), roles_required, termination,
   pred_attribute, pred_all; `scope` excluded; no positive-only entries needed.
2. **UNMEAS policy unchanged:** UNMEAS rows (pred_value 116; pred_all 57; scope 11;
   per-dimension join conflicts) are excluded from comparator numerators and
   denominators; an UNMEAS field verdict is never a mismatch.
3. **No extraction-side eligibility loss:** all 640 pairs both-valid +
   both-side-JOINT 1.000 — the comparator's denominator is the full 640.
4. **scope**: excluded from vetoes at rc1; if a scope measurement is wanted later it
   needs its own window-anchored rule plus a look at the 21-row paraphrase class.

Discipline: SFT adapter only (no fine-tuning); GPU 4 only for extraction; audit CPU-only;
labels reached the pipeline only through sealed truth joins at scoring time, never in
extraction inputs; deterministic seeds (42); frozen gates/thresholds untouched; writes
confined to `pilot/peval/phi_d/sft2_eval/`.
