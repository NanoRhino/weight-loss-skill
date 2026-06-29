#!/usr/bin/env python3
"""
pre-send-check.py — Deterministic pre-send checks for meal/weight reminders.

Returns SEND or NO_REPLY (with reason on stderr for logging).
The model should NOT be invoked if this returns NO_REPLY.

Usage:
  python3 pre-send-check.py --workspace-dir <path> --meal-type <type> --tz-offset <seconds>

  --workspace-dir   Agent workspace root (contains health-profile.md, data/, etc.)
  --meal-type       One of: breakfast, lunch, dinner, meal_1, meal_2, weight,
                    weight_morning_followup
  --tz-offset       Timezone offset in seconds from UTC (e.g. 28800 for UTC+8)

Exit code 0 always. Output is exactly "SEND" or "NO_REPLY" on stdout.
Reason is printed to stderr for debugging.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta

# Lifecycle is resolved locally + deterministically by notification-manager's
# lifecycle-check.py (the 127.0.0.1:3100 DB API was never deployed — every caller
# failed open to Stage 1, so recall/decay was a prod no-op). Import the resolver
# from the sibling skill's scripts dir; subprocess fallback keeps the gate working
# even if the import path can't be resolved at runtime.
_HERE = os.path.dirname(os.path.abspath(__file__))
_LIFECYCLE_DIR = os.path.normpath(
    os.path.join(_HERE, "..", "..", "notification-manager", "scripts")
)
if _LIFECYCLE_DIR not in sys.path:
    sys.path.insert(0, _LIFECYCLE_DIR)
try:
    import importlib
    _lifecycle = importlib.import_module("lifecycle-check")
except Exception:  # noqa: BLE001 — fall back to subprocess at call sites
    _lifecycle = None


def _normalize_path(p):
    """Lowercase wechat-dm/wecom-dm segment to avoid case-mismatch directories."""
    import re as _re
    return _re.sub(r'(workspace-(?:wechat|wecom)-dm-)([^/]+)', lambda m: m.group(1) + m.group(2).lower(), p)


def log(msg):
    """Log to stderr (not visible to user, only for debugging)."""
    print(f"[pre-send-check] {msg}", file=sys.stderr)


def _account_id(workspace_dir):
    """workspace-wechat-dm-<acc> → <acc>."""
    base = os.path.basename(os.path.normpath(workspace_dir)).replace("workspace-", "")
    for prefix in ("wechat-dm-", "wecom-dm-"):
        if base.startswith(prefix):
            return base[len(prefix):]
    return base


def lifecycle_state(workspace_dir, tz_offset=0):
    """Local lifecycle resolution (replaces GET /v1/lifecycle/state). Returns the
    resolver dict {state, activated, days_silent, stage, ...} or None on hard
    failure. Prefers the in-process import; falls back to subprocessing
    lifecycle-check.py if the import wasn't available."""
    if _lifecycle is not None:
        try:
            return _lifecycle.resolve(workspace_dir, tz_offset)
        except Exception as e:  # noqa: BLE001
            log(f"lifecycle resolve() failed: {e}")
            return None
    # Subprocess fallback.
    import subprocess
    script = os.path.join(_LIFECYCLE_DIR, "lifecycle-check.py")
    try:
        out = subprocess.run(
            ["python3", script, "--workspace-dir", workspace_dir,
             "--tz-offset", str(tz_offset)],
            capture_output=True, timeout=15, text=True,
        )
        if out.returncode == 0 and out.stdout.strip():
            return json.loads(out.stdout.strip())
    except (OSError, ValueError, json.JSONDecodeError, subprocess.SubprocessError) as e:
        log(f"lifecycle subprocess failed: {e}")
    return None


def lifecycle_mark_recall(workspace_dir, tier):
    """Local replacement for POST /v1/lifecycle/recall-sent: bump the recall
    counter (recall.weekly_sent / monthly_sent + last_recall_at) in
    engagement.json so recall cadence/dedup is deterministic. Best-effort — a
    failure here must never block a send decision."""
    if _lifecycle is not None:
        try:
            _lifecycle.mark_recall_sent(workspace_dir, tier)
            return True
        except Exception as e:  # noqa: BLE001
            log(f"mark recall-sent failed for {workspace_dir}: {e}")
            return False
    import subprocess
    script = os.path.join(_LIFECYCLE_DIR, "lifecycle-check.py")
    try:
        subprocess.run(
            ["python3", script, "--workspace-dir", workspace_dir,
             "--mark-recall", tier],
            capture_output=True, timeout=10,
        )
        return True
    except (OSError, subprocess.SubprocessError) as e:
        log(f"mark recall-sent subprocess failed: {e}")
        return False


def get_local_date(tz_offset):
    """Get current local date string YYYY-MM-DD."""
    tz = timezone(timedelta(seconds=tz_offset))
    return datetime.now(tz).strftime("%Y-%m-%d")


def get_local_weekday(tz_offset):
    """Get current local weekday (0=Monday, 6=Sunday)."""
    tz = timezone(timedelta(seconds=tz_offset))
    return datetime.now(tz).weekday()


def check_health_profile(workspace_dir):
    """Check 1: health-profile.md exists (user is onboarded)."""
    path = os.path.join(workspace_dir, "health-profile.md")
    if not os.path.exists(path):
        return False, "health-profile.md not found — user not onboarded"
    return True, None


def _last_recall_at(workspace_dir):
    """Read recall.last_recall_at (ISO-8601 UTC) from engagement.json, or None.
    Used for local recall cadence + same-day dedup (replaces the 3100 /due API)."""
    eng_path = os.path.join(workspace_dir, "data", "engagement.json")
    if not os.path.exists(eng_path):
        return None
    try:
        with open(eng_path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError):
        return None
    if not isinstance(data, dict):
        return None
    recall = data.get("recall")
    if not isinstance(recall, dict):
        return None
    return _parse_iso(recall.get("last_recall_at"))


def check_engagement_stage(workspace_dir, meal_type, tz_offset, out=None):
    """Check 2: engagement stage gating.

    Stage 1 (ACTIVE):  SEND — normal reminder
    Stage 2 (RECALL):  SEND once per day (lunch recall only, suppress rest)
                        Weight reminders suppressed entirely.
    Stage 3 (WEEKLY):  SEND once per week (>= 7 days since last_recall_at)
                        Weight reminders suppressed entirely.
    Stage 4 (MONTHLY): SEND once per month (>= 30 days since last_recall_at)
                        Weight reminders suppressed entirely.
    Stage 5 (SILENT):  NO_REPLY — suppress everything

    Stage + days_silent come from the LOCAL deterministic resolver
    (notification-manager/lifecycle-check.py) — the 127.0.0.1:3100 DB API was
    never deployed, so this is now a real (no longer no-op) gate. Recall ladder is
    the 2/4 model: days_silent <2 → S1, 2-3 → S2, >=4 → S3+ (weekly→monthly→silent
    by local recall counters). Recall cadence + same-day dedup are computed locally
    from recall.last_recall_at; on a SEND-recall we claim the slot by bumping the
    local counter (recall.weekly_sent / monthly_sent) immediately.
    """
    state = lifecycle_state(workspace_dir, tz_offset)
    if state is None:
        # fail-open: resolver unavailable → behave as Stage 1 (don't drop sends).
        log(f"lifecycle resolve unavailable for {workspace_dir}, fail-open as stage 1")
        return True, None

    stage = state.get("stage", 1)
    days_silent_val = state.get("days_silent", 0)
    # Record the pre-claim stage/days_silent for the output line (claiming a recall
    # may advance stage, but this recall's identity is the pre-claim stage).
    if out is not None:
        out["stage"] = stage
        out["days_silent"] = days_silent_val

    if stage >= 5:
        return False, f"stage={stage} — user is in silent mode"

    # first_meal_nudge / activation: the authoritative Silent gate (stage >= 5,
    # above) still applies — never nudge a Silent user. Past that, the recall/
    # lunch-only logic below is for the engaged recall stages and is irrelevant to
    # these never-engaged cohorts, so bypass it. The nudge-specific gating
    # (onboarding/already-logged/lastInboundAt/cap) lives in
    # check_first_meal_nudge / check_activation_nudge, which run after this.
    if meal_type in ("first_meal_nudge", "activation"):
        return True, None

    # Stage 2-4: suppress weight reminders entirely
    if stage in (2, 3, 4):
        if meal_type in ("weight", "weight_morning_followup"):
            return False, f"stage={stage} — weight reminders suppressed during recall"

    # Stage 2-4: suppress custom reminders, daily summaries; Stage 3-4: also weekly reports
    if stage in (2, 3, 4):
        if meal_type in ("custom", "daily_summary"):
            return False, f"stage={stage} — {meal_type} suppressed during recall"
        if stage >= 3 and meal_type == "weekly_report":
            return False, f"stage={stage} — weekly_report suppressed at stage 3+"

    # Stage 2: only lunch slot recall. Exception: weekly_report allowed at S2
    # (user still has recent data). (2/4 ladder: S2 spans days_silent 2-3.)
    if stage == 2 and meal_type not in ("weekly_report",):
        if meal_type not in ("lunch", "meal_2"):
            return False, f"stage=2 — only lunch recall allowed, got {meal_type}"

    # Stage 3-4: only lunch slot for recall messages
    if stage in (3, 4):
        if meal_type not in ("lunch", "meal_2"):
            return False, f"stage={stage} — only lunch recall allowed, got {meal_type}"

    # Recall cadence + same-day dedup, computed LOCALLY from recall.last_recall_at.
    # weekly_report at S2 is NOT a recall message — skip the cadence/claim gate.
    #   S2: at most one recall per day (same-day dedup).
    #   S3: at most one per 7 days.   S4: at most one per 30 days.
    if stage in (2, 3, 4) and meal_type not in ("weekly_report",):
        last_recall = _last_recall_at(workspace_dir)
        now = datetime.now(timezone.utc)
        if last_recall is not None:
            elapsed_days = (now - last_recall).total_seconds() / 86400.0
            min_gap_days = {2: 1, 3: 7, 4: 30}[stage]
            if elapsed_days < min_gap_days:
                return False, (f"stage={stage} — not due for recall "
                               f"(last recall {elapsed_days:.1f}d ago < {min_gap_days}d)")
        # Due → claim the slot immediately by bumping the local recall counter
        # (replaces POST /recall-sent). weekly for S2/S3, monthly for S4.
        tier = "monthly" if stage == 4 else "weekly"
        lifecycle_mark_recall(workspace_dir, tier)
        if stage == 2:
            return True, f"recall stage=2 days_silent={days_silent_val}"
        return True, None

    return True, None


def check_meal_logged(workspace_dir, meal_type, tz_offset):
    """Check 3: this meal is not already logged today."""
    local_date = get_local_date(tz_offset)
    meals_file = os.path.join(workspace_dir, "data", "meals", f"{local_date}.json")

    if not os.path.exists(meals_file):
        return True, None  # no meals logged today at all

    try:
        with open(meals_file) as f:
            meals = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        log(f"Warning: could not read {meals_file}: {e}")
        return True, None  # fail-open

    for meal in meals:
        mt = meal.get("meal_type", "") or meal.get("name", "")
        if mt == meal_type:
            return False, f"{meal_type} already logged today ({local_date})"

    return True, None


def check_weight_logged(workspace_dir, tz_offset):
    """Check for weight: already weighed today?"""
    local_date = get_local_date(tz_offset)
    return _weight_logged_on(workspace_dir, local_date)


def check_weight_logged_yesterday_or_today(workspace_dir, tz_offset):
    """Check for weight morning followup: suppress if user weighed yesterday or today."""
    tz = timezone(timedelta(seconds=tz_offset))
    now = datetime.now(tz)
    today = now.strftime("%Y-%m-%d")
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")

    logged_today, _ = _weight_logged_on(workspace_dir, today)
    logged_yesterday, _ = _weight_logged_on(workspace_dir, yesterday)

    if not logged_today:
        return False, f"weight already logged today ({today}) — no morning followup needed"
    if not logged_yesterday:
        return False, f"weight logged yesterday ({yesterday}) — no morning followup needed"
    return True, None


def _weight_logged_on(workspace_dir, date_str):
    """Helper: check if weight was logged on a specific date. Returns (not_logged, reason)."""
    weight_file = os.path.join(workspace_dir, "data", "weight.json")

    if not os.path.exists(weight_file):
        return True, None

    try:
        with open(weight_file) as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        log(f"Warning: could not read weight.json: {e}")
        return True, None

    # weight.json keys are ISO-8601 datetimes; check date prefix
    if isinstance(data, dict):
        for key in data:
            if key[:10] == date_str:
                return False, f"weight logged on {date_str}"

    # Also handle list format
    if isinstance(data, list):
        for record in data:
            record_date = record.get("date", "")
            if record_date == date_str:
                return False, f"weight logged on {date_str}"

    records = data.get("records", []) if isinstance(data, dict) else []
    for record in records:
        record_date = record.get("date", "")
        if record_date == date_str:
            return False, f"weight logged on {date_str}"

    return True, None


FIRST_MEAL_NUDGE_CAP = 2

# Cold-Start v3 (Part-2): the first-meal nudge is driven by the SAME recurring
# generic sweep as activation (the sweep payload runs this gate after the
# activation gate returns NO_REPLY — the two cohorts are mutually exclusive).
# Cadence: touch1 fires as soon as the user is eligible (onboarded, no meal);
# touch2 fires >= FIRST_MEAL_TOUCH2_GAP_SECONDS (24h) after touch1. Then the cap
# is the terminal anti-nag guarantee. Angles pick the copy the composer renders.
FIRST_MEAL_TOUCH2_GAP_SECONDS = 24 * 3600
FIRST_MEAL_ANGLES = {1: "day1", 2: "followup"}


def _meal_has_food(meal):
    """Mirror of check-stage.py's _meal_has_food: a meal entry counts as a
    real food log if it has a non-empty items/foods list."""
    if not isinstance(meal, dict):
        return False
    items = meal.get("items") or meal.get("foods")
    return bool(items)


def _any_meal_ever_logged(workspace_dir):
    """Return True if any meal entry containing food data exists in
    data/meals/*.json (any date). Used by the first-meal nudge: the moment
    the user logs ANY meal, the nudge self-cancels."""
    import glob as _glob
    meals_dir = os.path.join(workspace_dir, "data", "meals")
    if not os.path.isdir(meals_dir):
        return False
    for fp in _glob.glob(os.path.join(meals_dir, "*.json")):
        try:
            with open(fp) as f:
                meals = json.load(f)
        except (json.JSONDecodeError, IOError):
            continue
        if isinstance(meals, list):
            if any(_meal_has_food(m) for m in meals):
                return True
        elif isinstance(meals, dict):
            if any(_meal_has_food(m) for m in meals.values()):
                return True
    return False


def check_first_meal_nudge(workspace_dir, tz_offset, out=None):
    """Gate for the first-meal nudge (meal_type=first_meal_nudge) — the Part-2
    "onboarded but never logged a meal" cohort.

    Cold-Start v3 (Part-2): driven by the SAME recurring generic sweep as
    activation. The sweep payload runs this gate AFTER the activation gate
    returns NO_REPLY (the cohorts are mutually exclusive — activation requires
    onboarding NOT completed, this one requires it completed). Because the sweep
    is generic, this gate COMPUTES which of the 2 touches is due:

        index = first_meal_nudges_sent + 1   (1..2)

      touch1 fires as soon as the user is eligible (onboarded, no meal) — no
        prior nudge, so no gap to satisfy;
      touch2 fires only once now - last_nudge_at >= FIRST_MEAL_TOUCH2_GAP_SECONDS
        (~24h after touch1), giving the chosen "touch1 immediately + touch2 +24h"
        cadence and de-bunching catch-up sweeps.

    On SEND it writes the chosen index/angle into `out` (composer renders by it),
    replacing the old `nudge=N` cron-payload source.

    Suppress (NO_REPLY) when ANY of:
      - onboarding NOT completed (wrong cohort — that's the activation nudge's
        never-replied user; keeps the two cohorts mutually exclusive at the
        gate level, not just at cron-creation time)
      - the user has already logged a meal on any date (nudge self-cancels —
        normal tracking takes over)
      - the nudge cap (FIRST_MEAL_NUDGE_CAP) has already been reached — this is
        the terminal anti-nag guarantee, and it is lifecycle-independent
      - touch2 is not yet 24h past touch1

    Note: leave/pause AND the authoritative Silent state (stage 5) are handled by
    the generic check_leave + check_engagement_stage gates that run BEFORE this
    one (check_engagement_stage derives stage from the LOCAL lifecycle-check.py
    resolver — days_silent + recall counters, no DB). The `notification_stage`
    field is no longer read here; only `activation.*` (non-stage business
    counters, owned in engagement.json) is read. This gate does NOT increment the
    counter — notification-composer calls
    activation-mark-sent.py --counter first_meal_nudges_sent after a successful
    compose (which also stamps last_nudge_at).
    """
    if not _onboarding_completed(workspace_dir):
        return False, "first_meal_nudge — onboarding not completed (wrong cohort)"

    if _any_meal_ever_logged(workspace_dir):
        return False, "first_meal_nudge — user has already logged a meal, nudge no longer needed"

    nudges_sent = 0
    last_nudge_at_raw = None
    eng_path = os.path.join(workspace_dir, "data", "engagement.json")
    if os.path.exists(eng_path):
        try:
            with open(eng_path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            data = {}
        activation = data.get("activation") or {}
        nudges_sent = activation.get("first_meal_nudges_sent", 0)
        if not isinstance(nudges_sent, int) or isinstance(nudges_sent, bool):
            nudges_sent = 0
        last_nudge_at_raw = activation.get("last_nudge_at")

    if nudges_sent >= FIRST_MEAL_NUDGE_CAP:
        return False, f"first_meal_nudge — cap reached ({nudges_sent}/{FIRST_MEAL_NUDGE_CAP})"

    index = nudges_sent + 1  # 1..2 (cap enforced above)

    # touch2 must wait FIRST_MEAL_TOUCH2_GAP after touch1's send. touch1 has no
    # prior nudge → it fires as soon as the user is eligible.
    if index >= 2:
        now = datetime.now(timezone.utc)
        last_nudge_dt = _parse_iso(last_nudge_at_raw)
        if last_nudge_dt is None:
            # sent==1 should imply last_nudge_at was stamped; if it's missing we
            # cannot confirm 24h elapsed → hold (anti-nag) rather than fire early.
            return False, "first_meal_nudge — touch 2 held (no last_nudge_at to time the 24h gap)"
        gap = (now - last_nudge_dt).total_seconds()
        if gap < FIRST_MEAL_TOUCH2_GAP_SECONDS:
            return False, (f"first_meal_nudge — touch 2 not due yet "
                           f"(last nudge {int(gap)}s ago < {FIRST_MEAL_TOUCH2_GAP_SECONDS}s)")

    if out is not None:
        out["nudge_index"] = index
        out["nudge_angle"] = FIRST_MEAL_ANGLES[index]
    return True, f"first_meal_nudge — touch {index} due (angle={FIRST_MEAL_ANGLES[index]})"


# Cold = behavioral (no meal/weight check-in AND zero inbound SMS) — NOT
# plan-less. ~86% of this cohort came via TDEE handoff and HAVE a full PLAN.md
# ("got their plan, went silent"); only ~14% are truly plan-less. So this gate
# already serves the cold population, and the composer's WARM/COLD split (PLAN.md
# present?) gives the plan-less minority the no-numbers variant.
#
# Sequence shortened 4 → 2 touches (Track A, 2026-06-24). The WARM recall
# analysis showed touches 3 and 4 produced ZERO recall — every re-engagement came
# from touch 1 or 2, and the 3 users who hit the full 4-touch cap never replied.
# Cold users have even lower intent, so touches 3-4 (T+3d rapport, T+7d exit) were
# pure opt-out/annoyance risk with no upside. We keep ONLY the two beats that ever
# worked: T+4h and T+24h. The cap is the terminal anti-nag guarantee.
ACTIVATION_NUDGE_CAP = 2

# Minimum age the SMS coaching service is offered to. Mirrors the TDEE-upstream
# refusal — this SMS gate is defense-in-depth (a minor who somehow reached a
# warm-start agent must never receive a re-engagement nudge).
ACTIVATION_MIN_AGE = 18

# Cold-Start v3: the infra side fires ONE recurring "sweep" cron (~every 2h)
# whose payload is GENERIC — it no longer tells us which touch to send. So the
# gate computes the due touch here:
#   index = nudges_sent + 1   (1..2)
# Touch N is due iff BOTH:
#   (a) now - claimedAt >= ACTIVATION_THRESHOLDS_SECONDS[index]
#   (b) now - last_nudge_at >= ACTIVATION_MIN_GAP_SECONDS  (de-bunch: when a
#       sweep catches up after an overnight registration and several thresholds
#       are already crossed, only ONE touch goes out per sweep window).
# Index → angle (content key the composer renders):
#   1=value_first  2=photo
# Thresholds are the agreed contract: touch1=4h, touch2=24h. (T+3d/T+7d dropped —
# see ACTIVATION_NUDGE_CAP note above.)
ACTIVATION_THRESHOLDS_SECONDS = {
    1: 4 * 3600,        # T+4h
    2: 24 * 3600,       # T+24h
}
ACTIVATION_ANGLES = {
    1: "value_first",
    2: "photo",
}
# MIN_GAP ~20h: at most one activation touch per ~20h. 20h (not 24h) leaves
# slack so a touch isn't skipped a whole extra day when a sweep lands slightly
# under 24h after the previous send.
ACTIVATION_MIN_GAP_SECONDS = 20 * 3600


def _parse_iso(value):
    """Parse an ISO-8601 timestamp (with optional trailing 'Z') into an aware
    UTC datetime, or None on any failure. claimedAt is written by infra as
    `new Date().toISOString()` (always UTC 'Z'); last_nudge_at is written by
    activation-mark-sent.py as UTC 'Z' too."""
    if not isinstance(value, str) or not value.strip():
        return None
    s = value.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _profile_age_years(workspace_dir):
    """Return the user's age in whole years from a STRUCTURED source, or None
    when no reliable structured age is available.

    Source priority (most reliable first):
      1. handoff.json > structured.age_years — a typed integer written by the
         infra-side TDEE handoff. This is the canonical, machine-written field
         for warm-start users (the only cohort this gate targets).
      2. PROFILE.md field form `- **Age:** <int>` — the same field-form
         convention used elsewhere (mirrors _onboarding_completed's regex
         style). PROFILE.md is the handoff overlay, so the value is the same
         number, just markdown-rendered.

    Returns None (→ caller fails OPEN, no cancel) when neither structured source
    yields a clean integer. We deliberately do NOT scrape free-text summaries —
    a fragile parse that mis-reads an age is worse than relying on the typed
    field plus the upstream TDEE refusal.
    """
    # 1) handoff.json structured field (typed int).
    hpath = os.path.join(workspace_dir, "handoff.json")
    if os.path.exists(hpath):
        try:
            with open(hpath) as f:
                hd = json.load(f)
            if isinstance(hd, dict):
                struct = hd.get("structured")
                if isinstance(struct, dict):
                    age = struct.get("age_years")
                    if isinstance(age, bool):
                        age = None  # guard: bool is an int subclass
                    if isinstance(age, int):
                        return age
                    if isinstance(age, float) and age == int(age):
                        return int(age)
                    if isinstance(age, str) and age.strip().isdigit():
                        return int(age.strip())
        except (json.JSONDecodeError, IOError):
            pass

    # 2) PROFILE.md field form `- **Age:** <int>`.
    import re as _re
    ppath = os.path.join(workspace_dir, "PROFILE.md")
    if os.path.exists(ppath):
        try:
            with open(ppath) as f:
                content = f.read()
            m = _re.search(
                r"^\s*-\s*\*\*Age:\*\*\s*(\d{1,3})\b",
                content, _re.IGNORECASE | _re.MULTILINE,
            )
            if m:
                return int(m.group(1))
        except IOError:
            pass

    return None


def _read_channel_source(workspace_dir):
    """Load channel-source.json from the workspace root.

    Returns (data_dict, readable):
      - (dict, True)  when the file exists and parsed to a dict
      - ({},  False)  when the file is missing OR unreadable/corrupt

    The `readable` flag lets the activation gate fail CLOSED (NO_REPLY) when the
    file is absent/unreadable — the target cohort always has this file (infra
    writes it at registration), so a missing file is anomalous and the
    conservative anti-nag choice is to not nudge when we can't read state.
    """
    path = os.path.join(workspace_dir, "channel-source.json")
    if not os.path.exists(path):
        return {}, False
    try:
        with open(path) as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data, True
        return {}, False
    except (json.JSONDecodeError, IOError):
        return {}, False


def _onboarding_completed(workspace_dir):
    """True iff health-profile.md has a REAL Onboarding Completed date (not '—').

    Mirrors the field-form regex used by mark-onboarding-done.py /
    onboarding-check.py: `- **Onboarding Completed:** <value>` inside the
    Automation section. A value of '—' (or '-', empty) means NOT completed.
    """
    import re as _re
    path = os.path.join(workspace_dir, "health-profile.md")
    if not os.path.exists(path):
        return False
    try:
        with open(path) as f:
            content = f.read()
    except IOError:
        return False
    m = _re.search(
        r"^\s*-\s*\*\*Onboarding\s+Completed:\*\*\s*(.+?)\s*$",
        content, _re.IGNORECASE | _re.MULTILINE,
    )
    if not m:
        return False
    val = m.group(1).strip()
    return bool(val) and val not in ("—", "-", "none", "None")


def _activation_enabled():
    """Kill switch for the activation nudge. Reads ACTIVATION_ENABLED from the
    environment. Default ON: only an explicit falsey value disables it. This lets
    ops hot-disable the entire activation sequence (set ACTIVATION_ENABLED=0 and
    restart the gateway) without a skill redeploy. Scoped to activation only — it
    does NOT affect meal/weight reminders, recall, or the first-meal nudge."""
    val = os.environ.get("ACTIVATION_ENABLED")
    if val is None:
        return True
    return val.strip().lower() not in ("0", "false", "no", "off", "")


def check_activation_nudge(workspace_dir, tz_offset, out=None):
    """Gate for the activation nudge (meal_type=activation) — the Part-1
    "greeted but never replied" cohort.

    Cold-Start v3: the infra side now fires ONE recurring generic "sweep" cron
    instead of payload-tagged one-shots, so the sweep no longer tells us which
    touch to send. This gate COMPUTES the due touch:

        index = nudges_sent + 1   (1..2)

    and sends touch `index` ONLY when BOTH timing windows are open:
      (a) now - claimedAt   >= ACTIVATION_THRESHOLDS_SECONDS[index]
          (touch1=4h, touch2=24h — the agreed contract; T+3d/T+7d dropped, see
          ACTIVATION_NUDGE_CAP note)
      (b) now - last_nudge_at >= ACTIVATION_MIN_GAP_SECONDS  (~20h)
          de-bunches a catch-up sweep: when a user registered overnight and the
          first daytime sweep sees several thresholds already crossed, only ONE
          touch goes out per ~20h window (no first-nudge gap on touch 1).

    On SEND it writes the chosen index/angle into `out` (composer renders by it).

    The DEFINING gate (unchanged): read channel-source.json > lastInboundAt
    (epoch ms, written by infra Phase-0 on every inbound). If lastInboundAt is
    present AT ALL, the user has replied → NO_REPLY (cancel).

    Also suppress (NO_REPLY) when ANY of (all unchanged):
      - channel-source.json is missing/unreadable (fail closed)
      - the user is a minor (structured age < ACTIVATION_MIN_AGE; fails OPEN
        when no structured age is available)
      - onboarding already completed (wrong cohort)
      - any meal ever logged (they engaged)
      - engagement stage is Silent (handled by check_engagement_stage, before
        this gate)
      - the cap (ACTIVATION_NUDGE_CAP) has been reached

    Leave/pause AND the authoritative lifecycle Silent state are handled by the
    generic check_leave + check_engagement_stage gates that run BEFORE this one.
    Stage is NOT read from engagement.json. Only `activation.nudges_sent` and
    `activation.last_nudge_at` (non-stage business fields, owned in
    engagement.json, written ONLY by activation-mark-sent.py) are read. This
    gate does NOT write engagement.json — the composer calls
    activation-mark-sent.py --counter nudges_sent after a successful compose,
    which atomically bumps the counter AND stamps last_nudge_at.
    """
    # Kill switch: hot-disable the whole activation nudge without a redeploy.
    # Set ACTIVATION_ENABLED=0 (or false/no/off) in the gateway/cron environment
    # to short-circuit every activation touch to NO_REPLY. Default ON (any other
    # value, or unset, keeps the nudge running). Cheap operational lever — flip
    # the env var and restart the gateway; no skill push needed.
    if not _activation_enabled():
        return False, "activation — disabled via ACTIVATION_ENABLED kill switch"

    cs, cs_readable = _read_channel_source(workspace_dir)

    # --- Fail closed: if we can't read channel-source.json at all, do NOT
    # nudge. The target cohort always has this file; a missing/unreadable file
    # is anomalous and the conservative anti-nag choice is silence. ---
    if not cs_readable:
        return False, "activation — channel-source.json missing/unreadable, failing closed (no nudge)"

    # --- The defining check: any inbound at all means the user replied. ---
    if cs.get("lastInboundAt") is not None:
        return False, "activation — lastInboundAt present (user has replied), nudge cancelled"

    # --- Minor gate (defense-in-depth behind the TDEE upstream refusal): never
    # nudge a user whose STRUCTURED age is under ACTIVATION_MIN_AGE. Fails OPEN
    # (no cancel) when no reliable structured age is available — we do not block
    # on a missing/ambiguous age, and we do not scrape free text. ---
    age = _profile_age_years(workspace_dir)
    if age is not None and age < ACTIVATION_MIN_AGE:
        return False, f"activation — minor (age={age} < {ACTIVATION_MIN_AGE}), service not offered"

    # Target user must actually be a handoff/never-replied case: onboarding
    # NOT completed. If onboarding is done, this is the wrong cohort.
    if _onboarding_completed(workspace_dir):
        return False, "activation — onboarding already completed (wrong cohort)"

    # Any meal logged means they engaged (defensive — implies inbound too).
    if _any_meal_ever_logged(workspace_dir):
        return False, "activation — a meal has been logged (user engaged), nudge cancelled"

    # --- Read the activation business counters (single source of truth, written
    # only by activation-mark-sent.py). ---
    nudges_sent = 0
    last_nudge_at_raw = None
    eng_path = os.path.join(workspace_dir, "data", "engagement.json")
    if os.path.exists(eng_path):
        try:
            with open(eng_path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            data = {}
        activation = data.get("activation") or {}
        nudges_sent = activation.get("nudges_sent", 0)
        if not isinstance(nudges_sent, int) or isinstance(nudges_sent, bool):
            nudges_sent = 0
        last_nudge_at_raw = activation.get("last_nudge_at")

    # Cap: terminal anti-nag guarantee, lifecycle-independent.
    if nudges_sent >= ACTIVATION_NUDGE_CAP:
        return False, f"activation — cap reached ({nudges_sent}/{ACTIVATION_NUDGE_CAP})"

    # --- Compute which touch is due. ---
    index = nudges_sent + 1  # 1..2 (cap already enforced above)
    threshold = ACTIVATION_THRESHOLDS_SECONDS.get(index)
    if threshold is None:
        # Defensive: index outside 1..2 should be impossible past the cap gate.
        return False, f"activation — no threshold for computed index {index}"

    now = datetime.now(timezone.utc)

    # (a) elapsed since registration must reach this touch's threshold.
    claimed_dt = _parse_iso(cs.get("claimedAt"))
    if claimed_dt is None:
        # claimedAt is the registration anchor for the whole schedule. The target
        # cohort always has it (infra writes it at pool claim); if it's missing
        # or unparseable we can't time the touch → fail closed (anti-nag).
        return False, "activation — claimedAt missing/unparseable, cannot time touch (fail closed)"
    elapsed = (now - claimed_dt).total_seconds()
    if elapsed < threshold:
        return False, (f"activation — touch {index} not due yet "
                       f"(elapsed {int(elapsed)}s < threshold {threshold}s)")

    # (b) MIN_GAP since the last sent touch (de-bunch catch-up sweeps). Touch 1
    # has no prior nudge → no gap to satisfy.
    last_nudge_dt = _parse_iso(last_nudge_at_raw)
    if last_nudge_dt is not None:
        gap = (now - last_nudge_dt).total_seconds()
        if gap < ACTIVATION_MIN_GAP_SECONDS:
            return False, (f"activation — touch {index} held by MIN_GAP "
                           f"(last nudge {int(gap)}s ago < {ACTIVATION_MIN_GAP_SECONDS}s)")

    # Due. Hand the computed index/angle to the composer.
    if out is not None:
        out["nudge_index"] = index
        out["nudge_angle"] = ACTIVATION_ANGLES[index]
    return True, f"activation — touch {index} due (angle={ACTIVATION_ANGLES[index]})"


def check_health_flags(workspace_dir, meal_type):
    """Check: skip weight reminders if ED-related flags present."""
    if meal_type != "weight":
        return True, None

    # Check USER.md for health flags
    user_md = os.path.join(workspace_dir, "USER.md")
    if not os.path.exists(user_md):
        return True, None

    try:
        with open(user_md) as f:
            content = f.read().lower()
        if "avoid_weight_focus" in content or "history_of_ed" in content:
            return False, "health flag: avoid_weight_focus or history_of_ed"
    except IOError:
        pass

    return True, None


def check_scheduling_constraints(workspace_dir, meal_type, tz_offset):
    """Check 4: scheduling constraints from health-preferences.md."""
    prefs_path = os.path.join(workspace_dir, "health-preferences.md")
    if not os.path.exists(prefs_path):
        return True, None

    try:
        with open(prefs_path) as f:
            content = f.read().lower()
    except IOError:
        return True, None

    weekday = get_local_weekday(tz_offset)  # 0=Mon, 6=Sun
    weekday_names_en = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    weekday_names_zh = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    today_en = weekday_names_en[weekday]
    today_zh = weekday_names_zh[weekday]

    # Check for "skip breakfast on workdays" pattern
    if meal_type == "breakfast" and weekday < 5:  # Mon-Fri
        skip_patterns = [
            "skip breakfast on workday",
            "skips breakfast on workday",
            "always skips breakfast",
            "不吃早餐",
            "跳过早餐",
            "工作日不吃早餐",
        ]
        for pattern in skip_patterns:
            if pattern in content:
                return False, f"scheduling constraint: {pattern}"

    # Check for day-specific constraints like "works late on wednesdays"
    # Look for lines containing today's name + skip/delay keywords
    for line in content.split("\n"):
        if (today_en in line or today_zh in line) and meal_type in line:
            skip_keywords = ["skip", "跳过", "不吃", "不提醒", "no reminder"]
            for kw in skip_keywords:
                if kw in line:
                    return False, f"scheduling constraint: {line.strip()}"

    return True, None


def check_leave(workspace_dir, tz_offset, mock_date=None):
    """Check if user is on leave. If so, suppress all reminders.

    Leave is now tracked SOLELY by the local data/leave.json (start/end/reason).
    The DB silence_state='frozen' source is gone (the 3100 lifecycle API was never
    deployed). leave.json is the single source of truth: present + today within
    [start, end] → on leave → NO_REPLY. Expired files are auto-cleaned.
    """
    leave_path = os.path.join(workspace_dir, "data", "leave.json")

    # 读 leave.json 本地态
    leave_data = None
    if os.path.exists(leave_path):
        try:
            with open(leave_path) as f:
                leave_data = json.load(f)
        except (json.JSONDecodeError, IOError):
            try:
                os.remove(leave_path)  # 损坏文件清理
            except OSError:
                pass

    start = (leave_data or {}).get("start", "")
    end = (leave_data or {}).get("end", "")
    if leave_data is not None and (not start or not end):
        # 无效请假文件 → 清理
        try:
            os.remove(leave_path)
        except OSError:
            pass
        leave_data = None

    if mock_date:
        today = mock_date
    else:
        tz = timezone(timedelta(seconds=tz_offset))
        today = datetime.now(tz).strftime("%Y-%m-%d")

    leave_active_local = leave_data is not None and start <= today <= end

    if leave_active_local:
        return False, f"user on leave ({start} to {end})"
    # 过期自动清理
    if leave_data is not None and today > end:
        try:
            os.remove(leave_path)
        except FileNotFoundError:
            pass
        except OSError as e:
            log(f"Warning: could not delete expired leave.json: {e}")
    return True, None


def check_reminders_paused(workspace_dir):
    """Check 0 (belt-and-suspenders): user soft-paused ALL reminders.

    Infra implements a deterministic "pause all reminders" opt-down: on a
    stop/pause intent it calls disableCronJobsForAgent AND sets
    remindersPaused=true in the agent's channel-source.json (workspace root,
    OWNED by infra — we only READ it here). Infra already gates its own proactive
    paths; this is the FIRE-TIME gate so any cron still queued/surviving produces
    NO_REPLY for EVERY meal_type instead of a proactive message.

    FAIL-OPEN: channel-source.json missing/corrupt or the field absent → treat as
    NOT paused (continue) — never trap a user in silence on a read error.
    """
    cs, cs_readable = _read_channel_source(workspace_dir)
    if not cs_readable:
        return True, None  # fail-open
    val = cs.get("remindersPaused")
    if val is True or (isinstance(val, str) and val.strip().lower() == "true"):
        return False, "remindersPaused=true — user has paused all reminders"
    return True, None


def main():
    parser = argparse.ArgumentParser(description="Pre-send check for meal/weight reminders")
    parser.add_argument("--workspace-dir", required=True, help="Agent workspace root")
    parser.add_argument("--meal-type", required=True,
                        choices=["breakfast", "lunch", "dinner", "meal_1", "meal_2",
                                 "weight", "weight_morning_followup",
                                 "custom", "weekly_report", "daily_summary",
                                 "first_meal_nudge", "activation"],
                        help="Meal type to check")
    parser.add_argument("--tz-offset", required=True, type=int,
                        help="Timezone offset in seconds from UTC")
    parser.add_argument("--mock-date", default=None,
                        help="Mock today's date YYYY-MM-DD (for testing)")
    args = parser.parse_args()
    args.workspace_dir = _normalize_path(args.workspace_dir)

    # Stage is resolved locally + deterministically by lifecycle-check.py
    # (check_engagement_stage calls the in-workspace resolver — no HTTP, no DB).

    stage_info = {"stage": 1}
    activation_info = {}
    first_meal_info = {}
    checks = [
        ("reminders_paused", lambda: check_reminders_paused(args.workspace_dir)),
        ("leave", lambda: check_leave(args.workspace_dir, args.tz_offset, args.mock_date)),
        ("health_profile", lambda: check_health_profile(args.workspace_dir)),
        ("engagement_stage", lambda: check_engagement_stage(
            args.workspace_dir, args.meal_type, args.tz_offset, out=stage_info)),
        ("health_flags", lambda: check_health_flags(args.workspace_dir, args.meal_type)),
        ("scheduling", lambda: check_scheduling_constraints(
            args.workspace_dir, args.meal_type, args.tz_offset)),
    ]

    # Add meal-specific or weight-specific check
    if args.meal_type == "weight":
        checks.append(("weight_logged", lambda: check_weight_logged(
            args.workspace_dir, args.tz_offset)))
    elif args.meal_type == "weight_morning_followup":
        checks.append(("weight_logged_yesterday_or_today", lambda: check_weight_logged_yesterday_or_today(
            args.workspace_dir, args.tz_offset)))
    elif args.meal_type == "first_meal_nudge":
        checks.append(("first_meal_nudge", lambda: check_first_meal_nudge(
            args.workspace_dir, args.tz_offset, out=first_meal_info)))
    elif args.meal_type == "activation":
        checks.append(("activation", lambda: check_activation_nudge(
            args.workspace_dir, args.tz_offset, out=activation_info)))
    elif args.meal_type in ("custom", "weekly_report", "daily_summary"):
        pass  # Only stage check needed, no meal-logged check
    else:
        checks.append(("meal_logged", lambda: check_meal_logged(
            args.workspace_dir, args.meal_type, args.tz_offset)))

    # Run all checks
    for check_name, check_fn in checks:
        passed, reason = check_fn()
        if not passed:
            log(f"FAIL [{check_name}]: {reason}")
            print("NO_REPLY")
            return

    log("All checks passed")

    # Activation: the gate computed which touch is due (Cold-Start v3). Emit the
    # nudgeIndex/angle so the composer renders the right content — this replaces
    # the old cron-payload (nudgeIndex=N, nudgeAngle=X) source.
    if args.meal_type == "activation" and "nudge_index" in activation_info:
        print(f"SEND activation nudgeIndex={activation_info['nudge_index']} "
              f"nudgeAngle={activation_info['nudge_angle']}")
        return

    # First-meal nudge (Cold-Start v3 Part-2): same generic-sweep contract as
    # activation — the gate computed which of the 2 touches is due; emit the
    # nudgeIndex/angle so the composer renders the right copy (replaces the old
    # cron-payload `nudge=N` source).
    if args.meal_type == "first_meal_nudge" and "nudge_index" in first_meal_info:
        print(f"SEND first_meal_nudge nudgeIndex={first_meal_info['nudge_index']} "
              f"nudgeAngle={first_meal_info['nudge_angle']}")
        return

    # stage_info 由 engagement_stage check 填入「认领前」的 stage/days_silent
    if stage_info["stage"] >= 2:
        print(f"SEND recall stage={stage_info['stage']} days_silent={stage_info.get('days_silent', 0)}")
    else:
        print("SEND")


if __name__ == "__main__":
    main()
