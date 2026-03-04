# USER.md Format Reference

This file documents the expected structure of `USER.md`, which is created by the onboarding skill and consumed by downstream skills like this one.

The skill should be flexible when parsing — field names may vary slightly, and not all fields will always be present. Look for semantic matches, not exact strings.

## Expected Fields

### Required for this skill
```markdown
## Basic Info
- Name: [string]
- Age: [number]
- Sex: [Male / Female]
- Height: [X'X" or X cm]
- Current Weight: [X lbs or X kg]

## Activity & Lifestyle
- Activity Level: [Sedentary / Lightly Active / Moderately Active / Very Active / Extremely Active]
- Activity Description: [free text — what they actually do day-to-day]
```

### Optional (nice to have)
```markdown
- Target Weight: [X lbs or X kg]
- Health Conditions: [any relevant conditions]
- Dietary Restrictions: [vegetarian, allergies, etc.]
```

### Preferences section (accumulated over time)
```markdown
## Preferences

### Dietary
- [YYYY-MM-DD] Food likes, dislikes, allergies, flavor preferences

### Exercise
- [YYYY-MM-DD] Activity preferences, dislikes, physical limitations

### Scheduling & Lifestyle
- [YYYY-MM-DD] Work schedule, busy days, eating patterns

### Cooking & Kitchen
- [YYYY-MM-DD] Equipment, cooking skill, meal prep willingness

### General Notes
- [YYYY-MM-DD] Motivation details, communication preferences, pace
```

This section is appended to over time as users reveal preferences during conversations. Not all entries will be present from onboarding — preferences accumulate across sessions. All skills that read USER.md should check for and use this section when generating personalized content.

## Parsing Guidelines

- If the USER.md uses different section headers (e.g., "Profile" instead of "Basic Info"), that's fine — look for the data fields, not the headers.
- Heights might appear as `5'10"`, `5 ft 10 in`, `178 cm`, or `70 inches` — handle all common formats.
- Weights might be in lbs or kg — check for units and convert as needed.
- Activity level might be the standard label or a free-text description — map it to the closest standard level for TDEE calculation.
- If `Target Weight` is already present, you can pre-fill Step 3 but still confirm with the user.
