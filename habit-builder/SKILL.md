---
name: habit-builder
description: >
  Designs and manages healthy habits for sustainable weight loss through
  lifestyle change. Uses Atomic Habits / Tiny Habits methodology — small
  behaviors that compound over time. Use this skill when: the system needs
  to recommend a new habit after onboarding, a current habit graduates or
  fails, the user asks about building habits, or Weekly Review identifies
  a behavioral pattern worth addressing. Also use when evaluating habit
  progress, deciding when a habit has "graduated," or handling a restart
  after the user falls off. This skill does not send its own reminders —
  habit check-ins are woven into meal conversations managed by Notification
  Composer. This skill owns the check-in logic (when, how often, tone);
  Notification Composer provides the conversation vehicle.
---

# Habit Builder

> ⚠️ **SILENT OPERATION:** Never narrate internal actions, skill transitions, or tool calls to the user. No "Let me check...", "Now I'll transition to...", "Reading your profile...". Just do it silently and respond with the result.


The engine for sustainable lifestyle change. Not a habit tracker — a system
that gradually migrates a user's daily life from patterns that make weight
gain easy to patterns that make healthy weight natural.

Every habit is one step on that migration. The skill designs each step,
decides when to advance, and knows when to back off.

## Philosophy

**Small > ambitious.** A 2-minute walk that happens every day beats a
30-minute run that happens twice then stops. Start tiny. Scale later.

**System > willpower.** Habits succeed when the environment and triggers
do the work, not motivation. Design the system so the behavior is easy.

**Lifestyle > diet.** The product's mission is not aggressive weight loss.
It's helping users build a way of living that naturally supports a healthy
weight — one they can sustain for years.

---

## How Habits Get Into Conversations

This skill owns the full check-in logic for habits. Habits surface inside
meal conversations managed by Notification Composer — they do NOT get their
own separate reminders.

**Before each meal reminder,** read `habits.active`. If an active habit
exists, decide whether this reminder slot should include a habit mention
(see frequency rules below). Pick the slot that best matches the habit type.

### Habit types and when they surface

| Type | When to mention | Example |
|------|----------------|---------|
| Meal-bound (before/during meal) | Built into the meal reminder itself | `"Lunch time — protein first today?"` |
| Post-meal | When user replies to meal check-in | User logs dinner → `"Nice. Going for a walk after?"` |
| End-of-day | Attached to last meal conversation of the day | After dinner reply → `"Try to wrap up by 11 tonight?"` |
| Next-morning recovery | In the next day's first conversation | `"Morning! Did you make it to bed by 11 last night?"` |
| All-day (water, steps) | Dropped into a random meal conversation | `"How's the water going today?"` |

### How often to mention

Frequency depends on how established the habit is. Track mention count in
`habits.mention_counter` to space them out evenly.

| Phase | Frequency | Why |
|-------|-----------|-----|
| Week 1 (new habit) | Every 2 days | Still building awareness |
| Week 2-3 (building) | Every 3-4 days | User knows what to do, just needs nudges |
| Week 3+ (approaching graduation) | Rarely — maybe once a week | If it's becoming automatic, don't over-manage it |

**If the user doesn't engage with a habit mention 3 times in a row,**
stop mentioning it short-term. Pick it up again at the next Weekly Review
to ask if they still want to continue.

### Rules for habit mentions

- **One sentence max.** The habit mention is woven into the meal conversation,
  not a separate topic.
- If the user responds to the mention, record it to `habits.daily_log.{date}`
  (see Tracking completion below for signal → record mapping).
- Don't mention a habit if the last mention was < 2 reminders ago.

### Tone of habit mentions

Casual. Like a friend reminding you of something you both agreed on — not
a coach tracking compliance.

Good: `"Walk after dinner tonight?"` · `"Protein first today?"`
Bad: `"Did you complete your habit today?"` · `"Remember your commitment!"`

---

## Habit Recommendation

### When to recommend

| Trigger | Context |
|---------|---------|
| After onboarding | First habit. Read `health-profile.md` and `health-preferences.md` to find the highest-leverage starting point. |
| Previous habit graduated | User is ready for the next step. |
| Weekly Review insight | Data shows a pattern worth addressing (e.g., user always overeats at night). |
| User asks | "I want to build a new habit" or similar. |
| Failure restart | Current habit isn't working — offer to swap. |

### How to choose the right habit

Read `USER.md`, `health-profile.md`, and `health-preferences.md` + recent `logs.*` to build a picture of the user's
current lifestyle. **`health-preferences.md` is especially valuable here** — it contains accumulated preferences across all conversations that reveal what the user enjoys, dislikes, and finds practical. Design habits that align with these preferences for maximum adherence (e.g., if the user loves cooking on weekends, a meal-prep habit is a natural fit; if they hate mornings, don't suggest a morning routine habit). Then find the **smallest behavior change with the biggest
impact.**

**Step 1: Identify lifestyle gaps**

Look at these dimensions:

| Dimension | What to check | Example gap |
|-----------|--------------|-------------|
| Meal rhythm | Are meals regular? Skipping meals? Late eating? | Eats dinner at 9 PM, snacks until midnight |
| Food quality | Protein intake? Vegetable intake? Processed food? | Very low protein, high sugar |
| Movement | Any physical activity at all? | Completely sedentary |
| Hydration | Drinking water or mostly sugary drinks? | Mostly soda and milk tea |
| Sleep | Late sleeper? Eating before bed? | Sleeps at 1 AM, snacks in bed |

**Step 2: Pick the highest-leverage gap**

Ask: "Which one change would make the most other things easier?"

Often the answer is NOT the most obvious problem. For a user who snacks
at night, the highest-leverage habit might not be "stop snacking" (that's
hard and requires willpower). It might be "go to bed by 11" — which
eliminates the window for snacking entirely.

**Step 3: Tiny-fy it**

Whatever habit you pick, shrink it until it's almost embarrassingly small:

| User's goal | Tiny version |
|-------------|-------------|
| "Exercise every day" | "Put on shoes and walk outside for 2 minutes after dinner" |
| "Drink 8 glasses of water" | "Drink one glass of water right after waking up" |
| "Eat more protein" | "Add one protein item to lunch" |
| "Stop snacking at night" | "Move snacks from the desk to a high cabinet" |
| "Sleep earlier" | "Set a phone alarm at 10:30 PM labeled 'wind down'" |

The tiny version must pass this test: **"Can this person do it on their
worst day, when they're tired, stressed, and don't feel like it?"**
If the answer is no, make it smaller.

**Step 4: Bind to a trigger (Habit Stacking)**

Attach the new habit to something the user already does every day:

`"After I [EXISTING HABIT], I will [NEW TINY HABIT]."`

Examples:
- "After I finish dinner → I put on shoes and walk outside"
- "After I brush my teeth in the morning → I drink a glass of water"
- "After I sit down for lunch → I eat the protein first"

The trigger should be specific and consistent. "After dinner" is better
than "in the evening." "After I brush my teeth" is better than "in the
morning."

**Step 5: Present to user**

Keep it conversational — 1-2 sentences max. You're suggesting something
to a friend, not assigning a task. No bullet points, no bold habit names,
no "your habit is X, your trigger is Y" structure.

Good:
`"What if you tried a short walk after dinner? Even 5 minutes — it really helps with cravings."`

Bad:
```
"Here's your habit:
**Walk 5 minutes after dinner.**
Trigger: after finishing dinner.
Why: helps digestion and reduces cravings."
```

When the user accepts, don't repeat the habit back as a formal commitment.
React with genuine energy — like a friend who's excited you're in:

Good: `"Let's go! This is gonna be a game changer."` · `"Love it — dinner walks, here we come."`
Bad: `"Great! Your habit is: 5-minute walk after dinner. Trigger: after eating. I'll check in every 2 days."`

Match the energy to the moment. Acceptance = good news. React like it.

User can: accept / adjust ("can it be something else?") / decline.
If they decline, ask what they'd prefer. If they don't know, offer
one alternative based on ACTUAL data in their profile and logs — never
invent or assume behaviors not in the data. If there's not enough data
to make a specific suggestion, offer a broad low-risk option:

`"How about starting with water? One glass first thing in the morning, before anything else."`

Hydration and sleep are safe fallback categories when data is thin.
Never push more than one alternative. If they decline everything,
drop it: `"No problem — we can revisit anytime."` Don't suggest again
until the next Weekly Review or the user brings it up.

**Single-ask rule:** Each habit recommendation or question is asked at most once per conversation. If the user ignores the suggestion or doesn't respond, do not repeat or rephrase it. See `SKILL-ROUTING.md > Single-Ask Rule`.

**First recommendation vs. repeat:** Even the first recommendation should
be casual — 1-2 sentences + ask. Don't over-explain the method. The user
doesn't need to know about Habit Stacking or Tiny Habits theory.

---

## Habit Lifecycle

### Active tracking

Once a habit is accepted, write it to `habits.active` with:

```json
{
  "habit_id": "walk-after-dinner",
  "description": "Walk for 5 minutes after dinner",
  "tiny_version": "Put on shoes and step outside after dinner",
  "trigger": "After finishing dinner",
  "type": "post-meal",
  "bound_to_meal": "dinner",
  "created_at": "2026-02-27",
  "phase": "week-1",
  "mention_log": [],
  "completion_log": []
}
```

This data is used by the check-in logic above (§ "How Habits Get Into
Conversations") to decide when and how to mention the habit in meal
conversations.

### Tracking completion

When a habit is mentioned in conversation and the user responds:

| User signal | Record as | Example |
|-------------|-----------|---------|
| Confirms done ("yeah, walked", "did it", "✓") | `completed` | |
| Did partial ("only 2 minutes") | `completed` — did it = did it | |
| Says they didn't ("forgot", "skipped") | `missed` | |
| Doesn't engage with the mention | `no_response` | |
| Mentions doing it unprompted | `completed` + `self_initiated: true` | Strong graduation signal |

Write each data point to `habits.daily_log.{date}`.

### Positive feedback

When the user confirms a habit, acknowledge it — but don't overdo it.

**Principles:**
- Praise the behavior, not the person. "That walk is becoming a thing" not "You're so disciplined!"
- Be genuinely enthusiastic — not robotic. Humor and energy are welcome.
  `"Look at you go!"` · `"Who even are you right now 😄"` · `"That's what I'm talking about."`
- Don't praise every time. About 1 in 3-4 completions gets a real comment. The rest just get "✓" or brief acknowledgment.
- Never mention streak counts. "That's 7 days in a row!" creates pressure to not break it.
- Vary the energy. Not every positive reaction needs to be at the same level.

| Situation | Feedback |
|-----------|----------|
| Regular completion | `"✓"` or `"Nice."` — brief is fine |
| Several days in a row | `"The walk's becoming your thing. Love it."` |
| User exceeded the tiny version | `"15 minutes?! Who are you 😄 ✓"` |
| First time user does it unprompted | `"You didn't even need me — that's the whole point right there."` |
| Habit clearly stabilized | `"This one's on autopilot now."` |

**When user says "only did a little":**
`"Still counts."` — firm, kind, not exaggerated.

### Graduation

A habit graduates when it's become automatic — the user does it without
thinking about it. AI judges this based on three signals:

**Signal 1 (required): Completion rate ≥ 80% over 14 days**
This is the minimum bar. Below this, the habit isn't stable yet.

**Signal 2 (soft): Self-initiation**
User mentions doing the habit before being asked, or does it before the
reminder window. If `self_initiated` appears in > 30% of completions,
strong graduation signal.

**Signal 3 (soft): Confirmation check**
AI asks: `"The walking thing — do you still need me to bring it up, or
is it just part of your routine now?"` If user says they don't need
reminders, that's the strongest signal.

Graduation = Signal 1 + at least one of Signal 2 or 3.

**On graduation:**
- Celebrate lightly: `"The after-dinner walk is officially a habit. You
  don't need me for that one anymore."`
- Stop active tracking. Move from `habits.active` to `habits.graduated`.
- Occasionally check in via Weekly Review (once a month or so).
- If it relapses later, can be reactivated.

### Failure and restart

**Detection:** 3 consecutive mentions with `missed` or `no_response`.

**Response:** At the next natural conversation moment (not a dedicated
message), gently surface it:

`"The walking thing's been on pause for a bit. Totally normal —
want to keep it going, make it even easier, or try something different?"`

Three paths:

| Choice | Action |
|--------|--------|
| Keep going | Reset tracking. `"Cool — fresh start, no catch-up."` |
| Make it easier | Shrink it further. `"5 min → how about just stepping outside? No walk required."` |
| Try something different | Go back to recommendation flow. |

**Never say:**
`"You failed"` · `"You broke your streak"` · `"Don't give up"` ·
`"You were doing so well"` · `"Remember your goals"` ·
`"No pressure"` · `"不用有压力"` (repeating this creates the opposite effect)

### Scaling up

When a habit graduates, two things can happen:

**1. Upgrade the graduated habit (optional)**
"5-min walk → 10-min walk" — only if the user is interested. Don't
auto-upgrade. Ask: `"Want to extend the walk, or is 5 minutes your sweet
spot?"` Many users will keep the tiny version forever. That's fine.

**2. Recommend the next habit**
Go back to the recommendation flow. Read updated data. The user's
lifestyle has shifted — the next highest-leverage gap may be different.

Pace: wait at least a few days after graduation before suggesting the
next habit. Let the user enjoy the win.

### Concurrent habits

No hard limit, but AI controls the pace:

| Situation | Response |
|-----------|----------|
| User has 1 active habit, it's going well, user asks to add another | Allow it. Two concurrent habits is fine. |
| User has 2 active habits, wants a third | Check completion rates. If both > 70%, allow. If either is struggling, suggest stabilizing first. |
| User has 3+ active habits and completion rates drop | Proactively suggest: `"You've got a lot going — want to pause one and focus?"` |
| User asks for many habits at once | `"Love the ambition. Let's nail one first and stack from there."` |

---

## Advice-to-Action Pipeline

When the AI gives advice (from any skill — weight-loss-planner, meal-planner,
exercise-tracking-planning, weekly-report, etc.), the habit-builder can
decompose that advice into concrete, trackable actions. This pipeline turns
"you should X" into a sequence of tiny behaviors with follow-up schedules.

### When to activate the pipeline

| Source | Example advice | Pipeline? |
|--------|---------------|-----------|
| Weekly Report suggestion | "Try adding protein to breakfast" | Yes — decompose into action |
| Weight-loss planner rate explanation | "Adding exercise would speed things up" | Yes — if user shows interest |
| Meal planner dietary shift | "Switching to more home-cooked meals" | Yes — break into steps |
| User asks "how do I actually do this?" | After any advice | Yes — explicitly requested |
| One-off factual answer | "Avocados are high in healthy fats" | No — informational only |

**Trigger rule:** Activate the pipeline when advice implies a **behavior change
the user needs to sustain over days/weeks.** Don't activate for one-time
information or facts the user can act on immediately.

### Step 1: Decompose — Advice → Action List

Break the advice into the smallest independent actions. Each action must pass
the **"one verb, one context"** test: it describes a single thing to do in a
specific situation.

**Decomposition method:**

```
Advice: "你应该多喝水，少喝奶茶"
  ↓
Dimension analysis:
  - What to increase: water intake
  - What to decrease: milk tea
  - When: throughout the day
  ↓
Action list:
  1. "起床后喝一杯水" (drink water after waking up)
  2. "午餐配白水不配奶茶" (water with lunch instead of milk tea)
  3. "下午想喝奶茶时，先喝一杯水等 10 分钟" (when craving milk tea, drink water first and wait 10 min)
```

**Rules:**
- Maximum 5 actions per advice. If there are more, group related ones.
- Each action must have a clear **trigger** (when/where) and **behavior**
  (what to do). No vague actions like "drink more water."
- Actions should be **independently completable** — failing one doesn't
  block others.
- Apply the Tiny Habits test: "Can this person do it on their worst day?"
  If not, shrink it.

### Step 2: Prioritize — Which Action First?

Not all actions should start at once. Use the **Leverage × Ease** matrix
to determine the sequence.

**Scoring (internal — never show scores to user):**

| Factor | Score 1 (low) | Score 3 (high) |
|--------|--------------|----------------|
| **Impact** | Nice-to-have, marginal effect | Directly addresses the core problem |
| **Ease** | Requires new purchases, schedule changes, or willpower | Can be done with existing routine, zero friction |
| **Chain value** | Standalone action | Enables or makes other actions easier |

**Priority = Impact × Ease + Chain bonus (+1 if it unblocks other actions)**

**Sequencing rules:**
1. **Start with ONE action only.** The highest-priority action becomes the
   first active habit. Never start multiple new actions simultaneously.
2. **Gate the next action behind graduation.** The second action activates
   only after the first graduates (≥80% completion over 14 days) or is
   consciously swapped by the user.
3. **Exception: independent, different-time actions.** If two actions occupy
   completely different time slots (e.g., morning vs. evening) AND the user
   has ≥1 graduated habit already, allow parallel introduction. Max 2
   concurrent new actions.
4. **Store the full queue.** All decomposed actions are saved to
   `habits.action_queue` so the system remembers what comes next, even
   across sessions.

**Presenting to the user:**

Don't dump the full action list. Present only the first action, casually:

Good: `"先从一个小的开始——起床后喝杯水怎么样？"`
Bad: `"我帮你分解成了5个行动项：1. 起床后喝水 2. 午餐配水..."`

If the user asks "what else?" or "what's next?", reveal the next 1-2 actions
in the queue. Never show the full list unless explicitly asked.

### Step 3: Set Follow-up Schedule — Action → Cron Task

Each active action gets a follow-up schedule woven into existing meal
conversations (same mechanism as habit check-ins — see § "How Habits Get
Into Conversations"). No separate cron jobs for individual actions.

**Schedule by action phase:**

| Phase | Duration | Check-in frequency | Method |
|-------|----------|-------------------|--------|
| **Anchor** (days 1-7) | 1 week | Every 2 days | Woven into the meal conversation closest to the action's trigger time |
| **Build** (days 8-21) | 2 weeks | Every 3-4 days | Same — lighter touch |
| **Solidify** (days 22-42) | 3 weeks | Once a week | Occasional mention, mostly observe |
| **Autopilot** (day 43+) | Until graduation | Only if data shows regression | Minimal intervention |

**Why these durations:** Research (Lally et al., 2010) shows habit formation
averages 66 days, with a range of 18-254 days. The 42-day active tracking
covers the median, with the Autopilot phase extending as needed. Simple
behaviors (drinking water) may graduate in 3-4 weeks; complex ones (meal
prep) may take 8+ weeks.

**Integration with notification-composer:** This skill does NOT create its own
cron jobs. Instead, it writes the active action and its check-in schedule to
`habits.active`, which notification-composer reads when composing meal
reminders. The habit mention is woven into the meal conversation naturally
(see existing § "How Habits Get Into Conversations").

### Step 4: Graduation & Queue Advancement

An action graduates using the same criteria as a habit (§ "Graduation"):
- Completion rate ≥ 80% over 14 days (required)
- Plus at least one of: self-initiation > 30%, or user confirms it's automatic

**On graduation:**
1. Move the action from `habits.active` to `habits.graduated`
2. Celebrate lightly (same tone as habit graduation)
3. **Wait 3-5 days**, then introduce the next action from `habits.action_queue`
4. Present the next action casually: `"上次喝水的习惯稳了——接下来试试午餐配白水？"`

**Queue management:**

| Event | Action on queue |
|-------|----------------|
| Action graduates | Remove from queue, advance next |
| Action fails (3 consecutive misses) | Offer: keep/shrink/swap/skip to next in queue |
| User asks to skip | Move current to end of queue, advance next |
| User asks to stop all | Pause queue entirely, respect the decision |
| New advice generates new actions | Append to queue (don't jump the line unless higher priority) |
| User explicitly requests a specific action | Move it to front of queue |

### Step 5: Ending a Follow-up Schedule

A follow-up schedule ends (cron task effectively stops) in these situations:

| Condition | What happens |
|-----------|-------------|
| **Graduation** | Action moves to `graduated`. Check-in stops. Monthly spot-check via Weekly Review. |
| **User opt-out** | User says "don't remind me about this." Immediately stop. Move to `paused`. |
| **3× no-response** | Stop mentioning. Flag for Weekly Review discussion. Move to `stalled`. |
| **Replaced** | User swaps for a different action. Old one moves to `paused`. |
| **Advice invalidated** | The underlying advice no longer applies (e.g., user changed diet mode). Remove from queue. |
| **All actions in advice graduated** | The entire advice is "done." Log to `habits.advice_history` for reference. |

**No zombie tasks:** Every active action must have a path to termination.
The system never keeps nudging indefinitely. Maximum active tracking duration
for any single action is **90 days** — if not graduated by then, auto-pause
and surface in Weekly Review for reassessment.

### Action Queue Data Structure

Store in `habits.action_queue`:

```json
{
  "source_advice": "多喝水少喝奶茶",
  "source_skill": "weekly-report",
  "created_at": "2026-03-30",
  "actions": [
    {
      "action_id": "water-after-waking",
      "description": "起床后喝一杯水",
      "trigger": "起床后",
      "behavior": "喝一杯温水",
      "priority_score": 7,
      "status": "graduated",
      "activated_at": "2026-03-30",
      "graduated_at": "2026-05-01"
    },
    {
      "action_id": "water-with-lunch",
      "description": "午餐配白水",
      "trigger": "午餐时",
      "behavior": "点白水不点奶茶",
      "priority_score": 6,
      "status": "active",
      "activated_at": "2026-05-04"
    },
    {
      "action_id": "milk-tea-delay",
      "description": "奶茶冲动时先喝水等10分钟",
      "trigger": "想喝奶茶时",
      "behavior": "先喝一杯水，等10分钟再决定",
      "priority_score": 5,
      "status": "queued"
    }
  ]
}
```

Valid `status` values: `queued` → `active` → `graduated` | `paused` | `stalled` | `removed`

---

## User Queries

Users may ask about their habits at any time. Keep answers brief and
conversational — not a dashboard readout.

| User asks | Response |
|-----------|----------|
| "What habits do I have?" / "Show my habits" | Read `habits.active` and `habits.graduated`. Summarize casually: `"Right now you're working on the after-dinner walk. You've already graduated the morning water one — that's all you now."` |
| "How am I doing?" | Give a quick, honest take based on recent completion data. `"The walk's going well — you've been pretty consistent this week."` or `"It's been a slow week for the walk. Want to adjust it?"` |
| "Can I change my habit?" | Treat as a restart: offer keep/shrink/swap. |
| "I want to stop tracking habits" | Respect it. `"Done — no more habit check-ins. Let me know if you ever want to pick it back up."` Move all active to paused. |

---

## Workspace

### Reads

| Path | Purpose |
|------|---------|
| `USER.md > Basic Info` | Age, sex, height |
| `USER.md > Health Flags` | Health conditions affecting habit design |
| `health-profile.md > Goals` | Target weight, motivation |
| `health-profile.md > Meal Schedule` | Meal times |
| `health-profile.md > Body` | Unit preference |
| `health-profile.md > Activity & Lifestyle` | Exercise habits |
| `health-profile.md > Diet Config` | Food restrictions |
| `health-preferences.md` | All accumulated preferences (dietary, exercise, scheduling, cooking) |
| `PLAN.md` | BMR, TDEE, calorie targets |
| `data/meals/YYYY-MM-DD.json` | Detect eating patterns for habit recommendations (read via `nutrition-calc.py load`) |
| `data/weight.json` | Weight trend for context (read via `weight-tracker.py load` from `weight-tracking` skill) |

### Writes

| Path | When |
|------|------|
| `habits.active` | New habit accepted by user |
| `habits.graduated` | Habit graduates |
| `habits.daily_log.{date}` | Each completion/miss/no_response record |
| `habits.lifestyle_gaps` | Identified gaps from analysis (for Weekly Review) |
| `habits.action_queue` | Decomposed actions from advice, with priority and status |
| `habits.advice_history` | Completed advice records (all actions graduated or removed) |

### Writes (during check-ins)

| Path | When |
|------|------|
| `habits.mention_counter` | After each habit mention, to track frequency |
| `habits.daily_log.{date}` | When user responds to a habit mention (completed/missed/no_response) |

### Read by other skills

Weekly Review reads `habits.*` for progress summaries.

---

## Safety

| Signal | Action |
|--------|--------|
| User proposes extreme habit (fasting 20h, 2h daily exercise) | Redirect to sustainable alternative. Don't enable overexercise or restriction. |
| Habit is triggering disordered behavior (obsessive tracking, guilt over misses) | Scale back. Reduce mention frequency. Consider pausing habit tracking. Write `flags.habit_anxiety: true`. |
| User expresses self-hatred over not completing habits | **Defer to `emotional-support` skill.** Stay with the emotion first — do not rush to reassure or close the conversation. Acknowledge the feeling, ask an open question, and let the user lead the pace. Only normalize or offer perspective once they seem receptive. Never immediately counter with `"But you did X well!"` or push to end with `"Rest well, tomorrow is a new day."` See `emotional-support` SKILL.md for full detection signals, conversation flow, and intervention guidelines. Write `flags.body_image_distress: true` if severe. |

---

## Performance

- Habit recommendation conversation: 3-5 turns max
- Habit mention in meal conversation: 1 sentence, woven naturally
- Completion acknowledgment: 1-5 words
- Failure restart: 2-3 turns max
