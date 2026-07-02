"""SKILL.md schema 单测 — 保证下游 skill 依赖的字段/section 名不被误改。

背景:这些字段是 skills 之间的**契约**——
  - weight-loss-planner 从 health-profile.md 读 "Target Weight" / "Activity Level"
  - meal-tracker 从 health-preferences.md 读 "Food Restrictions"
  - diet-pattern-detection 读 "Diet Mode"
  - 等等
onboarding skill 改了字段名(比如把 "Target Weight" 改成 "Goal Weight")
下游 skill 就找不到字段,静默降级或 assume 默认值,agent 会给错建议。

本测试是 backend-service/.openclaw-user-service/tests/onboarding.test.ts 的
Python 副本,专门保护**通过独立 clone 直接改 skill 仓再 push**的场景——
父仓的 vitest 测试只在 backend-service 那边 pre-push 触发。

覆盖:
  - user-onboarding-profile SKILL.md 存在
  - health-profile / health-preferences schema 字段与 section 完整
"""
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
ONBOARDING_SKILL = REPO_ROOT / "user-onboarding-profile" / "SKILL.md"


@pytest.fixture(scope="module")
def skill_content() -> str:
    assert ONBOARDING_SKILL.exists(), f"missing {ONBOARDING_SKILL}"
    return ONBOARDING_SKILL.read_text(encoding="utf-8")


class TestSkillExists:
    def test_user_onboarding_profile_dir_exists(self):
        assert (REPO_ROOT / "user-onboarding-profile").is_dir()

    def test_skill_md_exists(self):
        assert ONBOARDING_SKILL.exists()


class TestHealthProfileFields:
    """health-profile.md schema 字段——下游 skills(weight-loss-planner 等)读这些字段。
    改字段名 = 破坏所有下游 → 必挂本测,让人先协调更新。
    """
    REQUIRED_FIELDS = [
        "Unit Preference",
        "Activity Level",
        "Exercise Habits",
        "Diet Mode",
        "Food Restrictions",
        "Target Weight",
        "Weight to Lose",
        "Core Motivation",
        "Onboarding Completed",
        "Pattern Detection Completed",
    ]

    @pytest.mark.parametrize("field", REQUIRED_FIELDS)
    def test_field_described(self, skill_content: str, field: str):
        assert field in skill_content, f"SKILL.md missing field: {field}"


class TestHealthProfileSections:
    """section headers 也是契约,agent 按 section 找字段"""
    REQUIRED_SECTIONS = [
        "## Body",
        "## Activity & Lifestyle",
        "## Goals",
        "## Automation",
    ]

    @pytest.mark.parametrize("section", REQUIRED_SECTIONS)
    def test_section_present(self, skill_content: str, section: str):
        assert section in skill_content, f"SKILL.md missing section: {section}"


class TestHealthPreferencesSections:
    """health-preferences.md 里的 section(在同一 SKILL.md 里描述)"""
    REQUIRED_SECTIONS = [
        "## Dietary",
        "## Exercise",
        "## Scheduling & Lifestyle",
        "## Cooking & Kitchen",
    ]

    @pytest.mark.parametrize("section", REQUIRED_SECTIONS)
    def test_section_present(self, skill_content: str, section: str):
        assert section in skill_content, f"SKILL.md missing section: {section}"
