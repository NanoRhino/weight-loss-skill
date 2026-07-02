"""weight-gain-strategy/scripts/analyze-weight-trend.py 单测。

覆盖 meal calories 提取 / meal type 抽取 / 样本质量门槛(nutrition 分析基础)。
这几个纯函数是趋势分析的输入 pipeline,错了下游全错。
"""
import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "weight-gain-strategy" / "scripts" / "analyze-weight-trend.py"
spec = importlib.util.spec_from_file_location("trend", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class TestGetMealCalories:
    def test_meal_level_cal(self):
        assert mod.get_meal_calories({"cal": 500}) == 500

    def test_meal_level_calories(self):
        assert mod.get_meal_calories({"calories": 500}) == 500

    def test_falls_back_to_foods_sum(self):
        meal = {"foods": [{"calories": 200}, {"calories": 150}]}
        assert mod.get_meal_calories(meal) == 350

    def test_falls_back_to_items(self):
        meal = {"items": [{"calories": 100}, {"calories": 100}]}
        assert mod.get_meal_calories(meal) == 200

    def test_not_dict_returns_zero(self):
        assert mod.get_meal_calories("string") == 0
        assert mod.get_meal_calories(None) == 0

    def test_empty_dict(self):
        assert mod.get_meal_calories({}) == 0

    def test_zero_cal_with_food_fallback(self):
        """cal=0 也走 foods 兜底"""
        meal = {"cal": 0, "foods": [{"calories": 100}]}
        assert mod.get_meal_calories(meal) == 100

    def test_skip_non_dict_foods(self):
        # foods 里有非 dict 项要跳过
        meal = {"foods": [{"calories": 100}, "invalid", None, {"calories": 50}]}
        assert mod.get_meal_calories(meal) == 150


class TestExtractMealTypesFromDay:
    def test_dict_of_meal_types(self):
        day = {
            "breakfast": {"calories": 300},
            "lunch": {"calories": 600},
            "dinner": {"calories": 500},
        }
        result = mod._extract_meal_types_from_day(day)
        assert result["breakfast"] == 300
        assert result["lunch"] == 600
        assert result["dinner"] == 500

    def test_skips_below_50_kcal(self):
        # 5 kcal 太少不算一餐
        day = {"breakfast": {"calories": 30}, "lunch": {"calories": 600}}
        result = mod._extract_meal_types_from_day(day)
        assert "breakfast" not in result
        assert result["lunch"] == 600

    def test_list_of_meals(self):
        # 内部按 meal_type 或 type 字段查
        day = [
            {"meal_type": "breakfast", "calories": 300},
            {"meal_type": "lunch", "calories": 500},
        ]
        result = mod._extract_meal_types_from_day(day)
        assert result.get("breakfast") == 300
        assert result.get("lunch") == 500

    def test_meals_wrapped_field(self):
        day = {"meals": [{"meal_type": "breakfast", "calories": 300}]}
        result = mod._extract_meal_types_from_day(day)
        assert result.get("breakfast") == 300

    def test_empty(self):
        assert mod._extract_meal_types_from_day({}) == {}
        assert mod._extract_meal_types_from_day([]) == {}


class TestMealAvgQualityGated:
    def test_insufficient_samples(self):
        r = mod._meal_avg_quality_gated([500, 600])
        assert r["ok"] is False
        assert r["reason"] == "insufficient_samples"

    def test_zero_mean_rejected(self):
        r = mod._meal_avg_quality_gated([0, 0, 0])
        assert r["ok"] is False

    def test_valid_samples(self):
        r = mod._meal_avg_quality_gated([500, 600, 550, 580, 520])
        assert r["ok"] is True
        assert 500 <= r["avg"] <= 600
        assert r["n"] == 5

    def test_cv_included(self):
        """稳定用户 CV 低,波动大 CV 高"""
        stable = mod._meal_avg_quality_gated([500, 500, 500, 500])
        assert stable["cv"] == 0.0

        chaotic = mod._meal_avg_quality_gated([100, 1000, 200, 900])
        assert chaotic["cv"] > 0.5
