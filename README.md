# Deck Table

Deck-building companion for the hybrid climate board game. The app handles only
shuffling, drawing, hands, discard/burn piles, the shop and the money/emissions/
quota/turn counters. Cards are inert data: players read the text and resolve
effects on the physical board.

## Files

- `index.html` — the whole app (vanilla JS, no build step).
- `cards.json` — card definitions. Hand-edit this between playtests.
- `convert_cards.py` — regenerates `cards.json` from `Cards.xlsx`.
- `Cards.xlsx` — the source spreadsheet.

## Run

Browsers refuse to `fetch()` a local file, so serve the folder:

```
python -m http.server 8000
```

then open <http://localhost:8000>. (Opening `index.html` directly also works:
the page falls back to a file picker for `cards.json`, and remembers the last
loaded copy.)

## Automatic updates on GitHub

`.github/workflows/cards-and-site.yml` runs on every push to `main`. If the
push changed `Cards.xlsx` (including an upload through the GitHub web UI), it
regenerates `cards.json`, commits it back, and then deploys the folder to
GitHub Pages. Pushes that only touch `cards.json` or `index.html` are deployed
as-is. For this to publish, set Settings → Pages → Source to **GitHub Actions**.

## Regenerate cards.json by hand

```
pip install openpyxl
python convert_cards.py Cards.xlsx cards.json
```

The script prints every card with its pile and quantity so you can check the
parse.

## cards.json format

```json
{ "id": "clean-shop-recycling", "team": "clean", "pile": "shop",
  "cost": 2, "name": "Recycling", "text": "...", "qty": 3, "permanent": false }
```

- `team`: `clean`, `dirty` or `neutral`.
- `pile`: `starter` (goes into that team's starting deck), `shop` (shuffled
  into that team's shop deck; 5 face-up at a time; bought cards join your
  deck), `permanent` (shuffled into that team's permanents deck; 3 face-up at
  a time; bought cards go into play for good), `neutral` (shared supply
  piles). Teams cannot buy from each other's shop or permanents.
- `permanent: true` cards go to the buyer's "In play" area instead of their
  discard pile when bought (also used for neutral buildings like Power line).
- `resource: true` (wood, coal, natural gas, synthetic fuel) cards also go
  into play whether bought or taken; only deck cards like State grants go to
  the discard pile when bought from the neutral supply.
- `qty`: number of copies. `null` on a neutral card means an unlimited supply
  pile (wood, coal, natural gas, synthetic fuel).
- `money`: added to the player's money automatically when the card is played.
  The converter fills it for text that starts with "Gain N money" (Income,
  State grants, Public transit, Negligent gas leak, Wastewater injection).
  Anything conditional stays manual; edit the field to change this.
- `resources`: `{ "<neutral card id>": N }`, taken from the supply into play
  automatically when the card is played. The converter fills it for text that
  starts with "Gain/Take N coal|natural gas|wood|synthetic fuel" (Mining,
  Drilling, Sustainable biofuels). Conditional ones (Fracking, Strip Mining,
  Landfill Gas Recovery, Deforestation) stay manual via the Take buttons.

Identical cards in a player's "In play" area are shown stacked with a × count;
Burn/Remove act on one copy at a time.
- `trash`: how many cards playing this card lets you trash (remove from the
  game) this turn. Trash buttons only appear while that allowance is above 0.
  Set in `TRASH_GRANTS` in `convert_cards.py` or edit here directly.

## Rules the app enforces

- Only the Dirty team can burn cards (from hand, discard pile or in play).
- Trashing needs a played card with a `trash` value (currently Upcycling).
- Each team buys only from its own shop row; the Neutral supply is shared.
- Money resets to 0 at the end of your turn (unspent money is lost).
- Shared counters: Emissions (starts at 5) and Turn. Every 4th turn shows a
  Power Generation Phase reminder; the game ends after turn 30.
- Starting in-play cards: Clean begins with 2 Windmills and 1 Hydroelectric
  plant, Dirty with 2 Natural gas plants and 2 Small coal plants, taken out of
  each team's permanents deck.

These settings live in the `setup` block at the top of `cards.json`
(`power_phase_every`, `max_turns`, `starting_emissions`, `starting_play`), generated from `SETUP`
in `convert_cards.py`.

Game state is saved in the browser's localStorage; "New game" clears it.
