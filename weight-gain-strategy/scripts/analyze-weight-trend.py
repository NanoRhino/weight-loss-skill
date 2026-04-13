#!/usr/bin/env python3
"""Analyze weight trends and generate adjustment strategies.

Commands:
  analyze          Analyze weight trend and diagnose probable causes
  deviation-check  Quick check if current weight deviates from plan (post-weigh-in)
  save-strategy    Save an active adjustment strategy
  check-strategy   Check progress on the active strategy
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


def get_meal_calories(meal):
    """Extract calories from a meal dict with fallback to foods/items sum."""
    if not isinstance(meal, dict):
        return 0
    meal_cal = meal.get("cal", meal.get("calories", 0)) or 0
    if meal_cal == 0:
        foods = meal.get("foods", meal.get("items", []))
        if foods:
            meal_cal = sum(f.get("calories", 0) for f in foods if isinstance(f, dict))
    return meal_cal


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
    # Match English: "Daily calorie target: ~1,600 kcal"
    match = re.search(
        r"[Dd]aily\s+calorie\s+target[:\s]*~?\s*([\d,]+)\s*(?:kcal|Cal)",
        content
    )
    if match:
        return int(match.group(1).replace(",", ""))
    # Match Chinese: "每日热量目标：1,700 kcal" or "每日热量目标：1700 kcal"
    match = re.search(
        r"每日热量目标[：:]\s*~?约?\s*([\d,]+)\s*(?:kcal|Cal)",
        content
    )
    if match:
        return int(match.group(1).replace(",", ""))
    # Fallback: look for any calorie number near "target" / "目标"
    match = re.search(r"(?:target|目标)[^0-9]*([\d,]+)\s*(?:kcal|Cal)", content)
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
    """Extract raw statistics for AI-driven weight gain analysis.

    This function does NOT make diagnostic judgments (no detected: true/false).
    It outputs raw numbers, lists, and statistics. The AI interprets these
    in context (user history, lifestyle, chat context) to determine causes.
    """
    import statistics
    tz_offset = args.tz_offset
    local_now = get_local_now(tz_offset)
    window = args.window
    end_date = local_now.strftime("%Y-%m-%d")
    start_date = (local_now - timedelta(days=window)).strftime("%Y-%m-%d")

    display_unit = parse_display_unit(args.health_profile)
    calorie_target = parse_plan_target(args.plan_file) if args.plan_file else None
    # Fallback: read calorie_target from health-profile.json
    if not calorie_target:
        hp = load_json(os.path.join(args.data_dir, "health-profile.json"))
        calorie_target = hp.get("calorie_target") or hp.get("daily_calorie_target")

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
        if isinstance(raw, dict) and "entries" in raw:
            # Format: {"entries": [{"date": "...", "value": N}, ...]}
            for entry in raw["entries"]:
                d = entry.get("date", "")[:10]
                if start_date <= d <= end_date:
                    weight_data.append({
                        "date": d,
                        "value": entry.get("value", 0),
                        "unit": entry.get("unit", display_unit),
                    })
        elif isinstance(raw, dict):
            # Format: {"2026-04-01": {"value": 65}, ...} or {"2026-04-01": 65, ...}
            for k, v in sorted(raw.items()):
                d = k[:10]
                if start_date <= d <= end_date:
                    weight_data.append({
                        "date": d,
                        "value": v.get("value", v) if isinstance(v, dict) else v,
                        "unit": v.get("unit", display_unit) if isinstance(v, dict) else display_unit,
                    })
        elif isinstance(raw, list):
            # Format: [{"date": "...", "value": N}, ...]
            for entry in raw:
                d = entry.get("date", "")[:10]
                if start_date <= d <= end_date:
                    weight_data.append({
                        "date": d,
                        "value": entry.get("value", 0),
                        "unit": entry.get("unit", display_unit),
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

    # --- Collect meal data ---
    daily_cals = []
    all_food_names = []
    for day_offset in range(window):
        d = (local_now - timedelta(days=window - 1 - day_offset)).strftime("%Y-%m-%d")
        meal_path = os.path.join(args.data_dir, "meals", f"{d}.json")
        if os.path.exists(meal_path):
            day_data = load_json(meal_path)
            day_cal = 0
            day_prot = 0
            day_meal_count = 0
            day_food_names = []
            meals = day_data if isinstance(day_data, list) else day_data.get("meals", [])
            for meal in meals:
                if isinstance(meal, dict):
                    mc = get_meal_calories(meal)
                    day_cal += mc
                    if mc > 0:
                        day_meal_count += 1
                    foods = meal.get("foods", meal.get("items", []))
                    if foods:
                        for f in foods:
                            if isinstance(f, dict):
                                name = f.get("name", "")
                                if name:
                                    all_food_names.append(name)
                                    day_food_names.append(name)
                                day_prot += f.get("protein", 0) or 0
            if day_cal > 0:
                daily_cals.append({"date": d, "cal": day_cal, "protein": day_prot,
                                   "meal_count": day_meal_count, "food_names": day_food_names})

    # --- Data confidence ---
    data_confidence = {
        "sufficient": True,
        "issues": [],
        "logged_days": len(daily_cals),
        "window_days": window,
        "coverage": round(len(daily_cals) / window, 2) if window > 0 else 0,
        "avg_meals_per_day": 0,
        "single_meal_days": 0,
    }
    if daily_cals:
        avg_meals = sum(d["meal_count"] for d in daily_cals) / len(daily_cals)
        single_meal = sum(1 for d in daily_cals if d["meal_count"] <= 1)
        data_confidence["avg_meals_per_day"] = round(avg_meals, 1)
        data_confidence["single_meal_days"] = single_meal
        if data_confidence["coverage"] < 0.4:
            data_confidence["sufficient"] = False
            data_confidence["issues"].append("low_coverage")
        if single_meal / len(daily_cals) > 0.5:
            data_confidence["sufficient"] = False
            data_confidence["issues"].append("incomplete_logging")
    else:
        data_confidence["sufficient"] = False
        data_confidence["issues"].append("no_data")

    # === RAW STATISTICS OUTPUT (no diagnostic judgments) ===
    # AI interprets these numbers in context to determine causes.

    # --- Calorie statistics ---
    calorie_stats = {
        "calorie_target": calorie_target,
        "logged_days": len(daily_cals),
        "avg_daily_intake": 0,
        "min_daily_intake": 0,
        "max_daily_intake": 0,
        "std_dev": 0,
        "days_over_target": 0,
        "days_under_60pct_target": 0,
        "daily_breakdown": [],  # [{date, cal, protein, meal_count}]
    }
    if daily_cals:
        cals = [c["cal"] for c in daily_cals]
        calorie_stats["avg_daily_intake"] = round(sum(cals) / len(cals))
        calorie_stats["min_daily_intake"] = round(min(cals))
        calorie_stats["max_daily_intake"] = round(max(cals))
        if len(cals) > 1:
            calorie_stats["std_dev"] = round(statistics.stdev(cals))
        if calorie_target:
            calorie_stats["days_over_target"] = sum(1 for c in cals if c > calorie_target)
            calorie_stats["days_under_60pct_target"] = sum(1 for c in cals if c < calorie_target * 0.6)
        calorie_stats["daily_breakdown"] = [
            {"date": d["date"], "cal": round(d["cal"]), "protein": round(d.get("protein", 0)),
             "meal_count": d.get("meal_count", 0)}
            for d in daily_cals
        ]

    # --- Protein statistics ---
    protein_stats = {
        "user_weight_kg": float(readings[-1].get("value", 0)) if readings else None,
        "recommended_daily_g": None,
        "avg_daily_g": 0,
        "days_with_protein_data": 0,
        "days_below_70pct": 0,
    }
    if readings:
        w = float(readings[-1].get("value", 0))
        protein_stats["recommended_daily_g"] = round(w * 1.2, 1)
    protein_data = [d for d in daily_cals if d.get("protein", 0) > 0]
    if protein_data:
        avg_p = sum(d["protein"] for d in protein_data) / len(protein_data)
        protein_stats["avg_daily_g"] = round(avg_p, 1)
        protein_stats["days_with_protein_data"] = len(protein_data)
        rec = protein_stats["recommended_daily_g"]
        if rec:
            protein_stats["days_below_70pct"] = sum(1 for d in protein_data if d["protein"] < rec * 0.7)

    # --- Exercise statistics ---
    exercise_stats = {
        "current_week_sessions": 0,
        "previous_week_sessions": 0,
        "current_week_minutes": 0,
        "previous_week_minutes": 0,
    }
    exercise_path = os.path.join(args.data_dir, "exercise.json")
    if os.path.exists(exercise_path):
        ex_data = load_json(exercise_path)
        entries = ex_data if isinstance(ex_data, list) else ex_data.get("entries", [])
        current_week_start = (local_now - timedelta(days=local_now.weekday())).strftime("%Y-%m-%d")
        prev_week_start = (local_now - timedelta(days=local_now.weekday() + 7)).strftime("%Y-%m-%d")
        current_sessions = [e for e in entries if e.get("date", "") >= current_week_start]
        previous_sessions = [e for e in entries if prev_week_start <= e.get("date", "") < current_week_start]
        exercise_stats["current_week_sessions"] = len(current_sessions)
        exercise_stats["previous_week_sessions"] = len(previous_sessions)
        exercise_stats["current_week_minutes"] = sum(e.get("duration_minutes", 0) for e in current_sessions)
        exercise_stats["previous_week_minutes"] = sum(e.get("duration_minutes", 0) for e in previous_sessions)

    # --- Logging coverage ---
    logging_stats = {
        "window_days": window,
        "logged_days": len(daily_cals),
        "coverage_pct": round(len(daily_cals) / window * 100) if window > 0 else 0,
        "single_meal_days": sum(1 for d in daily_cals if d.get("meal_count", 0) <= 1),
        "unlogged_days": window - len(daily_cals),
    }

    # --- Weight pattern ---
    weight_pattern = {
        "largest_daily_jump": 0,
        "largest_jump_dates": "",
    }
    sorted_readings = sorted(readings, key=lambda r: r["date"])
    for i in range(1, len(sorted_readings)):
        jump = abs(float(sorted_readings[i]["value"]) - float(sorted_readings[i-1]["value"]))
        if jump > weight_pattern["largest_daily_jump"]:
            weight_pattern["largest_daily_jump"] = round(jump, 2)
            weight_pattern["largest_jump_dates"] = f"{sorted_readings[i-1]['date']} → {sorted_readings[i]['date']}"

    # --- Food list (raw, for AI quality analysis) ---
    food_list = list(set(all_food_names))[:50]

    # --- Active strategy check ---
    strategy_path = os.path.join(args.data_dir, "weight-gain-strategy.json")
    active_strategy = None
    if os.path.exists(strategy_path):
        strat_data = load_json(strategy_path)
        act = strat_data.get("active_strategy", {})
        if act and act.get("status") == "active":
            end_date_str = act.get("end_date", "")
            if end_date_str >= local_now.strftime("%Y-%m-%d"):
                active_strategy = {
                    "type": act.get("type"),
                    "started": act.get("start_date"),
                    "ends": act.get("end_date"),
                    "description": act.get("description"),
                }

    # --- Suggested actions (concrete, script-driven, not AI judgment) ---
    suggested_actions = []

    # Logging insufficient → strict mode (no new habit — meal reminders already exist)
    ls = logging_stats
    if ls["coverage_pct"] < 50 or (ls["logged_days"] > 0 and ls["single_meal_days"] / ls["logged_days"] > 0.5):
        suggested_actions.append({
            "type": "strict_mode",
            "reason": "logging_gaps",
            "description": "Enter strict mode — existing meal reminders become more insistent, no new cron needed",
            "stats": {"coverage_pct": ls["coverage_pct"], "single_meal_days": ls["single_meal_days"],
                      "logged_days": ls["logged_days"]},
        })

    # Calorie target missing → need onboarding
    if not calorie_target:
        suggested_actions.append({
            "type": "set_calorie_target",
            "reason": "no_target",
            "description": "No calorie target set — cannot assess surplus/deficit",
        })

    # Active strategy exists → suppress new interventions
    if active_strategy:
        suggested_actions.append({
            "type": "suppress_new_strategy",
            "reason": "active_strategy",
            "description": f"Active strategy until {active_strategy['ends']} — no new cause-check needed",
        })

    # --- Final output ---
    result = {
        "trend": trend,
        "data_confidence": data_confidence,
        "calorie_stats": calorie_stats,
        "protein_stats": protein_stats,
        "exercise_stats": exercise_stats,
        "logging_stats": logging_stats,
        "weight_pattern": weight_pattern,
        "food_list": food_list,
        "active_strategy": active_strategy,
        "suggested_actions": suggested_actions,
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


def parse_plan_start_date(plan_path):
    """Extract plan start date from PLAN.md."""
    if not plan_path or not os.path.exists(plan_path):
        return None
    with open(plan_path, "r", encoding="utf-8") as f:
        content = f.read()
    import re
    # Match "开始日期：2026-03-18" or "Start date: 2026-03-18"
    match = re.search(
        r"(?:开始日期|[Ss]tart\s*[Dd]ate)[：:]\s*(\d{4}-\d{2}-\d{2})",
        content
    )
    if match:
        return match.group(1)
    return None


def parse_plan_rate(plan_path):
    """Extract weekly loss rate (kg/week) from PLAN.md."""
    if not plan_path or not os.path.exists(plan_path):
        return None
    with open(plan_path, "r", encoding="utf-8") as f:
        content = f.read()
    import re
    # Match patterns like "0.6 kg/周", "0.6 kg/week", "~0.6 kg/week"
    match = re.search(
        r"(?:约|~)?\s*([\d.]+)\s*kg\s*/\s*(?:周|week)",
        content, re.IGNORECASE
    )
    if match:
        return float(match.group(1))
    # Match lbs pattern and convert
    match = re.search(
        r"(?:约|~)?\s*([\d.]+)\s*(?:lbs?)\s*/\s*(?:周|week)",
        content, re.IGNORECASE
    )
    if match:
        return float(match.group(1)) * 0.4536
    return None


def parse_user_sex(user_file):
    """Extract biological sex from USER.md."""
    if not user_file or not os.path.exists(user_file):
        return None
    with open(user_file, "r", encoding="utf-8") as f:
        content = f.read().lower()
    import re
    match = re.search(r"sex[:\s]*(male|female|男|女)", content)
    if match:
        val = match.group(1)
        if val in ("female", "女"):
            return "female"
        return "male"
    return None


def detect_temporary_causes(args, local_now, readings, calorie_target):
    """Detect temporary/explainable causes for weight increase.

    Returns a list of detected temporary cause dicts, each with:
      - cause: string identifier
      - message: human-readable explanation
    """
    causes = []

    # --- Check 1: Yesterday's calorie spike ---
    yesterday = (local_now - timedelta(days=1)).strftime("%Y-%m-%d")
    meal_path = os.path.join(args.data_dir, "meals", f"{yesterday}.json")
    if os.path.exists(meal_path) and calorie_target:
        day_data = load_json(meal_path)
        meals = day_data if isinstance(day_data, list) else day_data.get("meals", [])
        day_cal = 0
        for meal in meals:
            if isinstance(meal, dict):
                day_cal += get_meal_calories(meal)
        if day_cal > 0:
            overshoot = day_cal - calorie_target
            overshoot_pct = overshoot / calorie_target * 100
            if overshoot_pct >= 30:  # 30%+ over target
                causes.append({
                    "cause": "yesterday_overeating",
                    "message": "Yesterday's intake was {0} kcal ({1:+.0f}% over target) — "
                               "a single high day often shows up on the scale the next morning "
                               "as water retention from extra carbs/sodium.".format(
                                   day_cal, overshoot_pct),
                    "yesterday_cal": day_cal,
                    "target_cal": calorie_target,
                    "overshoot_kcal": overshoot,
                })

    # --- Check 2: Possible menstrual cycle ---
    sex = parse_user_sex(args.user_file)
    if sex == "female":
        # Check if the weight increase pattern is consistent with cycle-related
        # water retention: sudden spike 0.5–2 kg in last 3 days, with no
        # calorie surplus detected over the broader window
        if len(readings) >= 2:
            recent_change = readings[-1]["value"] - readings[-2]["value"]
            recent_days = (
                datetime.strptime(readings[-1]["date"], "%Y-%m-%d")
                - datetime.strptime(readings[-2]["date"], "%Y-%m-%d")
            ).days
            if recent_change >= 0.5 and recent_days <= 5:
                # Check if average calorie intake over last 7 days is within target
                cal_within_target = True
                if calorie_target:
                    recent_cals = []
                    for day_offset in range(7):
                        d = (local_now - timedelta(days=day_offset)).strftime("%Y-%m-%d")
                        mp = os.path.join(args.data_dir, "meals", f"{d}.json")
                        if os.path.exists(mp):
                            dd = load_json(mp)
                            ms = dd if isinstance(dd, list) else dd.get("meals", [])
                            dc = sum(
                                get_meal_calories(m)
                                for m in ms if isinstance(m, dict)
                            )
                            if dc > 0:
                                recent_cals.append(dc)
                    if recent_cals:
                        avg_cal = sum(recent_cals) / len(recent_cals)
                        if avg_cal > calorie_target * 1.1:
                            cal_within_target = False

                if cal_within_target:
                    causes.append({
                        "cause": "possible_menstrual_cycle",
                        "message": "Weight jumped {0:+.1f} kg in {1} day(s) while calorie intake "
                                   "looks normal — this pattern is consistent with cycle-related "
                                   "water retention, which typically resolves in a few days.".format(
                                       recent_change, recent_days),
                        "recent_change_kg": round(recent_change, 2),
                        "recent_days": recent_days,
                    })

    # --- Check 3: Sudden spike (possible water/sodium retention) ---
    if len(readings) >= 2 and not any(c["cause"] == "possible_menstrual_cycle" for c in causes):
        recent_change = readings[-1]["value"] - readings[-2]["value"]
        recent_days = (
            datetime.strptime(readings[-1]["date"], "%Y-%m-%d")
            - datetime.strptime(readings[-2]["date"], "%Y-%m-%d")
        ).days
        if recent_change >= 0.8 and recent_days <= 2:
            causes.append({
                "cause": "sudden_spike",
                "message": "Weight jumped {0:+.1f} kg overnight — this is almost certainly "
                           "water/sodium retention rather than fat gain.".format(recent_change),
                "spike_kg": round(recent_change, 2),
            })

    return causes


def parse_health_flags(user_file):
    """Check USER.md for health flags that should skip weight analysis."""
    if not user_file or not os.path.exists(user_file):
        return []
    with open(user_file, "r", encoding="utf-8") as f:
        content = f.read().lower()
    flags = []
    if "avoid_weight_focus" in content:
        flags.append("avoid_weight_focus")
    if "history_of_ed" in content:
        flags.append("history_of_ed")
    return flags


def deviation_check(args):
    """Quick post-weigh-in check: has weight been going up consecutively?

    Counts how many consecutive weigh-ins show an increase over the previous
    one (streak), and maps that to a graduated severity level.

    Now self-contained: handles PLAN.md existence check, health flag checking,
    and plan start date parsing internally. The caller just passes file paths.

    Returns:
      - triggered: true if the latest weigh-in is higher than the previous
      - severity: "none" | "comfort" | "cause-check" | "significant"
      - consecutive_increases: the streak count driving severity
      - temporary_causes: list of detected temporary explanations (if any)
    """
    tz_offset = args.tz_offset
    local_now = get_local_now(tz_offset)

    # --- Early exit: check health flags ---
    health_flags = parse_health_flags(args.user_file)
    if health_flags:
        print(json.dumps({
            "triggered": False,
            "severity": "none",
            "reason": "health_flag",
            "flags": health_flags,
            "message": "Skipped — user has health flags that preclude weight focus.",
        }, indent=2, ensure_ascii=False))
        return

    # --- Early exit: no plan file ---
    if not args.plan_file or not os.path.exists(args.plan_file):
        print(json.dumps({
            "triggered": False,
            "severity": "none",
            "reason": "no_plan",
            "message": "Skipped — no PLAN.md found.",
        }, indent=2, ensure_ascii=False))
        return

    display_unit = parse_display_unit(args.health_profile)

    # Load recent weight readings (last 28 days for streak counting)
    end_date = local_now.strftime("%Y-%m-%d")
    start_date = (local_now - timedelta(days=28)).strftime("%Y-%m-%d")

    raw = load_json(os.path.join(args.data_dir, "weight.json"))
    readings = []
    for k, v in sorted(raw.items()):
        d = k[:10]
        if start_date <= d <= end_date:
            val = v.get("value", v) if isinstance(v, dict) else v
            unit = v.get("unit", display_unit) if isinstance(v, dict) else display_unit
            readings.append({"date": d, "datetime": k, "value": float(val), "unit": unit})

    if len(readings) < 2:
        print(json.dumps({
            "triggered": False,
            "severity": "none",
            "reason": "insufficient_data",
            "message": "Not enough weight readings to assess trend (need >= 2).",
        }, indent=2, ensure_ascii=False))
        return

    # --- Count consecutive increases from most recent reading backwards ---
    # Deduplicate: if the same value appears multiple times (e.g., save-and-check
    # just saved the same value), collapse consecutive identical readings
    deduped = []
    for r in readings:
        if not deduped or r["value"] != deduped[-1]["value"]:
            deduped.append(r)

    consecutive_increases = 0
    for i in range(len(deduped) - 1, 0, -1):
        if deduped[i]["value"] > deduped[i - 1]["value"]:
            consecutive_increases += 1
        else:
            break

    # --- Map streak to severity (with cooldown-aware escalation) ---
    # Load previous state for escalation logic
    wgs_state_path = os.path.join(args.data_dir, "weight-gain-state.json")
    wgs_state = {}
    if os.path.exists(wgs_state_path):
        try:
            with open(wgs_state_path) as f:
                wgs_state = json.load(f)
        except (json.JSONDecodeError, IOError):
            wgs_state = {}

    # --- Two-tier severity: light-analysis vs full cause-check ---
    # Tier 1 "light": first increase → quick data glance + comfort
    # Tier 2 "cause-check": second+ increase (>=3 days after light) → full analysis mode
    # During cause-check 7-day window: additional increases get "light" only
    last_severity = wgs_state.get("last_severity", "")
    last_trigger_date = wgs_state.get("last_trigger_date", "")

    if consecutive_increases == 0:
        severity = "none"
        triggered = False
    elif last_severity == "cause-check" and last_trigger_date:
        # We already did a full cause-check — check if within 7-day window
        try:
            days_since = (local_now.date() - datetime.strptime(
                last_trigger_date, "%Y-%m-%d"
            ).date()).days
        except ValueError:
            days_since = 999
        if days_since < 7:
            # Within 7-day window → light analysis only
            severity = "light"
            triggered = True
        else:
            # Past 7 days → eligible for new cause-check
            severity = "cause-check"
            triggered = True
    elif last_severity == "light" and last_trigger_date:
        # Previously triggered light → check if >=3 days for cause-check
        try:
            days_since = (local_now.date() - datetime.strptime(
                last_trigger_date, "%Y-%m-%d"
            ).date()).days
        except ValueError:
            days_since = 999
        if days_since >= 3:
            severity = "cause-check"
            triggered = True
        else:
            # <3 days since light → stay light (no spam)
            severity = "light"
            triggered = True
    else:
        # First increase or no previous state → light
        severity = "light"
        triggered = True

    # --- Detect adaptation period (first 2 weeks of plan) ---
    adaptation_period = False
    plan_start = args.plan_start_date
    if not plan_start:
        plan_start = parse_plan_start_date(args.plan_file)
    if plan_start:
        try:
            days_since_start = (local_now.date() - datetime.strptime(
                plan_start, "%Y-%m-%d"
            ).date()).days
            if 0 <= days_since_start <= 14:
                adaptation_period = True
        except ValueError:
            pass

    # --- Active strategy suppression: cause-check suppressed if strategy still active ---
    if triggered and severity == "cause-check":
        strategy_path = os.path.join(args.data_dir, "weight-gain-strategy.json")
        if os.path.exists(strategy_path):
            try:
                with open(strategy_path) as f:
                    strat_data = json.load(f)
                active = strat_data.get("active_strategy", {})
                if active and active.get("status") == "active":
                    end_date = active.get("end_date", "")
                    if end_date >= local_now.strftime("%Y-%m-%d"):
                        # Downgrade to light instead of blocking entirely
                        severity = "light"
            except (json.JSONDecodeError, IOError):
                pass

    # --- Cooldown: light has 1-day cooldown (no spam), cause-check handled above ---
    if triggered and severity == "light" and last_trigger_date:
        try:
            days_since = (local_now.date() - datetime.strptime(
                last_trigger_date, "%Y-%m-%d"
            ).date()).days
            if days_since < 1:
                print(json.dumps({
                    "triggered": False,
                    "severity": "none",
                    "reason": "cooldown",
                    "actual_severity": "light",
                    "consecutive_increases": consecutive_increases,
                    "cooldown_days": 1,
                    "days_since_last": days_since,
                    "message": "Light analysis already triggered today. Skipped.",
                }, indent=2, ensure_ascii=False))
                return
        except ValueError:
            pass

    # If we will trigger, persist state for future cooldown checks
    if triggered:
        wgs_state["last_trigger_date"] = local_now.strftime("%Y-%m-%d")
        wgs_state["last_severity"] = severity
        wgs_state["consecutive_increases"] = consecutive_increases
        try:
            with open(wgs_state_path, "w") as f:
                json.dump(wgs_state, f, indent=2, ensure_ascii=False)
        except IOError:
            pass

    # --- Detect temporary / specific causes ---
    calorie_target = parse_plan_target(args.plan_file) if args.plan_file else None
    temporary_causes = []
    if triggered:
        temporary_causes = detect_temporary_causes(
            args, local_now, readings, calorie_target
        )

    # --- Plan deviation as context (not for severity) ---
    first = readings[0]
    last = readings[-1]
    days_between = (
        datetime.strptime(last["date"], "%Y-%m-%d")
        - datetime.strptime(first["date"], "%Y-%m-%d")
    ).days

    plan_rate = parse_plan_rate(args.plan_file)
    deviation_context = {}
    if plan_rate and days_between > 0:
        weeks = days_between / 7.0
        actual_change = last["value"] - first["value"]
        expected_change = -(plan_rate * weeks)
        deviation = actual_change - expected_change
        deviation_context = {
            "plan_rate_kg_per_week": plan_rate,
            "expected_change_kg": round(expected_change, 2),
            "actual_change_kg": round(actual_change, 2),
            "deviation_kg": round(deviation, 2),
        }

    # --- Latest increase amount ---
    latest_increase_kg = round(readings[-1]["value"] - readings[-2]["value"], 2)

    # --- Build previous context for escalation callback ---
    previous_context = None
    if severity == "significant" and wgs_state.get("last_severity") == "cause-check":
        previous_context = {
            "last_trigger_date": wgs_state.get("last_trigger_date"),
            "days_since_cause_check": None,
            "message": "This is a follow-up. Last time we did a cause-check and identified potential issues. Reference that conversation — acknowledge what was discussed, note that the trend continued despite the analysis, and escalate to strategy suggestions. Do NOT repeat the same cause-check flow. The tone should show continuity: '上次我们聊过...' / '之前分析过一次...'",
        }
        if wgs_state.get("last_trigger_date"):
            try:
                previous_context["days_since_cause_check"] = (local_now.date() - datetime.strptime(
                    wgs_state["last_trigger_date"], "%Y-%m-%d"
                ).date()).days
            except ValueError:
                pass

    result = {
        "triggered": triggered,
        "severity": severity,
        "consecutive_increases": consecutive_increases,
        "adaptation_period": adaptation_period,
        "latest_increase_kg": latest_increase_kg,
        "window": {
            "start_date": readings[0]["date"],
            "end_date": readings[-1]["date"],
            "days": days_between,
        },
        "latest_weight": last["value"],
        "latest_unit": last["unit"],
        "readings_count": len(readings),
        "temporary_causes": temporary_causes,
        "deviation_context": deviation_context,
    }

    if previous_context:
        result["previous_context"] = previous_context

    if severity == "comfort":
        result["recommendation"] = (
            "Weight is up compared to last weigh-in. "
            "Comfort and encourage — this is normal, keep going. "
            "If a temporary cause was detected, mention it lightly."
        )
    elif severity == "cause-check":
        result["recommendation"] = (
            "Weight has been going up for {0} consecutive weigh-ins. "
            "Run analyze to identify probable causes (weekend overeating, "
            "exercise decline, menstrual cycle, calorie surplus) and tell "
            "the user what to watch out for. Do NOT offer strategy yet."
        ).format(consecutive_increases)
    elif severity == "significant":
        result["recommendation"] = (
            "Weight has been going up for {0} consecutive weigh-ins. "
            "Run full analyze, present diagnosis, and offer adjustment strategies."
        ).format(consecutive_increases)
    else:
        result["recommendation"] = "Weight stable or down. No action needed."

    print(json.dumps(result, indent=2, ensure_ascii=False))


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
    p_save.add_argument("--strategy-type", required=True)
    p_save.add_argument("--params", default="{}")
    p_save.add_argument("--tz-offset", type=int, default=0)

    # deviation-check
    p_devcheck = subparsers.add_parser("deviation-check")
    p_devcheck.add_argument("--data-dir", required=True)
    p_devcheck.add_argument("--plan-file", default=None)
    p_devcheck.add_argument("--health-profile", default=None)
    p_devcheck.add_argument("--user-file", default=None)
    p_devcheck.add_argument("--plan-start-date", default=None,
                            help="Plan start date YYYY-MM-DD for adaptation period detection")
    p_devcheck.add_argument("--tz-offset", type=int, default=0)

    # check-strategy
    p_check = subparsers.add_parser("check-strategy")
    p_check.add_argument("--data-dir", required=True)
    p_check.add_argument("--tz-offset", type=int, default=0)

    args = parser.parse_args()

    if args.command == "analyze":
        analyze(args)
    elif args.command == "deviation-check":
        deviation_check(args)
    elif args.command == "save-strategy":
        save_strategy(args)
    elif args.command == "check-strategy":
        check_strategy(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
