#!/usr/bin/env python3
# /// script
# requires-python = ">=3.6"
# dependencies = []
# ///
"""Self-tests for the body-weight-scaled loss-rate offer (planner-calc.py).

No test framework repo-wide — run directly on bare python3:
    python3 test_rate_offer.py

Covers the >25 kg-to-lose bucket raising its ceiling + default to 1%/week of
body weight, while the max(BMR, 1000) calorie floor stays the HARD limit — so a
high-TDEE user speeds up and a low-TDEE (floor-bound) user is unchanged.
"""

from __future__ import annotations

import importlib.util
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "planner_calc", os.path.join(_HERE, "planner-calc.py"))
pc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pc)

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


def test_offer_ceiling_scales_with_body_weight():
    print("test_offer_ceiling_scales_with_body_weight:")
    # >25 kg bucket, no body weight → historical cap (default 0.7, high 1.0).
    r = pc.recommend_rate(60)
    check("no-bw default 0.7", r["rate_default_kg"] == 0.7, r)
    check("no-bw high 1.0", r["rate_high_kg"] == 1.0, r)
    # 136 kg (~300 lb) body → 1% = 1.36 kg/wk offered as both high + default.
    r = pc.recommend_rate(60, body_weight_kg=136)
    check("heavy default 1.36", r["rate_default_kg"] == 1.36, r)
    check("heavy high 1.36", r["rate_high_kg"] == 1.36, r)
    # A lighter >25-bucket body (85 kg) → 1% = 0.85, never below the old 0.7
    # default or the 1.0 high.
    r = pc.recommend_rate(30, body_weight_kg=85)
    check("85kg default 0.85", r["rate_default_kg"] == 0.85, r)
    check("85kg high stays 1.0", r["rate_high_kg"] == 1.0, r)


def test_smaller_buckets_untouched():
    print("test_smaller_buckets_untouched (only the >25 kg bucket scales):")
    r = pc.recommend_rate(15, body_weight_kg=136)   # 10-25 bucket
    check("10-25 default still 0.6", r["rate_default_kg"] == 0.6, r)
    check("10-25 high still 0.7", r["rate_high_kg"] == 0.7, r)
    r = pc.recommend_rate(5, body_weight_kg=136)     # <10 bucket
    check("<10 default still 0.35", r["rate_default_kg"] == 0.35, r)


def test_high_tdee_user_speeds_up():
    print("test_high_tdee_user_speeds_up (300 lb, real TDEE headroom):")
    # 136 kg -> 90 kg, 178 cm male 40, moderately_active.
    d = pc.forward_calc(136, 178, 40, "male", "moderately_active", 90)
    check("realized rate > old 0.7 cap", d["rate_kg_per_week"] > 0.7, d)
    # Floor still clamps below the raw 1.36 offer (real headroom, not infinite).
    check("realized rate <= 1% offer (1.36)", d["rate_kg_per_week"] <= 1.36, d)
    check("daily_cal at/above floor", d["daily_cal"] >= d["calorie_floor"], d)


def test_low_tdee_user_unchanged():
    print("test_low_tdee_user_unchanged (floor binds → same as old 0.7):")
    # 92 kg -> 60 kg small sedentary woman: floor binds under both old and new.
    d = pc.forward_calc(92, 158, 55, "female", "sedentary", 60)
    check("floor clamped", d["floor_clamped"] is True, d)
    check("daily_cal == floor", d["daily_cal"] == d["calorie_floor"], d)
    # Realized rate is purely floor-derived: (tdee - floor) / 1100 — identical
    # regardless of the offered rate, so raising the offer does NOT speed them up.
    tdee = d["tdee"]["tdee"]
    expected = round((tdee - d["calorie_floor"]) / 1100, 2)
    check("realized rate is floor-derived", d["rate_kg_per_week"] == expected,
          (d["rate_kg_per_week"], expected))


def test_reverse_calc_ceiling_scales():
    print("test_reverse_calc_ceiling_scales (aggressive deadline, heavy user):")
    # Heavy user, tight deadline needing ~1.2 kg/wk: now within offer for 136 kg
    # (1% = 1.36), so it is flagged safe rather than capped at the old 1.0.
    d = pc.reverse_calc(136, 178, 40, "male", "moderately_active", 90,
                        deadline="2027-07-01")
    check("required rate present", d["required_rate_kg"] > 0, d)
    if d["required_rate_kg"] <= 1.36:
        check("within 1% offer → rate_safe true", d["rate_safe"] is True, d)


def main():
    for t in (test_offer_ceiling_scales_with_body_weight,
              test_smaller_buckets_untouched,
              test_high_tdee_user_speeds_up,
              test_low_tdee_user_unchanged,
              test_reverse_calc_ceiling_scales):
        t()
    print("\n{} passed, {} failed".format(_passed, _failed))
    raise SystemExit(1 if _failed else 0)


if __name__ == "__main__":
    main()
