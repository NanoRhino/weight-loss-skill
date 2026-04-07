# AI Preferences Template

> Reference template for `ai-preferences.md`. Created during onboarding with
> default values. Updated by `user-onboarding-profile` when the user requests
> changes, or by `notification-composer` when processing guided-feedback replies.
>
> **All skills read this file** to adjust their output style. Only the owning
> skills listed above may write to it.

```markdown
# AI Preferences

**Created:** [ISO-8601 timestamp]
**Updated:** [ISO-8601 timestamp]

## Coaching Style
- **Strictness:** moderate
- **Tone:** warm-friend
- **Detail Level:** standard
- **Encouragement Frequency:** normal
- **Advice Style:** action-only

## Content Control
- **Calorie Display:** always
- **Macro Breakdown:** always
- **Unsolicited Advice:** welcome
- **Comparison with Plan:** daily-summary

## Reminder Settings
- **Reminder Lead Time:** 15min
- **Reminder Repeat:** false
- **Reminder Max Repeats:** 0
- **Reminder Content:** recommend

## Interaction Preferences
- **Proactive Check-ins:** all
- **Check-in Topics:** [sleep, hunger, mood, menstrual]
- **Response Length:** medium

## Boundaries
- **Off-limit Topics:** None
- **Sensitive Periods:** None
```

## Field Reference

### Coaching Style

| Field | Values | Default | Effect |
|-------|--------|---------|--------|
| Strictness | relaxed, moderate, strict, drill-sergeant | moderate | How aggressively AI flags deviations from plan |
| Tone | warm-friend, professional, tough-love, playful | warm-friend | Overall communication style |
| Detail Level | minimal, standard, detailed | standard | How much explanation accompanies feedback |
| Encouragement Frequency | less, normal, more | normal | How often AI adds positive reinforcement |
| Advice Style | action-only, with-reasoning, with-consequences | action-only | How much context accompanies suggestions. `action-only` = just say what to do; `with-reasoning` = explain why; `with-consequences` = also describe what happens if you don't adjust |

### Content Control

| Field | Values | Default | Effect |
|-------|--------|---------|--------|
| Calorie Display | always, on-request, never | always | Whether calorie numbers appear in meal feedback |
| Macro Breakdown | always, on-request, never | always | Whether P/C/F breakdown appears in meal feedback |
| Unsolicited Advice | welcome, minimal, none | welcome | Whether AI proactively offers suggestions |
| Comparison with Plan | every-meal, daily-summary, weekly-only | daily-summary | How often AI compares intake vs plan |

### Reminder Settings

| Field | Values | Default | Effect |
|-------|--------|---------|--------|
| Reminder Lead Time | 15min, 30min, 60min | 15min | How far before meal time the reminder fires |
| Reminder Repeat | true, false | false | Whether additional reminders fire if no reply |
| Reminder Max Repeats | 0, 1, 2 | 0 | How many additional reminders (only when Repeat is true) |
| Reminder Content | recommend, brief, motivational | recommend | Style of reminder message |

### Interaction Preferences

| Field | Values | Default | Effect |
|-------|--------|---------|--------|
| Proactive Check-ins | all, selective, minimal, off | all | Master switch for wellness check-ins |
| Check-in Topics | list of: sleep, hunger, mood, menstrual | all | Which topics AI may proactively ask about |
| Response Length | short, medium, long | medium | Target length of AI replies |

### Boundaries

| Field | Values | Default | Effect |
|-------|--------|---------|--------|
| Off-limit Topics | free-text list | None | Topics AI should never raise |
| Sensitive Periods | free-text list | None | Time-based rules (e.g. "workday mornings no weight talk") |
