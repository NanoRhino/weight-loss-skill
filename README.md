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
clawhub install NanoRhino/notification-manager
clawhub install NanoRhino/notification-composer
clawhub install NanoRhino/diet-tracking-analysis
clawhub install NanoRhino/user-onboarding-profile
clawhub install NanoRhino/weight-loss-planner
clawhub install NanoRhino/weekly-report
```

### OpenClaw (manual)

```bash
git clone https://github.com/NanoRhino/weight-loss-skill.git
cp -r weight-loss-skill/notification-manager        ~/.openclaw-user-service/skills/
cp -r weight-loss-skill/notification-composer       ~/.openclaw-user-service/skills/
cp -r weight-loss-skill/diet-tracking-analysis      ~/.openclaw-user-service/skills/
cp -r weight-loss-skill/user-onboarding-profile     ~/.openclaw-user-service/skills/
cp -r weight-loss-skill/weight-loss-planner         ~/.openclaw-user-service/skills/
cp -r weight-loss-skill/weekly-report               ~/.openclaw-user-service/skills/
```

### Claude Code (plugin)

```bash
claude plugin install NanoRhino/weight-loss-skill
```

### Claude Code (manual)

```bash
git clone https://github.com/NanoRhino/weight-loss-skill.git
cp -r weight-loss-skill/notification-manager        ~/.claude/skills/
cp -r weight-loss-skill/notification-composer       ~/.claude/skills/
cp -r weight-loss-skill/diet-tracking-analysis      ~/.claude/skills/
cp -r weight-loss-skill/user-onboarding-profile     ~/.claude/skills/
cp -r weight-loss-skill/weight-loss-planner         ~/.claude/skills/
cp -r weight-loss-skill/weekly-report               ~/.claude/skills/
```

## Skills

| Skill | Description |
|-------|-------------|
| `user-onboarding-profile` | Build a user profile through natural conversation (height, weight, goals, etc.) |
| `diet-tracking-analysis` | Log food, estimate calories/macros, get practical suggestions |
| `notification-manager` | Cron infrastructure and reminder lifecycle management |
| `notification-composer` | Meal-time reminder composition, weight-logging nudges, and reply handling |
| `emotional-support` | Detect and respond to negative emotions — body image distress, food guilt, hopelessness |
| `weight-loss-planner` | Goal-setting with BMI, TDEE, calorie targets, and milestone roadmaps |
| `weekly-report` | Personalized weekly progress report with logging streaks, calorie/macro analysis, weight trends, and suggestions |

## Structure

```
weight-loss-skill/
├── .claude-plugin/
│   └── plugin.json                # Claude Code plugin manifest
├── notification-manager/
│   ├── SKILL.md
│   ├── evals/
│   └── scripts/
├── notification-composer/
│   ├── SKILL.md
│   ├── evals/
│   └── references/
├── diet-tracking-analysis/
│   ├── SKILL.md
│   └── references/
├── emotional-support/
│   └── SKILL.md
├── user-onboarding-profile/
│   └── SKILL.md
├── weekly-report/
│   ├── SKILL.md
│   └── references/
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

## Deployment

Most skills are pure Markdown + stdlib Python and need no extra setup.

**`plan-card` (SMS/MMS plan-card pipeline) and `plan-export` (HTML/PDF
export)** share Python dependencies declared in `plan-card/requirements.txt`
(`weasyprint`, `pymupdf`, `markdown`):

```bash
pip3 install -r plan-card/requirements.txt
```

The openclaw-infra Twilio extension invokes the plan-card pipeline directly
— its deploy config (`planImage.scriptPath`) must point to
`plan-card/scripts/plan-to-image.py`.

WeasyPrint additionally requires **pango/cairo/gdk-pixbuf system libraries**
— pip alone is not enough. On an EC2 host:

```bash
# Amazon Linux 2023
sudo dnf install -y pango cairo gdk-pixbuf2

# Ubuntu/Debian
sudo apt-get install -y libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0
```

## How It Works

This skill gives Claude Code (or OpenClaw) the context to act as your personal weight loss assistant. It stores data locally in markdown/JSON files — no cloud, no accounts, fully private.

## Contributing

PRs welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT License — see [LICENSE](LICENSE) for details.

## Built by

[NanoRhino](https://nanorhino.com) — AI technology company building intelligent agent solutions.
