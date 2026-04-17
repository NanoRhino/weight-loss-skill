#!/usr/bin/env python3
"""
check-stage.py — Update engagement stage based on user silence duration.

Derives last interaction from meal logging records (data/meals/*.json)
rather than relying on a platform-written timestamp. A "logged day" is
any date with at least one meal entry that contains food data.

Lifecycle rules:

  Stage 1 (ACTIVE)   → 3 full calendar days silent  → Stage 2 (RECALL)
  Stage 2 (RECALL)   → 3 days of daily recalls       → Stage 3 (WEEKLY)
  Stage 3 (WEEKLY)   → 3 weeks of weekly recalls      → Stage 4 (MONTHLY)
  Stage 4 (MONTHLY)  → 90 days total silence          → Stage 5 (SILENT)
  Stage 5 (SILENT)   → permanent silence

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

def _normalize_path(p):
    """Lowercase wechat-dm/wecom-dm segment to avoid case-mismatch directories."""
    import re as _re
    return _re.sub(r'(workspace-(?:wechat|wecom)-dm-)([^/]+)', lambda m: m.group(1) + m.group(2).lower(), p)



def log(msg):
    """Log to stderr (not visible to user, only for debugging)."""
    print(f"[check-stage] {msg}", file=sys.stderr)


# Transition thresholds
STAGE_1_TO_2_DAYS = 3   # 3 full calendar days silent → daily recall
STAGE_2_TO_3_DAYS = 3   # 3 days of daily recalls (Day 4-6) → weekly recall
STAGE_3_TO_4_WEEKS = 3  # 3 weeks of weekly recalls → monthly recall
STAGE_4_TO_5_DAYS = 90  # 90 days total silence → permanent silence

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

    today_str = datetime.now().strftime("%Y-%m-%d")
    for filepath in glob.glob(os.path.join(meals_dir, "*.json")):
        match = date_pattern.match(os.path.basename(filepath))
        if not match:
            continue
        date_str = match.group(1)
        if date_str > today_str:
            continue  # skip future dates
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
    args.workspace_dir = _normalize_path(args.workspace_dir)

    data, existed = load_engagement(args.workspace_dir)
    tz = timezone(timedelta(seconds=args.tz_offset))
    now = datetime.now(tz)
    today_str = now.strftime("%Y-%m-%d")

    stage = normalize_stage(data.get("notification_stage", 1))
    stage_changed_at = parse_iso(data.get("stage_changed_at"))

    # --- Derive last interaction from meal records ---
    last_logged = get_last_logged_date(args.workspace_dir)

    if last_logged is None:
        # No meal records at all — user hasn't started logging yet.
        # Use stage_changed_at (or engagement creation time) as fallback
        # to calculate days_silent, so users who never logged still
        # transition to recall stages instead of getting normal reminders forever.
        if not existed:
            data["stage_changed_at"] = now.isoformat()
            save_engagement(args.workspace_dir, data)
            log("No meal records found, initialized engagement.json")
            print(f"{stage} 0")
            return

        # Use stage_changed_at as the "last activity" reference
        fallback_date = stage_changed_at
        if fallback_date is None:
            # No stage_changed_at either — treat as just created
            log("No meal records and no stage_changed_at, assuming new user")
            print(f"{stage} 0")
            return

        last_logged_date = fallback_date.date()
        log(f"No meal records, using stage_changed_at as fallback: {fallback_date.isoformat()}")
    else:
        last_logged_date = datetime.strptime(last_logged, "%Y-%m-%d").date()
    today_date = now.date()
    days_silent = (today_date - last_logged_date).days

    log(f"Last logged meal: {last_logged}, days silent: {days_silent}, stage: {stage}")

    old_stage = stage
    changed = False

    # --- User returned: logged a meal today/yesterday but stage > 1 ---
    if stage > 1 and days_silent <= 1:
        stage = 1
        data["notification_stage"] = 1
        data["stage_changed_at"] = now.isoformat()
        data["last_recall_date"] = None
        data["recall_2_sent"] = False
        data["recall_count"] = 0
        data["last_nudge_date"] = None
        changed = True
        log(f"RESET to stage 1 (user returned, last meal {last_logged})")

    # --- Forward transitions (fast-forward to correct stage) ---
    else:
        # Calculate target stage directly from days_silent.
        # This avoids the one-step-per-cron problem where a user stuck at S1
        # due to a reset takes multiple cron cycles to reach the correct stage.
        def calc_target_stage(ds):
            if ds >= STAGE_4_TO_5_DAYS:
                return 5   # 90+ days → permanent silence
            if ds >= STAGE_1_TO_2_DAYS + STAGE_2_TO_3_DAYS * 1 + STAGE_3_TO_4_WEEKS * 7:
                return 4   # 3 + 3 + 21 = 27+ days → monthly recall
            if ds >= STAGE_1_TO_2_DAYS + STAGE_2_TO_3_DAYS:
                return 3   # 3 + 3 = 6+ days → weekly recall
            if ds >= STAGE_1_TO_2_DAYS:
                return 2   # 3+ days → daily recall
            return 1

        target = calc_target_stage(days_silent)
        # Only move forward, never backward (backward is handled by reset above)
        if target > stage:
            old_stage = stage
            stage = target
            data["notification_stage"] = stage
            data["stage_changed_at"] = now.isoformat()
            # DO NOT reset last_recall_date here — pre-send-check uses it
            # for same-day dedup. Resetting it would let a second cron
            # through after the first already sent a recall message.
            # Reset stage-specific counters
            if stage >= 2:
                data["recall_2_sent"] = False
            if stage >= 3:
                data["weekly_recall_count"] = 0
            if stage >= 4:
                data["monthly_recall_count"] = 0
            changed = True
            log(f"FAST-FORWARD {old_stage} → {stage} (silent {days_silent} days)")

    # Stage 5 is permanent silence — no further transitions

    if changed or not existed:
        save_engagement(args.workspace_dir, data)

    # Output: "stage days_silent" (e.g. "1 2" = Stage 1, 2 days silent)
    print(f"{stage} {days_silent}")


if __name__ == "__main__":
    main()
