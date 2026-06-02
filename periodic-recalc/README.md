# periodic-recalc

Automated periodic recalculation of weight loss plans based on current weight.

## Overview

Every 4 weeks, this skill:
1. Checks if user has recent weight data (within 14 days)
2. Recalculates TDEE, daily calorie target, and macro ranges using current weight
3. Updates PLAN.md with new values
4. Reviews actual eating patterns vs current diet_mode
5. Suggests diet mode changes if patterns have shifted

## Files

### Scripts

- `scripts/periodic-recalc.py` — Main orchestration script
- `scripts/diet-mode-review.py` — Analyzes eating patterns vs diet mode
- `scripts/check-pending-recalc.py` — Checks if deferred recalc should trigger

### Data Files

#### `pending-recalc.json`

Location: `{workspace}/data/pending-recalc.json`

Written when recalc is deferred (awaiting weight or user is on leave).

**Structure:**
```json
{
  "created_at": "2026-06-02T10:30:00+08:00",
  "reason": "awaiting_weight" | "on_leave",
  "cycle_date": "2026-06-02"
}
```

**Fields:**
- `created_at` — ISO 8601 timestamp when the flag was created
- `reason` — Why recalc was deferred:
  - `awaiting_weight` — No recent weight data (>14 days old). Will trigger when user logs weight.
  - `on_leave` — User is on leave. Will trigger on first Sunday after leave ends.
- `cycle_date` — The date when the 4-week cycle completed (for tracking)

**Lifecycle:**
- Created by `periodic-recalc.py` when recalc cannot proceed
- Read by `check-pending-recalc.py` after weight logging
- Deleted by `periodic-recalc.py` after successful recalc

## Trigger Conditions

### Primary: Cron (Every 4 Weeks Sunday)

Cron job calls `periodic-recalc.py`. Possible outcomes:

| Action | Condition | Behavior |
|--------|-----------|----------|
| `recalculated` | Fresh weight data available | PLAN.md updated, notify user with celebratory message |
| `awaiting_weight` | Weight data >14 days old | Write `pending-recalc.json`, ask user to weigh in |
| `on_leave` | User is on leave (`leave.json` end >= today) | Write `pending-recalc.json`, reschedule for after leave |

### Secondary: After Weight Logging

When `weight-tracking` logs a new weight:
1. Call `check-pending-recalc.py`
2. If `should_trigger: true` → run full recalc flow
3. Delete `pending-recalc.json` after success

## Usage Examples

### Running periodic recalc manually

```bash
python3 scripts/periodic-recalc.py \
  --workspace /path/to/workspace \
  --planner-calc /path/to/weight-loss-planner/scripts/planner-calc.py
```

### Dry-run mode (no file writes)

```bash
python3 scripts/periodic-recalc.py \
  --workspace /path/to/workspace \
  --planner-calc /path/to/planner-calc.py \
  --dry-run
```

### Review diet mode

```bash
python3 scripts/diet-mode-review.py \
  --workspace /path/to/workspace \
  --days 28
```

### Check pending recalc

```bash
python3 scripts/check-pending-recalc.py \
  --workspace /path/to/workspace
```

## Output Format

### periodic-recalc.py

**Success (recalculated):**
```json
{
  "action": "recalculated",
  "old_calories": 1290,
  "new_calories": 1260,
  "old_tdee": 1772,
  "new_tdee": 1740,
  "current_weight": 58.5,
  "previous_weight": 60.0,
  "weight_change": -1.5,
  "macros": {
    "protein_g": [70, 94],
    "fat_g": [28, 42],
    "carbs_g": [142, 189]
  },
  "floor_clamped": false,
  "message_for_user": "..."
}
```

**Awaiting weight:**
```json
{
  "action": "awaiting_weight",
  "current_weight": 58.5,
  "weight_date": "2026-05-18",
  "days_old": 15,
  "message": "Weight data is stale (>14 days). Awaiting new weight entry."
}
```

**On leave:**
```json
{
  "action": "on_leave",
  "message": "User is on leave. Recalc deferred."
}
```

### diet-mode-review.py

**Recommend change:**
```json
{
  "action": "recommend_change",
  "current_mode": "balanced",
  "actual_macros": {
    "protein_pct": 38,
    "carbs_pct": 30,
    "fat_pct": 32
  },
  "recommended_mode": "high_protein",
  "reason": "Your actual protein (38%) exceeds balanced range (25-35%)...",
  "days_analyzed": 25
}
```

**No change needed:**
```json
{
  "action": "no_change",
  "current_mode": "balanced",
  "actual_macros": {...},
  "days_analyzed": 28
}
```

**Insufficient data:**
```json
{
  "action": "insufficient_data",
  "days_analyzed": 5,
  "message": "Not enough meal data (need at least 7 days)."
}
```

### check-pending-recalc.py

**Should trigger:**
```json
{
  "should_trigger": true,
  "reason": "awaiting_weight",
  "cycle_date": "2026-06-02",
  "created_at": "2026-06-02T10:30:00+08:00"
}
```

**Should not trigger:**
```json
{
  "should_trigger": false,
  "reason": "No pending recalc found."
}
```

## Integration with Other Skills

### weight-loss-planner

- **Dependency:** Uses `planner-calc.py` for all TDEE/calorie/macro calculations
- **Data:** Reads formulas from `references/formulas.md` and `references/diet-modes.md`

### weight-tracking

- **Integration:** After logging weight, weight-tracking should call `check-pending-recalc.py`
- **Flow:** If pending recalc exists with `reason="awaiting_weight"`, trigger full recalc

### notification-manager

- **Integration:** Creates cron job for every 4 weeks Sunday
- **Scheduling:** If recalc is deferred due to leave, reschedule for first Sunday after leave ends

## Design Decisions

### Why 14-day staleness threshold?

Balance between:
- Too short: User forgets to weigh for a week, gets nagged
- Too long: Recalc uses outdated data, plan becomes inaccurate

14 days = 2 weeks is a reasonable "you should weigh in" reminder cadence.

### Why always recalculate (no threshold)?

Each 4-week cycle is treated as a "new phase" psychologically. Even small weight changes (0.5 kg) can affect TDEE by 20-30 kcal, which compounds over 4 weeks. Consistency in recalc builds trust in the system.

### Why separate diet-mode-review?

Diet mode is a preference/habit dimension, separate from the metabolic calculation. Running it as a second step allows:
1. User to see the new numbers first
2. Optional prompt for mode change (not forced)
3. Independent testing of macro analysis logic

### Why pending-recalc.json instead of task queue?

Simple, transparent state tracking. Agent can inspect the file directly. No need for database or complex state management.

## Testing

### Test scenario 1: Normal recalc

```bash
# Setup: User at 58.5 kg, last weighed 3 days ago
python3 scripts/periodic-recalc.py --workspace /workspace --planner-calc /planner-calc.py

# Expected: action="recalculated", PLAN.md updated
```

### Test scenario 2: Stale weight

```bash
# Setup: User last weighed 20 days ago
python3 scripts/periodic-recalc.py --workspace /workspace --planner-calc /planner-calc.py

# Expected: action="awaiting_weight", pending-recalc.json created
```

### Test scenario 3: On leave

```bash
# Setup: leave.json exists with end date >= today
python3 scripts/periodic-recalc.py --workspace /workspace --planner-calc /planner-calc.py

# Expected: action="on_leave", pending-recalc.json created
```

### Test scenario 4: Weight logged, pending recalc exists

```bash
# Setup: pending-recalc.json exists with reason="awaiting_weight"
# User logs weight
python3 scripts/check-pending-recalc.py --workspace /workspace

# Expected: should_trigger=true
# Then run periodic-recalc.py → action="recalculated", pending-recalc.json deleted
```

### Test scenario 5: Diet mode drift

```bash
# Setup: User has been eating 38% protein for 28 days, current mode is "balanced"
python3 scripts/diet-mode-review.py --workspace /workspace --days 28

# Expected: action="recommend_change", recommended_mode="high_protein"
```

## Future Enhancements

- [ ] Support for body fat % tracking (use Katch-McArdle when available)
- [ ] Plateau detection (weight stalled for N weeks → suggest diet break)
- [ ] Adaptive recalc frequency (accelerate if weight change is faster than expected)
- [ ] Multi-week trend analysis (not just snapshot comparison)
- [ ] Export recalc history to a log file for user review
