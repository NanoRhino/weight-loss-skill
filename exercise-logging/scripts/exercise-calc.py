# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
Exercise calorie calculator for exercise-logging skill.

Codifies the MET-based calorie estimation and continuous mapping
(linear interpolation for running, cycling, swimming) from
references/met-table.md into executable commands.

Commands:
  calc             — Estimate calories burned from activity, duration, weight, and intensity.
  interpolate-run  — Running speed/pace → MET via linear interpolation.
  interpolate-cycle — Cycling speed → MET via linear interpolation.
  classify-swim    — Swimming pace → MET classification.
  batch            — Process multiple exercises in one call (JSON array).

Usage:
  python3 exercise-calc.py calc --activity running --weight 75 --duration 30 --speed 10
  python3 exercise-calc.py calc --activity cycling --weight 75 --duration 45 --speed 20
  python3 exercise-calc.py calc --activity swimming --weight 75 --duration 30 --pace-100m 2.5
  python3 exercise-calc.py calc --activity basketball --weight 75 --duration 60 --intensity high
  python3 exercise-calc.py interpolate-run --speed 10
  python3 exercise-calc.py interpolate-cycle --speed 20
  python3 exercise-calc.py classify-swim --pace-100m 2.5
  python3 exercise-calc.py batch --weight 75 --exercises '[{"activity":"running","duration":30,"speed":10},{"activity":"yoga","duration":20,"intensity":"moderate"}]'
"""

import argparse
import json
import sys

# ---------------------------------------------------------------------------
# MET tables (from references/met-table.md)
# ---------------------------------------------------------------------------

# Running: speed (km/h) → MET anchor points for linear interpolation
RUNNING_ANCHORS = [
    (6.4,  6.0),
    (8.0,  8.3),
    (9.5,  10.0),
    (11.0, 11.5),
    (13.0, 12.8),
    (16.0, 14.5),
]

# Cycling: speed (km/h) → MET
CYCLING_ANCHORS = [
    (16.0, 6.8),
    (19.0, 8.0),
    (22.0, 10.0),
    (26.0, 12.0),
]

# Swimming: pace per 100m (minutes) → MET
SWIMMING_CLASSIFICATION = [
    (3.0, float("inf"), 4.8,  "low"),       # > 3:00 per 100m
    (2.0, 3.0,          7.0,  "moderate"),   # 2:00–3:00
    (0.0, 2.0,          9.8,  "high"),       # < 2:00
]

# Discrete MET lookup: (category, intensity) → MET
# From references/met-table.md
MET_TABLE = {
    # Cardio
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
    # Strength
    ("weight_training", "low"):      3.5,
    ("weight_training", "moderate"): 5.0,
    ("weight_training", "high"):     6.0,
    ("bodyweight", "moderate"):      3.8,
    ("bodyweight", "high"):          5.0,
    ("resistance_bands", "moderate"): 3.5,
    # Flexibility
    ("stretching", "low"):        2.3,
    ("yoga_hatha", "low"):        2.5,
    ("yoga_vinyasa", "moderate"): 4.0,
    ("yoga_bikram", "high"):      5.0,
    ("pilates", "low"):           3.0,
    ("pilates", "moderate"):      4.0,
    ("foam_rolling", "low"):      2.0,
    ("tai_chi", "low"):           3.0,
    # HIIT
    ("hiit", "high"):             8.0,
    ("hiit", "very_high"):        10.0,
    ("tabata", "very_high"):      10.0,
    ("crossfit", "high"):         10.0,
    ("circuit_training", "moderate"): 7.0,
    ("circuit_training", "high"):    9.0,
    # Sports
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
    # Daily activities
    ("walking_commute", "low"):   3.5,
    ("cycling_commute", "moderate"): 5.5,
    ("stair_climbing_daily", "moderate"): 4.0,
    ("housework_light", "low"):   2.5,
    ("housework_heavy", "moderate"): 4.0,
    ("gardening", "moderate"):    3.8,
    ("moving_heavy", "high"):     6.5,
}

# Default intensity when not specified
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

def interpolate(speed: float, anchors: list[tuple[float, float]]) -> float:
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


def interpolate_running(speed_kmh: float) -> dict:
    met = interpolate(speed_kmh, RUNNING_ANCHORS)
    pace_min_per_km = round(60 / speed_kmh, 2) if speed_kmh > 0 else 0
    return {
        "speed_kmh": speed_kmh,
        "pace_min_per_km": pace_min_per_km,
        "met": met,
    }


def interpolate_cycling(speed_kmh: float) -> dict:
    met = interpolate(speed_kmh, CYCLING_ANCHORS)
    return {"speed_kmh": speed_kmh, "met": met}


def classify_swimming(pace_100m_min: float) -> dict:
    for lo, hi, met, intensity in SWIMMING_CLASSIFICATION:
        if lo <= pace_100m_min < hi:
            return {
                "pace_100m_min": pace_100m_min,
                "intensity": intensity,
                "met": met,
            }
    return {"pace_100m_min": pace_100m_min, "intensity": "moderate", "met": 7.0}


# ---------------------------------------------------------------------------
# Calorie calculation
# ---------------------------------------------------------------------------

def calc_calories(met: float, weight_kg: float, duration_min: float) -> float:
    """Calories (kcal) = MET × weight_kg × duration_hours."""
    return round(met * weight_kg * (duration_min / 60), 1)


def resolve_met(activity: str, intensity: str = None,
                speed: float = None, pace_100m: float = None) -> tuple[float, str]:
    """Resolve MET value from activity + optional speed/intensity.

    Returns (met_value, source_description).
    """
    # Speed-based interpolation for specific activities
    if activity == "running" and speed is not None:
        info = interpolate_running(speed)
        return info["met"], f"interpolated from {speed} km/h"

    if activity == "cycling" and speed is not None:
        info = interpolate_cycling(speed)
        return info["met"], f"interpolated from {speed} km/h"

    if activity == "swimming" and pace_100m is not None:
        info = classify_swimming(pace_100m)
        return info["met"], f"classified from {pace_100m} min/100m"

    # Discrete MET lookup
    if intensity is None:
        intensity = DEFAULT_INTENSITY.get(activity, "moderate")

    key = (activity, intensity)
    if key in MET_TABLE:
        return MET_TABLE[key], f"table lookup ({activity}, {intensity})"

    # Fallback: try just activity with moderate
    for int_level in ["moderate", "high", "low"]:
        fallback = (activity, int_level)
        if fallback in MET_TABLE:
            return MET_TABLE[fallback], f"fallback ({activity}, {int_level})"

    return 4.0, "default fallback (unknown activity)"


def calc_exercise(activity: str, weight_kg: float, duration_min: float,
                  intensity: str = None, speed: float = None,
                  pace_100m: float = None) -> dict:
    """Full exercise calorie calculation."""
    met, source = resolve_met(activity, intensity, speed, pace_100m)
    calories = calc_calories(met, weight_kg, duration_min)
    return {
        "activity": activity,
        "duration_min": duration_min,
        "weight_kg": weight_kg,
        "intensity": intensity,
        "speed_kmh": speed,
        "met": met,
        "met_source": source,
        "calories_kcal": calories,
        "estimated": True,
    }


def batch_calc(weight_kg: float, exercises: list[dict]) -> dict:
    """Process multiple exercises."""
    results = []
    total_cal = 0
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
        total_min += r["duration_min"]

    return {
        "exercises": results,
        "total_calories_kcal": round(total_cal, 1),
        "total_duration_min": total_min,
        "exercise_count": len(results),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Exercise calorie calculator")
    sub = parser.add_subparsers(dest="cmd")

    # --- calc ---
    p = sub.add_parser("calc", help="Estimate calories burned")
    p.add_argument("--activity", required=True, help="Exercise type")
    p.add_argument("--weight", type=float, required=True, help="Body weight in kg")
    p.add_argument("--duration", type=float, required=True, help="Duration in minutes")
    p.add_argument("--intensity", choices=["low", "moderate", "high", "very_high"],
                   default=None)
    p.add_argument("--speed", type=float, default=None,
                   help="Speed in km/h (for running, cycling)")
    p.add_argument("--pace-100m", type=float, default=None,
                   help="Pace per 100m in minutes (for swimming)")

    # --- interpolate-run ---
    p = sub.add_parser("interpolate-run", help="Running speed → MET")
    p.add_argument("--speed", type=float, required=True, help="km/h")

    # --- interpolate-cycle ---
    p = sub.add_parser("interpolate-cycle", help="Cycling speed → MET")
    p.add_argument("--speed", type=float, required=True, help="km/h")

    # --- classify-swim ---
    p = sub.add_parser("classify-swim", help="Swimming pace → MET")
    p.add_argument("--pace-100m", type=float, required=True,
                   help="Minutes per 100m")

    # --- batch ---
    p = sub.add_parser("batch", help="Process multiple exercises")
    p.add_argument("--weight", type=float, required=True, help="kg")
    p.add_argument("--exercises", type=str, required=True,
                   help='JSON array of exercises')

    args = parser.parse_args()
    if not args.cmd:
        parser.print_help()
        sys.exit(1)

    result = None

    if args.cmd == "calc":
        result = calc_exercise(
            args.activity, args.weight, args.duration,
            args.intensity, args.speed, args.pace_100m,
        )

    elif args.cmd == "interpolate-run":
        result = interpolate_running(args.speed)

    elif args.cmd == "interpolate-cycle":
        result = interpolate_cycling(args.speed)

    elif args.cmd == "classify-swim":
        result = classify_swimming(args.pace_100m)

    elif args.cmd == "batch":
        try:
            exercises = json.loads(args.exercises)
        except json.JSONDecodeError as e:
            print(f"Error: invalid --exercises JSON: {e}", file=sys.stderr)
            sys.exit(1)
        result = batch_calc(args.weight, exercises)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
