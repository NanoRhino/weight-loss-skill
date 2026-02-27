# 🏃 Weight Loss Skill for Claude Code

An open-source [Claude Code](https://docs.anthropic.com/en/docs/claude-code) skill suite that helps you track weight, plan meals, and stay on top of your fitness goals — all from your terminal. Compatible with **Claude Code** and **OpenClaw**.

## Features

- 📊 **Weight Tracking** — Log daily weight, visualize trends
- 🍽️ **Meal Planning** — AI-powered meal suggestions based on your goals
- 🔥 **Calorie Tracking** — Log meals and track daily intake
- 📈 **Progress Reports** — Weekly/monthly summaries with insights
- 🎯 **Goal Setting** — Set target weight and timeline, get personalized plans
- 🔔 **Daily Reminders** — Proactive meal-time and weight-logging notifications

## Install

### OpenClaw (ClawHub)

```bash
# Install individual skills
clawhub install NanoRhino/daily-notification
clawhub install NanoRhino/diet-tracking-analysis
clawhub install NanoRhino/user-onboarding-profile
clawhub install NanoRhino/weight-loss-planner
```

### OpenClaw (manual)

```bash
git clone https://github.com/NanoRhino/weight-loss-skill.git
cp -r weight-loss-skill/daily-notification-skill   ~/.openclaw/skills/
cp -r weight-loss-skill/diet-tracking-analysis      ~/.openclaw/skills/
cp -r weight-loss-skill/user-onboarding-profile     ~/.openclaw/skills/
cp -r weight-loss-skill/weight-loss-planner         ~/.openclaw/skills/
```

### Claude Code (plugin)

```bash
claude plugin install NanoRhino/weight-loss-skill
```

### Claude Code (manual)

```bash
git clone https://github.com/NanoRhino/weight-loss-skill.git
cp -r weight-loss-skill/daily-notification-skill   ~/.claude/skills/
cp -r weight-loss-skill/diet-tracking-analysis      ~/.claude/skills/
cp -r weight-loss-skill/user-onboarding-profile     ~/.claude/skills/
cp -r weight-loss-skill/weight-loss-planner         ~/.claude/skills/
```

## Skills

| Skill | Description |
|-------|-------------|
| `user-onboarding-profile` | Build a user profile through natural conversation (height, weight, goals, etc.) |
| `diet-tracking-analysis` | Log food, estimate calories/macros, get practical suggestions |
| `daily-notification` | Proactive meal-time reminders and weight-logging nudges |
| `weight-loss-planner` | Goal-setting with BMI, TDEE, calorie targets, and milestone roadmaps |

## Structure

```
weight-loss-skill/
├── .claude-plugin/
│   └── plugin.json                # Claude Code plugin manifest
├── daily-notification-skill/
│   ├── SKILL.md
│   ├── evals/
│   └── references/
├── diet-tracking-analysis/
│   ├── SKILL.md
│   └── references/
├── user-onboarding-profile/
│   └── SKILL.md
├── weight-loss-planner/
│   ├── SKILL.md
│   └── references/
└── scripts/
    └── package.sh                 # Auto-packaging tool
```

## Packaging

Build distributable packages for Claude Code and OpenClaw/ClawHub:

```bash
# Package all formats (Claude Code plugin ZIP + ClawHub skill ZIPs)
./scripts/package.sh

# Claude Code plugin only
./scripts/package.sh --claude

# OpenClaw/ClawHub skills only
./scripts/package.sh --openclaw

# Package + publish to ClawHub
./scripts/package.sh --publish
```

Outputs are written to `dist/`.

## How It Works

This skill gives Claude Code (or OpenClaw) the context to act as your personal weight loss assistant. It stores data locally in markdown/JSON files — no cloud, no accounts, fully private.

## Contributing

PRs welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT License — see [LICENSE](LICENSE) for details.

## Built by

[NanoRhino](https://nanorhino.com) — AI technology company building intelligent agent solutions.
