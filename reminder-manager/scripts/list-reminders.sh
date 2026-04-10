#!/usr/bin/env bash
set -euo pipefail

# list-reminders.sh — List all cron jobs belonging to a specific agent.
# Output: JSON array of jobs (enabled + disabled).
# Privacy: only returns jobs matching --agent.

usage() {
  echo '{"error":"Usage: list-reminders.sh --agent <agentId>"}' >&2
  exit 1
}

AGENT_ID=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --agent) AGENT_ID="$2"; shift 2 ;;
    *) shift ;;
  esac
done

[[ -z "$AGENT_ID" ]] && usage

# Fetch all jobs (enabled + disabled) as JSON, filter by agentId
openclaw cron list --json --all 2>/dev/null | python3 -c "
import json, sys
data = json.load(sys.stdin)
jobs = data if isinstance(data, list) else data.get('jobs', [])
filtered = [j for j in jobs if j.get('agentId') == '$AGENT_ID']
# Simplify output for agent consumption
result = []
for j in filtered:
    sched = j.get('schedule', {})
    payload = j.get('payload', {})
    result.append({
        'id': j.get('id'),
        'name': j.get('name', ''),
        'enabled': j.get('enabled', False),
        'schedule_type': sched.get('kind', ''),
        'schedule_expr': sched.get('expr', sched.get('at', '')),
        'timezone': sched.get('tz', ''),
        'message': payload.get('text', payload.get('message', '')),
        'session_target': j.get('sessionTarget', ''),
    })
json.dump({'ok': True, 'count': len(result), 'jobs': result}, sys.stdout, ensure_ascii=False, indent=2)
print()
"
