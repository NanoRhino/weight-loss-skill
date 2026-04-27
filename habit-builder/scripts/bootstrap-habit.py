#!/usr/bin/env python3
"""
Bootstrap habits for a new user.
Deterministic: reads profile, picks habits, activates them, creates cron reminders.

Usage:
  python3 bootstrap-habit.py \
    --workspace-dir /path/to/workspace \
    --base-dir /path/to/habit-builder \
    --agent-id wechat-dm-xxx \
    --channel wechat \
    --notification-manager-dir /path/to/notification-manager
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# Default habits ranked by general impact for weight-loss users.
# timing_rule: how to derive the cron time from the user's meal schedule.
#   "before_first_meal:-30"  = first meal time minus 30 min
#   "after_meal:lunch:+30"   = lunch time plus 30 min
#   "before_meal:lunch:-15"  = lunch time minus 15 min
#   "fixed:22:30"            = fixed time
DEFAULT_HABITS = [
    {
        "id": "water-after-waking",
        "description": "起床后喝一杯水",
        "trigger": "起床后",
        "behavior": "喝一杯温水",
        "cadence": "daily_fixed",
        "gap_keywords": ["喝水", "水", "hydrat", "water", "drink"],
        "timing_rule": "before_first_meal:-30",
        "checkin_zh": "早上好～起来后有喝杯温水吗？💧",
        "user_msg_zh": "每天早上起来后喝一杯温水 💧 很小的一步，但对代谢特别有帮助。",
        "timing_desc_zh": "每天早上{time}提醒你",
    },
    {
        "id": "walk-after-lunch",
        "description": "午饭后散步5分钟",
        "trigger": "吃完午饭后",
        "behavior": "出门走5分钟",
        "cadence": "daily_fixed",
        "gap_keywords": ["久坐", "不动", "sedentary", "不运动", "exercise"],
        "timing_rule": "after_last_meal:+30",
        "checkin_zh": "吃完了吗？出去走5分钟消消食～🚶‍♀️",
        "user_msg_zh": "午饭后出门走5分钟 🚶‍♀️ 消消食顺便活动一下，不用多就5分钟。",
        "timing_desc_zh": "每天{time}提醒你",
    },
    {
        "id": "protein-at-lunch",
        "description": "午餐加一份蛋白质",
        "trigger": "准备吃午餐时",
        "behavior": "确保有一份蛋白质（鸡蛋、鸡胸肉、豆腐等）",
        "cadence": "daily_fixed",
        "gap_keywords": ["蛋白", "protein", "肉", "营养"],
        "timing_rule": "before_last_meal:-15",
        "checkin_zh": "午饭准备好了吗？记得加份蛋白质哦 🥚",
        "user_msg_zh": "午餐的时候确保有一份蛋白质（蛋、鸡胸、豆腐都行）🥚 帮你扛饿到晚上。",
        "timing_desc_zh": "每天{time}提醒你",
    },
    {
        "id": "no-phone-before-sleep",
        "description": "睡前放下手机",
        "trigger": "22:30闹钟响时",
        "behavior": "把手机放到伸手够不到的地方",
        "cadence": "daily_fixed",
        "gap_keywords": ["睡", "sleep", "熬夜", "late", "晚睡"],
        "timing_rule": "fixed:22:30",
        "checkin_zh": "手机放个假的时间到了📱 放远一点，早点休息～",
        "user_msg_zh": "晚上10:30给手机放个假📱 放到够不着的地方，帮你早点入睡。",
        "timing_desc_zh": "每天晚上22:30提醒你",
    },
]


def read_file(path):
    try:
        return Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def log(msg):
    print(f"[bootstrap-habit] {msg}", file=sys.stderr)


def parse_meal_times(workspace_dir):
    """Parse meal times from health-profile.md."""
    content = read_file(os.path.join(workspace_dir, "health-profile.md"))
    meals = {}
    # Match patterns like "- **Breakfast:** 08:00" or "- **Meal 1:** 09:00"
    for line in content.split("\n"):
        m = re.search(r'\*\*(Breakfast|Lunch|Dinner|Meal\s*\d+):?\*\*:?\s*(\d{1,2}:\d{2})', line, re.IGNORECASE)
        if m:
            name = m.group(1).lower().strip()
            time_str = m.group(2)
            meals[name] = time_str

    # Normalize to ordered list
    ordered = []
    for key in sorted(meals.keys()):
        ordered.append({"name": key, "time": meals[key]})

    # Sort by time
    ordered.sort(key=lambda x: x["time"])
    return ordered


def time_add_minutes(time_str, minutes):
    """Add minutes to HH:MM, return HH:MM."""
    h, m = map(int, time_str.split(":"))
    total = h * 60 + m + minutes
    total = max(0, min(total, 23 * 60 + 59))  # clamp to 00:00-23:59
    return f"{total // 60:02d}:{total % 60:02d}"


def resolve_timing(rule, meal_times):
    """Resolve a timing_rule to a HH:MM time string."""
    if not meal_times:
        # Fallback defaults
        meal_times = [
            {"name": "breakfast", "time": "08:00"},
            {"name": "lunch", "time": "12:00"},
            {"name": "dinner", "time": "18:00"},
        ]

    first_meal = meal_times[0]["time"]
    last_meal = meal_times[-1]["time"]

    if rule.startswith("fixed:"):
        return rule.split(":", 1)[1]
    elif rule.startswith("before_first_meal:"):
        offset = int(rule.split(":")[1])
        return time_add_minutes(first_meal, offset)
    elif rule.startswith("after_first_meal:"):
        offset = int(rule.split(":")[1])
        return time_add_minutes(first_meal, offset)
    elif rule.startswith("before_last_meal:"):
        offset = int(rule.split(":")[1])
        return time_add_minutes(last_meal, offset)
    elif rule.startswith("after_last_meal:"):
        offset = int(rule.split(":")[1])
        return time_add_minutes(last_meal, offset)
    else:
        # Fallback
        return "09:00"


def pick_habits(workspace_dir, max_count=3):
    """Pick up to max_count habits based on health-preferences and profile."""
    prefs = read_file(os.path.join(workspace_dir, "health-preferences.md")).lower()
    profile = read_file(os.path.join(workspace_dir, "health-profile.md")).lower()
    combined = prefs + "\n" + profile

    habits_path = os.path.join(workspace_dir, "habits.active")
    existing_ids = set()
    if os.path.exists(habits_path):
        try:
            existing = json.loads(Path(habits_path).read_text(encoding="utf-8"))
            existing_ids = {h.get("habit_id") for h in existing}
        except (json.JSONDecodeError, TypeError):
            pass

    scored = []
    for i, habit in enumerate(DEFAULT_HABITS):
        if habit["id"] in existing_ids:
            continue
        score = len(DEFAULT_HABITS) - i
        for kw in habit["gap_keywords"]:
            if kw in combined:
                score += 10
                break
        scored.append((score, habit))

    scored.sort(key=lambda x: -x[0])
    return [h for _, h in scored[:max_count]]


def activate_habit(habit, base_dir, source_advice):
    """Run action-pipeline.py activate to create the habit entry."""
    action = {
        "action_id": habit["id"],
        "description": habit["description"],
        "trigger": habit["trigger"],
        "behavior": habit["behavior"],
        "trigger_cadence": habit["cadence"],
    }
    cmd = [
        sys.executable,
        os.path.join(base_dir, "scripts", "action-pipeline.py"),
        "activate",
        "--action", json.dumps(action, ensure_ascii=False),
        "--source", "habit-builder",
        "--source-advice", source_advice,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None, result.stderr
    return json.loads(result.stdout), None


def create_habit_cron(habit_def, reminder_time, agent_id, channel, nm_dir):
    """Create a recurring cron job for this habit's check-in."""
    h, m = reminder_time.split(":")
    cron_expr = f"{m} {h} * * *"
    checkin_text = habit_def["checkin_zh"]
    habit_id = habit_def["id"]

    # The cron message tells the agent to send this exact check-in
    message = (
        f"Habit check-in for {habit_id}. "
        f"Send this message to the user exactly as written (do not add anything): "
        f"{checkin_text}"
    )

    cmd = [
        "bash", os.path.join(nm_dir, "scripts", "create-reminder.sh"),
        "--agent", agent_id,
        "--channel", channel,
        "--name", f"Habit: {habit_def['description']}",
        "--message", message,
        "--cron", cron_expr,
        "--exact",  # Don't anti-burst shift habit reminders
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log(f"Warning: failed to create cron for {habit_id}: {result.stderr}")
        return None
    return result.stdout


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-dir", required=True)
    parser.add_argument("--base-dir", required=True)
    parser.add_argument("--agent-id", required=True, help="Agent ID for cron jobs")
    parser.add_argument("--channel", default="wechat", help="Delivery channel")
    parser.add_argument("--notification-manager-dir", required=True,
                        help="Path to notification-manager skill dir")
    parser.add_argument("--max-habits", type=int, default=3)
    args = parser.parse_args()

    # Check if onboarding is complete
    if not os.path.exists(os.path.join(args.workspace_dir, "health-profile.md")):
        print(json.dumps({"action": "skip", "reason": "no health-profile.md"}))
        return

    # Check if habits already exist
    habits_path = os.path.join(args.workspace_dir, "habits.active")
    if os.path.exists(habits_path):
        try:
            existing = json.loads(Path(habits_path).read_text(encoding="utf-8"))
            if existing:
                print(json.dumps({"action": "skip", "reason": "habits already exist", "count": len(existing)}))
                return
        except (json.JSONDecodeError, TypeError):
            pass

    # Parse meal times
    meal_times = parse_meal_times(args.workspace_dir)
    log(f"Meal times: {meal_times}")

    # Pick habits
    habits_to_activate = pick_habits(args.workspace_dir, max_count=args.max_habits)
    if not habits_to_activate:
        print(json.dumps({"action": "skip", "reason": "no suitable habit found"}))
        return

    # Activate all selected habits
    activated = []
    crons_created = []
    for habit_def in habits_to_activate:
        entry, err = activate_habit(habit_def, args.base_dir,
                                     f"Auto-bootstrap: {habit_def['description']}")
        if err:
            log(f"Warning: failed to activate {habit_def['id']}: {err}")
            continue

        # Resolve timing and create cron
        reminder_time = resolve_timing(habit_def["timing_rule"], meal_times)
        entry["reminder_time"] = reminder_time  # store for reference

        cron_out = create_habit_cron(
            habit_def, reminder_time,
            args.agent_id, args.channel, args.notification_manager_dir
        )
        if cron_out:
            crons_created.append({"habit_id": habit_def["id"], "time": reminder_time})

        activated.append(entry)

    if not activated:
        print(json.dumps({"action": "error", "error": "all activations failed"}))
        sys.exit(1)

    # Write to habits.active
    existing = []
    if os.path.exists(habits_path):
        try:
            existing = json.loads(Path(habits_path).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, TypeError):
            pass

    all_habits = existing + activated
    Path(habits_path).write_text(
        json.dumps(all_habits, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    # Build user-facing message
    habit_lines = []
    for h_def, h_entry in zip(habits_to_activate[:len(activated)], activated):
        time_str = h_entry.get("reminder_time", "")
        timing_desc = h_def["timing_desc_zh"].format(time=time_str)
        habit_lines.append(f"• {h_def['user_msg_zh']}\n  ⏰ {timing_desc}")

    habits_text = "\n".join(habit_lines)
    user_msg = f"Boss～帮你安排了{len(activated)}个小习惯：\n\n{habits_text}\n\n不用刻意，慢慢来就好 😊"

    print(json.dumps({
        "action": "activated",
        "habits": activated,
        "crons": crons_created,
        "count": len(activated),
        "user_message": user_msg,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
