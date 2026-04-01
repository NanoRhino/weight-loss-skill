# Produce Tracking (China Region)

## Estimation
- Log `vegetables_g`/`fruits_g` in `--meal-json`; prefix with `~`
- Starchy vegetables (potato, sweet potato, taro, corn) → count as carbs, NOT toward vegetable target

## Response line (after macro summary)
Show when `has_vegetable_target` or `is_final_meal`:
```
🥦 Vegetables: ~XXXg ✅/⬇️  🍎 Fruit: ~XXXg ✅/⬇️ (fruit only at final meal)
```
✅ on_track | ⬇️ low | ⬆️ high. Omit at breakfast if no vegetable target.

## Rules
- Produce targets < calorie/macro targets in priority
- Low vegetables → suggest adding at next meal; at final meal → suggest now
- Low fruit at final meal → suggest if calories allow
- Never reduce vegetables unless causing calorie excess
