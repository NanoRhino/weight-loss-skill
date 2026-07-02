"""streak-tracker/scripts/streak-calc.py 单测。

skill 脚本是 shebang 命令行工具,不是 python module,用 importlib 动态加载。
覆盖:
- _meal_has_food:输入类型/字段
- calculate_streak:空/单日/连续/断档/今天or昨天结尾
- get_pending_milestone:已达成/过期自动标记/celebrated set
"""
import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "streak-tracker" / "scripts" / "streak-calc.py"

# 动态加载脚本模块
spec = importlib.util.spec_from_file_location("streak_calc", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class TestMealHasFood:
    def test_items(self):
        assert mod._meal_has_food({"items": [{"name": "苹果"}]}) is True

    def test_foods_fallback(self):
        # 老 schema 用 foods 字段
        assert mod._meal_has_food({"foods": [{"name": "香蕉"}]}) is True

    def test_empty_items(self):
        assert mod._meal_has_food({"items": []}) is False

    def test_no_food_fields(self):
        assert mod._meal_has_food({"meal_number": 1}) is False

    def test_not_dict(self):
        assert mod._meal_has_food("string") is False
        assert mod._meal_has_food(None) is False
        assert mod._meal_has_food([1, 2]) is False


class TestCalculateStreak:
    def test_empty(self):
        assert mod.calculate_streak(set(), "2026-07-02") == (0, 0, None)

    def test_single_day_today(self):
        cur, longest, start = mod.calculate_streak({"2026-07-02"}, "2026-07-02")
        assert cur == 1
        assert longest == 1
        assert start == "2026-07-02"

    def test_single_day_yesterday_still_counts(self):
        # 昨天记的今天没记,streak 仍是 1(允许一天宽限)
        cur, longest, _ = mod.calculate_streak({"2026-07-01"}, "2026-07-02")
        assert cur == 1
        assert longest == 1

    def test_broken_stops_counting(self):
        # 3 天前一天,今天没记 → current 0(超过 1 天缺口)
        cur, longest, _ = mod.calculate_streak({"2026-06-29"}, "2026-07-02")
        assert cur == 0
        assert longest == 1

    def test_consecutive_days(self):
        dates = {"2026-06-30", "2026-07-01", "2026-07-02"}
        cur, longest, start = mod.calculate_streak(dates, "2026-07-02")
        assert cur == 3
        assert longest == 3
        assert start == "2026-06-30"

    def test_two_streaks_pick_longest(self):
        # 早期 5 天连续 + 中间断 + 最近 2 天
        dates = {
            "2026-06-01", "2026-06-02", "2026-06-03", "2026-06-04", "2026-06-05",
            "2026-07-01", "2026-07-02",
        }
        cur, longest, _ = mod.calculate_streak(dates, "2026-07-02")
        assert cur == 2       # 最近的 streak
        assert longest == 5   # 历史最长

    def test_gap_within_streak_stops(self):
        # 连续 3 天 + 隔 1 天 + 今天记 → 当前 streak 只算今天(单点)
        dates = {"2026-06-28", "2026-06-29", "2026-06-30", "2026-07-02"}
        cur, longest, _ = mod.calculate_streak(dates, "2026-07-02")
        assert cur == 1
        assert longest == 3


class TestGetPendingMilestone:
    def test_reached_and_not_celebrated(self):
        celebrated = []
        # streak=7 刚到,应该 pending 7
        assert mod.get_pending_milestone(7, celebrated) == 7

    def test_reached_within_1_day_still_pending(self):
        # streak=8, 里程碑 7 前一天到的,还没庆祝过
        celebrated = []
        assert mod.get_pending_milestone(8, celebrated) == 7

    def test_expired_silently_marks(self):
        # streak=10,里程碑 7 早就过了(current - m > 1),不弹但要 mark
        celebrated = []
        result = mod.get_pending_milestone(10, celebrated)
        assert result is None
        assert 7 in celebrated  # silently added

    def test_already_celebrated_skip(self):
        celebrated = [7]
        assert mod.get_pending_milestone(7, celebrated) is None

    def test_no_milestone_reached(self):
        assert mod.get_pending_milestone(2, []) is None

    def test_milestone_3_edge(self):
        # 3 是第一个里程碑
        assert mod.get_pending_milestone(3, []) == 3

    def test_multiple_expired(self):
        # streak=30,里程碑 3/7/14/21 都过了 → 全部 mark,只有 30 pending
        celebrated = []
        result = mod.get_pending_milestone(30, celebrated)
        assert result == 30
        assert set(celebrated) == {3, 7, 14, 21}
