# Deviation Check — Severity Response Guide

Deviation-check is bundled into `save-and-check.py` — no separate call needed. The `deviation` field in the combined response contains the result. The script handles all skip logic internally (missing PLAN.md, health flags, insufficient data).

## Result Fields

- `triggered: false` → no action, just confirm the log
- `triggered: false` + `reason: "no_plan"` → no PLAN.md, skip silently
- `triggered: false` + `reason: "health_flag"` → skip silently
- `triggered: false` + `reason: "insufficient_data"` → skip silently
- `triggered: true` → respond per severity below
- `temporary_causes` → if present, mention lightly
- `adaptation_period: true` → first 2 weeks of plan, be extra gentle

---

## Severity: `none` (streak 0)

Weight stable or down — just confirm the log. No extra output.

---

## Severity: `comfort` (streak 1)

Append a warm one-liner after log confirmation. See `weight-gain-strategy` SKILL.md `references/diagnosis-templates.md` for examples.

---

## Severity: `cause-check` (streak 2–3)

> ⚠️ **MANDATORY: Follow Steps A→B→C→D exactly. Do NOT freestyle. Do NOT give advice without running `analyze` first.**

Multi-turn guided discovery. Each step waits for user response before proceeding.

### Step A: Hook + opt-in (this message, after log confirmation)

Open with playful observation + invite user into **"减重分析模式"**:
- "连着两次往上走了，想开启减重分析模式，一起当回侦探吗？"
- "秤连续两次不太乖。要不要进入减重分析模式看看怎么回事？"

**Silently run `analyze` now** so data is ready for Step C:
```bash
python3 {weight-gain-strategy:baseDir}/scripts/analyze-weight-trend.py analyze \
  --data-dir {workspaceDir}/data \
  --plan-file {workspaceDir}/PLAN.md \
  --health-profile {workspaceDir}/health-profile.md \
  --tz-offset {tz_offset}
```

**Wait.** User says no → drop it. User says yes → Step B.

### Step B: Let user guess

Ask user to guess the cause BEFORE showing data:
- "先猜猜看，你觉得是什么原因？"
- "在我亮数据之前——你自己觉得呢？"

**Wait.** User guesses → validate in Step C. User says "不知道" → lead with data in Step C.

### Step C: Data reveal (validate → data → consequence → motivation)

Use the `analyze` result from Step A. Structure:
1. **Validate guess**: Right → "没错！数据也这么说"; Partially → "有一部分对，数据还显示…"; No guess → "我看了下数据——"
2. **Data finding**: cite actual numbers from analyze result (e.g., "14天里13天没记录饮食", "平均每日摄入比目标高250大卡")
3. **Consequence**: what this means (e.g., "等于蒙着眼减肥，吃多了自己都不知道")
4. **Motivation**: encouraging reframe

**Special cases — end flow here, skip Step D:**
- Menstrual cycle detected → "摄入正常，时间点对得上经期，大概率水分波动，过几天再看。"
- Adaptation period + no actionable cause → "还在适应期，波动正常。"

### Step D: Challenge → pact (same message as Step C, don't wait)

After motivation line, immediately tease:
- "我有个提议，敢不敢听？"
- "要不要来个一周挑战？"

**Wait.** User says yes → reveal pact:

**Pact = mutual commitment**: "我做 X" + "你做 Y"

| Detected cause | AI commits to | User commits to |
|---------------|--------------|----------------|
| Snacking / calorie surplus | 盯紧每顿饭，接近目标时提醒 | 记录每顿 + 换掉具体零食 |
| Weekend overeating | 周末饮食提醒 | 周末拍照记录 |
| Exercise decline | 周中运动提醒 | 恢复一次具体运动 |
| Late-night eating | 晚8点提醒 | 8点前吃完晚饭 |
| Logging gaps | 每日饮食提醒 | 至少记录午餐和晚餐 |
| Calorie creep | 每顿算热量反馈 | 主食稍微减量 |

### After user agrees to pact

> ⚠️ **MUST execute both script calls before replying.**

**1. Create habit:**
```bash
python3 {habit-builder:baseDir}/scripts/action-pipeline.py activate \
  --action '{"action_id":"<cause-id>","description":"<user side>","trigger":"<when>","behavior":"<tiny version>","trigger_cadence":"<every_meal|daily_fixed|weekly>"}' \
  --source weight-gain-strategy \
  [--strict] \
  --source-advice "<AI side + context>"
```
Write output to `{workspaceDir}/data/habits.active`.

**2. Save strategy:**
```bash
python3 {weight-gain-strategy:baseDir}/scripts/analyze-weight-trend.py save-strategy \
  --data-dir {workspaceDir}/data \
  --strategy-type <reduce_calories|increase_exercise|combined> \
  --params '{"duration_days":7}' \
  --tz-offset {tz_offset}
```

**3. Reply**: short cheeky confirmation — "成交！这周你可跑不掉了 😏"

User says no → drop it. Single-ask rule.

---

## Severity: `significant` (streak 4+)

> ⚠️ **MANDATORY: Follow Steps 1→2→3 exactly.**

### Step 1: Analyze & Present

1. Run `analyze` (same command as cause-check Step A)
2. Present: **安慰一句** → **趋势总结** → **诊断**（用 `diagnosis-templates.md` 的模板）
3. Transition: "要不要一起想想怎么调整？"

If `normal_fluctuation` → reassuring close, no Step 2.
**Wait.** User agrees → Step 2.

### Step 2: Discuss & Choose Strategy

Present 1-3 options from `suggested_strategies`, sorted by ease of execution for this user:

```
选项 {N}: {策略名}
{一句话描述}
预计效果: {expected_impact}
```

Strategy types:
- **A. 减少摄入** — 每日减 100-300 kcal，具体到哪顿饭怎么调
- **B. 增加运动** — 加 1-3 次运动，从用户能接受的开始
- **C. 组合** — A+B 各来一点

Ask: "哪个最不像受刑？" 尊重选择。

### Step 3: Confirm & Save

Same as cause-check "After user agrees" — create habit + save strategy + cheeky close.

---

## Standalone Command

For manual re-check (not normally needed):
```bash
python3 {weight-gain-strategy:baseDir}/scripts/analyze-weight-trend.py deviation-check \
  --data-dir {workspaceDir}/data \
  --plan-file {workspaceDir}/PLAN.md \
  --health-profile {workspaceDir}/health-profile.md \
  --user-file {workspaceDir}/USER.md \
  --tz-offset {tz_offset}
```
