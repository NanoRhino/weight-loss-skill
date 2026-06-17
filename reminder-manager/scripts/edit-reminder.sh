#!/usr/bin/env bash
set -euo pipefail

# edit-reminder.sh — Edit a cron job, with agent ownership verification.
# Privacy: refuses to edit jobs not owned by --agent.
# Supports: --name, --cron, --at, --in, --message, --enable, --tz
#
# ⚠️ --disable 已移除（2026-06-17）：disable cron 的入口收口到系统级 churn-scan 唯一一处，
# agent 不得 disable 任何 cron。想让用户暂停接收提醒 → 走 notification-composer 的
# leave-manager.py 写 leave.json（pre-send-check 在请假期自动静默 cron、到期自动恢复，
# 全程不碰 cron）。直接 disable 会导致：①请假结束提醒恢复不回来（churn/re-enable 只认
# churn 关的）②破坏沉默生命周期收口。误传 --disable 会被拒绝并提示走 leave。

usage() {
  echo '{"error":"Usage: edit-reminder.sh --agent <agentId> --job <jobId> [--name ...] [--cron ...] [--at ...] [--in ...] [--message ...] [--enable] [--tz ...]"}' >&2
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
    --disable)
      echo '{"ok":false,"error":"--disable is not allowed. Agents must NOT disable cron jobs. To pause reminders for a user, use notification-composer leave-manager.py to write leave.json (pre-send-check auto-silences crons during leave and auto-restores on expiry, without ever disabling them)."}' >&2
      exit 1 ;;
    --tz)      EDIT_ARGS+=(--tz "$2"); shift 2 ;;
    *)         shift ;;
  esac
done

[[ -z "$AGENT_ID" || -z "$JOB_ID" ]] && usage
[[ ${#EDIT_ARGS[@]} -eq 0 ]] && { echo '{"ok":false,"error":"Nothing to edit. Provide at least one of: --name, --cron, --at, --in, --message, --enable, --tz"}'; exit 1; }

# Verify ownership: fetch this agent's jobs (server-side filter avoids the
# 200-result cap), check this job is in the list.
OWNER=$(openclaw cron list --json --all --agent "$AGENT_ID" 2>/dev/null | python3 -c "
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
