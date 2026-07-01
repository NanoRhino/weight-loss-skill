---
name: personal-data-query
version: 1.0.0
description: "Query personal health and diet data. Use when user asks about today's intake, daily progress, calorie summary, or 'how am I doing today'. Trigger phrases: 'how many calories today', 'what did I eat', 'today's progress', '今天吃了多少', '今天还剩多少', '今日进度', '今天怎么样了'. Do NOT trigger for logging food or recording weight — those go to diet-tracking-analysis and weight-tracking respectively."
metadata:
  openclaw:
    emoji: "bar_chart"
---

# Personal Data Query

## Role

Concise data reporter. Show the numbers, keep commentary minimal.

## Tool

```
meal_checkin({ action: "query_day", workspace_dir: "{workspaceDir}" })
```

Format result per the response schema below.

---

## Response Schema

📊 今日摄入：
🔥 XXX/TARGET kcal
███████░░░ XX%
蛋白质 Xg [status] | 碳水 Xg [status] | 脂肪 Xg [status]

🥦 蔬菜：~XXXg ✅/⬇️  🍎 水果：~XXXg ✅/⬇️

**Meals logged:**
· 餐次 — XXX kcal (食物列表简述)

**Calorie progress bar:** 10 chars, `█` filled `░` remaining. >100% → `██████████ XXX% ⚠️`

**Status:** ✅ on_track | ⬆️ high | ⬇️ low

---

## Net daily balance (append when exercise was logged today)

The intake summary above is **intake-vs-target only** — the eating target never
moves for exercise (fixed-target rule). When the user has ALSO logged a workout
today, append ONE net-balance line so the answer reflects their true deficit
*including* the workout. Owned by exercise-tracking-planning:

```
python3 {exercise-tracking-planning:baseDir}/scripts/energy-balance.py \
  --data-dir {workspaceDir}/data --date {today}
```

- `data_complete: false` (no `data/plan.json`) → omit the line (don't fabricate).
- `exercise_burn_net == 0` (no workout today) → omit (keep it clean).
- Otherwise append, localized per USER.md language:

  🏃 净热量：吃 {intake} · 运动消耗 {exercise_burn_net} · 目标 {eating_target} · 今日净{deficit/surplus}约 {|balance|} 大卡（含运动）— 目标仍是 {eating_target}

  English: *ate {intake} · burned {exercise_burn_net} · target {eating_target} ·
  net ~{|balance|} kcal {deficit/surplus} today (incl. workout) — target stays
  {eating_target}*.

The **"target stays {eating_target}"** clause is mandatory. `verdict:
"maintenance"` → "about maintenance today".
