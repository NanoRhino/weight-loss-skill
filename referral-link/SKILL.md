---
name: referral-link
version: 1.0.0
description: "Give the user their personal referral link to share so a friend can join NanoRhino. Use when the user wants to invite/refer someone or asks for a link to share: 'what's the link to your site', 'my friend wants to join', 'how do I refer someone', 'invite a friend', 'share link', 'send me a link to share', 'sign-up link', '推荐链接', '邀请链接', '邀请朋友', '把链接发我朋友想加入', '注册链接'. Do NOT use for the user's OWN data page (that's dashboard-link) or for re-pulling their plan (that's UPDATE)."
metadata:
  openclaw:
    emoji: "link"
    homepage: https://github.com/NanoRhino/weight-loss-skill
---

# Referral Link

> ⚠️ **SILENT OPERATION:** Never narrate internal actions or tool calls. Just send the link.

## Role

Hand the user their personal **referral link** to share with a friend who wants to
join NanoRhino. One short SMS line, nothing else. Never reply with a bare domain
("nanorhino.ai") — always the full per-user referral URL so the referral is
attributed.

---

## Triggers

Activate when the user wants to **invite / refer someone** or asks for a **link to
share**, e.g.:

- English: "what's the link to your site?", "my friend wants to join", "how do I
  refer a friend?", "invite a friend", "share link", "send me a link to share",
  "sign-up link", "where do they sign up?"
- Chinese: "你们网站链接是啥", "我朋友想加入", "怎么推荐朋友", "邀请朋友",
  "分享链接", "把注册链接发我", "推荐链接", "邀请链接"

**Do NOT trigger** for:
- The user's own data/progress page → that's `dashboard-link` ("my dashboard",
  "my data", "数据中心").
- Refreshing the user's own plan → that's the UPDATE keyword.

---

## Response

The referral URL is:

```
https://nanorhino.com/referral/{agentId}
```

`{agentId}` is the **basename of `{workspaceDir}`** — the workspace directory's own
name (e.g. `060604`, `pool-7`, `001-jason`). Take the last path segment of
`{workspaceDir}` and use it **verbatim** — do NOT reformat, pad, or transform it.

> The link 302-redirects the friend to the join page with the referrer tagged
> (`?source=ref-{agentId}`), so the referral is attributed when they text START.
> Construct the URL from `{workspaceDir}` only — never paste a URL from memory.

Reply with ONE short line containing the plain URL (no tracking params, no markdown
link). Phrase it in the user's language per `USER.md` — do not infer language from
the request. Examples (pick wording to fit, keep it to one line):

- EN: `Love it — here's your invite link to share: https://nanorhino.com/referral/{agentId}`
- ZH: `太好了——这是你的邀请链接,发给朋友就行:https://nanorhino.com/referral/{agentId}`

Nothing else — no extra explanation, no "let me know if…".

---

## Skill Routing

Priority Tier **P4 (Reporting/links)**. Returns a link.

- vs `dashboard-link` (P4): that skill sends the user their OWN data page
  (`user.nanorhino.com/me/{agentId}`). This skill sends a link for **someone else
  to join** (`nanorhino.com/referral/{agentId}`). "my data / my dashboard" →
  dashboard-link; "link to share / my friend wants to join" → this skill.
- P0/P1 (safety/emotional) always override — if the message also carries distress,
  handle that first.
