"""Builds the four frozen Part VI manifests (v3 §2.2 / §4 /§5).

  part6/manifest_src.json   640 harvest candidates (320 X-role + 320 R-role)
  part6/manifest_hr.json     40 headroom targets
  part6/manifest_cal.json    60 G-S calibration targets
  part6/manifest_main.json  240 main-grid targets

Every instance is synthetic (clone + frozen 5-field perturbation) with a CPU
GT-replay receipt. Global reservation order src/ -> hr/ -> cal/ -> main/ from
ONE PCG64 stream (seed 20260812): base reservations are consumed from a single
shuffled permutation, never reused across zones. Deterministic: two runs are
byte-identical (numpy stream stable, json sort_keys, no wall-clock).
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

PART6 = Path(__file__).resolve().parent
sys.path.insert(0, str(PART6))

import generator as G  # noqa: E402

FROZEN_AT = "2026-08-11"

# Frozen by the bank-feasibility ruling (correction C2): src pool 360 X +
# 360 R = 720 (was 320+320=640 at v0); per-source attempts 3. See
# FEASIBILITY_BANK.md (full-fill >= 0.95 for both roles at q >= 0.60; the
# v0 640/2-attempt pool only secured that at q >= 0.80).
ZONES = [  # (zone, role, count) in the frozen global reservation order
    ("src", "X", 360),
    ("src", "R", 360),
    ("hr", "target", 40),
    ("cal", "target", 60),
    ("main", "target", 240),
]


def render_instruction(template: str, reservation: dict, user: dict) -> str:
    return template.format(
        user_id=reservation["user_id"],
        reservation_id=reservation["reservation_id"],
        first_name=user["name"]["first_name"],
        last_name=user["name"]["last_name"],
        route_str=G.route_str(reservation),
    )


def main() -> int:
    data = G.load_data()
    hasher = G._Hasher(data)
    vendor_ids = set(data["reservations"])

    eligible = G.eligible_base_ids(data)
    rng = np.random.Generator(np.random.PCG64(G.SEED))

    perm = rng.permutation(len(eligible))   # single draw, consumed in order
    cursor = 0
    taken: set[str] = set()

    zone_entries: dict[str, list[dict]] = {"src": [], "hr": [], "cal": [], "main": []}
    slot = 0
    skipped_invalid = 0
    zone_skips: dict[str, int] = {}
    for zone, role, count in ZONES:
        for zone_idx in range(count):
            # first-valid ordering: draw candidates from the single PCG64
            # stream until one passes DOMAIN VALIDITY (post-correction C1);
            # skips are ledgered, draws are never rewound.
            while True:
                base_rid = eligible[perm[cursor]]
                cursor += 1
                base = data["reservations"][base_rid]
                uid = base["user_id"]
                user = data["users"][uid]

                tmpl_i = int(rng.choice(len(G.TEMPLATES), p=G.TEMPLATE_WEIGHTS))
                lo, hi = G.age_window(role)
                age_min = int(rng.integers(lo, hi + 1))
                created_at = (G.NOW - timedelta(minutes=age_min)).isoformat()
                first_leg_date = G.FLIGHT_FIRST_LEG_DATES[
                    int(rng.integers(0, len(G.FLIGHT_FIRST_LEG_DATES)))]
                rid = G.mint_reservation_id(rng, taken, vendor_ids)

                res = G.make_reservation(base, rid, created_at, first_leg_date)
                if G.leg_domain_report(data, res)["domain_ok"]:
                    break
                skipped_invalid += 1
                zone_skips[zone] = zone_skips.get(zone, 0) + 1
            instance_id = (
                f"tau6-{zone}-{role.lower()}-{zone_idx:04d}" if zone == "src"
                else f"tau6-{zone}-{zone_idx:04d}")
            canonical_id = f"{zone}/{instance_id}"
            instruction = render_instruction(
                G.TEMPLATES[tmpl_i][2], res, user)
            receipt = G.cpu_receipt(data, res, hasher, role)

            if not receipt["hashes_differ"]:
                raise AssertionError(f"{instance_id}: trap not env-detectable")
            az = receipt["assertions"]
            if not (az["basic_econ"] and az["no_insurance"] and az["domain_ok"]
                    and az["user_holds_reservation"] and az["gt_do_nothing_solvable"]):
                raise AssertionError(f"{instance_id}: construction assertion failed {az}")
            if role == "R" and not (az["in_window_r_lt_24"] and receipt["true_policy_legal"]):
                raise AssertionError(f"{instance_id}: R source must be <24h true-legal")
            if zone != "src" and not az["in_window_x_24_48"]:
                raise AssertionError(f"{instance_id}: must be inside (24h,48h]")
            if role == "X" and not az["in_window_x_24_48"]:
                raise AssertionError(f"{instance_id}: X source must be inside (24h,48h]")
            if zone != "src" and receipt["true_policy_legal"]:
                raise AssertionError(f"{instance_id}: target must be DENY under true policy")

            entry = {
                "instance_id": instance_id,
                "canonical_id": canonical_id,
                "zone": zone,
                "role": role if zone == "src" else "target",
                "slot_global": slot,
                "user": {"user_id": uid,
                         "first_name": user["name"]["first_name"],
                         "last_name": user["name"]["last_name"]},
                "instruction_template_id": G.TEMPLATES[tmpl_i][0],
                "instruction": instruction,
                "reservation": res,
                "perturbation": {
                    "fields": G.PERTURBED_FIELDS,
                    "base_reservation_id": base_rid,
                    "age_minutes_draw": age_min,
                    "first_leg_date_draw": first_leg_date.isoformat(),
                },
                "age_hours": G.age_hours(created_at),
                "receipt": receipt,
            }
            zone_entries[zone].append(entry)
            slot += 1

    # Frozen harvest candidate order (v3 §4): sha256(canonical game path)
    # ascending, per role. Precomputed now that the pool is frozen.
    for role in ("X", "R"):
        role_entries = [e for e in zone_entries["src"] if e["role"] == role]
        ranked = sorted(
            role_entries,
            key=lambda e: hashlib.sha256(
                ("tau6/" + e["canonical_id"]).encode()).hexdigest())
        for rank, e in enumerate(ranked):
            e["harvest_candidate_rank_within_role"] = rank

    meta_common = {
        "frozen_at": FROZEN_AT,
        "protocol": "pilot/tau_survey/PART_VI_PREREG_V3.md (v3 §2.2/§4/§5)",
        "object_naming": ("author-created tau-bench-v1-compatible V1 "
                          "cancel-denial instances (never 'the tau-bench airline "
                          "benchmark')"),
        "generator": {
            "prng": "numpy PCG64", "seed": G.SEED,
            "numpy_version": np.__version__,
            "perturbed_fields": G.PERTURBED_FIELDS,
            "age_windows_minutes": {"x": [G.AGE_MIN_X, G.AGE_MAX_X],
                                    "r": [G.AGE_MIN_R, G.AGE_MAX_R]},
            "now_iso": G.NOW_ISO,
            "timezone_convention": ("naive local ISO timestamps exactly as vendor "
                                    "data (wiki.md current time 2024-05-15 15:00:00 "
                                    "EST); no tz conversion"),
            "reservation_id_visibility": ("reservation id AND user id always included "
                                          "in the user-sim instruction"),
            "instruction_template_weights": {t[0]: t[1] for t in G.TEMPLATES},
            "template_texts": {t[0]: t[2] for t in G.TEMPLATES},
            "first_valid_ordering": ("single PCG64 stream; base reservations consumed "
                                     "from one permutation; no re-draws, no reuse"),
            "dedupe": ("minted reservation ids collision-checked against vendor DB and "
                       "all previously minted ids; base reservations used at most "
                       "once globally"),
            "global_reservation_order": ["src", "hr", "cal", "main"],
            "src_role_block_order": ["X", "R"],
            "eligible_base_count": len(eligible),
            "bases_consumed": cursor,
            "skipped_invalid_domain_global": skipped_invalid,
            "domain_rule": ("per-leg: valid ISO calendar date; flight_number in vendor "
                            "schedule on that date; schedule status in "
                            "{available, delayed, on time} (never airline-cancelled); "
                            "date strictly after NOW (post-correction C1)"),
        },
        "receipt_rule": ("CPU GT-replay: vendor CancelReservation.invoke + "
                         "consistent_hash(to_hashable(db)) (anchors_cpu.py mechanics); "
                         "GT-do-nothing hash != wrong-cancel hash, pure cancel delta"),
        "synthetic_db_rebuild_rule": G.build_synthetic_db.__doc__.strip(),
    }

    counts = {"src": len(zone_entries["src"]), "hr": len(zone_entries["hr"]),
              "cal": len(zone_entries["cal"]), "main": len(zone_entries["main"])}
    assert counts == {"src": 720, "hr": 40, "cal": 60, "main": 240}, counts
    assert counts["src"] >= 520, "src pool must be >= 520"

    for zone in ("src", "hr", "cal", "main"):
        gen_meta = dict(meta_common["generator"],
                        skipped_invalid_domain_this_zone=zone_skips.get(zone, 0))
        doc = {"meta": dict(meta_common, zone=zone, count=counts[zone],
                            generator=gen_meta),
               "entries": zone_entries[zone]}
        path = PART6 / f"manifest_{zone}.json"
        text = json.dumps(doc, indent=2, sort_keys=True) + "\n"
        path.write_text(text)
        print(f"wrote {path.name}: {counts[zone]} entries "
              f"sha256 {hashlib.sha256(text.encode()).hexdigest()[:16]}…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
