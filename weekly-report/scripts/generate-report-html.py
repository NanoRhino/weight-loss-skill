#!/usr/bin/env python3.11
"""
generate-report-html.py — Deterministic HTML weekly report generator.

Reads collect-weekly-data.py JSON output and produces a self-contained HTML file
with precise chart rendering (SVG weight curves, bar charts for calories/macros).

Usage:
    python3.11 collect-weekly-data.py ... | python3.11 generate-report-html.py --output report.html
    python3.11 generate-report-html.py --data-file data.json --output report.html
"""

import argparse, json, sys, math, os
from datetime import datetime, timedelta

# ─── Catmull-Rom spline ──────────────────────────────────────────────────────

def catmull_rom_path(points):
    """Convert list of (x,y) to SVG cubic bezier path using Catmull-Rom interpolation."""
    n = len(points)
    if n < 2:
        return ""
    path = f"M {points[0][0]},{points[0][1]}"
    for i in range(n - 1):
        p0 = points[max(0, i - 1)]
        p1 = points[i]
        p2 = points[min(n - 1, i + 1)]
        p3 = points[min(n - 1, i + 2)]
        cp1x = p1[0] + (p2[0] - p0[0]) / 6
        cp1y = p1[1] + (p2[1] - p0[1]) / 6
        cp2x = p2[0] - (p3[0] - p1[0]) / 6
        cp2y = p2[1] - (p3[1] - p1[1]) / 6
        path += f" C {cp1x:.1f},{cp1y:.1f} {cp2x:.1f},{cp2y:.1f} {p2[0]},{p2[1]}"
    return path


def nice_ticks(max_val, preferred_count=4):
    """Generate round-number ticks from 0 to max_val."""
    if max_val <= 0:
        return [0]
    raw_step = max_val / preferred_count
    magnitude = 10 ** math.floor(math.log10(raw_step))
    for nice in [1, 2, 2.5, 5, 10]:
        step = nice * magnitude
        if max_val / step <= preferred_count + 1:
            break
    ticks = []
    v = 0
    while v <= max_val * 1.01:
        ticks.append(round(v))
        v += step
    return ticks


# ─── CSS ─────────────────────────────────────────────────────────────────────

CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: system-ui, -apple-system, 'Segoe UI', sans-serif; background: #faf9f5; color: #333; line-height: 1.5; font-size: 14px; -webkit-text-size-adjust: 100%; }
.page { max-width: 800px; margin: 0 auto; padding: 0 1.5rem 2rem; }
.report-header { text-align: center; margin-top: 1.5rem; margin-bottom: 2rem; padding-bottom: 1.5rem; border-bottom: 2px solid #e0ddd5; }
.report-header h1 { font-size: 1.4rem; font-weight: 700; color: #2d5016; margin-bottom: 0.3rem; }
.report-header .subtitle { font-size: 0.85rem; color: #666; }
.report-card { background: #fff; border: 1px solid #e0ddd5; border-radius: 12px; margin-bottom: 1.5rem; overflow: hidden; }
.card-header { padding: 0.6rem 1rem; font-size: 0.95rem; font-weight: 600; color: #2d5016; border-bottom: 1px solid #f0ede5; }
.card-body { padding: 0.8rem 1rem; }
.card-commentary { font-size: 0.82rem; color: #555; padding: 0.5rem 1rem 0.8rem; border-top: 1px solid #f0ede5; }

/* Logging grid */
.logging-grid { display: grid; grid-template-columns: repeat(7, 1fr); text-align: center; gap: 0.2rem; }
.logging-grid .day-label { font-size: 0.78rem; color: #888; font-weight: 500; padding: 0.3rem 0; }
.logging-grid .day-status { font-size: 1.2rem; padding: 0.2rem 0 0.3rem; }
.logging-summary { text-align: center; font-size: 0.85rem; font-weight: 600; color: #333; padding-top: 0.5rem; }

/* Calorie + macro charts (shared) */
.cal-chart { position: relative; height: 220px; display: flex; align-items: flex-end; justify-content: space-between; padding: 0 0.3rem 0 2.5rem; margin-bottom: 0.4rem; }
.cal-target-band { position: absolute; left: 2.5rem; right: 0; background: rgba(0,0,0,0.05); z-index: 0; }
.cal-target-label { position: absolute; right: 4px; top: 2px; font-size: 0.65rem; color: #aaa; }
.cal-grid-line { position: absolute; left: 2.5rem; right: 0; height: 0; border-bottom: 1px dashed #e8e5dd; z-index: 0; }
.cal-grid-label { position: absolute; right: 100%; margin-right: 4px; white-space: nowrap; transform: translateY(-50%); font-size: 0.65rem; color: #999; font-weight: 500; }
.cal-bar-col { display: flex; flex-direction: column; align-items: center; flex: 1; z-index: 1; position: relative; }
.cal-bar-wrapper { width: 60%; max-width: 36px; }
.cal-bar { width: 100%; border-radius: 4px 4px 0 0; transition: height 0.3s; opacity: 0.75; }
.cal-bar-value { font-size: 0.7rem; color: #888; margin-bottom: 2px; font-weight: 500; }
.cal-x-labels { display: flex; justify-content: space-between; padding: 0.3rem 0.3rem 0 2.5rem; }
.cal-x-label { flex: 1; text-align: center; font-size: 0.75rem; color: #888; font-weight: 500; }
.cal-average { text-align: center; font-size: 0.85rem; font-weight: 600; color: #333; padding-top: 0.6rem; }
.cal-average .sub { font-weight: 400; font-size: 0.78rem; color: #888; }

/* Macro-specific */
.macro-legend { display: flex; justify-content: center; gap: 1.2rem; margin-bottom: 1rem; }
.macro-legend-item { display: flex; align-items: center; gap: 0.3rem; font-size: 0.8rem; color: #888; }
.macro-legend-dot { width: 14px; height: 14px; border-radius: 3px; }
.macro-chart-section { margin-bottom: 1.8rem; }
.macro-chart-section:last-of-type { margin-bottom: 0.5rem; }
.macro-chart-title { text-align: center; font-size: 0.95rem; font-weight: 700; color: #333; margin-bottom: 0.5rem; }
.macro-avg-line { position: absolute; left: 2.5rem; right: 0; height: 0; border-top: 1px dashed #333; z-index: 2; }
.macro-avg-label { position: absolute; right: 4px; transform: translateY(-100%); font-size: 0.65rem; color: #333; font-weight: 500; }

/* Weight chart */
.weight-chart-wrapper { position: relative; display: flex; margin-bottom: 0.6rem; }
.weight-y-axis { width: 2.5rem; flex-shrink: 0; position: relative; height: 175px; }
.weight-y-label { position: absolute; left: 0; font-size: 10px; color: #bbb; transform: translateY(-50%); }
.weight-chart-container { position: relative; overflow-x: auto; overflow-y: hidden; -webkit-overflow-scrolling: touch; flex: 1; }
.weight-chart-container::-webkit-scrollbar { height: 4px; }
.weight-chart-container::-webkit-scrollbar-thumb { background: #ddd; border-radius: 2px; }
.weight-chart-scroll-hint { text-align: center; font-size: 0.72rem; color: #bbb; margin-top: 0.3rem; }
.weight-change { text-align: center; font-size: 0.85rem; font-weight: 600; color: #333; padding-top: 0.3rem; }
.weight-change.same { color: #888; }
.weight-change.up { color: #e57373; }
.weight-change.down { color: #6bcb8b; }
.weight-progress { text-align: center; font-size: 0.78rem; color: #888; padding-top: 0.2rem; }

/* Suggestions */
.section-subtitle { font-size: 0.85rem; font-weight: 600; color: #2d5016; margin-bottom: 0.3rem; padding-top: 0.3rem; }
.section-subtitle:first-child { padding-top: 0; }
.suggestions-divider { border: none; border-top: 1px solid #f0ede5; margin: 0.6rem 0; }
.achievement-list, .suggestion-list { padding-left: 1.2rem; font-size: 0.82rem; color: #444; }
.achievement-list li, .suggestion-list li { margin-bottom: 0.3rem; }
.safety-note { background: #fff8e1; border-left: 3px solid #ffc107; padding: 0.6rem 1rem; margin-top: 0.6rem; font-size: 0.85rem; color: #665500; border-radius: 0 6px 6px 0; }

/* Week nav */
.week-nav { display: flex; justify-content: space-between; align-items: center; position: sticky; top: 0; z-index: 100; background: #faf9f5; padding: 0.6rem 1rem; margin: 0 -1.5rem; border-bottom: 1px solid #e0ddd5; }
.week-nav-btn { display: inline-block; padding: 0.35rem 0.7rem; background: #2d5016; color: #fff; text-decoration: none; border-radius: 6px; font-size: 0.78rem; font-weight: 600; transition: background 0.2s; }
.week-nav-btn:hover { background: #3d6b1f; }
.week-nav-btn.disabled { background: #ccc; color: #999; pointer-events: none; cursor: default; }
.week-nav-current { font-size: 0.78rem; color: #666; font-weight: 500; }
.report-footer { text-align: center; margin-top: 2rem; padding-top: 1rem; border-top: 1px solid #e0ddd5; font-size: 0.8rem; color: #aaa; }
"""


# ─── Chart generators ────────────────────────────────────────────────────────

def gen_calorie_chart(days, cal_min, cal_max_target, chart_max):
    """Generate calorie bar chart HTML."""
    weekdays = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
    chart_h = 220

    # Grid ticks
    ticks = nice_ticks(chart_max, 4)

    # Target band
    band_bottom = (cal_min / chart_max) * 100
    band_height = ((cal_max_target - cal_min) / chart_max) * 100

    html = f'<div class="cal-chart">\n'
    # Grid lines
    for t in ticks:
        pct = (t / chart_max) * 100
        solid = ' border-bottom-style: solid;' if t == 0 else ''
        html += f'  <div class="cal-grid-line" style="bottom: {pct:.1f}%;{solid}"><span class="cal-grid-label">{t}</span></div>\n'
    # Target band
    html += f'  <div class="cal-target-band" style="bottom: {band_bottom:.1f}%; height: {band_height:.1f}%">'
    html += f'<span class="cal-target-label">目标 {cal_min}–{cal_max_target}</span></div>\n'

    # Bars
    for day_data in days:
        cal = day_data['totals']['cal']
        status = day_data.get('cal_status', 'below')
        if not day_data['logged'] or cal == 0:
            html += '  <div class="cal-bar-col"><div class="cal-bar-value"></div>'
            html += '<div class="cal-bar-wrapper"><div class="cal-bar" style="height:0px;background:transparent;"></div></div></div>\n'
        else:
            bar_h = round((cal / chart_max) * (chart_h - 30))
            color = {'below': '#c8e6c9', 'on-target': '#6bcb8b', 'over': '#fdd0b1'}.get(status, '#c8e6c9')
            html += f'  <div class="cal-bar-col"><div class="cal-bar-value">{cal}</div>'
            html += f'<div class="cal-bar-wrapper"><div class="cal-bar" style="height:{bar_h}px;background:{color};"></div></div></div>\n'

    html += '</div>\n'
    # X labels
    html += '<div class="cal-x-labels">'
    for d in days:
        html += f'<div class="cal-x-label">{d["weekday"]}</div>'
    html += '</div>\n'
    return html


def gen_weight_chart(weight_readings, all_weight_data, meta, plan_rate=0.5, target_weight=None):
    """Generate SVG weight curve chart with plan path overlay."""
    if not all_weight_data or len(all_weight_data) < 1:
        return '<p style="text-align:center;color:#888;">暂无体重数据</p>'

    start_date = datetime.strptime(meta['start_date'], '%Y-%m-%d')
    first_monday = datetime.strptime(meta['first_monday'], '%Y-%m-%d')

    # Collect all weight points (including historical)
    points = []
    for r in all_weight_data:
        d = datetime.strptime(r['date'], '%Y-%m-%d')
        points.append((d, r['value']))
    points.sort(key=lambda p: p[0])

    if not points:
        return '<p style="text-align:center;color:#888;">暂无体重数据</p>'

    # Determine which points are "this week"
    end_date = start_date + timedelta(days=6)
    this_week_dates = set()
    for d, _ in points:
        if start_date <= d <= end_date:
            this_week_dates.add(d.strftime('%Y-%m-%d'))

    # X spacing: 120px between points, start at 60
    x_start = 60
    x_spacing = 120
    xs = [x_start + i * x_spacing for i in range(len(points))]
    svg_width = max(xs[-1] + 60, 400)

    # Y range: auto from data + plan path
    vals = [v for _, v in points]
    # Plan path: from first point, decreasing
    first_val = points[0][1]
    plan_vals = []
    for i, (d, _) in enumerate(points):
        days_from_start = (d - points[0][0]).days
        weeks = days_from_start / 7.0
        plan_vals.append(first_val - plan_rate * weeks)

    all_vals = vals + plan_vals
    y_min_val = min(all_vals) - 0.5
    y_max_val = max(all_vals) + 0.5
    # Round to nice values
    y_min_val = math.floor(y_min_val * 2) / 2  # round to 0.5
    y_max_val = math.ceil(y_max_val * 2) / 2
    y_range = y_max_val - y_min_val
    if y_range < 1:
        y_range = 1
        y_max_val = y_min_val + 1

    chart_top = 20
    chart_bottom = 150
    chart_height = chart_bottom - chart_top

    def val_to_y(v):
        return round(chart_bottom - ((v - y_min_val) / y_range) * chart_height)

    # Actual curve points
    actual_pts = [(x, val_to_y(v)) for x, (_, v) in zip(xs, points)]
    plan_pts = [(x, val_to_y(pv)) for x, pv in zip(xs, plan_vals)]

    actual_path = catmull_rom_path(actual_pts)
    plan_path_d = catmull_rom_path(plan_pts)

    # Y-axis labels (4-6 ticks)
    y_step = 0.5 if y_range <= 3 else 1.0
    y_ticks = []
    v = y_min_val
    while v <= y_max_val + 0.01:
        y_ticks.append(v)
        v += y_step

    # Generate Y-axis div
    y_axis_html = '<div class="weight-y-axis">\n'
    for yv in y_ticks:
        pct = ((yv - y_min_val) / y_range) * 100
        top_pct = 100 - pct
        # Map to chart area within the div
        top_px_pct = chart_top / 175 * 100 + (1 - (yv - y_min_val) / y_range) * (chart_height / 175 * 100)
        y_axis_html += f'  <span class="weight-y-label" style="top: {top_px_pct:.1f}%">{yv:.1f}</span>\n'
    y_axis_html += '</div>\n'

    # Generate SVG
    svg = f'<svg width="{svg_width}" height="175" viewBox="0 0 {svg_width} 175" style="display:block;min-width:{svg_width}px;">\n'

    # Grid lines
    for yv in y_ticks:
        y = val_to_y(yv)
        svg += f'  <line x1="0" y1="{y}" x2="{svg_width}" y2="{y}" stroke="#f0ede5" stroke-width="1" stroke-dasharray="4"/>\n'
    # Bottom line (solid)
    svg += f'  <line x1="0" y1="{chart_bottom}" x2="{svg_width}" y2="{chart_bottom}" stroke="#f0ede5" stroke-width="1"/>\n'

    # Defs
    svg += '  <defs>\n'
    svg += '    <linearGradient id="weightGrad" x1="0" y1="0" x2="0" y2="1">\n'
    svg += '      <stop offset="0%" stop-color="#6bcb8b" stop-opacity="0.3"/>\n'
    svg += '      <stop offset="100%" stop-color="#6bcb8b" stop-opacity="0.02"/>\n'
    svg += '    </linearGradient>\n'
    svg += '  </defs>\n'

    # Plan path (behind actual)
    if len(plan_pts) >= 2:
        svg += f'  <path d="{plan_path_d} L {plan_pts[-1][0]},{chart_bottom} L {plan_pts[0][0]},{chart_bottom} Z" fill="rgba(0,0,0,0.04)"/>\n'
        svg += f'  <path d="{plan_path_d}" fill="none" stroke="#ccc" stroke-width="1" opacity="0.7"/>\n'
        svg += f'  <text x="{plan_pts[-1][0] - 5}" y="{chart_bottom - 5}" text-anchor="end" font-size="8.5" fill="#bbb" font-style="italic">计划 −{plan_rate}kg/周</text>\n'

    # Actual curve
    if len(actual_pts) >= 2:
        svg += f'  <path d="{actual_path} L {actual_pts[-1][0]},{chart_bottom} L {actual_pts[0][0]},{chart_bottom} Z" fill="url(#weightGrad)"/>\n'
        svg += f'  <path d="{actual_path}" fill="none" stroke="#6bcb8b" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>\n'

    # Data points
    for i, ((x, y), (d, v)) in enumerate(zip(actual_pts, points)):
        date_str = d.strftime('%Y-%m-%d')
        label = f"{d.month}/{d.day}"
        is_this_week = date_str in this_week_dates

        if is_this_week:
            svg += f'  <circle cx="{x}" cy="{y}" r="6" fill="#6bcb8b" stroke="#fff" stroke-width="2.5"/>\n'
            svg += f'  <text x="{x}" y="167" text-anchor="middle" font-size="10" fill="#2d5016" font-weight="600">{label}</text>\n'
            svg += f'  <text x="{x}" y="{y - 8}" text-anchor="middle" font-size="11.5" fill="#2d5016" font-weight="700">{v}</text>\n'
        else:
            svg += f'  <circle cx="{x}" cy="{y}" r="4.5" fill="#fff" stroke="#a8deb8" stroke-width="2"/>\n'
            svg += f'  <text x="{x}" y="167" text-anchor="middle" font-size="9.5" fill="#aaa">{label}</text>\n'
            svg += f'  <text x="{x}" y="{y - 7}" text-anchor="middle" font-size="10" fill="#888" font-weight="500">{v}</text>\n'

    svg += '</svg>\n'

    # Assemble
    html = '<div class="weight-chart-wrapper">\n'
    html += y_axis_html
    html += '<div class="weight-chart-container" id="weightChartContainer">\n'
    html += svg
    html += '</div>\n</div>\n'
    html += '<div class="weight-chart-scroll-hint">← 左右滑动查看更多 →</div>\n'

    # Weight change summary
    if len(weight_readings) >= 2:
        change = weight_readings[-1]['value'] - weight_readings[0]['value']
        cls = 'up' if change > 0 else ('down' if change < 0 else 'same')
        sign = '+' if change > 0 else ''
        html += f'<div class="weight-change {cls}">本周 {sign}{change:.1f} kg（{weight_readings[0]["value"]}→{weight_readings[-1]["value"]}）</div>\n'
    elif len(weight_readings) == 1:
        html += f'<div class="weight-change same">本周称重 1 次 · {weight_readings[0]["value"]} kg</div>\n'

    return html


def gen_macro_chart(name, daily_values, target_low, target_high, chart_h=160):
    """Generate one macro nutrient bar chart."""
    weekdays = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

    non_null = [v for v in daily_values if v is not None and v > 0]
    if not non_null:
        return ''

    avg_val = round(sum(non_null) / len(non_null))
    max_data = max(non_null) if non_null else 0
    chart_max = max(max_data, target_high) * 1.2
    chart_max = max(chart_max, 10)

    ticks = nice_ticks(chart_max, 3)
    chart_max = max(ticks) if ticks else chart_max

    t_low_pct = (target_low / chart_max) * 100
    t_high_pct = (target_high / chart_max) * 100
    avg_pct = (avg_val / chart_max) * 100

    def bar_color(val):
        if val < target_low:
            return '#c8e6c9'
        elif val > target_high:
            return '#fdd0b1'
        return '#6bcb8b'

    html = f'<div class="macro-chart-section">\n'
    html += f'  <div class="macro-chart-title">{name}</div>\n'
    html += f'  <div class="cal-chart" style="height: {chart_h}px;">\n'

    # Grid lines
    for t in ticks:
        pct = (t / chart_max) * 100
        solid = ' border-bottom-style: solid;' if t == 0 else ''
        html += f'    <div class="cal-grid-line" style="bottom: {pct:.1f}%;{solid}"><span class="cal-grid-label">{t}</span></div>\n'

    # Target band
    html += f'    <div class="cal-target-band" style="bottom: {t_low_pct:.1f}%; height: {t_high_pct - t_low_pct:.1f}%">'
    html += f'<span class="cal-target-label">目标 {target_low}–{target_high}</span></div>\n'

    # Average line
    html += f'    <div class="macro-avg-line" style="bottom: {avg_pct:.1f}%;"><span class="macro-avg-label">平均摄入 {avg_val}</span></div>\n'

    # Bars
    for val in daily_values:
        if val is None or val == 0:
            html += '    <div class="cal-bar-col"><div class="cal-bar-value"></div>'
            html += '<div class="cal-bar-wrapper"><div class="cal-bar" style="height:0px;background:transparent;"></div></div></div>\n'
        else:
            bar_h = round((val / chart_max) * (chart_h - 30))
            c = bar_color(val)
            html += f'    <div class="cal-bar-col"><div class="cal-bar-value">{val}</div>'
            html += f'<div class="cal-bar-wrapper"><div class="cal-bar" style="height:{bar_h}px;background:{c};"></div></div></div>\n'

    html += '  </div>\n'
    # X labels
    html += '  <div class="cal-x-labels">'
    for wd in weekdays:
        html += f'<div class="cal-x-label">{wd}</div>'
    html += '</div>\n'
    html += '</div>\n'
    return html


def gen_macro_section(days, plan, summary):
    """Generate all three macro charts with legend."""
    protein_range = plan.get('protein_range', [0, 0])
    fat_range = plan.get('fat_range', [0, 0])
    carb_range = plan.get('carb_range', [0, 0])

    # Extract per-day values
    protein_vals = [d['totals']['protein'] if d['logged'] and d['totals']['protein'] > 0 else None for d in days]
    fat_vals = [d['totals']['fat'] if d['logged'] and d['totals']['fat'] > 0 else None for d in days]
    carb_vals = [d['totals']['carb'] if d['logged'] and d['totals']['carb'] > 0 else None for d in days]

    has_any = any(v for v in protein_vals + fat_vals + carb_vals if v)
    if not has_any:
        return ''

    html = ''
    # Legend
    html += '<div class="macro-legend">\n'
    html += '  <div class="macro-legend-item"><div class="macro-legend-dot" style="background:#6bcb8b;opacity:0.75;"></div>达标</div>\n'
    html += '  <div class="macro-legend-item"><div class="macro-legend-dot" style="background:#c8e6c9;opacity:0.75;"></div>偏低</div>\n'
    html += '  <div class="macro-legend-item"><div class="macro-legend-dot" style="background:#fdd0b1;opacity:0.75;"></div>超标</div>\n'
    html += '</div>\n'

    # Charts
    if any(v for v in carb_vals if v):
        html += gen_macro_chart('碳水', carb_vals, carb_range[0], carb_range[1])
    if any(v for v in protein_vals if v):
        html += gen_macro_chart('蛋白质', protein_vals, protein_range[0], protein_range[1])
    if any(v for v in fat_vals if v):
        html += gen_macro_chart('脂肪', fat_vals, fat_range[0], fat_range[1])

    if summary.get('macro_estimated'):
        html += '<p style="font-size:0.82rem;color:#888;margin-top:0.5rem;">* 部分天数记录不全，缺失餐次按本周同类餐平均值估算</p>\n'

    return html


# ─── Full page assembly ──────────────────────────────────────────────────────

def generate_html(data, args):
    meta = data['meta']
    plan = data['plan']
    summary = data['summary']
    days = data['days']
    weight = data.get('weight', {})
    weight_readings = weight.get('readings', [])

    week_num = meta.get('week_number', 1)
    start_date = meta['start_date']
    end_date = meta['end_date']

    # Parse commentary if provided
    commentary = {}
    if args.commentary:
        try:
            commentary = json.loads(args.commentary)
        except:
            pass

    highlights = []
    if args.highlights:
        try:
            highlights = json.loads(args.highlights)
        except:
            pass

    suggestions = []
    if args.suggestions:
        try:
            suggestions = json.loads(args.suggestions)
        except:
            pass

    # Navigation URLs
    prev_start = meta.get('prev_start', '')
    next_start = meta.get('next_start', '')
    username = args.username or 'unknown'
    base_url = f'https://nanorhino.ai/user/{username}'
    prev_url = f'{base_url}/weekly-report-{prev_start}.html' if prev_start else '#'
    next_url = f'{base_url}/weekly-report-{next_start}.html' if next_start else '#'
    prev_disabled = '' if meta.get('prev_exists') else ' disabled'
    next_disabled = ' disabled'  # Current week never has next

    # Build page
    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>📊 第{week_num}周周报</title>
<style>
{CSS}
</style>
</head>
<body>
<div class="page">
  <nav class="week-nav">
    <a class="week-nav-btn week-nav-prev{prev_disabled}" href="{prev_url}">← 上一周</a>
    <span class="week-nav-current">第{week_num}周</span>
    <a class="week-nav-btn week-nav-next{next_disabled}" href="{next_url}">下一周 →</a>
  </nav>

  <header class="report-header">
    <h1>📊 第{week_num}周周报</h1>
    <div class="subtitle">{start_date} ~ {end_date}</div>
  </header>

'''

    # ── Section 1: Logging Calendar ──
    html += '  <div class="report-card">\n'
    html += '    <div class="card-header">📅 记录日历</div>\n'
    html += '    <div class="card-body">\n'
    html += '      <div class="logging-grid">\n'
    for d in days:
        html += f'        <div class="day-label">{d["weekday"]}</div>\n'
    html += '      </div>\n'
    html += '      <div class="logging-grid">\n'
    for d in days:
        emoji = '✅' if d['logged'] and d['totals']['cal'] > 0 else '—'
        html += f'        <div class="day-status">{emoji}</div>\n'
    html += '      </div>\n'
    logged = summary['logged_days']
    total = summary['total_days']
    html += f'      <div class="logging-summary">记录 {logged}/{total} 天</div>\n'
    html += '    </div>\n'
    if commentary.get('logging'):
        html += f'    <div class="card-commentary">{commentary["logging"]}</div>\n'
    html += '  </div>\n\n'

    # ── Section 2: Calorie Analysis ──
    cal_min = summary.get('cal_min', plan['cal_min'][0] if isinstance(plan['cal_min'], list) else plan['cal_min'])
    cal_max_target = summary.get('cal_max_target', plan['cal_min'][1] if isinstance(plan['cal_min'], list) else 2000)
    if isinstance(plan['cal_min'], list):
        cal_min = plan['cal_min'][0]
        cal_max_target = plan['cal_min'][1]
    chart_max = summary.get('chart_max', max(max(d['totals']['cal'] for d in days if d['logged']), cal_max_target * 1.2))

    html += '  <div class="report-card">\n'
    html += '    <div class="card-header">🔥 热量分析</div>\n'
    html += '    <div class="card-body">\n'
    html += gen_calorie_chart(days, cal_min, cal_max_target, chart_max)
    html += f'      <div class="cal-average">日均 {summary["cal_avg"]} kcal <span class="sub">（目标 {cal_min}–{cal_max_target}）</span></div>\n'
    html += '    </div>\n'
    if commentary.get('calories'):
        html += f'    <div class="card-commentary">{commentary["calories"]}</div>\n'
    html += '  </div>\n\n'

    # ── Section 3: Weight Chart ──
    if weight_readings:
        # Use all historical weight data for the chart (includes pre-week readings)
        all_weight = data.get('weight_all', weight_readings)
        if not all_weight:
            all_weight = weight_readings
        html += '  <div class="report-card">\n'
        html += '    <div class="card-header">⚖️ 体重记录</div>\n'
        html += '    <div class="card-body">\n'
        html += gen_weight_chart(weight_readings, all_weight, meta, args.plan_rate)
        html += '    </div>\n'
        if commentary.get('weight'):
            html += f'    <div class="card-commentary">{commentary["weight"]}</div>\n'
        html += '  </div>\n\n'

    # ── Section 4: Macronutrient Analysis ──
    macro_html = gen_macro_section(days, plan, summary)
    if macro_html:
        html += '  <div class="report-card">\n'
        html += '    <div class="card-header">🥗 营养素分析</div>\n'
        html += '    <div class="card-body">\n'
        html += macro_html
        html += '    </div>\n'
        if commentary.get('macros'):
            html += f'    <div class="card-commentary">{commentary["macros"]}</div>\n'
        html += '  </div>\n\n'

    # ── Section 5: Highlights & Suggestions ──
    if highlights or suggestions:
        html += '  <div class="report-card">\n'
        html += '    <div class="card-header">✨ 本周亮点 & 建议</div>\n'
        html += '    <div class="card-body">\n'
        if highlights:
            html += '      <div class="section-subtitle">亮点</div>\n'
            html += '      <ul class="achievement-list">\n'
            for h in highlights:
                html += f'        <li>{h}</li>\n'
            html += '      </ul>\n'
        if highlights and suggestions:
            html += '      <hr class="suggestions-divider">\n'
        if suggestions:
            html += '      <div class="section-subtitle">下周建议</div>\n'
            html += '      <ul class="suggestion-list">\n'
            for s in suggestions:
                html += f'        <li>{s}</li>\n'
            html += '      </ul>\n'
        html += '    </div>\n'
        html += '  </div>\n\n'

    # ── Footer ──
    html += '  <div class="report-footer">NanoRhino · 小犀牛营养师</div>\n'
    html += '</div>\n'

    # Scroll to right for weight chart
    html += '''<script>
document.addEventListener('DOMContentLoaded', function() {
  var c = document.getElementById('weightChartContainer');
  if (c) c.scrollLeft = c.scrollWidth;
});
</script>
'''
    html += '</body>\n</html>\n'
    return html


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Generate weekly report HTML from collected data.')
    parser.add_argument('--output', '-o', required=True, help='Output HTML file path')
    parser.add_argument('--data-file', help='JSON data file (default: read from stdin)')
    parser.add_argument('--commentary', help='JSON object with section commentaries')
    parser.add_argument('--highlights', help='JSON array of highlight strings')
    parser.add_argument('--suggestions', help='JSON array of suggestion strings')
    parser.add_argument('--plan-rate', type=float, default=0.5, help='Planned weight loss rate kg/week')
    parser.add_argument('--username', help='Username for navigation URLs')
    args = parser.parse_args()

    if args.data_file:
        with open(args.data_file) as f:
            data = json.load(f)
    else:
        data = json.load(sys.stdin)

    html = generate_html(data, args)

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, 'w') as f:
        f.write(html)

    print(f"[generate-report-html] Written {len(html)} bytes to {args.output}")


if __name__ == '__main__':
    main()
