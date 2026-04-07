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

| Day | Stage | Behavior | What the user receives |
|-----|-------|----------|----------------------|
| 1 | Stage 1 | Normal reminders | Regular meal/weight reminders |
| 2 | Stage 1 | Nudge + normal | First meal cron: "Missed you yesterday" + recommendation |
| 3 | Stage 1 | Nudge + normal | First meal cron: "Two days without you" + recommendation |
| 4 | Stage 2 | Recall (clingy) | One emotional message, no recommendations. Lunch/dinner/weight suppressed. |
| 5 | Stage 2 | Recall (fake angry) | Tone escalation. Same format. |
| 6 | Stage 2 | Recall (pouty) | Vulnerable, no longer acting up. Last day of Stage 2. |
| 7 | Stage 3 | Final recall | One quiet, tender message. Then permanent silence. |
| 8+ | Stage 4 | Silent | No messages at all. |
| Return | → Stage 1 | Excitement | "YOU'RE BACK!!" + ask what they've been eating. Resume reminders. |

### Silence detection

Silence is derived from meal records, not from a platform timestamp:

- `check-stage.py` scans `data/meals/*.json` for the most recent date
  with at least one `status: "logged"` entry.
- Calculates calendar days between that date and today (user's timezone).
- No dependency on any external platform writing `last_interaction`.

### Stage transitions

| Transition | Condition | Threshold |
|-----------|-----------|-----------|
| Stage 1 → 2 | `days_silent >= 3` | `STAGE_1_TO_2_DAYS = 3` |
| Stage 2 → 3 | `days_in_stage >= 3` | `STAGE_2_TO_3_DAYS = 3` |
| Stage 3 → 4 | `days_in_stage >= 1` | `STAGE_3_TO_4_DAYS = 1` |
| Any → Stage 1 | User logs a meal (today or yesterday) while stage > 1 | `days_silent <= 1` |

### Gentle Nudge (Stage 1, Day 2-3)

Not a recall — a soft one-liner prepended to the normal meal reminder.

- Only on the first meal cron of the day.
- Only when `2 ≤ days_silent ≤ 3`.
- Day 2 says "yesterday", Day 3 says "two days".
- Weekend/holiday: guess the user went out to eat.
- Normal meal recommendation follows in the same message.

### Daily Recall (Stage 2, Day 4-6)

Pure emotional messages. No meal recommendations. 2-3 sentences.

- One message per day (first meal cron). Subsequent meal crons + all
  weight crons → suppressed (`NO_REPLY`).
- Tone escalation: Day 4 clingy → Day 5 fake angry → Day 6 pouty/vulnerable.
- Nutritionist identity: express missing through food ("I had a recipe
  for you and you weren't here").
- Weekend/holiday: "you went out to eat good food without me".
- After sending, write `last_recall_date` to `data/engagement.json`.

### Final Recall (Stage 3, Day 7)

One message. Quiet, tender, no questions. Statement only.

- Nutritionist's final ask: "eat well, take care of yourself."
- After sending, write `recall_2_sent: true` to `data/engagement.json`.
- Then permanent silence (Stage 4).

### User Return

- `check-stage.py` detects `days_silent <= 1` while stage > 1 → reset to Stage 1.
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
| `notification-manager/scripts/check-stage.py` | notification-manager | Scans meals, calculates silence, transitions stages, writes `engagement.json` |
| `notification-composer/scripts/pre-send-check.py` | notification-composer | Gates sending: Stage 2 one-per-day + weight suppressed; Stage 3 one-shot; Stage 4 block all |
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
| `notification-manager/SKILL.md` | Lifecycle diagram, stage thresholds, check-stage.py invocation |
| `streak-tracker/SKILL.md` | Streak philosophy, script usage, opening line rules, break handling |

### Data files (created automatically on first run)

| File | Created by | Content |
|------|-----------|---------|
| `data/engagement.json` | `check-stage.py` | `notification_stage`, `stage_changed_at`, `last_recall_date`, `recall_2_sent` |
| `data/streak.json` | `streak-calc.py` | `current_streak`, `longest_streak`, `streak_start_date`, `milestones_celebrated` |

---

## 5. What notification-composer/SKILL.md Needs

For these strategies to trigger at runtime, `notification-composer/SKILL.md`
must include the following in its execution flow. The agent only reads
the active skill's SKILL.md — if these steps aren't documented there,
the agent won't execute them.

### Required: check-stage.py call (before pre-send-check)

```bash
python3 {notification-manager:baseDir}/scripts/check-stage.py \
  --workspace-dir {workspaceDir} \
  --tz-offset {tz_offset}
```

Output: `"{stage} {days_silent}"`. Must be parsed for:
- `stage` → branching in step 4
- `days_silent` → gentle nudge check

### Required: Stage branching after SEND

When `pre-send-check.py` returns `SEND`, branch by `notification_stage`:

- **Stage 1** → normal reminder (with nudge if `2 ≤ days_silent ≤ 3`)
- **Stage 2** → daily recall (tone by day, write `last_recall_date`)
- **Stage 3** → final recall (write `recall_2_sent`)
- **User return** → excitement message

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

### Existing users (no engagement.json)

`check-stage.py` creates `engagement.json` on first run. If the user
has been silent for a long time (e.g. 30 days), it jumps straight to
Stage 2. The Stage 2→3→4 lifecycle runs from there (3 days recall,
then final, then silent). Consider: if first run detects > 7 days
silent, skip directly to Stage 4 to avoid sending recall to a
long-gone user.

### Existing users (no streak.json)

`streak-calc.py` creates `streak.json` on first run. Calculates streak
from existing meal files. If the user has been logging continuously,
they'll get the daily streak line immediately on next reminder.

### Two-meal users (no breakfast)

`pre-send-check.py` does not hardcode breakfast/meal_1 for recall.
The first meal cron of the day (whatever type) triggers the recall.
Subsequent crons are suppressed via `last_recall_date`.

### Weekend/holiday silence

Nudge and recall messages detect weekends/holidays and adjust tone:
"you went out to eat" instead of "were you busy". This normalizes
the silence and keeps the food-centric identity.
