#!/usr/bin/env python3
"""
lifecycle-check.py — Deterministic, in-workspace user-lifecycle resolver.

Replaces the never-deployed DB lifecycle/recall API (127.0.0.1:3100). Every
signal is read from the agent workspace; nothing is fetched over HTTP and no new
persisted state field is introduced ("derive, don't store"). The ONE small
exception is the local recall counter (recall.weekly_sent / monthly_sent /
last_recall_at) which the recall-dispatch path bumps via this script's
mark_recall_sent() — that replaces the old POST /v1/lifecycle/recall-sent event.

Importable: callers should prefer `resolve(workspace_dir, tz_offset)` (returns
the dict below) over subprocessing. The CLI wrapper prints that dict as JSON.

Stdout JSON (CLI) / return value of resolve():
  {
    "state": "cold|warm|active|abandoning",
    "activated": true,
    "first_meal_ever": true,
    "days_silent": 0,
    "stage": 1,
    "last_interaction_date": "2026-06-26",   # or null
    "reminders_set_at": "2026-06-25T14:00:00Z" # or null
  }

Signals (all already in-workspace):
  - data/engagement.json → activation.reminders_set_at  (set-once activation stamp)
  - data/engagement.json → recall.{weekly_sent,monthly_sent,last_recall_at}
  - data/meals/*.json   → a food meal = entry with non-empty items/foods
                          (reuse first-meal-check.py's `_meal_has_food`)
  - data/weight.json    → weight check-ins (most recent date)
  - inbound signal      → channel-source.json > lastInboundAt (epoch ms, written
                          by infra Phase-0 on every inbound). This is the SAME
                          file the activation gate uses. If it is absent/unreadable
                          the cold<->warm split degrades to best-effort (see below).

Derivations:
  - activated   = reminders_set_at set OR >= 1 food meal ever
  - first_meal_ever = exactly 1 food meal exists (mirrors first-meal-check.py)
  - days_silent = whole days since the most recent of
                  {last food-meal date, last weight date, last inbound date}.
                  If NONE of those exist, days_silent = 0 (no silence to measure —
                  a never-engaged user is handled by the cold state, not recall).
  - Recall ladder (2/4 thresholds, NEW — replaces the old 3/6):
      Stage 1 ACTIVE  : days_silent < 2
      Stage 2 RECALL  : 2 <= days_silent < 4
      Stage 3 WEEKLY  : days_silent >= 4
      Stage 4 MONTHLY : after 3 weekly recalls sent  (recall.weekly_sent  >= 3)
      Stage 5 SILENT  : after 3 monthly recalls sent (recall.monthly_sent >= 3)
      Reset to Stage 1 on any new meal/weight/inbound (automatic — days_silent
      drops below 2 the moment a fresh interaction lands, and the counters are
      cleared by mark_recall_sent's caller / on reset; see reset_recall()).
  - state:
      abandoning = activated AND stage >= 2
      active     = activated AND stage == 1
      warm       = not activated AND (inbound > 0 OR in First-Meal Mode)
      cold       = not activated AND no inbound AND no food meals

Load-bearing outputs (must be correct): activated, days_silent, stage.
cold vs warm is best-effort: when channel-source.json has no lastInboundAt we
cannot prove the user replied, so a not-activated user with no inbound and no
food meal but who IS in First-Meal Mode (onboarding NOT yet completed but a
handoff overlay exists) is reported `warm`; a truly blank workspace is `cold`.
The downstream nudge composer already splits WARM/COLD by PLAN.md presence, so
this field is informational, not gating.

Usage:
  python3 lifecycle-check.py --workspace-dir <ws> [--tz-offset N]

Exit code 0 always (on a hard error it still emits a safe stage-1 JSON).
"""

from __future__ import annotations

import argparse
import fcntl
import glob
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone, timedelta


# Recall ladder thresholds (NEW 2/4 — see module docstring).
RECALL_ACTIVE_MAX_DAYS = 2     # days_silent < 2  → Stage 1 ACTIVE
RECALL_RECALL_MAX_DAYS = 4     # 2 <= days_silent < 4 → Stage 2 RECALL; >=4 → Stage 3+
WEEKLY_RECALLS_TO_MONTHLY = 3  # weekly recalls sent before Stage 4 MONTHLY
MONTHLY_RECALLS_TO_SILENT = 3  # monthly recalls sent before Stage 5 SILENT


def log(msg):
    """Log to stderr (not visible to user, only for debugging)."""
    print(f"[lifecycle-check] {msg}", file=sys.stderr)


def _normalize_path(p):
    """Lowercase wechat-dm/wecom-dm segment to avoid case-mismatch directories."""
    return re.sub(
        r'(workspace-(?:wechat|wecom)-dm-)([^/]+)',
        lambda m: m.group(1) + m.group(2).lower(), p,
    )


def _meal_has_food(meal):
    """A meal entry counts as a real food log if it has a non-empty items/foods
    list. Mirror of first-meal-check.py / check-stage.py / pre-send-check.py."""
    if not isinstance(meal, dict):
        return False
    items = meal.get("items") or meal.get("foods")
    return bool(items)


def _load_engagement(workspace_dir):
    """Return the engagement.json dict (empty dict if missing/corrupt)."""
    path = os.path.join(workspace_dir, "data", "engagement.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, IOError):
        return {}


def count_food_meals(workspace_dir):
    """Count meal entries with real food across all data/meals/*.json files.
    Mirror of first-meal-check.py count_food_meals."""
    meals_dir = os.path.join(workspace_dir, "data", "meals")
    if not os.path.isdir(meals_dir):
        return 0
    total = 0
    for fp in glob.glob(os.path.join(meals_dir, "*.json")):
        try:
            with open(fp) as f:
                meals = json.load(f)
        except (json.JSONDecodeError, IOError):
            continue
        if isinstance(meals, list):
            total += sum(1 for m in meals if _meal_has_food(m))
        elif isinstance(meals, dict):
            total += sum(1 for m in meals.values() if _meal_has_food(m))
    return total


def get_last_food_meal_date(workspace_dir, tz_offset=0):
    """Most recent date (YYYY-MM-DD) with >=1 food meal, or None.
    Resurrected from check-stage.py get_last_logged_date."""
    meals_dir = os.path.join(workspace_dir, "data", "meals")
    if not os.path.isdir(meals_dir):
        return None
    date_pattern = re.compile(r"(\d{4}-\d{2}-\d{2})\.json$")
    logged_dates = []
    tz = timezone(timedelta(seconds=tz_offset))
    today_str = datetime.now(tz).strftime("%Y-%m-%d")
    for filepath in glob.glob(os.path.join(meals_dir, "*.json")):
        match = date_pattern.match(os.path.basename(filepath))
        if not match:
            continue
        date_str = match.group(1)
        if date_str > today_str:
            continue  # skip future dates
        try:
            with open(filepath) as f:
                meals = json.load(f)
        except (json.JSONDecodeError, IOError):
            continue
        has_logged = False
        if isinstance(meals, list):
            has_logged = any(_meal_has_food(m) for m in meals)
        elif isinstance(meals, dict):
            has_logged = any(_meal_has_food(m) for m in meals.values())
        if has_logged:
            logged_dates.append(date_str)
    return max(logged_dates) if logged_dates else None


def get_last_weight_date(workspace_dir, tz_offset=0):
    """Most recent weight check-in date (YYYY-MM-DD), or None.

    weight.json is observed in several shapes across the codebase (see
    pre-send-check._weight_logged_on): a dict keyed by ISO-8601 datetime, a list
    of records, or a dict with a `records` list. Handle all three; ignore future
    dates."""
    path = os.path.join(workspace_dir, "data", "weight.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError):
        return None

    tz = timezone(timedelta(seconds=tz_offset))
    today_str = datetime.now(tz).strftime("%Y-%m-%d")
    dates = []

    def _consider(date_str):
        if isinstance(date_str, str) and len(date_str) >= 10:
            d = date_str[:10]
            if re.match(r"^\d{4}-\d{2}-\d{2}$", d) and d <= today_str:
                dates.append(d)

    if isinstance(data, dict):
        # dict keyed by ISO datetime
        for key in data:
            _consider(key)
        # dict with a records list
        records = data.get("records")
        if isinstance(records, list):
            for rec in records:
                if isinstance(rec, dict):
                    _consider(rec.get("date", ""))
    elif isinstance(data, list):
        for rec in data:
            if isinstance(rec, dict):
                _consider(rec.get("date", ""))

    return max(dates) if dates else None


def get_last_inbound_date(workspace_dir, tz_offset=0):
    """Most recent inbound date (YYYY-MM-DD) from channel-source.json >
    lastInboundAt (epoch ms, written by infra Phase-0), or None.

    This is the single in-workspace inbound signal (same source the activation
    gate uses). When the field is absent the cold<->warm split is best-effort —
    days_silent then falls back to meal/weight only, which is the conservative
    choice (we never invent silence).
    """
    path = os.path.join(workspace_dir, "channel-source.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError):
        return None
    if not isinstance(data, dict):
        return None
    raw = data.get("lastInboundAt")
    if raw is None:
        return None
    # epoch ms (int/float) or numeric string
    try:
        ms = float(raw)
    except (TypeError, ValueError):
        return None
    tz = timezone(timedelta(seconds=tz_offset))
    try:
        return datetime.fromtimestamp(ms / 1000.0, tz).strftime("%Y-%m-%d")
    except (OverflowError, OSError, ValueError):
        return None


def _has_inbound(workspace_dir):
    """True iff channel-source.json has any lastInboundAt (user has replied).
    Best-effort: a missing/unreadable file returns False (cannot prove a reply)."""
    path = os.path.join(workspace_dir, "channel-source.json")
    if not os.path.exists(path):
        return False
    try:
        with open(path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError):
        return False
    return isinstance(data, dict) and data.get("lastInboundAt") is not None


def _onboarding_completed(workspace_dir):
    """True iff health-profile.md has a REAL Onboarding Completed date (not '—').
    Mirrors pre-send-check._onboarding_completed."""
    path = os.path.join(workspace_dir, "health-profile.md")
    if not os.path.exists(path):
        return False
    try:
        with open(path) as f:
            content = f.read()
    except IOError:
        return False
    m = re.search(
        r"^\s*-\s*\*\*Onboarding\s+Completed:\*\*\s*(.+?)\s*$",
        content, re.IGNORECASE | re.MULTILINE,
    )
    if not m:
        return False
    val = m.group(1).strip()
    return bool(val) and val not in ("—", "-", "none", "None")


def _in_first_meal_mode(workspace_dir):
    """Best-effort 'First-Meal Mode' detector for the cold<->warm split.

    A handoff/warm-start user is in First-Meal Mode when they have a handoff
    overlay (handoff.json or PROFILE.md/PLAN.md) but onboarding is NOT completed.
    Used only when there is no inbound signal — informational, never gating.
    """
    if _onboarding_completed(workspace_dir):
        return False
    for fname in ("handoff.json", "PROFILE.md", "PLAN.md"):
        if os.path.exists(os.path.join(workspace_dir, fname)):
            return True
    return False


def _recall_block(engagement):
    """Return the recall counter sub-dict (weekly_sent/monthly_sent/last_recall_at)
    with safe int defaults."""
    recall = engagement.get("recall")
    if not isinstance(recall, dict):
        recall = {}

    def _int(v):
        if isinstance(v, bool) or not isinstance(v, int):
            return 0
        return v

    return {
        "weekly_sent": _int(recall.get("weekly_sent", 0)),
        "monthly_sent": _int(recall.get("monthly_sent", 0)),
        "last_recall_at": recall.get("last_recall_at"),
    }


def _compute_stage(days_silent, weekly_sent, monthly_sent):
    """Map days_silent + local recall counters → stage 1..5 (2/4 ladder)."""
    if days_silent < RECALL_ACTIVE_MAX_DAYS:
        return 1
    if days_silent < RECALL_RECALL_MAX_DAYS:
        return 2
    # days_silent >= 4 → weekly/monthly/silent by how many recalls already sent
    if weekly_sent < WEEKLY_RECALLS_TO_MONTHLY:
        return 3
    if monthly_sent < MONTHLY_RECALLS_TO_SILENT:
        return 4
    return 5


def resolve(workspace_dir, tz_offset=0):
    """The deterministic resolver. Returns the lifecycle dict (see module
    docstring). Importable — callers prefer this over subprocessing."""
    workspace_dir = _normalize_path(workspace_dir)
    engagement = _load_engagement(workspace_dir)

    # --- activation signal ---
    activation = engagement.get("activation")
    if not isinstance(activation, dict):
        activation = {}
    reminders_set_at = activation.get("reminders_set_at")
    if not (isinstance(reminders_set_at, str) and reminders_set_at.strip()):
        reminders_set_at = None

    food_meals = count_food_meals(workspace_dir)
    activated = bool(reminders_set_at) or food_meals >= 1
    first_meal_ever = food_meals == 1

    # --- last-interaction dates (most recent of meal / weight / inbound) ---
    last_meal = get_last_food_meal_date(workspace_dir, tz_offset)
    last_weight = get_last_weight_date(workspace_dir, tz_offset)
    last_inbound = get_last_inbound_date(workspace_dir, tz_offset)
    interaction_dates = [d for d in (last_meal, last_weight, last_inbound) if d]
    last_interaction_date = max(interaction_dates) if interaction_dates else None

    # --- days_silent ---
    if last_interaction_date is None:
        # No measurable interaction → no silence to measure. A never-engaged user
        # is described by the cold/warm state, not by the recall ladder.
        days_silent = 0
    else:
        tz = timezone(timedelta(seconds=tz_offset))
        today = datetime.now(tz).date()
        try:
            last_date = datetime.strptime(last_interaction_date, "%Y-%m-%d").date()
            days_silent = max(0, (today - last_date).days)
        except ValueError:
            days_silent = 0

    # --- recall counters (local, replaces the 3100 event store) ---
    recall = _recall_block(engagement)

    # --- stage ---
    stage = _compute_stage(days_silent, recall["weekly_sent"], recall["monthly_sent"])

    # --- state ---
    if activated:
        state = "abandoning" if stage >= 2 else "active"
    else:
        # not activated → cold vs warm (best-effort)
        if _has_inbound(workspace_dir) or food_meals >= 1 or _in_first_meal_mode(workspace_dir):
            state = "warm"
        else:
            state = "cold"

    return {
        "state": state,
        "activated": activated,
        "first_meal_ever": first_meal_ever,
        "days_silent": days_silent,
        "stage": stage,
        "last_interaction_date": last_interaction_date,
        "reminders_set_at": reminders_set_at,
    }


def mark_recall_sent(workspace_dir, tier):
    """Local replacement for POST /v1/lifecycle/recall-sent. Atomically bump the
    weekly/monthly recall counter and stamp last_recall_at in engagement.json,
    under an exclusive flock (mirrors activation-mark-reminders-set.py).

    tier: "weekly" → recall.weekly_sent += 1
          "monthly" → recall.monthly_sent += 1
    Returns the updated recall block. Raises on hard write failure.
    """
    workspace_dir = _normalize_path(workspace_dir)
    if tier not in ("weekly", "monthly"):
        raise ValueError(f"tier must be 'weekly' or 'monthly', got {tier!r}")

    path = os.path.join(workspace_dir, "data", "engagement.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)

    lockfile = path + ".lock"
    lock_fd = None
    try:
        lock_fd = open(lockfile, "w")
        fcntl.flock(lock_fd, fcntl.LOCK_EX)

        data = {}
        if os.path.exists(path):
            try:
                with open(path) as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    data = {}
            except (json.JSONDecodeError, IOError):
                data = {}

        recall = data.get("recall")
        if not isinstance(recall, dict):
            recall = {}

        def _int(v):
            if isinstance(v, bool) or not isinstance(v, int):
                return 0
            return v

        key = "weekly_sent" if tier == "weekly" else "monthly_sent"
        recall[key] = _int(recall.get(key, 0)) + 1
        recall["last_recall_at"] = datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        # keep the sibling counter present (default 0) for a stable schema
        recall.setdefault("weekly_sent", 0)
        recall.setdefault("monthly_sent", 0)
        data["recall"] = recall

        tmp_fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        return dict(recall)
    finally:
        if lock_fd:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                lock_fd.close()
            except Exception:
                pass


def last_proactive_send_date(workspace_dir):
    """Return engagement.json proactive.last_send_date (local 'YYYY-MM-DD'), or
    None. Read-only; used by pre-send-check's global daily proactive cap (at most
    one proactive message per local day across ALL meal_types). Never raises."""
    workspace_dir = _normalize_path(workspace_dir)
    data = _load_engagement(workspace_dir)
    proactive = data.get("proactive")
    if not isinstance(proactive, dict):
        return None
    val = proactive.get("last_send_date")
    return val if isinstance(val, str) and val.strip() else None


def mark_proactive_sent(workspace_dir, local_date, meal_type):
    """Claim the global daily proactive slot. Atomically stamp
    proactive.{last_send_date,last_send_type,last_send_at} in engagement.json
    under an exclusive flock (mirrors mark_recall_sent). The daily cap is enforced
    by pre-send-check: once last_send_date == today, every further proactive
    meal_type that day returns NO_REPLY. Claimed at gate-decision time (the
    conservative anti-burst choice — errs toward fewer messages, like the recall
    claim). Raises on hard write failure; caller treats failure as best-effort.

    local_date: 'YYYY-MM-DD' in the user's local tz (the cap's day boundary).
    meal_type:  the slot that won the day (debug/audit only).
    """
    workspace_dir = _normalize_path(workspace_dir)
    path = os.path.join(workspace_dir, "data", "engagement.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)

    lockfile = path + ".lock"
    lock_fd = None
    try:
        lock_fd = open(lockfile, "w")
        fcntl.flock(lock_fd, fcntl.LOCK_EX)

        data = {}
        if os.path.exists(path):
            try:
                with open(path) as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    data = {}
            except (json.JSONDecodeError, IOError):
                data = {}

        proactive = data.get("proactive")
        if not isinstance(proactive, dict):
            proactive = {}
        proactive["last_send_date"] = local_date
        proactive["last_send_type"] = meal_type
        proactive["last_send_at"] = datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        data["proactive"] = proactive

        tmp_fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        return dict(proactive)
    finally:
        if lock_fd:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                lock_fd.close()
            except Exception:
                pass


def reset_recall(workspace_dir):
    """Clear the local recall counters when a user returns (any fresh
    interaction). Best-effort: silently no-ops if engagement.json can't be read.

    Note: stage already auto-resets to 1 via days_silent the moment a fresh
    interaction lands; this clears the weekly/monthly counters so a future
    silent spell starts the ladder fresh. Callers may invoke it on inbound, but
    it is NOT required for stage correctness (the resolver re-reads counters and
    days_silent on every call)."""
    workspace_dir = _normalize_path(workspace_dir)
    path = os.path.join(workspace_dir, "data", "engagement.json")
    if not os.path.exists(path):
        return
    lockfile = path + ".lock"
    lock_fd = None
    try:
        lock_fd = open(lockfile, "w")
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        try:
            with open(path) as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return
        except (json.JSONDecodeError, IOError):
            return
        if isinstance(data.get("recall"), dict):
            data["recall"]["weekly_sent"] = 0
            data["recall"]["monthly_sent"] = 0
            tmp_fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
            try:
                with os.fdopen(tmp_fd, "w") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                os.replace(tmp_path, path)
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
    finally:
        if lock_fd:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                lock_fd.close()
            except Exception:
                pass


def main():
    parser = argparse.ArgumentParser(
        description="Deterministic in-workspace user-lifecycle resolver"
    )
    parser.add_argument("--workspace-dir", required=True, help="Agent workspace root")
    parser.add_argument("--tz-offset", type=int, default=0,
                        help="Timezone offset in seconds from UTC (default 0)")
    # Optional CLI for the recall counter (mirrors the old POST /recall-sent).
    parser.add_argument("--mark-recall", choices=["weekly", "monthly"], default=None,
                        help="Bump the local recall counter for this tier and exit")
    parser.add_argument("--reset-recall", action="store_true",
                        help="Clear local weekly/monthly recall counters and exit")
    # Optional CLI for the global daily proactive cap marker (subprocess fallback
    # for pre-send-check when the in-process import isn't available).
    parser.add_argument("--last-proactive-date", action="store_true",
                        help="Print proactive.last_send_date (or 'null') and exit")
    parser.add_argument("--mark-proactive", default=None, metavar="YYYY-MM-DD",
                        help="Claim the daily proactive slot for this local date and exit")
    parser.add_argument("--mark-proactive-type", default="unknown",
                        help="meal_type that won the daily slot (audit only)")
    args = parser.parse_args()

    if args.last_proactive_date:
        val = last_proactive_send_date(args.workspace_dir)
        print(val if val else "null")
        return 0

    if args.mark_proactive:
        try:
            mark_proactive_sent(args.workspace_dir, args.mark_proactive, args.mark_proactive_type)
            print(json.dumps({"status": "ok"}, ensure_ascii=False))
            return 0
        except Exception as e:  # noqa: BLE001
            log(f"mark-proactive failed: {e}")
            print(json.dumps({"status": "error", "error": str(e)}, ensure_ascii=False))
            return 1

    if args.mark_recall:
        try:
            recall = mark_recall_sent(args.workspace_dir, args.mark_recall)
            print(json.dumps({"status": "ok", "recall": recall}, ensure_ascii=False))
            return 0
        except Exception as e:  # noqa: BLE001
            log(f"mark-recall failed: {e}")
            print(json.dumps({"status": "error", "error": str(e)}, ensure_ascii=False))
            return 1

    if args.reset_recall:
        reset_recall(args.workspace_dir)
        print(json.dumps({"status": "ok"}, ensure_ascii=False))
        return 0

    try:
        result = resolve(args.workspace_dir, args.tz_offset)
    except Exception as e:  # noqa: BLE001 — never crash a reminder gate
        log(f"resolve failed, emitting safe stage-1 default: {e}")
        result = {
            "state": "active", "activated": False, "first_meal_ever": False,
            "days_silent": 0, "stage": 1,
            "last_interaction_date": None, "reminders_set_at": None,
        }
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
