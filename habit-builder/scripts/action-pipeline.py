#!/usr/bin/env python3
"""
Habit-builder action pipeline utilities.

Subcommands:
  prioritize         Score and rank actions by Impact × Ease + chain bonus
  schedule           Return check-in frequency for a given cadence + phase
  check-graduation   Evaluate whether an action is ready to graduate
  activate           Generate habits.active entry from an action_queue item
"""

import argparse
import json
import sys
from datetime import datetime, timedelta

# ── Schedule table ──────────────────────────────────────────────────────────
# Key: (cadence, phase) → check-in rule
# For daily cadences (every_meal / daily_fixed / daily_random):
#   value = number of days between mentions
# For weekly / conditional:
#   value = fraction of occurrences to mention (1.0 = every, 0.5 = half)

SCHEDULE = {
    # Daily cadences: Anchor allows daily check-in
    ("every_meal",   "anchor"):    1,    # every day
    ("every_meal",   "build"):     3,    # every 3 days
    ("every_meal",   "solidify"):  5,    # every 5 days
    ("every_meal",   "autopilot"): 7,    # once a week

    ("daily_fixed",  "anchor"):    1,    # every day
    ("daily_fixed",  "build"):     3,
    ("daily_fixed",  "solidify"):  5,
    ("daily_fixed",  "autopilot"): 7,

    ("daily_random", "anchor"):    1,    # every day
    ("daily_random", "build"):     3,
    ("daily_random", "solidify"):  7,    # once a week
    ("daily_random", "autopilot"): -1,   # only if regression

    # Occurrence-based cadences: value = fraction of occurrences to mention
    ("weekly",       "anchor"):    1.0,  # every occurrence
    ("weekly",       "build"):     1.0,
    ("weekly",       "solidify"):  0.5,  # every other
    ("weekly",       "autopilot"): -1,   # only if regression

    ("conditional",  "anchor"):    1.0,
    ("conditional",  "build"):     1.0,
    ("conditional",  "solidify"):  0.5,
    ("conditional",  "autopilot"): -1,
}

# Phase boundaries (days since activation)
PHASE_BOUNDARIES = {
    "anchor":    (0, 7),
    "build":     (8, 21),
    "solidify":  (22, None),  # open-ended until graduation
}

# Graduation requirements by cadence
GRADUATION = {
    # cadence → (min_sample, unit)
    # unit: "days" = calendar days, "occurrences" = trigger events
    "every_meal":   (14, "days"),
    "daily_fixed":  (14, "days"),
    "daily_random": (14, "days"),
    "weekly":       (6,  "occurrences"),
    "conditional":  (8,  "occurrences"),
}

COMPLETION_THRESHOLD = 0.80  # 80%
SELF_INIT_THRESHOLD = 0.30   # 30%
NO_RESPONSE_STALL = 3        # consecutive no-responses → stall
FAILURE_THRESHOLD = 3         # consecutive missed/no_response → failure
MAX_ACTIVE_DAYS = 90         # auto-pause after this
MAX_CONCURRENT = 3           # max active habits
STABILIZE_THRESHOLD = 0.70   # below this → suggest stabilizing before adding


# ── Cadence → habit type mapping ────────────────────────────────────────────

CADENCE_TO_TYPE = {
    "every_meal":   "meal-bound",
    "daily_fixed":  "post-meal",   # default; caller may override to
                                   # "meal-bound" or "end-of-day" based on
                                   # trigger time vs meal schedule
    "daily_random": "all-day",
    "weekly":       "weekly",
    "conditional":  "conditional",
}


def get_phase(days_since_activation: int) -> str:
    """Return current phase name given days since activation."""
    for phase, (start, end) in PHASE_BOUNDARIES.items():
        if end is None:
            if days_since_activation >= start:
                return phase
        elif start <= days_since_activation <= end:
            return phase
    return "solidify"


# ── Subcommands ─────────────────────────────────────────────────────────────

def cmd_prioritize(args):
    """Score and sort actions. Input: JSON array on stdin or --actions."""
    actions = json.loads(args.actions)
    for a in actions:
        impact = a.get("impact", 1)
        ease = a.get("ease", 1)
        chain = 1 if a.get("chain", False) else 0
        a["priority_score"] = impact * ease + chain
    actions.sort(key=lambda a: a["priority_score"], reverse=True)
    print(json.dumps(actions, ensure_ascii=False, indent=2))


def cmd_schedule(args):
    """Return check-in rule for a cadence + phase."""
    phase = args.phase or get_phase(args.days or 0)
    key = (args.cadence, phase)

    # Autopilot: check if eligible for graduation first
    if phase == "solidify" and args.days and args.days > 42:
        phase = "autopilot"
        key = (args.cadence, "autopilot")

    freq = SCHEDULE.get(key)
    if freq is None:
        print(json.dumps({"error": f"Unknown cadence/phase: {key}"}))
        sys.exit(1)

    is_daily = args.cadence in ("every_meal", "daily_fixed", "daily_random")
    result = {
        "cadence": args.cadence,
        "phase": phase,
        "frequency_type": "interval_days" if is_daily else "occurrence_fraction",
        "value": freq,
    }
    if freq == -1:
        result["rule"] = "only_if_regression"
    elif is_daily:
        result["rule"] = f"mention every {freq} day(s)"
    else:
        result["rule"] = f"mention {int(freq * 100)}% of occurrences"

    print(json.dumps(result, ensure_ascii=False))


def cmd_check_graduation(args):
    """Check if an action is ready to graduate."""
    log = json.loads(args.log)  # array of {"date", "result", "self_initiated"}
    cadence = args.cadence

    min_sample, unit = GRADUATION[cadence]

    if unit == "days":
        # Filter to the last min_sample days (inclusive, truncate to midnight)
        cutoff = (datetime.now() - timedelta(days=min_sample)).replace(
            hour=0, minute=0, second=0, microsecond=0)
        recent = [e for e in log
                  if datetime.fromisoformat(e["date"]) >= cutoff]
    else:
        # Last N occurrences
        recent = log[-min_sample:] if len(log) >= min_sample else []

    # Check consecutive no-response for stall detection (always, even if
    # insufficient data — stall can happen before enough samples accumulate)
    consecutive_no_response = 0
    for e in reversed(log):
        if e["result"] == "no_response":
            consecutive_no_response += 1
        else:
            break
    stall = consecutive_no_response >= NO_RESPONSE_STALL

    if not recent or len(recent) < min_sample:
        print(json.dumps({
            "eligible": False,
            "reason": f"insufficient_data: {len(recent)}/{min_sample}",
            "stall": stall,
        }))
        return

    completed = sum(1 for e in recent if e["result"] == "completed")
    total = len(recent)
    rate = completed / total

    self_init_count = sum(1 for e in recent
                          if e.get("self_initiated", False))
    self_init_rate = self_init_count / total if total else 0

    signal_1 = rate >= COMPLETION_THRESHOLD
    signal_2 = self_init_rate >= SELF_INIT_THRESHOLD

    result = {
        "eligible": signal_1 and signal_2,
        "signal_1_completion": {"rate": round(rate, 2), "pass": signal_1},
        "signal_2_self_init": {"rate": round(self_init_rate, 2), "pass": signal_2},
        "signal_3_user_confirm": "ask_user",
        "stall": stall,
        "sample_size": total,
    }
    # Signal 1 + (Signal 2 OR Signal 3) — Signal 3 needs user input
    if signal_1 and not signal_2:
        result["eligible"] = False
        result["action"] = "ask_signal_3"
        result["prompt"] = "这个习惯还需要我提醒吗，还是已经成自然了？"

    print(json.dumps(result, ensure_ascii=False))


def cmd_activate(args):
    """Generate a habits.active entry from action_queue item."""
    action = json.loads(args.action)
    cadence = action.get("trigger_cadence", "daily_fixed")

    entry = {
        "habit_id": action["action_id"],
        "description": action["description"],
        "tiny_version": action.get("behavior", action["description"]),
        "trigger": action["trigger"],
        "type": CADENCE_TO_TYPE.get(cadence, "all-day"),
        "bound_to_meal": action.get("bound_to_meal"),
        "trigger_cadence": cadence,
        "created_at": datetime.now().strftime("%Y-%m-%d"),
        "phase": "anchor",
        "source_advice": args.source_advice or "",
        "mention_log": [],
        "completion_log": [],
    }
    print(json.dumps(entry, ensure_ascii=False, indent=2))


def cmd_should_mention(args):
    """Decide whether to mention a habit in the current meal conversation."""
    habit = json.loads(args.habit)
    cadence = habit.get("trigger_cadence", "daily_fixed")
    habit_type = habit.get("type", "all-day")
    current_meal = args.meal
    days = args.days or 0

    # Weekly: only on the relevant day
    if habit_type == "weekly":
        # Caller must pass --today-matches if today is the relevant day
        if not args.today_matches:
            print(json.dumps({"mention": False, "reason": "wrong_day"}))
            return

    # Conditional: never proactive — caller decides based on conversation
    if habit_type == "conditional":
        print(json.dumps({"mention": False,
                          "reason": "conditional_reactive_only"}))
        return

    # Check min gap: last mention must be ≥ min_gap_reminders ago
    last_mention_ago = args.reminders_since_last_mention
    if last_mention_ago is not None and last_mention_ago < 2:
        print(json.dumps({"mention": False, "reason": "too_soon",
                          "reminders_since_last": last_mention_ago}))
        return

    # Get schedule frequency
    phase = args.phase or get_phase(days)
    if phase == "solidify" and days > 42:
        phase = "autopilot"
    key = (cadence, phase)
    freq = SCHEDULE.get(key)

    if freq == -1:
        print(json.dumps({"mention": False,
                          "reason": "autopilot_no_regression"}))
        return

    is_daily = cadence in ("every_meal", "daily_fixed", "daily_random")

    # Check meal match for meal-bound and post-meal types
    bound = habit.get("bound_to_meal")
    if bound and current_meal and bound != current_meal:
        if habit_type in ("meal-bound", "post-meal"):
            print(json.dumps({"mention": False, "reason": "wrong_meal",
                              "bound_to": bound, "current": current_meal}))
            return

    # For daily cadences, check if enough days have passed since last mention
    if is_daily:
        days_since = args.days_since_last_mention
        if days_since is not None and days_since < freq:
            print(json.dumps({"mention": False, "reason": "interval_not_reached",
                              "need": freq, "elapsed": days_since}))
            return

    print(json.dumps({"mention": True, "phase": phase,
                      "frequency": freq, "type": habit_type}))


def cmd_check_failure(args):
    """Check if a habit has hit the failure threshold."""
    log = json.loads(args.log)

    consecutive_fail = 0
    for e in reversed(log):
        if e["result"] in ("missed", "no_response"):
            consecutive_fail += 1
        else:
            break

    failed = consecutive_fail >= FAILURE_THRESHOLD
    result = {
        "failed": failed,
        "consecutive_fail": consecutive_fail,
        "threshold": FAILURE_THRESHOLD,
    }
    if failed:
        result["action"] = "surface_gently"
        result["options"] = ["keep_going", "make_easier", "try_different"]

    print(json.dumps(result, ensure_ascii=False))


def cmd_check_concurrency(args):
    """Check if a new habit can be added given current active count."""
    active_habits = json.loads(args.active_habits)
    count = len(active_habits)

    if count >= MAX_CONCURRENT:
        print(json.dumps({
            "can_add": False,
            "reason": "at_max",
            "active": count,
            "max": MAX_CONCURRENT,
        }))
        return

    # Check if any active habit is struggling
    struggling = []
    for h in active_habits:
        log = h.get("completion_log", [])
        if len(log) >= 7:
            recent = log[-7:]
            completed = sum(1 for e in recent if e.get("result") == "completed")
            rate = completed / len(recent)
            if rate < STABILIZE_THRESHOLD:
                struggling.append({
                    "habit_id": h.get("habit_id"),
                    "rate_7d": round(rate, 2),
                })

    print(json.dumps({
        "can_add": len(struggling) == 0,
        "reason": "struggling_habits" if struggling else "ok",
        "active": count,
        "max": MAX_CONCURRENT,
        "struggling": struggling,
    }, ensure_ascii=False))


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command")

    # prioritize
    pr = sub.add_parser("prioritize",
                        help="Score and rank actions")
    pr.add_argument("--actions", required=True,
                    help='JSON array: [{"impact":3,"ease":2,"chain":true,...}]')

    # schedule
    sc = sub.add_parser("schedule",
                        help="Get check-in frequency")
    sc.add_argument("--cadence", required=True,
                    choices=["every_meal","daily_fixed","daily_random",
                             "weekly","conditional"])
    sc.add_argument("--days", type=int,
                    help="Days since activation (auto-detects phase)")
    sc.add_argument("--phase",
                    choices=["anchor","build","solidify","autopilot"],
                    help="Override phase directly")

    # check-graduation
    cg = sub.add_parser("check-graduation",
                        help="Check graduation eligibility")
    cg.add_argument("--cadence", required=True,
                    choices=["every_meal","daily_fixed","daily_random",
                             "weekly","conditional"])
    cg.add_argument("--log", required=True,
                    help='JSON array: [{"date":"2026-04-01","result":"completed","self_initiated":false}]')

    # activate
    ac = sub.add_parser("activate",
                        help="Generate habits.active entry from queue item")
    ac.add_argument("--action", required=True,
                    help="JSON object: single action from action_queue")
    ac.add_argument("--source-advice", default="",
                    help="The source_advice string from the parent queue")

    # should-mention
    sm = sub.add_parser("should-mention",
                        help="Decide whether to mention a habit now")
    sm.add_argument("--habit", required=True,
                    help="JSON object: the habit from habits.active")
    sm.add_argument("--meal",
                    help="Current meal (breakfast/lunch/dinner)")
    sm.add_argument("--days", type=int,
                    help="Days since activation")
    sm.add_argument("--phase",
                    choices=["anchor","build","solidify","autopilot"])
    sm.add_argument("--days-since-last-mention", type=int, dest="days_since_last_mention",
                    help="Calendar days since last mention")
    sm.add_argument("--reminders-since-last-mention", type=int,
                    dest="reminders_since_last_mention",
                    help="Number of reminders since last mention")
    sm.add_argument("--today-matches", action="store_true",
                    dest="today_matches",
                    help="For weekly habits: today is the relevant day")

    # check-failure
    cf = sub.add_parser("check-failure",
                        help="Check if habit hit failure threshold")
    cf.add_argument("--log", required=True,
                    help='JSON array of completion log entries')

    # check-concurrency
    cc = sub.add_parser("check-concurrency",
                        help="Check if a new habit can be added")
    cc.add_argument("--active-habits", required=True, dest="active_habits",
                    help="JSON array of current active habits with completion_log")

    args = p.parse_args()
    if not args.command:
        p.print_help()
        sys.exit(1)

    {
        "prioritize": cmd_prioritize,
        "schedule": cmd_schedule,
        "check-graduation": cmd_check_graduation,
        "activate": cmd_activate,
        "should-mention": cmd_should_mention,
        "check-failure": cmd_check_failure,
        "check-concurrency": cmd_check_concurrency,
    }[args.command](args)


if __name__ == "__main__":
    main()
