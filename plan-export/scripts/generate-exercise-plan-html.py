#!/usr/bin/env python3
"""
generate-exercise-plan-html.py — Convert a structured Exercise Plan Markdown file to styled HTML.

Parses the exercise-plan-schema.md format and fills into the exercise-plan HTML template.

Usage: python3 generate-exercise-plan-html.py <input.md> [output.html]
"""

import sys
import os
import re
import html as html_module


def detect_lang(text):
    """Detect if text is primarily Chinese."""
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    return 'zh' if chinese_chars > 20 else 'en'


def escape(text):
    return html_module.escape(text)


def parse_metadata(lines):
    """Parse H1 metadata section (key: value list items)."""
    meta = {}
    for line in lines:
        line = line.strip()
        if line.startswith('- '):
            line = line[2:]
        if ':' in line:
            key, val = line.split(':', 1)
            meta[key.strip().lower()] = val.strip()
    return meta


def parse_weekly_overview(lines):
    """Parse a markdown table into list of {day, training} dicts."""
    rows = []
    for line in lines:
        line = line.strip()
        # Skip header row and separator
        if line.startswith('|') and '---' not in line:
            cells = [c.strip() for c in line.strip('|').split('|')]
            if len(cells) >= 2 and cells[0].lower() != 'day':
                rows.append({'day': cells[0], 'training': cells[1]})
    return rows


def is_rest_day(label):
    """Check if a day label indicates a rest day."""
    lower = label.lower()
    return 'rest' in lower or '休息' in lower


def parse_exercise_plan(md_text):
    """Parse the full exercise plan Markdown into a structured dict."""
    lines = md_text.split('\n')
    plan = {
        'title': '',
        'metadata': {},
        'weekly_overview': [],
        'days': [],
        'progression': [],
        'notes': [],
        'disclaimer': None,
    }

    metadata_lines = []
    in_metadata = False
    in_weekly_overview = False
    weekly_overview_lines = []

    current_day = None
    current_phase = None  # 'video', 'warmup', 'main', 'cooldown', 'rest'
    current_exercise = None

    in_progression = False
    in_notes = False
    in_disclaimer = False

    def flush_exercise():
        nonlocal current_exercise
        if current_exercise and current_day:
            if 'exercises' not in current_day:
                current_day['exercises'] = []
            current_day['exercises'].append(current_exercise)
            current_exercise = None

    def flush_day():
        nonlocal current_day, current_phase
        flush_exercise()
        if current_day:
            plan['days'].append(current_day)
            current_day = None
            current_phase = None

    for line in lines:
        stripped = line.strip()

        # H1 — Plan title
        if stripped.startswith('# ') and not stripped.startswith('## '):
            plan['title'] = stripped[2:].strip()
            in_metadata = True
            continue

        # H2 — Section headers
        if stripped.startswith('## ') and not stripped.startswith('### '):
            in_metadata = False
            in_weekly_overview = False
            in_progression = False
            in_notes = False
            in_disclaimer = False

            if metadata_lines:
                plan['metadata'] = parse_metadata(metadata_lines)
                metadata_lines = []
            if weekly_overview_lines:
                plan['weekly_overview'] = parse_weekly_overview(weekly_overview_lines)
                weekly_overview_lines = []

            h2_text = stripped[3:].strip()

            # Weekly Overview
            if re.match(r'weekly\s+overview', h2_text, re.IGNORECASE):
                flush_day()
                in_weekly_overview = True
                continue

            # Progression
            if re.match(r'progression', h2_text, re.IGNORECASE):
                flush_day()
                in_progression = True
                continue

            # Notes
            if re.match(r'notes', h2_text, re.IGNORECASE):
                flush_day()
                in_notes = True
                continue

            # Disclaimer
            if re.match(r'disclaimer', h2_text, re.IGNORECASE):
                flush_day()
                in_disclaimer = True
                continue

            # Day card: ## Day N | DayName: Label [| ~Xmin]
            flush_day()
            parts = [p.strip() for p in h2_text.split('|')]
            # parts[0] = "Day N", parts[1] = "DayName: Label", parts[2] = "~55 min" (optional)
            day_label = parts[1] if len(parts) > 1 else parts[0]
            day_meta = parts[2] if len(parts) > 2 else ''
            is_rest = is_rest_day(day_label)

            current_day = {
                'label': day_label,
                'meta': day_meta,
                'is_rest': is_rest,
                'video': None,
                'warmup_title': '',
                'warmup_items': [],
                'exercises': [],
                'cooldown_title': '',
                'cooldown_items': [],
                'rest_items': [],
            }
            current_phase = 'rest' if is_rest else None
            continue

        # H3 — Phase headers within a day card
        if stripped.startswith('### ') and current_day is not None:
            flush_exercise()
            h3_text = stripped[4:].strip()

            if re.match(r'video', h3_text, re.IGNORECASE):
                current_phase = 'video'
            elif re.match(r'warm-?up', h3_text, re.IGNORECASE) or re.match(r'热身', h3_text):
                current_phase = 'warmup'
                current_day['warmup_title'] = h3_text
            elif re.match(r'main\s+training', h3_text, re.IGNORECASE) or re.match(r'正式训练', h3_text):
                current_phase = 'main'
            elif re.match(r'cool-?down', h3_text, re.IGNORECASE) or re.match(r'拉伸|放松', h3_text):
                current_phase = 'cooldown'
                current_day['cooldown_title'] = h3_text
            continue

        # H4 — Exercise header within Main Training
        if stripped.startswith('#### ') and current_day is not None and current_phase == 'main':
            flush_exercise()
            h4_text = stripped[5:].strip()
            # Format: N. ExerciseName | intensity description
            pipe_parts = [p.strip() for p in h4_text.split('|', 1)]
            exercise_name = pipe_parts[0]
            intensity = pipe_parts[1] if len(pipe_parts) > 1 else ''
            current_exercise = {
                'name': exercise_name,
                'intensity': intensity,
                'prescription': [],
            }
            continue

        # Metadata lines (between H1 and first H2)
        if in_metadata and stripped.startswith('- '):
            metadata_lines.append(stripped)
            continue

        # Weekly overview table lines
        if in_weekly_overview:
            if stripped.startswith('|') or stripped == '':
                weekly_overview_lines.append(stripped)
            continue

        # Progression items
        if in_progression:
            if stripped.startswith('- '):
                plan['progression'].append(stripped[2:].strip())
            continue

        # Notes items
        if in_notes:
            if stripped:
                plan['notes'].append(stripped)
            continue

        # Disclaimer
        if in_disclaimer:
            if stripped:
                plan['disclaimer'] = stripped
            continue

        # Content within day cards
        if current_day is not None:
            # Video link: [text](url)
            if current_phase == 'video' and stripped:
                link_match = re.match(r'\[([^\]]+)\]\(([^)]+)\)', stripped)
                if link_match:
                    current_day['video'] = {
                        'text': link_match.group(1),
                        'url': link_match.group(2),
                    }
                continue

            # Warm-up numbered items
            if current_phase == 'warmup':
                num_match = re.match(r'\d+\.\s+(.+)', stripped)
                if num_match:
                    current_day['warmup_items'].append(num_match.group(1))
                continue

            # Cooldown numbered items
            if current_phase == 'cooldown':
                num_match = re.match(r'\d+\.\s+(.+)', stripped)
                if num_match:
                    current_day['cooldown_items'].append(num_match.group(1))
                continue

            # Exercise prescription lines
            if current_phase == 'main' and current_exercise is not None:
                if stripped and not stripped.startswith('#'):
                    current_exercise['prescription'].append(stripped)
                continue

            # Rest day bullet items
            if current_phase == 'rest' and stripped.startswith('- '):
                current_day['rest_items'].append(stripped[2:].strip())
                continue

    # Flush remaining
    flush_day()
    if metadata_lines and not plan['metadata']:
        plan['metadata'] = parse_metadata(metadata_lines)
    if weekly_overview_lines and not plan['weekly_overview']:
        plan['weekly_overview'] = parse_weekly_overview(weekly_overview_lines)

    return plan


def render_bold(text):
    """Convert **bold** markdown to <strong> tags."""
    return re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', escape(text))


def render_html(plan, lang='en'):
    """Render parsed plan into full HTML."""
    meta = plan['metadata']
    date_str = meta.get('date', '')
    goal_str = meta.get('goal', '')
    level_str = meta.get('level', '')
    split_str = meta.get('split', '')
    freq_str = meta.get('frequency', '')
    equip_str = meta.get('equipment', '')

    # Localized labels
    if lang == 'zh':
        labels = {
            'goal': '目标:', 'level': '水平:', 'split': '训练分化:',
            'frequency': '频率:', 'equipment': '器械/场地:',
            'weekly_overview': '每周概览', 'progression': '进阶计划',
            'notes': '备注', 'footer': 'AI 健身教练生成 · 仅供参考，如有伤病或健康问题请咨询专业人士',
            'day_col': '日', 'training_col': '训练内容',
        }
    else:
        labels = {
            'goal': 'Goal:', 'level': 'Level:', 'split': 'Split:',
            'frequency': 'Frequency:', 'equipment': 'Equipment:',
            'weekly_overview': 'Weekly Overview', 'progression': 'Progression Plan',
            'notes': 'Notes', 'footer': 'Generated by AI Fitness Coach · For reference only — consult a certified trainer for specialized needs',
            'day_col': 'Day', 'training_col': 'Training',
        }

    # Weekly overview table
    overview_rows = []
    for row in plan['weekly_overview']:
        is_rest = is_rest_day(row['training'])
        rest_class = ' class="rest-label"' if is_rest else ''
        overview_rows.append(
            f'        <tr><td>{escape(row["day"])}</td><td{rest_class}>{escape(row["training"])}</td></tr>'
        )
    overview_html = '\n'.join(overview_rows)

    # Day cards
    days_html = []
    for day in plan['days']:
        if day['is_rest']:
            # Rest day card
            rest_items = '\n'.join(
                f'          <li>{escape(item)}</li>' for item in day['rest_items']
            )
            day_block = f"""  <div class="day-card">
    <div class="day-header rest-day">
      <h2>{escape(day['label'])}</h2>
    </div>
    <div class="day-body">
      <div class="rest-content">
        <ul>
{rest_items}
        </ul>
      </div>
    </div>
  </div>"""
        else:
            # Training day card
            parts = []

            # Video link
            if day['video']:
                parts.append(f"""      <div class="video-link">
        {"跟练视频：" if lang == "zh" else "Follow-along video: "}<a href="{escape(day['video']['url'])}" target="_blank">{escape(day['video']['text'])}</a>
      </div>""")

            # Warm-up
            if day['warmup_items']:
                warmup_items = '\n'.join(
                    f'          <li>{escape(item)}</li>' for item in day['warmup_items']
                )
                warmup_title = day['warmup_title'] or ('Warm-up' if lang != 'zh' else '热身')
                parts.append(f"""      <div class="phase-block">
        <div class="phase-title">{escape(warmup_title)}</div>
        <ol class="phase-list">
{warmup_items}
        </ol>
      </div>""")

            # Main Training
            if day['exercises']:
                parts.append("""      <div class="phase-block">
        <div class="phase-title">{"正式训练" if lang == "zh" else "Main Training"}</div>
      </div>""".replace('{"正式训练" if lang == "zh" else "Main Training"}',
                         '正式训练' if lang == 'zh' else 'Main Training'))

                for ex in day['exercises']:
                    intensity_html = ''
                    if ex['intensity']:
                        intensity_html = f'\n          <span class="intensity">| {escape(ex["intensity"])}</span>'
                    prescription_lines = '\n'.join(
                        f'        <div class="exercise-prescription">{escape(p)}</div>'
                        for p in ex['prescription']
                    )
                    parts.append(f"""      <div class="exercise-block">
        <div class="exercise-header">
          <span class="exercise-num">{escape(ex['name'].split('.')[0].strip()) + '.' if '.' in ex['name'] else ''}</span>
          {escape(ex['name'].split('.', 1)[1].strip() if '.' in ex['name'] else ex['name'])}{intensity_html}
        </div>
{prescription_lines}
      </div>""")

            # Cooldown
            if day['cooldown_items']:
                cooldown_items = '\n'.join(
                    f'          <li>{escape(item)}</li>' for item in day['cooldown_items']
                )
                cooldown_title = day['cooldown_title'] or ('Cooldown' if lang != 'zh' else '拉伸放松')
                parts.append(f"""      <div class="phase-block">
        <div class="phase-title">{escape(cooldown_title)}</div>
        <ol class="phase-list">
{cooldown_items}
        </ol>
      </div>""")

            meta_html = ''
            if day['meta']:
                meta_html = f'\n      <span class="day-meta">{escape(day["meta"])}</span>'

            day_block = f"""  <div class="day-card">
    <div class="day-header">
      <h2>{escape(day['label'])}</h2>{meta_html}
    </div>
    <div class="day-body">
{chr(10).join(parts)}
    </div>
  </div>"""

        days_html.append(day_block)

    # Progression section
    progression_items = '\n'.join(
        f'      <li>{render_bold(item)}</li>' for item in plan['progression']
    )
    progression_html = f"""  <div class="progression-section">
    <h2>{escape(labels['progression'])}</h2>
    <ul>
{progression_items}
    </ul>
  </div>""" if plan['progression'] else ''

    # Notes section
    notes_parts = []
    for note in plan['notes']:
        if note.startswith('💡'):
            tip_text = note[1:].strip().lstrip(' ')
            notes_parts.append(f'    <p class="tip">💡 {escape(tip_text)}</p>')
        else:
            notes_parts.append(f'    <p>{escape(note)}</p>')
    notes_html = f"""  <div class="notes-section">
    <h2>{escape(labels['notes'])}</h2>
{chr(10).join(notes_parts)}
  </div>""" if plan['notes'] else ''

    # Disclaimer
    disclaimer_html = ''
    if plan['disclaimer']:
        disclaimer_html = f"""  <div class="disclaimer">
    {escape(plan['disclaimer'])}
  </div>"""

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
  .week-overview {{
    background: #fff; border: 1px solid #e0ddd5; border-radius: 12px;
    padding: 1.2rem 1.5rem; margin-bottom: 2rem;
  }}
  .week-overview h2 {{ font-size: 1.15rem; font-weight: 600; color: #2d5016; margin-bottom: 0.8rem; }}
  .week-overview table {{ width: 100%; border-collapse: collapse; }}
  .week-overview th {{
    text-align: left; font-size: 0.82rem; color: #888; font-weight: 500;
    padding: 0.4rem 0.6rem; border-bottom: 2px solid #e0ddd5;
  }}
  .week-overview td {{ font-size: 0.88rem; color: #444; padding: 0.5rem 0.6rem; border-bottom: 1px solid #f0ede5; }}
  .week-overview td:first-child {{ font-weight: 600; color: #2d5016; white-space: nowrap; width: 4.5rem; }}
  .week-overview tr:last-child td {{ border-bottom: none; }}
  .week-overview .rest-label {{ color: #999; }}
  .day-card {{ background: #fff; border: 1px solid #e0ddd5; border-radius: 12px; margin-bottom: 1.5rem; overflow: hidden; }}
  .day-header {{
    background: #2d5016; color: #fff; padding: 0.8rem 1.2rem;
    display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.4rem;
  }}
  .day-header h2 {{ font-size: 1.15rem; font-weight: 600; margin: 0; }}
  .day-header .day-meta {{ font-size: 0.82rem; opacity: 0.9; font-weight: 400; }}
  .day-header.rest-day {{ background: #8a8578; }}
  .day-body {{ padding: 0.6rem 0; }}
  .video-link {{ padding: 0.5rem 1.2rem 0.3rem; font-size: 0.88rem; }}
  .video-link a {{ color: #2d5016; text-decoration: none; font-weight: 500; }}
  .video-link a:hover {{ text-decoration: underline; }}
  .phase-block {{ padding: 0.6rem 1.2rem; border-bottom: 1px solid #f0ede5; }}
  .phase-block:last-child {{ border-bottom: none; }}
  .phase-title {{ font-size: 0.92rem; font-weight: 600; color: #2d5016; margin-bottom: 0.4rem; }}
  .phase-list {{ list-style: none; padding: 0; margin: 0; counter-reset: phase-counter; }}
  .phase-list li {{
    font-size: 0.88rem; color: #444; padding: 0.15rem 0 0.15rem 1.8rem;
    position: relative; counter-increment: phase-counter;
  }}
  .phase-list li::before {{
    content: counter(phase-counter) "."; position: absolute; left: 0.3rem;
    color: #aaa; font-weight: 600; font-size: 0.82rem;
  }}
  .exercise-block {{ padding: 0.5rem 1.2rem; border-bottom: 1px solid #f0ede5; }}
  .exercise-block:last-child {{ border-bottom: none; }}
  .exercise-header {{ font-size: 0.95rem; font-weight: 600; color: #333; margin-bottom: 0.2rem; }}
  .exercise-header .exercise-num {{ color: #2d5016; margin-right: 0.3rem; }}
  .exercise-header .intensity {{ font-weight: 400; font-size: 0.82rem; color: #888; }}
  .exercise-prescription {{ font-size: 0.85rem; color: #666; padding-left: 1.6rem; margin-top: 0.1rem; }}
  .rest-content {{ padding: 0.8rem 1.2rem; }}
  .rest-content ul {{ list-style: none; padding: 0; margin: 0; }}
  .rest-content li {{ font-size: 0.88rem; color: #666; padding: 0.15rem 0 0.15rem 1.2rem; position: relative; }}
  .rest-content li::before {{ content: "·"; position: absolute; left: 0.3rem; color: #aaa; font-weight: 700; }}
  .progression-section {{
    background: #fff; border: 1px solid #e0ddd5; border-radius: 12px;
    padding: 1.2rem 1.5rem; margin-top: 2rem;
  }}
  .progression-section h2 {{ font-size: 1.15rem; font-weight: 600; color: #2d5016; margin-bottom: 0.8rem; }}
  .progression-section ul {{ list-style: none; padding: 0; margin: 0; }}
  .progression-section li {{ font-size: 0.88rem; color: #444; padding: 0.3rem 0 0.3rem 1.2rem; position: relative; }}
  .progression-section li::before {{ content: "·"; position: absolute; left: 0.3rem; color: #2d5016; font-weight: 700; }}
  .progression-section li strong {{ color: #333; }}
  .notes-section {{
    background: #fff; border: 1px solid #e0ddd5; border-radius: 12px;
    padding: 1.2rem 1.5rem; margin-top: 1.5rem;
  }}
  .notes-section h2 {{ font-size: 1.15rem; font-weight: 600; color: #2d5016; margin-bottom: 0.8rem; }}
  .notes-section p {{ font-size: 0.88rem; color: #555; margin-bottom: 0.5rem; }}
  .notes-section .tip {{ font-size: 0.85rem; color: #b45309; padding-left: 1.2rem; margin-bottom: 0.3rem; }}
  .disclaimer {{
    background: #fffbeb; border: 1px solid #f5d78e; border-radius: 12px;
    padding: 1rem 1.2rem; margin-top: 1.5rem; font-size: 0.82rem; color: #92400e; line-height: 1.5;
  }}
  .plan-footer {{
    text-align: center; margin-top: 2rem; padding-top: 1rem;
    border-top: 1px solid #e0ddd5; font-size: 0.8rem; color: #aaa;
  }}
  @media (max-width: 600px) {{
    html {{ font-size: 14px; }}
    .page {{ padding: 1rem; }}
    .summary-card {{ grid-template-columns: 1fr; }}
    .day-header {{ flex-direction: column; align-items: flex-start; }}
    .week-overview td:first-child {{ width: auto; }}
  }}
  @media print {{
    body {{ background: #fff; font-size: 11pt; }}
    .page {{ max-width: none; padding: 0; }}
    .day-card {{ break-inside: avoid; border: 1px solid #ccc; margin-bottom: 1rem; }}
    .day-header {{ background: #2d5016 !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
    .day-header.rest-day {{ background: #8a8578 !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
    .plan-footer {{ display: none; }}
    .disclaimer {{ break-inside: avoid; }}
  }}
</style>
</head>
<body>
<div class="page">
  <header class="plan-header">
    <h1>💪 {escape(plan['title'])}</h1>
    <p class="subtitle">{escape(date_str)}</p>
  </header>

  <div class="summary-card">
    <div class="item">
      <span class="label">{labels['goal']}</span>
      <span class="value">{escape(goal_str)}</span>
    </div>
    <div class="item">
      <span class="label">{labels['level']}</span>
      <span class="value">{escape(level_str)}</span>
    </div>
    <div class="item">
      <span class="label">{labels['split']}</span>
      <span class="value">{escape(split_str)}</span>
    </div>
    <div class="item">
      <span class="label">{labels['frequency']}</span>
      <span class="value">{escape(freq_str)}</span>
    </div>
    <div class="item full-width">
      <span class="label">{labels['equipment']}</span>
      <span class="value">{escape(equip_str)}</span>
    </div>
  </div>

  <div class="week-overview">
    <h2>{escape(labels['weekly_overview'])}</h2>
    <table>
      <thead>
        <tr>
          <th>{labels['day_col']}</th>
          <th>{labels['training_col']}</th>
        </tr>
      </thead>
      <tbody>
{overview_html}
      </tbody>
    </table>
  </div>

{chr(10).join(days_html)}

{progression_html}

{notes_html}

{disclaimer_html}

  <footer class="plan-footer">
    {labels['footer']}
  </footer>
</div>
</body>
</html>"""


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 generate-exercise-plan-html.py <input.md> [output.html]", file=sys.stderr)
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else input_path.rsplit('.', 1)[0] + '.html'

    if not os.path.isfile(input_path):
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    with open(input_path, 'r', encoding='utf-8') as f:
        md_text = f.read()

    lang = detect_lang(md_text)
    plan = parse_exercise_plan(md_text)
    html_output = render_html(plan, lang=lang)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_output)

    print(f"HTML generated: {output_path}")


if __name__ == '__main__':
    main()
