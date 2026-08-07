"""End-to-end smoke test (SPEC.md section 8 acceptance criteria).

Grid: 2 families x 2 target siblings x 6 cells x 1 seed x Qwen2.5-1.5B
(24 rollouts). Mirrors the SPEC grid (2 families x 6 cells x 1 seed); the
second sibling per family is included so the SPEC 8.4 difficulty criterion
(1.5B no-memory success rate in 20-80%) has binomial resolution 0/25/.../100%
on 4 N-condition tasks instead of an uninformative 0/50/100% on 2.

Checks (all must pass):
  1. oracle validation report in sealed manifest: 100% legal terminal states;
  2. oracle isolation: no family/cell/program labels anywhere in public_view
     (in-process scan + literal `grep -r "family_id\\|cell_id"`);
  3. 24 valid rollout records (schema fields present);
  4. 1.5B N-condition success rate within [0.20, 0.80];
  5. all four core figures and analysis tables produced by analyze.py.

Usage:
  CUDA_VISIBLE_DEVICES=0 HF_HOME=/work1/zixuan/cache/huggingface \
    python tests/smoke.py [--config configs/pilot.yaml]
"""

import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from generate_families import load_config, isolation_scan
from harness import run_rollouts, load_model
from run_pilot import (load_sealed, build_grid, materialize_episodes,
                       existing_units)

SMOKE_FAMILIES = [0, 1]
SMOKE_SIBLINGS = [0, 1]
SMOKE_SEED = 0
SMOKE_MODEL = "qwen1.5b"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(
        os.path.dirname(HERE), "configs", "pilot.yaml"))
    ap.add_argument("--keep-going", action="store_true",
                    help="run every stage and report all failures at the end "
                         "instead of stopping at the first failure")
    args = ap.parse_args()
    cfg = load_config(args.config)
    cfg["_config_path"] = args.config
    sealed_dir = cfg["paths"]["sealed"]
    out_dir = os.path.join(cfg["paths"]["output_root"], "smoke")
    os.makedirs(out_dir, exist_ok=True)
    failures = []

    def check(name, ok, detail=""):
        print("[smoke] %-46s %s %s" % (name, "PASS" if ok else "FAIL", detail),
              flush=True)
        if not ok:
            failures.append(name)
            if not args.keep_going:
                print("[smoke] aborting at first failure "
                      "(use --keep-going to run all stages)")
                sys.exit(1)

    # ---- 1. oracle validation report -------------------------------------
    with open(os.path.join(sealed_dir, "manifest.json")) as f:
        manifest = json.load(f)
    orep = manifest["oracle_report"]
    check("oracle validation 100%% legal terminal",
          orep["ok"] == orep["checked"],
          "%d/%d" % (orep["ok"], orep["checked"]))

    # ---- 2. isolation checks ----------------------------------------------
    hits = isolation_scan(cfg["paths"]["public_view"])
    check("oracle isolation scan (in-process)", len(hits) == 0,
          "%d hits" % len(hits))
    g = subprocess.run(["grep", "-r", "family_id\\|cell_id",
                        cfg["paths"]["public_view"]],
                       capture_output=True, text=True)
    check("grep -r family_id|cell_id public_view (no hits)", g.stdout == "",
          "%d lines" % len(g.stdout.splitlines()))

    # ---- 3. rollouts -------------------------------------------------------
    out_path = os.path.join(out_dir, "rollouts_smoke.jsonl")
    tasks, cells_map, fams = load_sealed(sealed_dir)
    tasks_by_key = {(r["family_idx"], r["sibling_idx"], r["seed"]): r
                    for r in tasks}
    units = build_grid(cfg, SMOKE_MODEL, SMOKE_FAMILIES,
                       cells_filter=None, seeds=[SMOKE_SEED],
                       n_siblings=len(SMOKE_SIBLINGS))
    done = existing_units([out_path])
    units = [u for u in units if (u["family_idx"], u["sibling_idx"],
                                  u["cell"], u["seed"]) not in done]
    print("[smoke] %d rollout units to run (%d already present)"
          % (len(units), len(done)), flush=True)
    if units:
        episodes = materialize_episodes(cfg, SMOKE_MODEL, units,
                                        tasks_by_key, cells_map)
        llm = load_model(cfg["models"][SMOKE_MODEL], cfg)
        t0 = time.time()
        with open(out_path, "a") as out:
            for r in run_rollouts(llm, [ep for _, ep in episodes], cfg):
                out.write(json.dumps(r) + "\n")
        print("[smoke] rollouts done in %.0fs -> %s"
              % (time.time() - t0, out_path), flush=True)

    rows = []
    with open(out_path) as f:
        for line in f:
            rows.append(json.loads(line))
    n_expected = len(SMOKE_FAMILIES) * len(SMOKE_SIBLINGS) * 6 * 1
    required = {"meta", "success", "finished", "terminal_ok", "terminal_detail",
                "steps", "parse_ok", "parse_fail", "tool_errors",
                "prompt_tokens", "completion_tokens", "trajectory", "ts"}
    valid = (len(rows) == n_expected
             and all(required <= set(r) for r in rows)
             and all(isinstance(r["success"], bool) for r in rows)
             and all(len(r["trajectory"]) == r["steps"] for r in rows))
    check("valid JSONL: %d records with required schema" % n_expected, valid,
          "got %d" % len(rows))

    # ---- 4. N-condition difficulty (SPEC 8.4) ------------------------------
    n_rows = [r for r in rows if r["meta"]["cell"] == "N"]
    n_rate = sum(r["success"] for r in n_rows) / max(1, len(n_rows))
    check("N-condition success rate in [0.20, 0.80]",
          0.20 <= n_rate <= 0.80,
          "%d/%d = %.3f" % (sum(r["success"] for r in n_rows), len(n_rows), n_rate))

    # per-cell recap
    print("[smoke] per-cell success (%s):" % SMOKE_MODEL)
    for c in ["A00", "A01", "A10", "A11", "N", "Q"]:
        rs = [r for r in rows if r["meta"]["cell"] == c]
        if rs:
            print("  %s: %d/%d" % (c, sum(r["success"] for r in rs), len(rs)),
                  flush=True)

    # ---- 5. analysis --------------------------------------------------------
    ana_dir = os.path.join(out_dir, "analysis")
    subprocess.run([sys.executable, os.path.join(os.path.dirname(HERE), "analyze.py"),
                    "--config", args.config, "--rollouts", out_path,
                    "--out", ana_dir], check=True)
    figs = ["fig1_cells_success.png", "fig2_uplift.png",
            "fig3_sim_uplift.png", "fig4_harmful_flip.png"]
    ok_figs = all(os.path.exists(os.path.join(ana_dir, f)) and
                  os.path.getsize(os.path.join(ana_dir, f)) > 1000 for f in figs)
    tables = ["token_len_balance.csv", "difficulty_tost.json",
              "compliance_summary.csv", "summary.json"]
    ok_tabs = all(os.path.exists(os.path.join(ana_dir, t)) for t in tables)
    check("four core figures produced", ok_figs)
    check("analysis tables produced", ok_tabs)

    tok_path = os.path.join(ana_dir, "token_len_balance.csv")
    print("[smoke] token-length balance table:")
    with open(tok_path) as f:
        print("  " + f.read().replace("\n", "\n  ").strip())

    if failures:
        print("[smoke] FAILED: %s" % ", ".join(failures))
        sys.exit(1)
    print("[smoke] ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
