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
                day_cal += meal.get("cal", meal.get("calories", 0)) or 0
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
                                (m.get("cal", m.get("calories", 0)) or 0)
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


def deviation_check(args):
    """Quick post-weigh-in check: is the user deviating from plan?

    Compares the latest weight readings against the expected trajectory
    based on PLAN.md weekly loss rate. Also detects temporary causes
    (yesterday overeating, menstrual cycle, water retention) that warrant
    reassurance + deferral rather than immediate analysis.

    Returns:
      - triggered: true if deviation warrants action
      - severity: "none" | "deferred" | "mild" | "significant"
      - temporary_causes: list of detected temporary explanations (if any)
    """
    tz_offset = args.tz_offset
    local_now = get_local_now(tz_offset)
    display_unit = parse_display_unit(args.health_profile)

    # Load recent weight readings (last 14 days)
    end_date = local_now.strftime("%Y-%m-%d")
    start_date = (local_now - timedelta(days=14)).strftime("%Y-%m-%d")

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
            "message": "Not enough weight readings to assess deviation (need >= 2).",
        }, indent=2, ensure_ascii=False))
        return

    # Get plan rate
    plan_rate = parse_plan_rate(args.plan_file)
    if not plan_rate:
        print(json.dumps({
            "triggered": False,
            "severity": "none",
            "reason": "no_plan",
            "message": "No PLAN.md or no weekly loss rate found.",
        }, indent=2, ensure_ascii=False))
        return

    # Detect adaptation period (first 2 weeks of plan)
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

    # Calculate expected vs actual weight change over the window
    first = readings[0]
    last = readings[-1]
    days_between = (
        datetime.strptime(last["date"], "%Y-%m-%d")
        - datetime.strptime(first["date"], "%Y-%m-%d")
    ).days

    if days_between < 3:
        # Too short a window, daily fluctuation dominates
        print(json.dumps({
            "triggered": False,
            "severity": "none",
            "reason": "window_too_short",
            "message": "Only {0} days between readings — too short to assess trend.".format(days_between),
        }, indent=2, ensure_ascii=False))
        return

    actual_change = last["value"] - first["value"]  # negative = lost weight
    weeks = days_between / 7.0
    expected_change = -(plan_rate * weeks)  # expected is negative (losing)

    deviation = actual_change - expected_change  # positive = worse than plan

    # Determine raw severity before temporary-cause adjustment
    # mild: deviation 0.3–0.8 kg above expected (falling behind)
    # significant: deviation > 0.8 kg above expected OR actual gain > 0.5 kg
    raw_severity = "none"
    triggered = False

    if actual_change > 0.3:
        # Actually gaining weight
        if actual_change > 0.8:
            raw_severity = "significant"
        else:
            raw_severity = "mild"
        triggered = True
    elif deviation > 0.8:
        # Not gaining, but far behind plan
        raw_severity = "significant"
        triggered = True
    elif deviation > 0.3:
        raw_severity = "mild"
        triggered = True

    # --- Detect temporary causes ---
    calorie_target = parse_plan_target(args.plan_file) if args.plan_file else None
    temporary_causes = []
    if triggered:
        temporary_causes = detect_temporary_causes(
            args, local_now, readings, calorie_target
        )

    # Downgrade severity based on context
    severity = raw_severity
    if adaptation_period and severity in ("mild", "significant"):
        # Adaptation period: still report the trend but cap to "adaptation"
        # so the response is lighter — reassurance + brief cause note, no
        # strategy suggestions
        severity = "adaptation"
    elif temporary_causes and severity in ("mild", "significant"):
        # Temporary cause explains the spike — reassure now, re-evaluate
        # at the next weigh-in
        severity = "deferred"

    result = {
        "triggered": triggered,
        "severity": severity,
        "raw_severity": raw_severity,
        "adaptation_period": adaptation_period,
        "window": {
            "start_date": first["date"],
            "end_date": last["date"],
            "days": days_between,
        },
        "plan_rate_kg_per_week": plan_rate,
        "expected_change_kg": round(expected_change, 2),
        "actual_change_kg": round(actual_change, 2),
        "deviation_kg": round(deviation, 2),
        "latest_weight": last["value"],
        "latest_unit": last["unit"],
        "readings_count": len(readings),
        "temporary_causes": temporary_causes,
    }

    if severity == "adaptation":
        result["recommendation"] = (
            "Adaptation period — reassure the user that early fluctuation is normal. "
            "Lightly mention any detected causes (temporary or otherwise) as context, "
            "not as problems. Do NOT suggest adjustments."
        )
    elif severity == "deferred":
        result["recommendation"] = (
            "Reassure the user (temporary cause detected). "
            "Defer analysis to next weigh-in cycle."
        )
    elif triggered:
        if severity == "significant":
            result["recommendation"] = "Run full analyze to diagnose causes and offer adjustment strategies."
        else:
            result["recommendation"] = "Mention the trend gently. Offer to investigate if the user wants."
    else:
        result["recommendation"] = "On track or within normal fluctuation. No action needed."

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
    p_save.add_argument("--strategy-type", required=True,
                        choices=["reduce_calories", "increase_exercise",
                                 "adjust_schedule", "combined"])
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
