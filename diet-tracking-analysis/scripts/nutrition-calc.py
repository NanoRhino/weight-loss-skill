# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
Nutrition calculator for diet-tracking-analysis skill.

Commands:
  detect-meal  — Detect meal type from timestamp, timezone, and meal schedule.
  target       — Compute daily macro targets from weight & calorie goal.
  analyze      — Compute cumulative intake, compare with targets, output status.
  save         — Persist a meal record to today's log file.
  load         — Load today's (or a given date's) meal records.
  evaluate     — Evaluate cumulative intake at a meal checkpoint (range-based).
  check-missing — Check which main meals are missing before the current meal.
  meal-history  — Analyze meal history for a meal type over N days.
  save-recommendation — Save meal recommendations for today.
  weekly-low-cal-check — Check if weekly average calorie intake is below BMR.
  produce-check — Evaluate cumulative vegetable and fruit intake (China region).

Usage:
  python3 nutrition-calc.py detect-meal --tz-offset 28800 --meals 3 \
      [--schedule '{"breakfast":"09:00","lunch":"12:00","dinner":"18:00"}'] \
      [--log '[...]'] [--timestamp 2026-03-17T11:14:13Z]
  python3 nutrition-calc.py target  --weight 65 --cal 1500 [--meals 3]
  python3 nutrition-calc.py analyze --weight 65 --cal 1500 --meals 3 \
      --log '[{"name":"breakfast","calories":379,"protein":24,"carbs":45,"fat":12}]'
  python3 nutrition-calc.py save --data-dir /path/to/data \
      --meal '{"name":"breakfast","meal_type":"breakfast","calories":379,"protein":24,"carbs":45,"fat":12,"foods":[{"name":"boiled eggs x2","calories":144}]}'
  python3 nutrition-calc.py load --data-dir /path/to/data [--date 2026-02-27]
  python3 nutrition-calc.py evaluate --weight 65 --cal 1500 --meals 3 \
      --current-meal lunch --log '[...]'
  python3 nutrition-calc.py check-missing --meals 3 --current-meal lunch --log '[...]'
  python3 nutrition-calc.py meal-history --data-dir /path/to/data --days 30 --meal-type lunch
  python3 nutrition-calc.py save-recommendation --data-dir /path/to/data \
      --meal-type lunch --items '["鸡胸肉+糙米+西兰花", "牛肉面+茶叶蛋", "沙拉+全麦面包+酸奶"]'
  python3 nutrition-calc.py weekly-low-cal-check --data-dir /path/to/data --bmr 1400
  python3 nutrition-calc.py produce-check --meals 3 --current-meal lunch --log '[...]'
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone


def _local_date(tz_offset: int = None) -> str:
    """Return local date as YYYY-MM-DD string.
    If tz_offset (seconds from UTC) is given, compute local date from UTC now.
    Otherwise fall back to server's date.today().
    """
    if tz_offset is not None:
        utc_now = datetime.now(timezone.utc)
        local_dt = utc_now + timedelta(seconds=tz_offset)
        return local_dt.date().isoformat()
    return date.today().isoformat()


# ---------------------------------------------------------------------------
# Backward compatibility: migrate old short field names to full names
# ---------------------------------------------------------------------------

# Mapping from old short keys to new full keys
_SHORT_TO_LONG = {"cal": "calories", "p": "protein", "c": "carbs", "f": "fat"}


def _migrate_meal(meal: dict) -> dict:
    """Convert old short-key meal dicts to full-name keys.

    Handles both top-level fields and nested foods list.
    If both short and long keys exist, long key takes precedence.
    """
    out = {}
    for k, v in meal.items():
        new_key = _SHORT_TO_LONG.get(k, k)
        # Don't overwrite if the long name already exists
        if new_key in out:
            continue
        if k == "foods" and isinstance(v, list):
            out[k] = [_migrate_meal(f) for f in v]
        else:
            out[new_key] = v
    return out


def _migrate_meals(meals: list) -> list:
    """Migrate a list of meal dicts."""
    return [_migrate_meal(m) for m in meals]


# ---------------------------------------------------------------------------
# Meal blocks & aliases
# ---------------------------------------------------------------------------

MEAL_BLOCKS_3 = [
    {"label": "breakfast", "pct": 30, "meals": ["breakfast", "snack_am"]},
    {"label": "lunch",     "pct": 40, "meals": ["lunch", "snack_pm"]},
    {"label": "dinner",    "pct": 30, "meals": ["dinner"]},
]

MEAL_BLOCKS_2 = [
    {"label": "meal_1", "pct": 50, "meals": ["meal_1", "snack_1"]},
    {"label": "meal_2", "pct": 50, "meals": ["meal_2", "snack_2"]},
]

# Alias map: traditional 3-meal names → 2-meal equivalents.
MEAL_ALIAS_2 = {
    "breakfast": "meal_1",
    "snack_am":  "snack_1",
    "lunch":     "meal_1",
    "snack_pm":  "snack_2",
    "dinner":    "meal_2",
}

# ---------------------------------------------------------------------------
# Diet mode configurations
# ---------------------------------------------------------------------------

DIET_MODE_FAT = {
    "usda":          (20, 35),
    "balanced":      (25, 35),
    "high_protein":  (25, 35),
    "low_carb":      (40, 50),
    "keto":          (65, 75),
    "mediterranean": (25, 35),
    "plant_based":   (20, 30),
    "if_16_8":       (25, 35),
    "if_5_2":        (25, 35),
}

DIET_MODE_MACROS = {
    "usda":          {"protein": (10, 35), "carbs": (45, 65), "fat": (20, 35)},
    "balanced":      {"protein": (25, 35), "carbs": (35, 45), "fat": (25, 35)},
    "high_protein":  {"protein": (35, 45), "carbs": (25, 35), "fat": (25, 35)},
    "low_carb":      {"protein": (30, 40), "carbs": (15, 25), "fat": (40, 50)},
    "keto":          {"protein": (20, 25), "carbs": (5, 10),  "fat": (65, 75)},
    "mediterranean": {"protein": (20, 30), "carbs": (40, 50), "fat": (25, 35)},
    "plant_based":   {"protein": (20, 30), "carbs": (45, 55), "fat": (20, 30)},
}

# ---------------------------------------------------------------------------
# Produce tracking constants (China region)
# ---------------------------------------------------------------------------

# Cumulative vegetable target (g) by checkpoint. None = no target at this checkpoint.
# Key: (meals_per_day, block_index)
PRODUCE_VEG_TARGETS: dict = {
    (3, 0): None,   # breakfast block — no vegetable requirement
    (3, 1): 150,    # by lunch — cumulative ≥150g
    (3, 2): 300,    # by dinner — cumulative ≥300g
    (2, 0): 150,    # by meal_1 — cumulative ≥150g
    (2, 1): 300,    # by meal_2 — cumulative ≥300g
}

PRODUCE_FRUIT_DAILY_MIN = 200  # g — minimum daily fruit intake
PRODUCE_FRUIT_DAILY_MAX = 350  # g — maximum daily fruit intake


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_meal_blocks(meals: int) -> list:
    return MEAL_BLOCKS_3 if meals == 3 else MEAL_BLOCKS_2


def resolve_meal_name(meal_name: str, meals: int) -> str:
    """Resolve a meal name, applying 2-meal aliases when needed."""
    if meals == 2 and meal_name in MEAL_ALIAS_2:
        return MEAL_ALIAS_2[meal_name]
    return meal_name


def find_block_index(meal_name: str, meals: int) -> int:
    """Find which block a meal type belongs to."""
    resolved = resolve_meal_name(meal_name, meals)
    for i, block in enumerate(get_meal_blocks(meals)):
        if resolved in block["meals"]:
            return i
    return None


def _in_range(value: float, lo: float, hi: float) -> bool:
    return lo <= value <= hi


def _range_status(value: float, lo: float, hi: float) -> str:
    if value < lo:
        return "low"
    elif value > hi:
        return "high"
    return "on_track"


def _sum_macros(meal_list: list) -> dict:
    s = {"calories": 0, "protein": 0, "carbs": 0, "fat": 0}
    for m in meal_list:
        s["calories"] += m.get("calories", 0)
        s["protein"] += m.get("protein", 0)
        s["carbs"] += m.get("carbs", 0)
        s["fat"] += m.get("fat", 0)
    return {k: round(v, 1) for k, v in s.items()}


def get_log_path(data_dir: str, day: str = None, tz_offset: int = None) -> str:
    day = day or _local_date(tz_offset)
    return os.path.join(data_dir, f"{day}.json")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def calc_targets(weight: float, daily_cal: int, meals: int = 3,
                 mode: str = "balanced") -> dict:
    protein = round(weight * 1.4, 1)
    protein_lo = round(weight * 1.2, 1)
    protein_hi = round(weight * 1.6, 1)

    fat_lo_pct, fat_hi_pct = DIET_MODE_FAT.get(mode, (25, 35))
    fat_mid_pct = (fat_lo_pct + fat_hi_pct) / 2

    fat = round(daily_cal * fat_mid_pct / 100 / 9, 1)
    fat_lo = round(daily_cal * fat_lo_pct / 100 / 9, 1)
    fat_hi = round(daily_cal * fat_hi_pct / 100 / 9, 1)

    carb = round((daily_cal - protein * 4 - fat * 9) / 4, 1)
    carb_lo = round((daily_cal - protein_hi * 4 - fat_hi * 9) / 4, 1)
    carb_hi = round((daily_cal - protein_lo * 4 - fat_lo * 9) / 4, 1)

    cal_lo = daily_cal - 100
    cal_hi = daily_cal + 100

    blocks = get_meal_blocks(meals)
    alloc = []
    for b in blocks:
        alloc.append({"meal": b["label"], "pct": b["pct"],
                       "calories": round(daily_cal * b["pct"] / 100)})

    return {
        "daily_calories": daily_cal,
        "calories_range": {"min": cal_lo, "max": cal_hi},
        "weight": weight,
        "meals": meals,
        "protein": {"target": protein, "min": protein_lo, "max": protein_hi},
        "fat": {"target": fat, "min": fat_lo, "max": fat_hi},
        "carb": {"target": carb, "min": carb_lo, "max": carb_hi},
        "allocation": alloc,
    }


def analyze(weight: float, daily_cal: int, meals: int, log: list,
            mode: str = "balanced") -> dict:
    log = _migrate_meals(log)
    targets = calc_targets(weight, daily_cal, meals, mode)

    cum = {"calories": 0, "protein": 0, "carbs": 0, "fat": 0}
    meal_details = []
    for entry in log:
        cum["calories"] += entry.get("calories", 0)
        cum["protein"] += entry.get("protein", 0)
        cum["carbs"] += entry.get("carbs", 0)
        cum["fat"] += entry.get("fat", 0)
        meal_details.append({
            "name": entry.get("name", ""),
            "meal_type": entry.get("meal_type", ""),
            "calories": entry.get("calories", 0),
            "protein": entry.get("protein", 0),
            "carbs": entry.get("carbs", 0),
            "fat": entry.get("fat", 0),
        })

    for k in cum:
        cum[k] = round(cum[k], 1)

    pct_cal = round(cum["calories"] / daily_cal * 100) if daily_cal else 0
    remain = {
        "calories": round(daily_cal - cum["calories"], 1),
        "protein": round(targets["protein"]["target"] - cum["protein"], 1),
        "carbs": round(targets["carb"]["target"] - cum["carbs"], 1),
        "fat": round(targets["fat"]["target"] - cum["fat"], 1),
    }

    status = {
        "calories": _range_status(cum["calories"], targets["calories_range"]["min"], targets["calories_range"]["max"]),
        "protein": _range_status(cum["protein"], targets["protein"]["min"], targets["protein"]["max"]),
        "carbs": _range_status(cum["carbs"], targets["carb"]["min"], targets["carb"]["max"]),
        "fat": _range_status(cum["fat"], targets["fat"]["min"], targets["fat"]["max"]),
    }

    return {
        "targets": targets,
        "meals": meal_details,
        "cumulative": cum,
        "pct_calories": pct_cal,
        "remaining": remain,
        "status": status,
    }


def _resolve_tz_offset(workspace_dir: str) -> int:
    """Try to read tz_offset from workspace files, fallback to 28800 (UTC+8)."""
    import re
    # Try timezone.json
    tz_json = os.path.join(workspace_dir, "data", "timezone.json")
    if os.path.isfile(tz_json):
        try:
            with open(tz_json) as f:
                d = json.load(f)
            v = d.get("tz_offset") or d.get("tzOffset")
            if v is not None:
                return int(v)
        except Exception:
            pass
    # Try USER.md
    user_md = os.path.join(workspace_dir, "USER.md")
    if os.path.isfile(user_md):
        try:
            with open(user_md) as f:
                text = f.read()
            m = re.search(r'TZ Offset[:\s]*(\d+)', text)
            if m:
                return int(m.group(1))
        except Exception:
            pass
    return 28800  # default UTC+8


def _check_pending_feedback(workspace_dir: str) -> dict:
    """Check short-term.json for a pending guided-feedback reply.
    Returns a warning dict if found, None otherwise.
    This reads the file in real-time (not from agent's cached session start)."""
    st_path = os.path.join(workspace_dir, "memory", "short-term.json")
    if not os.path.isfile(st_path):
        return None
    try:
        with open(st_path, 'r', encoding='utf-8') as f:
            entries = json.load(f)
        for entry in entries:
            if entry.get("topic") == "guided-feedback-pending-reply":
                gf = entry.get("_guided_feedback", {})
                return {
                    "WARNING": "A preference survey question was sent to the user. "
                               "If the user's NEXT message is a number (1/2/3) or short text, "
                               "it is a reply to the preference question, NOT a food log or clarification reply. "
                               "Route to notification-composer 'Handling replies' section.",
                    "question_id": gf.get("question_id", ""),
                    "hint": entry.get("summary", "")
                }
    except Exception:
        pass
    return None


def _check_ambiguous_foods(meal: dict) -> list:
    """Check if any foods in the meal match the ambiguous-foods dictionary.
    Returns a list of clarification prompts for foods that need user input."""
    ambiguous_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'references', 'ambiguous-foods.json')
    if not os.path.isfile(ambiguous_path):
        return []
    try:
        with open(ambiguous_path, 'r', encoding='utf-8') as f:
            dictionary = json.load(f)
    except Exception:
        return []

    clarifications = []
    foods = meal.get("foods", [])
    for food_item in foods:
        food_name = food_item.get("name", "")
        if not food_name:
            continue
        for entry in dictionary:
            keyword = entry.get("keyword", "")
            if keyword not in food_name:
                continue
            # Check if user already specified a variant
            excludes = entry.get("exclude", [])
            already_specified = any(ex in food_name for ex in excludes)
            if already_specified:
                continue
            # Found ambiguous food — build clarification
            variants = entry.get("variants", [])
            default_variant = next((v for v in variants if v.get("default")), variants[0] if variants else None)
            emoji = entry.get("emoji", "🤔")
            hint = entry.get("hint", f"{keyword}已先按{default_variant['name'] if default_variant else '默认'}记录，如果不是告诉我，我来改～")
            clarifications.append({
                "food": food_name,
                "keyword": keyword,
                "hint": f"{emoji} {hint}",
                "default_used": default_variant["name"] if default_variant else None,
                "default_calories": default_variant["calories"] if default_variant else None
            })
            break  # One match per food item
    return clarifications


def save_meal(data_dir: str, meal: dict, day: str = None, tz_offset: int = None,
              workspace_dir: str = None) -> dict:
    """Save a meal to the daily log. Same meal name overwrites (supports corrections).
    
    Auto-runs guided-feedback increment+next after saving. workspace_dir is
    auto-inferred from data_dir (../../) if not provided.
    """
    os.makedirs(data_dir, exist_ok=True)
    meal = _migrate_meal(meal)
    path = get_log_path(data_dir, day, tz_offset)

    existing: list = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            existing = _migrate_meals(json.load(f))

    meal_name = meal.get("name", "")
    replaced = False
    for i, m in enumerate(existing):
        if m.get("name") == meal_name:
            existing[i] = meal
            replaced = True
            break
    if not replaced:
        existing.append(meal)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    result = {"saved": True, "file": path, "meals_count": len(existing), "meals": existing}

    # Check for pending guided-feedback reply (real-time file read, not cached)
    ws = workspace_dir or os.path.normpath(os.path.join(os.path.abspath(data_dir), '..', '..'))
    pending_hint = _check_pending_feedback(ws)
    if pending_hint:
        result["⚠️ GUIDED_FEEDBACK_PENDING"] = pending_hint

    # Check for ambiguous foods that need clarification
    clarifications = _check_ambiguous_foods(meal)
    if clarifications:
        result["needs_clarification"] = clarifications

    # Auto-run guided-feedback increment+next
    ws = workspace_dir or os.path.normpath(os.path.join(os.path.abspath(data_dir), '..', '..'))
    gf_script = os.path.normpath(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        '..', 'notification-manager', 'scripts', 'guided-feedback-state.py'))
    if os.path.isfile(gf_script):
        try:
            # Resolve tz_offset: explicit arg > timezone.json > USER.md > default 28800
            if tz_offset is not None and tz_offset != 0:
                tz = str(tz_offset)
            else:
                tz = str(_resolve_tz_offset(ws))
            inc_out = subprocess.run(
                [sys.executable, gf_script, '--workspace-dir', ws, '--tz-offset', tz, 'increment'],
                capture_output=True, text=True, timeout=10
            )
            inc_result = json.loads(inc_out.stdout) if inc_out.stdout.strip() else {}
            next_out = subprocess.run(
                [sys.executable, gf_script, '--workspace-dir', ws, '--tz-offset', tz, 'next'],
                capture_output=True, text=True, timeout=10
            )
            next_result = json.loads(next_out.stdout) if next_out.stdout.strip() else {}
            result["guided_feedback"] = {"increment": inc_result, "next": next_result}

            # Auto-create cron if scheduling is needed
            if next_result.get("action") == "schedule":
                question_id = next_result.get("question_id", "")
                # Read channel info from workspace
                channel_src = os.path.join(ws, 'channel-source.json')
                channel = "wechat"
                to_id = ""
                agent_id = ""
                if os.path.isfile(channel_src):
                    with open(channel_src) as csf:
                        cs = json.load(csf)
                    channel = cs.get("channel", "wechat")
                    to_id = cs.get("senderId", "")
                # Infer agent-id from workspace dir name
                ws_basename = os.path.basename(os.path.normpath(ws))
                if ws_basename.startswith("workspace-"):
                    agent_id = ws_basename[len("workspace-"):]

                if agent_id:
                    # Schedule at 21:00 local time today (or tomorrow if past 21:00)
                    from datetime import datetime, timezone, timedelta
                    tz_sec = int(tz)
                    local_tz = timezone(timedelta(seconds=tz_sec))
                    now_local = datetime.now(local_tz)
                    target = now_local.replace(hour=21, minute=0, second=0, microsecond=0)
                    if now_local >= target:
                        target += timedelta(days=1)
                    at_iso = target.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

                    cron_cmd = [
                        "openclaw", "cron", "add",
                        "--agent", agent_id,
                        "--session", "isolated",
                        "--name", f"Guided feedback: {question_id}",
                        "--message", f"Run notification-composer for guided-feedback {question_id}.",
                        "--announce",
                        "--channel", channel,
                        "--at", at_iso,
                        "--delete-after-run",
                        "--json",
                    ]
                    if to_id:
                        cron_cmd.extend(["--to", to_id])
                    # Run in background — openclaw cron add can take 30-60s due to
                    # Kafka plugin initialization. We don't need to wait for it.
                    cron_proc = subprocess.Popen(
                        cron_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                    result["guided_feedback"]["cron_created"] = True
                    result["guided_feedback"]["cron_pid"] = cron_proc.pid

                    # Update status to scheduled (fire-and-forget, cron is async)
                    subprocess.run(
                        [sys.executable, gf_script, '--workspace-dir', ws, '--tz-offset', tz,
                         'update', '--question-id', question_id, '--new-status', 'scheduled'],
                        capture_output=True, text=True, timeout=10
                    )
                    result["guided_feedback"]["scheduled"] = question_id
        except Exception as e:
            result["guided_feedback"] = {"error": str(e)}

    return result


def load_meals(data_dir: str, day: str = None, tz_offset: int = None) -> dict:
    """Load all meals for a given day, migrating old format if needed."""
    path = get_log_path(data_dir, day, tz_offset)
    resolved_day = day or _local_date(tz_offset)
    if not os.path.exists(path):
        return {"date": resolved_day, "meals": [], "meals_count": 0}
    with open(path, "r", encoding="utf-8") as f:
        meals = _migrate_meals(json.load(f))
    return {"date": resolved_day, "meals": meals, "meals_count": len(meals)}


def evaluate(weight: float, daily_cal: int, meals: int,
             current_meal: str, log: list,
             assumed_meals: list = None,
             mode: str = "balanced") -> dict:
    """Evaluate cumulative intake at the checkpoint for *current_meal*.

    Uses range-based evaluation:
    - Each checkpoint scales daily min/max ranges by the checkpoint percentage.
    - Adjustment is needed when: calories outside checkpoint kcal range
      OR 2+ macros outside their checkpoint ranges.
    """
    log = _migrate_meals(log)
    if assumed_meals:
        assumed_meals = _migrate_meals(assumed_meals)

    targets = calc_targets(weight, daily_cal, meals, mode)
    blocks = get_meal_blocks(meals)

    block_idx = find_block_index(current_meal, meals)
    if block_idx is None:
        return {"error": f"Unknown meal name: {current_meal}"}

    checkpoint_pct = sum(blocks[i]["pct"] for i in range(block_idx + 1))

    checkpoint_meal_names: set[str] = set()
    for i in range(block_idx + 1):
        checkpoint_meal_names.update(blocks[i]["meals"])

    logged_names = {resolve_meal_name(m.get("name", ""), meals) for m in log}

    checkpoint_log = [m for m in log
                      if resolve_meal_name(m.get("name", ""), meals) in checkpoint_meal_names]

    missing_meals: list = []
    for i in range(block_idx + 1):
        main_meal = blocks[i]["meals"][0]
        if main_meal not in logged_names:
            missing_meals.append(main_meal)

    actual = _sum_macros(checkpoint_log)

    cp_target = {
        "calories": round(daily_cal * checkpoint_pct / 100),
        "protein": round(targets["protein"]["target"] * checkpoint_pct / 100, 1),
        "carbs": round(targets["carb"]["target"] * checkpoint_pct / 100, 1),
        "fat": round(targets["fat"]["target"] * checkpoint_pct / 100, 1),
    }

    cp_range = {
        "calories_min": round(targets["calories_range"]["min"] * checkpoint_pct / 100),
        "calories_max": round(targets["calories_range"]["max"] * checkpoint_pct / 100),
        "protein_min": round(targets["protein"]["min"] * checkpoint_pct / 100, 1),
        "protein_max": round(targets["protein"]["max"] * checkpoint_pct / 100, 1),
        "carbs_min": round(targets["carb"]["min"] * checkpoint_pct / 100, 1),
        "carbs_max": round(targets["carb"]["max"] * checkpoint_pct / 100, 1),
        "fat_min": round(targets["fat"]["min"] * checkpoint_pct / 100, 1),
        "fat_max": round(targets["fat"]["max"] * checkpoint_pct / 100, 1),
    }

    adjusted = dict(actual)
    if assumed_meals:
        for m in assumed_meals:
            if resolve_meal_name(m.get("name", ""), meals) in checkpoint_meal_names:
                adjusted["calories"] = round(adjusted["calories"] + m.get("calories", 0), 1)
                adjusted["protein"] = round(adjusted["protein"] + m.get("protein", 0), 1)
                adjusted["carbs"] = round(adjusted["carbs"] + m.get("carbs", 0), 1)
                adjusted["fat"] = round(adjusted["fat"] + m.get("fat", 0), 1)

    status = {
        "calories": _range_status(actual["calories"], cp_range["calories_min"], cp_range["calories_max"]),
        "protein": _range_status(actual["protein"], cp_range["protein_min"], cp_range["protein_max"]),
        "carbs": _range_status(actual["carbs"], cp_range["carbs_min"], cp_range["carbs_max"]),
        "fat": _range_status(actual["fat"], cp_range["fat_min"], cp_range["fat_max"]),
    }

    cal_outside = not _in_range(actual["calories"], cp_range["calories_min"], cp_range["calories_max"])
    macros_outside = sum(1 for k in ["protein", "carbs", "fat"] if status[k] != "on_track")
    needs_adjustment = cal_outside or macros_outside >= 2

    suggestion_base = adjusted if assumed_meals else actual
    diff = {
        "calories": round(cp_target["calories"] - suggestion_base["calories"], 1),
        "protein": round(cp_target["protein"] - suggestion_base["protein"], 1),
        "carbs": round(cp_target["carbs"] - suggestion_base["carbs"], 1),
        "fat": round(cp_target["fat"] - suggestion_base["fat"], 1),
    }

    return {
        "current_meal": current_meal,
        "checkpoint_pct": checkpoint_pct,
        "checkpoint_target": cp_target,
        "checkpoint_range": cp_range,
        "actual": actual,
        "adjusted": adjusted if assumed_meals else None,
        "status": status,
        "needs_adjustment": needs_adjustment,
        "diff_for_suggestions": diff,
        "missing_meals": missing_meals,
        "meals_included": [m.get("name") for m in checkpoint_log],
        "resolved_meal": resolve_meal_name(current_meal, meals),
    }


def check_missing(meals: int, current_meal: str, log: list) -> dict:
    log = _migrate_meals(log)
    blocks = get_meal_blocks(meals)
    block_idx = find_block_index(current_meal, meals)
    if block_idx is None:
        return {"error": f"Unknown meal name: {current_meal}"}

    logged_names = {resolve_meal_name(m.get("name", ""), meals) for m in log}

    missing: list = []
    for i in range(block_idx):
        main_meal = blocks[i]["meals"][0]
        if main_meal not in logged_names:
            missing.append({
                "name": main_meal,
                "expected_pct": blocks[i]["pct"],
            })

    return {
        "current_meal": current_meal,
        "missing": missing,
        "has_missing": len(missing) > 0,
    }


def produce_check(meals: int, current_meal: str, log: list) -> dict:
    """Evaluate cumulative vegetable and fruit intake at the current checkpoint.

    Vegetables: cumulative target based on checkpoint (None = no target at that point).
    Fruits: checked only at the final meal of the day (200–350 g daily total).

    Meal JSON records may include optional fields:
      - vegetables_g: grams of vegetables in this meal
      - fruits_g: grams of fruit in this meal
    Missing fields default to 0.
    """
    log = _migrate_meals(log)
    blocks = get_meal_blocks(meals)
    block_idx = find_block_index(current_meal, meals)
    if block_idx is None:
        return {"error": f"Unknown meal name: {current_meal}"}

    checkpoint_meal_names: set[str] = set()
    for i in range(block_idx + 1):
        checkpoint_meal_names.update(blocks[i]["meals"])

    checkpoint_log = [
        m for m in log
        if resolve_meal_name(m.get("name", ""), meals) in checkpoint_meal_names
    ]

    veg_total = round(sum((m.get("vegetables_g") or 0) for m in checkpoint_log), 1)
    fruit_total = round(sum((m.get("fruits_g") or 0) for m in checkpoint_log), 1)

    is_final = block_idx == len(blocks) - 1

    veg_target = PRODUCE_VEG_TARGETS.get((meals, block_idx))
    has_veg_target = veg_target is not None

    veg_status: str | None = None
    if has_veg_target:
        veg_status = "on_track" if veg_total >= veg_target else "low"

    fruit_status: str | None = None
    if is_final:
        if fruit_total < PRODUCE_FRUIT_DAILY_MIN:
            fruit_status = "low"
        elif fruit_total > PRODUCE_FRUIT_DAILY_MAX:
            fruit_status = "high"
        else:
            fruit_status = "on_track"

    return {
        "current_meal": current_meal,
        "is_final_meal": is_final,
        "vegetables_actual_g": veg_total,
        "vegetables_target_g": veg_target,
        "has_vegetable_target": has_veg_target,
        "vegetable_status": veg_status,
        "fruits_actual_g": fruit_total,
        "fruits_daily_min_g": PRODUCE_FRUIT_DAILY_MIN if is_final else None,
        "fruits_daily_max_g": PRODUCE_FRUIT_DAILY_MAX if is_final else None,
        "fruit_status": fruit_status,
    }


def weekly_low_cal_check(data_dir: str, bmr: float,
                         ref_date: str = None, tz_offset: int = None) -> dict:
    end = date.fromisoformat(ref_date) if ref_date else date.fromisoformat(_local_date(tz_offset))
    calorie_floor = max(bmr, 1000)

    daily_totals: list[dict] = []
    days_below: list[str] = []

    for offset in range(7):
        day = (end - timedelta(days=offset)).isoformat()
        path = get_log_path(data_dir, day)
        if not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            meals = _migrate_meals(json.load(f))
        day_cal = round(sum(m.get("calories", 0) for m in meals), 1)
        daily_totals.append({"date": day, "calories": day_cal})
        if day_cal < calorie_floor:
            days_below.append(day)

    logged_days = len(daily_totals)
    avg_cal = round(sum(d["calories"] for d in daily_totals) / logged_days, 1) if logged_days else 0

    below_floor = avg_cal < calorie_floor if logged_days > 0 else False

    return {
        "period_end": end.isoformat(),
        "logged_days": logged_days,
        "daily_totals": sorted(daily_totals, key=lambda d: d["date"]),
        "weekly_avg_calories": avg_cal,
        "bmr": bmr,
        "calorie_floor": calorie_floor,
        "days_below_floor": days_below,
        "days_below_count": len(days_below),
        "below_floor": below_floor,
    }


# ---------------------------------------------------------------------------
# Diet pattern detection
# ---------------------------------------------------------------------------

def _calc_macro_pcts(meals: list):
    meals = _migrate_meals(meals)
    total_cal = sum(m.get("calories", 0) for m in meals)
    total_p = sum(m.get("protein", 0) for m in meals)
    total_c = sum(m.get("carbs", 0) for m in meals)
    total_f = sum(m.get("fat", 0) for m in meals)

    if total_cal < 500:
        return None

    return {
        "calories": round(total_cal, 1),
        "protein_pct": round(total_p * 4 / total_cal * 100, 1),
        "carbs_pct": round(total_c * 4 / total_cal * 100, 1),
        "fat_pct": round(total_f * 9 / total_cal * 100, 1),
    }


def _mode_distance(p_pct: float, c_pct: float, f_pct: float,
                   mode: str) -> float:
    ranges = DIET_MODE_MACROS.get(mode)
    if not ranges:
        return float("inf")

    dist = 0.0
    for actual, key in [(p_pct, "protein"), (c_pct, "carbs"), (f_pct, "fat")]:
        lo, hi = ranges[key]
        if actual < lo:
            dist += lo - actual
        elif actual > hi:
            dist += actual - hi
    return dist


def _matches_mode(p_pct: float, c_pct: float, f_pct: float,
                  mode: str) -> bool:
    return _mode_distance(p_pct, c_pct, f_pct, mode) == 0


def detect_diet_pattern(data_dir: str, current_mode: str,
                        ref_date: str = None, tz_offset: int = None) -> dict:
    end = date.fromisoformat(ref_date) if ref_date else date.fromisoformat(_local_date(tz_offset))

    daily_splits: list[dict] = []
    for offset in range(7):
        day = (end - timedelta(days=offset)).isoformat()
        path = get_log_path(data_dir, day)
        if not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            meals = json.load(f)
        pcts = _calc_macro_pcts(meals)
        if pcts is not None:
            daily_splits.append({"date": day, **pcts})
        if len(daily_splits) >= 3:
            break

    if len(daily_splits) < 3:
        return {
            "has_pattern": False,
            "reason": "insufficient_data",
            "days_found": len(daily_splits),
            "daily_splits": sorted(daily_splits, key=lambda d: d["date"]),
        }

    avg_p = round(sum(d["protein_pct"] for d in daily_splits) / 3, 1)
    avg_c = round(sum(d["carbs_pct"] for d in daily_splits) / 3, 1)
    avg_f = round(sum(d["fat_pct"] for d in daily_splits) / 3, 1)
    avg_split = {"protein_pct": avg_p, "carbs_pct": avg_c, "fat_pct": avg_f}

    effective_current = current_mode
    if current_mode in ("if_16_8", "if_5_2"):
        effective_current = "balanced"

    current_dist = _mode_distance(avg_p, avg_c, avg_f, effective_current)

    best_mode = None
    best_dist = float("inf")
    for mode in DIET_MODE_MACROS:
        dist = _mode_distance(avg_p, avg_c, avg_f, mode)
        if dist < best_dist:
            best_dist = dist
            best_mode = mode

    all_days_match = all(
        _mode_distance(d["protein_pct"], d["carbs_pct"], d["fat_pct"], best_mode) <=
        _mode_distance(d["protein_pct"], d["carbs_pct"], d["fat_pct"], effective_current)
        for d in daily_splits
    )

    mismatch = (best_mode != effective_current
                and best_dist < current_dist
                and all_days_match)

    pros_cons = _get_pros_cons(effective_current, best_mode) if mismatch else None

    return {
        "has_pattern": mismatch,
        "current_mode": current_mode,
        "effective_current_mode": effective_current,
        "detected_mode": best_mode if mismatch else None,
        "current_mode_distance": round(current_dist, 1),
        "detected_mode_distance": round(best_dist, 1),
        "avg_split": avg_split,
        "daily_splits": sorted(daily_splits, key=lambda d: d["date"]),
        "days_found": len(daily_splits),
        "all_days_consistent": all_days_match,
        "pros_cons": pros_cons,
    }


def _get_pros_cons(current_mode: str, detected_mode: str) -> dict:
    mode_info = {
        "balanced": {
            "name": "Balanced / Flexible",
            "pros": [
                "No food restrictions — highest flexibility and adherence",
                "Easy to maintain long-term",
                "Well-suited for beginners",
            ],
            "cons": [
                "Less targeted than specialized modes",
                "Requires tracking to stay on course",
            ],
        },
        "high_protein": {
            "name": "High-Protein",
            "pros": [
                "Better muscle preservation during calorie deficit",
                "Higher satiety — feel fuller longer",
                "Increased thermic effect of food",
            ],
            "cons": [
                "Can feel monotonous — requires rotating protein sources",
                "May be harder to hit protein targets consistently",
                "Higher food cost (protein sources tend to be pricier)",
            ],
        },
        "low_carb": {
            "name": "Low-Carb",
            "pros": [
                "Reduced hunger and more stable energy for many people",
                "Lower insulin response",
                "Can reduce bloating",
            ],
            "cons": [
                "Fiber intake may drop — need to eat plenty of vegetables",
                "Can feel restrictive for carb lovers",
                "May reduce exercise performance initially",
            ],
        },
        "keto": {
            "name": "Keto",
            "pros": [
                "Strong appetite suppression after adaptation",
                "High fat intake increases meal satisfaction",
            ],
            "cons": [
                "Extremely restrictive — hard to sustain socially",
                "Keto flu during adaptation (1-2 weeks)",
                "Risk of nutrient deficiencies without careful planning",
                "Not recommended below 1,800 kcal/day",
            ],
        },
        "mediterranean": {
            "name": "Mediterranean",
            "pros": [
                "Strong evidence for cardiovascular health",
                "Feels like eating well rather than dieting",
                "Rich in healthy fats and whole foods",
            ],
            "cons": [
                "Olive oil and nuts are calorie-dense — portions need care",
                "May require more cooking and meal prep",
            ],
        },
        "plant_based": {
            "name": "Plant-Based",
            "pros": [
                "High fiber naturally increases satiety",
                "Associated with lower heart disease risk",
                "Often lower calorie density",
            ],
            "cons": [
                "Hitting protein targets is harder without animal products",
                "Requires more intentional meal planning",
                "May need B12 and other supplements",
            ],
        },
        "usda": {
            "name": "Healthy U.S.-Style (USDA)",
            "pros": [
                "Government-backed, evidence-based guidelines",
                "No food groups excluded — very flexible",
                "Good baseline for general health",
            ],
            "cons": [
                "Broad ranges may feel too vague for specific goals",
                "Less targeted for weight loss than specialized modes",
            ],
        },
    }

    detected_info = mode_info.get(detected_mode, {})
    current_info = mode_info.get(current_mode, {})

    return {
        "switch_to": detected_mode,
        "switch_to_name": detected_info.get("name", detected_mode),
        "switch_from": current_mode,
        "switch_from_name": current_info.get("name", current_mode),
        "pros": detected_info.get("pros", []),
        "cons": detected_info.get("cons", []),
    }


# ---------------------------------------------------------------------------
# Meal history & recommendations
# ---------------------------------------------------------------------------

def _get_recommendations_dir(data_dir: str) -> str:
    """Return the recommendations directory, sibling to data_dir."""
    return os.path.join(os.path.dirname(data_dir), "recommendations")


def meal_history(data_dir: str, meal_type: str, days: int = 30,
                 ref_date: str = None, tz_offset: int = None) -> dict:
    """Analyze meal history for a given meal type over the last N days.

    Returns top foods by frequency, average macros, recent 3 days of actual
    meals, and recent 3 days of recommendations.
    """
    end = date.fromisoformat(ref_date) if ref_date else date.fromisoformat(_local_date(tz_offset))

    food_counts: dict[str, list[float]] = {}  # name -> list of calorie values
    macro_sums = {"calories": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0}
    days_with_data = 0
    recent_3: list[dict] = []

    for offset in range(days):
        day = (end - timedelta(days=offset)).isoformat()
        path = get_log_path(data_dir, day)
        if not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            all_meals = _migrate_meals(json.load(f))

        matched = [m for m in all_meals if m.get("meal_type") == meal_type
                    or m.get("name") == meal_type]
        if not matched:
            continue

        days_with_data += 1

        for m in matched:
            macro_sums["calories"] += m.get("calories", 0)
            macro_sums["protein"] += m.get("protein", 0)
            macro_sums["carbs"] += m.get("carbs", 0)
            macro_sums["fat"] += m.get("fat", 0)

            for food in m.get("foods", []):
                fname = food.get("name", "")
                if not fname:
                    continue
                fcal = food.get("calories", 0)
                food_counts.setdefault(fname, []).append(fcal)

        if len(recent_3) < 3:
            day_foods = []
            for m in matched:
                day_foods.extend(f.get("name", "") for f in m.get("foods", [])
                                 if f.get("name"))
            recent_3.append({"date": day, "foods": day_foods})

    # Build top foods
    top_foods = sorted(food_counts.items(), key=lambda x: len(x[1]),
                       reverse=True)[:10]
    top_foods_out = [
        {"name": name, "count": len(cals),
         "avg_calories": round(sum(cals) / len(cals), 1)}
        for name, cals in top_foods
    ]

    # Average macros
    avg_macros = {k: round(v / days_with_data, 1) if days_with_data else 0
                  for k, v in macro_sums.items()}

    # Data level
    if days_with_data >= 7:
        data_level = "rich"
    elif days_with_data >= 1:
        data_level = "limited"
    else:
        data_level = "none"

    # Recent recommendations
    rec_dir = _get_recommendations_dir(data_dir)
    recent_recs: list[dict] = []
    for offset in range(days):
        if len(recent_recs) >= 3:
            break
        day = (end - timedelta(days=offset)).isoformat()
        rec_path = os.path.join(rec_dir, f"{day}.json")
        if not os.path.exists(rec_path):
            continue
        with open(rec_path, "r", encoding="utf-8") as f:
            rec_data = json.load(f)
        if meal_type in rec_data:
            entry = rec_data[meal_type]
            recent_recs.append({
                "date": day,
                "items": entry.get("items", []),
                "picked": entry.get("picked"),
            })

    return {
        "meal_type": meal_type,
        "data_level": data_level,
        "days_with_data": days_with_data,
        "top_foods": top_foods_out,
        "avg_macros": avg_macros,
        "recent_3_days": recent_3,
        "recent_recommendations": recent_recs,
    }


def save_recommendation(data_dir: str, meal_type: str, items: list,
                         day: str = None, tz_offset: int = None) -> dict:
    """Save meal recommendations for a given meal type today."""
    rec_dir = _get_recommendations_dir(data_dir)
    os.makedirs(rec_dir, exist_ok=True)
    day = day or _local_date(tz_offset)
    path = os.path.join(rec_dir, f"{day}.json")

    existing: dict = {}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            existing = json.load(f)

    existing[meal_type] = {
        "items": items,
        "picked": None,
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    return {"saved": True, "file": path, "meal_type": meal_type,
            "items": items}


# ---------------------------------------------------------------------------
# Meal type detection from timestamp + schedule
# ---------------------------------------------------------------------------

# Default time windows (3-meal mode) — used when no custom schedule provided.
# Format: (start_hour, end_hour, meal_name)
# Hours are in local time. Windows that cross midnight use end > 24.
DEFAULT_WINDOWS_3 = [
    (5,  10, "breakfast"),
    (10, 11, "snack_am"),
    (11, 14, "lunch"),
    (14, 17, "snack_pm"),
    (17, 21, "dinner"),
    (21, 29, "snack_pm"),   # 21:00 – 05:00 next day (29 = 24+5)
]

DEFAULT_WINDOWS_2 = [
    (5,  10, "meal_1"),
    (10, 11, "snack_1"),
    (11, 14, "meal_1"),
    (14, 17, "snack_2"),
    (17, 21, "meal_2"),
    (21, 29, "snack_2"),
]


def _parse_hhmm(s: str) -> float:
    """Parse 'HH:MM' to fractional hours (e.g. '09:30' → 9.5)."""
    parts = s.strip().split(":")
    return int(parts[0]) + int(parts[1]) / 60.0


def _build_schedule_windows(schedule: dict, meals: int) -> list:
    """Build time windows from a custom meal schedule.

    Strategy: each meal owns the time from the midpoint with the previous meal
    to the midpoint with the next meal. Snack detection uses a post-meal offset.

    Args:
        schedule: {"breakfast": "09:00", "lunch": "12:00", "dinner": "18:00"}
                  or {"meal_1": "12:00", "meal_2": "18:00"} for 2-meal mode.
        meals: 2 or 3.

    Returns: list of (start_hour, end_hour, meal_name) tuples.
    """
    if meals == 3:
        keys = ["breakfast", "lunch", "dinner"]
    else:
        keys = ["meal_1", "meal_2"]

    # Parse schedule times
    times = []
    for k in keys:
        if k not in schedule:
            return None  # Incomplete schedule, fall back to default
        times.append((k, _parse_hhmm(schedule[k])))

    # Sort by time (should already be in order, but be safe)
    times.sort(key=lambda x: x[1])

    windows = []
    n = len(times)
    for i in range(n):
        name, t = times[i]
        # Previous meal time (wrap around midnight)
        _, t_prev = times[(i - 1) % n]
        _, t_next = times[(i + 1) % n]

        # Midpoint with previous meal
        if i == 0:
            # First meal: midpoint with last meal of previous day
            gap_prev = (t - t_prev) % 24
            start = (t - gap_prev / 2) % 24
        else:
            gap_prev = t - t_prev
            start = t_prev + gap_prev / 2

        # Midpoint with next meal
        if i == n - 1:
            # Last meal: midpoint with first meal of next day
            gap_next = (t_next - t) % 24
            end = t + gap_next / 2
            if end < start:
                end += 24  # Crosses midnight
        else:
            gap_next = t_next - t
            end = t + gap_next / 2

        windows.append((start, end, name))

    return windows


# Snack offset: if current time is more than this many hours AFTER the main
# meal time AND that meal is already logged, classify as snack instead.
_SNACK_OFFSET_HOURS = 1.5

# Map main meal → snack name (3-meal mode)
_SNACK_MAP_3 = {
    "breakfast": "snack_am",
    "lunch": "snack_pm",
    # dinner has no snack after it in standard mode
}

_SNACK_MAP_2 = {
    "meal_1": "snack_1",
    # meal_2 has no snack after it
}


# ---------------------------------------------------------------------------
# Local date utility
# ---------------------------------------------------------------------------

def local_date_info(tz_offset: int) -> dict:
    """Return local date info: today, weekday, and current week's Mon-Sun range.

    Useful for any skill that needs the user's local date without relying
    on the LLM to compute it.
    """
    utc_now = datetime.now(timezone.utc)
    local_dt = utc_now + timedelta(seconds=tz_offset)
    today = local_dt.date()
    weekday = today.isoweekday()  # Mon=1, Sun=7
    monday = today - timedelta(days=weekday - 1)
    sunday = monday + timedelta(days=6)
    prev_monday = monday - timedelta(days=7)
    prev_sunday = monday - timedelta(days=1)

    return {
        "today": today.isoformat(),
        "weekday": today.strftime("%A"),
        "weekday_num": weekday,
        "local_time": local_dt.strftime("%H:%M:%S"),
        "current_week": {
            "monday": monday.isoformat(),
            "sunday": sunday.isoformat(),
        },
        "previous_week": {
            "monday": prev_monday.isoformat(),
            "sunday": prev_sunday.isoformat(),
        },
    }


def detect_meal(tz_offset: int, meals: int,
                schedule: dict = None,
                log: list = None,
                timestamp: str = None) -> dict:
    """Detect which meal type the current time corresponds to.

    Args:
        tz_offset: Timezone offset from UTC in seconds (e.g. 28800 for UTC+8).
        meals: 2 or 3.
        schedule: Optional custom meal schedule dict.
        log: Optional list of already-logged meals today (for snack detection).
        timestamp: Optional ISO-8601 UTC timestamp. Defaults to now.

    Returns: dict with detected_meal, local_time, local_date, method, etc.
    """
    # 1. Determine local time
    if timestamp:
        # Parse ISO timestamp — support Python 3.6+ (no fromisoformat with tz)
        ts_clean = timestamp.replace("Z", "").rstrip("+00:00").split("+")[0].split("-")
        # Try common ISO formats
        ts_bare = timestamp.replace("Z", "").split("+")[0]
        for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
            try:
                utc_dt = datetime.strptime(ts_bare, fmt).replace(tzinfo=timezone.utc)
                break
            except ValueError:
                continue
        else:
            raise ValueError(f"Cannot parse timestamp: {timestamp}")
    else:
        utc_dt = datetime.now(timezone.utc)

    local_dt = utc_dt + timedelta(seconds=tz_offset)
    local_hour = local_dt.hour + local_dt.minute / 60.0
    local_time_str = local_dt.strftime("%H:%M")
    local_date_str = local_dt.strftime("%Y-%m-%d")

    # 2. Build or select windows
    method = "default"
    windows = None
    if schedule:
        windows = _build_schedule_windows(schedule, meals)
        if windows:
            method = "schedule"

    if windows is None:
        windows = DEFAULT_WINDOWS_3 if meals == 3 else DEFAULT_WINDOWS_2

    # 3. Find which window the current time falls into
    detected = None
    win_start_str = None
    win_end_str = None

    # Normalize local_hour for windows that cross midnight
    for start, end, name in windows:
        h = local_hour
        # If window crosses midnight (end > 24), check both raw and +24
        if end > 24:
            if h < start:
                h += 24
            if start <= h < end:
                detected = name
                win_start_str = f"{int(start % 24):02d}:{int((start % 1) * 60):02d}"
                win_end_str = f"{int(end % 24):02d}:{int((end % 1) * 60):02d}"
                break
        else:
            if start <= h < end:
                detected = name
                win_start_str = f"{int(start):02d}:{int((start % 1) * 60):02d}"
                win_end_str = f"{int(end):02d}:{int((end % 1) * 60):02d}"
                break

    # Fallback if no window matched (shouldn't happen with proper windows)
    if detected is None:
        detected = "snack_pm" if meals == 3 else "snack_2"
        method = "fallback"

    # 4. Snack upgrade: if the main meal is already logged and we're past
    #    the meal time by _SNACK_OFFSET_HOURS, switch to snack.
    snack_map = _SNACK_MAP_3 if meals == 3 else _SNACK_MAP_2
    if detected in snack_map and log:
        logged_names = set()
        for m in log:
            n = m.get("name", "")
            logged_names.add(n)
            mt = m.get("meal_type", "")
            if mt:
                logged_names.add(mt)

        if detected in logged_names:
            # Main meal already logged → this is a snack
            meal_time_hour = None
            if schedule and detected in schedule:
                meal_time_hour = _parse_hhmm(schedule[detected])
            if meal_time_hour is not None and local_hour > meal_time_hour + _SNACK_OFFSET_HOURS:
                detected = snack_map[detected]

    return {
        "detected_meal": detected,
        "local_time": local_time_str,
        "local_date": local_date_str,
        "method": method,
        "window_start": win_start_str,
        "window_end": win_end_str,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Nutrition calculator")
    sub = parser.add_subparsers(dest="cmd")

    dm = sub.add_parser("detect-meal", help="Detect meal type from timestamp and schedule")
    dm.add_argument("--tz-offset", type=int, required=True,
                    help="Timezone offset from UTC in seconds (e.g. 28800 for UTC+8)")
    dm.add_argument("--meals", type=int, default=3, choices=[2, 3],
                    help="Meals per day (2 or 3)")
    dm.add_argument("--schedule", type=str, default=None,
                    help='JSON object with meal times, e.g. \'{"breakfast":"09:00","lunch":"12:00","dinner":"18:00"}\'')
    dm.add_argument("--log", type=str, default=None,
                    help='JSON array of already-logged meals today (for snack detection)')
    dm.add_argument("--timestamp", type=str, default=None,
                    help="ISO-8601 UTC timestamp of the message (default: current UTC time)")

    t = sub.add_parser("target", help="Compute daily macro targets")
    t.add_argument("--weight", type=float, required=True, help="Body weight in kg")
    t.add_argument("--cal", type=int, required=True, help="Daily calorie target (kcal)")
    t.add_argument("--meals", type=int, default=3, choices=[2, 3], help="Meals per day")
    t.add_argument("--mode", type=str, default="balanced",
                   choices=list(DIET_MODE_FAT.keys()),
                   help="Diet mode (determines fat %% range)")

    a = sub.add_parser("analyze", help="Analyze cumulative intake")
    a.add_argument("--weight", type=float, required=True)
    a.add_argument("--cal", type=int, required=True)
    a.add_argument("--meals", type=int, default=3, choices=[2, 3])
    a.add_argument("--mode", type=str, default="balanced",
                   choices=list(DIET_MODE_FAT.keys()))
    a.add_argument("--log", type=str, required=True,
                   help='JSON array of meals')

    s = sub.add_parser("save", help="Save a meal record to today's log")
    s.add_argument("--data-dir", type=str, required=True, help="Directory to store daily JSON logs")
    s.add_argument("--meal", type=str, required=True, help="JSON object for the meal")
    s.add_argument("--date", type=str, default=None, help="Date override (YYYY-MM-DD)")
    s.add_argument("--tz-offset", type=int, default=None,
                   help="Timezone offset from UTC in seconds (e.g. 28800 for UTC+8). "
                        "Used to compute local date when --date is omitted.")
    s.add_argument("--workspace-dir", type=str, default=None,
                   help="Workspace directory. When provided, auto-runs guided-feedback "
                        "increment+next after saving.")

    l = sub.add_parser("load", help="Load today's meal records")
    l.add_argument("--data-dir", type=str, required=True, help="Directory with daily JSON logs")
    l.add_argument("--date", type=str, default=None, help="Date to load (YYYY-MM-DD), default today")
    l.add_argument("--tz-offset", type=int, default=None,
                   help="Timezone offset from UTC in seconds. "
                        "Used to compute local date when --date is omitted.")

    e = sub.add_parser("evaluate", help="Evaluate cumulative intake at a meal checkpoint")
    e.add_argument("--weight", type=float, required=True)
    e.add_argument("--cal", type=int, required=True)
    e.add_argument("--meals", type=int, default=3, choices=[2, 3])
    e.add_argument("--mode", type=str, default="balanced",
                   choices=list(DIET_MODE_FAT.keys()))
    e.add_argument("--current-meal", type=str, required=True,
                   help="Meal being evaluated (e.g. breakfast, lunch, dinner, snack_am, snack_pm)")
    e.add_argument("--log", type=str, required=True,
                   help="JSON array of all logged meals today")
    e.add_argument("--assumed", type=str, default=None,
                   help="JSON array of assumed meals (for forgotten meals)")

    cm = sub.add_parser("check-missing", help="Check for missing meals before current meal")
    cm.add_argument("--meals", type=int, default=3, choices=[2, 3])
    cm.add_argument("--current-meal", type=str, required=True)
    cm.add_argument("--log", type=str, required=True,
                   help="JSON array of all logged meals today")

    mh = sub.add_parser("meal-history",
                         help="Analyze meal history for a meal type over N days")
    mh.add_argument("--data-dir", type=str, required=True,
                    help="Directory with daily JSON logs")
    mh.add_argument("--meal-type", type=str, required=True,
                    help="Meal type to analyze (e.g. breakfast, lunch, dinner)")
    mh.add_argument("--days", type=int, default=30,
                    help="Number of days to look back (default 30)")
    mh.add_argument("--date", type=str, default=None,
                    help="End date (YYYY-MM-DD), default today")
    mh.add_argument("--tz-offset", type=int, default=None,
                    help="Timezone offset from UTC in seconds")

    sr = sub.add_parser("save-recommendation",
                         help="Save meal recommendations for today")
    sr.add_argument("--data-dir", type=str, required=True,
                    help="Directory with daily JSON logs (recommendations stored as sibling)")
    sr.add_argument("--meal-type", type=str, required=True,
                    help="Meal type (e.g. breakfast, lunch, dinner)")
    sr.add_argument("--items", type=str, required=True,
                    help="JSON array of recommendation strings")
    sr.add_argument("--date", type=str, default=None,
                    help="Date override (YYYY-MM-DD)")
    sr.add_argument("--tz-offset", type=int, default=None,
                    help="Timezone offset from UTC in seconds")

    wlc = sub.add_parser("weekly-low-cal-check",
                          help="Check if weekly average calorie intake is below BMR")
    wlc.add_argument("--data-dir", type=str, required=True,
                     help="Directory with daily JSON logs")
    wlc.add_argument("--bmr", type=float, required=True,
                     help="User's BMR in kcal/day")
    wlc.add_argument("--date", type=str, default=None,
                     help="End date for the 7-day window (YYYY-MM-DD), default today")
    wlc.add_argument("--tz-offset", type=int, default=None,
                     help="Timezone offset from UTC in seconds")

    ddp = sub.add_parser("detect-diet-pattern",
                          help="Detect if eating pattern differs from selected diet mode")
    ddp.add_argument("--data-dir", type=str, required=True,
                     help="Directory with daily JSON logs")
    ddp.add_argument("--current-mode", type=str, required=True,
                     choices=list(DIET_MODE_FAT.keys()),
                     help="User's currently selected diet mode")
    ddp.add_argument("--date", type=str, default=None,
                     help="End date for the 3-day window (YYYY-MM-DD), default today")
    ddp.add_argument("--tz-offset", type=int, default=None,
                     help="Timezone offset from UTC in seconds")

    ld = sub.add_parser("local-date",
                         help="Get the user's local date, weekday, and week ranges")
    ld.add_argument("--tz-offset", type=int, required=True,
                    help="Timezone offset from UTC in seconds (e.g. 28800 for UTC+8)")

    pc = sub.add_parser("produce-check",
                         help="Evaluate cumulative vegetable and fruit intake (China region)")
    pc.add_argument("--meals", type=int, default=3, choices=[2, 3],
                    help="Meals per day (2 or 3)")
    pc.add_argument("--current-meal", type=str, required=True,
                    help="Current meal checkpoint (e.g. breakfast, lunch, dinner, meal_1, meal_2)")
    pc.add_argument("--log", type=str, required=True,
                    help="JSON array of all logged meals today (each may include vegetables_g, fruits_g)")

    args = parser.parse_args()

    if args.cmd == "detect-meal":
        sched = None
        if args.schedule:
            try:
                sched = json.loads(args.schedule)
            except json.JSONDecodeError as e:
                print(f"Error: invalid --schedule JSON: {e}", file=sys.stderr)
                sys.exit(1)
        log = None
        if args.log:
            try:
                log = json.loads(args.log)
            except json.JSONDecodeError as e:
                print(f"Error: invalid --log JSON: {e}", file=sys.stderr)
                sys.exit(1)
        result = detect_meal(args.tz_offset, args.meals, sched, log, args.timestamp)
    elif args.cmd == "target":
        result = calc_targets(args.weight, args.cal, args.meals, args.mode)
    elif args.cmd == "analyze":
        try:
            log = json.loads(args.log)
        except json.JSONDecodeError as e:
            print(f"Error: invalid --log JSON: {e}", file=sys.stderr)
            sys.exit(1)
        result = analyze(args.weight, args.cal, args.meals, log, args.mode)
    elif args.cmd == "save":
        try:
            meal = json.loads(args.meal)
        except json.JSONDecodeError as e:
            print(f"Error: invalid --meal JSON: {e}", file=sys.stderr)
            sys.exit(1)
        result = save_meal(args.data_dir, meal, args.date, getattr(args, 'tz_offset', None),
                           getattr(args, 'workspace_dir', None))
    elif args.cmd == "load":
        result = load_meals(args.data_dir, args.date, getattr(args, 'tz_offset', None))
    elif args.cmd == "evaluate":
        try:
            log = json.loads(args.log)
        except json.JSONDecodeError as e:
            print(f"Error: invalid --log JSON: {e}", file=sys.stderr)
            sys.exit(1)
        assumed = None
        if args.assumed:
            try:
                assumed = json.loads(args.assumed)
            except json.JSONDecodeError as e:
                print(f"Error: invalid --assumed JSON: {e}", file=sys.stderr)
                sys.exit(1)
        result = evaluate(args.weight, args.cal, args.meals,
                          args.current_meal, log, assumed, args.mode)
    elif args.cmd == "check-missing":
        try:
            log = json.loads(args.log)
        except json.JSONDecodeError as e:
            print(f"Error: invalid --log JSON: {e}", file=sys.stderr)
            sys.exit(1)
        result = check_missing(args.meals, args.current_meal, log)
    elif args.cmd == "meal-history":
        result = meal_history(args.data_dir, args.meal_type, args.days,
                              args.date, getattr(args, 'tz_offset', None))
    elif args.cmd == "save-recommendation":
        try:
            items = json.loads(args.items)
        except json.JSONDecodeError as e:
            print(f"Error: invalid --items JSON: {e}", file=sys.stderr)
            sys.exit(1)
        result = save_recommendation(args.data_dir, args.meal_type, items,
                                     args.date, getattr(args, 'tz_offset', None))
    elif args.cmd == "weekly-low-cal-check":
        result = weekly_low_cal_check(args.data_dir, args.bmr, args.date,
                                      getattr(args, 'tz_offset', None))
    elif args.cmd == "detect-diet-pattern":
        result = detect_diet_pattern(args.data_dir, args.current_mode, args.date,
                                     getattr(args, 'tz_offset', None))
    elif args.cmd == "local-date":
        result = local_date_info(args.tz_offset)
    elif args.cmd == "produce-check":
        try:
            log = json.loads(args.log)
        except json.JSONDecodeError as e:
            print(f"Error: invalid --log JSON: {e}", file=sys.stderr)
            sys.exit(1)
        result = produce_check(args.meals, args.current_meal, log)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
