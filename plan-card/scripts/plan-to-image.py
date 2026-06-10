#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["weasyprint", "pymupdf"]
# ///
"""
plan-to-image.py — Deterministic plan-card renderer for SMS/MMS delivery.

Turns handoff profile data (JSON) into:
  (a) a branded NanoRhino plan card PNG suitable for MMS, and
  (b) PLAN.md markdown content (returned in stdout JSON, not written to disk).

No LLM involved. Plan CONTENT follows the canonical Step-3 spec in
user-onboarding-profile/SKILL.md ("Step 3：生成并确认减脂方案"):
  - a SINGLE daily calorie target (no band),
  - daily calorie deficit (~XXX),
  - weekly loss rate,
  - a single completion month + year,
  - NO macro split at the plan stage (macros come later, at diet-mode
    selection).

All math comes from weight-loss-planner/scripts/planner-calc.py invoked as a
SUBPROCESS — `forward-calc --mode balanced` is the canonical calculation
(pace table, safety floor max(BMR, 1000), floor clamping, completion date).
Its interface is not modified.

CLI contract (invoked by the openclaw-infra Twilio extension — frozen):

  python3 plan-card/scripts/plan-to-image.py \
      --input <input.json> --output <out.png> [--width 1080] [--max-bytes 614400]

stdout on success (single JSON line):
  {"ok": true, "png": "<abs path>", "bytes": N, "plan": {...}, "plan_markdown": "..."}
On failure: non-zero exit, {"ok": false, "error": "..."} on stdout, details on stderr.

System dependencies: WeasyPrint needs pango/cairo/gdk-pixbuf system libraries
(on EC2/Amazon Linux: `sudo dnf install pango cairo gdk-pixbuf2`;
on Ubuntu: `sudo apt-get install libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0`).
"""

import argparse
import json
import string
import subprocess
import sys
import traceback
from datetime import date, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
PLANNER_CALC = REPO_ROOT / "weight-loss-planner" / "scripts" / "planner-calc.py"
TEMPLATE = SCRIPT_DIR.parent / "templates" / "plan-card.html"

# Fallback when goal_weight_kg is null and intent == "lose": assume the most
# conservative pace-table default (0.35 kg/week → ≈385 kcal/day deficit) and
# show the target without a completion date ("unlock" prompt instead).
NO_GOAL_RATE_KG = 0.35
# Mild deterministic adjustments for the intents the Step-3 spec doesn't model.
RECOMP_DEFICIT_KCAL = 200
GAIN_RATE_KG_PER_WEEK = 0.25  # lean gain default → ≈275 kcal/day surplus

VALID_SEX = {"male", "female"}
VALID_INTENT = {"lose", "maintain", "recomp", "gain"}

# Regions using the Asian BMI classification (per Step-3 spec: zh/ja/ko
# regions or languages → asian, else WHO).
ASIAN_BMI_COUNTRIES = {"CN", "TW", "HK", "MO", "SG", "JP", "KR"}
ASIAN_BMI_LANGUAGES = {"zh", "ja", "ko"}

MIN_RENDER_WIDTH = 480  # don't shrink the PNG below this when fitting max-bytes


# ---------------------------------------------------------------------------
# planner-calc subprocess wrapper
# ---------------------------------------------------------------------------

def run_planner(*args) -> dict:
    """Invoke planner-calc.py as a subprocess and parse its JSON output."""
    cmd = [sys.executable, str(PLANNER_CALC), *[str(a) for a in args]]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"planner-calc {args[0]} failed (exit {proc.returncode}): "
            f"{proc.stderr.strip() or proc.stdout.strip()}"
        )
    return json.loads(proc.stdout)


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

def validate_input(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("Input JSON must be an object")

    profile = data.get("profile")
    if not isinstance(profile, dict):
        raise ValueError("Missing 'profile' object")

    for field in ("sex", "age_years", "height_cm", "weight_kg"):
        if profile.get(field) in (None, ""):
            raise ValueError(f"Missing required profile field: {field}")

    if profile["sex"] not in VALID_SEX:
        raise ValueError(f"profile.sex must be one of {sorted(VALID_SEX)}")

    intent = profile.get("intent") or "lose"
    if intent not in VALID_INTENT:
        raise ValueError(f"profile.intent must be one of {sorted(VALID_INTENT)}")
    profile["intent"] = intent

    profile["age_years"] = int(profile["age_years"])
    profile["height_cm"] = float(profile["height_cm"])
    profile["weight_kg"] = float(profile["weight_kg"])
    if profile.get("goal_weight_kg") is not None:
        profile["goal_weight_kg"] = float(profile["goal_weight_kg"])

    if profile["height_cm"] <= 0 or profile["weight_kg"] <= 0:
        raise ValueError("height_cm and weight_kg must be positive")

    tdee = data.get("tdee")
    if not isinstance(tdee, dict):
        raise ValueError("Missing 'tdee' object")
    for field in ("recommended", "bmr"):
        if tdee.get(field) in (None, ""):
            raise ValueError(f"Missing required tdee field: {field}")
    tdee["recommended"] = round(float(tdee["recommended"]))
    tdee["bmr"] = float(tdee["bmr"])
    tdee["low"] = round(float(tdee.get("low") or tdee["recommended"] - 100))
    tdee["high"] = round(float(tdee.get("high") or tdee["recommended"] + 100))

    locale = data.get("locale") or {}
    country = (locale.get("country") or "US").upper()
    units = locale.get("units") or ("imperial" if country == "US" else "metric")
    if units not in ("imperial", "metric"):
        raise ValueError("locale.units must be 'imperial' or 'metric'")
    language = (locale.get("language") or "").lower()
    data["locale"] = {"country": country, "units": units, "language": language}
    return data


def resolve_activity(profile: dict) -> tuple:
    """Resolve the planner-calc activity level (and whether it was assumed).

    Falls back to daily steps when activity_level is missing, then to
    lightly_active (the weight-loss-planner default for unclear activity).
    """
    level = profile.get("activity_level")
    if level in ("sedentary", "lightly_active", "moderately_active",
                 "very_active", "extremely_active"):
        return level, False
    steps = profile.get("daily_steps")
    if steps is not None:
        steps = float(steps)
        if steps < 5000:
            return "sedentary", True
        if steps < 8000:
            return "lightly_active", True
        if steps < 12000:
            return "moderately_active", True
        return "very_active", True
    return "lightly_active", True


def bmi_standard_for(locale: dict) -> str:
    if locale["country"] in ASIAN_BMI_COUNTRIES:
        return "asian"
    if locale["language"][:2] in ASIAN_BMI_LANGUAGES:
        return "asian"
    return "who"


# ---------------------------------------------------------------------------
# Plan computation
# ---------------------------------------------------------------------------

def compute_plan(profile: dict, tdee: dict, locale: dict) -> dict:
    weight = profile["weight_kg"]
    goal = profile.get("goal_weight_kg")
    intent = profile["intent"]
    activity, activity_assumed = resolve_activity(profile)
    bmi_std = bmi_standard_for(locale)

    plan = {
        "intent": intent,
        "weight_kg": weight,
        "goal_weight_kg": goal,
        "activity": activity,
        "activity_assumed": activity_assumed,
        "bmi_standard": bmi_std,
        "rate_kg_per_week": None,
        "daily_deficit": None,
        "weeks": None,
        "estimated_completion": None,
        "timeline_locked": False,
        "floor_clamped": False,
    }

    # Treat a goal at/above current weight under 'lose' as maintenance.
    if intent == "lose" and goal is not None and goal >= weight:
        intent = plan["intent"] = "maintain"

    if intent == "lose" and goal is not None:
        # Canonical path: trust planner-calc forward-calc end to end.
        fc = run_planner(
            "forward-calc",
            "--weight", weight, "--height", profile["height_cm"],
            "--age", profile["age_years"], "--sex", profile["sex"],
            "--activity", activity, "--target-weight", goal,
            "--mode", "balanced", "--bmi-standard", bmi_std,
        )
        plan.update({
            "bmr": fc["bmr"],
            "tdee": fc["tdee"]["tdee"],
            "calorie_floor": fc["calorie_floor"],
            "floor_clamped": fc["floor_clamped"],
            "to_lose_kg": fc["to_lose_kg"],
            "rate_kg_per_week": fc["rate_kg_per_week"],
            "daily_deficit": fc["daily_deficit"],
            "daily_cal": fc["daily_cal"],
            "weeks": fc["weeks"],
            "estimated_completion": fc["estimated_completion"],
            "bmi_current": fc["bmi_current"],
            "bmi_current_class": fc["bmi_current_class"],
            "bmi_target": fc["bmi_target"],
            "bmi_target_class": fc["bmi_target_class"],
            "maintenance_tdee": fc["maintenance_tdee"],
        })
        return plan

    # The remaining paths can't use forward-calc (it requires a target
    # weight), so they anchor on the handoff TDEE/BMR; the safety floor
    # still comes from planner-calc.
    bmr = tdee["bmr"]
    tdee_rec = tdee["recommended"]
    floor = run_planner("safety-floor", "--bmr", bmr)["calorie_floor"]
    bmi = run_planner("bmi", "--weight", weight,
                      "--height", profile["height_cm"], "--standard", bmi_std)
    plan.update({
        "bmr": bmr,
        "tdee": tdee_rec,
        "calorie_floor": floor,
        "bmi_current": bmi["bmi"],
        "bmi_current_class": bmi["classification"],
    })

    if intent == "lose":  # goal_weight_kg is null → unlock fallback
        rate = NO_GOAL_RATE_KG
        ct = run_planner("calorie-target", "--tdee", tdee_rec, "--rate-kg", rate)
        daily_cal = ct["daily_cal"]
        deficit = ct["daily_deficit"]
        if daily_cal < floor:
            # Same clamping rule planner-calc applies: floor wins, then
            # back-calculate the max safe rate from the floor.
            plan["floor_clamped"] = True
            daily_cal = floor
            deficit = tdee_rec - floor
            rate = round(deficit / 1100, 2)
        plan.update({
            "daily_cal": daily_cal,
            "daily_deficit": deficit,
            "rate_kg_per_week": rate,
            "timeline_locked": True,
        })

    elif intent == "maintain":
        plan["daily_cal"] = max(tdee_rec, floor)

    elif intent == "recomp":
        daily_cal = max(tdee_rec - RECOMP_DEFICIT_KCAL, floor)
        plan.update({
            "daily_cal": daily_cal,
            "daily_deficit": tdee_rec - daily_cal,
        })

    else:  # gain
        rate = GAIN_RATE_KG_PER_WEEK
        surplus = round(rate * 1100)
        plan.update({
            "daily_cal": tdee_rec + surplus,
            "daily_deficit": -surplus,
            "rate_kg_per_week": rate,
        })
        if goal is not None and goal > weight:
            weeks = round((goal - weight) / rate, 1)
            plan["weeks"] = weeks
            plan["estimated_completion"] = (
                date.today() + timedelta(days=round(weeks * 7))
            ).isoformat()
        else:
            plan["timeline_locked"] = True

    return plan


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def fmt_weight(kg: float, units: str) -> str:
    if units == "imperial":
        return f"{round(kg * 2.205)} lb"
    return f"{round(kg, 1):g} kg"


def fmt_height(cm: float, units: str) -> str:
    if units == "imperial":
        total_in = cm / 2.54
        feet = int(total_in // 12)
        inches = round(total_in - feet * 12)
        if inches == 12:
            feet, inches = feet + 1, 0
        return f"{feet}'{inches}\""
    return f"{round(cm):d} cm"


def fmt_rate(rate_kg: float, units: str) -> str:
    if units == "imperial":
        return f"{round(rate_kg * 2.205, 1):g} lb/wk"
    return f"{round(rate_kg, 2):g} kg/wk"


def cal_unit(country: str) -> str:
    return "Cal" if country == "US" else "kcal"


def fmt_num(n) -> str:
    return f"{round(n):,}"


def fmt_month_year(iso_date: str) -> str:
    return date.fromisoformat(iso_date).strftime("%B %Y")


def fmt_month_year_short(iso_date: str) -> str:
    return date.fromisoformat(iso_date).strftime("%b %Y")


PLAN_TITLES = {
    "lose": "Your Weight Loss Plan",
    "maintain": "Your Maintenance Plan",
    "recomp": "Your Recomposition Plan",
    "gain": "Your Lean Gain Plan",
}

ACTIVITY_DESCRIPTIONS = {
    "sedentary": "mostly sitting during the day",
    "lightly_active": "on your feet part of the day, light exercise",
    "moderately_active": "regular exercise most weeks",
    "very_active": "hard exercise most days",
    "extremely_active": "very hard daily training",
}

HABITS = {
    "lose": [
        "Protein at every meal",
        "Log it before you eat it",
        "10-minute walk after dinner",
    ],
    "maintain": [
        "Weigh in once a week, same time",
        "Protein at every meal",
        "Keep the walks — they're working",
    ],
    "recomp": [
        "Lift 3x a week — progress the weights",
        "Protein at every meal",
        "Sleep 7+ hours; muscle is built at night",
    ],
    "gain": [
        "Eat on a schedule — don't skip meals",
        "Protein at every meal",
        "Lift 3x a week — progress the weights",
    ],
}


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------

def build_template_vars(plan: dict, profile: dict, locale: dict) -> dict:
    units = locale["units"]
    cu = cal_unit(locale["country"])
    intent = plan["intent"]

    stats_bits = [fmt_weight(profile["weight_kg"], units)]
    if plan.get("goal_weight_kg") is not None and intent != "maintain":
        stats_bits[0] += f"  →  {fmt_weight(plan['goal_weight_kg'], units)}"
    stats_bits.append(fmt_height(profile["height_cm"], units))
    stats_bits.append(f"Age {profile['age_years']}")
    stats_line = "   ·   ".join(stats_bits)

    hero_label = ("Daily Maintenance Target" if intent == "maintain"
                  else "Daily Calorie Target")

    # Plan tiles: deficit + pace (Step-3 elements 2 and 3).
    if intent == "maintain":
        tiles = (
            ("Goal", "Hold steady", "Keep eating at this level"),
            ("Check-in", "Weekly", "One weigh-in a week keeps drift visible"),
        )
    elif intent == "recomp":
        tiles = (
            ("Daily Deficit", f"~{fmt_num(plan['daily_deficit'])} {cu}",
             "Slight deficit, heavy protein"),
            ("Watch", "The mirror", "Scale moves slowly — strength won't"),
        )
    elif intent == "gain":
        tiles = (
            ("Daily Surplus", f"~{fmt_num(-plan['daily_deficit'])} {cu}",
             "Above maintenance"),
            ("Weekly Gain", fmt_rate(plan["rate_kg_per_week"], units),
             "Lean and steady"),
        )
    else:  # lose
        tiles = (
            ("Daily Deficit", f"~{fmt_num(plan['daily_deficit'])} {cu}",
             "Below what you burn"),
            ("Weekly Pace", fmt_rate(plan["rate_kg_per_week"], units),
             "Steady and sustainable"),
        )

    # Timeline: single completion month, or the unlock prompt.
    if plan.get("estimated_completion"):
        timeline_label = "Your Timeline"
        timeline_html = (
            '<div class="goal-tile">'
            '<div class="goal-label">Goal Reached</div>'
            f'<div class="goal-value">{fmt_month_year_short(plan["estimated_completion"])}</div>'
            f'<div class="goal-note">~{round(plan["weeks"])} weeks from today</div>'
            "</div>"
        )
    elif plan.get("timeline_locked"):
        timeline_label = "Your Timeline"
        timeline_html = (
            '<div class="unlock">'
            '<div class="unlock-title">Reply with your goal weight'
            "<br>to unlock your completion date</div>"
            "</div>"
        )
    else:  # maintain / recomp — no timeline concept
        timeline_label = "Your Focus"
        focus = ("Consistency beats perfection — show up daily"
                 if intent == "maintain"
                 else "Give it 8–12 weeks before judging the scale")
        timeline_html = (
            '<div class="goal-tile">'
            '<div class="goal-label">Remember</div>'
            f'<div class="goal-note" style="margin-top:16px; font-size:33px; '
            f'color:#ffffff; font-weight:700;">{focus}</div>'
            "</div>"
        )

    habits_html = "".join(
        f'<div class="habit"><span class="tick">✓</span>&nbsp;&nbsp;{h}</div>'
        for h in HABITS[intent]
    )

    return {
        "date_label": date.today().strftime("%B %d, %Y").upper(),
        "plan_title": PLAN_TITLES[intent],
        "stats_line": stats_line,
        "hero_label": hero_label,
        "hero_value": fmt_num(plan["daily_cal"]),
        "hero_unit": f"{cu} per day",
        "tile1_label": tiles[0][0],
        "tile1_value": tiles[0][1],
        "tile1_note": tiles[0][2],
        "tile2_label": tiles[1][0],
        "tile2_value": tiles[1][1],
        "tile2_note": tiles[1][2],
        "timeline_section_label": timeline_label,
        "timeline_html": timeline_html,
        "habits_html": habits_html,
    }


def render_html(template_vars: dict) -> str:
    template = string.Template(TEMPLATE.read_text(encoding="utf-8"))
    return template.substitute(template_vars)


# ---------------------------------------------------------------------------
# PNG pipeline: HTML → PDF (WeasyPrint) → PNG (PyMuPDF), fit under max-bytes
# ---------------------------------------------------------------------------

def html_to_png(html: str, out_path: Path, width: int, max_bytes: int) -> int:
    from weasyprint import HTML  # imported lazily so --help works without deps
    import fitz  # PyMuPDF

    pdf_bytes = HTML(string=html, base_url=str(TEMPLATE.parent)).write_pdf()

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        page = doc[0]
        page_w_pt = page.rect.width  # CSS px * 0.75
        render_width = width
        png = None
        while True:
            zoom = render_width / page_w_pt
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            png = pix.tobytes("png")
            if len(png) <= max_bytes or render_width <= MIN_RENDER_WIDTH:
                break
            render_width = max(MIN_RENDER_WIDTH, int(render_width * 0.85))
    finally:
        doc.close()

    if len(png) > max_bytes:
        raise RuntimeError(
            f"Could not compress PNG under {max_bytes} bytes "
            f"(best effort: {len(png)} bytes at width {render_width})"
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(png)
    return len(png)


# ---------------------------------------------------------------------------
# PLAN.md generation — mirrors the Step-3 presentation
# (user-onboarding-profile/SKILL.md): user info block + the four plan
# elements + short pace explanation. NO macro split. The "Daily calorie
# target:" line is what downstream skills (meal-planner) look for.
# ---------------------------------------------------------------------------

def build_plan_markdown(plan: dict, profile: dict, locale: dict) -> str:
    units = locale["units"]
    cu = cal_unit(locale["country"])
    intent = plan["intent"]

    activity_desc = ACTIVITY_DESCRIPTIONS[plan["activity"]]
    if plan["activity_assumed"]:
        activity_desc += " (assumed — tell me your routine to fine-tune)"

    lines = []
    lines.append(f"# {PLAN_TITLES[intent].replace('Your ', '')}")
    lines.append("")
    lines.append(f"*Generated {date.today().isoformat()} · NanoRhino AI Nutrition Coach*")
    lines.append("")
    lines.append("## Your Info")
    lines.append("")
    lines.append(f"• Height: {fmt_height(profile['height_cm'], units)}")
    lines.append(f"• Current weight: {fmt_weight(profile['weight_kg'], units)}")
    if plan.get("goal_weight_kg") is not None:
        lines.append(f"• Goal weight: {fmt_weight(plan['goal_weight_kg'], units)}")
    lines.append(f"• Age: {profile['age_years']} · Sex: {profile['sex'].capitalize()}")
    lines.append(f"• Activity: {activity_desc}")
    lines.append("")
    lines.append("## Your Plan")
    lines.append("")
    lines.append(f"• Daily calorie target: {fmt_num(plan['daily_cal'])} {cu}")
    deficit = plan.get("daily_deficit")
    if deficit:
        if deficit > 0:
            lines.append(f"• Daily calorie deficit: ~{fmt_num(deficit)} {cu}")
        else:
            lines.append(f"• Daily calorie surplus: ~{fmt_num(-deficit)} {cu}")
    if plan.get("rate_kg_per_week") and intent != "maintain":
        word = "gain" if intent == "gain" else "loss"
        lines.append(f"• Weekly {word} rate: ~{fmt_rate(plan['rate_kg_per_week'], units)}")
    if plan.get("estimated_completion"):
        lines.append(f"• Estimated completion: {fmt_month_year(plan['estimated_completion'])}")
    elif plan.get("timeline_locked"):
        lines.append("• Estimated completion: reply with your goal weight "
                     "to unlock your completion date")
    lines.append("")

    # Short pace explanation, user-perspective, no TDEE/BMR jargon.
    if intent == "lose":
        explanation = ("This pace keeps your energy up while the scale keeps "
                       "moving — steady enough to stick with.")
        if plan["activity"] == "sedentary":
            explanation += (" Adding a bit more daily movement would "
                            "speed things up.")
    elif intent == "maintain":
        explanation = ("Eat around this level and your weight holds steady — "
                       "a weekly weigh-in catches any drift early.")
    elif intent == "recomp":
        explanation = ("A small deficit with plenty of protein lets you build "
                       "strength while trimming fat — judge progress by the "
                       "mirror, not the scale.")
    else:
        explanation = ("A modest surplus keeps the gains lean — slow on the "
                       "scale, visible in the gym.")
    lines.append(f"*{explanation}*")
    lines.append("")
    if plan.get("floor_clamped"):
        lines.append("> Note: your daily target was raised to your safety "
                     "floor and the pace adjusted accordingly — eating less "
                     "than this would work against you.")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Render a handoff profile into an MMS plan card PNG + PLAN.md markdown"
    )
    parser.add_argument("--input", required=True, help="Path to input JSON")
    parser.add_argument("--output", required=True, help="Path to output PNG")
    parser.add_argument("--width", type=int, default=1080, help="PNG width in px (default 1080)")
    parser.add_argument("--max-bytes", type=int, default=614400,
                        help="Max PNG size in bytes (default 614400 = 600 KB)")
    args = parser.parse_args()

    try:
        with open(args.input, "r", encoding="utf-8") as f:
            data = json.load(f)
        data = validate_input(data)
        profile, tdee, locale = data["profile"], data["tdee"], data["locale"]

        plan = compute_plan(profile, tdee, locale)

        template_vars = build_template_vars(plan, profile, locale)
        html = render_html(template_vars)

        out_path = Path(args.output).resolve()
        png_bytes = html_to_png(html, out_path, args.width, args.max_bytes)

        plan_markdown = build_plan_markdown(plan, profile, locale)

        print(json.dumps({
            "ok": True,
            "png": str(out_path),
            "bytes": png_bytes,
            "plan": plan,
            "plan_markdown": plan_markdown,
        }, ensure_ascii=False))
    except Exception as exc:  # noqa: BLE001 — contract: error JSON + non-zero exit
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
