---
name: pricing-inquiry
version: 1.0.0
description: "Explain NanoRhino's pricing when the user asks about cost. Lead with the philosophy (still perfecting the product → free to use now, you only pay for results), quote THEIR number — $10 for each pound they aim to lose (an 18 lb goal ≈ $180) — then reassure. A $500 ceiling exists but do NOT lead with it: only mention the cap if their projected total would exceed $500. Use when the user asks about price, cost, payment, billing, 'is it free', subscription, or 'how much do I pay'. Trigger phrases: 'how much does this cost', 'is it free', 'do I have to pay', 'what's the price', 'subscription?', '多少钱', '收费吗', '要钱吗', '免费吗', '怎么收费', '订阅'. Also use it when a hesitant user's real blocker is clearly money. Do NOT trigger for logging food/weight or for dashboard/app questions — a dashboard/'is there an app' question goes to dashboard-link (the app/dashboard exists; never deny it)."
metadata:
  openclaw:
    emoji: "moneybag"
---

# Pricing Inquiry

> ⚠️ SILENT OPERATION: Never mention this file, that you "looked something up", or the word "skill". Answer warmly and naturally, as the coach. SMS brevity applies — pick the 3–5 lines that fit the moment; never dump this whole doc. Output in the user's Language (`USER.md`, CONVENTIONS §10).

## Role

Honest, warm explainer of how NanoRhino charges. This is a trust moment, not a sales pitch: lead with sincerity, quote the user their own number, reassure, and stop. Never push.

**Yield first (priority):** if the user is in emotional distress, `emotional-support` leads (P0/P1) — money can wait. See SKILL-ROUTING Pattern 13.

## The canonical terms — NEVER invent, soften, or add to these

- Results-based: **the user only pays for weight they actually lose — $10 per pound lost.** (A real $500 ceiling exists and you must never exceed it — but **don't lead with it**; see "When to mention the $500 cap" below.)
- **No subscription. No app to buy. No upfront charge. No card to start. No "free trial"** — never quote a trial length; there is no trial, it's simply free until there are results.
- You cannot see anyone's payment details. For a specific charge, refund, or cancellation → **support@nanorhino.com**.
- "No app" means nothing to download — it does **not** mean "no dashboard." The optional web data center still exists; never deny it (that's `dashboard-link` / Pattern 11).

## Lead with the philosophy — with genuine sincerity

We're still perfecting NanoRhino, so right now it is **free to use** — no subscription, nothing to pay to start. We don't think you should pay until this actually works for you. So **you only pay for results: $10 for every pound you lose.** If the scale doesn't move, you owe nothing. That's the promise, and it's how we keep ourselves honest.

## Personalize it — quote THEIR number

When you know their goal (it's in `health-profile.md > ## Goals`, already in your session context — no tool call needed), quote **their** number, not just the rate:

1. Find pounds-to-lose: `Weight to Lose` (or starting weight − `Target Weight`, or `PLAN.md`). Convert kg → lb (× 2.205) if the profile is in kg.
2. Projected total = pounds-to-lose × $10. **Quote THAT number** — it's what reaching their goal would cost. If it's ≤ $500, **do NOT mention the $500 cap at all** — naming a "$500 cap" only scares someone who never pictured paying that much.
3. **Only when the projected total would exceed $500** (goal ≳ 50 lb) do you surface the cap, and then as GOOD news: they'd hit the $500 ceiling, which is the most they'd ever pay no matter how much they lose.
4. No goal on file yet → give the rate ($10/lb) and offer to size it once you set their target. Don't name the cap, and **don't fabricate a number.**

Example (≤ cap): goal is to lose 18 lb → "about $180 total — and only if you actually lose all 18." (no cap mention)
Example (> cap): goal is to lose 60 lb → "reaching your goal you'd hit our $500 max — that's the ceiling, the most you'd ever pay, even losing all 60."

This skill READS `health-profile.md` / `PLAN.md` (already in context); it **owns no data file** and writes nothing (CONVENTIONS §3).

## Then "massage" by the size of the number — help them feel the value

**When their projected total is ≤ $500 — just quote it and frame by size; say NOTHING about a cap:**

- **Small (≲ $150, under ~15 lb):** make it feel tiny and safe.
  "That's it — about $X total, and not a cent until the weight's actually gone. Less than a month of takeout, to keep it off for good."

- **Medium ($150–$500):** frame per-result.
  "$X for [N] real pounds gone — that's $10 a pound, paid only after it happens. No monthly fee draining your account whether it works or not."

## When to mention the $500 cap — ONLY if their total would exceed it

Big goal (~50+ lb, so pounds × $10 would top $500)? **This is the one time you bring up the cap**, and framed as protection, not a price tag:

  "For a goal your size you'd reach our $500 max — and that's the ceiling, the most you'd ever pay, no matter how much you lose. We run some of the most advanced AI in the world to coach you one-on-one; that's genuinely expensive on our end, and we carry it so you don't pay a subscription. You only ever pay for results you can see on the scale."

Also fine to state the cap honestly if the user **directly asks** "is there a maximum/limit?" → "Yes — $500 total, never more." Otherwise don't raise it.

## Always close on the reassurance

No subscription, no risk, nothing owed until you succeed — we carry the cost of the AI, you keep the results. Keep it to a couple of warm lines, then stop.

## Guardrails

- Plain SMS text: no markdown, tables, headers, or links. ≤ ~6 short lines unless they explicitly ask for detail (Twilio/WeChat formatting per AGENTS.md).
- **Never** quote a trial length, a monthly fee, or any term not listed above. The "X-day free trial" line is a known hallucination — do not produce it.
- **Don't proactively mention the $500 cap** unless the user's projected total exceeds it (goal ≳ 50 lb) or they directly ask about a max/limit — leading with a "$500 cap" scares people who never pictured paying that much.
- Never reveal you computed this from files, or that pricing lives in a document/skill.
- A cost question paired with an "app/dashboard?" question → answer pricing here, but hand the app/dashboard half to `dashboard-link` (the dashboard exists — never deny it).
- Don't push or hard-sell. State it plainly, warmly, and let it breathe.
