#!/usr/bin/env python3
"""
mark-onboarding-done.py — Write/update the Onboarding Completed marker in
health-profile.md with a guaranteed, machine-readable format.

Why this script exists:
  Agents have been observed writing `## Onboarding Completed\\n\\n<date>`
  (a standalone section) instead of the spec-compliant
  `## Automation\\n- **Onboarding Completed:** <date>` (a field inside the
  Automation section). Downstream code (onboarding_completed() detector in
  the miniprogram backend, and conflict-check in migration.py) parses the
  field form with a regex that does not accept the section form, so users
  who got the wrong format are treated as "not onboarded" forever.

  This script writes the field form deterministically so agents don't have
  to get it right.

What it does:
  1. Read health-profile.md in the given workspace.
  2. If a standalone `## Onboarding Completed` / `## Pattern Detection Completed`
     section exists (common agent mistake), remove it.
  3. Ensure `## Automation` section exists (add it if missing, placed right
     before `## Health Flags` if present, otherwise at end of file).
  4. Inside ## Automation, ensure two fields:
       - **Onboarding Completed:** <date>
       - **Pattern Detection Completed:** <existing or —>
     If field already present, update `Onboarding Completed` to the new date
     and leave Pattern Detection Completed alone.
  5. Update the top-level `**Updated:**` header to the current timestamp.

Usage:
  python3 mark-onboarding-done.py --workspace /path/to/workspace \\
    [--tz-name Asia/Shanghai]

  If --tz-name not provided, reads USER.md > Timezone (defaults Asia/Shanghai).

Output (JSON):
  {"ok": true, "date": "2026-05-12", "mode": "updated" | "inserted"}

  On failure:
  {"ok": false, "error": "..."}

Idempotent: re-running on already-marked workspace just updates the date
(or is a no-op if today's date is already there).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone


def _read_timezone_from_user_md(workspace: str) -> str | None:
    user_md = os.path.join(workspace, "USER.md")
    if not os.path.exists(user_md):
        return None
    try:
        with open(user_md, "r", encoding="utf-8") as f:
            content = f.read()
        m = re.search(r"\*\*Timezone:\*\*\s*(\S+)", content)
        if m:
            val = m.group(1).strip()
            if val and val != "—":
                return val
    except Exception:
        pass
    return None


def _now(tz_name: str | None) -> datetime:
    if tz_name:
        try:
            from zoneinfo import ZoneInfo
            return datetime.now(ZoneInfo(tz_name))
        except Exception:
            pass
    # Fallback: UTC+8
    return datetime.now(timezone(timedelta(hours=8)))


# Detect an erroneous standalone section like:
#   ## Onboarding Completed
#   (blank line)
#   2026-05-12
# Also matches "## Pattern Detection Completed" if the agent made the same
# mistake for that field.
_BAD_STANDALONE_RE = re.compile(
    r"^##\s+(Onboarding\s+Completed|Pattern\s+Detection\s+Completed)\s*\n+"
    r"(?:(?!^##\s)[^\n]*\n)*",  # consume until next ## section or EOF
    re.MULTILINE,
)

# Automation section — already existing
_AUTOMATION_SECTION_RE = re.compile(
    r"^##\s+Automation\s*\n((?:(?!^##\s)[^\n]*\n)*)",
    re.MULTILINE,
)

# Within Automation, the Onboarding Completed field
_ONBOARDING_FIELD_RE = re.compile(
    r"^(\s*-\s*\*\*Onboarding\s+Completed:\*\*\s*).*?\s*$",
    re.IGNORECASE | re.MULTILINE,
)

_PATTERN_FIELD_RE = re.compile(
    r"^(\s*-\s*\*\*Pattern\s+Detection\s+Completed:\*\*\s*).*?\s*$",
    re.IGNORECASE | re.MULTILINE,
)

_UPDATED_HEADER_RE = re.compile(
    r"^(\*\*Updated:\*\*)\s*.*$",
    re.MULTILINE,
)


def _extract_standalone_value(content: str) -> str | None:
    """If a '## Onboarding Completed' standalone section exists, extract its
    value (the first non-empty line after the heading). Returns None if not
    found or value unusable.
    """
    m = re.search(
        r"^##\s+Onboarding\s+Completed\s*\n+([^\n]+)",
        content, re.MULTILINE,
    )
    if not m:
        return None
    val = m.group(1).strip()
    if not val or val in ("—", "-", "none", "None"):
        return None
    return val


def _remove_bad_standalone_sections(content: str) -> str:
    """Remove any standalone '## Onboarding Completed' / '## Pattern Detection
    Completed' sections."""
    return _BAD_STANDALONE_RE.sub("", content)


def _upsert_automation_field(content: str, date_str: str) -> tuple[str, str]:
    """Ensure ## Automation section + Onboarding Completed field exist.
    Returns (new_content, mode) where mode ∈ {"updated", "inserted"}.
    """
    m_auto = _AUTOMATION_SECTION_RE.search(content)
    if m_auto:
        # Automation section exists — upsert the field
        section_body = m_auto.group(1)
        if _ONBOARDING_FIELD_RE.search(section_body):
            # Field exists — update its value
            new_section_body = _ONBOARDING_FIELD_RE.sub(
                rf"\g<1>{date_str}", section_body, count=1,
            )
            mode = "updated"
        else:
            # Field missing — append it. Keep pattern detection field if
            # already there (just add our field in front).
            pattern_match = _PATTERN_FIELD_RE.search(section_body)
            if pattern_match:
                new_section_body = section_body.replace(
                    pattern_match.group(0),
                    f"- **Onboarding Completed:** {date_str}\n"
                    + pattern_match.group(0),
                    1,
                )
            else:
                trimmed = section_body.rstrip("\n")
                new_section_body = (
                    (trimmed + "\n" if trimmed else "")
                    + f"- **Onboarding Completed:** {date_str}\n"
                    + "- **Pattern Detection Completed:** —\n"
                )
            mode = "inserted"
        new_content = content[:m_auto.start(1)] + new_section_body + content[m_auto.end(1):]
        return new_content, mode

    # Automation section missing entirely — insert it before ## Health Flags
    # if present, otherwise at end of file.
    automation_block = (
        "## Automation\n"
        f"- **Onboarding Completed:** {date_str}\n"
        "- **Pattern Detection Completed:** —\n\n"
    )
    m_flags = re.search(r"^##\s+Health\s+Flags\s*$", content, re.MULTILINE)
    if m_flags:
        insert_pos = m_flags.start()
        new_content = content[:insert_pos] + automation_block + content[insert_pos:]
    else:
        # Append at end
        if not content.endswith("\n"):
            content += "\n"
        if not content.endswith("\n\n"):
            content += "\n"
        new_content = content + automation_block
    return new_content, "inserted"


def _update_updated_header(content: str, iso_ts: str) -> str:
    if _UPDATED_HEADER_RE.search(content):
        return _UPDATED_HEADER_RE.sub(rf"\g<1> {iso_ts}", content, count=1)
    return content


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Mark onboarding as completed in health-profile.md"
    )
    parser.add_argument("--workspace", required=True,
                        help="Path to agent workspace (contains health-profile.md)")
    parser.add_argument("--tz-name", default=None,
                        help="IANA timezone name (default: read from USER.md, fallback Asia/Shanghai)")
    args = parser.parse_args()

    workspace = args.workspace
    path = os.path.join(workspace, "health-profile.md")
    if not os.path.exists(path):
        print(json.dumps({"ok": False, "error": f"health-profile.md not found: {path}"}))
        return 1

    tz_name = args.tz_name or _read_timezone_from_user_md(workspace) or "Asia/Shanghai"
    now = _now(tz_name)
    date_str = now.strftime("%Y-%m-%d")
    iso_ts = now.strftime("%Y-%m-%dT%H:%M:%S%z")
    # Insert colon in the offset: +0800 -> +08:00
    iso_ts = iso_ts[:-2] + ":" + iso_ts[-2:]

    try:
        with open(path, "r", encoding="utf-8") as f:
            original = f.read()
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"read failed: {e}"}))
        return 1

    # 1. If a bad standalone section exists, salvage its value if today's
    #    arg wasn't provided — actually we always use today's date, but
    #    removing the bad section first ensures we don't end up with both.
    content = _remove_bad_standalone_sections(original)

    # 2. Upsert the correct Automation field.
    content, mode = _upsert_automation_field(content, date_str)

    # 3. Refresh the top-level Updated timestamp.
    content = _update_updated_header(content, iso_ts)

    if content == original:
        # No actual change (already correct with today's date).
        print(json.dumps({"ok": True, "date": date_str, "mode": "noop"}))
        return 0

    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"write failed: {e}"}))
        return 1

    print(json.dumps({"ok": True, "date": date_str, "mode": mode}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
