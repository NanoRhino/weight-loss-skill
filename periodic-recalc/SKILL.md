# periodic-recalc

## Overview

**Type:** Cron-triggered background task  
**Trigger:** Every 4 weeks on Sunday (after weekly-report)  
**Owner:** periodic-recalc skill  
**Dependencies:** weight-loss-planner, weight-tracking

Recalculates the user's daily calorie target based on their current weight every 4 weeks. Updates PLAN.md with new TDEE, calorie target, and macro ranges. Reviews whether their actual eating pattern matches their current diet_mode and suggests mode changes if needed.

## Trigger Conditions

1. **Primary trigger:** Cron job (every 4 weeks Sunday, after weekly-report completes)
2. **Secondary trigger:** When weight-tracking logs a new weight AND `pending-recalc.json` exists with `reason="awaiting_weight"`

## When Cron Fires

Run `scripts/periodic-recalc.py` with:
- `--workspace` → user workspace path
- `--planner-calc` → path to `weight-loss-planner/scripts/planner-calc.py`

Based on the JSON output `action` field:

### `action: "skipped"`

Less than 25 days since last recalculation. Do nothing — silently exit.

### `action: "recalculated"`

The plan has been updated. Compose a "周期复盘 + 开启新周期" message for the user.

**Message structure:**
1. 🎉 **高调庆祝**上一减脂周期完成——这是用户坚持了4周的成果，要给足仪式感和成就感。回顾这4周的体重变化，让用户感受到"我做到了"
2. 明确的**周期切换分割线**——让用户清晰感受到"上一页翻篇了，新的一页开始了"。可以用 emoji 分隔、换个语气、或者直接说"接下来是新周期的安排"
3. 解释新周期为什么这样调——**语气温和、有人情味**，不要像念教科书。不说"根据热量守恒定律"，而是用用户能感受到的方式表达（"你现在比4周前轻了，身体需要的也少了一点"）。参考数据：
   - `weight_change`：掉了多少？快还是慢？
   - `old_calories` vs `new_calories`：热量升了还是降了？
   - `rate_kg_per_week` 变化
   - 过去4周打卡情况（读 `data/meals/` 最近28天，统计实际平均摄入 vs 旧目标）
   - 进度不及预期时：温和指出可能是记录有遗漏、分量比想象中多，建议下个周期注意（不要指责、不要说"你吃多了"）
4. 列出新周期具体数字：每日热量目标、预计减脂速度（kg/周）、4周预期减重
5. 宏量素范围（蛋白质/碳水/脂肪 g）——所有数值保留到个位数，不要小数
6. 问用户是否同意新计划："如果没问题我就按这个来了，有想调的随时说~"

**数值精度：** 热量和三大营养素都保留到个位数（如 1359 kcal、蛋白质 70-93g），不要出现小数。

**确认机制：** 消息末尾需要和用户确认新计划。用户不回复 = 默认同意，正常按新计划执行。用户回复有异议 → 根据用户诉求调整后重新更新 PLAN.md。

**核心原则：**
- 相信热量守恒，不盲信打卡数据。进度不对 = 实际摄入有偏差，但表达要有人情味
- 前周期总结和新周期安排要有明确区分，让用户感觉到翻篇进入新阶段
- 像朋友聊天，不像发通知。少用"因此""所以""根据"，多用口语化表达

**Tone:** 像一个懂你的私人教练在跟你聊阶段复盘——开心的事大声说，需要改进的地方轻轻提，整体让人有动力继续。

After composing the message, run `scripts/diet-mode-review.py` with `--workspace` and `--days 28`.

Based on the output:
- **`action: "recommend_change"`** → Ask the user if they'd like to switch to the recommended diet mode. Present the actual macro ratios vs current mode's expected ranges. Frame as: "Your eating pattern has naturally evolved to match [mode] better — would you like to update your plan?"
- **`action: "no_change"`** → Silently continue (don't mention it)
- **`action: "insufficient_data"`** → Silently continue

### `action: "awaiting_weight"`

Output to the user:
"It's time for your 4-week plan recalculation! Please weigh yourself when you can, and I'll update your plan once you log your weight."

Write `pending-recalc.json` with:
```json
{
  "created_at": "<ISO timestamp>",
  "reason": "awaiting_weight",
  "cycle_date": "<today's date>"
}
```

### `action: "on_leave"`

Write `pending-recalc.json` with:
```json
{
  "created_at": "<ISO timestamp>",
  "reason": "on_leave",
  "cycle_date": "<today's date>"
}
```

Do NOT notify the user. The recalc will trigger on the first Sunday after leave ends (notification-manager will reschedule).

## When Weight is Logged (Secondary Trigger)

After weight-tracking logs a new weight, run `scripts/check-pending-recalc.py` with `--workspace`.

If output is `{"should_trigger": true}`:
- Run the full recalc flow as if the cron had fired
- Delete `pending-recalc.json` after successful completion

## Data Dependencies

| File/Script | Access | Purpose |
|-------------|--------|---------|
| `data/weight.json` | Read | Get most recent weight entry |
| `data/leave.json` | Read | Check if user is on leave |
| `data/pending-recalc.json` | Read/Write/Delete | Track deferred recalcs |
| `PLAN.md` | Read/Write | Update calorie target, TDEE, macros |
| `health-profile.md` | Read | Get activity level, diet_mode, user demographics |
| `data/meals/*.json` | Read | Analyze actual eating patterns (diet-mode-review) |
| `weight-loss-planner/scripts/planner-calc.py` | Execute | Recalculate TDEE/calories/macros |

## Important Notes

- **Always recalculate** — no threshold check. Each 4-week cycle is a new phase regardless of weight change magnitude.
- **Macro calculation** must match onboarding formulas:
  - Protein: 1.2-1.6 g/kg × current_weight
  - Fat: diet_mode percentage × daily_calories
  - Carbs: remainder
- If `floor_clamped: true` in planner-calc output, the weekly rate was reduced because daily_cal hit the BMR floor. Update `Weekly Rate` in PLAN.md accordingly.
- Delete `pending-recalc.json` after successful recalc (whether triggered by cron or by weight logging).

## Examples

### Example 1: Normal recalc

Input: User is at 58.5 kg (down from 60 kg)  
Output: "Congratulations! You've lost 1.5 kg in 4 weeks! 🎉 Your new plan is ready: 1,260 kcal/day (down from 1,290). Your TDEE dropped from 1,772 to 1,740 kcal."

### Example 2: Diet mode mismatch

After recalc, diet-mode-review detects: user is in `balanced` mode but eating 38% protein / 30% carbs / 32% fat.  
Output: "I noticed your eating pattern has naturally shifted toward higher protein (38% vs the 25-35% balanced range). Would you like to switch to `high_protein` mode? It better matches what you're already doing."

### Example 3: Awaiting weight

User hasn't logged weight in 3 weeks. Cron fires.  
Output: "It's time for your 4-week plan recalculation! Please weigh yourself when you can, and I'll update your plan once you log your weight."  
(pending-recalc.json is written)

Two days later, user logs weight → check-pending-recalc detects flag → full recalc runs → pending-recalc.json is deleted.
