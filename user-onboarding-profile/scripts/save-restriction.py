#!/usr/bin/env python3
"""
save-restriction.py — Append a canonical dietary restriction to the STRUCTURED
`health-profile.md > Diet Config > Food Restrictions` list, deterministically.

Why this script exists:
  Restrictions stated mid-conversation ("no greens", "no pork") were only ever
  written to free-text `health-preferences.md` at the END of a round — and often
  not until the user escalated. Within a multi-turn exchange the agent relied on
  volatile conversation memory and re-suggested excluded foods (the "greens"
  flip-flop, agent 050184). This script lets the agent persist a restriction to a
  durable, machine-readable list THE INSTANT it is heard, before composing the
  reply, so the never-suggest rule has something concrete to honor.

  It is the deterministic half of the instruction-layer fix: the agent must still
  *notice* the restriction and call this script (instruction/LLM-dependent), but
  once called, canonical storage + de-dup is guaranteed.

What it does:
  1. Read health-profile.md in the given workspace.
  2. Ensure `## Diet Config` section exists (add it if missing, placed before
     `## Meal Schedule` if present, otherwise before `## Goals`, otherwise at the
     end of the file).
  3. Convert the `Food Restrictions` field to a STRUCTURED multi-line list under
     a `- **Food Restrictions:**` header, one term per `  - ` line.
     - Migrates a legacy inline value (e.g. `- **Food Restrictions:** No pork; no
       leafy greens`) into list items on first write.
     - A value of `None` / `—` / empty is treated as "no restrictions yet".
  4. Append the new term as `  - <term>` (optionally `  - <term> (<reason>)`).
     - De-dupes case-insensitively against existing terms (by the term text,
       ignoring any trailing reason). Re-running with the same term is a no-op.
  5. Update the top-level `**Updated:**` header to the current timestamp.

Usage:
  python3 save-restriction.py --workspace /path/to/workspace \\
    --term "leafy greens (spinach, kale, chard)" [--reason "oxalates"] \\
    [--tz-name Asia/Shanghai]

  --term   the canonical restriction term to store (required). Use a precise,
           disambiguated term — e.g. "leafy greens", NOT a vague "greens".
  --reason optional short reason, stored in parentheses after the term.
  --tz-name / --tz-offset  used only for the `**Updated:**` timestamp.

Output (JSON):
  {"ok": true, "term": "leafy greens", "mode": "appended" | "duplicate" |
   "created", "restrictions": ["No pork", "leafy greens (oxalates)"]}
  On failure: {"ok": false, "error": "..."}

Idempotent: re-running with an already-present term is a no-op (mode=duplicate).
health-profile.md is owned by user-onboarding-profile / meal-planner, so writing
here is ownership-clean.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone


def _read_user_md_tz(workspace: str) -> tuple[str | None, int | None]:
    """Return (tz_name, tz_offset_seconds) from USER.md if present."""
    user_md = os.path.join(workspace, "USER.md")
    tz_name = None
    tz_offset = None
    if os.path.exists(user_md):
        try:
            with open(user_md, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError:
            return (None, None)
        m = re.search(r"TZ Offset[:*\s]+(-?\d+)", text, re.IGNORECASE)
        if m:
            try:
                tz_offset = int(m.group(1))
            except ValueError:
                tz_offset = None
        m = re.search(r"Timezone[:*\s]+([A-Za-z]+/[A-Za-z_]+)", text)
        if m:
            tz_name = m.group(1)
    return (tz_name, tz_offset)


def _now_iso(tz_name: str | None, tz_offset: int | None) -> str:
    """Best-effort local ISO timestamp for the `**Updated:**` header."""
    tz = None
    if tz_name:
        try:
            from zoneinfo import ZoneInfo  # py3.9+

            tz = ZoneInfo(tz_name)
        except Exception:
            tz = None
    if tz is None and tz_offset is not None:
        tz = timezone(timedelta(seconds=tz_offset))
    if tz is None:
        tz = timezone.utc
    return datetime.now(tz).isoformat(timespec="seconds")


# --- markdown helpers -------------------------------------------------------

FOOD_RESTR_RE = re.compile(
    r"^- \*\*Food Restrictions:\*\*(.*)$", re.IGNORECASE
)
SUBITEM_RE = re.compile(r"^  - (.+?)\s*$")
SECTION_RE = re.compile(r"^## (.+?)\s*$")


def _split_inline_value(value: str) -> list[str]:
    """Split a legacy inline restriction value into individual terms."""
    value = value.strip()
    if not value or value in ("None", "—", "-", "[list or None]", "[list]"):
        return []
    # Split on common separators: semicolon, comma, ' and '
    parts = re.split(r"[;,]|\band\b", value)
    out = []
    for p in parts:
        p = p.strip().rstrip(".")
        if p and p.lower() not in ("none", "—", "-"):
            out.append(p)
    return out


def _term_key(item: str) -> str:
    """Normalize a list item for de-dup: lowercase, strip trailing (reason)."""
    base = re.sub(r"\s*\([^)]*\)\s*$", "", item).strip().lower()
    # also strip a leading "no " to catch "No pork" vs "pork"
    base = re.sub(r"^no\s+", "", base)
    return base


def _find_section_bounds(lines: list[str], name: str) -> tuple[int, int] | None:
    """Return (header_idx, end_idx_exclusive) for `## name`, or None."""
    start = None
    for i, ln in enumerate(lines):
        m = SECTION_RE.match(ln)
        if m and m.group(1).strip().lower() == name.lower():
            start = i
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if SECTION_RE.match(lines[j]):
            end = j
            break
    return (start, end)


def _insert_section(lines: list[str], header: str, body: list[str]) -> list[str]:
    """Insert a new `## header` block before Meal Schedule/Goals, else at end."""
    block = [header] + body
    for anchor in ("## Meal Schedule", "## Goals"):
        for i, ln in enumerate(lines):
            if ln.strip() == anchor:
                return lines[:i] + block + [""] + lines[i:]
    # append at end
    if lines and lines[-1].strip() != "":
        lines = lines + [""]
    return lines + block


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--term", required=True)
    ap.add_argument("--reason", default=None)
    ap.add_argument("--tz-name", default=None)
    ap.add_argument("--tz-offset", type=int, default=None)
    args = ap.parse_args()

    profile_path = os.path.join(args.workspace, "health-profile.md")
    if not os.path.exists(profile_path):
        print(json.dumps({"ok": False, "error": "health-profile.md not found"}))
        return 1

    term = args.term.strip()
    if not term:
        print(json.dumps({"ok": False, "error": "empty --term"}))
        return 1
    if args.reason:
        item = "{0} ({1})".format(term, args.reason.strip())
    else:
        item = term

    try:
        with open(profile_path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        print(json.dumps({"ok": False, "error": "read failed: {0}".format(e)}))
        return 1

    lines = text.split("\n")

    # Ensure Diet Config section exists
    bounds = _find_section_bounds(lines, "Diet Config")
    if bounds is None:
        lines = _insert_section(
            lines,
            "## Diet Config",
            ["- **Diet Mode:** —", "- **Food Restrictions:** None"],
        )
        bounds = _find_section_bounds(lines, "Diet Config")

    start, end = bounds
    section = lines[start:end]

    # Locate the Food Restrictions field line within the section
    fr_idx = None
    for i, ln in enumerate(section):
        if FOOD_RESTR_RE.match(ln):
            fr_idx = i
            break

    existing: list[str] = []
    if fr_idx is None:
        # No Food Restrictions field; create one right after the header line
        insert_at = 1
        section = section[:insert_at] + ["- **Food Restrictions:**"] + section[insert_at:]
        fr_idx = insert_at
    else:
        m = FOOD_RESTR_RE.match(section[fr_idx])
        inline = m.group(1) if m else ""
        existing = _split_inline_value(inline)
        # collect any existing sub-items below the field line
        k = fr_idx + 1
        while k < len(section):
            sm = SUBITEM_RE.match(section[k])
            if sm:
                existing.append(sm.group(1).strip())
                k += 1
            elif section[k].strip() == "":
                k += 1 if False else k  # don't consume blanks; stop
                break
            else:
                break
        # Normalize: header becomes bare `- **Food Restrictions:**`, drop old subitems
        # Rebuild section without the old field + its subitems
        tail_start = fr_idx + 1
        while tail_start < len(section):
            if SUBITEM_RE.match(section[tail_start]):
                tail_start += 1
            else:
                break
        section = section[:fr_idx] + section[tail_start:]
        # re-insert clean header
        section = section[:fr_idx] + ["- **Food Restrictions:**"] + section[fr_idx:]

    # De-dup
    keys = {_term_key(e) for e in existing}
    mode = "appended" if existing else "created"
    if _term_key(item) in keys:
        mode = "duplicate"
    else:
        existing.append(item)

    # Rebuild the Food Restrictions block
    block = ["- **Food Restrictions:**"]
    if existing:
        for e in existing:
            block.append("  - {0}".format(e))
    else:
        block = ["- **Food Restrictions:** None"]

    # Replace header line + (already removed) subitems with the new block
    new_section = section[:fr_idx] + block + section[fr_idx + 1:]
    lines = lines[:start] + new_section + lines[end:]

    # Update **Updated:** header
    tz_name = args.tz_name
    tz_offset = args.tz_offset
    if tz_name is None and tz_offset is None:
        tz_name, tz_offset = _read_user_md_tz(args.workspace)
    now_iso = _now_iso(tz_name, tz_offset)
    for i, ln in enumerate(lines):
        if ln.startswith("**Updated:**"):
            lines[i] = "**Updated:** {0}".format(now_iso)
            break

    out_text = "\n".join(lines)
    try:
        with open(profile_path, "w", encoding="utf-8") as f:
            f.write(out_text)
    except OSError as e:
        print(json.dumps({"ok": False, "error": "write failed: {0}".format(e)}))
        return 1

    print(
        json.dumps(
            {
                "ok": True,
                "term": term,
                "mode": mode,
                "restrictions": existing,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
