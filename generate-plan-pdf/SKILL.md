---
name: generate-plan-pdf
version: 2.0.0
description: "Convert Markdown plans to styled HTML web pages (hosted on S3 with presigned URLs) or PDFs, and deliver them to users. Use after generating a weight loss plan, meal plan, or any structured Markdown document. Trigger when: (1) weight-loss-planner finishes generating PLAN.md, (2) meal-planner finishes generating a meal plan, (3) any time a Markdown document should be delivered as a professional document to the user, (4) user asks for their plan link and the previous one has expired."
metadata:
  openclaw:
    emoji: "page_facing_up"
---

# Generate Plan (HTML Web / PDF)

Convert Markdown plans into professionally styled documents and deliver them to users.

**Primary mode:** HTML web page uploaded to S3 — generates a beautiful, mobile-friendly web page and provides a presigned URL (valid 7 days).

**Fallback mode:** PDF via Slack file upload — used when S3 is not configured.

## Primary Mode: HTML + S3 Presigned URL

### Prerequisites

- S3 bucket with 30-day lifecycle rule (auto-deletion)
- AWS CLI credentials with `s3:PutObject` + `s3:GetObject` permission
- Bucket: `nanorhino-im-plans` (us-west-1)

### How to Use

```bash
URL=$(bash {baseDir}/scripts/generate-and-send.sh \
  --agent <YOUR_AGENT_ID> \
  --input PLAN.md \
  --bucket nanorhino-im-plans \
  --workspace <AGENT_WORKSPACE_PATH>)
```

Parameters:
- `--agent` (required): Your agent ID (e.g., `007-zhuoran`)
- `--input` (required): Path to the Markdown file
- `--bucket` (required for HTML mode): S3 bucket name
- `--workspace` (optional): Agent workspace path — if provided, writes `plan-url.json` there

The script outputs the presigned URL to stdout. **You are responsible for sending this URL to the user using the message tool** (works with any channel: Slack, Telegram, etc.).

### After Sending

Tell the user their plan is ready and include the link. Example:

> "你的计划已经生成好了！点击这里查看：[链接] 📄 有什么问题随时问我！"

### When PLAN.md is Updated

**Whenever PLAN.md is modified by any skill** (weight-loss-planner, meal-planner, etc.), **always re-run the upload script** to push the new version to S3. Each update generates a new UUID file and a new presigned URL. Send the new link to the user so they always have the latest version.

### plan-url.json

When `--workspace` is provided, the script writes `plan-url.json`:

```json
{
  "url": "https://nanorhino-im-plans.s3.us-west-1.amazonaws.com/plans/a3f8b2c1-xxxx.html?X-Amz-...",
  "uploaded_at": "2026-03-09T04:15:00Z",
  "expires_at": "2026-03-16T04:15:00Z"
}
```

**When a user asks for their plan link:**
1. Read `plan-url.json`
2. If `expires_at` has NOT passed → send the existing `url`
3. If `expires_at` HAS passed → re-run the script with `PLAN.md` to generate a new upload, then send the new URL

**Note:** Presigned URLs are valid for 7 days (S3 IAM user max). S3 objects are auto-deleted after 30 days by lifecycle rule. If the URL expires but the object still exists, re-running the script generates a fresh presigned URL for the same content.

## Fallback Mode: PDF via Slack

When `--bucket` is NOT provided, the script falls back to PDF generation and Slack file upload:

```bash
bash {baseDir}/scripts/generate-and-send.sh \
  --agent <YOUR_AGENT_ID> \
  --input PLAN.md \
  --message "📋 这是你的体重管理计划" \
  --filename "体重管理计划.pdf"
```

Parameters:
- `--agent` (required): Your agent ID
- `--input` (required): Path to the Markdown file
- `--message` (optional): Message alongside the file in Slack
- `--filename` (optional): Display name for the PDF in Slack

## Individual Scripts (Advanced)

### Generate HTML only
```bash
python3 {baseDir}/scripts/generate-html.py <input.md> [output.html]
```

### Generate PDF only
```bash
bash {baseDir}/scripts/generate-pdf.sh <input.md> [output.pdf]
```

### Upload to S3 only
```bash
bash {baseDir}/scripts/upload-to-s3.sh \
  --file <path.html> \
  --bucket <name> \
  [--workspace <path>]
```

### Send file to Slack only (legacy)
```bash
bash {baseDir}/scripts/send-to-slack.sh --agent <id> --file <path> [--message <text>] [--filename <name>]
```

## Notes

- HTML mode produces a mobile-friendly web page (responsive CSS, Inter + Noto Sans SC fonts)
- PDF mode uses WeasyPrint (Python) — no Chrome/browser dependency
- Both support Chinese, English, and mixed-language content
- S3 objects auto-deleted after 30 days by lifecycle rule
- Presigned URLs valid for 7 days; re-run script to get a new URL if expired
- Agent-to-Slack-user mapping (PDF fallback) is auto-resolved from `openclaw.json` bindings
