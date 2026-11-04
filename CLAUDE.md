# OpenZeus: guide for contributors and coding agents

OpenZeus re-implements Zeus: Master of Olympus (TM) in Python, with a browser client. The original game is the
reference for every rule and number: a change is right when it does what Zeus.exe does. This file is for people
and coding agents working on the code; players start with README.md.

## Layout
- `sim/`: the simulation: state and rules, no drawing code. `python3 -m sim ...` is its command line, with the
  state in a save file. `python3 -m sim live SAVE` runs a game and serves the browser client.
- `viewer/play/`: the browser client (WebGL 2). It draws what the server sends and sends the player's commands.
- `data/`: the rules and numbers as JSON, built by `tools/build_data.py` and other builders. Hand-editable.
- `tools/`: extractors, data builders, checks. `tools/assets.py` builds or installs the game's assets.
- `docs/`: everything we know and decided. Start at `docs/README.md`. Mechanics are in `docs/logic/`,
  reverse-engineering notes in `docs/re/`, the client in `docs/play/`.
- `tests/`: `python3 tests/test_sim.py` runs every test module in parallel. `python3 tests/test_sim.py military`
  runs one module, `python3 tests/test_sim.py test_NAME` one test.
- `scripts/`: benchmark games (`boom.txt`, `full.txt`) that must keep working.
- The original's sprites, sounds and text are not in this repository. `tools/assets.py` builds them from your own
  install of the game or installs them from the asset pack (docs/assets.md).

## Faithful to the original
- Zeus.exe is the source of truth. Other remakes are hints at most: check every number against the exe.
- Port every difference you find. Don't log a known mismatch as a leftover.
- Changes we make on purpose are marked "ours" in the docs and, where it makes sense, can be switched off in the
  client's Options. Screen-size adaptations (zoom, scrolling, wide windows, upscaled sprites) count as "ours".
- Bugs in the original that we fix on purpose are listed in `data/fixes.json` (`"fixed": false` restores the
  original's rule) and in `docs/play/bugs.md`.
- No shortcuts: everything moves at the original's pace (walkers 15 ticks per tile), nothing is produced or moved
  instantly.

## Evidence
- Function names and addresses refer to the GOG build of Zeus.exe, SHA-256
  382bcd286192a06eb8fdc45f5c37390a19999f5db9c940c3ce2dfcd775e90a57.
- docs/re/method.md describes the decompile, the names we gave the original's functions (`re/names/*.tsv`) and its
  structures (`re/structs/*.tsv`). The decompile itself is never committed.
- The oracle runs the original game headless and dumps its state, to compare with ours tick by tick:
  docs/re/oracle.md. `python3 tools/oracle_suite.py OUTDIR` runs every comparison.

## Key facts
- The original runs one tick per call of simulation_tick (0x513A30). Each tick does one step of a 51-step cycle of
  city work; a cycle is a day, and 16 days make a month. Maps are 228 x 228 tiles.
- The original's figure, building and map-point positions are logical coordinates. Our grids use raw coordinates:
  raw = logical + `World.origin`. Map points are converted once, in `sim/world.py` (docs/logic/map-terrain.md
  "Logical and raw coordinates").
- Tick order: `Game.step` counts the tick, runs its cycle step's work, then moves every figure (walkers, animals,
  soldiers), as simulation_tick does. Our state after N ticks matches oracle dump N in every field the oracle dumps
  (docs/logic/time-core.md).

## Conventions
- Write decisions and findings to `docs/` as you make them.
- Every derived file comes from a script in `tools/`. A doc in `docs/` gives the steps to rebuild it: commands,
  inputs, outputs, downloads with URL and SHA-256, and tool versions. No one-off shell steps.
- Rules and numbers belong in `data/`, not in code. Keep features in modules with narrow interfaces. The engine core
  (walkers, tick, map) is the exception.
- Before a pull request: the full tests pass, and `python3 tools/state_hash.py full` gives the same hash as before
  your change (run it on the main branch first), or the pull request explains why it changed.
- Log every bug report and its outcome in `docs/play/bugs.md`, including reports where the original does the same
  ("as original").
- Commit messages: short and dense.

## Drawing changes
The client follows the original's draw order, one rule in `viewer/play/order.js` (docs/play/draw-order.md). Never add
a depth constant. Before calling a drawing change done:
- Read back the drawn pixels (gl.readPixels after the frame) along every edge the change touches: panel edges,
  minimap borders, tile and sprite seams, window frames.
- Test at browser zoom 125 % (devicePixelRatio 1.25).
- Compare with screenshots of the original. A line the original also has is not a bug.
- Big things break first. On a large city, check every view and zoom level the change affects. Look at the palace,
  sanctuaries and monuments, walls and gatehouses, villas, the stadium, agoras, avenues, docks, bridges, and raised
  terrain (cliffs, hills, rocks, marble).
- Checks: `node tools/draw_order_check.mjs URL` (the play page of your own server), `tools/gpu_check.mjs` (whole-map
  pixel regression), `tools/comms_check.mjs` (client/server protocol).

## Testing with the client
Run your own server on a free port, on a copy of a save: the server writes the city back to its save file. Drive it
with `tools/play_cdp.mjs`, which starts a headless, muted Chrome with a temporary profile. Close your servers and
browsers when done.
