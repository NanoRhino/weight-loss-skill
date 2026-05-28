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
import subprocess
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

# Meal name normalization: map all variants (Chinese, English, typos) to canonical keys
MEAL_ALIAS = {
    "breakfast": "breakfast", "早餐": "breakfast", "早饭": "breakfast", "早点": "breakfast",
    "lunch": "lunch", "午餐": "lunch", "午饭": "lunch", "中餐": "lunch", "中饭": "lunch",
    "dinner": "dinner", "晚餐": "dinner", "晚饭": "dinner", "夜饭": "dinner",
    "meal_1": "meal_1", "meal_2": "meal_2", "meal_3": "meal_3",
}

MAIN_MEAL_CANONICAL = {"breakfast", "lunch", "dinner", "meal_1", "meal_2", "meal_3"}


def normalize_meal_name(name: str) -> str | None:
    """Normalize meal name to canonical form. Returns None if not a main meal."""
    cleaned = name.lower().strip()
    canonical = MEAL_ALIAS.get(cleaned)
    if canonical:
        return canonical
    # Fuzzy fallback: check if any alias is a substring
    for alias, canon in MEAL_ALIAS.items():
        if alias in cleaned or cleaned in alias:
            return canon
    return None

# Percentile ranking table: level -> list of (max_elapsed_days, percentile_text)
# elapsed_days = calendar days from previous level-up (or first qualified date for L1) to this level-up
# Each level only counts the NEW days needed (L1=3, L2=4, L3=7, L4=16, L5=30)
PERCENTILE_TABLE = {
    1: [  # needs 3 new days
        (3, "99%"),
        (4, "95%"),
        (5, "90%"),
        (6, "85%"),
        (7, "80%"),
        (9, "75%"),
        (11, "70%"),
        (14, "60%"),
        (18, "50%"),
        (23, "40%"),
        (30, "30%"),
        (40, "20%"),
        (60, "10%"),
        (999999, "10%"),
    ],
    2: [  # needs 4 new days
        (4, "99%"),
        (5, "95%"),
        (7, "90%"),
        (9, "85%"),
        (10, "80%"),
        (12, "75%"),
        (14, "70%"),
        (20, "60%"),
        (27, "50%"),
        (35, "40%"),
        (45, "30%"),
        (60, "20%"),
        (90, "10%"),
        (999999, "10%"),
    ],
    3: [  # needs 7 new days
        (7, "99%"),
        (9, "95%"),
        (12, "90%"),
        (15, "85%"),
        (17, "80%"),
        (20, "75%"),
        (24, "70%"),
        (35, "60%"),
        (45, "50%"),
        (60, "40%"),
        (80, "30%"),
        (110, "20%"),
        (150, "10%"),
        (999999, "10%"),
    ],
    4: [  # needs 16 new days
        (16, "99%"),
        (20, "95%"),
        (27, "90%"),
        (32, "85%"),
        (36, "80%"),
        (42, "75%"),
        (48, "70%"),
        (65, "60%"),
        (85, "50%"),
        (110, "40%"),
        (140, "30%"),
        (180, "20%"),
        (240, "10%"),
        (999999, "10%"),
    ],
    5: [  # needs 30 new days
        (30, "99%"),
        (38, "95%"),
        (50, "90%"),
        (58, "85%"),
        (68, "80%"),
        (78, "75%"),
        (90, "70%"),
        (120, "60%"),
        (150, "50%"),
        (190, "40%"),
        (240, "30%"),
        (300, "20%"),
        (400, "10%"),
        (999999, "10%"),
    ],
    6: [  # needs 15 new days (45-30)
        (15, "99%"),
        (19, "95%"),
        (25, "90%"),
        (29, "85%"),
        (34, "80%"),
        (39, "75%"),
        (45, "70%"),
        (60, "60%"),
        (80, "50%"),
        (100, "40%"),
        (130, "30%"),
        (170, "20%"),
        (220, "10%"),
        (999999, "10%"),
    ],
    7: [  # needs 15 new days (60-45)
        (15, "99%"),
        (19, "95%"),
        (25, "90%"),
        (29, "85%"),
        (34, "80%"),
        (39, "75%"),
        (45, "70%"),
        (60, "60%"),
        (80, "50%"),
        (100, "40%"),
        (130, "30%"),
        (170, "20%"),
        (220, "10%"),
        (999999, "10%"),
    ],
    8: [  # needs 30 new days (90-60)
        (30, "99%"),
        (38, "95%"),
        (50, "90%"),
        (58, "85%"),
        (68, "80%"),
        (78, "75%"),
        (90, "70%"),
        (120, "60%"),
        (150, "50%"),
        (190, "40%"),
        (240, "30%"),
        (300, "20%"),
        (400, "10%"),
        (999999, "10%"),
    ],
}

# Percentile -> line2 copy for badge image
PERCENTILE_LINE2 = {
    "99%": "太厉害了，达标速度超过了99%的人",
    "95%": "这速度绝了，超过了95%的人",
    "90%": "进度飞快，超过了90%的人",
    "85%": "节奏很稳，超过了85%的人",
    "80%": "比80%的人都快到这一步",
    "75%": "不知不觉已经超过了75%的人",
    "70%": "稳扎稳打，超过了70%的人",
    "60%": "你的坚持超过了60%的人",
    "50%": "已经跑赢了一半的人",
    "40%": "每一天都在往前走，超过了40%的人",
    "30%": "还在路上，超过了30%的人",
    "20%": "起步不怕慢，已经超过了20%的人",
    "10%": "迈出第一步就已经赢了，超过了10%的人",
}


def calc_percentile(level: int, elapsed_days: int) -> str:
    """Calculate percentile ranking based on level and elapsed calendar days."""
    table = PERCENTILE_TABLE.get(level, PERCENTILE_TABLE.get(5))  # fallback to L5
    for max_days, pct in table:
        if elapsed_days <= max_days:
            return pct
    return "50%"


def get_local_date(tz_offset_minutes: int) -> str:
    """Get today's date string in user's local timezone."""
    tz = timezone(timedelta(minutes=tz_offset_minutes))
    return datetime.now(tz).strftime("%Y-%m-%d")


def parse_plan(workspace_dir: str) -> dict:
    """Parse PLAN.md for calorie target, BMR, deficit, and meal count."""
    plan_path = Path(workspace_dir) / "PLAN.md"
    result = {
        "calorie_target": None,
        "cal_range": None,  # (low, high) from Daily Calorie Range
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
        r"每日热量范围[:\s：]*(\d[,\d]*)\s*[-~]\s*(\d[,\d]*)",
    ]

    for pattern in range_patterns:
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            low = int(match.group(1).replace(",", ""))
            high = int(match.group(2).replace(",", ""))
            result["cal_range"] = (low, high)
            result["calorie_target"] = (low + high) // 2
            break

    # Fallback: single target value
    if result["calorie_target"] is None:
        target_patterns = [
            r"每日热量目标[:\s：]*(\d[,\d]*)",
            r"Daily Calories?[:\s]*~?(\d[,\d]*)",
            r"Daily Calorie Budget[:\s]*(\d[,\d]*)",
        ]
        for pattern in target_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                val = int(match.group(1).replace(",", ""))
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


def load_today_meals(workspace_dir: str, date_str: str) -> dict:
    """Load a specific day's meal data and return meal count + total calories."""
    meals_path = Path(workspace_dir) / "data" / "meals" / f"{date_str}.json"
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

    seen_meals = set()
    total_cal = 0

    for meal in meals:
        meal_name = None
        calories = 0

        if isinstance(meal, dict):
            # Try to get meal_name from various formats
            meal_name = (meal.get("meal_type") or meal.get("meal_name")
                         or meal.get("_key") or meal.get("type", ""))
            meal_name = meal_name.strip() if meal_name else ""

            # Get calories - try multiple formats
            if "calories" in meal:
                calories = meal["calories"] or 0
            elif "total_calories" in meal:
                calories = meal["total_calories"] or 0
            elif "items" in meal:
                for item in meal.get("items", []):
                    calories += item.get("calories", 0)
            elif "dishes" in meal:
                for dish in meal.get("dishes", []):
                    calories += dish.get("calories", 0)

        # Normalize meal name and check if it's a main meal
        if meal_name:
            canonical = normalize_meal_name(meal_name)
            if canonical and canonical in MAIN_MEAL_CANONICAL:
                seen_meals.add(canonical)
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


def qualify_day(workspace_dir: str, date_str: str, cal_range: tuple, bmr, expected_meals: int) -> bool:
    """Check if a specific date qualifies (3 conditions)."""
    meals = load_today_meals(workspace_dir, date_str)
    main_meal_count = meals["main_meal_count"]
    total_calories = meals["total_calories"]

    if total_calories == 0:
        return False

    # Condition 1: enough main meals
    if main_meal_count < expected_meals:
        return False

    # Condition 2: calories in target range
    cal_low, cal_high = cal_range
    if not (cal_low <= total_calories <= cal_high):
        return False

    # Condition 3: above safety floor (BMR × 0.8)
    if bmr is not None:
        safety_floor = bmr * 0.8
        if total_calories < safety_floor:
            return False

    return True


def backfill(workspace_dir: str, cal_range: tuple, bmr, expected_meals: int, daily_deficit: int) -> dict:
    """Scan all historical meal files and build badges from scratch.
    Returns the populated calorie_target dict."""
    meals_dir = Path(workspace_dir) / "data" / "meals"
    qualified_dates = []

    if meals_dir.exists():
        # Get all meal files sorted by date
        meal_files = sorted(meals_dir.glob("*.json"))
        for meal_file in meal_files:
            date_str = meal_file.stem[:10]  # YYYY-MM-DD
            # Validate date format
            try:
                datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                continue

            if qualify_day(workspace_dir, date_str, cal_range, bmr, expected_meals):
                qualified_dates.append(date_str)

    count = len(qualified_dates)
    level = get_level_for_count(count)

    # Build unlocked_at by replaying level transitions
    unlocked_at = {}
    running_count = 0
    for date_str in qualified_dates:
        running_count += 1
        new_level = get_level_for_count(running_count)
        if str(new_level) not in unlocked_at and new_level > 0:
            unlocked_at[str(new_level)] = date_str

    return {
        "current_level": level,
        "current_count": count,
        "next_level_target": get_next_level_target(level),
        "qualified_dates": qualified_dates,
        "unlocked_at": unlocked_at,
        "daily_deficit": daily_deficit,
        "last_calculated": qualified_dates[-1] if qualified_dates else None,
        "backfilled": True,
    }


def generate_badge_image(workspace_dir: str, today: str, new_badge: dict, current_count: int) -> str:
    """Generate badge card PNG via ImageMagick overlay. Returns public URL or None on failure."""
    script_dir = Path(__file__).parent

    # Read user nickname from USER.md
    nickname = "小犀牛"
    user_md = Path(workspace_dir) / "USER.md"
    if user_md.exists():
        content = user_md.read_text(encoding="utf-8")
        for line in content.splitlines():
            if "nickname" in line.lower() or "昵称" in line:
                parts = line.split(":", 1) if ":" in line else line.split("：", 1)
                if len(parts) == 2:
                    nickname = parts[1].strip() or nickname
                    break

    # Format date
    date_formatted = today.replace("-", ".")

    # Output to nginx public dir for direct URL access
    public_dir = "/usr/share/nginx/html/tmp"
    os.makedirs(public_dir, exist_ok=True)
    filename = f"badge-{Path(workspace_dir).name}-{today}.png"
    output_path = f"{public_dir}/{filename}"
    public_url = f"https://nanorhino.ai/tmp/{filename}"

    # Use ImageMagick overlay script
    shell_script = script_dir / "generate-badge-img.sh"
    if shell_script.exists():
        # Determine base image (level-specific or fallback to level1)
        assets_dir = script_dir.parent / "assets"
        level = new_badge.get("level", 1)
        base_img = assets_dir / f"badge-base-level{level}.png"
        if not base_img.exists():
            base_img = assets_dir / "badge-base-level1.png"
        if not base_img.exists():
            sys.stderr.write(f"No base badge image found at {base_img}\n")
            return None

        try:
            result = subprocess.run(
                ["bash", str(shell_script),
                 "--base", str(base_img),
                 "--output", output_path,
                 "--line1a", f"累计热量达标{current_count}天",
                 "--line1b", f"相当于少喝了{new_badge.get('milk_tea_cups', 0)}杯奶茶🧋",
                 "--line2", PERCENTILE_LINE2.get(new_badge.get("percentile", "50%"), "已经跑赢了一半的人"),
                 "--username", nickname,
                 "--username-sub", "",
                 "--date", date_formatted],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode == 0 and os.path.exists(output_path):
                return public_url
            else:
                sys.stderr.write(f"generate-badge-img.sh failed: {result.stderr[:200]}\n")
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            sys.stderr.write(f"generate-badge-img.sh error: {e}\n")

    return None


def check(workspace_dir: str, tz_offset: int, target_date: str = None):
    """Main check logic.
    
    Args:
        target_date: Optional specific date to check (YYYY-MM-DD). 
                     Used for back-fill/补录 scenarios.
                     If None, checks today.
    """
    today = target_date if target_date else get_local_date(tz_offset)

    # Parse plan data
    plan = parse_plan(workspace_dir)
    calorie_target = plan["calorie_target"]
    cal_range = plan["cal_range"]
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

    # If no explicit range, fallback to target ± 10%
    if cal_range is None:
        cal_range = (int(calorie_target * 0.9), int(calorie_target * 1.1))

    # Load badges
    badges = load_badges(workspace_dir)
    ct = badges["calorie_target"]

    # Auto-backfill on first run (badges.json empty or never backfilled)
    if not ct.get("backfilled") and ct["current_count"] == 0:
        ct = backfill(workspace_dir, cal_range, bmr, expected_meals, daily_deficit)
        badges["calorie_target"] = ct
        save_badges(workspace_dir, badges)

    # Load today's meals
    meals = load_today_meals(workspace_dir, today)
    main_meal_count = meals["main_meal_count"]
    total_calories = meals["total_calories"]

    # Check if already counted today
    already_counted = today in ct.get("qualified_dates", [])

    # Qualification check
    qualified = True
    reasons = []

    # Condition 1: enough main meals
    if main_meal_count < expected_meals:
        qualified = False
        reasons.append(f"main_meals_{main_meal_count}_of_{expected_meals}")

    # Condition 2: calories in target range (from PLAN.md)
    cal_low, cal_high = cal_range
    if not (cal_low <= total_calories <= cal_high):
        qualified = False
        reasons.append(f"calories_{total_calories}_not_in_{cal_low}-{cal_high}")

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

            # Calculate elapsed days for percentile ranking
            # For L1: from first_qualified_date to today
            # For L2+: from previous level_up_date to today
            prev_level = new_level - 1
            if prev_level >= 1 and str(prev_level) in ct.get("unlocked_at", {}):
                ref_date_str = ct["unlocked_at"][str(prev_level)]
            elif ct.get("qualified_dates"):
                ref_date_str = ct["qualified_dates"][0]  # first qualified date
            else:
                ref_date_str = today

            try:
                ref_date = datetime.strptime(ref_date_str, "%Y-%m-%d")
                current_date = datetime.strptime(today, "%Y-%m-%d")
                elapsed_days = (current_date - ref_date).days + 1  # inclusive
            except ValueError:
                elapsed_days = 999  # fallback

            percentile = calc_percentile(new_level, elapsed_days)

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
                "elapsed_days": elapsed_days,
                "percentile": percentile,
            }

            # Generate badge image
            badge_image = generate_badge_image(
                workspace_dir, today, new_badge, ct["current_count"]
            )

            # Mark pending delivery
            ct["pending_delivery"] = {
                "level": new_badge["level"],
                "date": today,
                "badge_image": badge_image,
                "delivered": False,
            }
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

    # Include pending_delivery info for fallback checks
    if ct.get("pending_delivery") and not ct["pending_delivery"].get("delivered"):
        output["pending_delivery"] = ct["pending_delivery"]

    print(json.dumps(output, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description="Calorie target badge calculator")
    sub = parser.add_subparsers(dest="command")

    check_parser = sub.add_parser("check", help="Check today's qualification and update badges")
    check_parser.add_argument("--workspace-dir", required=True, help="User workspace directory")
    check_parser.add_argument("--tz-offset", required=True, type=int, help="Timezone offset in minutes")
    check_parser.add_argument("--date", default=None, help="Specific date to check (YYYY-MM-DD), for back-fill/补录")

    args = parser.parse_args()

    if args.command == "check":
        check(args.workspace_dir, args.tz_offset, target_date=args.date)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
