#!/usr/bin/env python3
"""
migrate-cron-tz-dups.py — One-shot repair for existing reminder cron jobs that
were created with the wrong timezone (silently defaulted to Asia/Shanghai instead
of the user's real zone) and/or were duplicated by a failed-then-retried batch.

WHY A REBUILD (not an in-place --tz edit):
  Field analysis of affected agents showed the broken jobs are not merely
  mislabeled — the cron EXPRESSIONS themselves are inconsistent. In the
  failed-then-retried batch, the agent hand-created some jobs by (incorrectly)
  converting clock times (e.g. lunch 2:30 PM was stored as `15 2` = 02:15 instead
  of `15 14` = 14:15; dinner 6:30 PM as `15 6` = 06:15). So a blanket tz-label
  swap would leave afternoon/evening reminders firing at the wrong hour. The only
  reliable repair is to DELETE the broken system crons and RE-CREATE them from
  `health-profile.md` via the (now fixed) batch-create-reminders.sh, which
  deterministically computes the correct local expression AND passes the correct
  --tz from USER.md.

Per agent, this script:
  1. Lists the agent's recurring (kind=cron) SYSTEM jobs (never `[custom]`).
  2. Flags the agent as NEEDS-REBUILD if any such job has schedule.tz != the
     agent's USER.md Timezone, OR any system job name is duplicated.
  3. In --apply mode: removes ALL of the agent's recurring system crons
     (`openclaw cron rm <id>`), then runs batch-create-reminders.sh
     --only meal,weight,report,pattern,tips --skip-existing to rebuild them
     correctly. One-shot nudges (kind=at) and `[custom]` jobs are left untouched.

DRY-RUN BY DEFAULT. Mutations use only the gateway CLI (`cron rm` +
batch-create-reminders.sh, which calls `cron add`) — safe against a running
gateway; no direct store writes.

The set of names treated as "system recurring" (safe to remove + rebuild):
  Breakfast reminder, Lunch reminder, Dinner reminder, Snack reminder,
  Weight check-in reminder, Weight morning followup, Weekly report,
  Weekly insight, Product tips, Diet pattern detection, Periodic recalc (4-week).
Any other non-[custom] recurring job is REPORTED but NOT removed (operator
decides), so we never silently destroy a job we don't own.

Usage:
  python3 migrate-cron-tz-dups.py                     # dry-run, all agents
  python3 migrate-cron-tz-dups.py --agent 050184      # dry-run, one agent
  python3 migrate-cron-tz-dups.py --agent 050184 --apply
  python3 migrate-cron-tz-dups.py --apply             # apply to all (after verifying)

Options:
  --state-dir <path>   OpenClaw home (cwd for `openclaw cron`). Default: resolve
                       OPENCLAW_STATE_DIR -> OPENCLAW_HOME -> ~/.openclaw.
  --workspaces <path>  Per-agent workspaces dir.
                       Default: <state-dir>/workspace-nutritionist
  --channel <ch>       Delivery channel passed to batch-create-reminders.sh on
                       rebuild. Default: twilio.
  --agent <id>         Limit to one agent id (workspace dir name).
  --apply              Perform removals + rebuild (otherwise dry-run).
  --json               Emit a machine-readable summary to stdout.

Exit 0 on success (including dry-run); 1 on a hard error.

Runs on Python 3.9 (bare `python3` on EC2): `from __future__ import annotations`
defers annotation evaluation so PEP 604 (`X | Y`) annotation syntax is safe.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

# Recurring system reminder names this migration owns (safe to remove + rebuild).
SYSTEM_RECURRING_NAMES = {
    "Breakfast reminder", "Lunch reminder", "Dinner reminder", "Snack reminder",
    "Weight check-in reminder", "Weight morning followup",
    "Weekly report", "Weekly insight", "Product tips",
    "Diet pattern detection", "Periodic recalc (4-week)",
}

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_BATCH_SCRIPT = os.path.join(_SCRIPT_DIR, "batch-create-reminders.sh")


def resolve_state_dir(explicit):
    if explicit:
        return explicit
    env = os.environ.get("OPENCLAW_STATE_DIR")
    if env:
        return env
    home = os.environ.get("OPENCLAW_HOME")
    if home and os.path.isdir(home):
        return home
    return os.path.expanduser("~/.openclaw")


def read_usermd_timezone(workspace):
    path = os.path.join(workspace, "USER.md")
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                m = re.match(r"^- \*\*Timezone:\*\*\s*(.+?)\s*$", line)
                if m:
                    return m.group(1).strip() or None
    except OSError:
        return None
    return None


def list_jobs(state_dir, agent):
    """Return the agent's cron jobs, or None if listing FAILED (fail closed).

    `openclaw cron list` has no --agent flag and omits disabled jobs without
    --all; pass --all and filter by agentId in Python.
    """
    try:
        r = subprocess.run(
            ["openclaw", "cron", "list", "--all", "--json"],
            capture_output=True, text=True, timeout=60, cwd=state_dir,
        )
    except Exception as e:
        print(f"  [{agent}] ERROR running cron list: {e}", file=sys.stderr)
        return None
    if r.returncode != 0:
        print(f"  [{agent}] ERROR cron list rc={r.returncode}: {r.stderr.strip()}",
              file=sys.stderr)
        return None
    try:
        data = json.loads(r.stdout)
    except Exception as e:
        print(f"  [{agent}] ERROR parsing cron list JSON: {e}", file=sys.stderr)
        return None
    jobs = data.get("jobs", data) if isinstance(data, dict) else data
    return [j for j in (jobs or []) if j.get("agentId") == agent]


def is_recurring(job):
    return (job.get("schedule", {}) or {}).get("kind") == "cron"


def cron_rm(state_dir, job_id):
    try:
        r = subprocess.run(["openclaw", "cron", "rm", job_id],
                           capture_output=True, text=True, timeout=30, cwd=state_dir)
        return r.returncode == 0
    except Exception:
        return False


def rebuild(state_dir, workspace, agent, channel):
    """Re-create system reminders from health-profile.md via the fixed batch script."""
    try:
        r = subprocess.run(
            ["bash", _BATCH_SCRIPT,
             "--agent", agent, "--channel", channel,
             "--workspace", workspace,
             "--only", "meal,weight,report,pattern,tips",
             "--skip-existing"],
            capture_output=True, text=True, timeout=300, cwd=state_dir,
        )
        ok = r.returncode == 0
        if not ok:
            print(f"  [{agent}] rebuild stderr:\n{r.stderr}", file=sys.stderr)
        return ok
    except Exception as e:
        print(f"  [{agent}] ERROR running batch rebuild: {e}", file=sys.stderr)
        return False


def process_agent(state_dir, workspace, agent, channel, apply):
    summary = {
        "agent": agent, "tz_expected": None, "listed": False,
        "needs_rebuild": False, "wrong_tz": [], "duplicates": [],
        "would_remove": [], "unowned_recurring": [],
        "removed": [], "rebuilt": False, "errors": [],
    }
    tz_expected = read_usermd_timezone(workspace)
    summary["tz_expected"] = tz_expected
    if not tz_expected:
        summary["errors"].append("no USER.md Timezone — skipped (cannot determine correct zone)")
        return summary

    jobs = list_jobs(state_dir, agent)
    if jobs is None:
        summary["errors"].append("cron list failed — skipped (fail closed)")
        return summary
    summary["listed"] = True

    recurring = [j for j in jobs if is_recurring(j)]
    owned = [j for j in recurring
             if (j.get("name") or "") in SYSTEM_RECURRING_NAMES]
    # Recurring, non-custom, but a name we don't own -> report only.
    for j in recurring:
        nm = j.get("name") or ""
        if nm.startswith("[custom]"):
            continue
        if nm not in SYSTEM_RECURRING_NAMES:
            summary["unowned_recurring"].append({"name": nm, "id": j.get("id", "")})

    # Detect wrong tz among owned jobs.
    for j in owned:
        cur_tz = (j.get("schedule", {}) or {}).get("tz", "")
        if cur_tz != tz_expected:
            summary["wrong_tz"].append({
                "name": j.get("name", ""), "id": j.get("id", ""),
                "from_tz": cur_tz, "expr": (j.get("schedule", {}) or {}).get("expr", ""),
            })

    # Detect duplicate names among owned jobs.
    by_name = {}
    for j in owned:
        by_name.setdefault(j.get("name", ""), []).append(j)
    for nm, group in by_name.items():
        if len(group) > 1:
            summary["duplicates"].append({"name": nm, "count": len(group)})

    summary["needs_rebuild"] = bool(summary["wrong_tz"] or summary["duplicates"])
    if not summary["needs_rebuild"]:
        return summary

    # Plan: remove ALL owned recurring jobs, then rebuild from health-profile.
    summary["would_remove"] = [{"name": j.get("name", ""), "id": j.get("id", "")}
                               for j in owned]

    if not apply:
        return summary

    all_removed = True
    for j in owned:
        jid = j.get("id", "")
        if cron_rm(state_dir, jid):
            summary["removed"].append({"name": j.get("name", ""), "id": jid})
        else:
            all_removed = False
            summary["errors"].append(f"rm failed for {j.get('name','')} {jid}")
    if not all_removed:
        summary["errors"].append("aborting rebuild: not all old jobs removed")
        return summary

    summary["rebuilt"] = rebuild(state_dir, workspace, agent, channel)
    if not summary["rebuilt"]:
        summary["errors"].append("rebuild via batch-create-reminders.sh failed")
    return summary


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--state-dir")
    p.add_argument("--workspaces")
    p.add_argument("--channel", default="twilio")
    p.add_argument("--agent")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    state_dir = resolve_state_dir(args.state_dir)
    workspaces_dir = args.workspaces or os.path.join(state_dir, "workspace-nutritionist")
    mode = "APPLY" if args.apply else "DRY-RUN"

    if not os.path.isdir(workspaces_dir):
        print(f"ERROR: workspaces dir not found: {workspaces_dir}", file=sys.stderr)
        return 1

    if args.agent:
        agents = [args.agent]
    else:
        agents = sorted(
            d for d in os.listdir(workspaces_dir)
            if os.path.isdir(os.path.join(workspaces_dir, d))
        )

    print(f"== migrate-cron-tz-dups [{mode}] ==")
    print(f"state-dir : {state_dir}")
    print(f"workspaces: {workspaces_dir}")
    print(f"channel   : {args.channel}")
    print(f"agents    : {len(agents)}")
    print("")

    results = []
    n_need = n_rebuilt = n_err = 0
    for agent in agents:
        ws = os.path.join(workspaces_dir, agent)
        s = process_agent(state_dir, ws, agent, args.channel, args.apply)
        results.append(s)
        interesting = (s["needs_rebuild"] or s["errors"] or s["unowned_recurring"])
        if not interesting:
            continue
        print(f"[{agent}] tz_expected={s['tz_expected']}")
        for d in s["duplicates"]:
            print(f"  DUP   '{d['name']}' x{d['count']}")
        for t in s["wrong_tz"]:
            print(f"  TZ    '{t['name']}' {t['id']} tz={t['from_tz'] or '(none)'}  [{t['expr']}]")
        for u in s["unowned_recurring"]:
            print(f"  NOTE  unowned recurring (not touched): '{u['name']}' {u['id']}")
        if s["needs_rebuild"]:
            n_need += 1
            if args.apply:
                for r in s["removed"]:
                    print(f"  RM    removed: '{r['name']}' {r['id']}")
                print(f"  REBUILD {'OK' if s['rebuilt'] else 'FAILED'}")
                if s["rebuilt"]:
                    n_rebuilt += 1
            else:
                print(f"  PLAN  would remove {len(s['would_remove'])} system cron(s) and "
                      f"rebuild from health-profile.md (correct tz + expressions)")
        for e in s["errors"]:
            print(f"  ERR   {e}")
            n_err += 1
        print("")

    print("=====================================")
    if args.apply:
        print(f"APPLY: agents rebuilt={n_rebuilt}/{n_need}  errors={n_err}")
    else:
        print(f"DRY-RUN: agents needing rebuild={n_need}  errors={n_err}")
        if n_need:
            print("Re-run with --apply (start with a single --agent <id> to verify).")
    print("=====================================")

    if args.json:
        print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
