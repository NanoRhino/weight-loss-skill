---
name: weight-gain-strategy
version: 1.0.0
description: "Detect and respond to upward weight trends after weigh-ins or when the user asks why their weight is increasing. Use for: (1) consecutive weight increases detected by post-weigh-in deviation checks, (2) explicit weight-gain questions like 'why am I gaining weight' or '体重怎么涨了'. Provides graduated support from reassurance to cause analysis to temporary adjustment strategies. Do not use when emotional distress needs higher-priority support or when weight-focus should be avoided (history_of_ed / avoid_weight_focus flags)."
metadata:
  openclaw:
    emoji: "mag"
    homepage: https://github.com/NanoRhino/weight-loss-skill
---

# Weight Gain Strategy

Detect upward weight trends and respond with graduated support — from
reassurance on the first increase, to guided cause discovery, to full
diagnosis with adjustment strategies — matching the response depth to how
persistent the trend is.

## Routing Gate

**Entry paths:**
- **Auto (post-weigh-in):** `weight-tracking` calls `deviation-check` after every weight log → severity returned → respond per severity table below.
- **Manual:** User asks about weight gain ("why am I gaining weight", "体重怎么涨了") → skip streak logic → run `analyze` directly → Interactive Flow Step 1.

**Skip — do NOT enter this skill if:**
- No `PLAN.md` exists (no plan to deviate from)
- `USER.md > Health Flags` contains `avoid_weight_focus` or `history_of_ed`
- User shows emotional distress about weight → defer to `emotional-support` (P1 priority)

## Principles

1. **Normalize first.** Weight fluctuations are normal. Never alarm the user — lead with reassurance, then dig into data.
2. **Data + habits before opinions.** Every diagnosis must cite actual numbers from the user's logs OR observable behavioral patterns (e.g., exercise frequency dropping, meal timing shifting, snack patterns emerging). Never speculate without evidence — but evidence includes consistent behavior trends, not just calorie numbers.
3. **Escalate gradually.** Response depth follows the streak — comfort first, then guided discovery, then full analysis. Never skip levels or jump to strategy on a first increase.
4. **Collaborate, don't force.** The user can opt in or out at every step. Playful challenges and teasing are fine; pushing past a "no" is not. Frame adjustments as mutual pacts, not prescriptions.
5. **Keep it light.** You're a witty friend who happens to know nutrition — not a stern doctor reading lab results. Tease gently, celebrate small wins enthusiastically, and never make the user feel like they're being lectured. Keep the data rigorous but the delivery fun.

---

## Severity → Response

| Severity | Streak | Behavior |
|----------|--------|----------|
| `none` | 0 | Weight stable or down — just confirm the log. |
| `comfort` | 1 | Comfort and encourage. Mention temporary causes (yesterday overeating, menstrual cycle, water retention) lightly as reassurance. |
| `cause-check` | 2–3 | Multi-step guided discovery flow — see below. |
| `significant` | 4+ | Run `analyze` → Interactive Flow Step 1 (cause analysis), then Step 2 (strategy) if user agrees. |

**`comfort` examples (streak = 1):**

- **No temporary cause:** "Up a tiny bit from last time — totally normal fluctuation, just keep doing what you're doing!"
- **Yesterday overeating:** "Yesterday's bigger meal shows up on the scale as water, not fat — it'll come back down in a day or two."
- **Menstrual cycle:** "Weight fluctuates 1–2 kg around your period — totally normal, not fat. Check again after it passes."
- **Sudden spike:** "That kind of overnight jump is water/sodium, not fat — don't worry about it."
- **Adaptation period:** "Your body is still adjusting to the new plan — fluctuations in the first couple of weeks are expected, keep going!"

**`cause-check` guided discovery flow (streak = 2–3):**

A multi-turn conversational flow with **push-pull rhythm** — playful teasing,
user opt-in at each step, suspense before the reveal. Run `analyze` silently
at the very start so data is ready, but don't reveal findings until the user
is engaged. Each step waits for the user's response before proceeding.

**Step A: Hook + opt-in** — Open with a playful, light-hearted observation
about the streak. Frame it as a fun investigation, not a problem. Ask if the
user wants to enter "analysis mode" — this gives them a chance to opt in
rather than being ambushed with data.

Examples:
- "Hmm, the scale's been a bit naughty twice in a row. No rush — want to go into analysis mode and figure it out together?"
- "Scale's acting up again — two in a row. Want to play detective with me?"

**Wait for user response.** If the user says no or ignores → drop it (single-
ask rule). If yes → proceed.

**Step B: Let the user guess** — Don't show data yet. Ask the user to guess
the cause first. This surfaces context the data can't capture (stress, social
events, mood) and makes the user an active participant, not a passive
recipient of a report.

Examples:
- "Take a guess first — what do you think is going on?"
- "Before I show my cards — what's your hunch?"

**Wait for user response.** If the user has a guess → validate in Step C.
If the user says "no idea" or shrugs → that's fine, move to Step C and lead
with the data.

**Step C: Data reveal + consequence + motivation** — Structure: **validate
→ data → consequence → motivation**. See `references/diagnosis-templates.md`
for per-factor diagnosis lines, consequence lines, and cause-specific
motivation lines.

**Validation** — If the user guessed in Step B, validate first:
- **Right:** "Spot on! The data backs you up — {data finding}."
- **Partially right:** "That's part of it — data also shows {finding}."
- **Didn't know:** "I dug into the data — {data finding}."

**Special cases — end flow here, skip Step D:**
- **Menstrual cycle:** "Your intake looks fine — timing lines up with your cycle, likely water retention. Let's check again after it passes."
- **Adaptation period with no actionable cause:** "Still early and your body is adjusting — fluctuation is expected."

**Step D flows directly from Step C (same message, no wait).** After the
motivation line, immediately tease the challenge. Do NOT wait for user
response between Step C and Step D — they are one continuous message.

**Tease the challenge:**
- "Want to hear my plan?"
- "I've got a little challenge for you — dare to take it?"

**Wait for user response here.** If they ask what it is or show interest:

**Build suspense (optional, 1 exchange max):**
- "Say yes and you'll find out — it'll be worth it!"
- "Just say yes — I promise you'll like it."

Only use suspense if the user asks "what challenge?" or "what would you do?". If they directly agree,
skip to the reveal. **Never drag suspense beyond 1 extra exchange.**

**Reveal the habit as a pact:** Frame the habit as a mutual commitment, not a
one-sided instruction. The AI is committing to something too (stricter
monitoring, closer attention, daily check-ins).

Structure: **"I will do X" + "you do Y"**

Examples by cause:

| Detected cause | AI commits to | User commits to | Example |
|---------------|--------------|----------------|---------|
| **Snacking / calorie surplus** | Tighter meal review, flag when close to target | Log every meal, swap the specific snack | "I'm going to keep a closer eye on your meals from now on — and you? Tell me everything you eat, and swap those afternoon chips for yogurt. One week, deal?" |
| **Weekend overeating** | Weekend meal check-in reminder | Photo-log weekend meals | "I'll check in on weekends to see what you ate — just snap a photo for me. No need to restrict, just let me see it." |
| **Exercise decline** | Exercise check-in mid-week | Restore one specific session | "I'll check in Wednesday to see if you ran — just add that one session back. That's it, just the one." |
| **Late-night eating** | Evening check-in before kitchen-closes time | Move last meal earlier | "I'll ping you at 8 PM to ask if you're done eating — try to wrap up dinner before 8. Sound fair?" |
| **Logging gaps** | Daily meal-log reminder, gentler tone | Log one specific meal daily | "From now on, tell me everything you eat — start with lunch and dinner, just a photo is fine!" |
| **Calorie creep** | Calorie summary after each meal log | Slightly smaller portion of one staple | "I'll tally up your calories after every log — you just take slightly less rice at dinner. Deal?" |

**Key rules for the pact:**
- **AI side is real.** The commitment from the AI side (stricter monitoring,
  check-ins, daily review) must actually be followed through. If promising
  "closer eye on your meals", subsequent meal logs should get more detailed calorie feedback.
  Coordinate with `notification-composer` for any check-in reminders.
- **Mutual, not one-sided.** The user shouldn't feel like they're the only one
  making an effort. The AI is stepping up too.
- **Playful accountability.** The tone is "we're in this together" with a
  dash of playful strictness — like a coach who teases you but clearly cares.

**After user agrees** → run `save-strategy` to persist. Close with a short,
cheeky confirmation:
- "Deal! Don't say I didn't warn you 😏"
- "Alright, you're on my watch list this week 👀"

**If the user says no, ignores, or changes topic** → drop it. Single-ask rule
applies at each step.

---

## Data Sources

### Reads

| Path | Via | Purpose |
|------|-----|---------|
| `data/weight.json` | `weight-tracker.py load` | Weight trend (last 14–28 days) |
| `data/meals/YYYY-MM-DD.json` | `nutrition-calc.py load` | Daily calorie intake for the analysis window |
| `data/exercise.json` | `exercise-calc.py load` | Exercise frequency, duration, and calories burned |
| `PLAN.md` | Direct read | Calorie target, weekly loss rate |
| `health-profile.md` | Direct read | Activity level, meal schedule, unit preference |
| `health-preferences.md` | Direct read | Known preferences and constraints |
| `USER.md` | Direct read | Name, age, sex (for context) |
| `timezone.json` | Direct read | Timezone offset for date calculations |
| `engagement.json` | Direct read | Engagement stage |

### Writes

| Path | When |
|------|------|
| `data/weight-gain-strategy.json` | After the user confirms a strategy — stores the active strategy with start date, end date, type, and parameters |
| `health-preferences.md` | If the user reveals new preferences during the conversation (append only) |

---

## Analysis Script

Script path: `python3 {baseDir}/scripts/analyze-weight-trend.py`

Commands: `analyze`, `deviation-check`, `save-strategy`, `check-strategy`.
See `references/script-api.md` for full usage, parameters, and return schemas.

---

## Interactive Flow

Used by `significant` (streak 4+) and manual trigger paths.

### Step 1: Analyze & Present Causes

1. Read `timezone.json` → run `analyze`
2. Present: **[Reassurance]** → **[Trend summary]** → **[Diagnosis]**
   - Reassurance: one playful sentence normalizing fluctuation. Never open with bad news.
   - Trend: "Over the past {N} days, your weight wandered from {start} to {end} — that's {change}."
   - Diagnosis: use per-factor templates from `references/diagnosis-templates.md`.
3. Pause — do NOT continue to Step 2 automatically.
4. Transition: "Want to brainstorm a tweak or two?"

If `normal_fluctuation` → reassuring close, no Step 2.
Only proceed to Step 2 when the user explicitly agrees. If ignored → drop it.

### Step 2: Discuss & Choose Strategy

Present 1–3 strategy options based on the `suggested_strategies` from the analysis.

**Strategy ranking rule:** Sort options by ease-of-execution for this specific user, not by theoretical effectiveness. Cross-reference `health-profile.md` (activity level, preferences) and `health-preferences.md` to determine what the user is already good at or enjoys. Put the lowest-friction option first. Examples:
- User exercises regularly → lead with "add one more session" rather than "cut calories"
- User enjoys cooking → lead with "swap this ingredient" rather than "eat less"
- User is sedentary but has been logging meals diligently → lead with a small calorie tweak they can track easily
- User's exercise dropped recently but they used to be active → lead with "get back to your old routine" (reactivation is easier than starting fresh)

For each option:

**Format:**

```
Option {N}: {strategy_name}
{one-sentence description}
{expected_impact} over {duration}
```

**Strategy Types:**

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

**After presenting options:** Ask the user which feels most doable — keep the tone light: "Which one sounds the least like torture?" Respect their choice. If they choose something suboptimal, support it enthusiastically — compliance beats optimization every time.

### Step 3: Confirm & Save Strategy

1. Confirm the chosen strategy with specific, actionable details:
   - What exactly changes (calorie target, number of sessions, specific meals)
   - For how long (start date → end date)
   - When to check in (midpoint and end)
2. Run `save-strategy` to persist the strategy
3. Close with encouragement — brief, genuine, a bit cheeky. No hollow platitudes like "you've got this!" — instead, something specific and fun: "Let's see what the scale says next week — I'm betting on you."

**Do NOT:**
- Set up reminders here (that's `notification-manager`'s job)
- Modify PLAN.md (the strategy is temporary; PLAN.md is the long-term plan)
- Generate HTML reports

---

## Safety Rules

- **Calorie floor:** Never suggest intake below max(BMR, 1000 kcal/day). Read the floor from PLAN.md or recalculate via `planner-calc.py`.
- **Exercise safety:** For users who are sedentary or have health conditions noted in `USER.md`, start with walking and low-impact activities only.
- **Emotional awareness:** If the user shows signs of distress about the weight gain, defer to `emotional-support` per SKILL-ROUTING.md. Come back to strategy only when the user is ready.
- **No shame, no blame.** Never imply the weight gain is the user's fault. Frame adjustments as experiments, not corrections.
- **ED flags:** If `USER.md > Health Flags` contains `avoid_weight_focus` or `history_of_ed`, do NOT run this skill automatically. Only respond if the user explicitly asks, and focus on behaviors (activity, sleep, stress) rather than weight numbers.

---

## Strategy Data Schema

**File:** `data/weight-gain-strategy.json`

```json
{
  "active_strategy": {
    "type": "reduce_calories",
    "start_date": "2026-03-24",
    "end_date": "2026-03-31",
    "params": {
      "target_kcal": 1450,
      "original_target_kcal": 1600,
      "reduction_kcal": 150
    },
    "status": "active",
    "created_at": "2026-03-24T10:00:00+08:00"
  },
  "history": [
    {
      "type": "increase_exercise",
      "start_date": "2026-03-10",
      "end_date": "2026-03-17",
      "params": {
        "target_sessions": 3,
        "target_minutes_per_session": 30
      },
      "status": "completed",
      "outcome": "weight stabilized"
    }
  ]
}
```

---

## Integration with Other Skills

| Skill | Integration |
|-------|-------------|
| `weekly-report` | Reads `check-strategy` output to report on active strategy progress. |
| `notification-composer` | Reads `check-strategy` output to optionally include mid-week strategy check-in reminders. |
| `weight-tracking` | Source of weight data. This skill reads only — never writes to `data/weight.json`. |
| `diet-tracking-analysis` | Source of meal data. This skill reads only — never writes to `data/meals/`. |
| `exercise-tracking-planning` | Source of exercise data. This skill reads only — never writes to `data/exercise.json`. |
| `emotional-support` | Takes priority (P1) when user shows distress about weight gain. This skill defers. |
| `weight-loss-planner` | Owns PLAN.md. This skill reads the plan but never modifies it. Strategies are temporary overlays. |

---

## Skill Routing

**Priority Tier: P3 (Planning)** — same tier as `weight-loss-planner` and `meal-planner`.

### Conflict Patterns

**Weight gain strategy + Emotional distress (P3 vs P1):**
Emotional support leads. If user says "I'm gaining weight and I hate myself",
`emotional-support` takes over. Weight gain analysis happens later, only if
the user asks for it.

**Weight gain strategy + Diet logging (P3 vs P2):**
If the user logs food AND asks about weight gain in the same message, log the
food first (P2), then provide the weight gain analysis.

**Weight gain strategy + Weight-loss planner (same tier):**
If the user asks to redo their plan because of weight gain, route to
`weight-loss-planner` for a full recalculation. This skill handles
short-term tactical adjustments only; replanning is a different skill's job.

---

## Edge Cases

**Insufficient data (< 3 weight readings in 14 days):**
Cannot diagnose reliably. Respond with: "I don't have enough weight data to
spot a clear trend — try weighing in 1–2 times per week and we'll have a
better picture soon."

**No meal logs:**
Skip calorie surplus analysis. Note the gap: "Without meal logs, I can't
check if calorie intake is a factor. Want to start logging meals?"

**User is in first 2 weeks of plan (adaptation period):**
Weight fluctuation is expected at the start. The `deviation-check` will return
`adaptation_period: true` — add "body is still adjusting" context to whatever
severity level applies. At `comfort`, this is the primary message. At
`cause-check`, early-exit at Step C with reassurance if no actionable cause.
If the user explicitly asks for changes, gently recommend waiting: "Your body
is still adjusting — let's give it another week and the picture will be
clearer."

**Weight gain is muscle gain (exercise increased significantly):**
If exercise volume increased significantly while weight went up, note the
possibility: "You've been exercising more — some of this could be muscle.
How do your clothes fit? That's often a better indicator than the scale."

**Active strategy already exists:**
If a strategy is already active and the user asks again, show progress on
the current strategy first. Only propose a new strategy if the current one
has ended or the user explicitly wants to change.
