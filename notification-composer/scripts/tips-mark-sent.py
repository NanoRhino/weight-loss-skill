#!/usr/bin/env python3
"""
tips-mark-sent.py — Mark a tip as sent (called AFTER successful delivery).

Usage:
  python3 tips-mark-sent.py --data-dir <workspace>/data --tip-id N --date YYYY-MM-DD
"""

import argparse
import json
import os
import subprocess
import sys


def _delete_tips_cron(data_dir):
    """Delete the 'Product tips' cron job after all tips are sent."""
    try:
        result = subprocess.run(
            ["openclaw", "cron", "list", "--json"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            print(f"[tips-mark-sent] cron list failed: {result.stderr.strip()}", file=sys.stderr)
            return
        data = json.loads(result.stdout)
        jobs = data.get("jobs", data) if isinstance(data, dict) else data
        # Find the Product tips cron for this agent's workspace
        for job in jobs:
            name = job.get("name", "") or job.get("label", "")
            payload = job.get("payload", {})
            message = payload.get("message", "") if isinstance(payload, dict) else ""
            if "Product tips" in name or "for tips" in message:
                job_id = job.get("id")
                if not job_id:
                    continue
                rm_result = subprocess.run(
                    ["openclaw", "cron", "rm", job_id],
                    capture_output=True, text=True, timeout=15
                )
                if rm_result.returncode == 0:
                    print(f"[tips-mark-sent] Deleted Product tips cron: {job_id}", file=sys.stderr)
                else:
                    print(f"[tips-mark-sent] Failed to delete cron {job_id}: {rm_result.stderr.strip()}", file=sys.stderr)
    except Exception as e:
        print(f"[tips-mark-sent] Error deleting tips cron: {e}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--tip-id", type=int, required=True)
    parser.add_argument("--date", required=True, help="Today's date YYYY-MM-DD")
    args = parser.parse_args()

    path = os.path.join(args.data_dir, "tips.json")
    state = {}
    if os.path.exists(path):
        try:
            with open(path) as f:
                state = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass

    state["next_tip"] = args.tip_id + 1
    state["last_sent"] = args.date

    os.makedirs(args.data_dir, exist_ok=True)
    with open(path, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

    print(f"[tips-mark-sent] tip {args.tip_id} marked as sent for {args.date}", file=sys.stderr)

    # Auto-delete the Product tips cron after the last tip is sent
    TOTAL_TIPS = 7
    if args.tip_id >= TOTAL_TIPS:
        _delete_tips_cron(args.data_dir)

    print(json.dumps({"status": "ok", "tip_id": args.tip_id, "date": args.date}, ensure_ascii=False))


if __name__ == "__main__":
    main()
