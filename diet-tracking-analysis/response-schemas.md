# Response Schemas

## Food Log Reply Format

Every food log reply has up to three sections:

### ① Meal Details

```
📝 [Meal type] logged!

🍽 This meal total: XXX kcal | Protein Xg | Carbs Xg | Fat Xg
· Food 1 — portion — XXX kcal
· Food 2 — portion — XXX kcal
```

### ② Nutrition Summary

Cumulative intake evaluation (from `evaluate` output). Always show.

```
📊 So far today: XXX calories [status] | Protein Xg [status] | Carbs Xg [status] | Fat Xg [status]
[1-sentence overall comment]
```

- Show cumulative `actual` values; do NOT show checkpoint target numbers — only status indicators
- Status: ✅ on track, ⬆️ high, ⬇️ low (from `status` field)
- 1-sentence comment: summarize overall, can lead into suggestion. Keep complementary with ③, not repetitive
- Language consistency: do not mix languages (no "蛋白质on track"). Use localized nutrient names
- Forgotten/assumed meals: only show real recorded values
- **CN region:** See `references/produce-rules.md` for produce status line format

### ③ Suggestion

Use `evaluation.suggestion_type` from `log-meal`:

**`"right_now"`** — Before eating, adjustment needed:
```
⚡ Right now: [specific adjustment for current meal]
```
- Reduce/swap items in current meal (not yet eaten). Add items to next occasion, not current (already prepared).
- When reducing, tell user they can have it later ("skip bread now, save for dinner")
- Do NOT list per-item calories. Single option → adjusted totals. Multiple → list and ask.

**`"next_meal"`** — Already eaten, adjustment needed:
```
💡 Next meal: [forward-looking compensatory advice]
```
- Suggest next-meal adjustments. Frame as planning, never fixing a mistake.
- Last meal + over target: "A bit over today, totally normal — aim for your usual pattern tomorrow."

**`"next_time"`** — On track:
```
💡 Next time: [habit tip or next-meal pairing — specific food + amount, no calorie listing]
```

**`"case_d_snack"`** — Final meal, below BMR: recommend adding a snack. Gentle but clear.

**`"case_d_ok"`** — Final meal, mild deficit (≥ BMR, < target): note they CAN snack if hungry, no need if not.

**✨ Nice work** (optional, between ② and ③):
```
✨ [1–2 genuine lines tied to actual food choices, or omit if nothing noteworthy]
```

---

## Food Suggestion Format

When suggesting food (in any suggestion type):

1. **State the category** — "high-protein food", "complex carbs", "healthy fat"
2. **Give concrete examples** — prioritize foods from user's recent meal records (`load` with past dates). Falls back to common, easy-to-obtain foods.
3. **Respect preferences** — never suggest disliked/allergenic foods; favor loved foods

Examples:
- ✅ "加点**优质蛋白**，比如你常吃的鸡胸肉或水煮蛋"
- ✅ "Add some **complex carbs** — like the oatmeal you had yesterday"
- ❌ "Add 100g chicken breast" (no category, no personalization)
- ❌ "Try quinoa with salmon" (user may never eat these)

---

## Full Example

```
📝 Lunch logged!

🍽 This meal total: 900 kcal | Protein 15g | Carbs 128g | Fat 35g
· Fried rice — ~1 bowl — 520 kcal
· Bubble tea — 1 cup — 380 kcal

📊 So far today: 1279 kcal ⬆️ | Protein 39g ⬇️ | Carbs 173g ⬆️ | Fat 49g ✅
Calories and carbs are running high while protein is low — the rice + bubble tea combo pushed carbs up.

💡 Next meal: Dinner go heavier on high-protein food — like your usual grilled chicken breast or steamed fish — and lighter on carbs, keep rice to half a bowl or skip it.
```
