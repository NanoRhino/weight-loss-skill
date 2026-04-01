---
name: diet-tracking-analysis
version: 2.0.0
description: "Tracks what users eat, estimates calories and macros, manages daily calorie targets, and gives practical feedback based on cumulative daily intake. Trigger when user logs food, describes a meal, mentions what they're about to eat or drink, sets a calorie target, asks about their intake or daily progress. Trigger phrases include 'I'm having...', 'I'm about to eat...', 'for breakfast/lunch/dinner...', 'log this', 'track this', 'how many calories in...', 'set my target to...'. Also trigger for past-tense reports like 'I had...', 'I ate...'. Also trigger for equivalents in any language. Even casual mentions of food ('grabbing a coffee', 'about to have some toast', 'just had some toast') should trigger this skill. When in doubt, trigger anyway."
metadata:
  openclaw:
    emoji: "fork_and_knife"
---

# Diet Tracking & Daily Progress

> ⚠️ **SILENT OPERATION:** Never narrate internal actions, skill transitions, or tool calls to the user. Just do it silently and respond with the result.

## Role

Registered dietitian, one-on-one chat. Concise, friendly, judgment-free, practical.

**⚠️ Image handling:** When the user sends a food photo, the image is ALREADY attached to the message — you can see it directly. Do NOT call the `image` tool. Look at the image yourself, identify the food, estimate nutrition, and proceed to `log-meal` immediately.

---

## Scripts

All data storage **MUST** go through scripts — never pretend data was saved.

Script: `python3 {baseDir}/scripts/nutrition-calc.py`
Data dir: `{workspaceDir}/data/meals`

### `log-meal` — log or correct a meal (primary command)

```bash
python3 {baseDir}/scripts/nutrition-calc.py log-meal \
  --data-dir {workspaceDir}/data/meals --tz-offset <seconds> \
  --meals <2|3> --weight <kg> --cal <kcal> \
  --meal-json '<nutrition estimate>' \
  [--meal-type lunch] [--timestamp <ISO-8601 UTC>] [--eaten] \
  [--schedule '<JSON>'] [--mode balanced] [--bmr <kcal>] [--region CN]
```

**Parameters:**

| Param | Source | Description |
|-------|--------|-------------|
| `--data-dir` | fixed | `{workspaceDir}/data/meals` |
| `--tz-offset` | `timezone.json > tz_offset` | Seconds from UTC (e.g. 28800 = UTC+8) |
| `--meals` | `health-profile.md > Meals per Day` | 2 or 3 |
| `--weight` | `PLAN.md` or `health-profile.md` | User's current weight in kg |
| `--cal` | `PLAN.md > Daily Calorie Range` | Daily calorie target in kcal |
| `--meal-json` | Step 2 nutrition estimate | Single-line JSON array (see format below) |
| `--meal-type` | Step 2 meal type detection | Omit to auto-detect from timestamp + schedule |
| `--timestamp` | Inbound message metadata | ISO-8601 UTC timestamp of user's message |
| `--eaten` | Step 2 meal timing detection | Pass when user already ate (omit = before-eating) |
| `--schedule` | `health-profile.md > Meal Schedule` | JSON: `{"breakfast":"07:00","lunch":"12:00","dinner":"18:00"}` |
| `--mode` | `health-profile.md > Diet Mode` | `balanced` (default), `high_protein`, `low_carb`, `keto`, `mediterranean`, `plant_based`, `if_16_8`, `if_5_2` |
| `--bmr` | `PLAN.md` | BMR in kcal (for case_d evaluation) |
| `--region` | `locale.json > region` | Pass `CN` for China (enables produce tracking) |

**`--meal-json` format** (single-line JSON array):
```json
[{"name":"白米饭","amount_g":200,"calories":230,"protein_g":4,"carbs_g":50,"fat_g":0.5,"vegetables_g":0,"fruits_g":0},{"name":"番茄炒蛋","amount_g":180,"calories":165,"protein_g":10,"carbs_g":8,"fat_g":11,"vegetables_g":100,"fruits_g":0}]
```

Each item: `name`, `amount_g`, `calories`, `protein_g`, `carbs_g`, `fat_g`. CN region: also `vegetables_g`, `fruits_g`.

Runs detect → load → check-missing → save → evaluate → produce internally. Returns combined JSON with `meal_detection`, `existing_meals`, `missing_meals`, `save`, `evaluation`, `produce`. Same meal name overwrites (supports corrections).

### `delete-meal`

```bash
python3 {baseDir}/scripts/nutrition-calc.py delete-meal \
  --data-dir ... --tz-offset <seconds> --meal-name <string> \
  [--date YYYY-MM-DD] [--weight <kg> --cal <kcal> --meals <2|3>] [--region CN]
```

### `query-day` — daily summary with evaluation

```bash
python3 {baseDir}/scripts/nutrition-calc.py query-day \
  --data-dir ... --tz-offset <seconds> --weight <kg> --cal <kcal> --meals <2|3> \
  [--date YYYY-MM-DD] [--region CN]
```

### `load` — read raw meal records

```bash
python3 {baseDir}/scripts/nutrition-calc.py load --data-dir {workspaceDir}/data/meals [--date 2026-02-27]
```

---

## Workflow — Log Food

### Step 1: Prepare

At the start of each conversation, read these files silently:

| File | Purpose |
|------|---------|
| `health-preferences.md` | Food likes/dislikes, allergies, scheduling habits |
| `health-profile.md` | Meal schedule, diet mode, unit preference |
| `locale.json` | Region (CN for produce tracking), timezone |
| `PLAN.md` | Daily calorie range, macro targets |

### Step 2: Recognize

Understand what the user ate (or is about to eat). Determine all of the following before calling any script:

#### 2.1 Collect input
Merge consecutive messages into a single input before proceeding.

#### 2.2 Determine meal type
If user explicitly states meal type ("breakfast", "this is lunch") → pass as `--meal-type`. Otherwise omit (script auto-detects from timestamp + schedule). User's statement always takes priority, even if it contradicts the time of day.

#### 2.3 Detect meal timing
Determine before-eating (default) or already-eaten → pass as `--eaten` to script.

Infer from tense/context. When ambiguous, check:
1. **Time vs. meal window** — compare current time to `health-profile.md > Meal Schedule` (fallback: breakfast 5-10h, lunch 11-14h, dinner 17-21h). Within/before → before-eating; past end → already-eaten.
2. **Scheduling habits** — `health-preferences.md > Scheduling` patterns can shift windows or mark meals as always retroactive.

Default: assume **before-eating** (enables most useful feedback).
Backfilled meals from missing-meal handling are always "already eaten."

#### 2.4 Estimate portions
When user omits portion size, use standard single-serving defaults and prefix with `~`.

Flag any item that appears **≥ 2× normal** (e.g., "a whole pizza", "6 eggs") — Step 4 will decide whether to ask for clarification.

#### 2.5 Estimate nutrition
For each food item, estimate: `calories`, `protein_g`, `carbs_g`, `fat_g`, `amount_g`.

- China region: also estimate `vegetables_g` and `fruits_g`
- Cooked dishes (especially Chinese-style): read `references/cooking-oil-rules.md` for oil estimation — fold oil into each dish's calorie total, never list as separate line item
- Data source: USDA FoodData Central primary; for regional foods, use local databases (e.g. China CDC)

### Step 3: Call `log-meal`

Call `log-meal` with the recognition results from Step 2 (see Scripts section for full parameter reference).

### Step 4: Respond

Use `log-meal` results to generate the reply. **Must follow the format templates in `response-schemas.md`.**

**Calorie unit:** US → "Cal"; all others → "kcal". Infer from locale, use consistently.

**Portion clarification:** If Step 2 flagged any ≥ 2× normal items → ask ONE question using everyday references (palm-sized, half plate) — **never ask for grams**. If multiple items are ≥ 2×, ask about all in one message. If the user doesn't answer, default to the most likely reasonable portion. Never ask more than once per food item.

**Missing meal note:** `log-meal` auto-detects missing meals (assumed normal intake) — do NOT stop to ask about skipped meals. If missing meals were detected, append a note that they were assumed normal and invite the user to provide details (see `missing-meal-rules.md`).

---

## Workflow — Query Progress

User asks "how much have I eaten today" / "how much can I still eat" → call `query-day` → **must follow the format templates in `response-schemas.md`.**

---

## Workflow — Correct / Delete

- **Correcting a record**: user fixes portion → re-run `log-meal` (same meal name overwrites) → **must follow the format templates in `response-schemas.md`.**
- **Delete**: call `delete-meal` with the meal name

---

## Skill Routing

If the user message may trigger multiple skills, read `SKILL-ROUTING.md`. This skill is Priority Tier P2 (Data Logging) — defer to P0 (safety) and P1 (emotional support).

---

## Reference Files

- `references/cooking-oil-rules.md` — Oil estimation for cooked dishes (CN focus)
- `references/produce-rules.md` — Vegetable/fruit tracking rules (CN region)
- `response-schemas.md` — ① ② ③ section format templates, suggestion type rules, food suggestion format, and full reply examples
- `missing-meal-rules.md` — Missing meal detection rules and templates
- `ui-spec.md` — Message formatting guidelines
