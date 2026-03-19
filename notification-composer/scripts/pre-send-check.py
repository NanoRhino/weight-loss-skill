#!/usr/bin/env python3
"""
pre-send-check.py — Deterministic pre-send checks for meal/weight reminders.

Returns SEND or NO_REPLY (with reason on stderr for logging).
The model should NOT be invoked if this returns NO_REPLY.

Usage:
  python3 pre-send-check.py --workspace-dir <path> --meal-type <type> --tz-offset <seconds>

  --workspace-dir   Agent workspace root (contains health-profile.md, data/, etc.)
  --meal-type       One of: breakfast, lunch, dinner, meal_1, meal_2, weight
  --tz-offset       Timezone offset in seconds from UTC (e.g. 28800 for UTC+8)

Exit code 0 always. Output is exactly "SEND" or "NO_REPLY" on stdout.
Reason is printed to stderr for debugging.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta


def log(msg):
    """Log to stderr (not visible to user, only for debugging)."""
    print(f"[pre-send-check] {msg}", file=sys.stderr)


def get_local_date(tz_offset):
    """Get current local date string YYYY-MM-DD."""
    tz = timezone(timedelta(seconds=tz_offset))
    return datetime.now(tz).strftime("%Y-%m-%d")


def get_local_weekday(tz_offset):
    """Get current local weekday (0=Monday, 6=Sunday)."""
    tz = timezone(timedelta(seconds=tz_offset))
    return datetime.now(tz).weekday()


def check_health_profile(workspace_dir):
    """Check 1: health-profile.md exists (user is onboarded)."""
    path = os.path.join(workspace_dir, "health-profile.md")
    if not os.path.exists(path):
        return False, "health-profile.md not found — user not onboarded"
    return True, None


def check_engagement_stage(workspace_dir):
    """Check 2: user is not in silent mode (Stage 4)."""
    path = os.path.join(workspace_dir, "data", "engagement.json")
    if not os.path.exists(path):
        # No engagement file = assume active (Stage 1)
        return True, None
    try:
        with open(path) as f:
            data = json.load(f)
        stage = data.get("notification_stage", 1)
        if stage >= 4:
            return False, f"notification_stage={stage} — user is in silent mode"
        return True, None
    except (json.JSONDecodeError, IOError) as e:
        log(f"Warning: could not read engagement.json: {e}")
        return True, None  # fail-open: send if we can't read


def check_meal_logged(workspace_dir, meal_type, tz_offset):
    """Check 3: this meal is not already logged today."""
    local_date = get_local_date(tz_offset)
    meals_file = os.path.join(workspace_dir, "data", "meals", f"{local_date}.json")

    if not os.path.exists(meals_file):
        return True, None  # no meals logged today at all

    try:
        with open(meals_file) as f:
            meals = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        log(f"Warning: could not read {meals_file}: {e}")
        return True, None  # fail-open

    # Normalize meal_type for matching
    # meal_1 -> check for "meal_1" or "breakfast" (first meal)
    # meal_2 -> check for "meal_2" or "lunch" (second meal)
    type_aliases = {
        "breakfast": ["breakfast"],
        "lunch": ["lunch"],
        "dinner": ["dinner"],
        "meal_1": ["meal_1", "meal 1"],
        "meal_2": ["meal_2", "meal 2"],
    }
    match_types = type_aliases.get(meal_type, [meal_type])

    for meal in meals:
        mt = meal.get("meal_type", "") or meal.get("name", "")
        if mt in match_types:
            return False, f"{meal_type} already logged today ({local_date})"

    return True, None


def check_weight_logged(workspace_dir, tz_offset):
    """Check for weight: already weighed today?"""
    local_date = get_local_date(tz_offset)
    weight_file = os.path.join(workspace_dir, "data", "weight.json")

    if not os.path.exists(weight_file):
        return True, None

    try:
        with open(weight_file) as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        log(f"Warning: could not read weight.json: {e}")
        return True, None

    # weight.json can be a list of entries or have a "records" key
    records = data if isinstance(data, list) else data.get("records", [])

    for record in records:
        record_date = record.get("date", "")
        if record_date == local_date:
            return False, f"weight already logged today ({local_date})"

    return True, None


def check_health_flags(workspace_dir, meal_type):
    """Check: skip weight reminders if ED-related flags present."""
    if meal_type != "weight":
        return True, None

    # Check USER.md for health flags
    user_md = os.path.join(workspace_dir, "USER.md")
    if not os.path.exists(user_md):
        return True, None

    try:
        with open(user_md) as f:
            content = f.read().lower()
        if "avoid_weight_focus" in content or "history_of_ed" in content:
            return False, "health flag: avoid_weight_focus or history_of_ed"
    except IOError:
        pass

    return True, None


def check_scheduling_constraints(workspace_dir, meal_type, tz_offset):
    """Check 4: scheduling constraints from health-preferences.md."""
    prefs_path = os.path.join(workspace_dir, "health-preferences.md")
    if not os.path.exists(prefs_path):
        return True, None

    try:
        with open(prefs_path) as f:
            content = f.read().lower()
    except IOError:
        return True, None

    weekday = get_local_weekday(tz_offset)  # 0=Mon, 6=Sun
    weekday_names_en = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    weekday_names_zh = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    today_en = weekday_names_en[weekday]
    today_zh = weekday_names_zh[weekday]

    # Check for "skip breakfast on workdays" pattern
    if meal_type == "breakfast" and weekday < 5:  # Mon-Fri
        skip_patterns = [
            "skip breakfast on workday",
            "skips breakfast on workday",
            "always skips breakfast",
            "不吃早餐",
            "跳过早餐",
            "工作日不吃早餐",
        ]
        for pattern in skip_patterns:
            if pattern in content:
                return False, f"scheduling constraint: {pattern}"

    # Check for day-specific constraints like "works late on wednesdays"
    # Look for lines containing today's name + skip/delay keywords
    for line in content.split("\n"):
        if (today_en in line or today_zh in line) and meal_type in line:
            skip_keywords = ["skip", "跳过", "不吃", "不提醒", "no reminder"]
            for kw in skip_keywords:
                if kw in line:
                    return False, f"scheduling constraint: {line.strip()}"

    return True, None


def main():
    parser = argparse.ArgumentParser(description="Pre-send check for meal/weight reminders")
    parser.add_argument("--workspace-dir", required=True, help="Agent workspace root")
    parser.add_argument("--meal-type", required=True,
                        choices=["breakfast", "lunch", "dinner", "meal_1", "meal_2", "weight"],
                        help="Meal type to check")
    parser.add_argument("--tz-offset", required=True, type=int,
                        help="Timezone offset in seconds from UTC")
    args = parser.parse_args()

    checks = [
        ("health_profile", lambda: check_health_profile(args.workspace_dir)),
        ("engagement_stage", lambda: check_engagement_stage(args.workspace_dir)),
        ("health_flags", lambda: check_health_flags(args.workspace_dir, args.meal_type)),
        ("scheduling", lambda: check_scheduling_constraints(
            args.workspace_dir, args.meal_type, args.tz_offset)),
    ]

    # Add meal-specific or weight-specific check
    if args.meal_type == "weight":
        checks.append(("weight_logged", lambda: check_weight_logged(
            args.workspace_dir, args.tz_offset)))
    else:
        checks.append(("meal_logged", lambda: check_meal_logged(
            args.workspace_dir, args.meal_type, args.tz_offset)))

    # Run all checks
    for check_name, check_fn in checks:
        passed, reason = check_fn()
        if not passed:
            log(f"FAIL [{check_name}]: {reason}")
            print("NO_REPLY")
            return

    log("All checks passed")
    print("SEND")


if __name__ == "__main__":
    main()
