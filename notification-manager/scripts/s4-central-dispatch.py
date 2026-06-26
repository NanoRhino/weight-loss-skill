#!/usr/bin/env python3
"""
s4-central-dispatch.py — Central dispatcher for Stage 4 (monthly) recall messages.

Runs once daily (lunch slot). Scans all user workspaces, resolves each one's
lifecycle locally (notification-manager/lifecycle-check.py), and emits routing
info for the users who are in Stage 4 (monthly recall) AND due today (>= 30 days
since their last recall, from recall.last_recall_at). No HTTP, no DB.

History: this used to call GET /v1/lifecycle/due on the 127.0.0.1:3100 lifecycle
API, which was NEVER deployed — so this dispatcher was a no-op in prod. It now
computes stage + monthly-cadence deterministically from each workspace.

Usage:
  python3 s4-central-dispatch.py --openclaw-dir /home/admin/.openclaw --tz-offset 28800
  python3 s4-central-dispatch.py --mark-sent <workspace_dir|account_id>

Output (stdout): JSON array, each object:
    workspace_dir, session_key, channel, target, stage(=4), days_silent

  If no users need monthly recall today, outputs: []
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
try:
    import importlib
    _lifecycle = importlib.import_module("lifecycle-check")
except Exception:  # noqa: BLE001
    _lifecycle = None

MONTHLY_CADENCE_DAYS = 30


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


def _channel_and_target(agent_id):
    """Derive (channel, target) from the agent/session id prefix.
    Defaults to wechat (the historical default) when no known prefix matches."""
    if agent_id.startswith("wecom-dm-"):
        return "wecom", agent_id[len("wecom-dm-"):]
    if agent_id.startswith("wechat-dm-"):
        return "wechat", agent_id[len("wechat-dm-"):]
    return "wechat", agent_id


def _monthly_due(workspace_dir):
    """True iff >= MONTHLY_CADENCE_DAYS since recall.last_recall_at (or never)."""
    eng_path = os.path.join(workspace_dir, "data", "engagement.json")
    if not os.path.exists(eng_path):
        return True
    try:
        with open(eng_path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError):
        return True
    recall = data.get("recall") if isinstance(data, dict) else None
    if not isinstance(recall, dict):
        return True
    last = recall.get("last_recall_at")
    if not (isinstance(last, str) and last.strip()):
        return True
    s = last.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return True
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    elapsed_days = (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0
    return elapsed_days >= MONTHLY_CADENCE_DAYS


def scan(openclaw_dir, tz_offset):
    """Scan all workspaces; return the Stage-4-and-due routing list."""
    results = []
    if _lifecycle is None:
        log("lifecycle-check.py not importable — cannot resolve stages")
        return results
    if not os.path.isdir(openclaw_dir):
        log(f"openclaw dir not found: {openclaw_dir}")
        return results

    for entry in sorted(os.listdir(openclaw_dir)):
        if not entry.startswith("workspace-"):
            continue
        workspace_dir = os.path.join(openclaw_dir, entry)
        if not os.path.isdir(workspace_dir):
            continue
        agent_id = entry[len("workspace-"):]
        try:
            state = _lifecycle.resolve(workspace_dir, tz_offset)
        except Exception as e:  # noqa: BLE001
            log(f"resolve failed for {agent_id}: {e}")
            continue
        if state.get("stage") != 4:
            continue
        if not _monthly_due(workspace_dir):
            continue
        channel, target = _channel_and_target(agent_id)
        results.append({
            "workspace_dir": workspace_dir,
            "session_key": agent_id,
            "channel": channel,
            "target": target,
            "stage": 4,
            "days_silent": state.get("days_silent", 0),
        })
        log(f"  → {agent_id}: needs monthly recall (days_silent={state.get('days_silent')})")
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--openclaw-dir", default="/home/admin/.openclaw",
                        help="Path to ~/.openclaw (workspaces live under it)")
    parser.add_argument("--tz-offset", type=int, default=28800,
                        help="Timezone offset in seconds from UTC")
    parser.add_argument("--mark-sent", metavar="WORKSPACE_OR_ACCOUNT",
                        help="Record a monthly recall as sent (call after message delivered)")
    args = parser.parse_args()

    # --mark-sent mode: bump the local monthly recall counter and exit.
    if args.mark_sent:
        if _lifecycle is None:
            log("lifecycle-check.py not importable — cannot mark recall sent")
            return
        # Resolve the workspace dir: --mark-sent may be a full workspace path or
        # a bare account/session id (then we cannot bump without a path).
        ws = args.mark_sent
        if "/" not in ws:
            ws = os.path.join(args.openclaw_dir, f"workspace-{ws}")
        try:
            _lifecycle.mark_recall_sent(ws, "monthly")
            log(f"  recall-sent recorded (monthly): {ws}")
        except Exception as e:  # noqa: BLE001
            log(f"  ERROR recall-sent for {ws}: {e}")
        return

    results = scan(args.openclaw_dir, args.tz_offset)
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
