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

**WHO Classification:**

| BMI Range | Classification |
|---|---|
| < 18.5 | Underweight |
| 18.5 – 24.9 | Normal weight |
| 25.0 – 29.9 | Overweight |
| 30.0 – 34.9 | Obese (Class I) |
| 35.0 – 39.9 | Obese (Class II) |
| ≥ 40.0 | Obese (Class III) |

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

### Activity Multipliers

| Level | Multiplier | Description |
|---|---|---|
| Sedentary | 1.2 | Desk job, little or no exercise |
| Lightly Active | 1.375 | Light exercise 1–3 days/week |
| Moderately Active | 1.55 | Moderate exercise 3–5 days/week |
| Very Active | 1.725 | Hard exercise 6–7 days/week |
| Extremely Active | 1.9 | Physical job + daily intense training |

### TDEE Range Calculation

People often misjudge their activity level. To give the user a more useful estimate, present TDEE as a **point estimate plus a range** spanning one level above and one level below the selected multiplier.

**Procedure:**
1. Based on the user's activity description, select the best-fit multiplier as the primary estimate
2. Identify the multiplier one level below (lower bound) and one level above (upper bound)
3. If the user is at the minimum (Sedentary), use Sedentary as the lower bound
4. If the user is at the maximum (Extremely Active), use Extremely Active as the upper bound

**Example:**
- User describes: "I go to the gym 3x/week and walk my dog daily"
- Best fit: Moderately Active (×1.55)
- Range: Lightly Active (×1.375) to Very Active (×1.725)
- BMR = 1,800 → TDEE = **2,790** (range: 2,475 – 3,105)

The range empowers the user to self-correct. Someone who says "I work out 5 days" but actually skips 2 days most weeks can look at the range and pick a more realistic number.

---

## Calorie Deficit Math

Core principle: approximately **3,500 calories ≈ 1 pound** of body fat. This is an approximation — individual variation exists, but it's the standard used in clinical practice.

| Weekly Loss Target | Daily Deficit |
|---|---|
| 0.5 lbs/week | 250 cal/day |
| 1.0 lbs/week | 500 cal/day |
| 1.5 lbs/week | 750 cal/day |
| 2.0 lbs/week | 1,000 cal/day |

**Daily Calorie Target:**
```
Daily_Calories = TDEE - Daily_Deficit
```

### Safe Minimums

| | Floor | Action if breached |
|---|---|---|
| Women | 1,200 cal/day | Set intake to 1,200; reduce loss rate; suggest adding exercise for additional deficit |
| Men | 1,500 cal/day | Set intake to 1,500; reduce loss rate; suggest adding exercise for additional deficit |

Going below these floors without medical supervision risks nutrient deficiencies, muscle loss, metabolic slowdown, and hormonal disruption.

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
- Is required_rate ≤ 2.0 lbs/week? If not → unsafe, suggest closest safe rate
- Is daily_calories ≥ safe minimum? If not → unsafe, adjust rate down

---

## TDEE Recalculation at New Weight

As the user loses weight, BMR drops and so does TDEE. Recalculate at each milestone:

```
new_BMR  = Mifflin-St Jeor(new_weight, same height, age+elapsed, same sex)
new_TDEE = new_BMR × activity_multiplier
new_daily_calories = new_TDEE - daily_deficit
```

If new_daily_calories drops below the safe floor, reduce the weekly rate rather than the calorie intake.

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
