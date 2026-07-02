"""diet-tracking-analysis/scripts/nutrition-calc.py 单测。

覆盖 meal 归一化 / 营养素累加 / 目标计算 / block 结构。之前踩过 skip 逻辑
的坑([[meal-skip-no-assume]]),回归价值高。
"""
import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "diet-tracking-analysis" / "scripts" / "nutrition-calc.py"
spec = importlib.util.spec_from_file_location("nutrition_calc", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class TestRangeStatus:
    def test_low(self):
        assert mod._range_status(80, 100, 200) == "low"

    def test_on_track(self):
        assert mod._range_status(150, 100, 200) == "on_track"

    def test_high(self):
        assert mod._range_status(250, 100, 200) == "high"

    def test_edge_lo(self):
        assert mod._range_status(100, 100, 200) == "on_track"

    def test_edge_hi(self):
        assert mod._range_status(200, 100, 200) == "on_track"

    def test_just_above_hi(self):
        assert mod._range_status(201, 100, 200) == "high"


class TestSumMacros:
    def test_empty(self):
        r = mod._sum_macros([])
        assert r == {"calories": 0, "protein": 0, "carbs": 0, "fat": 0}

    def test_single_meal(self):
        r = mod._sum_macros([{"calories": 500, "protein": 30, "carbs": 60, "fat": 15}])
        assert r["calories"] == 500
        assert r["protein"] == 30

    def test_missing_fields_default_zero(self):
        r = mod._sum_macros([{"calories": 500}])  # 无 protein/carbs/fat
        assert r["calories"] == 500
        assert r["protein"] == 0

    def test_multi_meal_sum(self):
        r = mod._sum_macros([
            {"calories": 500, "protein": 30, "carbs": 60, "fat": 15},
            {"calories": 300, "protein": 20, "carbs": 40, "fat": 10},
        ])
        assert r["calories"] == 800
        assert r["protein"] == 50


class TestMigrateMeal:
    def test_items_to_foods(self):
        """新 schema items → 老 schema foods 兼容"""
        m = mod._migrate_meal({"items": [{"name": "苹果", "calories": 50}]})
        assert "foods" in m
        assert "items" not in m
        assert m["foods"][0]["calories"] == 50

    def test_short_keys(self):
        """短 key(cal)→ 长 key(calories)"""
        m = mod._migrate_meal({"cal": 500, "meal_name": "breakfast"})
        assert m["calories"] == 500

    def test_g_suffix_stripped(self):
        """protein_g → protein 之类"""
        m = mod._migrate_meal({"protein_g": 30, "carbs_g": 60, "fat_g": 15})
        assert m["protein"] == 30
        assert m["carbs"] == 60
        assert m["fat"] == 15


class TestGetMealBlocks:
    def test_3_meals_default(self):
        blocks = mod.get_meal_blocks(3)
        labels = [b["label"] for b in blocks]
        assert labels == ["breakfast", "lunch", "dinner"]
        # 百分比之和 100
        assert sum(b["pct"] for b in blocks) == 100

    def test_2_meals_default(self):
        blocks = mod.get_meal_blocks(2)
        assert len(blocks) == 2
        assert sum(b["pct"] for b in blocks) == 100

    def test_2_meals_with_schedule(self):
        """schedule 里给标准 meal keys 会推断 label"""
        # 2 餐用户吃 breakfast + dinner(跳午),schedule value 是 HH:MM 字符串
        blocks = mod.get_meal_blocks(2, schedule={"breakfast": "09:00", "dinner": "18:00"})
        labels = [b["label"] for b in blocks]
        assert "breakfast" in labels
        assert "dinner" in labels


class TestCalcTargets:
    def test_balanced_mode(self):
        t = mod.calc_targets(weight=70, daily_cal=1500, meals=3, mode="balanced")
        # 蛋白 = 70 * 1.4 = 98g(mid)
        assert t["protein"]["target"] == 98.0
        # calories 应等于目标
        assert t["daily_calories"] == 1500

    def test_high_protein_gives_more_protein(self):
        balanced = mod.calc_targets(weight=70, daily_cal=1500, mode="balanced")
        hp = mod.calc_targets(weight=70, daily_cal=1500, mode="high_protein")
        assert hp["protein"]["target"] > balanced["protein"]["target"]

    def test_target_weight_used_for_protein(self):
        """减重场景用 target_weight 算蛋白,避免 protein 目标过高"""
        # 100kg 想减到 70kg,protein 按 70 算
        t = mod.calc_targets(weight=100, daily_cal=1500, target_weight=70)
        # 70 * 1.4 = 98
        assert t["protein"]["target"] == 98.0

    def test_keto_high_fat(self):
        """keto 模式脂肪占比很高"""
        t = mod.calc_targets(weight=70, daily_cal=1500, mode="keto")
        # keto 脂肪 65-75%,mid = 70%
        # fat = 1500 * 70/100 / 9 ≈ 116.7
        assert 110 <= t["fat"]["target"] <= 125
