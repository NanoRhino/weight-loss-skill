---
name: periodic-recalc
version: 2.0.0
description: "Recalculates the user's daily calorie target every 4 weeks based on current weight. Updates PLAN.md with new TDEE, calories, and macro ranges. Reviews diet mode fit."
---

# Periodic Recalculation

## Step 0: Read PLAN.md (MANDATORY — do this FIRST)

Before running any script, **read the user's `{workspaceDir}/PLAN.md`** and extract these values:

| Field | Type | Description |
|-------|------|-------------|
| `current_calories` | int | Current daily calorie target |
| `target_weight` | float | Target weight in kg |
| `tdee` | int | Current TDEE estimate (0 if not stated) |
| `activity` | string | Activity level: `sedentary`, `lightly_active`, `moderately_active`, or `very_active` |
| `diet_mode` | string | Diet mode: `balanced`, `high_protein`, `low_carb`, `keto`, `mediterranean`, `plant_based`, `usda`, `if_16_8`, `if_5_2` |

PLAN.md has no fixed format — it may be in English, Chinese, bullet points, prose, or markdown tables. Use your language understanding to extract the values regardless of formatting. If a value is not explicitly stated, use these defaults:
- `activity`: `lightly_active`
- `diet_mode`: `balanced`
- `tdee`: `0` (script will calculate it)

---

## Overview

- **Type:** Inline post-weekly-report task
- **Trigger:** Every 4 weeks on Sunday (after weekly-report)
- **Dependencies:** weight-loss-planner, weight-tracking

Recalculates daily calorie target based on current weight. Updates PLAN.md with new TDEE, calorie target, and macro ranges. Reviews whether actual eating pattern matches the current diet_mode.

---

## Trigger Conditions

1. **Primary:** Called inline by weekly-report skill after sending the weekly report (Sunday)
2. **Secondary:** When weight-tracking logs a new weight AND `pending-recalc.json` exists with `reason="awaiting_weight"`

**25 天门的真值源：** `data/last-recalc-summary.json` 的 `date` 字段。`periodic-recalc.py` 在每次 `action="recalculated"` 时自动写入 `date` + 核心数值（weight_from, weight_to, old_calories, new_calories）；LLM 后续按本 SKILL "After sending" 那块补全完整字段（cycle_number / message_sent 等）。PLAN.md 不再用于 25 天判断。

---

## Execution

After extracting values from PLAN.md (Step 0), run:

```bash
python3 {baseDir}/scripts/periodic-recalc.py \
  --workspace {workspaceDir} \
  --planner-calc {weight-loss-planner:baseDir}/scripts/planner-calc.py \
  --current-calories <extracted> \
  --target-weight <extracted> \
  --tdee <extracted> \
  --activity <extracted> \
  --diet-mode <extracted>
```

All `--current-calories`, `--target-weight`, `--tdee`, `--activity`, `--diet-mode` are optional CLI args. When provided, the script skips its own PLAN.md parsing. Always provide them — that's the whole point.

---

## Handling Output

Based on the JSON output `action` field:

### `action: "skipped"`

Less than 25 days since last recalc. Do nothing — silently exit.

### `action: "recalculated"`

Plan has been updated. Compose a cycle review + new cycle message for the user.

**Message structure (in user's language — check USER.md):**

1. 🎉 **Celebrate** the completed cycle — the user stuck with it for 4 weeks. Make them feel proud. Reference their weight change.
2. **Clear divider** between old cycle review and new cycle plan. The user should feel "previous page closed, new page begins."
3. **Explain** why the new numbers are what they are — warm, human tone. Not "based on thermodynamic principles" but "you're lighter now, your body needs a bit less." Reference:
   - `weight_change`: how much lost? fast or slow?
   - `old_calories` vs `new_calories`: up or down?
   - `rate_kg_per_week` change
   - Actual intake vs target (read `data/meals/` last 28 days)
   - If progress underperformed: gently note possible recording gaps or portion underestimation. Never accuse.
4. **New cycle numbers:** daily calorie target, expected rate (kg/week), 4-week forecast
5. **Macro ranges** (protein/carbs/fat in grams) — integers only, no decimals
6. **Ask for confirmation:** "Does this work for you? Happy to adjust if you want."

**Precision:** All nutrition values as integers (e.g. 1359 kcal, protein 70-93g). No decimals.

**Confirmation flow:**
- No reply = accepted. Proceed with new plan.
- User has concerns → adjust and rewrite PLAN.md accordingly.

**After sending,** write `{workspaceDir}/data/last-recalc-summary.json`:

注：脚本已经预写了 `date` / `weight_from` / `weight_to` / `old_calories` / `new_calories` 字段，你只需要 merge 补全 `cycle_number` / `old_rate` / `new_rate` / `awaiting_confirmation` / `message_sent` 等剩余字段（读现有 JSON、merge、写回）。

```json
{
  "date": "<today>",
  "cycle_number": <N>,
  "weight_from": <previous>,
  "weight_to": <current>,
  "old_calories": <old>,
  "new_calories": <new>,
  "old_rate": <old>,
  "new_rate": <new>,
  "awaiting_confirmation": true,
  "message_sent": "<full message text>"
}
```

**Then** run diet-mode review:

```bash
python3 {baseDir}/scripts/diet-mode-review.py --workspace {workspaceDir} --days 28
```

- `action: "recommend_change"` → Ask user if they want to switch diet mode. Show actual macro ratios vs expected. Frame as: "Your eating has naturally shifted toward [mode] — want to update?"
- `action: "no_change"` → Silently continue
- `action: "insufficient_data"` → Silently continue

### `action: "awaiting_weight"`

Tell the user: "It's time for your 4-week plan recalculation! Please weigh yourself when you can, and I'll update your plan once you log your weight."

Write `pending-recalc.json`:
```json
{"created_at": "<ISO>", "reason": "awaiting_weight", "cycle_date": "<today>"}
```

### `action: "on_leave"`

Write `pending-recalc.json`:
```json
{"created_at": "<ISO>", "reason": "on_leave", "cycle_date": "<today>"}
```

Do NOT notify the user. Recalc triggers on first Sunday after leave ends.

---

## Secondary Trigger: Weight Logged

When weight-tracking logs a new weight, run:

```bash
python3 {baseDir}/scripts/check-pending-recalc.py --workspace {workspaceDir}
```

If `{"should_trigger": true}`: run the full recalc flow, then delete `pending-recalc.json`.

---

## User Reply Handling (Main Session)

When user replies to the recalc message, check `data/last-recalc-summary.json`:

If `awaiting_confirmation: true`:
- User confirms → set `awaiting_confirmation: false` (PLAN.md already updated by script)
- User wants changes → recalculate with their preferences, update PLAN.md, confirm
- No reply for 3 days → treat as confirmed

**Semantic mapping:**
- "previous pace / old calories / last cycle's" → `old_rate`, `old_calories`
- "current / new / this plan" → `new_rate`, `new_calories`
- "keep the old pace" = user wants `old_rate`, not the new slower rate → recalculate with that rate

---

## Data Dependencies

| File | Access | Purpose |
|------|--------|---------|
| `PLAN.md` | Read + Write | Source of current plan; updated with new values |
| `data/weight.json` | Read | Most recent weight |
| `data/leave.json` | Read | Leave status |
| `data/pending-recalc.json` | R/W/Delete | Deferred recalc tracking |
| `data/last-recalc-summary.json` | Write | Context for user reply handling |
| `data/meals/*.json` | Read | Actual eating patterns (diet-mode-review) |
| `health-profile.md` | Read | Activity level, demographics |

---

## Important Notes

- **Always recalculate** — no "too small to bother" threshold. Each 4-week cycle is a new phase.
- **Macro formula** (must match onboarding):
  - Protein: 1.2–1.6 g/kg × target_weight (high_protein: 1.4–1.8)
  - Fat: diet_mode percentage × daily_calories
  - Carbs: remainder
- If `floor_clamped: true`: weekly rate was reduced because calories hit BMR floor. Mention this to user.
- Delete `pending-recalc.json` after successful recalc.
