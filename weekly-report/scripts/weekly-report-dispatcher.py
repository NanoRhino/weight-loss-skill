#!/usr/bin/env python3
"""
weekly-report-dispatcher.py — Scan all user workspaces and determine
which users should receive a weekly report this week.

Usage (called by main agent's cron, Sunday 20:30):
  python3 weekly-report-dispatcher.py \
    --openclaw-dir ~/.openclaw \
    --min-logged-days 2 \
    --tz-offset 28800

Output: JSON to stdout with list of eligible users and their cron job IDs.
The main agent then runs `openclaw cron run <job_id>` for each.

Registry file: weekly-report-crons.json (in skill dir or openclaw dir)
Maps agentId -> cronJobId for weekly report triggers.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone


def log(msg):
    print(f"[dispatcher] {msg}", file=sys.stderr)


def get_week_range(tz_offset):
    """Get this week's Monday-Sunday date range."""
    tz = timezone(timedelta(seconds=tz_offset))
    now = datetime.now(tz)
    # Find this week's Monday (report covers Mon-Sun of the PREVIOUS week)
    today = now.date()
    # Previous week: last Monday to last Sunday
    days_since_monday = today.weekday()  # 0=Mon, 6=Sun
    # If today is Sunday (6), we want THIS week (Mon-Sun ending today)
    # If today is any other day, we want LAST week
    if days_since_monday == 6:
        # Sunday: report for Mon-Sun ending today
        end = today
        start = today - timedelta(days=6)
    else:
        # Any other day: report for previous Mon-Sun
        last_sunday = today - timedelta(days=days_since_monday + 1)
        start = last_sunday - timedelta(days=6)
        end = last_sunday
    return start, end


def count_logged_days(meals_dir, start, end):
    """Count how many days in [start, end] have meal files with actual food data."""
    count = 0
    current = start
    while current <= end:
        date_str = current.strftime("%Y-%m-%d")
        meal_file = os.path.join(meals_dir, f"{date_str}.json")
        if os.path.exists(meal_file):
            try:
                with open(meal_file) as f:
                    raw = json.load(f)
                # Check if there's actual food data (not just empty/skip)
                has_food = False
                if isinstance(raw, list):
                    for meal in raw:
                        items = meal.get("items") or meal.get("foods") or []
                        if items:
                            has_food = True
                            break
                elif isinstance(raw, dict):
                    for key, val in raw.items():
                        if isinstance(val, dict):
                            items = val.get("items") or val.get("foods") or []
                            if items:
                                has_food = True
                                break
                if has_food:
                    count += 1
            except (json.JSONDecodeError, IOError):
                pass
        current += timedelta(days=1)
    return count


def get_engagement_stage(workspace_dir):
    """Read engagement.json and return current stage (default 1)."""
    eng_file = os.path.join(workspace_dir, "engagement.json")
    if not os.path.exists(eng_file):
        return 1
    try:
        with open(eng_file) as f:
            data = json.load(f)
        return data.get("stage", 1)
    except (json.JSONDecodeError, IOError):
        return 1


def load_cron_registry(registry_path):
    """Load agentId -> cronJobId mapping."""
    if not os.path.exists(registry_path):
        return {}
    try:
        with open(registry_path) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def scan_workspaces(openclaw_dir, min_logged_days, tz_offset):
    """Scan all user workspaces and return eligible users."""
    start, end = get_week_range(tz_offset)
    log(f"Report period: {start} to {end}")

    # Find all user workspace directories
    eligible = []
    skipped = []

    for entry in sorted(os.listdir(openclaw_dir)):
        # Match workspace-{channel}-dm-{userId}
        if not entry.startswith("workspace-") or "-dm-" not in entry:
            continue

        workspace_dir = os.path.join(openclaw_dir, entry)
        if not os.path.isdir(workspace_dir):
            continue

        # Extract agent ID: channel-dm-userId
        # workspace-wechat-dm-accx5l8ro → wechat-dm-accx5l8ro
        agent_id = entry.replace("workspace-", "")

        # Check health-profile exists (onboarded)
        if not os.path.exists(os.path.join(workspace_dir, "health-profile.md")):
            skipped.append({"agent_id": agent_id, "reason": "no health-profile"})
            continue

        # Check engagement stage (skip if in recall or silent)
        stage = get_engagement_stage(workspace_dir)
        if stage >= 2:
            skipped.append({"agent_id": agent_id, "reason": f"stage {stage} (recall/silent — suppressed)"})
            continue

        # Count logged days this week
        meals_dir = os.path.join(workspace_dir, "data", "meals")
        if not os.path.isdir(meals_dir):
            skipped.append({"agent_id": agent_id, "reason": "no meals dir"})
            continue

        logged = count_logged_days(meals_dir, start, end)
        if logged < min_logged_days:
            skipped.append({"agent_id": agent_id, "reason": f"logged {logged}/{min_logged_days} days"})
            continue

        eligible.append({
            "agent_id": agent_id,
            "workspace_dir": workspace_dir,
            "logged_days": logged,
            "stage": stage,
        })

    return eligible, skipped, start, end


def main():
    parser = argparse.ArgumentParser(description="Weekly report dispatcher")
    parser.add_argument("--openclaw-dir", required=True, help="Path to ~/.openclaw")
    parser.add_argument("--min-logged-days", type=int, default=2,
                        help="Minimum days with food data to qualify (default: 2)")
    parser.add_argument("--tz-offset", type=int, required=True, help="Timezone offset in seconds")
    parser.add_argument("--registry", default=None,
                        help="Path to weekly-report-crons.json (default: <openclaw-dir>/weekly-report-crons.json)")
    parser.add_argument("--dry-run", action="store_true", help="Don't output run commands")
    args = parser.parse_args()

    registry_path = args.registry or os.path.join(args.openclaw_dir, "weekly-report-crons.json")
    registry = load_cron_registry(registry_path)

    eligible, skipped, start, end = scan_workspaces(
        args.openclaw_dir, args.min_logged_days, args.tz_offset
    )

    # Match eligible users with their cron job IDs
    for user in eligible:
        user["cron_job_id"] = registry.get(user["agent_id"])
        if not user["cron_job_id"]:
            user["status"] = "no_cron_registered"
        else:
            user["status"] = "ready"

    output = {
        "report_period": {
            "start": start.strftime("%Y-%m-%d"),
            "end": end.strftime("%Y-%m-%d"),
        },
        "eligible": eligible,
        "skipped": skipped,
        "summary": {
            "total_workspaces": len(eligible) + len(skipped),
            "eligible_count": len(eligible),
            "skipped_count": len(skipped),
            "ready_count": sum(1 for u in eligible if u["status"] == "ready"),
            "no_cron_count": sum(1 for u in eligible if u["status"] == "no_cron_registered"),
        }
    }

    json.dump(output, sys.stdout, ensure_ascii=False, indent=2)
    print()


if __name__ == "__main__":
    main()
