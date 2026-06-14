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

# --- Resolve OpenClaw state dir (cwd for `openclaw cron` invocations) ---
# `openclaw cron list/add` resolves ~/.openclaw relative to its working dir / env.
# On production the state dir IS the OpenClaw home (~/.openclaw); the legacy
# layout used $PROJECT_ROOT/.openclaw-gateway. Prefer an explicit override, then
# the real OpenClaw home, then the legacy path — never hardcode one layout.
resolve_state_dir() {
  if [[ -n "${OPENCLAW_STATE_DIR:-}" ]]; then echo "$OPENCLAW_STATE_DIR"; return; fi
  if [[ -n "${OPENCLAW_HOME:-}" && -d "${OPENCLAW_HOME}" ]]; then echo "$OPENCLAW_HOME"; return; fi
  if [[ -d "$HOME/.openclaw" ]]; then echo "$HOME/.openclaw"; return; fi
  echo "$PROJECT_ROOT/.openclaw-gateway"  # legacy fallback
}
STATE_DIR="$(resolve_state_dir)"

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

# Auto-detect channel from agentId prefix, fallback to slack
if [[ -z "$CHANNEL" ]]; then
  if [[ "$AGENT" == wechat-dm-* ]]; then
    CHANNEL="wechat"
  elif [[ "$AGENT" == wecom-dm-* ]]; then
    CHANNEL="wecom"
  else
    CHANNEL="slack"
  fi
fi

# Validate required params
if [[ -z "$AGENT" ]]; then echo "ERROR: --agent is required" >&2; exit 1; fi
if [[ -z "$NAME" ]]; then echo "ERROR: --name is required" >&2; exit 1; fi
if [[ -z "$MESSAGE" ]]; then echo "ERROR: --message is required" >&2; exit 1; fi
if [[ -z "$AT" && -z "$CRON_EXPR" ]]; then echo "ERROR: --at or --cron is required" >&2; exit 1; fi

# --- Candidate workspace directories (used by both TZ detection + msg injection) ---
# Order matters: production layout (~/.openclaw/workspace-nutritionist/$AGENT)
# first, then legacy layouts. Defined unconditionally so USER_WORKSPACE
# resolution below always has the list (previously only set inside the TZ block).
WS_CANDIDATES=(
  "$STATE_DIR/workspace-nutritionist/$AGENT"
  "$STATE_DIR/workspace-$AGENT"
  "$PROJECT_ROOT/.openclaw-user-service/workspaces/$AGENT"
)

# Read a "- **<Field>:** <value>" line out of a USER.md, trimmed. Inlined so we
# don't depend on usermd-helpers.sh, whose path differs across deployments and
# is frequently absent (which silently broke TZ detection -> Asia/Shanghai).
read_usermd_field() {
  local file="$1" field="$2"
  [[ -f "$file" ]] || return 1
  grep -m1 "^- \*\*${field}:\*\*" "$file" 2>/dev/null \
    | sed -E 's/^- \*\*[^*]*\*\*[[:space:]]*//' \
    | sed -E 's/[[:space:]]+$//'
}

# --- Timezone resolution ---
# For recurring (--cron) jobs we MUST schedule in the user's real timezone.
# A wrong timezone is worse than no reminder (fires at the wrong real-world
# hour), so if --tz is not given AND we can't read it from USER.md, we FAIL
# LOUD instead of silently defaulting to Asia/Shanghai.
if [[ "$TZ_EXPLICIT" == "true" ]]; then
  echo "Using explicit --tz: $TZ (skipping auto-detect)"
elif [[ -n "$CRON_EXPR" ]]; then
  for WS_DIR in "${WS_CANDIDATES[@]}"; do
    if [[ -f "$WS_DIR/USER.md" ]]; then
      AUTO_TZ=$(read_usermd_field "$WS_DIR/USER.md" "Timezone" || true)
      if [[ -n "$AUTO_TZ" ]]; then
        TZ="$AUTO_TZ"
        echo "Auto-detected timezone from $WS_DIR/USER.md: $TZ"
        break
      fi
    fi
  done
  if [[ -z "$TZ" ]]; then
    echo "ERROR: Could not resolve timezone for agent '$AGENT'." >&2
    echo "ERROR: No --tz given and no '- **Timezone:**' field found in USER.md under:" >&2
    for WS_DIR in "${WS_CANDIDATES[@]}"; do echo "ERROR:   $WS_DIR/USER.md" >&2; done
    echo "ERROR: Refusing to schedule a recurring reminder in the wrong timezone. Pass --tz explicitly or set USER.md > Timezone." >&2
    exit 1
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
    twilio)
      # Look up phone number from openclaw.json bindings
      CONFIG="$HOME/.openclaw/openclaw.json"
      TWILIO_PHONE=$(python3 -c "
import json, sys
with open('$CONFIG') as f:
    cfg = json.load(f)
for b in cfg.get('bindings', []):
    if b.get('agentId') == '$AGENT' and b.get('match', {}).get('channel') == 'twilio':
        print(b['match']['peer']['id'])
        sys.exit(0)
print('NOT_FOUND')
")
      if [[ "$TWILIO_PHONE" == "NOT_FOUND" ]]; then
        echo "ERROR: No Twilio binding found for agent $AGENT" >&2
        exit 1
      fi
      TO="$TWILIO_PHONE"
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

# --- Imminent-first-run guard (recurring jobs only) ---
# A freshly created recurring reminder whose next occurrence is only minutes away
# would fire during the same session that created it (the mid-onboarding
# early-fire bug). OpenClaw's `cron add` CLI cannot set the initial nextRunAtMs,
# and direct store edits race a running gateway, so we use the one race-free,
# gateway-safe lever the CLI gives us: create the job DISABLED. A disabled job
# never fires, so it cannot go off mid-session. notification-manager auto-sync
# (every activation) and the deploy migration re-enable it; by then the imminent
# window has long passed and the job resumes on its normal daily schedule.
# Threshold is generous (45 min) to cover the slot-15min meal reminders.
IMMINENT_LEAD_SECONDS="${REMINDER_IMMINENT_LEAD_SECONDS:-2700}"  # 45 min
CREATE_DISABLED=false
if [[ -n "$CRON_EXPR" ]]; then
  SECS_UNTIL=$(python3 "$SCRIPT_DIR/next-cron-run.py" --cron "$CRON_EXPR" --tz "$TZ" 2>/dev/null || echo "")
  if [[ -n "$SECS_UNTIL" && "$SECS_UNTIL" =~ ^[0-9]+$ ]]; then
    if (( SECS_UNTIL < IMMINENT_LEAD_SECONDS )); then
      CREATE_DISABLED=true
      echo "Imminent-fire guard: next run is in ${SECS_UNTIL}s (< ${IMMINENT_LEAD_SECONDS}s). Creating job DISABLED to avoid a mid-session fire; auto-sync/migration will enable it for its next occurrence."
    fi
  else
    echo "WARNING: could not compute next run for '$CRON_EXPR' ($TZ); creating normally (fail-open)." >&2
  fi
fi

# --- Idempotency guard: skip if a job with this name already exists ---
# Protects against the failed-then-retried batch pattern (and any double
# invocation) that otherwise produces duplicate meal-slot crons. Keyed on
# agentId + job name (the meal slot identity). Safe regardless of
# --skip-existing upstream. If we cannot read the cron list we do NOT skip
# (fail-open here is correct: missing a reminder is worse than a possible dup,
# and the batch layer fails closed on its own list error).
existing_job_with_name() {
  command -v openclaw >/dev/null 2>&1 || return 1
  # `openclaw cron list` has no --agent flag and omits disabled jobs without
  # --all; pass --all and filter by agentId + name in Python.
  ( cd "$STATE_DIR" && openclaw cron list --all --json 2>/dev/null ) \
    | AGENT="$AGENT" NAME="$NAME" python3 -c "
import sys, json, os
agent = os.environ.get('AGENT','')
want = os.environ.get('NAME','')
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(2)  # unreadable -> caller treats as 'cannot confirm', does not skip
jobs = data.get('jobs', data) if isinstance(data, dict) else data
for j in (jobs or []):
    if j.get('agentId') == agent and j.get('name') == want:
        print(j.get('id',''))
        sys.exit(0)
sys.exit(1)
"
}

DUP_ID=""
DUP_RC=0
DUP_ID="$(existing_job_with_name)" || DUP_RC=$?
if [[ $DUP_RC -eq 0 && -n "$DUP_ID" ]]; then
  echo "Idempotent skip: a job named '$NAME' already exists for agent $AGENT (id=$DUP_ID). Not creating a duplicate."
  exit 0
fi

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
    --model "anthropic/claude-sonnet-4-6"
    --no-deliver
    --json
  )
else
  CMD=(openclaw cron add
    --name "$NAME"
    --session isolated
    --agent "$AGENT"
    --message "$MESSAGE"
    --model "anthropic/claude-sonnet-4-6"
    --announce
    --channel "$CHANNEL"
    --to "$TO"
  )

fi

if [[ -n "$AT" ]]; then
  CMD+=(--at "$AT")
  if [[ -z "$DELETE_AFTER_RUN" ]]; then
    CMD+=(--delete-after-run)
  fi
elif [[ -n "$CRON_EXPR" ]]; then
  CMD+=(--cron "$CRON_EXPR" --tz "$TZ")
  if [[ "$CREATE_DISABLED" == "true" ]]; then
    CMD+=(--disabled)
  fi
fi

echo "Running: ${CMD[*]}"
cd "$STATE_DIR"
"${CMD[@]}"
