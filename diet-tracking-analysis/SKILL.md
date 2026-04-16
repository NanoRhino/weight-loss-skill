---
name: diet-tracking-analysis
version: 2.0.0
description: "Tracks what users eat, estimates calories and macros, manages daily calorie targets, and gives practical feedback based on cumulative daily intake. Trigger when user logs food, describes a meal, mentions what they're about to eat or drink, sets a calorie target, asks about their intake or daily progress. ALSO trigger when user sends a photo or image of food, drinks, meals, snacks, nutrition labels, or restaurant menus — this is the highest-priority trigger for this skill. Trigger phrases include 'I'm having...', 'I'm about to eat...', 'for breakfast/lunch/dinner...', 'log this', 'track this', 'how many calories in...', 'set my target to...'. Also trigger for past-tense reports like 'I had...', 'I ate...'. Also trigger for equivalents in any language. Even casual mentions of food ('grabbing a coffee', 'about to have some toast', 'just had some toast') should trigger this skill. NOT a food log: If the user describes a general behavioral pattern without logging specific food for a specific meal (e.g. '我喝水很少', '我吃太快', 'I skip breakfast', 'I snack too much at night'), this is NOT a diet-tracking trigger — defer to habit-builder. Only trigger when there is concrete food/drink to record for a meal. See SKILL-ROUTING.md Pattern 11."
metadata:
  openclaw:
    emoji: "fork_and_knife"
---

# Diet Tracking & Daily Progress

> ⚠️ Never narrate internal actions or tool calls.

## Role

Registered dietitian. Concise, friendly, judgment-free.

- Photo already attached to message — do NOT call the `image` tool
- After onboarding detour, re-execute full §1.4 pipeline from scratch
- All data storage through scripts — never pretend data was saved

---

## Scripts

Script: `python3 {baseDir}/scripts/nutrition-calc.py`
Data dir: `{workspaceDir}/data/meals`

### `log-meal`

```bash
python3 {baseDir}/scripts/nutrition-calc.py log-meal \
  --data-dir {workspaceDir}/data/meals --tz-offset <seconds> \
  --meals <2|3> --weight <kg> --cal <kcal> \
  --meal-json '<nutrition estimate>' \
  [--meal-type lunch] [--timestamp <ISO-8601 UTC>] [--eaten] \
  [--schedule '<JSON>'] [--mode balanced] [--bmr <kcal>] [--region CN] \
  [--append]
```

| Param | Source | Description |
|-------|--------|-------------|
| `--data-dir` | fixed | `{workspaceDir}/data/meals` |
| `--tz-offset` | `USER.md > TZ Offset` | Seconds from UTC (e.g. 28800 = UTC+8) |
| `--meals` | `health-profile.md > Meals per Day` | 2 or 3 |
| `--weight` | `PLAN.md` or `health-profile.md` | Current weight in kg |
| `--cal` | `PLAN.md > Daily Calorie Range` | Daily calorie target in kcal |
| `--meal-json` | §1.5 nutrition estimate | Single-line JSON array (see format below) |
| `--meal-type` | User's exact words ONLY | Only if user explicitly names the meal. Otherwise ALWAYS omit — script auto-detects. Do NOT infer or retry. |
| `--timestamp` | Inbound message metadata | ISO-8601 UTC timestamp |
| `--eaten` | §1.3 meal timing | Pass when user already ate (omit = before-eating) |
| `--schedule` | `health-profile.md > Meal Schedule` | JSON: `{"breakfast":"07:00","lunch":"12:00","dinner":"18:00"}` |
| `--mode` | `health-profile.md > Diet Mode` | `balanced`, `high_protein`, `low_carb`, `keto`, `mediterranean`, `plant_based`, `if_16_8`, `if_5_2` |
| `--bmr` | `PLAN.md` | BMR in kcal (for case_d evaluation) |
| `--append` | context | Adding to already-logged meal. Only NEW items; script auto-merges. |
| `--region` | `USER.md > Language` | `CN` for China (enables produce tracking) |

**`--meal-json` format:**
```json
[{"name":"白米饭","amount_g":200,"calories":230,"protein_g":4,"carbs_g":50,"fat_g":0.5,"vegetables_g":0,"fruits_g":0}]
```

Each item: `name`, `amount_g`, `calories`, `protein_g`, `carbs_g`, `fat_g`. CN region: also `vegetables_g`, `fruits_g`.

> 🚫 **GATE CHECK (photo meals):** Every `amount_g` MUST come from the §1.4 pipeline. Verify your thinking contains filled Step 2/Step 3 templates for EACH item. If not — STOP, go back to §1.4.

Returns: `meal_detection`, `existing_meals`, `missing_meals`, `save`, `evaluation`, `produce`. Same meal name overwrites (corrections).

**Post-response:** Call `save-evaluation` to persist suggestion text:
```bash
python3 {baseDir}/scripts/nutrition-calc.py save-evaluation \
  --data-dir {workspaceDir}/data/meals \
  --meal-name <meal_name> \
  --suggestion-text '<suggestion text>' \
  --tz-offset <seconds>
```

### `delete-meal`

```bash
python3 {baseDir}/scripts/nutrition-calc.py delete-meal \
  --data-dir ... --tz-offset <seconds> --meal-name <string> \
  [--date YYYY-MM-DD] [--weight <kg> --cal <kcal> --meals <2|3>] [--region CN]
```

### `query-day`

```bash
python3 {baseDir}/scripts/nutrition-calc.py query-day \
  --data-dir ... --tz-offset <seconds> --weight <kg> --cal <kcal> --meals <2|3> \
  [--date YYYY-MM-DD] [--region CN]
```

### `load`

```bash
python3 {baseDir}/scripts/nutrition-calc.py load --data-dir {workspaceDir}/data/meals [--date 2026-02-27]
```

### `calibration-lookup`

```bash
python3 {baseDir}/scripts/nutrition-calc.py calibration-lookup \
  --data-dir {workspaceDir}/data/meals \
  --foods '<JSON array of food name strings>'
```

Returns `matches` (`user_portion_g`, `correction_count`, match type) and `no_match`. Stored in `health-preferences.md > ## Portion Calibrations`.

### `oil-calibration-lookup`

```bash
python3 {baseDir}/scripts/nutrition-calc.py oil-calibration-lookup \
  --data-dir {workspaceDir}/data/meals \
  --foods '<JSON array of food name strings>'
```

Returns `matches` (`oil_per_100g`, `correction_count`) and `no_match`. Stored in `health-preferences.md > ## Oil Calibrations`.

---

## Workflow — Log Food

### Step 1: Recognize & Log

#### 1.1 Collect input

- Merge consecutive messages
- Photo: interior/filling not visible → generic name ("包子" not "鲜肉包"). Specific only if user stated or visible in photo.

#### 1.2 Meal type

- User explicitly names it → `--meal-type` (overrides time of day)
- Otherwise ALWAYS omit — script auto-detects. Do NOT infer or retry.

#### 1.3 Meal timing

- Infer from tense/context → pass `--eaten` if already ate
- Ambiguous → check time vs `health-profile.md > Meal Schedule` (fallback: breakfast 5–10h, lunch 11–14h, dinner 17–21h)
- Default: before-eating
- Backfilled meals: always "already eaten"

#### 1.3b Calibration lookup

Call `calibration-lookup` with food names from 1.1:
- `correction_count ≥ 1` → **use `user_portion_g` as default.** One correction is enough. Do NOT wait for a second correction.
- **Override exception:** ONLY ignore when photo **clearly and unmistakably** shows a very different portion. "Might be different" is NOT enough — trust the calibration.
- `match_type: "alias"` / `"alias_contains"` → use `matched_key` name and its calibration
- Do NOT mention calibration to user

**Safety net:** `log-meal` returns `calibration_warnings` when amount differs >20% from calibration — confirm with user.

#### 1.4 Estimate portions

**Photo present → 3-step pipeline:**

> 🚫 **HARD RULE:** `read` `{baseDir}/references/portion-estimation.md` first. No exceptions.

**Step 0 — Scene inventory (REQUIRED):**
```
Scene: [N] containers
1. [type] — contains [food] — [single/multi-section]
```
Do NOT merge separate containers.

**Step 1 — Anchor:**
- Known object (egg, chopstick, spoon, phone, hand) → `§ Photo Reference Objects`
- Container matches known type → `§ Common Container Sizes`
- None found → single-serving default, prefix `~`, **set `_no_anchor = true`**

**Anchor check (REQUIRED in thinking):**
```
Anchor check:
  Reference object: [object name / "none"]
  Container type:   [matched type / "unrecognized"]
  → Anchor status:  [anchored / no_anchor]
```

**Step 2 — Measure (REQUIRED in thinking for EACH container):**
```
Container [N]: [type]
  Matched: [reference entry or "estimated from anchor"]
  Volume: [X] ml
  Fill level: [Y]% ([from § Fill Level])
  Effective volume: [X] × [Y]% = [Z] ml
```

> Uncertain container size → pick the **larger** estimate.

**Step 3 — Convert (REQUIRED in thinking for EACH food):**
```
[food name]:
  Volume share: [Z] ml × [P]% = [V] ml
  Density: [D] g/ml (from § Volume → Weight Conversion: [category])
  Cooked weight: [V] × [D] = [W] g
  → amount_g = [W]
```
Mixed dishes — split by component:
```
[dish name] total effective volume: [V] ml
  - [vegetable]: [V] × [veg%]% = [Vv] ml × [Dv] g/ml = [Wv] g cooked
    Raw weight: [Wv] ÷ [shrinkage ratio] = [Rv] g → vegetables_g = [Rv]
  - [meat]: [V] × [meat%]% = [Vm] ml × [Dm] g/ml = [Wm] g
  Total: → amount_g = [W]
```

**⚠️ `vegetables_g` = raw weight of VEGETABLES ONLY.** Exclude meat, tofu, eggs.

**Self-check (REQUIRED):**
- `amount_g` ≤ effective volume × 1.0 g/ml?
- `vegetables_g` (raw) ≤ `amount_g` (cooked) × vegetable share %?
- Every number traces to a calculation? If any is a guess → redo.

**No photo, no portion stated** → single-serving default, prefix `~`.

Flag items **≥ 2× standard** — Step 2 decides whether to clarify.

#### 1.5 Estimate nutrition

For each food: `calories`, `protein_g`, `carbs_g`, `fat_g`, `amount_g`.
- CN region: also `vegetables_g`, `fruits_g`. Starchy vegetables (potato, sweet potato, taro, corn) → carbs, NOT vegetable target.
- Source: USDA FoodData Central primary; regional foods → China CDC.
- `vegetables_g` = raw weight (use shrinkage ratios from `references/portion-estimation.md`)

#### 1.5a Oil calibration lookup

Call `oil-calibration-lookup` with food names:
- `correction_count ≥ 1` → **use `oil_per_100g` as default.** One correction is enough.
- **Override exception:** ONLY ignore when photo clearly shows very different oil level. When in doubt, trust calibration.
- Do NOT mention calibration to user

#### 1.5b Oil estimation

> 🚫 **HARD RULE:** `read` `{baseDir}/references/oil-estimation.md` first. No exceptions.

**Rule priority (first match wins):**
1. Oil calibration from §1.5a
2. High-absorption dish → `references/oil-estimation.md § High-Absorption Dishes`
3. 凉拌菜 → 3–5g/100g
4. Deep-fried → 0g extra
5. Soup → visible floating oil only; clear broth → 0g
6. Photo → visual cue table in `references/oil-estimation.md`
7. 食堂/外卖/餐厅 → 7g/100g
8. Unknown → 7g/100g

Fold oil into each dish's `calories` and `fat_g`.

**Oil template (REQUIRED in thinking for each cooked dish):**
```
Oil — [dish name]:
  Rule: [# matched]
  Oil: [X]g/100g → [W]g dish → [oil]g → +[kcal] kcal, +[fat]g fat
```

### Step 2: Respond

Follow `{baseDir}/references/response-schemas.md` for format.

- Calorie unit: US → "Cal"; others → "kcal"
- ≥ 2× normal items → ONE clarification question, everyday references (not grams)
- `_no_anchor = true` → append: `📸 小提示：下次拍照时把拳头放在食物旁边，我能估得更准哦～` (skip if already reminded within last 3 meals same day)
- `has_missing = true` → append PS about assumed meals, invite corrections
- `needs_clarification` → append hint(s) directly; multiple → merge into ONE sentence (see `references/response-schemas.md § Ambiguous Food`)

---

## Workflow — Query Progress

`query-day` → format per `references/response-schemas.md`.

---

## Workflow — Correct / Delete / Append

- **Append:** `log-meal --append` with NEW items only. Do NOT re-send old items.
- **Correct:** `log-meal` with same meal name (overwrites). Calibrations auto-saved.
- **Delete:** `delete-meal`

---

## Skill Routing

P2 (Data Logging) — defer to P0 (safety) and P1 (emotional support). See `SKILL-ROUTING.md`.
