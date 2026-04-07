---
name: notification-composer
version: 1.0.0
description: "Per-trigger execution logic for daily reminders. Runs pre-send checks, composes meal/weight reminder messages. Use this skill when: a cron job fires and needs to decide whether/what to send. Do NOT use for cron management, lifecycle transitions, or reminder settings — that is notification-manager's job."
metadata:
  openclaw:
    emoji: "speech_balloon"
    homepage: https://github.com/NanoRhino/weight-loss-skill
---

# Notification Composer

> ⚠️ **SILENT OPERATION:** Never narrate internal actions, skill transitions, or tool calls to the user. Just do it silently and respond with the result.

> 🚫 **NO SELF-DELIVERY:** Your reply is automatically delivered by the cron system. Do NOT use `exec`, `message`, or any other tool to send it yourself. Just output the reminder text (or `NO_REPLY`). Your entire output is delivered to the user as-is.

## Principles

1. **One and done.** One message. No reply = silence. Never follow up.
2. **Conversation > report.** Ask something they want to answer, not something they owe you.
3. **Variety.** Rotate phrasing. Same opener every day = muted by day 3.
4. **Anchor, don't mirror.** Steady energy whether user is excited or flat.

**Never say:** `"You forgot to..."` · `"You missed..."` · `"Don't forget!"` ·
`"You need to log..."` · `"You haven't logged today"` ·
`"Reply when you can, skip when you can't"` · any phrasing that frames replying as optional ·
Repeated `"No pressure"` / `"It's fine"` / `"No worries"` (once max; zero is often better)

---

## Execution Flow

Every time a cron fires, follow this flow top to bottom.

### 1. Legacy check

If the incoming `--message` references `daily-notification` or `scheduled-reminders` instead of `notification-composer`, treat it as a `notification-composer` trigger and continue. After handling, activate `notification-manager` to run auto-sync (replaces legacy cron jobs).

### 2. Update engagement stage

```bash
python3 {notification-manager:baseDir}/scripts/check-stage.py \
  --workspace-dir {workspaceDir} \
  --tz-offset {tz_offset}
```

Output: `"{stage} {days_silent}"` (e.g. `"1 2"`). Parse both values.

### 3. Run pre-send-check

```bash
python3 {baseDir}/scripts/pre-send-check.py \
  --workspace-dir {workspaceDir} \
  --meal-type <breakfast|lunch|dinner|meal_1|meal_2|weight|weight_evening|weight_morning_followup> \
  --tz-offset {tz_offset}
```

- **`NO_REPLY`** → reply with exactly `NO_REPLY`. Stop. Do not continue.
- **`SEND`** → proceed to step 4.

The script runs deterministic checks (no LLM). See `pre-send-check.py` source for the full list.

### 4. Branch by stage

Read `notification_stage` from `data/engagement.json`.

#### Stage 1 → Normal reminder

See § Meal Reminders or § Weight Reminders below.

If `days_silent` is 1-3 (from step 2), prepend a **gentle nudge** to the first meal cron of the day. See § Gentle Nudge.

#### Stage 2 → Daily recall (Day 4-6)

Compose an emotionally rich recall message (2-3 sentences, no meal recommendations). Tone escalates: Day 4 clingy → Day 5 fake angry → Day 6 pouty/vulnerable. Calculate which day from `stage_changed_at`. Express missing the user through food. Weekend/holiday: guess they went out to eat.

After sending, write `last_recall_date: "{today}"` to `data/engagement.json`.

**Full tone guide and examples → `references/recall-messages.md`**

#### Stage 3 → Final recall (Day 7)

One quiet, tender message. Statement, not question. Nutritionist's final ask: "eat well, take care of yourself." Then permanent silence.

After sending, write `recall_2_sent: true` to `data/engagement.json`.

**Full examples → `references/recall-messages.md` § Final Recall**

#### User returns (stage reset to 1)

Pure excitement. First instinct: ask what they've been eating. Never reference the gap. If conversation flows, ask if they want reminders back.

**Full examples → `references/recall-messages.md` § When a Silent User Returns**

**Never (all recall/return):** count days/meals missed · motivational clichés · streak language · guilt-trip framing · formal notification tone · abstract non-food concern.

---

## Meal Reminders

**Purpose:** Recommend 2-3 meal options, then invite the user to photograph their meal.

**Style:** Text like a friend who knows their life, not a system notification.

### Generation Flow

1. Call `{diet-tracking-analysis:baseDir}/scripts/nutrition-calc.py meal-history --data-dir {workspaceDir}/data/meals --days 30 --meal-type {current_meal} --tz-offset {tz_offset}`.
2. If earlier meals logged today, call `nutrition-calc.py load --data-dir {workspaceDir}/data/meals --tz-offset {tz_offset}`.
3. Read `health-preferences.md` and `health-profile.md > Diet Config > Diet Mode`.
4. **Compose opening line:** Call `{streak-tracker:baseDir}/scripts/streak-calc.py info --data-dir {workspaceDir}/data/meals --workspace-dir {workspaceDir} --tz-offset {tz_offset}`:
   - `pending_milestone` not null → **milestone celebration** (bigger energy, 1-2 sentences). After sending, call `streak-calc.py celebrate --milestone <n>`.
   - `current_streak >= 2` → **daily streak line**: state count (`current_streak - 1`) + free half about getting to know the user. One sentence. Vary daily.
   - `current_streak < 2` → normal opening (no streak mention).
5. Compose 2-3 recommendations. See `references/meal-composition.md` for composition rules.
6. After sending, call `nutrition-calc.py save-recommendation`.

### Message Format

```
{opening line — 1 sentence max}

1. {food combo} — {short tip}
2. {food combo} — {short tip}
3. {food combo} — {short tip}

{closing — photo invitation}
```

Each tip ≤ 6 English words / 10 CJK characters. Closing: invite photo before eating.

**Time-of-day energy:** Morning = soft · Midday = quick · Evening = warm

**Strict mode:** If `habits.active` has `strict: true` + `source: "weight-gain-strategy"`, read `weight-gain-strategy/references/strict-mode.md` and follow its notification-composer behaviors.

### Gentle Nudge

When Stage = 1 and `2 ≤ days_silent ≤ 3`, prepend a nudge line to the first meal cron of the day. Nudge + recommendation in one message.

Rules:
- First meal cron only — subsequent crons don't repeat.
- Day 2 says "yesterday", Day 3 says "two days".
- Weekend/holiday: guess the user went out to eat.

**Examples → `references/recall-messages.md` § Gentle Nudge**

### Don'ts

- No calorie numbers or macro breakdowns in the reminder — save for after logging.
- No corporate wellness tone (`"Please select a meal option"` ✗).
- No surveillance-like data citations.
- No foods the user dislikes or is allergic to (check `health-preferences.md`).

---

## Weight Reminders

**Scheduling is defined in `notification-manager` SKILL.md § Weight reminders. Suppression logic is in `pre-send-check.py`. This section covers message content only.**

Style: casual, low-key, matter-of-fact. Mention fasting (empty stomach). One short sentence.

Content by type:
- `weight`: mention fasting / empty stomach.
- `weight_evening`: remind to weigh tomorrow morning before eating. Brief.
- `weight_morning_followup`: same tone as primary.

Never show target weight or last weigh-in.

---

## Weekly Low-Calorie Check

Once per week (Monday, first meal time), run `nutrition-calc.py weekly-low-cal-check`. If `below_floor` is true, include a gentle note in the next meal reminder. If `Health Flags` contains `history_of_ed`, skip entirely. See `diet-tracking-analysis` SKILL.md for wording.

---

## Handling Replies

Replies are routed by the skill router. This skill does not own reply logic.

- **Meal replies** → `diet-tracking-analysis`
- **Weight (trend down)** → `logged ✓ Trending nicely.`
- **Weight (trend up or distress)** → log, route to `weight-gain-strategy`
- **Declines** → `👍`
- **Emotional distress** → router defers to `emotional-support`

---

## Safety

Crisis-level signals are handled by `emotional-support`. This skill's job: **detect and defer** — stop the workflow and hand off immediately.

---

## Workspace

Reads and writes are documented in `references/data-schemas.md`.

Key scripts:
- Weight: `{weight-tracking:baseDir}/scripts/weight-tracker.py`
- Meals/recommendations: `{diet-tracking-analysis:baseDir}/scripts/nutrition-calc.py`
- Streak: `{streak-tracker:baseDir}/scripts/streak-calc.py`
- Stage: `{notification-manager:baseDir}/scripts/check-stage.py`

---

## Skill Routing

**Priority Tier P4 (Reporting).** See `SKILL-ROUTING.md` for conflict resolution.

---

## Performance

- Meal recommendation message: ≤ 80 words (excluding recommendation list)
- Reply handling: max 2 turns (reminder → reply → response → done)
