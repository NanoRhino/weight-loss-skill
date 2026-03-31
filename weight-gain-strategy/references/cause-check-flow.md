# cause-check Guided Discovery Flow (streak 2–3)

A multi-turn conversational flow with **push-pull rhythm** — playful teasing,
user opt-in at each step, suspense before the reveal. Run `analyze` silently
at the very start so data is ready, but don't reveal findings until the user
is engaged. Each step waits for the user's response before proceeding.

## Step A: Hook + opt-in

Open with a playful, light-hearted observation about the streak. Frame it as
entering **"减重分析模式"** — a special mode name that makes the investigation
feel structured and fun, not scary. Ask if the user wants to enter this mode
to give them a chance to opt in.

Examples:
- "唔，这两次秤有点不太乖哦。先别急，让我们一起来看看是怎么回事。进入减重分析模式吗？"
- "Hmm, scale's been naughty twice in a row. No rush — want to enter weight-loss analysis mode and figure it out together?"
- "连着两次往上走了。想开启减重分析模式，一起当回侦探吗？"

**Wait for user response.** If the user says no or ignores → drop it (single-
ask rule). If yes → proceed.

## Step B: Let the user guess

Don't show data yet. Ask the user to guess the cause first. This surfaces
context the data can't capture (stress, social events, mood) and makes the
user an active participant, not a passive recipient of a report.

Examples:
- "Take a guess first — what do you think is going on?"
- "Before I show my cards — what's your hunch?"

**Wait for user response.** If the user has a guess → validate in Step C.
If the user says "no idea" or shrugs → that's fine, move to Step C and lead
with the data.

## Step C: Data reveal + consequence + motivation

Structure: **validate → data → consequence → motivation**. See
`references/diagnosis-templates.md` for per-factor diagnosis lines,
consequence lines, and cause-specific motivation lines.

**Validation** — If the user guessed in Step B, validate first:
- **Right:** "Spot on! The data backs you up — {data finding}."
- **Partially right:** "That's part of it — data also shows {finding}."
- **Didn't know:** "I dug into the data — {data finding}."

**Special cases — end flow here, skip Step D:**
- **Menstrual cycle:** "Your intake looks fine — timing lines up with your cycle, likely water retention. Let's check again after it passes."
- **Adaptation period with no actionable cause:** "Still early and your body is adjusting — fluctuation is expected."

## Step D: Challenge + suspense → reveal pact

Step D flows directly from Step C (same message, no wait). After the
motivation line, immediately tease the challenge. Do NOT wait for user
response between Step C and Step D — they are one continuous message.

**Tease the challenge:**
- "Want to hear my plan?"
- "I've got a little challenge for you — dare to take it?"

**Wait for user response.** If yes → reveal the pact immediately.

**Reveal the habit as a pact:** Frame the habit as a mutual commitment, not a
one-sided instruction. The AI is committing to something too (stricter
monitoring, closer attention, daily check-ins).

Structure: **"I will do X" + "you do Y"**

### Pact examples by cause

| Detected cause | AI commits to | User commits to | Example |
|---------------|--------------|----------------|---------|
| **Snacking / calorie surplus** | Tighter meal review, flag when close to target | Log every meal, swap the specific snack | "I'm going to keep a closer eye on your meals from now on — and you? Tell me everything you eat, and swap those afternoon chips for yogurt. One week, deal?" |
| **Weekend overeating** | Weekend meal check-in reminder | Photo-log weekend meals | "I'll check in on weekends to see what you ate — just snap a photo for me. No need to restrict, just let me see it." |
| **Exercise decline** | Exercise check-in mid-week | Restore one specific session | "I'll check in Wednesday to see if you ran — just add that one session back. That's it, just the one." |
| **Late-night eating** | Evening check-in before kitchen-closes time | Move last meal earlier | "I'll ping you at 8 PM to ask if you're done eating — try to wrap up dinner before 8. Sound fair?" |
| **Logging gaps** | Daily meal-log reminder, gentler tone | Log one specific meal daily | "From now on, tell me everything you eat — start with lunch and dinner, just a photo is fine!" |
| **Calorie creep** | Calorie summary after each meal log | Slightly smaller portion of one staple | "I'll tally up your calories after every log — you just take slightly less rice at dinner. Deal?" |

### Pact rules

- **AI side is real.** The commitment from the AI side (stricter monitoring,
  check-ins, daily review) must actually be followed through. If promising
  "closer eye on your meals", subsequent meal logs should get more detailed
  calorie feedback. Coordinate with `notification-composer` for check-in
  reminders.
- **Mutual, not one-sided.** The user shouldn't feel like they're the only one
  making an effort. The AI is stepping up too.
- **Playful accountability.** The tone is "we're in this together" with a
  dash of playful strictness — like a coach who teases you but clearly cares.

### After user agrees

1. **Create a habit in `habits.active`** via `habit-builder` — the pact becomes
   a tracked habit with the standard lifecycle (week-1 phase = check-in every
   2 days, woven into meal conversations by notification-composer). Map the
   pact to habit-builder's schema:
   - `habit_id`: derive from cause (e.g., `"swap-afternoon-snack"`, `"log-meals"`, `"restore-wed-run"`)
   - `description`: the user's side of the pact
   - `tiny_version`: the smallest version of the commitment
   - `trigger`: the meal or time it's bound to
   - `type`: `"post-meal"` / `"end-of-day"` / `"all-day"` depending on cause
   - `phase`: `"week-1"` (starts with highest check-in frequency)
   - `source`: `"weight-gain-strategy"` (so weekly-report knows it came from a cause-check pact)

2. **Run `save-strategy`** to persist strategy metadata (type, params, dates).
   This is for `check-strategy` / `weekly-report` only — `habits.active` is
   the source of truth for daily execution and tracking.

3. **Strict mode** — when the cause includes `logging_gaps` AND `calorie_surplus`
   or `calorie_creep`, mark the habit with `strict: true`. See
   `references/strict-mode.md` for full behavior rules, duration, and failure
   escalation.

4. Close with a short, cheeky confirmation:
   - "Deal! Don't say I didn't warn you 😏"
   - "Alright, you're on my watch list this week 👀"

If the user says no, ignores, or changes topic → drop it. Single-ask rule
applies at each step.
