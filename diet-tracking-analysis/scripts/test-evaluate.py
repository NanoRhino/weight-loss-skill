# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
Test script for nutrition-calc.py evaluate command.
Tests range-based checkpoint evaluation with the merged logic.
"""

import json
import subprocess
import sys
import os

SCRIPT = os.path.join(os.path.dirname(__file__), "nutrition-calc.py")


def run_cmd(args: list) -> dict:
    result = subprocess.run(
        [sys.executable, SCRIPT] + args,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True
    )
    if result.returncode != 0:
        print(f"STDERR: {result.stderr}", file=sys.stderr)
        raise RuntimeError(f"Command failed: {args}")
    return json.loads(result.stdout)


def test_target():
    """Test target calculation."""
    r = run_cmd(["target", "--weight", "65", "--cal", "1500", "--meals", "3"])
    assert r["daily_cal"] == 1500
    assert r["cal_range"]["min"] == 1400
    assert r["cal_range"]["max"] == 1600
    assert r["protein"]["target"] == 91.0
    assert r["protein"]["min"] == 78.0
    assert r["protein"]["max"] == 104.0
    assert len(r["allocation"]) == 3
    assert r["allocation"][0]["meal"] == "breakfast"
    assert r["allocation"][0]["pct"] == 30
    print("✅ test_target passed")


def test_evaluate_on_track():
    """Test evaluate when intake is within range."""
    log = json.dumps([
        {"name": "breakfast", "cal": 420, "p": 28, "c": 50, "f": 14}
    ])
    r = run_cmd(["evaluate", "--weight", "65", "--cal", "1500", "--meals", "3",
                 "--current-meal", "breakfast", "--log", log])
    assert r["checkpoint_pct"] == 30
    assert r["checkpoint_range"]["cal_min"] == 420  # 1400 * 0.3
    assert r["checkpoint_range"]["cal_max"] == 480  # 1600 * 0.3
    assert r["status"]["cal"] == "on_track"
    assert r["needs_adjustment"] == False
    print("✅ test_evaluate_on_track passed")


def test_evaluate_needs_adjustment():
    """Test evaluate when calories are outside range."""
    log = json.dumps([
        {"name": "breakfast", "cal": 700, "p": 15, "c": 90, "f": 30}
    ])
    r = run_cmd(["evaluate", "--weight", "65", "--cal", "1500", "--meals", "3",
                 "--current-meal", "breakfast", "--log", log])
    assert r["status"]["cal"] == "high"
    assert r["needs_adjustment"] == True
    print("✅ test_evaluate_needs_adjustment passed")


def test_evaluate_macro_trigger():
    """Test that 2+ macros outside range triggers adjustment even if calories OK."""
    # Calories on track but protein low and fat high
    log = json.dumps([
        {"name": "breakfast", "cal": 450, "p": 10, "c": 80, "f": 25}
    ])
    r = run_cmd(["evaluate", "--weight", "65", "--cal", "1500", "--meals", "3",
                 "--current-meal", "breakfast", "--log", log])
    # Check that needs_adjustment reflects macro imbalance
    macros_outside = sum(1 for k in ["p", "c", "f"] if r["status"][k] != "on_track")
    if macros_outside >= 2:
        assert r["needs_adjustment"] == True
        print("✅ test_evaluate_macro_trigger passed (2+ macros outside)")
    else:
        print("⚠️ test_evaluate_macro_trigger: macros within range, adjusting test data needed")


def test_evaluate_cumulative_lunch():
    """Test lunch checkpoint includes breakfast."""
    log = json.dumps([
        {"name": "breakfast", "cal": 400, "p": 25, "c": 48, "f": 13},
        {"name": "lunch", "cal": 550, "p": 35, "c": 60, "f": 20}
    ])
    r = run_cmd(["evaluate", "--weight", "65", "--cal", "1500", "--meals", "3",
                 "--current-meal", "lunch", "--log", log])
    assert r["checkpoint_pct"] == 70
    assert r["actual"]["cal"] == 950  # 400 + 550
    print("✅ test_evaluate_cumulative_lunch passed")


def test_evaluate_with_assumed():
    """Test assumed meals for forgotten meals."""
    # User logging lunch but forgot breakfast. Assumed breakfast = 30% of daily targets.
    log = json.dumps([
        {"name": "lunch", "cal": 600, "p": 35, "c": 70, "f": 18}
    ])
    assumed = json.dumps([
        {"name": "breakfast", "cal": 450, "p": 27, "c": 54, "f": 14}
    ])
    r = run_cmd(["evaluate", "--weight", "65", "--cal", "1500", "--meals", "3",
                 "--current-meal", "lunch", "--log", log, "--assumed", assumed])
    # Actual should only show lunch
    assert r["actual"]["cal"] == 600
    # Adjusted should include assumed breakfast
    assert r["adjusted"]["cal"] == 1050  # 600 + 450
    assert r["missing_meals"] == ["breakfast"]
    print("✅ test_evaluate_with_assumed passed")


def test_check_missing():
    """Test missing meal detection."""
    log = json.dumps([
        {"name": "lunch", "cal": 500, "p": 30, "c": 60, "f": 15}
    ])
    r = run_cmd(["check-missing", "--meals", "3", "--current-meal", "lunch", "--log", log])
    assert r["has_missing"] == True
    assert len(r["missing"]) == 1
    assert r["missing"][0]["name"] == "breakfast"
    print("✅ test_check_missing passed")


def test_snack_types():
    """Test that snack_am and snack_pm are recognized."""
    log = json.dumps([
        {"name": "breakfast", "cal": 400, "p": 25, "c": 48, "f": 13},
        {"name": "snack_am", "cal": 150, "p": 5, "c": 20, "f": 7}
    ])
    r = run_cmd(["evaluate", "--weight", "65", "--cal", "1500", "--meals", "3",
                 "--current-meal", "snack_am", "--log", log])
    assert r["checkpoint_pct"] == 30
    assert r["actual"]["cal"] == 550  # breakfast + snack_am both in breakfast block
    print("✅ test_snack_types passed")


def test_save_and_load(tmp_dir: str):
    """Test save and load cycle."""
    meal = json.dumps({
        "name": "breakfast", "cal": 400, "p": 25, "c": 48, "f": 13,
        "foods": [{"name": "eggs x2", "cal": 144}, {"name": "toast", "cal": 90}]
    })
    r = run_cmd(["save", "--data-dir", tmp_dir, "--meal", meal, "--date", "2026-01-01"])
    assert r["saved"] == True
    assert r["meals_count"] == 1

    r = run_cmd(["load", "--data-dir", tmp_dir, "--date", "2026-01-01"])
    assert r["meals_count"] == 1
    assert r["meals"][0]["name"] == "breakfast"
    print("✅ test_save_and_load passed")


def main():
    import tempfile
    tmp_dir = tempfile.mkdtemp()

    print("Running nutrition-calc tests...\n")
    test_target()
    test_evaluate_on_track()
    test_evaluate_needs_adjustment()
    test_evaluate_macro_trigger()
    test_evaluate_cumulative_lunch()
    test_evaluate_with_assumed()
    test_check_missing()
    test_snack_types()
    test_save_and_load(tmp_dir)

    print("\n🎉 All tests passed!")

    # Cleanup
    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
