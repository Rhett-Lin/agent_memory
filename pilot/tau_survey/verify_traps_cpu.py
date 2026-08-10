"""CPU-only trap-validity probe for tau-bench (v1, commit 59a200c).

Reproduces the EXACT reward mechanism of tau_bench/envs/base.py:
    reward = 1 iff sha256(str(to_hashable(final_db))) == sha256(str(to_hashable(gt_db)))
where gt_db = fresh data with the task's ground-truth actions replayed.

For each candidate X-active task (denied/denial-edge), we:
  1. compute gt_data_hash by replaying task.actions on fresh data
     (identical logic to Env.calculate_reward),
  2. simulate the "agent obeyed a WRONG policy variant" move (e.g. cancel an
     out-of-window reservation) and re-hash,
  3. assert hash differs  =>  the env verifier necessarily scores 0
     =>  trap is env-detectable with ZERO model involvement.

No GPU, no LLM, no litellm. Tool modules are loaded by file path to dodge
tau_bench/__init__.py's litellm import.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT / "vendor" / "tau-bench" / "tau_bench"


# --- verbatim copies from tau_bench/envs/base.py (lines 27-41) ---------------
def to_hashable(item):
    if isinstance(item, dict):
        return tuple((key, to_hashable(value)) for key, value in sorted(item.items()))
    elif isinstance(item, list):
        return tuple(to_hashable(element) for element in item)
    elif isinstance(item, set):
        return tuple(sorted(to_hashable(element) for element in item))
    else:
        return item


def consistent_hash(value):
    return sha256(str(value).encode("utf-8")).hexdigest()


# ------------------------------------------------------------------------------


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def load_env_parts():
    """Stub the tau_bench package so `from tau_bench.envs.tool import Tool` works
    without executing tau_bench/__init__.py (which pulls litellm)."""
    for pkg, p in [
        ("tau_bench", REPO),
        ("tau_bench.envs", REPO / "envs"),
        ("tau_bench.envs.airline", REPO / "envs" / "airline"),
        ("tau_bench.envs.airline.tools", REPO / "envs" / "airline" / "tools"),
        ("tau_bench.envs.airline.data", REPO / "envs" / "airline" / "data"),
    ]:
        if pkg not in sys.modules:
            m = types.ModuleType(pkg)
            m.__path__ = [str(p)]
            sys.modules[pkg] = m
    _load("tau_bench.envs.tool", REPO / "envs" / "tool.py")
    data = _load("tau_bench.envs.airline.data_", REPO / "envs" / "airline" / "data" / "__init__.py")
    tools = {}
    for name in ["cancel_reservation", "update_reservation_baggages", "book_reservation"]:
        tools[name] = _load(
            f"tau_bench.envs.airline.tools.{name}",
            REPO / "envs" / "airline" / "tools" / f"{name}.py",
        )
    return data.load_data, tools


def tool_class(mod):
    return next(v for v in vars(mod).values() if isinstance(v, type) and v.__module__ == mod.__name__)


def replay(load_data, tools, actions):
    d = load_data()
    for name, kwargs in actions:
        tool_class(tools[name]).invoke(data=d, **kwargs)
    return d


def h(d):
    return consistent_hash(to_hashable(d))


def main():
    import ast

    load_data, tools = load_env_parts()
    toolclasses = {n: tool_class(m) for n, m in tools.items()}

    # --- parse airline test tasks without importing tau_bench -----------------
    tree = ast.parse((REPO / "envs" / "airline" / "tasks_test.py").read_text())
    tasks = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "TASKS":
            for elt in node.value.elts:
                t = {"instr": None, "actions": []}
                for kw in elt.keywords:
                    if kw.arg == "instruction":
                        t["instr"] = ast.literal_eval(kw.value)
                    elif kw.arg == "actions":
                        for a in kw.value.elts:
                            name = None
                            kw2 = {}
                            for k2 in a.keywords:
                                if k2.arg == "name":
                                    name = ast.literal_eval(k2.value)
                                elif k2.arg == "kwargs":
                                    kw2 = ast.literal_eval(k2.value)
                            t["actions"].append((name, kw2))
                tasks.append(t)

    data0 = load_data()
    R = data0["reservations"]
    U = data0["users"]

    print("== trap-validity probe: wrong-policy move vs GT state (task 18/49: cancel denial) ==")
    # Task 49 (Emma Kim, MDCLVA): GT actions = []  =>  GT DB == fresh DB
    for task_id, rid in [(49, "MDCLVA"), (18, "SI5UKW")]:
        t = tasks[task_id]
        gt = replay(load_data, tools, [a for a in t["actions"] if a[0] in tools])
        wrong = replay(load_data, tools, [("cancel_reservation", {"reservation_id": rid})])
        det = {
            "cabin": R[rid]["cabin"],
            "insurance": R[rid]["insurance"],
            "created_at": R[rid]["created_at"],
            "status_now": R[rid]["status"] if "status" in R[rid] else "?",
        }
        print(f"task {task_id}: res={rid} {det}")
        print(f"  GT-hash == fresh-hash : {h(gt) == h(load_data())}")
        print(f"  wrong-move changes DB : {h(wrong) != h(gt)}  => verifier must reward 0 for the trap move")

    print("\n== positive control: task 8 GT replay must reproduce its own GT hash ==")
    t8 = tasks[8]
    writes = [a for a in t8["actions"] if a[0] in tools]
    gt8 = replay(load_data, tools, writes)
    # wrong variant: same booking flow but cancel AFTER 24h rule would move payment_history
    print(f"  GT replay deterministic : {h(gt8) == h(replay(load_data, tools, writes))}")

    print("\n== variant-table inventory ==")
    print("within-24h cancel-legal tasks: 8,9 (created_at within 24h of 2024-05-15 15:00 EST)")
    for i in (8, 9):
        rid = next(kw["reservation_id"] for n, kw in tasks[i]["actions"] if n == "cancel_reservation")
        r = R[rid]
        print(f"  task {i}: {rid} created_at={r['created_at']} cabin={r['cabin']} ins={r['insurance']}")


if __name__ == "__main__":
    main()
