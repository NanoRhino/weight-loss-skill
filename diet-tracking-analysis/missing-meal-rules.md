# Missing Meal Rules

`log-meal` auto-detects missing meals — **never ask the user about them**.

- When `missing_meals.has_missing = true`: append a PS after the reply, saying which meal(s) were assumed normal and inviting corrections
- Assumed meals are for suggestion calculation only — never show in progress display

## User Corrections

- **Skipped** → mark zero intake, re-run `query-day`
- **Can't recall** → keep assumed value, don't ask further
- Backfilled meals are always "already eaten" — never use `right_now` suggestion type
