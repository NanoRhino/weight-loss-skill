#!/usr/bin/env python3
"""Load meal records for a given date.

Usage:
  python3 load-meals.py --data-dir <meals_dir> [--date YYYY-MM-DD] [--tz-offset <seconds>]

Output: JSON to stdout.
"""

import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone


_SHORT_TO_LONG = {
    "cal": "calories", "p": "protein", "c": "carbs", "f": "fat",
    "protein_g": "protein", "carbs_g": "carbs", "fat_g": "fat",
}


def _normalize_path(p):
    return re.sub(r'(workspace-(?:wechat|wecom)-dm-)([^/]+)',
                  lambda m: m.group(1) + m.group(2).lower(), p)


def _local_date(tz_offset=None):
    if tz_offset is not None:
        utc_now = datetime.now(timezone.utc)
        local_dt = utc_now + timedelta(seconds=tz_offset)
        return local_dt.date().isoformat()
    return date.today().isoformat()


def _migrate_meal(meal):
    out = {}
    for k, v in meal.items():
        new_key = _SHORT_TO_LONG.get(k, k)
        if new_key in out:
            continue
        if k == "foods" and isinstance(v, list):
            out[k] = [_migrate_meal(f) for f in v]
        else:
            out[new_key] = v
    if "items" in out and "foods" not in out:
        out["foods"] = [_migrate_meal(f) for f in out.pop("items")]
    if "foods" in out and "calories" not in out:
        for key in ("calories", "protein", "carbs", "fat"):
            out[key] = round(sum(f.get(key, 0) for f in out["foods"]), 1)
    return out


def load_meals(data_dir, day):
    path = os.path.join(data_dir, f"{day}.json")
    if not os.path.exists(path):
        return {"date": day, "meals": [], "meals_count": 0}
    with open(path, "r", encoding="utf-8") as f:
        meals = json.load(f)
    meals = [_migrate_meal(m) for m in meals]
    return {"date": day, "meals": meals, "meals_count": len(meals)}


def main():
    parser = argparse.ArgumentParser(description="Load meal records for a date")
    parser.add_argument("--data-dir", required=True, help="Path to meals data directory")
    parser.add_argument("--date", default=None, help="Date (YYYY-MM-DD), default today")
    parser.add_argument("--tz-offset", type=int, default=None, help="Timezone offset in seconds")
    args = parser.parse_args()

    data_dir = _normalize_path(args.data_dir)
    day = args.date or _local_date(args.tz_offset)
    result = load_meals(data_dir, day)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
