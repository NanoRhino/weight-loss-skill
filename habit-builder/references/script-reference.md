# action-pipeline.py — Script Reference

All habit lifecycle decisions are handled by `{baseDir}/scripts/action-pipeline.py`.

## Subcommands

### should-mention — 是否在本次对话中提及习惯

```bash
python3 {baseDir}/scripts/action-pipeline.py should-mention \
  --habit '<habit JSON from habits.active>' \
  --meal <breakfast|lunch|dinner> \
  --days <days_since_activation> \
  --days-since-last-mention <N> \
  --reminders-since-last-mention <N> \
  [--today-matches]  # weekly habits: pass when today is the relevant day
# → {"mention": true/false, "reason": "...", "phase": "...", ...}
```

### schedule — 查询提醒频率

```bash
python3 {baseDir}/scripts/action-pipeline.py schedule \
  --cadence <every_meal|daily_fixed|daily_random|weekly|conditional> \
  --days <days_since_activation>
# → {"phase": "anchor", "value": 1, "rule": "mention every 1 day(s)"}
```

### check-graduation — 判断是否可毕业

```bash
python3 {baseDir}/scripts/action-pipeline.py check-graduation \
  --cadence <cadence> \
  --log '[{"date":"2026-04-01","result":"completed","self_initiated":false}, ...]'
# → {"eligible": true/false, "signal_1_completion": {...}, "signal_2_self_init": {...}, "stall": false}
# If Signal 1 pass but Signal 2 fail → returns action: "ask_signal_3" with prompt
```

### check-failure — 判断是否连续失败

```bash
python3 {baseDir}/scripts/action-pipeline.py check-failure \
  --log '[{"result":"missed"}, {"result":"no_response"}, {"result":"missed"}]'
# → {"failed": true, "consecutive_fail": 3, "options": ["keep_going","make_easier","try_different"]}
```

### check-concurrency — 判断是否可新增习惯

```bash
python3 {baseDir}/scripts/action-pipeline.py check-concurrency \
  --active-habits '<habits.active JSON with completion_log>'
# → {"can_add": true/false, "struggling": [...]}
```

### prioritize — 行动排序

```bash
python3 {baseDir}/scripts/action-pipeline.py prioritize \
  --actions '[{"action_id":"x", "impact":3, "ease":3, "chain":true}]'
# → sorted array with priority_score = impact × ease + chain_bonus
```

### activate — 生成 habits.active 记录

```bash
python3 {baseDir}/scripts/action-pipeline.py activate \
  --action '{"action_id":"water-after-waking", "description":"起床后喝水", "trigger":"起床后", "behavior":"喝一杯温水", "trigger_cadence":"daily_fixed"}' \
  --source-advice "多喝水少喝奶茶"
# → habits.active entry with trigger_cadence → type mapping applied
```

## Action Queue Data Structure

```json
{
  "source_advice": "多喝水少喝奶茶",
  "source_skill": "weekly-report",
  "created_at": "2026-03-30",
  "actions": [
    {
      "action_id": "water-after-waking",
      "description": "起床后喝一杯水",
      "trigger": "起床后",
      "behavior": "喝一杯温水",
      "trigger_cadence": "daily_fixed",
      "priority_score": 10,
      "status": "active",
      "activated_at": "2026-03-30"
    }
  ]
}
```

Valid `status`: `queued` → `active` → `graduated` | `paused` | `stalled` | `removed`
