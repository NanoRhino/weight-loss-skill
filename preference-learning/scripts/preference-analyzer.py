# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
Preference analyzer for preference-learning skill.

Aggregates meal logs, weight records, and timing data to surface implicit
user preferences and behavioral patterns. The agent interprets the output
and decides what qualifies as a real preference.

Commands:
  food-patterns      — Analyze food frequency, categories, and portion patterns.
  timing-patterns    — Analyze meal timing, skipping, and weigh-in patterns.
  behavior-patterns  — Analyze logging compliance, weekday trends, engagement.

Usage:
  python3 preference-analyzer.py food-patterns \
      --data-dir /path/to/meals --days 14 --tz-offset 28800
  python3 preference-analyzer.py timing-patterns \
      --data-dir /path/to/meals --weight-file /path/to/weight.json \
      --days 14 --tz-offset 28800
  python3 preference-analyzer.py behavior-patterns \
      --data-dir /path/to/meals --weight-file /path/to/weight.json \
      --days 28 --tz-offset 28800
"""

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Backward compatibility: migrate old short field names to full names
_SHORT_TO_LONG = {"cal": "calories", "p": "protein", "c": "carbs", "f": "fat"}


def _migrate_meal(meal: dict) -> dict:
    """Convert old short-key meal dicts to full-name keys."""
    out = {}
    for k, v in meal.items():
        new_key = _SHORT_TO_LONG.get(k, k)
        if new_key in out:
            continue
        if k == "foods" and isinstance(v, list):
            out[k] = [_migrate_meal(f) for f in v]
        else:
            out[new_key] = v
    return out


def _local_date(tz_offset: int | None = None) -> date:
    """Return user's local date."""
    if tz_offset is not None:
        utc_now = datetime.now(timezone.utc)
        local_dt = utc_now + timedelta(seconds=tz_offset)
        return local_dt.date()
    return date.today()


def _date_range(end_date: date, days: int) -> list[date]:
    """Return a list of dates from (end_date - days + 1) to end_date inclusive."""
    return [end_date - timedelta(days=i) for i in range(days - 1, -1, -1)]


def _load_day(data_dir: str, d: date) -> list[dict]:
    """Load meals for a single date. Returns empty list if no file."""
    path = os.path.join(data_dir, f"{d.isoformat()}.json")
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            meals = json.load(f)
        return [_migrate_meal(m) for m in meals]
    except (json.JSONDecodeError, OSError):
        return []


def _load_weight(weight_file: str) -> dict:
    """Load weight.json. Returns dict of datetime_str -> {value, unit}."""
    if not weight_file or not os.path.isfile(weight_file):
        return {}
    try:
        with open(weight_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _is_weekend(d: date) -> bool:
    return d.weekday() >= 5  # Saturday=5, Sunday=6


def _weekday_name(d: date) -> str:
    return ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][d.weekday()]


def _meal_slot(name: str) -> str:
    """Normalize meal name to a standard slot."""
    n = name.lower().strip()
    if "breakfast" in n or n in ("早餐", "早饭"):
        return "breakfast"
    if "lunch" in n or n in ("午餐", "午饭"):
        return "lunch"
    if "dinner" in n or "supper" in n or n in ("晚餐", "晚饭"):
        return "dinner"
    if "snack" in n or n in ("加餐", "零食"):
        return "snack"
    return n


# ---------------------------------------------------------------------------
# Command: food-patterns
# ---------------------------------------------------------------------------

def cmd_food_patterns(args):
    today = _local_date(args.tz_offset)
    dates = _date_range(today, args.days)

    # Collect data
    food_counter_by_meal = defaultdict(Counter)  # meal_slot -> Counter({food_name: count})
    meal_calories = defaultdict(list)  # meal_slot -> [calories]
    snack_days = 0
    total_days_with_data = 0
    all_food_names = []

    for d in dates:
        meals = _load_day(args.data_dir, d)
        if not meals:
            continue
        total_days_with_data += 1
        has_snack = False

        for meal in meals:
            slot = _meal_slot(meal.get("name", ""))
            cal = meal.get("calories", 0)
            if cal > 0:
                meal_calories[slot].append(cal)

            if "snack" in slot:
                has_snack = True

            foods = meal.get("foods", [])
            for food in foods:
                fname = food.get("name", "").strip()
                if fname:
                    food_counter_by_meal[slot][fname] += 1
                    all_food_names.append(fname)

        if has_snack:
            snack_days += 1

    # Build top foods per meal slot
    top_foods_by_meal = {}
    for slot, counter in food_counter_by_meal.items():
        top = counter.most_common(10)
        top_foods_by_meal[slot] = [
            {"name": name, "count": count,
             "pct": round(count / total_days_with_data * 100) if total_days_with_data > 0 else 0}
            for name, count in top
        ]

    # Meal calorie averages
    meal_calorie_averages = {}
    for slot, cals in meal_calories.items():
        if cals:
            meal_calorie_averages[slot] = {
                "avg": round(sum(cals) / len(cals)),
                "min": min(cals),
                "max": max(cals),
                "count": len(cals),
            }

    # Snack frequency (per week)
    weeks = args.days / 7
    snack_frequency = round(snack_days / weeks, 1) if weeks > 0 else 0

    # Overall top foods
    overall_top = Counter(all_food_names).most_common(15)

    result = {
        "period": {"from": dates[0].isoformat(), "to": dates[-1].isoformat()},
        "days_with_data": total_days_with_data,
        "days_analyzed": args.days,
        "top_foods_by_meal": top_foods_by_meal,
        "overall_top_foods": [{"name": n, "count": c} for n, c in overall_top],
        "meal_calorie_averages": meal_calorie_averages,
        "snack_frequency_per_week": snack_frequency,
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# Command: timing-patterns
# ---------------------------------------------------------------------------

def cmd_timing_patterns(args):
    today = _local_date(args.tz_offset)
    dates = _date_range(today, args.days)

    weekday_cals = []
    weekend_cals = []
    skipped = defaultdict(lambda: {"total": 0, "skipped": 0, "weekday_skipped": 0, "weekend_skipped": 0})
    meal_slots_seen = set()

    for d in dates:
        meals = _load_day(args.data_dir, d)
        if not meals:
            continue

        day_cal = sum(m.get("calories", 0) for m in meals)
        if _is_weekend(d):
            weekend_cals.append(day_cal)
        else:
            weekday_cals.append(day_cal)

        # Track which slots were logged
        logged_slots = set()
        for meal in meals:
            slot = _meal_slot(meal.get("name", ""))
            if slot != "snack":
                logged_slots.add(slot)
                meal_slots_seen.add(slot)

        # Check skipped meals (only for known slots)
        for slot in meal_slots_seen:
            skipped[slot]["total"] += 1
            if slot not in logged_slots:
                skipped[slot]["skipped"] += 1
                if _is_weekend(d):
                    skipped[slot]["weekend_skipped"] += 1
                else:
                    skipped[slot]["weekday_skipped"] += 1

    # Weekday vs weekend calorie comparison
    weekday_avg = round(sum(weekday_cals) / len(weekday_cals)) if weekday_cals else None
    weekend_avg = round(sum(weekend_cals) / len(weekend_cals)) if weekend_cals else None
    cal_diff = None
    cal_diff_pct = None
    if weekday_avg and weekend_avg and weekday_avg > 0:
        cal_diff = weekend_avg - weekday_avg
        cal_diff_pct = round(cal_diff / weekday_avg * 100, 1)

    # Skipped meals summary
    skipped_meals = {}
    for slot, data in skipped.items():
        if data["total"] > 0:
            skip_rate = round(data["skipped"] / data["total"], 2)
            weekday_total = data["total"] - (len(weekend_cals))  # approximate
            weekday_skip_rate = None
            if data["skipped"] > 0:
                # Check if skipping is weekday-only
                weekday_only = (data["weekend_skipped"] == 0 and data["weekday_skipped"] > 0)
            else:
                weekday_only = False
            skipped_meals[slot] = {
                "skip_rate": skip_rate,
                "skipped_count": data["skipped"],
                "total_days": data["total"],
                "weekday_only": weekday_only,
            }

    # Weight timing patterns
    weighin_times = []
    weight_data = _load_weight(args.weight_file)
    for dt_str in weight_data:
        try:
            dt = datetime.fromisoformat(dt_str)
            hour = dt.hour + dt.minute / 60
            weighin_times.append(round(hour, 1))
        except (ValueError, TypeError):
            continue

    weighin_pattern = None
    if weighin_times:
        avg_time = sum(weighin_times) / len(weighin_times)
        morning_count = sum(1 for t in weighin_times if t < 12)
        evening_count = sum(1 for t in weighin_times if t >= 18)
        if morning_count > len(weighin_times) * 0.6:
            weighin_pattern = "morning"
        elif evening_count > len(weighin_times) * 0.6:
            weighin_pattern = "evening"
        else:
            weighin_pattern = "mixed"
        weighin_pattern = {
            "pattern": weighin_pattern,
            "avg_hour": round(avg_time, 1),
            "total_entries": len(weighin_times),
            "morning_pct": round(morning_count / len(weighin_times) * 100),
        }

    result = {
        "period": {"from": dates[0].isoformat(), "to": dates[-1].isoformat()},
        "days_analyzed": args.days,
        "weekday_avg_cal": weekday_avg,
        "weekend_avg_cal": weekend_avg,
        "weekend_vs_weekday_diff": cal_diff,
        "weekend_vs_weekday_diff_pct": cal_diff_pct,
        "skipped_meals": skipped_meals,
        "weighin_pattern": weighin_pattern,
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# Command: behavior-patterns
# ---------------------------------------------------------------------------

def cmd_behavior_patterns(args):
    today = _local_date(args.tz_offset)
    dates = _date_range(today, args.days)

    # Daily logging rates
    weekday_logging = defaultdict(lambda: {"logged": 0, "total": 0})
    daily_cals = {}  # date -> total calories
    logged_dates = []

    for d in dates:
        meals = _load_day(args.data_dir, d)
        wday = _weekday_name(d)
        weekday_logging[wday]["total"] += 1

        if meals:
            weekday_logging[wday]["logged"] += 1
            logged_dates.append(d)
            daily_cals[d.isoformat()] = sum(m.get("calories", 0) for m in meals)

    # Logging rate by weekday
    logging_rate_by_weekday = {}
    for wday in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]:
        data = weekday_logging[wday]
        if data["total"] > 0:
            logging_rate_by_weekday[wday] = round(data["logged"] / data["total"], 2)
        else:
            logging_rate_by_weekday[wday] = None

    # Overall logging rate
    total_days = len(dates)
    logged_days = len(logged_dates)
    overall_logging_rate = round(logged_days / total_days, 2) if total_days > 0 else 0

    # Engagement trend (compare first half vs second half)
    mid = args.days // 2
    first_half_dates = dates[:mid]
    second_half_dates = dates[mid:]
    first_half_logged = sum(1 for d in first_half_dates if d in logged_dates)
    second_half_logged = sum(1 for d in second_half_dates if d in logged_dates)
    first_rate = first_half_logged / len(first_half_dates) if first_half_dates else 0
    second_rate = second_half_logged / len(second_half_dates) if second_half_dates else 0

    if second_rate > first_rate + 0.15:
        engagement_trend = "increasing"
    elif second_rate < first_rate - 0.15:
        engagement_trend = "decreasing"
    else:
        engagement_trend = "stable"

    # Post-over-target pattern: after a high-calorie day, does the user compensate?
    # Load plan targets if available (passed via args or inferred)
    sorted_dates = sorted(daily_cals.keys())
    post_over_pattern = None
    if len(sorted_dates) >= 3:
        cal_values = [daily_cals[d] for d in sorted_dates]
        avg_cal = sum(cal_values) / len(cal_values) if cal_values else 0
        over_threshold = avg_cal * 1.15  # 15% over average

        over_days = []
        compensate_count = 0
        for i, d in enumerate(sorted_dates):
            if daily_cals[d] > over_threshold:
                over_days.append(d)
                # Check next day
                if i + 1 < len(sorted_dates):
                    next_d = sorted_dates[i + 1]
                    if daily_cals[next_d] < avg_cal * 0.9:
                        compensate_count += 1

        if over_days:
            post_over_pattern = {
                "over_target_days": len(over_days),
                "compensated_next_day": compensate_count,
                "compensation_rate": round(compensate_count / len(over_days), 2) if over_days else 0,
            }

    # Weekly compliance vs weight change correlation
    weight_data = _load_weight(args.weight_file)
    weekly_correlation = None
    if weight_data and len(logged_dates) >= 7:
        # Group by week
        week_data = defaultdict(lambda: {"logged_days": 0, "total_days": 0})
        weight_by_week = defaultdict(list)

        for d in dates:
            week_num = d.isocalendar()[1]
            week_data[week_num]["total_days"] += 1
            if d in logged_dates:
                week_data[week_num]["logged_days"] += 1

        for dt_str, entry in weight_data.items():
            try:
                dt = datetime.fromisoformat(dt_str)
                wk = dt.date().isocalendar()[1]
                weight_by_week[wk].append(entry.get("value", 0))
            except (ValueError, TypeError):
                continue

        # Compare weeks with high vs low logging to weight changes
        weeks_with_both = []
        for wk in sorted(week_data.keys()):
            if wk in weight_by_week and week_data[wk]["total_days"] >= 5:
                rate = week_data[wk]["logged_days"] / week_data[wk]["total_days"]
                w_values = weight_by_week[wk]
                if len(w_values) >= 1:
                    weeks_with_both.append({
                        "week": wk,
                        "logging_rate": round(rate, 2),
                        "avg_weight": round(sum(w_values) / len(w_values), 1),
                    })

        if len(weeks_with_both) >= 2:
            weekly_correlation = weeks_with_both

    # Low-compliance weekdays
    low_compliance_days = [
        wday for wday, rate in logging_rate_by_weekday.items()
        if rate is not None and rate < 0.5
    ]

    result = {
        "period": {"from": dates[0].isoformat(), "to": dates[-1].isoformat()},
        "days_analyzed": args.days,
        "days_with_data": logged_days,
        "overall_logging_rate": overall_logging_rate,
        "logging_rate_by_weekday": logging_rate_by_weekday,
        "low_compliance_days": low_compliance_days,
        "engagement_trend": engagement_trend,
        "engagement_detail": {
            "first_half_rate": round(first_rate, 2),
            "second_half_rate": round(second_rate, 2),
        },
        "post_over_pattern": post_over_pattern,
        "weekly_correlation": weekly_correlation,
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Preference analyzer — surfaces implicit user preferences from daily records."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # food-patterns
    fp = sub.add_parser("food-patterns", help="Analyze food frequency and portion patterns.")
    fp.add_argument("--data-dir", required=True, help="Path to meals data directory")
    fp.add_argument("--days", type=int, default=14, help="Number of days to analyze (default 14)")
    fp.add_argument("--tz-offset", type=int, default=None, help="Timezone offset in seconds from UTC")

    # timing-patterns
    tp = sub.add_parser("timing-patterns", help="Analyze meal timing and weigh-in patterns.")
    tp.add_argument("--data-dir", required=True, help="Path to meals data directory")
    tp.add_argument("--weight-file", default=None, help="Path to weight.json")
    tp.add_argument("--days", type=int, default=14, help="Number of days to analyze (default 14)")
    tp.add_argument("--tz-offset", type=int, default=None, help="Timezone offset in seconds from UTC")

    # behavior-patterns
    bp = sub.add_parser("behavior-patterns", help="Analyze logging compliance and engagement.")
    bp.add_argument("--data-dir", required=True, help="Path to meals data directory")
    bp.add_argument("--weight-file", default=None, help="Path to weight.json")
    bp.add_argument("--days", type=int, default=28, help="Number of days to analyze (default 28)")
    bp.add_argument("--tz-offset", type=int, default=None, help="Timezone offset in seconds from UTC")

    args = parser.parse_args()

    if args.command == "food-patterns":
        cmd_food_patterns(args)
    elif args.command == "timing-patterns":
        cmd_timing_patterns(args)
    elif args.command == "behavior-patterns":
        cmd_behavior_patterns(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
