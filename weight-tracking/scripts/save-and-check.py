#!/usr/bin/env python3
"""Combined save + deviation-check in a single call.

Runs weight-tracker.py save, then (if successful) runs
analyze-weight-trend.py deviation-check. Returns both results
in one JSON response so the LLM only needs one tool call.

Usage:
  python3 save-and-check.py \
    --data-dir {workspaceDir}/data \
    --value 75.2 --unit kg \
    --tz-offset 28800 \
    --plan-file {workspaceDir}/PLAN.md \
    --health-profile {workspaceDir}/health-profile.md \
    --user-file {workspaceDir}/USER.md \
    --wgs-script {weight-gain-strategy:baseDir}/scripts/analyze-weight-trend.py \
    [--correct]
"""

import argparse
import json
import os
import subprocess
import sys


def run_script(cmd):
    """Run a subprocess and return (parsed JSON or None, stderr)."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return None, result.stderr
        return json.loads(result.stdout), None
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError) as e:
        return None, str(e)


def main():
    parser = argparse.ArgumentParser(description="Save weight + deviation check")
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--value", required=True, type=float)
    parser.add_argument("--unit", required=True)
    parser.add_argument("--tz-offset", type=int, default=0)
    parser.add_argument("--correct", action="store_true")
    parser.add_argument("--plan-file", default=None)
    parser.add_argument("--health-profile", default=None)
    parser.add_argument("--user-file", default=None)
    parser.add_argument("--wgs-script", default=None,
                        help="Path to analyze-weight-trend.py")
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    tracker = os.path.join(script_dir, "weight-tracker.py")

    # --- Step 1: Save ---
    save_cmd = [
        "python3", tracker, "save",
        "--data-dir", args.data_dir,
        "--value", str(args.value),
        "--unit", args.unit,
        "--tz-offset", str(args.tz_offset),
    ]
    if args.correct:
        save_cmd.append("--correct")

    save_result, save_err = run_script(save_cmd)
    if not save_result:
        print(json.dumps({
            "save": None,
            "deviation": None,
            "error": f"save failed: {save_err}",
        }, indent=2, ensure_ascii=False))
        sys.exit(1)

    # --- Step 2: Deviation check (skip if no script path) ---
    deviation_result = None
    if args.wgs_script and os.path.exists(args.wgs_script):
        dev_cmd = [
            "python3", args.wgs_script, "deviation-check",
            "--data-dir", args.data_dir,
            "--tz-offset", str(args.tz_offset),
        ]
        if args.plan_file:
            dev_cmd += ["--plan-file", args.plan_file]
        if args.health_profile:
            dev_cmd += ["--health-profile", args.health_profile]
        if args.user_file:
            dev_cmd += ["--user-file", args.user_file]

        deviation_result, _ = run_script(dev_cmd)

    # --- Step 3: Auto-update TOOLS.md current_weight (best-effort) ---
    tools_updated = False
    try:
        tools_path = os.path.join(os.path.dirname(args.data_dir), "TOOLS.md")
        if os.path.exists(tools_path):
            import re
            with open(tools_path, "r", encoding="utf-8") as f:
                content = f.read()
            # Extract date from save result key
            save_date = save_result.get("key", "")[:10]
            display_val = save_result.get("value", args.value)
            display_unit = save_result.get("unit", args.unit)
            new_line = f"- **current_weight:** {display_val} {display_unit} ({save_date})"
            updated = re.sub(
                r"- \*\*current_weight:\*\*.*",
                new_line,
                content
            )
            if updated != content:
                with open(tools_path, "w", encoding="utf-8") as f:
                    f.write(updated)
                tools_updated = True
    except Exception:
        pass  # Best-effort, don't break the main flow

    print(json.dumps({
        "save": save_result,
        "deviation": deviation_result,
        "tools_updated": tools_updated,
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
