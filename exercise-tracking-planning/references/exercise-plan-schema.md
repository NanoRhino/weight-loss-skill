# Exercise Plan Markdown Schema

This document defines the strict Markdown format for `EXERCISE-PLAN.md`. The agent generates this file; `generate-exercise-plan-html.py` parses it into styled HTML.

## Rules

1. **H1** (`#`) = Plan title. Followed by metadata lines (unordered list). **Metadata keys MUST always be in English** (`Date`, `Goal`, `Level`, `Split`, `Frequency`, `Equipment`) regardless of the user's language — the HTML parser matches on these exact keys. Values can be in any language.
2. **H2** (`##`) = Section header. Used for:
   - `## Weekly Overview` — the at-a-glance table (required, English key)
   - `## Day N | DayName: Label` — day card (e.g., `## Day 1 | Monday: Full Body A` or `## Day 2 | Tuesday: Rest Day`)
   - `## Progression` — week-by-week progression guidance (required, English key)
   - `## Notes` — closing notes section (required, English key)
   - `## Disclaimer` — safety disclaimer (required for first-time plans, English key)
3. **Weekly Overview** block: a Markdown table with columns `| Day | Training |`. Rest-day cells must start with `Rest` (parser uses this to apply muted styling).
4. **Day cards** come in two types:
   - **Training day**: Contains `### Warm-up`, `### Main Training`, and `### Cooldown` sub-sections, plus an optional video link line.
   - **Rest day**: Contains a bullet list of suggestions (light activity, stretching, etc.). Parser detects rest days by the word `Rest` in the day label.
5. **H3** (`###`) = Phase header within a day card. Used for:
   - `### Video` — follow-along video link (one per training day, must be first H3)
   - `### Warm-up (Xmin)` — warm-up phase with numbered list
   - `### Main Training` — main training phase with exercise blocks
   - `### Cooldown (Xmin)` — cooldown phase with numbered list
6. **Video line**: A single line under `### Video` in the format: `[Display Text](URL)`
7. **Exercise block** (under Main Training): Uses **H4** (`####`) for each exercise.
   - Format: `#### N. ExerciseName | intensity description`
   - Followed by a single prescription line (indented or not): `3 sets ×10-12 reps, rest 90s between sets`
   - Or multiple prescription lines if sets differ (one line per set).
8. **Numbered list items** (`1.`, `2.`, etc.) in Warm-up/Cooldown = `.phase-list` items.
9. **Bullet list items** (`-`) in rest days = `.rest-content` items.
10. **Progression section**: Bullet list items where `**bold text**` becomes `<strong>` for week labels.
11. **Notes section**: Each paragraph is a separate `<p>`. Lines starting with `💡` become `.tip` elements.
12. **Disclaimer section**: Single paragraph of disclaimer text.

## Duration Hint

Training day H2 headers can include a duration hint after the label:
- Format: `## Day 1 | Monday: Full Body A | ~55 min`
- The `| ~55 min` part becomes `.day-meta` in the HTML header.

## Complete Example

```markdown
# Weekly Training Plan
- Date: 2026-03-09
- Goal: Fat loss while preserving muscle
- Level: Beginner
- Split: Full Body (3 days)
- Frequency: 3 days/week
- Equipment: Full gym (dumbbells, cables, barbells, machines)

## Weekly Overview

| Day | Training |
|-----|----------|
| Mon | Full Body A |
| Tue | Rest · Walk 30min |
| Wed | Full Body B |
| Thu | Rest · Walk 30min |
| Fri | Full Body C |
| Sat | Rest · Optional light activity |
| Sun | Full rest |

## Day 1 | Monday: Full Body A | ~55 min

### Video
[▶ Full Body Beginner Gym Workout](https://www.youtube.com/results?search_query=full+body+beginner+gym+workout)

### Warm-up (8 min)
1. Elliptical slow pace — 3 min
2. Cat-Cow — ×10
3. World's Greatest Stretch — ×5 each side
4. Bodyweight Squat — ×10

### Main Training

#### 1. Goblet Squat | moderate effort (could do ~3 more reps)
3 sets ×10-12 reps, rest 90s between sets

#### 2. Dumbbell Bench Press | moderate effort (could do ~3 more reps)
3 sets ×10-12 reps, rest 90s between sets

#### 3. Cable Row | moderate effort (could do ~3 more reps)
3 sets ×10-12 reps, rest 90s between sets

#### 4. Dumbbell Romanian Deadlift | moderate effort (could do ~3 more reps)
3 sets ×10-12 reps, rest 90s between sets

#### 5. Overhead Press (Dumbbell) | moderate effort (could do ~3 more reps)
3 sets ×10-12 reps, rest 90s between sets

### Cooldown (5 min)
1. Quad stretch — 20s each side
2. Hamstring stretch — 20s each side
3. Chest doorway stretch — 20s
4. Child's pose — 30s

## Day 2 | Tuesday: Rest Day

- Elliptical or brisk walk — 25-30 min, easy conversational pace
- Or full rest if needed

## Day 3 | Wednesday: Full Body B | ~55 min

### Video
[▶ Full Body Intermediate Workout](https://www.youtube.com/results?search_query=full+body+intermediate+workout)

### Warm-up (8 min)
1. Jump rope — 2 min
2. Hip circles — ×10 each direction
3. Arm circles — ×10 forward, ×10 backward
4. Bodyweight lunges — ×8 each side

### Main Training

#### 1. Barbell Squat | moderate effort (could do ~3 more reps)
3 sets ×8-10 reps, rest 2 min between sets

#### 2. Incline Dumbbell Press | moderate effort (could do ~3 more reps)
3 sets ×10-12 reps, rest 90s between sets

#### 3. Lat Pulldown | moderate effort (could do ~3 more reps)
3 sets ×10-12 reps, rest 90s between sets

#### 4. Leg Curl (Machine) | moderate effort (could do ~3 more reps)
3 sets ×12-15 reps, rest 60s between sets

#### 5. Lateral Raise | light-moderate effort
3 sets ×12-15 reps, rest 60s between sets

### Cooldown (5 min)
1. Standing quad stretch — 20s each side
2. Seated hamstring stretch — 20s each side
3. Cross-body shoulder stretch — 15s each arm
4. Deep breathing — 5 breaths

## Day 4 | Thursday: Rest Day

- Light walk — 20-30 min
- Foam rolling (optional) — 10 min
- Or full rest if needed

## Day 5 | Friday: Full Body C | ~55 min

### Video
[▶ Full Body Dumbbell Workout](https://www.youtube.com/results?search_query=full+body+dumbbell+workout+beginner)

### Warm-up (8 min)
1. Stationary bike easy pace — 3 min
2. Leg swings — ×10 each side
3. Band pull-aparts — ×15
4. Glute bridges — ×12

### Main Training

#### 1. Leg Press | moderate effort (could do ~3 more reps)
3 sets ×10-12 reps, rest 90s between sets

#### 2. Dumbbell Shoulder Press | moderate effort (could do ~3 more reps)
3 sets ×10-12 reps, rest 90s between sets

#### 3. Seated Cable Row | moderate effort (could do ~3 more reps)
3 sets ×10-12 reps, rest 90s between sets

#### 4. Hip Thrust (Barbell or Machine) | moderate effort
3 sets ×10-12 reps, rest 90s between sets

#### 5. Face Pull | light-moderate effort
3 sets ×15 reps, rest 60s between sets

### Cooldown (5 min)
1. Pigeon stretch — 20s each side
2. Cat-Cow — ×8
3. Chest stretch on wall — 15s each side
4. Child's pose — 30s

## Day 6 | Saturday: Rest Day

- Optional light activity: yoga, swimming, hiking
- Or full rest

## Day 7 | Sunday: Rest Day

- Full rest
- Light stretching if desired

## Progression

- **Weeks 1–2:** Learn the movements, use moderate effort (could do ~3 more reps)
- **Weeks 3–4:** Begin progressive overload — add a little weight or a few reps each session
- **Week 5 (Deload):** Reduce volume by 40%, keep intensity the same

## Notes

If any exercise is unfamiliar, just ask me and I'll explain it in detail!

Track your workouts — even a notes app works. Recording weights, reps, and perceived effort is essential for progressive overload.

💡 For home/solo training: always use safety pins on the squat rack, never test your true 1RM alone, and learn the safe bail technique for squat and bench press.

## Disclaimer

⚠️ This training plan is for informational and educational purposes only. It is not a substitute for professional medical advice. If you have any injuries, chronic conditions, or health concerns, please consult a physician or licensed physical therapist before starting. Proper form is critical — consider working with a qualified trainer in person, especially if you're new to the exercises.
```

## Notes for the Agent

- **Metadata keys (`Date`, `Goal`, `Level`, `Split`, `Frequency`, `Equipment`) MUST be in English** — the parser depends on these exact keys. Values can be localized (e.g., `Goal: 减脂增肌` is fine, but `目标: 减脂增肌` will break parsing).
- Every day (Day 1–7) must be fully written out. No placeholders like "same as Day 1".
- Rest days are detected by the word `Rest` in the H2 label (e.g., `Rest Day`, `休息日 Rest`). For Chinese plans, include `Rest` somewhere in the label.
- Training days MUST have all three phases: Warm-up, Main Training, Cooldown.
- Video link is mandatory for each training day and must be the first H3 section.
- Duration hint (e.g., `| ~55 min`) in the H2 is optional but recommended.
- The metadata Date field should be the generation date.
- Adapt exercise names, day names, instructions, and language to the user's locale. Keep metadata keys in English.
