"""Executable bank-fill feasibility simulation (adjudication correction C2).

Simulates the frozen source-attempt contract:
  - per role (X / R), candidates tried in sha-rank order;
  - per target: up to MAX_CAND_PER_TARGET=4 distinct candidates, each up to
    its REMAINING global attempts; first PASS binds the target
    (accepted sources never reused);
  - per candidate: at most A global attempts (frozen attempt allowance);
  - cache-consistent attempt outcomes: (candidate, attempt) outcomes are
    drawn once per replicate and reused across targets (deterministic
    harvest seeds make retrying the same (candidate, attempt) a no-op);
  - strict pass gate (grounding-first + authored window digit + explicit
    user confirmation + pure-cancel replay delta) packaged as the
    per-attempt pass probability q — UNKNOWN pre-harvest, swept on a grid.

Required fills (v3 §4): X = 40 (hr) + 240 (main) = 280;
                         R = 60 (cal) + 240 (main) = 300.
Binding order per role: hr/cal targets first, then main (global reservation
order src/ -> hr/ -> cal/ -> main/).

Exhaustion rule (frozen, ruling-mandated): bank fill short of the required
counts => NOT_ESTIMATED; no pool substitution, ever.

Deterministic: replicate seeds derive from the frozen formula
md5("tau6|feasibility|<q>|<A>|<C>|<replicate>")[:4] little-endian % 2^31.
Output: feasibility_bank_results.json + FEASIBILITY_BANK.md (frozen number
+ chosen design change + worst-case budget under global-attempt semantics).
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np

MAX_CAND_PER_TARGET = 4          # v3 §4 (frozen, unchanged by the correction)
NEED = {"X": 280, "R": 300}      # hr+main / cal+main
TARGETS_ORDER = {"X": ["hr"] * 40 + ["main"] * 240,
                 "R": ["cal"] * 60 + ["main"] * 240}
SEED_NS = "tau6|feasibility"

GPU_EPISODES_PER_HOUR = 95.0     # smoke calibration (~95 ep/GPU·h)
# B4: headroom is N/X only (80 cells); R headroom card deleted
OTHER_BUDGET_H = {"grid_720": 7.6, "headroom_80": 0.85, "overhead_reserve": 2.0}
BUDGET_CAP_H = 60.0
ICC_SENSITIVITY = 0.35           # frozen within-source correlation sensitivity (B5)


def feas_seed(tag: str) -> int:
    s = f"{SEED_NS}|{tag}"
    return int.from_bytes(hashlib.md5(s.encode()).digest()[:4], "little") % 2**31


def simulate_role(need: int, cands: int, attempts: int, q: float,
                  n_rep: int, seed_tag: str) -> dict:
    """Greedy first-fit allocation with cache-consistent attempts."""
    fill = np.zeros(n_rep, dtype=int)
    episodes = np.zeros(n_rep, dtype=int)
    for rep in range(n_rep):
        rng = np.random.default_rng(feas_seed(f"{seed_tag}|{rep}"))
        # success attempt indices per candidate (cache-consistent)
        outcome = rng.random((cands, attempts)) < q
        attempts_used = np.zeros(cands, dtype=int)
        accepted = np.zeros(cands, dtype=bool)
        filled = 0
        for _ in range(need):
            tried = 0
            ptr = 0
            while tried < MAX_CAND_PER_TARGET and ptr < cands:
                if accepted[ptr] or attempts_used[ptr] >= attempts:
                    ptr += 1
                    continue
                tried += 1
                row = outcome[ptr]
                hit = -1
                for a in range(attempts_used[ptr], attempts):
                    if row[a]:
                        hit = a
                        break
                if hit >= 0:
                    attempts_used[ptr] = hit + 1
                    accepted[ptr] = True
                    filled += 1
                    break
                attempts_used[ptr] = attempts
                ptr += 1
        fill[rep] = filled
        episodes[rep] = int(attempts_used.sum())
    fill_sorted = np.sort(fill)
    ep_sorted = np.sort(episodes)

    def pct(arr, p):
        return float(arr[min(int(math.floor(p * len(arr))), len(arr) - 1)])

    return {
        "need": need, "candid_pool": cands, "attempts_per_source": attempts,
        "q": q, "replicates": n_rep,
        "fill_p5": pct(fill_sorted, 0.05), "fill_mean": float(fill.mean()),
        "fill_p50": pct(fill_sorted, 0.50), "fill_p95": pct(fill_sorted, 0.95),
        "full_fill_prob": float(np.mean(fill == need)),
        "episodes_p50": pct(ep_sorted, 0.50), "episodes_p95": pct(ep_sorted, 0.95),
        "episodes_max": int(ep_sorted[-1]),
    }


def source_success_prob(q: float, attempts: int, icc: float | None = None) -> float:
    """P(a source ever passes within its attempt allowance).
    icc=None: independent attempts. icc=rho: beta-binomial per-source latent
    propensity p_i ~ Beta(a, b), E[p_i]=q, ICC rho = 1/(a+b+1)."""
    if icc is None:
        return 1.0 - (1.0 - q) ** attempts
    ab = (1.0 - icc) / icc
    a, b = q * ab, (1.0 - q) * ab
    fail = math.prod((b + k) for k in range(attempts)) / \
        math.prod((a + b + k) for k in range(attempts))
    return 1.0 - fail


def simulate_role_correlated(need: int, cands: int, attempts: int, q: float,
                             icc: float, n_rep: int, seed_tag: str) -> dict:
    """simulate_role under beta-binomial within-source correlation (B5)."""
    ab = (1.0 - icc) / icc
    a, b = q * ab, (1.0 - q) * ab
    fill = np.zeros(n_rep, dtype=int)
    for rep in range(n_rep):
        rng = np.random.default_rng(feas_seed(f"icc|{seed_tag}|{rep}"))
        p = rng.beta(a, b, size=cands)
        outcome = rng.random((cands, attempts)) < p[:, None]
        attempts_used = np.zeros(cands, dtype=int)
        accepted = np.zeros(cands, dtype=bool)
        filled = 0
        for _ in range(need):
            tried = 0
            ptr = 0
            while tried < MAX_CAND_PER_TARGET and ptr < cands:
                if accepted[ptr] or attempts_used[ptr] >= attempts:
                    ptr += 1
                    continue
                tried += 1
                row = outcome[ptr]
                hit = -1
                for aa in range(attempts_used[ptr], attempts):
                    if row[aa]:
                        hit = aa
                        break
                if hit >= 0:
                    attempts_used[ptr] = hit + 1
                    accepted[ptr] = True
                    filled += 1
                    break
                attempts_used[ptr] = attempts
                ptr += 1
        fill[rep] = filled
    return {"need": need, "q": q, "icc": icc,
            "fill_p5": float(np.sort(fill)[min(int(0.05 * n_rep), n_rep - 1)]),
            "full_fill_prob": float(np.mean(fill == need))}


def worst_case_episodes(cx: int, cr: int, a: int) -> int:
    """Global-attempt worst case: every candidate exhausted."""
    return (cx + cr) * a


def budget_hours(harvest_episodes: float) -> dict:
    h = harvest_episodes / GPU_EPISODES_PER_HOUR
    total = h + sum(OTHER_BUDGET_H.values())
    return {"harvest_h": round(h, 1), "total_h": round(total, 1),
            "within_cap_60": total <= BUDGET_CAP_H}


def main() -> int:
    out_dir = Path(__file__).resolve().parent
    q_grid = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50,
              0.60, 0.70, 0.80, 0.90]
    configs = [(320, 2), (360, 2), (440, 2), (560, 2),
               (320, 3), (360, 3), (440, 3), (560, 3)]
    n_coarse, n_final = 400, 4000

    coarse = {}
    for c, a in configs:
        for q in q_grid:
            key = f"C{c}_A{a}"
            rx = simulate_role(NEED["X"], c, a, q, n_coarse, f"coarse|X|{key}|{q}")
            rr = simulate_role(NEED["R"], c, a, q, n_coarse, f"coarse|R|{key}|{q}")
            coarse.setdefault(key, {})[q] = {
                "X_full_fill": rx["full_fill_prob"], "R_full_fill": rr["full_fill_prob"],
                "X_fill_p5": rx["fill_p5"], "R_fill_p5": rr["fill_p5"],
                "R_episodes_p95": rr["episodes_p95"], "X_episodes_p95": rx["episodes_p95"]}

    # selection: LOWEST q* first (a feasibility boundary as low as budget
    # allows), then smallest worst-case episodes (R role binds: 300 needed).
    best = None
    for c, a in configs:
        key = f"C{c}_A{a}"
        wc = worst_case_episodes(c, c, a)
        if budget_hours(wc)["within_cap_60"] is False:
            continue
        qstar = None
        for q in q_grid:
            if coarse[key][q]["X_full_fill"] >= 0.95 and coarse[key][q]["R_full_fill"] >= 0.95:
                qstar = q
                break
        if qstar is None:
            continue
        cand = (qstar, wc, key)
        if best is None or cand < best[0]:
            best = (cand, key, c, a, qstar)
    if best is None:
        chosen = None
    else:
        _, key, c, a, qstar = best
        chosen = {"pool_per_role": c, "attempts_per_source": a,
                  "q_star_full_fill_95pct": qstar,
                  "worst_case_harvest_episodes": worst_case_episodes(c, c, a)}

    # final high-replicate confirmation of the chosen config (+ baseline 640/A2)
    final = {}
    confirm = ([(320, 2)] if chosen is None or (c, a) != (320, 2) else []) + ([(c, a)] if chosen else [])
    for cc, aa in confirm:
        for q in q_grid:
            rx = simulate_role(NEED["X"], cc, aa, q, n_final, f"final|X|C{cc}_A{aa}|{q}")
            rr = simulate_role(NEED["R"], cc, aa, q, n_final, f"final|R|C{cc}_A{aa}|{q}")
            final[f"C{cc}_A{aa}|{q}"] = {"X": rx, "R": rr}

    # frozen within-source-correlation sensitivity (B5) for the chosen config
    icc_block = None
    if best is not None:
        cc_, aa_ = chosen["pool_per_role"], chosen["attempts_per_source"]
        qs_ = chosen["q_star_full_fill_95pct"]
        icc_block = {
            "model": ("beta-binomial per-source latent pass propensity p_i ~ Beta(a,b), "
                      "E[p_i]=q, ICC rho = 1/(a+b+1); attempts within one source are "
                      "correlated through p_i"),
            "icc": ICC_SENSITIVITY, "q": qs_, "attempts": aa_,
            "source_success_independence": source_success_prob(qs_, aa_),
            "source_success_icc": source_success_prob(qs_, aa_, ICC_SENSITIVITY),
            "X_full_fill_icc": simulate_role_correlated(
                NEED["X"], cc_, aa_, qs_, ICC_SENSITIVITY, n_final, f"final|X|icc"),
            "R_full_fill_icc": simulate_role_correlated(
                NEED["R"], cc_, aa_, qs_, ICC_SENSITIVITY, n_final, f"final|R|icc"),
            "label": ("all q* and full-fill numbers in this artifact are "
                      "independence-conditional planning figures"),
            "sole_gate": ("full bank cardinality (280 X + 300 R accepted, balanced "
                          "main pairs) else NOT_ESTIMATED; no post-harvest pool "
                          "adjustment under EITHER hypothesis"),
        }

    results = {
        "contract": {
            "max_candidates_per_target": MAX_CAND_PER_TARGET,
            "need": NEED, "targets_order": {k: [v[0], len(v)] for k, v in TARGETS_ORDER.items()},
            "cache_consistent_attempts": True,
            "exhaustion_rule": ("bank fill short of required counts => NOT_ESTIMATED; "
                                "no pool substitution, ever"),
            "seed_namespace": SEED_NS,
        },
        "q_grid": q_grid,
        "configs_tested": [f"C{c}_A{a}" for c, a in configs],
        "coarse_replicates": n_coarse, "final_replicates": n_final,
        "coarse": coarse,
        "chosen_design_change": chosen,
        "final": final,
        "icc_sensitivity": icc_block,
    }
    (out_dir / "feasibility_bank_results.json").write_text(
        json.dumps(results, indent=2, sort_keys=True) + "\n")

    # ---- FEASIBILITY_BANK.md (numbers inlined, regenerable) -----------------
    lines = [
        "# FEASIBILITY_BANK — bank-fill feasibility under the frozen source-attempt contract",
        "",
        "Executable: `part6/feasibility_bank.py` (deterministic seeds "
        "`tau6|feasibility|...`; output `feasibility_bank_results.json`). "
        "CPU only; no rollouts. The per-attempt pass probability q of the strict gate "
        "(grounding-first + authored window digit + explicit user confirmation + "
        "pure-cancel replay delta) is UNKNOWN pre-harvest and is swept as a planning "
        "axis — same honesty discipline as the Part V gateway simulation.",
        "",
        f"- Contract: per-target up to {MAX_CAND_PER_TARGET} candidates (frozen, unchanged); "
        f"per-source global attempt allowance A; candidates tried in sha256 rank order; "
        "cache-consistent attempts; accepted sources never reused.",
        f"- Required fill: X = {NEED['X']} (40 hr + 240 main), R = {NEED['R']} (60 cal + 240 main); "
        "binding order hr/cal -> main per role.",
        "- **Exhaustion rule (frozen): fill short of the required counts => NOT_ESTIMATED; "
        "no pool substitution, ever.**",
        "",
        "## Chosen design change (ONE, per ruling)",
    ]
    if chosen is None:
        lines.append("NO config in the tested grid achieved full_fill >= 0.95 for both "
                     "roles at any q in the grid — bank is INFEASIBLE as specified.")
    else:
        cx = chosen["pool_per_role"]
        lines += [
            f"- src pool: **640 → {2*cx} ({cx} X + {cx} R)**; per-source attempts: "
            f"**{chosen['attempts_per_source']}** (per-target 4-candidate cap unchanged).",
            f"- Coarse sweep criterion: LEAST infeasibility boundary first — lowest q "
            f"with full-fill probability >= 0.95 for BOTH roles; tie-break: smallest "
            f"worst-case episodes that still fit the 60 A5000·h cap.",
            f"- **Frozen operating threshold q\\* = {chosen['q_star_full_fill_95pct']:.2f}** "
            "(independence-conditional planning figure): below this per-attempt pass "
            "rate the bank cannot be expected to fill and the experiment refuses "
            "(NOT_ESTIMATED) by design.",
            f"- **Frozen numbers: pool = {2*cx} ({cx}/role), attempts/source = "
            f"{chosen['attempts_per_source']}, worst-case harvest episodes = "
            f"{chosen['worst_case_harvest_episodes']}** (global-attempt semantics: every "
            "candidate exhausted; the old v3 figure 3,840 was computed under a "
            "per-target-only reading and is wrong under global attempts).",
            "",
            "### Final confirmation (replicates = %d, chosen config)" % n_final,
            "",
            "| q | role | fill P5 | fill mean | full-fill prob | episodes P95 |",
            "|---|---|---|---|---|---|",
        ]
        for q in q_grid:
            row = final[f"C{c}_A{a}|{q}"]
            for role in ("X", "R"):
                r = row[role]
                lines.append(
                    f"| {q:.2f} | {role} | {r['fill_p5']:.0f} | {r['fill_mean']:.1f} "
                    f"| {r['full_fill_prob']:.3f} | {r['episodes_p95']:.0f} |")
        lines += [
            "",
            "### Baseline 640/A=2 (why it is inadequate)",
            "",
            "| q | role | fill P5 | full-fill prob |",
            "|---|---|---|---|",
        ]
        if any(k.startswith("C320_A2|") for k in final):
            for q in q_grid:
                row = final[f"C320_A2|{q}"]
                for role in ("X", "R"):
                    r = row[role]
                    lines.append(f"| {q:.2f} | {role} | {r['fill_p5']:.0f} "
                                 f"| {r['full_fill_prob']:.3f} |")
        b = budget_hours(chosen["worst_case_harvest_episodes"])
        lines += [
            "",
            "## Independence-conditional label + within-source correlation sensitivity (B5)",
            "",
            "- Every q\\*-band and full-fill number in this artifact is "
            "**independence-conditional** (attempt outcomes modeled as independent "
            "within a source).",
            "- Frozen sensitivity check: beta-binomial per-source latent pass "
            "propensity with ICC ρ = 0.35: source success "
            f"{source_success_prob(chosen['q_star_full_fill_95pct'], chosen['attempts_per_source']):.3f} "
            "(independence) → "
            f"{source_success_prob(chosen['q_star_full_fill_95pct'], chosen['attempts_per_source'], ICC_SENSITIVITY):.3f} "
            "(ICC .35); full-fill probabilities degrade accordingly:",
            "",
            "| role | independence full-fill (q*) | ICC .35 full-fill (q*) | ICC .35 fill P5 |",
            "|---|---|---|---|",
        ]
        fi = final[f"C{chosen['pool_per_role']}_A{chosen['attempts_per_source']}|{chosen['q_star_full_fill_95pct']}"]
        for role in ("X", "R"):
            block = icc_block[f"{role}_full_fill_icc"]
            lines.append(
                f"| {role} | {fi[role]['full_fill_prob']:.3f} "
                f"| {block['full_fill_prob']:.3f} | {block['fill_p5']:.0f} |")
        lines += [
            "",
            "- **Sole operational gate (frozen): FULL bank cardinality — "
            "280 X + 300 R accepted with balanced main pairs — else NOT_ESTIMATED. "
            "No post-harvest pool adjustment under either hypothesis** (the ICC "
            "sensitivity is a planning disclosure, not a retry license).",
            "",
            "## Budget recomputation (global-attempt semantics, frozen)",
            "",
            f"- worst-case harvest episodes {chosen['worst_case_harvest_episodes']} "
            f"≈ {b['harvest_h']} A5000·h at ~95 ep/GPU·h (smoke calibration).",
            f"- + main grid 720 ≈ 7.6h + headroom 80 (N/X only, B4) ≈ 0.85h + "
            f"overhead reserve 2.0h = **{b['total_h']} A5000·h total** — under the "
            f"frozen outcome-independent cap 60 A5000·h: {b['within_cap_60']}.",
            "- expected (typical) harvest consumption is far below the worst case "
            "(see episodes P95 per q above); the budget is booked at the worst case.",
        ]
    (out_dir / "FEASIBILITY_BANK.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(chosen, indent=2))
    print("wrote feasibility_bank_results.json + FEASIBILITY_BANK.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
