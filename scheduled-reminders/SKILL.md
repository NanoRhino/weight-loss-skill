---
name: scheduled-reminders
version: 1.0.0
description: "Create and manage scheduled reminders via cron. Provides a wrapper script that auto-resolves Slack delivery config from agent bindings. Use when any skill needs to schedule one-shot or recurring reminders. Other skills (daily-notification, habit-builder, exercise-programming, etc.) should use this skill for all scheduling needs."
metadata:
  openclaw:
    emoji: "alarm_clock"
    homepage: https://github.com/NanoRhino/weight-loss-skill
---

# Scheduled Reminders

Bottom-level scheduling skill. **All cron job creation must go through this script** — do NOT use the cron tool directly.

Script path: `bash {baseDir}/scripts/create-reminder.sh`

## One-shot reminder

```bash
bash {baseDir}/scripts/create-reminder.sh \
  --agent <your-agent-id> \
  --name "描述性名称" \
  --message "提醒内容" \
  --at "2m"
```

`--at` accepts relative time (`2m`, `1h`, `30s`) or ISO timestamp (`2026-03-04T10:00:00Z`).
One-shot reminders auto-delete after running. Use `--keep` to preserve them.

## Recurring reminder

```bash
bash {baseDir}/scripts/create-reminder.sh \
  --agent <your-agent-id> \
  --name "午餐提醒" \
  --message "根据用户的饮食计划发一条友好的午餐提醒。" \
  --cron "0 12 * * *" \
  --tz "Asia/Shanghai"
```

`--tz` defaults to `Asia/Shanghai`. Set to the user's timezone from `USER.md`.

## Parameters

| Param | Required | Description |
|-------|----------|-------------|
| `--agent` | ✅ | Your agent ID (e.g. `007-zhuoran`) |
| `--name` | ✅ | Descriptive job name (shown in cron list) |
| `--message` | ✅ | Prompt sent to user when the job fires |
| `--at` | one of | One-shot: relative time or ISO timestamp |
| `--cron` | one of | Recurring: 5-field cron expression |
| `--tz` | ❌ | Timezone for cron (default: `Asia/Shanghai`) |
| `--keep` | ❌ | Don't auto-delete one-shot jobs after running |

## Managing existing jobs

Use the cron tool directly for listing and removing:
- **List**: cron tool with `action: "list"`
- **Remove**: cron tool with `action: "remove"` and `jobId`
- **Adjust timing**: remove old job + create new one

## How it works

The script:
1. Looks up the agent's Slack user ID from `~/.openclaw/openclaw.json` bindings
2. Calls `openclaw cron add` with correct `delivery.channel = "slack"` and `delivery.to = "user:<id>"`
3. Sets `sessionTarget = "isolated"` and `payload.kind = "agentTurn"` automatically

This ensures delivery config is always correct regardless of which skill creates the reminder.
