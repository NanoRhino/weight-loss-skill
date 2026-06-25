#!/usr/bin/env python3
"""
activation-mark-reminders-set.py — Deterministically stamp the
reminder-first activation signal inside data/engagement.json (called AFTER the
3 meal reminders are created for a not-yet-logged handoff user).

Owned by notification-manager (which owns engagement.json). When a handoff user
in First-Meal Mode has nothing to log yet and opts into meal reminders, the
coach creates the reminders via batch-create-reminders.sh and then calls this
script to record that reminder-setup happened — this counts as a tracked
activation event (read by the openclaw-infra dashboard + activation funnel), so
the user is no longer a dead lead.

Behavior:
  - Read-modify-write the `activation` block inside engagement.json.
  - Set `activation.reminders_set_at` (ISO-8601 UTC) ONLY IF it is not already a
    non-empty string — set-once, never overwritten (the signal records the FIRST
    time reminders were set up via this flow).
  - Create the `activation` block if absent; never clobber sibling fields
    (notification_stage, stage_changed_at, etc.) or sibling activation counters
    (nudges_sent, first_meal_nudges_sent, last_nudge_at).
  - Atomic write (tmp file + os.replace) under an exclusive flock, so a
    concurrent cron writing engagement.json can't lose the stamp.

Usage:
  python3 activation-mark-reminders-set.py --workspace-dir <WS>

Output (stdout): JSON
  {"status":"ok","reminders_set_at":<iso>,"already_set":<bool>}
already_set=true (and the existing value is kept) if it was already stamped.
Exit code 0 on success, 1 on hard failure (e.g. cannot write).
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
import tempfile
from datetime import datetime, timezone


def _normalize_path(p):
    """Lowercase wechat-dm/wecom-dm segment to avoid case-mismatch directories."""
    import re as _re
    return _re.sub(
        r'(workspace-(?:wechat|wecom)-dm-)([^/]+)',
        lambda m: m.group(1) + m.group(2).lower(), p,
    )


def main():
    parser = argparse.ArgumentParser(
        description="Stamp the reminder-first activation signal in engagement.json"
    )
    parser.add_argument("--workspace-dir", required=True, help="Agent workspace root")
    args = parser.parse_args()
    workspace_dir = _normalize_path(args.workspace_dir)

    path = os.path.join(workspace_dir, "data", "engagement.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)

    lockfile = path + ".lock"
    lock_fd = None
    try:
        lock_fd = open(lockfile, "w")
        fcntl.flock(lock_fd, fcntl.LOCK_EX)

        data = {}
        if os.path.exists(path):
            try:
                with open(path) as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    data = {}
            except (json.JSONDecodeError, IOError):
                data = {}

        activation = data.get("activation")
        if not isinstance(activation, dict):
            activation = {}

        existing = activation.get("reminders_set_at")
        # Set-once: only stamp if not already a non-empty string.
        if isinstance(existing, str) and existing.strip():
            print(json.dumps(
                {"status": "ok", "reminders_set_at": existing, "already_set": True},
                ensure_ascii=False,
            ))
            return 0

        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        activation["reminders_set_at"] = now_iso
        data["activation"] = activation

        # Atomic write to avoid races with the gateway / concurrent crons.
        tmp_fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        print(json.dumps(
            {"status": "ok", "reminders_set_at": now_iso, "already_set": False},
            ensure_ascii=False,
        ))
        return 0
    except Exception as e:
        print(f"[activation-mark-reminders-set] error: {e}", file=sys.stderr)
        print(json.dumps({"status": "error", "error": str(e)}, ensure_ascii=False))
        return 1
    finally:
        if lock_fd:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                lock_fd.close()
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())
