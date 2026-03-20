# Nutrition Science Formulas Reference

## Unit Conversions (Imperial ↔ Metric)

```
weight_kg  = weight_lbs / 2.205
weight_lbs = weight_kg × 2.205
height_cm  = (height_feet × 12 + height_inches) × 2.54
height_m   = height_cm / 100
```

---

## BMI (Body Mass Index)

**Imperial:**
```
BMI = (weight_lbs × 703) / (height_inches²)
```

**Metric:**
```
BMI = weight_kg / (height_m²)
```

**WHO Classification (International Default):**

| BMI Range | Classification |
|---|---|
| < 18.5 | Underweight |
| 18.5 – 24.9 | Normal weight |
| 25.0 – 29.9 | Overweight |
| 30.0 – 34.9 | Obese (Class I) |
| 35.0 – 39.9 | Obese (Class II) |
| ≥ 40.0 | Obese (Class III) |

**Asian Classification (China, Japan, Korea, Southeast Asia):**

Use this standard when the user is located in an Asian country, or when the user's language is Chinese, Japanese, or Korean and their country is unknown.

| BMI Range | Classification |
|---|---|
| < 18.5 | Underweight |
| 18.5 – 23.9 | Normal weight |
| 24.0 – 27.9 | Overweight |
| ≥ 28.0 | Obese |

**How to select the standard:**
1. If the user's country is known → use the corresponding regional standard
2. If the user's country is unknown → infer from language:
   - Chinese (zh), Japanese (ja), Korean (ko) → Asian standard
   - All other languages → WHO international standard
3. Always label which standard is being used in the output (e.g., "BMI 25.2 — Overweight per Asian standard" or "BMI 25.2 — Normal per WHO standard")

Note: BMI is a rough screening tool. It doesn't account for muscle mass, bone density, or body composition. Present it as context, not as a verdict.

---

## BMR — Mifflin-St Jeor Equation

Preferred over Harris-Benedict for modern populations; more accurate especially for overweight individuals.

**Male:**
```
BMR = (10 × weight_kg) + (6.25 × height_cm) - (5 × age_years) + 5
```

**Female:**
```
BMR = (10 × weight_kg) + (6.25 × height_cm) - (5 × age_years) - 161
```

---

## TDEE — Total Daily Energy Expenditure

```
TDEE = BMR × Activity Multiplier
```

### Activity Multipliers (NEAT-Only — Excludes Intentional Exercise)

These multipliers estimate **non-exercise activity thermogenesis (NEAT)** — energy spent on daily living, commuting, job-related movement, errands, and general fidgeting. They deliberately **exclude** intentional exercise (gym, running, swimming, sports, etc.), which is tracked separately by the `exercise-tracking-planning` skill via MET-based calorie estimation.

**Why NEAT-only?** The classic Harris-Benedict activity multipliers bundle exercise into the lifestyle factor, which causes double-counting when users also log workouts. By separating NEAT from exercise, we get a stable baseline TDEE that doesn't overlap with per-session exercise calorie estimates.

| Level | Multiplier | Description (lifestyle only, no exercise) | Typical Daily Steps |
|---|---|---|---|
| Sedentary | 1.2 | Works from home or desk job, drives everywhere, minimal daily movement beyond basic self-care | < 4,000 |
| Lightly Active | 1.375 | Office/desk worker who commutes (walk/transit), runs errands, does light housework — typical modern adult | 4,000–7,500 |
| Moderately Active | 1.55 | On-feet job (teacher, nurse, retail, waiter) or very active daily routine (frequent walking, manual household tasks) | 7,500–10,000 |
| Very Active | 1.725 | Physically demanding job (warehouse, postal carrier, agriculture) with sustained movement throughout the day | 10,000–15,000 |
| Extremely Active | 1.9 | Heavy manual labor all day (construction, mining, commercial fishing) | > 15,000 |

**Important:** These multipliers are population averages. Individual variation of ±10–15% is common. Factors like NEAT (fidgeting, posture maintenance, spontaneous movement), genetics, thyroid function, and body composition all play a role. The TDEE range (±100 kcal) helps account for this uncertainty.

### Activity Level Selection Policy

**Default to Lightly Active (×1.375)** for most users. This represents a typical adult with a desk-based job and normal daily movement (commuting, errands, housework).

**Critical rule: Classify by daily lifestyle and job type ONLY.** Gym sessions, running, sports, and other intentional exercise must NOT influence the activity level selection. Exercise is tracked and reported separately — including it here would double-count those calories.

**Selection rules:**
1. **Lightly Active (×1.375)** — use by default for most users. This covers: office workers, students, remote workers who leave the house for errands, and anyone whose daily routine is primarily seated with normal daily movement. A user who has a desk job but goes to the gym 5 days/week is still **Lightly Active** — their gym sessions are tracked separately
2. **Sedentary (×1.2)** — use only when the user explicitly describes a near-immobile daily life: works from home **and** rarely leaves the house **and** minimal daily movement. Simply having a desk job is NOT enough — most desk workers still commute, shop, and move around enough to qualify as lightly active
3. **Moderately Active (×1.55)** — use when the user's **job or daily routine** (not exercise) involves significant on-feet time. Examples: nurses, teachers, retail workers, parents with young children who are constantly moving, or anyone who walks/cycles as their primary mode of transport. A desk worker who also exercises intensely does NOT qualify — their lifestyle NEAT is still lightly active
4. **Very Active (×1.725) and Extremely Active (×1.9)** — reserve for users whose **jobs** are physically demanding: warehouse workers, postal carriers, farm hands, construction workers, etc. Do not use these levels based on exercise frequency alone

**Do not expose multiplier values to the user.** Activity level classification is an internal calculation detail. Present TDEE results without mentioning the specific multiplier used.

### TDEE Range Calculation

TDEE estimation is inherently imprecise. To give the user a practical range, present TDEE as a **point estimate ± 100 kcal**.

**Procedure:**
1. Based on the user's activity description, select the best-fit multiplier per the selection policy above (default: lightly active)
2. Calculate: `TDEE_low = TDEE - 100`, `TDEE_high = TDEE + 100`

**Example:**
- User describes: "I work in an office and sometimes go for walks on weekends"
- Best fit: Lightly Active (×1.375) — default
- BMR = 1,800 → TDEE = **2,475** (range: 2,375 – 2,575)

This ±100 kcal range accounts for day-to-day variation in activity and measurement imprecision. If the user feels the estimate is too high or too low, they can adjust within the range or request a recalculation with a different activity level.

---

## Calorie Deficit Math

Core principle: approximately **3,500 calories ≈ 1 pound** of body fat. This is an approximation — individual variation exists, but it's the standard used in clinical practice.

| Weekly Loss Target | Daily Deficit |
|---|---|
| 0.5 lbs/week | 250 kcal/day |
| 1.0 lbs/week | 500 kcal/day |
| 1.5 lbs/week | 750 kcal/day |
| 2.0 lbs/week | 1,000 kcal/day |

**Daily Calorie Target:**
```
Daily_Calories = TDEE - Daily_Deficit
```

### Safe Minimums — BMR-Based Floor

Eating below BMR means the body cannot sustain basic organ function, thermoregulation, and cellular repair even at complete rest. The calorie floor should be personalized using BMR rather than a fixed number.

**Floor rule:**
```
calorie_floor = max(BMR, absolute_minimum)
```

| Parameter | Value | Rationale |
|---|---|---|
| BMR | Calculated per user (Mifflin-St Jeor) | Never eat below what the body burns at rest |
| Absolute minimum | 1,000 kcal/day | Bare minimum for micronutrient adequacy regardless of body size |

**How this works in practice:**

| User Profile | BMR | Floor = max(BMR, 1000) | Old Fixed Floor |
|---|---|---|---|
| Small female (50kg, 155cm, 55y) | 1,033 | **1,033** | 1,200 |
| Average female (65kg, 163cm, 35y) | 1,333 | **1,333** | 1,200 |
| Large female (90kg, 170cm, 40y) | 1,602 | **1,602** | 1,200 |
| Small male (60kg, 168cm, 50y) | 1,405 | **1,405** | 1,500 |
| Average male (80kg, 178cm, 35y) | 1,742 | **1,742** | 1,500 |
| Large male (110kg, 180cm, 40y) | 2,030 | **2,030** | 1,500 |

**Why this is better than fixed 1,200/1,500:**
- For larger users: BMR is well above the old fixed floor, so the old rule allowed eating below BMR — physiologically unhealthy
- For smaller users: BMR may be close to 1,000, and the absolute minimum still protects them
- Personalizes the safety boundary to each user's actual metabolic needs

Going below the floor without medical supervision risks nutrient deficiencies, muscle loss, metabolic slowdown, and hormonal disruption. If the calculated daily intake falls below the floor, clamp to the floor and reduce the weekly loss rate accordingly.

---

## Forward Calculation (No Timeline Given)

```
recommended_rate = (see rate table in SKILL.md)
daily_deficit    = recommended_rate × 500
daily_calories   = TDEE - daily_deficit
total_weeks      = total_lbs_to_lose / recommended_rate
```

## Reverse Calculation (Timeline Given)

```
available_weeks  = (target_date - today) in weeks
required_rate    = total_lbs_to_lose / available_weeks
daily_deficit    = required_rate × 500
daily_calories   = TDEE - daily_deficit
```

Then check:
- Is required_rate ≤ 2.0 lbs/week? If not → **explain the risks clearly** (muscle loss, metabolic slowdown, nutrient deficiency, gallstone risk, hormonal disruption) and propose the closest safe rate with its projected timeline
- Is daily_calories ≥ safe minimum? If not → **explain that this intake level is medically inadvisable** and show what the safe floor allows

**If the user insists on the aggressive rate after being informed of the risks:**
- Respect their autonomy — generate the plan at their requested rate
- Add a prominent health warning in the final report
- Remind them: "If at any point this pace feels unsustainable or you're experiencing fatigue, dizziness, or excessive hunger, let me know and we can adjust the plan immediately. There's no penalty for slowing down."
- Set a mandatory check-in at week 2 to reassess how they're feeling

---

## TDEE Recalculation at New Weight

As the user loses weight, BMR drops and so does TDEE. Recalculate on a regular schedule to keep the plan accurate.

**Recalculation triggers (whichever comes first):**
- Every **4 weeks** from plan start or last recalculation
- When the user's weight drops by **4 kg (≈ 8.8 lbs)** or more since last calculation

```
new_BMR  = Mifflin-St Jeor(new_weight, same height, age+elapsed, same sex)
new_TDEE = new_BMR × activity_multiplier
new_daily_calories = new_TDEE - daily_deficit
```

If new_daily_calories drops below the safe floor, reduce the weekly rate rather than the calorie intake. When recalculating, also update the protein target based on the new interim target weight.

---

## Non-Weight Progress Indicators

Weight is noisy (±2–5 lbs daily from water, sodium, glycogen, hormones). Encourage users to track additional metrics for a fuller picture:

| Indicator | How to Measure | Typical Change |
|---|---|---|
| Waist circumference | Tape measure at navel level, morning, relaxed | ↓ 0.5–1 inch per 10 lbs lost |
| Body fat % | Smart scale, calipers, or DEXA scan | Varies; ~1–2% per 10 lbs for most people |
| Energy level | Self-rated 1–10, morning and afternoon | Often improves after initial adaptation (1–2 weeks) |
| Clothing fit | Note how specific garments fit weekly | Noticeable after ~10 lbs; often motivating before scale moves |
| Sleep quality | Self-rated or tracked via wearable | Often improves with weight loss and better nutrition |

These matter because the scale can stall while body composition continues to improve. Including non-weight goals in each milestone helps users stay motivated through plateaus and builds a healthier relationship with progress.

---

## Plateau Science

Plateaus are normal and expected. Brief reference for when users report stalls:

**Common causes:**
- Metabolic adaptation (adaptive thermogenesis)
- Water retention masking fat loss (the "whoosh effect")
- Unconscious reduction in NEAT (non-exercise activity)
- Gradual calorie creep in tracking

**Evidence-based strategies:**
1. Reassess portion sizes and tracking accuracy
2. Structured diet break: 1–2 weeks at maintenance calories (restores leptin, reduces cortisol)
3. Increase NEAT: more walking, standing, daily movement
4. Prioritize sleep (7–9 hours) — sleep deprivation increases hunger hormones
5. Manage stress — cortisol promotes water retention
6. Recalculate TDEE at current weight — the original deficit may no longer be sufficient

---

## BMR — Katch-McArdle Equation (Alternative)

Use this when the user knows their body fat percentage. It can be more accurate than Mifflin-St Jeor for very lean or very obese individuals because it accounts for lean body mass directly.

```
lean_body_mass_kg = weight_kg × (1 - body_fat_percentage / 100)
BMR = 370 + (21.6 × lean_body_mass_kg)
```

**When to prefer Katch-McArdle over Mifflin-St Jeor:**
- User has a recent DEXA scan or reliable body fat measurement
- User is very muscular (BMI overestimates fat)
- User has BMI ≥ 40 (Mifflin-St Jeor may overestimate BMR)

If the user doesn't know their body fat %, stick with Mifflin-St Jeor.

---

## Daily Macronutrient Targets During Weight Loss

The diet-tracking-analysis skill reads daily targets directly from weight-loss-planner output instead of recalculating them. Protein is always anchored to body weight; fat varies by diet mode; carbs fill the remainder.

### Diet Mode Fat Ranges

| Diet Mode | Fat Range | Fat Midpoint |
|---|---|---|
| Healthy U.S.-Style (USDA) | 20–35% | 27.5% |
| Balanced / Flexible | 25–35% | 30% |
| High-Protein | 25–35% | 30% |
| Low-Carb | 40–50% | 45% |
| Keto | 65–75% | 70% |
| Mediterranean | 25–35% | 30% |
| Plant-Based | 20–30% | 25% |
| IF (16:8 / 5:2) | Use the chosen macro split's fat range | — |

If no diet mode is specified, default to **Balanced (fat 25–35%)**.

### Calculation

All targets are expressed as **ranges**. When a single display value is needed for simplicity, use the **midpoint** of the range.

Given:
- `weight_kg` = user's current weight in kg
- `totalCal` = daily calorie target (from TDEE minus deficit)
- `fat_pct_low`, `fat_pct_high` = from the user's diet mode (see table above)

```
Calories:
  range    = totalCal - 100  to  totalCal + 100 kcal
  display  = totalCal (midpoint)

Protein (always from body weight, not percentage):
  range    = weight_kg × 1.2  to  weight_kg × 1.6 g
  display  = weight_kg × 1.4 g (midpoint)
  calories = protein_g × 4

Fat (from diet mode):
  range    = totalCal × fat_pct_low ÷ 9  to  totalCal × fat_pct_high ÷ 9 g
  display  = totalCal × fat_pct_mid ÷ 9 g (midpoint)
  calories = fat_g × 9

Carbohydrate (derived — fills remaining calories):
  display  = (totalCal − protein_display×4 − fat_display×9) ÷ 4 g
  max      = (totalCal − protein_min×4 − fat_min×9) ÷ 4 g
  min      = (totalCal − protein_max×4 − fat_max×9) ÷ 4 g
  calories = carb_g × 4
```

**Key principle:** The ranges are the real targets. The display values (midpoints) are shown for convenience when a single number is needed (e.g., in the summary table). In coaching and suggestions, always reference the range to give the user flexibility.

### Example (weight = 70 kg, totalCal = 1,800 kcal, Balanced mode — fat 25–35%)

| Macro | Range | Display (midpoint) | Calories |
|---|---|---|---|
| Calories | 1,700–1,900 kcal | 1,800 kcal | — |
| Protein | 84–112 g | 98 g | 392 kcal |
| Fat | 50–70 g | 60 g | 540 kcal |
| Carbohydrate | 155–234 g | 217 g | 868 kcal |

### Guidelines by User Profile

| User Profile | Protein | Fat | Carbs | Notes |
|---|---|---|---|---|
| General / low activity | ×1.2–1.4 g/kg | 25–30% of kcal | remainder | Standard for moderate weight loss |
| Strength training | ×1.4–1.6 g/kg | 25–30% of kcal | remainder | Higher protein supports muscle repair |
| Older adults (50+) | ×1.4–1.6 g/kg | 25–35% of kcal | remainder | Higher protein counters sarcopenia |
| Low-carb preference | ×1.4–1.6 g/kg | 30–35% of kcal | remainder (lower) | User preference; ensure min ~100g carbs for brain function |

### Practical Notes

- **Protein** is the priority macro during a deficit — it preserves muscle mass, supports satiety, and has the highest thermic effect of food (~20–30% of calories burned during digestion)
- **Fat** should not drop below 20% of total calories — essential for hormone production (especially important during sustained calorie restriction)
- **Carbohydrates** are the flexible macro that fills remaining calories after protein and fat targets are met
- When recalculating at a new weight, update protein target using the new current weight; fat % stays anchored to total calories
- These targets are for the overall daily total — individual meal distribution should follow the user's meal template (see diet-tracking-analysis skill for per-meal checkpoint logic)
