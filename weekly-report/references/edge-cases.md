# Edge Cases

## First week (< 7 days of data)
Generate partial report. Prefix with:
`"这是你的第一份周报，数据越多越有参考价值！"`

## Week with zero data
Don't generate full report. Send short message:
`"这周没有数据，准备重新开始？💪"`

## No PLAN.md (no calorie/macro targets)
Skip calorie and macro sections. Show logging overview and weight only.
Add note: `"创建减脂计划后，周报会加入热量和营养素分析。"`

## Health flags (ED-related)
If `USER.md > Health Flags` contains `avoid_weight_focus` or `history_of_ed`:
- Skip weight section entirely
- Calorie section: focus on consistency of eating, not numbers
- Achievements: focus on variety and balance, not restriction
- Omit progress bar and weight fields in chat message
- `data_hook` focuses on consistency, variety, energy — never weight

## next_week_focus tracking

### Writing
After composing suggestions, write the focus action to
`logs.weekly_report.{start_date}` as `next_week_focus` (plain text string).

### Reading
Before composing, read `logs.weekly_report.{previous_start_date}` and check `next_week_focus`.

| Outcome | Action |
|---------|--------|
| Acted on it | Add to highlights: `"上周说要{focus_summary}——做到了。"` |
| Did not act on it | Carry forward as first suggestion, no guilt |
| Unclear | Skip — do not mention |
