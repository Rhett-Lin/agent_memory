"""ONE frozen comparator run over the 640 pairs (φ+d lane A pre-SFT baseline).

Joins pilot/peval/pairs.jsonl to out/extractions_v2.jsonl by text sha and runs
comparator.compare() per pair. Veto-field eligibility is consumed from
out/audit_expanded/field_metrics.json (present at run time): its demotions are
applied per the audit veto rule. Labels (cell/P/S/family/archetype) are NOT read
here — join keys are memory_id + text sha only.

Deterministic: file order of pairs.jsonl is the canonical row order; no RNG, no
timestamps inside verdicts.jsonl. Writes:
  verdicts.jsonl          one row per pair (comparator output trace)
  run_receipt_v0.json     provenance: code input shas, eligibility map, counts
"""
import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
PHI_D = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(PHI_D))

import comparator as K                       # noqa: E402

PAIRS = PHI_D.parent / "pairs.jsonl"
EXTRACTIONS = PHI_D / "out" / "extractions_v2.jsonl"
AUDIT_DIR = PHI_D / "audit_expanded"
OUT_VERDICTS = HERE / "verdicts.jsonl"
OUT_RECEIPT = HERE / "run_receipt_v0.json"


def sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def file_sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def main():
    pairs = [json.loads(l) for l in open(PAIRS) if l.strip()]
    exts = {}
    with open(EXTRACTIONS) as f:
        for line in f:
            if line.strip():
                e = json.loads(line)
                exts[e["key"]] = e

    eligibility, eligibility_raw = K.load_veto_eligibility(AUDIT_DIR)
    if not eligibility:
        raise RuntimeError("audit gate table missing at run time: "
                           f"{AUDIT_DIR / 'field_metrics.json'}")

    n_missing = 0
    rows = []
    for p in pairs:
        ki = f"instruction:{sha(p['instruction'])[:16]}"
        km = f"memory:{sha(p['memory_text'])[:16]}"
        ei, em = exts.get(ki), exts.get(km)
        if ei is None or em is None:
            n_missing += 1
            rows.append({"memory_id": p["memory_id"],
                         "instruction_key": ki, "memory_key": km,
                         "verdict": "unknown",
                         "reasons": [{"component": "ir", "code": "EXTRACTION_MISSING",
                                      "level": "unknown",
                                      "detail": "no extraction row for text sha"}],
                         "certificates": None})
            continue
        v = K.compare(ei["ir"], ei["text"], em["ir"], em["text"],
                      require_branch=True, eligibility=eligibility)
        rows.append({"memory_id": p["memory_id"],
                     "instruction_key": ki, "memory_key": km,
                     "verdict": v["verdict"],
                     "reasons": v["reasons"],
                     "certificates": {
                         "instruction_complete": v["certificates"]["instruction"]["complete"],
                         "memory_complete": v["certificates"]["memory"]["complete"],
                         "instruction_checks": v["certificates"]["instruction"]["checks"],
                         "memory_checks": v["certificates"]["memory"]["checks"],
                         "instruction_stats": v["certificates"]["instruction"].get("stats"),
                         "memory_stats": v["certificates"]["memory"].get("stats")}})

    assert len(rows) == len(pairs) == 640, (len(rows), len(pairs))
    with open(OUT_VERDICTS, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    import collections
    receipt = {
        "code": {"comparator_sha256": file_sha(HERE / "comparator.py"),
                 "run_comparator_sha256": file_sha(HERE / "run_comparator.py"),
                 "test_comparator_sha256": file_sha(HERE / "test_comparator.py")},
        "inputs": {"pairs_jsonl_sha256": file_sha(PAIRS),
                   "extractions_v2_sha256": file_sha(EXTRACTIONS),
                   "audit_field_metrics_sha256": file_sha(AUDIT_DIR / "field_metrics.json")},
        "eligibility": eligibility,
        "eligibility_raw": eligibility_raw,
        "require_branch_completeness": True,
        "n_pairs": len(rows),
        "n_extraction_missing": n_missing,
        "verdict_mix": dict(collections.Counter(r["verdict"] for r in rows)),
        "memory_certificate_complete_rate":
            sum(1 for r in rows if r["certificates"] and r["certificates"]["memory_complete"]) / len(rows),
        "instruction_certificate_complete_rate":
            sum(1 for r in rows if r["certificates"] and r["certificates"]["instruction_complete"]) / len(rows),
    }
    with open(OUT_RECEIPT, "w") as f:
        json.dump(receipt, f, indent=2, ensure_ascii=False)
    print(json.dumps(receipt, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
