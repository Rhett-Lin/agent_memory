#!/usr/bin/env python
"""External validation: ALFWorld effect-ordering check for CausalMemAgent.

Bounded validation of the RelationalOps pilot's key effect ordering in a
non-synthetic environment (tech report section 6.4, ALFWorld):

    pilot A11 (P=1,S=1 replay)   -> R: transcript card, same-family sibling,
                                    high entity overlap, verified successful
    pilot A10 (P=1,S=0 struct)   -> S: procedure card, same program, different
                                    entities + different wording template
    pilot A01 (P=0,S=1 near-miss)-> X: transcript card of a SUCCESSFUL episode
                                    of a wrong program (critical step missing),
                                    surface-similar entities
    pilot N                      -> N: no memory injected

Grid: 3 families x 4 siblings x 4 cells x 3 seeds = 144 rollouts,
max 30 steps/episode, success = env `won` (deterministic game metric).

Single command:
    ALFWORLD_DATA=/work1/zixuan/data/agent_memory/alfworld \
    HF_HOME=/work1/zixuan/cache/huggingface \
    python pilot/external/run_alfworld_check.py --stage all

Stages: prepare (select games + verify gold trajectories) -> cards (freeze
memory cards) -> run (vLLM rollouts) -> analyze (EXT_RESULTS.json + report).

All raw outputs are written under /work1/zixuan/outputs/agent_memory/external/
and the two deliverables are also copied to pilot/external/.
"""

import argparse
import difflib
import glob
import hashlib
import json
import math
import os
import re
import shutil
import sys
import time
from collections import defaultdict

DATA_ROOT = os.environ.get("ALFWORLD_DATA", "/work1/zixuan/data/agent_memory/alfworld")
TRAIN = os.path.join(DATA_ROOT, "json_2.1.1", "train")
OUT_ROOT = "/work1/zixuan/outputs/agent_memory/external"
DELIVER_DIR = os.path.dirname(os.path.abspath(__file__))

MODEL = "Qwen/Qwen2.5-7B-Instruct"
FAMILIES = {
    "clean":   {"task_type": "pick_clean_then_place_in_recep", "critical": "clean"},
    "heat":    {"task_type": "pick_heat_then_place_in_recep",  "critical": "heat"},
    "picktwo": {"task_type": "pick_two_obj_and_place",         "critical": "second pick"},
}
SIMPLE = "pick_and_place_simple"
CELLS = ["N", "R", "S", "X"]
SEEDS = [0, 1, 2]
N_SIBLINGS = 4
MAX_STEPS = 30
GOLD_STEP_CAP = 27          # target games whose expert needs >27 steps leave no margin for the agent
WAVE = 16                   # concurrent textworld envs per wave
OBS_TRUNC = 500             # chars per observation kept in the prompt history
HISTORY_TOKEN_BUDGET = 3200

FILLER = [
    "Careful planning before acting prevents wasted steps.",
    "Keep track of which receptacle you are currently facing.",
    "After picking up an object, verify the inventory state before moving on.",
    "Closed receptacles often need to be opened before objects can go inside.",
    "Avoid revisiting locations that were already searched unless necessary.",
    "Match the action verb to the manipulation the goal asks for.",
    "If an action fails, re-read the observation and adjust the next step.",
    "Stay focused on the final placement that the task requires.",
    "A tidy plan is better than a long one; take the direct route.",
    "Check that you are holding the right object before manipulating it.",
    "The destination receptacle must be reached before the object is placed.",
    "Do not drop the object anywhere except the required destination.",
]

# ---------------------------------------------------------------------------
# game catalogue / textworld env management
# ---------------------------------------------------------------------------

def load_env(game_file, max_steps=MAX_STEPS):
    """Independent single-game textworld env (alfworld wrapper stack).

    NOTE: textworld.gym batch envs created from one registration are NOT
    independent when stepped concurrently (observed spurious early `done`),
    so each episode gets its own textworld.start env. `max_steps` is then
    NOT enforced by the engine -- callers enforce it themselves.
    """
    import textworld
    from alfworld.agents.environment.alfred_tw_env import (
        AlfredDemangler, AlfredInfos, AlfredExpert, AlfredExpertType)
    infos = textworld.EnvInfos(won=True, admissible_commands=True,
                               extras=["gamefile", "expert_plan"])
    wrappers = [AlfredDemangler(shuffle=False), AlfredInfos,
                AlfredExpert(AlfredExpertType.HANDCODED)]
    return textworld.start(game_file, infos, wrappers=wrappers)


def parse_dirname(name):
    """pick_clean_then_place_in_recep-Plate-None-Cabinet-4 -> (obj, recep)."""
    parts = name.split("-")
    return parts[1], parts[3] if len(parts) > 3 else ""


def discover():
    """{task_type: [ {name, obj, recep, trials:[game_file,...]} ]}"""
    cat = defaultdict(list)
    wanted = set(v["task_type"] for v in FAMILIES.values()) | {SIMPLE}
    for tdir in sorted(os.listdir(TRAIN)):
        ttype = tdir.split("-")[0]
        if ttype not in wanted:
            continue
        if "movable" in tdir or "Sliced" in tdir:
            continue
        trials = sorted(glob.glob(os.path.join(TRAIN, tdir, "trial_*", "game.tw-pddl")))
        if not trials:
            continue
        obj, recep = parse_dirname(tdir)
        cat[ttype].append({"name": tdir, "obj": obj, "recep": recep, "trials": trials})
    return cat


def run_gold(game_file, max_steps=45):
    """Run the hand-coded expert; return trajectory or None if not clearly won."""
    won, n_steps, actions, fbs, goal = False, 0, [], [], ""
    try:
        env = load_env(game_file, max_steps=max_steps)
        state = env.reset()
        obs0 = state.feedback
        for line in obs0.split("\n"):
            if "task is to" in line.lower():
                goal = line.split(":", 1)[-1].strip()
        done = False
        while n_steps < max_steps and not done:
            cmd = state["extra.expert_plan"][0]
            state, score, done = env.step(cmd)
            actions.append(cmd)
            fbs.append(state.feedback)
            n_steps += 1
            won = bool(state["won"])
        env.close()
    except Exception:
        return None
    if not won or not goal:
        return None
    return {"won": True, "n_steps": n_steps, "actions": actions,
            "feedback": fbs, "obs0": obs0, "goal": goal}


# ---------------------------------------------------------------------------
# stage: prepare -- choose 4 siblings per family + resolve R/S/X sources
# ---------------------------------------------------------------------------


def prepare():
    os.makedirs(OUT_ROOT, exist_ok=True)
    cat = discover()
    manifest = {"families": {}, "notes": {
        "split": "train",
        "selection": "first 4 task dirs with distinct object names whose target "
                     "trial is expert-winnable within <=%d steps" % GOLD_STEP_CAP,
    }}
    cache = {}

    def gold(gf):
        if gf not in cache:
            cache[gf] = run_gold(gf)
        return cache[gf]

    for fam, spec in FAMILIES.items():
        ttype = spec["task_type"]
        dirs = cat[ttype]
        tdir_by_name = {d["name"]: d for d in dirs}
        simple_by_obj = defaultdict(list)
        for d in cat[SIMPLE]:
            simple_by_obj[d["obj"].lower()].append(d)
        fam_dirs_by_obj = defaultdict(list)
        for d in dirs:
            fam_dirs_by_obj[d["obj"].lower()].append(d)

        def first_winnable(d, skip=(), step_cap=45):
            for gf in d["trials"]:
                if gf in skip:
                    continue
                g = gold(gf)
                if g and g["n_steps"] <= step_cap:
                    return {"dir": d["name"], "game": gf, "gold": g}
            return None

        targets, used_objs = [], set()
        for phase in (0, 1):
            for d in dirs:
                if len(targets) >= N_SIBLINGS:
                    break
                if d["name"] in [t["target"]["dir"] for t in targets]:
                    continue
                if phase == 0 and d["obj"].lower() in used_objs:
                    continue
                t = first_winnable(d, step_cap=GOLD_STEP_CAP)
                if not t:
                    continue
                t.update({"obj": d["obj"], "recep": d["recep"]})
                # R source: same program + high entity overlap.
                #   (a) another same-family dir with the SAME object (sibling
                #       instance, shared object entity); else
                #   (b) another winnable trial of the same dir (same obj+recep,
                #       different room layout).
                r_src, r_kind = None, None
                for od in fam_dirs_by_obj[t["obj"].lower()]:
                    if od["name"] == t["dir"]:
                        continue
                    r = first_winnable(od)
                    if r:
                        r_src, r_kind = r, "same_obj_diff_dir"
                        break
                if not r_src:
                    r = first_winnable(tdir_by_name[t["dir"]], skip=(t["game"],))
                    if r:
                        r_src, r_kind = r, "same_dir_diff_trial"
                if not r_src:
                    continue
                # X source: successful pick_and_place_simple episode with the
                # same object (critical step absent); prefer the same recep
                # class for maximal surface overlap.
                x_src, x_kind = None, None
                sdirs = sorted(simple_by_obj[t["obj"].lower()],
                               key=lambda x: x["recep"].lower() != t["recep"].lower())
                for sd in sdirs:
                    x = first_winnable(sd)
                    if x:
                        x_src, x_kind = x, "simple_missing_%s" % spec["critical"]
                        break
                if not x_src:
                    continue
                targets.append({"target": t, "r_src": r_src, "r_kind": r_kind,
                                "x_src": x_src, "x_kind": x_kind})
                used_objs.add(d["obj"].lower())
        if len(targets) < N_SIBLINGS:
            raise RuntimeError("family %s: only %d usable siblings" % (fam, len(targets)))

        # S source: R-source episode of the NEXT sibling (same program,
        # different entities) once all siblings are known.
        sibs = targets
        for i in range(N_SIBLINGS):
            sibs[i]["s_src"] = {
                "dir": sibs[(i + 1) % N_SIBLINGS]["r_src"]["dir"],
                "game": sibs[(i + 1) % N_SIBLINGS]["r_src"]["game"],
                "gold": sibs[(i + 1) % N_SIBLINGS]["r_src"]["gold"],
            }
        manifest["families"][fam] = {"task_type": ttype, "siblings": sibs}
        print("family %s: %d siblings resolved" % (fam, len(sibs)))
        for i, s in enumerate(sibs):
            print("  s%d target=%s R<-%s(%s) X<-%s(%s) S<-%s" % (
                i, s["target"]["dir"], s["r_src"]["dir"], s["r_kind"],
                s["x_src"]["dir"], s["x_kind"], s["s_src"]["dir"]))

    path = os.path.join(OUT_ROOT, "manifest_games.json")
    with open(path, "w") as f:
        json.dump(manifest, f, indent=1)
    print("wrote", path)


# ---------------------------------------------------------------------------
# stage: cards -- freeze 200-300 token memory cards from gold trajectories
# ---------------------------------------------------------------------------


def norm_ent(text):
    """Remove trailing object indices: 'desk 1' -> 'desk'."""
    return re.sub(r"\s+\d+\b", "", text)


def proceduralize(actions):
    steps = []
    for a in actions:
        m = re.match(r"(take|pick up|clean|heat|cool|put|move|open|close|use|slice|examine)\b", a)
        if not m:
            continue
        if a.startswith("take "):
            obj = re.sub(r"\s+from\s+.*$", "", a[5:])
            steps.append("Locate and pick up the %s." % norm_ent(obj))
        elif a.startswith("clean "):
            mm = re.match(r"clean (.*?) with (.*)$", a)
            steps.append("Clean the %s using the %s." % (norm_ent(mm.group(1)), norm_ent(mm.group(2))))
        elif a.startswith("heat "):
            mm = re.match(r"heat (.*?) with (.*)$", a)
            steps.append("Heat the %s using the %s." % (norm_ent(mm.group(1)), norm_ent(mm.group(2))))
        elif a.startswith("cool "):
            mm = re.match(r"cool (.*?) with (.*)$", a)
            steps.append("Cool the %s in the %s." % (norm_ent(mm.group(1)), norm_ent(mm.group(2))))
        elif a.startswith(("put ", "move ")):
            mm = re.match(r"(?:put|move) (.*?) (?:in|on|to) (.*)$", a)
            steps.append("Place the %s in/on the %s." % (norm_ent(mm.group(1)), norm_ent(mm.group(2))))
        elif a.startswith("open "):
            steps.append("Open the %s if it is closed." % norm_ent(a[5:]))
        elif a.startswith("close "):
            steps.append("Close the %s." % norm_ent(a[6:]))
        elif a.startswith("use "):
            steps.append("Switch on the %s." % norm_ent(a[4:]))
    return steps


def _fit(card_fn, tok, lo=200, hi=300):
    """Render a card, then adjust filler so the token count sits in [lo, hi].

    card_fn takes (filler_lines, level); higher levels compress content if the
    base text is already longer than `hi`.
    """
    last_err = None
    for level in range(3):
        base_len = None
        for n_fill in range(0, len(FILLER) + 1):
            text = card_fn(FILLER[:n_fill], level)
            n = len(tok.encode(text))
            if base_len is None:
                base_len = n
            if n >= lo and n <= hi:
                return text, n
        last_err = RuntimeError(
            "level %d: base %d tokens, padded max %d" % (level, base_len, n))
        if base_len <= hi:
            break  # padding could not reach `lo`: no point trying next level
    raise last_err


def transcript_card(gold, goal):
    """R/X cell: episode-transcript style card from a verified successful run."""
    actions = gold["actions"]
    salient = [fb.split("\n")[-1] for fb in gold["feedback"]
               if re.search(r"pick up|clean|heat|cool|put|move|open", fb.split("\n")[-1], re.I)]
    def build(filler, level):
        acts = actions if level < 2 else [a for a in actions
                                          if not a.startswith(("go to", "look"))]
        lines = ["Episode transcript (a successfully completed household task).",
                 "Task goal of that episode: \"%s\"." % goal,
                 "Actions taken, in order:"]
        lines += ["%2d. %s" % (i + 1, a) for i, a in enumerate(acts)]
        if level == 0 and len(actions) <= 16 and salient:
            lines.append("Key outcomes: " + " ".join(salient[:6]))
        if level == 2:
            lines.append("(Locomotion steps omitted; manipulation order shown as executed.)")
        lines.append("Result: SUCCESS. The task was fully completed this way.")
        lines.append("Treat this as a reference for how a similar task was solved.")
        lines += filler
        return "\n".join(lines)
    return build


def procedure_card(gold, goal):
    """S cell: procedure-style card; same program rendered abstractly."""
    steps = proceduralize(gold["actions"])
    def build(filler, level):
        lines = ["Standard operating procedure (verified successful on a similar household task).",
                 "Task pattern: \"%s\"." % goal,
                 "Procedure:"]
        lines += ["%2d) %s" % (i + 1, s) for i, s in enumerate(steps)]
        lines.append("This sequence achieved the goal every time it was followed;")
        lines.append("adapt object and receptacle names to the task in front of you.")
        lines += filler
        return "\n".join(lines)
    return build


def build_cards():
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(MODEL)
    with open(os.path.join(OUT_ROOT, "manifest_games.json")) as f:
        manifest = json.load(f)

    cards = {}
    audit = []
    for fam, fdata in manifest["families"].items():
        for i, sib in enumerate(fdata["siblings"]):
            key = "%s/s%d" % (fam, i)
            tgt = sib["target"]
            entry = {"family": fam, "sibling": i, "target_dir": tgt["dir"],
                     "target_obj": tgt["obj"], "target_recep": tgt["recep"],
                     "goal": tgt["gold"]["goal"], "tokens": {}}
            r_card, r_tok = _fit(transcript_card(sib["r_src"]["gold"], sib["r_src"]["gold"]["goal"]), tok)
            entry["R"] = r_card
            entry["tokens"]["R"] = r_tok
            entry["r_source"] = "%s (%s)" % (sib["r_src"]["dir"], sib["r_kind"])
            s_card, s_tok = _fit(procedure_card(sib["s_src"]["gold"], sib["s_src"]["gold"]["goal"]), tok)
            entry["S"] = s_card
            entry["tokens"]["S"] = s_tok
            entry["s_source"] = sib["s_src"]["dir"]
            x_card, x_tok = _fit(transcript_card(sib["x_src"]["gold"], sib["x_src"]["gold"]["goal"]), tok)
            entry["X"] = x_card
            entry["tokens"]["X"] = x_tok
            entry["x_source"] = "%s (%s)" % (sib["x_src"]["dir"], sib["x_kind"])
            cards[key] = entry
            audit.append({"key": key, **entry["tokens"],
                          "r_source": entry["r_source"], "s_source": entry["s_source"],
                          "x_source": entry["x_source"]})
    with open(os.path.join(OUT_ROOT, "cards.json"), "w") as f:
        json.dump(cards, f, indent=1)
    print("wrote %d card sets" % len(cards))
    for a in audit:
        print("  %-14s R=%3d S=%3d X=%3d | R<-%s | X<-%s" % (
            a["key"], a["R"], a["S"], a["X"], a["r_source"], a["x_source"]))
    bad = [k for k, e in cards.items() for c in ("R", "S", "X")
           if not (200 <= e["tokens"][c] <= 300)]
    if bad:
        raise RuntimeError("cards outside 200-300 tokens: %s" % bad)


# ---------------------------------------------------------------------------
# stage: run -- vLLM agent rollouts
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are an agent playing a text-based household simulator (ALFWorld). "
    "Each turn you receive the current observation and a list of admissible commands. "
    "Reply with EXACTLY ONE command, copied verbatim from the admissible list. "
    "Do not explain, do not add any other text."
)

MEM_BLOCK = "[Recalled memory from an earlier experience. It may or may not be helpful.]\n%s\n[End of memory]\n\n"


def trunc_obs(obs, n=OBS_TRUNC):
    obs = obs.strip()
    return obs if len(obs) <= n else obs[:n] + " ..."


def normalize_cmd(text):
    text = text.strip().strip("`").strip("*").strip()
    text = re.sub(r"^>\s*", "", text)
    text = re.sub(r"^(command|action|your command)\s*[:\-]\s*", "", text, flags=re.I)
    text = re.sub(r"^\d+[\.\)]\s*", "", text)
    return text.strip().rstrip(".").lower()


def parse_command(raw, admissible):
    for line in reversed([l for l in raw.split("\n") if l.strip()]):
        cand = normalize_cmd(line)
        if not cand:
            continue
        adm_norm = {normalize_cmd(a): a for a in admissible}
        if cand in adm_norm:
            return adm_norm[cand], "exact"
        close = difflib.get_close_matches(cand, list(adm_norm), n=1, cutoff=0.65)
        if close:
            return adm_norm[close[0]], "fuzzy"
    return ("look" if any(normalize_cmd(a) == "look" for a in admissible)
            else admissible[0]), "fallback"


def build_prompt(tok, goal, card, history, obs, admissible):
    mem = MEM_BLOCK % card if card else ""
    lines = [mem + "Task: %s" % goal, ""]
    lines.append("History:")
    for o, a in history:
        if o:
            lines.append("Obs: %s" % trunc_obs(o))
        if a:
            lines.append("> %s" % a)
    lines.append("Current observation:\n%s" % trunc_obs(obs))
    lines.append("")
    lines.append("Admissible commands:")
    lines += admissible
    lines.append("")
    lines.append("Reply with only the command text, nothing else.")
    user = "\n".join(lines)
    # shrink history from the middle if the prompt exceeds the budget
    while len(tok.encode(SYSTEM_PROMPT + user)) > HISTORY_TOKEN_BUDGET and len(history) > 8:
        history = history[:2] + history[4:]
        return build_prompt(tok, goal, card, history, obs, admissible)
    return tok.apply_chat_template(
        [{"role": "system", "content": SYSTEM_PROMPT},
         {"role": "user", "content": user}],
        tokenize=False, add_generation_prompt=True)


def extract_goal(obs0):
    for line in obs0.split("\n"):
        if "task is to" in line.lower():
            return line.split(":", 1)[-1].strip()
    return ""


class Episode:
    def __init__(self, fam, sib, cell, seed, game_file, card):
        self.meta = {"family": fam, "sibling": sib, "cell": cell, "seed": seed}
        self.game_file = game_file
        self.card = card
        self.env = None
        self.history = []      # list of (obs, action) rounds
        self.obs = None
        self.admissible = []
        self.done = False
        self.won = False
        self.n_steps = 0
        self.parses = defaultdict(int)
        self.commands = []
        self.goal = ""

    def start(self):
        self.env = load_env(self.game_file, MAX_STEPS)
        state = self.env.reset()
        self.obs = state.feedback
        self.admissible = list(state["admissible_commands"])
        self.goal = extract_goal(self.obs)
        return self

    def step(self, cmd):
        state, score, done = self.env.step(cmd)
        self.history.append((self.obs, cmd))
        self.commands.append(cmd)
        self.obs = state.feedback
        self.admissible = list(state["admissible_commands"])
        self.done = bool(done) or self.n_steps + 1 >= MAX_STEPS
        self.won = bool(state["won"])
        self.n_steps += 1

    def close(self):
        if self.env is not None:
            try:
                self.env.close()
            except Exception:
                pass


def grid_key(fam, sib, cell, seed):
    return "%s/s%d/%s/%d" % (fam, sib, cell, seed)


def run_grid(args):
    import torch  # noqa: F401  (ensure vllm imports after torch env is set)
    from vllm import LLM, SamplingParams
    from transformers import AutoTokenizer

    os.makedirs(OUT_ROOT, exist_ok=True)
    with open(os.path.join(OUT_ROOT, "manifest_games.json")) as f:
        manifest = json.load(f)
    with open(os.path.join(OUT_ROOT, "cards.json")) as f:
        cards = json.load(f)
    rollouts_path = os.path.join(OUT_ROOT, "rollouts.jsonl")

    done_keys = set()
    if os.path.exists(rollouts_path):
        with open(rollouts_path) as f:
            for line in f:
                try:
                    r = json.loads(line)
                    done_keys.add(grid_key(r["family"], r["sibling"], r["cell"], r["seed"]))
                except Exception:
                    pass

    todo = []
    fams = [args.smoke_family] if args.smoke else list(FAMILIES)
    sib_range = range(1) if args.smoke else range(N_SIBLINGS)
    seed_list = [0] if args.smoke else SEEDS
    for fam in fams:
        for sib in sib_range:
            tgt = manifest["families"][fam]["siblings"][sib]["target"]["game"]
            for cell in CELLS:
                card = cards["%s/s%d" % (fam, sib)].get(cell)
                for seed in seed_list:
                    if grid_key(fam, sib, cell, seed) not in done_keys:
                        todo.append(Episode(fam, sib, cell, seed, tgt, card))
    print("%d rollouts to run" % len(todo))
    if not todo:
        return

    llm = LLM(model=MODEL, dtype="float16", gpu_memory_utilization=0.85,
              max_model_len=4096, seed=0)
    tok = AutoTokenizer.from_pretrained(MODEL)
    t0 = time.time()
    n_done = 0

    for w0 in range(0, len(todo), WAVE):
        wave = [ep.start() for ep in todo[w0:w0 + WAVE]]
        for step_i in range(MAX_STEPS):
            active = [ep for ep in wave if not ep.done]
            if not active:
                break
            by_decode_seed = defaultdict(list)
            for ep in active:
                ds = int(hashlib.md5(("%s|%d" % (ep.game_file, ep.meta["seed"])).encode()).hexdigest(), 16) % (2 ** 31)
                by_decode_seed[ds].append(ep)
            for ds, eps in by_decode_seed.items():
                prompts = [build_prompt(tok, ep.goal, ep.card, list(ep.history),
                                        ep.obs, ep.admissible) for ep in eps]
                sp = SamplingParams(temperature=0.7, top_p=0.9, max_tokens=24, seed=ds)
                outs = llm.generate(prompts, sp)
                for ep, out in zip(eps, outs):
                    raw = out.outputs[0].text
                    cmd, how = parse_command(raw, ep.admissible)
                    ep.parses[how] += 1
                    ep.step(cmd)
        with open(rollouts_path, "a") as f:
            for ep in wave:
                ep.close()
                row = dict(ep.meta)
                row.update({
                    "success": int(ep.won), "steps": ep.n_steps,
                    "commands": ep.commands, "parses": dict(ep.parses),
                    "game": ep.game_file, "goal": ep.goal,
                    "card_tokens": (cards["%s/s%d" % (ep.meta["family"], ep.meta["sibling"])]
                                    ["tokens"].get(ep.meta["cell"])),
                    "model": MODEL, "max_steps": MAX_STEPS,
                })
                f.write(json.dumps(row) + "\n")
                n_done += 1
        print("[%5.1f min] %d/%d rollouts done" % ((time.time() - t0) / 60, n_done, len(todo)),
              flush=True)
    print("all rollouts finished in %.1f min" % ((time.time() - t0) / 60))


# ---------------------------------------------------------------------------
# stage: analyze
# ---------------------------------------------------------------------------


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def cell_stats(rows):
    out = {}
    for cell in CELLS:
        rr = [r for r in rows if r["cell"] == cell]
        k = sum(r["success"] for r in rr)
        n = len(rr)
        lo, hi = wilson(k, n)
        out[cell] = {"k": k, "n": n, "rate": k / n if n else 0.0,
                     "ci95": [round(lo, 3), round(hi, 3)],
                     "mean_steps": round(sum(r["steps"] for r in rr) / n, 1) if n else 0}
    return out


def analyze():
    with open(os.path.join(OUT_ROOT, "rollouts.jsonl")) as f:
        rows = [json.loads(l) for l in f]
    with open(os.path.join(OUT_ROOT, "cards.json")) as f:
        cards = json.load(f)

    overall = cell_stats(rows)
    per_family = {}
    flips = {"harmful_X": 0, "helpful_X": 0, "pairs": 0,
             "harmful_S": 0, "helpful_S": 0, "harmful_R": 0, "helpful_R": 0}
    by_key = {}
    for r in rows:
        by_key[(r["family"], r["sibling"], r["seed"], r["cell"])] = r["success"]
    for fam in FAMILIES:
        fam_rows = [r for r in rows if r["family"] == fam]
        per_family[fam] = cell_stats(fam_rows)
    for (fam, sib, seed, cell), succ in by_key.items():
        if cell != "N":
            continue
        base = succ
        for cell2, tag in (("X", "X"), ("S", "S"), ("R", "R")):
            v = by_key.get((fam, sib, seed, cell2))
            if v is None:
                continue
            if cell2 == "X":
                flips["pairs"] += 1
            if base == 1 and v == 0:
                flips["harmful_" + tag] += 1
            if base == 0 and v == 1:
                flips["helpful_" + tag] += 1

    ordering = {
        "R>S": overall["R"]["rate"] > overall["S"]["rate"],
        "S>N": overall["S"]["rate"] > overall["N"]["rate"],
        "N>X": overall["N"]["rate"] > overall["X"]["rate"],
        "R>N": overall["R"]["rate"] > overall["N"]["rate"],
    }
    pilot_directions = {
        "replay>struct (pilot)": "R>S",
        "struct|replay>nothing (pilot)": "S>N",
        "near-miss below nothing (pilot)": "N>X",
    }
    direction_match = {k: ordering[v] for k, v in pilot_directions.items()}

    results = {
        "n_rollouts": len(rows),
        "model": MODEL,
        "grid": "3 families x 4 siblings x 4 cells x 3 seeds",
        "max_steps": MAX_STEPS,
        "overall": overall,
        "per_family": per_family,
        "ordering": ordering,
        "pilot_direction_match": direction_match,
        "flips_vs_N": flips,
        "card_tokens": {k: v["tokens"] for k, v in cards.items()},
        "card_sources": {k: {"R": v["r_source"], "S": v["s_source"], "X": v["x_source"]}
                         for k, v in cards.items()},
    }
    res_path = os.path.join(DELIVER_DIR, "EXT_RESULTS.json")
    with open(res_path, "w") as f:
        json.dump(results, f, indent=1)
    shutil.copy(res_path, os.path.join(OUT_ROOT, "EXT_RESULTS.json"))
    print(json.dumps({c: {"rate": round(overall[c]["rate"], 3), "ci": overall[c]["ci95"]}
                      for c in CELLS}, indent=1))
    print("ordering:", ordering)
    print("wrote", res_path)
    return results


# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="all",
                    choices=["prepare", "cards", "run", "analyze", "all", "goldonly"])
    ap.add_argument("--smoke", action="store_true", help="1 family x 1 sibling x 4 cells x 1 seed")
    ap.add_argument("--smoke-family", default="clean")
    ap.add_argument("--force-prepare", action="store_true",
                    help="re-run expert verification and rebuild the manifest")
    args = ap.parse_args()
    os.makedirs(OUT_ROOT, exist_ok=True)
    stage = args.stage
    manifest_path = os.path.join(OUT_ROOT, "manifest_games.json")
    if stage == "goldonly":
        # verify cached freezed gold materials without re-running experts
        with open(manifest_path) as f:
            m = json.load(f)
        with open(os.path.join(OUT_ROOT, "manifest_gold.json")) as f:
            golds = json.load(f)
        ok, bad = 0, []
        for fam, fd in m["families"].items():
            assert len(fd["siblings"]) == N_SIBLINGS
            for i, s in enumerate(fd["siblings"]):
                t = s["target"]
                g = golds.get(t["game"])
                if g and g["won"] and g["n_steps"] <= GOLD_STEP_CAP:
                    ok += 1
                else:
                    bad.append("%s/s%d" % (fam, i))
                for role in ("r_src", "x_src", "s_src"):
                    g2 = golds.get(s[role]["game"])
                    if not (g2 and g2["won"]):
                        bad.append("%s/s%d/%s" % (fam, i, role))
        print("gold-checked %d target games OK; issues: %s" % (ok, bad or "none"))
        return
    if stage in ("prepare", "all"):
        if os.path.exists(manifest_path) and not args.force_prepare:
            print("manifest exists, skipping prepare (delete %s to rebuild)" % manifest_path)
        else:
            prepare()
    if stage in ("cards", "all"):
        build_cards()
    if stage in ("run", "all"):
        run_grid(args)
    if stage in ("analyze", "all") and not args.smoke:
        analyze()


if __name__ == "__main__":
    main()
