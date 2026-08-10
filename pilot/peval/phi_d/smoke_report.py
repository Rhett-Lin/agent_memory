"""Smoke/full rescue analysis for out/guided/rescue1.jsonl.

Per canonical failure class (json_parse_error=truncation, schema_validation_error):
rows attempted, first-pass valid, post-retry valid (the corpus-effective rate).
Gate per plan: truncation-class rescue mostly resolving means post-retry >= 85%.
No labels are read.
"""
import collections
import json
import sys

import common as C

SRC = C.OUT / "extractions.jsonl"
RESC = C.OUT / "guided" / "rescue1.jsonl"


def main(keys_file=None):
    canon = {r["key"]: r for r in (json.loads(l) for l in open(SRC))}
    resc = [json.loads(l) for l in open(RESC)] if RESC.exists() else []
    if keys_file:
        doc = json.load(open(keys_file))
        keep = set(doc["keys"] if isinstance(doc, dict) else doc)
        resc = [r for r in resc if r["key"] in keep]
    by_class = collections.defaultdict(lambda: {"n": 0, "first_pass_valid": 0, "valid": 0})
    for r in resc:
        cls = canon[r["key"]]["error_class"]
        b = by_class[cls]
        b["n"] += 1
        b["valid"] += int(r["valid"])
        b["first_pass_valid"] += int(r["valid"] and r.get("attempts", 1) == 1)
    out = {}
    for cls, b in sorted(by_class.items()):
        out[cls] = {**b,
                    "first_pass_rate": b["first_pass_valid"] / b["n"],
                    "post_retry_rate": b["valid"] / b["n"]}
    print(json.dumps(out, indent=2))
    return out


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
