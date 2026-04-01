---
name: weight-gain-habits
description: >
  Owns the lifecycle of habits originating from weight-gain-strategy pacts.
  Handles strict mode, pact-based accountability, daily motivation, and
  failure escalation. Use when: cause-check or interactive flow creates a
  pact habit, notification-composer detects strict: true, or a pact habit
  graduates/fails. Does NOT own general lifestyle habits — those belong
  to habit-builder.
---

# Weight-Gain Habits

Manages habits born from weight-gain-strategy pacts — the mutual commitments
made when the user's weight trend triggers cause-check or significant analysis.
These habits are firmer and more accountable than general lifestyle habits.

> ⚠️ **SILENT OPERATION:** Never narrate internal actions or tool calls.

## Routing Gate

**Entry paths:**
- **Pact creation:** `weight-gain-strategy` cause-check (Step D) or interactive flow (Step 3) → user agrees to pact → this skill creates and tracks the habit
- **Strict mode execution:** `notification-composer` detects `strict: true` + `source: "weight-gain-strategy"` → reads this skill's `references/strict-mode.md`
- **Check-in:** notification-composer calls `should-mention` for pact habits (`source: "weight-gain-strategy"`)
- **Failure escalation:** pact habit fails → this skill decides whether to escalate back to `weight-gain-strategy`
- **User query:** "what's our deal?" / "how's the pact going?"

**Not this skill:** General lifestyle habits (onboarding, Weekly Review insights, advice pipeline) → `habit-builder`.

**Partition rule:** `habits.active` entries with `source: "weight-gain-strategy"` belong to this skill. All other entries belong to `habit-builder`.

## Principles

- **Mutual commitment.** Every pact has an AI side and a user side. AI side is real — follow through.
- **Firm but caring.** Strict coach, not angry parent. Data-driven, playful accountability.
- **Escalate, don't nag.** If the pact isn't working, escalate to weight-gain-strategy for reassessment rather than repeating the same ask.

---

## Pact Creation

Called by `weight-gain-strategy` after user agrees to a pact (cause-check Step D or interactive flow Step 3).

**Step 1 — Create habit** using habit-builder's script:

```bash
python3 {habit-builder:baseDir}/scripts/action-pipeline.py activate \
  --action '{
    "action_id": "<cause-derived-id>",
    "description": "<user side of pact>",
    "trigger": "<meal or time>",
    "behavior": "<tiny version>",
    "trigger_cadence": "<every_meal|daily_fixed|daily_random|weekly|conditional>",
    "bound_to_meal": "<breakfast|lunch|dinner|null>"
  }' \
  --source weight-gain-strategy \
  [--strict] \
  --source-advice "<AI side of pact + context>"
```

- `--strict`: add when `logging_gaps` AND `calorie_surplus` both detected
- Output → **write to `habits.active` immediately**

**Step 2 — Save strategy metadata:**

```bash
python3 {weight-gain-strategy:baseDir}/scripts/analyze-weight-trend.py save-strategy \
  --data-dir {workspaceDir}/data \
  --strategy-type <reduce_calories|increase_exercise|combined> \
  --params '{"duration_days": 7, ...}' \
  --tz-offset {tz_offset}
```

→ Full pact examples by cause: `weight-gain-strategy/references/cause-check-flow.md` (pact table)

---

## Habit Check-in

Pact habits surface in meal conversations via notification-composer, same as general habits. Use habit-builder's `should-mention` script:

```bash
python3 {habit-builder:baseDir}/scripts/action-pipeline.py should-mention \
  --habit '<habit JSON>' --meal <meal> --days <N> \
  --days-since-last-mention <N> --reminders-since-last-mention <N>
```

The script reads `strict` from the habit JSON and extends anchor phase to 14 days automatically.

---

## Strict Mode

When the habit has `strict: true`, 4 extra behaviors activate in notification-composer.

→ Full rules, behaviors, motivation toolkit, duration, failure escalation: `references/strict-mode.md`

---

## Lifecycle

### Completion tracking

Same signals as habit-builder: `completed` / `missed` / `no_response` / `self_initiated`. Write to `habits.daily_log.{date}`.

### Graduation

Run `check-graduation` (habit-builder's script). Same criteria: ≥ 80% completion over 14 days + self-initiation > 30% or user confirms. On graduation → celebrate → move to `habits.graduated` → strict behaviors stop.

### Failure + Escalation

Run `check-failure`. When 3 consecutive misses detected:

1. Surface gently: keep / shrink / swap
2. **Check weight streak** via `pact-pipeline.py check-escalation`:
   ```bash
   python3 {baseDir}/scripts/pact-pipeline.py check-escalation \
     --data-dir {workspaceDir}/data \
     --tz-offset {tz_offset}
   ```
   - `streak < 4` → stay in this skill, offer smaller pact. Keep/shrink → `strict` stays. Swap unrelated → `strict` resets to false.
   - `streak >= 4` → **escalate to `weight-gain-strategy` significant path** (Interactive Flow Steps 1→3).

---

## Safety

| Signal | Action |
|--------|--------|
| User reacts negatively to tough love | Immediately soften. Defer to `emotional-support` if distress detected. |
| User opts out ("stop tracking") | Respect. Pause habit, stop all strict behaviors. |
| Obsessive compliance / anxiety | Scale back frequency. Write `flags.habit_anxiety: true`. |

---

## Workspace

### Reads

`USER.md` (Core Motivation), `health-profile.md`, `PLAN.md`, `data/meals/*.json`, `data/weight.json`, `habits.active` (own entries only: `source: "weight-gain-strategy"`)

### Writes

| Path | When |
|------|------|
| `habits.active` | Pact accepted (source: weight-gain-strategy) |
| `habits.graduated` | Pact habit graduates |
| `habits.daily_log.{date}` | Completion/miss/no_response |

### References

| File | Contents |
|------|----------|
| `references/strict-mode.md` | Strict mode: 4 behaviors, motivation toolkit, duration, failure escalation, ownership |
| `references/script-reference.md` | Cross-skill calls to action-pipeline.py + own pact-pipeline.py commands |
