---
name: weight-gain-strategy
version: 1.0.0
description: "Detect and respond to upward weight trends after weigh-ins or when the user asks why their weight is increasing. Use for: (1) consecutive weight increases detected by post-weigh-in deviation checks, (2) explicit weight-gain questions like 'why am I gaining weight' or '体重怎么涨了'. Provides graduated support from reassurance to cause analysis to temporary adjustment strategies. Do not use when emotional distress needs higher-priority support or when weight-focus should be avoided (history_of_ed / avoid_weight_focus flags)."
metadata:
  openclaw:
    emoji: "mag"
    homepage: https://github.com/NanoRhino/weight-loss-skill
---

# Weight Gain Strategy

Detect upward weight trends and respond with graduated support — from
reassurance on the first increase, to guided cause discovery, to full
diagnosis with adjustment strategies — matching the response depth to how
persistent the trend is.

## Routing Gate

**Entry paths:**
- **Auto (post-weigh-in):** `weight-tracking` calls `deviation-check` after every weight log → severity returned → respond per severity table below.
- **Manual:** User asks about weight gain ("why am I gaining weight", "体重怎么涨了") → skip streak logic → **check Skip conditions first** (no PLAN.md, health flags, emotional distress — if any skip condition is met, do NOT enter this skill even on manual trigger) → run `analyze` directly → Interactive Flow Step 1.

**Skip — do NOT enter this skill if:**
- No `PLAN.md` exists (no plan to deviate from)
- `USER.md > Health Flags` contains `avoid_weight_focus` or `history_of_ed`
- User shows emotional distress about weight → defer to `emotional-support` (P1 priority)

## Principles

1. **Normalize first.** Lead with reassurance, then dig into data.
2. **Data + habits before opinions.** Every diagnosis must cite actual numbers or observable behavioral patterns. Never speculate without evidence.
3. **Escalate gradually.** Response depth follows the streak. Never skip levels or jump to strategy on a first increase.
4. **Collaborate, don't force.** The user can opt in or out at every step. Playful challenges are fine; pushing past a "no" is not.
5. **Keep it light.** Witty friend, not stern doctor. Data rigorous, delivery fun.

---

## Severity → Response

| Severity | When | Behavior |
|----------|------|----------|
| `none` | No increase | Weight stable or down — just confirm the log. |
| `light` | First increase, or within 7 days of cause-check | Quick data glance + comfort + encouragement. No deep analysis. |
| `cause-check` | ≥3 days after light, or ≥7 days after previous cause-check | Run `analyze` → 告诉用户增重原因 → 给 3 个可选改变 → 用户选 → 建习惯。See `references/cause-check-flow.md`. |

---

## Diagnosis Dimensions

The `analyze` command outputs **raw statistics only** — no `detected: true/false` judgments. The AI interprets these numbers in context (user history, lifestyle, chat context) to determine causes.

### Output fields

| Field | What it contains | AI uses it for |
|-------|-----------------|----------------|
| `calorie_stats` | avg/min/max/std_dev, days over target, days under 60%, daily breakdown | Surplus, volatility, binge/restrict patterns |
| `protein_stats` | avg daily g, recommended g (weight×1.2), days below 70% | Protein deficit detection |
| `exercise_stats` | This week vs last week sessions & minutes | Exercise decline |
| `logging_stats` | Coverage %, single-meal days, unlogged days | Data reliability |
| `weight_pattern` | Largest daily jump + dates | Sudden spike (water retention) |
| `food_list` | Raw food names (dedupe, up to 50) | Food quality, variety, processed patterns |
| `data_confidence` | sufficient flag, issues list | Whether to analyze or ask for more data first |
| `active_strategy` | Current strategy type/dates if active | Whether to suppress new interventions |
| `suggested_actions` | Concrete script-driven actions (not AI judgment) | Strict mode, set calorie target, suppress strategy |

> ⚠️ **`suggested_actions` are deterministic rules, not AI opinions:**
> - `strict_mode`: coverage < 50% or >50% single-meal days → enter strict mode (see `references/strict-mode.md`). Do NOT create new meal reminder crons — they already exist. Strict mode makes existing reminders more insistent.
> - `set_calorie_target`: no calorie target set → cannot do surplus analysis
> - `suppress_new_strategy`: active strategy hasn't expired → don't start a new cause-check

> 🎯 **AI creates targeted habits based on analysis — NOT generic meal reminders:**
> After analyzing the raw data, the AI identifies the specific problem and creates a habit that addresses it. Examples:
> - Protein low → habit: "每餐加一份蛋白质（鸡蛋/鸡胸/豆腐）"
> - Calorie volatility (binge/restrict) → habit: "每天吃到{目标}附近，不跳餐"
> - Late-night eating pattern → habit: "8点前吃完晚饭"
> - Weekend overeating → habit: "周末拍照打卡，不多不少"
> - Food quality issues → habit: specific swap based on actual foods (e.g. "方便面换成挂面煮蛋")
> - Snacking excess → habit: specific swap (e.g. "下午零食换成酸奶/坚果")
>
> **NEVER create habits for:** meal logging reminders, weight check-ins, or anything that already has a cron job.
> - `set_calorie_target`: no calorie target set → cannot do surplus analysis
> - `suppress_new_strategy`: active strategy hasn't expired → don't start a new cause-check

> ⚠️ **AI-driven analysis:** The script provides numbers; the AI decides what they mean. A std_dev of 967 kcal might be binge/restrict — or a user transitioning diets. The AI considers context.

---

## Analysis Script

Script path: `python3 {baseDir}/scripts/analyze-weight-trend.py`

Commands: `analyze`, `deviation-check`, `save-strategy`, `check-strategy`.
See `references/script-api.md` for full usage, parameters, and return schemas.

> ⚠️ **`deviation-check` anti-repeat:** If `weight-gain-strategy.json` contains an `active_strategy` (status=active, end_date ≥ today), cause-check is downgraded to light (simple comfort). Light responses have a 1-day cooldown. cause-check becomes available again ≥3 days after light or ≥7 days after a previous cause-check.

---

## Safety Rules

- **Calorie floor:** Never suggest intake below max(BMR, 1000 kcal/day).
- **Exercise safety:** For sedentary users or those with health conditions, start with walking only.
- **No shame, no blame.** Frame adjustments as experiments, not corrections.

---

## References

| File | Contents |
|------|----------|
| `references/cause-check-flow.md` | Full cause-check guided discovery flow (Steps A–D), pact table, pact rules |
| `references/interactive-flow.md` | Interactive Flow Steps 1–3, strategy types, ranking rules |
| `references/diagnosis-templates.md` | Per-factor diagnosis lines, consequence lines, motivation lines |
| `references/script-api.md` | Script commands, parameters, return schemas |
| `references/strict-mode.md` | Strict mode: trigger, behavior rules, duration, failure escalation, ownership |
| `references/data-schemas.md` | Data sources, strategy JSON schema, skill integration, routing conflicts, edge cases |
