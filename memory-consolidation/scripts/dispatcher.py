#!/usr/bin/env python3
"""
Memory Consolidation Dispatcher
================================
Scans all per-user nutritionist workspaces (Twilio/SMS deployment), determines
who needs memory consolidation, and creates one-shot cron jobs for each user
that needs work.

Intended to run daily as a single global cron job (e.g. ~09:00 UTC). Each
per-user job runs in an isolated session with --no-deliver (no SMS to users)
and --delete-after-run.

Cost optimization: only agents with *real* consolidation work (short-term-
update / medium-term-consolidate / medium-term-cleanup / long-term-promote)
get an agent turn. Dormant agents whose only need is `init` (empty memory
files) are skipped entirely — their files are created lazily during the next
real conversation. Agents that have real work but are missing memory files
are `init`-ed inline (in-process, no agent turn) before dispatch.

Usage:
    python3 dispatcher.py scan          # Scan only, print JSON report
    python3 dispatcher.py dispatch      # Scan + create cron jobs
    python3 dispatcher.py dispatch --dry-run   # Show what would be created
    python3 dispatcher.py dispatch --limit 10  # Max 10 jobs
    python3 dispatcher.py dispatch --gap 30    # 30s between jobs (default)

Output (scan mode):
    JSON with users needing consolidation and their task types.

Output (dispatch mode):
    Creates one-shot cron jobs staggered by --gap seconds.
    Each job is: schedule.kind="at", deleteAfterRun=true, sessionTarget=isolated
"""

# Production EC2 invokes skill scripts as bare `python3` = 3.9; defer annotation
# evaluation so PEP-604 unions (`str | None`) don't crash at import on 3.9.
from __future__ import annotations

import argparse
import json
import os
import sys
import glob
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── Constants ──
# Twilio/SMS (NanoRhino) deployment. Each per-user agent has:
#   - workspace at  /home/ec2-user/.openclaw/workspace-nutritionist/<agentId>
#   - sessions  at  /home/ec2-user/.openclaw/agents/<sanitized agentId>/sessions
# The workspace dir name IS the agentId (no prefix), and matches the id used by
# `openclaw cron add --agent <id>` and openclaw.json agents.list. NOTE: the
# agents/ session dir name is a *sanitized* (lowercased) form of the agentId for
# mixed-case ids (e.g. agentId "002-XiaomengSlack" → agents/002-xiaomengslack),
# so session lookup tries the exact id then the lowercased id.

WORKSPACE_GLOB = "/home/ec2-user/.openclaw/workspace-nutritionist/*"
MEMORY_SUBDIR = "memory"
SESSION_DIR_TEMPLATE = "/home/ec2-user/.openclaw/agents/{agent_id}/sessions"

# Skill SKILL.md path on the SMS gateway (skills are a git checkout of
# weight-loss-skill on branch experiment/activation-hooks).
SKILL_PATH = "/home/ec2-user/.openclaw/skills/memory-consolidation/SKILL.md"

# Workspace basenames that are NOT real per-user agents — skip entirely.
# Pool-warmed agents (pool-*) have no real user; counter.json is bookkeeping;
# test_* are provisioning stubs.
SKIP_WORKSPACE_NAMES = {"counter.json"}
SKIP_WORKSPACE_PREFIXES = ("pool-", "test_", "test-")

# How old short-term entries must be before medium-term consolidation (days)
SHORT_TERM_MAX_AGE_DAYS = 2

# How many days since last long-term update before triggering weekly promotion
LONG_TERM_UPDATE_INTERVAL_DAYS = 7

# Patterns to skip when scanning session files for real user messages
SKIP_PATTERNS = [
    '"role":"system"',
    '"role":"assistant"',
    '"customType":"heartbeat"',
    '"customType":"model-snapshot"',
    '"customType":"cron-',
    '"type":"session"',
    '"type":"model_change"',
    '"type":"thinking_level_change"',
    '"type":"custom"',
    '"type":"toolCall"',
    '"type":"toolResult"',
    # Skip cron-injected user messages (isolated sessions)
    "[cron:",
    "Run notification-composer",
    "Run notification-manager",
    "memory consolidation",
    "Your previous response was only an acknowledgement",
    # Skip heartbeat polls
    "Read HEARTBEAT.md if it exists",
    # Twilio/SMS deployment: each real inbound text is preceded by an injected
    # "Conversation info (untrusted metadata)" message carrying chat_id etc.
    # It is role:user with a top-level timestamp, so it would otherwise be
    # falsely counted as a new user message — skip it. (The actual user text
    # arrives as a separate plain role:user line and is correctly counted.)
    "Conversation info (untrusted metadata)",
]


def parse_args():
    p = argparse.ArgumentParser(description="Memory Consolidation Dispatcher")
    sub = p.add_subparsers(dest="command", required=True)

    scan_p = sub.add_parser("scan", help="Scan workspaces, print JSON report")
    scan_p.add_argument("--verbose", action="store_true")

    disp_p = sub.add_parser("dispatch", help="Scan + create cron jobs")
    disp_p.add_argument("--dry-run", action="store_true", help="Print commands without executing")
    disp_p.add_argument("--limit", type=int, default=0, help="Max jobs to create (0=unlimited)")
    disp_p.add_argument("--gap", type=int, default=30, help="Seconds between jobs")
    disp_p.add_argument("--start-offset", type=int, default=120, help="Seconds from now for first job")
    disp_p.add_argument("--model", default="amazon-bedrock/arn:aws:bedrock:us-east-1:405912452115:inference-profile/us.anthropic.claude-sonnet-4-20250514-v1:0")
    disp_p.add_argument("--verbose", action="store_true")

    return p.parse_args()


def extract_account_id(workspace_path: str) -> str:
    """Derive the agentId from a workspace path.

    For the SMS deployment the workspace dir name IS the agentId (no prefix),
    e.g. /home/ec2-user/.openclaw/workspace-nutritionist/040108 → "040108".
    """
    return os.path.basename(workspace_path.rstrip("/"))


def get_agent_id(account_id: str) -> str:
    """The agentId is the workspace basename itself (no prefix)."""
    return account_id


def _session_dir_for(agent_id: str) -> str | None:
    """Resolve the sessions dir for an agentId.

    The agents/ dir name is a sanitized (lowercased) form of the agentId for
    mixed-case ids, so try the exact id first, then the lowercased id.
    """
    for candidate in (agent_id, agent_id.lower()):
        d = SESSION_DIR_TEMPLATE.format(agent_id=candidate)
        if os.path.isdir(d):
            return d
    return None


def find_latest_session_file(agent_id: str) -> str | None:
    """Find the most recently modified session file (non-deleted)."""
    session_dir = _session_dir_for(agent_id)
    if session_dir is None:
        return None
    candidates = []
    for f in os.listdir(session_dir):
        # Only the canonical session transcript: exclude soft-deleted sessions
        # and the *.trajectory.jsonl internal-events sibling (which holds tool
        # calls / cron injections, not the user-facing transcript).
        if not f.endswith(".jsonl"):
            continue
        if ".deleted." in f or f.endswith(".trajectory.jsonl"):
            continue
        full = os.path.join(session_dir, f)
        candidates.append((os.path.getmtime(full), full))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def has_new_user_messages(session_file: str, since_ts: float) -> bool:
    """Check if session file has real user messages after since_ts."""
    try:
        with open(session_file, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                # Quick pre-filter: must be a user message
                if '"role":"user"' not in line:
                    continue
                # Skip system/cron injections that have role:user wrapper
                skip = False
                for pat in SKIP_PATTERNS:
                    if pat in line:
                        skip = True
                        break
                if skip:
                    continue
                # Parse timestamp
                try:
                    d = json.loads(line)
                    ts_str = d.get("timestamp", "")
                    if ts_str:
                        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp()
                        if ts > since_ts:
                            return True
                except (json.JSONDecodeError, ValueError):
                    continue
        return False
    except (FileNotFoundError, PermissionError):
        return False


def count_user_messages_today(session_file: str, today_str: str) -> int:
    """Count real user messages from today."""
    count = 0
    try:
        with open(session_file, "r") as f:
            for line in f:
                if '"role":"user"' not in line:
                    continue
                if today_str not in line:
                    continue
                skip = False
                for pat in SKIP_PATTERNS:
                    if pat in line:
                        skip = True
                        break
                if skip:
                    continue
                count += 1
    except (FileNotFoundError, PermissionError):
        pass
    return count


def analyze_short_term(memory_dir: str) -> dict:
    """Analyze short-term.json status."""
    st_path = os.path.join(memory_dir, "short-term.json")
    result = {"exists": False, "has_entries": False, "has_old_entries": False,
              "entry_count": 0, "oldest_date": None, "newest_date": None}
    try:
        with open(st_path, "r") as f:
            data = json.load(f)
        result["exists"] = True
        # Handle formats: {"days": {...}}, {"days": [...]}, and bare [...]
        if isinstance(data, list):
            days = data
        else:
            days = data.get("days", [])
        if not days:
            return result

        all_entries = []
        # days can be a dict keyed by date, or a list of day objects
        if isinstance(days, dict):
            for date_str, day_obj in days.items():
                entries = day_obj.get("conversations", day_obj.get("entries", [])) if isinstance(day_obj, dict) else []
                if entries:
                    all_entries.append(date_str)
                    result["entry_count"] += len(entries)
        else:
            for day in days:
                if isinstance(day, str):
                    # Unexpected bare string in list, skip
                    continue
                date_str = day.get("date", "")
                entries = day.get("conversations", day.get("entries", []))
                if entries:
                    all_entries.append(date_str)
                    result["entry_count"] += len(entries)

        if all_entries:
            result["has_entries"] = True
            result["oldest_date"] = min(all_entries)
            result["newest_date"] = max(all_entries)

            # Check if any entries are old enough for medium-term consolidation
            cutoff = (datetime.now(timezone.utc) - timedelta(days=SHORT_TERM_MAX_AGE_DAYS)).strftime("%Y-%m-%d")
            if result["oldest_date"] < cutoff:
                result["has_old_entries"] = True

    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return result


def analyze_medium_term(memory_dir: str) -> dict:
    """Analyze medium-term.md status."""
    mt_path = os.path.join(memory_dir, "medium-term.md")
    result = {"exists": False, "line_count": 0, "section_count": 0,
              "over_limit": False, "last_consolidated": None}
    try:
        with open(mt_path, "r") as f:
            content = f.read()
        result["exists"] = True
        lines = content.strip().split("\n")
        result["line_count"] = len(lines)
        result["section_count"] = sum(1 for l in lines if l.startswith("## "))
        result["over_limit"] = result["line_count"] > 500

        # Try to find "Last consolidated" date
        m = re.search(r"Last consolidated[：:]\s*(\d{4}-\d{2}-\d{2})", content)
        if m:
            result["last_consolidated"] = m.group(1)
    except FileNotFoundError:
        pass
    return result


def analyze_long_term(memory_dir: str) -> dict:
    """Analyze long-term.md status."""
    lt_path = os.path.join(memory_dir, "long-term.md")
    result = {"exists": False, "line_count": 0, "last_updated": None,
              "needs_update": False, "mtime": None}
    try:
        stat = os.stat(lt_path)
        result["mtime"] = stat.st_mtime
        with open(lt_path, "r") as f:
            content = f.read()
        result["exists"] = True
        result["line_count"] = len(content.strip().split("\n"))

        # Try to find "Last updated" date
        m = re.search(r"\*\*Last updated[：:]\*\*\s*(\d{4}-\d{2}-\d{2})", content)
        if m:
            result["last_updated"] = m.group(1)
            last_dt = datetime.strptime(m.group(1), "%Y-%m-%d").replace(tzinfo=timezone.utc)
            if (datetime.now(timezone.utc) - last_dt).days >= LONG_TERM_UPDATE_INTERVAL_DAYS:
                result["needs_update"] = True
        else:
            # Fallback to mtime
            mtime_dt = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
            if (datetime.now(timezone.utc) - mtime_dt).days >= LONG_TERM_UPDATE_INTERVAL_DAYS:
                result["needs_update"] = True
    except FileNotFoundError:
        result["needs_update"] = True  # Missing → needs init + update
    return result


# Tasks that constitute "real" consolidation work requiring an agent turn.
# `init` is intentionally excluded: it is pure file creation, handled inline by
# the dispatcher (see maybe_init_inline) and never on its own justifies a turn.
REAL_WORK_TASKS = (
    "short-term-update",
    "medium-term-consolidate",
    "medium-term-cleanup",
    "long-term-promote",
)


def determine_tasks(short_term: dict, medium_term: dict, long_term: dict,
                    has_new_messages: bool) -> list[str]:
    """Determine which consolidation tasks a user needs."""
    tasks = []

    # Task 1: short-term update (new messages need summarizing)
    if has_new_messages:
        tasks.append("short-term-update")

    # Task 2: medium-term consolidation (old short-term entries to rotate + merge)
    if short_term["has_old_entries"]:
        tasks.append("medium-term-consolidate")

    # Task 3: medium-term cleanup (over 500 lines)
    if medium_term["over_limit"]:
        tasks.append("medium-term-cleanup")

    # Task 4: long-term promotion (>7 days since last update, and medium-term has substantial content)
    if long_term["needs_update"] and medium_term["section_count"] >= 3 and medium_term["line_count"] >= 50:
        tasks.append("long-term-promote")

    # Task 5: init missing files
    if not short_term["exists"] or not long_term["exists"]:
        tasks.append("init")

    return tasks


def has_real_work(tasks: list) -> bool:
    """True if the task list contains anything beyond `init`."""
    return any(t in REAL_WORK_TASKS for t in tasks)


def run_inline_init(memory_dir: str) -> bool:
    """Create missing memory files in-process (no agent turn).

    Invokes `memory-consolidator.py init` directly. Returns True on success.
    """
    import subprocess
    consolidator = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "memory-consolidator.py")
    try:
        r = subprocess.run(
            ["python3", consolidator, "init", "--memory-dir", memory_dir],
            capture_output=True, text=True, timeout=30,
        )
        return r.returncode == 0
    except Exception:
        return False


def count_real_workspaces() -> int:
    """Count workspaces that are real per-user agents (post skip-filter)."""
    n = 0
    for ws in glob.glob(WORKSPACE_GLOB):
        if not os.path.isdir(ws):
            continue
        name = os.path.basename(ws.rstrip("/"))
        if name in SKIP_WORKSPACE_NAMES or name.startswith(SKIP_WORKSPACE_PREFIXES):
            continue
        n += 1
    return n


def scan_all_workspaces(verbose: bool = False) -> list[dict]:
    """Scan all workspaces and determine consolidation needs."""
    workspaces = sorted(glob.glob(WORKSPACE_GLOB))
    now = datetime.now(timezone.utc)
    today_str = now.strftime("%Y-%m-%d")

    # "Since" timestamp: 24 hours ago for new message detection
    since_ts = (now - timedelta(hours=24)).timestamp()

    results = []
    for ws in workspaces:
        if not os.path.isdir(ws):
            continue  # glob may match non-dir entries (e.g. counter.json)

        account_id = extract_account_id(ws)

        # Skip non-user workspaces: pre-warmed pool agents, provisioning stubs,
        # and bookkeeping files.
        if account_id in SKIP_WORKSPACE_NAMES or account_id.startswith(SKIP_WORKSPACE_PREFIXES):
            if verbose:
                print(f"  SKIP {account_id}: not a real user workspace", file=sys.stderr)
            continue

        agent_id = get_agent_id(account_id)
        memory_dir = os.path.join(ws, MEMORY_SUBDIR)

        if not os.path.isdir(memory_dir):
            if verbose:
                print(f"  SKIP {account_id}: no memory dir", file=sys.stderr)
            continue

        # Analyze memory layers
        short_term = analyze_short_term(memory_dir)
        medium_term = analyze_medium_term(memory_dir)
        long_term = analyze_long_term(memory_dir)

        # Check for new user messages
        session_file = find_latest_session_file(agent_id)
        has_new = False
        if session_file:
            has_new = has_new_user_messages(session_file, since_ts)

        # Determine tasks
        tasks = determine_tasks(short_term, medium_term, long_term, has_new)

        # Optimization: dormant agents whose ONLY task is `init` (no new user
        # messages, no pending short→medium / medium→long work) are skipped
        # entirely — they don't need an agent turn. Their memory files are
        # created lazily during the next real conversation (normal short-term-
        # update flow), or inline here if they later acquire real work.
        if not has_real_work(tasks):
            if verbose:
                reason = "init-only (dormant)" if tasks else "no tasks needed"
                print(f"  SKIP {account_id}: {reason}", file=sys.stderr)
            continue

        # Agent has real work. `needs_init` flags that memory files are missing
        # and must be created inline (in-process) before the dispatched turn.
        needs_init = "init" in tasks
        dispatch_tasks = [t for t in tasks if t != "init"]

        results.append({
            "account_id": account_id,
            "agent_id": agent_id,
            "workspace": ws,
            "memory_dir": memory_dir,
            "tasks": dispatch_tasks,
            "needs_init": needs_init,
            "short_term": short_term,
            "medium_term": {"line_count": medium_term["line_count"],
                            "section_count": medium_term["section_count"],
                            "over_limit": medium_term["over_limit"]},
            "long_term": {"exists": long_term["exists"],
                          "needs_update": long_term["needs_update"],
                          "last_updated": long_term["last_updated"]},
            "has_new_messages": has_new,
        })

    return results


def build_sub_task_prompt(user: dict) -> str:
    """Build the agentTurn prompt for a per-user consolidation job."""
    tasks = user["tasks"]
    account_id = user["account_id"]
    workspace = user["workspace"]
    memory_dir = f"{workspace}/memory"
    agent_id = user["agent_id"]
    session_dir = _session_dir_for(agent_id) or SESSION_DIR_TEMPLATE.format(agent_id=agent_id)

    task_list = ", ".join(tasks)

    prompt = (
        f"Read the memory-consolidation skill at {SKILL_PATH} and follow it.\n\n"
        f"User: `{account_id}`\n"
        f"Workspace: `{workspace}`\n"
        f"Memory dir: `{memory_dir}`\n"
        f"Session dir: `{session_dir}`\n\n"
        f"Tasks: {task_list}\n\n"
        f"Execute only the listed tasks. Reply with a brief JSON summary when done: "
        '{"tasks_completed": [...], "entries_added": N, "topics_updated": N}'
    )

    return prompt


def dispatch_jobs(users: list[dict], args) -> list[dict]:
    """Create one-shot cron jobs for each user."""
    import subprocess

    now = datetime.now(timezone.utc)
    start_time = now + timedelta(seconds=args.start_offset)
    created = []

    for i, user in enumerate(users):
        if args.limit and i >= args.limit:
            break

        job_time = start_time + timedelta(seconds=i * args.gap)
        at_str = job_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        agent_id = user["agent_id"]
        task_summary = "+".join(user["tasks"])
        init_note = " (+inline init)" if user.get("needs_init") else ""

        # Create missing memory files in-process before dispatching the turn,
        # so the consolidation job has files to operate on. No agent turn.
        if user.get("needs_init"):
            if args.dry_run:
                pass  # report only; don't touch the filesystem in dry-run
            elif not run_inline_init(user["memory_dir"]):
                print(f"⚠️  [{i+1}/{len(users)}] {user['account_id']}: inline init failed; "
                      f"dispatching anyway (job will init via skill)", file=sys.stderr)

        prompt = build_sub_task_prompt(user)

        cmd = [
            "openclaw", "cron", "add",
            "--name", f"memory-consolidation-{user['account_id'][:12]}",
            "--agent", agent_id,
            "--session", "isolated",
            "--at", at_str,
            "--message", prompt,
            "--model", args.model,
            "--delete-after-run",
            "--timeout-seconds", "300",
            "--no-deliver",
            "--json",
        ]

        if args.dry_run:
            print(f"DRY-RUN [{i+1}/{len(users)}] {user['account_id']} @ {at_str} | tasks: {task_summary}{init_note}")
            created.append({"account_id": user["account_id"], "at": at_str,
                            "tasks": user["tasks"], "needs_init": user.get("needs_init", False),
                            "dry_run": True})
        else:
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
                if r.returncode == 0:
                    job = json.loads(r.stdout)
                    print(f"✅ [{i+1}/{len(users)}] {user['account_id']} → {at_str} (id: {job['id'][:8]}) | {task_summary}")
                    created.append({"account_id": user["account_id"], "at": at_str,
                                    "tasks": user["tasks"], "job_id": job["id"]})
                else:
                    print(f"❌ [{i+1}/{len(users)}] {user['account_id']}: {r.stderr[:100]}", file=sys.stderr)
            except Exception as e:
                print(f"❌ [{i+1}/{len(users)}] {user['account_id']}: {e}", file=sys.stderr)

    return created


def main():
    args = parse_args()

    if args.command == "scan":
        print("Scanning workspaces...", file=sys.stderr)
        users = scan_all_workspaces(verbose=args.verbose)
        # Summary
        task_counts = {}
        for u in users:
            for t in u["tasks"]:
                task_counts[t] = task_counts.get(t, 0) + 1
        inline_init_count = sum(1 for u in users if u.get("needs_init"))

        summary = {
            "scan_time": datetime.now(timezone.utc).isoformat(),
            "total_workspaces": count_real_workspaces(),
            "users_needing_work": len(users),
            "task_breakdown": task_counts,
            "inline_init_count": inline_init_count,
            "users": users,
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))

    elif args.command == "dispatch":
        print("Scanning workspaces...", file=sys.stderr)
        users = scan_all_workspaces(verbose=args.verbose)

        if not users:
            print("No users need consolidation. Done.")
            return

        # Sort: users with more tasks first, then by account_id
        users.sort(key=lambda u: (-len(u["tasks"]), u["account_id"]))

        task_counts = {}
        for u in users:
            for t in u["tasks"]:
                task_counts[t] = task_counts.get(t, 0) + 1

        print(f"\nFound {len(users)} users needing work:")
        for t, c in sorted(task_counts.items()):
            print(f"  {t}: {c}")
        print()

        created = dispatch_jobs(users, args)
        total_time = len(created) * args.gap
        print(f"\n{'Would create' if args.dry_run else 'Created'} {len(created)} jobs, "
              f"spanning ~{total_time // 60}m{total_time % 60}s")


if __name__ == "__main__":
    main()
