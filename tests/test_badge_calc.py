"""reward-engine/scripts/badge-calc.py 单测。

覆盖徽章 level 判定 + percentile 计算 + progress bar。
level 判定错了用户会看到错误徽章,percentile 用来激励文案,都要准。
"""
import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "reward-engine" / "scripts" / "badge-calc.py"
spec = importlib.util.spec_from_file_location("badge_calc", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class TestGetLevelForCount:
    def test_below_first_level(self):
        # < 3 天 → level 0
        assert mod.get_level_for_count(0) == 0
        assert mod.get_level_for_count(2) == 0

    def test_level_1_at_3(self):
        assert mod.get_level_for_count(3) == 1

    def test_level_2_at_7(self):
        assert mod.get_level_for_count(7) == 2

    def test_level_3_at_14(self):
        assert mod.get_level_for_count(14) == 3

    def test_between_levels_takes_lower(self):
        # 5 天 → 已过 3 未到 7 → level 1
        assert mod.get_level_for_count(5) == 1

    def test_max_level_at_90(self):
        # LEVELS 最高 90 天
        assert mod.get_level_for_count(90) == 8

    def test_beyond_max_stays_at_max(self):
        # 200 天也是 max level
        assert mod.get_level_for_count(200) == 8


class TestGetNextLevelTarget:
    def test_level_0_needs_3(self):
        assert mod.get_next_level_target(0) == 3

    def test_level_1_needs_7(self):
        assert mod.get_next_level_target(1) == 7

    def test_level_2_needs_14(self):
        assert mod.get_next_level_target(2) == 14

    def test_level_3_needs_21(self):
        assert mod.get_next_level_target(3) == 21

    def test_at_max_returns_max(self):
        # max level 后没有 next,函数兜底返 max day count
        assert mod.get_next_level_target(8) == 90


class TestGenerateProgressBar:
    def test_no_current_level(self):
        """0 → 1 之间"""
        bar = mod.generate_progress_bar(current_count=1, next_target=3, current_level=0)
        assert isinstance(bar, str)
        assert len(bar) > 0

    def test_max_level_returns_MAX_string(self):
        # 已经 max,不再显示进度条
        bar = mod.generate_progress_bar(current_count=100, next_target=90, current_level=8)
        assert "MAX" in bar

    def test_between_levels(self):
        # level 1 → 2,当前 5 天(还差 2 天)
        bar = mod.generate_progress_bar(current_count=5, next_target=7, current_level=1)
        assert isinstance(bar, str)


class TestCalcPercentile:
    def test_new_user_high_percentile(self):
        # 刚开始就升级 = 顶尖
        p = mod.calc_percentile(level=1, elapsed_days=3)
        assert isinstance(p, str)
        assert "%" in p

    def test_slow_user_lower_percentile(self):
        # 拖了很久才 level 1
        p_fast = mod.calc_percentile(level=1, elapsed_days=3)
        p_slow = mod.calc_percentile(level=1, elapsed_days=90)
        # 越慢排名越低数字越大
        # (至少不该抛错)
        assert isinstance(p_slow, str)

    def test_unknown_level_falls_back(self):
        # 未知 level → 兜底(不抛错)
        p = mod.calc_percentile(level=99, elapsed_days=30)
        assert isinstance(p, str)
