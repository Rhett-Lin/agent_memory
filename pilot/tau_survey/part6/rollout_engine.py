"""Part VI rollout engine (adjudication round-2 B2): executable protocol +
generic episode loop with snapshot capture.

Engine protocol (dependency-injected): any object with
    chat(messages, temperature, seed, max_tokens) -> str
works — the vLLM production engine (smoke harness VLLMEngine, reused by
import) and the scripted FakeEngine used by the state-machine fixtures. No
episode internals depend on the engine class.

Snapshot capture (frozen, compact schema — full DBs would be ~3 MB/episode):
    db_snapshot(env, target_rid) = {
        "_compact": "v1",
        "full_hash": env.get_data_hash(),
        "flights_hash": sha(to_hashable(env.data["flights"])),
        "reservations": {target_rid: <full entry copy>},
        "users": {owner_uid: <full entry copy>},
        "other_reservations_hash": sha(all reservations except target),
        "other_users_hash": sha(all users except owner),
    }
detector.delta_decomposition understands BOTH this compact schema and the
full-dict schema used by the analyzer fixtures (correction C4 semantics
unchanged: verified cancellation = status flip; pure = status flip + appended
negative refund rows and NOTHING else changed anywhere).

Seeds: per-step agent seed and user seed come from caller-supplied functions
(harvest/grid runners supply the frozen namespace formulas); every row of the
episode tape records the seeds actually used.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

PART6 = Path(__file__).resolve().parent
SMOKE = PART6.parent / "smoke"
if str(SMOKE) not in sys.path:
    sys.path.insert(0, str(SMOKE))

import common  # noqa: E402,F401  (vendor sys.path bootstrap BEFORE tau_bench imports)
from tau_bench.envs.base import consistent_hash, to_hashable  # noqa: E402
from tau_bench.types import RESPOND_ACTION_NAME  # noqa: E402
from harness import parse_action  # noqa: E402  (import reuse, not forked)

MAX_STEPS = 30


def compact_snapshot(env, target_rid: str, owner_uid: str) -> dict:
    data = env.data
    others_res = {k: v for k, v in data["reservations"].items() if k != target_rid}
    others_usr = {k: v for k, v in data["users"].items() if k != owner_uid}
    return {
        "_compact": "v1",
        "full_hash": env.get_data_hash(),
        "flights_hash": consistent_hash(to_hashable(data["flights"])),
        "reservations": {target_rid: copy.deepcopy(data["reservations"].get(target_rid))},
        "users": {owner_uid: copy.deepcopy(data["users"].get(owner_uid))},
        "other_reservations_hash": consistent_hash(to_hashable(others_res)),
        "other_users_hash": consistent_hash(to_hashable(others_usr)),
    }


class _VLLMChat:
    """Production chat engine: ONE offline vLLM instance with the frozen
    runtime config (V4 §4): fp16 explicitly (dtype="float16", NOT auto/bf16),
    gpu_mem_util 0.85, max_model_len 8192, fixed seed 1234."""

    def __init__(self, max_model_len: int = 8192):
        from transformers import AutoTokenizer
        from vllm import LLM
        from common import MODEL_PATH

        self.tok = AutoTokenizer.from_pretrained(MODEL_PATH)
        self.llm = LLM(
            model=MODEL_PATH,
            max_model_len=max_model_len,
            gpu_memory_utilization=0.85,
            seed=1234,
            enforce_eager=False,
            disable_log_stats=True,
            dtype="float16",
        )
        self.gen_tokens = 0
        self.prompt_tokens = 0

    def chat(self, messages: list[dict], temperature: float, seed: int,
             max_tokens: int = 512) -> str:
        from vllm import SamplingParams

        prompt = self.tok.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        sp = SamplingParams(
            temperature=temperature, top_p=0.9 if temperature > 0 else 1.0,
            max_tokens=max_tokens, seed=seed,
        )
        req = self.llm.generate([prompt], sp, use_tqdm=False)[0]
        out = req.outputs[0]
        self.prompt_tokens += len(req.prompt_token_ids)
        self.gen_tokens += len(out.token_ids)
        return out.text.strip()


def vllm_engine(max_model_len: int = 8192):
    """Production engine (GPU, constructed only under --run)."""
    return _VLLMChat(max_model_len=max_model_len)


def scripted_user_sim(replies: list[str]):
    """Minimal user-sim with the VLLMUserSim interface (reset/step)."""
    class _Sim:
        def __init__(self):
            self.calls = 0

        def reset(self, instruction=None):
            self.calls += 1
            return replies[min(self.calls - 1, len(replies) - 1)]

        def step(self, content):
            self.calls += 1
            return replies[min(self.calls - 1, len(replies) - 1)]

        def get_total_cost(self):
            return 0.0
    return _Sim()


def build_synthetic_env(reservation: dict):
    """Real vendor env with the synthetic instance's DB injected (frozen
    rebuild rule: generator.build_synthetic_db)."""
    import generator as G
    import tau_bench.envs.airline.env as airline_env

    data = G.load_data()
    airline_env.load_data = lambda: G.build_synthetic_db(data, reservation)
    from tau_bench.envs.airline.env import MockAirlineDomainEnv
    return MockAirlineDomainEnv(user_strategy="human", task_index=0)


def run_episode(*, engine, env, system_prompt: str,
                agent_seed_fn, max_steps: int = MAX_STEPS,
                agent_temperature: float = 0.7, agent_max_tokens: int = 512,
                user_sim=None, meta: dict | None = None) -> dict:
    """Generic episode loop (smoke harness semantics + snapshot capture).

    user_sim: object with reset()/step()/get_total_cost() (vLLMUserSim or
    scripted). The first user message always comes from env.reset (which
    calls user.reset exactly once internally — never reset the sim twice).
    """
    if user_sim is None:
        raise ValueError("user_sim required (scripted or VLLMUserSim)")
    env.user = user_sim
    obs = env.reset(task_index=0)          # resets DB via injected load_data
    first = obs if isinstance(obs, str) else getattr(obs, "observation", obs)

    target_rid = (meta or {}).get("target_rid")
    owner_uid = (meta or {}).get("owner_uid")
    db_before = compact_snapshot(env, target_rid, owner_uid) if target_rid else None
    # Pending snapshot = last KNOWN-GOOD DB state. Vendor Env.step() runs
    # calculate_reward() at `done`, which RELOADS env.data and replays GT —
    # so env.data after a terminal step is polluted. Terminal actions
    # (respond/STOP or transfer_to_human_agents) never write the DB, hence
    # the pending snapshot after the last successful writer IS the true final
    # state (same discipline as the smoke harness's last-pre-hash).
    pending = db_before

    messages = [{"role": "system", "content": system_prompt},
                {"role": "user", "content": first}]
    steps_log, user_msgs = [], [first]
    done_reason = "step_cap"
    reward = 0.0

    steps = 0
    for step in range(max_steps):
        seed = agent_seed_fn(step)
        content = engine.chat(messages, temperature=agent_temperature,
                              seed=seed, max_tokens=agent_max_tokens)
        action, parse_ok = parse_action(content)
        response = env.step(action)
        ob = response.observation
        steps = step + 1
        steps_log.append({
            "step": step, "agent_content": content, "parse_ok": parse_ok,
            "agent_seed": seed,
            "action": {"name": action.name, "kwargs": action.kwargs},
            "observation": ob, "reward": response.reward, "done": response.done})
        if response.info and getattr(response.info, "source", None) == "user":
            user_msgs.append(ob)
        # DB may have been mutated by a successful writer call this step —
        # refresh the pending snapshot ONLY then (cheap; writers are rare).
        if target_rid and not response.done and action.name != RESPOND_ACTION_NAME \
                and not ob.startswith("Error"):
            pending = compact_snapshot(env, target_rid, owner_uid)
        obs_msg = ob if action.name == RESPOND_ACTION_NAME else "API output: " + ob
        messages.extend([{"role": "assistant", "content": content},
                         {"role": "user", "content": obs_msg}])
        if response.done:
            reward = response.reward
            done_reason = "stop_token" if "###STOP###" in ob else "transfer_to_human"
            break

    row = {
        "steps_log": steps_log,
        "user_msgs": user_msgs,
        "reward": reward,
        "steps": steps,
        "done_reason": done_reason,
        "initial_db_hash": db_before["full_hash"] if db_before else None,
        "final_db_hash": pending["full_hash"] if pending else None,
        "db_before": db_before,
        "db_after": pending,
        "engine_meta": {"agent_temperature": agent_temperature,
                        "max_model_len": 8192, "max_steps": max_steps,
                        "prompt_tokens": getattr(engine, "prompt_tokens", 0),
                        "gen_tokens": getattr(engine, "gen_tokens", 0)},
    }
    row.update(meta or {})
    return row
