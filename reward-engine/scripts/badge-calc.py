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

from PIL import Image, ImageDraw, ImageFont


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

# Percentile speed table: level -> list of (max_elapsed_days, percentile_str)
PERCENTILE_TABLE = {
    1: [(3, "99%"), (5, "95%"), (7, "90%"), (10, "85%"), (14, "80%"), (21, "75%"), (28, "70%"), (35, "60%"), (42, "50%"), (56, "40%"), (70, "30%"), (90, "20%"), (999999, "10%")],
    2: [(5, "99%"), (7, "95%"), (10, "90%"), (14, "85%"), (21, "80%"), (28, "75%"), (35, "70%"), (42, "60%"), (56, "50%"), (70, "40%"), (90, "30%"), (120, "20%"), (999999, "10%")],
    3: [(7, "99%"), (10, "95%"), (14, "90%"), (21, "85%"), (28, "80%"), (35, "75%"), (42, "70%"), (56, "60%"), (70, "50%"), (90, "40%"), (120, "30%"), (150, "20%"), (999999, "10%")],
    4: [(7, "99%"), (14, "95%"), (21, "90%"), (28, "85%"), (35, "80%"), (42, "75%"), (56, "70%"), (70, "60%"), (90, "50%"), (120, "40%"), (150, "30%"), (200, "20%"), (999999, "10%")],
    5: [(10, "99%"), (14, "95%"), (21, "90%"), (30, "85%"), (42, "80%"), (56, "75%"), (70, "70%"), (90, "60%"), (120, "50%"), (150, "40%"), (200, "30%"), (300, "20%"), (999999, "10%")],
    6: [(14, "99%"), (21, "95%"), (30, "90%"), (42, "85%"), (56, "80%"), (70, "75%"), (90, "70%"), (120, "60%"), (150, "50%"), (200, "40%"), (250, "30%"), (350, "20%"), (999999, "10%")],
    7: [(14, "99%"), (21, "95%"), (30, "90%"), (42, "85%"), (56, "80%"), (70, "75%"), (90, "70%"), (120, "60%"), (150, "50%"), (200, "40%"), (300, "30%"), (400, "20%"), (999999, "10%")],
    8: [(21, "99%"), (30, "95%"), (42, "90%"), (56, "85%"), (70, "80%"), (90, "75%"), (120, "70%"), (150, "60%"), (200, "50%"), (250, "40%"), (300, "30%"), (400, "20%"), (999999, "10%")],
}

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

PERCENTILE_LINE2_EN = {
    "99%": "Incredible — faster than 99% of everyone!",
    "95%": "Amazing pace — ahead of 95% of people",
    "90%": "Flying ahead of 90% of people",
    "85%": "Steady rhythm — ahead of 85%",
    "80%": "Faster here than 80% of people",
    "75%": "Quietly ahead of 75% already",
    "70%": "Solid and steady — ahead of 70%",
    "60%": "Your consistency beats 60% of people",
    "50%": "Already ahead of half the pack",
    "40%": "Moving forward daily — ahead of 40%",
    "30%": "On your way — ahead of 30%",
    "20%": "Slow start is fine — already past 20%",
    "10%": "First step already wins — ahead of 10%",
}



# Level -> text color (RGBA) for line2
LEVEL_TEXT_COLOR = {
    1: (143, 89, 41, 255),    # #8F5929
    2: (148, 84, 88, 255),    # #945458
    3: (217, 123, 82, 255),   # #D97B52
    4: (56, 92, 43, 255),     # #385C2B
    5: (94, 134, 170, 255),   # #5E86AA
}
DEFAULT_TEXT_COLOR = (143, 89, 41, 255)  # fallback to Level 1 color

def calc_percentile(level: int, elapsed_days: int) -> str:
    """Calculate percentile ranking based on level and elapsed calendar days."""
    table = PERCENTILE_TABLE.get(level, PERCENTILE_TABLE.get(5))
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
    # Strip markdown formatting (bold/italic) to normalize pattern matching
    content = re.sub(r"\*{1,2}([^*]+)\*{1,2}", r"\1", content)
    content = content.replace("\u2013", "-").replace("\u2014", "-")


    # Parse Daily Calorie Range (e.g., "Daily Calorie Range: 1200-1400" or "1,200 ~ 1,400")
    range_patterns = [
        r"Daily Calorie Range[:\s]*(?:~|约|大约|≈)?\s*(\d[,，\d]*)\s*[-~]\s*(\d[,，\d]*)",
        r"每日热量范围[:\s：]*(?:~|约|大约|≈)?\s*(\d[,，\d]*)\s*[-~]\s*(\d[,，\d]*)",
        r"Calorie Range[:\s]*(?:~|约|大约|≈)?\s*(\d[,，\d]*)\s*[-~–—]\s*(\d[,，\d]*)",
        r"Range[:\s]*(?:~|约|大约|≈)?\s*(\d[,，\d]*)\s*[-~–—]\s*(\d[,，\d]*)\s*(?:kcal|大卡)?",
    ]

    for pattern in range_patterns:
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            low = int(match.group(1).replace(",", "").replace("，", ""))
            high = int(match.group(2).replace(",", "").replace("，", ""))
            result["cal_range"] = (low, high)
            result["calorie_target"] = (low + high) // 2
            break

    # Fallback: single target value
    if result["calorie_target"] is None:
        target_patterns = [
            r"每日热量目标[:\s：]*(?:~|约|大约|≈)?\s*(\d[,，\d]*)\s*(?:大卡|kcal|千卡)?",
            r"Daily Calories?[:\s]*(?:~|约|大约|≈)?\s*(\d[,，\d]*)",
            r"Daily Calorie Budget[:\s]*(?:~|约|大约|≈)?\s*(\d[,，\d]*)",
            r"Daily Calorie Target[:\s]*(?:~|约|大约|≈)?\s*(\d[,，\d]*)",
            r"Calories[:\s]*(?:~|约|大约|≈)?\s*(\d[,，\d]*)\s*(?:kcal|大卡|千卡)",
            r"Target[:\s]*(?:~|约|大约|≈)?\s*(\d[,，\d]*)\s*(?:kcal|大卡|千卡)",
            r"每日热量[:\s：]*(?:~|约|大约|≈)?\s*(\d[,，\d]*)\s*(?:大卡|kcal|千卡)?",
        ]
        for pattern in target_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                val = int(match.group(1).replace(",", "").replace("，", ""))
                if 800 <= val <= 3000:
                    result["calorie_target"] = val
                break

    # Parse BMR
    bmr_match = re.search(r"BMR[:\s]*(\d[,\d]*)", content, re.IGNORECASE)
    if bmr_match:
        result["bmr"] = int(bmr_match.group(1).replace(",", ""))

    # Parse daily deficit
    deficit_patterns = [
        r"Daily (?:Calorie )?Deficit[:\s]*(?:~|约|大约|≈)?\s*(\d[,\d]*)",
        r"每日[热量]*缺口[:\s：]*(?:~|约|大约|≈)?\s*(\d[,\d]*)",
    ]
    for pattern in deficit_patterns:
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            result["daily_deficit"] = int(match.group(1).replace(",", "").replace("，", ""))
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

    main_meal_names = {"breakfast", "lunch", "dinner", "meal_1", "meal_2", "meal_3"}
    seen_meals = set()
    total_cal = 0

    for meal in meals:
        meal_name = None
        calories = 0

        if isinstance(meal, dict):
            # Try to get meal_name from various formats
            meal_name = (meal.get("meal_type") or meal.get("meal_name")
                         or meal.get("_key") or meal.get("type", ""))
            meal_name = meal_name.lower().strip() if meal_name else ""

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
    """Initialize badges for first run — start from zero, do not replay history.

    Rationale: historical meals were logged under potentially different PLAN
    calorie ranges, so retroactive qualification would be inaccurate.
    Users accumulate from today onward.
    """
    return {
        "current_level": 0,
        "current_count": 0,
        "next_level_target": LEVELS[0]["days"],
        "qualified_dates": [],
        "unlocked_at": {},
        "daily_deficit": daily_deficit,
        "last_calculated": None,
        "backfilled": True,
    }


# Agent registry paths to search for nickname
_AGENT_REGISTRY_CANDIDATES = [
    Path("/home/admin/.openclaw/extensions/wechat/agent-registry.json"),
]


def _resolve_nickname(workspace_dir: str) -> str:
    """
    Resolve user nickname with fallback chain:
    1. agent-registry.json (match by account ID from workspace path)
    2. USER.md in workspace (improved regex)
    3. Fallback: "小犀牛"
    """
    fallback = "小犀牛"

    # --- Try 1: agent-registry.json ---
    try:
        # Extract account-like IDs from workspace_dir path
        # Path patterns: .openclaw-gateway/workspace-wechat-dm-{peerAccId}_{selfAccId}/
        # or .openclaw-user-service/workspaces/{agentId}/ where agentId = peerAccId_selfAccId
        ws_name = Path(workspace_dir).name
        # Account IDs look like: acc8bOJDErKkNOUvDXxZx7I or accYcdSNiv4Jk6lYrnEH3uf
        import re as _re
        acc_ids = _re.findall(r'acc[A-Za-z0-9_-]+', ws_name)

        if acc_ids:
            for registry_path in _AGENT_REGISTRY_CANDIDATES:
                if not registry_path.exists():
                    continue
                registry = json.loads(registry_path.read_text(encoding="utf-8"))
                agents = registry.get("agents", registry)  # handle both root-level and nested
                for acc_id in acc_ids:
                    # Try exact and lowercase lookup
                    for key_variant in [acc_id, acc_id.lower()]:
                        agent_entry = agents.get(key_variant)
                        if agent_entry:
                            profile_name = None
                            if isinstance(agent_entry, dict):
                                profile_name = (
                                    agent_entry.get("profile", {}).get("name")
                                    or agent_entry.get("name")
                                )
                            if profile_name and profile_name.strip():
                                return profile_name.strip()
    except Exception:
        pass  # Non-fatal, continue to next method

    # --- Try 2: USER.md ---
    try:
        user_md = Path(workspace_dir) / "USER.md"
        if user_md.exists():
            file_content = user_md.read_text(encoding="utf-8")
            # Match patterns like:
            # - **Name:** xxx / - **Nickname:** xxx / 昵称：xxx / 称呼：xxx
            # - What to call them: xxx / Name: xxx
            nickname_patterns = [
                r'\*{0,2}(?:Name|Nickname|昵称|称呼|名字|What to call them)\*{0,2}\s*[:：]\s*(.+)',
            ]
            for line in file_content.splitlines():
                for pattern in nickname_patterns:
                    m = _re.search(pattern, line, _re.IGNORECASE)
                    if m:
                        val = m.group(1).strip().strip("*").strip()
                        if val and val != "（待采集）" and val != "（自动填充）":
                            return val
    except Exception:
        pass  # Non-fatal

    return fallback


def _resolve_locale(workspace_dir: str) -> str:
    """Read Language from USER.md '## Locale & Timezone'. Return 'zh' or 'en'."""
    try:
        user_md = Path(workspace_dir) / "USER.md"
        if user_md.exists():
            content = user_md.read_text(encoding="utf-8")
            import re as _re
            m = _re.search(r'Language[:：]\s*\**\s*([A-Za-z\-]+)', content)
            if m:
                lang = m.group(1).lower()
                return "zh" if lang.startswith("zh") else "en"
    except Exception:
        pass
    return "zh"  # default Chinese


def generate_badge_image(workspace_dir: str, today: str, new_badge: dict, current_count: int, badges: dict = None) -> str:
    """
    Generate badge card PNG using Pillow.
    Renders one dynamic line (line2: personalized encouragement) on a pre-designed base image.
    Returns local file path or None on failure.
    """
    script_dir = Path(__file__).parent
    assets_dir = script_dir.parent / "assets"

    # Determine base image (locale + level-specific, with fallbacks)
    level = new_badge.get("level", 1)
    locale = _resolve_locale(workspace_dir)
    suffix = "-en" if locale == "en" else ""
    base_img_path = assets_dir / f"badge-base-level{level}{suffix}.png"
    if not base_img_path.exists():
        base_img_path = assets_dir / f"badge-base-level1{suffix}.png"
    if not base_img_path.exists():
        base_img_path = assets_dir / "badge-base-level1.png"  # final fallback: Chinese
    if not base_img_path.exists():
        sys.stderr.write(f"No base badge image found at {base_img_path}\n")
        return None

    # Resolve user nickname (try agent registry first, then USER.md, then fallback)
    nickname = _resolve_nickname(workspace_dir)


    # Calculate percentile for line2
    if badges is None:
        badges = load_badges(workspace_dir)
    ct = badges.get("calorie_target", {})
    unlocked_at = ct.get("unlocked_at", {})
    prev_level = level - 1
    if prev_level > 0 and str(prev_level) in unlocked_at:
        prev_date = datetime.strptime(unlocked_at[str(prev_level)], "%Y-%m-%d")
        current_date = datetime.strptime(today, "%Y-%m-%d")
        elapsed_days = (current_date - prev_date).days
    else:
        qualified_dates = ct.get("qualified_dates", [])
        if qualified_dates:
            first_date = datetime.strptime(qualified_dates[0], "%Y-%m-%d")
            current_date = datetime.strptime(today, "%Y-%m-%d")
            elapsed_days = (current_date - first_date).days
        else:
            elapsed_days = level * 7

    percentile = calc_percentile(level, elapsed_days)
    if locale == "en":
        line2_base = PERCENTILE_LINE2_EN.get(percentile, "Already ahead of half the pack")
        line2_text = f'"{nickname}, {line2_base}"'
    else:
        line2_base = PERCENTILE_LINE2.get(percentile, "\u5df2\u7ecf\u8dd1\u8d62\u4e86\u4e00\u534a\u7684\u4eba")
        line2_text = f"\u201c{nickname}\uff0c{line2_base}\u201d"

    # Render with Pillow
    try:
        img = Image.open(base_img_path)
        draw = ImageDraw.Draw(img)

        # Font: Noto Sans SC Regular, design spec 16px on 480x720 -> 32px on 960x1440
        font_size = 32
        font_candidates = [
            Path(__file__).parent.parent / "assets/fonts/NotoSansSC-Regular.otf",
            Path.home() / ".local/share/fonts/NotoSansSC/NotoSansCJKsc-Regular.otf",
            Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
            Path("/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc"),
        ]
        font_path = None
        for fp in font_candidates:
            if fp.exists():
                font_path = fp
                break

        if font_path is None:
            sys.stderr.write("Noto Sans SC font not found, badge image generation skipped\n")
            return None

        font = ImageFont.truetype(str(font_path), font_size)

        # Position: y=448 on 480x720 design -> y=896 on 960x1440; horizontally centered
        img_width = img.size[0]
        y = 955 if locale == "en" else 896

        # Measure text width; shrink font if too wide (keep single line)
        bbox = font.getbbox(line2_text)
        text_width = bbox[2] - bbox[0]
        min_font_size = 20
        while text_width > img_width - 80 and font_size > min_font_size:
            font_size -= 1
            font = ImageFont.truetype(str(font_path), font_size)
            bbox = font.getbbox(line2_text)
            text_width = bbox[2] - bbox[0]

        x = (img_width - text_width) // 2

        # Color per level
        text_color = LEVEL_TEXT_COLOR.get(level, DEFAULT_TEXT_COLOR)
        draw.text((x, y), line2_text, font=font, fill=text_color)

        # Save
        filename = f"badge-{Path(workspace_dir).name}-{today}.png"
        # Save to workspace badges dir (persistent) instead of /tmp
        badges_dir = Path(workspace_dir) / "data" / "badges"
        badges_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(badges_dir / filename)
        img.save(output_path, "PNG")
        return output_path

    except Exception as e:
        sys.stderr.write(f"Badge image generation error: {e}\n")
        return None


def check(workspace_dir: str, tz_offset: int):
    """Main check logic."""
    today = get_local_date(tz_offset)

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

            # Generate badge image
            badge_image = generate_badge_image(
                workspace_dir, today, new_badge, ct["current_count"], badges
            )
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
