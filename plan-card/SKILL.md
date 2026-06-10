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
  "locale":  { "country": "US", "units": "imperial|metric",
               "language": "en|zh|..." }
}
```

`locale.language` (optional, BCP-47-ish lowercase, e.g. `en`, `zh`,
`zh-tw`) selects the output language; absent/unknown → `en`. The upstream
authority is **`USER.md > Language`** — the Twilio extension reads it and
passes it through. This script does NO language inference of its own
(consistent with `docs/CONVENTIONS.md` §10).

See `examples/sample-input-with-goalweight.json`,
`examples/sample-input-without-goalweight.json`, and
`examples/sample-input-zh.json`.

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

**Card-only macro override (approved):** the Step-3 "no macros at plan
stage" rule is explicitly overridden for the CARD — it additionally shows
daily macros, the per-meal rhythm, focus recommendations, and week-1
checkpoints (see Card content below). **PLAN.md stays Step-3 compliant:
no macros, no meal split there** — macros still belong to Step 4
(diet-mode selection) for everything downstream.

### Energy anchoring (product decision — Jason, 2026-06-10)

**The handoff `tdee.recommended` / `tdee.bmr` (the web TDEE decomposition
the user already saw and trusts) is the energy authority for EVERY path** —
以 tdee 的结果为准. This overrides the earlier trust-forward-calc
instruction: forward-calc re-derives BMR/TDEE from the profile and can
disagree with the web number (we saw a 2,032 Cal target against a web TDEE
of 2,010 — a "target" above the user's shown burn reads as broken).
`forward-calc` is therefore NOT called at all.

`weight-loss-planner/scripts/planner-calc.py` (subprocess; interface
unchanged) still provides the **methodology** on top of the anchored TDEE:

- **Pace:** Step-3 pace table via `recommend-rate` when `goal_weight_kg`
  is present (<10 kg → 0.35 kg/wk default; 10–25 kg → 0.6; >25 kg → 0.7);
  0.35 kg/wk default without a goal.
- **Target:** `calorie-target` → daily target = handoff
  `tdee.recommended` − deficit.
- **Floor:** `safety-floor` → max(handoff BMR, 1000). If the target falls
  below the floor it is clamped to it, and the effective rate + completion
  date are re-derived from the actual achievable deficit.
- **Timeline:** weeks = total loss ÷ (possibly clamped) rate; completion
  date recomputed from that.
- **BMI:** `bmi` with `--standard asian` when the locale country/language
  is Chinese/Japanese/Korean (CN/TW/HK/MO/SG/JP/KR or zh/ja/ko), `who`
  otherwise.
- **Macros + rhythm:** `macro-targets` from the anchored daily target
  (mode `balanced`; `high_protein` for recomp/gain), including the
  canonical 30/40/30 allocation.
- **Guarantee:** for `intent=lose` the daily target is always strictly
  below the handoff TDEE — enforced in code (degenerate handoff data
  where TDEE ≤ floor fails loudly with an error instead of rendering a
  broken card).
- The Step-3 "50 岁以上偏向下限" pace note is a conversational judgment
  call and is not part of planner-calc's deterministic math; this pipeline
  uses the pace-table default rate.

## Intent handling

- **`lose` + goal:** full plan as above (pace table, timeline, goal BMI).
- **`lose`, `goal_weight_kg` null:** 0.35 kg/wk default deficit (≈385
  kcal); the card and PLAN.md show "Reply with your goal weight to unlock
  your completion date" instead of a date — still a single target number.
- **`maintain`:** target = handoff `tdee.recommended` (single number),
  no deficit, no timeline.
- **`recomp`:** target = TDEE − 200, no timeline.
- **`gain`:** target = TDEE + ≈275 (0.25 kg/wk lean gain); timeline only
  if a goal weight above current weight is provided.
- **Activity missing:** derived from `daily_steps`
  (<5000 sedentary, <8000 lightly, <12000 moderately, else very active),
  else defaults to `lightly_active` (the weight-loss-planner default).
  (Activity only drives the focus rules and the PLAN.md description —
  energy comes from the handoff TDEE, never from an activity multiplier.)

## Card content (in order)

1. **Header** — NanoRhino wordmark (CamelCase, single color — no accent
   split) + date.
2. **Title + profile line** — weight (→ goal), height, age.
3. **Hero** — the single daily calorie target.
4. **Plan tiles** — daily deficit + weekly pace.
5. **Daily macros** — protein (visually emphasized, with its floor) /
   fat / carbs, from planner-calc `macro-targets` computed on the anchored
   daily target (mode `balanced`, or `high_protein` for recomp/gain).
6. **Daily rhythm** — per-meal calorie split from planner-calc's
   canonical 30/40/30 allocation (breakfast/lunch/dinner with ~Cal each).
7. **Focus this week** — 3 personalized, rule-based recommendations
   (table below; pure rules, no LLM).
8. **Timeline** — completion month tile, or the goal-weight unlock box.
9. **Week 1 checkpoints** — SMS coaching cadence preview:
   📸 log every meal (text a photo) / ⚖️ weigh in Wed & Sat morning /
   🍗 hit the protein target every meal.
10. **Footer** — "Text me anytime" coach line.

### Focus-this-week rules (deterministic)

| Slot | Condition (first match) | Recommendation |
|---|---|---|
| Movement | `daily_steps` < 5,000 OR resolved activity `sedentary` | 10-minute walk after lunch and dinner |
| Movement | resolved activity `lightly_active`/`moderately_active` | 2 short strength sessions |
| Movement | `very_active`/`extremely_active` | protect sleep (7+ hours) |
| Anchor | always | palm-sized protein portion every meal |
| Hydration | always | water first — 2 liters a day |

### Localization

Every user-facing string on the card and in `plan_markdown` comes from the
`STRINGS` table in `scripts/plan-to-image.py` (full `en` + `zh` today;
adding a language = adding a table entry). Language-aware conventions:
zh uses 大卡, `kg/周` pace, `kg / 斤` in PLAN.md, and `YYYY年M月` dates.

## Rendering

`templates/plan-card.html` (1080×2520 portrait, inline CSS only, no
external assets) → WeasyPrint HTML→PDF → PyMuPDF PDF→PNG at `--width`,
downscaled until it fits `--max-bytes` (default 600 KB MMS budget;
full-size renders are ~240–260 KB).

## PLAN.md structure (plan_markdown)

Mirrors the Step-3 presentation so downstream skills work unchanged:
user info block (height / weight / goal weight / age / sex / colloquial
activity) → "Your Plan"/"你的计划" with the four elements → 1–2 sentence
pace explanation (no TDEE/BMR jargon). **No macros, no meal split** —
the card-only macro override does not apply to PLAN.md.

Localized (en/zh) like the card. The calorie-target line stays parseable
in both languages (`Daily calorie target:` / `每日热量目标：` — matched by
weekly-report's existing regex), and a language-independent machine anchor
is always emitted near the top:

```
<!-- daily-calorie-target-kcal: 1805 -->
```

## Dependencies

`pip install -r {baseDir}/requirements.txt` (`weasyprint`, `pymupdf`).
WeasyPrint also needs pango/cairo/gdk-pixbuf **system libraries** — on EC2
(Amazon Linux): `sudo dnf install -y pango cairo gdk-pixbuf2`; on Ubuntu:
`sudo apt-get install -y libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0`.

For zh cards the host also needs a CJK font (e.g.
`google-noto-sans-cjk-fonts`), and the week-1 checkpoint emoji need a
color emoji font (`google-noto-emoji-color-fonts`); without them CJK/emoji
glyphs render as boxes.

## Data dependencies

| Resource | Direction | Mechanism |
|---|---|---|
| Handoff profile JSON (`--input`) | read | provided by openclaw-infra Twilio extension |
| `weight-loss-planner/scripts/planner-calc.py` | read/execute | subprocess (owner: weight-loss-planner) |
| Plan card PNG (`--output`) | write | this script |
| `PLAN.md` content | emit | `plan_markdown` in stdout JSON; caller writes the file |
