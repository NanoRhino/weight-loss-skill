#!/usr/bin/env bash
set -euo pipefail

# batch-create-reminders.sh — Create all reminder cron jobs in parallel.
#
# Two-phase execution:
#   Phase 1 (serial)   — collect job definitions, then call find-slot.py
#                        --batch-file once to allocate all time slots in a
#                        single cron list fetch. This prevents race conditions
#                        from concurrent slot lookups.
#   Phase 2 (parallel) — spawn all `create-reminder.sh --exact` calls in
#                        background and wait for all to finish.
#
# Usage:
#   bash batch-create-reminders.sh --agent <id> --channel <ch> --workspace <path> [options]
#
# Required:
#   --agent <agent-id>       Agent ID (e.g. wechat-dm-xxx)
#   --channel <channel>      Channel (e.g. wechat, slack, wecom)
#   --workspace <path>       Path to user workspace (contains USER.md, health-profile.md)
#
# Optional:
#   --dry-run                Print commands without executing (skips slot allocation)
#   --skip-existing          Skip reminders that already exist (checked before queuing)
#   --only <type>            Only create specific type: meal, weight, review, report,
#                            pattern, all (default: all). Comma-separated for multiple.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_DIR="${OPENCLAW_STATE_DIR:-$HOME/.openclaw-gateway}"
CREATE_REMINDER="$SCRIPT_DIR/create-reminder.sh"
FIND_SLOT="$SCRIPT_DIR/find-slot.py"

AGENT=""
CHANNEL=""
WORKSPACE=""
DRY_RUN=false
SKIP_EXISTING=false
ONLY_TYPE="all"

while [[ $# -gt 0 ]]; do
  case $1 in
    --agent)     AGENT="$2"; shift 2 ;;
    --channel)   CHANNEL="$2"; shift 2 ;;
    --workspace) WORKSPACE="$2"; shift 2 ;;
    --dry-run)   DRY_RUN=true; shift ;;
    --skip-existing) SKIP_EXISTING=true; shift ;;
    --only)      ONLY_TYPE="$2"; shift 2 ;;
    *) echo "ERROR: Unknown option: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "$AGENT" ]];     then echo "ERROR: --agent is required" >&2;     exit 1; fi
if [[ -z "$CHANNEL" ]];   then echo "ERROR: --channel is required" >&2;   exit 1; fi
if [[ -z "$WORKSPACE" ]]; then echo "ERROR: --workspace is required" >&2; exit 1; fi
if [[ ! -d "$WORKSPACE" ]]; then
  echo "ERROR: Workspace directory does not exist: $WORKSPACE" >&2; exit 1
fi

HEALTH_PROFILE="$WORKSPACE/health-profile.md"
USER_MD="$WORKSPACE/USER.md"

if [[ ! -f "$HEALTH_PROFILE" ]]; then
  echo "ERROR: health-profile.md not found: $HEALTH_PROFILE" >&2; exit 1
fi

# --- Helpers ---

read_usermd() {
  [[ ! -f "$USER_MD" ]] && return
  grep "^- \*\*${1}:\*\*" "$USER_MD" 2>/dev/null \
    | sed -E 's/^- \*\*[^*]*\*\*[[:space:]]*//' | xargs || true
}

get_timezone() {
  local tz
  tz=$(read_usermd "Timezone")
  echo "${tz:-Asia/Shanghai}"
}

get_meal_schedule() {
  local in_section=false
  while IFS= read -r line; do
    [[ "$line" == "## Meal Schedule" ]] && in_section=true && continue
    if [[ "$in_section" == true ]]; then
      [[ "$line" =~ ^##\  ]] && break
      if [[ "$line" =~ ^-\ \*\*([^*]+):\*\*\ (.+)$ ]]; then
        local meal="${BASH_REMATCH[1]}" time="${BASH_REMATCH[2]}"
        [[ "$meal" != "Meals per Day" && "$time" != "—" && -n "$time" ]] && echo "$meal $time"
      fi
    fi
  done < "$HEALTH_PROFILE"
}

get_automation_field() {
  local in_section=false
  while IFS= read -r line; do
    [[ "$line" == "## Automation" ]] && in_section=true && continue
    if [[ "$in_section" == true ]]; then
      [[ "$line" =~ ^##\  ]] && break
      [[ "$line" =~ ^-\ \*\*${1}:\*\*\ (.+)$ ]] && echo "${BASH_REMATCH[1]}" && return
    fi
  done < "$HEALTH_PROFILE"
  echo "—"
}

# Output: "MM HH" for cron
calc_cron_time() {
  local time_str="$1" offset_min="$2"
  [[ ! "$time_str" =~ ^([0-9]{2}):([0-9]{2})$ ]] && echo "ERROR: bad time: $time_str" >&2 && return 1
  local hour=$((10#${BASH_REMATCH[1]})) minute=$((10#${BASH_REMATCH[2]}))
  local total=$(( hour * 60 + minute + offset_min ))
  (( total < 0 ))    && total=$(( total + 1440 ))
  (( total >= 1440 )) && total=$(( total - 1440 ))
  echo "$(( total % 60 )) $(( total / 60 ))"
}

get_existing_cron_names() {
  command -v openclaw &>/dev/null || return
  (cd "$STATE_DIR" && openclaw cron list --json) 2>/dev/null \
    | python3 -c "
import sys, json
try:
    for j in json.load(sys.stdin).get('jobs', []):
        print(j.get('name',''))
except: pass
" || true
}

should_create_type() {
  [[ "$ONLY_TYPE" == "all" ]] && return 0
  [[ ",$ONLY_TYPE," == *",$1,"* ]] && return 0
  return 1
}

# --- Phase 1: Collect job definitions ---

TIMEZONE=$(get_timezone)
echo "Timezone: $TIMEZONE"

EXISTING_JOBS=""
if [[ "$SKIP_EXISTING" == true ]]; then
  EXISTING_JOBS=$(get_existing_cron_names)
fi

MEAL_SCHEDULE=$(get_meal_schedule)
if [[ -z "$MEAL_SCHEDULE" ]]; then
  echo "ERROR: No meal times in health-profile.md > Meal Schedule" >&2; exit 1
fi

echo "Meal schedule:"
echo "$MEAL_SCHEDULE"
echo ""

# Parallel arrays for queued jobs
QUEUED_NAMES=()
QUEUED_MESSAGES=()
QUEUED_BASE_CRONS=()
QUEUED_TYPES=()

# TSV file used as input to find-slot.py --batch-file
TMPJOBDIR=$(mktemp -d)
trap "rm -rf $TMPJOBDIR" EXIT
JOBS_TSV="$TMPJOBDIR/jobs.tsv"  # name<TAB>cron<TAB>type

queue_job() {
  local name="$1" message="$2" cron="$3" type="${4:-other}"

  if [[ "$SKIP_EXISTING" == true ]] && echo "$EXISTING_JOBS" | grep -qxF "$name"; then
    echo "Skipping (exists): $name"
    return
  fi

  QUEUED_NAMES+=("$name")
  QUEUED_MESSAGES+=("$message")
  QUEUED_BASE_CRONS+=("$cron")
  QUEUED_TYPES+=("$type")
  printf '%s\t%s\t%s\n' "$name" "$cron" "$type" >> "$JOBS_TSV"
}

BREAKFAST_TIME=""
DINNER_TIME=""
while IFS= read -r meal_line; do
  [[ "$meal_line" =~ ^Breakfast\ (.+)$ ]] && BREAKFAST_TIME="${BASH_REMATCH[1]}"
  [[ "$meal_line" =~ ^Dinner\ (.+)$ ]]    && DINNER_TIME="${BASH_REMATCH[1]}"
done <<< "$MEAL_SCHEDULE"

# 1. Meal reminders
if should_create_type "meal"; then
  while IFS= read -r meal_line; do
    [[ -z "$meal_line" ]] && continue
    meal_name=$(echo "$meal_line" | awk '{print $1}')
    meal_time=$(echo "$meal_line" | awk '{print $2}')
    ct=$(calc_cron_time "$meal_time" -15)
    cm=$(echo "$ct" | awk '{print $1}')
    ch=$(echo "$ct" | awk '{print $2}')
    jname="$(tr '[:lower:]' '[:upper:]' <<< "${meal_name:0:1}")${meal_name:1} reminder"
    msg="Run notification-composer for $(tr '[:upper:]' '[:lower:]' <<< "$meal_name")."
    queue_job "$jname" "$msg" "$cm $ch * * *" meal
  done <<< "$MEAL_SCHEDULE"
fi

# 2. Weight reminders
EARLIEST_TIME="${BREAKFAST_TIME:-}"
if [[ -z "$EARLIEST_TIME" && -n "$MEAL_SCHEDULE" ]]; then
  EARLIEST_TIME=$(echo "$MEAL_SCHEDULE" | awk 'NR==1{print $2}')
fi

if should_create_type "weight" && [[ -n "$EARLIEST_TIME" && -n "$DINNER_TIME" ]]; then
  ct=$(calc_cron_time "$EARLIEST_TIME" -30)
  cm=$(echo "$ct" | awk '{print $1}'); ch=$(echo "$ct" | awk '{print $2}')
  queue_job "Weight check-in reminder"  "Run notification-composer for weight."                  "$cm $ch * * 3,6" weight

  ct=$(calc_cron_time "$EARLIEST_TIME" -30)
  cm=$(echo "$ct" | awk '{print $1}'); ch=$(echo "$ct" | awk '{print $2}')
  queue_job "Weight morning followup"   "Run notification-composer for weight_morning_followup." "$cm $ch * * 4,0" weight
fi

# 3. Weekly report
if should_create_type "report"; then
  queue_job "Weekly report" "Run weekly-report to generate this week's progress report." "0 21 * * 0" other
fi

# 4. Daily review
if should_create_type "review" && [[ -n "$DINNER_TIME" ]]; then
  ct=$(calc_cron_time "$DINNER_TIME" 180)
  cm=$(echo "$ct" | awk '{print $1}'); ch=$(echo "$ct" | awk '{print $2}')
  queue_job "Daily review" "Run daily-review to generate today's nutrition summary." "$cm $ch * * *" other
fi

# 5. Diet pattern detection
if should_create_type "pattern" && [[ -n "$DINNER_TIME" ]]; then
  pattern_completed=$(get_automation_field "Pattern Detection Completed")
  if [[ "$pattern_completed" == "—" ]]; then
    ct=$(calc_cron_time "$DINNER_TIME" 180)
    cm=$(echo "$ct" | awk '{print $1}'); ch=$(echo "$ct" | awk '{print $2}')
    queue_job "Diet pattern detection" "Run diet-pattern-detection skill." "$cm $ch * * *" other
  fi
fi

TOTAL=${#QUEUED_NAMES[@]}
if [[ $TOTAL -eq 0 ]]; then
  echo "No jobs to create."
  exit 0
fi

echo ""
echo "$TOTAL job(s) queued. Running slot allocation..."

# --- Phase 2: Batch slot allocation (serial, one cron list fetch) ---

ADJUSTED_CRONS=()

if [[ "$DRY_RUN" == true ]]; then
  # In dry-run, skip the live cron list fetch — use base crons as-is
  ADJUSTED_CRONS=("${QUEUED_BASE_CRONS[@]}")
else
  # Build JSON for find-slot.py --batch-file
  BATCH_INPUT="$TMPJOBDIR/batch_input.json"
  python3 - "$BATCH_INPUT" "$TIMEZONE" "$JOBS_TSV" <<'PYEOF'
import json, sys

out_file, tz, tsv_file = sys.argv[1], sys.argv[2], sys.argv[3]
jobs = []
with open(tsv_file) as f:
    for line in f:
        line = line.rstrip('\n')
        if not line:
            continue
        parts = line.split('\t')
        name, cron, jtype = parts[0], parts[1], parts[2]
        jobs.append({"name": name, "cron": cron, "type": jtype, "tz": tz})
with open(out_file, 'w') as f:
    json.dump(jobs, f)
PYEOF

  BATCH_OUTPUT="$TMPJOBDIR/batch_output.json"
  python3 "$FIND_SLOT" --batch-file "$BATCH_INPUT" > "$BATCH_OUTPUT"

  # Extract adjusted crons in order (same order as QUEUED_NAMES)
  mapfile -t ADJUSTED_CRONS < <(python3 - "$BATCH_OUTPUT" <<'PYEOF'
import json, sys
with open(sys.argv[1]) as f:
    for r in json.load(f):
        print(r["adjusted_cron"])
PYEOF
  )
fi

echo "Slot allocation complete. Creating $TOTAL job(s) in parallel..."
echo ""

# --- Phase 3: Parallel job creation ---

PIDS=()
FAIL_COUNT=0

for idx in "${!QUEUED_NAMES[@]}"; do
  name="${QUEUED_NAMES[$idx]}"
  message="${QUEUED_MESSAGES[$idx]}"
  adjusted="${ADJUSTED_CRONS[$idx]}"

  if [[ "$DRY_RUN" == true ]]; then
    echo "[DRY-RUN] bash create-reminder.sh --agent \"$AGENT\" --channel \"$CHANNEL\" --exact --name \"$name\" --message \"$message\" --cron \"$adjusted\""
    continue
  fi

  (
    bash "$CREATE_REMINDER" \
      --agent   "$AGENT" \
      --channel "$CHANNEL" \
      --exact \
      --name    "$name" \
      --message "$message" \
      --cron    "$adjusted"
  ) &
  PIDS+=($!)
done

if [[ "$DRY_RUN" == false ]]; then
  for pid in "${PIDS[@]}"; do
    wait "$pid" || FAIL_COUNT=$((FAIL_COUNT + 1))
  done
fi

echo ""
echo "====================================="
if [[ "$DRY_RUN" == true ]]; then
  echo "DRY-RUN: $TOTAL job(s) would be created"
else
  CREATED=$(( TOTAL - FAIL_COUNT ))
  echo "Created $CREATED/$TOTAL job(s)${FAIL_COUNT:+ ($FAIL_COUNT failed)}"
fi
echo "====================================="

[[ $FAIL_COUNT -gt 0 ]] && exit 1
exit 0
