# Data Schemas — Daily Notification

Detailed JSON schemas for all data records produced by this Skill.

---

## Weight Record

Logged whenever the user reports a weight number in response to a
weight reminder.

```json
{
  "type": "weight",
  "user_id": "string",
  "weight": {
    "value": 162.5,
    "unit": "lbs"
  },
  "recorded_at": "2025-02-26T07:18:00Z",
  "reminder_sent_at": "2025-02-26T07:00:00Z",
  "source": "daily-notification"
}
```

| Field | Description |
|-------|-------------|
| `weight.value` | User-reported number |
| `weight.unit` | `"lbs"` or `"kg"` based on user preference |
| `recorded_at` | Timestamp when user actually replied |
| `reminder_sent_at` | Timestamp when the reminder was sent |
| `source` | Always `"daily-notification"` (distinguishes from other logging sources) |

---

## Meal Check-in Record

Logged for every meal reminder sent, regardless of whether the user replied.
This lets other parts of the system see the full picture — not just what was logged,
but what was skipped.

```json
{
  "type": "meal_checkin",
  "user_id": "string",
  "meal_type": "lunch",
  "status": "logged",
  "food_description": "chicken salad and crackers",
  "estimated_calories": 450,
  "reminder_sent_at": "2025-02-26T12:15:00Z",
  "replied_at": "2025-02-26T12:22:00Z",
  "source": "daily-notification"
}
```

| Field | Description |
|-------|-------------|
| `meal_type` | `"breakfast"` / `"lunch"` / `"dinner"` |
| `status` | `"logged"` (user reported food) / `"skipped"` (user said they're skipping) / `"no_reply"` (user didn't respond) |
| `food_description` | What the user said they ate. `null` if skipped or no reply. |
| `estimated_calories` | From nutrition RAG if available. `null` if not available or not applicable. |
| `reminder_sent_at` | When the reminder was sent |
| `replied_at` | When the user responded. `null` if no reply. |
| `source` | Always `"daily-notification"` |

---

## Daily Summary

Auto-generated at 9:00 PM (or end of user's last meal window). Compiles
the day's records into a summary written to `logs.daily_summary.{date}`.

```json
{
  "type": "daily_notification_summary",
  "user_id": "string",
  "date": "2025-02-26",
  "weight": {
    "logged": true,
    "value": 162.5,
    "unit": "lbs",
    "recorded_at": "2025-02-26T07:18:00Z"
  },
  "meals": {
    "breakfast": {
      "reminder_sent": true,
      "status": "logged",
      "replied_at": "2025-02-26T07:52:00Z",
      "food_description": "oatmeal and coffee",
      "estimated_calories": 350
    },
    "lunch": {
      "reminder_sent": true,
      "status": "no_reply",
      "replied_at": null,
      "food_description": null,
      "estimated_calories": null
    },
    "dinner": {
      "reminder_sent": true,
      "status": "logged",
      "replied_at": "2025-02-26T18:50:00Z",
      "food_description": "grilled chicken and rice",
      "estimated_calories": 650
    }
  },
  "engagement": {
    "reminders_sent": 4,
    "reminders_replied": 3,
    "reply_rate": 0.75,
    "avg_reply_delay_min": 15
  }
}
```

### Field Reference

**weight object:**
- `logged`: boolean — whether weight was recorded today
- `value`: number or null
- `unit`: `"lbs"` or `"kg"`
- `recorded_at`: ISO timestamp or null

**meals.{meal_type} object:**
- `reminder_sent`: boolean — whether a reminder was sent for this meal
- `status`: `"logged"` / `"skipped"` / `"no_reply"` / `"not_sent"` (reminder was suppressed)
- `replied_at`: ISO timestamp or null
- `food_description`: string or null
- `estimated_calories`: number or null

**engagement object:**
- `reminders_sent`: total reminders sent today (meals + weight)
- `reminders_replied`: how many got a reply
- `reply_rate`: 0-1
- `avg_reply_delay_min`: average minutes between reminder sent and user reply

---

## Workspace Paths

All data is written to the user's workspace and readable by any part of the system.

| Data | Workspace Path |
|------|---------------|
| Weight records | `logs.weight.{date}` |
| Meal check-in records | `logs.meals.{date}.{meal_type}` |
| Daily summaries | `logs.daily_summary.{date}` |
| Engagement stage | `engagement.notification_stage` |
| Adaptive config | `engagement.reminder_config` |
