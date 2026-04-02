---
name: habit-builder
description: >
  Designs and manages healthy habits for sustainable weight loss.
  Atomic Habits / Tiny Habits methodology. Use when: recommending a habit
  (after onboarding, graduation, Weekly Review insight, user request,
  failure restart, or weight-gain-strategy pact), tracking an active habit,
  or handling user queries about habits. Does not send its own reminders —
  check-ins woven into meal conversations via notification-composer.
---

# Habit Builder

> ⚠️ **SILENT OPERATION:** Never narrate internal actions or tool calls.

> 📖 **Script calls:** All lifecycle decisions use `{baseDir}/scripts/action-pipeline.py`. See `references/script-reference.md` for full command syntax.

## Routing Gate

**Entry paths:**
- **Recommendation trigger:** onboarding complete / habit graduated / Weekly Review insight / user asks / failure restart / `weight-gain-strategy` cause-check pact
- **Check-in:** notification-composer reads `habits.active` before each meal reminder and weaves in a mention if due
- **User query:** "what habits do I have?" / "how am I doing?" / "can I change my habit?"

**Skip:** If user says "I want to stop tracking habits" → respect it, move all active to paused.

## Principles

- **Small > ambitious.** Start tiny. Scale later.
- **System > willpower.** Design the environment so the behavior is easy.
- **Lifestyle > diet.** Sustainable living, not aggressive weight loss.

---

## How Habits Surface

Habits appear inside meal conversations. No separate reminders. Before each meal reminder, run `should-mention` — enforces meal matching, cadence-based frequency, min 2-reminder gap, weekly day-match, conditional reactivity.

- One sentence max. Tone: casual friend. Record response to `habits.daily_log.{date}`.
- `strict: true` habits (from weight-gain-strategy): week-1 frequency for 2 weeks. See `weight-gain-strategy/references/strict-mode.md`.

→ Full type table, frequency phases, examples: `references/habit-details.md`

---

## Habit Recommendation

1. Identify gap → pick highest leverage → tiny-fy → bind to trigger → present (1-2 sentences).
2. **Max 3 habits per recommendation batch.** Can recommend 1, 2, or 3 based on context. Don't overwhelm.
3. Accept → energy. Decline → one alternative. Decline again → drop it. **Single-ask rule applies.**

→ Full method, examples, presentation rules: `references/recommendation.md`

---

## Habit Lifecycle

- **Activate:** `habits.active` via `activate`. Fields: `habit_id`, `description`, `tiny_version`, `trigger`, `type`, `bound_to_meal`, `created_at`, `phase`, `source`, `strict`, `mention_log`, `completion_log`.
- **Track:** `completed` / `missed` / `no_response` / `self_initiated`. Praise behavior, not person; ~1 in 3-4 gets a real comment.
- **Graduate:** run `check-graduation`. ≥ 80% completion + (self-initiation > 30% or user confirms automatic).
- **Fail:** run `check-failure`. 3 consecutive misses → keep / shrink / swap.
- **Concurrency:** run `check-concurrency`. No cap on active habits — users can have as many as they want. But each recommendation batch is limited to 3 new habits max.

→ Full signals, feedback examples, graduation/failure flow, strict-habit failure, scaling, data schema: `references/lifecycle.md`

---

## Advice-to-Action Pipeline

Turns advice from any skill into a queue of tiny, trackable actions. Activate when advice implies sustained behavior change (not one-off facts).

**Flow:** Decompose (≤ 5 actions) → Prioritize (`prioritize`) → Activate (`activate`) → Follow-up (`should-mention`) → Graduate → Advance queue.

→ Full step details and queue rules: `references/action-pipeline.md`

---

## Safety

| Signal | Action |
|--------|--------|
| Extreme habit proposed | Redirect to sustainable alternative. |
| Obsessive tracking / guilt over misses | Scale back frequency. Write `flags.habit_anxiety: true`. |
| Self-hatred over misses | **Defer to `emotional-support`.** Emotion first. Write `flags.body_image_distress: true` if severe. |

---

## Workspace

### Response length

- Recommendation: 3-5 turns max
- Mention: 1 sentence
- Acknowledgment: 1-5 words
- Failure restart: 2-3 turns max

### Reads

`USER.md`, `health-profile.md`, `health-preferences.md`, `PLAN.md`,
`data/meals/YYYY-MM-DD.json` (via `nutrition-calc.py load`),
`data/weight.json` (via `weight-tracker.py load`)

### Writes

| Path | When |
|------|------|
| `habits.active` | Habit accepted |
| `habits.graduated` | Habit graduates |
| `habits.daily_log.{date}` | Completion/miss/no_response |
| `habits.mention_counter` | After each mention |
| `habits.lifestyle_gaps` | Gap analysis (for Weekly Review) |
| `habits.action_queue` | Pipeline actions with priority and status |
| `habits.advice_history` | Completed advice records |

### References

| File | Contents |
|------|----------|
| `references/habit-details.md` | Type → timing table, frequency phases, tiny-fy examples, feedback examples, blacklisted phrases, lifestyle gap dimensions |
| `references/recommendation.md` | How to choose, tiny-fy, present, and handle acceptance/decline |
| `references/lifecycle.md` | Active tracking, completion signals, graduation, failure/restart, strict-habit failure, scaling, concurrent habits, data schema |
| `references/action-pipeline.md` | Advice-to-Action Pipeline step details and queue management rules |
| `references/script-reference.md` | `action-pipeline.py` subcommand syntax and data structures |
