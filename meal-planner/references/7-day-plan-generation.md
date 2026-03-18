# 7-Day Meal Plan Generation

> **Trigger:** Only when the user proactively requests a 7-day meal plan. Do not auto-generate or prompt the user about it.

## Time Estimate Notice

**Before starting generation**, send the user a brief heads-up about the expected wait time (adapt to the user's language):

> 没问题！7 天食谱内容比较多，生成大约需要 10–20 分钟，请稍等一下 ⏳

English equivalent:

> Sure! A full 7-day meal plan is quite detailed — it'll take about 10–20 minutes to generate. Hang tight ⏳

**Why:** The 7-day plan involves designing 21+ unique meals with precise macros, storage-tier considerations, and locale-appropriate foods. This takes noticeably longer than a normal chat reply. Setting expectations upfront prevents users from thinking something went wrong.

Send this message **immediately** after confirming the user wants the plan, **before** you begin generating the HTML file.

## Output as Markdown → HTML → S3 Link (Not Chat Text)

**CRITICAL: Generate the 7-day meal plan as a Markdown file, convert to HTML, upload to S3 — NOT as chat text.** The meal plan is too long to stream reliably in chat (messages get interrupted, context overflows, and it's hard for users to save). Instead:

1. **Write the meal plan as `MEAL-PLAN.md`** in the workspace, following the schema defined in `references/meal-plan-schema.md`. This file is the agent's reference copy. **Important: metadata keys (`Date`, `Calories`, `Mode`, `Macros`) MUST always be in English** — the HTML parser depends on these exact keys. Values can be localized.
2. **Run the export script** to convert to HTML and upload to S3:
   ```bash
   URL=$(bash {plan-export:baseDir}/scripts/generate-and-send.sh \
     --agent <YOUR_AGENT_ID> \
     --input MEAL-PLAN.md \
     --bucket nanorhino-im-plans \
     --username <USERNAME> \
     --workspace <AGENT_WORKSPACE_PATH> \
     --template meal-plan \
     --key meal-plan)
   ```
   **`--username` resolution:** Derive from the workspace path:
   - If workspace path contains `workspace-wechat-dm-{id}` → extract `{id}` as username (e.g., `accr51qz5uksxmi82ixyztd`)
   - Otherwise → use the agent ID (e.g., `007-zhuoran`)
   
   Shell one-liner to auto-detect:
   ```bash
   USERNAME=$(basename "$AGENT_WORKSPACE_PATH" | grep -oP 'workspace-wechat-dm-\K.*' || echo "$YOUR_AGENT_ID")
   ```
3. **Send the public URL to the user** via the message tool, with a brief summary. The URL is permanent: `https://nanorhino.ai/{username}/meal-plan.html`.
4. Adapt all content (food names, meal names, day names, tips) to the user's language.
5. Use full macro names matching the user's language — never abbreviate to P/C/F. English: `Protein`, `Carbs`, `Fat`; Chinese: `蛋白`, `碳水`, `脂肪`.

**Chat message template** (adapt to user's language):

> 你的 7 天食谱已经生成好了！点击这里查看：[链接]
>
> （这个链接是你的专属链接，永久有效，每次更新食谱后内容会自动刷新）
>
> **概要：** [X,XXX] kcal/天 · [饮食模式] · 蛋白 [X]g / 碳水 [X]g / 脂肪 [X]g
>
> 可以直接在浏览器里查看。有什么想调整的随时告诉我！

English equivalent:

> Your 7-day meal plan is ready! View it here: [link]
>
> **Summary:** [X,XXX] Cal/day · [Diet Mode] · Protein [X]g / Carbs [X]g / Fat [X]g
>
> You can view it directly in your browser. Let me know if you'd like to adjust anything!

**When a user asks for their meal plan link:**
1. Read `plan-url.json` → check the `meal-plan` key
2. If `expires_at` has NOT passed → send the existing `url`
3. If `expires_at` HAS passed → re-run the script with `MEAL-PLAN.md` to generate a new upload, then send the new URL

Build a 7-day meal plan based on the confirmed calories, macros, diet mode, and user preferences.

## Meal Structure

Default to **3 meals + 1–2 snacks** unless the user's diet mode dictates otherwise:
- **IF 16:8** → 2 meals + 1 snack within the eating window
- **IF 5:2** → Normal structure for 5 days; 2 low-calorie days with 2 small meals
- **All other modes** → 3 meals + 1–2 snacks

Typical calorie distribution (defaults — adjustable based on user preference and lifestyle):

| Component | % of Daily Calories | Example (1,850 kcal) |
|---|---|---|
| Breakfast | 25% | ~460 kcal |
| Lunch | 30% | ~555 kcal |
| Dinner | 30% | ~555 kcal |
| Snack(s) | 15% | ~280 kcal |

> These are starting defaults. If the user prefers a lighter breakfast and bigger dinner, or wants to shift snack calories into meals, adjust accordingly — the daily total is what matters.

## Food Selection Principles

**#1 Priority: Practicality and ease of execution.** A nutritionally perfect plan that's too hard to follow is worthless. Every meal should pass the test: "Would this person realistically make/buy/eat this on a busy weekday?" Nutritional optimization is important but secondary — a slightly less optimal meal that actually gets eaten beats a perfect meal that gets skipped.

**Locale-appropriate foods.** Use foods that match the user's country/region and are available at their local grocery stores, markets, or restaurants. Don't recommend foods that are hard to find or culturally unfamiliar unless the user asks for them.

- **US-based users:** grocery store staples — chicken breast, ground turkey, eggs, Greek yogurt, canned tuna, rice, oats, sweet potatoes, etc. Think Walmart, Trader Joe's, Costco.
- **China-based users:** chicken breast, eggs, tofu, fish/shrimp, brown rice/mixed-grain rice, leafy greens, legumes. Think Hema, Yonghui, wet markets.
- **Japan-based users:** chicken breast, fish, tofu, natto, brown rice, miso soup, vegetables. Think supermarkets, convenience stores (konbini are a legitimate meal source in Japan).
- **Other regions:** Adapt accordingly based on local staple foods, common proteins, and typical grocery availability. When unsure, ask the user what's easy for them to get.

**Build around cooking conditions:**

| Cooking Situation | Plan Strategy |
|---|---|
| **Full kitchen** | Mix of home-cooked meals + batch prep. Include 2–3 "cook once, eat twice" recipes per week. |
| **Basic kitchen** | Simple one-pot/one-pan meals, microwave-friendly options, rice cooker meals, overnight oats, salads, wraps. |
| **No kitchen / eating out** | Build the plan around restaurant orders, takeout, convenience store meals, and ready-to-eat options. Include specific ordering guidance with calorie estimates (e.g., "Chipotle: chicken bowl, no rice, extra veggies — ~520 Cal"). |
| **Mixed (most common)** | Designate which days are cook days vs. eat-out days. Typically 3–4 cook days + 3–4 eat-out/simple days per week. |

**Variety matters.** Don't repeat the same protein at every meal. Rotate across the week. If Tuesday dinner is chicken stir-fry, Thursday dinner should be something different.

**Meal prep friendliness & storage feasibility.** For users who cook, flag which meals can be batch-cooked — but **only recommend batch-prepping dishes that actually store and reheat well.** See `references/meal-prep-feasibility.md` for the full storage tier system. Key rules:
- **Batch-prep backbone:** Braised meats, curries, soups, roasted root vegetables, and cooked grains are ideal for 3–4 day storage. Build the week around these.
- **Fresh-only dishes on cook days or eat-out days:** Leafy-green stir-fries, sautéed spinach, fried/crispy foods, noodle soups, raw salads, and sashimi must be eaten the same day they're made — never schedule these as batch-prep leftovers.
- **Fish is a 1–2 day protein, not a batch-prep protein.** Cooked fish develops stronger off-flavors after 2 days. Use chicken thigh, beef, pork, or tofu for multi-day prep; schedule fish on cook days or eat-out days.
- **Separate components that store differently:** Pasta + sauce, soup + noodles, salad + dressing, congee + toppings — always store separately so the absorbent component doesn't degrade.
- **Don't recommend pre-cutting fruit for the week.** Cut apples brown, cut avocado grays, cut bananas get mushy. Recommend whole fruit as snacks. Berries are the exception — they hold 2–3 days.
- **Cap any single batch-prep dish at 3 consecutive days max.** Even great-storing dishes become monotonous. Alternate 2–3 different prep dishes per week.
- **Prep-day annotations must be temporally valid.** When noting which day a dish was batch-prepped, the prep day must fall **before** the consumption day within the plan's timeline. If the plan starts on Monday (Day 1), Tuesday's (Day 2) dishes should reference "周一备餐" (Monday prep), NOT "周日备餐" (Sunday prep) — because Sunday is Day 7, which hasn't happened yet. Day 1 meals are cooked fresh (and double as the first batch-prep session). See `references/meal-prep-feasibility.md` § Prep-Day Timeline Rule for detailed examples.

**Single-meal item cap.** Every meal must respect the structure defined in the main SKILL.md (§ Single-Meal Item Cap): breakfast = 1 staple + 1 protein + 1 drink/side (3 items); lunch/dinner = 1 staple + 2 dishes (3 items). Never put 2 staples in one meal. Each dish is one ready-to-eat unit (a stir-fry, braised meat, soup, etc.) — don't split protein and veggie into separate items when they naturally form one dish. If more calories are needed, increase portion sizes first; if still insufficient, move extras (fruit, drink, yogurt) to a snack slot and add a `💡` tip: "如果一餐吃不完，可以把 [items] 留到加餐，时间自由安排" / "If this is too much for one meal, save [items] as a snack — eat whenever works for you."

**Egg limit: 1 per day.** Cap whole-egg intake at one egg per day across all meals. This includes boiled eggs, fried eggs, tea eggs, braised eggs, and eggs as a primary ingredient in dishes like tomato egg stir-fry. If the user needs more protein, supplement with other sources — chicken breast, fish, tofu, Greek yogurt, cottage cheese, legumes, or protein powder. When a breakfast already includes an egg, do not schedule egg-heavy dishes (e.g., egg stir-fries, egg-drop soup, shakshuka) for other meals that day. Eggs used as a minor binding ingredient in cooking (e.g., a small amount of egg wash) do not count toward this limit.

**Budget awareness.** Default to affordable staples. If recommending salmon, also offer a canned tuna alternative. If a recipe calls for pine nuts, suggest sunflower seeds as a swap.

## Portion Guidance

Use **measurement units appropriate to the user's locale**:

- **US users:** American household measurements as primary — oz, cups, tbsp, fl oz. Include gram equivalents in parentheses for people who use food scales: "6 oz (170g) chicken breast"
- **Metric-region users (China, Japan, Europe, etc.):** Grams (g) and milliliters (ml) as primary units. Use everyday references that make sense locally (e.g., "1 small bowl of rice ~150g", "palm-sized chicken breast ~120g")

**Visual portion anchors** are helpful for people who don't measure:
- Palm-sized portion of protein ≈ 3–4 oz (85–113g)
- Fist-sized portion ≈ 1 cup (about 150–200g for cooked grains)
- Thumb tip ≈ 1 tbsp (about 15g for oils/butter)
- A pair of dice ≈ 1 oz (28g) cheese

## Snack Strategy

Snacks serve two purposes: filling the calorie gap between meals, and satisfying cravings so they don't lead to overeating. For each day, include 1–2 snack options:

- One **nutrient-dense** option (protein or fiber focused — sustains energy)
- One **satisfaction** option (something that feels like a treat but fits the calories — popcorn, dark chocolate, frozen fruit bars)

Don't moralize about snacks. A 200 kcal cookie that fits the macro budget is fine. The goal is a plan people will actually follow.

## Present the Plan & Let User Customize

The meal plan has been saved as `MEAL-PLAN.md` and uploaded as HTML to S3. In the chat, provide the brief summary with the link and ask for feedback. **Do NOT mention "Markdown", `.md`, or internal implementation details to the user.**

After presenting, ask:
- "How does this look? Any meals you'd want to swap out?"
- "Are there days where your schedule is different (like weekends)?"
- "Want me to add a grocery list?"

### Customization Options

The user may want to:
- **Swap a meal** → replace with an alternative at similar macros. **Update `MEAL-PLAN.md`, re-run the export script, and send the new link.**
- **Simplify** → "I want to eat the same breakfast every day" — totally fine, reduce variety in that slot. Update and re-export.
- **Add restaurant/fast-food options** → include calorie-smart choices from common chains. Update and re-export.
- **Adjust for a specific day** → "Saturday is date night" → build in a higher-calorie dinner and offset elsewhere. Update and re-export.
- **Get a grocery list** → add a grocery list section to `MEAL-PLAN.md` and re-export.

For any customization, **always update `MEAL-PLAN.md` and re-run the export script** so the user gets an updated link.

After the plan is finalized (all customizations done), introduce the daily tracking workflow if it hasn't been presented yet (see main SKILL.md § Introduce Daily Tracking Workflow).

## Markdown Content Rules

The `MEAL-PLAN.md` file is the source of truth. **All content rules below govern what goes inside the Markdown file.** The `generate-meal-plan-html.py` script handles HTML conversion automatically.

**Adapt content to the user's locale** — use appropriate language, units, local food categories, and culturally relevant references.

### Content Structure Rules

**CRITICAL: The `MEAL-PLAN.md` MUST follow the schema defined in `references/meal-plan-schema.md`.** The conversion script parses the Markdown based on heading levels, list items, blockquotes, and tip markers.

The meal plan uses a **Day (H2) → Meal (H3) → Food list (-)** hierarchy. Each level shows calories and macros (Protein/Carbs/Fat).

**1. Day level:** H2 heading showing day name + daily totals (`X,XXX kcal · Protein Xg · Carbs Xg · Fat Xg`). Day names and macro names use the user's locale (e.g., Chinese: `X,XXX kcal · 蛋白 Xg · 碳水 Xg · 脂肪 Xg`).

**2. Meal level:** H3 heading showing emoji + meal name + macros. Two types:

- **Self-cooked meal:** Blockquote (`>`) with concise dish names joined by " + ". Below it = list items (`-`) for each food: `FoodName — NaturalPortion (PreciseWeight)`. Parenthesized weight is auto-styled in HTML. "Natural portion" means how people actually talk about that food — "2 slices", "1 bowl", "1 egg", "half an avocado" — NOT body-part comparisons unless that's genuinely how people describe it (like "palm-sized steak" is fine, but "two-egg-sized toast" is not).

- **Eating-out meal:** Add `[Tag]` after meal name in H3 (e.g., `[Takeout]`, `[Eating out]`, `[便利店]`). Use blockquote for restaurant + dish, list items for ordering details, `💡` for tips.

**3. Portion descriptions:** Use the most natural, everyday way people describe that specific food in their locale:
- Countable items: "2 slices", "1 egg", "3 dumplings", "1 banana"
- Bowls/cups: "1 small bowl", "half a cup"
- Weight-based (when no natural unit exists): "a thin slice (~30g)"
- Always include precise weight in `<span class="portion">` after the natural description

**4. No repetition:** Don't use the same main dish twice in 7 days. Rotate proteins, cooking styles, and cuisines. Breakfast can repeat a few times (most people prefer routine), but lunch and dinner should be distinct every day. Batch-prep dishes may appear on 2–3 consecutive days (this is expected and practical), but they count as a single dish — don't use the same batch-prep dish in two different batches within the same week.

**5. All 7 days must be fully generated.** Every day must have complete meals with specific foods and portions. Do not abbreviate remaining days with placeholders like "same structure" or "continue pattern." The HTML file is the user's complete reference.

**6. Snacks:** H3 with emoji 🍎 and locale-appropriate snack name — list items directly, no blockquote dish summary needed.

**7. Prep-day timeline consistency.** Any prep-day annotation (e.g., "周日备餐", "prepped on Sunday") must reference a day that falls **before** the consumption day in the plan's timeline. If the plan starts Monday, Day 2 (Tuesday) dishes cannot say "周日备餐" — Sunday is Day 7. Use "周一备餐" (Monday prep) instead. See `references/meal-prep-feasibility.md` § Prep-Day Timeline Rule.

**8. Tips must be non-obvious.** Only include tips that provide genuine, actionable value — things the user likely doesn't already know. Never state common-sense steps like "grab a bowl," "eat it," "finish the food," or "boil water." Good tips: "request less oil and salt," "eat noodles and meat first, skip the oily broth," "marinate chicken the night before." Bad tips: "put oatmeal in a bowl," "eat the eggs," "drink the soy milk." If a meal has no non-obvious tip worth mentioning, skip the `💡` line entirely.
