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

| Severity | Streak | Behavior |
|----------|--------|----------|
| `none` | 0 | Weight stable or down — just confirm the log. |
| `comfort` | 1 | Comfort and encourage. Mention temporary causes lightly. See `references/diagnosis-templates.md` for examples. |
| `cause-check` | 2–3 | Multi-step guided discovery: hook → user guesses → data + challenge → mutual pact → habit created in `habit-builder`. See `references/cause-check-flow.md`. |
| `significant` | 2–3 (7d after cause-check) or 4+ | Follow-up analysis with **承接感**. Reference the previous cause-check conversation ("上次我们聊过…"), note trend continued, escalate to strategy. When `previous_context` is present in script output, use it for callback tone. See `references/interactive-flow.md`. |

---

## Diagnosis Dimensions

The `analyze` command evaluates these factors:

| Factor | Detection | Strategy |
|--------|-----------|----------|
| `calorie_surplus` | Average intake > target by 50+ kcal | Reduce daily intake (max -300 kcal) |
| `processed_food` | ≥30% processed items or ≥5 items flagged | Swap processed → whole foods habit |
| `low_protein` | Avg protein < 70% of recommended (weight×1.2g) | Add protein source per meal |
| `exercise_decline` | Current week < previous week sessions | Restore exercise sessions |
| `logging_gaps` | <50% of days have logged meals | Strict mode + daily logging habit |
| `possible_water_retention` | Sudden ≥0.5kg spike, no calorie surplus | Reassurance, wait it out |
| `normal_fluctuation` | Net change < 0.3kg | Reassurance, no action |

---

## Analysis Script

Script path: `python3 {baseDir}/scripts/analyze-weight-trend.py`

Commands: `analyze`, `deviation-check`, `save-strategy`, `check-strategy`.
See `references/script-api.md` for full usage, parameters, and return schemas.

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
