---
name: reward-engine
version: 1.0.0
description: >
  Calculates cumulative calorie-target achievement days and badge level.
  Called BY other skills (diet-tracking-analysis) after meal check-in — not a standalone skill.
  
  WHEN to call:
  - diet-tracking-analysis: after meal_checkin returns successfully (action: create/append).
    Run badge-calc.py check. If level_up is true, append badge celebration + image to reply.
  - diet-tracking-analysis: after 补录 (back-fill past date), run with --date flag.
  - notification-composer: at morning reminder, check pending_delivery for fallback delivery.

  WHEN NOT to call:
  - During corrections or deletions (action: correct/delete)
  - During recall stages (Stage 2/3/4)
  - If meal_checkin failed or returned an error

  DELIVERY: Badge image sent via wechat API (upload to OSS → URL → SendMessageToAccount).
  This skill never sends messages directly — only provides data + generates images.

  Returns: JSON with qualified_today, current_count, current_level, level_up, badge info.
metadata:
  openclaw:
    emoji: "trophy"
    homepage: https://github.com/NanoRhino/weight-loss-skill
---

# Reward Engine — Calorie Target Badge

> ⚠️ **SILENT OPERATION:** Never narrate internal actions or tool calls.

## Philosophy

1. **Celebrate accumulation, never punish gaps.** Count goes up only — never down.
2. **Reward the behavior (eating on target), not the outcome (weight loss).**
3. **One celebration per level-up, then move on.** Don't revisit past badges.
4. **Personalize the image.** User name + their data on the badge.

## Qualification Rules

A day counts as "qualified" when ALL THREE conditions are met:

1. **Complete meals logged:** Number of main meals (breakfast/lunch/dinner) logged today ≥ expected meal count
   - Default: 3 meals
   - Intermittent fasting (16:8 or explicit "两餐" in PLAN.md): 2 meals
   - `snack` does NOT count as a main meal
2. **Calories in target range:** Total daily calories within the `Daily Calorie Range` from PLAN.md (e.g., 1,430 - 1,630)
   - Falls back to target ± 10% if only a single target value exists
3. **Above safety floor:** Total daily calories ≥ BMR × 0.8
   - Prevents rewarding dangerous under-eating

## Script

```bash
python3 {baseDir}/scripts/badge-calc.py check \
  --workspace-dir {workspaceDir} \
  --tz-offset {tz_offset}
```

### Output

```json
{
  "qualified_today": true,
  "already_counted": false,
  "current_count": 14,
  "current_level": 3,
  "level_up": true,
  "new_badge": {
    "level": 3,
    "name": "⭐⭐⭐ 自由支配者",
    "message": "两周的精准分配。你不是在\"控制饮食\"，你是真的会吃了。",
    "milk_tea_cups": 28,
    "progress_bar": "━━━━━━━━━━░░░░ 14/21 → 下一级：稳定输出选手"
  },
  "badge_image": "{workspaceDir}/data/badges/badge_level_3.png"
}
```

- `qualified_today`: whether today meets all 3 conditions
- `already_counted`: true if today was already counted (prevents double-counting)
- `level_up`: true only when a NEW level is reached this check
- `new_badge`: null if no level-up
- `badge_image`: path to generated badge image (null if no level-up)

## Level Definitions

| Level | Days | Name | Message |
|-------|------|------|---------|
| 1 | 3 | ⭐ 稳稳吃饭的人 | 有3天热量刚好落在目标区间。这不是运气——是你对"一顿饭多少热量"有感觉了。 |
| 2 | 7 | ⭐⭐ 热量掌控达人 | 7天达标。你已经知道什么时候该多吃、什么时候该收着。这种判断力比任何食谱都管用。 |
| 3 | 14 | ⭐⭐⭐ 自由支配者 | 两周的精准分配。你不是在"控制饮食"，你是真的会吃了。 |
| 4 | 21 | ⭐⭐⭐⭐ 稳定输出选手 | 三周的节奏，已经不是"在坚持"了，是你的正常状态。 |
| 5 | 30 | ⭐⭐⭐⭐⭐ 精准生活家 | 一个月。你对热量的直觉已经内化了——不看数字也不会差太远。 |
| 6 | 45 | ⭐×6 持续进化者 | 45天。一个半月的稳定输出，这不是阶段性的表现，是你的新常态。 |
| 7 | 60 | ⭐×7 长期主义玩家 | 60天。不需要鸡汤，数据说明一切。 |
| 8 | 90 | ⭐×8 不可撼动 | 90天。多数人的计划活不过两周，你走完了全程。这不是关于减肥了，这是你证明了自己能长期做好一件事。 |

## Milk Tea Conversion

```
milk_tea_cups = (daily_deficit × current_count) ÷ 500
```

- `daily_deficit` from PLAN.md (`Daily Calorie Deficit` field)
- If not found, default to 300 kcal
- 500 kcal = one standard full-sugar milk tea

## Badge Image Generation

When `level_up == true`, generate a personalized badge image using ImageMagick overlay.

### Base Template
- **File:** `{baseDir}/assets/badge-base-level{N}.png` (480×480 RGBA PNG)
- **Fallback:** use `badge-base-level1.png` if level-specific template doesn't exist

### Dynamic Text (LLM-generated)

The text content is NOT hardcoded. The LLM composes it based on the user's actual data:

| Position | Field | Description |
|----------|-------|-------------|
| 绿圈右侧 line1a | `line1a` | 数据概要第一行，如 "过去7天中有5天" |
| 绿圈右侧 line1b | `line1b` | 数据概要第二行，如 "热量处于合理范围" |
| 💛右侧 line2 | `line2` | 鼓励语，如 "没有极端节食，认真照顾了自己" |
| 左下 | `username` | 用户昵称 |
| 左下副标题 | `username_sub` | 用户英文名/ID（可选） |
| 右下 | `date` | 获得日期，格式 YYYY.MM.DD |

**LLM 生成规则：**
- `line1a` + `line1b`：基于 `current_count`、达标天数、时间跨度，用简洁数据描述
- `line2`：基于用户的实际表现写一句个性化鼓励，温暖但不夸张
- 语气参考：「认真照顾了自己」「热量稳稳的」「没有极端节食」

### Generation Script

```bash
bash {baseDir}/scripts/generate-badge-img.sh \
  --base {baseDir}/assets/badge-base-level1.png \
  --output {workspaceDir}/data/badges/badge_level_{N}.png \
  --line1a "{line1a}" \
  --line1b "{line1b}" \
  --line2 "{line2}" \
  --username "{username}" \
  --username-sub "{username_sub}" \
  --date "{date}"
```

### Output
- Saved to `{workspaceDir}/data/badges/badge_level_{N}.png`
- Format: PNG 480×480

## Data Storage

File: `{workspaceDir}/data/badges.json`

```json
{
  "calorie_target": {
    "current_level": 3,
    "current_count": 14,
    "next_level_target": 21,
    "qualified_dates": ["2026-05-01", "2026-05-03", "2026-05-04"],
    "unlocked_at": {
      "1": "2026-04-15",
      "2": "2026-04-28",
      "3": "2026-05-10"
    },
    "daily_deficit": 385,
    "last_calculated": "2026-05-19"
  }
}
```

## Integration Point

Called by `diet-tracking-analysis` after `meal_checkin` returns with `action: "create"` or `action: "append"`:

### Triple-Trigger Guarantee

**Trigger 1 — Primary (最后一餐):**
After every successful meal_checkin (create/append), run badge-calc.py check.
badge-calc.py itself checks if meals_logged >= expected_meals internally.
If the user hasn't logged all meals yet, `qualified_today` will be false — that's fine, it's a no-op.

**Trigger 2 — Back-fill (补录):**
When user logs a past meal (补录 date ≠ today), also run badge-calc.py with `--date {past_date}`.
This ensures a day that was missed at real-time can still qualify retroactively.

**Trigger 3 — Fallback (兜底 via notification-composer):**
When the morning reminder fires (next day), check `badges.json` → `pending_delivery`:
- If `pending_delivery` exists AND `delivered == false`:
  → Deliver the badge image + celebration text
  → Mark `delivered = true` in badges.json
- This catches cases where Trigger 1 or 2 succeeded in qualification/level-up
  but failed to deliver the image (e.g., no public URL at that moment).

### Execution Flow

```
# After composing the normal meal reply (①②③):
1. Run badge-calc.py check [--date {date} if 补录]
2. If level_up == true:
   a. LLM generates badge text fields (line1a, line1b, line2) based on:
      - new_badge.name, new_badge.message
      - current_count, qualified_dates history
      - user's recent eating patterns
   b. Run generate-badge-img.sh with generated text
   c. Append badge celebration text after normal reply
   d. Send badge image (upload to OSS → get URL → wechat API)
   e. Mark pending_delivery.delivered = true in badges.json
3. If delivery fails (no public URL, API error, etc.):
   → Leave pending_delivery.delivered = false
   → Trigger 3 will retry next morning
4. If qualified_today == true but no level_up:
   → Say nothing (silent accumulation)
5. If qualified_today == false:
   → Say nothing about badges
```
