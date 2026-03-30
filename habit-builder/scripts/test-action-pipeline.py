#!/usr/bin/env python3
"""
action-pipeline.py 端到端测试。

5 个场景覆盖完整生命周期：
  1. 把建议拆成行动并排优先级
  2. 每天喝水行为的提醒频率从第 0 天到第 50 天逐步递减
  3. 每周备餐行为：什么时候能毕业
  4. 条件触发行为（外出吃饭时点清淡的）：连续不回应的停滞检测
  5. 完整链路：激活 → 确定提醒频率 → 毕业判定 → 兜底询问
"""

import json
import subprocess
import sys
from datetime import datetime, timedelta

SCRIPT = "habit-builder/scripts/action-pipeline.py"
errors = []


def run(args: list[str]) -> dict | list:
    result = subprocess.run(
        ["python3", SCRIPT] + args,
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"脚本执行失败: {result.stderr}")
    return json.loads(result.stdout)


def check(name: str, condition: bool, detail: str = ""):
    status = "✓ 通过" if condition else "✗ 失败"
    msg = f"  {status}  {name}"
    if detail and not condition:
        msg += f"  （{detail}）"
    print(msg)
    if not condition:
        errors.append(name)


# ─────────────────────────────────────────────────────────────────────────────
# 测试 1：把建议"晚上少吃零食"拆成 3 个行动，排优先级
# ─────────────────────────────────────────────────────────────────────────────
print()
print("═" * 55)
print("测试 1：建议拆解与优先级排序")
print("─" * 55)
print("场景：用户问「晚上总忍不住吃零食怎么办」")
print("AI 拆出 3 个行动：")
print("  • 把零食从茶几收到高柜（影响大、容易做、能带动其他行动）")
print("  • 设 22 点闹钟开始洗漱（影响大、稍难、能带动其他行动）")
print("  • 晚 9 点后不吃东西（影响一般、很难、独立行动）")
print("─" * 55)

actions = [
    {"action_id": "move-snacks",       "impact": 3, "ease": 3, "chain": True},
    {"action_id": "wind-down-alarm",   "impact": 3, "ease": 2, "chain": True},
    {"action_id": "no-food-after-9pm", "impact": 2, "ease": 1, "chain": False},
]
result = run(["prioritize", "--actions", json.dumps(actions)])

check("返回了 3 个行动", len(result) == 3)
check("「收零食」排第一（得分 10 = 影响3×容易3+带动1）",
      result[0]["action_id"] == "move-snacks" and result[0]["priority_score"] == 10)
check("「设闹钟」排第二（得分 7 = 影响3×容易2+带动1）",
      result[1]["action_id"] == "wind-down-alarm" and result[1]["priority_score"] == 7)
check("「晚9点后不吃」排最后（得分 2 = 影响2×容易1+0）",
      result[2]["action_id"] == "no-food-after-9pm" and result[2]["priority_score"] == 2)


# ─────────────────────────────────────────────────────────────────────────────
# 测试 2：每天喝水的提醒频率，从第 0 天到第 50 天
# ─────────────────────────────────────────────────────────────────────────────
print()
print("═" * 55)
print("测试 2：每天喝水——提醒频率随时间递减")
print("─" * 55)
print("场景：用户接受了「起床后喝一杯水」的习惯")
print("预期：刚开始每天提醒，慢慢减少，最后几乎不提")
print("─" * 55)

r = run(["schedule", "--cadence", "daily_fixed", "--days", "0"])
check("第 0 天：锚定期，每天提醒",
      r["phase"] == "anchor" and r["value"] == 1)

r = run(["schedule", "--cadence", "daily_fixed", "--days", "5"])
check("第 5 天：还在锚定期，每天提醒",
      r["phase"] == "anchor" and r["value"] == 1)

r = run(["schedule", "--cadence", "daily_fixed", "--days", "10"])
check("第 10 天：进入建设期，每 3 天提醒一次",
      r["phase"] == "build" and r["value"] == 3)

r = run(["schedule", "--cadence", "daily_fixed", "--days", "25"])
check("第 25 天：进入巩固期，每 5 天提醒一次",
      r["phase"] == "solidify" and r["value"] == 5)

r = run(["schedule", "--cadence", "daily_fixed", "--days", "50"])
check("第 50 天：进入自动期，每周提醒一次",
      r["phase"] == "autopilot" and r["value"] == 7)


# ─────────────────────────────────────────────────────────────────────────────
# 测试 3：每周日备餐——什么时候能毕业
# ─────────────────────────────────────────────────────────────────────────────
print()
print("═" * 55)
print("测试 3：每周日备餐——毕业需要多少次")
print("─" * 55)
print("场景：用户每周日备餐，系统判断什么时候可以不再提醒")
print("规则：周频行为需要至少 6 次记录，完成率 ≥ 80%")
print("─" * 55)

log_5 = [
    {"date": "2026-03-02", "result": "completed", "self_initiated": True},
    {"date": "2026-03-09", "result": "completed", "self_initiated": False},
    {"date": "2026-03-16", "result": "completed", "self_initiated": True},
    {"date": "2026-03-23", "result": "completed", "self_initiated": False},
    {"date": "2026-03-30", "result": "completed", "self_initiated": True},
]
r = run(["check-graduation", "--cadence", "weekly", "--log", json.dumps(log_5)])
check("坚持了 5 周：还不能毕业（数据不够，至少要 6 次）",
      r["eligible"] == False and "insufficient_data" in r.get("reason", ""))

log_6 = log_5 + [
    {"date": "2026-04-06", "result": "completed", "self_initiated": False},
]
r = run(["check-graduation", "--cadence", "weekly", "--log", json.dumps(log_6)])
check("坚持了 6 周，全部完成：可以毕业！",
      r["eligible"] == True)
check("  完成率 100%", r["signal_1_completion"]["rate"] == 1.0)
check("  自发执行率 50%（3 次主动 / 6 次总共）", r["signal_2_self_init"]["rate"] == 0.5)

log_6_low = [
    {"date": "2026-03-02", "result": "completed", "self_initiated": False},
    {"date": "2026-03-09", "result": "missed",    "self_initiated": False},
    {"date": "2026-03-16", "result": "completed", "self_initiated": False},
    {"date": "2026-03-23", "result": "missed",    "self_initiated": False},
    {"date": "2026-03-30", "result": "completed", "self_initiated": False},
    {"date": "2026-04-06", "result": "completed", "self_initiated": False},
]
r = run(["check-graduation", "--cadence", "weekly", "--log", json.dumps(log_6_low)])
check("坚持了 6 周但只完成 4 次（67%）：不能毕业（需要 ≥ 80%）",
      r["eligible"] == False)


# ─────────────────────────────────────────────────────────────────────────────
# 测试 4：「外出吃饭时点清淡的」——连续不回应会怎样
# ─────────────────────────────────────────────────────────────────────────────
print()
print("═" * 55)
print("测试 4：条件触发行为——连续不理会的停滞检测")
print("─" * 55)
print("场景：用户接受了「外出吃饭时选清淡选项」的习惯")
print("系统只在检测到用户外出吃饭时才会提醒")
print("如果连续 3 次提醒都不回应，系统自动暂停")
print("─" * 55)

log_stall = [
    {"date": "2026-03-10", "result": "completed",   "self_initiated": False},
    {"date": "2026-03-15", "result": "completed",   "self_initiated": False},
    {"date": "2026-03-20", "result": "no_response",  "self_initiated": False},
    {"date": "2026-03-25", "result": "no_response",  "self_initiated": False},
    {"date": "2026-04-01", "result": "no_response",  "self_initiated": False},
]
r = run(["check-graduation", "--cadence", "conditional", "--log", json.dumps(log_stall)])
check("连续 3 次不回应：触发停滞，系统暂停提醒", r["stall"] == True)
check("停滞状态下不能毕业", r["eligible"] == False)

log_recover = log_stall[:4] + [
    {"date": "2026-04-01", "result": "completed", "self_initiated": False},
]
r = run(["check-graduation", "--cadence", "conditional", "--log", json.dumps(log_recover)])
check("中间回应了一次：停滞解除，继续跟踪", r["stall"] == False)


# ─────────────────────────────────────────────────────────────────────────────
# 测试 5：完整链路——从激活到毕业
# ─────────────────────────────────────────────────────────────────────────────
print()
print("═" * 55)
print("测试 5：完整链路——一个习惯从头到尾")
print("─" * 55)
print("场景：建议「多喝水少喝奶茶」→ 激活「起床后喝水」→")
print("      每天提醒 → 坚持 14 天 → 判断能否毕业")
print("─" * 55)

action = {
    "action_id": "water-after-waking",
    "description": "起床后喝一杯水",
    "trigger": "起床后",
    "behavior": "喝一杯温水",
    "trigger_cadence": "daily_fixed",
}
r = run(["activate", "--action", json.dumps(action),
         "--source-advice", "多喝水少喝奶茶"])

print("  ── 第一步：激活行动 ──")
check("行动 ID 正确：water-after-waking",
      r["habit_id"] == "water-after-waking")
check("提醒类型自动映射为「餐后提醒」",
      r["type"] == "post-meal")
check("记住了来源建议：「多喝水少喝奶茶」",
      r["source_advice"] == "多喝水少喝奶茶")
check("初始阶段为「锚定期」",
      r["phase"] == "anchor")

print("  ── 第二步：确认提醒频率 ──")
r = run(["schedule", "--cadence", "daily_fixed", "--days", "1"])
check("第 1 天：每天在早餐对话中提醒喝水", r["value"] == 1)

print("  ── 第三步：坚持 14 天后，判断能否毕业 ──")
today = datetime.now()

# 情况 A：14 天全部完成，且 33% 是主动做的
log_good = []
for i in range(14):
    d = today - timedelta(days=14 - i)
    log_good.append({
        "date": d.strftime("%Y-%m-%d"),
        "result": "completed",
        "self_initiated": i % 3 == 0,
    })
r = run(["check-graduation", "--cadence", "daily_fixed",
         "--log", json.dumps(log_good)])
check("14 天全完成 + 33% 主动执行 → 可以毕业！",
      r["eligible"] == True)
check("  完成率 100%", r["signal_1_completion"]["rate"] == 1.0)
check("  自发执行率 ≥ 30%", r["signal_2_self_init"]["rate"] >= 0.30)

# 情况 B：14 天全完成，但从来不是主动做的
print("  ── 第四步：如果用户从不主动喝水呢？ ──")
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
check("14 天全完成但 0% 主动 → 还不能自动毕业",
      r["eligible"] == False)
check("系统会问用户：「这个习惯还需要我提醒吗？」",
      r.get("action") == "ask_signal_3" and "提醒" in r.get("prompt", ""))


# ─────────────────────────────────────────────────────────────────────────────
# 汇总
# ─────────────────────────────────────────────────────────────────────────────
print()
print("═" * 55)
total = len(errors)
if total == 0:
    print(f"全部 32 项检查通过 ✓")
else:
    print(f"{total} 项检查未通过：")
    for e in errors:
        print(f"  ✗ {e}")
print("═" * 55)
sys.exit(1 if total else 0)
