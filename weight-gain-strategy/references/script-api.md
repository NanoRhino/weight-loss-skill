# Script API — analyze-weight-trend.py

Script path: `python3 {baseDir}/scripts/analyze-weight-trend.py`

## Command: `analyze`

```bash
python3 {baseDir}/scripts/analyze-weight-trend.py analyze \
  --data-dir {workspaceDir}/data \
  --weight-script {weight-tracking:baseDir}/scripts/weight-tracker.py \
  --nutrition-script {diet-tracking-analysis:baseDir}/scripts/nutrition-calc.py \
  --exercise-script {exercise-tracking-planning:baseDir}/scripts/exercise-calc.py \
  --plan-file {workspaceDir}/PLAN.md \
  --health-profile {workspaceDir}/health-profile.md \
  --tz-offset {tz_offset} \
  --window 14
```

**Returns** a JSON object:

```json
{
  "trend": {
    "direction": "up",
    "net_change_kg": 0.8,
    "net_change_display": "0.8 kg",
    "window_days": 14,
    "readings": [
      {"date": "2026-03-10", "value": 74.2, "unit": "kg"},
      {"date": "2026-03-17", "value": 74.6, "unit": "kg"},
      {"date": "2026-03-24", "value": 75.0, "unit": "kg"}
    ]
  },
  "diagnosis": {
    "calorie_surplus": {
      "detected": true,
      "avg_daily_intake": 1850,
      "target": 1600,
      "surplus_kcal": 250,
      "days_over_target": 10,
      "days_total": 14
    },
    "exercise_decline": {
      "detected": true,
      "current_week_sessions": 1,
      "previous_week_sessions": 3,
      "current_week_minutes": 30,
      "previous_week_minutes": 120
    },
    "logging_gaps": {
      "detected": false,
      "unlogged_days": 2,
      "total_days": 14
    },
    "possible_water_retention": {
      "detected": false,
      "note": "Sudden spike ≥ 0.5 kg in 1–2 days without calorie surplus"
    },
    "normal_fluctuation": {
      "detected": false,
      "note": "Net change < 0.5 kg over 14 days with no sustained trend"
    }
  },
  "top_factors": ["calorie_surplus", "exercise_decline"],
  "suggested_strategies": [
    {
      "type": "reduce_calories",
      "description": "Reduce daily intake by 150 kcal",
      "target_kcal": 1450,
      "duration_days": 7,
      "expected_impact": "~0.15 kg deficit per week"
    },
    {
      "type": "increase_exercise",
      "description": "Add 2 more exercise sessions this week",
      "target_sessions": 3,
      "target_minutes_per_session": 30,
      "duration_days": 7,
      "expected_impact": "~200 kcal additional burn per session"
    }
  ],
  "energy_balance_check": {
    "available": true,
    "tdee_from_plan": 2093,
    "plan_duration_days": 33,
    "implied_surplus_kcal": 6930,
    "raw_balance_kcal": -14972,
    "adjusted_avg_daily_intake": 1556,
    "adjusted_balance_kcal": -7532,
    "adjustment": {
      "confidence": "high",
      "missing_by_meal": {"breakfast": 3, "lunch": 1},
      "estimated_by_meal": {"breakfast": 3, "lunch": 1},
      "unestimatable_by_meal": {},
      "total_added_kcal": 1660
    },
    "verdict": "contradicts_after_adjustment"
  }
}
```

**`energy_balance_check.verdict` values:**
- `within_noise` — implied surplus < 300 kcal; no meaningful contradiction
- `consistent` — data trustworthy; raw balance matches weight change
- `consistent_after_adjustment` — raw contradicted, but estimated missing meals resolve it
- `contradicts_after_adjustment` — even after estimating missing meals, still contradicts
- `insufficient_data` — missing PLAN.md deficit/target, or all missing meals unestimatable

**`adjustment.confidence` values:**
- `none_needed` — no missing meal slots detected
- `high` — all missing meals estimated
- `partial` — some estimated, some unestimatable
- `none` — no meals could be estimated (verdict forced to `insufficient_data`)
```

## Command: `deviation-check`

Lightweight post-weigh-in check. Called by `weight-tracking` after every weight
log. Counts **consecutive weigh-in increases** (streak) and maps to a graduated
severity level.

```bash
python3 {baseDir}/scripts/analyze-weight-trend.py deviation-check \
  --data-dir {workspaceDir}/data \
  --plan-file {workspaceDir}/PLAN.md \
  --health-profile {workspaceDir}/health-profile.md \
  --user-file {workspaceDir}/USER.md \
  --plan-start-date {plan_start_date} \
  --tz-offset {tz_offset}
```

The `--plan-start-date` is read from the `开始日期` / `Start date` field in
`PLAN.md`. If not passed, the script also attempts to parse it directly from
`PLAN.md`. Used to detect the adaptation period (first 14 days).

**Returns:**

```json
{
  "triggered": true,
  "severity": "comfort",
  "consecutive_increases": 1,
  "adaptation_period": false,
  "latest_increase_kg": 0.5,
  "window": {
    "start_date": "2026-03-10",
    "end_date": "2026-03-24",
    "days": 14
  },
  "latest_weight": 75.0,
  "latest_unit": "kg",
  "readings_count": 4,
  "temporary_causes": [
    {
      "cause": "yesterday_overeating",
      "message": "Yesterday's intake was 2400 kcal (+41% over target)...",
      "yesterday_cal": 2400,
      "target_cal": 1700,
      "overshoot_kcal": 700
    }
  ],
  "deviation_context": {
    "plan_rate_kg_per_week": 0.6,
    "expected_change_kg": -1.2,
    "actual_change_kg": 0.4,
    "deviation_kg": 1.6
  },
  "recommendation": "Weight is up compared to last weigh-in. Comfort and encourage..."
}
```

**Severity levels (streak-based):**
- `none` (streak 0) — weight stable or down, no action
- `comfort` (streak 1) — first increase, comfort and encourage
- `cause-check` (streak 2–3) — consecutive increases, run `analyze` to identify causes and tell user what to watch
- `significant` (streak 4+) — sustained trend, run `analyze` with full diagnosis + strategy options

**Temporary cause detection** (used as context, especially at `comfort` level):
- `yesterday_overeating` — previous day's calorie intake ≥ 30% over target
- `possible_menstrual_cycle` — female user, sudden ≥ 0.5 kg spike in ≤ 5 days while average weekly intake is within target
- `sudden_spike` — ≥ 0.8 kg jump in ≤ 2 days (water/sodium retention)

**Design notes:**
- Requires ≥ 2 readings (loads last 28 days for accurate streak counting)
- Severity is driven purely by consecutive increase count, not deviation magnitude
- `deviation_context` provides plan deviation data as informational context (not for severity)
- `adaptation_period` is a modifier flag — adds "body adjusting" context to any severity level
- Temporary causes are always detected when triggered, used as context in responses (not as severity overrides)

## Command: `save-strategy`

```bash
python3 {baseDir}/scripts/analyze-weight-trend.py save-strategy \
  --data-dir {workspaceDir}/data \
  --strategy-type reduce_calories|increase_exercise|combined \
  --params '{"target_kcal": 1450, "duration_days": 7}' \
  --tz-offset {tz_offset}
```

Saves the active strategy to `data/weight-gain-strategy.json`.

## Command: `check-strategy`

```bash
python3 {baseDir}/scripts/analyze-weight-trend.py check-strategy \
  --data-dir {workspaceDir}/data \
  --tz-offset {tz_offset}
```

Returns the current active strategy and progress against it (for use by
`weekly-report` and `notification-composer`).
