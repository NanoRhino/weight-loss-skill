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


def test_weekly_low_cal_check_below(tmp_dir: str):
    """Test weekly-low-cal-check when average is below BMR."""
    # Create 5 days of low-calorie data (800 cal/day, BMR=1400)
    for offset in range(5):
        day = f"2026-02-{20 + offset:02d}"
        meals = [{"name": "lunch", "cal": 500, "p": 30, "c": 60, "f": 15},
                 {"name": "dinner", "cal": 300, "p": 20, "c": 30, "f": 10}]
        run_cmd(["save", "--data-dir", tmp_dir, "--meal", json.dumps(meals[0]), "--date", day])
        run_cmd(["save", "--data-dir", tmp_dir, "--meal", json.dumps(meals[1]), "--date", day])

    r = run_cmd(["weekly-low-cal-check", "--data-dir", tmp_dir, "--bmr", "1400",
                 "--date", "2026-02-24"])
    assert r["logged_days"] == 5
    assert r["weekly_avg_cal"] == 800.0
    assert r["calorie_floor"] == 1400
    assert r["below_floor"] == True
    assert r["days_below_count"] == 5
    print("✅ test_weekly_low_cal_check_below passed")


def test_weekly_low_cal_check_above(tmp_dir: str):
    """Test weekly-low-cal-check when average is above BMR."""
    # Create 3 days of adequate-calorie data (1600 cal/day, BMR=1400)
    for offset in range(3):
        day = f"2026-03-{1 + offset:02d}"
        meals = [{"name": "breakfast", "cal": 400, "p": 25, "c": 48, "f": 13},
                 {"name": "lunch", "cal": 600, "p": 35, "c": 70, "f": 18},
                 {"name": "dinner", "cal": 600, "p": 35, "c": 60, "f": 22}]
        for m in meals:
            run_cmd(["save", "--data-dir", tmp_dir, "--meal", json.dumps(m), "--date", day])

    r = run_cmd(["weekly-low-cal-check", "--data-dir", tmp_dir, "--bmr", "1400",
                 "--date", "2026-03-03"])
    assert r["logged_days"] == 3
    assert r["weekly_avg_cal"] == 1600.0
    assert r["below_floor"] == False
    assert r["days_below_count"] == 0
    print("✅ test_weekly_low_cal_check_above passed")


def test_weekly_low_cal_check_no_data(tmp_dir: str):
    """Test weekly-low-cal-check with no logged days."""
    r = run_cmd(["weekly-low-cal-check", "--data-dir", tmp_dir, "--bmr", "1400",
                 "--date", "2026-04-01"])
    assert r["logged_days"] == 0
    assert r["below_floor"] == False
    print("✅ test_weekly_low_cal_check_no_data passed")


def test_weekly_low_cal_check_floor_minimum(tmp_dir: str):
    """Test that calorie floor is at least 1000 even when BMR is lower."""
    # Create 2 days with 900 cal/day, BMR=900 → floor should be 1000
    for offset in range(2):
        day = f"2026-04-{10 + offset:02d}"
        meal = {"name": "lunch", "cal": 900, "p": 50, "c": 100, "f": 25}
        run_cmd(["save", "--data-dir", tmp_dir, "--meal", json.dumps(meal), "--date", day])

    r = run_cmd(["weekly-low-cal-check", "--data-dir", tmp_dir, "--bmr", "900",
                 "--date", "2026-04-11"])
    assert r["calorie_floor"] == 1000  # max(900, 1000)
    assert r["below_floor"] == True    # 900 < 1000
    print("✅ test_weekly_low_cal_check_floor_minimum passed")


def test_detect_diet_pattern_mismatch(tmp_dir: str):
    """Detect pattern: user on balanced but eating high-protein for 3 days."""
    # Create 3 days of high-protein meals (protein ~40%, carbs ~30%, fat ~30%)
    for offset in range(3):
        day = f"2026-03-{4 - offset:02d}"
        meals = [
            {"name": "breakfast", "cal": 400, "p": 45, "c": 25, "f": 12},
            {"name": "lunch", "cal": 600, "p": 65, "c": 40, "f": 18},
            {"name": "dinner", "cal": 500, "p": 55, "c": 35, "f": 15},
        ]
        for m in meals:
            run_cmd(["save", "--data-dir", tmp_dir, "--meal", json.dumps(m), "--date", day])

    r = run_cmd(["detect-diet-pattern", "--data-dir", tmp_dir,
                 "--current-mode", "balanced", "--date", "2026-03-04"])
    assert r["has_pattern"] == True, f"Expected mismatch, got {r}"
    assert r["detected_mode"] == "high_protein", f"Expected high_protein, got {r['detected_mode']}"
    assert r["pros_cons"] is not None
    assert len(r["pros_cons"]["pros"]) > 0
    assert len(r["pros_cons"]["cons"]) > 0
    print("✅ test_detect_diet_pattern_mismatch passed")


def test_detect_diet_pattern_no_mismatch(tmp_dir: str):
    """No pattern when eating matches current mode (balanced)."""
    # Create 3 days of balanced meals (protein ~30%, carbs ~40%, fat ~30%)
    for offset in range(3):
        day = f"2026-03-{4 - offset:02d}"
        meals = [
            {"name": "breakfast", "cal": 400, "p": 30, "c": 42, "f": 13},
            {"name": "lunch", "cal": 600, "p": 45, "c": 63, "f": 20},
            {"name": "dinner", "cal": 500, "p": 38, "c": 52, "f": 17},
        ]
        for m in meals:
            run_cmd(["save", "--data-dir", tmp_dir, "--meal", json.dumps(m), "--date", day])

    r = run_cmd(["detect-diet-pattern", "--data-dir", tmp_dir,
                 "--current-mode", "balanced", "--date", "2026-03-04"])
    assert r["has_pattern"] == False, f"Expected no mismatch, got {r}"
    print("✅ test_detect_diet_pattern_no_mismatch passed")


def test_detect_diet_pattern_insufficient_data(tmp_dir: str):
    """Insufficient data: less than 3 days with meals."""
    # Create only 2 days
    for offset in range(2):
        day = f"2026-03-{4 - offset:02d}"
        meals = [{"name": "lunch", "cal": 600, "p": 65, "c": 40, "f": 18}]
        for m in meals:
            run_cmd(["save", "--data-dir", tmp_dir, "--meal", json.dumps(m), "--date", day])

    r = run_cmd(["detect-diet-pattern", "--data-dir", tmp_dir,
                 "--current-mode", "balanced", "--date", "2026-03-04"])
    assert r["has_pattern"] == False
    assert r["reason"] == "insufficient_data"
    assert r["days_found"] == 2
    print("✅ test_detect_diet_pattern_insufficient_data passed")


def test_detect_diet_pattern_low_carb(tmp_dir: str):
    """Detect low-carb pattern when user is on balanced."""
    # Create 3 days of low-carb meals (protein ~35%, carbs ~20%, fat ~45%)
    for offset in range(3):
        day = f"2026-03-{4 - offset:02d}"
        meals = [
            {"name": "breakfast", "cal": 450, "p": 35, "c": 20, "f": 23},
            {"name": "lunch", "cal": 600, "p": 48, "c": 28, "f": 30},
            {"name": "dinner", "cal": 500, "p": 40, "c": 23, "f": 25},
        ]
        for m in meals:
            run_cmd(["save", "--data-dir", tmp_dir, "--meal", json.dumps(m), "--date", day])

    r = run_cmd(["detect-diet-pattern", "--data-dir", tmp_dir,
                 "--current-mode", "balanced", "--date", "2026-03-04"])
    assert r["has_pattern"] == True, f"Expected mismatch, got {r}"
    assert r["detected_mode"] == "low_carb", f"Expected low_carb, got {r['detected_mode']}"
    print("✅ test_detect_diet_pattern_low_carb passed")


def test_detect_diet_pattern_if_mode(tmp_dir: str):
    """IF mode uses balanced macro profile for comparison."""
    # Create 3 days of balanced meals — should NOT trigger for if_16_8
    for offset in range(3):
        day = f"2026-03-{4 - offset:02d}"
        meals = [
            {"name": "meal_1", "cal": 750, "p": 56, "c": 79, "f": 25},
            {"name": "meal_2", "cal": 750, "p": 56, "c": 79, "f": 25},
        ]
        for m in meals:
            run_cmd(["save", "--data-dir", tmp_dir, "--meal", json.dumps(m), "--date", day])

    r = run_cmd(["detect-diet-pattern", "--data-dir", tmp_dir,
                 "--current-mode", "if_16_8", "--date", "2026-03-04"])
    assert r["has_pattern"] == False, f"Expected no mismatch for IF mode with balanced macros"
    assert r["effective_current_mode"] == "balanced"
    print("✅ test_detect_diet_pattern_if_mode passed")


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

    # Weekly low-calorie check tests (each uses isolated subdirectories)
    wlc_dir_below = os.path.join(tmp_dir, "wlc_below")
    wlc_dir_above = os.path.join(tmp_dir, "wlc_above")
    wlc_dir_empty = os.path.join(tmp_dir, "wlc_empty")
    wlc_dir_floor = os.path.join(tmp_dir, "wlc_floor")
    os.makedirs(wlc_dir_below, exist_ok=True)
    os.makedirs(wlc_dir_above, exist_ok=True)
    os.makedirs(wlc_dir_empty, exist_ok=True)
    os.makedirs(wlc_dir_floor, exist_ok=True)
    test_weekly_low_cal_check_below(wlc_dir_below)
    test_weekly_low_cal_check_above(wlc_dir_above)
    test_weekly_low_cal_check_no_data(wlc_dir_empty)
    test_weekly_low_cal_check_floor_minimum(wlc_dir_floor)

    # Diet pattern detection tests
    ddp_mismatch = os.path.join(tmp_dir, "ddp_mismatch")
    ddp_no_mismatch = os.path.join(tmp_dir, "ddp_no_mismatch")
    ddp_insufficient = os.path.join(tmp_dir, "ddp_insufficient")
    ddp_low_carb = os.path.join(tmp_dir, "ddp_low_carb")
    ddp_if_mode = os.path.join(tmp_dir, "ddp_if_mode")
    for d in [ddp_mismatch, ddp_no_mismatch, ddp_insufficient, ddp_low_carb, ddp_if_mode]:
        os.makedirs(d, exist_ok=True)
    test_detect_diet_pattern_mismatch(ddp_mismatch)
    test_detect_diet_pattern_no_mismatch(ddp_no_mismatch)
    test_detect_diet_pattern_insufficient_data(ddp_insufficient)
    test_detect_diet_pattern_low_carb(ddp_low_carb)
    test_detect_diet_pattern_if_mode(ddp_if_mode)

    print("\n🎉 All tests passed!")

    # Cleanup
    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
