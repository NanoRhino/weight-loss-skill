#!/usr/bin/env python3
"""
batch-create.py — Create multiple cron jobs with a single cron-list fetch.

Resolves timezone and delivery target once, fetches existing jobs once,
computes all anti-burst slots with awareness of slots allocated within the
batch, then creates each job via `openclaw cron add`.

Usage:
  python3 batch-create.py --agent <id> --channel <ch> --jobs '<JSON array>'
  python3 batch-create.py --agent <id> --channel <ch> --jobs-file jobs.json

JSON array format:
  [
    {"name": "Breakfast reminder", "message": "Run notification-composer for breakfast.", "cron": "45 6 * * *", "type": "meal"},
    {"name": "Lunch reminder", "message": "Run notification-composer for lunch.", "cron": "45 11 * * *", "type": "meal"},
    ...
  ]

Each job object supports: name (required), message (required), cron (required),
type (meal|weight|other, default: other), exact (bool, default: false).
"""

import argparse
import json
import os
import re
import subprocess
import sys

# Re-use find-slot logic
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.normpath(os.path.join(_SCRIPT_DIR, "..", "..", "..", ".."))
_STATE_DIR = os.environ.get("OPENCLAW_STATE_DIR", os.path.join(_PROJECT_ROOT, ".openclaw-gateway"))

sys.path.insert(0, _SCRIPT_DIR)
from importlib import import_module
find_slot = import_module("find-slot")


def parse_args():
    p = argparse.ArgumentParser(description="Batch-create cron jobs")
    p.add_argument("--agent", required=True)
    p.add_argument("--channel", default="slack")
    p.add_argument("--to", default="", help="Explicit delivery target")
    p.add_argument("--jobs", default="", help="JSON array of job definitions")
    p.add_argument("--jobs-file", default="", help="Path to JSON file with job array")
    return p.parse_args()


def detect_timezone(agent: str) -> str:
    """Auto-detect timezone from USER.md, same logic as create-reminder.sh."""
    helpers_path = os.path.expanduser("~/.openclaw/backend-service/scripts/usermd-helpers.sh")
    ws_candidates = [
        os.path.join(_STATE_DIR, f"workspace-{agent}"),
    ]
    for ws_dir in ws_candidates:
        usermd = os.path.join(ws_dir, "USER.md")
        if not os.path.exists(usermd):
            continue
        if os.path.exists(helpers_path):
            try:
                result = subprocess.run(
                    ["bash", "-c", f'source "{helpers_path}" && usermd_read "{ws_dir}" "Timezone"'],
                    capture_output=True, text=True, timeout=5,
                )
                tz = result.stdout.strip()
                if tz:
                    print(f"Auto-detected timezone: {tz}", file=sys.stderr)
                    return tz
            except Exception:
                pass
        # Fallback: grep USER.md directly
        try:
            with open(usermd, "r") as f:
                for line in f:
                    m = re.match(r"^[-*]\s*\*{0,2}Timezone\*{0,2}\s*[:：]\s*(.+)", line.strip())
                    if m:
                        tz = m.group(1).strip()
                        if tz and tz != "—":
                            print(f"Auto-detected timezone from USER.md: {tz}", file=sys.stderr)
                            return tz
        except Exception:
            pass

    print("WARNING: No timezone found, falling back to Asia/Shanghai", file=sys.stderr)
    return "Asia/Shanghai"


def resolve_delivery_target(agent: str, channel: str, explicit_to: str) -> str:
    """Resolve --to, same logic as create-reminder.sh."""
    if explicit_to:
        return explicit_to

    if channel == "slack":
        config_path = os.path.join(_STATE_DIR, "openclaw.json")
        with open(config_path, "r") as f:
            cfg = json.load(f)
        for b in cfg.get("bindings", []):
            if (b.get("agentId") == agent
                    and b.get("match", {}).get("channel") == "slack"):
                return "user:" + b["match"]["peer"]["id"]
        print(f"ERROR: No Slack binding found for agent {agent}", file=sys.stderr)
        sys.exit(1)

    if channel in ("app", "webchat"):
        return "http://127.0.0.1:8100/cron-webhook"

    if channel in ("wechat", "wecom"):
        user_id = re.sub(r"^(wechat|wecom)-dm-", "", agent)
        if user_id == agent:
            print(f"ERROR: Cannot extract userId from agent '{agent}'", file=sys.stderr)
            sys.exit(1)
        return user_id

    print(f"ERROR: --to is required for channel '{channel}'", file=sys.stderr)
    sys.exit(1)


def build_cron_cmd(agent, channel, to_target, name, message, cron_expr, tz):
    """Build the openclaw cron add command."""
    if channel in ("app", "webchat"):
        bridge_url = "http://127.0.0.1:8100/cron-deliver"
        wrapped = (
            f"{message}\n\n"
            f"IMPORTANT: After composing your response, you MUST deliver it to the app by running this exec command "
            f"(replace YOUR_MESSAGE with your actual composed message, properly escaped for JSON):\n"
            f"exec command: curl -s -X POST '{bridge_url}' -H 'Content-Type: application/json' "
            f"-d '{{\"agent_id\": \"{agent}\", \"message\": \"YOUR_MESSAGE\", \"type\": \"other\", "
            f"\"cron_name\": \"{name}\", \"channel\": \"app\"}}'\n"
            f"Do NOT output the message as your reply. Instead, put your full message text into the curl command "
            f"above and execute it. Reply with only: NO_REPLY"
        )
        cmd = [
            "openclaw", "cron", "add",
            "--name", name,
            "--session", "isolated",
            "--agent", agent,
            "--message", wrapped,
            "--no-deliver",
            "--json",
            "--cron", cron_expr,
            "--tz", tz,
        ]
    else:
        cmd = [
            "openclaw", "cron", "add",
            "--name", name,
            "--session", "isolated",
            "--agent", agent,
            "--message", message,
            "--announce",
            "--channel", channel,
            "--to", to_target,
            "--cron", cron_expr,
            "--tz", tz,
        ]
    return cmd


def main():
    args = parse_args()

    # 1. Load job definitions
    if args.jobs_file:
        with open(args.jobs_file, "r") as f:
            jobs = json.load(f)
    elif args.jobs:
        jobs = json.loads(args.jobs)
    else:
        jobs = json.load(sys.stdin)

    if not jobs:
        print("No jobs to create.", file=sys.stderr)
        return

    print(f"Batch creating {len(jobs)} cron jobs...", file=sys.stderr)

    # 2. Resolve shared params ONCE
    tz = detect_timezone(args.agent)
    to_target = resolve_delivery_target(args.agent, args.channel, args.to)
    print(f"Agent: {args.agent} → Channel: {args.channel} → To: {to_target}", file=sys.stderr)

    # 3. Fetch existing cron jobs ONCE
    existing_jobs = find_slot.get_existing_jobs()
    counts = find_slot.build_utc_minute_counts(existing_jobs)
    print(f"Fetched {len(existing_jobs)} existing jobs", file=sys.stderr)

    # 4. Process each job
    results = []
    for i, job in enumerate(jobs):
        name = job["name"]
        message = job["message"]
        cron_expr = job["cron"]
        job_type = job.get("type", "other")
        exact = job.get("exact", False)

        print(f"\n[{i+1}/{len(jobs)}] {name}", file=sys.stderr)

        # Anti-burst slot finding (using shared counts, updated per allocation)
        if not exact:
            target_utc_mins = find_slot.cron_to_utc_minutes(cron_expr, tz)
            if target_utc_mins:
                target_utc_min = target_utc_mins[0]

                if job_type in ("meal", "weight"):
                    window_before, window_after = 10, 5
                else:
                    window_before, window_after = 10, 0

                if counts.get(target_utc_min, 0) >= find_slot.MAX_PER_MINUTE:
                    chosen, is_fallback = find_slot.find_available_slot(
                        target_utc_min, window_before, window_after, counts
                    )
                    if not is_fallback:
                        new_h, new_m = find_slot.utc_minute_to_local(chosen, tz)
                        adjusted = find_slot.adjust_cron_expr(cron_expr, new_h, new_m)
                        print(f"  Anti-burst: {cron_expr} → {adjusted}", file=sys.stderr)
                        cron_expr = adjusted
                        target_utc_min = chosen
                    else:
                        print(f"  Anti-burst: window full, using original", file=sys.stderr)

                # Update counts so next job in batch sees this allocation
                for utc_min in find_slot.cron_to_utc_minutes(cron_expr, tz):
                    counts[utc_min] = counts.get(utc_min, 0) + 1

        # Create the job
        cmd = build_cron_cmd(args.agent, args.channel, to_target, name, message, cron_expr, tz)
        print(f"  Creating: {name} ({cron_expr})", file=sys.stderr)
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=_STATE_DIR)
            if result.returncode == 0:
                print(f"  ✓ Created", file=sys.stderr)
                results.append({"name": name, "cron": cron_expr, "status": "created"})
            else:
                err = result.stderr.strip()
                print(f"  ✗ Failed: {err}", file=sys.stderr)
                results.append({"name": name, "cron": cron_expr, "status": "failed", "error": err})
        except Exception as e:
            print(f"  ✗ Error: {e}", file=sys.stderr)
            results.append({"name": name, "cron": cron_expr, "status": "error", "error": str(e)})

    # 5. Summary
    created = sum(1 for r in results if r["status"] == "created")
    failed = len(results) - created
    print(f"\nDone: {created} created, {failed} failed", file=sys.stderr)
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
