# Food Recognition Prompt (for image tool)

```
Analyze this food photo. Identify every food and drink item, estimate weight in grams using visual references.

## Instructions

1. **Inventory**: List every distinct food/drink item visible.
2. **Scale reference**: Find a known-size object in the photo (chopsticks ~24cm, standard rice bowl ~12cm diameter / ~300ml, dinner plate ~23-25cm, Chinese soup spoon ~14cm, disposable chopsticks ~20cm, teaspoon, 500ml bottle, adult hand width ~8-9cm). State which reference you used.
3. **Portion estimation**: For each item, estimate the volume or count, then convert to grams using typical density. Show your reasoning briefly.
4. **Cooking method & oil**: Note visible cooking method and oil level for each dish.

## Output format

Return ONLY a JSON object, no other text:

{
  "reference_object": "what you used for scale and its assumed size",
  "items": [
    {
      "name": "food name in Chinese (use generic name if filling/interior is not visible, e.g. 包子 not 鲜肉包, 饺子 not 猪肉饺)",
      "name_en": "English name",
      "amount_g": estimated weight in grams (number),
      "count": number of pieces if countable (null otherwise),
      "container": "bowl size / plate size / description",
      "cooking_method": "stir-fried / steamed / boiled / deep-fried / raw / grilled / etc.",
      "oil_level": "none / light / moderate / heavy / deep-fried",
      "confidence": "high / medium / low",
      "notes": "any uncertainty or assumptions"
    }
  ]
}

## Rules

- If a dish has multiple components (e.g. rice + stir-fry on one plate), list each separately.
- For items where the interior is not visible (buns, dumplings, wraps), use the generic name and note "filling not visible" in notes.
- Estimate raw ingredient weight for cooked dishes (e.g. 200g cooked rice ≈ 200g, not the dry weight).
- Beverages: estimate volume in ml, convert to grams (water-based ≈ 1g/ml; milk ≈ 1.03g/ml).
- If no scale reference is found, state "no reference object" and estimate based on typical serving sizes. Set confidence to "low".
- Do NOT guess nutrition values — only identify foods and estimate weights.
```
