# MET Value Reference Table

MET (Metabolic Equivalent of Task) values for common exercises. Source: Compendium of Physical Activities.

Formula: `Calories (kcal) = MET × weight (kg) × duration (hours)`

---

## Cardio

| Activity | Intensity | MET |
|----------|-----------|-----|
| Walking, 4 km/h (casual) | Low | 2.8 |
| Walking, 5.5 km/h (brisk) | Moderate | 3.8 |
| Walking, 6.5 km/h (fast) | Moderate-High | 5.0 |
| Running, 8 km/h (5:00/km) | Moderate | 8.3 |
| Running, 9.5 km/h (6:20/km) | Moderate-High | 10.0 |
| Running, 11 km/h (5:27/km) | High | 11.5 |
| Running, 13 km/h (4:37/km) | High | 12.8 |
| Running, 16 km/h (3:45/km) | Very High | 14.5 |
| Cycling, 16-19 km/h (leisure) | Moderate | 6.8 |
| Cycling, 19-22 km/h | Moderate-High | 8.0 |
| Cycling, 22-26 km/h | High | 10.0 |
| Cycling, >26 km/h (racing) | Very High | 12.0 |
| Cycling, stationary, moderate | Moderate | 6.8 |
| Cycling, stationary, vigorous | High | 10.0 |
| Swimming, leisurely | Low-Moderate | 4.8 |
| Swimming, moderate laps | Moderate | 7.0 |
| Swimming, vigorous laps | High | 9.8 |
| Jump rope, moderate | High | 10.0 |
| Jump rope, fast | Very High | 12.3 |
| Rowing machine, moderate | Moderate | 7.0 |
| Rowing machine, vigorous | High | 10.0 |
| Elliptical trainer | Moderate | 5.0 |
| Stair climbing machine | Moderate-High | 7.5 |
| Hiking, moderate terrain | Moderate | 6.0 |
| Hiking, steep terrain/heavy pack | High | 8.0 |

---

## Strength Training

| Activity | Intensity | MET |
|----------|-----------|-----|
| Weight training, light effort | Low | 3.5 |
| Weight training, moderate effort | Moderate | 5.0 |
| Weight training, vigorous effort | High | 6.0 |
| Bodyweight exercises, moderate | Moderate | 3.8 |
| Bodyweight exercises, vigorous | High | 5.0 |
| Resistance bands | Low-Moderate | 3.5 |

**Note**: Strength training calorie estimates via MET are less precise than cardio. The MET method underestimates EPOC (excess post-exercise oxygen consumption). Acknowledge this limitation when logging.

---

## Flexibility & Recovery

| Activity | Intensity | MET |
|----------|-----------|-----|
| Stretching, light | Low | 2.3 |
| Yoga, Hatha | Low-Moderate | 2.5 |
| Yoga, Vinyasa/Power | Moderate | 4.0 |
| Yoga, Bikram/Hot | Moderate-High | 5.0 |
| Pilates, beginner | Low-Moderate | 3.0 |
| Pilates, advanced | Moderate | 4.0 |
| Foam rolling | Low | 2.0 |
| Tai Chi | Low | 3.0 |

---

## HIIT & Interval Training

| Activity | Intensity | MET |
|----------|-----------|-----|
| HIIT, general | High | 8.0 |
| HIIT, vigorous | Very High | 10.0 |
| Tabata | Very High | 10.0 |
| CrossFit | High | 8.0–12.0 |
| Circuit training, moderate | Moderate-High | 7.0 |
| Circuit training, intense | High | 9.0 |

**Note**: For HIIT, use the average MET across work and rest intervals. Actual calorie burn varies significantly based on work-to-rest ratio and exercise selection.

---

## Sports

| Activity | Intensity | MET |
|----------|-----------|-----|
| Basketball, game | High | 8.0 |
| Basketball, casual/shooting | Moderate | 4.5 |
| Soccer, game | High | 10.0 |
| Soccer, casual | Moderate | 7.0 |
| Tennis, singles | High | 8.0 |
| Tennis, doubles | Moderate | 5.0 |
| Badminton, competitive | High | 7.0 |
| Badminton, casual | Moderate | 4.5 |
| Table tennis | Moderate | 4.0 |
| Volleyball, game | Moderate-High | 6.0 |
| Volleyball, casual | Moderate | 3.0 |
| Golf, walking with clubs | Low-Moderate | 4.3 |
| Rock climbing | High | 8.0 |
| Martial arts (general) | High | 10.3 |
| Boxing, sparring | Very High | 12.0 |
| Dancing, general | Moderate | 5.0 |
| Dancing, vigorous | High | 7.5 |

---

## Daily Activities

| Activity | Intensity | MET |
|----------|-----------|-----|
| Walking commute, normal pace | Low | 3.5 |
| Cycling commute, leisurely | Moderate | 5.5 |
| Stair climbing (daily) | Moderate | 4.0 |
| Housework, light (tidying) | Low | 2.5 |
| Housework, heavy (scrubbing, moving) | Moderate | 4.0 |
| Gardening, general | Moderate | 3.8 |
| Moving / carrying heavy loads | High | 6.5 |

---

## Selection Guidelines

1. **Pace/speed available** → use the most specific row matching the pace
2. **Only intensity description** → match to Low/Moderate/High row
3. **No intensity info** → default to Moderate row
4. **Device heart rate available** → cross-reference: if avg HR suggests higher/lower intensity than default, adjust MET one level up or down
5. **Mixed activity** (e.g., run/walk intervals) → estimate time split and calculate weighted average MET

---

## Continuous Mapping — Running

When user provides a pace that falls between two data points, use linear interpolation rather than snapping to the nearest row.

**Running speed → MET anchor points:**

| Speed (km/h) | Pace (min/km) | MET |
|---------------|---------------|-----|
| 6.4 | 9:23 | 6.0 |
| 8.0 | 7:30 | 8.3 |
| 9.5 | 6:19 | 10.0 |
| 11.0 | 5:27 | 11.5 |
| 13.0 | 4:37 | 12.8 |
| 16.0 | 3:45 | 14.5 |

**Interpolation formula:**

```
MET = MET_low + (speed - speed_low) / (speed_high - speed_low) × (MET_high - MET_low)
```

**Example**: User runs 5km in 30min → speed = 10 km/h → between 9.5 km/h (MET 10.0) and 11.0 km/h (MET 11.5):

```
MET = 10.0 + (10.0 - 9.5) / (11.0 - 9.5) × (11.5 - 10.0) = 10.0 + 0.5/1.5 × 1.5 = 10.5
```

---

## Continuous Mapping — Cycling

| Speed (km/h) | MET |
|---------------|-----|
| 16 | 6.8 |
| 19 | 8.0 |
| 22 | 10.0 |
| 26 | 12.0 |

Use the same linear interpolation formula as running.

---

## Continuous Mapping — Swimming

Swimming MET depends more on stroke and effort than speed. Use the discrete Low/Moderate/High rows from the table above. If user provides a specific distance and time, classify:

| Pace (per 100m) | Intensity | MET |
|------------------|-----------|-----|
| > 3:00 | Low (leisurely) | 4.8 |
| 2:00 – 3:00 | Moderate | 7.0 |
| < 2:00 | High (vigorous) | 9.8 |
