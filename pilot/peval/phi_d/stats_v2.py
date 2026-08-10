"""Post-rescue corpus statistics for out/extractions_v2.jsonl.

Computes: overall validity, by-kind validity, error-class breakdown, rescue
per-class rescue rates, UNKNOWN/ABSENT/present distribution, evidence-span
presence, node op distribution, and the comparator ceiling = per-cell
both-sides-IR-valid rate over pilot/peval/pairs.jsonl.
Cell/P/S labels are used ONLY for the per-cell ceiling breakdown (eval-only,
same discipline as score_baselines.py); nothing here feeds a model prompt.

Output: out/guided/stats_v2.json
"""
import collections
import json
import pathlib

import common as C
from score_baselines import extraction_stats

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "out"
V2 = OUT / "extractions_v2.jsonl"
DST = OUT / "guided" / "stats_v2.json"


def text_key(kind, text):
    return f"{kind}:{C.sha(text)[:16]}"


def main():
    rows = [json.loads(l) for l in open(V2)]
    emap = {r["key"]: r for r in rows}
    base = extraction_stats(rows)   # status/evidence/op distributions, reused verbatim

    pairs = C.load_pairs()
    per_cell = collections.defaultdict(lambda: [0, 0])   # cell -> [both_valid, n]
    side_valid = collections.Counter()
    for p in pairs:
        ik = text_key("instruction", p["instruction"])
        mk = text_key("memory", p["memory_text"])
        iv = bool(emap[ik]["valid"]); mv = bool(emap[mk]["valid"])
        per_cell[p["cell"]][1] += 1
        per_cell[p["cell"]][0] += int(iv and mv)
        side_valid[f"instruction_valid={iv} memory_valid={mv}"] += 1
    ceiling = {c: {"both_valid": v, "n": n, "rate": v / n} for c, (v, n) in sorted(per_cell.items())}
    overall_both = sum(v for v, _ in per_cell.values())

    merged_by_kind = {}
    for kind in ("instruction", "memory"):
        sub = [r for r in rows if r["kind"] == kind]
        merged_by_kind[kind] = {"n": len(sub), "valid": sum(1 for r in sub if r["valid"])}

    rescue_rows = [r for r in rows if r.get("rescue")]
    promoted = [r for r in rows if r.get("rescue", {}).get("promoted_from")]
    surv = collections.Counter(r["error_class"] for r in rows if not r["valid"])
    rescue_by_canonical_class = collections.Counter(
        (r["rescue"]["canonical_error_class"]) for r in promoted)

    out = {
        "file": "out/extractions_v2.jsonl",
        "n_rows": len(rows),
        "n_valid": base["n_valid"],
        "validity_rate": base["n_valid"] / len(rows),
        "target_479": {"met": base["n_valid"] >= 479, "short_by": max(0, 479 - base["n_valid"])},
        "by_kind": merged_by_kind,
        "invalid_survivors_by_error_class": dict(surv),
        "rescue": {"attempted": len(rescue_rows), "promoted": len(promoted),
                   "promoted_by_canonical_error_class": dict(rescue_by_canonical_class)},
        "comparator_ceiling": {
            "overall_both_side_valid": f"{overall_both}/640",
            "overall_rate": overall_both / len(pairs),
            "per_cell": ceiling,
            "side_valid_cross": dict(side_valid)},
        "status_distribution": base["status_distribution"],
        "evidence_presence_rate_among_present": base["evidence_presence_rate_among_present"],
        "node_op_distribution": base["node_op_distribution"],
        "first_pass_error_classes": base["first_pass_error_classes"],
    }
    DST.parent.mkdir(parents=True, exist_ok=True)
    with open(DST, "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(json.dumps({k: out[k] for k in ("n_valid", "validity_rate", "by_kind",
                                          "invalid_survivors_by_error_class",
                                          "comparator_ceiling")}, indent=2))


if __name__ == "__main__":
    main()
