#!/usr/bin/env python3
"""
find-slot.py — Find an available cron minute slot to avoid simultaneous sends.

Given a target cron expression and timezone, examines all existing recurring cron
jobs and finds a nearby minute where fewer than MAX_PER_MINUTE jobs are scheduled.

Usage:
  python3 find-slot.py --cron "45 11 * * *" --tz "Asia/Shanghai" --type meal
  python3 find-slot.py --cron "30 7 * * 3,6" --tz "Asia/Shanghai" --type weight

Output (stdout): adjusted cron expression (e.g. "47 11 * * *")
If no adjustment needed, outputs the original expression unchanged.

Exit codes:
  0 = success (adjusted or unchanged)
  1 = error
  2 = window full, using original (warning printed to stderr)
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import timezone, timedelta
from zoneinfo import ZoneInfo

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.normpath(os.path.join(_SCRIPT_DIR, "..", "..", "..", ".."))
_STATE_DIR = os.environ.get("OPENCLAW_STATE_DIR", os.path.join(_PROJECT_ROOT, ".openclaw-gateway"))

MAX_PER_MINUTE = 2


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--cron", required=True, help="5-field cron expression")
    p.add_argument("--tz", required=True, help="Timezone for this cron")
    p.add_argument(
        "--type",
        choices=["meal", "weight", "other"],
        default="other",
        help="Job type determines search window",
    )
    return p.parse_args()


def cron_to_utc_minutes(expr: str, tz_name: str) -> list[int]:
    """
    Convert a cron expression's hour:minute + timezone to a list of UTC
    minute-of-day values (0-1439). Returns a list because some cron expressions
    may have multiple hours/minutes (e.g. "0,30 8 * * *").

    Only extracts minute and hour fields; ignores day/month/dow for simplicity
    (per design: we count all recurring jobs regardless of day overlap).
    """
    fields = expr.strip().split()
    if len(fields) != 5:
        raise ValueError(f"Expected 5-field cron, got: {expr}")

    minutes = _expand_field(fields[0], 0, 59)
    hours = _expand_field(fields[1], 0, 23)

    tz = ZoneInfo(tz_name)
    utc_minutes = set()

    for h in hours:
        for m in minutes:
            # Use a reference date to convert local -> UTC
            # We pick a non-DST-ambiguous date; slight inaccuracy near DST
            # transitions is acceptable for slot distribution purposes
            from datetime import datetime

            local_dt = datetime(2026, 6, 15, h, m, tzinfo=tz)
            utc_dt = local_dt.astimezone(timezone.utc)
            utc_min = utc_dt.hour * 60 + utc_dt.minute
            utc_minutes.add(utc_min)

    return list(utc_minutes)


def _expand_field(field: str, lo: int, hi: int) -> list[int]:
    """Expand a single cron field into a list of integer values."""
    results = set()
    for part in field.split(","):
        if "/" in part:
            range_part, step = part.split("/", 1)
            step = int(step)
            if range_part == "*":
                start, end = lo, hi
            elif "-" in range_part:
                start, end = map(int, range_part.split("-", 1))
            else:
                start, end = int(range_part), hi
            results.update(range(start, end + 1, step))
        elif "-" in part:
            a, b = map(int, part.split("-", 1))
            results.update(range(a, b + 1))
        elif part == "*":
            results.update(range(lo, hi + 1))
        else:
            results.add(int(part))
    return sorted(results)


def get_existing_jobs() -> list[dict]:
    """Fetch all cron jobs from the gateway."""
    try:
        result = subprocess.run(
            ["openclaw", "cron", "list", "--json"],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=_STATE_DIR,
        )
        if result.returncode != 0:
            print(f"WARNING: cron list failed: {result.stderr}", file=sys.stderr)
            return []
        data = json.loads(result.stdout)
        return data.get("jobs", [])
    except Exception as e:
        print(f"WARNING: cron list error: {e}", file=sys.stderr)
        return []


def build_utc_minute_counts(jobs: list[dict]) -> dict[int, int]:
    """
    Build a map of UTC minute-of-day -> number of recurring jobs at that minute.
    Only counts enabled, recurring (cron kind) jobs.
    """
    counts: dict[int, int] = {}
    for job in jobs:
        if not job.get("enabled", True):
            continue
        sched = job.get("schedule", {})
        if sched.get("kind") != "cron":
            continue
        expr = sched.get("expr", "")
        tz_name = sched.get("tz", "UTC")
        try:
            for utc_min in cron_to_utc_minutes(expr, tz_name):
                counts[utc_min] = counts.get(utc_min, 0) + 1
        except Exception as e:
            print(f"WARNING: skipping job {job.get('id','?')}: {e}", file=sys.stderr)
    return counts


def find_available_slot(
    target_utc_min: int, window_before: int, window_after: int, counts: dict[int, int]
) -> tuple[int, bool]:
    """
    Find an available minute slot near the target.

    Scans outward from target: target, target-1, target+1, target-2, target+2, ...
    but only within [target - window_before, target + window_after].

    Returns (chosen_utc_minute, is_fallback).
    is_fallback=True means window was full, returning original target.
    """
    lo = (target_utc_min - window_before) % 1440
    hi = (target_utc_min + window_after) % 1440

    def in_window(m: int) -> bool:
        m = m % 1440
        if lo <= hi:
            return lo <= m <= hi
        else:  # wraps around midnight
            return m >= lo or m <= hi

    # Scan outward from target
    for offset in range(0, window_before + window_after + 1):
        candidates = []
        if offset == 0:
            candidates = [target_utc_min % 1440]
        else:
            candidates = [
                (target_utc_min - offset) % 1440,
                (target_utc_min + offset) % 1440,
            ]
        for candidate in candidates:
            if in_window(candidate) and counts.get(candidate, 0) < MAX_PER_MINUTE:
                return candidate, False

    return target_utc_min % 1440, True  # fallback


def utc_minute_to_local(utc_min: int, tz_name: str) -> tuple[int, int]:
    """Convert a UTC minute-of-day back to local hour, minute."""
    from datetime import datetime

    utc_dt = datetime(2026, 6, 15, utc_min // 60, utc_min % 60, tzinfo=timezone.utc)
    local_dt = utc_dt.astimezone(ZoneInfo(tz_name))
    return local_dt.hour, local_dt.minute


def adjust_cron_expr(original_expr: str, new_hour: int, new_minute: int) -> str:
    """Replace the minute and hour fields of a cron expression."""
    fields = original_expr.strip().split()
    fields[0] = str(new_minute)
    fields[1] = str(new_hour)
    return " ".join(fields)


def main():
    args = parse_args()

    # 1. Parse target cron -> UTC minute(s)
    target_utc_mins = cron_to_utc_minutes(args.cron, args.tz)
    if not target_utc_mins:
        print(f"ERROR: could not parse cron expression: {args.cron}", file=sys.stderr)
        sys.exit(1)

    # For multi-time crons, use the first one (typical case is single hour:minute)
    target_utc_min = target_utc_mins[0]

    # 2. Determine window based on type
    if args.type in ("meal", "weight"):
        window_before = 10
        window_after = 5
    else:  # other
        window_before = 10
        window_after = 0

    # 3. Fetch existing jobs and count per-minute
    jobs = get_existing_jobs()
    counts = build_utc_minute_counts(jobs)

    # 4. Check if target is already available
    if counts.get(target_utc_min, 0) < MAX_PER_MINUTE:
        # No adjustment needed
        print(args.cron)
        sys.exit(0)

    # 5. Find available slot
    chosen_utc_min, is_fallback = find_available_slot(
        target_utc_min, window_before, window_after, counts
    )

    if is_fallback:
        print(
            f"WARNING: All slots in window are full "
            f"(target UTC minute {target_utc_min}, "
            f"window [-{window_before}, +{window_after}]). "
            f"Using original time.",
            file=sys.stderr,
        )
        print(args.cron)
        sys.exit(2)

    # 6. Convert chosen UTC minute back to local and adjust cron
    new_hour, new_minute = utc_minute_to_local(chosen_utc_min, args.tz)
    adjusted = adjust_cron_expr(args.cron, new_hour, new_minute)

    if adjusted != args.cron:
        print(
            f"Adjusted cron: {args.cron} -> {adjusted} "
            f"(slot {counts.get(target_utc_min, 0)} jobs at target, "
            f"moved to UTC :{chosen_utc_min % 60:02d})",
            file=sys.stderr,
        )

    print(adjusted)
    sys.exit(0)


if __name__ == "__main__":
    main()
