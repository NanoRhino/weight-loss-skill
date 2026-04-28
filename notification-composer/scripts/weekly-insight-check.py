#!/usr/bin/env python3
"""
weekly-insight-check.py — Check if a weekly personalized insight should be sent.

Runs once a week (e.g. Thursday 21:00). Sends a coach-style observation
based on user's recent meals and conversations.

Starts after all one-time tips (1-7) are finished.

Output:
  SEND  → agent should generate and send insight
  NO_REPLY reason=<reason>

Usage:
  python3 weekly-insight-check.py --data-dir <workspace>/data --tz-offset <seconds> \
    --onboarding-date YYYY-MM-DD [--mock-date YYYY-MM-DD]
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone


def log(msg):
    print(f"[weekly-insight] {msg}", file=sys.stderr)


def get_today(tz_offset, mock_date=None):
    if mock_date:
        return datetime.strptime(mock_date, "%Y-%m-%d").date()
    tz = timezone(timedelta(seconds=tz_offset))
    return datetime.now(tz).date()


def load_json(path):
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--tz-offset", type=int, required=True)
    parser.add_argument("--onboarding-date", required=True)
    parser.add_argument("--mock-date", default=None)
    args = parser.parse_args()

    today = get_today(args.tz_offset, args.mock_date)

    # Check onboarding date valid
    try:
        onboarding = datetime.strptime(args.onboarding_date, "%Y-%m-%d").date()
    except ValueError:
        print("NO_REPLY reason=invalid_onboarding_date")
        return

    # Must be at least 7 days after onboarding
    days_since = (today - onboarding).days
    if days_since < 7:
        log(f"Too early: {days_since} days since onboarding")
        print("NO_REPLY reason=too_early")
        return

    # Check leave
    leave_data = load_json(os.path.join(args.data_dir, "leave.json"))
    if leave_data.get("active"):
        log("User on leave")
        print("NO_REPLY reason=on_leave")
        return

    # All one-time tips must be finished before weekly insights start
    tips_data = load_json(os.path.join(args.data_dir, "tips.json"))

    if tips_data.get("opted_out"):
        log("User opted out")
        print("NO_REPLY reason=opted_out")
        return

    # tip-topics.json has 7 tips; next_tip > 7 means all sent
    next_tip = tips_data.get("next_tip", 1)
    if next_tip <= 7:
        log(f"Tips not finished yet (next_tip={next_tip})")
        print("NO_REPLY reason=tips_not_finished")
        return

    # Check if already sent this week
    insight_data = load_json(os.path.join(args.data_dir, "weekly-insight.json"))
    last_sent = insight_data.get("last_sent")
    if last_sent:
        try:
            last_date = datetime.strptime(last_sent, "%Y-%m-%d").date()
            if (today - last_date).days < 6:
                log(f"Sent recently: {last_sent}")
                print("NO_REPLY reason=sent_recently")
                return
        except ValueError:
            pass

    # Do NOT advance state here — agent calls weekly-insight-mark-sent.py
    # after confirming delivery.
    log("Weekly insight ready to send")
    print("SEND")


if __name__ == "__main__":
    main()
