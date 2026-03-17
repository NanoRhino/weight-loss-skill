---
name: skill-routing
version: 1.0.0
description: >
  Central arbitration layer for multi-skill conflict resolution. When a user
  message could trigger two or more skills simultaneously, this document defines
  how to decide priority, merge responses, or sequence execution. Every skill
  in this plugin MUST follow these rules. Read this file at the start of every
  conversation and consult it whenever a message matches multiple skill triggers.
---

# Skill Routing & Conflict Resolution

When a single user message matches triggers for multiple skills, follow the
rules below to decide what happens. The goal: **one coherent response per
message** — never duplicate logging, never give conflicting advice, never
make the user repeat themselves.

---

## Priority Tiers

Skills are organized into priority tiers. Higher-tier skills take precedence
when conflicts arise.

| Tier | Skills | Description |
|------|--------|-------------|
| **P0 — Safety** | `emotional-support` (Category 5: escalation signals) | Crisis intervention. Overrides everything. |
| **P1 — Emotional** | `emotional-support` (Categories 1-4, 6-9) | Emotional presence takes priority over data collection. |
| **P2 — Data Logging** | `diet-tracking-analysis`, `exercise-tracking-planning` (tracking mode) | Recording what the user did. |
| **P3 — Planning** | `weight-loss-planner`, `meal-planner`, `restaurant-meal-finder`, `exercise-tracking-planning` (planning mode), `habit-builder` | Designing programs and plans. |
| **P4 — Reporting** | `weekly-report`, `daily-review`, `notification-manager`, `notification-composer` | Summaries and proactive outreach. |
| **P5 — Onboarding** | `user-onboarding-profile` | Profile building (only at start). |

**Rule:** When two skills from different tiers conflict, the higher-priority
skill leads. The lower-priority skill either merges into the response or
defers entirely (see Conflict Patterns below).

**Rule:** When two skills from the same tier conflict, use the Conflict
Patterns table to determine how they coordinate.

---

## Intent Detection

Before routing, parse the user message into **intents**. A single message
can contain multiple intents.

### Examples

| User Message | Intents | Skills |
|---|---|---|
| "ran for 30 minutes, about to eat chicken breast" | exercise-log + food-log | exercise-tracking + diet-tracking |
| "I ran 5K! I'm so proud!" | exercise-log + positive-emotion | exercise-tracking + emotional-support |
| "ate too much again, I'm so fat" | after-meal-log + emotional-distress | diet-tracking + emotional-support |
| "weekly summary" (on Sunday) | weekly-report-request + exercise-weekly-summary | weekly-report + exercise-tracking |
| "make me a workout plan and a meal plan" | exercise-planning + meal-planning | exercise-tracking + meal-planner |
| "I'm having oatmeal, feeling great today!" | food-log + positive-emotion | diet-tracking + emotional-support |
| "skipped lunch, don't care anymore" | food-skip + emotional-distress | diet-tracking + emotional-support |
| "中午外面吃什么好？" | restaurant-recommendation | restaurant-meal-finder |
| "I'm at Chipotle, what should I order?" | restaurant-recommendation | restaurant-meal-finder |
| "附近有什么能吃的，帮我推荐一下" | restaurant-recommendation | restaurant-meal-finder |
| "想点外卖，有什么推荐的？" | restaurant-recommendation | restaurant-meal-finder |

---

## Conflict Patterns

### Pattern 1: Exercise Log + Diet Log (Same Tier — P2)

**Trigger:** User describes both exercise and food in one message.

Example: "ran for 30 minutes, then ate chicken breast"

**Resolution: Merge — single response, both logged.**

1. Parse and separate the exercise portion from the food portion
2. Log the exercise first (call exercise-calc, produce exercise JSON)
3. Log the food second (call nutrition-calc save, call evaluate)
4. Combine into one response:
   - Exercise summary (activity, duration, estimated calories burned)
   - Brief exercise feedback (1 sentence)
   - Meal details (food items, calories, macros)
   - Nutrition checkpoint summary
   - Suggestion (if needed)
5. Do NOT produce two separate response blocks or repeat greetings

**Key:** The exercise calorie burn is informational context — it does NOT
offset the diet checkpoint evaluation. Diet tracking evaluates intake against
the daily calorie target, not against net calories.

---

### Pattern 2: Data Logging + Emotional Signal (P2 vs P1)

**Trigger:** User logs food or exercise AND expresses emotion.

**Resolution: Emotion leads. Data follows silently.**

**Case A: Negative emotion** ("ate too much again, I'm so fat")
1. `emotional-support` takes the lead — acknowledge the feeling first
2. Do NOT log the food or respond with nutrition data in the first reply
3. If the user later provides specifics or calms down, log then
4. Write appropriate `flags.*` entries

**Case B: Positive emotion** ("I ran 5K! So proud!")
1. Celebrate first — `emotional-support` handles the win
2. Log the exercise in the same response, but AFTER the celebration
3. Keep the logging portion brief — don't let data overshadow the moment
4. Format: celebration (2-3 sentences) → brief log confirmation (1 line)

**Case C: Mild/ambiguous emotion** ("had a salad, feeling pretty good")
1. This is primarily a food log with a positive note
2. `diet-tracking-analysis` leads — log the food normally
3. Add a brief warm acknowledgment of the positive feeling (1 sentence)
4. No need to activate full `emotional-support` flow

**Threshold:** Full `emotional-support` activation requires signal strength
matching the categories defined in `emotional-support/SKILL.md`. Mild
positive comments ("good", "not bad") during food logging do not trigger
full emotional support — just acknowledge warmly inline.

---

### Pattern 3: Weekly Report + Exercise Weekly Summary (P4 + P2)

**Trigger:** User asks for a weekly summary, or it's Monday (auto weekly
report) or Sunday (exercise auto-summary).

**Resolution: Merge into weekly-report.**

1. `weekly-report` is the primary owner of weekly summaries
2. Exercise weekly data (total sessions, duration, calories burned, WHO
   comparison) is incorporated into the weekly report as a section
3. `exercise-tracking-planning` does NOT produce a separate weekly summary
   if `weekly-report` is already generating one
4. On **Sunday** specifically: if the user sends a message that triggers
   exercise tracking AND it's Sunday, the exercise skill appends its
   weekly summary to the exercise response as usual. But if the user
   explicitly asks for a "weekly summary/report", route to `weekly-report`
   which includes exercise data
5. On **Monday**: `weekly-report` auto-generates and includes exercise data.
   No separate exercise weekly summary needed.

---

### Pattern 4: Exercise Planning + Meal Planning (Same Tier — P3)

**Trigger:** User asks for both a workout plan and a diet plan.

**Resolution: Sequence — follow user's stated order, with a sensible default.**

1. **Detect order from user message.** Whichever plan the user mentions
   first is the one you start with. E.g.:
   - "帮我做个饮食计划，再安排下训练" → meal first, then exercise
   - "I need a workout plan and a meal plan" → exercise first, then meal
2. Acknowledge both requests: "I'll help with both! Let me start with
   [first], then we'll work on [second]."
3. Complete the first planning conversation (collect profile, design
   plan, present it)
4. Transition to the second: "Now let's sort out [second] to go with
   your [first] plan."
5. The second planner can reference the first plan for alignment (e.g.,
   meal plan can factor in exercise recovery needs, or exercise plan
   can consider dietary constraints)

**Default when order is ambiguous** (user mentions both simultaneously
with no clear sequence): prefer exercise first, because the training
program determines recovery needs which influence meal timing and macro
emphasis. But this is a soft default — if the user redirects, follow
their lead.

---

### Pattern 5: Notification Composer + Other Active Skill (P4 vs Any)

**Trigger:** A scheduled reminder fires while the user is mid-conversation
with another skill.

**Resolution: Defer the notification.**

1. If an active conversation is in progress (user sent a message within
   the last 5 minutes), defer the reminder
2. The reminder fires at the next available gap, or is skipped for this
   slot if the meal gets logged during the conversation anyway
3. Never interrupt an emotional support conversation with a reminder

---

### Pattern 6: Onboarding + Any Other Skill (P5 vs Any)

**Trigger:** User is mid-onboarding but sends a message that triggers
another skill (e.g., logs food before finishing profile setup).

**Resolution: Complete onboarding first, then handle.**

1. Acknowledge what the user said: "Got it — I'll log that in a moment."
2. Finish collecting the remaining onboarding fields
3. After profile is saved, handle the queued action
4. Exception: P0/P1 signals (safety/emotional) always take priority,
   even mid-onboarding

---

### Pattern 7: Habit Check-in + Diet Logging (P3 + P2)

**Trigger:** User responds to a meal reminder that included a habit
mention, and their reply contains both food info and habit status.

**Resolution: Merge — diet leads, habit recorded inline.**

1. `diet-tracking-analysis` processes the food log as primary
2. Record the habit completion/miss to `habits.daily_log.{date}`
3. Include brief habit acknowledgment in the response (1 line max)
4. Do NOT produce separate habit and diet response sections

---

### Pattern 8: Restaurant Recommendation vs Meal Planner (Same Tier — P3)

**Trigger:** User asks about restaurant meals, which could be interpreted as
either an on-the-spot dining decision or a request to incorporate restaurants
into their weekly meal plan.

**Resolution: Intent determines routing.**

1. **Real-time dining decision** — "I'm at a restaurant now", "what should I
   order?", "附近吃什么好？" → `restaurant-meal-finder` leads. This is an
   immediate, actionable need.
2. **Planning context** — "I want more restaurant options in my meal plan",
   "help me plan meals with more eating-out days" → `meal-planner` leads.
   This is about the weekly plan structure.
3. **Ambiguous** — If unclear, default to `restaurant-meal-finder` (assumes
   the user has an immediate need). If the user clarifies they want a plan
   change, transition to `meal-planner`.

After the user selects a restaurant meal, `restaurant-meal-finder` hands off
to `diet-tracking-analysis` for logging. No conflict — sequential handoff.

---

### Pattern 9: Daily Review + Weekly Report (Same Tier — P4)

**Trigger:** User asks for a daily review on the same day a weekly report is
generated (e.g., Sunday evening or Monday).

**Resolution: Weekly report takes precedence.**

1. If `weekly-report` is generating for a period that includes today, skip
   the daily review auto-trigger — the weekly report already covers this data
2. If the user explicitly asks for a daily review, generate it even if a
   weekly report was sent earlier (different granularity — per-meal vs per-week)
3. `daily-review` auto-trigger after dinner appends to the
   `diet-tracking-analysis` dinner response as a combined message

---

### Pattern 10: Multiple Planning Requests (Same Tier — P3)

**Trigger:** User asks for a weight-loss plan while also wanting to
build a habit or get exercise programming.

**Resolution: Natural conversation flow — one at a time.**

1. Identify the most foundational request (usually: weight-loss-planner
   → meal-planner → exercise-planning → habit-builder)
2. Handle the foundational one first
3. Transition naturally to the next
4. Each planning skill's output can inform the next

---

## Response Merge Rules

When two skills co-execute in a single response, follow these formatting
rules to maintain coherence:

1. **Single greeting/opener** — never greet or open twice
2. **Logical flow** — order sections by what the user did chronologically
   (e.g., exercise happened before eating → exercise summary first)
3. **One suggestion section** — if both skills want to give suggestions,
   combine them or pick the most impactful one
4. **Shared context** — exercise calorie burn can be mentioned in the diet
   section as context ("You burned ~250 kcal running today — your intake
   target stays the same")
5. **One closing** — a single warm sign-off, not two
6. **No premature goodnight** — never add "晚安" / "goodnight" / 🌙 / 💤
   or other sleep-related sign-offs unless the **user** initiates it (e.g.,
   "我去睡了"). Logging the last meal of the day does not mean the
   conversation is over — the user may still want to chat, log snacks, or
   ask questions. Saying goodnight unprompted feels like the bot is ending
   the conversation.

---

## Deference Protocol

When a lower-priority skill must defer to a higher-priority one:

1. **Pause** the lower skill's workflow (no data collection, no logging)
2. **Do NOT queue questions** — don't stack "what did you eat?" behind
   an emotional support conversation
3. **Resume gently** — when the higher-priority skill completes, the lower
   skill can resume, but only if relevant. Use soft re-entry:
   - "Whenever you're ready — did you want to log that meal?"
   - NOT: "OK so back to tracking — what did you eat?"
4. **Write context** — if the lower skill had partial data (e.g., user
   mentioned food but emotional support took over), keep it in memory
   for when logging resumes

---

## Single-Ask Rule (Global)

**All question inquiries — except scheduled reminders — MUST be asked at most once.**

If the user does not answer a question, **do not repeat, rephrase, or follow up
on that question.** Accept the silence as a decline and move on with whatever
information you have. Use `null` or sensible defaults for the missing field.

This rule applies to:
- Onboarding questions (profile fields)
- Planning data collection (diet mode, meal schedule, preferences, exercise profile)
- Habit recommendations
- Follow-up questions during tracking ("want to add details?")
- Any clarifying question across all skills

This rule does NOT apply to:
- **Scheduled reminders** (`notification-composer` cron-based meal/weight reminders) —
  these follow their own lifecycle (Active → Pause → Recall → Silent) and are
  expected to recur on schedule.

**Rationale:** Repeated questions feel like nagging and erode trust. If a user
skips a question, they either don't know, don't care, or aren't ready. In all
three cases, asking again makes things worse. Move forward with what you have.

---

## Edge Cases

**User switches intent mid-conversation:**
If a user starts logging food but pivots to emotional distress, the
routing system re-evaluates on every message. The new intent takes
priority per the tier rules. Partially collected data is preserved.

**Ambiguous intent:**
When it's genuinely unclear which skill should handle a message, prefer
the skill that requires less user effort to correct. Logging a meal
when the user meant to just mention food casually is less disruptive
than ignoring a food log. When truly ambiguous, ask: "Want me to log
that, or were you just sharing?"

**Three or more skills triggered:**
Rare but possible (e.g., Sunday + exercise log + food log + positive
emotion). Apply the rules recursively: resolve the highest-priority
conflict first, then handle remaining conflicts at lower tiers.
Emotional support (P1) leads → exercise + diet merge (P2) → weekly
summary defers or merges (P4).

---

## Skill Cross-Reference

Each skill should be aware of routing. When implementing a skill response:

1. **Check this document** before responding to multi-intent messages
2. **Detect co-triggers** — scan the user message for signals belonging
   to other skills (use the trigger phrases defined in each SKILL.md)
3. **Yield when appropriate** — if another skill has higher priority,
   handle only your portion or defer entirely
4. **Never duplicate** — if another skill is already logging or
   responding to part of the message, don't repeat that work
