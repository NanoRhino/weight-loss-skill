---
name: reward-engine
version: 1.0.0
description: >
  Calculates cumulative calorie-target achievement days and badge level, PLUS
  the weight-loss milestone ladder (first 5 lb / 5% / every 10 lb / Onederland /
  10% / halfway / goal). Called BY other skills (diet-tracking-analysis after
  meal check-in for badges; weight-tracking after a weigh-in for milestones) —
  not a standalone skill.
  
  WHEN to call:
  - diet-tracking-analysis: after meal_checkin returns successfully (action: create/append).
    Run badge-calc.py check. If level_up is true, append badge celebration + image to reply.

  WHEN NOT to call:
  - During corrections or deletions (action: correct/delete)
  - During recall stages (Stage 2/3/4)
  - If meal_checkin failed or returned an error

  DELIVERY: Badge image sent via MEDIA directive when level_up is true.
  This skill never sends messages directly — only provides data + generates images.

  Returns: JSON with qualified_today, current_count, current_level, level_up, badge info.
metadata:
  openclaw:
    emoji: "trophy"
    homepage: https://github.com/NanoRhino/weight-loss-skill
---

# Reward Engine — Calorie Target Badge

> ⚠️ **SILENT OPERATION:** Never narrate internal actions or tool calls.

## Philosophy

1. **Celebrate accumulation, never punish gaps.** Count goes up only — never down.
2. **Reward the behavior (eating on target), not the outcome (weight loss).**
3. **One celebration per level-up, then move on.** Don't revisit past badges.
4. **Personalize the image.** User name + their data on the badge.

## Qualification Rules

A day counts as "qualified" when ALL THREE conditions are met:

1. **Complete meals logged:** Number of main meals (breakfast/lunch/dinner) logged today ≥ expected meal count
   - Default: 3 meals
   - Intermittent fasting (16:8 or explicit "两餐" in PLAN.md): 2 meals
   - `snack` does NOT count as a main meal
2. **Calories in target range:** Total daily calories within the `Daily Calorie Range` from PLAN.md (e.g., 1,430 - 1,630)
   - Falls back to target ± 10% if only a single target value exists
3. **Above safety floor:** Total daily calories ≥ BMR × 0.8
   - Prevents rewarding dangerous under-eating

## Script

```bash
python3 {baseDir}/scripts/badge-calc.py check \
  --workspace-dir {workspaceDir} \
  --tz-offset {tz_offset}
```

### Output

```json
{
  "qualified_today": true,
  "already_counted": false,
  "current_count": 14,
  "current_level": 3,
  "level_up": true,
  "new_badge": {
    "level": 3,
    "name": "⭐⭐⭐ 自由支配者",
    "message": "两周的精准分配。你不是在\"控制饮食\"，你是真的会吃了。",
    "milk_tea_cups": 28,
    "progress_bar": "━━━━━━━━━━░░░░ 14/21 → 下一级：稳定输出选手"
  },
  "badge_image": "{workspaceDir}/data/badges/badge_level_3.png"
}
```

- `qualified_today`: whether today meets all 3 conditions
- `already_counted`: true if today was already counted (prevents double-counting)
- `level_up`: true only when a NEW level is reached this check
- `new_badge`: null if no level-up
- `badge_image`: path to generated badge image (null if no level-up)

## Level Definitions

| Level | Days | Name | Message |
|-------|------|------|---------|
| 1 | 3 | ⭐ 稳稳吃饭的人 | 有3天热量刚好落在目标区间。这不是运气——是你对"一顿饭多少热量"有感觉了。 |
| 2 | 7 | ⭐⭐ 热量掌控达人 | 7天达标。你已经知道什么时候该多吃、什么时候该收着。这种判断力比任何食谱都管用。 |
| 3 | 14 | ⭐⭐⭐ 自由支配者 | 两周的精准分配。你不是在"控制饮食"，你是真的会吃了。 |
| 4 | 21 | ⭐⭐⭐⭐ 稳定输出选手 | 三周的节奏，已经不是"在坚持"了，是你的正常状态。 |
| 5 | 30 | ⭐⭐⭐⭐⭐ 精准生活家 | 一个月。你对热量的直觉已经内化了——不看数字也不会差太远。 |
| 6 | 45 | ⭐×6 持续进化者 | 45天。一个半月的稳定输出，这不是阶段性的表现，是你的新常态。 |
| 7 | 60 | ⭐×7 长期主义玩家 | 60天。不需要鸡汤，数据说明一切。 |
| 8 | 90 | ⭐×8 不可撼动 | 90天。多数人的计划活不过两周，你走完了全程。这不是关于减肥了，这是你证明了自己能长期做好一件事。 |

## Starter Badge — "First Step" / 「第一步」 (one-time, NOT part of the day ladder)

A separate, ONE-TIME starter badge awarded the moment the user logs their **first meal ever** — to reward the single most important action immediately, instead of waiting for the 3-qualified-day Level 1. It is **independent of the calorie-target ladder above**: it does not count toward, gate, or interfere with the day-based levels, and it lives under its own `starter` key in `badges.json` (sibling to `calorie_target`).

- **Who awards it:** `diet-tracking-analysis`'s first-meal flow detects the first-meal-ever moment (via `first-meal-check.py`) and calls reward-engine's award entry point below. reward-engine remains the **sole writer** of `badges.json` (CONVENTIONS.md §3 ownership).
- **Award command (idempotent):**
  ```bash
  python3 {baseDir}/scripts/badge-calc.py award-starter --workspace-dir {workspaceDir} --tz-offset {tz_offset}
  ```
  Returns `{ "newly_awarded": bool, "already_awarded": bool, "badge": {...} }`. The caller celebrates **only** when `newly_awarded: true`; `already_awarded: true` → no-op (covers `/compact` re-runs and edge re-fires).
- **Surfaced as TEXT** in the same meal-log reply by `diet-tracking-analysis` (Twilio is text/MMS — the in-the-moment unlock is text, not a badge-card image).
- **No double-celebration:** the day-ladder `check` flow above is untouched (still needs 3 qualified days for Level 1), and streak day-1 is silent — so the starter badge is the only thing that fires at the first meal.

### Starter badge definition

| id | name (en) | name (zh) | message (en) | message (zh) |
|----|-----------|-----------|--------------|--------------|
| `first-step` | 🏅 First Step | 🏅 第一步 | You logged your very first meal. This is where it starts. | 你记录了第一餐。一切从这里开始。 |

Defined in `scripts/badge-calc.py` as `STARTER_BADGE`.



## Weight-Loss Milestone Ladder (the *scale*, not the calorie badge)

A second, independent ladder that celebrates **weight** milestones — the good
news users actually joined for. Where `badge-calc.py` rewards the *behavior*
(eating on target), `weight-milestone-calc.py` rewards *scale progress*.
Text-only (like the starter badge — no milestone card images exist yet).

**Script:** `scripts/weight-milestone-calc.py`

```bash
# On a weigh-in — detect + persist the newly-crossed milestone:
python3 {baseDir}/scripts/weight-milestone-calc.py check \
  --data-dir {workspaceDir}/data \
  --start <first weight> --current <latest weight> --goal <goal weight> \
  --unit lb|kg --tz-offset {tz_offset}

# For hope-first framing — the NEXT upcoming milestone (no write):
python3 {baseDir}/scripts/weight-milestone-calc.py next \
  --start <start> --current <current> --goal <goal> --unit lb|kg
```

**Ladder (shared cross-repo contract — celebrate each ONCE, deduped):**
first **5 lb / 2.5 kg** lost · **5%** of start weight · every **10 lb / 5 kg**
(10/20/30…) · **"Onederland"** = crossing under 200 lb (lb-unit only; start ≥ 200
& goal < 200) · **10%** of start weight · **halfway** to goal · **goal reached**.
If several fire on one weigh-in, the single **most significant** is surfaced and
the rest are still marked celebrated so they never re-fire.

**`check` output** (see weight-tracking SKILL.md for the surfacing rule):
```json
{ "newly_crossed": true,
  "milestone": { "id": "onederland", "kind": "onederland", "amount": null,
                 "unit": "lb", "target_weight": 199.99, "lost_so_far": 11.0,
                 "message_en": "Welcome to Onederland — you're under 200 lb!",
                 "message_zh": "体重进入「1 字头」——已经低于 200 磅！" },
  "also_crossed": ["pct_5"], "all_celebrated": ["first_chunk","pct_5","onederland"] }
```
- **First run backfills silently** (`backfilled: true`, nothing surfaced) so a
  mid-journey user is never spammed with historical milestones (补算不补发).
- `message_en`/`message_zh` are seeds — the caller delivers in the user's
  language per `USER.md` (this skill does NO language selection, CONVENTIONS §10).

**Who calls it:**
- `weight-tracking` (via `save-and-check.py`) runs `check` on every new weigh-in
  (never on a correction) and returns it as `context.milestone`.
- `weight-loss-planner` / any hope-first framing may run `next` to lead with the
  near-term win instead of the far completion date.

### Data Storage — `data/weight-milestones.json` (owned by reward-engine)

```json
{ "initialized": true,
  "celebrated": ["first_chunk", "pct_5", "onederland"],
  "last_checked": "2026-07-02" }
```
reward-engine **owns** this file (CONVENTIONS §3). Sibling to `data/badges.json`
— kept separate because the two ladders are independent (behavior vs. scale) and
have different write triggers. Backward-compatible: absent = `initialized:false`
→ the next `check` backfills silently. `celebrated` is the dedup set of
milestone ids; only `weight-milestone-calc.py` writes it.

## Badge Image Generation

When `level_up == true`, generate a personalized badge image:

- **Template:** from `{baseDir}/assets/` (operator provides base template)
- **Dynamic text overlay:**
  - User's name (from USER.md)
  - Badge level + name
  - Cumulative days count
  - Milk tea cups equivalent
  - Progress bar to next level
- **Output:** saved to `{workspaceDir}/data/badges/badge_level_{N}.png`
- **Format:** PNG, dimensions TBD (pending operator's style reference)

> ⚠️ Image template assets pending — operator will provide reference design.
> Until then, badge_image will be null and celebration is text-only.

## Data Storage

File: `{workspaceDir}/data/badges.json`

```json
{
  "calorie_target": {
    "current_level": 3,
    "current_count": 14,
    "next_level_target": 21,
    "qualified_dates": ["2026-05-01", "2026-05-03", "2026-05-04"],
    "unlocked_at": {
      "1": "2026-04-15",
      "2": "2026-04-28",
      "3": "2026-05-10"
    },
    "daily_deficit": 385,
    "last_calculated": "2026-05-19"
  },
  "starter": {
    "id": "first-step",
    "name_en": "🏅 First Step",
    "name_zh": "🏅 第一步",
    "message_en": "You logged your very first meal. This is where it starts.",
    "message_zh": "你记录了第一餐。一切从这里开始。",
    "unlocked_at": "2026-04-14"
  }
}
```

The `starter` key (one-time "First Step" badge) is a sibling of `calorie_target` — written only by `award-starter`, never by `check`. `check` preserves it (it only ever touches `calorie_target`).

## Integration Point

Called by `diet-tracking-analysis` after `meal_checkin` returns with `action: "create"` or `action: "append"`:

```
# After composing the normal meal reply (①②③):
1. Run badge-calc.py check
2. If level_up == true AND badge_image exists:
   → Append badge celebration text after normal reply
   → Send badge image via MEDIA: directive
3. If level_up == true AND badge_image is null/empty:
   → Say nothing (silent skip — do NOT fall back to text)
4. If qualified_today == true but no level_up:
   → Say nothing (silent accumulation)
5. If qualified_today == false:
   → Say nothing about badges
```

## Milestone → Dashboard Tip (touch point 1)

A **level-up** (`level_up == true`) is a logging milestone — the natural,
once-in-a-while moment to also help the user discover their live web dashboard.
This is the ONLY badge-flow moment that may carry the dashboard tip; never add it on
a plain `qualified_today` accumulation day, and never on every meal log.

**Only when `level_up == true`** (after composing the badge celebration above),
gate-check and, if allowed, append the dashboard tip as ONE extra line:

```bash
python3 {dashboard-link:baseDir}/scripts/dashboard-tip-gate.py check \
  --workspace-dir {workspaceDir} --surface milestone --tz-offset {tz_offset}
```

- `SHOW surface=milestone` → append the **milestone** tip line from
  `dashboard-link/SKILL.md` § Proactive Dashboard Tip (one line, plain URL, user's
  language per `USER.md`), then after the reply is sent run:
  ```bash
  python3 {dashboard-link:baseDir}/scripts/dashboard-tip-gate.py mark \
    --workspace-dir {workspaceDir} --surface milestone --tz-offset {tz_offset}
  ```
- `SUPPRESS ...` → say nothing about the dashboard; send the badge celebration alone.

The shared gate (owned by `dashboard-link`) enforces the global show-policy
(≤ 2 total, once per surface, never twice/day, stop once discovered) and respects
pause/leave/opt-out — so this never spams. Do NOT introduce a separate flag here.
