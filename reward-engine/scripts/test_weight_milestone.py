#!/usr/bin/env python3
# /// script
# requires-python = ">=3.6"
# dependencies = []
# ///
"""Self-tests for weight-milestone-calc.py.

No test framework repo-wide — run directly on bare python3:
    python3 test_weight_milestone.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "wmc", os.path.join(_HERE, "weight-milestone-calc.py"))
wmc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wmc)

_passed = 0
_failed = 0


def check(name, cond, detail=""):
    global _passed, _failed
    if cond:
        _passed += 1
        print("  PASS: {}".format(name))
    else:
        _failed += 1
        print("  FAIL: {} {}".format(name, detail))


class _Args:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _run_check(tmp, start, current, goal, unit="lb"):
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        wmc.cmd_check(_Args(data_dir=tmp, start=start, current=current,
                            goal=goal, unit=unit, tz_offset=0))
    return json.loads(buf.getvalue())


def test_ladder_ordering():
    print("test_ladder_ordering (nearest-to-start first, capped at goal):")
    ladder = wmc.build_ladder(210, 175, "lb")
    ids = [m["id"] for m in ladder]
    check("first entry is nearest to start", ladder[0]["target_weight"] > ladder[-1]["target_weight"], ids)
    check("goal is the last entry", ladder[-1]["id"] == "goal", ids)
    check("has onederland", "onederland" in ids, ids)
    check("has halfway", "halfway" in ids, ids)


def test_backfill_silent():
    print("test_backfill_silent (first run never celebrates history):")
    with tempfile.TemporaryDirectory() as tmp:
        # existing user already 12 lb down at first ever check
        out = _run_check(tmp, 210, 198, 175)
        check("backfilled flag", out.get("backfilled") is True, out)
        check("nothing surfaced", out["newly_crossed"] is False, out)
        check("history marked celebrated", "first_chunk" in out["all_celebrated"], out)
        # next weigh-in a bit lower should NOT re-fire the backfilled ones
        out2 = _run_check(tmp, 210, 197.5, 175)
        check("no re-fire of backfilled", out2["newly_crossed"] is False, out2)


def test_first_chunk_then_dedup():
    print("test_first_chunk + single-surface + dedup:")
    with tempfile.TemporaryDirectory() as tmp:
        _run_check(tmp, 210, 210, 175)                 # init empty
        out = _run_check(tmp, 210, 204.5, 175)         # crosses first 5 lb
        check("surfaces first_chunk", out["milestone"]["id"] == "first_chunk", out)
        # jump past onederland + 5% at once → surface the most significant
        out2 = _run_check(tmp, 210, 199.0, 175)
        check("surfaces most significant (onederland)",
              out2["milestone"]["id"] == "onederland", out2)
        check("also-crossed carries the rest", "pct_5" in out2["also_crossed"], out2)
        # already-celebrated → silent
        out3 = _run_check(tmp, 210, 198.5, 175)
        check("already celebrated is silent", out3["newly_crossed"] is False, out3)


def test_goal_reached():
    print("test_goal_reached:")
    with tempfile.TemporaryDirectory() as tmp:
        _run_check(tmp, 210, 210, 175)
        out = _run_check(tmp, 210, 175, 175)
        check("surfaces goal", out["milestone"]["id"] == "goal", out)


def test_kg_no_onederland():
    print("test_kg_no_onederland (US idiom is lb-only):")
    ladder = wmc.build_ladder(95, 70, "kg")
    ids = [m["id"] for m in ladder]
    check("no onederland in kg ladder", "onederland" not in ids, ids)
    check("kg first chunk is 2.5", any(m["id"] == "first_chunk" and m["amount"] == 2.5 for m in ladder), ids)


def test_tiny_goal():
    print("test_tiny_goal (goal closer than first chunk → no phantom 5lb):")
    ladder = wmc.build_ladder(150, 147, "lb")
    ids = [m["id"] for m in ladder]
    check("first_chunk (5lb) excluded beyond goal", "first_chunk" not in ids, ids)
    check("goal present", "goal" in ids, ids)


def test_next():
    print("test_next (framing helper):")
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        wmc.cmd_next(_Args(start=210, current=210, goal=175, unit="lb"))
    out = json.loads(buf.getvalue())
    check("next is first 5 lb", out["next"]["id"] == "first_chunk", out)
    check("remaining 5 lb", out["next"]["remaining"] == 5.0, out)


def main():
    for t in (test_ladder_ordering, test_backfill_silent, test_first_chunk_then_dedup,
              test_goal_reached, test_kg_no_onederland, test_tiny_goal, test_next):
        t()
    print("\n{} passed, {} failed".format(_passed, _failed))
    raise SystemExit(1 if _failed else 0)


if __name__ == "__main__":
    main()
