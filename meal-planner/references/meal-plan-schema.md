# Meal Plan Markdown Schema

This document defines the strict Markdown format for `MEAL-PLAN.md`. The agent generates this file; `generate-meal-plan-html.py` parses it into styled HTML.

## Rules

1. **H1** (`#`) = Plan title. Followed by metadata lines (unordered list). **Metadata keys MUST always be in English** (`Date`, `Calories`, `Mode`, `Macros`) regardless of the user's language — the HTML parser matches on these exact keys. Values can be in any language.
2. **H2** (`##`) = Day header. Format: `Day N | DayName | Xcal · Protein Xg · Carbohydrate Xg · Fat Xg`
3. **H3** (`###`) = Meal header. Format: `Emoji MealName [Tag]? | Xcal · Protein Xg · Carbohydrate Xg · Fat Xg`
   - `[Tag]` is optional, used for eating-out meals: `[Takeout]`, `[Eating out]`, `[外卖]`, `[便利店]`, etc.
4. **Blockquote** (`>`) = Dish summary (concise dish names joined by " + ") or order info for eating-out meals.
5. **List items** (`-`) = Food items. Format: `FoodName — NaturalPortion (PreciseWeight)`
   - Parenthesized weight at the end becomes `<span class="portion">` in HTML.
   - For eating-out meals, list items are ordering details.
6. **Tip line** (`💡`) = Meal tip. Must start with `💡` emoji. Only include non-obvious, actionable tips.
7. **Grocery section** (optional): `## Grocery List` followed by `### Category` and list items.

## Macro Format

Always use full names — never abbreviate to P/C/F. **Use macro names matching the user's language:**

- **English:** `Protein`, `Carbohydrate`, `Fat`
- **Chinese:** `蛋白质`, `碳水化合物`, `脂肪`

```
English: 1850 kcal · Protein 105g · Carbohydrate 196g · Fat 62g
Chinese: 1850 kcal · 蛋白质 105g · 碳水化合物 196g · 脂肪 62g
```

## Complete Example

```markdown
# 7-Day Meal Plan
- Date: 2026-03-09
- Calories: 1850 kcal (1750-1950)
- Mode: Balanced
- Macros: Protein 105g · Carbohydrate 196g · Fat 62g

## Day 1 | Sunday | 1610 kcal · Protein 102g · Carbohydrate 178g · Fat 48g

### 🍳 Breakfast | 380 kcal · Protein 22g · Carbohydrate 48g · Fat 11g
> Oatmeal + boiled egg + milk
- Rolled oats (cooked) — 1/2 cup (40g dry)
- Boiled egg — 1 (50g)
- Whole milk — 1 cup (240ml)

### 🥗 Lunch | 540 kcal · Protein 36g · Carbohydrate 60g · Fat 16g
> Baked salmon + roasted vegetables + brown rice
- Baked salmon — 1 fillet (140g)
- Roasted zucchini & bell peppers — 2 cups (200g)
- Brown rice (cooked) — 1/2 cup (100g)

### 🍽️ Dinner [Takeout] | 500 kcal · Protein 30g · Carbohydrate 52g · Fat 18g
> Chipotle — Chicken burrito bowl
- Order: chicken, brown rice, black beans, fajita veggies, salsa, lettuce. Skip sour cream and cheese.
💡 Ask for half rice to save ~100 Cal. Extra veggies are free.

### 🍎 Snack | 180 kcal · Protein 9g · Carbohydrate 18g · Fat 4g
- Plain Greek yogurt — 3/4 cup (170g)
- 1 medium apple

## Day 2 | Monday | 1590 kcal · Protein 100g · Carbohydrate 172g · Fat 52g

### 🍳 Breakfast | 380 kcal · Protein 24g · Carbohydrate 46g · Fat 12g
> Whole-wheat toast + boiled egg + milk
- Whole-wheat toast — 2 slices (60g)
- Boiled egg — 1 (50g)
- Cheddar cheese — 1 slice (28g)
- Whole milk — 1 cup (240ml)

(... continue for all 7 days ...)

## Grocery List

### Proteins
- Chicken breast — 600g
- Salmon fillet — 2 pieces
- Eggs — 1 dozen

### Grains & Starches
- Brown rice — 500g
- Rolled oats — 200g
- Whole-wheat bread — 1 loaf

### Vegetables
- Broccoli — 2 heads
- Bell peppers — 4
- Zucchini — 2

### Dairy & Others
- Whole milk — 2L
- Greek yogurt — 500g
- Cheddar cheese — 200g
```

## Notes for the Agent

- **Metadata keys (`Date`, `Calories`, `Mode`, `Macros`) MUST be in English** — the parser depends on these exact keys. Values can be localized (e.g., `Mode: 均衡饮食` is fine, but `饮食模式: 均衡饮食` will break parsing).
- Every day (Day 1–7) must be fully written out. No placeholders like "same as Day 1".
- Meal emojis: 🍳 Breakfast, 🥗 Lunch, 🍽️ Dinner, 🍎 Snack (adapt names to user's language).
- The metadata Date field should be the generation date.
- Adapt food names, units, macro names, and language to the user's locale. For Chinese users, use `蛋白质`, `碳水化合物`, `脂肪` instead of `Protein`, `Carbohydrate`, `Fat`.
- Grocery list is optional — only include if the user requested it.
