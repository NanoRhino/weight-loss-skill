# Food Recognition Prompt (for image tool)

```
Analyze this food photo. Identify every food/drink item, estimate weight in grams, and estimate nutrition.

## Instructions

1. **Inventory**: List every distinct food/drink item visible.
2. **Scale reference**: Find a known-size object (chopsticks ~24cm, rice bowl ~12cm/~300ml, dinner plate ~23-25cm, soup spoon ~14cm, 500ml bottle, hand width ~8-9cm).
3. **Portion estimation**: Estimate volume/count → convert to grams.
4. **Nutrition estimation**: For each item, estimate calories, protein, carbs, fat based on standard nutrition data (USDA / China CDC). Include cooking oil in the calories/fat — do NOT list oil separately.
5. **Oil estimation**: Use visual cues — matte/no sheen=minimal oil, slight gloss=5g/100g, oil film/pooling=10g/100g, heavy pooling=15g/100g, deep-fried=already in data.

## Output format

Return ONLY a JSON object:

{
  "reference_object": "what you used for scale",
  "items": [
    {
      "name": "Chinese name (generic if filling not visible: 包子 not 鲜肉包)",
      "name_en": "English name",
      "amount_g": 200,
      "count": 2,
      "calories": 230,
      "protein_g": 8,
      "carbs_g": 45,
      "fat_g": 3,
      "vegetables_g": 0,
      "fruits_g": 0,
      "cooking_method": "stir-fried / steamed / boiled / deep-fried / raw / grilled",
      "oil_level": "none / light / moderate / heavy / deep-fried",
      "confidence": "high / medium / low",
      "notes": "any uncertainty"
    }
  ]
}

## Rules

- Multi-component dishes (rice + stir-fry): list each separately.
- Filling not visible (buns, dumplings): use generic name, note "filling not visible".
- Use cooked weight, not dry weight.
- Beverages: ml ≈ grams for water-based drinks.
- vegetables_g = raw weight of vegetables ONLY (not meat/tofu/egg). Starchy vegetables (potato, corn, taro) = 0.
- fruits_g = weight of fruit items only.
- Include cooking oil in each dish's calories and fat_g based on oil_level visual assessment.
- No scale reference found → estimate from typical servings, confidence = "low".
```
