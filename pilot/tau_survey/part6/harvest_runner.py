"""Part VI harvest runner (adjudication round-2 B2): REAL executable state
machine. `--dry-run` keeps the planner behavior; `--run` executes the harvest
against an injected engine (vLLM in production, scripted fake in fixtures).

State machine (frozen, v3 §4 + corrections C2/B2):
  - source pool: manifest_src.json; per-role candidate order =
    harvest_candidate_rank_within_role ascending;
  - binding order per role: hr/cal targets first, then main (global
    reservation order); per target: scan candidates in rank order (skipping
    accepted/exhausted), at most 4 fresh candidates, each up to its remaining
    global attempts (A=3); FIRST pass binds the target; accepted sources are
    never reused;
  - attempt episode: harvest system prompt (X: mutated 48h wiki; R: true
    wiki) + real env (synthetic DB injected); pass gate =
    card_builder.check_harvest_pass (B3-hardened); card build =
    card_builder.build_card; over-cap-after-shrink cards count as failures;
  - attempt tag = task_ns|role|cand_ord|att (cand_ord = ordinal position of
    the candidate in the target's scanned sequence); per-step agent seed =
    frozen_seed("harvest", tag, step) (step 0 == v3 §4 attempt seed); user
    seed = frozen_seed("user", tag, step);
  - resumable ledger: deterministic JSONL records per attempt/acceptance/
    binding/balancing action; restarting replays the ledger, skips completed
    work, and yields state byte-identical to an uninterrupted run (T03);
  - pair balancing: main tasks are canonical_id-ordered in the binding list;
    task i pairs its X card with its R card (acceptance maps are keyed by
    target index, so replacements stay aligned); mismatch rejects the X card
    and re-harvests that target from remaining pool attempts;
  - termination: bank fill == 280 X / 300 R with every main pair balanced =>
    DONE; any shortfall after pool exhaustion => NOT_ESTIMATED.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PART6 = Path(__file__).resolve().parent
sys.path.insert(0, str(PART6))

import card_builder  # noqa: E402
from analyze_tau import frozen_seed  # noqa: E402
from rollout_engine import build_synthetic_env, run_episode  # noqa: E402

REQUIRED = {"X": {"hr": 40, "main": 240}, "R": {"cal": 60, "main": 240}}
BINDING_ORDER = {"X": ["hr", "main"], "R": ["cal", "main"]}
MAX_CAND_PER_TARGET = 4
ATTEMPTS_PER_SOURCE = 3            # frozen by feasibility ruling (C2)


def attempt_seed(task_ns: str, role: str, candidate_idx: int, attempt_idx: int) -> int:
    """THE ONE byte-exact attempt-seed serialization (V4 §3, round-3 blocker 2b):
        md5(task_ns + "|" + role + "|" + candidate_idx + "|" + attempt_idx)
        first 4 bytes little-endian mod 2^31
    with candidate_idx = cand_ord (ordinal in the target's scanned sequence,
    0-based). Per-step agent turn seeds use turn = att + step:
        attempt_seed(task_ns, role, cand_ord, att + step)  (step 0 == attempt seed).
    Anchor constants pinned by runner fixture T04."""
    import hashlib
    s = f"{task_ns}|{role}|{candidate_idx}|{attempt_idx}"
    return int.from_bytes(hashlib.md5(s.encode()).digest()[:4], "little") % 2**31


def harvest_system_prompt(pkg: dict, role: str) -> str:
    wiki = pkg["harvest"]["wiki_mutated_48h"] if role == "X" \
        else pkg["harvest"]["wiki_true_24h"]
    return pkg["harvest"]["system_template"].format(
        wiki=wiki,
        tools_json=pkg["shared_literals"]["tools_info_json"],
        act_instruction=pkg["shared_literals"]["act_instruction"])


class StopHarvest(Exception):
    """Fixture/rehearsal control: raised by an attempt hook to simulate a kill."""


class HarvestRunner:
    def __init__(self, *, src_entries: list[dict],
                 targets_by_role: dict[str, list[str]],
                 targets_zone_by_role: dict[str, list[str]],
                 prompts_pkg: dict, tok, ledger_path: Path,
                 attempts_per_source: int = ATTEMPTS_PER_SOURCE,
                 required: dict | None = None):
        self.pkg = prompts_pkg
        self.required = required or REQUIRED
        self.tok = tok
        self.A = attempts_per_source
        self.ledger_path = Path(ledger_path)
        self.targets = targets_by_role
        self.target_zones = targets_zone_by_role
        self.cands = {r: sorted([e for e in src_entries if e["role"] == r],
                                key=lambda e: e["harvest_candidate_rank_within_role"])
                      for r in ("X", "R")}
        self.attempts_used = {r: [0] * len(self.cands[r]) for r in ("X", "R")}
        self.accepted = {r: {} for r in ("X", "R")}      # pos -> card
        self.bound = {r: {} for r in ("X", "R")}         # target_idx -> pos
        # cumulative distinct candidates tried per (role, target) — round-3 2a:
        # the <=4 cap spans initial binding, pair rejection, replacement, resume
        self.tried = {r: {} for r in ("X", "R")}         # target_idx -> [pos in scan order]
        self.unfilled = {r: [] for r in ("X", "R")}
        self.records = []
        self.attempt_hook = None
        if self.ledger_path.exists():
            self._replay_ledger()
        self.ledger = self.ledger_path.open("a")

    # ---- ledger ----------------------------------------------------------
    def _emit(self, rec: dict):
        self.records.append(rec)
        self.ledger.write(json.dumps(rec, sort_keys=True) + "\n")
        self.ledger.flush()

    def _replay_ledger(self):
        for line in self.ledger_path.read_text().splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            self.records.append(rec)
            role = rec.get("role")
            kind = rec.get("rec")
            if kind == "attempt":
                pos = rec["rank_pos"]
                self.attempts_used[role][pos] = max(
                    self.attempts_used[role][pos], rec["seed_att_idx"] + 1)
                t = self.tried[role].setdefault(rec["target_idx"], [])
                if pos not in t:
                    t.append(pos)
            elif kind == "accept":
                self.accepted[role][rec["rank_pos"]] = rec["card"]
                self.bound[role][rec["target_idx"]] = rec["rank_pos"]
            elif kind in ("unbind_x", "unbind_r"):
                t = rec["target_idx"]
                pos = self.bound[role].pop(t, None)
                if pos is not None:
                    self.accepted[role].pop(pos, None)
            elif kind == "pair_padded":
                # durable resume (round-4 D1): restore the padding-removed cards
                for role_key, pos_key, card_key in (
                        ("X", "x_rank_pos", "x_card"), ("R", "r_rank_pos", "r_card")):
                    if pos_key in rec:
                        self.accepted[role_key][rec[pos_key]] = rec[card_key]
            elif kind == "target_unfilled":
                self.unfilled[role].append(rec["target_idx"])

    # ---- one attempt ------------------------------------------------------
    def _attempt(self, engine, sim_factory, role: str, target_idx: int,
                 pos: int, cand_ord: int) -> dict:
        inst = self.cands[role][pos]
        att = self.attempts_used[role][pos]
        task_ns = self.targets[role][target_idx]
        tag = f"{task_ns}|{role}|{cand_ord}|{att}"
        env = build_synthetic_env(inst["reservation"])
        sim = sim_factory(inst, tag)
        row = run_episode(
            engine=engine, env=env,
            system_prompt=harvest_system_prompt(self.pkg, role),
            # V4 §3 byte-exact serialization: step 0 == attempt seed;
            # step s uses turn = att + s
            agent_seed_fn=lambda step: attempt_seed(task_ns, role, cand_ord, att + step),
            user_sim=sim,
            meta={"target_rid": inst["reservation"]["reservation_id"],
                  "owner_uid": inst["user"]["user_id"],
                  "canonical_id": inst["canonical_id"], "role": role})
        gate = card_builder.check_harvest_pass(row, inst, role)
        card, reason = None, None
        if gate["pass"]:
            card = card_builder.build_card(row, inst, role, self.pkg, self.tok)
            if not card["valid"]:
                gate["pass"] = False
                reason = card["reason"]
        self.attempts_used[role][pos] = att + 1
        self._emit({
            "rec": "attempt", "role": role, "target_idx": target_idx,
            "target_canonical_id": task_ns,
            "rank_pos": pos, "cand_ord": cand_ord, "seed_att_idx": att,
            "attempt_tag": tag,
            "seed_step0": attempt_seed(task_ns, role, cand_ord, att),
            "passed": bool(gate["pass"]),
            "fail_reason": reason, "checks": dict(gate["checks"]),
            "episode": row})
        return {"gate": gate, "card": card, "row": row, "pos": pos}

    def _bind_target(self, engine, sim_factory, role: str, target_idx: int,
                     exclude: frozenset = frozenset()) -> bool:
        tried = self.tried[role].setdefault(target_idx, [])
        for pos in range(len(self.cands[role])):
            if len(tried) >= MAX_CAND_PER_TARGET:
                break                                    # cumulative cap (round-3 2a)
            if (pos in exclude or pos in tried or pos in self.accepted[role]
                    or self.attempts_used[role][pos] >= self.A):
                continue
            tried.append(pos)
            cand_ord = len(tried) - 1                  # 0-based ordinal in scan sequence
            while self.attempts_used[role][pos] < self.A:
                if self.attempt_hook is not None:
                    self.attempt_hook()
                out = self._attempt(engine, sim_factory, role, target_idx,
                                    pos, cand_ord)
                if out["gate"]["pass"]:
                    self.accepted[role][pos] = out["card"]
                    self.bound[role][target_idx] = pos
                    self._emit({"rec": "accept", "role": role,
                                "target_idx": target_idx,
                                "target_canonical_id": self.targets[role][target_idx],
                                "rank_pos": pos, "card": out["card"]})
                    return True
        return False

    def _bind_all(self, engine, sim_factory):
        for role in ("X", "R"):
            for t_idx in range(len(self.targets[role])):
                if t_idx in self.bound[role] or t_idx in self.unfilled[role]:
                    continue
                if not self._bind_target(engine, sim_factory, role, t_idx):
                    self.unfilled[role].append(t_idx)
                    self._emit({"rec": "target_unfilled", "role": role,
                                "target_idx": t_idx,
                                "target_canonical_id": self.targets[role][t_idx]})

    def _main_indices(self, role: str) -> list[int]:
        return [i for i, z in enumerate(self.target_zones[role]) if z == "main"]

    def _balance_main_pairs(self, engine, sim_factory) -> dict:
        all_ok = True
        for ix, ir in zip(self._main_indices("X"), self._main_indices("R")):
            excluded: set[int] = set()
            while True:
                if ix not in self.bound["X"] or ir not in self.bound["R"]:
                    all_ok = False
                    break
                cx = self.accepted["X"][self.bound["X"][ix]]
                cr = self.accepted["R"][self.bound["R"][ir]]
                bal = card_builder.pair_balance(
                    dict(cx, tokens=card_builder.n_tokens(self.tok, cx["card_text"])),
                    dict(cr, tokens=card_builder.n_tokens(self.tok, cr["card_text"])),
                    self.tok)
                if bal["ok"]:
                    if bal["action"] == "padding_removed":
                        self.accepted["X"][self.bound["X"][ix]] = bal["x_card"]
                        self.accepted["R"][self.bound["R"][ir]] = bal["r_card"]
                        # ledger-persisted (round-4 D1): padding-removed cards
                        # survive kill+resume by replay
                        self._emit({"rec": "pair_padded", "pair": [ix, ir],
                                    "x_rank_pos": self.bound["X"][ix],
                                    "r_rank_pos": self.bound["R"][ir],
                                    "x_card": bal["x_card"], "r_card": bal["r_card"],
                                    "delta_tokens": bal["delta_tokens"]})
                    break
                # X card rejected: unbind and re-harvest the same target from
                # the NEXT candidates in rank order (never retry rejected).
                self._emit({"rec": "reject_pair", "pair": [ix, ir],
                            "card_source_instance_id": cx["source_instance_id"],
                            "delta_tokens": bal["delta_tokens"]})
                pos = self.bound["X"].pop(ix)
                del self.accepted["X"][pos]
                excluded.add(pos)
                self._emit({"rec": "unbind_x", "role": "X", "target_idx": ix,
                            "target_canonical_id": self.targets["X"][ix]})
                if not self._bind_target(engine, sim_factory, "X", ix,
                                         exclude=frozenset(excluded)):
                    all_ok = False
                    self.unfilled["X"].append(ix)
                    self._emit({"rec": "target_unfilled", "role": "X",
                                "target_idx": ix,
                                "target_canonical_id": self.targets["X"][ix]})
                    break
                # re-bound: loop re-checks the replacement pair
        return {"all_balanced": all_ok}

    def run(self, engine, sim_factory) -> dict:
        self._bind_all(engine, sim_factory)
        balance = self._balance_main_pairs(engine, sim_factory)
        fills = {r: len(self.accepted[r]) for r in ("X", "R")}
        fill_ok = (fills["X"] == sum(self.required["X"].values())
                   and fills["R"] == sum(self.required["R"].values()))
        terminal = "DONE" if (fill_ok and balance["all_balanced"]
                              and not self.unfilled["X"]
                              and not self.unfilled["R"]) else "NOT_ESTIMATED"
        summary = {"rec": "bank_summary", "fills": fills, "fill_ok": fill_ok,
                   "all_balanced": balance["all_balanced"],
                   "unfilled": {r: len(self.unfilled[r]) for r in ("X", "R")},
                   "terminal": terminal,
                   "attempts_total": sum(sum(v) for v in self.attempts_used.values())}
        self._emit(summary)
        return summary

    def state_view(self) -> dict:
        """Deterministic state snapshot (fixtures compare byte-wise)."""
        return {
            "attempts_used": {r: list(self.attempts_used[r]) for r in ("X", "R")},
            "accepted_counts": {r: len(self.accepted[r]) for r in ("X", "R")},
            "bound": {r: {str(k): v for k, v in sorted(self.bound[r].items())}
                      for r in ("X", "R")},
            "tried": {r: {str(k): list(v) for k, v in sorted(self.tried[r].items())}
                      for r in ("X", "R")},
            "cards": {r: [self.accepted[r][k]["card_text"]
                          for k in sorted(self.accepted[r])] for r in ("X", "R")},
        }

    # ---- grid-consumable exports (round-3 blocker 1) -----------------------
    def export_cards_for_grid(self) -> dict[str, dict[str, str]]:
        """EXACT wire shape the grid runner consumes:
            {target_canonical_id: {role: card_text}}
        zone coverage: main tasks get both X and R; hr tasks get X (real card —
        headroom X is never card=None); cal tasks get R (G-S input)."""
        out: dict[str, dict[str, str]] = {}
        for role in ("X", "R"):
            for t_idx, pos in self.bound[role].items():
                cid = self.targets[role][t_idx]
                out.setdefault(cid, {})[role] = self.accepted[role][pos]["card_text"]
        return out

    def emit_bank_summary(self) -> dict:
        """Analyzer bank-summary JSON, derived ONLY from the ledger-replayable
        state (round-3 blocker 1g)."""
        def zone_count(role, zone):
            return sum(1 for t_idx, z in enumerate(self.target_zones[role])
                       if z == zone and t_idx in self.bound[role])
        x_main, x_hr = zone_count("X", "main"), zone_count("X", "hr")
        r_main, r_cal = zone_count("R", "main"), zone_count("R", "cal")
        cards = [self.accepted[r][p] for r in ("X", "R") for p in self.accepted[r]]
        prov_ok = all(c.get("provenance") == card_builder.PROVENANCE_LABEL
                      and c.get("valid") for c in cards)
        src_unique = len({c["source_instance_id"] for c in cards}) == len(cards)
        return {
            "X_main": {"accepted": x_main, "alive": x_main, "model_only": True},
            "X_hr": {"accepted": x_hr, "alive": x_hr, "model_only": True},
            "R_main": {"accepted": r_main, "alive": r_main, "model_only": True},
            "R_cal": {"accepted": r_cal, "alive": r_cal, "model_only": True},
            "provenance_complete": bool(prov_ok and src_unique),
            "X_provenance_complete": bool(prov_ok and src_unique),
            "provenance_label": card_builder.PROVENANCE_LABEL,
            "attempts_total": sum(sum(v) for v in self.attempts_used.values()),
        }


# ---------------------------------------------------------------------------
# Sim factories + CLI
# ---------------------------------------------------------------------------

def vllm_sim_factory(engine):
    from harness import VLLMUserSim

    def make(inst, tag):
        return VLLMUserSim(engine, inst["instruction"],
                           seed=frozen_seed("user", tag, 0))
    return make


def load_plan(manifest_dir: Path, attempts_per_source: int) -> dict:
    src = json.loads((manifest_dir / "manifest_src.json").read_text())["entries"]
    plan = {}
    for role in ("X", "R"):
        cands = [e for e in src if e["role"] == role]
        cands.sort(key=lambda e: e["harvest_candidate_rank_within_role"])
        targets = []
        for zone in BINDING_ORDER[role]:
            man = json.loads((manifest_dir / f"manifest_{zone}.json").read_text())["entries"]
            for t in man:
                targets.append(t["canonical_id"])
        assert len(targets) == sum(REQUIRED[role].values())
        rows = []
        for t in targets:
            cand_view = []
            for ci, c in enumerate(cands[:MAX_CAND_PER_TARGET]):
                cand_view.append({
                    "candidate_rank": c["harvest_candidate_rank_within_role"],
                    "candidate_canonical_id": "tau6/" + c["canonical_id"],
                    "attempts": [{"attempt_idx": ai,
                                  "seed": attempt_seed(t, role, ci, ai)}
                                 for ai in range(attempts_per_source)]})
            rows.append({
                "target_canonical_id": t,
                "budget": {"max_candidates": MAX_CAND_PER_TARGET,
                           "max_attempts_per_candidate_global": attempts_per_source},
                "initial_candidate_window": cand_view,
                "note": ("candidates beyond the window are tried in rank order as "
                         "earlier ones exhaust their global attempts; attempt seeds "
                         "use cand_ord = ordinal position in the target's scanned "
                         "sequence"),
            })
        plan[role] = {"pool_size": len(cands),
                      "attempts_per_source": attempts_per_source,
                      "worst_case_episodes": len(cands) * attempts_per_source,
                      "targets": rows}
    return plan


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest-dir", default=str(PART6))
    ap.add_argument("--attempts-per-source", type=int, default=ATTEMPTS_PER_SOURCE)
    ap.add_argument("--out", default=str(PART6 / "harvest_plan.json"))
    ap.add_argument("--ledger", default=str(PART6 / "harvest_ledger.jsonl"))
    ap.add_argument("--cards-out", default=None)
    ap.add_argument("--engine", choices=["vllm"], default="vllm")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--run", action="store_true")
    args = ap.parse_args()

    if args.run:
        pkg = json.loads((PART6 / "PART_VI_PROMPTS.json").read_text())
        mdir = Path(args.manifest_dir)
        src = json.loads((mdir / "manifest_src.json").read_text())["entries"]
        targets, zones = {}, {}
        for role in ("X", "R"):
            t, z = [], []
            for zone in BINDING_ORDER[role]:
                for e in json.loads((mdir / f"manifest_{zone}.json").read_text())["entries"]:
                    t.append(e["canonical_id"])
                    z.append(zone)
            targets[role], zones[role] = t, z
        from rollout_engine import vllm_engine
        engine = vllm_engine()
        runner = HarvestRunner(
            src_entries=src, targets_by_role=targets, targets_zone_by_role=zones,
            prompts_pkg=pkg, tok=card_builder.load_tokenizer(),
            ledger_path=Path(args.ledger),
            attempts_per_source=args.attempts_per_source)
        summary = runner.run(engine, vllm_sim_factory(engine))
        if args.cards_out:
            out = {
                "summary": summary,
                "cards": runner.export_cards_for_grid(),  # {target: {role: card_text}}
                "cards_full": [runner.accepted[r][k] for r in ("X", "R")
                               for k in sorted(runner.accepted[r])],
                "bank_summary": runner.emit_bank_summary(),
            }
            Path(args.cards_out).write_text(
                json.dumps(out, indent=2, sort_keys=True) + "\n")
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0 if summary["terminal"] == "DONE" else 2

    plan = load_plan(Path(args.manifest_dir), args.attempts_per_source)
    doc = {
        "frozen_at": "2026-08-11",
        "mode": ("dry-run executable plan (the --run state machine consumes this "
                 "same contract; only the engine object is injected)"),
        "contract": {
            "binding_order_per_role": BINDING_ORDER,
            "max_candidates_per_target": MAX_CAND_PER_TARGET,
            "attempts_per_source": args.attempts_per_source,
            "attempt_seed_formula": "frozen_seed harvest ns (v3 §4/§5 verbatim)",
            "pass_gate": "card_builder.check_harvest_pass (B3-hardened, frozen)",
            "card_rules": {"token_cap": card_builder.TOKEN_CAP,
                           "pair_balance_max_delta": card_builder.PAIR_BALANCE_MAX_DELTA,
                           "provenance_label": card_builder.PROVENANCE_LABEL},
            "exhaustion_rule": "fill short of required counts => NOT_ESTIMATED",
            "required_fills": REQUIRED,
        },
        "plan": plan,
    }
    Path(args.out).write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    tot = sum(p["worst_case_episodes"] for p in plan.values())
    print(f"dry-run plan written: {args.out}; worst-case episodes {tot} "
          f"(pools X={plan['X']['pool_size']}, R={plan['R']['pool_size']}, "
          f"A={args.attempts_per_source})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
