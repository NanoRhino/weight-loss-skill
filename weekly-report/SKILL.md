---
name: weekly-report
description: generate personalized weekly progress reports for Nano Rhino users. Use for manual weekly report requests such as "weekly report", "周报", "这周怎么样", and for scheduled Sunday 21:00 user-local cron runs. Always generate a clickable report URL using the bundled weekly report scripts; never return a text-only report.
---

# Weekly Report

> 🚨 **OUTPUT CONTRACT: Every execution MUST produce a clickable report URL. A text-only summary without a URL = FAILED. If scripts fail, report the error — do NOT fall back to plain-text.**

> ⚠️ **SILENT OPERATION:** Never narrate internal actions to the user. Just do it and respond with the result.

> 🚨 **ALL reports use template+data separation. `generate-report-html.py` outputs JSON data. The HTML template renders client-side. WRITING HTML YOURSELF IS FORBIDDEN.**

---

## Principles

1. **Show, don't lecture.** Let data speak. Short commentary.
2. **Celebrate consistency over perfection.** 5/7 is great — don't dwell on the 2.
3. **One week is noise, trends are signal.** No dramatic single-week conclusions.
4. **Personalize everything.** User's name, foods, goals — never generic.
5. **Actionable > informational.** Suggestions must be doable next week.

---

## Execution Flow

### Step 1: Get Date Range

```bash
python3 {diet-tracking-analysis:baseDir}/scripts/nutrition-calc.py local-date --tz-offset {tz_offset}
```

Use `current_week` (monday–sunday) as report range. **Never calculate dates yourself.**

### Step 2: Gate Check (cron only)

```bash
bash {baseDir}/scripts/should-send-report.sh --workspace-dir {workspaceDir}
```

If output starts with "no" → reply `NO_REPLY`. Stop.

### Step 3: Collect Data (once, reuse in Step 6)

```bash
python3 {baseDir}/scripts/collect-weekly-data.py \
  --workspace-dir {workspaceDir} \
  --start-date {monday} --end-date {sunday} --tz-offset {tz_offset} \
  --targets '{"cal_min":[min,max],...}' \
  2>/dev/null > /tmp/weekly-data-{username}.json
```

This outputs ALL data as JSON. **Do NOT call individual scripts per-day.**
Save to a temp file (use workspace username to avoid multi-user collision) — you'll read it now for analysis and pipe it to the report generator in Step 5.

### Step 4: Read Context

- `USER.md` → name, health flags, language preference
- `health-profile.md` → unit preference
- Previous report log: `data/logs/weekly-report-{prev_monday}.json` → check `next_week_focus`

All calorie/macro targets, weight loss rate, phase, progress bar, and week number are already in the collect output (`meta.*` and `plan.*`). No need to read `PLAN.md` separately.

### Step 5: Generate Report

```bash
cat /tmp/weekly-data-{username}.json | \
python3 {baseDir}/scripts/generate-report-html.py \
  --output {workspaceDir}/data/reports/weekly-data-{start_date}.html \
  --workspace-dir {workspaceDir} \
  --nickname {user_nickname} \
  --tagline '{short fun summary of the week}' \
  --plan-rate {weight_loss_rate_per_week} \
  --commentary '{JSON object}' \
  --highlights '{JSON array}' \
  --suggestions '{JSON array}'
```

**Script stdout = report URL.** Capture it.

**What the script does automatically:**
1. Generates JSON data file
2. Copies latest + template to reports dir
3. Uploads 3 files to cloud storage
4. Writes report log
5. Outputs public URL

**What YOU provide:**

| Param | Description |
|-------|-------------|
| `--nickname` | User's display name (from USER.md) |
| `--tagline` | Short witty one-liner summarizing the week (spoken Chinese, like a friend roasting with love) |
| `--commentary` | JSON: `{"logging": "...", "calories": "...", "weight": "...", "macros": "..."}` — 2-4 sentences each, casual spoken Chinese, funny/witty, backed by real numbers |
| `--highlights` | JSON array: 2-3 specific data-backed wins |
| `--suggestions` | JSON array: 1-2 concrete actionable improvements |
| `--plan-rate` | kg/week — use `meta.plan_rate` from collect output (default 0.5) |
| `--lang` | Report language: `zh` (default) or `en`. Read from user's profile or infer from conversation language |

> 🚨 **ALL parameters are REQUIRED with real content. Empty `'{}'` or `'[]'` = degraded experience. Read the data, think, write real commentary.**

For section-by-section rules: `read references/report-sections.md`
For edge cases (zero data, no plan, ED flags): `read references/edge-cases.md`

### Step 6: Compose Chat Message

Use values directly from collect output (`meta.*`):

```
📊 第{meta.week_number}周周报
完整分析 👇
{report_url}

{meta.progress_bar} 已走 {meta.progress_pct}%
{meta.start_weight} → {meta.current_weight} {unit} → 目标 {meta.target_weight} {unit}

{data_hook}
```

- Skip progress bar line if `meta.phase` is `"初始"` OR `meta.progress_pct` is `0`
- **快完成 phase:** Append `只差 {remaining} {unit}` after target weight

**data_hook:** ONE sentence citing specific data, sparking curiosity to click report.
For style examples: `read references/hook-examples.md`

**ED/avoid_weight_focus flags:** Omit progress bar, weight fields, and ⚖️ line. Hook focuses on consistency/variety.

---

## Pre-send Checks (cron auto-send)

1. Stage ≥ 3 → skip (still generate if manually requested)
2. < 2 days data in period → short encouragement message instead
3. All clear → generate and send

---

## Schedule & Trigger

- **Auto:** Sunday 21:00 user local time via per-user cron
- **Manual:** User says "周报" / "weekly report" → most recent completed Mon–Sun

---

## Report URLs

- `https://nanorhino.ai/user/{username}/weekly-report.html?week={start_date}`
- Latest: `https://nanorhino.ai/user/{username}/weekly-report.html` (no ?week= → loads latest)

Username auto-resolved from workspace path. Do NOT pass `--username` manually.

⚠️ Do NOT use `jdcloud-oss-upload` skill. Use `generate-report-html.py` internal upload.

---

## Writes

| Path | When |
|------|------|
| `data/reports/weekly-data-{start_date}.html` | JSON data file |
| `data/logs/weekly-report-{start_date}.json` | Report log (auto by script) |

---

## Skill Routing

Priority Tier P4 (Reporting). Owns all weekly summaries including exercise data.
Exercise-tracking does NOT produce separate weekly summary when this skill generates.

---

## Performance

- Single message, no back-and-forth
- Chat message: scannable in under 10 seconds
- Commentary per section: 2-4 sentences max
