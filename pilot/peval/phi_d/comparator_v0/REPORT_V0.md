# φ+d comparator v0 — lane A pre-SFT baseline (REPORT-ONLY)

**Scope.** Single frozen deterministic run of the adjudicated S2 comparator over all
640 pairs of `pilot/peval/pairs.jsonl`, IRs from `out/extractions_v2.jsonl`
(532/532 valid, both-side-valid coverage 640/640 = 100% in every cell). Pure stdlib,
CPU-only, no training, no labels in comparator inputs. This artifact is the **legal
pre-SFT baseline**, not the S2 release.

**Veto-field eligibility at run time.** `pilot/peval/phi_d/audit_expanded/field_metrics.json`
**existed at run time** (sha256 `c4aef380…`), so the adjudicated dual-mode fallback is
NOT triggered — the report runs one audit-gated mode, no mode contrast, no winner
picking. Demotions applied per the audit veto rule:

| audit field | veto_eligibility | comparator effect |
|---|---|---|
| pred_op | positive-only / soft (unknown-if-absent) | op-relation contradictions kept where both predicates populated; absence → unknown |
| pred_value, pred_polarity, pred_all, pred_attribute, branch_effects | excluded | threshold-literal + effect-mapping disagreements → unknown (never contradiction); polarity metadata-only |
| direction, scope, archive_capture | excluded | reversal/scope/order violations → unknown (soft) |
| roles_required, termination | excluded | omissions/incompatibilities → unknown (soft) |
| branch_presence | (unscored, default hard) | required-branch-missing under complete(memory) stays a backbone veto |

Not in the audit table → kept hard per adjudicated semantics: required-op-missing under
complete(memory), extra-effectful-op, conflicting resolved action target
(TARGET_CONFLICT), explicit aggregate-function mismatch (AGG_FN_MISMATCH).

**Kill-condition outcome: LANE A DEMOTES to baseline-only, no rule iteration.** All
four adjudicated gates fail (details below). Per discipline, no rule iteration was or
will be performed from these outcomes.

## 1. Verdict mix and per-cell admission/retention

Verdict mix over 640 pairs: **match 2, contradict 218, unknown 420** (directional
coverage 34.4%; unknown kept in all denominators).

| cell | n | match | contradict | unknown | admission/retention (comparator) | judge (S1) | sim_embed (mean) |
|---|---|---|---|---|---|---|---|
| A00 (P=0,S=0) | 160 | 0 | 60 | 100 | **0.312** | 0.019 | 0.620 |
| A01 (P=0,S=1) | 160 | 1 | 56 | 103 | **0.328** | 0.397 | 0.853 |
| A10 (P=1,S=0) | 160 | 0 | 50 | 110 | **0.344** | 0.059 | 0.691 |
| A11 (P=1,S=1) | 160 | 1 | 52 | 107 | **0.341** | 0.831 | 0.858 |

Per-archetype admission/retention (comparator):

| archetype | A00 | A01 | A10 | A11 |
|---|---|---|---|---|
| aggregate_gate | 0.263 | 0.300 | 0.375 | 0.325 |
| conditional_write | 0.362 | 0.263 | 0.338 | 0.375 |
| delete_after_capture | 0.312 | 0.375 | 0.325 | 0.325 |
| two_row_transfer | 0.312 | 0.375 | 0.338 | 0.338 |

## 2. AUCs (labels read only here; fixed map match=1, unknown=0.5, contradict=0)

| scorer | overall | S=1 (A01 vs A11) | family-40 macro overall | family-40 macro S=1 | LOAO-macro S=1 |
|---|---|---|---|---|---|
| **comparator_v0** | **0.522** | **0.512** | 0.522 | 0.512 | 0.512 |
| sim_embed (pairs cols) | 0.606 | 0.529 | 0.612 | 0.598 | 0.574 |
| judge frozen (S1) | 0.630 | 0.740 | 0.630 | 0.738 | 0.733 |

Per-archetype comparator AUCs (S=1): aggregate_gate 0.525, conditional_write 0.607,
delete_after_capture 0.454, two_row_transfer 0.463. Leave-one-archetype-out pooled
S=1 AUCs in `score_summary.json`; all 40 family folds had both classes (none skipped).

## 3. Kill conditions (adjudicated thresholds) — ALL FAIL

- retention(A10) < 0.50: **0.344 overall** and every archetype (0.325–0.375) — 5 violations
- retention(A11) < 0.50: **0.341 overall** and every archetype (0.325–0.375) — 5 violations
- archetype S=1 AUC < 0.60: aggregate_gate 0.525, delete_after_capture 0.454,
  two_row_transfer 0.463 — 3 violations (conditional_write 0.607 passes)
- admission(A01) > 0.10: **0.328** — 1 violation

**Verdict: DEMOTE lane A to baseline-only.**

## 4. Verdict reason histogram (machine-readable trace in verdicts.jsonl)

Reason events by level: contradict 532, unknown 820, note 1485, benign 416.

Top contradiction classes:
1. `EXTRA_EFFECTFUL_OP` — 347/532 (set 129, insert 89, branch 69, delete 60): the
   dominant veto; fires when one side's IR carries writes/branches the other lacks.
2. `REQ_OP_MISSING_UNDER_COMPLETE` — 82 (write/aggregate/read/branch; absence under
   a trusted memory certificate).
3. `PRED_OP_MISMATCH` — 48 (non-complemented operator differences; positive-only
   pred_op channel). Then TARGET_CONFLICT 31, AGG_FN_MISMATCH 16.

Top unknown classes:
1. `VACUOUS_MEMORY` 248 / `VACUOUS_INSTRUCTION` 112 — 360/820: one side's IR has no
   present node at all (degenerate extraction; certificate memory-complete rate is
   24.5%, instruction 21.3%).
2. `ROLE_OMITTED_SOFT:*` — 165 (policy_row/audit_sink/source/…; demoted roles
   channel) and `REQ_OP_MISSING_INCOMPLETE:*` — 151 (absence with untrusted memory
   certificate).
3. `PRED_EFFECT_MISMATCH` (soft, 83) + `PRED_COMPLEMENT_NO_SWAP` (soft, 24) —
   demoted branch-effects channel. (`PRED_THRESHOLD_NO_ANCHOR` — 6.)

Certificate check-failure counts (memory side, n=640): connected 308,
no-unknown-in-used-fields 307, evidence-verbatim 158, branch-populated 45.
Instruction side: evidence-verbatim 380, connected 136, no-unknown 108,
branch-populated 84.

## 5. Diagnosis (for the record; NO comparator changes made)

- The surviving hard vetoes are **structural, not semantic**: they fire on
  program-shape asymmetry between two lossy IRs, at near-equal rates on A01 (0.328)
  and A11 (0.341). Hence AUC_all ≈ AUC_S1 ≈ 0.51 — chance level.
- The channels that could separate near-misses from true equivalents (pred_value
  literals, branch-effect payloads, scope/direction/capture-order signatures) are
  exactly the channels the faithfulness audit demoted to soft/unknown — the
  deterministic lane cannot legally use them with this IR quality.
- 56% of pairs (360/640) are decided by extraction degeneracy (vacuous IRs),
  not by comparison.

## 6. Bug-fix log (discipline: fixes only from unit-test / syntax evidence, never
from 640-pair outcomes)

1. **SyntaxError**: malformed generator in extras action-classification
   (`neff = _norm_effect(...) for e in eff]`). Detected at import. Fixed by
   parenthesizing. Before: module unimportable; after: compiles.
2. **`_precedes` direction inverted** (comparator): searched `early`'s ancestors for
   `late` instead of `late`'s ancestors for `early`. Detected by
   test_12 (capture-after-delete order analysis never fired). Before: ordering
   component dead code on dependency chains; after: correct transitive-depends
   direction. End-to-end test_12 passes.
3. **Predicate channel gating** (comparator): effect-mapping mismatches were gated
   on the pred_op channel; audit semantics place them on the branch_effects channel
   (excluded → unknown). Detected by test_03 (complement-without-swap fired
   `contradict` under the audit-gated config instead of `unknown`). Before:
   `rel_code` level keyed to `op_veto`; after: keyed to `fx_veto`; literal-valued
   effect mapping kept always-on (without it swap/no-swap is invisible and the
   complementation rule is vacuous).
4. **Test-construction fix** (test data, not comparator): synthetic texts must
   contain predicate subfield evidence spans verbatim (the certificate's
   evidence-verbatim check failed on composed texts). `ir_from` now includes
   predicate subfield evidences. Detected by test_06/test_17 setUp asserts.

18/18 synthetic unit tests pass (hand-written mini-IRs, no benchmark texts):
operator complementation ±swap, eq/ne swap, extra-effectful, extra-benign-read,
required-missing under complete vs incomplete, invalid side, src/dest reversal
(audit-soft and hard), threshold anchor/no-anchor, capture-order, AGG_FN mismatch,
polarity-metadata, scope-soft, role-omission-soft, op-mismatch.

## 7. What the SFT baseline comparison needs from this artifact

- `verdicts.jsonl` + `score_summary.json` are the legal pre-SFT baseline row:
  AUC 0.522/0.512, per-cell table above, verdict reason traces per pair.
- Score any SFT variant through **this exact `score.py` protocol** (same verdict→score
  map, all 640 in denominators, same kill gates) for comparability; report deltas vs
  this row, and vs judge/sim_embed already tabulated here.
- The baseline's failure decomposition defines what SFT must beat: (1) vacuous-IR
  abstains (extraction degeneracy, 360/640 pair-decisions), (2) structure-only
  vetoes with no cell separation, (3) demoted channels that require learned binding
  (cross-domain parameter anchoring, effect-payload equivalence) the deterministic
  lane may not approximate.
- `run_receipt_v0.json` pins code/input shas for the frozen run; re-running
  `run_comparator.py` after any comparator change is a NEW run and must be logged
  as such (this artifact stays untouched).

## 8. Provenance

- Inputs: pairs.jsonl sha256 `aa33ea61…44bf`; extractions_v2.jsonl sha256
  `9e66c3db…`; audit field_metrics sha256 `c4aef380…`.
- Code shas of the frozen run in `run_receipt_v0.json`; verdicts.jsonl written once,
  640 rows, `n_extraction_missing=0`.
- Eligibility consumed from the audit table (single audit-gated mode;
  `require_branch_completeness=True` in the certificate).
- CPU-only, deterministic, no RNG; unit tests precede the run; no git mutations.
