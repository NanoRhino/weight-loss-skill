#!/usr/bin/env bash
#
# upload-to-s3.sh — Upload an HTML file to cloud storage (auto-detect AWS S3 or JD Cloud OSS)
#
# Usage: upload-to-s3.sh --file <path> --bucket <name> --username <name> --key <doc-key>
#                        [--workspace <path>] [--base-url <url>]
#
# Outputs the public URL to stdout.
# Writes plan-url.json to the workspace directory with URL and upload time.
#
# S3 key format: {username}/{key}.html
# Public URL format: {base-url}/{username}/{key}.html
#
# --username (optional): User identifier for the URL path. If omitted, auto-resolved
#                        from agent-registry.json using the workspace path.
#                        Resolution: workspace dir name → agentId → shortId (6-char).
#                        Falls back to agentId if shortId not found.
# --key (required): Document key (e.g., "weight-loss-plan", "meal-plan")
# --base-url: Public URL base (default: https://nanorhino.ai)
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
USERNAME=""
BASE_URL="${PLAN_BASE_URL:-https://nanorhino.ai}"

while [[ $# -gt 0 ]]; do
  case $1 in
    --file)      FILE="$2"; shift 2 ;;
    --bucket)    BUCKET="$2"; shift 2 ;;
    --workspace) WORKSPACE="$2"; shift 2 ;;
    --key)       KEY="$2"; shift 2 ;;
    --username)  USERNAME="$2"; shift 2 ;;
    --base-url)  BASE_URL="$2"; shift 2 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "$FILE" ]]; then echo "ERROR: --file is required" >&2; exit 1; fi
if [[ ! -f "$FILE" ]]; then echo "ERROR: File not found: $FILE" >&2; exit 1; fi
if [[ -z "$KEY" ]]; then echo "ERROR: --key is required" >&2; exit 1; fi

# === Auto-resolve username from workspace path if not provided ===
if [[ -z "$USERNAME" ]]; then
  if [[ -z "$WORKSPACE" ]]; then
    echo "ERROR: --username or --workspace is required" >&2; exit 1
  fi
  # Extract agentId from workspace dir name: workspace-wechat-dm-xxx → wechat-dm-xxx
  WS_BASENAME=$(basename "$WORKSPACE")
  AGENT_ID="${WS_BASENAME#workspace-}"

  # Look up shortId from agent-registry.json
  REGISTRY="${HOME}/.openclaw/extensions/wechat/agent-registry.json"
  if [[ -f "$REGISTRY" ]]; then
    # Extract accountId from agentId (strip "wechat-dm-" prefix)
    ACCOUNT_ID="${AGENT_ID#wechat-dm-}"
    USERNAME=$(python3 -c "
import json, sys
try:
    with open('${REGISTRY}') as f:
        reg = json.load(f)
    info = reg.get('agents', {}).get('${ACCOUNT_ID}', {})
    sid = info.get('shortId', '')
    if sid:
        print(sid)
    else:
        print('${ACCOUNT_ID}')
except Exception:
    print('${ACCOUNT_ID}')
" 2>/dev/null)
  else
    USERNAME="$ACCOUNT_ID"
  fi

  if [[ -z "$USERNAME" ]]; then
    echo "ERROR: Could not resolve username from workspace path" >&2; exit 1
  fi
  echo "Auto-resolved username: $USERNAME (from $AGENT_ID)" >&2
fi

# Auto-detect extension from file, default to .html
FILE_EXT="${FILE##*.}"
if [[ "$FILE_EXT" == "$FILE" ]] || [[ -z "$FILE_EXT" ]]; then
  FILE_EXT="html"
fi

S3_KEY="user/${USERNAME}/${KEY}.${FILE_EXT}"
PUBLIC_URL="${BASE_URL}/user/${USERNAME}/${KEY}.${FILE_EXT}"

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

# === Detect content type from extension and filename pattern ===
detect_content_type() {
  # weekly-data-*.html files are actually JSON data
  local basename=$(basename "$FILE")
  if echo "$basename" | grep -qE '^weekly-data-.*\.html$'; then
    echo "application/json; charset=utf-8"
    return
  fi
  case "$FILE_EXT" in
    json) echo "application/json; charset=utf-8" ;;
    *)    echo "text/html; charset=utf-8" ;;
  esac
}
CONTENT_TYPE=$(detect_content_type)

# === AWS S3 upload ===
upload_aws() {
  BUCKET="${BUCKET:-nanorhino-im-plans}"

  echo "Uploading to s3://${BUCKET}/${S3_KEY} ..." >&2

  aws s3 cp "$FILE" "s3://${BUCKET}/${S3_KEY}" \
    --content-type "$CONTENT_TYPE" \
    --cache-control "public, max-age=300" \
    --quiet

  UPLOADED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  echo "Uploaded successfully" >&2
}

# === JD Cloud OSS upload ===
upload_jdoss() {
  BUCKET="${BUCKET:-${JD_OSS_BUCKET:-}}"
  if [[ -z "$BUCKET" ]]; then echo "ERROR: --bucket is required (or set JD_OSS_BUCKET)" >&2; exit 1; fi

  UPLOADED_AT=$(uv run --quiet --script - "$FILE" "$BUCKET" "$S3_KEY" << 'PYTHON_SCRIPT'
# /// script
# requires-python = ">=3.10"
# dependencies = ["boto3>=1.34"]
# ///
import sys
import os
import re
from datetime import datetime, timezone
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
    s3_key = sys.argv[3]

    access_key = get_env("JD_OSS_ACCESS_KEY")
    secret_key = get_env("JD_OSS_SECRET_KEY")
    endpoint = get_env("JD_OSS_ENDPOINT")

    path = Path(file_path)
    if not path.is_file():
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        sys.exit(1)

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
        ExtraArgs={
            "ContentType": os.environ.get("UPLOAD_CONTENT_TYPE", "text/html; charset=utf-8"),
            "CacheControl": "public, max-age=300",
        },
    )

    now = datetime.now(timezone.utc)
    uploaded_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    print(f"Uploaded successfully", file=sys.stderr)
    print(uploaded_at)


if __name__ == "__main__":
    main()
PYTHON_SCRIPT
)
}

# === Run upload ===
export UPLOAD_CONTENT_TYPE="$CONTENT_TYPE"
case "$BACKEND" in
  aws)    upload_aws ;;
  jdoss)  upload_jdoss ;;
  *)      echo "ERROR: Unknown backend: $BACKEND" >&2; exit 1 ;;
esac

# === Write plan-url.json ===
if [[ -n "$WORKSPACE" ]]; then
  PLAN_URL_FILE="${WORKSPACE}/plan-url.json"

  python3 -c "
import json, os

public_url = '${PUBLIC_URL}'
uploaded_at = '${UPLOADED_AT}'
key = '${KEY}'
plan_url_file = '${PLAN_URL_FILE}'

entry = {
    'url': public_url,
    'uploaded_at': uploaded_at
}

data = {}
if os.path.exists(plan_url_file):
    try:
        with open(plan_url_file) as f:
            data = json.load(f)
        # Auto-migrate old single-document format
        if 'url' in data and isinstance(data.get('url'), str):
            data = {}
    except (json.JSONDecodeError, IOError):
        data = {}
data[key] = entry

with open(plan_url_file, 'w') as f:
    json.dump(data, f, indent=2)
" >&2
  echo "Wrote ${PLAN_URL_FILE}" >&2
fi

# Output public URL to stdout
echo "$PUBLIC_URL"
