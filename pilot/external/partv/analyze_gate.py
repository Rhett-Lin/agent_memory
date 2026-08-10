"""Part V analysis gate (frozen; commit-before-outcome-inspection artifact).

Implements PART_V_PREREG_V5_FINAL.md $6 + $10 EXACTLY:

  - policy value V(g) = E_c[ g*succ_c + (1-g)*succ_N ] with the frozen
    {R:1/2, X:1/2} candidate distribution per (target, seed); type mixture
    1/2 heat + 1/2 cool; targets/seeds uniform within type.
  - endpoints: (1) E-harm = succ(N)-succ(X), theta0=0;
               (2) E-serve = V(G-struct)-V(G-S), theta0=0;
               (3) E-oracle-noninf = V(G-struct)-V(oracle), theta0=-0.05.
  - null-centered cluster bootstrap: cluster=target, stratified (60 heat /
    60 cool), B=20000, seed 20260809 (numpy PCG64);
    p_raw = (1 + #{ (th_b* - th) >= (th - theta0) }) / (B+1).
  - Holm m=3 one-sided: p_raw ascending, k-th vs alpha/(m-k+1), ties kept in
    the frozen (1)(2)(3) order; endpoints that are NOT_ESTIMATED or whose
    service premise failed enter with p_raw=1 (keystone rule, $10).
  - descriptive CIs: percentile 2.5/97.5 of the bootstrap distribution.
  - NO_GO bounds: mixture UB = 95th percentile; per-type Bonferroni UBs =
    97.5th percentile per type (both < +10pp required).
  - terminal state machine GO / PARTIAL / NO_GO / INCONCLUSIVE /
    NOT_ESTIMATED, per-endpoint, hard-refuse on incomplete grid (exit 2).
  - report header recomputes q / ICC / DE against PART_V_POWER.md values.

Gate decisions are deterministic post-hoc functions of the fixed rollout
grid: G-struct via partv.gstruct.decide (abstain -> admit, documented),
G-S via cached bge cosine sims >= tau_s (computed pre-rollout into
audits.json), oracle = perfect congruence gate (admits R, rejects X).

ANALYSIS HYGIENE: success-rate inspection is FORBIDDEN before this script
runs; the harvest ledger records only won/steps for sourcing.

Usage:
  python -m pilot.external.partv.analyze_gate --results-dir <dir>
  python -m pilot.external.partv.analyze_gate --self-test
"""

import argparse
import json
import math
import os
import sys
from collections import defaultdict

import numpy as np

from pilot.external.partv import common
from pilot.external.partv import gstruct

# ---------------------------------------------------------------------------
# Frozen constants
# ---------------------------------------------------------------------------

ALPHA = 0.05
M_TESTS = 3
B_BOOT = 20000
NONINF_MARGIN = 0.05               # endpoint (3): theta0 = -0.05
GO_POINT_FLOOR = 0.05              # E-harm observed point >= +5pp for GO
NOGO_MIX_UB = 0.05                 # mixture 95th-pct UB must be < +5pp
NOGO_TYPE_UB = 0.10                # per-type 97.5th-pct UBs must be < +10pp
EHARM, ESERVE, EORACLE = "E-harm", "E-serve", "E-oracle-noninf"
ENDPOINTS = [EHARM, ESERVE, EORACLE]           # frozen tie order (1)(2)(3)
THETA0 = {EHARM: 0.0, ESERVE: 0.0, EORACLE: -NONINF_MARGIN}
STATES = ("GO", "PARTIAL", "NO_GO", "INCONCLUSIVE", "NOT_ESTIMATED")

POWER_FROZEN = {"q": 0.25, "ICC": 0.35, "DE": 2.0, "n_eff": 240.0}


class IncompleteGrid(RuntimeError):
    """Hard-refuse condition: the frozen 60+60 model-only grid is incomplete."""


# ---------------------------------------------------------------------------
# data loading / validation
# ---------------------------------------------------------------------------

def _read_jsonl(path):
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_bundle(results_dir):
    """Load the frozen analysis bundle; verify pinned hashes first."""
    bundle = {"dir": results_dir}
    # hash verification (premise 5): builder + prompt package (Appendix A).
    hash_ok, hash_detail = True, {}
    try:
        hash_detail["builder_sha256"] = common.verify_builder()
    except RuntimeError as e:                      # FrozenHashMismatch
        hash_ok = False
        hash_detail["builder_error"] = str(e)
    try:
        common.load_prompts(verify=True)
        hash_detail["prompts_sha256"] = common.PROMPTS_SHA256
    except RuntimeError as e:
        hash_ok = False
        hash_detail["prompts_error"] = str(e)
    bundle["hash_ok"] = hash_ok
    bundle["hash_detail"] = hash_detail

    with open(os.path.join(results_dir, "cards.json")) as f:
        bundle["cards"] = json.load(f)
    with open(os.path.join(results_dir, "audits.json")) as f:
        bundle["audits"] = json.load(f)
    bundle["rollouts"] = _read_jsonl(
        os.path.join(results_dir, "grid", "rollouts.jsonl"))
    return bundle


def build_cluster_table(bundle, n_per_type=common.CONFIRMATORY_PER_TYPE,
                        seeds=common.GRID_SEEDS):
    """(type -> target -> per-seed arm successes + gate inputs).

    Hard-refuse (raise IncompleteGrid) when anything is missing for the
    frozen confirmatory grid: exactly n_per_type targets per type, each with
    all seeds x arms {N,R,X} present exactly once, plus cards for R and X.
    """
    rows = bundle["rollouts"]
    cards = bundle["cards"]
    succ = defaultdict(dict)          # (type, target, seed)[arm] = 0/1
    seen = defaultdict(set)
    for r in rows:
        if r.get("pool", "confirmatory") != "confirmatory":
            continue
        key = (r["type"], r["target"], int(r["seed"]))
        arm = r["arm"]
        if arm in seen[key]:
            raise IncompleteGrid("duplicate rollout row: %s %s" % (key, arm))
        seen[key].add(arm)
        succ[key][arm] = int(r["success"])

    by_type = defaultdict(dict)       # type -> target -> {seed: {arm: 0/1}}
    for (typ, target, seed), arms in succ.items():
        by_type[typ].setdefault(target, {})[seed] = arms

    problems = []
    for typ in ("heat", "cool"):
        targets = by_type.get(typ, {})
        if len(targets) > n_per_type:
            problems.append("type %s has %d > %d targets"
                            % (typ, len(targets), n_per_type))
        for t, per_seed in targets.items():
            for s in seeds:
                got = per_seed.get(s, {})
                for arm in common.ARMS:
                    if arm not in got:
                        problems.append("missing %s/%s/seed%d/%s"
                                        % (typ, t, s, arm))
            if t not in cards:
                problems.append("missing cards for target %s" % t)
        if len(targets) < n_per_type:
            problems.append("type %s has %d < %d confirmatory targets"
                            % (typ, len(targets), n_per_type))
    if problems:
        raise IncompleteGrid("; ".join(problems[:20]))
    return by_type


# ---------------------------------------------------------------------------
# gates (post-hoc, deterministic)
# ---------------------------------------------------------------------------

def gate_decisions(goal, card_text, sim_gs, tau_s):
    """(gstruct, gs, oracle) admission bits for one (goal, card) candidate.

    G-struct abstain (parse-fail) maps to ADMIT: $5 defines 'reject' only for
    a positively parsed contradiction, so abstention cannot block memory.
    G-S admits iff bge cosine similarity >= tau_s ($5).
    oracle admits iff the candidate is prep-congruent with the goal.
    """
    decision, goal_prep, card_prep = gstruct.decide(goal, card_text)
    g_gate = 0 if decision == "reject" else 1       # admit | abstain -> 1
    g_sim = 1 if (sim_gs is not None and tau_s is not None
                  and sim_gs >= tau_s) else 0
    g_oracle = 1 if (goal_prep is not None and card_prep is not None
                     and goal_prep == card_prep) else 0
    return {"G-struct": g_gate, "G-S": g_sim, "oracle": g_oracle,
            "decision": decision, "goal_prep": goal_prep,
            "card_prep": card_prep}


# ---------------------------------------------------------------------------
# estimands
# ---------------------------------------------------------------------------

def cluster_values(by_type, cards, audits, seeds=common.GRID_SEEDS):
    """Per-cluster (target) endpoint contributions.

    -> {"values": {ep: {"heat": np.array, "cool": np.array}},
        "gates":  detail per target}
    """
    tau_s = audits.get("tau_s")
    sims = audits.get("gs_sims", {})
    values = {ep: {"heat": [], "cool": []} for ep in ENDPOINTS}
    gates_detail = {}
    for typ in ("heat", "cool"):
        for target in sorted(by_type[typ]):
            per_seed = by_type[typ][target]
            cinfo = cards[target]
            goal = cinfo["goal"]
            d_harm, vals = [], {g: [] for g in ("G-struct", "G-S", "oracle")}
            gd = {}
            for arm in ("R", "X"):
                card_text = cinfo[arm]["text"]
                sim = sims.get(target, {}).get(arm)
                gd[arm] = gate_decisions(goal, card_text, sim, tau_s)
            for s in seeds:
                ss = per_seed[s]
                sN, sR, sX = ss["N"], ss["R"], ss["X"]
                d_harm.append(sN - sX)
                for gname in vals:
                    gR, gX = gd["R"][gname], gd["X"][gname]
                    v = 0.5 * (gR * sR + (1 - gR) * sN) \
                        + 0.5 * (gX * sX + (1 - gX) * sN)
                    vals[gname].append(v)
            harm = float(np.mean(d_harm))
            vg = {g: float(np.mean(v)) for g, v in vals.items()}
            values[EHARM][typ].append(harm)
            values[ESERVE][typ].append(vg["G-struct"] - vg["G-S"])
            values[EORACLE][typ].append(vg["G-struct"] - vg["oracle"])
            gates_detail[target] = {a: {k: gd[a][k] for k in
                                        ("G-struct", "G-S", "oracle",
                                         "decision", "goal_prep", "card_prep")}
                                    for a in ("R", "X")}
    for ep in values:
        for typ in values[ep]:
            values[ep][typ] = np.asarray(values[ep][typ], dtype=float)
    return {"values": values, "gates": gates_detail}


def theta_hat(values_ep):
    """Frozen 1/2+1/2 type mixture of cluster means."""
    return 0.5 * (values_ep["heat"].mean() + values_ep["cool"].mean())


# ---------------------------------------------------------------------------
# null-centered cluster bootstrap (frozen)
# ---------------------------------------------------------------------------

def bootstrap_replicates(values_ep, B=B_BOOT, seed=common.SEED_BOOTSTRAP):
    """Stratified cluster bootstrap; cluster=target, strata heat/cool.

    One shared set of resampled index draws (heat then cool, PCG64(seed)) is
    reused for every endpoint, CI, and NO_GO bound -- frozen draw order.

    -> (theta_b (B,), theta_b_heat (B,), theta_b_cool (B,))
    """
    rng = np.random.Generator(np.random.PCG64(seed))
    vh, vc = values_ep["heat"], values_ep["cool"]
    idx_h = rng.integers(0, len(vh), size=(B, len(vh)))
    idx_c = rng.integers(0, len(vc), size=(B, len(vc)))
    th_h = vh[idx_h].mean(axis=1)
    th_c = vc[idx_c].mean(axis=1)
    return 0.5 * (th_h + th_c), th_h, th_c


def p_raw_null_centered(theta_b, theta, theta0):
    """Frozen formula: (1 + #{(th_b* - th) >= (th - theta0)}) / (B+1)."""
    cnt = int(np.sum((theta_b - theta) >= (theta - theta0)))
    return (1.0 + cnt) / (len(theta_b) + 1.0)


def holm(p_raws, alpha=ALPHA, m=M_TESTS, order=ENDPOINTS):
    """Holm step-down, ties kept in the frozen endpoint order.

    Python's sort is stable, so equal p's keep `order`.  Sequential: rank k
    compares against alpha/(m-k+1); stop at the first non-rejection.
    """
    ranked = sorted(order, key=lambda ep: p_raws[ep])
    out, rejected_so_far = {}, True
    for k, ep in enumerate(ranked, start=1):
        thr = alpha / (m - k + 1)
        rej = rejected_so_far and (p_raws[ep] < thr)
        out[ep] = {"rank": k, "threshold": thr, "p_raw": p_raws[ep],
                   "rejected": bool(rej)}
        rejected_so_far = rej
    return out


# ---------------------------------------------------------------------------
# q / ICC / DE header recompute (PART_V_POWER.md artifacts)
# ---------------------------------------------------------------------------

def icc_oneway(matrix):
    """One-way random-effects ANOVA ICC on a (n_clusters, k) matrix."""
    x = np.asarray(matrix, dtype=float)
    n, k = x.shape
    if n < 2 or k < 2:
        return float("nan")
    grand = x.mean()
    row_means = x.mean(axis=1)
    msb = k * np.sum((row_means - grand) ** 2) / (n - 1)
    msw = np.sum((x - row_means[:, None]) ** 2) / (n * (k - 1))
    denom = msb + (k - 1) * msw
    if denom == 0:
        return float("nan")
    return float((msb - msw) / denom)


# ---------------------------------------------------------------------------
# q / ICC / DE header recompute (PART_V_POWER.md artifacts)
# ---------------------------------------------------------------------------

def power_header(by_type, seeds=common.GRID_SEEDS):
    """Recompute q / ICC / DE against the PART_V_POWER.md planning values.

    DE uses the ICC of the paired difference d = succ_N - succ_X over the
    seeds within a target (the E-harm pairing unit); ICC_N / ICC_X are also
    reported for transparency.  Realized ICC >= 0.6 only triggers the frozen
    disclosure note (no criterion change).
    """
    n_pairs, n_discordant = 0, 0
    dmat, nmat, xmat = [], [], []
    for typ in ("heat", "cool"):
        for t in by_type[typ]:
            ds, ns, xs = [], [], []
            for s in seeds:
                a = by_type[typ][t][s]
                ds.append(a["N"] - a["X"])
                ns.append(a["N"])
                xs.append(a["X"])
                n_pairs += 1
                if a["N"] != a["X"]:
                    n_discordant += 1
            dmat.append(ds)
            nmat.append(ns)
            xmat.append(xs)
    q = (n_discordant / n_pairs) if n_pairs else float("nan")
    icc_d = icc_oneway(dmat)
    if math.isnan(icc_d):
        de, n_eff = float("nan"), float("nan")
    else:
        de = 1.0 + (len(seeds) - 1) * icc_d
        n_eff = (n_pairs / de) if de else float("nan")
    return {
        "q": q, "n_pairs": n_pairs, "n_discordant": n_discordant,
        "ICC": icc_d, "ICC_N": icc_oneway(nmat), "ICC_X": icc_oneway(xmat),
        "DE": de, "n_eff": n_eff,
        "icc_disclosure": bool(not math.isnan(icc_d) and icc_d >= 0.6),
        "power_planning_frozen": dict(POWER_FROZEN),
    }


# ---------------------------------------------------------------------------
# terminal state machine ($10) and driver
# ---------------------------------------------------------------------------

def terminal_overall(holm_res, point, bounds, premises):
    """Frozen precedence: GO > PARTIAL > NO_GO > INCONCLUSIVE.

    Only reached when the E-harm premises hold (grid complete + headroom +
    hashes); otherwise the endpoint is NOT_ESTIMATED upstream.
    """
    five = all(premises[k] for k in
               ("grid_complete", "headroom_ok", "hash_ok", "parser_ok",
                "dumbness_ok"))
    if (all(holm_res[ep]["rejected"] for ep in ENDPOINTS)
            and point[EHARM] >= GO_POINT_FLOOR and five):
        return "GO"
    if holm_res[EHARM]["rejected"] and point[EHARM] >= GO_POINT_FLOOR:
        return "PARTIAL"
    if (bounds["mix_ub95"] < NOGO_MIX_UB
            and bounds["heat_ub975"] < NOGO_TYPE_UB
            and bounds["cool_ub975"] < NOGO_TYPE_UB):
        return "NO_GO"
    return "INCONCLUSIVE"


def analyze(results_dir, n_per_type=common.CONFIRMATORY_PER_TYPE,
            seeds=common.GRID_SEEDS, write=True):
    """Run the frozen analysis; return the report dict.

    Hard-refuse contract: if the bundle cannot be loaded or the grid is
    incomplete, the run raises SystemExit(2) after writing a NOT_ESTIMATED
    report (no estimand values are ever fabricated).
    """
    report = {"results_dir": results_dir, "schema": "partv.analysis.v1",
              "frozen": {"B": B_BOOT, "seed": common.SEED_BOOTSTRAP,
                         "alpha": ALPHA, "m": M_TESTS,
                         "noninf_margin": NONINF_MARGIN,
                         "n_per_type": n_per_type, "seeds": list(seeds)}}

    def refuse(reason, extra=None):
        report.update({"overall_state": "NOT_ESTIMATED",
                       "hard_refuse": True, "refuse_reason": reason})
        if extra:
            report.update(extra)
        _emit(report, results_dir, write)
        raise SystemExit(2)

    try:
        bundle = load_bundle(results_dir)
    except (OSError, ValueError, KeyError) as e:
        refuse("analysis bundle unreadable: %s" % e)

    audits = bundle["audits"]
    premises = {
        "hash_ok": bool(bundle["hash_ok"]),
        "headroom_ok": bool(audits.get("headroom", {}).get("passed")),
        "parser_ok": bool(audits.get("parser", {}).get("passed")),
        "dumbness_ok": bool(audits.get("dumbness", {}).get("passed")),
        "grid_complete": False,
    }
    report["hash_detail"] = bundle["hash_detail"]

    try:
        by_type = build_cluster_table(bundle, n_per_type=n_per_type,
                                      seeds=seeds)
        premises["grid_complete"] = True
    except IncompleteGrid as e:
        report["grid_problems"] = str(e)
    if not premises["hash_ok"]:
        refuse("pinned hash verification failed (builder / prompt package)",
               {"premises": premises})
    if not premises["grid_complete"]:
        refuse("incomplete confirmatory grid (hard refuse)",
               {"premises": premises})
    if not premises["headroom_ok"]:
        refuse("headroom precondition failed "
               "(section 7: whole experiment NOT_ESTIMATED)",
               {"premises": premises})

    # ---- estimation -----------------------------------------------------
    cv = cluster_values(by_type, bundle["cards"], audits, seeds=seeds)
    values = cv["values"]
    point = {ep: float(theta_hat(values[ep])) for ep in ENDPOINTS}

    service_estimable = premises["parser_ok"] and premises["dumbness_ok"]
    endpoint_state = {}
    p_raws, boots = {}, {}
    ci95 = {}
    for ep in ENDPOINTS:
        tb, tb_h, tb_c = bootstrap_replicates(values[ep])
        boots[ep] = {"mix": tb, "heat": tb_h, "cool": tb_c}
        ci95[ep] = [float(np.percentile(tb, 2.5)),
                    float(np.percentile(tb, 97.5))]
        if ep == EHARM:
            endpoint_state[ep] = "estimated"
        else:
            endpoint_state[ep] = ("estimated" if service_estimable
                                  else "not_estimated_keystone_p1")
        if endpoint_state[ep] != "estimated":
            p_raws[ep] = 1.0                       # keystone rule ($10)
        else:
            p_raws[ep] = p_raw_null_centered(tb, point[ep], THETA0[ep])
    holm_res = holm(p_raws)
    bounds = {"mix_ub95": float(np.percentile(boots[EHARM]["mix"], 95)),
              "heat_ub975": float(np.percentile(boots[EHARM]["heat"], 97.5)),
              "cool_ub975": float(np.percentile(boots[EHARM]["cool"], 97.5))}
    overall = terminal_overall(holm_res, point, bounds, premises)

    report.update({
        "overall_state": overall,
        "hard_refuse": False,
        "premises": premises,
        "endpoint_state": endpoint_state,
        "point": point,
        "p_raw": p_raws,
        "holm": holm_res,
        "ci95_percentile": ci95,
        "no_go_bounds": bounds,
        "power_header": power_header(by_type, seeds=seeds),
        "gate_decisions": cv["gates"],
    })
    _emit(report, results_dir, write)
    return report


def _jsonable(o):
    if isinstance(o, dict):
        return {k: _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
        return None
    if isinstance(o, np.generic):
        return _jsonable(o.item())
    return o


def _emit(report, results_dir, write):
    if not write:
        return
    os.makedirs(results_dir, exist_ok=True)
    with open(os.path.join(results_dir, "gate_analysis.json"), "w") as f:
        json.dump(_jsonable(report), f, indent=1, sort_keys=True)
    lines = ["# Part V gate analysis (frozen analyze_gate.py)", ""]
    hdr = report.get("power_header") or {}
    plan = hdr.get("power_planning_frozen", POWER_FROZEN)
    def _num(x):
        return float("nan") if x is None else x
    lines.append(
        "header: q=%.4g (plan %.4g)  ICC=%.4g (plan %.4g)  DE=%.4g "
        "(plan %.4g)  n_eff=%.4g (plan %.4g)%s" % (
            _num(hdr.get("q")), plan.get("q", float("nan")),
            _num(hdr.get("ICC")), plan.get("ICC", float("nan")),
            _num(hdr.get("DE")), plan.get("DE", float("nan")),
            _num(hdr.get("n_eff")), plan.get("n_eff", float("nan")),
            "  [ICC>=0.6 disclosure]" if hdr.get("icc_disclosure") else ""))
    lines.append("overall_state: %s" % report.get("overall_state"))
    if report.get("refuse_reason"):
        lines.append("refuse_reason: %s" % report["refuse_reason"])
    for ep in ENDPOINTS:
        if "p_raw" in report:
            h = report["holm"][ep]
            lines.append(
                "%s: point=%.6f p_raw=%.6f holm_rank=%d thr=%.4f rejected=%s "
                "ci95=[%.6f, %.6f] state=%s" % (
                    ep, report["point"][ep], report["p_raw"][ep],
                    h["rank"], h["threshold"], h["rejected"],
                    report["ci95_percentile"][ep][0],
                    report["ci95_percentile"][ep][1],
                    report["endpoint_state"][ep]))
    with open(os.path.join(results_dir, "GATE_ANALYSIS.md"), "w") as f:
        f.write("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# synthetic self-test fixtures (known expected outcomes)
# ---------------------------------------------------------------------------

def _fixture_dir(root, name):
    d = os.path.join(root, name)
    os.makedirs(os.path.join(d, "grid"), exist_ok=True)
    return d


def _write_bundle(d, rollouts, cards, audits):
    with open(os.path.join(d, "grid", "rollouts.jsonl"), "w") as f:
        for r in rollouts:
            f.write(json.dumps(r) + "\n")
    with open(os.path.join(d, "cards.json"), "w") as f:
        json.dump(cards, f)
    with open(os.path.join(d, "audits.json"), "w") as f:
        json.dump(audits, f)
    return d


def _synth_rollouts(tids, seeds, succ_fn, pool="confirmatory",
                    drop_last=False):
    """succ_fn(type, target_idx, seed, arm) -> 0/1."""
    rows = []
    for typ in ("heat", "cool"):
        for i, t in enumerate(tids[typ]):
            for s in seeds:
                for arm in common.ARMS:
                    rows.append({
                        "pool": pool, "type": typ, "target": t, "seed": s,
                        "arm": arm,
                        "success": int(succ_fn(typ, i, s, arm)),
                        "steps": 20, "goal": "put a %s pan on stoveburner" % (
                            "hot" if typ == "heat" else "cool"),
                    })
    if drop_last:
        rows.pop()
    return rows


_GOAL = {"heat": "put a hot pan on stoveburner",
         "cool": "put a cool pan on stoveburner"}

# consistent cards: R admits, X contradicts under G-struct; G-S sims from audits
_CARD = {
    "heat": {"R": " 1. heat pan 1 with microwave 1\nResult: SUCCESS.",
             "X": " 1. cool pan 1 in fridge 1\nResult: SUCCESS."},
    "cool": {"R": " 1. cool pan 1 in fridge 1\nResult: SUCCESS.",
             "X": " 1. heat pan 1 with microwave 1\nResult: SUCCESS."},
}


def _synth_cards(tids):
    cards = {}
    for typ in ("heat", "cool"):
        for t in tids[typ]:
            cards[t] = {"goal": _GOAL[typ],
                        "R": {"text": _CARD[typ]["R"], "tokens": 220},
                        "X": {"text": _CARD[typ]["X"], "tokens": 220}}
    return cards


def _synth_audits(tids, sims=(("R", 0.9), ("X", 0.9)),
                  parser_passed=True, dumbness_passed=True,
                  headroom_passed=True):
    gs = {}
    for typ in ("heat", "cool"):
        for t in tids[typ]:
            gs[t] = dict(sims)
    return {"tau_s": 0.5, "gs_sims": gs,
            "parser": {"passed": parser_passed},
            "dumbness": {"passed": dumbness_passed},
            "headroom": {"passed": headroom_passed, "chosen": "mem_A"}}


def _tids(n_per_type):
    return {"heat": ["t_heat_%02d" % i for i in range(n_per_type)],
            "cool": ["t_cool_%02d" % i for i in range(n_per_type)]}


def self_test(tmpdir):
    """Deterministic synthetic checks with known expected outcomes."""
    import tempfile
    n, seeds = 8, (0, 1)
    tids = _tids(n)
    results = {}

    # 1) clear GO: X always fails, N/R always succeed; G-struct == oracle.
    d = _fixture_dir(tmpdir, "go")
    sf = lambda ty, i, s, a: 0 if a == "X" else 1
    _write_bundle(d, _synth_rollouts(tids, seeds, sf), _synth_cards(tids),
                  _synth_audits(tids))
    rep = analyze(d, n_per_type=n, seeds=seeds, write=False)
    assert rep["overall_state"] == "GO", rep["overall_state"]
    assert rep["point"][EHARM] == 1.0
    assert all(rep["holm"][ep]["rejected"] for ep in ENDPOINTS)
    results["go"] = rep

    # 2) exact NO_GO: no effect anywhere (all succ 0.5 deterministic pattern is
    #    not possible on 0/1 with point exactly 0 and UB narrow; use succ all
    #    zero -> point exactly 0, bootstrap degenerate => UB 0 < bounds).
    d = _fixture_dir(tmpdir, "nogo")
    sf = lambda ty, i, s, a: 0
    _write_bundle(d, _synth_rollouts(tids, seeds, sf), _synth_cards(tids),
                  _synth_audits(tids))
    rep = analyze(d, n_per_type=n, seeds=seeds, write=False)
    assert rep["overall_state"] == "NO_GO", rep["overall_state"]
    assert rep["point"][EHARM] == 0.0
    assert rep["no_go_bounds"]["mix_ub95"] == 0.0
    results["nogo"] = rep

    # 3) INCONCLUSIVE: E-harm positive but below +5pp floor, service fine.
    #    X loses in 1 of (n*2) cells -> point = 1/32 ~ 3.1pp < 5pp.
    d = _fixture_dir(tmpdir, "incon")
    def sf3(ty, i, s, a, _tids=tids):
        if a == "X":
            return 0 if (ty == "heat" and i == 0 and s == 0) else 1
        return 1
    _write_bundle(d, _synth_rollouts(tids, seeds, sf3), _synth_cards(tids),
                  _synth_audits(tids, sims=(("R", 0.9), ("X", 0.9))))
    rep = analyze(d, n_per_type=n, seeds=seeds, write=False)
    assert rep["overall_state"] == "INCONCLUSIVE", (rep["overall_state"],
                                                    rep["point"])
    assert 0 < rep["point"][EHARM] < GO_POINT_FLOOR
    results["inconclusive"] = rep

    # 4) PARTIAL via keystone: service premises fail -> p_raw=1 for 2),3).
    d = _fixture_dir(tmpdir, "partial")
    sf = lambda ty, i, s, a: 0 if a == "X" else 1
    _write_bundle(d, _synth_rollouts(tids, seeds, sf), _synth_cards(tids),
                  _synth_audits(tids, parser_passed=False))
    rep = analyze(d, n_per_type=n, seeds=seeds, write=False)
    assert rep["overall_state"] == "PARTIAL", rep["overall_state"]
    assert rep["p_raw"][ESERVE] == 1.0 and rep["p_raw"][EORACLE] == 1.0
    assert rep["holm"][EHARM]["rejected"]
    results["partial"] = rep

    # 5) hard refuse on incomplete grid (missing final rollout row).
    d = _fixture_dir(tmpdir, "incomplete")
    _write_bundle(d, _synth_rollouts(tids, seeds,
                                     (lambda ty, i, s, a: 1), drop_last=True),
                  _synth_cards(tids), _synth_audits(tids))
    try:
        analyze(d, n_per_type=n, seeds=seeds, write=False)
        raise AssertionError("expected SystemExit(2) on incomplete grid")
    except SystemExit as e:
        assert e.code == 2
    results["incomplete"] = "SystemExit(2) OK"

    # 6) hash mismatch -> NOT_ESTIMATED (monkeypatch verifier).
    d = _fixture_dir(tmpdir, "hashbad")
    sf = lambda ty, i, s, a: 0 if a == "X" else 1
    _write_bundle(d, _synth_rollouts(tids, seeds, sf), _synth_cards(tids),
                  _synth_audits(tids))
    orig = common.verify_builder
    common.verify_builder = lambda: (_ for _ in ()).throw(
        common.FrozenHashMismatch("forced"))
    try:
        try:
            analyze(d, n_per_type=n, seeds=seeds, write=False)
            raise AssertionError("expected SystemExit(2) on hash mismatch")
        except SystemExit as e:
            assert e.code == 2
    finally:
        common.verify_builder = orig
    results["hash_mismatch"] = "SystemExit(2) OK"

    # 7) q / ICC recompute sanity on fixture 1: every (target,seed) N=1 X=0
    #    -> q = 1.0, ICC of d (all identical rows) is nan-tolerant; DE nan.
    d = _fixture_dir(tmpdir, "go2")
    _write_bundle(d, _synth_rollouts(tids, seeds, sf), _synth_cards(tids),
                  _synth_audits(tids))
    rep = analyze(d, n_per_type=n, seeds=seeds, write=False)
    assert rep["power_header"]["q"] == 1.0
    results["power_header"] = "q=1.0 OK"
    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--results-dir", default=common.OUT_ROOT)
    ap.add_argument("--n-per-type", type=int,
                    default=common.CONFIRMATORY_PER_TYPE)
    ap.add_argument("--seeds", type=int, nargs="+",
                    default=list(common.GRID_SEEDS))
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            res = self_test(td)
        for k, v in res.items():
            print("self-test %-12s: %s" % (k, v if isinstance(v, str)
                                           else v["overall_state"]))
        print("ALL SELF-TESTS PASSED")
        return
    try:
        rep = analyze(args.results_dir, n_per_type=args.n_per_type,
                      seeds=tuple(args.seeds), write=not args.no_write)
    except SystemExit as e:
        if e.code == 2:
            print("NOT_ESTIMATED (hard refuse); see gate_analysis.json")
        raise
    print("overall_state:", rep["overall_state"])
    for ep in ENDPOINTS:
        h = rep["holm"][ep]
        print("%-16s point=%+.4f p=%.6f thr=%.4f rejected=%s" % (
            ep, rep["point"][ep], rep["p_raw"][ep], h["threshold"],
            h["rejected"]))


if __name__ == "__main__":
    main()
