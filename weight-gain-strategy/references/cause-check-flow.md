# cause-check 体重分析流程

当 deviation-check 返回 `severity: "cause-check"` 时触发。

## 流程

1. **跑 `analyze`**（静默，不告诉用户）
2. **告诉用户增重原因** — 基于 analyze 数据 + 用户最近的饮食/运动/生活习惯，用人话说清楚为什么涨了。直接、具体、有数据支撑。
3. **给 3 个可选的改变** — 每个改变是一个具体、可执行的小动作。用户选一个。
4. **用户选了之后** → 建习惯（`action-pipeline.py activate`）+ 保存策略（`save-strategy`）

## 原因分析

AI 根据 `analyze` 输出的原始数据自行判断。常见方向：
- 热量超标 / 热量波动大
- 蛋白质不足
- 食物质量差（高钠、高油、加工食品多）
- 运动减少
- 打卡不全（数据不够无法判断）
- 水肿（突然跳涨 + 高钠饮食）
- 吃得太少反弹

不限于以上，AI 根据实际数据判断。

## 3 个可选改变

**格式示例：**
```
我看了你最近两周的数据，涨的主要原因是 xxx。

给你三个选择，挑一个这周试试：

1️⃣ xxx — 一句话说明
2️⃣ xxx — 一句话说明  
3️⃣ xxx — 一句话说明

选哪个？
```

**规则：**
- 3 个改变按影响力排序
- 每个改变要具体（"每餐加个鸡蛋"而不是"多吃蛋白质"）
- 难度递增（1最简单，3稍难）
- 不要重复已有的提醒（三餐提醒已有，不要再建）

## 用户选了之后

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
  --source-advice "<AI 承诺做什么>"
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

**Step 3 — 如果需要非餐时提醒才建 cron：**
- 餐时习惯（蛋白质、食物替换）→ 不建 cron，通过 should-mention 嵌入三餐提醒
- 非餐时习惯（零食 15:00、晚间 20:00、周末、运动日）→ 建 cron

**Step 4 — 回复用户**，简短确认。
