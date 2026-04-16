#!/usr/bin/env bash
# inject-context.sh — Inject a message into the user's main session transcript
# via chat.inject (zero LLM cost, no agent turn triggered).
#
# Usage:
#   bash inject-context.sh --workspace-dir /path/to/workspace --message "提醒内容"
#
# The script derives the sessionKey from the workspace directory name:
#   workspace-wechat-dm-accxxx → agent:wechat-dm-accxxx:direct:accxxx

set -euo pipefail

WORKSPACE_DIR=""
MESSAGE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --workspace-dir) WORKSPACE_DIR="$2"; shift 2 ;;
    --message)       MESSAGE="$2";       shift 2 ;;
    *)               echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "$WORKSPACE_DIR" ]]; then
  echo "ERROR: --workspace-dir is required" >&2
  exit 1
fi

if [[ -z "$MESSAGE" ]]; then
  echo "ERROR: --message is required" >&2
  exit 1
fi

# Derive agentId from workspace dir name
# /home/admin/.openclaw/workspace-wechat-dm-accxxx → wechat-dm-accxxx
BASENAME=$(basename "$WORKSPACE_DIR")
AGENT_ID="${BASENAME#workspace-}"

if [[ "$AGENT_ID" == "$BASENAME" ]]; then
  echo "ERROR: could not derive agentId from workspace dir: $WORKSPACE_DIR" >&2
  exit 1
fi

# Derive accountId from agentId
# wechat-dm-accxxx → accxxx
# wechat-group-groupxxx → groupxxx
ACCOUNT_ID=""
if [[ "$AGENT_ID" == wechat-dm-* ]]; then
  ACCOUNT_ID="${AGENT_ID#wechat-dm-}"
elif [[ "$AGENT_ID" == wechat-group-* ]]; then
  ACCOUNT_ID="${AGENT_ID#wechat-group-}"
else
  echo "ERROR: unsupported agent type: $AGENT_ID" >&2
  exit 1
fi

SESSION_KEY="agent:${AGENT_ID}:direct:${ACCOUNT_ID}"

# Escape message for JSON (handle quotes, newlines, backslashes)
JSON_MESSAGE=$(python3 -c "import json,sys; print(json.dumps(sys.argv[1]))" "$MESSAGE")

PARAMS="{\"sessionKey\":\"${SESSION_KEY}\",\"message\":${JSON_MESSAGE}}"

# Call chat.inject via gateway CLI
RESULT=$(openclaw gateway call chat.inject --params "$PARAMS" --json --timeout 5000 2>/dev/null) || {
  echo "ERROR: chat.inject call failed" >&2
  echo "$RESULT" >&2
  exit 1
}

# Check result
OK=$(echo "$RESULT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('ok', False))" 2>/dev/null || echo "False")

if [[ "$OK" == "True" ]]; then
  MSG_ID=$(echo "$RESULT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('messageId', ''))" 2>/dev/null || echo "")
  echo "{\"ok\":true,\"messageId\":\"${MSG_ID}\",\"sessionKey\":\"${SESSION_KEY}\"}"
else
  echo "ERROR: chat.inject returned non-ok" >&2
  echo "$RESULT" >&2
  exit 1
fi
