#!/usr/bin/env python3
"""
onboarding-finalize.py — atomically finalize onboarding: sanity-check profile
files, save the initial weight record, and mark the workspace as onboarded.

Called as the *last* step of the onboarding skill (right before Step 3 begins,
or after Step 3 saves PLAN.md — the SKILL.md controls the order). Existing
practice was for the agent to remember to call weight-tracker.py save on its
own; that step gets skipped in practice (see 2026-07-02 audit: user 210.8斤
built full profile but data/weight.json never got created), so this script
enforces it.

Semantics:
- All-or-nothing. If any required profile file is missing/empty, exit non-zero
  and tell the agent exactly what's missing — the agent can then fix and retry.
  We do NOT silently mark onboarding as completed with a half-built profile.
- Idempotent. Re-running with the same weight value is a no-op (script will
  detect an existing entry within 30min and skip). Re-running with a different
  value near the same time uses weight-tracker's own correction logic.
- The initial weight save is the load-bearing side effect. Everything else
  is validation.

Usage:
    python3 onboarding-finalize.py \
      --workspace /path/to/workspace-<agent-id> \
      --weight-value 65.0 --weight-unit kg \
      --tz-offset 28800

Exit codes:
    0  — all checks passed, weight recorded, onboarding marked complete
    1  — one or more required profile files missing/empty (message on stderr)
    2  — weight-tracker.py save failed (message on stderr)

Output on success (stdout, JSON):
    {"ok": true, "weight_key": "...", "already_recorded": false}
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


# 5 files onboarding must have produced before we finalize.
# health-preferences.md is optional in practice (user may share nothing personal
# beyond the required rounds); we don't require it be non-empty.
REQUIRED_PROFILE_FILES = [
    ("USER.md", True),
    ("health-profile.md", True),
    ("PLAN.md", True),
    ("health-preferences.md", False),
]


def check_profile_files(workspace: Path):
    """Return list of (relpath, reason) for missing/empty required files.
    Empty = zero bytes OR only whitespace. required=False just checks exists."""
    problems = []
    for rel, must_be_nonempty in REQUIRED_PROFILE_FILES:
        p = workspace / rel
        if not p.is_file():
            problems.append((rel, "missing"))
            continue
        if must_be_nonempty:
            try:
                content = p.read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                problems.append((rel, f"unreadable: {e}"))
                continue
            if not content.strip():
                problems.append((rel, "empty"))
    return problems


def find_weight_tracker():
    """Locate weight-tracker.py relative to this script. Both live in the
    same skills submodule."""
    here = Path(__file__).resolve().parent
    # this file: skills/user-onboarding-profile/scripts/onboarding-finalize.py
    # tracker : skills/weight-tracking/scripts/weight-tracker.py
    tracker = here.parent.parent / "weight-tracking" / "scripts" / "weight-tracker.py"
    if not tracker.is_file():
        raise SystemExit(f"weight-tracker.py not found at {tracker}")
    return tracker


def call_weight_tracker_save(tracker: Path, data_dir: Path, value: float,
                             unit: str, tz_offset: int):
    """Invoke weight-tracker.py save. Returns the parsed JSON stdout, or
    raises on failure. weight-tracker itself is idempotent within a 30min
    correction window so re-runs won't create duplicates."""
    data_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, str(tracker), "save",
        "--data-dir", str(data_dir),
        "--value", str(value),
        "--unit", unit,
        "--tz-offset", str(tz_offset),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise RuntimeError(
            f"weight-tracker save failed (exit={r.returncode}): "
            f"stderr={r.stderr.strip()[:400]}"
        )
    try:
        return json.loads(r.stdout.strip())
    except json.JSONDecodeError as e:
        raise RuntimeError(f"weight-tracker returned non-JSON: {r.stdout[:200]}") from e


def mark_onboarding_complete(workspace: Path):
    """Idempotent touch of .onboarding-completed. health-profile.md's
    Automation > Onboarding Completed field is written separately by the
    agent per SKILL.md (using now.py). We don't duplicate that here."""
    marker = workspace / ".onboarding-completed"
    if not marker.exists():
        marker.write_text("finalized")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", required=True, help="path to workspace-<agent-id>")
    ap.add_argument("--weight-value", type=float, required=True,
                    help="initial weight numeric value")
    ap.add_argument("--weight-unit", required=True, choices=["kg", "lb"],
                    help="unit for --weight-value")
    ap.add_argument("--tz-offset", type=int, required=True,
                    help="user's TZ offset in seconds from USER.md")
    args = ap.parse_args()

    workspace = Path(args.workspace).resolve()
    if not workspace.is_dir():
        print(f"workspace not a directory: {workspace}", file=sys.stderr)
        sys.exit(1)

    # 1) Profile file sanity — fail loudly with a specific list.
    problems = check_profile_files(workspace)
    if problems:
        print("onboarding-finalize: profile incomplete, cannot finalize:", file=sys.stderr)
        for rel, reason in problems:
            print(f"  - {rel}: {reason}", file=sys.stderr)
        print("Fix these files then re-run.", file=sys.stderr)
        sys.exit(1)

    # 2) Save initial weight — but skip if this workspace has already been
    #    finalized (marker exists) AND weight.json already has entries. That
    #    covers the "agent retried finalize because it wasn't sure" case;
    #    weight-tracker's own 30min correction window doesn't handle retries
    #    hours or days later.
    marker = workspace / ".onboarding-completed"
    weight_json = workspace / "data" / "weight.json"
    weight_json_has_entries = False
    if weight_json.is_file():
        try:
            wj = json.loads(weight_json.read_text(encoding="utf-8", errors="replace"))
            weight_json_has_entries = isinstance(wj, dict) and len(wj) > 0
        except Exception:
            pass

    if marker.exists() and weight_json_has_entries:
        # Already finalized — do nothing. Return the most recent entry so
        # caller has a useful weight_key to log.
        try:
            latest_key = sorted(wj.keys())[-1] if weight_json_has_entries else None
            latest_val = wj[latest_key] if latest_key else {}
        except Exception:
            latest_key, latest_val = None, {}
        print(json.dumps({
            "ok": True,
            "weight_key": latest_key,
            "weight_value": latest_val.get("value") if isinstance(latest_val, dict) else None,
            "weight_unit": latest_val.get("unit") if isinstance(latest_val, dict) else None,
            "already_recorded": True,
        }, ensure_ascii=False))
        sys.exit(0)

    tracker = find_weight_tracker()
    data_dir = workspace / "data"
    try:
        result = call_weight_tracker_save(
            tracker, data_dir,
            args.weight_value, args.weight_unit, args.tz_offset,
        )
    except RuntimeError as e:
        print(f"onboarding-finalize: {e}", file=sys.stderr)
        sys.exit(2)

    already = result.get("action") == "corrected"

    # 3) Mark workspace as onboarded (agent still updates health-profile.md's
    #    Onboarding Completed field per SKILL.md).
    mark_onboarding_complete(workspace)

    print(json.dumps({
        "ok": True,
        "weight_key": result.get("key"),
        "weight_value": result.get("value"),
        "weight_unit": result.get("unit"),
        "already_recorded": already,
    }, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
