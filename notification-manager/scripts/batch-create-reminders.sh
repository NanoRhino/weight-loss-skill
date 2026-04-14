#!/usr/bin/env bash
set -euo pipefail

# batch-create-reminders.sh — Create all reminder cron jobs for a user in one go
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
#   --dry-run                Print commands without executing
#   --skip-existing          Skip reminders that already exist
#   --only <type>            Only create specific type: meal, weight, review, report, pattern, all (default: all)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
STATE_DIR="${OPENCLAW_STATE_DIR:-$PROJECT_ROOT/.openclaw-gateway}"
CREATE_REMINDER="$SCRIPT_DIR/create-reminder.sh"

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

# Validate required params
if [[ -z "$AGENT" ]]; then
  echo "ERROR: --agent is required" >&2
  exit 1
fi
if [[ -z "$CHANNEL" ]]; then
  echo "ERROR: --channel is required" >&2
  exit 1
fi
if [[ -z "$WORKSPACE" ]]; then
  echo "ERROR: --workspace is required" >&2
  exit 1
fi
if [[ ! -d "$WORKSPACE" ]]; then
  echo "ERROR: Workspace directory does not exist: $WORKSPACE" >&2
  exit 1
fi

USER_MD="$WORKSPACE/USER.md"
HEALTH_PROFILE="$WORKSPACE/health-profile.md"

if [[ ! -f "$HEALTH_PROFILE" ]]; then
  echo "ERROR: health-profile.md not found in workspace: $HEALTH_PROFILE" >&2
  exit 1
fi

# --- Helper functions ---

# Read a field from USER.md (Timezone)
read_usermd() {
  local field="$1"
  if [[ ! -f "$USER_MD" ]]; then
    return 1
  fi
  local value
  value=$(grep "^- \*\*${field}:\*\*" "$USER_MD" 2>/dev/null | sed -E 's/^- \*\*[^*]*\*\*[[:space:]]*//' || true)
  # Trim whitespace and return empty if nothing left
  value=$(echo "$value" | xargs)
  if [[ -n "$value" ]]; then
    echo "$value"
  fi
}

# Read timezone from USER.md, fallback to Asia/Shanghai
get_timezone() {
  local tz
  tz=$(read_usermd "Timezone")
  if [[ -z "$tz" ]]; then
    echo "Asia/Shanghai"
  else
    echo "$tz"
  fi
}

# Parse meal times from health-profile.md
# Returns lines like "Breakfast 09:00" or empty if meal not set
get_meal_schedule() {
  local in_meal_section=false
  while IFS= read -r line; do
    if [[ "$line" == "## Meal Schedule" ]]; then
      in_meal_section=true
      continue
    fi
    if [[ "$in_meal_section" == true ]]; then
      # Stop at next section
      if [[ "$line" =~ ^##\  ]]; then
        break
      fi
      # Parse meal lines: - **Breakfast:** 09:00
      if [[ "$line" =~ ^-\ \*\*([^*]+):\*\*\ (.+)$ ]]; then
        local meal_name="${BASH_REMATCH[1]}"
        local meal_time="${BASH_REMATCH[2]}"
        # Skip "Meals per Day" and lines with "—" or empty time
        if [[ "$meal_name" != "Meals per Day" && "$meal_time" != "—" && -n "$meal_time" ]]; then
          echo "$meal_name $meal_time"
        fi
      fi
    fi
  done < "$HEALTH_PROFILE"
}

# Read a field from health-profile.md under ## Automation
get_automation_field() {
  local field="$1"
  local in_automation_section=false
  while IFS= read -r line; do
    if [[ "$line" == "## Automation" ]]; then
      in_automation_section=true
      continue
    fi
    if [[ "$in_automation_section" == true ]]; then
      if [[ "$line" =~ ^##\  ]]; then
        break
      fi
      if [[ "$line" =~ ^-\ \*\*${field}:\*\*\ (.+)$ ]]; then
        echo "${BASH_REMATCH[1]}"
        return 0
      fi
    fi
  done < "$HEALTH_PROFILE"
  echo "—"
}

# Calculate cron time from HH:MM and offset in minutes
# Args: time_str (HH:MM), offset_minutes (can be negative)
# Output: "MM HH" for cron (minute hour)
calc_cron_time() {
  local time_str="$1"
  local offset_min="$2"

  # Parse HH:MM
  if [[ ! "$time_str" =~ ^([0-9]{2}):([0-9]{2})$ ]]; then
    echo "ERROR: Invalid time format: $time_str" >&2
    return 1
  fi
  local hour="${BASH_REMATCH[1]}"
  local minute="${BASH_REMATCH[2]}"

  # Remove leading zeros
  hour=$((10#$hour))
  minute=$((10#$minute))

  # Calculate total minutes
  local total_min=$((hour * 60 + minute + offset_min))

  # Handle day wrap
  if [[ $total_min -lt 0 ]]; then
    total_min=$((total_min + 1440))
  elif [[ $total_min -ge 1440 ]]; then
    total_min=$((total_min - 1440))
  fi

  # Convert back to hour:minute
  local new_hour=$((total_min / 60))
  local new_minute=$((total_min % 60))

  echo "$new_minute $new_hour"
}

# Get existing cron job names (for --skip-existing)
get_existing_cron_names() {
  if command -v openclaw &> /dev/null; then
    (cd "$STATE_DIR" && openclaw cron list --json) 2>/dev/null | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    for job in data.get('jobs', []):
        print(job.get('name', ''))
except:
    pass
" || true
  fi
}

# Check if a job name already exists
job_exists() {
  local name="$1"
  echo "$EXISTING_JOBS" | grep -qxF "$name"
}

# Execute or print a command
run_cmd() {
  if [[ "$DRY_RUN" == true ]]; then
    # Print command with proper quoting for readability
    local cmd_str=""
    for arg in "$@"; do
      # Quote arguments that contain spaces or special chars
      if [[ "$arg" =~ [[:space:]] || "$arg" =~ \* ]]; then
        cmd_str+="\"$arg\" "
      else
        cmd_str+="$arg "
      fi
    done
    echo "[DRY-RUN] $cmd_str"
  else
    echo "Creating: $*"
    "$@"
  fi
}

# Check if we should create this type
should_create_type() {
  local type="$1"
  if [[ "$ONLY_TYPE" == "all" ]]; then
    return 0
  fi
  # Support comma-separated types (e.g., "meal,weight")
  if [[ ",$ONLY_TYPE," == *",$type,"* ]]; then
    return 0
  fi
  return 1
}

# --- Main logic ---

TIMEZONE=$(get_timezone)
echo "Timezone: $TIMEZONE"

# Get existing jobs if --skip-existing
EXISTING_JOBS=""
if [[ "$SKIP_EXISTING" == true ]]; then
  EXISTING_JOBS=$(get_existing_cron_names)
fi

# Parse meal schedule
MEAL_SCHEDULE=$(get_meal_schedule)
if [[ -z "$MEAL_SCHEDULE" ]]; then
  echo "ERROR: No meal times found in health-profile.md > Meal Schedule" >&2
  exit 1
fi

echo "Meal schedule:"
echo "$MEAL_SCHEDULE"
echo ""

# Track creation stats
CREATED=0
SKIPPED=0
TOTAL=0

# Extract specific meal times for later use
BREAKFAST_TIME=""
DINNER_TIME=""
while IFS= read -r meal_line; do
  if [[ "$meal_line" =~ ^Breakfast\ (.+)$ ]]; then
    BREAKFAST_TIME="${BASH_REMATCH[1]}"
  elif [[ "$meal_line" =~ ^Dinner\ (.+)$ ]]; then
    DINNER_TIME="${BASH_REMATCH[1]}"
  fi
done <<< "$MEAL_SCHEDULE"

# Determine first meal time (for users who skip breakfast)
FIRST_MEAL_TIME=""
while IFS= read -r meal_line; do
  if [[ -n "$meal_line" ]]; then
    FIRST_MEAL_TIME=$(echo "$meal_line" | awk '{print $2}')
    break
  fi
done <<< "$MEAL_SCHEDULE"

# --- 1. Meal reminders ---
if should_create_type "meal"; then
  while IFS= read -r meal_line; do
    if [[ -z "$meal_line" ]]; then continue; fi

    meal_name=$(echo "$meal_line" | awk '{print $1}')
    meal_time=$(echo "$meal_line" | awk '{print $2}')

    # Calculate reminder time (meal - 15 min)
    cron_time=$(calc_cron_time "$meal_time" -15)
    cron_min=$(echo "$cron_time" | awk '{print $1}')
    cron_hour=$(echo "$cron_time" | awk '{print $2}')

    job_name="$(tr '[:lower:]' '[:upper:]' <<< ${meal_name:0:1})${meal_name:1} reminder"
    message="Run notification-composer for $(tr '[:upper:]' '[:lower:]' <<< $meal_name)."

    TOTAL=$((TOTAL + 1))

    if [[ "$SKIP_EXISTING" == true ]] && job_exists "$job_name"; then
      echo "Skipping (exists): $job_name"
      SKIPPED=$((SKIPPED + 1))
      continue
    fi

    run_cmd bash "$CREATE_REMINDER" \
      --agent "$AGENT" \
      --channel "$CHANNEL" \
      --type meal \
      --name "$job_name" \
      --message "$message" \
      --cron "$cron_min $cron_hour * * *"

    CREATED=$((CREATED + 1))
  done <<< "$MEAL_SCHEDULE"
fi

# --- 2. Weight reminders ---
if should_create_type "weight" && [[ -n "$FIRST_MEAL_TIME" ]] && [[ -n "$DINNER_TIME" ]]; then
  # Weight check-in (Wed & Sat, first meal - 30 min)
  cron_time=$(calc_cron_time "$FIRST_MEAL_TIME" -30)
  cron_min=$(echo "$cron_time" | awk '{print $1}')
  cron_hour=$(echo "$cron_time" | awk '{print $2}')

  job_name="Weight check-in reminder"
  TOTAL=$((TOTAL + 1))

  if [[ "$SKIP_EXISTING" == true ]] && job_exists "$job_name"; then
    echo "Skipping (exists): $job_name"
    SKIPPED=$((SKIPPED + 1))
  else
    run_cmd bash "$CREATE_REMINDER" \
      --agent "$AGENT" \
      --channel "$CHANNEL" \
      --type weight \
      --name "$job_name" \
      --message "Run notification-composer for weight." \
      --cron "$cron_min $cron_hour * * 3,6"
    CREATED=$((CREATED + 1))
  fi

  # Weight evening followup (Wed & Sat, dinner + 30 min)
  cron_time=$(calc_cron_time "$DINNER_TIME" 30)
  cron_min=$(echo "$cron_time" | awk '{print $1}')
  cron_hour=$(echo "$cron_time" | awk '{print $2}')

  job_name="Weight evening followup"
  TOTAL=$((TOTAL + 1))

  if [[ "$SKIP_EXISTING" == true ]] && job_exists "$job_name"; then
    echo "Skipping (exists): $job_name"
    SKIPPED=$((SKIPPED + 1))
  else
    run_cmd bash "$CREATE_REMINDER" \
      --agent "$AGENT" \
      --channel "$CHANNEL" \
      --type weight \
      --name "$job_name" \
      --message "Run notification-composer for weight_evening." \
      --cron "$cron_min $cron_hour * * 3,6"
    CREATED=$((CREATED + 1))
  fi

  # Weight morning followup (Thu & Sun, first meal - 30 min)
  cron_time=$(calc_cron_time "$FIRST_MEAL_TIME" -30)
  cron_min=$(echo "$cron_time" | awk '{print $1}')
  cron_hour=$(echo "$cron_time" | awk '{print $2}')

  job_name="Weight morning followup"
  TOTAL=$((TOTAL + 1))

  if [[ "$SKIP_EXISTING" == true ]] && job_exists "$job_name"; then
    echo "Skipping (exists): $job_name"
    SKIPPED=$((SKIPPED + 1))
  else
    run_cmd bash "$CREATE_REMINDER" \
      --agent "$AGENT" \
      --channel "$CHANNEL" \
      --type weight \
      --name "$job_name" \
      --message "Run notification-composer for weight_morning_followup." \
      --cron "$cron_min $cron_hour * * 4,0"
    CREATED=$((CREATED + 1))
  fi
fi

# --- 3. Weekly report ---
if should_create_type "report"; then
  job_name="Weekly report"
  TOTAL=$((TOTAL + 1))

  if [[ "$SKIP_EXISTING" == true ]] && job_exists "$job_name"; then
    echo "Skipping (exists): $job_name"
    SKIPPED=$((SKIPPED + 1))
  else
    run_cmd bash "$CREATE_REMINDER" \
      --agent "$AGENT" \
      --channel "$CHANNEL" \
      --name "$job_name" \
      --message "Run weekly-report to generate this week's progress report." \
      --cron "0 21 * * 0"
    CREATED=$((CREATED + 1))
  fi
fi

# --- 4. Daily review ---
if should_create_type "review" && [[ -n "$DINNER_TIME" ]]; then
  cron_time=$(calc_cron_time "$DINNER_TIME" 180)  # +3 hours
  cron_min=$(echo "$cron_time" | awk '{print $1}')
  cron_hour=$(echo "$cron_time" | awk '{print $2}')

  job_name="Daily review"
  TOTAL=$((TOTAL + 1))

  if [[ "$SKIP_EXISTING" == true ]] && job_exists "$job_name"; then
    echo "Skipping (exists): $job_name"
    SKIPPED=$((SKIPPED + 1))
  else
    run_cmd bash "$CREATE_REMINDER" \
      --agent "$AGENT" \
      --channel "$CHANNEL" \
      --name "$job_name" \
      --message "Run daily-review to generate today's nutrition summary." \
      --cron "$cron_min $cron_hour * * *"
    CREATED=$((CREATED + 1))
  fi
fi

# --- Summary ---
echo ""
echo "====================================="
echo "Created $CREATED/$TOTAL jobs ($SKIPPED skipped)"
echo "====================================="

exit 0
