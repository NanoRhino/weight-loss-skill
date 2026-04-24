#!/usr/bin/env python3
"""
tips-check.py — Check if a product tip should be sent today.

Called by the tips cron job before sending. Outputs:
  SEND tip_id=N topic=<topic> prompt=<prompt>
  NO_REPLY reason=<reason>

Usage:
  python3 tips-check.py --data-dir <workspace>/data --tz-offset <seconds> \
    --onboarding-date YYYY-MM-DD [--mock-date YYYY-MM-DD]
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TIPS_FILE = os.path.join(SCRIPT_DIR, "..", "tips", "tip-topics.json")


def log(msg):
    print(f"[tips-check] {msg}", file=sys.stderr)


def get_today(tz_offset, mock_date=None):
    if mock_date:
        return datetime.strptime(mock_date, "%Y-%m-%d").date()
    tz = timezone(timedelta(seconds=tz_offset))
    return datetime.now(tz).date()


def load_tips():
    with open(TIPS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_tips_state(data_dir):
    path = os.path.join(data_dir, "tips.json")
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"next_tip": 1, "opted_out": False}


def save_tips_state(data_dir, state):
    path = os.path.join(data_dir, "tips.json")
    os.makedirs(data_dir, exist_ok=True)
    with open(path, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def check_leave(data_dir):
    leave_path = os.path.join(data_dir, "leave.json")
    if os.path.exists(leave_path):
        try:
            with open(leave_path) as f:
                data = json.load(f)
            return data.get("active", False)
        except (json.JSONDecodeError, IOError):
            pass
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--tz-offset", type=int, required=True)
    parser.add_argument("--onboarding-date", required=True, help="YYYY-MM-DD from health-profile.md")
    parser.add_argument("--mock-date", default=None)
    args = parser.parse_args()

    today = get_today(args.tz_offset, args.mock_date)

    # Check onboarding >= 24h (next day)
    try:
        onboarding = datetime.strptime(args.onboarding_date, "%Y-%m-%d").date()
    except ValueError:
        print("NO_REPLY reason=invalid_onboarding_date")
        return

    if today <= onboarding:
        log(f"Onboarding too recent: {onboarding}, today: {today}")
        print("NO_REPLY reason=onboarding_too_recent")
        return

    # Check leave
    if check_leave(args.data_dir):
        log("User on leave")
        print("NO_REPLY reason=on_leave")
        return

    # Load state
    state = load_tips_state(args.data_dir)

    if state.get("opted_out", False):
        log("User opted out")
        print("NO_REPLY reason=opted_out")
        return

    # Check if already sent today
    if state.get("last_sent") == str(today):
        log("Already sent today")
        print("NO_REPLY reason=already_sent")
        return

    # Load tips
    tips = load_tips()
    next_id = state.get("next_tip", 1)

    # Find next tip
    tip = None
    for t in tips:
        if t["id"] == next_id:
            tip = t
            break

    if not tip:
        log(f"No more tips (next_id={next_id}, total={len(tips)})")
        print("NO_REPLY reason=all_tips_sent")
        return

    # Advance state
    state["next_tip"] = next_id + 1
    state["last_sent"] = str(today)
    save_tips_state(args.data_dir, state)

    log(f"Sending tip {next_id}: {tip['topic']}")
    print(f"SEND tip_id={next_id} topic={tip['topic']}")
    # Print prompt on stderr for the cron message to pick up
    print(f"PROMPT:{tip['prompt']}", file=sys.stderr)


if __name__ == "__main__":
    main()
