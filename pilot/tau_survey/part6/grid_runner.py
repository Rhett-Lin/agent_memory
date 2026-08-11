"""Part VI grid runner (adjudication round-2 B2/B4): REAL executable.

`--dry-run` emits the frozen schedule; `--run` executes it against an
injected engine (vLLM production / scripted fixture), cell by cell, with
resumable skip-on-existing-rows semantics and per-cell compact snapshots.
The judge stage renders frozen judge inputs (digit-stripped), decodes T=0
seed 0, and stores RAW judge output — verdicts are derived ONLY through
judge_parser (never trusted as pre-parsed labels) by the analyzer.

Frozen (v3 §5 + round-2 B4):
  - main grid: 240 instances x {N,R,X} x ONE paired decode seed = 720 cells;
  - headroom: 40 instances x {N,X} ONLY = 80 cells (B4: the R headroom card
    never existed — deleted, recorded in the decisions registry);
  - seeds: agent seed for turn t = frozen_seed(<ns>, canonical_id, t);
    ns = "agent-main" (main, SAME value for the N/R/X arms of one instance)
    and "hr" (headroom); user seed = frozen_seed("user", canonical_id +
    "|" + arm, t);
  - waves: instances batched in sha256("tau6|"+canonical_id) ascending order,
    BATCH_SIZE frozen; batch id recorded in wave records;
  - per-cell compact snapshots BEFORE the first step and AFTER the loop
    (rollout_engine.compact_snapshot; the analyzer's strict trap
    certification requires them);
  - judge decode: T=0, seed 0, max_tokens 128, single call (judge_package).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

PART6 = Path(__file__).resolve().parent
sys.path.insert(0, str(PART6))

from analyze_tau import frozen_seed  # noqa: E402
import build_judge  # noqa: E402
import judge_parser  # noqa: E402
from rollout_engine import build_synthetic_env, run_episode  # noqa: E402

BATCH_SIZE = 24
MAIN_ARMS = ("N", "R", "X")
HR_ARMS = ("N", "X")        # B4: R headroom card deleted


def instance_wave_sort(canonical_id: str) -> str:
    return hashlib.sha256(("tau6|" + canonical_id).encode()).hexdigest()


def build_schedule(manifest_dir: Path) -> dict:
    sched = {}
    for zone, ns, arms in (("main", "agent-main", MAIN_ARMS),
                           ("hr", "hr", HR_ARMS)):
        entries = json.loads((manifest_dir / f"manifest_{zone}.json").read_text())["entries"]
        entries = sorted(entries, key=lambda e: instance_wave_sort(e["canonical_id"]))
        waves = []
        for wi in range(0, len(entries), BATCH_SIZE):
            batch = entries[wi:wi + BATCH_SIZE]
            cells = []
            for e in batch:
                for arm in arms:
                    cells.append({
                        "canonical_id": e["canonical_id"],
                        "arm": arm,
                        "agent_seed_turn0": frozen_seed(ns, e["canonical_id"], 0),
                        "user_seed_turn0": frozen_seed("user", f"{e['canonical_id']}|{arm}", 0),
                        "pairing_note": "agent seed identical across arms of one instance",
                    })
            waves.append({"wave_index": wi // BATCH_SIZE,
                          "batch_id": hashlib.sha256(
                              "|".join(e["canonical_id"] for e in batch).encode()).hexdigest()[:12],
                          "cells": cells})
        sched[zone] = {"namespace": ns, "arms": list(arms),
                       "instances": len(entries),
                       "cells": sum(len(w["cells"]) for w in waves), "waves": waves}
    return sched


def arm_system_prompt(pkg: dict, arm: str, card_text: str | None) -> str:
    """Card-memory prompt. ONE owner of the recalled-case header/footer:
    CARD_BUILDER (round-3 blocker 1c — cards carry the wrapper; the grid
    inserts the card text verbatim and never wraps it again)."""
    mem = ""
    if arm in ("R", "X"):
        mem = "\n" + (card_text or "") + "\n"
    return pkg["agent_grid"]["system_template"].format(
        wiki=pkg["harvest"]["wiki_true_24h"],
        memory_section=mem,
        tools_json=pkg["shared_literals"]["tools_info_json"],
        act_instruction=pkg["shared_literals"]["act_instruction"])


class GridRunner:
    def __init__(self, *, entries_by_zone: dict[str, list[dict]], prompts_pkg: dict,
                 episodes_by_zone_path: dict[str, Path], judge_decisions_path: Path,
                 cards_by_task: dict[str, dict[str, str]]):
        self.pkg = prompts_pkg
        self.entries = entries_by_zone
        # main vs headroom artifacts are SEPARATED on disk (round-3 blocker 1e)
        self.episodes_by_zone_path = {z: Path(p) for z, p in episodes_by_zone_path.items()}
        self.judge_path = Path(judge_decisions_path)
        self.cards = cards_by_task
        self.done = self._load_done()

    def _load_done(self) -> set:
        done = set()
        for z, p in self.episodes_by_zone_path.items():
            if p.exists():
                for line in p.read_text().splitlines():
                    if line.strip():
                        r = json.loads(line)
                        done.add((r["canonical_id"], r["arm"]))
        return done

    def run_cells(self, engine, sim_factory, zones=("main", "hr")) -> dict:
        n_new = 0
        for zone in zones:
            ns = "agent-main" if zone == "main" else "hr"
            arms = MAIN_ARMS if zone == "main" else HR_ARMS
            out = self.episodes_by_zone_path[zone].open("a")
            entries = sorted(self.entries[zone],
                             key=lambda e: instance_wave_sort(e["canonical_id"]))
            for wi in range(0, len(entries), BATCH_SIZE):
                for e in entries[wi:wi + BATCH_SIZE]:
                    for arm in arms:
                        cid = e["canonical_id"]
                        if (cid, arm) in self.done:
                            continue
                        card = (self.cards.get(cid, {}) or {}).get(arm)
                        # round-3 blocker 1b/1d: an R/X arm NEVER runs with an
                        # empty memory section — missing card hard-refuses.
                        if arm in ("R", "X") and card is None:
                            raise ValueError(
                                f"HARD REFUSE: {cid}/{arm} arm has no bank card "
                                f"(empty-memory {arm} arms never run)")
                        env = build_synthetic_env(e["reservation"])
                        sim = sim_factory(e, arm, zone)
                        row = run_episode(
                            engine=engine, env=env,
                            system_prompt=arm_system_prompt(
                                self.pkg, arm,
                                card if arm in ("R", "X") else None),
                            agent_seed_fn=lambda step, c=cid, n=ns:
                                frozen_seed(n, c, step),
                            user_sim=sim,
                            meta={"canonical_id": cid, "arm": arm,
                                  "zone": zone,
                                  "target_rid": e["reservation"]["reservation_id"],
                                  "owner_uid": e["user"]["user_id"],
                                  "wave_index": wi // BATCH_SIZE})
                        out.write(json.dumps(row, sort_keys=True) + "\n")
                        out.flush()
                        self.done.add((cid, arm))
                        n_new += 1
        return {"cells_new": n_new,
                "cells_total": len(self.done),
                "hr_arms": list(HR_ARMS)}

    def run_judge_stage(self, engine, tasks: list[dict]) -> dict:
        """One deterministic call per (main task, card role). RAW output is the
        source of truth; the analyzer re-derives verdicts via judge_parser.
        Output wrap (round-3 blocker 1f): {decisions, audited_metadata}."""
        import re
        policy = build_judge.load_cancel_policy_excerpt()
        leak_rx = re.compile(build_judge.WINDOW_DIGITS_RE)

        def _audit_decisions(decisions: dict) -> dict:
            """Round-4 D3: route EVERY decision (including legacy flat fields)
            through the per-render leak-audited judge_parser path. Entries
            without raw_output are normalized to abstain-refuse; no pre-parsed
            label is ever trusted."""
            leaves = {}
            ok = True
            out_decisions = {}
            for cid, roles in decisions.items():
                out_decisions.setdefault(cid, {})
                for role, dec in roles.items():
                    e = next((t for t in tasks if t["canonical_id"] == cid), None)
                    card = (self.cards.get(cid, {}) or {}).get(role)
                    if isinstance(dec, dict):
                        raw = dec.get("raw_output")
                    else:
                        raw = str(dec)
                    if e is not None and card is not None:
                        rendered = build_judge.render_judge_input(
                            policy, e["instruction"], card)
                        leak_free = not leak_rx.search(rendered)
                        leaves[f"{cid}|{role}"] = leak_free
                        ok = ok and leak_free
                    parsed = judge_parser.parse_judge_output(raw or "")
                    out_decisions[cid][role] = {
                        "raw_output": raw,
                        "parser_status": parsed["status"],
                        "parser_reason": parsed.get("reason"),
                        "parser_verdict": parsed.get("verdict"),
                        "gate_decision": judge_parser.gate_decision(raw or ""),
                    }
            return out_decisions, leaves, ok

        doc = {"decisions": {}, "audited_metadata": {
            "model": "Qwen/Qwen2.5-7B-Instruct@a09a3545",
            "decode": {"temperature": 0.0, "top_p": 1.0, "max_tokens": 128, "seed": 0},
            "input_field_order": build_judge.PROMPT_TEMPLATE and
                ["policy_excerpt", "task_goal", "candidate_card"],
            "leak_grep_regex": build_judge.WINDOW_DIGITS_RE,
            "leak_grep_pass": True,
            "per_render_leak_free": {},
            "parser": "part6/judge_parser.py (frozen)",
            "normalized_from_flat": False,
        }}
        if self.judge_path.exists():
            old = json.loads(self.judge_path.read_text())
            if "decisions" in old:
                doc["decisions"] = old["decisions"]
                meta = old.get("audited_metadata", {})
                doc["audited_metadata"].update(meta)
            else:  # legacy flat decisions -> audited-parser normalization (D3)
                flat, leaves, ok = _audit_decisions(old)
                doc["decisions"] = flat
                doc["audited_metadata"]["per_render_leak_free"].update(leaves)
                doc["audited_metadata"]["leak_grep_pass"] = ok
                doc["audited_metadata"]["normalized_from_flat"] = True
        decisions = doc["decisions"]
        leaves = doc["audited_metadata"]["per_render_leak_free"]
        for e in tasks:
            cid = e["canonical_id"]
            decisions.setdefault(cid, {})
            for role in ("X", "R"):
                if role in decisions[cid]:
                    continue
                card = (self.cards.get(cid, {}) or {}).get(role)
                if card is None:
                    continue
                rendered = build_judge.render_judge_input(
                    policy, e["instruction"], card)
                leak_free = not leak_rx.search(rendered)
                leaves[f"{cid}|{role}"] = leak_free
                if not leak_free:
                    doc["audited_metadata"]["leak_grep_pass"] = False
                raw = engine.chat([{"role": "user", "content": rendered}],
                                  temperature=0.0, seed=0, max_tokens=128)
                parsed = judge_parser.parse_judge_output(raw)
                decisions[cid][role] = {
                    "raw_output": raw,
                    "parser_status": parsed["status"],
                    "parser_reason": parsed.get("reason"),
                    "parser_verdict": parsed.get("verdict"),
                    "gate_decision": judge_parser.gate_decision(raw),
                }
        doc["audited_metadata"]["n_calls"] = sum(len(v) for v in decisions.values())
        doc["audited_metadata"]["n_abstain_like"] = sum(
            1 for v in decisions.values() for r in v.values()
            if r["parser_status"] != "ok" or r.get("parser_verdict") == "abstain")
        self.judge_path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
        return {"judge_calls": doc["audited_metadata"]["n_calls"],
                "tasks": len(decisions),
                "leak_grep_pass": doc["audited_metadata"]["leak_grep_pass"]}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest-dir", default=str(PART6))
    ap.add_argument("--out", default=str(PART6 / "grid_plan.json"))
    ap.add_argument("--episodes-main-out", default=str(PART6 / "grid_episodes_main.jsonl"))
    ap.add_argument("--episodes-hr-out", default=str(PART6 / "grid_episodes_hr.jsonl"))
    ap.add_argument("--judge-out", default=str(PART6 / "judge_decisions.json"))
    ap.add_argument("--cards", default=None, help="bank cards JSON (main tasks)")
    ap.add_argument("--engine", choices=["vllm"], default="vllm")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--judge-stage", action="store_true")
    args = ap.parse_args()

    if args.run or args.judge_stage:
        pkg = json.loads((PART6 / "PART_VI_PROMPTS.json").read_text())
        mdir = Path(args.manifest_dir)
        entries = {z: json.loads((mdir / f"manifest_{z}.json").read_text())["entries"]
                   for z in ("main", "hr")}
        cards = {}
        if args.cards:
            doc = json.loads(Path(args.cards).read_text())
            # exact harvest export shape: {target: {role: card_text}}
            cards = doc["cards"] if "cards" in doc else doc
        runner = GridRunner(
            entries_by_zone=entries, prompts_pkg=pkg,
            episodes_by_zone_path={
                "main": Path(args.episodes_main_out),
                "hr": Path(args.episodes_hr_out),
            },
            judge_decisions_path=Path(args.judge_out),
            cards_by_task=cards)
        from rollout_engine import vllm_engine
        engine = vllm_engine()
        if args.run:
            from harvest_runner import vllm_sim_factory
            def sim_factory(e, arm, zone):
                return vllm_sim_factory(engine)(
                    e, f"{e['canonical_id']}|{arm}")
            print(json.dumps(runner.run_cells(engine, sim_factory), indent=2))
        if args.judge_stage:
            print(json.dumps(runner.run_judge_stage(engine, entries["main"]), indent=2))
        return 0

    sched = build_schedule(Path(args.manifest_dir))
    doc = {
        "frozen_at": "2026-08-11",
        "mode": "dry-run executable schedule (state machine identical to --run)",
        "engine_spec": {"vllm": "offline", "fp16": True, "gpu_mem_util": 0.85,
                         "max_model_len": 8192, "agent_temperature": 0.7,
                         "user_sim_temperature": 0.0, "max_steps": 30,
                         "gpus": "5-7"},
        "seed_formula": ("seed(ns,id,turn) = int.from_bytes(md5(utf8('tau6|' + ns + "
                         "'|' + canonical_id + '|' + decimal(turn))).digest()[:4], "
                         "'little') % 2**31 (v3 §5 verbatim)"),
        "headroom_note": ("B4: headroom cells are N/X only (80 cells); the R "
                          "headroom card never existed — deleted, recorded in "
                          "PART_VI_FREEZE_DECISIONS.md"),
        "snapshot_contract": {
            "required_per_cell": ["steps_log", "user_msgs", "db_before", "db_after",
                                   "initial_db_hash", "final_db_hash"],
            "schema": "rollout_engine.compact_snapshot (compact v1)",
            "note": ("analyzer hard-refuses cells whose action log claims a cancel "
                     "without a VERIFIED snapshot cancellation (correction C4)"),
        },
        "schedule": sched,
    }
    Path(args.out).write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    print(f"dry-run schedule written: {args.out}; main cells "
          f"{sched['main']['cells']} ({sched['main']['instances']} instances, "
          f"{len(sched['main']['waves'])} waves), hr cells {sched['hr']['cells']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
