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
#   --only <type>            Only create specific type: meal, weight, report,
#                            pattern, tips, firstmeal, all (default: all).
#                            Comma-separated for multiple.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Resolve OpenClaw state dir (cwd for `openclaw cron` invocations). Prefer an
# explicit override, then the real OpenClaw home (~/.openclaw on production),
# then the legacy $HOME/.openclaw-gateway path. Must match create-reminder.sh.
resolve_state_dir() {
  if [[ -n "${OPENCLAW_STATE_DIR:-}" ]]; then echo "$OPENCLAW_STATE_DIR"; return; fi
  if [[ -n "${OPENCLAW_HOME:-}" && -d "${OPENCLAW_HOME}" ]]; then echo "$OPENCLAW_HOME"; return; fi
  if [[ -d "$HOME/.openclaw" ]]; then echo "$HOME/.openclaw"; return; fi
  echo "$HOME/.openclaw-gateway"  # legacy fallback
}
STATE_DIR="$(resolve_state_dir)"
CREATE_REMINDER="$SCRIPT_DIR/create-reminder.sh"
FIND_SLOT="$SCRIPT_DIR/find-slot.py"

# Default timezone when USER.md has no Timezone. US-funnel product → US-Eastern
# is usually right, and beats aborting (no reminders). Must match create-reminder.sh.
DEFAULT_TZ="America/New_York"

# CANONICAL DEFAULT MEAL TIMES (single source of truth) — used when
# health-profile.md > Meal Schedule is empty/absent (e.g. the post-first-meal
# activation flow creates the default 3 meal reminders before the user has
# confirmed their own times). Times are LOCAL (the script passes --tz). Format:
# "<MealName> HH:MM" per line, matching the output shape of get_meal_schedule().
# If you change these, this is the ONLY place to change them.
#   Breakfast 08:30 / Lunch 12:30 / Dinner 18:30 local
DEFAULT_MEAL_SCHEDULE=$'Breakfast 08:30\nLunch 12:30\nDinner 18:30'

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

# Ensure engagement.json exists (default stage=1 for new users)
ENGAGEMENT_PATH="$WORKSPACE/data/engagement.json"
if [[ ! -f "$ENGAGEMENT_PATH" ]]; then
  mkdir -p "$(dirname "$ENGAGEMENT_PATH")"
  cat > "$ENGAGEMENT_PATH" << 'ENGAGEMENT_EOF'
{
  "notification_stage": 1,
  "stage_changed_at": null,
  "last_recall_date": null,
  "recall_2_sent": false,
  "reminder_config": {}
}
ENGAGEMENT_EOF
  echo "Created engagement.json (stage=1)"
fi

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
  # Read the user's IANA timezone from USER.md. If absent, fall back to the US
  # default (DEFAULT_TZ) with a logged warning — this is a US-funnel product, so
  # a US default is usually right and beats aborting (which would leave the user
  # with no reminders). The warning goes to stderr so it doesn't pollute the
  # captured stdout value.
  local tz
  tz=$(read_usermd "Timezone")
  if [[ -z "$tz" ]]; then
    echo "WARNING: No '- **Timezone:**' field in $USER_MD; defaulting to $DEFAULT_TZ (US default)." >&2
    tz="$DEFAULT_TZ"
  fi
  echo "$tz"
}

get_meal_schedule() {
  local in_section=false
  while IFS= read -r line; do
    [[ "$line" == "## Meal Schedule" ]] && in_section=true && continue
    if [[ "$in_section" == true ]]; then
      [[ "$line" =~ ^##\  ]] && break
      if [[ "$line" =~ ^-\ \*\*([^*]+):\*\*\ (.+)$ ]]; then
        local meal="${BASH_REMATCH[1]}" time="${BASH_REMATCH[2]}"
        # Only recognize the known meal slots. The Meal Schedule section can
        # contain non-meal keys (e.g. "Meals per Day", or a stray
        # "Work Schedule" a user pasted in) — those must NOT become reminders
        # (a "Work Schedule" line once produced a bogus "Work reminder" cron).
        case "$meal" in
          Breakfast|Lunch|Dinner|Snack) ;;
          *) continue ;;
        esac
        # Skip empty / placeholder times (—, -, none, TBD).
        case "$time" in
          ""|"—"|"-"|[Nn]one|[Tt][Bb][Dd]) continue ;;
        esac
        echo "$meal $time"
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


# Extract first HH:MM from text and normalize to 24h (handles "9:00",
# "18:00（注释）", "07:00-08:00", and 12-hour "2:30 PM" / "9:30am").
# A 12-hour AM/PM suffix MUST be honored: without it "2:30 PM" was read as
# 02:30 (PM dropped), scheduling afternoon/evening reminders 12h early.
# 24-hour input has no AM/PM marker → hour passes through unchanged.
extract_time() {
  local raw="$1"
  if [[ "$raw" =~ ([0-9]{1,2}):([0-9]{2}) ]]; then
    local hour=$((10#${BASH_REMATCH[1]})) min="${BASH_REMATCH[2]}"
    shopt -s nocasematch
    if [[ "$raw" =~ (a|p)\.?m\.? ]]; then
      if [[ "${BASH_REMATCH[1]}" == "p" ]]; then
        (( hour < 12 )) && hour=$(( hour + 12 ))
      else
        (( hour == 12 )) && hour=0
      fi
    fi
    shopt -u nocasematch
    printf "%02d:%s" "$hour" "$min"
  else
    echo ""
  fi
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

# Print existing job names for $AGENT, one per line.
# Exit 0 = listing succeeded (output may be empty = no jobs).
# Exit 3 = listing FAILED (gateway unreachable / bad JSON) — caller must NOT
#          treat this as "no existing jobs" (that would create blind duplicates).
get_existing_cron_names() {
  if ! command -v openclaw &>/dev/null; then
    echo "ERROR: openclaw CLI not found on PATH" >&2
    return 3
  fi
  local raw
  # `openclaw cron list` has no --agent flag and omits disabled jobs without
  # --all; pass --all and filter by agentId in Python.
  raw="$(cd "$STATE_DIR" && openclaw cron list --all --json 2>/dev/null)" || return 3
  echo "$raw" | AGENT="$AGENT" python3 -c "
import sys, json, os
agent = os.environ.get('AGENT','')
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(3)
jobs = data.get('jobs', data) if isinstance(data, dict) else data
for j in (jobs or []):
    if j.get('agentId') == agent:
        print(j.get('name',''))
sys.exit(0)
"
}

should_create_type() {
  [[ "$ONLY_TYPE" == "all" ]] && return 0
  [[ ",$ONLY_TYPE," == *",$1,"* ]] && return 0
  return 1
}

# --- Re-enable system jobs disabled by the imminent-fire guard ---
# create-reminder.sh creates a recurring job DISABLED when its next occurrence is
# imminent (avoids a mid-onboarding early fire). Once a later sync runs — by which
# point the imminent window has passed — re-enable any disabled system jobs so
# they resume their normal daily schedule. Recurring (kind=cron) jobs only;
# one-shots and [custom] jobs are left untouched.
#
# IMPORTANT: this MUST run even when there are no new jobs to create. If every
# queued reminder already exists (all skipped via --skip-existing) and we bailed
# out early, the meal/weight/report crons that the imminent-fire guard left
# enabled=false would NEVER get re-enabled once they already exist — stranding
# them disabled forever (this stranded real users with all their meal reminders
# stuck off). So this is a function called on BOTH the "nothing to create" path
# and the normal completion path (exactly once per invocation).
reenable_disabled_system_jobs() {
  if [[ "$DRY_RUN" == false ]] && command -v openclaw &>/dev/null; then
    local DISABLED_IDS
    DISABLED_IDS="$( (cd "$STATE_DIR" && openclaw cron list --all --json 2>/dev/null) | AGENT="$AGENT" python3 -c "
import sys, json, os
agent = os.environ.get('AGENT','')
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)
jobs = data.get('jobs', data) if isinstance(data, dict) else data
for j in (jobs or []):
    if j.get('agentId') != agent:
        continue
    name = j.get('name','') or ''
    if name.startswith('[custom]'):
        continue
    if (j.get('schedule',{}) or {}).get('kind') != 'cron':
        continue
    if j.get('enabled', True) is False:
        print(j.get('id',''))
" 2>/dev/null || true)"
    if [[ -n "$DISABLED_IDS" ]]; then
      local jid
      while IFS= read -r jid; do
        [[ -z "$jid" ]] && continue
        if (cd "$STATE_DIR" && openclaw cron enable "$jid" >/dev/null 2>&1); then
          echo "Re-enabled previously-disabled system cron: $jid"
        else
          echo "WARNING: failed to re-enable cron $jid" >&2
        fi
      done <<< "$DISABLED_IDS"
    fi
  fi
}

# --- Phase 1: Collect job definitions ---

TIMEZONE=$(get_timezone)
echo "Timezone: $TIMEZONE"

EXISTING_JOBS=""
if [[ "$SKIP_EXISTING" == true ]]; then
  # Fail CLOSED: if we cannot read the existing cron list, abort rather than
  # create blind (the failed-then-retried list error is exactly what produced
  # the duplicate breakfast crons). The per-job idempotency guard in
  # create-reminder.sh is a second line of defense, but the batch must not
  # proceed with stale dedup data when the user explicitly asked to skip dups.
  if ! EXISTING_JOBS=$(get_existing_cron_names); then
    echo "ERROR: --skip-existing was requested but listing existing cron jobs FAILED" >&2
    echo "ERROR: (gateway unreachable from STATE_DIR=$STATE_DIR, or bad JSON)." >&2
    echo "ERROR: Aborting to avoid creating duplicate reminders. Fix the gateway/STATE_DIR and re-run." >&2
    exit 1
  fi
fi

MEAL_SCHEDULE=$(get_meal_schedule)
if [[ -z "$MEAL_SCHEDULE" ]]; then
  # No Meal Schedule yet (e.g. post-first-meal activation: we want the default
  # 3 meal reminders created before the user has confirmed their own times).
  # Fall back to the canonical default schedule rather than aborting. The
  # caller can later confirm/override times → auto-sync rewrites the crons.
  MEAL_SCHEDULE="$DEFAULT_MEAL_SCHEDULE"
  echo "WARNING: No meal times in health-profile.md > Meal Schedule; falling back to default schedule (08:30/12:30/18:30 local)." >&2
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
  [[ "$meal_line" =~ ^Breakfast\ (.+)$ ]] && BREAKFAST_TIME=$(extract_time "${BASH_REMATCH[1]}")
  [[ "$meal_line" =~ ^Dinner\ (.+)$ ]]    && DINNER_TIME=$(extract_time "${BASH_REMATCH[1]}")
done <<< "$MEAL_SCHEDULE"

# 1. Meal reminders
if should_create_type "meal"; then
  while IFS= read -r meal_line; do
    [[ -z "$meal_line" ]] && continue
    meal_name=$(echo "$meal_line" | awk '{print $1}')
    raw_time=$(echo "$meal_line" | cut -d' ' -f2-)
    meal_time=$(extract_time "$raw_time")
    [[ -z "$meal_time" ]] && echo "SKIP: $meal_name — no parseable time in '$raw_time'" && continue
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

if should_create_type "weight" && [[ -n "$EARLIEST_TIME" ]]; then
  ct=$(calc_cron_time "$EARLIEST_TIME" -30)
  cm=$(echo "$ct" | awk '{print $1}'); ch=$(echo "$ct" | awk '{print $2}')
  queue_job "Weight check-in reminder"  "Run notification-composer for weight."                  "$cm $ch * * 6" weight

  ct=$(calc_cron_time "$EARLIEST_TIME" -30)
  cm=$(echo "$ct" | awk '{print $1}'); ch=$(echo "$ct" | awk '{print $2}')
  queue_job "Weight morning followup"   "Run notification-composer for weight_morning_followup." "$cm $ch * * 0" weight
fi

# 3. Weekly report
if should_create_type "report"; then
  queue_job "Weekly report" "Run weekly-report to generate this week's progress report." "0 21 * * 0" other
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

# 6. Product tips (daily, prefer 21:00 — slot allocator handles conflicts)
if should_create_type "tips"; then
  queue_job "Product tips" "Run notification-composer for tips." "0 21 * * *" tips
fi

# 7. Weekly insight (Thursday, prefer 21:00 — slot allocator handles conflicts)
if should_create_type "tips"; then
  queue_job "Weekly insight" "Run notification-composer for weekly-insight." "0 21 * * 4" tips
fi

# 8. First-meal nudge (one-shot, activation flow).
# Created at onboarding completion for users who have a populated Meal Schedule
# but have never logged a meal. Two one-shot jobs:
#   - Day 1: fires ~3-4h after completion at the NEXT meal slot today (if a
#            slot remains today and is in the daytime window), else the first
#            meal slot tomorrow.
#   - Day 2: fires at the first meal slot the following day (softer follow-up).
# Each is a one-shot (--at) that auto-deletes after running. Both route through
# pre-send-check.py --meal-type first_meal_nudge, which self-cancels the moment
# any meal is logged or the cap is reached — so they are safe to over-schedule.
# These are scheduled directly via create-reminder.sh (NOT the queue/slot
# pipeline, which is for recurring crons); one-shots skip anti-burst anyway.
# Timing is deliberately offset from meal-reminder minutes (meal reminders fire
# at slot-15min; the nudge fires AT the meal slot) so the user never gets the
# nudge and a meal reminder minutes apart.
if should_create_type "firstmeal" && [[ -n "$MEAL_SCHEDULE" ]]; then
  # Compute the two one-shot ISO timestamps in the user's timezone.
  # Output: two lines, "DAY1 <iso>" and "DAY2 <iso>" (or nothing if skipped).
  FIRST_MEAL_PLAN=$(MEAL_SCHEDULE="$MEAL_SCHEDULE" TIMEZONE="$TIMEZONE" python3 - <<'PYEOF'
import os, sys
from datetime import datetime, timedelta
try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

tz_name = os.environ.get("TIMEZONE", "Asia/Shanghai")
tz = None
if ZoneInfo:
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = None

now = datetime.now(tz) if tz else datetime.now()

# Parse meal times from "Name <time>" lines, sorted ascending.
# Mirror the shell extract_time(): take the FIRST HH:MM in the value, so
# annotated times like "18:00（注释）" or "07:00-08:00" parse correctly
# (the value is everything after the meal name, which may contain spaces).
import re as _re
slots = []
for line in os.environ.get("MEAL_SCHEDULE", "").splitlines():
    line = line.strip()
    if not line:
        continue
    parts = line.split(None, 1)
    if len(parts) < 2:
        continue
    m = _re.search(r"([0-9]{1,2}):([0-9]{2})", parts[1])
    if not m:
        continue
    hh, mm = int(m.group(1)), int(m.group(2))
    if 0 <= hh < 24 and 0 <= mm < 60:
        slots.append((hh, mm))
if not slots:
    sys.exit(0)
slots.sort()

# Daytime cap: never fire before 08:00 or after 20:00 local.
DAY_START, DAY_END = 8, 20
MIN_LEAD_HOURS = 3  # fire at least ~3h after onboarding completion

def slot_dt(day, hh, mm):
    return day.replace(hour=hh, minute=mm, second=0, microsecond=0)

def clamp_daytime(dt):
    """If dt falls outside the daytime window, push it to next day's DAY_START."""
    if dt.hour < DAY_START:
        return dt.replace(hour=DAY_START, minute=0, second=0, microsecond=0)
    if dt.hour >= DAY_END:
        nxt = dt + timedelta(days=1)
        return nxt.replace(hour=DAY_START, minute=0, second=0, microsecond=0)
    return dt

# Day 1: next meal slot today that is >= now + MIN_LEAD_HOURS and within
# daytime; else first slot tomorrow.
earliest = now + timedelta(hours=MIN_LEAD_HOURS)
day1 = None
for hh, mm in slots:
    cand = slot_dt(now, hh, mm)
    if cand >= earliest and DAY_START <= hh < DAY_END:
        day1 = cand
        break
if day1 is None:
    tomorrow = now + timedelta(days=1)
    hh, mm = slots[0]
    day1 = clamp_daytime(slot_dt(tomorrow, hh, mm))

# Day 2: first meal slot the day AFTER day1.
day2_base = day1 + timedelta(days=1)
hh, mm = slots[0]
day2 = clamp_daytime(slot_dt(day2_base, hh, mm))

def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S%z") if dt.tzinfo else dt.strftime("%Y-%m-%dT%H:%M:%S")

print(f"DAY1 {iso(day1)}")
print(f"DAY2 {iso(day2)}")
PYEOF
)
  FM_DAY1=$(echo "$FIRST_MEAL_PLAN" | awk '/^DAY1/{print $2}')
  FM_DAY2=$(echo "$FIRST_MEAL_PLAN" | awk '/^DAY2/{print $2}')

  # Cron payload: task instruction only (per CONVENTIONS.md §11 — no
  # self-delivery wrapper). nudge=1 / nudge=2 tells the composer which copy
  # to use (day-1 vs softer follow-up).
  FM_MSG_1="First run: python3 {notification-composer:baseDir}/scripts/pre-send-check.py --workspace-dir $WORKSPACE --meal-type first_meal_nudge --tz-offset {tz_offset}. If output is NO_REPLY, stop and output NO_REPLY. Otherwise run notification-composer for first_meal_nudge (nudge=1)."
  FM_MSG_2="First run: python3 {notification-composer:baseDir}/scripts/pre-send-check.py --workspace-dir $WORKSPACE --meal-type first_meal_nudge --tz-offset {tz_offset}. If output is NO_REPLY, stop and output NO_REPLY. Otherwise run notification-composer for first_meal_nudge (nudge=2)."

  if [[ -n "$FM_DAY1" ]]; then
    if [[ "$DRY_RUN" == true ]]; then
      echo "[DRY-RUN] first-meal nudge 1 --at $FM_DAY1"
      echo "[DRY-RUN] first-meal nudge 2 --at $FM_DAY2"
    else
      if ! echo "$EXISTING_JOBS" | grep -qxF "First meal nudge"; then
        bash "$CREATE_REMINDER" --agent "$AGENT" --channel "$CHANNEL" \
          --name "First meal nudge" --message "$FM_MSG_1" --at "$FM_DAY1" || \
          echo "WARNING: failed to create first-meal nudge 1" >&2
      fi
      if [[ -n "$FM_DAY2" ]] && ! echo "$EXISTING_JOBS" | grep -qxF "First meal nudge followup"; then
        bash "$CREATE_REMINDER" --agent "$AGENT" --channel "$CHANNEL" \
          --name "First meal nudge followup" --message "$FM_MSG_2" --at "$FM_DAY2" || \
          echo "WARNING: failed to create first-meal nudge followup" >&2
      fi
    fi
  fi
fi


TOTAL=${#QUEUED_NAMES[@]}
if [[ $TOTAL -eq 0 ]]; then
  echo "No jobs to create."
  # Even with nothing new to create, still re-enable any system crons the
  # imminent-fire guard left disabled — otherwise an all-skipped run (every
  # reminder already exists) would leave them disabled forever.
  reenable_disabled_system_jobs
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
    echo "[DRY-RUN] bash create-reminder.sh --agent \"$AGENT\" --channel \"$CHANNEL\" --exact --tz \"$TIMEZONE\" --name \"$name\" --message \"$message\" --cron \"$adjusted\""
    continue
  fi

  # Pass --tz explicitly so the child never re-detects the timezone (its own
  # workspace-path auto-detect is unreliable across deployment layouts and was
  # the root cause of every reminder landing in Asia/Shanghai).
  (
    bash "$CREATE_REMINDER" \
      --agent   "$AGENT" \
      --channel "$CHANNEL" \
      --exact \
      --tz      "$TIMEZONE" \
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

reenable_disabled_system_jobs

[[ $FAIL_COUNT -gt 0 ]] && exit 1
exit 0
