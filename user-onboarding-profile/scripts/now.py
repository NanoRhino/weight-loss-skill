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

    # Deterministically populate USER.md > Locale & Timezone (Timezone + TZ
    # Offset) on first message — for BOTH cold-onboarding and handoff users:
    python3 now.py --write-usermd --workspace /path/to/workspace --tz-name Asia/Shanghai

Output (JSON):
    {"now": "2026-04-13T16:30:00+08:00", "date": "2026-04-13", "tz_source": "arg_tz_name"}

    With --write-usermd, an extra "usermd" object is included describing what was
    written, e.g.:
    {"now": "...", "date": "...", "tz_source": "arg_tz_name",
     "usermd": {"timezone": "Asia/Shanghai", "tz_offset": 28800,
                "wrote": true, "reason": "filled_blank"}}

tz_source values:
    - "arg_tz_name"     — from --tz-name argument
    - "arg_tz_offset"   — from --tz-offset argument
    - "user_md_offset"  — from USER.md > TZ Offset
    - "user_md_tzname"  — from USER.md > Timezone
    - "server_local"    — fallback to server's local timezone

TZ Offset format convention: a BARE SIGNED INTEGER number of seconds from UTC
(e.g. -14400 for EDT/UTC-4, 28800 for Asia/Shanghai/UTC+8). No "+", no colon,
no "UTC" prefix. This matches what every reminder/date script expects.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta

# Default timezone when no arg and no resolvable USER.md zone. US-funnel product
# → US-Eastern default. Must match the reminder scripts' DEFAULT_TZ.
DEFAULT_TZ = "America/New_York"


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

    # Priority 5: US default (DEFAULT_TZ).
    # This is a US-funnel product, so when no zone is resolvable a US-Eastern
    # default is "usually right" — better than the prod server's UTC (which
    # would put a US user's "today"/"now" several hours ahead) and never a silent
    # Asia/Shanghai. Callers that need an exact user-local date should still pass
    # --tz-name / --tz-offset or a --workspace whose USER.md has Timezone/TZ
    # Offset set. Logged for observability.
    print(f"[now] WARNING: no tz-name/tz-offset arg and no USER.md "
          f"Timezone/TZ Offset — defaulting to {DEFAULT_TZ} (US default); "
          f"may be wrong for a non-Eastern user", file=sys.stderr)
    tz = _tz_from_name(DEFAULT_TZ)
    if tz:
        return datetime.now(tz), "default_us"
    # zoneinfo data somehow unavailable — last-resort server local time.
    return datetime.now().astimezone(), "server_local"


def _set_usermd_field(content: str, field: str, value: str) -> str:
    """Return content with `- **<field>:** <value>` set under the
    `## Locale & Timezone` section. Replaces an existing (possibly blank) line,
    appends the line inside the section if the field is absent, or creates the
    whole section if it's missing entirely. Idempotent."""
    line_re = re.compile(
        r"^(\s*-\s*\*\*" + re.escape(field) + r":\*\*).*$", re.MULTILINE
    )
    new_line = f"- **{field}:** {value}"

    if line_re.search(content):
        return line_re.sub(new_line, content, count=1)

    # Field absent — try to insert into an existing "## Locale & Timezone" section.
    sec_re = re.compile(r"^##\s+Locale\s*&\s*Timezone\s*$", re.MULTILINE)
    m = sec_re.search(content)
    if m:
        insert_at = content.find("\n", m.end())
        if insert_at == -1:
            return content.rstrip("\n") + "\n" + new_line + "\n"
        return content[: insert_at + 1] + new_line + "\n" + content[insert_at + 1 :]

    # No section at all — create one (keeps USER.md as the sole locale authority).
    sep = "" if content.endswith("\n") or content == "" else "\n"
    return content + sep + "\n## Locale & Timezone\n" + new_line + "\n"


def _is_blank_tz_value(val) -> bool:
    """A TZ field counts as 'needs filling' when missing, empty, or the em-dash
    placeholder used in templates."""
    if val is None:
        return True
    if isinstance(val, str):
        s = val.strip()
        return s == "" or s == "—"
    return False


def write_usermd(workspace: str, tz_name: str, tz_offset: int) -> dict:
    """Deterministically ensure USER.md has BOTH Timezone and TZ Offset populated.

    - tz_offset is written as a bare signed integer (seconds from UTC).
    - Idempotent: a USER.md that already has BOTH a non-blank Timezone AND a
      non-blank TZ Offset is left untouched (we never clobber a value that may
      have been corrected by the user / Slack sync). We only fill when at least
      one field is blank/missing — the exact prod failure mode (TZ Offset blank).
    """
    user_md = os.path.join(workspace, "USER.md")
    existing = _read_user_md(workspace) if os.path.exists(workspace) else {
        "tz_offset": None, "tz_name": None
    }

    have_offset = not _is_blank_tz_value(existing.get("tz_offset"))
    have_name = not _is_blank_tz_value(existing.get("tz_name"))
    if have_offset and have_name:
        return {"timezone": existing["tz_name"], "tz_offset": existing["tz_offset"],
                "wrote": False, "reason": "already_populated"}

    try:
        with open(user_md, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        content = "# User Profile\n"
    except Exception as e:
        return {"wrote": False, "reason": f"read_error:{e}"}

    if tz_name:
        content = _set_usermd_field(content, "Timezone", tz_name)
    # Always write a numeric offset (bare signed integer seconds).
    content = _set_usermd_field(content, "TZ Offset", str(int(tz_offset)))

    try:
        with open(user_md, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        return {"wrote": False, "reason": f"write_error:{e}"}

    reason = "filled_blank" if (have_offset or have_name) else "created"
    return {"timezone": tz_name, "tz_offset": int(tz_offset),
            "wrote": True, "reason": reason}


def main():
    parser = argparse.ArgumentParser(description="Return current timestamp in user's timezone")
    parser.add_argument("--tz-name", type=str, default=None,
                        help="IANA timezone name (e.g. Asia/Shanghai)")
    parser.add_argument("--tz-offset", type=int, default=None,
                        help="Timezone offset in seconds from UTC (e.g. 28800)")
    parser.add_argument("--workspace", type=str, default=None,
                        help="Path to agent workspace (reads USER.md)")
    parser.add_argument("--write-usermd", action="store_true",
                        help="Populate USER.md > Locale & Timezone (Timezone + "
                             "TZ Offset) deterministically. Requires --workspace.")
    args = parser.parse_args()

    now, source = get_now(args.tz_name, args.tz_offset, args.workspace)

    iso = now.strftime("%Y-%m-%dT%H:%M:%S") + _format_offset(now.utcoffset())
    date_str = now.strftime("%Y-%m-%d")

    out = {"now": iso, "date": date_str, "tz_source": source}

    if args.write_usermd:
        if not args.workspace:
            print("[now] ERROR: --write-usermd requires --workspace", file=sys.stderr)
            sys.exit(2)
        # Offset for the resolved 'now' — the actual UTC offset at this instant
        # (handles DST correctly because it comes from the live datetime, not a
        # static table). Bare signed integer seconds.
        offset_seconds = int(now.utcoffset().total_seconds()) if now.utcoffset() else 0
        out["usermd"] = write_usermd(args.workspace, args.tz_name, offset_seconds)

    print(json.dumps(out))


if __name__ == "__main__":
    main()
