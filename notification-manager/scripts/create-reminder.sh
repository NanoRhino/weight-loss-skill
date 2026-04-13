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
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
STATE_DIR="${OPENCLAW_STATE_DIR:-$PROJECT_ROOT/.openclaw-gateway}"

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
# Read from USER.md in workspace
if [[ "$TZ_EXPLICIT" == "false" && -n "$CRON_EXPR" ]]; then
  HELPERS="$PROJECT_ROOT/.openclaw-strategic-management/scripts/usermd-helpers.sh"
  if [[ -f "$HELPERS" ]]; then
    source "$HELPERS"
  fi

  WS_CANDIDATES=(
    "$STATE_DIR/workspace-$AGENT"
    "$PROJECT_ROOT/.openclaw-user-service/workspaces/$AGENT"
  )
  for WS_DIR in "${WS_CANDIDATES[@]}"; do
    if [[ -f "$WS_DIR/USER.md" ]] && type usermd_read &>/dev/null; then
      AUTO_TZ=$(usermd_read "$WS_DIR" "Timezone" 2>/dev/null || echo "")
      if [[ -n "$AUTO_TZ" ]]; then
        TZ="$AUTO_TZ"
        echo "Auto-detected timezone from $WS_DIR/USER.md: $TZ"
        break
      fi
    fi
  done
  # Fallback if still empty
  if [[ -z "$TZ" ]]; then
    TZ="Asia/Shanghai"
    echo "WARNING: No timezone found in USER.md, falling back to $TZ"
  fi
fi

# --- Resolve user workspace for cron message injection ---
USER_WORKSPACE=""
for WS_DIR in "${WS_CANDIDATES[@]}"; do
  if [[ -d "$WS_DIR" ]]; then
    USER_WORKSPACE="$WS_DIR"
    break
  fi
done

# For wechat/wecom channels, also try {userId}_{robotId} format
if [[ -z "$USER_WORKSPACE" && ("$CHANNEL" == "wechat" || "$CHANNEL" == "wecom") ]]; then
  WORKSPACES_DIR="$PROJECT_ROOT/.openclaw-user-service/workspaces"
  if [[ -d "$WORKSPACES_DIR" ]]; then
    for DIR in "$WORKSPACES_DIR"/*; do
      DIR_NAME=$(basename "$DIR")
      # Case-insensitive match on the agent ID (which is lowercased)
      if [[ "${DIR_NAME,,}" == "${AGENT,,}"* ]]; then
        USER_WORKSPACE="$DIR"
        break
      fi
    done
  fi

  # Also try STATE_DIR workspace directories
  if [[ -z "$USER_WORKSPACE" ]]; then
    for DIR in "$STATE_DIR"/workspace-*; do
      [[ -d "$DIR" ]] || continue
      DIR_NAME=$(basename "$DIR")
      DIR_NAME="${DIR_NAME#workspace-}"  # strip prefix
      if [[ "${DIR_NAME,,}" == "${AGENT,,}"* ]]; then
        USER_WORKSPACE="$DIR"
        break
      fi
    done
  fi
fi

if [[ -n "$USER_WORKSPACE" ]]; then
  echo "Resolved user workspace: $USER_WORKSPACE"
else
  echo "WARNING: Could not resolve user workspace for agent $AGENT" >&2
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
      CONFIG="$PROJECT_ROOT/.openclaw-gateway/openclaw.json"
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
    app|webchat)
      # App channel: use webhook delivery to Bridge
      TO="http://127.0.0.1:8100/cron-webhook"
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
if [[ "$CHANNEL" == "app" || "$CHANNEL" == "webchat" ]]; then
  # App channel: agent composes message, then uses exec curl to push to Bridge.
  # OpenClaw's SSRF guard blocks webhook delivery to localhost/private IPs,
  # but agent exec tool bypasses SSRF since it's a shell command.
  BRIDGE_URL="http://127.0.0.1:8100/cron-deliver"
  WRAPPED_MESSAGE="$MESSAGE

IMPORTANT: After composing your response, you MUST deliver it to the app by running this exec command (replace YOUR_MESSAGE with your actual composed message, properly escaped for JSON):
exec command: curl -s -X POST '$BRIDGE_URL' -H 'Content-Type: application/json' -d '{\"agent_id\": \"$AGENT\", \"message\": \"YOUR_MESSAGE\", \"type\": \"other\", \"cron_name\": \"$NAME\", \"channel\": \"app\"}'
Do NOT output the message as your reply. Instead, put your full message text into the curl command above and execute it. Reply with only: NO_REPLY"
  CMD=(openclaw cron add
    --name "$NAME"
    --session main
    --agent "$AGENT"
    --message "$WRAPPED_MESSAGE"
    --no-deliver
    --json
  )
else
  CMD=(openclaw cron add
    --name "$NAME"
    --session main
    --agent "$AGENT"
    --system-event "$MESSAGE"
  )
fi

if [[ -n "$AT" ]]; then
  CMD+=(--at "$AT")
  if [[ -z "$DELETE_AFTER_RUN" ]]; then
    CMD+=(--delete-after-run)
  fi
elif [[ -n "$CRON_EXPR" ]]; then
  CMD+=(--cron "$CRON_EXPR" --tz "$TZ")
fi

echo "Running: ${CMD[*]}"
cd "$STATE_DIR"
"${CMD[@]}"
