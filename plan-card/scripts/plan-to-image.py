#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["weasyprint", "pymupdf", "qrcode"]
# ///
# NOTE: production (EC2) invokes this script with bare /usr/bin/python3
# (currently 3.9) via the openclaw-infra Twilio extension — the PEP-723
# header above is NOT resolved at runtime. Keep the code 3.9-compatible:
# no PEP 604 `X | Y` unions outside annotations, no match statements, and
# keep the `from __future__ import annotations` import below.
"""
plan-to-image.py — Deterministic plan-card renderer for SMS/MMS delivery.

Turns handoff profile data (JSON) into:
  (a) a branded NanoRhino plan card PNG suitable for MMS, and
  (b) PLAN.md markdown content (returned in stdout JSON, not written to disk).

No LLM involved. Plan CONTENT follows the canonical Step-3 spec in
user-onboarding-profile/SKILL.md ("Step 3：生成并确认减脂方案"):
  - a SINGLE daily calorie target (no band),
  - daily calorie deficit (~XXX),
  - weekly loss rate,
  - a single completion month + year.

The CARD additionally shows daily macros, the per-meal calorie rhythm
(30/40/30 via planner-calc's allocation), rule-based "Focus this week"
recommendations, and Week-1 checkpoints — an explicitly approved override
of the Step-3 "no macros at plan stage" rule, for the CARD ONLY.
PLAN.md (plan_markdown) stays Step-3 compliant: no macros there.

LANGUAGE: all user-facing strings (card + plan_markdown) are localized via
the STRINGS table below. `locale.language` in the input JSON selects the
language ("en"/"zh"; unknown/absent → "en"). The upstream authority is
USER.md > Language — the openclaw-infra Twilio extension reads it and
passes it through; this script does NO language inference of its own.

ENERGY ANCHORING (product decision, Jason 2026-06-10, overriding the earlier
trust-forward-calc approach): the handoff `tdee.recommended` / `tdee.bmr`
from the input JSON — the TDEE decomposition the user already saw and
trusts on the web — is the ENERGY AUTHORITY for every path. planner-calc
(invoked as a SUBPROCESS; interface unmodified) supplies the methodology
on top: pace table (recommend-rate), safety floor max(BMR, 1000)
(safety-floor), calorie-target, BMI classification, and
macro-targets/allocation. forward-calc is NOT called — its re-derived
BMR/TDEE can disagree with the web number (e.g. produce a daily target
above the burn the user was shown). Guarantee: for intent=lose the daily
target is always strictly below the handoff TDEE (enforced in code).

CLI contract (invoked by the openclaw-infra Twilio extension — frozen):

  python3 plan-card/scripts/plan-to-image.py \
      --input <input.json> --output <out.png> [--width 1080] [--max-bytes 614400]

OPTIONAL QR CLAIM BLOCK (additive input field — part of the cross-repo
"email plan uses plan-card" feature, contract confirmed by Jason): the input
JSON may carry a top-level `qr` object:

  "qr": {"kind": "sms_claim", "number": "+19152777888", "body": "<handoff token>"}

When present, a QR code is rendered in the timeline ("unlock") area encoding
`SMSTO:<number>:<body>` — scanning it opens the phone's SMS app with the
claim token pre-filled (same action as the web SMS CTA). The page grows
taller to make room; the QR caption is localized via STRINGS. When `qr` is
ABSENT the output is byte-identical to the pre-QR renderer (the `qrcode`
dependency is imported lazily and only on the QR path).

OPTIONAL GLP-1 VARIANT (additive input field — `profile.on_glp1: bool`,
default false; absent/false renders byte-identically to the pre-GLP-1
pipeline). A GLP-1 agonist already suppresses appetite, so prescribing a
deficit on top risks undereating / muscle loss. When on_glp1 is true the
renderer pivots the product: the hero becomes the daily PROTEIN FLOOR
(1.6 g/kg via planner-calc high_protein, forced for every intent) and the
card/markdown drop the prescribed-deficit countdown:
  - lose    → 保肌 (protect muscle while the shot leads the pace): daily_cal
              held at a protective floor max(safety-floor, 1200 F / 1500 M);
              NO deficit / weekly pace / goal date.
  - recomp  → existing small-deficit math + GLP-1 framing.
  - maintain→ maintenance calories + GLP-1 framing (protect muscle as
              appetite returns).

stdout on success (single JSON line):
  {"ok": true, "png": "<abs path>", "bytes": N, "plan": {...}, "plan_markdown": "..."}
On failure: non-zero exit, {"ok": false, "error": "..."} on stdout, details on stderr.

System dependencies: WeasyPrint needs pango/cairo/gdk-pixbuf system libraries
(on EC2/Amazon Linux: `sudo dnf install pango cairo gdk-pixbuf2`;
on Ubuntu: `sudo apt-get install libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0`).
For zh rendering install a CJK font (e.g. google-noto-sans-cjk-fonts), and a
color emoji font (google-noto-emoji-color-fonts) for the checkpoint icons.
"""

from __future__ import annotations

import argparse
import json
import re
import string
import subprocess
import sys
import traceback
from datetime import date, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
PLANNER_CALC = REPO_ROOT / "weight-loss-planner" / "scripts" / "planner-calc.py"
TEMPLATE = SCRIPT_DIR.parent / "templates" / "plan-card.html"

# Fallback when goal_weight_kg is null and intent == "lose": assume the most
# conservative pace-table default (0.35 kg/week → ≈385 kcal/day deficit) and
# show the target without a completion date ("unlock" prompt instead).
NO_GOAL_RATE_KG = 0.35
# Mild deterministic adjustments for the intents the Step-3 spec doesn't model.
RECOMP_DEFICIT_KCAL = 200
GAIN_RATE_KG_PER_WEEK = 0.25  # lean gain default → ≈275 kcal/day surplus

# GLP-1 calorie floors (protective lower bound for users on a GLP-1 agonist,
# whose appetite is already pharmacologically suppressed). More protective
# than planner-calc's safety-floor max(BMR, 1000): research saw GLP-1 users
# self-imposing unsafe 1185–1300 kcal/day, so we hold a sex-specific minimum
# of 1200 (female) / 1500 (male) and take whichever floor is higher.
GLP1_FLOOR_FEMALE = 1200
GLP1_FLOOR_MALE = 1500

VALID_SEX = {"male", "female"}
VALID_INTENT = {"lose", "maintain", "recomp", "gain"}

# Regions using the Asian BMI classification (per Step-3 spec: zh/ja/ko
# regions or languages → asian, else WHO).
ASIAN_BMI_COUNTRIES = {"CN", "TW", "HK", "MO", "SG", "JP", "KR"}
ASIAN_BMI_LANGUAGES = {"zh", "ja", "ko"}

MIN_RENDER_WIDTH = 480  # don't shrink the PNG below this when fitting max-bytes

# @page height (CSS px). The base value is the historical fixed page size;
# byte-identical output without `qr` depends on it staying 3200. The QR
# claim block adds ~340px, so the page grows when (and only when) `qr` is
# present — otherwise the footer would overflow onto a second (unrendered)
# PDF page.
PAGE_HEIGHT_PX = 3200
PAGE_HEIGHT_QR_PX = 3540

# QR kinds accepted in the optional input `qr` object (additive contract).
VALID_QR_KINDS = {"sms_claim"}


# ---------------------------------------------------------------------------
# Localized strings (card + PLAN.md). USER.md > Language is the upstream
# authority; the Twilio extension passes it through as locale.language.
# Adding a language = adding a table entry (keys must match "en").
# ---------------------------------------------------------------------------

STRINGS = {
    "en": {
        "title_card": {"lose": "Your Weight Loss Plan",
                       "maintain": "Your Maintenance Plan",
                       "recomp": "Your Recomposition Plan",
                       "gain": "Your Lean Gain Plan"},
        "title_md": {"lose": "Weight Loss Plan",
                     "maintain": "Maintenance Plan",
                     "recomp": "Recomposition Plan",
                     "gain": "Lean Gain Plan"},
        "age": "Age {age}",
        "hero_target": "Daily Calorie Target",
        "hero_maint": "Daily Maintenance Target",
        "per_day": "{cu} per day",
        "sec_plan": "Your Plan",
        "sec_macros": "Daily Macros",
        "sec_rhythm": "Daily Rhythm",
        "sec_timeline": "Your Timeline",
        "sec_focus_alt": "Your Focus",
        "sec_first_week": "Your First Week",
        "tile_approx": "~{v} {cu}",
        "deficit": "Daily Deficit",
        "below_burn": "Below what you burn",
        "pace": "Weekly Pace",
        "steady": "Steady and sustainable",
        "surplus": "Daily Surplus",
        "above_maint": "Above maintenance",
        "weekly_gain": "Weekly Gain",
        "lean_steady": "Lean and steady",
        "goal_lbl": "Goal",
        "hold_steady": "Hold steady",
        "keep_level": "Keep eating at this level",
        "checkin": "Check-in",
        "weekly": "Weekly",
        "weekly_note": "One weigh-in a week keeps drift visible",
        "slight_deficit": "Slight deficit, heavy protein",
        "watch": "Watch",
        "mirror": "The mirror",
        "mirror_note": "Scale moves slowly — strength won't",
        "protein": "Protein",
        "fat": "Fat",
        "carbs": "Carbs",
        "floor": "floor {g}g",
        "target_note": "target ~{g}g",
        "meals": {"breakfast": "Breakfast", "lunch": "Lunch",
                  "dinner": "Dinner", "meal_1": "Meal 1", "meal_2": "Meal 2"},
        "of_day": "{pct}% of your day",
        "sec_sample": "Sample Day",
        "meal_col": "Meal",
        "recommend_col": "Suggested",
        "protein_col": "Protein",
        "snack_label": "Snacks",
        "sample_breakfast": [
            "Greek yogurt + berries + granola — ~30g protein",
            "3 eggs + turkey sausage + toast — ~35g protein",
            "Whey smoothie with banana + oats — ~40g protein",
        ],
        "sample_lunch": "Chicken breast + rice + broccoli — ~40g protein",
        "sample_dinner": "Salmon or lean beef + sweet potato — ~35g protein",
        "sample_snacks": "Greek yogurt (20g) · cottage cheese (14g) · egg (6g)",
        "sample_formula": "The pattern: protein (6 oz) + complex carb (1 cup) + vegetables (unlimited) + fat (1 tbsp)",
        "goal_reached": "Goal Reached",
        "weeks_from": "~{w} weeks from today",
        "unlock_title": "Reply with your goal weight<br>to unlock your completion date",
        "remember": "Remember",
        "maintain_focus": "Consistency beats perfection — show up daily",
        "recomp_focus": "Give it 8–12 weeks before judging the scale",
        "focus_walk": "Add a 10-minute walk after lunch and dinner",
        "focus_strength": "Add 2 short strength sessions — muscle protects your burn",
        "focus_sleep": "Protect your sleep — 7+ hours makes results come easier",
        "focus_water": "Water first: 2 liters a day — thirst often reads as hunger",
        "cp_photo": "Log every meal — just text what you ate, a photo works too",
        "cp_weigh": "Weigh in Saturday morning",
        "cp_protein": "Hit your protein target at every meal",
        # GLP-1 variant (card): hero = protein floor; intent-adapted tiles,
        # focus copy, and first-week checkpoints. No prescribed deficit /
        # pace / goal date for the lose (保肌) case.
        "glp1_title": {"lose": "Your GLP-1 Plan",
                       "maintain": "Your GLP-1 Plan",
                       "recomp": "Your GLP-1 Plan"},
        "glp1_hero_label": "Daily Protein Floor",
        "glp1_hero_unit": "g · hit it even when you're not hungry",
        "glp1_tile1_lose_label": "Don't eat below",
        "glp1_tile1_lose_note": "muscle first, not the scale",
        "glp1_tile2_lose_label": "Weigh in",
        "glp1_tile2_lose_value": "Weekly",
        "glp1_tile2_lose_note": "eat to appetite, watch the trend",
        "glp1_tile1_recomp_label": "Slight deficit",
        "glp1_tile1_recomp_value": "+ high protein",
        "glp1_tile2_recomp_label": "The mirror",
        "glp1_tile2_recomp_value": "strength shows first",
        "glp1_tile1_maint_label": "Hold steady",
        "glp1_tile2_maint_label": "Protein first",
        "glp1_tile2_maint_value": "hold muscle as appetite returns",
        "glp1_focus_lose": "Your shot leads the pace — eat to appetite, weigh "
                           "weekly; what comes off stays fat, not muscle.",
        "glp1_focus_kicker": "HOW THIS WORKS",
        "glp1_cp_protein": "Hit your protein every meal, even with no appetite",
        "glp1_cp_floor": "Don't drop below your calorie floor",
        "glp1_cp_weigh": "Weigh in once a week",
        "glp1_cp_strength": "2 short strength sessions — muscle protects your "
                            "results",
        "glp1_cp_water": "Water first",
        "qr_title": "Scan to start",
        "qr_note": "Opens a text to me with your claim code — just hit send.",
        "footer": "Text me anytime — your AI nutrition coach",
        # PLAN.md
        "generated": "Generated {date} · NanoRhino AI Nutrition Coach",
        "md_info": "Your Info",
        "md_plan": "Your Plan",
        "md_height": "Height: {v}",
        "md_weight": "Current weight: {v}",
        "md_goal": "Goal weight: {v}",
        "md_age_sex": "Age: {age} · Sex: {sex}",
        "sex": {"male": "Male", "female": "Female"},
        "md_activity": "Activity: {v}",
        "assumed": " (assumed — tell me your routine to fine-tune)",
        "md_target": "Daily calorie target: {v} {cu}",
        "md_protein_floor": "Daily protein floor: {v} g — hit it every meal, "
                            "even when you're not hungry",
        "md_deficit": "Daily calorie deficit: ~{v} {cu}",
        "md_surplus": "Daily calorie surplus: ~{v} {cu}",
        "md_rate_loss": "Weekly loss rate: ~{v}",
        "md_rate_gain": "Weekly gain rate: ~{v}",
        "md_completion": "Estimated completion: {v}",
        "md_unlock": "Estimated completion: reply with your goal weight "
                     "to unlock your completion date",
        "expl_lose": "This pace keeps your energy up while the scale keeps "
                     "moving — steady enough to stick with.",
        "expl_lose_sedentary": " Adding a bit more daily movement would "
                               "speed things up.",
        "expl_maintain": "Eat around this level and your weight holds steady "
                         "— a weekly weigh-in catches any drift early.",
        "expl_recomp": "A small deficit with plenty of protein lets you build "
                       "strength while trimming fat — judge progress by the "
                       "mirror, not the scale.",
        "expl_gain": "A modest surplus keeps the gains lean — slow on the "
                     "scale, visible in the gym.",
        # GLP-1 PLAN.md explanations (per intent).
        "expl_glp1_lose": "Eat at least {floor} {cu} a day, hit your protein "
                          "every meal to protect muscle, let your appetite "
                          "lead, and weigh in weekly. Your shot already sets "
                          "the pace — your job is to protect muscle so what "
                          "comes off is fat.",
        "expl_glp1_recomp": "A small deficit with plenty of protein lets you "
                            "build strength while the shot holds your appetite "
                            "— judge progress by the mirror, not the scale.",
        "expl_glp1_maintain": "Eat around this level and hold steady — protein "
                              "first, so you keep your muscle as your appetite "
                              "returns.",
        "floor_note": "> Note: your daily target was raised to your safety "
                      "floor and the pace adjusted accordingly — eating less "
                      "than this would work against you.",
        "act_desc": {
            "sedentary": "mostly sitting during the day",
            "lightly_active": "on your feet part of the day, light exercise",
            "moderately_active": "regular exercise most weeks",
            "very_active": "hard exercise most days",
            "extremely_active": "very hard daily training",
        },
    },
    "zh": {
        "title_card": {"lose": "你的减脂计划",
                       "maintain": "你的体重维持计划",
                       "recomp": "你的塑形计划",
                       "gain": "你的增肌计划"},
        "title_md": {"lose": "减脂计划",
                     "maintain": "体重维持计划",
                     "recomp": "塑形计划",
                     "gain": "增肌计划"},
        "age": "{age} 岁",
        "hero_target": "每日热量目标",
        "hero_maint": "每日维持热量",
        "per_day": "{cu} / 天",
        "sec_plan": "你的计划",
        "sec_macros": "每日宏量营养",
        "sec_rhythm": "三餐节奏",
        "sec_timeline": "你的时间线",
        "sec_focus_alt": "你的重点",
        "sec_first_week": "你的第一周",
        "tile_approx": "约 {v} {cu}",
        "deficit": "每日热量缺口",
        "below_burn": "低于你每天的消耗",
        "pace": "每周减脂速度",
        "steady": "稳健、可持续",
        "surplus": "每日热量盈余",
        "above_maint": "高于维持热量",
        "weekly_gain": "每周增重",
        "lean_steady": "干净增肌、稳步推进",
        "goal_lbl": "目标",
        "hold_steady": "保持稳定",
        "keep_level": "按这个量吃就好",
        "checkin": "检查节奏",
        "weekly": "每周一次",
        "weekly_note": "每周称重一次，及时发现波动",
        "slight_deficit": "小缺口 + 高蛋白",
        "watch": "关注",
        "mirror": "镜子里的变化",
        "mirror_note": "体重变化慢——线条不会骗人",
        "protein": "蛋白质",
        "fat": "脂肪",
        "carbs": "碳水",
        "floor": "下限 {g}g",
        "target_note": "目标约 {g}g",
        "meals": {"breakfast": "早餐", "lunch": "午餐",
                  "dinner": "晚餐", "meal_1": "第一餐", "meal_2": "第二餐"},
        "of_day": "占全天 {pct}%",
        "sec_sample": "一日三餐示例",
        "meal_col": "餐次",
        "recommend_col": "推荐搭配",
        "protein_col": "蛋白质",
        "snack_label": "加餐",
        "sample_breakfast": [
            "鸡蛋 2 个 + 无糖豆浆 + 全麦面包——约 25g 蛋白质",
            "鸡蛋 3 个 + 牛奶 + 燕麦——约 30g 蛋白质",
        ],
        "sample_lunch": "鸡胸肉 150g + 米饭 1 碗 + 西兰花——约 40g 蛋白质",
        "sample_dinner": "清蒸鱼或瘦牛肉 150g + 红薯 + 时蔬——约 35g 蛋白质",
        "sample_snacks": "希腊酸奶（15–20g 蛋白质）· 茶叶蛋（每个约 6g）",
        "sample_formula": "搭配公式：蛋白质 150g + 主食 1 碗 + 蔬菜不限量 + 油脂 1 勺",
        "goal_reached": "达成目标",
        "weeks_from": "距今约 {w} 周",
        "unlock_title": "回复你的目标体重<br>解锁预计完成日期",
        "remember": "记住",
        "maintain_focus": "持续比完美更重要——每天坚持就好",
        "recomp_focus": "给自己 8–12 周，再看体重秤的变化",
        "focus_walk": "午餐和晚餐后各走 10 分钟",
        "focus_strength": "每周加 2 次简短力量训练——肌肉护住你的代谢",
        "focus_sleep": "睡够 7 小时以上——恢复好，效果来得更快",
        "focus_water": "先喝水：每天 2 升——口渴常被误以为是饿",
        "cp_photo": "记录每一餐——随手发文字就行，也能拍照",
        "cp_weigh": "周六早晨称体重",
        "cp_protein": "每餐吃够你的蛋白质目标",
        # GLP-1 变体（卡片）：主视觉换成蛋白质底线；瓷砖、重点文案和
        # 第一周清单按 intent 适配。保肌（lose）这一档不显示规定缺口、
        # 减脂速度或目标日期。
        "glp1_title": {"lose": "你的 GLP-1 计划",
                       "maintain": "你的 GLP-1 计划",
                       "recomp": "你的 GLP-1 计划"},
        "glp1_hero_label": "每日蛋白质底线",
        "glp1_hero_unit": "g · 没胃口也要吃够它",
        "glp1_tile1_lose_label": "别低于",
        "glp1_tile1_lose_note": "保肌优先，不是减秤",
        "glp1_tile2_lose_label": "每周称重",
        "glp1_tile2_lose_value": "每周一次",
        "glp1_tile2_lose_note": "按食欲吃，看趋势",
        "glp1_tile1_recomp_label": "小缺口",
        "glp1_tile1_recomp_value": "+ 高蛋白",
        "glp1_tile2_recomp_label": "看镜子",
        "glp1_tile2_recomp_value": "线条先变",
        "glp1_tile1_maint_label": "保持维持热量",
        "glp1_tile2_maint_label": "蛋白质优先",
        "glp1_tile2_maint_value": "食欲回来时守住肌肉",
        "glp1_focus_lose": "针剂主导节奏——按食欲吃、每周称重，掉下去的是"
                           "脂肪不是肌肉。",
        "glp1_focus_kicker": "记住这一点",
        "glp1_cp_protein": "每餐都吃够蛋白质，哪怕没胃口",
        "glp1_cp_floor": "别低于你的热量下限",
        "glp1_cp_weigh": "每周称一次",
        "glp1_cp_strength": "每周 2 次力量训练——肌肉护住成果",
        "glp1_cp_water": "先喝水",
        "qr_title": "扫码开始",
        "qr_note": "自动打开短信并填好领取码——点发送就行。",
        "footer": "有问题随时发消息——你的 AI 营养师",
        # PLAN.md
        "generated": "生成于 {date} · NanoRhino AI 营养师",
        "md_info": "你的信息",
        "md_plan": "你的计划",
        "md_height": "身高：{v}",
        "md_weight": "当前体重：{v}",
        "md_goal": "目标体重：{v}",
        "md_age_sex": "年龄：{age} · 性别：{sex}",
        "sex": {"male": "男", "female": "女"},
        "md_activity": "活动情况：{v}",
        "assumed": "（估算值——告诉我你的日常作息可以更精确）",
        "md_target": "每日热量目标：{v} {cu}",
        "md_protein_floor": "每日蛋白质底线：{v} g——每餐都吃够，哪怕没胃口",
        "md_deficit": "每日热量缺口：约 {v} {cu}",
        "md_surplus": "每日热量盈余：约 {v} {cu}",
        "md_rate_loss": "每周减脂速度：约 {v}",
        "md_rate_gain": "每周增重速度：约 {v}",
        "md_completion": "预计完成：{v}",
        "md_unlock": "预计完成：回复你的目标体重，解锁预计完成日期",
        "expl_lose": "这个节奏既能让体重稳步下降，又不至于饿得没精神——"
                     "坚持得下去才是关键。",
        "expl_lose_sedentary": "平时多走动一些，进度还会更快。",
        "expl_maintain": "按这个量吃，体重会保持稳定——每周称一次，及时发现波动。",
        "expl_recomp": "小热量缺口配足量蛋白质，边减脂边涨力量——看镜子，别只盯着秤。",
        "expl_gain": "适度盈余让增重更干净——秤上慢一点，训练房里看得见。",
        # GLP-1 PLAN.md 说明（按 intent）。
        "expl_glp1_lose": "每天至少吃 {floor} {cu}，每餐都吃够蛋白质来保住"
                          "肌肉，按食欲进食，每周称一次。针剂已经在主导节奏"
                          "——你要做的是守住肌肉，让掉下去的是脂肪。",
        "expl_glp1_recomp": "小热量缺口配足量蛋白质，趁针剂压住食欲时增长"
                            "力量——看镜子，别只盯着秤。",
        "expl_glp1_maintain": "按这个量吃、保持稳定——蛋白质优先，食欲回来时"
                              "也能守住肌肉。",
        "floor_note": "> 注：你的每日目标已上调至安全下限，节奏也相应调整——"
                      "吃得更少反而会拖慢进度。",
        "act_desc": {
            "sedentary": "平时大部分时间坐着",
            "lightly_active": "日常有一定走动，轻量运动",
            "moderately_active": "每周有规律运动",
            "very_active": "几乎每天高强度运动",
            "extremely_active": "日常高强度训练",
        },
    },
}

# NOTE: the first-week emoji icons (📸 ⚖️ 🍗 in first_week_items) need a
# color emoji font on the render host (Apple Color Emoji on macOS; install
# google-noto-emoji-color-fonts on EC2/Amazon Linux).


def resolve_lang(language_tag: str) -> str:
    """Map a BCP-47-ish tag to a STRINGS table key. Unknown → 'en'."""
    primary = (language_tag or "").lower().split("-")[0]
    return primary if primary in STRINGS else "en"


# ---------------------------------------------------------------------------
# planner-calc subprocess wrapper
# ---------------------------------------------------------------------------

def run_planner(*args) -> dict:
    """Invoke planner-calc.py as a subprocess and parse its JSON output."""
    cmd = [sys.executable, str(PLANNER_CALC), *[str(a) for a in args]]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"planner-calc {args[0]} failed (exit {proc.returncode}): "
            f"{proc.stderr.strip() or proc.stdout.strip()}"
        )
    return json.loads(proc.stdout)


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

def validate_input(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("Input JSON must be an object")

    profile = data.get("profile")
    if not isinstance(profile, dict):
        raise ValueError("Missing 'profile' object")

    for field in ("sex", "age_years", "height_cm", "weight_kg"):
        if profile.get(field) in (None, ""):
            raise ValueError(f"Missing required profile field: {field}")

    if profile["sex"] not in VALID_SEX:
        raise ValueError(f"profile.sex must be one of {sorted(VALID_SEX)}")

    intent = profile.get("intent") or "lose"
    if intent not in VALID_INTENT:
        raise ValueError(f"profile.intent must be one of {sorted(VALID_INTENT)}")
    profile["intent"] = intent

    # GLP-1 flag (additive, backward-compatible — absent/false renders
    # byte-identically to the pre-GLP-1 pipeline). When true the renderer
    # pivots the card/markdown from a prescribed-deficit countdown to a
    # protein-floor / muscle-preservation framing (see compute_plan).
    profile["on_glp1"] = bool(profile.get("on_glp1"))

    profile["age_years"] = int(profile["age_years"])
    profile["height_cm"] = float(profile["height_cm"])
    profile["weight_kg"] = float(profile["weight_kg"])
    if profile.get("goal_weight_kg") is not None:
        profile["goal_weight_kg"] = float(profile["goal_weight_kg"])

    if profile["height_cm"] <= 0 or profile["weight_kg"] <= 0:
        raise ValueError("height_cm and weight_kg must be positive")

    tdee = data.get("tdee")
    if not isinstance(tdee, dict):
        raise ValueError("Missing 'tdee' object")
    for field in ("recommended", "bmr"):
        if tdee.get(field) in (None, ""):
            raise ValueError(f"Missing required tdee field: {field}")
    tdee["recommended"] = round(float(tdee["recommended"]))
    tdee["bmr"] = float(tdee["bmr"])
    tdee["low"] = round(float(tdee.get("low") or tdee["recommended"] - 100))
    tdee["high"] = round(float(tdee.get("high") or tdee["recommended"] + 100))

    # Optional QR claim block (additive field — absent input renders
    # byte-identically to the pre-QR pipeline).
    qr = data.get("qr")
    if qr is not None:
        if not isinstance(qr, dict):
            raise ValueError("'qr' must be an object")
        kind = qr.get("kind")
        if kind not in VALID_QR_KINDS:
            raise ValueError(f"qr.kind must be one of {sorted(VALID_QR_KINDS)}")
        for field in ("number", "body"):
            value = qr.get(field)
            if not value or not isinstance(value, str):
                raise ValueError(f"Missing required qr field: {field}")
    data["qr"] = qr

    locale = data.get("locale") or {}
    country = (locale.get("country") or "US").upper()
    units = locale.get("units") or ("imperial" if country == "US" else "metric")
    if units not in ("imperial", "metric"):
        raise ValueError("locale.units must be 'imperial' or 'metric'")
    language = (locale.get("language") or "").lower()
    data["locale"] = {
        "country": country,
        "units": units,
        "language": language,
        "lang": resolve_lang(language),  # STRINGS table key
    }
    return data


def resolve_activity(profile: dict) -> tuple:
    """Resolve the planner-calc activity level (and whether it was assumed).

    Falls back to daily steps when activity_level is missing, then to
    lightly_active (the weight-loss-planner default for unclear activity).
    """
    level = profile.get("activity_level")
    if level in ("sedentary", "lightly_active", "moderately_active",
                 "very_active", "extremely_active"):
        return level, False
    steps = profile.get("daily_steps")
    if steps is not None:
        steps = float(steps)
        if steps < 5000:
            return "sedentary", True
        if steps < 8000:
            return "lightly_active", True
        if steps < 12000:
            return "moderately_active", True
        return "very_active", True
    return "lightly_active", True


def bmi_standard_for(locale: dict) -> str:
    if locale["country"] in ASIAN_BMI_COUNTRIES:
        return "asian"
    if locale["language"][:2] in ASIAN_BMI_LANGUAGES:
        return "asian"
    return "who"


# ---------------------------------------------------------------------------
# Plan computation
# ---------------------------------------------------------------------------

def compute_plan(profile: dict, tdee: dict, locale: dict) -> dict:
    weight = profile["weight_kg"]
    goal = profile.get("goal_weight_kg")
    intent = profile["intent"]
    on_glp1 = profile.get("on_glp1", False)
    activity, activity_assumed = resolve_activity(profile)
    bmi_std = bmi_standard_for(locale)
    lang = locale["lang"]

    plan = {
        "intent": intent,
        "weight_kg": weight,
        "goal_weight_kg": goal,
        "activity": activity,
        "activity_assumed": activity_assumed,
        "bmi_standard": bmi_std,
        "language": lang,
        "glp1": on_glp1,
        "rate_kg_per_week": None,
        "daily_deficit": None,
        "weeks": None,
        "estimated_completion": None,
        "timeline_locked": False,
        "floor_clamped": False,
    }

    # Treat a goal at/above current weight under 'lose' as maintenance.
    if intent == "lose" and goal is not None and goal >= weight:
        intent = plan["intent"] = "maintain"

    # ENERGY ANCHOR (product decision, Jason 2026-06-10): the handoff
    # tdee.recommended / tdee.bmr — the numbers the user already saw on the
    # web — are the energy truth for EVERY path. planner-calc provides the
    # methodology on top (pace table, safety floor, calorie target, BMI,
    # macros); forward-calc's re-derived BMR/TDEE is never used.
    bmr = tdee["bmr"]
    tdee_rec = tdee["recommended"]
    floor = run_planner("safety-floor", "--bmr", bmr)["calorie_floor"]
    bmi = run_planner("bmi", "--weight", weight,
                      "--height", profile["height_cm"], "--standard", bmi_std)
    plan.update({
        "bmr": bmr,
        "tdee": tdee_rec,
        "calorie_floor": floor,
        "bmi_current": bmi["bmi"],
        "bmi_current_class": bmi["classification"],
    })

    # GLP-1 path: the shot already suppresses appetite, so the lever is muscle
    # preservation, NOT a prescribed deficit. We force a more protective floor
    # (whichever is higher: planner-calc safety-floor or the sex-specific
    # GLP-1 minimum) and route each intent through the GLP-1 branches below.
    if on_glp1:
        sex_floor = (GLP1_FLOOR_FEMALE if profile["sex"] == "female"
                     else GLP1_FLOOR_MALE)
        glp1_floor = max(floor, sex_floor)
        plan["glp1_floor"] = glp1_floor
        return compute_plan_glp1(plan, profile, tdee_rec, glp1_floor, lang)

    if intent == "lose":
        if goal is not None:
            # Step-3 pace table via planner-calc recommend-rate.
            to_lose = round(weight - goal, 1)
            rate = run_planner("recommend-rate",
                               "--to-lose-kg", to_lose)["rate_default_kg"]
        else:
            # No goal yet: most conservative pace-table default.
            to_lose = None
            rate = NO_GOAL_RATE_KG

        ct = run_planner("calorie-target", "--tdee", tdee_rec, "--rate-kg", rate)
        daily_cal = ct["daily_cal"]
        deficit = ct["daily_deficit"]
        if daily_cal < floor:
            # Same clamping rule planner-calc applies: floor wins, then
            # back-calculate the achievable rate from the actual deficit.
            plan["floor_clamped"] = True
            daily_cal = floor
            deficit = tdee_rec - floor
            rate = round(deficit / 1100, 2)

        # Guarantee: a deficit plan must sit strictly below the burn the
        # user was shown. Only violable with degenerate handoff data
        # (TDEE at/below the safety floor) — fail loudly rather than send
        # a card that reads as broken.
        if not daily_cal < tdee_rec:
            raise ValueError(
                f"handoff TDEE ({tdee_rec}) is at/below the safety floor "
                f"({floor}) — cannot build a deficit plan"
            )

        plan.update({
            "to_lose_kg": to_lose,
            "daily_cal": daily_cal,
            "daily_deficit": deficit,
            "rate_kg_per_week": rate,
        })

        if goal is not None and rate > 0:
            # Timeline re-derived from the anchored (possibly clamped) rate.
            weeks = round(to_lose / rate, 1)
            plan["weeks"] = weeks
            plan["estimated_completion"] = (
                date.today() + timedelta(days=round(weeks * 7))
            ).isoformat()
            bmi_t = run_planner("bmi", "--weight", goal,
                                "--height", profile["height_cm"],
                                "--standard", bmi_std)
            plan["bmi_target"] = bmi_t["bmi"]
            plan["bmi_target_class"] = bmi_t["classification"]
        else:
            plan["timeline_locked"] = True

    elif intent == "maintain":
        plan["daily_cal"] = max(tdee_rec, floor)

    elif intent == "recomp":
        daily_cal = max(tdee_rec - RECOMP_DEFICIT_KCAL, floor)
        plan.update({
            "daily_cal": daily_cal,
            "daily_deficit": tdee_rec - daily_cal,
        })

    else:  # gain
        rate = GAIN_RATE_KG_PER_WEEK
        surplus = round(rate * 1100)
        plan.update({
            "daily_cal": tdee_rec + surplus,
            "daily_deficit": -surplus,
            "rate_kg_per_week": rate,
        })
        if goal is not None and goal > weight:
            weeks = round((goal - weight) / rate, 1)
            plan["weeks"] = weeks
            plan["estimated_completion"] = (
                date.today() + timedelta(days=round(weeks * 7))
            ).isoformat()
        else:
            plan["timeline_locked"] = True

    return finalize_plan(plan, profile, lang)


def compute_plan_glp1(plan: dict, profile: dict, tdee_rec: float,
                      glp1_floor: float, lang: str) -> dict:
    """GLP-1 plan computation. Hero = protein floor for every intent;
    muscle preservation is the lever, not a prescribed deficit.

    - lose (保肌, the p1-06 safety fix): NO deficit / pace / goal date. The
      drug leads the pace; we only hold a protective calorie floor. daily_cal
      = glp1_floor, daily_deficit/rate/completion all None, timeline locked.
    - recomp: keep the existing small-deficit math (clamped to glp1_floor).
    - maintain: eat at maintenance (max of TDEE and the GLP-1 floor).

    Macros are forced to high_protein (1.6 g/kg) for ALL intents in
    finalize_plan via the plan["glp1"] flag.
    """
    intent = plan["intent"]

    # A 'lose' goal at/above current weight is really maintenance (same
    # reframe the non-GLP-1 path applies before the energy anchor).
    if intent == "lose" and plan.get("goal_weight_kg") is not None \
            and plan["goal_weight_kg"] >= plan["weight_kg"]:
        intent = plan["intent"] = "maintain"

    if intent == "lose":
        # Safety fix: do NOT prescribe a deficit/pace/goal date on top of the
        # appetite suppression. Hold the protective floor; let the shot lead.
        plan.update({
            "to_lose_kg": (round(plan["weight_kg"] - plan["goal_weight_kg"], 1)
                           if plan.get("goal_weight_kg") is not None else None),
            "daily_cal": glp1_floor,
            "daily_deficit": None,
            "rate_kg_per_week": None,
            "weeks": None,
            "estimated_completion": None,
            "timeline_locked": True,
        })
    elif intent == "recomp":
        daily_cal = max(tdee_rec - RECOMP_DEFICIT_KCAL, glp1_floor)
        plan.update({
            "daily_cal": daily_cal,
            "daily_deficit": tdee_rec - daily_cal,
        })
    else:  # maintain
        plan["daily_cal"] = max(tdee_rec, glp1_floor)

    return finalize_plan(plan, profile, lang)


def finalize_plan(plan: dict, profile: dict, lang: str) -> dict:
    """Attach card-only richness: macros, focus rules, week-1 checkpoints.
    (Approved override — card only; PLAN.md stays Step-3 compliant and
    never includes these.)"""
    if "macros" not in plan:
        # Macros from the anchored daily target via planner-calc
        # macro-targets (canonical methodology on top of the handoff TDEE).
        # GLP-1 forces high_protein for EVERY intent — muscle preservation
        # (1.6 g/kg) is the lever while the drug holds appetite.
        if plan.get("glp1") or plan["intent"] in ("recomp", "gain"):
            mode = "high_protein"
        else:
            mode = "balanced"
        args = ["macro-targets", "--weight", plan["weight_kg"],
                "--cal", round(plan["daily_cal"]), "--mode", mode]
        goal = plan.get("goal_weight_kg")
        # GLP-1 computes protein off CURRENT body weight for muscle
        # preservation (Jason 2026-06-25), so skip --target-weight on the
        # GLP-1 path. The non-GLP-1 path still uses goal weight when set.
        if goal is not None and plan["intent"] != "maintain" \
                and not plan.get("glp1"):
            args += ["--target-weight", goal]
        plan["macros"] = run_planner(*args)
    plan["first_week"] = [text for _, text in
                          first_week_items(profile, plan["activity"], lang)]
    plan["sample_day"] = sample_day(plan, lang)
    return plan


def first_week_items(profile: dict, activity: str, lang: str) -> list:
    """Merged 'Your First Week' block: SMS cadence checkpoints + the
    rule-based personalized items, deduplicated, capped at 5.

    Items (icon, text), no LLM:
      1. 📸 log every meal (text a photo)        — cadence
      2. ⚖️ weigh in Sat morning                 — cadence
      3. 🍗 protein target at every meal          — cadence (this absorbs
         the old 'palm-sized protein' focus anchor; deduplicated)
      4. → movement slot (first match):
           daily_steps < 5,000 OR sedentary → 10-min walks
           lightly/moderately active        → 2 strength sessions
           very/extremely active            → protect sleep
      5. → hydration: water first, 2L a day
    """
    s = STRINGS[lang]
    # GLP-1 first-week set: protein-floor / floor-defense / weekly weigh /
    # strength / water — the muscle-preservation playbook, not the cadence
    # checkpoints (no "log every meal", no Saturday weigh-in anchor).
    if profile.get("on_glp1"):
        return [
            ("🍗", s["glp1_cp_protein"]),
            ("🛑", s["glp1_cp_floor"]),
            ("⚖️", s["glp1_cp_weigh"]),
            ("🏋️", s["glp1_cp_strength"]),
            ("💧", s["glp1_cp_water"]),
        ]
    steps = profile.get("daily_steps")
    if (steps is not None and float(steps) < 5000) or activity == "sedentary":
        movement = "focus_walk"
    elif activity in ("lightly_active", "moderately_active"):
        movement = "focus_strength"
    else:
        movement = "focus_sleep"
    return [
        ("📸", s["cp_photo"]),
        ("⚖️", s["cp_weigh"]),
        ("🍗", s["cp_protein"]),
        ("→", s[movement]),
        ("→", s["focus_water"]),
    ]


def sample_day(plan: dict, lang: str) -> dict:
    """Deterministic SAMPLE DAY selection from references/meal-templates.md.

    Breakfast is picked by per-meal protein need (protein target ÷ 3,
    per the reference's 25–40g-per-meal guidance); lunch/dinner/snacks
    and the plate formula are the reference's best defaults. zh uses
    Chinese-food equivalents with the same protein-forward structure
    (metric portions, no literal translation of American items).

      need < 32g  → option 0 (lighter breakfast)
      32–37g      → option 1
      ≥ 38g       → option 2 (highest-protein option; zh table has two
                    tiers, so it clamps to the last option)
    """
    s = STRINGS[lang]
    need = plan["macros"]["protein"]["target"] / 3
    if need >= 38:
        idx = 2
    elif need >= 32:
        idx = 1
    else:
        idx = 0
    opts = s["sample_breakfast"]
    return {
        "breakfast": opts[min(idx, len(opts) - 1)],
        "lunch": s["sample_lunch"],
        "dinner": s["sample_dinner"],
        "snacks": s["sample_snacks"],
        "formula": s["sample_formula"],
    }


# ---------------------------------------------------------------------------
# Formatting helpers (language/unit aware)
# ---------------------------------------------------------------------------

def fmt_weight(kg: float, units: str) -> str:
    if units == "imperial":
        return f"{round(kg * 2.205)} lb"
    return f"{round(kg, 1):g} kg"


def fmt_height(cm: float, units: str) -> str:
    if units == "imperial":
        total_in = cm / 2.54
        feet = int(total_in // 12)
        inches = round(total_in - feet * 12)
        if inches == 12:
            feet, inches = feet + 1, 0
        return f"{feet}'{inches}\""
    return f"{round(cm):d} cm"


def fmt_rate(rate_kg: float, units: str, lang: str) -> str:
    """Compact weekly rate for the card tile."""
    if units == "imperial":
        value = f"{round(rate_kg * 2.205, 1):g}"
        return f"{value} 磅/周" if lang == "zh" else f"{value} lb/wk"
    value = f"{round(rate_kg, 2):g}"
    return f"{value} kg/周" if lang == "zh" else f"{value} kg/wk"


def fmt_rate_md(rate_kg: float, units: str, lang: str) -> str:
    """Weekly rate for PLAN.md. zh metric uses the Step-3 'kg / 斤' style."""
    if lang == "zh" and units == "metric":
        jin = round(rate_kg * 2, 1)
        return f"{round(rate_kg, 2):g} kg / {jin:g} 斤"
    if units == "imperial":
        unit = "磅/周" if lang == "zh" else "lb/week"
        return f"{round(rate_kg * 2.205, 1):g} {unit}"
    return f"{round(rate_kg, 2):g} kg/week"


def cal_unit(country: str, lang: str) -> str:
    if lang == "zh":
        return "大卡"
    return "Cal" if country == "US" else "kcal"


def fmt_num(n) -> str:
    return f"{round(n):,}"


def fmt_month_year(iso_date: str, lang: str, short: bool = False) -> str:
    d = date.fromisoformat(iso_date)
    if lang == "zh":
        return f"{d.year}年{d.month}月"
    return d.strftime("%b %Y" if short else "%B %Y")


def fmt_date_label(d: date, lang: str) -> str:
    if lang == "zh":
        return f"{d.year}年{d.month}月{d.day}日"
    return d.strftime("%B %d, %Y").upper()


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------

def build_qr_svg_datauri(number: str, body: str) -> str:
    """Build the SMSTO QR code as an SVG data URI for inline embedding.

    Format choice — `SMSTO:<number>:<body>` (the ZXing "Barcode Contents"
    de-facto standard) over the RFC 5724 `sms:` URI:
      - iOS Camera and Android (Google Lens / ZXing-derived scanners) both
        open the SMS app with number AND body pre-filled from SMSTO; with
        `sms:num:body` iOS fills the number but drops the body, and the
        RFC `sms:num?body=` form needs URL-encoding and historically fails
        to pre-fill on some Android handsets.
      - SMSTO takes the body as plain text, so handoff tokens (Crockford-8
        or profile slugs) need no escaping.

    Pure-python `qrcode` with its SVG factory — no PIL/system deps; imported
    lazily so the no-QR path never needs the package.
    """
    import base64

    import qrcode
    import qrcode.image.svg

    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        border=2,  # quiet zone (the white CSS background pads it further)
        image_factory=qrcode.image.svg.SvgPathImage,
    )
    qr.add_data(f"SMSTO:{number}:{body}")
    qr.make(fit=True)
    svg = qr.make_image().to_string(encoding="unicode")
    b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"


def build_template_vars(plan: dict, profile: dict, locale: dict,
                        qr: dict | None = None) -> dict:
    units = locale["units"]
    lang = locale["lang"]
    s = STRINGS[lang]
    cu = cal_unit(locale["country"], lang)
    intent = plan["intent"]
    glp1 = plan.get("glp1", False)

    stats_bits = [fmt_weight(profile["weight_kg"], units)]
    if plan.get("goal_weight_kg") is not None and intent != "maintain":
        stats_bits[0] += f"  →  {fmt_weight(plan['goal_weight_kg'], units)}"
    stats_bits.append(fmt_height(profile["height_cm"], units))
    stats_bits.append(s["age"].format(age=profile["age_years"]))
    stats_line = "   ·   ".join(stats_bits)

    hero_label = s["hero_maint"] if intent == "maintain" else s["hero_target"]

    # Plan tiles: deficit + pace (Step-3 elements 2 and 3).
    if glp1:
        # GLP-1: hero pivots to the protein floor; tiles adapt by intent.
        hero_label = s["glp1_hero_label"]
        if intent == "recomp":
            tiles = (
                (s["glp1_tile1_recomp_label"], s["glp1_tile1_recomp_value"],
                 s["slight_deficit"]),
                (s["glp1_tile2_recomp_label"], s["glp1_tile2_recomp_value"],
                 s["mirror_note"]),
            )
        elif intent == "maintain":
            # tile1 value = the maintenance calorie target (avoids repeating
            # the "Hold steady" label as its own value).
            tiles = (
                (s["glp1_tile1_maint_label"],
                 s["tile_approx"].format(v=fmt_num(plan["daily_cal"]), cu=cu),
                 s["keep_level"]),
                (s["protein"], s["glp1_tile2_maint_label"],
                 s["glp1_tile2_maint_value"]),
            )
        else:  # lose (保肌) — no prescribed deficit / pace
            tiles = (
                (s["glp1_tile1_lose_label"],
                 s["tile_approx"].format(v=fmt_num(plan["daily_cal"]), cu=cu),
                 s["glp1_tile1_lose_note"]),
                (s["glp1_tile2_lose_label"], s["glp1_tile2_lose_value"],
                 s["glp1_tile2_lose_note"]),
            )
    elif intent == "maintain":
        tiles = (
            (s["goal_lbl"], s["hold_steady"], s["keep_level"]),
            (s["checkin"], s["weekly"], s["weekly_note"]),
        )
    elif intent == "recomp":
        tiles = (
            (s["deficit"], s["tile_approx"].format(v=fmt_num(plan["daily_deficit"]), cu=cu),
             s["slight_deficit"]),
            (s["watch"], s["mirror"], s["mirror_note"]),
        )
    elif intent == "gain":
        tiles = (
            (s["surplus"], s["tile_approx"].format(v=fmt_num(-plan["daily_deficit"]), cu=cu),
             s["above_maint"]),
            (s["weekly_gain"], fmt_rate(plan["rate_kg_per_week"], units, lang),
             s["lean_steady"]),
        )
    else:  # lose
        tiles = (
            (s["deficit"], s["tile_approx"].format(v=fmt_num(plan["daily_deficit"]), cu=cu),
             s["below_burn"]),
            (s["pace"], fmt_rate(plan["rate_kg_per_week"], units, lang),
             s["steady"]),
        )

    # Macros (protein emphasized with its floor).
    macros = plan["macros"]
    protein, fat, carb = macros["protein"], macros["fat"], macros["carb"]

    # Daily rhythm: solid color bars (inline-block for WeasyPrint compat).
    alloc = macros["allocation"]
    bar_colors = ['#dc2353', '#f7b0c9', '#fbe7ec']
    text_colors = ['#ffffff', '#ffffff', '#D73C63']
    meal_names = {k: s["meals"].get(k, k) for k in ["breakfast", "lunch", "dinner"]}
    rhythm_html = '<div class="rhythm-bar-wrap">'
    for i, meal in enumerate(alloc[:3]):
        pct, cal = meal['pct'], meal['cal']
        name = meal_names.get(meal['meal'], meal['meal'])
        width = int(pct * 7.5)
        rhythm_html += (
            f'<div class="rhythm-bar-item">'
            f'<div class="rhythm-bar" style="width:{width}px; background:{bar_colors[i]}">'
            f'<span style="color:{text_colors[i]}; font-size:28px; font-weight:800">{pct}%</span>'
            f'</div>'
            f'<div class="rhythm-bar-name">{name} · {cal} kcal</div>'
            f'</div>'
        )
    rhythm_html += '</div>'

    # Keep legacy vars for backward compat (unused by current template).
    rhythm = [
        (meal_names.get(a["meal"], a["meal"]),
         f"~{fmt_num(a['cal'])}",
         s["of_day"].format(pct=a["pct"]))
        for a in alloc
    ]
    while len(rhythm) < 3:
        rhythm.append(("—", "—", "—"))

    # Sample day: table with protein column split out.
    sd = plan["sample_day"]
    meal_config = [
        ("breakfast", s["meals"]["breakfast"], True),
        ("lunch", s["meals"]["lunch"], False),
        ("dinner", s["meals"]["dinner"], True),
        ("snacks", s["snack_label"], False),
    ]
    header_cols = (s.get("meal_col", "餐次"), s.get("recommend_col", "推荐搭配"),
                   s.get("protein_col", s["protein"]))
    rows = ''
    for key, name, is_pink in meal_config:
        if key in sd:
            text = sd[key]
            # Split protein info from content
            prot_text = ''
            content_text = text
            pm = re.search(r'[———-]+\s*(约?\s*\d+g?\s*蛋白质)', text)
            if pm:
                prot_text = pm.group(1)
                content_text = text[:pm.start()].rstrip('——— -')
            else:
                pm2 = re.search(r'[（(]([^)）]*蛋白质[^)）]*)[)）]', text)
                if pm2:
                    prot_text = pm2.group(1)
                    content_text = text[:pm2.start()].rstrip()
            row_class = ' class="row-pink"' if is_pink else ''
            rows += (
                f'<tr{row_class}>'
                f'<td class="meal-td-tag">{name}</td>'
                f'<td class="meal-td-content">{content_text}</td>'
                f'<td class="meal-td-protein">{prot_text}</td>'
                f'</tr>'
            )
    sample_html = (
        f'<table class="sample-table">'
        f'<thead><tr><td>{header_cols[0]}</td><td>{header_cols[1]}</td><td>{header_cols[2]}</td></tr></thead>'
        f'<tbody>{rows}</tbody></table>'
    )

    # Timeline: single completion month, or the unlock prompt.
    if glp1:
        # GLP-1: no goal-date countdown for any intent — the shot leads the
        # pace. The focus message is the card's takeaway (for lose it's the
        # core SAFETY message), so render it as a soft-pink accent tile with
        # DARK ink — NOT the white-on-white text the non-GLP-1 maintain/recomp
        # focus block uses (that pre-existing block is left untouched).
        if intent == "recomp":
            focus_line = s["recomp_focus"]
        elif intent == "maintain":
            focus_line = s["maintain_focus"]
        else:  # lose (保肌)
            focus_line = s["glp1_focus_lose"]
        timeline_label = s["sec_focus_alt"]
        timeline_html = (
            '<div style="margin-top:14px; background:#fff5f8; '
            'border:2px solid #fbe7ec; border-radius:22px; '
            'padding:30px 36px; box-shadow:0 2px 8px rgba(215,60,99,0.06);">'
            '<div style="font-size:22px; font-weight:700; letter-spacing:3px; '
            f'text-transform:uppercase; color:#D73C63;">{s["glp1_focus_kicker"]}</div>'
            '<div style="margin-top:14px; font-size:36px; line-height:1.4; '
            f'font-weight:700; color:#1a1a2e;">{focus_line}</div>'
            "</div>"
        )
    elif plan.get("estimated_completion"):
        timeline_label = s["sec_timeline"]
        timeline_html = (
            '<div class="goal-tile">'
            f'<div class="goal-label">{s["goal_reached"]}</div>'
            f'<div class="goal-value">{fmt_month_year(plan["estimated_completion"], lang, short=True)}</div>'
            f'<div class="goal-note">{s["weeks_from"].format(w=round(plan["weeks"]))}</div>'
            "</div>"
        )
    elif plan.get("timeline_locked"):
        timeline_label = s["sec_timeline"]
        timeline_html = (
            '<div class="unlock">'
            f'<div class="unlock-title">{s["unlock_title"]}</div>'
            "</div>"
        )
    else:  # maintain / recomp — no timeline concept
        timeline_label = s["sec_focus_alt"]
        focus_line = s["maintain_focus"] if intent == "maintain" else s["recomp_focus"]
        timeline_html = (
            '<div class="goal-tile">'
            f'<div class="goal-label">{s["remember"]}</div>'
            f'<div class="goal-note" style="margin-top:16px; font-size:33px; '
            f'color:#ffffff; font-weight:700;">{focus_line}</div>'
            "</div>"
        )

    # Optional QR claim block (rendered in the timeline/"unlock" area).
    # Absent qr → empty substitution + the historical page height, keeping
    # the no-QR render byte-identical.
    if qr:
        qr_datauri = build_qr_svg_datauri(qr["number"], qr["body"])
        qr_html = (
            '<div class="qr-block">'
            '<table class="qr-row"><tr>'
            f'<td class="qr-cell"><img class="qr-img" src="{qr_datauri}"/></td>'
            '<td class="qr-text">'
            f'<div class="qr-title">{s["qr_title"]}</div>'
            f'<div class="qr-note">{s["qr_note"]}</div>'
            "</td></tr></table></div>"
        )
        page_height = PAGE_HEIGHT_QR_PX
    else:
        qr_html = ""
        page_height = PAGE_HEIGHT_PX

    # Merged first-week block (cadence checkpoints + personalized items).
    first_week_html = "".join(
        f'<div class="checkpoint">'
        f'<span class="icon{" arrow" if icon == "→" else ""}">{icon}</span>'
        f'&nbsp;&nbsp;{text}</div>'
        for icon, text in first_week_items(profile, plan["activity"], lang)
    )

    if glp1:
        plan_title = s["glp1_title"][intent]
        hero_value = fmt_num(plan["macros"]["protein"]["target"])
        hero_unit = s["glp1_hero_unit"]
    else:
        plan_title = s["title_card"][intent]
        hero_value = fmt_num(plan["daily_cal"])
        hero_unit = s["per_day"].format(cu=cu)

    return {
        "page_height": f"{page_height}px",
        "qr_html": qr_html,
        "date_label": fmt_date_label(date.today(), lang),
        "plan_title": plan_title,
        "stats_line": stats_line,
        "hero_label": hero_label,
        "hero_value": hero_value,
        "hero_unit": hero_unit,
        "sec_plan": s["sec_plan"],
        "sec_macros": s["sec_macros"],
        "sec_rhythm": s["sec_rhythm"],
        "sec_sample": s["sec_sample"],
        "sec_first_week": s["sec_first_week"],
        "tile1_label": tiles[0][0],
        "tile1_value": tiles[0][1],
        "tile1_note": tiles[0][2],
        "tile2_label": tiles[1][0],
        "tile2_value": tiles[1][1],
        "tile2_note": tiles[1][2],
        "protein_label": s["protein"],
        "protein_value": f"{round(protein['min'])}–{round(protein['max'])}g",
        "protein_note": s["floor"].format(g=round(protein["min"])),
        "fat_label": s["fat"],
        "fat_value": f"{round(fat['min'])}–{round(fat['max'])}g",
        "fat_note": s["target_note"].format(g=round(fat["target"])),
        "carb_label": s["carbs"],
        "carb_value": f"{round(carb['min'])}–{round(carb['max'])}g",
        "carb_note": s["target_note"].format(g=round(carb["target"])),
        "meal1_name": rhythm[0][0], "meal1_value": rhythm[0][1], "meal1_note": rhythm[0][2],
        "meal2_name": rhythm[1][0], "meal2_value": rhythm[1][1], "meal2_note": rhythm[1][2],
        "meal3_name": rhythm[2][0], "meal3_value": rhythm[2][1], "meal3_note": rhythm[2][2],
        "rhythm_html": rhythm_html,
        "sample_html": sample_html,
        "timeline_section_label": timeline_label,
        "timeline_html": timeline_html,
        "first_week_html": first_week_html,
        "footer_main": s["footer"],
    }


def render_html(template_vars: dict) -> str:
    template = string.Template(TEMPLATE.read_text(encoding="utf-8"))
    return template.substitute(template_vars)


# ---------------------------------------------------------------------------
# PNG pipeline: HTML → PDF (WeasyPrint) → PNG (PyMuPDF), fit under max-bytes
# ---------------------------------------------------------------------------

def html_to_png(html: str, out_path: Path, width: int, max_bytes: int) -> int:
    from weasyprint import HTML  # imported lazily so --help works without deps
    import fitz  # PyMuPDF

    pdf_bytes = HTML(string=html, base_url=str(TEMPLATE.parent)).write_pdf()

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        page = doc[0]
        page_w_pt = page.rect.width  # CSS px * 0.75
        render_width = width
        png = None
        while True:
            zoom = render_width / page_w_pt
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            png = pix.tobytes("png")
            if len(png) <= max_bytes or render_width <= MIN_RENDER_WIDTH:
                break
            render_width = max(MIN_RENDER_WIDTH, int(render_width * 0.85))
    finally:
        doc.close()

    if len(png) > max_bytes:
        raise RuntimeError(
            f"Could not compress PNG under {max_bytes} bytes "
            f"(best effort: {len(png)} bytes at width {render_width})"
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(png)
    return len(png)


# ---------------------------------------------------------------------------
# PLAN.md generation — mirrors the Step-3 presentation
# (user-onboarding-profile/SKILL.md): user info block + the four plan
# elements + short pace explanation. NO macro split (Step-3 compliant —
# the card-only macro override does NOT apply here). Localized via STRINGS.
# The calorie-target line stays parseable in both languages (weekly-report
# matches `每日热量目标|Daily Calorie Target`); a machine-readable HTML
# comment anchor is also emitted for robust downstream parsing.
# ---------------------------------------------------------------------------

def build_plan_markdown(plan: dict, profile: dict, locale: dict) -> str:
    units = locale["units"]
    lang = locale["lang"]
    s = STRINGS[lang]
    cu = cal_unit(locale["country"], lang)
    intent = plan["intent"]

    activity_desc = s["act_desc"][plan["activity"]]
    if plan["activity_assumed"]:
        activity_desc += s["assumed"]

    glp1 = plan.get("glp1", False)

    lines = []
    # GLP-1 uses its own plan heading ("Your GLP-1 Plan"); other intents
    # keep the Step-3 markdown title.
    lines.append(f"# {s['glp1_title'][intent] if glp1 else s['title_md'][intent]}")
    lines.append("")
    lines.append(f"*{s['generated'].format(date=date.today().isoformat())}*")
    lines.append("")
    # Machine-readable anchor (language-independent) for downstream parsers.
    # Stays = round(daily_cal) for GLP-1 too, so weekly-report parsing works.
    lines.append(f"<!-- daily-calorie-target-kcal: {round(plan['daily_cal'])} -->")
    lines.append("")
    lines.append(f"## {s['md_info']}")
    lines.append("")
    lines.append(f"• {s['md_height'].format(v=fmt_height(profile['height_cm'], units))}")
    lines.append(f"• {s['md_weight'].format(v=fmt_weight(profile['weight_kg'], units))}")
    if plan.get("goal_weight_kg") is not None:
        lines.append(f"• {s['md_goal'].format(v=fmt_weight(plan['goal_weight_kg'], units))}")
    lines.append(f"• {s['md_age_sex'].format(age=profile['age_years'], sex=s['sex'][profile['sex']])}")
    lines.append(f"• {s['md_activity'].format(v=activity_desc)}")
    lines.append("")
    lines.append(f"## {s['md_plan']}")
    lines.append("")
    lines.append(f"• {s['md_target'].format(v=fmt_num(plan['daily_cal']), cu=cu)}")

    if glp1:
        # GLP-1: NO prescribed deficit / pace / goal-date lines. The drug
        # leads the pace; we surface the protein floor and let appetite lead.
        protein_target = round(plan["macros"]["protein"]["target"])
        lines.append(f"• {s['md_protein_floor'].format(v=protein_target)}")
        lines.append("")
        if intent == "recomp":
            explanation = s["expl_glp1_recomp"]
        elif intent == "maintain":
            explanation = s["expl_glp1_maintain"]
        else:  # lose (保肌)
            explanation = s["expl_glp1_lose"].format(
                floor=fmt_num(plan["daily_cal"]), cu=cu)
        lines.append(f"*{explanation}*")
        lines.append("")
        return "\n".join(lines)

    deficit = plan.get("daily_deficit")
    if deficit:
        if deficit > 0:
            lines.append(f"• {s['md_deficit'].format(v=fmt_num(deficit), cu=cu)}")
        else:
            lines.append(f"• {s['md_surplus'].format(v=fmt_num(-deficit), cu=cu)}")
    if plan.get("rate_kg_per_week") and intent != "maintain":
        key = "md_rate_gain" if intent == "gain" else "md_rate_loss"
        lines.append(f"• {s[key].format(v=fmt_rate_md(plan['rate_kg_per_week'], units, lang))}")
    if plan.get("estimated_completion"):
        lines.append(f"• {s['md_completion'].format(v=fmt_month_year(plan['estimated_completion'], lang))}")
    elif plan.get("timeline_locked"):
        lines.append(f"• {s['md_unlock']}")
    lines.append("")

    # Short pace explanation, user-perspective, no TDEE/BMR jargon.
    if intent == "lose":
        explanation = s["expl_lose"]
        if plan["activity"] == "sedentary":
            explanation += s["expl_lose_sedentary"]
    elif intent == "maintain":
        explanation = s["expl_maintain"]
    elif intent == "recomp":
        explanation = s["expl_recomp"]
    else:
        explanation = s["expl_gain"]
    lines.append(f"*{explanation}*")
    lines.append("")
    if plan.get("floor_clamped"):
        lines.append(s["floor_note"])
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Render a handoff profile into an MMS plan card PNG + PLAN.md markdown"
    )
    parser.add_argument("--input", required=True, help="Path to input JSON")
    parser.add_argument("--output", required=True, help="Path to output PNG")
    parser.add_argument("--width", type=int, default=1080, help="PNG width in px (default 1080)")
    parser.add_argument("--max-bytes", type=int, default=614400,
                        help="Max PNG size in bytes (default 614400 = 600 KB)")
    args = parser.parse_args()

    try:
        with open(args.input, "r", encoding="utf-8") as f:
            data = json.load(f)
        data = validate_input(data)
        profile, tdee, locale = data["profile"], data["tdee"], data["locale"]

        plan = compute_plan(profile, tdee, locale)

        template_vars = build_template_vars(plan, profile, locale,
                                            qr=data.get("qr"))
        html = render_html(template_vars)

        out_path = Path(args.output).resolve()
        png_bytes = html_to_png(html, out_path, args.width, args.max_bytes)

        plan_markdown = build_plan_markdown(plan, profile, locale)

        print(json.dumps({
            "ok": True,
            "png": str(out_path),
            "bytes": png_bytes,
            "plan": plan,
            "plan_markdown": plan_markdown,
        }, ensure_ascii=False))
    except Exception as exc:  # noqa: BLE001 — contract: error JSON + non-zero exit
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
