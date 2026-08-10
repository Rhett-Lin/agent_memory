"""Merge canonical extractions + rescue1 rows into out/extractions_v2.jsonl.

Documented merge rule (frozen here, before stats are computed):
- Universe = the 532 canonical rows of out/extractions.jsonl (key set and order).
- valid canonical row          -> carried as-is, provenance.source_run = "canonical_v2".
- invalid canonical key with a VALID row in out/guided/rescue1.jsonl
                             -> the rescue row is promoted, plus a rescue note
                                (promoted_from, canonical_error_class).
- invalid canonical key whose rescue row is absent or invalid
                             -> the ORIGINAL canonical row is carried (valid=false,
                                original error_class), plus a rescue note
                                (attempted, rescue error_class/attempts if a row exists).
out/extractions.jsonl is never modified. Receipt: out/guided/merge_v2.receipt.json.
Labels (cell/P/S) are not read here.
"""
import hashlib
import json
import pathlib
import time

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "out"
CANON = OUT / "extractions.jsonl"
RESCUE = OUT / "guided" / "rescue1.jsonl"
DST = OUT / "extractions_v2.jsonl"
RCPT = OUT / "guided" / "merge_v2.receipt.json"


def sha_file(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def load(path):
    if not path.exists():
        return []
    return [json.loads(l) for l in open(path) if l.strip()]


def main():
    canon = load(CANON)
    rescue = {r["key"]: r for r in load(RESCUE)}
    assert len(canon) == 532 and len({r["key"] for r in canon}) == 532

    merged, n_promoted, n_still = [], 0, 0
    for r in canon:
        r = dict(r)
        if r.get("valid"):
            r["provenance"] = {"source_run": "canonical_v2",
                               "receipt": "out/run_receipt_s2.json"}
        elif r["key"] in rescue and rescue[r["key"]].get("valid"):
            q = dict(rescue[r["key"]])
            q["provenance"] = {"source_run": "rescue1",
                               "receipt": "out/guided/rescue1.receipt.json"}
            q["rescue"] = {"promoted_from": "canonical_v2_invalid",
                           "canonical_error_class": r.get("error_class")}
            r = q
            n_promoted += 1
        else:
            note = {"attempted": r["key"] in rescue}
            if r["key"] in rescue:
                note.update({"error_class": rescue[r["key"]].get("error_class"),
                             "attempts": rescue[r["key"]].get("attempts")})
            r["provenance"] = {"source_run": "canonical_v2_still_invalid",
                               "receipt": "out/run_receipt_s2.json"}
            r["rescue"] = note
            n_still += 1
        merged.append(r)

    assert len(merged) == 532 and len({r["key"] for r in merged}) == 532
    n_valid = sum(1 for r in merged if r.get("valid"))
    with open(DST, "w") as f:
        for r in merged:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    rcpt = {
        "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "rule": "canonical valid rows carried; invalid keys promoted from valid rescue1 rows; "
                "otherwise canonical invalid row kept with rescue note",
        "inputs": {"canonical": {"path": str(CANON.name), "sha256": sha_file(CANON)},
                   "rescue": {"path": str(RESCUE.relative_to(HERE)), "sha256": sha_file(RESCUE)}},
        "output": {"path": "out/extractions_v2.jsonl", "rows": len(merged),
                   "valid": n_valid, "validity_rate": n_valid / len(merged),
                   "promoted_from_rescue": n_promoted, "still_invalid": n_still,
                   "sha256": None},
        "keys_unique": True, "row_order": "canonical file order",
    }
    RCPT.parent.mkdir(parents=True, exist_ok=True)
    with open(DST, "rb") as f:
        rcpt["output"]["sha256"] = hashlib.sha256(f.read()).hexdigest()
    with open(RCPT, "w") as f:
        json.dump(rcpt, f, indent=2, ensure_ascii=False)
    print(json.dumps(rcpt["output"], indent=2))


if __name__ == "__main__":
    main()
