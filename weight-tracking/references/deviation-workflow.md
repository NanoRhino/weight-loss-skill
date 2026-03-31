# Deviation Check — Severity Response Guide

Deviation-check is bundled into `save-and-check.py` — no separate call needed. The `deviation` field in the combined response contains the result. The script handles all skip logic internally (missing PLAN.md, health flags, insufficient data).

## Result Fields

- `triggered: false` → no action, just confirm the log
- `triggered: false` + `reason: "no_plan"` → no PLAN.md, skip silently
- `triggered: false` + `reason: "health_flag"` → skip silently
- `triggered: false` + `reason: "insufficient_data"` → skip silently
- `triggered: true` → respond per severity below
- `temporary_causes` → if present, mention lightly
- `adaptation_period: true` → first 2 weeks of plan, be extra gentle

---

## Severity Routing

> ⚠️ **When `triggered: true`, you MUST read the referenced file and follow it exactly. Do NOT improvise the response.**

| Severity | Streak | Action |
|----------|--------|--------|
| `none` | 0 | Weight stable or down — just confirm the log. No extra output. |
| `comfort` | 1 | Append a warm one-liner after log confirmation. Use `weight-gain-strategy/references/diagnosis-templates.md` for templates. If `temporary_causes` present, mention lightly. |
| `cause-check` | 2–3 | **Read `weight-gain-strategy/references/cause-check-flow.md` and follow Steps A→D.** In Step A, also silently run `analyze` (command in that file). |
| `significant` | 4+ | **Read `weight-gain-strategy/references/interactive-flow.md` and follow Steps 1→3.** Run `analyze` in Step 1. |

---

## Standalone Command

For manual re-check (not normally needed):
```bash
python3 {weight-gain-strategy:baseDir}/scripts/analyze-weight-trend.py deviation-check \
  --data-dir {workspaceDir}/data \
  --plan-file {workspaceDir}/PLAN.md \
  --health-profile {workspaceDir}/health-profile.md \
  --user-file {workspaceDir}/USER.md \
  --tz-offset {tz_offset}
```
