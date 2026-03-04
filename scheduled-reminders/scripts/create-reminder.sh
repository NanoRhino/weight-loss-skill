#!/usr/bin/env bash
set -euo pipefail

# create-reminder.sh — Wrapper for creating cron jobs with correct Slack delivery.
# Agents call this instead of the cron tool directly.
#
# Usage:
#   bash create-reminder.sh --agent <id> --name <name> --message <text> --at <ISO|relative>
#   bash create-reminder.sh --agent <id> --name <name> --message <text> --cron <expr> [--tz <tz>]
#
# Examples:
#   bash create-reminder.sh --agent 007-zhuoran --name "走路提醒" --message "该走路了" --at "2m"
#   bash create-reminder.sh --agent 007-zhuoran --name "午餐提醒" --message "午饭时间到了" --cron "0 12 * * *" --tz "Asia/Shanghai"

AGENT=""
NAME=""
MESSAGE=""
AT=""
CRON_EXPR=""
TZ="Asia/Shanghai"
DELETE_AFTER_RUN=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --agent)   AGENT="$2"; shift 2 ;;
    --name)    NAME="$2"; shift 2 ;;
    --message) MESSAGE="$2"; shift 2 ;;
    --at)      AT="$2"; shift 2 ;;
    --cron)    CRON_EXPR="$2"; shift 2 ;;
    --tz)      TZ="$2"; shift 2 ;;
    --keep)    DELETE_AFTER_RUN="--no-delete-after-run"; shift ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

# Validate required params
if [[ -z "$AGENT" ]]; then echo "ERROR: --agent is required" >&2; exit 1; fi
if [[ -z "$NAME" ]]; then echo "ERROR: --name is required" >&2; exit 1; fi
if [[ -z "$MESSAGE" ]]; then echo "ERROR: --message is required" >&2; exit 1; fi
if [[ -z "$AT" && -z "$CRON_EXPR" ]]; then echo "ERROR: --at or --cron is required" >&2; exit 1; fi

CONFIG="$HOME/.openclaw/openclaw.json"

# Look up Slack user ID from openclaw.json bindings
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

echo "Agent: $AGENT → Slack user: $SLACK_USER_ID"

# Build the cron command
CMD=(openclaw cron add
  --name "$NAME"
  --session isolated
  --agent "$AGENT"
  --message "$MESSAGE"
  --announce
  --channel slack
  --to "user:$SLACK_USER_ID"
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
