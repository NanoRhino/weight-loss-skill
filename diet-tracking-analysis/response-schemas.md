# Response Schemas

## Food Log Reply (3 sections)

### ① Meal Details
```
📝 [Meal type] logged!

🍽 This meal: XXX kcal | Protein Xg | Carbs Xg | Fat Xg
· Food — portion — XXX kcal
```

### ② Nutrition Summary (from `evaluate`)
```
📊 So far today: XXX kcal [status] | Protein Xg [status] | Carbs Xg [status] | Fat Xg [status]
[1-sentence comment → leads into ③]
```
Status: ✅ on_track | ⬆️ high | ⬇️ low. Show cumulative actuals only, no target numbers.

**CN produce** (after macro line): `🥦 Vegetables: ~XXXg ✅/⬇️  🍎 Fruit: ~XXXg ✅/⬇️`
Low → suggest adding at next meal (final meal → suggest now). Fruit: only track at final meal. Produce targets never override calorie/macro targets.

### ③ Suggestion (by `suggestion_type`)

**`"right_now"`** — Before eating, adjustment needed:
```
⚡ Right now: [specific adjustment for current meal]
```
- Reduce/swap items in current meal (not yet eaten). Add items to next occasion, not current (already prepared).
- When reducing, tell user they can have it later ("skip bread now, save for dinner")
- Do NOT list per-item calories. Single option → adjusted totals. Multiple → list and ask.

**Other types:**
| Type | Icon | Guidance |
|------|------|----------|
| `next_meal` | 💡 | Forward-looking advice. Frame as planning, not fixing. Over at last meal → "normal, aim for usual pattern tomorrow." |
| `next_time` | 💡 | On track — habit tip or next-meal pairing, specific food, no calorie listing |
| `case_d_snack` | 🍽 | Final meal, below BMR — gently recommend a snack |
| `case_d_ok` | 💡 | Final meal, mild deficit — CAN snack if hungry, no pressure |

Optional: `✨ Nice work` between ② and ③ — 1 line on actual food choices, omit if nothing noteworthy.

## Food Suggestions
- State category ("high-protein", "complex carbs") + concrete examples from user's recent meals (use `load` with past dates)
- Respect preferences: never suggest disliked/allergenic foods (check `health-preferences.md`); favor loved foods
- Fallback to common easy-to-obtain foods if no meal history
- ✅ "Add some **lean protein** — like the chicken breast you had yesterday"
- ❌ "Add 100g chicken breast" (no category, no personalization)

## Full Example

```
📝 Lunch logged!

🍽 This meal: 900 kcal | Protein 15g | Carbs 128g | Fat 35g
· Fried rice — ~1 bowl — 520 kcal
· Bubble tea — 1 cup — 380 kcal

📊 So far today: 1279 kcal ⬆️ | Protein 39g ⬇️ | Carbs 173g ⬆️ | Fat 49g ✅
Calories and carbs high, protein low — rice + bubble tea pushed carbs up.

💡 Next meal: heavier on protein (grilled chicken/steamed fish), lighter on carbs (half bowl rice or skip).
```
