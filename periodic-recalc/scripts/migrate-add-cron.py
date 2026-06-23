#!/usr/bin/env python3
"""
One-time migration script to add "Periodic recalc" cron jobs to existing agents.

Scans all existing wechat-dm-* / wecom-dm-* agents in jobs.json and creates a
"Periodic recalc" job for those missing one, using the same delivery/schedule.tz
as their existing "Weekly report" job.

Usage:
  python3 migrate-add-cron.py [--dry-run] [--apply] [--workspace-root <path>] [--only-agent <agentId>]

Options:
  --dry-run          (default) Print diff without writing files
  --apply            Write changes to jobs.json (backs up to jobs.json.bak.<timestamp> first)
  --workspace-root   Path to workspace root (default: auto-detect from script location)
  --only-agent       Only process a specific agent ID (for testing)

Output:
  - Prints summary: how many agents scanned, how many skipped (already have), how many created
  - In --apply mode, backs up jobs.json first and writes the updated version
"""

import argparse
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path


def find_jobs_json(workspace_root: Path | None) -> Path:
    """Locate .openclaw-gateway/cron/jobs.json from workspace root."""
    if workspace_root:
        jobs_path = workspace_root / ".openclaw-gateway" / "cron" / "jobs.json"
    else:
        # Auto-detect: script is in skills/periodic-recalc/scripts/
        # workspace root is 3 levels up
        script_dir = Path(__file__).parent
        workspace_root = script_dir.parent.parent.parent.parent
        jobs_path = workspace_root / ".openclaw-gateway" / "cron" / "jobs.json"

    if not jobs_path.exists():
        print(f"ERROR: jobs.json not found at {jobs_path}", file=sys.stderr)
        sys.exit(1)

    return jobs_path


def load_jobs(jobs_path: Path) -> list[dict]:
    """Load jobs.json and return list of job dicts."""
    with open(jobs_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data.get('jobs', [])


def save_jobs(jobs_path: Path, jobs: list[dict], backup: bool = True):
    """Save jobs list back to jobs.json, optionally backing up first."""
    if backup:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = jobs_path.with_suffix(f".json.bak.{timestamp}")
        backup_path.write_text(jobs_path.read_text(encoding='utf-8'), encoding='utf-8')
        print(f"Backed up to {backup_path}")

    data = {"jobs": jobs}
    with open(jobs_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def group_by_agent(jobs: list[dict]) -> dict[str, list[dict]]:
    """Group jobs by agentId. Returns {agentId: [job, job, ...]}."""
    grouped = {}
    for job in jobs:
        agent_id = job.get('agentId')
        if not agent_id:
            continue
        grouped.setdefault(agent_id, []).append(job)
    return grouped


def has_periodic_recalc(jobs: list[dict]) -> bool:
    """Check if agent already has a Periodic recalc job."""
    for job in jobs:
        name = job.get('name', '')
        message = job.get('payload', {}).get('message', '')
        if 'Periodic recalc' in name or 'periodic-recalc.py' in message:
            return True
    return False


def find_weekly_report_job(jobs: list[dict]) -> dict | None:
    """Find the Weekly report job to use as template."""
    for job in jobs:
        if job.get('name') == 'Weekly report':
            return job
    return None


def create_periodic_recalc_job(template_job: dict, agent_id: str) -> dict:
    """
    Create a new Periodic recalc job based on the Weekly report template.

    New job structure:
    - name: "Periodic recalc"
    - schedule.expr: "10 21 * * 0"
    - schedule.tz: same as template
    - sessionTarget: "isolated"
    - wakeMode: "now"
    - payload.kind: "agentTurn"
    - payload.message: with 🔄 header
    - delivery: same as template
    - id: new UUID
    - createdAtMs: current timestamp
    """
    now_ms = int(datetime.now().timestamp() * 1000)

    # Extract template values
    template_tz = template_job.get('schedule', {}).get('tz', 'Asia/Shanghai')
    template_delivery = template_job.get('delivery', {})

    # Build message with header constraint
    message = """🔄——周期性调整——🔄

Run periodic-recalc skill: python3 {skillsDir}/periodic-recalc/scripts/periodic-recalc.py --workspace {workspaceDir} --planner-calc {skillsDir}/weight-loss-planner/scripts/planner-calc.py. Then run diet-mode-review.py if recalculated."""

    new_job = {
        "id": str(uuid.uuid4()),
        "agentId": agent_id,
        "name": "Periodic recalc",
        "schedule": {
            "expr": "10 21 * * 0",
            "tz": template_tz
        },
        "sessionTarget": "isolated",
        "wakeMode": "now",
        "payload": {
            "kind": "agentTurn",
            "message": message
        },
        "delivery": template_delivery,
        "createdAtMs": now_ms
    }

    return new_job


def main():
    parser = argparse.ArgumentParser(description='Migrate: add Periodic recalc cron jobs')
    parser.add_argument('--dry-run', action='store_true', default=True,
                        help='Print diff without writing (default: true)')
    parser.add_argument('--apply', action='store_true',
                        help='Write changes to jobs.json')
    parser.add_argument('--workspace-root', type=Path, default=None,
                        help='Path to workspace root (default: auto-detect)')
    parser.add_argument('--only-agent', type=str, default=None,
                        help='Only process a specific agent ID')
    args = parser.parse_args()

    # If --apply is set, override --dry-run default
    if args.apply:
        args.dry_run = False

    jobs_path = find_jobs_json(args.workspace_root)
    print(f"Loading jobs from {jobs_path}")

    jobs = load_jobs(jobs_path)
    print(f"Total jobs: {len(jobs)}")

    grouped = group_by_agent(jobs)

    # Filter to wechat-dm-* / wecom-dm-* agents
    target_agents = {
        agent_id: agent_jobs
        for agent_id, agent_jobs in grouped.items()
        if agent_id.startswith('wechat-dm-') or agent_id.startswith('wecom-dm-')
    }

    if args.only_agent:
        if args.only_agent in target_agents:
            target_agents = {args.only_agent: target_agents[args.only_agent]}
        else:
            print(f"ERROR: Agent {args.only_agent} not found or not a wechat/wecom agent", file=sys.stderr)
            sys.exit(1)

    print(f"Target agents (wechat/wecom): {len(target_agents)}")

    # Stats
    scanned = 0
    skipped = 0
    created = 0
    errors = 0

    new_jobs = []

    for agent_id, agent_jobs in target_agents.items():
        scanned += 1

        # Check if already has Periodic recalc
        if has_periodic_recalc(agent_jobs):
            skipped += 1
            print(f"  SKIP {agent_id}: already has Periodic recalc job")
            continue

        # Find Weekly report job as template
        template = find_weekly_report_job(agent_jobs)
        if not template:
            errors += 1
            print(f"  ERROR {agent_id}: no Weekly report job found (can't determine tz/delivery)", file=sys.stderr)
            continue

        # Create new job
        new_job = create_periodic_recalc_job(template, agent_id)
        new_jobs.append(new_job)
        created += 1

        print(f"  CREATE {agent_id}: {new_job['name']} @ {new_job['schedule']['expr']} {new_job['schedule']['tz']}")

    print()
    print("=" * 60)
    print(f"SUMMARY:")
    print(f"  Scanned:  {scanned} agents")
    print(f"  Skipped:  {skipped} (already have Periodic recalc)")
    print(f"  Created:  {created}")
    print(f"  Errors:   {errors}")
    print("=" * 60)

    if new_jobs and not args.dry_run:
        print()
        print("Writing changes to jobs.json...")
        all_jobs = jobs + new_jobs
        save_jobs(jobs_path, all_jobs, backup=True)
        print(f"✓ Added {len(new_jobs)} new jobs")
    elif new_jobs and args.dry_run:
        print()
        print("DRY-RUN: No changes written. Use --apply to write.")
        print()
        print("Would add these jobs:")
        for job in new_jobs:
            print(f"  - {job['agentId']}: {job['name']} @ {job['schedule']['expr']}")
    else:
        print()
        print("No new jobs to create.")


if __name__ == '__main__':
    main()
