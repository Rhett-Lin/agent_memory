# PART_VI_POWER — executable power artifact (SUPERSEDED TEXT; code still operative)

> **TEXT SUPERSEDED BY `PART_VI_PREREG_V4.md` §6 (2026-08-11). The executable
> artifact `power_check.py` (+ `power_table.json`) REMAINS the operative power
> reference and reproduces every number below.**
> For the 344-instance variant note below: the cost arithmetic was corrected in
> V4 §6 ("not taken, reason + corrected cost delta" — budget was NOT the blocker).

Status: FROZEN CANDIDATE for the hash-only Part VI freeze adjudication.
Executable reference: `pilot/tau_survey/part6/power_check.py` (pure stdlib;
output table `power_table.json`; both hashed into
`PART_VI_FREEZE_MANIFEST.json`). CPU only: closed-form enumeration, no model.

## 1. Design under power (frozen)

- **Grid:** 240 synthetic main instances × {N, R, X} × **one** paired decode
  seed per instance (720 rollouts); pairing unit = (instance, paired seed).
- **Decision rule for E-harm:** exact one-sided McNemar with
  **Holm α/3 = 0.05/3 ≈ 0.016667** (worst-case denominator, m=3) **and**
  observed trap(X)−trap(N) ≥ **+10pp floor** (GO co-requirement, v3 §6).

## 2. Planning margins — provenance (如实)

- **p_N = 0.67** — OBSERVED: 4/6 N-arm smoke episodes on FAR-window anchors
  (110.9–217.6h booking age) executed the out-of-window cancel
  (`SMOKE_REPORT.md`). The main grid uses the (24h,48h] near-window; p_N is a
  planning margin transferred from far-window evidence, not a near-window
  measurement.
- **p_X = 0.82** — **ASSUMED, never observed**: the X arm has never been run.
  It is the planning assumption p_N + 15pp. δ = p_X − p_N = 0.15 enters the
  discordance split below.

## 3. Model and exact enumeration code (verbatim from `power_check.py`)

Discordants `K ~ Binomial(n, q)`; X-favoring `b | K ~ Binomial(K, π(q))` with
`π(q) = (q+δ)/(2q)` (the split consistent with margins p_N, p_X). Planning
band `q ∈ [δ, δ + 2·min(p_N, 1−p_X)] = [.15, .51]` — the full envelope of
discordance levels consistent with the two margins.

```python
def binom_pmf(k, n, p):
    return 0.0 if (k < 0 or k > n) else comb(n, k) * p**k * (1-p)**(n-k)

def binom_sf_ge(m, n, p):
    return sum(binom_pmf(k, n, p) for k in range(m, n+1))

def mcnemar_p_one_sided(b, c):          # H1: b>c — upward sum FROM b
    k = b + c                            # (correction C4; max(b,c) was a
    return 1.0 if k == 0 else binom_sf_ge(b, k, 0.5)  # direction bug)

def power(q, n=240, delta=0.15, alpha=0.05/3, floor=0.10):
    pi = (q + delta) / (2*q)
    pw = 0.0
    for K in range(n+1):
        pk = binom_pmf(K, n, q)
        for b in range(K+1):
            if mcnemar_p_one_sided(b, K-b) < alpha and (b-(K-b))/n >= floor:
                pw += pk * binom_pmf(b, K, pi)
    return pw
```

## 4. Realized output (`power_check.py`, run 2026-08-11; `power_table.json`)

- **Planning band q ∈ [.15, .51] → power 85.8%–99.1%** (monotone decreasing
  in q; the band endpoints: q=.15 → 99.1%, q=.51 → 85.8%).
- **Robustness curve** (n=240, extending q beyond the margins-consistent
  envelope): q=.15 99.1 / .20 97.4 / .25 95.6 / .30 93.8 / .35 92.1 /
  .40 90.5 / .45 89.0 / .50 86.5 / .55 83.0 / .60 79.3 / .65 75.7 /
  .70 72.2 / .75 69.1 / .80 66.1 / **.85 63.2 — curve minimum = 63.2%
  (registered limitation, 如实)**.
- **344-instance variant:** power at q=.85 = **80.1% ≥ 80%** — the only
  variant that secures ≥80% across the full swept range. **CONSIDERED AND NOT
  TAKEN**, reason + cost delta (logged per v3 §7):
  - reason: the q > .51 region lies OUTSIDE the margins-consistent envelope
    (it requires N-side discordance beyond what p_N=.67/p_X=.82 permit), and
    the 240-instance band power is already ≥85.8% everywhere INSIDE the
    envelope; insuring the out-of-envelope regime costs the budget cap;
  - cost delta: bank worst path scales 3840→5504 episodes (≈ +21.2 A5000·h at
    the frozen 48.8h/3840 rate), grid 720→1032 rollouts (≈ +3.3 A5000·h at
    ~95 ep/h) ⇒ **≈ +24.5 A5000·h total** — variant total ≈ 81.9 A5000·h vs
    the frozen outcome-independent cap ≤ 60 A5000·h (infeasible);
    the 240 variant totals ≈ 57.4 A5000·h + overhead and stays under the cap.

## 5. Frozen operating statements

- **Realized q is report-only** (v3 §7): the observed discordance rate is
  reported after the grid; it NEVER triggers sample-size adaptation. Power is
  a planning statement, not a retrieval target.
- The +10pp floor and α/3 enter the power curve itself (above); a grid that
  passes McNemar but misses the floor is NOT a GO.
- Robustness limitation registered: below-envelope margin erosions larger than
  planned (q > .51) degrade power to 63.2% at q=.85; this is disclosed in the
  paper boundary if E-harm inference is drawn.
