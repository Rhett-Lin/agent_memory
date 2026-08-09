# P-evaluator (pilot/peval)

Engineering artifact that estimates the **program-match probability P̂(instruction, memory)**
between a candidate agent memory and a target task instruction, to be used as an
**admission gate** on retrieved memories (surface retrieval gets you S; P̂ aims to catch
program mismatches such as the near-miss A01 flips). CPU-only; no new rollouts; read-only
use of existing artifacts. All scripts are deterministic with fixed seed 42.

## Files

| file | what it does |
|---|---|
| `build_pairs.py` | builds `pairs.jsonl` (640 labeled pairs) with validations |
| `p_evaluator.py` | trains/evaluates the P̂ classifier; writes `P_EVAL_RESULTS.json`, `pair_scores.jsonl` |
| `gate_eval.py` | offline admission-policy evaluation on existing pilot rollouts; writes `GATE_EVAL.json` |
| `pairs.jsonl` | one row per (memory_id, family_idx, target_sibling): cell, P, S, instruction, memory_text, sim_tf, sim_embed, archetype, domain |
| `P_EVAL_RESULTS.json` | AUC metrics: overall / S=1 subset, family-CV, archetype-holdout, domain-holdout, baselines |
| `pair_scores.jsonl` | per-pair P̂ scores (full fit + family/archetype/domain out-of-fold) |
| `GATE_EVAL.json` | per-policy expected success, uplift vs never-admit, acceptance rates (keyed `by_model`) |

## Reproduce

```bash
PY=/work1/zixuan/envs/conda_envs/causalmemagent/bin/python
cd /work1/zixuan/projects/agent_memory/pilot/peval
$PY build_pairs.py                 #  ~5 s
$PY p_evaluator.py                 # ~7 min (40-fold family CV + 4 + 4 holdouts)
$PY gate_eval.py --model qwen7b    # ~10 s
$PY gate_eval.py --model qwen3b    # ~10 s (secondary model, same JSON under by_model)
```

## Mapping assumptions (verified in code, asserted on failure)

- **Pair label source.** `sealed/sim_report.csv` A-rows (640 = 40 families × 4 target
  siblings × 4 cells). `P=1 ⟺ cell ∈ {A10,A11}`; `S=1 ⟺ cell ∈ {A01,A11}` (checked).
  Q rows carry no labels and are ignored.
- **Instruction mapping.** The target task of pair (family_idx, target_sibling) is the
  benchmark task with `kind='sibling'` for that (family, sibling) in
  `sealed/tasks_sealed.jsonl`. Verified: exactly **one distinct instruction per
  (family, sibling) across the 4 seeds** (640 sibling tasks → 160 unique instructions);
  seeds vary the DB state/distractors, not the instruction text. Each sealed instruction
  is string-equal to its public task file (`public_view/tasks/<task_id>.json`, matched by
  task_id), so instructions are publicly observable.
- **Memory text.** `public_view/memories/<memory_id>.json → text`; all 640 A-cell memory
  files exist and are non-empty. Identity of `memory_id` inside file asserted.
- **archetype/domain.** `sealed/families.jsonl` keyed by family_idx (4 archetypes × 10,
  4 domains × 10). `nm_kind` is 1:1 with archetype (conditional_write→flip_polarity,
  two_row_transfer→reverse_direction, aggregate_gate→wrong_child_set,
  delete_after_capture→skip_archive), so **leave-one-archetype-out ≡ transfer to an
  unseen near-miss kind**.
- **Gate simulation.** Candidates for instance (family, sibling, seed) = the 4 A-cell
  memories of (family, sibling). Retriever = top-1 by `sim_embed`
  (tie-break `sim_tf` desc, `memory_id` asc). Abstain = N-arm (no-memory) rollout outcome
  for the same (family, sibling, seed). Rollouts:
  `outputs/agent_memory/pilot/rollouts_{qwen7b,qwen3b}_shard*-of-005.jsonl`
  (per model: 6 cells {N,Q,A00,A01,A10,A11} × 160 (family,sibling) × 4 seeds = 3840 rows,
  verified complete; **0 instances dropped**).
- **Leakage guardrails.** Features come from instruction + memory text only, plus
  sim_tf/sim_embed which are functions of the texts (recomputable at deployment).
  TF-IDF vocabularies, idf, and the hand-feature scaler are refit inside every CV fold.
  Gate simulation scores candidates with **family-CV out-of-fold P̂** (`phat_oof_family`),
  so no evaluated family was in its scorer's training set.

## Model

LogisticRegression (C=1.0, class_weight='balanced', solver=liblinear, tol=1e-2,
random_state=42) on:

- word TF-IDF (1–2 grams) and char_wb TF-IDF (3–5 grams) **pair features**:
  elementwise product `u∘v` and `|u−v|` of the L2-normalized vectors of the two sides
  (shared vocabulary, fit on train folds only);
- 15 hand features: sim_tf, sim_embed, token jaccard/containment, number containment,
  comparator-polarity agreement ("at or below/at least/above/fewer than/…" → {LE,LT,GE,GT}
  classes; containment/conflict/missing), direction-word containment
  (from/to/origin/target/…), action-verb containment, archive/delete instr-only flags —
  i.e., features pointed at the four near-miss flip kinds.

liblinear@tol=1e-2 reproduces lbfgs@max_iter=3000 with Spearman 1.0000 on a smoke fold
and keeps total runtime ≈ 7 min (< 10 min budget).

## Headline results

### P̂ discrimination (AUC; overall / S=1 subset = A11-vs-A01 deployment-critical cut)

Baselines reproduced exactly on all 640 pairs: sim_tf 0.608/0.595, sim_embed 0.606/0.529.

| scheme | P̂ overall | P̂ S=1 | sim_tf | sim_embed |
|---|---|---|---|---|
| in-sample (upper bound, labeled) | 0.988 | 0.958 | 0.608/0.595 | 0.606/0.529 |
| **GroupKFold by family (40)** | **0.966** | **0.935** | 0.608/0.595 | 0.606/0.529 |
| leave-one-domain-out | 0.793 | 0.739 | 0.608/0.595 | 0.606/0.529 |
| leave-one-archetype-out | **0.636** | **0.590** | 0.608/0.595 | 0.606/0.529 |

Per-held-out archetype (S=1): conditional_write 0.587 (overall **0.408, below chance**),
aggregate_gate 0.646, two_row_transfer 0.569, delete_after_capture 0.787.
Per-held-out domain (S=1): ticket 0.888, crm 0.749, calendar 0.706, inventory 0.598.

**Read:** P̂ crushes the sim baselines when the near-miss *kind* is in-distribution
(new families of a seen flip type: S=1 AUC 0.935). It collapses to baseline on an
unseen flip type (S=1 AUC 0.590 ≈ sim_tf 0.595), and can actively misrank
(conditional_write held out → 0.408 overall).

### Offline gate evaluation (qwen7b pilot rollouts; 640 instances, 0 dropped)

Retriever top-1 is always an S=1 cell: A11 for 380/640 instances, A01 for 260/640 —
median |sim_embed(A11)−sim_embed(A01)| per group is only 0.0032, so retrieval effectively
coin-flips the near-miss and the gate is the only line of defense.

| policy | expected success | uplift vs never (pp) [95% CI] | accept rate | A01 accept |
|---|---|---|---|---|
| never_admit (N) | 0.5469 | 0.0 | 0.000 | 0.00 |
| always_admit | 0.5984 | +5.16 [1.09, 9.06] | 1.000 | 1.00 |
| S-gate sim_embed≥0.80 | 0.6031 | +5.63 [1.88, 9.38] | 0.919 | 0.86 |
| P̂-gate ≥0.5 | 0.6172 | +7.03 [4.06, 10.00] | 0.681 | 0.31 |
| **P̂-gate ≥0.6** | **0.6328** | **+8.59 [5.62, 11.41]** | 0.575 | **0.17** |
| P̂-gate ≥0.7 | 0.6312 | +8.44 [5.94, 10.94] | 0.419 | 0.09 |
| oracle-P (ceiling) | 0.6281 | +8.13 [5.47, 10.79] | 0.594 | 0.00 |

qwen3b (secondary): memory injection is weak for the small model, so the gate has little
to work with — oracle-P +1.25pp (CI includes 0), P̂-gates between −1.25 and +0.16pp;
A01 acceptance rates identical to qwen7b at equal thresholds (scores are model-agnostic).

## Caveats (read before using these numbers)

1. **Upper-bound AUC vs deployment.** In this benchmark the instruction states the policy
   nearly verbatim (the flipped comparator appears in the text, e.g. "above 5" vs
   "at or below"), so a text classifier is close to reading the answer off the surface.
   Real deployments with implicit task language will do worse; the family-CV 0.935 is not
   a deployment guarantee.
2. **No transfer to unseen near-miss kinds.** nm_kind↔archetype is 1:1, and
   leave-one-archetype-out drops to sim-baseline level (S=1 0.590; overall on
   conditional_write even 0.408 < 0.5). The gate only protects against flip mechanisms
   it has seen labeled examples of; coverage of new memory-generation failure modes must
   be re-established before trusting P̂ on them.
3. **Small grounded sample + pilot effect sizes.** 640 labeled pairs / 640 gate instances;
   gate uses OOF scores but thresholds and features were selected on the same labeled set
   (mild selection bias — treat 0.5–0.7 thresholds as pilot-tuned). On qwen7b the A01
   memory was *not* harmful on average (+3.1pp vs N cell-level), so "harmful-flip"
   rejection mostly buys variance reduction there (it is genuinely harmful on qwen3b,
   −5.8pp). P̂-gate@0.6 slightly *exceeding* oracle (+8.59 vs +8.13pp) is sampling noise
   from selective A11 rejection — bootstrap CIs overlap, and it should not be read as a
   causal improvement over an oracle.
