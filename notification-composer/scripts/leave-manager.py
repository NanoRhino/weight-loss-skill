#!/usr/bin/env python3
"""Manage user leave/vacation periods.

Commands:
  check   — Check if today is within a leave period
  set     — Set a leave period
  clear   — Clear active leave
  info    — Show current leave status

Usage:
  python3 leave-manager.py check --data-dir <dir> --tz-offset <seconds>
  python3 leave-manager.py set --data-dir <dir> --tz-offset <seconds> --start 2026-05-01 --end 2026-05-05 [--reason "五一出游"]
  python3 leave-manager.py clear --data-dir <dir>
  python3 leave-manager.py info --data-dir <dir> --tz-offset <seconds>
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone


def _normalize_path(p):
    return re.sub(r'(workspace-(?:wechat|wecom)-dm-)([^/]+)',
                  lambda m: m.group(1) + m.group(2).lower(), p)


def _leave_path(data_dir):
    return os.path.join(data_dir, "leave.json")


def _load(data_dir):
    path = _leave_path(data_dir)
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(data_dir, data):
    path = _leave_path(data_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _today(tz_offset, mock_date=None):
    if mock_date:
        return mock_date
    tz = timezone(timedelta(seconds=tz_offset))
    return datetime.now(tz).strftime("%Y-%m-%d")


def _clear_holiday_asked(data_dir):
    """Remove holiday_asked from engagement.json when user confirms leave."""
    eng_path = os.path.join(os.path.dirname(data_dir.rstrip("/")), "data", "engagement.json")
    # data_dir might already be the data dir
    if not os.path.exists(eng_path):
        eng_path = os.path.join(data_dir, "engagement.json")
    if not os.path.exists(eng_path):
        return
    try:
        with open(eng_path) as f:
            eng = json.load(f)
        if "holiday_asked" in eng:
            del eng["holiday_asked"]
            with open(eng_path, "w") as f:
                json.dump(eng, f, indent=2, ensure_ascii=False)
    except (json.JSONDecodeError, IOError):
        pass


# ─── lifecycle API 同步(stage 真源在 DB) ──────────────────────────────────
# 请假的天数/原因等业务细节仍以 leave.json 为准(cron 提醒拦截读它);
# 但 stage 的 frozen 状态必须同步进 lifecycle DB,这样 lifecycle-stage plugin
# 才能注入 frozen=true 让 agent 在请假期不催打卡。双写过渡:leave.json + DB。

# 2026-07-01 重命名过渡:新名 DATA_API_URL 优先,老名 LIFECYCLE_API_URL 兼容
LIFECYCLE_API = os.environ.get("DATA_API_URL") or os.environ.get("LIFECYCLE_API_URL", "http://127.0.0.1:3100")


def _account_id_from_data_dir(data_dir):
    """从 workspace 路径提取 account_id。

    data_dir 形如 .../workspace-wechat-dm-<acc>/data → <acc>。
    取不到返回 None(同步静默跳过,不影响 leave.json 主流程)。
    """
    m = re.search(r"workspace-(?:wechat|wecom)-dm-([^/]+)", data_dir)
    return m.group(1).lower() if m else None


def _sync_silence(account_id, state, frozen_until=None):
    """调 POST /v1/lifecycle/silence 同步 frozen/active 状态到 DB。

    非关键:失败只告警,不阻塞 leave.json 主流程(lifecycle 不可用时
    请假仍按 leave.json 生效,只是 plugin 注入不到 frozen,降级可接受)。
    """
    import urllib.request
    import urllib.error

    if not account_id:
        return
    body = {"account_id": account_id, "state": state}
    if state == "frozen" and frozen_until:
        body["frozen_until"] = frozen_until
        body["reason"] = "leave"
    try:
        req = urllib.request.Request(
            f"{LIFECYCLE_API}/v1/lifecycle/silence",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=3) as r:
            r.read()
    except Exception as e:  # noqa: BLE001 — 同步失败不致命
        print(f"[leave-manager] /silence sync failed ({state}): {e}", file=sys.stderr)


def cmd_check(args):
    """Check if today is within a leave period. Returns JSON.

    Simplified: file exists with start/end = leave is set.
    No 'active' field needed.
    """
    path = _leave_path(args.data_dir)
    if not os.path.exists(path):
        print(json.dumps({"on_leave": False}))
        return

    data = _load(args.data_dir)
    today = _today(args.tz_offset, getattr(args, 'mock_date', None))

    start = data.get("start", "")
    end = data.get("end", "")

    if not start or not end:
        print(json.dumps({"on_leave": False}))
        return

    on_leave = start <= today <= end

    # Check if leave ended yesterday (for welcome back)
    tz = timezone(timedelta(seconds=args.tz_offset))
    if getattr(args, 'mock_date', None):
        yesterday = (datetime.strptime(args.mock_date, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        yesterday = (datetime.now(tz) - timedelta(days=1)).strftime("%Y-%m-%d")
    just_returned = (not on_leave) and end == yesterday

    # Auto-expire: delete file if leave ended
    if today > end:
        try:
            os.remove(path)
        except OSError:
            pass

    print(json.dumps({
        "on_leave": on_leave,
        "just_returned": just_returned,
        "start": start,
        "end": end,
        "reason": data.get("reason", ""),
    }))


def cmd_set(args):
    """Set a leave period.

    Semantics: end = last full day user is AWAY. Reminders resume on end+1.
    Example: user says "5号回来" → end = 05-04 (last day away),
             reminders resume on 05-05 (return day).
    The agent calling this should interpret user intent correctly.
    """
    today = _today(args.tz_offset, getattr(args, 'mock_date', None))
    current_year = today[:4]
    start = args.start
    end = args.end
    if start < today and start[5:] >= today[5:]:
        start = current_year + start[4:]
    if end < start:
        end = current_year + end[4:]

    data = {
        "start": start,
        "end": end,
        "reason": args.reason or "",
        "created_at": today,
    }
    _save(args.data_dir, data)

    # Clear holiday_asked from engagement.json since user responded
    _clear_holiday_asked(args.data_dir)

    # 同步 frozen 状态到 lifecycle DB。解冻日 = 请假结束次日(end 是最后一个
    # 离开日,end+1 用户回归)。reactor 到期自动把 silence_state 改回 active。
    try:
        resume = (datetime.strptime(end, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    except ValueError:
        resume = end
    _sync_silence(_account_id_from_data_dir(args.data_dir), "frozen", frozen_until=resume)

    print(json.dumps(data, ensure_ascii=False))


def cmd_clear(args):
    """Clear active leave by deleting leave.json."""
    path = _leave_path(args.data_dir)
    existed = os.path.exists(path)
    if existed:
        try:
            os.remove(path)
        except OSError:
            pass
    # 用户提前回来 → 解冻 lifecycle(silence_state 改回 active)。
    _sync_silence(_account_id_from_data_dir(args.data_dir), "active")
    print(json.dumps({"cleared": True, "existed": existed}))


def cmd_info(args):
    """Show current leave status.

    Simplified: file exists with dates = leave is set.
    File absent = no leave.
    """
    path = _leave_path(args.data_dir)
    if not os.path.exists(path):
        print(json.dumps({"has_leave": False}))
        return

    data = _load(args.data_dir)
    start = data.get("start", "")
    end = data.get("end", "")

    if not start or not end:
        print(json.dumps({"has_leave": False}))
        return

    today = _today(args.tz_offset, getattr(args, 'mock_date', None))
    status = "upcoming" if today < start else ("active" if today <= end else "expired")

    # Auto-expire: delete file if leave ended
    if status == "expired":
        try:
            os.remove(path)
        except OSError:
            pass

    try:
        days_remaining = max(0, (datetime.strptime(end, "%Y-%m-%d") - datetime.strptime(today, "%Y-%m-%d")).days)
    except ValueError:
        days_remaining = 0

    print(json.dumps({
        "has_leave": status != "expired",
        "status": status,
        "start": start,
        "end": end,
        "reason": data.get("reason", ""),
        "days_remaining": days_remaining if status != "expired" else 0,
    }, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description="Manage user leave periods")
    sub = parser.add_subparsers(dest="command")

    p_check = sub.add_parser("check")
    p_check.add_argument("--data-dir", required=True)
    p_check.add_argument("--tz-offset", type=int, default=0)
    p_check.add_argument("--mock-date", default=None, help="Mock today's date YYYY-MM-DD")

    p_set = sub.add_parser("set")
    p_set.add_argument("--data-dir", required=True)
    p_set.add_argument("--tz-offset", type=int, default=0)
    p_set.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    p_set.add_argument("--end", required=True, help="End date YYYY-MM-DD")
    p_set.add_argument("--reason", default="", help="Reason for leave")
    p_set.add_argument("--mock-date", default=None, help="Mock today's date YYYY-MM-DD")

    p_clear = sub.add_parser("clear")
    p_clear.add_argument("--data-dir", required=True)
    p_clear.add_argument("--tz-offset", type=int, default=0)
    p_clear.add_argument("--mock-date", default=None, help="Mock today's date YYYY-MM-DD")

    p_info = sub.add_parser("info")
    p_info.add_argument("--data-dir", required=True)
    p_info.add_argument("--tz-offset", type=int, default=0)
    p_info.add_argument("--mock-date", default=None, help="Mock today's date YYYY-MM-DD")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.data_dir = _normalize_path(args.data_dir)

    {"check": cmd_check, "set": cmd_set, "clear": cmd_clear, "info": cmd_info}[args.command](args)


if __name__ == "__main__":
    main()
