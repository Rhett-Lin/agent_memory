"""Shared loaders / statistics for the Gate B causal-validity audit.

Read-only with respect to the pilot: imports pilot.analyze and
pilot.generate_families but never modifies existing pilot modules.

Conventions used by every audit script:
  * family-cluster bootstrap (families resampled with replacement),
    2000 reps, percentile 95% CI, seeds derived from AUDIT_SEED;
  * results written as JSON to pilot/audit/results/<name>.json;
  * cell labels: A00 (P=0,S=0), A01 (P=0,S=1 near-miss), A10 (P=1,S=0),
    A11 (P=1,S=1), N (no memory), Q (sham);
  * tau_struct  = rate(A10) - rate(A00)
    tau_trap    = rate(A01) - rate(A00)
    replay      = rate(A11) - rate(A10)
    tau_PxS     = (A11 - A01) - (A10 - A00).
"""

import csv
import glob
import json
import os
import sys
from collections import defaultdict

import numpy as np

AUDIT_DIR = os.path.dirname(os.path.abspath(__file__))
PILOT_DIR = os.path.dirname(AUDIT_DIR)
RESULTS_DIR = os.path.join(AUDIT_DIR, "results")
SEALED = "/work1/zixuan/data/agent_memory/sealed"
PUBLIC = "/work1/zixuan/data/agent_memory/public_view"
ROLLOUT_GLOB = "/work1/zixuan/outputs/agent_memory/pilot/rollouts_qwen*_shard*-of-*.jsonl"
CONFIG = os.path.join(PILOT_DIR, "configs", "pilot.yaml")

sys.path.insert(0, PILOT_DIR)  # read-only imports of pilot modules

AUDIT_SEED = 20260808
NBOOT = 2000
CI_LEVEL = 0.95

A_CELLS = ["A00", "A01", "A10", "A11"]
ALL_CELLS = ["A00", "A01", "A10", "A11", "N", "Q"]
CELL_P = {"A00": 0, "A01": 0, "A10": 1, "A11": 1}
CELL_S = {"A00": 0, "A01": 1, "A10": 0, "A11": 1}


def load_rollout_rows():
    from analyze import load_rollouts
    rows, files = load_rollouts([ROLLOUT_GLOB])
    return rows, files


def load_jsonl(path):
    with open(path) as f:
        return [json.loads(line) for line in f]


def load_memories():
    return load_jsonl(os.path.join(SEALED, "memories_sealed.jsonl"))


def load_families():
    rows = load_jsonl(os.path.join(SEALED, "families.jsonl"))
    return {r["family_idx"]: r for r in rows}


def load_cells():
    rows = load_jsonl(os.path.join(SEALED, "cells.jsonl"))
    return {(r["family_idx"], r["sibling_idx"]): r for r in rows}


def load_tasks_sealed():
    return load_jsonl(os.path.join(SEALED, "tasks_sealed.jsonl"))


def load_sim_rows():
    out = {}
    with open(os.path.join(SEALED, "sim_report.csv")) as f:
        for r in csv.DictReader(f):
            out[r["memory_id"]] = {
                "sim_tf": float(r["sim_tf"]),
                "sim_embed": float(r["sim_embed"]),
                "P": None if r["P"] in ("", "None") else int(r["P"]),
                "S": None if r["S"] in ("", "None") else int(r["S"]),
                "family_idx": int(r["family_idx"]),
                "cell": r["cell"],
                "target_sibling": int(r["target_sibling"]),
            }
    return out


def load_public_task(task_id):
    with open(os.path.join(PUBLIC, "tasks", task_id + ".json")) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# statistics
# ---------------------------------------------------------------------------

def rate(rows):
    return sum(r["success"] for r in rows) / len(rows) if rows else float("nan")


def family_cluster_bootstrap(units, stat_fn, reps=NBOOT, seed=AUDIT_SEED,
                             level=CI_LEVEL):
    """units: list of dicts each carrying 'family_idx'. stat_fn(units)->float.
    Families resampled with replacement; returns (point, lo, hi, boot_dist)."""
    rng = np.random.default_rng(seed)
    by_fam = defaultdict(list)
    for u in units:
        by_fam[u["family_idx"]].append(u)
    fams = sorted(by_fam)
    point = stat_fn(units)
    stats = []
    for _ in range(reps):
        idx = rng.integers(0, len(fams), len(fams))
        sub = []
        for i in idx:
            sub.extend(by_fam[fams[i]])
        try:
            v = stat_fn(sub)
        except Exception:
            continue
        if v == v and np.isfinite(v):
            stats.append(v)
    alpha = (1 - level) / 2
    lo = float(np.quantile(stats, alpha)) if stats else float("nan")
    hi = float(np.quantile(stats, 1 - alpha)) if stats else float("nan")
    return float(point), lo, hi, [float(s) for s in stats]


def cell_contrast_stat(cell_a, cell_b):
    def f(rows):
        a = [r for r in rows if r["cell"] == cell_a]
        b = [r for r in rows if r["cell"] == cell_b]
        if not a or not b:
            return float("nan")
        return rate(a) - rate(b)
    return f


def contrast_with_ci(rows, cell_a, cell_b, seed, reps=NBOOT):
    point, lo, hi, _ = family_cluster_bootstrap(
        rows, cell_contrast_stat(cell_a, cell_b), reps=reps, seed=seed)
    return {"contrast": "%s-%s" % (cell_a, cell_b),
            "point": point, "ci": [lo, hi], "sig": bool(lo > 0 or hi < 0)}


def tau_block(rows, seed, reps=NBOOT):
    """The four canonical contrasts on a rollout subset."""
    fams = sorted({r["family_idx"] for r in rows})

    def tau_struct(sub):
        return rate([r for r in sub if r["cell"] == "A10"]) - \
               rate([r for r in sub if r["cell"] == "A00"])

    def tau_trap(sub):
        return rate([r for r in sub if r["cell"] == "A01"]) - \
               rate([r for r in sub if r["cell"] == "A00"])

    def replay(sub):
        return rate([r for r in sub if r["cell"] == "A11"]) - \
               rate([r for r in sub if r["cell"] == "A10"])

    def tau_pxs(sub):
        r_ = {c: rate([x for x in sub if x["cell"] == c]) for c in A_CELLS}
        return (r_["A11"] - r_["A01"]) - (r_["A10"] - r_["A00"])

    out = {}
    for name, fn in [("tau_struct", tau_struct), ("tau_trap", tau_trap),
                     ("replay_premium", replay), ("tau_PxS", tau_pxs)]:
        p, lo, hi, _ = family_cluster_bootstrap(rows, fn, reps=reps, seed=seed)
        out[name] = {"point": p, "ci": [lo, hi], "sig": bool(lo > 0 or hi < 0)}
    out["n_families"] = len(fams)
    return out


def auc_scores(y_true, y_score):
    """Plain rank-based AUC (ties handled by average ranks)."""
    y = np.asarray(y_true, float)
    s = np.asarray(y_score, float)
    n_pos = y.sum()
    n_neg = len(y) - n_pos
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    order = np.argsort(s, kind="mergesort")
    ranks = np.empty(len(s), float)
    i = 0
    while i < len(s):
        j = i
        while j + 1 < len(s) and s[order[j + 1]] == s[order[i]]:
            j += 1
        ranks[order[i:j + 1]] = 0.5 * (i + j) + 1.0
        i = j + 1
    return float((ranks[y == 1].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def env_block(extra=None):
    """Environment / seed block recorded in every result file."""
    import platform
    blk = {
        "python": platform.python_version(),
        "audit_seed": AUDIT_SEED,
        "bootstrap": {"reps": NBOOT, "level": CI_LEVEL, "cluster": "family"},
        "cwd": os.getcwd(),
    }
    try:
        import numpy, sklearn  # noqa
        blk["numpy"] = numpy.__version__
        blk["sklearn"] = sklearn.__version__
    except Exception:
        pass
    try:
        import torch
        blk["torch"] = torch.__version__
        if torch.cuda.is_available():
            blk["gpu"] = torch.cuda.get_device_name(0)
    except Exception:
        pass
    try:
        import vllm
        blk["vllm"] = vllm.__version__
    except Exception:
        pass
    if extra:
        blk.update(extra)
    return blk


def write_result(name, payload):
    os.makedirs(RESULTS_DIR, exist_ok=True)
    path = os.path.join(RESULTS_DIR, name)
    with open(path, "w") as f:
        json.dump(payload, f, indent=1)
    print("[audit] wrote %s" % path)
    return path
