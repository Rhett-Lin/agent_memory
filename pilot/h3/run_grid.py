"""H3 stage C: experiment grid (parent's final ruling, supersedes sec.16's
ambiguous count).

Per model:
  32 fam x 4 sib x 2 cells {A10,A11} x 5 arms {script_complete, script_prefix,
  transcript_complete, transcript_prefix, eco} x 3 seeds = 3840 A-cell rollouts
  + N reference (32x4x3 = 384, memory=None)
  + Q reference (32x4x3 = 384, h3 sealed sham memory text, reused verbatim
    from public_view/memories exactly as the pilot does)
  = 4608 rollouts.  Two models (qwen7b then qwen3b): 9216 total.

Memory text per (fam,sib,cell,arm): public_view/cards/<arm>/<memory_id>.json
with memory_id = cells.jsonl[(fam,sib)][cell].  Target task: sealed sibling
row (fam,sib,seed) -- same (sib,seed) DB-state pairing as the pilot.

Multi-GPU: one process per GPU, shard by family index (i % n_shards).
Resume: units (family_idx,sibling_idx,cell,seed,arm) already present in ANY
rollouts_<model>_shard*.jsonl or the rollouts_h3_<model>_ndiff.jsonl
pre-collected N cells are skipped (failed rollouts stay logged as-is and are
NOT re-run on resume -- they count as done, matching pilot convention).
Retries: a failed chunk retries up to harness.retry_max times.

DEVIATION (documented in IMPLEMENTATION_NOTES.md): 8 shards, not 10 --
GPUs 0 and 5 are occupied by another user's job; shards run on GPUs
1,2,3,4,6,7,8,9.

Launch (from pilot/):
  for g in 1 2 3 4 6 7 8 9; do
    CUDA_VISIBLE_DEVICES=$g python h3/run_grid.py --model qwen7b \
      --shard $((g<5?g:g-1))/8 &
  done
"""

import argparse
import glob
import hashlib
import json
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_PILOT = os.path.dirname(_HERE)
sys.path.insert(0, _PILOT)

from generate_families import load_config, git_commit  # noqa: E402
from harness import load_model, run_rollouts, build_episode, load_memory  # noqa: E402

DEFAULT_CONFIG = os.path.join(_HERE, "configs", "h3.yaml")
ARMS = ["script_complete", "script_prefix",
        "transcript_complete", "transcript_prefix", "eco"]
A_CELLS = ["A10", "A11"]
FORM = {"script_complete": "script", "script_prefix": "script",
        "transcript_complete": "transcript", "transcript_prefix": "transcript",
        "eco": "transcript"}
COV = {"script_complete": "complete", "script_prefix": "prefix",
       "transcript_complete": "complete", "transcript_prefix": "prefix",
       "eco": "prefix"}


def load_sealed(sealed_dir):
    tasks, cells = {}, {}
    with open(os.path.join(sealed_dir, "tasks_sealed.jsonl")) as f:
        for line in f:
            r = json.loads(line)
            if r["kind"] == "sibling":
                tasks[(r["family_idx"], r["sibling_idx"], r["seed"])] = r
    with open(os.path.join(sealed_dir, "cells.jsonl")) as f:
        for line in f:
            r = json.loads(line)
            cells[(r["family_idx"], r["sibling_idx"])] = r
    fam_ids = sorted({k[0] for k in cells})
    return tasks, cells, fam_ids


def config_hash(path):
    with open(path, "rb") as f:
        return hashlib.sha1(f.read()).hexdigest()[:12]


def build_units(fam_ids, seeds):
    units = []
    for fi in fam_ids:
        for sib in range(4):
            for seed in seeds:
                for cell in A_CELLS:
                    for arm in ARMS:
                        units.append({"family_idx": fi, "sibling_idx": sib,
                                      "seed": seed, "cell": cell, "arm": arm})
                units.append({"family_idx": fi, "sibling_idx": sib,
                              "seed": seed, "cell": "N", "arm": "N"})
                units.append({"family_idx": fi, "sibling_idx": sib,
                              "seed": seed, "cell": "Q", "arm": "Q"})
    return units


def existing_units(patterns):
    done = set()
    for pat in patterns:
        for fn in glob.glob(pat):
            with open(fn) as f:
                for line in f:
                    try:
                        m = json.loads(line)["meta"]
                        done.add((m["family_idx"], m["sibling_idx"],
                                  m["cell"], m["seed"], m.get("arm")))
                    except Exception:
                        continue
    return done


def materialize(cfg, model_key, units, tasks, cells_map):
    pub = cfg["paths"]["public_view"]
    chash = config_hash(cfg["_config_path"])
    commit = git_commit()
    try:
        import vllm, torch
        env_versions = {"vllm": vllm.__version__, "torch": torch.__version__,
                        "gpu": torch.cuda.get_device_name(0)}
    except Exception:
        env_versions = {"vllm": "unknown"}
    episodes = []
    for u in units:
        key = (u["family_idx"], u["sibling_idx"], u["seed"])
        trow = tasks[key]
        crow = cells_map[(u["family_idx"], u["sibling_idx"])]
        if u["cell"] == "N":
            mem_id, mem_text, form, cov = None, None, None, None
        elif u["cell"] == "Q":
            mem_id = crow["Q"]
            mem_text = load_memory(pub, mem_id)
            form, cov = None, None
        else:
            mem_id = crow[u["cell"]]
            with open(os.path.join(pub, "cards", u["arm"],
                                   mem_id + ".json")) as f:
                mem_text = json.load(f)["text"]
            form, cov = FORM[u["arm"]], COV[u["arm"]]
        ep = build_episode(pub, trow, mem_text, u["cell"], u["seed"],
                           {"memory_id": mem_id, "model": model_key,
                            "arm": u["arm"], "form": form, "coverage": cov,
                            "system": "h3", "config_hash": chash,
                            "git_commit": commit, "env_versions": env_versions})
        episodes.append((u, ep))
    return episodes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--model", default="qwen7b")
    ap.add_argument("--shard", default="0/8")
    ap.add_argument("--batch-size", type=int, default=64)
    ap.add_argument("--limit", type=int, default=None, help="smoke: first N units")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    cfg = load_config(args.config)
    cfg["_config_path"] = args.config
    out_root = cfg["paths"]["output_root"]
    log_root = cfg["paths"]["log_root"]
    os.makedirs(out_root, exist_ok=True)
    os.makedirs(log_root, exist_ok=True)

    shard_idx, n_shards = (int(x) for x in args.shard.split("/"))
    tasks, cells_map, fam_ids = load_sealed(cfg["paths"]["sealed"])
    fam_ids = [f for i, f in enumerate(fam_ids) if i % n_shards == shard_idx]
    units = build_units(fam_ids, cfg["grid"]["seeds"])
    out_path = os.path.join(out_root, "rollouts_%s_shard%03d-of-%03d.jsonl"
                            % (args.model, shard_idx, n_shards))
    done = existing_units([
        os.path.join(out_root, "rollouts_%s_shard*-of-*.jsonl" % args.model),
        os.path.join(out_root, "rollouts_h3_%s_ndiff.jsonl" % args.model)])
    units = [u for u in units if (u["family_idx"], u["sibling_idx"], u["cell"],
                                  u["seed"], u["arm"]) not in done]
    if args.limit:
        units = units[:args.limit]
    from collections import Counter
    print("[h3] model=%s shard=%d/%d families=%s units_to_run=%d skipped_done=%d"
          % (args.model, shard_idx, n_shards, fam_ids, len(units), len(done)))
    print("[h3] unit mix: %s" % dict(Counter(
        (u["cell"] if u["cell"] in ("N", "Q") else u["arm"]) for u in units)))
    if args.dry_run:
        return

    episodes = materialize(cfg, args.model, units, tasks, cells_map)
    print("[h3] loading model %s ..." % cfg["models"][args.model], flush=True)
    llm = load_model(cfg["models"][args.model], cfg)
    err_log = os.path.join(log_root, "errors_h3_%s_shard%03d.log"
                           % (args.model, shard_idx))
    retry_max = cfg["harness"]["retry_max"]
    n_written, n_succ = 0, 0
    t0 = time.time()
    with open(out_path, "a") as out:
        for i0 in range(0, len(episodes), args.batch_size):
            chunk = episodes[i0:i0 + args.batch_size]
            attempt, results = 0, None
            while attempt <= retry_max:
                try:
                    results = run_rollouts(llm, [ep for _, ep in chunk], cfg)
                    break
                except Exception as e:
                    attempt += 1
                    with open(err_log, "a") as ef:
                        ef.write("%s chunk @%d attempt %d: %r\n"
                                 % (time.strftime("%F %T"), i0, attempt, e))
                    if attempt > retry_max:
                        raise
                    print("[h3] chunk failed (attempt %d), retrying ..."
                          % attempt, flush=True)
                    time.sleep(5)
            for r in results:
                out.write(json.dumps(r) + "\n")
            out.flush()
            n_written += len(results)
            n_succ += sum(1 for r in results if r["success"])
            print("[h3] %d/%d rollouts written (cum success %.3f, elapsed "
                  "%.0fs)" % (n_written, len(episodes),
                              n_succ / max(1, n_written), time.time() - t0),
                  flush=True)
    print("[h3] done: %d rollouts -> %s" % (n_written, out_path))


if __name__ == "__main__":
    main()
