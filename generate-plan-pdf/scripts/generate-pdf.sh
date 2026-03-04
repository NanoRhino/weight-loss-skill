#!/usr/bin/env bash
#
# generate-pdf.sh — Convert a Markdown file to a styled PDF using WeasyPrint
#
# Usage: generate-pdf.sh <input.md> [output.pdf]
#
# If output is omitted, writes to <input-basename>.pdf in the same directory.
# Requires: python3, weasyprint, markdown (pip packages)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

INPUT="${1:?Usage: generate-pdf.sh <input.md> [output.pdf]}"
OUTPUT="${2:-${INPUT%.md}.pdf}"

if [[ ! -f "$INPUT" ]]; then
  echo "Error: Input file not found: $INPUT" >&2
  exit 1
fi

python3 "$SCRIPT_DIR/generate-pdf.py" "$INPUT" "$OUTPUT"
