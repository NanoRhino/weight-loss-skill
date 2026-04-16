# /// script
# requires-python = ">=3.6"
# dependencies = []
# ///
"""
Exercise calorie calculator + CRUD for exercise-tracking-planning skill.

Data file: {data_dir}/exercise.json
Format: JSON object keyed by date (YYYY-MM-DD), each value contains
an exercises array and total_calories.

Commands:
  calc             — Estimate calories burned from activity, duration, weight, and intensity.
  interpolate-run  — Running speed/pace → MET via linear interpolation.
  interpolate-cycle — Cycling speed → MET via linear interpolation.
  classify-swim    — Swimming pace → MET classification.
  batch            — Process multiple exercises in one call (JSON array).
  save             — Persist exercise log(s) to data/exercise.json.
  load             — Read exercise entries with optional date filters.
  delete           — Remove exercise entry by date + index.
  update           — Modify an exercise entry by date + index.

Usage:
  python3 exercise-calc.py calc --activity running --weight 75 --duration 30 --speed 10
  python3 exercise-calc.py batch --weight 75 --exercises '[{"activity":"running","duration":30,"speed":10}]'
  python3 exercise-calc.py save --data-dir /path/to/data --tz-offset 28800 \\
      --log '[{"activity":"running","category":"cardio","duration_min":30,"calories":350}]'
  python3 exercise-calc.py load --data-dir /path/to/data --date 2026-03-21
  python3 exercise-calc.py load --data-dir /path/to/data --from 2026-03-17 --to 2026-03-23
  python3 exercise-calc.py load --data-dir /path/to/data --last 7
  python3 exercise-calc.py delete --data-dir /path/to/data --date 2026-03-21 --index 0
  python3 exercise-calc.py update --data-dir /path/to/data --date 2026-03-21 --index 0 \\
      --log '{"activity":"hiking","category":"cardio","duration_min":120,"calories":900}'
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from typing import List, Tuple, Dict, Any, Optional

def _normalize_path(p):
    """Lowercase wechat-dm/wecom-dm segment to avoid case-mismatch directories."""
    import re as _re
    return _re.sub(r'(workspace-(?:wechat|wecom)-dm-)([^/]+)', lambda m: m.group(1) + m.group(2).lower(), p)


# ---------------------------------------------------------------------------
# MET tables (from references/met-table.md)
# ---------------------------------------------------------------------------

RUNNING_ANCHORS = [
    (6.4,  6.0),
    (8.0,  8.3),
    (9.5,  10.0),
    (11.0, 11.5),
    (13.0, 12.8),
    (16.0, 14.5),
]

CYCLING_ANCHORS = [
    (16.0, 6.8),
    (19.0, 8.0),
    (22.0, 10.0),
    (26.0, 12.0),
]

SWIMMING_CLASSIFICATION = [
    (3.0, float("inf"), 4.8,  "low"),
    (2.0, 3.0,          7.0,  "moderate"),
    (0.0, 2.0,          9.8,  "high"),
]

MET_TABLE = {
    ("walking", "low"):           2.8,
    ("walking", "moderate"):      3.8,
    ("walking", "high"):          5.0,
    ("running", "low"):           6.0,
    ("running", "moderate"):      8.3,
    ("running", "high"):          11.5,
    ("running", "very_high"):     14.5,
    ("cycling", "moderate"):      6.8,
    ("cycling", "high"):          10.0,
    ("cycling", "very_high"):     12.0,
    ("cycling_stationary", "moderate"): 6.8,
    ("cycling_stationary", "high"):     10.0,
    ("swimming", "low"):          4.8,
    ("swimming", "moderate"):     7.0,
    ("swimming", "high"):         9.8,
    ("jump_rope", "high"):        10.0,
    ("jump_rope", "very_high"):   12.3,
    ("rowing", "moderate"):       7.0,
    ("rowing", "high"):           10.0,
    ("elliptical", "moderate"):   5.0,
    ("stair_climbing", "moderate"): 7.5,
    ("hiking", "moderate"):       6.0,
    ("hiking", "high"):           8.0,
    ("weight_training", "low"):      3.5,
    ("weight_training", "moderate"): 5.0,
    ("weight_training", "high"):     6.0,
    ("bodyweight", "moderate"):      3.8,
    ("bodyweight", "high"):          5.0,
    ("resistance_bands", "moderate"): 3.5,
    ("stretching", "low"):        2.3,
    ("yoga_hatha", "low"):        2.5,
    ("yoga_vinyasa", "moderate"): 4.0,
    ("yoga_bikram", "high"):      5.0,
    ("pilates", "low"):           3.0,
    ("pilates", "moderate"):      4.0,
    ("foam_rolling", "low"):      2.0,
    ("tai_chi", "low"):           3.0,
    ("hiit", "high"):             8.0,
    ("hiit", "very_high"):        10.0,
    ("tabata", "very_high"):      10.0,
    ("crossfit", "high"):         10.0,
    ("circuit_training", "moderate"): 7.0,
    ("circuit_training", "high"):    9.0,
    ("basketball", "high"):       8.0,
    ("basketball", "moderate"):   4.5,
    ("soccer", "high"):           10.0,
    ("soccer", "moderate"):       7.0,
    ("tennis_singles", "high"):   8.0,
    ("tennis_doubles", "moderate"): 5.0,
    ("badminton", "high"):        7.0,
    ("badminton", "moderate"):    4.5,
    ("table_tennis", "moderate"): 4.0,
    ("volleyball", "high"):       6.0,
    ("volleyball", "moderate"):   3.0,
    ("golf", "low"):              4.3,
    ("rock_climbing", "high"):    8.0,
    ("martial_arts", "high"):     10.3,
    ("boxing", "very_high"):      12.0,
    ("dancing", "moderate"):      5.0,
    ("dancing", "high"):          7.5,
    ("walking_commute", "low"):   3.5,
    ("cycling_commute", "moderate"): 5.5,
    ("stair_climbing_daily", "moderate"): 4.0,
    ("housework_light", "low"):   2.5,
    ("housework_heavy", "moderate"): 4.0,
    ("gardening", "moderate"):    3.8,
    ("moving_heavy", "high"):     6.5,
}

DEFAULT_INTENSITY = {
    "running": "moderate",
    "walking": "moderate",
    "cycling": "moderate",
    "swimming": "moderate",
    "hiking": "moderate",
    "weight_training": "moderate",
    "bodyweight": "moderate",
    "yoga_hatha": "low",
    "yoga_vinyasa": "moderate",
    "pilates": "moderate",
    "hiit": "high",
    "tabata": "very_high",
    "crossfit": "high",
    "basketball": "high",
    "soccer": "high",
    "tennis_singles": "high",
    "tennis_doubles": "moderate",
    "badminton": "moderate",
    "table_tennis": "moderate",
    "volleyball": "moderate",
    "dancing": "moderate",
}


# ---------------------------------------------------------------------------
# Interpolation
# ---------------------------------------------------------------------------

def interpolate(speed, anchors):
    # type: (float, List[Tuple[float, float]]) -> float
    """Linear interpolation between anchor points."""
    if speed <= anchors[0][0]:
        return anchors[0][1]
    if speed >= anchors[-1][0]:
        return anchors[-1][1]

    for i in range(len(anchors) - 1):
        s_lo, met_lo = anchors[i]
        s_hi, met_hi = anchors[i + 1]
        if s_lo <= speed <= s_hi:
            ratio = (speed - s_lo) / (s_hi - s_lo)
            return round(met_lo + ratio * (met_hi - met_lo), 1)

    return anchors[-1][1]


def interpolate_running(speed_kmh):
    # type: (float) -> dict
    met = interpolate(speed_kmh, RUNNING_ANCHORS)
    pace_min_per_km = round(60 / speed_kmh, 2) if speed_kmh > 0 else 0
    return {"speed_kmh": speed_kmh, "pace_min_per_km": pace_min_per_km, "met": met}


def interpolate_cycling(speed_kmh):
    # type: (float) -> dict
    met = interpolate(speed_kmh, CYCLING_ANCHORS)
    return {"speed_kmh": speed_kmh, "met": met}


def classify_swimming(pace_100m_min):
    # type: (float) -> dict
    for lo, hi, met, intensity in SWIMMING_CLASSIFICATION:
        if lo <= pace_100m_min < hi:
            return {"pace_100m_min": pace_100m_min, "intensity": intensity, "met": met}
    return {"pace_100m_min": pace_100m_min, "intensity": "moderate", "met": 7.0}


# ---------------------------------------------------------------------------
# Calorie calculation
# ---------------------------------------------------------------------------

def calc_calories(met, weight_kg, duration_min):
    # type: (float, float, float) -> float
    """Gross calories (kcal) = MET * weight_kg * duration_hours."""
    return round(met * weight_kg * (duration_min / 60), 1)


def calc_net_calories(met, weight_kg, duration_min):
    # type: (float, float, float) -> float
    """Net calories (kcal) = (MET - 1) * weight_kg * duration_hours.

    Net calories represent the additional energy expenditure above resting
    metabolism (BMR). Use this when TDEE is calculated with NEAT-only
    multipliers to avoid double-counting the resting component."""
    net_met = max(met - 1, 0)
    return round(net_met * weight_kg * (duration_min / 60), 1)


def resolve_met(activity, intensity=None, speed=None, pace_100m=None):
    # type: (str, Optional[str], Optional[float], Optional[float]) -> Tuple[float, str]
    """Resolve MET value. Returns (met_value, source_description)."""
    if activity == "running" and speed is not None:
        info = interpolate_running(speed)
        return info["met"], "interpolated from {} km/h".format(speed)

    if activity == "cycling" and speed is not None:
        info = interpolate_cycling(speed)
        return info["met"], "interpolated from {} km/h".format(speed)

    if activity == "swimming" and pace_100m is not None:
        info = classify_swimming(pace_100m)
        return info["met"], "classified from {} min/100m".format(pace_100m)

    if intensity is None:
        intensity = DEFAULT_INTENSITY.get(activity, "moderate")

    key = (activity, intensity)
    if key in MET_TABLE:
        return MET_TABLE[key], "table lookup ({}, {})".format(activity, intensity)

    for int_level in ["moderate", "high", "low"]:
        fallback = (activity, int_level)
        if fallback in MET_TABLE:
            return MET_TABLE[fallback], "fallback ({}, {})".format(activity, int_level)

    return 4.0, "default fallback (unknown activity)"


def calc_exercise(activity, weight_kg, duration_min, intensity=None, speed=None, pace_100m=None):
    # type: (str, float, float, Optional[str], Optional[float], Optional[float]) -> dict
    met, source = resolve_met(activity, intensity, speed, pace_100m)
    calories = calc_calories(met, weight_kg, duration_min)
    net_calories = calc_net_calories(met, weight_kg, duration_min)
    return {
        "activity": activity,
        "duration_min": duration_min,
        "weight_kg": weight_kg,
        "intensity": intensity,
        "speed_kmh": speed,
        "met": met,
        "met_source": source,
        "calories_kcal": calories,
        "net_calories_kcal": net_calories,
        "estimated": True,
    }


def batch_calc(weight_kg, exercises):
    # type: (float, List[dict]) -> dict
    results = []
    total_cal = 0
    total_net_cal = 0
    total_min = 0
    for ex in exercises:
        r = calc_exercise(
            activity=ex.get("activity", "unknown"),
            weight_kg=weight_kg,
            duration_min=ex.get("duration", 30),
            intensity=ex.get("intensity"),
            speed=ex.get("speed"),
            pace_100m=ex.get("pace_100m"),
        )
        results.append(r)
        total_cal += r["calories_kcal"]
        total_net_cal += r["net_calories_kcal"]
        total_min += r["duration_min"]
    return {
        "exercises": results,
        "total_calories_kcal": round(total_cal, 1),
        "total_net_calories_kcal": round(total_net_cal, 1),
        "total_duration_min": total_min,
        "exercise_count": len(results),
    }


# ---------------------------------------------------------------------------
# Data persistence (CRUD for data/exercise.json)
# ---------------------------------------------------------------------------

def data_path(data_dir):
    # type: (str) -> str
    return os.path.join(data_dir, "exercise.json")


def load_data(data_dir):
    # type: (str) -> dict
    p = data_path(data_dir)
    if not os.path.exists(p):
        return {}
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def save_data(data_dir, data):
    # type: (str, dict) -> None
    p = data_path(data_dir)
    d = os.path.dirname(p)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)
    sorted_data = dict(sorted(data.items()))
    with open(p, "w", encoding="utf-8") as f:
        json.dump(sorted_data, f, indent=2, ensure_ascii=False)


def now_date_str(tz_offset_seconds):
    # type: (int) -> str
    tz = timezone(timedelta(seconds=tz_offset_seconds))
    return datetime.now(tz).strftime("%Y-%m-%d")


def cmd_save(args):
    data = load_data(args.data_dir)
    tz_offset = args.tz_offset or 0

    try:
        exercises = json.loads(args.log)
    except (json.JSONDecodeError, ValueError) as e:
        print(json.dumps({"error": "invalid --log JSON: {}".format(e)}), file=sys.stderr)
        sys.exit(1)

    # Normalize: accept single object or array
    if isinstance(exercises, dict):
        exercises = [exercises]

    if not isinstance(exercises, list) or len(exercises) == 0:
        print(json.dumps({"error": "--log must be a non-empty JSON array or object"}), file=sys.stderr)
        sys.exit(1)

    # Determine date: use --date if provided, else from first exercise, else today
    if args.date:
        date_key = args.date
    elif exercises[0].get("date"):
        date_key = exercises[0]["date"]
    else:
        date_key = now_date_str(tz_offset)

    # Get or create the day entry
    day = data.get(date_key, {"exercises": [], "total_calories": 0})

    # Append exercises
    for ex in exercises:
        # Remove 'date' from individual exercise (stored at day level)
        ex.pop("date", None)
        day["exercises"].append(ex)

    # Recalculate total calories
    total = 0
    for ex in day["exercises"]:
        cal = ex.get("calories") or ex.get("calories_burned") or ex.get("total_calories") or 0
        total += cal
    day["total_calories"] = total

    data[date_key] = day
    save_data(args.data_dir, data)

    result = {
        "action": "saved",
        "date": date_key,
        "added": len(exercises),
        "day_total_exercises": len(day["exercises"]),
        "day_total_calories": total,
    }
    print(json.dumps(result, ensure_ascii=False))


def cmd_load(args):
    data = load_data(args.data_dir)
    if not data:
        print(json.dumps([], ensure_ascii=False))
        return

    # Filter by date range
    entries = sorted(data.items())

    if args.date:
        entries = [(k, v) for k, v in entries if k == args.date]
    else:
        if args.from_date:
            entries = [(k, v) for k, v in entries if k >= args.from_date]
        if args.to_date:
            entries = [(k, v) for k, v in entries if k <= args.to_date]

    # Limit to last N days
    if args.last:
        entries = entries[-args.last:]

    result = []
    for date_key, day in entries:
        result.append({
            "date": date_key,
            "exercises": day.get("exercises", []),
            "total_calories": day.get("total_calories", 0),
        })

    print(json.dumps(result, ensure_ascii=False))


def cmd_delete(args):
    data = load_data(args.data_dir)

    if args.date not in data:
        print(json.dumps({"error": "No exercises found for date: {}".format(args.date)}))
        sys.exit(1)

    day = data[args.date]

    if args.index is not None:
        # Delete specific exercise by index
        exercises = day.get("exercises", [])
        if args.index < 0 or args.index >= len(exercises):
            print(json.dumps({"error": "Index {} out of range (0-{})".format(args.index, len(exercises) - 1)}))
            sys.exit(1)

        removed = exercises.pop(args.index)

        if len(exercises) == 0:
            # No exercises left, remove the whole day
            del data[args.date]
            save_data(args.data_dir, data)
            print(json.dumps({"action": "deleted_day", "date": args.date, "removed": removed}, ensure_ascii=False))
        else:
            # Recalculate total
            total = sum(ex.get("calories") or ex.get("calories_burned") or ex.get("total_calories") or 0 for ex in exercises)
            day["total_calories"] = total
            save_data(args.data_dir, data)
            print(json.dumps({
                "action": "deleted_exercise",
                "date": args.date,
                "index": args.index,
                "removed": removed,
                "remaining": len(exercises),
                "day_total_calories": total,
            }, ensure_ascii=False))
    else:
        # Delete entire day
        removed = data.pop(args.date)
        save_data(args.data_dir, data)
        print(json.dumps({
            "action": "deleted_day",
            "date": args.date,
            "exercises_removed": len(removed.get("exercises", [])),
        }, ensure_ascii=False))


def cmd_update(args):
    data = load_data(args.data_dir)

    if args.date not in data:
        print(json.dumps({"error": "No exercises found for date: {}".format(args.date)}))
        sys.exit(1)

    day = data[args.date]
    exercises = day.get("exercises", [])

    if args.index < 0 or args.index >= len(exercises):
        print(json.dumps({"error": "Index {} out of range (0-{})".format(args.index, len(exercises) - 1)}))
        sys.exit(1)

    try:
        updated = json.loads(args.log)
    except (json.JSONDecodeError, ValueError) as e:
        print(json.dumps({"error": "invalid --log JSON: {}".format(e)}), file=sys.stderr)
        sys.exit(1)

    # Remove date from updated entry (stored at day level)
    updated.pop("date", None)

    old = exercises[args.index]
    exercises[args.index] = updated

    # Recalculate total
    total = sum(ex.get("calories") or ex.get("calories_burned") or ex.get("total_calories") or 0 for ex in exercises)
    day["total_calories"] = total

    save_data(args.data_dir, data)
    print(json.dumps({
        "action": "updated",
        "date": args.date,
        "index": args.index,
        "old": old,
        "new": updated,
        "day_total_calories": total,
    }, ensure_ascii=False))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Exercise calorie calculator + CRUD")
    sub = parser.add_subparsers(dest="cmd")

    # --- calc ---
    p = sub.add_parser("calc", help="Estimate calories burned")
    p.add_argument("--activity", required=True, help="Exercise type")
    p.add_argument("--weight", type=float, required=True, help="Body weight in kg")
    p.add_argument("--duration", type=float, required=True, help="Duration in minutes")
    p.add_argument("--intensity", choices=["low", "moderate", "high", "very_high"], default=None)
    p.add_argument("--speed", type=float, default=None, help="Speed in km/h (for running, cycling)")
    p.add_argument("--pace-100m", type=float, default=None, help="Pace per 100m in minutes (for swimming)")

    # --- interpolate-run ---
    p = sub.add_parser("interpolate-run", help="Running speed -> MET")
    p.add_argument("--speed", type=float, required=True, help="km/h")

    # --- interpolate-cycle ---
    p = sub.add_parser("interpolate-cycle", help="Cycling speed -> MET")
    p.add_argument("--speed", type=float, required=True, help="km/h")

    # --- classify-swim ---
    p = sub.add_parser("classify-swim", help="Swimming pace -> MET")
    p.add_argument("--pace-100m", type=float, required=True, help="Minutes per 100m")

    # --- batch ---
    p = sub.add_parser("batch", help="Process multiple exercises")
    p.add_argument("--weight", type=float, required=True, help="kg")
    p.add_argument("--exercises", type=str, required=True, help="JSON array of exercises")

    # --- save ---
    p = sub.add_parser("save", help="Save exercise log to data/exercise.json")
    p.add_argument("--data-dir", required=True, help="Path to data directory")
    p.add_argument("--log", required=True, help="JSON array or object of exercise(s)")
    p.add_argument("--date", default=None, help="Date YYYY-MM-DD (default: today)")
    p.add_argument("--tz-offset", type=int, default=0, help="Timezone offset in seconds")

    # --- load ---
    p = sub.add_parser("load", help="Load exercise entries")
    p.add_argument("--data-dir", required=True, help="Path to data directory")
    p.add_argument("--date", default=None, help="Specific date YYYY-MM-DD")
    p.add_argument("--from", dest="from_date", default=None, help="Start date YYYY-MM-DD")
    p.add_argument("--to", dest="to_date", default=None, help="End date YYYY-MM-DD")
    p.add_argument("--last", type=int, default=None, help="Last N days with data")

    # --- delete ---
    p = sub.add_parser("delete", help="Delete exercise entry")
    p.add_argument("--data-dir", required=True, help="Path to data directory")
    p.add_argument("--date", required=True, help="Date YYYY-MM-DD")
    p.add_argument("--index", type=int, default=None, help="Exercise index (0-based); omit to delete entire day")

    # --- update ---
    p = sub.add_parser("update", help="Update exercise entry")
    p.add_argument("--data-dir", required=True, help="Path to data directory")
    p.add_argument("--date", required=True, help="Date YYYY-MM-DD")
    p.add_argument("--index", type=int, required=True, help="Exercise index (0-based)")
    p.add_argument("--log", required=True, help="Updated exercise JSON object")

    args = parser.parse_args()
    args.data_dir = _normalize_path(args.data_dir)
    if not args.cmd:
        parser.print_help()
        sys.exit(1)

    if args.cmd == "calc":
        result = calc_exercise(args.activity, args.weight, args.duration, args.intensity, args.speed, getattr(args, 'pace_100m', None))
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.cmd == "interpolate-run":
        print(json.dumps(interpolate_running(args.speed), ensure_ascii=False, indent=2))
    elif args.cmd == "interpolate-cycle":
        print(json.dumps(interpolate_cycling(args.speed), ensure_ascii=False, indent=2))
    elif args.cmd == "classify-swim":
        print(json.dumps(classify_swimming(getattr(args, 'pace_100m', None)), ensure_ascii=False, indent=2))
    elif args.cmd == "batch":
        try:
            exercises = json.loads(args.exercises)
        except (json.JSONDecodeError, ValueError) as e:
            print("Error: invalid --exercises JSON: {}".format(e), file=sys.stderr)
            sys.exit(1)
        print(json.dumps(batch_calc(args.weight, exercises), ensure_ascii=False, indent=2))
    elif args.cmd == "save":
        cmd_save(args)
    elif args.cmd == "load":
        cmd_load(args)
    elif args.cmd == "delete":
        cmd_delete(args)
    elif args.cmd == "update":
        cmd_update(args)


if __name__ == "__main__":
    main()
