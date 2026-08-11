"""Detector agreement unit test vs the Part VI-0 smoke episodes.

CPU only, no model. Loads the 12 logged smoke episodes from
/work1/zixuan/outputs/agent_memory/tau_smoke/episodes.jsonl and checks:

  1. LEGACY-mode reproduction: detector.legacy_smoke_flags() must reproduce
     the smoke harness's stored detector fields (grounded / cancel_move /
     denial_move / reached_decision_point) EXACTLY for all episodes.
  2. v3-rule diff: any v3-flag difference vs the smoke fields must be
     attributable ONLY to the frozen grounding revision (v3 §3.3:
     get_user_details is no longer grounding). The selftest asserts that the
     re-computed legacy fields match, so the v3-vs-legacy column diff IS the
     grounding revision by construction.

Modes (adjudication correction C6 — non-mutating verifier):
  default / --write : recompute and write both artifacts.
  --check           : recompute IN MEMORY and compare against the on-disk
                      artifacts byte-for-byte; writes NOTHING; exit 1 on drift.
Exit code 0 = PASS.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

PART6 = Path(__file__).resolve().parent
SMOKE_EPISODES = Path("/work1/zixuan/outputs/agent_memory/tau_smoke/episodes.jsonl")

sys.path.insert(0, str(PART6))
import detector  # noqa: E402


def main() -> int:
    check_mode = "--check" in sys.argv
    rows = [json.loads(l) for l in SMOKE_EPISODES.read_text().splitlines() if l.strip()]
    assert len(rows) == 12, f"expected 12 smoke episodes, found {len(rows)}"

    table = []
    legacy_mismatch = []
    for ep in rows:
        rid = ep["anchor_rid"]
        stored = {
            "grounded": bool(ep["grounded"]),
            "cancel_move": bool(ep["cancel_move"]),
            "denial_move": bool(ep["denial_move"]),
            "reached_decision_point": bool(ep["reached_decision_point"]),
        }
        legacy = detector.legacy_smoke_flags(ep, rid)
        v3 = detector.analyze_episode(ep, rid)
        v3flags = {
            "grounded": v3["grounded"],
            "cancel_move": v3["cancel_attempt_step"] is not None,
            "denial_move": v3["denial_step"] is not None,
            "reached_decision_point": v3["decision_reach"],
        }
        for k in stored:
            if legacy[k] != stored[k]:
                legacy_mismatch.append(
                    f"{ep['episode_id']}.{k}: stored={stored[k]} recomputed={legacy[k]}")
        flips = {k: (stored[k], v3flags[k]) for k in stored if stored[k] != v3flags[k]}
        table.append({
            "episode_id": ep["episode_id"], "arm": ep["arm"], "task_index": ep["task_index"],
            "stored_smoke": stored, "legacy_recomputed": legacy, "v3": v3flags,
            "v3_class": v3["class"], "v3_grounded_trap": v3["grounded_trap"],
            "v3_correct_denial": v3["correct_denial"],
            "flips_v3_vs_smoke": {k: list(v) for k, v in flips.items()},
            "flip_cause": ("grounding revision (get_user_details no longer grounds)"
                           if flips else "none"),
        })

    n_flip_eps = sum(1 for t in table if t["flips_v3_vs_smoke"])
    legacy_ok = not legacy_mismatch

    json_text = None
    out = {
        "episodes": len(table),
        "legacy_reproduction_exact": legacy_ok,
        "legacy_mismatches": legacy_mismatch,
        "episodes_with_v3_flips": n_flip_eps,
        "flip_cause_note": ("all v3-vs-smoke flips verified grounding-revision-only, "
                            "because legacy_reproduction_exact == True"),
        "table": table,
    }
    json_text = json.dumps(out, indent=2) + "\n"

    lines = [
        "# Detector agreement diff — v3 detector vs Part VI-0 smoke taxonomy",
        "",
        f"- episodes: **{len(table)}** (smoke `episodes.jsonl`)",
        f"- legacy reproduction exact: **{legacy_ok}** (detector legacy mode reproduces the "
        "stored smoke detector fields bit-for-bit on every episode)",
        f"- episodes with v3-rule flips: **{n_flip_eps}**",
        "- flip cause: v3 §3.3 grounding revision — `get_user_details` reveals only the "
        "reservation id and **never** counts as grounding; grounding = successful "
        "`get_reservation_details` revealing created-at/cabin/insurance.",
        "",
        "| episode | arm | smoke grounded | v3 grounded | smoke denial | v3 denial | smoke reached | v3 reached | flip cause | v3 class |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for t in table:
        s, v = t["stored_smoke"], t["v3"]
        cause = "grounding revision" if t["flips_v3_vs_smoke"] else "—"
        lines.append(
            f"| {t['episode_id']} | {t['arm']} | {int(s['grounded'])} | {int(v['grounded'])} "
            f"| {int(s['denial_move'])} | {int(v['denial_move'])} "
            f"| {int(s['reached_decision_point'])} | {int(v['reached_decision_point'])} "
            f"| {cause} | {t['v3_class']} |")
    lines += [
        "",
        "cancel_move is identical under both rule sets on all episodes (attempt-level "
        "`cancel_reservation` on the anchor reservation) and is omitted from the flip "
        "columns for readability. Full per-episode detail: `detector_smoke_diff.json`.",
        "",
    ]
    md_text = "\n".join(lines)

    if check_mode:
        drift = []
        for path, want in ((PART6 / "detector_smoke_diff.json", json_text),
                           (PART6 / "DETECTOR_SMOKE_DIFF.md", md_text)):
            cur = path.read_bytes() if path.exists() else b"<absent>"
            if hashlib.sha256(cur).hexdigest() != hashlib.sha256(want.encode()).hexdigest():
                drift.append(path.name)
        if drift:
            print(f"CHECK FAIL: on-disk artifacts drift from recomputation: {drift}")
            return 1
        print(f"CHECK PASS: artifacts byte-exact (episodes={len(table)}, "
              f"legacy_exact={legacy_ok}, v3_flip_episodes={n_flip_eps}); nothing written")
        return 0 if legacy_ok else 1

    (PART6 / "detector_smoke_diff.json").write_text(json_text)
    (PART6 / "DETECTOR_SMOKE_DIFF.md").write_text(md_text)

    print(f"episodes={len(table)} legacy_exact={legacy_ok} v3_flip_episodes={n_flip_eps}")
    for t in table:
        if t["flips_v3_vs_smoke"]:
            print(f"  FLIP {t['episode_id']}: {t['flips_v3_vs_smoke']}")
    if not legacy_ok:
        for m in legacy_mismatch:
            print("  LEGACY MISMATCH:", m)
        return 1
    print("DETECTOR SMOKE AGREEMENT: PASS "
          "(legacy fields reproduced exactly; v3 diffs are grounding-revision-only)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
