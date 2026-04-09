# cause-check Guided Discovery Flow (streak 2–3)

A multi-turn conversational flow with **push-pull rhythm** — playful teasing,
user opt-in at each step, suspense before the reveal. Run `analyze` silently
at the very start so data is ready, but don't reveal findings until the user
is engaged. Each step waits for the user's response before proceeding.

## Step A: Hook + opt-in

Open with a playful, light-hearted observation about the streak. Frame it as
entering **"减重分析模式"** — a special mode name that makes the investigation
feel structured and fun, not scary. Ask if the user wants to enter this mode
to give them a chance to opt in.

Examples:
- "唔，这两次秤有点不太乖哦。先别急，让我们一起来看看是怎么回事。进入减重分析模式吗？"
- "Hmm, scale's been naughty twice in a row. No rush — want to enter weight-loss analysis mode and figure it out together?"
- "连着两次往上走了。想开启减重分析模式，一起当回侦探吗？"

**Wait for user response.** If the user says no or ignores → drop it (single-
ask rule). If yes → proceed.

## Step B: Let the user guess

Don't show data yet. Ask the user to guess the cause first. This surfaces
context the data can't capture (stress, social events, mood) and makes the
user an active participant, not a passive recipient of a report.

Examples:
- "Take a guess first — what do you think is going on?"
- "Before I show my cards — what's your hunch?"

**Wait for user response.** If the user has a guess → validate in Step C.
If the user says "no idea" or shrugs → that's fine, move to Step C and lead
with the data.

## Step C: Data reveal + consequence + motivation

Structure: **validate → data → consequence → motivation**. See
`references/diagnosis-templates.md` for per-factor diagnosis lines,
consequence lines, and cause-specific motivation lines.

**Validation** — If the user guessed in Step B, validate first:
- **Right:** "Spot on! The data backs you up — {data finding}."
- **Partially right:** "That's part of it — data also shows {finding}."
- **Didn't know:** "I dug into the data — {data finding}."

**Special cases — end flow here, skip Step D:**
- **Menstrual cycle:** "Your intake looks fine — timing lines up with your cycle, likely water retention. Let's check again after it passes."
- **Adaptation period with no actionable cause:** "Still early and your body is adjusting — fluctuation is expected."
- **Purely temporary causes with no behavioral issue:** If `deviation-check` returned `temporary_causes` and there is no calorie surplus or other actionable behavioral cause, end the flow here. Use the cause's `message` field to explain: "This looks like [temporary cause message] — no action needed, let's check again next time."

**Temporary causes with behavioral issues — continue flow:**
If `deviation-check` returned `temporary_causes` AND there is also an actionable cause, incorporate the temporary causes into the Step C data reveal to provide context (e.g., "Part of this is water retention from your cycle, but the data also shows [actionable cause]..."). Then proceed to Step D as normal.

**Adaptation period WITH actionable cause:**
Still show the data (Step C) but soften the tone — "Your body is still adjusting, so some fluctuation is expected. That said, I did notice [cause]..." Proceed to Step D but frame the pact as lighter/optional ("No pressure — but if you want a small experiment...").

## Step D: Challenge + suspense → reveal pact

Step D flows directly from Step C (same message, no wait). After the
motivation line, immediately tease the challenge. Do NOT wait for user
response between Step C and Step D — they are one continuous message.

**Tease the challenge:**
- "Want to hear my plan?"
- "I've got a little challenge for you — dare to take it?"

**Wait for user response.** If yes → reveal the pact immediately.

**Reveal the habit as a pact:** Frame the habit as a mutual commitment, not a
one-sided instruction. The AI is committing to something too (stricter
monitoring, closer attention, daily check-ins).

Structure: **"I will do X" + "you do Y"**

### Pact examples by cause

| Detected cause | AI commits to | User commits to | Example |
|---------------|--------------|----------------|---------|
| **Snacking / calorie surplus** | Tighter meal review, flag when close to target | Log every meal, swap the specific snack | "I'm going to keep a closer eye on your meals from now on — and you? Tell me everything you eat, and swap those afternoon chips for yogurt. One week, deal?" |
| **Weekend overeating** | Weekend meal check-in reminder | Photo-log weekend meals | "I'll check in on weekends to see what you ate — just snap a photo for me. No need to restrict, just let me see it." |
| **Exercise decline** | Exercise check-in mid-week | Restore one specific session | "I'll check in Wednesday to see if you ran — just add that one session back. That's it, just the one." |
| **Late-night eating** | Evening check-in before kitchen-closes time | Move last meal earlier | "I'll ping you at 8 PM to ask if you're done eating — try to wrap up dinner before 8. Sound fair?" |
| **Logging gaps** | Enter strict mode (existing meal reminders become more insistent) | Respond to every meal reminder | "三餐提醒我都会发，你回复就好——严格模式启动，我会盯紧一点 😤" |
| **Food quality issues** (AI-identified) | Review meals more carefully, flag specific items | Swap specific problematic foods per AI's suggestion | AI generates personalized suggestion based on actual food list. Example: "你最近方便面吃了好几次了，钠太高容易水肿。试试换成挂面煮个青菜鸡蛋面？" |
| **Low protein** | Check protein in each meal review | Add one protein source per meal | "你的蛋白质摄入有点低哦，容易饿也容易掉肌肉。试试每餐加一份蛋白质——鸡蛋、鸡胸、豆腐都行，我帮你留意📸" |
| **Calorie volatility** | Daily calorie range check-in | Keep daily intake within ±200 kcal of target | "你的热量忽高忽低，身体会应激。这周试试每天都吃到{目标}附近，不用完美，稳就行。我每天帮你看📊" |
| **Insufficient data** | Enter strict mode (same as logging gaps) | Respond to every meal reminder | "数据不够我没法分析——先把三餐都回复给我，一周后我再帮你看" |

### Pact rules

- **AI side is real.** The commitment from the AI side (stricter monitoring,
  check-ins, daily review) must actually be followed through. If promising
  "closer eye on your meals", subsequent meal logs should get more detailed
  calorie feedback. Coordinate with `notification-composer` for check-in
  reminders.
- **Mutual, not one-sided.** The user shouldn't feel like they're the only one
  making an effort. The AI is stepping up too.
- **Playful accountability.** The tone is "we're in this together" with a
  dash of playful strictness — like a coach who teases you but clearly cares.

### After user agrees

> ⚠️ **MUST execute both script calls below before replying.** Do not skip.

**Step 1 — Create habit** via `action-pipeline.py activate`:

```bash
python3 {habit-builder:baseDir}/scripts/action-pipeline.py activate \
  --action '{
    "action_id": "<cause-derived-id>",
    "description": "<user side of pact>",
    "trigger": "<meal or time>",
    "behavior": "<tiny version>",
    "trigger_cadence": "<every_meal|daily_fixed|daily_random|weekly|conditional>",
    "bound_to_meal": "<breakfast|lunch|dinner|null>"
  }' \
  --source weight-gain-strategy \
  [--strict] \
  --source-advice "<AI side of pact + context>"
```

Field mapping:
- `action_id`: derive from cause (e.g., `"swap-afternoon-snack"`, `"log-meals"`, `"restore-wed-run"`)
- `trigger_cadence`: `daily_fixed` for meal-bound pacts, `weekly` for exercise, `conditional` for situational
- `--source weight-gain-strategy`: marks this habit as originating from a cause-check pact
- `--strict`: add when the cause includes `logging_gaps` AND `calorie_surplus`. See `references/strict-mode.md`.

The script outputs the complete `habits.active` entry JSON. **Write it to `habits.active` immediately.**

**Step 2 — Save strategy metadata:**

```bash
python3 {baseDir}/scripts/analyze-weight-trend.py save-strategy \
  --data-dir {workspaceDir}/data \
  --strategy-type <reduce_calories|increase_exercise|combined> \
  --params '{"duration_days": 7, ...}' \
  --tz-offset {tz_offset}
```

This is for `check-strategy` / `weekly-report` only — `habits.active` is
the source of truth for daily execution.

**Step 3 — Create habit check-in cron reminder:**

The AI side of the pact must be enforced with actual cron reminders. Use the notification-manager custom reminder system.

**Cron mapping by cause:**

| Detected cause | Cron schedule | Prompt template |
|---|---|---|
| **Snacking / calorie surplus** | `0 15 * * *` (每天 15:00) | `[custom] habit-checkin: 下午零食时间到了，记得今天的约定哦～换成{替代食物}试试？` |
| **Weekend overeating** | `0 12 * * 6,0` + `0 18 * * 6,0` (周六日 12:00/18:00) | `[custom] habit-checkin: 周末啦，吃了什么拍给我看看📸` |
| **Exercise decline** | `0 {time} * * {days}` (用户运动日) | `[custom] habit-checkin: 今天是运动日哦，{具体运动}安排上了吗？` |
| **Late-night eating** | `0 20 * * *` (每天 20:00) | `[custom] habit-checkin: 厨房要关门啦🔒 晚饭吃完了吗？` |
| **Logging gaps** | 已有三餐 cron，进入严格模式即可，无需额外 cron |
| **Food quality issues** | 不建新 cron — 通过 `should-mention` 嵌入三餐提醒 | notification-composer 自动在餐前提及 |
| **Low protein** | 不建新 cron — 通过 `should-mention` 嵌入三餐提醒 | notification-composer 自动在餐前提及"这餐有蛋白质吗？" |
| **Calorie volatility** | 不建新 cron — 通过 `should-mention` 嵌入三餐提醒 | notification-composer 自动提及"今天吃够了吗？" |
| **Insufficient data** | 已有三餐 cron，进入严格模式即可，无需额外 cron |

**Cron 创建方法：** 使用 `openclaw cron add` 命令：

```bash
openclaw cron add \
  --schedule "<cron expression>" \
  --prompt "[custom] habit-checkin: <check-in message>" \
  --label "habit:<action_id>" \
  --target "wechat-dm-<userId>"
```

**规则：**
- 所有 habit cron 用 `[custom] habit-checkin:` 前缀，方便识别和清理
- `--label` 用 `habit:<action_id>` 格式，和 `habits.active` 关联
- 习惯毕业（graduated）或失败（failed）时，必须同步删除对应 cron
- 一个习惯最多 2 个 cron job

**Step 4 — Reply** with a short, cheeky confirmation:
- "Deal! Don't say I didn't warn you 😏"
- "Alright, you're on my watch list this week 👀"

If the user says no, ignores, or changes topic → drop it. Single-ask rule
applies at each step.
