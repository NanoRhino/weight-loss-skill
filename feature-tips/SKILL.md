---
name: feature-tips
version: 1.0.0
description: "Cron-only. Daily feature introduction from Day 3 after onboarding. Skips already-used features. Self-destructs when done."
metadata:
  openclaw:
    emoji: "bulb"
    homepage: https://github.com/NanoRhino/weight-loss-skill
---

# Feature Tips

> **Cron-only skill.** Not user-triggered.

## Trigger

Daily 21:00 cron. Start: `Onboarding Completed` + 3 days.

## Workflow

1. **Precondition** — `health-profile.md > Automation > Feature Tips Completed` has date → `NO_REPLY`.

2. **Conflict** — yields to other 21:00 tasks:
   - Sunday → `NO_REPLY` (weekly report)
   - `Pattern Detection Completed` is `—` → `NO_REPLY` (diet-pattern-detection)

3. **Engagement** — run `check-stage.py`. Stage ≥ 2 → `NO_REPLY`.
   ```bash
   python3 {notification-manager:baseDir}/scripts/check-stage.py \
     --workspace-dir {workspaceDir} --tz-offset {tz_offset}
   ```

4. **Detect used features**:
   ```bash
   python3 {baseDir}/scripts/check-feature-usage.py \
     --workspace-dir {workspaceDir}
   ```
   Supplement script result with:
   - Cron list has `[custom]` job → `custom_reminders` used
   - `memory/medium-term.md` matches keywords in `references/tips-content.md § Memory Keywords` → mark corresponding feature used

5. **Pick next tip** — first in Feature Queue not in `used_features` or `sent_tips`. None left → step 7.

6. **Send** — compose per `references/tips-content.md`, then mark sent:
   ```bash
   python3 {baseDir}/scripts/check-feature-usage.py \
     --workspace-dir {workspaceDir} --mark-sent <feature_id>
   ```

7. **Self-destruct** — `cron list` → find "Feature tips" → `cron remove` → write `Feature Tips Completed: <YYYY-MM-DD>` to `health-profile.md > Automation`.

## Feature Queue

| # | ID | Name |
|---|---|------|
| 1 | `packaged_food` | 解读包装食品 |
| 2 | `restaurant_recommendation` | 点餐推荐 |
| 3 | `exercise_tracking` | 记录运动 |
| 4 | `custom_reminders` | 设置提醒 |
| 5 | `emotional_support` | 情绪倾诉 & 支持 |
| 6 | `nutrition_knowledge` | 饮食/营养知识 |

## Message Style

- Friend tone, not product tutorial
- Include concrete usage example
- End with actionable invitation
- Vary wording each time per `references/tips-content.md`
