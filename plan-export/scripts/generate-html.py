#!/usr/bin/env python3
"""
generate-html.py — Convert Markdown to a beautifully styled standalone HTML file.

Usage: python3 generate-html.py <input.md> [output.html] [--username NAME] [--date DATE]

Reuses the same HTML template and CSS as generate-pdf.py but outputs HTML
instead of PDF (no WeasyPrint dependency needed).
"""

import sys
import os
import markdown
import re
import argparse
from datetime import datetime, timezone, timedelta


def get_html_template(body_html: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Noto+Sans+SC:wght@300;400;500;700&display=swap');

@page {{
    size: A4;
    margin: 22mm 18mm 22mm 18mm;
}}

* {{
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}}

body {{
    font-family: 'Inter', 'Noto Sans SC', system-ui, -apple-system, 'Segoe UI', sans-serif;
    color: #333;
    line-height: 1.65;
    font-size: 14px;
    max-width: 800px;
    margin: 0 auto;
    padding: 0 1.5rem 2rem;
    background: #faf9f5;
    -webkit-text-size-adjust: 100%;
}}

/* ── Main Title ── */
h1 {{
    font-size: 1.4rem;
    font-weight: 700;
    color: #D73C63;
    margin-top: 1.5rem;
    margin-bottom: 0.3rem;
    padding-bottom: 10px;
    border-bottom: 2px solid #e0ddd5;
    text-align: center;
}}

/* ── Section Headers ── */
h2 {{
    font-size: 0.95rem;
    font-weight: 600;
    color: #D73C63;
    margin-top: 1.5rem;
    margin-bottom: 0;
    padding: 0.6rem 1rem;
    background: #fff;
}}

/* ── Card-style sections ── */
.section-card {{
    background: #fff;
    border: 1px solid #e0ddd5;
    border-radius: 12px;
    margin-bottom: 1.5rem;
    overflow: hidden;
}}
.section-card h2 {{
    margin-top: 0;
    border-radius: 0;
    border: none;
    border-bottom: 1px solid #f0ede5;
}}
.section-card .section-body {{
    padding: 0.8rem 1rem;
}}

h3 {{
    font-size: 0.85rem;
    font-weight: 600;
    color: #D73C63;
    margin-top: 14px;
    margin-bottom: 6px;
}}

/* ── Metadata (subtitle lines after h1) ── */
.plan-meta {{
    text-align: center;
    margin-bottom: 1.2rem;
}}
.plan-meta p {{
    font-size: 0.85rem;
    color: #666;
    margin: 2px 0;
    line-height: 1.5;
}}

h1 + p, h1 + p + p, h1 + p + p + p {{
    font-size: 0.85rem;
    color: #666;
    margin-bottom: 2px;
    line-height: 1.5;
    text-align: center;
}}

/* ── Tables ── */
table {{
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
    margin: 12px 0 20px;
    font-size: 13px;
    border-radius: 8px;
    overflow: hidden;
    border: 1px solid #e0ddd5;
    background: #fff;
}}

thead th {{
    background: #D73C63;
    color: white;
    font-weight: 600;
    padding: 10px 14px;
    text-align: left;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}}

tbody td {{
    padding: 9px 14px;
    border-bottom: 1px solid #f0ede5;
    vertical-align: top;
}}

tbody tr:nth-child(even) {{
    background: #faf9f5;
}}

tbody tr:last-child td {{
    border-bottom: none;
}}

/* First column styling */
tbody td:first-child {{
    font-weight: 500;
    color: #333;
    white-space: nowrap;
}}

/* Value column */
tbody td:last-child {{
    color: #555;
}}

/* ── Lists ── */
ul, ol {{
    padding-left: 24px;
    margin: 10px 0;
}}

li {{
    margin-bottom: 6px;
    line-height: 1.6;
    color: #444;
}}

li strong {{
    color: #333;
}}

/* ── Horizontal Rules ── */
hr {{
    border: none;
    border-top: 1px solid #e0ddd5;
    margin: 22px 0;
}}

/* ── Inline elements ── */
strong {{
    font-weight: 600;
    color: #333;
}}

em {{
    color: #666;
    font-style: italic;
}}

code {{
    background: #f0ede5;
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 13px;
    font-family: 'SF Mono', 'Fira Code', monospace;
}}

/* ── Blockquotes (callouts) ── */
blockquote {{
    background: #fff;
    border-left: 4px solid #D73C63;
    padding: 14px 18px;
    margin: 14px 0;
    border-radius: 0 8px 8px 0;
    font-size: 0.85rem;
    color: #555;
    border: 1px solid #e0ddd5;
    border-left: 4px solid #D73C63;
}}

blockquote p {{
    margin: 4px 0;
}}

/* ── Paragraphs ── */
p {{
    margin: 8px 0;
    line-height: 1.65;
}}

/* ── Links ── */
a {{
    color: #D73C63;
    text-decoration: none;
}}

a:hover {{
    text-decoration: underline;
}}

/* ── Responsive ── */
@media (max-width: 600px) {{
    body {{
        font-size: 13px;
        padding: 0 1rem 2rem;
    }}
    h1 {{ font-size: 1.2rem; }}
    h2 {{ font-size: 0.9rem; }}
    table {{ font-size: 12px; }}
    thead th, tbody td {{ padding: 6px 8px; }}
}}

</style>
</head>
<body>
{body_html}
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(description="Convert Markdown to styled HTML")
    parser.add_argument("input", help="Input Markdown file")
    parser.add_argument("output", nargs="?", help="Output HTML file")
    parser.add_argument("--username", help="User display name (shown below title)")
    parser.add_argument("--date", help="Date string (shown below username). Default: today")
    args = parser.parse_args()

    input_path = args.input
    output_path = args.output or input_path.rsplit('.', 1)[0] + '.html'

    if not os.path.isfile(input_path):
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    # Read Markdown
    with open(input_path, 'r', encoding='utf-8') as f:
        md_text = f.read()

    # Convert Markdown to HTML
    body_html = markdown.markdown(
        md_text,
        extensions=['tables', 'fenced_code', 'nl2br', 'sane_lists']
    )

    # Wrap sections in card divs (h2 + content until next h2)
    parts = re.split(r'(<h2>.*?</h2>)', body_html)
    wrapped = ''
    i = 0
    while i < len(parts):
        part = parts[i]
        if part.startswith('<h2>'):
            # Collect all content until next h2
            body_content = ''
            i += 1
            while i < len(parts) and not parts[i].startswith('<h2>'):
                body_content += parts[i]
                i += 1
            wrapped += '<div class="section-card">' + part + '<div class="section-body">' + body_content + '</div></div>'
        else:
            wrapped += part
            i += 1
    body_html = wrapped

    # Insert username and date after <h1>...</h1>
    if args.username or args.date:
        date_str = args.date or datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
        meta_lines = []
        if args.username:
            meta_lines.append(f'<p>{args.username}</p>')
        meta_lines.append(f'<p>{date_str}</p>')
        meta_html = '<div class="plan-meta">' + ''.join(meta_lines) + '</div>'
        # Insert after closing </h1>
        body_html = re.sub(r'(</h1>)', r'\1' + meta_html, body_html, count=1)

    # Wrap in styled template
    full_html = get_html_template(body_html)

    # Write HTML file
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(full_html)

    print(f"HTML generated: {output_path}")


if __name__ == '__main__':
    main()
