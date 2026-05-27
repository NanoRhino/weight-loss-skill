#!/bin/bash
# generate-badge-img.sh — Generate badge image by overlaying text on base template
#
# Usage:
#   ./generate-badge-img.sh \
#     --base /path/to/badge-base-levelN.png \
#     --output /path/to/output.png \
#     --line1a "过去7天中有5天" \
#     --line1b "热量处于合理范围" \
#     --line2 "没有极端节食，认真照顾了自己" \
#     --username "小犀牛" \
#     --username-sub "RIRI" \
#     --date "2024.05.20"

set -euo pipefail

# Parse args
while [[ $# -gt 0 ]]; do
  case "$1" in
    --base) BASE="$2"; shift 2;;
    --output) OUTPUT="$2"; shift 2;;
    --line1a) LINE1A="$2"; shift 2;;
    --line1b) LINE1B="$2"; shift 2;;
    --line2) LINE2="$2"; shift 2;;
    --username) USERNAME="$2"; shift 2;;
    --username-sub) USERNAME_SUB="$2"; shift 2;;
    --date) DATE_STR="$2"; shift 2;;
    *) echo "Unknown arg: $1"; exit 1;;
  esac
done

# Defaults
BASE="${BASE:-}"
OUTPUT="${OUTPUT:-/tmp/badge-output.png}"
LINE1A="${LINE1A:-}"
LINE1B="${LINE1B:-}"
LINE2="${LINE2:-}"
USERNAME="${USERNAME:-小犀牛}"
USERNAME_SUB="${USERNAME_SUB:-}"
DATE_STR="${DATE_STR:-}"

if [[ -z "$BASE" || ! -f "$BASE" ]]; then
  echo "ERROR: --base is required and must exist" >&2
  exit 1
fi

FONT="/usr/share/fonts/google-droid/DroidSansFallback.ttf"

# Ensure output dir exists
mkdir -p "$(dirname "$OUTPUT")"

# Layout for 480x480 base image:
#
# Green circle icon is at ~(48, 318). Text starts to its right.
#   Line1a: x:75, y:328 (first line, ~14px)
#   Line1b: x:75, y:348 (second line, ~14px)
#
# Yellow heart icon is at ~(48, 368). Text starts to its right.
#   Line2: x:75, y:380 (~13px)
#
# Bottom left (next to small rhino icon):
#   Username: x:80, y:432 (~13px, bold-ish)
#   Username sub: x:80, y:447 (~10px, lighter color)
#
# Bottom right ("获得时间" label is baked in):
#   Date: x:315, y:445 (~12px)

convert "$BASE" \
  -font "$FONT" \
  -fill '#4a4a4a' \
  -pointsize 14 \
  -annotate +135+328 "$LINE1A" \
  -annotate +135+348 "$LINE1B" \
  -fill '#4a4a4a' \
  -pointsize 13 \
  -annotate +135+380 "$LINE2" \
  -fill '#5a5a5a' \
  -pointsize 13 \
  -annotate +140+432 "$USERNAME" \
  -fill '#999999' \
  -pointsize 10 \
  -annotate +140+447 "$USERNAME_SUB" \
  -fill '#7a7a7a' \
  -pointsize 12 \
  -annotate +375+445 "$DATE_STR" \
  "$OUTPUT"

echo "$OUTPUT"
