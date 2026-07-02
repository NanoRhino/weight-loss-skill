"""periodic-recalc 单测:重算触发条件 + macro 目标计算。

覆盖:
- is_weight_fresh:14 天窗口边界
- calc_macros:diet_mode 差异
- calculate_macro_percentages:样本 < 7 天返回 None
- is_within_range
- has_periodic_recalc / find_weekly_report_job / group_by_agent:cron 迁移工具
"""
import importlib.util
from datetime import date, timedelta
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parent.parent / "periodic-recalc" / "scripts"

def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

recalc = _load("periodic_recalc", SKILL / "periodic-recalc.py")
review = _load("diet_mode_review", SKILL / "diet-mode-review.py")
migrate = _load("migrate_add_cron", SKILL / "migrate-add-cron.py")


class TestIsWeightFresh:
    def test_today_fresh(self):
        today = date.today().isoformat()
        assert recalc.is_weight_fresh(today) is True

    def test_7_days_fresh(self):
        d = (date.today() - timedelta(days=7)).isoformat()
        assert recalc.is_weight_fresh(d) is True

    def test_14_days_boundary(self):
        # 14 天边界包含
        d = (date.today() - timedelta(days=14)).isoformat()
        assert recalc.is_weight_fresh(d) is True

    def test_15_days_stale(self):
        d = (date.today() - timedelta(days=15)).isoformat()
        assert recalc.is_weight_fresh(d) is False

    def test_custom_max_age(self):
        d = (date.today() - timedelta(days=30)).isoformat()
        assert recalc.is_weight_fresh(d, max_age_days=60) is True


class TestCalcMacros:
    """返回结构 { protein_g: [lo,hi], carbs_g: [lo,hi], fat_g: [lo,hi] }"""

    def test_balanced_mode(self):
        r = recalc.calc_macros(weight_kg=70, daily_cal=1500, diet_mode="balanced")
        assert "protein_g" in r
        assert "fat_g" in r
        assert "carbs_g" in r
        # 每个都是 [lo, hi] 数组
        assert r["protein_g"][0] < r["protein_g"][1]

    def test_target_weight_used_for_protein(self):
        # 100kg 用户目标 60kg,protein 按 60 算
        r_actual = recalc.calc_macros(weight_kg=60, daily_cal=1500, diet_mode="balanced")
        r_target = recalc.calc_macros(weight_kg=100, daily_cal=1500, diet_mode="balanced", target_weight=60)
        assert r_actual["protein_g"] == r_target["protein_g"]

    def test_keto_high_fat(self):
        r = recalc.calc_macros(weight_kg=70, daily_cal=1500, diet_mode="keto")
        r_bal = recalc.calc_macros(weight_kg=70, daily_cal=1500, diet_mode="balanced")
        # keto fat lo > balanced fat lo
        assert r["fat_g"][0] > r_bal["fat_g"][0]

    def test_carb_non_negative(self):
        r = recalc.calc_macros(weight_kg=100, daily_cal=800, diet_mode="keto")
        assert r["carbs_g"][0] >= 0


class TestIsWithinRange:
    def test_in_range(self):
        assert review.is_within_range(50, (30, 60)) is True

    def test_below(self):
        assert review.is_within_range(20, (30, 60)) is False

    def test_above(self):
        assert review.is_within_range(70, (30, 60)) is False

    def test_at_lo_edge(self):
        assert review.is_within_range(30, (30, 60)) is True

    def test_at_hi_edge(self):
        assert review.is_within_range(60, (30, 60)) is True


class TestCalcMacroPercentages:
    def test_below_7_days_returns_none(self):
        # 6 天不够
        data = [{"protein_g": 100, "carbs_g": 200, "fat_g": 50, "calories": 1500} for _ in range(6)]
        assert review.calculate_macro_percentages(data) is None

    def test_7_days_ok(self):
        # 使物理成立:protein 90g*4=360 + carbs 150g*4=600 + fat 60g*9=540 = 1500
        data = [{"protein_g": 90, "carbs_g": 150, "fat_g": 60, "calories": 1500} for _ in range(7)]
        r = review.calculate_macro_percentages(data)
        assert r is not None
        assert "protein_pct" in r
        assert "carbs_pct" in r
        assert "fat_pct" in r
        total = r["protein_pct"] + r["carbs_pct"] + r["fat_pct"]
        assert 95 <= total <= 105


class TestCronMigration:
    def test_has_periodic_recalc_matches_name(self):
        jobs = [{"name": "Periodic recalc", "payload": {}}]
        assert migrate.has_periodic_recalc(jobs) is True

    def test_has_periodic_recalc_matches_script(self):
        jobs = [{"name": "Foo", "payload": {"message": "run periodic-recalc.py --now"}}]
        assert migrate.has_periodic_recalc(jobs) is True

    def test_has_periodic_recalc_no_match(self):
        jobs = [{"name": "Weekly report", "payload": {"message": "weekly-report"}}]
        assert migrate.has_periodic_recalc(jobs) is False

    def test_find_weekly_report_job(self):
        jobs = [
            {"name": "Foo", "payload": {}},
            {"name": "Weekly report", "payload": {"schedule": "0 9 * * 0"}},
        ]
        r = migrate.find_weekly_report_job(jobs)
        assert r["name"] == "Weekly report"

    def test_find_weekly_report_none(self):
        assert migrate.find_weekly_report_job([]) is None

    def test_group_by_agent(self):
        # 字段是 agentId(camelCase),不是 agent_id
        jobs = [
            {"agentId": "a1", "name": "j1"},
            {"agentId": "a1", "name": "j2"},
            {"agentId": "a2", "name": "j3"},
        ]
        r = migrate.group_by_agent(jobs)
        assert len(r["a1"]) == 2
        assert len(r["a2"]) == 1

    def test_group_by_agent_skips_missing(self):
        # 无 agentId 的应跳过而非抛错
        jobs = [{"agentId": "a1", "name": "j1"}, {"name": "j2"}]
        r = migrate.group_by_agent(jobs)
        assert "a1" in r
