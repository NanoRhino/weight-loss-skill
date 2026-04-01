# Interactive Flow (streak 4+ / manual trigger)

## Step 1: Analyze & Present Causes

1. Read `timezone.json` → run `analyze`
2. Present: **[Reassurance]** → **[Trend summary]** → **[Diagnosis]**
   - Reassurance: one playful sentence normalizing fluctuation. Never open with bad news.
   - Trend: "Over the past {N} days, your weight wandered from {start} to {end} — that's {change}."
   - Diagnosis: use per-factor templates from `references/diagnosis-templates.md`.
3. Pause — do NOT continue to Step 2 automatically.
4. Transition: "Want to brainstorm a tweak or two?"

If `normal_fluctuation` → reassuring close, no Step 2.
Only proceed to Step 2 when the user explicitly agrees. If ignored → drop it.

## Step 2: Discuss & Choose Strategy

Present 1–3 strategy options based on the `suggested_strategies` from the analysis.

**Strategy ranking rule:** Sort options by ease-of-execution for this specific
user, not by theoretical effectiveness. Cross-reference `health-profile.md`
(activity level, preferences) and `health-preferences.md` to determine what
the user is already good at or enjoys. Put the lowest-friction option first.
Examples:
- User exercises regularly → lead with "add one more session" rather than "cut calories"
- User enjoys cooking → lead with "swap this ingredient" rather than "eat less"
- User is sedentary but has been logging meals diligently → lead with a small calorie tweak they can track easily
- User's exercise dropped recently but they used to be active → lead with "get back to your old routine" (reactivation is easier than starting fresh)

For each option:

```
Option {N}: {strategy_name}
{one-sentence description}
{expected_impact} over {duration}
```

### Strategy Types

#### A. Reduce Calories (`reduce_calories`)
- Reduce daily intake by 100–300 kcal (never below calorie floor)
- Suggest specific meal adjustments based on the user's logged meals (e.g., "swap the afternoon snack for fruit", "reduce rice portion at dinner by 1/3")
- Duration: 1–2 weeks, then reassess

#### B. Increase Exercise (`increase_exercise`)
- Add 1–3 more exercise sessions per week
- Suggest activities aligned with user's existing habits and preferences
- If user doesn't exercise, suggest walking 20–30 min/day as a starting point
- Duration: 1–2 weeks, then reassess

#### C. Combined (`combined`)
- A modest version of A + B (smaller calorie reduction + 1 extra session)
- For users who prefer balanced adjustments
- Duration: 1–2 weeks

**After presenting options:** Ask the user which feels most doable — "Which
one sounds the least like torture?" Respect their choice. If they choose
something suboptimal, support it enthusiastically — compliance beats
optimization every time.

## Step 3: Confirm & Save Strategy

> ⚠️ **MUST execute both script calls below before replying.** Do not skip.

1. Confirm the chosen strategy with specific, actionable details:
   - What exactly changes (calorie target, number of sessions, specific meals)
   - For how long (start date → end date)
   - When to check in (midpoint and end)

2. **Create habit** via `weight-gain-habits`:
   ```bash
   python3 {habit-builder:baseDir}/scripts/action-pipeline.py activate \
     --action '{
       "action_id": "<strategy-derived-id>",
       "description": "<what the user committed to>",
       "trigger": "<meal or time>",
       "behavior": "<tiny version>",
       "trigger_cadence": "<every_meal|daily_fixed|daily_random|weekly|conditional>",
       "bound_to_meal": "<breakfast|lunch|dinner|null>"
     }' \
     --source weight-gain-strategy \
     [--strict] \
     --source-advice "<strategy context>"
   ```
   - `--strict`: add when `logging_gaps` + `calorie_surplus` detected (see `weight-gain-habits/references/strict-mode.md`).
   - The script outputs the complete `habits.active` entry JSON. **Write it to `habits.active` immediately.**

3. **Save strategy metadata:**
   ```bash
   python3 {baseDir}/scripts/analyze-weight-trend.py save-strategy \
     --data-dir {workspaceDir}/data \
     --strategy-type <reduce_calories|increase_exercise|combined> \
     --params '{"duration_days": 7, ...}' \
     --tz-offset {tz_offset}
   ```

4. Close with encouragement — brief, genuine, a bit cheeky: "Let's see what the scale says next week — I'm betting on you."

**Do NOT:**
- Set up reminders here (that's `notification-manager`'s job)
- Modify PLAN.md (the strategy is temporary; PLAN.md is the long-term plan)
- Generate HTML reports
