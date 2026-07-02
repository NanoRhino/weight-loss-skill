#!/usr/bin/env python3
"""Combined save + weight context in a single call.

Runs weight-tracker.py save, then returns recent weight history and plan
context so the model can judge whether to intervene.

Usage:
  python3 save-and-check.py \
    --data-dir {workspaceDir}/data \
    --value 75.2 --unit kg \
    --tz-offset 28800 \
    --plan-file {workspaceDir}/PLAN.md \
    --health-profile {workspaceDir}/health-profile.md \
    --user-file {workspaceDir}/USER.md \
    [--correct]
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone


def _normalize_path(p):
    return re.sub(r'(workspace-(?:wechat|wecom)-dm-)([^/]+)', lambda m: m.group(1) + m.group(2).lower(), p)


def run_script(cmd):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return None, result.stderr
        return json.loads(result.stdout), None
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError) as e:
        return None, str(e)


def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_recent_weights(data_dir, tz_offset, limit=14):
    """Return last N weight readings sorted by date."""
    raw = load_json(os.path.join(data_dir, "weight.json"))
    readings = []
    for k, v in sorted(raw.items()):
        val = v.get("value", v) if isinstance(v, dict) else v
        unit = v.get("unit", "kg") if isinstance(v, dict) else "kg"
        readings.append({"date": k[:10], "value": float(val), "unit": unit})
    return readings[-limit:]


# ── Weight-milestone ladder integration (owned by reward-engine) ─────────────

_LB_PER_KG = 2.2046226218


def _norm_unit(u):
    u = (u or "").lower().strip()
    if u in ("kg", "公斤", "千克", "斤", "jin"):
        return "kg"
    if u in ("lb", "lbs", "pound", "pounds", "磅"):
        return "lb"
    return u or "kg"


def _conv(value, from_u, to_u):
    from_u, to_u = _norm_unit(from_u), _norm_unit(to_u)
    if from_u == to_u:
        return round(value, 1)
    if from_u == "kg" and to_u == "lb":
        return round(value * _LB_PER_KG, 1)
    if from_u == "lb" and to_u == "kg":
        return round(value / _LB_PER_KG, 1)
    return round(value, 1)


def _first_last_weights(data_dir):
    """Return (first_reading, last_reading) as {value, unit} dicts, or (None, None)."""
    raw = load_json(os.path.join(data_dir, "weight.json"))
    if not raw:
        return None, None
    keys = sorted(raw.keys())

    def _r(k):
        v = raw[k]
        val = v.get("value", v) if isinstance(v, dict) else v
        unit = v.get("unit", "kg") if isinstance(v, dict) else "kg"
        return {"value": float(val), "unit": unit}
    return _r(keys[0]), _r(keys[-1])


def _parse_unit_pref(health_profile, fallback_unit):
    """Preferred display unit from health-profile.md, else the weight's own unit."""
    if health_profile and os.path.exists(health_profile):
        try:
            content = open(health_profile, encoding="utf-8").read()
            m = re.search(r"Unit Preference[:\s*]*[:：]?\s*\**\s*(kg|公斤|lb|lbs|磅|斤)",
                          content, re.IGNORECASE)
            if m:
                return _norm_unit(m.group(1))
        except OSError:
            pass
    return _norm_unit(fallback_unit)


def _parse_goal_weight(plan_file, health_profile, target_unit):
    """Parse goal/target weight (converted to target_unit) from health-profile.md
    then PLAN.md. Returns float or None."""
    pat = re.compile(
        r"(?:target weight|goal weight|goal|目标体重|目标)[^\d\n]{0,12}?"
        r"(\d+(?:\.\d+)?)\s*(kg|公斤|千克|lb|lbs|磅|斤)?",
        re.IGNORECASE)
    for path in (health_profile, plan_file):
        if not path or not os.path.exists(path):
            continue
        try:
            content = open(path, encoding="utf-8").read()
        except OSError:
            continue
        m = pat.search(content)
        if m:
            val = float(m.group(1))
            unit = m.group(2)
            if _norm_unit(unit or "") == "kg" and (unit or "").strip() in ("斤",):
                val = val * 0.5
            src_unit = _norm_unit(unit) if unit else target_unit
            return _conv(val, src_unit, target_unit)
    return None


def milestone_check(data_dir, tz_offset, plan_file, health_profile):
    """Run reward-engine's weight-milestone-calc.py against the current weigh-in.
    Returns the parsed dict (or None if it can't be computed / script missing)."""
    first, last = _first_last_weights(data_dir)
    if not first or not last:
        return None
    unit = _parse_unit_pref(health_profile, last["unit"])
    start = _conv(first["value"], first["unit"], unit)
    current = _conv(last["value"], last["unit"], unit)
    goal = _parse_goal_weight(plan_file, health_profile, unit)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    skills_root = os.path.dirname(os.path.dirname(script_dir))
    ms_script = os.path.join(skills_root, "reward-engine", "scripts",
                             "weight-milestone-calc.py")
    if not os.path.exists(ms_script):
        return None

    cmd = ["python3", ms_script, "check", "--data-dir", data_dir,
           "--start", str(start), "--current", str(current),
           "--unit", unit, "--tz-offset", str(tz_offset)]
    if goal is not None:
        cmd += ["--goal", str(goal)]
    result, _err = run_script(cmd)
    return result


def get_strategy_status(data_dir, tz_offset):
    """Check if there's an active weight-gain strategy."""
    tz = timezone(timedelta(seconds=tz_offset))
    today = datetime.now(tz).strftime("%Y-%m-%d")
    strat = load_json(os.path.join(data_dir, "weight-gain-strategy.json"))
    active = strat.get("active_strategy", {})
    if active and active.get("status") == "active":
        end = active.get("end_date", "")
        if end >= today:
            result = {"active": True, "type": active.get("type"), "end_date": end}
            if active.get("consensus"):
                result["consensus"] = active["consensus"]
            return result
    return {"active": False}


def get_last_intervention(data_dir):
    """Return the last intervention date from weight-gain-state.json."""
    state = load_json(os.path.join(data_dir, "weight-gain-state.json"))
    return state.get("last_intervention_date")


def save_intervention_date(data_dir, tz_offset):
    """Record that an intervention happened today (called by weight-gain-strategy)."""
    tz = timezone(timedelta(seconds=tz_offset))
    today = datetime.now(tz).strftime("%Y-%m-%d")
    path = os.path.join(data_dir, "weight-gain-state.json")
    state = load_json(path)
    state["last_intervention_date"] = today
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(description="Save weight + context / mark intervention")
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--value", type=float, default=None)
    parser.add_argument("--unit", default=None)
    parser.add_argument("--tz-offset", type=int, default=0)
    parser.add_argument("--correct", action="store_true")
    parser.add_argument("--plan-file", default=None)
    parser.add_argument("--health-profile", default=None)
    parser.add_argument("--user-file", default=None)
    parser.add_argument("--mark-intervention", action="store_true",
                        help="Record today as last intervention date and exit")
    args = parser.parse_args()
    args.data_dir = _normalize_path(args.data_dir)

    # --- Mark intervention mode ---
    if args.mark_intervention:
        save_intervention_date(args.data_dir, args.tz_offset)
        print(json.dumps({"marked": True, "date": datetime.now(
            timezone(timedelta(seconds=args.tz_offset))).strftime("%Y-%m-%d")}))
        return

    if args.value is None or args.unit is None:
        parser.error("--value and --unit are required (unless --mark-intervention)")


    script_dir = os.path.dirname(os.path.abspath(__file__))
    tracker = os.path.join(script_dir, "weight-tracker.py")

    # --- Step 1: Save ---
    save_cmd = [
        "python3", tracker, "save",
        "--data-dir", args.data_dir,
        "--value", str(args.value),
        "--unit", args.unit,
        "--tz-offset", str(args.tz_offset),
    ]
    if args.correct:
        save_cmd.append("--correct")

    save_result, save_err = run_script(save_cmd)
    if not save_result:
        print(json.dumps({
            "save": None,
            "error": f"save failed: {save_err}",
        }, indent=2, ensure_ascii=False))
        sys.exit(1)

    # --- Step 2: Context for model judgment ---
    recent = get_recent_weights(args.data_dir, args.tz_offset)
    strategy = get_strategy_status(args.data_dir, args.tz_offset)
    last_intervention = get_last_intervention(args.data_dir)

    context = {
        "recent_weights": recent,
        "active_strategy": strategy,
        "last_intervention_date": last_intervention,
    }

    # Weight-loss milestone ladder — only on a genuine new weigh-in ("created"),
    # never on a correction ("updated"), mirroring reward-engine's "don't run on
    # corrections" rule. Non-fatal: any failure just omits the key.
    if save_result.get("action") == "created":
        try:
            ms = milestone_check(args.data_dir, args.tz_offset,
                                 args.plan_file, args.health_profile)
            if ms is not None:
                context["milestone"] = ms
        except Exception:
            pass  # never let milestone detection break a weight save

    print(json.dumps({
        "save": save_result,
        "context": context,
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
