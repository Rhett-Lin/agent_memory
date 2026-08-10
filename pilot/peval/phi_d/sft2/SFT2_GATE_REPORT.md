# SFT2_GATE_REPORT — φ-extractor LoRA SFT2 + extraction-gate evaluation (φ+d lane C, stage 2)

**Verdict: the SFT2 extractor passes all 8 adjudicated extraction gates on the held-out
production test slice (test500, held-out families, all 4 archetypes) — every metric is
at 1.000/0.000 exactly, including 500/500 gold-exact full-IR string equality.**
The canonical-80 regression guardrail shows net improvement over the base extractor on
every gate metric, with ONE regression cell (two_row_transfer per-archetype recall
0.042→0.000, a 1-row net on n=24) that field-level evidence attributes to the frozen
audit attribute-anchor convention on the sealed canon corpus, not to an extraction
capability loss (all other P2 fields 1.0; see §5).

## 0. Artifacts

| artifact | path |
|---|---|
| adapter | `/work1/zixuan/checkpoints/agent_memory/phi_sft/sft2/` (adapter_model.safetensors, 40.4 MB; `_trainer_tmp/` is Trainer scratch) |
| train curve + receipt | `train.log`, `train_receipt.json` |
| eval outputs | `eval/sft_test500.jsonl` (sha `32f12009a1090b7a`…), `eval/sft_canon80.jsonl` (sha `cc46a480470aeb1f`…) (16-char prefixes; full values in metrics.json), `eval.log` |
| gate metrics | `metrics.json`, `worst_examples.json` (top-10 with raw payloads) |
| maxlen measurement | `maxlen_measure.json` |
| scripts | `train_lora.py`, `eval_extract.py`, `audit_sft2.py` |

## 1. Training (one job, GPU 4, seed 42)

Qwen/Qwen2.5-7B-Instruct @ a09a3545 + LoRA r16/α32/d0.05 on q,k,v,o (10,092,544
trainable params = 0.1323%), lr 1e-4 cosine (3% warmup), bs1×accum16 (eff 16),
2 epochs (376 optimizer steps), bf16, grad-checkpointing, loss on gold-IR completion
tokens only (prompt+PREFILL masked). Identical to the adjudicated SFT1 recipe except
the two sanctioned adjustments:

- **MAXLEN 2304.** Re-measured on this corpus (`maxlen_measure.json`): prompt+gold
  tokens min 1799 / p50 2173 / p90 2221 / **p95 2241** / p98 2254 / p99 2259 /
  **max 2270**. Ladder {2048, 2304, 2560}: 2048 would drop 70.6% of rows; 2304 covers
  the max → **drop 0.0% ≤ 2%**. Target (completion) max 653 tokens < 768 decode budget.
- 2 epochs (unchanged; restated for the receipt).

Data integrity: consumed train sha256 `54685e41…`, val sha256 `8d0aa43b…` — byte-equal
to the QC'd mint artifacts (DATA_QC §7). 3,000/3,000 usable (0 skipped), val 500/0.
Test500 never trained (family-disjoint splits from mint_receipt, no re-splitting).

- **Train loss curve** (log every 5 steps, 76 points): 0.3318 → 0.2871 → 0.1816 →
  0.1357 → 0.1017 → 0.0728 → 0.0539 → 0.0369 → 0.0220 → … → 0.0053 (ep 0.29) →
  ~0.0001 by ep ~0.55 → 0.0000–0.0004 for the remainder of epoch 2.
  Smooth monotone decay, **no spikes, no NaN** (kill criterion NOT hit), grad_norm
  0.42 → <0.01.
- **Val curve** (held-out val families, per epoch): 2.2415e-4 (epoch 1) → 6.9399e-5
  (epoch 2). Both ends below any historic level seen in SFT1 (0.0117→0.0054); the
  near-zero plateau on held-out families indicates the gold surface convention is
  fully learnable from 3,000 rows — consistent with the test500 gold-exact 1.000.
- Wall time 9,052 s on GPU 4 (val eval 2×238 s included). No OOM; r/seqlen untouched.

## 2. Extraction protocol (evaluation)

Canonical run5200 lineage (EXA constants imported read-only): extraction prompt +
PREFILL, temperature 0 (top_p 1), max_tokens 768, seed 42, ≤1 JSON-repair retry
(0 repairs were needed anywhere), `validate_ir`. **Prompt-only decoding — guided FSM
not used** (same as SFT1: the canonical extraction protocol does not use guided
decoding, and an FSM with adapter weights would break parity with the audited base
lineage; disclosed, no numbers depend on it). One vLLM job, two conditions
(sft×test500, sft×canon80); base numbers are the frozen `out/extractions_v2.jsonl`
rows sanity-checked bit-for-bit against `audit_expanded/per_sample.jsonl` (80/80
verdicts identical, see §6).

## 3. Gate table

### (a) test500 — held-out families, all 4 archetypes: **8/8 PASS**

| gate (bar) | sft@test500 | verdict |
|---|---|---|
| parse ≥ 0.99 | **1.000** (first-pass 1.000, repairs 0) | PASS |
| evidence verbatim ≥ 0.99 | **1.000** (span-level 6,293/6,293 checked, 0 bad) | PASS |
| critical precision ≥ 0.95 (pred_all present-only) | **1.000** | PASS |
| critical recall ≥ 0.90 overall (pred_all all-rows) | **1.000** | PASS |
| critical recall ≥ 0.85 per archetype | P1 1.000 / P2 1.000 / P3 1.000 / P4 1.000 | PASS |
| false-ABSENT ≤ 0.05 (roles ∪ termination) | **0.000** | PASS |
| both-side branch/effect coverage ≥ 0.80 overall / ≥ 0.70 per archetype | **1.000** overall; per-arch 1.000/1.000/1.000/1.000 | PASS |
| LCS ≥ 0.90 | **1.000** | PASS |

Per-archetype × metric (all row-level): parse 1.000, evidence 1.000, coverage 1.000,
LCS 1.000, recall 1.000 on every archetype
(aggregate_gate n=136, conditional_write n=130, delete_after_capture n=128,
two_row_transfer n=106).

Supplemental minted-slice fidelity: **gold-exact full-IR string equality 1.000**
(500/500; SFT1 test90 was 0.874), exact predicate subfields / then-else effect sets
1.000, role status confusion matrix = identity (present 1.000, absent 1.000, no
false-absent anywhere). UNMEAS-on-value rows: none flipped to disagreement — the
whitelisted measurement gaps (documented in DATA_QC §4) remain measurement-side only.

### (b) canon80 — canonical regression (first 80 keys of extractions_v2, file order)

Base column recomputed with the same code (sanity gate: 80/80 field verdicts ==
`audit_expanded/per_sample.jsonl`); base numbers consistent with the adjudicated
`audit_expanded/field_metrics.json` lineage.

| gate metric | base@canon80 | sft@canon80 | vs base | sft gate verdict |
|---|---|---|---|---|
| parse (first-pass) | 1.000 (0.7625) | **1.000 (1.000)** | PASS (+0.238 fp) | PASS |
| evidence verbatim | 0.200 | **1.000** (980 spans, 0 bad) | PASS (+0.800) | PASS |
| critical precision | 0.406 | 0.550 | PASS (+0.144) | FAIL (<0.95) |
| critical recall (overall) | 0.325 | 0.550 | PASS (+0.225) | FAIL (<0.90) |
| recall per archetype | P1 .458 / P2 .042 / P3 .000 / P4 .875 | P1 .500 / **P2 .000** / P3 1.000 / P4 1.000 | P1/P3/P4 PASS, **P2 REGRESS** (−0.042) | FAIL |
| false-ABSENT | 0.338 | **0.000** | PASS (−0.338) | PASS |
| branch/effect coverage | 0.425 | **1.000** | PASS (+0.575) | PASS |
| LCS | 0.617 | **0.988** | PASS (+0.371) | PASS |

**sft@canon80: 5/8 gates pass; regression guardrail: 12/13 cells improved, 1 cell
regressed (P2 per-archetype recall, −1 row of 24).** Read against the SFT1 column
(sft1@canon80: parse 0.562, evidence 0.622, precision 0.316, recall 0.267, coverage
0.338, LCS 0.428, 0/8) the full-archetype mix fixed the SFT1 specialization collapse:
parse +0.438, evidence +0.378, coverage +0.662, P3 4/16→16/16 valid, P4 0/16→16/16
valid.

### (c) learning-curve spot check — SKIPPED per stage plan (not in this run).

### vs-base apples-to-apples (minted side, SFT1 historic columns; cross-dataset caveat)

These columns cross corpora (pilot mint gs 20260811, P1-only 90 rows vs production
mint gs 20260812, 4-archetype 500 rows) and are indicative only:

| metric | base@test90 (historic) | sft1@test90 (historic) | sft2@test500 |
|---|---|---|---|
| parse | 0.756 | 0.967 | **1.000** |
| evidence verbatim | 0.603 | 0.943 | **1.000** |
| precision | 0.949 | 1.000 | **1.000** |
| recall | 0.949 | 1.000 | **1.000** |
| false-ABSENT | 0.000 | 0.000 | **0.000** |
| coverage | 0.756 | 0.967 | **1.000** |
| LCS | 0.756 | 0.967 | **1.000** |
| gold-exact full IR | — | 0.874 | **1.000** |

The two open SFT1 gates (parse 0.967 single-family cluster; evidence 0.943 overlong
verbatim) are both closed at production scale — the SFT1-§8.4 mint-side preference
(≤12-word gold evidence clips) did its job: not a single overlong or non-verbatim
quote in 6,293 spans.

## 4. Per-archetype breakdowns

| archetype | n (test500) | parse | evidence | coverage | LCS | recall (pred_all) | canon80 recall (n) base → sft |
|---|---|---|---|---|---|---|---|
| conditional_write | 130 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.458 → 0.500 (24) |
| two_row_transfer | 106 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.042 → **0.000** (24) |
| aggregate_gate | 136 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 → 1.000 (16) |
| delete_after_capture | 128 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.875 → 1.000 (16) |

test500 per-schema max gap from 1.0: none (all 8 schemas at 1.0 on all row metrics,
including the thin strata crm J2 n=21 and inv J1 n=20).

## 5. Worst failure classes (with raw outputs)

There were ZERO failures on test500 (500/500 gold-exact) and zero parse/evidence/
false-ABSENT/coverage failures anywhere on canon80. The complete failure inventory is
the 40 canon80 predicate-attribute disagreements + 4 op-sequence elisions below —
only 3 classes exist (raw payloads in `worst_examples.json`).

**Class 1 — sealed-field attribute-anchor contradiction (P2, 24/24 canon P2 rows).**
SFT emits the text-surface unit word per the frozen minted D1 convention; the canon's
sealed-join truth anchors attribute on the program-param where-field tokens, so the
audit scores `pred_attribute:contradiction` even though op/value/polarity/direction/
branch-effects all agree. Example `instruction:1000f0a1e512aace`:
```
TEXT: "Ops note: move 10 attendees of 'Support Retreat' from the morning session to the
 afternoon session ... Guard: morning >= 5 after the move; afternoon <= capacity 28."
SFT predicate: attribute="attendees"  op=">="  value=5  polarity=positive
Audit truth (sealed join): attr tokens = guard where-fields; op membership {>=,<=} OK;
value numset {5,28} OK; polarity positive OK; direction/effects OK.
Verdict: contradiction on pred_attribute ONLY -> pred_all 0.
```
This is the exact D1 artifact SFT1 documented in the opposite direction (the audit's
sealed-field anchor contradicts the text's surface concept); SFT1 shipped the
minted-truth anchor for minted slices and kept the sealed anchor on canon for
comparability. The model now deterministically produces the minted D1 surface-form,
where the base extractor incidentally overlapped the sealed tokens on 2/24
rows (0.083→0.000 on pred_attribute; all_rows 0.042→0.000 = the −1-row regression
cell). Everything the gate measures as competence went P2 0.125→1.0.

**Class 2 — sealed-field attribute-anchor contradiction (P1, 12/24 canon P1 rows).**
Same convention boundary on conditional_write: e.g. `instruction:04e5a242f82a4722`:
```
TEXT: "Policy: If the on-hand quantity of SKU KB-7225 at warehouse 'main' is above 77,
 set its flag to 'markdown' ... otherwise, set flag to 'ok' ..."
SFT predicate: attribute="on-hand quantity"  op=">"  value=77  polarity=positive
Audit truth: sealed cond_field token set ('qty') -> pred_attribute contradiction;
op/value/polarity/effects all OK.
```
(The remaining 12/24 P1 rows: sealed tokens overlap the surface phrase → agreement.
P1 pred_attribute base 0.458 → sft 0.500 — improved, not regressed.)

**Class 3 — J2 policy-read node elision (4/24 canon P1 rows, J2 instructions).**
On canon J2 (policy-table lookup) instructions the SFT extractor merges the policy
read into the branch node instead of emitting the second read node:
e.g. `instruction:bf3dbe310b0bb39a`:
```
expected ops: [read, read, branch, verify]   (audit expected_seq of READ+POLICY)
SFT ops:       [read, branch, verify]        (LCS 0.75; overall canon80 LCS 0.9875)
branch evidence: "If the on-hand quantity of SKU NC-5627 ... is above the overstock
 limit for category 'hardware' in the inv_policies table (column overstock_limit), ..."
```
4 rows × LCS 0.75 = the entire 0.0125 LCS deficit. Cause chain: on minted data the
policy read renders only in J2 cards (the mint's kind-aware expected-ops rule), so
the model learned "policy lookup stays inside the branch" for instruction-shaped
text; the audit's canon `expected_seq` expects the policy read unconditionally.

No class beyond these three exists; on the production distribution they do not
manifest at all (test500 covers 65 held-out P1 J2 rows across cards+instructions with
policy-read ops at LCS 1.000 — the minted J2 convention includes the policy read in
cards, which the model reproduces exactly).

## 6. Measurement integrity

- Sanity gate 1: all 500 test rows rebuilt from the frozen mint plan (200 families,
  generator read-only); signature parity + instruction-text byte parity + 6,293
  evidence spans re-sliced exactly — 0 problems.
- Sanity gate 2: gold audit self-check on all 500 test rows — only whitelisted
  measurement gaps (cal_finalize|scope 77, crm_escalate|pred_value+pred_all 15+15,
  ticket_gate_close|scope 15, inv_overstock|pred_value+pred_all 9+9), matching the
  frozen DATA_QC §4 classes; non-whitelisted problems = 0.
- Sanity gate 3: recomputed base@canon80 field verdicts ==
  `audit_expanded/per_sample.jsonl` for all 80 keys.
- Discipline: labels/cells/families never in model input (training view = text+gold
  only, provenance sidecars never serialized); test500/canon never trained; splits
  from mint_receipt (no re-splitting); no threshold touched after any metric run;
  seeds 42 (train seed, data_seed, vLLM seed); one training job total; decode params
  logged here and in eval.log; GPUs 5–7 untouched.

## 7. Go / no-go

**(i) Frozen comparator S2 run: GO.** The extraction gates this lane was built to
satisfy are green across the board: on the held-out production distribution the SFT
extractor reproduces the gold IR byte-for-byte on 500/500 held-out-family texts
(span-level faithful, all archetypes/schemas/strata, zero false-absent). The S2
comparator freezes its rules against exactly this surface — there is no extraction
uncertainty left on-distribution to confound the comparator's measurement.
One carry-forward the S2 protocol must pin: the **attribute-anchor convention**.
Any comparator evaluation on sealed-canon texts will re-trigger Class 1/2 above
(model emits the minted D1 surface form; the sealed audit anchors on program-param
field tokens). Freeze the minted-truth anchor (gold-IR attribute tokens) for any
canon-side comparator measurement, or Class 1 will masquerade as a −4.2pp P2 recall
regression on n=24.

**(ii) More data at current gates: NO-GO (utility exhausted).** Every gate is at
residual-zero on the held-out slice; val loss is at 6.9e-5; there is no measurable
headroom for additional minted data to buy. The only open defects are measurement-
convention artifacts on a corpus this lane deliberately keeps frozen (canon80), and
they affect 1-of-13 regression cells on n=24. Investing next compute in the S2
comparator — and optionally the pre-frozen LC300/LC1000 learning-curve runs if a
saturation-vs-size claim is wanted for the paper — dominates any second data wave.
