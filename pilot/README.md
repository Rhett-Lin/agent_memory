# CausalMemBench Mini-Pilot (Round 1)

Implements `SPEC.md`: Stage A causal-inference pilot for agent memory on a
single RelationalOps (SQLite) environment — 40 latent program families,
6 cells (A00/A01/A10/A11/N/Q), fixed-injection 200–300-token procedural
memory cards, evaluator-only sealed oracle, vLLM ReAct harness, four core
analysis figures.

## Layout

```
pilot/
  SPEC.md                 # authoritative spec (acceptance criteria in §8)
  program_dsl.py          # partial-order program spec + 4 archetypes + oracle walker
  env_relationalops.py    # SQLite env, tool API, terminal predicates
  generate_families.py    # family/sibling/near-miss/memory generator (sealed oracle split)
  harness.py              # vLLM offline ReAct rollout loop (fixed memory injection)
  run_pilot.py            # experiment grid orchestrator (shard / resume / retry / dry-run)
  analyze.py              # four core figures + cluster bootstrap + TOST + tables
  configs/pilot.yaml      # all hyperparameters
  tests/smoke.py          # end-to-end smoke (SPEC §8 acceptance)
  README.md
```

Key directories (hard-coded via `configs/pilot.yaml`, all under `/work1`):

- data:    `/work1/zixuan/data/agent_memory/{public_view,sealed}`
- outputs: `/work1/zixuan/outputs/agent_memory/pilot/`
- logs:    `/work1/zixuan/logs/agent_memory/`
- models/embeddings via HF cache: `/work1/zixuan/cache/huggingface`

## Requirements

- conda env `/work1/zixuan/envs/conda_envs/causalmemagent` (python 3.11):
  `vllm==0.6.6.post1 sentence-transformers matplotlib pandas scipy statsmodels pyyaml`
  (only vllm/torch, numpy, sentence-transformers, transformers, matplotlib,
  pyyaml are actually imported by the pilot code; pandas/scipy/statsmodels
  are unused).
- GPU: 1× RTX A5000 24GB is enough for the smoke test
  (`gpu_memory_utilization=0.6`); the full grid shards across GPUs by family.
- HF models (cache): `Qwen/Qwen2.5-1.5B-Instruct` (smoke),
  `Qwen/Qwen2.5-3B-Instruct`, `Qwen/Qwen2.5-7B-Instruct` (full grid);
  embedding model `thenlper/gte-small` with fallback `BAAI/bge-small-en-v1.5`
  (CPU inference).
- env: `export HF_HOME=/work1/zixuan/cache/huggingface` in every run.

## Design notes (deviations and calibration, all recorded)

- 8 program schemas = 4 abstract archetypes × 2 domain renderings each
  (CRM/inventory/ticket/calendar). Both renderings of an archetype share the
  same abstract signature, supplying the P=1, S=0 (A10) pairing.
- Equivalence class = abstract signature (step set, partial order, check
  polarity, abstract role tags). Thresholds/entities are instance parameters.
- Near-miss z′ per archetype: P1 flipped polarity, P2 reversed direction,
  P3 gate on the wrong child-set (done≥1), P4 delete without archive. Each z′
  is executable and reaches its own legal terminal state.
- S operationalisation: bucket-defining metric = TF cosine over content
  tokens with procedural stopwords and pure digits removed (measured
  clusters: S=1 [0.315, 0.795], S=0 [0.000, 0.127]; thresholds 0.29/0.20),
  plus frozen-embedding cosine on the card content core (goal+steps+
  postconditions; fillers/styles excluded) as the second view. Frozen
  encoders conflate surface and program similarity (A10 and A11 clusters
  touch at ~0.89), so the embedding metric is calibrated at the distribution
  level (per-cell medians vs config anchors) and the residual boundary
  overlap is reported in `sealed/manifest.json: embed_calibration` as input
  to the continuous-S sensitivity analysis (tech report §6.9-4).
  This is a documented calibration deviation from a strict per-pair
  dual-metric gate, forced by measured embedding-space overlap.
- Token length is measured with the Qwen2.5-1.5B tokenizer; cards are padded
  with task-neutral boilerplate to a 240-token target (all cells within
  [200, 300]; per-cell means within ~1 token, see manifest).
- Card style templates (6) are Latin-square counterbalanced across
  (family, sibling, cell); balance verified per cell in the manifest.
- Paired design: for a fixed (sibling, seed) the initial DB state is
  byte-identical across all six cells (three independent RNG streams:
  family params / sibling entities / per-seed distractors). Decode seed per
  (sibling, seed) is also shared across cells.
- Success = agent calls `finish(answer)` AND all terminal predicates hold.
  Predicates are computed programmatically from the DB; no LLM judge.
- `run_pilot.py` writes raw JSONL per shard and each row carries git commit,
  config hash, model, vllm/torch versions, GPU model, seed.
- `tests/smoke.py` runs 2 families × 2 siblings × 6 cells × 1 seed (24
  rollouts) instead of literally 1 sibling: SPEC §8.4 requires the 1.5B
  N-condition success rate inside [0.2, 0.8], which has 0/50/100% resolution
  on 2 tasks; 2 siblings give a meaningful 0/25/.../100% reading.
- Known text-level caveat: with per-branch sibling construction, the P3
  near-miss memory (gate on done≥1) is harmless-by-construction on sibling
  states whose branch is A (both programs resolve the ticket there); it is
  harmful on branch-B states. P labels are structural (program equivalence
  class), which is the pre-registered semantics.
- Embedding model is pinned to `BAAI/bge-small-en-v1.5` (config, 2026-08-07),
  with `thenlper/gte-small` as fallback; both are cached in HF_HOME and load
  offline (`HF_HUB_OFFLINE=1` recommended to make the choice deterministic).
  The manifest records which model was actually used and all calibrated
  anchors are measured against the pinned model.
- `git_commit` fields in manifests/rollouts record "unknown": the project
  directory is not a git repository, so the config hash serves as the
  reproducibility anchor instead.

## Reproduce

All commands from `/work1/zixuan/projects/agent_memory/pilot`, with
`PY=/work1/zixuan/envs/conda_envs/causalmemagent/bin/python` and
`export HF_HOME=/work1/zixuan/cache/huggingface`.

1. Generate the benchmark (40 families, sealed oracle split, similarity
   calibration, oracle validation, isolation scan):

   ```bash
   $PY generate_families.py --config configs/pilot.yaml
   # -> /work1/zixuan/data/agent_memory/{public_view,sealed}
   # oracle validation must report 800/800; exits non-zero otherwise.
   ```

2. Isolation check (SPEC §8.3, must print nothing):

   ```bash
   grep -r "family_id\|cell_id" /work1/zixuan/data/agent_memory/public_view
   ```

3. Grid dry-run (no GPU):

   ```bash
   $PY run_pilot.py --config configs/pilot.yaml --model qwen3b --shard 0/5 --dry-run
   ```

4. Instruction-following self-check (SPEC §5, gate >90% parseable):

   ```bash
   CUDA_VISIBLE_DEVICES=0 $PY harness.py --selfcheck --model qwen1.5b \
     --config configs/pilot.yaml
   ```

5. Smoke test (SPEC §8):

   ```bash
   CUDA_VISIBLE_DEVICES=0 $PY tests/smoke.py --config configs/pilot.yaml
   # -> outputs/agent_memory/pilot/smoke/{rollouts_smoke.jsonl,analysis/}
   ```

6. Full grid launch (per GPU, shard by family; example on 10 GPUs):

   ```bash
   for i in 0 1 2 3 4; do
     CUDA_VISIBLE_DEVICES=$i $PY run_pilot.py --model qwen3b --shard $i/5 \
       > /work1/zixuan/logs/agent_memory/pilot_qwen3b_shard$i.log 2>&1 &
   done
   for i in 5 6 7 8 9; do
     CUDA_VISIBLE_DEVICES=$i $PY run_pilot.py --model qwen7b --shard $((i-5))/5 \
       > /work1/zixuan/logs/agent_memory/pilot_qwen7b_shard$((i-5)).log 2>&1 &
   done
   # rerun the same commands after a crash: completed rollout units are skipped
   ```

7. Analysis on the full grid:

   ```bash
   $PY analyze.py --config configs/pilot.yaml \
     --rollouts "/work1/zixuan/outputs/agent_memory/pilot/rollouts_*.jsonl" \
     --out /work1/zixuan/outputs/agent_memory/pilot/analysis
   ```

## Not done in this pilot (SPEC §9)

No retrieval stage, no exact-exposure nesting (Stage B), no D/I/V slices
(Stage C), no training, no utility predictor, no TRU-Mem. No rollout data is
fabricated anywhere: every reported success comes from an actual model
rollout judged by programmatic terminal predicates.
