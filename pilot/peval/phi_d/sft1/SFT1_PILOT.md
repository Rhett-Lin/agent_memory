# SFT1_PILOT — φ-extractor LoRA-SFT mini pipeline (φ+d lane C, stage-B pilot)

**Goal of this run: validate the end-to-end mini pipeline (mint → LoRA train →
extraction audit vs base) and measure the first extraction-gate numbers — NOT to
produce a good model.** Verdict below; all numbers reproducible from the receipts.

## Verdict / go–no-go

**GO for the full 4,000-text production, with conditions (§8).** Every pipeline stage
ran end-to-end with hard receipts (mint self-consistency 8194/8194 checks twice,
byte-identical sha256 across runs; train converged, no divergence/hang; audit
sanity-checked bit-for-bit against the adjudicated audit machinery). On the minted
P1 test slice the SFT extractor passes **6/8 adjudicated gates** (fails parse 0.967
and evidence-verbatim 0.943 vs the 0.99 bars). The canonical-80 comparison shows the
expected P1-only specialization cost: general extraction collapses on non-P1
archetypes (parse: P3 4/16, P4 0/16 valid) — a data-coverage problem the full
production mix is designed to fix, not a pipeline defect.

## 1. Stage status

| stage | status | receipt / artifacts |
|---|---|---|
| 1. Mint P1 dataset | DONE — 460 minted (train 300 / val 60 / test 90 shipped; 10 test-family texts held out) | `mint_receipt.json`, `data/{train,val,test}.jsonl`, `minted_all.jsonl`; 8194/8194 checks; two consecutive runs byte-identical (train `8c6af91f…`, val `30649f4b…`, test `24d9dd6b…`, all `8c2c0bf0…`) |
| 2. LoRA train | DONE — converged, no kill criteria hit | `train_receipt.json`, `train.log`; adapter `/work1/zixuan/checkpoints/agent_memory/phi_sft/lora_p1_sft1/` (40.4 MB) |
| 3. Extraction eval | DONE — 3 conditions, one GPU job | `eval/{base_test90,sft_test90,sft_canon80}.jsonl`, `eval.log` |
| 4. Audit vs base | DONE — audit_expanded machinery reused verbatim; base@canon80 verdicts match `audit_expanded/per_sample.jsonl` for all 80 keys | `metrics.json`, `worst_examples.json` |

## 2. Dataset (stage 1)

- 23 NEW families, seed `gs_mint=20260811` (sealed benchmark seed 20260807 fully held
  out); interleaved crm_escalate/inv_overstock, join-depth cycles of the generator's
  own patterns → strata crmJ1 8 / crmJ2 4 / invJ1 5 / invJ2 6.
- Groups frozen BEFORE rendering (rank by sha1 within stratum, frozen quotas):
  train 15 fam / val 3 fam / test 5 fam; every stratum covered in the test slice.
- Per family 20 texts: 5 instructions (4 sibling + 1 near-miss) + 15 cards
  (4 A11 + 2 A10 + 5 A01 + 4 A00). Mix: same 50% / near-miss 30% / unrelated 20%.
- Shipped: train 300 (150/90/60), val 60 (30/18/12), test 90 (46/25/19 — the first
  18/family per frozen pair-order key; mix drifts ≤2pp by construction).
- Test strata: crmJ1 31, crmJ2 18, invJ1 20, invJ2 21. Value policy: 65 numeric
  (J1 instructions) / 395 symbolic by construction, 0 numeric leaks (asserted both
  directions per pair).
- Decontamination: zero sha256 overlap of any minted text vs
  tasks_sealed + memories_sealed + pairs.jsonl unique texts (hard gate every pair).
- **Two mint-side corrections, both forced by hard gates and disclosed in the receipt
  (NOT silent relaxations):**
  1. *Entity-instantiated cards.* Entity-generic P1 card cores are param-free — 162/345
     naively minted cards were byte-identical to sealed benchmark memories (the
     decontamination gate fired). Cards now substitute the concrete email/SKU into the
     roles id-phrase before rendering (families' own identifiers; DATA_SPEC.md §4's
     "needs-building" lever class). All clause expectations are still asserted
     verbatim by the same projection machinery.
  2. *Dedupe-by-rotation.* Cross-family collisions (A10/A00 partner card ≈ partner's
     own A11 card when unpadded) are resolved inside the mint: per slot, rotate card
     style (32/345 slots) then sibling-meta variant (0/345) until globally new; the
     labels are re-projected after each attempt.
  - also: word-boundary fork of one prototype assertion (`theta 57` ⊂ `SKU LV-5725`
    naive-substring false alarm → audit's `num_stated` word-boundary semantics);
    dual-run proof: fork output ≡ prototype output wherever the prototype did not
    misfire. A00 texts use the generator's own unrelated-partner rule restricted to
    P1 (opposite join-depth, cross domain) so all gold stays inside the verified
    projection machinery; A01 gets a documented 5th slot.

## 3. Training (stage 2)

Qwen2.5-7B-Instruct @ a09a3545 + LoRA r16/α32/d0.05 on q,k,v,o (10.09M trainable),
lr 1e-4 cosine (3% warmup), bs1 × accum16 (eff 16), 2 epochs (38 optimizer steps),
bf16, loss on gold-IR completion tokens only (canonical extraction prompt + PREFILL
masked). MAXLEN 2112 (task default 2048 would have dropped 92/300 examples: measured
full-length range 1803–2092; 0 skipped).

- Loss curve (log every 5 steps): 0.1784 → 0.0579 → 0.0264 → 0.0148 → 0.0100 →
  0.0075 → 0.0068 (smooth, no spikes/NaN; kill criterion "diverge/hang" NOT hit).
- Eval loss (epoch 1→2, on held-out group-val families): 0.0117 → 0.0054.
- Wall time 873 s on GPU 4; train_loss 0.0401 (final aggregate).

## 4. Extraction-gate table

Protocol: canonical dde9f415 lineage (extract_phi_run5200 constants) — prompt +
PREFILL, temp 0 seed 42, one JSON-repair retry, `validate_ir`. Prompt-only decoding +
parse **for both conditions** (the canonical extraction does not use guided decoding;
guided FSM building with adapter weights was not needed and would break parity with
the audited base lineage — disclosed, no numbers depend on it). base@canon80 rows are
the frozen `out/extractions_v2.jsonl` rows; SFT@canon80 re-run with the adapter in the
same vLLM process. Minted-slice truth: minted gold (pred-attr anchored on gold
attribute tokens — the audit's sealed-field anchor is a D1 artifact on minted data;
applied identically to both conditions). canon80 truth: audited sealed-join
(sanity-verified identical verdicts). Field aggregates over valid rows; invalid rows
enter parse/coverage/LCS denominators.

| gate (threshold) | base@test90 | **sft@test90** | base@canon80 | sft@canon80 |
|---|---|---|---|---|
| parse ≥ 0.99 | 0.756 | **0.967 FAIL** | 1.000 | 0.562 FAIL |
| evidence verbatim ≥ 0.99 | 0.603 | **0.943 FAIL** | 0.200 | 0.622 FAIL |
| critical precision ≥ 0.95 (pred_all present-only) | 0.949 | **1.000 PASS** | 0.406 | 0.316 FAIL |
| critical recall ≥ 0.90 (pred_all all-rows) | 0.949 | **1.000 PASS** | 0.325 | 0.267 FAIL |
| critical recall per archetype ≥ 0.85 (covered) | 0.949 PASS (P1 only) | **1.000 PASS (P1 only)** | 0.000 FAIL (agg) | 0.000 FAIL |
| false-ABSENT ≤ 0.05 (max roles/termination) | 0.000 PASS | **0.000 PASS** | 0.338 FAIL | 0.133 FAIL |
| both-side joint branch/effect coverage ≥ 0.80 | 0.756 FAIL | **0.967 PASS** | 0.425 FAIL | 0.338 FAIL |
| LCS ≥ 0.90 | 0.756 FAIL | **0.967 PASS** | 0.617 FAIL | 0.428 FAIL |

**sft@test90: 6/8 PASS.** Kill criterion "extraction recall < 0.60 on minted test"
NOT hit (1.0 ≫ 0.60).

Supporting diagnostics (sft@test90): per-field all-rows agreement = 1.0 on
pred_attribute / pred_op / pred_value / pred_polarity / branch_effects / termination;
pred_value UNMEAS on 39/90 (36 J1-family cards — cards are symbolic-valued by
construction and hit the audit's digits-absent-no-symbolic-handle rule — plus the 3
invalid rows; their value fidelity is instead covered by gold-exact string match = 1.0). Roles
slot-level: present 1.0 / unknown 0.0 / false-absent 0.0. Gold-exact full-IR string
equality 0.874; predicate subfields + then/else effect sets exact 1.0.

canon80 per-archetype pred_all (all-rows): base conditional_write 0.458 →
**sft 0.522** (P1 improved; has_branch 0.708→0.958), two_row_transfer 0.042→0.000,
aggregate_gate 0.000→0.000, delete_after_capture 0.875→no valid IRs. SFT parse by
archetype: P1 23/24, P2 18/24, P3 4/16, P4 0/16.

## 5. Worst remaining failures

Selected by critical-field failure count (`worst_examples.json` has full payloads).

1. **Distribution narrowing on non-P1 archetypes (canon80, dominant class).** On
   P3/P4 instructions the SFT extractor either emits a non-phi_ir graph dialect
   (fails `validate_ir`; raw shows `"type"/"role"/"cond"` keys) or drops the
   predicate/effects payload — e.g. `instruction:0be22a4c…` (P3): polarity
   contradiction + branch_effects missing + roles false-absent + termination
   contradiction; `instruction:1d01617f…` (P2): all predicate fields missing (the
   remaining top-5 rows are P2 as well). P4 went 16/16 invalid. This is the expected
   cost of P1-only training at near-zero loss and is the main thing the 4-archetype
   production mix must fix.
2. **Family-clustered schema fallback (minted test90).** Exactly 3 rows invalid after
   repair — all three are sibling instructions of a single held-out test family
   (f9, inv_overstock J2, category 'controls', θ=68). Sibling s3 of the same family
   parses fine. No textual exoticism; reads as a stochastic mode-collapse pocket at
   the distribution edge of one family.
3. **Overlong verbatim evidence (both slices).** 5/87 valid SFT test90 IRs quote the
   full condition clause (>15 words) instead of the mint's 15-word head clip
   (0 non-verbatim quotes). Verbatim YES, word-cap NO — the 0.943 evidence gate miss
   is purely a formatting convention boundary; on canon80 SFT quotes are still 3×
   more verbatim-conformant than base (0.622 vs 0.200).

## 6. Kill criteria — none triggered

- Train loss divergence/hang: NO (curve §3).
- Extraction recall < 0.60 on minted test: NO (1.0).
- OOM: none (MAXLEN 2112 change was data-driven, logged; r/seq kept as specified).

## 7. Budget

One GPU (id 4) throughout, one training job total: mint ~2×2 min CPU; train 873 s;
eval 3 conditions ≈ 4.5 min; audit < 1 min CPU. GPUs 5–7 were free but unused.

## 8. Go/no-go rationale and conditions for the 4,000-text production

The pipeline gates themselves are now evidence: mint machinery scales (460 texts,
100% self-consistency, decontamination enforced), training is reproducible from the
receipt, and the audit reuse is sanity-verified against the adjudicated numbers.
GO, conditional on:

1. **Extend the P1 mint corrections to all 8 schemas** (entity instantiation,
   dedupe-by-rotation, word-boundary probes) and build the P2/P3/P4 clause tables +
   projections per DATA_SPEC.md Option A — otherwise either the same card-collision
   wall (entity-generic cores) or unverifiable labels.
2. **Full-archetype training mix.** P1-only SFT demonstrably collapses non-P1
   extraction (§5.1); uniform archetype/domain/style mix per DATA_SPEC §1–2 is
   expected to address this; re-measure the canon-side regression against today's
   base@canon80 column as the guardrail.
3. **Keep the ≥3 conv-state families per stratum in test** and the sealed-seed
   decontamination gate exactly as implemented here; do not reuse `gs_mint`.
4. Watch items: parse 0.967 (3-row single-family cluster) and the 15-word evidence
   convention are the two open gates on the minted slice; if they persist at
   production scale, prefer a mint-side evidence-clip preference (≤12-word gold
   clips) over any threshold change.

## Appendix — frozen measurement definitions (set before first metrics run)

- critical_recall = pred_all all-rows agreement (audit def; missing = disagreement,
  UNMEAS excluded); critical_precision = pred_all present-only; per-archetype clause
  applies to archetypes covered by the slice (test90 covers P1 only).
- false-ABSENT = max(roles_required, termination) audit false-absent rates.
- both-side joint branch/effect coverage = valid IR with a branch node carrying a
  non-null predicate AND non-empty then_effects AND non-empty else_effects;
  denominator = ALL rows.
- evidence verbatim = every present-status evidence string an exact case-sensitive
  substring of the text AND ≤15 words (row level over valid rows).
- LCS = mean LCS(expected_ops, ir_ops)/len(expected) (mint kind-aware expansion on
  test90; audit `expected_seq` on canon80); invalid = 0.
- canon80 = first 80 keys of extractions_v2.jsonl in file order (all instructions:
  24 P1 / 24 P2 / 16 P3 / 16 P4).
- Discipline kept: labels/cell/family never in model input; gold IR used only as
  supervision target; test slice never trained (train/test families disjoint by the
  pre-rendering split); no threshold touched after seeing metrics; all seeds 42 /
  gs_mint 20260811.
