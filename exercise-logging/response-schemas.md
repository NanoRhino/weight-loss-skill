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
