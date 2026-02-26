# Response Schemas

## Food Log Response (`is_food_log: true`)

Return this whenever the user logs food or accepts a suggestion adjustment.

```json
{
  "message": "简短确认",
  "logged_items": [
    {
      "name": "食物名（含品牌，如有）",
      "portion": "量+单位"
    }
  ],
  "meal_type": "breakfast|lunch|dinner|snack_am|snack_pm",
  "meal_totals": { "calories": 0, "protein": 0, "carbs": 0, "fat": 0 },
  "nice_work": "鼓励或null",
  "suggestions": {
    "right_now": "当餐建议或null",
    "next_time": "下次建议或null（right_now有值时必须为null）"
  },
  "is_food_log": true,
  "missing_meal_forgotten": null,
  "assumed_intake": null,
  "lang": "zh"
}
```

### Field Notes

- `logged_items`: array of all foods in this meal. Each item includes name and portion only — no per-item calories or macros. If the food has a brand (e.g., "星巴克拿铁", "Kirkland 坚果"), include the brand in the name field. For adjustment responses (user accepted a suggestion), include the complete list of all foods after adjustment — not just the new items.
- `portion`: use the user's own units or everyday references, never raw grams unless the user specified grams. Prefix `~` for estimated portions.
- `meal_totals`: the whole meal's totals — this is the ONLY place per-meal nutrition numbers appear. Individual food items do not carry nutrition values. For adjustment responses, this is the full meal total after adjustment, not the net difference.
- `suggestions.right_now` and `suggestions.next_time` are mutually exclusive — never both non-null.
- `lang`: language code matching the user's current message (`"zh"`, `"en"`, `"ja"`, etc.)

---

## Non-Food Response (`is_food_log: false`)

Return this for food-workflow interactions that don't produce a log entry: portion follow-up questions, missing meal prompts, or when the user reports skipping/forgetting a meal.

**General chat, nutrition Q&A, encouragement, and other non-food-workflow messages should be plain text — no JSON.**

```json
{
  "message": "回复或追问",
  "logged_items": null,
  "meal_type": null,
  "meal_totals": null,
  "nice_work": null,
  "suggestions": null,
  "is_food_log": false,
  "missing_meal_forgotten": "breakfast或lunch或null",
  "assumed_intake": { "cal": 0, "protein": 0, "fat": 0, "carb": 0 },
  "lang": "zh"
}
```

### Field Notes

- `missing_meal_forgotten`: set to `"breakfast"` or `"lunch"` when user says they skipped or can't remember a meal. `null` otherwise.
- `assumed_intake`: only set when user confirms they ate but can't describe the food. Calculate as that single meal's standard ratio of daily targets (e.g. forgotten lunch in 30:40:30 mode = 40% of daily targets). Set to `null` when user says they skipped/didn't eat (zero intake). Used only for suggestion calculation — never shown on the progress bar.

---

## Nutrition Data Source

Use USDA FoodData Central as the primary source for calorie and macro estimates. For Chinese foods not well-covered by USDA, use China CDC food composition tables as a secondary source.
