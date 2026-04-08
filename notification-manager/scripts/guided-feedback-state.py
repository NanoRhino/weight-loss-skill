#!/usr/bin/env python3
"""
guided-feedback-state.py — State management for guided-feedback system.

Commands:
  increment    Increment check-in counter and add today to active days.
  next         Get the next question to schedule (if trigger met).
  status       Show current state summary.
  update       Update a question's status.
  skip-check   Check for questions past 24h skip timer.
  init         Create initial guided-feedback.json.

Usage:
  python3 guided-feedback-state.py --workspace-dir <path> --tz-offset <sec> <command> [options]

  increment    (no extra options)
  next         → prints JSON: {"action":"schedule"|"wait"|"done", "question_id":..., "chain_next":...}
  status       → prints JSON summary
  update       --question-id <id> --new-status <status> [--answer <text>]
  skip-check   → prints JSON: {"skipped": [...ids...], "next_chain_scheduled": true|false}
  init         → creates data/guided-feedback.json with default queue
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta

CHAIN_MAP = {
    "reminder-timing": ["reminder-frequency", "reminder-style"],
    "feedback-tone": ["food-preference", "advice-intensity"],
}

CHAIN_HEADS = ["reminder-timing", "feedback-tone"]

TERMINAL_STATUSES = {"answered", "skipped", "covered"}


def log(msg):
    print(f"[guided-feedback-state] {msg}", file=sys.stderr)


def get_local_date(tz_offset):
    tz = timezone(timedelta(seconds=tz_offset))
    return datetime.now(tz).strftime("%Y-%m-%d")


def get_now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_data(workspace_dir):
    path = os.path.join(workspace_dir, "data", "guided-feedback.json")
    if not os.path.exists(path):
        return None, path
    with open(path) as f:
        return json.load(f), path


def save_data(data, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_default_data():
    return {
        "total_check_ins": 0,
        "distinct_active_days": [],
        "queue": [
            {"id": "reminder-timing", "group": "reminder",
             "same_day_chain": ["reminder-frequency", "reminder-style"],
             "trigger": "total_check_ins >= 3",
             "status": "pending", "scheduled_at": None,
             "asked_at": None, "answered_at": None, "answer": None},
            {"id": "reminder-frequency", "group": "reminder",
             "trigger": "same_day_chain",
             "status": "pending", "scheduled_at": None,
             "asked_at": None, "answered_at": None, "answer": None},
            {"id": "reminder-style", "group": "reminder",
             "trigger": "same_day_chain",
             "status": "pending", "scheduled_at": None,
             "asked_at": None, "answered_at": None, "answer": None},
            {"id": "feedback-tone", "group": "feedback",
             "same_day_chain": ["food-preference", "advice-intensity"],
             "trigger": "reminder chain terminal",
             "status": "pending", "scheduled_at": None,
             "asked_at": None, "answered_at": None, "answer": None},
            {"id": "food-preference", "group": "feedback",
             "trigger": "same_day_chain",
             "status": "pending", "scheduled_at": None,
             "asked_at": None, "answered_at": None, "answer": None},
            {"id": "advice-intensity", "group": "feedback",
             "trigger": "same_day_chain",
             "status": "pending", "scheduled_at": None,
             "asked_at": None, "answered_at": None, "answer": None},
            {"id": "open-review", "group": "review",
             "trigger": "distinct_active_days >= 5",
             "status": "pending", "scheduled_at": None,
             "asked_at": None, "answered_at": None, "answer": None},
        ],
        "preference_signals": []
    }


def find_question(data, qid):
    for q in data["queue"]:
        if q["id"] == qid:
            return q
    return None


def is_covered(data, qid):
    for sig in data.get("preference_signals", []):
        if sig.get("covers") == qid:
            return True
    return False


def get_chain_for(qid):
    """Return the full chain list if qid is a chain head, else None."""
    return CHAIN_MAP.get(qid)


def get_chain_next(data, qid):
    """If qid is in a chain, return the next pending question in chain."""
    for head, members in CHAIN_MAP.items():
        full_chain = [head] + members
        if qid in full_chain:
            idx = full_chain.index(qid)
            for next_id in full_chain[idx + 1:]:
                q = find_question(data, next_id)
                if q and q["status"] == "pending":
                    if is_covered(data, next_id):
                        q["status"] = "covered"
                        continue
                    return next_id
            return None
    return None


def is_chain_terminal(data, group_ids):
    """Check if all questions in a list are in terminal status."""
    for qid in group_ids:
        q = find_question(data, qid)
        if q and q["status"] not in TERMINAL_STATUSES:
            return False
    return True


def cmd_increment(data, tz_offset):
    data["total_check_ins"] = data.get("total_check_ins", 0) + 1
    today = get_local_date(tz_offset)
    days = data.get("distinct_active_days", [])
    if today not in days:
        days.append(today)
    data["distinct_active_days"] = days
    return {
        "total_check_ins": data["total_check_ins"],
        "distinct_active_days": len(days),
        "today": today
    }


def cmd_next(data):
    """Determine which question to schedule next (chain heads only)."""
    queue = data["queue"]

    for q in queue:
        if q["status"] != "pending":
            continue

        qid = q["id"]

        # Skip non-chain-heads (they're triggered by chain flow, not scheduler)
        if q.get("trigger") == "same_day_chain":
            continue

        # Check if covered by preference signals
        if is_covered(data, qid):
            q["status"] = "covered"
            continue

        # Check trigger condition
        if qid == "reminder-timing":
            if data.get("total_check_ins", 0) >= 3:
                return {"action": "schedule", "question_id": qid}
            return {"action": "wait", "reason": f"total_check_ins={data.get('total_check_ins', 0)}, need 3"}

        if qid == "feedback-tone":
            # Requires reminder chain to be terminal
            reminder_ids = ["reminder-timing", "reminder-frequency", "reminder-style"]
            if is_chain_terminal(data, reminder_ids):
                return {"action": "schedule", "question_id": qid}
            return {"action": "wait", "reason": "reminder chain not complete"}

        if qid == "open-review":
            days = data.get("distinct_active_days", [])
            if len(days) >= 5:
                return {"action": "schedule", "question_id": qid}
            return {"action": "wait", "reason": f"distinct_active_days={len(days)}, need 5"}

    return {"action": "done", "reason": "all questions completed"}


def cmd_status(data):
    summary = []
    for q in data["queue"]:
        summary.append({"id": q["id"], "status": q["status"]})
    return {
        "total_check_ins": data.get("total_check_ins", 0),
        "distinct_active_days": len(data.get("distinct_active_days", [])),
        "questions": summary
    }


def _write_short_term_hint(workspace_dir, question_id):
    """Write a hint to short-term.json so the main session knows a guided-feedback
    question was asked and can route the user's reply correctly."""
    st_path = os.path.join(workspace_dir, "memory", "short-term.json")
    try:
        if os.path.isfile(st_path):
            with open(st_path, "r") as f:
                entries = json.load(f)
        else:
            entries = []

        # Remove any existing guided-feedback hint (only one at a time)
        entries = [e for e in entries if e.get("topic") != "guided-feedback-pending-reply"]

        now = get_now_iso()
        entries.append({
            "date": now[:10],
            "time": now[11:16],
            "topic": "guided-feedback-pending-reply",
            "summary": (
                f"我刚通过定时消息向用户发送了偏好调查问题（{question_id}），"
                "用户如果回复数字（1/2/3）或简短文字，这是对偏好问题的回答。"
                "请读 notification-composer SKILL.md 的'Handling replies'部分处理回复，"
                f"调用 guided-feedback-state.py update --question-id {question_id} "
                "--new-status answered --answer <用户回复>"
            ),
            "follow_ups": [f"处理用户对 {question_id} 的偏好回复"],
            "_guided_feedback": {"question_id": question_id, "status": "asked"}
        })

        with open(st_path, "w") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log(f"Warning: failed to write short-term hint: {e}")


def _clear_short_term_hint(workspace_dir):
    """Remove the guided-feedback hint from short-term.json after answer/skip."""
    st_path = os.path.join(workspace_dir, "memory", "short-term.json")
    try:
        if not os.path.isfile(st_path):
            return
        with open(st_path, "r") as f:
            entries = json.load(f)
        entries = [e for e in entries if e.get("topic") != "guided-feedback-pending-reply"]
        with open(st_path, "w") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log(f"Warning: failed to clear short-term hint: {e}")


def cmd_update(data, question_id, new_status, answer=None, workspace_dir=None):
    q = find_question(data, question_id)
    if not q:
        return {"error": f"question '{question_id}' not found"}

    q["status"] = new_status
    now = get_now_iso()

    if new_status == "scheduled":
        q["scheduled_at"] = now
    elif new_status == "asked":
        q["asked_at"] = now
        if workspace_dir:
            _write_short_term_hint(workspace_dir, question_id)
    elif new_status == "answered":
        q["answered_at"] = now
        q["answer"] = answer
        if workspace_dir:
            _clear_short_term_hint(workspace_dir)

    # Determine chain next
    chain_next = None
    if new_status == "answered":
        chain_next = get_chain_next(data, question_id)
    elif new_status == "skipped":
        # Skip remaining chain members
        for head, members in CHAIN_MAP.items():
            full_chain = [head] + members
            if question_id in full_chain:
                idx = full_chain.index(question_id)
                for remaining_id in full_chain[idx + 1:]:
                    rq = find_question(data, remaining_id)
                    if rq and rq["status"] == "pending":
                        rq["status"] = "skipped"

    return {
        "updated": question_id,
        "new_status": new_status,
        "chain_next": chain_next
    }


def cmd_skip_check(data, workspace_dir=None):
    """Check for questions past 24h skip timer."""
    now = datetime.now(timezone.utc)
    skipped = []

    for q in data["queue"]:
        if q["status"] != "asked":
            continue
        asked_at = q.get("asked_at")
        if not asked_at:
            continue
        try:
            asked_time = datetime.fromisoformat(asked_at)
            if (now - asked_time).total_seconds() > 86400:
                result = cmd_update(data, q["id"], "skipped", workspace_dir=workspace_dir)
                skipped.append(q["id"])
        except (ValueError, TypeError):
            continue

    return {"skipped": skipped}


def backfill_counters(data, workspace_dir, tz_offset):
    """Scan existing meal data to populate counters for existing users."""
    meals_dir = os.path.join(workspace_dir, "data", "meals")
    if not os.path.isdir(meals_dir):
        return 0, []

    total = 0
    active_days = []

    # Scan daily meal files (YYYY-MM-DD.json)
    for fname in sorted(os.listdir(meals_dir)):
        if not fname.endswith(".json") or len(fname) != 15:  # YYYY-MM-DD.json
            continue
        date_str = fname[:-5]
        fpath = os.path.join(meals_dir, fname)
        try:
            with open(fpath) as f:
                meals = json.load(f)
            if not isinstance(meals, list):
                continue
            meal_count = len(meals)
            if meal_count > 0:
                active_days.append(date_str)
                total += meal_count
        except (json.JSONDecodeError, IOError):
            continue

    data["total_check_ins"] = total
    data["distinct_active_days"] = active_days
    return total, active_days


def cmd_init(workspace_dir, tz_offset):
    path = os.path.join(workspace_dir, "data", "guided-feedback.json")
    if os.path.exists(path):
        return {"action": "exists", "path": path}
    data = get_default_data()
    total, active_days = backfill_counters(data, workspace_dir, tz_offset)
    save_data(data, path)
    return {
        "action": "created",
        "path": path,
        "backfilled": total > 0,
        "total_check_ins": total,
        "distinct_active_days": len(active_days)
    }


def main():
    parser = argparse.ArgumentParser(description="Guided feedback state management")
    parser.add_argument("--workspace-dir", required=True)
    parser.add_argument("--tz-offset", type=int, default=28800)
    parser.add_argument("command", choices=["increment", "next", "status", "update", "skip-check", "init"])
    parser.add_argument("--question-id", default=None)
    parser.add_argument("--new-status", default=None)
    parser.add_argument("--answer", default=None)
    args = parser.parse_args()

    if args.command == "init":
        result = cmd_init(args.workspace_dir, args.tz_offset)
        print(json.dumps(result, ensure_ascii=False))
        return

    data, path = load_data(args.workspace_dir)
    if data is None:
        # Auto-init for existing users: create + backfill + proceed
        log("guided-feedback.json not found, auto-initializing with backfill")
        init_result = cmd_init(args.workspace_dir, args.tz_offset)
        data, path = load_data(args.workspace_dir)
        if data is None:
            print(json.dumps({"error": "failed to auto-init guided-feedback.json"}))
            sys.exit(1)

    if args.command == "increment":
        result = cmd_increment(data, args.tz_offset)
    elif args.command == "next":
        result = cmd_next(data)
    elif args.command == "status":
        result = cmd_status(data)
    elif args.command == "update":
        if not args.question_id or not args.new_status:
            print(json.dumps({"error": "--question-id and --new-status required"}))
            sys.exit(1)
        result = cmd_update(data, args.question_id, args.new_status, args.answer, workspace_dir=args.workspace_dir)
    elif args.command == "skip-check":
        result = cmd_skip_check(data, workspace_dir=args.workspace_dir)

    save_data(data, path)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
