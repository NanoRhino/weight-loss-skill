# Weekly Summary Template

## Trigger Conditions

- **Sunday auto-append**: If today is Sunday and the user sends any message in this conversation, append the weekly summary after handling the user's message. Separate with a divider (e.g., `---`). If the user has already received a summary this Sunday in the current conversation, do not repeat it.
- **Manual trigger**: User explicitly asks for a summary at any time (e.g., "weekly summary", "how did I do this week")

**Sunday auto-append format:**

```
[Normal response to user's message]

---

📊 Here's your weekly exercise summary:

[Weekly summary content]
```

---

## Summary Structure

### 1. Overview Line

Format: **[sessions] sessions · [total duration] min · ≈[total calories] kcal**

Example:
- "This week: 5 sessions · 210 min total · ≈1,580 kcal"

---

### 2. Category Breakdown

Show time and session count per category. Only include categories that were logged.

Example:
```
Cardio: 3 sessions, 120 min (57%)
Strength: 1 session, 60 min (29%)
Flexibility: 1 session, 30 min (14%)
```

---

### 3. WHO Comparison

Compare against WHO Physical Activity Guidelines:
- ✅ / ❌ 150 min moderate-intensity aerobic (or 75 min vigorous, or equivalent combo)
- ✅ / ❌ 2+ strength training sessions per week

Conversion for mixed intensity: 1 min vigorous = 2 min moderate.

Example:
- "✅ Aerobic met: 150 min moderate intensity (target 150 min)"
- "❌ Strength insufficient: 1 session this week (recommend at least 2)"

---

### 4. Week-over-Week Trend

Compare with previous week's data. Show direction indicators:

| Metric | Symbols |
|--------|---------|
| Frequency | ↑ increased / → same / ↓ decreased |
| Duration | ↑ increased / → same / ↓ decreased |
| Calories | ↑ increased / → same / ↓ decreased |

Example:
- "vs last week: frequency 5→5 →, duration 180→210 min ↑, calories 1,320→1,580 ↑"

If no previous week data is available, skip this section.

---

### 5. Goal-Aligned Insight

One paragraph of analysis based on user's `fitness_goal` from USER.md:

- **lose_fat**: Focus on calorie burn, whether aerobic volume is sufficient, suggest optimal fat-burning intensities
- **build_muscle**: Assess strength training frequency and volume, note if recovery days are adequate
- **stay_healthy**: Celebrate consistency, note variety of activities, encourage maintaining the habit
- **improve_endurance**: Comment on aerobic progression (distance, duration, pace trends), note if base-building is on track

If `fitness_goal` is not set, give general balanced feedback.

---

### 6. Next Week Suggestions

1-2 specific, actionable recommendations. Must be concrete (not generic "keep it up").

Good examples:
- "Try adding a 30-min strength session next week — bodyweight exercises are a good starting point."
- "Your running pace was consistent this week. Try one interval session next week: 4×400m fast with 2-min rest."

Bad examples (too vague):
- "Keep up the good work!"

---

## Edge Cases

### No exercise logged this week

Don't guilt-trip. Acknowledge it neutrally and encourage:
- "No exercise logged this week. That's okay — every week is a fresh start. Even a 20-min walk is a great beginning."

### Only 1-2 sessions logged

Still produce the full summary. Emphasize that starting is the hardest part. Suggest realistic, small additions.

### Very high volume week

Acknowledge the effort, but gently check on recovery:
- "Big week! Make sure to build in adequate recovery next week."

---

## Output Format

The weekly summary is returned as a `message` string in the non-exercise response format. Structure the message using the sections above, with clear line breaks between sections. Do not use JSON for the summary content itself — write it as natural, readable text following the template structure.
