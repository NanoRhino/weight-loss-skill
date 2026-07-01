#!/usr/bin/env python3
# /// script
# requires-python = ">=3.6"
# dependencies = []
# ///
"""
Unified daily energy-balance resolver (owner: exercise-tracking-planning).

Answers the single question "am I in a deficit today?" deterministically, by
combining the three inputs that already live in the workspace:

  expenditure = tdee_base (NEAT TDEE, from data/plan.json)
              + exercise_burn_net (net kcal, from data/exercise.json)
  intake      = sum of meals[].calories (from data/meals/{date}.json)
  balance     = expenditure - intake         (+ = deficit, - = surplus)

"Derive, don't store" (CONVENTIONS §12): this script persists nothing. It reads
plan.json + exercise-calc.py + nutrition-calc.py and re-implements none of their
math (no MET table, no Atwater / nutrition logic).

DEFICIT RULE (locked design decision Q2 = "net deficit, fixed target"): the
eating target from the plan does NOT move when the user exercises. We report the
true NET balance (which DOES credit the workout) AND the intake-vs-target number
side by side, so the coach can show both without ever telling the user their
eating target went up.

CLI:
  python3 energy-balance.py --data-dir {ws}/data --date YYYY-MM-DD
    [--exercise-calc /path/to/exercise-calc.py]
    [--nutrition-calc /path/to/nutrition-calc.py]

Output (JSON, single object):
  {
    "date": "2026-07-01",
    "tdee_base": 1850,
    "exercise_burn_net": 300,
    "expenditure": 2150,            # tdee_base + exercise_burn_net
    "intake": 1200,
    "balance": 950,                 # expenditure - intake; + = deficit
    "verdict": "deficit",           # deficit | maintenance | surplus (±100 band)
    "eating_target": 1404,          # daily_calorie_target from plan.json (UNCHANGED)
    "intake_vs_target": 204,        # eating_target - intake (+ = under target)
    "data_complete": true,
    "notes": []
  }

Fail-open: if plan.json / tdee_base is missing, returns data_complete=false with
tdee_base=null and a degraded note (mirrors the insufficient_data pattern in
weight-gain-strategy/analyze-weight-trend.py). Callers should degrade gracefully
(skip the net-balance line) rather than error.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

# ±kcal band around zero within which we call it "maintenance" (per the plan).
MAINTENANCE_BAND = 100


def _normalize_path(p):
    """Lowercase wechat-dm/wecom-dm segment to avoid case-mismatch directories
    (mirrors exercise-calc.py / nutrition-calc.py)."""
    import re as _re
    return _re.sub(r'(workspace-(?:wechat|wecom)-dm-)([^/]+)',
                   lambda m: m.group(1) + m.group(2).lower(), p)


def _local_date(tz_offset=None):
    # type: (int) -> str
    """Local YYYY-MM-DD given tz_offset seconds; server date if None."""
    if tz_offset is not None:
        return (datetime.now(timezone.utc) + timedelta(seconds=tz_offset)).strftime("%Y-%m-%d")
    return datetime.now().strftime("%Y-%m-%d")


def _run_json(cmd):
    # type: (list) -> object
    """Run a subprocess and return parsed JSON stdout, or None on any failure.

    Mirrors analyze-weight-trend.py:run_script — we never raise, callers treat
    None as 'input unavailable' and fail open."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return None
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError, OSError):
        return None


def _find_script(explicit, filename, *rel_dirs):
    # type: (str, str, str) -> str
    """Resolve a sibling calc script.

    Priority: explicit CLI path → each rel_dir (relative to this script's dir,
    walking up for the skills-root layout) → bare filename (PATH / cwd). Returns
    the first existing path, else the bare filename (subprocess then fails → None
    → fail-open)."""
    if explicit and os.path.exists(explicit):
        return explicit
    here = os.path.dirname(os.path.abspath(__file__))
    for rel in rel_dirs:
        cand = os.path.normpath(os.path.join(here, rel, filename))
        if os.path.exists(cand):
            return cand
    return filename


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

def load_plan(data_dir):
    # type: (str) -> dict
    """Read data/plan.json. Returns {} if missing/unreadable (fail-open)."""
    p = os.path.join(data_dir, "plan.json")
    if not os.path.exists(p):
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def load_exercise_burn_net(data_dir, date, exercise_calc):
    # type: (str, str, str) -> float
    """Net exercise kcal for the day via exercise-calc.py load.

    exercise-calc.py writes `total_calories` from each entry's `calories` field;
    per the exercise-tracker contract that stored value is already NET, so the
    day total IS the net burn. Returns 0.0 when there's no data (a rest day is a
    legitimate zero, NOT missing data)."""
    out = _run_json(["python3", exercise_calc, "load",
                     "--data-dir", data_dir, "--date", date])
    if not out or not isinstance(out, list):
        return 0.0
    total = 0.0
    for day in out:
        if isinstance(day, dict) and day.get("date") == date:
            total += float(day.get("total_calories", 0) or 0)
    return round(total, 1)


def load_intake(data_dir, date, nutrition_calc):
    # type: (str, str, str) -> float
    """Sum meals[].calories for the day via nutrition-calc.py load.

    nutrition-calc stores meals at {data_dir}/meals/{date}.json, so it is
    invoked with --data-dir {data_dir}/meals. Returns 0.0 on no data."""
    meals_dir = os.path.join(data_dir, "meals")
    out = _run_json(["python3", nutrition_calc, "load",
                     "--data-dir", meals_dir, "--date", date])
    if not out or not isinstance(out, dict):
        return 0.0
    total = 0.0
    for m in out.get("meals", []):
        if isinstance(m, dict):
            total += float(m.get("calories", 0) or 0)
    return round(total, 1)


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------

def _classify(balance):
    # type: (float) -> str
    if balance > MAINTENANCE_BAND:
        return "deficit"
    if balance < -MAINTENANCE_BAND:
        return "surplus"
    return "maintenance"


def resolve(data_dir, date, exercise_calc, nutrition_calc):
    # type: (str, str, str, str) -> dict
    """Compute the unified daily energy balance. Never raises."""
    data_dir = _normalize_path(data_dir)
    plan = load_plan(data_dir)
    notes = []

    tdee_base = plan.get("tdee_base")
    eating_target = plan.get("daily_calorie_target")

    # Intake + exercise are always resolvable (absence = 0, a real value).
    exercise_burn_net = load_exercise_burn_net(data_dir, date, exercise_calc)
    intake = load_intake(data_dir, date, nutrition_calc)

    data_complete = tdee_base is not None

    if not data_complete:
        # Fail open: no machine-readable plan yet (pre-plan.json agents, or
        # onboarding not finished). Report what we can; callers skip the line.
        notes.append(
            "plan.json missing or has no tdee_base — net daily balance "
            "unavailable (run weight-loss-planner write-plan-json)."
        )
        return {
            "date": date,
            "tdee_base": None,
            "exercise_burn_net": exercise_burn_net,
            "expenditure": None,
            "intake": intake,
            "balance": None,
            "verdict": "unknown",
            "eating_target": eating_target,
            "intake_vs_target": (round(eating_target - intake, 1)
                                 if eating_target is not None else None),
            "data_complete": False,
            "notes": notes,
        }

    tdee_base = float(tdee_base)
    expenditure = round(tdee_base + exercise_burn_net, 1)
    balance = round(expenditure - intake, 1)
    verdict = _classify(balance)

    # Q2 = "net deficit, fixed target": eating_target is reported verbatim from
    # the plan and NEVER adjusted by exercise. intake_vs_target is the classic
    # meal-checkpoint number (independent of the workout).
    intake_vs_target = None
    if eating_target is not None:
        intake_vs_target = round(float(eating_target) - intake, 1)
    else:
        notes.append("plan.json has tdee_base but no daily_calorie_target — "
                     "intake_vs_target unavailable.")

    if intake == 0:
        notes.append("no meals logged yet today — intake is 0.")

    return {
        "date": date,
        "tdee_base": int(tdee_base),
        "exercise_burn_net": exercise_burn_net,
        "expenditure": expenditure,
        "intake": intake,
        "balance": balance,
        "verdict": verdict,
        "eating_target": (int(eating_target) if eating_target is not None else None),
        "intake_vs_target": intake_vs_target,
        "data_complete": True,
        "notes": notes,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Unified daily energy-balance resolver (derive, don't store)")
    parser.add_argument("--data-dir", required=True,
                        help="Workspace data/ directory (contains plan.json, "
                             "exercise.json, meals/)")
    parser.add_argument("--date", default=None,
                        help="Date YYYY-MM-DD (default: today, local via --tz-offset)")
    parser.add_argument("--tz-offset", type=int, default=None,
                        help="Timezone offset seconds — used only to resolve "
                             "'today' when --date is omitted")
    parser.add_argument("--exercise-calc", default=None,
                        help="Path to exercise-calc.py (default: sibling script)")
    parser.add_argument("--nutrition-calc", default=None,
                        help="Path to nutrition-calc.py (default: diet-tracking-analysis)")

    args = parser.parse_args()

    date = args.date or _local_date(args.tz_offset)

    exercise_calc = _find_script(
        args.exercise_calc, "exercise-calc.py",
        ".",                                              # same scripts/ dir
        "../../exercise-tracking-planning/scripts",       # skills-root layout
    )
    nutrition_calc = _find_script(
        args.nutrition_calc, "nutrition-calc.py",
        "../../diet-tracking-analysis/scripts",           # sibling skill
    )

    result = resolve(args.data_dir, date, exercise_calc, nutrition_calc)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
