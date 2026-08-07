"""H-C minimal gate (GATE_PROTOCOL.md Part II section 9): run the frozen grid
for one representation system.

Grid (identical to the pilot): 40 families x 4 target siblings x 6 cells
(A00/A01/A10/A11/N/Q) x 4 seeds x qwen7b = 3840 rollouts per system.  Only the
[MEMORY] content changes between systems; task texts, tool schema, harness,
parsing, terminal predicates, budgets, config-hash/commit recording, Latin
square and DB initial states are pilot-identical:

  cell N        -> no memory injected (exactly like the pilot)
  cell Q        -> pilot SHAM card re-used verbatim from public_view/memories
                   (identical text in all three systems, by design)
  cells A00-A11 -> system card:
       procedural -> public_view/memories/<mid>.json              (pilot asset)
       raw        -> public_view/systems/raw/<mid>.json           (build_raw_cards.py)
       summary    -> public_view/systems/summary/<mid>.json       (build_summary_cards.py)

The `procedural` system's rollouts are the EXISTING pilot files
(rollouts_qwen7b_shard*-of-*.jsonl, 3840 rows) and are NOT re-run
(pre-registered reuse).

Before materializing the grid, the injected card directories pass the
FORBIDDEN_RE_CS isolation scan (cell labels) from generate_families; any hit
aborts the run.

Launch (one process per GPU, same pattern as the pilot; example 2x5 shards):
  for i in 0 1 2 3 4; do
    CUDA_VISIBLE_DEVICES=$i python systems/run_hc_grid.py --system raw \
      --model qwen7b --shard $i/5 > /work1/zixuan/logs/agent_memory/hc_raw_shard$i.log 2>&1 &
  done
  for i in 5 6 7 8 9; do
    j=$((i-5))
    CUDA_VISIBLE_DEVICES=$i python systems/run_hc_grid.py --system summary \
      --model qwen7b --shard $j/5 > /work1/zixuan/logs/agent_memory/hc_summary_shard$j.log 2>&1 &
  done
Completed units in the output JSONL are skipped on re-run (resume-safe).
"""

import argparse
import json
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_PILOT = os.path.dirname(_HERE)
sys.path.insert(0, _PILOT)

from generate_families import load_config, git_commit, FORBIDDEN_RE_CS  # noqa: E402
from harness import load_model, run_rollouts, build_episode, load_memory  # noqa: E402
from run_pilot import (load_sealed, build_grid, existing_units,  # noqa: E402
                       config_hash_cached)

DEFAULT_CONFIG = os.path.join(_PILOT, "configs", "pilot_7b.yaml")
MEM_CELLS = ["A00", "A01", "A10", "A11", "Q"]
SYSTEMS = ["procedural", "raw", "summary"]


def system_memory_text(cfg, system, cell, mem_id):
    if mem_id is None or cell == "N":
        return None
    pub = cfg["paths"]["public_view"]
    if cell == "Q" or system == "procedural":
        return load_memory(pub, mem_id)
    with open(os.path.join(pub, "systems", system, mem_id + ".json")) as f:
        return json.load(f)["text"]


def isolation_check_cards(cfg, system):
    """FORBIDDEN_RE_CS scan over the A-cell cards this system will inject
    (Q/N are pilot-identical and were scanned at generation time)."""
    if system == "procedural":
        return []
    d = os.path.join(cfg["paths"]["public_view"], "systems", system)
    hits = []
    if not os.path.isdir(d):
        print("[hc] WARNING: card dir %s missing (ok only for --dry-run)" % d)
        return hits
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".json"):
            continue
        with open(os.path.join(d, fn), errors="replace") as f:
            txt = f.read()
        for m in FORBIDDEN_RE_CS.finditer(txt):
            hits.append((fn, txt[:m.start()].count("\n") + 1, m.group(0)))
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--system", required=True, choices=SYSTEMS)
    ap.add_argument("--model", default="qwen7b")
    ap.add_argument("--shard", default="0/1", help="shard index / num shards")
    ap.add_argument("--families", default=None)
    ap.add_argument("--cells", default=None)
    ap.add_argument("--seeds", default=None)
    ap.add_argument("--siblings", type=int, default=None)
    ap.add_argument("--batch-size", type=int, default=64)
    ap.add_argument("--out", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    cfg = load_config(args.config)
    cfg["_config_path"] = args.config
    os.environ.setdefault("HF_HOME", cfg["paths"]["hf_home"])
    sealed = cfg["paths"]["sealed"]
    out_root = cfg["paths"]["output_root"]
    log_root = cfg["paths"]["log_root"]
    os.makedirs(out_root, exist_ok=True)
    os.makedirs(log_root, exist_ok=True)

    if args.system != "procedural":
        hits = isolation_check_cards(cfg, args.system)
        if hits:
            for h in hits[:20]:
                print("[hc] ISOLATION VIOLATION: %s:%d %r" % h)
            raise SystemExit("[hc] %d FORBIDDEN_RE_CS hits in %s cards; abort"
                             % (len(hits), args.system))
        print("[hc] isolation scan clean on system=%s cards" % args.system)

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
        out_root, "rollouts_hc_%s_%s_shard%03d-of-%03d.jsonl"
                  % (args.system, args.model, shard_idx, n_shards))

    done = existing_units([out_path])
    units = [u for u in units if (u["family_idx"], u["sibling_idx"],
                                  u["cell"], u["seed"]) not in done]
    print("[hc] system=%s model=%s shard=%d/%d families=%d units_to_run=%d "
          "(skipped %d done) -> %s"
          % (args.system, args.model, shard_idx, n_shards, len(fam_ids),
             len(units), len(done), out_path))
    if args.dry_run:
        per_cell = {}
        for u in units:
            per_cell[u["cell"]] = per_cell.get(u["cell"], 0) + 1
        print("[hc] DRY RUN grid: cells=%s seeds=%s total=%d"
              % (per_cell, seeds if seeds else cfg["grid"]["seeds"], len(units)))
        return

    tasks_by_key = {(r["family_idx"], r["sibling_idx"], r["seed"]): r
                    for r in tasks}
    chash = config_hash_cached(cfg["_config_path"])
    commit = git_commit()
    env_versions = {"vllm": "unknown"}
    try:
        import vllm, torch
        env_versions = {"vllm": vllm.__version__, "torch": torch.__version__,
                        "gpu": torch.cuda.get_device_name(0)}
    except Exception:
        pass
    pub = cfg["paths"]["public_view"]
    episodes = []
    for u in units:
        trow = tasks_by_key[(u["family_idx"], u["sibling_idx"], u["seed"])]
        mem_id = cells_map[(u["family_idx"], u["sibling_idx"])][u["cell"]]
        mem_text = system_memory_text(cfg, args.system, u["cell"], mem_id)
        ep = build_episode(pub, trow, mem_text, u["cell"], u["seed"],
                           {"memory_id": mem_id, "model": args.model,
                            "system": args.system, "config_hash": chash,
                            "git_commit": commit, "env_versions": env_versions})
        episodes.append(ep)
    print("[hc] loading model %s ..." % cfg["models"][args.model])
    llm = load_model(cfg["models"][args.model], cfg)
    err_log = os.path.join(log_root, "errors_hc_%s_%s_shard%03d.log"
                           % (args.system, args.model, shard_idx))
    retry_max = cfg["harness"]["retry_max"]
    n_written = 0
    t0 = time.time()
    with open(out_path, "a") as out:
        for i0 in range(0, len(episodes), args.batch_size):
            chunk = episodes[i0:i0 + args.batch_size]
            attempt, results = 0, None
            while attempt <= retry_max:
                try:
                    results = run_rollouts(llm, chunk, cfg)
                    break
                except Exception as e:
                    attempt += 1
                    with open(err_log, "a") as ef:
                        ef.write("%s chunk @%d attempt %d: %r\n"
                                 % (time.strftime("%F %T"), i0, attempt, e))
                    if attempt > retry_max:
                        raise
                    print("[hc] chunk failed (attempt %d), retrying ..."
                          % attempt, flush=True)
                    time.sleep(5)
            for r in results:
                out.write(json.dumps(r) + "\n")
            out.flush()
            n_written += len(results)
            n_succ = sum(1 for r in results if r["success"])
            print("[hc] %d/%d rollouts written (chunk success %d/%d, "
                  "elapsed %.0fs)" % (n_written, len(episodes), n_succ,
                                      len(results), time.time() - t0),
                  flush=True)
    print("[hc] done: %d rollouts -> %s" % (n_written, out_path))


if __name__ == "__main__":
    main()
