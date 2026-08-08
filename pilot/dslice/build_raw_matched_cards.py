"""Part IV-A section A2 control system `raw_matched`.

For every memory_id, take the FULL untruncated raw transcript (identical
source trajectory as the raw and dslice cards) and top-truncate it to the
exact token count of the paired dslice card (same TokenMeter / tokenizer).
Naive truncation at a per-card paired budget: realized token counts are equal
to dslice by construction -- no padding, no new text.

QA / report:
  - paired |n_tokens(raw_matched) - n_tokens(dslice)| distribution (target 0
    for every card where the full transcript is long enough; only cards whose
    full transcript is shorter than the target keep their full length and are
    counted);
  - isolation grep family_idx|cell|A00|A01|A10|A11 -> 0 hits;
  - per-card map -> pilot/dslice/raw_matched_cards_map.jsonl

Outputs: <public_view>/systems/raw_matched/<memory_id>.json
"""

import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PILOT = os.path.dirname(_HERE)
sys.path.insert(0, _PILOT)

from generate_families import load_config, TokenMeter  # noqa: E402
from systems.build_raw_cards import (load_sealed, transcript_text,  # noqa: E402
                                     truncate_card)
from dslice.build_dslice_cards import (DEFAULT_CONFIG, index_harvest,  # noqa: E402
                                       trajectory_for, SEALED_FORBIDDEN)


def truncate_to(text, target, meter):
    """Truncate text to exactly `target` tokens if possible (BPE boundary
    effects may shift a re-count by +/-1, so probe a small window)."""
    ids = meter.tok.encode(text)
    if len(ids) <= target:
        return text, len(ids)
    for t in (target, target - 1, target + 1, target - 2, target + 2):
        cand = meter.tok.decode(ids[:t])
        if meter.count(cand) == target:
            return cand, target
    cand = meter.tok.decode(ids[:target])
    return cand, meter.count(cand)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    args = ap.parse_args()
    cfg = load_config(args.config)
    os.environ.setdefault("HF_HOME", cfg["paths"]["hf_home"])
    pub = cfg["paths"]["public_view"]

    with open(os.path.join(_PILOT, "systems", "raw_cards_map.jsonl")) as f:
        rows = [json.loads(l) for l in f]
    with open(os.path.join(_HERE, "cards_map.jsonl")) as f:
        dslice_tok = {json.loads(l)["memory_id"]: json.loads(l)["n_tokens"]
                      for l in f}

    mems, tasks, fams = load_sealed(cfg["paths"]["sealed"])
    harvest_idx = index_harvest(cfg)
    meter = TokenMeter(cfg["memories"]["tokenizer"])
    out_dir = os.path.join(pub, "systems", "raw_matched")
    os.makedirs(out_dir, exist_ok=True)

    out_rows, n_leak = [], 0
    for r in rows:
        mid = r["memory_id"]
        traj = trajectory_for(r, harvest_idx, tasks, fams, pub)
        full = transcript_text(traj)
        card, n_tok = truncate_to(full, dslice_tok[mid], meter)
        leak = [w for w in SEALED_FORBIDDEN if w in card]
        n_leak += len(leak)
        with open(os.path.join(out_dir, mid + ".json"), "w") as f:
            json.dump({"memory_id": mid, "text": card}, f, indent=1,
                      sort_keys=True)
        out_rows.append({"memory_id": mid, "cell": r["cell"],
                         "card_family_idx": r["card_family_idx"],
                         "card_sibling_idx": r["card_sibling_idx"],
                         "n_tokens": n_tok,
                         "n_tokens_dslice_paired": dslice_tok[mid],
                         "paired_abs_diff": abs(n_tok - dslice_tok[mid]),
                         "full_shorter_than_target":
                             meter.count(full) <= dslice_tok[mid]})
    with open(os.path.join(_HERE, "raw_matched_cards_map.jsonl"), "w") as f:
        for o in out_rows:
            f.write(json.dumps(o, sort_keys=True) + "\n")

    import statistics
    from collections import Counter
    diffs = [o["paired_abs_diff"] for o in out_rows]
    toks = [o["n_tokens"] for o in out_rows]
    print("[raw_matched] cards=%d tokens: min=%d mean=%.2f max=%d"
          % (len(out_rows), min(toks), statistics.mean(toks), max(toks)))
    print("[raw_matched] paired |dtok|: max=%d mean=%.3f hist=%s"
          % (max(diffs), statistics.mean(diffs), dict(Counter(diffs))))
    print("[raw_matched] full_shorter_than_target=%d  sealed_leak=%d"
          % (sum(o["full_shorter_than_target"] for o in out_rows), n_leak))
    print("[raw_matched] cards -> %s ; map -> %s"
          % (out_dir, os.path.join(_HERE, "raw_matched_cards_map.jsonl")))


if __name__ == "__main__":
    main()
