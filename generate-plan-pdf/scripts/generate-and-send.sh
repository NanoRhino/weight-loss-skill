#!/usr/bin/env bash
#
# generate-and-send.sh — Convert Markdown to styled PDF and send via Slack
#
# Usage: generate-and-send.sh --agent <id> --input <file.md> [--message <text>] [--filename <display-name>]
#
# Example:
#   generate-and-send.sh --agent 007-zhuoran --input PLAN.md --message "📋 这是你的体重管理计划" --filename "体重管理计划.pdf"

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

AGENT=""
INPUT=""
MESSAGE=""
FILENAME=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --agent)    AGENT="$2"; shift 2 ;;
    --input)    INPUT="$2"; shift 2 ;;
    --message)  MESSAGE="$2"; shift 2 ;;
    --filename) FILENAME="$2"; shift 2 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "$AGENT" ]]; then echo "ERROR: --agent is required" >&2; exit 1; fi
if [[ -z "$INPUT" ]]; then echo "ERROR: --input is required" >&2; exit 1; fi

# Resolve input path (relative to cwd)
if [[ ! -f "$INPUT" ]]; then
  echo "ERROR: Input file not found: $INPUT" >&2
  exit 1
fi

# Generate output path
OUTPUT="${INPUT%.md}.pdf"

# Default filename
if [[ -z "$FILENAME" ]]; then
  FILENAME="$(basename "$OUTPUT")"
fi

echo "=== Step 1: Generating PDF ==="
python3 "$SCRIPT_DIR/generate-pdf.py" "$INPUT" "$OUTPUT"

echo ""
echo "=== Step 2: Sending to Slack ==="
SEND_ARGS=(--agent "$AGENT" --file "$OUTPUT" --filename "$FILENAME")
if [[ -n "$MESSAGE" ]]; then
  SEND_ARGS+=(--message "$MESSAGE")
fi
bash "$SCRIPT_DIR/send-to-slack.sh" "${SEND_ARGS[@]}"

echo ""
echo "✅ Done! PDF generated and sent via Slack."
