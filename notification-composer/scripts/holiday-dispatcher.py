#!/usr/bin/env python3
"""
holiday-dispatcher.py — Check for upcoming holidays and create one-shot
cron jobs to ask eligible users about their vacation plans.

Usage (main agent's daily cron, 01:00):
  python3 holiday-dispatcher.py \
    --openclaw-dir ~/.openclaw \
    --tz-offset 28800

Flow:
  1. Load holiday JSONs for all regions, find holidays within LOOKAHEAD_DAYS
  2. If no holiday in any region → exit immediately
  3. Scan all user workspaces → match each user to their region's holiday
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
LOOKAHEAD_DAYS = 5


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


def find_all_upcoming_holidays(today):
    """Scan all region holiday files, return {region: holiday_dict} for holidays within LOOKAHEAD_DAYS.
    Only includes regions that have an upcoming holiday. Returns empty dict if none."""
    result = {}
    if not os.path.isdir(HOLIDAYS_DIR):
        return result
    for fname in os.listdir(HOLIDAYS_DIR):
        if not fname.endswith(".json"):
            continue
        # Extract region from filename like "cn-2026.json"
        parts = fname.replace(".json", "").rsplit("-", 1)
        if len(parts) != 2:
            continue
        region = parts[0]
        holiday = find_upcoming_holiday(today, region)
        if holiday:
            result[region] = holiday
    return result


def detect_language(workspace_dir):
    """Detect user language from USER.md Language field. Returns 'zh' or 'en'."""
    user_md = os.path.join(workspace_dir, "USER.md")
    if os.path.exists(user_md):
        try:
            with open(user_md, "r", encoding="utf-8") as f:
                for line in f:
                    if "language" in line.lower() and ":" in line:
                        # Handle "- **Language:** en-US" format
                        val = line.split(":", 1)[1].strip().lower()
                        val = val.lstrip("* ").strip()
                        if val.startswith("en"):
                            return "en"
                        break
        except IOError:
            pass
    return "zh"


def detect_timezone(workspace_dir):
    """Detect user timezone from USER.md Timezone field. Returns IANA tz name like 'Asia/Shanghai'."""
    user_md = os.path.join(workspace_dir, "USER.md")
    if os.path.exists(user_md):
        try:
            with open(user_md, "r", encoding="utf-8") as f:
                for line in f:
                    if "timezone" in line.lower() and ":" in line:
                        val = line.split(":", 1)[1].strip()
                        val = val.lstrip("* ").strip()
                        if "/" in val:  # Basic sanity check for IANA format
                            return val
                        break
        except IOError:
            pass
    return "Asia/Shanghai"


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
                        lang = lang.lstrip("* ").strip()
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
            raw = data.get("notification_stage", data.get("stage", 1))
            try:
                return int(raw)
            except (ValueError, TypeError):
                return 1
        except (json.JSONDecodeError, IOError):
            pass
    return 1


def is_already_asked(workspace_dir, holiday_name):
    """Check if this holiday has already been asked about.

    Checks two things:
    1. leave.json exists → user already has leave set → don't ask
    2. engagement.json has holiday_asked matching this holiday → already asked
    """
    # Check if leave is already set
    leave_path = os.path.join(workspace_dir, "data", "leave.json")
    if os.path.exists(leave_path):
        try:
            with open(leave_path) as f:
                data = json.load(f)
            if data.get("start") and data.get("end"):
                return True  # has active leave
        except (json.JSONDecodeError, IOError):
            pass

    # Check if already asked (stored in engagement.json)
    eng_path = os.path.join(workspace_dir, "data", "engagement.json")
    if os.path.exists(eng_path):
        try:
            with open(eng_path) as f:
                data = json.load(f)
            if data.get("holiday_asked") == holiday_name:
                return True
        except (json.JSONDecodeError, IOError):
            pass

    return False


def mark_holiday_asked(workspace_dir, holiday_name):
    """Write holiday_asked to engagement.json (not leave.json)."""
    eng_path = os.path.join(workspace_dir, "data", "engagement.json")
    data = {}
    if os.path.exists(eng_path):
        try:
            with open(eng_path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    data["holiday_asked"] = holiday_name
    os.makedirs(os.path.dirname(eng_path), exist_ok=True)
    with open(eng_path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def create_cron(agent_id, trigger_time_utc, holiday_name, holiday_start, holiday_end, lang="zh", tz_name="Asia/Shanghai", dry_run=False):
    """Create a one-shot cron job for the user."""
    if lang == "en":
        message = (
            f"{holiday_name} ({holiday_start} to {holiday_end}) is coming up. "
            f"Send the user a message asking if they have any plans for the holiday "
            f"and which days they won't be able to log meals. "
            f"Note: just ask — don't decide for the user. "
            f"Once they reply with specific dates, call leave-manager.py set to set the leave. "
            f"The end date = the last day the user is away (not the day they return). "
            f"For example, if the user says 'back on the 5th', set --end to the 4th. "
            f"If the user says they don't need a break, say okay. "
            f"Also let them know: anytime they're unable to log meals (not just holidays), "
            f"they can just tell you and you'll pause reminders."
        )
    else:
        message = (
            f"{holiday_name}（{holiday_start} 至 {holiday_end}）快到了。"
            f"给用户发一条消息，问问假期有没有出去玩的计划，哪几天不方便打卡记录。"
            f"注意：你只需要问用户，不要自己替用户做决定。"
            f"等用户回复了具体日期后，再调用 leave-manager.py set 设置请假。"
            f"end 日期 = 用户不在的最后一天（不含回来当天）。"
            f"例如用户说'5号回来'，set --end 2026-05-04（4号是最后一天不在）。"
            f"如果用户说不需要暂停，就说好的。"
            f"另外告诉用户：不只是假期，平时如果有不方便记录饮食的时候，也可以随时跟我说，我会暂停提醒。"
        )

    at_time = trigger_time_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Derive channel and recipient from agent_id prefix
    if agent_id.startswith("wecom-dm-"):
        channel = "wecom"
        to_user = agent_id.replace("wecom-dm-", "")
    else:
        channel = "wechat"
        to_user = agent_id.replace("wechat-dm-", "")

    cmd = [
        "openclaw", "cron", "add",
        "--agent", agent_id,
        "--at", at_time,
        "--delete-after-run",
        "--session", "isolated",
        "--message", message,
        "--name", f"holiday-ask-{holiday_name}",
        "--announce",
        "--channel", channel,
        "--to", to_user,
        "--timeout", "30000",
        "--tz", tz_name,
    ]

    if dry_run:
        return {"cmd": " ".join(cmd), "status": "dry-run"}

    try:
        # Use Popen to avoid blocking (cron add can take 30-60s via Kafka)
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        stdout, stderr = proc.communicate(timeout=90)
        if proc.returncode == 0:
            return {"status": "created", "output": stdout.decode()[:200]}
        else:
            return {"status": "error", "error": stderr.decode()[:200]}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def scan_and_dispatch(openclaw_dir, tz_offset, holidays_by_region, today, dry_run=False,
                      agent_filter=None):
    """Scan all workspaces and create cron jobs for eligible users.

    Args:
        holidays_by_region: dict of {region: holiday_dict} from find_all_upcoming_holidays
        agent_filter: optional set of agent_ids to include (skip all others)
    """
    results = []

    for entry in sorted(os.listdir(openclaw_dir)):
        if not entry.startswith("workspace-") or "-dm-" not in entry:
            continue

        workspace_dir = os.path.join(openclaw_dir, entry)
        if not os.path.isdir(workspace_dir):
            continue

        agent_id = entry.replace("workspace-", "")

        # Filter by agent list if provided
        if agent_filter and agent_id not in agent_filter:
            continue

        # Check onboarded
        if not os.path.exists(os.path.join(workspace_dir, "health-profile.md")):
            results.append({"agent_id": agent_id, "status": "skipped", "reason": "not onboarded"})
            continue

        # Check stage
        stage = get_engagement_stage(workspace_dir)
        if stage >= 2:
            results.append({"agent_id": agent_id, "status": "skipped", "reason": f"stage {stage}"})
            continue

        # Check recently active (meal logged in last 7 days)
        meals_dir = os.path.join(workspace_dir, "data", "meals")
        recently_active = False
        if os.path.isdir(meals_dir):
            cutoff_str = (today - timedelta(days=7)).strftime("%Y-%m-%d")
            for mf in os.listdir(meals_dir):
                if mf.endswith(".json") and not mf.endswith(".reset"):
                    if mf.replace(".json", "") >= cutoff_str:
                        try:
                            with open(os.path.join(meals_dir, mf)) as f:
                                data = json.load(f)
                            if isinstance(data, list) and len(data) > 0:
                                recently_active = True
                                break
                        except Exception:
                            pass
        if not recently_active:
            results.append({"agent_id": agent_id, "status": "skipped", "reason": "no meals in last 7 days"})
            continue

        # Match holiday by user's region
        user_region = detect_region(workspace_dir)
        holiday = holidays_by_region.get(user_region)
        if not holiday:
            results.append({"agent_id": agent_id, "status": "skipped", "reason": f"no holiday for region {user_region}"})
            continue

        # Check already asked
        if is_already_asked(workspace_dir, holiday["name"]):
            results.append({"agent_id": agent_id, "status": "skipped", "reason": "already asked or has leave"})
            continue

        # Compute trigger time
        # Get breakfast time and compute trigger time (breakfast - 30min)
        breakfast_hour = get_breakfast_time(workspace_dir)
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

        # Detect language and timezone for cron message
        lang = detect_language(workspace_dir)
        tz_name = detect_timezone(workspace_dir)

        # Create cron
        cron_result = create_cron(
            agent_id, trigger_utc,
            holiday["name"], holiday["start"], holiday["end"],
            lang=lang,
            tz_name=tz_name,
            dry_run=dry_run
        )
        cron_result["agent_id"] = agent_id
        cron_result["trigger_time"] = trigger_utc.isoformat()
        results.append(cron_result)

        # Mark as asked ONLY after successful cron creation
        if cron_result.get("status") == "created":
            mark_holiday_asked(workspace_dir, holiday["name"])

    return results


def main():
    parser = argparse.ArgumentParser(description="Holiday dispatcher — scan users and create holiday inquiry crons")
    parser.add_argument("--openclaw-dir", required=True, help="Path to ~/.openclaw")
    parser.add_argument("--tz-offset", type=int, required=True, help="Timezone offset in seconds")
    parser.add_argument("--mock-date", default=None, help="Mock today's date YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true", help="Don't create crons, just show what would happen")
    parser.add_argument("--agents", default=None, help="Comma-separated agent IDs to target (skip all others)")
    args = parser.parse_args()

    today = get_today(args.tz_offset, args.mock_date)
    log(f"Today: {today}")

    # Step 1: Check all regions for upcoming holidays within LOOKAHEAD_DAYS
    holidays_by_region = find_all_upcoming_holidays(today)

    if not holidays_by_region:
        log(f"No upcoming holiday within {LOOKAHEAD_DAYS} days. Done.")
        print(json.dumps({"status": "no_holiday", "date": str(today)}))
        return

    for region, h in holidays_by_region.items():
        log(f"Found upcoming holiday [{region}]: {h['name']} ({h['start']} to {h['end']})")

    # Step 2: Scan users and create crons (each user matched to their region's holiday)
    agent_filter = set(args.agents.split(",")) if args.agents else None

    results = scan_and_dispatch(
        args.openclaw_dir, args.tz_offset, holidays_by_region, today,
        dry_run=args.dry_run,
        agent_filter=agent_filter
    )

    output = {
        "status": "dispatched",
        "date": str(today),
        "holidays": holidays_by_region,
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
