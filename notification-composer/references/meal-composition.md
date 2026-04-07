# Meal Composition Rules — Notification Composer

Rules for composing 2-3 meal recommendations in each reminder.

---

## Recommendation Sources (by `data_level`)

| `data_level` | Strategy |
|-------------|----------|
| `rich` (≥ 7 days) | Base recommendations on the user's real eating habits (`top_foods`). Combine familiar ingredients into varied meals. |
| `limited` (1-6 days) | Mix available history with the diet template. Use known favorites where possible, fill gaps from the template. |
| `none` (0 days) | Use the diet template + `health-preferences.md` preferences entirely. |

## Format

Each recommendation = food combo + short tip (joined by ` — `).
Tip ≤ 6 English words / 10 CJK characters. Casual, friend-like tone.

Tip sources:
- Nutritional complement to earlier meals today ("light on carbs this morning — balancing out")
- Habit acknowledgment ("your go-to combo, solid")
- Variety ("switching it up")
- Situational ("if you want something lighter today")

## Deduplication

- Read `recent_recommendations` from `meal-history` output.
- Of the 2-3 options, at least 2 must differ from yesterday's `items` for the same meal type.
- Among the 2-3 options themselves, ensure variety: ideally one familiar favorite, one variation on a favorite, one different choice.
- If the user picked the same recommendation 3+ days in a row, don't force a change — respect their preference.

## Example

```
Morning! A few ideas:

1. Oatmeal + boiled eggs + milk — your go-to, solid
2. Avocado toast + yogurt — switch it up
3. Smoothie bowl + granola — light start today

Snap a pic before you eat — I'll take a look~
```
