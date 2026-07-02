#!/usr/bin/env python3
# /// script
# requires-python = ">=3.6"
# dependencies = []
# ///
"""weight-milestone-calc.py — weight-loss milestone ladder.

Mirrors badge-calc.py (calorie-target ladder) but for the *scale*: given
start / current / goal weight, it reports which milestone (if any) a weigh-in
newly crosses, so the coach can surface a warm, specific celebration — and it
answers "what's the next milestone" for hope-first timeline framing.

Runs on bare python3 (prod is 3.9); no third-party deps.

Milestone ladder (shared cross-repo contract — celebrate each ONCE):
  • first chunk lost      — 5 lb / 2.5 kg
  • 5% of start weight
  • every chunk           — 10 lb / 5 kg (10/20/30…)
  • "Onederland"          — crossing under 200 lb (lb-unit only; start ≥ 200 & goal < 200)
  • 10% of start weight
  • halfway to goal
  • goal reached
If several fire on one weigh-in, the single most significant is surfaced and
the rest are still marked celebrated (dedup) so they never re-fire.

Commands:
  check  — detect newly-crossed milestone(s), persist dedup, print the one to
           celebrate. First run backfills silently (补算不补发) so an already
           mid-journey user isn't spammed with historical milestones.
  next   — print the NEXT upcoming milestone (no persistence) for framing
           ("lead with the next win, not the far endpoint").

Usage:
  python3 weight-milestone-calc.py check --data-dir <ws>/data \
      --start 210 --current 204.5 --goal 175 --unit lb --tz-offset 28800
  python3 weight-milestone-calc.py next \
      --start 210 --current 204.5 --goal 175 --unit lb
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone

# ── Ladder constants (per display unit) ──────────────────────────────────────
LADDER = {
    "lb": {"first_chunk": 5.0, "chunk_step": 10.0, "onederland": 200.0},
    "kg": {"first_chunk": 2.5, "chunk_step": 5.0, "onederland": None},
}

# Significance for picking the single milestone to surface when several fire,
# and for de-duplicating two milestones that land on the same weight.
SIG = {
    "goal": 1000,
    "onederland": 900,
    "halfway": 800,
    "pct_10": 700,
    "pct_5": 400,
    "first_chunk": 300,
}
CHUNK_SIG_BASE = 500  # chunk_{n} significance = base + n (bigger chunk wins)

EPS = 1e-6


def _local_date(tz_offset_seconds: int) -> str:
    tz = timezone(timedelta(seconds=tz_offset_seconds or 0))
    return datetime.now(tz).strftime("%Y-%m-%d")


def _fmt_amt(v: float) -> str:
    """Render an amount without a trailing .0 (5.0 -> '5', 2.5 -> '2.5')."""
    return str(int(round(v))) if abs(v - round(v)) < 1e-9 else ("%.1f" % v)


def _messages(kind: str, unit: str, amount, goal) -> dict:
    """en/zh celebration copy for a milestone kind. Language chosen by caller
    per USER.md — this returns both (no language selection here)."""
    unit_en = unit
    unit_zh = "公斤" if unit == "kg" else "磅"
    a = _fmt_amt(amount) if amount is not None else None
    g = _fmt_amt(goal) if goal is not None else None
    table = {
        "first_chunk": (
            "First {a} {u} down — the hardest part (starting) is behind you.".format(a=a, u=unit_en),
            "减掉第一个 {a} {u}——最难的一步已经迈出了。".format(a=a, u=unit_zh),
        ),
        "pct_5": (
            "That's 5% of your starting weight gone — real, measurable progress.",
            "已经减掉起始体重的 5%——实打实的进步。",
        ),
        "chunk": (
            "{a} {u} down — you're stacking wins.".format(a=a, u=unit_en),
            "累计减掉 {a} {u}——一个接一个地拿下。".format(a=a, u=unit_zh),
        ),
        "onederland": (
            "Welcome to Onederland — you're under 200 lb!",
            "体重进入「1 字头」——已经低于 200 磅！",
        ),
        "pct_10": (
            "10% of your starting weight gone — this is where the health "
            "markers really start to shift.",
            "已经减掉起始体重的 10%——身体各项指标开始明显改善。",
        ),
        "halfway": (
            "Halfway there — you've covered half the distance to your goal.",
            "到半程了——目标已经完成一半。",
        ),
        "goal": (
            "Goal reached — {g} {u}. You did exactly what you set out to do.".format(g=g, u=unit_en),
            "达成目标——{g} {u}。你做到了。".format(g=g, u=unit_zh),
        ),
    }
    en, zh = table.get(kind, ("", ""))
    return {"message_en": en, "message_zh": zh}


def build_ladder(start: float, goal, unit: str) -> list:
    """Return the milestone ladder ordered from nearest-to-start → goal.

    Each entry: {id, kind, target_weight, amount, significance, message_en,
    message_zh}. `amount` is weight LOST at that point (or the goal weight for
    the goal milestone / None for onederland).
    """
    cfg = LADDER.get(unit, LADDER["lb"])
    have_goal = goal is not None
    to_lose = round(start - goal, 2) if have_goal else None
    if have_goal and to_lose <= 0:
        return []  # not a weight-loss goal

    cand = []  # (id, kind, lost_threshold, amount, significance)

    def in_range(lost: float) -> bool:
        # A milestone is meaningful only strictly before the goal (goal itself
        # is added separately); and must be a positive loss.
        if lost <= EPS:
            return False
        if have_goal and lost >= to_lose - EPS:
            return False
        return True

    # first chunk (5 lb / 2.5 kg)
    if in_range(cfg["first_chunk"]):
        cand.append(("first_chunk", "first_chunk", cfg["first_chunk"],
                     cfg["first_chunk"], SIG["first_chunk"]))
    # 5% / 10% of start
    if in_range(0.05 * start):
        cand.append(("pct_5", "pct_5", 0.05 * start, None, SIG["pct_5"]))
    if in_range(0.10 * start):
        cand.append(("pct_10", "pct_10", 0.10 * start, None, SIG["pct_10"]))
    # every chunk (10 lb / 5 kg)
    step = cfg["chunk_step"]
    n = step
    # Cap the chunk loop at the goal (or, with no goal, a full start-weight
    # loss so the loop always terminates).
    ceiling = to_lose if have_goal else start
    while n < ceiling - EPS:
        if in_range(n):
            cid = "chunk_%s" % _fmt_amt(n)
            cand.append((cid, "chunk", n, n, CHUNK_SIG_BASE + int(round(n))))
        n += step
    # Onederland (lb only): crossing under 200 lb
    od = cfg.get("onederland")
    if od is not None and start >= od and have_goal and goal < od:
        # target strictly under 200 → threshold just past (start - 200)
        lost = start - (od - 0.01)
        if in_range(lost):
            cand.append(("onederland", "onederland", lost, None, SIG["onederland"]))
    # halfway
    if have_goal:
        cand.append(("halfway", "halfway", 0.5 * to_lose, None, SIG["halfway"]))
        cand.append(("goal", "goal", to_lose, goal, SIG["goal"]))

    # Build entries with target weights, then dedup by (rounded) target weight
    # keeping the most significant id, and order nearest-to-start first.
    entries = []
    for cid, kind, lost, amount, sig in cand:
        target = round(start - lost, 2)
        entries.append({
            "id": cid, "kind": kind, "target_weight": target,
            "amount": amount, "significance": sig,
        })

    by_target = {}
    for e in entries:
        key = round(e["target_weight"], 1)
        if key not in by_target or e["significance"] > by_target[key]["significance"]:
            by_target[key] = e
    ladder = sorted(by_target.values(), key=lambda e: -e["target_weight"])

    for e in ladder:
        e.update(_messages(e["kind"], unit, e["amount"], goal))
    return ladder


# ── Persistence (data/weight-milestones.json — owned by reward-engine) ───────
def _store_path(data_dir: str) -> str:
    return os.path.join(data_dir, "weight-milestones.json")


def _load_store(data_dir: str) -> dict:
    path = _store_path(data_dir)
    if not os.path.exists(path):
        return {"initialized": False, "celebrated": [], "last_checked": None}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"initialized": False, "celebrated": [], "last_checked": None}
    data.setdefault("initialized", bool(data.get("celebrated")))
    data.setdefault("celebrated", [])
    data.setdefault("last_checked", None)
    return data


def _save_store(data_dir: str, store: dict):
    os.makedirs(data_dir, exist_ok=True)
    with open(_store_path(data_dir), "w", encoding="utf-8") as f:
        json.dump(store, f, indent=2, ensure_ascii=False)


def cmd_check(args):
    ladder = build_ladder(args.start, args.goal, args.unit)
    store = _load_store(args.data_dir)
    celebrated = set(store.get("celebrated", []))
    today = _local_date(args.tz_offset)

    crossed = [m for m in ladder if args.current <= m["target_weight"] + EPS]

    # First-ever run: backfill silently (补算不补发) — mark everything already
    # crossed as celebrated without surfacing, so a mid-journey user isn't
    # spammed with historical milestones when the feature first runs.
    if not store.get("initialized"):
        for m in crossed:
            celebrated.add(m["id"])
        store.update({"initialized": True, "celebrated": sorted(celebrated),
                      "last_checked": today})
        _save_store(args.data_dir, store)
        print(json.dumps({"newly_crossed": False, "milestone": None,
                          "backfilled": True, "also_crossed": [],
                          "all_celebrated": sorted(celebrated)},
                         ensure_ascii=False))
        return

    newly = [m for m in crossed if m["id"] not in celebrated]
    if not newly:
        store["last_checked"] = today
        _save_store(args.data_dir, store)
        print(json.dumps({"newly_crossed": False, "milestone": None,
                          "also_crossed": [],
                          "all_celebrated": sorted(celebrated)},
                         ensure_ascii=False))
        return

    surfaced = max(newly, key=lambda m: m["significance"])
    for m in newly:
        celebrated.add(m["id"])
    store.update({"celebrated": sorted(celebrated), "last_checked": today})
    _save_store(args.data_dir, store)

    print(json.dumps({
        "newly_crossed": True,
        "milestone": {
            "id": surfaced["id"], "kind": surfaced["kind"],
            "amount": surfaced["amount"], "unit": args.unit,
            "target_weight": surfaced["target_weight"],
            "lost_so_far": round(args.start - args.current, 2),
            "message_en": surfaced["message_en"],
            "message_zh": surfaced["message_zh"],
        },
        "also_crossed": [m["id"] for m in newly if m["id"] != surfaced["id"]],
        "all_celebrated": sorted(celebrated),
    }, ensure_ascii=False))


def cmd_next(args):
    ladder = build_ladder(args.start, args.goal, args.unit)
    ahead = [m for m in ladder if m["target_weight"] < args.current - EPS]
    nxt = max(ahead, key=lambda m: m["target_weight"]) if ahead else None
    if not nxt:
        print(json.dumps({"next": None}, ensure_ascii=False))
        return
    print(json.dumps({
        "next": {
            "id": nxt["id"], "kind": nxt["kind"], "amount": nxt["amount"],
            "unit": args.unit, "target_weight": nxt["target_weight"],
            "remaining": round(args.current - nxt["target_weight"], 2),
            "message_en": nxt["message_en"], "message_zh": nxt["message_zh"],
        }
    }, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description="Weight-loss milestone ladder")
    sub = parser.add_subparsers(dest="command")

    c = sub.add_parser("check", help="Detect + persist newly-crossed milestone")
    c.add_argument("--data-dir", required=True, help="{workspaceDir}/data")
    c.add_argument("--start", type=float, required=True, help="Start weight")
    c.add_argument("--current", type=float, required=True, help="Current weight")
    c.add_argument("--goal", type=float, default=None, help="Goal weight")
    c.add_argument("--unit", choices=["kg", "lb"], default="lb")
    c.add_argument("--tz-offset", type=int, default=0,
                   help="Timezone offset from UTC in seconds (for last_checked)")

    n = sub.add_parser("next", help="Next upcoming milestone (framing; no write)")
    n.add_argument("--start", type=float, required=True)
    n.add_argument("--current", type=float, required=True)
    n.add_argument("--goal", type=float, default=None)
    n.add_argument("--unit", choices=["kg", "lb"], default="lb")

    args = parser.parse_args()
    if args.command == "check":
        cmd_check(args)
    elif args.command == "next":
        cmd_next(args)
    else:
        parser.print_help()
        raise SystemExit(1)


if __name__ == "__main__":
    main()
