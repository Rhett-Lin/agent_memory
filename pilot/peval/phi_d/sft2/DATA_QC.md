# DATA_QC — SFT2 production mint (φ+d lane C, data stage)

Dataset: 4,000 (text, gold phi_ir/v0) pairs from 200 NEW latent families (25 per
schema × 8 schemas, interleaved plan_families port), mint seed `gs_mint=20260812`
(sealed benchmark seed 20260807 and pilot seed 20260811 held out/disjoint).
Splits frozen BEFORE first rendering: 150 train / 25 val / 25 test families →
**train 3,000 / val 500 / test 500** (family-disjoint; every schema×join-depth
stratum represented in test). Nested learning-curve subsets `train_lc300 ⊂
train_lc1000 ⊂ train_lc3000` frozen by `sha1(gs|"curve"|pair_id)` order.

Ground truth chain (read-only): `pilot/generate_families.py` + `program_dsl.py`
(renderer) · `sft0/mint_spec.py` (mint20 prototype, 355/355) · `sft1/mint_p1.py`
(adjudicated P1 driver) · `audit_expanded.py` (adjudicated audit; gold self-check).
Everything else is mint-side machinery under `sft2/`.

## 1. Gate table (per-item, 4,000 rows)

| gate | result | note |
|---|---|---|
| validate_ir pass rate | 4,000/4,000 (1.0) | hard gate per item |
| byte-determinism (two consecutive full runs) | identical on all 7 artifacts | sha256 of every emitted file compared |
| evidence verbatim + ≤12 words + pre-filler core | 82,151 checks incl. span re-slice, 1.0 | independent re-verification pass, offsets recorded |
| predicate op == program op (incl. near-miss flips) | 4,000/4,000 | P1 `cond_op`, P3/P4 `check.op`, P2 frozen `>=` (membership {>=,<=}) |
| polarity rule | 4,000/4,000 | P1/P4 positive assert; P2 audit cue rule on full text; P3 negative-correct/positive-NM |
| value statedness (word-boundary, bidirectional) | 4,000/4,000 | numeric iff digits in condition clause, else symbolic/string; mint probe in `mint_core.stated_num` (D5) |
| decontamination vs 732 sealed reference hashes | 0 collisions | tasks_sealed + memories_sealed + pairs.jsonl unique texts |
| global text uniqueness | 4,000/4,000 unique | dedupe-by-rotation machinery |
| audit gold self-check | all True except whitelisted measurement gaps (§4) | `audit_expanded.task_truth` + `score_row`, minted-truth attr anchor |
| stratum coverage in every group | 10/10 strata in train/val/test | receipt `by_stratum` |
| LC subset archetype shares ±5pp | pass, 0 re-draws | receipt `lc_subsets` |

Total per-item checks: **82,151 / 82,151 pass (sft1-style ledger + spans)**.

## 2. Counts vs spec

| measure | spec (DATA_SPEC §1–3) | minted | verdict |
|---|---|---|---|
| texts | 4,000 (200 fam × 20) | 4,000 | ✓ |
| families | 200 (25/schema) | 200 | ✓ |
| train / val / test texts | ~3,000 / 500 / 500 | 3,000 / 500 / 500 | ✓ |
| card relation mix (per DATA_SPEC §2 over 3,000 cards) | 40% same / 30% near-miss / 30% unrelated | global: 1,200 same / 900 nm / 900 A00 | ✓ exact |
| all-text mix (incl. 1,000 instructions) | — | 2,000 same / 1,100 nm / 900 unrelated | n/a |
| instruction vs card | 1,000 / 3,000 | 1,000 / 3,000 | ✓ |
| join-depth strata (P1) | crm 15 J1+10 J2, inv 10 J1+15 J2 families | same (plan port) | ✓ |
| archetype share | 50 families each | texts: P1 735 / P2 730 / P3 776 / P4 759 (train) ±2.6pp | ✓ |
| numeric vs symbolic (P1/P2 cards goal: kill kind⇒value-mode shortcut) | lever ~50/50 | crm_esc 182/182 (0.500) · inv_over 170/215 (0.442) · inv_trans 166/184 (0.474) · cal_move 182/180 (0.503) | ✓ |
| value policy global | hidden values symbolic | numeric 1,275 / symbolic 1,709 / string 1,016 | ✓ |
| test strata | every (schema,J) stratum ≥1 family; ≥3/schema | 10/10 strata; ≥3 fam/schema (crm J2 1, inv J1 1 by frozen quota, crm schema total 4) | ✓ |

## 3. Forced fixes (machinery iterations, all mint-side, all logged)

1. **P2 card instantiation budget.** Per-occurrence entity substitution blows
   the [200,300]-token pad window (measured cal_move card core 470–510 tokens)
   → P2 cards carry a GOAL-LINE family tag only ("...warehouse row for SKU
   WD-1044."). Labels re-projected from the mutated roles, same machinery.
2. **Dedupe retry levers.** The (family) pad-stream hash made every retry of a
   slot byte-identical whenever the unpadded core ≥240 tokens (P2/P3 cores:
   2447 slots clean, 349 style rotations, 3 sibling variants, 277 filler-forced
   in the final mint) — a 45-text kill tripped on the first production run.
   Fix: per-attempt pad stream `sha_int("cardx", gs, fi, s, cell, v, rot, force)`
   + up to two forced filler lines (fresh stream, window enforced). Kill
   condition resolved inside machinery; second production run: 0 failures.
3. **A01 nm-entity variants.** A family's NM card core is a single roles blob
   (only 2 of 6 styles fit the window on cal_move) → 5 A01 slots could not
   dedupe. Fix: nm sibling-entity draws `sib_idx 90+v` (v∈0..3), same family
   params / same flipped program — the pilot's variant rule applied to the nm
   stream. Logged as A01 `dedupe_variant`.
4. **Sentence-final-dot numeric probe.** Audit `num_stated` treats `"400."` as
   not-stated (decimal protection) although digits are plainly visible at a
   sentence boundary (P2 cap bound). Mint probe `stated_num` strips only
   sentence-final dots (decimal-safe). Label consistency with the audit is
   preserved by its own numeric-membership rule (digit-bearing matching values
   score True even when the window probe says digit-absent).
5. **P4 NM erase-clause evidence split.** NM instructions collapse the two
   deletes into one "erase the X and all of its Y" clause; the two delete nodes
   take distinct sub-spans (children "all of its rows in lead_notes", parent
   "erase the lead"). Correct-program phrasing asserted separately.

## 4. Whitelisted measurement-side gaps (frozen set, gold unchanged)

These are adjudicated-audit lexical/keyword conventions that any text-faithful
gold violates; all counts in `mint_receipt.json → dedupe_by_rotation.whitelisted_gap_counts`:

- `cal_finalize|scope` (554 texts): audit scope triple keys the parent-link
  filter (`event_id` digits, never printed in text) — same artifact regime as
  the adjudicated canon audit (cal rows `truth_filter [['event','id'],'==',[digits]]`).
- `ticket_gate_close|scope` (125 texts): NM text says "complete"; audit keyword
  parse wants literal `done`. Gold stays as-stated.
- `crm_escalate|pred_value`, `inv_overstock|pred_value` (+ `pred_all`
  aggregates): J1-symbolic P1 cards hit the audit's documented
  digits-absent-no-symbolic-handle → UNMEAS (SFT1 §4 documents the identical
  regime: value fidelity is covered by gold-exact matching).
- `ticket_gate_close|clause_artifact` (1 text): audit `condition_clause` cue
  matching is case-sensitive substring — `"Elif Nieminen"` contains lowercase
  `"if "`, so the audit window lands on a reporter-name fragment. Gold polarity
  follows the mint's frozen cond-scope negation rule (semantics: negative,
  correct). Detection rule in `mint_all.clause_extraction_artifact` (frozen).

## 5. The five hardest schema-specific correctness decisions (frozen rules)

- **D1 — P2 composite guard = ONE branch node.** Predicate = the source-side
  keep bound: attribute = the text's unit word ("units"/"attendees" instructions;
  "stock level"/"headcount" cards), op `>=`, value = min_keep numeric iff stated
  (word-boundary) else the symbolic min_text. The destination-side cap bound
  lives in the branch node evidence (full guard clip) — phi_ir/v0 has no
  conjunction construct; audit accepts op ∈ {>=,<=} and numset value.
  Direction is carried by roles source/destination + sign-tagged effects
  (then: subtract@source, add@destination; else: sign-free report).
  **P2 polarity = the audit's condition-clause cue rule evaluated on the full
  text** (style 0 lands in the 300-char fallback window containing "must not
  exceed" → `negative`; styles 1/2 and all cards → `positive`). Frozen
  measurement convention, not a semantic claim about the guard.
- **D2 — P3 instruction verify/termination evidence** = the procedure's stated
  completion directive per style ("Verify the counts yourself before writing" /
  "then write the update and the log entry" / ...). The generator renders no
  literal read-back sentence in P3 instruction styles; cards carry the explicit
  read-back step. Same disclosure class as the adjudicated SFT1 J2 policy-read
  kind rule. Op sequence stays complete (LCS = 1.0 by construction).
- **D3 — P4 audit_sink & archive node: absent-with-evidence on near-miss.**
  status `absent` + verbatim omission clause ("no archival copy is needed" /
  "do NOT leave any audit entry" / card step "No archival copy is required for
  this request."). The absent archive write keeps its pipeline position; the
  present-node op sequence matches the skip_archive signature expansion.
  P4 card polarity is positive via the pre-registered E1 exception pattern
  (asserted: "is 'cold' -- if it is not"; anything else fails the mint loudly).
- **D4 — Aggregate node carries the as-stated filter phrase** in `args.value`
  ("subtasks whose status is not 'done'" / "subtasks that are complete" /
  "attendees with RSVP 'declined'" / "attendees that have accepted"), with the
  whitelisted measurement gaps of §4. No unstated filter tokens are invented.
- **D5 — Numeric-vs-symbolic decided from the RENDERED TEXT, bidirectionally.**
  Instructions: P1 J1 numeric / J2 policy-pointer symbolic; P2 always numeric
  (both bounds printed); P3 correct instructions numeric 0, NM symbolic;
  P4 string values. Cards: value symbolic per theta phrase UNLESS the
  numeric-printing card lever fires (deterministic per-slot coin
  `sha_int("numcard", gs, fi, s, cell) % 10 < 5`, P1/P2 schemas; coin invariant
  across dedupe retries). The label follows the probe alone — a missed
  substitution would show up as a share drift in the receipt, never as a
  mislabeled row.

## 6. Known limitations

- Near-miss inclusion is 1-of-1 kind per archetype (the generator's own NM
  classes); the comparator gets no second mutation family.
- P2 instruction polarity is style-dependent by measurement convention (D1);
  the model will learn style→polarity alongside text-reading. Documented,
  consistent with the evaluator on this corpus.
- Sham (Q) cards excluded (per DATA_SPEC §2).
- The P2 cap bound is not a first-class predicate field (see D1) — it is
  recoverable from branch evidence; comparator must not expect a second predicate.
- LC300's smallest stratum (crm J2 ≈ 21 texts) is thin for per-stratum curves.

## 7. Artifact hashes (two-run byte-identity)

| artifact | run 1 sha256 | run 2 sha256 | identical |
|---|---|---|---|
| data/train.jsonl | 54685e41 | same | ✓ |
| data/val.jsonl | 8d0aa43b | same | ✓ |
| data/test.jsonl | 414061bb | same | ✓ |
| data/train_lc300.jsonl | e0af3f16 | same | ✓ |
| data/train_lc1000.jsonl | 1a6021ba | same | ✓ |
| data/train_lc3000.jsonl | 54685e41 | same | ✓ |
| minted_all.jsonl | d02aed1e | same | ✓ |
| mint_receipt.json | — | — | ✓ byte-equal content (incl. code hash after rerun) |

Discipline kept: labels/cell/family never enter any model input (training view =
`{text, gold_ir}`; everything else provenance sidecar); test slice never trained
(train/test families disjoint by the pre-render split); no threshold touched
after seeing any metric; all seeds gs_mint 20260812.
