# Guided Feedback — Data Schema

## `data/guided-feedback.json`

```json
{
  "total_check_ins": 0,
  "distinct_active_days": [],
  "queue": [
    {
      "id": "reminder-timing",
      "group": "reminder",
      "same_day_chain": ["reminder-frequency", "reminder-style"],
      "trigger": "total_check_ins >= 3",
      "status": "pending",
      "scheduled_at": null,
      "asked_at": null,
      "answered_at": null,
      "answer": null
    },
    {
      "id": "reminder-frequency",
      "group": "reminder",
      "trigger": "same_day_chain",
      "status": "pending",
      "scheduled_at": null,
      "asked_at": null,
      "answered_at": null,
      "answer": null
    },
    {
      "id": "reminder-style",
      "group": "reminder",
      "trigger": "same_day_chain",
      "status": "pending",
      "scheduled_at": null,
      "asked_at": null,
      "answered_at": null,
      "answer": null
    },
    {
      "id": "feedback-tone",
      "group": "feedback",
      "same_day_chain": ["food-preference", "advice-intensity"],
      "trigger": "reminder chain terminal",
      "status": "pending",
      "scheduled_at": null,
      "asked_at": null,
      "answered_at": null,
      "answer": null
    },
    {
      "id": "food-preference",
      "group": "feedback",
      "trigger": "same_day_chain",
      "status": "pending",
      "scheduled_at": null,
      "asked_at": null,
      "answered_at": null,
      "answer": null
    },
    {
      "id": "advice-intensity",
      "group": "feedback",
      "trigger": "same_day_chain",
      "status": "pending",
      "scheduled_at": null,
      "asked_at": null,
      "answered_at": null,
      "answer": null
    },
    {
      "id": "open-review",
      "group": "review",
      "trigger": "distinct_active_days >= 5",
      "status": "pending",
      "scheduled_at": null,
      "asked_at": null,
      "answered_at": null,
      "answer": null
    }
  ],
  "preference_signals": []
}
```

## Status Values

`pending` → `scheduled` → `asked` → `answered` | `skipped` | `covered`

## Preference Signal Entry

```json
{
  "date": "2026-04-08",
  "source": "diet-tracking-analysis",
  "covers": "feedback-tone",
  "content": "用户说回复太长了"
}
```

Valid `covers`: `reminder-timing`, `reminder-frequency`, `reminder-style`,
`feedback-tone`, `food-preference`, `advice-intensity`, `open-review`.

## Same-Day Chains

- Chain 1 (reminder): `reminder-timing` → `reminder-frequency` → `reminder-style`
- Chain 2 (feedback): `feedback-tone` → `food-preference` → `advice-intensity`

Only chain heads are scheduled via cron. Chain members are sent as immediate
follow-ups when user answers.
