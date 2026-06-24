#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
Periodic recalculation script for weight loss plans.

Every 4 weeks, recalculates the user's daily calorie target based on
current weight. Outputs new TDEE/calories/macros for the LLM to write back to PLAN.md.

Usage:
  python3 periodic-recalc.py \
    --workspace /path/to/workspace \
    --planner-calc /path/to/planner-calc.py \
    --current-calories 1300 \
    --target-weight 50 \
    --tdee 1769 \
    --activity lightly_active \
    --diet-mode balanced \
    --height 160 \
    --age 30 \
    --sex female \
    --cycle-start-date 2026-05-27 \
    [--weekly-rate 0.4] \
    [--bmi-standard asian] \
    [--dry-run]
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, date
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


def get_second_weight(weight_json_path: Path) -> float | None:
    """
    Get the second most recent weight value from weight.json (for previous_weight).
    Returns weight_kg or None if fewer than two entries.
    """
    data = read_json(weight_json_path)
    if not data:
        return None

    entries = []
    for timestamp_str, entry in data.items():
        try:
            dt = datetime.fromisoformat(timestamp_str)
            entries.append((dt, entry['value'], entry['unit']))
        except (ValueError, KeyError):
            continue

    if len(entries) < 2:
        return None

    entries.sort(key=lambda x: x[0], reverse=True)
    second = entries[1]

    weight = second[1]
    if second[2] == 'lbs':
        weight = weight / 2.205

    return weight


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


def run_planner_calc(planner_calc_path: Path, args: list[str]) -> dict:
    """Run planner-calc.py and return parsed JSON output."""
    cmd = ['python3', str(planner_calc_path)] + args
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(f"planner-calc.py failed: {result.stderr}")

    return json.loads(result.stdout)


def main():
    parser = argparse.ArgumentParser(description='Periodic recalculation of weight loss plan')
    parser.add_argument('--workspace', type=Path, required=True,
                        help='Path to user workspace directory')
    parser.add_argument('--planner-calc', type=Path, required=True,
                        help='Path to planner-calc.py script')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would change without writing files')
    parser.add_argument('--current-calories', type=int, required=True,
                        help='Current daily calorie target')
    parser.add_argument('--target-weight', type=float, required=True,
                        help='Target weight in kg')
    parser.add_argument('--tdee', type=int, required=True,
                        help='Current TDEE estimate')
    parser.add_argument('--activity', type=str, required=True,
                        choices=['sedentary', 'lightly_active', 'moderately_active', 'very_active'],
                        help='Activity level')
    parser.add_argument('--diet-mode', type=str, required=True,
                        choices=['balanced', 'high_protein', 'low_carb', 'keto', 'mediterranean',
                                 'plant_based', 'usda', 'if_16_8', 'if_5_2'],
                        help='Diet mode')
    parser.add_argument('--height', type=float, required=True,
                        help='Height in cm')
    parser.add_argument('--age', type=int, required=True,
                        help='Age in years')
    parser.add_argument('--sex', type=str, required=True,
                        choices=['male', 'female'],
                        help='Sex')
    parser.add_argument('--cycle-start-date', type=str, required=True,
                        help='ISO date when current cycle started (YYYY-MM-DD)')
    parser.add_argument('--bmi-standard', type=str, default='asian',
                        choices=['asian', 'who'],
                        help='BMI standard (default: asian)')
    parser.add_argument('--weekly-rate', type=float, default=None,
                        help='Old cycle weekly rate in kg/week (optional)')
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

    # Step 0: Check if it's too soon since last recalc (< 25 days)
    # Source of truth: data/last-recalc-summary.json (script-written, schema-stable)
    # Skip this check if triggered by pending-recalc (secondary trigger)
    last_recalc_path = workspace / 'data' / 'last-recalc-summary.json'

    if pending_json.exists():
        read_json(pending_json)
        # Secondary trigger — always proceed
    else:
        if last_recalc_path.exists():
            last_recalc_data = read_json(last_recalc_path)
            last_date_str = last_recalc_data.get('date')
            if last_date_str:
                try:
                    last_date = date.fromisoformat(last_date_str)
                    days_since = (date.today() - last_date).days
                    if days_since < 25:
                        print(json.dumps({
                            "action": "skipped",
                            "reason": f"Only {days_since} days since last recalc (need >= 25)",
                            "days_since_last": days_since
                        }))
                        return
                except (ValueError, TypeError):
                    # Corrupt date in last-recalc-summary — treat as never recalc, proceed
                    pass
        # No last-recalc-summary or no/invalid date → proceed (first-time or stale)

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

    # Step 4: Get previous weight from weight.json (second most recent entry)
    previous_weight_raw = get_second_weight(weight_json)
    previous_weight = previous_weight_raw if previous_weight_raw is not None else current_weight
    weight_change = round(current_weight - previous_weight, 1)

    old_calories = args.current_calories
    old_tdee = args.tdee

    # Step 5: Call planner-calc.py forward-calc with new weight
    calc_args = [
        'forward-calc',
        '--weight', str(current_weight),
        '--height', str(args.height),
        '--age', str(args.age),
        '--sex', args.sex,
        '--activity', args.activity,
        '--target-weight', str(args.target_weight),
        '--mode', args.diet_mode,
        '--bmi-standard', args.bmi_standard,
    ]

    try:
        new_calc = run_planner_calc(planner_calc, calc_args)
    except RuntimeError as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)

    # Step 6: Extract new values
    new_calories = new_calc['daily_cal']
    new_tdee = new_calc['tdee']['tdee']
    macros = new_calc['macros']

    if not args.dry_run:
        # Archive current cycle to plan-history.json before LLM rewrites PLAN.md
        history_path = workspace / 'data' / 'plan-history.json'
        history = []
        if history_path.exists():
            try:
                with open(history_path, 'r', encoding='utf-8') as f:
                    history = json.load(f)
            except (json.JSONDecodeError, IOError):
                history = []

        cycle_number = len(history) + 1
        old_macros = calc_macros(previous_weight, old_calories, args.diet_mode, target_weight=args.target_weight)
        history.append({
            "cycle": cycle_number,
            "start_date": args.cycle_start_date,
            "end_date": date.today().isoformat(),
            "weight_start": previous_weight,
            "weight_end": current_weight,
            "calories": old_calories,
            "tdee": old_tdee,
            "rate": args.weekly_rate,
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

        # Write minimal last-recalc-summary as floor — LLM may overwrite with richer fields later
        # Read existing if present, preserve LLM-written fields
        existing = read_json(last_recalc_path) if last_recalc_path.exists() else {}
        existing.update({
            "date": date.today().isoformat(),
            "weight_from": previous_weight,
            "weight_to": current_weight,
            "old_calories": old_calories,
            "new_calories": new_calories,
        })
        write_json(last_recalc_path, existing)

        # Delete pending-recalc.json if it exists
        delete_file(pending_json)

    # Step 7: Output results for LLM to rewrite PLAN.md and compose message
    output = {
        "action": "recalculated",
        "old_calories": old_calories,
        "new_calories": new_calories,
        "old_tdee": old_tdee,
        "new_tdee": new_tdee,
        "old_rate": args.weekly_rate,
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
