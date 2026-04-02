# CRUD Operations (Delete / Update / Set Unit)

## Delete — `delete`

```bash
python3 {baseDir}/scripts/weight-tracker.py delete \
  --data-dir {workspaceDir}/data \
  --key "2026-03-06T08:30:00+08:00"
```

- Removes the entry with the exact datetime key
- Returns confirmation or error if key not found

## Update — `update`

```bash
python3 {baseDir}/scripts/weight-tracker.py update \
  --data-dir {workspaceDir}/data \
  --key "2026-03-06T08:30:00+08:00" \
  --value 75.0 --unit kg
```

- Updates the value and unit for an existing entry
- Returns confirmation or error if key not found

## Set Unit Preference — `set-unit`

```bash
python3 {baseDir}/scripts/weight-tracker.py set-unit \
  --health-profile {workspaceDir}/health-profile.md \
  --unit lb
```

- Updates `health-profile.md > Body > Unit Preference`
- Returns confirmation with the new unit

## Correction Workflow

1. If user says "that was wrong" / "刚才称错了" after a recent save → call `save` with `--correct` and the new value
2. If user references a specific date → call `update` with the matching `--key`
