---
name: preference-learning
version: 1.0.0
description: >
  Analyzes accumulated meal logs, weight records, habit data, and conversation
  history to infer user preferences and behavioral patterns that were never
  explicitly stated. Runs periodically (weekly, after weekly-report) or on
  demand. Writes discoveries to health-preferences.md and memory/long-term.md.
  This skill is NOT triggered by user messages. It is called by the agent
  internally — typically as part of the weekly consolidation cycle.
metadata:
  openclaw:
    emoji: "mag"
    homepage: https://github.com/NanoRhino/weight-loss-skill
---

# Preference Learning

> ⚠️ **SILENT OPERATION:** Never narrate internal actions, skill transitions, or tool calls to the user. No "Let me check...", "Now I'll transition to...", "Reading your profile...". Just do it silently and respond with the result.

An analytical skill that mines the user's daily records to discover implicit
preferences and behavioral patterns. While other skills capture preferences
reactively (user says "I hate fish" → write it down), this skill proactively
finds patterns the user never articulated.

## Philosophy

**Observe, don't assume.** Every inference must be backed by repeated data
points — a single occurrence is noise, three occurrences are a signal.

**Respect existing data.** Never overwrite preferences that other skills
recorded from explicit user statements. Only append new discoveries.

**Actionable insights only.** Don't record trivia. Every discovered preference
should be useful for at least one downstream skill (meal-planner, habit-builder,
notification-composer, etc.).

---

## When to Run

| Trigger | Context |
|---------|---------|
| **Weekly consolidation** | After `weekly-report` generates on Sunday. This is the primary cadence. |
| **After onboarding + first week** | Once 7 days of meal data exist, run a first-pass analysis. |
| **On demand** | Agent decides more context is needed for personalization. |

This skill never sends messages to the user. All output is written to files.

---

## Analysis Dimensions

The script (`scripts/preference-analyzer.py`) aggregates raw data. The agent
interprets the aggregations and decides what qualifies as a real preference.

### 1. Food Preferences (→ `health-preferences.md > ## Dietary`)

**Data source:** `nutrition-calc.py meal-history` + daily meal files

**What to detect:**

| Pattern | Signal | Threshold | Example |
|---------|--------|-----------|---------|
| Frequently eaten foods | `meal-history` top_foods, frequency ≥ 3/week | ≥ 3 times in 7 days for a specific meal slot | "Eats eggs for breakfast 5/7 days" |
| Never-eaten food categories | Absence across 14+ days despite being suggested | Category absent for 2+ weeks | "Never eats seafood despite suggestions" |
| Cuisine clustering | Foods consistently from one cuisine | ≥ 60% of meals in a week from same cuisine | "Prefers Chinese home-cooking style" |
| Portion patterns | Consistently large or small portions for a meal | Avg calories for a meal slot deviates ≥ 20% from plan | "Lunch is consistently 40% above plan target" |
| Snacking patterns | Frequent snack logging between meals | Snacks logged ≥ 3 times/week | "Regular afternoon snacker" |

**Script command:**

```bash
python3 {baseDir}/scripts/preference-analyzer.py food-patterns \
  --data-dir {workspaceDir}/data/meals \
  --days 14 \
  --tz-offset <seconds>
```

Returns: `top_foods_by_meal`, `meal_calorie_averages`, `snack_frequency`,
`food_categories`, `never_categories` (categories suggested but never picked).

### 2. Timing & Rhythm (→ `health-preferences.md > ## Scheduling & Lifestyle`)

**Data source:** Daily meal files (timestamps), weight records

**What to detect:**

| Pattern | Signal | Threshold | Example |
|---------|--------|-----------|---------|
| Weekday vs weekend difference | Calorie/macro averages differ by day type | ≥ 15% difference weekday vs weekend avg | "Eats ~300 kcal more on weekends" |
| Late dinner pattern | Dinner logged consistently after plan time | ≥ 3 days/week dinner after 20:00 | "Usually eats dinner around 21:00" |
| Meal skipping | A meal slot consistently empty | Skipped ≥ 3 times/week | "Skips breakfast on weekdays" |
| Logging time pattern | When the user tends to log meals | Cluster analysis on log timestamps | "Logs meals immediately after eating" |
| Weigh-in pattern | When user weighs themselves | Time-of-day clustering | "Prefers morning weigh-ins" |

**Script command:**

```bash
python3 {baseDir}/scripts/preference-analyzer.py timing-patterns \
  --data-dir {workspaceDir}/data/meals \
  --weight-file {workspaceDir}/data/weight.json \
  --days 14 \
  --tz-offset <seconds>
```

Returns: `weekday_avg`, `weekend_avg`, `late_meals`, `skipped_meals`,
`weighin_times`.

### 3. Behavioral Trends (→ `health-preferences.md > ## Scheduling & Lifestyle` or `memory/long-term.md`)

**Data source:** Habit logs, weight trend, meal compliance

**What to detect:**

| Pattern | Signal | Threshold | Example |
|---------|--------|-----------|---------|
| Compliance cycle | Logging rate drops on specific days | Same weekday has < 50% logging rate over 3 weeks | "Logging drops every Friday" |
| Post-cheat recovery | How user behaves after an over-target day | Pattern in day-after-cheat meals | "Tends to under-eat the day after overeating" |
| Weight response to behavior | Correlation between weekly compliance and weight change | Directional consistency over 3+ weeks | "Weeks with ≥ 5 logged days show weight loss" |
| Motivation pattern | Engagement level over time (logging frequency trend) | Trend direction over 4 weeks | "Engagement increasing steadily" |

**Script command:**

```bash
python3 {baseDir}/scripts/preference-analyzer.py behavior-patterns \
  --data-dir {workspaceDir}/data/meals \
  --weight-file {workspaceDir}/data/weight.json \
  --days 28 \
  --tz-offset <seconds>
```

Returns: `daily_logging_rate`, `weekday_compliance`, `post_over_pattern`,
`engagement_trend`.

---

## Output Rules

### Writing to health-preferences.md

1. **Read the existing file first** — never overwrite
2. **Check for duplicates** — if a similar preference already exists (from
   explicit user statement or previous analysis), do NOT add a duplicate
3. **Tag inferred entries** — use the format:
   `- [YYYY-MM-DD] [inferred] Description (based on N days of data)`
4. **Place under the correct section:**
   - Food likes/dislikes/patterns → `## Dietary`
   - Timing/schedule patterns → `## Scheduling & Lifestyle`
   - Exercise patterns → `## Exercise`
   - Cooking patterns → `## Cooking & Kitchen`
5. **Max 3 new entries per run** — prioritize the most actionable discoveries

### Writing to memory/long-term.md

For stable behavioral patterns (confirmed over 3+ weeks), write to:
- `## Core Health Patterns` — e.g., "Consistently low protein on weekdays"
- `## Personality & Communication` — e.g., "Engagement peaks mid-week"

Only write to long-term if the pattern has been stable for 3+ weeks and
is not already captured there.

### What NOT to write

- Single-occurrence observations (noise, not signal)
- Preferences already explicitly stated by the user
- Judgmental observations ("eats too much junk food")
- Anything that contradicts an explicit user statement

---

## Confidence Levels

The agent assigns a confidence level to each inference:

| Level | Criteria | Action |
|-------|----------|--------|
| **High** | Pattern observed in ≥ 70% of relevant data points over 14+ days | Write to `health-preferences.md` |
| **Medium** | Pattern observed in 50-69% of data points or only 7-13 days | Write to `health-preferences.md` with `[inferred]` tag |
| **Low** | Pattern observed in < 50% or fewer than 7 days | Do NOT write — wait for more data |

---

## Integration with Other Skills

| Skill | How it uses preference-learning output |
|-------|---------------------------------------|
| **meal-planner** | Reads `health-preferences.md` to avoid disliked foods, favor preferred cuisines, respect timing patterns |
| **diet-tracking-analysis** | Uses food preferences for personalized suggestions; respects meal-skip patterns |
| **habit-builder** | Uses behavioral trends to identify highest-leverage habit targets |
| **notification-composer** | Uses timing patterns to optimize reminder timing |
| **weekly-report** | References behavioral trends in commentary |
| **memory-consolidation** | Preference-learning may write to `long-term.md`; memory-consolidation reads it |

---

## Workspace

### Reads

| Path | How | Purpose |
|------|-----|---------|
| `data/meals/YYYY-MM-DD.json` | `preference-analyzer.py` aggregation | Food patterns, timing, compliance |
| `data/weight.json` | `preference-analyzer.py` aggregation | Weigh-in patterns, weight-behavior correlation |
| `health-preferences.md` | direct read | Check existing preferences to avoid duplicates |
| `health-profile.md` | direct read | Meal schedule, diet mode, activity level for context |
| `PLAN.md` | direct read | Calorie/macro targets for compliance analysis |
| `memory/long-term.md` | direct read | Check existing long-term patterns |
| `habits.active` | direct read | Current habit context |
| `habits.daily_log.*` | direct read | Habit compliance patterns |
| `timezone.json` | direct read | Timezone offset for date calculations |

### Writes

| Path | When |
|------|------|
| `health-preferences.md` | After analysis — append new inferred preferences (max 3 per run) |
| `memory/long-term.md` | When a behavioral pattern is stable for 3+ weeks |
| `data/preference-analysis.json` | After each run — store full analysis results for trend tracking |

---

## Analysis Results Schema

Stored to `data/preference-analysis.json` after each run:

```json
{
  "last_run": "2026-03-20",
  "period": { "from": "2026-03-06", "to": "2026-03-20" },
  "days_analyzed": 14,
  "food_patterns": {
    "top_foods_by_meal": {
      "breakfast": [{ "name": "eggs", "count": 10, "pct": 71 }],
      "lunch": [],
      "dinner": []
    },
    "snack_frequency": 2.5,
    "weekday_vs_weekend_cal": { "weekday_avg": 1650, "weekend_avg": 1920 }
  },
  "timing_patterns": {
    "late_meals": { "dinner": { "avg_time": "20:45", "late_count": 4 } },
    "skipped_meals": { "breakfast": { "skip_rate": 0.43, "weekday_only": true } }
  },
  "behavior_patterns": {
    "logging_rate_by_weekday": { "Mon": 1.0, "Tue": 0.85, "Fri": 0.42 },
    "engagement_trend": "stable"
  },
  "new_preferences_written": [
    "[inferred] Skips breakfast on weekdays (based on 14 days of data)"
  ]
}
```

---

## Execution Flow

When invoked (typically after weekly-report):

1. **Read context** — `timezone.json`, `health-profile.md`, `PLAN.md`,
   `health-preferences.md`, `memory/long-term.md`
2. **Run food-patterns** — aggregate meal data
3. **Run timing-patterns** — aggregate timing/weight data
4. **Run behavior-patterns** — aggregate compliance/engagement data
5. **Interpret results** — the agent reviews script output and applies
   confidence thresholds to identify real preferences
6. **Deduplicate** — compare against existing `health-preferences.md` entries
7. **Write discoveries** — append to `health-preferences.md` (max 3),
   optionally update `memory/long-term.md`
8. **Save analysis** — write full results to `data/preference-analysis.json`

---

## Safety

- **Never infer eating disorders** from meal patterns — that's `emotional-support`'s domain
- **Never label foods as "bad"** in preference entries — stick to neutral descriptions
- **Never write weight judgments** — "gained weight on weekends" is data; "overeats on weekends" is judgment
- **Respect user autonomy** — if a user consistently eats something "unhealthy", that's their choice, not a problem to flag

---

## Performance

- Fully automated, no user interaction
- Analysis runs in < 10 seconds (script aggregation + agent interpretation)
- Max 3 new preference entries per run to avoid overwhelming the file
- Results stored for trend comparison across runs
