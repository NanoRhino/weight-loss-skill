# Missing Meal Detection Rules

Check for missing meals on **every food log message**, before logging or giving suggestions. The frontend may also inject a `missingPrompt` override as a fallback, but do not rely on it.

---

## Detection Logic

Evaluate from conversation history (including `apiHistory`):

```
bfRecorded    = any breakfast or snack_am entry exists in apiHistory
              OR user previously said "没吃早饭" / "skip breakfast" / equivalent
lunchRecorded = any lunch or snack_pm entry exists in apiHistory
              OR user previously said "没吃午饭" / "skip lunch" / equivalent
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

**Chinese:**
- 早饭还没记录，为了让今天的数据完整、给你的建议更准，早上吃了什么？（没吃也告诉我一声就好）
- 午饭还没记录，想先补上才能给你准确的晚饭建议，中午吃了什么？（没吃也没关系）

**English:**
- "Breakfast isn't logged yet — filling it in helps keep your data complete and makes my suggestions more accurate. Did you have anything this morning? (totally fine if you skipped)"
- "Lunch isn't logged yet — I'd like to fill that in before giving you dinner suggestions. Did you eat anything around midday? (no worries if not)"

---

## Handling User Responses

| User response | Action |
|---------------|--------|
| Describes food | Record normally (`is_food_log: true`, `meal_type` = missing meal), `assumed_intake: null` |
| "没吃" / "跳过" / "skip" | `is_food_log: false`, set `missing_meal_forgotten` = `"breakfast"` or `"lunch"`, set `assumed_intake` = checkpoint target ÷ 4 per macro |
| "记不得" / can't recall | `is_food_log: false`, set `missing_meal_forgotten` = `"breakfast"` or `"lunch"`, set `assumed_intake` = checkpoint target ÷ 4 per macro |
| Ambiguous (e.g. "随便吃了点") | Ask one follow-up for portion, then record |

After resolving the missing meal, **always continue to log the meal the user originally mentioned** in the same or next response — do not make the user repeat themselves.

---

## Assumed Meals

Only created when the user says they can't remember or doesn't describe any food. Stored in app state (`assumedMeals`), used only for suggestion calculation — never added to the progress bar.
