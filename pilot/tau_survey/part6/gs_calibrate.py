"""Part VI G-S calibration (v3 §4 descriptive-only; correction C3 — frozen
code, NOT deleted: the pinned bge rev exists in the local cache).

Descriptive G-S: 60 cal goals x R-bank cards, bge(goal, card) cosine,
empirical 5th percentile -> tau_s; acceptance rate audited and reported. The
G-S gate is NEVER a GO-bearing endpoint (v3 §4: 描述级, 不入 GO 判据).

Frozen pins
-----------
- model: BAAI/bge-small-en-v1.5, snapshot rev
  5c38ec7c405ec4b44b94cc5a9bb96e735b38267a (local HF cache path recorded).
- pooling: whatever the pinned 1_Pooling config declares (bge canonical CLS);
  read from the pinned modules, never re-selected.
- prompting: bge convention — goal side gets the bge query instruction
  prefix, card side gets no prefix.
- cosine similarity over all (goal, card) pairs (60 x |R-bank|);
  tau_s = floor-index 5th percentile of the pair score distribution (same
  percentile rule as analyze_tau.percentile); acceptance rate = fraction of
  pairs >= tau_s, reported with the audit.

Usage (CPU, later stage):  --goals FILE --cards FILE --out FILE
Selftest (synthetic strings, no experiment material):  --selftest
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

PART6 = Path(__file__).resolve().parent
sys.path.insert(0, str(PART6))

BGE_NAME = "BAAI/bge-small-en-v1.5"
BGE_REV = "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"
BGE_CACHE = ("/work1/zixuan/cache/huggingface/hub/models--BAAI--bge-small-en-v1.5/"
             f"snapshots/{BGE_REV}")
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
TAU_PERCENTILE = 0.05


def floor_percentile(sorted_vals, p):
    idx = min(max(int(math.floor(p * len(sorted_vals))), 0), len(sorted_vals) - 1)
    return sorted_vals[idx]


def load_encoder():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(BGE_CACHE)


def pair_cosines(model, goals: list[str], cards: list[str]) -> list[dict]:
    import numpy as np
    g_emb = model.encode([QUERY_PREFIX + g for g in goals],
                         normalize_embeddings=True, show_progress_bar=False)
    c_emb = model.encode(cards, normalize_embeddings=True, show_progress_bar=False)
    sims = (np.asarray(g_emb) @ np.asarray(c_emb).T)
    return [{"goal_idx": i, "card_idx": j, "cosine": float(sims[i, j])}
            for i in range(len(goals)) for j in range(len(cards))]


def calibrate(goals, cards):
    model = load_encoder()
    pairs = pair_cosines(model, goals, cards)
    dist = sorted(p["cosine"] for p in pairs)
    tau_s = floor_percentile(dist, TAU_PERCENTILE)
    accepted = sum(1 for p in pairs if p["cosine"] >= tau_s)
    return {
        "pins": {"model": BGE_NAME, "revision": BGE_REV, "cache_path": BGE_CACHE,
                 "pooling": "pinned 1_Pooling (bge canonical CLS)",
                 "query_prefix": QUERY_PREFIX},
        "n_goals": len(goals), "n_cards": len(cards), "n_pairs": len(pairs),
        "tau_s": tau_s, "percentile_rule": f"floor-index {TAU_PERCENTILE}",
        "acceptance_rate": accepted / len(pairs),
        "goals_sha256": hashlib.sha256("\n".join(goals).encode()).hexdigest(),
        "cards_sha256": hashlib.sha256("\n".join(cards).encode()).hexdigest(),
        "note": ("descriptive only; never a GO-bearing endpoint (v3 §4). "
                 "Acceptance on the calibration set is ~1 - percentile by "
                 "construction; the audit matter is the acceptance rate on "
                 "later placements."),
    }


def _selftest() -> int:
    goals = ["I want to cancel my reservation ABCDEF booked yesterday",
             "please cancel my booking GHIJKL, plans changed",
             "cancel reservation MNOPQR and refund me",
             "what is the weather in Paris today"]
    cards = ["[Recalled prior case]\nUser request: cancel basic-economy reservation ZZZZZZ, "
             "booked at 2024-05-15 08:00 — i.e. about 7 hours before the request, within "
             "the 24-hour cancellation window.\nWhat the agent did: pulled details, "
             "obtained explicit user confirmation, then called cancel_reservation\n"
             "Outcome: SUCCESS — full refund.\n[End of recalled case]",
             "[Recalled prior case]\nUser request: cancel basic-economy reservation YYYYYY, "
             "booked at 2024-05-14 20:00 — i.e. about 19 hours before the request, within "
             "the 24-hour cancellation window.\nWhat the agent did: listed the cancellation "
             "details and cancelled after confirmation\nOutcome: SUCCESS.\n[End of recalled case]"]
    r = calibrate(goals, cards)
    ok = (0.0 <= r["tau_s"] <= 1.0 and r["n_pairs"] == 8
          and 0.0 < r["acceptance_rate"] <= 1.0)
    print(json.dumps(r, indent=2, sort_keys=True))
    print("G-S SELFTEST:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--goals")
    ap.add_argument("--cards")
    ap.add_argument("--out")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return _selftest()
    goals = [json.loads(l)["instruction"] for l in Path(args.goals).read_text().splitlines() if l.strip()]
    cards = [json.loads(l)["card_text"] for l in Path(args.cards).read_text().splitlines() if l.strip()]
    r = calibrate(goals, cards)
    Path(args.out).write_text(json.dumps(r, indent=2, sort_keys=True) + "\n")
    print(f"wrote {args.out}: tau_s={r['tau_s']:.4f}, pairs={r['n_pairs']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
