# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
Weight-loss planner calculator.

Codifies all formulas from references/formulas.md into executable commands
so that the AI skill calls scripts instead of computing in-context.

Commands:
  bmi              — Compute BMI with WHO or Asian classification.
  bmr              — Compute BMR (Mifflin-St Jeor or Katch-McArdle).
  tdee             — Compute TDEE = BMR × activity multiplier (±100 kcal range).
  calorie-target   — Compute daily calorie target from TDEE and deficit rate.
  macro-targets    — Compute daily protein / fat / carb ranges for a given diet mode.
  safety-floor     — Return the calorie floor = max(BMR, 1000).
  recommend-rate   — Recommend a weekly loss rate based on total weight to lose.
  forward-calc     — Full forward calculation: rate → deficit → target → timeline.
  reverse-calc     — Full reverse calculation: timeline → rate → deficit → target.
  maintenance-tdee — Recalculate TDEE at goal weight for maintenance phase.
  unit-convert     — Convert between imperial and metric units.

Usage:
  python3 planner-calc.py bmi --weight 80 --height 178
  python3 planner-calc.py bmr --weight 80 --height 178 --age 35 --sex male
  python3 planner-calc.py tdee --weight 80 --height 178 --age 35 --sex male --activity moderately_active
  python3 planner-calc.py calorie-target --tdee 2500 --rate-kg 0.6
  python3 planner-calc.py macro-targets --weight 80 --cal 1800 --mode balanced
  python3 planner-calc.py safety-floor --bmr 1742
  python3 planner-calc.py recommend-rate --to-lose-kg 15
  python3 planner-calc.py forward-calc --weight 85 --height 178 --age 35 --sex male --activity moderately_active --target-weight 70 --mode balanced
  python3 planner-calc.py reverse-calc --weight 85 --height 178 --age 35 --sex male --activity moderately_active --target-weight 70 --deadline 2027-06-01 --mode balanced
  python3 planner-calc.py maintenance-tdee --goal-weight 70 --height 178 --age 36 --sex male --activity moderately_active
  python3 planner-calc.py unit-convert --value 170 --from lbs --to kg
"""

import argparse
import json
import math
import sys
from datetime import date, datetime, timedelta, timezone


def _local_today(tz_offset: int = None) -> date:
    """Return the user's local date. If tz_offset (seconds) is given,
    compute from UTC now; otherwise fall back to server date."""
    if tz_offset is not None:
        utc_now = datetime.now(timezone.utc)
        return (utc_now + timedelta(seconds=tz_offset)).date()
    return date.today()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ACTIVITY_MULTIPLIERS = {
    "sedentary":        1.2,
    "lightly_active":   1.3,
    "moderately_active": 1.45,
    "very_active":      1.6,
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
    "if_16_8":       (25, 35),  # defaults to balanced macro split
    "if_5_2":        (25, 35),  # defaults to balanced macro split
}

# Rate recommendation table: (min_kg, max_kg) → (rate_low, rate_high, default)
RATE_TABLE = [
    (0,   10,  0.2, 0.5, 0.35),   # < 10 kg to lose
    (10,  25,  0.5, 0.7, 0.6),    # 10–25 kg
    (25, 9999, 0.5, 1.0, 0.7),    # > 25 kg
]

ABSOLUTE_CALORIE_MINIMUM = 1000

# WHO BMI classification
BMI_WHO = [
    (0,    18.5, "Underweight"),
    (18.5, 25.0, "Normal weight"),
    (25.0, 30.0, "Overweight"),
    (30.0, 35.0, "Obese (Class I)"),
    (35.0, 40.0, "Obese (Class II)"),
    (40.0, 999,  "Obese (Class III)"),
]

# Asian BMI classification
BMI_ASIAN = [
    (0,    18.5, "Underweight"),
    (18.5, 24.0, "Normal weight"),
    (24.0, 28.0, "Overweight"),
    (28.0, 999,  "Obese"),
]


# ---------------------------------------------------------------------------
# Core calculations
# ---------------------------------------------------------------------------

def calc_bmi(weight_kg: float, height_cm: float) -> float:
    height_m = height_cm / 100
    return round(weight_kg / (height_m ** 2), 1)


def classify_bmi(bmi: float, standard: str = "who") -> str:
    table = BMI_ASIAN if standard == "asian" else BMI_WHO
    for lo, hi, label in table:
        if lo <= bmi < hi:
            return label
    return "Unknown"


def calc_bmr_mifflin(weight_kg: float, height_cm: float,
                     age: int, sex: str) -> float:
    """Mifflin-St Jeor equation."""
    base = (10 * weight_kg) + (6.25 * height_cm) - (5 * age)
    if sex == "male":
        return round(base + 5, 1)
    return round(base - 161, 1)


def calc_bmr_katch(weight_kg: float, body_fat_pct: float) -> float:
    """Katch-McArdle equation (requires body fat %)."""
    lbm = weight_kg * (1 - body_fat_pct / 100)
    return round(370 + (21.6 * lbm), 1)


def calc_tdee(bmr: float, activity: str) -> dict:
    multiplier = ACTIVITY_MULTIPLIERS.get(activity, 1.2)
    point = round(bmr * multiplier)
    return {
        "bmr": bmr,
        "activity": activity,
        "multiplier": multiplier,
        "tdee": point,
        "tdee_low": point - 100,
        "tdee_high": point + 100,
    }


def calc_safety_floor(bmr: float) -> int:
    return max(round(bmr), ABSOLUTE_CALORIE_MINIMUM)


def recommend_rate(to_lose_kg: float) -> dict:
    for min_kg, max_kg, lo, hi, default in RATE_TABLE:
        if min_kg <= to_lose_kg < max_kg:
            return {
                "to_lose_kg": round(to_lose_kg, 1),
                "rate_low_kg": lo,
                "rate_high_kg": hi,
                "rate_default_kg": default,
                "rate_low_lbs": round(lo * 2.205, 1),
                "rate_high_lbs": round(hi * 2.205, 1),
                "rate_default_lbs": round(default * 2.205, 1),
            }
    # fallback
    return {"to_lose_kg": round(to_lose_kg, 1),
            "rate_default_kg": 0.5, "rate_low_kg": 0.2, "rate_high_kg": 1.0,
            "rate_default_lbs": 1.1, "rate_low_lbs": 0.4, "rate_high_lbs": 2.2}


def calc_calorie_target(tdee: int, rate_kg_per_week: float) -> dict:
    """Daily calorie target from TDEE and weekly loss rate (kg)."""
    # 1 kg ≈ 7700 kcal → daily deficit = rate × 7700 / 7 = rate × 1100
    # Simplified: 0.5 kg/wk ≈ 550/day, 1 kg/wk ≈ 1100/day
    daily_deficit = round(rate_kg_per_week * 1100)
    daily_cal = tdee - daily_deficit
    return {
        "tdee": tdee,
        "rate_kg_per_week": rate_kg_per_week,
        "daily_deficit": daily_deficit,
        "daily_cal": daily_cal,
        "daily_cal_range": {"min": daily_cal - 100, "max": daily_cal + 100},
    }


def calc_macro_targets(weight_kg: float, daily_cal: int,
                       mode: str = "balanced", meals: int = 3) -> dict:
    """Compute protein / fat / carb ranges for a given diet mode."""
    fat_lo_pct, fat_hi_pct = DIET_MODE_FAT.get(mode, (25, 35))
    fat_mid_pct = (fat_lo_pct + fat_hi_pct) / 2

    # Protein: always body-weight-based
    protein_lo = round(weight_kg * 1.2, 1)
    protein_hi = round(weight_kg * 1.6, 1)
    protein_mid = round(weight_kg * 1.4, 1)

    # Fat
    fat_lo = round(daily_cal * fat_lo_pct / 100 / 9, 1)
    fat_hi = round(daily_cal * fat_hi_pct / 100 / 9, 1)
    fat_mid = round(daily_cal * fat_mid_pct / 100 / 9, 1)

    # Carbs: fill remainder
    carb_mid = round((daily_cal - protein_mid * 4 - fat_mid * 9) / 4, 1)
    carb_max = round((daily_cal - protein_lo * 4 - fat_lo * 9) / 4, 1)
    carb_min = round((daily_cal - protein_hi * 4 - fat_hi * 9) / 4, 1)

    # Calorie range ±100
    cal_lo = daily_cal - 100
    cal_hi = daily_cal + 100

    # Per-meal allocation
    if meals == 3:
        alloc = [
            {"meal": "breakfast", "pct": 30, "cal": round(daily_cal * 0.30)},
            {"meal": "lunch",     "pct": 40, "cal": round(daily_cal * 0.40)},
            {"meal": "dinner",    "pct": 30, "cal": round(daily_cal * 0.30)},
        ]
    else:
        alloc = [
            {"meal": "meal_1", "pct": 50, "cal": round(daily_cal * 0.50)},
            {"meal": "meal_2", "pct": 50, "cal": round(daily_cal * 0.50)},
        ]

    return {
        "daily_cal": daily_cal,
        "cal_range": {"min": cal_lo, "max": cal_hi},
        "diet_mode": mode,
        "fat_pct_range": {"min": fat_lo_pct, "max": fat_hi_pct},
        "protein": {"min": protein_lo, "target": protein_mid, "max": protein_hi, "unit": "g"},
        "fat":     {"min": fat_lo,     "target": fat_mid,     "max": fat_hi,     "unit": "g"},
        "carb":    {"min": carb_min,   "target": carb_mid,    "max": carb_max,   "unit": "g"},
        "allocation": alloc,
    }


def forward_calc(weight_kg: float, height_cm: float, age: int, sex: str,
                 activity: str, target_weight_kg: float,
                 mode: str = "balanced", meals: int = 3,
                 bmi_standard: str = "who", tz_offset: int = None) -> dict:
    """Full forward calculation: no timeline given → recommend rate → derive timeline."""
    bmr = calc_bmr_mifflin(weight_kg, height_cm, age, sex)
    tdee_info = calc_tdee(bmr, activity)
    tdee = tdee_info["tdee"]

    to_lose = round(weight_kg - target_weight_kg, 1)
    rate_info = recommend_rate(to_lose)
    rate = rate_info["rate_default_kg"]

    cal_info = calc_calorie_target(tdee, rate)
    daily_cal = cal_info["daily_cal"]

    floor = calc_safety_floor(bmr)
    floor_clamped = False
    if daily_cal < floor:
        floor_clamped = True
        daily_cal = floor
        # Back-calculate max safe rate from floor
        max_deficit = tdee - floor
        rate = round(max_deficit / 1100, 2)
        cal_info = calc_calorie_target(tdee, rate)
        cal_info["daily_cal"] = floor
        cal_info["daily_cal_range"] = {"min": floor - 100, "max": floor + 100}

    weeks = round(to_lose / rate, 1) if rate > 0 else 0
    completion = _add_weeks(_local_today(tz_offset), weeks)

    bmi_current = calc_bmi(weight_kg, height_cm)
    bmi_target = calc_bmi(target_weight_kg, height_cm)

    macros = calc_macro_targets(weight_kg, daily_cal, mode, meals)

    # Maintenance TDEE at goal weight
    maint_bmr = calc_bmr_mifflin(target_weight_kg, height_cm, age + math.ceil(weeks / 52), sex)
    maint_tdee = calc_tdee(maint_bmr, activity)

    return {
        "bmi_current": bmi_current,
        "bmi_current_class": classify_bmi(bmi_current, bmi_standard),
        "bmi_target": bmi_target,
        "bmi_target_class": classify_bmi(bmi_target, bmi_standard),
        "bmi_standard": bmi_standard,
        "bmr": bmr,
        "tdee": tdee_info,
        "calorie_floor": floor,
        "floor_clamped": floor_clamped,
        "to_lose_kg": to_lose,
        "rate_kg_per_week": rate,
        "rate_lbs_per_week": round(rate * 2.205, 1),
        "daily_deficit": cal_info["daily_deficit"],
        "daily_cal": daily_cal,
        "daily_cal_range": cal_info["daily_cal_range"],
        "macros": macros,
        "weeks": weeks,
        "estimated_completion": completion,
        "maintenance_tdee": maint_tdee["tdee"],
    }


def reverse_calc(weight_kg: float, height_cm: float, age: int, sex: str,
                 activity: str, target_weight_kg: float, deadline: str,
                 mode: str = "balanced", meals: int = 3,
                 bmi_standard: str = "who", tz_offset: int = None) -> dict:
    """Reverse calculation: timeline given → derive required rate."""
    bmr = calc_bmr_mifflin(weight_kg, height_cm, age, sex)
    tdee_info = calc_tdee(bmr, activity)
    tdee = tdee_info["tdee"]

    to_lose = round(weight_kg - target_weight_kg, 1)
    deadline_date = date.fromisoformat(deadline)
    available_days = (deadline_date - _local_today(tz_offset)).days
    available_weeks = available_days / 7 if available_days > 0 else 1

    required_rate = round(to_lose / available_weeks, 2)

    # Safety checks
    rate_safe = required_rate <= 1.0
    floor = calc_safety_floor(bmr)
    cal_info = calc_calorie_target(tdee, required_rate)
    daily_cal = cal_info["daily_cal"]
    cal_safe = daily_cal >= floor

    # If unsafe, compute the closest safe rate
    safe_rate = required_rate
    safe_daily_cal = daily_cal
    safe_weeks = available_weeks
    if not rate_safe:
        safe_rate = 1.0
    if not cal_safe:
        max_deficit = tdee - floor
        safe_rate = min(safe_rate, round(max_deficit / 1100, 2))
        safe_daily_cal = floor
    if safe_rate != required_rate:
        safe_weeks = round(to_lose / safe_rate, 1) if safe_rate > 0 else 0
        safe_daily_cal = max(tdee - round(safe_rate * 1100), floor)

    bmi_current = calc_bmi(weight_kg, height_cm)
    bmi_target = calc_bmi(target_weight_kg, height_cm)

    macros = calc_macro_targets(weight_kg, max(daily_cal, floor), mode, meals)

    return {
        "bmi_current": bmi_current,
        "bmi_current_class": classify_bmi(bmi_current, bmi_standard),
        "bmi_target": bmi_target,
        "bmi_target_class": classify_bmi(bmi_target, bmi_standard),
        "bmi_standard": bmi_standard,
        "bmr": bmr,
        "tdee": tdee_info,
        "calorie_floor": floor,
        "to_lose_kg": to_lose,
        "deadline": deadline,
        "available_weeks": round(available_weeks, 1),
        "required_rate_kg": required_rate,
        "required_rate_lbs": round(required_rate * 2.205, 1),
        "rate_safe": rate_safe,
        "cal_safe": cal_safe,
        "required_daily_cal": daily_cal,
        "safe_rate_kg": safe_rate,
        "safe_daily_cal": safe_daily_cal,
        "safe_weeks": safe_weeks,
        "safe_completion": _add_weeks(_local_today(tz_offset), safe_weeks),
        "macros": macros,
    }


def maintenance_tdee(goal_weight_kg: float, height_cm: float,
                     age: int, sex: str, activity: str) -> dict:
    bmr = calc_bmr_mifflin(goal_weight_kg, height_cm, age, sex)
    tdee_info = calc_tdee(bmr, activity)
    return {
        "goal_weight_kg": goal_weight_kg,
        "bmr": bmr,
        "maintenance_tdee": tdee_info["tdee"],
        "maintenance_range": {
            "min": tdee_info["tdee_low"],
            "max": tdee_info["tdee_high"],
        },
    }


def unit_convert(value: float, from_unit: str, to_unit: str) -> dict:
    conversions = {
        ("lbs", "kg"): lambda v: v / 2.205,
        ("kg", "lbs"): lambda v: v * 2.205,
        ("ft_in", "cm"): None,  # handled specially
        ("cm", "ft_in"): None,
        ("in", "cm"): lambda v: v * 2.54,
        ("cm", "in"): lambda v: v / 2.54,
    }
    key = (from_unit, to_unit)
    fn = conversions.get(key)
    if fn is None:
        return {"error": f"Unsupported conversion: {from_unit} → {to_unit}"}
    result = round(fn(value), 2)
    return {"input": value, "from": from_unit, "to": to_unit, "result": result}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _add_weeks(start: date, weeks: float) -> str:
    """Add fractional weeks to a date and return ISO string."""
    days = round(weeks * 7)
    from datetime import timedelta
    return (start + timedelta(days=days)).isoformat()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Weight-loss planner calculator")
    sub = parser.add_subparsers(dest="cmd")

    # --- bmi ---
    p = sub.add_parser("bmi", help="Compute BMI")
    p.add_argument("--weight", type=float, required=True, help="kg")
    p.add_argument("--height", type=float, required=True, help="cm")
    p.add_argument("--standard", choices=["who", "asian"], default="who")

    # --- bmr ---
    p = sub.add_parser("bmr", help="Compute BMR")
    p.add_argument("--weight", type=float, required=True, help="kg")
    p.add_argument("--height", type=float, required=True, help="cm")
    p.add_argument("--age", type=int, required=True)
    p.add_argument("--sex", choices=["male", "female"], required=True)
    p.add_argument("--body-fat", type=float, default=None,
                   help="Body fat %% for Katch-McArdle (optional)")

    # --- tdee ---
    p = sub.add_parser("tdee", help="Compute TDEE")
    p.add_argument("--weight", type=float, required=True, help="kg")
    p.add_argument("--height", type=float, required=True, help="cm")
    p.add_argument("--age", type=int, required=True)
    p.add_argument("--sex", choices=["male", "female"], required=True)
    p.add_argument("--activity", required=True,
                   choices=list(ACTIVITY_MULTIPLIERS.keys()))
    p.add_argument("--body-fat", type=float, default=None)

    # --- calorie-target ---
    p = sub.add_parser("calorie-target", help="Compute daily calorie target")
    p.add_argument("--tdee", type=int, required=True)
    p.add_argument("--rate-kg", type=float, required=True,
                   help="Weekly loss rate in kg")

    # --- macro-targets ---
    p = sub.add_parser("macro-targets", help="Compute macro targets")
    p.add_argument("--weight", type=float, required=True, help="kg")
    p.add_argument("--cal", type=int, required=True, help="Daily calorie target (kcal)")
    p.add_argument("--mode", default="balanced",
                   choices=list(DIET_MODE_FAT.keys()))
    p.add_argument("--meals", type=int, default=3, choices=[2, 3])

    # --- safety-floor ---
    p = sub.add_parser("safety-floor", help="Compute calorie floor")
    p.add_argument("--bmr", type=float, required=True)

    # --- recommend-rate ---
    p = sub.add_parser("recommend-rate", help="Recommend weekly loss rate")
    p.add_argument("--to-lose-kg", type=float, required=True)

    # --- forward-calc ---
    p = sub.add_parser("forward-calc", help="Full forward calculation")
    p.add_argument("--weight", type=float, required=True, help="Current weight kg")
    p.add_argument("--height", type=float, required=True, help="Height cm")
    p.add_argument("--age", type=int, required=True)
    p.add_argument("--sex", choices=["male", "female"], required=True)
    p.add_argument("--activity", required=True,
                   choices=list(ACTIVITY_MULTIPLIERS.keys()))
    p.add_argument("--target-weight", type=float, required=True, help="Goal weight kg")
    p.add_argument("--mode", default="balanced",
                   choices=list(DIET_MODE_FAT.keys()))
    p.add_argument("--meals", type=int, default=3, choices=[2, 3])
    p.add_argument("--bmi-standard", choices=["who", "asian"], default="who")
    p.add_argument("--tz-offset", type=int, default=None,
                   help="Timezone offset from UTC in seconds")

    # --- reverse-calc ---
    p = sub.add_parser("reverse-calc", help="Reverse calculation from deadline")
    p.add_argument("--weight", type=float, required=True, help="Current weight kg")
    p.add_argument("--height", type=float, required=True, help="Height cm")
    p.add_argument("--age", type=int, required=True)
    p.add_argument("--sex", choices=["male", "female"], required=True)
    p.add_argument("--activity", required=True,
                   choices=list(ACTIVITY_MULTIPLIERS.keys()))
    p.add_argument("--target-weight", type=float, required=True, help="Goal weight kg")
    p.add_argument("--deadline", type=str, required=True, help="YYYY-MM-DD")
    p.add_argument("--mode", default="balanced",
                   choices=list(DIET_MODE_FAT.keys()))
    p.add_argument("--meals", type=int, default=3, choices=[2, 3])
    p.add_argument("--bmi-standard", choices=["who", "asian"], default="who")
    p.add_argument("--tz-offset", type=int, default=None,
                   help="Timezone offset from UTC in seconds")

    # --- maintenance-tdee ---
    p = sub.add_parser("maintenance-tdee", help="TDEE at goal weight")
    p.add_argument("--goal-weight", type=float, required=True, help="kg")
    p.add_argument("--height", type=float, required=True, help="cm")
    p.add_argument("--age", type=int, required=True)
    p.add_argument("--sex", choices=["male", "female"], required=True)
    p.add_argument("--activity", required=True,
                   choices=list(ACTIVITY_MULTIPLIERS.keys()))

    # --- unit-convert ---
    p = sub.add_parser("unit-convert", help="Convert units")
    p.add_argument("--value", type=float, required=True)
    p.add_argument("--from", dest="from_unit", required=True,
                   choices=["lbs", "kg", "in", "cm"])
    p.add_argument("--to", dest="to_unit", required=True,
                   choices=["lbs", "kg", "in", "cm"])

    args = parser.parse_args()
    if not args.cmd:
        parser.print_help()
        sys.exit(1)

    result = None

    if args.cmd == "bmi":
        bmi = calc_bmi(args.weight, args.height)
        result = {
            "bmi": bmi,
            "classification": classify_bmi(bmi, args.standard),
            "standard": args.standard,
        }

    elif args.cmd == "bmr":
        if args.body_fat is not None:
            bmr = calc_bmr_katch(args.weight, args.body_fat)
            method = "katch_mcardle"
        else:
            bmr = calc_bmr_mifflin(args.weight, args.height, args.age, args.sex)
            method = "mifflin_st_jeor"
        result = {"bmr": bmr, "method": method}

    elif args.cmd == "tdee":
        if args.body_fat is not None:
            bmr = calc_bmr_katch(args.weight, args.body_fat)
        else:
            bmr = calc_bmr_mifflin(args.weight, args.height, args.age, args.sex)
        result = calc_tdee(bmr, args.activity)

    elif args.cmd == "calorie-target":
        result = calc_calorie_target(args.tdee, args.rate_kg)

    elif args.cmd == "macro-targets":
        result = calc_macro_targets(args.weight, args.cal, args.mode, args.meals)

    elif args.cmd == "safety-floor":
        floor = calc_safety_floor(args.bmr)
        result = {"bmr": args.bmr, "calorie_floor": floor,
                  "absolute_minimum": ABSOLUTE_CALORIE_MINIMUM}

    elif args.cmd == "recommend-rate":
        result = recommend_rate(args.to_lose_kg)

    elif args.cmd == "forward-calc":
        result = forward_calc(
            args.weight, args.height, args.age, args.sex,
            args.activity, args.target_weight,
            args.mode, args.meals, args.bmi_standard,
            getattr(args, 'tz_offset', None),
        )

    elif args.cmd == "reverse-calc":
        result = reverse_calc(
            args.weight, args.height, args.age, args.sex,
            args.activity, args.target_weight, args.deadline,
            args.mode, args.meals, args.bmi_standard,
            getattr(args, 'tz_offset', None),
        )

    elif args.cmd == "maintenance-tdee":
        result = maintenance_tdee(
            args.goal_weight, args.height, args.age, args.sex, args.activity,
        )

    elif args.cmd == "unit-convert":
        result = unit_convert(args.value, args.from_unit, args.to_unit)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
