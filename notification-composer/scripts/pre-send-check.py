#!/usr/bin/env python3
"""
pre-send-check.py — Deterministic pre-send checks for meal/weight reminders.

Returns SEND or NO_REPLY (with reason on stderr for logging).
The model should NOT be invoked if this returns NO_REPLY.

Usage:
  python3 pre-send-check.py --workspace-dir <path> --meal-type <type> --tz-offset <seconds>

  --workspace-dir   Agent workspace root (contains health-profile.md, data/, etc.)
  --meal-type       One of: breakfast, lunch, dinner, meal_1, meal_2, weight,
                    weight_morning_followup
  --tz-offset       Timezone offset in seconds from UTC (e.g. 28800 for UTC+8)

Exit code 0 always. Output is exactly "SEND" or "NO_REPLY" on stdout.
Reason is printed to stderr for debugging.
"""

import argparse
import fcntl
import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta

def _normalize_path(p):
    """Lowercase wechat-dm/wecom-dm segment to avoid case-mismatch directories."""
    import re as _re
    return _re.sub(r'(workspace-(?:wechat|wecom)-dm-)([^/]+)', lambda m: m.group(1) + m.group(2).lower(), p)



def log(msg):
    """Log to stderr (not visible to user, only for debugging)."""
    print(f"[pre-send-check] {msg}", file=sys.stderr)


def _run_check_stage(workspace_dir, tz_offset):
    """Auto-run check-stage.py to ensure engagement.json is current.
    
    This makes pre-send-check self-contained — it no longer depends on
    the agent calling check-stage.py first. check-stage is idempotent:
    running it multiple times in the same minute produces the same result.
    """
    eng_path = os.path.join(workspace_dir, "data", "engagement.json")
    script = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "..", "notification-manager", "scripts", "check-stage.py"
    )
    if not os.path.exists(script):
        log(f"check-stage.py not found at {script}, skipping")
        return
    try:
        result = subprocess.run(
            [sys.executable, script,
             "--workspace-dir", workspace_dir,
             "--tz-offset", str(tz_offset)],
            capture_output=True, text=True, timeout=10
        )
        if result.stdout.strip():
            log(f"check-stage output: {result.stdout.strip()}")
        if result.returncode != 0:
            log(f"check-stage exited {result.returncode}: {result.stderr.strip()}")
    except Exception as e:
        log(f"check-stage failed: {e}")


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


def _update_engagement_field(workspace_dir, updates):
    """Read-modify-write specific fields in engagement.json."""
    path = os.path.join(workspace_dir, "data", "engagement.json")
    try:
        with open(path) as f:
            data = json.load(f)
        data.update(updates)
        with open(path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except (json.JSONDecodeError, IOError) as e:
        log(f"Warning: could not update engagement.json: {e}")


def check_engagement_stage(workspace_dir, meal_type, tz_offset):
    """Check 2: engagement stage gating.

    Stage 1 (ACTIVE):  SEND — normal reminder
    Stage 2 (RECALL):  SEND once per day (first meal cron only, suppress rest)
                        Weight reminders suppressed entirely.
    Stage 3 (WEEKLY):  SEND once per week (if >= 7 days since last_recall_date)
                        Weight reminders suppressed entirely.
    Stage 4 (MONTHLY): SEND once per month (if >= 30 days since last_recall_date)
                        Weight reminders suppressed entirely.
    Stage 5 (SILENT):  NO_REPLY — suppress everything

    Uses file locking to prevent concurrent crons from all passing the gate.
    """
    path = os.path.join(workspace_dir, "data", "engagement.json")
    if not os.path.exists(path):
        return True, None

    # Acquire exclusive lock for the entire check-and-update operation.
    # This prevents concurrent cron processes from all reading stale data.
    lockfile = path + ".lock"
    lock_fd = None
    try:
        lock_fd = open(lockfile, "w")
        fcntl.flock(lock_fd, fcntl.LOCK_EX)

        with open(path) as f:
            data = json.load(f)
        stage = data.get("notification_stage", 1)
        if isinstance(stage, str):
            stage_map = {"active": 1, "pause": 2, "recall": 3, "silent": 4}
            stage = stage_map.get(stage.lower(), 1)
        if stage >= 5:
            return False, f"notification_stage={stage} — user is in silent mode"

        # Stage 2-4: suppress weight reminders entirely
        if stage in (2, 3, 4):
            is_weight = meal_type in ("weight", "weight_morning_followup")
            if is_weight:
                return False, f"notification_stage={stage} — weight reminders suppressed during recall"

        # Stage 2-4: suppress custom reminders, daily summaries
        # Stage 3-4: also suppress weekly reports
        if stage in (2, 3, 4):
            is_non_recall = meal_type in ("custom", "daily_summary")
            if is_non_recall:
                return False, f"notification_stage={stage} — {meal_type} suppressed during recall"
            if stage >= 3 and meal_type == "weekly_report":
                return False, f"notification_stage={stage} — weekly_report suppressed at stage 3+"

        # Stage 2: only allow lunch slot, only on days_silent 3 or 5 (Day 3 and Day 5)
        # Exception: weekly_report is allowed through at S2 (user has recent data)
        if stage == 2 and meal_type not in ("weekly_report",):
            is_lunch = meal_type in ("lunch", "meal_2")
            if not is_lunch:
                return False, f"notification_stage=2 — only lunch recall allowed, got {meal_type}"
            days_silent_val = data.get("days_silent", 0)
            if days_silent_val not in (3, 5):
                return False, f"notification_stage=2 — days_silent={days_silent_val}, recall only on day 3 (ds=3) and day 5 (ds=5)"

        # Stage 3-4: also only allow lunch slot for recall messages
        if stage in (3, 4):
            is_lunch = meal_type in ("lunch", "meal_2")
            if not is_lunch:
                return False, f"notification_stage={stage} — only lunch recall allowed, got {meal_type}"

        local_date = get_local_date(tz_offset)

        if stage == 2:
            last_recall_date = data.get("last_recall_date", "")
            if last_recall_date == local_date:
                return False, f"notification_stage=2, recall already sent today ({local_date})"
            # Atomically claim today's slot under lock
            data["last_recall_date"] = local_date
            with open(path, "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            days_silent_val = data.get("days_silent", 0)
            return True, f"recall stage=2 days_silent={days_silent_val}"

        if stage == 3:
            last_recall_date = data.get("last_recall_date", "")
            if last_recall_date:
                try:
                    last = datetime.strptime(last_recall_date, "%Y-%m-%d").date()
                    today = datetime.strptime(local_date, "%Y-%m-%d").date()
                    if (today - last).days < 7:
                        return False, f"notification_stage=3, weekly recall sent {last_recall_date} (<7 days)"
                except ValueError:
                    pass
            # Atomically claim under lock
            data["last_recall_date"] = local_date
            with open(path, "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True, None

        if stage == 4:
            last_recall_date = data.get("last_recall_date", "")
            if last_recall_date:
                try:
                    last = datetime.strptime(last_recall_date, "%Y-%m-%d").date()
                    today = datetime.strptime(local_date, "%Y-%m-%d").date()
                    if (today - last).days < 30:
                        return False, f"notification_stage=4, monthly recall sent {last_recall_date} (<30 days)"
                except ValueError:
                    pass
            # Atomically claim under lock
            data["last_recall_date"] = local_date
            with open(path, "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True, None

        return True, None
    except (json.JSONDecodeError, IOError) as e:
        log(f"Warning: could not read engagement.json: {e}")
        return True, None  # fail-open: send if we can't read
    finally:
        if lock_fd:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                lock_fd.close()
            except Exception:
                pass


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

    for meal in meals:
        mt = meal.get("meal_type", "") or meal.get("name", "")
        if mt == meal_type:
            return False, f"{meal_type} already logged today ({local_date})"

    return True, None


def check_weight_logged(workspace_dir, tz_offset):
    """Check for weight: already weighed today?"""
    local_date = get_local_date(tz_offset)
    return _weight_logged_on(workspace_dir, local_date)


def check_weight_logged_yesterday_or_today(workspace_dir, tz_offset):
    """Check for weight morning followup: suppress if user weighed yesterday or today."""
    tz = timezone(timedelta(seconds=tz_offset))
    now = datetime.now(tz)
    today = now.strftime("%Y-%m-%d")
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")

    logged_today, _ = _weight_logged_on(workspace_dir, today)
    logged_yesterday, _ = _weight_logged_on(workspace_dir, yesterday)

    if not logged_today:
        return False, f"weight already logged today ({today}) — no morning followup needed"
    if not logged_yesterday:
        return False, f"weight logged yesterday ({yesterday}) — no morning followup needed"
    return True, None


def _weight_logged_on(workspace_dir, date_str):
    """Helper: check if weight was logged on a specific date. Returns (not_logged, reason)."""
    weight_file = os.path.join(workspace_dir, "data", "weight.json")

    if not os.path.exists(weight_file):
        return True, None

    try:
        with open(weight_file) as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        log(f"Warning: could not read weight.json: {e}")
        return True, None

    # weight.json keys are ISO-8601 datetimes; check date prefix
    if isinstance(data, dict):
        for key in data:
            if key[:10] == date_str:
                return False, f"weight logged on {date_str}"

    # Also handle list format
    if isinstance(data, list):
        for record in data:
            record_date = record.get("date", "")
            if record_date == date_str:
                return False, f"weight logged on {date_str}"

    records = data.get("records", []) if isinstance(data, dict) else []
    for record in records:
        record_date = record.get("date", "")
        if record_date == date_str:
            return False, f"weight logged on {date_str}"

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


def check_leave(workspace_dir, tz_offset, mock_date=None):
    """Check if user is on leave. If so, suppress all reminders.

    Simplified model:
      - leave.json exists with start/end → on leave
      - leave.json absent or empty/invalid → not on leave
      - today > end → delete file (auto-expire) → allow send
    No 'active' field needed — file existence = leave is set.
    """
    leave_path = os.path.join(workspace_dir, "data", "leave.json")
    if not os.path.exists(leave_path):
        return True, None

    try:
        with open(leave_path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError):
        # Corrupted file — treat as no leave, remove it
        try:
            os.remove(leave_path)
        except OSError:
            pass
        return True, None

    start = data.get("start", "")
    end = data.get("end", "")

    # No valid dates → not a real leave file, clean up
    if not start or not end:
        try:
            os.remove(leave_path)
        except OSError:
            pass
        return True, None

    if mock_date:
        today = mock_date
    else:
        tz = timezone(timedelta(seconds=tz_offset))
        today = datetime.now(tz).strftime("%Y-%m-%d")

    if start <= today <= end:
        return False, f"user on leave ({start} to {end})"

    # Auto-expire: leave ended → delete file
    if today > end:
        try:
            os.remove(leave_path)
        except FileNotFoundError:
            pass  # concurrent cron already deleted it
        except OSError as e:
            log(f"Warning: could not delete expired leave.json: {e}")
            # Still allow send even if delete fails

    return True, None




def main():
    parser = argparse.ArgumentParser(description="Pre-send check for meal/weight reminders")
    parser.add_argument("--workspace-dir", required=True, help="Agent workspace root")
    parser.add_argument("--meal-type", required=True,
                        choices=["breakfast", "lunch", "dinner", "meal_1", "meal_2",
                                 "weight", "weight_morning_followup",
                                 "custom", "weekly_report", "daily_summary"],
                        help="Meal type to check")
    parser.add_argument("--tz-offset", required=True, type=int,
                        help="Timezone offset in seconds from UTC")
    parser.add_argument("--mock-date", default=None,
                        help="Mock today's date YYYY-MM-DD (for testing)")
    args = parser.parse_args()
    args.workspace_dir = _normalize_path(args.workspace_dir)

    # Auto-run check-stage.py BEFORE any checks to ensure engagement.json
    # is up-to-date. This removes the dependency on the agent calling
    # check-stage.py first — pre-send-check is now self-contained.
    _run_check_stage(args.workspace_dir, args.tz_offset)

    checks = [
        ("leave", lambda: check_leave(args.workspace_dir, args.tz_offset, args.mock_date)),
        ("health_profile", lambda: check_health_profile(args.workspace_dir)),
        ("engagement_stage", lambda: check_engagement_stage(
            args.workspace_dir, args.meal_type, args.tz_offset)),
        ("health_flags", lambda: check_health_flags(args.workspace_dir, args.meal_type)),
        ("scheduling", lambda: check_scheduling_constraints(
            args.workspace_dir, args.meal_type, args.tz_offset)),
    ]

    # Add meal-specific or weight-specific check
    if args.meal_type == "weight":
        checks.append(("weight_logged", lambda: check_weight_logged(
            args.workspace_dir, args.tz_offset)))
    elif args.meal_type == "weight_morning_followup":
        checks.append(("weight_logged_yesterday_or_today", lambda: check_weight_logged_yesterday_or_today(
            args.workspace_dir, args.tz_offset)))
    elif args.meal_type in ("custom", "weekly_report", "daily_summary"):
        pass  # Only stage check needed, no meal-logged check
    else:
        checks.append(("meal_logged", lambda: check_meal_logged(
            args.workspace_dir, args.meal_type, args.tz_offset)))

    # Run all checks
    # Track stage info from engagement_stage check for output
    stage_info = {"stage": 1}

    for check_name, check_fn in checks:
        passed, reason = check_fn()
        if not passed:
            log(f"FAIL [{check_name}]: {reason}")
            print("NO_REPLY")
            return

    # Read stage for output enrichment
    eng_path = os.path.join(args.workspace_dir, "data", "engagement.json")
    if os.path.exists(eng_path):
        try:
            with open(eng_path) as f:
                eng = json.load(f)
            s = eng.get("notification_stage", 1)
            if isinstance(s, str):
                s = {"active": 1, "pause": 2, "recall": 3, "silent": 4}.get(s.lower(), 1)
            stage_info["stage"] = s
            stage_info["days_silent"] = eng.get("days_silent", 0)
        except Exception:
            pass

    log("All checks passed")

    if stage_info["stage"] >= 2:
        print(f"SEND recall stage={stage_info['stage']} days_silent={stage_info.get('days_silent', 0)}")
    else:
        print("SEND")


if __name__ == "__main__":
    main()
