#!/usr/bin/env bash
set -euo pipefail

# create-reminder.sh — Wrapper for creating cron jobs with correct delivery.
# Agents call this instead of the cron tool directly.
# Supports multiple channels: slack (default), wechat, wecom, etc.
#
# Usage:
#   bash create-reminder.sh --agent <id> --name <name> --message <text> --at <ISO|relative> [--channel <ch>] [--to <dest>]
#   bash create-reminder.sh --agent <id> --name <name> --message <text> --cron <expr> [--tz <tz>] [--channel <ch>] [--to <dest>]
#
# Anti-burst options (for recurring --cron jobs only):
#   --type <meal|weight|other>  Job type for slot window (default: other)
#                               meal/weight: search [-10, +5] minutes around target
#                               other: search [-10, 0] minutes around target
#   --exact                     Skip anti-burst logic, use exact cron time
#
# Examples:
#   # Slack (default, backward-compatible — no --channel needed)
#   bash create-reminder.sh --agent 007-zhuoran --name "午餐提醒" --message "午饭时间到了" --cron "0 12 * * *"
#
#   # WeChat with anti-burst
#   bash create-reminder.sh --agent wechat-dm-accjoh25tsvoasahx0psjfg --channel wechat --type meal --name "午餐提醒" --message "午饭时间到了" --cron "0 12 * * *"
#
#   # Exact time (no adjustment)
#   bash create-reminder.sh --agent some-agent --exact --name "Standup" --message "Standup time" --cron "0 9 * * 1-5"
#
#   # Explicit --to (any channel)
#   bash create-reminder.sh --agent some-agent --channel telegram --to "123456789" --name "提醒" --message "test" --at "2m"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

AGENT=""
NAME=""
MESSAGE=""
AT=""
CRON_EXPR=""
TZ=""
TZ_EXPLICIT=false
DELETE_AFTER_RUN=""
CHANNEL=""
TO=""
JOB_TYPE="other"
EXACT=false

while [[ $# -gt 0 ]]; do
  case $1 in
    --agent)   AGENT="$2"; shift 2 ;;
    --name)    NAME="$2"; shift 2 ;;
    --message) MESSAGE="$2"; shift 2 ;;
    --at)      AT="$2"; shift 2 ;;
    --cron)    CRON_EXPR="$2"; shift 2 ;;
    --tz)      TZ="$2"; TZ_EXPLICIT=true; shift 2 ;;
    --keep)    DELETE_AFTER_RUN="--no-delete-after-run"; shift ;;
    --channel) CHANNEL="$2"; shift 2 ;;
    --to)      TO="$2"; shift 2 ;;
    --type)    JOB_TYPE="$2"; shift 2 ;;
    --exact)   EXACT=true; shift ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

# Default channel: slack (backward-compatible)
if [[ -z "$CHANNEL" ]]; then
  CHANNEL="slack"
fi

# Validate required params
if [[ -z "$AGENT" ]]; then echo "ERROR: --agent is required" >&2; exit 1; fi
if [[ -z "$NAME" ]]; then echo "ERROR: --name is required" >&2; exit 1; fi
if [[ -z "$MESSAGE" ]]; then echo "ERROR: --message is required" >&2; exit 1; fi
if [[ -z "$AT" && -z "$CRON_EXPR" ]]; then echo "ERROR: --at or --cron is required" >&2; exit 1; fi

# --- Timezone auto-detection ---
# Try multiple workspace path conventions
if [[ "$TZ_EXPLICIT" == "false" && -n "$CRON_EXPR" ]]; then
  TZ_CANDIDATES=(
    "$HOME/.openclaw/workspace-$AGENT/timezone.json"
    "$HOME/.openclaw/workspace-nutritionist/$AGENT/timezone.json"
  )
  for TZ_FILE in "${TZ_CANDIDATES[@]}"; do
    if [[ -f "$TZ_FILE" ]]; then
      AUTO_TZ=$(python3 -c "
import json
with open('$TZ_FILE') as f:
    d = json.load(f)
    print(d.get('tz', '') or d.get('tz_name', ''))
" 2>/dev/null || echo "")
      if [[ -n "$AUTO_TZ" ]]; then
        TZ="$AUTO_TZ"
        echo "Auto-detected timezone from $TZ_FILE: $TZ"
        break
      fi
    fi
  done
  # Fallback if still empty
  if [[ -z "$TZ" ]]; then
    TZ="Asia/Shanghai"
    echo "WARNING: No timezone.json found, falling back to $TZ"
  fi
fi

# --- Anti-burst: adjust cron expression for recurring jobs ---
if [[ -n "$CRON_EXPR" && "$EXACT" == "false" ]]; then
  echo "Running anti-burst slot finder (type=$JOB_TYPE)..."
  SLOT_OUTPUT=$(python3 "$SCRIPT_DIR/find-slot.py" \
    --cron "$CRON_EXPR" --tz "$TZ" --type "$JOB_TYPE" 2>&1)
  SLOT_EXIT=$?
  # Print full output for logging, then extract last line as the adjusted cron
  echo "$SLOT_OUTPUT" >&2
  ADJUSTED_CRON=$(echo "$SLOT_OUTPUT" | tail -1)

  if [[ $SLOT_EXIT -eq 0 || $SLOT_EXIT -eq 2 ]]; then
    if [[ -n "$ADJUSTED_CRON" && "$ADJUSTED_CRON" != "$CRON_EXPR" ]]; then
      echo "Anti-burst: adjusted cron from '$CRON_EXPR' to '$ADJUSTED_CRON'"
    fi
    CRON_EXPR="$ADJUSTED_CRON"
  else
    echo "WARNING: find-slot.py failed (exit $SLOT_EXIT), using original cron" >&2
  fi
fi

# --- Resolve delivery target (--to) ---
if [[ -z "$TO" ]]; then
  case "$CHANNEL" in
    slack)
      # Original Slack logic: look up user ID from openclaw.json bindings
      CONFIG="$HOME/.openclaw/openclaw.json"
      SLACK_USER_ID=$(python3 -c "
import json, sys
with open('$CONFIG') as f:
    cfg = json.load(f)
for b in cfg.get('bindings', []):
    if b.get('agentId') == '$AGENT' and b.get('match', {}).get('channel') == 'slack':
        print(b['match']['peer']['id'])
        sys.exit(0)
print('NOT_FOUND')
")
      if [[ "$SLACK_USER_ID" == "NOT_FOUND" ]]; then
        echo "ERROR: No Slack binding found for agent $AGENT" >&2
        exit 1
      fi
      TO="user:$SLACK_USER_ID"
      ;;
    wechat|wecom)
      # Extract userId from agent ID: wechat-dm-xxx → xxx, wecom-dm-xxx → xxx
      USER_ID=$(echo "$AGENT" | sed -E 's/^(wechat|wecom)-dm-//')
      if [[ "$USER_ID" == "$AGENT" ]]; then
        echo "ERROR: Cannot extract userId from agent '$AGENT'. Use --to to specify explicitly." >&2
        exit 1
      fi
      TO="$USER_ID"
      ;;
    *)
      echo "ERROR: --to is required for channel '$CHANNEL' (cannot auto-detect)" >&2
      exit 1
      ;;
  esac
fi

echo "Agent: $AGENT → Channel: $CHANNEL → To: $TO"

# --- Build the cron command ---
# Note: Do NOT wrap $MESSAGE with delivery instructions here.
# The no-self-delivery rule is enforced in notification-composer SKILL.md
# and AGENTS.md, not in each cron job's payload. See CONVENTIONS.md §11.
CMD=(openclaw cron add
  --name "$NAME"
  --session isolated
  --agent "$AGENT"
  --message "$MESSAGE"
  --announce
  --channel "$CHANNEL"
  --to "$TO"
)

if [[ -n "$AT" ]]; then
  CMD+=(--at "$AT")
  if [[ -z "$DELETE_AFTER_RUN" ]]; then
    CMD+=(--delete-after-run)
  fi
elif [[ -n "$CRON_EXPR" ]]; then
  CMD+=(--cron "$CRON_EXPR" --tz "$TZ")
fi

echo "Running: ${CMD[*]}"
"${CMD[@]}"
