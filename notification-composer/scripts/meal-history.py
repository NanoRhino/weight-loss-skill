#!/usr/bin/env python3
"""Meal history analysis for notification-composer skill.

Analyzes meal history for a given meal type over the last N days.
Returns top foods by frequency, average macros, recent meals, recommendations,
and same-weekday-last-week data for personalized reminders.

Usage:
  python3 meal-history.py --data-dir <meals_dir> --meal-type <type> \
    [--days 30] [--tz-offset <seconds>] [--schedule '{}']

Output: JSON to stdout.
"""

import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

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


def _migrate_meals(meals):
    return [_migrate_meal(m) for m in meals]


def get_log_path(data_dir, day):
    return os.path.join(data_dir, f"{day}.json")


def _get_recommendations_dir(data_dir):
    return os.path.join(os.path.dirname(data_dir), "recommendations")


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def meal_history(data_dir, meal_type, days=30, ref_date=None, tz_offset=None):
    """Analyze meal history for a given meal type over the last N days."""
    end = date.fromisoformat(ref_date) if ref_date else date.fromisoformat(_local_date(tz_offset))

    food_counts = {}  # name -> list of calorie values
    macro_sums = {"calories": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0}
    days_with_data = 0
    recent_3 = []

    for offset in range(days):
        day = (end - timedelta(days=offset)).isoformat()
        path = get_log_path(data_dir, day)
        if not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            all_meals = _migrate_meals(json.load(f))

        matched = [m for m in all_meals if m.get("meal_type") == meal_type
                   or m.get("name") == meal_type]
        if not matched:
            continue

        days_with_data += 1

        for m in matched:
            macro_sums["calories"] += m.get("calories", 0)
            macro_sums["protein"] += m.get("protein", 0)
            macro_sums["carbs"] += m.get("carbs", 0)
            macro_sums["fat"] += m.get("fat", 0)

            for food in m.get("foods", []):
                fname = food.get("name", "")
                if not fname:
                    continue
                fcal = food.get("calories", 0)
                food_counts.setdefault(fname, []).append(fcal)

        if len(recent_3) < 3:
            day_foods = []
            for m in matched:
                day_foods.extend(f.get("name", "") for f in m.get("foods", [])
                                 if f.get("name"))
            recent_3.append({"date": day, "foods": day_foods})

    # Top foods
    top_foods = sorted(food_counts.items(), key=lambda x: len(x[1]), reverse=True)[:10]
    top_foods_out = [
        {"name": name, "count": len(cals), "avg_calories": round(sum(cals) / len(cals), 1)}
        for name, cals in top_foods
    ]

    # Average macros
    avg_macros = {k: round(v / days_with_data, 1) if days_with_data else 0
                  for k, v in macro_sums.items()}

    # Data level
    if days_with_data >= 7:
        data_level = "rich"
    elif days_with_data >= 1:
        data_level = "limited"
    else:
        data_level = "none"

    # Recent recommendations
    rec_dir = _get_recommendations_dir(data_dir)
    recent_recs = []
    for offset in range(days):
        if len(recent_recs) >= 3:
            break
        day = (end - timedelta(days=offset)).isoformat()
        rec_path = os.path.join(rec_dir, f"{day}.json")
        if not os.path.exists(rec_path):
            continue
        with open(rec_path, "r", encoding="utf-8") as f:
            rec_data = json.load(f)
        if meal_type in rec_data:
            entry = rec_data[meal_type]
            recent_recs.append({
                "date": day,
                "items": entry.get("items", []),
                "picked": entry.get("picked"),
            })

    # Same weekday last week
    same_weekday_date = (end - timedelta(days=7)).isoformat()
    same_weekday_meal = None
    sw_path = get_log_path(data_dir, same_weekday_date)
    if os.path.exists(sw_path):
        with open(sw_path, "r", encoding="utf-8") as f:
            sw_meals = _migrate_meals(json.load(f))
        matched_sw = [m for m in sw_meals if m.get("meal_type") == meal_type
                      or m.get("name") == meal_type]
        if matched_sw:
            sw_foods = []
            sw_macros = {"calories": 0, "protein": 0, "carbs": 0, "fat": 0}
            for m in matched_sw:
                sw_foods.extend(f.get("name", "") for f in m.get("foods", [])
                                if f.get("name"))
                for k in sw_macros:
                    sw_macros[k] += m.get(k, 0)
            same_weekday_meal = {
                "date": same_weekday_date,
                "foods": sw_foods,
                "macros": sw_macros,
            }

    return {
        "meal_type": meal_type,
        "data_level": data_level,
        "days_with_data": days_with_data,
        "top_foods": top_foods_out,
        "avg_macros": avg_macros,
        "recent_3_days": recent_3,
        "recent_recommendations": recent_recs,
        "same_weekday_last_week": same_weekday_meal,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Meal history analysis")
    parser.add_argument("--data-dir", required=True, help="Path to meals data directory")
    parser.add_argument("--meal-type", required=True, help="Meal type to analyze")
    parser.add_argument("--days", type=int, default=30, help="Lookback days")
    parser.add_argument("--tz-offset", type=int, default=None, help="Timezone offset in seconds")
    parser.add_argument("--date", default=None, help="Reference date (YYYY-MM-DD)")
    args = parser.parse_args()

    result = meal_history(
        data_dir=_normalize_path(args.data_dir),
        meal_type=args.meal_type,
        days=args.days,
        ref_date=args.date,
        tz_offset=args.tz_offset,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
