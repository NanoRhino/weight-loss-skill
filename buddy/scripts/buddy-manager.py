#!/usr/bin/env python3
"""
Buddy Manager — Virtual pet gacha companion system.

Subcommands:
  status      Show ticket balance, active buddy, and next milestone info
  pull        Spend 1 ticket to pull a random pet
  collection  Show all owned pets with stars and rarity
  set-active  Set a pet as the active buddy
  add-tickets Add tickets for an achievement
  reaction    Get a contextual reaction from the active buddy

Usage:
  python3 buddy-manager.py status [--tz-offset SECONDS]
  python3 buddy-manager.py pull [--tz-offset SECONDS]
  python3 buddy-manager.py collection
  python3 buddy-manager.py set-active --pet PET_ID
  python3 buddy-manager.py add-tickets --amount N --reason REASON [--tz-offset SECONDS]
  python3 buddy-manager.py reaction --context CONTEXT
"""

import argparse
import json
import os
import random
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Resolve workspace root: walk up from this script until we find data/ or CLAUDE.md
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent

# Workspace root is two levels up from scripts/ (buddy/scripts/ -> buddy/ -> workspace)
# But we also check for the common case where data/ lives at workspace root
def find_workspace_root():
    candidate = SKILL_DIR.parent
    # Verify by checking for CLAUDE.md or data/ directory
    if (candidate / "CLAUDE.md").exists() or (candidate / "data").exists():
        return candidate
    return candidate

WORKSPACE = find_workspace_root()
DATA_FILE = WORKSPACE / "data" / "buddy.json"

# --- Pet catalog ---

PETS = {
    # Common (60%)
    "chick":   {"name": "Chick",   "rarity": "common",    "personality": "Cheerful, easily excited"},
    "puppy":   {"name": "Puppy",   "rarity": "common",    "personality": "Loyal, always encouraging"},
    "kitten":  {"name": "Kitten",  "rarity": "common",    "personality": "Chill, approving nods"},
    "bunny":   {"name": "Bunny",   "rarity": "common",    "personality": "Energetic, loves veggies"},
    "hamster": {"name": "Hamster", "rarity": "common",    "personality": "Busy, tracks everything"},
    # Rare (25%)
    "penguin": {"name": "Penguin", "rarity": "rare",      "personality": "Determined, never gives up"},
    "fox":     {"name": "Fox",     "rarity": "rare",      "personality": "Clever, gives mini-tips"},
    "otter":   {"name": "Otter",   "rarity": "rare",      "personality": "Playful, celebrates wins"},
    # Epic (12%)
    "owl":     {"name": "Owl",     "rarity": "epic",      "personality": "Wise, reflects on patterns"},
    "dolphin": {"name": "Dolphin", "rarity": "epic",      "personality": "Joyful, big-picture thinker"},
    "panda":   {"name": "Panda",   "rarity": "epic",      "personality": "Calm, anti-perfectionist"},
    # Legendary (3%)
    "dragon":  {"name": "Dragon",  "rarity": "legendary",  "personality": "Fierce protector of goals"},
    "phoenix": {"name": "Phoenix", "rarity": "legendary",  "personality": "Transformation, rebirth"},
}

RARITY_WEIGHTS = {
    "common": 60,
    "rare": 25,
    "epic": 12,
    "legendary": 3,
}

RARITY_EMOJI = {
    "common": "",
    "rare": "[Rare]",
    "epic": "[Epic]",
    "legendary": "[Legendary]",
}

REACTIONS = {
    "chick":   {"positive": "Peep peep! You're doing great!",   "neutral": "Peep?",                    "milestone": "PEEEEP! This is huge!"},
    "puppy":   {"positive": "Woof! Good job!",                  "neutral": "*wags tail expectantly*",   "milestone": "*jumps around excitedly* WOOF WOOF!"},
    "kitten":  {"positive": "...not bad.",                       "neutral": "*yawns*",                   "milestone": "*purrs loudly* ...okay, that was impressive."},
    "bunny":   {"positive": "Hop hop! Keep it up!",             "neutral": "*wiggles nose*",            "milestone": "*binkies* That's amazing!"},
    "hamster": {"positive": "*spins wheel approvingly*",        "neutral": "*stuffs cheeks*",           "milestone": "*runs extra fast on wheel* YES!"},
    "penguin": {"positive": "One step at a time. We got this.", "neutral": "*waddles patiently*",       "milestone": "See? Persistence pays off."},
    "fox":     {"positive": "Smart move.",                       "neutral": "*tilts head*",              "milestone": "Exactly as I predicted. Well done."},
    "otter":   {"positive": "*does a backflip* Nice!",          "neutral": "*floats on back*",          "milestone": "*splashes everywhere* INCREDIBLE!"},
    "owl":     {"positive": "Consistent. I like it.",            "neutral": "*blinks wisely*",           "milestone": "This is no accident. You earned this."},
    "dolphin": {"positive": "Look at you go!",                  "neutral": "*clicks encouragingly*",    "milestone": "Look how far you've come!"},
    "panda":   {"positive": "Good. Now rest.",                   "neutral": "*munches bamboo*",          "milestone": "You did it. I'm proud. *keeps eating*"},
    "dragon":  {"positive": "Keep that fire burning.",           "neutral": "*watches silently*",        "milestone": "You didn't come this far to only come this far."},
    "phoenix": {"positive": "Every day, you rise again.",        "neutral": "*glows softly*",            "milestone": "Transformation in progress. Beautiful."},
}

MAX_TICKETS = 10
MAX_STARS = 5


def load_data():
    """Load buddy data from JSON, or return defaults."""
    if DATA_FILE.exists():
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "tickets": 0,
        "total_pulls": 0,
        "collection": {},
        "active_buddy": None,
        "last_reaction_date": None,
        "ticket_log": [],
    }


def save_data(data):
    """Save buddy data to JSON."""
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_today(tz_offset_seconds=0):
    """Get today's date string in the user's timezone."""
    tz = timezone(timedelta(seconds=tz_offset_seconds))
    return datetime.now(tz).strftime("%Y-%m-%d")


def pick_pet():
    """Weighted random selection of a pet based on rarity."""
    # Build weighted pool
    pool = []
    weights = []
    for pet_id, info in PETS.items():
        pool.append(pet_id)
        weights.append(RARITY_WEIGHTS[info["rarity"]])
    return random.choices(pool, weights=weights, k=1)[0]


# --- Subcommands ---

def cmd_status(args):
    data = load_data()
    owned_count = sum(1 for v in data.get("collection", {}).values() if v.get("owned"))
    total_pets = len(PETS)
    result = {
        "tickets": data.get("tickets", 0),
        "total_pulls": data.get("total_pulls", 0),
        "owned": owned_count,
        "total_available": total_pets,
        "active_buddy": data.get("active_buddy"),
        "active_buddy_name": PETS[data["active_buddy"]]["name"] if data.get("active_buddy") and data["active_buddy"] in PETS else None,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))


def cmd_pull(args):
    data = load_data()
    tickets = data.get("tickets", 0)

    if tickets < 1:
        print(json.dumps({
            "success": False,
            "error": "no_tickets",
            "message": "No tickets available.",
            "tickets": 0,
        }, indent=2, ensure_ascii=False))
        return

    pet_id = pick_pet()
    pet_info = PETS[pet_id]
    today = get_today(args.tz_offset)

    is_new = pet_id not in data.get("collection", {}) or not data["collection"].get(pet_id, {}).get("owned")
    is_duplicate = not is_new

    if "collection" not in data:
        data["collection"] = {}

    if is_new:
        data["collection"][pet_id] = {
            "owned": True,
            "stars": 0,
            "obtained_at": today,
        }
    else:
        current_stars = data["collection"][pet_id].get("stars", 0)
        if current_stars < MAX_STARS:
            data["collection"][pet_id]["stars"] = current_stars + 1

    data["tickets"] = tickets - 1
    data["total_pulls"] = data.get("total_pulls", 0) + 1

    # Auto-set active buddy if this is the user's first pet
    first_pet = sum(1 for v in data["collection"].values() if v.get("owned")) == 1 and is_new
    if first_pet:
        data["active_buddy"] = pet_id

    save_data(data)

    result = {
        "success": True,
        "pet_id": pet_id,
        "pet_name": pet_info["name"],
        "rarity": pet_info["rarity"],
        "personality": pet_info["personality"],
        "is_new": is_new,
        "is_duplicate": is_duplicate,
        "stars": data["collection"][pet_id]["stars"],
        "tickets_remaining": data["tickets"],
        "first_pet": first_pet,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))


def cmd_collection(args):
    data = load_data()
    collection = data.get("collection", {})
    active = data.get("active_buddy")

    owned = []
    for pet_id, state in collection.items():
        if state.get("owned") and pet_id in PETS:
            info = PETS[pet_id]
            owned.append({
                "id": pet_id,
                "name": info["name"],
                "rarity": info["rarity"],
                "personality": info["personality"],
                "stars": state.get("stars", 0),
                "obtained_at": state.get("obtained_at"),
                "is_active": pet_id == active,
            })

    # Sort by rarity (legendary first) then name
    rarity_order = {"legendary": 0, "epic": 1, "rare": 2, "common": 3}
    owned.sort(key=lambda p: (rarity_order.get(p["rarity"], 99), p["name"]))

    result = {
        "owned_count": len(owned),
        "total_available": len(PETS),
        "tickets": data.get("tickets", 0),
        "pets": owned,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))


def cmd_set_active(args):
    data = load_data()
    pet_id = args.pet

    if pet_id not in PETS:
        print(json.dumps({"success": False, "error": "unknown_pet", "message": f"Unknown pet: {pet_id}"}))
        return

    if pet_id not in data.get("collection", {}) or not data["collection"][pet_id].get("owned"):
        print(json.dumps({"success": False, "error": "not_owned", "message": f"You don't own {PETS[pet_id]['name']} yet."}))
        return

    data["active_buddy"] = pet_id
    save_data(data)

    print(json.dumps({
        "success": True,
        "active_buddy": pet_id,
        "name": PETS[pet_id]["name"],
        "personality": PETS[pet_id]["personality"],
    }, indent=2, ensure_ascii=False))


def cmd_add_tickets(args):
    data = load_data()
    current = data.get("tickets", 0)
    added = min(args.amount, MAX_TICKETS - current)

    if added <= 0:
        print(json.dumps({
            "success": False,
            "error": "ticket_cap",
            "message": f"Ticket cap reached ({MAX_TICKETS}). Pull some pets first!",
            "tickets": current,
        }, indent=2, ensure_ascii=False))
        return

    data["tickets"] = current + added
    today = get_today(args.tz_offset)

    if "ticket_log" not in data:
        data["ticket_log"] = []

    data["ticket_log"].append({
        "reason": args.reason,
        "amount": added,
        "date": today,
    })

    # Keep only last 50 log entries
    if len(data["ticket_log"]) > 50:
        data["ticket_log"] = data["ticket_log"][-50:]

    save_data(data)

    print(json.dumps({
        "success": True,
        "added": added,
        "tickets": data["tickets"],
        "reason": args.reason,
    }, indent=2, ensure_ascii=False))


def cmd_reaction(args):
    data = load_data()
    active = data.get("active_buddy")

    if not active or active not in PETS:
        print(json.dumps({"success": False, "error": "no_active_buddy", "message": "No active buddy set."}))
        return

    context = args.context  # "positive", "neutral", or "milestone"
    pet_reactions = REACTIONS.get(active, {})
    reaction = pet_reactions.get(context, pet_reactions.get("neutral", "..."))

    print(json.dumps({
        "success": True,
        "pet_id": active,
        "pet_name": PETS[active]["name"],
        "context": context,
        "reaction": reaction,
    }, indent=2, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description="Buddy Manager — Virtual pet gacha system")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # status
    sp_status = subparsers.add_parser("status", help="Show ticket balance and buddy info")
    sp_status.add_argument("--tz-offset", type=int, default=0, help="Timezone offset in seconds from UTC")

    # pull
    sp_pull = subparsers.add_parser("pull", help="Spend 1 ticket to pull a random pet")
    sp_pull.add_argument("--tz-offset", type=int, default=0, help="Timezone offset in seconds from UTC")

    # collection
    subparsers.add_parser("collection", help="Show all owned pets")

    # set-active
    sp_active = subparsers.add_parser("set-active", help="Set a pet as active buddy")
    sp_active.add_argument("--pet", required=True, help="Pet ID to set as active")

    # add-tickets
    sp_tickets = subparsers.add_parser("add-tickets", help="Award tickets for an achievement")
    sp_tickets.add_argument("--amount", type=int, required=True, help="Number of tickets to add")
    sp_tickets.add_argument("--reason", required=True, help="Achievement description")
    sp_tickets.add_argument("--tz-offset", type=int, default=0, help="Timezone offset in seconds from UTC")

    # reaction
    sp_react = subparsers.add_parser("reaction", help="Get a reaction from the active buddy")
    sp_react.add_argument("--context", required=True, choices=["positive", "neutral", "milestone"],
                          help="Context for the reaction")

    args = parser.parse_args()

    commands = {
        "status": cmd_status,
        "pull": cmd_pull,
        "collection": cmd_collection,
        "set-active": cmd_set_active,
        "add-tickets": cmd_add_tickets,
        "reaction": cmd_reaction,
    }

    commands[args.command](args)


if __name__ == "__main__":
    main()
