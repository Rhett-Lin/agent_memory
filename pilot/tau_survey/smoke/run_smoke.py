"""Part VI-0 smoke gate runner (≤24 episodes).

Plan (frozen):
  - 6 N-arm episodes: X anchors tasks 12/18/49 × seeds {0,1}
  - 6 R-arm episodes (with `[Recalled prior case]` block): same tasks × seeds {0,1}
  - up to 12 N-retry episodes (seeds 2..5) ONLY if N reach-rate < 60% on first 6
Gate: PASS iff >= 60% of N-arm episodes reach the trap decision point.

Resume-safe: (task_index, arm, seed) already present in episodes.jsonl are skipped.
Writes:
  OUT_DIR/episodes.jsonl          one record per episode (full step log)
  OUT_DIR/prompt_pilot_{N,R}.txt  system prompts of the first N/R episodes (framing pilot)
  OUT_DIR/metrics.json            gate metrics
"""
from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict

from common import OUT_DIR  # noqa: F401
from harness import (
    VLLMEngine, build_system_prompt, run_episode, MEMORY_BLOCK_R,
)
import anchors_cpu  # noqa: F401

X_TASKS = [12, 18, 49]
EPISODES_LOG = OUT_DIR / "episodes.jsonl"
METRICS = OUT_DIR / "metrics.json"
REACH_GATE = 0.60


def planned_episodes() -> list[tuple[int, str, int]]:
    eps = []
    for t in X_TASKS:
        for seed in (0, 1):
            eps.append((t, "N", seed))
            eps.append((t, "R", seed))
    return eps


def retry_episodes() -> list[tuple[int, str, int]]:
    return [(t, "N", seed) for t in X_TASKS for seed in (2, 3, 4, 5)]


def load_done() -> set[tuple[int, str, int]]:
    done = set()
    if EPISODES_LOG.exists():
        for line in EPISODES_LOG.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                done.add((r["task_index"], r["arm"], r["seed"]))
    return done


def dump_prompt_pilots() -> None:
    """Text-only framing pilot: dump the exact N and R system prompts and diff them."""
    from tau_bench.envs.airline.env import MockAirlineDomainEnv
    env = MockAirlineDomainEnv(user_strategy="human", task_index=12)
    for arm in ("N", "R"):
        p = build_system_prompt(env.wiki, env.tools_info, arm)
        (OUT_DIR / f"prompt_pilot_{arm}.txt").write_text(p)
    import difflib
    n = (OUT_DIR / "prompt_pilot_N.txt").read_text().splitlines()
    r = (OUT_DIR / "prompt_pilot_R.txt").read_text().splitlines()
    diff = "\n".join(difflib.unified_diff(n, r, "prompt_N", "prompt_R", lineterm=""))
    (OUT_DIR / "prompt_pilot_diff.txt").write_text(diff)
    print(f"[pilot] prompt diff lines: {len(diff.splitlines())}, memory block chars: {len(MEMORY_BLOCK_R)}")


def summarize(records: list[dict]) -> dict:
    n_recs = [r for r in records if r["arm"] == "N"]
    r_recs = [r for r in records if r["arm"] == "R"]
    def rate(rs, key):
        return round(sum(1 for r in rs if r[key]) / len(rs), 3) if rs else None
    taxonomy: dict[str, int] = {}
    for r in n_recs:
        if r["failure_category"]:
            taxonomy[r["failure_category"]] = taxonomy.get(r["failure_category"], 0) + 1
    reach = rate(n_recs, "reached_decision_point")
    return {
        "n_episodes_total": len(records),
        "N": {
            "episodes": len(n_recs),
            "reach_rate": reach,
            "reward1": rate(n_recs, "db_matches_gt"),
            "cancel_move_rate": rate(n_recs, "cancel_move"),
            "denial_move_rate": rate(n_recs, "denial_move"),
            "grounded_rate": rate(n_recs, "grounded"),
            "failure_taxonomy": taxonomy,
            "user_repeat_stall": rate(n_recs, "user_repeat_stall"),
            "user_char_break": rate(n_recs, "user_char_break"),
            "mean_steps": round(sum(r["steps"] for r in n_recs) / len(n_recs), 1) if n_recs else None,
            "mean_wall_s": round(sum(r["wall_time_s"] for r in n_recs) / len(n_recs), 1) if n_recs else None,
            "mean_gen_tokens": round(sum(r["gen_tokens"] for r in n_recs) / len(n_recs), 1) if n_recs else None,
            "parse_fail_turns": sum(r["parse_fail_turns"] for r in n_recs),
            "tool_calls": sum(r["tool_calls"] for r in n_recs),
            "tool_error_turns": sum(r["tool_error_turns"] for r in n_recs),
        },
        "R": {
            "episodes": len(r_recs),
            "reach_rate": rate(r_recs, "reached_decision_point"),
            "reward1": rate(r_recs, "db_matches_gt"),
            "cancel_move_rate": rate(r_recs, "cancel_move"),
            "mean_steps": round(sum(r["steps"] for r in r_recs) / len(r_recs), 1) if r_recs else None,
            "mean_wall_s": round(sum(r["wall_time_s"] for r in r_recs) / len(r_recs), 1) if r_recs else None,
        },
        "gate": "PASS" if (reach is not None and reach >= REACH_GATE) else "FAIL",
        "gate_rule": f">= {REACH_GATE:.0%} of N-arm episodes reach the trap decision point",
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    from pathlib import Path
    denial_cues = json.loads(
        (Path(__file__).parent / "anchors.json").read_text()
    )["decision_point_detector"]["denial_cues"]

    dump_prompt_pilots()

    t0 = time.time()
    engine = VLLMEngine()
    done = load_done()
    records: list[dict] = []
    if EPISODES_LOG.exists():
        records = [json.loads(l) for l in EPISODES_LOG.read_text().splitlines() if l.strip()]

    def run_plan(plan):
        for t, arm, seed in plan:
            if (t, arm, seed) in done:
                print(f"[skip] task{t} arm{arm} seed{seed}")
                continue
            anchor_rid = {12: "3FRNFB", 18: "SI5UKW", 49: "MDCLVA"}[t]
            r = run_episode(engine, t, arm, seed, anchor_rid, denial_cues)
            rec = asdict(r)
            records.append(rec)
            done.add((t, arm, seed))
            with EPISODES_LOG.open("a") as f:
                f.write(json.dumps(rec) + "\n")
            print(f"[done] task{t} arm{arm} seed{seed}: reached={r.reached_decision_point} "
                  f"reward={r.reward} steps={r.steps} t={r.wall_time_s}s fail={r.failure_category}")
            m = summarize(records)
            METRICS.write_text(json.dumps(m, indent=2))

    run_plan(planned_episodes())
    m = summarize(records)
    if m["N"]["reach_rate"] is not None and m["N"]["reach_rate"] < REACH_GATE:
        print(f"[gate] N reach-rate {m['N']['reach_rate']} < {REACH_GATE} -> running up to 12 N-retry episodes")
        run_plan(retry_episodes())
    m = summarize(records)
    m["gpu_hours"] = round((time.time() - t0) / 3600, 3)
    m["engine_gen_tokens_total"] = engine.gen_tokens
    m["engine_prompt_tokens_total"] = engine.prompt_tokens
    METRICS.write_text(json.dumps(m, indent=2))
    print(json.dumps(m, indent=2))


if __name__ == "__main__":
    main()
