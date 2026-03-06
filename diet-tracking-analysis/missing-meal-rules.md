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
- Assume breakfast was eaten normally (standard ratio of daily targets)
- Continue to log the current meal immediately

**RULE 2** — User is logging dinner, AND `lunchRecorded = false` (but `bfRecorded = true`):
- Assume lunch was eaten normally (standard ratio of daily targets)
- Continue to log the current meal immediately

### Rules for `mealMode = 2`

In 2-meal mode, meal types are `meal_1` / `meal_2` (with `snack_1` / `snack_2`). Traditional names like "dinner" or "lunch" are automatically aliased (see SKILL.md Meal Type Assignment). There is no separate dinner checkpoint — `meal_2` is the final checkpoint at 100%.

**RULE 3** — User is logging `meal_2` (or aliased "dinner") AND `meal_1` not recorded:
- Assume first meal was eaten normally (standard ratio of daily targets)
- Continue to log the current meal immediately

---

## Assumed-Normal Logic

When missing meals are detected, **do NOT stop to ask** — instead:

1. **Assume the user ate normally** for each missing meal: use that meal's standard ratio of daily targets (e.g. in 3-meal 30:40:30 mode, a missing breakfast = 30% of daily targets, a missing lunch = 40% of daily targets)
2. **Pass the assumed meals via `--assumed`** to the `evaluate` command, so suggestions account for the assumed intake
3. **Log and evaluate the current meal as usual** — give the full response (meal details + nutrition summary + suggestion)
4. **Append a note after the suggestion** informing the user that missed meals were assumed normal, and they can provide details for more accurate advice (see Prompt Templates below)

---

## Prompt Templates

Append naturally after the current meal's suggestion — one short note only. Match the user's language:

**Examples (Chinese):**
- "PS: 早餐还没打卡，我先按正常吃了帮你算的。如果告诉我具体吃了什么，建议会更准确哦~"
- "PS: 午餐还没打卡，暂时按正常饮食算了。告诉我实际吃了什么的话，建议可以更精准~"

**Examples (English):**
- "PS: Breakfast wasn't logged — I assumed a normal meal for now. Let me know what you actually had and I can fine-tune the suggestions!"
- "PS: Lunch wasn't logged — I used a standard estimate for now. Share what you had if you'd like more precise advice!"

---

## Handling User Responses (After-the-Fact Updates)

If the user later comes back and provides details about the missed meal:

| User response | Action |
|---------------|--------|
| Describes food | Record normally as that meal type, re-run `evaluate` without `--assumed` for that meal, update suggestions |
| "Didn't eat" / "Skipped" | Mark as skipped (zero intake), re-run `evaluate` without `--assumed` for that meal, update suggestions |
| "Ate but can't recall" | Keep the assumed value as-is (already using standard ratio) |

**Backfilled meals** (meals the user is reporting after the fact): these are always classified as "already eaten" by the Eaten-Meal Detection rules in SKILL.md. Do NOT give `right_now` suggestions — use `next_meal` (if adjustment needed) or `next_time` (if on track) instead. `nice_work` can still be used if warranted.

---

## Assumed Meals

The assumed amount is that single meal's standard ratio of daily targets (e.g. in 3-meal 30:40:30 mode, a forgotten lunch = 40% of daily targets, NOT the 70% cumulative checkpoint).

Assumed meals are used only for suggestion calculation — never shown in the progress display.

When the user later confirms they skipped / didn't eat, remove the assumed intake and re-evaluate.
