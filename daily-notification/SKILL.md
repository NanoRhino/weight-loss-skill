---
name: daily-notification
version: 0.0.0
description: "DEPRECATED redirect — this skill no longer contains any logic. It exists only so that legacy cron jobs whose --message references 'daily-notification' can still be routed. On activation, immediately hand off to notification-composer for the actual reminder, then trigger notification-manager auto-sync to replace the legacy cron jobs. Remove this skill once all legacy cron jobs have been migrated."
metadata:
  openclaw:
    emoji: "arrow_right"
    homepage: https://github.com/NanoRhino/weight-loss-skill
---

# Daily Notification (Deprecated Redirect)

> **This skill is a temporary migration shim.** Delete it once all legacy cron
> jobs have been replaced by `notification-manager` auto-sync.

## What to do when this skill is activated

1. You received a cron trigger whose `--message` references `daily-notification`.
2. **Do NOT attempt any logic here.** Hand off the entire message to
   `notification-composer` — treat the message as if it said
   `notification-composer` instead of `daily-notification`.
3. After `notification-composer` finishes (whether it sent a reminder or
   responded `NO_REPLY`), activate `notification-manager` so its auto-sync
   replaces all legacy cron jobs with ones that reference `notification-composer`.

That's it. This skill does nothing else.
