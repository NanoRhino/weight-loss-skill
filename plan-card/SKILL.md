---
name: plan-card
version: 1.0.0
description: "Programmatic (non-conversational) skill that generates the user's weight-loss plan per the canonical Step-3 spec (user-onboarding-profile) from handoff profile data, and renders it as a branded MMS plan-card PNG plus PLAN.md markdown. Invoked directly by the openclaw-infra Twilio extension via a frozen CLI — it is NOT triggered by user conversation. Do not invoke this skill in chat; during conversational onboarding the plan is produced by user-onboarding-profile / weight-loss-planner."
metadata:
  openclaw:
    emoji: "frame_with_picture"
---

# Plan Card — SMS/MMS Plan Image + PLAN.md

Deterministic pipeline that turns handoff profile data into (a) a branded
NanoRhino plan card PNG for MMS delivery and (b) PLAN.md markdown content —
no LLM involved. The openclaw-infra Twilio extension invokes the script
programmatically (`planImage.scriptPath` in its deploy config must point to
`plan-card/scripts/plan-to-image.py`).

## CLI Contract (frozen — do not change)

```bash
python3 {baseDir}/scripts/plan-to-image.py \
  --input <input.json> --output <out.png> [--width 1080] [--max-bytes 614400]
```

**Input JSON:**

```json
{
  "profile": { "sex": "male|female", "age_years": N, "height_cm": N,
               "weight_kg": N, "goal_weight_kg": N|null,
               "intent": "lose|maintain|recomp|gain",
               "daily_steps": N|null,
               "activity_level": "sedentary|lightly_active|moderately_active|very_active|null" },
  "tdee":    { "recommended": N, "low": N, "high": N, "bmr": N },
  "locale":  { "country": "US", "units": "imperial|metric" }
}
```

See `examples/sample-input-with-goalweight.json` and
`examples/sample-input-without-goalweight.json`.

**stdout on success (single JSON line):**
`{"ok": true, "png": "<abs path>", "bytes": N, "plan": {...}, "plan_markdown": "..."}`

**On failure:** non-zero exit, `{"ok": false, "error": "..."}` on stdout,
traceback on stderr.

The caller is responsible for writing `plan_markdown` to the agent
workspace as `PLAN.md`.

## Methodology (canonical sources)

Plan **content** follows `user-onboarding-profile/SKILL.md > Step 3：生成并
确认减脂方案` exactly:

- A **single** daily calorie target — never a band.
- Daily calorie deficit (~XXX).
- Weekly loss rate.
- A **single** completion month + year.
- **No macro split** at the plan stage — macros belong to Step 4
  (diet-mode selection, later in SMS coaching). The card and PLAN.md
  contain no protein/fat/carb numbers.

Plan **math** comes from `weight-loss-planner/scripts/planner-calc.py`
invoked as a subprocess (its interface is unchanged):

- `forward-calc --mode balanced` is the canonical calculation when
  `goal_weight_kg` is present and intent is `lose` — pace table
  (<10 kg → 0.35 kg/wk default; 10–25 kg → 0.6; >25 kg → 0.7), safety
  floor max(BMR, 1000) with rate back-calculation, completion date.
  The handoff `tdee` block is NOT used on this path; forward-calc's own
  BMR/TDEE is trusted.
- `--bmi-standard asian` when the locale country/language is
  Chinese/Japanese/Korean (CN/TW/HK/MO/SG/JP/KR or zh/ja/ko); `who`
  otherwise.
- The Step-3 "50 岁以上偏向下限" pace note is a conversational judgment
  call and is not part of planner-calc's deterministic math; this pipeline
  trusts forward-calc's default rate.

## Fallback rules (paths forward-calc cannot compute)

- **`goal_weight_kg` null + intent `lose`:** daily target = handoff
  `tdee.recommended` minus the deficit implied by the most conservative
  pace-table default 0.35 kg/wk (≈385 kcal, via planner-calc
  `calorie-target`), floored at max(BMR, 1000) (via planner-calc
  `safety-floor`). The card and PLAN.md show "Reply with your goal weight
  to unlock your completion date" instead of a date — still a single
  target number.
- **`maintain`:** target = handoff `tdee.recommended` (single number),
  no deficit, no timeline.
- **`recomp`:** target = TDEE − 200, no timeline.
- **`gain`:** target = TDEE + ≈275 (0.25 kg/wk lean gain); timeline only
  if a goal weight above current weight is provided.
- **Activity missing:** derived from `daily_steps`
  (<5000 sedentary, <8000 lightly, <12000 moderately, else very active),
  else defaults to `lightly_active` (the weight-loss-planner default).

## Rendering

`templates/plan-card.html` (1080×1620 portrait, inline CSS only, no
external assets) → WeasyPrint HTML→PDF → PyMuPDF PDF→PNG at `--width`,
downscaled until it fits `--max-bytes` (default 600 KB MMS budget).

Card blocks: NanoRhino wordmark (CamelCase, single color — no accent
split), hero single daily calorie target, daily deficit + weekly pace
tiles, completion month (or unlock box), starter habits, coach footer.

## PLAN.md structure (plan_markdown)

Mirrors the Step-3 presentation so downstream skills work unchanged:
user info block (height / weight / goal weight / age / sex / colloquial
activity) → "Your Plan" with the four elements (the
`Daily calorie target: X` line is what meal-planner looks up) → 1–2
sentence pace explanation (no TDEE/BMR jargon). No macros, no meal split.

## Dependencies

`pip install -r {baseDir}/requirements.txt` (`weasyprint`, `pymupdf`).
WeasyPrint also needs pango/cairo/gdk-pixbuf **system libraries** — on EC2
(Amazon Linux): `sudo dnf install -y pango cairo gdk-pixbuf2`; on Ubuntu:
`sudo apt-get install -y libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0`.

## Data dependencies

| Resource | Direction | Mechanism |
|---|---|---|
| Handoff profile JSON (`--input`) | read | provided by openclaw-infra Twilio extension |
| `weight-loss-planner/scripts/planner-calc.py` | read/execute | subprocess (owner: weight-loss-planner) |
| Plan card PNG (`--output`) | write | this script |
| `PLAN.md` content | emit | `plan_markdown` in stdout JSON; caller writes the file |
