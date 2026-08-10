"""Part V shared rollout engine (frozen runtime, $9).

Wraps the pinned builder's functions (imported read-only, hash-verified):
load_env / extract_goal / build_prompt(with builder framing) /
normalize_cmd+parse_command / trunc_obs.  Frozen decode: temp 0.7, top_p
0.9, max_tokens 24, <=30 steps, fp16, gpu_mem_util 0.85, max_model_len
4096; obs truncation 500 chars; 3200-token history budget with middle
shrink keeping the first 2 rounds -- all inherited from the pinned builder.

ANALYSIS HYGIENE: success-rate inspection is FORBIDDEN; this engine reports
only per-episode won/steps/commands/parses into caller-managed ledgers.

The decoder is injectable (VLLMDecoder for GPU runs, FakeDecoder for CPU
smoke tests) so harvest/grid/headroom driver logic is CPU-testable.
"""

import time

from pilot.external.partv import common

MAX_STEPS = 30                       # $9
WAVE = 16                            # builder's concurrent envs per wave
DECODE = {"temperature": 0.7, "top_p": 0.9, "max_tokens": 24}


class VLLMDecoder:
    """Real backend: one vLLM engine per process (frozen $9 params)."""

    def __init__(self, gpu_id=None):
        import os
        if gpu_id is not None:
            os.environ.setdefault("CUDA_VISIBLE_DEVICES", str(gpu_id))
        import torch  # noqa: F401  (torch first, per builder convention)
        from vllm import LLM
        from transformers import AutoTokenizer
        common.verify_builder()
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        self.llm = LLM(model=common.MODEL_7B, revision=common.MODEL_7B_REV,
                       dtype="float16", gpu_memory_utilization=0.85,
                       max_model_len=4096, seed=0)
        self.tok = AutoTokenizer.from_pretrained(
            common.MODEL_7B, revision=common.MODEL_7B_REV)
        from vllm import SamplingParams
        self._sp_cls = SamplingParams

    def generate(self, prompts, decode_seed):
        sp = self._sp_cls(temperature=DECODE["temperature"],
                          top_p=DECODE["top_p"],
                          max_tokens=DECODE["max_tokens"],
                          seed=decode_seed)
        outs = self.llm.generate(prompts, sp)
        return [o.outputs[0].text for o in outs]


class FakeDecoder:
    """CPU smoke backend: scripted reply stream; records prompts."""

    def __init__(self, reply="look"):
        self.reply = reply
        self.calls = []

    class _Tok:
        def encode(self, text):
            return text.split()

        def apply_chat_template(self, msgs, tokenize=False,
                                add_generation_prompt=True):
            return "\n".join(m["content"] for m in msgs)

    tok = _Tok()

    def generate(self, prompts, decode_seed):
        self.calls.append((len(prompts), decode_seed))
        return [self.reply for _ in prompts]


class Episode:
    """One rollout of one game with an optional memory card ($9)."""

    def __init__(self, meta, game_file, card=None, mem_header=None,
                 decode_seed=0, max_steps=MAX_STEPS):
        self.meta = dict(meta)
        self.game_file = game_file
        self.card = card
        # mem_header None -> pinned builder framing (== mem_A verbatim)
        self.mem_header = mem_header
        self.decode_seed = int(decode_seed)
        self.max_steps = max_steps
        self.env = None
        self.history = []              # list of (obs, action)
        self.obs = ""
        self.admissible = []
        self.goal = ""
        self.commands = []
        self.feedback = []
        self.done = False
        self.won = False
        self.n_steps = 0
        self.parses = {}

    # -- lifecycle -----------------------------------------------------
    def start(self, builder):
        self.env = builder.load_env(self.game_file, self.max_steps)
        state = self.env.reset()
        self.obs = state.feedback
        self.admissible = list(state["admissible_commands"])
        self.goal = builder.extract_goal(self.obs)
        return self

    def step(self, cmd, builder):
        state, _score, done = self.env.step(cmd)
        self.history.append((self.obs, cmd))
        self.commands.append(cmd)
        self.feedback.append(state.feedback)
        self.obs = state.feedback
        self.admissible = list(state["admissible_commands"])
        self.done = bool(done) or self.n_steps + 1 >= self.max_steps
        self.won = bool(state["won"])
        self.n_steps += 1

    def close(self):
        if self.env is not None:
            try:
                self.env.close()
            except Exception:
                pass

    def row(self):
        r = dict(self.meta)
        r.update({"success": int(self.won), "steps": self.n_steps,
                  "commands": self.commands, "parses": dict(self.parses),
                  "game": self.game_file, "goal": self.goal,
                  "decode_seed": self.decode_seed,
                  "model": common.MODEL_7B, "model_rev": common.MODEL_7B_REV,
                  "max_steps": self.max_steps})
        return r

    def gold_like(self):
        """Builder-`transcript_card` compatible dict of a finished episode."""
        return {"won": self.won, "n_steps": self.n_steps,
                "actions": list(self.commands),
                "feedback": list(self.feedback),
                "obs0": self.history[0][0] if self.history else "",
                "goal": self.goal}


def build_prompt(builder, tok, episode, prompts_pkg):
    """Prompt per $9: builder framing (== mem_A) or an explicit mem header."""
    if episode.mem_header is None:
        return builder.build_prompt(tok, episode.goal, episode.card,
                                    list(episode.history), episode.obs,
                                    episode.admissible)
    mem = (episode.mem_header % episode.card) if episode.card else ""
    hist_lines = []
    for o, a in episode.history:
        if o:
            hist_lines.append("Obs: %s" % builder.trunc_obs(o))
        if a:
            hist_lines.append("> %s" % a)
    user = prompts_pkg["user_template"].format(
        mem=mem, goal=episode.goal, history="\n".join(hist_lines),
        obs=builder.trunc_obs(episode.obs),
        admissible="\n".join(episode.admissible))
    while len(tok.encode(prompts_pkg["system"] + user)) > 3200 \
            and len(episode.history) > 8:
        episode.history = episode.history[:2] + episode.history[4:]
        return build_prompt(builder, tok, episode, prompts_pkg)
    return tok.apply_chat_template(
        [{"role": "system", "content": prompts_pkg["system"]},
         {"role": "user", "content": user}],
        tokenize=False, add_generation_prompt=True)


def run_episodes(episodes, decoder, tok, on_wave=None, prompts_pkg=None,
                 wave_size=WAVE, builder=None):
    """Wave runner: returns list of episode.row(); frozen step/decode loop.

    `builder` defaults to the pinned, hash-verified run_alfworld_check
    module; tests may inject a fake one (never in production paths).
    """
    if builder is None:
        builder = common.import_builder_module()
    if prompts_pkg is None:
        prompts_pkg = common.load_prompts()
    done_rows, t0 = [], time.time()
    for w0 in range(0, len(episodes), wave_size):
        wave = episodes[w0:w0 + wave_size]
        for ep in wave:
            ep.start(builder)
        for _step in range(MAX_STEPS):
            active = [ep for ep in wave if not ep.done]
            if not active:
                break
            by_seed = {}
            for ep in active:
                by_seed.setdefault(ep.decode_seed, []).append(ep)
            for ds, eps in sorted(by_seed.items()):
                prompts = [build_prompt(builder, tok, ep, prompts_pkg)
                           for ep in eps]
                raws = decoder.generate(prompts, ds)
                for ep, raw in zip(eps, raws):
                    cmd, how = builder.parse_command(raw, ep.admissible)
                    ep.parses[how] = ep.parses.get(how, 0) + 1
                    ep.step(cmd, builder)
        for ep in wave:
            ep.close()
        rows = [ep.row() for ep in wave]
        if on_wave is not None:
            on_wave(w0 // wave_size, rows)
        done_rows.extend(rows)
        print("[%6.1f min] %d/%d episodes done"
              % ((time.time() - t0) / 60, len(done_rows), len(episodes)),
              flush=True)
    return done_rows
