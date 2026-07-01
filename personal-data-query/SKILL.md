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
- Otherwise append the **LOCKED net-balance string** — byte-for-byte identical to
  the `exercise_checkin` plugin card and diet-tracking-analysis. Build it from the
  resolver fields; pick the string by USER.md language:

  **EN:** `ate {intake} · burned {burn} · target {target} · net ~{abs(balance)} kcal {verdict} today (incl. workout) — target stays {target}`

  **zh:** `吃了 {intake} · 运动消耗 {burn} · 目标 {target} · 今日净{赤字|盈余|维持} ~{abs} kcal（含运动）— 目标不变，仍是 {target}`

  Example (EN, numbers filled): `ate 1,200 · burned 300 · target 1,404 · net ~950 kcal deficit today (incl. workout) — target stays 1,404`

- Field map: `{intake}`=intake, `{burn}`=exercise_burn_net, `{target}`=eating_target,
  `{abs(balance)}`/`{abs}`=abs(balance), `{verdict}`=resolver's `verdict`
  (`deficit`|`surplus`|`maintenance`; zh map: deficit→赤字, surplus→盈余,
  maintenance→维持).
- **Comma-group thousands** in the kcal numbers only (1,200 / 1,404 / 1,006) — NOT
  durations. Matches the plugin card + card house style ("≈1,474").
- Do NOT reword, reorder, or drop the "— target stays"/"目标不变，仍是" clause. Must
  match the plugin card + diet-tracking-analysis byte-for-byte.
