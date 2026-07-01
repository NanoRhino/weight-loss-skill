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
- Otherwise append the **shared net-balance line template** — IDENTICAL on all
  three surfaces (the `exercise_checkin` plugin card, diet-tracking-analysis, and
  here). Build it from the resolver fields and localize per USER.md language,
  substituting the numbers:

  > ate {intake} · burned {exercise_burn_net} · target {eating_target} · net ~{abs(balance)} kcal {deficit|surplus|maintenance} today (incl. workout) — target stays {eating_target}

  Example (numbers filled): `ate 1,200 · burned 300 · target 1,404 · net ~950 kcal deficit today (incl. workout) — target stays 1,404`

- `{deficit|surplus|maintenance}` = the resolver's `verdict`.
- **Comma-group thousands** in every number (1,200 / 1,404 / 1,006) to match the
  plugin card and existing card house style ("≈1,474").
- The **"— target stays {eating_target}"** clause is MANDATORY — never imply the
  eating target moved.
- Do NOT reword or reorder this line — it must match the plugin card and
  diet-tracking-analysis byte-for-byte (translation aside).
