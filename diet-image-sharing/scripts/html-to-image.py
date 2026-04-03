#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["weasyprint>=62", "pymupdf>=1.24", "pillow>=10"]
# ///
"""
html-to-image.py — Convert an HTML file to a PNG image.

Pipeline: HTML → PDF (WeasyPrint) → PNG (PyMuPDF).
No browser binary required.

Usage:
  uv run {baseDir}/scripts/html-to-image.py <input.html> [output.png] [--scale 2]

If output is omitted, writes to <input-basename>.png in the same directory.
"""

import argparse
import io
import sys
import tempfile
from pathlib import Path


def html_to_image(input_path: str, output_path: str, scale: int = 2):
    """Render HTML file to PNG via WeasyPrint (HTML → PDF) + PyMuPDF (PDF → PNG)."""
    from weasyprint import HTML
    import fitz  # PyMuPDF
    from PIL import Image

    input_file = Path(input_path).resolve()
    if not input_file.is_file():
        print(f"Error: File not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    output_file = Path(output_path).resolve()
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Step 1: HTML → PDF in memory
    html = HTML(filename=str(input_file))
    pdf_bytes = html.write_pdf()

    # Step 2: PDF → PNG via PyMuPDF
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    # Render all pages and stack vertically
    images = []
    total_width = 0
    total_height = 0

    for page in doc:
        mat = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        images.append(img)
        total_width = max(total_width, pix.width)
        total_height += pix.height

    doc.close()

    if not images:
        print("Error: no pages rendered", file=sys.stderr)
        sys.exit(1)

    # Combine pages into single image (usually just 1 page for our card)
    if len(images) == 1:
        combined = images[0]
    else:
        combined = Image.new("RGB", (total_width, total_height))
        y_offset = 0
        for img in images:
            combined.paste(img, (0, y_offset))
            y_offset += img.height

    # Trim bottom whitespace: scan from bottom for non-background rows
    # Background color is #f0f4e8 = (240, 244, 232)
    pixels = combined.load()
    bg = (240, 244, 232)
    bottom = combined.height

    for y in range(combined.height - 1, 0, -1):
        row_is_bg = True
        for x in range(0, combined.width, max(1, combined.width // 20)):
            px = pixels[x, y]
            if abs(px[0] - bg[0]) > 15 or abs(px[1] - bg[1]) > 15 or abs(px[2] - bg[2]) > 15:
                row_is_bg = False
                break
        if not row_is_bg:
            bottom = y + int(20 * scale)  # small padding
            break

    if bottom < combined.height:
        combined = combined.crop((0, 0, combined.width, min(bottom, combined.height)))

    combined.save(str(output_file), "PNG", optimize=True)

    print(f"Image saved: {output_file}", file=sys.stderr)
    print(str(output_file))


def main():
    parser = argparse.ArgumentParser(description="Convert HTML to PNG image")
    parser.add_argument("input", help="Input HTML file path")
    parser.add_argument("output", nargs="?", default=None,
                        help="Output PNG file path (default: same name as input)")
    parser.add_argument("--scale", type=int, default=2,
                        help="Scale factor for retina output (default: 2)")
    args = parser.parse_args()

    output = args.output or args.input.rsplit(".", 1)[0] + ".png"
    html_to_image(args.input, output, args.scale)


if __name__ == "__main__":
    main()
