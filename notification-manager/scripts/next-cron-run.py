#!/usr/bin/env python3
"""
next-cron-run.py — Compute seconds until the next occurrence of a 5-field cron
expression in a given IANA timezone, measured from now (or a supplied --now
epoch-seconds, for testing).

Used by create-reminder.sh to detect an "imminent first fire": a freshly created
recurring reminder whose next occurrence is only minutes away would fire during
the same session that created it (the mid-onboarding double/early-fire bug).

Usage:
  python3 next-cron-run.py --cron "15 9 * * *" --tz America/Chicago
  python3 next-cron-run.py --cron "15 9 * * *" --tz America/Chicago --now 1781399550

Output (stdout): integer seconds until the next occurrence (>= 0).
Exit codes:
  0 = ok (printed seconds)
  1 = error (could not parse / compute) — caller should treat as "unknown" and
      NOT take the imminent-fire branch (fail open: better to create normally
      than to wrongly disable a reminder).

Pure stdlib (no croniter dependency): supports the cron field syntax this repo
emits — '*', single values, comma lists, ranges 'a-b', and steps '*/n' / 'a-b/n'.

Runs on Python 3.9 (bare `python3` on EC2): `from __future__ import annotations`
defers all annotation evaluation so PEP 604 (`X | Y`) syntax is never evaluated
at runtime.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None


def expand_field(field: str, lo: int, hi: int) -> set[int]:
    out: set[int] = set()
    for part in field.split(","):
        part = part.strip()
        if not part:
            continue
        step = 1
        if "/" in part:
            base, step_s = part.split("/", 1)
            step = int(step_s)
        else:
            base = part
        if base == "*":
            start, end = lo, hi
        elif "-" in base:
            a, b = base.split("-", 1)
            start, end = int(a), int(b)
        else:
            start = end = int(base)
        for v in range(start, end + 1, step):
            if lo <= v <= hi:
                out.add(v)
    return out


def matches(dt: datetime, minutes, hours, doms, months, dows) -> bool:
    # cron DOW: 0 and 7 both = Sunday. Python weekday(): Mon=0..Sun=6.
    py_dow = dt.weekday()
    cron_dow = (py_dow + 1) % 7  # Mon=1..Sat=6, Sun=0
    dow_ok = (cron_dow in dows) or (cron_dow == 0 and 7 in dows)
    return (
        dt.minute in minutes
        and dt.hour in hours
        and dt.day in doms
        and dt.month in months
        and dow_ok
    )


def seconds_until_next(expr: str, tz_name: str, now_epoch: float | None) -> int:
    fields = expr.strip().split()
    if len(fields) != 5:
        raise ValueError(f"expected 5-field cron, got: {expr!r}")
    minutes = expand_field(fields[0], 0, 59)
    hours = expand_field(fields[1], 0, 23)
    doms = expand_field(fields[2], 1, 31)
    months = expand_field(fields[3], 1, 12)
    dows = expand_field(fields[4], 0, 7)
    if not (minutes and hours and doms and months and dows):
        raise ValueError(f"cron field expanded to empty set: {expr!r}")

    tz = ZoneInfo(tz_name) if (ZoneInfo and tz_name) else None
    if now_epoch is not None:
        now = datetime.fromtimestamp(now_epoch, tz=tz)
    else:
        now = datetime.now(tz)

    # Start from the next whole minute and scan forward up to ~13 months.
    cursor = (now + timedelta(minutes=1)).replace(second=0, microsecond=0)
    limit = cursor + timedelta(days=400)
    while cursor <= limit:
        if matches(cursor, minutes, hours, doms, months, dows):
            delta = (cursor - now).total_seconds()
            return int(max(0, delta))
        cursor += timedelta(minutes=1)
    raise ValueError(f"no occurrence within 400 days for {expr!r}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--cron", required=True)
    p.add_argument("--tz", required=True)
    p.add_argument("--now", type=float, default=None,
                   help="Epoch seconds to treat as 'now' (testing).")
    args = p.parse_args()
    try:
        print(seconds_until_next(args.cron, args.tz, args.now))
        return 0
    except Exception as e:
        print(f"next-cron-run: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
