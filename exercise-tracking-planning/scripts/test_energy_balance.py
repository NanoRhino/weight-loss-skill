#!/usr/bin/env python3
# /// script
# requires-python = ">=3.6"
# dependencies = []
# ///
"""Self-tests for energy-balance.py (the unified daily energy-balance resolver).

No test framework repo-wide — run directly on bare python3:
    python3 test_energy_balance.py

Builds throwaway fixture workspaces in a tempdir and asserts:
  - balance / verdict math (deficit / maintenance / surplus)
  - eating_target is NEVER changed by exercise  (locked Q2 = "net deficit,
    fixed target")
  - fail-open when plan.json / tdee_base is missing
  - a rest day (no exercise) is a real 0 burn, not missing data
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))

# Load the hyphenated module by path.
_spec = importlib.util.spec_from_file_location(
    "energy_balance", os.path.join(_HERE, "energy-balance.py"))
eb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(eb)

EXERCISE_CALC = os.path.join(_HERE, "exercise-calc.py")
NUTRITION_CALC = os.path.normpath(
    os.path.join(_HERE, "..", "..", "diet-tracking-analysis", "scripts", "nutrition-calc.py"))

DATE = "2026-07-01"

_passed = 0
_failed = 0


def check(name, cond, detail=""):
    global _passed, _failed
    if cond:
        _passed += 1
        print("  PASS: {}".format(name))
    else:
        _failed += 1
        print("  FAIL: {} {}".format(name, detail))


def build_ws(tmp, plan=None, exercise=None, meals=None):
    """Create a fixture workspace data/ dir. Returns the data dir path."""
    data = os.path.join(tmp, "data")
    os.makedirs(os.path.join(data, "meals"), exist_ok=True)
    if plan is not None:
        with open(os.path.join(data, "plan.json"), "w", encoding="utf-8") as f:
            json.dump(plan, f)
    if exercise is not None:
        with open(os.path.join(data, "exercise.json"), "w", encoding="utf-8") as f:
            json.dump(exercise, f)
    if meals is not None:
        with open(os.path.join(data, "meals", DATE + ".json"), "w", encoding="utf-8") as f:
            json.dump(meals, f)
    return data


def run(data_dir):
    return eb.resolve(data_dir, DATE, EXERCISE_CALC, NUTRITION_CALC)


PLAN = {
    "tdee_base": 1850, "bmr": 1344, "activity_level": "lightly_active",
    "activity_multiplier": 1.375, "daily_calorie_target": 1404,
    "daily_deficit": 446, "goal": "lose_fat", "weekly_rate_kg": 0.4,
    "updated_at": "2026-07-01T00:00:00Z", "source": "planner-calc",
}
EX_300 = {DATE: {"exercises": [{"activity": "running", "category": "cardio",
                               "duration_min": 45, "calories": 300}],
                 "total_calories": 300}}
MEALS_1200 = [
    {"name": "breakfast", "calories": 400, "protein": 30, "carbs": 40, "fat": 12},
    {"name": "lunch", "calories": 800, "protein": 50, "carbs": 70, "fat": 25},
]


def test_full_deficit(tmp):
    print("test_full_deficit (exercise credited, deficit):")
    d = build_ws(tmp, plan=PLAN, exercise=EX_300, meals=MEALS_1200)
    r = run(d)
    check("data_complete", r["data_complete"] is True)
    check("tdee_base", r["tdee_base"] == 1850, r)
    check("exercise_burn_net==300", r["exercise_burn_net"] == 300.0, r)
    check("expenditure==2150", r["expenditure"] == 2150.0, r)
    check("intake==1200", r["intake"] == 1200.0, r)
    check("balance==950", r["balance"] == 950.0, r)
    check("verdict==deficit", r["verdict"] == "deficit", r)
    # THE load-bearing assertion: fixed target.
    check("eating_target UNCHANGED (1404)", r["eating_target"] == 1404, r)
    check("intake_vs_target==204 (target-intake)", r["intake_vs_target"] == 204.0, r)


def test_target_never_moves_with_exercise(tmp):
    """Same intake/plan; add a big workout. Target must NOT change; only the
    net balance improves."""
    print("test_target_never_moves_with_exercise (Q2=C):")
    d_rest = build_ws(os.path.join(tmp, "rest"), plan=PLAN, meals=MEALS_1200)
    r_rest = run(d_rest)
    d_work = build_ws(os.path.join(tmp, "work"),
                      plan=PLAN,
                      exercise={DATE: {"exercises": [], "total_calories": 500}},
                      meals=MEALS_1200)
    r_work = run(d_work)
    check("target same rest vs work",
          r_rest["eating_target"] == r_work["eating_target"] == 1404,
          (r_rest["eating_target"], r_work["eating_target"]))
    check("intake_vs_target same rest vs work",
          r_rest["intake_vs_target"] == r_work["intake_vs_target"] == 204.0,
          (r_rest["intake_vs_target"], r_work["intake_vs_target"]))
    check("net balance improves by exactly the burn",
          r_work["balance"] - r_rest["balance"] == 500.0,
          (r_rest["balance"], r_work["balance"]))


def test_surplus(tmp):
    print("test_surplus (over expenditure):")
    d = build_ws(tmp, plan=PLAN,
                 meals=[{"name": "feast", "calories": 2500, "protein": 80,
                         "carbs": 250, "fat": 100}])
    r = run(d)
    check("balance==-650", r["balance"] == -650.0, r)
    check("verdict==surplus", r["verdict"] == "surplus", r)
    check("eating_target UNCHANGED", r["eating_target"] == 1404, r)


def test_maintenance_band(tmp):
    print("test_maintenance_band (within +/-100):")
    # intake == expenditure - 50 → balance +50 → maintenance
    d = build_ws(tmp, plan=PLAN,
                 meals=[{"name": "d", "calories": 1800, "protein": 1, "carbs": 1, "fat": 1}])
    r = run(d)
    check("balance==50", r["balance"] == 50.0, r)
    check("verdict==maintenance", r["verdict"] == "maintenance", r)


def test_failopen_no_plan(tmp):
    print("test_failopen_no_plan (plan.json missing):")
    d = build_ws(tmp, exercise=EX_300, meals=MEALS_1200)  # no plan
    r = run(d)
    check("data_complete False", r["data_complete"] is False, r)
    check("tdee_base None", r["tdee_base"] is None, r)
    check("verdict unknown", r["verdict"] == "unknown", r)
    check("balance None", r["balance"] is None, r)
    check("still reports intake", r["intake"] == 1200.0, r)
    check("still reports burn", r["exercise_burn_net"] == 300.0, r)
    check("has degraded note", len(r["notes"]) >= 1, r)


def test_failopen_no_tdee_base(tmp):
    print("test_failopen_no_tdee_base (plan.json without tdee_base):")
    d = build_ws(tmp, plan={"daily_calorie_target": 1404}, meals=MEALS_1200)
    r = run(d)
    check("data_complete False", r["data_complete"] is False, r)
    # eating_target still surfaced from the partial plan
    check("eating_target surfaced", r["eating_target"] == 1404, r)


def test_rest_day_is_zero(tmp):
    print("test_rest_day_is_zero (no exercise.json → 0 burn, complete):")
    d = build_ws(tmp, plan=PLAN, meals=MEALS_1200)
    r = run(d)
    check("burn 0", r["exercise_burn_net"] == 0.0, r)
    check("data_complete True", r["data_complete"] is True, r)
    check("balance==650", r["balance"] == 650.0, r)


def main():
    tmp_root = tempfile.mkdtemp(prefix="eb_test_")
    tests = [
        test_full_deficit, test_target_never_moves_with_exercise, test_surplus,
        test_maintenance_band, test_failopen_no_plan, test_failopen_no_tdee_base,
        test_rest_day_is_zero,
    ]
    try:
        for i, t in enumerate(tests):
            t(os.path.join(tmp_root, "t{}".format(i)))
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    print("\n{} passed, {} failed".format(_passed, _failed))
    raise SystemExit(1 if _failed else 0)


if __name__ == "__main__":
    main()
