#!/usr/bin/env python3
"""
first-meal-check.py — Detect whether the user has logged their FIRST meal ever.

Scans data/meals/*.json (all dates) and counts meal entries that contain real
food data (non-empty items/foods list — same rule as streak-calc.py and
notification-composer's pre-send-check.py `_any_meal_ever_logged`).

Run this in diet-tracking-analysis's Round 1 parallel batch, AFTER meal_checkin
has saved the current meal. Interpretation of the output:
  - total_food_meals == 1  → this IS the user's first meal ever (celebrate it)
  - total_food_meals  > 1  → not the first meal (say nothing special)
  - total_food_meals == 0  → meal_checkin hasn't persisted yet / no food logged

Single source of truth for the "first meal ever" signal so the in-the-moment
celebration and the next-day cron never both fire for the same milestone.

Usage:
  python3 first-meal-check.py --workspace-dir <path>

Exit code 0 always. Output is JSON on stdout.
"""

import argparse
import glob
import json
import os
import sys


def log(msg):
    print(f"[first-meal-check] {msg}", file=sys.stderr)


def _normalize_path(p):
    """Lowercase wechat-dm/wecom-dm segment to avoid case-mismatch directories."""
    import re as _re
    return _re.sub(
        r'(workspace-(?:wechat|wecom)-dm-)([^/]+)',
        lambda m: m.group(1) + m.group(2).lower(),
        p,
    )


def _meal_has_food(meal):
    """A meal entry counts as a real food log if it has a non-empty
    items/foods list. Mirror of streak-calc.py / pre-send-check.py."""
    if not isinstance(meal, dict):
        return False
    items = meal.get("items") or meal.get("foods")
    return bool(items)


def count_food_meals(workspace_dir):
    """Count meal entries with real food across all data/meals/*.json files."""
    meals_dir = os.path.join(workspace_dir, "data", "meals")
    if not os.path.isdir(meals_dir):
        return 0
    total = 0
    for fp in glob.glob(os.path.join(meals_dir, "*.json")):
        try:
            with open(fp) as f:
                meals = json.load(f)
        except (json.JSONDecodeError, IOError):
            continue
        if isinstance(meals, list):
            total += sum(1 for m in meals if _meal_has_food(m))
        elif isinstance(meals, dict):
            total += sum(1 for m in meals.values() if _meal_has_food(m))
    return total


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-dir", required=True)
    args = parser.parse_args()

    workspace_dir = _normalize_path(args.workspace_dir)
    total = count_food_meals(workspace_dir)

    print(json.dumps({
        "total_food_meals": total,
        "is_first_meal_ever": total == 1,
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
