#!/usr/bin/env python3
"""
badge-calc.py — Calorie target badge calculator.

Usage:
    python3 badge-calc.py check --workspace-dir <path> --tz-offset <minutes>

Checks if today qualifies as a calorie-target day, updates badges.json,
and outputs JSON result indicating current status and any level-up.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


# Badge level definitions
LEVELS = [
    {"level": 1, "days": 3, "name": "⭐ 稳稳吃饭的人",
     "message": "有3天热量刚好落在目标区间。这不是运气——是你对\"一顿饭多少热量\"有感觉了。"},
    {"level": 2, "days": 7, "name": "⭐⭐ 热量掌控达人",
     "message": "7天达标。你已经知道什么时候该多吃、什么时候该收着。这种判断力比任何食谱都管用。"},
    {"level": 3, "days": 14, "name": "⭐⭐⭐ 自由支配者",
     "message": "两周的精准分配。你不是在\"控制饮食\"，你是真的会吃了。"},
    {"level": 4, "days": 21, "name": "⭐⭐⭐⭐ 稳定输出选手",
     "message": "三周的节奏，已经不是\"在坚持\"了，是你的正常状态。"},
    {"level": 5, "days": 30, "name": "⭐⭐⭐⭐⭐ 精准生活家",
     "message": "一个月。你对热量的直觉已经内化了——不看数字也不会差太远。"},
    {"level": 6, "days": 45, "name": "⭐×6 持续进化者",
     "message": "45天。一个半月的稳定输出，这不是阶段性的表现，是你的新常态。"},
    {"level": 7, "days": 60, "name": "⭐×7 长期主义玩家",
     "message": "60天。不需要鸡汤，数据说明一切。"},
    {"level": 8, "days": 90, "name": "⭐×8 不可撼动",
     "message": "90天。多数人的计划活不过两周，你走完了全程。这不是关于减肥了，这是你证明了自己能长期做好一件事。"},
]

MILK_TEA_KCAL = 500  # One standard full-sugar milk tea


def get_local_date(tz_offset_minutes: int) -> str:
    """Get today's date string in user's local timezone."""
    tz = timezone(timedelta(minutes=tz_offset_minutes))
    return datetime.now(tz).strftime("%Y-%m-%d")


def parse_plan(workspace_dir: str) -> dict:
    """Parse PLAN.md for calorie target, BMR, deficit, and meal count."""
    plan_path = Path(workspace_dir) / "PLAN.md"
    result = {
        "calorie_target": None,
        "bmr": None,
        "daily_deficit": 300,  # default
        "expected_meals": 3,   # default
    }

    if not plan_path.exists():
        return result

    content = plan_path.read_text(encoding="utf-8")

    # Parse Daily Calorie Range (e.g., "Daily Calorie Range: 1200-1400" or "1,200 ~ 1,400")
    range_patterns = [
        r"Daily Calorie Range[:\s]*(\d[,\d]*)\s*[-~]\s*(\d[,\d]*)",
        r"每日热量[目范]?[标围]?[:\s：]*(\d[,\d]*)\s*[-~]\s*(\d[,\d]*)",
        r"Daily Calories?[:\s]*~?(\d[,\d]*)",
        r"每日热量目标[:\s：]*(\d[,\d]*)",
        r"Daily Calorie Budget[:\s]*(\d[,\d]*)",
    ]

    for pattern in range_patterns:
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            groups = match.groups()
            if len(groups) == 2:
                low = int(groups[0].replace(",", ""))
                high = int(groups[1].replace(",", ""))
                result["calorie_target"] = (low + high) // 2
            else:
                val = int(groups[0].replace(",", ""))
                if 800 <= val <= 3000:
                    result["calorie_target"] = val
            break

    # Parse BMR
    bmr_match = re.search(r"BMR[:\s]*(\d[,\d]*)", content, re.IGNORECASE)
    if bmr_match:
        result["bmr"] = int(bmr_match.group(1).replace(",", ""))

    # Parse daily deficit
    deficit_patterns = [
        r"Daily (?:Calorie )?Deficit[:\s]*~?(\d[,\d]*)",
        r"每日[热量]*缺口[:\s：]*~?(\d[,\d]*)",
    ]
    for pattern in deficit_patterns:
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            result["daily_deficit"] = int(match.group(1).replace(",", ""))
            break

    # Check for intermittent fasting / 2-meal pattern
    if re.search(r"(16[:/]8|间歇断食|intermittent fasting|两餐|2\s*餐)", content, re.IGNORECASE):
        result["expected_meals"] = 2

    return result


def parse_health_profile(workspace_dir: str) -> dict:
    """Fallback: parse health-profile.md for BMR if not in PLAN.md."""
    hp_path = Path(workspace_dir) / "health-profile.md"
    result = {"bmr": None}

    if not hp_path.exists():
        return result

    content = hp_path.read_text(encoding="utf-8")
    bmr_match = re.search(r"BMR[:\s]*(\d[,\d]*)", content, re.IGNORECASE)
    if bmr_match:
        result["bmr"] = int(bmr_match.group(1).replace(",", ""))

    return result


def load_today_meals(workspace_dir: str, today: str) -> dict:
    """Load today's meal data and return meal count + total calories."""
    meals_path = Path(workspace_dir) / "data" / "meals" / f"{today}.json"
    result = {"main_meal_count": 0, "total_calories": 0}

    if not meals_path.exists():
        return result

    try:
        data = json.loads(meals_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return result

    # Handle both list format and dict format
    meals = []
    if isinstance(data, list):
        meals = data
    elif isinstance(data, dict):
        # Could be keyed by meal_name or have a "meals" array
        if "meals" in data:
            meals = data["meals"]
        else:
            # Each key might be a meal
            for key, val in data.items():
                if isinstance(val, dict):
                    val["_key"] = key
                    meals.append(val)

    main_meal_names = {"breakfast", "lunch", "dinner", "meal_1", "meal_2", "meal_3"}
    seen_meals = set()
    total_cal = 0

    for meal in meals:
        meal_name = None
        calories = 0

        if isinstance(meal, dict):
            # Try to get meal_name
            meal_name = meal.get("meal_name") or meal.get("_key") or meal.get("type", "")
            meal_name = meal_name.lower().strip() if meal_name else ""

            # Get calories - could be in dishes or at top level
            if "calories" in meal:
                calories = meal["calories"] or 0
            elif "total_calories" in meal:
                calories = meal["total_calories"] or 0
            elif "dishes" in meal:
                for dish in meal.get("dishes", []):
                    calories += dish.get("calories", 0)

        if meal_name in main_meal_names:
            seen_meals.add(meal_name)
        total_cal += calories

    result["main_meal_count"] = len(seen_meals)
    result["total_calories"] = total_cal
    return result


def load_badges(workspace_dir: str) -> dict:
    """Load existing badges.json or return default structure."""
    badges_path = Path(workspace_dir) / "data" / "badges.json"
    default = {
        "calorie_target": {
            "current_level": 0,
            "current_count": 0,
            "next_level_target": LEVELS[0]["days"],
            "qualified_dates": [],
            "unlocked_at": {},
            "daily_deficit": 300,
            "last_calculated": None,
        }
    }

    if not badges_path.exists():
        return default

    try:
        data = json.loads(badges_path.read_text(encoding="utf-8"))
        if "calorie_target" not in data:
            data["calorie_target"] = default["calorie_target"]
        return data
    except (json.JSONDecodeError, OSError):
        return default


def save_badges(workspace_dir: str, badges: dict):
    """Save badges.json."""
    badges_dir = Path(workspace_dir) / "data"
    badges_dir.mkdir(parents=True, exist_ok=True)
    badges_path = badges_dir / "badges.json"
    badges_path.write_text(json.dumps(badges, indent=2, ensure_ascii=False), encoding="utf-8")


def get_level_for_count(count: int) -> int:
    """Get the level number for a given count."""
    level = 0
    for lv in LEVELS:
        if count >= lv["days"]:
            level = lv["level"]
        else:
            break
    return level


def get_next_level_target(current_level: int) -> int:
    """Get the day count needed for the next level."""
    for lv in LEVELS:
        if lv["level"] == current_level + 1:
            return lv["days"]
    return LEVELS[-1]["days"]  # max level


def generate_progress_bar(current_count: int, next_target: int, current_level: int) -> str:
    """Generate a text progress bar."""
    if current_level >= len(LEVELS):
        return "━━━━━━━━━━━━━━ MAX 🏆"

    next_level_info = None
    for lv in LEVELS:
        if lv["level"] == current_level + 1:
            next_level_info = lv
            break

    if not next_level_info:
        return "━━━━━━━━━━━━━━ MAX 🏆"

    # Previous level target (or 0 if level 0)
    prev_target = 0
    for lv in LEVELS:
        if lv["level"] == current_level:
            prev_target = lv["days"]
            break

    progress = current_count - prev_target
    total_needed = next_target - prev_target
    bar_length = 14
    filled = int((progress / total_needed) * bar_length) if total_needed > 0 else 0
    filled = min(filled, bar_length)

    bar = "━" * filled + "░" * (bar_length - filled)
    return f"{bar} {current_count}/{next_target} → 下一级：{next_level_info['name']}"


def check(workspace_dir: str, tz_offset: int):
    """Main check logic."""
    today = get_local_date(tz_offset)

    # Parse plan data
    plan = parse_plan(workspace_dir)
    calorie_target = plan["calorie_target"]
    bmr = plan["bmr"]
    daily_deficit = plan["daily_deficit"]
    expected_meals = plan["expected_meals"]

    # Fallback BMR from health-profile
    if bmr is None:
        hp = parse_health_profile(workspace_dir)
        bmr = hp["bmr"]

    # If no calorie target found, can't evaluate
    if calorie_target is None:
        print(json.dumps({
            "qualified_today": False,
            "already_counted": False,
            "current_count": 0,
            "current_level": 0,
            "level_up": False,
            "new_badge": None,
            "badge_image": None,
            "error": "no_calorie_target_in_plan"
        }))
        return

    # Load today's meals
    meals = load_today_meals(workspace_dir, today)
    main_meal_count = meals["main_meal_count"]
    total_calories = meals["total_calories"]

    # Load badges
    badges = load_badges(workspace_dir)
    ct = badges["calorie_target"]

    # Check if already counted today
    already_counted = today in ct.get("qualified_dates", [])

    # Qualification check
    qualified = True
    reasons = []

    # Condition 1: enough main meals
    if main_meal_count < expected_meals:
        qualified = False
        reasons.append(f"main_meals_{main_meal_count}_of_{expected_meals}")

    # Condition 2: calories in range (target ± 10%)
    cal_low = calorie_target * 0.9
    cal_high = calorie_target * 1.1
    if not (cal_low <= total_calories <= cal_high):
        qualified = False
        reasons.append(f"calories_{total_calories}_not_in_{cal_low:.0f}-{cal_high:.0f}")

    # Condition 3: above safety floor (BMR × 0.8)
    if bmr is not None:
        safety_floor = bmr * 0.8
        if total_calories < safety_floor:
            qualified = False
            reasons.append(f"below_safety_floor_{safety_floor:.0f}")

    # Update badges if qualified and not already counted
    level_up = False
    new_badge = None
    badge_image = None

    if qualified and not already_counted:
        ct["qualified_dates"].append(today)
        ct["current_count"] = len(ct["qualified_dates"])
        ct["daily_deficit"] = daily_deficit
        ct["last_calculated"] = today

        # Check for level up
        new_level = get_level_for_count(ct["current_count"])
        if new_level > ct["current_level"]:
            level_up = True
            ct["current_level"] = new_level
            ct["unlocked_at"][str(new_level)] = today

            # Find level info
            level_info = None
            for lv in LEVELS:
                if lv["level"] == new_level:
                    level_info = lv
                    break

            milk_tea_cups = (daily_deficit * ct["current_count"]) // MILK_TEA_KCAL
            next_target = get_next_level_target(new_level)
            ct["next_level_target"] = next_target
            progress_bar = generate_progress_bar(ct["current_count"], next_target, new_level)

            new_badge = {
                "level": new_level,
                "name": level_info["name"],
                "message": level_info["message"],
                "milk_tea_cups": milk_tea_cups,
                "progress_bar": progress_bar,
            }

            # Badge image generation placeholder
            # TODO: Generate image when template assets are provided
            badge_image = None
        else:
            ct["next_level_target"] = get_next_level_target(ct["current_level"])

        save_badges(workspace_dir, badges)
    elif not already_counted:
        # Not qualified, don't save
        pass

    # Build output
    output = {
        "qualified_today": qualified,
        "already_counted": already_counted,
        "current_count": ct["current_count"],
        "current_level": ct["current_level"],
        "level_up": level_up,
        "new_badge": new_badge,
        "badge_image": badge_image,
    }

    if not qualified:
        output["disqualify_reasons"] = reasons

    print(json.dumps(output, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description="Calorie target badge calculator")
    sub = parser.add_subparsers(dest="command")

    check_parser = sub.add_parser("check", help="Check today's qualification and update badges")
    check_parser.add_argument("--workspace-dir", required=True, help="User workspace directory")
    check_parser.add_argument("--tz-offset", required=True, type=int, help="Timezone offset in minutes")

    args = parser.parse_args()

    if args.command == "check":
        check(args.workspace_dir, args.tz_offset)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
