---
name: weekly-report
version: 1.0.0
description: "Generate a personalized weekly progress report for the user's weight-loss journey. Use this skill every Monday (or when the user asks for a weekly summary). Compiles 7 days of meal logs, weight records, and macro data into a visual Markdown report with logging streaks, calorie analysis, weight trends, macronutrient breakdown, achievements, and actionable suggestions. Trigger phrases: 'weekly report', 'week summary', 'how did I do this week', '本周报告', '周报', '这周怎么样'."
metadata:
  openclaw:
    emoji: "bar_chart"
    homepage: https://github.com/NanoRhino/weight-loss-skill
---

# Weekly Report

A personalized end-of-week progress report that turns 7 days of scattered data
into a clear, motivating snapshot. The report is data-driven but human —
celebrate consistency, normalize fluctuations, and give exactly one or two
things to focus on next week.

## Principles

1. **Show, don't lecture.** Let the data speak. Keep commentary short.
2. **Celebrate consistency over perfection.** 5 out of 7 days logged is great — don't focus on the 2 missed.
3. **One week is noise, trends are signal.** Never draw dramatic conclusions from a single week.
4. **Personalize everything.** Use the user's name, units, food history, and goals — never a generic template dump.
5. **Actionable > informational.** Every suggestion must be something the user can do next week.

---

## Trigger Strategy

### Schedule

Auto-generate every **Monday at 9:00 AM** (user's local time), covering the
previous Monday–Sunday. Read `timezone.json` to determine the user's local
time and correctly calculate the Mon–Sun date range. If the user's quiet hours
extend past 9 AM, delay to end of quiet hours.

### Manual Trigger

User can request a report at any time:
- `"weekly report"` / `"week summary"` / `"how was my week"` → generate for the most recent completed Mon–Sun
- `"report for last week"` / `"上周报告"` → same
- `"report for Feb 10–16"` → generate for that specific range

### Pre-send Checks

1. User in Stage 4 (silent)? → skip auto-send, but still generate if manually requested
2. Less than 2 days of data in the period? → send a short message instead: `"Not enough data for a full report this week — let's make next week count! 💪"`
3. All clear → generate and send

---

## Data Sources

### Reads from `USER.md`

| Field | Purpose |
|-------|---------|
| `Basic Info > Name` | Greeting / header personalization |
| `Health Flags` | Skip weight section if ED-related flags |

### Reads from `health-profile.md`

| Field | Purpose |
|-------|---------|
| `Body > Current Weight` | Baseline reference (initial weight) |
| `Goals > Target Weight` | Progress percentage calculation |
| `Meal Schedule > Meals per Day` | Expected logs per day (for logging rate calc) |
| `Meal Schedule` | Which meals to expect |
| `Diet Config > Food Restrictions` | Context for suggestions |
| `Activity & Lifestyle > Exercise Habits` | Context for suggestions |

### Reads from `PLAN.md`

| Field | Purpose |
|-------|---------|
| `Daily Calorie Range` | On-target / below / over classification |
| `Protein Range` | Macro analysis |
| `Fat Range` | Macro analysis |
| `Carb Range` | Macro analysis |
| `Weight Loss Rate` | Expected weekly loss for progress assessment |
| `Diet Mode` | Context for suggestions |

### Reads from logs (workspace)

| Path | Purpose |
|------|---------|
| `logs.meals.{date}.{meal_type}` | Logging status, food descriptions, estimated calories per meal |
| `logs.weight.{date}` | Weight readings for the week |
| `logs.daily_summary.{date}` | Pre-compiled daily totals and engagement stats |
| `habits.active` | Current active habits for habit progress section |
| `habits.daily_log.{date}` | Daily habit completion/miss/no_response records |
| `habits.graduated` | Recently graduated habits for achievements section |

---

## Report Structure

The report has 7 sections. Generate them in order. Each section adapts to the
user's actual data — skip or simplify sections with no data.

### Section 1: Header

```
📊 Weekly Report
{Mon date} – {Sun date}
```

Use the language from locale.json. Chinese example: `📊 本周报告  2月10日 – 2月16日`

If user's name is available, add: `Hi {Name}! Here's your week.` /
`{Name}，这是你这周的总结！`

---

### Section 2: Logging Overview

Show each day of the week with a status indicator for whether the user logged
meals that day.

**Data logic:**
- For each day (Mon–Sun), check `logs.meals.{date}`:
  - If at least 1 meal has `status: "logged"` → ✅
  - If all meals are `"skipped"` or `"no_reply"` or no log exists → ❌
- Count total days with ✅ → `{X}/7 days logged`

**Display format (Markdown):**

```
### 📅 Logging Overview

| Mon | Tue | Wed | Thu | Fri | Sat | Sun |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| ✅  | ✅  | ✅  | ❌  | ✅  | ✅  | ❌  |

**5/7 days logged** — Nice consistency!
```

**Commentary rules:**
- 7/7 → `"Perfect week! 🎉"` / `"满勤！🎉"`
- 5-6/7 → `"Nice consistency!"` / `"记录很稳！"`
- 3-4/7 → `"Solid start — let's aim for one more day next week."` / `"不错的开始，下周争取多记一天。"`
- 1-2/7 → `"Every logged day counts. Small steps!"` / `"每记一天都有价值，慢慢来！"`

---

### Section 3: Calorie Analysis

Show daily calorie intake vs the user's target range. Classify each day.

**Data logic:**
- For each day, sum `estimated_calories` across all logged meals from `logs.meals.{date}` or use `logs.daily_summary.{date}` totals
- Compare against `Daily Calorie Range` from `PLAN.md`:
  - Below range min → `📉 Below`
  - Within range → `✅ On Target`
  - Above range max → `📈 Over`
- Days with no data → `—` (skip from calculations)

**Display format:**

```
### 🔥 Calorie Analysis

Daily target: {min} – {max} kcal

| Day | Intake | Status |
|-----|--------|--------|
| Mon | 1,620 kcal | ✅ On Target |
| Tue | 1,480 kcal | 📉 Below |
| Wed | 1,750 kcal | ✅ On Target |
| Thu | — | — |
| Fri | 1,830 kcal | ✅ On Target |
| Sat | 2,150 kcal | 📈 Over |
| Sun | — | — |

**Average: 1,766 kcal/day** (target midpoint: {midpoint} kcal)
On Target: 3 days · Below: 1 day · Over: 1 day
```

**Commentary rules:**
- Average within range → `"Right on track this week."` / `"这周热量控制得很好。"`
- Average below range → `"A bit under — make sure you're eating enough to sustain energy."` / `"稍微偏低，注意吃够保持精力。"`
- Average above range → `"Slightly over, but a few small adjustments can close the gap."` / `"略微超标，小调整就能回来。"`
- Only 1-2 days of data → Show what's available but note: `"Limited data this week — the more you log, the more useful this gets."`

---

### Section 4: Weight Progress

Show weight readings recorded during the week and the net change.

**Data logic:**
- Collect all entries from `logs.weight.{date}` within the period
- If 2+ readings: calculate change = last reading − first reading
- If 1 reading: show it, compare to previous week's last reading if available
- If 0 readings: skip this section entirely, add a gentle note

**Display format:**

```
### ⚖️ Weight Progress

| Date | Weight |
|------|--------|
| Mon 2/10 | 75.2 kg |
| Thu 2/13 | 74.8 kg |

**This week: −0.4 kg ↓**
Total progress: 80.0 kg → 74.8 kg (−5.2 kg toward goal of 65.0 kg)
```

Use the user's preferred unit system (kg or lbs) — read from existing weight
log entries' `unit` field.

**Commentary rules:**
- Loss within expected rate (from `PLAN.md` weekly rate) → `"Right on pace."` / `"进度刚好。"`
- Loss faster than expected → `"Great progress — just make sure you're not undereating."` / `"进度不错，注意别吃太少。"`
- No change or slight gain → `"Weight fluctuates — one week doesn't define the trend. 💛"` / `"体重会波动，一周说明不了什么。💛"`
- No readings → `"No weigh-ins this week — want to add one next week?"` / `"这周没有称重记录，下周要不要试试？"`

**Never:** compare to target weight in a pressuring way, criticize a gain, or
suggest the user weigh more often than 2x/week.

---

### Section 5: Macronutrient Analysis

Compare the user's average daily macro intake against their target ranges.

**Data logic:**
- Calculate average daily protein, fat, carb from logged meals across the week
  (use `meal_totals` from food logs or `daily_summary` data)
- Compare each macro's average against the range from `PLAN.md`
- Classify: `Below Range` / `In Range` / `Above Range`

**Display format:**

```
### 🥗 Macronutrient Analysis

| Macro   | Avg Intake | Target Range | Status |
|---------|-----------|--------------|--------|
| Protein | 82 g/day  | 84–112 g/day | 📉 Slightly Below |
| Fat     | 58 g/day  | 50–70 g/day  | ✅ In Range |
| Carb    | 225 g/day | 181–254 g/day | ✅ In Range |
```

**Commentary rules:**
- All in range → `"Balanced macros this week — keep it up!"` / `"三大营养素都在范围内，继续保持！"`
- Protein below → always flag: `"Protein is a bit low — try adding an egg, yogurt, or chicken breast to one meal."` / `"蛋白质偏低，试试每天多加一个鸡蛋或一份鸡胸肉。"`
- Fat over → `"Fat ran a little high — check cooking oils and snacks."` / `"脂肪偏高，留意下烹饪用油和零食。"`
- Insufficient data (< 3 days of macro data) → show what's available with caveat: `"Based on limited data — log more meals for a clearer picture."`

---

### Section 6: Habit Progress

Show the status of active habits, if any exist. Read `habits.active` and
`habits.daily_log.{date}` for the week.

**Data logic:**
- For each active habit, count completions, misses, and no_responses during the week
- Calculate completion rate for the week
- Check for graduation signals (see `habit-builder` SKILL.md)
- If no active habits exist, skip this section entirely

**Display format:**

```
### 🌱 Habit Progress

**Walk after dinner** (Week 2)
This week: ✅✅✅❌✅ — 4/5 mentions completed

Looking solid — becoming part of your routine.
```

**Commentary rules:**
- High completion (≥ 80%) → celebrate casually: `"This one's becoming automatic."` / `"快变成习惯了。"`
- Medium (50-79%) → encourage: `"Getting there — consistency beats perfection."` / `"在进步，坚持比完美更重要。"`
- Low (< 50%) → gentle: `"Tough week for this one. Want to adjust it or try something different?"` / `"这周有点难，要不要调整一下？"`
- If graduation criteria met → flag it: `"This might be ready to graduate — we'll check in."` / `"这个习惯可能可以毕业了，下次聊聊。"`

**Behavioral pattern detection:**
If `habits.daily_log` data across the week reveals a pattern worth addressing
(e.g., user always overeats at night, skips meals on weekdays), note it in
`habits.lifestyle_gaps` for the `habit-builder` skill to act on.

---

### Section 7: Key Achievements & Suggestions

Two sub-sections: what went well, and what to focus on next week. Both are
AI-generated based on the week's actual data.

#### Achievements (max 3)

Scan the week's data for genuine wins. Pick the most meaningful ones.

**Pattern library** (use as inspiration, personalize to actual data):
- Logging streak: `"Logged meals 5 days straight — that's real commitment."` / `"连续5天记录饮食，这就是坚持。"`
- Calorie consistency: `"3 days right in your target range."` / `"3天热量都在目标范围内。"`
- Protein improvement: `"Protein intake improved vs last week."` / `"蛋白质摄入比上周有进步。"`
- Weight trend: `"Down 0.4 kg this week — steady progress."` / `"这周减了0.4 kg，稳步前进。"`
- Variety: `"Tried 3 new foods this week."` / `"这周尝试了3种新食物。"`
- Healthy choices: `"Chose grilled over fried twice."` / `"两次选了烤的而不是炸的。"`

If nothing stands out, find something — even `"You showed up and logged. That's the hardest part."` / `"你坚持记录了，这就是最难的一步。"`

**Never fabricate achievements.** Every achievement must be backed by actual data.

#### Suggestions (max 2)

Specific, actionable improvements for next week. Based on the week's gaps.

**Rules:**
- Each suggestion must reference actual data (e.g., "Protein averaged 82g vs target 84–112g")
- Must include a concrete action (e.g., "Add a Greek yogurt to breakfast")
- Respect food restrictions from `health-profile.md`
- Never suggest weighing more than 2x/week
- Never suggest calorie counting if user is on IF mode
- Tone: collaborative, not prescriptive — `"One thing to try next week:"` not `"You need to:"`

**Display format:**

```
### 🏆 Key Achievements

- Logged meals 5 out of 7 days — building a strong habit.
- 3 days within calorie target — that's real progress.
- Down 0.4 kg this week — steady and sustainable.

### 💡 Suggestions for Next Week

- **Boost protein**: Averaged 82g vs 84–112g target. Try adding an egg to breakfast or a handful of nuts as a snack.
- **Weekend logging**: Missed both weekend days — even a quick note helps keep awareness up.
```

---

## Formatting Rules

- **Units:** Use the user's preferred system consistently. Read from existing weight logs or `PLAN.md`. Never show dual units.
- **Numbers:** Use locale-appropriate formatting. English: `1,620 kcal`. Chinese: `1620 kcal`.
- **Tone:** Warm, data-driven, encouraging. Like a supportive coach reviewing game tape with an athlete.
- **Length:** The full report should be scannable in under 60 seconds. Keep commentary to 1-2 sentences per section max.

---

## Edge Cases

**First week (< 7 days of data):**
Generate a partial report with whatever data exists. Prefix with:
`"This is your first report — it'll get more useful as we collect more data!"` /
`"这是你的第一份周报，数据越多越有参考价值！"`

**Week with zero data:**
Don't generate a full report. Send a short message:
`"No data to report this week — ready to start fresh? 💪"` /
`"这周没有数据，准备重新开始？💪"`

**User has no PLAN.md (no calorie/macro targets):**
Skip Sections 3 and 5 (calorie and macro analysis). Show logging overview and
weight progress only. Add note: `"Set up a weight loss plan to unlock calorie and macro tracking in your weekly report."` /
`"创建减重计划后，周报会加入热量和营养素分析。"`

**Health flags (ED-related):**
If `USER.md > Health Flags` contains `avoid_weight_focus` or `history_of_ed`:
- Skip Section 4 (Weight Progress) entirely
- In calorie section, focus on consistency of eating, not numbers
- Achievements: focus on variety and balance, not restriction

---

## Workspace

### Reads

| Path | Purpose |
|------|---------|
| `USER.md` | User identity, name, health flags |
| `health-profile.md` | Health data, goals, meal schedule, food restrictions |
| `PLAN.md` | Calorie targets, macro ranges, weekly loss rate, diet mode |
| `logs.meals.{date}.{meal_type}` | Meal logging status, food descriptions, calories, macros |
| `logs.weight.{date}` | Weight readings |
| `logs.daily_summary.{date}` | Pre-compiled daily totals |

### Writes

| Path | When |
|------|------|
| `logs.weekly_report.{start_date}` | After generating the report — store the full report JSON (see `references/data-schemas.md`) |
| `habits.lifestyle_gaps` | When behavioral patterns are detected during weekly analysis (consumed by `habit-builder`) |

---

## Output

### Delivery

Send the report as a single in-app chat message in Markdown format. The
frontend renders Markdown natively — no special UI components needed.

### Report JSON (stored to workspace)

After displaying the report to the user, write a structured JSON summary to
`logs.weekly_report.{start_date}` for cross-session reference and trend
analysis. Schema in `references/data-schemas.md`.

---

## Skill Routing

**See `SKILL-ROUTING.md` for the full conflict resolution system.** This skill
is **Priority Tier P4 (Reporting)**. Key scenarios:

- **Weekly report + exercise weekly summary** (Pattern 3): This skill is the primary owner of weekly summaries. Exercise weekly data (sessions, duration, calories burned, WHO comparison) is incorporated as a section within this report. `exercise-tracking-planning` does NOT produce a separate weekly summary when this skill is generating.
- **Monday auto-report**: Include exercise data from the week. No separate exercise summary needed.
- **User requests "weekly summary"**: Route here, not to exercise-tracking's weekly summary.

---

## Performance

- Report generation: single message, no back-and-forth
- Total report length: aim for 40–60 lines of Markdown
- Commentary: 1–2 sentences per section, max
