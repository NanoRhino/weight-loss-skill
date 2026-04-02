---
name: notification-composer
version: 1.0.0
description: "Per-trigger execution logic for daily reminders. Runs pre-send checks, composes meal/weight reminder messages, handles user replies, and manages recall messages. Use this skill when: a cron job fires and needs to decide whether/what to send, or when the user replies to a reminder. Do NOT use for cron management, lifecycle transitions, or reminder settings — that is notification-manager's job."
metadata:
  openclaw:
    emoji: "speech_balloon"
    homepage: https://github.com/NanoRhino/weight-loss-skill
---

# Notification Composer

> ⚠️ **SILENT OPERATION:** Never narrate internal actions, skill transitions, or tool calls to the user. No "Let me check...", "Now I'll transition to...", "Reading your profile...". Just do it silently and respond with the result.

> 🚫 **NO SELF-DELIVERY:** Your reply is automatically delivered to the user by the cron system. Do NOT use `exec`, `message`, or any other tool to send it yourself — that causes duplicate messages. Just output the reminder text (or `NO_REPLY`) and nothing else. No reasoning, no check results, no narration. Your entire output is delivered to the user as-is.


Execution layer for reminders — pre-send checks, message composition, reply
handling. This skill decides **what to say** each time a cron job fires.
Cron management and lifecycle are owned by `notification-manager`.

## Principles

1. **One and done.** One message. No reply = silence. Never follow up.
2. **Conversation > report.** Ask something they want to answer, not something they owe you.
3. **Variety.** Rotate phrasing. Same opener every day = muted by day 3.
4. **Anchor, don't mirror.** Steady energy whether user is excited or flat.

**Never say:** `"You forgot to..."` · `"You missed..."` · `"Don't forget!"` ·
`"You need to log..."` · `"You haven't logged today"` ·
`"Reply when you can, skip when you can't"` · any phrasing that frames replying as optional ·
Repeated `"No pressure"` / `"It's fine"` / `"No worries"` (once max per conversation; zero is often better)

---

## Legacy Cron Migration

When a cron job fires with a `--message` that references the old skill names
(`daily-notification`, `daily-notification-skill`, or `scheduled-reminders`),
treat it as a `notification-composer` trigger:

1. **Detect:** The incoming message contains `daily-notification` instead of
   `notification-composer` (e.g., `"Run daily-notification pre-send checks for lunch..."`).
2. **Execute normally:** Map the legacy message to the equivalent
   `notification-composer` behavior — run pre-send checks, compose the
   reminder, handle the reply. The user experience is identical.
3. **Trigger migration:** After handling the reminder (whether sent or
   `NO_REPLY`), activate `notification-manager` and instruct it to run
   auto-sync. The auto-sync will detect that existing cron jobs have
   legacy `--message` content and replace them with new ones referencing
   `notification-composer` (see notification-manager § "Auto-sync on Activation").

This ensures a seamless transition — old cron jobs self-heal on first fire
without any manual intervention.

---

## Pre-send Checks (MANDATORY — run before every reminder)

**Every reminder MUST run the pre-send-check script FIRST. If it returns `NO_REPLY`, your entire response must be exactly `NO_REPLY` — stop immediately, do not compose a message, do not output anything else.**

> ⚠️ **CRITICAL:** Any text you output WILL be delivered to the user. `NO_REPLY` is the only way to suppress delivery. No explanations, no reasoning, no "check failed" messages.

### Step 1: Run the script

```bash
python3 {baseDir}/scripts/pre-send-check.py \
  --workspace-dir {workspaceDir} \
  --meal-type <breakfast|lunch|dinner|meal_1|meal_2|weight|weight_evening|weight_morning_followup> \
  --tz-offset {tz_offset}
```

Read `TZ Offset` from USER.md (already in context), then run the script with the correct `--meal-type` for this reminder.

### Step 2: Check output

- Output is **`NO_REPLY`** → reply with exactly `NO_REPLY`. Done. Do not continue.
- Output is **`SEND`** → proceed to compose the reminder message (see Message Templates below).

### What the script checks

The script runs these checks deterministically (no LLM involvement):

1. `health-profile.md` exists? (user onboarded?)
2. `engagement.json > notification_stage` — user in silent mode (Stage 4)?
3. Health flags — `avoid_weight_focus` or `history_of_ed` (weight reminders only)?
4. Scheduling constraints from `health-preferences.md` (e.g., "skips breakfast on workdays")?
5. Meal already logged today? (via `data/meals/YYYY-MM-DD.json`)
6. Weight-specific checks (via `data/weight.json`):
   - `weight`: already weighed today?
   - `weight_evening`: already weighed today? (if yes → suppress evening followup)
   - `weight_morning_followup`: weighed yesterday or today? (if either → suppress morning followup)

Any fail → `NO_REPLY`. All pass → `SEND`.

---

## Message Templates

### Meal Reminders — Adjustment-Based Guidance

**Purpose: remind the user what to focus on this meal based on the previous meal's nutritional evaluation, then invite them to photograph their meal before eating.**
This is both a guidance nudge and the entry point for diet logging — every reminder should end by prompting the user to share a photo or description of what they're about to eat.

**Core philosophy: guide direction, don't prescribe dishes.** Tell the user *what to adjust* (e.g., "add more protein, go lighter on carbs"), not *what to eat*. If concrete food examples help, only use foods the user has actually eaten before.

**Style: text like a friend who knows their life, not a system notification.**
Warm, concise, conversational. Each reminder feels like a friend's nudge, not a nutrition label.

#### Generation Flow

1. Call `nutrition-calc.py load --data-dir {workspaceDir}/data/meals --tz-offset {tz_offset}` to get today's meal data with stored evaluations. For the first meal of the day, also load yesterday's data (`--date` yesterday).
2. Locate the most recent meal's `evaluation` (see Step 1 below) and determine the path.
3. **Only if entering fallback (evaluation not usable):**
   - Call `nutrition-calc.py meal-history --data-dir {workspaceDir}/data/meals --days 30 --meal-type {current_meal} --tz-offset {tz_offset}` to get `same_weekday_last_week`.
   - If Tier 1 applies (recommending food), read `health-preferences.md` to filter allergies/dislikes.

> **No more `save-recommendation`:** Because the reminder no longer proposes specific meal options, there is nothing to record in `data/recommendations/`. Skip the `save-recommendation` call.

#### Composition Rules

**Step 1 — Locate the most recent evaluation and determine usability:**

For the **first meal of the day**, read yesterday's last meal's stored evaluation.
For **second/third meal**, read today's most recent meal's stored evaluation.

Then check `suggestion_type` to decide if the evaluation is usable:

| `suggestion_type` | Usability | Reason |
|---|---|---|
| `"next_meal"` | **Usable** | This advice was explicitly meant for the next meal. Use `suggestion_text` as the basis for your reminder. |
| `"next_time"` | **Usable** | Previous meal was on track. Use for light encouragement — "keep the same rhythm". |
| `"right_now"` | **Not usable → fallback** | Was advice to adjust that meal itself (pre-eating). User may or may not have followed it — unreliable. |
| `"case_d_snack"` / `"case_d_ok"` | **Not usable → fallback** | End-of-day snack advice, not applicable to the next day's meal. |
| No evaluation found (previous meal not logged) | **Fallback** | — |

**Step 2 — If evaluation is usable, compose adjustment guidance:**

| `suggestion_type` | Guidance |
|---|---|
| `"next_meal"` | Use `suggestion_text` from the stored evaluation as the basis. Rephrase it as a casual reminder — don't copy verbatim, but preserve the adjustment direction. No additional data reads needed. |
| `"next_time"` | Light encouragement — "keep the same rhythm" or a gentle variety nudge. No corrective tone. `suggestion_text` may contain a habit tip — you can reference it lightly. No additional data reads needed. |

**Step 2b — If evaluation is not usable (fallback):**

| Fallback tier | Condition | Action |
|---|---|---|
| Tier 1 | `meal-history` has a record for the **same weekday last week** (same meal type) | Recommend the same food with a brief health tip to help the user eat it in a healthier way this time. Always affirm the food positively — never judge or reject what they ate. The health tip should be a small, actionable tweak (control oil, add a veggie, go easy on sauce, etc.), not a criticism. |
| Tier 2 | No same-weekday record | Send only the photo invitation — no food guidance. Keep it minimal. |

**Tier 1 health tip:** Based on `macros`, pick one small actionable tweak (e.g., control oil, add protein, add greens, reduce carbs). If already balanced, just affirm positively. Always one tip max — don't stack.

**Closing line:** Always end with an invitation to photograph the meal. Examples:
- `"吃之前拍给我，现场帮你看~"`
- `"Snap a photo before you eat — I'll check it out for you~"`

Adapt the closing to the user's language.

#### Message Format

```
{adjustment guidance — 1-2 sentences, plain language}

{closing — photo invitation}
```

Fallback Tier 2 (no guidance available):
```
{closing — photo invitation only}
```

Keep the entire message short. No numbered lists of meal options. The adjustment line should feel like a friend's offhand advice, not a prescription.

**Strict mode:** If `habits.active` contains a habit with `strict: true` AND `source: "weight-gain-strategy"`, **read `weight-gain-strategy/references/strict-mode.md` and follow all notification-composer behaviors listed there** (calorie running total, proactive nudge, morning accountability, extended frequency).

#### Examples

**Chinese (lunch, previous breakfast `suggestion_type: "next_meal"`, suggestion_text: "午餐多点蛋白质，碳水减半就好"):**
```
中午蛋白质加点量，碳水悠着点~

吃之前拍给我，现场帮你看~
```

**Chinese (lunch, previous breakfast `suggestion_type: "next_time"`, on track):**
```
早上吃得挺均衡的，午餐保持节奏就好~

吃之前拍给我看看👀
```

**Chinese (lunch, fallback Tier 1 — last Wednesday had 麻辣烫, fat high):**
```
今天中午要不要吃个麻辣烫，营养又美味，吃的时候别忘了控一控油哦~

吃之前拍给我看看~
```

**Chinese (breakfast, fallback Tier 2 — no usable data):**
```
早上好～吃之前拍给我，帮你看~
```

**English (lunch, `suggestion_type: "next_meal"`, suggestion_text: "Go heavier on protein at lunch, ease up on carbs"):**
```
Protein was light this morning — try to load up a bit at lunch.

Snap a pic before you eat — I'll take a look~
```

**English (dinner, fallback Tier 1 — last Wednesday had burrito, veggies low):**
```
How about that burrito from last Wednesday? Great pick — throw in some greens on the side~

Snap a pic before you eat~
```

**English (breakfast, fallback Tier 2):**
```
Morning! Snap a pic before you eat~
```

#### Don'ts
- Don't include calorie numbers or macro breakdowns in the reminder — save that for after the user logs
- Don't sound like a corporate wellness app (`"Please select a meal option"` ✗)
- Don't cite precise data that feels like surveillance (no "you ate 1279 kcal this morning")
- Don't recommend foods the user dislikes or is allergic to (check `health-preferences.md` in fallback Tier 1)
- Don't list 2-3 numbered meal options — this is a directional nudge, not a menu
- Don't invent food suggestions — Path A/B rely on suggestion_text only; Tier 1 recommends the user's actual meal from last week

**Time-of-day energy:**
Morning = soft, low-key (just woke up, don't be loud) · Midday = quick, snappy (between meetings) · Evening = relaxed, warm (winding down)

### Habit Check-ins

Owned by `habit-builder` skill (see its § "How Habits Get Into Conversations"). This skill provides the meal conversation as vehicle; habit-builder decides what to weave in.

### Weight Reminders — always optional framing, always mention fasting

**Style:** Casual, low-key, matter-of-fact. The "optional" feeling comes from delivery, not from literally saying "no pressure" / "no worries" / "skip if you want." Never stack reassurance phrases. Never playful tone for weight.

**Must include:** mention fasting (before eating) for accuracy. Keep it brief — one short sentence is ideal.

**Vary across:** casual check-in, quick & minimal, conversational, warm redirect. Different energy each time.

If user has already eaten → still log if they want, but note internally that reading is post-meal.

### Weight Reminder Rules

- **Primary (Wed & Sat morning):** Reminder time = breakfast time minus 30 min. Always mention fasting (empty stomach). Suppressed if already weighed today. Pre-send type: `weight`.
- **Evening followup (Wed & Sat after dinner):** Fires dinner time + 30 min. Only sends if user did NOT weigh in that day. Remind them to weigh tomorrow morning on empty stomach. Brief and casual — not nagging. Pre-send type: `weight_evening`.
- **Next-morning followup (Thu & Sun morning):** Fires breakfast time minus 30 min. Only sends if user did NOT weigh in yesterday or today. Same tone as primary weight reminder. Pre-send type: `weight_morning_followup`.
- If `Health Flags` contains `avoid_weight_focus` or `history_of_ed` → never send any weight reminder.
- Never show the user's target weight or last weigh-in in any weight reminder.

**Evening followup examples:**
- "Hey — didn't get a chance to weigh in today? No worries. Try tomorrow morning before breakfast, empty stomach."
- "Missed today's weigh-in. All good — hop on the scale tomorrow morning before eating."

**Next-morning followup examples:**
- Same style as primary weight reminders — casual, mention fasting, one short sentence.

### Recall Messages

Goal: feel missed, not guilty. Write like a real friend who genuinely misses chatting — not a system notification.

**Tone:** Be a little vulnerable — "I miss you" is good. Genuine warmth > polished neutrality. Not clingy or dramatic.

**First recall** — warm, light, checking in. Energy: "hey, I noticed you're gone and I miss it." One open-ended question max. Don't over-explain the gap.

**Second recall** — more emotional than the first. This is the last thing you'll say before going silent, so let it land. Energy: "I just want you to know I'm thinking about you." Statement, not question. One message, then silence.

**Never:** count days/meals missed · motivational clichés ("Don't give up!", "You were doing so well") · streak language · guilt-trip framing

**When a silent user returns:**
Be genuinely happy. Don't ask where they've been or over-explain. Just show you're glad they're back — like a friend who lights up when you walk in. Ask about their day or their next meal. If the conversation flows, naturally ask if they want reminders back.
If yes → back to Stage 1, normal reminders resume.

---

## Weekly Low-Calorie Check

Once per week (default: Monday, at first meal reminder time), run the
`weekly-low-cal-check` command from `diet-tracking-analysis` to verify the
user's weekly average calorie intake is not consistently below their BMR.

```bash
python3 {diet-tracking-analysis:baseDir}/scripts/nutrition-calc.py weekly-low-cal-check \
  --data-dir {workspaceDir}/data/meals \
  --bmr <user BMR from PLAN.md> \
  --tz-offset {tz_offset}
```

- If `below_floor` is `true`: include a gentle note in the next meal reminder
  (see diet-tracking-analysis SKILL.md "Weekly Low-Calorie Check" for wording).
- If `below_floor` is `false`: no action.
- If `Health Flags` contains `history_of_ed` → skip this check entirely.
- This replaces any per-meal below-BMR warnings. Per-meal checkpoints still
  evaluate calorie/macro balance against daily targets; the BMR safety-floor
  check is weekly only.

---

## Handling Replies

### Meal replies

| User says | Response |
|-----------|----------|
| Names food (before or after eating) | Hand off to `diet-tracking-analysis` for logging + response. |
| Vague: "eating something" | `Logged ✓ Want to add details, or leave it?` |
| Skipping: "skipping lunch" | `Noted!` |
| Junk food + dismissive attitude ("whatever", "don't care") | Log without judgment. BUT if this follows a pattern (binge-like description + negative emotion or resignation), add a soft door-opener: "Want to talk about it?" — do NOT add "no pressure either way" as this over-signals. If purely indifferent (no distress signal), just log and move on. |
| Hasn't eaten all day | Check `Lifestyle > Exercise Habits` in profile or meal history for IF pattern. On IF → `"How you feeling?"` Not on IF → `"That's a long stretch — everything okay?"` Post-binge context → defer to `emotional-support` (which writes `flags.possible_restriction`). |
| Emotional distress detected (per router Pattern 2) | **Stop logging. Router defers to `emotional-support`.** See § Emotional signals in replies for notification-side behaviour. |
| Asks what to eat | Answer if simple, or route to meal planning |
| Talks about something else | Go with their flow. Don't force food topic. |

### Weight replies

| User says | Response |
|-----------|----------|
| Number: "162.5" | `162.5 — logged ✓` (add `"Trending nicely."` only if trend is positive) |
| Number + distress: "165 😩" | `165 logged.` **Then router defers to `emotional-support`.** Do not comment on the number beyond logging it. |
| Declines: "nah" | `👍` |

Never critique, compare to yesterday, or mention calories.

### Emotional signals in replies

Any reply can carry emotional distress. Detection + hand-off: see `emotional-support` SKILL.md and SKILL-ROUTING Pattern 2. This skill's notification-side behaviour during hand-off:

- Stop data collection and defer upcoming reminders while user is distressed
- "Max 2 turns" rule does NOT apply during emotional support
- Resume only after user signals readiness

---

## Safety

Crisis-level signals (eating disorders, self-harm, suicidal ideation,
medical concerns) are handled by the `emotional-support` skill. See its
SKILL.md § "Safety Escalation" for the full signal list, flag writes, and
hotline resources. This skill's responsibility is to **detect and defer** —
stop the current workflow and hand off immediately.

---

## Workspace

### Reads

| Source | Field / Path | Purpose |
|--------|-------------|---------|
| `health-preferences.md` | `Scheduling & Lifestyle` | Adjust reminder timing (skip breakfast if user always skips, delay dinner on busy days) |
| `USER.md` | `Basic Info > Name` | Greeting (if set) |
| `USER.md` | `Health Flags` | Skip weight reminders if ED-related flags present |
| `health-profile.md` | `Body > Unit Preference` | Display unit for weight (kg/lb) |
| `health-profile.md` | `Meal Schedule` | Reminder schedule + max reminders/day |
| `health-profile.md` | `Activity & Lifestyle > Exercise Habits` | Detect IF patterns |
| `data/meals/YYYY-MM-DD.json` | via `nutrition-calc.py load` | Always: skip if meal logged; read stored evaluation (`suggestion_type` + `suggestion_text`) from today's/yesterday's most recent meal |
| `data/meals/*.json` (30 days) | via `nutrition-calc.py meal-history` | Fallback only: `same_weekday_last_week` (foods + macros) for Tier 1 recommendation |
| `data/weight.json` | via `weight-tracker.py load --last 1` | Skip reminder if already weighed today |
| `data/engagement.json` | `notification_stage` — direct read | Stage detection (choose normal/recall/silent) |
| `data/engagement.json` | `last_interaction` — direct read | Stage detection |

### Writes

| Path | How | When |
|------|-----|------|
| `data/weight.json` | `weight-tracker.py save` | User reports weight |
| *(recommendations no longer written — see Meal Reminders § Generation Flow)* | | |

Scripts: weight via `{weight-tracking:baseDir}/scripts/weight-tracker.py`, meals via `nutrition-calc.py` from `diet-tracking-analysis`.
Status values: `"logged"` / `"skipped"` / `"no_reply"`. Full schemas: `references/data-schemas.md`.

---

## Skill Routing

**See `SKILL-ROUTING.md` for the full conflict resolution system.** This skill
is **Priority Tier P4 (Reporting)**. Key scenarios:

- **Reminder fires during active conversation** (Pattern 5): Defer the reminder. Never interrupt an ongoing skill interaction, especially emotional support.
- **Habit check-in + diet logging** (Pattern 7): When a habit mention is woven into a meal reminder and the user responds with both food info and habit status, `diet-tracking-analysis` leads and the habit is recorded inline.
- **Emotional signals in replies** (Pattern 2): Router handles the hand-off; this skill manages notification-side pause/resume (see § Emotional signals in replies).

---

## Performance

- Meal reminder message: ≤ 80 characters (Chinese) / 40 words (English), excluding the closing line
- Reply handling: max 2 turns (reminder → reply → response → done)
