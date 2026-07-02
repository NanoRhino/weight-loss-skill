"""weight-loss-planner/scripts/planner-calc.py 单测。

跟 miniprogram_backend/app/plan_calc.py 是**同一套公式**的两处实现
(audit 模式和 agent 模式对齐)。这里保护 skill 侧不 drift。

覆盖:BMI/BMR/TDEE/rate/floor + WHO vs Asian BMI 标准。
"""
import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "weight-loss-planner" / "scripts" / "planner-calc.py"
spec = importlib.util.spec_from_file_location("planner_calc", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class TestBMI:
    def test_calc_bmi(self):
        assert mod.calc_bmi(60, 170) == 20.8

    def test_classify_who_normal(self):
        # WHO 标准 [18.5, 25.0) = Normal
        assert mod.classify_bmi(22.0, "who") == "Normal weight"

    def test_classify_who_overweight(self):
        assert mod.classify_bmi(27.0, "who") == "Overweight"

    def test_classify_asian_overweight_earlier(self):
        # 亚洲标准 24 就算 Overweight,WHO 25 才算
        assert mod.classify_bmi(24.5, "asian") == "Overweight"
        assert mod.classify_bmi(24.5, "who") == "Normal weight"

    def test_default_is_who(self):
        # 默认走 WHO
        assert mod.classify_bmi(24.5) == "Normal weight"


class TestBMR:
    def test_mifflin_male(self):
        # 10*70 + 6.25*175 - 5*30 + 5 = 1648.75
        assert mod.calc_bmr_mifflin(70, 175, 30, "male") == 1648.8

    def test_mifflin_female(self):
        # -161 而非 +5
        assert mod.calc_bmr_mifflin(55, 165, 28, "female") == 1280.2

    def test_katch_high_bf(self):
        # 60kg, 30% BF → LBM=42, BMR = 370 + 21.6*42 = 1277.2
        assert mod.calc_bmr_katch(60, 30) == 1277.2

    def test_katch_low_bf(self):
        # 60kg, 10% BF → LBM=54, BMR = 370 + 21.6*54 = 1536.4
        assert mod.calc_bmr_katch(60, 10) == 1536.4


class TestTDEE:
    def test_sedentary(self):
        result = mod.calc_tdee(1500, "sedentary")
        assert result["tdee"] == 1800  # 1500 * 1.2
        assert result["multiplier"] == 1.2

    def test_very_active(self):
        result = mod.calc_tdee(1500, "very_active")
        assert result["tdee"] == round(1500 * 1.725)

    def test_unknown_activity_fallback_sedentary(self):
        # 未知 activity 兜底 1.2
        result = mod.calc_tdee(1500, "made_up_level")
        assert result["multiplier"] == 1.2

    def test_range_returned(self):
        result = mod.calc_tdee(1500, "sedentary")
        assert result["tdee_low"] == result["tdee"] - 100
        assert result["tdee_high"] == result["tdee"] + 100


class TestSafetyFloor:
    def test_bmr_above_min(self):
        assert mod.calc_safety_floor(1400) == 1400

    def test_bmr_below_min_clamp(self):
        # 极低 BMR 也要保底 1000
        assert mod.calc_safety_floor(800) == 1000

    def test_bmr_at_edge(self):
        assert mod.calc_safety_floor(1000) == 1000


class TestRecommendRate:
    def test_small_loss(self):
        r = mod.recommend_rate(5)
        assert r["rate_default_kg"] == 0.35
        assert r["rate_low_kg"] == 0.2
        assert r["rate_high_kg"] == 0.5

    def test_medium_loss(self):
        r = mod.recommend_rate(15)
        assert r["rate_default_kg"] == 0.6

    def test_large_loss(self):
        r = mod.recommend_rate(30)
        assert r["rate_default_kg"] == 0.7

    def test_edge_10(self):
        assert mod.recommend_rate(10)["rate_default_kg"] == 0.6

    def test_edge_25(self):
        assert mod.recommend_rate(25)["rate_default_kg"] == 0.7

    def test_lbs_conversion(self):
        r = mod.recommend_rate(5)
        # 0.35 kg ≈ 0.77 lb
        assert 0.7 <= r["rate_default_lbs"] <= 0.8


class TestUnitConvert:
    def test_lbs_to_kg(self):
        r = mod.unit_convert(100, "lbs", "kg")
        assert 45.3 <= r["result"] <= 45.4

    def test_kg_to_lbs(self):
        r = mod.unit_convert(60, "kg", "lbs")
        assert 132.2 <= r["result"] <= 132.4

    def test_in_to_cm(self):
        r = mod.unit_convert(70, "in", "cm")
        # 70 in * 2.54 = 177.8
        assert r["result"] == 177.8

    def test_unsupported_returns_error(self):
        r = mod.unit_convert(1, "kg", "cm")
        assert "error" in r
