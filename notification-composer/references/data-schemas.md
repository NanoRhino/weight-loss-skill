# Data Schemas — Notification Composer

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
  "fasting": true,
  "recorded_at": "2025-02-26T07:18:00Z",
  "reminder_sent_at": "2025-02-26T07:00:00Z",
  "source": "notification-composer"
}
```

| Field | Description |
|-------|-------------|
| `weight.value` | User-reported number |
| `weight.unit` | `"lbs"` or `"kg"` based on user preference |
| `fasting` | `true` if user weighed before eating, `false` if user had already eaten. Used for trend accuracy — fasting readings are more comparable. |
| `recorded_at` | Timestamp when user actually replied |
| `reminder_sent_at` | Timestamp when the reminder was sent |
| `source` | Always `"notification-composer"` (distinguishes from other logging sources) |

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
  "source": "notification-composer"
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
| `source` | Always `"notification-composer"` |

---

## Workspace Paths

All data is written to the user's workspace and readable by any part of the system.

| Data | Workspace Path | How |
|------|---------------|-----|
| Weight records | `data/weight.json` | `weight-tracker.py save/load` (from `weight-tracking` skill) |
| Meal records | `data/meals/YYYY-MM-DD.json` | `nutrition-calc.py save/load` (from `diet-tracking-analysis` skill) |
| Engagement stage | `data/engagement.json > notification_stage` | direct read/write |
| Last interaction | `data/engagement.json > last_interaction` | direct read (written by platform) |
| Stage changed at | `data/engagement.json > stage_changed_at` | written by `check-stage.py` |
| Recall 1 sent | `data/engagement.json > recall_1_sent` | written by `notification-composer` after sending first recall |
| Recall 2 sent | `data/engagement.json > recall_2_sent` | written by `notification-composer` after sending second recall |
| Adaptive config | `data/engagement.json > reminder_config` | direct read/write |
