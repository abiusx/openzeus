# TODO

Open work on OpenZeus. Most items name the original's function (an address in Zeus.exe) or the bug report they come
from (docs/play/bugs.md). Check each fix against Zeus.exe, with the decompile or an oracle run (docs/re/oracle.md).
To take an item, name it in a GitHub issue, or comment on its existing issue, then send a pull request.
"Ours" means OpenZeus's behaviour where it differs from the original (CLAUDE.md, "Faithful to the original").

## Simulation

- [ ] Floating debris: when a map starts, the original creates 20 floating-debris figures at the sea entry
  (FUN_004E0DE0, handler 0x004B8110). OpenZeus does not model them (docs/logic/episode-transition.md B10).
- [ ] Map entry and exit signs: on every load, the original puts a sign on a free tile next to each entry and exit
  point and blocks that tile (FUN_004A1D30). Ours draws no sign, and the tile stays buildable
  (docs/logic/episode-transition.md F12).
- [ ] Beach tile objects: at map load the original makes objects on and beside beach tiles (0x00666930, made by
  FUN_004176F0). Depending on their picture, some of them block walkers and road drags. Ours has neither the objects
  nor their pictures (docs/play/terrain.md section 7).
- [ ] Priests: a priest takes a sheep, goat or bull to its sanctuary as an offering, in rounds about 4 months apart,
  two priests a round. Ours lets every arriving priest make its offering; the original may hold the second priest and
  its animal until the next round (bugs.md 340). Check with an oracle run: count the sheep over a year, with two
  sanctuaries.
- [ ] Daily step 31: the original sends out every building's walkers in building-id order
  (buildings_spawn_walkers 0x0048CFB0). Ours runs the step one kind of building at a time.
- [ ] Palace and sanctuary companies: the original keeps them as lists of soldier figures (formations_refresh).
  Ours keeps the soldiers at home as a count.
- [ ] The random number generator: port the original's (random_next 0x004488C0) and draw from it in the original's
  order, so oracle runs match tick for tick. Swapping in the generator alone does not make the runs match, because
  the order of the draws matters (docs/logic/time-core.md 6.1).
- [ ] Heroes on deep water: a hero crossing water is drawn swimming, and the original has no death case for that
  state (bugs.md 392). Find what the original does when a hero's health runs out there.
- [ ] Remaining checks: the statue carver's offset, ramp samples, the ox-pair mode-2 check,
  the meadow mask for animal placement, and god_resource_available.

## Play mode (the browser client)

- [ ] Build ghost: while dragging a road, the original shows the cost at the cursor (map_number_draw 0x004542B0);
  ours shows none. The ghost's diamonds should be the original's masked frame, not a translucent fill (bugs.md 466).
- [ ] Build ghost on slopes: the original shows either the tinted building or the diamonds. Ours shows both
  (bugs.md 389).
- [ ] Ramp ends: re-stamp the ramp-end pictures during a road drag, as roads_drag_place does (FUN_00460290).
- [ ] Carts and gods: the cases left in bugs.md 387 (carts whose heading is unknown) and 393 (Hermes' walk-out
  frames, a god facing direction 0xB, a god on water, Ares leaving).
- [ ] Error messages over full screens: a refused command's message does not show while the world map is open
  (bugs.md 449). Show it over every screen, as the original's warnings do.
- [ ] Two new games in a row, with the clock paused, keep the first game's hidden-buildings list until a reload.
- [ ] In the walker info window, compare every figure's picture with an oracle screenshot, pixel by pixel
  (docs/play/info.md).
- [ ] Sanctuary builders are drawn inside the platform while they work. The draw rule says the original does the
  same; an oracle screenshot of an Ares sanctuary at about 40 % would confirm it and close bugs.md 394.

## Poseidon expansion

- [ ] Poseidon buildings, great monuments, Atlantean cities and their campaigns. They are
  off by default; `poseidon on` enables them. This includes the Atlantean branch of expedition_attitude_effects
  0x00483110 (docs/logic/world-map.md 6.8).

## Tooling

- [ ] Rename `scripts/`, which holds the benchmark games boom.txt and full.txt, to a name that says so (for example
  `benchmarks/`), and update every reference.
