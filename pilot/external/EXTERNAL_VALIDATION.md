# External Validation: ALFWorld Effect-Ordering Check (CausalMemAgent)

Bounded external-validity check (tech report §6.4, ALFWorld as the cheap
non-synthetic environment). Goal: does the RelationalOps pilot's key effect
ordering — **replay-like (surface-matched) memory > structural (program-matched,
low-surface) memory > no memory > near-miss memory** — reproduce at a coarse
level outside the synthetic SQLite environment?

**Verdict (honest): partially reproduced, and weaker than the pilot.**
- `R > S > N` direction holds in the aggregate (22.2% / 19.4% / 16.7%) but the
  gaps are small and all binomial CIs overlap — direction-only signal at n=36/cell.
- **The near-miss harm direction did NOT reproduce**: X (25.0%) ≥ N (16.7%).
  Paired (family, sibling, seed) flips vs N: harmful 3, helpful 6.
  Interpretation below — most likely our missing-critical-step near-miss is
  *recoverable* (the env's own goal text still states the full requirement,
  e.g. "find two X and put them in Y"), whereas the pilot's A01 near-misses
  were polarity/order flips that actively mislead.

## Setup (exact commands)

```bash
PY=/work1/zixuan/envs/conda_envs/causalmemagent/bin/python   # python 3.11.15
export PATH=/work1/zixuan/envs/conda_envs/causalmemagent/bin:$PATH
$PY -m pip install "alfworld[full]"   # FAILED: visdom build error (pkg_resources missing)
$PY -m pip install alfworld           # FAILED first try: 'python' not on PATH in
                                      #   fast-downward-textworld build; succeeded after
                                      #   adding the env bin to PATH. Installed alfworld 0.4.2.
export ALFWORLD_DATA=/work1/zixuan/data/agent_memory/alfworld
alfworld-download                     # json_2.1.1 + logic + detectors into $ALFWORLD_DATA
```

Run (single command as specified; stages are prepare → cards → run → analyze):

```bash
export ALFWORLD_DATA=/work1/zixuan/data/agent_memory/alfworld
export HF_HOME=/work1/zixuan/cache/huggingface HF_HUB_OFFLINE=1
export CUDA_VISIBLE_DEVICES=6   # GPUs 0–5 were occupied by another grid
$PY pilot/external/run_alfworld_check.py --stage all
# re-run / resume: --stage run (skips finished rollouts via rollouts.jsonl)
# analysis only: --stage analyze ; smoke: --stage run --smoke --smoke-family clean
```

Versions: alfworld 0.4.2, textworld 1.7.0, jericho 3.3.1, vllm 0.6.6.post1,
torch 2.5.1+cu124, transformers 4.57.6. GPU: 1× NVIDIA RTX A5000 24 GB.
Agent: Qwen/Qwen2.5-7B-Instruct via vllm.LLM, float16,
gpu_memory_utilization 0.85, max_model_len 4096, temperature 0.7, top_p 0.9,
decode seed per (game, seed). Data split: `json_2.1.1/train`.

## Design mapping (pilot → ALFWorld)

| Pilot cell | Ext cell | Construction (all env-validated: source episodes actually `won` their own game) |
|---|---|---|
| N | N | no memory |
| A11 (P=1,S=1) | R | transcript card of a successful episode from a same-family sibling instance sharing the target's object (e.g. clean Bowl→Cabinet target, source clean Bowl→DiningTable); different room/trial |
| A10 (P=1,S=0) | S | procedure card of the same program, entities from the *next* sibling (different object+recep), different template (imperative checklist vs transcript) |
| A01 (P=0,S=1) | X | transcript card of a successful `pick_and_place_simple` episode with the same object — i.e. the critical step (clean / heat / second-pick) is absent; goal text of the source episode matches its own simpler program |

Grid: 3 families (pick_clean_then_place_in_recep, pick_heat_then_place_in_recep,
pick_two_obj_and_place) × 4 siblings × 4 cells × 3 seeds = 144 rollouts,
max 30 steps, success = deterministic env `won`. Cards frozen by script from
hand-coded-expert gold trajectories, 200–300 Qwen tokens each
(R 201–271, S 200–214, X 200–293). Agent interface: pick one command per turn
from the env's admissible list (parse: 87.0% exact, 9.5% fuzzy, 3.5% fallback
→ `look`). Full game/source pairing:
`/work1/zixuan/outputs/agent_memory/external/manifest_games.json`;
cards: `.../cards.json`; raw rollouts: `.../rollouts.jsonl` (144 rows).

## Results

Per-cell success (n=36 each), Wilson 95% CI — see also `EXT_RESULTS.json`:

| cell | k/n | rate | 95% CI | mean steps |
|---|---|---|---|---|
| N | 6/36 | 0.167 | [0.079, 0.319] | 26.7 |
| R | 8/36 | 0.222 | [0.117, 0.381] | 26.0 |
| S | 7/36 | 0.194 | [0.098, 0.350] | 27.8 |
| X | 9/36 | 0.250 | [0.138, 0.411] | 25.5 |

Per family (k/n):

| family | N | R | S | X |
|---|---|---|---|---|
| clean | 0/12 | 4/12 | 4/12 | 1/12 |
| heat | 4/12 | 2/12 | 2/12 | 2/12 |
| pick_two | 2/12 | 2/12 | 1/12 | 6/12 |

Ordering (aggregate rates): `R>S` ✓, `S>N` ✓, `R>N` ✓, `N>X` ✗ (X > N).
Paired flips vs N (36 triads): harmful_X 3, helpful_X 6; harmful_R 5,
helpful_R 7; harmful_S 6, helpful_S 7.

## Interpretation (no overclaiming)

1. **Direction, not magnitude, is the only defensible claim here.** n=36/cell,
   CIs ±15pp; nothing is significant. The pattern `R ≥ S ≥ N` matches the
   pilot's ordering, and the clean family reproduces the full pilot pattern
   (R=S=33% > X=8% > N=0%) — the most pilot-like family.
2. **Near-miss harm did NOT transfer.** X ≥ N overall. Our X is a *successful*
   episode of a wrong program with the critical step omitted; the current-task
   goal text (always visible) still states the requirement, so a 7B model can
   recover the missing step. The pilot's A01 actively contradicts the correct
   precondition (flipped polarity / reversed order), which is harder to undo.
   Coarse implication: **harmful near-miss transfer depends on the near-miss
   type (active misinformation vs recoverable omission)** — ALFWorld with
   recoverable omissions does not show it. pick_two even shows a helpful X
   (6/12: the single-pick transcript teaches navigation/placement scaffolding).
3. **heat family shows no memory benefit at all** (N=4/12 ≥ R=S=X=2/12) —
   small-sample noise is plausible, but it is also the family where X-card
   surface hints (microwave locations) cannot mislead much.

## Deviations (documented loudly)

1. **Custom env wrapper.** `alfworld'gym` batch envs built from ONE
   registration proved non-independent under concurrent stepping (spurious
   early `done` at ~8 steps, reproduced deterministically; first smoke run
   discarded). All reported rollouts use per-episode `textworld.start` envs
   with alfworld's AlfredDemangler/AlfredInfos/AlfredExpert wrappers; the
   30-step cap is enforced by our harness (engine has none in this mode).
   Gold trajectories were verified `won` with the same stack.
2. **No cross-domain rendering for S.** ALFWorld has one domain; A10's
   "same program, different domain wording" is approximated by different
   entities + a different card template (procedure vs transcript). The surface
   gap S=0 vs S=1 is therefore much smaller than in the pilot.
3. **Near-miss operationalization = recoverable omission** (missing critical
   step, env-validated as a complete episode of `pick_and_place_simple` —
   always available, guaranteed executable and successful under its own goal).
   This differs from pilot A01's active polarity/order flips; the negative
   result for X should be read against this construction, not against "near-miss
   memory" in general. A future ALFWorld A01 should inject *actively wrong*
   instructions (e.g. wrong target receptacle, clean-before-pick narration).
4. **R surface similarity is coarser than the pilot's.** R sources share the
   object class (and often recep class, different room layout/trial) with the
   target; pilot A11 siblings shared the full task template with different
   entity values.
5. **Admissible-command action selection** (standard in ALFWorld LLM evals)
   rather than free-form generation; decode seeds are per-(game,seed) vLLM
   seeds — exact vLLM batch-scheduling nondeterminism can make reruns differ
   slightly; the env itself is deterministic per game file.
6. **No Latin-square template counterbalancing** (two fixed card templates:
   transcript for R/X, procedure for S) and **n=36/cell only** — pilot-grade
   calibration checks (dual surface-similarity metrics, token-balance tables)
   were not replicated; this was a bounded validation by design.

## Artifacts

- `pilot/external/run_alfworld_check.py` — single-command pipeline (prepare/cards/run/analyze/--smoke).
- `pilot/external/EXT_RESULTS.json` — per-cell rates, CIs, ordering booleans, flips, card tokens/sources.
- `/work1/zixuan/outputs/agent_memory/external/` — `manifest_games.json` (12 sibling targets + R/S/X source pairings), `cards.json` (36 frozen cards), `rollouts.jsonl` (144 raw episodes incl. commands/parse stats), `EXT_RESULTS.json` copy.
- `pilot/external/alfworld_base_config.yaml` — upstream config kept for reference (data paths).
