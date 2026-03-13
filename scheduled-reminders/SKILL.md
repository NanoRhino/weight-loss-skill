---
name: scheduled-reminders
version: 1.1.0
description: "Create and manage scheduled reminders via cron. Provides a wrapper script that auto-resolves delivery config for multiple channels (Slack, WeChat, WeCom, etc.). Use when any skill needs to schedule one-shot or recurring reminders. Other skills (daily-notification, habit-builder, exercise-tracking-planning, etc.) should use this skill for all scheduling needs."
metadata:
  openclaw:
    emoji: "alarm_clock"
    homepage: https://github.com/NanoRhino/weight-loss-skill
---

# Scheduled Reminders

> ⚠️ **SILENT OPERATION:** Never narrate internal actions, skill transitions, or tool calls to the user. No "Let me check...", "Now I'll transition to...", "Reading your profile...". Just do it silently and respond with the result.


Bottom-level scheduling skill. **All cron job creation must go through this script** — do NOT use the cron tool directly.

Script path: `bash {baseDir}/scripts/create-reminder.sh`

## One-shot reminder

```bash
bash {baseDir}/scripts/create-reminder.sh \
  --agent <your-agent-id> \
  --channel <channel> \
  --name "描述性名称" \
  --message "提醒内容" \
  --at "2m"
```

`--at` accepts relative time (`2m`, `1h`, `30s`) or ISO timestamp (`2026-03-04T10:00:00Z`).
One-shot reminders auto-delete after running. Use `--keep` to preserve them.

## Recurring reminder

```bash
# WeChat example
bash {baseDir}/scripts/create-reminder.sh \
  --agent wechat-dm-accjoh25tsvoasahx0psjfg \
  --channel wechat \
  --name "午餐提醒" \
  --message "根据用户的饮食计划发一条友好的午餐提醒。" \
  --cron "0 12 * * *"

# Slack example
bash {baseDir}/scripts/create-reminder.sh \
  --agent 007-zhuoran \
  --channel slack \
  --name "午餐提醒" \
  --message "根据用户的饮食计划发一条友好的午餐提醒。" \
  --cron "0 12 * * *"
```

`--tz` auto-detects from the agent workspace's `timezone.json`. Falls back to `Asia/Shanghai` if not found. You can override explicitly with `--tz`.

## Parameters

| Param | Required | Description |
|-------|----------|-------------|
| `--agent` | ✅ | Your agent ID (e.g. `wechat-dm-xxx`, `007-zhuoran`) |
| `--channel` | ❌ | Delivery channel (`wechat`, `wecom`, `slack`, etc.). Defaults to `slack` if omitted (backward-compatible) |
| `--name` | ✅ | Descriptive job name (shown in cron list) |
| `--message` | ✅ | Prompt sent to user when the job fires |
| `--at` | one of | One-shot: relative time or ISO timestamp |
| `--cron` | one of | Recurring: 5-field cron expression |
| `--tz` | ❌ | Timezone for cron (auto-detects from `timezone.json`, fallback: `Asia/Shanghai`) |
| `--keep` | ❌ | Don't auto-delete one-shot jobs after running |
| `--to` | ❌ | Explicit delivery target. Overrides auto-detection. Required for channels other than `slack`/`wechat`/`wecom` |

## Managing existing jobs

Use the cron tool directly for listing and removing:
- **List**: cron tool with `action: "list"`
- **Remove**: cron tool with `action: "remove"` and `jobId`
- **Adjust timing**: remove old job + create new one

## How it works

The script resolves the delivery target (`--to`) based on the channel:

| Channel | Auto-detection | Example |
|---------|---------------|---------|
| `slack` (default) | Looks up Slack user ID from `~/.openclaw/openclaw.json` bindings → `user:<id>` | `--agent 007-zhuoran` → `user:U12345` |
| `wechat` / `wecom` | Extracts userId from agent ID (`wechat-dm-xxx` → `xxx`) | `--agent wechat-dm-abc123` → `abc123` |
| Others | No auto-detection — must pass `--to` explicitly | `--to "123456789"` |

Timezone auto-detection searches these paths in order:
1. `~/.openclaw/workspace-$AGENT/timezone.json`
2. `~/.openclaw/workspace-nutritionist/$AGENT/timezone.json`

Then calls `openclaw cron add` with `sessionTarget = "isolated"` and `payload.kind = "agentTurn"` automatically.

This ensures delivery config is always correct regardless of which skill creates the reminder.
