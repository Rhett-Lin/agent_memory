"""PART_VI_POWER executable artifact. Pure stdlib. CPU only.

Exact one-sided McNemar power for the frozen Part VI design:
  n = 240 paired instances (one paired decode seed per instance),
  decision rule = exact one-sided McNemar p < Holm alpha/3 = 0.05/3
                  AND observed E-harm >= +10pp floor.

Model (frozen):
  discordants  K ~ Binomial(n, q)
  X-favoring   b | K = k ~ Binomial(k, pi(q)),  pi(q) = (q + delta) / (2q)
  delta = p_X - p_N = 0.82 - 0.67 = 0.15 (planning margins; see provenance)
  planning band: q in [delta, delta + 2*min(p_N, 1-p_X)] = [.15, .51]
  (all q values consistent with the two planning margins).

Run:  python power_check.py          -> prints table + writes power_table.json
Two runs are byte-identical (stdlib pure-Python enumeration, no RNG).
"""
from __future__ import annotations

import json
from math import comb
from pathlib import Path

N = 240
ALPHA = 0.05 / 3            # Holm denominator m=3, worst case for E-harm
DELTA = 0.15                # p_X - p_N planning margins
FLOOR = 0.10                # observed +10pp floor (GO co-requirement)
P_N, P_X = 0.67, 0.82       # planning margins (provenance in PART_VI_POWER.md)


def binom_pmf(k: int, n: int, p: float) -> float:
    if k < 0 or k > n:
        return 0.0
    return comb(n, k) * p ** k * (1.0 - p) ** (n - k)


def binom_sf_ge(m: int, n: int, p: float) -> float:
    """P(Bin(n,p) >= m), exact."""
    return sum(binom_pmf(k, n, p) for k in range(m, n + 1))


def mcnemar_p_one_sided(b: int, c: int) -> float:
    """Exact one-sided McNemar p for H1 b>c: P(Bin(b+c,.5) >= b), summed
    upward from b (adjudication correction C4; the max(b,c) form treated the
    adverse direction as significant)."""
    k = b + c
    if k == 0:
        return 1.0
    return binom_sf_ge(b, k, 0.5)


def power(q: float, n: int = N, delta: float = DELTA,
          alpha: float = ALPHA, floor: float = FLOOR) -> float:
    pi = (q + delta) / (2.0 * q)
    pw = 0.0
    for K in range(0, n + 1):
        pk = binom_pmf(K, n, q)
        if pk == 0.0:
            continue
        for b in range(0, K + 1):
            pb = binom_pmf(b, K, pi)
            if pb == 0.0:
                continue
            if mcnemar_p_one_sided(b, K - b) < alpha and (b - (K - b)) / n >= floor:
                pw += pk * pb
    return pw


def planning_band() -> tuple[float, float]:
    return DELTA, DELTA + 2.0 * min(P_N, 1.0 - P_X)


def main() -> int:
    lo, hi = planning_band()
    print(f"planning band q in [{lo:.2f}, {hi:.2f}] (margins-consistent envelope)")
    band_pts = [round(lo + i * 0.01, 2) for i in range(int(round((hi - lo) / 0.01)) + 1)]
    band = [(q, power(q)) for q in band_pts]
    print(f"band power range: {min(p for _, p in band)*100:.1f}%..{max(p for _, p in band)*100:.1f}%")

    curve_q = [round(0.15 + i * 0.05, 2) for i in range(15)]   # .15 .. .85
    curve = [(q, power(q)) for q in curve_q]
    print("robustness curve (n=240):")
    for q, p in curve:
        print(f"  q={q:.2f}  power={p*100:.1f}%")
    p344 = power(0.85, n=344)
    print(f"344-instance variant at q=.85: power={p344*100:.1f}% (>=80% requirement)")

    table = {
        "design": {"n": N, "alpha_holm_third": ALPHA, "delta_margins": DELTA,
                   "observed_floor_pp": FLOOR, "p_N": P_N, "p_X": P_X,
                   "paired_decode_seed_per_instance": 1},
        "planning_band": {"q_lo": lo, "q_hi": hi,
                          "power_min": min(p for _, p in band),
                          "power_max": max(p for _, p in band)},
        "robustness_curve": [{"q": q, "power": p} for q, p in curve],
        "robustness_min": min(p for _, p in curve),
        "n344_at_q085": p344,
    }
    out = Path(__file__).parent / "power_table.json"
    out.write_text(json.dumps(table, indent=2, sort_keys=True) + "\n")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
