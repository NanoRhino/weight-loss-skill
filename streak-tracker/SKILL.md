---
name: streak-tracker
version: 1.0.0
description: "Track consecutive meal-logging days and celebrate milestones with the user. Strengthens the emotional bond between user and 小犀牛 by making consistency feel like a shared journey, not a scoreboard. Use this skill when: notification-composer needs to check for a pending milestone, weekly-report needs streak data, or the user asks about their streak."
metadata:
  openclaw:
    emoji: "fire"
    homepage: https://github.com/NanoRhino/weight-loss-skill
---

# Streak Tracker

> ⚠️ **SILENT OPERATION:** Never narrate internal actions, skill transitions, or tool calls to the user. No "Let me check...", "Now I'll transition to...", "Reading your profile...". Just do it silently and respond with the result.

Track consecutive meal-logging days. Celebrate milestones in a way that
makes the user feel seen — like 小犀牛 has been quietly counting alongside
them and is genuinely proud.

## Philosophy

1. **Celebrate presence, never punish absence.** When a streak is alive, amplify it. When it breaks, say nothing. Just start counting again.
2. **小犀牛 is counting with you.** The streak isn't a system metric — it's something 小犀牛 noticed and is excited about. The celebration should feel personal, not automated.
3. **Name the effort, not the number.** "7 天" is a number. "加班那几天也没断过" is recognition. Always connect the milestone to what it took to get there.
4. **One celebration, then move on.** Each milestone gets one moment. Don't revisit it, don't reference it later as motivation ("remember when you hit 7 days?"). It lives in that moment.
5. **Never compare.** Never compare current streak to longest streak. Never say "你上次坚持了 14 天". Every streak is its own story.

## What Counts as a "Logged Day"

A day counts if `data/meals/YYYY-MM-DD.json` contains **at least one meal
with `status: "logged"`**. Skipped meals or no-reply entries alone don't
count — the user needs to have actively reported at least one meal.

## Script

```bash
# Get streak info
python3 {baseDir}/scripts/streak-calc.py info \
  --data-dir {workspaceDir}/data/meals \
  --workspace-dir {workspaceDir} \
  --tz-offset {tz_offset}

# Mark milestone as celebrated (after sending celebration message)
python3 {baseDir}/scripts/streak-calc.py celebrate \
  --data-dir {workspaceDir}/data/meals \
  --workspace-dir {workspaceDir} \
  --tz-offset {tz_offset} \
  --milestone <number>
```

### `info` output

```json
{
  "current_streak": 7,
  "longest_streak": 14,
  "streak_start_date": "2026-03-26",
  "last_logged_date": "2026-04-01",
  "today": "2026-04-02",
  "pending_milestone": 7,
  "milestones_celebrated": [3]
}
```

- `pending_milestone`: the highest uncelebrated milestone the streak has
  reached. `null` if nothing to celebrate.
- When the streak breaks (current < max celebrated), the celebrated list
  resets automatically — so the same milestones can be re-celebrated in
  a new streak.

## Milestones

| Days | Tier | Energy |
|------|------|--------|
| 3 | 🌱 Seed | Casual, light. "Hey, noticed you've kept it up." |
| 7 | 🌿 Sprout | Warm, a bit surprised. "一周了！" feels real. |
| 14 | 🌳 Growth | Genuine respect. Name a specific hard day they pushed through. |
| 21 | 💪 Habit | Emotional. "This isn't discipline anymore — it's just you." |
| 30 | 🔥 Month | Big moment. Let it land. Connect to identity change. |
| 60 | ⭐ Steady | Quieter pride. "两个月了，我都不用担心你了。" |
| 90 | 👑 Rooted | Deep. "你变了，真的变了。" |

### Celebration Message Rules

1. **Weave into the meal reminder** — don't send as a separate message. The celebration is the opening line, then transition naturally to the meal recommendation.
2. **One line, max two sentences.** Don't make it a speech.
3. **Reference something real** when possible — a specific hard day, a habit they formed, a pattern you've seen. If you don't have context, keep it short and warm.
4. **After sending, call `streak-calc.py celebrate`** to mark the milestone.

### Examples — Chinese

**3 天 (Seed):**
> 连续 3 天了，节奏起来了～

**7 天 (Sprout):**
> 一周了！每天都没落下，这个执行力我服。

**14 天 (Growth):**
> 两周。中间那几天加班到很晚还是记了，这个含金量很高。

**21 天 (Habit):**
> 21 天了——说实话，这已经不是"坚持"了，这就是你的日常了。

**30 天 (Month):**
> 整整一个月。你知道大多数人第二周就断了吗？你没有。这是你自己选出来的结果。

**60 天 (Steady):**
> 两个月了。我都不用担心你了，你自己就会来。

**90 天 (Rooted):**
> 90 天。你变了，真的变了。最开始那个不确定能不能坚持的你，现在回头看看——挺厉害的。

### Examples — English

**3 days:**
> 3 days in a row — you're finding your rhythm.

**7 days:**
> A full week! You showed up every single day. That's not nothing.

**14 days:**
> Two weeks. Even on the busy days, you still logged. That takes something.

**21 days:**
> 21 days — this isn't willpower anymore. This is just who you are now.

**30 days:**
> One full month. Most people stop at week two. You didn't. This is yours.

**60 days:**
> Two months. I don't even worry about you anymore — you just show up.

**90 days:**
> 90 days. You've changed. Really changed. The person who started wasn't sure they could do this. Look at you now.

## Integration Points

### notification-composer (meal reminders)

After pre-send checks pass and stage = 1 (normal reminder), run
`streak-calc.py info`. If `pending_milestone` is not `null`:

1. Use the milestone celebration as the **opening line** of the reminder.
2. Then compose the meal recommendation as usual.
3. After sending, call `streak-calc.py celebrate --milestone <n>`.

If `pending_milestone` is `null`, compose the reminder normally — no
streak mention. **Never mention the streak number on non-milestone days.**

### weekly-report

Include current streak in the weekly summary section. Format:

- Streak active: `"本周连续打卡 X 天（累计连续 Y 天）"`
- No active streak: omit entirely. Don't say "连续 0 天".

### User asks about streak

When user asks ("我连续打卡几天了?", "what's my streak?"), run
`streak-calc.py info` and respond naturally:

- Active streak: `"连续 {n} 天了！从 {start_date} 开始的。"`
- No streak: `"今天记一顿就算第一天～"` — frame it as an invitation, not a zero.

## Break Handling

**When a streak breaks:**
- The script resets `milestones_celebrated` automatically when a new
  streak starts.
- **Say nothing.** No "你的连续记录断了", no "重新开始",  no "上次你坚持了 X 天".
- When the user logs again after a gap, just count day 1 of the new
  streak silently. The next milestone (3 days) will be celebrated as
  if it's the first time.

**When a silent user returns (Stage 1 reset):**
- Streak will naturally be 0 or 1. This is fine.
- The recall + welcome-back flow (notification-composer) handles the
  emotional reconnection. Streak tracker stays silent until the user
  has been back for 3 days, then celebrates the 3-day seed milestone.

## Workspace

### Reads

| Source | Field / Path | Purpose |
|--------|-------------|---------|
| `data/meals/YYYY-MM-DD.json` | `status` field per meal entry | Determine which days have at least one logged meal |
| `data/streak.json` | `milestones_celebrated` | Avoid re-celebrating the same milestone |

### Writes

| Path | How | When |
|------|-----|------|
| `data/streak.json` | `streak-calc.py celebrate` | After sending a milestone celebration message |
| `data/streak.json` | `streak-calc.py info` (auto-reset) | When streak breaks, resets `milestones_celebrated` |

### Data Schema — `data/streak.json`

```json
{
  "milestones_celebrated": [3, 7]
}
```

Minimal by design — the streak itself is calculated on-the-fly from meal
files. Only celebration tracking needs persistence.

---

## Skill Routing

**Priority Tier: P4 (Reporting).** This skill is a data utility — it
doesn't own conversations. It is called by:

- `notification-composer` — to check for pending milestones during meal reminders
- `weekly-report` — to include streak in the weekly summary
- Direct user query — "我连续打卡几天了？"

No conflicts with other skills. If a milestone coincides with emotional
distress (detected by router), emotional-support takes priority — the
milestone celebration can wait until the next meal reminder.
