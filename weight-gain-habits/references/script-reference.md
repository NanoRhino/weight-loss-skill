# Weight-Gain Habits — Script Reference

## Cross-skill calls (from habit-builder)

All generic habit mechanics use `{habit-builder:baseDir}/scripts/action-pipeline.py`:

- `activate` — create habit entry (with `--source weight-gain-strategy` and optional `--strict`)
- `should-mention` — decide if habit should surface in meal conversation
- `check-graduation` — evaluate if habit is ready to graduate
- `check-failure` — detect 3 consecutive misses
- `check-concurrency` — respect global max-3 active habits limit

See `habit-builder/references/script-reference.md` for full syntax.

## Own scripts

### check-escalation — 失败后是否升级到 weight-gain-strategy

```bash
python3 {baseDir}/scripts/pact-pipeline.py check-escalation \
  --data-dir {workspaceDir}/data \
  --tz-offset {tz_offset}
# → {"escalate": true/false, "streak": N, "action": "escalate_significant"|"offer_smaller_pact"}
```

When a pact habit fails (3 consecutive misses), call this to check the current weight streak:
- `streak < 4` → offer smaller pact within this skill
- `streak >= 4` → hand off to `weight-gain-strategy` Interactive Flow

### check-strict-eligibility — 是否启用严格模式

```bash
python3 {baseDir}/scripts/pact-pipeline.py check-strict-eligibility \
  --top-factors '["logging_gaps", "calorie_surplus"]'
# → {"strict": true, "logging_gaps": true, "calorie_surplus": true}
```

Pass the `top_factors` array from `analyze` result. Returns `strict: true` when both `logging_gaps` AND `calorie_surplus` are present.
