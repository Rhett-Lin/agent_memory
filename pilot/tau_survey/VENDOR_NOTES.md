# VENDOR_NOTES — exact sources read for the τ-bench survey

## Repos (cloned 2026-08-10 into `pilot/tau_survey/vendor/`)

| Repo | Commit hash | Commit date | License |
|---|---|---|---|
| sierra-research/tau-bench (v1) | `59a200c6d575d595120f1cb70fea53cef0632f6b` | 2026-03-18 | MIT © 2024 Sierra |
| sierra-research/tau2-bench (τ²/τ³, "the fixed tasks") | `668d3bcd135c02aa3438f987ef45735b7c163ee3` | 2026-08-06 | MIT © 2025 Sierra Research |

v1 README note (lines 3-5): tasks in v1 are outdated; τ³-bench has the fixed
airline/retail tasks + new domains. ν1 git log confirms last functional change long
before; README pointer added 2026-03-18 (commit e44ef65).

## What was read where (v1 unless marked)

- `tau_bench/envs/base.py` (all 164 lines) — reward = DB-hash equality vs GT-action
  replay + output-string containment; hash via `sha256(str(to_hashable(db)))`.
- `tau_bench/envs/airline/wiki.md` (all 70 lines) — the policy "program".
- `tau_bench/envs/airline/env.py`, `rules.py` (RULES=[]), `data/__init__.py`.
- `tau_bench/envs/airline/tasks_test.py` — 50 test tasks, parsed with `ast` (no import).
  Category counts: 15 cancel, 20 update_flights, 6 update_bags, 9 book, 4 transfer,
  3 send_certificate, 3 update_passengers (write actions); 7 zero-write tasks;
  4 tasks with output-string checks (ids 2, 8, 9, 44 — verified by ast literal_eval).
- `tau_bench/envs/airline/tools/{cancel_reservation,update_reservation_baggages,update_reservation_flights,send_certificate}.py`
  — read in full; they mutate DB with NO policy checks (availability/payment rails only).
- `tau_bench/envs/airline/tools/__init__.py` listing, plus file list of all 14 tools.
- `tau_bench/envs/retail/wiki.md` (grep), `tasks_test.py` head + ast parse — 115 tasks.
- `tau_bench/agents/tool_calling_agent.py` (full), `chat_react_agent.py` (head ~60),
  `run.py` (full), `types.py` (head), `model_utils/args.py` (head).
- `tau_bench/envs/user.py` (full) — user-sim strategies human/llm/react/verify/reflection;
  `llm` strategy is plain-text chat via litellm; `###STOP###` termination.
- `setup.py` — deps: litellm/openai/anthropic/mistral/… ; `python_requires` implicit;
  NOTE: v1 code uses `dict[str, Any]` annotations at class level → **Python ≥ 3.9
  required** (system python3.8 fails; conda `causalmemagent` = 3.11.15 works).
- Data JSONs (sampled heads + counts): flights=300, users=500, reservations=2000.

## τ²/τ³ (cross-check only)

- `data/tau2/domains/airline/policy.md` — same core gates (24h window, business,
  airline-cancelled, insurance-covered reason), restructured text.
- `data/tau2/domains/airline/tasks.json` — 50 tasks with structured
  `evaluation_criteria` (actions / communicate_info / nl_assertions / reward_basis);
  all 50 have reward_basis = [DB, COMMUNICATE]; 13 tasks have refusal/deception
  "purpose" descriptions; task id "1" is an explicit <48h cancellation edge case.
- `src/tau2/evaluator/evaluator_env.py` — deterministic replay → DB-hash comparison;
  explicitly supports re-grading logged trajectories (`strict_replay=False`).
- `src/tau2/evaluator/evaluator_nl_assertions.py` — LLM-judged; not needed for our
  outcome if we grade on DB+ACTION only.

## Execution receipts (CPU only, no GPU/model)

- `pilot/tau_survey/verify_traps_cpu.py` — run with
  `/work1/zixuan/envs/conda_envs/causalmemagent/bin/python` (3.11.15). Result:
  for v1 tasks 49 (MDCLVA) and 18 (SI5UKW): GT replay == fresh DB (True) and a
  wrong-policy `cancel_reservation` changes the DB hash (True) → trap is verifiably
  env-detectable; GT replay determinism check on task 8 passed. Task 8/9 legal
  cancels confirmed within-24h (created_at 2024-05-14T16:03 vs env-now
  2024-05-15T15:00).

## Data root

`/work1/zixuan/data/agent_memory/tau_bench/` was created per server rules. It is
currently empty on purpose: all benchmark data is self-contained in the vendored
repos; nothing external was downloaded beyond the two git clones.
