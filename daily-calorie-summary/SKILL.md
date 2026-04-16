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
📋 今日总结 {verdict}

📉 热量缺口 {actual_deficit} kcal {status_symbol}
{one_sentence_comment}

热量明细：
🍽 摄入 {food_intake} kcal
🔥 总消耗 {total_burn} kcal（TDEE {tdee} + 运动 {exercise_burn}）

{follow_up_questions}
```

### Field Rules

- **Title**: `📋 今日总结 {verdict}` — no date. Verdict is a one-word tag: `达标` / `超标` / `不足` / `⚠️低于基代`
  - On track (within ±100 of plan): `达标`
  - Larger deficit than planned: `不足`（ate too little）
  - Smaller deficit / surplus: `超标`
  - Below BMR: `⚠️低于基代`
- **`date_display`**: weekday + date, e.g. `周四 · 4/16`
- **Deficit line**: `📉 热量缺口 {actual_deficit} kcal {status_symbol}` — no "计划 X kcal" suffix. The comment below explains vs plan.
- **`one_sentence_comment`**: mentions planned deficit for context. E.g. `今天制造热量缺口高于计划500kcal，相当于大约四个鸡翅的量。`
- **Details section**: labeled `热量明细：` (not a divider line). Lists intake and total burn. Exercise is always part of the total burn parenthetical — no separate exercise line.
- **`food_intake`**: sum of all logged meals.
- **`total_burn`**: TDEE + exercise. Always show parenthetical `（TDEE {tdee} + 运动 {exercise_burn}）`, even when exercise is 0.
- **`actual_deficit`**: total_burn - food_intake
- **`status_symbol`**: only `▲` (larger deficit) or `▽` (smaller deficit) or `≈` (on track) or `⚠️` (surplus). Appended after kcal, no other text.
- **Follow-up questions**: appear after a blank line from the details section. No separator needed.

### Commentary Rules

The one-sentence comment should **only state the analogy** — no evaluation, no advice, no encouragement.

| Status | Example |
|--------|---------|
| On track | `跟计划差不多。` |
| Larger deficit (< 200 over) | `比计划多了一点。` |
| Larger deficit (>= 200 over) | `比计划多消耗了大约四个鸡翅的量。` |
| Below BMR | `摄入低于基础代谢，差了大约三个鸡翅的量。` |
| Smaller deficit (mild) | `比计划少了一点。` |
| Smaller deficit (large) | `多了大约一杯奶茶的量。` |
| Surplus | `多了大约两小把花生米的量。` |
| Has exercise | `跑步贡献了 250 kcal。` |
| Missing meals | `可能还有没记的。` |

**禁止：** 不要加"不错"、"明天回来就好"、"注意别太少"、"不影响趋势"等评价/建议。只说相当于多少食物或运动。

### Calorie Analogies

**When to use:** Only when all meals are logged AND the gap between actual and
planned deficit is **>= 200 kcal**. Small deviations don't need analogies —
just state the number.

**How to pick:** Choose ONE analogy per summary. Only use a single food item or
a single exercise item — never组合多种食材（e.g. "一块鸡胸肉加一杯牛奶" ✗）。
Rotate across days, don't总是用同一个比喻。

**Food reference** (approximate, pick one):

| Item | Calories |
|------|----------|
| 一碗白米饭 (150g cooked) | ~195 kcal |
| 一个鸡翅 | ~100 kcal |
| 一小把花生米 (30g) | ~170 kcal |
| 一根香蕉 | ~105 kcal |
| 一块巧克力 (30g) | ~160 kcal |
| 一杯奶茶 | ~300 kcal |
| 一个肉包子 | ~200 kcal |

**Exercise reference** (approximate, pick one):

| Item | Calories |
|------|----------|
| 走 1,000 步 | ~30 kcal |
| 慢跑 10 分钟 | ~100 kcal |
| 骑车 15 分钟 | ~100 kcal |

**Fat burn reference:**

| | |
|---|---|
| 消耗 1g 脂肪 | ~7.7 kcal |

**Direction matters:**

- **Deficit too large** (ate too little / burned too much) → two analogy types可选：
  - Food: `相当于少吃了三个鸡翅的量。`
  - Fat burn: `约等于燃烧了 55g 脂肪。`

- **Deficit too small / surplus** (ate too much) → use exercise OR food analogy:
  - Exercise: `相当于散步 40 分钟的量。`
  - Food: `大约多了一杯奶茶的量。`

**Tone rules:**
- **只说类比，不加评价。** 不说"不错"、"明天回来就好"、"注意"、"不影响趋势"。
- **Single item only.** 用数量调节（"三个鸡翅"、"两小把花生米"），不混搭食材。
- Never say "you need to walk X steps to burn it off" — say "相当于走 X 步的量".

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
📋 今日总结 不足

📉 热量缺口 1,150 kcal ▲
缺口比计划500kcal大不少，可能还有没记的。

热量明细：
🍽 摄入 1,050 kcal
🔥 总消耗 2,200 kcal（TDEE 2,200 + 运动 0）

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
