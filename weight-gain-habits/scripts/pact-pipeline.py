#!/usr/bin/env python3
"""Weight-gain pact habit utilities.

Subcommands:
  check-escalation       Determine if a failed pact should escalate to weight-gain-strategy
  check-strict-eligibility  Determine if strict mode should be enabled for a pact
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone


def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_local_now(tz_offset):
    tz = timezone(timedelta(seconds=tz_offset))
    return datetime.now(tz)


def cmd_check_escalation(args):
    """Given a failed pact habit, check weight streak to decide escalation path.

    Returns:
      - escalate: true if streak >= 4 (hand off to weight-gain-strategy significant)
      - streak: current consecutive weight increases
      - action: "escalate_significant" | "offer_smaller_pact"
    """
    tz_offset = args.tz_offset
    local_now = get_local_now(tz_offset)

    # Load recent weight readings (28 days)
    end_date = local_now.strftime("%Y-%m-%d")
    start_date = (local_now - timedelta(days=28)).strftime("%Y-%m-%d")

    raw = load_json(os.path.join(args.data_dir, "weight.json"))
    readings = []
    for k, v in sorted(raw.items()):
        d = k[:10]
        if start_date <= d <= end_date:
            val = v.get("value", v) if isinstance(v, dict) else v
            readings.append({"date": d, "value": float(val)})

    if len(readings) < 2:
        print(json.dumps({
            "escalate": False,
            "streak": 0,
            "action": "offer_smaller_pact",
            "reason": "insufficient_data",
        }, indent=2))
        return

    # Count consecutive increases from most recent backwards
    streak = 0
    for i in range(len(readings) - 1, 0, -1):
        if readings[i]["value"] > readings[i - 1]["value"]:
            streak += 1
        else:
            break

    escalate = streak >= 4
    result = {
        "escalate": escalate,
        "streak": streak,
        "action": "escalate_significant" if escalate else "offer_smaller_pact",
    }
    if escalate:
        result["recommendation"] = (
            "Weight streak is {0}. Escalate to weight-gain-strategy "
            "Interactive Flow (significant path) for full reassessment."
        ).format(streak)
    else:
        result["recommendation"] = (
            "Weight streak is {0}. Stay in weight-gain-habits — "
            "offer a smaller/easier pact."
        ).format(streak)

    print(json.dumps(result, indent=2))


def cmd_check_strict_eligibility(args):
    """Given analyze top_factors, determine if strict mode should be enabled.

    Returns:
      - strict: true if both logging_gaps and calorie_surplus are in top_factors
    """
    top_factors = json.loads(args.top_factors)

    has_logging_gaps = "logging_gaps" in top_factors
    has_calorie_surplus = "calorie_surplus" in top_factors

    result = {
        "strict": has_logging_gaps and has_calorie_surplus,
        "logging_gaps": has_logging_gaps,
        "calorie_surplus": has_calorie_surplus,
    }
    print(json.dumps(result, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Weight-gain pact pipeline")
    sub = parser.add_subparsers(dest="command")

    # check-escalation
    ce = sub.add_parser("check-escalation",
                        help="Check if failed pact should escalate")
    ce.add_argument("--data-dir", required=True)
    ce.add_argument("--tz-offset", type=int, default=0)

    # check-strict-eligibility
    cs = sub.add_parser("check-strict-eligibility",
                        help="Check if strict mode should be enabled")
    cs.add_argument("--top-factors", required=True,
                    help='JSON array of top_factors from analyze')

    args = parser.parse_args()

    if args.command == "check-escalation":
        cmd_check_escalation(args)
    elif args.command == "check-strict-eligibility":
        cmd_check_strict_eligibility(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
