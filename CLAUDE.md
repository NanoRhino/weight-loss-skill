# CLAUDE.md

## Project: weight-loss-skill

A collection of AI nutritionist skills — diet tracking, exercise planning,
meal planning, weight tracking, emotional support, and more. Each skill
is a self-contained module with its own SKILL.md.

## Required Reading

Before modifying any skill or data structure, read `docs/CONVENTIONS.md`.

## Key Rules

- Transactional/structured data → JSON under `data/`
- Profile-like content that changes slowly → Markdown at workspace root
- Group related data into one file per domain
- Use existing scripts for data access when available
- File naming: lowercase, hyphen-separated
- No dots in filenames as namespace separators
- Each data file has an owning skill — check before modifying its schema
- New fields in existing JSON files must be backward-compatible

## Project Structure

- Each skill lives in its own directory with a `SKILL.md`
- Shared scripts live in each skill's `scripts/` directory
- `docs/` contains project-level documentation
- Agent workspaces follow the layout defined in `docs/CONVENTIONS.md`
