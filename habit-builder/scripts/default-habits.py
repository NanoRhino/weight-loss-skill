#!/usr/bin/env python3
"""
Default habit pool — 30 pre-designed habits across 5 lifestyle dimensions.

Usage:
  # List all habits, sorted by default priority
  python3 {baseDir}/scripts/default-habits.py list

  # Recommend top habits for a user, filtered by profile data
  python3 {baseDir}/scripts/default-habits.py recommend \
    --profile '<profile JSON>' \
    [--exclude-ids '["already-active-id", ...]'] \
    [--top 3]
"""

import argparse
import json
import sys

# ── 30 Default Habits ───────────────────────────────────────────────────────
# Each habit has pre-assigned impact/ease/chain scores (1-3).
# The prioritize formula (impact × ease + chain_bonus) gives base priority.
# `recommend` adjusts scores based on user profile gaps.
#
# dimension: meal_rhythm | food_quality | movement | hydration | sleep
# trigger_cadence: every_meal | daily_fixed | daily_random | weekly | conditional

HABITS = [
    # ── Hydration (6) ───────────────────────────────────────────────────────
    {
        "action_id": "water-after-waking",
        "dimension": "hydration",
        "description": "起床后喝一杯水",
        "trigger": "起床后",
        "behavior": "喝一杯温水",
        "trigger_cadence": "daily_fixed",
        "impact": 3, "ease": 3, "chain": True,
        "tags": ["starter", "zero-cost"],
    },
    {
        "action_id": "water-with-meals",
        "dimension": "hydration",
        "description": "每餐配一杯白水",
        "trigger": "吃饭时",
        "behavior": "倒一杯水放在旁边",
        "trigger_cadence": "every_meal",
        "impact": 2, "ease": 3, "chain": False,
        "tags": ["zero-cost"],
    },
    {
        "action_id": "water-before-milk-tea",
        "dimension": "hydration",
        "description": "想喝奶茶时先喝水等10分钟",
        "trigger": "想喝奶茶/饮料时",
        "behavior": "先喝一杯水，等10分钟再决定",
        "trigger_cadence": "conditional",
        "impact": 2, "ease": 1, "chain": False,
        "tags": ["willpower"],
    },
    {
        "action_id": "water-bottle-carry",
        "dimension": "hydration",
        "description": "出门带水杯",
        "trigger": "出门前",
        "behavior": "把水杯放进包里",
        "trigger_cadence": "daily_fixed",
        "impact": 2, "ease": 2, "chain": True,
        "tags": ["environment"],
    },
    {
        "action_id": "replace-soda-sparkling",
        "dimension": "hydration",
        "description": "用气泡水替代碳酸饮料",
        "trigger": "想喝可乐/雪碧时",
        "behavior": "选气泡水",
        "trigger_cadence": "conditional",
        "impact": 2, "ease": 2, "chain": False,
        "tags": ["swap"],
    },
    {
        "action_id": "no-drinks-after-8pm",
        "dimension": "hydration",
        "description": "晚8点后只喝水",
        "trigger": "晚8点后想喝饮料时",
        "behavior": "选白水",
        "trigger_cadence": "conditional",
        "impact": 2, "ease": 1, "chain": False,
        "tags": ["willpower"],
    },

    # ── Meal Rhythm (6) ────────────────────────────────────────────────────
    {
        "action_id": "eat-breakfast",
        "dimension": "meal_rhythm",
        "description": "每天吃早餐",
        "trigger": "起床洗漱后",
        "behavior": "吃任何东西——哪怕一片面包",
        "trigger_cadence": "daily_fixed",
        "impact": 3, "ease": 2, "chain": True,
        "tags": ["foundational"],
    },
    {
        "action_id": "regular-lunch-time",
        "dimension": "meal_rhythm",
        "description": "午餐固定在12-13点",
        "trigger": "到12点时",
        "behavior": "放下手头的事去吃饭",
        "trigger_cadence": "daily_fixed",
        "impact": 2, "ease": 2, "chain": False,
        "tags": [],
    },
    {
        "action_id": "dinner-before-7pm",
        "dimension": "meal_rhythm",
        "description": "晚餐在19点前吃完",
        "trigger": "下午6点",
        "behavior": "开始准备或点餐",
        "trigger_cadence": "daily_fixed",
        "impact": 3, "ease": 2, "chain": True,
        "tags": ["high-leverage"],
    },
    {
        "action_id": "no-eating-after-dinner",
        "dimension": "meal_rhythm",
        "description": "晚餐后不再吃东西",
        "trigger": "晚饭后想吃零食时",
        "behavior": "喝杯水或刷牙",
        "trigger_cadence": "conditional",
        "impact": 3, "ease": 1, "chain": False,
        "tags": ["willpower", "high-leverage"],
    },
    {
        "action_id": "plate-half-veg",
        "dimension": "meal_rhythm",
        "description": "每餐盘子一半是蔬菜",
        "trigger": "盛饭/点餐时",
        "behavior": "先装蔬菜占一半",
        "trigger_cadence": "every_meal",
        "impact": 3, "ease": 2, "chain": False,
        "tags": [],
    },
    {
        "action_id": "slow-eating",
        "dimension": "meal_rhythm",
        "description": "每餐至少吃15分钟",
        "trigger": "开始吃饭时",
        "behavior": "放下筷子嚼完再夹",
        "trigger_cadence": "every_meal",
        "impact": 2, "ease": 1, "chain": False,
        "tags": ["mindful"],
    },

    # ── Food Quality (6) ───────────────────────────────────────────────────
    {
        "action_id": "protein-first",
        "dimension": "food_quality",
        "description": "每餐先吃蛋白质",
        "trigger": "开始吃饭时",
        "behavior": "先吃肉/蛋/豆腐",
        "trigger_cadence": "every_meal",
        "impact": 3, "ease": 3, "chain": False,
        "tags": ["zero-cost", "high-leverage"],
    },
    {
        "action_id": "add-egg-breakfast",
        "dimension": "food_quality",
        "description": "早餐加一个鸡蛋",
        "trigger": "准备早餐时",
        "behavior": "煮/煎一个鸡蛋",
        "trigger_cadence": "daily_fixed",
        "impact": 2, "ease": 3, "chain": False,
        "tags": ["zero-cost"],
    },
    {
        "action_id": "less-white-rice",
        "dimension": "food_quality",
        "description": "米饭减到小半碗",
        "trigger": "盛饭时",
        "behavior": "只盛小半碗",
        "trigger_cadence": "every_meal",
        "impact": 2, "ease": 2, "chain": False,
        "tags": [],
    },
    {
        "action_id": "swap-snack-fruit",
        "dimension": "food_quality",
        "description": "零食换成水果",
        "trigger": "想吃零食时",
        "behavior": "先吃一个水果",
        "trigger_cadence": "conditional",
        "impact": 2, "ease": 2, "chain": False,
        "tags": ["swap"],
    },
    {
        "action_id": "read-nutrition-label",
        "dimension": "food_quality",
        "description": "买包装食品前看营养标签",
        "trigger": "超市/便利店拿食品时",
        "behavior": "翻过来看热量和含糖量",
        "trigger_cadence": "conditional",
        "impact": 1, "ease": 3, "chain": False,
        "tags": ["awareness"],
    },
    {
        "action_id": "cook-one-meal",
        "dimension": "food_quality",
        "description": "每周至少自己做一顿饭",
        "trigger": "周末",
        "behavior": "做一顿简单的饭",
        "trigger_cadence": "weekly",
        "impact": 2, "ease": 1, "chain": True,
        "tags": ["skill-building"],
    },

    # ── Movement (6) ───────────────────────────────────────────────────────
    {
        "action_id": "walk-after-dinner",
        "dimension": "movement",
        "description": "晚饭后散步5分钟",
        "trigger": "吃完晚饭后",
        "behavior": "穿上鞋出门走5分钟",
        "trigger_cadence": "daily_fixed",
        "impact": 3, "ease": 3, "chain": True,
        "tags": ["starter", "zero-cost"],
    },
    {
        "action_id": "take-stairs",
        "dimension": "movement",
        "description": "6层以下走楼梯",
        "trigger": "到电梯口时",
        "behavior": "选楼梯",
        "trigger_cadence": "conditional",
        "impact": 1, "ease": 2, "chain": False,
        "tags": ["environment"],
    },
    {
        "action_id": "standing-break",
        "dimension": "movement",
        "description": "每坐1小时站起来活动2分钟",
        "trigger": "手机/电脑久坐提醒",
        "behavior": "站起来走一圈或拉伸",
        "trigger_cadence": "daily_random",
        "impact": 2, "ease": 2, "chain": False,
        "tags": [],
    },
    {
        "action_id": "morning-stretch",
        "dimension": "movement",
        "description": "起床后拉伸2分钟",
        "trigger": "起床后",
        "behavior": "做2分钟简单拉伸",
        "trigger_cadence": "daily_fixed",
        "impact": 1, "ease": 3, "chain": False,
        "tags": ["starter"],
    },
    {
        "action_id": "weekend-walk-30min",
        "dimension": "movement",
        "description": "周末走路30分钟",
        "trigger": "周六或周日上午",
        "behavior": "出门散步或逛公园",
        "trigger_cadence": "weekly",
        "impact": 2, "ease": 2, "chain": False,
        "tags": [],
    },
    {
        "action_id": "walk-to-nearby",
        "dimension": "movement",
        "description": "1公里内步行不打车",
        "trigger": "要去1公里内的地方时",
        "behavior": "走过去",
        "trigger_cadence": "conditional",
        "impact": 2, "ease": 2, "chain": False,
        "tags": ["environment"],
    },

    # ── Sleep (6) ──────────────────────────────────────────────────────────
    {
        "action_id": "wind-down-alarm",
        "dimension": "sleep",
        "description": "设22:30洗漱闹钟",
        "trigger": "每天22:30",
        "behavior": "闹钟响→关屏幕→去洗漱",
        "trigger_cadence": "daily_fixed",
        "impact": 3, "ease": 2, "chain": True,
        "tags": ["high-leverage"],
    },
    {
        "action_id": "no-phone-in-bed",
        "dimension": "sleep",
        "description": "手机不带上床",
        "trigger": "上床前",
        "behavior": "把手机放在卧室外充电",
        "trigger_cadence": "daily_fixed",
        "impact": 3, "ease": 1, "chain": True,
        "tags": ["environment", "high-leverage"],
    },
    {
        "action_id": "dim-lights-9pm",
        "dimension": "sleep",
        "description": "21点后调暗灯光",
        "trigger": "21点",
        "behavior": "关大灯，开小灯/台灯",
        "trigger_cadence": "daily_fixed",
        "impact": 2, "ease": 3, "chain": True,
        "tags": ["environment"],
    },
    {
        "action_id": "no-caffeine-after-2pm",
        "dimension": "sleep",
        "description": "下午2点后不喝咖啡",
        "trigger": "下午想喝咖啡时",
        "behavior": "选无咖啡因饮品",
        "trigger_cadence": "conditional",
        "impact": 2, "ease": 2, "chain": False,
        "tags": ["swap"],
    },
    {
        "action_id": "move-snacks-away",
        "dimension": "sleep",
        "description": "晚饭后把零食收到高柜",
        "trigger": "收拾厨房时",
        "behavior": "把零食从客厅/桌面收到高柜",
        "trigger_cadence": "daily_fixed",
        "impact": 3, "ease": 3, "chain": True,
        "tags": ["environment", "high-leverage", "starter"],
    },
    {
        "action_id": "sleep-log",
        "dimension": "sleep",
        "description": "每天记录几点睡的",
        "trigger": "起床后",
        "behavior": "回想并记录昨晚几点睡",
        "trigger_cadence": "daily_fixed",
        "impact": 1, "ease": 3, "chain": False,
        "tags": ["awareness"],
    },
]

# ── Profile gap detection ───────────────────────────────────────────────────
# Profile JSON expected keys (all optional):
#   skips_breakfast: bool
#   late_dinner: bool (dinner after 20:00)
#   late_sleeper: bool (sleep after midnight)
#   low_protein: bool
#   low_vegetable: bool
#   high_sugar: bool
#   sedentary: bool
#   low_water: bool
#   high_snacking: bool
#   night_snacking: bool

GAP_BOOST = {
    # profile_key → dimensions to boost (+2 impact)
    "skips_breakfast":  ["meal_rhythm"],
    "late_dinner":      ["meal_rhythm", "sleep"],
    "late_sleeper":     ["sleep"],
    "low_protein":      ["food_quality"],
    "low_vegetable":    ["food_quality", "meal_rhythm"],
    "high_sugar":       ["hydration", "food_quality"],
    "sedentary":        ["movement"],
    "low_water":        ["hydration"],
    "high_snacking":    ["food_quality", "meal_rhythm"],
    "night_snacking":   ["sleep", "meal_rhythm"],
}


def score(habit: dict, profile: dict = None) -> int:
    """Calculate priority score, optionally adjusted by profile gaps."""
    impact = habit["impact"]
    ease = habit["ease"]
    chain = 1 if habit.get("chain") else 0

    # Boost impact for dimensions matching user's gaps
    if profile:
        for key, dims in GAP_BOOST.items():
            if profile.get(key) and habit["dimension"] in dims:
                impact = min(impact + 2, 5)  # cap at 5

    return impact * ease + chain


def cmd_list(args):
    """List all 30 habits sorted by default priority."""
    scored = []
    for h in HABITS:
        s = score(h)
        scored.append({**h, "priority_score": s})
    scored.sort(key=lambda x: x["priority_score"], reverse=True)

    if args.dimension:
        scored = [h for h in scored if h["dimension"] == args.dimension]

    print(json.dumps(scored, ensure_ascii=False, indent=2))


def cmd_recommend(args):
    """Recommend top habits adjusted for user profile."""
    profile = json.loads(args.profile) if args.profile else {}
    exclude = set(json.loads(args.exclude_ids)) if args.exclude_ids else set()
    top = args.top or 5

    scored = []
    for h in HABITS:
        if h["action_id"] in exclude:
            continue
        s = score(h, profile)
        scored.append({**h, "priority_score": s})

    scored.sort(key=lambda x: x["priority_score"], reverse=True)
    print(json.dumps(scored[:top], ensure_ascii=False, indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command")

    ls = sub.add_parser("list", help="List all habits")
    ls.add_argument("--dimension",
                    choices=["hydration","meal_rhythm","food_quality",
                             "movement","sleep"])

    rec = sub.add_parser("recommend", help="Recommend for a user")
    rec.add_argument("--profile", help="JSON: user profile gap flags")
    rec.add_argument("--exclude-ids", dest="exclude_ids",
                     help="JSON array: already active/graduated habit IDs")
    rec.add_argument("--top", type=int, default=5,
                     help="Number of recommendations (default: 5)")

    args = p.parse_args()
    if not args.command:
        p.print_help()
        sys.exit(1)

    {"list": cmd_list, "recommend": cmd_recommend}[args.command](args)


if __name__ == "__main__":
    main()
