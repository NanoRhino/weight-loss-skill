# Quick TDEE Estimation (Standalone Mode)

When this skill is used without a prior weight-loss-planner session, and the user doesn't have a calorie target, use this quick inline estimation. This is a simplified version — for a thorough plan with milestones, recommend the weight-loss-planner skill.

## Quick Flow

1. Ask: height, weight, age, sex, activity level
2. Calculate BMR (Mifflin-St Jeor):
   - Male: BMR = (10 × weight_kg) + (6.25 × height_cm) - (5 × age) + 5
   - Female: BMR = (10 × weight_kg) + (6.25 × height_cm) - (5 × age) - 161
3. Multiply by activity factor:
   - Sedentary: ×1.2
   - Lightly Active: ×1.375
   - Moderately Active: ×1.55
   - Very Active: ×1.725
4. Subtract a standard deficit:
   - Gentle (0.5 lb/week): -250 cal
   - Moderate (1 lb/week): -500 cal
   - Aggressive (1.5 lb/week): -750 cal
5. Check against safe floors: 1,200 (women) / 1,500 (men)

## Unit Conversions
```
weight_kg = weight_lbs / 2.205
height_cm = (feet × 12 + inches) × 2.54
```

## When to Recommend the Full Skill Instead

If the user wants milestones, phased plans, or has >20 lbs to lose, recommend the weight-loss-planner skill for a proper assessment. This quick calc is just to get a calorie number for meal planning when the user's primary ask is "tell me what to eat" rather than "build me a weight loss plan."
