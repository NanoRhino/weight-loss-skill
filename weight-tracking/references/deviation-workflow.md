# 体重趋势判断 — 模型自主决策

`save-and-check.py` 返回体重历史和上下文，模型自主判断是否需要干预。

## 返回字段

- `save`: 保存结果
- `context.recent_weights`: 最近 10 条体重记录
- `context.plan`: 计划信息（TDEE、目标体重、热量目标）
- `context.active_strategy`: 是否有进行中的干预策略
- `context.last_intervention_date`: 上次干预日期

## 判断指南

- **不干预**：体重稳定/下降/小幅波动
- **轻微安抚**：小幅上涨但不持续（1-2 次），简短安慰不追问
- **进入诊断**：明显持续上涨趋势 → 读 `weight-gain-strategy/references/cause-check-flow.md`
- `active_strategy.active: true` → 不重复干预
- `last_intervention_date` 在 3 天内 → 不重复干预
