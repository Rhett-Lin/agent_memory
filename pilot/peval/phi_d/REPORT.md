# φ+d S0+S1 pipeline report (extraction + decomposed judge)

Date: 2026-08-10. Scope per `pilot/peval/PHI_D_EVALUATOR_PLAN.md` §4/§8 and `SPEC.md`:
full-run φ-extraction over all unique texts, decomposed-judge baseline over all 640
pairs, scoring vs registered baselines. Labels were used **eval-only**, inside
`score_baselines.py` exclusively. No comparator, no threshold tuning, all files under
`pilot/peval/phi_d/`.

---

## 0. TL;DR / verdict

- **Decomposed judge (S1 baseline): GO.** 640/640 judged, 98.75 % valid after the
  frozen single-retry policy. **AUC overall 0.597, S=1 0.664** — clearly above the
  holistic intent judge (~0.508 overall) and above `sim_embed` on S=1 (0.664 vs 0.529);
  above P̂-v1-LOAO on S=1 (0.664 vs 0.590), below everything P̂-v1-family-CV
  (0.966/0.935). This is exactly the ablation-floor role plan §4 assigns it.
- **IR φ-extraction: NO-GO at scale.** Only **185/532 (34.8 %)** unique texts yield a
  valid IR under the frozen prompt family; the one-repair retry rescued **0/347**.
  The 8/8 smoke was not predictive: failure scales with text diversity, not format.
- **Comparator stage (S2): BLOCKED, not refuted.** Pair-level both-side IR availability
  is the comparator ceiling; with ~1/3 of texts valid, per-cell coverage would be far
  below any admissible operating point (see §5). Fix extraction *first*; the judge
  numbers prove the evaluation harness + scoring are ready.

## 1. Artifacts and provenance

Canonical outputs were produced with frozen prompts, temp 0, seed 42, one JSON-repair
retry, failures recorded (`valid=false` + `error_class`) and never dropped:

| artifact | rows | prompt_sha | valid | producing instance (pinned) |
|---|---|---|---|---|
| `out/extractions.jsonl` | 532 (160 instr + 372 memory; unique-by-text) | `5200e56eee95…` | 185 (34.8 %) | `extract_phi_run5200.py` |
| `out/judgments.jsonl` | 640 | `47669c03df56…` | 632 (98.75 %) | `decomposed_judge_run4766.py` |
| `out/summary.json` / `out/examples.jsonl` | — | — | — | `score_baselines.py` (only label-reading script) |

- Run receipts: `out/run_receipt_s2.json` (+ `out/frozen/` snapshots:
  `summary_run1_score.json`, `summary_final.json`, `examples_*.jsonl`).
- `*_run5200.py` / `*_run4766.py` are byte-pinned instances of the frozen prompt
  surfaces whose module-level `prompt_sha` recomputes to the row shas above; the
  sibling `extract_phi.py` / `decomposed_judge.py` filenames were concurrently edited
  by a second agent during the run window (see §8) and must not be assumed to match.
- Dev artifacts (never scored): `out/dev_smoke/` — incl. `extractions_v3_partial.jsonl`
  (448 rows, earlier abandoned full attempt of the v3 prompt, 38 % valid) and
  `judgments_05e4dev_rerunpending.jsonl` (640 rows of an unvalidated judge prompt
  variant, quarantined; 6/8 verdict agreement with the frozen judge on overlap keys,
  flips only on match↔unknown boundary pairs).

## 2. Judge results (scoring by `score_baselines.py`, fixed mapping match→1 / unknown→0.5 / contradict→0, invalid→0.5 kept)

| metric | φ+d decomposed judge (this run) | sim_embed | holistic STITCH judge | P̂ v1 family-CV | P̂ v1 LOAO |
|---|---|---|---|---|---|
| AUC overall (all 640) | **0.597** | 0.606 (recomputed 0.6055) | ~0.508 | 0.966 | 0.636 |
| AUC S=1 (A01 vs A11) | **0.664** | 0.529 (recomputed 0.5288) | — | 0.935 | 0.590 |
| AUC overall, covered-only | 0.583 | — | — | — | — |
| AUC S=1, covered-only | 0.671 | — | — | — | — |
| coverage (non-abstain) | 83.3 % (533/640) | — | — | — | — |
| accuracy, covered | 0.593 | — | — | — | — |
| accuracy, abstain-as-error | 0.564 | — | — | — | — |
| invalid rate | 1.25 % (8/640: 7 schema + 1 parse) | — | — | — | — |

Verdict distribution: contradict 430 (67.2 %), match 103 (16.1 %), unknown 99 (15.5 %),
invalid 8. Per-cell verdict rates:

| cell | match | contradict | unknown | invalid | reading |
|---|---|---|---|---|---|
| A00 (P=0,S=0) | 0.0 % | **93.8 %** | 2.5 % | 3.8 % | easy contradictions: caught |
| A01 (P=0,S=1) | **19.4 %** | 58.8 % | 21.9 % | 0.0 % | near-misses: 19 % false-accepted |
| A10 (P=1,S=0) | 0.0 % | 85.0 % | 15.0 % | 0.0 % | cross-surface equivalents killed |
| A11 (P=1,S=1) | 45.0 % | 31.3 % | 22.5 % | 1.3 % | true transfer: only 45 % retained |

Interpretation: the judge has a strong **contradiction prior** (2/3 of all pairs).
That is the right prior for A00/A01 (灾难门 cares about A01 acceptance ≤ 0.10 — the
judge's 19.4 % false-match on A01 is too high for admission, but this is the *baseline*,
not the comparator), and the wrong prior for A10/A11 (85 %/31 % contradiction of true
equivalents — exactly the "只会抓明示 near-miss，却杀掉跨域真等价" pattern plan §5
warns about; the frozen comparator must beat this asymmetrically on A10/A11).

## 3. Extraction stats (532 unique texts; frozen prompt `5200e56e…`)

- valid **185/532 = 34.8 %**; failure 65.2 %; instructions 58/160 (36.2 %), memory
  texts 127/372 (34.1 %) — evenly broken across text kinds.
- error classes (final, after one retry): `schema_validation_error` **272**
  (dominant detail: `roles keys != canonical 6` — model invents ad-hoc role/DSL
  vocabularies), `json_parse_error` **75** (mostly unbalanced quotes/brackets inside
  long evidence strings). `finish_reason=length` on 1/532.
- **retry rescue rate 0/347**: every row that failed first pass failed the repair pass
  too (deterministic decoding replays the same drift). First-pass errors:
  226 parse + 121 schema; after repair: 75 parse + 272 schema — repairs converted
  parse failures *into* schema failures, not into valid IRs.
- Cross-version stability: vs the abandoned v3 dev partial (same prompt family,
  `4f358963…`, 448 overlapping keys), the valid-mask agreement is **414/448 (92 %)**:
  failures are a property of prompt *design*, not of the byte-level variant.
- On the 185 valid IRs: roles present 301 / absent 809 / **unknown 0**;
  nodes present 996 / unknown 9; predicate fields present 185–187, unknown ≤2;
  termination present 185 / unknown 0. Evidence-span presence among `present`
  entries: 99.4–100 % per field. Node ops: write 241, read 203, verify 199,
  branch 187, finish 127, aggregate 48 (no list-ops survived).
  → **UNKNOWN is never used** (0.4 % of statuses); ABSENT is asserted freely.
  For the comparator this inverts one design assumption of the IR: UNKNOWN-as-
  abstain-fuel does not materialize from the extractor; over-claimed ABSENT will
  manufacture false contradiction evidence unless the comparator treats
  ABSENT-on-incomplete-IRs conservatively.

## 4. Top 3 extraction failure classes (evidence from `out/dev_smoke/extractions_v3_partial.jsonl`, same-family canonical distribution)

1. **Schema drift into ad-hoc DSLs** (272/347 final failures). The model abandons the
   frozen 6-role skeleton mid-document and invents task-shaped vocabularies:
   `"roles":{"from_warehouse":"east","to_warehouse":"west"}` /
   `{"type":"guard","condition":"('east' >= 0) and ('west' <= 400)"}` /
   `"termination":{"actions":["read","check","update","verify"]}` — validator:
   `roles keys != canonical 6`. Failed raws are *shorter* (mean 923 chars) than valid
   ones (mean 2268): drift outputs are terse paraphrase schemas.
2. **JSON syntax breaks inside long evidence strings** (75/347): unbalanced quotes /
   missing commas at evidence boundaries, e.g. `Expecting ',' delimiter: line 1
   column 533`. Concentrated in memory texts with nested quotes (`'escalated'`,
   multi-line episode structure).
3. **Zero-rescue repair loop** (347 retries, 0 conversions): under temp-0 the repair
   prompt replays the same drift; 121 first-pass schema errors stayed schema errors,
   and 151 of 226 first-pass parse errors *became* schema errors on repair. A single
   same-prompt retry is structurally useless against design-level drift — it only
   fixes stochastic noise that never occurs at temp 0.

## 5. Viability verdict for the comparator stage (S2)

**Conditional NO-GO until extraction is fixed; judge baseline stands.**

- Judge: production-ready as the plan-§4 ablation floor. Its numbers above are the
  reference the comparator must beat, especially the A10/A11 retention side
  (judge retains 45 % of A11, kills 85 % of A10).
- Comparator ceiling today (exact, `out/frozen/extractions_frozen5200.jsonl` ×
  `pairs.jsonl` text-sha join): **both-side valid IR per pair is 18.1 % (116/640)
  overall — A00 13.1 %, A01 23.8 %, A10 16.9 %, A11 18.8 %**. Even a perfect
  comparator that accepted every decidable A11 pair would retain ≤ 18.8 % of A11,
  against the frozen 准入门 floor of ≥ 50 % — ~82 % forced abstain under the frozen
  failure→abstain rule. No admissible operating point exists before the extraction
  fix.
- Recommended path, in order:
  1. **Replace prompt-anchored extraction with grammar-constrained decoding that runs
     in this environment.** Guided JSON was attempted twice and crashed inside vLLM
     0.6.6's outlines path (`TokenizerInfo.from_huggingface` AttributeError at first
     generate call — both backends tried); needs an outlines/vLLM version bump in
     the causalmemagent env, then re-smoke. The frozen `IR_GUIDE_SCHEMA` /
     `JUDGE_GUIDE_SCHEMA` definitions already exist in `common.py`.
  2. If staying prompt-only: add **negative exemplars** (the two observed ad-hoc DSL
     shapes) + emit the role skeleton on the prefill side (prefill through all six
     role keys, not just the first), and make the repair prompt echo the validator's
     specific complaint (the 0/347 evidence says the current one can't).
  3. Only then freeze the comparator; evaluate per plan §5 on the pairs whose both
     sides extract (report coverage per cell explicitly, per the frozen protocol).
- Do **not** compensate at the comparator for extraction failure patterns; do not
  reuse the judge's per-field outputs to iterate the comparator (plan §4 wall).

## 6. Reproducibility

```
cd pilot/peval/phi_d
PY=/work1/zixuan/envs/conda_envs/causalmemagent/bin/python
export CUDA_VISIBLE_DEVICES=4 HF_HOME=/work1/zixuan/cache/huggingface HF_HUB_OFFLINE=1
$PY extract_phi_run5200.py       # -> out/extractions.jsonl (532 rows, sha 5200e56e…)
$PY decomposed_judge_run4766.py  # -> out/judgments.jsonl   (640 rows, sha 47669c03…)
$PY score_baselines.py           # labels read HERE only -> out/summary.json, out/examples.jsonl
```

Model: Qwen2.5-7B-Instruct rev `a09a3545…`, fp16, vLLM 0.6.6.post1, gpu_mem 0.85,
max_model_len 4096, seed 42. Decode: temp 0 / top_p 1 / seed 42; extraction
max_tokens 768, judge 512. Run logs: `out/run_extract_full2.log`,
`out/run_judge_full3.log`, `out/run_score.log` (+ `out/frozen/*` snapshots and
`out/run_extract_frozen5200.log` / `out/run_judge_frozen4766.log` from the
pin-verified re-issuance of the same artifacts).

## 7. Honest-notes (process disclosure)

- Two agents worked this directory concurrently during the run window (shared harness
  session). All scored artifacts above were (re)produced from byte-pinned prompt
  instances whose `prompt_sha` recomputes to the row shas; provenance is per-row, and
  dev/quarantined states are kept under `out/dev_smoke/` with names, never mixed into
  canonical outputs. `SPEC.md` and the sibling script filenames may reflect the other
  agent's mid-iteration state; the `*_run5200.py` / `*_run4766.py` instances +
  `out/frozen/` snapshots are the durable record of THIS report.
- The v3 prefill-era prompt smoke (8/8) genuinely passed but did not predict full-run
  validity — smoke-on-first-8-texts is not a scale proxy; future smokes should sample
  across the worklist, not its head.
- LATE UPDATE (2026-08-10 ~03:20): the concurrent agent appears to have found a
  working guided-decoding configuration (`OUTLINES_CACHE_DIR=/work1/zixuan/cache/outlines`,
  one-time outlines FSM build ~10 min; see `SPEC.md` §0 row "code freeze" +
  `out/freeze_v0.sha256`, and its `*_GUIDE_SCHEMA` in the current `common.py`). A GPU-4
  job consistent with a guided full run was in progress at report time. IF its guided
  extraction lands with high first-pass validity, it directly implements fix #1 of §5
  and supersedes the NO-GO for the comparator on extraction grounds — re-audit its
  canonical outputs per-row `prompt_sha` before adopting them; dev versions of both
  tracks are preserved under `out/dev_smoke/`.
