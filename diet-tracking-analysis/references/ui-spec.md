# UI Specification

This document describes how the frontend renders Claude's JSON responses. Claude does not need to generate UI code — this is for context on how responses are displayed.

---

## Meal Card Structure

Each food log entry renders as a card. Display in this order, with clear visual hierarchy (summary prominent, details secondary):

1. **Header** — meal type icon + label + "Adjusted" badge if adjusted
2. **Summary** — whole-meal totals displayed prominently:
   - Calories (large number)
   - Protein / Carbs / Fat (values only, no daily targets, no progress bars)
3. **Details** — list of individual food items, visually secondary:
   - Food name (include brand if applicable, e.g., "Starbucks Latte")
   - Portion / weight
   - No per-item calories or macros
4. **Tips section** (mutually exclusive):
   - ✨ Nice Work (`nice_work`)
   - ⚡ Right Now (`right_now`, only if adjustment needed)
   - 💡 Next Time (`next_time`, only if no adjustment needed)

Multi-line suggestions: each `\n`-separated line renders as a separate `<div>`.

When the user accepts a suggestion, the frontend merges all entries for the same `meal_type`, deduplicates by food name (summing nutrition values), and shows the combined card with an "Adjusted" badge.

---

## Top Summary Bar

Shows today's cumulative actual intake vs daily goals:

- **Calories**: current / goal, progress bar, ±100 kcal range markers, "remaining" or "exceeded"
- **Protein / carbs / fat**: current / target, colour-coded (green = in range, red = over)
- **Expandable detail panel**: lists all logged meals with per-meal macro breakdown

Progress bar always uses actual recorded intake only — never includes assumed/estimated missing meals.

---

## App State

```
profile        → { weight, totalCal, mealMode, customRatios }
chatLog        → UI messages including entry objects for meal cards
apiHistory     → full conversation history sent to API
missingMeals   → string[] of meal types user confirmed forgetting
assumedMeals   → { breakfast?: {cal,protein,fat,carb}, lunch?: ... }
```

Persisted to `window.storage` under key `"nourish_v3"`.
