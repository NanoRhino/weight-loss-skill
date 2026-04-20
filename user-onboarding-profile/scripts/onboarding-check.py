#!/usr/bin/env python3
"""
onboarding-check.py — Check which onboarding fields are already filled.

Reads USER.md, health-profile.md, weight.json, and PLAN.md from the workspace.
Returns JSON indicating field status and where to resume the onboarding flow.

Now covers the merged flow: profile → plan (Step 3) → diet preferences (Step 4)
→ diet template (Step 5 / onboarding_completed).

Usage:
    python3 onboarding-check.py --workspace /path/to/workspace

Output (JSON):
    {
        "fields": { "name": "filled", ... },
        "skip_rounds": ["motivation", "body_data", ...],
        "next_round": "name" | "motivation" | "body_data" | "target_weight" |
                      "activity" | "plan" | "diet_preferences" | "diet_template" |
                      "complete",
        "onboarding_completed": false,
        "summary": "..."
    }
"""

import argparse
import json
import os
import re


def read_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def parse_md_field(content, field_name):
    """Extract '- **Field:** value' → 'value'. Returns None if blank/dash."""
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

    # Onboarding Completed lives in health-profile.md > Automation
    onboarding_completed_val = parse_md_field(health_md, "Onboarding Completed")
    if onboarding_completed_val:
        return {
            "onboarding_completed": True,
            "fields": {},
            "skip_rounds": ["name", "motivation", "body_data", "target_weight",
                            "activity", "plan", "diet_preferences", "diet_template"],
            "next_round": "complete",
            "summary": "Onboarding completed. Skip entirely, proceed with normal chat.",
        }

    # --- Profile fields ---
    weight_json_path = os.path.join(workspace_dir, "data", "weight.json")
    has_weight_data = os.path.isfile(weight_json_path) and os.path.getsize(weight_json_path) > 5

    name = parse_md_field(user_md, "Name")
    age = parse_md_field(user_md, "Age")
    sex = parse_md_field(user_md, "Sex")
    height = parse_md_field(user_md, "Height")

    target_weight = parse_md_field(health_md, "Target Weight")
    motivation = parse_md_field(health_md, "Core Motivation")
    activity_level = parse_md_field(health_md, "Activity Level")

    # --- Post-profile states ---
    plan_md_path = os.path.join(workspace_dir, "PLAN.md")
    has_plan = os.path.isfile(plan_md_path) and os.path.getsize(plan_md_path) > 5

    diet_mode = parse_md_field(health_md, "Diet Mode")
    meal_schedule_filled = parse_md_field(health_md, "Meals per Day") is not None

    fields = {
        "name": "filled" if name else "missing",
        "age": "filled" if age else "missing",
        "sex": "filled" if sex else "missing",
        "height": "filled" if height else "missing",
        "weight": "filled" if has_weight_data else "missing",
        "target_weight": "filled" if target_weight else "missing",
        "motivation": "filled" if motivation else "missing",
        "activity_level": "filled" if activity_level else "missing",
        "plan": "filled" if has_plan else "missing",
        "diet_mode": "filled" if diet_mode else "missing",
        "meal_schedule": "filled" if meal_schedule_filled else "missing",
    }

    # --- Determine skip_rounds ---
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
    if has_plan:
        skip_rounds.append("plan")
    if diet_mode and meal_schedule_filled:
        skip_rounds.append("diet_preferences")

    # --- Determine next_round ---
    round_order = [
        ("name",             lambda: name),
        ("motivation",       lambda: motivation),
        ("body_data",        lambda: age and sex and height and has_weight_data),
        ("target_weight",    lambda: target_weight),
        ("activity",         lambda: activity_level),
        ("plan",             lambda: has_plan),
        ("diet_preferences", lambda: diet_mode and meal_schedule_filled),
        ("diet_template",    lambda: False),  # only skipped when onboarding_completed is set
    ]

    next_round = "complete"
    for round_name, check_fn in round_order:
        if not check_fn():
            next_round = round_name
            break

    # --- Summary ---
    profile_fields = ["name", "age", "sex", "height", "weight",
                      "target_weight", "motivation", "activity_level"]
    filled_profile = sum(1 for k in profile_fields if fields[k] == "filled")
    missing_fields = [k for k in profile_fields if fields[k] == "missing"]

    if next_round == "complete":
        summary = "All onboarding steps done. Proceed with normal chat."
    elif next_round == "diet_template":
        summary = "Profile and plan saved, diet preferences collected. Resume at Step 5: present diet template."
    elif next_round == "diet_preferences":
        summary = "Profile and plan saved. Resume at Step 4: collect diet mode, meal schedule, and food preferences."
    elif next_round == "plan":
        summary = "Profile complete. Resume at Step 3: generate and confirm weight loss plan."
    elif len(missing_fields) == 1 and missing_fields[0] == "name":
        summary = "All body data pre-filled. Only name missing. After getting name, skip to Step 3 (plan)."
    elif filled_profile == 0:
        summary = "No data pre-filled. Run full onboarding from Round 1."
    else:
        summary = "Partially filled (%d/%d profile fields). Missing: %s. Start from: %s." % (
            filled_profile, len(profile_fields), ", ".join(missing_fields), next_round
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
