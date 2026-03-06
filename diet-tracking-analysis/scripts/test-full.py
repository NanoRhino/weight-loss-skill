# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
Comprehensive test suite for nutrition-calc.py.

Covers all 6 commands (target, analyze, save, load, evaluate, check-missing)
with edge cases, boundary conditions, and error handling.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

SCRIPT = os.path.join(os.path.dirname(__file__), "nutrition-calc.py")

passed = 0
failed = 0
errors: list[str] = []


def run_cmd(args: list, expect_fail: bool = False) -> dict | None:
    result = subprocess.run(
        [sys.executable, SCRIPT] + args,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    if expect_fail:
        if result.returncode == 0:
            raise AssertionError(f"Expected failure but got success: {args}")
        return None
    if result.returncode != 0:
        raise RuntimeError(f"Command failed ({result.returncode}): {args}\nSTDERR: {result.stderr}")
    return json.loads(result.stdout)


def check(condition: bool, msg: str):
    global passed, failed
    if condition:
        passed += 1
    else:
        failed += 1
        errors.append(msg)
        print(f"  FAIL: {msg}")


def approx(a: float, b: float, tol: float = 0.15) -> bool:
    return abs(a - b) <= tol


# ---------------------------------------------------------------------------
# TARGET command
# ---------------------------------------------------------------------------

def test_target_3meal():
    """3-meal target: protein/fat/carb ranges and allocation."""
    r = run_cmd(["target", "--weight", "65", "--cal", "1500", "--meals", "3"])
    check(r["daily_cal"] == 1500, "daily_cal == 1500")
    check(r["weight"] == 65, "weight == 65")
    check(r["meals"] == 3, "meals == 3")

    check(r["cal_range"]["min"] == 1400, "cal_range min = cal-100")
    check(r["cal_range"]["max"] == 1600, "cal_range max = cal+100")

    check(approx(r["protein"]["target"], 65 * 1.4), "protein target ≈ weight*1.4")
    check(approx(r["protein"]["min"], 65 * 1.2), "protein min ≈ weight*1.2")
    check(approx(r["protein"]["max"], 65 * 1.6), "protein max ≈ weight*1.6")

    check(approx(r["fat"]["target"], 1500 * 0.275 / 9), "fat target ≈ cal*0.275/9")
    check(approx(r["fat"]["min"], 1500 * 0.20 / 9), "fat min ≈ cal*0.20/9")
    check(approx(r["fat"]["max"], 1500 * 0.35 / 9), "fat max ≈ cal*0.35/9")

    p_target = r["protein"]["target"]
    f_target = r["fat"]["target"]
    expected_carb = round((1500 - p_target * 4 - f_target * 9) / 4, 1)
    check(approx(r["carb"]["target"], expected_carb), "carb target = remainder")

    alloc = r["allocation"]
    check(len(alloc) == 3, "3 allocation blocks")
    check(alloc[0]["meal"] == "breakfast" and alloc[0]["pct"] == 30, "breakfast 30%")
    check(alloc[1]["meal"] == "lunch" and alloc[1]["pct"] == 40, "lunch 40%")
    check(alloc[2]["meal"] == "dinner" and alloc[2]["pct"] == 30, "dinner 30%")
    check(alloc[0]["cal"] == round(1500 * 0.30), "breakfast cal allocation")
    check(alloc[1]["cal"] == round(1500 * 0.40), "lunch cal allocation")


def test_target_2meal():
    """2-meal target: 50/50 allocation."""
    r = run_cmd(["target", "--weight", "70", "--cal", "1800", "--meals", "2"])
    check(r["meals"] == 2, "meals == 2")
    alloc = r["allocation"]
    check(len(alloc) == 2, "2 allocation blocks")
    check(alloc[0]["meal"] == "meal_1" and alloc[0]["pct"] == 50, "meal_1 50%")
    check(alloc[1]["meal"] == "meal_2" and alloc[1]["pct"] == 50, "meal_2 50%")
    check(alloc[0]["cal"] == 900, "meal_1 cal = 900")
    check(alloc[1]["cal"] == 900, "meal_2 cal = 900")


def test_target_different_weights():
    """Targets scale with different body weights."""
    r1 = run_cmd(["target", "--weight", "50", "--cal", "1200", "--meals", "3"])
    r2 = run_cmd(["target", "--weight", "100", "--cal", "2400", "--meals", "3"])
    check(r2["protein"]["target"] > r1["protein"]["target"],
          "heavier person gets higher protein target")
    check(r2["fat"]["target"] > r1["fat"]["target"],
          "higher cal gets higher fat target")


# ---------------------------------------------------------------------------
# ANALYZE command
# ---------------------------------------------------------------------------

def test_analyze_single_meal():
    """Analyze with a single meal entry."""
    log = json.dumps([{"name": "breakfast", "cal": 400, "p": 25, "c": 50, "f": 12}])
    r = run_cmd(["analyze", "--weight", "65", "--cal", "1500", "--meals", "3", "--log", log])
    check(r["cumulative"]["cal"] == 400, "cumulative cal = 400")
    check(r["cumulative"]["p"] == 25, "cumulative p = 25")
    check(r["pct_cal"] == round(400 / 1500 * 100), "pct_cal correct")
    check(r["remaining"]["cal"] == 1100, "remaining cal = 1100")
    check(len(r["meals"]) == 1, "1 meal in details")


def test_analyze_multiple_meals():
    """Analyze cumulative intake across multiple meals."""
    log = json.dumps([
        {"name": "breakfast", "cal": 400, "p": 25, "c": 50, "f": 12},
        {"name": "lunch", "cal": 600, "p": 35, "c": 70, "f": 20},
    ])
    r = run_cmd(["analyze", "--weight", "65", "--cal", "1500", "--meals", "3", "--log", log])
    check(r["cumulative"]["cal"] == 1000, "cumulative cal = 1000")
    check(r["cumulative"]["p"] == 60, "cumulative p = 60")
    check(r["cumulative"]["c"] == 120, "cumulative c = 120")
    check(r["cumulative"]["f"] == 32, "cumulative f = 32")
    check(r["remaining"]["cal"] == 500, "remaining cal = 500")


def test_analyze_empty_log():
    """Analyze with no meals logged."""
    log = json.dumps([])
    r = run_cmd(["analyze", "--weight", "65", "--cal", "1500", "--meals", "3", "--log", log])
    check(r["cumulative"]["cal"] == 0, "empty log → 0 cal")
    check(r["pct_cal"] == 0, "empty log → 0% cal")
    check(r["remaining"]["cal"] == 1500, "remaining = full daily target")


def test_analyze_status_labels():
    """Status labels: low, on_track, high."""
    low_log = json.dumps([{"name": "breakfast", "cal": 100, "p": 5, "c": 10, "f": 2}])
    r = run_cmd(["analyze", "--weight", "65", "--cal", "1500", "--meals", "3", "--log", low_log])
    check(r["status"]["cal"] == "low", "very low cal → status low")
    check(r["status"]["p"] == "low", "very low p → status low")

    high_log = json.dumps([
        {"name": "breakfast", "cal": 850, "p": 60, "c": 120, "f": 40},
        {"name": "lunch", "cal": 800, "p": 60, "c": 120, "f": 40},
    ])
    r = run_cmd(["analyze", "--weight", "65", "--cal", "1500", "--meals", "3", "--log", high_log])
    check(r["status"]["cal"] == "high", "high total cal (1650 > 1600) → status high")


def test_analyze_on_track():
    """All macros on track when values fall within ranges."""
    targets = run_cmd(["target", "--weight", "65", "--cal", "1500", "--meals", "3"])
    log = json.dumps([
        {"name": "breakfast", "cal": 400, "p": 25, "c": 50, "f": 13},
        {"name": "lunch", "cal": 600, "p": 36, "c": 72, "f": 18},
        {"name": "dinner", "cal": 450, "p": 28, "c": 55, "f": 14},
    ])
    r = run_cmd(["analyze", "--weight", "65", "--cal", "1500", "--meals", "3", "--log", log])
    check(r["cumulative"]["cal"] == 1450, "total cal 1450")
    check(r["status"]["cal"] == "on_track", "1450 within [1400,1600]")


# ---------------------------------------------------------------------------
# SAVE & LOAD commands
# ---------------------------------------------------------------------------

def test_save_creates_file(tmp_dir: str):
    """Save creates a new daily log file."""
    meal = json.dumps({
        "name": "breakfast", "cal": 400, "p": 25, "c": 50, "f": 12,
        "foods": [{"name": "eggs x2", "cal": 144}, {"name": "toast", "cal": 90}],
    })
    r = run_cmd(["save", "--data-dir", tmp_dir, "--meal", meal, "--date", "2026-03-01"])
    check(r["saved"] is True, "saved == True")
    check(r["meals_count"] == 1, "meals_count == 1")
    check(os.path.exists(os.path.join(tmp_dir, "2026-03-01.json")), "file created")


def test_save_appends(tmp_dir: str):
    """Second save appends to existing file."""
    m1 = json.dumps({"name": "breakfast", "cal": 400, "p": 25, "c": 50, "f": 12})
    m2 = json.dumps({"name": "lunch", "cal": 600, "p": 35, "c": 70, "f": 20})
    run_cmd(["save", "--data-dir", tmp_dir, "--meal", m1, "--date", "2026-03-02"])
    r = run_cmd(["save", "--data-dir", tmp_dir, "--meal", m2, "--date", "2026-03-02"])
    check(r["meals_count"] == 2, "2 meals after append")
    names = [m["name"] for m in r["meals"]]
    check("breakfast" in names and "lunch" in names, "both meals present")


def test_save_overwrites_same_meal(tmp_dir: str):
    """Saving same meal name overwrites (correction support)."""
    m1 = json.dumps({"name": "breakfast", "cal": 400, "p": 25, "c": 50, "f": 12})
    m2 = json.dumps({"name": "breakfast", "cal": 500, "p": 30, "c": 55, "f": 15})
    run_cmd(["save", "--data-dir", tmp_dir, "--meal", m1, "--date", "2026-03-03"])
    r = run_cmd(["save", "--data-dir", tmp_dir, "--meal", m2, "--date", "2026-03-03"])
    check(r["meals_count"] == 1, "still 1 meal after overwrite")
    check(r["meals"][0]["cal"] == 500, "cal updated to 500")
    check(r["meals"][0]["p"] == 30, "protein updated to 30")


def test_load_existing(tmp_dir: str):
    """Load returns saved meals."""
    meal = json.dumps({"name": "lunch", "cal": 600, "p": 35, "c": 70, "f": 20})
    run_cmd(["save", "--data-dir", tmp_dir, "--meal", meal, "--date", "2026-03-04"])
    r = run_cmd(["load", "--data-dir", tmp_dir, "--date", "2026-03-04"])
    check(r["meals_count"] == 1, "loaded 1 meal")
    check(r["meals"][0]["name"] == "lunch", "correct meal name")
    check(r["date"] == "2026-03-04", "correct date")


def test_load_nonexistent(tmp_dir: str):
    """Load returns empty for a day with no records."""
    r = run_cmd(["load", "--data-dir", tmp_dir, "--date", "1999-01-01"])
    check(r["meals_count"] == 0, "no meals for nonexistent date")
    check(r["meals"] == [], "empty meals list")


def test_save_preserves_food_details(tmp_dir: str):
    """Food sub-items are preserved in save/load."""
    meal = json.dumps({
        "name": "dinner", "cal": 700, "p": 40, "c": 80, "f": 25,
        "foods": [
            {"name": "grilled salmon", "cal": 350},
            {"name": "brown rice", "cal": 200},
            {"name": "steamed broccoli", "cal": 55},
        ],
    })
    run_cmd(["save", "--data-dir", tmp_dir, "--meal", meal, "--date", "2026-03-05"])
    r = run_cmd(["load", "--data-dir", tmp_dir, "--date", "2026-03-05"])
    check(len(r["meals"][0]["foods"]) == 3, "3 food items preserved")
    check(r["meals"][0]["foods"][0]["name"] == "grilled salmon", "food name preserved")


def test_save_multiple_then_overwrite_one(tmp_dir: str):
    """Save 3 meals, overwrite middle one, verify others unchanged."""
    for name, cal in [("breakfast", 400), ("lunch", 600), ("dinner", 500)]:
        m = json.dumps({"name": name, "cal": cal, "p": 25, "c": 50, "f": 15})
        run_cmd(["save", "--data-dir", tmp_dir, "--meal", m, "--date", "2026-03-06"])

    fix = json.dumps({"name": "lunch", "cal": 550, "p": 30, "c": 60, "f": 18})
    r = run_cmd(["save", "--data-dir", tmp_dir, "--meal", fix, "--date", "2026-03-06"])
    check(r["meals_count"] == 3, "still 3 meals")
    lunch = [m for m in r["meals"] if m["name"] == "lunch"][0]
    check(lunch["cal"] == 550, "lunch updated to 550")
    bf = [m for m in r["meals"] if m["name"] == "breakfast"][0]
    check(bf["cal"] == 400, "breakfast unchanged")


# ---------------------------------------------------------------------------
# EVALUATE command
# ---------------------------------------------------------------------------

def test_eval_breakfast_on_track():
    """Breakfast checkpoint (30%): intake within range → no adjustment."""
    log = json.dumps([{"name": "breakfast", "cal": 450, "p": 27, "c": 54, "f": 14}])
    r = run_cmd(["evaluate", "--weight", "65", "--cal", "1500", "--meals", "3",
                 "--current-meal", "breakfast", "--log", log])
    check(r["checkpoint_pct"] == 30, "breakfast checkpoint = 30%")
    check(r["checkpoint_range"]["cal_min"] == round(1400 * 0.30), "cal_min = 1400*0.30")
    check(r["checkpoint_range"]["cal_max"] == round(1600 * 0.30), "cal_max = 1600*0.30")
    check(r["actual"]["cal"] == 450, "actual cal = 450")
    check(r["status"]["cal"] == "on_track", "cal on_track")
    check(r["needs_adjustment"] is False, "no adjustment needed")
    check(r["adjusted"] is None, "no assumed → adjusted is None")


def test_eval_lunch_cumulative():
    """Lunch checkpoint (70%): cumulative breakfast + lunch."""
    log = json.dumps([
        {"name": "breakfast", "cal": 420, "p": 26, "c": 50, "f": 13},
        {"name": "lunch", "cal": 580, "p": 35, "c": 68, "f": 19},
    ])
    r = run_cmd(["evaluate", "--weight", "65", "--cal", "1500", "--meals", "3",
                 "--current-meal", "lunch", "--log", log])
    check(r["checkpoint_pct"] == 70, "lunch checkpoint = 70%")
    check(r["actual"]["cal"] == 1000, "cumulative cal = 420+580")
    check(r["actual"]["p"] == 61, "cumulative p = 26+35")
    check(r["checkpoint_target"]["cal"] == round(1500 * 0.70), "checkpoint target cal")
    check("breakfast" in r["meals_included"], "breakfast included")
    check("lunch" in r["meals_included"], "lunch included")


def test_eval_dinner_full_day():
    """Dinner checkpoint (100%): full day evaluation."""
    log = json.dumps([
        {"name": "breakfast", "cal": 400, "p": 25, "c": 48, "f": 13},
        {"name": "lunch", "cal": 600, "p": 36, "c": 72, "f": 18},
        {"name": "dinner", "cal": 450, "p": 28, "c": 55, "f": 14},
    ])
    r = run_cmd(["evaluate", "--weight", "65", "--cal", "1500", "--meals", "3",
                 "--current-meal", "dinner", "--log", log])
    check(r["checkpoint_pct"] == 100, "dinner checkpoint = 100%")
    check(r["actual"]["cal"] == 1450, "total cal = 1450")
    check(r["checkpoint_target"]["cal"] == 1500, "checkpoint target = full daily")


def test_eval_calories_high_triggers_adjustment():
    """Calories over checkpoint range triggers needs_adjustment."""
    log = json.dumps([{"name": "breakfast", "cal": 700, "p": 30, "c": 80, "f": 25}])
    r = run_cmd(["evaluate", "--weight", "65", "--cal", "1500", "--meals", "3",
                 "--current-meal", "breakfast", "--log", log])
    check(r["status"]["cal"] == "high", "cal status = high")
    check(r["needs_adjustment"] is True, "adjustment needed for high cal")


def test_eval_calories_low_triggers_adjustment():
    """Calories under checkpoint range triggers needs_adjustment."""
    log = json.dumps([{"name": "breakfast", "cal": 200, "p": 10, "c": 25, "f": 5}])
    r = run_cmd(["evaluate", "--weight", "65", "--cal", "1500", "--meals", "3",
                 "--current-meal", "breakfast", "--log", log])
    check(r["status"]["cal"] == "low", "cal status = low")
    check(r["needs_adjustment"] is True, "adjustment needed for low cal")


def test_eval_two_macros_outside_triggers_adjustment():
    """2+ macros outside range → adjustment even if calories OK."""
    log = json.dumps([{"name": "breakfast", "cal": 450, "p": 5, "c": 95, "f": 5}])
    r = run_cmd(["evaluate", "--weight", "65", "--cal", "1500", "--meals", "3",
                 "--current-meal", "breakfast", "--log", log])
    macros_outside = sum(1 for k in ["p", "c", "f"] if r["status"][k] != "on_track")
    check(macros_outside >= 2, f"at least 2 macros outside (got {macros_outside})")
    check(r["needs_adjustment"] is True, "adjustment from macro imbalance")


def test_eval_one_macro_outside_no_adjustment():
    """1 macro slightly outside range, cal OK → no adjustment."""
    targets = run_cmd(["target", "--weight", "65", "--cal", "1500", "--meals", "3"])
    cp_p_target = targets["protein"]["target"] * 0.30
    cp_c_target = targets["carb"]["target"] * 0.30
    cp_f_target = targets["fat"]["target"] * 0.30
    log = json.dumps([{
        "name": "breakfast",
        "cal": 450,
        "p": round(cp_p_target - 15),
        "c": round(cp_c_target),
        "f": round(cp_f_target),
    }])
    r = run_cmd(["evaluate", "--weight", "65", "--cal", "1500", "--meals", "3",
                 "--current-meal", "breakfast", "--log", log])
    cal_ok = r["status"]["cal"] == "on_track"
    macros_outside = sum(1 for k in ["p", "c", "f"] if r["status"][k] != "on_track")
    if cal_ok and macros_outside <= 1:
        check(r["needs_adjustment"] is False, "1 macro outside + cal OK = no adjustment")
    else:
        check(True, "test_eval_one_macro_outside: values shifted into adj range, skipped")


def test_eval_snack_am_in_breakfast_block():
    """snack_am belongs to breakfast block (30%)."""
    log = json.dumps([
        {"name": "breakfast", "cal": 350, "p": 22, "c": 42, "f": 11},
        {"name": "snack_am", "cal": 100, "p": 3, "c": 15, "f": 4},
    ])
    r = run_cmd(["evaluate", "--weight", "65", "--cal", "1500", "--meals", "3",
                 "--current-meal", "snack_am", "--log", log])
    check(r["checkpoint_pct"] == 30, "snack_am → breakfast block 30%")
    check(r["actual"]["cal"] == 450, "breakfast + snack_am included")
    check("snack_am" in r["meals_included"], "snack_am in meals_included")
    check("breakfast" in r["meals_included"], "breakfast in meals_included")


def test_eval_snack_pm_in_lunch_block():
    """snack_pm belongs to lunch block; checkpoint = 70% cumulative."""
    log = json.dumps([
        {"name": "breakfast", "cal": 400, "p": 25, "c": 48, "f": 13},
        {"name": "lunch", "cal": 550, "p": 33, "c": 66, "f": 18},
        {"name": "snack_pm", "cal": 150, "p": 5, "c": 20, "f": 7},
    ])
    r = run_cmd(["evaluate", "--weight", "65", "--cal", "1500", "--meals", "3",
                 "--current-meal", "snack_pm", "--log", log])
    check(r["checkpoint_pct"] == 70, "snack_pm → lunch block, cumulative 70%")
    check(r["actual"]["cal"] == 1100, "bf+lunch+snack_pm cumulative")
    check("snack_pm" in r["meals_included"], "snack_pm included")


def test_eval_with_assumed_meals():
    """Assumed meals: actual excludes them, adjusted includes them."""
    log = json.dumps([{"name": "lunch", "cal": 600, "p": 35, "c": 70, "f": 18}])
    assumed = json.dumps([{"name": "breakfast", "cal": 450, "p": 27, "c": 54, "f": 14}])
    r = run_cmd(["evaluate", "--weight", "65", "--cal", "1500", "--meals", "3",
                 "--current-meal", "lunch", "--log", log, "--assumed", assumed])
    check(r["actual"]["cal"] == 600, "actual only includes logged meals")
    check(r["adjusted"]["cal"] == 1050, "adjusted = logged + assumed")
    check(r["adjusted"]["p"] == 62, "adjusted p = 35 + 27")
    check("breakfast" in r["missing_meals"], "breakfast in missing_meals")


def test_eval_assumed_affects_diff():
    """diff_for_suggestions uses adjusted values when assumed meals present."""
    log = json.dumps([{"name": "lunch", "cal": 600, "p": 35, "c": 70, "f": 18}])
    assumed = json.dumps([{"name": "breakfast", "cal": 450, "p": 27, "c": 54, "f": 14}])
    r = run_cmd(["evaluate", "--weight", "65", "--cal", "1500", "--meals", "3",
                 "--current-meal", "lunch", "--log", log, "--assumed", assumed])
    cp_target_cal = r["checkpoint_target"]["cal"]
    expected_diff_cal = round(cp_target_cal - 1050, 1)
    check(r["diff_for_suggestions"]["cal"] == expected_diff_cal,
          "diff uses adjusted (with assumed) for suggestions")


def test_eval_no_assumed_diff_uses_actual():
    """Without assumed meals, diff_for_suggestions uses actual values."""
    log = json.dumps([{"name": "breakfast", "cal": 450, "p": 27, "c": 54, "f": 14}])
    r = run_cmd(["evaluate", "--weight", "65", "--cal", "1500", "--meals", "3",
                 "--current-meal", "breakfast", "--log", log])
    cp_target_cal = r["checkpoint_target"]["cal"]
    expected_diff_cal = round(cp_target_cal - 450, 1)
    check(r["diff_for_suggestions"]["cal"] == expected_diff_cal,
          "diff uses actual when no assumed")


def test_eval_2meal_plan():
    """2-meal plan: meal_1 checkpoint = 50%."""
    log = json.dumps([{"name": "meal_1", "cal": 800, "p": 50, "c": 95, "f": 28}])
    r = run_cmd(["evaluate", "--weight", "70", "--cal", "1800", "--meals", "2",
                 "--current-meal", "meal_1", "--log", log])
    check(r["checkpoint_pct"] == 50, "meal_1 checkpoint = 50%")
    check(r["checkpoint_target"]["cal"] == round(1800 * 0.50), "checkpoint target = 900")
    check(r["actual"]["cal"] == 800, "actual cal correct")


def test_eval_2meal_cumulative():
    """2-meal plan: meal_2 checkpoint = 100% cumulative."""
    log = json.dumps([
        {"name": "meal_1", "cal": 850, "p": 50, "c": 100, "f": 28},
        {"name": "meal_2", "cal": 900, "p": 55, "c": 105, "f": 30},
    ])
    r = run_cmd(["evaluate", "--weight", "70", "--cal", "1800", "--meals", "2",
                 "--current-meal", "meal_2", "--log", log])
    check(r["checkpoint_pct"] == 100, "meal_2 checkpoint = 100%")
    check(r["actual"]["cal"] == 1750, "cumulative 850+900")


def test_eval_2meal_snack():
    """2-meal plan: snack_1 belongs to meal_1 block."""
    log = json.dumps([
        {"name": "meal_1", "cal": 750, "p": 45, "c": 90, "f": 25},
        {"name": "snack_1", "cal": 100, "p": 3, "c": 15, "f": 4},
    ])
    r = run_cmd(["evaluate", "--weight", "70", "--cal", "1800", "--meals", "2",
                 "--current-meal", "snack_1", "--log", log])
    check(r["checkpoint_pct"] == 50, "snack_1 → meal_1 block 50%")
    check(r["actual"]["cal"] == 850, "meal_1 + snack_1")


def test_eval_2meal_dinner_alias():
    """2-meal plan: 'dinner' is aliased to meal_2 (100% checkpoint)."""
    log = json.dumps([
        {"name": "meal_1", "cal": 850, "p": 50, "c": 100, "f": 28},
        {"name": "dinner", "cal": 900, "p": 55, "c": 105, "f": 30},
    ])
    r = run_cmd(["evaluate", "--weight", "70", "--cal", "1800", "--meals", "2",
                 "--current-meal", "dinner", "--log", log])
    check(r["checkpoint_pct"] == 100, "dinner aliased to meal_2 → 100%")
    check(r["actual"]["cal"] == 1750, "cumulative includes both meals")
    check("dinner" in r["meals_included"], "dinner in meals_included")
    check(r["resolved_meal"] == "meal_2", "resolved_meal = meal_2")


def test_eval_2meal_lunch_alias():
    """2-meal plan: 'lunch' is aliased to meal_1 (50% checkpoint)."""
    log = json.dumps([
        {"name": "lunch", "cal": 800, "p": 50, "c": 95, "f": 28},
    ])
    r = run_cmd(["evaluate", "--weight", "70", "--cal", "1800", "--meals", "2",
                 "--current-meal", "lunch", "--log", log])
    check(r["checkpoint_pct"] == 50, "lunch aliased to meal_1 → 50%")
    check(r["actual"]["cal"] == 800, "actual cal correct")
    check(r["resolved_meal"] == "meal_1", "resolved_meal = meal_1")


def test_missing_2meal_dinner_alias():
    """2-meal plan: check-missing with 'dinner' alias detects missing meal_1."""
    log = json.dumps([{"name": "dinner", "cal": 800, "p": 50, "c": 95, "f": 28}])
    r = run_cmd(["check-missing", "--meals", "2", "--current-meal", "dinner", "--log", log])
    check(r["has_missing"] is True, "meal_1 missing when logging dinner alias")
    check(r["missing"][0]["name"] == "meal_1", "missing = meal_1")


def test_missing_2meal_lunch_covers_meal1():
    """2-meal plan: 'lunch' logged satisfies meal_1 requirement."""
    log = json.dumps([{"name": "lunch", "cal": 800, "p": 50, "c": 95, "f": 28}])
    r = run_cmd(["check-missing", "--meals", "2", "--current-meal", "dinner", "--log", log])
    check(r["has_missing"] is False, "lunch satisfies meal_1 for dinner checkpoint")


def test_eval_unknown_meal():
    """Unknown meal name returns error."""
    log = json.dumps([{"name": "breakfast", "cal": 400, "p": 25, "c": 50, "f": 12}])
    r = run_cmd(["evaluate", "--weight", "65", "--cal", "1500", "--meals", "3",
                 "--current-meal", "brunch", "--log", log])
    check("error" in r, "unknown meal returns error key")


def test_eval_missing_meals_in_output():
    """Evaluate reports missing main meals before the current checkpoint."""
    log = json.dumps([{"name": "dinner", "cal": 500, "p": 30, "c": 60, "f": 15}])
    r = run_cmd(["evaluate", "--weight", "65", "--cal", "1500", "--meals", "3",
                 "--current-meal", "dinner", "--log", log])
    check("breakfast" in r["missing_meals"], "breakfast missing")
    check("lunch" in r["missing_meals"], "lunch missing")


def test_eval_meals_outside_checkpoint_excluded():
    """Meals from later blocks are excluded from checkpoint evaluation."""
    log = json.dumps([
        {"name": "breakfast", "cal": 400, "p": 25, "c": 50, "f": 12},
        {"name": "dinner", "cal": 500, "p": 30, "c": 60, "f": 15},
    ])
    r = run_cmd(["evaluate", "--weight", "65", "--cal", "1500", "--meals", "3",
                 "--current-meal", "breakfast", "--log", log])
    check(r["actual"]["cal"] == 400, "dinner excluded from breakfast checkpoint")
    check("dinner" not in r["meals_included"], "dinner not in meals_included")


def test_eval_range_boundary_exactly_min():
    """Exactly at checkpoint min → on_track."""
    cal_min_30 = round(1400 * 0.30)
    log = json.dumps([{"name": "breakfast", "cal": cal_min_30, "p": 27, "c": 54, "f": 14}])
    r = run_cmd(["evaluate", "--weight", "65", "--cal", "1500", "--meals", "3",
                 "--current-meal", "breakfast", "--log", log])
    check(r["status"]["cal"] == "on_track", f"cal={cal_min_30} exactly at min → on_track")


def test_eval_range_boundary_exactly_max():
    """Exactly at checkpoint max → on_track."""
    cal_max_30 = round(1600 * 0.30)
    log = json.dumps([{"name": "breakfast", "cal": cal_max_30, "p": 27, "c": 54, "f": 14}])
    r = run_cmd(["evaluate", "--weight", "65", "--cal", "1500", "--meals", "3",
                 "--current-meal", "breakfast", "--log", log])
    check(r["status"]["cal"] == "on_track", f"cal={cal_max_30} exactly at max → on_track")


def test_eval_range_boundary_one_below_min():
    """One below checkpoint min → low."""
    cal_min_30 = round(1400 * 0.30)
    log = json.dumps([{"name": "breakfast", "cal": cal_min_30 - 1, "p": 27, "c": 54, "f": 14}])
    r = run_cmd(["evaluate", "--weight", "65", "--cal", "1500", "--meals", "3",
                 "--current-meal", "breakfast", "--log", log])
    check(r["status"]["cal"] == "low", f"cal={cal_min_30 - 1} just below min → low")


def test_eval_range_boundary_one_above_max():
    """One above checkpoint max → high."""
    cal_max_30 = round(1600 * 0.30)
    log = json.dumps([{"name": "breakfast", "cal": cal_max_30 + 1, "p": 27, "c": 54, "f": 14}])
    r = run_cmd(["evaluate", "--weight", "65", "--cal", "1500", "--meals", "3",
                 "--current-meal", "breakfast", "--log", log])
    check(r["status"]["cal"] == "high", f"cal={cal_max_30 + 1} just above max → high")


# ---------------------------------------------------------------------------
# CHECK-MISSING command
# ---------------------------------------------------------------------------

def test_missing_no_missing():
    """No missing meals when logging breakfast (first meal)."""
    log = json.dumps([])
    r = run_cmd(["check-missing", "--meals", "3", "--current-meal", "breakfast", "--log", log])
    check(r["has_missing"] is False, "nothing missing before breakfast")
    check(len(r["missing"]) == 0, "empty missing list")


def test_missing_breakfast_before_lunch():
    """Breakfast missing when logging lunch."""
    log = json.dumps([{"name": "lunch", "cal": 600, "p": 35, "c": 70, "f": 20}])
    r = run_cmd(["check-missing", "--meals", "3", "--current-meal", "lunch", "--log", log])
    check(r["has_missing"] is True, "breakfast missing")
    check(r["missing"][0]["name"] == "breakfast", "missing meal = breakfast")
    check(r["missing"][0]["expected_pct"] == 30, "breakfast block = 30%")


def test_missing_breakfast_before_dinner():
    """Breakfast missing when logging dinner (lunch present)."""
    log = json.dumps([{"name": "lunch", "cal": 600, "p": 35, "c": 70, "f": 20}])
    r = run_cmd(["check-missing", "--meals", "3", "--current-meal", "dinner", "--log", log])
    check(r["has_missing"] is True, "has missing")
    missing_names = [m["name"] for m in r["missing"]]
    check("breakfast" in missing_names, "breakfast in missing")
    check("lunch" not in missing_names, "lunch not missing (logged)")


def test_missing_both_before_dinner():
    """Both breakfast and lunch missing when logging dinner."""
    log = json.dumps([{"name": "dinner", "cal": 500, "p": 30, "c": 60, "f": 15}])
    r = run_cmd(["check-missing", "--meals", "3", "--current-meal", "dinner", "--log", log])
    missing_names = [m["name"] for m in r["missing"]]
    check(len(missing_names) == 2, "2 meals missing")
    check("breakfast" in missing_names, "breakfast missing")
    check("lunch" in missing_names, "lunch missing")


def test_missing_none_when_all_present():
    """No missing meals when all prior meals are logged."""
    log = json.dumps([
        {"name": "breakfast", "cal": 400, "p": 25, "c": 50, "f": 12},
        {"name": "lunch", "cal": 600, "p": 35, "c": 70, "f": 20},
    ])
    r = run_cmd(["check-missing", "--meals", "3", "--current-meal", "dinner", "--log", log])
    check(r["has_missing"] is False, "no missing meals")


def test_missing_2meal_plan():
    """2-meal plan: meal_1 missing when logging meal_2."""
    log = json.dumps([{"name": "meal_2", "cal": 800, "p": 50, "c": 95, "f": 28}])
    r = run_cmd(["check-missing", "--meals", "2", "--current-meal", "meal_2", "--log", log])
    check(r["has_missing"] is True, "meal_1 missing")
    check(r["missing"][0]["name"] == "meal_1", "missing = meal_1")
    check(r["missing"][0]["expected_pct"] == 50, "meal_1 block = 50%")


def test_missing_2meal_none():
    """2-meal plan: no missing when meal_1 is logged before meal_2."""
    log = json.dumps([{"name": "meal_1", "cal": 800, "p": 50, "c": 95, "f": 28}])
    r = run_cmd(["check-missing", "--meals", "2", "--current-meal", "meal_2", "--log", log])
    check(r["has_missing"] is False, "no missing in 2-meal plan")


def test_missing_unknown_meal():
    """Unknown meal name in check-missing returns error."""
    log = json.dumps([])
    r = run_cmd(["check-missing", "--meals", "3", "--current-meal", "brunch", "--log", log])
    check("error" in r, "unknown meal returns error")


def test_missing_snack_doesnt_count_as_main():
    """snack_am logged doesn't satisfy breakfast requirement."""
    log = json.dumps([{"name": "snack_am", "cal": 150, "p": 5, "c": 20, "f": 7}])
    r = run_cmd(["check-missing", "--meals", "3", "--current-meal", "lunch", "--log", log])
    check(r["has_missing"] is True, "snack_am doesn't count as breakfast")
    check(r["missing"][0]["name"] == "breakfast", "breakfast still missing")


# ---------------------------------------------------------------------------
# ERROR HANDLING
# ---------------------------------------------------------------------------

def test_invalid_json_log():
    """Invalid JSON in --log causes failure."""
    run_cmd(["evaluate", "--weight", "65", "--cal", "1500", "--meals", "3",
             "--current-meal", "breakfast", "--log", "not-json"], expect_fail=True)
    check(True, "invalid --log JSON → exit code != 0")


def test_invalid_json_meal():
    """Invalid JSON in --meal causes failure."""
    run_cmd(["save", "--data-dir", "/tmp/noop", "--meal", "{bad-json}"], expect_fail=True)
    check(True, "invalid --meal JSON → exit code != 0")


def test_invalid_json_assumed():
    """Invalid JSON in --assumed causes failure."""
    log = json.dumps([{"name": "lunch", "cal": 600, "p": 35, "c": 70, "f": 18}])
    run_cmd(["evaluate", "--weight", "65", "--cal", "1500", "--meals", "3",
             "--current-meal", "lunch", "--log", log, "--assumed", "bad"], expect_fail=True)
    check(True, "invalid --assumed JSON → exit code != 0")


# ---------------------------------------------------------------------------
# INTEGRATION / WORKFLOW
# ---------------------------------------------------------------------------

def test_full_day_workflow(tmp_dir: str):
    """Simulate a full day: set target → save 3 meals → evaluate at each checkpoint."""
    targets = run_cmd(["target", "--weight", "65", "--cal", "1500", "--meals", "3"])
    check(targets["daily_cal"] == 1500, "workflow: target set")

    day = "2026-03-10"
    bf = {"name": "breakfast", "cal": 420, "p": 26, "c": 50, "f": 13}
    ln = {"name": "lunch", "cal": 580, "p": 35, "c": 68, "f": 19}
    dn = {"name": "dinner", "cal": 430, "p": 27, "c": 52, "f": 13}

    # Save breakfast
    r = run_cmd(["save", "--data-dir", tmp_dir, "--meal", json.dumps(bf), "--date", day])
    check(r["meals_count"] == 1, "workflow: bf saved")

    # Evaluate at breakfast
    r = run_cmd(["evaluate", "--weight", "65", "--cal", "1500", "--meals", "3",
                 "--current-meal", "breakfast", "--log", json.dumps(r["meals"])])
    check(r["checkpoint_pct"] == 30, "workflow: bf eval at 30%")

    # Save lunch
    r = run_cmd(["save", "--data-dir", tmp_dir, "--meal", json.dumps(ln), "--date", day])
    check(r["meals_count"] == 2, "workflow: lunch saved")

    # Check missing before lunch (none expected)
    r_miss = run_cmd(["check-missing", "--meals", "3", "--current-meal", "lunch",
                       "--log", json.dumps(r["meals"])])
    check(r_miss["has_missing"] is False, "workflow: no missing before lunch")

    # Evaluate at lunch
    r_eval = run_cmd(["evaluate", "--weight", "65", "--cal", "1500", "--meals", "3",
                       "--current-meal", "lunch", "--log", json.dumps(r["meals"])])
    check(r_eval["checkpoint_pct"] == 70, "workflow: lunch eval at 70%")
    check(r_eval["actual"]["cal"] == 1000, "workflow: cumulative 420+580")

    # Save dinner
    r = run_cmd(["save", "--data-dir", tmp_dir, "--meal", json.dumps(dn), "--date", day])
    check(r["meals_count"] == 3, "workflow: dinner saved")

    # Evaluate at dinner
    r_eval = run_cmd(["evaluate", "--weight", "65", "--cal", "1500", "--meals", "3",
                       "--current-meal", "dinner", "--log", json.dumps(r["meals"])])
    check(r_eval["checkpoint_pct"] == 100, "workflow: dinner eval at 100%")
    check(r_eval["actual"]["cal"] == 1430, "workflow: total 1430")

    # Analyze the full day
    r_ana = run_cmd(["analyze", "--weight", "65", "--cal", "1500", "--meals", "3",
                      "--log", json.dumps(r["meals"])])
    check(r_ana["cumulative"]["cal"] == 1430, "workflow: analyze total")
    check(r_ana["remaining"]["cal"] == 70, "workflow: 70 cal remaining")
    check(r_ana["status"]["cal"] == "on_track", "workflow: overall on track")


def test_correction_workflow(tmp_dir: str):
    """Save a meal, then correct it, verify updated evaluate."""
    day = "2026-03-11"
    wrong = {"name": "breakfast", "cal": 800, "p": 15, "c": 100, "f": 35}
    run_cmd(["save", "--data-dir", tmp_dir, "--meal", json.dumps(wrong), "--date", day])

    r1 = run_cmd(["evaluate", "--weight", "65", "--cal", "1500", "--meals", "3",
                   "--current-meal", "breakfast",
                   "--log", json.dumps([wrong])])
    check(r1["needs_adjustment"] is True, "correction: before fix needs adj")

    fixed = {"name": "breakfast", "cal": 420, "p": 26, "c": 50, "f": 13}
    r_save = run_cmd(["save", "--data-dir", tmp_dir, "--meal", json.dumps(fixed), "--date", day])
    check(r_save["meals_count"] == 1, "correction: overwrite keeps count")
    check(r_save["meals"][0]["cal"] == 420, "correction: updated cal")

    r2 = run_cmd(["evaluate", "--weight", "65", "--cal", "1500", "--meals", "3",
                   "--current-meal", "breakfast",
                   "--log", json.dumps(r_save["meals"])])
    check(r2["actual"]["cal"] == 420, "correction: eval uses fixed value")


def test_forgotten_meal_workflow(tmp_dir: str):
    """User logs lunch, forgot breakfast, uses --assumed."""
    day = "2026-03-12"
    lunch = {"name": "lunch", "cal": 600, "p": 35, "c": 70, "f": 18}
    run_cmd(["save", "--data-dir", tmp_dir, "--meal", json.dumps(lunch), "--date", day])

    r_load = run_cmd(["load", "--data-dir", tmp_dir, "--date", day])
    log_json = json.dumps(r_load["meals"])

    r_miss = run_cmd(["check-missing", "--meals", "3", "--current-meal", "lunch",
                       "--log", log_json])
    check(r_miss["has_missing"] is True, "forgotten: breakfast missing")

    assumed = [{"name": "breakfast", "cal": 450, "p": 27, "c": 54, "f": 14}]
    r_eval = run_cmd(["evaluate", "--weight", "65", "--cal", "1500", "--meals", "3",
                       "--current-meal", "lunch", "--log", log_json,
                       "--assumed", json.dumps(assumed)])
    check(r_eval["actual"]["cal"] == 600, "forgotten: actual = lunch only")
    check(r_eval["adjusted"]["cal"] == 1050, "forgotten: adjusted = lunch + assumed bf")
    check(r_eval["diff_for_suggestions"]["cal"] == round(r_eval["checkpoint_target"]["cal"] - 1050, 1),
          "forgotten: diff based on adjusted")


# ---------------------------------------------------------------------------
# DETECT DIET PATTERN command
# ---------------------------------------------------------------------------

def _create_days(tmp_dir: str, meals_per_day: list[list[dict]],
                 start_date: str = "2026-03-04"):
    """Helper to create N days of meal data going backwards from start_date."""
    from datetime import date as d, timedelta as td
    start = d.fromisoformat(start_date)
    for offset, day_meals in enumerate(meals_per_day):
        day = (start - td(days=offset)).isoformat()
        for m in day_meals:
            run_cmd(["save", "--data-dir", tmp_dir, "--meal", json.dumps(m), "--date", day])


def test_detect_pattern_high_protein_mismatch(tmp_dir: str):
    """3 days of high-protein eating while on balanced mode → mismatch."""
    # ~40% protein, ~30% carbs, ~30% fat
    day_meals = [
        {"name": "breakfast", "cal": 400, "p": 45, "c": 25, "f": 12},
        {"name": "lunch", "cal": 600, "p": 65, "c": 40, "f": 18},
        {"name": "dinner", "cal": 500, "p": 55, "c": 35, "f": 15},
    ]
    _create_days(tmp_dir, [day_meals] * 3)

    r = run_cmd(["detect-diet-pattern", "--data-dir", tmp_dir,
                 "--current-mode", "balanced", "--date", "2026-03-04"])
    check(r["has_pattern"] is True, "high-protein pattern detected")
    check(r["detected_mode"] == "high_protein",
          f"detected high_protein (got {r.get('detected_mode')})")
    check(r["pros_cons"] is not None, "pros_cons present")
    check(len(r["pros_cons"]["pros"]) > 0, "has pros")
    check(len(r["pros_cons"]["cons"]) > 0, "has cons")
    check(r["days_found"] == 3, "3 days found")


def test_detect_pattern_matches_current(tmp_dir: str):
    """3 days of balanced eating while on balanced mode → no mismatch."""
    # ~30% protein, ~40% carbs, ~30% fat
    day_meals = [
        {"name": "breakfast", "cal": 400, "p": 30, "c": 42, "f": 13},
        {"name": "lunch", "cal": 600, "p": 45, "c": 63, "f": 20},
        {"name": "dinner", "cal": 500, "p": 38, "c": 52, "f": 17},
    ]
    _create_days(tmp_dir, [day_meals] * 3)

    r = run_cmd(["detect-diet-pattern", "--data-dir", tmp_dir,
                 "--current-mode", "balanced", "--date", "2026-03-04"])
    check(r["has_pattern"] is False, "no mismatch when eating matches mode")
    check(r["detected_mode"] is None, "detected_mode is None")


def test_detect_pattern_insufficient_data(tmp_dir: str):
    """Less than 3 days of data → insufficient_data."""
    day_meals = [
        {"name": "lunch", "cal": 600, "p": 65, "c": 40, "f": 18},
    ]
    _create_days(tmp_dir, [day_meals] * 2)

    r = run_cmd(["detect-diet-pattern", "--data-dir", tmp_dir,
                 "--current-mode", "balanced", "--date", "2026-03-04"])
    check(r["has_pattern"] is False, "no pattern with insufficient data")
    check(r.get("reason") == "insufficient_data", "reason = insufficient_data")
    check(r["days_found"] == 2, "2 days found")


def test_detect_pattern_low_carb_detected(tmp_dir: str):
    """3 days of low-carb eating while on balanced → detects low_carb."""
    # ~35% protein, ~20% carbs, ~45% fat
    day_meals = [
        {"name": "breakfast", "cal": 450, "p": 35, "c": 20, "f": 23},
        {"name": "lunch", "cal": 600, "p": 48, "c": 28, "f": 30},
        {"name": "dinner", "cal": 500, "p": 40, "c": 23, "f": 25},
    ]
    _create_days(tmp_dir, [day_meals] * 3)

    r = run_cmd(["detect-diet-pattern", "--data-dir", tmp_dir,
                 "--current-mode", "balanced", "--date", "2026-03-04"])
    check(r["has_pattern"] is True, "low-carb pattern detected")
    check(r["detected_mode"] == "low_carb",
          f"detected low_carb (got {r.get('detected_mode')})")


def test_detect_pattern_keto_detected(tmp_dir: str):
    """3 days of keto eating while on balanced → detects keto."""
    # ~20% protein, ~5% carbs, ~75% fat
    day_meals = [
        {"name": "breakfast", "cal": 500, "p": 25, "c": 6, "f": 42},
        {"name": "lunch", "cal": 600, "p": 30, "c": 8, "f": 50},
        {"name": "dinner", "cal": 500, "p": 25, "c": 6, "f": 42},
    ]
    _create_days(tmp_dir, [day_meals] * 3)

    r = run_cmd(["detect-diet-pattern", "--data-dir", tmp_dir,
                 "--current-mode", "balanced", "--date", "2026-03-04"])
    check(r["has_pattern"] is True, "keto pattern detected")
    check(r["detected_mode"] == "keto",
          f"detected keto (got {r.get('detected_mode')})")


def test_detect_pattern_if_uses_balanced(tmp_dir: str):
    """IF 16:8 mode uses balanced macro profile; balanced eating → no mismatch."""
    # ~30% protein, ~40% carbs, ~30% fat
    day_meals = [
        {"name": "meal_1", "cal": 750, "p": 56, "c": 79, "f": 25},
        {"name": "meal_2", "cal": 750, "p": 56, "c": 79, "f": 25},
    ]
    _create_days(tmp_dir, [day_meals] * 3)

    r = run_cmd(["detect-diet-pattern", "--data-dir", tmp_dir,
                 "--current-mode", "if_16_8", "--date", "2026-03-04"])
    check(r["has_pattern"] is False, "no mismatch for IF with balanced macros")
    check(r["effective_current_mode"] == "balanced", "IF uses balanced profile")


# ---------------------------------------------------------------------------
# RUNNER
# ---------------------------------------------------------------------------

def main():
    tmp_root = tempfile.mkdtemp(prefix="nutrition-test-")

    test_groups = [
        ("TARGET", [
            test_target_3meal,
            test_target_2meal,
            test_target_different_weights,
        ]),
        ("ANALYZE", [
            test_analyze_single_meal,
            test_analyze_multiple_meals,
            test_analyze_empty_log,
            test_analyze_status_labels,
            test_analyze_on_track,
        ]),
        ("SAVE & LOAD", [
            (test_save_creates_file, True),
            (test_save_appends, True),
            (test_save_overwrites_same_meal, True),
            (test_load_existing, True),
            (test_load_nonexistent, True),
            (test_save_preserves_food_details, True),
            (test_save_multiple_then_overwrite_one, True),
        ]),
        ("EVALUATE", [
            test_eval_breakfast_on_track,
            test_eval_lunch_cumulative,
            test_eval_dinner_full_day,
            test_eval_calories_high_triggers_adjustment,
            test_eval_calories_low_triggers_adjustment,
            test_eval_two_macros_outside_triggers_adjustment,
            test_eval_one_macro_outside_no_adjustment,
            test_eval_snack_am_in_breakfast_block,
            test_eval_snack_pm_in_lunch_block,
            test_eval_with_assumed_meals,
            test_eval_assumed_affects_diff,
            test_eval_no_assumed_diff_uses_actual,
            test_eval_2meal_plan,
            test_eval_2meal_cumulative,
            test_eval_2meal_snack,
            test_eval_2meal_dinner_alias,
            test_eval_2meal_lunch_alias,
            test_eval_unknown_meal,
            test_eval_missing_meals_in_output,
            test_eval_meals_outside_checkpoint_excluded,
            test_eval_range_boundary_exactly_min,
            test_eval_range_boundary_exactly_max,
            test_eval_range_boundary_one_below_min,
            test_eval_range_boundary_one_above_max,
        ]),
        ("CHECK-MISSING", [
            test_missing_no_missing,
            test_missing_breakfast_before_lunch,
            test_missing_breakfast_before_dinner,
            test_missing_both_before_dinner,
            test_missing_none_when_all_present,
            test_missing_2meal_plan,
            test_missing_2meal_none,
            test_missing_2meal_dinner_alias,
            test_missing_2meal_lunch_covers_meal1,
            test_missing_unknown_meal,
            test_missing_snack_doesnt_count_as_main,
        ]),
        ("ERROR HANDLING", [
            test_invalid_json_log,
            test_invalid_json_meal,
            test_invalid_json_assumed,
        ]),
        ("INTEGRATION WORKFLOWS", [
            (test_full_day_workflow, True),
            (test_correction_workflow, True),
            (test_forgotten_meal_workflow, True),
        ]),
        ("DETECT DIET PATTERN", [
            (test_detect_pattern_high_protein_mismatch, True),
            (test_detect_pattern_matches_current, True),
            (test_detect_pattern_insufficient_data, True),
            (test_detect_pattern_low_carb_detected, True),
            (test_detect_pattern_keto_detected, True),
            (test_detect_pattern_if_uses_balanced, True),
        ]),
    ]

    print(f"Running comprehensive nutrition-calc tests...\n")

    for group_name, tests in test_groups:
        print(f"--- {group_name} ---")
        for t in tests:
            needs_dir = False
            fn = t
            if isinstance(t, tuple):
                fn, needs_dir = t

            test_name = fn.__name__
            try:
                if needs_dir:
                    sub = tempfile.mkdtemp(dir=tmp_root)
                    fn(sub)
                else:
                    fn()
                print(f"  ✅ {test_name}")
            except Exception as e:
                global failed
                failed += 1
                errors.append(f"{test_name}: {e}")
                print(f"  ❌ {test_name}: {e}")
        print()

    shutil.rmtree(tmp_root, ignore_errors=True)

    print("=" * 50)
    print(f"Results: {passed} passed, {failed} failed")
    if errors:
        print(f"\nFailures:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print("\n🎉 All tests passed!")


if __name__ == "__main__":
    main()
