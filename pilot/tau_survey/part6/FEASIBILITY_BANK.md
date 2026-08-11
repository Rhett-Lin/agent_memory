# FEASIBILITY_BANK — bank-fill feasibility under the frozen source-attempt contract

Executable: `part6/feasibility_bank.py` (deterministic seeds `tau6|feasibility|...`; output `feasibility_bank_results.json`). CPU only; no rollouts. The per-attempt pass probability q of the strict gate (grounding-first + authored window digit + explicit user confirmation + pure-cancel replay delta) is UNKNOWN pre-harvest and is swept as a planning axis — same honesty discipline as the Part V gateway simulation.

- Contract: per-target up to 4 candidates (frozen, unchanged); per-source global attempt allowance A; candidates tried in sha256 rank order; cache-consistent attempts; accepted sources never reused.
- Required fill: X = 280 (40 hr + 240 main), R = 300 (60 cal + 240 main); binding order hr/cal -> main per role.
- **Exhaustion rule (frozen): fill short of the required counts => NOT_ESTIMATED; no pool substitution, ever.**

## Chosen design change (ONE, per ruling)
- src pool: **640 → 720 (360 X + 360 R)**; per-source attempts: **3** (per-target 4-candidate cap unchanged).
- Coarse sweep criterion: LEAST infeasibility boundary first — lowest q with full-fill probability >= 0.95 for BOTH roles; tie-break: smallest worst-case episodes that still fit the 60 A5000·h cap.
- **Frozen operating threshold q\* = 0.60** (independence-conditional planning figure): below this per-attempt pass rate the bank cannot be expected to fill and the experiment refuses (NOT_ESTIMATED) by design.
- **Frozen numbers: pool = 720 (360/role), attempts/source = 3, worst-case harvest episodes = 2160** (global-attempt semantics: every candidate exhausted; the old v3 figure 3,840 was computed under a per-target-only reading and is wrong under global attempts).

### Final confirmation (replicates = 4000, chosen config)

| q | role | fill P5 | fill mean | full-fill prob | episodes P95 |
|---|---|---|---|---|---|
| 0.10 | X | 84 | 97.5 | 0.000 | 996 |
| 0.10 | R | 84 | 97.6 | 0.000 | 995 |
| 0.15 | X | 124 | 138.9 | 0.000 | 949 |
| 0.15 | R | 123 | 138.7 | 0.000 | 950 |
| 0.20 | X | 160 | 175.5 | 0.000 | 903 |
| 0.20 | R | 160 | 175.5 | 0.000 | 904 |
| 0.25 | X | 192 | 208.1 | 0.000 | 858 |
| 0.25 | R | 192 | 208.1 | 0.000 | 859 |
| 0.30 | X | 221 | 236.4 | 0.000 | 816 |
| 0.30 | R | 221 | 236.3 | 0.000 | 815 |
| 0.35 | X | 247 | 260.9 | 0.007 | 773 |
| 0.35 | R | 246 | 261.0 | 0.000 | 774 |
| 0.40 | X | 269 | 277.6 | 0.405 | 731 |
| 0.40 | R | 269 | 282.1 | 0.010 | 733 |
| 0.45 | X | 279 | 279.8 | 0.798 | 667 |
| 0.45 | R | 288 | 297.3 | 0.477 | 693 |
| 0.50 | X | 279 | 279.9 | 0.931 | 599 |
| 0.50 | R | 299 | 299.9 | 0.923 | 641 |
| 0.60 | X | 280 | 280.0 | 0.996 | 496 |
| 0.60 | R | 300 | 300.0 | 0.995 | 531 |
| 0.70 | X | 280 | 280.0 | 1.000 | 422 |
| 0.70 | R | 300 | 300.0 | 1.000 | 453 |
| 0.80 | X | 280 | 280.0 | 1.000 | 366 |
| 0.80 | R | 300 | 300.0 | 1.000 | 391 |
| 0.90 | X | 280 | 280.0 | 1.000 | 321 |
| 0.90 | R | 300 | 300.0 | 1.000 | 344 |

### Baseline 640/A=2 (why it is inadequate)

| q | role | fill P5 | full-fill prob |
|---|---|---|---|
| 0.10 | X | 50 | 0.000 |
| 0.10 | R | 49 | 0.000 |
| 0.15 | X | 76 | 0.000 |
| 0.15 | R | 76 | 0.000 |
| 0.20 | X | 101 | 0.000 |
| 0.20 | R | 101 | 0.000 |
| 0.25 | X | 125 | 0.000 |
| 0.25 | R | 126 | 0.000 |
| 0.30 | X | 149 | 0.000 |
| 0.30 | R | 148 | 0.000 |
| 0.35 | X | 170 | 0.000 |
| 0.35 | R | 170 | 0.000 |
| 0.40 | X | 191 | 0.000 |
| 0.40 | R | 191 | 0.000 |
| 0.45 | X | 210 | 0.000 |
| 0.45 | R | 210 | 0.000 |
| 0.50 | X | 228 | 0.000 |
| 0.50 | R | 228 | 0.000 |
| 0.60 | X | 258 | 0.042 |
| 0.60 | R | 258 | 0.000 |
| 0.70 | X | 280 | 0.965 |
| 0.70 | R | 283 | 0.046 |
| 0.80 | X | 280 | 0.999 |
| 0.80 | R | 300 | 0.978 |
| 0.90 | X | 280 | 1.000 |
| 0.90 | R | 300 | 1.000 |

## Independence-conditional label + within-source correlation sensitivity (B5)

- Every q\*-band and full-fill number in this artifact is **independence-conditional** (attempt outcomes modeled as independent within a source).
- Frozen sensitivity check: beta-binomial per-source latent pass propensity with ICC ρ = 0.35: source success 0.936 (independence) → 0.826 (ICC .35); full-fill probabilities degrade accordingly:

| role | independence full-fill (q*) | ICC .35 full-fill (q*) | ICC .35 fill P5 |
|---|---|---|---|
| X | 0.996 | 0.778 | 279 |
| R | 0.995 | 0.329 | 286 |

- **Sole operational gate (frozen): FULL bank cardinality — 280 X + 300 R accepted with balanced main pairs — else NOT_ESTIMATED. No post-harvest pool adjustment under either hypothesis** (the ICC sensitivity is a planning disclosure, not a retry license).

## Budget recomputation (global-attempt semantics, frozen)

- worst-case harvest episodes 2160 ≈ 22.7 A5000·h at ~95 ep/GPU·h (smoke calibration).
- + main grid 720 ≈ 7.6h + headroom 80 (N/X only, B4) ≈ 0.85h + overhead reserve 2.0h = **33.2 A5000·h total** — under the frozen outcome-independent cap 60 A5000·h: True.
- expected (typical) harvest consumption is far below the worst case (see episodes P95 per q above); the budget is booked at the worst case.
