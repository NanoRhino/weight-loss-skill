#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
Check if a pending recalculation should be triggered.

Called by weight-tracking skill after a new weight is logged.
Checks if pending-recalc.json exists with reason="awaiting_weight",
and if so, signals that the full recalc should run.

Usage:
  python3 check-pending-recalc.py --workspace /path/to/workspace
"""

import argparse
import json
import sys
from pathlib import Path


def read_json(path: Path) -> dict:
    """Read and parse JSON file."""
    if not path.exists():
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(description='Check if pending recalc should trigger')
    parser.add_argument('--workspace', type=Path, required=True,
                        help='Path to user workspace directory')
    args = parser.parse_args()

    workspace = args.workspace.resolve()
    pending_json = workspace / 'data' / 'pending-recalc.json'

    # Check if pending-recalc.json exists
    pending_data = read_json(pending_json)

    if not pending_data:
        print(json.dumps({
            "should_trigger": False,
            "reason": "No pending recalc found."
        }))
        return

    # Check reason field
    reason = pending_data.get('reason')

    if reason == 'awaiting_weight':
        print(json.dumps({
            "should_trigger": True,
            "reason": "awaiting_weight",
            "cycle_date": pending_data.get('cycle_date'),
            "created_at": pending_data.get('created_at')
        }))
    elif reason == 'on_leave':
        # Don't trigger yet - wait for leave to end and next Sunday cron
        print(json.dumps({
            "should_trigger": False,
            "reason": "User is on leave. Will trigger on first Sunday after leave ends.",
            "cycle_date": pending_data.get('cycle_date')
        }))
    else:
        print(json.dumps({
            "should_trigger": False,
            "reason": f"Unknown reason: {reason}"
        }))


if __name__ == '__main__':
    main()
