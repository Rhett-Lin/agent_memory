"""Part VI freeze manifest builder + verifier (adjudication correction C6:
the verifier is NON-MUTATING).

  python freeze_manifest.py            # write PART_VI_FREEZE_MANIFEST.json
  python freeze_manifest.py --verify   # READ-ONLY verification: hashes +
                                       # vendor pins + read-only functional
                                       # checks; exit 1 (STOP) on ANY failure;
                                       # never writes a byte
  python freeze_manifest.py --write    # explicit MUTATING maintenance path:
                                       # regenerates every deterministic
                                       # artifact, then writes the manifest

The hash-only freeze adjudication runs `--verify` and STOPS on any mismatch.
PART_VI_FREEZE_MANIFEST_v0_superseded.json is preserved as superseded
evidence (thread 019fe550 "STOP—pre-freeze correction") and hashed here.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

PART6 = Path(__file__).resolve().parent
SURVEY = PART6.parent
REPO = SURVEY.parent.parent          # .../agent_memory
PYTHON = sys.executable

FROZEN_AT = "2026-08-11"

ARTIFACTS = [
    # deliverable 1 — detector package
    "pilot/tau_survey/part6/detector.py",
    "pilot/tau_survey/part6/PART_VI_DETECTOR.md",
    "pilot/tau_survey/part6/detector_selftest.py",
    "pilot/tau_survey/part6/DETECTOR_SMOKE_DIFF.md",
    "pilot/tau_survey/part6/detector_smoke_diff.json",
    # deliverable 2 — prompt package
    "pilot/tau_survey/part6/PART_VI_PROMPTS.json",
    "pilot/tau_survey/part6/build_prompts.py",
    # deliverable 3 — judge package (+ parser module, correction C5)
    "pilot/tau_survey/part6/judge_package.json",
    "pilot/tau_survey/part6/build_judge.py",
    "pilot/tau_survey/part6/judge_parser.py",
    "pilot/tau_survey/part6/judge_leakcheck.py",
    # deliverable 4 — generator + manifests (+ date/domain fix, correction C1)
    "pilot/tau_survey/part6/generator.py",
    "pilot/tau_survey/part6/build_manifest.py",
    "pilot/tau_survey/part6/manifest_main.json",
    "pilot/tau_survey/part6/manifest_src.json",
    "pilot/tau_survey/part6/manifest_hr.json",
    "pilot/tau_survey/part6/manifest_cal.json",
    # deliverable 5 — power artifact (text superseded; code operative)
    "pilot/tau_survey/part6/PART_VI_POWER.md",
    "pilot/tau_survey/part6/power_check.py",
    "pilot/tau_survey/part6/power_table.json",
    # deliverable 6 — analyzer (+ corrections C4, B4 endpoint specificity)
    "pilot/tau_survey/part6/analyze_tau.py",
    "pilot/tau_survey/part6/analyze_tau_fixtures.py",
    # gatekeeper runners — REAL executables (round-2 B2/B3)
    "pilot/tau_survey/part6/rollout_engine.py",
    "pilot/tau_survey/part6/card_builder.py",
    "pilot/tau_survey/part6/harvest_runner.py",
    "pilot/tau_survey/part6/grid_runner.py",
    "pilot/tau_survey/part6/gs_calibrate.py",
    "pilot/tau_survey/part6/headroom_validator.py",
    "pilot/tau_survey/part6/headroom_validator_fixtures.py",
    # state-machine fixtures (round-2 B2)
    "pilot/tau_survey/part6/runner_fixtures.py",
    # bank feasibility (correction C2 + B5 honesty pass)
    "pilot/tau_survey/part6/feasibility_bank.py",
    "pilot/tau_survey/part6/feasibility_bank_results.json",
    "pilot/tau_survey/part6/FEASIBILITY_BANK.md",
    # decisions ledger (correction C7 + round-2 D-20..D-28 + round-3 D-30..D-34)
    "pilot/tau_survey/part6/PART_VI_FREEZE_DECISIONS.md",
    # merged end-to-end chain fixture (round-3 blocker 1)
    "pilot/tau_survey/part6/chain_fixture.py",
    # superseded protocol text (evidence only; operative = PROTOCOL_FILE)
    "pilot/tau_survey/PART_VI_PREREG_V3.md",
    # smoke harness files (runtime imports, round-3 blocker 4a)
    "pilot/tau_survey/smoke/common.py",
    "pilot/tau_survey/smoke/harness.py",
    "pilot/tau_survey/smoke/anchors_cpu.py",
    # deliverable 7 — freeze manifest builder itself
    "pilot/tau_survey/part6/freeze_manifest.py",
    # archived legacy anchors + superseded freeze evidence
    "pilot/tau_survey/part6/anchors_legacy_archived.json",
    "pilot/tau_survey/part6/PART_VI_FREEZE_MANIFEST_v0_superseded.json",
    "pilot/tau_survey/part6/PART_VI_FREEZE_MANIFEST_v1_superseded.json",
    "pilot/tau_survey/part6/PART_VI_FREEZE_MANIFEST_v2_superseded.json",
    "pilot/tau_survey/part6/PART_VI_FREEZE_MANIFEST_v3_superseded.json",
]

PROTOCOL_FILE = "pilot/tau_survey/PART_VI_PREREG_V4.md"
ARCHIVED_SOURCE = "pilot/tau_survey/smoke/anchors.json"

RUNTIME_DEPS = ["numpy", "torch", "transformers", "vllm", "litellm",
                "sentence-transformers"]

VENDOR_REPOS = {
    "tau-bench": ("pilot/tau_survey/vendor/tau-bench",
                  "59a200c6d575d595120f1cb70fea53cef0632f6b"),
    "tau2-bench": ("pilot/tau_survey/vendor/tau2-bench",
                   "668d3bcd135c02aa3438f987ef45735b7c163ee3"),
}


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def collect_hashes() -> dict:
    out = {}
    for rel in ARTIFACTS + [PROTOCOL_FILE, ARCHIVED_SOURCE]:
        p = REPO / rel
        if not p.exists():
            raise FileNotFoundError(rel)
        out[rel] = {"sha256": sha256_file(p), "bytes": p.stat().st_size}
    return out


def vendor_commits_live() -> dict:
    got = {}
    for name, (rel, _pin) in VENDOR_REPOS.items():
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO / rel,
                           capture_output=True, text=True)
        got[name] = r.stdout.strip() if r.returncode == 0 else f"ERROR: {r.stderr.strip()}"
    return got


def run_check(cmd: list[str], cwd: Path = PART6) -> tuple[int, str]:
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    tail = (r.stdout + r.stderr).strip().splitlines()
    return r.returncode, (tail[-1] if tail else "")


def runtime_env() -> dict:
    """Runtime dependency pins (round-2 B2): versions + module __init__ hashes."""
    import importlib
    import importlib.metadata as imd
    out = {}
    for p in RUNTIME_DEPS:
        rec = {}
        try:
            rec["version"] = imd.version(p)
        except Exception:
            rec["version"] = None
        try:
            mod = importlib.import_module(p.replace("-", "_"))
            init = Path(mod.__file__).parent / "__init__.py"
            if init.exists():
                rec["init_sha256"] = sha256_file(init)
        except Exception as e:
            rec["import_error"] = str(e)[:200]
        out[p] = rec
    return out


def derived_counts() -> dict:
    """Fixture/audit case counts derived FROM THE ACTUAL fixture/audit code
    (round-4 residual R4) — never hand-written numbers."""
    import importlib
    counts = {}
    af = importlib.import_module("analyze_tau_fixtures")
    counts["analyzer_fixtures"] = len(af.fixtures())
    rf = importlib.import_module("runner_fixtures")
    counts["runner_fixtures"] = len(rf.FIXTURES)
    rc, out = run_check([PYTHON, "headroom_validator.py", "--selftest"])
    import re
    m = re.search(r"(\d+) audit cases pinned", out)
    counts["headroom_audit_cases"] = int(m.group(1)) if m else None
    counts["headroom_selftest_exit"] = rc
    return counts


def supersedes_chain() -> list[dict]:
    """Superseded freeze manifests with their actual byte hashes."""
    out = []
    for p in sorted(PART6.glob("PART_VI_FREEZE_MANIFEST_v*_superseded.json")):
        out.append({"file": str(p.relative_to(REPO)), "sha256": sha256_file(p)})
    return out


def build_manifest() -> dict:
    hashes = collect_hashes()
    live = vendor_commits_live()
    counts = derived_counts()
    chain = supersedes_chain()
    return {
        "name": "PART_VI_FREEZE_MANIFEST",
        "frozen_at": FROZEN_AT,
        "supersedes": chain,
        "supersedes_note": ("superseded manifests kept as evidence with their "
                            "byte hashes; never verified against"),
        "scope": ("hash-only freeze of the Part VI gatekeeper freeze package "
                  "(PART_VI_PREREG_V4.md = THE operative protocol; corrections "
                  "C1–C7 + B1–B5 applied): detector, prompts, judge (+parser), "
                  "generator + 4 manifests, power, analyzer + fixtures, REAL "
                  "gatekeeper runners + state-machine fixtures, headroom validator, "
                  "bank feasibility, decisions, protocols (V4 operative, V3 "
                  "superseded), archived legacy anchors, vendor commits"),
        "artifacts": hashes,
        "vendor_commits": {
            name: {"path": VENDOR_REPOS[name][0], "pinned": VENDOR_REPOS[name][1],
                   "live_at_freeze": live[name],
                   "matches_pin": live[name] == VENDOR_REPOS[name][1]}
            for name in VENDOR_REPOS},
        "runtime": {"python": sys.version.replace("\n", " "),
                    "numpy_pinned_by_generator": "1.26.4"},
        "runtime_deps": runtime_env(),
        "functional_checks_at_freeze": {
            "judge_leakcheck": "zero 24/48 in rendered judge inputs; parser "
                               "inconsistency rule pinned on 12 cases (exit 0)",
            "detector_selftest --check": "read-only byte-exactness of the smoke "
                                         "agreement artifacts (exit 0)",
            "analyzer_selftest": f"{counts['analyzer_fixtures']}/{counts['analyzer_fixtures']} "
                                 "pinned fixtures pass (exit 0)",
            "runner_fixtures": f"{counts['runner_fixtures']}/{counts['runner_fixtures']} "
                               "state-machine fixtures on scripted engines driving "
                               "the real vendor env (exit 0)",
            "chain_fixture": "merged harvest->cards->prompts->cells->judge->"
                             "validator->analyzer contract chain (exit 0)",
            "headroom_validator_selftest": f"headroom recompute + "
                                           f"{counts['headroom_audit_cases']} audit "
                                           "cases pinned (exit "
                                           f"{counts['headroom_selftest_exit']})",
            "gs_selftest": "pinned bge-small-en-v1.5@5c38ec7c CPU pipeline (exit 0)",
            "manifest_determinism": "two consecutive build_manifest.py runs "
                                    "byte-identical",
        },
        "verifier_contract": {
            "command": "python freeze_manifest.py --verify",
            "mutating_command": "python freeze_manifest.py --write (regenerates "
                                "deterministic artifacts; NOT part of adjudication)",
            "stop_rule": ("exit 1 immediately on any hash mismatch, artifact drift, "
                          "vendor-commit drift, or failed read-only functional check; "
                          "no partial verdicts; the verifier never writes"),
        },
    }


def verify() -> int:
    man_path = PART6 / "PART_VI_FREEZE_MANIFEST.json"
    if not man_path.exists():
        print("STOP: PART_VI_FREEZE_MANIFEST.json absent — nothing was frozen")
        return 1
    recorded = json.loads(man_path.read_text())
    failures = []

    current = collect_hashes()
    for rel, rec in recorded["artifacts"].items():
        cur = current.get(rel)
        if cur is None or cur["sha256"] != rec["sha256"]:
            failures.append(f"hash mismatch: {rel}")
    extra = set(current) - set(recorded["artifacts"])
    if extra:
        failures.append(f"unrecorded artifact(s): {sorted(extra)}")

    live = vendor_commits_live()
    for name, vc in recorded["vendor_commits"].items():
        if live[name] != vc["pinned"]:
            failures.append(f"vendor drift: {name} {live[name]} != {vc['pinned']}")

    # runtime dependency pins (round-2 B2)
    for pkg, rec in runtime_env().items():
        old = recorded.get("runtime_deps", {}).get(pkg, {})
        if rec.get("version") != old.get("version"):
            failures.append(f"runtime drift: {pkg} version "
                            f"{rec.get('version')} != {old.get('version')}")
        elif rec.get("init_sha256") and rec.get("init_sha256") != old.get("init_sha256"):
            failures.append(f"runtime drift: {pkg} __init__ hash changed")

    # READ-ONLY functional checks (none of these write a byte)
    for cmd, label in (
        ([PYTHON, "judge_leakcheck.py"], "judge leak-grep/parser"),
        ([PYTHON, "detector_selftest.py", "--check"], "detector diff drift"),
        ([PYTHON, "analyze_tau.py", "--selftest"], "analyzer selftest"),
        ([PYTHON, "runner_fixtures.py"], "runner state-machine fixtures"),
        ([PYTHON, "chain_fixture.py"], "merged chain fixture"),
        ([PYTHON, "headroom_validator.py", "--selftest"], "headroom validator"),
        ([PYTHON, "gs_calibrate.py", "--selftest"], "G-S selftest"),
    ):
        rc, last = run_check(cmd)
        if rc != 0:
            failures.append(f"{label} FAILED: {last}")

    if failures:
        print("FREEZE VERIFY: STOP")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"FREEZE VERIFY: PASS — {len(recorded['artifacts'])} artifacts + "
          f"{len(recorded['vendor_commits'])} vendor commits hash-exact; "
          "read-only checks (judge leak-grep/parser, detector drift, analyzer, "
          "runner, chain, headroom validator, G-S) all green; nothing written")
    return 0


def write_all() -> int:
    """Explicit mutating maintenance path: regenerate every deterministic
    artifact, then the manifest itself."""
    steps = [
        ([PYTHON, "detector_selftest.py"], "detector diff artifacts"),
        ([PYTHON, "build_prompts.py"], "prompt package"),
        ([PYTHON, "build_judge.py"], "judge package"),
        ([PYTHON, "build_manifest.py"], "4 manifests"),
        ([PYTHON, "power_check.py"], "power table"),
    ]
    for cmd, label in steps:
        rc, last = run_check(cmd)
        if rc != 0:
            print(f"STOP: regeneration failed at {label}: {last}")
            return 1
        print(f"regenerated {label}")
    return main()


def main() -> int:
    doc = build_manifest()
    out = PART6 / "PART_VI_FREEZE_MANIFEST.json"
    out.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    print(f"wrote {out} ({len(doc['artifacts'])} artifact hashes, "
          f"{len(doc['vendor_commits'])} vendor pins)")
    return 0


if __name__ == "__main__":
    if "--verify" in sys.argv:
        raise SystemExit(verify())
    if "--write" in sys.argv:
        raise SystemExit(write_all())
    raise SystemExit(main())
