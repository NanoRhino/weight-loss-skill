#!/usr/bin/env bash
#
# generate-and-send.sh — Convert Markdown to styled HTML and upload to cloud storage
#
# Generates HTML, uploads to S3/OSS, writes plan-url.json, outputs public URL.
# The agent is responsible for sending the URL to the user via the message tool.
#
# --bucket is optional: upload-to-s3.sh defaults to nanorhino-im-plans (AWS)
# or JD_OSS_BUCKET env var (JD Cloud OSS).
#
# Usage:
#   # Weight loss plan (default template):
#   generate-and-send.sh --agent <id> --input PLAN.md \
#     [--bucket <s3-bucket>] --workspace <path> --key weight-loss-plan
#
#   # Meal plan (diet template — default HTML renderer):
#   generate-and-send.sh --agent <id> --input MEAL-PLAN.md \
#     [--bucket <s3-bucket>] --workspace <path> --key meal-plan
#
#   # 7-day meal plan (structured meal-plan HTML renderer):
#   generate-and-send.sh --agent <id> --input MEAL-PLAN.md \
#     [--bucket <s3-bucket>] --workspace <path> --template meal-plan --key meal-plan

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

AGENT=""
INPUT=""
BUCKET=""
WORKSPACE=""
TEMPLATE=""
KEY=""
USERNAME=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --agent)     AGENT="$2"; shift 2 ;;
    --input)     INPUT="$2"; shift 2 ;;
    --bucket)    BUCKET="$2"; shift 2 ;;
    --workspace) WORKSPACE="$2"; shift 2 ;;
    --template)  TEMPLATE="$2"; shift 2 ;;
    --key)       KEY="$2"; shift 2 ;;
    --username)  USERNAME="$2"; shift 2 ;;
    --message|--filename) shift 2 ;;  # legacy args, ignored
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "$AGENT" ]]; then echo "ERROR: --agent is required" >&2; exit 1; fi
if [[ -z "$INPUT" ]]; then echo "ERROR: --input is required" >&2; exit 1; fi
if [[ ! -f "$INPUT" ]]; then echo "ERROR: Input file not found: $INPUT" >&2; exit 1; fi
if [[ -z "$KEY" ]]; then echo "ERROR: --key is required" >&2; exit 1; fi

# Auto-resolve username from workspace or agent ID
if [[ -z "$USERNAME" && -n "$WORKSPACE" ]]; then
  USERNAME=$(basename "$WORKSPACE")
elif [[ -z "$USERNAME" && -n "$AGENT" ]]; then
  USERNAME="$AGENT"
fi
if [[ -z "$USERNAME" ]]; then echo "ERROR: --username, --workspace, or --agent is required" >&2; exit 1; fi

# ── Step 1: Generate HTML ──
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

# ── Step 2: Upload to cloud storage ──
echo "" >&2
echo "=== Step 2: Uploading ===" >&2

UPLOAD_ARGS=(--file "$HTML_OUTPUT" --username "$USERNAME" --key "$KEY")
if [[ -n "$BUCKET" ]]; then
  UPLOAD_ARGS+=(--bucket "$BUCKET")
fi
if [[ -n "$WORKSPACE" ]]; then
  UPLOAD_ARGS+=(--workspace "$WORKSPACE")
fi
URL=$(bash "$SCRIPT_DIR/upload-to-s3.sh" "${UPLOAD_ARGS[@]}")

# ── Step 3: Cleanup ──
echo "" >&2
echo "=== Step 3: Cleaning up ===" >&2
rm -f "$HTML_OUTPUT"
echo "Deleted: $HTML_OUTPUT" >&2

echo "" >&2
echo "✅ Done! HTML generated, uploaded, local copy removed." >&2
echo "URL: $URL" >&2

# Output URL to stdout
echo "$URL"
