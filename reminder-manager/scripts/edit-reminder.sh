#!/usr/bin/env bash
set -euo pipefail

# edit-reminder.sh — Edit a cron job, with agent ownership verification.
# Privacy: refuses to edit jobs not owned by --agent.
# Supports: --name, --cron, --at, --in, --message, --enable, --disable, --tz

usage() {
  echo '{"error":"Usage: edit-reminder.sh --agent <agentId> --job <jobId> [--name ...] [--cron ...] [--at ...] [--in ...] [--message ...] [--enable] [--disable] [--tz ...]"}' >&2
  exit 1
}

AGENT_ID=""
JOB_ID=""
EDIT_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --agent)   AGENT_ID="$2"; shift 2 ;;
    --job)     JOB_ID="$2"; shift 2 ;;
    --name)    EDIT_ARGS+=(--name "$2"); shift 2 ;;
    --cron)    EDIT_ARGS+=(--cron "$2"); shift 2 ;;
    --at)      EDIT_ARGS+=(--at "$2"); shift 2 ;;
    --in)      EDIT_ARGS+=(--at "$2"); shift 2 ;;  # alias: --in maps to --at
    --message) EDIT_ARGS+=(--system-event "$2"); shift 2 ;;
    --enable)  EDIT_ARGS+=(--enable); shift ;;
    --disable) EDIT_ARGS+=(--disable); shift ;;
    --tz)      EDIT_ARGS+=(--tz "$2"); shift 2 ;;
    *)         shift ;;
  esac
done

[[ -z "$AGENT_ID" || -z "$JOB_ID" ]] && usage
[[ ${#EDIT_ARGS[@]} -eq 0 ]] && { echo '{"ok":false,"error":"Nothing to edit. Provide at least one of: --name, --cron, --at, --in, --message, --enable, --disable"}'; exit 1; }

# Verify ownership
OWNER=$(openclaw cron list --json --all 2>/dev/null | python3 -c "
import json, sys
data = json.load(sys.stdin)
jobs = data if isinstance(data, list) else data.get('jobs', [])
for j in jobs:
    if j.get('id') == '$JOB_ID':
        print(j.get('agentId', ''))
        sys.exit(0)
print('NOT_FOUND')
")

if [[ "$OWNER" == "NOT_FOUND" ]]; then
  echo '{"ok":false,"error":"Job not found: '"$JOB_ID"'"}'
  exit 1
fi

if [[ "$OWNER" != "$AGENT_ID" ]]; then
  echo '{"ok":false,"error":"Permission denied: job belongs to a different agent"}'
  exit 1
fi

# Edit
if openclaw cron edit "$JOB_ID" "${EDIT_ARGS[@]}" 2>/dev/null; then
  echo '{"ok":true,"edited":"'"$JOB_ID"'"}'
else
  echo '{"ok":false,"error":"Failed to edit job '"$JOB_ID"'"}'
fi
