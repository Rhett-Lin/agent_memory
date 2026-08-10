# Part V — manual GPU launch sheet (three stages + analysis)

Frozen protocol: `pilot/external/PART_V_PREREG_V5_FINAL.md` (§8 execution order).
Code package: `pilot/external/partv/` (all stages below are resumable; rerun
any command safely — it continues where the ledger/rows stop).

Environment prefix for EVERY command:

```bash
cd /work1/zixuan/projects/agent_memory
export ALFWORLD_DATA=/work1/zixuan/data/agent_memory/alfworld
export HF_HOME=/work1/zixuan/cache/huggingface
export HF_HUB_OFFLINE=1
PY=/work1/zixuan/envs/conda_envs/causalmemagent/bin/python
OUT=/work1/zixuan/outputs/agent_memory/external_gate
LOG=/work1/zixuan/logs/agent_memory/external_gate
mkdir -p "$OUT" "$LOG"
```

## 0. Pre-flight (CPU, seconds)

```bash
$PY -m pilot.external.partv.freeze_manifest            # verify+record hashes (STOP if mismatch)
$PY -m pilot.external.partv.prepare_pools --build      # pools_manifest.json derivation state
$PY -m pilot.external.partv.prepare_pools --dry-run --sim-win-prob 0.5   # feasibility report
$PY -m pilot.external.partv.analyze_gate --self-test   # analysis gate must self-test green
```

NOTE (structural feasibility, see dry-run report): under the frozen §3.5/§3.4
rules the confirmatory pools cannot reach 60+60 even with a 100% per-attempt
harvest win rate (≈40 heat targets max; afterwards ≈2 cool targets, because
the families' qualifying (obj,recep) tuples overlap and confirmatory-heat runs
first by frozen order). Per §3.5.5 this yields NOT_ESTIMATED at pool time.
Harvest commands below are the frozen procedure regardless; the ledger will
make the actual fill rate definitive.

## 1. Harvest (GPUs 5,6,7 — one vLLM per GPU, 3 tuple-disjoint shards)

Pool order is frozen: confirmatory-heat → confirmatory-cool → calibration(20+20)
→ headroom-A(6+6) → headroom-B(6+6). Run all three shards of a pool, `wait`,
then the next pool. Each shard loads its own Qwen2.5-7B (rev a09a354…).

```bash
for POOL in confirmatory-heat confirmatory-cool calibration headroom-A headroom-B; do
  CUDA_VISIBLE_DEVICES=5 $PY -m pilot.external.partv.harvest --pool $POOL --shard 0 --n-shards 3 --gpu 5 > "$LOG/harvest_${POOL}_s0.log" 2>&1 &
  CUDA_VISIBLE_DEVICES=6 $PY -m pilot.external.partv.harvest --pool $POOL --shard 1 --n-shards 3 --gpu 6 > "$LOG/harvest_${POOL}_s1.log" 2>&1 &
  CUDA_VISIBLE_DEVICES=7 $PY -m pilot.external.partv.harvest --pool $POOL --shard 2 --n-shards 3 --gpu 7 > "$LOG/harvest_${POOL}_s2.log" 2>&1 &
  wait
done
```

Ledger: `$OUT/harvest_ledger.jsonl` (only won/steps + trajectory pointers;
NO success-rate inspection). Rejected targets consume replacements;
>40 per type → that pool is recorded NOT_ESTIMATED.

## 2. Cards + pre-rollout audits (CPU; bge on CPU, no GPU job)

```bash
$PY -m pilot.external.partv.build_cards                 # cards.json + cards_audit.json (§4, 200–300 tok, |Δ|≤30, survival assertions)
$PY -m pilot.external.partv.gates_and_audits            # §5 parser criteria, τ_s.json (bge 5th pct), gs_sims, dumbness → audits.json
```

If dumbness fails: `dumbness_rebuild_plan.json` is emitted — re-run harvest
for the listed X-source replacements (§3.4) and rebuild cards, ≤3 rounds.

## 3. Headroom (one GPU; A first, B only if A fails)

```bash
CUDA_VISIBLE_DEVICES=5 $PY -m pilot.external.partv.headroom > "$LOG/headroom.log" 2>&1
```

Writes `headroom/headroom_headroom-{A,B}.json` (manipulation metric,
behavior only — success fields are stripped from headroom rows) and merges
`audits.json["headroom"]` with the chosen framing (A or B). Both fail →
whole experiment NOT_ESTIMATED; do not run the main grid (grid.py refuses).

## 4. Main grid (GPUs 5,6,7 — per-shard files, then merge)

120 targets × 4 seeds × 3 arms = 1440 rollout units (fewer if pools were
shortfall-limited), order shuffled by rng_rollout PCG64(20260810).

```bash
CUDA_VISIBLE_DEVICES=5 $PY -m pilot.external.partv.grid --shard 0 --n-shards 3 > "$LOG/grid_s0.log" 2>&1 &
CUDA_VISIBLE_DEVICES=6 $PY -m pilot.external.partv.grid --shard 1 --n-shards 3 > "$LOG/grid_s1.log" 2>&1 &
CUDA_VISIBLE_DEVICES=7 $PY -m pilot.external.partv.grid --shard 2 --n-shards 3 > "$LOG/grid_s2.log" 2>&1 &
wait
cat "$OUT"/grid/rollouts.s0.jsonl "$OUT"/grid/rollouts.s1.jsonl "$OUT"/grid/rollouts.s2.jsonl > "$OUT"/grid/rollouts.jsonl
```

(Shards write disjoint `rollouts.s{0,1,2}.jsonl` to avoid torn JSON rows;
the merge line is the last grid step.)

## 5. Analysis gate (CPU; runs the frozen bootstrap, B=20000)

```bash
$PY -m pilot.external.partv.analyze_gate --results-dir "$OUT"
```

Exit 0 with `overall_state` ∈ GO/PARTIAL/NO_GO/INCONCLUSIVE, or exit 2 =
NOT_ESTIMATED (hard refuse; nothing estimated). Report: `$OUT/gate_analysis.json`
+ `$OUT/GATE_ANALYSIS.md` (header recomputes q/ICC/DE vs PART_V_POWER.md).

## Budget notes (§9)

- harvest ≤ 20 A5000·h, headroom ≤ 4, grid ≤ 24; hard cap 48.
- Single-episode smoke on GPU 5 took ≈59 s engine+env (model already warm);
  cold vLLM load ≈ 3–4 min per stage start.
- Every GPU command above is idempotent/resumable; interrupted stages
  continue from the ledger/row files.
