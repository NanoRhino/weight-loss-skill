#!/usr/bin/env python3
"""
streak-calc.py — Calculate meal-logging streak from daily meal files.

A "logged day" is any date with at least one meal entry whose status is
"logged" (not just "skipped" or "no_reply").

Usage:
  python3 streak-calc.py info    --data-dir <path> --tz-offset <sec>
  python3 streak-calc.py celebrate --data-dir <path> --tz-offset <sec> --milestone <n>

Commands:
  info        Output streak info as JSON (default)
  celebrate   Mark a milestone as celebrated in data/streak.json

Exit code 0 always.  Output is JSON on stdout.
"""

import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta


MILESTONES = [3, 7, 14, 21, 30, 60, 90, 180, 365]


def log(msg):
    print(f"[streak-calc] {msg}", file=sys.stderr)


def get_local_date(tz_offset):
    """Get current local date as YYYY-MM-DD."""
    tz = timezone(timedelta(seconds=tz_offset))
    return datetime.now(tz).strftime("%Y-%m-%d")


def _meal_has_food(meal):
    """Check if a meal dict contains actual food data."""
    if not isinstance(meal, dict):
        return False
    if meal.get("status") == "logged":
        return True
    items = meal.get("items") or meal.get("foods")
    return bool(items)


def find_logged_dates(data_dir):
    """Scan data/meals/ for dates with at least one meal entry with food data."""
    meals_dir = data_dir
    if not os.path.isdir(meals_dir):
        return set()

    date_pattern = re.compile(r"(\d{4}-\d{2}-\d{2})\.json$")
    logged_dates = set()

    for filepath in glob.glob(os.path.join(meals_dir, "*.json")):
        basename = os.path.basename(filepath)
        match = date_pattern.match(basename)
        if not match:
            continue
        date_str = match.group(1)
        try:
            with open(filepath) as f:
                meals = json.load(f)
        except (json.JSONDecodeError, IOError):
            continue

        # Check if any meal in this file has actual food data
        if isinstance(meals, list):
            for meal in meals:
                if _meal_has_food(meal):
                    logged_dates.add(date_str)
                    break
        elif isinstance(meals, dict):
            # Handle dict-format meal files (keyed by meal_type)
            for key, meal in meals.items():
                if _meal_has_food(meal):
                    logged_dates.add(date_str)
                    break

    return logged_dates


def calculate_streak(logged_dates, today_str):
    """
    Calculate current streak (consecutive days ending at today or yesterday)
    and longest streak ever.

    Returns (current_streak, longest_streak, streak_start_date).
    """
    if not logged_dates:
        return 0, 0, None

    today = datetime.strptime(today_str, "%Y-%m-%d").date()

    # Sort all logged dates
    sorted_dates = sorted(
        datetime.strptime(d, "%Y-%m-%d").date() for d in logged_dates
    )

    # Calculate all streaks
    streaks = []  # list of (start_date, length)
    streak_start = sorted_dates[0]
    streak_len = 1

    for i in range(1, len(sorted_dates)):
        if sorted_dates[i] - sorted_dates[i - 1] == timedelta(days=1):
            streak_len += 1
        else:
            streaks.append((streak_start, streak_len))
            streak_start = sorted_dates[i]
            streak_len = 1
    streaks.append((streak_start, streak_len))

    # Longest streak
    longest = max(streaks, key=lambda s: s[1])
    longest_streak = longest[1]

    # Current streak: must end at today or yesterday
    last_streak_start, last_streak_len = streaks[-1]
    last_streak_end = last_streak_start + timedelta(days=last_streak_len - 1)

    if last_streak_end == today or last_streak_end == today - timedelta(days=1):
        current_streak = last_streak_len
        streak_start_date = last_streak_start.isoformat()
    else:
        current_streak = 0
        streak_start_date = None

    return current_streak, longest_streak, streak_start_date


def load_streak_data(workspace_dir):
    """Load data/streak.json (milestones_celebrated tracking)."""
    path = os.path.join(workspace_dir, "data", "streak.json")
    if not os.path.exists(path):
        return {"milestones_celebrated": []}
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"milestones_celebrated": []}


def save_streak_data(workspace_dir, data):
    """Write data/streak.json."""
    path = os.path.join(workspace_dir, "data", "streak.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_pending_milestone(current_streak, celebrated):
    """
    Return the highest uncelebrated milestone that current_streak has reached.
    Returns None if nothing to celebrate.
    """
    celebrated_set = set(celebrated)
    pending = None
    for m in MILESTONES:
        if current_streak >= m and m not in celebrated_set:
            pending = m
    return pending


def cmd_info(args):
    """Output streak info as JSON and persist to data/streak.json."""
    today = get_local_date(args.tz_offset)
    logged_dates = find_logged_dates(args.data_dir)
    current_streak, longest_streak, streak_start = calculate_streak(
        logged_dates, today
    )

    streak_data = load_streak_data(args.workspace_dir)
    celebrated = streak_data.get("milestones_celebrated", [])

    # Reset celebrated list if streak was broken (current < max celebrated)
    if celebrated and current_streak < max(celebrated):
        celebrated = []

    # Preserve longest_streak across resets
    stored_longest = streak_data.get("longest_streak", 0)
    if longest_streak < stored_longest:
        longest_streak = stored_longest

    pending = get_pending_milestone(current_streak, celebrated)

    # Persist streak data
    streak_data["current_streak"] = current_streak
    streak_data["longest_streak"] = longest_streak
    streak_data["streak_start_date"] = streak_start
    streak_data["last_logged_date"] = max(logged_dates) if logged_dates else None
    streak_data["milestones_celebrated"] = celebrated
    save_streak_data(args.workspace_dir, streak_data)

    result = {
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "streak_start_date": streak_start,
        "last_logged_date": streak_data["last_logged_date"],
        "today": today,
        "pending_milestone": pending,
        "milestones_celebrated": celebrated,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))


def cmd_celebrate(args):
    """Mark a milestone as celebrated."""
    streak_data = load_streak_data(args.workspace_dir)
    celebrated = streak_data.get("milestones_celebrated", [])

    if args.milestone not in celebrated:
        celebrated.append(args.milestone)
        celebrated.sort()
        streak_data["milestones_celebrated"] = celebrated
        save_streak_data(args.workspace_dir, streak_data)
        log(f"Marked milestone {args.milestone} as celebrated")
    else:
        log(f"Milestone {args.milestone} already celebrated")

    print(json.dumps({"ok": True, "milestones_celebrated": celebrated}))


def main():
    parser = argparse.ArgumentParser(description="Streak calculator")
    # Shared arguments on the parent parser (used by both subcommands and bare invocation)
    parser.add_argument("--data-dir", required=True,
                        help="Path to data/meals directory")
    parser.add_argument("--workspace-dir", required=True,
                        help="Agent workspace root")
    parser.add_argument("--tz-offset", required=True, type=int,
                        help="Timezone offset in seconds from UTC")

    sub = parser.add_subparsers(dest="command")

    # info subcommand (also the default)
    sub.add_parser("info", help="Get streak info")

    # celebrate subcommand
    cel_p = sub.add_parser("celebrate", help="Mark milestone as celebrated")
    cel_p.add_argument("--milestone", required=True, type=int,
                        help="Milestone number to mark as celebrated")

    args = parser.parse_args()

    if args.command == "celebrate":
        cmd_celebrate(args)
    else:
        cmd_info(args)


if __name__ == "__main__":
    main()
