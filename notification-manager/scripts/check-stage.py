#!/usr/bin/env python3
"""
check-stage.py — Update engagement stage based on user silence duration.

Derives last interaction from meal logging records (data/meals/*.json)
rather than relying on a platform-written timestamp. A "logged day" is
any date with at least one meal entry that contains food data.

Lifecycle rules:

  Stage 1 (ACTIVE)   → 3 full calendar days silent  → Stage 2 (RECALL)
  Stage 2 (RECALL)   → 3 days of daily recalls       → Stage 3 (FINAL)
  Stage 3 (FINAL)    → 1 day after final recall       → Stage 4 (WEEKLY)
  Stage 4 (WEEKLY)   → 3 weeks of weekly recalls      → Stage 5 (MONTHLY)
  Stage 5 (MONTHLY)  → monthly recalls indefinitely

When a silent user returns (new meal logged while stage > 1),
resets to Stage 1.

Usage:
  python3 check-stage.py --workspace-dir <path> --tz-offset <seconds>

Output (stdout): current stage number (1-5) and days_silent
Transitions are logged to stderr.

Exit code 0 always.
"""

import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta


def log(msg):
    """Log to stderr (not visible to user, only for debugging)."""
    print(f"[check-stage] {msg}", file=sys.stderr)


# Transition thresholds (in days)
STAGE_1_TO_2_DAYS = 3   # 3 full calendar days silent → recall phase
STAGE_2_TO_3_DAYS = 3   # 3 days of recall messages (Day 4-6) → final recall
STAGE_3_TO_4_DAYS = 1   # 1 day after final recall → weekly recall
STAGE_4_TO_5_WEEKS = 3  # 3 weeks of weekly recalls → monthly recall

ENGAGEMENT_DEFAULTS = {
    "notification_stage": 1,
    "stage_changed_at": None,
    "last_recall_date": None,
    "recall_2_sent": False,
    "reminder_config": {},
}


def load_engagement(workspace_dir):
    """Load engagement.json, returning (data_dict, file_existed)."""
    path = os.path.join(workspace_dir, "data", "engagement.json")
    if not os.path.exists(path):
        return dict(ENGAGEMENT_DEFAULTS), False
    try:
        with open(path) as f:
            data = json.load(f)
        for key, default in ENGAGEMENT_DEFAULTS.items():
            if key not in data:
                data[key] = default
        return data, True
    except (json.JSONDecodeError, IOError) as e:
        log(f"Warning: could not read engagement.json: {e}")
        return dict(ENGAGEMENT_DEFAULTS), False


def save_engagement(workspace_dir, data):
    """Write engagement.json (creates data/ dir if needed)."""
    path = os.path.join(workspace_dir, "data", "engagement.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def parse_iso(s):
    """Parse an ISO-8601 datetime string, returning None on failure."""
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def normalize_stage(stage):
    """Convert stage to int (handles string names from older formats)."""
    if isinstance(stage, int):
        return stage
    if isinstance(stage, str):
        stage_map = {"active": 1, "pause": 2, "recall": 3, "silent": 4}
        return stage_map.get(stage.lower(), 1)
    return 1


def _meal_has_food(meal):
    """Check if a meal dict contains actual food data (items or foods list)."""
    if not isinstance(meal, dict):
        return False
    # Explicit status takes precedence if present
    if meal.get("status") == "logged":
        return True
    # Fallback: has non-empty items or foods list
    items = meal.get("items") or meal.get("foods")
    return bool(items)


def get_last_logged_date(workspace_dir):
    """
    Scan data/meals/*.json to find the most recent date with at least one
    meal entry that contains actual food data. Returns a date string (YYYY-MM-DD)
    or None if no logged meals found.
    """
    meals_dir = os.path.join(workspace_dir, "data", "meals")
    if not os.path.isdir(meals_dir):
        return None

    date_pattern = re.compile(r"(\d{4}-\d{2}-\d{2})\.json$")
    logged_dates = []

    for filepath in glob.glob(os.path.join(meals_dir, "*.json")):
        match = date_pattern.match(os.path.basename(filepath))
        if not match:
            continue
        date_str = match.group(1)
        try:
            with open(filepath) as f:
                meals = json.load(f)
        except (json.JSONDecodeError, IOError):
            continue

        has_logged = False
        if isinstance(meals, list):
            has_logged = any(_meal_has_food(m) for m in meals)
        elif isinstance(meals, dict):
            for key, meal in meals.items():
                if _meal_has_food(meal):
                    has_logged = True
                    break

        if has_logged:
            logged_dates.append(date_str)

    return max(logged_dates) if logged_dates else None


def main():
    parser = argparse.ArgumentParser(
        description="Update engagement stage based on user silence duration"
    )
    parser.add_argument("--workspace-dir", required=True, help="Agent workspace root")
    parser.add_argument("--tz-offset", required=True, type=int,
                        help="Timezone offset in seconds from UTC")
    args = parser.parse_args()

    data, existed = load_engagement(args.workspace_dir)
    tz = timezone(timedelta(seconds=args.tz_offset))
    now = datetime.now(tz)
    today_str = now.strftime("%Y-%m-%d")

    stage = normalize_stage(data.get("notification_stage", 1))
    stage_changed_at = parse_iso(data.get("stage_changed_at"))

    # --- Derive last interaction from meal records ---
    last_logged = get_last_logged_date(args.workspace_dir)

    if last_logged is None:
        # No meal records at all — user hasn't started logging yet, stay at current stage
        if not existed:
            data["stage_changed_at"] = now.isoformat()
            save_engagement(args.workspace_dir, data)
            log("No meal records found, initialized engagement.json")
        print(f"{stage} 0")
        return

    # Calculate days since last logged meal (in calendar days)
    last_logged_date = datetime.strptime(last_logged, "%Y-%m-%d").date()
    today_date = now.date()
    days_silent = (today_date - last_logged_date).days

    log(f"Last logged meal: {last_logged}, days silent: {days_silent}, stage: {stage}")

    old_stage = stage
    changed = False

    # --- User returned: logged a meal today or yesterday but stage > 1 ---
    if stage > 1 and days_silent <= 1:
        stage = 1
        data["notification_stage"] = 1
        data["stage_changed_at"] = now.isoformat()
        data["last_recall_date"] = None
        data["recall_2_sent"] = False
        data["recall_count"] = 0
        data["last_nudge_date"] = None
        changed = True
        log(f"RESET to stage 1 (user returned, last logged {last_logged})")

    # --- Forward transitions ---
    elif stage == 1:
        if days_silent >= STAGE_1_TO_2_DAYS:
            stage = 2
            data["notification_stage"] = 2
            data["stage_changed_at"] = now.isoformat()
            data["last_recall_date"] = None
            data["recall_2_sent"] = False
            changed = True
            log(f"TRANSITION 1 → 2 (silent {days_silent} days)")

    elif stage == 2:
        if stage_changed_at:
            days_in_stage = (now - stage_changed_at).total_seconds() / 86400
            if days_in_stage >= STAGE_2_TO_3_DAYS:
                stage = 3
                data["notification_stage"] = 3
                data["stage_changed_at"] = now.isoformat()
                data["recall_2_sent"] = False
                changed = True
                log(f"TRANSITION 2 → 3 (in stage 2 for {days_in_stage:.1f} days)")

    elif stage == 3:
        if stage_changed_at:
            days_in_stage = (now - stage_changed_at).total_seconds() / 86400
            if days_in_stage >= STAGE_3_TO_4_DAYS:
                stage = 4
                data["notification_stage"] = 4
                data["stage_changed_at"] = now.isoformat()
                data["weekly_recall_count"] = 0
                changed = True
                log(f"TRANSITION 3 → 4 (in stage 3 for {days_in_stage:.1f} days)")

    elif stage == 4:
        if stage_changed_at:
            weeks_in_stage = (now - stage_changed_at).total_seconds() / (86400 * 7)
            if weeks_in_stage >= STAGE_4_TO_5_WEEKS:
                stage = 5
                data["notification_stage"] = 5
                data["stage_changed_at"] = now.isoformat()
                data["monthly_recall_count"] = 0
                changed = True
                log(f"TRANSITION 4 → 5 (in stage 4 for {weeks_in_stage:.1f} weeks)")

    # Stage 5 is permanent — no further transitions

    if changed or not existed:
        save_engagement(args.workspace_dir, data)

    # Output: "stage days_silent" (e.g. "1 2" = Stage 1, 2 days silent)
    print(f"{stage} {days_silent}")


if __name__ == "__main__":
    main()
