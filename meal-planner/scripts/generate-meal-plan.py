#!/usr/bin/env python3
"""Generate an HTML meal plan from JSON data.

Usage:
    python3 generate-meal-plan.py <input.json> [output.html]

If output filename is omitted, defaults to meal-plan-<date>.html.
The output path is printed to stdout for the caller to capture.
"""

import json
import sys
from html import escape as _esc

# ── Day accent colours (7 days) ─────────────────────────────────────────

DAY_COLORS = [
    "#ef4444",  # Day 1 – red
    "#3b82f6",  # Day 2 – blue
    "#10b981",  # Day 3 – green
    "#8b5cf6",  # Day 4 – purple
    "#f59e0b",  # Day 5 – amber
    "#06b6d4",  # Day 6 – cyan
    "#ec4899",  # Day 7 – pink
]

# ── CSS ──────────────────────────────────────────────────────────────────

CSS = """\
*{margin:0;padding:0;box-sizing:border-box}
body{
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,
    "Noto Sans SC","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
  background:#f8f9fa;color:#1a1a2e;line-height:1.6;padding:20px;
}
.ctn{max-width:680px;margin:0 auto}
.hdr{background:#fff;border-radius:16px;padding:28px 32px;margin-bottom:20px;
  box-shadow:0 1px 3px rgba(0,0,0,.08)}
.hdr h1{font-size:24px;margin-bottom:16px}
.meta{display:grid;grid-template-columns:auto 1fr;gap:6px 16px;font-size:14px;color:#555}
.ml{font-weight:600;color:#333}
.day{background:#fff;border-radius:16px;padding:24px 28px;margin-bottom:16px;
  box-shadow:0 1px 3px rgba(0,0,0,.08);border-left:5px solid}
.dh h2{font-size:20px;font-weight:700}
.ds{font-size:14px;color:#666;margin-top:2px}
.meal{padding:12px 0;border-top:1px solid #f0f0f0}
.meal:first-child{border-top:none}
.mh{display:flex;flex-wrap:wrap;align-items:baseline;gap:6px;margin-bottom:2px}
.mn{font-weight:600;font-size:15px}
.mc{font-size:14px;color:#666}
.mm{font-size:13px;color:#999;margin-bottom:2px}
.mt{display:inline-block;background:#fff3e0;color:#e65100;font-size:12px;
  padding:1px 8px;border-radius:10px;font-weight:500}
.mi{font-size:14px;color:#444;line-height:1.8}
.mr{font-size:14px;color:#888;font-style:italic}
.ms{font-size:14px;color:#aaa;font-style:italic}
.tp{font-size:13px;color:#666;margin-top:4px;padding-left:4px;font-style:italic}
.pb{display:block;margin:24px auto;padding:10px 24px;background:#333;color:#fff;
  border:none;border-radius:8px;font-size:14px;cursor:pointer}
.pb:hover{background:#555}
.ft{text-align:center;color:#ccc;font-size:12px;margin:24px 0 8px}
@media print{
  body{background:#fff;padding:0}
  .day{box-shadow:none;break-inside:avoid;border-radius:0;margin-bottom:8px}
  .hdr{box-shadow:none;border-radius:0}
  .pb,.ft{display:none}
}
@media(max-width:600px){
  body{padding:12px}
  .hdr{padding:20px}
  .day{padding:16px 20px}
  .hdr h1{font-size:20px}
  .dh h2{font-size:18px}
}
"""


# ── Render helpers ───────────────────────────────────────────────────────


def _render_meal(m):
    """Render a single meal block."""
    name = _esc(m["n"])

    # Skipped meal (e.g. IF 16:8)
    if m.get("skip"):
        return (
            f'<div class="meal"><div class="mh">'
            f'<span class="mn">{name}</span>'
            f'<span class="ms">— {_esc(m["skip"])}</span>'
            f"</div></div>"
        )

    cal = m.get("cal", "")
    cal_s = f"{cal} kcal" if cal else ""

    # Header pieces
    hdr = f'<span class="mn">{name}</span>'
    if cal_s:
        hdr += f' <span class="mc">{cal_s}</span>'
    if m.get("tag"):
        hdr += f' <span class="mt">{_esc(m["tag"])}</span>'

    # Macros line (optional for snacks)
    macros = ""
    if m.get("p") is not None:
        macros = f'<div class="mm">P {m["p"]}g · C {m["c"]}g · F {m["f"]}g</div>'

    # Content: ref > items
    content = ""
    if m.get("ref"):
        content = f'<div class="mr">← {_esc(m["ref"])}</div>'
    elif m.get("items"):
        content = f'<div class="mi">{_esc(m["items"])}</div>'

    # Tip
    tip = ""
    if m.get("tip"):
        tip = f'<div class="tp">💡 {_esc(m["tip"])}</div>'

    return f'<div class="meal"><div class="mh">{hdr}</div>{macros}{content}{tip}</div>'


def _render_day(day, idx):
    """Render a single day card."""
    color = DAY_COLORS[idx % len(DAY_COLORS)]
    meals = "\n".join(_render_meal(m) for m in day["m"])
    return (
        f'<div class="day" style="border-left-color:{color}">'
        f'<div class="dh"><h2>{_esc(day["d"])}</h2>'
        f'<div class="ds">{day["cal"]} kcal | P {day["p"]}g · C {day["c"]}g · F {day["f"]}g</div></div>'
        f"{meals}</div>"
    )


def render_html(data):
    """Produce the complete HTML document."""
    days = "\n".join(_render_day(d, i) for i, d in enumerate(data["days"]))

    return f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{_esc(data['title'])}</title>
<style>{CSS}</style>
</head>
<body>
<div class="ctn">
  <div class="hdr">
    <h1>{_esc(data['title'])}</h1>
    <div class="meta">
      <span class="ml">📅</span><span>{_esc(data['date'])}</span>
      <span class="ml">🎯</span><span>{_esc(data['target'])}（{_esc(data['range'])}）</span>
      <span class="ml">📋</span><span>{_esc(data['mode'])}</span>
      <span class="ml">📊</span><span>{_esc(data['macros'])}</span>
    </div>
  </div>
  {days}
  <button class="pb" onclick="window.print()">🖨️ Print / Save as PDF</button>
  <div class="ft">Generated by meal-planner skill</div>
</div>
</body>
</html>"""


# ── Main ─────────────────────────────────────────────────────────────────


def main():
    if len(sys.argv) < 2:
        print(
            "Usage: generate-meal-plan.py <input.json> [output.html]",
            file=sys.stderr,
        )
        sys.exit(1)

    with open(sys.argv[1], encoding="utf-8") as f:
        data = json.load(f)

    html = render_html(data)

    if len(sys.argv) > 2:
        out_path = sys.argv[2]
    else:
        out_path = f"meal-plan-{data.get('date', 'plan')}.html"

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    # Print output path so the caller can capture it.
    print(out_path)


if __name__ == "__main__":
    main()
