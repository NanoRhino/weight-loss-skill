#!/usr/bin/env bash
set -euo pipefail

# create-reminder.sh — Create a cron job by delegating to notification-manager's script.
# This is a thin wrapper that resolves the notification-manager script path
# and forwards all arguments.

# Resolve notification-manager's create-reminder.sh
SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SKILLS_ROOT="$(cd "$SKILL_DIR/.." && pwd)"
NM_SCRIPT="$SKILLS_ROOT/notification-manager/scripts/create-reminder.sh"

if [[ ! -f "$NM_SCRIPT" ]]; then
  echo '{"ok":false,"error":"notification-manager/scripts/create-reminder.sh not found at '"$NM_SCRIPT"'"}' >&2
  exit 1
fi

exec bash "$NM_SCRIPT" "$@"
