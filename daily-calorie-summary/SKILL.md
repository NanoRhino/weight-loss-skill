---
name: daily-calorie-summary
version: 1.0.0
description: "Nightly summary of the user's calorie deficit — food intake, exercise burn, and how it compares to the plan. Runs automatically every evening via cron or on-demand. Trigger phrases: 'daily summary', 'today's deficit', 'how's my deficit', 'calorie summary', '今天的缺口', '今日总结', '热量总结', '今天怎么样'."
metadata:
  openclaw:
    emoji: "crescent_moon"
    homepage: https://github.com/NanoRhino/weight-loss-skill
---

# Daily Calorie Summary

> **SILENT OPERATION:** Never narrate internal actions, skill transitions, or tool calls to the user. Just do it silently and respond with the result.

A concise nightly check-in that answers one question: **am I on track today?**

Compares actual calorie deficit (food intake vs TDEE + exercise) against the
planned deficit from `PLAN.md`. Short, scannable, actionable.

## Principles

1. **One screen, ten seconds.** The summary must be scannable in a single glance.
2. **Show the gap, not the lecture.** Numbers speak — keep commentary to one sentence.
3. **Exercise is a bonus, not a requirement.** Show exercise burn when present; never guilt the user for not exercising.
4. **One bad day is noise.** Never dramatize a single day's overshoot.

---

## Trigger Strategy

### Schedule

Auto-generate every day at **21:30** (user's local time). To get today's date:

```bash
python3 {diet-tracking-analysis:baseDir}/scripts/nutrition-calc.py local-date \
  --tz-offset {tz_offset}
```

Use the `today` field from the output. **Never calculate dates yourself.**

### Manual Trigger

User can request at any time:
- `"daily summary"` / `"today's deficit"` / `"how's my deficit"` / `"今天的缺口"` / `"今日总结"` / `"热量总结"` → generate for today
- `"summary for yesterday"` / `"昨天的总结"` → generate for yesterday (pass `--date`)

### Pre-send Checks (cron only)

1. User in Stage 4+ (silent)? → output `NO_REPLY`, stop.
2. No meal data for today? → output `NO_REPLY`, stop. (User didn't log anything — a reminder would feel like nagging.)
3. No `PLAN.md`? → output `NO_REPLY`, stop. (No target to compare against.)
4. All clear → generate and send.

---

## Data Sources

### Reads from `USER.md`

| Field | Purpose |
|-------|---------|
| `TZ Offset` | Timezone for local-date and data queries |
| `Basic Info > Name` | Optional personalization |
| `Health Flags` | Skip if ED-related flags present |

### Reads from `health-profile.md`

| Field | Purpose |
|-------|---------|
| `Body > Unit Preference` | Display unit consistency |
| `Meals per Day` | Context for missing-meal awareness |

### Reads from `PLAN.md`

| Field | Purpose |
|-------|---------|
| `Daily Calorie Range` | Target intake (use midpoint as target) |
| `Daily Calorie Deficit` | Planned deficit for comparison |
| `TDEE` | Total daily energy expenditure |
| `BMR` | Safety floor check |
| `Weight Loss Rate` | Context for deficit meaning |

### Reads from data (workspace)

| Data | How | Purpose |
|------|-----|---------|
| Today's meals | `nutrition-calc.py load --data-dir {workspaceDir}/data/meals --date {today} --tz-offset {tz_offset}` | Sum calorie intake |
| Today's exercise | `exercise-calc.py load --data-dir {workspaceDir}/data --from {today} --to {today}` | Sum net exercise calories |

---

## Calculation

```
food_intake    = sum of calories from all logged meals today
exercise_burn  = sum of net_calories_kcal from exercise logs today (0 if none)
total_burn     = TDEE + exercise_burn
actual_deficit = total_burn - food_intake
planned_deficit = from PLAN.md (e.g. 500 kcal)
gap            = actual_deficit - planned_deficit
```

### Classification

| Condition | Status | Symbol |
|-----------|--------|--------|
| actual_deficit within planned +-100 kcal | On track | `~` |
| actual_deficit > planned + 100 kcal | Larger deficit than planned | `+` |
| actual_deficit < planned - 100 kcal | Smaller deficit than planned | `-` |
| food_intake < BMR | Below safety floor | `!!` |

---

## Output

### Delivery

Plain text in chat. No Markdown rendering. Scannable in under 10 seconds.

### Format

```
{date_display}

🍽 摄入 {food_intake} kcal
🏃 运动 {exercise_burn} kcal
🔥 总消耗 {total_burn} kcal（TDEE {tdee} + 运动 {exercise_burn}）

📉 实际缺口 {actual_deficit} kcal {status_symbol} 计划 {planned_deficit} kcal

{one_sentence_comment}
```

### Field Rules

- **`date_display`**: weekday + date, e.g. `周二 · 4/14`
- **`food_intake`**: sum of all logged meals. Missing meals are handled by the Follow-Up Questions section — do not annotate inline.
- **`exercise_burn`**: sum of net exercise calories. If no exercise logged, use the No-Exercise Display format instead.
- **`total_burn`**: TDEE + exercise net. Parenthetical breakdown always shown.
- **`actual_deficit`**: total_burn - food_intake
- **`status_symbol`**:
  - On track: `≈` — e.g. `📉 实际缺口 520 kcal ≈ 计划 500 kcal`
  - Larger deficit: `▲` — e.g. `📉 实际缺口 720 kcal ▲ 计划 500 kcal`
  - Smaller deficit: `▽` — e.g. `📉 实际缺口 280 kcal ▽ 计划 500 kcal`
  - Surplus (negative deficit): `⚠️` — e.g. `📈 热量盈余 120 kcal ⚠️ 计划缺口 500 kcal`
- **`one_sentence_comment`**: one short sentence, data-driven. See Commentary Rules.

### Commentary Rules

| Status | Tone | Example |
|--------|------|---------|
| On track | Affirm | `今天节奏刚好。` |
| Larger deficit (< 200 over) | Casual positive | `比计划多消耗了一些，不错。` |
| Larger deficit (>= 200 over) | Gentle caution | `缺口偏大，明天可以多吃一点。` |
| Below BMR | Safety note | `今天摄入低于基础代谢，注意别太少。` |
| Smaller deficit (mild) | Neutral | `比计划少了一点，正常波动。` |
| Smaller deficit (large) | Forward-looking | `今天超了一些，明天回来就好。` |
| Surplus | No guilt | `热量略有盈余，一天不影响趋势。` |
| No exercise | Never mention | Do NOT comment on lack of exercise — the follow-up question handles it. |
| Has exercise | Brief acknowledgment | Incorporate naturally, e.g. `跑步贡献了 250 kcal 额外消耗。` |
| Missing meals | Hint at incompleteness | E.g. `缺口比计划大不少，可能还有没记的。` — the follow-up question handles specifics. |

### No-Exercise Display

When no exercise is logged for the day, simplify the format:

```
{date_display}

🍽 摄入 {food_intake} kcal
🔥 TDEE {tdee} kcal

📉 实际缺口 {actual_deficit} kcal {status_symbol} 计划 {planned_deficit} kcal

{one_sentence_comment}
```

Omit the `🏃 运动` line and the `总消耗` breakdown entirely — show only TDEE as total burn.

---

## Follow-Up Questions

After the summary, append up to two follow-up questions to help the user
complete today's data. Questions appear at the **end** of the same message,
separated by a blank line from the comment. Keep them casual — like a friend
checking in, not a form.

### Missing Meals

Compare logged meals against the expected schedule from `health-profile.md >
Meal Schedule` (or default: breakfast / lunch / dinner for 3-meal; meal_1 /
meal_2 for 2-meal). If any meal has no record for today:

```
{meal_name} 好像没记，吃了什么？
```

Multiple missing meals → combine into one question:
```
午餐和晚餐还没记，吃了什么？
```

If ALL meals are logged → skip this question.

### Unlogged Exercise

If no exercise is logged for today, ask:

```
今天有运动吗？
```

If exercise IS logged → skip this question.

### Combined Example

```
周二 · 4/14

🍽 摄入 1,050 kcal
🔥 TDEE 2,200 kcal

📉 实际缺口 1,150 kcal ▲ 计划 500 kcal

缺口比计划大不少，可能还有没记的。

晚餐还没记，吃了什么？
今天有运动吗？
```

### Rules

1. **Max 2 follow-up questions per summary** — one for meals, one for exercise.
2. **Single-ask only** — if the user ignores the questions, never repeat them. Respect the global Single-Ask Rule from `SKILL-ROUTING.md`.
3. **Cron delivery:** follow-up questions are part of the output text — the user can reply naturally in the next message, which will be routed to `diet-tracking-analysis` or `exercise-tracking-planning` as appropriate.
4. **Manual trigger:** same behavior — append questions if data is incomplete.

### Handling Replies

This skill does NOT handle replies. User responses are routed by the normal
skill-routing system:
- Food reply → `diet-tracking-analysis` logs the meal
- Exercise reply → `exercise-tracking-planning` logs the workout
- "没有" / "没运动" / "跳过了" → acknowledged, no further action

After the user completes the missing data, **do NOT auto-regenerate the
summary.** The user can request it again manually if they want an updated view.

---

## Edge Cases

**No meal data at all (manual trigger):**
If the user explicitly asks for today's summary but has no meal data:
`今天还没有记录，先去拍个照吧～`

**No `PLAN.md` (manual trigger):**
`还没有制定计划，先用 weight-loss-planner 创建一个吧。`

**Health flags (ED-related):**
If `USER.md > Health Flags` contains `avoid_weight_focus` or `history_of_ed`:
- Skip this skill entirely (cron → `NO_REPLY`; manual → gentle redirect to general meal feedback)

**First day of tracking:**
No special treatment — show whatever data exists. Don't add "this is your first summary" preamble.

**Negative deficit (surplus):**
Use `📈` instead of `📉`. Never use alarming language. One day of surplus is meaningless.

---

## Workspace

### Reads

| Path | Via |
|------|-----|
| `PLAN.md` | Direct read |
| `USER.md` | Direct read (already in context) |
| `health-profile.md` | Direct read |
| `data/meals/{today}.json` | `nutrition-calc.py load` |
| `data/exercise.json` | `exercise-calc.py load` |

### Writes

None. This skill is read-only — it summarizes, it does not modify data.

---

## Skill Routing

**Priority Tier P4 (Reporting).** See `SKILL-ROUTING.md`.

- **Daily summary + weekly report on same day (Sunday):** weekly-report is the comprehensive summary; daily-calorie-summary cron is suppressed on Sundays (weekly report covers the day).
- **Daily summary + meal logging:** If the user is actively logging a meal, defer the cron. The summary fires at the next gap or is skipped if it's past the window.
- **Manual trigger during conversation:** Generate immediately — no conflict with other skills.

---

## Performance

- Output: single message with optional follow-up questions
- Length: 4–6 lines + 1 comment + up to 2 follow-up questions
- No HTML report, no file upload — chat only
- Replies handled by other skills via normal routing — no multi-turn in this skill
