#!/usr/bin/env python3
"""
generate-meal-plan-html.py — Convert a structured Meal Plan Markdown file to styled HTML.

Parses the meal-plan-schema.md format and fills into the meal-plan HTML template.

Usage: python3 generate-meal-plan-html.py <input.md> [output.html]
"""

import sys
import os
import re
import html as html_module


def detect_lang(text):
    """Detect if text is primarily Chinese."""
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    return 'zh' if chinese_chars > 20 else 'en'


def parse_macros(macro_str):
    """Parse macro string like '1610 kcal · Protein 102g · Carbohydrate 178g · Fat 48g'.

    Supports both English and Chinese macro names.
    """
    result = {}
    cal_match = re.search(r'(\d[\d,]*)\s*kcal', macro_str)
    if cal_match:
        result['calories'] = cal_match.group(1)
    macro_patterns = {
        'protein': r'(?:Protein|蛋白质)\s*(\d+)\s*g',
        'carbohydrate': r'(?:Carbohydrate|碳水化合物|碳水)\s*(\d+)\s*g',
        'fat': r'(?:Fat|脂肪)\s*(\d+)\s*g',
    }
    for key, pattern in macro_patterns.items():
        m = re.search(pattern, macro_str)
        if m:
            result[key] = m.group(1)
    return result


def parse_metadata(lines):
    """Parse H1 metadata section."""
    meta = {}
    for line in lines:
        line = line.strip()
        if line.startswith('- '):
            line = line[2:]
        if ':' in line:
            key, val = line.split(':', 1)
            meta[key.strip().lower()] = val.strip()
    return meta


def escape(text):
    return html_module.escape(text)


def format_food_item(item_text):
    """Format a food list item, wrapping parenthesized portions in <span class='portion'>."""
    # Match trailing parenthesized content like (40g dry) or (240ml)
    pattern = r'\(([^)]+)\)\s*$'
    match = re.search(pattern, item_text)
    if match:
        before = item_text[:match.start()].rstrip()
        portion = match.group(0)
        return f'{escape(before)} <span class="portion">{escape(portion)}</span>'
    return escape(item_text)


def parse_meal_plan(md_text):
    """Parse the full meal plan Markdown into a structured dict."""
    lines = md_text.split('\n')
    plan = {
        'title': '',
        'metadata': {},
        'days': [],
        'grocery': None,
    }

    current_day = None
    current_meal = None
    metadata_lines = []
    in_metadata = False
    in_grocery = False
    grocery_categories = []
    current_grocery_cat = None

    for line in lines:
        stripped = line.strip()

        # H1 — Plan title
        if stripped.startswith('# ') and not stripped.startswith('## '):
            plan['title'] = stripped[2:].strip()
            in_metadata = True
            continue

        # Grocery section
        if re.match(r'^##\s+Grocery\s+List', stripped, re.IGNORECASE) or \
           re.match(r'^##\s+采购清单', stripped):
            in_grocery = True
            in_metadata = False
            if current_meal and current_day:
                current_day['meals'].append(current_meal)
                current_meal = None
            if current_day:
                plan['days'].append(current_day)
                current_day = None
            continue

        if in_grocery:
            if stripped.startswith('### '):
                if current_grocery_cat:
                    grocery_categories.append(current_grocery_cat)
                current_grocery_cat = {'name': stripped[4:].strip(), 'items': []}
            elif stripped.startswith('- ') and current_grocery_cat:
                current_grocery_cat['items'].append(stripped[2:].strip())
            continue

        # H2 — Day header
        if stripped.startswith('## '):
            in_metadata = False
            if metadata_lines:
                plan['metadata'] = parse_metadata(metadata_lines)
                metadata_lines = []

            if current_meal and current_day:
                current_day['meals'].append(current_meal)
                current_meal = None
            if current_day:
                plan['days'].append(current_day)

            day_text = stripped[3:].strip()
            # Parse: Day N | DayName | macros
            parts = [p.strip() for p in day_text.split('|')]
            day_name = parts[1] if len(parts) > 1 else parts[0]
            day_macros_str = parts[2] if len(parts) > 2 else ''
            day_macros = parse_macros(day_macros_str)

            current_day = {
                'name': day_name,
                'macros_str': day_macros_str,
                'macros': day_macros,
                'meals': [],
            }
            continue

        # H3 — Meal header
        if stripped.startswith('### ') and current_day is not None:
            if current_meal:
                current_day['meals'].append(current_meal)

            meal_text = stripped[4:].strip()
            # Parse: Emoji MealName [Tag]? | macros
            pipe_parts = [p.strip() for p in meal_text.split('|')]
            meal_name_part = pipe_parts[0]
            meal_macros_str = pipe_parts[1] if len(pipe_parts) > 1 else ''
            meal_macros = parse_macros(meal_macros_str)

            # Extract tag like [Takeout]
            tag_match = re.search(r'\[([^\]]+)\]', meal_name_part)
            tag = tag_match.group(1) if tag_match else None
            meal_name = re.sub(r'\s*\[[^\]]+\]', '', meal_name_part).strip()

            current_meal = {
                'name': meal_name,
                'tag': tag,
                'macros_str': meal_macros_str,
                'macros': meal_macros,
                'dish_summary': None,
                'foods': [],
                'tip': None,
            }
            continue

        # Metadata lines (between H1 and first H2)
        if in_metadata and stripped.startswith('- '):
            metadata_lines.append(stripped)
            continue

        if current_meal is not None:
            # Blockquote — dish summary / order info
            if stripped.startswith('> '):
                current_meal['dish_summary'] = stripped[2:].strip()
                continue

            # Food list item
            if stripped.startswith('- '):
                current_meal['foods'].append(stripped[2:].strip())
                continue

            # Tip line
            if stripped.startswith('💡'):
                current_meal['tip'] = stripped[1:].strip().lstrip(' ')
                continue

    # Flush remaining
    if current_meal and current_day:
        current_day['meals'].append(current_meal)
    if current_day:
        plan['days'].append(current_day)
    if metadata_lines and not plan['metadata']:
        plan['metadata'] = parse_metadata(metadata_lines)
    if current_grocery_cat:
        grocery_categories.append(current_grocery_cat)
    if grocery_categories:
        plan['grocery'] = grocery_categories

    return plan


def render_html(plan, lang='en'):
    """Render parsed plan into full HTML."""
    meta = plan['metadata']
    date_str = meta.get('date', '')
    cal_str = meta.get('calories', '')
    mode_str = meta.get('mode', '')
    macros_str = meta.get('macros', '')

    # Build days HTML
    days_html = []
    for day in plan['days']:
        meals_html = []
        for meal in day['meals']:
            eating_out_class = ' eating-out' if meal['tag'] else ''
            tag_html = f' <span class="tag">{escape(meal["tag"])}</span>' if meal['tag'] else ''

            # Dish summary or order info
            summary_html = ''
            if meal['dish_summary']:
                css_class = 'order-info' if meal['tag'] else 'dish-summary'
                summary_html = f'        <p class="{css_class}">{escape(meal["dish_summary"])}</p>\n'

            # Food list
            food_items = '\n'.join(
                f'          <li>{format_food_item(f)}</li>'
                for f in meal['foods']
            )
            food_html = f'        <ul class="food-list">\n{food_items}\n        </ul>\n' if meal['foods'] else ''

            # Tip
            tip_html = ''
            if meal['tip']:
                tip_html = f'        <p class="meal-tip">💡 {escape(meal["tip"])}</p>\n'

            meals_html.append(f"""      <div class="meal-block{eating_out_class}">
        <div class="meal-title">
          <h3>{escape(meal['name'])}{tag_html}</h3>
          <span class="meal-macros">{escape(meal['macros_str'])}</span>
        </div>
{summary_html}{food_html}{tip_html}      </div>""")

        day_block = f"""  <div class="day-card">
    <div class="day-header">
      <h2>{escape(day['name'])}</h2>
      <span class="day-macros">{escape(day['macros_str'])}</span>
    </div>
    <div class="day-body">
{chr(10).join(meals_html)}
    </div>
  </div>"""
        days_html.append(day_block)

    # Grocery section
    grocery_html = ''
    if plan['grocery']:
        cats_html = []
        for cat in plan['grocery']:
            items = '\n'.join(f'      <li>{escape(i)}</li>' for i in cat['items'])
            cats_html.append(f"""    <div class="grocery-category">
      <h3>{escape(cat['name'])}</h3>
      <ul>
{items}
      </ul>
    </div>""")
        grocery_html = f"""
  <div class="grocery-section">
    <h2>{"🛒 采购清单" if lang == "zh" else "🛒 Grocery List"}</h2>
{chr(10).join(cats_html)}
  </div>"""

    # Footer text
    footer_text = 'Generated by AI Nutrition Coach · For reference only — consult a dietitian for medical dietary needs'
    if lang == 'zh':
        footer_text = 'AI 营养师生成 · 仅供参考，如有医学饮食需求请咨询专业营养师'

    return f"""<!DOCTYPE html>
<html lang="{lang}" dir="ltr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{escape(plan['title'])}</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html {{ font-size: 15px; -webkit-text-size-adjust: 100%; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                 "Helvetica Neue", Arial, "Noto Sans SC", "PingFang SC",
                 "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
    line-height: 1.6; color: #1a1a1a; background: #f5f5f0; padding: 0; margin: 0;
  }}
  .page {{ max-width: 800px; margin: 0 auto; padding: 2rem 1.5rem; }}
  .plan-header {{ text-align: center; margin-bottom: 2rem; padding-bottom: 1.5rem; border-bottom: 2px solid #e0ddd5; }}
  .plan-header h1 {{ font-size: 1.8rem; font-weight: 700; color: #2d5016; margin-bottom: 0.4rem; }}
  .plan-header .subtitle {{ font-size: 0.95rem; color: #666; }}
  .summary-card {{
    background: #fff; border: 1px solid #e0ddd5; border-radius: 12px;
    padding: 1.2rem 1.5rem; margin-bottom: 2rem;
    display: grid; grid-template-columns: 1fr 1fr; gap: 0.6rem 2rem;
  }}
  .summary-card .item {{ display: flex; gap: 0.5rem; font-size: 0.9rem; align-items: baseline; }}
  .summary-card .label {{ color: #888; white-space: nowrap; }}
  .summary-card .value {{ font-weight: 600; color: #333; }}
  .summary-card .full-width {{ grid-column: 1 / -1; }}
  .day-card {{ background: #fff; border: 1px solid #e0ddd5; border-radius: 12px; margin-bottom: 1.5rem; overflow: hidden; }}
  .day-header {{
    background: #2d5016; color: #fff; padding: 0.8rem 1.2rem;
    display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.4rem;
  }}
  .day-header h2 {{ font-size: 1.15rem; font-weight: 600; margin: 0; }}
  .day-header .day-macros {{ font-size: 0.82rem; opacity: 0.9; font-weight: 400; }}
  .day-body {{ padding: 0.2rem 0; }}
  .meal-block {{ padding: 0.8rem 1.2rem; border-bottom: 1px solid #f0ede5; }}
  .meal-block:last-child {{ border-bottom: none; }}
  .meal-title {{ display: flex; justify-content: space-between; align-items: baseline; flex-wrap: wrap; gap: 0.3rem; margin-bottom: 0.3rem; }}
  .meal-title h3 {{ font-size: 1rem; font-weight: 600; color: #2d5016; margin: 0; }}
  .meal-title .meal-macros {{ font-size: 0.78rem; color: #888; white-space: nowrap; }}
  .meal-title .tag {{
    display: inline-block; font-size: 0.7rem; font-weight: 500;
    background: #fef3c7; color: #92400e; padding: 0.1rem 0.5rem;
    border-radius: 999px; margin-left: 0.4rem; vertical-align: middle;
  }}
  .dish-summary {{ font-size: 0.88rem; color: #555; margin-bottom: 0.4rem; font-style: italic; }}
  .food-list {{ list-style: none; padding: 0; margin: 0; }}
  .food-list li {{ font-size: 0.88rem; color: #444; padding: 0.15rem 0; padding-left: 1.2rem; position: relative; }}
  .food-list li::before {{ content: "·"; position: absolute; left: 0.3rem; color: #aaa; font-weight: 700; }}
  .food-list .portion {{ color: #888; }}
  .meal-tip {{ font-size: 0.82rem; color: #b45309; margin-top: 0.3rem; padding-left: 1.2rem; }}
  .meal-block.eating-out .order-info {{ font-size: 0.88rem; color: #444; padding-left: 1.2rem; margin-bottom: 0.2rem; }}
  .grocery-section {{ background: #fff; border: 1px solid #e0ddd5; border-radius: 12px; padding: 1.2rem 1.5rem; margin-top: 2rem; }}
  .grocery-section h2 {{ font-size: 1.15rem; font-weight: 600; color: #2d5016; margin-bottom: 0.8rem; }}
  .grocery-category h3 {{ font-size: 0.95rem; font-weight: 600; color: #555; margin: 0.8rem 0 0.3rem 0; padding-bottom: 0.2rem; border-bottom: 1px solid #f0ede5; }}
  .grocery-category ul {{ list-style: none; padding: 0; margin: 0; columns: 2; column-gap: 2rem; }}
  .grocery-category li {{ font-size: 0.88rem; color: #444; padding: 0.12rem 0; break-inside: avoid; }}
  .plan-footer {{ text-align: center; margin-top: 2rem; padding-top: 1rem; border-top: 1px solid #e0ddd5; font-size: 0.8rem; color: #aaa; }}
  @media (max-width: 600px) {{
    html {{ font-size: 14px; }}
    .page {{ padding: 1rem; }}
    .summary-card {{ grid-template-columns: 1fr; }}
    .day-header {{ flex-direction: column; align-items: flex-start; }}
    .meal-title {{ flex-direction: column; }}
    .grocery-category ul {{ columns: 1; }}
  }}
  @media print {{
    body {{ background: #fff; font-size: 11pt; }}
    .page {{ max-width: none; padding: 0; }}
    .day-card {{ break-inside: avoid; border: 1px solid #ccc; margin-bottom: 1rem; }}
    .day-header {{ background: #2d5016 !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
    .plan-footer {{ display: none; }}
  }}
</style>
</head>
<body>
<div class="page">
  <header class="plan-header">
    <h1>🍽️ {escape(plan['title'])}</h1>
    <p class="subtitle">{escape(date_str)}</p>
  </header>

  <div class="summary-card">
    <div class="item">
      <span class="label">{"每日目标:" if lang == "zh" else "Daily Target:"}</span>
      <span class="value">{escape(cal_str)}</span>
    </div>
    <div class="item">
      <span class="label">{"饮食模式:" if lang == "zh" else "Diet Mode:"}</span>
      <span class="value">{escape(mode_str)}</span>
    </div>
    <div class="item full-width">
      <span class="label">{"宏量素:" if lang == "zh" else "Macros:"}</span>
      <span class="value">{escape(macros_str)}</span>
    </div>
  </div>

{chr(10).join(days_html)}
{grocery_html}

  <footer class="plan-footer">
    {footer_text}
  </footer>
</div>
</body>
</html>"""


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 generate-meal-plan-html.py <input.md> [output.html]", file=sys.stderr)
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else input_path.rsplit('.', 1)[0] + '.html'

    if not os.path.isfile(input_path):
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    with open(input_path, 'r', encoding='utf-8') as f:
        md_text = f.read()

    lang = detect_lang(md_text)
    plan = parse_meal_plan(md_text)
    html_output = render_html(plan, lang=lang)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_output)

    print(f"HTML generated: {output_path}")


if __name__ == '__main__':
    main()
