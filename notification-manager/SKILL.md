---
name: notification-manager
version: 1.0.0
description: "Cron infrastructure and reminder lifecycle management for the AI weight loss companion. Creates, syncs, and removes meal/weight reminder cron jobs. Manages the engagement lifecycle (Active → Pause → Recall → Silent). Handles adaptive timing and user reminder setting changes. Use this skill when: meal-planner completes onboarding (to bootstrap reminders), user requests reminder setting changes, or another skill needs to verify/fix cron state. Do NOT use for composing reminder content or handling replies — that is notification-composer's job."
metadata:
  openclaw:
    emoji: "bell"
    homepage: https://github.com/NanoRhino/weight-loss-skill
---

# Notification Manager

> ⚠️ **SILENT OPERATION:** Never narrate internal actions, skill transitions, or tool calls to the user. No "Let me check...", "Now I'll transition to...", "Reading your profile...". Just do it silently and respond with the result.


Orchestration layer for reminders — cron CRUD, lifecycle management, adaptive
timing, and setting changes. This skill decides **when** to send and **whether
to keep sending**. The actual message content is composed by `notification-composer`.

## Cron Infrastructure

### Script

All cron job creation must go through this skill's script:

```bash
bash {baseDir}/scripts/create-reminder.sh
```

This script (migrated from the former `scheduled-reminders` skill) auto-resolves
delivery config for multiple channels (Slack, WeChat, WeCom, etc.).

### One-shot reminder

```bash
bash {baseDir}/scripts/create-reminder.sh \
  --agent <your-agent-id> \
  --channel <channel> \
  --name "Descriptive name" \
  --message "Reminder content" \
  --at "2m"
```

`--at` accepts relative time (`2m`, `1h`, `30s`) or ISO timestamp (`2026-03-04T10:00:00Z`).
One-shot reminders auto-delete after running. Use `--keep` to preserve them.

### Recurring reminder

```bash
bash {baseDir}/scripts/create-reminder.sh \
  --agent <your-agent-id> --channel <channel> --name "Lunch reminder" \
  --message "Run notification-composer for lunch." \
  --cron "0 12 * * *"
```

`--tz` auto-detects from the agent workspace's `timezone.json`. Falls back to `Asia/Shanghai` if not found. You can override explicitly with `--tz`.

### Parameters

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

### How it works

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

### Managing existing jobs

Use the cron tool directly for listing and removing:
- **List**: cron tool with `action: "list"`
- **Remove**: cron tool with `action: "remove"` and `jobId`
- **Adjust timing**: remove old job + create new one

---

## Auto-sync on Activation

**Every time this skill is activated** (by a cron trigger, by another skill like `meal-planner`, or by any interaction), verify that existing cron jobs match the current meal times in `health-profile.md > Meal Schedule`:

1. List existing reminder cron jobs (`action: "list"`).
2. Derive the expected cron times from `health-profile.md > Meal Schedule` (each meal time minus 15 min).
3. Compare:
   - **Missing jobs** (expected time has no matching cron) → create them.
   - **Stale jobs** (cron exists but its time doesn't match any current meal time) → remove then recreate.
   - **Legacy jobs** (cron exists and time matches, but `--message` references `daily-notification` or `daily-notification-skill` instead of `notification-composer`) → remove then recreate with the correct `notification-composer` message. This ensures old cron jobs from before the skill split are automatically migrated.
   - **Matching jobs** (time matches AND message references `notification-composer`) → no action.
4. Also verify the weight reminder cron job exists (Mon & Thu, 30 min before breakfast — see § "Weight reminders" below). Create if missing.
5. Also verify the weekly report cron job exists (Sunday 21:00 — see § "Weekly report" below). Create if missing.
5. Do all of this **silently** — do not mention it to the user.

---

## Cron Job Definitions

Create recurring cron jobs using the script above. Derive the cron times from `health-profile.md > Meal Schedule` (each meal time minus 15 min). **Do NOT pass `--tz`** — the script auto-detects from `timezone.json`. **Pass `--channel`** to match the agent's delivery channel (e.g. `wechat`, `slack`). If omitted, defaults to `slack` for backward compatibility.

Every meal cron `--message` MUST tell the agent to run `notification-composer` for that meal, AND include the NO_REPLY enforcement clause. This is critical because `delivery.mode = announce` will deliver any text the agent outputs — if the agent adds reasoning alongside `NO_REPLY`, the reasoning text gets sent to the user.

**Meal reminder message template:**
```
Run notification-composer for <meal>. CRITICAL: If pre-send checks fail, output ONLY the exact string NO_REPLY — nothing before it, nothing after it. No explanations, no reasoning. NO_REPLY must be your complete and only output.
```

```bash
# Example: 3 meals, reminders 15 min before each (adjust times from health-profile.md)
bash {baseDir}/scripts/create-reminder.sh \
  --agent <your-agent-id> --channel <channel> --name "Breakfast reminder" \
  --message "Run notification-composer for breakfast. CRITICAL: If pre-send checks fail, output ONLY the exact string NO_REPLY — nothing before it, nothing after it. No explanations, no reasoning. NO_REPLY must be your complete and only output." \
  --cron "45 6 * * *"

bash {baseDir}/scripts/create-reminder.sh \
  --agent <your-agent-id> --channel <channel> --name "Lunch reminder" \
  --message "Run notification-composer for lunch. CRITICAL: If pre-send checks fail, output ONLY the exact string NO_REPLY — nothing before it, nothing after it. No explanations, no reasoning. NO_REPLY must be your complete and only output." \
  --cron "45 11 * * *"

bash {baseDir}/scripts/create-reminder.sh \
  --agent <your-agent-id> --channel <channel> --name "Dinner reminder" \
  --message "Run notification-composer for dinner. CRITICAL: If pre-send checks fail, output ONLY the exact string NO_REPLY — nothing before it, nothing after it. No explanations, no reasoning. NO_REPLY must be your complete and only output." \
  --cron "45 17 * * *"
```

### Weight reminders (2x/week)

Cron time = breakfast time minus **30 min** (not 15 min like meals). Derive from `health-profile.md > Meal Schedule`.

```bash
# Example assumes breakfast at 07:00 → weight cron at 06:30
bash {baseDir}/scripts/create-reminder.sh \
  --agent <your-agent-id> --channel <channel> --name "Weight check-in reminder" \
  --message "Run notification-composer for weight." \
  --cron "30 6 * * 1,4"
```

### Weekly report (Sunday 9 PM)

One fixed cron job — every Sunday at 21:00 user local time.

```bash
bash {baseDir}/scripts/create-reminder.sh \
  --agent <your-agent-id> --channel <channel> --name "Weekly report" \
  --message "Run weekly-report to generate this week's progress report." \
  --cron "0 21 * * 0"
```

---

## Lifecycle: Active → Recall → Silent

```
Stage 1: ACTIVE — normal reminders
    │
    └── 2 full calendar days: zero replies + zero messages
           │
Stage 2: PAUSE — stop all reminders, send first recall
    │
    ├── User replies → back to Stage 1
    └── 3 days, no reply
           │
Stage 3: SECOND RECALL — one final message
    │
    ├── User replies → back to Stage 1
    └── No reply → Stage 4
           │
Stage 4: SILENT — send nothing. Wait for user to return.
```

Recall replaces the next meal reminder slot — don't send at random hours.
Weight reminders also stop at Stage 2. Write current stage to
`data/engagement.json > notification_stage`.

**Stage transition logic:** This skill periodically checks `data/engagement.json > last_interaction`
to detect when the user has gone silent. When a stage transition occurs, update
`data/engagement.json > notification_stage`. The `notification-composer` reads this value to
decide whether to send a normal reminder, a recall message, or nothing at all.

**When a silent user returns:**
Reset to Stage 1. Resume normal reminders. The warm welcome message itself
is composed by `notification-composer`.

---

## Adaptive Timing (within Stage 1)

| Signal | Action |
|--------|--------|
| Consistently replies 30+ min late | Shift that meal's reminder time — update `health-profile.md > Meal Schedule` (the auto-sync logic will fix the cron on next activation) |
| Never replies to breakfast (2+ weeks) | Stop breakfast reminders |

When a meal time changes, update `health-profile.md > Meal Schedule` — auto-sync will fix the cron on next activation.

---

## Reminder Settings Changes

Users may ask to change reminders in natural language. Handle inline:

| User says | Action |
|-----------|--------|
| "Stop breakfast reminders" | Stop that meal's reminders. Update `data/engagement.json > reminder_config`. Confirm: `"Done — no more breakfast reminders. Let me know if you change your mind."` |
| "Change dinner to 8 PM" | Update `health-profile.md > Meal Schedule` with the new time. The auto-sync will update the cron on next activation. Confirm: `"Got it — dinner reminders moved to 7:45 PM."` |
| "Stop all reminders" | Stop everything, move to Stage 4. `"All reminders off. I'm still here if you want to chat. 💛"` |
| "Remind me more" / "Can you also remind me for snacks" | Outside current scope — acknowledge and note for future: `"I can only do meals and weight for now, but I'll keep that in mind."` |
| "Resume reminders" / "Start reminding me again" | Restart Stage 1 with previous config. Confirm schedule. |

---

## Workspace

### Reads

| Source | Field / Path | Purpose |
|--------|-------------|---------|
| `health-profile.md` | `Meal Schedule` | Reminder schedule + max reminders/day |
| `data/engagement.json` | `last_interaction` | Stage detection |

### Writes

| Path | How | When |
|------|-----|------|
| `data/engagement.json` | `notification_stage` — direct write | Stage transitions |
| `data/engagement.json` | `reminder_config` — direct write | Adaptive timing changes, user setting changes |
| `health-profile.md > Meal Schedule` | direct write | Adaptive timing updates, user-requested time changes |

---

## Skill Routing

**See `SKILL-ROUTING.md` for the full conflict resolution system.** This skill
is **Priority Tier P4 (Reporting)**. It handles the orchestration side of
reminders — cron management, lifecycle, and settings. The execution side
(composing messages, handling replies) is handled by `notification-composer`.
