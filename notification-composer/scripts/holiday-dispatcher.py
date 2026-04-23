#!/usr/bin/env python3
"""
holiday-dispatcher.py — Check for upcoming holidays and create one-shot
cron jobs to ask eligible users about their vacation plans.

Usage (main agent's daily cron, 01:00):
  python3 holiday-dispatcher.py \
    --openclaw-dir ~/.openclaw \
    --tz-offset 28800

Flow:
  1. Load holiday JSON for current year + region
  2. If no holiday within 3 days → exit immediately
  3. Scan all user workspaces → filter eligible users
  4. For each eligible user, create a one-shot cron (breakfast - 30min)
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HOLIDAYS_DIR = os.path.join(SCRIPT_DIR, "..", "references", "holidays")
LOOKAHEAD_DAYS = 3


def log(msg):
    print(f"[holiday-dispatcher] {msg}", file=sys.stderr)


def get_today(tz_offset, mock_date=None):
    if mock_date:
        return datetime.strptime(mock_date, "%Y-%m-%d").date()
    tz = timezone(timedelta(seconds=tz_offset))
    return datetime.now(tz).date()


def load_holidays(year, region="cn"):
    """Load holidays from JSON file."""
    path = os.path.join(HOLIDAYS_DIR, f"{region}-{year}.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("holidays", [])
    except (json.JSONDecodeError, IOError):
        return []


def find_upcoming_holiday(today, region="cn"):
    """Find a holiday starting within LOOKAHEAD_DAYS. Returns holiday dict or None."""
    holidays = load_holidays(today.year, region)
    for h in holidays:
        try:
            start = datetime.strptime(h["start"], "%Y-%m-%d").date()
        except (ValueError, KeyError):
            continue
        delta = (start - today).days
        if 0 <= delta <= LOOKAHEAD_DAYS:
            return h
    return None


def detect_region(workspace_dir):
    """Detect user region from USER.md Language field."""
    lang_map = {"zh-cn": "cn", "zh-tw": "cn", "zh": "cn", "en-us": "us", "en": "us"}
    user_md = os.path.join(workspace_dir, "USER.md")
    if os.path.exists(user_md):
        try:
            with open(user_md, "r", encoding="utf-8") as f:
                for line in f:
                    if "language" in line.lower() and ":" in line:
                        lang = line.split(":", 1)[1].strip().lower()
                        if lang in lang_map:
                            return lang_map[lang]
                        break
        except IOError:
            pass
    return "cn"


def get_breakfast_time(workspace_dir):
    """Read user's breakfast reminder time from engagement.json or health-profile.md.
    Returns hour (int) or default 9."""
    # Try engagement.json first
    eng_path = os.path.join(workspace_dir, "data", "engagement.json")
    if os.path.exists(eng_path):
        try:
            with open(eng_path) as f:
                data = json.load(f)
            config = data.get("reminder_config", {})
            breakfast_time = config.get("breakfast", config.get("meal_1", ""))
            if breakfast_time and ":" in str(breakfast_time):
                return int(str(breakfast_time).split(":")[0])
        except (json.JSONDecodeError, IOError, ValueError):
            pass

    # Try health-profile.md
    hp_path = os.path.join(workspace_dir, "health-profile.md")
    if os.path.exists(hp_path):
        try:
            with open(hp_path, "r", encoding="utf-8") as f:
                in_schedule = False
                for line in f:
                    if "meal schedule" in line.lower() or "提醒时间" in line.lower():
                        in_schedule = True
                        continue
                    if in_schedule and ("breakfast" in line.lower() or "早餐" in line):
                        # Extract time like "09:00" or "9:00"
                        import re
                        m = re.search(r'(\d{1,2}):(\d{2})', line)
                        if m:
                            return int(m.group(1))
        except IOError:
            pass

    return 9  # default


def get_engagement_stage(workspace_dir):
    """Read engagement stage. Default 1 (active)."""
    eng_path = os.path.join(workspace_dir, "data", "engagement.json")
    if os.path.exists(eng_path):
        try:
            with open(eng_path) as f:
                data = json.load(f)
            return data.get("notification_stage", data.get("stage", 1))
        except (json.JSONDecodeError, IOError):
            pass
    return 1


def is_already_asked(workspace_dir, holiday_name):
    """Check if this holiday has already been asked about."""
    leave_path = os.path.join(workspace_dir, "data", "leave.json")
    if not os.path.exists(leave_path):
        return False
    try:
        with open(leave_path) as f:
            data = json.load(f)
        # Already has active leave → don't ask
        if data.get("active"):
            return True
        # Already asked about this specific holiday
        if data.get("holiday_asked") == holiday_name:
            return True
    except (json.JSONDecodeError, IOError):
        pass
    return False


def mark_holiday_asked(workspace_dir, holiday_name):
    """Write holiday_asked to leave.json."""
    leave_path = os.path.join(workspace_dir, "data", "leave.json")
    data = {}
    if os.path.exists(leave_path):
        try:
            with open(leave_path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    data["holiday_asked"] = holiday_name
    os.makedirs(os.path.dirname(leave_path), exist_ok=True)
    with open(leave_path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def create_cron(agent_id, trigger_time_utc, holiday_name, holiday_start, holiday_end, dry_run=False):
    """Create a one-shot cron job for the user."""
    message = (
        f"假期提醒：{holiday_name}（{holiday_start} 至 {holiday_end}）即将到来。"
        f"请询问用户假期期间是否需要暂停打卡提醒。"
        f"如果用户说需要，调用 leave-manager.py set 设置请假。"
        f"如果用户说不需要，就正常结束。"
    )

    at_time = trigger_time_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    cmd = [
        "openclaw", "cron", "add",
        "--agent", agent_id,
        "--at", at_time,
        "--delete-after-run",
        "--session", "isolated",
        "--message", message,
        "--name", f"holiday-ask-{holiday_name}",
        "--announce",
        "--channel", "wechat",
        "--timeout", "30000",
        "--tz", "Asia/Shanghai",
    ]

    if dry_run:
        return {"cmd": " ".join(cmd), "status": "dry-run"}

    try:
        # Use Popen to avoid blocking (cron add can take 30-60s via Kafka)
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=90
        )
        stdout, stderr = proc.communicate(timeout=90)
        if proc.returncode == 0:
            return {"status": "created", "output": stdout.decode()[:200]}
        else:
            return {"status": "error", "error": stderr.decode()[:200]}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def scan_and_dispatch(openclaw_dir, tz_offset, holiday, today, dry_run=False):
    """Scan all workspaces and create cron jobs for eligible users."""
    results = []

    for entry in sorted(os.listdir(openclaw_dir)):
        if not entry.startswith("workspace-") or "-dm-" not in entry:
            continue

        workspace_dir = os.path.join(openclaw_dir, entry)
        if not os.path.isdir(workspace_dir):
            continue

        agent_id = entry.replace("workspace-", "")

        # Check onboarded
        if not os.path.exists(os.path.join(workspace_dir, "health-profile.md")):
            results.append({"agent_id": agent_id, "status": "skipped", "reason": "not onboarded"})
            continue

        # Check stage
        stage = get_engagement_stage(workspace_dir)
        if stage >= 2:
            results.append({"agent_id": agent_id, "status": "skipped", "reason": f"stage {stage}"})
            continue

        # Check already asked
        if is_already_asked(workspace_dir, holiday["name"]):
            results.append({"agent_id": agent_id, "status": "skipped", "reason": "already asked or has leave"})
            continue

        # Get breakfast time and compute trigger time (breakfast - 30min)
        breakfast_hour = get_breakfast_time(workspace_dir)
        # Convert to UTC: breakfast_hour in local time - tz_offset
        tz = timezone(timedelta(seconds=tz_offset))
        local_trigger = datetime(
            today.year, today.month, today.day,
            breakfast_hour, 0, tzinfo=tz
        ) - timedelta(minutes=30)
        trigger_utc = local_trigger.astimezone(timezone.utc)

        # If trigger time already passed today, skip
        now_utc = datetime.now(timezone.utc)
        if trigger_utc <= now_utc:
            results.append({"agent_id": agent_id, "status": "skipped", "reason": "trigger time already passed"})
            continue

        # Mark as asked
        mark_holiday_asked(workspace_dir, holiday["name"])

        # Create cron
        cron_result = create_cron(
            agent_id, trigger_utc,
            holiday["name"], holiday["start"], holiday["end"],
            dry_run=dry_run
        )
        cron_result["agent_id"] = agent_id
        cron_result["trigger_time"] = trigger_utc.isoformat()
        results.append(cron_result)

    return results


def main():
    parser = argparse.ArgumentParser(description="Holiday dispatcher — scan users and create holiday inquiry crons")
    parser.add_argument("--openclaw-dir", required=True, help="Path to ~/.openclaw")
    parser.add_argument("--tz-offset", type=int, required=True, help="Timezone offset in seconds")
    parser.add_argument("--mock-date", default=None, help="Mock today's date YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true", help="Don't create crons, just show what would happen")
    args = parser.parse_args()

    today = get_today(args.tz_offset, args.mock_date)
    log(f"Today: {today}")

    # Step 1: Check if any holiday is within 3 days
    # Try all regions that might be relevant
    holiday = None
    for region in ["cn", "us"]:
        holiday = find_upcoming_holiday(today, region)
        if holiday:
            break

    if not holiday:
        log("No upcoming holiday within 3 days. Done.")
        print(json.dumps({"status": "no_holiday", "date": str(today)}))
        return

    log(f"Found upcoming holiday: {holiday['name']} ({holiday['start']} to {holiday['end']})")

    # Step 2: Scan users and create crons
    results = scan_and_dispatch(
        args.openclaw_dir, args.tz_offset, holiday, today,
        dry_run=args.dry_run
    )

    output = {
        "status": "dispatched",
        "date": str(today),
        "holiday": holiday,
        "users": results,
        "summary": {
            "total": len(results),
            "created": sum(1 for r in results if r.get("status") == "created"),
            "skipped": sum(1 for r in results if r.get("status") == "skipped"),
            "dry_run": sum(1 for r in results if r.get("status") == "dry-run"),
            "errors": sum(1 for r in results if r.get("status") == "error"),
        }
    }

    json.dump(output, sys.stdout, ensure_ascii=False, indent=2)
    print()


if __name__ == "__main__":
    main()
