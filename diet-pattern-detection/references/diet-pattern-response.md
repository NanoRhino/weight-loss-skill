# Diet Pattern Detection Response

## When `has_pattern` is `true`

The user's actual macro split over 3 consecutive days is closer to a different diet mode than their current one. Notify the user **after the normal meal log reply** (after the nutrition summary and suggestion sections), using this format:

```
📋 I noticed something over the past few days — your actual eating pattern looks more like [detected_mode_name] than [current_mode_name]. Here's a quick comparison:

Your average macro split: Protein [X]% / Carbs [X]% / Fat [X]%
[current_mode_name] range: Protein [X-X]% / Carbs [X-X]% / Fat [X-X]%
[detected_mode_name] range: Protein [X-X]% / Carbs [X-X]% / Fat [X-X]%

---

### HARD RULES — range numbers

1. The `[current_mode_name] range` numbers **MUST** come from `effective_current_mode_range` in the script output — never from memory or common knowledge. Note: IF modes (if_16_8, if_5_2) fall back to the Balanced range; `effective_current_mode_range` already reflects this correctly.
2. The `[detected_mode_name] range` numbers **MUST** come from `detected_mode_range` in the script output.
3. The `Your average macro split` numbers **MUST** come from `avg_split` in the script output (`protein_pct`, `carbs_pct`, `fat_pct`).
4. **Forbidden**: Do not invent, recall, or guess any percentage figures. If a required field is missing from the script output, omit that line entirely rather than fabricating numbers.
5. A three-column comparison table (Actual / Current mode range / Detected mode range) is also acceptable — use whichever format reads most naturally.

---

Switching to [detected_mode_name] could work well for you:
✅ [pro 1]
✅ [pro 2]

Things to keep in mind:
⚠️ [con 1]
⚠️ [con 2]

Would you like to switch to [detected_mode_name], or keep your current plan? Either way is totally fine — the best diet mode is the one you can stick with.
```

- Keep the tone neutral and supportive — this is a suggestion, not a correction
- Only show the top 2-3 pros and 1-2 cons from the `pros_cons` output
- Do not mention this again for at least 7 days after the user declines
- If the user agrees to switch, update `health-profile.md > Diet Config > Diet Mode` and recalculate macro targets using the new mode
