# cause-check 体重分析流程

当 deviation-check 返回 `severity: "cause-check"` 时触发。

## 准备

进入流程前，**静默跑 `analyze`**，拿到数据备用，但不立即展示。

## Step A: Hook + opt-in

轻松开场，告诉用户体重在涨，问要不要一起看看原因。给用户选择权。

示例：
- "唔，连着两次往上走了。想一起看看是怎么回事吗？🔍"
- "秤又调皮了，要不要进入分析模式看看？"

**等用户回复。** 说不要 → 放弃。说好 → 继续。

## Step B: 让用户先猜

不急着亮数据。先问用户自己觉得是什么原因。这能捕捉数据看不到的上下文（压力、聚餐、情绪）。

示例：
- "在我亮底牌之前——你自己觉得是什么原因？"
- "你先猜猜，然后我们对答案"

**等用户回复。**

## Step C: AI 分析原因

基于 `analyze` 数据 + 用户在 Step B 的回答，**AI 自行判断增重原因**。

**要求：**
- 用数据说话（引用具体数字）
- 结合用户上下文（如果 Step B 提到了压力/聚餐等，纳入分析）
- 直接、具体、不绕弯
- 如果用户 Step B 猜对了，先肯定再补充
- 如果猜错了，温和纠正

**不限定分析方向。** AI 根据实际数据判断，可能是热量、蛋白质、食物质量、运动、打卡不全、水肿、节食反弹、或任何组合。

## Step C2: 给 3 个可选改变

紧接 Step C，给用户 3 个具体的、可执行的改变，让用户选一个。

**格式：**
```
1️⃣ xxx — 一句话说明
2️⃣ xxx — 一句话说明
3️⃣ xxx — 一句话说明

你觉得哪个最想试试？选个数字就行～
```

**要求：**
- AI 根据分析结果自行生成，不用固定模板
- 每个改变要**具体可执行**（"每餐加个鸡蛋"不是"多吃蛋白质"）
- 难度递增（1 最简单，3 稍难）
- 不要和已有提醒重复（三餐提醒已有，不需要再建打卡提醒）

**特殊情况 — 打卡不全：**
如果 `analyze` 数据显示打卡覆盖率低（coverage_pct < 50% 或大量单餐日），"打卡不全"本身就是一个原因——数据不够无法准确分析。这种情况：
- 可以把"先把每餐都记下来"作为 3 个选项之一
- 如果用户选了这个 → 进入**严格模式**（`--strict` 参数），已有三餐提醒变严格，不建新 cron
- 严格模式详见 `references/strict-mode.md`

**等用户回复。** 用户选一个 → Step D。说"都要" → 选最简单的那个，"一个一个来"。

## Step D: 建立习惯

用户选了之后，执行以下步骤：

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

输出写入 `habits.active`。

**Step 2 — 保存策略：**
```bash
python3 {baseDir}/scripts/analyze-weight-trend.py save-strategy \
  --data-dir {workspaceDir}/data \
  --strategy-type <类型> \
  --params '{"duration_days": 7, ...}' \
  --tz-offset {tz_offset}
```

**Step 3 — 按需建 cron：**
- 餐时习惯（蛋白质、食物替换等）→ 不建 cron，通过 should-mention 嵌入三餐提醒
- 非餐时习惯（零食、晚间、周末、运动日）→ 建 cron

**Step 4 — 回复用户**，简短确认。
