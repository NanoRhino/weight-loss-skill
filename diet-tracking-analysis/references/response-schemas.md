# Response Schemas

## Food Log Response (`is_food_log: true`)

Return this whenever the user logs food or accepts a suggestion adjustment.

```json
{
  "message": "简短确认",
  "logged_items": [
    {
      "name": "食物名（用户语言）",
      "portion": "量+单位",
      "calories": 0,
      "protein": 0,
      "carbs": 0,
      "fat": 0,
      "confidence": "exact or estimated"
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

- `logged_items`: array of all foods in this meal. For adjustment responses (user accepted a suggestion), include only the new/changed items. Negative values represent removed food.
- `portion`: use the user's own units or everyday references, never raw grams unless the user specified grams.
- `confidence`: `"exact"` for standardized items (e.g., 一罐可乐), `"estimated"` for portion-guessed items. Prefix estimated item names with `~`.
- `meal_totals`: sum of all `logged_items` in this response. Can be negative for adjustment entries.
- `suggestions.right_now` and `suggestions.next_time` are mutually exclusive — never both non-null.
- `lang`: language code matching the user's current message (`"zh"`, `"en"`, `"ja"`, etc.)

---

## Non-Food Response (`is_food_log: false`)

Return this for follow-up questions, missing meal prompts, general chat, or when the user reports skipping/forgetting a meal.

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
- `assumed_intake`: when `missing_meal_forgotten` is set, calculate as checkpoint target ÷ 4 per macro. This is used internally for suggestion math but never shown on the progress bar.

---

## Nutrition Data Source

Use USDA FoodData Central as the primary source for calorie and macro estimates. For Chinese foods not well-covered by USDA, use China CDC food composition tables as a secondary source.
