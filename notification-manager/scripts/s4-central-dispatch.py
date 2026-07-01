#!/usr/bin/env python3
"""
s4-central-dispatch.py — Central dispatcher for Stage 4 (monthly) recall messages.

Runs once daily (lunch slot). Asks the lifecycle API which users need a recall
today, filters to monthly (Stage 4), and outputs the routing info for each.

Lifecycle API is the single source of truth: GET /v1/lifecycle/due already does
stage resolution + 30-day cadence + same-day dedup, so this script no longer
scans workspaces or reads engagement.json.

Usage:
  python3 s4-central-dispatch.py --openclaw-dir <ignored> --tz-offset 28800
  python3 s4-central-dispatch.py --mark-sent <workspace_dir|account_id>

Output (stdout): JSON array, each object:
    workspace_dir, session_key, channel, target, stage(=4), days_silent

  If no users need monthly recall today, outputs: []
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error

# 2026-07-01 重命名过渡:新名 DATA_API_URL 优先,老名 LIFECYCLE_API_URL 兼容
LIFECYCLE_API = os.environ.get("DATA_API_URL") or os.environ.get("LIFECYCLE_API_URL", "http://127.0.0.1:3100")


def log(msg):
    print(f"[s4-dispatch] {msg}", file=sys.stderr)


def _account_id(s):
    """Accept a workspace dir, session key, or bare account id → return account id."""
    base = os.path.basename(os.path.normpath(s)) if "/" in s else s
    if base.startswith("workspace-"):
        base = base[len("workspace-"):]
    for prefix in ("wechat-dm-", "wecom-dm-"):
        if base.startswith(prefix):
            return base[len(prefix):]
    return base


def fetch_due(limit=1000):
    """GET /v1/lifecycle/due → list of due users (any stage)."""
    url = f"{LIFECYCLE_API}/v1/lifecycle/due?limit={limit}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("users", [])
    except (urllib.error.URLError, json.JSONDecodeError, OSError, ValueError) as e:
        log(f"ERROR fetching /due: {e}")
        return None


def post_recall_sent(account_id, tier="monthly"):
    """POST /v1/lifecycle/recall-sent — record a sent recall (event-sourced)."""
    url = f"{LIFECYCLE_API}/v1/lifecycle/recall-sent"
    body = json.dumps({"account_id": account_id, "tier": tier}).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            json.loads(resp.read().decode("utf-8"))
        log(f"  recall-sent recorded: {account_id} ({tier})")
    except (urllib.error.URLError, OSError, ValueError) as e:
        log(f"  ERROR recall-sent for {account_id}: {e}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--openclaw-dir", default="/home/admin/.openclaw",
                        help="(ignored, kept for backward-compat)")
    parser.add_argument("--tz-offset", type=int, default=28800,
                        help="(ignored, lifecycle API handles tz)")
    parser.add_argument("--mark-sent", metavar="WORKSPACE_OR_ACCOUNT",
                        help="Record a monthly recall as sent (call after message delivered)")
    args = parser.parse_args()

    # --mark-sent mode: record recall_sent event and exit
    if args.mark_sent:
        post_recall_sent(_account_id(args.mark_sent), tier="monthly")
        return

    users = fetch_due()
    if users is None:
        print("[]")  # API failure → no dispatch (fail-safe, avoids wrong sends)
        return

    results = []
    for u in users:
        if u.get("tier") != "monthly":
            continue  # this dispatcher only handles Stage 4 monthly recall
        acc = u["account_id"]
        session_key = f"wechat-dm-{acc}"
        results.append({
            "workspace_dir": None,  # lifecycle API is source of truth; no longer workspace-based
            "session_key": session_key,
            "channel": "wechat",
            "target": acc,
            "stage": 4,
            "days_silent": u.get("days_silent", 0),
        })
        log(f"  → {session_key}: needs monthly recall (days_silent={u.get('days_silent')})")

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
