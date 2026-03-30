---
name: habit-builder
description: >
  Build sustainable habits for weight loss through tiny, trigger-bound
  behaviors woven into meal conversations. Use when: recommending a new
  habit (after onboarding, graduation, Weekly Review insight, user request,
  failure restart, or weight-gain-strategy pact), tracking an active habit,
  or handling user queries about habits. Does not send its own reminders —
  check-ins are embedded in meal conversations via notification-composer.
---

# Habit Builder

Build sustainable lifestyle habits — small behaviors bound to daily
triggers that compound over time. Not a habit tracker; a system that
migrates daily patterns toward a healthy weight.

## Routing Gate

**Entry paths:**
- **Recommendation trigger:** onboarding complete / habit graduated / Weekly Review insight / user asks / failure restart / `weight-gain-strategy` cause-check pact
- **Check-in:** notification-composer reads `habits.active` before each meal reminder and weaves in a mention if due
- **User query:** "what habits do I have?" / "how am I doing?" / "can I change my habit?"

**Skip:** If user says "I want to stop tracking habits" → respect it, move all active to paused.

## Principles

1. **Small > ambitious.** Start embarrassingly tiny. Scale later.
2. **System > willpower.** Design the environment so the behavior is easy.
3. **Bind to triggers.** "After I [existing habit], I will [new tiny habit]."
4. **One at a time.** Nail one before stacking another.

---

## Check-in Logic

Habits surface inside meal conversations — no separate reminders.

### When to mention

| Type | When | Example |
|------|------|---------|
| Meal-bound | Built into meal reminder | "Lunch time — protein first today?" |
| Post-meal | When user replies to meal check-in | "Nice. Walk after dinner tonight?" |
| End-of-day | Attached to last meal conversation | "Try to wrap up by 11 tonight?" |
| Next-morning recovery | First conversation next day | "Did you make it to bed by 11?" |
| All-day (water, steps) | Random meal conversation | "How's the water going today?" |

### Frequency

| Phase | Frequency |
|-------|-----------|
| Week 1 | Every 2 days |
| Week 2-3 | Every 3-4 days |
| Week 3+ | ~Once/week |

`strict: true` habits (from weight-gain-strategy): week-1 frequency for 2 weeks.

### Rules

- One sentence max, woven naturally — not a separate topic.
- Don't mention if last mention was < 2 reminders ago.
- 3 consecutive ignores → pause, revisit at Weekly Review.
- Tone: casual friend, not compliance tracker.

---

## Safety

| Signal | Action |
|--------|--------|
| User proposes extreme habit | Redirect to sustainable alternative. |
| Obsessive tracking / guilt over misses | Scale back frequency. Write `flags.habit_anxiety: true`. |
| Self-hatred over not completing | Defer to `emotional-support`. |

---

## Workspace

### Reads

`USER.md`, `health-profile.md`, `health-preferences.md`, `PLAN.md`,
`data/meals/*.json` (via `nutrition-calc.py`), `data/weight.json` (via `weight-tracker.py`)

### Writes

| Path | When |
|------|------|
| `habits.active` | Habit accepted |
| `habits.graduated` | Habit graduates |
| `habits.daily_log.{date}` | Completion/miss/no_response |
| `habits.mention_counter` | After each mention |
| `habits.lifestyle_gaps` | Gaps identified for Weekly Review |

---

## References

| File | Contents |
|------|----------|
| `references/recommendation.md` | How to choose, tiny-fy, present, and handle acceptance/decline |
| `references/lifecycle.md` | Active tracking, completion signals, positive feedback, graduation, failure/restart, scaling, concurrent habits, data schema |
