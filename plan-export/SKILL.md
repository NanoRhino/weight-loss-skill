---
name: plan-export
version: 2.2.0
description: "Convert Markdown plans to styled HTML web pages (hosted on cloud storage with presigned URLs) or PDFs, and deliver them to users. Supports weight loss plans (PLAN.md) and meal plans (MEAL-PLAN.md) with different HTML templates. Trigger when: (1) weight-loss-planner finishes generating PLAN.md, (2) meal-planner finishes generating MEAL-PLAN.md, (3) any time a Markdown document should be delivered as a professional document to the user, (4) user asks for their plan link and the previous one has expired."
metadata:
  openclaw:
    emoji: "page_facing_up"
---

# Plan Export (HTML Web / PDF)

Convert Markdown plans into professionally styled documents and deliver them to users.

**Primary mode:** HTML web page uploaded to cloud storage — generates a beautiful, mobile-friendly web page and provides a presigned URL (valid 7 days).

**Fallback mode:** PDF via Slack file upload — used when cloud storage is not configured.

## Supported Document Types

| Type | Input File | Template | Key | HTML Script |
|---|---|---|---|---|
| Weight Loss Plan | `PLAN.md` | (default) | `weight-loss-plan` | `generate-html.py` |
| Meal Plan | `MEAL-PLAN.md` | `meal-plan` | `meal-plan` | `generate-meal-plan-html.py` |

## Primary Mode: HTML + Cloud Storage Presigned URL

### Storage Backend (Auto-Detected)

The upload script automatically detects the storage backend:

1. **`PLAN_STORAGE_BACKEND`** env var (`aws` or `jdoss`) — force a specific backend
2. **`JD_OSS_ACCESS_KEY`** is set → JD Cloud OSS
3. **`aws sts get-caller-identity`** succeeds → AWS S3
4. None detected → error

**AWS S3 prerequisites:**
- S3 bucket with 30-day lifecycle rule (auto-deletion)
- AWS CLI credentials with `s3:PutObject` + `s3:GetObject` permission
- Default bucket: `nanorhino-im-plans` (us-west-1)

**JD Cloud OSS prerequisites:**
- Environment variables: `JD_OSS_ACCESS_KEY`, `JD_OSS_SECRET_KEY`, `JD_OSS_ENDPOINT`
- Default bucket: `JD_OSS_BUCKET` env var, or override with `--bucket`

### How to Use

```bash
# Weight loss plan
URL=$(bash {baseDir}/scripts/generate-and-send.sh \
  --agent <YOUR_AGENT_ID> \
  --input PLAN.md \
  --bucket <BUCKET_NAME> \
  --workspace <AGENT_WORKSPACE_PATH> \
  --key weight-loss-plan)

# Meal plan
URL=$(bash {baseDir}/scripts/generate-and-send.sh \
  --agent <YOUR_AGENT_ID> \
  --input MEAL-PLAN.md \
  --bucket <BUCKET_NAME> \
  --workspace <AGENT_WORKSPACE_PATH> \
  --template meal-plan \
  --key meal-plan)
```

Parameters:
- `--agent` (required): Your agent ID (e.g., `007-zhuoran`)
- `--input` (required): Path to the Markdown file
- `--bucket` (required for HTML mode): Storage bucket name. For JD OSS, falls back to `JD_OSS_BUCKET` env var if omitted. For AWS, defaults to `nanorhino-im-plans`.
- `--workspace` (optional): Agent workspace path — if provided, writes `plan-url.json` there
- `--template` (optional): `meal-plan` for meal plan HTML. Omit for default (weight loss plan).
- `--key` (optional): Document key in `plan-url.json`. Enables multi-document URL tracking.

The script outputs the presigned URL to stdout. **You are responsible for sending this URL to the user using the message tool** (works with any channel: Slack, Telegram, etc.).

### After Sending

Tell the user their plan is ready and include the link. Example:

> "你的计划已经生成好了！点击这里查看：[链接] 📄 有什么问题随时问我！"

### When PLAN.md or MEAL-PLAN.md is Updated

**Whenever a plan file is modified by any skill**, **always re-run the upload script** to push the new version to cloud storage. Each update generates a new UUID file and a new presigned URL. Send the new link to the user so they always have the latest version.

### plan-url.json (Multi-Document)

When `--workspace` and `--key` are provided, the script writes/merges into `plan-url.json`:

```json
{
  "weight-loss-plan": {
    "url": "https://<storage-host>/plans/uuid1.html?...",
    "uploaded_at": "2026-03-09T04:15:00Z",
    "expires_at": "2026-03-16T04:15:00Z"
  },
  "meal-plan": {
    "url": "https://<storage-host>/plans/uuid2.html?...",
    "uploaded_at": "2026-03-09T07:00:00Z",
    "expires_at": "2026-03-16T07:00:00Z"
  }
}
```

Each key is updated independently — uploading a new meal plan doesn't affect the weight loss plan entry.

**Backward compatibility:** If `--key` is omitted, the script writes a flat single-document JSON (old format). If the script encounters an old-format file when using `--key`, it auto-migrates it.

**When a user asks for their plan link:**
1. Read `plan-url.json` → find the relevant key
2. If `expires_at` has NOT passed → send the existing `url`
3. If `expires_at` HAS passed → re-run the script with the source `.md` file to generate a new upload, then send the new URL

## Fallback Mode: PDF via Slack

When `--bucket` is NOT provided, the script falls back to PDF generation and Slack file upload:

```bash
bash {baseDir}/scripts/generate-and-send.sh \
  --agent <YOUR_AGENT_ID> \
  --input PLAN.md \
  --message "📋 这是你的体重管理计划" \
  --filename "体重管理计划.pdf"
```

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
  [--workspace <path>] \
  [--key <document-key>]
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
- Cloud storage objects: set lifecycle rule on bucket for auto-deletion
- Presigned URLs valid for 7 days; re-run script to get a new URL if expired
- Agent-to-Slack-user mapping (PDF fallback) is auto-resolved from `openclaw.json` bindings
