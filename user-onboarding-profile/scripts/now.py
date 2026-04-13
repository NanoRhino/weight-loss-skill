#!/usr/bin/env python3
"""
now.py — Return the current ISO-8601 timestamp in the user's local timezone.

Timezone resolution order:
  1. --tz-name argument (e.g. "Asia/Shanghai") — most reliable during onboarding
  2. --tz-offset argument (seconds from UTC)
  3. USER.md > TZ Offset (if workspace provided)
  4. USER.md > Timezone (if workspace provided)
  5. Server local timezone (fallback)

Usage:
    python3 now.py --tz-name Asia/Shanghai
    python3 now.py --workspace /path/to/workspace
    python3 now.py --tz-offset 28800
    python3 now.py  # falls back to server local time

Output (JSON):
    {"now": "2026-04-13T16:30:00+08:00", "date": "2026-04-13", "tz_source": "arg_tz_name"}

tz_source values:
    - "arg_tz_name"     — from --tz-name argument
    - "arg_tz_offset"   — from --tz-offset argument
    - "user_md_offset"  — from USER.md > TZ Offset
    - "user_md_tzname"  — from USER.md > Timezone
    - "server_local"    — fallback to server's local timezone
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta


def _read_user_md(workspace: str) -> dict:
    """Read TZ Offset and Timezone from USER.md."""
    user_md = os.path.join(workspace, "USER.md")
    result = {"tz_offset": None, "tz_name": None}
    if not os.path.exists(user_md):
        return result
    try:
        with open(user_md, "r", encoding="utf-8") as f:
            content = f.read()
        m = re.search(r"\*\*TZ Offset:\*\*\s*(-?\d+)", content)
        if m:
            result["tz_offset"] = int(m.group(1))
        m = re.search(r"\*\*Timezone:\*\*\s*(\S+)", content)
        if m:
            val = m.group(1).strip()
            if val and val != "—":
                result["tz_name"] = val
    except Exception:
        pass
    return result


def _tz_from_name(name: str):
    """Get timezone object from IANA name."""
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception:
        return None


def _format_offset(td):
    """Format a timedelta as +HH:MM or -HH:MM."""
    if td is None:
        return "+00:00"
    total = int(td.total_seconds())
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    hours, remainder = divmod(total, 3600)
    minutes = remainder // 60
    return f"{sign}{hours:02d}:{minutes:02d}"


def get_now(tz_name: str = None, tz_offset: int = None, workspace: str = None) -> tuple:
    """Return (datetime_with_tz, tz_source)."""

    # Priority 1: --tz-name argument
    if tz_name:
        tz = _tz_from_name(tz_name)
        if tz:
            return datetime.now(tz), "arg_tz_name"

    # Priority 2: --tz-offset argument
    if tz_offset is not None:
        tz = timezone(timedelta(seconds=tz_offset))
        return datetime.now(tz), "arg_tz_offset"

    # Priority 3 & 4: USER.md fields
    if workspace:
        info = _read_user_md(workspace)
        if info["tz_offset"] is not None:
            tz = timezone(timedelta(seconds=info["tz_offset"]))
            return datetime.now(tz), "user_md_offset"
        if info["tz_name"]:
            tz = _tz_from_name(info["tz_name"])
            if tz:
                return datetime.now(tz), "user_md_tzname"

    # Priority 5: Server local time
    return datetime.now().astimezone(), "server_local"


def main():
    parser = argparse.ArgumentParser(description="Return current timestamp in user's timezone")
    parser.add_argument("--tz-name", type=str, default=None,
                        help="IANA timezone name (e.g. Asia/Shanghai)")
    parser.add_argument("--tz-offset", type=int, default=None,
                        help="Timezone offset in seconds from UTC (e.g. 28800)")
    parser.add_argument("--workspace", type=str, default=None,
                        help="Path to agent workspace (reads USER.md)")
    args = parser.parse_args()

    now, source = get_now(args.tz_name, args.tz_offset, args.workspace)

    iso = now.strftime("%Y-%m-%dT%H:%M:%S") + _format_offset(now.utcoffset())
    date_str = now.strftime("%Y-%m-%d")

    print(json.dumps({"now": iso, "date": date_str, "tz_source": source}))


if __name__ == "__main__":
    main()
