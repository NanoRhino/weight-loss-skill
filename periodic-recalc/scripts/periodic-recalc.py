#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
Periodic recalculation script for weight loss plans.

Every 4 weeks, recalculates the user's daily calorie target based on
current weight, updates PLAN.md with new TDEE/calories/macros.

Usage:
  python3 periodic-recalc.py --workspace /path/to/workspace --planner-calc /path/to/planner-calc.py
  python3 periodic-recalc.py --workspace /path/to/workspace --planner-calc /path/to/planner-calc.py --dry-run
"""

# Production EC2 invokes skill scripts as bare `python3` = 3.9; defer annotation
# evaluation so PEP-604 unions (`tuple[...] | None`) don't crash at import on 3.9.
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, date, timedelta, timezone
from pathlib import Path


DIET_MODE_FAT = {
    "usda": (20, 35), "balanced": (20, 35), "high_protein": (20, 35),
    "low_carb": (40, 50), "keto": (65, 75), "mediterranean": (20, 35),
    "plant_based": (20, 30), "if_16_8": (20, 35), "if_5_2": (20, 35),
}

PROTEIN_MODES = {
    "high_protein": (1.4, 1.8, 1.6),
    "balanced": (1.2, 1.6, 1.4),
    "low_carb": (1.2, 1.6, 1.4),
    "keto": (1.2, 1.6, 1.4),
    "mediterranean": (1.2, 1.6, 1.4),
    "plant_based": (1.2, 1.6, 1.4),
    "usda": (1.2, 1.6, 1.4),
    "if_16_8": (1.2, 1.6, 1.4),
    "if_5_2": (1.2, 1.6, 1.4),
}


def calc_macros(weight_kg: float, daily_cal: int, diet_mode: str, target_weight: float = None) -> dict:
    """Calculate macro ranges — aligned with nutrition-calc.js 741ae13."""
    protein_weight = target_weight if target_weight else weight_kg
    p_min_mult, p_max_mult, _ = PROTEIN_MODES.get(diet_mode, (1.2, 1.6, 1.4))

    protein_lo = round(protein_weight * p_min_mult)
    protein_hi = round(protein_weight * p_max_mult)

    fat_lo_pct, fat_hi_pct = DIET_MODE_FAT.get(diet_mode, (20, 35))
    fat_lo = round(daily_cal * fat_lo_pct / 100 / 9)
    fat_hi = round(daily_cal * fat_hi_pct / 100 / 9)

    carb_max = round((daily_cal - protein_lo * 4 - fat_lo * 9) / 4)
    carb_min = round((daily_cal - protein_hi * 4 - fat_hi * 9) / 4)
    if carb_min < 0:
        carb_min = 0

    return {
        "protein_g": [protein_lo, protein_hi],
        "carbs_g": [carb_min, carb_max],
        "fat_g": [fat_lo, fat_hi],
    }


def read_json(path: Path) -> dict:
    """Read and parse JSON file."""
    if not path.exists():
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def write_json(path: Path, data: dict):
    """Write data to JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def delete_file(path: Path):
    """Delete file if it exists."""
    if path.exists():
        path.unlink()


def get_most_recent_weight(weight_json_path: Path) -> tuple[float, str] | None:
    """
    Get the most recent weight entry from weight.json.
    Returns (weight_kg, date_iso) or None if no entries.
    """
    data = read_json(weight_json_path)
    if not data:
        return None

    # Weight.json format: {"2026-05-02T08:00:00+08:00": {"value": 57.9, "unit": "kg"}}
    entries = []
    for timestamp_str, entry in data.items():
        try:
            dt = datetime.fromisoformat(timestamp_str)
            entries.append((dt, entry['value'], entry['unit']))
        except (ValueError, KeyError):
            continue

    if not entries:
        return None

    # Sort by datetime, most recent first
    entries.sort(key=lambda x: x[0], reverse=True)
    most_recent = entries[0]

    # Convert to kg if needed
    weight = most_recent[1]
    unit = most_recent[2]
    if unit == 'lbs':
        weight = weight / 2.205

    return weight, most_recent[0].date().isoformat()


def is_weight_fresh(weight_date_iso: str, max_age_days: int = 14) -> bool:
    """Check if weight is within max_age_days of today."""
    weight_date = date.fromisoformat(weight_date_iso)
    today = date.today()
    return (today - weight_date).days <= max_age_days


def is_on_leave(leave_json_path: Path) -> bool:
    """Check if user is currently on leave."""
    data = read_json(leave_json_path)
    if not data or 'end' not in data:
        return False

    try:
        end_date = date.fromisoformat(data['end'])
        return end_date >= date.today()
    except (ValueError, KeyError):
        return False


def write_pending_recalc(pending_path: Path, reason: str):
    """Write pending-recalc.json flag."""
    data = {
        "created_at": datetime.now().astimezone().isoformat(),
        "reason": reason,
        "cycle_date": date.today().isoformat()
    }
    write_json(pending_path, data)


def parse_plan_md(plan_path: Path) -> dict:
    """
    Parse PLAN.md to extract current values.
    Returns dict with: current_weight, target_weight, daily_calories, tdee, weekly_rate, diet_mode, etc.
    """
    if not plan_path.exists():
        return {}

    content = plan_path.read_text(encoding='utf-8')
    result = {}

    # Extract key-value pairs from Summary section
    patterns = {
        'current_weight': r'\*\*Current Weight:\*\*\s*([0-9.]+)\s*kg',
        'target_weight': r'\*\*Target Weight:\*\*\s*([0-9.]+)\s*kg',
        'daily_calories': r'\*\*Daily Calorie Target:\*\*\s*([0-9,]+)',
        'tdee': r'\*\*TDEE:\*\*\s*([0-9,]+)',
        'weekly_rate': r'\*\*Weekly Rate:\*\*\s*~?([0-9.]+)',
        'diet_mode': r'\*\*Diet Mode:\*\*\s*(\w+)',
        'activity_level': r'\*\*Activity Level:\*\*\s*(\w+)',
        'bmi_standard': r'\*\*BMI Standard:\*\*\s*(\w+)',
    }

    # Extract dates
    for date_key, date_pattern in [
        ('created', r'\*\*Created:\*\*\s*(\d{4}-\d{2}-\d{2})'),
        ('updated', r'\*\*Updated:\*\*\s*(\d{4}-\d{2}-\d{2})'),
    ]:
        match = re.search(date_pattern, content)
        if match:
            result[date_key] = match.group(1)

    for key, pattern in patterns.items():
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            value = match.group(1).replace(',', '')
            # Convert numeric values
            if key in ['current_weight', 'target_weight', 'weekly_rate']:
                result[key] = float(value)
            elif key in ['daily_calories', 'tdee']:
                result[key] = int(value)
            else:
                result[key] = value

    return result


def parse_health_profile(profile_path: Path) -> dict:
    """
    Parse health-profile.md to extract user demographics and preferences.
    Returns dict with: activity_level, diet_mode, bmr, etc.
    """
    if not profile_path.exists():
        return {}

    content = profile_path.read_text(encoding='utf-8')
    result = {}

    patterns = {
        'activity_level': r'\*\*Activity Level:\*\*\s*(\w+)',
        'diet_mode': r'\*\*Diet Mode:\*\*\s*(\w+)',
        'bmr': r'\*\*BMR:\*\*\s*([0-9]+)',
    }

    for key, pattern in patterns.items():
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            value = match.group(1)
            if key == 'bmr':
                result[key] = int(value)
            else:
                result[key] = value

    return result


def run_planner_calc(planner_calc_path: Path, args: list[str]) -> dict:
    """Run planner-calc.py and return parsed JSON output."""
    cmd = ['python3', str(planner_calc_path)] + args
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(f"planner-calc.py failed: {result.stderr}")

    return json.loads(result.stdout)


def update_plan_md(plan_path: Path, old_values: dict, new_values: dict, dry_run: bool = False):
    """
    Update PLAN.md with new calorie target, TDEE, macros, and updated date.
    """
    if not plan_path.exists():
        raise FileNotFoundError(f"PLAN.md not found at {plan_path}")

    content = plan_path.read_text(encoding='utf-8')

    # Update daily calorie target
    content = re.sub(
        r'(\*\*Daily Calorie Target:\*\*\s*)[0-9,]+',
        f'\\g<1>{new_values["daily_cal"]:,}',
        content
    )

    # Update TDEE
    content = re.sub(
        r'(\*\*TDEE:\*\*\s*)[0-9,]+',
        f'\\g<1>{new_values["tdee"]:,}',
        content
    )

    # Update weekly rate if it changed
    if 'rate_kg_per_week' in new_values:
        content = re.sub(
            r'(\*\*Weekly Rate:\*\*\s*~?)[0-9.]+',
            f'\\g<1>{new_values["rate_kg_per_week"]:.2f}',
            content
        )

    # Update current weight
    if 'current_weight' in new_values:
        content = re.sub(
            r'(\*\*Current Weight:\*\*\s*)[0-9.]+',
            f'\\g<1>{new_values["current_weight"]}',
            content
        )

    # Update "Updated" date
    today = date.today().isoformat()
    content = re.sub(
        r'(\*\*Updated:\*\*\s*)[0-9-]+',
        f'\\g<1>{today}',
        content
    )

    if not dry_run:
        plan_path.write_text(content, encoding='utf-8')


def get_previous_weight(plan_md: dict) -> float:
    """Get previous weight from PLAN.md (current_weight field)."""
    return plan_md.get('current_weight', 0.0)


def main():
    parser = argparse.ArgumentParser(description='Periodic recalculation of weight loss plan')
    parser.add_argument('--workspace', type=Path, required=True,
                        help='Path to user workspace directory')
    parser.add_argument('--planner-calc', type=Path, required=True,
                        help='Path to planner-calc.py script')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would change without writing files')
    args = parser.parse_args()

    workspace = args.workspace.resolve()
    planner_calc = args.planner_calc.resolve()

    # Check required files
    if not planner_calc.exists():
        print(json.dumps({"error": "planner-calc.py not found"}), file=sys.stderr)
        sys.exit(1)

    # File paths
    weight_json = workspace / 'data' / 'weight.json'
    leave_json = workspace / 'data' / 'leave.json'
    pending_json = workspace / 'data' / 'pending-recalc.json'
    plan_md = workspace / 'PLAN.md'
    health_profile = workspace / 'health-profile.md'

    # Step 0: Check if it's too soon since last recalc (< 25 days)
    # This allows the cron to fire every Sunday but only execute every ~4 weeks
    # Skip this check if triggered by pending-recalc (secondary trigger)
    if pending_json.exists():
        pending_data = read_json(pending_json)
        # If there's a pending flag, this is a secondary trigger — always proceed
    else:
        # Check PLAN.md "Updated" date
        if plan_md.exists():
            plan_content = plan_md.read_text(encoding='utf-8')
            updated_match = re.search(r'\*\*Updated:\*\*\s*(\d{4}-\d{2}-\d{2})', plan_content)
            if updated_match:
                last_updated = date.fromisoformat(updated_match.group(1))
                days_since = (date.today() - last_updated).days
                if days_since < 25:
                    print(json.dumps({
                        "action": "skipped",
                        "reason": f"Only {days_since} days since last update (need >= 25)",
                        "days_since_last": days_since
                    }))
                    return

    # Step 1: Check if on leave
    if is_on_leave(leave_json):
        if not args.dry_run:
            write_pending_recalc(pending_json, "on_leave")
        print(json.dumps({
            "action": "on_leave",
            "message": "User is on leave. Recalc deferred."
        }))
        return

    # Step 2: Get most recent weight
    weight_info = get_most_recent_weight(weight_json)
    if not weight_info:
        print(json.dumps({
            "error": "No weight entries found in weight.json"
        }), file=sys.stderr)
        sys.exit(1)

    current_weight, weight_date = weight_info

    # Step 3: Check if weight is fresh (within 14 days)
    if not is_weight_fresh(weight_date, max_age_days=14):
        if not args.dry_run:
            write_pending_recalc(pending_json, "awaiting_weight")
        print(json.dumps({
            "action": "awaiting_weight",
            "current_weight": current_weight,
            "weight_date": weight_date,
            "days_old": (date.today() - date.fromisoformat(weight_date)).days,
            "message": "Weight data is stale (>14 days). Awaiting new weight entry."
        }))
        return

    # Step 4: Parse current plan
    plan_data = parse_plan_md(plan_md)
    if not plan_data:
        print(json.dumps({"error": "Could not parse PLAN.md"}), file=sys.stderr)
        sys.exit(1)

    # Get additional params from health-profile.md if not in PLAN.md
    profile_data = parse_health_profile(health_profile)
    activity_level = plan_data.get('activity_level') or profile_data.get('activity_level', 'lightly_active')
    diet_mode = plan_data.get('diet_mode') or profile_data.get('diet_mode', 'balanced')
    bmi_standard = plan_data.get('bmi_standard', 'asian')
    target_weight = plan_data.get('target_weight', current_weight)

    # We need height, age, sex from somewhere - these should be in USER.md or health-profile
    # For now, we'll call planner-calc with weight only and let it use stored profile
    # Actually, we need to read USER.md for these demographics
    user_md = workspace / 'USER.md'
    if not user_md.exists():
        print(json.dumps({"error": "USER.md not found"}), file=sys.stderr)
        sys.exit(1)

    user_content = user_md.read_text(encoding='utf-8')

    # Extract height, age, sex from USER.md
    height_match = re.search(r'\*\*Height:\*\*\s+([0-9.]+)\s*cm', user_content, re.IGNORECASE)
    age_match = re.search(r'\*\*Age:\*\*\s+([0-9]+)', user_content, re.IGNORECASE)
    sex_match = re.search(r'\*\*Sex:\*\*\s+(\w+)', user_content, re.IGNORECASE)

    if not all([height_match, age_match, sex_match]):
        print(json.dumps({"error": "Could not extract demographics from USER.md"}), file=sys.stderr)
        sys.exit(1)

    height_cm = float(height_match.group(1))
    age = int(age_match.group(1))
    sex = sex_match.group(1).lower()

    # Step 5: Call planner-calc.py forward-calc with new weight
    calc_args = [
        'forward-calc',
        '--weight', str(current_weight),
        '--height', str(height_cm),
        '--age', str(age),
        '--sex', sex,
        '--activity', activity_level,
        '--target-weight', str(target_weight),
        '--mode', diet_mode,
        '--bmi-standard', bmi_standard,
    ]

    try:
        new_calc = run_planner_calc(planner_calc, calc_args)
    except RuntimeError as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)

    # Step 6: Extract values
    old_calories = plan_data.get('daily_calories', 0)
    old_tdee = plan_data.get('tdee', 0)
    previous_weight = get_previous_weight(plan_data)

    new_calories = new_calc['daily_cal']
    new_tdee = new_calc['tdee']['tdee']
    weight_change = round(current_weight - previous_weight, 1)

    macros = new_calc['macros']

    # Step 7: Update PLAN.md
    update_values = {
        'daily_cal': new_calories,
        'tdee': new_tdee,
        'rate_kg_per_week': new_calc['rate_kg_per_week'],
        'current_weight': current_weight,
    }

    if not args.dry_run:
        # Step 7a: Archive current cycle to plan-history.json before overwriting
        history_path = Path(args.workspace) / 'data' / 'plan-history.json'
        history = []
        if history_path.exists():
            try:
                with open(history_path, 'r', encoding='utf-8') as f:
                    history = json.load(f)
            except (json.JSONDecodeError, IOError):
                history = []

        cycle_number = len(history) + 1
        old_macros = calc_macros(previous_weight, old_calories, plan_data.get('diet_mode', 'balanced'), target_weight=plan_data.get('target_weight'))
        history.append({
            "cycle": cycle_number,
            "start_date": plan_data.get('updated', plan_data.get('created', '')),
            "end_date": date.today().isoformat(),
            "weight_start": previous_weight,
            "weight_end": current_weight,
            "calories": old_calories,
            "tdee": old_tdee,
            "rate": plan_data.get('weekly_rate', None),
            "macros": old_macros,
            "next_cycle": {
                "calories": new_calories,
                "tdee": new_tdee,
                "rate": new_calc['rate_kg_per_week'],
                "macros": {
                    "protein_g": [round(macros['protein']['min']), round(macros['protein']['max'])],
                    "carbs_g": [round(macros['carb']['min']), round(macros['carb']['max'])],
                    "fat_g": [round(macros['fat']['min']), round(macros['fat']['max'])],
                }
            }
        })

        with open(history_path, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=2, ensure_ascii=False)

        update_plan_md(plan_md, plan_data, update_values, dry_run=False)

        # Step 7b: Keep the canonical machine-readable target store in sync.
        # data/plan.json is owned by weight-loss-planner and read by the
        # energy-balance resolver + weekly-report. Reuse the SAME planner-calc
        # inputs so tdee_base / target match PLAN.md exactly. Best-effort: never
        # fail the recalc if plan.json can't be written.
        try:
            run_planner_calc(planner_calc, [
                'write-plan-json',
                '--data-dir', str(Path(args.workspace) / 'data'),
                '--weight', str(current_weight),
                '--height', str(height_cm),
                '--age', str(age),
                '--sex', sex,
                '--activity', activity_level,
                '--target-weight', str(target_weight),
                '--updated-at', datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                '--source', 'planner-calc',
            ])
        except Exception:
            pass

        # Delete pending-recalc.json if it exists
        delete_file(pending_json)

    # Step 8: Output results
    output = {
        "action": "recalculated",
        "old_calories": old_calories,
        "new_calories": new_calories,
        "old_tdee": old_tdee,
        "new_tdee": new_tdee,
        "old_rate": plan_data.get('weekly_rate', None),
        "new_rate": new_calc['rate_kg_per_week'],
        "current_weight": current_weight,
        "previous_weight": previous_weight,
        "weight_change": weight_change,
        "macros": {
            "protein_g": [round(macros['protein']['min']), round(macros['protein']['max'])],
            "fat_g": [round(macros['fat']['min']), round(macros['fat']['max'])],
            "carbs_g": [round(macros['carb']['min']), round(macros['carb']['max'])],
        },
        "floor_clamped": new_calc.get('floor_clamped', False),
    }

    if args.dry_run:
        output['dry_run'] = True

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
