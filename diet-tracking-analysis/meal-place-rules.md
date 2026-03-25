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

### How to Ask

Two modes depending on whether the venue can be inferred from the current meal's photo/text context, and the confidence level of that inference:

**Mode A: High confidence inference** — directly confirm the inferred venue:

| Language | Template |
|----------|----------|
| Chinese | `对了顺便问下，{meal_label}一般都是{inferred_label}呀？` |
| English | `By the way, do you usually {inferred_verb} for {meal_label}?` |

Examples:
- `对了顺便问下，早餐一般都是吃外卖呀？`
- `对了顺便问下，午餐一般都是在外面吃呀？`
- `By the way, do you usually order takeout for breakfast?`

**Mode B: Low confidence or no inference** — present two options, with inferred venue (if any) as the first option:

| Language | Template |
|----------|----------|
| Chinese | `对了顺便问下，{meal_label}一般是{option1_label}呢，还是{option2_label}呢？` |
| English | `By the way, do you usually {option1_verb} or {option2_verb} for {meal_label}?` |

Examples (no inference):
- `对了顺便问下，早餐一般是在家吃呢，还是点外卖呢？`
- `对了顺便问下，午餐一般是吃食堂呢，还是点外卖呢？`
- `By the way, do you usually eat at home or order takeout for breakfast?`

Examples (low-confidence inference of cafeteria for dinner):
- `对了顺便问下，晚餐一般是吃食堂呢，还是在家吃呢？` (inferred "cafeteria" becomes option 1)
- `By the way, do you usually eat at the cafeteria or at home for dinner?`

**Option selection logic for Mode B:**
1. If an inferred venue exists (low confidence): put it as option 1, pair with the first default that differs
2. If the inferred venue is already in the defaults: reorder so inferred is first
3. If no inference: use defaults as-is

**Default Top-2 per meal (workday, fallback when no inference):**

| Meal | Option 1 | Option 2 |
|------|----------|----------|
| breakfast | 在家吃 / eat at home | 点外卖 / order takeout |
| lunch | 吃食堂 / eat at cafeteria | 点外卖 / order takeout |
| dinner | 在家吃 / eat at home | 点外卖 / order takeout |

**Place label map (for Mode A):**

| Value | Chinese label | English verb |
|-------|--------------|-------------|
| `home` | 在家吃 | eat at home |
| `cafeteria` | 吃食堂 | eat at the cafeteria |
| `takeout` | 吃外卖 | order takeout |
| `restaurant` | 在外面吃 | eat out |
| `bring_meal` | 自己带饭 | bring your own meal |
| `other` | — | — |

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
