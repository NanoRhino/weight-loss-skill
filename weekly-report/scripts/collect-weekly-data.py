#!/usr/bin/env python3
"""
collect-weekly-data.py — One-shot data collector for weekly reports.

Replaces 7+ individual nutrition-calc.py calls + weight-tracker.py + exercise-calc.py
with a single script that outputs all weekly data as JSON.

Usage:
  python3 collect-weekly-data.py \
    --workspace-dir <path> \
    --start-date 2026-04-14 \
    --end-date 2026-04-20 \
    --tz-offset 28800

Output: JSON to stdout with all data needed for report generation.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone


def log(msg):
    print(f"[collect-weekly-data] {msg}", file=sys.stderr)


def _normalize_path(p):
    """Lowercase wechat-dm/wecom-dm segment to avoid case-mismatch directories."""
    import re as _re
    return _re.sub(
        r'(workspace-(?:wechat|wecom)-dm-)([^/]+)',
        lambda m: m.group(1) + m.group(2).lower(), p
    )


def find_script(skills_base, skill_name, script_name):
    """Find a script in the skills directory."""
    path = os.path.join(skills_base, skill_name, "scripts", script_name)
    if os.path.exists(path):
        return path
    return None


def run_script(cmd, timeout=15):
    """Run a script and return parsed JSON or None on error."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        if result.returncode != 0:
            log(f"Script error: {' '.join(cmd[:3])}... → {result.stderr.strip()[:100]}")
            return None
        output = result.stdout.strip()
        if not output:
            return None
        return json.loads(output)
    except (json.JSONDecodeError, subprocess.TimeoutExpired, Exception) as e:
        log(f"Script failed: {e}")
        return None


def collect_meals(nutrition_calc, data_dir, start_date, end_date, tz_offset):
    """Collect meal data for each day in the range."""
    days = []
    current = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")

    while current <= end:
        date_str = current.strftime("%Y-%m-%d")
        weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        weekday = weekday_names[current.weekday()]

        # Try loading from file directly first (faster than subprocess)
        meal_file = os.path.join(data_dir, f"{date_str}.json")
        day_data = {
            "date": date_str,
            "weekday": weekday,
            "logged": False,
            "meals": [],
            "totals": {"cal": 0, "protein": 0, "fat": 0, "carb": 0, "fiber": 0}
        }

        if os.path.exists(meal_file):
            try:
                with open(meal_file) as f:
                    raw = json.load(f)

                meals = []
                # Handle both list and dict formats
                if isinstance(raw, dict):
                    for key, val in raw.items():
                        if isinstance(val, dict) and ("items" in val or "foods" in val):
                            items = val.get("items") or val.get("foods") or []
                            meal_cal = sum(i.get("calories", 0) or i.get("cal", 0) or 0 for i in items if isinstance(i, dict))
                            meal_protein = sum((i.get("protein_g") or i.get("protein") or 0) for i in items if isinstance(i, dict))
                            meal_fat = sum((i.get("fat_g") or i.get("fat") or 0) for i in items if isinstance(i, dict))
                            meal_carb = sum((i.get("carb_g") or i.get("carb") or i.get("carbs") or 0) for i in items if isinstance(i, dict))
                            meal_fiber = sum(i.get("fiber", 0) or 0 for i in items if isinstance(i, dict))
                            foods = [i.get("name", "?") for i in items if isinstance(i, dict)]
                            meals.append({
                                "meal_type": key,
                                "cal": round(meal_cal),
                                "protein": round(meal_protein, 1),
                                "fat": round(meal_fat, 1),
                                "carb": round(meal_carb, 1),
                                "fiber": round(meal_fiber, 1),
                                "foods": foods
                            })
                elif isinstance(raw, list):
                    for item in raw:
                        if isinstance(item, dict):
                            items_list = item.get("items") or item.get("foods") or []
                            if items_list:
                                meal_cal = sum(i.get("calories", 0) or i.get("cal", 0) or 0 for i in items_list if isinstance(i, dict))
                                meal_protein = sum((i.get("protein_g") or i.get("protein") or 0) for i in items_list if isinstance(i, dict))
                                meal_fat = sum((i.get("fat_g") or i.get("fat") or 0) for i in items_list if isinstance(i, dict))
                                meal_carb = sum((i.get("carb_g") or i.get("carb") or i.get("carbs") or 0) for i in items_list if isinstance(i, dict))
                                meal_fiber = sum(i.get("fiber", 0) or 0 for i in items_list if isinstance(i, dict))
                                foods = [i.get("name", "?") for i in items_list if isinstance(i, dict)]
                            else:
                                meal_cal = item.get("cal", 0) or item.get("calories", 0) or 0
                                meal_protein = (item.get("protein_g") or item.get("protein") or 0)
                                meal_fat = (item.get("fat_g") or item.get("fat") or 0)
                                meal_carb = (item.get("carb_g") or item.get("carb") or item.get("carbs") or 0)
                                meal_fiber = item.get("fiber", 0) or 0
                                foods = []
                            meals.append({
                                "meal_type": item.get("meal_type") or item.get("name", "unknown"),
                                "cal": round(meal_cal),
                                "protein": round(meal_protein, 1),
                                "fat": round(meal_fat, 1),
                                "carb": round(meal_carb, 1),
                                "fiber": round(meal_fiber, 1),
                                "foods": foods
                            })

                if meals:
                    day_data["logged"] = True
                    day_data["meals"] = meals
                    day_data["totals"] = {
                        "cal": round(sum(m["cal"] for m in meals)),
                        "protein": round(sum(m["protein"] for m in meals), 1),
                        "fat": round(sum(m["fat"] for m in meals), 1),
                        "carb": round(sum(m["carb"] for m in meals), 1),
                        "fiber": round(sum(m["fiber"] for m in meals), 1),
                    }
            except (json.JSONDecodeError, IOError) as e:
                log(f"Error reading {meal_file}: {e}")

        days.append(day_data)
        current += timedelta(days=1)

    return days


def collect_weight(weight_tracker, data_dir, start_date, end_date, display_unit):
    """Collect weight data for the date range."""
    if not weight_tracker:
        return {"readings": [], "change": None}

    data = run_script([
        sys.executable, weight_tracker, "load",
        "--data-dir", data_dir,
        "--from", start_date, "--to", end_date,
        "--display-unit", display_unit
    ])

    if not data or not isinstance(data, list):
        return {"readings": [], "change": None}

    readings = data
    change = None
    if len(readings) >= 2:
        change = round(readings[-1]["value"] - readings[0]["value"], 2)

    return {"readings": readings, "change": change}


def collect_exercise(exercise_calc, data_dir, start_date, end_date):
    """Collect exercise data for the date range."""
    if not exercise_calc:
        return {"sessions": [], "total_calories": 0, "total_minutes": 0}

    data = run_script([
        sys.executable, exercise_calc, "load",
        "--data-dir", data_dir,
        "--from", start_date, "--to", end_date
    ])

    if not data or not isinstance(data, list):
        return {"sessions": [], "total_calories": 0, "total_minutes": 0}

    total_cal = sum(s.get("net_calories_kcal", 0) or s.get("calories", 0) or 0 for s in data)
    total_min = sum(s.get("duration_min", 0) or 0 for s in data)

    return {
        "sessions": data,
        "total_calories": total_cal,
        "total_minutes": total_min
    }


def collect_habits(workspace_dir, start_date, end_date):
    """Collect habit data for the date range."""
    habits_file = os.path.join(workspace_dir, "habits.json")
    if not os.path.exists(habits_file):
        return {"active": [], "daily_log": {}}

    try:
        with open(habits_file) as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"active": [], "daily_log": {}}

    active = data.get("active", [])
    daily_log = data.get("daily_log", {})

    # Filter daily_log to only include dates in range
    current = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    filtered_log = {}
    while current <= end:
        ds = current.strftime("%Y-%m-%d")
        if ds in daily_log:
            filtered_log[ds] = daily_log[ds]
        current += timedelta(days=1)

    return {"active": active, "daily_log": filtered_log, "graduated": data.get("graduated", [])}


def read_plan(workspace_dir):
    """Read PLAN.md and extract key fields. Falls back to health-profile.md for reasonable defaults."""
    plan_path = os.path.join(workspace_dir, "PLAN.md")
    plan = None

    if os.path.exists(plan_path):
        try:
            with open(plan_path) as f:
                content = f.read()
        except IOError:
            content = ""

        plan = {}
        import re

        patterns = {
            "cal_min": r"Daily Calorie Range[:\s]*(\d[\d,]*)\s*[-–]\s*(\d[\d,]*)",
            "cal_target_single": r"(?:每日热量目标|Daily Calorie Target|Calorie Target|热量目标)[：:\s]*([\d,]+)",
            "tdee": r"TDEE[:\s]*([\d,]+)",
            "bmr": r"BMR[:\s]*([\d,]+)",
            "deficit": r"Daily Calorie Deficit[:\s]*([\d,]+)",
            "protein_range": r"(?:Protein|蛋白质)[：:\s]*(\d+)\s*[-–]\s*(\d+)\s*g",
            "fat_range": r"(?:Fat|脂肪)[：:\s]*(\d+)\s*[-–]\s*(\d+)\s*g",
            "carb_range": r"(?:Carb|碳水)[：:\s]*(\d+)\s*[-–]\s*(\d+)\s*g",
            "weight_loss_rate": r"(?:Weight Loss Rate|每周减重)[：:\s]*([\d.]+)",
            "target_weight": r"(?:Target Weight|目标体重)[：:\s]*([\d.]+)",
            "start_weight": r"(?:Start|Initial|Starting|初始) ?(?:Weight|体重)[：:\s]*([\d.]+)",
        }

        for key, pattern in patterns.items():
            m = re.search(pattern, content, re.IGNORECASE)
            if m:
                groups = m.groups()
                if len(groups) == 2:
                    plan[key] = [int(groups[0].replace(",", "")), int(groups[1].replace(",", ""))]
                else:
                    try:
                        plan[key] = float(groups[0].replace(",", ""))
                    except ValueError:
                        plan[key] = groups[0].replace(",", "")

        # Convert single calorie target to range if no range was found
        if "cal_min" not in plan and "cal_target_single" in plan:
            target = int(plan.pop("cal_target_single"))
            plan["cal_min"] = [round(target * 0.9), round(target * 1.1)]
        elif "cal_target_single" in plan:
            plan.pop("cal_target_single")  # range takes priority

        if not plan:
            plan = None

    # Fallback: derive reasonable targets from health-profile.md
    if plan is None:
        plan = {}

    plan = _fill_macro_defaults(workspace_dir, plan)
    return plan if plan else None


def _fill_macro_defaults(workspace_dir, plan):
    """Fill in missing macro targets from health-profile.md using standard formulas."""
    hp_path = os.path.join(workspace_dir, "health-profile.md")
    if not os.path.exists(hp_path):
        return plan

    try:
        with open(hp_path) as f:
            content = f.read()
    except IOError:
        return plan

    import re

    # Extract weight (current or target for calculation)
    weight = None
    weight_match = re.search(r"Weight to Lose[:\s]*([\d.]+)", content)
    target_match = re.search(r"Target Weight[:\s]*([\d.]+)", content)

    # Try to get current weight from weight.json
    weight_file = os.path.join(workspace_dir, "data", "weight.json")
    if os.path.exists(weight_file):
        try:
            with open(weight_file) as f:
                wd = json.load(f)
            if isinstance(wd, dict):
                # Get latest reading
                readings = [(k, v) for k, v in wd.items() if isinstance(v, dict) and "value" in v]
                if readings:
                    readings.sort(key=lambda x: x[0])
                    weight = readings[-1][1]["value"]
        except (json.JSONDecodeError, IOError):
            pass

    if weight is None and target_match:
        weight = float(target_match.group(1))
    if weight is None:
        weight = 65  # safe default

    # Detect diet mode
    diet_mode = "balanced"
    if "high_protein" in content.lower() or "高蛋白" in content:
        diet_mode = "high_protein"
    elif "low_carb" in content.lower() or "低碳" in content:
        diet_mode = "low_carb"

    # Default calorie range if missing
    if "cal_min" not in plan:
        # Try health-profile.json first
        hp_json_path = os.path.join(workspace_dir, "data", "health-profile.json")
        cal_from_json = None
        if os.path.exists(hp_json_path):
            try:
                with open(hp_json_path) as f:
                    hp_data = json.load(f)
                cal_from_json = hp_data.get("calorie_target")
            except (json.JSONDecodeError, IOError):
                pass

        if cal_from_json and cal_from_json > 0:
            # Use calorie_target as center, ±10% range
            plan["cal_min"] = [round(cal_from_json * 0.9), round(cal_from_json * 1.1)]
        else:
            # Standard deficit: BMR~1400-1650 for most users, target 1600-2000
            plan["cal_min"] = [1600, 2000]

    cal_mid = (plan["cal_min"][0] + plan["cal_min"][1]) / 2

    # Protein target (g)
    # Weight loss: 1.2-1.6 g/kg (preserve muscle mass)
    # High protein mode: 1.6-2.0 g/kg
    if "protein_range" not in plan:
        if diet_mode == "high_protein":
            plan["protein_range"] = [round(weight * 1.6), round(weight * 2.0)]
        else:
            plan["protein_range"] = [round(weight * 1.2), round(weight * 1.6)]

    # Fat target (g) — 20-30% of calories (lower end for weight loss)
    if "fat_range" not in plan:
        fat_low = round(cal_mid * 0.20 / 9)
        fat_high = round(cal_mid * 0.30 / 9)
        plan["fat_range"] = [fat_low, fat_high]

    # Carb target (g) — remainder after protein and fat
    if "carb_range" not in plan:
        protein_mid = (plan["protein_range"][0] + plan["protein_range"][1]) / 2
        fat_mid = (plan["fat_range"][0] + plan["fat_range"][1]) / 2
        remaining_cal = cal_mid - (protein_mid * 4) - (fat_mid * 9)
        carb_target = max(remaining_cal / 4, 100)  # at least 100g for brain function
        plan["carb_range"] = [round(carb_target * 0.85), round(carb_target * 1.15)]

    return plan


def compute_summary(days, plan, weight_data):
    """Compute aggregated statistics."""
    logged_days = [d for d in days if d["logged"]]
    logged_count = len(logged_days)

    cal_values = [d["totals"]["cal"] for d in logged_days if d["totals"]["cal"] > 0]
    cal_avg = round(sum(cal_values) / len(cal_values)) if cal_values else 0
    cal_max = max(cal_values) if cal_values else 0

    # --- Macronutrient estimation: per-meal-type average, then fill missing meals ---
    # Step 1: collect per-meal-type averages from all logged meals this week
    meal_type_stats = {}  # {meal_type: {"protein": [...], "fat": [...], "carb": [...], "cal": [...]}}
    for d in logged_days:
        for meal in d.get("meals", []):
            mt = meal.get("meal_type", "unknown")
            if meal.get("cal", 0) > 0:  # only count meals with data
                if mt not in meal_type_stats:
                    meal_type_stats[mt] = {"protein": [], "fat": [], "carb": [], "cal": []}
                meal_type_stats[mt]["protein"].append(meal.get("protein", 0) or 0)
                meal_type_stats[mt]["fat"].append(meal.get("fat", 0) or 0)
                meal_type_stats[mt]["carb"].append(meal.get("carb", 0) or 0)
                meal_type_stats[mt]["cal"].append(meal.get("cal", 0) or 0)

    # Compute averages per meal type
    meal_type_avgs = {}
    for mt, stats in meal_type_stats.items():
        meal_type_avgs[mt] = {
            "protein": round(sum(stats["protein"]) / len(stats["protein"])) if stats["protein"] else 0,
            "fat": round(sum(stats["fat"]) / len(stats["fat"])) if stats["fat"] else 0,
            "carb": round(sum(stats["carb"]) / len(stats["carb"])) if stats["carb"] else 0,
            "cal": round(sum(stats["cal"]) / len(stats["cal"])) if stats["cal"] else 0,
        }

    # Global meal average (fallback when a meal type has no data)
    all_proteins = [v for s in meal_type_stats.values() for v in s["protein"]]
    all_fats = [v for s in meal_type_stats.values() for v in s["fat"]]
    all_carbs = [v for s in meal_type_stats.values() for v in s["carb"]]
    all_cals = [v for s in meal_type_stats.values() for v in s["cal"]]
    global_avg = {
        "protein": round(sum(all_proteins) / len(all_proteins)) if all_proteins else 0,
        "fat": round(sum(all_fats) / len(all_fats)) if all_fats else 0,
        "carb": round(sum(all_carbs) / len(all_carbs)) if all_carbs else 0,
        "cal": round(sum(all_cals) / len(all_cals)) if all_cals else 0,
    }

    # Step 2: for each logged day, estimate full-day intake by filling missing meals
    # "Missing meal" = a standard meal type (breakfast/lunch/dinner) not present in the day's records
    # or present but with 0 calories (meaning skipped/not logged)
    standard_meals = {"breakfast", "lunch", "dinner"}
    estimated_daily = []  # list of {protein, fat, carb, cal} per day

    for d in logged_days:
        logged_types = set()
        day_protein = 0
        day_fat = 0
        day_carb = 0
        day_cal = d["totals"]["cal"]  # start with actual recorded calories

        for meal in d.get("meals", []):
            mt = meal.get("meal_type", "unknown")
            if meal.get("cal", 0) > 0:
                logged_types.add(mt)
                day_protein += meal.get("protein", 0) or 0
                day_fat += meal.get("fat", 0) or 0
                day_carb += meal.get("carb", 0) or 0

        # Fill missing standard meals with their type average
        missing_meals = standard_meals - logged_types
        for mt in missing_meals:
            avg = meal_type_avgs.get(mt, global_avg)
            day_protein += avg["protein"]
            day_fat += avg["fat"]
            day_carb += avg["carb"]
            day_cal += avg["cal"]

        estimated_daily.append({
            "protein": day_protein,
            "fat": day_fat,
            "carb": day_carb,
            "cal": day_cal,
            "missing_meals": len(missing_meals),
        })

    # Step 3: compute averages from estimated full-day values
    protein_values = [d["protein"] for d in estimated_daily if d["protein"] > 0]
    fat_values = [d["fat"] for d in estimated_daily if d["fat"] > 0]
    carb_values = [d["carb"] for d in estimated_daily if d["carb"] > 0]
    cal_est_values = [d["cal"] for d in estimated_daily if d["cal"] > 0]
    cal_avg_estimated = round(sum(cal_est_values) / len(cal_est_values)) if cal_est_values else cal_avg

    summary = {
        "logged_days": logged_count,
        "total_days": len(days),
        "cal_avg": cal_avg,
        "cal_avg_estimated": cal_avg_estimated,
        "days_with_missing_meals": sum(1 for d in estimated_daily if d["missing_meals"] > 0),
        "cal_max": cal_max,
        "cal_values": cal_values,
        "protein_avg": round(sum(protein_values) / len(protein_values)) if protein_values else 0,
        "fat_avg": round(sum(fat_values) / len(fat_values)) if fat_values else 0,
        "carb_avg": round(sum(carb_values) / len(carb_values)) if carb_values else 0,
        "macro_estimated": True,  # flag: macros include meal-fill estimation
        "weight_change": weight_data.get("change"),
        "weight_readings_count": len(weight_data.get("readings", [])),
    }

    # Calorie status per day (for chart)
    if plan and "cal_min" in plan:
        cal_min, cal_max_target = plan["cal_min"]
        for d in days:
            if d["logged"] and d["totals"]["cal"] > 0:
                cal = d["totals"]["cal"]
                if cal < cal_min:
                    d["cal_status"] = "below"
                elif cal > cal_max_target:
                    d["cal_status"] = "over"
                else:
                    d["cal_status"] = "on-target"
            else:
                d["cal_status"] = "empty"
        summary["cal_min"] = cal_min
        summary["cal_max_target"] = cal_max_target

    # Chart max for vertical bars
    chart_max = max(cal_max, (plan["cal_min"][1] * 1.2 if plan and "cal_min" in plan else 0))
    summary["chart_max"] = round(chart_max)

    return summary


def main():
    parser = argparse.ArgumentParser(description="Collect all weekly report data in one shot")
    parser.add_argument("--workspace-dir", required=True)
    parser.add_argument("--start-date", required=True, help="Monday of the report week (YYYY-MM-DD)")
    parser.add_argument("--end-date", required=True, help="Sunday of the report week (YYYY-MM-DD)")
    parser.add_argument("--tz-offset", type=int, required=True)
    parser.add_argument("--display-unit", default="kg")
    args = parser.parse_args()

    workspace_dir = _normalize_path(args.workspace_dir)
    data_dir = os.path.join(workspace_dir, "data")
    meals_dir = os.path.join(data_dir, "meals")

    # Find skill scripts (relative to this script's location)
    skills_base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    weight_tracker = find_script(skills_base, "weight-tracking", "weight-tracker.py")
    exercise_calc = find_script(skills_base, "exercise-tracking-planning", "exercise-calc.py")

    log(f"Collecting data for {args.start_date} to {args.end_date}")

    # Collect all data
    meals = collect_meals(None, meals_dir, args.start_date, args.end_date, args.tz_offset)
    weight = collect_weight(weight_tracker, data_dir, args.start_date, args.end_date, args.display_unit)
    # Also collect ALL historical weight for chart rendering
    all_weight = collect_weight(weight_tracker, data_dir, "2000-01-01", args.end_date, args.display_unit)
    exercise = collect_exercise(exercise_calc, data_dir, args.start_date, args.end_date)
    habits = collect_habits(workspace_dir, args.start_date, args.end_date)
    plan = read_plan(workspace_dir)
    summary = compute_summary(meals, plan, weight)

    # Week number calculation
    first_monday = None
    meal_files = sorted(os.listdir(meals_dir)) if os.path.isdir(meals_dir) else []
    if meal_files:
        first_date_str = meal_files[0].replace(".json", "")
        try:
            first_date = datetime.strptime(first_date_str, "%Y-%m-%d")
            # Round back to Monday
            first_monday = (first_date - timedelta(days=first_date.weekday())).strftime("%Y-%m-%d")
        except ValueError:
            pass

    start_dt = datetime.strptime(args.start_date, "%Y-%m-%d")
    if first_monday:
        first_monday_dt = datetime.strptime(first_monday, "%Y-%m-%d")
        week_number = ((start_dt - first_monday_dt).days // 7) + 1
    else:
        week_number = 1

    # Report count (previous reports)
    reports_dir = os.path.join(data_dir, "reports")
    report_count = 0
    if os.path.isdir(reports_dir):
        # Count unique weeks with report data (deduplicate old + new format)
        import re as _re
        week_dates = set()
        for f in os.listdir(reports_dir):
            m = _re.match(r'(?:weekly-report|weekly-data)-(\d{4}-\d{2}-\d{2})\.(?:html|json)$', f)
            if m:
                week_dates.add(m.group(1))
        report_count = len(week_dates)

    # Prev/next report existence
    prev_start = (start_dt - timedelta(days=7)).strftime("%Y-%m-%d")
    next_start = (start_dt + timedelta(days=7)).strftime("%Y-%m-%d")
    # Check both old and new file naming for prev/next existence
    # Only check for new-format data files (weekly-data-*.html contains JSON)
    # Old weekly-report-*.html files are static HTML and can't be loaded by the new template
    def _report_exists(reports_dir, date_str):
        if not os.path.isdir(reports_dir):
            return False
        return os.path.exists(os.path.join(reports_dir, f"weekly-data-{date_str}.html"))

    prev_exists = _report_exists(reports_dir, prev_start)
    next_exists = _report_exists(reports_dir, next_start)

    output = {
        "meta": {
            "start_date": args.start_date,
            "end_date": args.end_date,
            "week_number": week_number,
            "first_monday": first_monday,
            "report_count": report_count,
            "prev_start": prev_start,
            "prev_exists": prev_exists,
            "next_exists": next_exists,
            "next_start": next_start,
        },
        "plan": plan,
        "summary": summary,
        "days": meals,
        "weight": weight,
        "weight_all": all_weight.get("readings", []),
        "exercise": exercise,
        "habits": habits,
    }

    json.dump(output, sys.stdout, ensure_ascii=False, indent=2)
    print()  # trailing newline


if __name__ == "__main__":
    main()
