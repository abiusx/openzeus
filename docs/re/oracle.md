# Oracle: running the original game and dumping its state

`zeus-run` from refs/zeus-poseidon-arm64 runs the **unmodified GOG Zeus.exe** in an x86 emulator
(Unicorn) on this Mac, headless and deterministic (virtual clock: the same script gives the same
ticks). We added a raw state dump to it.

## Build (done 2026-10-26)
```
brew install cmake ninja pkgconf sdl2 unicorn
cd refs/zeus-poseidon-arm64
git apply ../../re/oracle/zeus-run-state-dump.patch     # our local addition (base commit in re/oracle/zeus-run-base-commit)
cmake -S . -B build -G Ninja && cmake --build build
```

## Run
```
O=re/oracle/runs/NAME; mkdir -p $O/dump
ZEUS_STATE_DUMP=$PWD/$O/dump ZEUS_STATE_DUMP_EVERY=50 \
  refs/zeus-poseidon-arm64/build/zeus-run --run zeus-original/app/Zeus.exe --headless --deterministic \
  --write-dir $O/write --seconds 90 --state-log $O/state.txt --screenshot $O/end.bmp --script "SCRIPT"
```
- Script: `T:action; ...` with T = virtual seconds; actions `click x,y`, `rclick x,y`, `key CODE`,
  `char CODE` (see the arm64 tests/scenarios/*.txt and docs/getting-started.md). Screen 800x600.
- `--no-native` runs every game function emulated (pure original); the default replaces some hot
  paths with native code that is proven identical.
- Output: `dump/zones.txt` (block, address, size, offset), and `dump/tick_NNNNNN.bin`: all 140 state
  zones (the 136 save blocks + RNG tick area + recomputed vars), about 4.5 MB per dump, taken at the
  entry of simulation_tick (0x00513A30).
- Read with `tools/oracle.py` (`Dump(path).block(rank)`, `.at(address, fmt)`).
- `ZEUS_STATE_DUMP_FROM=A ZEUS_STATE_DUMP_TO=B` (local addition 10-30, same patch): dump only ticks A..B (every
  ZEUS_STATE_DUMP_EVERY), e.g. every tick around the moment a shot is wanted without 4.5 MB for every tick before it.
- `ZEUS_STATE_DUMP_ZONES=17,16,4` (local addition 11-02, same patch): only these blocks (zones.txt lists what is
  written), e.g. tick-by-tick terrain without 4.2 MB per dump (tools/oracle_roads.py).
- `ZEUS_STATE_DUMP_EXTRA=ADDR:SIZE,...` (local addition 11-02, same patch): memory outside the save zones (hex address,
  decimal size), written after the zones and listed in zones.txt as block -2 (`Dump.at` reads it by address), e.g. the
  invaders' presence grid `c5bd98:51984` (tools/oracle_invcity.py).
- Every script `shot` prints `shot PATH ticks K` on stderr (local addition 10-30, same patch: the ticks run so far,
  equivalence.cpp g_oracle_ticks): the shot shows the state of dump tick_K (entry of tick K), so shots taken by
  virtual second can be matched to dumps (keep stderr in the run's log).

Difficulty (10-30): Open Play Sandbox runs play at Easy (the config default; empty --write-dir), "See a working
city" runs at VeryEasy; ours defaults to Normal. Compare at the run's level (`tools/difficulty_check.py`,
docs/logic/difficulty.md "Oracle runs and check").

## Pokes (local addition, 10-28)
`ZEUS_POKE=FILE` (same patch, re/oracle/zeus-run-state-dump.patch; needs `--state-log`, e.g. `/dev/null`): one poke
per line, `TICK ADDRESS SIZE VALUE` (decimal tick counted from the first simulation_tick, hex address, size 1/2/4,
decimal value; '#' lines are comments), written at the entry of that tick before its dump. Used to set up states the menus cannot reach,
e.g. a sanctuary under construction (re/oracle/scenarios/sanctuary-build.txt; the poke file from
`tools/oracle_monument.py --poke`). The exe redraws a piece only when its stage changes, so poked pieces keep their
old picture until worked.

Camera pokes (10-31, bugs.md 363): poke an even top-left ROW (0x00DA2F68). At an odd row the exe draws the tiles of
even x + y 30 px left and those of odd x + y 30 px right of where the even-row rule puts them (its screen rows shear
apart; crack lines and anything spanning rows look broken). Play mode's camera for a shot: (60 COL - 6870, 15 ROW - 30)
at zoom 1/dpr (docs/play/rotation.md "Verification").

## Suite (11-02)
`python3 tools/oracle_suite.py OUTDIR [NAME ...]` runs every compare tool that replays ours against a stored run
(invasions land / walk / sea, the inv-city AI days and soldier walk, the horsemen's walk and AI days of
1B-inv-city-horse (horseman company 9 in hold, tools/oracle_invcity.py OIC_COMP=9 OIC_ICON=951,121), route mode 2, road drags, monster missile, guardians, arrows, troops march, requests,
quake, lava, tidal waves, effects, schools, campaign flow, tutorials; `--list`), one output file per check, and
prints each one's summary. Run it before and after a change that moves timing and diff the two directories.
Pairing: ours' state after N ticks is dump N (Game.step's order is simulation_tick's since 11-02; docs/logic/
time-core.md "Ours"); events the exe starts inside a tick are spawned in ours' run_day by a day hook
(tools/oracle_invasion.py `arm`), not between steps.

## Verified
Tutorial scenario: 1,529 ticks in 6 s. The tick-1500 dump gives treasury 14745 (city+0x0C),
population 92 (city+0x24), year −1989, month 4, all matching the screenshot (May 1989 BC).

## Plan
1. A scenario that starts Open Play Sandbox and builds a small city (houses, roads, fountain,
   farm, granary, agora…), dumping every tick.
2. Our Python sim loads the state at tick N and runs to N+k; then diff it against the dump, zone by
   zone and field by field.

## Disk (2026-10-31)
State dumps are ~4.2 MB each; runs reached 32 GB. `python3 tools/oracle_compress.py [RUN ...]` compresses every
`dump/tick_NNNNNN.bin` into `tick_NNNNNN.bin.zst` (zstd level 9, ~38x, each verified before the .bin is removed;
Python 3.14 compression.zstd, no other dependency). zeus-run still writes plain .bin: run the tool after a new run.
Screenshots: `python3 tools/oracle_compress.py --shots [RUN ...]` turns every run's .bmp into lossless WebP (~4x;
each decoded back and compared pixel by pixel first). `oracle.shot(path)` resolves a cited .bmp path to its .webp;
every tool that opens a shot goes through it. 10-31: dumps 19.3 GB -> 0.48 GB, shots ~13 GB -> ~3 GB.
Every reader goes through tools/oracle.py: `read_dump(path)` (a .bin path that no longer exists falls back to its
.zst, so paths in docs keep working), `dump_files(dir)` (plain names, tick order), `Dump(path)`. Shell globs in
tool usage lines are `tick_*.bin*`.

