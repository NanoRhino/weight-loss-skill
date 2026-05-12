---
name: weight-tracking
version: 1.1.0
description: "Track body weight with full CRUD operations, unit conversion, and trend analysis. Trigger when user reports weight, asks about weight trend, wants to correct a weight entry, or change their unit preference. Trigger phrases: 'I weigh...', '体重...', '称了一下...', 'my weight is...', 'change to pounds', '改成斤', 'weight trend', '体重趋势'."
metadata:
  openclaw:
    emoji: "scales"
    homepage: https://github.com/NanoRhino/weight-loss-skill
---

# Weight Tracking

> ⚠️ **SILENT OPERATION:** Never narrate internal actions, skill transitions, or tool calls to the user. Just do it silently and respond with the result.

## Performance

**Use TOOLS.md Quick Reference first.** If `tz_offset`, `unit_preference`, and `daily_cal_target` are already in the auto-injected TOOLS.md context, use those values directly — do NOT read `timezone.json` or `health-profile.md`.

Only fall back to reading those files if Quick Reference is missing or outdated.

Do NOT read this SKILL.md again if it's already in context from a prior turn.

## Data Storage

**File:** `{workspaceDir}/data/weight.json` — JSON object keyed by ISO-8601 datetime with timezone offset. Each entry: `{ "value": 80, "unit": "kg" }`.

## Scripts

Script path: `python3 {baseDir}/scripts/weight-tracker.py`

### Save + Context — `save-and-check.py` (preferred)

**Use this for all weight saves.** Saves weight + returns recent history and plan context.

```bash
python3 {baseDir}/scripts/save-and-check.py \
  --data-dir {workspaceDir}/data \
  --value 79.5 --unit kg \
  --tz-offset 28800 \
  --plan-file {workspaceDir}/PLAN.md \
  --health-profile {workspaceDir}/health-profile.md \
  --user-file {workspaceDir}/USER.md \
  [--correct]
```

Returns:
```json
{
  "save": { "action": "created"|"updated", "key": "<datetime>", "value": 79.5, "unit": "kg" },
  "context": {
    "recent_weights": [...],
    "plan": { "target_weight": 55.0, "tdee": 1916, "calorie_target": 1800 },
    "active_strategy": { "active": false },
    "last_intervention_date": null
  }
}
```

### Save only — `weight-tracker.py save`

Use only when deviation-check is not needed (e.g., onboarding initial weight).

```bash
python3 {baseDir}/scripts/weight-tracker.py save \
  --data-dir {workspaceDir}/data \
  --value 79.5 --unit kg \
  --tz-offset 28800 \
  [--correct]
```

- Auto-detects new vs correction: if last entry ≤ 30 min ago, overwrites. Otherwise creates new.
- `--correct`: force overwrite most recent entry (when user explicitly says "that was wrong")

### Load — `load`

```bash
python3 {baseDir}/scripts/weight-tracker.py load \
  --data-dir {workspaceDir}/data \
  --display-unit kg \
  [--last 7] \
  [--from 2026-02-01 --to 2026-03-06]
```

Returns entries converted to `--display-unit`, rounded to 1 decimal.

### Other Commands

See `references/crud-operations.md` for: `delete`, `update`, `set-unit`.

## Workflow

### User Reports Weight

1. Read `timezone.json` → `tz_offset`; read `health-profile.md` → Unit Preference (parallel, first session only)
2. Call `save-and-check.py`:
   ```bash
   python3 {baseDir}/scripts/save-and-check.py \
     --data-dir {workspaceDir}/data \
     --value <N> --unit <u> --tz-offset <tz> \
     --plan-file {workspaceDir}/PLAN.md \
     --health-profile {workspaceDir}/health-profile.md \
     --user-file {workspaceDir}/USER.md
   ```
3. Read response:
   - `save.action`: `"created"` → "Logged ✓"; `"updated"` → "Updated ✓". Show value in preferred unit.
   - `context.recent_weights`: 最近体重记录
   - `context.plan`: 计划目标（TDEE、目标体重等）
   - `context.active_strategy`: 是否有进行中的干预策略
   - `context.last_intervention_date`: 上次干预日期
4. **自主判断是否需要关注体重趋势**——核心标准：**体重变化方向是否与用户目标一致。** 一致就鼓励，不一致就安抚情绪 + 把选择权交给用户。
   - **与目标一致（如目标减重，体重在降）**→ 确认 + 鼓励，给到正面情绪价值
   - **1-2 天的小波动**→ 安抚（"正常浮动，不用担心"），不追问
   - **与目标不一致且持续（连续上涨、平台期停滞、从低点回升）**→ 安抚情绪 + 提一句问用户要不要一起看看。不替用户决定"这没事"，把选择权交出去
   - **判断倾向：宁可多问一句。** 用户可以说"不用管"，但你不能帮他们忽略趋势
   - 如果 `active_strategy.active: true`（已有进行中的策略），不重复干预，但可以结合 `consensus` 提醒策略还在跑。可以主动查看最近几天的餐食记录（`{workspaceDir}/data/meals/YYYY-MM-DD.json`），结合共识给具体反馈
   - 如果 `last_intervention_date` 在 3 天内，不重复干预
   - **诊断后记录**：只有进入 cause-check 诊断流程后，调一次：
     ```bash
     python3 {baseDir}/scripts/save-and-check.py --data-dir {workspaceDir}/data --tz-offset <tz> --mark-intervention
     ```
   - **用户视角优先**：不只看科学趋势，也想想用户看到这个数字会怎么想。涨了半斤用户会慌、平台期一周不动用户会焦虑、好不容易降下来又反弹用户会沮丧——回应他们的感受，不是冷冰冰确认一个数字

### User Asks for Trend / History

1. Call `load` with appropriate filters and `--display-unit`
2. Present data (table, summary, or trend description)

### User Wants to Correct / Delete / Change Unit

See `references/crud-operations.md`.

## Interaction Guidelines

- **Record weight whenever mentioned.** Not limited to scheduled days. "今天早上74.5", "刚称了一下79" → call `save`. Exception: past/hypothetical ("我以前80公斤").
- **Never comment on weight changes unprompted.** Just log and confirm. Emotional reactions → `emotional-support` skill.
- **Always display in preferred unit**, rounded to 1 decimal.
- **Accept any common unit**: kg, lb, lbs, 斤 (=0.5 kg), 公斤.
- **Fasting tag**: if user mentions empty stomach / morning weigh-in → note `fasting: true` in context.

## References

| File | Contents |
|------|----------|
| `references/crud-operations.md` | Delete, update, set-unit commands + correction workflow |
| `references/deviation-workflow.md` | Deviation-check severity table, response guide, command |
| `references/integrations.md` | Which other skills use this skill's scripts |
