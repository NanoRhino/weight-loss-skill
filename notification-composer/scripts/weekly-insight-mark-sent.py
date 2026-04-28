#!/usr/bin/env python3
"""
weekly-insight-mark-sent.py — Mark weekly insight as sent (called AFTER delivery).

Usage:
  python3 weekly-insight-mark-sent.py --data-dir <workspace>/data --date YYYY-MM-DD
"""

import argparse
import json
import os
import sys


def load_json(path):
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--date", required=True, help="Today's date YYYY-MM-DD")
    args = parser.parse_args()

    path = os.path.join(args.data_dir, "weekly-insight.json")
    data = load_json(path)

    data["last_sent"] = args.date
    data["send_count"] = data.get("send_count", 0) + 1

    os.makedirs(args.data_dir, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"[weekly-insight-mark-sent] marked sent for {args.date}", file=sys.stderr)
    print(json.dumps({"status": "ok", "date": args.date, "send_count": data["send_count"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
