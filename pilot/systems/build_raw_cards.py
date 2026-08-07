"""H-C minimal gate (GATE_PROTOCOL.md Part II): build `raw` representation cards.

For EVERY non-Q memory in sealed/memories_sealed.jsonl (640 A-cell rows; the
160 Q rows are sham cards and are skipped -- the pilot sham text is reused at
injection time) this script reconstructs the SOURCE task whose correct
execution produces the procedure the parallel procedural card describes, runs
qwen7b on it NO-memory via the existing pilot harness (12 steps budget), keeps
only SUCCESS trajectories, and writes a transcript-style card.

Source-task mapping (recovered from sealed data, no invented semantics):
  A11 ("sibling_same_family") -> tasks_sealed row (sibling, m.family_idx, sib 0, seed 0)
  A10 ("cross_domain_pair")   -> (sibling, m.source_family == a10_partner, sib 0, seed 0)
  A01 ("near_miss")           -> (near_miss, m.family_idx, sib 0, seed 0)
  A00 ("unrelated")           -> (sibling, m.source_family == a00_partner, sib 0, seed 0)
The generator built every card from the seed-0 instance roles
(generate_families.py lines 1796-1814: roles from ("sibling"/"near_miss", 0, 0)),
so the seed-0 sealed task row is exactly the task the card describes.

Retry policy (pre-registered): one decode seed per memory (= target_sibling
index, so the 4 cards sharing one source task get distinct rollouts); on
failure retry <= 2 with decode seeds 100+s and 200+s; if still failing,
substitute the oracle plan trajectory from program_dsl.run_oracle_plan and mark
oracle_fallback=true.  ALL attempts (failed included) are appended to the
harvest JSONL -- no rollout is dropped.  Oracle fallback trajectory skips
"__check__" pseudo-steps only; their observations are already explicit
READ/AGGREGATE tool steps in the oracle plan (program_dsl.py dependency
structure), so the transcript stays verbatim tool calls + tool results.

Card text: "step k: <assistant completion verbatim>" + "<tool_result>...</"
lines, hard-truncated to <= 300 Qwen2.5-1.5B tokens (same TokenMeter code path
as the pilot).  Cards shorter than the 200-token window floor are kept and
flagged below_window=true (never padded, never fabricated).

Outputs:
  /work1/zixuan/data/agent_memory/public_view/systems/raw/<memory_id>.json
      {"memory_id", "text"} -- same memory_id as the procedural card it parallels
  pilot/systems/raw_cards_map.jsonl  (sealed map; per-shard suffixed, merged by
      --merge-shards N) recording source task id, fallback flag, token counts
  /work1/zixuan/outputs/agent_memory/pilot/hc_raw_source[_shardXXX-of-YYY].jsonl
      every harvest attempt (successes and failures)

Run (from pilot/):
  CUDA_VISIBLE_DEVICES=0 python systems/build_raw_cards.py --config configs/pilot_7b.yaml
  # parallel: one process per GPU with --shard i/5, then
  python systems/build_raw_cards.py --config configs/pilot_7b.yaml --merge-shards 5
"""

import argparse
import json
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_PILOT = os.path.dirname(_HERE)
sys.path.insert(0, _PILOT)

from generate_families import (load_config, git_commit, TokenMeter,  # noqa: E402
                               FORBIDDEN_RE_CI, FORBIDDEN_RE_CS)
from harness import load_model, run_rollouts, build_episode, load_task  # noqa: E402
from run_pilot import config_hash_cached  # noqa: E402
from program_dsl import ARCHETYPES, run_oracle_plan  # noqa: E402
from env_relationalops import RelationalOpsEnv  # noqa: E402

DEFAULT_CONFIG = os.path.join(_PILOT, "configs", "pilot_7b.yaml")
A_CELLS = ["A00", "A01", "A10", "A11"]
ATTEMPT_SEED_OFFSETS = [0, 100, 200]       # decode seed = target_sibling + offset


# ---------------------------------------------------------------------------
# sealed loading + source-task reconstruction
# ---------------------------------------------------------------------------

def load_sealed(sealed_dir):
    mems, tasks, fams = [], {}, {}
    with open(os.path.join(sealed_dir, "memories_sealed.jsonl")) as f:
        for line in f:
            mems.append(json.loads(line))
    with open(os.path.join(sealed_dir, "tasks_sealed.jsonl")) as f:
        for line in f:
            r = json.loads(line)
            tasks[(r["kind"], r["family_idx"], r["sibling_idx"], r["seed"])] = r
    with open(os.path.join(sealed_dir, "families.jsonl")) as f:
        for line in f:
            r = json.loads(line)
            fams[r["family_idx"]] = r
    return mems, tasks, fams


def source_task_row(mem, tasks):
    """Reconstruct the exact source task instance for a memory card.
    Returns (sealed_task_row, source_key_str). Raises on ambiguity: the mapping
    must be total over A-cell memories (verified 640/640 before GPU launch)."""
    fidx, cell = mem["family_idx"], mem["cell"]
    if cell == "A11" and mem["source_kind"] == "sibling_same_family" \
            and mem["source_family"] == fidx:
        key = ("sibling", fidx, 0, 0)
    elif cell == "A10" and mem["source_kind"] == "cross_domain_pair":
        key = ("sibling", mem["source_family"], 0, 0)
    elif cell == "A01" and mem["source_kind"] == "near_miss" \
            and mem["source_family"] == fidx:
        key = ("near_miss", fidx, 0, 0)
    elif cell == "A00" and mem["source_kind"] == "unrelated":
        key = ("sibling", mem["source_family"], 0, 0)
    else:
        raise RuntimeError("unexpected memory row semantics: %s" % json.dumps(mem))
    if key not in tasks:
        raise RuntimeError("source task %r for memory %s not in tasks_sealed"
                           % (key, mem["memory_id"]))
    return tasks[key], "%s/fam%d/sib%d/seed%d" % key


def build_jobs(cfg, shard_idx, n_shards, limit=None):
    mems, tasks, fams = load_sealed(cfg["paths"]["sealed"])
    jobs = []
    for m in mems:
        if m["cell"] == "Q":
            continue                                  # sham: skipped per protocol
        if m["family_idx"] % n_shards != shard_idx:
            continue
        trow, src_key = source_task_row(m, tasks)
        jobs.append({"memory_id": m["memory_id"], "cell": m["cell"],
                     "card_family_idx": m["family_idx"],
                     "card_sibling_idx": m["target_sibling"],
                     "source_kind": m["source_kind"],
                     "source_family": m["source_family"],
                     "source_key": src_key, "task_row": trow,
                     "base_seed": m["target_sibling"]})
    jobs.sort(key=lambda j: (j["card_family_idx"], j["card_sibling_idx"],
                             j["cell"]))
    if limit:
        jobs = jobs[:limit]
    return jobs, fams


# ---------------------------------------------------------------------------
# transcript formatting + card truncation
# ---------------------------------------------------------------------------

def transcript_text(traj):
    lines = []
    for s in traj:
        lines.append("step %d: %s" % (s["step"], s["completion"]))
        lines.append("<tool_result>%s</tool_result>"
                     % json.dumps(s["tool_result"], ensure_ascii=False))
    return "\n".join(lines)


def truncate_card(text, meter, max_tok):
    ids = meter.tok.encode(text)
    if len(ids) <= max_tok:
        return text, len(ids), False
    return meter.tok.decode(ids[:max_tok]), max_tok, True


def oracle_trajectory(task_row, fam_row, tables):
    """Substitute trajectory: execute the oracle plan from program_dsl (same
    plan, same env as the generator's 800/800 validation). CHECK pseudo-steps
    are validated but not rendered (their observations are prior READ/AGG
    steps). Appends a finish step. Returns harness-shaped trajectory.
    `tables` comes from the public task file (sealed rows carry only a digest).
    """
    env = RelationalOpsEnv(tables, task_row["terminal"])
    prog = ARCHETYPES[fam_row["archetype"]](task_row["program_params"])
    ok, detail = run_oracle_plan(env, prog, task_row["oracle_plan"])
    if not ok:
        raise RuntimeError("oracle plan failed for task %s: %s"
                           % (task_row["task_id"], detail))
    traj, i = [], 0
    for entry in detail:
        if "tool" not in entry:            # CHECK pseudo-step: validated, not rendered
            continue
        i += 1
        act = {"tool": entry["tool"], "args": entry["args"]}
        traj.append({"step": i, "completion": json.dumps(act), "parsed": act,
                     "parse_error": None, "tool_result": entry["result"]})
    i += 1
    fin = {"tool": "finish", "args": {"answer": "final state reached and verified"}}
    traj.append({"step": i, "completion": json.dumps(fin), "parsed": fin,
                 "parse_error": None,
                 "tool_result": {"ok": True, "message": "episode finished"}})
    return traj


# ---------------------------------------------------------------------------
# card + map writers
# ---------------------------------------------------------------------------

def card_dir(cfg):
    return os.path.join(cfg["paths"]["public_view"], "systems", "raw")


def write_card(cfg, memory_id, text):
    path = os.path.join(card_dir(cfg), memory_id + ".json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump({"memory_id": memory_id, "text": text}, f, indent=1,
                  sort_keys=True)


def suffix(shard_idx, n_shards):
    return "" if (shard_idx, n_shards) == (0, 1) else \
        "_shard%03d-of-%03d" % (shard_idx, n_shards)


# ---------------------------------------------------------------------------
# isolation scan over the new card files (SPEC isolation, FORBIDDEN_RE_CS)
# ---------------------------------------------------------------------------

def isolation_scan_cards(cfg):
    hits = []
    d = card_dir(cfg)
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".json"):
            continue
        p = os.path.join(d, fn)
        with open(p, errors="replace") as f:
            txt = f.read()
        for name, rx in (("CS", FORBIDDEN_RE_CS), ("CI", FORBIDDEN_RE_CI)):
            for m in rx.finditer(txt):
                line_no = txt[:m.start()].count("\n") + 1
                hits.append({"file": p, "line": line_no, "regex": name,
                             "match": m.group(0)})
    return hits


# ---------------------------------------------------------------------------
# merge mode: fuse per-shard maps into the final sealed map + report
# ---------------------------------------------------------------------------

def merge_shards(cfg, n_shards):
    here_maps = []
    for i in range(n_shards):
        p = os.path.join(_HERE, "raw_cards_map_shard%03d-of-%03d.jsonl"
                         % (i, n_shards))
        if not os.path.exists(p):
            raise SystemExit("[merge] missing shard map %s" % p)
        with open(p) as f:
            here_maps.extend(json.loads(l) for l in f)
    here_maps.sort(key=lambda r: (r["card_family_idx"], r["card_sibling_idx"],
                                  r["cell"]))
    out = os.path.join(_HERE, "raw_cards_map.jsonl")
    with open(out, "w") as f:
        for r in here_maps:
            f.write(json.dumps(r, sort_keys=True) + "\n")
    n = len(here_maps)
    fb = sum(1 for r in here_maps if r["oracle_fallback"])
    below = sum(1 for r in here_maps if r["below_window"])
    trunc = sum(1 for r in here_maps if r["truncated"])
    ncards = len([fn for fn in os.listdir(card_dir(cfg)) if fn.endswith(".json")])
    hits = isolation_scan_cards(cfg)
    cs = [h for h in hits if h["regex"] == "CS"]
    print("[merge] map rows=%d cards_on_disk=%d" % (n, ncards))
    print("[merge] harvest success=%d/%d (oracle_fallback=%d, %.1f%%)"
          % (n - fb, n, fb, 100.0 * fb / max(1, n)))
    print("[merge] token window: truncated=%d below_200=%d" % (trunc, below))
    print("[merge] isolation scan (raw cards): %d CS hits, %d CI hits"
          % (len(cs), len(hits) - len(cs)))
    for h in hits[:20]:
        print("  ISOLATION HIT: %s:%d %s %r" % (h["file"], h["line"],
                                                h["regex"], h["match"]))
    if cs:
        raise SystemExit("[merge] FORBIDDEN_RE_CS violations in raw cards; "
                         "do NOT launch the grid")
    toks = [r["n_tokens_card"] for r in here_maps]
    print("[merge] card tokens: min=%d mean=%.1f max=%d"
          % (min(toks), sum(toks) / len(toks), max(toks)))
    print("[merge] wrote %s" % out)


# ---------------------------------------------------------------------------
# main harvest
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--shard", default="0/1", help="shard index / num shards")
    ap.add_argument("--limit", type=int, default=None, help="smoke: first N jobs")
    ap.add_argument("--batch-size", type=int, default=64)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--merge-shards", type=int, default=None, metavar="N",
                    help="merge per-shard maps into raw_cards_map.jsonl (no GPU)")
    args = ap.parse_args()
    cfg = load_config(args.config)
    cfg["_config_path"] = args.config
    os.environ.setdefault("HF_HOME", cfg["paths"]["hf_home"])

    if args.merge_shards:
        merge_shards(cfg, args.merge_shards)
        return

    shard_idx, n_shards = (int(x) for x in args.shard.split("/"))
    sfx = suffix(shard_idx, n_shards)
    map_path = os.path.join(_HERE, "raw_cards_map%s.jsonl" % sfx)
    harvest_path = os.path.join(cfg["paths"]["output_root"],
                                "hc_raw_source%s.jsonl" % sfx)
    os.makedirs(cfg["paths"]["output_root"], exist_ok=True)

    jobs, fams = build_jobs(cfg, shard_idx, n_shards, args.limit)
    done = set()
    if os.path.exists(map_path):
        with open(map_path) as f:
            for line in f:
                done.add(json.loads(line)["memory_id"])
    jobs = [j for j in jobs if j["memory_id"] not in done]
    print("[raw] shard=%d/%d jobs_to_run=%d (skipped %d done)"
          % (shard_idx, n_shards, len(jobs), len(done)))
    if args.dry_run:
        from collections import Counter
        print("[raw] DRY RUN cells=%s source_kinds=%s"
              % (Counter(j["cell"] for j in jobs),
                 Counter(j["source_kind"] for j in jobs)))
        for j in jobs[:5]:
            print("  %s cell=%s src=%s task=%s"
                  % (j["memory_id"], j["cell"], j["source_key"],
                     j["task_row"]["task_id"]))
        return

    chash = config_hash_cached(cfg["_config_path"])
    commit = git_commit()
    env_versions = {"vllm": "unknown"}
    try:
        import vllm, torch
        env_versions = {"vllm": vllm.__version__, "torch": torch.__version__,
                        "gpu": torch.cuda.get_device_name(0)}
    except Exception:
        pass
    meter = TokenMeter(cfg["memories"]["tokenizer"])
    mem_min, mem_max = (cfg["memories"]["tokens_min"],
                        cfg["memories"]["tokens_max"])

    pub = cfg["paths"]["public_view"]
    pending = {j["memory_id"]: j for j in jobs}
    map_rows = []

    print("[raw] loading model qwen7b (%s) ..." % cfg["models"]["qwen7b"])
    llm = load_model(cfg["models"]["qwen7b"], cfg)
    t0 = time.time()
    with open(harvest_path, "a") as harvest:
        for attempt, off in enumerate(ATTEMPT_SEED_OFFSETS):
            if not pending:
                break
            episodes = []
            for j in pending.values():
                seed = j["base_seed"] + off
                ep = build_episode(
                    pub, j["task_row"], None, "SRC", seed,
                    {"memory_id": j["memory_id"], "model": "qwen7b",
                     "system": "raw", "card_cell": j["cell"],
                     "card_family_idx": j["card_family_idx"],
                     "card_sibling_idx": j["card_sibling_idx"],
                     "source_key": j["source_key"], "attempt": attempt,
                     "config_hash": chash, "git_commit": commit,
                     "env_versions": env_versions})
                episodes.append((j, ep))
            print("[raw] attempt %d: %d source rollouts (no memory) ..."
                  % (attempt, len(episodes)), flush=True)
            results = run_rollouts(llm, [ep for _, ep in episodes], cfg,
                                   batch_size=args.batch_size)
            for (j, _), r in zip(episodes, results):
                harvest.write(json.dumps(r) + "\n")
                if r["success"]:
                    j["traj"] = r["trajectory"]
                    j["n_attempts"] = attempt + 1
                    j["decode_seed"] = r["meta"]["seed"]
                    j["oracle_fallback"] = False
                    pending.pop(j["memory_id"], None)
            harvest.flush()
            print("[raw] attempt %d done: %d pending, elapsed %.0fs"
                  % (attempt, len(pending), time.time() - t0), flush=True)

    # oracle fallback for still-failing source tasks (marked, counted)
    for mid, j in pending.items():
        fam_row = fams[j["task_row"]["family_idx"]]
        tables = load_task(pub, j["task_row"]["task_id"])["tables"]
        j["traj"] = oracle_trajectory(j["task_row"], fam_row, tables)
        j["n_attempts"] = len(ATTEMPT_SEED_OFFSETS)
        j["decode_seed"] = None
        j["oracle_fallback"] = True
    if pending:
        print("[raw] ORACLE FALLBACK used on %d source tasks: %s"
              % (len(pending), sorted(pending)[:20]), flush=True)

    n_fb = 0
    with open(map_path, "a") as mout:
        for j in jobs:
            text = transcript_text(j["traj"])
            n_full = meter.count(text)
            card, n_card, truncated = truncate_card(text, meter, mem_max)
            write_card(cfg, j["memory_id"], card)
            n_fb += 1 if j["oracle_fallback"] else 0
            mout.write(json.dumps({
                "memory_id": j["memory_id"], "cell": j["cell"],
                "card_family_idx": j["card_family_idx"],
                "card_sibling_idx": j["card_sibling_idx"],
                "source_kind": j["source_kind"],
                "source_family": j["source_family"],
                "source_task_id": j["task_row"]["task_id"],
                "source_key": j["source_key"],
                "oracle_fallback": j["oracle_fallback"],
                "decode_seed": j["decode_seed"],
                "n_attempts": j["n_attempts"],
                "n_tokens_full": n_full, "n_tokens_card": n_card,
                "truncated": truncated,
                "below_window": n_card < mem_min,
                "config_hash": chash, "git_commit": commit,
                "env_versions": env_versions}, sort_keys=True) + "\n")
    n = len(jobs)
    print("[raw] DONE shard=%d/%d: %d cards written (%d model trajectories, "
          "%d oracle_fallback = %.1f%% of 640 total target) -> %s"
          % (shard_idx, n_shards, n, n - n_fb, n_fb,
             100.0 * n_fb / 640.0, card_dir(cfg)))
    print("[raw] map -> %s ; harvest -> %s" % (map_path, harvest_path))


if __name__ == "__main__":
    main()
