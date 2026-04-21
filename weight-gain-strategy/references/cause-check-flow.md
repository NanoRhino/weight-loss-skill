# cause-check 体重分析流程

当 deviation-check 返回 `severity: "cause-check"` 时触发。

## 准备

进入流程前，**静默跑 `analyze`**，拿到数据备用，但不立即展示。

## Step A: Hook + opt-in

轻松开场，告诉用户体重在涨，问要不要一起看看原因。给用户选择权。

**等用户回复。** 说不要 → 放弃。说好 → 继续。

## Step B: 了解近况

承接 A 的"看原因"语境，先问问用户最近生活有没有变化（压力、聚餐、情绪、生理期、睡眠等），捕捉数据看不到的上下文。

- 不要用独立的寒暄开场，不要审问，不要预设立场
- **等用户回复。** 用户说了什么都行——**一句话接纳，立即进 Step C0 看数据**。不要追问细节、不要深挖原因、不要变成心理咨询。Step B 只有一轮问答。

## Step C0: 能量守恒验算

读 `analyze` 输出的 `energy_balance_check.verdict`，按下表路由：

| verdict | 行为 |
|---------|------|
| `within_noise` | 体重波动在正常范围，简短安抚，**不进入 Step C** |
| `consistent` | 进入 Step C |
| `consistent_after_adjustment` | 进入 Step C；漏记填补后热量能解释体重变化 |
| `estimate_below_expected` | 进入 Step C；热量估算低于体重变化所暗示的摄入 |
| `insufficient_data` | 进入 Step C；标注"数据不足，仅供参考" |

## Step C: 分析原因

基于 `analyze` 数据 + 用户 Step B 的回答，**诚实分析增重原因**。

**⚠️ 数据引用规则（HARD RULE）：**

| 数据 | raw（禁止直接引用） | adjusted（用这个） |
|------|-------------|------------------|
| 热量 | `calorie_stats.avg_daily_intake` | `energy_balance_check.adjusted_avg_daily_intake` |
| 蛋白质 | `protein_stats.avg_daily_g` | `energy_balance_check.adjusted_avg_daily_protein` |

- raw 只算有记录的餐，缺餐当 0，严重偏低
- adjusted = 记录的 + 缺餐按历史均值估算
- 有缺餐时用 adjusted 值并标注"含估算"

**一条原则：基于数据和科学常识说话，不确定的不说。**

**认知前提：** 体重秤的读数是事实，热量估算（包括 adjusted）是粗估。当两者矛盾时，需要综合判断——体重涨了说明实际摄入有可能超过了消耗，可能存在估算不够准，不是体重不准。

其他交给你自己判断——你有科学素养，不需要模板。

打卡不全时，先问用户确认（是真的吃得少还是没记），不要直接断言。

## Step C2: 调整建议

分析完后加一句过渡，等用户回复。用户说好 → 给建议。

- 建议针对分析出的主因，具体可执行
- 较难的拆到最简单的一个动作
- 不超过 3 个，选一个
- 打卡覆盖率很低时，可以建议先补全记录 → 用户选了则进入严格模式（见 `references/strict-mode.md`）

**等用户回复。** 用户选一个 → Step D。说"都要" → 尊重用户意愿，都执行。

## Step D: 建立习惯

**Step 1 — 建习惯：**
```bash
python3 {habit-builder:baseDir}/scripts/action-pipeline.py activate \
  --action '{
    "action_id": "<id>",
    "description": "<用户选的改变>",
    "trigger": "<触发场景>",
    "behavior": "<最小动作>",
    "trigger_cadence": "<every_meal|daily_fixed|weekly|conditional>",
    "bound_to_meal": "<breakfast|lunch|dinner|null>"
  }' \
  --source weight-gain-strategy \
  --source-advice "<context>"
```

**Step 2 — 保存策略：**
```bash
python3 {baseDir}/scripts/analyze-weight-trend.py save-strategy \
  --data-dir {workspaceDir}/data \
  --strategy-type <类型> \
  --params '{"duration_days": 7, ...}' \
  --tz-offset {tz_offset}
```

**Step 3 — 按需建 cron：**
- 餐时习惯 → 不建 cron，通过 should-mention 嵌入三餐提醒
- 非餐时习惯 → 建 cron

**Step 4 — 回复用户**，简短确认。周期固定一周（7天后复盘）。
