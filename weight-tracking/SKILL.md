---
name: weight-tracking
version: 1.0.0
description: "Track body weight with full CRUD operations, unit conversion, and trend analysis. Trigger when user reports weight, asks about weight trend, wants to correct a weight entry, or change their unit preference. Trigger phrases: 'I weigh...', '体重...', '称了一下...', 'my weight is...', 'change to pounds', '改成斤', 'weight trend', '体重趋势'."
metadata:
  openclaw:
    emoji: "scales"
    homepage: https://github.com/NanoRhino/weight-loss-skill
---

# Weight Tracking

> ⚠️ **SILENT OPERATION:** Never narrate internal actions, skill transitions, or tool calls to the user. No "Let me check...", "Now I'll transition to...", "Reading your profile...". Just do it silently and respond with the result.


Manage body weight records with full CRUD operations. All data lives in a
single JSON file; display always uses the user's preferred unit.

## Data Storage

**File:** `{workspaceDir}/data/weight.json`

**Format:** JSON object keyed by ISO-8601 datetime (with timezone offset):

```json
{
  "2026-03-01T08:30:00+08:00": { "value": 80, "unit": "kg" },
  "2026-03-04T07:45:00+08:00": { "value": 79.5, "unit": "kg" },
  "2026-03-04T21:00:00+08:00": { "value": 79.8, "unit": "kg" }
}
```

- Each entry stores the **original value and original unit** as reported by the user
- Multiple entries per day are supported (e.g., morning and evening weigh-ins)
- Keys are sorted chronologically

## Unit Preference

**Stored in:** `health-profile.md > Body > Unit Preference`

```markdown
## Body
- **Unit Preference:** kg
```

- Set during onboarding (inferred from user input: "80kg" → `kg`, "165 lbs" → `lb`, "130斤" → `kg`)
- User can change at any time via `set-unit` command
- All display/output uses this preference, with values rounded to 1 decimal place

## Scripts

Script path: `python3 {baseDir}/scripts/weight-tracker.py`

### 1. Save — `save`

```bash
python3 {baseDir}/scripts/weight-tracker.py save \
  --data-dir {workspaceDir}/data \
  --value 79.5 --unit kg \
  --tz-offset 28800 \
  [--correct]
```

- Reads TZ Offset from USER.md to generate local datetime key
- **Auto-detect new vs correction:** if the last entry is ≤ 30 minutes ago, overwrite it (treat as correction). Otherwise, create a new entry.
- `--correct` flag: force overwrite the most recent entry regardless of time gap (for when user explicitly says "that was wrong" / "刚才称错了")
- Returns: `{ "action": "created" | "updated", "key": "<datetime>", "value": <n>, "unit": "<u>" }`

### 2. Load — `load`

```bash
python3 {baseDir}/scripts/weight-tracker.py load \
  --data-dir {workspaceDir}/data \
  --display-unit kg \
  [--last 7] \
  [--from 2026-02-01 --to 2026-03-06]
```

- Returns all matching entries converted to `--display-unit`, rounded to 1 decimal place
- `--last N`: return the N most recent entries
- `--from` / `--to`: filter by date range (inclusive)
- Without filters: returns all entries

### 3. Delete — `delete`

```bash
python3 {baseDir}/scripts/weight-tracker.py delete \
  --data-dir {workspaceDir}/data \
  --key "2026-03-06T08:30:00+08:00"
```

- Removes the entry with the exact datetime key
- Returns confirmation or error if key not found

### 4. Update — `update`

```bash
python3 {baseDir}/scripts/weight-tracker.py update \
  --data-dir {workspaceDir}/data \
  --key "2026-03-06T08:30:00+08:00" \
  --value 75.0 --unit kg
```

- Updates the value and unit for an existing entry
- Returns confirmation or error if key not found

### 5. Set Unit Preference — `set-unit`

```bash
python3 {baseDir}/scripts/weight-tracker.py set-unit \
  --health-profile {workspaceDir}/health-profile.md \
  --unit lb
```

- Updates `health-profile.md > Body > Unit Preference`
- Returns confirmation with the new unit

## Timezone Handling

The server runs in UTC. To record the correct local datetime:

1. Read `TZ Offset` from USER.md (already in context)
2. Pass `--tz-offset <seconds>` to the `save` command
3. The script calculates the user's local time and formats the key as ISO-8601 with offset (e.g., `2026-03-06T08:30:00+08:00`)

## Workflow

### User Reports Weight

1. Read `health-profile.md > Body > Unit Preference` for display unit
2. Call `save` with the reported value, unit, and timezone offset
3. Check the response `action` field:
   - `"created"` → confirm: "Logged ✓"
   - `"updated"` → confirm: "Updated ✓"
4. Display the saved value in the user's preferred unit

### User Asks for Trend / History

1. Read `health-profile.md > Body > Unit Preference`
2. Call `load` with appropriate filters and `--display-unit`
3. Present the data (table, summary, or trend description depending on context)

### User Wants to Correct an Entry

1. If user says "that was wrong" / "刚才称错了" after a recent save → call `save` with `--correct` and the new value
2. If user references a specific date → call `update` with the matching `--key`

### User Changes Unit Preference

1. Call `set-unit` with the new unit
2. Confirm the change to the user

## Interaction Guidelines

- **Record weight whenever mentioned.** Weight recording is NOT limited to scheduled weigh-in days. If the user mentions a specific weight number in any context — casual conversation, progress check-in, replying to a reminder, or unprompted — call `save` to record it. Examples: "今天早上74.5"、"刚称了一下79"、"I was 165 this morning". The only exception is when the user is clearly referring to a past or hypothetical number, not a current reading (e.g., "我以前80公斤"、"if I were 70kg").
- **Never comment on weight changes unprompted.** Just log and confirm. Emotional reactions to weight (positive or negative) are handled by the `emotional-support` skill.
- **Always display in preferred unit**, rounded to 1 decimal place.
- **Accept any common unit** in user input: kg, lb, lbs, 斤 (catty = 0.5 kg), 公斤. Convert to standard kg or lb for storage.
- **Fasting tag**: if the user mentions they haven't eaten yet, or it's a morning weigh-in before breakfast, note `fasting: true` in the response context (for notification-composer to use). If they've already eaten, note `fasting: false`.

## Used By Other Skills

This skill's script is called by other skills for weight data access:

| Skill | Usage |
|-------|-------|
| `notification-composer` | `save` when user replies to weight reminder; `load --last 1` to check if already weighed today |
| `weekly-report` | `load --from --to` for weekly weight trend |
| `emotional-support` | `load --last N` for recent weight context |
| `habit-builder` | `load` for weight trend analysis |
| `user-onboarding-profile` | `save` to record initial weight during onboarding |
| `weight-loss-planner` | `load --last 1` to get current weight for calculations |
