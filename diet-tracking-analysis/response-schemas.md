# Response Examples

## Setting a Target

```
✅ Target set!

📋 Daily targets:
Calories: 1500 kcal
Protein: 91g (78–104g)
Carbs: 181g (140–222g)
Fat: 46g (33–58g)

Meal allocation: Breakfast 450 / Lunch 600 / Dinner 450 kcal

Start logging your first meal!
```

## Food Log Reply

```
📝 Lunch logged!

🍽 This meal total: 460 kcal | Protein 38g | Carbs 42g | Fat 14g
· Chicken breast salad — one large plate — 280 kcal
· Whole wheat bread — 2 slices — 180 kcal

📊 So far today: 839 kcal ✅ | Protein 62g ✅ | Carbs 87g ⬇️ | Fat 33g ✅
Protein and fat are on track, carbs slightly low — adding a bit of grain at dinner will sort that out.

✨ Great protein choice with the chicken breast!
💡 Next time: Try adding half a cup of quinoa to your salad for an extra carb boost.
```

## Food Log with Adjustment Needed

```
📝 Lunch logged!

🍽 This meal total: 900 kcal | Protein 15g | Carbs 128g | Fat 35g
· Fried rice — ~1 bowl — 520 kcal
· Bubble tea — 1 cup — 380 kcal

📊 So far today: 1279 kcal ⬆️ | Protein 39g ⬇️ | Carbs 173g ⬆️ | Fat 49g ✅
Calories and carbs are running high while protein is low — the rice + bubble tea combo pushed carbs up.

⚡ Right now: Swap the bubble tea for unsweetened tea, and rice reduced to half a bowl — the other half can go with dinner. Protein is low, so dinner add some high-protein food, like your usual grilled chicken breast or eggs. After adjustment, this meal would total ~340 kcal, protein 8g, carbs 58g, fat 10g.
```

## Food Log with Adjustment Needed — Already Eaten

```
📝 Lunch logged!

🍽 This meal total: 900 kcal | Protein 15g | Carbs 128g | Fat 35g
· Fried rice — ~1 bowl — 520 kcal
· Bubble tea — 1 cup — 380 kcal

📊 So far today: 1279 kcal ⬆️ | Protein 39g ⬇️ | Carbs 173g ⬆️ | Fat 49g ✅
Calories and carbs are running high while protein is low — the fried rice and bubble tea are tasty but carb-heavy.

💡 Next meal: Dinner go heavier on high-protein food — like your usual grilled chicken breast or steamed fish — and lighter on carbs, keep rice to half a bowl or skip it.
```

## Daily Summary — Calories On Track or Over

When the user closes the day ("今天都吃完了", "done eating for today", etc.), reply with the daily summary only. **Do NOT add any sign-off** — no "晚安" / "goodnight" / 🌙 / 💤 / "明天见" / "see you tomorrow". "Done eating" ≠ going to sleep. End with the suggestion or summary line — nothing after it.

```
📊 Today's summary:
Calories 1259 kcal ✅
Protein 94g ✅
Carbs 133g ⚠️ Low
Fat 34g ⚠️ Low

Nice job overall! Carbs and fat are a bit low — try adding half a bowl of rice and a handful of nuts tomorrow 💪
```

## Daily Summary — Calories Under Target (Below BMR)

```
📊 Today's summary:
Calories 980 kcal ⚠️ Low
Protein 72g ✅
Carbs 98g ⚠️ Low
Fat 28g ⚠️ Low

🍽 Today's total (~980 kcal) is below your resting metabolism (~1280 kcal) — I'd recommend adding a snack. Some healthy fat or protein, like the nuts you had last week or a cup of yogurt.
```

## Daily Summary — Calories Under Target (Above BMR)

```
📊 Today's summary:
Calories 1180 kcal ⚠️ Low
Protein 88g ✅
Carbs 110g ⚠️ Low
Fat 32g ⚠️ Low

💡 Today's calories are a bit under target but still above your resting metabolism, so no worries. If you get hungry later, feel free to grab a small snack — if not, no need to eat more.
```

## Meal Place Collection Prompt (Workdays Only)

Appended after the food log reply when the current meal's venue is not yet recorded. See `meal-place-rules.md` for full logic.

### First-time collection (place is null, ask_count < 3)

Chinese:
```
🍽 这顿工作日一般在哪吃？ 🏠 在家 ｜ 📦 外卖 ｜ 其他
```

English:
```
🍽 Where do you usually have this meal on workdays? 🏠 Home | 📦 Takeout | Other
```

Default top-2 options per meal:

| Meal | Option 1 | Option 2 |
|------|----------|----------|
| breakfast | 🏠 在家 / Home | 📦 外卖 / Takeout |
| lunch | 🏢 食堂 / Cafeteria | 📦 外卖 / Takeout |
| dinner | 🏠 在家 / Home | 📦 外卖 / Takeout |

### Drift detection confirmation (consecutive_mismatches >= 3)

Chinese:
```
🍽 最近几次午饭好像都不在食堂了，是换地方了吗？ 📦 外卖 ｜ 没变还是🏢食堂
```

English:
```
🍽 Your last few lunches don't seem to be at the cafeteria anymore — has it changed? 📦 Takeout | No, still 🏢 Cafeteria
```
