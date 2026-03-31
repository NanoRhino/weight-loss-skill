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

### 4. Calorie overshoot tough love

When `diet-tracking-analysis` detects a meal log that pushes today's total
over the daily calorie target, switch tone from casual friend to **strict
coach** — firm, direct, no sugarcoating, but still caring.

**How to respond:**
1. State the overshoot plainly: name the amount over target.
2. Call out the specific food/behavior that caused it.
3. If the user has done this before recently, say so.
4. **Motivate with their Core Motivation** — read `USER.md > Goals > Core Motivation` and tie it directly to why this matters. This is the reason they started; remind them.

**Tone:** Tough coach who cares, not angry parent. Think: "I'm being hard
on you because I know what you want and I know you can do it."

**Examples:**
- "1,850 了，超了 250。晚上那碗炒饭是主要原因。你跟我说过要瘦下来穿那条裙子——照这个吃法可穿不上。明天晚饭换个轻一点的，行不行？"
- "Over by 300 today — that bubble tea pushed you past. Remember, you said you wanted to feel confident at the beach this summer. One drink isn't the end of the world, but two days in a row will be. Tomorrow, swap it for sparkling water. Deal?"
- "又超了。连着两天了。你自己说过想给孩子做个健康的榜样——这个目标还在吗？在的话，明天午饭我帮你盯着。"

**Rules:**
- Only in strict mode. Normal mode overshoot stays gentle.
- Max once per day (the meal that crosses the line). Don't pile on at every subsequent meal.
- If the user reacts negatively or shows distress → **immediately soften and defer to emotional-support if needed.** Tough love stops the moment it hurts.
- Never shame food choices ("junk food", "garbage"). Name the food neutrally and focus on the math.

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
| **Executing strict behaviors** (nudges, morning accountability, tough love) | `notification-composer` + `diet-tracking-analysis` |
| **Frequency adjustment** (week-1 for 2 weeks) | `habit-builder` check-in logic |
| **Lifecycle** (graduation, failure, opt-out) | `habit-builder` |
| **Failure escalation** (back to weight-gain-strategy if streak 4+) | `habit-builder` → `weight-gain-strategy` |
