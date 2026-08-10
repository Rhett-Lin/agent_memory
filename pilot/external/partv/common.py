"""Part V shared constants and deterministic primitives (frozen protocol).

ANALYSIS HYGIENE: success-rate inspection is FORBIDDEN before the frozen
analysis point; the harvest ledger records only won/steps for sourcing.

Everything here is byte-deterministic and CPU-only:

  - canonical game points (family/type) drawn deterministically from
    game-file goal text ($3.5 goal parser, no task-dir labels);
  - canonical relpath + sha256 ordering ($3.5.1/.3);
  - the literal MD5 decode-seed rule ($3.5.6);
  - pinned hashes for the builder, prompt package, and model revisions.
"""

import hashlib
import json
import os
import re

# ---------------------------------------------------------------------------
# Frozen pins (PART_V_PREREG_V5_FINAL.md / PART_V_POWER.md)
# ---------------------------------------------------------------------------

PARTV_DIR = os.path.dirname(os.path.abspath(__file__))
EXTERNAL_DIR = os.path.dirname(PARTV_DIR)

BUILDER_PATH = os.path.join(EXTERNAL_DIR, "run_alfworld_check.py")
BUILDER_SHA256 = ("96ef23ea8516fc95c11d34b7c639e7474ada4f1b9dfd0a153c036b"
                  "964f11eec3")
PROMPTS_PATH = os.path.join(EXTERNAL_DIR, "PART_V_PROMPTS.json")
PROMPTS_SHA256 = ("46da398ab41e173155c48fde247a12e14e3b0359cb3ba0eb898370"
                  "694884d739")
MEM_A_SHA256 = ("707adb37ca25ccb2b2955fc3a0bc9805ec8a6b980e32d5c10e29f8bd"
                "7546274b")
MEM_B_SHA256 = ("51b0d8d5fb51dbb4aecaa8a09e5efce85e137494e75b287d6607a380"
                "946124ae")
PROTOCOL_PATH = os.path.join(EXTERNAL_DIR, "PART_V_PREREG_V5_FINAL.md")
POWER_PATH = os.path.join(EXTERNAL_DIR, "PART_V_POWER.md")

MODEL_7B = "Qwen/Qwen2.5-7B-Instruct"
MODEL_7B_REV = "a09a35458c702b33eeacc393d103063234e8bc28"
BGE_MODEL = "BAAI/bge-small-en-v1.5"
BGE_REV = "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"

SEED_RNG_SCREEN = 20260809          # $3.5.2
SEED_RNG_ROLLOUT = 20260810         # $3.5.2
SEED_BOOTSTRAP = 20260809           # $6 null-centered cluster bootstrap

OUT_ROOT = "/work1/zixuan/outputs/agent_memory/external_gate"
LOG_ROOT = "/work1/zixuan/logs/agent_memory/external_gate"
LEDGER_PATH = os.path.join(OUT_ROOT, "harvest_ledger.jsonl")

# Main-grid design (frozen): 60 heat + 60 cool targets, 4 seeds, arms N/R/X.
CONFIRMATORY_PER_TYPE = 60
CALIBRATION_PER_TYPE = 20           # exactly 20 heat + 20 cool ($3.5.4)
HEADROOM_PER_TYPE = 6               # 12 targets per headroom set, half heat
N_SEEDS = 4
GRID_SEEDS = (0, 1, 2, 3)
ARMS = ("N", "R", "X")
MAX_REPLACEMENTS = 40               # $3.4 replacement cap

# ---------------------------------------------------------------------------
# hashing / canonical paths
# ---------------------------------------------------------------------------

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def canonical_relpath(abspath, data_root):
    """$3.5.1: POSIX relpath under $ALFWORLD_DATA, no leading ./, '/' only."""
    rel = os.path.relpath(os.path.abspath(abspath), os.path.abspath(data_root))
    rel = rel.replace(os.sep, "/")
    while rel.startswith("./"):
        rel = rel[2:]
    return rel


# ---------------------------------------------------------------------------
# $3.5.6 literal MD5 decode-seed rule
# ---------------------------------------------------------------------------

def md5_decode_seed(literal):
    """md5(literal.encode('utf-8')).digest()[:4] little-endian, mod 2**31."""
    d = hashlib.md5(literal.encode("utf-8")).digest()
    return int.from_bytes(d[:4], "little") % (2 ** 31)


def harvest_decode_seed(candidate_path, role, attempt_idx):
    """$3.4: seed string is 'candidate_path|role|attempt_idx', idx in 1..4."""
    assert isinstance(attempt_idx, int) and 1 <= attempt_idx <= 4
    return md5_decode_seed("%s|%s|%d" % (candidate_path, role, attempt_idx))


# ---------------------------------------------------------------------------
# goal-text game parser (documented, deterministic, no metadata labels)
# ---------------------------------------------------------------------------
#
# Each ALFWorld game.tw-pddl is a JSON document; its "grammar" field embeds
# the goal sentence shown to the agent ("Your task is to: ...").  Across all
# 459 heat + 533 cool train games, exactly two phrasings occur:
#   A) "<heat|cool> some <obj> and put it <in|on> <recep>"
#   B) "put a <hot|cool> <obj> <in|on> <recep>"
# We parse (prep, obj, recep) solely from this goal text; classes are
# lowercased whitespace-stripped tokens, trailing '.' removed.  The task-dir
# name is NEVER used (it carries "Sliced"/metadata not present in goals).

_GOAL_TASK_RE = re.compile(r'"task": \[\s*\{\s*"rhs": "(.*?)"\s*\}\s*\]', re.S)
_GOAL_A_RE = re.compile(r"(heat|cool) some (.+?) and put it (?:in|on) (.+)")
_GOAL_B_RE = re.compile(r"put a (hot|cool) (.+?) (?:in|on) (.+)")

TASK_TYPES = {"heat": "pick_heat_then_place_in_recep",
              "cool": "pick_cool_then_place_in_recep"}


class GoalParseError(ValueError):
    pass


def parse_goal_sentence(sentence):
    """goal sentence -> (prep, obj, recep); raises GoalParseError."""
    s = sentence.strip().rstrip(".")
    s = re.sub(r"^Your task is to:\s*", "", s)
    m = _GOAL_A_RE.fullmatch(s)
    if m:
        prep, obj, recep = m.group(1), m.group(2), m.group(3)
    else:
        m = _GOAL_B_RE.fullmatch(s)
        if not m:
            raise GoalParseError("unparsable goal sentence: %r" % sentence)
        prep = {"hot": "heat", "cool": "cool"}[m.group(1)]
        obj, recep = m.group(2), m.group(3)
    return prep, obj.lower().strip(), recep.lower().strip()


def parse_game_goal(game_json):
    """Extract the goal sentence from a parsed game.tw-pddl JSON document."""
    gram = game_json["grammar"]
    m = _GOAL_TASK_RE.search(gram)
    if not m:
        raise GoalParseError("no task rhs in grammar")
    # json-escapes inside the grammar blob ('Your task is to: ...')
    return m.group(1).encode().decode("unicode_escape").strip()


def load_game_info(game_file, data_root):
    """-> dict(canonical path, prep, obj, recep, goal, sha256) for one game.

    `goal` is stored in runtime form (the "Your task is to:" prefix stripped,
    exactly what the env observation line yields), so it can be compared
    verbatim against rollout-recorded goals.
    """
    with open(game_file) as f:
        doc = json.load(f)
    raw = parse_game_goal(doc)
    goal = re.sub(r"^Your task is to:\s*", "", raw).strip()
    prep, obj, recep = parse_goal_sentence(goal)
    rel = canonical_relpath(game_file, data_root)
    return {"path": rel, "prep": prep, "obj": obj, "recep": recep,
            "goal": goal, "sha256": sha256_bytes(rel.encode("utf-8"))}


def data_root():
    return os.environ.get("ALFWORLD_DATA",
                          "/work1/zixuan/data/agent_memory/alfworld")


def train_dir(root=None):
    return os.path.join(root or data_root(), "json_2.1.1", "train")


def list_family_games(prep, root=None):
    """All game.tw-pddl of one family ('heat'/'cool') under train/.

    Existence of game.tw-pddl is the only filter; directories without a game
    file (all 'Sliced' object variants) contribute nothing, matching the
    frozen family totals 459/533.
    """
    import glob
    base = train_dir(root)
    out = []
    prefix = TASK_TYPES[prep] + "-"
    for tdir in sorted(os.listdir(base)):
        if not tdir.startswith(prefix):
            continue
        for gf in sorted(glob.glob(os.path.join(base, tdir, "trial_*",
                                                 "game.tw-pddl"))):
            out.append(gf)
    return out


# ---------------------------------------------------------------------------
# pinned-artifact verification
# ---------------------------------------------------------------------------

class FrozenHashMismatch(RuntimeError):
    pass


def verify_builder():
    """STOP-AND-REPORT contract: pinned builder must be byte-identical."""
    got = sha256_file(BUILDER_PATH)
    if got != BUILDER_SHA256:
        raise FrozenHashMismatch(
            "pinned builder hash mismatch: %s != %s -- STOP and report" %
            (got, BUILDER_SHA256))
    return got


def load_prompts(verify=True):
    """Load PART_V_PROMPTS.json; verify file-bytes hash ($0 item 1, App. A)."""
    with open(PROMPTS_PATH, "rb") as f:
        raw = f.read()
    if verify:
        got = hashlib.sha256(raw).hexdigest()
        if got != PROMPTS_SHA256:
            raise FrozenHashMismatch(
                "prompt-package hash mismatch: %s != %s" %
                (got, PROMPTS_SHA256))
    d = json.loads(raw.decode("utf-8"))
    return d


def import_builder_module():
    """Import the pinned builder read-only (never execute its main())."""
    verify_builder()
    import importlib.util
    spec = importlib.util.spec_from_file_location("run_alfworld_check",
                                                  BUILDER_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
