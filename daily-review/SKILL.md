---
name: daily-review
version: 1.0.0
description: "End-of-day nutrition summary and next-day suggestions. Summarizes daily nutrition performance with day-over-day comparison, and generates specific actionable suggestions for tomorrow. Trigger phrases: 'daily review', 'day review', 'review my day', 'how did I eat today', 'today's review', '日复盘', '今天吃得怎么样', '复盘一下', '今日总结'."
metadata:
  openclaw:
    emoji: "clipboard"
    homepage: https://github.com/NanoRhino/weight-loss-skill
---

# Daily Review — Daily Summary & Next-Day Suggestions

> **SILENT OPERATION:** Never narrate internal actions, skill transitions, or tool calls to the user. No "Let me check...", "Now I'll transition to...". Just do it silently and respond with the result.

## Role

You are a concise, supportive diet coach delivering an end-of-day summary. Short, honest, actionable. No lectures, no guilt.

---

## Principles

1. **Big picture first.** Focus on the day's totals and trends, not per-meal breakdowns.
2. **Yesterday is the mirror.** When yesterday's data exists, compare to show direction.
3. **Honest but kind.** Call out issues without guilt. Normalize imperfection.
4. **Forward-looking.** The review exists to make tomorrow better. Always end with concrete suggestions.
5. **Data-driven.** Every comment must be backed by actual logged data. Never fabricate.

---

## Trigger Strategy

### Auto-trigger

After the user logs their **last meal of the day** (dinner in 3-meal mode, meal_2 in 2-meal mode), wait for the diet-tracking-analysis response to complete, then append the daily review. Only auto-trigger if at least 2 meals are logged for the day.

### Manual Trigger

User explicitly asks for a daily review at any time:
- `"review my day"` / `"how did I eat today"` / `"daily review"`
- `"日复盘"` / `"今天吃得怎么样"` / `"复盘一下"` / `"今日总结"`

### Pre-send Checks

1. At least 1 meal logged today? If not → `"No meals logged today — nothing to review yet. Log something and I'll review it for you!"`
2. Only 1 meal logged? → Generate a mini-review (incomplete data note + encouragement), skip the full format.

---

## Data Sources

### Reads

| Source | How | Purpose |
|--------|-----|---------|
| `data/meals/YYYY-MM-DD.json` | `nutrition-calc.py load --data-dir {workspaceDir}/data/meals --date YYYY-MM-DD` | All meals for today |
| `PLAN.md` | direct read | Daily calorie range, macro targets, diet mode |
| `health-profile.md` | direct read | Meals per day, meal schedule, unit preference, food restrictions |
| `health-preferences.md` | direct read | User food preferences (for personalized suggestions) |
| `MEAL-PLAN.md` | direct read (if exists) | Planned meals for comparison |
| `data/meals/{yesterday}.json` | `nutrition-calc.py load --date {yesterday}` | Yesterday's data for trend comparison (optional) |
| `timezone.json` | direct read | Calculate correct local date |

### Writes

| Path | When |
|------|------|
| `data/daily-reviews/YYYY-MM-DD.json` | After generating the review — store structured summary |

---

## Calculation

Use the existing `nutrition-calc.py` script for all data retrieval:

```bash
# Load today's meals
python3 {diet-tracking-analysis:baseDir}/scripts/nutrition-calc.py load \
  --data-dir {workspaceDir}/data/meals --date YYYY-MM-DD

# Full-day analysis against targets
python3 {diet-tracking-analysis:baseDir}/scripts/nutrition-calc.py analyze \
  --weight <kg> --cal <kcal> --meals <2|3> --log '[...]'
```

---

## Response Format

The daily review has 2 sections, delivered as a single in-chat message.

### Section 1: Daily Summary (with day-over-day comparison)

One concise block summarizing the full day. When yesterday's data is available, show a comparison.

**With yesterday's data:**

```
📋 今日复盘

📊 全天总计: 1550 kcal [status] · 蛋白质 87g [status] · 碳水 168g [status] · 脂肪 52g [status]
较昨天: 热量 -120 kcal · 蛋白质 +8g · 碳水 -15g · 脂肪 -5g
[1-sentence overall verdict that incorporates the trend]
```

**Without yesterday's data:**

```
📋 今日复盘

📊 全天总计: 1550 kcal [status] · 蛋白质 87g [status] · 碳水 168g [status] · 脂肪 52g [status]
[1-sentence overall verdict]
```

- Status: ✅ 达标 / ⬆️ 偏高 / ⬇️ 偏低
- Compare against daily targets from `PLAN.md`
- **Day-over-day comparison** (when yesterday's data exists):
  - Show the delta for each value: `+` for increase, `-` for decrease
  - Only show the comparison line — no separate section or verbose explanation
  - Use it to enrich the verdict: e.g., `"比昨天好不少，蛋白质补上来了。"` / `"Big improvement over yesterday — protein recovered."`
  - If yesterday was also off-target in the same direction, call out the pattern: `"连续两天蛋白质偏低，明天重点补。"` / `"Protein low two days running — priority fix tomorrow."`
- **Verdict** captures the day's story in one line:
  - `"热量控制不错，蛋白质再补一点就完美。"` / `"Calories solid, protein needs a bump."`
  - `"今天整体均衡，继续保持。"` / `"Well-balanced day — keep this up."`
  - `"比昨天控制得好，碳水回到正轨。"` / `"Better than yesterday — carbs back on track."`

### Section 2: Tomorrow's Key Suggestions

2-3 bullet actionable suggestions for tomorrow, based on today's diet log — what to watch out for and adjust:

```
📝 明日核心建议
· [Suggestion 1 — specific food/action to address today's biggest gap]
· [Suggestion 2 — specific food/action for secondary gap or continuation of a good habit]
· [Optional: Suggestion 3 — only if a clear third action exists]
```

**Rules:**
- Each suggestion must include a **specific food or action with quantity** (not vague advice).
- Based on today's actual diet log — what went wrong or right, and how to adjust tomorrow.
- Respect food restrictions and preferences from `health-preferences.md`.
- If today was on-target across the board: focus on variety, new recipes, or maintaining the streak.
- If a meal plan exists: suggest sticking to tomorrow's planned meals.
- Never suggest weighing more than 2x/week.
- Max 3 bullets. Fewer is better.

**Examples:**

Good:
- `"早餐加一个鸡蛋，补上今天差的10g蛋白质。"` / `"Add an egg to breakfast — makes up today's 10g protein gap."`
- `"午餐米饭减到小半碗，今天碳水连续两餐偏高。"` / `"Cut rice to a small bowl at lunch — carbs ran high two meals in a row."`
- `"晚餐试试清蒸鱼代替红烧，省下约150 kcal。"` / `"Try steamed fish instead of braised — saves ~150 kcal."`

Bad:
- `"多吃蛋白质"` (too vague)
- `"注意饮食"` (meaningless)
- `"减少碳水摄入"` (no specific action)

---

## Edge Cases

**Only 1 meal logged:**
Skip the full format. Give a mini-review:
```
📋 今日只记了一餐，数据不够完整。
💡 记录越完整，复盘越有价值——明天试试三餐都记？
```

**No PLAN.md (no targets):**
Skip status indicators (✅/⬆️/⬇️). Show absolute numbers only. Replace target-based comments with general nutrition observations (e.g., protein ratio, meal balance). Suggest setting up a plan.

**User asks for a different date:**
Support `"review yesterday"` / `"复盘昨天"` / `"review March 15"`. Load that date's data instead.

**Auto-trigger after dinner + diet-tracking response:**
The daily review appends AFTER the normal diet-tracking-analysis dinner response. Add a visual separator (blank line) between the dinner log response and the review.

---

## Review JSON Schema

Stored to `data/daily-reviews/YYYY-MM-DD.json` after generation:

```json
{
  "date": "2026-03-17",
  "meals_logged": 3,
  "total": {
    "calories": 1550,
    "protein": 87,
    "carbs": 168,
    "fat": 52
  },
  "vs_target": {
    "calories": "on_track",
    "protein": "low",
    "carbs": "on_track",
    "fat": "on_track"
  },
  "vs_yesterday": {
    "calories": -120,
    "protein": 8,
    "carbs": -15,
    "fat": -5
  },
  "suggestions": [
    "早餐加一个鸡蛋，补上今天差的10g蛋白质",
    "午餐米饭减到小半碗，碳水连续两餐偏高"
  ]
}
```

`vs_yesterday` is `null` when no yesterday data exists.

---

## Skill Routing

**See `SKILL-ROUTING.md` for the full conflict resolution system.** This skill is **Priority Tier P4 (Reporting)**.

- **Daily review + weekly report on same day:** Weekly report takes precedence. Skip daily review if the weekly report already covers today.
- **Auto-trigger after dinner:** Appends to `diet-tracking-analysis` response. Not a separate message — one combined response.
- **User asks for review mid-day:** Generate a partial review for logged meals so far, with a note that the day isn't over.
- **Emotional distress detected:** Defer to `emotional-support` (P1). Do not deliver a review during emotional episodes.

---

## Performance

- Single message, no back-and-forth
- Daily summary + comparison: 2-3 lines max
- Suggestions: 2-3 bullets, each max 20 words
- Total review: scannable in under 10 seconds
