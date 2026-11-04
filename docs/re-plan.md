# Reverse-engineering plan (milestone 1: sandbox simulation)

Goal: a written, testable description of everything the **open-play sandbox** simulates, precise
enough to port to Python and compare tick by tick with the original.

## Sources, in order of authority
1. **`Zeus.exe` decompiled** (`re/decomp/zeus.c`, Ghidra 12.2, with the 322 names from arm64's
   `noms.tsv` applied). Ground truth.
2. **Model data** (`extracted/model/*.json`): numbers the exe loads at start.
3. **arm64 docs** (`refs/zeus-poseidon-arm64/docs/engine/*`, `formats/*`): verified addresses,
   tick order, formats.
4. **eZeus** (`refs/eZeus`): readable C++ for every mechanic. Use it to find what to look for and
   to name things, **not** as the source of numbers (it's known to differ).
5. Manuals (PDF): designer intent and player-facing rules.

Every rule we write down is marked **verified** (read in the exe, with an address) or
**hypothesis** (from eZeus, the manual, or inference).

## Subsystems (one doc each in docs/logic/)
| # | Subsystem | Notes |
|---|---|---|
| 1 | time | tick, 51-step cycle, months/years, RNG (simulation.md has the skeleton) |
| 2 | map & terrain | tile grid, terrain types, elevation, fertility, resources, water (terrain.md) |
| 3 | buildings | types, sizes, placement rules, road access, construction, damage/fire/collapse |
| 4 | labor & employment | labor pool, workers, employment priority, wages |
| 5 | population & housing | immigration/emigration, house evolution, desirability, needs, consumption |
| 6 | walkers | roaming, destinations, pathfinding, service coverage, carts |
| 7 | production chains | farms, orchards, herding, hunting, fishing, raw materials, workshops |
| 8 | storage & distribution | granary, storehouse, agora, vendors, delivery rules |
| 9 | finance | taxes, wages, treasury, mint, debt |
| 10 | services | water, health/disease, fire/collapse watch, crime, culture, education/science |
| 11 | religion | sanctuaries, gods (moods, blessings, wrath), heroes, monsters |
| 12 | trade & empire | world cities, trading post/dock, routes, prices, requests |
| 13 | military | troops, horses, armor, invasions (probably off in the sandbox but needed later) |
| 14 | sentiment & ratings | mood, tax sentiment, advisors |

## Validation
arm64's emulator (`zeus-run`) runs the original exe deterministically and can dump game state
per tick. Plan: build it, play sandbox scenarios, and diff the state against our port.
