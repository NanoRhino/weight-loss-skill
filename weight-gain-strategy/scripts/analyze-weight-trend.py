#!/usr/bin/env python3
"""Analyze weight trends and generate adjustment strategies.

Commands:
  analyze         Analyze weight trend and diagnose probable causes
  save-strategy   Save an active adjustment strategy
  check-strategy  Check progress on the active strategy
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone


def load_json(path):
    """Load a JSON file, return empty dict if not found."""
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    """Save data as JSON."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_local_now(tz_offset):
    """Get current local datetime given tz_offset in seconds."""
    tz = timezone(timedelta(seconds=tz_offset))
    return datetime.now(tz)


def run_script(cmd):
    """Run a subprocess and return parsed JSON output."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            return None
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return None


def parse_plan_target(plan_path):
    """Extract daily calorie target from PLAN.md."""
    if not os.path.exists(plan_path):
        return None
    with open(plan_path, "r", encoding="utf-8") as f:
        content = f.read()
    # Look for calorie target patterns
    import re
    # Match patterns like "1,600 kcal", "1600 kcal", "1,600 Cal"
    match = re.search(
        r"[Dd]aily\s+calorie\s+target[:\s]*~?\s*([\d,]+)\s*(?:kcal|Cal)",
        content
    )
    if match:
        return int(match.group(1).replace(",", ""))
    # Fallback: look for any calorie number near "target"
    match = re.search(r"([\d,]+)\s*(?:kcal|Cal)", content)
    if match:
        return int(match.group(1).replace(",", ""))
    return None


def parse_display_unit(health_profile_path):
    """Extract unit preference from health-profile.md."""
    if not health_profile_path or not os.path.exists(health_profile_path):
        return "kg"
    with open(health_profile_path, "r", encoding="utf-8") as f:
        content = f.read()
    if "lb" in content.lower() and "unit preference" in content.lower():
        return "lb"
    return "kg"


def analyze(args):
    """Analyze weight trend and diagnose causes."""
    tz_offset = args.tz_offset
    local_now = get_local_now(tz_offset)
    window = args.window
    end_date = local_now.strftime("%Y-%m-%d")
    start_date = (local_now - timedelta(days=window)).strftime("%Y-%m-%d")

    display_unit = parse_display_unit(args.health_profile)
    calorie_target = parse_plan_target(args.plan_file) if args.plan_file else None

    # --- Load weight data ---
    weight_data = None
    if args.weight_script and os.path.exists(args.weight_script):
        weight_data = run_script([
            "python3", args.weight_script, "load",
            "--data-dir", args.data_dir,
            "--display-unit", display_unit,
            "--from", start_date,
            "--to", end_date,
        ])

    # Fallback: read weight.json directly
    if not weight_data:
        raw = load_json(os.path.join(args.data_dir, "weight.json"))
        weight_data = []
        for k, v in sorted(raw.items()):
            d = k[:10]
            if start_date <= d <= end_date:
                weight_data.append({
                    "date": d,
                    "value": v.get("value", v) if isinstance(v, dict) else v,
                    "unit": v.get("unit", display_unit) if isinstance(v, dict) else display_unit,
                })

    # Normalize weight_data to list of readings
    readings = []
    if isinstance(weight_data, list):
        readings = weight_data
    elif isinstance(weight_data, dict):
        # Script might return {"entries": [...]}
        readings = weight_data.get("entries", [])

    if len(readings) < 2:
        result = {
            "trend": {
                "direction": "insufficient_data",
                "net_change_kg": 0,
                "net_change_display": "N/A",
                "window_days": window,
                "readings": readings,
            },
            "diagnosis": {},
            "top_factors": [],
            "suggested_strategies": [],
            "error": "Insufficient weight data (need at least 2 readings)",
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    first_reading = readings[0]
    last_reading = readings[-1]
    first_val = float(first_reading.get("value", first_reading.get("display_value", 0)))
    last_val = float(last_reading.get("value", last_reading.get("display_value", 0)))
    net_change = round(last_val - first_val, 2)
    unit = display_unit

    direction = "up" if net_change > 0.1 else ("down" if net_change < -0.1 else "stable")

    trend = {
        "direction": direction,
        "net_change_kg": net_change,
        "net_change_display": f"{net_change:+.1f} {unit}",
        "window_days": window,
        "readings": readings,
    }

    # --- Diagnose: calorie surplus ---
    calorie_diagnosis = {
        "detected": False,
        "avg_daily_intake": None,
        "target": calorie_target,
        "surplus_kcal": None,
        "days_over_target": 0,
        "days_total": 0,
    }

    daily_cals = []
    for day_offset in range(window):
        d = (local_now - timedelta(days=window - 1 - day_offset)).strftime("%Y-%m-%d")
        meal_path = os.path.join(args.data_dir, "meals", f"{d}.json")
        if os.path.exists(meal_path):
            day_data = load_json(meal_path)
            day_cal = 0
            meals = day_data if isinstance(day_data, list) else day_data.get("meals", [])
            for meal in meals:
                if isinstance(meal, dict):
                    day_cal += meal.get("cal", meal.get("calories", 0)) or 0
            if day_cal > 0:
                daily_cals.append({"date": d, "cal": day_cal})

    if daily_cals:
        avg_intake = round(sum(c["cal"] for c in daily_cals) / len(daily_cals))
        calorie_diagnosis["avg_daily_intake"] = avg_intake
        calorie_diagnosis["days_total"] = len(daily_cals)

        if calorie_target:
            surplus = avg_intake - calorie_target
            calorie_diagnosis["surplus_kcal"] = surplus
            calorie_diagnosis["days_over_target"] = sum(
                1 for c in daily_cals if c["cal"] > calorie_target
            )
            if surplus > 50:
                calorie_diagnosis["detected"] = True

    # --- Diagnose: exercise decline ---
    exercise_diagnosis = {
        "detected": False,
        "current_week_sessions": 0,
        "previous_week_sessions": 0,
        "current_week_minutes": 0,
        "previous_week_minutes": 0,
    }

    exercise_data = load_json(os.path.join(args.data_dir, "exercise.json"))
    if isinstance(exercise_data, list):
        exercises = exercise_data
    elif isinstance(exercise_data, dict):
        exercises = exercise_data.get("entries", exercise_data.get("sessions", []))
    else:
        exercises = []

    current_week_start = (local_now - timedelta(days=7)).strftime("%Y-%m-%d")
    previous_week_start = (local_now - timedelta(days=14)).strftime("%Y-%m-%d")

    current_sessions = []
    previous_sessions = []

    for ex in exercises:
        ex_date = ex.get("date", ex.get("datetime", ""))[:10]
        if current_week_start <= ex_date <= end_date:
            current_sessions.append(ex)
        elif previous_week_start <= ex_date < current_week_start:
            previous_sessions.append(ex)

    cur_minutes = sum(e.get("duration", e.get("duration_minutes", 0)) or 0 for e in current_sessions)
    prev_minutes = sum(e.get("duration", e.get("duration_minutes", 0)) or 0 for e in previous_sessions)

    exercise_diagnosis["current_week_sessions"] = len(current_sessions)
    exercise_diagnosis["previous_week_sessions"] = len(previous_sessions)
    exercise_diagnosis["current_week_minutes"] = cur_minutes
    exercise_diagnosis["previous_week_minutes"] = prev_minutes

    if len(previous_sessions) > 0 and len(current_sessions) < len(previous_sessions):
        exercise_diagnosis["detected"] = True
    elif prev_minutes > 0 and cur_minutes < prev_minutes * 0.6:
        exercise_diagnosis["detected"] = True

    # --- Diagnose: logging gaps ---
    logging_gaps = {
        "detected": False,
        "unlogged_days": 0,
        "total_days": window,
    }
    logged_days = len(daily_cals)
    unlogged = window - logged_days
    logging_gaps["unlogged_days"] = unlogged
    if unlogged > window * 0.5:
        logging_gaps["detected"] = True

    # --- Diagnose: water retention ---
    water_retention = {
        "detected": False,
        "note": "Sudden spike >= 0.5 kg in 1-2 days without calorie surplus",
    }
    if len(readings) >= 2:
        for i in range(1, len(readings)):
            prev_val = float(readings[i - 1].get("value", readings[i - 1].get("display_value", 0)))
            curr_val = float(readings[i].get("value", readings[i].get("display_value", 0)))
            if curr_val - prev_val >= 0.5 and not calorie_diagnosis["detected"]:
                water_retention["detected"] = True
                break

    # --- Diagnose: normal fluctuation ---
    normal_fluctuation = {
        "detected": False,
        "note": "Net change < 0.3 kg over the analysis window with no sustained trend",
    }
    if abs(net_change) < 0.3:
        normal_fluctuation["detected"] = True

    # --- Build top factors ---
    diagnosis = {
        "calorie_surplus": calorie_diagnosis,
        "exercise_decline": exercise_diagnosis,
        "logging_gaps": logging_gaps,
        "possible_water_retention": water_retention,
        "normal_fluctuation": normal_fluctuation,
    }

    top_factors = []
    if normal_fluctuation["detected"]:
        top_factors = ["normal_fluctuation"]
    else:
        if calorie_diagnosis["detected"]:
            top_factors.append("calorie_surplus")
        if exercise_diagnosis["detected"]:
            top_factors.append("exercise_decline")
        if logging_gaps["detected"]:
            top_factors.append("logging_gaps")
        if water_retention["detected"] and not calorie_diagnosis["detected"]:
            top_factors.append("possible_water_retention")

    # --- Generate suggested strategies ---
    strategies = []

    if calorie_diagnosis["detected"] and calorie_target:
        surplus = calorie_diagnosis["surplus_kcal"]
        reduction = min(surplus, 300)  # Cap reduction at 300 kcal
        new_target = calorie_target - reduction
        # Enforce calorie floor (1000 kcal minimum)
        new_target = max(new_target, 1000)
        actual_reduction = calorie_target - new_target

        if actual_reduction > 0:
            strategies.append({
                "type": "reduce_calories",
                "description": f"Reduce daily intake by {actual_reduction} kcal",
                "target_kcal": new_target,
                "original_target_kcal": calorie_target,
                "reduction_kcal": actual_reduction,
                "duration_days": 7,
                "expected_impact": f"~{round(actual_reduction * 7 / 7700, 2)} kg deficit per week",
            })

    if exercise_diagnosis["detected"] or (direction == "up" and not calorie_diagnosis["detected"]):
        prev_sessions = exercise_diagnosis["previous_week_sessions"]
        target_sessions = max(prev_sessions, 3)
        strategies.append({
            "type": "increase_exercise",
            "description": f"Target {target_sessions} exercise sessions this week",
            "target_sessions": target_sessions,
            "target_minutes_per_session": 30,
            "duration_days": 7,
            "expected_impact": "~150-300 kcal additional burn per session",
        })

    if len(strategies) >= 2:
        # Offer a combined option with more modest adjustments
        combined_params = {}
        if calorie_diagnosis["detected"] and calorie_target:
            modest_reduction = min(100, calorie_diagnosis["surplus_kcal"])
            combined_params["target_kcal"] = max(calorie_target - modest_reduction, 1000)
            combined_params["reduction_kcal"] = calorie_target - combined_params["target_kcal"]
        combined_params["target_sessions"] = max(
            exercise_diagnosis["current_week_sessions"] + 1, 2
        )
        combined_params["target_minutes_per_session"] = 30
        strategies.append({
            "type": "combined",
            "description": "Modest calorie reduction + 1 extra exercise session",
            "params": combined_params,
            "duration_days": 7,
            "expected_impact": "Balanced approach — smaller changes, easier to sustain",
        })

    result = {
        "trend": trend,
        "diagnosis": diagnosis,
        "top_factors": top_factors,
        "suggested_strategies": strategies,
    }

    print(json.dumps(result, indent=2, ensure_ascii=False))


def save_strategy(args):
    """Save an active adjustment strategy."""
    local_now = get_local_now(args.tz_offset)
    strategy_path = os.path.join(args.data_dir, "weight-gain-strategy.json")
    data = load_json(strategy_path)

    params = json.loads(args.params) if args.params else {}
    duration = params.pop("duration_days", 7)
    start_date = local_now.strftime("%Y-%m-%d")
    end_date = (local_now + timedelta(days=duration)).strftime("%Y-%m-%d")

    # Archive current active strategy if exists
    if "active_strategy" in data and data["active_strategy"]:
        if "history" not in data:
            data["history"] = []
        old = data["active_strategy"]
        old["status"] = "superseded"
        data["history"].append(old)

    data["active_strategy"] = {
        "type": args.strategy_type,
        "start_date": start_date,
        "end_date": end_date,
        "params": params,
        "status": "active",
        "created_at": local_now.isoformat(),
    }

    if "history" not in data:
        data["history"] = []

    save_json(strategy_path, data)
    print(json.dumps(data["active_strategy"], indent=2, ensure_ascii=False))


def check_strategy(args):
    """Check progress on the active strategy."""
    local_now = get_local_now(args.tz_offset)
    strategy_path = os.path.join(args.data_dir, "weight-gain-strategy.json")
    data = load_json(strategy_path)

    if not data.get("active_strategy"):
        print(json.dumps({"status": "no_active_strategy"}, indent=2))
        return

    strategy = data["active_strategy"]
    end_date = strategy.get("end_date", "")
    today = local_now.strftime("%Y-%m-%d")

    if today > end_date:
        strategy["status"] = "expired"
        save_json(strategy_path, data)

    days_elapsed = (local_now.date() - datetime.strptime(
        strategy["start_date"], "%Y-%m-%d"
    ).date()).days
    total_days = (datetime.strptime(
        strategy["end_date"], "%Y-%m-%d"
    ).date() - datetime.strptime(
        strategy["start_date"], "%Y-%m-%d"
    ).date()).days

    result = {
        "strategy": strategy,
        "progress": {
            "days_elapsed": days_elapsed,
            "total_days": total_days,
            "percentage": round(days_elapsed / max(total_days, 1) * 100),
        },
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description="Weight trend analysis")
    subparsers = parser.add_subparsers(dest="command")

    # analyze
    p_analyze = subparsers.add_parser("analyze")
    p_analyze.add_argument("--data-dir", required=True)
    p_analyze.add_argument("--weight-script", default=None)
    p_analyze.add_argument("--nutrition-script", default=None)
    p_analyze.add_argument("--exercise-script", default=None)
    p_analyze.add_argument("--plan-file", default=None)
    p_analyze.add_argument("--health-profile", default=None)
    p_analyze.add_argument("--tz-offset", type=int, default=0)
    p_analyze.add_argument("--window", type=int, default=14)

    # save-strategy
    p_save = subparsers.add_parser("save-strategy")
    p_save.add_argument("--data-dir", required=True)
    p_save.add_argument("--strategy-type", required=True,
                        choices=["reduce_calories", "increase_exercise",
                                 "adjust_schedule", "combined"])
    p_save.add_argument("--params", default="{}")
    p_save.add_argument("--tz-offset", type=int, default=0)

    # check-strategy
    p_check = subparsers.add_parser("check-strategy")
    p_check.add_argument("--data-dir", required=True)
    p_check.add_argument("--tz-offset", type=int, default=0)

    args = parser.parse_args()

    if args.command == "analyze":
        analyze(args)
    elif args.command == "save-strategy":
        save_strategy(args)
    elif args.command == "check-strategy":
        check_strategy(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
