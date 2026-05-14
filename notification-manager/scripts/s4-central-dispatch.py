#!/usr/bin/env python3
"""
s4-central-dispatch.py — Central dispatcher for Stage 4 (monthly) recall messages.

Instead of each S4 user's personal cron running daily and getting NO_REPLY,
this single script runs once daily (lunch slot), scans all user workspaces,
and outputs which users need a monthly recall message today.

Usage:
  python3 s4-central-dispatch.py --openclaw-dir /home/admin/.openclaw --tz-offset 28800

Output (stdout):
  JSON array of objects, each with:
    - workspace_dir: path to user workspace
    - session_key: the session key for message routing
    - stage: 4
    - days_silent: int
    - monthly_recall_count: int
    - last_recall_date: str or null

  If no users need recall today, outputs: []
"""

import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone


def log(msg):
    print(f"[s4-dispatch] {msg}", file=sys.stderr)


def scan_workspaces(openclaw_dir):
    """Find all user workspace directories."""
    pattern = os.path.join(openclaw_dir, "workspace-*")
    return sorted(glob.glob(pattern))


def load_engagement(workspace_dir):
    path = os.path.join(workspace_dir, "data", "engagement.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def extract_session_key(workspace_dir):
    """Extract session key from workspace directory name.
    
    workspace-wecom-dm-username -> wecom-dm-username
    workspace-wechat-dm-accXXX -> wechat-dm-accXXX
    """
    basename = os.path.basename(workspace_dir)
    if basename.startswith("workspace-"):
        return basename[len("workspace-"):]
    return basename


def needs_monthly_recall(engagement, tz_offset):
    """Check if this S4 user needs a recall message today."""
    stage = engagement.get("notification_stage", 1)
    if isinstance(stage, str):
        stage_map = {"active": 1, "pause": 2, "recall": 3, "silent": 4}
        stage = stage_map.get(stage.lower(), 1)
    
    if stage != 4:
        return False
    
    monthly_count = engagement.get("monthly_recall_count", 0)
    if monthly_count >= 3:
        return False  # All 3 monthly recalls sent, should be S5
    
    last_recall = engagement.get("last_recall_date", "")
    if not last_recall:
        return True  # Never sent a recall in this stage
    
    tz = timezone(timedelta(seconds=tz_offset))
    today = datetime.now(tz).date()
    
    try:
        last_date = datetime.strptime(last_recall, "%Y-%m-%d").date()
        days_since = (today - last_date).days
        return days_since >= 30
    except ValueError:
        return True  # Can't parse date, send anyway


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--openclaw-dir", default="/home/admin/.openclaw")
    parser.add_argument("--tz-offset", type=int, default=28800)
    args = parser.parse_args()

    workspaces = scan_workspaces(args.openclaw_dir)
    log(f"Found {len(workspaces)} user workspaces")

    results = []

    for ws in workspaces:
        eng = load_engagement(ws)
        if eng is None:
            continue

        if needs_monthly_recall(eng, args.tz_offset):
            session_key = extract_session_key(ws)
            results.append({
                "workspace_dir": ws,
                "session_key": session_key,
                "stage": 4,
                "days_silent": eng.get("days_silent", 0),
                "monthly_recall_count": eng.get("monthly_recall_count", 0),
                "last_recall_date": eng.get("last_recall_date"),
            })
            log(f"  → {session_key}: needs monthly recall (count={eng.get('monthly_recall_count', 0)})")

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
