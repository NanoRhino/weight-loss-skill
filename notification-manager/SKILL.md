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
| `slack` (default) | Looks up Slack user ID from `~/.openclaw/openclaw.json` bindings → `user:<id>` | `--agent 007-zhuoran` → `user:U12345` |
| `wechat` / `wecom` | Extracts userId from agent ID (`wechat-dm-xxx` → `xxx`) | `--agent wechat-dm-abc123` → `abc123` |
| Others | No auto-detection — must pass `--to` explicitly | `--to "123456789"` |

Timezone auto-detection searches these paths in order:
1. `~/.openclaw/workspace-$AGENT/USER.md`
2. `~/.openclaw/workspace-nutritionist/$AGENT/USER.md`

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
4. Also verify weight reminder cron jobs exist — see § "Weight reminders" below. This includes the primary (Wed & Sat morning), evening followup (Wed & Sat after dinner), and next-morning followup (Thu & Sun morning). Create any that are missing.
5. Also verify the weekly report cron job exists (Sunday 21:00 — see § "Weekly report" below). Create if missing.
6. **Diet pattern detection** — special handling:
   - Read `health-profile.md > Automation > Pattern Detection Completed`
   - If has a date → job already completed. If job still exists, remove it (stale).
   - If `—` (not completed) → check if job exists. If missing AND `Onboarding Completed` has a date → create it.
   - If `Onboarding Completed` is `—` → skip (onboarding not done yet).
7. Do all of this **silently** — do not mention it to the user.

---

## Cron Job Definitions

Create recurring cron jobs using the script above. Derive the cron times from `health-profile.md > Meal Schedule` (each meal time minus 15 min). **Do NOT pass `--tz`** — the script auto-detects from `USER.md`. **Pass `--channel`** to match the agent's delivery channel (e.g. `wechat`, `slack`). If omitted, defaults to `slack` for backward compatibility.

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
Stage 1: ACTIVE — normal reminders (Day 2-3: morning nudge + normal recommendation)
    │
    └── 3 full calendar days: zero replies + zero messages
           │
Stage 2: RECALL — stop normal reminders, send daily recall (Day 4-6)
    │       First meal cron of the day: one recall message (no meal recommendations)
    │       Subsequent meal crons + weight: suppressed
    │       Tone escalation: Day 4 clingy → Day 5 fake angry → Day 6 pouty/vulnerable
    │
    ├── User replies → back to Stage 1
    └── 3 days, no reply
           │
Stage 3: FINAL RECALL — one last emotional message
    │
    ├── User replies → back to Stage 1
    └── 1 day, no reply → Stage 4
           │
Stage 4: SILENT — send nothing. Wait for user to return.
```

Recall replaces the next meal reminder slot — don't send at random hours.
Weight reminders also stop at Stage 2. Write current stage to
`data/engagement.json > notification_stage`.

**Stage transition logic:** Before every reminder, `notification-composer` calls this skill's
stage-check script to update the engagement stage:

```bash
python3 {baseDir}/scripts/check-stage.py \
  --workspace-dir {workspaceDir} \
  --tz-offset {tz_offset}
```

The script scans `data/meals/*.json` to find the most recent date with a logged
meal — this is the "last interaction". No platform-level timestamp needed; meal
records are the ground truth. It calculates calendar days since that date and
advances `notification_stage` when thresholds are met. It also resets to Stage 1
when a silent user returns (new meal logged today/yesterday but stage > 1).

The `notification-composer` then reads the updated stage to decide whether to
send a normal reminder, a recall message, or nothing at all.

During Stage 2 (Day 4-6), `notification-composer` sends one recall per day
(morning only) and writes `last_recall_date` to `data/engagement.json`.
After the final recall (Stage 3), it writes `recall_2_sent: true`.

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

Schema: `references/guided-feedback-schema.md`
Script: `{baseDir}/scripts/guided-feedback-state.py`

### Script Commands

```bash
# Initialize (during onboarding)
python3 {baseDir}/scripts/guided-feedback-state.py --workspace-dir {workspaceDir} --tz-offset {tz_offset} init

# After each meal check-in (called by diet-tracking-analysis)
python3 {baseDir}/scripts/guided-feedback-state.py --workspace-dir {workspaceDir} --tz-offset {tz_offset} increment

# Check what to schedule next
python3 {baseDir}/scripts/guided-feedback-state.py --workspace-dir {workspaceDir} --tz-offset {tz_offset} next
# → {"action":"schedule"|"wait"|"done", "question_id":...}

# Update question status
python3 {baseDir}/scripts/guided-feedback-state.py --workspace-dir {workspaceDir} --tz-offset {tz_offset} update \
  --question-id <id> --new-status <scheduled|asked|answered|skipped> [--answer <text>]
# → {"updated":..., "chain_next": "<next-id>"|null}

# Check 24h skip timer (run on every activation)
python3 {baseDir}/scripts/guided-feedback-state.py --workspace-dir {workspaceDir} --tz-offset {tz_offset} skip-check
```

### Existing User Backfill

If `guided-feedback.json` doesn't exist when any command runs, the script
auto-initializes it and backfills `total_check_ins` and `distinct_active_days`
from existing `data/meals/*.json` files. This means existing users who already
have enough check-ins will immediately qualify for guided-feedback questions
on their next meal log.

### Scheduling Flow

1. After each meal check-in → run `increment`, then `next`
2. If `next` returns `action: "schedule"` → create one-shot cron:
   ```bash
   bash {baseDir}/scripts/create-reminder.sh \
     --agent <agent> --channel <channel> --type other --exact \
     --name "Guided feedback: <question-id>" \
     --message "Run notification-composer for guided-feedback <question-id>." \
     --at "<last-meal-time + 60min>"
   ```
   Then run `update --question-id <id> --new-status scheduled`
3. On every activation → run `skip-check`

### Key Rules

- **One chain per day.** Chain 1 (reminder ×3) on Day A, Chain 2 (feedback ×3) on Day A+1, open-review on Day 5+.
- **Chain heads only get cron jobs.** Chain members are sent as immediate follow-ups by `notification-composer`.
- **24h skip timer.** Unanswered → `skipped`, remaining chain members also skipped.
- **Conflict:** if `open-review` collides with a chain, chain wins, review defers.
- **Timing conflict with daily-review:** shift to +90min instead of +60min.

### Acting on Preference Changes

| Changed Field | Action |
|---------------|--------|
| `Reminder Lead Time` | Auto-sync will fix crons on next activation |
| `Reminder Repeat: true` | Create repeat reminder at meal time + 30min |
| `Reminder Content` | No cron change — composer reads at compose time |

---

## Custom User Reminders

Users may ask the AI to set arbitrary recurring or one-shot reminders unrelated
to meals/weight (e.g., "每天给我讲个笑话", "提醒我周五交报告", "每天早上发条励志语录").

### Naming Convention

All custom reminders MUST use the `[custom]` prefix in their job name:
- `[custom] 每日笑话`
- `[custom] 周五交报告提醒`
- `[custom] 早间励志语录`

This distinguishes them from system reminders (meal/weight/weekly-report) and
prevents accidental deletion of system jobs when users say "取消提醒".

### Creating

Use the same `create-cron.py` script with appropriate parameters:

```bash
python3 {baseDir}/scripts/create-cron.py \
  --workspace-dir {workspaceDir} \
  --name "[custom] 每日笑话" \
  --message "给用户讲一个好笑的笑话，风格轻松幽默，每次不同。" \
  --cron "0 9 * * *" \
  --type meal
```

For one-shot reminders:
```bash
python3 {baseDir}/scripts/create-cron.py \
  --workspace-dir {workspaceDir} \
  --name "[custom] 周五交报告提醒" \
  --message "提醒用户今天要交报告。" \
  --at "2026-04-11T09:00:00+08:00" \
  --type meal \
  --delete-after
```

### Canceling

When a user asks to stop a custom reminder (e.g., "别讲笑话了", "取消那个提醒"):

1. `cron list` — find jobs with `[custom]` prefix matching the user's intent.
2. `cron rm` — delete the matched job(s).
3. Confirm: `"好的，已取消「每日笑话」提醒。"`

**Important:** Only delete `[custom]` jobs. Never delete system reminders
(meal/weight/weekly-report) unless the user explicitly asks to stop those
(handled by § Reminder Settings Changes above).

### Listing

When a user asks "我设了哪些提醒" / "有哪些定时任务":

1. `cron list` — filter for `[custom]` prefix jobs.
2. Present as a simple list with name + schedule.
3. Also mention system reminders separately if relevant.

### Ambiguity

If the user says "取消提醒" without specifying which one:
- If only one `[custom]` job exists → cancel it and confirm.
- If multiple `[custom]` jobs exist → list them and ask which to cancel.
- If no `[custom]` jobs exist → assume they mean system reminders, defer to
  § Reminder Settings Changes.

---

## Workspace

### Reads

| Source | Field / Path | Purpose |
|--------|-------------|---------|
| `health-profile.md` | `Meal Schedule` | Reminder schedule + max reminders/day |
| `data/engagement.json` | `last_interaction` | Stage detection |
| `data/guided-feedback.json` | `queue`, `preference_signals` | Guided feedback scheduling |
| `ai-preferences.md` | `Reminder Settings` | Act on user preference changes |
| `data/meals/*.json` | `status` field per meal entry | Derive last interaction date (most recent logged meal) |
| `data/engagement.json` | `stage_changed_at` | Stage transition timing |

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
