#!/usr/bin/env bash
#
# upload-to-s3.sh — Upload an HTML file to AWS S3
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
# AWS S3 environment:
#   Standard AWS CLI credentials (IAM role, env vars, or ~/.aws/credentials)

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
  # Extract accountId from agentId (strip "wechat-dm-" prefix)
  ACCOUNT_ID="${AGENT_ID#wechat-dm-}"

  # Look up shortId from agent-registry.json (located in gateway extensions dir)
  GATEWAY_DIR=$(dirname "$WORKSPACE")
  REGISTRY="${GATEWAY_DIR}/extensions/wechat/agent-registry.json"
  if [[ -f "$REGISTRY" ]]; then
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


# === Run upload ===
export UPLOAD_CONTENT_TYPE="$CONTENT_TYPE"
upload_aws

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
