# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
Nutrition calculator for diet-tracking-analysis skill.

Commands:
  target       — Compute daily macro targets from weight & calorie goal.
  analyze      — Compute cumulative intake, compare with targets, output status.
  save         — Persist a meal record to today's log file.
  load         — Load today's (or a given date's) meal records.
  evaluate     — Evaluate cumulative intake at a meal checkpoint (range-based).
  check-missing — Check which main meals are missing before the current meal.

Usage:
  python3 nutrition-calc.py target  --weight 65 --cal 1500 [--meals 3]
  python3 nutrition-calc.py analyze --weight 65 --cal 1500 --meals 3 \
      --log '[{"name":"breakfast","cal":379,"p":24,"c":45,"f":12}]'
  python3 nutrition-calc.py save --data-dir /path/to/data \
      --meal '{"name":"breakfast","cal":379,"p":24,"c":45,"f":12,"foods":[{"name":"boiled eggs x2","cal":144}]}'
  python3 nutrition-calc.py load --data-dir /path/to/data [--date 2026-02-27]
  python3 nutrition-calc.py evaluate --weight 65 --cal 1500 --meals 3 \
      --current-meal lunch --log '[...]'
  python3 nutrition-calc.py check-missing --meals 3 --current-meal lunch --log '[...]'
"""

import argparse
import json
import os
import sys
from datetime import date


# Meal blocks define the structure and percentage allocation for each checkpoint.
# Each block has a label, percentage of daily targets, and which meal types belong to it.

MEAL_BLOCKS_3 = [
    {"label": "breakfast", "pct": 30, "meals": ["breakfast", "snack_am"]},
    {"label": "lunch",     "pct": 40, "meals": ["lunch", "snack_pm"]},
    {"label": "dinner",    "pct": 30, "meals": ["dinner"]},
]

MEAL_BLOCKS_2 = [
    {"label": "meal_1", "pct": 50, "meals": ["meal_1", "snack_1"]},
    {"label": "meal_2", "pct": 50, "meals": ["meal_2", "snack_2"]},
]


def get_meal_blocks(meals: int) -> list:
    return MEAL_BLOCKS_3 if meals == 3 else MEAL_BLOCKS_2


def find_block_index(meal_name: str, meals: int) -> int:
    """Find which block a meal type belongs to."""
    for i, block in enumerate(get_meal_blocks(meals)):
        if meal_name in block["meals"]:
            return i
    return None


def calc_targets(weight: float, daily_cal: int, meals: int = 3) -> dict:
    """Compute daily macro targets with min/max ranges."""
    protein = round(weight * 1.4, 1)
    protein_lo = round(weight * 1.2, 1)
    protein_hi = round(weight * 1.6, 1)

    fat = round(daily_cal * 0.275 / 9, 1)
    fat_lo = round(daily_cal * 0.20 / 9, 1)
    fat_hi = round(daily_cal * 0.35 / 9, 1)

    carb = round((daily_cal - protein * 4 - fat * 9) / 4, 1)
    carb_lo = round((daily_cal - protein_hi * 4 - fat_hi * 9) / 4, 1)
    carb_hi = round((daily_cal - protein_lo * 4 - fat_lo * 9) / 4, 1)

    # Daily calorie range: ±100 kcal
    cal_lo = daily_cal - 100
    cal_hi = daily_cal + 100

    blocks = get_meal_blocks(meals)
    alloc = []
    for b in blocks:
        alloc.append({"meal": b["label"], "pct": b["pct"],
                       "cal": round(daily_cal * b["pct"] / 100)})

    return {
        "daily_cal": daily_cal,
        "cal_range": {"min": cal_lo, "max": cal_hi},
        "weight": weight,
        "meals": meals,
        "protein": {"target": protein, "min": protein_lo, "max": protein_hi},
        "fat": {"target": fat, "min": fat_lo, "max": fat_hi},
        "carb": {"target": carb, "min": carb_lo, "max": carb_hi},
        "allocation": alloc,
    }


def _in_range(value: float, lo: float, hi: float) -> bool:
    """Check if a value falls within [lo, hi]."""
    return lo <= value <= hi


def _range_status(value: float, lo: float, hi: float) -> str:
    """Return status label based on range comparison."""
    if value < lo:
        return "low"
    elif value > hi:
        return "high"
    return "on_track"


def analyze(weight: float, daily_cal: int, meals: int, log: list) -> dict:
    """Analyze cumulative intake against daily targets."""
    targets = calc_targets(weight, daily_cal, meals)

    cum = {"cal": 0, "p": 0, "c": 0, "f": 0}
    meal_details = []
    for entry in log:
        cum["cal"] += entry.get("cal", 0)
        cum["p"] += entry.get("p", 0)
        cum["c"] += entry.get("c", 0)
        cum["f"] += entry.get("f", 0)
        meal_details.append({
            "name": entry.get("name", ""),
            "cal": entry.get("cal", 0),
            "p": entry.get("p", 0),
            "c": entry.get("c", 0),
            "f": entry.get("f", 0),
        })

    for k in cum:
        cum[k] = round(cum[k], 1)

    pct_cal = round(cum["cal"] / daily_cal * 100) if daily_cal else 0
    remain = {
        "cal": round(daily_cal - cum["cal"], 1),
        "p": round(targets["protein"]["target"] - cum["p"], 1),
        "c": round(targets["carb"]["target"] - cum["c"], 1),
        "f": round(targets["fat"]["target"] - cum["f"], 1),
    }

    status = {
        "cal": _range_status(cum["cal"], targets["cal_range"]["min"], targets["cal_range"]["max"]),
        "p": _range_status(cum["p"], targets["protein"]["min"], targets["protein"]["max"]),
        "c": _range_status(cum["c"], targets["carb"]["min"], targets["carb"]["max"]),
        "f": _range_status(cum["f"], targets["fat"]["min"], targets["fat"]["max"]),
    }

    return {
        "targets": targets,
        "meals": meal_details,
        "cumulative": cum,
        "pct_cal": pct_cal,
        "remaining": remain,
        "status": status,
    }


def get_log_path(data_dir: str, day: str = None) -> str:
    day = day or date.today().isoformat()
    return os.path.join(data_dir, f"{day}.json")


def save_meal(data_dir: str, meal: dict, day: str = None) -> dict:
    """Save a meal to the daily log. Same meal name overwrites (supports corrections)."""
    os.makedirs(data_dir, exist_ok=True)
    path = get_log_path(data_dir, day)

    existing: list = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            existing = json.load(f)

    meal_name = meal.get("name", "")
    replaced = False
    for i, m in enumerate(existing):
        if m.get("name") == meal_name:
            existing[i] = meal
            replaced = True
            break
    if not replaced:
        existing.append(meal)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    return {"saved": True, "file": path, "meals_count": len(existing), "meals": existing}


def load_meals(data_dir: str, day: str = None) -> dict:
    """Load all meals for a given day."""
    path = get_log_path(data_dir, day)
    if not os.path.exists(path):
        return {"date": day or date.today().isoformat(), "meals": [], "meals_count": 0}
    with open(path, "r", encoding="utf-8") as f:
        meals = json.load(f)
    return {"date": day or date.today().isoformat(), "meals": meals, "meals_count": len(meals)}


def _sum_macros(meal_list: list) -> dict:
    s = {"cal": 0, "p": 0, "c": 0, "f": 0}
    for m in meal_list:
        s["cal"] += m.get("cal", 0)
        s["p"] += m.get("p", 0)
        s["c"] += m.get("c", 0)
        s["f"] += m.get("f", 0)
    return {k: round(v, 1) for k, v in s.items()}


def evaluate(weight: float, daily_cal: int, meals: int,
             current_meal: str, log: list,
             assumed_meals: list = None) -> dict:
    """Evaluate cumulative intake at the checkpoint for *current_meal*.

    Uses range-based evaluation:
    - Each checkpoint scales daily min/max ranges by the checkpoint percentage.
    - Adjustment is needed when: calories outside checkpoint cal range
      OR 2+ macros outside their checkpoint ranges.

    Checkpoint rules (3-meal, 30:40:30):
      - Evaluating breakfast/snack_am block → compare to 30% of daily ranges
      - Evaluating lunch/snack_pm block    → compare to 70% of daily ranges (cumulative)
      - Evaluating dinner block            → compare to 100% of daily ranges

    *assumed_meals*: meals the user forgot; their standard ratio of daily targets
    (e.g. forgotten lunch in 30:40:30 = 40% of daily targets, NOT the cumulative checkpoint).
    Included in suggestions but NOT in progress/actual numbers.
    """
    targets = calc_targets(weight, daily_cal, meals)
    blocks = get_meal_blocks(meals)

    block_idx = find_block_index(current_meal, meals)
    if block_idx is None:
        return {"error": f"Unknown meal name: {current_meal}"}

    # Cumulative checkpoint percentage
    checkpoint_pct = sum(blocks[i]["pct"] for i in range(block_idx + 1))

    # All meal types included up to this checkpoint
    checkpoint_meal_names: set[str] = set()
    for i in range(block_idx + 1):
        checkpoint_meal_names.update(blocks[i]["meals"])

    logged_names = {m.get("name", "") for m in log}

    # Only count meals that belong to the checkpoint window
    checkpoint_log = [m for m in log if m.get("name", "") in checkpoint_meal_names]

    # Missing main meals before this checkpoint
    missing_meals: list = []
    for i in range(block_idx + 1):
        main_meal = blocks[i]["meals"][0]
        if main_meal not in logged_names:
            missing_meals.append(main_meal)

    actual = _sum_macros(checkpoint_log)

    # Checkpoint targets (midpoint)
    cp_target = {
        "cal": round(daily_cal * checkpoint_pct / 100),
        "p": round(targets["protein"]["target"] * checkpoint_pct / 100, 1),
        "c": round(targets["carb"]["target"] * checkpoint_pct / 100, 1),
        "f": round(targets["fat"]["target"] * checkpoint_pct / 100, 1),
    }

    # Checkpoint ranges (min/max scaled by checkpoint percentage)
    cp_range = {
        "cal_min": round(targets["cal_range"]["min"] * checkpoint_pct / 100),
        "cal_max": round(targets["cal_range"]["max"] * checkpoint_pct / 100),
        "p_min": round(targets["protein"]["min"] * checkpoint_pct / 100, 1),
        "p_max": round(targets["protein"]["max"] * checkpoint_pct / 100, 1),
        "c_min": round(targets["carb"]["min"] * checkpoint_pct / 100, 1),
        "c_max": round(targets["carb"]["max"] * checkpoint_pct / 100, 1),
        "f_min": round(targets["fat"]["min"] * checkpoint_pct / 100, 1),
        "f_max": round(targets["fat"]["max"] * checkpoint_pct / 100, 1),
    }

    # Adjusted = actual + assumed (for generating suggestions when meals forgotten)
    adjusted = dict(actual)
    if assumed_meals:
        for m in assumed_meals:
            if m.get("name", "") in checkpoint_meal_names:
                adjusted["cal"] = round(adjusted["cal"] + m.get("cal", 0), 1)
                adjusted["p"] = round(adjusted["p"] + m.get("p", 0), 1)
                adjusted["c"] = round(adjusted["c"] + m.get("c", 0), 1)
                adjusted["f"] = round(adjusted["f"] + m.get("f", 0), 1)

    # Status per macro using range-based comparison
    status = {
        "cal": _range_status(actual["cal"], cp_range["cal_min"], cp_range["cal_max"]),
        "p": _range_status(actual["p"], cp_range["p_min"], cp_range["p_max"]),
        "c": _range_status(actual["c"], cp_range["c_min"], cp_range["c_max"]),
        "f": _range_status(actual["f"], cp_range["f_min"], cp_range["f_max"]),
    }

    # Determine if adjustment is needed:
    # calories outside range OR 2+ macros outside range
    cal_outside = not _in_range(actual["cal"], cp_range["cal_min"], cp_range["cal_max"])
    macros_outside = sum(1 for k in ["p", "c", "f"] if status[k] != "on_track")
    needs_adjustment = cal_outside or macros_outside >= 2

    # Diff for suggestions (based on adjusted values if assumed meals exist)
    suggestion_base = adjusted if assumed_meals else actual
    diff = {
        "cal": round(cp_target["cal"] - suggestion_base["cal"], 1),
        "p": round(cp_target["p"] - suggestion_base["p"], 1),
        "c": round(cp_target["c"] - suggestion_base["c"], 1),
        "f": round(cp_target["f"] - suggestion_base["f"], 1),
    }

    return {
        "current_meal": current_meal,
        "checkpoint_pct": checkpoint_pct,
        "checkpoint_target": cp_target,
        "checkpoint_range": cp_range,
        "actual": actual,
        "adjusted": adjusted if assumed_meals else None,
        "status": status,
        "needs_adjustment": needs_adjustment,
        "diff_for_suggestions": diff,
        "missing_meals": missing_meals,
        "meals_included": [m.get("name") for m in checkpoint_log],
    }


def check_missing(meals: int, current_meal: str, log: list) -> dict:
    """Check which main meals are missing before the current meal's block."""
    blocks = get_meal_blocks(meals)
    block_idx = find_block_index(current_meal, meals)
    if block_idx is None:
        return {"error": f"Unknown meal name: {current_meal}"}

    logged_names = {m.get("name", "") for m in log}

    missing: list = []
    for i in range(block_idx):
        main_meal = blocks[i]["meals"][0]
        if main_meal not in logged_names:
            missing.append({
                "name": main_meal,
                "expected_pct": blocks[i]["pct"],
            })

    return {
        "current_meal": current_meal,
        "missing": missing,
        "has_missing": len(missing) > 0,
    }


def main():
    parser = argparse.ArgumentParser(description="Nutrition calculator")
    sub = parser.add_subparsers(dest="cmd")

    t = sub.add_parser("target", help="Compute daily macro targets")
    t.add_argument("--weight", type=float, required=True, help="Body weight in kg")
    t.add_argument("--cal", type=int, required=True, help="Daily calorie target (kcal)")
    t.add_argument("--meals", type=int, default=3, choices=[2, 3], help="Meals per day")

    a = sub.add_parser("analyze", help="Analyze cumulative intake")
    a.add_argument("--weight", type=float, required=True)
    a.add_argument("--cal", type=int, required=True)
    a.add_argument("--meals", type=int, default=3, choices=[2, 3])
    a.add_argument("--log", type=str, required=True,
                   help='JSON array of meals')

    s = sub.add_parser("save", help="Save a meal record to today's log")
    s.add_argument("--data-dir", type=str, required=True, help="Directory to store daily JSON logs")
    s.add_argument("--meal", type=str, required=True, help="JSON object for the meal")
    s.add_argument("--date", type=str, default=None, help="Date override (YYYY-MM-DD)")

    l = sub.add_parser("load", help="Load today's meal records")
    l.add_argument("--data-dir", type=str, required=True, help="Directory with daily JSON logs")
    l.add_argument("--date", type=str, default=None, help="Date to load (YYYY-MM-DD), default today")

    e = sub.add_parser("evaluate", help="Evaluate cumulative intake at a meal checkpoint")
    e.add_argument("--weight", type=float, required=True)
    e.add_argument("--cal", type=int, required=True)
    e.add_argument("--meals", type=int, default=3, choices=[2, 3])
    e.add_argument("--current-meal", type=str, required=True,
                   help="Meal being evaluated (e.g. breakfast, lunch, dinner, snack_am, snack_pm)")
    e.add_argument("--log", type=str, required=True,
                   help="JSON array of all logged meals today")
    e.add_argument("--assumed", type=str, default=None,
                   help="JSON array of assumed meals (for forgotten meals)")

    cm = sub.add_parser("check-missing", help="Check for missing meals before current meal")
    cm.add_argument("--meals", type=int, default=3, choices=[2, 3])
    cm.add_argument("--current-meal", type=str, required=True)
    cm.add_argument("--log", type=str, required=True,
                   help="JSON array of all logged meals today")

    args = parser.parse_args()

    if args.cmd == "target":
        result = calc_targets(args.weight, args.cal, args.meals)
    elif args.cmd == "analyze":
        try:
            log = json.loads(args.log)
        except json.JSONDecodeError as e:
            print(f"Error: invalid --log JSON: {e}", file=sys.stderr)
            sys.exit(1)
        result = analyze(args.weight, args.cal, args.meals, log)
    elif args.cmd == "save":
        try:
            meal = json.loads(args.meal)
        except json.JSONDecodeError as e:
            print(f"Error: invalid --meal JSON: {e}", file=sys.stderr)
            sys.exit(1)
        result = save_meal(args.data_dir, meal, args.date)
    elif args.cmd == "load":
        result = load_meals(args.data_dir, args.date)
    elif args.cmd == "evaluate":
        try:
            log = json.loads(args.log)
        except json.JSONDecodeError as e:
            print(f"Error: invalid --log JSON: {e}", file=sys.stderr)
            sys.exit(1)
        assumed = None
        if args.assumed:
            try:
                assumed = json.loads(args.assumed)
            except json.JSONDecodeError as e:
                print(f"Error: invalid --assumed JSON: {e}", file=sys.stderr)
                sys.exit(1)
        result = evaluate(args.weight, args.cal, args.meals,
                          args.current_meal, log, assumed)
    elif args.cmd == "check-missing":
        try:
            log = json.loads(args.log)
        except json.JSONDecodeError as e:
            print(f"Error: invalid --log JSON: {e}", file=sys.stderr)
            sys.exit(1)
        result = check_missing(args.meals, args.current_meal, log)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
