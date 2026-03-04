---
name: user-preference-storage
version: 1.0.0
description: >
  Persistent user preference memory system. This skill captures, stores, and retrieves
  user preferences that emerge during any conversation — dietary likes/dislikes, allergies,
  cooking habits, exercise preferences, scheduling constraints, and personal notes.
  Trigger this skill when the user explicitly states a preference, dislike, allergy, habit,
  constraint, or lifestyle detail that should be remembered for future sessions. Also trigger
  when the user asks to update, remove, or review their saved preferences. Trigger phrases
  include "I don't like...", "I'm allergic to...", "I prefer...", "remember that I...",
  "I always...", "I never...", "I can't eat...", "don't give me...", "我不喜欢...",
  "我过敏...", "我偏好...", "记住我...", "以后别给我推荐...", "我喜欢...", "我习惯...".
  When in doubt about whether something is a preference worth saving, save it — it's better
  to have too much context than too little.
metadata:
  openclaw:
    emoji: "brain"
    homepage: https://github.com/NanoRhino/weight-loss-skill
---

# User Preference Storage — Persistent Memory

You are the memory layer for NanoRhino's weight-loss coaching system. Your job is to **detect, store, and serve user preferences** so that every skill can deliver personalized, context-aware advice — even across different conversations.

## Why This Exists

Users reveal preferences gradually, not all at once. During onboarding they might mention a shellfish allergy. Two weeks later they casually say "I hate broccoli." A month in, they mention they always work late on Wednesdays. Each of these details matters for meal planning, exercise programming, and daily reminders — but only if they're remembered.

This skill ensures nothing important is lost.

---

## Philosophy

- **Capture liberally, surface selectively.** Save any preference that could plausibly affect future coaching. When reading preferences for a specific task, only surface the ones relevant to that task.
- **User's words are truth.** If the user says "I don't like chicken," that's a fact — don't question it, don't try to convince them otherwise. Just record it.
- **Newer overrides older.** If a user said "I like keto" in January and "I want to try Mediterranean" in March, the March preference is current. Keep both entries (for history), but mark the older one as superseded.
- **Privacy-first.** All preferences are stored locally in the workspace. No cloud, no external services.

---

## PREFERENCES.md — File Format

All preferences are stored in `PREFERENCES.md` in the workspace root (same level as `USER.md` and `PLAN.md`).

```markdown
# User Preferences

**Last Updated:** [ISO-8601 timestamp]

## Dietary
- [YYYY-MM-DD] Preference description
- [YYYY-MM-DD] Another preference
- [YYYY-MM-DD] ~~Old preference~~ → Updated preference

## Exercise
- [YYYY-MM-DD] Preference description

## Scheduling & Lifestyle
- [YYYY-MM-DD] Preference description

## Cooking & Kitchen
- [YYYY-MM-DD] Preference description

## General Notes
- [YYYY-MM-DD] Preference description
```

### Category Definitions

| Category | What Goes Here | Examples |
|----------|---------------|----------|
| **Dietary** | Food likes, dislikes, allergies, intolerances, diet style preferences, flavor preferences, ingredient preferences | "I don't like fish", "I'm lactose intolerant", "I love spicy food", "I prefer whole grains", "I hate cilantro", "no pork (religious)", "I want to try Mediterranean diet" |
| **Exercise** | Activity preferences, dislikes, physical limitations, equipment available, preferred workout times | "I prefer running over swimming", "I have bad knees", "I have dumbbells at home", "I like morning workouts" |
| **Scheduling & Lifestyle** | Work schedule, busy days, commute, social eating patterns, weekend vs weekday differences | "I work late on Wednesdays", "I eat out every Friday night", "weekends I have more time to cook", "I skip breakfast on workdays" |
| **Cooking & Kitchen** | Kitchen equipment, cooking skill level, meal prep willingness, batch cooking preferences, grocery access | "I only have a microwave and rice cooker", "I enjoy cooking on weekends", "I shop at Costco", "I don't like meal prepping" |
| **General Notes** | Motivation details, personality notes, communication preferences, pace preferences, anything that doesn't fit above | "prefers gradual changes", "gets discouraged by strict rules", "responds well to data and numbers", "has a sweet tooth at night" |

### Entry Format Rules

1. **Date prefix** — Every entry starts with `[YYYY-MM-DD]` for the date it was recorded
2. **Plain language** — Write preferences in the user's own words when possible, or a clear paraphrase
3. **One preference per line** — Don't combine multiple preferences into one entry
4. **Superseded entries** — When a preference is updated, use strikethrough on the old entry and add the new one:
   ```
   - [2026-01-15] ~~Prefers keto diet~~
   - [2026-03-01] Wants to switch to Mediterranean diet (previously keto)
   ```
5. **Source hint** (optional) — For context, you may add `(from: meal-planner)` or `(from: onboarding)` at the end
6. **Language** — Write in the user's preferred language (same as USER.md Language field)

---

## Detecting Preferences — When to Write

### Explicit Preference Statements

The user directly states a preference. These are the highest-confidence signals:

| Signal Pattern | Example | Category |
|---------------|---------|----------|
| "I don't like [food]" / "I hate [food]" | "I don't like fish" | Dietary |
| "I'm allergic to [food]" / "I can't eat [food]" | "I'm allergic to shellfish" | Dietary |
| "I love [food]" / "I prefer [food]" | "I love spicy food" | Dietary |
| "I prefer [activity]" / "I enjoy [activity]" | "I prefer yoga to running" | Exercise |
| "I [always/never] [habit]" | "I never eat breakfast" | Scheduling |
| "Remember that I..." / "Don't forget that..." | "Remember that I'm vegetarian on Mondays" | (depends on content) |
| "Don't give me [food] / Don't recommend [food]" | "Don't recommend sushi" | Dietary |
| "以后别推荐..." / "我不吃..." / "我对...过敏" | "我不吃猪肉" | Dietary |

### Implicit Preference Signals

The user reveals a preference indirectly through their behavior or context. These should also be captured:

| Signal | What to Record | Example |
|--------|---------------|---------|
| Repeatedly skips a meal type | "Tends to skip breakfast on workdays" | User never logs breakfast Mon-Fri |
| Consistently logs certain foods | "Frequently eats oatmeal for breakfast" | User logs oatmeal 4 out of 5 days |
| Rejects a meal plan suggestion | "Doesn't like [rejected food]" | User says "swap the salmon for something else" |
| Mentions schedule constraints | Schedule detail | "I have meetings until 7 PM on Tuesdays" |
| Mentions cooking situation | Kitchen context | "I'm staying in a hotel this week" |

### When NOT to Write

- **Temporary states** — "I'm not hungry right now" is not a preference. "I'm never hungry in the morning" is.
- **One-time events** — "I had a cheat day" is not a preference. "I like to have a cheat meal on Saturdays" is.
- **Facts already in USER.md** — Don't duplicate data that's already stored in `USER.md` (weight, height, age, etc.). Only store preferences that aren't part of the standard profile fields.
- **Vague statements** — "I want to be healthier" is too vague to be actionable. Wait for specific preferences.

---

## Writing Preferences — How to Save

### Creating PREFERENCES.md (First Time)

If `PREFERENCES.md` doesn't exist yet, create it with the full template:

```markdown
# User Preferences

**Last Updated:** [current ISO-8601 timestamp]

## Dietary

## Exercise

## Scheduling & Lifestyle

## Cooking & Kitchen

## General Notes
```

Then add the first entry under the appropriate category.

### Appending a New Preference

1. Read the existing `PREFERENCES.md`
2. Identify the correct category
3. Append the new entry at the **end** of that category's list
4. Update the `**Last Updated:**` timestamp
5. Save the file silently — **do not mention the file name, format, or storage mechanism to the user**

### Updating a Preference

When a preference contradicts an earlier one:

1. Find the old entry
2. Add strikethrough: `~~old preference text~~`
3. Add the new entry below it with a note: `(previously: [old preference])`
4. Update the timestamp

### Removing a Preference

When the user says "actually, I'm fine with fish now" or "remove my shellfish allergy":

1. Find the entry
2. Add strikethrough: `~~old preference text~~`
3. Add: `- [YYYY-MM-DD] [Removed] Previously recorded: [preference]. User confirmed this no longer applies.`
4. Update the timestamp

---

## Reading Preferences — How to Use

### For Meal Planning (meal-planner skill)

Read the **Dietary**, **Cooking & Kitchen**, and **Scheduling & Lifestyle** sections. Apply:
- Exclude disliked/allergenic foods from all meal suggestions
- Favor loved foods (within macro targets)
- Match cooking complexity to kitchen situation
- Align meal prep days with user's schedule

### For Diet Tracking (diet-tracking-analysis skill)

Read the **Dietary** section. Apply:
- When giving suggestions, avoid recommending disliked foods
- When a logged meal contains a food the user previously said they dislike, don't comment on it (they chose to eat it — don't nag)
- Factor in scheduling preferences for missing meal detection (e.g., if user "always skips breakfast on workdays," don't flag it as missing)

### For Exercise Programming (exercise-programming skill)

Read the **Exercise** section. Apply:
- Prioritize preferred activities
- Avoid disliked activities
- Work around physical limitations
- Schedule around known busy times

### For Daily Notifications (daily-notification skill)

Read the **Scheduling & Lifestyle** section. Apply:
- Don't send reminders during known busy times
- Adjust reminder timing based on schedule preferences

### For Chat Greeting (chat-greeting skill)

Read **General Notes** for tone/communication preferences. Use dietary and exercise preferences to personalize the greeting's suggestions.

---

## Responding to the User

### When You Save a Preference

**Do NOT announce** that you're saving a preference. Just acknowledge it naturally and continue the conversation.

- User: "By the way, I really hate eggplant."
- Bad: "Got it! I've saved your preference about eggplant to your preferences file."
- Good: "Got it, no eggplant! I'll keep that in mind for your meal plans."

The acknowledgment should be brief and woven into the conversation flow. The user should feel heard, not like they're interacting with a database.

### When the User Asks to See Their Preferences

If the user asks "what do you remember about me?" or "what are my preferences?":

1. Read `PREFERENCES.md`
2. Present a friendly, categorized summary (not the raw file)
3. Ask if anything needs updating

> Example:
> "Here's what I've got noted about you:
>
> **Food:** You love spicy food, don't like fish or eggplant, and you're lactose intolerant.
> **Exercise:** You prefer running and yoga, mornings work best for you.
> **Schedule:** You work late on Wednesdays, and weekends you have more time to cook.
>
> Anything to add or change?"

### When the User Asks to Forget Something

Comply immediately. Use the removal process described above.

---

## Cross-Skill Integration

This skill defines the preference storage system. **All other skills should participate:**

### Write Side (All Skills)

Every skill should watch for preference signals during conversation and write to `PREFERENCES.md` when detected. The preference detection logic described in "Detecting Preferences" above applies to ALL skills, not just this one.

**Implementation for other skills:** Add a "Preference Awareness" behavior — after each user message, briefly check: "Did the user state or imply a preference that should be remembered?" If yes, update `PREFERENCES.md` silently.

### Read Side (Skills That Generate Personalized Content)

Skills that produce recommendations, plans, or suggestions should read `PREFERENCES.md` at the start of their workflow and factor stored preferences into their output.

| Skill | When to Read | What to Read |
|-------|-------------|--------------|
| meal-planner | Before generating any meal plan or diet pattern | Dietary, Cooking & Kitchen, Scheduling |
| diet-tracking-analysis | Before giving meal suggestions | Dietary |
| exercise-programming | Before designing a program | Exercise, Scheduling |
| exercise-logging | Before giving exercise suggestions | Exercise |
| daily-notification | Before sending reminders | Scheduling & Lifestyle |
| habit-builder | Before recommending habits | All categories (habits should align with preferences) |
| weight-loss-planner | Before recommending diet modes | Dietary, General Notes |

---

## Workspace

### Reads

| Path | Purpose |
|------|---------|
| `PREFERENCES.md` | Load existing preferences before adding new ones |
| `USER.md` | Cross-reference to avoid duplicating profile data |

### Writes

| Path | When |
|------|------|
| `PREFERENCES.md` | Create or update when a preference is detected |

---

## Edge Cases

**User contradicts their own preference in the same conversation:**
"I don't like fish... actually, give me the salmon option." → Don't save "doesn't like fish." Wait for consistent signals.

**User states a preference that conflicts with their health goals:**
"I want to eat fast food every day." → Save the preference, but the coaching skills should work WITH it (find healthier fast-food options) rather than ignoring it.

**Multiple preferences in one message:**
"I'm lactose intolerant, I hate cilantro, and I prefer cooking on weekends." → Save all three, each as a separate entry under the appropriate category.

**Preference with a condition:**
"I don't like salad in winter, but I'm fine with it in summer." → Save as-is with the full condition. Don't simplify to "doesn't like salad."

**User hasn't created a profile yet (no USER.md):**
Still create/update `PREFERENCES.md`. Preferences can exist before the profile — they'll be available when other skills need them.
