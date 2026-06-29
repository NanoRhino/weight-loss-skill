---
name: notification-manager
version: 1.0.0
description: "Cron infrastructure and reminder lifecycle management for the AI weight loss companion. Creates, syncs, and removes meal/weight reminder cron jobs. Manages the engagement lifecycle (Active → Pause → Recall → Silent). Handles adaptive timing, user reminder setting changes, and leave/vacation management. Use this skill when: meal-planner completes onboarding (to bootstrap reminders), user requests reminder setting changes, user wants to pause/resume reminders for a vacation or holiday ('五一不打卡了', '放假暂停提醒', '2号到4号出去玩', 'pause reminders', 'I'm going on vacation'), or another skill needs to verify/fix cron state. Do NOT use for composing reminder content or handling replies — that is notification-composer's job."
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

`--tz` auto-detects from the agent workspace's `USER.md > Timezone`. If no `--tz` is given **and** no timezone can be read, the script **defaults to `America/New_York` (US default) with a logged warning** — this is a US-funnel product, so a US default is usually right and beats leaving the user with no reminders. For correctness, still prefer setting `USER.md > Timezone` or passing `--tz` explicitly.

### Parameters

| Param | Required | Description |
|-------|----------|-------------|
| `--agent` | ✅ | Your agent ID (e.g. `wechat-dm-xxx`, `007-zhuoran`) |
| `--channel` | ❌ | Delivery channel (`wechat`, `wecom`, `slack`, etc.). Defaults to `slack` if omitted (backward-compatible) |
| `--name` | ✅ | Descriptive job name (shown in cron list) |
| `--message` | ✅ | Prompt sent to user when the job fires |
| `--at` | one of | One-shot: relative time or ISO timestamp |
| `--cron` | one of | Recurring: 5-field cron expression |
| `--tz` | ❌ | IANA timezone for cron. Auto-detects from `USER.md > Timezone` if omitted; **falls back to `America/New_York` (US default) with a warning if neither is available** |
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

Timezone auto-detection reads `- **Timezone:**` from the first existing `USER.md` among (in order): `<state>/workspace-nutritionist/$AGENT/`, `<state>/workspace-$AGENT/`, `<project>/.openclaw-user-service/workspaces/$AGENT/`. `<state>` resolves to `$OPENCLAW_STATE_DIR` → `$OPENCLAW_HOME` → `~/.openclaw`. If none yields a timezone and no `--tz` was passed, the script defaults to `America/New_York` (US default) with a warning — never `Asia/Shanghai`.

**Idempotency:** before creating, the script checks the agent's existing jobs for one with the same `--name`; if found it skips (no duplicate). This makes creation safe under retries.

**Imminent-fire guard:** for recurring (`--cron`) jobs, if the next occurrence is within ~45 min of creation, the job is created **disabled** (so it cannot fire during the same session that created it — e.g. mid-onboarding). `batch-create-reminders.sh` (auto-sync) and the deploy migration re-enable such jobs on a later run, by which point the imminent window has passed. Override the window with `REMINDER_IMMINENT_LEAD_SECONDS`.

Then calls `openclaw cron add` with `sessionTarget = "isolated"`, `payload.kind = "agentTurn"`, and `delivery.mode = "announce"` automatically. The isolated agent composes the reminder and outputs the text — announce delivery sends it to the user and automatically injects the context into the main session.

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

### Repairing wrong-timezone / duplicate crons (ops migration)

`scripts/migrate-cron-tz-dups.py` repairs existing agents whose reminders were
created in the wrong timezone (silently defaulted to `Asia/Shanghai`) or were
duplicated by a failed-then-retried batch. Because the failed-batch fallback also
corrupted some cron **expressions** (e.g. afternoon meals stored as `15 2`/`15 6`
instead of `15 14`/`15 18`), a tz-label swap alone is unsafe — so the migration
**removes the agent's recurring system crons and rebuilds them** from
`health-profile.md` via the fixed `batch-create-reminders.sh` (correct local
expression + correct `--tz`). It never touches `[custom]` jobs, one-shot nudges,
or recurring jobs whose names it doesn't own (those are reported only). It is
**dry-run by default** and uses only the gateway CLI (safe with the gateway up).

```bash
# Preview one agent, then apply, then roll out to all:
python3 {baseDir}/scripts/migrate-cron-tz-dups.py --agent 050184
python3 {baseDir}/scripts/migrate-cron-tz-dups.py --agent 050184 --apply
python3 {baseDir}/scripts/migrate-cron-tz-dups.py            # dry-run all
python3 {baseDir}/scripts/migrate-cron-tz-dups.py --apply    # apply all
```

Agents with no `USER.md > Timezone` are skipped (cannot determine the correct
zone — set it first). Run this once after deploying the timezone fix.

---

## Lifecycle resolver (owned here)

`scripts/lifecycle-check.py` is the **single, deterministic, in-workspace**
user-lifecycle resolver — it replaces the never-deployed `127.0.0.1:3100` DB
lifecycle/recall API. "Derive, don't store": stage/days_silent/activated are
computed from signals that already exist (`data/meals/*.json`, `data/weight.json`,
`channel-source.json > lastInboundAt`, `engagement.json > activation.reminders_set_at`).

```bash
# Resolve a workspace's lifecycle (JSON on stdout)
python3 {baseDir}/scripts/lifecycle-check.py --workspace-dir {workspaceDir} --tz-offset {tz_offset}
# → {"state","activated","first_meal_ever","days_silent","stage","last_interaction_date","reminders_set_at"}

# Claim a recall slot (local counter — replaces POST /v1/lifecycle/recall-sent)
python3 {baseDir}/scripts/lifecycle-check.py --workspace-dir {workspaceDir} --mark-recall weekly|monthly
# Clear recall counters on a clean return (optional; stage already auto-resets)
python3 {baseDir}/scripts/lifecycle-check.py --workspace-dir {workspaceDir} --reset-recall
```

Importable: `from importlib import import_module; m = import_module("lifecycle-check")`
then `m.resolve(workspace_dir, tz_offset)` / `m.mark_recall_sent(workspace_dir, tier)`.
`pre-send-check.py`, `holiday-dispatcher.py`, and `s4-central-dispatch.py` all
consume it (import-with-subprocess-fallback). **Recall counters** (the only new
persisted field) live in `engagement.json > recall.{weekly_sent, monthly_sent,
last_recall_at}` — owned by this skill (see § Workspace). Recall ladder is the
**2/4** model. `check-stage.py` was removed; its meal-scan logic is folded in here.

### AGENTS.md activation strip (warm → active)

`scripts/agents-activation-strip.py --workspace-dir {workspaceDir}` removes the
`<!-- activation-only -->` … `<!-- /activation-only -->` fenced block from the
workspace `AGENTS.md` once the user activates, so that always-injected First-Meal
content stops eating the 12,288 B bootstrap budget. It backs up to
`AGENTS.md.pre-activation-strip`, asserts the result is ≤ 12,288 B and that the
load-bearing markers (`System Confidentiality`, `Cron`, `Tools & Formatting`)
survive, restores the backup on any assertion failure, and is idempotent (no
fence → no-op). It is the **first sanctioned skill mutation of `AGENTS.md`** (see
CONVENTIONS.md §12). It runs automatically from `activation-mark-reminders-set.py`
(reminder-first activation) and from the first-meal path
(diet-tracking-analysis, on `is_first_meal_ever`).

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
4. Also verify weight reminder cron jobs exist — see § "Weight reminders" below. This includes the primary (Sat morning) and next-morning followup (Sun morning). Create any that are missing.
5. Also verify the weekly report cron job exists (Sunday 21:00 — see § "Weekly report" below). Create if missing.
6. **Diet pattern detection** — special handling:
   - Read `health-profile.md > Automation > Pattern Detection Completed`
   - If has a date → job already completed. If job still exists, remove it (stale).
   - If `—` (not completed) → check if job exists. If missing → create it.
7. **Disabled system jobs** — a recurring meal/weight/report cron may have been created `enabled=false` by the imminent-fire guard (next run too close to creation time). On sync, re-enable any disabled non-`[custom]` recurring system job (its imminent window has passed). `batch-create-reminders.sh` does this automatically at the end of its run.
8. Do all of this **silently** — do not mention it to the user.

**When creating multiple jobs at once** (initial bootstrap or large sync), use `batch-create-reminders.sh` instead of calling `create-reminder.sh` one by one. It handles slot allocation in a single pass and creates all jobs in parallel:

```bash
bash {baseDir}/scripts/batch-create-reminders.sh \
  --agent <your-agent-id> \
  --channel <channel> \
  --workspace {workspaceDir} \
  --skip-existing
```

Use `--only meal,weight,report,pattern` to restrict which job types are created. The `--skip-existing` flag prevents duplicate creation during partial syncs.

### Default meal times (post-first-meal activation)

The canonical **default meal schedule is `08:30` breakfast / `12:30` lunch / `18:30` dinner (local)**, with each reminder firing at meal **−15 min** (08:15 / 12:15 / 18:15). This constant lives in **exactly one place**: the `DEFAULT_MEAL_SCHEDULE` variable at the top of `scripts/batch-create-reminders.sh` (alongside `DEFAULT_TZ`). Do not hard-code these times anywhere else — reference the script.

`batch-create-reminders.sh` reads meal times from `health-profile.md > Meal Schedule`. **If that section is empty or absent, the script falls back to `DEFAULT_MEAL_SCHEDULE` instead of aborting** (it previously errored out). This is what makes the deterministic post-first-meal → active transition work: right after the user logs their first meal, the activation flow can create the default 3 meal reminders with

```bash
bash {baseDir}/scripts/batch-create-reminders.sh \
  --agent <id> --channel <ch> --workspace {workspaceDir} \
  --only meal --skip-existing
```

even before the user has a confirmed Meal Schedule. Onboarding later confirms/overrides meal times one ask at a time (goal weight → diet prefs → confirm meal times); when the user changes a time, `health-profile.md > Meal Schedule` is updated and auto-sync rewrites the crons (stale jobs removed + recreated). A populated Meal Schedule always wins over the default — the fallback only applies when no times exist yet.

All preserved behavior still applies to the fallback path: anti-burst slot allocation (`--type meal`, [−10, +5] window), timezone from `USER.md > Timezone` (default `America/New_York`, never `Asia/Shanghai`), the imminent-fire guard, and `--skip-existing` idempotency.

---

## Cron Job Definitions

Create recurring cron jobs using the script above. Derive the cron times from `health-profile.md > Meal Schedule` (each meal time minus 15 min). **Prefer `batch-create-reminders.sh`** for bootstrap/sync — it reads the timezone from `USER.md` once and passes `--tz` explicitly to every job (the per-job script's own auto-detect is a fallback only). If you call `create-reminder.sh` directly, prefer setting `USER.md > Timezone` or passing `--tz`; if neither is available it falls back to `America/New_York` (US default) with a warning. **Pass `--channel`** to match the agent's delivery channel (e.g. `wechat`, `slack`). If omitted, defaults to `slack` for backward compatibility.

> ⚠️ **Cron expressions use the user's LOCAL time. Do NOT convert to UTC.** The script sets `--tz` automatically, so the cron scheduler handles timezone conversion. Example: if meal is at 09:00 Beijing time, the cron expression is `45 8 * * *` (08:45 local), NOT `45 0 * * *`.

Every meal cron `--message` MUST tell the agent to run `notification-composer` for that meal. Keep it minimal — notification-composer owns pre-send checks, message composition, and reply handling. Do not duplicate its rules in the cron message.

**Meal naming:** Always use standard meal names (`breakfast`, `lunch`, `dinner`) — never `meal_1`/`meal_2`. For 2-meal users, use whichever two standard names match their schedule (e.g., user eats at 12:00 and 18:30 → `lunch` and `dinner`).

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

# Example: 2 meals (lunch + dinner)
bash {baseDir}/scripts/create-reminder.sh \
  --agent <your-agent-id> --channel <channel> --type meal --name "Lunch reminder" \
  --message "Run notification-composer for lunch." \
  --cron "45 11 * * *"

bash {baseDir}/scripts/create-reminder.sh \
  --agent <your-agent-id> --channel <channel> --type meal --name "Dinner reminder" \
  --message "Run notification-composer for dinner." \
  --cron "15 18 * * *"
```

### Weight reminders (weekly + followup)

> **Cadence is weekly by default — one weigh-in per week, not 2×.** Over-frequent scale checks surface day-to-day water-weight noise and demoralize the engaged users a results-based product most wants to keep (an engaged 7-day-streak user told us "weighing 2 times a week… very depressing and not really necessary"). The Sunday followup is a conditional catch-up that only fires if Saturday was missed — it is NOT a second expected weigh-in. If a user explicitly wants more frequent weigh-ins, add days on request; never default above weekly.

> ⚠️ **Breakfast fallback:** If user has no breakfast (BREAKFAST_TIME is empty/null), use the **earliest meal time** from `health-profile.md > Meal Schedule` as the reference for all "breakfast time − 30 min" calculations below. For example, if user only eats lunch (12:00) and dinner (18:00), weight primary reminder = 11:30, morning followup = 11:30. The condition for creating weight reminders is that **at least one meal time exists** — not specifically breakfast.

**Primary reminder:** Cron time = breakfast time (or earliest meal) minus **30 min**. Fires Sat.

```bash
# Example assumes breakfast at 07:00 → weight cron at 06:30
bash {baseDir}/scripts/create-reminder.sh \
  --agent <your-agent-id> --channel <channel> --type weight --name "Weight check-in reminder" \
  --message "Run notification-composer for weight." \
  --cron "30 6 * * 6"
```

**Next-morning followup:** Cron time = breakfast time (or earliest meal) minus **30 min**. Fires Sun (day after primary). Only sends if the user did NOT weigh in yesterday OR today. Pre-send-check uses `weight_morning_followup` type.

```bash
# Example assumes breakfast at 07:00 → morning followup at 06:30
bash {baseDir}/scripts/create-reminder.sh \
  --agent <your-agent-id> --channel <channel> --type weight --name "Weight morning followup" \
  --message "Run notification-composer for weight_morning_followup." \
  --cron "30 6 * * 0"
```

### Weekly report (Sunday 9 PM)

One fixed cron job — every Sunday at 21:00 user local time.

```bash
bash {baseDir}/scripts/create-reminder.sh \
  --agent <your-agent-id> --channel <channel> --name "Weekly report" \
  --message "🚨 WEEKLY REPORT — MANDATORY SCRIPT EXECUTION\n\nGenerate this week's weekly report using the weekly-report skill.\n\nABSOLUTE RULES:\n1. Run collect-weekly-data.py to gather all nutrition/weight/exercise data\n2. Run generate-report-html.py with real commentary/highlights/suggestions — capture the URL from stdout\n3. The final message to user MUST contain the clickable report URL\n4. If any script fails, report the error — do NOT fall back to a text-only summary\n5. A delivery without a report URL = FAILED execution\n\n❌ FORBIDDEN: Writing a text summary without running the scripts\n❌ FORBIDDEN: Sending a message without a report link (https://nanorhino.ai/user/...)\n✅ REQUIRED: The message MUST contain the actual uploaded report URL\n\nSkill: weekly-report\nUser workspace: {workspaceDir}" \
  --cron "0 21 * * 0"
```

### Periodic recalc (every 4 weeks Sunday, after weekly report)

Every 4 weeks, recalculates the user's daily calorie target based on current weight and reviews diet mode fit. Fires after the weekly report (Sunday 21:30).

```bash
bash {baseDir}/scripts/create-reminder.sh \
  --agent <your-agent-id> --channel <channel> --name "Periodic recalc (4-week)" \
  --message "Run periodic-recalc skill: python3 {skillsDir}/periodic-recalc/scripts/periodic-recalc.py --workspace {workspaceDir} --planner-calc {skillsDir}/weight-loss-planner/scripts/planner-calc.py. Then run diet-mode-review.py if recalculated." \
  --cron "30 21 * * 0" \
  --exact
```

**Scheduling note:** Use `--exact` to ensure it fires at 21:30 (after weekly report at 21:00). The `0 */4` week cycle is NOT achievable in standard cron — instead, the script itself tracks the last recalc date in `pending-recalc.json` or `PLAN.md > Updated` field and skips execution if less than 25 days since last recalc.

**Created at onboarding** (alongside meal/weight/weekly-report reminders).

---

### Diet pattern detection (self-destructing, onboarding + 3 days)

One-time diet pattern analysis. Created at onboarding, starts running 3 days after `Onboarding Completed` date (from `health-profile.md > Automation`). Cron time = dinner + 3h.

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

### First-meal nudge (one-shot, activation flow)

**Purpose:** Break the ice for users who completed onboarding (picked a plan,
set meal reminders) but have **never logged a single meal**. The stall point is
"now actually text me your food." This is a gentle, capped nudge — NOT a recall.

**Created at onboarding completion** by `batch-create-reminders.sh` (included in
the default `--only all` bootstrap; restrict with `--only firstmeal`). It
creates **two one-shot** (`--at`) jobs:

| Job name | Fires | Payload |
|----------|-------|---------|
| `First meal nudge` | ~3-4h after completion, at the next meal slot today (daytime-capped 08:00-20:00 local) — else first meal slot next day | `... pre-send-check.py --meal-type first_meal_nudge ...` then `notification-composer for first_meal_nudge (nudge=1)` |
| `First meal nudge followup` | First meal slot the following day (softer) | same, `nudge=2` |

**Timing uses the user's IANA timezone** (from `USER.md > Timezone`). The nudge
fires **at** the meal slot, deliberately offset from the meal-reminder minutes
(which fire at slot−15min), so the user never gets the nudge and a meal reminder
minutes apart.

**Detection (who gets it):** `health-profile.md` has a real
`Onboarding Completed` date AND `data/meals/` has zero food entries AND
`## Meal Schedule` is populated (so meal crons exist). The one-shot crons are
created unconditionally at onboarding; the actual send is gated at fire time by
`pre-send-check.py --meal-type first_meal_nudge`, which self-cancels if
onboarding is NOT completed (wrong cohort — keeps it mutually exclusive with the
activation nudge), the user logged any meal, is on leave, or the cap is reached.

**Cap & terminal state:** Max **2** nudges (`activation.first_meal_nudges_sent`,
a non-stage business counter in `data/engagement.json`). The moment the user logs
ANY meal, both nudges self-cancel (pre-send-check). After 2 nudges, the
pre-send-check **cap gate** (reads `activation.first_meal_nudges_sent >= 2`)
permanently suppresses the nudge — this is the terminal anti-nag guarantee and is
**lifecycle-independent** (it does not depend on the stage system). The intent is
that a never-logged user never receives the engaged-recall content (S2-S4), which
is generated from logged meals and would be hollow.

> **Stage authority (post-3100-decommission):** `notification_stage` /
> `stage_changed_at` are NOT stored in `engagement.json` — stage is **derived
> locally** by `lifecycle-check.py` (days_silent + `recall.*` counters). The cap
> gate is what enforces the "stop after 2" guarantee; it does not rely on writing
> a Silent stage. `check-stage.py` has been **removed** (its meal-scan logic was
> folded into `lifecycle-check.py`). The activation flow does not depend on any
> stage field. See the cross-system flag in § Activation nudge below.

---

### Activation nudge (greeted but never replied)

**Purpose:** Break the ice for users who came in via TDEE handoff, got the
welcome message, but have **never replied at all**. Different cohort from the
first-meal nudge (who replied + onboarded but never logged).

**Cron created by openclaw-infra, NOT this repo.** **Cold-Start v3** changed the
schedule from payload-tagged one-shot crons to **ONE recurring "sweep"
cron** (fires ~every 2h) created by the infra side at handoff/registration. The
sweep payload is **generic** — it just says "run the activation pre-send check
and send the single due touch if the gate allows" and **no longer carries which
touch to send**. This skill only implements what the sweep fires into.

> **Cold = behavioral, not plan-less.** "Cold" = no meal/weight check-in AND zero
> inbound SMS (the :8899 dashboard's `classifyEngagement` definition) — it has
> nothing to do with whether the user has a plan. ~86% of this cohort came via
> TDEE handoff and HAVE a full PLAN.md ("got their plan, went silent"); only ~14%
> are truly plan-less. This activation gate already == the no-inbound cohort, so
> it already serves the cold population; the composer's WARM/COLD split (PLAN.md
> present?) handles the plan-less minority. No separate "cold" system or counter.

> **Sequence shortened 4 → 2 (Track A, 2026-06-24).** WARM recall analysis: touches
> 3 and 4 (T+3d, T+7d) produced ZERO recall — every re-engagement came from touch
> 1 or 2, and the 3 users who hit the full 4-touch cap never replied. Cold users
> have even lower intent, so touches 3-4 were pure opt-out/annoyance risk. Only
> T+4h and T+24h remain; cap=2.

**Who computes the touch:** the gate (`pre-send-check.py --meal-type activation`),
not the payload. It computes `index = nudges_sent + 1` (1–2) and green-lights
touch `index` only when BOTH `now - claimedAt >= threshold[index]` (touch1=4h,
touch2=24h — the agreed contract; T+3d/T+7d dropped) AND
`now - last_nudge_at >= ~20h` (MIN_GAP, so a catch-up sweep doesn't bunch
touches). On SEND it prints `SEND activation nudgeIndex=N nudgeAngle=X` and the
composer renders content by that `nudgeIndex` (source of truth), NOT by the
`nudges_sent` counter and NOT from the payload. Generic sweep payload:

```
First run: python3 {notification-composer:baseDir}/scripts/pre-send-check.py \
  --workspace-dir <WS> --meal-type activation --tz-offset <off>.
If output is NO_REPLY, stop and output NO_REPLY.
Otherwise run notification-composer for activation (it reads nudgeIndex/nudgeAngle
from the pre-send-check output line).
```

> The old `(nudgeIndex=N, nudgeAngle=X)` / `(nudge=N)` payload tokens are
> **removed** — the composer no longer parses them from the cron message.

**Detection / defining gate** (`pre-send-check.py --meal-type activation`): the
target user is a handoff case — `health-profile.md` exists with
`Onboarding Completed: —` (NOT a date) and `channel-source.json > handoffAppliedAt`
set. The **defining cancel signal** is `channel-source.json > lastInboundAt`
(epoch ms, written by infra Phase-0 on every inbound): **if present at all, the
user has replied → NO_REPLY (cancel)**. Also NO_REPLY if `channel-source.json`
is missing/unreadable (**fail closed** — the target cohort always has the file;
if we can't confirm no-reply we stay silent), `channel-source.json > claimedAt`
(ISO-8601, the registration anchor for the schedule) is missing/unparseable
(**fail closed** — can't time the touch), **user is a minor** (structured age
< 18 from `handoff.json > structured.age_years`, fallback `PROFILE.md > **Age:**`;
fails open when no structured age — defense-in-depth behind the TDEE upstream
refusal), onboarding completed, any meal logged, the authoritative
Silent stage (handled by the generic `check_engagement_stage` gate via the
local `lifecycle-check.py` resolver), on leave/pause, the `ACTIVATION_ENABLED` kill switch is off
(env set to 0/false → every activation touch returns NO_REPLY),
`activation.nudges_sent >= 2`, the computed touch's threshold not yet reached, or
the MIN_GAP holding it back.

**Kill switch:** `ACTIVATION_ENABLED` (env var read by `pre-send-check.py`,
default ON). Set `ACTIVATION_ENABLED=0` in the gateway/cron environment and
restart the gateway to hot-disable the entire activation sequence without a skill
redeploy. Scoped to activation only — meal/weight reminders, recall, and the
first-meal nudge are unaffected.

**Cold-START users also enter this flow.** "Cold" is behavioral (no inbound, no
check-in), NOT plan-less — most of the cohort HAS a PLAN.md. Previously cold-start
(no PLAN.md) users were never scheduled; under v3 the sweep covers them too. The
composer uses the COLD content variant (no `target_cal`/`target_protein`, no "your
plan is ready" language) for the plan-less minority when `PLAN.md` is absent, and
the production-validated "your plan's still saved, want to give it a shot" copy
for the WARM majority — see `notification-composer` SKILL.md § 激活提醒 and
`references/recall-messages.md`.

**Cap & terminal state:** Max **2** nudges (`activation.nudges_sent`). The moment
the user replies (or logs a meal), all remaining nudges self-cancel. After 2
nudges, the pre-send-check **cap gate** (reads `activation.nudges_sent >= 2`)
permanently suppresses the nudge — lifecycle-independent terminal guarantee, same
as the first-meal nudge. The composer increments the counter via
`activation-mark-sent.py --counter nudges_sent` after each successful send;
that script, in the SAME flock + atomic os.replace, also stamps
`activation.last_nudge_at` (ISO-8601 UTC) — the single source of truth the gate's
MIN_GAP reads. **The composer must NOT hand-edit engagement.json (or write
recall_topics, or write `last_nudge_at`) in the activation path** — both the
counter and `last_nudge_at` are owned exclusively by the script (flock + atomic
os.replace, written together); a freehand Edit races it and mis-flags successful
nudge runs as `error` (the 050208 incident).

> ⚠️ **Cross-system flag (lifecycle interaction):** The cap gate stops the
> *nudges*, but it does NOT itself move the user to Silent — stage is **derived**
> by `lifecycle-check.py` from days_silent + recall counters. For a never-engaged
> user (no meals, no inbound) there is no recent interaction, so days_silent has
> nothing to anchor to and `lifecycle-check.py` reports stage 1 with days_silent 0
> (cold/warm state, not the recall ladder). The recall ladder only engages once a
> user has interacted at least once and then gone quiet. The weight-loss-skill
> guarantee here is narrowly: **these two nudge types stop firing after 2 sends**
> (cap gate, lifecycle-independent). Recall content (S2–S4) never fires for a
> never-engaged user precisely because there is no last-interaction date to start
> the silence clock.

---

### Reminder-first activation (no meal to log yet)

**Purpose:** Give the handoff First-Meal Mode user a constructive branch when they
have **nothing to log right now** ("I haven't eaten yet"). Instead of nagging for
a meal or going quiet, the coach pivots ONCE (Single-Ask — no nagging) to offering
the 3 meal reminders, which then become the engine that prompts the first real log.

**Flow** (driven by the AGENTS-handoff First-Meal Mode template; this skill owns
the reminder + signal mechanics):
1. The coach writes the user's meal times to `health-profile.md > Meal Schedule`
   (user's times if given; else `DEFAULT_MEAL_SCHEDULE` 08:30/12:30/18:30 — do NOT
   hard-code times, reference `batch-create-reminders.sh`).
2. Creates the 3 meal reminders:
   ```bash
   bash {baseDir}/scripts/batch-create-reminders.sh \
     --agent <your-agent-id> --channel twilio --workspace {workspaceDir} \
     --only meal --skip-existing
   ```
3. Stamps the activation signal (idempotent, set-once):
   ```bash
   python3 {baseDir}/scripts/activation-mark-reminders-set.py \
     --workspace-dir {workspaceDir}
   ```
   This sets `data/engagement.json > activation.reminders_set_at` (ISO-8601 UTC) the
   first time only; later calls are no-ops (returns `already_set: true`). The
   openclaw-infra dashboard + activation funnel read this field to count the user as
   activated rather than a dead lead. **On the first stamp it also runs
   `agents-activation-strip.py` automatically** (warm → active housekeeping): the
   `<!-- activation-only -->` block in the handoff `AGENTS.md` is shed (backup +
   12,288 B cap assert + load-bearing marker assert, idempotent, restore-on-failure).
   Best-effort — a strip failure never blocks the activation stamp.

**This counts as activation.** It does **NOT** call `mark-onboarding-done.py` —
reminder-setup ≠ full onboarding complete (consistent with the post-first-meal
path, which also doesn't mark done). Meal logging stays **never-gated**, and the
user's first real meal still triggers the First-Meal Celebration + Starter Badge.
Progressive onboarding (goal weight → diet prefs → confirm meal times) resumes
one-ask-per-touchpoint on later turns. See `SKILL-ROUTING.md` Pattern 6 (First-Meal
Mode note).

---

## Lifecycle: Active → Recall → Silent

**Resolved locally + deterministically** by `scripts/lifecycle-check.py` (the
`127.0.0.1:3100` DB API was never deployed — every caller failed open to Stage 1,
so recall was a prod no-op until this resolver replaced it). Recall ladder is the
**2/4** model (NEW — was 3/6):

```
Stage 1: ACTIVE — normal reminders        (days_silent < 2)
    │
    └── days_silent >= 2
           │
Stage 2: RECALL — stop meal/weight reminders, lunch-only recall  (2 <= days_silent < 4)
    │       At most one recall per day (same-day dedup via recall.last_recall_at)
    │
    ├── User sends any message / logs a meal / weighs in → back to Stage 1
    └── days_silent >= 4
           │
Stage 3: WEEKLY RECALL — 1x/week (>= 7d since last recall), rotate content types
    │       Also stops weekly report
    │
    ├── User returns → back to Stage 1
    └── 3 weekly recalls sent (recall.weekly_sent >= 3) → disable personal crons
           │
Stage 4: MONTHLY RECALL — 1x/month (>= 30d), central dispatch (not personal crons)
    │
    ├── User returns → back to Stage 1, re-enable personal crons
    └── 3 monthly recalls sent (recall.monthly_sent >= 3) → Stage 5
           │
Stage 5: SILENT — send nothing. Wait for user to return.
```

**Stage source:** `scripts/lifecycle-check.py` — import
`resolve(workspace_dir, tz_offset)` or run
`python3 {baseDir}/scripts/lifecycle-check.py --workspace-dir {workspaceDir} [--tz-offset N]`.
It returns `{state, activated, first_meal_ever, days_silent, stage,
last_interaction_date, reminders_set_at}`. `days_silent` is whole days since the
most recent of {last food-meal, last weight, last inbound (`channel-source.json >
lastInboundAt`)}. A new meal/weight/inbound auto-resets to Stage 1 (days_silent
drops below 2). `pre-send-check.py` calls this resolver, not any HTTP endpoint.

**Recall claim:** when `pre-send-check.py` green-lights a recall, it claims the
slot by bumping the **local** counter (`recall.weekly_sent` for S2/S3,
`recall.monthly_sent` for S4) and stamping `recall.last_recall_at` via
`lifecycle-check.py mark_recall_sent()` — replaces the old
`POST /v1/lifecycle/recall-sent` event. Same-day / 7-day / 30-day cadence dedup is
computed from `recall.last_recall_at`.

**Activation nudges (special case — never-engaged users):** Two cohorts get a
capped one-shot nudge instead of (or before) the recall content above:
1. **Never logged** — completed onboarding but logged zero meals (first-meal
   nudge, `activation.first_meal_nudges_sent`).
2. **Never replied** — handoff user who never sent any message (activation
   nudge, `activation.nudges_sent`; cron created by openclaw-infra).

Each nudge fires at most **2 times**, then the pre-send-check cap gate
permanently suppresses it (lifecycle-independent). The intent is to avoid feeding
these users the engaged-recall content (S2-S4), which is generated from logged
meals / conversation and would be hollow. The moment they log a meal or reply,
they rejoin the normal lifecycle. **Note:** the actual stage is owned by the
lifecycle DB (post-migration); the cap gate only guarantees the *nudges* stop —
moving a never-engaged user to lifecycle Silent is a lifecycle-side concern. See
§ First-meal nudge and § Activation nudge (incl. the cross-system flag).

### S4 Central Dispatch

Stage 4 users no longer consume personal cron resources. Instead:

1. A single central cron runs daily at lunch, executing `s4-central-dispatch.py`
2. The script **scans all workspaces and resolves each one locally** via
   `lifecycle-check.py`, emitting users who are Stage 4 AND monthly-due (>= 30
   days since `recall.last_recall_at`). No HTTP — the old `GET /due` API was never
   deployed.
3. For each matched user, the main agent:
   a. Reads user data from their workspace (meals, preferences, etc.)
   b. Generates a recall message following `recall-messages.md` S4 rules
   c. Sends via `message` tool with the `channel` and `target` from script output
   d. Calls `s4-central-dispatch.py --mark-sent <workspace_dir>`, which bumps the
      **local** `recall.monthly_sent` counter (+ `recall.last_recall_at`)

**Central dispatch usage:**
```bash
# Scan workspaces for S4 users due for monthly recall today
python3 {notification-manager:baseDir}/scripts/s4-central-dispatch.py \
  --openclaw-dir /home/admin/.openclaw --tz-offset 28800

# After sending message to a user, record the recall (prefer the workspace dir)
python3 {notification-manager:baseDir}/scripts/s4-central-dispatch.py \
  --openclaw-dir /home/admin/.openclaw --mark-sent <workspace_dir|account_id>
```

**Suppression rules:**
- Stage 2+: stop weight reminders + meal reminders (only recall messages at lunch)
- Stage 3+: also stop weekly report
- Stage 5: stop everything

Recall replaces the lunch reminder slot — don't send at random hours.

**Stage transition logic:** Stage is derived in real time by
`lifecycle-check.py` from the user's last **interaction** (most recent of last
food-meal date / last weight date / last inbound date from `channel-source.json >
lastInboundAt`) and the **local** recall counters: `days_silent < 2` → S1, `2–3` →
S2, `>= 4` → S3, then `recall.weekly_sent >= 3` → S4, `recall.monthly_sent >= 3` →
S5. A returning user (any new meal/weight/inbound) drops days_silent below 2 →
auto-resets to S1; `lifecycle-check.py reset_recall()` clears the weekly/monthly
counters so a future silent spell starts fresh. `pre-send-check.py` calls the
resolver (no HTTP) to decide whether to send a normal reminder, a recall, or
nothing — the agent no longer runs any stage-update script before reminders.

During recall stages, `pre-send-check.py` claims the day's recall slot by bumping
`recall.weekly_sent` / `recall.monthly_sent` (+ `recall.last_recall_at`) when it
green-lights a send; same-day / 7-day / 30-day dedup is computed from
`recall.last_recall_at`.

**When a silent user returns:**
Stage auto-resets to 1 the moment a fresh meal/weight/inbound lands (days_silent
drops below 2). Resume normal reminders. The warm welcome itself is composed by
`notification-composer` (triggered by SKILL-ROUTING's Welcome Back Check).

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

Use the same `create-cron.py` script with appropriate parameters.

> **⚠️ RECALL SUPPRESSION:** All custom reminders are automatically suppressed when
> the user is in recall stage (engagement_stage ≥ 2). The agent payload MUST include
> a pre-send-check call with `--meal-type custom` at the start. This is handled
> automatically by the payload template below.

Payload template for custom reminders:
```
First run: python3 {notification-composer:baseDir}/scripts/pre-send-check.py --workspace-dir {workspaceDir} --meal-type custom --tz-offset {tz_offset}
If output is NO_REPLY, stop and output NO_REPLY.
Otherwise: <the actual reminder message/task>
```

```bash
python3 {baseDir}/scripts/create-cron.py \
  --workspace-dir {workspaceDir} \
  --name "[custom] 每日笑话" \
  --message "First run: python3 {notification-composer:baseDir}/scripts/pre-send-check.py --workspace-dir {workspaceDir} --meal-type custom --tz-offset {tz_offset}\nIf output is NO_REPLY, stop and output NO_REPLY.\nOtherwise: 给用户讲一个好笑的笑话，风格轻松幽默，每次不同。" \
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
| `data/meals/*.json` | food meals (non-empty `items`/`foods`) | `lifecycle-check.py` last-interaction date + food-meal count |
| `data/weight.json` | weight check-ins | `lifecycle-check.py` last-interaction date |
| `channel-source.json` | `lastInboundAt` | `lifecycle-check.py` last-inbound date (cold/warm + days_silent) |
| `data/engagement.json` | `activation.reminders_set_at`, `recall.*` | `lifecycle-check.py` activation + recall ladder |

### Writes

| Path | How | When |
|------|-----|------|
| (stage) | derived locally by `lifecycle-check.py` | Stage is NOT persisted — computed on demand from signals above |
| `data/engagement.json` | `recall.{weekly_sent,monthly_sent,last_recall_at}` — written by `lifecycle-check.py mark_recall_sent()` (atomic flock) | When `pre-send-check.py` / `s4-central-dispatch.py` claims a recall slot |
| `AGENTS.md` | activation-only block removed by `agents-activation-strip.py` (backup + cap/marker assert) | On warm → active (reminder-first activation or first meal) — see § Reminder-first activation |
| `data/engagement.json` | `reminder_config` — direct write | Adaptive timing changes, user setting changes |
| `data/engagement.json` | `activation.first_meal_nudges_sent` — incremented by `notification-composer` via `activation-mark-sent.py` | After each first-meal nudge send |
| `data/engagement.json` | `activation.nudges_sent` — incremented by `notification-composer` via `activation-mark-sent.py` | After each activation (never-replied) nudge send |
| `data/engagement.json` | `activation.last_nudge_at` (ISO-8601 UTC) — stamped by `activation-mark-sent.py` in the SAME atomic write as the increment | After each activation/first-meal nudge send; read by `pre-send-check.py` for the ~20h MIN_GAP |
| `data/engagement.json` | `activation.reminders_set_at` (ISO-8601 UTC) — stamped once by `activation-mark-reminders-set.py` (set-once, never overwritten) | When the reminder-first activation flow creates meal reminders for a not-yet-logged user (see § Reminder-first activation). Read by the openclaw-infra dashboard + activation funnel |
| `health-profile.md > Meal Schedule` | direct write | Adaptive timing updates, user-requested time changes |
| `data/engagement.json` | `dashboard_tip.*` sub-object — written by **`dashboard-link`**'s `dashboard-tip-gate.py` (read-modify-write, preserves all other keys) | Proactive data-center tip show-policy gate. This file is owned here, but the `dashboard_tip` sub-key is owned by `dashboard-link` — a sanctioned narrow cross-write (see `dashboard-link/SKILL.md` § Proactive Dashboard Tip). Do NOT read/write `dashboard_tip` from this skill. |

---

## Leave / Vacation Management

用户要求暂停打卡（假期、出游、不方便记录等）时，调用 leave-manager 设置请假。

**触发场景：**
1. 用户主动说要请假/暂停/放假不打卡
2. 用户在对话中表达最近很忙、无法打卡、顾不上记录
3. S2 Day 5 询问暂停后用户确认暂停

**处理流程：**
1. 表达理解，主动提出暂停提醒
2. 询问暂停多久（"大概要忙多久呀？"）
3. 用户给了时间 → set leave 对应日期
4. 用户没给时间 → 不设leave，让 `lifecycle-check.py` 按 days_silent 自然推进到 S3（4 天后进入每周召回）
5. 暂停期间所有主动消息停止
6. 给了时间的：到期自动恢复 / 用户提前回来 → clear leave
7. 没给时间的：按S3→S4→S5正常流转，用户随时回来重置到S1

### Set leave
```bash
python3 {notification-composer:baseDir}/scripts/leave-manager.py set \
  --data-dir {workspaceDir}/data --tz-offset {tz_offset} \
  --start YYYY-MM-DD --end YYYY-MM-DD --reason "五一出游"
```

### Clear leave（用户提前回来）
```bash
python3 {notification-composer:baseDir}/scripts/leave-manager.py clear \
  --data-dir {workspaceDir}/data --tz-offset {tz_offset}
```

### Check leave status
```bash
python3 {notification-composer:baseDir}/scripts/leave-manager.py info \
  --data-dir {workspaceDir}/data --tz-offset {tz_offset}
```

**规则：**
- 请假期间所有 cron 提醒自动静默（pre-send-check 处理，无需改 cron）
- 用户主动发消息不受影响，正常记录
- 过期自动清理

---

## Tips 管理

用户说"别发了"/"不要再发小贴士"/"关掉tips"时：

```bash
python3 {notification-composer:baseDir}/scripts/tips-optout.py \
  --data-dir {workspaceDir}/data
```

---

## Skill Routing

**See `SKILL-ROUTING.md` for the full conflict resolution system.** This skill
is **Priority Tier P4 (Reporting)**. It handles the orchestration side of
reminders — cron management, lifecycle, and settings. The execution side
(composing messages, handling replies) is handled by `notification-composer`.
