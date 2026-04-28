#!/usr/bin/env python3
"""
tips-mark-sent.py — Mark a tip as sent (called AFTER successful delivery).

Usage:
  python3 tips-mark-sent.py --data-dir <workspace>/data --tip-id N --date YYYY-MM-DD
"""

import argparse
import json
import os
import sys


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
    print(json.dumps({"status": "ok", "tip_id": args.tip_id, "date": args.date}, ensure_ascii=False))


if __name__ == "__main__":
    main()
