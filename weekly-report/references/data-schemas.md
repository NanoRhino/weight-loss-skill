# Data Schemas — Weekly Report

Detailed JSON schemas for data produced and consumed by the Weekly Report skill.

---

## Weekly Report Record

Written to `logs.weekly_report.{start_date}` after each report is generated.
Stores structured data for cross-week trend analysis and historical reference.

```json
{
  "type": "weekly_report",
  "user_id": "string",
  "period": {
    "start": "2025-02-10",
    "end": "2025-02-16"
  },
  "logging": {
    "days_logged": 5,
    "days_total": 7,
    "daily_status": {
      "2025-02-10": true,
      "2025-02-11": true,
      "2025-02-12": true,
      "2025-02-13": false,
      "2025-02-14": true,
      "2025-02-15": true,
      "2025-02-16": false
    }
  },
  "calories": {
    "daily_intake": {
      "2025-02-10": 1620,
      "2025-02-11": 1480,
      "2025-02-12": 1750,
      "2025-02-13": null,
      "2025-02-14": 1830,
      "2025-02-15": 2150,
      "2025-02-16": null
    },
    "average": 1766,
    "target_range": {
      "min": 1600,
      "max": 1800
    },
    "days_on_target": 3,
    "days_below": 1,
    "days_over": 1
  },
  "weight": {
    "readings": [
      {
        "date": "2025-02-10",
        "value": 75.2,
        "unit": "kg"
      },
      {
        "date": "2025-02-13",
        "value": 74.8,
        "unit": "kg"
      }
    ],
    "change": -0.4,
    "unit": "kg"
  },
  "macros": {
    "protein": {
      "average": 82,
      "target_range": {
        "min": 84,
        "max": 112
      },
      "unit": "g",
      "status": "below"
    },
    "fat": {
      "average": 58,
      "target_range": {
        "min": 50,
        "max": 70
      },
      "unit": "g",
      "status": "in_range"
    },
    "carb": {
      "average": 225,
      "target_range": {
        "min": 181,
        "max": 254
      },
      "unit": "g",
      "status": "in_range"
    }
  },
  "achievements": [
    "Logged meals 5 out of 7 days",
    "3 days within calorie target",
    "Down 0.4 kg this week"
  ],
  "suggestions": [
    "Boost protein: averaged 82g vs 84–112g target",
    "Try logging on weekends for a fuller picture"
  ],
  "next_week_focus": "午饭加豆腐或鸡蛋，把蛋白质从83g补到95g以上",
  "generated_at": "2025-02-17T09:00:00Z"
}
```

### Field Reference

**period:**
- `start`: Monday of the report week (ISO date)
- `end`: Sunday of the report week (ISO date)

**logging:**
- `days_logged`: count of days with at least 1 meal logged
- `days_total`: always 7 (full week)
- `daily_status`: map of date → boolean (true = at least 1 meal logged)

**calories:**
- `daily_intake`: map of date → calories (number or null if no data)
- `average`: mean of non-null daily intake values
- `target_range`: from `PLAN.md` daily calorie range `{ min, max }`
- `days_on_target`: count of days within target range
- `days_below`: count of days below target min
- `days_over`: count of days above target max

**weight:**
- `readings`: array of weight entries recorded during the week, sorted by date
- `change`: last reading minus first reading (negative = loss). `null` if fewer than 2 readings
- `unit`: `"kg"` or `"lbs"` — matches user preference

**macros:**
- Each macro (`protein`, `fat`, `carb`) includes:
  - `average`: daily average in grams
  - `target_range`: `{ min, max }` from `PLAN.md`
  - `unit`: always `"g"`
  - `status`: `"below"` / `"in_range"` / `"above"`

**achievements:** array of 1–3 strings describing the week's wins

**suggestions:** array of 1–2 strings with actionable next-week improvements

**next_week_focus:** plain text string — the single action item from the 🎯 section,
stored for continuity checking when the following week's report is generated.
`null` if no focus was set.

**generated_at:** ISO timestamp of when the report was generated

---

## Data Sources (Read)

The weekly report aggregates data from these existing schemas. It does not
define new input schemas — all inputs are produced by other skills.

| Source | Schema Owner | Path | How to read |
|--------|-------------|------|-------------|
| Meal logs | diet-tracking-analysis | `data/meals/YYYY-MM-DD.json` | `nutrition-calc.py load --date YYYY-MM-DD` |
| Weight logs | weight-tracking | `data/weight.json` | `weight-tracker.py load --from <start> --to <end> --display-unit <unit>` |
| User identity | user-onboarding-profile | `USER.md` | direct read |
| Health profile | user-onboarding-profile | `health-profile.md` | direct read |
| Health preferences | user-onboarding-profile + all skills | `health-preferences.md` | direct read |
| Weight loss plan | weight-loss-planner | `PLAN.md` | direct read |
| Previous weekly reports | weekly-report | `logs.weekly_report.{start_date}` | direct read |

### Cross-Reference: Meal Log Fields Used

From `data/meals/YYYY-MM-DD.json` (array of meal objects):

| Field | Used For |
|-------|----------|
| `name` | Meal type identification |
| `cal` | Daily calorie totals |
| `p`, `c`, `f` | Macro analysis |
| `foods[].name` | Achievement pattern detection (variety, streaks) |

### Cross-Reference: Weight Log Fields Used

From `data/weight.json` (object keyed by ISO-8601 datetime):

| Field | Used For |
|-------|----------|
| `value` | Weight progress, trend calculation |
| `unit` | Original unit (converted to display unit by script) |

### Cross-Reference: PLAN.md Fields Used

| Field | Used For |
|-------|----------|
| `Daily Calorie Range` | Calorie on-target/below/over classification |
| `Protein Range` | Macro analysis |
| `Fat Range` | Macro analysis |
| `Carb Range` | Macro analysis |
| `Weight Loss Rate` | Expected vs actual weight change |
