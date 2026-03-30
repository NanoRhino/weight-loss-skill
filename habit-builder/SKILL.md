---
name: habit-builder
description: >
  Designs and manages healthy habits for sustainable weight loss.
  Atomic Habits / Tiny Habits methodology. Use when: recommending a habit
  after onboarding, graduating or restarting a habit, user asks about habits,
  or Weekly Review identifies a pattern. Does not send its own reminders —
  check-ins woven into meal conversations via Notification Composer.
---

# Habit Builder

> ⚠️ **SILENT OPERATION:** Never narrate internal actions or tool calls.

## Philosophy

- **Small > ambitious.** Start tiny. Scale later.
- **System > willpower.** Design the environment so the behavior is easy.
- **Lifestyle > diet.** Sustainable living, not aggressive weight loss.

---

## How Habits Surface

Habits appear inside meal conversations (Notification Composer). No separate reminders.

Before each meal reminder, read `habits.active`. Pick the slot matching the habit type.
See `references/habit-details.md` for the full type → timing table.

### Frequency

```bash
python3 {baseDir}/scripts/action-pipeline.py schedule \
  --cadence <cadence> --days <days_since_activation>
```

- Daily behaviors: **daily** (Anchor/week 1) → every 3d (Build) → every 5-7d (Solidify) → weekly (Autopilot)
- Weekly/conditional: every occurrence early → every-other later
- **3 consecutive no-responses → stall.** Stop. Revisit at Weekly Review.

### Mention rules

- One sentence max, woven into the meal conversation
- Record response to `habits.daily_log.{date}`
- Min gap: 2 reminders between mentions
- Tone: casual friend, not compliance coach
  - Good: `"Walk after dinner tonight?"` Bad: `"Did you complete your habit today?"`

---

## Habit Recommendation

### Triggers

After onboarding | habit graduated | Weekly Review insight | user asks | failure restart

### Design method

1. **Identify gap** — read `USER.md`, `health-profile.md`, `health-preferences.md`, recent `logs.*`. See `references/habit-details.md` for dimension checklist.
2. **Pick highest leverage** — "Which one change makes the most other things easier?" (e.g., "go to bed by 11" > "stop snacking" — eliminates the window)
3. **Tiny-fy** — shrink until passable on the worst day. See `references/habit-details.md` for examples.
4. **Bind to trigger** — `"After I [EXISTING], I will [NEW TINY]."`  Specific > vague ("after dinner" > "in the evening").
5. **Present** — 1-2 sentences, conversational. Never repeat formally or explain methodology.

Accept → react with energy. Decline → one alternative (hydration/sleep as fallback). Decline again → drop it.
**Single-ask rule applies** (`SKILL-ROUTING.md`).

---

## Habit Lifecycle

### Active tracking

Write to `habits.active` via the activate script (§ Pipeline Step 3). Standalone habits: write directly with `habit_id`, `description`, `tiny_version`, `trigger`, `type`, `bound_to_meal`, `created_at`, `phase`, `mention_log`, `completion_log`.

### Completion signals

| Signal | Record as |
|--------|-----------|
| Confirms done / partial | `completed` |
| Says missed | `missed` |
| Ignores mention | `no_response` |
| Does it unprompted | `completed` + `self_initiated: true` |

### Feedback

- Praise behavior, not person. No streak counts. Vary energy.
- ~1 in 3-4 completions gets a real comment; rest get `"✓"`.
- See `references/habit-details.md` for examples.

### Graduation

```bash
python3 {baseDir}/scripts/action-pipeline.py check-graduation \
  --cadence <cadence> --log '<completion_log JSON>'
```

**Signal 1 (required):** ≥ 80% completion (daily=14 days, weekly=6 occurrences, conditional=8)
**+ at least one of:**
- Signal 2: self-initiation > 30%
- Signal 3: user confirms automatic (`"还需要我提醒吗？"`)

On graduation: celebrate briefly → move to `habits.graduated` → advance queue → monthly spot-check via Weekly Review.

### Failure

Detection: 3 consecutive `missed` or `no_response`.

Surface gently at next natural moment. Three paths: keep going (reset) / make easier (shrink) / try different (re-recommend). See `references/habit-details.md` for response examples and blacklisted phrases.

### Scaling & concurrency

- Upgrade after graduation only if user wants. Don't auto-upgrade.
- Max 3 active. If any < 70% completion, suggest stabilizing first.

---

## Advice-to-Action Pipeline

Turns advice from any skill into a queue of tiny, trackable actions.
Activate when advice implies sustained behavior change (not one-off facts).

### Step 1: Decompose

≤ 5 independent actions. Each = one trigger + one behavior. Must pass Tiny Habits test.

### Step 2: Prioritize

```bash
python3 {baseDir}/scripts/action-pipeline.py prioritize \
  --actions '[{"action_id":"x", "impact":3, "ease":3, "chain":true, ...}]'
```

Sorted by `Impact × Ease + chain bonus`. Present top one casually, ask if user wants 1-2 more (max 3 concurrent, different time slots).

### Step 3: Activate

```bash
python3 {baseDir}/scripts/action-pipeline.py activate \
  --action '<action JSON with trigger_cadence>' \
  --source-advice "..."
```

Maps `trigger_cadence` → `type` for notification-composer. Update `habits.action_queue` status to `active`.

### Step 4: Follow-up

Schedule via `action-pipeline.py schedule`. Habits surface in meal conversations.
- **Weekly:** relevant day only, first meal conversation.
- **Conditional:** reactive only — mention when user's message matches the condition.

### Step 5: Graduation

Same as § Lifecycle Graduation. On graduation, introduce next queued action immediately. Exception: emotionally taxing → wait for Weekly Review.

Max tracking: 90 days. Auto-pause if not graduated.

### Step 6: Queue

| Event | Action |
|-------|--------|
| Graduation | Advance next (fill freed slots, cap 3) |
| Failure (3 misses) | Offer: keep / shrink / swap / skip |
| User skips | Move to end of queue |
| User stops all | Pause entire queue |
| New advice | Append (don't jump line) |

### Data structure

```json
{
  "source_advice": "多喝水少喝奶茶",
  "source_skill": "weekly-report",
  "created_at": "2026-03-30",
  "actions": [
    {
      "action_id": "water-after-waking",
      "description": "起床后喝一杯水",
      "trigger": "起床后",
      "behavior": "喝一杯温水",
      "trigger_cadence": "daily_fixed",
      "priority_score": 10,
      "status": "active",
      "activated_at": "2026-03-30"
    }
  ]
}
```

Valid `status`: `queued` → `active` → `graduated` | `paused` | `stalled` | `removed`

---

## Workspace

### Reads

| Path | Purpose |
|------|---------|
| `USER.md` | Basic info, health flags |
| `health-profile.md` | Goals, meal schedule, body, activity, diet config |
| `health-preferences.md` | Accumulated preferences |
| `PLAN.md` | BMR, TDEE, calorie targets |
| `data/meals/YYYY-MM-DD.json` | Eating patterns (via `nutrition-calc.py load`) |
| `data/weight.json` | Weight trend (via `weight-tracker.py load`) |

### Writes

| Path | When |
|------|------|
| `habits.active` | Habit accepted |
| `habits.graduated` | Habit graduates |
| `habits.daily_log.{date}` | Completion/miss/no_response |
| `habits.mention_counter` | After each mention |
| `habits.lifestyle_gaps` | Gap analysis (for Weekly Review) |
| `habits.action_queue` | Pipeline actions with priority and status |
| `habits.advice_history` | Completed advice records |

Weekly Review reads `habits.*` for progress summaries.

---

## Safety

| Signal | Action |
|--------|--------|
| Extreme habit proposed | Redirect to sustainable alternative. |
| Obsessive tracking / guilt | Scale back frequency. Write `flags.habit_anxiety: true`. |
| Self-hatred over misses | **Defer to `emotional-support`.** Emotion first. Write `flags.body_image_distress: true` if severe. |

---

## Performance

- Recommendation: 3-5 turns max
- Mention: 1 sentence
- Acknowledgment: 1-5 words
- Failure restart: 2-3 turns max
