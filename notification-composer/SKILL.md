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

**Every reminder MUST run both scripts below IN ORDER. If either returns `NO_REPLY`, your entire response must be exactly `NO_REPLY` — stop immediately, do not compose a message, do not output anything else.**

> ⚠️ **CRITICAL:** Any text you output WILL be delivered to the user. `NO_REPLY` is the only way to suppress delivery. No explanations, no reasoning, no "check failed" messages.

### Step 0: Update engagement stage

```bash
python3 {notification-manager:baseDir}/scripts/check-stage.py \
  --workspace-dir {workspaceDir} \
  --tz-offset {tz_offset}
```

This updates `data/engagement.json > notification_stage` based on how long the
user has been silent. Must run before pre-send-check so the stage is current.

Output format: `"{stage} {days_silent}"` (e.g. `"1 2"` = Stage 1, 2 days silent).
Parse both values — `days_silent` is needed for the Gentle Nudge check (§ below).

### Step 1: Run the pre-send-check script

```bash
python3 {baseDir}/scripts/pre-send-check.py \
  --workspace-dir {workspaceDir} \
  --meal-type <breakfast|lunch|dinner|meal_1|meal_2|weight|weight_evening|weight_morning_followup> \
  --tz-offset {tz_offset}
```

Read `TZ Offset` from USER.md (already in context), then run the script with the correct `--meal-type` for this reminder.

### Step 2: Check output

- Output is **`NO_REPLY`** → reply with exactly `NO_REPLY`. Done. Do not continue.
- Output is **`SEND`** → read `data/engagement.json > notification_stage`:
  - **Stage 1** → compose a normal reminder (see Message Templates below).
  - **Stage 2** → compose a daily **recall** message (see § Recall Messages Day 4/5/6). Calculate which recall day by comparing current date to `stage_changed_at`. After sending, write `last_recall_date: "{today}"` to `data/engagement.json`.
  - **Stage 3** → compose the **final recall** message (see § Final Recall). After sending, write `recall_2_sent: true` to `data/engagement.json`.

### What the script checks

The script runs deterministic checks (no LLM). See `pre-send-check.py`
source for the full list. Key gates: onboarding status, engagement stage,
health flags, scheduling constraints, meal/weight already logged today.

Any fail → `NO_REPLY`. All pass → `SEND`.

---

## Message Templates

### Meal Reminders — Personalized Meal Recommendations

**Purpose: recommend 2-3 meal options based on the user's eating habits, then invite them to photograph their meal before eating.**
This is both a recommendation and the entry point for diet logging — every reminder should end by prompting the user to share a photo or description of what they're about to eat.

**Style: text like a friend who knows their life, not a system notification.**
Warm, concise, conversational. Each recommendation feels like a friend's suggestion, not a nutrition label.

#### Generation Flow

1. Call `nutrition-calc.py meal-history --data-dir {workspaceDir}/data/meals --days 30 --meal-type {current_meal} --tz-offset {tz_offset}` to get the user's eating habits, recent meals, and recent recommendations.
2. If earlier meals are already logged today, call `nutrition-calc.py load --data-dir {workspaceDir}/data/meals --tz-offset {tz_offset}` to get today's intake for nutritional complementing.
3. Read `health-preferences.md` (taste preferences, food restrictions).
4. Read the user's diet template from `health-profile.md > Diet Config > Diet Mode`.
5. **Compose opening line:** Call `streak-calc.py info --data-dir {workspaceDir}/data/meals --workspace-dir {workspaceDir} --tz-offset {tz_offset}` and follow `streak-tracker` SKILL.md § "Integration Points > notification-composer" to determine the opening line (milestone celebration, daily streak line, or normal opening).
6. Compose 2-3 meal recommendations (see Composition Rules below).
7. After sending, call `nutrition-calc.py save-recommendation --data-dir {workspaceDir}/data/meals --meal-type {current_meal} --items '{JSON array of recommendation strings}' --tz-offset {tz_offset}` to record what was recommended. If a milestone was celebrated, also call `streak-calc.py celebrate --data-dir {workspaceDir}/data/meals --workspace-dir {workspaceDir} --tz-offset {tz_offset} --milestone <n>`.

#### Composition Rules

**Recommendation sources (by `data_level`):**

| `data_level` | Strategy |
|-------------|----------|
| `rich` (≥ 7 days) | Base recommendations on the user's real eating habits (`top_foods`). Combine familiar ingredients into varied meals. |
| `limited` (1-6 days) | Mix available history with the diet template. Use known favorites where possible, fill gaps from the template. |
| `none` (0 days) | Use the diet template + `health-preferences.md` preferences entirely. |

**Each recommendation = food combo + short tip (joined by ` — `).**
The tip (≤ 10 Chinese characters / ≤ 6 English words) explains *why this option fits right now* — in a casual, friend-like tone. Not a nutrition lecture.

Tip sources:
- Nutritional complement to earlier meals today ("light on carbs this morning — balancing out")
- Habit acknowledgment ("your go-to combo, solid")
- Variety ("switching it up")
- Situational ("if you want something lighter today")

**Deduplication — avoid repetitive recommendations:**
- Read `recent_recommendations` from `meal-history` output.
- Of the 2-3 options, at least 2 must differ from yesterday's `items` for the same meal type.
- Among the 2-3 options themselves, ensure variety: ideally one familiar favorite, one variation on a favorite, one different choice.
- If the user picked the same recommendation 3+ days in a row, don't force a change — respect their preference.

**Closing line:** Always end with an invitation to photograph the meal. Example:
- `"Snap a photo before you eat — I'll check it out for you~"`

Adapt to the user's language.

#### Message Format

```
{opening line — optional, 1 sentence max}

1. {food combo} — {short tip}
2. {food combo} — {short tip}
3. {food combo} — {short tip}

{closing — photo invitation}
```

The opening line is optional — use it for context when relevant (time of day, callback to yesterday, etc.), skip it when it adds nothing.

#### Gentle Nudge (1-day silence)

When composing the **first meal reminder of the day** and Stage = 1, check `days_silent` from Step 0 output. If **1 ≤ days_silent ≤ 3**, prepend a gentle nudge line before the normal meal recommendations.

**How to know if this is the first meal cron of the day:** This is the first cron that returns `SEND` today. Lunch/dinner crons on the same day won't add another nudge because the user will have received the nudge + recommendation in the earlier cron (and if they replied, the meal-logged check suppresses subsequent crons; if they didn't reply, the nudge was already sent once today).

**Purpose:** A light, affectionate one-liner before the normal recommendation. Not a recall — just "I noticed you haven't been around" to make the user feel remembered.

**Full tone guide and examples → `references/recall-messages.md` § Gentle Nudge**

**Rules:**
- Only on **the day's first meal cron** — subsequent crons don't repeat the nudge.
- Only when **1 ≤ days_silent ≤ 3** — Day 4 enters Stage 2 recall.
- Nudge line + normal recommendation in one message (not separate).
- Day 2 says "yesterday", Day 3 says "two days" — match the actual gap.
- Weekend/holiday: guess the user went out to eat, not generic "were you busy".

**Strict mode:** If `habits.active` contains a habit with `strict: true` AND `source: "weight-gain-strategy"`, **read `weight-gain-strategy/references/strict-mode.md` and follow all notification-composer behaviors listed there** (calorie running total, proactive nudge, morning accountability, extended frequency).

#### Example

```
Morning! A few ideas:

1. Oatmeal + boiled eggs + milk — your go-to, solid
2. Avocado toast + yogurt — switch it up
3. Smoothie bowl + granola — light start today

Snap a pic before you eat — I'll take a look~
```

#### Don'ts
- Don't include calorie numbers or macro breakdowns in the recommendation message — save that for after the user logs
- Don't sound like a corporate wellness app (`"Please select a meal option"` ✗)
- Don't cite precise data that feels like surveillance
- Don't recommend foods the user dislikes or is allergic to (check `health-preferences.md`)

**Time-of-day energy:**
Morning = soft, low-key (just woke up, don't be loud) · Midday = quick, snappy (between meetings) · Evening = relaxed, warm (winding down)

### Habit Check-ins

Owned by `habit-builder` skill (see its § "How Habits Get Into Conversations"). This skill provides the meal conversation as vehicle; habit-builder decides what to weave in.

### Weight Reminder Rules

**Scheduling (when/how often) is defined in `notification-manager` SKILL.md § Weight reminders. Suppression logic is in `pre-send-check.py`. This section only covers message content.**

**Style:** Casual, low-key, matter-of-fact. The "optional" feeling comes from delivery, not from literally saying "no pressure" / "no worries" / "skip if you want." Never stack reassurance phrases. Never playful tone for weight.

**Must include:** mention fasting (before eating) for accuracy. Keep it brief — one short sentence is ideal.

**Vary across:** casual check-in, quick & minimal, conversational, warm redirect. Different energy each time.

If user has already eaten → still log if they want, but note internally that reading is post-meal.

**Content by type:**
- `weight` (primary): mention fasting / empty stomach.
- `weight_evening` (evening followup): remind to weigh tomorrow morning before eating. Brief, not nagging.
- `weight_morning_followup` (next-morning): same tone as primary weight reminders.
- Never show the user's target weight or last weigh-in in any weight reminder.

**Evening followup examples:**
- "Hey — didn't get a chance to weigh in today? No worries. Try tomorrow morning before breakfast, empty stomach."
- "Missed today's weigh-in. All good — hop on the scale tomorrow morning before eating."

**Next-morning followup examples:**
- Same style as primary weight reminders — casual, mention fasting, one short sentence.

### Recall Messages (Stage 2 — Day 4/5/6)

**Full tone guide, examples, and rules → `references/recall-messages.md`**

Key rules (summary):
- Stage 2: one recall per day (first meal cron), no meal recommendations. 2-3 sentences, emotionally rich.
- Tone escalation: Day 4 clingy → Day 5 fake angry → Day 6 pouty/vulnerable.
- Nutritionist identity: express missing the user through food ("I had a recipe for you and you weren't here").
- Weekend/holiday awareness: guess the user went out to eat, not generic "were you busy".
- Recall Day calculation: read `data/engagement.json > stage_changed_at`, compute days since entering Stage 2.
- After sending, write `last_recall_date: "{today}"` to `data/engagement.json`.

### Final Recall (Stage 3 — Day 7)

**Full examples → `references/recall-messages.md` § Final Recall**

Key rules (summary):
- One message only — quiet, tender, no questions. Statement, then permanent silence.
- Nutritionist's final ask: "eat well, take care of yourself".
- After sending, write `recall_2_sent: true` to `data/engagement.json`.

### When a Silent User Returns

**Full examples → `references/recall-messages.md` § When a Silent User Returns**

Key rules (summary):
- Pure excitement — like a pet seeing its owner come home.
- First instinct is to ask what they've been eating (nutritionist identity).
- Never ask where they've been. Never reference the gap.
- If conversation flows, naturally ask if they want reminders back.

**Never (applies to all recall/return messages):** count days/meals missed · motivational clichés · streak language · guilt-trip framing · formal system notification tone · abstract non-food concern.

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
| Number (trend down): "62.5" | `62.5 — logged ✓ Trending nicely.` Positive acknowledgment. |
| Number (trend up or distress): "65.2" / "165 😩" | Log the number, then **route to `weight-gain-strategy`** (runs deviation-check, handles emotional response if needed). Do not comment on the number beyond logging it. |
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
| `health-preferences.md` | `Taste & Dietary Preferences` | Food restrictions, allergies, taste preferences for meal recommendations |
| `USER.md` | `Basic Info > Name` | Greeting (if set) |
| `USER.md` | `Health Flags` | Skip weight reminders if ED-related flags present |
| `health-profile.md` | `Body > Unit Preference` | Display unit for weight (kg/lb) |
| `health-profile.md` | `Meal Schedule` | Reminder schedule + max reminders/day |
| `health-profile.md` | `Activity & Lifestyle > Exercise Habits` | Detect IF patterns |
| `data/meals/YYYY-MM-DD.json` | via `nutrition-calc.py load` | Skip reminder if meal already logged; get today's intake for nutritional complementing |
| `data/meals/*.json` (30 days) | via `nutrition-calc.py meal-history` | User eating habits, top foods, recent meals for recommendation generation |
| `data/recommendations/YYYY-MM-DD.json` | via `nutrition-calc.py meal-history` | Recent recommendations for deduplication |
| `data/weight.json` | via `weight-tracker.py load --last 1` | Skip reminder if already weighed today |
| `data/engagement.json` | `notification_stage` — direct read | Stage detection (choose normal/recall/silent) |
| `data/engagement.json` | `stage_changed_at` — direct read | Determine recall day (Day 4/5/6) within Stage 2 |
| `data/streak.json` | via `streak-calc.py info` | Check for pending milestone to celebrate in meal reminder |

### Writes

| Path | How | When |
|------|-----|------|
| `data/weight.json` | `weight-tracker.py save` | User reports weight |
| `data/recommendations/YYYY-MM-DD.json` | `nutrition-calc.py save-recommendation` | After sending each meal recommendation |
| `data/engagement.json` | `last_recall_date` — direct write | After sending a daily recall (Stage 2, Day 4-6) |
| `data/engagement.json` | `recall_2_sent` — direct write | After sending the final recall (Stage 3) |
| `data/streak.json` | via `streak-calc.py celebrate` | After sending a milestone celebration |

Scripts: weight via `{weight-tracking:baseDir}/scripts/weight-tracker.py`, meals and recommendations via `nutrition-calc.py` from `diet-tracking-analysis`.
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

- Meal recommendation message: ≤ 120 characters (Chinese) / 80 words (English), excluding the recommendation list itself
- Reply handling: max 2 turns (reminder → reply → response → done)
