"""Thin second-model-family analysis for llama8b (NousResearch/Meta-Llama-3.1-8B-Instruct).

Reuses pilot/analyze.py statistics verbatim (family-cluster bootstrap, same
reps/seed from the config). Computes the pre-registered estimands for the
llama8b Stage-A grid and the cross-family comparisons against qwen7b / qwen3b
(recomputed from the raw rollout files through the SAME code path, so no
numbers are hand-copied):

  - 6 cell rates (A00/A01/A10/A11/N/Q) with family-cluster bootstrap 95% CIs
  - tau_struct  = A10 - A00
  - tau_trap    = A01 - A00
  - replay_premium = A11 - A10
  - HFR(A01) = paired P(N=1 & A01=0)
  - replay share of matched effect (gatec/transplants_2x2.py definition):
        eff_match   = 0.5*(A11 + A10) - A00
        replay_share = 0.5*(A11 - A00) / eff_match

Usage:
  python llama8b/analyze_llama8b.py --config configs/pilot_llama8b.yaml \
      --rollouts "/work1/zixuan/outputs/agent_memory/pilot/rollouts_llama8b_shard*-of-*.jsonl"
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import analyze as A
from generate_families import load_config

PILOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_ROOT = "/work1/zixuan/outputs/agent_memory/pilot"

REFERENCE_ROLLOUTS = {
    "qwen7b": os.path.join(OUT_ROOT, "rollouts_qwen7b_shard*-of-*.jsonl"),
    "qwen3b": os.path.join(OUT_ROOT, "rollouts_qwen3b_shard*-of-*.jsonl"),
}


def eff_match_stat(rows):
    r = {c: A.rate([x for x in rows if x["cell"] == c]) for c in A_CELLS4}
    return 0.5 * (r["A11"] + r["A10"]) - r["A00"]


def replay_share_stat(rows):
    r = {c: A.rate([x for x in rows if x["cell"] == c]) for c in A_CELLS4}
    denom = 0.5 * (r["A11"] + r["A10"]) - r["A00"]
    if abs(denom) < 1e-9:
        return float("nan")
    return 0.5 * (r["A11"] - r["A00"]) / denom


A_CELLS4 = ["A00", "A01", "A10", "A11"]


def estimands(rows, model):
    mrows = [r for r in rows if r["model"] == model]
    fams = sorted({r["family_idx"] for r in mrows})
    out = {"model": model, "n_rollouts": len(mrows),
           "parseable_action_rate": None, "cells": {}}
    ptot = sum((r["parse_ok"] or 0) + (r["parse_fail"] or 0) for r in mrows)
    pok = sum(r["parse_ok"] or 0 for r in mrows)
    out["parseable_action_rate"] = pok / ptot if ptot else None
    for c in A.ALL_CELLS:
        p, lo, hi = A.cluster_bootstrap_ci(mrows, A.cell_rate_stat(c), fams,
                                           A.NBOOT, A.BOOT_SEED + 1)
        out["cells"][c] = {"rate": p, "ci": [lo, hi],
                           "n": len([x for x in mrows if x["cell"] == c])}
    for name, fn in [("tau_struct_A10_minus_A00", A.rd_stat("A10", "A00")),
                     ("tau_trap_A01_minus_A00", A.rd_stat("A01", "A00")),
                     ("replay_premium_A11_minus_A10", A.rd_stat("A11", "A10"))]:
        p, lo, hi = A.cluster_bootstrap_ci(mrows, fn, fams, A.NBOOT,
                                           A.BOOT_SEED + 2)
        out[name] = {"est": p, "ci": [lo, hi]}
    p, lo, hi = A.cluster_bootstrap_ci(mrows, A.hf_stat, fams, A.NBOOT,
                                       A.BOOT_SEED + 4)
    _, npairs = A.harmful_flip_stat(mrows)
    out["HFR_A01"] = {"est": p, "ci": [lo, hi], "n_pairs": npairs}
    p, lo, hi = A.cluster_bootstrap_ci(mrows, eff_match_stat, fams, A.NBOOT,
                                       A.BOOT_SEED + 6)
    out["eff_match_pooled"] = {"est": p, "ci": [lo, hi]}
    p, lo, hi = A.cluster_bootstrap_ci(mrows, replay_share_stat, fams,
                                       A.NBOOT, A.BOOT_SEED + 7)
    out["replay_share_of_matched_effect"] = {"est": p, "ci": [lo, hi]}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(
        PILOT, "configs", "pilot_llama8b.yaml"))
    ap.add_argument("--rollouts", nargs="+", required=True)
    ap.add_argument("--out", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "LLAMA8B_RESULTS.json"))
    args = ap.parse_args()
    cfg = load_config(args.config)
    A.NBOOT = cfg["analysis"]["bootstrap_reps"]
    A.BOOT_SEED = cfg["analysis"]["bootstrap_seed"]

    rows, files = A.load_rollouts(args.rollouts)
    print("[llama8b] %d llama8b rollouts from %d files" % (len(rows), len(files)))
    if not rows:
        raise SystemExit("no llama8b rollouts found: %s" % (args.rollouts,))
    llama = estimands(rows, "llama8b")

    refs = {}
    for model, pat in REFERENCE_ROLLOUTS.items():
        rrows, rfiles = A.load_rollouts([pat])
        rrows = [r for r in rrows if r["model"] == model]
        if not rrows:
            print("[warn] no reference rollouts for %s" % model)
            continue
        refs[model] = estimands(rrows, model)
        print("[llama8b] reference %s: %d rollouts (tau_struct=%+.3f, "
              "replay_share=%.3f, HFR=%.3f)"
              % (model, refs[model]["n_rollouts"],
                 refs[model]["tau_struct_A10_minus_A00"]["est"],
                 refs[model]["replay_share_of_matched_effect"]["est"],
                 refs[model]["HFR_A01"]["est"]))

    cmp_ = {}
    if "qwen7b" in refs:
        q = refs["qwen7b"]
        cmp_["tau_struct_sign_vs_qwen7b"] = {
            "llama8b": llama["tau_struct_A10_minus_A00"],
            "qwen7b": q["tau_struct_A10_minus_A00"],
            "same_sign": (llama["tau_struct_A10_minus_A00"]["est"] > 0)
                         == (q["tau_struct_A10_minus_A00"]["est"] > 0)}
        cmp_["replay_share_vs_qwen7b"] = {
            "llama8b": llama["replay_share_of_matched_effect"],
            "qwen7b": q["replay_share_of_matched_effect"]}
        cmp_["HFR_vs_qwen7b"] = {"llama8b": llama["HFR_A01"],
                                 "qwen7b": q["HFR_A01"]}
    if "qwen3b" in refs:
        cmp_["HFR_vs_qwen3b"] = {"llama8b": llama["HFR_A01"],
                                 "qwen3b": refs["qwen3b"]["HFR_A01"]}

    results = {
        "model": "llama8b", "hf_repo": "NousResearch/Meta-Llama-3.1-8B-Instruct",
        "config": os.path.abspath(args.config),
        "rollout_files": files,
        "bootstrap": {"reps": A.NBOOT, "seed": A.BOOT_SEED,
                      "level": cfg["analysis"]["ci_level"],
                      "cluster": "family"},
        "llama8b": llama, "references": refs, "comparisons": cmp_,
    }
    with open(args.out, "w") as f:
        json.dump(results, f, indent=1)
    print("[llama8b] written -> %s" % args.out)

    l = llama
    print("\ncell rates: %s" % {c: round(l["cells"][c]["rate"], 3)
                                for c in A.ALL_CELLS})
    print("tau_struct=%+.3f%stau_trap=%+.3f replay_premium=%+.3f HFR=%.3f "
          "replay_share=%.2f parseable=%.3f"
          % (l["tau_struct_A10_minus_A00"]["est"], " ", 
             l["tau_trap_A01_minus_A00"]["est"],
             l["replay_premium_A11_minus_A10"]["est"], l["HFR_A01"]["est"],
             l["replay_share_of_matched_effect"]["est"],
             l["parseable_action_rate"] or float("nan")))


if __name__ == "__main__":
    main()
