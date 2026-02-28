# Exercise Programming Skill

A Claude skill for designing personalized exercise and training programs. Covers strength training, running/endurance, flexibility, bodyweight/calisthenics, and special populations.

## Structure

```
├── SKILL.md                    # Main skill file — workflow, output format, rules
├── references/                 # Detailed design logic (Claude reads these when generating plans)
│   ├── program-design-guide.md         # Strength training: splits, exercises, volume, periodization
│   ├── cardio-endurance-guide.md       # Running, cycling, swimming, Couch-to-5K, HIIT/LISS
│   ├── flexibility-mobility-guide.md   # Stretching, yoga integration, mobility protocols
│   ├── special-populations-guide.md    # Older adults 50+, postpartum, pregnancy
│   ├── nutrition-recovery-guide.md     # Sleep, nutrition basics, recovery protocols
│   ├── sport-specific-guide.md         # Sport-specific conditioning principles
│   └── mental-health-chronic-adaptive-guide.md  # Chronic conditions, adaptive fitness, mental health
├── examples/                   # Sample outputs from testing
│   ├── eval-1-chinese-beginner.md      # Chinese beginner, commercial gym, fat loss + muscle gain
│   ├── eval-2-english-intermediate.md  # English intermediate, home gym, strength focus
│   ├── eval-3-chinese-knee-injury.md   # Chinese female, knee injury, home dumbbells + yoga
│   └── eval-4-5k-runner.md            # Chinese female, Couch-to-5K, outdoor bodyweight
└── README.md
```

## Evidence Base

Reference guides cite and align with:

- ACSM Guidelines for Exercise Testing and Prescription (11th ed., 2022)
- WHO Guidelines on Physical Activity and Sedentary Behaviour (2020)
- NSCA Essentials of Strength Training and Conditioning (4th ed.)
- ACOG Guidelines on Physical Activity and Exercise During Pregnancy and the Postpartum Period (2020)
- Relevant meta-analyses and systematic reviews (cited inline)

## Usage

Install as a Claude skill. The skill triggers on exercise/training-related requests and follows a 4-step workflow:

1. **Collect user profile** — goals, experience, schedule, equipment, preferences, injuries
2. **Design the program** — reads reference guides to build an evidence-based plan
3. **Present the plan** — weekly Mon–Sun overview + sequential training timeline
4. **Adjust on feedback** — modifies based on user reactions

## Output Format

All plans use a sequential timeline format with:
- Full Monday-to-Sunday weekly overview (training + rest days)
- Each exercise as a bold block with sets/rests written individually
- Blank lines between sets and rests for readability
- Repeating identical rounds merged (e.g., "跑1分钟/走2分钟 × 8轮")
- Video links (follow-along for home; reference list for gym)
- Supplementary info (RPE scale, starting weights) placed at end as appendix

## Languages

Responds in the user's language. Tested in Chinese and English.
