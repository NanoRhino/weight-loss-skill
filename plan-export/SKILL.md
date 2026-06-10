---
name: plan-export
version: 2.2.0
description: "Convert Markdown plans to styled HTML web pages (hosted on cloud storage with presigned URLs) or PDFs, and deliver them to users. Supports weight loss plans (PLAN.md) and meal plans (MEAL-PLAN.md) with different HTML templates. Trigger when: (1) weight-loss-planner finishes generating PLAN.md, (2) meal-planner finishes generating MEAL-PLAN.md, (3) any time a Markdown document should be delivered as a professional document to the user, (4) user asks for their plan link and the previous one has expired."
metadata:
  openclaw:
    emoji: "page_facing_up"
---

# Plan Export (HTML Web / PDF)

> ⚠️ **SILENT OPERATION:** Never narrate internal actions, skill transitions, or tool calls to the user. No "Let me check...", "Now I'll transition to...", "Reading your profile...". Just do it silently and respond with the result.


Convert Markdown plans into professionally styled documents and deliver them to users.

**Primary mode:** HTML web page uploaded to cloud storage — generates a beautiful, mobile-friendly web page and provides a permanent URL.

**Note:** `--bucket` is required. Always pass `--bucket nanorhino-im-plans` (or the appropriate bucket name) when calling the script.

## Channel-Based Export Policy

Not all channels need URL export. Read `{baseDir}/config.json` to get the `urlExportChannels` list, then read the agent workspace's `channel-source.json` to determine the user's channel.

- **If the user's channel is in `urlExportChannels`**: Generate HTML, upload, and send the URL to the user.
- **If the user's channel is NOT in the list**: Skip URL export entirely. The calling skill (weight-loss-planner / meal-planner) already presented the plan as inline text — no additional action needed.

When called by another skill, **always check channel first**. If the channel doesn't need URL export, return silently — do not generate HTML, do not upload, do not send any message.

## Supported Document Types

| Type | Input File | Template | Key | HTML Script |
|---|---|---|---|---|
| Weight Loss Plan | `PLAN.md` | (default) | `weight-loss-plan` | `generate-html.py` |
| Meal Plan | `MEAL-PLAN.md` | `meal-plan` | `meal-plan` | `generate-meal-plan-html.py` |

## Primary Mode: HTML + Cloud Storage Presigned URL

### Storage Backend (AWS S3)

Uploads go to AWS S3 only.

**Prerequisites:**
- S3 bucket with 30-day lifecycle rule (auto-deletion)
- AWS CLI credentials via standard mechanisms (IAM role, env vars `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`, or `~/.aws/credentials`) with `s3:PutObject` + `s3:GetObject` permission
- Default bucket: `nanorhino-im-plans` (us-west-1)

### How to Use

```bash
# Weight loss plan
URL=$(bash {baseDir}/scripts/generate-and-send.sh \
  --agent <YOUR_AGENT_ID> \
  --input PLAN.md \
  --workspace <AGENT_WORKSPACE_PATH> \
  --key weight-loss-plan)

# Meal plan (diet template — generated during onboarding)
URL=$(bash {baseDir}/scripts/generate-and-send.sh \
  --agent <YOUR_AGENT_ID> \
  --input MEAL-PLAN.md \
  --workspace <AGENT_WORKSPACE_PATH> \
  --key meal-plan)

# 7-day meal plan (detailed weekly plan — only if user requests)
URL=$(bash {baseDir}/scripts/generate-and-send.sh \
  --agent <YOUR_AGENT_ID> \
  --input MEAL-PLAN.md \
  --workspace <AGENT_WORKSPACE_PATH> \
  --template meal-plan \
  --key meal-plan)
```

Parameters:
- `--agent` (required): Your agent ID (e.g., `007-zhuoran`)
- `--input` (required): Path to the Markdown file
- `--bucket` (optional): Storage bucket name. Defaults to `nanorhino-im-plans`.
- `--workspace` (required): Agent workspace path. Used to write `plan-url.json` and to **auto-resolve the username** for the S3 key path (workspace dir → agentId → `agent-registry.json` shortId). No need to pass `--username` manually.
- `--template` (optional): `meal-plan` for meal plan HTML. Omit for default (weight loss plan).
- `--key` (required for HTML mode): Document key, used in both S3 path and `plan-url.json` (e.g., `weight-loss-plan`, `meal-plan`)

The script outputs the public URL to stdout. **You are responsible for sending this URL to the user using the message tool** (works with any channel: Slack, Telegram, etc.).

### After Sending

Tell the user their plan is ready and include the link. Example:

> "你的计划已经生成好了！点击这里查看：[链接] 📄 有什么问题随时问我！"

### When PLAN.md or MEAL-PLAN.md is Updated

**Whenever a plan file is modified by any skill**, **always re-run the upload script** to push the new version to cloud storage. The file is uploaded to the same S3 key (`{username}/{key}.html`), so the public URL stays the same. You only need to send the link once; subsequent updates are reflected automatically at the same URL.

### plan-url.json (Multi-Document)

When `--workspace` and `--key` are provided, the script writes/merges into `plan-url.json`:

```json
{
  "weight-loss-plan": {
    "url": "https://nanorhino.ai/zhuoran/weight-loss-plan.html",
    "uploaded_at": "2026-03-09T04:15:00Z"
  },
  "meal-plan": {
    "url": "https://nanorhino.ai/zhuoran/meal-plan.html",
    "uploaded_at": "2026-03-09T07:00:00Z"
  }
}
```

Each key is updated independently — uploading a new meal plan doesn't affect the weight loss plan entry.

**When a user asks for their plan link:**
1. Read `plan-url.json` → find the relevant key
2. Send the existing `url` — URLs are permanent (no expiry)
3. If the plan content has been updated since last upload, re-run the script to push the new version (URL stays the same)

## SMS/MMS Plan Card (plan-to-image)

Deterministic pipeline that turns handoff profile data into a branded plan
card PNG (for MMS) plus PLAN.md markdown — no LLM involved. Invoked directly
by the openclaw-infra Twilio extension; the CLI contract below is frozen.

```bash
python3 {baseDir}/scripts/plan-to-image.py \
  --input <input.json> --output <out.png> [--width 1080] [--max-bytes 614400]
```

- **Input JSON:** `{ "profile": {...}, "tdee": {...}, "locale": {...} }` —
  see `examples/sample-input-with-goalweight.json` and
  `examples/sample-input-without-goalweight.json`.
- **stdout (success, single JSON line):**
  `{"ok": true, "png": "<abs path>", "bytes": N, "plan": {...}, "plan_markdown": "..."}`
- **On failure:** non-zero exit, `{"ok": false, "error": "..."}` on stdout,
  traceback on stderr.
- **Numbers:** computed by reusing `weight-loss-planner/scripts/planner-calc.py`
  (imported as a module — its interface is unchanged), anchored on the
  handoff TDEE/BMR. `goal_weight_kg: null` + `intent: lose` falls back to a
  0.75% bodyweight/week deficit and the card shows an "unlock your timeline"
  prompt instead of a completion date. `maintain` shows the maintenance zone
  with no timeline.
- **Rendering:** `templates/plan-card.html` (inline CSS) → WeasyPrint
  HTML→PDF → PyMuPDF PDF→PNG at `--width`, downscaled until it fits
  `--max-bytes` (default 600 KB MMS budget).
- **PLAN.md:** the `plan_markdown` field follows the weight-loss-planner
  PLAN.md structure (user info → plan details with calorie target → macros →
  milestones → notes) so downstream consumers (AGENTS.md gate, meal-planner
  calorie-target lookup) work unchanged. The caller is responsible for
  writing it to the workspace as `PLAN.md`.

**Dependencies:** `pip install -r {baseDir}/requirements.txt`
(`weasyprint`, `pymupdf`). WeasyPrint also needs pango/cairo/gdk-pixbuf
**system libraries** — on EC2 (Amazon Linux): `sudo dnf install -y pango
cairo gdk-pixbuf2`; on Ubuntu: `sudo apt-get install -y libpango-1.0-0
libpangocairo-1.0-0 libgdk-pixbuf-2.0-0`.

## Individual Scripts (Advanced)

### Generate HTML only (weight loss plan)
```bash
python3 {baseDir}/scripts/generate-html.py <input.md> [output.html]
```

### Generate HTML only (meal plan)
```bash
python3 {baseDir}/scripts/generate-meal-plan-html.py <input.md> [output.html]
```

The meal plan script expects Markdown in the schema defined at `meal-planner/references/meal-plan-schema.md`.

### Generate PDF only
```bash
bash {baseDir}/scripts/generate-pdf.sh <input.md> [output.pdf]
```

### Upload to cloud storage only
```bash
bash {baseDir}/scripts/upload-to-s3.sh \
  --file <path.html> \
  --bucket <name> \
  --key <document-key> \
  --workspace <path> \
  [--base-url <url>]
```

### Send file to Slack only (legacy)
```bash
bash {baseDir}/scripts/send-to-slack.sh --agent <id> --file <path> [--message <text>] [--filename <name>]
```

## Notes

- Weight loss plan HTML: blue theme, tables, Inter + Noto Sans SC fonts
- Meal plan HTML: green theme, day-card layout, responsive, print-friendly
- PDF mode uses WeasyPrint (Python) — no Chrome/browser dependency
- All formats support Chinese, English, and mixed-language content
- Cloud storage objects: set lifecycle rule on bucket for auto-cleanup (optional)
- Public URLs are permanent (`{base-url}/user/{shortId}/{key}.html`), served via Cloudflare Worker
- Same S3 key is overwritten on each upload — URL stays stable
- Agent-to-Slack-user mapping (PDF fallback) is auto-resolved from `openclaw.json` bindings
