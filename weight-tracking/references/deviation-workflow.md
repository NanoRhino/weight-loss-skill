# 体重趋势判断 — 模型自主决策

`save-and-check.py` 返回体重历史和上下文，模型自主判断是否需要干预。

## 返回字段

- `save`: 保存结果
- `context.recent_weights`: 最近 10 条体重记录
- `context.plan`: 计划信息（TDEE、目标体重、热量目标）
- `context.active_strategy`: 是否有进行中的干预策略
- `context.last_intervention_date`: 上次干预日期

## 判断指南

核心标准：**体重变化方向是否与用户目标一致。**

- **与目标一致**（如减重目标，体重在降）→ 鼓励
- **1-2 天小波动** → 安抚，不追问
- **与目标不一致且持续**（连续上涨、平台期停滞、从低点回升）→ 安抚情绪 + 提一句问要不要看看原因。用户说好 → 读 `weight-gain-strategy/references/cause-check-flow.md`
- `active_strategy.active: true` → 不重复干预
- `last_intervention_date` 在 3 天内 → 不重复干预
- **判断倾向：宁可多问一句。** 用户可以说"不用管"，但你不能帮他们忽略趋势。
