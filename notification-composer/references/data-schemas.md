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
| Last interaction | Derived from `data/meals/*.json` | `check-stage.py` scans for most recent logged meal date |
| Stage changed at | `data/engagement.json > stage_changed_at` | written by `check-stage.py` |
| Last recall date | `data/engagement.json > last_recall_date` | written by `notification-composer` after each daily recall (Stage 2) |
| Final recall sent | `data/engagement.json > recall_2_sent` | written by `notification-composer` after final recall (Stage 3) |
| Adaptive config | `data/engagement.json > reminder_config` | direct read/write |
| First-meal nudge count | `data/engagement.json > activation.first_meal_nudges_sent` | written by `notification-composer` via `activation-mark-sent.py` after each first-meal nudge send |
| Activation nudge count | `data/engagement.json > activation.nudges_sent` | written by `notification-composer` via `activation-mark-sent.py` after each activation (never-replied) nudge send |

---

## Activation Block

Lives in `data/engagement.json`. Owner: `notification-manager` (consistent with
the rest of engagement.json). Holds the two activation-nudge counters — both are
**non-stage business fields** (note: post-lifecycle-migration, `notification_stage`
/ `stage_changed_at` are NO LONGER stored here; stage lives in the lifecycle DB,
but `activation.*`, `recall_topics`, etc. remain in engagement.json). Both are
incremented **deterministically** by
`notification-manager/scripts/activation-mark-sent.py --counter <name>` (called
by `notification-composer` after each successful send) — NOT by LLM-driven
read-modify-write, because the "max 2 then stop" anti-nag guarantee depends on
the count being exact.

```json
{
  "activation": {
    "first_meal_nudges_sent": 0,
    "nudges_sent": 0
  },
  "recall_topics": []
}
```

| Field | Description |
|-------|-------------|
| `activation.first_meal_nudges_sent` | First-meal nudges sent (0-2; onboarded-but-never-logged cohort). Capped at 2 — after 2, the pre-send-check cap gate permanently suppresses the nudge (lifecycle-independent terminal guarantee). |
| `activation.nudges_sent` | Activation nudges sent (0-2; greeted-but-never-replied cohort; cron created by openclaw-infra). Capped at 2 — same cap-gate suppression. |

The `activation` block and each counter are optional/backward-compatible —
absent reads as 0. (The cap gate is what stops the nudges; transitioning a
never-engaged user to lifecycle Silent so normal recall content also stops is a
lifecycle-side concern — see notification-manager SKILL.md § Activation nudge.)
| Streak data | `data/streak.json > current_streak, longest_streak, streak_start_date, last_logged_date` | written by `streak-calc.py info` on every run |
| Milestones celebrated | `data/streak.json > milestones_celebrated` | written by `streak-calc.py celebrate` after milestone message |
