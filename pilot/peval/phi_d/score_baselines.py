"""S1 scoring: decomposed-judge vs labels + registered-baseline tabulation.

THIS IS THE ONLY SCRIPT IN phi_d/ THAT READS LABELS (cell/P/S). No threshold
tuning: the verdict->score mapping {match:1.0, unknown:0.5, contradict:0.0} and
the abstain rule (invalid/unknown judge -> score 0.5, kept, never dropped) are
fixed in SPEC.md section 6 before any label is inspected by this pipeline.

Outputs (under pilot/peval/phi_d/out/):
  summary.json    all metrics + extraction stats
  examples.jsonl  5 random (seed 42) side-by-side text -> extracted IR for human audit
"""
import collections
import json
import random

import common as C

VERDICT_SCORE = {"match": 1.0, "unknown": 0.5, "contradict": 0.0}

# Registered baselines (design doc PHI_D_EVALUATOR_PLAN.md section 0 / pilot/peval README).
# Static tabulation only - nothing is retrained or recomputed for these except the
# sim_* reproduction straight from pairs.jsonl columns.
REGISTERED_BASELINES = {
    "sim_embed (recomputed from pairs.jsonl)": {"overall": None, "S1": None},
    "holistic intent judge ~ STITCH (registered)": {"overall": 0.508, "S1": None},
    "P-hat v1 logistic, family-CV (registered)": {"overall": 0.966, "S1": 0.935},
    "P-hat v1 logistic, LOAO (registered)": {"overall": 0.636, "S1": 0.590},
}


def auc(scores, labels):
    """Rank-based AUC with tie handling; None if single-class."""
    n1 = sum(labels)
    n0 = len(labels) - n1
    if n1 == 0 or n0 == 0:
        return None
    order = sorted(range(len(scores)), key=lambda i: scores[i])
    ranks = [0.0] * len(scores)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and scores[order[j + 1]] == scores[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    sum_pos = sum(r for r, l in zip(ranks, labels) if l == 1)
    return (sum_pos - n1 * (n1 + 1) / 2.0) / (n1 * n0)


def load_jsonl(path):
    if not path.exists():
        return []
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]


def load_extractions_dedup(path):
    """Latest row per key wins (rescue-pass rows are appended after the originals)."""
    rows = load_jsonl(path)
    by_key = {}
    for r in rows:          # later occurrences overwrite earlier ones
        by_key[r["key"]] = r
    return list(by_key.values())


# ---------------------------------------------------------------- judge metrics

def judge_metrics(pairs, judgments):
    jmap = {j["memory_id"]: j for j in judgments}
    rows = []
    missing = 0
    for p in pairs:
        j = jmap.get(p["memory_id"])
        if j is None:
            missing += 1
            verdict, valid = None, False
        else:
            verdict, valid = (j["verdict"] if j["valid"] else None), j["valid"]
        abstain = (verdict is None) or (verdict == "unknown")
        score = VERDICT_SCORE.get(verdict, 0.5)  # abstain -> 0.5, fixed rule
        rows.append({"row": p, "verdict": verdict, "valid": valid,
                     "abstain": abstain, "score": score,
                     "error_class": (j or {}).get("error_class")})
    if missing:
        print(f"[score] WARNING: {missing} pairs without judgment row")

    P = [r["row"]["P"] for r in rows]
    S = [r["row"]["S"] for r in rows]
    sc = [r["score"] for r in rows]
    out = {}

    out["auc_overall_all_pairs"] = auc(sc, P)
    s1 = [i for i in range(len(rows)) if S[i] == 1]
    out["auc_S1_all_pairs"] = auc([sc[i] for i in s1], [P[i] for i in s1])

    cov = [i for i in range(len(rows)) if not rows[i]["abstain"]]
    out["n_pairs"] = len(rows)
    out["n_covered"] = len(cov)
    out["coverage"] = len(cov) / len(rows)
    out["auc_overall_covered_only"] = auc([sc[i] for i in cov], [P[i] for i in cov])
    cov_s1 = [i for i in cov if S[i] == 1]
    out["auc_S1_covered_only"] = auc([sc[i] for i in cov_s1], [P[i] for i in cov_s1])

    # agreement on covered: verdict match <-> P=1
    agree = sum(1 for i in cov if (rows[i]["verdict"] == "match") == (P[i] == 1))
    out["accuracy_covered"] = agree / len(cov) if cov else None
    # full-set accuracy with abstain counted as error
    agree_all = sum(1 for i in range(len(rows)) if (rows[i]["verdict"] == "match") == (P[i] == 1))
    out["accuracy_all_abstain_as_error"] = agree_all / len(rows)

    # verdict distribution overall + per cell
    vd = collections.Counter(r["verdict"] if r["verdict"] is not None else "invalid" for r in rows)
    out["verdict_distribution"] = dict(vd)
    per_cell = {}
    for cell in ("A00", "A01", "A10", "A11"):
        idx = [i for i in range(len(rows)) if rows[i]["row"]["cell"] == cell]
        c = collections.Counter(rows[i]["verdict"] if rows[i]["verdict"] is not None else "invalid" for i in idx)
        rates = {k: c.get(k, 0) / len(idx) for k in ("match", "contradict", "unknown", "invalid")}
        per_cell[cell] = {"n": len(idx), "verdict_rates": rates}
    out["per_cell"] = per_cell

    # invalid breakdown
    inv = collections.Counter(r["error_class"] for r in rows if not r["valid"])
    out["invalid_by_error_class"] = {str(k): v for k, v in inv.items()}
    out["invalid_rate"] = sum(1 for r in rows if not r["valid"]) / len(rows)
    return out


# ---------------------------------------------------------------- extraction stats

def extraction_stats(extractions):
    out = {}
    out["n_texts"] = len(extractions)
    out["n_valid"] = sum(1 for e in extractions if e["valid"])
    out["failure_rate"] = 1 - out["n_valid"] / max(1, out["n_texts"])
    out["retried"] = sum(1 for e in extractions if e.get("attempts", 1) == 2)
    by_kind = {}
    for kind in ("instruction", "memory"):
        sub = [e for e in extractions if e["kind"] == kind]
        by_kind[kind] = {"n": len(sub), "n_valid": sum(1 for e in sub if e["valid"])}
    out["by_kind"] = by_kind
    out["invalid_by_error_class"] = dict(collections.Counter(
        e["error_class"] for e in extractions if not e["valid"]))
    out["first_pass_error_classes"] = dict(collections.Counter(
        e["first_pass_error"] for e in extractions if e.get("first_pass_error")))

    # UNKNOWN vs ABSENT vs present distribution + evidence presence among present
    status_counts = collections.Counter()
    evid_present = collections.Counter()   # among status==present: evidence non-empty?
    fields_tracked = ["role", "node", "predicate.attribute", "predicate.op",
                      "predicate.value", "predicate.polarity", "termination"]
    for e in extractions:
        if not e["valid"]:
            continue
        ir = e["ir"]
        spots = []
        for rv in ir["roles"].values():
            spots.append(("role", rv))
        for n in ir["nodes"]:
            spots.append(("node", n))
            if n["op"] == "branch":
                pr = n["args"]["predicate"]
                for fk in ("attribute", "op", "value", "polarity"):
                    spots.append((f"predicate.{fk}", pr[fk]))
        spots.append(("termination", ir["termination"]))
        for fkey, v in spots:
            status_counts[f"{fkey}:{v['status']}"] += 1
            if v["status"] == "present":
                has = bool((v.get("evidence") or "").strip())
                evid_present[fkey] += 0  # ensure key exists
                evid_present[f"{fkey}__with_evidence"] += int(has)
                evid_present[f"{fkey}__total"] += 1
    out["status_distribution"] = dict(status_counts)
    ev_rates = {}
    for f in fields_tracked:
        tot = evid_present.get(f"{f}__total", 0)
        w = evid_present.get(f"{f}__with_evidence", 0)
        ev_rates[f] = (w / tot) if tot else None
    out["evidence_presence_rate_among_present"] = ev_rates

    # node op distribution
    ops = collections.Counter()
    for e in extractions:
        if e["valid"]:
            ops.update(n["op"] for n in e["ir"]["nodes"])
    out["node_op_distribution"] = dict(ops)
    return out


# ---------------------------------------------------------------- main

def main():
    pairs = C.load_pairs()
    judgments = load_jsonl(C.OUT / "judgments.jsonl")
    extractions = load_extractions_dedup(C.OUT / "extractions.jsonl")
    print(f"[score] pairs={len(pairs)} judgments={len(judgments)} extractions={len(extractions)}")

    summary = {}
    summary["judge"] = judge_metrics(pairs, judgments) if judgments else None
    summary["extraction"] = extraction_stats(extractions) if extractions else None

    # sim baselines recomputed from stored columns (no model, no training)
    P = [r["P"] for r in pairs]
    S = [r["S"] for r in pairs]
    s1 = [i for i in range(len(pairs)) if S[i] == 1]
    sim = {}
    for col in ("sim_embed", "sim_tf"):
        sc = [r[col] for r in pairs]
        sim[col] = {"overall": auc(sc, P),
                    "S1": auc([sc[i] for i in s1], [P[i] for i in s1])}
    summary["sim_recomputed"] = sim
    REGISTERED_BASELINES["sim_embed (recomputed from pairs.jsonl)"] = {
        "overall": round(sim["sim_embed"]["overall"], 4), "S1": round(sim["sim_embed"]["S1"], 4)}
    summary["registered_baselines"] = REGISTERED_BASELINES

    # frozen input hashes for the record
    import hashlib
    summary["inputs"] = {
        "pairs_jsonl_sha256": hashlib.sha256(open(C.PAIRS, "rb").read()).hexdigest(),
        "score_mapping": VERDICT_SCORE,
        "abstain_rule": "invalid judge OR verdict=unknown -> score 0.5 (kept, never dropped)",
    }

    C.OUT.mkdir(parents=True, exist_ok=True)
    with open(C.OUT / "summary.json", "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    # 5 random side-by-side examples for human audit (seed 42)
    rng = random.Random(42)
    valid_ext = [e for e in extractions if e["valid"]]
    ex = rng.sample(valid_ext, k=min(5, len(valid_ext)))
    with open(C.OUT / "examples.jsonl", "w") as f:
        for e in ex:
            f.write(json.dumps({"kind": e["kind"], "key": e["key"], "text": e["text"],
                                "ir": e["ir"]}, ensure_ascii=False) + "\n")
    print(f"[score] wrote {C.OUT/'summary.json'} and examples.jsonl ({len(ex)} examples)")

    jm = summary.get("judge")
    if jm:
        print(f"[score] judge AUC overall={jm['auc_overall_all_pairs']:.4f} "
              f"S=1={jm['auc_S1_all_pairs']:.4f} coverage={jm['coverage']:.3f} "
              f"acc_covered={jm['accuracy_covered']:.4f}")
    print(f"[score] sim_embed overall={sim['sim_embed']['overall']:.4f} S=1={sim['sim_embed']['S1']:.4f}")


if __name__ == "__main__":
    main()
