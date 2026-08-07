"""Experiment-grid orchestrator for the CausalMemBench mini-pilot (SPEC 6).

Grid: families x 4 target siblings x 6 cells x 4 seeds x 2 models
     (= 40 x 4 x 6 x 4 x 2 = 15360 rollouts at full size; every dimension is
     a single config/CLI knob so the whole grid can be reproduced exactly).

Multi-GPU: one process per GPU, shard by family index:
  CUDA_VISIBLE_DEVICES=0 python run_pilot.py --model qwen3b --shard 0/5 ...

Resume: rollout units already present in the output JSONL are skipped.
Retries: a failed chunk is retried up to harness.retry_max times and errors
are appended to logs/<log_root>/errors_<model>_<shard>.log.

Dry run (no GPU, prints the grid):  python run_pilot.py --dry-run
"""

import argparse
import glob
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from generate_families import load_config, git_commit
from harness import load_model, run_rollouts, build_episode, load_memory

import hashlib


def load_sealed(sealed_dir):
    tasks, cells, fams = [], {}, {}
    with open(os.path.join(sealed_dir, "tasks_sealed.jsonl")) as f:
        for line in f:
            r = json.loads(line)
            if r["kind"] == "sibling":
                tasks.append(r)
    with open(os.path.join(sealed_dir, "cells.jsonl")) as f:
        for line in f:
            r = json.loads(line)
            cells[(r["family_idx"], r["sibling_idx"])] = r
    with open(os.path.join(sealed_dir, "families.jsonl")) as f:
        for line in f:
            r = json.loads(line)
            fams[r["family_idx"]] = r
    return tasks, cells, fams


def config_hash(path):
    with open(path, "rb") as f:
        return hashlib.sha1(f.read()).hexdigest()[:12]


def build_grid(cfg, model_key, family_ids, cells_filter=None, seeds=None,
               n_siblings=None):
    grid = cfg["grid"]
    cells = cells_filter or grid["cells"]
    seeds = seeds if seeds is not None else grid["seeds"]
    n_sib = n_siblings or grid["n_target_siblings"]
    units = []
    for fi in family_ids:
        for sib in range(n_sib):
            for cell in cells:
                for seed in seeds:
                    units.append({"family_idx": fi, "sibling_idx": sib,
                                  "cell": cell, "seed": seed})
    return units


def materialize_episodes(cfg, model_key, units, tasks_by_key, cells_map):
    pub = cfg["paths"]["public_view"]
    chash = config_hash_cached(cfg["_config_path"])
    commit = git_commit()
    env_versions = None
    try:
        import vllm, torch
        env_versions = {"vllm": vllm.__version__, "torch": torch.__version__,
                        "gpu": torch.cuda.get_device_name(0)}
    except Exception:
        env_versions = {"vllm": "unknown"}
    episodes = []
    for u in units:
        trow = tasks_by_key[(u["family_idx"], u["sibling_idx"], u["seed"])]
        mem_id = cells_map[(u["family_idx"], u["sibling_idx"])][u["cell"]]
        mem_text = load_memory(pub, mem_id) if mem_id else None
        ep = build_episode(pub, trow, mem_text, u["cell"], u["seed"],
                           {"memory_id": mem_id, "model": model_key,
                            "config_hash": chash, "git_commit": commit,
                            "env_versions": env_versions})
        episodes.append((u, ep))
    return episodes


_CH = {}


def config_hash_cached(path):
    if path not in _CH:
        _CH[path] = config_hash(path)
    return _CH[path]


def existing_units(out_files):
    done = set()
    for pat in out_files:
        for fn in glob.glob(pat):
            with open(fn) as f:
                for line in f:
                    try:
                        r = json.loads(line)
                        m = r["meta"]
                        done.add((m["family_idx"], m["sibling_idx"],
                                  m["cell"], m["seed"]))
                    except Exception:
                        continue
    return done


def main():
    ap = argparse.ArgumentParser()
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--config", default=os.path.join(here, "configs", "pilot.yaml"))
    ap.add_argument("--model", default="qwen3b")
    ap.add_argument("--shard", default="0/1", help="shard index / num shards")
    ap.add_argument("--families", default=None,
                    help="override family list, e.g. '0-9' or '0,3,7'")
    ap.add_argument("--cells", default=None, help="comma list override")
    ap.add_argument("--seeds", default=None, help="comma list override, e.g. '0,1'")
    ap.add_argument("--siblings", type=int, default=None)
    ap.add_argument("--batch-size", type=int, default=64)
    ap.add_argument("--out", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    cfg = load_config(args.config)
    cfg["_config_path"] = args.config
    sealed = cfg["paths"]["sealed"]
    out_root = cfg["paths"]["output_root"]
    log_root = cfg["paths"]["log_root"]
    os.makedirs(out_root, exist_ok=True)
    os.makedirs(log_root, exist_ok=True)

    shard_idx, n_shards = (int(x) for x in args.shard.split("/"))
    tasks, cells_map, fams = load_sealed(sealed)
    all_fam = sorted(fams)
    if args.families:
        fam_ids = []
        for part in args.families.split(","):
            if "-" in part:
                a, b = part.split("-")
                fam_ids.extend(range(int(a), int(b) + 1))
            else:
                fam_ids.append(int(part))
    else:
        fam_ids = [f for i, f in enumerate(all_fam) if i % n_shards == shard_idx]

    cells_filter = args.cells.split(",") if args.cells else None
    seeds = [int(x) for x in args.seeds.split(",")] if args.seeds else None
    units = build_grid(cfg, args.model, fam_ids, cells_filter, seeds,
                       args.siblings)
    out_path = args.out or os.path.join(
        out_root, "rollouts_%s_shard%03d-of-%03d.jsonl"
                  % (args.model, shard_idx, n_shards))

    done = existing_units([out_path])
    units = [u for u in units if (u["family_idx"], u["sibling_idx"],
                                  u["cell"], u["seed"]) not in done]

    print("[pilot] model=%s shard=%d/%d families=%d units_to_run=%d (skipped %d done)"
          % (args.model, shard_idx, n_shards, len(fam_ids), len(units), len(done)))
    if args.dry_run:
        per_cell = {}
        for u in units:
            per_cell[u["cell"]] = per_cell.get(u["cell"], 0) + 1
        print("[pilot] DRY RUN grid: families=%s cells=%s seeds=%s "
              "total=%d -> %s" % (fam_ids[:20], per_cell,
                                  seeds if seeds else cfg["grid"]["seeds"],
                                  len(units), out_path))
        return

    tasks_by_key = {(r["family_idx"], r["sibling_idx"], r["seed"]): r
                    for r in tasks}
    episodes = materialize_episodes(cfg, args.model, units, tasks_by_key,
                                    cells_map)
    print("[pilot] loading model %s ..." % cfg["models"][args.model])
    llm = load_model(cfg["models"][args.model], cfg)
    err_log = os.path.join(log_root, "errors_%s_shard%03d.log"
                           % (args.model, shard_idx))
    retry_max = cfg["harness"]["retry_max"]
    n_written = 0
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
                    print("[pilot] chunk failed (attempt %d), retrying ..."
                          % attempt, flush=True)
                    time.sleep(5)
            for r in results:
                out.write(json.dumps(r) + "\n")
            out.flush()
            n_written += len(results)
            n_succ = sum(1 for r in results if r["success"])
            print("[pilot] %d/%d rollouts written (chunk success %d/%d, "
                  "elapsed %.0fs)" % (n_written, len(episodes), n_succ,
                                      len(results), time.time() - t0),
                  flush=True)
    print("[pilot] done: %d rollouts -> %s" % (n_written, out_path))


if __name__ == "__main__":
    main()
