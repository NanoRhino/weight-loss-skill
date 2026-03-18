---
name: jdcloud-oss-upload
description: Upload local files to JD Cloud OSS and get presigned URLs (15 min expiry). Use when needing to share local files via URL, send images to chat channels that require public URLs, or upload any file to cloud storage. Supports images, PDFs, videos, and any file type.
metadata:
  openclaw:
    emoji: "☁️"
    requires:
      bins: ["uv"]
---

# JD Cloud OSS Upload

> ⚠️ **SILENT OPERATION:** Never narrate internal actions, skill transitions, or tool calls to the user. No "Let me check...", "Now I'll transition to...", "Reading your profile...". Just do it silently and respond with the result.


Upload a local file to JD Cloud OSS and get a presigned URL (default 15 min expiry).

## Usage

```bash
uv run {baseDir}/scripts/upload.py <file_path> [--bucket BUCKET] [--prefix PREFIX] [--expires 900]
```

## Examples

Upload an image:
```bash
uv run {baseDir}/scripts/upload.py ./screenshot.png
```

Upload with custom expiry (1 hour):
```bash
uv run {baseDir}/scripts/upload.py ./report.pdf --expires 3600
```

Upload to specific bucket and prefix:
```bash
uv run {baseDir}/scripts/upload.py ./photo.jpg --bucket my-bucket --prefix images/2026
```

## Environment Variables

| Variable | Description |
|---|---|
| `JD_OSS_ACCESS_KEY` | JD Cloud access key ID |
| `JD_OSS_SECRET_KEY` | JD Cloud secret access key |
| `JD_OSS_ENDPOINT` | OSS endpoint URL (e.g. `https://s3.cn-north-1.jdcloud-oss.com`) |
| `JD_OSS_BUCKET` | Default bucket name |

## Output

The script prints two lines:
- `URL: <presigned-url>` — the presigned URL
- `MEDIA: <presigned-url>` — for OpenClaw auto-attach to chat

## Notes

- Presigned URLs default to 15 min expiry; use `--expires` to adjust.
- Files get unique keys: `prefix/timestamp-hash-filename` to avoid collisions.
- Content-Type is auto-detected from file extension.
- JD Cloud OSS is S3-compatible; the script uses boto3 with S3v4 signatures.
