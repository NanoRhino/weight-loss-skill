# Diagnosis Response Templates

Shared templates for presenting `analyze` findings. Used by both the
`cause-check` flow (streak 2–3) and the Interactive Flow Step 1 (streak 4+ /
manual trigger).

## Per-Factor Diagnosis

For each detected factor in `top_factors`, explain in plain language with data.
Cross-reference behavioral patterns from `health-profile.md` and recent logs.
Tone: curious and light, not accusatory.

- **Calorie surplus:** "You averaged {avg} kcal/day — about {surplus} over your {target} target. Over target on {X} of {Y} days. Looks like snacks have been busy!"
- **Exercise decline:** "You worked out {current} time(s) this week vs {previous} last week — {diff} fewer minutes. Your body might be on vacation mode!"
- **Logging gaps:** "No meal logs for {X} days — even a detective needs clues!"
- **Water retention:** "That jump is suspiciously sudden — likely water playing tricks. Give it a few days."
- **Normal fluctuation:** "Totally normal fluctuation — bodies aren't machines!"
- **Behavioral pattern shift:** When a habit change is detected (e.g., user stopped their usual evening walks, started ordering delivery more often, shifted dinner to later), call it out gently: "Looks like dinner has been creeping later — that can throw off your body's rhythm."

## Consequence Lines

One sentence connecting the cause to the weight trend. Don't catastrophize, don't sugarcoat:

- "The short-term gain isn't all fat, but if the pattern sticks, it'll be hard to make progress."
- "Once in a while is fine, but two weeks in a row and your body starts keeping score."

## Motivation Lines (cause-specific)

Immediately follow the consequence with a positive, aspirational pull tied to the specific cause:

| Cause | Motivation example |
|-------|-------------------|
| Snacking / calorie surplus | "But hey — food is tempting, but so is looking amazing, right? A few small swaps and you're right back on track." |
| Weekend overeating | "Weekdays you're crushing it — imagine what happens when weekends stop undoing all that hard work." |
| Exercise decline | "You used to be so consistent — your body remembers that rhythm, it won't take much to get it back." |
| Late-night eating | "One small timing shift and your body gets way more time to do its thing overnight." |
| Logging gaps | "Hard to win a game you're not keeping score in — but the fix is easy." |
| Calorie creep | "No single meal is the villain here — just a tiny trim and the math starts working for you again." |
| Processed food / high sodium | "加工食品里的钠含量很高，身体会多留住水分。换几顿新鲜食材，体重可能很快就回来了。" |
| Low protein | "蛋白质不够容易饿、容易掉肌肉，基础代谢也会慢慢降。每餐加一份蛋白质，饱腹感和效果都会好很多。" |
