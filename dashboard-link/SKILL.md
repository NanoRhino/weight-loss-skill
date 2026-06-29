---
name: dashboard-link
version: 1.0.0
description: "Send the user their personal web dashboard ('data center') link — the full web view of their weight, calories, charts, and history. Use ONLY when the user asks for the full web/online view of their data: 'my dashboard', 'my data center', 'my progress page', 'show me my charts', 'the website', 'web version', 'data link', '我的数据中心', '数据中心', '我的进度网页', '看我的数据图表', '数据链接', '网页版'. Do NOT trigger for quick in-chat numbers like 'how many calories today' / '今日进度' — those stay text and route to personal-data-query."
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

Nothing else — no extra explanation, no "let me know if…".

---

## Data

Reads: none. Writes: none. The URL is constructed from `{workspaceDir}` only; all
data is rendered server-side by the dashboard worker from its own store.

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
