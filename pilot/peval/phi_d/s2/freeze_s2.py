"""freeze_s2.py — writes freeze_rc1.json for S2-rc1.

Pins sha256/sha16 of every rc1 file, the S2_SPEC.md rule text, and every import
dependency of s2_comparator.py, plus the composite rc1 hash over the full pinned
surface. Also records the fixture-suite result (re-runs test_s2.py read-only into
a captured stream; no corpus is ever read here).

Deterministic content (no timestamps): re-running on unchanged inputs reproduces
the byte-identical rc1_hash. CPU only, stdlib only.
"""
import hashlib
import io
import json
import pathlib
import unittest

HERE = pathlib.Path(__file__).resolve().parent          # pilot/peval/phi_d/s2
PHI_D = HERE.parent                                     # pilot/peval/phi_d

RC_FILES = ["S2_SPEC.md", "s2_comparator.py", "test_s2.py", "score_s2.py"]
IMPORT_DEPS = [PHI_D / "common.py", PHI_D / "audit_expanded.py",
               PHI_D / "comparator_v0" / "comparator.py"]
OUT = HERE / "freeze_rc1.json"


def shas(path):
    b = path.read_bytes()
    h = hashlib.sha256(b).hexdigest()
    return {"sha256": h, "sha16": h[:16], "bytes": len(b)}


def run_fixtures():
    import sys
    sys.path.insert(0, str(HERE))
    import test_s2 as T
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=0).run(
        unittest.defaultTestLoader.loadTestsFromModule(T))
    return {"tests_run": result.testsRun,
            "failures": len(result.failures),
            "errors": len(result.errors),
            "ok": result.wasSuccessful()}


def main():
    files = {}
    for name in RC_FILES:
        files[name] = shas(HERE / name)
    deps = {str(p.relative_to(PHI_D)): shas(p) for p in IMPORT_DEPS}
    tests = run_fixtures()
    composite_src = "".join(
        f"{k}:{v['sha256']}\n" for k, v in sorted(files.items())) + "".join(
        f"dep:{k}:{v['sha256']}\n" for k, v in sorted(deps.items()))
    rc1_hash = hashlib.sha256(composite_src.encode()).hexdigest()
    doc = {
        "release": "s2-rc1",
        "rule_version": "s2-rc1",
        "generated_by": "pilot/peval/phi_d/s2/freeze_s2.py (deterministic content)",
        "discipline": {
            "execution": "NO 640-pair execution at rc1 (Codex adversarial review "
                         "round 3 comes first; score_s2.py --640 path is locked "
                         "by the RULE_VERSION pin)",
            "label_hygiene": "comparator inputs are two IRs + two texts only; "
                             "P/cell/family labels never enter s2_comparator",
            "frozen_before_outcomes": "all rules in S2_SPEC.md were frozen before "
                                      "any corpus verdict was observed",
            "cpu_only": True,
            "stdlib_only": True,
        },
        "files": files,
        "spec_text_sha256": files["S2_SPEC.md"]["sha256"],
        "spec_text_sha16": files["S2_SPEC.md"]["sha16"],
        "import_dependencies": deps,
        "fixture_suite": tests,
        "composite_sha_source": "sorted(name:sha256) over files[] then sorted("
                                "'dep:'name:sha256) over import_dependencies[]",
        "rc1_hash": rc1_hash,
        "rc1_hash16": rc1_hash[:16],
    }
    OUT.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {OUT}")
    print(f"rc1_hash = {rc1_hash}")
    print(f"fixtures: {tests['tests_run']} run, ok={tests['ok']}")


if __name__ == "__main__":
    main()
