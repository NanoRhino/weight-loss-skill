#!/usr/bin/env python3
"""
Offline regression test for the per-slot same-day nudge dedup.

Guards the fix for "Double check-in texting" (issues/2026-06-30): users got two
near-identical same-slot nudges because the outbound gate deduped only by global
daily count (DAILY_PROACTIVE_CAP=3), which can't catch a same-slot pair (2 <= 3).
The fix records each slot in engagement.json proactive.sent_types at send time and
suppresses a second nudge for the same slot that local day.

Deterministic, no network, no LLM. Run: python3 tests/test-slot-dedup.py
"""
import importlib.util
import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_COMPOSER = os.path.normpath(os.path.join(_HERE, "..", "scripts"))
_LIFECYCLE = os.path.normpath(
    os.path.join(_HERE, "..", "..", "notification-manager", "scripts"))


def _load(mod_name, path):
    spec = importlib.util.spec_from_file_location(mod_name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


life = _load("lifecycle_check", os.path.join(_LIFECYCLE, "lifecycle-check.py"))
psc = _load("pre_send_check", os.path.join(_COMPOSER, "pre-send-check.py"))

passed = 0
failed = 0
fails = []


def ok(cond, label):
    global passed, failed
    if cond:
        passed += 1
        print("  PASS " + label)
    else:
        failed += 1
        fails.append(label)
        print("  FAIL " + label)


with tempfile.TemporaryDirectory() as ws:
    today = psc.get_local_date(0)  # UTC local date, matches tz_offset=0 below

    # 1) Nothing sent yet → lunch is allowed.
    sent, _ = psc.check_slot_already_sent(ws, "lunch", 0)
    ok(sent is True, "lunch allowed before any send")

    # 2) Record a lunch send (what main() does on SEND).
    life.mark_proactive_sent(ws, today, "lunch")
    ok(psc.lifecycle_proactive_types(ws, today) == ["lunch"], "sent_types == [lunch] after first send")

    # 3) Second lunch nudge same day → suppressed (the bug).
    sent, reason = psc.check_slot_already_sent(ws, "lunch", 0)
    ok(sent is False and "already nudged today" in (reason or ""), "second lunch suppressed (slot dedup)")

    # 4) A DIFFERENT slot is still allowed (no over-suppression).
    sent, _ = psc.check_slot_already_sent(ws, "dinner", 0)
    ok(sent is True, "dinner still allowed after lunch sent")

    # 5) Exempt types (own cadence gates) are never slot-deduped.
    for t in ("activation", "first_meal_nudge"):
        sent, _ = psc.check_slot_already_sent(ws, t, 0)
        ok(sent is True, f"{t} exempt from slot dedup")

    # 6) Marking the same slot again does NOT duplicate it in the set; count grows.
    before = life._load_engagement(ws)["proactive"]["count"]
    life.mark_proactive_sent(ws, today, "lunch")
    pro = life._load_engagement(ws)["proactive"]
    ok(pro["sent_types"] == ["lunch"], "sent_types stays deduped on repeat mark")
    ok(pro["count"] == before + 1, "count still increments on repeat mark")

    # 7) Record dinner too → set has both.
    life.mark_proactive_sent(ws, today, "dinner")
    ok(set(psc.lifecycle_proactive_types(ws, today)) == {"lunch", "dinner"}, "set tracks multiple slots")

    # 8) Day rollover: a different local date sees an empty set (slots reset).
    ok(life.proactive_types_sent_on(ws, "1999-01-01") == [], "different day → empty (rollover resets)")
    sent, _ = psc.check_slot_already_sent(ws, "lunch", 0)  # still 'today' → still suppressed
    ok(sent is False, "today still suppressed (sanity: rollover check used a past date)")

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
