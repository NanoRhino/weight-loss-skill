#!/usr/bin/env python3
"""
tips-optout.py — Opt out of product tips.

Usage:
  python3 tips-optout.py --data-dir <workspace>/data
"""

import argparse
import json
import os
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True)
    args = parser.parse_args()

    path = os.path.join(args.data_dir, "tips.json")
    state = {}
    if os.path.exists(path):
        try:
            with open(path) as f:
                state = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass

    state["opted_out"] = True
    os.makedirs(args.data_dir, exist_ok=True)
    with open(path, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

    print(json.dumps({"status": "opted_out", "message": "已关闭产品小贴士推送"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
