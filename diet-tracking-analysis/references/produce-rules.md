# Produce Tracking Rules (China Region)

## Logging

Estimate vegetable/fruit gram weights in `--meal-json` (`vegetables_g`/`fruits_g`). Prefix with `~` in response.
Starchy vegetables (potato, sweet potato, taro, corn) count toward carbs — **not** toward the vegetable target.

## Display

Show produce status line when `has_vegetable_target = true` or `is_final_meal = true`:
```
🥦 Vegetables: ~XXXg ✅/⬇️   🍎 Fruit: ~XXXg ✅/⬇️ (fruit only at final meal)
```
Icons: ✅ on_track, ⬇️ low, ⬆️ high. Omit entirely at breakfast checkpoint if no vegetable target.

## Priority

Calorie/macro targets always override produce targets — never cut vegetables unless they cause calorie excess.

## Suggestions

- **Low at non-final meal** → suggest adding vegetables/fruit next meal
- **Low at final meal** → suggest a side of vegetables or fruit now (if calories allow)
- **High / on track** → brief note, no push
