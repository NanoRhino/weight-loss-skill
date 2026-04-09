---
name: diet-image-sharing
version: 1.1.0
description: "Generate a shareable daily diet record card as an image (PNG) or web page (HTML). Trigger when user asks to share their diet record, wants a summary image/card of what they ate today, or says phrases like 'share my meals', 'diet card', '饮食打卡', '分享今天吃了什么', '发个今天的饮食记录', '饮食记录图片'. Also triggered by daily-review or notification-composer when sending a visual diet summary."
metadata:
  openclaw:
    emoji: "camera_with_flash"
    requires:
      bins: ["uv"]
---

# Diet Image Sharing — Shareable Daily Diet Card

> **SILENT OPERATION:** Never narrate internal actions, skill transitions, or tool calls to the user. Just do it silently and respond with the result.

Generate a beautiful, shareable daily diet record card — meals, calories, macros, and progress toward target. Supports two output modes:

- **Image mode (default):** PNG image sent directly in chat — best for WeChat / Telegram / social sharing.
- **Link mode:** HTML web page hosted on cloud storage — best when the user wants a clickable link.

## When to Trigger

- **Auto-trigger (primary):** `diet-tracking-analysis` calls `log-meal` and it returns `all_meals_logged: true` — meaning the user has logged all main meals for the day. The diet card is generated and sent automatically as a "check-in complete" reward. No user request needed.
- **Manual trigger:** User asks to share or see a visual summary of their diet record — "饮食打卡", "分享饮食记录", "今天吃了什么（给我看看）", "diet card", "share my meals".
- **Cross-skill trigger:** Another skill (e.g., daily-review) requests a visual diet summary.

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
| `data/diet-cards/daily-diet-{date}.png` | After converting HTML to image (image mode) |

## Workflow

### Step 1: Load Meal Data

```bash
python3 {diet-tracking-analysis:baseDir}/scripts/nutrition-calc.py load \
  --data-dir {workspaceDir}/data/meals --tz-offset <offset> [--date YYYY-MM-DD]
```

If no meals are logged for the requested date, tell the user:
- zh: "今天还没有饮食记录，记录了再来生成吧！"
- en: "No meals logged for today yet — log some food first!"

### Step 2: Generate Vintage Card HTML

```bash
python3 {baseDir}/scripts/generate-vintage-card.py \
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

The vintage card generates a hand-drawn style "food journal" with:
- SVG food illustrations auto-matched to each food item by keyword
- Vintage paper texture background with warm brown tones
- Each meal shown with its food icons + detail table
- Daily summary with macro breakdown and progress bar

### Step 3: Convert to Image (image mode — default)

Convert the HTML card to a PNG image using WeasyPrint + PyMuPDF:

```bash
uv run {baseDir}/scripts/html-to-image.py \
  {workspaceDir}/data/diet-cards/daily-diet-{date}.html \
  {workspaceDir}/data/diet-cards/daily-diet-{date}.png \
  --scale 2
```

- No browser binary required — uses WeasyPrint (HTML→PDF) + PyMuPDF (PDF→PNG).
- `--scale 2` produces retina-quality output (2x resolution).
- Bottom whitespace is auto-trimmed.

### Step 4: Upload & Send

#### Image mode (default — send PNG directly in chat)

Upload the PNG via `jdcloud-oss-upload` — its `MEDIA:` output auto-attaches the image to the chat message:

```bash
uv run {jdcloud-oss-upload:baseDir}/scripts/upload.py \
  {workspaceDir}/data/diet-cards/daily-diet-{date}.png \
  --prefix diet-cards
```

The script prints:
- `URL: <presigned-url>` — the presigned URL (15 min expiry)
- `MEDIA: <presigned-url>` — OpenClaw auto-attaches this as an inline image

After upload, send a short message alongside the image:
- zh: "你的今日饮食记录 👆"
- en: "Your daily diet record 👆"

#### Link mode (send HTML link — use when user explicitly asks for a link)

Upload the HTML via `plan-export`'s upload script:

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

Send the URL:
- zh: "你的今日饮食记录卡 👇\n{url}"
- en: "Your daily diet card 👇\n{url}"

## Notes

- **Default is image mode** — sends a PNG directly in chat, no click needed.
- Use link mode only when the user explicitly asks for a link or URL.
- HTML is fully self-contained (inline CSS, no external dependencies)
- Designed for mobile — max width 480px, responsive layout
- Green theme consistent with the project's visual identity
- Card shows: date, meal breakdown with individual foods, calorie progress bar, macro summary
- Meals with no data are omitted from the card
- Image is 2x retina quality (960px actual width for sharp rendering on phones)
- The `daily-diet` key in `plan-url.json` is overwritten each time (only latest card is live)

## Skill Routing

**See `SKILL-ROUTING.md` for the full conflict resolution system.** This skill is **Priority Tier P4 (Reporting)**.

- If the user sends a food photo AND asks to share → `diet-tracking-analysis` (P2) logs first, then this skill generates the card.
- If the user asks for a daily review AND a diet card → `daily-review` handles the text review; this skill can be triggered afterward for the visual card.
