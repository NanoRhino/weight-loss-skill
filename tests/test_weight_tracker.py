"""weight-tracking/scripts/weight-tracker.py 单测。

覆盖单位换算(kg/lb/斤)、日期解析。这些函数在打卡入口 hot path,
错了就直接给用户错的体重数字。
"""
import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "weight-tracking" / "scripts" / "weight-tracker.py"
spec = importlib.util.spec_from_file_location("weight_tracker", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class TestNormalizeUnit:
    def test_kg_variants(self):
        assert mod.normalize_unit("kg") == "kg"
        assert mod.normalize_unit("KG") == "kg"
        assert mod.normalize_unit("公斤") == "kg"
        assert mod.normalize_unit("千克") == "kg"
        assert mod.normalize_unit(" kg ") == "kg"

    def test_lb_variants(self):
        assert mod.normalize_unit("lb") == "lb"
        assert mod.normalize_unit("lbs") == "lb"
        assert mod.normalize_unit("pound") == "lb"
        assert mod.normalize_unit("Pounds") == "lb"

    def test_catty_maps_to_kg(self):
        # 斤 存储为 kg,归一化就返 kg
        assert mod.normalize_unit("斤") == "kg"
        assert mod.normalize_unit("jin") == "kg"


class TestCattyToKg:
    def test_catty(self):
        # 100 斤 = 50 kg
        assert mod.catty_to_kg(100, "斤") == 50.0

    def test_jin_pinyin(self):
        assert mod.catty_to_kg(2, "jin") == 1.0

    def test_kg_untouched(self):
        assert mod.catty_to_kg(60, "kg") == 60


class TestConvertWeight:
    def test_same_unit_noop(self):
        assert mod.convert_weight(60.0, "kg", "kg") == 60.0

    def test_kg_to_lb(self):
        # 60 kg ≈ 132.3 lb
        result = mod.convert_weight(60, "kg", "lb")
        assert 132.2 <= result <= 132.4

    def test_lb_to_kg(self):
        # 100 lb ≈ 45.4 kg
        result = mod.convert_weight(100, "lb", "kg")
        assert 45.3 <= result <= 45.5

    def test_kg_from_catty_normalize(self):
        # 斤/jin 归一化后都是 kg,convert 不出错
        assert mod.convert_weight(60, "斤", "kg") == 60.0


class TestDateFromKey:
    def test_iso_datetime(self):
        assert mod.date_from_key("2026-05-12T10:30:00+08:00") == "2026-05-12"

    def test_short_date(self):
        # 短日期直接返回前 10 字符(能容忍)
        assert mod.date_from_key("2026-05-12") == "2026-05-12"


class TestParseIso:
    def test_full_datetime(self):
        dt = mod.parse_iso("2026-05-12T10:30:00+08:00")
        assert dt.year == 2026
        assert dt.month == 5
        assert dt.day == 12
