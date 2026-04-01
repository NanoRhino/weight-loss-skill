# Habit Lifecycle

## Active tracking

Once accepted, write to `habits.active`:

```json
{
  "habit_id": "walk-after-dinner",
  "description": "Walk for 5 minutes after dinner",
  "tiny_version": "Put on shoes and step outside after dinner",
  "trigger": "After finishing dinner",
  "type": "post-meal",
  "bound_to_meal": "dinner",
  "created_at": "2026-02-27",
  "phase": "week-1",
  "source": "habit-builder",
  "strict": false,
  "mention_log": [],
  "completion_log": []
}
```

`source` can be `"habit-builder"` (normal) or `"weight-gain-strategy"` (from
cause-check pact). `strict: true` means tighter monitoring — see
`weight-gain-strategy` references for details.

## Tracking completion

| User signal | Record as |
|-------------|-----------|
| Confirms done ("yeah, walked", "did it", "✓") | `completed` |
| Did partial ("only 2 minutes") | `completed` — did it = did it |
| Says they didn't ("forgot", "skipped") | `missed` |
| Doesn't engage with the mention | `no_response` |
| Mentions doing it unprompted | `completed` + `self_initiated: true` |

Write to `habits.daily_log.{date}`.

## Positive feedback

- Praise the behavior, not the person. "That walk is becoming a thing" not "You're so disciplined!"
- Don't praise every time. ~1 in 3-4 completions gets a real comment. Rest just get "✓".
- Never mention streak counts.

| Situation | Feedback |
|-----------|----------|
| Regular completion | "✓" or "Nice." |
| Several days in a row | "The walk's becoming your thing." |
| User exceeded the tiny version | "15 minutes?! Who are you 😄" |
| First unprompted | "You didn't even need me — that's the whole point." |
| When user says "only did a little" | "Still counts." |

## Graduation

**Required:** Completion rate ≥ 80% over 14 days.
**Plus at least one of:**
- Self-initiation in > 30% of completions
- User confirms they don't need reminders anymore

On graduation: celebrate lightly, move to `habits.graduated`, stop active
tracking. Occasionally check in via Weekly Review.

## Failure and restart

**Detection:** 3 consecutive `missed` or `no_response`.

Surface gently at next natural moment:
`"The walking thing's been on pause. Want to keep it, make it easier, or try something different?"`

| Choice | Action |
|--------|--------|
| Keep going | Reset tracking. "Fresh start, no catch-up." |
| Make it easier | Shrink further. "5 min → how about just stepping outside?" |
| Try something different | Back to recommendation flow. |

**Never say:** "You failed" / "You broke your streak" / "Don't give up" /
"You were doing so well" / "No pressure"

**Weight-gain pact habits** (`source: "weight-gain-strategy"`): failure and escalation are owned by `weight-gain-habits` — see that skill's SKILL.md § Failure + Escalation.

## Scaling up

After graduation:
1. **Upgrade (optional):** "Want to extend the walk, or is 5 min your sweet spot?"
2. **Next habit:** wait a few days, then back to recommendation flow.

## Concurrent habits

| Situation | Response |
|-----------|----------|
| 1 active, going well, wants another | Allow — 2 concurrent is fine |
| 2 active, wants a third | Check rates. Both > 70% → allow. Either struggling → stabilize first. |
| 3+ active, rates dropping | "You've got a lot going — want to pause one?" |
