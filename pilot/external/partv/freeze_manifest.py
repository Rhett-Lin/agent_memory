"""Part V freeze manifest ($6/$8; Part V-A $A6): records sha256 of all
pinned artifacts and all partv code modules into FREEZE_MANIFEST.json.

STOP-AND-REPORT contract: if the pinned builder byte hash differs from
96ef23ea8516fc95c11d34b7c639e7474ada4f1b9dfd0a153c036b964f11eec3, or the
prompt-package file bytes differ from 46da398a..., this tool raises and
writes nothing.

Part V-A ($A6): modules added by the amendment (allocator.py,
feasibility_sim.py) are hashed into the manifest BEFORE any harvest; the
pre-amendment hashes of the superseded pool-construction semantics
(prepare_pools.py v1 greedy reservation, harvest.py per-(target,
candidate) exposure ledger) stay visible under "superseded" with notes.
The files themselves remain in the tree (provenance); allocator.py's
contract ledger + tuple matcher are authoritative for pool construction.

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
           "grid.py", "freeze_manifest.py",
           "allocator.py", "feasibility_sim.py"]

# Pre-amendment hashes retained for audit (taken from FREEZE_MANIFEST.json
# schema partv.freeze.v1, generated 2026-08-10 pre-amendment).
SUPERSEDED = {
    "prepare_pools.py": {
        "pre_amendment_sha256":
            "805162a278dc65d256e13ef6b7e76545a1b80659b1f9f9e27ef42af2568f2c62",
        "superseded_by": "allocator.py",
        "note": ("v1 greedy reservation order + per-attempt reservation "
                 "superseded by Part V-A $A2 ex-ante role contract and $A3 "
                 "tuple-constrained matching; v1 code path retained for "
                 "provenance only (module docstring Part V-A block)"),
    },
    "harvest.py": {
        "pre_amendment_sha256":
            "1f506e9c426c4d08c0d61c103aaada7c07c5af5e89757cc8e2b72f22e75c8e5b",
        "superseded_by": "allocator.SourceAttemptLedger + tuple matcher",
        "note": ("per-(target, candidate) exposure ledger with 8+8 lists "
                 "superseded by the $A2 global (candidate, role) attempt "
                 "cache (k=2 slots, <=8 global attempts, 8-fail permanent "
                 "ineligibility); file unchanged, hash re-recorded in "
                 "partv_modules above"),
    },
    "pools_manifest.json": {
        "pre_amendment_sha256": None,
        "superseded_by": "pools_manifest_v2.json (schema partv.pools.v2)",
        "note": ("v1 derivation-state output is left untouched in "
                 "$OUT_ROOT; the v2 manifest is produced by "
                 "prepare_pools --build-v2 / allocator --build"),
    },
}


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
        "schema": "partv.freeze.v2",
        "amendment": "Part V-A (frozen 2026-08-10): pool-construction "
                     "amendment modules hashed pre-harvest per $A6",
        "builder": {"path": "../run_alfworld_check.py",
                    "sha256": builder_sha, "verified_against_pin": True},
        "prompts": {"path": "../PART_V_PROMPTS.json",
                    "file_sha256": prompts_sha,
                    "mem_A_sha256": common.MEM_A_SHA256,
                    "mem_B_sha256": common.MEM_B_SHA256},
        "protocol_sha256": common.sha256_file(common.PROTOCOL_PATH),
        "power_sha256": common.sha256_file(common.POWER_PATH),
        "partv_modules": modules,
        "superseded": SUPERSEDED,
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
