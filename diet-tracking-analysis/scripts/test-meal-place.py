# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
Test suite for meal-place.py.

Covers: load, check, save-place, record-drift, reset-drift
with all key scenarios from meal-place-rules.md.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

SCRIPT = os.path.join(os.path.dirname(__file__), "meal-place.py")

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


# ---------------------------------------------------------------------------
# LOAD: empty profile creation
# ---------------------------------------------------------------------------

def test_load_creates_default():
    """Load on empty dir returns a valid default profile."""
    tmpdir = tempfile.mkdtemp()
    try:
        r = run_cmd(["load", "--data-dir", tmpdir])
        check(r is not None, "load returns JSON")
        for meal in ("breakfast", "lunch", "dinner"):
            check(r["workday_meal_place_profile"][meal]["place"] is None,
                  f"load default: {meal} place is null")
            check(r["_collection_state"][meal]["ask_count"] == 0,
                  f"load default: {meal} ask_count is 0")
            check(r["_drift_detection"][meal]["consecutive_mismatches"] == 0,
                  f"load default: {meal} drift is 0")
    finally:
        shutil.rmtree(tmpdir)


def test_load_reads_existing():
    """Load reads back a previously saved profile."""
    tmpdir = tempfile.mkdtemp()
    try:
        run_cmd(["save-place", "--data-dir", tmpdir, "--meal", "lunch", "--place", "cafeteria"])
        r = run_cmd(["load", "--data-dir", tmpdir])
        check(r["workday_meal_place_profile"]["lunch"]["place"] == "cafeteria",
              "load reads saved place")
    finally:
        shutil.rmtree(tmpdir)


# ---------------------------------------------------------------------------
# CHECK: weekday / weekend
# ---------------------------------------------------------------------------

def test_check_weekend_skips():
    """Check on weekend (Sat=5, Sun=6) always returns skip."""
    tmpdir = tempfile.mkdtemp()
    try:
        for day in (5, 6):
            r = run_cmd(["check", "--data-dir", tmpdir, "--meal", "lunch", "--weekday", str(day)])
            check(r["action"] == "skip", f"weekend day {day} → skip")
            check(r["reason"] == "weekend", f"weekend day {day} → reason=weekend")
    finally:
        shutil.rmtree(tmpdir)


def test_check_workday_empty_asks_pick_two():
    """Check on workday with empty profile and no inference returns pick_two mode."""
    tmpdir = tempfile.mkdtemp()
    try:
        r = run_cmd(["check", "--data-dir", tmpdir, "--meal", "lunch", "--weekday", "2"])
        check(r["action"] == "ask", "empty profile → ask")
        check(r["mode"] == "pick_two", "no inference → pick_two mode")
        check(r["options"] == ["cafeteria", "restaurant"],
              "lunch default options = cafeteria, restaurant")
        check(r["ask_count"] == 1, "first check → ask_count=1")
    finally:
        shutil.rmtree(tmpdir)


def test_check_auto_increments_ask_count():
    """Each check call auto-increments ask_count when place is null."""
    tmpdir = tempfile.mkdtemp()
    try:
        r = run_cmd(["check", "--data-dir", tmpdir, "--meal", "lunch", "--weekday", "1"])
        check(r["ask_count"] == 1, "1st check → ask_count=1")

        r = run_cmd(["check", "--data-dir", tmpdir, "--meal", "lunch", "--weekday", "2"])
        check(r["ask_count"] == 2, "2nd check → ask_count=2")

        r = run_cmd(["check", "--data-dir", tmpdir, "--meal", "lunch", "--weekday", "3"])
        check(r["ask_count"] == 3, "3rd check → ask_count=3")
    finally:
        shutil.rmtree(tmpdir)


def test_check_high_confidence_confirms():
    """Check with --inferred + --confidence high returns confirm mode."""
    tmpdir = tempfile.mkdtemp()
    try:
        r = run_cmd(["check", "--data-dir", tmpdir, "--meal", "breakfast", "--weekday", "1",
                      "--inferred", "takeout", "--confidence", "high"])
        check(r["action"] == "ask", "high confidence → ask")
        check(r["mode"] == "confirm", "high confidence → confirm mode")
        check(r["inferred"] == "takeout", "inferred value passed through")
    finally:
        shutil.rmtree(tmpdir)


def test_check_low_confidence_pick_two_with_inferred():
    """Check with --inferred + --confidence low returns pick_two with inferred first."""
    tmpdir = tempfile.mkdtemp()
    try:
        r = run_cmd(["check", "--data-dir", tmpdir, "--meal", "dinner", "--weekday", "1",
                      "--inferred", "cafeteria", "--confidence", "low"])
        check(r["action"] == "ask", "low confidence → ask")
        check(r["mode"] == "pick_two", "low confidence → pick_two mode")
        check(r["options"][0] == "cafeteria", "low confidence → inferred is first option")
        check(len(r["options"]) == 2, "low confidence → still 2 options")
    finally:
        shutil.rmtree(tmpdir)


def test_check_low_confidence_inferred_already_in_defaults():
    """When inferred is already in defaults, it moves to first position."""
    tmpdir = tempfile.mkdtemp()
    try:
        r = run_cmd(["check", "--data-dir", tmpdir, "--meal", "lunch", "--weekday", "2",
                      "--inferred", "restaurant", "--confidence", "low"])
        check(r["options"] == ["restaurant", "cafeteria"],
              "low confidence → inferred moved to first, other kept")
    finally:
        shutil.rmtree(tmpdir)


def test_check_inferred_no_confidence_defaults_to_pick_two():
    """--inferred without --confidence defaults to pick_two with inferred."""
    tmpdir = tempfile.mkdtemp()
    try:
        r = run_cmd(["check", "--data-dir", tmpdir, "--meal", "dinner", "--weekday", "3",
                      "--inferred", "cafeteria"])
        check(r["mode"] == "pick_two", "no confidence flag → pick_two")
        check(r["options"][0] == "cafeteria", "no confidence → inferred still first")
    finally:
        shutil.rmtree(tmpdir)


def test_check_invalid_inference_falls_back():
    """Check with invalid --inferred falls back to pick_two with defaults."""
    tmpdir = tempfile.mkdtemp()
    try:
        r = run_cmd(["check", "--data-dir", tmpdir, "--meal", "lunch", "--weekday", "3",
                      "--inferred", "moon_base"])
        check(r["action"] == "ask", "invalid inferred → still ask")
        check(r["mode"] == "pick_two", "invalid inferred → pick_two fallback")
        check(r["options"] == ["cafeteria", "restaurant"], "invalid inferred → default options")
    finally:
        shutil.rmtree(tmpdir)


def test_check_breakfast_options():
    """Breakfast default top-2 is home + cafeteria."""
    tmpdir = tempfile.mkdtemp()
    try:
        r = run_cmd(["check", "--data-dir", tmpdir, "--meal", "breakfast", "--weekday", "0"])
        check(r["options"] == ["home", "cafeteria"],
              "breakfast default options = home, cafeteria")
    finally:
        shutil.rmtree(tmpdir)


def test_check_dinner_options():
    """Dinner default top-2 is home + restaurant."""
    tmpdir = tempfile.mkdtemp()
    try:
        r = run_cmd(["check", "--data-dir", tmpdir, "--meal", "dinner", "--weekday", "3"])
        check(r["options"] == ["home", "restaurant"],
              "dinner default options = home, restaurant")
    finally:
        shutil.rmtree(tmpdir)


# ---------------------------------------------------------------------------
# CHECK: already collected (place is set)
# ---------------------------------------------------------------------------

def test_check_already_collected_skips():
    """Check after place is saved returns none/no_drift."""
    tmpdir = tempfile.mkdtemp()
    try:
        run_cmd(["save-place", "--data-dir", tmpdir, "--meal", "lunch", "--place", "cafeteria"])
        r = run_cmd(["check", "--data-dir", tmpdir, "--meal", "lunch", "--weekday", "1"])
        check(r["action"] == "none", "collected → action=none")
        check(r["reason"] == "no_drift", "collected → reason=no_drift")
    finally:
        shutil.rmtree(tmpdir)


# ---------------------------------------------------------------------------
# CHECK: 3-strike give-up (check auto-increments)
# ---------------------------------------------------------------------------

def test_gave_up_after_3_checks():
    """After 3 checks without save-place, 4th check returns skip/gave_up."""
    tmpdir = tempfile.mkdtemp()
    try:
        # 3 checks auto-increment ask_count to 3
        for i in range(3):
            r = run_cmd(["check", "--data-dir", tmpdir, "--meal", "dinner", "--weekday", "0"])
            check(r["action"] == "ask", f"check {i+1} → still ask")

        # 4th check: gave up
        r = run_cmd(["check", "--data-dir", tmpdir, "--meal", "dinner", "--weekday", "1"])
        check(r["action"] == "skip", "4th check → skip")
        check(r["reason"] == "gave_up", "4th check → reason=gave_up")
    finally:
        shutil.rmtree(tmpdir)


# ---------------------------------------------------------------------------
# SAVE-PLACE
# ---------------------------------------------------------------------------

def test_save_place_stores():
    """save-place stores the venue."""
    tmpdir = tempfile.mkdtemp()
    try:
        r = run_cmd(["save-place", "--data-dir", tmpdir, "--meal", "breakfast", "--place", "home"])
        check(r["workday_meal_place_profile"]["breakfast"]["place"] == "home",
              "saved place = home")
        check(r["workday_meal_place_profile"]["breakfast"]["updated_at"] is not None,
              "saved → updated_at set")
    finally:
        shutil.rmtree(tmpdir)


def test_save_place_invalid():
    """save-place rejects invalid place values."""
    tmpdir = tempfile.mkdtemp()
    try:
        run_cmd(["save-place", "--data-dir", tmpdir, "--meal", "lunch", "--place", "moon"],
                expect_fail=True)
    finally:
        shutil.rmtree(tmpdir)


def test_save_place_overwrites():
    """save-place can update an existing venue."""
    tmpdir = tempfile.mkdtemp()
    try:
        run_cmd(["save-place", "--data-dir", tmpdir, "--meal", "lunch", "--place", "cafeteria"])
        r = run_cmd(["save-place", "--data-dir", tmpdir, "--meal", "lunch", "--place", "takeout"])
        check(r["workday_meal_place_profile"]["lunch"]["place"] == "takeout",
              "overwrite: place updated to takeout")
    finally:
        shutil.rmtree(tmpdir)


# ---------------------------------------------------------------------------
# RECORD-DRIFT: mismatch counting
# ---------------------------------------------------------------------------

def test_drift_match_resets():
    """Inferred venue matching stored place resets counter."""
    tmpdir = tempfile.mkdtemp()
    try:
        run_cmd(["save-place", "--data-dir", tmpdir, "--meal", "lunch", "--place", "cafeteria"])
        r = run_cmd(["record-drift", "--data-dir", tmpdir, "--meal", "lunch",
                      "--inferred", "cafeteria"])
        check(r["consecutive_mismatches"] == 0, "match → counter=0")
        check(r["should_confirm"] is False, "match → no confirm")
    finally:
        shutil.rmtree(tmpdir)


def test_drift_mismatch_increments():
    """Inferred venue differing from stored increments counter."""
    tmpdir = tempfile.mkdtemp()
    try:
        run_cmd(["save-place", "--data-dir", tmpdir, "--meal", "lunch", "--place", "cafeteria"])

        r = run_cmd(["record-drift", "--data-dir", tmpdir, "--meal", "lunch",
                      "--inferred", "takeout"])
        check(r["consecutive_mismatches"] == 1, "1st mismatch → counter=1")
        check(r["should_confirm"] is False, "1 mismatch → no confirm")

        r = run_cmd(["record-drift", "--data-dir", tmpdir, "--meal", "lunch",
                      "--inferred", "takeout"])
        check(r["consecutive_mismatches"] == 2, "2nd mismatch → counter=2")

        r = run_cmd(["record-drift", "--data-dir", tmpdir, "--meal", "lunch",
                      "--inferred", "takeout"])
        check(r["consecutive_mismatches"] == 3, "3rd mismatch → counter=3")
        check(r["should_confirm"] is True, "3 mismatches → should_confirm")
    finally:
        shutil.rmtree(tmpdir)


def test_drift_mixed_resets_on_match():
    """A matching inference in between resets the counter."""
    tmpdir = tempfile.mkdtemp()
    try:
        run_cmd(["save-place", "--data-dir", tmpdir, "--meal", "lunch", "--place", "cafeteria"])

        run_cmd(["record-drift", "--data-dir", tmpdir, "--meal", "lunch",
                  "--inferred", "takeout"])
        run_cmd(["record-drift", "--data-dir", tmpdir, "--meal", "lunch",
                  "--inferred", "takeout"])
        # 2 mismatches, then a match
        r = run_cmd(["record-drift", "--data-dir", tmpdir, "--meal", "lunch",
                      "--inferred", "cafeteria"])
        check(r["consecutive_mismatches"] == 0, "match after 2 mismatches → reset to 0")
    finally:
        shutil.rmtree(tmpdir)


def test_drift_no_baseline_skips():
    """record-drift with no saved place returns skip."""
    tmpdir = tempfile.mkdtemp()
    try:
        r = run_cmd(["record-drift", "--data-dir", tmpdir, "--meal", "lunch",
                      "--inferred", "takeout"])
        check(r["action"] == "skip", "no baseline → skip")
        check(r["reason"] == "no_baseline", "no baseline → reason")
    finally:
        shutil.rmtree(tmpdir)


def test_check_shows_drift_confirm():
    """check returns drift_confirm when threshold reached."""
    tmpdir = tempfile.mkdtemp()
    try:
        run_cmd(["save-place", "--data-dir", tmpdir, "--meal", "lunch", "--place", "cafeteria"])
        for _ in range(3):
            run_cmd(["record-drift", "--data-dir", tmpdir, "--meal", "lunch",
                      "--inferred", "takeout"])

        r = run_cmd(["check", "--data-dir", tmpdir, "--meal", "lunch", "--weekday", "1"])
        check(r["action"] == "drift_confirm", "3 drifts → drift_confirm")
        check(r["current_place"] == "cafeteria", "drift_confirm shows current")
        check(r["inferred_place"] == "takeout", "drift_confirm shows inferred")
    finally:
        shutil.rmtree(tmpdir)


# ---------------------------------------------------------------------------
# RESET-DRIFT
# ---------------------------------------------------------------------------

def test_reset_drift_clears():
    """reset-drift zeros out the counters."""
    tmpdir = tempfile.mkdtemp()
    try:
        run_cmd(["save-place", "--data-dir", tmpdir, "--meal", "lunch", "--place", "cafeteria"])
        for _ in range(3):
            run_cmd(["record-drift", "--data-dir", tmpdir, "--meal", "lunch",
                      "--inferred", "takeout"])

        r = run_cmd(["reset-drift", "--data-dir", tmpdir, "--meal", "lunch"])
        check(r["drift_reset"] is True, "reset-drift returns true")

        # Verify check no longer shows drift_confirm
        r = run_cmd(["check", "--data-dir", tmpdir, "--meal", "lunch", "--weekday", "1"])
        check(r["action"] == "none", "after reset → no drift_confirm")
    finally:
        shutil.rmtree(tmpdir)


# ---------------------------------------------------------------------------
# INTEGRATION: full collection flow
# ---------------------------------------------------------------------------

def test_full_collection_flow():
    """End-to-end: check × 2 (no reply) → check → save → check."""
    tmpdir = tempfile.mkdtemp()
    try:
        # First check: should ask (ask_count becomes 1)
        r = run_cmd(["check", "--data-dir", tmpdir, "--meal", "lunch", "--weekday", "1"])
        check(r["action"] == "ask", "flow: 1st check → ask")
        check(r["ask_count"] == 1, "flow: ask_count=1")

        # User doesn't reply, next meal log triggers another check (ask_count becomes 2)
        r = run_cmd(["check", "--data-dir", tmpdir, "--meal", "lunch", "--weekday", "2"])
        check(r["action"] == "ask", "flow: 2nd check → still ask")
        check(r["ask_count"] == 2, "flow: ask_count=2")

        # Third check (ask_count becomes 3, last chance)
        r = run_cmd(["check", "--data-dir", tmpdir, "--meal", "lunch", "--weekday", "3"])
        check(r["action"] == "ask", "flow: 3rd check → still ask")
        check(r["ask_count"] == 3, "flow: ask_count=3")

        # User replies this time
        run_cmd(["save-place", "--data-dir", tmpdir, "--meal", "lunch", "--place", "cafeteria"])

        # Fourth check: collected (place is set), no more asking
        r = run_cmd(["check", "--data-dir", tmpdir, "--meal", "lunch", "--weekday", "4"])
        check(r["action"] == "none", "flow: after save → no ask")
    finally:
        shutil.rmtree(tmpdir)


def test_full_giveup_flow():
    """End-to-end: 3 checks without reply → gave up → never ask again."""
    tmpdir = tempfile.mkdtemp()
    try:
        # 3 checks auto-increment to ask_count=3
        for _ in range(3):
            run_cmd(["check", "--data-dir", tmpdir, "--meal", "dinner", "--weekday", "0"])

        # 4th check: gave up
        r = run_cmd(["check", "--data-dir", tmpdir, "--meal", "dinner", "--weekday", "4"])
        check(r["action"] == "skip", "giveup flow: skip after 3")
        check(r["reason"] == "gave_up", "giveup flow: reason=gave_up")

        # Even on another workday, still gave up
        r = run_cmd(["check", "--data-dir", tmpdir, "--meal", "dinner", "--weekday", "0"])
        check(r["action"] == "skip", "giveup flow: still skip on different day")
    finally:
        shutil.rmtree(tmpdir)


def test_full_drift_flow():
    """End-to-end: save → 3 drifts → confirm → update → no drift."""
    tmpdir = tempfile.mkdtemp()
    try:
        run_cmd(["save-place", "--data-dir", tmpdir, "--meal", "lunch", "--place", "cafeteria"])

        # 3 consecutive mismatches
        for _ in range(3):
            run_cmd(["record-drift", "--data-dir", tmpdir, "--meal", "lunch",
                      "--inferred", "takeout"])

        # Check shows drift_confirm
        r = run_cmd(["check", "--data-dir", tmpdir, "--meal", "lunch", "--weekday", "2"])
        check(r["action"] == "drift_confirm", "drift flow: confirm triggered")

        # User confirms the change
        run_cmd(["save-place", "--data-dir", tmpdir, "--meal", "lunch", "--place", "takeout"])

        # Check: no drift, place updated
        r = run_cmd(["check", "--data-dir", tmpdir, "--meal", "lunch", "--weekday", "2"])
        check(r["action"] == "none", "drift flow: resolved after update")

        # Verify the place was updated
        r = run_cmd(["load", "--data-dir", tmpdir])
        check(r["workday_meal_place_profile"]["lunch"]["place"] == "takeout",
              "drift flow: place updated to takeout")
    finally:
        shutil.rmtree(tmpdir)


def test_drift_denied_flow():
    """End-to-end: 3 drifts → user denies → reset → no more confirm."""
    tmpdir = tempfile.mkdtemp()
    try:
        run_cmd(["save-place", "--data-dir", tmpdir, "--meal", "lunch", "--place", "cafeteria"])
        for _ in range(3):
            run_cmd(["record-drift", "--data-dir", tmpdir, "--meal", "lunch",
                      "--inferred", "takeout"])

        # User denies change → reset drift
        run_cmd(["reset-drift", "--data-dir", tmpdir, "--meal", "lunch"])

        r = run_cmd(["check", "--data-dir", tmpdir, "--meal", "lunch", "--weekday", "3"])
        check(r["action"] == "none", "denied flow: no confirm after reset")

        # Place unchanged
        r = run_cmd(["load", "--data-dir", tmpdir])
        check(r["workday_meal_place_profile"]["lunch"]["place"] == "cafeteria",
              "denied flow: place unchanged")
    finally:
        shutil.rmtree(tmpdir)


# ---------------------------------------------------------------------------
# CROSS-MEAL independence
# ---------------------------------------------------------------------------

def test_meals_independent():
    """Each meal's state is independent of others."""
    tmpdir = tempfile.mkdtemp()
    try:
        run_cmd(["save-place", "--data-dir", tmpdir, "--meal", "breakfast", "--place", "home"])
        # Exhaust dinner's 3 checks
        for _ in range(3):
            run_cmd(["check", "--data-dir", tmpdir, "--meal", "dinner", "--weekday", "0"])

        # Breakfast: collected (place set)
        r = run_cmd(["check", "--data-dir", tmpdir, "--meal", "breakfast", "--weekday", "1"])
        check(r["action"] == "none", "independence: breakfast collected")

        # Lunch: still needs asking (untouched)
        r = run_cmd(["check", "--data-dir", tmpdir, "--meal", "lunch", "--weekday", "1"])
        check(r["action"] == "ask", "independence: lunch still asks")

        # Dinner: gave up (3 checks exhausted)
        r = run_cmd(["check", "--data-dir", tmpdir, "--meal", "dinner", "--weekday", "1"])
        check(r["action"] == "skip", "independence: dinner gave up")
    finally:
        shutil.rmtree(tmpdir)


# ---------------------------------------------------------------------------
# Run all tests
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        name = t.__name__
        print(f"▶ {name}")
        try:
            t()
        except Exception as e:
            failed += 1
            errors.append(f"{name}: {e}")
            print(f"  ERROR: {e}")

    print(f"\n{'=' * 50}")
    print(f"Passed: {passed}  Failed: {failed}")
    if errors:
        print("\nFailures:")
        for e in errors:
            print(f"  ✗ {e}")
        sys.exit(1)
    else:
        print("All tests passed ✓")
