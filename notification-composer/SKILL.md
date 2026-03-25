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

## Preference-Aware Behavior

Before composing any meal reminder or check-in response, read
`data/preference-tuning.json` (if it exists). Two fields affect this skill's
behavior:

### Supervision Level (`defaults.supervision_level`)

Supervision level controls **how strictly `diet-tracking-analysis` treats
calorie overages** — it does NOT change reminder style or format in this skill.
Meal reminders look the same regardless of supervision level.

This skill only needs to know the supervision level for the **Day 3 nudge**
(to know whether it has been sent). The actual behavioral changes live in
`diet-tracking-analysis`.

### Week 1 Nudges (Preference Discovery)

During `phase: "week1"`, check the `nudges` array for a nudge that is:
- `status: "pending"`
- `scheduled_day` <= (today - `onboarding_start` + 1)

If a qualifying nudge exists:

1. **`reminder_offset`** and **`open_feedback`** nudges: Append the nudge text
   (from `preference-tuning` SKILL.md templates) after the meal reminder,
   separated by `---`. Only on the **first meal reminder** of the day.
2. **`supervision_level`** nudge: Append the nudge text after the **first
   check-in response** (when user logs a meal) of the day, separated by `---`.
   This nudge does NOT go on a reminder — it goes on a reply.

After appending a nudge, update its status to `"sent_awaiting_reply"` and
set `sent_date` to today in `data/preference-tuning.json`.

If the user replies with a preference choice, hand off to `preference-tuning`
skill for processing (update JSON + trigger downstream changes). Then mark
the nudge `"answered"`.

If the user's next message ignores the nudge (e.g., just logs food), mark the
nudge `"sent_no_reply"` and move on. Never re-ask per the Single-Ask Rule.

When all nudges have been sent and 1 day has passed, set `phase` to `"settled"`.

---

## Pre-send Checks (MANDATORY — run before every reminder)

**Every reminder MUST run the pre-send-check script FIRST. If it returns `NO_REPLY`, your entire response must be exactly `NO_REPLY` — stop immediately, do not compose a message, do not output anything else.**

> ⚠️ **CRITICAL:** Any text you output WILL be delivered to the user. `NO_REPLY` is the only way to suppress delivery. No explanations, no reasoning, no "check failed" messages.

### Step 1: Run the script

```bash
python3 {baseDir}/scripts/pre-send-check.py \
  --workspace-dir {workspaceDir} \
  --meal-type <breakfast|lunch|dinner|meal_1|meal_2|weight> \
  --tz-offset {tz_offset}
```

Read `timezone.json` to get `tz_offset` (seconds from UTC), then run the script with the correct `--meal-type` for this reminder.

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
6. Weight already logged today? (via `data/weight.json`, weight reminders only)

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
5. Compose 2-3 meal recommendations (see Composition Rules below).
6. After sending, call `nutrition-calc.py save-recommendation --data-dir {workspaceDir}/data/meals --meal-type {current_meal} --items '{JSON array of recommendation strings}' --tz-offset {tz_offset}` to record what was recommended.

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
- Nutritional complement to earlier meals today ("早上碳水少了，补一点")
- Habit acknowledgment ("你的经典搭配，稳")
- Variety ("换换口味")
- Situational ("今天想轻一点的话")

**Deduplication — avoid repetitive recommendations:**
- Read `recent_recommendations` from `meal-history` output.
- Of the 2-3 options, at least 2 must differ from yesterday's `items` for the same meal type.
- Among the 2-3 options themselves, ensure variety: ideally one familiar favorite, one variation on a favorite, one different choice.
- If the user picked the same recommendation 3+ days in a row, don't force a change — respect their preference.

**Closing line:** Always end with an invitation to photograph the meal. Examples:
- `"吃之前拍给我，现场帮你看~"`
- `"Snap a photo before you eat — I'll check it out for you~"`

Adapt the closing to the user's language.

#### Message Format

```
{opening line — optional, 1 sentence max}

1. {food combo} — {short tip}
2. {food combo} — {short tip}
3. {food combo} — {short tip}

{closing — photo invitation}
```

The opening line is optional — use it for context when relevant (time of day, callback to yesterday, etc.), skip it when it adds nothing.

#### Examples

**Chinese (lunch):**
```
午餐想好了吗？

1. 鸡胸肉 + 糙米 + 西兰花 — 你的经典搭配，稳
2. 牛肉面 + 茶叶蛋 — 换换口味，蛋白质也够
3. 沙拉 + 全麦面包 + 酸奶 — 今天想轻一点的话

吃之前拍给我，现场帮你看~
```

**English (breakfast):**
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

### Weight Reminders — always optional framing, always mention fasting

**Style:** Casual, low-key, matter-of-fact. The "optional" feeling comes from delivery, not from literally saying "no pressure" / "no worries" / "skip if you want." Never stack reassurance phrases. Never playful tone for weight.

**Must include:** mention fasting (before eating) for accuracy. Keep it brief — one short sentence is ideal.

**Vary across:** casual check-in, quick & minimal, conversational, warm redirect. Different energy each time.

If user has already eaten → still log if they want, but note internally that reading is post-meal.

### Weight Reminder Rules

- **Mon & Thu only.** Max 2x/week. Always framed as optional.
- Reminder time = breakfast time from `health-profile.md > Meal Schedule` minus 30 min. Always remind user to weigh **on an empty stomach** (before eating). If user has already eaten, still accept the reading but tag it internally as `fasting: false`.
- If `Health Flags` contains `avoid_weight_focus` or `history_of_ed` → never send.
- Never show the user's target weight or last weigh-in in the reminder message.
- Check whether user already weighed today: call `weight-tracker.py load --data-dir {workspaceDir}/data --display-unit <unit from health-profile.md> --last 1` and check if the last entry is from today. If so, skip.

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
| `data/meals/YYYY-MM-DD.json` | via `nutrition-calc.py load` | Skip reminder if meal already logged; get today's intake for nutritional complementing |
| `data/meals/*.json` (30 days) | via `nutrition-calc.py meal-history` | User eating habits, top foods, recent meals for recommendation generation |
| `data/recommendations/YYYY-MM-DD.json` | via `nutrition-calc.py meal-history` | Recent recommendations for deduplication |
| `data/weight.json` | via `weight-tracker.py load --last 1` | Skip reminder if already weighed today |
| `data/engagement.json` | `notification_stage` — direct read | Stage detection (choose normal/recall/silent) |
| `data/engagement.json` | `last_interaction` — direct read | Stage detection |
| `data/preference-tuning.json` | `phase`, `nudges` — direct read | Week 1 nudge delivery |

### Writes

| Path | How | When |
|------|-----|------|
| `data/weight.json` | `weight-tracker.py save` | User reports weight |
| `data/recommendations/YYYY-MM-DD.json` | `nutrition-calc.py save-recommendation` | After sending each meal recommendation |
| `data/preference-tuning.json` | `nudges[].status`, `nudges[].sent_date` — direct write | After appending a nudge to a reminder/reply |

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
