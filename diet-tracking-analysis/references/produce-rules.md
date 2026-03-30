# Produce Tracking Rules (China Region)

## Estimating produce amounts

When logging a meal, estimate vegetable and fruit gram weights and include `vegetables_g`/`fruits_g` in `--meal-json`:
- Standard portions: a plate of stir-fried greens ≈ 200g, one medium apple ≈ 180g, half a cucumber ≈ 100g
- Prefix estimates with `~` in the response
- Starchy vegetables (potato, sweet potato, taro, corn) count toward carbs/calories but **not** toward the vegetable target

## Priority rules

Produce targets have **lower priority** than calories and macros:
- Never suggest reducing vegetables unless they cause calorie/macro excess (e.g. oily stir-fry)
- If adding vegetables conflicts with calorie targets, calorie target takes precedence

## Suggestions (based on `produce` in log-meal results)

- `vegetable_status: "low"` at non-final meal → suggest adding vegetables at the next meal
- `vegetable_status: "low"` at final meal → suggest a side of low-calorie vegetables now
- `fruit_status: "low"` at final meal → suggest a fruit as snack/dessert if calories allow
- `fruit_status: "high"` → briefly mention, no strong push
- On track → brief positive note
