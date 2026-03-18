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
# Examples:
#   # Slack (default, backward-compatible — no --channel needed)
#   bash create-reminder.sh --agent 007-zhuoran --name "午餐提醒" --message "午饭时间到了" --cron "0 12 * * *"
#
#   # WeChat
#   bash create-reminder.sh --agent wechat-dm-accjoh25tsvoasahx0psjfg --channel wechat --name "午餐提醒" --message "午饭时间到了" --cron "0 12 * * *"
#
#   # Explicit --to (any channel)
#   bash create-reminder.sh --agent some-agent --channel telegram --to "123456789" --name "提醒" --message "test" --at "2m"

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

# --- Wrap message with delivery instructions ---
# Cron isolated sessions auto-deliver via announce. Without this wrapper,
# the agent may also try to send via exec/message tool → duplicate messages.
WRAPPED_MESSAGE="Your reply will be automatically delivered to the user. Do NOT use exec, message, or any tool to send it yourself. Just output the reminder text and nothing else.

${MESSAGE}"

# --- Build the cron command ---
CMD=(openclaw cron add
  --name "$NAME"
  --session isolated
  --agent "$AGENT"
  --message "$WRAPPED_MESSAGE"
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
