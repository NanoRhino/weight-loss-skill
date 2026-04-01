---
name: diet-pattern-detection
version: 1.0.0
description: "One-time diet pattern analysis. Runs via daily cron after onboarding, checks if user's actual eating pattern matches a different diet mode. Self-destructs after successful execution. NOT user-triggered — cron-only."
metadata:
  openclaw:
    emoji: "bar_chart"
    homepage: https://github.com/NanoRhino/weight-loss-skill
---

# Diet Pattern Detection

> ⚠️ **Cron-only skill.** Never triggered by user messages. Activated by a daily cron job created by `notification-manager` at onboarding completion.

## Trigger

Daily cron job. Start date: `Onboarding Completed` + 3 days (from `health-profile.md > Automation`). Cron time: dinner_time + 3h.

## Workflow

1. **Check precondition** — read `health-profile.md > Automation > Pattern Detection Completed`. If already has a date → skip (should not happen, but defensive).

2. **Count logged days** — load past 7 days of meal data:
   ```bash
   python3 {diet-tracking-analysis:baseDir}/scripts/nutrition-calc.py load \
     --data-dir {workspaceDir}/data/meals --date <YYYY-MM-DD>
   ```
   Count days with ≥1 meal. If < 3 → reply with no output (insufficient data, cron preserved, retry tomorrow).

3. **Run detection**:
   ```bash
   python3 {diet-tracking-analysis:baseDir}/scripts/nutrition-calc.py detect-diet-pattern \
     --data-dir {workspaceDir}/data/meals \
     --current-mode <from health-profile.md > Diet Config > Diet Mode>
   ```

4. **Handle result**:
   - `has_pattern: true` → read `references/diet-pattern-response.md`, compose and send message to user. If user agrees to switch → update `health-profile.md > Diet Config > Diet Mode` and recalculate targets.
   - `has_pattern: false` → no message (pattern matches current mode, all good).
   - `reason: "insufficient_data"` → no action, cron preserved, retry tomorrow.

5. **Self-destruct** (when result is `has_pattern` true or false, NOT insufficient_data):
   1. List current agent's cron jobs (`cron list`)
   2. Find job with name containing "diet-pattern" or "Diet pattern"
   3. Delete it (`cron remove`)
   4. Write completion date to `health-profile.md > Automation > Pattern Detection Completed: <YYYY-MM-DD>`

## Reference Files

- `references/diet-pattern-response.md` — user notification template (when pattern detected)
