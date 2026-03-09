#!/usr/bin/env bash
#
# upload-to-s3.sh — Upload an HTML file to S3 with a UUID path and return a presigned URL
#
# Usage: upload-to-s3.sh --file <path> --bucket <name> [--workspace <path>] [--key <doc-key>] [--expiry-seconds <seconds>]
#
# Outputs the presigned URL to stdout.
# Writes plan-url.json to the workspace directory with URL, upload time, and expiry.
#
# --key: Document key for multi-document support (e.g., "weight-loss-plan", "meal-plan").
#   With --key: merges into existing plan-url.json under that key, preserving other keys.
#   Without --key: backward-compatible single-document mode (overwrites entire file).

set -euo pipefail

FILE=""
BUCKET=""
WORKSPACE=""
KEY=""
EXPIRY_SECONDS=604800  # 7 days (max for IAM user credentials)

while [[ $# -gt 0 ]]; do
  case $1 in
    --file)           FILE="$2"; shift 2 ;;
    --bucket)         BUCKET="$2"; shift 2 ;;
    --workspace)      WORKSPACE="$2"; shift 2 ;;
    --key)            KEY="$2"; shift 2 ;;
    --expiry-seconds) EXPIRY_SECONDS="$2"; shift 2 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "$FILE" ]]; then echo "ERROR: --file is required" >&2; exit 1; fi
if [[ -z "$BUCKET" ]]; then echo "ERROR: --bucket is required" >&2; exit 1; fi
if [[ ! -f "$FILE" ]]; then echo "ERROR: File not found: $FILE" >&2; exit 1; fi

# Generate UUID
UUID=$(python3 -c "import uuid; print(uuid.uuid4())")
S3_KEY="plans/${UUID}.html"

echo "Uploading to s3://${BUCKET}/${S3_KEY} ..." >&2

# Upload to S3
aws s3 cp "$FILE" "s3://${BUCKET}/${S3_KEY}" \
  --content-type "text/html; charset=utf-8" \
  --quiet

# Generate presigned URL
URL=$(aws s3 presign "s3://${BUCKET}/${S3_KEY}" --expires-in "$EXPIRY_SECONDS")

UPLOADED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
EXPIRES_AT=$(python3 -c "
from datetime import datetime, timedelta
print((datetime.utcnow() + timedelta(seconds=${EXPIRY_SECONDS})).strftime('%Y-%m-%dT%H:%M:%SZ'))
")

echo "Presigned URL generated (expires in ${EXPIRY_SECONDS}s)" >&2

# Write plan-url.json if workspace is specified
if [[ -n "$WORKSPACE" ]]; then
  PLAN_URL_FILE="${WORKSPACE}/plan-url.json"

  python3 -c "
import json, os

url = '''${URL}'''
uploaded_at = '${UPLOADED_AT}'
expires_at = '${EXPIRES_AT}'
key = '${KEY}'
plan_url_file = '${PLAN_URL_FILE}'

entry = {
    'url': url,
    'uploaded_at': uploaded_at,
    'expires_at': expires_at
}

if key:
    # Multi-key mode: merge into existing file
    data = {}
    if os.path.exists(plan_url_file):
        try:
            with open(plan_url_file) as f:
                data = json.load(f)
            # Handle migration from old single-doc format
            if 'url' in data and isinstance(data.get('url'), str):
                # Old format — wrap in 'weight-loss-plan' key
                data = {'weight-loss-plan': data}
        except (json.JSONDecodeError, IOError):
            data = {}
    data[key] = entry
else:
    # Backward-compatible single-doc mode
    data = entry

with open(plan_url_file, 'w') as f:
    json.dump(data, f, indent=2)
" >&2
  echo "Wrote ${PLAN_URL_FILE}" >&2
fi

# Output URL to stdout (only the URL, everything else goes to stderr)
echo "$URL"
