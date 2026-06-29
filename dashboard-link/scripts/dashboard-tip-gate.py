#!/usr/bin/env python3
"""
dashboard-tip-gate.py — Single shared gate for the proactive "data center" tip.

The coach surfaces a ONE-LINE tip pointing the user at their personal web
dashboard (https://user.nanorhino.com/me/{agentId}) at three natural touch
points (meal-log milestone, weekly report, post-activation). This script is the
ONE place that decides whether the tip may be shown right now, and the ONE place
that records that it was shown — so the tip is never spammed across the three
surfaces.

Design (anti-over-messaging):
  - State lives in data/engagement.json under a single `dashboard_tip` sub-object,
    owned by the dashboard-link skill. All OTHER keys in engagement.json
    (activation.*, recall.*, reminder_config, ...) are preserved untouched on
    every write (read-modify-write, atomic via os.replace).
  - Show policy: AT MOST `--max-shows` total (default 2) across all touch points,
    AND at most one show per touch point (a given surface fires once, ever), AND
    never twice on the same local day.
  - Hard stop once the user has demonstrably discovered the dashboard:
    `dashboard_tip.opened == true` (set when the user actually asks for / opens
    the dashboard — wire from dashboard-link's own send path) suppresses the tip
    forever. A user who already knows about the page stops seeing the tip.
  - Respects pause / leave: if data/leave.json is an active leave, the gate
    returns SUPPRESS (no tip). Opt-out (`dashboard_tip.opted_out == true`) also
    suppresses forever. Pause/opt-out state is read here so each touch-point
    skill does not re-implement it.

`dashboard_tip` schema (all fields optional / backward-compatible; absent == defaults):
  {
    "shows": 1,                              # total times the tip has been shown
    "last_shown_date": "2026-06-29",         # local date (tz-adjusted) of last show
    "shown_surfaces": ["activation"],        # which touch points have fired
    "opened": false,                         # user opened/asked for the dashboard
    "opted_out": false                       # user told us to stop
  }

Commands:
  check  --workspace-dir WS --surface {milestone,weekly_report,activation}
         [--tz-offset SEC] [--max-shows N] [--mock-date YYYY-MM-DD]
      -> stdout: "SHOW surface=<s>" or "SUPPRESS reason=<r>"
      Does NOT mutate state. The caller composes + sends the tip, THEN calls
      `mark` (mirrors the tips-check / tips-mark-sent split so a failed send
      never burns a slot).

  mark   --workspace-dir WS --surface {milestone,weekly_report,activation}
         [--tz-offset SEC] [--mock-date YYYY-MM-DD]
      -> records one show (increments shows, appends surface, stamps date).
      Idempotent per (surface): re-marking the same surface won't double-count.

  opened --workspace-dir WS        # mark dashboard discovered -> tip suppressed forever
  optout --workspace-dir WS        # user asked to stop the tip -> suppressed forever

Exit code 0 always (best-effort: on a hard error `check` prints SUPPRESS so we
fail safe to NOT messaging).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

SURFACES = ("milestone", "weekly_report", "activation")
DEFAULT_MAX_SHOWS = 2


def log(msg):
    print(f"[dashboard-tip-gate] {msg}", file=sys.stderr)


def _engagement_path(workspace_dir):
    return os.path.join(workspace_dir, "data", "engagement.json")


def _load_engagement(workspace_dir):
    path = _engagement_path(workspace_dir)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, IOError, OSError):
            pass
    return {}


def _save_engagement(workspace_dir, data):
    """Atomic write that preserves the whole engagement.json object."""
    path = _engagement_path(workspace_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".engagement-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _get_tip_state(engagement):
    state = engagement.get("dashboard_tip")
    if not isinstance(state, dict):
        state = {}
    return state


def _today(tz_offset, mock_date=None):
    if mock_date:
        return datetime.strptime(mock_date, "%Y-%m-%d").date()
    tz = timezone(timedelta(seconds=tz_offset))
    return datetime.now(tz).date()


def _leave_active(workspace_dir, today):
    """Active leave per data/leave.json (same source pre-send-check reads)."""
    leave_path = os.path.join(workspace_dir, "data", "leave.json")
    if not os.path.exists(leave_path):
        return False
    try:
        with open(leave_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError, OSError):
        return False
    if not isinstance(data, dict):
        return False
    # Prefer explicit start/end window (matches leave-manager.py); fall back to a
    # bare `active` flag if that's all that's present.
    start = data.get("start")
    end = data.get("end")
    if start and end:
        try:
            s = datetime.strptime(start, "%Y-%m-%d").date()
            e = datetime.strptime(end, "%Y-%m-%d").date()
            return s <= today <= e
        except ValueError:
            pass
    return bool(data.get("active", False))


def cmd_check(args):
    today = _today(args.tz_offset, args.mock_date)
    engagement = _load_engagement(args.workspace_dir)
    state = _get_tip_state(engagement)

    if state.get("opted_out", False):
        print("SUPPRESS reason=opted_out")
        return
    if state.get("opened", False):
        print("SUPPRESS reason=already_discovered")
        return
    if _leave_active(args.workspace_dir, today):
        print("SUPPRESS reason=on_leave")
        return

    shown_surfaces = state.get("shown_surfaces") or []
    if args.surface in shown_surfaces:
        print(f"SUPPRESS reason=surface_already_shown surface={args.surface}")
        return

    shows = int(state.get("shows", 0) or 0)
    if shows >= args.max_shows:
        print(f"SUPPRESS reason=max_shows_reached shows={shows}")
        return

    if state.get("last_shown_date") == str(today):
        print("SUPPRESS reason=already_shown_today")
        return

    print(f"SHOW surface={args.surface}")


def cmd_mark(args):
    today = _today(args.tz_offset, args.mock_date)
    engagement = _load_engagement(args.workspace_dir)
    state = _get_tip_state(engagement)

    shown_surfaces = list(state.get("shown_surfaces") or [])
    if args.surface in shown_surfaces:
        # Idempotent: this surface already recorded — do not double-count.
        log(f"surface {args.surface} already marked; no-op")
        print(f"OK shows={int(state.get('shows', 0) or 0)} surface={args.surface} (noop)")
        return

    shown_surfaces.append(args.surface)
    state["shows"] = int(state.get("shows", 0) or 0) + 1
    state["shown_surfaces"] = shown_surfaces
    state["last_shown_date"] = str(today)
    engagement["dashboard_tip"] = state
    _save_engagement(args.workspace_dir, engagement)
    print(f"OK shows={state['shows']} surface={args.surface}")


def cmd_flag(args, key):
    engagement = _load_engagement(args.workspace_dir)
    state = _get_tip_state(engagement)
    state[key] = True
    engagement["dashboard_tip"] = state
    _save_engagement(args.workspace_dir, engagement)
    print(f"OK {key}=true")


def main():
    parser = argparse.ArgumentParser(description="Shared gate for the data-center dashboard tip.")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p, surface=False):
        p.add_argument("--workspace-dir", required=True)
        p.add_argument("--tz-offset", type=int, default=0)
        p.add_argument("--mock-date", default=None)
        if surface:
            p.add_argument("--surface", required=True, choices=SURFACES)

    p_check = sub.add_parser("check", help="May the tip be shown now? (no mutation)")
    add_common(p_check, surface=True)
    p_check.add_argument("--max-shows", type=int, default=DEFAULT_MAX_SHOWS)

    p_mark = sub.add_parser("mark", help="Record one shown tip (after confirmed send).")
    add_common(p_mark, surface=True)

    p_opened = sub.add_parser("opened", help="User discovered the dashboard -> suppress tip forever.")
    p_opened.add_argument("--workspace-dir", required=True)

    p_optout = sub.add_parser("optout", help="User asked to stop the tip -> suppress forever.")
    p_optout.add_argument("--workspace-dir", required=True)

    args = parser.parse_args()

    try:
        if args.command == "check":
            cmd_check(args)
        elif args.command == "mark":
            cmd_mark(args)
        elif args.command == "opened":
            cmd_flag(args, "opened")
        elif args.command == "optout":
            cmd_flag(args, "opted_out")
    except Exception as e:  # fail safe: never message on error
        log(f"error: {e}")
        if args.command == "check":
            print("SUPPRESS reason=error")
        else:
            print("ERROR")


if __name__ == "__main__":
    main()
