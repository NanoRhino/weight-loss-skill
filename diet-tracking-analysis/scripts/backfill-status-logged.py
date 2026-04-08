#!/usr/bin/env python3
"""
backfill-status-logged.py — One-time script to add status: "logged" to all
existing meal records that have actual food data but no status field.

Usage:
  python3 backfill-status-logged.py --openclaw-dir /path/to/.openclaw [--dry-run]

Scans all workspace-wechat-dm-*/data/meals/*.json files.
"""

import argparse
import glob
import json
import os
import sys


def backfill_workspace(meals_dir, dry_run=False):
    """Backfill status: logged for all meal files in a directory."""
    files_updated = 0
    records_updated = 0

    for filepath in sorted(glob.glob(os.path.join(meals_dir, "*.json"))):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                meals = json.load(f)
        except (json.JSONDecodeError, IOError):
            continue

        if not isinstance(meals, list):
            continue

        changed = False
        for meal in meals:
            if not isinstance(meal, dict):
                continue
            # Has actual food data (items or foods) but no status
            has_food = meal.get("items") or meal.get("foods")
            if has_food and meal.get("status") != "logged":
                meal["status"] = "logged"
                changed = True
                records_updated += 1

        if changed:
            files_updated += 1
            if not dry_run:
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(meals, f, ensure_ascii=False, indent=2)

    return files_updated, records_updated


def main():
    parser = argparse.ArgumentParser(description="Backfill status: logged")
    parser.add_argument("--openclaw-dir", required=True, help="Path to .openclaw directory")
    parser.add_argument("--dry-run", action="store_true", help="Don't write, just report")
    args = parser.parse_args()

    total_files = 0
    total_records = 0
    total_users = 0

    for ws in sorted(glob.glob(os.path.join(args.openclaw_dir, "workspace-wechat-dm-*"))):
        meals_dir = os.path.join(ws, "data", "meals")
        if not os.path.isdir(meals_dir):
            continue

        user = os.path.basename(ws).replace("workspace-wechat-dm-", "")
        files, records = backfill_workspace(meals_dir, args.dry_run)

        if files > 0:
            total_users += 1
            total_files += files
            total_records += records
            print(f"  {user}: {files} files, {records} records")

    mode = "DRY RUN" if args.dry_run else "DONE"
    print(f"\n[{mode}] {total_users} users, {total_files} files, {total_records} records updated")


if __name__ == "__main__":
    main()
