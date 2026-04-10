#!/usr/bin/env bash
set -euo pipefail

# delete-reminder.sh — Delete a cron job, with agent ownership verification.
# Privacy: refuses to delete jobs not owned by --agent.

usage() {
  echo '{"error":"Usage: delete-reminder.sh --agent <agentId> --job <jobId>"}' >&2
  exit 1
}

AGENT_ID=""
JOB_ID=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --agent) AGENT_ID="$2"; shift 2 ;;
    --job)   JOB_ID="$2"; shift 2 ;;
    *)       shift ;;
  esac
done

[[ -z "$AGENT_ID" || -z "$JOB_ID" ]] && usage

# Verify ownership: fetch all jobs, check this job belongs to agent
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

# Delete
openclaw cron rm "$JOB_ID" --json 2>/dev/null && \
  echo '{"ok":true,"deleted":"'"$JOB_ID"'"}' || \
  echo '{"ok":false,"error":"Failed to delete job '"$JOB_ID"'"}'
