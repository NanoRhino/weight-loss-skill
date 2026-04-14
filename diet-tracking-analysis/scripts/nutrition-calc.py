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
  calibration-lookup — Look up user's portion calibrations for food items.

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
import re
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
_SHORT_TO_LONG = {
    "cal": "calories", "p": "protein", "c": "carbs", "f": "fat",
    "protein_g": "protein", "carbs_g": "carbs", "fat_g": "fat",
}


def _migrate_meal(meal: dict) -> dict:
    """Normalize meal dicts across old and new formats.

    Handles: short keys (cal→calories), _g suffix keys (protein_g→protein),
    items→foods rename, and meal-level macro summation from food items.
    """
    out = {}
    for k, v in meal.items():
        new_key = _SHORT_TO_LONG.get(k, k)
        if new_key in out:
            continue
        if k == "foods" and isinstance(v, list):
            out[k] = [_migrate_meal(f) for f in v]
        else:
            out[new_key] = v

    # New format: items → foods
    if "items" in out and "foods" not in out:
        out["foods"] = [_migrate_meal(f) for f in out.pop("items")]

    # New format: no meal-level macros → sum from foods
    if "foods" in out and "calories" not in out:
        for key in ("calories", "protein", "carbs", "fat"):
            out[key] = round(sum(f.get(key, 0) for f in out["foods"]), 1)

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


def _strip_food_noise(text: str) -> str:
    """Strip quantity/measure/temperature/size/cooking-method/particle noise."""
    for phrase in ('常温', '去冰', '少冰', '多冰', '加冰'):
        text = text.replace(phrase, '')
    text = re.sub(r'[\s\dx×*]+', '', text)
    text = re.sub(r'[一二三四五六七八九十两半几]', '', text)
    # 包/串 excluded — they appear in food names (面包).
    text = re.sub(r'[碗份个盘杯袋盒块片根条勺只颗粒瓶罐]', '', text)
    text = re.sub(r'[冰热温凉]', '', text)
    text = re.sub(r'[大小中]', '', text)
    text = re.sub(r'[蒸煮煎炸炒烤烙焖卤涮炖焗熏烘灼拌烩煲酿烫]', '', text)
    text = re.sub(r'[的]', '', text)
    return text.strip()


def _check_ambiguous_foods(meal: dict) -> list:
    """Return clarification hints for ambiguous foods in *meal*.

    Match keyword/alias → remove it → strip noise → if remainder is empty
    the food is ambiguous.
    """
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
    foods = meal.get("foods", []) or meal.get("items", [])
    for food_item in foods:
        food_name = food_item.get("name", "")
        if not food_name:
            continue
        for entry in dictionary:
            keyword = entry.get("keyword", "")
            aliases = entry.get("aliases", [])

            # Longest match first (e.g. alias "汉堡包" over keyword "汉堡")
            candidates = ([keyword] if keyword else []) + aliases
            candidates.sort(key=len, reverse=True)
            matched = None
            for candidate in candidates:
                if candidate in food_name:
                    matched = candidate
                    break
            if not matched:
                continue

            remainder = _strip_food_noise(food_name.replace(matched, '', 1))
            if remainder:
                continue
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


# ---------------------------------------------------------------------------
# Portion calibration memory (stored in health-preferences.md)
# ---------------------------------------------------------------------------

_MAX_CALIBRATIONS = 200
_CAL_SECTION_HEADER = "## Portion Calibrations\n"
_CAL_LINE_RE = re.compile(
    r'^- \[(\d{4}-\d{2}-\d{2})\] (.+?) → (\d+)g \(×(\d+)\)$')
# Confusion pairs: AI guessed X but user corrected to Y
_CONFUSION_SECTION_HEADER = "## Correction Aliases\n"
_CONFUSION_LINE_RE = re.compile(
    r'^- (.+?) → (.+?)$')


def _hp_path(data_dir: str) -> str:
    """Return path to health-preferences.md at workspace root."""
    workspace = os.path.dirname(os.path.dirname(os.path.normpath(data_dir)))
    return os.path.join(workspace, "health-preferences.md")


def _load_calibrations(data_dir: str) -> dict:
    path = _hp_path(data_dir)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except IOError:
        return {}
    idx = content.find(_CAL_SECTION_HEADER)
    if idx == -1:
        return {}
    section_start = idx + len(_CAL_SECTION_HEADER)
    next_header = content.find("\n## ", section_start)
    section = content[section_start:next_header] if next_header != -1 else content[section_start:]
    calibrations = {}
    for line in section.strip().split("\n"):
        m = _CAL_LINE_RE.match(line.strip())
        if m:
            calibrations[m.group(2)] = {
                "user_portion_g": int(m.group(3)),
                "correction_count": int(m.group(4)),
                "last_corrected": m.group(1),
            }
    return calibrations


def _load_confusion_aliases(data_dir: str) -> dict:
    """Load correction aliases: {ai_guessed_name: user_corrected_name}."""
    path = _hp_path(data_dir)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except IOError:
        return {}
    idx = content.find(_CONFUSION_SECTION_HEADER)
    if idx == -1:
        return {}
    section_start = idx + len(_CONFUSION_SECTION_HEADER)
    next_header = content.find("\n## ", section_start)
    section = content[section_start:next_header] if next_header != -1 else content[section_start:]
    aliases = {}
    for line in section.strip().split("\n"):
        m = _CONFUSION_LINE_RE.match(line.strip())
        if m:
            aliases[m.group(1)] = m.group(2)
    return aliases


def _save_confusion_aliases(data_dir: str, aliases: dict):
    """Save correction aliases to health-preferences.md."""
    path = _hp_path(data_dir)
    lines = [f"- {ai_name} → {real_name}" for ai_name, real_name in sorted(aliases.items())]
    new_body = "\n".join(lines) + "\n" if lines else ""

    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    else:
        content = ""

    idx = content.find(_CONFUSION_SECTION_HEADER)
    if idx != -1:
        section_start = idx + len(_CONFUSION_SECTION_HEADER)
        next_header = content.find("\n## ", section_start)
        if next_header != -1:
            content = content[:section_start] + new_body + content[next_header:]
        else:
            content = content[:section_start] + new_body
    else:
        if content and not content.endswith("\n"):
            content += "\n"
        content += "\n" + _CONFUSION_SECTION_HEADER + new_body

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _save_calibrations_to_hp(data_dir: str, calibrations: dict):
    path = _hp_path(data_dir)
    lines = []
    for name, cal in sorted(calibrations.items(),
                            key=lambda x: x[1].get("correction_count", 0),
                            reverse=True):
        lines.append(
            f"- [{cal['last_corrected']}] {name} → {cal['user_portion_g']}g"
            f" (×{cal['correction_count']})")
    new_body = "\n".join(lines) + "\n" if lines else ""

    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    else:
        content = ""

    idx = content.find(_CAL_SECTION_HEADER)
    if idx != -1:
        section_start = idx + len(_CAL_SECTION_HEADER)
        next_header = content.find("\n## ", section_start)
        if next_header != -1:
            content = content[:section_start] + new_body + content[next_header:]
        else:
            content = content[:section_start] + new_body
    else:
        if content and not content.endswith("\n"):
            content += "\n"
        content += "\n" + _CAL_SECTION_HEADER + new_body

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _cleanup_calibrations(calibrations: dict) -> dict:
    """Remove lowest-frequency entries when over limit."""
    if len(calibrations) <= _MAX_CALIBRATIONS:
        return calibrations
    sorted_keys = sorted(calibrations.keys(),
                         key=lambda k: calibrations[k].get("correction_count", 1))
    to_remove = len(calibrations) - _MAX_CALIBRATIONS
    for key in sorted_keys[:to_remove]:
        del calibrations[key]
    return calibrations


def _update_calibrations_on_correction(data_dir: str, old_foods: list,
                                       new_foods: list, day: str = None):
    """Compare old and new food items; save calibrations for changed portions.
    Also detects name+portion corrections (e.g. 鸡蛋面→玉米面) and stores
    confusion aliases so future lookups can resolve them."""
    old_by_name = {f.get("name", ""): f for f in old_foods if f.get("name")}
    new_by_name = {f.get("name", ""): f for f in new_foods if f.get("name")}
    changes = []
    name_changes = []  # (ai_guessed_name, user_corrected_name, new_g)

    for nf in new_foods:
        name = nf.get("name", "")
        if not name:
            continue
        if name in old_by_name:
            # Same name — portion-only correction
            old_g = old_by_name[name].get("amount_g", 0)
            new_g = nf.get("amount_g", 0)
            if old_g and new_g and old_g != new_g:
                changes.append((name, old_g, new_g))
        elif name not in old_by_name:
            # New name not in old foods — check if it replaced a removed item
            # A removed item = old food name that's no longer in new_foods
            removed = [oname for oname in old_by_name if oname not in new_by_name]
            if len(removed) == 1 and len([n for n in new_by_name if n not in old_by_name]) == 1:
                # 1-to-1 replacement: AI guessed removed[0], user corrected to name
                ai_name = removed[0]
                new_g = nf.get("amount_g", 0)
                if new_g:
                    name_changes.append((ai_name, name, new_g))
                    changes.append((name, 0, new_g))

    if not changes and not name_changes:
        return []

    calibrations = _load_calibrations(data_dir)
    today = day or date.today().isoformat()
    updated = []
    for food_name, _old_g, new_g in changes:
        if food_name in calibrations:
            entry = calibrations[food_name]
            entry["user_portion_g"] = new_g
            entry["correction_count"] = entry.get("correction_count", 0) + 1
            entry["last_corrected"] = today
        else:
            calibrations[food_name] = {
                "user_portion_g": new_g,
                "correction_count": 1,
                "last_corrected": today,
            }
        updated.append(food_name)

    calibrations = _cleanup_calibrations(calibrations)
    _save_calibrations_to_hp(data_dir, calibrations)

    # Save confusion aliases for name changes
    if name_changes:
        aliases = _load_confusion_aliases(data_dir)
        for ai_name, real_name, _g in name_changes:
            aliases[ai_name] = real_name
        _save_confusion_aliases(data_dir, aliases)

    return updated


def calibration_lookup(data_dir: str, food_names: list) -> dict:
    """Look up portion calibrations for a list of food names.
    Also checks confusion aliases: if AI guessed 'X' and we have an alias
    X→Y with calibration for Y, return Y's calibration with a hint."""
    calibrations = _load_calibrations(data_dir)
    aliases = _load_confusion_aliases(data_dir)
    matches = []
    no_match = []

    for query in food_names:
        if not query:
            continue
        # Exact match on calibrations
        if query in calibrations:
            matches.append({
                "query": query,
                "match_type": "exact",
                "matched_key": query,
                "calibration": calibrations[query],
            })
            continue
        # Check confusion aliases: AI might be guessing the same wrong name again
        if query in aliases:
            real_name = aliases[query]
            cal = calibrations.get(real_name)
            matches.append({
                "query": query,
                "match_type": "alias",
                "matched_key": real_name,
                "alias_from": query,
                "calibration": cal or {"user_portion_g": None, "correction_count": 0},
                "hint": f"Previously corrected: '{query}' was actually '{real_name}'",
            })
            continue
        # Contains match: query contains a key, or key contains query
        best = None
        for key, cal in calibrations.items():
            if key in query or query in key:
                if best is None or cal.get("correction_count", 0) > best[1].get("correction_count", 0):
                    best = (key, cal)
        if best:
            matches.append({
                "query": query,
                "match_type": "contains",
                "matched_key": best[0],
                "calibration": best[1],
            })
        else:
            # Also check aliases with contains match
            alias_best = None
            for ai_name, real_name in aliases.items():
                if ai_name in query or query in ai_name:
                    cal = calibrations.get(real_name)
                    if cal and (alias_best is None or cal.get("correction_count", 0) > alias_best[2].get("correction_count", 0)):
                        alias_best = (ai_name, real_name, cal)
            if alias_best:
                matches.append({
                    "query": query,
                    "match_type": "alias_contains",
                    "matched_key": alias_best[1],
                    "alias_from": alias_best[0],
                    "calibration": alias_best[2],
                    "hint": f"Previously corrected: '{alias_best[0]}' was actually '{alias_best[1]}'",
                })
            else:
                no_match.append(query)

    matches.sort(key=lambda m: m["calibration"].get("correction_count", 0) if m["calibration"] else 0,
                 reverse=True)
    return {"matches": matches, "no_match": no_match}


def save_meal(data_dir: str, meal: dict, day: str = None, tz_offset: int = None) -> dict:
    """Save a meal to the daily log. Same meal name overwrites (supports corrections)."""
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
            # Auto-save portion calibrations on correction
            _update_calibrations_on_correction(
                data_dir, m.get("foods", []), meal.get("foods", []),
                day or _local_date(tz_offset))
            existing[i] = meal
            replaced = True
            break
    if not replaced:
        existing.append(meal)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    result = {"saved": True, "file": path, "meals_count": len(existing), "meals": existing}

    # Check for ambiguous foods that need clarification
    clarifications = _check_ambiguous_foods(meal)
    if clarifications:
        result["needs_clarification"] = clarifications

    return result


def _save_evaluation_to_meal(data_dir: str, day: str, meal_name: str, eval_result: dict):
    """Persist suggestion_type into the saved meal record.

    Only stores suggestion_type from the script layer. The human-readable
    suggestion_text is written later by diet-tracking-analysis via
    save-evaluation command after the LLM composes the response.
    """
    path = get_log_path(data_dir, day)
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        meals = json.load(f)
    for m in meals:
        if m.get("name") == meal_name:
            m["evaluation"] = {
                "suggestion_type": eval_result.get("suggestion_type"),
            }
            break
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meals, f, ensure_ascii=False, indent=2)


def save_evaluation_text(data_dir: str, meal_name: str, suggestion_text: str,
                         day: str = None, tz_offset: int = None) -> dict:
    """Save the LLM-generated suggestion text into a meal's evaluation record.

    Called by diet-tracking-analysis after composing the user-facing response.
    Merges suggestion_text into the existing evaluation dict (which already
    has suggestion_type from _save_evaluation_to_meal).
    """
    day = day or _local_date(tz_offset)
    path = get_log_path(data_dir, day)
    if not os.path.exists(path):
        return {"saved": False, "error": "No meal file for this date"}
    with open(path, "r", encoding="utf-8") as f:
        meals = json.load(f)
    found = False
    for m in meals:
        if m.get("name") == meal_name:
            if "evaluation" not in m:
                m["evaluation"] = {}
            m["evaluation"]["suggestion_text"] = suggestion_text
            found = True
            break
    if not found:
        return {"saved": False, "error": f"Meal '{meal_name}' not found"}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meals, f, ensure_ascii=False, indent=2)
    return {"saved": True, "meal": meal_name, "date": day}


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

    # Calories within range but macros imbalanced → defer to next-day optimization
    cal_in_range_macro_off = (not cal_outside) and macros_outside >= 1

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
        "cal_in_range_macro_off": cal_in_range_macro_off,
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


def recent_overshoot_check(data_dir: str, daily_cal: int,
                           lookback_days: int = 7,
                           ref_date: str = None,
                           tz_offset: int = None) -> dict:
    """Check how many of the recent days had calorie overshoot.

    Counts ALL overshoot days in the lookback window (excluding today),
    regardless of whether they are consecutive.
    """
    end = date.fromisoformat(ref_date) if ref_date else date.fromisoformat(_local_date(tz_offset))
    cal_hi = daily_cal + 100  # same range as calc_targets

    overshoot_days: list[str] = []
    for offset in range(1, lookback_days + 1):  # start at 1 to exclude today
        day = (end - timedelta(days=offset)).isoformat()
        path = get_log_path(data_dir, day)
        if not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            meals = _migrate_meals(json.load(f))
        day_cal = round(sum(m.get("calories", 0) for m in meals), 1)
        if day_cal > cal_hi:
            overshoot_days.append(day)

    return {
        "lookback_days": lookback_days,
        "overshoot_days": overshoot_days,
        "overshoot_count": len(overshoot_days),
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

    # Same weekday last week (fallback for notification-composer)
    same_weekday_date = (end - timedelta(days=7)).isoformat()
    same_weekday_meal = None
    sw_path = get_log_path(data_dir, same_weekday_date)
    if os.path.exists(sw_path):
        with open(sw_path, "r", encoding="utf-8") as f:
            sw_meals = _migrate_meals(json.load(f))
        matched_sw = [m for m in sw_meals if m.get("meal_type") == meal_type
                      or m.get("name") == meal_type]
        if matched_sw:
            sw_foods = []
            sw_macros = {"calories": 0, "protein": 0, "carbs": 0, "fat": 0}
            for m in matched_sw:
                sw_foods.extend(f.get("name", "") for f in m.get("foods", [])
                                if f.get("name"))
                for k in sw_macros:
                    sw_macros[k] += m.get(k, 0)
            same_weekday_meal = {
                "date": same_weekday_date,
                "foods": sw_foods,
                "macros": sw_macros,
            }

    return {
        "meal_type": meal_type,
        "data_level": data_level,
        "days_with_data": days_with_data,
        "top_foods": top_foods_out,
        "avg_macros": avg_macros,
        "recent_3_days": recent_3,
        "recent_recommendations": recent_recs,
        "same_weekday_last_week": same_weekday_meal,
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
# Composite commands (CRUD)
# ---------------------------------------------------------------------------


def _resolve_suggestion_type(evaluation: dict, eaten: bool,
                             is_final_meal: bool, bmr: float = None) -> str:
    """Determine the suggestion type based on evaluation results and meal timing.

    Returns one of: "right_now", "next_meal", "next_time",
                    "case_d_snack", "case_d_ok"

    Note: cal_in_range_macro_off is exposed in evaluation output for the
    LLM to adjust tone (defer macro/produce gaps to tomorrow), but does
    NOT create a separate suggestion_type — it stays "next_time".
    """
    needs_adj = evaluation.get("needs_adjustment", False)
    daily_total = evaluation.get("daily_total", 0)
    cal_in_range_macro_off = evaluation.get("cal_in_range_macro_off", False)

    # Case D: final meal + under calorie target range
    if is_final_meal:
        cal_min = evaluation.get("checkpoint_range", {}).get("calories_min", 0)
        if daily_total < cal_min:
            if bmr and daily_total < bmr * 0.9:
                return "case_d_snack"
            return "case_d_ok"

    # Calories in range but macros off → still "next_time" (on track);
    # the LLM uses cal_in_range_macro_off flag to suggest tomorrow swaps
    if cal_in_range_macro_off:
        return "next_time"

    # Case A: before eating + adjustment needed
    if needs_adj and not eaten:
        return "right_now"

    # Case B: already eaten + adjustment needed
    if needs_adj and eaten:
        return "next_meal"

    # Case C: on track
    return "next_time"


def log_meal(data_dir: str, tz_offset: int, meals: int,
             weight: float, daily_cal: int, meal_json: dict,
             meal_type: str = None, timestamp: str = None,
             schedule: dict = None, mode: str = "balanced",
             bmr: float = None, region: str = None,
             eaten: bool = False, append: bool = False) -> dict:
    """Log a meal with full pipeline: detect → load → check-missing → save → evaluate → produce.

    This is the primary command for food logging. It replaces the need to call
    detect-meal, load, check-missing, save, evaluate, and produce-check separately.

    Args:
        data_dir: Directory with daily JSON logs.
        tz_offset: Timezone offset from UTC in seconds.
        meals: Meals per day (2 or 3).
        weight: Body weight in kg.
        daily_cal: Daily calorie target (kcal).
        meal_json: Meal data dict (same format as save --meal).
        meal_type: User-specified meal type. If None, auto-detected.
        timestamp: ISO-8601 UTC timestamp of the user's message.
        schedule: Optional meal schedule dict for detect-meal.
        mode: Diet mode for evaluate (default "balanced").
        bmr: BMR in kcal for Case D check. Optional.
        region: Region code (e.g. "CN") to enable produce-check. Optional.
        eaten: Whether the user has already eaten this meal (default False).

    Returns: Combined result dict with meal_detection, existing_meals,
             missing_meals, save, evaluation, and produce sections.
    """
    result = {}

    # 1. Detect meal type or use user-specified
    existing = load_meals(data_dir, None, tz_offset)
    existing_meals_list = existing.get("meals", [])

    if meal_type:
        # User explicitly stated the meal type
        local_date = existing.get("date") or _local_date(tz_offset)
        resolved = resolve_meal_name(meal_type, meals)
        result["meal_detection"] = {
            "detected_meal": resolved,
            "local_date": local_date,
            "method": "user_specified",
        }
    else:
        detection = detect_meal(tz_offset, meals, schedule,
                                existing_meals_list, timestamp)
        result["meal_detection"] = detection
        local_date = detection.get("local_date", _local_date(tz_offset))
        resolved = detection.get("detected_meal")

    current_meal = resolved
    result["existing_meals"] = existing_meals_list

    # 2. Check missing meals before current one
    missing = check_missing(meals, current_meal, existing_meals_list)
    result["missing_meals"] = missing

    # Build assumed meals for evaluate if there are missing meals
    assumed = None
    if missing.get("has_missing"):
        targets = calc_targets(weight, daily_cal, meals, mode)
        assumed = []
        for m in missing["missing"]:
            pct = m["expected_pct"] / 100.0
            assumed.append({
                "name": m["name"],
                "meal_type": m["name"],
                "calories": round(daily_cal * pct),
                "protein": round(targets["protein"]["target"] * pct),
                "carbs": round(targets["carb"]["target"] * pct),
                "fat": round(targets["fat"]["target"] * pct),
                "assumed": True,
            })

    # 3. Ensure meal_json has correct name/meal_type
    # meal_json may be a list of food items or a single dict
    if isinstance(meal_json, list):
        new_items = meal_json
    else:
        new_items = meal_json.get("items", [meal_json] if "name" in meal_json else [])

    # --append: merge new items into existing meal instead of replacing
    if append:
        for m in existing_meals_list:
            if m.get("name") == current_meal:
                old_items = m.get("items", [])
                new_items = old_items + new_items
                break

    meal_data = {"items": new_items}
    meal_data["name"] = current_meal
    if "meal_type" not in meal_data:
        meal_data["meal_type"] = meal_type or current_meal

    # 4. Save
    save_result = save_meal(data_dir, meal_data, local_date)
    result["save"] = save_result
    all_meals = save_result.get("meals", [])

    # 5. Evaluate
    eval_result = evaluate(weight, daily_cal, meals,
                           current_meal, all_meals, assumed, mode)
    # Attach BMR info for Case D if provided
    if bmr is not None:
        daily_total = sum(m.get("calories", 0) for m in all_meals)
        eval_result["bmr"] = bmr
        eval_result["daily_total"] = daily_total
        eval_result["below_bmr"] = daily_total < bmr
    else:
        daily_total = sum(m.get("calories", 0) for m in all_meals)
        eval_result["daily_total"] = daily_total

    # Overshoot severity: how far over the upper calorie limit
    cal_hi = daily_cal + 100  # same as calc_targets range
    if daily_total > cal_hi:
        overshoot_pct = round((daily_total - cal_hi) / cal_hi * 100, 1)
        eval_result["overshoot_severity"] = "significant" if overshoot_pct >= 20 else "mild"
        eval_result["overshoot_pct"] = overshoot_pct
    else:
        eval_result["overshoot_severity"] = None
        eval_result["overshoot_pct"] = 0

    # Recent overshoot history (past 3 days, excluding today)
    overshoot_history = recent_overshoot_check(
        data_dir, daily_cal, lookback_days=3,
        ref_date=local_date, tz_offset=tz_offset)
    eval_result["recent_overshoot_count"] = overshoot_history["overshoot_count"]
    eval_result["recent_overshoot_days"] = overshoot_history["overshoot_days"]

    # Determine if this is the final meal of the day
    blocks = get_meal_blocks(meals)
    is_final = find_block_index(current_meal, meals) == len(blocks) - 1

    # Resolve suggestion type
    eval_result["suggestion_type"] = _resolve_suggestion_type(
        eval_result, eaten, is_final, bmr)
    eval_result["is_final_meal"] = is_final

    result["evaluation"] = eval_result

    # 5b. Persist evaluation into saved meal record for notification-composer
    _save_evaluation_to_meal(data_dir, local_date, current_meal, eval_result)

    # 6. Produce check (China region only)
    if region and region.upper() == "CN":
        result["produce"] = produce_check(meals, current_meal, all_meals)
    else:
        result["produce"] = None

    # 7. Ambiguous food clarification
    save_clarifications = save_result.get("needs_clarification", [])
    if not save_clarifications:
        save_clarifications = _check_ambiguous_foods(meal_data)
    if save_clarifications:
        result["needs_clarification"] = save_clarifications

    # 8. Calibration warnings (safety net when lookup was skipped)
    cal_data = _load_calibrations(data_dir)
    if cal_data:
        cal_warnings = []
        for food in new_items:
            fname = food.get("name", "")
            logged_g = food.get("amount_g", 0)
            if not fname or not logged_g:
                continue
            cal_entry = cal_data.get(fname)
            if not cal_entry:
                for key, entry in cal_data.items():
                    if key in fname or fname in key:
                        cal_entry = entry
                        break
            if cal_entry:
                cal_g = cal_entry.get("user_portion_g", 0)
                if cal_g and abs(cal_g - logged_g) / max(cal_g, 1) > 0.2:
                    cal_warnings.append({
                        "food": fname,
                        "logged_g": logged_g,
                        "calibrated_g": cal_g,
                        "correction_count": cal_entry.get("correction_count", 0),
                    })
        if cal_warnings:
            result["calibration_warnings"] = cal_warnings

    return result


def delete_meal(data_dir: str, tz_offset: int, meal_name: str,
                day: str = None, weight: float = None,
                daily_cal: int = None, meals: int = None,
                mode: str = "balanced", region: str = None) -> dict:
    """Delete a meal from the daily log and optionally re-evaluate.

    Args:
        data_dir: Directory with daily JSON logs.
        tz_offset: Timezone offset from UTC in seconds.
        meal_name: Name of the meal to delete (e.g. "lunch", "meal_1").
        day: Date override (YYYY-MM-DD). Defaults to today (local).
        weight: Body weight in kg. If provided with cal/meals, re-evaluates.
        daily_cal: Daily calorie target. If provided with weight/meals, re-evaluates.
        meals: Meals per day (2 or 3). If provided with weight/cal, re-evaluates.
        mode: Diet mode for evaluate.
        region: Region code for produce-check.

    Returns: dict with deleted status, remaining meals, and optional evaluation.
    """
    resolved_day = day or _local_date(tz_offset)
    path = get_log_path(data_dir, resolved_day)

    if not os.path.exists(path):
        return {"deleted": False, "error": "No records for this date",
                "date": resolved_day}

    with open(path, "r", encoding="utf-8") as f:
        existing = _migrate_meals(json.load(f))

    # Find and remove the meal
    remaining = [m for m in existing if m.get("name") != meal_name]
    if len(remaining) == len(existing):
        return {"deleted": False, "error": f"Meal '{meal_name}' not found",
                "date": resolved_day, "meals": existing}

    # Write back
    with open(path, "w", encoding="utf-8") as f:
        json.dump(remaining, f, ensure_ascii=False, indent=2)

    result = {
        "deleted": True,
        "meal_name": meal_name,
        "date": resolved_day,
        "remaining_meals": remaining,
        "remaining_count": len(remaining),
    }

    # Re-evaluate if enough params provided
    if weight is not None and daily_cal is not None and meals is not None and remaining:
        # Use the last remaining meal as the checkpoint
        last_meal = remaining[-1].get("name", "breakfast")
        eval_result = evaluate(weight, daily_cal, meals,
                               last_meal, remaining, None, mode)
        result["evaluation"] = eval_result
        _save_evaluation_to_meal(data_dir, resolved_day, last_meal, eval_result)
        if region and region.upper() == "CN":
            result["produce"] = produce_check(meals, last_meal, remaining)
        else:
            result["produce"] = None
    else:
        result["evaluation"] = None
        result["produce"] = None

    return result


def query_day(data_dir: str, tz_offset: int, weight: float,
              daily_cal: int, meals: int, day: str = None,
              mode: str = "balanced", region: str = None) -> dict:
    """Load a day's records and evaluate current status.

    Args:
        data_dir: Directory with daily JSON logs.
        tz_offset: Timezone offset from UTC in seconds.
        weight: Body weight in kg.
        daily_cal: Daily calorie target (kcal).
        meals: Meals per day (2 or 3).
        day: Date override (YYYY-MM-DD). Defaults to today (local).
        mode: Diet mode for evaluate.
        region: Region code for produce-check.

    Returns: dict with date, meals, evaluation, and produce.
    """
    loaded = load_meals(data_dir, day, tz_offset)
    all_meals = loaded.get("meals", [])
    resolved_day = loaded.get("date", day or _local_date(tz_offset))

    result = {
        "date": resolved_day,
        "meals": all_meals,
        "meals_count": len(all_meals),
    }

    if not all_meals:
        result["evaluation"] = None
        result["produce"] = None
        return result

    # Determine the latest logged meal as checkpoint
    blocks = get_meal_blocks(meals)
    latest_block_idx = -1
    for m in all_meals:
        idx = find_block_index(m.get("name", ""), meals)
        if idx is not None and idx > latest_block_idx:
            latest_block_idx = idx
            latest_meal = m.get("name", "")

    if latest_block_idx < 0:
        latest_meal = all_meals[-1].get("name", "breakfast")

    result["evaluation"] = evaluate(weight, daily_cal, meals,
                                    latest_meal, all_meals, None, mode)

    if region and region.upper() == "CN":
        result["produce"] = produce_check(meals, latest_meal, all_meals)
    else:
        result["produce"] = None

    return result


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

    se = sub.add_parser("save-evaluation",
                         help="Save LLM-generated suggestion text to a meal's evaluation record")
    se.add_argument("--data-dir", type=str, required=True,
                    help="Directory with daily JSON logs")
    se.add_argument("--meal-name", type=str, required=True,
                    help="Name of meal to attach suggestion to (e.g. lunch)")
    se.add_argument("--suggestion-text", type=str, required=True,
                    help="The suggestion text shown to the user (e.g. '晚餐多点蛋白质')")
    se.add_argument("--date", type=str, default=None,
                    help="Date override (YYYY-MM-DD)")
    se.add_argument("--tz-offset", type=int, default=None,
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

    # ── Composite commands (CRUD) ──────────────────────────────────────────

    lm = sub.add_parser("log-meal",
                         help="Log a meal: detect → load → check-missing → save → evaluate → produce")
    lm.add_argument("--data-dir", type=str, required=True, help="Directory with daily JSON logs")
    lm.add_argument("--tz-offset", type=int, required=True, help="Timezone offset from UTC in seconds")
    lm.add_argument("--meals", type=int, required=True, choices=[2, 3], help="Meals per day")
    lm.add_argument("--weight", type=float, required=True, help="Body weight in kg")
    lm.add_argument("--cal", type=int, required=True, help="Daily calorie target (kcal)")
    lm.add_argument("--meal-json", type=str, required=True, help="Meal data JSON object")
    lm.add_argument("--meal-type", type=str, default=None, help="User-specified meal type (skip detect if provided)")
    lm.add_argument("--timestamp", type=str, default=None, help="ISO-8601 UTC timestamp of user message")
    lm.add_argument("--schedule", type=str, default=None, help="Meal schedule JSON")
    lm.add_argument("--mode", type=str, default="balanced", help="Diet mode for evaluate")
    lm.add_argument("--bmr", type=float, default=None, help="BMR in kcal for Case D check")
    lm.add_argument("--region", type=str, default=None, help="Region code (e.g. CN) for produce-check")
    lm.add_argument("--eaten", action="store_true", default=False, help="Whether the user has already eaten this meal")
    lm.add_argument("--append", action="store_true", default=False, help="Append items to existing meal instead of replacing")

    dm_cmd = sub.add_parser("delete-meal",
                             help="Delete a meal from today's log and optionally re-evaluate")
    dm_cmd.add_argument("--data-dir", type=str, required=True, help="Directory with daily JSON logs")
    dm_cmd.add_argument("--tz-offset", type=int, required=True, help="Timezone offset from UTC in seconds")
    dm_cmd.add_argument("--meal-name", type=str, required=True, help="Name of meal to delete")
    dm_cmd.add_argument("--date", type=str, default=None, help="Date (YYYY-MM-DD), default today")
    dm_cmd.add_argument("--weight", type=float, default=None, help="Body weight in kg (enables re-eval)")
    dm_cmd.add_argument("--cal", type=int, default=None, help="Daily calorie target (enables re-eval)")
    dm_cmd.add_argument("--meals", type=int, default=None, choices=[2, 3], help="Meals per day (enables re-eval)")
    dm_cmd.add_argument("--mode", type=str, default="balanced", help="Diet mode for evaluate")
    dm_cmd.add_argument("--region", type=str, default=None, help="Region code for produce-check")

    clk = sub.add_parser("calibration-lookup",
                          help="Look up user's portion calibrations for food items")
    clk.add_argument("--data-dir", type=str, required=True, help="Directory with daily JSON logs")
    clk.add_argument("--foods", type=str, required=True, help="JSON array of food name strings")

    qd = sub.add_parser("query-day",
                          help="Load a day's records and evaluate current status")
    qd.add_argument("--data-dir", type=str, required=True, help="Directory with daily JSON logs")
    qd.add_argument("--tz-offset", type=int, required=True, help="Timezone offset from UTC in seconds")
    qd.add_argument("--weight", type=float, required=True, help="Body weight in kg")
    qd.add_argument("--cal", type=int, required=True, help="Daily calorie target (kcal)")
    qd.add_argument("--meals", type=int, required=True, choices=[2, 3], help="Meals per day")
    qd.add_argument("--date", type=str, default=None, help="Date (YYYY-MM-DD), default today")
    qd.add_argument("--mode", type=str, default="balanced", help="Diet mode for evaluate")
    qd.add_argument("--region", type=str, default=None, help="Region code for produce-check")

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
        result = save_meal(args.data_dir, meal, args.date, getattr(args, 'tz_offset', None))
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
    elif args.cmd == "log-meal":
        try:
            meal_json = json.loads(args.meal_json)
        except json.JSONDecodeError as e:
            print(f"Error: invalid --meal-json JSON: {e}", file=sys.stderr)
            sys.exit(1)
        sched = None
        if args.schedule:
            try:
                sched = json.loads(args.schedule)
            except json.JSONDecodeError as e:
                print(f"Error: invalid --schedule JSON: {e}", file=sys.stderr)
                sys.exit(1)
        result = log_meal(
            data_dir=args.data_dir, tz_offset=args.tz_offset,
            meals=args.meals, weight=args.weight, daily_cal=args.cal,
            meal_json=meal_json, meal_type=args.meal_type,
            timestamp=args.timestamp, schedule=sched,
            mode=args.mode, bmr=args.bmr, region=args.region,
            eaten=args.eaten, append=args.append,
        )
    elif args.cmd == "delete-meal":
        result = delete_meal(
            data_dir=args.data_dir, tz_offset=args.tz_offset,
            meal_name=args.meal_name, day=args.date,
            weight=args.weight, daily_cal=args.cal,
            meals=args.meals, mode=args.mode, region=args.region,
        )
    elif args.cmd == "save-evaluation":
        result = save_evaluation_text(
            data_dir=args.data_dir, meal_name=args.meal_name,
            suggestion_text=args.suggestion_text,
            day=args.date, tz_offset=getattr(args, 'tz_offset', None),
        )
    elif args.cmd == "calibration-lookup":
        try:
            foods = json.loads(args.foods)
        except json.JSONDecodeError as e:
            print(f"Error: invalid --foods JSON: {e}", file=sys.stderr)
            sys.exit(1)
        result = calibration_lookup(args.data_dir, foods)
    elif args.cmd == "query-day":
        result = query_day(
            data_dir=args.data_dir, tz_offset=args.tz_offset,
            weight=args.weight, daily_cal=args.cal,
            meals=args.meals, day=args.date,
            mode=args.mode, region=args.region,
        )

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
