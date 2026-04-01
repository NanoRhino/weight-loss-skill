---
name: weight-tracking
version: 1.1.0
description: "Track body weight with full CRUD operations, unit conversion, and trend analysis. Trigger when user reports weight, asks about weight trend, wants to correct a weight entry, or change their unit preference. Trigger phrases: 'I weigh...', '体重...', '称了一下...', 'my weight is...', 'change to pounds', '改成斤', 'weight trend', '体重趋势'."
metadata:
  openclaw:
    emoji: "scales"
    homepage: https://github.com/NanoRhino/weight-loss-skill
---

# Weight Tracking

> ⚠️ **SILENT OPERATION:** Never narrate internal actions, skill transitions, or tool calls to the user. Just do it silently and respond with the result.

## Performance

**Use TOOLS.md Quick Reference first.** If `tz_offset`, `unit_preference`, and `daily_cal_target` are already in the auto-injected TOOLS.md context, use those values directly — do NOT read `timezone.json` or `health-profile.md`.

Only fall back to reading those files if Quick Reference is missing or outdated.

Do NOT read this SKILL.md again if it's already in context from a prior turn.

## Data Storage

**File:** `{workspaceDir}/data/weight.json` — JSON object keyed by ISO-8601 datetime with timezone offset. Each entry: `{ "value": 80, "unit": "kg" }`.

## Scripts

Script path: `python3 {baseDir}/scripts/weight-tracker.py`

### Save + Deviation Check — `save-and-check.py` (preferred)

**Use this for all weight saves.** Combines save + deviation-check in ONE call — no second tool call needed.

```bash
python3 {baseDir}/scripts/save-and-check.py \
  --data-dir {workspaceDir}/data \
  --value 79.5 --unit kg \
  --tz-offset 28800 \
  --plan-file {workspaceDir}/PLAN.md \
  --health-profile {workspaceDir}/health-profile.md \
  --user-file {workspaceDir}/USER.md \
  --wgs-script {weight-gain-strategy:baseDir}/scripts/analyze-weight-trend.py \
  [--correct]
```

Returns:
```json
{
  "save": { "action": "created"|"updated", "key": "<datetime>", "value": 79.5, "unit": "kg" },
  "deviation": { "triggered": true|false, "severity": "none"|"comfort"|"cause-check"|"significant", ... }
}
```

- `deviation` is `null` if PLAN.md missing, health flags active, or insufficient data — no extra handling needed.

### Save only — `weight-tracker.py save`

Use only when deviation-check is not needed (e.g., onboarding initial weight).

```bash
python3 {baseDir}/scripts/weight-tracker.py save \
  --data-dir {workspaceDir}/data \
  --value 79.5 --unit kg \
  --tz-offset 28800 \
  [--correct]
```

- Auto-detects new vs correction: if last entry ≤ 30 min ago, overwrites. Otherwise creates new.
- `--correct`: force overwrite most recent entry (when user explicitly says "that was wrong")

### Load — `load`

```bash
python3 {baseDir}/scripts/weight-tracker.py load \
  --data-dir {workspaceDir}/data \
  --display-unit kg \
  [--last 7] \
  [--from 2026-02-01 --to 2026-03-06]
```

Returns entries converted to `--display-unit`, rounded to 1 decimal.

### Other Commands

See `references/crud-operations.md` for: `delete`, `update`, `set-unit`.

## Workflow

### User Reports Weight

1. Read `timezone.json` → `tz_offset`; read `health-profile.md` → Unit Preference (parallel, first session only)
2. Call `save-and-check.py` — **one call does save + deviation-check + analyze:**
   ```bash
   python3 {baseDir}/scripts/save-and-check.py \
     --data-dir {workspaceDir}/data \
     --value <N> --unit <u> --tz-offset <tz> \
     --plan-file {workspaceDir}/PLAN.md \
     --health-profile {workspaceDir}/health-profile.md \
     --user-file {workspaceDir}/USER.md \
     --wgs-script {weight-gain-strategy:baseDir}/scripts/analyze-weight-trend.py \
     --weight-script {baseDir}/scripts/weight-tracker.py \
     --nutrition-script {diet-tracking-analysis:baseDir}/scripts/nutrition-calc.py
   ```
3. Read response — all results arrive together:
   - `save.action`: `"created"` → "Logged ✓"; `"updated"` → "Updated ✓". Show value in preferred unit.
   - `tools_updated: true` → TOOLS.md `current_weight` was auto-updated by the script. **Do NOT manually edit TOOLS.md** — it's already done.
   - `deviation` is `null` or `triggered: false` → just the log confirmation.
   - `deviation.triggered: true` → ⚠️ **STOP.** Read BOTH files **in parallel in one tool call:**
     - `references/deviation-workflow.md`
     - `weight-gain-strategy/references/cause-check-flow.md` (for cause-check/significant severity)
     
     Then follow the workflow exactly. Do NOT freestyle a response.
     
     `analyze` result is already included in the script output — **do NOT run analyze separately.** Use `analyze` field directly in Step C (data reveal).

### User Asks for Trend / History

1. Call `load` with appropriate filters and `--display-unit`
2. Present data (table, summary, or trend description)

### User Wants to Correct / Delete / Change Unit

See `references/crud-operations.md`.

## Interaction Guidelines

- **Record weight whenever mentioned.** Not limited to scheduled days. "今天早上74.5", "刚称了一下79" → call `save`. Exception: past/hypothetical ("我以前80公斤").
- **Never comment on weight changes unprompted.** Just log and confirm. Emotional reactions → `emotional-support` skill.
- **Always display in preferred unit**, rounded to 1 decimal.
- **Accept any common unit**: kg, lb, lbs, 斤 (=0.5 kg), 公斤.
- **Fasting tag**: if user mentions empty stomach / morning weigh-in → note `fasting: true` in context.

## References

| File | Contents |
|------|----------|
| `references/crud-operations.md` | Delete, update, set-unit commands + correction workflow |
| `references/deviation-workflow.md` | Deviation-check severity table, response guide, command |
| `references/integrations.md` | Which other skills use this skill's scripts |
