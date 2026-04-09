#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
generate-vintage-card.py — Generate a hand-drawn vintage-style daily diet card.

Reads meal data from nutrition-calc.py load output and produces a beautiful
vintage "food journal" HTML card with hand-drawn SVG food illustrations.

Usage:
  python3 generate-vintage-card.py \
    --meals-json '<load output JSON>' \
    [--cal-target 1600] \
    [--user-name "Name"] \
    [--lang zh] \
    [--cal-unit kcal] \
    [--output /path/to/output.html]
"""

import argparse
import html as html_mod
import json
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
TEMPLATE_PATH = SCRIPT_DIR.parent / "templates" / "daily-diet-vintage.html"

# ---------------------------------------------------------------------------
# Meal metadata
# ---------------------------------------------------------------------------
MEAL_ORDER = {
    "breakfast": 0, "snack_am": 1, "lunch": 2,
    "snack_pm": 3, "dinner": 4, "snack": 5,
}

MEAL_LABELS_ZH = {
    "breakfast": "早餐", "snack_am": "上午加餐", "lunch": "午餐",
    "snack_pm": "下午加餐", "dinner": "晚餐", "snack": "加餐",
}

MEAL_LABELS_EN = {
    "breakfast": "Breakfast", "snack_am": "AM Snack", "lunch": "Lunch",
    "snack_pm": "PM Snack", "dinner": "Dinner", "snack": "Snack",
}

MEAL_DECO = {
    "breakfast": ("morning", "·˚ ✧"),
    "snack_am":  ("snack",   "~ ♪"),
    "lunch":     ("noon",    "·˚ ❋"),
    "snack_pm":  ("snack",   "~ ♪"),
    "dinner":    ("evening", "·˚ ✦"),
    "snack":     ("snack",   "~ ♪"),
}

# ---------------------------------------------------------------------------
# Hand-drawn SVG food icons (simple sketch style)
# All icons: 44x44 viewBox, warm brown stroke, round caps
# ---------------------------------------------------------------------------
_S = 'fill="none" stroke="#7c5e2a" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"'
_Sl = 'fill="none" stroke="#7c5e2a" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"'
_Sf = 'fill="#f5e6c8" stroke="#7c5e2a" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"'

FOOD_SVGS = {
    "rice": f'<svg viewBox="0 0 44 44" width="44" height="44">'
        f'<path d="M9 22c0 9 6 14 13 14s13-5 13-14" {_Sf}/>'
        f'<path d="M7 22h30" {_S}/>'
        f'<circle cx="18" cy="18" r="1.5" fill="#7c5e2a"/>'
        f'<circle cx="24" cy="17" r="1.5" fill="#7c5e2a"/>'
        f'<circle cx="21" cy="14" r="1.5" fill="#7c5e2a"/>'
        f'</svg>',

    "noodles": f'<svg viewBox="0 0 44 44" width="44" height="44">'
        f'<path d="M9 24c0 8 6 13 13 13s13-5 13-13" {_Sf}/>'
        f'<path d="M7 24h30" {_S}/>'
        f'<path d="M15 20c2-6 2-10 0-12" {_Sl}/>'
        f'<path d="M22 20c2-6 2-10 0-12" {_Sl}/>'
        f'<path d="M29 20c2-6 2-10 0-12" {_Sl}/>'
        f'</svg>',

    "bread": f'<svg viewBox="0 0 44 44" width="44" height="44">'
        f'<path d="M8 28c0-12 6-18 14-18s14 6 14 18v4H8z" {_Sf}/>'
        f'<path d="M15 20v8" {_Sl}/><path d="M22 18v10" {_Sl}/><path d="M29 20v8" {_Sl}/>'
        f'</svg>',

    "egg": f'<svg viewBox="0 0 44 44" width="44" height="44">'
        f'<ellipse cx="22" cy="24" rx="10" ry="13" {_Sf}/>'
        f'<ellipse cx="22" cy="25" rx="5" ry="5" fill="#f0d48a" stroke="#7c5e2a" stroke-width="1.5"/>'
        f'</svg>',

    "meat": f'<svg viewBox="0 0 44 44" width="44" height="44">'
        f'<path d="M14 10c-4 2-6 6-5 10 2 6 8 10 14 12s10-1 12-5c1-4-1-8-5-10" {_Sf}/>'
        f'<path d="M22 32v6" {_S}/><circle cx="22" cy="40" r="2" fill="#7c5e2a"/>'
        f'</svg>',

    "fish": f'<svg viewBox="0 0 44 44" width="44" height="44">'
        f'<path d="M6 22c4-8 12-12 20-10 4 1 8 4 10 10-2 6-6 9-10 10-8 2-16-2-20-10z" {_Sf}/>'
        f'<circle cx="30" cy="20" r="2" fill="#7c5e2a"/>'
        f'<path d="M4 16c3 2 3 6 3 6s0 4-3 6" {_S}/>'
        f'</svg>',

    "vegetable": f'<svg viewBox="0 0 44 44" width="44" height="44">'
        f'<path d="M22 38v-16" {_S}/>'
        f'<path d="M22 22c-6-2-10-8-8-14" {_Sl}/>'
        f'<path d="M22 22c6-2 10-8 8-14" {_Sl}/>'
        f'<path d="M22 26c-8 0-12-4-10-10" {_Sl}/>'
        f'<path d="M22 26c8 0 12-4 10-10" {_Sl}/>'
        f'<path d="M18 38h8" {_Sl}/>'
        f'</svg>',

    "soup": f'<svg viewBox="0 0 44 44" width="44" height="44">'
        f'<path d="M8 22c0 9 6 14 14 14s14-5 14-14" {_Sf}/>'
        f'<path d="M6 22h32" {_S}/>'
        f'<path d="M16 18c0-3 1-5 0-8" {_Sl}/>'
        f'<path d="M22 17c0-3 1-5 0-8" {_Sl}/>'
        f'<path d="M28 18c0-3 1-5 0-8" {_Sl}/>'
        f'</svg>',

    "milk": f'<svg viewBox="0 0 44 44" width="44" height="44">'
        f'<rect x="12" y="14" width="20" height="24" rx="3" {_Sf}/>'
        f'<path d="M16 14v-4h12v4" {_S}/>'
        f'<path d="M12 24h20" {_Sl}/>'
        f'<path d="M18 28v4" {_Sl}/><path d="M22 27v6" {_Sl}/><path d="M26 28v4" {_Sl}/>'
        f'</svg>',

    "fruit": f'<svg viewBox="0 0 44 44" width="44" height="44">'
        f'<path d="M22 12c-8 0-14 6-14 13s6 12 14 12 14-5 14-12-6-13-14-13z" {_Sf}/>'
        f'<path d="M22 12c-1-4 1-7 4-9" {_Sl}/>'
        f'<path d="M23 11c2 0 5-1 6-3" {_Sl}/>'
        f'</svg>',

    "tofu": f'<svg viewBox="0 0 44 44" width="44" height="44">'
        f'<rect x="10" y="14" width="24" height="18" rx="2" {_Sf}/>'
        f'<path d="M10 22h24" {_Sl}/>'
        f'<path d="M22 14v18" {_Sl}/>'
        f'</svg>',

    "coffee": f'<svg viewBox="0 0 44 44" width="44" height="44">'
        f'<path d="M10 18h20v14c0 4-4 6-10 6s-10-2-10-6z" {_Sf}/>'
        f'<path d="M30 22c4 0 6 2 6 5s-2 5-6 5" {_Sl}/>'
        f'<path d="M18 14c0-3 1-4 0-7" {_Sl}/>'
        f'<path d="M24 14c0-3 1-4 0-7" {_Sl}/>'
        f'</svg>',

    "nut": f'<svg viewBox="0 0 44 44" width="44" height="44">'
        f'<ellipse cx="22" cy="24" rx="12" ry="9" {_Sf}/>'
        f'<path d="M22 15v18" {_Sl}/>'
        f'<path d="M13 20c4 2 8 2 9 4" {_Sl}/>'
        f'<path d="M31 20c-4 2-8 2-9 4" {_Sl}/>'
        f'</svg>',

    "dumpling": f'<svg viewBox="0 0 44 44" width="44" height="44">'
        f'<path d="M8 24c0-6 6-12 14-12s14 6 14 12" {_Sf}/>'
        f'<path d="M8 24h28" {_S}/>'
        f'<path d="M12 24c2-3 5-5 10-5s8 2 10 5" {_Sl}/>'
        f'</svg>',

    "default": f'<svg viewBox="0 0 44 44" width="44" height="44">'
        f'<circle cx="22" cy="24" r="14" {_Sf}/>'
        f'<circle cx="22" cy="24" r="10" {_Sl}/>'
        f'<path d="M18 24h8" {_Sl}/><path d="M22 20v8" {_Sl}/>'
        f'</svg>',
}

# Keyword → icon mapping
FOOD_KEYWORDS = [
    ("rice",      ["米饭", "糙米", "白米", "rice", "饭"]),
    ("noodles",   ["面", "面条", "荞麦面", "意面", "粉", "noodle", "pasta", "拉面", "米粉", "河粉"]),
    ("bread",     ["面包", "吐司", "toast", "bread", "馒头", "包子", "饼"]),
    ("egg",       ["蛋", "鸡蛋", "egg", "蛋花"]),
    ("meat",      ["鸡", "chicken", "肉", "beef", "牛肉", "猪", "pork", "羊", "鸭", "排骨"]),
    ("fish",      ["鱼", "fish", "虾", "shrimp", "海鲜", "三文鱼", "蟹"]),
    ("vegetable", ["菜", "蔬", "西兰花", "broccoli", "青菜", "白菜", "菠菜", "生菜",
                   "黄瓜", "番茄", "胡萝卜", "芹菜", "茄子"]),
    ("soup",      ["汤", "soup", "粥", "porridge", "羹"]),
    ("milk",      ["牛奶", "奶", "milk", "酸奶", "yogurt", "乳"]),
    ("fruit",     ["果", "apple", "苹果", "香蕉", "橙", "grape", "berry", "梨", "桃"]),
    ("tofu",      ["豆", "豆腐", "tofu", "豆浆", "豆干", "soy"]),
    ("coffee",    ["咖啡", "coffee", "茶", "tea"]),
    ("nut",       ["坚果", "nut", "花生", "杏仁", "核桃", "腰果"]),
    ("dumpling",  ["饺", "dumpling", "馄饨", "抄手", "粽"]),
]


def match_food_icon(food_name: str) -> str:
    """Match a food name to the best SVG icon key."""
    name_lower = food_name.lower()
    for icon_key, keywords in FOOD_KEYWORDS:
        for kw in keywords:
            if kw in name_lower:
                return icon_key
    return "default"


def esc(text: str) -> str:
    return html_mod.escape(str(text))


def format_date_zh(date_str: str) -> str:
    from datetime import date
    WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    try:
        d = date.fromisoformat(date_str)
        return f"{d.year}年{d.month}月{d.day}日 {WEEKDAYS[d.weekday()]}"
    except (ValueError, IndexError):
        return date_str


def format_date_en(date_str: str) -> str:
    from datetime import date
    try:
        d = date.fromisoformat(date_str)
        return d.strftime("%a, %b %-d, %Y")
    except (ValueError, AttributeError):
        return date_str


def aggregate_meals(meals: list) -> dict:
    """Group meals by meal_type and calculate totals."""
    grouped = {}
    totals = {"calories": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0}

    for meal in meals:
        mt = meal.get("meal_type", meal.get("name", "snack"))
        if mt not in grouped:
            grouped[mt] = {"foods": [], "calories": 0}

        foods = meal.get("foods", [])
        if not foods:
            foods = [meal]

        for food in foods:
            cal = food.get("calories", food.get("cal", 0))
            grouped[mt]["foods"].append({
                "name": food.get("name", ""),
                "amount_g": food.get("amount_g", 0),
                "calories": cal,
            })
            grouped[mt]["calories"] += cal

        totals["calories"] += meal.get("calories", meal.get("cal", 0))
        totals["protein_g"] += meal.get("protein_g", meal.get("protein", meal.get("p", 0)))
        totals["carbs_g"] += meal.get("carbs_g", meal.get("carbs", meal.get("c", 0)))
        totals["fat_g"] += meal.get("fat_g", meal.get("fat", meal.get("f", 0)))

    return {"grouped": grouped, "totals": totals}


def build_meal_sections(grouped: dict, lang: str, cal_unit: str) -> str:
    """Generate HTML for all meal sections in vintage style."""
    labels = MEAL_LABELS_ZH if lang == "zh" else MEAL_LABELS_EN
    sections = []

    sorted_meals = sorted(grouped.items(), key=lambda x: MEAL_ORDER.get(x[0], 99))

    for meal_type, data in sorted_meals:
        label = labels.get(meal_type, meal_type.replace("_", " ").title())
        time_class, deco = MEAL_DECO.get(meal_type, ("snack", "~"))
        meal_cal = data["calories"]

        # Build food icon grid
        food_icons = []
        for food in data["foods"]:
            icon_key = match_food_icon(food["name"])
            svg = FOOD_SVGS.get(icon_key, FOOD_SVGS["default"])
            food_icons.append(
                f'        <div class="food-icon-item">'
                f'<div class="food-svg">{svg}</div>'
                f'<div class="food-label">{esc(food["name"])}</div>'
                f'</div>'
            )

        # Build food detail list
        food_details = []
        for food in data["foods"]:
            amt = f'~{food["amount_g"]}g' if food["amount_g"] else ""
            food_details.append(
                f'        <tr>'
                f'<td class="fd-name">{esc(food["name"])}</td>'
                f'<td class="fd-amt">{esc(amt)}</td>'
                f'<td class="fd-cal">{food["calories"]}</td>'
                f'</tr>'
            )

        section = f"""  <div class="meal-section {time_class}">
    <div class="meal-header">
      <span class="meal-name">{esc(label)}</span>
      <span class="meal-deco">{deco}</span>
      <span class="meal-kcal">{meal_cal} {esc(cal_unit)}</span>
    </div>
    <div class="food-icons-row">
{chr(10).join(food_icons)}
    </div>
    <table class="food-detail">
{chr(10).join(food_details)}
    </table>
  </div>"""
        sections.append(section)

    return "\n\n".join(sections)


def build_summary(totals: dict, cal_target: int, lang: str, cal_unit: str) -> str:
    """Generate the bottom summary section."""
    cal = round(totals["calories"])
    p = round(totals["protein_g"])
    c = round(totals["carbs_g"])
    f = round(totals["fat_g"])

    summary_label = "今日小结" if lang == "zh" else "Daily Summary"
    p_label = "蛋白" if lang == "zh" else "P"
    c_label = "碳水" if lang == "zh" else "C"
    f_label = "脂肪" if lang == "zh" else "F"

    progress_html = ""
    if cal_target > 0:
        pct = min(round(cal / cal_target * 100), 120)
        bar_w = min(pct, 100)
        if cal > cal_target * 1.05:
            cls = "over"
            note = f"超出 {cal - cal_target}" if lang == "zh" else f"Over by {cal - cal_target}"
        elif cal < cal_target * 0.9:
            cls = "under"
            note = f"还剩 {cal_target - cal}" if lang == "zh" else f"{cal_target - cal} left"
        else:
            cls = "ok"
            note = "达标 ✓" if lang == "zh" else "On target ✓"

        target_word = "目标" if lang == "zh" else "Target"
        progress_html = f"""    <div class="progress-row">
      <div class="progress-track"><div class="progress-fill {cls}" style="width:{bar_w}%"></div></div>
      <div class="progress-note">{pct}% · {esc(note)} ({target_word} {cal_target})</div>
    </div>"""

    return f"""  <div class="summary-section">
    <div class="summary-title">— {esc(summary_label)} —</div>
    <div class="summary-macros">
      <span class="macro-item cal">{cal} <small>{esc(cal_unit)}</small></span>
      <span class="macro-sep">·</span>
      <span class="macro-item">{p_label} {p}g</span>
      <span class="macro-sep">·</span>
      <span class="macro-item">{c_label} {c}g</span>
      <span class="macro-sep">·</span>
      <span class="macro-item">{f_label} {f}g</span>
    </div>
{progress_html}
  </div>"""


def generate_html(meals_data: dict, cal_target: int, user_name: str,
                  lang: str, cal_unit: str) -> str:
    """Generate the complete vintage-style HTML card."""
    template = TEMPLATE_PATH.read_text(encoding="utf-8")

    date_str = meals_data.get("date", "")
    meals = meals_data.get("meals", [])
    agg = aggregate_meals(meals)

    date_display = format_date_zh(date_str) if lang == "zh" else format_date_en(date_str)
    title = "今日饮食手账" if lang == "zh" else "Daily Food Journal"
    footer = "AI 营养师手账 · 仅供参考" if lang == "zh" else "AI Nutritionist Journal · For reference only"

    meal_sections = build_meal_sections(agg["grouped"], lang, cal_unit)
    summary = build_summary(agg["totals"], cal_target, lang, cal_unit)

    replacements = {
        "{{LANG}}": lang,
        "{{TITLE}}": esc(title),
        "{{DATE_DISPLAY}}": esc(date_display),
        "{{USER_NAME}}": esc(user_name) if user_name else "",
        "{{MEAL_SECTIONS}}": meal_sections,
        "{{SUMMARY_SECTION}}": summary,
        "{{FOOTER_TEXT}}": esc(footer),
    }

    result = template
    for placeholder, value in replacements.items():
        result = result.replace(placeholder, value)
    return result


def main():
    parser = argparse.ArgumentParser(description="Generate vintage-style daily diet card")
    parser.add_argument("--meals-json", type=str, default=None)
    parser.add_argument("--cal-target", type=int, default=0)
    parser.add_argument("--user-name", type=str, default="")
    parser.add_argument("--lang", type=str, default="zh", choices=["zh", "en"])
    parser.add_argument("--cal-unit", type=str, default="kcal")
    parser.add_argument("--output", type=str, default=None)
    args = parser.parse_args()

    if args.meals_json:
        meals_data = json.loads(args.meals_json)
    elif not sys.stdin.isatty():
        meals_data = json.load(sys.stdin)
    else:
        print("Error: provide --meals-json or pipe JSON via stdin", file=sys.stderr)
        sys.exit(1)

    html_output = generate_html(
        meals_data=meals_data,
        cal_target=args.cal_target,
        user_name=args.user_name,
        lang=args.lang,
        cal_unit=args.cal_unit,
    )

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html_output, encoding="utf-8")
        print(f"Written to {args.output}", file=sys.stderr)
    else:
        print(html_output)


if __name__ == "__main__":
    main()
