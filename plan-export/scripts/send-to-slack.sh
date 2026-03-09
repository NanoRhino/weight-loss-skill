#!/usr/bin/env bash
#
# send-to-slack.sh — Upload a file to a Slack user via the Slack API
#
# Usage: send-to-slack.sh --agent <id> --file <path> [--message <text>] [--filename <name>]
#
# Resolves the Slack bot token and user ID from openclaw.json automatically.
# Requires: curl, python3

set -euo pipefail

AGENT=""
FILE=""
MESSAGE=""
FILENAME=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --agent)    AGENT="$2"; shift 2 ;;
    --file)     FILE="$2"; shift 2 ;;
    --message)  MESSAGE="$2"; shift 2 ;;
    --filename) FILENAME="$2"; shift 2 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "$AGENT" ]]; then echo "ERROR: --agent is required" >&2; exit 1; fi
if [[ -z "$FILE" ]]; then echo "ERROR: --file is required" >&2; exit 1; fi
if [[ ! -f "$FILE" ]]; then echo "ERROR: File not found: $FILE" >&2; exit 1; fi

# Default filename from file path
if [[ -z "$FILENAME" ]]; then
  FILENAME="$(basename "$FILE")"
fi

# Resolve config path
CONFIG="${OPENCLAW_CONFIG:-$HOME/.openclaw/openclaw.json}"
if [[ ! -f "$CONFIG" ]]; then
  echo "ERROR: openclaw.json not found at $CONFIG" >&2
  exit 1
fi

# Extract Slack bot token from config
BOT_TOKEN=$(python3 -c "
import json, sys
c = json.load(open('$CONFIG'))
slack = c.get('channels', {}).get('slack', {})
token = slack.get('botToken', '')
if not token:
    # Try accounts
    accts = slack.get('accounts', {})
    for a in accts.values():
        if a.get('botToken'):
            token = a['botToken']
            break
if token:
    print(token)
else:
    print('NOT_FOUND')
")

if [[ "$BOT_TOKEN" == "NOT_FOUND" ]]; then
  echo "ERROR: No Slack bot token found in config" >&2
  exit 1
fi

# Resolve Slack user ID from agent binding
SLACK_USER_ID=$(python3 -c "
import json, sys
c = json.load(open('$CONFIG'))
# Top-level bindings array
bindings = c.get('bindings', [])
for b in bindings:
    if b.get('agentId') == '$AGENT' and b.get('match', {}).get('channel') == 'slack':
        print(b['match']['peer']['id'])
        sys.exit(0)
print('NOT_FOUND')
")

if [[ "$SLACK_USER_ID" == "NOT_FOUND" ]]; then
  echo "ERROR: No Slack binding found for agent $AGENT" >&2
  exit 1
fi

echo "Agent: $AGENT → Slack user: $SLACK_USER_ID"

# Step 1: Open/get DM channel with the user
DM_CHANNEL=$(curl -s -X POST "https://slack.com/api/conversations.open" \
  -H "Authorization: Bearer $BOT_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"users\":\"$SLACK_USER_ID\"}" | python3 -c "
import json, sys
r = json.load(sys.stdin)
if r.get('ok'):
    print(r['channel']['id'])
else:
    print('ERROR:' + r.get('error', 'unknown'))
")

if [[ "$DM_CHANNEL" == ERROR:* ]]; then
  echo "ERROR: Failed to open DM channel: $DM_CHANNEL" >&2
  exit 1
fi

echo "DM channel: $DM_CHANNEL"

# Step 2: Upload file using files.upload_v2
# First get upload URL
FILE_SIZE=$(stat -c%s "$FILE" 2>/dev/null || stat -f%z "$FILE")
UPLOAD_URL_RESP=$(curl -s -X POST "https://slack.com/api/files.getUploadURLExternal" \
  -H "Authorization: Bearer $BOT_TOKEN" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "filename=$FILENAME&length=$FILE_SIZE")

UPLOAD_URL=$(echo "$UPLOAD_URL_RESP" | python3 -c "
import json, sys
r = json.load(sys.stdin)
if r.get('ok'):
    print(r['upload_url'])
else:
    print('ERROR:' + r.get('error', 'unknown'))
")

FILE_ID=$(echo "$UPLOAD_URL_RESP" | python3 -c "
import json, sys
r = json.load(sys.stdin)
if r.get('ok'):
    print(r['file_id'])
else:
    print('ERROR')
")

if [[ "$UPLOAD_URL" == ERROR:* ]]; then
  echo "ERROR: Failed to get upload URL: $UPLOAD_URL" >&2
  exit 1
fi

echo "Uploading file ($FILE_SIZE bytes)..."

# Step 3: Upload the actual file
curl -s -X POST "$UPLOAD_URL" \
  -F "file=@$FILE" > /dev/null

# Step 4: Complete the upload
PAYLOAD=$(python3 -c "
import json
d = {'files': [{'id': '$FILE_ID', 'title': '$FILENAME'}], 'channel_id': '$DM_CHANNEL'}
msg = '''$MESSAGE'''
if msg:
    d['initial_comment'] = msg
print(json.dumps(d))
")

COMPLETE_RESP=$(curl -s -X POST "https://slack.com/api/files.completeUploadExternal" \
  -H "Authorization: Bearer $BOT_TOKEN" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD" | python3 -c "
import json, sys
r = json.load(sys.stdin)
if r.get('ok'):
    print('OK')
else:
    print('ERROR:' + r.get('error', 'unknown'))
")

if [[ "$COMPLETE_RESP" == ERROR:* ]]; then
  echo "ERROR: Failed to complete upload: $COMPLETE_RESP" >&2
  exit 1
fi

echo "✅ File sent to Slack user $SLACK_USER_ID ($FILENAME)"
