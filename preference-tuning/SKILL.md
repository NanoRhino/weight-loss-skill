---
name: preference-tuning
version: 1.0.0
description: >
  Proactive preference discovery and tuning for new users. During the first week,
  appends short nudges to scheduled reminders asking about reminder timing,
  supervision intensity, and open feedback. Also handles explicit preference
  change requests at any time (e.g., "提醒早一点", "别管那么严").
  Use this skill when: a user expresses a preference change about reminder timing
  or supervision style, or when notification-composer detects a pending nudge
  during Week 1.
metadata:
  openclaw:
    emoji: "wrench"
    homepage: https://github.com/NanoRhino/weight-loss-skill
---

# Preference Tuning

> **SILENT OPERATION:** Never narrate internal actions, skill transitions, or tool calls to the user. No "Let me check...", "Now I'll transition to...", "Reading your profile...". Just do it silently and respond with the result.

Proactive preference discovery for new users plus anytime preference changes.
The system has sensible defaults, but they don't fit everyone. This skill
surfaces key defaults during the first week and lets users adjust them.

---

## Data File: `data/preference-tuning.json`

**Owner: this skill.** Other skills read; only this skill writes.

### Schema

```json
{
  "onboarding_start": "YYYY-MM-DD",
  "phase": "week1 | settled",
  "nudges": [
    {
      "topic": "reminder_offset | supervision_level | open_feedback",
      "scheduled_day": 2,
      "sent_date": null,
      "status": "pending | sent_awaiting_reply | answered | sent_no_reply"
    }
  ],
  "defaults": {
    "reminder_offset_min": 15,
    "supervision_level": "moderate"
  },
  "user_changes": []
}
```

### Initialization

When `data/preference-tuning.json` does not exist and the user has completed
onboarding (`health-profile.md` exists), create it with:

```json
{
  "onboarding_start": "<today YYYY-MM-DD>",
  "phase": "week1",
  "nudges": [
    {
      "topic": "reminder_offset",
      "scheduled_day": 2,
      "sent_date": null,
      "status": "pending"
    },
    {
      "topic": "supervision_level",
      "scheduled_day": 3,
      "sent_date": null,
      "status": "pending"
    },
    {
      "topic": "open_feedback",
      "scheduled_day": 4,
      "sent_date": null,
      "status": "pending"
    }
  ],
  "defaults": {
    "reminder_offset_min": 15,
    "supervision_level": "moderate"
  },
  "user_changes": []
}
```

### Phase Transitions

- **`week1`**: Nudges are active. `notification-composer` checks for pending
  nudges and appends them to the first meal reminder of the day.
- **`settled`**: No more proactive nudges. Transition when all nudges have
  been sent (regardless of whether the user replied). Users can still change
  preferences at any time via natural language.

After the last nudge is sent and 1 day has passed, set `phase` to `settled`.

---

## Nudge Schedule

| Day | Topic | Trigger | Content |
|-----|-------|---------|---------|
| **Day 2** | `reminder_offset` | First meal reminder of the day | Ask if reminder timing is right; offer 1h / 30min / 5min / custom |
| **Day 3** | `supervision_level` | First check-in (meal log) of the day | Ask about supervision intensity: strict / moderate / relaxed |
| **Day 4** | `open_feedback` | First meal reminder of the day | Tell user they can give feedback anytime |

"Day N" means N calendar days after `onboarding_start` (inclusive: Day 1 =
onboarding_start itself).

### Nudge Delivery Rules

1. **One nudge per day, max.** Never stack multiple nudges.
2. **Append, don't replace.** The nudge is appended after the normal reminder
   content, separated by `---`.
3. **First slot only.** Attach to the first meal reminder (Day 2, Day 4) or
   first check-in response (Day 3) of that day. Not repeated later in the day.
4. **No-reply = move on.** If the user doesn't reply to a nudge by the next
   day, mark it `sent_no_reply` and proceed to the next scheduled nudge.
   Never re-ask. This follows the global Single-Ask Rule.
5. **Nudge text is warm and brief.** Use `---` separator. End with
   "not replying = keep current default" sentiment.

---

## Nudge Templates

### Day 2 — Reminder Timing (`reminder_offset`)

Appended to the first meal reminder:

```
---
💡 现在的提醒是在每餐前 15 分钟发给你。你觉得这个时间合适吗？也可以改成：
- 餐前 1 小时 — 留出买菜做饭的时间
- 餐前 30 分钟 — 提前准备一下
- 餐前 5 分钟 — 快到了再提醒

也可以直接告诉我你想要的具体时间，比如「提前 20 分钟」。不说的话就保持 15 分钟～
```

English variant:
```
---
💡 Right now I remind you 15 minutes before each meal. Does that timing work? You can also switch to:
- 1 hour before — time to shop and cook
- 30 minutes before — a little prep time
- 5 minutes before — just a quick heads-up

Or tell me any specific time, like "20 minutes before." No reply = keep 15 min~
```

### Day 3 — Supervision Intensity (`supervision_level`)

Appended to the first check-in response (when user logs a meal):

```
---
💡 顺便问一下，你觉得我对热量的管控力度合适吗？
- **严格一点** — 吃超了会提醒你调整，帮你把每餐都控在目标内
- **现在这样就好** — 正常反馈，超了会说但不会太紧张
- **轻松一点** — 偶尔吃多不用在意，看周维度的趋势就好

跟我说一声就行，不说就保持现在这样～
```

English variant:
```
---
💡 Quick question — how strict should I be about calories?
- **Stricter** — flag overages and suggest adjustments to keep each meal on target
- **Keep as is** — note when you're over but no big deal
- **More relaxed** — occasional overages are fine, focus on weekly trends

Just let me know. No reply = keep current~
```

### Day 4 — Open Feedback (`open_feedback`)

Appended to the first meal reminder:

```
---
💡 用了几天了，有没有什么地方觉得不太舒服或者可以改进的？比如提醒的措辞、频率、反馈的详细程度，什么都可以说。随时告诉我，我来调～
```

English variant:
```
---
💡 You've been using this for a few days now — anything that doesn't feel right or could be better? Reminder wording, frequency, feedback detail — anything goes. Just tell me anytime and I'll adjust~
```

---

## Preference Options

### `reminder_offset_min`

| Value | Meaning |
|-------|---------|
| `60` | 1 hour before meal |
| `30` | 30 minutes before meal |
| `15` (default) | 15 minutes before meal |
| `5` | 5 minutes before meal |
| Any positive integer | Custom offset in minutes |

**Downstream effect:** `notification-manager` reads this value when creating
or syncing meal reminder cron jobs. The cron time = meal time from
`health-profile.md > Meal Schedule` minus `reminder_offset_min` minutes.

When this value changes:
1. Update `data/preference-tuning.json > defaults.reminder_offset_min`
2. Record the change in `user_changes`
3. Trigger `notification-manager` to re-sync cron jobs (it will pick up the
   new offset on next activation via auto-sync)
4. Confirm to user: e.g., `"好的，以后提醒改成餐前 30 分钟 ✅"`

### `supervision_level`

Controls how strictly the system treats calorie overages — not the amount of
detail in feedback.

| Value | Overage Attitude | `needs_adjustment` Behavior | End-of-day Over Target |
|-------|------------------|-----------------------------|------------------------|
| `strict` | Every overage matters | Always suggest adjustment when over checkpoint range. Proactive per-meal correction. | Concrete next-day compensation plan |
| `moderate` (default) | Note it, don't stress | Standard `evaluate` logic — suggest when outside range, neutral tone | Brief note, "aim for your usual pattern tomorrow" |
| `relaxed` | Weekly trend is what counts | Only suggest if significantly over (e.g., > 130% of checkpoint target). Skip minor overages. | No comment on single-day overages; only flag if weekly average trends high |

**Downstream effect:** `diet-tracking-analysis` reads this value when deciding
whether and how to respond to calorie overages:

- **`strict`**: Lower threshold for triggering `needs_adjustment` suggestions.
  When over, give a concrete adjustment suggestion. Tone is still friendly
  but clearly directional: `"午餐热量偏高，晚餐建议清淡一些——比如蔬菜沙拉+鸡胸肉。"`
- **`moderate`** (default): Current behavior. Standard checkpoint evaluation.
  Over-target gets a neutral note and forward-looking suggestion.
- **`relaxed`**: Higher threshold — only flag when significantly over (e.g.,
  single meal > 130% of checkpoint range, or daily total > 120% of target).
  Minor overages get no comment. When flagging, frame it around the weekly
  picture: `"这周整体看还行，今天多吃了一点不影响大局。"`

`notification-composer` is NOT affected by supervision level — reminder style
and format stay the same regardless.

When this value changes:
1. Update `data/preference-tuning.json > defaults.supervision_level`
2. Record the change in `user_changes`
3. Confirm to user: e.g., `"好的，以后偶尔吃多不会太紧张 ✅"`

---

## Handling User Preference Changes (Anytime)

Users can change preferences at any time, not just during Week 1. Detect
intent from natural language:

### Reminder Timing Intents

| User says | Action |
|-----------|--------|
| "提醒早一点" / "remind me earlier" | Ask how much earlier, or default to +15 min |
| "提前一个小时提醒" / "remind me 1 hour before" | Set `reminder_offset_min` to 60 |
| "提醒太早了" / "reminders are too early" | Ask preferred timing |
| "不用提前那么多" | Reduce offset (ask or default to 5 min) |
| Any explicit time: "提前 20 分钟" | Set `reminder_offset_min` to 20 |

### Supervision Level Intents

| User says | Action |
|-----------|--------|
| "管严一点" / "be stricter" / "帮我严格控制" | Set `supervision_level` to `strict` |
| "别管那么严" / "偶尔吃多没关系" / "don't stress about overages" | Set `supervision_level` to `relaxed` |
| "正常就好" / "keep it normal" | Set `supervision_level` to `moderate` |
| "吃超了不用说" / "不想每次都被提醒超标" | Set `supervision_level` to `relaxed` |
| "每餐都帮我盯着" / "超了就提醒我" | Set `supervision_level` to `strict` |

### General Feedback

Any feedback that doesn't map to the two settings above should be acknowledged
and, if actionable, applied. Record in `user_changes` with a descriptive
`field` name for traceability. If the feedback requires changes beyond this
skill's scope (e.g., "change my diet mode"), hand off to the appropriate skill.

---

## `user_changes` Format

```json
{
  "date": "2026-03-27",
  "field": "reminder_offset_min",
  "from": 15,
  "to": 30,
  "trigger": "nudge_reply | user_initiated"
}
```

---

## Workspace

### Reads

| Source | Purpose |
|--------|---------|
| `health-profile.md` | Check onboarding complete; read meal schedule for offset calculation |
| `data/preference-tuning.json` | Current defaults and nudge state |

### Writes

| Path | How | When |
|------|-----|------|
| `data/preference-tuning.json` | Direct write | Initialization, nudge status updates, preference changes |

---

## Skill Routing

**Priority Tier: P3 (Planning)** — preference changes are low-frequency
planning-like actions.

- If user expresses a preference change while logging food, `diet-tracking-analysis`
  leads (P2), then this skill handles the preference change inline or after.
- If user expresses preference + emotional distress, `emotional-support` leads (P1).
- Nudge delivery is handled by `notification-composer` (this skill provides
  the templates; composer provides the vehicle).
