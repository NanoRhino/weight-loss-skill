---
name: diet-image-sharing
version: 1.0.0
description: "Generate a shareable daily diet record card (styled HTML page hosted on cloud storage). Trigger when user asks to share their diet record, wants a summary image/card of what they ate today, or says phrases like 'share my meals', 'diet card', '饮食打卡', '分享今天吃了什么', '发个今天的饮食记录', '饮食记录图片'. Also triggered by daily-review or notification-composer when sending a visual diet summary."
metadata:
  openclaw:
    emoji: "camera_with_flash"
---

# Diet Image Sharing — Shareable Daily Diet Card

> **SILENT OPERATION:** Never narrate internal actions, skill transitions, or tool calls to the user. Just do it silently and respond with the result.

Generate a beautiful, shareable HTML card showing the user's daily diet record — meals, calories, macros, and progress toward their target. Upload to cloud storage and send the link.

## When to Trigger

- User asks to share or see a visual summary of their diet record
- User says "饮食打卡", "分享饮食记录", "今天吃了什么（给我看看）", "diet card", "share my meals"
- Another skill requests a visual diet summary for the user

## Data Sources

### Reads

| Source | How | Purpose |
|--------|-----|---------|
| `data/meals/YYYY-MM-DD.json` | `nutrition-calc.py load --data-dir {workspaceDir}/data/meals --tz-offset <offset> [--date YYYY-MM-DD]` | All meals for the day |
| `PLAN.md` | direct read | Daily calorie target |
| `USER.md` | already in context | Name, TZ Offset, Language |
| `health-profile.md` | direct read | Unit preference (for Cal vs kcal) |

### Writes

| Path | When |
|------|------|
| `data/diet-cards/daily-diet-{date}.html` | After generating the HTML card |

## Workflow

### Step 1: Load Meal Data

```bash
python3 {diet-tracking-analysis:baseDir}/scripts/nutrition-calc.py load \
  --data-dir {workspaceDir}/data/meals --tz-offset <offset> [--date YYYY-MM-DD]
```

If no meals are logged for the requested date, tell the user:
- zh: "今天还没有饮食记录，记录了再来生成吧！"
- en: "No meals logged for today yet — log some food first!"

### Step 2: Generate HTML Card

```bash
python3 {baseDir}/scripts/generate-daily-diet-html.py \
  --meals-json '<load output>' \
  --cal-target <from PLAN.md> \
  --user-name '<from USER.md>' \
  --lang <zh|en> \
  --cal-unit <kcal|Cal> \
  --output {workspaceDir}/data/diet-cards/daily-diet-{date}.html
```

Parameters:
- `--meals-json`: JSON string from Step 1 output
- `--cal-target`: Daily calorie target from `PLAN.md > Daily Calorie Range` (use midpoint). Pass 0 if no plan exists.
- `--user-name`: From `USER.md > Basic Info > Name`
- `--lang`: `zh` if `USER.md > Language` contains Chinese, else `en`
- `--cal-unit`: `Cal` for US locale, `kcal` for all others
- `--output`: Write HTML to `data/diet-cards/` directory

### Step 3: Upload to Cloud Storage

Use `plan-export`'s upload script (consistent with weekly-report):

```bash
bash {plan-export:baseDir}/scripts/upload-to-s3.sh \
  --file {workspaceDir}/data/diet-cards/daily-diet-{date}.html \
  --bucket nanorhino-im-plans \
  --username {shortId} \
  --key daily-diet \
  --workspace {workspaceDir}
```

- `{shortId}`: read from `agent-registry.json` (6-char identifier). Fall back to full account ID.
- The URL is stable: `{username}/daily-diet.html` — each upload overwrites the previous card.
- `plan-url.json` is auto-updated with the `daily-diet` key.

### Step 4: Send to User

Send the URL to the user with a short message:

- zh: "你的今日饮食记录卡 👇\n{url}"
- en: "Your daily diet card 👇\n{url}"

## Notes

- HTML is fully self-contained (inline CSS, no external dependencies)
- Designed for mobile — max width 480px, responsive layout
- Green theme consistent with the project's visual identity
- Card shows: date, meal breakdown with individual foods, calorie progress bar, macro summary
- Meals with no data are omitted from the card
- The `daily-diet` key in `plan-url.json` is overwritten each time (only latest card is live)

## Skill Routing

**See `SKILL-ROUTING.md` for the full conflict resolution system.** This skill is **Priority Tier P4 (Reporting)**.

- If the user sends a food photo AND asks to share → `diet-tracking-analysis` (P2) logs first, then this skill generates the card.
- If the user asks for a daily review AND a diet card → `daily-review` handles the text review; this skill can be triggered afterward for the visual card.
