# Deviation Check — Severity Response Guide

Deviation-check is bundled into `save-and-check.py` — no separate call needed. The `deviation` field in the combined response contains the result. The script handles all skip logic internally (missing PLAN.md, health flags, insufficient data).

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

Normally called via `save-and-check.py` (see SKILL.md). For standalone use (e.g., manual re-check):

```bash
python3 {weight-gain-strategy:baseDir}/scripts/analyze-weight-trend.py deviation-check \
  --data-dir {workspaceDir}/data \
  --plan-file {workspaceDir}/PLAN.md \
  --health-profile {workspaceDir}/health-profile.md \
  --user-file {workspaceDir}/USER.md \
  --tz-offset {tz_offset}
```
