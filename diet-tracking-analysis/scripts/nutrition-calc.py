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
  weekly-low-cal-check — Check if weekly average calorie intake is below BMR.

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
  python3 nutrition-calc.py weekly-low-cal-check --data-dir /path/to/data --bmr 1400
"""

import argparse
import json
import os
import sys
from datetime import date, timedelta


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

# Alias map: traditional 3-meal names → 2-meal equivalents.
# In 2-meal mode users may still say "breakfast", "lunch", or "dinner".
MEAL_ALIAS_2 = {
    "breakfast": "meal_1",
    "snack_am":  "snack_1",
    "lunch":     "meal_1",
    "snack_pm":  "snack_2",
    "dinner":    "meal_2",
}

# Diet mode → fat percentage range (low%, high%)
DIET_MODE_FAT = {
    "usda":          (20, 35),
    "balanced":      (25, 35),
    "high_protein":  (25, 35),
    "low_carb":      (40, 50),
    "keto":          (65, 75),
    "mediterranean": (25, 35),
    "plant_based":   (20, 30),
    "if_16_8":       (25, 35),
    "if_5_2":        (25, 35),
}

# Diet mode → full macro percentage ranges for pattern detection.
# protein (low%, high%), carb (low%, high%), fat (low%, high%)
# IF modes are timing strategies; their macro profile matches balanced.
DIET_MODE_MACROS = {
    "usda":          {"p": (10, 35), "c": (45, 65), "f": (20, 35)},
    "balanced":      {"p": (25, 35), "c": (35, 45), "f": (25, 35)},
    "high_protein":  {"p": (35, 45), "c": (25, 35), "f": (25, 35)},
    "low_carb":      {"p": (30, 40), "c": (15, 25), "f": (40, 50)},
    "keto":          {"p": (20, 25), "c": (5, 10),  "f": (65, 75)},
    "mediterranean": {"p": (20, 30), "c": (40, 50), "f": (25, 35)},
    "plant_based":   {"p": (20, 30), "c": (45, 55), "f": (20, 30)},
}


def get_meal_blocks(meals: int) -> list:
    return MEAL_BLOCKS_3 if meals == 3 else MEAL_BLOCKS_2


def resolve_meal_name(meal_name: str, meals: int) -> str:
    """Resolve a meal name, applying 2-meal aliases when needed."""
    if meals == 2 and meal_name in MEAL_ALIAS_2:
        return MEAL_ALIAS_2[meal_name]
    return meal_name


def find_block_index(meal_name: str, meals: int) -> int:
    """Find which block a meal type belongs to."""
    resolved = resolve_meal_name(meal_name, meals)
    for i, block in enumerate(get_meal_blocks(meals)):
        if resolved in block["meals"]:
            return i
    return None


def calc_targets(weight: float, daily_cal: int, meals: int = 3,
                 mode: str = "balanced") -> dict:
    """Compute daily macro targets with min/max ranges.

    Fat ranges are determined by the diet mode (see DIET_MODE_FAT).
    """
    protein = round(weight * 1.4, 1)
    protein_lo = round(weight * 1.2, 1)
    protein_hi = round(weight * 1.6, 1)

    fat_lo_pct, fat_hi_pct = DIET_MODE_FAT.get(mode, (25, 35))
    fat_mid_pct = (fat_lo_pct + fat_hi_pct) / 2

    fat = round(daily_cal * fat_mid_pct / 100 / 9, 1)
    fat_lo = round(daily_cal * fat_lo_pct / 100 / 9, 1)
    fat_hi = round(daily_cal * fat_hi_pct / 100 / 9, 1)

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


def analyze(weight: float, daily_cal: int, meals: int, log: list,
            mode: str = "balanced") -> dict:
    """Analyze cumulative intake against daily targets."""
    targets = calc_targets(weight, daily_cal, meals, mode)

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
             assumed_meals: list = None,
             mode: str = "balanced") -> dict:
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
    targets = calc_targets(weight, daily_cal, meals, mode)
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

    logged_names = {resolve_meal_name(m.get("name", ""), meals) for m in log}

    # Only count meals that belong to the checkpoint window
    checkpoint_log = [m for m in log
                      if resolve_meal_name(m.get("name", ""), meals) in checkpoint_meal_names]

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
            if resolve_meal_name(m.get("name", ""), meals) in checkpoint_meal_names:
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
        "resolved_meal": resolve_meal_name(current_meal, meals),
    }


def check_missing(meals: int, current_meal: str, log: list) -> dict:
    """Check which main meals are missing before the current meal's block."""
    blocks = get_meal_blocks(meals)
    block_idx = find_block_index(current_meal, meals)
    if block_idx is None:
        return {"error": f"Unknown meal name: {current_meal}"}

    logged_names = {resolve_meal_name(m.get("name", ""), meals) for m in log}

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


def weekly_low_cal_check(data_dir: str, bmr: float,
                         ref_date: str = None) -> dict:
    """Check if the user's weekly average calorie intake is below BMR.

    Loads the past 7 days of meal data (ending on *ref_date*, default today),
    computes total daily calories for each day that has records, and compares
    the average against the BMR-based calorie floor (max(BMR, 1000)).

    Returns a summary with per-day totals, the weekly average, the floor,
    and a boolean flag indicating whether intervention is warranted.
    """
    end = date.fromisoformat(ref_date) if ref_date else date.today()
    calorie_floor = max(bmr, 1000)

    daily_totals: list[dict] = []
    days_below: list[str] = []

    for offset in range(7):
        day = (end - timedelta(days=offset)).isoformat()
        path = get_log_path(data_dir, day)
        if not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            meals = json.load(f)
        day_cal = round(sum(m.get("cal", 0) for m in meals), 1)
        daily_totals.append({"date": day, "cal": day_cal})
        if day_cal < calorie_floor:
            days_below.append(day)

    logged_days = len(daily_totals)
    avg_cal = round(sum(d["cal"] for d in daily_totals) / logged_days, 1) if logged_days else 0

    # Flag a warning when the weekly average is below the floor
    below_floor = avg_cal < calorie_floor if logged_days > 0 else False

    return {
        "period_end": end.isoformat(),
        "logged_days": logged_days,
        "daily_totals": sorted(daily_totals, key=lambda d: d["date"]),
        "weekly_avg_cal": avg_cal,
        "bmr": bmr,
        "calorie_floor": calorie_floor,
        "days_below_floor": days_below,
        "days_below_count": len(days_below),
        "below_floor": below_floor,
    }


def _calc_macro_pcts(meals: list) -> dict | None:
    """Calculate macro percentage split from a list of meals.

    Returns {"cal": total, "p_pct": ..., "c_pct": ..., "f_pct": ...}
    or None if total calories are too low (< 500) for meaningful analysis.
    """
    total_cal = sum(m.get("cal", 0) for m in meals)
    total_p = sum(m.get("p", 0) for m in meals)
    total_c = sum(m.get("c", 0) for m in meals)
    total_f = sum(m.get("f", 0) for m in meals)

    if total_cal < 500:
        return None

    return {
        "cal": round(total_cal, 1),
        "p_pct": round(total_p * 4 / total_cal * 100, 1),
        "c_pct": round(total_c * 4 / total_cal * 100, 1),
        "f_pct": round(total_f * 9 / total_cal * 100, 1),
    }


def _mode_distance(p_pct: float, c_pct: float, f_pct: float,
                   mode: str) -> float:
    """Calculate how far a macro split is from a diet mode's expected ranges.

    Returns 0 if all macros fall within the mode's ranges.
    Otherwise returns the sum of distances outside each range.
    """
    ranges = DIET_MODE_MACROS.get(mode)
    if not ranges:
        return float("inf")

    dist = 0.0
    for actual, key in [(p_pct, "p"), (c_pct, "c"), (f_pct, "f")]:
        lo, hi = ranges[key]
        if actual < lo:
            dist += lo - actual
        elif actual > hi:
            dist += actual - hi
    return dist


def _matches_mode(p_pct: float, c_pct: float, f_pct: float,
                  mode: str) -> bool:
    """Check if a macro split falls within a diet mode's ranges."""
    return _mode_distance(p_pct, c_pct, f_pct, mode) == 0


def detect_diet_pattern(data_dir: str, current_mode: str,
                        ref_date: str = None) -> dict:
    """Detect if the user's actual eating pattern over 3 consecutive days
    differs from their selected diet mode.

    Loads the most recent 3 days (ending on *ref_date*) that have meal data,
    within a 7-day lookback window. Calculates macro percentage splits for
    each day and checks consistency against known diet modes.

    Returns:
      - detected_mode: the diet mode that best matches the actual pattern
        (None if no consistent pattern found)
      - mismatch: True if detected_mode differs from current_mode
      - daily_splits: per-day macro percentages
      - avg_split: average macro percentages across the 3 days
      - current_mode_distance: how far the average is from the current mode
      - detected_mode_distance: how far the average is from the detected mode
      - pros / cons: brief descriptions for switching to the detected mode
    """
    end = date.fromisoformat(ref_date) if ref_date else date.today()

    # Collect up to 3 days with data within a 7-day window
    daily_splits: list[dict] = []
    for offset in range(7):
        day = (end - timedelta(days=offset)).isoformat()
        path = get_log_path(data_dir, day)
        if not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            meals = json.load(f)
        pcts = _calc_macro_pcts(meals)
        if pcts is not None:
            daily_splits.append({"date": day, **pcts})
        if len(daily_splits) >= 3:
            break

    if len(daily_splits) < 3:
        return {
            "has_pattern": False,
            "reason": "insufficient_data",
            "days_found": len(daily_splits),
            "daily_splits": sorted(daily_splits, key=lambda d: d["date"]),
        }

    # Average macro percentages
    avg_p = round(sum(d["p_pct"] for d in daily_splits) / 3, 1)
    avg_c = round(sum(d["c_pct"] for d in daily_splits) / 3, 1)
    avg_f = round(sum(d["f_pct"] for d in daily_splits) / 3, 1)
    avg_split = {"p_pct": avg_p, "c_pct": avg_c, "f_pct": avg_f}

    # Normalize current_mode: IF modes use balanced macro profile
    effective_current = current_mode
    if current_mode in ("if_16_8", "if_5_2"):
        effective_current = "balanced"

    # Check if the average already matches the current mode
    current_dist = _mode_distance(avg_p, avg_c, avg_f, effective_current)

    # Find the best-matching mode
    best_mode = None
    best_dist = float("inf")
    for mode in DIET_MODE_MACROS:
        dist = _mode_distance(avg_p, avg_c, avg_f, mode)
        if dist < best_dist:
            best_dist = dist
            best_mode = mode

    # Check if each individual day also matches the detected mode
    # (consistency check — pattern must hold across all 3 days)
    all_days_match = all(
        _mode_distance(d["p_pct"], d["c_pct"], d["f_pct"], best_mode) <=
        _mode_distance(d["p_pct"], d["c_pct"], d["f_pct"], effective_current)
        for d in daily_splits
    )

    # Determine mismatch
    mismatch = (best_mode != effective_current
                and best_dist < current_dist
                and all_days_match)

    # Generate pros/cons for switching
    pros_cons = _get_pros_cons(effective_current, best_mode) if mismatch else None

    return {
        "has_pattern": mismatch,
        "current_mode": current_mode,
        "effective_current_mode": effective_current,
        "detected_mode": best_mode if mismatch else None,
        "current_mode_distance": round(current_dist, 1),
        "detected_mode_distance": round(best_dist, 1),
        "avg_split": avg_split,
        "daily_splits": sorted(daily_splits, key=lambda d: d["date"]),
        "days_found": len(daily_splits),
        "all_days_consistent": all_days_match,
        "pros_cons": pros_cons,
    }


def _get_pros_cons(current_mode: str, detected_mode: str) -> dict:
    """Return pros and cons of switching from current_mode to detected_mode."""
    mode_info = {
        "balanced": {
            "name": "Balanced / Flexible",
            "pros": [
                "No food restrictions — highest flexibility and adherence",
                "Easy to maintain long-term",
                "Well-suited for beginners",
            ],
            "cons": [
                "Less targeted than specialized modes",
                "Requires tracking to stay on course",
            ],
        },
        "high_protein": {
            "name": "High-Protein",
            "pros": [
                "Better muscle preservation during calorie deficit",
                "Higher satiety — feel fuller longer",
                "Increased thermic effect of food",
            ],
            "cons": [
                "Can feel monotonous — requires rotating protein sources",
                "May be harder to hit protein targets consistently",
                "Higher food cost (protein sources tend to be pricier)",
            ],
        },
        "low_carb": {
            "name": "Low-Carb",
            "pros": [
                "Reduced hunger and more stable energy for many people",
                "Lower insulin response",
                "Can reduce bloating",
            ],
            "cons": [
                "Fiber intake may drop — need to eat plenty of vegetables",
                "Can feel restrictive for carb lovers",
                "May reduce exercise performance initially",
            ],
        },
        "keto": {
            "name": "Keto",
            "pros": [
                "Strong appetite suppression after adaptation",
                "High fat intake increases meal satisfaction",
            ],
            "cons": [
                "Extremely restrictive — hard to sustain socially",
                "Keto flu during adaptation (1-2 weeks)",
                "Risk of nutrient deficiencies without careful planning",
                "Not recommended below 1,800 cal/day",
            ],
        },
        "mediterranean": {
            "name": "Mediterranean",
            "pros": [
                "Strong evidence for cardiovascular health",
                "Feels like eating well rather than dieting",
                "Rich in healthy fats and whole foods",
            ],
            "cons": [
                "Olive oil and nuts are calorie-dense — portions need care",
                "May require more cooking and meal prep",
            ],
        },
        "plant_based": {
            "name": "Plant-Based",
            "pros": [
                "High fiber naturally increases satiety",
                "Associated with lower heart disease risk",
                "Often lower calorie density",
            ],
            "cons": [
                "Hitting protein targets is harder without animal products",
                "Requires more intentional meal planning",
                "May need B12 and other supplements",
            ],
        },
        "usda": {
            "name": "Healthy U.S.-Style (USDA)",
            "pros": [
                "Government-backed, evidence-based guidelines",
                "No food groups excluded — very flexible",
                "Good baseline for general health",
            ],
            "cons": [
                "Broad ranges may feel too vague for specific goals",
                "Less targeted for weight loss than specialized modes",
            ],
        },
    }

    detected_info = mode_info.get(detected_mode, {})
    current_info = mode_info.get(current_mode, {})

    return {
        "switch_to": detected_mode,
        "switch_to_name": detected_info.get("name", detected_mode),
        "switch_from": current_mode,
        "switch_from_name": current_info.get("name", current_mode),
        "pros": detected_info.get("pros", []),
        "cons": detected_info.get("cons", []),
    }


def main():
    parser = argparse.ArgumentParser(description="Nutrition calculator")
    sub = parser.add_subparsers(dest="cmd")

    t = sub.add_parser("target", help="Compute daily macro targets")
    t.add_argument("--weight", type=float, required=True, help="Body weight in kg")
    t.add_argument("--cal", type=int, required=True, help="Daily calorie target (kcal)")
    t.add_argument("--meals", type=int, default=3, choices=[2, 3], help="Meals per day")
    t.add_argument("--mode", type=str, default="balanced",
                   choices=list(DIET_MODE_FAT.keys()),
                   help="Diet mode (determines fat %% range)")

    a = sub.add_parser("analyze", help="Analyze cumulative intake")
    a.add_argument("--weight", type=float, required=True)
    a.add_argument("--cal", type=int, required=True)
    a.add_argument("--meals", type=int, default=3, choices=[2, 3])
    a.add_argument("--mode", type=str, default="balanced",
                   choices=list(DIET_MODE_FAT.keys()))
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
    e.add_argument("--mode", type=str, default="balanced",
                   choices=list(DIET_MODE_FAT.keys()))
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

    wlc = sub.add_parser("weekly-low-cal-check",
                          help="Check if weekly average calorie intake is below BMR")
    wlc.add_argument("--data-dir", type=str, required=True,
                     help="Directory with daily JSON logs")
    wlc.add_argument("--bmr", type=float, required=True,
                     help="User's BMR in kcal/day")
    wlc.add_argument("--date", type=str, default=None,
                     help="End date for the 7-day window (YYYY-MM-DD), default today")

    ddp = sub.add_parser("detect-diet-pattern",
                          help="Detect if eating pattern differs from selected diet mode")
    ddp.add_argument("--data-dir", type=str, required=True,
                     help="Directory with daily JSON logs")
    ddp.add_argument("--current-mode", type=str, required=True,
                     choices=list(DIET_MODE_FAT.keys()),
                     help="User's currently selected diet mode")
    ddp.add_argument("--date", type=str, default=None,
                     help="End date for the 3-day window (YYYY-MM-DD), default today")

    args = parser.parse_args()

    if args.cmd == "target":
        result = calc_targets(args.weight, args.cal, args.meals, args.mode)
    elif args.cmd == "analyze":
        try:
            log = json.loads(args.log)
        except json.JSONDecodeError as e:
            print(f"Error: invalid --log JSON: {e}", file=sys.stderr)
            sys.exit(1)
        result = analyze(args.weight, args.cal, args.meals, log, args.mode)
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
                          args.current_meal, log, assumed, args.mode)
    elif args.cmd == "check-missing":
        try:
            log = json.loads(args.log)
        except json.JSONDecodeError as e:
            print(f"Error: invalid --log JSON: {e}", file=sys.stderr)
            sys.exit(1)
        result = check_missing(args.meals, args.current_meal, log)
    elif args.cmd == "weekly-low-cal-check":
        result = weekly_low_cal_check(args.data_dir, args.bmr, args.date)
    elif args.cmd == "detect-diet-pattern":
        result = detect_diet_pattern(args.data_dir, args.current_mode, args.date)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
