# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""
Deterministic tests for the edit-reconciliation + dedup helpers added to
nutrition-calc.py (Bug A: edits leave the log inconsistent; Bug B: duplicate
photo auto-logged as a second meal).

Pure arithmetic — no LLM, no network, no fixtures on disk. Run with bare
python3 (prod is 3.9; this file is 3.9-clean):

    python3 diet-tracking-analysis/tests/test_edit_reconcile.py

Exit 0 = all pass, exit 1 = a failure (with a diff printed).
"""
from __future__ import annotations

import importlib.util
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_NC_PATH = os.path.join(_HERE, "..", "scripts", "nutrition-calc.py")

_spec = importlib.util.spec_from_file_location("nutrition_calc", _NC_PATH)
nc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(nc)

_failures = []


def check(label, got, want):
    if got == want:
        print("  PASS  " + label)
    else:
        print("  FAIL  " + label)
        print("        got : " + repr(got))
        print("        want: " + repr(want))
        _failures.append(label)


def approx(label, got, want, tol=0.05):
    if abs(got - want) <= tol:
        print("  PASS  " + label)
    else:
        print("  FAIL  " + label + " got=" + repr(got) + " want~=" + repr(want))
        _failures.append(label)


# ---------------------------------------------------------------------------
# Bug A.1 — calories-only edit rescales macros (preserve ratio)
# ---------------------------------------------------------------------------
# Real case: "Update that protein bowl to 30 calories" left "30 kcal / 60.1g
# protein" (60g protein alone is ~240 kcal — impossible). After the fix the
# macros rescale down so 4P+4C+9F lands on 30.
print("Bug A.1 — calories-only edit (rescale macros to pinned kcal):")
r = nc.rescale_to_calories(protein=60.0, carbs=5.0, fat=3.0, pinned_calories=30.0)
check("calories pinned to 30", r["calories"], 30)
# 4P+4C+9F must now equal ~30 (the row is internally consistent)
implied = 4 * r["protein_g"] + 4 * r["carbs_g"] + 9 * r["fat_g"]
approx("rescaled macros satisfy 4P+4C+9F == 30", implied, 30.0, tol=1.0)
check("no impossibility flag on rescale path", r["flag"], None)
# Ratio preservation is checked at a larger pinned value where 1-decimal
# rounding doesn't distort it: pin 120 kcal (factor 0.5) on 60/5/3 → 30/2.5/1.5,
# P:C stays exactly 60:5 == 12:1.
r_big = nc.rescale_to_calories(protein=60.0, carbs=5.0, fat=3.0, pinned_calories=120.0)
approx("P:C ratio preserved (12:1)", r_big["protein_g"] / r_big["carbs_g"], 12.0, tol=0.05)

# Alternative strategy: user pins kcal but insists macros stay locked → flag,
# do not silently persist the impossible row.
print("Bug A.1 — pin-kcal-keep-macros (flag impossible instead of persisting):")
p = nc.pin_calories_keep_macros(protein=60.0, carbs=5.0, fat=3.0, pinned_calories=30.0)
check("flagged impossible", p["impossible"], True)
check("min_calories surfaced (4*60+4*5+9*3)", p["min_calories"], 287)
# a consistent pin (>= floor) is NOT flagged
p2 = nc.pin_calories_keep_macros(protein=10.0, carbs=10.0, fat=2.0, pinned_calories=100.0)
check("consistent pin not flagged", p2["impossible"], False)

# ---------------------------------------------------------------------------
# Bug A.2 — quantity edit recomputes kcal AND macros from per-unit values
# ---------------------------------------------------------------------------
# Real case: photo logged as "whole box — 600 kcal"; user says "5 slices".
# Old behavior kept 600 kcal. Box was ~12 slices, so 5 slices ~= 250 kcal.
print("Bug A.2 — quantity edit (recompute from per-unit x new quantity):")
row = {"name": "pizza", "calories": 600, "protein_g": 24.0, "carbs_g": 72.0,
       "fat_g": 24.0, "total_g": 600, "quantity": 12}
q = nc.recompute_quantity(row, new_quantity=5)
check("kcal recomputed (600/12*5)", q["calories"], 250)
check("protein recomputed (24/12*5)", q["protein_g"], 10.0)
check("carbs recomputed (72/12*5)", q["carbs_g"], 30.0)
check("fat recomputed (24/12*5)", q["fat_g"], 10.0)
check("weight recomputed (600/12*5)", q["total_g"], 250)
check("quantity updated", q["quantity"], 5)
# kcal no longer retains the whole-box number
check("kcal is NOT the stale 600", q["calories"] != 600, True)

# ---------------------------------------------------------------------------
# Bug A.3 — a single food must not be double-categorized
# ---------------------------------------------------------------------------
print("Bug A.3 — double-category guard:")
log = [
    {"name": "lunch", "foods": [{"name": "Grilled Chicken"}, {"name": "rice"}]},
    {"name": "snack", "foods": [{"name": "grilled chicken"}]},
]
d = nc.find_cross_category_dupes(log, meals=3)
check("dupe detected", d["has_cross_category_dupes"], True)
check("the right food flagged (case-insensitive)", d["dupes"][0]["food"], "grilled chicken")
check("both slots reported", d["dupes"][0]["slots"], ["lunch", "snack"])
# clean log → no false positive
clean = [
    {"name": "lunch", "foods": [{"name": "chicken"}]},
    {"name": "snack", "foods": [{"name": "apple"}]},
]
check("clean log not flagged", nc.find_cross_category_dupes(clean)["has_cross_category_dupes"], False)

# ---------------------------------------------------------------------------
# Bug B — duplicate / re-sent photo is a CANDIDATE duplicate (confirm, don't auto-add)
# ---------------------------------------------------------------------------
print("Bug B — candidate-duplicate photo detection:")
recent = [{"name": "lunch", "calories": 500, "logged_at": "2026-06-27T12:00:00Z"}]
# re-sent photo ~520 kcal, 3 min after a 500 kcal lunch → candidate duplicate
dup = nc.detect_duplicate({"calories": 520}, recent, now_iso="2026-06-27T12:03:00Z")
check("near-identical recent meal flagged", dup["is_candidate_duplicate"], True)
check("match names the prior meal", dup["match"]["name"], "lunch")
# a genuinely different meal is NOT a duplicate
diff_meal = nc.detect_duplicate({"calories": 900}, recent, now_iso="2026-06-27T12:03:00Z")
check("different calories not flagged", diff_meal["is_candidate_duplicate"], False)
# same calories but outside the window is NOT a duplicate (real second helping later)
late = nc.detect_duplicate({"calories": 520}, recent, now_iso="2026-06-27T12:40:00Z")
check("outside time window not flagged", late["is_candidate_duplicate"], False)
# no timestamp on the prior meal → cannot age-gate → not flagged (fail open to log)
no_ts = nc.detect_duplicate({"calories": 520}, [{"name": "lunch", "calories": 500}],
                            now_iso="2026-06-27T12:03:00Z")
check("missing timestamp not flagged", no_ts["is_candidate_duplicate"], False)

# ---------------------------------------------------------------------------
# Regression — verify_meal (new-log reconciliation) unchanged: snap kcal to 4P+4C+9F
# ---------------------------------------------------------------------------
print("Regression — verify_meal still snaps a fresh log to the Atwater identity:")
vm = nc.verify_meal([{"dish_name": "bowl", "ingredients": [
    {"name": "chicken", "amount_g": 150, "calories": 999,
     "protein_g": 30, "carbs_g": 0, "fat_g": 3}]}])
check("fresh-log kcal snapped to 4*30+9*3=147", vm["meal_total"]["calories"], 147)
check("a correction was recorded", len(vm["corrections"]), 1)

print("")
if _failures:
    print("RESULT: {} FAILED".format(len(_failures)))
    for f in _failures:
        print("  - " + f)
    sys.exit(1)
print("RESULT: ALL PASS")
sys.exit(0)
