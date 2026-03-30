# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
Meal place profile manager for diet-tracking-analysis skill.

Manages workday meal venue collection, state tracking, and drift detection.
Data file: {workspaceDir}/data/meal-place-profile.json

Commands:
  load         — Load the full profile (create with defaults if missing).
  check        — Check whether to ask venue for a meal (returns action + options, auto-increments ask_count).
  save-place   — Save a venue for a meal slot.
  record-drift — Record an inferred venue and update drift counters.
  reset-drift  — Reset drift counters for a meal (after user confirms or denies).

Usage:
  python3 meal-place.py load --data-dir /path/to/data
  python3 meal-place.py check --data-dir /path/to/data --meal lunch --weekday 2
  python3 meal-place.py save-place --data-dir /path/to/data --meal lunch --place cafeteria
  python3 meal-place.py record-drift --data-dir /path/to/data --meal lunch --inferred takeout
  python3 meal-place.py reset-drift --data-dir /path/to/data --meal lunch
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone


VALID_MEALS = ("breakfast", "lunch", "dinner")
VALID_PLACES = ("home", "cafeteria", "takeout", "restaurant", "bring_meal", "other")
MAX_ASK_COUNT = 3
DRIFT_THRESHOLD = 3

# Default top-2 options per meal for the pick-two prompt
DEFAULT_TOP2 = {
    "breakfast": ["home", "cafeteria"],
    "lunch": ["cafeteria", "restaurant"],
    "dinner": ["home", "restaurant"],
}

FILE_NAME = "meal-place-profile.json"


def _empty_profile() -> dict:
    """Return a fresh empty profile."""
    return {
        "workday_meal_place_profile": {
            m: {"place": None, "updated_at": None} for m in VALID_MEALS
        },
        "_collection_state": {
            m: {"ask_count": 0} for m in VALID_MEALS
        },
        "_drift_detection": {
            m: {"consecutive_mismatches": 0, "last_inferred": None}
            for m in VALID_MEALS
        },
    }


def _load(data_dir: str) -> dict:
    """Load profile from disk, creating with defaults if missing."""
    path = os.path.join(data_dir, FILE_NAME)
    if os.path.exists(path):
        with open(path) as f:
            data = json.load(f)
        # Back-fill any missing meals (forward compatibility)
        for section_key, factory in [
            ("workday_meal_place_profile", lambda: {"place": None, "updated_at": None}),
            ("_collection_state", lambda: {"ask_count": 0}),
            ("_drift_detection", lambda: {"consecutive_mismatches": 0, "last_inferred": None}),
        ]:
            section = data.setdefault(section_key, {})
            for m in VALID_MEALS:
                if m not in section:
                    section[m] = factory()
        return data
    return _empty_profile()


def _save(data_dir: str, data: dict) -> None:
    """Persist profile to disk."""
    os.makedirs(data_dir, exist_ok=True)
    path = os.path.join(data_dir, FILE_NAME)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_load(args):
    data = _load(args.data_dir)
    print(json.dumps(data, indent=2, ensure_ascii=False))


def cmd_check(args):
    """Determine what action to take for a meal log.

    Returns one of:
      - {"action": "skip", "reason": "weekend"}
      - {"action": "skip", "reason": "already_collected"}
      - {"action": "skip", "reason": "gave_up"}
      - {"action": "ask", "mode": "confirm", "inferred": "takeout",
         "options": ["home", "takeout"], "ask_count": 1}
      - {"action": "ask", "mode": "pick_two",
         "options": ["home", "takeout"], "ask_count": 1}
      - {"action": "drift_confirm", "current_place": "cafeteria",
         "inferred_place": "takeout", "consecutive_mismatches": 3}
      - {"action": "none", "reason": "no_drift"}
    """
    # weekday: 0=Mon, 6=Sun
    if args.weekday >= 5:
        print(json.dumps({"action": "skip", "reason": "weekend"}))
        return

    data = _load(args.data_dir)
    meal = args.meal
    profile = data["workday_meal_place_profile"][meal]
    state = data["_collection_state"][meal]
    drift = data["_drift_detection"][meal]

    # Case 1: place is null → check if we should ask
    if profile["place"] is None:
        if state["ask_count"] >= MAX_ASK_COUNT:
            print(json.dumps({"action": "skip", "reason": "gave_up"}))
            return
        # Should ask — increment ask_count now
        state["ask_count"] += 1
        _save(args.data_dir, data)
        # Mode depends on whether venue was inferred and confidence level
        defaults = DEFAULT_TOP2.get(meal, ["home", "takeout"])
        inferred = getattr(args, "inferred", None)
        confidence = getattr(args, "confidence", None)
        result = {
            "action": "ask",
            "ask_count": state["ask_count"],
        }
        if inferred and inferred in VALID_PLACES and confidence == "high":
            # High confidence → confirm mode
            result["mode"] = "confirm"
            result["inferred"] = inferred
            result["options"] = defaults
        elif inferred and inferred in VALID_PLACES:
            # Low confidence → pick_two with inferred as first option
            result["mode"] = "pick_two"
            if inferred in defaults:
                options = [inferred] + [o for o in defaults if o != inferred]
            else:
                options = [inferred, defaults[0]]
            result["options"] = options
        else:
            # No inference → pick_two with defaults
            result["mode"] = "pick_two"
            result["options"] = defaults
        print(json.dumps(result))
        return

    # Case 2: place is set → check drift
    if drift["consecutive_mismatches"] >= DRIFT_THRESHOLD:
        print(json.dumps({
            "action": "drift_confirm",
            "current_place": profile["place"],
            "inferred_place": drift["last_inferred"],
            "consecutive_mismatches": drift["consecutive_mismatches"],
        }))
        return

    print(json.dumps({"action": "none", "reason": "no_drift"}))


def cmd_save_place(args):
    """Save a venue for a meal slot."""
    if args.place not in VALID_PLACES:
        print(json.dumps({"error": f"Invalid place: {args.place}. Must be one of {VALID_PLACES}"}),
              file=sys.stderr)
        sys.exit(1)

    data = _load(args.data_dir)
    meal = args.meal
    data["workday_meal_place_profile"][meal] = {
        "place": args.place,
        "updated_at": _now_iso(),
    }
    # ask_count preserved but no longer matters once place is set
    # Reset drift on explicit save
    data["_drift_detection"][meal] = {"consecutive_mismatches": 0, "last_inferred": None}
    _save(args.data_dir, data)
    print(json.dumps(data, indent=2, ensure_ascii=False))



def cmd_record_drift(args):
    """Record an inferred venue and update drift counters."""
    data = _load(args.data_dir)
    meal = args.meal
    profile = data["workday_meal_place_profile"][meal]
    drift = data["_drift_detection"][meal]

    if profile["place"] is None:
        # No baseline to compare against
        print(json.dumps({"action": "skip", "reason": "no_baseline"}))
        return

    if args.inferred == profile["place"]:
        # Match → reset
        drift["consecutive_mismatches"] = 0
        drift["last_inferred"] = None
    else:
        # Mismatch → increment
        drift["consecutive_mismatches"] += 1
        drift["last_inferred"] = args.inferred

    _save(args.data_dir, data)
    print(json.dumps({
        "meal": meal,
        "current_place": profile["place"],
        "inferred": args.inferred,
        "consecutive_mismatches": drift["consecutive_mismatches"],
        "should_confirm": drift["consecutive_mismatches"] >= DRIFT_THRESHOLD,
    }))


def cmd_reset_drift(args):
    """Reset drift counters for a meal."""
    data = _load(args.data_dir)
    meal = args.meal
    data["_drift_detection"][meal] = {"consecutive_mismatches": 0, "last_inferred": None}
    _save(args.data_dir, data)
    print(json.dumps({"meal": meal, "drift_reset": True}))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Meal place profile manager")
    sub = parser.add_subparsers(dest="command", required=True)

    # load
    p_load = sub.add_parser("load")
    p_load.add_argument("--data-dir", required=True)

    # check
    p_check = sub.add_parser("check")
    p_check.add_argument("--data-dir", required=True)
    p_check.add_argument("--meal", required=True, choices=VALID_MEALS)
    p_check.add_argument("--weekday", required=True, type=int, help="0=Mon, 6=Sun")
    p_check.add_argument("--inferred", default=None, help="Venue inferred from photo/text context (optional)")
    p_check.add_argument("--confidence", default=None, choices=["high", "low"], help="Confidence of the inference (high → confirm, low → pick_two with inferred)")

    # save-place
    p_save = sub.add_parser("save-place")
    p_save.add_argument("--data-dir", required=True)
    p_save.add_argument("--meal", required=True, choices=VALID_MEALS)
    p_save.add_argument("--place", required=True)

    # record-drift
    p_drift = sub.add_parser("record-drift")
    p_drift.add_argument("--data-dir", required=True)
    p_drift.add_argument("--meal", required=True, choices=VALID_MEALS)
    p_drift.add_argument("--inferred", required=True)

    # reset-drift
    p_reset = sub.add_parser("reset-drift")
    p_reset.add_argument("--data-dir", required=True)
    p_reset.add_argument("--meal", required=True, choices=VALID_MEALS)

    args = parser.parse_args()
    {
        "load": cmd_load,
        "check": cmd_check,
        "save-place": cmd_save_place,
        "record-drift": cmd_record_drift,
        "reset-drift": cmd_reset_drift,
    }[args.command](args)


if __name__ == "__main__":
    main()
