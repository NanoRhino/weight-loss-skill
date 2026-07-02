"""exercise-tracking/scripts/exercise-calc.py 单测。

MET 插值 + 热量计算是 exercise 核心。插值边界搞错直接给用户错误热量。
"""
import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "exercise-tracking" / "scripts" / "exercise-calc.py"
spec = importlib.util.spec_from_file_location("exercise_calc", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class TestInterpolate:
    def test_below_min_returns_first(self):
        anchors = [(5.0, 6.0), (10.0, 12.0)]
        assert mod.interpolate(3.0, anchors) == 6.0

    def test_above_max_returns_last(self):
        anchors = [(5.0, 6.0), (10.0, 12.0)]
        assert mod.interpolate(15.0, anchors) == 12.0

    def test_at_anchor(self):
        anchors = [(5.0, 6.0), (10.0, 12.0)]
        assert mod.interpolate(5.0, anchors) == 6.0
        assert mod.interpolate(10.0, anchors) == 12.0

    def test_midpoint(self):
        anchors = [(5.0, 6.0), (10.0, 12.0)]
        # 中点 7.5 → MET (6 + 12) / 2 = 9.0
        assert mod.interpolate(7.5, anchors) == 9.0


class TestRunning:
    def test_slow(self):
        r = mod.interpolate_running(6.4)
        assert r["met"] == 6.0
        # 6.4 km/h → 60/6.4 ≈ 9.38 min/km
        assert 9.0 <= r["pace_min_per_km"] <= 9.5

    def test_fast(self):
        r = mod.interpolate_running(13.0)
        assert r["met"] == 12.8

    def test_below_slowest(self):
        r = mod.interpolate_running(5.0)
        # 低于最低锚点,兜底最低 MET
        assert r["met"] == 6.0

    def test_pace_at_zero_speed(self):
        r = mod.interpolate_running(0)
        assert r["pace_min_per_km"] == 0


class TestCycling:
    def test_slow(self):
        r = mod.interpolate_cycling(16.0)
        assert r["met"] == 6.8

    def test_fast(self):
        r = mod.interpolate_cycling(26.0)
        assert r["met"] == 12.0


class TestSwimmingClassification:
    def test_slow_low_intensity(self):
        # pace >= 3 min/100m → low
        r = mod.classify_swimming(3.5)
        assert r["intensity"] == "low"
        assert r["met"] == 4.8

    def test_moderate(self):
        # 2 <= pace < 3 → moderate
        r = mod.classify_swimming(2.5)
        assert r["intensity"] == "moderate"
        assert r["met"] == 7.0

    def test_fast_high(self):
        # pace < 2 → high
        r = mod.classify_swimming(1.5)
        assert r["intensity"] == "high"
        assert r["met"] == 9.8


class TestCalcCalories:
    def test_basic(self):
        # MET 6.0 × 70 kg × 30 min / 60 = 210 kcal
        assert mod.calc_calories(6.0, 70, 30) == 210.0

    def test_zero_duration(self):
        assert mod.calc_calories(6.0, 70, 0) == 0.0

    def test_high_met(self):
        # 大 MET
        cal = mod.calc_calories(12.0, 60, 60)
        assert cal == 720.0


class TestCalcNetCalories:
    def test_subtracts_bmr_component(self):
        # net = (MET - 1) * weight * hours = 5 * 70 * 0.5 = 175
        assert mod.calc_net_calories(6.0, 70, 30) == 175.0

    def test_met_below_1_clamps_zero(self):
        # 极低 MET(比如安静)不该出负数
        assert mod.calc_net_calories(0.5, 70, 30) == 0.0


class TestResolveMet:
    def test_running_by_speed(self):
        met, _ = mod.resolve_met("running", speed=10.0)
        assert 10 <= met <= 11

    def test_cycling_by_speed(self):
        met, _ = mod.resolve_met("cycling", speed=20.0)
        # 20 km/h 在 19-22 之间,插值应在 8-10
        assert 8 <= met <= 10

    def test_swimming_by_pace(self):
        met, _ = mod.resolve_met("swimming", pace_100m=2.5)
        assert met == 7.0
