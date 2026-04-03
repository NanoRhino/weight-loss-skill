#!/usr/bin/env python3
"""
onboarding-check.py — Check which onboarding fields are already filled.

Reads USER.md and health-profile.md from workspace, returns JSON
indicating which fields are filled vs missing, and which round to start from.

Usage:
    python3 onboarding-check.py --workspace /path/to/workspace

Output (JSON):
    {
        "fields": {
            "name": "filled",
            "motivation": "filled",
            "height": "filled",
            "weight": "filled",
            "age": "filled",
            "sex": "filled",
            "target_weight": "filled",
            "activity_level": "filled"
        },
        "skip_rounds": ["motivation", "body_data", "target_weight", "activity"],
        "next_round": "name",
        "summary": "All body data pre-filled. Only name is missing. After getting name, skip to diet/meal questions."
    }
"""

import argparse
import json
import os
import re
import sys


def read_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def parse_md_field(content, field_name):
    """Extract a markdown field value like '- **Name:** Ivan' -> 'Ivan'"""
    pattern = r"-\s*\*\*" + re.escape(field_name) + r":\*\*\s*(.*)"
    match = re.search(pattern, content, re.IGNORECASE)
    if match:
        val = match.group(1).strip()
        if val and val not in ("—", "-", "none", "n/a", "None", "N/A"):
            return val
    return None


def check_workspace(workspace_dir):
    user_md = read_file(os.path.join(workspace_dir, "USER.md"))
    health_md = read_file(os.path.join(workspace_dir, "health-profile.md"))

    # Check onboarding completed flag
    onboarding_completed = parse_md_field(user_md, "Onboarding Completed")
    if onboarding_completed and onboarding_completed.lower() == "true":
        return {
            "onboarding_completed": True,
            "fields": {},
            "skip_rounds": ["name", "motivation", "body_data", "target_weight", "activity"],
            "next_round": "complete",
            "summary": "Onboarding already completed (flag set). Skip onboarding entirely, proceed with normal chat.",
        }
    weight_json_path = os.path.join(workspace_dir, "data", "weight.json")
    has_weight_data = os.path.isfile(weight_json_path) and os.path.getsize(weight_json_path) > 5

    # Parse fields from USER.md
    name = parse_md_field(user_md, "Name")
    age = parse_md_field(user_md, "Age")
    sex = parse_md_field(user_md, "Sex")
    height = parse_md_field(user_md, "Height")

    # Parse fields from health-profile.md
    target_weight = parse_md_field(health_md, "Target Weight")
    motivation = parse_md_field(health_md, "Core Motivation")
    activity_level = parse_md_field(health_md, "Activity Level")

    fields = {
        "name": "filled" if name else "missing",
        "age": "filled" if age else "missing",
        "sex": "filled" if sex else "missing",
        "height": "filled" if height else "missing",
        "weight": "filled" if has_weight_data else "missing",
        "target_weight": "filled" if target_weight else "missing",
        "motivation": "filled" if motivation else "missing",
        "activity_level": "filled" if activity_level else "missing",
    }

    # Determine which rounds to skip
    skip_rounds = []
    if name:
        skip_rounds.append("name")
    if motivation:
        skip_rounds.append("motivation")
    if age and sex and height and has_weight_data:
        skip_rounds.append("body_data")
    if target_weight:
        skip_rounds.append("target_weight")
    if activity_level:
        skip_rounds.append("activity")

    # Determine next round
    round_order = [
        ("name", lambda: name),
        ("motivation", lambda: motivation),
        ("body_data", lambda: age and sex and height and has_weight_data),
        ("target_weight", lambda: target_weight),
        ("activity", lambda: activity_level),
    ]

    next_round = "complete"
    for round_name, check_fn in round_order:
        if not check_fn():
            next_round = round_name
            break

    # Build summary
    filled_count = sum(1 for v in fields.values() if v == "filled")
    total_count = len(fields)
    missing_fields = [k for k, v in fields.items() if v == "missing"]

    if next_round == "complete":
        summary = "All onboarding fields are filled. Skip entire onboarding and go directly to diet/meal questions via weight-loss-planner."
    elif len(missing_fields) == 1 and missing_fields[0] == "name":
        summary = "All body data pre-filled from app guide page. Only name is missing. After getting name, skip directly to diet/meal questions."
    elif filled_count == 0:
        summary = "No data pre-filled. Run full onboarding flow from Round 1."
    else:
        summary = "Partially filled (%d/%d). Missing: %s. Start from round: %s." % (
            filled_count, total_count, ", ".join(missing_fields), next_round
        )

    return {
        "onboarding_completed": False,
        "fields": fields,
        "skip_rounds": skip_rounds,
        "next_round": next_round,
        "summary": summary,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check onboarding progress")
    parser.add_argument("--workspace", required=True, help="Path to agent workspace")
    args = parser.parse_args()

    result = check_workspace(args.workspace)
    print(json.dumps(result, indent=2))
