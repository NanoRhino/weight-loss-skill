# Missing Meal Detection Rules

Check for missing meals on **every food log message**, before logging or giving suggestions.

---

## Detection Logic

Evaluate from conversation history (including prior logged meals):

```
bfRecorded    = any breakfast or snack_am entry exists in today's log
              OR user previously said "didn't eat breakfast" / "skip breakfast" / equivalent
lunchRecorded = any lunch or snack_pm entry exists in today's log
              OR user previously said "didn't eat lunch" / "skip lunch" / equivalent
```

### Rules for `mealMode = 3` (default)

**RULE 1** — User is logging lunch, snack_pm, or dinner, AND `bfRecorded = false`:
- Do NOT log the current meal yet
- Ask about breakfast first

**RULE 2** — User is logging dinner, AND `lunchRecorded = false` (but `bfRecorded = true`):
- Do NOT log the current meal yet
- Ask about lunch first

### Rules for `mealMode = 2`

**RULE 3** — User is logging second meal AND first meal not recorded:
- Ask about first meal first

---

## Prompt Templates

Ask naturally and briefly — one question only. Match the user's language. Always include a short reason (data completeness + accurate suggestions):

**Examples:**
- "Breakfast isn't logged yet — filling it in helps keep your data complete and makes my suggestions more accurate. Did you have anything this morning? (totally fine if you skipped)"
- "Lunch isn't logged yet — I'd like to fill that in before giving you dinner suggestions. Did you eat anything around midday? (no worries if not)"

---

## Handling User Responses

| User response | Action |
|---------------|--------|
| Describes food | Record normally as the missing meal type, then continue to log the original meal |
| "Didn't eat" / "Skipped" | Mark as skipped (zero intake), continue to log original meal |
| "Ate but can't recall" | Use assumed intake = that single meal's standard ratio of daily targets (e.g. in 3-meal 30:40:30 mode, a forgotten lunch = 40% of daily targets). Pass as `--assumed` to evaluate. |
| Ambiguous (e.g. "had a little something") | Ask one follow-up for portion, then record |

After resolving the missing meal, **always continue to log the meal the user originally mentioned** in the next response — do not make the user repeat themselves. This takes two separate responses: first the backfilled meal, then the original meal.

**Backfilled meals** (meals the user is reporting after the fact): since the user has already eaten, `right_now` suggestions must NOT be given. Only `next_time` suggestions are appropriate. `nice_work` can still be used if warranted.

---

## Assumed Meals

Only created when the user confirms they ate but can't describe the food. The assumed amount is that single meal's standard ratio of daily targets (e.g. in 3-meal 30:40:30 mode, a forgotten lunch = 40% of daily targets, NOT the 70% cumulative checkpoint).

When the user says they skipped / didn't eat, there is no assumed intake — that meal counts as zero.

Assumed meals are used only for suggestion calculation — never shown in the progress display.
