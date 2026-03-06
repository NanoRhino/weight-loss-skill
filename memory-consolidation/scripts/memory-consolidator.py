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

    # long-term-stats
    lts_p = sub.add_parser("long-term-stats",
                           help="Report long-term.md statistics")
    lts_p.add_argument("--memory-dir", required=True)

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
    elif args.cmd == "long-term-stats":
        result = cmd_long_term_stats(args.memory_dir)
    else:
        parser.print_help()
        sys.exit(1)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
