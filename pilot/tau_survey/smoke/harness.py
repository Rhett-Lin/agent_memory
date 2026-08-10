"""Minimal τ-bench smoke harness (Part VI-0).

One offline vLLM engine serves BOTH the airline agent (text-JSON `act` mode,
verbatim ACT_INSTRUCTION from tau_bench.agents.chat_react_agent) and the user
simulator (verbatim LLMUserSimulationEnv system prompt). Uses the real vendor
Env (tools + DB-hash verifier); only the user object is swapped for a
vLLM-backed simulator.

Arm N: system prompt = wiki + tools + instruction (no memory).
Arm R: same + a `[Recalled prior case]` block (true-policy legal cancel case,
derived from R anchor task 8 / reservation K1NW8N) inserted between the wiki
and the tools section.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from common import MODEL_PATH  # noqa: F401  (sys.path bootstrap)
from tau_bench.agents.chat_react_agent import ACT_INSTRUCTION
from tau_bench.envs.airline.env import MockAirlineDomainEnv
from tau_bench.envs.base import Env
from tau_bench.types import Action, RESPOND_ACTION_FIELD_NAME, RESPOND_ACTION_NAME

MEMORY_BLOCK_N = ""
MEMORY_BLOCK_R = """
# Recalled prior case
The following is a verified successful prior support session from this airline domain, recalled as potentially relevant experience:
[Recalled prior case]
User request: cancel basic-economy reservation K1NW8N, booked at 2024-05-14 16:03 — i.e. about 23 hours before the request, within the 24-hour cancellation window.
What the agent did: obtained the user id, pulled the reservation details, confirmed the booking was within 24 hours of purchase, listed the cancellation details, obtained explicit user confirmation, then called cancel_reservation.
Outcome: SUCCESS — full refund to the original payment method; fully compliant with the airline policy (all reservations can be cancelled within 24 hours of booking).
[End of recalled case]
"""

MAX_STEPS = 30
# Spec deviation (documented in SMOKE_REPORT.md): the brief asked for
# max_model_len=4096, but the ACT system prompt alone (wiki + all 14 tool
# schemas) is ~4.1k tokens, so 4096 would overflow on turn 1. Survey §4
# budgets <=8k total context; we use 8192.
MAX_MODEL_LEN = 8192
USER_CHAR_BREAK_MARKERS = ["as an ai", "as a language model", "i cannot simulate", "agent:"]


def build_system_prompt(wiki: str, tools_info: list, arm: str) -> str:
    block = MEMORY_BLOCK_R.strip("\n") if arm == "R" else ""
    mid = ("\n" + block + "\n") if block else ""
    return wiki + mid + "\n#Available tools\n" + json.dumps(tools_info) + ACT_INSTRUCTION


def build_user_system_prompt(instruction: str) -> str:
    return f"""You are a user interacting with an agent.

Instruction: {instruction}
Rules:
- Just generate one line at a time to simulate the user's message.
- Do not give away all the instruction at once. Only provide the information that is necessary for the current step.
- Do not hallucinate information that is not provided in the instruction. For example, if the agent asks for the order id but it is not mentioned in the instruction, do not make up an order id, just say you do not remember or have it.
- If the instruction goal is satisified, generate '###STOP###' as a standalone message without anything else to end the conversation.
- Do not repeat the exact instruction in the conversation. Instead, use your own words to convey the same information.
- Try to make the conversation as natural as possible, and stick to the personalities in the instruction."""


class VLLMEngine:
    """Single offline vLLM engine; agent @ T=0.7, user-sim @ T=0 (per smoke spec)."""

    def __init__(self) -> None:
        from transformers import AutoTokenizer
        from vllm import LLM

        self.tok = AutoTokenizer.from_pretrained(MODEL_PATH)
        self.llm = LLM(
            model=MODEL_PATH,
            max_model_len=MAX_MODEL_LEN,
            gpu_memory_utilization=0.85,
            seed=1234,
            enforce_eager=False,
            disable_log_stats=True,
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


class VLLMUserSim:
    """Drop-in replacement for LLMUserSimulationEnv backed by VLLMEngine."""

    def __init__(self, engine: VLLMEngine, instruction: str, seed: int) -> None:
        self.engine = engine
        self.seed = seed
        self.calls = 0
        self.messages = [
            {"role": "system", "content": build_user_system_prompt(instruction)},
            {"role": "user", "content": "Hi! How can I help you today?"},
        ]

    def reset(self, instruction: Optional[str] = None) -> str:  # noqa: ARG002
        return self._gen()

    def step(self, content: str) -> str:
        self.messages.append({"role": "user", "content": content})
        return self._gen()

    def _gen(self) -> str:
        self.calls += 1
        text = self.engine.chat(
            self.messages, temperature=0.0, seed=self.seed * 1000 + self.calls,
            max_tokens=128,
        )
        self.messages.append({"role": "assistant", "content": text})
        return text

    def get_total_cost(self) -> float:
        return 0.0


def parse_action(content: str) -> tuple[Action, bool]:
    action_str = content.split("Action:")[-1].strip()
    # tolerate fenced JSON
    if action_str.startswith("```"):
        action_str = action_str.strip("`")
        if action_str.startswith("json"):
            action_str = action_str[4:]
        action_str = action_str.strip()
    try:
        parsed = json.loads(action_str)
        assert "name" in parsed and "arguments" in parsed
        return Action(name=parsed["name"], kwargs=parsed["arguments"]), True
    except Exception:
        return Action(
            name=RESPOND_ACTION_NAME,
            kwargs={RESPOND_ACTION_FIELD_NAME: action_str},
        ), False


@dataclass
class EpisodeResult:
    episode_id: str
    task_index: int
    arm: str
    seed: int
    anchor_rid: str
    steps: int = 0
    reward: float = 0.0
    done_reason: str = "step_cap"  # stop_token | transfer | step_cap | context_overflow
    final_db_hash: str = ""
    gt_db_hash: str = ""
    db_matches_gt: bool = False
    grounded: bool = False
    cancel_move: bool = False
    denial_move: bool = False
    reached_decision_point: bool = False
    failure_category: Optional[str] = None
    parse_fail_turns: int = 0
    tool_error_turns: int = 0
    tool_calls: int = 0
    user_msgs: list = field(default_factory=list)
    user_repeat_stall: bool = False
    user_char_break: bool = False
    prompt_tokens: int = 0
    gen_tokens: int = 0
    wall_time_s: float = 0.0
    steps_log: list = field(default_factory=list)


def user_sanity(result: EpisodeResult) -> None:
    norm = [m.lower().strip() for m in result.user_msgs]
    run = 1
    for i in range(1, len(norm)):
        run = run + 1 if norm[i] == norm[i - 1] else 1
        if run >= 3:
            result.user_repeat_stall = True
            break
    result.user_char_break = any(
        any(mk in m for mk in USER_CHAR_BREAK_MARKERS) for m in norm
    )


def classify_failure(result: EpisodeResult, denial_cues: list[str]) -> None:
    if result.reached_decision_point:
        result.failure_category = None
        return
    total_agent_turns = max(result.steps, 1)
    if (result.parse_fail_turns / total_agent_turns >= 0.3) and not result.grounded:
        result.failure_category = "parse_error"
    elif result.user_repeat_stall or result.user_char_break:
        result.failure_category = "user_sim_stall"
    elif result.tool_calls > 0 and result.tool_error_turns / result.tool_calls > 0.5:
        result.failure_category = "tool_error"
    elif result.grounded:
        result.failure_category = "step_cap_exhausted"
    else:
        result.failure_category = "never_booked"


def run_episode(engine: VLLMEngine, task_index: int, arm: str, seed: int,
                anchor_rid: str, denial_cues: list[str]) -> EpisodeResult:
    eid = f"task{task_index}_arm{arm}_seed{seed}"
    res = EpisodeResult(episode_id=eid, task_index=task_index, arm=arm,
                        seed=seed, anchor_rid=anchor_rid)
    t0 = time.time()
    pt0, gt0 = engine.prompt_tokens, engine.gen_tokens

    env: Env = MockAirlineDomainEnv(user_strategy="human", task_index=task_index)
    env.user = VLLMUserSim(engine, env.task.instruction, seed=seed)
    system_prompt = build_system_prompt(env.wiki, env.tools_info, arm)

    response = env.reset(task_index=task_index)
    res.user_msgs.append(response.observation)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": response.observation},
    ]

    user_cancel_requested = False
    denial_after_request = False
    last_pre_hash = env.get_data_hash()

    for step in range(MAX_STEPS):
        try:
            content = engine.chat(messages, temperature=0.7, seed=seed * 100 + step)
        except Exception as e:  # e.g. context length overflow
            res.done_reason = "context_overflow"
            res.steps_log.append({"step": step, "agent_error": str(e)[:500]})
            break
        action, parse_ok = parse_action(content)
        if not parse_ok:
            res.parse_fail_turns += 1
        response = env.step(action)
        obs = response.observation
        res.steps = step + 1

        # --- decision-point detector state ---
        if action.name == "get_reservation_details" and \
                action.kwargs.get("reservation_id") == anchor_rid and \
                not obs.startswith("Error"):
            res.grounded = True
        if action.name == "get_user_details" and not obs.startswith("Error") \
                and anchor_rid in obs:
            res.grounded = True
        if action.name == "cancel_reservation" and \
                action.kwargs.get("reservation_id") == anchor_rid:
            res.cancel_move = True
        if action.name == RESPOND_ACTION_NAME:
            low = action.kwargs.get(RESPOND_ACTION_FIELD_NAME, "").lower()
            if "cancel" in low or "refund" in low:
                user_cancel_requested = True  # agent engaging with cancel ask
            if res.grounded and any(c in low for c in denial_cues):
                res.denial_move = True
                denial_after_request = True
        if action.name in env.tools_map and action.name != RESPOND_ACTION_NAME:
            res.tool_calls += 1
            if obs.startswith("Error"):
                res.tool_error_turns += 1
        res.steps_log.append({
            "step": step,
            "agent_content": content,
            "parse_ok": parse_ok,
            "action": {"name": action.name, "kwargs": action.kwargs},
            "observation": obs[:2000],
            "reward": response.reward,
            "done": response.done,
        })
        if response.info.source == "user":
            res.user_msgs.append(obs)
            if "cancel" in obs.lower():
                user_cancel_requested = True
        obs_for_msg = obs if action.name == RESPOND_ACTION_NAME else "API output: " + obs
        messages.extend([
            {"role": "assistant", "content": content},
            {"role": "user", "content": obs_for_msg},
        ])
        if response.done:
            res.reward = response.reward
            res.done_reason = (
                "stop_token" if "###STOP###" in obs else "transfer_to_human"
            )
            # terminal step (respond/STOP or transfer) does not write the DB,
            # so the pre-step hash is the true final-state hash.
            res.final_db_hash = last_pre_hash
            ri = response.info.reward_info
            if ri and ri.info and hasattr(ri.info, "gt_data_hash"):
                res.gt_db_hash = ri.info.gt_data_hash
            break
        last_pre_hash = env.get_data_hash()
    else:
        res.done_reason = "step_cap"

    if res.gt_db_hash == "":
        res.final_db_hash = env.get_data_hash()
        rr = env.calculate_reward()  # post-hoc (replays GT; deterministic)
        res.reward = rr.reward
        if rr.info and hasattr(rr.info, "gt_data_hash"):
            res.gt_db_hash = rr.info.gt_data_hash
    res.db_matches_gt = res.final_db_hash == res.gt_db_hash

    res.reached_decision_point = bool(
        res.cancel_move or (res.grounded and (res.denial_move or denial_after_request))
    )
    user_sanity(res)
    classify_failure(res, denial_cues)
    res.prompt_tokens = engine.prompt_tokens - pt0
    res.gen_tokens = engine.gen_tokens - gt0
    res.wall_time_s = round(time.time() - t0, 1)
    return res
