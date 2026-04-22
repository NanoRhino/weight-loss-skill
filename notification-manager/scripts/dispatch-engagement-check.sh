#!/usr/bin/env bash
set -euo pipefail

# dispatch-engagement-check.sh — Run check-stage.py for ALL user workspaces.
# Ensures engagement stage is updated even for users without meal/weight crons.
# Designed to run as a global cron job once daily (e.g., 10:00 AM).
#
# Usage:
#   bash dispatch-engagement-check.sh [--tz-offset 28800] [--dry-run]

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CHECK_STAGE="$SCRIPT_DIR/check-stage.py"
PYTHON="${PYTHON:-python3.11}"
TZ_OFFSET="${TZ_OFFSET:-28800}"  # default: Asia/Shanghai (+8h)
DRY_RUN=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tz-offset) TZ_OFFSET="$2"; shift 2 ;;
    --dry-run)   DRY_RUN=true; shift ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

OPENCLAW_DIR="${HOME}/.openclaw"
count=0
updated=0

for ws in "$OPENCLAW_DIR"/workspace-wechat-dm-* "$OPENCLAW_DIR"/workspace-wecom-dm-*; do
  [[ -d "$ws" ]] || continue
  
  # Skip if no engagement.json and no meal data (brand new / empty workspace)
  engagement="$ws/data/engagement.json"
  meals_dir="$ws/data/meals"
  [[ -f "$engagement" ]] || [[ -d "$meals_dir" ]] || continue
  
  username=$(basename "$ws" | sed 's/workspace-\(wechat\|wecom\)-dm-//')
  count=$((count + 1))
  
  if $DRY_RUN; then
    echo "[dry-run] Would check: $username ($ws)"
    continue
  fi
  
  # Run check-stage.py, capture stdout (stage days_silent) and stderr (logs)
  stdout=$($PYTHON "$CHECK_STAGE" --workspace-dir "$ws" --tz-offset "$TZ_OFFSET" 2>/dev/null) || true
  
  stage=$(echo "$stdout" | awk '{print $1}')
  days=$(echo "$stdout" | awk '{print $2}')
  stage=${stage:-"?"}
  days=${days:-"?"}
  
  echo "[$username] stage=$stage days_silent=$days"
  updated=$((updated + 1))
done

echo ""
echo "Done: checked $updated/$count user workspaces"
