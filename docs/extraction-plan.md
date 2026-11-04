# Extraction plan

## A. Logic
1. **Model data (easy wins).** Parse `Model/*.txt` into JSON. That gives every building, house level, and unit stat for each difficulty.
2. **Manuals.** Pull the rules from the PDFs: walker/service coverage, industry chains, trade, religion, military.
3. **Zeus.exe (hard).** Ghidra decompilation for anything not in the data: walker pathing and roaming, service coverage decay, house evolution ticks, the desirability spread algorithm, the economy (production rates, storage), fire/collapse/crime/disease rolls, god relations, monsters, trade/empire, sentiment. Write each subsystem up in `docs/logic/<subsystem>.md`.
4. **Existing knowledge.** Community wikis and strategy guides, plus open-source reimplementations of the sibling games (Julius/Augustus for Caesar III, Akhenaten for Pharaoh). The engine family is close, so their code explains a lot.

## B. Sprites
Write our own SG3/555 parser in Python and dump every image (with animation frames and offsets) to PNG, plus a JSON atlas: file → group → frame, sizes, anchor offsets, and isometric footprint.

## Other things worth extracting
- **Text strings** (`*.eng`): building names, descriptions, advisor messages, event text. Useful as a template for our own writing.
- **Scenario/campaign data** (`Adventures/*.pak`): maps, starting conditions, goals, and event scripts. Shows how missions are structured.
- **Empire/trade map** data, and the god/hero/monster definitions.
- **Audio**: plain files, already usable as reference.
- **Tile and terrain system**: tile sizes, the isometric projection, and how terrain is encoded.
- **Save format**: optional. Its fields reveal the full simulation state, which works as a checklist for our data model.

## Tools
- `innoextract`: installed, done
- `ffmpeg`, `python3`: installed
- **Ghidra** (needs a JDK): for `Zeus.exe`
- Optional: **Wine** or a Windows VM to run the original and check behavior against our simulation
