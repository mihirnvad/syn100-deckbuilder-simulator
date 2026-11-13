"""Convert Cards.xlsx -> cards.json

Usage:
    python convert_cards.py [path/to/Cards.xlsx] [cards.json]

Requires: pip install openpyxl

Sheet layout assumptions:
  - Row 1 holds group headers (Neutral, Clean Energy Starters, ...) above the
    first column of each group.
  - Row 2 holds column headers; every "Cost" cell starts a 4-wide group:
    Cost / Name / Text / Quantity. Any extra columns (e.g. "Ignore") are skipped.
  - Cost may be a number or a string like "(4)". Quantity may be a number or
    "x7". Blank quantity = 1, except in the Neutral group where blank means an
    unlimited supply pile (qty: null) — wood, coal, natural gas, synthetic fuel.
  - "money": if a card's text starts with "Gain N money" (and not "for each"),
    the app adds N money automatically when the card is played. Anything more
    conditional is left for players to adjust by hand.
  - "resources": if a card's text starts with "Gain/Take N coal|natural gas|
    wood|synthetic fuel", the app takes N of that neutral card into play
    automatically when the card is played. Conditional ones stay manual.
  - Rows without a name or a parseable cost are skipped (blank rows, the
    "total" / "avg cost" footer rows).
"""
import json
import re
import sys

import openpyxl

# Cards whose effect lets the player trash (remove from the game) cards.
# Trashing is otherwise not allowed, so the app only shows a Trash button after
# one of these is played. Value = how many trashes the card grants.
# Keyed by card name; edit here or directly in cards.json ("trash" field).
TRASH_GRANTS = {
    "Upcycling": 1,
}

# Game setup written into cards.json under "setup" (hand-editable there too).
#   starting_play: cards each team begins with in its In play area, keyed by
#                  card name; they are taken out of that team's permanents deck.
#   power_phase_every: a Power Generation Phase reminder every N turns.
SETUP = {
    "starting_play": {
        "clean": {"Windmill": 2, "Hydroelectric plant": 1},
        "dirty": {"Natural gas plant": 2, "Small coal plant": 2},
    },
    "power_phase_every": 4,
    "max_turns": 30,
}

GROUPS = {
    "neutral":                  ("neutral", "neutral"),
    "clean energy starters":    ("clean", "starter"),
    "clean energy permanents":  ("clean", "permanent"),
    "clean energy shop":        ("clean", "shop"),
    "dirty energy starters":    ("dirty", "starter"),
    "dirty energy permanents":  ("dirty", "permanent"),
    "dirty energy shop":        ("dirty", "shop"),
}


def parse_int(v):
    """'(4)' -> 4, 'x7' -> 7, 4.0 -> 4, None -> None"""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return int(v)
    m = re.search(r"\d+", str(v))
    return int(m.group()) if m else None


MONEY_RE = re.compile(r"^\s*gain\s+(\d+)\s+money\b(?!\s+for\s+each)", re.IGNORECASE)
# "Gain 2 coal." / "Take 2 wood cards ..." at the start of the text =
# unconditional, so the app takes those resource cards from the neutral supply
# automatically when the card is played. Conditional ones ("Then, if you are
# on a plains tile, ... take 4 coal cards") stay manual.
RESOURCE_RE = re.compile(r"^\s*(?:gain|take)\s+(\d+)\s+(coal|natural gas|wood|synthetic fuel)\b", re.IGNORECASE)
# Neutral cards that are resources: they always go into play ("keep this card
# in front of you"), whether bought, taken or granted by another card.
RESOURCE_NAMES = {"wood", "coal", "natural gas", "synthetic fuel"}


def auto_money(text):
    m = MONEY_RE.match(text)
    return int(m.group(1)) if m else 0


def auto_resources(text, neutral_by_name):
    m = RESOURCE_RE.match(text)
    if not m:
        return {}
    card = neutral_by_name.get(m.group(2).lower())
    return {card["id"]: int(m.group(1))} if card else {}


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def main(xlsx_path, out_path):
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    ws = wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    group_row, header_row, data_rows = rows[0], rows[1], rows[2:]

    # Locate each Cost column and the group header it belongs to.
    columns = []  # (start_col, team, pile)
    for c, h in enumerate(header_row):
        if h is None or str(h).strip().lower() != "cost":
            continue
        group = None
        for g in range(c, -1, -1):
            if group_row[g] is not None and str(group_row[g]).strip():
                group = str(group_row[g]).strip().lower()
                break
        if group not in GROUPS:
            raise SystemExit(f"Unknown group header {group!r} above column {c + 1}")
        columns.append((c, *GROUPS[group]))

    cards = []
    seen_ids = set()
    for start, team, pile in columns:
        for row in data_rows:
            cost = parse_int(row[start]) if start < len(row) else None
            name = row[start + 1] if start + 1 < len(row) else None
            text = row[start + 2] if start + 2 < len(row) else None
            qty = parse_int(row[start + 3]) if start + 3 < len(row) else None
            if name is None or not str(name).strip() or cost is None:
                continue
            name = str(name).strip()
            text = str(text).strip() if text is not None else ""
            cid = f"{team}-{pile}-{slug(name)}"
            if cid in seen_ids:
                raise SystemExit(f"Duplicate card id {cid}")
            seen_ids.add(cid)
            lname = name.lower()
            cards.append({
                "id": cid,
                "team": team,
                "pile": pile,
                "cost": cost,
                "name": name,
                "text": text,
                # Neutral + blank quantity = unlimited supply pile.
                "qty": qty if qty is not None else (None if pile == "neutral" else 1),
                "money": auto_money(text),
                # Permanents go to the player's Permanents area instead of the
                # discard pile when bought. Buildings/policies listed outside the
                # Permanents groups (e.g. Neutral "Power line (building)") too.
                "permanent": pile == "permanent" or "(building)" in lname or "(policy)" in lname,
                "resource": pile == "neutral" and lname in RESOURCE_NAMES,
                "trash": TRASH_GRANTS.get(name, 0),
            })
    # Second pass: resource auto-take needs the neutral card ids.
    neutral_by_name = {c["name"].lower(): c for c in cards if c["pile"] == "neutral"}
    for c in cards:
        c["resources"] = auto_resources(c["text"], neutral_by_name)

    missing = set(TRASH_GRANTS) - {c["name"] for c in cards}
    if missing:
        print(f"WARNING: TRASH_GRANTS names not found in sheet: {sorted(missing)}")

    # Resolve starting_play names to card ids for the given team.
    setup = {k: v for k, v in SETUP.items() if k != "starting_play"}
    setup["starting_play"] = {}
    for team, wanted in SETUP["starting_play"].items():
        setup["starting_play"][team] = {}
        for name, n in wanted.items():
            match = [c for c in cards if c["team"] == team and c["name"].lower() == name.lower()]
            if not match:
                raise SystemExit(f"starting_play: no {team} card named {name!r}")
            setup["starting_play"][team][match[0]["id"]] = n

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"source": xlsx_path.replace("\\", "/").split("/")[-1], "setup": setup, "cards": cards},
                  f, indent=2, ensure_ascii=False)

    # Summary
    print(f"Wrote {len(cards)} card definitions to {out_path}")
    print(f"Setup: power phase every {setup['power_phase_every']} turns, {setup['max_turns']} turns max")
    for team, cards_ in setup["starting_play"].items():
        print(f"  {team} starts with in play: " + ", ".join(f"{n}x {cid}" for cid, n in cards_.items()))
    print()
    for _, team, pile in columns:
        group = [c for c in cards if c["team"] == team and c["pile"] == pile]
        total = sum(c["qty"] or 0 for c in group)
        print(f"== {team} / {pile}: {len(group)} cards, {total} copies")
        for c in group:
            flag = ((" [PERMANENT]" if c["permanent"] else "")
                    + (" [RESOURCE]" if c["resource"] else "")
                    + (f" [GRANTS {c['trash']} TRASH]" if c["trash"] else "")
                    + (f" [+{c['money']} MONEY ON PLAY]" if c["money"] else "")
                    + "".join(f" [TAKES {n} {rid.split('-')[-1].upper()} ON PLAY]" for rid, n in c["resources"].items()))
            qty = "unlimited" if c["qty"] is None else f"x{c['qty']}"
            print(f"   ({c['cost']}) {c['name']} {qty}{flag}")
        print()


if __name__ == "__main__":
    xlsx = sys.argv[1] if len(sys.argv) > 1 else "Cards.xlsx"
    out = sys.argv[2] if len(sys.argv) > 2 else "cards.json"
    main(xlsx, out)
