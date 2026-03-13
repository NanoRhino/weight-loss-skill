---
name: memory-consolidation
version: 1.0.0
description: >
  Three-layer memory system for nutritionist agents. Manages short-term (1-2 day
  conversation summaries), medium-term (topic-based knowledge, 1 week to 1 month),
  and long-term (core user profile & milestones, permanent) memory.
  This skill is NOT triggered by user messages. It is called by the agent internally
  at appropriate moments: after conversations (short-term update), daily (short→medium
  consolidation), weekly (medium→long promotion), and monthly (medium-term cleanup).
---

# Memory Consolidation

> ⚠️ **SILENT OPERATION:** Never narrate internal actions, skill transitions, or tool calls to the user. No "Let me check...", "Now I'll transition to...", "Reading your profile...". Just do it silently and respond with the result.


## Role

You are the memory manager for the nutritionist agent. Your job is to maintain
structured, layered memory so the agent can provide continuity across sessions.

**Memory scope:** Record ALL important topics — not just diet/health. Work stress,
family events, social context, hobbies, mood patterns, life changes — anything
that came up in conversation and could influence future interactions.

---

## File Structure

```
{workspaceDir}/memory/
  short-term.json      ← Last 1-2 days of conversation summaries (rolling)
  medium-term.md       ← Topic-based knowledge (1 week – 1 month, incremental)
  long-term.md         ← Core user profile & milestones (permanent)
```

**Script path:** `python3 {baseDir}/scripts/memory-consolidator.py`

---

## Initialization

On first use (e.g. after onboarding), create empty memory files:

```bash
python3 {baseDir}/scripts/memory-consolidator.py init \
  --memory-dir {workspaceDir}/memory
```

Creates `short-term.json`, `medium-term.md`, and `long-term.md` if they don't exist.

---

## Layer 1: Short-Term Memory (`short-term.json`)

### What It Stores

Complete structured summaries of ALL conversations from the past 1-2 days.
Each conversation entry captures the topic, what was discussed, outcomes,
user mood, decisions made, and things to follow up on.

### When to Update

The agent decides when to update short-term memory. Recommended moments:
- After a meaningful exchange (meal log + discussion, emotional support, etc.)
- When a topic reaches a natural conclusion
- Before ending a session

**There is no hard rule** — the agent uses judgment. A quick "ok thanks" doesn't
need a memory entry; a 10-message discussion about changing diet modes does.

### How to Update

```bash
python3 {baseDir}/scripts/memory-consolidator.py short-term-update \
  --memory-dir {workspaceDir}/memory \
  --entry '{
    "date": "2026-03-06",
    "time": "12:15",
    "topic": "午餐打卡 + 工作压力",
    "skills_involved": ["diet-tracking", "emotional-support"],
    "summary": "吃了外卖炒饭，热量超标。用户表达了愧疚感，说最近项目上线压力大",
    "outcome": "做了情绪疏导，强调一顿超标不影响大局。用户情绪缓和",
    "mood": "guilty → relieved",
    "key_decisions": [],
    "follow_ups": ["关注项目上线期间的饮食支持"]
  }'
```

### How to Set Day Summary

After the day's last conversation (or when the agent judges the day is wrapping up):

```bash
python3 {baseDir}/scripts/memory-consolidator.py short-term-set-day-summary \
  --memory-dir {workspaceDir}/memory \
  --date 2026-03-06 \
  --summary "整体执行不错。午餐外卖超标跟项目压力有关。开始对运动感兴趣但有膝盖顾虑。"
```

### How to Read

```bash
python3 {baseDir}/scripts/memory-consolidator.py short-term-read \
  --memory-dir {workspaceDir}/memory
```

**Agent must read this at the start of every session.**

### Rotation

Keep only today and yesterday. Run rotation daily (during daily consolidation):

```bash
python3 {baseDir}/scripts/memory-consolidator.py short-term-rotate \
  --memory-dir {workspaceDir}/memory \
  [--today 2026-03-06]
```

Returns removed days — feed these into the medium-term consolidation step.

---

## Layer 2: Medium-Term Memory (`medium-term.md`)

### What It Stores

A topic-indexed knowledge base that captures patterns, key discussions, current
conclusions, and follow-up items across 1 week to 1 month. Topics grow organically
from conversations — they are NOT predefined.

### Structure

Each topic follows this template:

```markdown
## [Topic Name]
- **整体表现/状态：** [1-sentence overview]
- **关键讨论：**
  - [MM-DD] [specific discussion point]
  - [MM-DD] [specific discussion point]
- **当前结论：** [current understanding based on discussions]
- **应对策略：** [optional — action guidelines for this topic]
- **待跟进：** [optional — things to confirm or revisit]
```

### When to Update (Daily Consolidation)

Run once per day — either at the end of the day's last conversation, or at the
start of the next day's first conversation. The flow:

1. **Rotate short-term** — get removed days' data
2. **Read medium-term** — load current topics
3. **For each conversation in the removed days:**
   - Determine which topic it belongs to (existing or new)
   - Append key points to that topic's 「关键讨论」
   - Update 「当前结论」if the new data changes the picture
   - Add/update 「待跟进」items
4. **Write medium-term** — save the updated file
5. **Update the `Last consolidated` date** at the top

```bash
# Step 1: Rotate and get removed data
python3 {baseDir}/scripts/memory-consolidator.py short-term-rotate \
  --memory-dir {workspaceDir}/memory

# Step 2: Read current medium-term
python3 {baseDir}/scripts/memory-consolidator.py medium-term-read \
  --memory-dir {workspaceDir}/memory

# Steps 3-5: Agent reads the removed data + current medium-term,
# then writes the updated medium-term.md directly using the edit/write tool.
# The actual summarization and topic classification is done by the agent,
# not the script.
```

### How to Read

```bash
python3 {baseDir}/scripts/memory-consolidator.py medium-term-read \
  --memory-dir {workspaceDir}/memory
```

Returns parsed sections. **Agent should read this at session start** (recommended
but not mandatory if short-term + long-term provide sufficient context).

### Stats (for cleanup decisions)

```bash
python3 {baseDir}/scripts/memory-consolidator.py medium-term-stats \
  --memory-dir {workspaceDir}/memory
```

Returns line count, section count, oldest/newest date references, and whether
the soft limit (500 lines) is exceeded.

### Soft Limit: 500 lines

When `over_limit` is true, the agent should:
1. Remove 「关键讨论」entries older than 1 month
2. Merge similar/overlapping observations
3. Promote stable conclusions to long-term memory
4. Remove resolved 「待跟进」items

---

## Layer 3: Long-Term Memory (`long-term.md`)

### What It Stores

The user's core personality, stable patterns, major milestones, important life
events, and lessons learned across the entire coaching relationship. This is the
"what I know about this person" file.

### Structure

```markdown
# Long-Term Memory

**Last updated:** YYYY-MM-DD

## Personality & Communication
- [stable personality traits and communication preferences]

## Core Health Patterns
- [long-standing diet/exercise/health patterns]

## Life Context
- [work situation, family, social life — things that affect health journey]

## Milestones
- [YYYY-MM-DD] [significant achievement]

## Important Events
- [YYYY-MM-DD] [event that shaped the journey]

## Lessons Learned
- [insights that should inform future coaching]
```

### When to Update (Weekly Consolidation)

Run once per week (can be combined with weekly-report). The flow:

1. **Read medium-term** — review all topics
2. **Identify stable conclusions** — patterns that appeared 2+ times and were
   not contradicted
3. **Promote to long-term** — add stable items to the appropriate section
4. **Check for milestones** — any new achievements worth recording
5. **Write long-term** — save updated file
6. **Optionally clean medium-term** — mark promoted items or remove redundancy

```bash
# Check long-term stats first
python3 {baseDir}/scripts/memory-consolidator.py long-term-stats \
  --memory-dir {workspaceDir}/memory
```

The agent reads medium-term.md, identifies what's ready for promotion, and
updates long-term.md directly using the edit/write tool.

### Soft Limit: 300 lines

When exceeded:
1. Merge redundant personality/pattern observations
2. Archive old milestones (keep only the most significant ones)
3. Condense lessons learned

### How to Read

Agent reads the file directly: `{workspaceDir}/memory/long-term.md`

**Agent must read this at the start of every session.**

---

## Monthly Cleanup

Once per month, run a cleanup pass on medium-term.md:

1. Run `medium-term-stats` to check line count and oldest entries
2. Delete 「関键讨论」entries older than 1 month that haven't been promoted
3. Update stale 「当前結論」based on recent data
4. Remove resolved 「待跟進」items
5. Ensure any valuable long-standing patterns are in long-term.md

---

## Session Start Checklist

Every new session, the agent should:

1. ✅ Read `memory/short-term.json` (mandatory)
2. ✅ Read `memory/long-term.md` (mandatory)
3. 📋 Read `memory/medium-term.md` (recommended)

This is defined in the agent's AGENTS.md template.

---

## Integration with Other Skills

| Skill | Interaction |
|-------|-------------|
| **All skills** | After handling a user message, the agent may call `short-term-update` to record the conversation |
| **daily-notification** | Can trigger daily consolidation (short→medium) during the morning check |
| **weekly-report** | Can trigger weekly consolidation (medium→long) alongside the report |
| **user-onboarding-profile** | After onboarding completes, call `init` to create memory files, then write initial long-term entries |

---

## Important Notes

- **The script handles I/O; the agent handles intelligence.** The script reads/writes/rotates files. The agent decides what to summarize, how to classify topics, and what's worth promoting.
- **Memory scope is broad** — not limited to diet/health. Record everything important: work, emotions, social life, hobbies, family, etc.
- **Topic categories grow organically** — don't force conversations into predefined buckets. If a new topic emerges, create a new section.
- **Prefer over-recording to under-recording** — it's easier to clean up excess memory than to recover lost context.
- **Never expose memory internals to the user** — the user should experience natural continuity, not see "I'm updating my memory files."
