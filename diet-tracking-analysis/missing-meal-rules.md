# Missing Meal Rules

## Behavior

- **Never stop to ask** about skipped/missing meals — `log-meal` auto-detects and handles them
- After the current meal's ① ② ③ reply, **append a PS note** if `missing_meals.has_missing = true`: tell the user which meal(s) were assumed as normal intake, and invite them to share what they actually had for more accurate advice.
- Assumed meals affect suggestion calculation only — **never shown in progress display** (② only shows real recorded values)

## Handling User Responses (After-the-Fact)

| User response | Action |
|---------------|--------|
| Describes food | Log as that meal type via `log-meal`, suggestions auto-update |
| "Didn't eat" / "Skipped" | Mark as skipped (zero intake), re-run `query-day` to update |
| "Ate but can't recall" | Keep assumed value as-is |

**Backfilled meals** are always "already eaten" — use `next_meal` or `next_time` suggestion type, never `right_now`.
