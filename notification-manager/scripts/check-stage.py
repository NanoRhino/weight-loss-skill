#!/usr/bin/env python3
"""
check-stage.py — Update engagement stage based on user silence duration.

Reads data/engagement.json, calculates days since last_interaction,
and transitions notification_stage according to lifecycle rules:

  Stage 1 (ACTIVE)  → 5 full calendar days silent → Stage 2 (PAUSE)
  Stage 2 (PAUSE)   → 3 days after stage change   → Stage 3 (SECOND RECALL)
  Stage 3 (RECALL)  → 1 day after stage change     → Stage 4 (SILENT)

When a silent user returns (last_interaction is recent but stage > 1),
resets to Stage 1.

Usage:
  python3 check-stage.py --workspace-dir <path> --tz-offset <seconds>

Output (stdout): current stage number (1-4)
Transitions are logged to stderr.

Exit code 0 always.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta


def log(msg):
    """Log to stderr (not visible to user, only for debugging)."""
    print(f"[check-stage] {msg}", file=sys.stderr)


# Transition thresholds (in days)
STAGE_1_TO_2_DAYS = 3   # 3 full calendar days silent → pause + first recall
STAGE_2_TO_3_DAYS = 3   # 3 days of recall messages (Day 4-6) → second recall
STAGE_3_TO_4_DAYS = 1   # 1 day after second recall → silent

ENGAGEMENT_DEFAULTS = {
    "notification_stage": 1,
    "last_interaction": None,
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
        # Merge with defaults for any missing keys
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
    f.close()


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


def main():
    parser = argparse.ArgumentParser(
        description="Update engagement stage based on user silence duration"
    )
    parser.add_argument("--workspace-dir", required=True, help="Agent workspace root")
    parser.add_argument("--tz-offset", required=True, type=int,
                        help="Timezone offset in seconds from UTC")
    args = parser.parse_args()

    data, existed = load_engagement(args.workspace_dir)
    now = datetime.now(timezone.utc)

    stage = normalize_stage(data.get("notification_stage", 1))
    last_interaction = parse_iso(data.get("last_interaction"))
    stage_changed_at = parse_iso(data.get("stage_changed_at"))

    # If no last_interaction recorded, initialize and exit
    if last_interaction is None:
        if not existed:
            data["last_interaction"] = now.isoformat()
            data["stage_changed_at"] = now.isoformat()
            save_engagement(args.workspace_dir, data)
            log("Initialized engagement.json with stage 1")
        print(stage)
        return

    old_stage = stage
    days_silent = (now - last_interaction).total_seconds() / 86400
    changed = False

    # --- User returned: last_interaction is recent but stage > 1 ---
    if stage > 1 and days_silent < 1:
        stage = 1
        data["notification_stage"] = 1
        data["stage_changed_at"] = now.isoformat()
        data["last_recall_date"] = None
        data["recall_2_sent"] = False
        changed = True
        log(f"RESET to stage 1 (user returned, silent only {days_silent:.1f} days)")

    # --- Forward transitions based on silence duration ---
    elif stage == 1:
        if days_silent >= STAGE_1_TO_2_DAYS:
            stage = 2
            data["notification_stage"] = 2
            data["stage_changed_at"] = now.isoformat()
            data["last_recall_date"] = None
            data["recall_2_sent"] = False
            changed = True
            log(f"TRANSITION 1 → 2 (silent {days_silent:.1f} days)")

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
                changed = True
                log(f"TRANSITION 3 → 4 (in stage 3 for {days_in_stage:.1f} days)")

    if changed or not existed:
        save_engagement(args.workspace_dir, data)

    print(stage)


if __name__ == "__main__":
    main()
