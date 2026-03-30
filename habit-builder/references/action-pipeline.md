# Advice-to-Action Pipeline

Turns advice from any skill into a queue of tiny, trackable actions.
Activate when advice implies sustained behavior change (not one-off facts).

## Step 1: Decompose

≤ 5 independent actions. Each = one trigger + one behavior. Must pass Tiny Habits test ("can they do this on their worst day?").

## Step 2: Prioritize

Run `prioritize`. Present top one casually, ask if user wants 1-2 more (max 3 concurrent, different time slots).

## Step 3: Activate

Run `activate`. Maps `trigger_cadence` → `type` for notification-composer. Update `habits.action_queue` status to `active`.

## Step 4: Follow-up

Run `schedule` or `should-mention`. Habits surface in meal conversations.
- **Weekly:** relevant day only, first meal conversation.
- **Conditional:** reactive only — mention when user's message matches the condition.

## Step 5: Graduation

Same as lifecycle graduation (see `lifecycle.md`). On graduation, introduce next queued action immediately. Exception: emotionally taxing → wait for Weekly Review. Max tracking: 90 days.

## Step 6: Queue Management

| Event | Action |
|-------|--------|
| Graduation | Advance next (fill freed slots, cap 3) |
| Failure (3 misses) | Offer: keep / shrink / swap / skip |
| User skips | Move to end of queue |
| User stops all | Pause entire queue |
| New advice | Append (don't jump line) |

Data structure and script syntax: see `script-reference.md`.
