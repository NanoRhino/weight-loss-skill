#!/usr/bin/env python3
"""
check-feature-usage.py — Detect which features the user has already used
and track which feature tips have been sent.

Detection signals:
  - exercise_tracking:          data/exercise.json has ≥ 1 date entry
  - restaurant_recommendation:  data/nearby-restaurants.json has non-empty restaurants[]

Features that require memory/cron checks (packaged_food, custom_reminders,
emotional_support, nutrition_knowledge) cannot be reliably detected from
data files alone. The SKILL.md instructs the agent to supplement detection
via memory and cron checks at runtime.

Usage:
  # Check current state
  python3 check-feature-usage.py --workspace-dir <path>

  # Mark a tip as sent
  python3 check-feature-usage.py --workspace-dir <path> --mark-sent exercise_tracking

Output (stdout): JSON with used_features, sent_tips, and next_tip.
Exit code 0 always.
"""

import argparse
import json
import os
import sys

FEATURE_QUEUE = [
    "packaged_food",
    "restaurant_recommendation",
    "exercise_tracking",
    "custom_reminders",
    "emotional_support",
    "nutrition_knowledge",
]

TIPS_FILE = "data/feature-tips.json"

TIPS_DEFAULTS = {
    "sent_tips": [],
    "used_features": [],
}


def log(msg):
    """Log to stderr (not visible to user, only for debugging)."""
    print(f"[feature-tips] {msg}", file=sys.stderr)


def load_tips(workspace_dir):
    """Load feature-tips.json, creating defaults if missing."""
    path = os.path.join(workspace_dir, TIPS_FILE)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Ensure all keys exist
            for k, v in TIPS_DEFAULTS.items():
                if k not in data:
                    data[k] = v
            return data
        except (json.JSONDecodeError, IOError) as e:
            log(f"Warning: failed to read {path}: {e}. Using defaults.")
            return dict(TIPS_DEFAULTS)
    return dict(TIPS_DEFAULTS)


def save_tips(workspace_dir, data):
    """Write feature-tips.json."""
    path = os.path.join(workspace_dir, TIPS_FILE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log(f"Saved {path}")


def detect_exercise(workspace_dir):
    """Check if user has logged any exercise."""
    path = os.path.join(workspace_dir, "data", "exercise.json")
    if not os.path.exists(path):
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # exercise.json is keyed by date; any key means feature was used
        return len(data) > 0
    except (json.JSONDecodeError, IOError):
        return False


def detect_restaurant(workspace_dir):
    """Check if user has used restaurant recommendations."""
    path = os.path.join(workspace_dir, "data", "nearby-restaurants.json")
    if not os.path.exists(path):
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        restaurants = data.get("restaurants", [])
        return len(restaurants) > 0
    except (json.JSONDecodeError, IOError):
        return False


def detect_used_features(workspace_dir):
    """Detect features used from data files. Returns list of feature IDs."""
    used = []
    if detect_exercise(workspace_dir):
        used.append("exercise_tracking")
    if detect_restaurant(workspace_dir):
        used.append("restaurant_recommendation")
    return used


def find_next_tip(sent_tips, used_features):
    """Find next feature to introduce from the queue."""
    skip = set(sent_tips) | set(used_features)
    for feature_id in FEATURE_QUEUE:
        if feature_id not in skip:
            return feature_id
    return None


def main():
    parser = argparse.ArgumentParser(description="Feature tips usage checker")
    parser.add_argument("--workspace-dir", required=True, help="Workspace directory")
    parser.add_argument("--mark-sent", help="Mark a feature tip as sent")
    args = parser.parse_args()

    tips_data = load_tips(args.workspace_dir)

    if args.mark_sent:
        feature_id = args.mark_sent
        if feature_id not in tips_data["sent_tips"]:
            tips_data["sent_tips"].append(feature_id)
            log(f"Marked '{feature_id}' as sent")
        save_tips(args.workspace_dir, tips_data)

    # Detect usage from data files
    file_detected = detect_used_features(args.workspace_dir)

    # Merge file-detected features into persisted used_features
    for fid in file_detected:
        if fid not in tips_data["used_features"]:
            tips_data["used_features"].append(fid)

    # Save if we discovered new used features
    if file_detected:
        save_tips(args.workspace_dir, tips_data)

    # Find next tip (agent will further supplement used_features via memory/cron)
    next_tip = find_next_tip(tips_data["sent_tips"], tips_data["used_features"])

    result = {
        "used_features": tips_data["used_features"],
        "sent_tips": tips_data["sent_tips"],
        "next_tip": next_tip,
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
