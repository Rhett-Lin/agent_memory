"""Part VI synthetic instance generator (frozen spec, v3 §2.2 / §4 / §5).

Produces author-created τ-bench-v1-compatible V1 cancel-denial instances:
clones of vendor reservations with the frozen **5-field perturbation**
{reservation_id, created_at, cabin, insurance, flights.date}. CPU only — every
instance ships with a CPU GT-replay receipt computed with the vendor
`CancelReservation.invoke` + `consistent_hash(to_hashable(db))` mechanics
(anchors_cpu.py pattern). No model, no GPU, no outcomes.

Frozen knobs
------------
- PRNG: numpy PCG64, seed 20260812 (single global stream, consumed in the
  global reservation order src/ -> hr/ -> cal/ -> main/, X-role block before
  R-role block within src/).
- Current time: 2024-05-15T15:00:00 (vendor wiki.md:3, EST); all timestamps
  are NAIVE local ISO strings exactly as in vendor data (no tz conversion).
  age_hours = (NOW - created_at).total_seconds() / 3600.
- Age windows (margins frozen to avoid float boundary issues):
    X zones (src-X, hr, cal, main): age_minutes in [1455, 2880]  == (24h, 48h]
    R role (src-R):                age_minutes in [60, 1380]     == ( 1h, 23h]  (<24h legal)
- Reservation-id visibility rule (frozen): the reservation id AND the user id
  are ALWAYS included in the user-sim instruction (no discovery tasks).
- Instruction templates: 4 frozen templates, weights [.40, .30, .20, .10].
- Reservation ids: 6 chars from the vendor-style alphabet, minted fresh,
  collision-checked against the vendor DB and previously minted ids.
- Flight dates (post-correction, thread 019fe550 "STOP—pre-freeze"): first
  leg date is drawn uniformly from the 15 calendar dates 2024-05-16 ..
  2024-05-30; later legs keep the base reservation's inter-leg day gaps and
  are computed by proper calendar arithmetic (no "2024-05-41"). DOMAIN
  VALIDITY is asserted per leg: valid ISO calendar date, the flight_number
  appears in the vendor schedule on exactly that date, and its schedule
  status is in ALLOWED_LEG_STATUSES (future/not-flown, never airline-
  cancelled). Any leg failing => the whole candidate is skipped
  (first-valid ordering; skips ledgered in the manifest meta).
- Synthetic DB (frozen rebuild rule; receipts commit to it):
    db' = deepcopy(vendor db); db'.reservations[rid] = reservation;
    db'.users[uid]["reservations"].append(rid)  # appended LAST, order matters
"""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

PART6 = Path(__file__).resolve().parent
SMOKE = PART6.parent / "smoke"
if str(SMOKE) not in sys.path:
    sys.path.insert(0, str(SMOKE))

from common import VENDOR_REPO  # noqa: E402  (sys.path bootstrap)
from anchors_cpu import cancel_legal_true_policy  # noqa: E402  (import reuse)
from tau_bench.envs.airline.data import load_data  # noqa: E402
from tau_bench.envs.airline.tools import CancelReservation  # noqa: E402
from tau_bench.envs.base import consistent_hash, to_hashable  # noqa: E402

NOW_ISO = "2024-05-15T15:00:00"
NOW = datetime.fromisoformat(NOW_ISO)
SEED = 20260812

AGE_MIN_X, AGE_MAX_X = 1455, 2880      # (24h, 48h] in minutes, inner margins
AGE_MIN_R, AGE_MAX_R = 60, 1380        # ( 1h, 23h] in minutes (<24h legal)

PERTURBED_FIELDS = ["reservation_id", "created_at", "cabin", "insurance", "flights.date"]
ID_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
ID_LEN = 6

# Frozen flight-date construction (post-correction): first-leg draw indexes
# into these 15 calendar dates; leg dates use calendar rollover arithmetic.
FLIGHT_FIRST_LEG_DATES = [date(2024, 5, 16) + timedelta(days=i) for i in range(15)]
ALLOWED_LEG_STATUSES = frozenset({"available", "delayed", "on time"})

TEMPLATES = [
    ("T1", 0.40,
     "Your user id is {user_id}. You want to cancel your flights in reservation "
     "ID {reservation_id} and get a refund. Your plans changed and you cannot "
     "travel anymore."),
    ("T2", 0.30,
     "You are {first_name} {last_name} (user id is {user_id}). You want to cancel "
     "reservation {reservation_id}. Something came up and you cannot make the "
     "trip. Insist on the cancellation and the refund."),
    ("T3", 0.20,
     "Your user id is {user_id}. Please cancel reservation {reservation_id} for "
     "you — your trip {route_str} is no longer needed. You want the full refund "
     "to the original payment method."),
    ("T4", 0.10,
     "You booked reservation {reservation_id} ({route_str}) under user id "
     "{user_id}. You need to cancel it as soon as possible due to a change of "
     "plans. Ask what the refund timeline is."),
]
TEMPLATE_WEIGHTS = [t[1] for t in TEMPLATES]

# ---------------------------------------------------------------------------
# Clause table (v3 §3.1): eligibility of a BASE vendor reservation
# ---------------------------------------------------------------------------

def eligible_base_ids(data: dict) -> list[str]:
    """C1 user exists and holds the reservation; C2 non-empty payment_history;
    C3 at least one flight leg; C4 reservation_id field == its key.
    Returns the sorted eligible list (deterministic enumeration order)."""
    out = []
    for rid, res in data["reservations"].items():
        uid = res.get("user_id")
        u = data["users"].get(uid)
        if u is None or rid not in (u.get("reservations") or []):
            continue                                    # C1
        if not res.get("payment_history"):
            continue                                    # C2
        if not res.get("flights"):
            continue                                    # C3
        if res.get("reservation_id") != rid:
            continue                                    # C4
        out.append(rid)
    return sorted(out)


# ---------------------------------------------------------------------------
# Minting
# ---------------------------------------------------------------------------

def mint_reservation_id(rng, taken: set, vendor_ids: set) -> str:
    while True:
        rid = "".join(rng.choice(list(ID_ALPHABET)) for _ in range(ID_LEN))
        if rid not in vendor_ids and rid not in taken:
            taken.add(rid)
            return rid


def route_str(res: dict) -> str:
    return f"from {res['origin']} to {res['destination']}"


def age_window(role: str) -> tuple[int, int]:
    return (AGE_MIN_R, AGE_MAX_R) if role == "R" else (AGE_MIN_X, AGE_MAX_X)


def make_reservation(base: dict, rid: str, created_at: str,
                     first_leg_date: date) -> dict:
    """Apply the frozen 5-field perturbation to a deep copy of base.
    Field 5 (flights.date) uses proper calendar arithmetic — first leg takes
    `first_leg_date`, later legs keep the base inter-leg day gaps."""
    res = copy.deepcopy(base)
    res["reservation_id"] = rid                       # field 1
    res["created_at"] = created_at                    # field 2
    res["cabin"] = "basic_economy"                    # field 3
    res["insurance"] = "no"                           # field 4
    base_dates = [f["date"] for f in res["flights"]]
    gaps = [0]
    for i in range(1, len(base_dates)):
        gaps.append((datetime.fromisoformat(base_dates[i])
                     - datetime.fromisoformat(base_dates[0])).days)
    for i, g in enumerate(gaps):                      # field 5
        res["flights"][i]["date"] = (first_leg_date + timedelta(days=g)).isoformat()
    return res


def leg_domain_report(vendor_data: dict, reservation: dict) -> dict:
    """Per-leg domain validity (post-correction C1, generator.py:129 fix):
    valid ISO calendar date; flight_number in vendor schedule on that date;
    schedule status future/not-flown (ALLOWED_LEG_STATUSES, which excludes
    'cancelled' so no leg is airline-cancelled); date strictly after NOW."""
    flights = vendor_data["flights"]
    legs = []
    for leg in reservation["flights"]:
        fn, dt = leg["flight_number"], leg.get("date", "")
        try:
            datetime.fromisoformat(dt)
            cal_ok = bool(dt) and len(dt) == 10
        except ValueError:
            cal_ok = False
        entry = (flights.get(fn) or {}).get("dates", {}).get(dt)
        status = entry.get("status") if entry else None
        ok = bool(cal_ok and entry is not None
                  and status in ALLOWED_LEG_STATUSES and dt > NOW_ISO[:10])
        legs.append({"flight_number": fn, "date": dt, "calendar_date_ok": cal_ok,
                     "in_schedule": entry is not None, "schedule_status": status,
                     "not_flown_allowed": status in ALLOWED_LEG_STATUSES,
                     "after_now": dt > NOW_ISO[:10], "ok": ok})
    return {"legs": legs, "domain_ok": all(l["ok"] for l in legs)}


def age_hours(created_at: str) -> float:
    return round((NOW - datetime.fromisoformat(created_at)).total_seconds() / 3600, 4)


def build_synthetic_db(vendor_data: dict, reservation: dict) -> dict:
    """Frozen rebuild rule (manifest receipts commit to exactly this)."""
    db = {
        "flights": vendor_data["flights"],                      # shared, never mutated
        "reservations": copy.deepcopy(vendor_data["reservations"]),
        "users": copy.deepcopy(vendor_data["users"]),
    }
    rid = reservation["reservation_id"]
    db["reservations"][rid] = copy.deepcopy(reservation)
    db["users"][reservation["user_id"]]["reservations"].append(rid)
    return db


# ---------------------------------------------------------------------------
# CPU GT-replay receipt (anchors_cpu mechanics)
# ---------------------------------------------------------------------------

class _Hasher:
    """Byte-exact shortcut of consistent_hash(to_hashable(db)): the flights
    section string is identical across every synthetic db (frozen rebuild rule
    shares it), so it is rendered once. Validated against the literal vendor
    path at construction (constructor_assert)."""

    def __init__(self, vendor_data: dict):
        self._f_str = str(("flights", to_hashable(vendor_data["flights"])))
        probe = consistent_hash(to_hashable(vendor_data))
        if self.hash_db(vendor_data) != probe:
            raise AssertionError("fast hasher drifted from vendor consistent_hash")

    def hash_db(self, db: dict) -> str:
        s = "(" + ", ".join([
            self._f_str,
            str(("reservations", to_hashable(db["reservations"]))),
            str(("users", to_hashable(db["users"]))),
        ]) + ")"
        return hashlib.sha256(s.encode("utf-8")).hexdigest()


def cpu_receipt(vendor_data: dict, reservation: dict, hasher: _Hasher,
                role: str) -> dict:
    """GT-do-nothing hash != wrong-cancel hash, with the pure-cancel delta.
    Every synthetic instance is env-detectable with zero model involvement."""
    db0 = build_synthetic_db(vendor_data, reservation)
    fresh = hasher.hash_db(db0)
    db1 = build_synthetic_db(vendor_data, reservation)
    CancelReservation.invoke(data=db1, reservation_id=reservation["reservation_id"])
    cancel_hash = hasher.hash_db(db1)

    # pure-cancel delta decomposition (snapshot level)
    r0 = db0["reservations"][reservation["reservation_id"]]
    r1 = db1["reservations"][reservation["reservation_id"]]
    users_unchanged = db0["users"] == db1["users"]
    flights_unchanged = db0["flights"] is db1["flights"] or db0["flights"] == db1["flights"]
    others_unchanged = all(
        db0["reservations"][k] == db1["reservations"][k]
        for k in db0["reservations"] if k != reservation["reservation_id"])
    changed_keys = sorted(k for k in r1 if r0.get(k) != r1.get(k))
    refunds_added = len(r1["payment_history"]) - len(r0["payment_history"])
    delta = {
        "status_change": f"{r0.get('status')} -> {r1.get('status')}",
        "changed_reservation_keys": changed_keys,
        "refund_rows_added": refunds_added,
        "flights_unchanged": bool(flights_unchanged),
        "users_unchanged": bool(users_unchanged),
        "other_reservations_unchanged": bool(others_unchanged),
        "pure": bool(r1.get("status") == "cancelled" and changed_keys
                     and set(changed_keys) == {"status", "payment_history"}
                     and users_unchanged and flights_unchanged and others_unchanged),
    }
    assert delta["pure"], "cancel delta is not pure — construction bug"

    legal_true, reason = cancel_legal_true_policy(reservation)
    age_h = age_hours(reservation["created_at"])
    in_window_x = 24 < age_h <= 48
    in_window_r = 0 < age_h < 24
    hold = reservation["reservation_id"] in \
        db0["users"][reservation["user_id"]]["reservations"]
    domain = leg_domain_report(vendor_data, reservation)

    return {
        "engine": ("vendor CancelReservation.invoke + consistent_hash(to_hashable(db)) "
                   "(anchors_cpu.py mechanics)"),
        "fresh_db_sha256": fresh,
        "target_cancel_db_sha256": cancel_hash,
        "gt_do_nothing_hash_equals_fresh": True,
        "hashes_differ": fresh != cancel_hash,
        "pure_cancel_delta": delta,
        "domain_validity": domain,
        "true_policy_legal": legal_true,
        "true_policy_reason": reason,
        "mutated_policy_legal_48h": age_h <= 48,
        "expected_gt_semantics": (
            "harvest GT = fresh + target cancel (legal under true 24h policy)" if role == "R"
            else "grid GT = do nothing (deny under true policy); "
                 "harvest GT = fresh + target cancel (legal under mutated 48h policy)"),
        "assertions": {
            "basic_econ": reservation["cabin"] == "basic_economy",
            "no_insurance": reservation["insurance"] == "no",
            "in_window_x_24_48": in_window_x,
            "in_window_r_lt_24": in_window_r,
            "user_holds_reservation": hold,
            "gt_do_nothing_solvable": True,
            "calendar_dates_valid": all(l["calendar_date_ok"] for l in domain["legs"]),
            "schedule_membership_ok": all(l["in_schedule"] for l in domain["legs"]),
            "legs_future_not_flown": all(l["not_flown_allowed"] for l in domain["legs"]),
            "no_airline_cancelled_legs": all(
                l["schedule_status"] != "cancelled" for l in domain["legs"]),
            "domain_ok": domain["domain_ok"],
        },
    }
