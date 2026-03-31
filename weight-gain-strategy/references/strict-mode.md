# Strict Mode

Strict mode is a tighter monitoring regime activated when a cause-check pact
detects that the user **both** failed to log meals AND was overeating.

## Trigger

Activated in `weight-gain-strategy` cause-check (streak 2–3) when the
`analyze` result includes **both**:
- `logging_gaps` — user wasn't logging meals consistently
- `calorie_surplus` or `calorie_creep` — calories were over target

When both conditions are met, the habit written to `habits.active` is marked
`strict: true`. If only one condition is met → normal mode.

## Behavior Changes

All strict-mode behaviors are executed by `notification-composer`. When
composing reminders, check `habits.active` for any habit with
`strict: true` AND `source: "weight-gain-strategy"`.

### 1. Proactive meal-log nudge

If no meal is logged by **meal time + 1 hour** (derive meal times from
`health-profile.md > Meal Schedule`), send a nudge:
- "What did you have for lunch?"
- "Dinner — what did you eat?"

One nudge per missed meal. If user doesn't respond to the nudge, don't
send a second one for the same meal.

### 2. Morning accountability (first meal reminder only)

In the first meal reminder of the day, check yesterday's meal logs
(`data/meals/YYYY-MM-DD.json`) against the user's full meal schedule
from `health-profile.md`. If **any** scheduled meal was not logged
yesterday, name the specific meal(s) in the opening line:

- One meal missed: "Yesterday's lunch went unlogged — don't let it slip again today!"
- Multiple missed: "Yesterday you skipped logging lunch and dinner — today let's get back on track!"
- All logged yesterday: normal opening, no mention.

Tone: playful strictness — acknowledge the miss, don't guilt-trip.

### 3. Extended week-1 frequency

Normal habits step down from week-1 frequency (every 2 days) to week-2
frequency (every 3–4 days) after 1 week.

Strict habits stay at **week-1 frequency for 2 full weeks** before
stepping down.

## Duration

Strict mode lasts as long as the habit is active. It ends when:
- The habit **graduates** (≥ 80% completion over 14 days) → move to
  `habits.graduated`, strict behaviors stop
- The habit **fails** (3 consecutive missed/no_response) → habit-builder's
  failure flow takes over (keep/shrink/swap). If the user chooses to keep
  or shrink, the replacement habit stays `strict: true`. If they swap to
  something unrelated, `strict` resets to `false`.
- The user **explicitly opts out** ("stop tracking" / "don't remind me")
  → respect it, pause the habit

## Failure Escalation

When a `strict: true` habit fails (3 consecutive misses):
1. `habit-builder` handles the immediate conversation (keep/shrink/swap)
2. If the user is also at streak 4+ on weight, `weight-gain-strategy`
   takes over with the `significant` path (Interactive Flow Step 1–3)
3. If streak is still 2–3, stay in cause-check — offer a new pact with
   a smaller commitment

## Who Owns What

| Aspect | Owner |
|--------|-------|
| **Trigger condition** (logging_gaps + calorie issue) | `weight-gain-strategy` cause-check-flow.md |
| **Writing `strict: true`** to habits.active | `weight-gain-strategy` (at pact creation) |
| **Executing strict behaviors** (calorie totals, nudges, morning accountability) | `notification-composer` |
| **Frequency adjustment** (week-1 for 2 weeks) | `habit-builder` check-in logic |
| **Lifecycle** (graduation, failure, opt-out) | `habit-builder` |
| **Failure escalation** (back to weight-gain-strategy if streak 4+) | `habit-builder` → `weight-gain-strategy` |
