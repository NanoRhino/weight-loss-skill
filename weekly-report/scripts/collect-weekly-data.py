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
                            meal_protein = sum(i.get("protein", 0) or 0 for i in items if isinstance(i, dict))
                            meal_fat = sum(i.get("fat", 0) or 0 for i in items if isinstance(i, dict))
                            meal_carb = sum(i.get("carb", 0) or i.get("carbs", 0) or 0 for i in items if isinstance(i, dict))
                            meal_fiber = sum(i.get("fiber", 0) or 0 for i in items if isinstance(i, dict))
                            foods = [i.get("name", "?") for i in items if isinstance(i, dict)]
                            meals.append({
                                "meal_type": key,
                                "cal": meal_cal,
                                "protein": meal_protein,
                                "fat": meal_fat,
                                "carb": meal_carb,
                                "fiber": meal_fiber,
                                "foods": foods
                            })
                elif isinstance(raw, list):
                    for item in raw:
                        if isinstance(item, dict):
                            items_list = item.get("items") or item.get("foods") or []
                            if items_list:
                                meal_cal = sum(i.get("calories", 0) or i.get("cal", 0) or 0 for i in items_list if isinstance(i, dict))
                                meal_protein = sum(i.get("protein", 0) or 0 for i in items_list if isinstance(i, dict))
                                meal_fat = sum(i.get("fat", 0) or 0 for i in items_list if isinstance(i, dict))
                                meal_carb = sum(i.get("carb", 0) or i.get("carbs", 0) or 0 for i in items_list if isinstance(i, dict))
                                meal_fiber = sum(i.get("fiber", 0) or 0 for i in items_list if isinstance(i, dict))
                                foods = [i.get("name", "?") for i in items_list if isinstance(i, dict)]
                            else:
                                meal_cal = item.get("cal", 0) or item.get("calories", 0) or 0
                                meal_protein = item.get("protein", 0) or 0
                                meal_fat = item.get("fat", 0) or 0
                                meal_carb = item.get("carb", 0) or item.get("carbs", 0) or 0
                                meal_fiber = item.get("fiber", 0) or 0
                                foods = []
                            meals.append({
                                "meal_type": item.get("meal_type") or item.get("name", "unknown"),
                                "cal": meal_cal,
                                "protein": meal_protein,
                                "fat": meal_fat,
                                "carb": meal_carb,
                                "fiber": meal_fiber,
                                "foods": foods
                            })

                if meals:
                    day_data["logged"] = True
                    day_data["meals"] = meals
                    day_data["totals"] = {
                        "cal": sum(m["cal"] for m in meals),
                        "protein": sum(m["protein"] for m in meals),
                        "fat": sum(m["fat"] for m in meals),
                        "carb": sum(m["carb"] for m in meals),
                        "fiber": sum(m["fiber"] for m in meals),
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
            "tdee": r"TDEE[:\s]*([\d,]+)",
            "bmr": r"BMR[:\s]*([\d,]+)",
            "deficit": r"Daily Calorie Deficit[:\s]*([\d,]+)",
            "protein_range": r"Protein[:\s]*(\d+)\s*[-–]\s*(\d+)\s*g",
            "fat_range": r"Fat[:\s]*(\d+)\s*[-–]\s*(\d+)\s*g",
            "carb_range": r"Carb[:\s]*(\d+)\s*[-–]\s*(\d+)\s*g",
            "weight_loss_rate": r"Weight Loss Rate[:\s]*([\d.]+)",
            "target_weight": r"Target Weight[:\s]*([\d.]+)",
            "start_weight": r"(?:Start|Initial|Starting) Weight[:\s]*([\d.]+)",
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
        # Standard deficit: BMR~1400-1650 for most users, target 1600-2000
        plan["cal_min"] = [1600, 2000]

    cal_mid = (plan["cal_min"][0] + plan["cal_min"][1]) / 2

    # Protein target (g)
    if "protein_range" not in plan:
        if diet_mode == "high_protein":
            protein_per_kg = 1.2
        else:
            protein_per_kg = 0.8
        protein_target = round(weight * protein_per_kg)
        plan["protein_range"] = [protein_target - 10, protein_target + 10]

    # Fat target (g) — 25-35% of calories
    if "fat_range" not in plan:
        fat_low = round(cal_mid * 0.25 / 9)
        fat_high = round(cal_mid * 0.35 / 9)
        plan["fat_range"] = [fat_low, fat_high]

    # Carb target (g) — remainder
    if "carb_range" not in plan:
        protein_mid = (plan["protein_range"][0] + plan["protein_range"][1]) / 2
        fat_mid = (plan["fat_range"][0] + plan["fat_range"][1]) / 2
        remaining_cal = cal_mid - (protein_mid * 4) - (fat_mid * 9)
        carb_mid = max(remaining_cal / 4, 80)  # at least 80g
        plan["carb_range"] = [round(carb_mid * 0.8), round(carb_mid * 1.2)]

    return plan


def compute_summary(days, plan, weight_data):
    """Compute aggregated statistics."""
    logged_days = [d for d in days if d["logged"]]
    logged_count = len(logged_days)

    cal_values = [d["totals"]["cal"] for d in logged_days if d["totals"]["cal"] > 0]
    cal_avg = round(sum(cal_values) / len(cal_values)) if cal_values else 0
    cal_max = max(cal_values) if cal_values else 0

    protein_values = [d["totals"]["protein"] for d in logged_days if d["totals"]["protein"] > 0]
    fat_values = [d["totals"]["fat"] for d in logged_days if d["totals"]["fat"] > 0]
    carb_values = [d["totals"]["carb"] for d in logged_days if d["totals"]["carb"] > 0]

    summary = {
        "logged_days": logged_count,
        "total_days": len(days),
        "cal_avg": cal_avg,
        "cal_max": cal_max,
        "cal_values": cal_values,
        "protein_avg": round(sum(protein_values) / len(protein_values)) if protein_values else 0,
        "fat_avg": round(sum(fat_values) / len(fat_values)) if fat_values else 0,
        "carb_avg": round(sum(carb_values) / len(carb_values)) if carb_values else 0,
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
        report_count = len([f for f in os.listdir(reports_dir) if f.startswith("weekly-report-") and f.endswith(".html")])

    # Prev/next report existence
    prev_start = (start_dt - timedelta(days=7)).strftime("%Y-%m-%d")
    next_start = (start_dt + timedelta(days=7)).strftime("%Y-%m-%d")
    prev_exists = os.path.exists(os.path.join(reports_dir, f"weekly-report-{prev_start}.html")) if os.path.isdir(reports_dir) else False
    # Next always disabled for current report

    output = {
        "meta": {
            "start_date": args.start_date,
            "end_date": args.end_date,
            "week_number": week_number,
            "first_monday": first_monday,
            "report_count": report_count,
            "prev_start": prev_start,
            "prev_exists": prev_exists,
            "next_start": next_start,
        },
        "plan": plan,
        "summary": summary,
        "days": meals,
        "weight": weight,
        "exercise": exercise,
        "habits": habits,
    }

    json.dump(output, sys.stdout, ensure_ascii=False, indent=2)
    print()  # trailing newline


if __name__ == "__main__":
    main()
