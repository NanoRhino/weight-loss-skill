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

`--tz` auto-detects from the agent workspace's `USER.md`. Falls back to `Asia/Shanghai` if not found. You can override explicitly with `--tz`.

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
| `slack` (default) | Looks up Slack user ID from `.openclaw-gateway/openclaw.json` bindings → `user:<id>` | `--agent 007-zhuoran` → `user:U12345` |
| `wechat` / `wecom` | Extracts userId from agent ID (`wechat-dm-xxx` → `xxx`) | `--agent wechat-dm-abc123` → `abc123` |
| Others | No auto-detection — must pass `--to` explicitly | `--to "123456789"` |

Timezone auto-detection searches these paths in order:
1. `.openclaw-user-service/workspaces/$AGENT/USER.md`

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

### Batch creation (preferred for initial setup)

When creating ALL reminders for a user (e.g., after meal-planner completes onboarding), use the batch script instead of calling `create-reminder.sh` multiple times:

```bash
bash {baseDir}/scripts/batch-create-reminders.sh \
  --agent <your-agent-id> \
  --channel <channel> \
  --workspace <path-to-user-workspace>
```

This reads `health-profile.md` and `USER.md` from the workspace, calculates all cron times, and creates every required job (meal reminders, weight reminders, daily review, weekly report, diet pattern detection) in one execution.

| Param | Required | Description |
|-------|----------|-------------|
| `--agent` | ✅ | Agent ID |
| `--channel` | ✅ | Delivery channel |
| `--workspace` | ✅ | Path to user workspace directory |
| `--dry-run` | ❌ | Print commands without executing |
| `--skip-existing` | ❌ | Skip jobs that already exist (matches by name) |
| `--only <type>` | ❌ | Only create: `meal`, `weight`, `review`, `report`, `pattern`, or `all` (default) |

**When to use batch vs individual:**
- **Batch** (`batch-create-reminders.sh`): Initial setup after onboarding, re-syncing all reminders
- **Individual** (`create-reminder.sh`): One-shot reminders, individual job adjustments, custom reminders

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
4. Also verify weight reminder cron jobs exist — see § "Weight reminders" below. This includes the primary (Wed & Sat morning), evening followup (Wed & Sat after dinner), and next-morning followup (Thu & Sun morning). Create any that are missing.
5. Also verify the weekly report cron job exists (Sunday 21:00 — see § "Weekly report" below). Create if missing.
6. Also verify the daily review cron job exists (dinner + 3h — see § "Daily review" below). Create if missing. If dinner time changed, remove and recreate.
7. **Diet pattern detection** — special handling:
   - Read `health-profile.md > Automation > Pattern Detection Completed`
   - If has a date → job already completed. If job still exists, remove it (stale).
   - If `—` (not completed) → check if job exists. If missing AND `Onboarding Completed` has a date → create it.
   - If `Onboarding Completed` is `—` → skip (onboarding not done yet).
8. Do all of this **silently** — do not mention it to the user.

**Optimization:** When auto-sync detects that NO cron jobs exist for this user (initial setup), run `batch-create-reminders.sh` instead of creating jobs individually. This avoids multiple LLM round-trips. For incremental sync (some jobs exist, some missing/stale), use individual `create-reminder.sh` calls or remove-then-batch.

---

## Cron Job Definitions

Create recurring cron jobs using the script above. Derive the cron times from `health-profile.md > Meal Schedule` (each meal time minus 15 min). **Do NOT pass `--tz`** — the script auto-detects from `USER.md`. **Pass `--channel`** to match the agent's delivery channel (e.g. `wechat`, `slack`). If omitted, defaults to `slack` for backward compatibility.

> 💡 **Performance tip:** For initial reminder setup (all jobs need creation), prefer `batch-create-reminders.sh` — it creates all jobs in one script execution. The individual examples below are kept as reference for the auto-sync logic and single-job adjustments.

> ⚠️ **Cron expressions use the user's LOCAL time. Do NOT convert to UTC.** The script sets `--tz` automatically, so the cron scheduler handles timezone conversion. Example: if meal is at 09:00 Beijing time, the cron expression is `45 8 * * *` (08:45 local), NOT `45 0 * * *`.

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

### Weight reminders (2x/week + followups)

**Primary reminder:** Cron time = breakfast time minus **30 min**. Fires Wed & Sat.

```bash
# Example assumes breakfast at 07:00 → weight cron at 06:30
bash {baseDir}/scripts/create-reminder.sh \
  --agent <your-agent-id> --channel <channel> --type weight --name "Weight check-in reminder" \
  --message "Run notification-composer for weight." \
  --cron "30 6 * * 3,6"
```

**Evening followup:** Cron time = dinner time plus **30 min**. Fires same days (Wed & Sat). Only sends if the user did NOT weigh in that day — reminds them to weigh tomorrow morning. Pre-send-check uses `weight_evening` type.

```bash
# Example assumes dinner at 18:30 → evening followup at 19:00
bash {baseDir}/scripts/create-reminder.sh \
  --agent <your-agent-id> --channel <channel> --type weight --name "Weight evening followup" \
  --message "Run notification-composer for weight_evening." \
  --cron "0 19 * * 3,6"
```

**Next-morning followup:** Cron time = breakfast time minus **30 min**. Fires Thu & Sun (day after primary). Only sends if the user did NOT weigh in yesterday OR today. Pre-send-check uses `weight_morning_followup` type.

```bash
# Example assumes breakfast at 07:00 → morning followup at 06:30
bash {baseDir}/scripts/create-reminder.sh \
  --agent <your-agent-id> --channel <channel> --type weight --name "Weight morning followup" \
  --message "Run notification-composer for weight_morning_followup." \
  --cron "30 6 * * 4,0"
```

### Weekly report (Sunday 9 PM)

One fixed cron job — every Sunday at 21:00 user local time.

```bash
bash {baseDir}/scripts/create-reminder.sh \
  --agent <your-agent-id> --channel <channel> --name "Weekly report" \
  --message "Run weekly-report to generate this week's progress report." \
  --cron "0 21 * * 0"
```

### Daily review (every day, dinner + 3h)

Daily nutrition summary. Cron time = dinner reminder time + 3 hours. Derive dinner time from `health-profile.md > Meal Schedule`. Example: dinner at 18:00 → daily review cron at 21:00.

```bash
bash {baseDir}/scripts/create-reminder.sh \
  --agent <your-agent-id> --channel <channel> --name "Daily review" \
  --message "Run daily-review to generate today's nutrition summary." \
  --cron "0 21 * * *"
```

Included in auto-sync: when dinner time changes, adjust this cron accordingly.

### Diet pattern detection (self-destructing, onboarding + 3 days)

One-time diet pattern analysis. Created at onboarding, starts running 3 days after `Onboarding Completed` date (from `health-profile.md > Automation`). Cron time = same as daily review (dinner + 3h).

```bash
bash {baseDir}/scripts/create-reminder.sh \
  --agent <your-agent-id> --channel <channel> --name "Diet pattern detection" \
  --message "Run diet-pattern-detection skill." \
  --cron "0 21 * * *"
```

**Not included in normal auto-sync** — this job is managed by its own lifecycle:
- Created once at onboarding (by notification-manager)
- Self-deleted by diet-pattern-detection skill after successful execution
- See auto-sync special handling below

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
