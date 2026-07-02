#!/usr/bin/env python3
"""
save-medical.py — Persist a DOCTOR-reported medical fact (diagnosis / dietary
directive / protein cap / other limit) to the STRUCTURED
`health-profile.md > ## Medical` section, deterministically.

Why this script exists (mirrors save-restriction.py):
  We are a nutritionist, NOT a doctor. When a user reports a doctor's order,
  diagnosis, medical dietary restriction, or medication ("my doctor said I have
  proteinuria, keep protein moderate", "low-sodium, doctor's orders"), that is a
  GOVERNING RULE the coach must (1) record durably and (2) obey — it OVERRIDES
  the default high-protein coaching. Stated mid-conversation, such an order would
  otherwise live only in volatile conversation memory and the coach could keep
  pushing protein against it. This script persists the medical fact to a durable,
  machine-readable section THE INSTANT it is heard, before composing the reply,
  so the obey rule (diet-tracking-analysis) has something concrete to honor.

  It is the deterministic half of the instruction-layer fix: the agent must still
  *notice* the medical order and call this script (instruction/LLM-dependent), but
  once called, canonical storage + de-dup is guaranteed.

What it does:
  1. Read health-profile.md in the given workspace.
  2. Ensure `## Medical` section exists (add it — with the verbatim contract
     fields — if missing, placed before `## Meal Schedule` if present, otherwise
     before `## Goals`, otherwise at the end of the file).
  3. Update the requested field(s):
     - `--condition`  → append to `Reported Conditions` (inline, `; `-joined),
       annotated `(reported <date>)`. De-duped by the condition text.
     - `--directive`  → append to `Doctor Dietary Directives` (inline, `; `-joined).
       De-duped.
     - `--protein-cap`→ SET `Protein Cap` (a scalar: a number like `60 g/day`,
       or `moderate`, or `None`). Overwrites the prior value.
     - `--other-limit`→ append to `Other Limits` (inline, `; `-joined). De-duped.
     A value of `None` / `—` / empty in an existing field is treated as "nothing
     recorded yet". At least one of the four flags is required; several may be
     passed at once (a single doctor's order often carries multiple parts).
  4. Update the top-level `**Updated:**` header to the current timestamp.

Usage:
  python3 save-medical.py --workspace /path/to/workspace \\
    [--condition "proteinuria"] \\
    [--directive "keep protein moderate"] \\
    [--protein-cap "moderate"] \\
    [--other-limit "low sodium"] \\
    [--reported-date 2026-07-02] [--tz-name Asia/Shanghai] [--tz-offset 28800]

  --protein-cap  machine-readable: a number like "60 g/day", or "moderate", or
                 "None". Do NOT invent a medical number — if the doctor only said
                 "moderate/less", store "moderate", not a guessed gram value.
  --reported-date optional YYYY-MM-DD stamped on a condition; defaults to today.
  --tz-name / --tz-offset  used only for the `**Updated:**` timestamp + today's date.

Output (JSON):
  {"ok": true, "updated": {"reported_conditions": "appended", ...},
   "medical": {"reported_conditions": "...", "doctor_dietary_directives": "...",
   "protein_cap": "...", "other_limits": "...", "source": "..."}}
  On failure: {"ok": false, "error": "..."}

Idempotent: re-running with an already-present condition/directive/limit is a
no-op for that field (mode=duplicate); re-setting the same protein cap is a no-op.
health-profile.md `## Medical` is owned by user-onboarding-profile, so writing
here is ownership-clean.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone


# --- timestamp helpers ------------------------------------------------------

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


def _resolve_tz(tz_name: str | None, tz_offset: int | None):
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
    return tz


def _now_iso(tz_name: str | None, tz_offset: int | None) -> str:
    """Best-effort local ISO timestamp for the `**Updated:**` header."""
    return datetime.now(_resolve_tz(tz_name, tz_offset)).isoformat(timespec="seconds")


def _now_date(tz_name: str | None, tz_offset: int | None) -> str:
    """Best-effort local YYYY-MM-DD for the `(reported <date>)` annotation."""
    return datetime.now(_resolve_tz(tz_name, tz_offset)).strftime("%Y-%m-%d")


# --- markdown helpers -------------------------------------------------------

SECTION_RE = re.compile(r"^## (.+?)\s*$")
FIELD_RE = re.compile(r"^- \*\*(.+?):\*\*(.*)$")

# Canonical `## Medical` body — matches the shared cross-repo contract verbatim.
MEDICAL_HEADER = "## Medical"
MEDICAL_BODY = [
    "<!-- Doctor-reported. GOVERNING RULES — the coach is a nutritionist and obeys these; never override. -->",
    "- **Reported Conditions:** None",
    "- **Doctor Dietary Directives:** None",
    "- **Protein Cap:** None",
    "- **Other Limits:** None",
    "- **Source:** user-reported from their doctor",
]

_EMPTY_TOKENS = ("none", "—", "-", "", "[list or none]", "[list]")


def _is_empty(value: str) -> bool:
    return value.strip().lower() in _EMPTY_TOKENS


def _split_inline(value: str) -> list[str]:
    """Split an inline `; `-joined field value into individual items."""
    if _is_empty(value):
        return []
    out = []
    for part in value.split(";"):
        part = part.strip()
        if part and part.lower() not in _EMPTY_TOKENS:
            out.append(part)
    return out


def _item_key(item: str) -> str:
    """Normalize an item for de-dup: strip a trailing (…) note, lowercase."""
    base = re.sub(r"\s*\([^)]*\)\s*$", "", item).strip().lower()
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


def _field_idx(section: list[str], label: str) -> tuple[int | None, str]:
    """Find the `- **<label>:**` line in a section. Returns (idx, current_value)."""
    for i, ln in enumerate(section):
        m = FIELD_RE.match(ln)
        if m and m.group(1).strip().lower() == label.lower():
            return (i, m.group(2).strip())
    return (None, "")


def _body_end(section: list[str]) -> int:
    """Index just after the last `- **…` field line in a section."""
    last = 0
    for i, ln in enumerate(section):
        if FIELD_RE.match(ln):
            last = i + 1
    if last == 0:
        # no field lines yet; place after the header (and any comment/blank)
        last = 1
        while last < len(section) and (
            section[last].strip().startswith("<!--") or section[last].strip() == ""
        ):
            last += 1
    return last


def _append_inline(section: list[str], label: str, item: str) -> str:
    """Append `item` to an inline `; `-joined field; de-dupe. Returns mode."""
    idx, value = _field_idx(section, label)
    if idx is None:
        section.insert(_body_end(section), "- **{0}:** {1}".format(label, item))
        return "created"
    existing = _split_inline(value)
    keys = {_item_key(e) for e in existing}
    if _item_key(item) in keys:
        return "duplicate"
    mode = "appended" if existing else "created"
    existing.append(item)
    section[idx] = "- **{0}:** {1}".format(label, "; ".join(existing))
    return mode


def _set_scalar(section: list[str], label: str, value: str) -> str:
    """Set a scalar field (overwrite). Returns mode."""
    idx, old = _field_idx(section, label)
    if idx is None:
        section.insert(_body_end(section), "- **{0}:** {1}".format(label, value))
        return "created"
    if old.strip().lower().rstrip(".") == value.strip().lower().rstrip("."):
        return "duplicate"
    mode = "created" if _is_empty(old) else "set"
    section[idx] = "- **{0}:** {1}".format(label, value)
    return mode


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--condition", default=None,
                    help="a doctor-reported diagnosis / condition (e.g. proteinuria)")
    ap.add_argument("--directive", default=None,
                    help="a doctor dietary directive (e.g. keep protein moderate)")
    ap.add_argument("--protein-cap", dest="protein_cap", default=None,
                    help="machine-readable protein cap: a number like '60 g/day', 'moderate', or 'None'")
    ap.add_argument("--other-limit", dest="other_limit", default=None,
                    help="other doctor-imposed limit (e.g. low sodium)")
    ap.add_argument("--reported-date", dest="reported_date", default=None,
                    help="YYYY-MM-DD stamped on a condition (defaults to today)")
    ap.add_argument("--tz-name", default=None)
    ap.add_argument("--tz-offset", type=int, default=None)
    args = ap.parse_args()

    condition = (args.condition or "").strip()
    directive = (args.directive or "").strip()
    protein_cap = (args.protein_cap or "").strip()
    other_limit = (args.other_limit or "").strip()

    if not (condition or directive or protein_cap or other_limit):
        print(json.dumps({"ok": False, "error": "need at least one of "
                          "--condition / --directive / --protein-cap / --other-limit"}))
        return 1

    profile_path = os.path.join(args.workspace, "health-profile.md")
    if not os.path.exists(profile_path):
        print(json.dumps({"ok": False, "error": "health-profile.md not found"}))
        return 1

    try:
        with open(profile_path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        print(json.dumps({"ok": False, "error": "read failed: {0}".format(e)}))
        return 1

    # timezone (for both the reported-date annotation and the Updated header)
    tz_name = args.tz_name
    tz_offset = args.tz_offset
    if tz_name is None and tz_offset is None:
        tz_name, tz_offset = _read_user_md_tz(args.workspace)

    lines = text.split("\n")

    # Ensure Medical section exists.
    bounds = _find_section_bounds(lines, "Medical")
    if bounds is None:
        lines = _insert_section(lines, MEDICAL_HEADER, list(MEDICAL_BODY))
        bounds = _find_section_bounds(lines, "Medical")

    start, end = bounds
    section = lines[start:end]

    updated: dict[str, str] = {}

    if condition:
        reported = args.reported_date or _now_date(tz_name, tz_offset)
        if re.search(r"\(reported\b", condition, re.IGNORECASE):
            item = condition
        else:
            item = "{0} (reported {1})".format(condition, reported)
        updated["reported_conditions"] = _append_inline(
            section, "Reported Conditions", item)

    if directive:
        updated["doctor_dietary_directives"] = _append_inline(
            section, "Doctor Dietary Directives", directive)

    if protein_cap:
        updated["protein_cap"] = _set_scalar(section, "Protein Cap", protein_cap)

    if other_limit:
        updated["other_limits"] = _append_inline(
            section, "Other Limits", other_limit)

    lines = lines[:start] + section + lines[end:]

    # Update **Updated:** header
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

    # Read back the resulting field values for the caller.
    final_bounds = _find_section_bounds(lines, "Medical")
    medical: dict[str, str] = {}
    if final_bounds is not None:
        fs, fe = final_bounds
        fsection = lines[fs:fe]
        for key, label in (
            ("reported_conditions", "Reported Conditions"),
            ("doctor_dietary_directives", "Doctor Dietary Directives"),
            ("protein_cap", "Protein Cap"),
            ("other_limits", "Other Limits"),
            ("source", "Source"),
        ):
            _, val = _field_idx(fsection, label)
            medical[key] = val

    print(
        json.dumps(
            {"ok": True, "updated": updated, "medical": medical},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
