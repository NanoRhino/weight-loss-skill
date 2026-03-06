# Exercise Tracking & Planning Skill

A unified Claude skill that combines exercise tracking/logging with personalized training program design. Covers workout logging with calorie estimation, weekly progress summaries, and full program design for strength training, running/endurance, flexibility, bodyweight/calisthenics, and special populations.

This skill merges the former `exercise-logging` and `exercise-programming` skills into a single cohesive module.

## Capabilities

### Exercise Tracking
- Log workouts with MET-based calorie estimation
- Support for 60+ activities across 6 categories
- Smart device data integration (Apple Watch, Garmin, Strava, etc.)
- Risk alerts (overtraining, volume spikes, pain detection, monotony)
- Automated weekly summaries with WHO comparison

### Exercise Planning
- Personalized training programs based on goals, experience, equipment, and health
- Evidence-based program design with periodization
- Follow-along video recommendations
- Program adjustment based on user feedback

## Structure

```
exercise-tracking-planning/
├── SKILL.md                              # Main skill file — unified workflow and rules
├── README.md
├── scripts/
│   └── exercise-calc.py                  # MET-based calorie calculator CLI
├── references/                           # Detailed reference guides
│   ├── met-table.md                      # MET value reference table
│   ├── response-schemas.md               # JSON response schemas with examples
│   ├── risk-alerts.md                    # Risk detection rules and alert templates
│   ├── weekly-summary-template.md        # Weekly summary generation template
│   ├── program-design-guide.md           # Strength training: splits, exercises, volume, periodization
│   ├── cardio-endurance-guide.md         # Running, cycling, swimming, C25K, HIIT/LISS
│   ├── flexibility-mobility-guide.md     # Stretching, yoga, mobility protocols
│   ├── special-populations-guide.md      # Older adults, postpartum, pregnancy
│   ├── nutrition-recovery-guide.md       # Sleep, nutrition basics, recovery protocols
│   ├── sport-specific-guide.md           # Sport-specific conditioning principles
│   └── mental-health-chronic-adaptive-guide.md  # Chronic conditions, adaptive fitness, mental health
└── examples/                             # Sample outputs from testing
    ├── eval-1-beginner.md
    ├── eval-2-english-intermediate.md
    ├── eval-3-knee-injury.md
    └── eval-4-5k-runner.md
```

## Evidence Base

Reference guides cite and align with:

- ACSM Guidelines for Exercise Testing and Prescription (11th ed., 2022)
- WHO Guidelines on Physical Activity and Sedentary Behaviour (2020)
- NSCA Essentials of Strength Training and Conditioning (4th ed.)
- ACOG Guidelines on Physical Activity and Exercise During Pregnancy and the Postpartum Period (2020)
- Compendium of Physical Activities (MET values)
- Relevant meta-analyses and systematic reviews (cited inline)

## Usage

Install as a Claude skill. The skill triggers on:
- **Tracking**: workout logs, exercise descriptions, device data, weekly summary requests
- **Planning**: workout plan requests, training program design, exercise routine creation

## Languages

Responds in the user's language. Tested in Chinese and English.
