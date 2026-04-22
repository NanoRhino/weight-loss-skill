#!/bin/bash
set -euo pipefail

# should-send-report.sh — Quick gate check for weekly report eligibility.
# Exit 0 + prints "yes" if report should be sent.
# Exit 0 + prints "no: <reason>" if not.
#
# Usage: bash should-send-report.sh --workspace-dir <path> [--min-days 2]

WORKSPACE=""
MIN_DAYS=2

while [[ $# -gt 0 ]]; do
  case "$1" in
    --workspace-dir) WORKSPACE="$2"; shift 2 ;;
    --min-days) MIN_DAYS="$2"; shift 2 ;;
    *) shift ;;
  esac
done

if [[ -z "$WORKSPACE" ]]; then
  echo "no: missing --workspace-dir"
  exit 0
fi

# 1. health-profile must exist
if [[ ! -f "$WORKSPACE/health-profile.md" ]]; then
  echo "no: no health-profile.md"
  exit 0
fi

# 2. Run check-stage to ensure engagement.json is current, then check stage
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CHECK_STAGE="$SCRIPT_DIR/../../notification-manager/scripts/check-stage.py"
if [[ -f "$CHECK_STAGE" ]]; then
  python3.11 "$CHECK_STAGE" --workspace-dir "$WORKSPACE" --tz-offset 28800 2>/dev/null || true
fi

ENG="$WORKSPACE/data/engagement.json"
if [[ -f "$ENG" ]]; then
  STAGE=$(python3.11 -c "import json; print(json.load(open('$ENG')).get('notification_stage', 1))" 2>/dev/null || echo "1")
  if [[ "$STAGE" -ge 2 ]]; then
    echo "no: stage=$STAGE (recall/inactive)"
    exit 0
  fi
fi

# 3. count days with food data this week (Mon-Sun)
MEALS_DIR="$WORKSPACE/data/meals"
if [[ ! -d "$MEALS_DIR" ]]; then
  echo "no: no meals directory"
  exit 0
fi

# Get this week's Monday (or last Monday if today is Sun)
DOW=$(date +%u)  # 1=Mon, 7=Sun
if [[ "$DOW" -eq 7 ]]; then
  MONDAY=$(date -d "6 days ago" +%Y-%m-%d)
else
  MONDAY=$(date -d "$((DOW-1)) days ago" +%Y-%m-%d)
fi
SUNDAY=$(date -d "$MONDAY + 6 days" +%Y-%m-%d)

DAYS_WITH_DATA=0
for f in "$MEALS_DIR"/*.json; do
  [[ -f "$f" ]] || continue
  FNAME=$(basename "$f" .json)
  # Extract date from filename (format: YYYY-MM-DD or YYYY-MM-DD-meal)
  FDATE="${FNAME:0:10}"
  if [[ "$FDATE" > "$MONDAY" || "$FDATE" == "$MONDAY" ]] && [[ "$FDATE" < "$SUNDAY" || "$FDATE" == "$SUNDAY" ]]; then
    # Check if file has actual food data (not empty/skeleton)
    HAS_DATA=$(python3.11 -c "
import json
d = json.load(open('$f'))
if isinstance(d, list):
    has = any(m.get('items') or m.get('foods') for m in d if isinstance(m, dict))
elif isinstance(d, dict):
    has = bool(d.get('items') or d.get('foods'))
else:
    has = False
print('yes' if has else 'no')
" 2>/dev/null || echo "no")
    if [[ "$HAS_DATA" == "yes" ]]; then
      DAYS_WITH_DATA=$((DAYS_WITH_DATA + 1))
    fi
  fi
done

if [[ "$DAYS_WITH_DATA" -lt "$MIN_DAYS" ]]; then
  echo "no: only $DAYS_WITH_DATA days with data (need $MIN_DAYS)"
  exit 0
fi

echo "yes"
