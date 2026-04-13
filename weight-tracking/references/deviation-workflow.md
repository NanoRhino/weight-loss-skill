# Deviation Check — Severity Response Guide

Deviation-check is bundled into `save-and-check.py` — no separate call needed. The `deviation` field in the combined response contains the result. The script handles all skip logic internally (missing PLAN.md, health flags, insufficient data).

## Result Fields

- `triggered: false` → no action, just confirm the log
- `triggered: false` + `reason: "no_plan"` → no PLAN.md, skip silently
- `triggered: false` + `reason: "health_flag"` → skip silently
- `triggered: false` + `reason: "insufficient_data"` → skip silently
- `triggered: false` + `reason: "cooldown"` → recently triggered, skip silently
- `triggered: true` → respond per severity below
- `temporary_causes` → if present, mention lightly
- `adaptation_period: true` → first 2 weeks of plan, be extra gentle

---

## Severity Routing

| Severity | When | Action |
|----------|------|--------|
| `none` | No increase | Weight stable or down — just confirm the log. |
| `light` | First increase, or within 7 days of a cause-check | Append a brief comfort line after log confirmation. Quick data glance if relevant, keep it light. If `temporary_causes` is non-empty, use the cause's `message` field. |
| `cause-check` | ≥3 days after light, or ≥7 days after previous cause-check | **Read `weight-gain-strategy/references/cause-check-flow.md` and follow the flow.** Run `analyze` silently at the start. |

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
