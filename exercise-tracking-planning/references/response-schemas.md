# Response Schemas

## Exercise Log Response (`is_exercise_log: true`)

Return this whenever the user logs a workout or exercise session. Supports single or multiple activities in one message.

```json
{
  "message": "Brief confirmation in user's language",
  "exercises": [
    {
      "category": "cardio|strength|flexibility|hiit|sports|daily_activity",
      "activity": "specific activity name",
      "duration_min": 30,
      "intensity": "low|moderate|high",
      "calories": 350,
      "distance": null,
      "distance_unit": "km|mi|m|null",
      "avg_hr": null,
      "max_hr": null,
      "pace": null,
      "feeling": null,
      "source": "user|device|user+device|estimated"
    }
  ],
  "total_calories": 350,
  "feedback": "1-2 sentence goal-aligned comment",
  "risk_alert": null,
  "is_exercise_log": true,
  "date": "2026-02-28",
  "lang": "en"
}
```

### Field Notes

- `exercises`: **array** of exercise objects. Single activity = array with one item. Multiple activities (e.g., "ran 30min then stretched 20min") = array with multiple items.
- `category`: one of the six defined categories
- `activity`: specific name in user's language (e.g., "running", "swimming", "jogging")
- `duration_min`: integer, in minutes
- `intensity`: `low` / `moderate` / `high`. If user provides RPE or HR, map to these three levels
- `calories`: integer per exercise. If from device, use device value. If estimated via MET, prefix display text with `≈` (but store as integer in JSON)
- `total_calories`: sum of all exercises' calories in this log
- `distance`: float or null. Only for applicable activities (cardio, some sports)
- `distance_unit`: follows user's `unit_preference` or contextual language
- `avg_hr` / `max_hr`: integer or null. Only when device data is available
- `pace`: string or null (e.g., "5:30/km", "8:45/mi"). Calculated from distance + duration when both available
- `feeling`: string or null. User's subjective description (e.g., "good", "tired", "easy", "exhausted")
- `source`: indicates data origin per exercise
  - `"user"` — all data from user description
  - `"device"` — all data from smart device
  - `"user+device"` — mix of user and device data
  - `"estimated"` — key values (especially calories) estimated by Claude
- `feedback`: 1-2 sentences, goal-aligned, in user's language. For multi-activity, give one combined comment. Never null.
- `risk_alert`: string or null. Only set when a risk condition is detected (see risk-alerts.md)
- `date`: ISO date string. See Date Parsing Rules below.
- `lang`: language code matching user's current message

### Date Parsing Rules

Default to today's date. If user indicates a different date, parse as follows:

| User Expression | Parsing Rule | Example (today = 2026-02-28, Saturday) |
|----------------|--------------|----------------------------------------|
| "today" | Current date | 2026-02-28 |
| "yesterday" | Current date − 1 | 2026-02-27 |
| "day before yesterday" | Current date − 2 | 2026-02-26 |
| "Wednesday" / "on Wednesday" | Most recent past Wednesday (or today if today is Wednesday) | 2026-02-25 |
| "last Friday" | Previous week's Friday | 2026-02-20 |
| "2/25" / "Feb 25" | Specific date, assume current year unless year is specified | 2026-02-25 |
| "3 days ago" | Current date − N | 2026-02-25 |

If the parsed date is in the future, ask user to confirm — likely a mistake.

### Examples

**Single activity: "Ran 5km in 30 minutes" (weight: 70kg)**

```json
{
  "message": "Logged!",
  "exercises": [
    {
      "category": "cardio",
      "activity": "running",
      "duration_min": 30,
      "intensity": "moderate",
      "calories": 368,
      "distance": 5.0,
      "distance_unit": "km",
      "avg_hr": null,
      "max_hr": null,
      "pace": "6:00/km",
      "feeling": null,
      "source": "estimated"
    }
  ],
  "total_calories": 368,
  "feedback": "Nice 6:00/km pace — ≈368 kcal. Moderate-to-high intensity cardio, right in the efficient fat-burning zone.",
  "risk_alert": null,
  "is_exercise_log": true,
  "date": "2026-02-28",
  "lang": "en"
}
```

**Multiple activities: "Ran for 30 minutes today, then did 20 minutes of stretching" (weight: 70kg)**

```json
{
  "message": "Logged!",
  "exercises": [
    {
      "category": "cardio",
      "activity": "running",
      "duration_min": 30,
      "intensity": "moderate",
      "calories": 280,
      "distance": null,
      "distance_unit": null,
      "avg_hr": null,
      "max_hr": null,
      "pace": null,
      "feeling": null,
      "source": "estimated"
    },
    {
      "category": "flexibility",
      "activity": "stretching",
      "duration_min": 20,
      "intensity": "low",
      "calories": 54,
      "distance": null,
      "distance_unit": null,
      "avg_hr": null,
      "max_hr": null,
      "pace": null,
      "feeling": null,
      "source": "estimated"
    }
  ],
  "total_calories": 334,
  "feedback": "Running + stretching is a great combo — ≈334 kcal. Post-run stretching helps with recovery and reduces muscle soreness.",
  "risk_alert": null,
  "is_exercise_log": true,
  "date": "2026-02-28",
  "lang": "en"
}
```

**Single activity (English): "Did an hour of weights at the gym, felt great"**

```json
{
  "message": "Logged!",
  "exercises": [
    {
      "category": "strength",
      "activity": "weight training",
      "duration_min": 60,
      "intensity": "moderate",
      "calories": 350,
      "distance": null,
      "distance_unit": null,
      "avg_hr": null,
      "max_hr": null,
      "pace": null,
      "feeling": "great",
      "source": "estimated"
    }
  ],
  "total_calories": 350,
  "feedback": "Solid strength session — ≈350 kcal. Keep up the consistency!",
  "risk_alert": null,
  "is_exercise_log": true,
  "date": "2026-02-28",
  "lang": "en"
}
```

**Backdate: "Played badminton for an hour yesterday" (today is 2026-02-28)**

```json
{
  "message": "Logged!",
  "exercises": [
    {
      "category": "sports",
      "activity": "badminton",
      "duration_min": 60,
      "intensity": "moderate",
      "calories": 315,
      "distance": null,
      "distance_unit": null,
      "avg_hr": null,
      "max_hr": null,
      "pace": null,
      "feeling": null,
      "source": "estimated"
    }
  ],
  "total_calories": 315,
  "feedback": "An hour of badminton burns ≈315 kcal — great full-body workout, especially for agility and reflexes.",
  "risk_alert": null,
  "is_exercise_log": true,
  "date": "2026-02-27",
  "lang": "en"
}
```

---

## Training Plan Response (`is_training_plan: true`)

Return this when a new training plan is accepted by the user. Store the full object to `training_plan.active`. If an active plan already exists, archive it to `training_plan.history` first.

```json
{
  "plan_id": "plan_20260306",
  "created_date": "2026-03-06",
  "status": "active",
  "goal": "lose_fat",
  "experience_level": "beginner",
  "days_per_week": 3,
  "minutes_per_session": 55,
  "split_type": "full_body",
  "equipment": "commercial_gym",
  "schedule": [
    {
      "day": "mon",
      "type": "training",
      "label": "全身训练 A",
      "estimated_duration_min": 55,
      "exercises": [
        {
          "order": 1,
          "phase": "warmup",
          "name": "椭圆机慢速",
          "duration_min": 3,
          "sets": null,
          "reps": null
        },
        {
          "order": 2,
          "phase": "main",
          "name": "高脚杯深蹲",
          "category": "strength",
          "movement_pattern": "squat",
          "sets": 3,
          "reps": "10-12",
          "intensity": "moderate",
          "rest_sec": 90
        },
        {
          "order": 3,
          "phase": "cooldown",
          "name": "股四头肌拉伸",
          "duration_sec": 20,
          "per_side": true
        }
      ]
    },
    {
      "day": "tue",
      "type": "rest",
      "label": "休息 · 散步30分钟",
      "active_recovery": "walk 30min",
      "exercises": []
    }
  ],
  "progression": {
    "current_phase": 1,
    "phases": [
      { "phase": 1, "weeks": "1-2", "focus": "learn movements, moderate intensity" },
      { "phase": 2, "weeks": "3-4", "focus": "progressive overload" },
      { "phase": 3, "weeks": "5", "focus": "deload week, volume -40%" }
    ]
  },
  "constraints": {
    "injuries": [],
    "avoided_exercises": [],
    "preferences_applied": ["prefers_dumbbells"]
  },
  "is_training_plan": true,
  "lang": "zh"
}
```

### Field Notes

- `plan_id`: `plan_` + ISO date of creation. Unique identifier for archival.
- `status`: `"active"` when current; changes to `"archived"` when replaced or completed.
- `goal`: user's primary training goal — matches `fitness_goal` values.
- `experience_level`: `beginner` / `intermediate` / `advanced`.
- `days_per_week`: integer, how many training days per week.
- `minutes_per_session`: integer, typical session duration (excluding warm-up/cooldown if user specified "net training time").
- `split_type`: the training split chosen — `full_body` / `upper_lower` / `push_pull_legs` / `body_part` / `cardio_only` / `mixed`.
- `equipment`: `commercial_gym` / `home_gym` / `bodyweight` / `outdoor` / `mixed`.
- `schedule`: array of 7 objects (Mon–Sun). Each day has:
  - `day`: three-letter lowercase day code (`mon`–`sun`).
  - `type`: `"training"` or `"rest"`.
  - `label`: display name in user's language (e.g., "全身训练 A", "休息日").
  - `estimated_duration_min`: integer or null (null for rest days).
  - `exercises`: array of exercise objects for training days; empty array for rest days.
    - `order`: integer, sequence within the session.
    - `phase`: `"warmup"` / `"main"` / `"cooldown"`.
    - `name`: exercise name in user's language.
    - `category`: (main phase only) `strength` / `cardio` / `flexibility` / `hiit` / `sports`.
    - `movement_pattern`: (strength only) `squat` / `hinge` / `push_horizontal` / `push_vertical` / `pull_horizontal` / `pull_vertical` / `carry` / `core` / `isolation`.
    - `sets`, `reps`, `intensity`, `rest_sec`: (main phase only) training parameters.
    - `duration_min` or `duration_sec`: (warmup/cooldown) time-based exercises.
    - `per_side`: boolean, true if exercise is done per side.
  - `active_recovery`: (rest days only) string description or null.
- `progression`: periodization plan.
  - `current_phase`: integer, which phase the user is currently in.
  - `phases`: array of phase objects with week ranges and focus descriptions.
- `constraints`: records what limitations and preferences were applied during plan design.
- `lang`: language code matching user's language.

### Plan Lifecycle

1. User requests a training plan → skill designs and presents it in Markdown.
2. User accepts (explicitly or by not objecting) → write to `training_plan.active`.
3. User requests adjustments → update `training_plan.active` in place.
4. User requests a completely new plan → archive current plan to `training_plan.history`, write new plan to `training_plan.active`.
5. Plan reaches end of progression cycle → skill can propose a new mesocycle; if accepted, archive and replace.

### How Other Skills Use `training_plan.active`

- `daily-notification`: reads `schedule[today].label` to mention today's workout in reminders (e.g., "今天是全身训练 A 的日子").
- `weekly-report`: reads plan to compare planned vs. actual sessions logged in `logs.exercise.*`.
- `habit-builder`: reads `days_per_week` and schedule to recommend exercise-adjacent habits (e.g., "gym bag prep the night before").

---

## Non-Exercise Response (`is_exercise_log: false`)

Return this for follow-up questions, clarifications, weekly summaries, or general chat.

```json
{
  "message": "Response in user's language",
  "exercise": null,
  "feedback": null,
  "risk_alert": null,
  "is_exercise_log": false,
  "date": null,
  "lang": "en"
}
```

---

## Weekly Summary Response

Weekly summaries use the non-exercise response format with a structured `message` field. See `weekly-summary-template.md` for the message content template.

```json
{
  "message": "[structured weekly summary — see template]",
  "exercise": null,
  "feedback": null,
  "risk_alert": null,
  "is_exercise_log": false,
  "date": null,
  "lang": "en"
}
```
