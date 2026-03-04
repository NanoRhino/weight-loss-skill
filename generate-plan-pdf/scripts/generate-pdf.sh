#!/usr/bin/env bash
#
# generate-pdf.sh — Convert a Markdown file to a styled PDF
#
# Usage: generate-pdf.sh <input.md> [output.pdf]
#
# If output is omitted, writes to <input-basename>.pdf in the same directory.
# Requires: md-to-pdf (npm), Chrome/Chromium system libraries

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
STYLESHEET="${SKILL_DIR}/styles/plan.css"

INPUT="${1:?Usage: generate-pdf.sh <input.md> [output.pdf]}"
OUTPUT="${2:-${INPUT%.md}.pdf}"

if [[ ! -f "$INPUT" ]]; then
  echo "Error: Input file not found: $INPUT" >&2
  exit 1
fi

if [[ ! -f "$STYLESHEET" ]]; then
  echo "Error: Stylesheet not found: $STYLESHEET" >&2
  exit 1
fi

# Create temp working directory (md-to-pdf outputs next to input)
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

# Copy input to temp dir
cp "$INPUT" "$TMPDIR/document.md"

# Generate PDF
md-to-pdf "$TMPDIR/document.md" \
  --stylesheet "$STYLESHEET" \
  --pdf-options '{"format":"A4","margin":{"top":"18mm","bottom":"18mm","left":"15mm","right":"15mm"},"printBackground":true}' \
  --launch-options '{"args":["--no-sandbox","--disable-setuid-sandbox","--disable-gpu"]}' \
  2>&1

# Move to desired output location
mv "$TMPDIR/document.pdf" "$OUTPUT"

echo "PDF generated: $OUTPUT"
