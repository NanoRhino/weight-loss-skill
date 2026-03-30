# Data Schemas & Sources

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
| `habits.active` | After cause-check pact is accepted — creates a tracked habit via `habit-builder` (week-1 phase, `source: "weight-gain-strategy"`). If `logging_gaps` + calorie issue detected, mark `strict: true` for tighter monitoring. |
| `health-preferences.md` | If the user reveals new preferences during the conversation (append only) |

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

## Integration with Other Skills

| Skill | Integration |
|-------|-------------|
| `habit-builder` | Cause-check pacts are written to `habits.active` as tracked habits. Habit-builder owns the lifecycle (check-in frequency, graduation, failure handling). `strict: true` habits get tighter monitoring. |
| `weekly-report` | Reads `check-strategy` output to report on active strategy progress. |
| `notification-composer` | Reads `check-strategy` output and `habits.active` to weave pact check-ins into meal conversations. For `strict: true` habits, gives detailed calorie feedback and proactive meal-log nudges. |
| `weight-tracking` | Source of weight data. This skill reads only — never writes to `data/weight.json`. |
| `diet-tracking-analysis` | Source of meal data. This skill reads only — never writes to `data/meals/`. |
| `exercise-tracking-planning` | Source of exercise data. This skill reads only — never writes to `data/exercise.json`. |
| `emotional-support` | Takes priority (P1) when user shows distress about weight gain. This skill defers. |
| `weight-loss-planner` | Owns PLAN.md. This skill reads the plan but never modifies it. Strategies are temporary overlays. |

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

## Edge Cases

**Insufficient data (< 3 weight readings in 14 days):**
Cannot diagnose reliably. Respond with: "I don't have enough weight data to
spot a clear trend — try weighing in 1–2 times per week and we'll have a
better picture soon."

**No meal logs:**
Skip calorie surplus analysis. Note the gap: "Without meal logs, I can't
check if calorie intake is a factor. Want to start logging meals?"

**User is in first 2 weeks of plan (adaptation period):**
Weight fluctuation is expected at the start. The `deviation-check` will return
`adaptation_period: true` — add "body is still adjusting" context to whatever
severity level applies. At `comfort`, this is the primary message. At
`cause-check`, early-exit at Step C with reassurance if no actionable cause.
If the user explicitly asks for changes, gently recommend waiting: "Your body
is still adjusting — let's give it another week and the picture will be
clearer."

**Weight gain is muscle gain (exercise increased significantly):**
If exercise volume increased significantly while weight went up, note the
possibility: "You've been exercising more — some of this could be muscle.
How do your clothes fit? That's often a better indicator than the scale."

**Active strategy already exists:**
If a strategy is already active and the user asks again, show progress on
the current strategy first. Only propose a new strategy if the current one
has ended or the user explicitly wants to change.
