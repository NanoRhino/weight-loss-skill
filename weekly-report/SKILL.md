---
name: weekly-report
version: 1.0.0
description: "Generate a personalized weekly progress report for the user's weight-loss journey. Use this skill every Monday (or when the user asks for a weekly summary). Compiles 7 days of meal logs, weight records, and macro data into an in-chat summary plus a styled HTML report with logging streaks, calorie analysis, weight trends, macronutrient breakdown, achievements, and actionable suggestions. Trigger phrases: 'weekly report', 'week summary', 'how did I do this week', '本周报告', '周报', '这周怎么样'."
metadata:
  openclaw:
    emoji: "bar_chart"
    homepage: https://github.com/NanoRhino/weight-loss-skill
---

# Weekly Report

> ⚠️ **SILENT OPERATION:** Never narrate internal actions, skill transitions, or tool calls to the user. No "Let me check...", "Now I'll transition to...", "Reading your profile...". Just do it silently and respond with the result.


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

Auto-generate every **Sunday at 9:00 PM** (user's local time), covering the
current Monday–Sunday. To get the correct date range, run:

```bash
python3 {diet-tracking-analysis:baseDir}/scripts/nutrition-calc.py local-date --tz-offset {tz_offset}
```

This returns `today`, `current_week` (monday–sunday), and `previous_week` (monday–sunday). Use `current_week` as the report range. **Never calculate dates yourself** — always use the script output.

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
| `Body > Unit Preference` | Display unit for weight (kg or lb) |
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

### Reads from data (workspace)

| Path | How | Purpose |
|------|-----|---------|
| `data/meals/YYYY-MM-DD.json` | `nutrition-calc.py load --date YYYY-MM-DD --tz-offset {tz_offset}` for each day in range | Logging status, food descriptions, estimated calories per meal |
| `data/weight.json` | `weight-tracker.py load --from YYYY-MM-DD --to YYYY-MM-DD --display-unit <unit>` | Weight readings for the week |
| `data/exercise.json` | `exercise-calc.py load --data-dir {workspaceDir}/data --from YYYY-MM-DD --to YYYY-MM-DD` | Exercise sessions, duration, calories burned for the week |
| `habits.active` | direct read | Current active habits for habit progress section |
| `habits.daily_log.{date}` | direct read | Daily habit completion/miss/no_response records |
| `habits.graduated` | direct read | Recently graduated habits for achievements section |

**Note:** Weight data is read via the `weight-tracking` skill's `weight-tracker.py` script at `{weight-tracking:baseDir}/scripts/weight-tracker.py`. Read `health-profile.md > Body > Unit Preference` for the display unit. Meal data is read via `nutrition-calc.py load` from the `diet-tracking-analysis` skill. Exercise data is read via `exercise-calc.py load` from the `exercise-tracking-planning` skill at `{exercise-tracking-planning:baseDir}/scripts/exercise-calc.py`.

---

## Report Structure

The report has 6 sections. Generate them in order. Each section adapts to the
user's actual data — skip or simplify sections with no data. The header
(title, date range, greeting) is handled by the HTML template's
`.report-header` and the in-chat summary — not a separate section.

### Section 1: Logging Overview

Show each day of the week with a status indicator. See `.logging-grid` in the
HTML template.

**Data logic:**
- For each day (Mon–Sun), call `nutrition-calc.py load --date YYYY-MM-DD --tz-offset {tz_offset}` to check:
  - If at least 1 meal has `status: "logged"` → ✅
  - If all meals are `"skipped"` or `"no_reply"` or no log exists → ❌
- Count total days with ✅ → `{X}/7 days logged`

**Commentary rules:**
- 7/7 → `"Perfect week! 🎉"` / `"满勤！🎉"`
- 5-6/7 → `"Nice consistency!"` / `"记录很稳！"`
- 3-4/7 → `"Solid start — let's aim for one more day next week."` / `"不错的开始，下周争取多记一天。"`
- 1-2/7 → `"Every logged day counts. Small steps!"` / `"每记一天都有价值，慢慢来！"`

---

### Section 2: Calorie Analysis

Show daily calorie intake vs target range with bar chart. See `.calorie-table`
and `.calorie-bar` in the HTML template.

**Data logic:**
- For each day, call `nutrition-calc.py load --date YYYY-MM-DD --tz-offset {tz_offset}` and sum `cal` across all meals
- Compare against `Daily Calorie Range` from `PLAN.md`:
  - Below range min → `📉 Below` (bar class: `below`)
  - Within range → `✅ On Target` (bar class: `on-target`)
  - Above range max → `📈 Over` (bar class: `over`)
- Days with no data → `—` (skip from calculations)
- Bar width = `(day_calories / max_calories_in_week) * 100%`

**Commentary rules:**
- Average within range → `"Right on track this week."` / `"这周热量控制得很好。"`
- Average below range → `"A bit under — make sure you're eating enough to sustain energy."` / `"稍微偏低，注意吃够保持精力。"`
- Average above range → `"Slightly over, but a few small adjustments can close the gap."` / `"略微超标，小调整就能回来。"`
- Only 1-2 days of data → Show what's available but note: `"Limited data this week — the more you log, the more useful this gets."`

---

### Section 2b: Weekly Low-Calorie Safety Check

Run **after** Section 2 calorie analysis. Checks if the user's weekly average intake fell below their calorie floor (BMR).

```bash
python3 {diet-tracking-analysis:baseDir}/scripts/nutrition-calc.py weekly-low-cal-check \
  --data-dir {workspaceDir}/data/meals --bmr <kcal> [--date <end-of-week>]
```

Returns: `below_floor`, `weekly_avg_cal`, `calorie_floor`, `days_below_floor`, `days_below_count`.

BMR source: `PLAN.md` or calculate via Mifflin-St Jeor (see `weight-loss-planner/references/formulas.md`).

**When `below_floor` is true:**
Append a gentle safety note in the Calorie Analysis section:
```
⚠️ 这周平均每日摄入（~X kcal）低于基础代谢（~Y kcal）。
持续低于这个水平可能影响代谢和营养摄入。
其中 [day1, day2, ...] 偏低比较明显，下周可以在这几天多加一餐或增加份量。
```
Tone: informational, never guilt or alarm. Offer concrete suggestions (add a snack, increase portion).

**When `below_floor` is false:** No mention — the check passes silently.

---

### Section 3: Weight Progress

Show weight readings and net change. See `.weight-table` and `.weight-change`
in the HTML template.

**Data logic:**
- Call `weight-tracker.py load --from <start> --to <end> --display-unit <unit>` to collect all entries within the period
- If 2+ readings: calculate change = last reading − first reading
- If 1 reading: show it, compare to previous week's last reading if available
- If 0 readings: skip this section entirely (remove the card), add a gentle note

**Commentary rules:**
- Loss within expected rate (from `PLAN.md` weekly rate) → `"Right on pace."` / `"进度刚好。"`
- Loss faster than expected → `"Great progress — just make sure you're not undereating."` / `"进度不错，注意别吃太少。"`
- No change or slight gain → `"Weight fluctuates — one week doesn't define the trend. 💛"` / `"体重会波动，一周说明不了什么。💛"`
- No readings → `"No weigh-ins this week — want to add one next week?"` / `"这周没有称重记录，下周要不要试试？"`

**Never:** compare to target weight in a pressuring way, criticize a gain, or
suggest the user weigh more often than 2x/week.

---

### Section 4: Macronutrient Analysis

Compare average daily macro intake against target ranges. See `.macro-table`
in the HTML template.

**Data logic:**
- Calculate average daily protein, fat, carb from logged meals across the week
  (use `meal_totals` from food logs or `daily_summary` data)
- Compare each macro's average against the range from `PLAN.md`
- Classify: `Below Range` / `In Range` / `Above Range`

**Commentary rules:**
- All in range → `"Balanced macros this week — keep it up!"` / `"三大营养素都在范围内，继续保持！"`
- Protein below → always flag: `"Protein is a bit low — try adding an egg, yogurt, or chicken breast to one meal."` / `"蛋白质偏低，试试每天多加一个鸡蛋或一份鸡胸肉。"`
- Fat over → `"Fat ran a little high — check cooking oils and snacks."` / `"脂肪偏高，留意下烹饪用油和零食。"`
- Insufficient data (< 3 days of macro data) → show what's available with caveat: `"Based on limited data — log more meals for a clearer picture."`

---

### Section 5: Habit Progress

Show the status of active habits. See `.habit-item` in the HTML template.

**Data logic:**
- Read `habits.active` and `habits.daily_log.{date}` for the week
- For each active habit, count completions, misses, and no_responses
- Calculate completion rate for the week
- Check for graduation signals (see `habit-builder` SKILL.md)
- If no active habits exist, skip this section entirely (remove the card)

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

### Section 6: Key Achievements & Suggestions

Two sub-sections in a single card. See `.achievement-list` and
`.suggestion-list` in the HTML template.

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

---

## Formatting Rules

- **Units:** Use the user's preferred system consistently. Read from existing weight logs or `PLAN.md`. Never show dual units.
- **Numbers:** Use locale-appropriate formatting. English: `1,620 kcal`. Chinese: `1620 kcal`.
- **Tone:** Warm, data-driven, encouraging. Like a supportive coach reviewing game tape with an athlete.

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
Skip Sections 2 and 4 (calorie and macro analysis). Show logging overview and
weight progress only. Add note: `"Set up a weight loss plan to unlock calorie and macro tracking in your weekly report."` /
`"创建减脂计划后，周报会加入热量和营养素分析。"`

**Health flags (ED-related):**
If `USER.md > Health Flags` contains `avoid_weight_focus` or `history_of_ed`:
- Skip Section 3 (Weight Progress) entirely
- In calorie section, focus on consistency of eating, not numbers
- Achievements: focus on variety and balance, not restriction

---

## Workspace

### Writes

| Path | When |
|------|------|
| `logs.weekly_report.{start_date}` | After generating the report — store the full report JSON (see `references/data-schemas.md`) |
| `habits.lifestyle_gaps` | When behavioral patterns are detected during weekly analysis (consumed by `habit-builder`) |

---

## Phase Detection

Determine the user's journey phase before composing the Part 1 message.
Phase affects structure, tone, and what gets shown.

**Count past reports:** `report_count` = number of entries in `logs.weekly_report.*`
(not counting the one being generated now).

**Calculate progress percentage:**
```
progress_pct = (start_weight − current_weight) / (start_weight − target_weight) × 100
```
`start_weight` = weight at first report (or onboarding weight from `USER.md`).
`current_weight` = most recent weight reading available.

| Phase | Condition |
|-------|-----------|
| 初始 | `report_count < 4` |
| 中段 | `report_count ≥ 4` AND `progress_pct < 80%` |
| 快完成 | `report_count ≥ 4` AND `progress_pct ≥ 80%` |

**Progress bar** (中段 and 快完成 only):
- 12 characters total: `▓` × `round(progress_pct / 100 × 12)`, remainder `░`
- Example at 68%: `▓▓▓▓▓▓▓▓░░░░`

---

## next_week_focus Tracking

### Writing
After composing the 🎯 section, write the focus action to
`logs.weekly_report.{start_date}` as `next_week_focus` (plain text string).

### Reading (at report generation start)
Before composing this week's report, read `logs.weekly_report.{previous_start_date}`
and check `next_week_focus`.

Determine if the user acted on it by inspecting relevant data for the current week
(e.g., if the focus was protein, check this week's protein average against last week's).

| Outcome | Action |
|---------|--------|
| Acted on it | Add to ✨ 本周亮点: `"上周说要{focus_summary}——做到了。"` |
| Did not act on it | Carry it forward as the first bullet in 🎯，no guilt language |
| Unclear (insufficient data) | Skip — do not mention either way |

---

## Output

### Delivery (two parts)

#### Part 1: WeChat Message

Delivered as plain text in chat. No Markdown. Emoji serve as visual anchors.
Scannable in under 10 seconds.

---

**Inline context rules for the stats line:**

Calorie context (append symbol after the number, no parentheses):
- Within target range → ` ✓`
- Above target max → ` ↑`
- Below target min → ` ↓`
- No PLAN.md → omit symbol

Weight context (append symbol after the number, no parentheses):
- Change matches expected rate ±20% → ` ✓`
- Slower than expected → ` ↑`
- Faster than expected → ` ↓`
- Only 1 reading this week → show change vs last week's reading, no symbol
- 0 readings → replace ⚖️ line with `⚖️ 本周未称重`

Expected rate comes from `PLAN.md > Weight Loss Rate`.

---

**Phase: 初始（report_count < 4）**

```
📊 第{N}周小结

📅 记录 {X}/7 天   🔥 {cal_avg} kcal{calorie_context}   ⚖️ {weight_change}{weight_context}

{one_sentence_summary}

✨ 本周亮点
· {achievement_1}
· {achievement_2}

🎯 下周一件事
{focus_action}

完整数据 👇
```

- No progress bar — too early to show a meaningful arc
- `one_sentence_summary`: freely written, focuses on "getting started" and what
  the user overcame this week. Not a data restatement.
- Achievements: celebrate showing up, first completions, small resistances
- Max 2 achievement bullets

---

**Phase: 中段（report_count ≥ 4，progress_pct < 80%）**

```
📊 第{N}周 · {weekly_headline}

{progress_bar}  已走 {progress_pct}%
{start_weight} → {current_weight} kg → 目标 {target_weight} kg

📅 记录 {X}/7 天   🔥 {cal_avg} kcal{calorie_context}   ⚖️ {weight_change}{weight_context}

{one_sentence_summary}

✨ 本周亮点
· {achievement_1}
· {achievement_2}

🎯 下周一件事
{focus_action}

完整数据 👇
```

- `weekly_headline`: freely written one phrase summarizing the week's character
  (e.g. "低谷期也没停下来" / "节奏回来了" / "这周数字说明不了你").
  Not picked from a fixed list — generate based on actual data and tone.
- `one_sentence_summary`: pattern-level observation, not a data restatement.
  Focus on what this week reveals about the user's trajectory.
- Max 2 achievement bullets; if `next_week_focus` was acted on, it counts as one

---

**Phase: 快完成（report_count ≥ 4，progress_pct ≥ 80%）**

```
📊 第{N}周 · {weekly_headline} 🏁

{progress_bar}  已走 {progress_pct}%
{start_weight} → {current_weight} kg → 目标 {target_weight} kg  只差 {remaining} kg

📅 记录 {X}/7 天   🔥 {cal_avg} kcal{calorie_context}   ⚖️ {weight_change}{weight_context}

{one_sentence_summary}

✨ 本周亮点
· {achievement_1}
· {achievement_2}

🎯 下周一件事
{focus_action}

完整数据 👇
```

- `weekly_headline`: freely written, can reference the finish line or the journey
- `remaining` = `current_weight − target_weight` (display in user's unit)
- `one_sentence_summary`: connect this week to the full journey arc —
  acknowledge how far they've come, not just this week's numbers
- Achievements: at least one should reference the longer journey
  (e.g. "从{start_weight}走到今天" / "这几个月积累的结果")
- 🎯 **still gives a concrete action** — typically protein/muscle preservation
  focus, or preparing for maintenance transition. Do not replace with
  "keep it up" — always give something specific and actionable.
- Estimated weeks remaining: append after `{focus_action}` if computable:
  `按这个节奏，大约还有 {estimated_weeks} 周。`

---

**ED / avoid_weight_focus flag:**
If `USER.md > Health Flags` contains `avoid_weight_focus` or `history_of_ed`:
- Omit the ⚖️ line entirely
- Omit the progress bar and weight fields
- 本周亮点 focuses on consistency, variety, energy — never weight or restriction

---

#### Part 2: HTML Report (cloud-hosted link)

Generate a self-contained HTML file using the template at
`templates/weekly-report.html`. Write the file to
`data/reports/weekly-report-{start_date}.html`.

**HTML generation rules:**
- Replace all `{{PLACEHOLDER}}` values with actual data
- The file must be fully self-contained (all CSS inline, no external dependencies)
- Follow the template structure — do not add or remove sections
- Adapt language to user's locale (from USER.md (already in context))
- Skip sections with no data (remove the entire card, do not show empty cards)
- For the calorie bar chart: calculate bar widths as percentage of the max value in the week

**Upload to cloud storage** using `plan-export`'s upload script (respects
`PLAN_STORAGE_BACKEND` env var for AWS S3 / JD Cloud OSS auto-detection):

```bash
bash {plan-export:baseDir}/scripts/upload-to-s3.sh \
  --file {workspaceDir}/data/reports/weekly-report-{start_date}.html \
  --bucket nanorhino-im-plans \
  --key weekly-report \
  --workspace {workspaceDir}
```

- The script **auto-resolves the username** from the workspace path (→ agentId → `agent-registry.json` shortId). Do NOT pass `--username` manually.
- The script outputs the public URL to stdout. **Send this URL to the user** alongside the Part 1 message.
- The URL is stable (`{username}/weekly-report.html`) — each upload overwrites the previous week's report.
- `plan-url.json` is auto-updated with the `weekly-report` key.

⚠️ **Do NOT use the `jdcloud-oss-upload` skill** for weekly reports. Always use
`plan-export`'s `upload-to-s3.sh` to ensure consistent storage backend selection.

### Report JSON (stored to workspace)

After displaying the report to the user, write a structured JSON summary to
`logs.weekly_report.{start_date}` for cross-session reference and trend
analysis. Schema in `references/data-schemas.md`. Includes `next_week_focus`.

---

## Skill Routing

**See `SKILL-ROUTING.md` for the full conflict resolution system.** This skill
is **Priority Tier P4 (Reporting)**. Key scenarios:

- **Weekly report + exercise weekly summary** (Pattern 3): This skill is the primary owner of weekly summaries. Exercise weekly data (sessions, duration, calories burned, WHO comparison) is incorporated as a section within this report. `exercise-tracking-planning` does NOT produce a separate weekly summary when this skill is generating.
- **Sunday evening auto-report**: Include exercise data from the week. No separate exercise summary needed.
- **User requests "weekly summary"**: Route here, not to exercise-tracking's weekly summary.

---

## Performance

- Report generation: single message, no back-and-forth
- Part 1 WeChat message: scannable in under 10 seconds
- HTML report: aim for 40–60 lines of visible content; unchanged template structure
- Commentary per section: 1–2 sentences max
