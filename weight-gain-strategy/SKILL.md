---
name: weight-gain-strategy
version: 1.0.0
description: "Detect upward weight trends, analyze probable causes from user data (diet, exercise, habits), and produce a personalized adjustment strategy. Trigger when the weekly report or weight-tracking data shows a sustained weight increase (≥ 2 consecutive weigh-ins trending up, or net gain over a 7-day window), or when the user explicitly asks why their weight is rising. Trigger phrases: 'why am I gaining weight', 'weight keeps going up', 'gaining weight', '体重怎么涨了', '越来越重了', '为什么体重上升', '体重反弹了'."
metadata:
  openclaw:
    emoji: "mag"
    homepage: https://github.com/NanoRhino/weight-loss-skill
---

# Weight Gain Strategy

> **SILENT OPERATION:** Never narrate internal actions, skill transitions, or tool calls to the user. No "Let me check...", "Now I'll transition to...". Just do it silently and respond with the result.

Detect upward weight trends, diagnose probable causes by cross-referencing
diet, exercise, and habit data, then collaborate with the user to produce a
concrete, time-bound adjustment strategy for the coming 1–2 weeks.

## Principles

1. **Normalize first.** Weight fluctuations are normal. Never alarm the user — lead with reassurance, then dig into data.
2. **Data + habits before opinions.** Every diagnosis must cite actual numbers from the user's logs OR observable behavioral patterns (e.g., exercise frequency dropping, meal timing shifting, snack patterns emerging). Never speculate without evidence — but evidence includes consistent behavior trends, not just calorie numbers.
3. **One strategy at a time.** Don't overwhelm with five changes. Pick the highest-leverage adjustment and commit to it.
4. **Path of least resistance.** Recommend the strategy that is easiest for the user to execute based on their existing behavior and preferences. If the user already enjoys exercise, suggest adding a session — don't default to calorie reduction. If they love cooking, suggest a recipe swap — don't tell them to skip meals. Match the adjustment to what the user is already good at or willing to do.
5. **Collaborate, don't prescribe.** The user chooses the strategy; you provide options and recommendations.
6. **Respect the user's capacity.** If the user is already stressed, prioritize the easiest adjustment — not the most effective one.
7. **Keep it light.** Use a warm, playful, slightly cheeky tone. You're a witty friend who happens to know nutrition — not a stern doctor reading lab results. Tease gently, celebrate small wins enthusiastically, and never make the user feel like they're being lectured. Examples: "那几顿火锅可能有点嫌疑哦 🤔" rather than "Your calorie intake exceeded the target." Keep the data rigorous but the delivery fun.

---

## Trigger Conditions

### Automatic Trigger: Post-Weigh-In Deviation Check

After every weight log, `weight-tracking` calls the `deviation-check` command
to compare the user's recent trend against their PLAN.md target rate. This is
the **primary trigger path**.

**Severity → Response:**

| Severity | Behavior |
|----------|----------|
| `none` | No action. Weight is on track or within normal fluctuation. |
| `adaptation` | **Adaptation period (first 2 weeks of plan).** Body is still adjusting — reassure the user this is expected. Lightly mention any detected causes (calorie surplus, exercise change, water retention) as informational context, not as problems. Do NOT run `analyze`, do NOT suggest adjustments. Tone: warm, normalizing, educational. |
| `deferred` | **Reassure first, observe later.** A temporary cause was detected (yesterday overeating, possible menstrual cycle, overnight water retention). Respond with a warm, normalizing message based on the `temporary_causes[].message` — then wait until the next weigh-in to re-evaluate. Do NOT run `analyze` or suggest adjustments. |
| `mild` | Append a gentle one-liner to the log confirmation. Single-ask rule applies — if the user ignores it, drop it. |
| `significant` | Run `analyze`, present cause analysis to the user (Step 1 only). Ask if they want to discuss adjustments before proceeding to Step 2. |

**`adaptation` response examples:**

Lead with "body adjusting" reassurance. If the deviation-check also detected specific causes (calorie surplus, exercise decline, temporary causes), mention them lightly as context — informational, not accusatory. The key: specific causes are framed as "by the way, this might also be a factor" rather than "this is the problem."

- **No specific cause detected:** "刚开始新计划，身体还在适应新的饮食节奏，头两周体重波动是很正常的——有时候甚至会先涨一点再往下走，不用担心～" / "Your body is still adjusting to the new routine — fluctuations in the first couple of weeks are totally expected, sometimes weight even goes up a bit before it comes down."
- **With calorie surplus detected:** "头两周身体还在适应中，体重波动是正常的。顺便说一句，最近日均热量比目标稍高一些，等适应期过了可以留意一下～" / "Early fluctuation is normal while your body adjusts. By the way, your average intake has been slightly above target — something to keep an eye on once you've settled in."
- **With temporary cause (e.g., yesterday overeating):** "刚开始计划体重波动很正常，加上昨天吃得多一些，今天涨一点完全可以预期——大部分是水分，别放在心上～" / "Fluctuation is normal this early, and yesterday's bigger meal adds to it — most of that bump is water, don't sweat it."
- **With exercise decline:** "头两周体重波动是正常的，不用紧张。这周运动少了一些，等节奏稳定下来，身体会慢慢跟上的～" / "Totally normal early on. You've been a bit less active this week — once you find your rhythm, things will settle."

**Key rule:** In adaptation period, the primary message is always **"this is expected, your body is adjusting"**. Any specific cause is secondary context, never the headline. Do NOT suggest adjustments — the plan hasn't had enough time to work yet.

**`deferred` response examples:**

- **Yesterday overeating:** "昨天吃得比较多，今天秤上看到变化很正常——多出来的大部分是水分，不是脂肪。过两天再称一次看看～" / "You ate more yesterday, so a bump today is expected — most of it is water, not fat. Let's see where you are in a couple of days."
- **Possible menstrual cycle:** "生理期前后体重波动 1–2 kg 是完全正常的，跟脂肪没关系。等经期结束后再看趋势会更准确～" / "Weight fluctuates 1–2 kg around your period — that's totally normal and not fat. The trend will be clearer once your cycle passes."
- **Sudden overnight spike:** "一夜之间涨了这么多肯定不是脂肪——多半是盐分/水分的原因，过几天会回落的。" / "That kind of overnight jump is almost certainly water/sodium, not fat — it'll come back down."

**Key rule:** When severity is `deferred`, the response tone is **reassurance, not concern**. Never frame the temporary cause as a problem. The goal is to prevent unnecessary anxiety and let the next data point confirm whether a real trend exists.

**Skip conditions:**
- No `PLAN.md` (no plan to deviate from)
- `USER.md > Health Flags` contains `avoid_weight_focus` or `history_of_ed`

### Manual Trigger (user-initiated)

When the user explicitly asks about weight gain ("why am I gaining weight",
"体重怎么涨了"), this skill takes over as the primary responder and runs
the full interactive flow (Analysis → Discussion → Strategy).

---

## Data Sources

### Reads

| Path | Via | Purpose |
|------|-----|---------|
| `data/weight.json` | `weight-tracker.py load` | Weight trend (last 14–28 days) |
| `data/meals/YYYY-MM-DD.json` | `nutrition-calc.py load` | Daily calorie intake for the analysis window |
| `data/exercise.json` | `exercise-calc.py load` | Exercise frequency, duration, and calories burned |
| `PLAN.md` | Direct read | Calorie target, weekly loss rate |
| `health-profile.md` | Direct read | Activity level, meal schedule, unit preference |
| `health-preferences.md` | Direct read | Known preferences and constraints |
| `USER.md` | Direct read | Name, age, sex (for context) |
| `timezone.json` | Direct read | Timezone offset for date calculations |
| `engagement.json` | Direct read | Engagement stage |

### Writes

| Path | When |
|------|------|
| `data/weight-gain-strategy.json` | After the user confirms a strategy — stores the active strategy with start date, end date, type, and parameters |
| `health-preferences.md` | If the user reveals new preferences during the conversation (append only) |

---

## Analysis Script

Script path: `python3 {baseDir}/scripts/analyze-weight-trend.py`

### Command: `analyze`

```bash
python3 {baseDir}/scripts/analyze-weight-trend.py analyze \
  --data-dir {workspaceDir}/data \
  --weight-script {weight-tracking:baseDir}/scripts/weight-tracker.py \
  --nutrition-script {diet-tracking-analysis:baseDir}/scripts/nutrition-calc.py \
  --exercise-script {exercise-tracking-planning:baseDir}/scripts/exercise-calc.py \
  --plan-file {workspaceDir}/PLAN.md \
  --health-profile {workspaceDir}/health-profile.md \
  --tz-offset {tz_offset} \
  --window 14
```

**Returns** a JSON object:

```json
{
  "trend": {
    "direction": "up",
    "net_change_kg": 0.8,
    "net_change_display": "0.8 kg",
    "window_days": 14,
    "readings": [
      {"date": "2026-03-10", "value": 74.2, "unit": "kg"},
      {"date": "2026-03-17", "value": 74.6, "unit": "kg"},
      {"date": "2026-03-24", "value": 75.0, "unit": "kg"}
    ]
  },
  "diagnosis": {
    "calorie_surplus": {
      "detected": true,
      "avg_daily_intake": 1850,
      "target": 1600,
      "surplus_kcal": 250,
      "days_over_target": 10,
      "days_total": 14
    },
    "exercise_decline": {
      "detected": true,
      "current_week_sessions": 1,
      "previous_week_sessions": 3,
      "current_week_minutes": 30,
      "previous_week_minutes": 120
    },
    "logging_gaps": {
      "detected": false,
      "unlogged_days": 2,
      "total_days": 14
    },
    "possible_water_retention": {
      "detected": false,
      "note": "Sudden spike ≥ 0.5 kg in 1–2 days without calorie surplus"
    },
    "normal_fluctuation": {
      "detected": false,
      "note": "Net change < 0.5 kg over 14 days with no sustained trend"
    }
  },
  "top_factors": ["calorie_surplus", "exercise_decline"],
  "suggested_strategies": [
    {
      "type": "reduce_calories",
      "description": "Reduce daily intake by 150 kcal",
      "target_kcal": 1450,
      "duration_days": 7,
      "expected_impact": "~0.15 kg deficit per week"
    },
    {
      "type": "increase_exercise",
      "description": "Add 2 more exercise sessions this week",
      "target_sessions": 3,
      "target_minutes_per_session": 30,
      "duration_days": 7,
      "expected_impact": "~200 kcal additional burn per session"
    }
  ]
}
```

### Command: `deviation-check`

Lightweight post-weigh-in check. Called by `weight-tracking` after every weight
log to determine if the user's trend deviates from PLAN.md.

```bash
python3 {baseDir}/scripts/analyze-weight-trend.py deviation-check \
  --data-dir {workspaceDir}/data \
  --plan-file {workspaceDir}/PLAN.md \
  --health-profile {workspaceDir}/health-profile.md \
  --user-file {workspaceDir}/USER.md \
  --plan-start-date {plan_start_date} \
  --tz-offset {tz_offset}
```

The `--plan-start-date` is read from the `开始日期` / `Start date` field in
`PLAN.md`. If not passed, the script also attempts to parse it directly from
`PLAN.md`. Used to detect the adaptation period (first 14 days).

**Returns:**

```json
{
  "triggered": true,
  "severity": "deferred",
  "raw_severity": "mild",
  "window": {
    "start_date": "2026-03-10",
    "end_date": "2026-03-24",
    "days": 14
  },
  "plan_rate_kg_per_week": 0.6,
  "expected_change_kg": -1.2,
  "actual_change_kg": 0.4,
  "deviation_kg": 1.6,
  "latest_weight": 75.0,
  "latest_unit": "kg",
  "readings_count": 4,
  "adaptation_period": false,
  "temporary_causes": [
    {
      "cause": "yesterday_overeating",
      "message": "Yesterday's intake was 2400 kcal (+41% over target)...",
      "yesterday_cal": 2400,
      "target_cal": 1700,
      "overshoot_kcal": 700
    }
  ],
  "recommendation": "Reassure the user (temporary cause detected). Defer analysis to next weigh-in cycle."
}
```

**Severity levels:**
- `none` — actual change tracks plan within 0.3 kg tolerance
- `adaptation` — deviation detected but user is in the first 2 weeks of their plan. Reassure that early fluctuation is normal; lightly mention detected causes as context. No adjustments.
- `deferred` — deviation detected but a temporary cause explains it (yesterday overeating, menstrual cycle water retention, sudden overnight spike). Reassure user and re-evaluate at next weigh-in.
- `mild` — deviation 0.3–0.8 kg with no temporary explanation
- `significant` — deviation > 0.8 kg with no temporary explanation

**Temporary cause detection:**
- `yesterday_overeating` — previous day's calorie intake ≥ 30% over target
- `possible_menstrual_cycle` — female user, sudden ≥ 0.5 kg spike in ≤ 5 days while average weekly intake is within target
- `sudden_spike` — ≥ 0.8 kg jump in ≤ 2 days (water/sodium retention)

**Design notes:**
- Requires ≥ 2 readings spanning ≥ 3 days (avoids false alarms from daily fluctuation)
- Reads `data/weight.json` and `data/meals/` directly for speed
- Adaptation period (first 14 days of plan) caps severity to `adaptation` — reassure with light cause context, no adjustments
- When temporary causes are detected (outside adaptation period), severity downgrades to `deferred` — no full analysis runs
- `adaptation_period` takes priority over `deferred` (if both apply, `adaptation` wins since it's the stronger reassurance signal)
- `raw_severity` preserves the pre-adjustment severity for logging/debugging

### Command: `save-strategy`

```bash
python3 {baseDir}/scripts/analyze-weight-trend.py save-strategy \
  --data-dir {workspaceDir}/data \
  --strategy-type reduce_calories|increase_exercise|adjust_schedule|combined \
  --params '{"target_kcal": 1450, "duration_days": 7}' \
  --tz-offset {tz_offset}
```

Saves the active strategy to `data/weight-gain-strategy.json`.

### Command: `check-strategy`

```bash
python3 {baseDir}/scripts/analyze-weight-trend.py check-strategy \
  --data-dir {workspaceDir}/data \
  --tz-offset {tz_offset}
```

Returns the current active strategy and progress against it (for use by
`weekly-report` and `notification-composer`).

---

## Interactive Flow

Applies to both auto-triggered (post-weigh-in significant deviation) and
manual-triggered (user asks about weight gain) paths. **The key principle:
always show the cause analysis first — never jump straight to strategies.**

### Step 1: Analyze & Present Causes (always runs first)

1. Read `timezone.json` for tz_offset
2. Run the `analyze` command
3. Present findings to the user in a conversational, non-alarming way

**Presentation structure:**

**[Reassurance]** — One playful sentence normalizing weight fluctuation. Never open with bad news. Set a light, "no big deal" tone.

**[Trend summary]** — State the facts briefly but conversationally:
- "这 {N} 天体重从 {start} 溜达到了 {end}，涨了 {change}。" / "Over the past {N} days, your weight wandered from {start} to {end} ({change})."

**[Diagnosis]** — For each detected factor in `top_factors`, explain it in plain language with data. Also cross-reference behavioral patterns from `health-profile.md` and recent logs — behavior changes (skipped workouts, new snack habits, shifted meal times) are valid diagnostic evidence alongside raw numbers. Keep the tone curious and light, not accusatory:

- **Calorie surplus:** "日均吃了 {avg} kcal，比目标 {target} 多了大概 {surplus}——{Y} 天里有 {X} 天超标，看起来零食有点活跃哦～" / "You averaged {avg} kcal/day — about {surplus} over your {target} target. Over target on {X} of {Y} days. Looks like snacks have been busy!"
- **Exercise decline:** "这周运动了 {current} 次，上周可是 {previous} 次呢——少了大概 {diff} 分钟的活动量，身体有点'放假模式'了～" / "You worked out {current} time(s) this week vs {previous} last week — {diff} fewer minutes. Your body might be on vacation mode!"
- **Logging gaps:** "{X} 天没记录饮食，侦探也得有线索才能破案呀～" / "No meal logs for {X} days — even a detective needs clues!"
- **Water retention:** "涨得这么突然，大概率是水分搞的鬼——过几天就会回落的，别慌～" / "That jump is suspiciously sudden — likely water playing tricks. Give it a few days."
- **Normal fluctuation:** "这点波动完全正常，身体不是机器，不会每天一模一样的～" / "Totally normal fluctuation — bodies aren't machines!"
- **Behavioral pattern shift:** When a habit change is detected (e.g., user stopped their usual evening walks, started ordering delivery more often, shifted dinner to later), call it out gently: "最近晚饭时间好像越来越晚了，身体消化的节奏可能被打乱了～" / "Looks like dinner has been creeping later — that can throw off your body's rhythm."

**[Pause here — do NOT continue to Step 2 automatically]**

**[Transition to Step 2]** — "要不要一起想想怎么小调一下？" / "Want to brainstorm a tweak or two?"

If the diagnosis is `normal_fluctuation`, skip to a reassuring close — do NOT propose changes for normal fluctuation.

**Only proceed to Step 2 when the user explicitly agrees.** If the user
ignores the question, acknowledges without interest, or changes topic, drop it.
This ensures the user never feels pressured into a strategy discussion they
didn't ask for.

### Step 2: Discuss & Choose Strategy

Present 1–3 strategy options based on the `suggested_strategies` from the analysis.

**Strategy ranking rule:** Sort options by ease-of-execution for this specific user, not by theoretical effectiveness. Cross-reference `health-profile.md` (activity level, preferences) and `health-preferences.md` to determine what the user is already good at or enjoys. Put the lowest-friction option first. Examples:
- User exercises regularly → lead with "add one more session" rather than "cut calories"
- User enjoys cooking → lead with "swap this ingredient" rather than "eat less"
- User is sedentary but has been logging meals diligently → lead with a small calorie tweak they can track easily
- User's exercise dropped recently but they used to be active → lead with "get back to your old routine" (reactivation is easier than starting fresh)

For each option:

**Format:**

```
Option {N}: {strategy_name}
{one-sentence description}
{expected_impact} over {duration}
```

**Strategy Types:**

#### A. Reduce Calories (`reduce_calories`)
- Reduce daily intake by 100–300 kcal (never below calorie floor)
- Suggest specific meal adjustments based on the user's logged meals (e.g., "swap the afternoon snack for fruit", "reduce rice portion at dinner by 1/3")
- Duration: 1–2 weeks, then reassess

#### B. Increase Exercise (`increase_exercise`)
- Add 1–3 more exercise sessions per week
- Suggest activities aligned with user's existing habits and preferences
- If user doesn't exercise, suggest walking 20–30 min/day as a starting point
- Duration: 1–2 weeks, then reassess

#### C. Adjust Schedule (`adjust_schedule`)
- Shift meal timing (e.g., earlier dinner, longer overnight fast)
- Only suggest if the user's current schedule has obvious issues (e.g., late-night eating pattern detected)
- Duration: 1 week trial

#### D. Combined (`combined`)
- A modest version of A + B (smaller calorie reduction + 1 extra session)
- For users who prefer balanced adjustments
- Duration: 1–2 weeks

**After presenting options:** Ask the user which feels most doable — keep the tone light: "哪个听起来最不像受罪？" / "Which one sounds the least like torture?" Respect their choice. If they choose something suboptimal, support it enthusiastically — compliance beats optimization every time.

### Step 3: Confirm & Save Strategy

1. Confirm the chosen strategy with specific, actionable details:
   - What exactly changes (calorie target, number of sessions, specific meals)
   - For how long (start date → end date)
   - When to check in (midpoint and end)
2. Run `save-strategy` to persist the strategy
3. Close with encouragement — brief, genuine, a bit cheeky. No hollow platitudes like "you've got this!" — instead, something specific and fun: "下周这个时候秤上见分晓～" / "Let's see what the scale says next week — I'm betting on you."

**Do NOT:**
- Set up reminders here (that's `notification-manager`'s job)
- Modify PLAN.md (the strategy is temporary; PLAN.md is the long-term plan)
- Generate HTML reports

---

## Safety Rules

- **Calorie floor:** Never suggest intake below max(BMR, 1000 kcal/day). Read the floor from PLAN.md or recalculate via `planner-calc.py`.
- **Exercise safety:** For users who are sedentary or have health conditions noted in `USER.md`, start with walking and low-impact activities only.
- **Emotional awareness:** If the user shows signs of distress about the weight gain, defer to `emotional-support` per SKILL-ROUTING.md. Come back to strategy only when the user is ready.
- **No shame, no blame.** Never imply the weight gain is the user's fault. Frame adjustments as experiments, not corrections.
- **ED flags:** If `USER.md > Health Flags` contains `avoid_weight_focus` or `history_of_ed`, do NOT run this skill automatically. Only respond if the user explicitly asks, and focus on behaviors (activity, sleep, stress) rather than weight numbers.

---

## Strategy Data Schema

**File:** `data/weight-gain-strategy.json`

```json
{
  "active_strategy": {
    "type": "reduce_calories",
    "start_date": "2026-03-24",
    "end_date": "2026-03-31",
    "params": {
      "target_kcal": 1450,
      "original_target_kcal": 1600,
      "reduction_kcal": 150
    },
    "status": "active",
    "created_at": "2026-03-24T10:00:00+08:00"
  },
  "history": [
    {
      "type": "increase_exercise",
      "start_date": "2026-03-10",
      "end_date": "2026-03-17",
      "params": {
        "target_sessions": 3,
        "target_minutes_per_session": 30
      },
      "status": "completed",
      "outcome": "weight stabilized"
    }
  ]
}
```

---

## Integration with Other Skills

| Skill | Integration |
|-------|-------------|
| `weekly-report` | Reads `check-strategy` output to report on active strategy progress. |
| `notification-composer` | Reads `check-strategy` output to optionally include mid-week strategy check-in reminders. |
| `weight-tracking` | Source of weight data. This skill reads only — never writes to `data/weight.json`. |
| `diet-tracking-analysis` | Source of meal data. This skill reads only — never writes to `data/meals/`. |
| `exercise-tracking-planning` | Source of exercise data. This skill reads only — never writes to `data/exercise.json`. |
| `emotional-support` | Takes priority (P1) when user shows distress about weight gain. This skill defers. |
| `weight-loss-planner` | Owns PLAN.md. This skill reads the plan but never modifies it. Strategies are temporary overlays. |

---

## Skill Routing

**Priority Tier: P3 (Planning)** — same tier as `weight-loss-planner` and `meal-planner`.

### Conflict Patterns

**Weight gain strategy + Emotional distress (P3 vs P1):**
Emotional support leads. If user says "I'm gaining weight and I hate myself",
`emotional-support` takes over. Weight gain analysis happens later, only if
the user asks for it.

**Weight gain strategy + Diet logging (P3 vs P2):**
If the user logs food AND asks about weight gain in the same message, log the
food first (P2), then provide the weight gain analysis.

**Weight gain strategy + Weight-loss planner (same tier):**
If the user asks to redo their plan because of weight gain, route to
`weight-loss-planner` for a full recalculation. This skill handles
short-term tactical adjustments only; replanning is a different skill's job.

---

## Edge Cases

**Insufficient data (< 3 weight readings in 14 days):**
Cannot diagnose reliably. Respond with: "I don't have enough weight data to
spot a clear trend — try weighing in 1–2 times per week and we'll have a
better picture soon."

**No meal logs:**
Skip calorie surplus analysis. Note the gap: "Without meal logs, I can't
check if calorie intake is a factor. Want to start logging meals?"

**User is in first 2 weeks of plan (adaptation period):**
Weight fluctuation is expected at the start. The `deviation-check` will return
`severity: "adaptation"` — respond with reassurance and lightly mention any
detected causes as context (not problems). Do NOT suggest adjustments. If the
user explicitly asks for changes, gently recommend waiting: "身体还在适应中，
我们再观察一周，到时候数据会更清楚～" / "Your body is still adjusting — let's
give it another week and the picture will be clearer."

**Weight gain is muscle gain (exercise increased significantly):**
If exercise volume increased significantly while weight went up, note the
possibility: "You've been exercising more — some of this could be muscle.
How do your clothes fit? That's often a better indicator than the scale."

**Active strategy already exists:**
If a strategy is already active and the user asks again, show progress on
the current strategy first. Only propose a new strategy if the current one
has ended or the user explicitly wants to change.
