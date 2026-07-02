"""habit-builder 单测:phase 判定 + 时间规则解析。

覆盖:
- action-pipeline get_phase:0-7 anchor / 8-21 build / 22+ solidify;strict 模式 anchor 到 14
- bootstrap-habit time_add_minutes:HH:MM + 分钟 clamp
- bootstrap-habit resolve_timing:before/after first/last meal + fixed
"""
import importlib.util
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parent.parent / "habit-builder" / "scripts"

def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

pipeline = _load("action_pipeline", SKILL / "action-pipeline.py")
bootstrap = _load("bootstrap_habit", SKILL / "bootstrap-habit.py")


class TestGetPhase:
    def test_day_0_anchor(self):
        assert pipeline.get_phase(0) == "anchor"

    def test_day_7_edge_anchor(self):
        assert pipeline.get_phase(7) == "anchor"

    def test_day_8_build(self):
        assert pipeline.get_phase(8) == "build"

    def test_day_21_edge_build(self):
        assert pipeline.get_phase(21) == "build"

    def test_day_22_solidify(self):
        assert pipeline.get_phase(22) == "solidify"

    def test_day_100_solidify(self):
        assert pipeline.get_phase(100) == "solidify"

    def test_strict_extends_anchor_to_14(self):
        # 严格模式 anchor 延到 14 天(weight-gain pact)
        assert pipeline.get_phase(10, strict=True) == "anchor"
        assert pipeline.get_phase(14, strict=True) == "anchor"

    def test_strict_after_14_normal_logic(self):
        # 15 天后走正常 boundaries
        assert pipeline.get_phase(15, strict=True) == "build"


class TestTimeAddMinutes:
    def test_normal_add(self):
        assert bootstrap.time_add_minutes("08:00", 30) == "08:30"

    def test_cross_hour(self):
        assert bootstrap.time_add_minutes("08:45", 30) == "09:15"

    def test_negative_offset(self):
        # 减 30 分
        assert bootstrap.time_add_minutes("08:00", -30) == "07:30"

    def test_clamp_below_zero(self):
        # 00:00 - 60 → clamp 到 00:00
        assert bootstrap.time_add_minutes("00:00", -60) == "00:00"

    def test_clamp_above_2359(self):
        # 23:00 + 120 = 25:00 → clamp 到 23:59
        assert bootstrap.time_add_minutes("23:00", 120) == "23:59"


class TestResolveTiming:
    @pytest.fixture
    def meal_times(self):
        return [
            {"name": "breakfast", "time": "08:00"},
            {"name": "lunch", "time": "12:00"},
            {"name": "dinner", "time": "18:00"},
        ]

    def test_fixed(self, meal_times):
        assert bootstrap.resolve_timing("fixed:09:30", meal_times) == "09:30"

    def test_before_first_meal(self, meal_times):
        # breakfast 08:00 - 30 = 07:30
        assert bootstrap.resolve_timing("before_first_meal:-30", meal_times) == "07:30"

    def test_after_first_meal(self, meal_times):
        # breakfast 08:00 + 60 = 09:00
        assert bootstrap.resolve_timing("after_first_meal:60", meal_times) == "09:00"

    def test_before_last_meal(self, meal_times):
        # dinner 18:00 - 30 = 17:30
        assert bootstrap.resolve_timing("before_last_meal:-30", meal_times) == "17:30"

    def test_after_last_meal(self, meal_times):
        # dinner 18:00 + 60 = 19:00
        assert bootstrap.resolve_timing("after_last_meal:60", meal_times) == "19:00"

    def test_unknown_rule_fallback_9am(self, meal_times):
        assert bootstrap.resolve_timing("not_a_rule", meal_times) == "09:00"

    def test_no_meal_times_default_used(self):
        # 空 meal_times → 走默认(breakfast 08:00 first)
        assert bootstrap.resolve_timing("before_first_meal:-30", []) == "07:30"
