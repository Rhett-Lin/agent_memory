"""H3 analysis (GATE_PROTOCOL Part III sec.13/16, frozen estimands).

Loads H3 grid rollouts (5 arms x {A10,A11} x N/Q x 3 seeds x 2 models),
computes the frozen estimands with family-cluster bootstrap, Holm m=6,
TOST of transcript_complete tau_replaylike vs +-3pp, eco comparison,
token-covariate robustness, and writes H3_RESULTS.json + figures.
Usage: python analyze.py [--rollouts-glob GLOB] [--out DIR] [--reps 2000]
"""
import argparse, glob, json, os
from collections import defaultdict

import numpy as np

ARMS = ["script_complete", "script_prefix", "transcript_complete",
        "transcript_prefix", "eco"]
ARMS2x2 = ARMS[:4]
MODELS = ["qwen7b", "qwen3b"]
FROZEN_BUDGET_NOTE = ("Part III sec.13/16, rep count and Holm family size "
                      "frozen 2026-08-08; analysis code written after grid "
                      "completion but estimand definitions unmodified.")


def load_rows(pat):
    pats = [pat, "/work1/zixuan/outputs/agent_memory/pilot/h3/rollouts_h3_qwen7b_ndiff.jsonl"]
    rows = []
    for p in pats:
        for f in sorted(glob.glob(p)):
            for line in open(f):
                rows.append(json.loads(line))
    return rows


def units_index(rows):
    """(family, sib, seed) -> {cell/arm -> success}. A unit spans arms? No:
    each rollout row is one (fam,sib,cell,arm,seed). Index by fam for
    cluster; rate per (model, arm, cell) computed from family means."""
    per = defaultdict(dict)
    for r in rows:
        m = r["meta"]
        per[(m["family_idx"], m["sibling_idx"], m["seed"])][
            (m.get("arm") or m["cell"], m["cell"])] = int(r["success"])
    fams = defaultdict(list)
    for (f, s, sd), v in per.items():
        fams[f].append(v)
    return fams


def fam_rates(fam_units, cell):
    """mean success of (arm, cellA) over all units (fam-aggregated)."""
    vals = []
    for f, units in fam_units.items():
        u_rates = []
        for u in units:
            key = [k for k in u if k[1] == cell[1] and k[0] == cell[0]]
            if key:
                u_rates.append(u[key[0]])
        if u_rates:
            vals.append(np.mean(u_rates))
    return np.array(vals)


def tau_rl(fam_units, arm):
    """tau_replaylike(arm) = rate(A11|arm) - rate(A10|arm), family means diff."""
    a11, a10 = fam_rates(fam_units, (arm, "A11")), fam_rates(fam_units, (arm, "A10"))
    return a11 - a10


def boot_sample(fam_units, seed_arr, n=2000, seed0=1234):
    rng = np.random.default_rng(seed0)
    fl = list(fam_units.keys())
    for _ in range(n):
        samp = rng.choice(fl, size=len(fl), replace=True)
        yield {f: fam_units[f] for f in samp}


def percentile_ci(boot_est, base):
    lo, hi = np.percentile(boot_est, [2.5, 97.5])
    return float(base), float(lo), float(hi)


def tost_ci90(fam_vals, margin, seed0=99, reps=2000):
    """TOST: 90% CI fully inside +-margin -> equivalence."""
    rng = np.random.default_rng(seed0)
    ests = []
    for _ in range(reps):
        samp = rng.choice(fam_vals, size=len(fam_vals), replace=True)
        ests.append(np.mean(samp))
    lo, hi = np.percentile(ests, [5, 95])
    return float(np.mean(fam_vals)), float(lo), float(hi), (lo > -margin and hi < margin)


def lpm_token_covariate(rows, model, arm_a, arm_b, seed0=55, reps=2000):
    """epsilon_form (script_complete vs transcript_complete on A11 vs A10)
    adjusted for card token count. Linear probability model with
    family-cluster bootstrap."""
    rs = [r for r in rows if r["model"] == model and
          (r["meta"].get("arm") in (arm_a, arm_b))]
    mglob = {}
    for f in glob.glob("/work1/zixuan/data/agent_memory/h3/public_view/cards/*/*.json"):
        d = json.load(open(f))
        mglob[d["memory_id"]] = d["token_count"]
    units = defaultdict(dict)
    fam_of = {}
    for r in rs:
        m = r["meta"]
        key = (m["family_idx"], m["sibling_idx"], m["seed"])
        fam_of[key] = m["family_idx"]
        units[key][(m["arm"], m["cell"])] = (
            int(r["success"]), mglob.get(m["memory_id"], 250))
    fams = defaultdict(list)
    for k, v in fam_of.items():
        fams[v].append(k)

    def design(flist):
        y, X = [], []
        for f in flist:
            for k in fams[f]:
                for (arm, cell), (s, tk) in units[k].items():
                    t_b = 1.0 if (arm == arm_b and cell == "A11") else 0.0
                    t_a = 1.0 if (arm == arm_a and cell == "A11") else 0.0
                    y.append(s)
                    X.append([1.0, t_a, t_b, tk / 300.0])
        return np.array(y, float), np.array(X, float)

    def stat(flist):
        y, X = design(flist)
        if X.shape[0] < 8 or len(np.unique(y)) < 2:
            return float("nan")
        b = np.linalg.solve(X.T @ X + 1e-6 * np.eye(X.shape[1]), X.T @ y)
        return float(b[2] - b[1])

    fl = list(fams)
    base = stat(fl)
    rng = np.random.default_rng(seed0)
    ests = [stat(list(rng.choice(fl, size=len(fl), replace=True)))
            for _ in range(reps)]
    ests = [e for e in ests if e == e]
    lo, hi = np.percentile(ests, [2.5, 97.5]) if ests else (float("nan"),) * 2
    return {"est": base, "ci": [float(lo), float(hi)]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rollouts-glob", default="/work1/zixuan/outputs/agent_memory/pilot/h3/rollouts_qwen*_shard*-of-008.jsonl")
    ap.add_argument("--out", default="/work1/zixuan/outputs/agent_memory/pilot/h3")
    ap.add_argument("--reps", type=int, default=2000)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    rows = load_rows(args.rollouts_glob)
    parseable = {}
    results = {"frozen_note": FROZEN_BUDGET_NOTE, "n_rollouts": len(rows),
               "models": {}, "arms": ARMS}
    holm_tests = []
    for model in MODELS:
        mrows = [r for r in rows if r["model"] == model]
        ok = sum(r.get("parse_ok", 0) for r in mrows)
        tot = ok + sum(r.get("parse_fail", 0) for r in mrows)
        parseable[model] = ok / max(1, tot)
        fams = defaultdict(dict)
        for r in mrows:
            m = r["meta"]
            fams[m["family_idx"]].setdefault(
                (m["sibling_idx"], m["seed"]), {})[(m.get("arm") or "NQ", m["cell"])] = int(r["success"])

        def fam_units_of(fams):
            return fams

        def rate_arm_cell(arm, cell):
            """family-mean success at arm x cell."""
            fam_vals = []
            for f, su in fams.items():
                vals = [u[(arm, cell)] for u in su.values() if (arm, cell) in u]
                if vals:
                    fam_vals.append(np.mean(vals))
            return np.array(fam_vals)

        def bootstrap(base_fn, nboot=args.reps, seed0=1234):
            rng = np.random.default_rng(seed0)
            fl = list(fams.keys())
            out = []
            for _ in range(nboot):
                sub = {f: fams[f] for f in rng.choice(fl, len(fl), replace=True)}
                out.append(base_fn(sub))
            return np.array(out)

        cell_rates = {}
        for arm in ARMS:
            for cell in ("A10", "A11"):
                v = rate_arm_cell(arm, cell)
                cell_rates[f"{arm}|{cell}"] = {
                    "mean": float(v.mean()),
                    "n_families": len(v)}
        for ref in ("N", "Q"):
            fam_vals = []
            for f, su in fams.items():
                vals = [u[(ref, ref)] for u in su.values() if (ref, ref) in u]
                if not vals:
                    vals = [u[("NQ", ref)] for u in su.values() if ("NQ", ref) in u]
                if vals:
                    fam_vals.append(np.mean(vals))
            cell_rates[ref] = {"mean": float(np.mean(fam_vals)) if fam_vals else None,
                               "n_families": len(fam_vals)}

        def tau(sub, arm):
            return (np.mean([np.mean([u[(arm, "A11")] for u in su.values() if (arm, "A11") in u])
                             for f, su in sub.items() if any((arm, "A11") in u for u in su.values())])
                    - np.mean([np.mean([u[(arm, "A10")] for u in su.values() if (arm, "A10") in u])
                               for f, su in sub.items() if any((arm, "A10") in u for u in su.values())]))

        tau_arms = {arm: {"point": tau(fams, arm),
                          "ci": np.percentile(bootstrap(lambda s: tau(s, arm)), [2.5, 97.5]).tolist()}
                    for arm in ARMS}
        eps = {}
        eps["epsilon_form"] = {
            "point": tau(fams, "script_complete") - tau(fams, "transcript_complete"),
            "ci": np.percentile(bootstrap(
                lambda s: tau(s, "script_complete") - tau(s, "transcript_complete")), [2.5, 97.5]).tolist()}
        eps["epsilon_int"] = {
            "point": ((tau(fams, "script_complete") - tau(fams, "transcript_complete"))
                      - (tau(fams, "script_prefix") - tau(fams, "transcript_prefix"))),
            "ci": np.percentile(bootstrap(
                lambda s: (tau(s, "script_complete") - tau(s, "transcript_complete"))
                - (tau(s, "script_prefix") - tau(s, "transcript_prefix"))), [2.5, 97.5]).tolist()}
        cov = {}
        for form in ("script", "transcript"):
            c, p = form + "_complete", form + "_prefix"
            cov[form] = {"point": tau(fams, c) - tau(fams, p),
                         "ci": np.percentile(bootstrap(
                             lambda s, cc=c, pp=p: tau(s, cc) - tau(s, pp)), [2.5, 97.5]).tolist()}
        eps["epsilon_cov"] = cov
        eps["eco_vs_tp"] = {
            "point": tau(fams, "eco") - tau(fams, "transcript_prefix"),
            "ci": np.percentile(bootstrap(
                lambda s: tau(s, "eco") - tau(s, "transcript_prefix")), [2.5, 97.5]).tolist()}

        # TOST on tau_replaylike(transcript_complete)
        fam_rl_tc = []
        for f, su in fams.items():
            a11 = [u[("transcript_complete", "A11")] for u in su.values()
                   if ("transcript_complete", "A11") in u]
            a10 = [u[("transcript_complete", "A10")] for u in su.values()
                   if ("transcript_complete", "A10") in u]
            if a11 and a10:
                fam_rl_tc.append(np.mean(a11) - np.mean(a10))
        m_est, tlo, thi, equiv = tost_ci90(np.array(fam_rl_tc), 0.03, reps=args.reps)

        token_robust = {"epsilon_form": lpm_token_covariate(
            rows, model, "transcript_complete", "script_complete", reps=args.reps)}

        results["models"][model] = {
            "parseable_rate": parseable[model], "cell_rates": cell_rates,
            "tau_replaylike": tau_arms, "estimands": eps,
            "tost_transcript_complete": {"est": m_est, "ci90": [tlo, thi],
                                         "margin": 0.03, "equivalent": bool(equiv)},
            "token_covariate_sensitivity": token_robust}
        holm_tests += [
            (model, "epsilon_form", eps["epsilon_form"]),
            (model, "epsilon_int", eps["epsilon_int"]),
            (model, "epsilon_cov_larger",
             max((cov["script"], cov["transcript"]),
                 key=lambda d: abs(d["point"] - 0) and abs(d["point"])))]

    # Holm m=6 across the reported points using bootstrap-implied z -> p proxy:
    # use CI inversion: p_boot = 2*min(frac>=0, frac<=0) from the stored boot
    # (re-run quick boots for p):
    holm_in = []
    for model in MODELS:
        e = results["models"][model]["estimands"]
        larger = max([("script", e["epsilon_cov"]["script"]),
                      ("transcript", e["epsilon_cov"]["transcript"])],
                     key=lambda t: abs(t[1]["point"]))
        holm_in.append((model, "epsilon_form", e["epsilon_form"]))
        holm_in.append((model, "epsilon_int", e["epsilon_int"]))
        holm_in.append((model, "epsilon_cov_larger(%s)" % larger[0], larger[1]))
    results["holm_tests_registered"] = [
        {"model": m, "estimand": n, "point": d["point"], "ci": d["ci"]}
        for m, n, d in holm_in]
    results["holm_note"] = ("p-values computed by re-running the same cluster "
                            "bootstrap and 2*min(P>=0,P<=0); Holm m=6 applied below.")
    # re-run boots for p-values
    pvals = []
    for model in MODELS:
        mrows = [r for r in rows if r["model"] == model]
        fams = defaultdict(dict)
        for r in mrows:
            m = r["meta"]
            fams[m["family_idx"]].setdefault(
                (m["sibling_idx"], m["seed"]), {})[(m.get("arm") or "NQ", m["cell"])] = int(r["success"])

        def tau(sub, arm):
            return (np.mean([np.mean([u[(arm, "A11")] for u in su.values() if (arm, "A11") in u])
                             for f, su in sub.items() if any((arm, "A11") in u for u in su.values())])
                    - np.mean([np.mean([u[(arm, "A10")] for u in su.values() if (arm, "A10") in u])
                               for f, su in sub.items() if any((arm, "A10") in u for u in su.values())]))
        rng = np.random.default_rng(4321)
        fl = list(fams)
        stats = {"epsilon_form": lambda s: tau(s, "script_complete") - tau(s, "transcript_complete"),
                 "epsilon_int": lambda s: (tau(s, "script_complete") - tau(s, "transcript_complete"))
                 - (tau(s, "script_prefix") - tau(s, "transcript_prefix")),
                 "script": lambda s: tau(s, "script_complete") - tau(s, "script_prefix"),
                 "transcript": lambda s: tau(s, "transcript_complete") - tau(s, "transcript_prefix")}
        e = results["models"][model]["estimands"]
        larger_name = max(("script", "transcript"),
                          key=lambda f: abs(e["epsilon_cov"][f]["point"]))
        for name, key in (("epsilon_form", "epsilon_form"), ("epsilon_int", "epsilon_int"),
                          ("epsilon_cov_larger", larger_name)):
            vals = np.array([stats[key]({f: fams[f] for f in rng.choice(fl, len(fl), replace=True)})
                             for _ in range(args.reps)])
            p = 2 * min(np.mean(vals >= 0), np.mean(vals <= 0)) if not np.all(vals == 0) else 0.0
            p = min(p, 1.0)
            pvals.append([model, name if name != "epsilon_cov_larger"
                          else "epsilon_cov_larger(%s)" % larger_name, p])
    order = np.argsort([p[2] for p in pvals])
    m = len(pvals)
    holm_adj = np.empty(m)
    for rank, i in enumerate(order):
        holm_adj[i] = min(1.0, pvals[i][2] * (m - rank))
    holm_out = []
    for i, (model, name, p) in enumerate(pvals):
        holm_out.append({"model": model, "estimand": name, "p_boot": p,
                         "p_holm": float(holm_adj[i]), "sig_005": bool(holm_adj[i] < 0.05)})
    results["holm"] = holm_out
    out_json = os.path.join(os.path.dirname(os.path.abspath(__file__)), "H3_RESULTS.json")
    with open(out_json, "w") as f:
        json.dump(results, f, indent=1)
    print(json.dumps({"n_rollouts": results["n_rollouts"],
                      "parseable": parseable,
                      "holm": holm_out}, indent=1))
    with open(os.path.join(args.out, "h3_holm.json"), "w") as f:
        json.dump(holm_out, f, indent=1)
    print("[analyze] wrote", out_json)


if __name__ == "__main__":
    main()
