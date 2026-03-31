# Deviation Check — Severity Response Guide

After every weight save, call `deviation-check`. The script handles all skip logic internally (missing PLAN.md, health flags). Just pass the file paths.

## Severity → Response

| Severity | Streak | Agent Behavior |
|----------|--------|----------------|
| `none` | 0 | Weight stable or down — just confirm the log. |
| `comfort` | 1 | Append a warm one-liner after log confirmation. See `weight-gain-strategy` SKILL.md `references/diagnosis-templates.md` for examples. |
| `cause-check` | 2–3 | Start multi-turn guided discovery flow. See `weight-gain-strategy` SKILL.md `references/cause-check-flow.md`. |
| `significant` | 4+ | Run full analysis and present causes. See `weight-gain-strategy` SKILL.md `references/interactive-flow.md`. |

## Result Fields

- `triggered: false` → no action, just confirm the log
- `triggered: false` + `reason: "no_plan"` → no PLAN.md, skip silently
- `triggered: false` + `reason: "health_flag"` → user has avoid_weight_focus/history_of_ed, skip silently
- `triggered: false` + `reason: "insufficient_data"` → < 2 readings, skip silently
- `triggered: true` → respond per severity table above
- `temporary_causes` → if present, mention lightly (e.g. water retention, menstrual cycle)
- `adaptation_period: true` → first 2 weeks of plan, be extra gentle

## Command

```bash
python3 {weight-gain-strategy:baseDir}/scripts/analyze-weight-trend.py deviation-check \
  --data-dir {workspaceDir}/data \
  --plan-file {workspaceDir}/PLAN.md \
  --health-profile {workspaceDir}/health-profile.md \
  --user-file {workspaceDir}/USER.md \
  --tz-offset {tz_offset}
```

No need to read PLAN.md or USER.md yourself — the script parses plan start date, calorie target, and health flags internally.
