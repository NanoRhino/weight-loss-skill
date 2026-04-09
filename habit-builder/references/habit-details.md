# Habit Builder — Reference Details

## Tiny-fy Examples

| User's goal | Tiny version |
|-------------|-------------|
| "Exercise every day" | "Put on shoes and walk outside 2 min after dinner" |
| "Drink 8 glasses of water" | "One glass right after waking up" |
| "Eat more protein" | "Add one protein item to lunch" |
| "Stop snacking at night" | "Move snacks from desk to high cabinet" |
| "Sleep earlier" | "Phone alarm at 10:30 PM labeled 'wind down'" |

## Positive Feedback Examples

| Situation | Response |
|-----------|----------|
| Regular completion | `"✓"` or `"Nice."` |
| Several days in a row | `"The walk's becoming your thing. Love it."` |
| User exceeded tiny version | `"15 minutes?! Who are you 😄 ✓"` |
| First unprompted | `"You didn't even need me — that's the whole point."` |
| Stabilized | `"This one's on autopilot now."` |
| "Only did a little" | `"Still counts."` |

## Failure Restart Examples

| Choice | Response |
|--------|----------|
| Keep going | `"Cool — fresh start, no catch-up."` |
| Make easier | `"5 min → how about just stepping outside? No walk required."` |
| Try different | Go back to recommendation flow. |

## Blacklisted Phrases

Never say: `"You failed"` · `"You broke your streak"` · `"Don't give up"` ·
`"You were doing so well"` · `"Remember your goals"` · `"No pressure"` ·
`"不用有压力"`

## User Query Response Examples

| User asks | Response |
|-----------|----------|
| "What habits do I have?" | `"Right now you're working on the after-dinner walk. You've already graduated the morning water one — that's all you now."` |
| "How am I doing?" | `"The walk's going well — pretty consistent this week."` or `"Slow week for the walk. Want to adjust it?"` |
| "Can I change my habit?" | Offer keep/shrink/swap. |
| "I want to stop tracking" | `"Done — no more habit check-ins. Let me know if you ever want to pick it back up."` Move all active to paused. |

## Check-in Frequency

| Phase | Frequency |
|-------|-----------|
| Week 1 | Every 2 days |
| Week 2-3 | Every 3-4 days |
| Week 3+ | ~Once/week |

`strict: true` habits (from weight-gain-strategy): week-1 frequency for 2 weeks.
See `weight-gain-strategy/references/strict-mode.md` for full strict-mode rules.

## Habit Types — Full Table

| Type | When to mention | Example |
|------|----------------|---------|
| Meal-bound | Built into the meal reminder | `"Lunch time — protein first today?"` |
| Post-meal | User replies to meal check-in | `"Nice. Going for a walk after?"` |
| End-of-day | Last meal conversation of the day | `"Try to wrap up by 11 tonight?"` |
| Next-morning recovery | Next day's first conversation | `"Morning! Did you make it to bed by 11?"` |
| All-day | Random meal conversation | `"How's the water going today?"` |
| Weekly | Relevant day, first meal conversation | `"Today's meal-prep day — got a plan?"` |
| Conditional | When condition detected in conversation | `"Outside today — go for the lighter option?"` |

## Lifestyle Gap Dimensions

| Dimension | What to check | Example gap |
|-----------|--------------|-------------|
| Meal rhythm | Regular? Skipping? Late eating? | Dinner at 9 PM, snacks until midnight |
| Food quality | Protein? Vegetables? Processed? | Very low protein, high sugar |
| Movement | Any physical activity? | Completely sedentary |
| Hydration | Water or sugary drinks? | Mostly soda and milk tea |
| Sleep | Late sleeper? Eating before bed? | Sleeps at 1 AM, snacks in bed |
