# Diet Modes Reference

Detailed specifications for each supported diet mode. The SKILL.md overview table gives the quick summary — this file has the full implementation details.

## Healthy U.S.-Style (USDA Dietary Guidelines)

**Macro Split:** 10–35% protein / 45–65% carbs / 20–35% fat (AMDR ranges from the Dietary Guidelines for Americans 2020–2025)
**Philosophy:** Follow the USDA's recommended Healthy U.S.-Style Dietary Pattern — one of three patterns recommended by the DGA (alongside Healthy Mediterranean-Style and Healthy Vegetarian). Emphasizes nutrient-dense whole foods across all food groups.
**Best for:** Users who want a government-backed, evidence-based baseline; general health maintenance; those new to structured eating.

**Core principles:**
- Fruits and vegetables: fill half the plate
- Grains: at least half should be whole grains
- Dairy: low-fat or fat-free milk, yogurt, cheese
- Protein: variety including seafood, lean meats, poultry, eggs, legumes, nuts, seeds, soy
- Oils: healthy oils (vegetable oils, oils in nuts/seafood) in place of solid fats

**Daily limits:**
- Added sugars: <10% of total calories
- Saturated fat: <10% of total calories
- Sodium: <2,300 mg
- Alcohol: up to 1 drink/day (women), 2 drinks/day (men) — if consumed at all

**In a weight loss context:** The AMDR ranges are very broad (e.g., protein 10–35%). For a calorie deficit, aim for the higher end of protein (25–35%) to preserve muscle, and moderate fat (20–30%) to leave room for adequate carbohydrates. The `diet-tracking-analysis` skill uses this pattern's ranges as its default (fat 20–35%, protein by body weight at 1.2–1.6 g/kg).

**Key advantage:** Backed by the most extensive body of nutrition research. No food groups excluded. Flexible within the AMDR ranges.
**Key risk:** The ranges are wide enough that users may need more specific guidance — which is why the other diet modes below offer narrower targets for specific goals.

---

## Balanced / Flexible Dieting (IIFYM)

**Macro Split:** 25–35% protein / 35–45% carbs / 25–35% fat (default: 30/40/30)
**Philosophy:** No food restrictions. Hit your calorie and macro targets, and the rest is up to you.
**Best for:** Most users, especially beginners. Lowest barrier to adherence.

**Meal building blocks:**
- Each meal: 1 palm-sized protein + 1 fist-sized carb + 1 thumb-sized fat + unlimited non-starchy veggies
- Snacks: aim for at least one with protein to stay satiated

**Sample day structure (1,850 cal):**
- Breakfast: oatmeal + protein powder + banana + peanut butter
- Lunch: chicken burrito bowl (rice, beans, chicken, veggies, salsa)
- Dinner: salmon + sweet potato + roasted broccoli
- Snack: Greek yogurt + berries

**Key advantage:** Flexible. Pizza on Friday? Fine — adjust the rest of the day.
**Key risk:** Requires tracking to work. Without monitoring, "flexible" can drift into "uncontrolled."

---

## High-Protein

**Macro Split:** 35–45% protein / 25–35% carbs / 25–35% fat (default: 40/30/30)
**Philosophy:** Prioritize protein to preserve muscle during a calorie deficit, increase satiety, and boost thermic effect of food.
**Best for:** People who lift weights, active individuals, anyone who finds protein keeps them fuller longer.

**Daily protein target:** 0.8–1.0g per lb of body weight. For a 200-lb person = 160–200g protein/day.

**Practical protein targets per meal:**
| Calories/day | Protein/day | Per meal (3 meals) | Per meal (4 meals) |
|---|---|---|---|
| 1,500 | 150g | 50g | 38g |
| 1,800 | 180g | 60g | 45g |
| 2,000 | 200g | 67g | 50g |

**High-protein foods (per oz or serving):**
| Food | Serving | Protein | Calories |
|---|---|---|---|
| Chicken breast | 4 oz (113g) | 26g | 120 |
| Ground turkey (93% lean) | 4 oz | 22g | 150 |
| Salmon | 4 oz | 23g | 160 |
| Eggs | 2 large | 12g | 140 |
| Greek yogurt (nonfat) | 1 cup (227g) | 20g | 130 |
| Cottage cheese (2%) | 1 cup | 24g | 180 |
| Canned tuna | 1 can (5 oz) | 27g | 120 |
| Whey protein powder | 1 scoop (~30g) | 24g | 120 |
| Shrimp | 4 oz | 24g | 100 |
| Tofu (extra firm) | 4 oz | 11g | 90 |

**Key advantage:** Highest satiety per calorie. Muscle preservation in a deficit.
**Key risk:** Can feel monotonous. Rotate protein sources to avoid "chicken fatigue."

---

## Low-Carb

**Macro Split:** 30–40% protein / 15–25% carbs / 40–50% fat (default: 35/20/45)
**Philosophy:** Reduce carbohydrates to lower insulin response and increase fat utilization. Not as extreme as keto.
**Best for:** People who feel sluggish or bloated with high-carb meals, or who notice better appetite control on fewer carbs.

**Daily carb target:** ~75–125g/day depending on total calories.

**Foods to emphasize:**
- Proteins: all lean meats, fish, eggs
- Fats: avocado, olive oil, nuts, cheese, butter
- Low-carb veggies: leafy greens, zucchini, cauliflower, bell peppers, mushrooms, asparagus
- Limited carbs: berries (best fruit choice), sweet potatoes (small portions), legumes

**Foods to minimize:**
- Bread, pasta, rice (or use in very small portions)
- Sugary drinks, juice
- Cereals, crackers
- Potatoes (large portions)

**Key advantage:** Many people report reduced hunger and more stable energy.
**Key risk:** Fiber intake can drop. Include plenty of non-starchy vegetables and consider a fiber supplement.

---

## Keto (Ketogenic)

**Macro Split:** 20–25% protein / 5–10% carbs / 65–75% fat (default: 20/5/75)
**Philosophy:** Extreme carb restriction to shift the body into ketosis (burning fat as primary fuel).
**Best for:** Experienced dieters who've tried keto before and liked it. Not recommended as a first approach.

**Daily carb target:** 20–30g net carbs (total carbs minus fiber).

**Note on protein:** Protein is kept moderate (20–25%) to avoid excess gluconeogenesis, which can interfere with ketosis. Higher protein intakes (>25%) may knock some individuals out of ketosis.

**Keto staple foods:**
- Proteins: fatty fish, beef, chicken thighs (skin-on), eggs, bacon
- Fats: avocado, olive oil, coconut oil, butter, heavy cream, cheese, nuts (macadamia, pecans)
- Veggies: spinach, kale, cauliflower, zucchini, mushrooms, broccoli (small portions)
- Snacks: pork rinds, cheese crisps, olives, fat bombs, celery + cream cheese

**Keto-incompatible foods:**
- Bread, pasta, rice, oats, cereal
- Fruit (except small amounts of berries)
- Sugar, honey, syrups
- Beans, legumes, most root vegetables
- Beer, sweet cocktails

**Adaptation period:** Warn the user about "keto flu" — fatigue, headaches, irritability during the first 1–2 weeks as the body adapts. Recommend extra water + electrolytes (sodium, potassium, magnesium).

**Key advantage:** Some people find appetite nearly disappears after adaptation.
**Key risk:** Extremely restrictive. Social eating is hard. Fiber and micronutrient deficiencies if not planned carefully. Not recommended below 1,800 cal/day without careful planning.

---

## Mediterranean

**Macro Split:** 20–30% protein / 40–50% carbs / 25–35% fat (default: 25/45/30)
**Philosophy:** Whole foods, healthy fats (olive oil), lean proteins (fish, poultry), abundant vegetables, whole grains. Inspired by traditional eating patterns of Mediterranean cultures.
**Best for:** Users focused on heart health, those who enjoy cooking, people who want a "lifestyle" rather than a "diet."

**Core principles:**
- Olive oil as primary cooking fat
- Fish/seafood 2–3x per week
- Poultry 2–3x per week
- Red meat sparingly (1x per week or less)
- Abundant vegetables, fruits, legumes, whole grains
- Nuts and seeds daily (small portions)
- Moderate dairy (yogurt, cheese)
- Red wine optional (1 glass with dinner — not required!)

**Sample staple meals:**
- Greek salad with grilled chicken + feta + olive oil dressing
- Baked salmon with lemon, capers, roasted vegetables
- Lentil soup with whole grain bread
- Shakshuka (eggs poached in tomato sauce) with pita
- Grilled shrimp over orzo with roasted tomatoes

**Key advantage:** Strong evidence base for cardiovascular health. Feels more like "eating well" than "dieting."
**Key risk:** Olive oil and nuts are calorie-dense. Portions of fats need to be measured carefully during a deficit.

---

## Intermittent Fasting — 16:8

**Macro Split:** Any (layer on top of chosen macro split; default to Balanced 30/40/30)
**Philosophy:** Compress all eating into an 8-hour window. The remaining 16 hours are fasted.
**Best for:** People who naturally skip breakfast, prefer larger meals, or find it easier to control calories by eating less frequently.

**Common eating windows:**
- 12:00 PM – 8:00 PM (most popular — skip breakfast, eat lunch/dinner)
- 10:00 AM – 6:00 PM (earlier window for morning exercisers)
- 2:00 PM – 10:00 PM (late schedule)

**Meal structure (defaults — adjustable):**
- Meal 1 (breaking fast): 40% of daily calories
- Meal 2 (dinner): 40% of daily calories
- Snack: 20% of daily calories

> If the user prefers a larger first meal and smaller snack, or wants to split more evenly, adjust to their preference while keeping the daily total on target.

**During the fast (allowed):**
- Water, black coffee, plain tea (no sugar, no cream)
- Zero-calorie beverages

**Key advantage:** Fewer meals = larger, more satisfying portions. Simplifies meal prep (fewer meals to plan).
**Key risk:** Can lead to overeating in the window if not tracking. Some people get irritable or low-energy during extended fasting. Not suitable for people with a history of disordered eating.

---

## Intermittent Fasting — 5:2

**Macro Split:** Any for normal days; low-calorie days are simplified.
**Philosophy:** Eat normally 5 days per week. On 2 non-consecutive days, eat only 500–600 calories.
**Best for:** People who hate daily restriction but can handle occasional very-low days.

**Structure:**
- **5 normal days:** Hit regular calorie target with chosen macro split
- **2 low days (non-consecutive):** 500 cal (women) or 600 cal (men)
  - Typically 2 small meals: e.g., 250-cal lunch + 250-cal dinner
  - Focus on protein + vegetables for maximum satiety on minimal calories
  - Example low day: scrambled eggs with spinach (lunch) + grilled chicken salad (dinner)

**Weekly calorie math:** Factor low days into the weekly average. If normal target is 1,850/day:
- 5 days × 1,850 = 9,250
- 2 days × 600 = 1,200
- Weekly total: 10,450 → daily average: ~1,493

So the normal days can actually be slightly higher if the weekly average needs to match a target.

**Key advantage:** Mental freedom on normal days. Only need willpower 2 days/week.
**Key risk:** Low days can feel brutal. Risk of binge eating on normal days to "compensate." Not for everyone.

---

## Plant-Based

**Macro Split:** 20–30% protein / 45–55% carbs / 20–30% fat (default: 25/50/25)
**Philosophy:** All or primarily plant-derived foods. Two sub-modes:
- **Vegan:** No animal products whatsoever
- **Vegetarian:** Allows dairy and eggs

**Best for:** Users with ethical, environmental, or health motivations for plant-based eating. Also works for users who just want to eat more plants.

**Protein sources (critical — this is the main challenge):**
| Food | Serving | Protein | Calories |
|---|---|---|---|
| Tofu (extra firm) | 4 oz (113g) | 11g | 90 |
| Tempeh | 4 oz | 21g | 220 |
| Lentils (cooked) | 1 cup | 18g | 230 |
| Black beans (cooked) | 1 cup | 15g | 230 |
| Edamame | 1 cup (shelled) | 18g | 190 |
| Chickpeas (cooked) | 1 cup | 15g | 270 |
| Seitan | 4 oz | 25g | 140 |
| Pea protein powder | 1 scoop | 24g | 120 |
| Greek yogurt (vegetarian) | 1 cup | 20g | 130 |
| Eggs (vegetarian) | 2 large | 12g | 140 |

**Key nutrients to watch:**
- **B12:** Supplement required for vegans (not found in plant foods)
- **Iron:** Plant iron (non-heme) is less bioavailable; pair with vitamin C to boost absorption
- **Omega-3:** Consider algae-based supplement (EPA/DHA) for vegans
- **Calcium:** Fortified plant milks, tofu made with calcium sulfate, leafy greens

**Key advantage:** High fiber intake naturally increases satiety. Associated with lower rates of heart disease.
**Key risk:** Hitting protein targets is harder (and more calorie-expensive) without animal products. Requires more intentional planning.
