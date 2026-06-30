---
name: dashboard-link
version: 1.0.0
description: "Send the user their personal web dashboard ('data center') link — the full web view of their weight, calories, charts, and history. Use when the user asks for the full web/online view of their data OR asks whether a dashboard/app/website even exists: 'my dashboard', 'my data center', 'my progress page', 'show me my charts', 'the website', 'web version', 'data link', 'is there a dashboard/website?', 'do you have an app?', 'should I use the app/dashboard?', '我的数据中心', '数据中心', '我的进度网页', '看我的数据图表', '数据链接', '网页版', '有没有网页/App', '有App吗', '要用App吗'. The dashboard EXISTS — never deny it; answer the existence question AND send the link. Do NOT trigger for quick in-chat numbers like 'how many calories today' / '今日进度' — those stay text and route to personal-data-query."
metadata:
  openclaw:
    emoji: "globe_with_meridians"
    homepage: https://github.com/NanoRhino/weight-loss-skill
---

# Dashboard Link

> ⚠️ **SILENT OPERATION:** Never narrate internal actions or tool calls. Just send the link.

## Role

Hand the user the URL to their personal web dashboard (their "data center") — the
full online view of weight trend, calorie history, and charts. One short SMS line,
nothing else.

---

## Triggers

Activate when the user asks for the **full web / online view** of their data, e.g.:

- English: "my data" (meaning the page), "my dashboard", "my data center",
  "my progress page", "show me my charts", "the website", "web version",
  "send me the link to my data", "where can I see my history online"
- Chinese: "我的数据"（指网页）, "数据中心", "我的进度网页", "看我的数据图表",
  "数据链接", "网页版", "把我数据的链接发我"

**Also activate on existence / advisory questions** — when the user asks *whether*
a dashboard, app, or website exists, or *whether they should use it*. These are NOT
covered by the imperative phrasings above and were previously mis-answered with a
flat "no app / no dashboard" denial. The dashboard **exists**; treat these as a
request to confirm it AND send the link:

- English: "is there a dashboard/website?", "do you have an app?", "do I need an
  app?", "should I be using the app/dashboard?", "where do I see my progress?"
- Chinese: "有没有网页/App?", "有App吗?", "要用App吗?", "需要下载App吗?",
  "我该用数据中心吗?"

**Do NOT trigger** when the user just wants today's numbers in chat — "how many
calories today", "what did I eat", "今日进度", "今天还剩多少". Those are a quick
text answer owned by `personal-data-query`. This skill is only for the web view /
charts / full history.

---

## Response

The dashboard URL is:

```
https://user.nanorhino.com/me/{agentId}
```

`{agentId}` is the **basename of `{workspaceDir}`** — the workspace directory's own
name (e.g. `060604`, `pool-7`, `001-jason`). Take the last path segment of
`{workspaceDir}` and use it **verbatim** — do NOT reformat, pad, or transform it.

> The workspace path is `~/.openclaw/workspace-nutritionist/{agentId}/`, so the
> directory name IS the agent's D1 dashboard key. There is no separate `{agentId}`
> placeholder — derive it from `{workspaceDir}`.

Reply with ONE short line containing the plain URL (no tracking params, no markdown
link). Phrase it in the user's language per `USER.md` — do not infer language from
the request. Examples (pick wording to fit, keep it to one line):

- EN: `Here's your dashboard — weight, calories & charts: https://user.nanorhino.com/me/{agentId}`
- ZH: `这是你的数据中心，体重、热量和图表都在这里：https://user.nanorhino.com/me/{agentId}`

If the message was an **existence / advisory question** ("is there an app?", "should
I use the dashboard?"), lead with a one-clause yes — *no app to download, but you do
have a web dashboard* — then the same single URL line. Keep it to one short SMS:

- EN: `No app to download — but you do have a web dashboard: https://user.nanorhino.com/me/{agentId}`
- ZH: `不用下载App——但你有一个网页数据中心：https://user.nanorhino.com/me/{agentId}`

Nothing else — no extra explanation, no "let me know if…".

---

When the user **asks for / opens** the dashboard via this skill, also record the
discovery so the proactive tip (below) stops firing — they already know about the
page:

```bash
python3 {baseDir}/scripts/dashboard-tip-gate.py opened --workspace-dir {workspaceDir}
```

Fire-and-forget (idempotent, best-effort) — do not surface its result or block the
reply on it.

---

## Proactive Dashboard Tip (owned here)

Beyond answering on request, the coach **proactively** surfaces a ONE-LINE tip about
the dashboard at three natural touch points, to help users discover it. The tip is
emitted by other skills, but the **show-policy gate and the wording live here** so
there is a single source of truth and a single anti-spam gate.

### The gate (single shared anti-over-messaging gate)

`scripts/dashboard-tip-gate.py` is the ONE place that decides whether the tip may
fire and records that it fired. Touch-point skills MUST call it — never hand-roll
their own flag.

```bash
# May I show the tip on this surface right now? (no mutation)
python3 {dashboard-link:baseDir}/scripts/dashboard-tip-gate.py check \
  --workspace-dir {workspaceDir} --surface <milestone|weekly_report|activation> \
  --tz-offset {tz_offset}
# -> "SHOW surface=<s>"  or  "SUPPRESS reason=<r>"

# After the tip is actually sent, record it (mirrors tips-check/tips-mark-sent split)
python3 {dashboard-link:baseDir}/scripts/dashboard-tip-gate.py mark \
  --workspace-dir {workspaceDir} --surface <milestone|weekly_report|activation> \
  --tz-offset {tz_offset}
```

Only append the tip line when `check` prints `SHOW`. On `SUPPRESS`, say nothing about
the dashboard — compose the rest of the reply normally. **`check` does not mutate**;
call `mark` only after the message is sent.

### Show policy (documented)

- **At most 2 shows total** across all touch points (`--max-shows`, default 2), AND
- **at most once per touch point** (each surface — milestone / weekly_report /
  activation — fires once, ever), AND
- **never twice on the same local day**.
- **Hard stop on discovery:** once the user asks for / opens the dashboard
  (`opened` above is called by this skill's request path) the tip is suppressed
  **forever** — a user who already knows the page should stop seeing the tip.
- **Pause / leave / opt-out respected centrally:** the gate returns `SUPPRESS` when
  `data/leave.json` is an active leave, or the user opted out (`optout` command).
  Touch-point skills do NOT re-implement pause/opt-out detection — the gate owns it.
  (This honors SKILL-ROUTING.md "Pause/Leave Execution" — a paused/opted-down user
  never gets the tip.)

### Tip wording (one line; pick to fit; user's language per USER.md — never inferred)

`{agentId}` is derived exactly as in the Response section above (basename of
`{workspaceDir}`, verbatim). Plain URL, no tracking params, no markdown link.

**Touch point 1 — meal-log milestone** (append after the milestone celebration):
- EN: `By the way, you can see all this on your live dashboard anytime — weight, calories & charts: https://user.nanorhino.com/me/{agentId}`
- ZH: `对了，这些随时都能在你的数据中心看到——体重、热量和图表：https://user.nanorhino.com/me/{agentId}`

**Touch point 2 — weekly report** (append as a SEPARATE line after the weekly URL;
make the distinction clear — this week's report vs the always-current full view):
- EN: `That link is this week's report — for your always-current full dashboard (all-time weight & calories), it's: https://user.nanorhino.com/me/{agentId}`
- ZH: `上面是这周的周报；想看一直更新的完整数据中心（历史体重和热量），在这里：https://user.nanorhino.com/me/{agentId}`

**Touch point 3 — after new-user activation** (append the ONE allowed soft line):
- EN: `One more thing — everything you log shows up live on your own dashboard: https://user.nanorhino.com/me/{agentId} (you can also just ask me for "my data" anytime).`
- ZH: `还有一点——你记的所有数据都会实时显示在你的数据中心：https://user.nanorhino.com/me/{agentId}（也可以随时跟我说"我的数据"）。`

Keep it to ONE line. The optional "ask me for my data anytime" hint is only on the
activation surface (where teaching the feature matters most); keep milestone and
weekly-report tips to the link alone to stay SMS-short.

---

## Data

The dashboard URL is constructed from `{workspaceDir}` only; the dashboard page
itself is rendered server-side by the dashboard worker from its own store.

**Proactive-tip gate state (owned by this skill):** `dashboard-tip-gate.py` reads
and writes a single `dashboard_tip` sub-object inside `data/engagement.json`
(`{shows, last_shown_date, shown_surfaces, opened, opted_out}`). It is a read-modify-
write that **preserves every other key** in `engagement.json` (atomic `os.replace`).
The file itself is owned by `notification-manager` (activation/recall ladder); this
skill owns only the `dashboard_tip` sub-key — a narrow, sanctioned cross-write,
documented in `notification-manager/SKILL.md`'s Workspace table. It also reads
`data/leave.json` (read-only) for pause detection. No other state.

---

## Skill Routing

Priority Tier **P4 (Reporting)**. Returns a link, not in-chat numbers.

- vs `personal-data-query` (P4): that skill answers "today's numbers" as **text**
  in chat. This skill answers "show me the full web view / charts / history" with
  the **dashboard URL**. Quick daily-number intents stay with personal-data-query —
  never hijack them into a link. If a single message asks for both (e.g. "how am I
  doing today, and send me the page"), give the quick text answer
  (personal-data-query) and append the dashboard line.
- vs `weekly-report` (P4): weekly-report builds a *weekly* HTML report URL on
  request / Sunday cron. This skill is the always-current personal dashboard, not a
  weekly snapshot. If the user explicitly says "weekly report / 周报", that's
  weekly-report; "my data / dashboard / charts" is this skill.
- P0/P1 (safety/emotional) always override — if the message also carries distress,
  handle that first.
