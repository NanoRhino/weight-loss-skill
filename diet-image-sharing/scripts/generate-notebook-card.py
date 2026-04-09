#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
generate-notebook-card.py — Generate a Japanese recipe-notebook style diet card.

Produces a hand-drawn notebook-paper card with watercolor-style SVG food
illustrations, masking tape decorations, and checkbox ingredient lists.

Usage:
  python3 generate-notebook-card.py \
    --meals-json '<load output JSON>' \
    [--cal-target 1600] [--user-name "Name"] \
    [--lang zh] [--cal-unit kcal] [--output card.html]
"""

import argparse
import html as html_mod
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
TEMPLATE_PATH = SCRIPT_DIR.parent / "templates" / "daily-diet-notebook.html"

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
TAPE_COLORS = ["tape-yellow", "tape-green", "tape-pink", "tape-blue"]

# ---------------------------------------------------------------------------
# Watercolor-style SVG food icons (colored fills, hand-drawn strokes)
# 56x56 viewBox
# ---------------------------------------------------------------------------
_sk = '#6b5230'  # stroke color (dark brown)

FOOD_SVGS = {
    "rice": (
        f'<svg viewBox="0 0 56 56" width="56" height="56">'
        f'<path d="M12 28c0 10 8 16 16 16s16-6 16-16" fill="#f5f0e0" stroke="{_sk}" stroke-width="2" stroke-linecap="round"/>'
        f'<path d="M10 28h36" stroke="{_sk}" stroke-width="2" stroke-linecap="round"/>'
        f'<ellipse cx="22" cy="24" rx="3" ry="2" fill="#fff" stroke="{_sk}" stroke-width="1"/>'
        f'<ellipse cx="30" cy="23" rx="3" ry="2" fill="#fff" stroke="{_sk}" stroke-width="1"/>'
        f'<ellipse cx="26" cy="19" rx="3" ry="2" fill="#fff" stroke="{_sk}" stroke-width="1"/>'
        f'<ellipse cx="20" cy="19" rx="2.5" ry="1.8" fill="#fff" stroke="{_sk}" stroke-width="1"/>'
        f'<ellipse cx="32" cy="19" rx="2.5" ry="1.8" fill="#fff" stroke="{_sk}" stroke-width="1"/>'
        f'</svg>'
    ),
    "noodles": (
        f'<svg viewBox="0 0 56 56" width="56" height="56">'
        f'<path d="M11 30c0 9 7 14 17 14s17-5 17-14" fill="#f5edd8" stroke="{_sk}" stroke-width="2" stroke-linecap="round"/>'
        f'<path d="M9 30h38" stroke="{_sk}" stroke-width="2" stroke-linecap="round"/>'
        f'<path d="M18 26c1-5 0-10-2-14" fill="none" stroke="#d4a840" stroke-width="2" stroke-linecap="round"/>'
        f'<path d="M26 26c1-5 0-10-2-14" fill="none" stroke="#d4a840" stroke-width="2" stroke-linecap="round"/>'
        f'<path d="M34 26c1-5 0-10-2-14" fill="none" stroke="#d4a840" stroke-width="2" stroke-linecap="round"/>'
        f'<circle cx="38" cy="22" r="4" fill="#e87050" stroke="{_sk}" stroke-width="1"/>'
        f'</svg>'
    ),
    "bread": (
        f'<svg viewBox="0 0 56 56" width="56" height="56">'
        f'<path d="M10 34c0-14 8-22 18-22s18 8 18 22v4H10z" fill="#e8c878" stroke="{_sk}" stroke-width="2" stroke-linecap="round"/>'
        f'<path d="M10 34h36" stroke="{_sk}" stroke-width="1.5" stroke-linecap="round" stroke-dasharray="3 2"/>'
        f'<path d="M19 24v10" stroke="{_sk}" stroke-width="1" stroke-linecap="round" opacity="0.4"/>'
        f'<path d="M28 22v12" stroke="{_sk}" stroke-width="1" stroke-linecap="round" opacity="0.4"/>'
        f'<path d="M37 24v10" stroke="{_sk}" stroke-width="1" stroke-linecap="round" opacity="0.4"/>'
        f'</svg>'
    ),
    "egg": (
        f'<svg viewBox="0 0 56 56" width="56" height="56">'
        f'<ellipse cx="28" cy="30" rx="14" ry="16" fill="#faf0d8" stroke="{_sk}" stroke-width="2"/>'
        f'<ellipse cx="28" cy="32" rx="8" ry="7" fill="#f8d84c" stroke="{_sk}" stroke-width="1.5"/>'
        f'<ellipse cx="26" cy="30" rx="3" ry="2.5" fill="#fae070" opacity="0.6"/>'
        f'</svg>'
    ),
    "meat": (
        f'<svg viewBox="0 0 56 56" width="56" height="56">'
        f'<path d="M16 12c-5 3-8 8-6 14 2 8 10 14 18 16s14-2 16-8c1-5-2-10-7-14" fill="#e8a070" stroke="{_sk}" stroke-width="2" stroke-linecap="round"/>'
        f'<path d="M20 20c2 3 6 5 10 6" fill="none" stroke="{_sk}" stroke-width="1" opacity="0.4"/>'
        f'<path d="M18 26c3 2 7 4 12 4" fill="none" stroke="{_sk}" stroke-width="1" opacity="0.4"/>'
        f'<path d="M28 42v7" stroke="{_sk}" stroke-width="2.5" stroke-linecap="round"/>'
        f'<circle cx="28" cy="51" r="2.5" fill="{_sk}"/>'
        f'</svg>'
    ),
    "fish": (
        f'<svg viewBox="0 0 56 56" width="56" height="56">'
        f'<path d="M8 28c5-10 15-15 24-13 5 1 10 5 13 13-3 8-8 12-13 13-9 2-19-3-24-13z" fill="#90c0d8" stroke="{_sk}" stroke-width="2" stroke-linecap="round"/>'
        f'<circle cx="38" cy="24" r="2.5" fill="#fff" stroke="{_sk}" stroke-width="1.5"/>'
        f'<circle cx="38" cy="24" r="1" fill="{_sk}"/>'
        f'<path d="M4 20c4 3 4 8 4 8s0 5-4 8" fill="#90c0d8" stroke="{_sk}" stroke-width="2" stroke-linecap="round"/>'
        f'<path d="M18 22c4 2 8 6 12 6" fill="none" stroke="{_sk}" stroke-width="1" opacity="0.3"/>'
        f'<path d="M16 28c5 1 10 4 14 4" fill="none" stroke="{_sk}" stroke-width="1" opacity="0.3"/>'
        f'</svg>'
    ),
    "vegetable": (
        f'<svg viewBox="0 0 56 56" width="56" height="56">'
        f'<path d="M28 44v-18" stroke="#6a8a40" stroke-width="2.5" stroke-linecap="round"/>'
        f'<path d="M28 26c-8-2-14-10-11-18" fill="#88b858" stroke="#5a7a30" stroke-width="1.5" stroke-linecap="round"/>'
        f'<path d="M28 26c8-2 14-10 11-18" fill="#78a848" stroke="#5a7a30" stroke-width="1.5" stroke-linecap="round"/>'
        f'<path d="M28 32c-10 0-16-6-13-14" fill="#98c868" stroke="#5a7a30" stroke-width="1.5" stroke-linecap="round"/>'
        f'<path d="M28 32c10 0 16-6 13-14" fill="#88b858" stroke="#5a7a30" stroke-width="1.5" stroke-linecap="round"/>'
        f'<path d="M22 44h12" stroke="#6a8a40" stroke-width="2" stroke-linecap="round"/>'
        f'</svg>'
    ),
    "soup": (
        f'<svg viewBox="0 0 56 56" width="56" height="56">'
        f'<path d="M10 28c0 10 8 16 18 16s18-6 18-16" fill="#f8e8c8" stroke="{_sk}" stroke-width="2" stroke-linecap="round"/>'
        f'<path d="M8 28h40" stroke="{_sk}" stroke-width="2" stroke-linecap="round"/>'
        f'<circle cx="20" cy="32" r="3" fill="#e87050" stroke="{_sk}" stroke-width="1" opacity="0.7"/>'
        f'<circle cx="30" cy="34" r="2.5" fill="#88b858" stroke="{_sk}" stroke-width="1" opacity="0.7"/>'
        f'<path d="M18 24c0-4 1-6 0-10" stroke="#b8a880" stroke-width="1.5" stroke-linecap="round" opacity="0.5"/>'
        f'<path d="M28 23c0-4 1-6 0-10" stroke="#b8a880" stroke-width="1.5" stroke-linecap="round" opacity="0.5"/>'
        f'<path d="M38 24c0-4 1-6 0-10" stroke="#b8a880" stroke-width="1.5" stroke-linecap="round" opacity="0.5"/>'
        f'</svg>'
    ),
    "milk": (
        f'<svg viewBox="0 0 56 56" width="56" height="56">'
        f'<rect x="15" y="16" width="26" height="30" rx="3" fill="#f5f0e8" stroke="{_sk}" stroke-width="2"/>'
        f'<path d="M20 16v-5h16v5" stroke="{_sk}" stroke-width="2" fill="#f5f0e8" stroke-linecap="round"/>'
        f'<rect x="15" y="28" width="26" height="18" rx="3" fill="#d0e8f0" stroke="none"/>'
        f'<path d="M15 28h26" stroke="{_sk}" stroke-width="1" stroke-dasharray="2 2"/>'
        f'<text x="28" y="40" text-anchor="middle" font-size="8" fill="{_sk}" font-weight="600">MILK</text>'
        f'</svg>'
    ),
    "fruit": (
        f'<svg viewBox="0 0 56 56" width="56" height="56">'
        f'<path d="M28 14c-10 0-17 8-17 16s7 15 17 15 17-7 17-15-7-16-17-16z" fill="#e85050" stroke="{_sk}" stroke-width="2"/>'
        f'<path d="M28 14c-1-5 2-8 5-11" stroke="#5a7a30" stroke-width="2" stroke-linecap="round"/>'
        f'<path d="M30 12c3 0 6-1 8-4" fill="#88b858" stroke="#5a7a30" stroke-width="1.5" stroke-linecap="round"/>'
        f'<ellipse cx="24" cy="24" rx="4" ry="3" fill="#f07070" opacity="0.5"/>'
        f'</svg>'
    ),
    "tofu": (
        f'<svg viewBox="0 0 56 56" width="56" height="56">'
        f'<rect x="12" y="16" width="32" height="24" rx="3" fill="#f8f0d8" stroke="{_sk}" stroke-width="2"/>'
        f'<path d="M12 28h32" stroke="{_sk}" stroke-width="1" stroke-dasharray="3 2"/>'
        f'<path d="M28 16v24" stroke="{_sk}" stroke-width="1" stroke-dasharray="3 2"/>'
        f'<circle cx="20" cy="22" r="1" fill="{_sk}" opacity="0.2"/>'
        f'<circle cx="36" cy="34" r="1.2" fill="{_sk}" opacity="0.2"/>'
        f'</svg>'
    ),
    "coffee": (
        f'<svg viewBox="0 0 56 56" width="56" height="56">'
        f'<path d="M12 22h24v16c0 5-5 8-12 8s-12-3-12-8z" fill="#f5edd8" stroke="{_sk}" stroke-width="2" stroke-linecap="round"/>'
        f'<path d="M36 26c5 0 8 3 8 6s-3 6-8 6" fill="none" stroke="{_sk}" stroke-width="2" stroke-linecap="round"/>'
        f'<path d="M20 18c1-3 0-6-1-9" stroke="#b8a880" stroke-width="1.5" stroke-linecap="round" opacity="0.5"/>'
        f'<path d="M28 17c1-3 0-6-1-9" stroke="#b8a880" stroke-width="1.5" stroke-linecap="round" opacity="0.5"/>'
        f'<ellipse cx="24" cy="30" rx="8" ry="3" fill="#c8a060" opacity="0.3"/>'
        f'</svg>'
    ),
    "nut": (
        f'<svg viewBox="0 0 56 56" width="56" height="56">'
        f'<ellipse cx="28" cy="30" rx="15" ry="11" fill="#d4a050" stroke="{_sk}" stroke-width="2"/>'
        f'<path d="M28 19v22" stroke="{_sk}" stroke-width="1.5" stroke-linecap="round"/>'
        f'<path d="M16 25c5 3 10 3 12 6" fill="none" stroke="{_sk}" stroke-width="1" opacity="0.4"/>'
        f'<path d="M40 25c-5 3-10 3-12 6" fill="none" stroke="{_sk}" stroke-width="1" opacity="0.4"/>'
        f'</svg>'
    ),
    "dumpling": (
        f'<svg viewBox="0 0 56 56" width="56" height="56">'
        f'<path d="M8 30c0-8 8-16 20-16s20 8 20 16" fill="#f5edd8" stroke="{_sk}" stroke-width="2" stroke-linecap="round"/>'
        f'<path d="M8 30h40" stroke="{_sk}" stroke-width="2" stroke-linecap="round"/>'
        f'<path d="M14 26c3-2 6-3 14-3s11 1 14 3" fill="none" stroke="{_sk}" stroke-width="1.5" stroke-dasharray="2 3" stroke-linecap="round"/>'
        f'</svg>'
    ),
    "default": (
        f'<svg viewBox="0 0 56 56" width="56" height="56">'
        f'<circle cx="28" cy="28" r="18" fill="#f5edd8" stroke="{_sk}" stroke-width="2"/>'
        f'<circle cx="28" cy="28" r="12" fill="none" stroke="{_sk}" stroke-width="1" stroke-dasharray="3 2"/>'
        f'<path d="M22 28h12" stroke="{_sk}" stroke-width="1.5" stroke-linecap="round"/>'
        f'<path d="M28 22v12" stroke="{_sk}" stroke-width="1.5" stroke-linecap="round"/>'
        f'</svg>'
    ),
}

FOOD_KEYWORDS = [
    ("rice",      ["米饭", "糙米", "白米", "rice", "饭"]),
    ("noodles",   ["面", "面条", "荞麦面", "意面", "粉", "noodle", "pasta", "拉面", "米粉", "河粉", "粿条"]),
    ("bread",     ["面包", "吐司", "toast", "bread", "馒头", "包子", "饼", "烧饼"]),
    ("egg",       ["蛋", "鸡蛋", "egg", "蛋花"]),
    ("meat",      ["鸡", "chicken", "肉", "beef", "牛肉", "猪", "pork", "羊", "鸭", "排骨"]),
    ("fish",      ["鱼", "fish", "虾", "shrimp", "海鲜", "三文鱼", "蟹"]),
    ("vegetable", ["菜", "蔬", "西兰花", "broccoli", "青菜", "白菜", "菠菜", "生菜",
                   "黄瓜", "番茄", "胡萝卜", "芹菜", "茄子", "冬瓜", "南瓜"]),
    ("soup",      ["汤", "soup", "粥", "porridge", "羹"]),
    ("milk",      ["牛奶", "奶", "milk", "酸奶", "yogurt", "乳"]),
    ("fruit",     ["果", "apple", "苹果", "香蕉", "橙", "grape", "berry", "梨", "桃"]),
    ("tofu",      ["豆", "豆腐", "tofu", "豆浆", "豆干", "soy"]),
    ("coffee",    ["咖啡", "coffee", "茶", "tea"]),
    ("nut",       ["坚果", "nut", "花生", "杏仁", "核桃", "腰果"]),
    ("dumpling",  ["饺", "dumpling", "馄饨", "抄手", "粽"]),
]


def match_food_icon(name: str) -> str:
    n = name.lower()
    for key, kws in FOOD_KEYWORDS:
        for kw in kws:
            if kw in n:
                return key
    return "default"


def esc(t: str) -> str:
    return html_mod.escape(str(t))


def fmt_date(d: str, lang: str) -> str:
    from datetime import date as D
    WD = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    try:
        dd = D.fromisoformat(d)
        if lang == "zh":
            return f"{dd.year}年{dd.month}月{dd.day}日 {WD[dd.weekday()]}"
        return dd.strftime("%a, %b %-d, %Y")
    except Exception:
        return d


def aggregate(meals):
    grouped = {}
    totals = {"calories": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0}
    for m in meals:
        mt = m.get("meal_type", m.get("name", "snack"))
        if mt not in grouped:
            grouped[mt] = {"foods": [], "calories": 0}
        foods = m.get("foods", [m] if "name" in m else [])
        for f in foods:
            cal = f.get("calories", f.get("cal", 0))
            grouped[mt]["foods"].append({
                "name": f.get("name", ""),
                "amount_g": f.get("amount_g", 0),
                "calories": cal,
            })
            grouped[mt]["calories"] += cal
        totals["calories"] += m.get("calories", m.get("cal", 0))
        totals["protein_g"] += m.get("protein_g", m.get("protein", m.get("p", 0)))
        totals["carbs_g"] += m.get("carbs_g", m.get("carbs", m.get("c", 0)))
        totals["fat_g"] += m.get("fat_g", m.get("fat", m.get("f", 0)))
    return grouped, totals


def build_meals(grouped, lang, cal_unit):
    labels = MEAL_LABELS_ZH if lang == "zh" else MEAL_LABELS_EN
    parts = []
    sorted_m = sorted(grouped.items(), key=lambda x: MEAL_ORDER.get(x[0], 99))

    for i, (mt, data) in enumerate(sorted_m):
        tape = TAPE_COLORS[i % len(TAPE_COLORS)]
        label = labels.get(mt, mt.replace("_", " ").title())

        # Food illustrations
        icons = []
        for f in data["foods"]:
            k = match_food_icon(f["name"])
            svg = FOOD_SVGS.get(k, FOOD_SVGS["default"])
            icons.append(
                f'      <div class="food-illust-item">'
                f'<div class="fi-svg">{svg}</div>'
                f'<div class="fi-name">{esc(f["name"])}</div>'
                f'</div>'
            )

        # Ingredient checklist
        items = []
        for f in data["foods"]:
            amt = f'~{f["amount_g"]}g' if f["amount_g"] else ""
            items.append(
                f'      <li>'
                f'<span class="cb cb-checked"></span>'
                f'{esc(f["name"])}'
                f'<span class="ing-cal">{f["calories"]}</span>'
                f'<span class="ing-amt">{esc(amt)}</span>'
                f'</li>'
            )

        part = f"""  <div class="meal-card">
    <div class="tape {tape}"></div>
    <div class="meal-inner">
      <div class="meal-title-row">
        {esc(label)}
        <span class="meal-kcal-badge">{data["calories"]} {esc(cal_unit)}</span>
      </div>
      <div class="food-illust">
{chr(10).join(icons)}
      </div>
      <ul class="ingredient-list">
{chr(10).join(items)}
      </ul>
    </div>
  </div>"""
        parts.append(part)

    return "\n\n".join(parts)


def build_summary(totals, cal_target, lang, cal_unit):
    cal = round(totals["calories"])
    p, c, f = round(totals["protein_g"]), round(totals["carbs_g"]), round(totals["fat_g"])
    sl = "今日小结" if lang == "zh" else "DAILY SUMMARY"
    pl, cl, fl = ("蛋白", "碳水", "脂肪") if lang == "zh" else ("P", "C", "F")

    prog = ""
    if cal_target > 0:
        pct = min(round(cal / cal_target * 100), 120)
        bw = min(pct, 100)
        if cal > cal_target * 1.05:
            cls, note = "over", (f"超出 {cal - cal_target}" if lang == "zh" else f"Over by {cal - cal_target}")
        elif cal < cal_target * 0.9:
            cls, note = "under", (f"还剩 {cal_target - cal}" if lang == "zh" else f"{cal_target - cal} left")
        else:
            cls, note = "ok", ("达标 ✓" if lang == "zh" else "On target ✓")
        tgt = "目标" if lang == "zh" else "Target"
        prog = f"""    <div class="progress-row">
      <div class="progress-track"><div class="progress-fill {cls}" style="width:{bw}%"></div></div>
      <div class="progress-note">{pct}% · {esc(note)} ({tgt} {cal_target})</div>
    </div>"""

    return f"""  <div class="summary-card">
    <div class="summary-label">{esc(sl)}</div>
    <div class="summary-cal">{cal} <small>{esc(cal_unit)}</small></div>
    <div class="summary-macros">
      {pl} {p}g <span class="sep">·</span> {cl} {c}g <span class="sep">·</span> {fl} {f}g
    </div>
{prog}
  </div>"""


def generate(meals_data, cal_target, user_name, lang, cal_unit):
    tpl = TEMPLATE_PATH.read_text(encoding="utf-8")
    date_str = meals_data.get("date", "")
    meals = meals_data.get("meals", [])
    grouped, totals = aggregate(meals)

    reps = {
        "{{LANG}}": lang,
        "{{TITLE}}": esc("今日饮食手账" if lang == "zh" else "Daily Food Journal"),
        "{{DATE_DISPLAY}}": esc(fmt_date(date_str, lang)),
        "{{USER_NAME}}": esc(user_name) if user_name else "",
        "{{MEAL_SECTIONS}}": build_meals(grouped, lang, cal_unit),
        "{{SUMMARY_SECTION}}": build_summary(totals, cal_target, lang, cal_unit),
        "{{FOOTER_TEXT}}": esc("AI 营养师手账 · 仅供参考" if lang == "zh" else "AI Nutritionist · For reference only"),
    }
    r = tpl
    for k, v in reps.items():
        r = r.replace(k, v)
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--meals-json", type=str, default=None)
    ap.add_argument("--cal-target", type=int, default=0)
    ap.add_argument("--user-name", type=str, default="")
    ap.add_argument("--lang", type=str, default="zh", choices=["zh", "en"])
    ap.add_argument("--cal-unit", type=str, default="kcal")
    ap.add_argument("--output", type=str, default=None)
    a = ap.parse_args()

    if a.meals_json:
        d = json.loads(a.meals_json)
    elif not sys.stdin.isatty():
        d = json.load(sys.stdin)
    else:
        print("Error: provide --meals-json or pipe via stdin", file=sys.stderr)
        sys.exit(1)

    html = generate(d, a.cal_target, a.user_name, a.lang, a.cal_unit)
    if a.output:
        Path(a.output).parent.mkdir(parents=True, exist_ok=True)
        Path(a.output).write_text(html, encoding="utf-8")
        print(f"Written to {a.output}", file=sys.stderr)
    else:
        print(html)


if __name__ == "__main__":
    main()
