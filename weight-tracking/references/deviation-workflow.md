# 体重趋势判断 — 模型自主决策

`save-and-check.py` 返回体重历史和上下文，模型自主判断是否需要干预。

## 返回字段

- `save`: 保存结果
- `context.recent_weights`: 最近 10 条体重记录
- `context.plan`: 计划信息（TDEE、目标体重、热量目标）
- `context.active_strategy`: 是否有进行中的干预策略
- `context.last_intervention_date`: 上次干预日期

## 判断指南

核心标准：**体重变化是否与用户目标方向一致，且偏离大概率是真实趋势而非日常波动。**

体重每天自然波动 ±0.5-1kg（水分、钠、排便）。需要多天数据才能区分趋势和噪音。

- **与目标一致**（如减重目标，体重在降）→ 鼓励
- **日常噪音**（1-2 天小幅波动，在正常范围内）→ 正常确认，不追问
- **大概率真实偏离**（连续多天反方向、从低点明显回升超出波动范围、长期停滞）→ 安抚情绪 + 提一句问要不要看看原因。用户说好 → 读 `weight-gain-strategy/references/cause-check-flow.md`
- `active_strategy.active: true` → 不重复干预
- `last_intervention_date` 在 3 天内 → 不重复干预
- **只在 80% 以上信心认为偏离是真实的时候才提。不必要的询问也是打扰。**
