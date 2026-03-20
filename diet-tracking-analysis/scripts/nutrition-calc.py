# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
Nutrition calculator for diet-tracking-analysis skill.

Commands:
  detect-meal  — Detect meal type from timestamp, timezone, and meal schedule.
  target       — Compute daily macro targets from weight & calorie goal.
  analyze      — Compute cumulative intake, compare with targets, output status.
  save         — Persist a meal record to today's log file.
  load         — Load today's (or a given date's) meal records.
  evaluate     — Evaluate cumulative intake at a meal checkpoint (range-based).
  check-missing — Check which main meals are missing before the current meal.
  meal-history  — Analyze meal history for a meal type over N days.
  save-recommendation — Save meal recommendations for today.
  weekly-low-cal-check — Check if weekly average calorie intake is below BMR.
  produce-check — Evaluate cumulative vegetable and fruit intake (China region).
  save-correction — Save a food correction when user corrects AI identification.
  lookup-corrections — Look up saved corrections matching food names.
  apply-correction — Increment usage counter for a correction record.
  propose-standard-adjustment — Analyze 2 consecutive days for consistent
      deviation from current standards and propose adjusted nutrition targets.

Usage:
  python3 nutrition-calc.py detect-meal --tz-offset 28800 --meals 3 \
      [--schedule '{"breakfast":"09:00","lunch":"12:00","dinner":"18:00"}'] \
      [--log '[...]'] [--timestamp 2026-03-17T11:14:13Z]
  python3 nutrition-calc.py target  --weight 65 --cal 1500 [--meals 3]
  python3 nutrition-calc.py analyze --weight 65 --cal 1500 --meals 3 \
      --log '[{"name":"breakfast","calories":379,"protein":24,"carbs":45,"fat":12}]'
  python3 nutrition-calc.py save --data-dir /path/to/data \
      --meal '{"name":"breakfast","meal_type":"breakfast","calories":379,"protein":24,"carbs":45,"fat":12,"foods":[{"name":"boiled eggs x2","calories":144}]}'
  python3 nutrition-calc.py load --data-dir /path/to/data [--date 2026-02-27]
  python3 nutrition-calc.py evaluate --weight 65 --cal 1500 --meals 3 \
      --current-meal lunch --log '[...]'
  python3 nutrition-calc.py check-missing --meals 3 --current-meal lunch --log '[...]'
  python3 nutrition-calc.py meal-history --data-dir /path/to/data --days 30 --meal-type lunch
  python3 nutrition-calc.py save-recommendation --data-dir /path/to/data \
      --meal-type lunch --items '["鸡胸肉+糙米+西兰花", "牛肉面+茶叶蛋", "沙拉+全麦面包+酸奶"]'
  python3 nutrition-calc.py weekly-low-cal-check --data-dir /path/to/data --bmr 1400
  python3 nutrition-calc.py produce-check --meals 3 --current-meal lunch --log '[...]'
  python3 nutrition-calc.py save-correction --data-dir /path/to/data \
      --original '[{"name":"white rice","calories":200}]' \
      --corrected '[{"name":"brown rice","calories":170}]' \
      --type food_identity --note "User always eats brown rice"
  python3 nutrition-calc.py lookup-corrections --data-dir /path/to/data \
      --foods '["rice","eggs"]'
  python3 nutrition-calc.py apply-correction --data-dir /path/to/data \
      --original-names '["white rice"]'
"""

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone


def _local_date(tz_offset: int = None) -> str:
    """Return local date as YYYY-MM-DD string.
    If tz_offset (seconds from UTC) is given, compute local date from UTC now.
    Otherwise fall back to server's date.today().
    """
    if tz_offset is not None:
        utc_now = datetime.now(timezone.utc)
        local_dt = utc_now + timedelta(seconds=tz_offset)
        return local_dt.date().isoformat()
    return date.today().isoformat()


# ---------------------------------------------------------------------------
# Backward compatibility: migrate old short field names to full names
# ---------------------------------------------------------------------------

# Mapping from old short keys to new full keys
_SHORT_TO_LONG = {"cal": "calories", "p": "protein", "c": "carbs", "f": "fat"}


def _migrate_meal(meal: dict) -> dict:
    """Convert old short-key meal dicts to full-name keys.

    Handles both top-level fields and nested foods list.
    If both short and long keys exist, long key takes precedence.
    """
    out = {}
    for k, v in meal.items():
        new_key = _SHORT_TO_LONG.get(k, k)
        # Don't overwrite if the long name already exists
        if new_key in out:
            continue
        if k == "foods" and isinstance(v, list):
            out[k] = [_migrate_meal(f) for f in v]
        else:
            out[new_key] = v
    return out


def _migrate_meals(meals: list) -> list:
    """Migrate a list of meal dicts."""
    return [_migrate_meal(m) for m in meals]


# ---------------------------------------------------------------------------
# Meal blocks & aliases
# ---------------------------------------------------------------------------

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
MEAL_ALIAS_2 = {
    "breakfast": "meal_1",
    "snack_am":  "snack_1",
    "lunch":     "meal_1",
    "snack_pm":  "snack_2",
    "dinner":    "meal_2",
}

# ---------------------------------------------------------------------------
# Diet mode configurations
# ---------------------------------------------------------------------------

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

DIET_MODE_MACROS = {
    "usda":          {"protein": (10, 35), "carbs": (45, 65), "fat": (20, 35)},
    "balanced":      {"protein": (25, 35), "carbs": (35, 45), "fat": (25, 35)},
    "high_protein":  {"protein": (35, 45), "carbs": (25, 35), "fat": (25, 35)},
    "low_carb":      {"protein": (30, 40), "carbs": (15, 25), "fat": (40, 50)},
    "keto":          {"protein": (20, 25), "carbs": (5, 10),  "fat": (65, 75)},
    "mediterranean": {"protein": (20, 30), "carbs": (40, 50), "fat": (25, 35)},
    "plant_based":   {"protein": (20, 30), "carbs": (45, 55), "fat": (20, 30)},
}

# ---------------------------------------------------------------------------
# Produce tracking constants (China region)
# ---------------------------------------------------------------------------

# Cumulative vegetable target (g) by checkpoint. None = no target at this checkpoint.
# Key: (meals_per_day, block_index)
PRODUCE_VEG_TARGETS: dict = {
    (3, 0): None,   # breakfast block — no vegetable requirement
    (3, 1): 150,    # by lunch — cumulative ≥150g
    (3, 2): 300,    # by dinner — cumulative ≥300g
    (2, 0): 150,    # by meal_1 — cumulative ≥150g
    (2, 1): 300,    # by meal_2 — cumulative ≥300g
}

PRODUCE_FRUIT_DAILY_MIN = 200  # g — minimum daily fruit intake
PRODUCE_FRUIT_DAILY_MAX = 350  # g — maximum daily fruit intake


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_meal_blocks(meals: int, custom_pcts: dict = None) -> list:
    """Get meal blocks, optionally with custom percentages.

    Args:
        meals: 2 or 3.
        custom_pcts: Optional dict mapping meal label to percentage,
                     e.g. {"breakfast": 25, "lunch": 45, "dinner": 30}.
                     Labels not present keep their default value.
    """
    base = MEAL_BLOCKS_3 if meals == 3 else MEAL_BLOCKS_2
    if not custom_pcts:
        return base
    result = []
    for block in base:
        pct = custom_pcts.get(block["label"], block["pct"])
        result.append({
            "label": block["label"],
            "pct": pct,
            "meals": list(block["meals"]),
        })
    return result


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


def _in_range(value: float, lo: float, hi: float) -> bool:
    return lo <= value <= hi


def _range_status(value: float, lo: float, hi: float) -> str:
    if value < lo:
        return "low"
    elif value > hi:
        return "high"
    return "on_track"


def _sum_macros(meal_list: list) -> dict:
    s = {"calories": 0, "protein": 0, "carbs": 0, "fat": 0}
    for m in meal_list:
        s["calories"] += m.get("calories", 0)
        s["protein"] += m.get("protein", 0)
        s["carbs"] += m.get("carbs", 0)
        s["fat"] += m.get("fat", 0)
    return {k: round(v, 1) for k, v in s.items()}


def get_log_path(data_dir: str, day: str = None, tz_offset: int = None) -> str:
    day = day or _local_date(tz_offset)
    return os.path.join(data_dir, f"{day}.json")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def calc_targets(weight: float, daily_cal: int, meals: int = 3,
                 mode: str = "balanced",
                 meal_blocks: dict = None) -> dict:
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

    cal_lo = daily_cal - 100
    cal_hi = daily_cal + 100

    blocks = get_meal_blocks(meals, meal_blocks)
    alloc = []
    for b in blocks:
        alloc.append({"meal": b["label"], "pct": b["pct"],
                       "calories": round(daily_cal * b["pct"] / 100)})

    return {
        "daily_calories": daily_cal,
        "calories_range": {"min": cal_lo, "max": cal_hi},
        "weight": weight,
        "meals": meals,
        "protein": {"target": protein, "min": protein_lo, "max": protein_hi},
        "fat": {"target": fat, "min": fat_lo, "max": fat_hi},
        "carb": {"target": carb, "min": carb_lo, "max": carb_hi},
        "allocation": alloc,
    }


def analyze(weight: float, daily_cal: int, meals: int, log: list,
            mode: str = "balanced",
            meal_blocks: dict = None) -> dict:
    log = _migrate_meals(log)
    targets = calc_targets(weight, daily_cal, meals, mode, meal_blocks)

    cum = {"calories": 0, "protein": 0, "carbs": 0, "fat": 0}
    meal_details = []
    for entry in log:
        cum["calories"] += entry.get("calories", 0)
        cum["protein"] += entry.get("protein", 0)
        cum["carbs"] += entry.get("carbs", 0)
        cum["fat"] += entry.get("fat", 0)
        meal_details.append({
            "name": entry.get("name", ""),
            "meal_type": entry.get("meal_type", ""),
            "calories": entry.get("calories", 0),
            "protein": entry.get("protein", 0),
            "carbs": entry.get("carbs", 0),
            "fat": entry.get("fat", 0),
        })

    for k in cum:
        cum[k] = round(cum[k], 1)

    pct_cal = round(cum["calories"] / daily_cal * 100) if daily_cal else 0
    remain = {
        "calories": round(daily_cal - cum["calories"], 1),
        "protein": round(targets["protein"]["target"] - cum["protein"], 1),
        "carbs": round(targets["carb"]["target"] - cum["carbs"], 1),
        "fat": round(targets["fat"]["target"] - cum["fat"], 1),
    }

    status = {
        "calories": _range_status(cum["calories"], targets["calories_range"]["min"], targets["calories_range"]["max"]),
        "protein": _range_status(cum["protein"], targets["protein"]["min"], targets["protein"]["max"]),
        "carbs": _range_status(cum["carbs"], targets["carb"]["min"], targets["carb"]["max"]),
        "fat": _range_status(cum["fat"], targets["fat"]["min"], targets["fat"]["max"]),
    }

    return {
        "targets": targets,
        "meals": meal_details,
        "cumulative": cum,
        "pct_calories": pct_cal,
        "remaining": remain,
        "status": status,
    }


def save_meal(data_dir: str, meal: dict, day: str = None, tz_offset: int = None) -> dict:
    """Save a meal to the daily log. Same meal name overwrites (supports corrections)."""
    os.makedirs(data_dir, exist_ok=True)
    meal = _migrate_meal(meal)
    path = get_log_path(data_dir, day, tz_offset)

    existing: list = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            existing = _migrate_meals(json.load(f))

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


def load_meals(data_dir: str, day: str = None, tz_offset: int = None) -> dict:
    """Load all meals for a given day, migrating old format if needed."""
    path = get_log_path(data_dir, day, tz_offset)
    resolved_day = day or _local_date(tz_offset)
    if not os.path.exists(path):
        return {"date": resolved_day, "meals": [], "meals_count": 0}
    with open(path, "r", encoding="utf-8") as f:
        meals = _migrate_meals(json.load(f))
    return {"date": resolved_day, "meals": meals, "meals_count": len(meals)}


def evaluate(weight: float, daily_cal: int, meals: int,
             current_meal: str, log: list,
             assumed_meals: list = None,
             mode: str = "balanced",
             meal_blocks: dict = None) -> dict:
    """Evaluate cumulative intake at the checkpoint for *current_meal*.

    Uses range-based evaluation:
    - Each checkpoint scales daily min/max ranges by the checkpoint percentage.
    - Adjustment is needed when: calories outside checkpoint kcal range
      OR 2+ macros outside their checkpoint ranges.
    """
    log = _migrate_meals(log)
    if assumed_meals:
        assumed_meals = _migrate_meals(assumed_meals)

    targets = calc_targets(weight, daily_cal, meals, mode, meal_blocks)
    blocks = get_meal_blocks(meals, meal_blocks)

    block_idx = find_block_index(current_meal, meals)
    if block_idx is None:
        return {"error": f"Unknown meal name: {current_meal}"}

    checkpoint_pct = sum(blocks[i]["pct"] for i in range(block_idx + 1))

    checkpoint_meal_names: set[str] = set()
    for i in range(block_idx + 1):
        checkpoint_meal_names.update(blocks[i]["meals"])

    logged_names = {resolve_meal_name(m.get("name", ""), meals) for m in log}

    checkpoint_log = [m for m in log
                      if resolve_meal_name(m.get("name", ""), meals) in checkpoint_meal_names]

    missing_meals: list = []
    for i in range(block_idx + 1):
        main_meal = blocks[i]["meals"][0]
        if main_meal not in logged_names:
            missing_meals.append(main_meal)

    actual = _sum_macros(checkpoint_log)

    cp_target = {
        "calories": round(daily_cal * checkpoint_pct / 100),
        "protein": round(targets["protein"]["target"] * checkpoint_pct / 100, 1),
        "carbs": round(targets["carb"]["target"] * checkpoint_pct / 100, 1),
        "fat": round(targets["fat"]["target"] * checkpoint_pct / 100, 1),
    }

    cp_range = {
        "calories_min": round(targets["calories_range"]["min"] * checkpoint_pct / 100),
        "calories_max": round(targets["calories_range"]["max"] * checkpoint_pct / 100),
        "protein_min": round(targets["protein"]["min"] * checkpoint_pct / 100, 1),
        "protein_max": round(targets["protein"]["max"] * checkpoint_pct / 100, 1),
        "carbs_min": round(targets["carb"]["min"] * checkpoint_pct / 100, 1),
        "carbs_max": round(targets["carb"]["max"] * checkpoint_pct / 100, 1),
        "fat_min": round(targets["fat"]["min"] * checkpoint_pct / 100, 1),
        "fat_max": round(targets["fat"]["max"] * checkpoint_pct / 100, 1),
    }

    adjusted = dict(actual)
    if assumed_meals:
        for m in assumed_meals:
            if resolve_meal_name(m.get("name", ""), meals) in checkpoint_meal_names:
                adjusted["calories"] = round(adjusted["calories"] + m.get("calories", 0), 1)
                adjusted["protein"] = round(adjusted["protein"] + m.get("protein", 0), 1)
                adjusted["carbs"] = round(adjusted["carbs"] + m.get("carbs", 0), 1)
                adjusted["fat"] = round(adjusted["fat"] + m.get("fat", 0), 1)

    status = {
        "calories": _range_status(actual["calories"], cp_range["calories_min"], cp_range["calories_max"]),
        "protein": _range_status(actual["protein"], cp_range["protein_min"], cp_range["protein_max"]),
        "carbs": _range_status(actual["carbs"], cp_range["carbs_min"], cp_range["carbs_max"]),
        "fat": _range_status(actual["fat"], cp_range["fat_min"], cp_range["fat_max"]),
    }

    cal_outside = not _in_range(actual["calories"], cp_range["calories_min"], cp_range["calories_max"])
    macros_outside = sum(1 for k in ["protein", "carbs", "fat"] if status[k] != "on_track")
    needs_adjustment = cal_outside or macros_outside >= 2

    suggestion_base = adjusted if assumed_meals else actual
    diff = {
        "calories": round(cp_target["calories"] - suggestion_base["calories"], 1),
        "protein": round(cp_target["protein"] - suggestion_base["protein"], 1),
        "carbs": round(cp_target["carbs"] - suggestion_base["carbs"], 1),
        "fat": round(cp_target["fat"] - suggestion_base["fat"], 1),
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


def check_missing(meals: int, current_meal: str, log: list,
                  meal_blocks: dict = None) -> dict:
    log = _migrate_meals(log)
    blocks = get_meal_blocks(meals, meal_blocks)
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


def produce_check(meals: int, current_meal: str, log: list) -> dict:
    """Evaluate cumulative vegetable and fruit intake at the current checkpoint.

    Vegetables: cumulative target based on checkpoint (None = no target at that point).
    Fruits: checked only at the final meal of the day (200–350 g daily total).

    Meal JSON records may include optional fields:
      - vegetables_g: grams of vegetables in this meal
      - fruits_g: grams of fruit in this meal
    Missing fields default to 0.
    """
    log = _migrate_meals(log)
    blocks = get_meal_blocks(meals)
    block_idx = find_block_index(current_meal, meals)
    if block_idx is None:
        return {"error": f"Unknown meal name: {current_meal}"}

    checkpoint_meal_names: set[str] = set()
    for i in range(block_idx + 1):
        checkpoint_meal_names.update(blocks[i]["meals"])

    checkpoint_log = [
        m for m in log
        if resolve_meal_name(m.get("name", ""), meals) in checkpoint_meal_names
    ]

    veg_total = round(sum((m.get("vegetables_g") or 0) for m in checkpoint_log), 1)
    fruit_total = round(sum((m.get("fruits_g") or 0) for m in checkpoint_log), 1)

    is_final = block_idx == len(blocks) - 1

    veg_target = PRODUCE_VEG_TARGETS.get((meals, block_idx))
    has_veg_target = veg_target is not None

    veg_status: str | None = None
    if has_veg_target:
        veg_status = "on_track" if veg_total >= veg_target else "low"

    fruit_status: str | None = None
    if is_final:
        if fruit_total < PRODUCE_FRUIT_DAILY_MIN:
            fruit_status = "low"
        elif fruit_total > PRODUCE_FRUIT_DAILY_MAX:
            fruit_status = "high"
        else:
            fruit_status = "on_track"

    return {
        "current_meal": current_meal,
        "is_final_meal": is_final,
        "vegetables_actual_g": veg_total,
        "vegetables_target_g": veg_target,
        "has_vegetable_target": has_veg_target,
        "vegetable_status": veg_status,
        "fruits_actual_g": fruit_total,
        "fruits_daily_min_g": PRODUCE_FRUIT_DAILY_MIN if is_final else None,
        "fruits_daily_max_g": PRODUCE_FRUIT_DAILY_MAX if is_final else None,
        "fruit_status": fruit_status,
    }


def weekly_low_cal_check(data_dir: str, bmr: float,
                         ref_date: str = None, tz_offset: int = None) -> dict:
    end = date.fromisoformat(ref_date) if ref_date else date.fromisoformat(_local_date(tz_offset))
    calorie_floor = max(bmr, 1000)

    daily_totals: list[dict] = []
    days_below: list[str] = []

    for offset in range(7):
        day = (end - timedelta(days=offset)).isoformat()
        path = get_log_path(data_dir, day)
        if not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            meals = _migrate_meals(json.load(f))
        day_cal = round(sum(m.get("calories", 0) for m in meals), 1)
        daily_totals.append({"date": day, "calories": day_cal})
        if day_cal < calorie_floor:
            days_below.append(day)

    logged_days = len(daily_totals)
    avg_cal = round(sum(d["calories"] for d in daily_totals) / logged_days, 1) if logged_days else 0

    below_floor = avg_cal < calorie_floor if logged_days > 0 else False

    return {
        "period_end": end.isoformat(),
        "logged_days": logged_days,
        "daily_totals": sorted(daily_totals, key=lambda d: d["date"]),
        "weekly_avg_calories": avg_cal,
        "bmr": bmr,
        "calorie_floor": calorie_floor,
        "days_below_floor": days_below,
        "days_below_count": len(days_below),
        "below_floor": below_floor,
    }


# ---------------------------------------------------------------------------
# Diet pattern detection
# ---------------------------------------------------------------------------

def _calc_macro_pcts(meals: list):
    meals = _migrate_meals(meals)
    total_cal = sum(m.get("calories", 0) for m in meals)
    total_p = sum(m.get("protein", 0) for m in meals)
    total_c = sum(m.get("carbs", 0) for m in meals)
    total_f = sum(m.get("fat", 0) for m in meals)

    if total_cal < 500:
        return None

    return {
        "calories": round(total_cal, 1),
        "protein_pct": round(total_p * 4 / total_cal * 100, 1),
        "carbs_pct": round(total_c * 4 / total_cal * 100, 1),
        "fat_pct": round(total_f * 9 / total_cal * 100, 1),
    }


def _mode_distance(p_pct: float, c_pct: float, f_pct: float,
                   mode: str) -> float:
    ranges = DIET_MODE_MACROS.get(mode)
    if not ranges:
        return float("inf")

    dist = 0.0
    for actual, key in [(p_pct, "protein"), (c_pct, "carbs"), (f_pct, "fat")]:
        lo, hi = ranges[key]
        if actual < lo:
            dist += lo - actual
        elif actual > hi:
            dist += actual - hi
    return dist


def _matches_mode(p_pct: float, c_pct: float, f_pct: float,
                  mode: str) -> bool:
    return _mode_distance(p_pct, c_pct, f_pct, mode) == 0


def detect_diet_pattern(data_dir: str, current_mode: str,
                        ref_date: str = None, tz_offset: int = None) -> dict:
    end = date.fromisoformat(ref_date) if ref_date else date.fromisoformat(_local_date(tz_offset))

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

    avg_p = round(sum(d["protein_pct"] for d in daily_splits) / 3, 1)
    avg_c = round(sum(d["carbs_pct"] for d in daily_splits) / 3, 1)
    avg_f = round(sum(d["fat_pct"] for d in daily_splits) / 3, 1)
    avg_split = {"protein_pct": avg_p, "carbs_pct": avg_c, "fat_pct": avg_f}

    effective_current = current_mode
    if current_mode in ("if_16_8", "if_5_2"):
        effective_current = "balanced"

    current_dist = _mode_distance(avg_p, avg_c, avg_f, effective_current)

    best_mode = None
    best_dist = float("inf")
    for mode in DIET_MODE_MACROS:
        dist = _mode_distance(avg_p, avg_c, avg_f, mode)
        if dist < best_dist:
            best_dist = dist
            best_mode = mode

    all_days_match = all(
        _mode_distance(d["protein_pct"], d["carbs_pct"], d["fat_pct"], best_mode) <=
        _mode_distance(d["protein_pct"], d["carbs_pct"], d["fat_pct"], effective_current)
        for d in daily_splits
    )

    mismatch = (best_mode != effective_current
                and best_dist < current_dist
                and all_days_match)

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
                "Not recommended below 1,800 kcal/day",
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


# ---------------------------------------------------------------------------
# Food corrections
# ---------------------------------------------------------------------------

def _get_corrections_path(data_dir: str) -> str:
    """Return path to food-corrections.json, sibling to the meals data dir."""
    return os.path.join(os.path.dirname(data_dir), "food-corrections.json")


def save_correction(data_dir: str, original_foods: list, corrected_foods: list,
                    correction_type: str = "general", meal_type: str = None,
                    note: str = None, day: str = None,
                    tz_offset: int = None) -> dict:
    """Save a food correction record.

    Called when the user corrects the AI's food identification, portion estimate,
    or nutrition values. Stores the mapping so future similar meals can reference
    the corrected result.

    Args:
        data_dir: Path to the meals data directory.
        original_foods: List of food dicts as originally identified by the AI.
            Each dict: {"name": str, "calories": num, "protein": num, "carbs": num, "fat": num}
        corrected_foods: List of food dicts after user correction (same structure).
        correction_type: One of "food_identity" (wrong food name/type),
            "portion" (wrong portion size), "nutrition" (wrong calorie/macro values),
            "add_item" (user added missing food items), "remove_item" (user removed
            wrongly identified items), "general" (other corrections).
        meal_type: Optional meal type context (e.g. "breakfast", "lunch").
        note: Optional brief note about what was corrected.
        day: Optional date override (YYYY-MM-DD).
        tz_offset: Optional timezone offset in seconds.

    Returns: dict with saved status and the correction record.
    """
    path = _get_corrections_path(data_dir)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    existing: list = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            existing = json.load(f)

    resolved_day = day or _local_date(tz_offset)

    # Extract normalized keywords from both original and corrected food names
    # for future matching
    original_names = [f.get("name", "").strip().lower() for f in original_foods if f.get("name")]
    corrected_names = [f.get("name", "").strip().lower() for f in corrected_foods if f.get("name")]

    record = {
        "date": resolved_day,
        "correction_type": correction_type,
        "original_foods": original_foods,
        "corrected_foods": corrected_foods,
        "original_names": original_names,
        "corrected_names": corrected_names,
        "meal_type": meal_type,
        "note": note,
        "times_applied": 0,
    }

    # Check for duplicate: if an existing correction has the same original_names,
    # update it instead of appending
    replaced = False
    for i, rec in enumerate(existing):
        if set(rec.get("original_names", [])) == set(original_names):
            record["times_applied"] = rec.get("times_applied", 0)
            existing[i] = record
            replaced = True
            break
    if not replaced:
        existing.append(record)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    return {
        "saved": True,
        "file": path,
        "replaced_existing": replaced,
        "total_corrections": len(existing),
        "record": record,
    }


def lookup_corrections(data_dir: str, food_names: list,
                       meal_type: str = None) -> dict:
    """Look up saved corrections that match the given food names.

    Called before estimating nutrition for a new food log to check if the user
    has previously corrected similar food identifications.

    Args:
        data_dir: Path to the meals data directory.
        food_names: List of food name strings to match against saved corrections.
        meal_type: Optional meal type to filter by (e.g. "breakfast").

    Returns: dict with matched corrections (if any).
    """
    path = _get_corrections_path(data_dir)
    if not os.path.exists(path):
        return {"has_matches": False, "matches": [], "food_names_queried": food_names}

    with open(path, "r", encoding="utf-8") as f:
        corrections = json.load(f)

    query_names = [n.strip().lower() for n in food_names if n]

    matches = []
    for rec in corrections:
        orig_names = rec.get("original_names", [])
        corr_names = rec.get("corrected_names", [])

        # Match if any queried food name overlaps with original or corrected names
        # Uses substring matching for flexibility (e.g. "rice" matches "brown rice")
        score = 0
        matched_on = []
        for qn in query_names:
            for on in orig_names:
                if qn in on or on in qn:
                    score += 2  # Higher weight for matching original (the "mistake")
                    matched_on.append({"query": qn, "matched": on, "field": "original"})
            for cn in corr_names:
                if qn in cn or cn in qn:
                    score += 1
                    matched_on.append({"query": qn, "matched": cn, "field": "corrected"})

        # Optional meal_type boost
        if meal_type and rec.get("meal_type") == meal_type:
            score += 1

        if score > 0:
            matches.append({
                "score": score,
                "matched_on": matched_on,
                "correction": rec,
            })

    # Sort by score descending
    matches.sort(key=lambda m: m["score"], reverse=True)

    # Return top 5 matches
    top = matches[:5]

    return {
        "has_matches": len(top) > 0,
        "matches": top,
        "total_corrections_in_db": len(corrections),
        "food_names_queried": food_names,
    }


def apply_correction(data_dir: str, original_names: list) -> dict:
    """Increment the times_applied counter for a correction.

    Called when a previously saved correction is actually used to adjust
    a food log entry.

    Args:
        data_dir: Path to the meals data directory.
        original_names: The original_names list that identifies the correction.

    Returns: dict with update status.
    """
    path = _get_corrections_path(data_dir)
    if not os.path.exists(path):
        return {"updated": False, "reason": "no_corrections_file"}

    with open(path, "r", encoding="utf-8") as f:
        corrections = json.load(f)

    target_set = set(n.strip().lower() for n in original_names)
    updated = False
    for rec in corrections:
        if set(rec.get("original_names", [])) == target_set:
            rec["times_applied"] = rec.get("times_applied", 0) + 1
            updated = True
            break

    if updated:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(corrections, f, ensure_ascii=False, indent=2)

    return {"updated": updated, "original_names": original_names}


# Nutrition standard adjustment proposal
# ---------------------------------------------------------------------------

# Thresholds for deviation detection and consistency checks
_MACRO_DEVIATION_SINGLE = 10   # 1 macro outside range by ≥10 pp → significant
_MACRO_DEVIATION_MULTI = 6     # 2+ macros outside range by ≥6 pp → significant
_MEAL_DIST_DEVIATION = 10      # meal block differs by ≥10 pp → significant
_MACRO_CONSISTENCY = 7         # 2 days within 7 pp → consistent
_MEAL_DIST_CONSISTENCY = 10    # 2 days within 10 pp → consistent

# Nutritional guardrails for proposed standards
_MIN_PROTEIN_G_PER_KG = 1.0
_MIN_FAT_PCT = 15
_MIN_MEAL_BLOCK_PCT = 15


def _compute_day_pattern(day_meals: list, meals: int) -> dict | None:
    """Compute macro split and meal distribution for one day.

    Returns None if the day has < 500 kcal total (insufficient data).
    """
    day_meals = _migrate_meals(day_meals)
    total_cal = sum(m.get("calories", 0) for m in day_meals)
    if total_cal < 500:
        return None

    total_p = sum(m.get("protein", 0) for m in day_meals)
    total_c = sum(m.get("carbs", 0) for m in day_meals)
    total_f = sum(m.get("fat", 0) for m in day_meals)

    macro_split = {
        "protein_pct": round(total_p * 4 / total_cal * 100, 1),
        "carbs_pct": round(total_c * 4 / total_cal * 100, 1),
        "fat_pct": round(total_f * 9 / total_cal * 100, 1),
    }

    # Per-block calorie distribution
    blocks = get_meal_blocks(meals)
    block_dist = {}
    for block in blocks:
        block_cal = sum(
            m.get("calories", 0) for m in day_meals
            if resolve_meal_name(m.get("name", ""), meals) in block["meals"]
        )
        block_dist[block["label"]] = round(block_cal / total_cal * 100, 1)

    # Count main meals (non-snack) actually logged
    main_meal_names = set()
    for block in blocks:
        main_meal_names.add(block["meals"][0])
    logged_main = sum(
        1 for m in day_meals
        if resolve_meal_name(m.get("name", ""), meals) in main_meal_names
    )

    return {
        "total_calories": round(total_cal, 1),
        "macro_split": macro_split,
        "meal_distribution": block_dist,
        "main_meals_logged": logged_main,
    }


def _patterns_consistent(patterns: list) -> dict:
    """Check whether N day-patterns are similar enough to constitute a
    consistent eating habit.

    Uses max spread (max - min across days) rather than pairwise comparison.
    """
    # Macro consistency
    macro_ok = True
    macro_detail = {}
    for key in ("protein_pct", "carbs_pct", "fat_pct"):
        vals = [p["macro_split"][key] for p in patterns]
        spread = max(vals) - min(vals)
        ok = spread <= _MACRO_CONSISTENCY
        macro_detail[key] = {"spread": round(spread, 1), "ok": ok}
        if not ok:
            macro_ok = False

    # Meal distribution consistency
    dist_ok = True
    dist_detail = {}
    all_labels: set[str] = set()
    for p in patterns:
        all_labels.update(p["meal_distribution"].keys())
    for label in all_labels:
        vals = [p["meal_distribution"].get(label, 0) for p in patterns]
        spread = max(vals) - min(vals)
        ok = spread <= _MEAL_DIST_CONSISTENCY
        dist_detail[label] = {"spread": round(spread, 1), "ok": ok}
        if not ok:
            dist_ok = False

    # Meal count consistency
    counts = [p["main_meals_logged"] for p in patterns]
    count_ok = len(set(counts)) == 1

    is_consistent = macro_ok and dist_ok
    return {
        "is_consistent": is_consistent,
        "macro": {"ok": macro_ok, "detail": macro_detail},
        "meal_distribution": {"ok": dist_ok, "detail": dist_detail},
        "meal_count": {"ok": count_ok, "counts": counts},
    }


def _avg_pattern(patterns: list) -> dict:
    """Average macro split and meal distribution across patterns."""
    n = len(patterns)
    avg_macro = {}
    for key in ("protein_pct", "carbs_pct", "fat_pct"):
        avg_macro[key] = round(sum(p["macro_split"][key] for p in patterns) / n, 1)

    all_labels = set()
    for p in patterns:
        all_labels.update(p["meal_distribution"].keys())

    avg_dist = {}
    for label in all_labels:
        vals = [p["meal_distribution"].get(label, 0) for p in patterns]
        avg_dist[label] = round(sum(vals) / n, 1)

    avg_main = round(sum(p["main_meals_logged"] for p in patterns) / n, 1)

    return {
        "macro_split": avg_macro,
        "meal_distribution": avg_dist,
        "avg_main_meals": avg_main,
    }


def _check_deviation_significance(avg: dict, meals: int, mode: str,
                                   current_blocks: list) -> dict:
    """Determine whether the average pattern deviates significantly from
    current standards."""
    effective_mode = mode if mode not in ("if_16_8", "if_5_2") else "balanced"
    ranges = DIET_MODE_MACROS.get(effective_mode, DIET_MODE_MACROS["balanced"])

    # Macro deviations
    macro_devs = {}
    outside_count = 0
    large_outside = 0
    for short, key in [("protein_pct", "protein"),
                       ("carbs_pct", "carbs"),
                       ("fat_pct", "fat")]:
        actual = avg["macro_split"][short]
        lo, hi = ranges[key]
        if actual < lo:
            dev = round(lo - actual, 1)
            direction = "low"
        elif actual > hi:
            dev = round(actual - hi, 1)
            direction = "high"
        else:
            dev = 0
            direction = "on_track"
        macro_devs[key] = {"actual_pct": actual, "range": [lo, hi],
                           "deviation": dev, "direction": direction}
        if dev >= _MACRO_DEVIATION_MULTI:
            outside_count += 1
        if dev >= _MACRO_DEVIATION_SINGLE:
            large_outside += 1

    macro_significant = large_outside >= 1 or outside_count >= 2

    # Meal distribution deviations
    dist_devs = {}
    dist_significant = False
    for block in current_blocks:
        label = block["label"]
        standard_pct = block["pct"]
        actual_pct = avg["meal_distribution"].get(label, 0)
        diff = round(actual_pct - standard_pct, 1)
        is_sig = abs(diff) >= _MEAL_DIST_DEVIATION
        dist_devs[label] = {"actual_pct": actual_pct, "standard_pct": standard_pct,
                            "diff": diff, "significant": is_sig}
        if is_sig:
            dist_significant = True

    significant = macro_significant or dist_significant

    return {
        "significant": significant,
        "macro": {"significant": macro_significant, "detail": macro_devs},
        "meal_distribution": {"significant": dist_significant, "detail": dist_devs},
    }


def _round_to_5(x: float) -> int:
    """Round to nearest 5."""
    return int(round(x / 5) * 5)


def _propose_meal_blocks(avg_dist: dict, current_blocks: list) -> dict:
    """Propose new meal block percentages based on actual distribution.

    Constraints: each block ≥ _MIN_MEAL_BLOCK_PCT, total = 100%, rounded to 5.
    """
    labels = [b["label"] for b in current_blocks]
    raw = {label: avg_dist.get(label, 0) for label in labels}

    # Round to 5 with minimum enforcement
    proposed = {}
    for label in labels:
        val = max(_round_to_5(raw[label]), _MIN_MEAL_BLOCK_PCT)
        proposed[label] = val

    # Adjust to sum to 100
    total = sum(proposed.values())
    if total != 100:
        diff = 100 - total
        # Distribute difference to the largest block
        largest = max(labels, key=lambda l: proposed[l])
        proposed[largest] += diff
        # Ensure minimum still holds after adjustment
        if proposed[largest] < _MIN_MEAL_BLOCK_PCT:
            proposed[largest] = _MIN_MEAL_BLOCK_PCT

    return proposed


def _find_closest_mode(avg_macro: dict) -> tuple[str, float]:
    """Find the diet mode whose ranges best fit the average macro split."""
    p = avg_macro["protein_pct"]
    c = avg_macro["carbs_pct"]
    f = avg_macro["fat_pct"]
    best_mode = "balanced"
    best_dist = float("inf")
    for m in DIET_MODE_MACROS:
        d = _mode_distance(p, c, f, m)
        if d < best_dist:
            best_dist = d
            best_mode = m
    return best_mode, round(best_dist, 1)


def propose_standard_adjustment(data_dir: str, daily_cal: int, weight: float,
                                 meals: int, mode: str,
                                 custom_meal_blocks: dict = None,
                                 ref_date: str = None,
                                 tz_offset: int = None) -> dict:
    """Analyze the 3 most recent days of meal data to detect consistent
    deviation from current nutrition standards.

    Designed to run once on the user's 4th day of logging, after 3 complete
    days of data exist.  Always returns ``avg_pattern`` when enough data is
    available so that the caller can compose a 3-day review message.

    A concrete proposal is generated only when *all* of these hold:
    1. All 3 days have sufficient data (≥ 500 kcal, ≥ 2 main meals each)
    2. The 3 days show a consistent pattern (similar to each other)
    3. The common pattern deviates significantly from current standards
    4. A nutritionally valid adjusted standard exists
    """
    end = date.fromisoformat(ref_date) if ref_date else \
        date.fromisoformat(_local_date(tz_offset))

    current_blocks = get_meal_blocks(meals, custom_meal_blocks)

    # Load up to 3 most recent days within 7-day lookback
    days_data = []
    for offset in range(7):
        day_str = (end - timedelta(days=offset)).isoformat()
        path = get_log_path(data_dir, day_str)
        if not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            day_meals = _migrate_meals(json.load(f))
        pattern = _compute_day_pattern(day_meals, meals)
        if pattern is None:
            continue
        if pattern["main_meals_logged"] < 2:
            continue
        days_data.append({"date": day_str, "pattern": pattern})
        if len(days_data) >= 3:
            break

    if len(days_data) < 3:
        return {"has_proposal": False, "reason": "insufficient_data",
                "days_found": len(days_data)}

    all_patterns = [d["pattern"] for d in days_data]

    # Average pattern (always returned for the 3-day review)
    avg = _avg_pattern(all_patterns)

    # Consistency check
    consistency = _patterns_consistent(all_patterns)
    if not consistency["is_consistent"]:
        return {"has_proposal": False, "reason": "inconsistent_pattern",
                "avg_pattern": avg}

    # Deviation significance
    deviations = _check_deviation_significance(avg, meals, mode, current_blocks)
    if not deviations["significant"]:
        return {"has_proposal": False, "reason": "no_significant_deviation",
                "avg_pattern": avg}

    # --- Build per-dimension proposals (independent) ---
    effective_mode = mode if mode not in ("if_16_8", "if_5_2") else "balanced"
    proposals = {}

    # 1. Macro split → diet mode proposal (independent)
    if deviations["macro"]["significant"]:
        closest_mode, closest_dist = _find_closest_mode(avg["macro_split"])
        current_dist = _mode_distance(
            avg["macro_split"]["protein_pct"],
            avg["macro_split"]["carbs_pct"],
            avg["macro_split"]["fat_pct"],
            effective_mode,
        )
        if closest_mode != effective_mode and closest_dist < current_dist:
            # Validate: protein & fat floors (only apply to macro dimension)
            issues = []
            actual_protein_g = daily_cal * avg["macro_split"]["protein_pct"] / 100 / 4
            if actual_protein_g < weight * _MIN_PROTEIN_G_PER_KG:
                issues.append(
                    f"protein {round(actual_protein_g, 1)}g < "
                    f"{round(weight * _MIN_PROTEIN_G_PER_KG, 1)}g needed")
            if avg["macro_split"]["fat_pct"] < _MIN_FAT_PCT:
                issues.append(
                    f"fat {avg['macro_split']['fat_pct']}% < {_MIN_FAT_PCT}%")
            proposals["diet_mode"] = {
                "has_change": True, "valid": len(issues) == 0,
                "from": effective_mode, "to": closest_mode,
                "issues": issues,
            }
    if "diet_mode" not in proposals:
        proposals["diet_mode"] = {"has_change": False}

    # 2. Meal distribution proposal (independent)
    current_block_pcts = {b["label"]: b["pct"] for b in current_blocks}
    if deviations["meal_distribution"]["significant"]:
        new_blocks = _propose_meal_blocks(avg["meal_distribution"],
                                          current_blocks)
        if new_blocks != current_block_pcts:
            # Validate: each block ≥ minimum (only apply to distribution)
            issues = []
            for label, pct in new_blocks.items():
                if pct < _MIN_MEAL_BLOCK_PCT:
                    issues.append(f"{label} {pct}% < {_MIN_MEAL_BLOCK_PCT}%")
            proposals["meal_distribution"] = {
                "has_change": True, "valid": len(issues) == 0,
                "from": current_block_pcts, "to": new_blocks,
                "issues": issues,
            }
    if "meal_distribution" not in proposals:
        proposals["meal_distribution"] = {"has_change": False}

    # 3. Meal count proposal (independent)
    if (consistency["meal_count"]["ok"]
            and all_patterns[0]["main_meals_logged"] != meals
            and all_patterns[0]["main_meals_logged"] in (2, 3)):
        proposals["meal_count"] = {
            "has_change": True, "valid": True,
            "from": meals, "to": all_patterns[0]["main_meals_logged"],
            "issues": [],
        }
    else:
        proposals["meal_count"] = {"has_change": False}

    # Any actionable proposal?
    any_change = any(p["has_change"] for p in proposals.values())
    if not any_change:
        return {"has_proposal": False, "reason": "no_better_standard_found",
                "avg_pattern": avg}

    return {
        "avg_pattern": avg,
        "proposals": proposals,
    }


# ---------------------------------------------------------------------------
# Meal history & recommendations
# ---------------------------------------------------------------------------

def _get_recommendations_dir(data_dir: str) -> str:
    """Return the recommendations directory, sibling to data_dir."""
    return os.path.join(os.path.dirname(data_dir), "recommendations")


def meal_history(data_dir: str, meal_type: str, days: int = 30,
                 ref_date: str = None, tz_offset: int = None) -> dict:
    """Analyze meal history for a given meal type over the last N days.

    Returns top foods by frequency, average macros, recent 3 days of actual
    meals, and recent 3 days of recommendations.
    """
    end = date.fromisoformat(ref_date) if ref_date else date.fromisoformat(_local_date(tz_offset))

    food_counts: dict[str, list[float]] = {}  # name -> list of calorie values
    macro_sums = {"calories": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0}
    days_with_data = 0
    recent_3: list[dict] = []

    for offset in range(days):
        day = (end - timedelta(days=offset)).isoformat()
        path = get_log_path(data_dir, day)
        if not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            all_meals = _migrate_meals(json.load(f))

        matched = [m for m in all_meals if m.get("meal_type") == meal_type
                    or m.get("name") == meal_type]
        if not matched:
            continue

        days_with_data += 1

        for m in matched:
            macro_sums["calories"] += m.get("calories", 0)
            macro_sums["protein"] += m.get("protein", 0)
            macro_sums["carbs"] += m.get("carbs", 0)
            macro_sums["fat"] += m.get("fat", 0)

            for food in m.get("foods", []):
                fname = food.get("name", "")
                if not fname:
                    continue
                fcal = food.get("calories", 0)
                food_counts.setdefault(fname, []).append(fcal)

        if len(recent_3) < 3:
            day_foods = []
            for m in matched:
                day_foods.extend(f.get("name", "") for f in m.get("foods", [])
                                 if f.get("name"))
            recent_3.append({"date": day, "foods": day_foods})

    # Build top foods
    top_foods = sorted(food_counts.items(), key=lambda x: len(x[1]),
                       reverse=True)[:10]
    top_foods_out = [
        {"name": name, "count": len(cals),
         "avg_calories": round(sum(cals) / len(cals), 1)}
        for name, cals in top_foods
    ]

    # Average macros
    avg_macros = {k: round(v / days_with_data, 1) if days_with_data else 0
                  for k, v in macro_sums.items()}

    # Data level
    if days_with_data >= 7:
        data_level = "rich"
    elif days_with_data >= 1:
        data_level = "limited"
    else:
        data_level = "none"

    # Recent recommendations
    rec_dir = _get_recommendations_dir(data_dir)
    recent_recs: list[dict] = []
    for offset in range(days):
        if len(recent_recs) >= 3:
            break
        day = (end - timedelta(days=offset)).isoformat()
        rec_path = os.path.join(rec_dir, f"{day}.json")
        if not os.path.exists(rec_path):
            continue
        with open(rec_path, "r", encoding="utf-8") as f:
            rec_data = json.load(f)
        if meal_type in rec_data:
            entry = rec_data[meal_type]
            recent_recs.append({
                "date": day,
                "items": entry.get("items", []),
                "picked": entry.get("picked"),
            })

    return {
        "meal_type": meal_type,
        "data_level": data_level,
        "days_with_data": days_with_data,
        "top_foods": top_foods_out,
        "avg_macros": avg_macros,
        "recent_3_days": recent_3,
        "recent_recommendations": recent_recs,
    }


def save_recommendation(data_dir: str, meal_type: str, items: list,
                         day: str = None, tz_offset: int = None) -> dict:
    """Save meal recommendations for a given meal type today."""
    rec_dir = _get_recommendations_dir(data_dir)
    os.makedirs(rec_dir, exist_ok=True)
    day = day or _local_date(tz_offset)
    path = os.path.join(rec_dir, f"{day}.json")

    existing: dict = {}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            existing = json.load(f)

    existing[meal_type] = {
        "items": items,
        "picked": None,
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    return {"saved": True, "file": path, "meal_type": meal_type,
            "items": items}


# ---------------------------------------------------------------------------
# Meal type detection from timestamp + schedule
# ---------------------------------------------------------------------------

# Default time windows (3-meal mode) — used when no custom schedule provided.
# Format: (start_hour, end_hour, meal_name)
# Hours are in local time. Windows that cross midnight use end > 24.
DEFAULT_WINDOWS_3 = [
    (5,  10, "breakfast"),
    (10, 11, "snack_am"),
    (11, 14, "lunch"),
    (14, 17, "snack_pm"),
    (17, 21, "dinner"),
    (21, 29, "snack_pm"),   # 21:00 – 05:00 next day (29 = 24+5)
]

DEFAULT_WINDOWS_2 = [
    (5,  10, "meal_1"),
    (10, 11, "snack_1"),
    (11, 14, "meal_1"),
    (14, 17, "snack_2"),
    (17, 21, "meal_2"),
    (21, 29, "snack_2"),
]


def _parse_hhmm(s: str) -> float:
    """Parse 'HH:MM' to fractional hours (e.g. '09:30' → 9.5)."""
    parts = s.strip().split(":")
    return int(parts[0]) + int(parts[1]) / 60.0


def _build_schedule_windows(schedule: dict, meals: int) -> list:
    """Build time windows from a custom meal schedule.

    Strategy: each meal owns the time from the midpoint with the previous meal
    to the midpoint with the next meal. Snack detection uses a post-meal offset.

    Args:
        schedule: {"breakfast": "09:00", "lunch": "12:00", "dinner": "18:00"}
                  or {"meal_1": "12:00", "meal_2": "18:00"} for 2-meal mode.
        meals: 2 or 3.

    Returns: list of (start_hour, end_hour, meal_name) tuples.
    """
    if meals == 3:
        keys = ["breakfast", "lunch", "dinner"]
    else:
        keys = ["meal_1", "meal_2"]

    # Parse schedule times
    times = []
    for k in keys:
        if k not in schedule:
            return None  # Incomplete schedule, fall back to default
        times.append((k, _parse_hhmm(schedule[k])))

    # Sort by time (should already be in order, but be safe)
    times.sort(key=lambda x: x[1])

    windows = []
    n = len(times)
    for i in range(n):
        name, t = times[i]
        # Previous meal time (wrap around midnight)
        _, t_prev = times[(i - 1) % n]
        _, t_next = times[(i + 1) % n]

        # Midpoint with previous meal
        if i == 0:
            # First meal: midpoint with last meal of previous day
            gap_prev = (t - t_prev) % 24
            start = (t - gap_prev / 2) % 24
        else:
            gap_prev = t - t_prev
            start = t_prev + gap_prev / 2

        # Midpoint with next meal
        if i == n - 1:
            # Last meal: midpoint with first meal of next day
            gap_next = (t_next - t) % 24
            end = t + gap_next / 2
            if end < start:
                end += 24  # Crosses midnight
        else:
            gap_next = t_next - t
            end = t + gap_next / 2

        windows.append((start, end, name))

    return windows


# Snack offset: if current time is more than this many hours AFTER the main
# meal time AND that meal is already logged, classify as snack instead.
_SNACK_OFFSET_HOURS = 1.5

# Map main meal → snack name (3-meal mode)
_SNACK_MAP_3 = {
    "breakfast": "snack_am",
    "lunch": "snack_pm",
    # dinner has no snack after it in standard mode
}

_SNACK_MAP_2 = {
    "meal_1": "snack_1",
    # meal_2 has no snack after it
}


# ---------------------------------------------------------------------------
# Local date utility
# ---------------------------------------------------------------------------

def local_date_info(tz_offset: int) -> dict:
    """Return local date info: today, weekday, and current week's Mon-Sun range.

    Useful for any skill that needs the user's local date without relying
    on the LLM to compute it.
    """
    utc_now = datetime.now(timezone.utc)
    local_dt = utc_now + timedelta(seconds=tz_offset)
    today = local_dt.date()
    weekday = today.isoweekday()  # Mon=1, Sun=7
    monday = today - timedelta(days=weekday - 1)
    sunday = monday + timedelta(days=6)
    prev_monday = monday - timedelta(days=7)
    prev_sunday = monday - timedelta(days=1)

    return {
        "today": today.isoformat(),
        "weekday": today.strftime("%A"),
        "weekday_num": weekday,
        "local_time": local_dt.strftime("%H:%M:%S"),
        "current_week": {
            "monday": monday.isoformat(),
            "sunday": sunday.isoformat(),
        },
        "previous_week": {
            "monday": prev_monday.isoformat(),
            "sunday": prev_sunday.isoformat(),
        },
    }


def detect_meal(tz_offset: int, meals: int,
                schedule: dict = None,
                log: list = None,
                timestamp: str = None) -> dict:
    """Detect which meal type the current time corresponds to.

    Args:
        tz_offset: Timezone offset from UTC in seconds (e.g. 28800 for UTC+8).
        meals: 2 or 3.
        schedule: Optional custom meal schedule dict.
        log: Optional list of already-logged meals today (for snack detection).
        timestamp: Optional ISO-8601 UTC timestamp. Defaults to now.

    Returns: dict with detected_meal, local_time, local_date, method, etc.
    """
    # 1. Determine local time
    if timestamp:
        # Parse ISO timestamp — support Python 3.6+ (no fromisoformat with tz)
        ts_clean = timestamp.replace("Z", "").rstrip("+00:00").split("+")[0].split("-")
        # Try common ISO formats
        ts_bare = timestamp.replace("Z", "").split("+")[0]
        for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
            try:
                utc_dt = datetime.strptime(ts_bare, fmt).replace(tzinfo=timezone.utc)
                break
            except ValueError:
                continue
        else:
            raise ValueError(f"Cannot parse timestamp: {timestamp}")
    else:
        utc_dt = datetime.now(timezone.utc)

    local_dt = utc_dt + timedelta(seconds=tz_offset)
    local_hour = local_dt.hour + local_dt.minute / 60.0
    local_time_str = local_dt.strftime("%H:%M")
    local_date_str = local_dt.strftime("%Y-%m-%d")

    # 2. Build or select windows
    method = "default"
    windows = None
    if schedule:
        windows = _build_schedule_windows(schedule, meals)
        if windows:
            method = "schedule"

    if windows is None:
        windows = DEFAULT_WINDOWS_3 if meals == 3 else DEFAULT_WINDOWS_2

    # 3. Find which window the current time falls into
    detected = None
    win_start_str = None
    win_end_str = None

    # Normalize local_hour for windows that cross midnight
    for start, end, name in windows:
        h = local_hour
        # If window crosses midnight (end > 24), check both raw and +24
        if end > 24:
            if h < start:
                h += 24
            if start <= h < end:
                detected = name
                win_start_str = f"{int(start % 24):02d}:{int((start % 1) * 60):02d}"
                win_end_str = f"{int(end % 24):02d}:{int((end % 1) * 60):02d}"
                break
        else:
            if start <= h < end:
                detected = name
                win_start_str = f"{int(start):02d}:{int((start % 1) * 60):02d}"
                win_end_str = f"{int(end):02d}:{int((end % 1) * 60):02d}"
                break

    # Fallback if no window matched (shouldn't happen with proper windows)
    if detected is None:
        detected = "snack_pm" if meals == 3 else "snack_2"
        method = "fallback"

    # 4. Snack upgrade: if the main meal is already logged and we're past
    #    the meal time by _SNACK_OFFSET_HOURS, switch to snack.
    snack_map = _SNACK_MAP_3 if meals == 3 else _SNACK_MAP_2
    if detected in snack_map and log:
        logged_names = set()
        for m in log:
            n = m.get("name", "")
            logged_names.add(n)
            mt = m.get("meal_type", "")
            if mt:
                logged_names.add(mt)

        if detected in logged_names:
            # Main meal already logged → this is a snack
            meal_time_hour = None
            if schedule and detected in schedule:
                meal_time_hour = _parse_hhmm(schedule[detected])
            if meal_time_hour is not None and local_hour > meal_time_hour + _SNACK_OFFSET_HOURS:
                detected = snack_map[detected]

    return {
        "detected_meal": detected,
        "local_time": local_time_str,
        "local_date": local_date_str,
        "method": method,
        "window_start": win_start_str,
        "window_end": win_end_str,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Nutrition calculator")
    sub = parser.add_subparsers(dest="cmd")

    dm = sub.add_parser("detect-meal", help="Detect meal type from timestamp and schedule")
    dm.add_argument("--tz-offset", type=int, required=True,
                    help="Timezone offset from UTC in seconds (e.g. 28800 for UTC+8)")
    dm.add_argument("--meals", type=int, default=3, choices=[2, 3],
                    help="Meals per day (2 or 3)")
    dm.add_argument("--schedule", type=str, default=None,
                    help='JSON object with meal times, e.g. \'{"breakfast":"09:00","lunch":"12:00","dinner":"18:00"}\'')
    dm.add_argument("--log", type=str, default=None,
                    help='JSON array of already-logged meals today (for snack detection)')
    dm.add_argument("--timestamp", type=str, default=None,
                    help="ISO-8601 UTC timestamp of the message (default: current UTC time)")

    t = sub.add_parser("target", help="Compute daily macro targets")
    t.add_argument("--weight", type=float, required=True, help="Body weight in kg")
    t.add_argument("--cal", type=int, required=True, help="Daily calorie target (kcal)")
    t.add_argument("--meals", type=int, default=3, choices=[2, 3], help="Meals per day")
    t.add_argument("--mode", type=str, default="balanced",
                   choices=list(DIET_MODE_FAT.keys()),
                   help="Diet mode (determines fat %% range)")
    t.add_argument("--meal-blocks", type=str, default=None,
                   help='Optional JSON object with custom meal block percentages, '
                        'e.g. \'{"breakfast":25,"lunch":45,"dinner":30}\'')

    a = sub.add_parser("analyze", help="Analyze cumulative intake")
    a.add_argument("--weight", type=float, required=True)
    a.add_argument("--cal", type=int, required=True)
    a.add_argument("--meals", type=int, default=3, choices=[2, 3])
    a.add_argument("--mode", type=str, default="balanced",
                   choices=list(DIET_MODE_FAT.keys()))
    a.add_argument("--log", type=str, required=True,
                   help='JSON array of meals')
    a.add_argument("--meal-blocks", type=str, default=None,
                   help='Optional JSON object with custom meal block percentages')

    s = sub.add_parser("save", help="Save a meal record to today's log")
    s.add_argument("--data-dir", type=str, required=True, help="Directory to store daily JSON logs")
    s.add_argument("--meal", type=str, required=True, help="JSON object for the meal")
    s.add_argument("--date", type=str, default=None, help="Date override (YYYY-MM-DD)")
    s.add_argument("--tz-offset", type=int, default=None,
                   help="Timezone offset from UTC in seconds (e.g. 28800 for UTC+8). "
                        "Used to compute local date when --date is omitted.")

    l = sub.add_parser("load", help="Load today's meal records")
    l.add_argument("--data-dir", type=str, required=True, help="Directory with daily JSON logs")
    l.add_argument("--date", type=str, default=None, help="Date to load (YYYY-MM-DD), default today")
    l.add_argument("--tz-offset", type=int, default=None,
                   help="Timezone offset from UTC in seconds. "
                        "Used to compute local date when --date is omitted.")

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
    e.add_argument("--meal-blocks", type=str, default=None,
                   help='Optional JSON object with custom meal block percentages')

    cm = sub.add_parser("check-missing", help="Check for missing meals before current meal")
    cm.add_argument("--meals", type=int, default=3, choices=[2, 3])
    cm.add_argument("--current-meal", type=str, required=True)
    cm.add_argument("--log", type=str, required=True,
                   help="JSON array of all logged meals today")
    cm.add_argument("--meal-blocks", type=str, default=None,
                   help='Optional JSON object with custom meal block percentages')

    mh = sub.add_parser("meal-history",
                         help="Analyze meal history for a meal type over N days")
    mh.add_argument("--data-dir", type=str, required=True,
                    help="Directory with daily JSON logs")
    mh.add_argument("--meal-type", type=str, required=True,
                    help="Meal type to analyze (e.g. breakfast, lunch, dinner)")
    mh.add_argument("--days", type=int, default=30,
                    help="Number of days to look back (default 30)")
    mh.add_argument("--date", type=str, default=None,
                    help="End date (YYYY-MM-DD), default today")
    mh.add_argument("--tz-offset", type=int, default=None,
                    help="Timezone offset from UTC in seconds")

    sr = sub.add_parser("save-recommendation",
                         help="Save meal recommendations for today")
    sr.add_argument("--data-dir", type=str, required=True,
                    help="Directory with daily JSON logs (recommendations stored as sibling)")
    sr.add_argument("--meal-type", type=str, required=True,
                    help="Meal type (e.g. breakfast, lunch, dinner)")
    sr.add_argument("--items", type=str, required=True,
                    help="JSON array of recommendation strings")
    sr.add_argument("--date", type=str, default=None,
                    help="Date override (YYYY-MM-DD)")
    sr.add_argument("--tz-offset", type=int, default=None,
                    help="Timezone offset from UTC in seconds")

    wlc = sub.add_parser("weekly-low-cal-check",
                          help="Check if weekly average calorie intake is below BMR")
    wlc.add_argument("--data-dir", type=str, required=True,
                     help="Directory with daily JSON logs")
    wlc.add_argument("--bmr", type=float, required=True,
                     help="User's BMR in kcal/day")
    wlc.add_argument("--date", type=str, default=None,
                     help="End date for the 7-day window (YYYY-MM-DD), default today")
    wlc.add_argument("--tz-offset", type=int, default=None,
                     help="Timezone offset from UTC in seconds")

    ddp = sub.add_parser("detect-diet-pattern",
                          help="Detect if eating pattern differs from selected diet mode")
    ddp.add_argument("--data-dir", type=str, required=True,
                     help="Directory with daily JSON logs")
    ddp.add_argument("--current-mode", type=str, required=True,
                     choices=list(DIET_MODE_FAT.keys()),
                     help="User's currently selected diet mode")
    ddp.add_argument("--date", type=str, default=None,
                     help="End date for the 3-day window (YYYY-MM-DD), default today")
    ddp.add_argument("--tz-offset", type=int, default=None,
                     help="Timezone offset from UTC in seconds")

    psa = sub.add_parser("propose-standard-adjustment",
                          help="Analyze 2 consecutive days and propose adjusted nutrition standards")
    psa.add_argument("--data-dir", type=str, required=True,
                     help="Directory with daily JSON logs")
    psa.add_argument("--cal", type=int, required=True,
                     help="Current daily calorie target (kcal)")
    psa.add_argument("--weight", type=float, required=True,
                     help="User's weight in kg")
    psa.add_argument("--meals", type=int, default=3, choices=[2, 3],
                     help="Current meals per day setting")
    psa.add_argument("--mode", type=str, default="balanced",
                     choices=list(DIET_MODE_FAT.keys()),
                     help="Current diet mode")
    psa.add_argument("--meal-blocks", type=str, default=None,
                     help='Current custom meal block percentages (JSON), if any')
    psa.add_argument("--date", type=str, default=None,
                     help="End date (YYYY-MM-DD), default today — checks this date and the day before")
    psa.add_argument("--tz-offset", type=int, default=None,
                     help="Timezone offset from UTC in seconds")

    ld = sub.add_parser("local-date",
                         help="Get the user's local date, weekday, and week ranges")
    ld.add_argument("--tz-offset", type=int, required=True,
                    help="Timezone offset from UTC in seconds (e.g. 28800 for UTC+8)")

    pc = sub.add_parser("produce-check",
                         help="Evaluate cumulative vegetable and fruit intake (China region)")
    pc.add_argument("--meals", type=int, default=3, choices=[2, 3],
                    help="Meals per day (2 or 3)")
    pc.add_argument("--current-meal", type=str, required=True,
                    help="Current meal checkpoint (e.g. breakfast, lunch, dinner, meal_1, meal_2)")
    pc.add_argument("--log", type=str, required=True,
                    help="JSON array of all logged meals today (each may include vegetables_g, fruits_g)")
    sc = sub.add_parser("save-correction",
                         help="Save a food correction (when user corrects AI identification)")
    sc.add_argument("--data-dir", type=str, required=True,
                    help="Directory with daily JSON logs")
    sc.add_argument("--original", type=str, required=True,
                    help="JSON array of original food dicts as identified by AI")
    sc.add_argument("--corrected", type=str, required=True,
                    help="JSON array of corrected food dicts after user correction")
    sc.add_argument("--type", type=str, default="general",
                    choices=["food_identity", "portion", "nutrition",
                             "add_item", "remove_item", "general"],
                    help="Type of correction")
    sc.add_argument("--meal-type", type=str, default=None,
                    help="Meal type context (e.g. breakfast, lunch)")
    sc.add_argument("--note", type=str, default=None,
                    help="Brief note about the correction")
    sc.add_argument("--date", type=str, default=None,
                    help="Date override (YYYY-MM-DD)")
    sc.add_argument("--tz-offset", type=int, default=None,
                    help="Timezone offset from UTC in seconds")

    lc = sub.add_parser("lookup-corrections",
                         help="Look up saved corrections matching food names")
    lc.add_argument("--data-dir", type=str, required=True,
                    help="Directory with daily JSON logs")
    lc.add_argument("--foods", type=str, required=True,
                    help="JSON array of food name strings to match")
    lc.add_argument("--meal-type", type=str, default=None,
                    help="Optional meal type filter")

    ac = sub.add_parser("apply-correction",
                         help="Increment usage counter for a correction")
    ac.add_argument("--data-dir", type=str, required=True,
                    help="Directory with daily JSON logs")
    ac.add_argument("--original-names", type=str, required=True,
                    help="JSON array of original food name strings identifying the correction")

    args = parser.parse_args()

    if args.cmd == "detect-meal":
        sched = None
        if args.schedule:
            try:
                sched = json.loads(args.schedule)
            except json.JSONDecodeError as e:
                print(f"Error: invalid --schedule JSON: {e}", file=sys.stderr)
                sys.exit(1)
        log = None
        if args.log:
            try:
                log = json.loads(args.log)
            except json.JSONDecodeError as e:
                print(f"Error: invalid --log JSON: {e}", file=sys.stderr)
                sys.exit(1)
        result = detect_meal(args.tz_offset, args.meals, sched, log, args.timestamp)
    elif args.cmd == "target":
        mb = None
        if args.meal_blocks:
            try:
                mb = json.loads(args.meal_blocks)
            except json.JSONDecodeError as e:
                print(f"Error: invalid --meal-blocks JSON: {e}", file=sys.stderr)
                sys.exit(1)
        result = calc_targets(args.weight, args.cal, args.meals, args.mode, mb)
    elif args.cmd == "analyze":
        try:
            log = json.loads(args.log)
        except json.JSONDecodeError as e:
            print(f"Error: invalid --log JSON: {e}", file=sys.stderr)
            sys.exit(1)
        mb = None
        if args.meal_blocks:
            try:
                mb = json.loads(args.meal_blocks)
            except json.JSONDecodeError as e:
                print(f"Error: invalid --meal-blocks JSON: {e}", file=sys.stderr)
                sys.exit(1)
        result = analyze(args.weight, args.cal, args.meals, log, args.mode, mb)
    elif args.cmd == "save":
        try:
            meal = json.loads(args.meal)
        except json.JSONDecodeError as e:
            print(f"Error: invalid --meal JSON: {e}", file=sys.stderr)
            sys.exit(1)
        result = save_meal(args.data_dir, meal, args.date, getattr(args, 'tz_offset', None))
    elif args.cmd == "load":
        result = load_meals(args.data_dir, args.date, getattr(args, 'tz_offset', None))
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
        mb = None
        if args.meal_blocks:
            try:
                mb = json.loads(args.meal_blocks)
            except json.JSONDecodeError as e:
                print(f"Error: invalid --meal-blocks JSON: {e}", file=sys.stderr)
                sys.exit(1)
        result = evaluate(args.weight, args.cal, args.meals,
                          args.current_meal, log, assumed, args.mode, mb)
    elif args.cmd == "check-missing":
        try:
            log = json.loads(args.log)
        except json.JSONDecodeError as e:
            print(f"Error: invalid --log JSON: {e}", file=sys.stderr)
            sys.exit(1)
        mb = None
        if args.meal_blocks:
            try:
                mb = json.loads(args.meal_blocks)
            except json.JSONDecodeError as e:
                print(f"Error: invalid --meal-blocks JSON: {e}", file=sys.stderr)
                sys.exit(1)
        result = check_missing(args.meals, args.current_meal, log, mb)
    elif args.cmd == "meal-history":
        result = meal_history(args.data_dir, args.meal_type, args.days,
                              args.date, getattr(args, 'tz_offset', None))
    elif args.cmd == "save-recommendation":
        try:
            items = json.loads(args.items)
        except json.JSONDecodeError as e:
            print(f"Error: invalid --items JSON: {e}", file=sys.stderr)
            sys.exit(1)
        result = save_recommendation(args.data_dir, args.meal_type, items,
                                     args.date, getattr(args, 'tz_offset', None))
    elif args.cmd == "weekly-low-cal-check":
        result = weekly_low_cal_check(args.data_dir, args.bmr, args.date,
                                      getattr(args, 'tz_offset', None))
    elif args.cmd == "detect-diet-pattern":
        result = detect_diet_pattern(args.data_dir, args.current_mode, args.date,
                                     getattr(args, 'tz_offset', None))
    elif args.cmd == "propose-standard-adjustment":
        mb = None
        if args.meal_blocks:
            try:
                mb = json.loads(args.meal_blocks)
            except json.JSONDecodeError as e:
                print(f"Error: invalid --meal-blocks JSON: {e}", file=sys.stderr)
                sys.exit(1)
        result = propose_standard_adjustment(
            args.data_dir, args.cal, args.weight, args.meals,
            args.mode, mb, args.date, getattr(args, 'tz_offset', None))
    elif args.cmd == "local-date":
        result = local_date_info(args.tz_offset)
    elif args.cmd == "produce-check":
        try:
            log = json.loads(args.log)
        except json.JSONDecodeError as e:
            print(f"Error: invalid --log JSON: {e}", file=sys.stderr)
            sys.exit(1)
        result = produce_check(args.meals, args.current_meal, log)
    elif args.cmd == "save-correction":
        try:
            original = json.loads(args.original)
        except json.JSONDecodeError as e:
            print(f"Error: invalid --original JSON: {e}", file=sys.stderr)
            sys.exit(1)
        try:
            corrected = json.loads(args.corrected)
        except json.JSONDecodeError as e:
            print(f"Error: invalid --corrected JSON: {e}", file=sys.stderr)
            sys.exit(1)
        result = save_correction(args.data_dir, original, corrected,
                                 args.type, args.meal_type, args.note,
                                 args.date, getattr(args, 'tz_offset', None))
    elif args.cmd == "lookup-corrections":
        try:
            foods = json.loads(args.foods)
        except json.JSONDecodeError as e:
            print(f"Error: invalid --foods JSON: {e}", file=sys.stderr)
            sys.exit(1)
        result = lookup_corrections(args.data_dir, foods, args.meal_type)
    elif args.cmd == "apply-correction":
        try:
            orig_names = json.loads(args.original_names)
        except json.JSONDecodeError as e:
            print(f"Error: invalid --original-names JSON: {e}", file=sys.stderr)
            sys.exit(1)
        result = apply_correction(args.data_dir, orig_names)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
