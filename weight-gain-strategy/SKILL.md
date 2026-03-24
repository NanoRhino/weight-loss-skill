---
name: weight-gain-strategy
version: 1.0.0
description: "Detect upward weight trends, analyze probable causes from user data (diet, exercise, habits), and produce a personalized adjustment strategy. Trigger when the weekly report or weight-tracking data shows a sustained weight increase (≥ 2 consecutive weigh-ins trending up, or net gain over a 7-day window), or when the user explicitly asks why their weight is rising. Trigger phrases: 'why am I gaining weight', 'weight keeps going up', 'gaining weight', '体重怎么涨了', '越来越重了', '为什么体重上升', '体重反弹了'."
metadata:
  openclaw:
    emoji: "mag"
    homepage: https://github.com/NanoRhino/weight-loss-skill
---

# Weight Gain Strategy

> **SILENT OPERATION:** Never narrate internal actions, skill transitions, or tool calls to the user. No "Let me check...", "Now I'll transition to...". Just do it silently and respond with the result.

Detect upward weight trends, diagnose probable causes by cross-referencing
diet, exercise, and habit data, then collaborate with the user to produce a
concrete, time-bound adjustment strategy for the coming 1–2 weeks.

## Principles

1. **Normalize first.** Weight fluctuations are normal. Never alarm the user — lead with reassurance, then dig into data.
2. **Data before opinions.** Every diagnosis must cite actual numbers from the user's logs. Never speculate without evidence.
3. **One strategy at a time.** Don't overwhelm with five changes. Pick the highest-leverage adjustment and commit to it.
4. **Collaborate, don't prescribe.** The user chooses the strategy; you provide options and recommendations.
5. **Respect the user's capacity.** If the user is already stressed, prioritize the easiest adjustment — not the most effective one.

---

## Trigger Conditions

### Automatic Trigger: Post-Weigh-In Deviation Check

After every weight log, `weight-tracking` calls the `deviation-check` command
to compare the user's recent trend against their PLAN.md target rate. This is
the **primary trigger path**.

**Severity → Response:**

| Severity | Behavior |
|----------|----------|
| `none` | No action. Weight is on track or within normal fluctuation. |
| `mild` | Append a gentle one-liner to the log confirmation. Single-ask rule applies — if the user ignores it, drop it. |
| `significant` | Run `analyze`, present cause analysis to the user (Step 1 only). Ask if they want to discuss adjustments before proceeding to Step 2. |

**Skip conditions:**
- No `PLAN.md` (no plan to deviate from)
- `USER.md > Health Flags` contains `avoid_weight_focus` or `history_of_ed`
- User is in first 2 weeks of plan (body is still adjusting)

### Automatic Trigger: Weekly Report

The `weekly-report` skill calls `analyze` when it detects:
- Net weight gain ≥ 0.3 kg (0.7 lbs) over the reporting week
- 2+ consecutive weigh-ins trending upward with no downward correction

When auto-triggered from weekly-report, this skill provides analysis data
back for inclusion in the Section 6 suggestions. It does NOT produce a
standalone message.

### Manual Trigger (user-initiated)

When the user explicitly asks about weight gain ("why am I gaining weight",
"体重怎么涨了"), this skill takes over as the primary responder and runs
the full interactive flow (Analysis → Discussion → Strategy).

---

## Data Sources

### Reads

| Path | Via | Purpose |
|------|-----|---------|
| `data/weight.json` | `weight-tracker.py load` | Weight trend (last 14–28 days) |
| `data/meals/YYYY-MM-DD.json` | `nutrition-calc.py load` | Daily calorie intake for the analysis window |
| `data/exercise.json` | `exercise-calc.py load` | Exercise frequency, duration, and calories burned |
| `PLAN.md` | Direct read | Calorie target, weekly loss rate |
| `health-profile.md` | Direct read | Activity level, meal schedule, unit preference |
| `health-preferences.md` | Direct read | Known preferences and constraints |
| `USER.md` | Direct read | Name, age, sex (for context) |
| `timezone.json` | Direct read | Timezone offset for date calculations |
| `engagement.json` | Direct read | Engagement stage |

### Writes

| Path | When |
|------|------|
| `data/weight-gain-strategy.json` | After the user confirms a strategy — stores the active strategy with start date, end date, type, and parameters |
| `health-preferences.md` | If the user reveals new preferences during the conversation (append only) |

---

## Analysis Script

Script path: `python3 {baseDir}/scripts/analyze-weight-trend.py`

### Command: `analyze`

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
  ]
}
```

### Command: `deviation-check`

Lightweight post-weigh-in check. Called by `weight-tracking` after every weight
log to determine if the user's trend deviates from PLAN.md.

```bash
python3 {baseDir}/scripts/analyze-weight-trend.py deviation-check \
  --data-dir {workspaceDir}/data \
  --plan-file {workspaceDir}/PLAN.md \
  --health-profile {workspaceDir}/health-profile.md \
  --tz-offset {tz_offset}
```

**Returns:**

```json
{
  "triggered": true,
  "severity": "mild",
  "window": {
    "start_date": "2026-03-10",
    "end_date": "2026-03-24",
    "days": 14
  },
  "plan_rate_kg_per_week": 0.6,
  "expected_change_kg": -1.2,
  "actual_change_kg": 0.4,
  "deviation_kg": 1.6,
  "latest_weight": 75.0,
  "latest_unit": "kg",
  "readings_count": 4,
  "recommendation": "Mention the trend gently. Offer to investigate if the user wants."
}
```

**Severity thresholds:**
- `none` — actual change tracks plan within 0.3 kg tolerance
- `mild` — actual weight gain 0.3–0.8 kg, OR deviation from plan 0.3–0.8 kg
- `significant` — actual weight gain > 0.8 kg, OR deviation from plan > 0.8 kg

**Design notes:**
- Requires ≥ 2 readings spanning ≥ 3 days (avoids false alarms from daily fluctuation)
- Reads `data/weight.json` directly (no subprocess call to weight-tracker.py) for speed
- Does NOT trigger full analysis — just a yes/no signal for `weight-tracking` to act on

### Command: `save-strategy`

```bash
python3 {baseDir}/scripts/analyze-weight-trend.py save-strategy \
  --data-dir {workspaceDir}/data \
  --strategy-type reduce_calories|increase_exercise|adjust_schedule|combined \
  --params '{"target_kcal": 1450, "duration_days": 7}' \
  --tz-offset {tz_offset}
```

Saves the active strategy to `data/weight-gain-strategy.json`.

### Command: `check-strategy`

```bash
python3 {baseDir}/scripts/analyze-weight-trend.py check-strategy \
  --data-dir {workspaceDir}/data \
  --tz-offset {tz_offset}
```

Returns the current active strategy and progress against it (for use by
`weekly-report` and `notification-composer`).

---

## Interactive Flow

Applies to both auto-triggered (post-weigh-in significant deviation) and
manual-triggered (user asks about weight gain) paths. **The key principle:
always show the cause analysis first — never jump straight to strategies.**

### Step 1: Analyze & Present Causes (always runs first)

1. Read `timezone.json` for tz_offset
2. Run the `analyze` command
3. Present findings to the user in a conversational, non-alarming way

**Presentation structure:**

**[Reassurance]** — One sentence normalizing weight fluctuation. Never open with bad news.

**[Trend summary]** — State the facts briefly:
- "Over the past {N} days, your weight went from {start} to {end} ({change})."

**[Diagnosis]** — For each detected factor in `top_factors`, explain it in plain language with data:

- **Calorie surplus:** "Your average daily intake was {avg} kcal — about {surplus} over your {target} target. You were over target on {X} out of {Y} days."
- **Exercise decline:** "You exercised {current} time(s) this week vs {previous} last week — that's about {diff} fewer minutes of activity."
- **Logging gaps:** "There were {X} days without meal logs, so we might be missing part of the picture."
- **Water retention:** "The jump looks sudden — could be water retention from {possible_cause}. This usually resolves in a few days."
- **Normal fluctuation:** "This is within normal daily fluctuation range — nothing to worry about."

**[Pause here — do NOT continue to Step 2 automatically]**

**[Transition to Step 2]** — "Want to talk about what we can adjust?" / "要不要聊聊怎么调整？"

If the diagnosis is `normal_fluctuation`, skip to a reassuring close — do NOT propose changes for normal fluctuation.

**Only proceed to Step 2 when the user explicitly agrees.** If the user
ignores the question, acknowledges without interest, or changes topic, drop it.
This ensures the user never feels pressured into a strategy discussion they
didn't ask for.

### Step 2: Discuss & Choose Strategy

Present 1–3 strategy options based on the `suggested_strategies` from the analysis. For each option:

**Format:**

```
Option {N}: {strategy_name}
{one-sentence description}
{expected_impact} over {duration}
```

**Strategy Types:**

#### A. Reduce Calories (`reduce_calories`)
- Reduce daily intake by 100–300 kcal (never below calorie floor)
- Suggest specific meal adjustments based on the user's logged meals (e.g., "swap the afternoon snack for fruit", "reduce rice portion at dinner by 1/3")
- Duration: 1–2 weeks, then reassess

#### B. Increase Exercise (`increase_exercise`)
- Add 1–3 more exercise sessions per week
- Suggest activities aligned with user's existing habits and preferences
- If user doesn't exercise, suggest walking 20–30 min/day as a starting point
- Duration: 1–2 weeks, then reassess

#### C. Adjust Schedule (`adjust_schedule`)
- Shift meal timing (e.g., earlier dinner, longer overnight fast)
- Only suggest if the user's current schedule has obvious issues (e.g., late-night eating pattern detected)
- Duration: 1 week trial

#### D. Combined (`combined`)
- A modest version of A + B (smaller calorie reduction + 1 extra session)
- For users who prefer balanced adjustments
- Duration: 1–2 weeks

**After presenting options:** Ask the user which feels most doable. Respect their choice. If they choose something suboptimal, support it — compliance beats optimization.

### Step 3: Confirm & Save Strategy

1. Confirm the chosen strategy with specific, actionable details:
   - What exactly changes (calorie target, number of sessions, specific meals)
   - For how long (start date → end date)
   - When to check in (midpoint and end)
2. Run `save-strategy` to persist the strategy
3. Close with encouragement — brief, genuine, no platitudes

**Do NOT:**
- Set up reminders here (that's `notification-manager`'s job)
- Modify PLAN.md (the strategy is temporary; PLAN.md is the long-term plan)
- Generate HTML reports

---

## Safety Rules

- **Calorie floor:** Never suggest intake below max(BMR, 1000 kcal/day). Read the floor from PLAN.md or recalculate via `planner-calc.py`.
- **Exercise safety:** For users who are sedentary or have health conditions noted in `USER.md`, start with walking and low-impact activities only.
- **Emotional awareness:** If the user shows signs of distress about the weight gain, defer to `emotional-support` per SKILL-ROUTING.md. Come back to strategy only when the user is ready.
- **No shame, no blame.** Never imply the weight gain is the user's fault. Frame adjustments as experiments, not corrections.
- **ED flags:** If `USER.md > Health Flags` contains `avoid_weight_focus` or `history_of_ed`, do NOT run this skill automatically. Only respond if the user explicitly asks, and focus on behaviors (activity, sleep, stress) rather than weight numbers.

---

## Strategy Data Schema

**File:** `data/weight-gain-strategy.json`

```json
{
  "active_strategy": {
    "type": "reduce_calories",
    "start_date": "2026-03-24",
    "end_date": "2026-03-31",
    "params": {
      "target_kcal": 1450,
      "original_target_kcal": 1600,
      "reduction_kcal": 150
    },
    "status": "active",
    "created_at": "2026-03-24T10:00:00+08:00"
  },
  "history": [
    {
      "type": "increase_exercise",
      "start_date": "2026-03-10",
      "end_date": "2026-03-17",
      "params": {
        "target_sessions": 3,
        "target_minutes_per_session": 30
      },
      "status": "completed",
      "outcome": "weight stabilized"
    }
  ]
}
```

---

## Integration with Other Skills

| Skill | Integration |
|-------|-------------|
| `weekly-report` | Calls `analyze` to include weight trend diagnosis in Section 6 suggestions. Calls `check-strategy` to report on active strategy progress. |
| `notification-composer` | Reads `check-strategy` output to optionally include mid-week strategy check-in reminders. |
| `weight-tracking` | Source of weight data. This skill reads only — never writes to `data/weight.json`. |
| `diet-tracking-analysis` | Source of meal data. This skill reads only — never writes to `data/meals/`. |
| `exercise-tracking-planning` | Source of exercise data. This skill reads only — never writes to `data/exercise.json`. |
| `emotional-support` | Takes priority (P1) when user shows distress about weight gain. This skill defers. |
| `weight-loss-planner` | Owns PLAN.md. This skill reads the plan but never modifies it. Strategies are temporary overlays. |

---

## Skill Routing

**Priority Tier: P3 (Planning)** — same tier as `weight-loss-planner` and `meal-planner`.

### Conflict Patterns

**Weight gain strategy + Emotional distress (P3 vs P1):**
Emotional support leads. If user says "I'm gaining weight and I hate myself",
`emotional-support` takes over. Weight gain analysis happens later, only if
the user asks for it.

**Weight gain strategy + Diet logging (P3 vs P2):**
If the user logs food AND asks about weight gain in the same message, log the
food first (P2), then provide the weight gain analysis.

**Weight gain strategy + Weight-loss planner (same tier):**
If the user asks to redo their plan because of weight gain, route to
`weight-loss-planner` for a full recalculation. This skill handles
short-term tactical adjustments only; replanning is a different skill's job.

---

## Edge Cases

**Insufficient data (< 3 weight readings in 14 days):**
Cannot diagnose reliably. Respond with: "I don't have enough weight data to
spot a clear trend — try weighing in 1–2 times per week and we'll have a
better picture soon."

**No meal logs:**
Skip calorie surplus analysis. Note the gap: "Without meal logs, I can't
check if calorie intake is a factor. Want to start logging meals?"

**User is in first 2 weeks of plan:**
Weight fluctuation is expected at the start. Reassure and suggest waiting
before making adjustments: "Your body is still adjusting to the new routine —
let's give it another week before changing anything."

**Weight gain is muscle gain (exercise increased significantly):**
If exercise volume increased significantly while weight went up, note the
possibility: "You've been exercising more — some of this could be muscle.
How do your clothes fit? That's often a better indicator than the scale."

**Active strategy already exists:**
If a strategy is already active and the user asks again, show progress on
the current strategy first. Only propose a new strategy if the current one
has ended or the user explicitly wants to change.
