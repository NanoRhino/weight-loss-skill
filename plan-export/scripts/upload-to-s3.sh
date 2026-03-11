#!/usr/bin/env bash
#
# upload-to-s3.sh — Upload an HTML file to cloud storage (auto-detect AWS S3 or JD Cloud OSS)
#
# Usage: upload-to-s3.sh --file <path> --bucket <name> [--workspace <path>] [--key <doc-key>] [--expiry-seconds <seconds>]
#
# Outputs the presigned URL to stdout.
# Writes plan-url.json to the workspace directory with URL, upload time, and expiry.
#
# --key: Document key for multi-document support (e.g., "weight-loss-plan", "meal-plan").
#   With --key: merges into existing plan-url.json under that key, preserving other keys.
#   Without --key: backward-compatible single-document mode (overwrites entire file).
#
# Storage backend auto-detection (in order):
#   1. PLAN_STORAGE_BACKEND env var (aws|jdoss) — force a specific backend
#   2. JD_OSS_ACCESS_KEY is set → JD Cloud OSS
#   3. aws sts get-caller-identity succeeds → AWS S3
#   4. None detected → error
#
# AWS S3 environment:
#   Standard AWS CLI credentials (IAM role, env vars, or ~/.aws/credentials)
#
# JD Cloud OSS environment variables:
#   JD_OSS_ACCESS_KEY   - JD Cloud access key (required)
#   JD_OSS_SECRET_KEY   - JD Cloud secret key (required)
#   JD_OSS_ENDPOINT     - OSS endpoint (required, e.g. https://s3.cn-north-1.jdcloud-oss.com)
#   JD_OSS_BUCKET       - Default bucket (used if --bucket not provided)

set -euo pipefail

FILE=""
BUCKET=""
WORKSPACE=""
KEY=""
EXPIRY_SECONDS=604800  # 7 days

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
if [[ ! -f "$FILE" ]]; then echo "ERROR: File not found: $FILE" >&2; exit 1; fi

# === Detect storage backend ===
detect_backend() {
  if [[ -n "${PLAN_STORAGE_BACKEND:-}" ]]; then
    echo "$PLAN_STORAGE_BACKEND"
  elif [[ -n "${JD_OSS_ACCESS_KEY:-}" ]]; then
    echo "jdoss"
  elif command -v aws &>/dev/null && aws sts get-caller-identity &>/dev/null; then
    echo "aws"
  else
    echo "ERROR: No storage backend detected. Set PLAN_STORAGE_BACKEND, JD_OSS_* env vars, or configure AWS CLI." >&2
    exit 1
  fi
}

BACKEND=$(detect_backend)
echo "Storage backend: $BACKEND" >&2

# === AWS S3 upload ===
upload_aws() {
  BUCKET="${BUCKET:-nanorhino-im-plans}"

  local UUID
  UUID=$(python3 -c "import uuid; print(uuid.uuid4())")
  S3_KEY="plans/${UUID}.html"

  echo "Uploading to s3://${BUCKET}/${S3_KEY} ..." >&2

  aws s3 cp "$FILE" "s3://${BUCKET}/${S3_KEY}" \
    --content-type "text/html; charset=utf-8" \
    --quiet

  URL=$(aws s3 presign "s3://${BUCKET}/${S3_KEY}" --expires-in "$EXPIRY_SECONDS")

  UPLOADED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  EXPIRES_AT=$(python3 -c "
from datetime import datetime, timedelta
print((datetime.utcnow() + timedelta(seconds=${EXPIRY_SECONDS})).strftime('%Y-%m-%dT%H:%M:%SZ'))
")

  echo "Presigned URL generated (expires in ${EXPIRY_SECONDS}s)" >&2
}

# === JD Cloud OSS upload ===
upload_jdoss() {
  BUCKET="${BUCKET:-${JD_OSS_BUCKET:-}}"
  if [[ -z "$BUCKET" ]]; then echo "ERROR: --bucket is required (or set JD_OSS_BUCKET)" >&2; exit 1; fi

  local RESULT
  RESULT=$(uv run --quiet --script - "$FILE" "$BUCKET" "$EXPIRY_SECONDS" << 'PYTHON_SCRIPT'
# /// script
# requires-python = ">=3.10"
# dependencies = ["boto3>=1.34"]
# ///
import sys
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3
from botocore.config import Config


def get_env(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        print(f"Error: {name} environment variable is not set", file=sys.stderr)
        sys.exit(1)
    return val


def main():
    file_path = sys.argv[1]
    bucket = sys.argv[2]
    expiry_seconds = int(sys.argv[3])

    access_key = get_env("JD_OSS_ACCESS_KEY")
    secret_key = get_env("JD_OSS_SECRET_KEY")
    endpoint = get_env("JD_OSS_ENDPOINT")

    path = Path(file_path)
    if not path.is_file():
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    s3_key = f"plans/{uuid.uuid4()}.html"

    region_match = re.search(r's3\.([^.]+)\.', endpoint)
    region = region_match.group(1) if region_match else "cn-north-1"

    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            request_checksum_calculation="when_required",
        ),
    )

    print(f"Uploading to {bucket}/{s3_key} ...", file=sys.stderr)

    s3.upload_file(
        str(path), bucket, s3_key,
        ExtraArgs={"ContentType": "text/html; charset=utf-8"},
    )

    url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": s3_key},
        ExpiresIn=expiry_seconds,
    )

    now = datetime.now(timezone.utc)
    uploaded_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    expires_at = (now + timedelta(seconds=expiry_seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")

    print(f"Presigned URL generated (expires in {expiry_seconds}s)", file=sys.stderr)

    # Output: url|uploaded_at|expires_at (pipe-separated for bash parsing)
    print(f"{url}|{uploaded_at}|{expires_at}")


if __name__ == "__main__":
    main()
PYTHON_SCRIPT
)

  URL=$(echo "$RESULT" | cut -d'|' -f1)
  UPLOADED_AT=$(echo "$RESULT" | cut -d'|' -f2)
  EXPIRES_AT=$(echo "$RESULT" | cut -d'|' -f3)
}

# === Run upload ===
case "$BACKEND" in
  aws)    upload_aws ;;
  jdoss)  upload_jdoss ;;
  *)      echo "ERROR: Unknown backend: $BACKEND" >&2; exit 1 ;;
esac

# === Write plan-url.json (shared by both backends) ===
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
    data = {}
    if os.path.exists(plan_url_file):
        try:
            with open(plan_url_file) as f:
                data = json.load(f)
            if 'url' in data and isinstance(data.get('url'), str):
                data = {'weight-loss-plan': data}
        except (json.JSONDecodeError, IOError):
            data = {}
    data[key] = entry
else:
    data = entry

with open(plan_url_file, 'w') as f:
    json.dump(data, f, indent=2)
" >&2
  echo "Wrote ${PLAN_URL_FILE}" >&2
fi

# Output URL to stdout
echo "$URL"
