# Meal Place Collection Rules

Collects where the user typically eats each meal on **workdays only**. Weekend meals are not tracked.

## Data File

Path: `{workspaceDir}/data/meal-place-profile.json`
Owner: `diet-tracking-analysis`

### Schema

```json
{
  "workday_meal_place_profile": {
    "breakfast": {
      "place": "home",
      "updated_at": "2026-03-23T07:30:00+08:00"
    },
    "lunch": {
      "place": "cafeteria",
      "updated_at": "2026-03-23T12:10:00+08:00"
    },
    "dinner": {
      "place": "home",
      "updated_at": "2026-03-23T18:20:00+08:00"
    }
  },
  "_collection_state": {
    "breakfast": { "ask_count": 0, "collected": false },
    "lunch": { "ask_count": 0, "collected": false },
    "dinner": { "ask_count": 0, "collected": false }
  },
  "_drift_detection": {
    "breakfast": { "consecutive_mismatches": 0, "last_inferred": null },
    "lunch": { "consecutive_mismatches": 0, "last_inferred": null },
    "dinner": { "consecutive_mismatches": 0, "last_inferred": null }
  }
}
```

### Place values

| Value | Chinese label | English label |
|-------|--------------|---------------|
| `home` | 在家 | Home |
| `cafeteria` | 食堂 | Cafeteria |
| `takeout` | 外卖 | Takeout |
| `restaurant` | 外面堂食 | Restaurant |
| `bring_meal` | 自己带饭 | Bring meal |
| `other` | 其他 | Other |

---

## Collection Logic

### Precondition: Workday Only

Before running any collection or drift detection logic, check whether today is a **workday** (Monday–Friday). If it is a weekend (Saturday or Sunday), skip all venue collection — do not ask, do not infer, do not update.

### When to Ask

**Rule: If the current meal's `place` is `null` AND `_collection_state` for that meal has `collected: false` AND `ask_count < 3` → ask after the food log reply.**

Decision flow per meal log:

1. Read `data/meal-place-profile.json` (create with empty defaults if missing)
2. Look up current meal type (breakfast / lunch / dinner) in `workday_meal_place_profile`
3. If `place` is not null → **do not ask** (already collected) → go to Drift Detection
4. If `place` is null → check `_collection_state`:
   - `collected: true` → do not ask (impossible state, but safe guard)
   - `ask_count >= 3` → **do not ask** (gave up after 3 unanswered attempts)
   - `ask_count < 3` → **ask** → increment `ask_count` and save

### How to Ask (Pick-Two)

Present 2 most likely options based on meal type, plus an "other" escape hatch. Append one line after the food log reply:

**Default Top-2 per meal (workday):**

| Meal | Option 1 | Option 2 |
|------|----------|----------|
| breakfast | 🏠 在家 | 📦 外卖 |
| lunch | 🏢 食堂 | 📦 外卖 |
| dinner | 🏠 在家 | 📦 外卖 |

**Prompt format (Chinese):**
```
🍽 这顿工作日一般在哪吃？ {option1} ｜ {option2} ｜ 其他
```

**Prompt format (English):**
```
🍽 Where do you usually have this meal on workdays? {option1} | {option2} | Other
```

### Handling the Response

- **User picks an option or types a venue** → set `place` to the matching value, set `collected: true`, save `updated_at` with current timestamp
- **User ignores / does not reply** → `ask_count` was already incremented when the question was shown. On next food log for the same meal, re-evaluate the decision flow
- **User replies with a venue not in the top 2** → match to the closest candidate value. If no match, use `other`

### Give-Up Rule

When `ask_count` reaches 3 and `collected` is still `false`, that meal's place remains `null` permanently. Never ask again for initial collection.

---

## Drift Detection

Runs on every **workday** meal log where `place` is already set (not null).

### Inferring Venue from Context

On each food log, attempt to infer the dining venue from available signals:

| Signal | Source | Example inference |
|--------|--------|-------------------|
| Disposable container | Photo | → `takeout` or `cafeteria` |
| Office desk / keyboard | Photo background | → `takeout` or `cafeteria` or `bring_meal` |
| Home kitchen / dining table | Photo background | → `home` |
| Restaurant table / menu | Photo background | → `restaurant` |
| "外卖" / "点了个" / "delivery" | Text | → `takeout` |
| "食堂" / "cafeteria" | Text | → `cafeteria` |
| "自己做" / "home cooked" | Text | → `home` |
| "带饭" / "packed lunch" | Text | → `bring_meal` |
| "堂食" / "dine-in" | Text | → `restaurant` |

If no signal is available → do not infer, skip drift detection for this log.

### Mismatch Counting

When an inferred venue differs from the stored `place`:

1. Increment `_drift_detection[meal].consecutive_mismatches`
2. Update `_drift_detection[meal].last_inferred` to the inferred value

When the inferred venue matches the stored `place`:

1. Reset `consecutive_mismatches` to 0
2. Set `last_inferred` to null

### Triggering a Change Confirmation

When `consecutive_mismatches >= 3` for a meal:

1. Ask the user to confirm:

   **Chinese:**
   ```
   🍽 最近几次{meal_label}好像都不在{current_place_label}了，是换地方了吗？ {inferred_label} ｜ 没变还是{current_place_label}
   ```

   **English:**
   ```
   🍽 Your last few {meal_label}s don't seem to be at {current_place_label} anymore — has it changed? {inferred_label} | No, still {current_place_label}
   ```

2. **User confirms change** → update `place` to the new value, update `updated_at`, reset `consecutive_mismatches` to 0, set `last_inferred` to null
3. **User says no change** → reset `consecutive_mismatches` to 0, set `last_inferred` to null
4. **User does not reply** → reset `consecutive_mismatches` to 0, set `last_inferred` to null (do not ask again until 3 new consecutive mismatches accumulate)

### User Voluntary Update

If the user explicitly states a venue change (e.g., "我现在午饭改在家吃了" / "I eat lunch at home now"):

1. Update `place` to the new value immediately
2. Update `updated_at`
3. Reset `consecutive_mismatches` to 0
4. Do not ask for confirmation — the user already told you
