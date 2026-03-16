#!/usr/bin/env bash
#
# generate-and-send.sh — Convert Markdown to styled HTML/PDF and deliver to user
#
# HTML+S3 mode (default when --bucket is provided):
#   Generates HTML, uploads to S3, writes plan-url.json, outputs presigned URL.
#   The agent is responsible for sending the URL to the user via the message tool.
#
# PDF fallback (when --bucket is NOT provided):
#   Generates PDF and uploads to Slack via send-to-slack.sh (legacy behavior).
#
# Usage:
#   # Weight loss plan (default template):
#   generate-and-send.sh --agent <id> --input PLAN.md \
#     --bucket <s3-bucket> [--workspace <path>] [--key weight-loss-plan]
#
#   # Meal plan (meal-plan template):
#   generate-and-send.sh --agent <id> --input MEAL-PLAN.md \
#     --bucket <s3-bucket> --template meal-plan [--workspace <path>] [--key meal-plan]
#
#   # PDF fallback:
#   generate-and-send.sh --agent <id> --input <file.md> \
#     [--message <text>] [--filename <display-name>]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

AGENT=""
INPUT=""
MESSAGE=""
FILENAME=""
BUCKET=""
WORKSPACE=""
TEMPLATE=""
KEY=""
USERNAME=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --agent)     AGENT="$2"; shift 2 ;;
    --input)     INPUT="$2"; shift 2 ;;
    --message)   MESSAGE="$2"; shift 2 ;;
    --filename)  FILENAME="$2"; shift 2 ;;
    --bucket)    BUCKET="$2"; shift 2 ;;
    --workspace) WORKSPACE="$2"; shift 2 ;;
    --template)  TEMPLATE="$2"; shift 2 ;;
    --key)       KEY="$2"; shift 2 ;;
    --username)  USERNAME="$2"; shift 2 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "$AGENT" ]]; then echo "ERROR: --agent is required" >&2; exit 1; fi
if [[ -z "$INPUT" ]]; then echo "ERROR: --input is required" >&2; exit 1; fi
if [[ ! -f "$INPUT" ]]; then echo "ERROR: Input file not found: $INPUT" >&2; exit 1; fi

# ── HTML+S3 mode ──
if [[ -n "$BUCKET" ]]; then
  HTML_OUTPUT="${INPUT%.md}.html"

  echo "=== Step 1: Generating HTML ===" >&2
  case "$TEMPLATE" in
    meal-plan)
      python3 "$SCRIPT_DIR/generate-meal-plan-html.py" "$INPUT" "$HTML_OUTPUT" >&2
      ;;
    exercise-plan)
      python3 "$SCRIPT_DIR/generate-exercise-plan-html.py" "$INPUT" "$HTML_OUTPUT" >&2
      ;;
    *)
      python3 "$SCRIPT_DIR/generate-html.py" "$INPUT" "$HTML_OUTPUT" >&2
      ;;
  esac

  echo "" >&2
  echo "=== Step 2: Uploading to S3 ===" >&2
  if [[ -z "$USERNAME" ]]; then echo "ERROR: --username is required for S3 upload" >&2; exit 1; fi
  if [[ -z "$KEY" ]]; then echo "ERROR: --key is required for S3 upload" >&2; exit 1; fi
  UPLOAD_ARGS=(--file "$HTML_OUTPUT" --bucket "$BUCKET" --username "$USERNAME" --key "$KEY")
  if [[ -n "$WORKSPACE" ]]; then
    UPLOAD_ARGS+=(--workspace "$WORKSPACE")
  fi
  URL=$(bash "$SCRIPT_DIR/upload-to-s3.sh" "${UPLOAD_ARGS[@]}")

  echo "" >&2
  echo "=== Step 3: Cleaning up local HTML ===" >&2
  rm -f "$HTML_OUTPUT"
  echo "Deleted: $HTML_OUTPUT" >&2

  echo "" >&2
  echo "✅ Done! HTML generated, uploaded to S3, local copy removed." >&2
  echo "URL: $URL" >&2

  # Output URL to stdout for the agent to use with message tool
  echo "$URL"
  exit 0
fi

# ── PDF fallback ──
OUTPUT="${INPUT%.md}.pdf"

if [[ -z "$FILENAME" ]]; then
  FILENAME="$(basename "$OUTPUT")"
fi

echo "=== Step 1: Generating PDF ===" >&2
python3 "$SCRIPT_DIR/generate-pdf.py" "$INPUT" "$OUTPUT" >&2

echo "" >&2
echo "=== Step 2: Sending to Slack ===" >&2
SEND_ARGS=(--agent "$AGENT" --file "$OUTPUT" --filename "$FILENAME")
if [[ -n "$MESSAGE" ]]; then
  SEND_ARGS+=(--message "$MESSAGE")
fi
bash "$SCRIPT_DIR/send-to-slack.sh" "${SEND_ARGS[@]}" >&2

echo "" >&2
echo "=== Step 3: Cleaning up local PDF ===" >&2
rm -f "$OUTPUT"
echo "Deleted: $OUTPUT" >&2

echo "" >&2
echo "✅ Done! PDF generated, sent via Slack, and local copy removed." >&2
