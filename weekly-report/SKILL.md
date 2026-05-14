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

> 🚨 **CRITICAL: ALL reports use template+data separation. `generate-report-html.py` outputs JSON data files. The HTML template (`templates/weekly-report.html`) renders client-side. WRITING HTML YOURSELF IS FORBIDDEN. NO EXCEPTIONS.**

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

> **Auto-send:** Weekly reports are sent via **per-user cron** (Sunday 21:00 user local time).
> The cron job runs `should-send-report.sh` as a gate check before generating.
> When onboarding a new user, create a weekly report cron job for them (see notification-manager SKILL.md).

1. User in Stage ≥ 3 (recall/silent)? → skip auto-send, but still generate if manually requested
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

### Reads from data (workspace) — ONE-SHOT COLLECTION

**⚠️ Use `collect-weekly-data.py` instead of calling individual scripts.**
This single script replaces 7+ `nutrition-calc.py load` calls + `weight-tracker.py` + `exercise-calc.py`
and outputs all data needed for the report as JSON:

```bash
python3 {baseDir}/scripts/collect-weekly-data.py \
  --workspace-dir {workspaceDir} \
  --start-date {monday} \
  --end-date {sunday} \
  --tz-offset {tz_offset} \
  --display-unit <kg|lb>
```

Output JSON structure:
```json
{
  "meta": { "week_number", "report_count", "prev_exists", "prev_start", "next_start", "first_monday" },
  "plan": { "cal_min": [min, max], "tdee", "bmr", "protein_range", "fat_range", "carb_range", ... },
  "summary": { "logged_days", "cal_avg", "cal_max", "chart_max", "protein_avg", "fat_avg", "carb_avg", "weight_change", "cal_min", "cal_max_target" },
  "days": [{ "date", "weekday", "logged", "cal_status", "meals": [{meal_type, cal, protein, fat, carb, foods}], "totals": {cal, protein, fat, carb} }],
  "weight": { "readings": [{date, value, unit}], "change" },
  "weight_all": [{date, value, unit}],  // ALL historical weight readings for chart rendering
  "exercise": { "sessions": [...], "total_calories", "total_minutes" },
  "habits": { "active": [...], "daily_log": {...}, "graduated": [...] }
}
```

Use this JSON to populate all report sections. **Do NOT call `nutrition-calc.py load` per-day or other individual scripts.**

**Legacy note:** The following individual script calls are kept for reference but should NOT be used when generating weekly reports:
| Path | Script | Purpose |
|------|--------|---------|
| `data/meals/YYYY-MM-DD.json` | `nutrition-calc.py load` | Per-day meal data |
| `data/weight.json` | `weight-tracker.py load` | Weight readings |
| `data/exercise.json` | `exercise-calc.py load` | Exercise sessions |
| `habits.active` | direct read | Habit data |

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

### 📐 Chart Design Rules (Global)

All charts in the HTML report follow these universal rules:

**Layout & alignment:**
- All charts use the same left padding (`2.5rem`) for Y-axis labels → charts align vertically
- Bar chart Y-axis labels: `position: absolute; left: -2.5rem; transform: translateY(-50%)`
- X-axis labels (周一-周日) go **outside** the chart div in a separate `.cal-x-labels` container
- Weight chart Y-axis is a separate fixed div (`.weight-y-axis`, width `2.5rem`) that doesn't scroll with the SVG

**Bar chart rules (calorie + macros):**
- Bar colors: `#6bcb8b` (on-target/达标), `#c8e6c9` (below/偏低), `#fdd0b1` (over/超标)
- All bars have `opacity: 0.75`
- Bar width: `60%` of column, `max-width: 36px`, `border-radius: 4px 4px 0 0`
- Each bar has a value label above it (`.cal-bar-value`)
- Days with no data: `class="empty"`, height 0, no value label
- Target range band: grey shadow only (`background: rgba(0,0,0,0.05)`), **no border/dashed lines** on the band itself
- Grid lines: `1px dashed #e8e5dd` at round-number intervals
- **0-coordinate grid line: solid** (`border-bottom-style: solid`), not dashed
- Y-axis ticks: 3-5 round numbers max (avoid clutter). Examples:
  - Calories (max ~2400): 0, 500, 1000, 1500, 2000
  - Carbs (max ~300): 0, 100, 200, 300
  - Protein (max ~120): 0, 40, 80, 120
  - Fat (max ~90): 0, 40, 80

**Average line (macros only):**
- `1px dashed #333` (black), z-index 2 (above bars)
- Label: `"平均摄入 {value}"`, color `#333`, font-weight 500, positioned at right edge

**Legend (macros section):**
- Displayed once above all three macro charts
- Items: 达标 (深绿) / 偏低 (浅绿) / 超标 (浅橙)

**Weight chart (SVG):**
- Smooth curves using **Catmull-Rom** spline (not polyline, not manually-tweaked bezier)
- Green gradient fill under actual data curve (`#6bcb8b`, opacity 0.3→0.02)
- Plan/target path: grey solid thin line (`stroke: #ccc`, `stroke-width: 1`) with light fill (`rgba(0,0,0,0.04)`)
  - Calculated from first weight reading, decreasing at planned rate (default -0.5kg/week)
  - Label: `"计划 −Xkg/周"` at bottom-right of plan area
- Historical data points: small circles (`r=4.5`, white fill, `#a8deb8` stroke)
- Current week data points: larger circles (`r=6`, `#6bcb8b` fill, white stroke), bold labels
- Y-axis: auto-range to fit both actual data AND plan path, with ~10% padding
- Y-axis labels: fixed position (don't scroll with SVG)
- SVG is horizontally scrollable on mobile (`overflow-x: auto`, `-webkit-overflow-scrolling: touch`)
- Default scroll position: rightmost (show latest data)
- Scroll hint: `"← 左右滑动查看更多 →"` below chart

**Sticky navigation:**
- `.week-nav`: `position: sticky; top: 0; z-index: 100`
- Parent `.page` must have `padding-top: 0` (not 2rem) to avoid sticky offset
- `.report-header` gets `margin-top: 1.5rem` to compensate

---

### Section 2: Calorie Analysis

Show daily calorie intake vs target range with a **vertical bar chart** and grey target
range band. See `.cal-chart`, `.cal-bar`, `.cal-target-band` in the HTML template.

**Data logic:**
- For each day, call `nutrition-calc.py load --date YYYY-MM-DD --tz-offset {tz_offset}` and sum `cal` across all meals
- Compare against `Daily Calorie Range` from `PLAN.md`:
  - Below range min → class `below`
  - Within range → class `on-target`
  - Above range max → class `over`
- Days with no data → class `empty`, height 0, no value label
- Chart max = `max(max_calories_in_week, CAL_MAX * 1.2)` (ensure target band is visible)
- Bar height (px) = `(day_calories / chart_max) * 220`
- **Target range band:** `bottom = (CAL_MIN / chart_max) * 100%`, `height = ((CAL_MAX - CAL_MIN) / chart_max) * 100%`
- **Grid lines:** place at round 500 kcal intervals, `bottom = (value / chart_max) * 100%`

**Commentary rules:**
- Average within range → `"Right on track this week."` / `"这周热量控制得很好。"`
- Average below range → `"A bit under — make sure you're eating enough to sustain energy."` / `"稍微偏低，注意吃够保持精力。"`
- Average above range → `"Slightly over, but a few small adjustments can close the gap."` / `"略微超标，小调整就能回来。"`
- Only 1-2 days of data → Show what's available but note: `"Limited data this week — the more you log, the more useful this gets."`

---

### Section 2b: Weekly Low-Calorie Safety Check

Run **after** Section 2 calorie analysis.

**Data logic:**
1. Get BMR from `PLAN.md` (or calculate via Mifflin-St Jeor: see `weight-loss-planner/references/formulas.md`)
2. Run the check script:
   ```bash
   python3 {baseDir}/scripts/weekly-low-cal-check.py \
     --data-dir {workspaceDir}/data/meals \
     --bmr <BMR from PLAN.md> \
     --date <end-of-week YYYY-MM-DD> \
     --tz-offset {tz_offset}
   ```
   Returns: `weekly_avg_calories`, `bmr`, `below_floor`, `days_below_floor`, `days_below_count`

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

Show daily macro intake as **three separate vertical bar charts** (碳水/蛋白质/脂肪),
each with per-day bars, a grey target range band, and an average line.
Uses the same `.cal-chart`, `.cal-bar-col`, `.cal-bar-wrapper` CSS as the calorie chart.

**Data logic:**
- Use `collect-weekly-data.py` output which includes per-day macro values with
  meal-fill estimation (missing meal types filled with weekly average for that type)
- For each macro, compare each day's value against target range:
  - Below range min → `background: #c8e6c9` (浅绿)
  - Within range → `background: #6bcb8b` (深绿)
  - Above range max → `background: #fdd0b1` (浅橙)
- Days with no logged data → empty bar (height 0)
- Average line (`平均摄入 {value}`): `1px dashed #333`, label in black
- Target range: grey band only (no border lines), with label `目标 {low}–{high}`
- Chart max per macro: enough to show all bars + target high with padding
  - Carb: ~300-350g, Protein: ~120-150g, Fat: ~90-100g
- Y-axis ticks: 3-5 round numbers (e.g., carb: 0/100/200/300)
- If `macro_estimated: true`, show footnote: `"* 部分天数记录不全，缺失餐次按本周同类餐平均值估算"`

**Target range source:**
1. Primary: `PLAN.md` macro ranges
2. Fallback: auto-derive from health-profile (protein=weight×1.2g/kg, fat=25-35% cal, carb=remainder)

**Commentary rules:**
- All in range → `"三大营养素都在范围内，继续保持！"`
- Protein below → always flag with actionable fix
- Fat over → mention cooking oils and snacks
- Insufficient data (< 3 days) → show with caveat

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

## ⚠️ CRITICAL: Execution Order

**You MUST complete ALL tool calls BEFORE writing your final message to the user.**

The correct sequence is:
1. Collect data (nutrition-calc, weight-tracker, etc.)
2. Generate JSON data file → write to `data/reports/weekly-data-{start_date}.html`
3. Upload JSON + HTML template via `upload-to-s3.sh` → capture the URL from stdout
4. **ONLY THEN** compose and send the final message (Part 1 + URL)

**NEVER write "完整数据 👇" or any link placeholder without having the actual URL from step 3.** If upload fails, omit the "完整数据" line entirely — do not leave a broken link.

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
📊 第{N}周周报
完整分析 👇 {report_url}

{progress_bar}  已走 {progress_pct}%
{start_weight} → {current_weight} kg → 目标 {target_weight} kg

{data_hook}
```

- `data_hook`: ONE sentence based on this week's actual data that sparks curiosity.
  Must reference a specific finding, not a generic summary.
  Rotate between different hook styles — never repeat the same angle two weeks in a row:
  · **反直觉**: "这周有一天吃得最多反而掉秤最狠，猜猜是哪天👀"
  · **发现规律**: "你可能没注意到，这周每次吃面的那天热量都超了🍜"
  · **对比悬念**: "跟第1周比你有一个数据变化很大，点进来看"
  · **接近里程碑**: "再掉0.7就到55了，这周的节奏够不够？看完就知道"
  · **具体某餐**: "周四那顿是这6周以来营养最均衡的一餐，不是巧合"
  NOT: "本周表现不错" / "继续加油" / generic praise / template-sounding language

---

**Phase: 中段（report_count ≥ 4，progress_pct < 80%）**

```
📊 第{N}周周报
完整分析 👇 {report_url}

{progress_bar}  已走 {progress_pct}%
{start_weight} → {current_weight} kg → 目标 {target_weight} kg

{data_hook}
```

- `data_hook`: same rules as above — one specific data-driven observation.
  Rotate styles, keep it fresh. Write like a human who just noticed something interesting.

---

**Phase: 快完成（report_count ≥ 4，progress_pct ≥ 80%）**

```
📊 第{N}周周报
完整分析 👇 {report_url}

{progress_bar}  已走 {progress_pct}%
{start_weight} → {current_weight} kg → 目标 {target_weight} kg  只差 {remaining} kg

{data_hook}
```

- `remaining` = `current_weight − target_weight` (display in user's unit)
- `data_hook`: connect to the journey arc — reference a trend or milestone

---

**ED / avoid_weight_focus flag:**
If `USER.md > Health Flags` contains `avoid_weight_focus` or `history_of_ed`:
- Omit the ⚖️ line entirely
- Omit the progress bar and weight fields
- `data_hook` focuses on consistency, variety, energy — never weight or restriction

---

#### Part 2: Weekly Report (cloud-hosted link)

**Architecture: Template + Data separation.**
- `generate-report-html.py` outputs a **JSON data file** (not HTML)
- `templates/weekly-report.html` is a **single HTML template** that renders any week's data client-side via JS
- URL format: `https://nanorhino.ai/user/{username}/weekly-report.html?week={start_date}`
- Changing the template automatically updates ALL historical reports (no regeneration needed)

⚠️ **MANDATORY**: You MUST call `generate-report-html.py`. Writing HTML by hand is FORBIDDEN.

> 🚨 **ALL parameters are REQUIRED — do NOT pass empty values for `--commentary`, `--highlights`, or `--suggestions`.** Every report MUST have personalized analysis. If you pass `'{}'` or `'[]'`, the report will show generic fallback text and the user experience is degraded. Read the data, think about it, then write real commentary.

```bash
python3 {baseDir}/scripts/collect-weekly-data.py \
  --workspace-dir {workspaceDir} \
  --start-date {monday} --end-date {sunday} --tz-offset {tz_offset} \
  2>&1 | tail -n +2 | \
python3 {baseDir}/scripts/generate-report-html.py \
  --output {workspaceDir}/data/reports/weekly-data-{start_date}.html \
  --workspace-dir {workspaceDir} \
  --nickname {user_nickname} \
  --tagline '{short fun summary of the week}' \
  --plan-rate {weight_loss_rate_per_week} \
  --commentary '{JSON object with section commentaries}' \
  --highlights '{JSON array of highlight strings}' \
  --suggestions '{JSON array of suggestion strings}'
```

**The script's stdout is the report URL.** Capture it and use it in the Part 1 message.

**What the script does automatically** (you do NOT need to do these manually):
1. Generates JSON data file
2. Copies `weekly-data-latest.html` (if this is the newest week)
3. Copies HTML template to reports dir
4. **Uploads 3 files to cloud storage** (dated data + latest + template)
5. **Writes report log** to `data/logs/weekly-report-{start_date}.json`
6. Outputs the public report URL to stdout

**What YOU provide as parameters:**
- `--nickname`: user's display name (from USER.md)
- `--tagline`: short, fun one-liner summarizing the week (witty, teasing, spoken Chinese — like a friend roasting you with love)
- `--commentary`: JSON object with keys `logging`, `calories`, `weight`, `macros` — your personalized analysis for each section. **Write like a sassy best friend who happens to know nutrition**: use casual spoken Chinese (口语化), be funny/witty, tease when appropriate, but always back it up with real numbers. Use `cal_avg_estimated` (meal-filled estimate) for dietary assessment, NOT `cal_avg` (which is deflated by missed-meal days). If `days_with_missing_meals > 0`, mention that some days had incomplete records. Each commentary should be 2-4 sentences.
- `--highlights`: JSON array of 2-3 this-week highlights — be specific and celebratory
- `--suggestions`: JSON array of 1-2 actionable next-week suggestions — concrete and encouraging
- `--plan-rate`: weight loss rate in kg/week (read from health-profile, default 0.5)

**Optional flags:**
- `--no-upload`: Skip cloud upload (for local testing)
- `--no-log`: Skip writing report log (for backfilling history)
- `--username`: Override auto-resolved username

**Username is auto-resolved** from the workspace path (→ agentId → `agent-registry.json` shortId). Do NOT pass `--username` manually unless testing.

**Report URLs:**
- **Report URL**: `https://nanorhino.ai/user/{username}/weekly-report.html?week={start_date}`
- **Latest URL**: `https://nanorhino.ai/user/{username}/weekly-report.html` (no `?week=` → loads latest)

⚠️ **Do NOT manually call `upload-to-s3.sh` for weekly reports.** The script handles all uploads internally. Manual upload is only needed for one-off fixes.

### Week Navigation (Previous / Next)

Handled automatically by the HTML template (`templates/weekly-report.html`). The template reads `meta.prev_start`, `meta.prev_exists`, and `meta.next_start` from the JSON data to generate sticky navigation. Clicking prev/next fetches the new JSON and re-renders without page reload.

⚠️ Navigation uses `?week=YYYY-MM-DD` URL parameters. No full URL construction needed — the template auto-resolves relative paths.

### Week Number Calculation

`{N}` (used as `第{N}周` in chat message and `{{WEEK_NUMBER}}` in HTML) is calculated from the user's **first logging week**:

```
first_monday = the Monday of the week when the user first logged a meal
               (= earliest date in data/meals/*.json, rounded back to its Monday)
N = ((start_date - first_monday) / 7) + 1
```

**Example:** User first logged on Wed 2026-03-26 → first_monday = 2026-03-24 → that week is Week 1. Report for 2026-03-31~04-06 is Week 2.

**If no meals exist at all:** Use `PLAN.md > 开始日期` as fallback, rounded back to its Monday.

**Never use ISO week numbers or calendar year week numbers.** The week count is always relative to the user's personal start.

### Report Period: Monday to Sunday

Every weekly report covers exactly **Monday 00:00 to Sunday 23:59** (user's local time). The `{start_date}` is always a Monday. The script output `current_week` already provides the correct Monday–Sunday range — **never adjust it**.

When querying meal data, weight data, and exercise data, use exactly this Monday–Sunday range. Do not use the script's `previous_week` unless generating a report for the prior period.

⚠️ **Do NOT use the `jdcloud-oss-upload` skill** for weekly reports. Always use
`plan-export`'s `upload-to-s3.sh` to ensure consistent storage backend selection.

### Report JSON (auto-written by script)

`generate-report-html.py` automatically writes a structured JSON summary to
`data/logs/weekly-report-{start_date}.json` after each generation.
Includes summary stats, commentary, highlights, suggestions, and the report URL.
Used for `next_week_focus` tracking and cross-session reference.
To skip (e.g., backfilling): pass `--no-log`.

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
