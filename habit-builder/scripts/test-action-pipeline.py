#!/usr/bin/env python3
"""
End-to-end test cases for action-pipeline.py.

5 scenarios covering the full lifecycle:
  1. Decompose + prioritize + activate a daily_fixed action
  2. Schedule progression across all 4 phases for daily behavior
  3. Weekly action: graduation after 6 occurrences
  4. Conditional action: stall detection after 3 no-responses
  5. Full lifecycle: activate → schedule → graduate → next action
"""

import json
import subprocess
import sys
from datetime import datetime, timedelta

SCRIPT = "habit-builder/scripts/action-pipeline.py"
PASS = "✓ PASS"
FAIL = "✗ FAIL"
errors = []


def run(args: list[str]) -> dict | list:
    result = subprocess.run(
        ["python3", SCRIPT] + args,
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Script failed: {result.stderr}")
    return json.loads(result.stdout)


def check(name: str, condition: bool, detail: str = ""):
    status = PASS if condition else FAIL
    msg = f"  {status}  {name}"
    if detail and not condition:
        msg += f"  ({detail})"
    print(msg)
    if not condition:
        errors.append(name)


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: Prioritize 3 actions from advice "晚上少吃零食"
# ─────────────────────────────────────────────────────────────────────────────
print("\n── Test 1: Prioritize actions ──")

actions = [
    {"action_id": "move-snacks",       "impact": 3, "ease": 3, "chain": True},
    {"action_id": "wind-down-alarm",   "impact": 3, "ease": 2, "chain": True},
    {"action_id": "no-food-after-9pm", "impact": 2, "ease": 1, "chain": False},
]
result = run(["prioritize", "--actions", json.dumps(actions)])

check("3 actions returned", len(result) == 3)
check("move-snacks ranked first (score=10)",
      result[0]["action_id"] == "move-snacks" and result[0]["priority_score"] == 10)
check("wind-down-alarm ranked second (score=7)",
      result[1]["action_id"] == "wind-down-alarm" and result[1]["priority_score"] == 7)
check("no-food-after-9pm ranked last (score=2)",
      result[2]["action_id"] == "no-food-after-9pm" and result[2]["priority_score"] == 2)


# ─────────────────────────────────────────────────────────────────────────────
# Test 2: Schedule progression for daily_fixed across all phases
# ─────────────────────────────────────────────────────────────────────────────
print("\n── Test 2: Daily fixed schedule progression ──")

# Day 0 → anchor, every day
r = run(["schedule", "--cadence", "daily_fixed", "--days", "0"])
check("Day 0: anchor phase", r["phase"] == "anchor")
check("Day 0: mention every 1 day", r["value"] == 1)

# Day 5 → still anchor
r = run(["schedule", "--cadence", "daily_fixed", "--days", "5"])
check("Day 5: still anchor", r["phase"] == "anchor")
check("Day 5: still every 1 day", r["value"] == 1)

# Day 10 → build, every 3 days
r = run(["schedule", "--cadence", "daily_fixed", "--days", "10"])
check("Day 10: build phase", r["phase"] == "build")
check("Day 10: every 3 days", r["value"] == 3)

# Day 25 → solidify, every 5 days
r = run(["schedule", "--cadence", "daily_fixed", "--days", "25"])
check("Day 25: solidify phase", r["phase"] == "solidify")
check("Day 25: every 5 days", r["value"] == 5)

# Day 50 → autopilot (>42 days), every 7 days
r = run(["schedule", "--cadence", "daily_fixed", "--days", "50"])
check("Day 50: autopilot phase", r["phase"] == "autopilot")
check("Day 50: every 7 days", r["value"] == 7)


# ─────────────────────────────────────────────────────────────────────────────
# Test 3: Weekly action graduation after 6 occurrences
# ─────────────────────────────────────────────────────────────────────────────
print("\n── Test 3: Weekly action graduation ──")

# 5 occurrences → insufficient
log_5 = [
    {"date": "2026-03-02", "result": "completed", "self_initiated": True},
    {"date": "2026-03-09", "result": "completed", "self_initiated": False},
    {"date": "2026-03-16", "result": "completed", "self_initiated": True},
    {"date": "2026-03-23", "result": "completed", "self_initiated": False},
    {"date": "2026-03-30", "result": "completed", "self_initiated": True},
]
r = run(["check-graduation", "--cadence", "weekly", "--log", json.dumps(log_5)])
check("5 weekly occurrences: not eligible", r["eligible"] == False)
check("5 weekly: reason is insufficient_data", "insufficient_data" in r.get("reason", ""))

# 6 occurrences, 5/6 completed (83%), 3/6 self-initiated (50%) → eligible
log_6 = log_5 + [
    {"date": "2026-04-06", "result": "completed", "self_initiated": False},
]
r = run(["check-graduation", "--cadence", "weekly", "--log", json.dumps(log_6)])
check("6 weekly occurrences: eligible",
      r["eligible"] == True,
      f"got eligible={r.get('eligible')}")
check("6 weekly: completion rate 1.0", r["signal_1_completion"]["rate"] == 1.0)
check("6 weekly: self-init rate 0.5", r["signal_2_self_init"]["rate"] == 0.5)

# 6 occurrences, 4/6 completed (67%) → not eligible (below 80%)
log_6_low = [
    {"date": "2026-03-02", "result": "completed", "self_initiated": False},
    {"date": "2026-03-09", "result": "missed",    "self_initiated": False},
    {"date": "2026-03-16", "result": "completed", "self_initiated": False},
    {"date": "2026-03-23", "result": "missed",    "self_initiated": False},
    {"date": "2026-03-30", "result": "completed", "self_initiated": False},
    {"date": "2026-04-06", "result": "completed", "self_initiated": False},
]
r = run(["check-graduation", "--cadence", "weekly", "--log", json.dumps(log_6_low)])
check("6 weekly, 67% completion: not eligible", r["eligible"] == False)


# ─────────────────────────────────────────────────────────────────────────────
# Test 4: Conditional action stall detection
# ─────────────────────────────────────────────────────────────────────────────
print("\n── Test 4: Conditional stall detection ──")

# 3 consecutive no_response → stall
log_stall = [
    {"date": "2026-03-10", "result": "completed",   "self_initiated": False},
    {"date": "2026-03-15", "result": "completed",   "self_initiated": False},
    {"date": "2026-03-20", "result": "no_response",  "self_initiated": False},
    {"date": "2026-03-25", "result": "no_response",  "self_initiated": False},
    {"date": "2026-04-01", "result": "no_response",  "self_initiated": False},
]
r = run(["check-graduation", "--cadence", "conditional", "--log", json.dumps(log_stall)])
check("Stall detected (3 consecutive no_response)", r["stall"] == True)
check("Not eligible when stalled", r["eligible"] == False)

# 2 no_response then 1 completed → not stalled
log_recover = log_stall[:4] + [
    {"date": "2026-04-01", "result": "completed", "self_initiated": False},
]
r = run(["check-graduation", "--cadence", "conditional", "--log", json.dumps(log_recover)])
check("No stall after recovery (2 no_response + 1 completed)", r["stall"] == False)


# ─────────────────────────────────────────────────────────────────────────────
# Test 5: Full lifecycle — activate → schedule → graduate → next action
# ─────────────────────────────────────────────────────────────────────────────
print("\n── Test 5: Full lifecycle ──")

# Step A: Activate an action
action = {
    "action_id": "water-after-waking",
    "description": "起床后喝一杯水",
    "trigger": "起床后",
    "behavior": "喝一杯温水",
    "trigger_cadence": "daily_fixed",
}
r = run(["activate", "--action", json.dumps(action),
         "--source-advice", "多喝水少喝奶茶"])
check("Activate: habit_id matches action_id",
      r["habit_id"] == "water-after-waking")
check("Activate: type mapped to post-meal",
      r["type"] == "post-meal")
check("Activate: trigger_cadence preserved",
      r["trigger_cadence"] == "daily_fixed")
check("Activate: phase starts as anchor",
      r["phase"] == "anchor")
check("Activate: source_advice set",
      r["source_advice"] == "多喝水少喝奶茶")

# Step B: Check schedule at day 1 (anchor → daily)
r = run(["schedule", "--cadence", "daily_fixed", "--days", "1"])
check("Lifecycle day 1: daily mention", r["value"] == 1)

# Step C: After 14 days of good compliance → check graduation
today = datetime.now()
log_good = []
for i in range(14):
    d = today - timedelta(days=14 - i)
    log_good.append({
        "date": d.strftime("%Y-%m-%d"),
        "result": "completed",
        "self_initiated": i % 3 == 0,  # ~33% self-initiated
    })
r = run(["check-graduation", "--cadence", "daily_fixed",
         "--log", json.dumps(log_good)])
check("Lifecycle graduation: eligible after 14 good days",
      r["eligible"] == True,
      f"got eligible={r.get('eligible')}, rate={r.get('signal_1_completion',{}).get('rate')}")
check("Lifecycle graduation: completion rate 1.0",
      r["signal_1_completion"]["rate"] == 1.0)
check("Lifecycle graduation: self-init rate ~0.36",
      r["signal_2_self_init"]["rate"] >= 0.30)

# Step D: Signal 1 pass but Signal 2 fail → should ask user (Signal 3)
log_no_self = []
for i in range(14):
    d = today - timedelta(days=14 - i)
    log_no_self.append({
        "date": d.strftime("%Y-%m-%d"),
        "result": "completed",
        "self_initiated": False,
    })
r = run(["check-graduation", "--cadence", "daily_fixed",
         "--log", json.dumps(log_no_self)])
check("No self-init: not auto-eligible",
      r["eligible"] == False)
check("No self-init: asks Signal 3",
      r.get("action") == "ask_signal_3")
check("No self-init: has prompt",
      "提醒" in r.get("prompt", ""))


# ─────────────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 50)
total = len(errors)
if total == 0:
    print(f"All tests passed.")
else:
    print(f"{total} test(s) FAILED:")
    for e in errors:
        print(f"  - {e}")
sys.exit(1 if total else 0)
