# CONVENTIONS.md — Project Conventions

This document defines conventions for the weight-loss-skill project.
All contributors (human or AI) should read this before modifying any skill
or data structure.

---

## 1. File Types and When to Use Each

### Markdown (.md)
Use for content that is **human-readable and changes infrequently**:
- Agent identity and configuration (SOUL.md, AGENTS.md, USER.md, IDENTITY.md)
- User profiles and preferences (health-profile.md, health-preferences.md)
- Generated documents meant for export (PLAN.md, MEAL-PLAN.md)
- Skill definitions (SKILL.md)
- Memory and notes (MEMORY.md, memory/*.md)

**Rule of thumb:** If the data reads like a document and evolves through
conversation, Markdown is appropriate.

### JSON (.json)
Use for **structured, transactional, or time-series data**:
- Records that accumulate over time (meals, weight, exercise logs)
- State tracking (engagement, flags, notification config)
- System metadata (timezone, locale)

**Rule of thumb:** If the data has timestamps, arrays, needs programmatic
querying, or changes frequently within a session, use JSON.

### HTML (.html)
Generated output only. Never hand-authored. Always produced by a script
from a Markdown or JSON source.

---

## 2. Directory Structure

```
workspace-root/
├── *.md                    Markdown profiles, plans, and identity files
├── data/                   All transactional and structured JSON data
│   └── (organized by domain — see Section 3)
├── memory/                 Agent memory files
└── *.json                  System config only (timezone, locale, plan-url)
```

### Rules
- **Transactional data goes under `data/`** — not in the workspace root.
- **System config JSON stays at workspace root** — files like timezone.json
  and locale.json that the platform reads directly.
- **Don't create new top-level directories** without good reason. If new
  data needs a home, prefer a subdirectory under `data/` or an existing
  location.

---

## 3. Data Organization

### One file per domain
Group related data into a single file. Don't split individual keys or
records into separate files.

When storing daily records, use the pattern `data/{domain}/YYYY-MM-DD.json`
with one file per day.

For non-daily data, use `data/{domain}.json` as a single file for the
entire domain.

### Ownership
Each data file should have a **primary owner** — the skill responsible for
its schema and write logic. Other skills may read the file, but only the
owner should define its structure.

Document ownership in the relevant SKILL.md.

---

## 4. Data Access

### When to use scripts
Use a script (Python, Bash) when the data domain involves:
- Validation or normalization
- Calculations (calories, macros, BMI)
- Complex queries (date ranges, aggregations)
- Multiple skills reading/writing the same file

### When direct read/write is fine
Simple config-like JSON (timezone, locale) or Markdown files (profiles,
plans) can be read and written directly by agents without a script layer.

### Adding new data domains
1. Determine if the data is transactional (→ JSON under `data/`) or
   profile-like (→ Markdown at root)
2. If transactional and complex, create a script for read/write operations
3. Document the new data file and its owner in the relevant SKILL.md

---

## 5. File Naming

- **Lowercase, hyphen-separated:** `health-profile.md`, `meal-plan.html`
- **JSON data files:** `{domain}.json` or `{domain}/YYYY-MM-DD.json`
- **No dots as namespace separators in filenames.** Use JSON keys or
  directories for namespacing.
- **Scripts:** `{verb}-{noun}.py` or `{verb}-{noun}.sh`
  (e.g., `generate-html.py`, `upload-to-s3.sh`)

---

## 6. SKILL.md Conventions

Every SKILL.md should:
- Clearly state its **trigger conditions** (when to activate)
- **Document data dependencies** — what files it reads from and writes to,
  and through which mechanism (script or direct)

Format of the data dependency section is flexible (table, list, or prose)
as long as the information is present.

---

## 7. Schema Evolution

When adding new fields to an existing JSON file:
- New fields should have sensible defaults or be optional
- Existing data should continue to work without migration
- If a breaking change is unavoidable, update the owning script to handle
  both old and new formats

---

## 8. Cross-Skill Data Sharing

Skills frequently read data owned by other skills. To keep this manageable:
- **Readers should not assume internal structure details** — use the
  owning skill's script to access data when one exists
- **Don't duplicate data across files.** If two skills need the same data,
  one owns it and the other reads from it.
- If a new skill needs data that doesn't exist yet, check if an existing
  domain covers it before creating a new file.

---

## 9. Common Pitfalls

- **Scattered files:** Group related data into one file per domain — don't
  create a separate file for each key or flag.
- **Root clutter:** Transactional data belongs under `data/`, not in the
  workspace root.
- **Bypassing scripts:** If a script exists for a data domain, use it
  rather than writing the JSON directly.
- **Filename hacks:** Use JSON keys or directories for structure, not
  dots or special characters in filenames.

---

## 10. Data File Ownership Quick Reference

| File | Owner Skill | Purpose |
|------|-------------|---------|
| `data/meals/YYYY-MM-DD.json` | `diet-tracking-analysis` | Daily meal logs |
| `data/recommendations/YYYY-MM-DD.json` | `notification-composer` | Meal recommendation dedup |
| `data/weight.json` | `weight-tracking` | Weight records |
| `data/engagement.json` | `notification-manager` | Notification lifecycle state |
| `data/preference-tuning.json` | `preference-tuning` | User preference defaults + Week 1 nudge state |

Other skills may **read** these files but should only **write** through the
owning skill's scripts or conventions.

---

## 11. Language & Locale Policy

**Do NOT add language selection logic to any skill.** Language is managed
centrally:

- `locale.json` is the **sole source of truth** for reply language
- `AGENTS.md` contains the mandatory locale check rule (read before every reply)
- Skills must **never** include directives like "reply in the user's language",
  "adapt language to match the user", or "if the user switches language, switch too"
- Cultural/food/unit adaptation based on locale (e.g., local foods, metric vs
  imperial) is fine — that's locale awareness, not language selection
- Format rules like "don't mix languages in one reply" are fine — that's
  output quality, not language selection
- If a skill needs locale info (e.g., for unit preference), read `locale.json`
  directly — don't infer language from user messages

---

## 12. Cron Job Delivery Policy

Cron isolated sessions use **announce delivery** — the agent's text output
is automatically delivered to the user by the OpenClaw cron system. This
means:

- **Never add "don't self-deliver" instructions to `payload.message`.**
  The no-self-delivery rule belongs in the **skill SKILL.md** (currently
  `notification-composer`), not in each cron job's payload text.
- **`payload.message` should contain only the task instruction** — e.g.,
  `"Run notification-composer pre-send checks for breakfast."` Keep it
  short and action-oriented.
- The no-self-delivery rule is enforced at two layers:
  1. **Skill layer:** `notification-composer` SKILL.md contains the
     `NO SELF-DELIVERY` directive (primary enforcement).
  2. **Agent layer:** `AGENTS.md` template contains a general rule that
     cron sessions should only output text, not call delivery tools
     (fallback enforcement).
- When creating new cron jobs (in `create-reminder.sh` or any other
  script), do **not** prepend wrapper text to `--message`. Pass the raw
  instruction only.
