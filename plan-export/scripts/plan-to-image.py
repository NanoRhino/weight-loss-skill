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

No LLM involved. All numbers come from weight-loss-planner/scripts/planner-calc.py
(imported as a module — its CLI/interface is not modified).

CLI contract (invoked by the openclaw-infra Twilio extension — do not change):

  python3 plan-export/scripts/plan-to-image.py \
      --input <input.json> --output <out.png> [--width 1080] [--max-bytes 614400]

stdout on success (single JSON line):
  {"ok": true, "png": "<abs path>", "bytes": N, "plan": {...}, "plan_markdown": "..."}
On failure: non-zero exit, {"ok": false, "error": "..."} on stdout, details on stderr.

System dependencies: WeasyPrint needs pango/cairo/gdk-pixbuf system libraries
(on EC2/Amazon Linux: `sudo dnf install pango cairo gdk-pixbuf2`;
on Ubuntu: `sudo apt-get install libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0`).
"""

import argparse
import importlib.util
import json
import string
import sys
import traceback
from datetime import date, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
PLANNER_CALC = REPO_ROOT / "weight-loss-planner" / "scripts" / "planner-calc.py"
TEMPLATE = SCRIPT_DIR.parent / "templates" / "plan-card.html"

KG_PER_LB = 1 / 2.205

# Intent-based fallback when goal_weight_kg is null and intent == "lose":
# 0.75% of bodyweight per week.
NO_GOAL_LOSE_RATE_PCT = 0.0075
# Mild deterministic adjustments for the intents planner-calc doesn't model.
RECOMP_DEFICIT_KCAL = 200
GAIN_RATE_KG_PER_WEEK = 0.25  # lean gain default

VALID_SEX = {"male", "female"}
VALID_INTENT = {"lose", "maintain", "recomp", "gain"}

MIN_RENDER_WIDTH = 480  # don't shrink the PNG below this when fitting max-bytes


# ---------------------------------------------------------------------------
# planner-calc import (filename contains a hyphen, so use importlib)
# ---------------------------------------------------------------------------

def load_planner_calc():
    spec = importlib.util.spec_from_file_location("planner_calc", PLANNER_CALC)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load planner-calc.py at {PLANNER_CALC}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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
    data["locale"] = {"country": country, "units": units}
    return data


# ---------------------------------------------------------------------------
# Plan computation (reuses planner-calc functions; same flow as forward_calc,
# but anchored on the handoff TDEE/BMR instead of recomputing them, so the
# card matches the numbers the user was already shown)
# ---------------------------------------------------------------------------

def compute_plan(pc, profile: dict, tdee: dict) -> dict:
    weight = profile["weight_kg"]
    goal = profile.get("goal_weight_kg")
    intent = profile["intent"]
    bmr = tdee["bmr"]
    tdee_rec = tdee["recommended"]
    floor = pc.calc_safety_floor(bmr)
    today = date.today()

    plan = {
        "intent": intent,
        "bmr": bmr,
        "tdee": tdee_rec,
        "calorie_floor": floor,
        "floor_clamped": False,
        "goal_weight_kg": goal,
        "weight_kg": weight,
        "bmi_current": pc.calc_bmi(weight, profile["height_cm"]),
        "rate_kg_per_week": None,
        "daily_deficit": None,
        "weeks": None,
        "estimated_completion": None,
        "timeline_locked": False,
        "milestones": [],
    }

    # Treat a goal at/above current weight under 'lose' as maintenance.
    if intent == "lose" and goal is not None and goal >= weight:
        intent = plan["intent"] = "maintain"

    if intent == "maintain":
        daily_cal = max(tdee_rec, floor)
        plan["daily_cal"] = daily_cal
        plan["daily_cal_range"] = {"min": tdee["low"], "max": tdee["high"]}
        macros = pc.calc_macro_targets(weight, daily_cal, "balanced", 3, None)

    elif intent == "recomp":
        daily_cal = max(tdee_rec - RECOMP_DEFICIT_KCAL, floor)
        plan["daily_cal"] = daily_cal
        plan["daily_cal_range"] = {"min": daily_cal - 100, "max": daily_cal + 100}
        plan["daily_deficit"] = tdee_rec - daily_cal
        macros = pc.calc_macro_targets(weight, daily_cal, "high_protein", 3, None)

    elif intent == "gain":
        rate = GAIN_RATE_KG_PER_WEEK
        surplus = round(rate * 1100)
        daily_cal = tdee_rec + surplus
        plan["daily_cal"] = daily_cal
        plan["daily_cal_range"] = {"min": daily_cal - 100, "max": daily_cal + 100}
        plan["rate_kg_per_week"] = rate
        plan["daily_deficit"] = -surplus
        if goal is not None and goal > weight:
            weeks = round((goal - weight) / rate, 1)
            plan["weeks"] = weeks
            plan["estimated_completion"] = (today + timedelta(days=round(weeks * 7))).isoformat()
            plan["bmi_target"] = pc.calc_bmi(goal, profile["height_cm"])
        else:
            plan["timeline_locked"] = True
        macros = pc.calc_macro_targets(weight, daily_cal, "high_protein", 3, goal)

    else:  # lose
        if goal is not None:
            to_lose = round(weight - goal, 1)
            rate = pc.recommend_rate(to_lose)["rate_default_kg"]
        else:
            to_lose = None
            rate = round(weight * NO_GOAL_LOSE_RATE_PCT, 2)

        cal_info = pc.calc_calorie_target(tdee_rec, rate)
        daily_cal = cal_info["daily_cal"]
        if daily_cal < floor:
            # Same clamping logic as planner-calc forward_calc.
            plan["floor_clamped"] = True
            daily_cal = floor
            rate = round((tdee_rec - floor) / 1100, 2)
            cal_info = pc.calc_calorie_target(tdee_rec, rate)
            cal_info["daily_cal"] = floor
            cal_info["daily_cal_range"] = {"min": floor - 100, "max": floor + 100}

        plan["daily_cal"] = daily_cal
        plan["daily_cal_range"] = cal_info["daily_cal_range"]
        plan["daily_deficit"] = cal_info["daily_deficit"]
        plan["rate_kg_per_week"] = rate

        if goal is not None and rate > 0:
            weeks = round(to_lose / rate, 1)
            plan["to_lose_kg"] = to_lose
            plan["weeks"] = weeks
            plan["estimated_completion"] = (today + timedelta(days=round(weeks * 7))).isoformat()
            plan["bmi_target"] = pc.calc_bmi(goal, profile["height_cm"])
            plan["milestones"] = build_milestones(weight, goal, rate, today)
        else:
            plan["timeline_locked"] = True

        macros = pc.calc_macro_targets(weight, daily_cal, "balanced", 3, goal)

    plan["macros"] = macros
    return plan


def build_milestones(weight: float, goal: float, rate: float, start: date) -> list:
    """Quarter-point milestones with projected dates (deterministic)."""
    to_lose = weight - goal
    milestones = []
    for pct in (25, 50, 75, 100):
        lost = to_lose * pct / 100
        weeks = lost / rate if rate > 0 else 0
        milestones.append({
            "percent": pct,
            "weight_kg": round(weight - lost, 1),
            "date": (start + timedelta(days=round(weeks * 7))).isoformat(),
        })
    return milestones


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def kg_to_lb(kg: float) -> float:
    return kg / KG_PER_LB


def fmt_weight(kg: float, units: str) -> str:
    if units == "imperial":
        return f"{round(kg_to_lb(kg))} lb"
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
    d = date.fromisoformat(iso_date)
    return d.strftime("%b %Y")


PLAN_TITLES = {
    "lose": "Your Weight Loss Plan",
    "maintain": "Your Maintenance Plan",
    "recomp": "Your Recomposition Plan",
    "gain": "Your Lean Gain Plan",
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
        "Hit your protein floor daily",
        "Sleep 7+ hours; muscle is built at night",
    ],
    "gain": [
        "Eat on a schedule — don't skip meals",
        "Hit your protein floor daily",
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
    band = plan["daily_cal_range"]
    macros = plan["macros"]

    hero_label = "Daily Maintenance Zone" if intent == "maintain" else "Daily Calorie Target"

    stats_bits = [fmt_weight(profile["weight_kg"], units)]
    if plan.get("goal_weight_kg") is not None and intent != "maintain":
        stats_bits[0] += f"  →  {fmt_weight(plan['goal_weight_kg'], units)}"
    stats_bits.append(fmt_height(profile["height_cm"], units))
    stats_bits.append(f"Age {profile['age_years']}")
    stats_line = "   ·   ".join(stats_bits)

    protein = macros["protein"]
    fat = macros["fat"]
    carb = macros["carb"]

    # Timeline section
    if intent == "maintain":
        timeline_label = "Your Pace"
        timeline_html = (
            '<table class="pace-row"><tr>'
            '<td><div class="pace-label">Goal</div>'
            '<div class="pace-value">Hold steady</div>'
            f'<div class="pace-note">Stay inside your {fmt_num(band["min"])}'
            f'–{fmt_num(band["max"])} {cu} zone</div></td>'
            '<td><div class="pace-label">Check-in</div>'
            '<div class="pace-value">Weekly</div>'
            '<div class="pace-note">One weigh-in a week keeps drift visible</div></td>'
            "</tr></table>"
        )
    elif plan.get("timeline_locked"):
        timeline_label = "Your Timeline"
        verb = "gain" if intent == "gain" else "loss"
        rate_html = ""
        if plan.get("rate_kg_per_week"):
            rate_html = (
                f'<div class="unlock-sub">Current pace: ~{fmt_rate(plan["rate_kg_per_week"], units)} '
                f"steady {verb}</div>"
            )
        timeline_html = (
            '<div class="unlock">'
            '<div class="unlock-title">Reply with your goal weight to unlock your timeline</div>'
            f"{rate_html}"
            "</div>"
        )
    elif intent == "recomp":
        timeline_label = "Your Pace"
        timeline_html = (
            '<table class="pace-row"><tr>'
            '<td><div class="pace-label">Strategy</div>'
            '<div class="pace-value">Recomp</div>'
            '<div class="pace-note">Slight deficit + heavy protein</div></td>'
            '<td><div class="pace-label">Watch</div>'
            '<div class="pace-value">The mirror</div>'
            '<div class="pace-note">Scale moves slowly — strength won’t</div></td>'
            "</tr></table>"
        )
    else:
        timeline_label = "Your Timeline"
        rate_word = "Weekly gain" if intent == "gain" else "Weekly loss"
        completion = fmt_month_year(plan["estimated_completion"])
        weeks = plan["weeks"]
        timeline_html = (
            '<table class="pace-row"><tr>'
            f'<td><div class="pace-label">{rate_word}</div>'
            f'<div class="pace-value">{fmt_rate(plan["rate_kg_per_week"], units)}</div>'
            '<div class="pace-note">Steady and sustainable</div></td>'
            '<td><div class="pace-label">Goal Reached</div>'
            f'<div class="pace-value">{completion}</div>'
            f'<div class="pace-note">~{round(weeks)} weeks from today</div></td>'
            "</tr></table>"
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
        "hero_value": f'{fmt_num(band["min"])}–{fmt_num(band["max"])}',
        "hero_unit": f"{cu} per day",
        "protein_value": f'{round(protein["target"])}g',
        "protein_note": f'floor {round(protein["min"])}g',
        "fat_value": f'{round(fat["target"])}g',
        "fat_note": f'{round(fat["min"])}–{round(fat["max"])}g',
        "carb_value": f'{round(carb["target"])}g',
        "carb_note": f'{round(carb["min"])}–{round(carb["max"])}g',
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
# PLAN.md generation (matches the structure weight-loss-planner saves:
# user info → plan details → macros → milestones → notes, so downstream
# skills like meal-planner can find the calorie target)
# ---------------------------------------------------------------------------

def build_plan_markdown(plan: dict, profile: dict, locale: dict) -> str:
    units = locale["units"]
    cu = cal_unit(locale["country"])
    intent = plan["intent"]
    band = plan["daily_cal_range"]
    macros = plan["macros"]
    protein, fat, carb = macros["protein"], macros["fat"], macros["carb"]

    sex_label = profile["sex"].capitalize()
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
    lines.append(f"• Age: {profile['age_years']} · Sex: {sex_label}")
    lines.append(f"• Current BMI: {plan['bmi_current']}")
    if plan.get("bmi_target") is not None:
        lines.append(f"• Target BMI: {plan['bmi_target']}")
    lines.append("")
    lines.append("## Your Plan")
    lines.append("")
    if intent == "maintain":
        lines.append(
            f"• Daily calorie target: {fmt_num(plan['daily_cal'])} {cu} "
            f"(maintenance zone {fmt_num(band['min'])}–{fmt_num(band['max'])} {cu})"
        )
    else:
        lines.append(
            f"• Daily calorie target: {fmt_num(plan['daily_cal'])} {cu} "
            f"(range {fmt_num(band['min'])}–{fmt_num(band['max'])} {cu})"
        )
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
        lines.append(
            f"• Estimated completion: {fmt_month_year(plan['estimated_completion'])} "
            f"({plan['estimated_completion']})"
        )
    elif plan.get("timeline_locked"):
        lines.append("• Timeline: reply with your goal weight to unlock your timeline")
    lines.append("")
    lines.append("## Macro Targets")
    lines.append("")
    lines.append(
        f"• Protein: {round(protein['min'])}–{round(protein['max'])} g "
        f"(target {round(protein['target'])} g — treat {round(protein['min'])} g as your daily floor)"
    )
    lines.append(f"• Fat: {round(fat['min'])}–{round(fat['max'])} g (target {round(fat['target'])} g)")
    lines.append(f"• Carbs: {round(carb['min'])}–{round(carb['max'])} g (target {round(carb['target'])} g)")
    alloc = " / ".join(
        f"{a['meal']} {a['pct']}% (~{fmt_num(a['cal'])} {cu})" for a in macros["allocation"]
    )
    lines.append(f"• Per-meal split: {alloc}")
    lines.append("")
    if plan.get("milestones"):
        lines.append("## Milestones")
        lines.append("")
        for m in plan["milestones"]:
            lines.append(
                f"• {m['percent']}% — {fmt_weight(m['weight_kg'], units)} "
                f"by {fmt_month_year(m['date'])} ({m['date']})"
            )
        lines.append("")
    lines.append("## Starter Habits")
    lines.append("")
    for h in HABITS[intent]:
        lines.append(f"• {h}")
    lines.append("")
    lines.append("## Important Notes")
    lines.append("")
    lines.append(
        f"• Never eat below your safety floor of {fmt_num(plan['calorie_floor'])} {cu}/day."
    )
    if plan.get("floor_clamped"):
        lines.append(
            "• Your calorie target was raised to the safety floor; "
            "the weekly rate was adjusted accordingly."
        )
    lines.append(
        "• Targets are recalculated every 4 weeks (or after significant weight change)."
    )
    lines.append("• This plan is guidance, not medical advice — consult a "
                 "healthcare provider for medical conditions.")
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

        pc = load_planner_calc()
        plan = compute_plan(pc, profile, tdee)

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
