#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
generate-daily-diet-html.py — Generate a shareable daily diet card as HTML.

Reads meal data from nutrition-calc.py's load command output (JSON via stdin
or --meals-json) and produces a styled, self-contained HTML card.

Usage:
  python3 generate-daily-diet-html.py \
    --meals-json '<load output JSON>' \
    [--cal-target 1600] \
    [--user-name "Name"] \
    [--lang zh] \
    [--cal-unit kcal] \
    [--output /path/to/output.html]

Or pipe from nutrition-calc.py:
  python3 nutrition-calc.py load --data-dir ... | \
  python3 generate-daily-diet-html.py --cal-target 1600 --output card.html
"""

import argparse
import html as html_mod
import json
import os
import re
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
TEMPLATE_PATH = SCRIPT_DIR.parent / "templates" / "daily-diet.html"

# Meal type display names and sort order
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

MEAL_ICONS = {
    "breakfast": "\U0001F305", "snack_am": "\U0001F34E", "lunch": "\u2600\uFE0F",
    "snack_pm": "\U0001F36A", "dinner": "\U0001F319", "snack": "\U0001F36C",
}


def esc(text: str) -> str:
    return html_mod.escape(str(text))


def format_date_zh(date_str: str) -> str:
    """Format YYYY-MM-DD to Chinese display like '2026年4月3日 周五'."""
    from datetime import date
    WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    try:
        d = date.fromisoformat(date_str)
        return f"{d.year}年{d.month}月{d.day}日 {WEEKDAYS[d.weekday()]}"
    except (ValueError, IndexError):
        return date_str


def format_date_en(date_str: str) -> str:
    """Format YYYY-MM-DD to English display like 'Fri, Apr 3, 2026'."""
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
            # Meal itself is a single food item
            foods = [meal]

        for food in foods:
            cal = food.get("calories", food.get("cal", 0))
            grouped[mt]["foods"].append({
                "name": food.get("name", ""),
                "amount_g": food.get("amount_g", 0),
                "calories": cal,
            })
            grouped[mt]["calories"] += cal

        meal_cal = meal.get("calories", meal.get("cal", 0))
        meal_protein = meal.get("protein_g", meal.get("protein", meal.get("p", 0)))
        meal_carbs = meal.get("carbs_g", meal.get("carbs", meal.get("c", 0)))
        meal_fat = meal.get("fat_g", meal.get("fat", meal.get("f", 0)))

        totals["calories"] += meal_cal
        totals["protein_g"] += meal_protein
        totals["carbs_g"] += meal_carbs
        totals["fat_g"] += meal_fat

    return {"grouped": grouped, "totals": totals}


def build_meal_cards_html(grouped: dict, lang: str, cal_unit: str) -> str:
    """Generate HTML for all meal cards."""
    labels = MEAL_LABELS_ZH if lang == "zh" else MEAL_LABELS_EN
    cards = []

    sorted_meals = sorted(
        grouped.items(),
        key=lambda x: MEAL_ORDER.get(x[0], 99)
    )

    for meal_type, data in sorted_meals:
        icon = MEAL_ICONS.get(meal_type, "\U0001F37D\uFE0F")
        label = labels.get(meal_type, meal_type.replace("_", " ").title())
        meal_cal = data["calories"]

        foods_html = []
        for food in data["foods"]:
            amount = food["amount_g"]
            amount_str = f"~{amount}g" if amount else ""
            cal = food["calories"]
            foods_html.append(
                f'      <div class="food-item">'
                f'<span class="food-name">{esc(food["name"])}</span>'
                f'<span class="food-amount">{esc(amount_str)}</span>'
                f'<span class="food-cal">{cal} {esc(cal_unit)}</span>'
                f'</div>'
            )

        card = f"""  <div class="meal-card">
    <div class="meal-title">
      <span>{icon} {esc(label)}</span>
      <span class="meal-cal">{meal_cal} {esc(cal_unit)}</span>
    </div>
    <div class="meal-foods">
{chr(10).join(foods_html)}
    </div>
  </div>"""
        cards.append(card)

    return "\n\n".join(cards)


def build_progress_section(total_cal: int, cal_target: int, lang: str, cal_unit: str) -> str:
    """Generate the calorie progress bar section."""
    if cal_target <= 0:
        return ""

    pct = min(round(total_cal / cal_target * 100), 120)
    bar_width = min(pct, 100)

    if total_cal > cal_target * 1.05:
        fill_class = "over"
        if lang == "zh":
            status = f"超出目标 {total_cal - cal_target} {cal_unit}"
        else:
            status = f"Over target by {total_cal - cal_target} {cal_unit}"
    elif total_cal < cal_target * 0.9:
        fill_class = "under"
        remaining = cal_target - total_cal
        if lang == "zh":
            status = f"还可以吃 {remaining} {cal_unit}"
        else:
            status = f"{remaining} {cal_unit} remaining"
    else:
        fill_class = "ok"
        if lang == "zh":
            status = "达标"
        else:
            status = "On target"

    target_label = "目标" if lang == "zh" else "Target"
    intake_label = "已摄入" if lang == "zh" else "Intake"

    return f"""  <div class="calorie-progress">
    <div class="label-row">
      <span>{intake_label}: {total_cal} {esc(cal_unit)}</span>
      <span>{target_label}: {cal_target} {esc(cal_unit)}</span>
    </div>
    <div class="progress-bar">
      <div class="progress-bar-fill {fill_class}" style="width: {bar_width}%"></div>
    </div>
    <div class="calorie-status">{esc(status)}</div>
  </div>"""


def generate_html(meals_data: dict, cal_target: int, user_name: str,
                  lang: str, cal_unit: str) -> str:
    """Generate the complete HTML card."""
    template = TEMPLATE_PATH.read_text(encoding="utf-8")

    date_str = meals_data.get("date", "")
    meals = meals_data.get("meals", [])
    agg = aggregate_meals(meals)
    totals = agg["totals"]
    grouped = agg["grouped"]

    # Date display
    date_display = format_date_zh(date_str) if lang == "zh" else format_date_en(date_str)

    # Title
    title = "今日饮食记录" if lang == "zh" else "Daily Diet Record"

    # Calorie status class
    if cal_target > 0:
        if totals["calories"] > cal_target * 1.05:
            cal_status = "over"
        elif totals["calories"] < cal_target * 0.9:
            cal_status = "under"
        else:
            cal_status = "ok"
    else:
        cal_status = ""

    # Labels
    if lang == "zh":
        protein_label = "蛋白质/g"
        carbs_label = "碳水/g"
        fat_label = "脂肪/g"
        footer = "AI 营养师生成 · 仅供参考"
    else:
        protein_label = "Protein/g"
        carbs_label = "Carbs/g"
        fat_label = "Fat/g"
        footer = "Generated by AI Nutritionist · For reference only"

    # Build sections
    meal_cards = build_meal_cards_html(grouped, lang, cal_unit)
    progress_section = build_progress_section(
        totals["calories"], cal_target, lang, cal_unit
    ) if cal_target > 0 else ""

    # Replace placeholders
    replacements = {
        "{{LANG}}": lang,
        "{{TITLE}}": esc(title),
        "{{DATE_DISPLAY}}": esc(date_display),
        "{{USER_NAME}}": esc(user_name) if user_name else "",
        "{{TOTAL_CAL}}": str(round(totals["calories"])),
        "{{CAL_UNIT}}": esc(cal_unit),
        "{{CAL_STATUS}}": cal_status,
        "{{TOTAL_PROTEIN}}": str(round(totals["protein_g"])),
        "{{PROTEIN_LABEL}}": esc(protein_label),
        "{{TOTAL_CARBS}}": str(round(totals["carbs_g"])),
        "{{CARBS_LABEL}}": esc(carbs_label),
        "{{TOTAL_FAT}}": str(round(totals["fat_g"])),
        "{{FAT_LABEL}}": esc(fat_label),
        "{{CALORIE_PROGRESS_SECTION}}": progress_section,
        "{{MEAL_CARDS}}": meal_cards,
        "{{FOOTER_TEXT}}": esc(footer),
    }

    result = template
    for placeholder, value in replacements.items():
        result = result.replace(placeholder, value)

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Generate a shareable daily diet card as HTML"
    )
    parser.add_argument("--meals-json", type=str, default=None,
                        help="JSON string from nutrition-calc.py load output")
    parser.add_argument("--cal-target", type=int, default=0,
                        help="Daily calorie target in kcal (0 = no target)")
    parser.add_argument("--user-name", type=str, default="",
                        help="User display name")
    parser.add_argument("--lang", type=str, default="zh", choices=["zh", "en"],
                        help="Language for labels (default: zh)")
    parser.add_argument("--cal-unit", type=str, default="kcal",
                        help="Calorie display unit (kcal or Cal)")
    parser.add_argument("--output", type=str, default=None,
                        help="Output HTML file path (default: stdout)")

    args = parser.parse_args()

    # Read meals data from --meals-json or stdin
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
