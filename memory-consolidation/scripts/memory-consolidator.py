# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
Memory consolidation helper for the three-layer memory system.

Handles file I/O, date rotation, and structural operations.
The agent provides the actual content (summaries, classifications, etc).

Commands:
  short-term-read     — Load current short-term.json
  short-term-update   — Add/update a conversation entry in short-term.json
  short-term-rotate   — Remove entries older than 2 days, return removed data
  medium-term-read    — Read medium-term.md and parse sections
  medium-term-stats   — Report line count, topic count, oldest entries
  long-term-stats     — Report line count and section summary
  init                — Create empty memory files if they don't exist

Usage:
  python3 memory-consolidator.py init --memory-dir /path/to/memory
  python3 memory-consolidator.py short-term-read --memory-dir /path/to/memory
  python3 memory-consolidator.py short-term-update --memory-dir /path/to/memory \
      --entry '{"date":"2026-03-06","time":"12:15","topic":"午餐打卡",...}'
  python3 memory-consolidator.py short-term-rotate --memory-dir /path/to/memory
  python3 memory-consolidator.py medium-term-read --memory-dir /path/to/memory
  python3 memory-consolidator.py medium-term-stats --memory-dir /path/to/memory
  python3 memory-consolidator.py long-term-stats --memory-dir /path/to/memory
"""

import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def _short_term_path(memory_dir: str) -> str:
    return os.path.join(memory_dir, "short-term.json")


def _medium_term_path(memory_dir: str) -> str:
    return os.path.join(memory_dir, "medium-term.md")


def _long_term_path(memory_dir: str) -> str:
    return os.path.join(memory_dir, "long-term.md")


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------

def cmd_init(memory_dir: str) -> dict:
    """Create empty memory files if they don't exist."""
    os.makedirs(memory_dir, exist_ok=True)
    created = []

    st_path = _short_term_path(memory_dir)
    if not os.path.exists(st_path):
        with open(st_path, "w", encoding="utf-8") as f:
            json.dump({"last_updated": None, "days": []}, f, indent=2)
        created.append("short-term.json")

    mt_path = _medium_term_path(memory_dir)
    if not os.path.exists(mt_path):
        with open(mt_path, "w", encoding="utf-8") as f:
            f.write("# Medium-Term Memory\n\n**Last consolidated:** —\n")
        created.append("medium-term.md")

    lt_path = _long_term_path(memory_dir)
    if not os.path.exists(lt_path):
        with open(lt_path, "w", encoding="utf-8") as f:
            f.write("# Long-Term Memory\n\n**Last updated:** —\n")
        created.append("long-term.md")

    return {
        "memory_dir": memory_dir,
        "created": created,
        "already_existed": len(created) == 0,
    }


# ---------------------------------------------------------------------------
# Short-term: read
# ---------------------------------------------------------------------------

def cmd_short_term_read(memory_dir: str) -> dict:
    """Load and return short-term.json contents."""
    path = _short_term_path(memory_dir)
    if not os.path.exists(path):
        return {"exists": False, "data": None}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {"exists": True, "data": data}


# ---------------------------------------------------------------------------
# Short-term: update
# ---------------------------------------------------------------------------

def cmd_short_term_update(memory_dir: str, entry: dict) -> dict:
    """Add or update a conversation entry in short-term.json.

    *entry* must contain at minimum:
      - date (YYYY-MM-DD)
      - time (HH:MM)
      - topic (string)
      - summary (string)

    Optional fields: skills_involved, outcome, mood, key_decisions, follow_ups

    If a day_summary is provided in the entry, it updates the day's summary.
    """
    path = _short_term_path(memory_dir)
    os.makedirs(memory_dir, exist_ok=True)

    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {"last_updated": None, "days": []}

    entry_date = entry.get("date")
    if not entry_date:
        return {"error": "entry must contain 'date' field"}

    day_summary_override = entry.pop("day_summary", None)

    # Find or create the day
    day_obj = None
    for d in data["days"]:
        if d.get("date") == entry_date:
            day_obj = d
            break

    if day_obj is None:
        day_obj = {"date": entry_date, "conversations": [], "day_summary": ""}
        data["days"].append(day_obj)
        # Keep days sorted newest first
        data["days"].sort(key=lambda d: d["date"], reverse=True)

    # Build the conversation record
    conv = {
        "time": entry.get("time", ""),
        "topic": entry.get("topic", ""),
        "skills_involved": entry.get("skills_involved", []),
        "summary": entry.get("summary", ""),
        "outcome": entry.get("outcome", ""),
        "mood": entry.get("mood", ""),
        "key_decisions": entry.get("key_decisions", []),
        "follow_ups": entry.get("follow_ups", []),
    }

    day_obj["conversations"].append(conv)

    if day_summary_override:
        day_obj["day_summary"] = day_summary_override

    data["last_updated"] = datetime.now(timezone.utc).isoformat()

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return {
        "saved": True,
        "date": entry_date,
        "conversations_count": len(day_obj["conversations"]),
        "total_days": len(data["days"]),
    }


# ---------------------------------------------------------------------------
# Short-term: rotate
# ---------------------------------------------------------------------------

def cmd_short_term_rotate(memory_dir: str, today: str = None) -> dict:
    """Remove entries older than 2 days. Return removed data for consolidation.

    Keeps today and yesterday. Everything older is returned and deleted.
    """
    path = _short_term_path(memory_dir)
    if not os.path.exists(path):
        return {"rotated": False, "reason": "file not found", "removed": []}

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    today_date = date.fromisoformat(today) if today else date.today()
    yesterday = today_date - timedelta(days=1)
    cutoff_dates = {today_date.isoformat(), yesterday.isoformat()}

    kept = []
    removed = []
    for d in data.get("days", []):
        if d.get("date") in cutoff_dates:
            kept.append(d)
        else:
            removed.append(d)

    data["days"] = kept
    data["last_updated"] = datetime.now(timezone.utc).isoformat()

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return {
        "rotated": True,
        "kept_days": len(kept),
        "removed_days": len(removed),
        "removed": removed,
    }


# ---------------------------------------------------------------------------
# Short-term: set day summary
# ---------------------------------------------------------------------------

def cmd_short_term_set_day_summary(memory_dir: str, target_date: str,
                                    summary: str) -> dict:
    """Set or update the day_summary for a specific date in short-term.json."""
    path = _short_term_path(memory_dir)
    if not os.path.exists(path):
        return {"error": "short-term.json not found"}

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for d in data.get("days", []):
        if d.get("date") == target_date:
            d["day_summary"] = summary
            data["last_updated"] = datetime.now(timezone.utc).isoformat()
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return {"updated": True, "date": target_date}

    return {"updated": False, "reason": f"no entry for date {target_date}"}


# ---------------------------------------------------------------------------
# Medium-term: read
# ---------------------------------------------------------------------------

def cmd_medium_term_read(memory_dir: str) -> dict:
    """Read medium-term.md, parse into sections by H2 headers."""
    path = _medium_term_path(memory_dir)
    if not os.path.exists(path):
        return {"exists": False, "sections": []}

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    sections = []
    current_section = None
    current_lines = []

    for line in content.split("\n"):
        if line.startswith("## "):
            if current_section:
                sections.append({
                    "title": current_section,
                    "content": "\n".join(current_lines).strip(),
                })
            current_section = line[3:].strip()
            current_lines = []
        elif current_section is not None:
            current_lines.append(line)

    if current_section:
        sections.append({
            "title": current_section,
            "content": "\n".join(current_lines).strip(),
        })

    return {
        "exists": True,
        "sections": sections,
        "section_count": len(sections),
    }


# ---------------------------------------------------------------------------
# Medium-term: stats
# ---------------------------------------------------------------------------

def cmd_medium_term_stats(memory_dir: str) -> dict:
    """Report line count, topic count, and oldest date references."""
    path = _medium_term_path(memory_dir)
    if not os.path.exists(path):
        return {"exists": False}

    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    line_count = len(lines)

    # Count H2 sections
    section_titles = [l.strip()[3:] for l in lines if l.startswith("## ")]

    # Find date references (MM-DD or YYYY-MM-DD patterns)
    date_refs = set()
    date_pattern = re.compile(r'\[(\d{2}-\d{2})\]|\[(\d{4}-\d{2}-\d{2})\]')
    for line in lines:
        for match in date_pattern.finditer(line):
            ref = match.group(1) or match.group(2)
            date_refs.add(ref)

    oldest = min(date_refs) if date_refs else None
    newest = max(date_refs) if date_refs else None

    # Check soft limit
    soft_limit = 500
    over_limit = line_count > soft_limit

    return {
        "exists": True,
        "line_count": line_count,
        "soft_limit": soft_limit,
        "over_limit": over_limit,
        "section_count": len(section_titles),
        "sections": section_titles,
        "oldest_date_ref": oldest,
        "newest_date_ref": newest,
        "date_ref_count": len(date_refs),
    }


# ---------------------------------------------------------------------------
# Long-term: stats
# ---------------------------------------------------------------------------

def cmd_long_term_stats(memory_dir: str) -> dict:
    """Report line count and section summary for long-term.md."""
    path = _long_term_path(memory_dir)
    if not os.path.exists(path):
        return {"exists": False}

    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    line_count = len(lines)
    section_titles = [l.strip()[3:] for l in lines if l.startswith("## ")]

    # Count milestone/event entries (lines starting with "- [")
    entry_count = sum(1 for l in lines if l.strip().startswith("- ["))

    soft_limit = 300
    over_limit = line_count > soft_limit

    return {
        "exists": True,
        "line_count": line_count,
        "soft_limit": soft_limit,
        "over_limit": over_limit,
        "section_count": len(section_titles),
        "sections": section_titles,
        "entry_count": entry_count,
    }


# ---------------------------------------------------------------------------
# Medium-term: atomic update commands
# ---------------------------------------------------------------------------

# Field label mapping (English key → Chinese label in file)
_FIELD_LABELS = {
    "overview": "整体表现/状态",
    "conclusion": "当前结论",
    "strategy": "应对策略",
    "follow_ups": "待跟进",
}

# Preferred insertion order for fields within a section
_FIELD_ORDER = ["overview", "discussions", "conclusion", "strategy", "follow_ups"]


def _parse_sections(lines: list[str]) -> list[dict]:
    """Parse medium-term.md into sections with line ranges.

    Returns list of: {"title": str, "start": int, "end": int}
    where start is the line index of the ## header and end is the line
    index of the next ## header (or len(lines)).
    """
    sections = []
    for i, line in enumerate(lines):
        if line.startswith("## "):
            if sections:
                sections[-1]["end"] = i
            sections.append({"title": line[3:].strip(), "start": i, "end": len(lines)})
    if sections:
        sections[-1]["end"] = len(lines)
    return sections


def _find_section(sections: list[dict], title: str) -> dict | None:
    """Find section by title (exact match)."""
    for s in sections:
        if s["title"] == title:
            return s
    return None


def _find_field_range(lines: list[str], section: dict, field_label: str) -> tuple[int, int] | None:
    """Find the line range [start, end) of a field within a section.

    The field starts at the line containing `- **{field_label}：**` or `- **{field_label}:**`
    and extends until the next `- **` line or section end.
    """
    start_idx = None
    for i in range(section["start"] + 1, section["end"]):
        line = lines[i]
        # Check if this line starts a field (handles both ： and :)
        stripped = line.strip()
        if stripped.startswith("- **") and field_label in stripped:
            # Verify it's the right field (not a substring match)
            # Pattern: - **LABEL：** or - **LABEL:**
            if f"**{field_label}：**" in stripped or f"**{field_label}:**" in stripped:
                start_idx = i
                break

    if start_idx is None:
        return None

    # Find end: next `- **` line or section end
    end_idx = section["end"]
    for i in range(start_idx + 1, section["end"]):
        stripped = lines[i].strip()
        if stripped.startswith("- **"):
            end_idx = i
            break

    return (start_idx, end_idx)


def _find_discussions_range(lines: list[str], section: dict) -> tuple[int, int] | None:
    """Find the line range of the 关键讨论 block (header + entries).

    Returns (header_line_idx, end_idx) where end_idx is the line after the
    last discussion entry.
    """
    return _find_field_range(lines, section, "关键讨论")


def cmd_medium_term_set_date(memory_dir: str, new_date: str) -> dict:
    """Update the 'Last consolidated' date at the top of medium-term.md."""
    path = _medium_term_path(memory_dir)
    if not os.path.exists(path):
        return {"error": "file_not_found"}

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Match: **Last consolidated:** YYYY-MM-DD or any date-like string or —
    pattern = r'(\*\*Last consolidated[：:]\*\*\s*)([\d\-T:.+Z—]+)'
    m = re.search(pattern, content)
    if not m:
        return {"error": "date_marker_not_found"}

    old_date = m.group(2)
    new_content = content[:m.start(2)] + new_date + content[m.end(2):]

    with open(path, "w", encoding="utf-8") as f:
        f.write(new_content)

    return {"status": "ok", "old_date": old_date, "new_date": new_date}


def cmd_medium_term_append_discussions(memory_dir: str, section_title: str,
                                       entries: list[dict]) -> dict:
    """Append discussion entries to a section's 关键讨论 list."""
    path = _medium_term_path(memory_dir)
    if not os.path.exists(path):
        return {"error": "file_not_found"}

    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    sections = _parse_sections(lines)
    section = _find_section(sections, section_title)
    if not section:
        return {"error": "section_not_found",
                "available": [s["title"] for s in sections]}

    disc_range = _find_discussions_range(lines, section)

    # Build new entry lines
    new_lines = []
    for entry in entries:
        date_str = entry.get("date", "??-??")
        text = entry.get("text", "")
        new_lines.append(f"  - [{date_str}] {text}\n")

    if disc_range:
        header_idx, end_idx = disc_range
        # Find the last discussion entry line (lines starting with spaces + - [)
        insert_at = header_idx + 1
        disc_pattern = re.compile(r'^\s+- \[')
        for i in range(header_idx + 1, end_idx):
            if disc_pattern.match(lines[i]):
                insert_at = i + 1
        # Insert new entries
        for j, new_line in enumerate(new_lines):
            lines.insert(insert_at + j, new_line)
        total_discussions = sum(1 for i in range(header_idx + 1, end_idx + len(new_lines))
                                if disc_pattern.match(lines[i]))
    else:
        # No 关键讨论 field exists — create it
        # Insert after overview line or after section header
        overview_range = _find_field_range(lines, section, "整体表现/状态")
        if overview_range:
            insert_at = overview_range[1]
        else:
            insert_at = section["start"] + 1

        header_line = "- **关键讨论：**\n"
        lines.insert(insert_at, header_line)
        for j, new_line in enumerate(new_lines):
            lines.insert(insert_at + 1 + j, new_line)
        total_discussions = len(new_lines)

    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)

    return {"status": "ok", "section": section_title,
            "entries_added": len(entries), "total_discussions": total_discussions}


def cmd_medium_term_set_field(memory_dir: str, section_title: str,
                              field: str, value: str) -> dict:
    """Set/replace a field value within a section."""
    path = _medium_term_path(memory_dir)
    if not os.path.exists(path):
        return {"error": "file_not_found"}

    if field not in _FIELD_LABELS:
        return {"error": "invalid_field",
                "valid_fields": list(_FIELD_LABELS.keys())}

    field_label = _FIELD_LABELS[field]

    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    sections = _parse_sections(lines)
    section = _find_section(sections, section_title)
    if not section:
        return {"error": "section_not_found",
                "available": [s["title"] for s in sections]}

    field_range = _find_field_range(lines, section, field_label)

    if field_range:
        start_idx, end_idx = field_range
        # Extract old value (everything after the :** marker on the first line +
        # continuation lines)
        first_line = lines[start_idx]
        # Find the marker end position
        for marker in [f"**{field_label}：**", f"**{field_label}:**"]:
            pos = first_line.find(marker)
            if pos >= 0:
                old_value_start = pos + len(marker)
                break
        else:
            old_value_start = len(first_line)

        old_first = first_line[old_value_start:].strip()
        old_rest = [lines[i].strip() for i in range(start_idx + 1, end_idx)]
        old_value = " ".join([old_first] + old_rest).strip()

        # Build replacement: single line with the new value
        new_line = f"- **{field_label}：** {value}\n"
        lines[start_idx:end_idx] = [new_line]
    else:
        # Field doesn't exist — create it at appropriate position
        old_value = ""
        new_line = f"- **{field_label}：** {value}\n"

        # Determine insertion point based on field order
        insert_at = section["end"]
        field_idx = _FIELD_ORDER.index(field) if field in _FIELD_ORDER else len(_FIELD_ORDER)

        # Find the last existing field that comes before this one in order
        for check_field in reversed(_FIELD_ORDER[:field_idx]):
            if check_field == "discussions":
                check_label = "关键讨论"
            else:
                check_label = _FIELD_LABELS.get(check_field, "")
            if not check_label:
                continue
            r = _find_field_range(lines, section, check_label)
            if r:
                insert_at = r[1]
                break
        else:
            # No preceding field found, insert after header
            insert_at = section["start"] + 1

        lines.insert(insert_at, new_line)

    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)

    return {"status": "ok", "section": section_title, "field": field,
            "old_value_preview": old_value[:50],
            "new_value_preview": value[:50]}


def cmd_medium_term_add_section(memory_dir: str, section_title: str,
                                overview: str = None, discussions: list[dict] = None,
                                conclusion: str = None, strategy: str = None,
                                follow_ups: str = None) -> dict:
    """Add a new section to medium-term.md."""
    path = _medium_term_path(memory_dir)
    if not os.path.exists(path):
        return {"error": "file_not_found"}

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
        lines = content.split("\n")

    # Check if section already exists
    for line in lines:
        if line.startswith("## ") and line[3:].strip() == section_title:
            return {"error": "section_exists"}

    # Build new section
    new_section_lines = [f"\n## {section_title}\n"]

    if overview:
        new_section_lines.append(f"- **整体表现/状态：** {overview}\n")
    if discussions:
        new_section_lines.append("- **关键讨论：**\n")
        for entry in discussions:
            date_str = entry.get("date", "??-??")
            text = entry.get("text", "")
            new_section_lines.append(f"  - [{date_str}] {text}\n")
    if conclusion:
        new_section_lines.append(f"- **当前结论：** {conclusion}\n")
    if strategy:
        new_section_lines.append(f"- **应对策略：** {strategy}\n")
    if follow_ups:
        new_section_lines.append(f"- **待跟进：** {follow_ups}\n")

    # Append to file
    with open(path, "a", encoding="utf-8") as f:
        f.writelines(new_section_lines)

    return {"status": "ok", "section": section_title,
            "line_count": len(new_section_lines)}


def cmd_medium_term_prune_discussions(memory_dir: str, section_title: str,
                                      before: str) -> dict:
    """Remove discussion entries older than a given MM-DD date."""
    path = _medium_term_path(memory_dir)
    if not os.path.exists(path):
        return {"error": "file_not_found"}

    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    sections = _parse_sections(lines)
    section = _find_section(sections, section_title)
    if not section:
        return {"error": "section_not_found",
                "available": [s["title"] for s in sections]}

    disc_range = _find_discussions_range(lines, section)
    if not disc_range:
        return {"status": "ok", "section": section_title, "removed": 0, "remaining": 0}

    header_idx, end_idx = disc_range
    disc_pattern = re.compile(r'^\s+- \[(\d{2}-\d{2})\]')

    # Collect indices to remove
    to_remove = []
    remaining = 0
    for i in range(header_idx + 1, end_idx):
        m = disc_pattern.match(lines[i])
        if m:
            entry_date = m.group(1)
            if entry_date < before:
                to_remove.append(i)
            else:
                remaining += 1

    # Remove in reverse order to preserve indices
    for i in reversed(to_remove):
        del lines[i]

    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)

    return {"status": "ok", "section": section_title,
            "removed": len(to_remove), "remaining": remaining}

# ---------------------------------------------------------------------------
# Extract conversations from session files (Batch Mode)
# ---------------------------------------------------------------------------

def cmd_extract_conversations(session_dir: str, hours: int = 24) -> dict:
    """Extract user messages from the latest session file.

    Finds the newest non-deleted .jsonl in session_dir, reads it,
    and extracts real user messages from the last N hours.

    Returns structured conversation data ready for the agent to summarize.
    """
    if not os.path.isdir(session_dir):
        return {"error": f"session dir not found: {session_dir}", "conversations": []}

    # Find newest non-deleted session file, skipping isolated/cron sessions
    candidates = []
    for f in os.listdir(session_dir):
        if f.endswith(".jsonl") and ".deleted." not in f:
            full = os.path.join(session_dir, f)
            # Skip cron sessions by checking first few lines for [cron: marker
            try:
                is_cron = False
                with open(full, "r", encoding="utf-8") as peek:
                    for _ in range(10):
                        ln = peek.readline()
                        if not ln:
                            break
                        if '"[cron:' in ln or "'[cron:" in ln:
                            is_cron = True
                            break
                if is_cron:
                    continue
            except OSError:
                pass
            candidates.append((os.path.getmtime(full), full))

    if not candidates:
        return {"error": "no session files found", "conversations": []}

    candidates.sort(reverse=True)
    session_file = candidates[0][1]

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    cutoff_ts = cutoff.isoformat()

    # Patterns that indicate non-user messages
    skip_types = {"session", "model_change", "thinking_level_change", "custom",
                  "toolCall", "toolResult"}

    conversations = []  # List of {timestamp, role, text}
    current_exchange = []  # Buffer for grouping

    with open(session_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            entry_type = entry.get("type", "")

            # Skip non-message types
            if entry_type in skip_types:
                continue
            if entry_type != "message":
                continue

            msg = entry.get("message", {})
            role = msg.get("role", "")
            ts_str = entry.get("timestamp", "")

            # Only process messages after cutoff
            if ts_str and ts_str < cutoff_ts:
                continue

            # Extract text content
            content = msg.get("content", [])
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                text_parts = []
                for c in content:
                    if isinstance(c, dict) and c.get("type") == "text":
                        text_parts.append(c.get("text", ""))
                    elif isinstance(c, str):
                        text_parts.append(c)
                text = "\n".join(text_parts)
            else:
                text = ""

            text = text.strip()
            if not text:
                continue

            # Skip system-injected messages disguised as user messages
            if role == "user":
                # Skip heartbeat, cron prompts, system events
                lower = text[:200].lower()
                if any(kw in lower for kw in [
                    "heartbeat", "read heartbeat.md",
                    "run notification-composer", "run diet-pattern-detection",
                    "run weekly-report", "run memory-consolidation",
                    "cron task", "system event",
                    '"customtype"', '"type":"custom"',
                ]):
                    continue
                # Skip metadata blocks
                # Strip metadata blocks (Sender/Conversation info) — may be nested
                while text.startswith(("Conversation info (untrusted metadata):", "Sender (untrusted metadata):")):
                    idx = text.find("```\n\n")
                    if idx >= 0:
                        text = text[idx + 5:].strip()
                    else:
                        idx = text.find("```\n")
                        if idx >= 0:
                            text = text[idx + 4:].strip()
                        else:
                            text = ""
                            break
                if not text:
                    continue

            conversations.append({
                "timestamp": ts_str,
                "role": role,
                "text": text[:2000],  # Truncate very long messages
            })

    # Group into exchanges (user message + assistant response pairs)
    exchanges = []
    current = {"user_messages": [], "assistant_messages": [], "start_time": None}

    for msg in conversations:
        if msg["role"] == "user":
            # If we had an exchange going with assistant response, save it
            if current["user_messages"] and current["assistant_messages"]:
                exchanges.append(current)
                current = {"user_messages": [], "assistant_messages": [], "start_time": None}
            current["user_messages"].append(msg)
            if not current["start_time"]:
                current["start_time"] = msg["timestamp"]
        elif msg["role"] == "assistant":
            current["assistant_messages"].append(msg)

    # Don't forget the last exchange
    if current["user_messages"]:
        exchanges.append(current)

    return {
        "session_file": session_file,
        "hours": hours,
        "cutoff": cutoff_ts,
        "total_messages": len(conversations),
        "exchanges": len(exchanges),
        "conversations": exchanges,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Memory consolidation helper")
    sub = parser.add_subparsers(dest="cmd")

    # init
    init_p = sub.add_parser("init", help="Create empty memory files")
    init_p.add_argument("--memory-dir", required=True)

    # short-term-read
    str_p = sub.add_parser("short-term-read", help="Load short-term.json")
    str_p.add_argument("--memory-dir", required=True)

    # short-term-update
    stu_p = sub.add_parser("short-term-update",
                           help="Add a conversation entry to short-term.json")
    stu_p.add_argument("--memory-dir", required=True)
    stu_p.add_argument("--entry", required=True,
                       help="JSON object with date, time, topic, summary, etc.")

    # short-term-rotate
    stro_p = sub.add_parser("short-term-rotate",
                            help="Remove entries older than 2 days")
    stro_p.add_argument("--memory-dir", required=True)
    stro_p.add_argument("--today", default=None,
                        help="Override today's date (YYYY-MM-DD)")

    # short-term-set-day-summary
    stds_p = sub.add_parser("short-term-set-day-summary",
                            help="Set day_summary for a date")
    stds_p.add_argument("--memory-dir", required=True)
    stds_p.add_argument("--date", required=True)
    stds_p.add_argument("--summary", required=True)

    # medium-term-read
    mtr_p = sub.add_parser("medium-term-read",
                           help="Read medium-term.md sections")
    mtr_p.add_argument("--memory-dir", required=True)

    # medium-term-stats
    mts_p = sub.add_parser("medium-term-stats",
                           help="Report medium-term.md statistics")
    mts_p.add_argument("--memory-dir", required=True)

    # medium-term-set-date
    mtsd_p = sub.add_parser("medium-term-set-date",
                            help="Update 'Last consolidated' date")
    mtsd_p.add_argument("--memory-dir", required=True)
    mtsd_p.add_argument("--date", required=True, help="New date (YYYY-MM-DD)")

    # medium-term-append-discussions
    mtad_p = sub.add_parser("medium-term-append-discussions",
                            help="Append entries to a section's discussion list")
    mtad_p.add_argument("--memory-dir", required=True)
    mtad_p.add_argument("--section", required=True, help="H2 section title")
    mtad_p.add_argument("--entries", required=True,
                        help='JSON array: [{"date":"MM-DD","text":"..."}]')

    # medium-term-set-field
    mtsf_p = sub.add_parser("medium-term-set-field",
                            help="Set/replace a field value within a section")
    mtsf_p.add_argument("--memory-dir", required=True)
    mtsf_p.add_argument("--section", required=True, help="H2 section title")
    mtsf_p.add_argument("--field", required=True,
                        choices=["overview", "conclusion", "strategy", "follow_ups"],
                        help="Field to set")
    mtsf_p.add_argument("--value", required=True, help="New field value")

    # medium-term-add-section
    mtas_p = sub.add_parser("medium-term-add-section",
                            help="Add a new section to medium-term.md")
    mtas_p.add_argument("--memory-dir", required=True)
    mtas_p.add_argument("--section", required=True, help="New section title")
    mtas_p.add_argument("--overview", default=None)
    mtas_p.add_argument("--discussions", default=None,
                        help='JSON array: [{"date":"MM-DD","text":"..."}]')
    mtas_p.add_argument("--conclusion", default=None)
    mtas_p.add_argument("--strategy", default=None)
    mtas_p.add_argument("--follow-ups", default=None, dest="follow_ups")

    # medium-term-prune-discussions
    mtpd_p = sub.add_parser("medium-term-prune-discussions",
                            help="Remove discussion entries older than a date")
    mtpd_p.add_argument("--memory-dir", required=True)
    mtpd_p.add_argument("--section", required=True, help="H2 section title")
    mtpd_p.add_argument("--before", required=True,
                        help="Remove entries with date < this (MM-DD)")

    # long-term-stats
    lts_p = sub.add_parser("long-term-stats",
                           help="Report long-term.md statistics")
    lts_p.add_argument("--memory-dir", required=True)

    # extract-conversations
    ec_p = sub.add_parser("extract-conversations",
                          help="Extract user messages from session files")
    ec_p.add_argument("--session-dir", required=True,
                      help="Path to agent's sessions directory")
    ec_p.add_argument("--hours", type=int, default=24,
                      help="Look back N hours (default: 24)")

    args = parser.parse_args()

    if args.cmd == "init":
        result = cmd_init(args.memory_dir)
    elif args.cmd == "short-term-read":
        result = cmd_short_term_read(args.memory_dir)
    elif args.cmd == "short-term-update":
        try:
            entry = json.loads(args.entry)
        except json.JSONDecodeError as e:
            print(f"Error: invalid --entry JSON: {e}", file=sys.stderr)
            sys.exit(1)
        result = cmd_short_term_update(args.memory_dir, entry)
    elif args.cmd == "short-term-rotate":
        result = cmd_short_term_rotate(args.memory_dir, args.today)
    elif args.cmd == "short-term-set-day-summary":
        result = cmd_short_term_set_day_summary(
            args.memory_dir, args.date, args.summary)
    elif args.cmd == "medium-term-read":
        result = cmd_medium_term_read(args.memory_dir)
    elif args.cmd == "medium-term-stats":
        result = cmd_medium_term_stats(args.memory_dir)
    elif args.cmd == "medium-term-set-date":
        result = cmd_medium_term_set_date(args.memory_dir, args.date)
    elif args.cmd == "medium-term-append-discussions":
        try:
            entries = json.loads(args.entries)
        except json.JSONDecodeError as e:
            print(f"Error: invalid --entries JSON: {e}", file=sys.stderr)
            sys.exit(1)
        result = cmd_medium_term_append_discussions(
            args.memory_dir, args.section, entries)
    elif args.cmd == "medium-term-set-field":
        result = cmd_medium_term_set_field(
            args.memory_dir, args.section, args.field, args.value)
    elif args.cmd == "medium-term-add-section":
        discussions = None
        if args.discussions:
            try:
                discussions = json.loads(args.discussions)
            except json.JSONDecodeError as e:
                print(f"Error: invalid --discussions JSON: {e}", file=sys.stderr)
                sys.exit(1)
        result = cmd_medium_term_add_section(
            args.memory_dir, args.section,
            overview=args.overview, discussions=discussions,
            conclusion=args.conclusion, strategy=args.strategy,
            follow_ups=args.follow_ups)
    elif args.cmd == "medium-term-prune-discussions":
        result = cmd_medium_term_prune_discussions(
            args.memory_dir, args.section, args.before)
    elif args.cmd == "long-term-stats":
        result = cmd_long_term_stats(args.memory_dir)
    elif args.cmd == "extract-conversations":
        result = cmd_extract_conversations(args.session_dir, args.hours)
    else:
        parser.print_help()
        sys.exit(1)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
