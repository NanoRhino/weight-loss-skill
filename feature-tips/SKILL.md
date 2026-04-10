---
name: feature-tips
version: 1.0.0
description: "Scheduled feature introduction for new users. Runs daily from Day 3 after onboarding, introducing one unused feature per day. Monitors feature usage and skips already-discovered features. Self-destructs after all features are introduced or used. Cron-only — NOT user-triggered."
metadata:
  openclaw:
    emoji: "bulb"
    homepage: https://github.com/NanoRhino/weight-loss-skill
---

# Feature Tips

> **Cron-only skill.** Never triggered by user messages. Activated by a daily cron job created by `notification-manager` at onboarding completion.

## Trigger

Daily cron job. Start date: `Onboarding Completed` + 3 days (from `health-profile.md > Automation`). Cron time: 21:00 (user local time) — same slot as weekly report and diet pattern detection.

**Conflict rule:** Other 21:00 tasks take priority. Before sending a feature tip, check if another task already ran in this session:
- **Sunday** → weekly report fires at 21:00 → feature tips yields, output `NO_REPLY`.
- **Diet pattern detection not yet completed** (i.e., `health-profile.md > Automation > Pattern Detection Completed` is `—`) → diet pattern detection fires at 21:00 → feature tips yields, output `NO_REPLY`.
- **Neither of the above** → feature tips proceeds normally.

## Workflow

1. **Check precondition** — read `health-profile.md > Automation > Feature Tips Completed`. If already has a date → output nothing (`NO_REPLY`), skip.

2. **Check conflict** — determine if another 21:00 task takes priority today:
   - If today is **Sunday** → output `NO_REPLY` (weekly report has priority).
   - If `health-profile.md > Automation > Pattern Detection Completed` is `—` → output `NO_REPLY` (diet pattern detection has priority).
   - Otherwise → continue.

3. **Check engagement stage** — run:
   ```bash
   python3 {notification-manager:baseDir}/scripts/check-stage.py \
     --workspace-dir {workspaceDir} --tz-offset {tz_offset}
   ```
   Read `data/engagement.json > notification_stage`. If stage ≥ 2 → output nothing (`NO_REPLY`). Feature tips only send during active engagement.

4. **Detect used features** — run:
   ```bash
   python3 {baseDir}/scripts/check-feature-usage.py \
     --workspace-dir {workspaceDir}
   ```
   Returns JSON:
   ```json
   {
     "used_features": ["exercise_tracking", ...],
     "sent_tips": ["packaged_food", ...],
     "next_tip": "restaurant_recommendation" | null
   }
   ```

5. **Supplement detection with cron check** — list current cron jobs (`cron list`). If any job name starts with `[custom]` → the user has already used the custom reminder feature. If `custom_reminders` is not already in `used_features`, add it mentally for this run.

6. **Supplement detection with memory check** — read `memory/medium-term.md` (if exists):
   - Keywords "包装食品", "营养成分表", "配料表", "nutrition label", "packaged" found in context of user querying → treat `packaged_food` as used.
   - Keywords indicating the AI provided emotional support (e.g., user expressed "焦虑", "难过", "自责", "压力大", "body image" and got support) → treat `emotional_support` as used.
   - Keywords indicating user asked about nutrition/health knowledge (e.g., "蛋白质怎么补", "碳水是什么", "什么是 TDEE", "how much protein") → treat `nutrition_knowledge` as used.

7. **Determine next tip** — from the Feature Queue below, find the first feature that is:
   - NOT in `used_features` (user hasn't discovered it on their own)
   - NOT in `sent_tips` (haven't introduced it yet)
   - NOT detected as used in steps 5-6

   If no tip remains → go to step 9 (self-destruct).

8. **Send tip** — compose a message using the template from `references/tips-content.md` for the selected feature. Then mark it as sent:
   ```bash
   python3 {baseDir}/scripts/check-feature-usage.py \
     --workspace-dir {workspaceDir} \
     --mark-sent <feature_id>
   ```

9. **Self-destruct** (when no tips remain):
   1. List current agent's cron jobs (`cron list`)
   2. Find job with name containing "Feature tips" or "feature-tips"
   3. Delete it (`cron remove`)
   4. Write completion date to `health-profile.md > Automation > Feature Tips Completed: <YYYY-MM-DD>`

## Feature Queue (ordered)

| # | Feature ID | Name |
|---|-----------|------|
| 1 | `packaged_food` | 解读包装食品 |
| 2 | `restaurant_recommendation` | 点餐推荐（拍餐单 / 食堂菜品推荐） |
| 3 | `exercise_tracking` | 记录运动 |
| 4 | `custom_reminders` | 设置提醒（喝水、休息、吃水果等） |
| 5 | `emotional_support` | 情绪倾诉 & 支持 |
| 6 | `nutrition_knowledge` | 饮食 / 营养知识 |

## Feature Usage Detection (automated by script)

| Feature ID | Detection Signal |
|-----------|-----------------|
| `packaged_food` | Memory keywords (see step 5) |
| `restaurant_recommendation` | `data/nearby-restaurants.json` exists AND `restaurants` array is non-empty |
| `exercise_tracking` | `data/exercise.json` exists AND has ≥ 1 date entry |
| `custom_reminders` | Cron list contains any `[custom]` job (see step 4) |
| `emotional_support` | Memory keywords (see step 5) |
| `nutrition_knowledge` | Memory keywords (see step 5) |

## Message Style

- Casual, friend tone — like sharing a cool trick, not a product tutorial
- Include a concrete example showing the actual usage effect
- End with an actionable invitation for the user to try
- Keep it short — conversational, not a feature spec
- Do NOT use bullet lists or markdown headers — just natural text
- Follow the templates in `references/tips-content.md` but vary wording each time
- Respect `USER.md > Language` for reply language (do NOT add language selection logic)

## Workspace

### Reads

| Source | Purpose |
|--------|---------|
| `health-profile.md > Automation` | Check preconditions |
| `data/feature-tips.json` | Track sent / used features |
| `data/engagement.json` | Check engagement stage |
| `data/exercise.json` | Detect exercise feature usage |
| `data/nearby-restaurants.json` | Detect restaurant feature usage |
| `memory/medium-term.md` | Detect other feature usage via keywords |

### Writes

| Path | How | When |
|------|-----|------|
| `data/feature-tips.json` | Via `check-feature-usage.py --mark-sent` | After sending each tip |
| `health-profile.md > Automation > Feature Tips Completed` | Direct write | Self-destruct |
