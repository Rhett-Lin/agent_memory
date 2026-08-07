"""H-C minimal gate (GATE_PROTOCOL.md Part II): build `summary` representation cards.

For each raw card in pilot/systems/raw_cards_map.jsonl, take the FULL
UNTRUNCATED trajectory harvested for that card (from
outputs/agent_memory/pilot/hc_raw_source*.jsonl, the exact attempt recorded in
the raw map) and summarize it with Qwen2.5-7B-Instruct at temperature 0 into a
<= 300-token procedure summary.

ANTI-LEAKAGE (pre-registered, GATE_PROTOCOL section 12): the summary prompt
contains ONLY the source-task instruction and the episode transcript.  Sealed
labels (family / cell / P / S / near-miss) never enter the prompt.  The frozen
prompt is the SUMMARY_PROMPT constant below -- it is stored verbatim in
summary_cards_map.jsonl rows and in this file.

Output cards: /work1/zixuan/data/agent_memory/public_view/systems/summary/<memory_id>.json
(same memory_id as the raw/procedural cards they parallel).
Sealed map: pilot/systems/summary_cards_map.jsonl (token counts, prompt hash).
Summaries are hard-truncated to <= 300 Qwen2.5-1.5B tokens (same TokenMeter code
path as the pilot); shorter ones are kept as generated (never padded).

Run (from pilot/, after build_raw_cards + --merge-shards finished):
  CUDA_VISIBLE_DEVICES=0 python systems/build_summary_cards.py --config configs/pilot_7b.yaml
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

from generate_families import load_config, git_commit, TokenMeter  # noqa: E402
from harness import load_model  # noqa: E402
from run_pilot import config_hash_cached  # noqa: E402
from build_raw_cards import transcript_text, card_dir, isolation_scan_cards  # noqa: E402

DEFAULT_CONFIG = os.path.join(_PILOT, "configs", "pilot_7b.yaml")

# FROZEN PROMPT (do not edit after launch; any change requires a new map +
# re-run of the summary grid).  Prompt sees ONLY instruction + transcript.
SUMMARY_PROMPT = """You are condensing one successful episode of a data-operations agent into a reusable memory for future episodes.

The agent worked in a relational (SQLite) environment with tools list_tables, read, aggregate, insert, update, delete, finish.

Task the agent was given:
\"\"\"{instruction}\"\"\"

Episode transcript (tool calls and tool results, in order):
\"\"\"{transcript}\"\"\"

Write a procedure summary of at most 300 tokens that another agent could follow when solving a similar task: the goal, the ordered steps that made the episode succeed (which tables and filters were read, the rule that was applied, and the exact writes that were made), and any pitfall to avoid. Output only the summary text, no preamble."""

SUMMARY_MAX_TOKENS = 300


def summary_card_dir(cfg):
    return os.path.join(cfg["paths"]["public_view"], "systems", "summary")


def find_harvest_rows(cfg):
    """memory_id -> list of harvest attempt rows (all shards)."""
    rows = {}
    pat = os.path.join(cfg["paths"]["output_root"], "hc_raw_source*.jsonl")
    for fn in sorted(glob.glob(pat)):
        with open(fn) as f:
            for line in f:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                mid = r.get("meta", {}).get("memory_id")
                if mid:
                    rows.setdefault(mid, []).append(r)
    return rows


def chosen_row(map_row, attempts):
    """The exact trajectory the raw card was built from: the LAST successful
    model attempt at the recorded decode seed (harvest files are append-only
    and chronological; a re-run after a crash appends later rows, and cards
    are always built from the latest run).  None when oracle_fallback."""
    if map_row["oracle_fallback"]:
        return None
    found = None
    for r in attempts:
        m = r["meta"]
        if m.get("seed") == map_row["decode_seed"] and r.get("success"):
            found = r
    if found is None:
        raise RuntimeError("no matching successful harvest row for %s (seed %r)"
                           % (map_row["memory_id"], map_row["decode_seed"]))
    return found


def fallback_trajectory(map_row, cfg):
    """Re-derive the oracle trajectory the raw fallback card was built from
    (deterministic: same plan, same env as the generator validation)."""
    from build_raw_cards import load_sealed, source_task_row, oracle_trajectory
    from harness import load_task
    sealed = cfg["paths"]["sealed"]
    mems, tasks, fams = load_sealed(sealed)
    mem = None
    with open(os.path.join(sealed, "memories_sealed.jsonl")) as f:
        for line in f:
            r = json.loads(line)
            if r["memory_id"] == map_row["memory_id"]:
                mem = r
                break
    if mem is None:
        raise RuntimeError("memory %s not in memories_sealed"
                           % map_row["memory_id"])
    trow, _ = source_task_row(mem, tasks)
    tables = load_task(cfg["paths"]["public_view"], trow["task_id"])["tables"]
    return oracle_trajectory(trow, fams[trow["family_idx"]], tables)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--limit", type=int, default=None, help="smoke: first N cards")
    ap.add_argument("--batch-size", type=int, default=64)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    cfg = load_config(args.config)
    cfg["_config_path"] = args.config
    os.environ.setdefault("HF_HOME", cfg["paths"]["hf_home"])

    map_path = os.path.join(_HERE, "raw_cards_map.jsonl")
    if not os.path.exists(map_path):
        raise SystemExit("[summary] %s missing; run build_raw_cards.py first "
                         "(and --merge-shards if sharded)" % map_path)
    with open(map_path) as f:
        maps = [json.loads(l) for l in f]
    if args.limit:
        maps = maps[:args.limit]
    out_dir = summary_card_dir(cfg)
    done = set()
    if os.path.isdir(out_dir):
        done = {fn[:-5] for fn in os.listdir(out_dir) if fn.endswith(".json")}
    maps = [m for m in maps if m["memory_id"] not in done]
    print("[summary] cards_to_build=%d (skipped %d done)" % (len(maps), len(done)))
    if not maps:
        print("[summary] nothing to do")
        return

    harvest = find_harvest_rows(cfg)
    pub = cfg["paths"]["public_view"]
    prompts, kept = [], []
    for m in maps:
        r = chosen_row(m, harvest.get(m["memory_id"], []))
        if r is None:
            # oracle fallback raw card: no model rollout stored; re-derive the
            # deterministic substituted trajectory the card was built from
            traj = fallback_trajectory(m, cfg)
        else:
            traj = r["trajectory"]
        with open(os.path.join(pub, "tasks", m["source_task_id"] + ".json")) as f:
            instr = json.load(f)["instruction"]
        prompts.append(SUMMARY_PROMPT.format(
            instruction=instr, transcript=transcript_text(traj)))
        kept.append(m)
    if args.dry_run:
        print("[summary] DRY RUN example prompt (first card, truncated view):\n")
        print(prompts[0][:1500])
        return

    chash = config_hash_cached(cfg["_config_path"])
    commit = git_commit()
    meter = TokenMeter(cfg["memories"]["tokenizer"])
    prompt_hash = hashlib.sha1(SUMMARY_PROMPT.encode()).hexdigest()[:12]

    print("[summary] loading model qwen7b (%s), temperature=0 ..."
          % cfg["models"]["qwen7b"])
    llm = load_model(cfg["models"]["qwen7b"], cfg)
    from vllm import SamplingParams
    sp = SamplingParams(temperature=0.0, top_p=1.0,
                        max_tokens=cfg["harness"]["max_tokens_per_step"],
                        seed=0)
    t0 = time.time()
    os.makedirs(out_dir, exist_ok=True)
    map_out = os.path.join(_HERE, "summary_cards_map.jsonl")
    n_trunc = 0
    with open(map_out, "a") as mout:
        for i0 in range(0, len(prompts), args.batch_size):
            chunk_p = prompts[i0:i0 + args.batch_size]
            chunk_m = kept[i0:i0 + args.batch_size]
            msgs = [[{"role": "user", "content": p}] for p in chunk_p]
            outs = llm.chat(msgs, sampling_params=[sp] * len(msgs),
                            add_generation_prompt=True, use_tqdm=False)
            for m, out in zip(chunk_m, outs):
                text = out.outputs[0].text.strip()
                n_gen = meter.count(text)
                if n_gen > SUMMARY_MAX_TOKENS:
                    text = meter.tok.decode(
                        meter.tok.encode(text)[:SUMMARY_MAX_TOKENS])
                    n_tok = SUMMARY_MAX_TOKENS
                    n_trunc += 1
                    trunc = True
                else:
                    n_tok = n_gen
                    trunc = False
                with open(os.path.join(out_dir, m["memory_id"] + ".json"),
                          "w") as f:
                    json.dump({"memory_id": m["memory_id"], "text": text},
                              f, indent=1, sort_keys=True)
                mout.write(json.dumps({
                    "memory_id": m["memory_id"], "cell": m["cell"],
                    "card_family_idx": m["card_family_idx"],
                    "card_sibling_idx": m["card_sibling_idx"],
                    "source_task_id": m["source_task_id"],
                    "raw_oracle_fallback": m["oracle_fallback"],
                    "n_tokens_generated": n_gen, "n_tokens_card": n_tok,
                    "truncated": trunc, "model": "qwen7b",
                    "temperature": 0.0, "prompt_sha1": prompt_hash,
                    "config_hash": chash, "git_commit": commit},
                    sort_keys=True) + "\n")
            mout.flush()
            print("[summary] %d/%d summarized (elapsed %.0fs)"
                  % (min(i0 + args.batch_size, len(prompts)), len(prompts),
                     time.time() - t0), flush=True)
    print("[summary] DONE: %d cards (%d truncated at %d tokens) -> %s"
          % (len(kept), n_trunc, SUMMARY_MAX_TOKENS, out_dir))
    hits = [h for h in isolation_scan_cards(cfg)]  # raw dir sanity (already clean)
    s_hits = []
    for fn in sorted(os.listdir(out_dir)):
        if not fn.endswith(".json"):
            continue
        with open(os.path.join(out_dir, fn), errors="replace") as f:
            txt = f.read()
        from generate_families import FORBIDDEN_RE_CI, FORBIDDEN_RE_CS
        for name, rx in (("CS", FORBIDDEN_RE_CS), ("CI", FORBIDDEN_RE_CI)):
            for mm in rx.finditer(txt):
                s_hits.append((fn, name, mm.group(0)))
    print("[summary] isolation scan: raw_dir=%d hits, summary_dir=%d hits"
          % (len(hits), len(s_hits)))
    for h in s_hits[:20]:
        print("  ISOLATION HIT: %s %s %r" % h)
    if any(h[1] == "CS" for h in s_hits):
        raise SystemExit("[summary] FORBIDDEN_RE_CS violations in summary cards")


if __name__ == "__main__":
    main()
