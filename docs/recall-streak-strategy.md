# Reminder Strategy: Recall + Streak

This document describes the full recall and streak strategy implemented
in this branch, including what each component does, how they connect,
and what needs to be reflected in `notification-composer/SKILL.md` to
actually trigger at runtime.

---

## 1. Recall Strategy — Silence Response Lifecycle

### Overview

When a user stops logging meals, the system progressively responds:
first with gentle nudges inside normal reminders, then with emotionally
rich recall messages, and finally with silence. The goal is to make the
user feel missed (not guilty) and give them a natural re-entry point.

### Timeline

The recall ladder is the **2/4** model — stages are keyed on `days_silent` and
the local recall counters, not on a fixed calendar.

| days_silent | Stage | Behavior | What the user receives |
|-------------|-------|----------|----------------------|
| 0–1 | Stage 1 (ACTIVE) | Normal reminders | Regular meal/weight reminders |
| 2–3 | Stage 2 (RECALL) | Recall (lunch slot) | One emotional message, no recommendations. ≤1/day; other meal + all weight crons suppressed. |
| ≥4 | Stage 3 (WEEKLY) | Weekly recall | One quiet recall, ≤1 per 7 days. Weekly report also stopped. |
| ≥4, after 3 weekly recalls | Stage 4 (MONTHLY) | Monthly recall | One recall, ≤1 per 30 days. Central dispatch (not personal crons). |
| ≥4, after 3 monthly recalls | Stage 5 (SILENT) | Silent | No messages at all. |
| Return (any meal/weight/inbound) | → Stage 1 | Excitement | "YOU'RE BACK!!" + ask what they've been eating. Resume reminders. |

### Silence detection

Silence is **derived deterministically and locally** from in-workspace signals —
there is no lifecycle DB (the `127.0.0.1:3100` API was never deployed). The
resolver is `notification-manager/scripts/lifecycle-check.py` (importable
`resolve(workspace_dir, tz_offset)` or `python3 lifecycle-check.py
--workspace-dir <ws>`):

- Scans `data/meals/*.json` for the most recent date with a food meal
  (non-empty `items`/`foods`), `data/weight.json` for the most recent weigh-in,
  and `channel-source.json > lastInboundAt` for the most recent inbound.
- `days_silent` = calendar days (user's timezone) since the **most recent** of
  those three. No dependency on any external platform writing `last_interaction`.

### Stage transitions

Computed in one pass by `lifecycle-check.py` from `days_silent` + the local
recall counters (`recall.weekly_sent` / `recall.monthly_sent`):

| Transition | Condition |
|-----------|-----------|
| Stage 1 → 2 | `days_silent >= 2` |
| Stage 2 → 3 | `days_silent >= 4` |
| Stage 3 → 4 | `recall.weekly_sent >= 3` (3 weekly recalls sent) |
| Stage 4 → 5 | `recall.monthly_sent >= 3` (3 monthly recalls sent) |
| Any → Stage 1 | New meal/weight/inbound → `days_silent < 2` (auto-reset) |

### Daily Recall (Stage 2, days_silent 2–3)

Pure emotional messages. No meal recommendations. 2-3 sentences.

- One message per day (lunch slot only). Other meal crons + all weight crons →
  suppressed (`NO_REPLY`). Same-day dedup is computed from `recall.last_recall_at`.
- Nutritionist identity: express missing through food ("I had a recipe
  for you and you weren't here").
- Weekend/holiday: "you went out to eat good food without me".
- On send, `pre-send-check.py` claims the slot by bumping `recall.weekly_sent`
  and stamping `recall.last_recall_at` (via `lifecycle-check.py mark_recall_sent`).

### Weekly Recall (Stage 3, days_silent ≥4)

One message per week (lunch slot), `≥ 7` days since `recall.last_recall_at`.

- Quiet, tender, rotate content type. Weekly report is also suppressed.
- On send, bump `recall.weekly_sent` (+ `recall.last_recall_at`). After 3 weekly
  recalls → Stage 4 (Monthly).

### Monthly Recall (Stage 4) → Silent (Stage 5)

One message per month (`≥ 30` days since `recall.last_recall_at`), via central
dispatch (`s4-central-dispatch.py`), not personal crons.

- On send, bump `recall.monthly_sent` (+ `recall.last_recall_at`). After 3
  monthly recalls → Stage 5 (Silent): no messages at all.

### User Return

- Any new meal/weight/inbound drops `days_silent` below 2, so `lifecycle-check.py`
  auto-resets to Stage 1 (no script run needed — the resolver recomputes on every
  call). `lifecycle-check.py reset_recall()` clears the weekly/monthly counters so
  a future silent spell starts the ladder fresh.
- Pure excitement. Ask what they've been eating.
- Never mention the gap, never reference missed days.
- Naturally ask if they want reminders back.

---

## 2. Streak Strategy — Daily Streak Opening Line

### Overview

Every meal reminder (Stage 1) includes an opening line about the user's
consecutive logging streak. This strengthens the emotional bond — the
nutritionist is counting alongside the user and getting to know them
through their eating habits.

### How it works

- `streak-calc.py info` scans `data/meals/*.json` to calculate the
  current consecutive streak (days with at least one `status: "logged"`).
- A "logged day" = at least one meal with `status: "logged"`.
- The streak must end at today or yesterday (allows "today's first meal
  hasn't been logged yet").

### Opening line logic

| Condition | Opening line |
|-----------|-------------|
| `pending_milestone` not null | **Milestone celebration** — bigger energy, 1-2 sentences. After sending, call `streak-calc.py celebrate --milestone <n>`. |
| `current_streak >= 2` | **Daily streak line** — "{current_streak - 1} days + free half about getting to know the user". One sentence. Vary daily. |
| `current_streak < 2` | Normal opening (no streak mention). |

Uses `current_streak - 1` because today's meal hasn't been logged yet
when the reminder fires.

### Milestones

`[3, 7, 14, 21, 30, 60, 90]` — each celebrated once per streak.
On milestone days, the daily line is replaced with a bigger celebration.

### Break handling

- When streak breaks: say nothing. `milestones_celebrated` resets
  automatically. New streak starts silently.
- Never compare to previous streak. Never mention the break.
- `longest_streak` is preserved across resets in `data/streak.json`.

### Data persistence

`streak-calc.py info` persists to `data/streak.json` on every run:

```json
{
  "current_streak": 7,
  "longest_streak": 14,
  "streak_start_date": "2026-03-26",
  "last_logged_date": "2026-04-01",
  "milestones_celebrated": [3, 7]
}
```

Other skills can read this directly without running the script.

---

## 3. Weight Reply Routing

When the user reports a weight number:

| Condition | Action |
|-----------|--------|
| Trend down | `logged ✓ Trending nicely.` |
| Trend up or distress | Log the number, route to `weight-gain-strategy` (runs deviation-check, handles emotional response if needed). |
| Declines | `👍` |

`weight-gain-strategy` owns both the analytical response (deviation-check)
and emotional handling. `notification-composer` does not route weight
distress directly to `emotional-support`.

---

## 4. Implementation — Files and Ownership

### Scripts (all working, tested)

| File | Owner | What it does |
|------|-------|-------------|
| `notification-manager/scripts/lifecycle-check.py` | notification-manager | The deterministic resolver: derives `state`/`activated`/`days_silent`/`stage` from meals + weight + inbound (no DB, no writes); `mark_recall_sent()` bumps the local recall counters. `resolve()` + CLI. |
| `notification-manager/scripts/agents-activation-strip.py` | notification-manager | On warm → active, strips the `<!-- activation-only -->` block from the workspace `AGENTS.md` (backup + 12,288 B cap + marker asserts, idempotent) |
| `notification-composer/scripts/pre-send-check.py` | notification-composer | Gates sending via `lifecycle-check.py`: Stage 2 ≤1/day + weight suppressed; Stage 3 ≤1/7d; Stage 4 ≤1/30d; Stage 5 block all. Claims recall slots by bumping the local counters. |
| `streak-tracker/scripts/streak-calc.py` | streak-tracker | Calculates streak from meals, persists to `streak.json`, tracks milestones |

### Reference files (all present)

| File | Content |
|------|---------|
| `notification-composer/references/recall-messages.md` | Nudge + Day 4/5/6 recall + final recall + return examples |
| `notification-composer/references/meal-composition.md` | Meal recommendation composition rules |
| `notification-composer/references/data-schemas.md` | engagement.json + streak.json field definitions |
| `streak-tracker/references/streak-milestones.md` | Milestone tiers, celebration rules, daily/milestone examples |

### SKILL.md documents

| File | Content |
|------|---------|
| `notification-manager/SKILL.md` | Lifecycle diagram (2/4 ladder), stage thresholds, `lifecycle-check.py` + `agents-activation-strip.py` usage |
| `streak-tracker/SKILL.md` | Streak philosophy, script usage, opening line rules, break handling |

### Data files (created automatically on first run)

| File | Created/written by | Content |
|------|-----------|---------|
| `data/engagement.json` | recall counters by `lifecycle-check.py mark_recall_sent()` | `recall.weekly_sent`, `recall.monthly_sent`, `recall.last_recall_at` (the only persisted lifecycle state — stage itself is derived, never stored). `activation.*` owned separately. |
| `data/streak.json` | `streak-calc.py` | `current_streak`, `longest_streak`, `streak_start_date`, `milestones_celebrated` |

---

## 5. What notification-composer/SKILL.md Needs

For these strategies to trigger at runtime, `notification-composer/SKILL.md`
must include the following in its execution flow. The agent only reads
the active skill's SKILL.md — if these steps aren't documented there,
the agent won't execute them.

### No separate stage-update step — pre-send-check resolves it

There is **no** pre-step script to run before `pre-send-check.py`. The composer
just calls `pre-send-check.py`, which internally calls the local
`lifecycle-check.py` resolver (no HTTP, no stage-write). The resolver recomputes
`stage` + `days_silent` from meals/weight/inbound on every call, so a returning
user is auto-detected without any explicit reset script.

If a skill needs the lifecycle directly (e.g. for the Welcome Back Check), it can
read it without sending a reminder:

```bash
python3 {notification-manager:baseDir}/scripts/lifecycle-check.py \
  --workspace-dir {workspaceDir} --tz-offset {tz_offset}
# → {"state","activated","first_meal_ever","days_silent","stage", ...}
```

### Required: Stage branching after SEND

When `pre-send-check.py` returns `SEND`, it appends the resolved stage on the
output line (`SEND recall stage=N days_silent=M` for recall stages). Branch on it:

- **Stage 1** → normal reminder
- **Stage 2** → daily recall (lunch slot; `pre-send-check.py` has already claimed
  the slot by bumping `recall.weekly_sent` + `recall.last_recall_at`)
- **Stage 3** → weekly recall (slot claimed the same way)
- **Stage 4** → monthly recall (via `s4-central-dispatch.py`; `--mark-sent` bumps
  `recall.monthly_sent`)
- **User return** → excitement message (auto-detected: `days_silent < 2`)

### Required: streak-calc.py call in meal reminder flow

```bash
python3 {streak-tracker:baseDir}/scripts/streak-calc.py info \
  --data-dir {workspaceDir}/data/meals \
  --workspace-dir {workspaceDir} \
  --tz-offset {tz_offset}
```

Three-way branch for opening line:
- `pending_milestone` not null → milestone celebration + `celebrate` call
- `current_streak >= 2` → daily streak line
- `current_streak < 2` → normal opening

### Required: Weight reply routing

Weight trend up / distress → route to `weight-gain-strategy`, not
`emotional-support`.

---

## 6. Edge Cases

### Existing users (no engagement.json / no recall counters)

`lifecycle-check.py` needs no pre-existing `engagement.json` — a missing file (or
a missing `recall` block) reads as all-zero counters, so the resolver works on the
first call. A user silent for a long time (e.g. 30 days) resolves directly to
Stage 3 (Weekly) because `days_silent >= 4` and no weekly recalls have been sent
yet; the ladder then advances to Monthly → Silent as recall counters accumulate.
`engagement.json` is only written when a recall slot is actually claimed
(`mark_recall_sent`), never just to record a stage.

### Existing users (no streak.json)

`streak-calc.py` creates `streak.json` on first run. Calculates streak
from existing meal files. If the user has been logging continuously,
they'll get the daily streak line immediately on next reminder.

### Two-meal users (no breakfast)

`pre-send-check.py` gates recall to the lunch slot (`lunch`/`meal_2`); other
meal crons that day are suppressed. Same-day / 7-day / 30-day dedup is computed
from `recall.last_recall_at`, so a second cron the same day returns `NO_REPLY`.

### Weekend/holiday silence

Nudge and recall messages detect weekends/holidays and adjust tone:
"you went out to eat" instead of "were you busy". This normalizes
the silence and keeps the food-centric identity.
