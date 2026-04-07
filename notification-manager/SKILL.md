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
| `--type` | ❌ | Job type for anti-burst scheduling: `meal`, `weight`, or `other` (default: `other`). See **Anti-burst scheduling** below |
| `--exact` | ❌ | Skip anti-burst logic, use exact cron time. Use for time-sensitive reminders that must fire at the precise minute |

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

### Anti-burst scheduling

When creating **recurring** cron jobs (`--cron`), the script automatically avoids
scheduling too many jobs at the same minute to prevent bulk message sends that
could trigger platform rate limits or account bans.

**How it works:**
1. Fetches all existing recurring cron jobs from the gateway
2. Converts all cron times to UTC for cross-timezone comparison
3. Checks if the target minute already has ≥2 jobs
4. If full, scans nearby minutes for an available slot (< 2 jobs per minute)
5. Adjusts the cron expression to the chosen slot

**Search windows by `--type`:**

| Type | Window | Use case |
|------|--------|----------|
| `meal` | target −10 to +5 min | Meal reminders (breakfast/lunch/dinner/snack) |
| `weight` | target −10 to +5 min | Weight check-in reminders |
| `other` (default) | target −10 to target | Other recurring reminders |

**Slot priority:** scans outward from target time (target, target−1, target+1,
target−2, ...) to stay as close to the intended time as possible.

**Edge cases:**
- One-shot jobs (`--at`) skip anti-burst entirely
- `--exact` flag skips anti-burst for time-critical reminders
- If the entire window is full (very unlikely — would need 30+ jobs in a
  15-minute window), falls back to the original time with a warning

**Important:** Always pass `--type meal` for meal reminders and `--type weight`
for weight reminders. This ensures correct window sizing.

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

Every meal cron `--message` MUST tell the agent to run `notification-composer` for that meal. Keep it minimal — notification-composer owns pre-send checks, message composition, and reply handling. Do not duplicate its rules in the cron message.

```bash
# Example: 3 meals, reminders 15 min before each (adjust times from health-profile.md)
# Note: --type meal ensures anti-burst scheduling with [-10, +5] min window
bash {baseDir}/scripts/create-reminder.sh \
  --agent <your-agent-id> --channel <channel> --type meal --name "Breakfast reminder" \
  --message "Run notification-composer for breakfast." \
  --cron "45 6 * * *"

bash {baseDir}/scripts/create-reminder.sh \
  --agent <your-agent-id> --channel <channel> --type meal --name "Lunch reminder" \
  --message "Run notification-composer for lunch." \
  --cron "45 11 * * *"

bash {baseDir}/scripts/create-reminder.sh \
  --agent <your-agent-id> --channel <channel> --type meal --name "Dinner reminder" \
  --message "Run notification-composer for dinner." \
  --cron "45 17 * * *"
```

### Weight reminders (2x/week)

Cron time = breakfast time minus **30 min** (not 15 min like meals). Derive from `health-profile.md > Meal Schedule`.

```bash
# Example assumes breakfast at 07:00 → weight cron at 06:30
bash {baseDir}/scripts/create-reminder.sh \
  --agent <your-agent-id> --channel <channel> --type weight --name "Weight check-in reminder" \
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

## Guided Feedback Scheduling

Manages the progressive guided-feedback system that teaches users they can
customize the AI's behavior. Questions are scheduled as **one-shot cron jobs**
and consumed strictly in queue order — one question per day maximum.

### Data File: `data/guided-feedback.json`

**Owner:** This skill (scheduling + counter updates) and `notification-composer`
(reply processing).

```json
{
  "total_check_ins": 0,
  "distinct_active_days": [],
  "queue": [
    {
      "id": "reminder-timing",
      "group": "reminder",
      "topic": "提醒时间",
      "trigger": "total_check_ins >= 3",
      "status": "pending",
      "scheduled_at": null,
      "asked_at": null,
      "answered_at": null,
      "answer": null
    },
    {
      "id": "reminder-frequency",
      "group": "reminder",
      "topic": "提醒频次（没回要不要再提醒）",
      "trigger": "previous answered|skipped|covered",
      "status": "pending",
      "scheduled_at": null,
      "asked_at": null,
      "answered_at": null,
      "answer": null
    },
    {
      "id": "reminder-style",
      "group": "reminder",
      "topic": "提醒内容风格",
      "trigger": "previous answered|skipped|covered",
      "status": "pending",
      "scheduled_at": null,
      "asked_at": null,
      "answered_at": null,
      "answer": null
    },
    {
      "id": "feedback-tone",
      "group": "feedback",
      "topic": "饮食反馈语气",
      "trigger": "previous answered|skipped|covered",
      "same_day_chain": ["food-preference", "advice-intensity"],
      "status": "pending",
      "scheduled_at": null,
      "asked_at": null,
      "answered_at": null,
      "answer": null
    },
    {
      "id": "food-preference",
      "group": "feedback",
      "topic": "推荐食物偏好",
      "trigger": "same_day_chain (feedback-tone answered)",
      "status": "pending",
      "scheduled_at": null,
      "asked_at": null,
      "answered_at": null,
      "answer": null
    },
    {
      "id": "advice-intensity",
      "group": "feedback",
      "topic": "建议力度（要不要说后果）",
      "trigger": "same_day_chain (food-preference answered)",
      "status": "pending",
      "scheduled_at": null,
      "asked_at": null,
      "answered_at": null,
      "answer": null
    },
    {
      "id": "open-review",
      "group": "review",
      "topic": "开放式回顾",
      "trigger": "distinct_active_days >= 5",
      "status": "pending",
      "scheduled_at": null,
      "asked_at": null,
      "answered_at": null,
      "answer": null
    }
  ],
  "preference_signals": []
}
```

### Status Lifecycle

```
pending → scheduled → asked → answered | skipped | covered
```

- `pending`: Not yet triggered
- `scheduled`: One-shot cron job created, `scheduled_at` set
- `asked`: Message delivered to user, `asked_at` set
- `answered`: User replied, `answered_at` + `answer` set
- `skipped`: 24h elapsed after `asked_at` with no reply
- `covered`: `preference_signals` already covers this question (skip it)

### Trigger Chain

After each meal check-in is logged by `diet-tracking-analysis`:

1. `diet-tracking-analysis` updates `total_check_ins` (+1) and
   `distinct_active_days` (append today's date if not present).
2. This skill checks whether the next `pending` question's trigger
   condition is met.
3. If met, check `preference_signals` for entries whose `covers` field
   matches the question `id`:
   - If covered → mark `status: "covered"`, check the next question.
   - If not covered → create a one-shot cron job.

### Scheduling Rules

**Timing:** Schedule the question for the **current day's last meal
reminder time + 60 minutes**. Read `health-profile.md > Meal Schedule`
to determine the last meal time.

**One question per day:** If a question was already asked or scheduled
today, do not schedule another. The next question goes to the
**next active day** (the next day the user logs a meal), at last meal
reminder + 60min.

**Cron creation:**

```bash
bash {baseDir}/scripts/create-reminder.sh \
  --agent <agent> --channel <channel> \
  --type other --exact \
  --name "Guided feedback: <question-id>" \
  --message "Run notification-composer for guided-feedback <question-id>." \
  --at "<last-meal-time + 60min as ISO timestamp>"
```

After creating the job, update the question's `status` to `"scheduled"`
and set `scheduled_at`.

### Trigger Conditions

| Question | Condition | Schedule Time |
|----------|-----------|---------------|
| `reminder-timing` | `total_check_ins >= 3` | Same day, last meal + 1h |
| `reminder-frequency` | Previous question terminal (`answered`/`skipped`/`covered`) | **Next day**, last meal + 1h |
| `reminder-style` | Previous question terminal | **Next day**, last meal + 1h |
| `feedback-tone` | Previous question terminal | **Next day**, last meal + 1h |
| `food-preference` | Same-day chain: `feedback-tone` answered | **Same day**, immediately after `feedback-tone` reply |
| `advice-intensity` | Same-day chain: `food-preference` answered | **Same day**, immediately after `food-preference` reply |
| `open-review` | `distinct_active_days.length >= 5` | Same day, last meal + 1h |

### Same-Day Chain

`feedback-tone`, `food-preference`, and `advice-intensity` form a **same-day
chain**: they are asked on the same day, one after another, as the user
replies. This avoids spreading 3 closely related questions across 3 separate
days.

**How it works:**
1. `feedback-tone` is scheduled via cron (normal next-day trigger).
2. When the user answers `feedback-tone`, `notification-composer` immediately
   sends `food-preference` as a follow-up in the same conversation turn
   (no cron needed — it's a direct follow-up message).
3. When the user answers `food-preference`, `notification-composer` immediately
   sends `advice-intensity`.
4. If the user doesn't answer one in the chain, the chain stops. The
   unanswered question gets the 24h skip timer as usual. The remaining
   chained questions stay `pending` and are skipped (marked `skipped`)
   along with the unanswered one.

**Important:** Same-day chain questions do NOT get their own cron jobs.
Only the chain head (`feedback-tone`) is scheduled via cron.

### Conflict Avoidance

- If `open-review` and another question would both trigger on the same day,
  the sequential queue question takes priority; `open-review` defers to
  the next active day.
- If the scheduled time falls within 30min of the daily-review auto-trigger
  (1h after last meal log), shift the guided-feedback question to +90min
  instead of +60min.

### Skip Timer

When a question has been in `asked` status for 24 hours with no reply:
- Mark it `"skipped"`
- Trigger scheduling of the next question (follows the "next day" rule)

This check runs every time this skill is activated (similar to auto-sync).

### Acting on Reminder Setting Changes

When a guided-feedback reply changes reminder settings (processed by
`notification-composer`, written to `ai-preferences.md`), this skill
must act on the change:

| Changed Field | Action |
|---------------|--------|
| `Reminder Lead Time` | Recalculate cron times: meal time − new lead time. Auto-sync will fix crons on next activation. |
| `Reminder Repeat` | If `true`, create a second one-shot reminder for each meal at meal time + 30min (only if first reminder got no reply). If `false`, remove repeat reminders. |
| `Reminder Content` | No cron change needed — `notification-composer` reads this at compose time. |

---

## Workspace

### Reads

| Source | Field / Path | Purpose |
|--------|-------------|---------|
| `health-profile.md` | `Meal Schedule` | Reminder schedule + max reminders/day |
| `data/engagement.json` | `last_interaction` | Stage detection |
| `data/guided-feedback.json` | `queue`, `preference_signals` | Guided feedback scheduling |
| `ai-preferences.md` | `Reminder Settings` | Act on user preference changes |

### Writes

| Path | How | When |
|------|-----|------|
| `data/engagement.json` | `notification_stage` — direct write | Stage transitions |
| `data/engagement.json` | `reminder_config` — direct write | Adaptive timing changes, user setting changes |
| `health-profile.md > Meal Schedule` | direct write | Adaptive timing updates, user-requested time changes |
| `data/guided-feedback.json` | `queue[].status`, `queue[].scheduled_at` — direct write | Scheduling questions, skip timer |

---

## Skill Routing

**See `SKILL-ROUTING.md` for the full conflict resolution system.** This skill
is **Priority Tier P4 (Reporting)**. It handles the orchestration side of
reminders — cron management, lifecycle, and settings. The execution side
(composing messages, handling replies) is handled by `notification-composer`.
