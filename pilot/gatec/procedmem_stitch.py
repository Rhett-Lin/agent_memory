"""Gate C-lite cond2: can the Proced-Mem structural signal (memory-task
embedding similarity) and the STITCH intent signal (LLM goal/constraint
mismatch probe) predict F-MED's quantities -- the P label, the paired uplift
vs N, and paired harmful flips on A01 cells?

Runs in three one-command modes (from repo root):

  (a)  python pilot/gatec/procedmem_stitch.py --mode a
       Proced-Mem structural signal, analysis only (CPU, no new rollouts).
       Tests (Holm family, m=6, alpha 0.05):
         T1  AUC: sim_embed -> P label within S=0 bucket {A00(P=0),A10(P=1)}
         T2  AUC: sim_embed -> P label within S=1 bucket {A01(P=0),A11(P=1)}
         T3  logistic slope: paired uplift vs N on pooled A-cells
             (units with Y_N=1; y=1[Y_c=1]; x=sim_embed), qwen7b and qwen3b
         T4  logistic slope: paired harmful flip on A01
             (units with Y_N=1; y=1[Y_A01=0]; x=sim_embed(A01)), 7b and 3b
       sim_tf variants of all six are computed as exploratory replication
       (never enter the Holm family).

  (b)  python pilot/gatec/procedmem_stitch.py --mode probe
       STITCH intent probe: Qwen2.5-7B-Instruct via vLLM offline
       (gpu_memory_utilization=0.85, temperature 0, seed fixed) judges
       memory-task pairs with the frozen STITCH_PROBE_PROMPT below.
       Units: 8 families (seeded draw, PROBE_FAMILY_SEED) x cells
       {A00,A01,A10,A11} x 4 siblings x 4 seeds = 512 judgments, saved
       VERBATIM (full prompt + raw response) to
       pilot/gatec/stitch_probe_judgments.jsonl. Nothing is fabricated:
       every alarm in the analysis traces to a raw model completion.

  (c)  python pilot/gatec/procedmem_stitch.py --mode b
       Joins judgments with pilot rollouts: alarm rate by cell class;
       per-family paired alarm vs actual harmful-flip correlation
       (Spearman, 8 families, family-cluster bootstrap CI); odds ratio of
       flip rates in alarmed vs unalarmed A01 units; Holm over m=2.

Inference convention: family-cluster bootstrap, 2000 reps, seed = config
analysis.bootstrap_seed; ONE aligned family resample per rep across all
tests/models so p-values are comparable.
"""

import argparse
import csv
import glob
import json
import os
import platform
import re
import sys
import time

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_PILOT = os.path.dirname(_HERE)
_REPO = os.path.dirname(_PILOT)
sys.path.insert(0, _PILOT)

from generate_families import load_config  # noqa: E402

CONFIG = os.path.join(_PILOT, "configs", "pilot_7b.yaml")
OUT_A = os.path.join(_HERE, "procedmem_results.json")
OUT_B = os.path.join(_HERE, "stitch_results.json")
JUDGMENTS = os.path.join(_HERE, "stitch_probe_judgments.jsonl")

A_CELLS = ["A00", "A01", "A10", "A11"]
CELLS = A_CELLS + ["N", "Q"]
MODELS = ["qwen7b", "qwen3b"]

# STITCH probe frozen settings (any change here invalidates comparability of
# stitch_probe_judgments.jsonl; record a new seed/file instead of editing).
PROBE_MODEL_KEY = "qwen7b"          # config models.qwen7b
PROBE_GPU_MEM_UTIL = 0.85
PROBE_TEMPERATURE = 0.0
PROBE_MAX_TOKENS = 96
PROBE_SEED = 20260808
PROBE_FAMILY_SEED = 20260808        # seeded 8-family draw
PROBE_N_FAMILIES = 8

# Frozen intent-mismatch prompt in STITCH's spirit (STITCH / CAME-Bench,
# arXiv 2601.10702, ACL 2026 Findings: surface-near but intent/goal-
# incompatible memory traps; contextual-intent gating): judge whether the
# memory's GOAL / CONSTRAINT mismatches the task's goal or action type.
# Verbatim template; the probe prompt for every unit is stored unmodified in
# stitch_probe_judgments.jsonl.
STITCH_PROBE_PROMPT = """\
You are auditing whether a stored agent memory should be trusted for a new
task. Judge ONLY intent alignment: does the memory's goal, policy, threshold,
direction, or constraint MISMATCH what the new task requires -- including the
case where the memory solves an unrelated problem? Surface wording overlap is
NOT the question; judge the intended procedure and its conditions.

[TASK]
<<<TASK>>>

[MEMORY]
<<<MEMORY>>>

Reply with exactly one JSON object on one line and nothing else:
{"mismatch": "yes" or "no", "confidence": <integer 1-5>, "reason": "<=20 words"}
"mismatch":"yes" means following this memory would pursue a goal that
conflicts with, or is unrelated to, the task's required goal or action type."""


# ---------------------------------------------------------------------------
# shared loading
# ---------------------------------------------------------------------------

def load_rolls(out_root, model):
    """(fam, sib, seed, cell) -> success for pilot procedural rolls."""
    unit = {}
    files = sorted(glob.glob(os.path.join(
        out_root, "rollouts_%s_shard*-of-*.jsonl" % model)))
    files = [f for f in files if "_hc_" not in os.path.basename(f)]
    for fn in files:
        with open(fn) as f:
            for line in f:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                m = r.get("meta", {})
                if m.get("model", model) != model:
                    continue
                if m.get("system", "procedural") != "procedural":
                    continue
                unit[(m["family_idx"], m["sibling_idx"], m["seed"],
                      m["cell"])] = bool(r["success"])
    return unit, files


def load_sim(sealed):
    """(fam, sib, cell) -> dict(sim_embed, sim_tf, P)."""
    sim = {}
    with open(os.path.join(sealed, "sim_report.csv")) as f:
        for r in csv.DictReader(f):
            sim[(int(r["family_idx"]), int(r["target_sibling"]), r["cell"])] = {
                "sim_embed": float(r["sim_embed"]),
                "sim_tf": float(r["sim_tf"]),
                "P": int(r["P"]) if r["P"] not in ("", "None") else None,
            }
    return sim


# ---------------------------------------------------------------------------
# small statistics
# ---------------------------------------------------------------------------

def auc_mannwhitney(x1, x0):
    """P(x1 > x0) + 0.5 P(tie), all pairs."""
    x1 = np.asarray(x1, float)
    x0 = np.asarray(x0, float)
    if len(x1) == 0 or len(x0) == 0:
        return float("nan")
    gt = (x1[:, None] > x0[None, :]).sum()
    eq = (x1[:, None] == x0[None, :]).sum()
    return float((gt + 0.5 * eq) / (len(x1) * len(x0)))


def logit_fit(x, y, iters=50):
    """Newton ML fit of y ~ sigmoid(b0 + b1*x) with tiny L2; returns (b0,b1)
    or (nan,nan) when y is single-class."""
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    if len(np.unique(y)) < 2:
        return float("nan"), float("nan")
    X = np.column_stack([np.ones_like(x), x])
    beta = np.zeros(2)
    lam = 1e-6
    for _ in range(iters):
        eta = np.clip(X @ beta, -30, 30)
        p = 1.0 / (1.0 + np.exp(-eta))
        W = np.clip(p * (1 - p), 1e-9, None)
        g = X.T @ (y - p) - lam * beta
        H = (X * W[:, None]).T @ X + lam * np.eye(2)
        try:
            step = np.linalg.solve(H, g)
        except np.linalg.LinAlgError:
            return float("nan"), float("nan")
        beta += step
        if np.max(np.abs(step)) < 1e-8:
            break
    return float(beta[0]), float(beta[1])


def spearman(a, b):
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    ra = (ra - ra.mean()) / ra.std()
    rb = (rb - rb.mean()) / rb.std()
    return float((ra * rb).mean())


def p_sign(vals):
    v = np.asarray(vals, float)
    v = v[~np.isnan(v)]
    if len(v) == 0:
        return float("nan")
    return min(1.0, 2 * min(float(np.mean(v <= 0)), float(np.mean(v >= 0))))


def ci_of(vals, pe, null=0.0):
    v = np.asarray(vals, float)
    v = v[~np.isnan(v)]
    if len(v) < 10:
        return {"est": float(pe) if pe == pe else None, "ci": [None, None],
                "p_boot": None, "n_boot_ok": len(v), "null_value": null}
    return {"est": float(pe), "ci": [float(np.quantile(v, 0.025)),
                                     float(np.quantile(v, 0.975))],
            "p_boot": p_sign(v - null), "n_boot_ok": len(v),
            "null_value": null,
            "ci_excludes_null": bool(np.quantile(v, 0.025) > null
                                     or np.quantile(v, 0.975) < null)}


def holm(pvals):
    order = sorted(range(len(pvals)), key=lambda i: pvals[i][1])
    m = len(pvals)
    adj, running = {}, 0.0
    for rank, i in enumerate(order):
        val = min(1.0, (m - rank) * pvals[i][1])
        running = max(running, val)
        adj[pvals[i][0]] = running
    return adj


# ---------------------------------------------------------------------------
# mode a: Proced-Mem structural signal
# ---------------------------------------------------------------------------

def mode_a(cfg):
    sealed, out_root = cfg["paths"]["sealed"], cfg["paths"]["output_root"]
    seed, nboot = cfg["analysis"]["bootstrap_seed"], 2000
    sim = load_sim(sealed)
    rolls = {m: load_rolls(out_root, m)[0] for m in MODELS}
    fam_universe = sorted({k[0] for k in sim})
    fpos = {f: i for i, f in enumerate(fam_universe)}

    # T1/T2 units: one per (fam,sib,cell) memory in the S buckets
    buckets = {"S0": (["A00", "A10"], "sim->P within S=0"),
               "S1": (["A01", "A11"], "sim->P within S=1")}
    auc_units = {}
    for bk, (cells, _) in buckets.items():
        units = []  # (fam_idx_pos, P, sim_embed, sim_tf)
        for (f, s, c), d in sim.items():
            if c in cells and d["P"] is not None:
                units.append((fpos[f], d["P"], d["sim_embed"], d["sim_tf"]))
        auc_units[bk] = units

    # T3/T4 units per model: (fam_pos, x_embed, x_tf, y)
    def t3_units(unit, metric):
        out = []
        for (f, s, sd, c), ok in unit.items():
            if c not in A_CELLS:
                continue
            if not unit.get((f, s, sd, "N")):
                continue  # paired uplift defined on Y_N=1 subset
            d = sim[(f, s, c)]
            out.append((fpos[f], d[metric], float(ok)))
        return out

    def t4_units(unit, metric):
        out = []
        for (f, s, sd, c), ok in unit.items():
            if c != "A01":
                continue
            if not unit.get((f, s, sd, "N")):
                continue  # harmful flip = Y_N=1 AND Y_A01=0
            d = sim[(f, s, c)]
            out.append((fpos[f], d[metric], float(not ok)))
        return out

    def eval_auc(units, idx, metric_col):
        x1 = [u[metric_col] for u in units if u[1] == 1 for _ in
              range((idx == u[0]).sum())]
        x0 = [u[metric_col] for u in units if u[1] == 0 for _ in
              range((idx == u[0]).sum())]
        return auc_mannwhitney(x1, x0)

    def eval_slope(units, idx):
        xs, ys = [], []
        for u in units:
            rep = (idx == u[0]).sum()
            xs += [u[1]] * rep
            ys += [u[2]] * rep
        return logit_fit(xs, ys)[1]

    tests = {("T1", "sim_embed"), ("T2", "sim_embed"),
             ("T3", "qwen7b", "sim_embed"), ("T3", "qwen3b", "sim_embed"),
             ("T4", "qwen7b", "sim_embed"), ("T4", "qwen3b", "sim_embed"),
             ("T1", "sim_tf"), ("T2", "sim_tf"),
             ("T3", "qwen7b", "sim_tf"), ("T3", "qwen3b", "sim_tf"),
             ("T4", "qwen7b", "sim_tf"), ("T4", "qwen3b", "sim_tf")}

    # point estimates
    pe = {}
    for bk, (cells, _) in buckets.items():
        for metric in ("sim_embed", "sim_tf"):
            col = "sim_embed" if metric == "sim_embed" else "sim_tf"
            units = auc_units[bk]
            x1 = [u[2 if col == "sim_embed" else 3] for u in units if u[1] == 1]
            x0 = [u[2 if col == "sim_embed" else 3] for u in units if u[1] == 0]
            pe[("%s" % ("T1" if bk == "S0" else "T2"), None, metric)] = \
                auc_mannwhitney(x1, x0)
    for metric in ("sim_embed", "sim_tf"):
        for m in MODELS:
            pe[("T3", m, metric)] = logit_fit(
                [u[1] for u in t3_units(rolls[m], metric)],
                [u[2] for u in t3_units(rolls[m], metric)])[1]
            pe[("T4", m, metric)] = logit_fit(
                [u[1] for u in t4_units(rolls[m], metric)],
                [u[2] for u in t4_units(rolls[m], metric)])[1]

    # bootstrap
    rng = np.random.default_rng(seed)
    F = len(fam_universe)
    boots = {k: [] for k in pe}
    unit_cache = {}
    for metric in ("sim_embed", "sim_tf"):
        for m in MODELS:
            unit_cache[("T3", m, metric)] = t3_units(rolls[m], metric)
            unit_cache[("T4", m, metric)] = t4_units(rolls[m], metric)
    for rep in range(nboot):
        idx = rng.integers(0, F, F)
        for bk, t in (("S0", "T1"), ("S1", "T2")):
            for ci, metric in ((2, "sim_embed"), (3, "sim_tf")):
                boots[(t, None, metric)].append(
                    eval_auc(auc_units[bk], idx, ci))
        for m in MODELS:
            for metric in ("sim_embed", "sim_tf"):
                boots[("T3", m, metric)].append(
                    eval_slope(unit_cache[("T3", m, metric)], idx))
                boots[("T4", m, metric)].append(
                    eval_slope(unit_cache[("T4", m, metric)], idx))
        if (rep + 1) % 500 == 0:
            print("[mode a] bootstrap %d/%d" % (rep + 1, nboot), flush=True)

    results = {"mode": "a_procedmem_structural_signal",
               "bootstrap": {"reps": nboot, "seed": seed,
                             "cluster": "family", "aligned": True},
               "tests": {}, "exploratory_sim_tf": {}}
    pvals = []
    for (t, m, metric), v in sorted(pe.items(), key=str):
        name = t + ("" if m is None else "@%s" % m)
        # AUC tests (T1/T2) test against the chance level 0.5; slope tests
        # (T3/T4) against 0.
        d = ci_of(boots[(t, m, metric)], v, null=0.5 if m is None else 0.0)
        if metric == "sim_embed":
            results["tests"][name] = d
            pvals.append((name, d["p_boot"] if d["p_boot"] is not None else 1.0))
        else:
            results["exploratory_sim_tf"][name] = d
    holm_adj = holm(pvals)
    results["holm_family_m6"] = {
        k: {"p_raw": dict(pvals)[k], "p_holm": holm_adj[k],
            "reject_0.05": bool(holm_adj[k] < 0.05)} for k, _ in pvals}
    results["unit_counts"] = {
        "T1_S0_memories": len(auc_units["S0"]),
        "T2_S1_memories": len(auc_units["S1"]),
        "T3_units_per_model": {m: len(unit_cache[("T3", m, "sim_embed")])
                               for m in MODELS},
        "T4_units_per_model": {m: len(unit_cache[("T4", m, "sim_embed")])
                               for m in MODELS},
    }
    results["env"] = {"python": sys.version.split()[0],
                      "numpy": np.__version__, "platform": platform.platform()}
    with open(OUT_A, "w") as f:
        json.dump(results, f, indent=1)
    print("[write] %s" % OUT_A)
    print("\n=== mode a: Proced-Mem structural signal (sim_embed) ===")
    for name, d in results["tests"].items():
        print("%-10s est=%+.4f CI=[%s,%s] p_boot=%s"
              % (name, d["est"],
                 ("%.4f" % d["ci"][0]) if d["ci"][0] is not None else "  n/a ",
                 ("%.4f" % d["ci"][1]) if d["ci"][1] is not None else "  n/a ",
                 ("%.4f" % d["p_boot"]) if d["p_boot"] is not None else " n/a "))
    print("--- Holm (m=6) ---")
    for k, v in results["holm_family_m6"].items():
        print("%-10s p_raw=%.4f p_holm=%.4f reject=%s"
              % (k, v["p_raw"], v["p_holm"], v["reject_0.05"]))
    print("--- exploratory sim_tf replication ---")
    for name, d in results["exploratory_sim_tf"].items():
        print("%-10s est=%+.4f CI=[%s,%s]"
              % (name, d["est"],
                 ("%.4f" % d["ci"][0]) if d["ci"][0] is not None else "  n/a ",
                 ("%.4f" % d["ci"][1]) if d["ci"][1] is not None else "  n/a "))


# ---------------------------------------------------------------------------
# mode probe: STITCH intent LLM probe (GPU, vLLM)
# ---------------------------------------------------------------------------

# ------------------------------------------------------------------
# shared verdict parser: the 7B sometimes echoes an instruction line and/or
# repeats the JSON object several times, so scan per-object candidates (no
# nesting is ever produced by the frozen prompt) and take the FIRST object
# that json-parses and carries a valid "mismatch".
# ------------------------------------------------------------------
_JSON_CAND = re.compile(r"\{[^{}]*\}", re.S)


def parse_verdict(raw):
    for mjson in _JSON_CAND.finditer(raw):
        try:
            j = json.loads(mjson.group(0))
        except Exception:
            continue
        v = str(j.get("mismatch", "")).strip().lower()
        if v not in ("yes", "no"):
            continue
        conf = j.get("confidence")
        try:
            conf = int(conf)
        except Exception:
            conf = None
        return v, conf, j.get("reason")
    return None, None, None


def mode_reparse(cfg):
    """Re-parse verdicts from the VERBATIM saved raw responses (no GPU, no
    new model calls; prompt_verbatim and raw_response bytes are left
    untouched -- only the derived parsed/parse_ok fields are recomputed
    after a parser fix)."""
    recs, n_ok = [], 0
    with open(JUDGMENTS) as f:
        for line in f:
            d = json.loads(line)
            v, conf, reason = parse_verdict(d["raw_response"])
            d["parsed"] = {"mismatch": v, "confidence": conf,
                           "reason": reason}
            d["parse_ok"] = v is not None
            d["reparse_note"] = ("parsed fields recomputed from verbatim "
                                 "raw_response; bytes unchanged")
            n_ok += int(d["parse_ok"])
            recs.append(d)
    with open(JUDGMENTS, "w") as f:
        for d in recs:
            f.write(json.dumps(d) + "\n")
    print("[reparse] %d/%d parse-ok -> %s" % (n_ok, len(recs), JUDGMENTS))


def mode_probe(cfg):
    os.environ.setdefault("HF_HOME", cfg["paths"]["hf_home"])
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("VLLM_LOGGING_LEVEL", "WARNING")
    sealed = cfg["paths"]["sealed"]

    mems = {}
    with open(os.path.join(sealed, "memories_sealed.jsonl")) as f:
        for line in f:
            r = json.loads(line)
            if r["cell"] in A_CELLS:
                mems[(r["family_idx"], r["target_sibling"], r["cell"])] = r
    tasks = {}
    with open(os.path.join(sealed, "tasks_sealed.jsonl")) as f:
        for line in f:
            r = json.loads(line)
            if r["kind"] == "sibling":
                tasks[(r["family_idx"], r["sibling_idx"], r["seed"])] = r

    rng = np.random.default_rng(PROBE_FAMILY_SEED)
    fam_pool = sorted({k[0] for k in mems})
    fam_pick = sorted(rng.choice(fam_pool, size=PROBE_N_FAMILIES,
                                 replace=False).tolist())
    seeds = cfg["grid"]["seeds"]
    units = []
    for f in fam_pick:
        for s in range(cfg["generation"]["siblings_per_family"]):
            for c in A_CELLS:
                for sd in seeds:
                    units.append((f, s, sd, c))
    print("[probe] families=%s units=%d" % (fam_pick, len(units)))

    prompts = []
    for (f, s, sd, c) in units:
        t = tasks[(f, s, sd)]
        m = mems[(f, s, c)]
        prompts.append(STITCH_PROBE_PROMPT
                       .replace("<<<TASK>>>", t["instruction"])
                       .replace("<<<MEMORY>>>", m["text"]))

    from vllm import LLM, SamplingParams  # deferred: GPU only in this mode
    llm = LLM(model=cfg["models"][PROBE_MODEL_KEY],
              gpu_memory_utilization=PROBE_GPU_MEM_UTIL,
              seed=PROBE_SEED, max_model_len=4096, enforce_eager=False)
    sp = SamplingParams(temperature=PROBE_TEMPERATURE,
                        max_tokens=PROBE_MAX_TOKENS, seed=PROBE_SEED)
    t0 = time.time()
    outs = llm.generate(prompts, sp)
    print("[probe] generated %d completions in %.1fs"
          % (len(outs), time.time() - t0))

    n_written, n_parsed = 0, 0
    with open(JUDGMENTS, "w") as f:
        for (f_, s, sd, c), prompt, out in zip(units, prompts, outs):
            raw = out.outputs[0].text
            verdict, conf, reason = parse_verdict(raw)
            parse_ok = verdict is not None
            rec = {"family_idx": f_, "sibling_idx": s, "seed": sd, "cell": c,
                   "memory_id": mems[(f_, s, c)]["memory_id"],
                   "task_id": tasks[(f_, s, sd)]["task_id"],
                   "prompt_verbatim": prompt, "raw_response": raw,
                   "parsed": {"mismatch": verdict, "confidence": conf,
                              "reason": reason},
                   "parse_ok": parse_ok,
                   "probe": {"model": cfg["models"][PROBE_MODEL_KEY],
                             "temperature": PROBE_TEMPERATURE,
                             "seed": PROBE_SEED,
                             "prompt_sha8":
                                 __import__("hashlib").sha1(
                                     STITCH_PROBE_PROMPT.encode()).hexdigest()[:8]},
                   "ts": time.strftime("%Y-%m-%d %H:%M:%S")}
            f.write(json.dumps(rec) + "\n")
            n_written += 1
            n_parsed += int(parse_ok)
    print("[probe] wrote %d judgments (%d parse-ok) -> %s"
          % (n_written, n_parsed, JUDGMENTS))


# ---------------------------------------------------------------------------
# mode b: STITCH alarm vs F-MED quantities
# ---------------------------------------------------------------------------

def mode_b(cfg):
    out_root = cfg["paths"]["output_root"]
    seed, nboot = cfg["analysis"]["bootstrap_seed"], 2000
    rolls = {m: load_rolls(out_root, m)[0] for m in MODELS}
    judgments = []
    with open(JUDGMENTS) as f:
        for line in f:
            d = json.loads(line)
            if d["parse_ok"]:
                judgments.append(d)
    fam_pick = sorted({j["family_idx"] for j in judgments})
    fam_universe = fam_pick  # cluster bootstrap over the probed families
    F = len(fam_universe)

    alarm = {}  # (fam,sib,seed,cell) -> 1/0
    conf = {}
    for j in judgments:
        alarm[(j["family_idx"], j["sibling_idx"], j["seed"], j["cell"])] = \
            int(j["parsed"]["mismatch"] == "yes")
        conf[(j["family_idx"], j["sibling_idx"], j["seed"], j["cell"])] = \
            j["parsed"]["confidence"]

    fpos = {f: i for i, f in enumerate(fam_universe)}

    def eval_all(idx):
        """All mode-b statistics for one family resample (idx over
        fam_universe positions)."""
        out = {}
        # alarm rate by cell
        for c in A_CELLS:
            num, den = 0.0, 0.0
            for (f, s, sd, cc), a in alarm.items():
                if cc != c:
                    continue
                rep = (idx == fpos[f]).sum()
                den += rep
                num += a * rep
            out["alarm_%s" % c] = num / den if den else float("nan")
        out["alarm_A01_minus_A11"] = out["alarm_A01"] - out["alarm_A11"]
        # per-family vectors for Spearman (probed families only; use all
        # distinct families once each -- resampled with repetition)
        for m in MODELS:
            fa, ff = [], []
            for fam in [fam_universe[i] for i in idx]:
                aa, an_, fn, fd = 0, 0, 0, 0
                for (f, s, sd, c), a in alarm.items():
                    if f != fam or c != "A01":
                        continue
                    aa += a
                    an_ += 1
                    yn = rolls[m].get((f, s, sd, "N"))
                    ya = rolls[m].get((f, s, sd, "A01"))
                    if yn is True and ya is not None:
                        fd += 1
                        fn += int(not ya)
                fa.append(aa / an_ if an_ else float("nan"))
                ff.append(fn / fd if fd else float("nan"))
            ok = [i for i in range(len(fa))
                  if fa[i] == fa[i] and ff[i] == ff[i]]
            out["spearman_%s" % m] = (spearman([fa[i] for i in ok],
                                               [ff[i] for i in ok])
                                      if len(set(ok)) >= 3 else float("nan"))
            # odds ratio on A01 units with Y_N=1
            f1, n1, f0, n0 = 0, 0, 0, 0
            for (f, s, sd, c), a in alarm.items():
                if c != "A01":
                    continue
                yn = rolls[m].get((f, s, sd, "N"))
                ya = rolls[m].get((f, s, sd, "A01"))
                if yn is not True or ya is None:
                    continue
                flip = int(not ya)
                rep = (idx == fpos[f]).sum()
                if a:
                    f1 += flip * rep
                    n1 += rep
                else:
                    f0 += flip * rep
                    n0 += rep
            out["flip_alarmed_%s" % m] = f1 / n1 if n1 else float("nan")
            out["flip_unalarmed_%s" % m] = f0 / n0 if n0 else float("nan")
            if min(f1, n1 - f1, f0, n0 - f0) > 0 and n1 and n0:
                out["logOR_%s" % m] = float(np.log(
                    (f1 / (n1 - f1)) / (f0 / (n0 - f0))))
            elif n1 and n0:  # Haldane-Anscombe fallback
                out["logOR_%s" % m] = float(np.log(
                    ((f1 + 0.5) / (n1 - f1 + 0.5))
                    / ((f0 + 0.5) / (n0 - f0 + 0.5))))
            else:
                out["logOR_%s" % m] = float("nan")
        return out

    point = eval_all(np.arange(F))
    rng = np.random.default_rng(seed)
    boots = {}
    for rep in range(nboot):
        idx = rng.integers(0, F, F)
        for k, v in eval_all(idx).items():
            boots.setdefault(k, []).append(v)
        if (rep + 1) % 500 == 0:
            print("[mode b] bootstrap %d/%d" % (rep + 1, nboot), flush=True)

    results = {"mode": "b_stitch_intent_signal",
               "probe_file": JUDGMENTS,
               "n_judgments_total": sum(1 for _ in open(JUDGMENTS)),
               "n_judgments_parsed": len(judgments),
               "probe_families": fam_pick,
               "bootstrap": {"reps": nboot, "seed": seed,
                             "cluster": "family (8 probed families -- coarse)",
                             "aligned": True},
               "alarm_by_cell": {}, "models": {}}
    for c in A_CELLS:
        results["alarm_by_cell"][c] = ci_of(boots["alarm_%s" % c],
                                            point["alarm_%s" % c])
    results["alarm_A01_minus_A11"] = ci_of(boots["alarm_A01_minus_A11"],
                                           point["alarm_A01_minus_A11"])
    pvals = []
    for m in MODELS:
        results["models"][m] = {
            "spearman_alarm_flip_A01": ci_of(boots["spearman_%s" % m],
                                             point["spearman_%s" % m]),
            "logOR_alarmed_vs_unalarmed_A01": ci_of(boots["logOR_%s" % m],
                                                    point["logOR_%s" % m]),
            "flip_rate_alarmed_A01": ci_of(boots["flip_alarmed_%s" % m],
                                           point["flip_alarmed_%s" % m]),
            "flip_rate_unalarmed_A01": ci_of(boots["flip_unalarmed_%s" % m],
                                             point["flip_unalarmed_%s" % m]),
        }
        pvals.append(("spearman@7b" if m == "qwen7b" else "spearman@3b",
                      results["models"][m]["spearman_alarm_flip_A01"]["p_boot"]))
        pvals.append(("logOR@7b" if m == "qwen7b" else "logOR@3b",
                      results["models"][m]["logOR_alarmed_vs_unalarmed_A01"]
                      ["p_boot"]))
    # Holm over the 7B inferential family (probe itself is 7B): 2 tests
    p7 = [(k, p if p is not None else 1.0) for k, p in pvals
          if k.endswith("@7b")]
    holm7 = holm(p7)
    results["holm_family_7b_m2"] = {k: {"p_raw": dict(p7)[k],
                                        "p_holm": holm7[k],
                                        "reject_0.05": bool(holm7[k] < 0.05)}
                                    for k, _ in p7}
    results["pvals_3b_descriptive"] = dict(pvals)
    results["env"] = {"python": sys.version.split()[0],
                      "numpy": np.__version__, "platform": platform.platform()}
    with open(OUT_B, "w") as f:
        json.dump(results, f, indent=1)
    print("[write] %s" % OUT_B)
    print("\n=== mode b: STITCH intent probe ===")
    print("judgments: %d total, %d parsed; families=%s"
          % (results["n_judgments_total"], results["n_judgments_parsed"],
             fam_pick))
    print("--- alarm rate by cell ---")
    for c in A_CELLS:
        d = results["alarm_by_cell"][c]
        print("  %s  %5.3f [%5.3f,%5.3f]" % (c, d["est"], d["ci"][0], d["ci"][1]))
    d = results["alarm_A01_minus_A11"]
    print("  A01-A11 alarm gap: %+.3f [%+.3f,%+.3f]" % (d["est"], d["ci"][0],
                                                       d["ci"][1]))
    for m in MODELS:
        r = results["models"][m]
        print("--- %s ---" % m)
        for k in ("spearman_alarm_flip_A01", "logOR_alarmed_vs_unalarmed_A01",
                  "flip_rate_alarmed_A01", "flip_rate_unalarmed_A01"):
            d = r[k]
            print("  %-32s %+.3f [%+.3f,%+.3f] p=%s"
                  % (k, d["est"], d["ci"][0], d["ci"][1],
                     "%.4f" % d["p_boot"] if d["p_boot"] is not None else "n/a"))
    print("--- Holm 7B (m=2) ---")
    for k, v in results["holm_family_7b_m2"].items():
        print("  %-12s p_raw=%.4f p_holm=%.4f reject=%s"
              % (k, v["p_raw"], v["p_holm"], v["reject_0.05"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True, choices=["a", "probe", "b"])
    ap.add_argument("--config", default=CONFIG)
    args = ap.parse_args()
    cfg = load_config(args.config)
    print("[env] python=%s numpy=%s platform=%s"
          % (sys.version.split()[0], np.__version__, platform.platform()))
    if args.mode == "a":
        mode_a(cfg)
    elif args.mode == "probe":
        mode_probe(cfg)
    else:
        mode_b(cfg)


if __name__ == "__main__":
    main()
