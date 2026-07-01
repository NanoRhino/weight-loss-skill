#!/usr/bin/env python3
# /// script
# requires-python = ">=3.6"
# dependencies = []
# ///
"""Self-tests for planner-calc.py `write-plan-json` / build_plan_json.

No test framework repo-wide — run directly on bare python3:
    python3 test_plan_json.py

Asserts the exact plan.json schema, that the numbers reuse the existing
forward/reverse math (deficit = tdee_base - target = rate * 1100 pre-clamp),
and that the safety floor clamps the realized rate.
"""

from __future__ import annotations

import importlib.util
import json
import os
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "planner_calc", os.path.join(_HERE, "planner-calc.py"))
pc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pc)

SCHEMA_KEYS = {
    "tdee_base", "bmr", "activity_level", "activity_multiplier",
    "daily_calorie_target", "daily_deficit", "goal", "weekly_rate_kg",
    "updated_at", "source",
}

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


def test_schema_and_types():
    print("test_schema_and_types:")
    p = pc.build_plan_json(85, 178, 35, "male", "lightly_active", 70,
                           "2026-07-01T12:00:00Z")
    check("exact schema keys", set(p.keys()) == SCHEMA_KEYS,
          set(p.keys()) ^ SCHEMA_KEYS)
    check("tdee_base int", isinstance(p["tdee_base"], int), p)
    check("bmr int", isinstance(p["bmr"], int), p)
    check("target int", isinstance(p["daily_calorie_target"], int), p)
    check("deficit int", isinstance(p["daily_deficit"], int), p)
    check("multiplier float", isinstance(p["activity_multiplier"], float), p)
    check("rate float", isinstance(p["weekly_rate_kg"], float), p)
    check("updated_at echoed", p["updated_at"] == "2026-07-01T12:00:00Z", p)
    check("source default", p["source"] == "planner-calc", p)
    check("goal default lose_fat", p["goal"] == "lose_fat", p)
    check("activity level echoed", p["activity_level"] == "lightly_active", p)


def test_deficit_identity():
    print("test_deficit_identity (deficit == tdee_base - target):")
    p = pc.build_plan_json(85, 178, 35, "male", "lightly_active", 70,
                           "2026-07-01T12:00:00Z")
    check("deficit == tdee_base - target",
          p["daily_deficit"] == p["tdee_base"] - p["daily_calorie_target"], p)
    # forward-calc default rate for 15 kg to lose is 0.6 kg/wk → deficit ~660
    check("deficit ~= rate*1100", abs(p["daily_deficit"] - round(0.6 * 1100)) <= 1, p)
    check("weekly_rate 0.6", p["weekly_rate_kg"] == 0.6, p)


def test_explicit_rate():
    print("test_explicit_rate:")
    p = pc.build_plan_json(85, 178, 35, "male", "lightly_active", 70,
                           "2026-07-01T12:00:00Z", rate_kg=0.44)
    check("rate honored", p["weekly_rate_kg"] == 0.44, p)
    check("deficit == 0.44*1100", p["daily_deficit"] == round(0.44 * 1100), p)


def test_floor_clamp():
    print("test_floor_clamp (aggressive rate clamps to BMR floor):")
    # small woman, sedentary, aggressive 1.0 kg/wk → target would fall below BMR
    p = pc.build_plan_json(55, 160, 30, "female", "sedentary", 50,
                           "2026-07-01T12:00:00Z", rate_kg=1.0)
    check("target >= bmr floor", p["daily_calorie_target"] >= p["bmr"], p)
    check("realized rate reduced below 1.0", p["weekly_rate_kg"] < 1.0, p)


def test_source_and_deadline():
    print("test_source_and_deadline:")
    p = pc.build_plan_json(85, 178, 35, "male", "lightly_active", 70,
                           "2026-07-01T12:00:00Z", source="handoff",
                           deadline="2027-01-01")
    check("source handoff", p["source"] == "handoff", p)
    check("has target", p["daily_calorie_target"] > 0, p)
    check("has positive rate", p["weekly_rate_kg"] > 0, p)


def test_write_roundtrip():
    print("test_write_roundtrip (file written + parses):")
    with tempfile.TemporaryDirectory() as tmp:
        p = pc.build_plan_json(85, 178, 35, "male", "lightly_active", 70,
                               "2026-07-01T12:00:00Z")
        path = pc.write_plan_json(tmp, p)
        check("file exists", os.path.exists(path), path)
        with open(path, encoding="utf-8") as f:
            loaded = json.load(f)
        check("roundtrip equal", loaded == p, (loaded, p))


def main():
    for t in (test_schema_and_types, test_deficit_identity, test_explicit_rate,
              test_floor_clamp, test_source_and_deadline, test_write_roundtrip):
        t()
    print("\n{} passed, {} failed".format(_passed, _failed))
    raise SystemExit(1 if _failed else 0)


if __name__ == "__main__":
    main()
