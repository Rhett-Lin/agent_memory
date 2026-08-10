"""Part V freeze manifest ($6/$8): records sha256 of all pinned artifacts
and all partv code modules into FREEZE_MANIFEST.json.

STOP-AND-REPORT contract: if the pinned builder byte hash differs from
96ef23ea8516fc95c11d34b7c639e7474ada4f1b9dfd0a153c036b964f11eec3, or the
prompt-package file bytes differ from 46da398a..., this tool raises and
writes nothing.

Re-runnable: regenerating overwrites FREEZE_MANIFEST.json with the current
hashes (the manifest is a recording device, not a frozen artifact itself).
"""

import argparse
import json
import os

from pilot.external.partv import common

MODULES = ["__init__.py", "common.py", "gstruct.py", "analyze_gate.py",
           "prepare_pools.py", "rollout_engine.py", "harvest.py",
           "build_cards.py", "gates_and_audits.py", "headroom.py",
           "grid.py", "freeze_manifest.py"]


def build_manifest():
    builder_sha = common.verify_builder()          # raises on mismatch
    with open(common.PROMPTS_PATH, "rb") as f:
        import hashlib
        prompts_sha = hashlib.sha256(f.read()).hexdigest()
    if prompts_sha != common.PROMPTS_SHA256:
        raise common.FrozenHashMismatch(
            "prompt package hash mismatch: %s != %s -- STOP and report"
            % (prompts_sha, common.PROMPTS_SHA256))
    modules = {}
    for m in MODULES:
        p = os.path.join(common.PARTV_DIR, m)
        if os.path.exists(p):
            modules[m] = common.sha256_file(p)
    return {
        "schema": "partv.freeze.v1",
        "builder": {"path": "../run_alfworld_check.py",
                    "sha256": builder_sha, "verified_against_pin": True},
        "prompts": {"path": "../PART_V_PROMPTS.json",
                    "file_sha256": prompts_sha,
                    "mem_A_sha256": common.MEM_A_SHA256,
                    "mem_B_sha256": common.MEM_B_SHA256},
        "protocol_sha256": common.sha256_file(common.PROTOCOL_PATH),
        "power_sha256": common.sha256_file(common.POWER_PATH),
        "partv_modules": modules,
        "runtime": {"model": common.MODEL_7B, "model_rev": common.MODEL_7B_REV,
                    "bge": common.BGE_MODEL, "bge_rev": common.BGE_REV,
                    "numpy_pin": "1.26.4"},
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=os.path.join(common.PARTV_DIR,
                                                  "FREEZE_MANIFEST.json"))
    ap.add_argument("--check-only", action="store_true",
                    help="verify pins without writing")
    args = ap.parse_args(argv)
    man = build_manifest()
    if not args.check_only:
        with open(args.out, "w") as f:
            json.dump(man, f, indent=1, sort_keys=True)
        print("wrote", args.out)
    print(json.dumps({k: (v if not isinstance(v, dict) else "...")
                      for k, v in man.items()}, indent=1, sort_keys=True))
    return man


if __name__ == "__main__":
    main()
