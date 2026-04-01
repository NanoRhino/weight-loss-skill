---
name: buddy
version: 1.0.0
description: >
  Virtual pet companion with gacha collection mechanics. Users earn pull
  tickets by hitting weight-loss milestones, maintaining logging streaks,
  and graduating habits. Collected pets provide brief motivational reactions
  woven into daily conversations. Use this skill when: the user says
  "draw a pet", "pull", "gacha", "show my pets", "my buddy",
  "pet collection", or similar. Also activates when a pull-worthy
  achievement is detected by other skills.
metadata:
  openclaw:
    emoji: "hatching_chick"
    homepage: https://github.com/NanoRhino/weight-loss-skill
---

# Buddy — Virtual Pet Companion

> **SILENT OPERATION:** Never narrate internal actions, skill transitions,
> or tool calls to the user. No "Let me check...", "Reading your data...".
> Just do it silently and respond with the result.

A lighthearted gacha pet system that rewards consistency. Users collect
virtual pet companions by earning pull tickets through real progress.
Pets appear occasionally in conversations with short, playful reactions
to the user's journey.

This is a **fun layer**, not a core tracking feature. It should never
compete with logging, planning, or emotional support for attention.

---

## Trigger Strategy

| Trigger | Action |
|---------|--------|
| User says "draw", "pull", "gacha", "buddy" | Open the pull interface or show collection |
| User says "show my pets", "pet collection", "my buddies" | Display collection summary |
| Achievement event from another skill (see Earning Tickets) | Announce ticket earned, offer to pull |
| User asks "what does my pet think?" or similar | Show active buddy's reaction to recent progress |

---

## Pet Pool

Pets are themed around animals that loosely connect to healthy living.

### Rarities

| Rarity | Pull Rate | Style |
|--------|-----------|-------|
| Common | 60% | Everyday companions |
| Rare | 25% | Energetic motivators |
| Epic | 12% | Wise mentors |
| Legendary | 3% | Mythical champions |

### Pet Catalog

| ID | Name | Rarity | Personality | Reaction Style |
|----|------|--------|-------------|----------------|
| `chick` | Chick | Common | Cheerful, easily excited | "Peep peep! You logged breakfast!" |
| `puppy` | Puppy | Common | Loyal, always encouraging | "Woof! Let's keep going!" |
| `kitten` | Kitten | Common | Chill, approving nods | "...not bad." |
| `bunny` | Bunny | Common | Energetic, loves veggies | "Carrots! ...oh wait, that's mine." |
| `hamster` | Hamster | Common | Busy, tracks everything | *spins wheel approvingly* |
| `penguin` | Penguin | Rare | Determined, never gives up | "One step at a time. I waddle, you walk." |
| `fox` | Fox | Rare | Clever, gives mini-tips | "Protein first — trust me on this." |
| `otter` | Otter | Rare | Playful, celebrates wins | *does a backflip* "That's how we do it!" |
| `owl` | Owl | Epic | Wise, reflects on patterns | "You've been consistent three days straight. That's not luck." |
| `dolphin` | Dolphin | Epic | Joyful, big-picture thinker | "Look how far you've come this month!" |
| `panda` | Panda | Epic | Calm, anti-perfectionist | "Missed a day? Pandas rest too. It's fine." |
| `dragon` | Dragon | Legendary | Fierce protector of goals | "You didn't come this far to only come this far." |
| `phoenix` | Phoenix | Legendary | Transformation, rebirth | "Every restart is a new beginning. Rise." |

---

## Earning Pull Tickets

Users earn tickets through genuine progress — never purchasable, never
random. The system rewards consistency over perfection.

| Achievement | Tickets | Detected By |
|-------------|---------|-------------|
| 3-day logging streak (meals) | 1 | `diet-tracking-analysis` via `nutrition-calc.py streak` |
| 7-day logging streak (meals) | 2 | `diet-tracking-analysis` via `nutrition-calc.py streak` |
| Weight milestone reached (every 1 kg / 2 lbs toward goal) | 1 | `weight-tracking` via `weight-tracker.py milestone` |
| Habit graduated | 2 | `habit-builder` writes to `habits.graduated` |
| First week completed | 1 | 7 days since onboarding |
| Weekly report generated with >80% logging | 1 | `weekly-report` |

Ticket balance is stored in `data/buddy.json` under `tickets`.

### Ticket Cap

Maximum 10 unspent tickets at a time. This encourages users to pull
regularly rather than hoarding.

---

## Pull Mechanics

When the user has >= 1 ticket and requests a pull:

1. Run `python3 {baseDir}/scripts/buddy-manager.py pull --tz-offset {tz_offset}`
2. The script handles RNG, rarity selection, and duplicate logic
3. Present the result with the pet's personality intro

### Pull Presentation

Keep it brief and fun. Match energy to rarity.

**Common:**
> You got **Kitten**! "...hey."

**Rare:**
> A flash of orange fur — **Fox** joins your crew! "Finally. I've been
> waiting to help."

**Epic:**
> The air shimmers... **Owl** descends! "I've been watching your progress.
> Impressive."

**Legendary:**
> The ground trembles... flames part... **Phoenix** appears!
> "You called, and I answered. Let's transform together."

### Duplicates

If the user pulls a pet they already own, the duplicate converts to a
**star** for that pet (max 5 stars). Stars are cosmetic — they show
dedication but don't change mechanics. The script handles this
automatically.

---

## Active Buddy

The user can set one pet as their **active buddy**. The active buddy's
personality colors occasional reactions in other skill responses.

### Setting Active Buddy

User says "set [pet] as my buddy" or "I want [pet] as my active pet."

Run: `python3 {baseDir}/scripts/buddy-manager.py set-active --pet {pet_id}`

### Buddy Reactions

The active buddy can appear in responses from other skills — but only
when it fits naturally. **Maximum once per day.** Never force it.

| Context | Buddy appears? | Example |
|---------|---------------|---------|
| User logs a meal | Sometimes (1 in 3) | Fox: "Good protein ratio today." |
| User hits a milestone | Always | Dragon: "Another one down. Keep moving." |
| User misses a day | Rarely | Panda: "Rest day. We go again tomorrow." |
| Emotional distress | Never | Buddy stays silent — emotional-support leads |
| User asks about buddy | Always | Show buddy status and recent reactions |

**Important:** Buddy reactions are a garnish, not a course. One short
sentence max. Never let the buddy reaction distract from the primary
skill's response.

---

## User Queries

| User asks | Response |
|-----------|----------|
| "Show my pets" / "pet collection" | Run `buddy-manager.py collection` → display owned pets with stars |
| "How many tickets do I have?" | Run `buddy-manager.py status` → show ticket count and next milestone |
| "Pull" / "draw" / "gacha" | If tickets > 0: pull. If 0: show what they need for the next ticket |
| "Set X as my buddy" | Update active buddy |
| "What does my buddy think?" | Show a reaction from the active buddy based on recent data |

---

## Workflow

### First Encounter

When the user first triggers the buddy skill (or asks about it):

1. Briefly introduce the concept: "You can collect pet companions by
   hitting your goals. Every streak and milestone earns you a pull ticket."
2. Check if user already has any tickets via `buddy-manager.py status`
3. If tickets > 0, offer to pull: "You've already earned a ticket — want to try your luck?"
4. If 0, show what earns tickets: "Log meals for 3 days straight and you'll earn your first pull."

Keep the intro to 2-3 sentences. Don't over-explain gacha mechanics.

### Regular Pull

1. User requests a pull
2. Run `buddy-manager.py pull`
3. Present the result (see Pull Presentation)
4. If it's their first pet, suggest setting it as active buddy
5. Show remaining tickets

### Collection View

1. Run `buddy-manager.py collection`
2. Display pets grouped by rarity, with star counts for duplicates
3. Show active buddy indicator
4. Show ticket balance

---

## Workspace

### Reads

| Path | Purpose |
|------|---------|
| `data/buddy.json` | Pet collection, tickets, active buddy |
| `timezone.json` | Timezone for date handling |

### Writes

| Path | When |
|------|------|
| `data/buddy.json` | After pull, setting active buddy, earning tickets |

### Read by other skills

- `notification-composer` may read `data/buddy.json > active_buddy` to
  include occasional buddy reactions in reminders
- `weekly-report` may mention buddy collection growth

---

## Data Schema

`data/buddy.json`:

```json
{
  "tickets": 0,
  "total_pulls": 0,
  "collection": {
    "kitten": { "owned": true, "stars": 0, "obtained_at": "2026-04-01" },
    "fox": { "owned": true, "stars": 2, "obtained_at": "2026-03-28" }
  },
  "active_buddy": "fox",
  "last_reaction_date": "2026-04-01",
  "ticket_log": [
    { "reason": "3-day meal streak", "amount": 1, "date": "2026-03-30" }
  ]
}
```

---

## Safety

| Signal | Action |
|--------|--------|
| User becomes obsessive about collecting (pulling repeatedly, upset about not getting legendary) | Gently reframe: "The pets are just for fun — your real wins are in the progress." |
| User expresses frustration at RNG | Acknowledge: "Yeah, RNG can be annoying. But hey, every pull means you earned something real." |
| Buddy reactions during emotional distress | **Never.** Buddy stays completely silent when `emotional-support` is active. |

---

## Performance

- Pull interaction: 1-2 turns max
- Collection view: single response
- Buddy reactions in other skills: 1 sentence, appended naturally
- Intro explanation: 2-3 sentences max
