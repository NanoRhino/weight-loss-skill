# Integrations — Used By Other Skills

| Skill | Usage |
|-------|-------|
| `notification-composer` | `save` when user replies to weight reminder; `load --last 1` to check if already weighed today |
| `weekly-report` | `load --from --to` for weekly weight trend |
| `emotional-support` | `load --last N` for recent weight context |
| `habit-builder` | `load` for weight trend analysis |
| `user-onboarding-profile` | `save` to record initial weight during onboarding |
| `weight-loss-planner` | `load --last 1` to get current weight for calculations |
| `weight-gain-strategy` | `deviation-check` called after each weigh-in to detect plan deviation |
