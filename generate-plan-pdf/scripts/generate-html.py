#!/usr/bin/env python3
"""
generate-html.py — Convert Markdown to a beautifully styled standalone HTML file.

Usage: python3 generate-html.py <input.md> [output.html]

Reuses the same HTML template and CSS as generate-pdf.py but outputs HTML
instead of PDF (no WeasyPrint dependency needed).
"""

import sys
import os
import markdown


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
    font-family: 'Inter', 'Noto Sans SC', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    color: #1e293b;
    line-height: 1.65;
    font-size: 15px;
    max-width: 800px;
    margin: 0 auto;
    padding: 32px 24px;
    background: #ffffff;
}}

/* ── Main Title ── */
h1 {{
    font-size: 28px;
    font-weight: 700;
    color: #0f172a;
    margin-bottom: 6px;
    padding-bottom: 10px;
    border-bottom: 3px solid #3b82f6;
}}

/* ── Section Headers ── */
h2 {{
    font-size: 18px;
    font-weight: 600;
    color: #1e40af;
    margin-top: 28px;
    margin-bottom: 12px;
    padding: 8px 0 8px 14px;
    border-left: 4px solid #3b82f6;
    background: linear-gradient(90deg, #eff6ff 0%, transparent 100%);
}}

/* Special section colors */
h2:nth-of-type(3), h2:nth-of-type(4) {{
    border-left-color: #10b981;
    background: linear-gradient(90deg, #ecfdf5 0%, transparent 100%);
    color: #065f46;
}}

h2:nth-of-type(5), h2:nth-of-type(6) {{
    border-left-color: #f59e0b;
    background: linear-gradient(90deg, #fffbeb 0%, transparent 100%);
    color: #92400e;
}}

h3 {{
    font-size: 16px;
    font-weight: 600;
    color: #334155;
    margin-top: 18px;
    margin-bottom: 8px;
}}

/* ── Metadata (subtitle lines after h1) ── */
h1 + p, h1 + p + p, h1 + p + p + p {{
    font-size: 14px;
    color: #64748b;
    margin-bottom: 2px;
    line-height: 1.5;
}}

/* ── Tables ── */
table {{
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
    margin: 12px 0 20px;
    font-size: 14px;
    border-radius: 8px;
    overflow: hidden;
    border: 1px solid #e2e8f0;
}}

thead th {{
    background: #1e40af;
    color: white;
    font-weight: 600;
    padding: 10px 14px;
    text-align: left;
    font-size: 13px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}}

tbody td {{
    padding: 9px 14px;
    border-bottom: 1px solid #f1f5f9;
    vertical-align: top;
}}

tbody tr:nth-child(even) {{
    background: #f8fafc;
}}

tbody tr:last-child td {{
    border-bottom: none;
}}

/* First column styling */
tbody td:first-child {{
    font-weight: 500;
    color: #1e293b;
    white-space: nowrap;
}}

/* Value column */
tbody td:last-child {{
    color: #475569;
}}

/* ── Lists ── */
ul, ol {{
    padding-left: 24px;
    margin: 10px 0;
}}

li {{
    margin-bottom: 6px;
    line-height: 1.6;
    color: #334155;
}}

li strong {{
    color: #1e293b;
}}

/* ── Horizontal Rules ── */
hr {{
    border: none;
    border-top: 1px solid #e2e8f0;
    margin: 22px 0;
}}

/* ── Inline elements ── */
strong {{
    font-weight: 600;
    color: #0f172a;
}}

em {{
    color: #64748b;
    font-style: italic;
}}

code {{
    background: #f1f5f9;
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 13px;
    font-family: 'SF Mono', 'Fira Code', monospace;
}}

/* ── Blockquotes (callouts) ── */
blockquote {{
    background: #f0fdf4;
    border-left: 4px solid #22c55e;
    padding: 14px 18px;
    margin: 14px 0;
    border-radius: 0 8px 8px 0;
    font-size: 14px;
    color: #166534;
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
    color: #2563eb;
    text-decoration: none;
}}

a:hover {{
    text-decoration: underline;
}}

/* ── Responsive ── */
@media (max-width: 600px) {{
    body {{
        font-size: 14px;
        padding: 16px 12px;
    }}
    h1 {{ font-size: 22px; }}
    h2 {{ font-size: 16px; }}
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
    if len(sys.argv) < 2:
        print("Usage: python3 generate-html.py <input.md> [output.html]", file=sys.stderr)
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else input_path.rsplit('.', 1)[0] + '.html'

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

    # Wrap in styled template
    full_html = get_html_template(body_html)

    # Write HTML file
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(full_html)

    print(f"HTML generated: {output_path}")


if __name__ == '__main__':
    main()
