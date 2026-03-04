---
name: generate-plan-pdf
version: 1.0.0
description: "Convert Markdown plans to styled PDFs and deliver them via Slack. Use this skill after generating a weight loss plan, meal plan, or any structured Markdown document that should be delivered as a professional PDF to the user. Trigger when: (1) weight-loss-planner finishes generating PLAN.md, (2) meal-planner finishes generating a meal plan, (3) any time a Markdown document should be converted to PDF and sent to the user."
metadata:
  openclaw:
    emoji: "page_facing_up"
---

# Generate Plan PDF

Convert Markdown plans into professionally styled PDFs and deliver them directly to the user via Slack.

## When to Use

Call this skill **immediately after** generating any plan document (e.g., `PLAN.md` from weight-loss-planner). Instead of outputting the plan as text in the chat, convert it to PDF and send as a file.

## How to Use — Single Command

Run the all-in-one script to generate the PDF and send it via Slack in one step:

```bash
bash {baseDir}/scripts/generate-and-send.sh \
  --agent <YOUR_AGENT_ID> \
  --input PLAN.md \
  --message "📋 这是你的体重管理计划" \
  --filename "体重管理计划.pdf"
```

Parameters:
- `--agent` (required): Your agent ID (e.g., `007-zhuoran`)
- `--input` (required): Path to the Markdown file (relative to current workspace)
- `--message` (optional): Message to display alongside the file in Slack
- `--filename` (optional): Display name for the file in Slack (defaults to input filename with .pdf extension)

The script will:
1. Convert Markdown to a styled PDF (professional formatting with Inter + Noto Sans SC fonts)
2. Upload the PDF to the user's Slack DM (auto-resolves Slack user ID from agent binding)

## After Sending

Once the file is sent successfully, tell the user in chat that their plan has been sent — but **do NOT output the full plan text**. Example:

> "你的计划已经生成好了，我刚发给你了 📄 有什么问题随时问我！"

## Individual Scripts (Advanced)

If you need more control, you can run the steps separately:

### Generate PDF only
```bash
bash {baseDir}/scripts/generate-pdf.sh <input.md> [output.pdf]
```

### Send file to Slack only
```bash
bash {baseDir}/scripts/send-to-slack.sh --agent <id> --file <path> [--message <text>] [--filename <name>]
```

## Notes

- The stylesheet uses Google Fonts — requires internet access
- Supports Chinese, English, and mixed-language content
- Output is A4 format with colored section headers and styled tables
- Agent-to-Slack-user mapping is auto-resolved from `openclaw.json` bindings
- The generated PDF is also saved in the workspace as `<input-basename>.pdf` for reference
