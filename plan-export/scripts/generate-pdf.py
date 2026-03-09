#!/usr/bin/env python3
"""
generate-pdf.py — Convert Markdown to a beautifully styled PDF using WeasyPrint.

Usage: python3 generate-pdf.py <input.md> [output.pdf]
"""

import sys
import os
import markdown
from weasyprint import HTML

def get_html_template(body_html: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Noto+Sans+SC:wght@300;400;500;700&display=swap');

@page {{
    size: A4;
    margin: 22mm 18mm 22mm 18mm;
    @bottom-center {{
        content: counter(page) " / " counter(pages);
        font-family: 'Inter', sans-serif;
        font-size: 9px;
        color: #94a3b8;
    }}
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
    font-size: 12px;
}}

/* ── Main Title ── */
h1 {{
    font-size: 24px;
    font-weight: 700;
    color: #0f172a;
    margin-bottom: 6px;
    padding-bottom: 10px;
    border-bottom: 3px solid #3b82f6;
}}

/* ── Section Headers ── */
h2 {{
    font-size: 15px;
    font-weight: 600;
    color: #1e40af;
    margin-top: 22px;
    margin-bottom: 10px;
    padding: 6px 0 6px 12px;
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
    font-size: 13px;
    font-weight: 600;
    color: #334155;
    margin-top: 14px;
    margin-bottom: 6px;
}}

/* ── Metadata (subtitle lines after h1) ── */
h1 + p, h1 + p + p, h1 + p + p + p {{
    font-size: 11.5px;
    color: #64748b;
    margin-bottom: 2px;
    line-height: 1.5;
}}

/* ── Tables ── */
table {{
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
    margin: 10px 0 16px;
    font-size: 11.5px;
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
    font-size: 11px;
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
    padding-left: 22px;
    margin: 8px 0;
}}

li {{
    margin-bottom: 5px;
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
    margin: 18px 0;
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
    font-size: 11px;
    font-family: 'SF Mono', 'Fira Code', monospace;
}}

/* ── Blockquotes (callouts) ── */
blockquote {{
    background: #f0fdf4;
    border-left: 4px solid #22c55e;
    padding: 12px 16px;
    margin: 12px 0;
    border-radius: 0 8px 8px 0;
    font-size: 11.5px;
    color: #166534;
}}

blockquote p {{
    margin: 4px 0;
}}

/* ── Paragraphs ── */
p {{
    margin: 6px 0;
    line-height: 1.65;
}}

/* ── Links ── */
a {{
    color: #2563eb;
    text-decoration: none;
}}

</style>
</head>
<body>
{body_html}
</body>
</html>"""


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 generate-pdf.py <input.md> [output.pdf]", file=sys.stderr)
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else input_path.rsplit('.', 1)[0] + '.pdf'

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

    # Generate PDF
    HTML(string=full_html).write_pdf(output_path)

    print(f"PDF generated: {output_path}")


if __name__ == '__main__':
    main()
