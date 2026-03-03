# Missing Meal Detection Rules

Check for missing meals on **every food log message**, before logging or giving suggestions. The frontend may also inject a `missingPrompt` override as a fallback, but do not rely on it.

---

## Detection Logic

Evaluate from conversation history (including `apiHistory`):

```
bfRecorded    = any breakfast or snack_am entry exists in apiHistory
              OR user previously said "skip breakfast" / "didn't have breakfast" / equivalent
lunchRecorded = any lunch or snack_pm entry exists in apiHistory
              OR user previously said "skip lunch" / "didn't have lunch" / equivalent
```

### Rules for `mealMode = "3"` (default)

**RULE 1** — User is logging lunch, snack_pm, or dinner, AND `bfRecorded = false`:
- Do NOT log the current meal yet
- Ask about breakfast first
- Set `is_food_log: false`

**RULE 2** — User is logging dinner, AND `lunchRecorded = false` (but `bfRecorded = true`):
- Do NOT log the current meal yet
- Ask about lunch first
- Set `is_food_log: false`

### Rules for `mealMode = "2"`

**RULE 3** — User is logging second meal AND first meal not recorded:
- Ask about first meal first
- Set `is_food_log: false`

---

## Prompt Templates

Ask naturally and briefly — one question only. Match the user's language. Always include a short reason (data completeness + accurate suggestions):

**English:**
- "Breakfast isn't logged yet — filling it in helps keep your data complete and makes my suggestions more accurate. Did you have anything this morning? (totally fine if you skipped)"
- "Lunch isn't logged yet — I'd like to fill that in before giving you dinner suggestions. Did you eat anything around midday? (no worries if not)"

---

## Handling User Responses

| User response | Action |
|---------------|--------|
| Describes food | Record normally (`is_food_log: true`, `meal_type` = missing meal), `assumed_intake: null` |
| "didn't eat" / "skip" / equivalent | `is_food_log: false`, set `missing_meal_forgotten` = `"breakfast"` or `"lunch"`, `assumed_intake: null` (zero intake — user confirmed they didn't eat) |
| "ate but can't recall" / equivalent | `is_food_log: false`, set `missing_meal_forgotten` = `"breakfast"` or `"lunch"`, set `assumed_intake` = that single meal's standard ratio of daily targets (NOT the cumulative checkpoint). E.g. in 3-meal mode with default 30:40:30 ratio, a forgotten lunch = 40% of daily targets. |
| Ambiguous (e.g. "had a little something") | Ask one follow-up for portion, then record |

After resolving the missing meal, **always continue to log the meal the user originally mentioned** in the next response — do not make the user repeat themselves. This takes two separate responses (two JSON objects in two turns): first the backfilled meal, then the original meal.

**Backfilled meals** (meals the user is reporting after the fact): since the user has already eaten, `right_now` must be `null`. Only `next_time` suggestions are appropriate. `nice_work` can still be used if warranted.

---

## Assumed Meals

Only created when the user confirms they ate but can't describe the food. The assumed amount is that single meal's standard ratio of daily targets (e.g. in 3-meal 30:40:30 mode, a forgotten lunch = 40% of daily targets, NOT the 70% cumulative checkpoint).

When the user says they skipped / didn't eat, assumed_intake is null — that meal counts as zero intake.

Assumed meals are stored in app state (`assumedMeals`), used only for suggestion calculation — never added to the progress bar.
