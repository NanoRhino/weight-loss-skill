#!/usr/bin/env python3
"""
check-stage.py — Update engagement stage based on user silence duration.

⚠️ DEPRECATED (post-lifecycle-migration): stage is now owned by the lifecycle
DB (computed live from last_interaction_at) and read via the lifecycle API.
This script and the engagement.json `notification_stage` / `stage_changed_at`
fields it writes are NOT in the live path anymore and are being removed. It is
retained only for any legacy caller. The activation/first-meal anti-nag
guarantee does NOT depend on this script — it is enforced by the pre-send-check
cap gate (reads activation.first_meal_nudges_sent / activation.nudges_sent),
which is lifecycle-independent.

Derives last interaction from meal logging records (data/meals/*.json)
rather than relying on a platform-written timestamp. A "logged day" is
any date with at least one meal entry that contains food data.

Lifecycle rules (V2):

  Stage 1 (ACTIVE)   → days_silent >= 3 (2 full missed days) → Stage 2 (RECALL)
  Stage 2 (RECALL)   → days_silent >= 6                       → Stage 3 (WEEKLY)
  Stage 3 (WEEKLY)   → 3 weekly recalls sent                   → Stage 4 (MONTHLY)
  Stage 4 (MONTHLY)  → 3 monthly recalls sent                  → Stage 5 (SILENT)
  Stage 5 (SILENT)   → permanent silence

When a silent user returns (any message or meal logged while stage > 1),
resets to Stage 1.

Usage:
  python3 check-stage.py --workspace-dir <path> --tz-offset <seconds>

Output (stdout): current stage number (1-5) and days_silent
Transitions are logged to stderr.

Exit code 0 always.
"""

import argparse
import glob
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone, timedelta

def _normalize_path(p):
    """Lowercase wechat-dm/wecom-dm segment to avoid case-mismatch directories."""
    import re as _re
    return _re.sub(r'(workspace-(?:wechat|wecom)-dm-)([^/]+)', lambda m: m.group(1) + m.group(2).lower(), p)



def log(msg):
    """Log to stderr (not visible to user, only for debugging)."""
    print(f"[check-stage] {msg}", file=sys.stderr)


# Transition thresholds (V2)
STAGE_1_TO_2_DAYS = 3   # 3 days_silent (2 full missed days) → recall
# Stage 2→3: days_silent >= 5
# Stage 3→4: weekly_recall_count >= 3
# Stage 4→5: monthly_recall_count >= 3

ENGAGEMENT_DEFAULTS = {
    "notification_stage": 1,
    "stage_changed_at": None,
    "last_recall_date": None,
    "recall_2_sent": False,
    "reminder_config": {},
}

# Activation (first-meal nudge) cap. After this many nudges with still-zero
# logged meals, a never-logged user goes straight to Stage 5 (Silent) instead
# of cycling through the recall-content stages (S2-S4), whose content is
# generated from logged meals and would be hollow for a never-logged user.
FIRST_MEAL_NUDGE_CAP = 2

# Activation nudge cap (Part-1 "greeted but never replied" cohort). Same anti-nag
# rule: after this many nudges with still no inbound/meal, go straight to Silent.
# NOTE: check-stage.py is deprecated (not in the live path — the authoritative cap
# gate lives in notification-composer/scripts/pre-send-check.py). Kept in sync at 4
# so a reactivation can't silently regress to the old 2-touch cap.
ACTIVATION_NUDGE_CAP = 4


def load_engagement(workspace_dir):
    """Load engagement.json, returning (data_dict, file_existed)."""
    path = os.path.join(workspace_dir, "data", "engagement.json")
    if not os.path.exists(path):
        return dict(ENGAGEMENT_DEFAULTS), False
    try:
        with open(path) as f:
            data = json.load(f)
        for key, default in ENGAGEMENT_DEFAULTS.items():
            if key not in data:
                data[key] = default
        return data, True
    except (json.JSONDecodeError, IOError) as e:
        log(f"Warning: could not read engagement.json: {e}")
        return dict(ENGAGEMENT_DEFAULTS), False


def load_leave(workspace_dir):
    """
    Load leave.json if exists and valid.
    Returns (leave_data, file_existed) or (None, False) if no valid leave data.
    """
    path = os.path.join(workspace_dir, "data", "leave.json")
    if not os.path.exists(path):
        return None, False
    try:
        with open(path) as f:
            data = json.load(f)
        # Validate required fields
        if not isinstance(data, dict):
            log("Warning: leave.json is not a dict")
            return None, False
        if "start" not in data or "end" not in data:
            log("Warning: leave.json missing start or end field")
            return None, False
        return data, True
    except (json.JSONDecodeError, IOError) as e:
        log(f"Warning: could not read leave.json: {e}")
        return None, False


def save_engagement(workspace_dir, data):
    """Write engagement.json (creates data/ dir if needed)."""
    path = os.path.join(workspace_dir, "data", "engagement.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def parse_iso(s):
    """Parse an ISO-8601 datetime string, returning None on failure."""
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def normalize_stage(stage):
    """Convert stage to int (handles string names from older formats)."""
    if isinstance(stage, int):
        return stage
    if isinstance(stage, str):
        stage_map = {"active": 1, "pause": 2, "recall": 3, "silent": 4}
        return stage_map.get(stage.lower(), 1)
    return 1


def _meal_has_food(meal):
    """Check if a meal dict contains actual food data (items or foods list)."""
    if not isinstance(meal, dict):
        return False
    items = meal.get("items") or meal.get("foods")
    return bool(items)


def get_last_logged_date(workspace_dir, tz_offset=0):
    """
    Scan data/meals/*.json to find the most recent date with at least one
    meal entry that contains actual food data. Returns a date string (YYYY-MM-DD)
    or None if no logged meals found.
    """
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
            for key, meal in meals.items():
                if _meal_has_food(meal):
                    has_logged = True
                    break

        if has_logged:
            logged_dates.append(date_str)

    return max(logged_dates) if logged_dates else None


def _get_agent_id(workspace_dir):
    """Derive agentId from workspace directory name.
    /home/admin/.openclaw/workspace-wecom-dm-fuzhuoran -> wecom-dm-fuzhuoran
    """
    basename = os.path.basename(os.path.normpath(workspace_dir))
    if basename.startswith("workspace-"):
        return basename[len("workspace-"):]
    return basename


_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.normpath(os.path.join(_SCRIPT_DIR, "..", "..", "..", ".."))
_STATE_DIR = os.environ.get("OPENCLAW_STATE_DIR", os.path.join(_PROJECT_ROOT, ".openclaw-gateway"))


def _get_cron_jobs_path():
    """Find the cron jobs.json file."""
    return os.path.join(_STATE_DIR, "cron", "jobs.json")


def _toggle_user_crons(workspace_dir, disable=True):
    """Disable or enable all cron jobs for a user by agentId.

    Returns True if the operation succeeded (changes written or no changes
    needed), False if jobs.json could not be found/opened.
    """
    agent_id = _get_agent_id(workspace_dir)
    jobs_path = _get_cron_jobs_path()

    if not os.path.exists(jobs_path):
        log(f"cron jobs.json not found at {jobs_path}")
        return False

    try:
        with open(jobs_path) as f:
            data = json.load(f)

        jobs = data.get("jobs", []) if isinstance(data, dict) else data
        changed = False

        for job in jobs:
            if job.get("agentId") == agent_id:
                if disable and job.get("enabled", True):
                    job["enabled"] = False
                    job["disabled_by"] = "s4_auto"
                    changed = True
                    log(f"  disabled cron: {job.get('id')} ({job.get('name')})")
                elif not disable and job.get("disabled_by") == "s4_auto":
                    job["enabled"] = True
                    job.pop("disabled_by", None)
                    changed = True
                    log(f"  re-enabled cron: {job.get('id')} ({job.get('name')})")

        if changed:
            # Atomic write: tmp file + os.replace to avoid race with gateway reads
            tmp_fd, tmp_path = tempfile.mkstemp(
                dir=os.path.dirname(jobs_path), suffix=".tmp"
            )
            try:
                with os.fdopen(tmp_fd, "w") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                os.replace(tmp_path, jobs_path)
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
            # Signal gateway to reload cron config
            try:
                subprocess.run(["openclaw", "cron", "list"],
                             capture_output=True, timeout=10)
            except Exception:
                pass  # best-effort reload
        else:
            action = "disable" if disable else "enable"
            log(f"  no cron jobs to {action} for agentId={agent_id}")
        return True
    except Exception as e:
        log(f"Error toggling crons for {agent_id}: {e}")
        return False


def _disable_user_crons(workspace_dir):
    return _toggle_user_crons(workspace_dir, disable=True)


def _enable_user_crons(workspace_dir):
    return _toggle_user_crons(workspace_dir, disable=False)


def main():
    parser = argparse.ArgumentParser(
        description="Update engagement stage based on user silence duration"
    )
    parser.add_argument("--workspace-dir", required=True, help="Agent workspace root")
    parser.add_argument("--tz-offset", required=True, type=int,
                        help="Timezone offset in seconds from UTC")
    parser.add_argument("--user-active", action="store_true",
                        help="Force-signal that user just sent a message (chat or food). "
                             "Triggers reset even without a meal logged today.")
    args = parser.parse_args()
    args.workspace_dir = _normalize_path(args.workspace_dir)

    data, existed = load_engagement(args.workspace_dir)
    tz = timezone(timedelta(seconds=args.tz_offset))
    now = datetime.now(tz)
    today_str = now.strftime("%Y-%m-%d")

    stage = normalize_stage(data.get("notification_stage", 1))
    stage_changed_at = parse_iso(data.get("stage_changed_at"))

    # --- Derive last interaction from meal records ---
    last_logged = get_last_logged_date(args.workspace_dir, args.tz_offset)

    if last_logged is None:
        # No meal records at all — user completed onboarding but has never
        # logged a meal (the "activation" cohort the first-meal nudge targets).
        #
        # These users must NOT cycle through the recall-content stages
        # (S2 emotion recall, S3 weekly knowledge, S4 monthly) — that content
        # is generated from the user's logged meals and would be hollow for a
        # never-logged user. Instead: stay in Stage 1 while the first-meal
        # nudge fires (capped at FIRST_MEAL_NUDGE_CAP), then go straight to
        # Stage 5 (Silent). This mirrors the never-replied cohort's
        # permanent-Silent rule and the anti-nag ethos.
        changed = False
        if not existed:
            data["stage_changed_at"] = now.isoformat()
            save_engagement(args.workspace_dir, data)
            log("No meal records found, initialized engagement.json")
            print(f"{stage} 0")
            return

        # --user-active overrides everything: user just sent a message, so
        # they are not silent right now regardless of meal history. If they
        # were already past S1 (shouldn't normally happen for this cohort),
        # the reset logic below handles it; otherwise hold at current stage.
        if args.user_active:
            if data.get("last_active_date") != today_str:
                data["last_active_date"] = today_str
                changed = True
            # A returning never-logged user in S5 resets to S1 so the nudge
            # cycle can resume only if they re-onboard; normal welcome handled
            # by the global welcome-back check. Keep it simple: hold stage.
            if changed:
                save_engagement(args.workspace_dir, data)
            print(f"{stage} 0")
            return

        # Two activation cohorts share this never-logged branch:
        #   - first_meal_nudges_sent → onboarded-but-never-logged (Part 2)
        #   - nudges_sent            → greeted-but-never-replied   (Part 1)
        # Whichever cohort a user is in, once that nudge cap is reached with
        # still no meal logged, they go straight to Silent (never into S2-S4
        # recall content, which is hollow for a never-engaged user).
        activation = data.get("activation") or {}
        first_meal_sent = activation.get("first_meal_nudges_sent", 0)
        activation_sent = activation.get("nudges_sent", 0)
        cap_reached = (
            first_meal_sent >= FIRST_MEAL_NUDGE_CAP
            or activation_sent >= ACTIVATION_NUDGE_CAP
        )

        # Already exhausted a nudge cap → straight to Silent (skip S2-S4).
        if cap_reached and stage < 5:
            old_stage = stage
            stage = 5
            data["notification_stage"] = 5
            data["stage_changed_at"] = now.isoformat()
            if _disable_user_crons(args.workspace_dir):
                log("Activation: nudge cap reached, never-engaged user → S5 (Silent), personal crons disabled")
            else:
                log("Activation: nudge cap reached → S5, WARNING: failed to disable personal crons")
            save_engagement(args.workspace_dir, data)
            print(f"5 0")
            return

        # Under the cap → hold at Stage 1 so the activation/first-meal nudge can
        # fire. Do NOT fast-forward into recall content. days_silent reported as
        # 0 so the gentle-nudge / recall logic in pre-send-check stays dormant.
        if stage != 1 and stage < 5:
            stage = 1
            data["notification_stage"] = 1
            data["stage_changed_at"] = now.isoformat()
            changed = True
        if changed or not existed:
            save_engagement(args.workspace_dir, data)
        log(f"Activation: never-engaged user, first_meal={first_meal_sent} "
            f"activation={activation_sent} nudge(s) sent, holding Stage {stage}")
        print(f"{stage} 0")
        return
    else:
        last_logged_date = datetime.strptime(last_logged, "%Y-%m-%d").date()

    # Also consider last_active_date (set by --user-active resets)
    # The true "days silent" is the minimum of days since last meal AND
    # days since last user interaction (chat without food logging).
    last_active_str = data.get("last_active_date")
    if last_active_str:
        try:
            last_active_date = datetime.strptime(last_active_str, "%Y-%m-%d").date()
            # Use the MORE RECENT of meal vs active date
            if last_active_date > last_logged_date:
                last_logged_date = last_active_date
        except ValueError:
            pass

    today_date = now.date()
    days_silent = (today_date - last_logged_date).days

    log(f"Last logged meal: {last_logged}, days silent: {days_silent}, stage: {stage}")

    old_stage = stage
    changed = False
    original_days_silent = days_silent  # preserve for welcome_back check

    # --- Always update last_active_date when --user-active is passed ---
    # This keeps the recall timer fresh even if user chats without logging food.
    # Must happen BEFORE days_silent is used for stage decisions.
    if args.user_active:
        if data.get("last_active_date") != today_str:
            data["last_active_date"] = today_str
            # Recalculate days_silent with fresh active date
            days_silent = 0
            changed = True

    # --- User returned: logged a meal today/yesterday but stage > 1 ---
    # Also triggers if --user-active flag is passed (user sent any message).
    # Only trigger reset if there are actual meal records (last_logged != None)
    # OR if --user-active explicitly signals user interaction.
    # Welcome back: triggered when user returns after any absence (days_silent >= 1)
    # For S1 with days_silent >= 1: just set welcome_back flag, don't change stage
    # For S2+: full reset to S1
    # NOTE: use original_days_silent for threshold checks since --user-active
    # already reset days_silent to 0 above.
    user_returned_from_recall = (
        (stage > 1 and days_silent <= 1 and last_logged is not None) or
        (stage > 1 and args.user_active)
    )
    user_returned_brief = (
        stage <= 1 and original_days_silent >= 2 and args.user_active
    )
    
    if user_returned_from_recall:
        prev_stage = stage
        stage = 1
        data["notification_stage"] = 1
        data["stage_changed_at"] = now.isoformat()
        data["last_active_date"] = today_str
        data["last_recall_date"] = None
        data["recall_2_sent"] = False
        data["recall_count"] = 0
        data["last_nudge_date"] = None
        data.pop("leave_ended_at", None)
        data["welcome_back"] = True
        data["welcome_back_from_stage"] = prev_stage
        data["welcome_back_days_away"] = original_days_silent
        # If returning from S4+, signal that personal crons should be re-enabled
        if prev_stage >= 4:
            if _enable_user_crons(args.workspace_dir):
                log("User returning from S4+ — personal crons re-enabled")
            else:
                log("User returning from S4+ — WARNING: failed to re-enable personal crons (jobs.json not found)")
        changed = True
        log(f"RESET to stage 1 (user returned, last meal {last_logged}) — welcome_back flag set")
    elif user_returned_brief:
        data["last_active_date"] = today_str
        data["welcome_back"] = True
        data["welcome_back_from_stage"] = 1
        data["welcome_back_days_away"] = original_days_silent
        changed = True
        log(f"User returned after {original_days_silent} day(s) — welcome_back flag set (still S1)")

    # --- Check if user is on leave ---
    leave_data, leave_existed = load_leave(args.workspace_dir)
    on_leave = False
    if leave_data:
        try:
            leave_start = datetime.strptime(leave_data["start"], "%Y-%m-%d").date()
            leave_end = datetime.strptime(leave_data["end"], "%Y-%m-%d").date()

            if leave_start <= today_date <= leave_end:
                # User is currently on leave — freeze stage
                on_leave = True
                data["leave_ended_at"] = leave_data["end"]
                changed = True
                log(f"User is on leave ({leave_data.get('start')} to {leave_data.get('end')}) — stage frozen at {stage}")
            elif leave_end < today_date:
                # Leave just ended — update last_active_date to leave end date
                # Only update if current last_active_date is older or missing
                current_last_active = data.get("last_active_date")
                should_update = False
                if not current_last_active:
                    should_update = True
                else:
                    try:
                        current_last_active_date = datetime.strptime(current_last_active, "%Y-%m-%d").date()
                        if current_last_active_date < leave_end:
                            should_update = True
                    except ValueError:
                        should_update = True

                if should_update:
                    data["last_active_date"] = leave_data["end"]
                    data["leave_ended_at"] = leave_data["end"]
                    # Recalculate days_silent from leave end date
                    days_silent = (today_date - leave_end).days
                    changed = True
                    log(f"Leave ended on {leave_data['end']}, updated last_active_date, days_silent now {days_silent}")
        except (ValueError, KeyError) as e:
            log(f"Warning: could not parse leave dates: {e}")

    # --- Fallback: use leave_ended_at if leave.json was deleted ---
    if not leave_data:
        leave_ended_str = data.get("leave_ended_at")
        if leave_ended_str:
            try:
                leave_ended_date = datetime.strptime(leave_ended_str, "%Y-%m-%d").date()

                # Check if leave ended before today and user hasn't logged since
                if leave_ended_date < today_date and leave_ended_date >= last_logged_date:
                    # Update last_active_date if needed
                    current_last_active = data.get("last_active_date")
                    should_update_active = False
                    if not current_last_active:
                        should_update_active = True
                    else:
                        try:
                            current_last_active_date = datetime.strptime(current_last_active, "%Y-%m-%d").date()
                            if current_last_active_date < leave_ended_date:
                                should_update_active = True
                        except ValueError:
                            should_update_active = True

                    if should_update_active:
                        data["last_active_date"] = leave_ended_str
                        days_silent = (today_date - leave_ended_date).days
                        changed = True
                        log(f"Fallback: using leave_ended_at {leave_ended_str}, days_silent now {days_silent}")
            except ValueError as e:
                log(f"Warning: could not parse leave_ended_at: {e}")

    # --- Forward transitions (fast-forward to correct stage) ---
    # Skip forward transitions if --user-active: user just sent a message,
    # so they are active right now regardless of meal history.
    # Also skip if user is on leave — stage should remain frozen.
    if not args.user_active and not on_leave:
        # Calculate target stage directly from days_silent.
        # This avoids the one-step-per-cron problem where a user stuck at S1
        # due to a reset takes multiple cron cycles to reach the correct stage.
        def calc_target_stage(ds):
            """V2 stage calculation based on days_silent + recall counts."""
            if ds < STAGE_1_TO_2_DAYS:
                return 1   # 0-1 days → active
            if ds < 6:
                return 2   # 3-5 days → recall (Day 3-5)
            # days_silent >= 5 → check recall counts for S3/S4/S5
            weekly_count = data.get("weekly_recall_count", 0)
            monthly_count = data.get("monthly_recall_count", 0)
            if weekly_count < 3:
                return 3   # weekly recall phase
            if monthly_count < 3:
                return 4   # monthly recall phase
            return 5       # all recalls exhausted → silent

        target = calc_target_stage(days_silent)
        # Only move forward, never backward (backward is handled by reset above)
        if target > stage:
            old_stage = stage
            stage = target
            data["notification_stage"] = stage
            data["stage_changed_at"] = now.isoformat()
            # DO NOT reset last_recall_date here — pre-send-check uses it
            # for same-day dedup. Resetting it would let a second cron
            # through after the first already sent a recall message.
            # Reset stage-specific counters
            if stage >= 2:
                data["recall_2_sent"] = False
            if stage >= 3:
                data["weekly_recall_count"] = 0
            if stage >= 4:
                data["monthly_recall_count"] = 0
            changed = True
            log(f"FAST-FORWARD {old_stage} → {stage} (silent {days_silent} days)")

            # When entering S4+, disable personal crons immediately.
            if stage >= 4 and old_stage < 4:
                if _disable_user_crons(args.workspace_dir):
                    log("S4 entered — personal crons disabled")
                else:
                    log("S4 entered — WARNING: failed to disable personal crons (jobs.json not found)")

    # Stage 5 is permanent silence — no further transitions

    # Always persist days_silent for downstream consumers
    if data.get("days_silent") != days_silent:
        data["days_silent"] = days_silent
        changed = True

    if changed or not existed:
        save_engagement(args.workspace_dir, data)

    # Output: "stage days_silent" (e.g. "1 2" = Stage 1, 2 days silent)
    print(f"{stage} {days_silent}")


if __name__ == "__main__":
    main()
