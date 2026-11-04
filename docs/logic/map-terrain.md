# Map: grids, terrain flags, regrowth, meadows, road networks

Status: **verified** from the exe unless marked. Addresses refer to GOG `Zeus.exe`.
Base material: `refs/zeus-poseidon-arm64/docs/engine/terrain.md` (re-checked here against
`re/decomp/zeus.c`; corrections are flagged). Names: `re/names/map-buildings.tsv`.

## Summary
The map is a set of 228×228 raw grids. The playable area is a diamond inside it. Each tile has
a u32 bit field of terrain flags plus a dozen per-tile byte/word grids. Simulation-relevant
rules here: the random byte per tile, regrowth of trees/reeds/meadows (cycle step 20), meadow
values, road networks (cycle step 7), and the "can this rectangle be built on" test.
Desirability is in [desirability.md](desirability.md); buildings in [buildings.md](buildings.md).

## 1. Coordinates (verified)
- Raw grid 228×228 = 51,984, row-major. Tile index = `base + 228*y + x`, `base = [0x00DA2F80]`
  (not saved; 10076 = 44*228+44 in the tutorial, i.e. logical (0,0) = raw (44,44)).
- W = `[0x00DA2F78]`, H = `[0x00DA2F7C]`; `[0x00DA2F84]` = 228 − W (row stride correction).
- Saved in the scenario block: +0x2C W, +0x30 H, +0x34 base, +0x38 stride correction (sandbox: 226, 226, 229, 2,
  i.e. logical (0,0) = raw (1,1)). Figure, building and scenario-point coordinates are logical; our sim's grids are
  raw (heroes-monsters.md "Logical vs raw coordinates", 1I 10-29: only the monster lairs are converted so far).
- Playable rows: for y < H, first tile index `0x00DA24B0[y]`, x from `0x00DA2BD0[y]` to
  `0x00DA2840[y]`−1 (used by regrowth and the terrain desirability pass).
- Diamond tests: `map_in_play_area` `0x00496010(x,y)` and `map_near_play_edge`
  `0x00496080(x,y,m)` take *absolute* coordinates (logical + `0x00DA2F90`/`0x00DA2F94`, or
  `index % 228`, `index / 228` of a raw index). `map_near_play_edge` returns **false outside**
  the diamond (only "inside and within m tiles of the edge" is true).
- Neighbours: N −228, NE −227, E +1, SE +229, S +228, SW +227, W −1, NW −229
  (`g_dir8_offsets` `0x0064324C`); 4-neighbour table `0x005F2318` = −228, +1, +228, −1.

## 2. Grids
| Grid | Address | Type | Sav rank | Meaning | Status |
|---|---|---|---|---|---|
| terrain | `0x00CCE128` | u32 | 17 | flags, section 3 | verified (bits marked) |
| building | `0x00D26E98` | i16 | 16 | id of the building on the tile | verified |
| draw | `0x00D404B8` | u8 | 15 | 0x40 = anchor tile; low bits = position in footprint (`building_footprint_place`) | verified |
| piece | `0x00D00D68` | u8 | 20 | low nibble = size−1 of what stands here; 0x10 set by house drag/roads; 0x80 with rock = desirability source | verified |
| random | `0x00CA7FF8` | u8 | 22 | fixed random byte per tile (section 4) | verified |
| desirability | `0x00C9B4E8` | i8 | 23 | [desirability.md](desirability.md) | verified |
| regrowth | `0x00C1C648` | u8 | 102 | 255 = grown; section 5; on marble = quarry depth 255/100/0 (5b) | verified |
| meadow value | `0x00C35C68` | u8 | 99 | section 6 | verified (formula) |
| scrub | `0x00C29158` | u8 | 109 | scrub amount painted by editor tool 174 (`0x0049CD80`, `+ __ftol` step not traced); also written by `trees_update_depth` `0x004A8E10` (ring distance); read by tree images (÷34) | verified (writers); scale hypothesis |
| elevation | `0x008E01FA` | i8 | 111 | 0..16 (editor clamps to 0x10); rendering 30 px/step | verified (clamp in `build_tool_click` 0x00404CD0 tools 177/178) |
| projected elevation | `0x008ECD0A` | i8 | 112 | display only | verified |
| ruin type | `0x00C688A8` | u8 | 108 | type byte (`Building+0x45`) of the building that stood here; 0x82 for a removed wall | verified (`0x004A07C0`, `0x004A09F0`) |
| wall damage | `0x00C753B8` | u16 | 25 | damage of wall tiles (terrain 0x4000); raised by enemies (`wall_damage_add` 0x00492830), lowered by maintenance walkers by model col 9 of type 121 (`0x004A5D90`) | verified (cross-ref military/services) |
| `0x00CB4B08` | | u8 | 21 | bridge piece 1..14 on road-over-water tiles (`0x0041D720`; 13/14 = short bridge, blocks ships), 15..20 race-track crossing (hypothesis); also used as an animation frame for other tiles (`0x00413380`); blocks the roadblock tool; see pathfinding.md §7.3 | partly |
| `0x00CC1618` | | u8 | 18 | cleared with the footprint; zero in samples | unknown |
| `0x00C8E9D8` | | u8 | 24 | non-zero blocks editor water/beach paint | unknown |
| `0x00B1E8F8` | | u32 | 105 | 2-bit fields (`0x004A3100`), decayed step 45 | unknown |
| road network | `0x00C4F288` | u8 | — | network id of road tiles (section 7) | verified |
| road flood step | `0x00C42778` | u8 | — | flood "wave" counter (section 7) | verified |
| route distance | `0x01079460` | i32 | — | distances of the last route BFS (walkers); 0 = unreachable | verified (use) |
| route grid | `0x0105FE40` | u16 | — | walkability bits (walkers) | cross-ref |
| ground image | `0x00D4CFC8` | u32 | — | graphics only | verified |

**Ground water:** no ground-water grid exists. No placement code tests one (fountains go
through the generic test). **verified** by the absence of any fountain branch in `build_commit`
`0x00498910`; the game text has no ground-water string.

## 3. Terrain flags (`0x00CCE128`)
Evidence: editor brushes in `editor_paint` `0x0049DA10` (tool id = BUILD_* row), plus readers.
| Bit | Meaning | Evidence | Status |
|---|---|---|---|
| 0x1 | tree | tool 171 `0x0049CCA0` sets it; regrowth | verified |
| 0x2 | rock | tool 192 `0x0049CD10(…,2)` | verified |
| 0x100000 / 0x200000 | rock kind, with 0x2: 0x100002 copper (tool 193), 0x200002 silver (194), 0x300002 "cliff rock" (195); 0x300000 without 0x2 = orichalc (219) | `0x0049CD10`; miners map foundry 50→0x100002, mint 48→0x200002, refinery 211→0x300000 (`buildings_spawn_walkers` 0x0048CFB0) | verified |
| 0x20000 | marble (quarry, tool 144); 0x120000 = black marble (tool 218); marble quarry 49→0x20000, black marble shop 213→0x120000 | `0x0049D210`, `0x0048CFB0` | verified |
| 0x4 | water | tool 172 | verified |
| 0x8 | occupied by a building/structure | `building_footprint_place` ORs 8 | verified |
| 0x10 | lava | tool 159 toggles it (`0x0049D110`) | verified (editor) |
| 0x20 | garden (gardens tool); spreads row 128 desirability; road placement clears it | `0x00493C80`, `road_set_tile` | verified |
| 0x40 | road | tool 179, `road_set_tile` 0x0049FF10 | verified |
| 0x80 | scrub (tool 174 sets it with the scrub grid); tree depth pass | `0x0049CD80`, `0x0049CE40` | verified (writer); name from tool |
| 0x100 | flood plain (tool 160 `0x0049D190`, not on rocks) | | verified (editor) |
| 0x200 | cliff | terrain.md | verified |
| 0x400 | ramp (kept only on cliffs); roads through it call `0x00460290` | | hypothesis (name) |
| 0x800 | meadow | tool 176; regrowth; grazing | verified |
| 0x1000 | rubble: set by `building_footprint_to_rubble`; desirability −2/2 rings | `0x004A07C0`, `0x00493C80` | verified |
| 0x4000 | wall | terrain.md | verified |
| 0x8000 | cleared with buildings; read by a walker routine | | unknown |
| 0x10000 | beach (tool 188 `0x0049CF80`) | buildable test (all-in/all-out), no fire/collapse risk on it, counts as meadow for farms | verified (tool) |
| 0x40000 | marsh/reeds (tool 196) | | verified |
| 0x80000 | off-map border: every raw tile outside the diamond gets 0x80005 (`map_mark_off_diamond` 0x004962E0) | | verified |
| 0x800000 | kept only on cliffs | terrain.md | verified (rule) |
| 0x1000000 | disaster damage (set by terrain event object `0x00506D80`, destroys the building) | | hypothesis (lava/landslide) |
| 0x2000000 | earthquake fault (tool 173 `0x0049D050`); drawn as the land it is in play; an earthquake turns it to cracked rock 0x300002 + piece 0x80 and keeps the bit (events.md "Terrain disasters") | | verified (editor, oracle 1L5-quake) |
| 0x4000000 | deep water | terrain.md | verified |
| 0x10000000 | never regrows, blocks building | terrain.md | verified (rules) |
| 0x40000000 | display flag (set/cleared by `walker_draw`) | | verified |
| 0x80000000 | (0x00506330 is the landslide's boulder path, not the earthquake's: events.md "Terrain disasters") | | unknown |

Masks seen (all verified): building footprint keeps `t & 0x93872F90`; rubble `& 0x93873F90 | 0x1000`;
demolition `& 0x93872F94`; road endpoints refused on `0x5361227` (unless ramp/special rock);
`map_area_buildable` forbids `0x3DFFD66F` (section 8).

## 4. RNG and the random grid
RNG (also documented by time-core): two 31-bit registers e4 = `0x00F137E4`, e0 = `0x00F137E0`
(sav ranks 42/43). One draw = first `ring[0x00F13624] = [0x00F137D4]` (ring of 100 bytes at
`0x00F13628`, index wraps at 100), then 31 times for each register
`r' = r >> 1; if ((r >> 4) & 1) != (r & 1): r' |= 0x40000000`; then
`d0 = e4 & 0x7FFF` (`0x00F137D0`), `d4 = e4 & 0x7F`, `d8 = e4 & 7`, `c4 = e0 & 0x7FFF`,
`c8 = e0 & 0x7F`, `cc = e0 & 7`. Most callers inline this. **verified** (`random_next` 0x004488C0 and inline copies).

Random grid (`map_random_grid_fill` `0x00496330`, called at map reset `0x00496120`): for every
raw index i = 0..51983 in order: one draw, `grid_random[i] = (e4 & 0x7FFF) & 0xFF`. **verified.**
Buildings copy it at creation: `+0x4D = rnd & 0x7F`, `+0x34 = rnd & 6`.

## 5. Regrowth — `terrain_regrow` `0x004A7D30`, cycle step 20 (after `0x00485360`)
**verified.** Clears flags `0x00B1E8F0..F5`. List L = `0x00B16BB4` (4000 i32 tile indices):
trees are appended from the front (`front`, starts 0), reeds from the back (`back`, starts 3999).
Over the playable rows, tile by tile, g = regrowth[t], f = terrain[t]:
```
if f & 0x10000000: skip
if f & 0x1:                                   # tree
    if g == 255: (if flag F0 == 0: L[front++] = t); F1 = 1
    else: draw (random_next); g8 = (g + 4 + (e4 & 1)) & 0xFF; regrowth[t] = 255 if g8 < g else g8
          terrain_resource_image(t); F1 = 1
elif f & 0x40000:                             # reeds
    if g == 255: (if F2 == 0: L[back--] = t); F3 = 1      # F2 is never set: reeds are always listed
    else: draw; +35 + (e4 & 1), same saturation; image; F3 = 1
elif f & 0x800:                               # meadow
    if g != 255: draw; +15 + (e4 & 1), saturation; image
    F5 = 1
if front == back:                             # list full; checked after every tile without 0x10000000
    for each building id 1..last: state 1, +0x40 (workers) != 0, type 51 (timber mill), F0 == 0:
        if route_find_listed_tile(+0x26, +0x28, L, front) != 0: F0 = 1
    front = 0; back = 3999
```
After the loop, if front != 0 or back < 3999, the same timber-mill search runs once more
(it searches only the `front` tree entries; reeds are listed but never searched here).
`route_find_listed_tile` `0x00588B20` is a BFS on the route grid (walkers). Regrowth to 255 takes 51–64
passes for trees, 8 for reeds, 16–17 for meadows. Meadows reset to g = 0 by grazing
(`0x004F8770`, walkers) — see terrain.md §8.5.

## 5b. Marble pits: regrowth on marble tiles (verified 2026-10-28, bugs.md 101)
On a marble tile (0x20000; black 0x120000) the regrowth byte is the **quarry depth**: 255 untouched, 100
shallow pit, 0 deep pit. Only the stonecutter writes it (`figure_miner` 0x004C1310, action 8, after 1632
ticks of work, 1077 with the god-13 sanctuary), on the tile he stands on:
```
g = regrowth[t]
if g == 255: g = 100                                     # untouched -> shallow
elif g == 100 and count(8 neighbours with regrowth <= 100) == 8: g = 0   # 0x0049F120 + 0x004A6CA0
regrowth[t] = g;  marble_images_rect(x-2, y-2, x+2, y+2)  # 0x0049B9E0 -> 0x0049F1B0 per marble tile
```
Marble never regrows (`terrain_regrow` skips 0x20000; the only regrowth writers are terrain_regrow, the
wood cutter and the stonecutter), the 0x20000 flag is never cleared by quarrying, and a deposit is
**never exhausted**: the stonecutter search (production.md "Resource search") keeps finding shallow pits
(4th pass, no neighbour test) and fully-surrounded deep pits; working them leaves them as they are.
So a deposit ends as: untouched rim (edge tiles are never picked, they have a non-marble neighbour),
a ring of shallow pits, and deep pits where 8 neighbours were pits. Ores (0x100002 copper, 0x200002 silver,
0x300000 orichalc) are not changed at all (the miner stands beside the rock; no grid write).
Oracle (working-city, 2,500 ticks, scratch run): two stonecutters worked shallow corner pits (139,114) and
(140,114) for 1632 ticks each; regrowth stayed 100 (3 pit neighbours), as the rule says.
Images: docs/play/terrain.md §2 (marble row) and §3.
Routes (11-02, bugs.md 413): the route grid 0x005876F0 gives a marble tile with regrowth != 0xFF bit 0x80 (its case
comes before the tree / marble open-land case), which only mask 0x19C has (route_search_area 0x0058A4D0, the marble
search; the stonecutters' route mode 0xB): every other land search (0x11D, 0x11C, 0x13C/0x13D, 0x15C) routes around
a pit. Walkers already on a route are not stopped (figure_check_next_tile tests terrain bits, not the route grid).
Ours: walkers.walkable() and monsters.passable() leave pits out, walkers.quarry_walkable() has them (the marble
search tree and the stonecutter's way home); g.quarry holds the depth (255 never stored: a pit never fills again, so
its size versions the caches). Not ported (TODO): route mode 0xB's roads-first search (0x0058A6C0, then 0x19C).

## 6. Meadow value — `meadows_update_rect` `0x004AA190` (editor / map changes, not per tick)
**verified (listing).** For each meadow tile (terrain 0x800) in the rectangle:
```
D = terrain_ring_density(x, y, 4, 0x800)               # 0x004A4900, x87 doubles
    total = 0.0; score = 0.0
    for r = 4 down to 1:
        w = (1.0 / r) * 100.0
        for each tile k of size-1 ring r (offset table) not ring_tile_off_map:
            total += w
            score += w if terrain[tile] & 0x800 else -w
    if score < 0: score = 0
    D = trunc(score / total * 100.0)                   # __ftol
v = trunc(D * 0.11)                                    # image index 0..11 (SPR_MEADOW + v)
meadow[t] = trunc((v + 1) * 0.08333333333333333 * 99.0)  # {8,16,24,33,41,49,57,66,74,82,90,99}
```
Non-meadow tiles in the rectangle get 0. Constants at `0x005D9210` (1.0), `0x005D85B0` (100.0),
`0x005D92E8` (0.11), `0x005D90A0` (1/12), `0x005D85B8` (99.0). Observed save values 8, 90, 66, 82
match. Hypothesis: x87 runs with 53-bit precision (MSVC default) so Python doubles reproduce it.
Consumers of the meadow value (farm yield) are economy's.

## 7. Road networks — `road_networks_update` `0x00491FE0`, cycle step 7 (verified)
```
top10 = [(0,0)]*10 at 0x00FEB0FC (id, size pairs)
wave = 1 (0x0091D888); clear road_network[] and road_step[]; waves_in_wave = 0 (0x0091D884)
net = 1
for y in 0..H-1, x in 0..W-1 (raw index walk with stride fix):
    if (terrain[t] & 0x44) == 0x40 and road_network[t] == 0:
        count = 1 (0x0091D880); road_network_flood(t, net)
        insert (net, count) into top10: first i with count > top10[i].size; shift i..8 down
        net += 1
```
`road_network_flood(t, id)` `0x00492120`: BFS with a ring queue of 1000 (`0x0091D894`):
```
mark(t): road_step[t] = wave & 0xFF; road_network[t] = id & 0xFF
loop: mark(t)                                  # re-marked at the start of every iteration
      for n in t-228, t+1, t+228, t-1:
        R = route_grid[n]
        if (R & 0x10C) and ((R & 8) == 0 or terrain[n] & 0x400) and road_network[n] == 0:
            mark(n); count += 1
            first such n becomes the next t (waves_in_wave += 1); later ones are queued
      if no neighbour found: pop from queue (stop when empty)
      if waves_in_wave > 30: wave += 1; waves_in_wave = 0
      stop after 0xCB10 iterations
```
Network ids are stored as a byte (wrap after 255 networks; id 256 stores 0). The flood follows
the walkers' route grid, not the road bit, so it may enter non-road walkable tiles flagged 0x10C.
Road access then prefers tiles of the best-ranked network in top10 ([buildings.md](buildings.md) §6).

## 8. Can a rectangle be built on? `map_area_buildable` `0x004A0DC0` (verified)
Arguments (x, y, w, h, mask, image, allow_beach, ignore_walkers, strict):
```
if x < 3 or y < 3 or x+w-1 >= W-3 or y+h-1 >= H-3: return 0
inside = outside = False
for each tile (row-major footprint):
    if map_near_play_edge(abs coords, 3): return 0
    u = terrain & (mask | 0x10010000)
    obj = tile_object[t] (0x00666930); if obj and obj[+0x18] == 0: return 0
    if u & 0x10000: (if outside: return 0) inside = True  else: (if inside: return 0) outside = True
    M = 0x3DFFDEEF if strict else (0x3DFED66F if allow_beach else 0x3DFFD66F)
    if u & M: return 0
    for each walker on the tile: if type not in (24, 6): return 0 unless ignore_walkers (then stop scanning)
    if image and ground_image[t] != image-1: return 0
return 1
```
Permitted bits with the full mask: 0x10, 0x80, 0x100, 0x800, 0x2000, 0x2000000, 0x40000000,
0x80000000 (beach 0x10000 only with allow_beach). Note: because `u` includes 0x10000 always,
"all inside or all outside the beach" is enforced even when allow_beach is set.

### 8.1 Vegetation and placement (verified 2026-10-28, bugs.md 83)
- Natural "bushes / grass tufts" are of two kinds. Scrub (0x80 without 0x1; SPR_GRASS / THICK_GRASS
  images): **buildable** for buildings (not in `0x3DFFD66F`), roads (road flood `FUN_0058C3E0` blocks
  `terrain & 0x10060001` = tree, marble, reeds, 0x10000000) and walls (`walls_drag` mask `0x1537166F`).
  Forest-edge trees (0x1; ring 0 of SPR_TREES / SOME_GRASS / LOTS_GRASS, offsets `rand&7` in {0,1,2,7}
  show only grass or a bush, docs/play/terrain.md §2): **trees**, refused by all three tests. Building
  never clears a tree; only clear land (`building_footprint_clear` mask `0x93872F94`) does.
- Bits the generic test refuses that the sim had allowed: marble 0x20000, reeds 0x40000 (refused:
  sim/world.py BLOCKING), rubble 0x1000 and beach 0x10000 (refused since 2026-10-28: BUILD_BLOCKING, area_ok).
  `allow_beach` is set only for tools 28 road, 29 clear, 123 roadblock (`build_tool_allows_beach` 0x00496490), so
  no building stands on beach. Shore buildings (fishing wharf 0x2C, urchin quay 0x2D, dock pier 0x3C: `0x004A10C0`;
  trireme wharf 0x88: `0x004A14B0`) skip this test: their land tiles refuse `0x10004` (water or beach) and `0x5361227`,
  so they can't stand on beach either (production.md "Shore buildings", trade.md "Dock placement"). Rubble must be cleared first: `clear_land_commit` 0x0049A460 clears every tile with
  `terrain & 0x2DFED66F` (rubble, trees, roads, walls…; beach is not in it, so beach stays) with `& 0x93B72F92` and
  counts it (2 dr per tile, col0 of tool 29).
- Roads: the drag (`path`, play mode's road tool) is the exe's `roads_drag_place` 0x0049ACB0, see "Road drag" below:
  rubble and beach are crossed; rubble (and every bit of 0x5361227) refuses a drag END, beach does not.
  `road_set_tile` 0x0049FF10 keeps the rubble bit (it clears only 0x20). Walls (`walls_drag`, mask 0x1537166F) refuse
  rubble and beach. The scripts' `road` (an L, ours) still uses World.free_land.
- `map_area_buildable` has no elevation test (the sim's "ground is not level" was ours; removed 10-29).

## Road drag (`roads_drag_place` 0x0049ACB0; ours sim/roaddrag.py, verified by oracle 1R-roads 11-02)
`build_commit` 0x00498910 tool 28, in this order: treasury < -1999 (message 0x13) and a wolf / boar / deer point
(scenario tables 0x00902BB4 / 0x00902D10 / 0x00902C54, logical) inside the drag's rectangle (`map_area_has_marker`
0x00496B50, message 0x16) refuse WITHOUT restoring the terrain: the preview's road of the last mouse position
(`roads_drag_place(1)`, a failed trace's part too) stays, free (oracle d137/d138: 8 tiles, 0 dr); an enemy soldier,
transport or warship within 12 tiles of either corner (`enemies_near_rect` 0x004DCF60, message 0x21) restores it.
The debt test and the enemies test come first for every tool but 0 and 0x93 (the enemies test not for clear land
0x1D): ours Game.tool_refusal for `build`, `road`, `wall`, `bridge`, `avenue`, `boulevard`, `clear` (11-02, bugs.md
412; was only `path`). A building's rectangle is its tile; hidden invaders count (state 1).
Then `roads_drag_place(0)`; cost = tiles counted by `road_set_tile` x col0; avenue road bits `0x00418BD0` +
`0x004193A0` twice (a road dragged across an avenue's side strip stays where it crosses: N+S / E+W).
1. Each end (start, then end): skipped on a building tile unless type 0x7B roadblock / 0x7E boulevard / 0x76 avenue;
   terrain & 0x5361227 (tree, rock, water, garden 0x20, cliff, rubble, marble, reeds, ore kinds 0x300000,
   0x1000000, deep) refuses (nothing set, no message), except a crossable crack (FUN_0058CAD0) or a ramp 0x400
   (`FUN_00460290` re-stamps the ramp pictures); a wall 0x4000 refuses. So a bridge (road on water) or a road on
   rubble cannot be a drag end; beach can.
2. `FUN_0058C3E0`: breadth-first flood of the WHOLE map from the start (N, E, S, W; ring queue of 0xCB10, never
   full). A tile is entered when: not `map_near_play_edge(x, y, 3)` (0x00496080 with `map_in_play_area` 0x00496010,
   corners from `FUN_00495E90`), route grid & 0x88 clear, terrain & 0x10060001 clear (tree, marble, reeds,
   0x10000000), and either a building tile (8) of type 0x7B / 0x7E / 0x76, or a non-building tile whose route grid
   (pathfinding.md section 2) has no blocked bit 2 (a crossable crack excepted). So 0x400000, 0x800000, 0x8000000,
   0x20000000, orichalc 0x300000 block (route grid 0x2DFFD66F), lava 0x10, fault 0x2000000, 0x8000, scrub,
   meadow, flood plain, beach, rubble, gardens 0x20 do not. Route bit 1 (tile objects 0x00666930 with +0x18 = 0, i.e.
   objects made at map load by `FUN_004176F0` on non-beach tiles beside beach) goes through `FUN_0058CB90`; the N
   neighbour takes the normal tests after it, E/S/W skip them (asymmetry). Ours: no tile objects (see below).
3. `FUN_0058CE40` from the end: each tile is made road BEFORE stepping (counted when it had no 0x40); the step
   tries the four sides in the order of table 0x006432AC by `direction_to` 0x0058CFF0 (cur -> start: N E W S /
   E S N W / S W E N / W N S E) and takes the first with 0 < distance < this one's (and not an uncrossable crack).
   It stops with failure, KEEPING the tiles set so far, at: distance < 1 (unless type 0x7B or 0xA4), a garden
   tile 0x20 (the flood crosses gardens, the trace does not: the road from the end up to the garden is built and
   charged; oracle d118..d121), an uncrossable crack, and after 399 tiles (a route of 400+ tiles builds its 399
   tiles from the end and charges them; 399 is the longest whole route: oracle d148..d151).
4. On success the pictures of the rectangle are redrawn (the preview shows the road pictures, ramp roads as built:
   oracle slope-road d1..d3c vs built.bmp, bugs.md 464; 1R-roads' shots show no route, its camera poked every tick);
   a failed trace's tiles are in the terrain but not redrawn: the ghost shows no route, only the cursor tile (red in
   the shots). Each call first restores the terrain, route, piece and draw grids (FUN_00413AF0 from the backups taken
   at the press) and the pictures of non-building tiles (FUN_004A7560).
5. The cursor tile, every frame (FUN_00451820 -> FUN_00452B80, on the terrain with the preview's road): green = the
   road picture SPR_ROADS (SPR_PAVED_ROADS when piece & 0x80; + 1 with a road E or W but none N or S) under the AND
   mask 0x1FE3, when terrain & 0x2DFED66F == 0 (a crossable crack: its crack-road picture), not within 3 of the play
   edge and the treasury >= -2000; else the red SPR_BUILD_CURSOR diamond (a road, a ramp, a placed drag end).
   Ours: sim/roaddrag.py cursor, sim/live.py footprint (key road), play mode build.js roadCursor (a crossable crack:
   the green diamond, its crack-road picture not ported).
Crack (`FUN_0058CAD0`): rock 2 with piece 0x80 whose crack picture (T_CRACKS 0x00636BE0 group 6, by view) is a
straight piece or an end: indices 0..3 / 16..19 need no road N and S of it, 4..7 / 20..23 none W and E (swapped in
views 2 and 6); other pictures never. Ours: Game._road_cracks (picture from tools/terrain_images.py; not on the
oracle: no earthquake in 1R-roads).
Not in ours: tile objects (route bit 1). In play they sit on water / land tiles beside beach and decide by their
ground picture (beach group, `FUN_0058CB90` 6/8/10/12) whether a road may cross there; ours has no object grid nor
those pictures (docs/play/terrain.md section 7). In 1R-roads a poked lane over the sandbox's central beach got no
route because of them; the oracle scene was moved off it. Open: TODO.md.

## 9. Editor-only terrain tools (`editor_paint` 0x0049DA10)
Brush sizes from `0x00665E28`; after painting it recomputes tree depth (`0x004A8E10`, ±12) and
meadow values (`meadows_update_rect`, ±9) when bits 0x80 / 0x800 changed. Tools and bit writes
are in section 3 and `re/names/map-buildings.tsv`. Not part of the simulation tick.

## Herd, predator and fishing points (scenario block, rank 14)

Stored in the scenario block (rank 14, 2032 bytes) of the map file. The block is the memory image of the
editor/scenario struct at `0x902928`: exe address = `0x902928 + block offset`. Slots are parallel arrays
`x[N]` then `y[N]` (not records); an empty slot is x = -1 (editor clear routines `0x405bc0..0x405cd0`).
Decoder: `tools/mapfile.py points FILE` (`herd_points`, `fishing_points`, `urchin_points`, `scenario_points`).

| Table | Tool id (text group 28) | Block off | Slots | Elem | y at | Used by |
|---|---|---|---|---|---|---|
| wolf spawn (killer point) | 187 (0xBB) | 0x28C (0x902BB4) | 4 | i16 | x+8 B | herd, figure type 59 (wolf) |
| fishing point | 186 (0xBA) | 0x29C (0x902BC4) | 8 | i16 | x+16 B | fishing boats |
| urchin point | 189 (0xBD) | 0x2BC (0x902BE4) | 8 | i16 | x+16 B | urchin quay (hypothesis: slot count/type from editor text "Urchin point 1..7"; confirmed on Open Play Economic, 7 points on the shore) |
| monster point (lair) | 197 (0xC5)? | 0x4E0 (0x902E08) | 3 | i32 | x+12 B | lairs of monster slots 0..2 (`monster_spawn` 0x0052EEF0, heroes-monsters.md; verified: the oracle's Maenads, slot 2, spawn at sandbox (121, 200) = slot 2; earlier read as "native hut/center/field" from editor text); `sim/world.py` `monster_points` |
| boar spawn (prey point) | 190 (0xBE) | 0x3E8 (0x902D10) | 4 | i32 | x+16 B | herd, figure type 51 (boar) |
| deer point | 210 (0xD2) | 0x32C (0x902C54) | 4 | i16 | x+8 B | spawns type 51 (boar) too; all zero in the sandbox |

Editor labels (text group 48): "Boar spawn 1-4", "Wolf spawn 1-4", "Fishing point 1-8", "Urchin point 1-7".
Tool id to table: switch in the editor coordinate lookup (decompile around line 2100, `case 0xBA/0xBB/0xBD/0xBE/0xD2`)
and the placement code (lines ~3230-3320). Clear routines: `0x405bf0` (wolf), `0x405c20` (fishing/urchin
region), `0x405bc0` (boar).

Spawning: `FUN_004E0160` (3100 B, only when `editor_mode == 0`, i.e. at map load/start). For each slot with
x > 0 it allocates a formation (`formation_alloc_other`) at the point and creates 7 animals (count constants
`DAT_00641FA8/F78/FCC/F9C` = 7 in the exe data) near it: tries the 16 ring offsets `DAT_005F2418/5F2518`
(x,y pairs) until the tile is passable (`FUN_00569D90`), `figure_create(1, type, x+dx, y+dy, rng&7, 1)`.
Loop 1: wolf table, type `DAT_00641FA0` = 59. Loop 2: boar table, type `DAT_00641F70` = 51 (boar).
Loop 3: deer table, also type 51. A slot with x <= 0 is skipped (zeroed deer table = none). Slots are
indexed 0..3 so at most 4 boar herds (28 boar), 4 wolf packs and 4 deer-point herds exist on any map.

Sandbox (`}Open Play Sandbox.pak`; both embedded maps identical), (x, y):
- boar herds (4): (105,18) (120,28) (16,99) (69,175)
- wolf packs (3): (115,14) (16,121) (48,156)
- fishing points (6): (102,104) (70,101) (88,98) (98,128) (115,125) (88,109)
- urchin: none. deer: none. monster points (lairs; first read as "native"): (116,10) (113,143) (121,200)
(all logical: on our raw grid + (1, 1), next section)

Plausibility (rank 6 flags): every fishing point is deep water (0x4000004); all wolf points and 3 of 4
boar points are on a tree tile (0x1/0x81) with 86-181 tree tiles in the 17x17 area; boar (120,28) is on a
rock/other tile (0x80) with 86 trees around. The native points are mixed terrain (rock, water, tree), so
that identification is unsure.

`Open Play Sandbox 2P.map` (other map in the sandbox 2 folder) has 4 boar points (172,81) (182,80)
(87,139) (73,45), no wolves or fishing points. Open Play Economic pak: containers differ (urchin 7 points
in two of them, 1 wolf in one).

Confidence: layout and the boar/wolf/fishing decoding high (spawn code read, terrain matches). Urchin
table identity medium-high. Not decoded: whether a wolf/boar point count in the file can exceed the slots
(no: fixed arrays); the third loop's relation to "deer" (the game has no deer figure; hypothesis: legacy).

### Logical and raw coordinates (track 1J, 10-29)
Every point of the scenario block is a **logical** map coordinate, as are figure and building x/y in the exe: the
grids are indexed `0x00DA2F80 + 228 y + x` (base = scenario block +0x34; play area W, H = +0x2C / +0x30). The
sandbox maps have base 229 (logical (0, 0) = grid (1, 1), W = H = 226); the tutorial-size maps 44 * 229 (origin
(44, 44)). Our grids are raw (the file's rank-6 index y * 228 + x), so raw = logical + origin.
Exe evidence, per table (tools/mapfile.py `_POINT_TABLES`, all 16 tables of the editor's marker switch
FUN_004040D0, which draws each marker at grid index `0x00DA2F80 + y * 0xE4 + x`):
- entry / exit / sea entry / sea exit: spawn_immigrant 0x00486C50 `figure_create(1, 1, g_map_entry_x, y)`;
  figure_create sets the tile to `0x00DA2F80 + y * 0xE4 + x`; building_water_access_check 0x00485670 floods
  from g_sea_entry with the same index (FUN_0058D500). Oracle: immigrants (type 1) appear on the sandbox's logical
  entry (166, 169) (gate-walk tick 400; the hero in 1I-hero tick 2448), land traders (0x13, 0x15) on the
  working city's logical entry (65, 133), its ships (0x14) on the logical sea entry (77, 130), traders leave
  at the logical exit (129, 61) (sanctuary-build); never at +-1.
- wolf / boar / deer herds: FUN_004E0160 tests `g_grid_terrain[x + 0x00DA2F80 + (y + dy) * 0xE4 + dx]`. Oracle
  open-play-events tick 0: all 28 boar and 21 wolves on the 16-offset ring of the logical points; ours since 1J:
  the same 49 tiles (+ (1, 1)); before, 20 boar and 12 wolves were on other tiles (tests/test_terrain.py
  test_scenario_points_raw). Read raw, 3 of 4 boar points and every wolf point are tree tiles; read logical,
  all are open land.
- fishing / urchin: FUN_00412B60 / FUN_00412C60 -> figure_create; oracle: the 6 effect figures (type 6) stand
  exactly on the 6 logical fishing points.
- monster points: heroes-monsters.md "Logical vs raw coordinates" (the Maenads' route, 1I).
- land / sea invasion points, landing points: enemy_army_spawn_land 0x00504650 indexes `0x00DA2F80 + y * 0xE4 + x`
  and takes the facing from logical y == 0 / y >= H-1 / x == 0 / x >= W-1 (ours: invaders.facing_of). No oracle
  run with an invasion yet.
- earthquake (+0x388), disaster points (+0x394), landslide points (+0x624): editor markers only; not used by ours.
Ours: sim/world.py converts every table once at load (`scenario_points`, `World.points`, `World.entry` ...,
`World.origin`, `World.size`); nothing else reads the scenario block's points. Worlds pickled before that
(`World.points_v` < 1) are migrated in Game.load (`world.migrate_points`: the points from the map file, and the
herd timers, wolf packs and animal origins keyed by the old points moved). Oracle tools print logical positions
(tools/oracle_heroes.py, oracle_military.py: add World.origin to compare with ours); oracle_moorings.py and
e1_ramp_check.py read the dump's own grid with the offset of its building tile field.

## 10. Map reset (`map_grids_reset` 0x00496120)
Clears the main grids, sets regrowth to 255 everywhere, marks off-diamond tiles 0x80005, fills the
random grid (51,984 RNG draws), then `0x0049B950`. **verified.**

## 11. Start state of a new game (track 1K, 10-30, bugs.md 233)
A new open-play game loads the map's blocks (`FUN_0042B230` -> `FUN_0050DF50`, table `0x0063CDC0`: map rank 6 is
the terrain grid `0x00CCE128`, 5 the draw grid, 7 the piece grid, 8 the random grid, 9 `0x00C8E9D8`, 15 the meadow
grid, 19 regrowth, 22 scrub, 23 elevation, 24 projected elevation; the building grid is not in a map) and then runs
`FUN_0051D2B0`: play-area tables (`FUN_00495E90`), invasion points off the play area cleared, fishing/urchin figures
(`FUN_004E0D80`), herds (`FUN_004E0160`), `city_init_from_map` 0x00511E30, `FUN_0051D760` (building grid ids
without a building zeroed; `FUN_00521520(3)`), the scroll limits, `route_grid_rebuild` ...
- **Roads are map data.** Terrain bit 0x40 is stored in the map's terrain grid and kept: the sandbox has 119 road
  tiles (raw x = 167, y 106..173, and y = 106, x 168..218: from the land entry (167, 170) to the exit (217, 106));
  sandbox 2 has 31 (pieces, 5 of them on cliff ramps 0x800640). No code lays a road on a new game. They are ordinary
  roads (the clear tool removes them).
- **Cliff clean-up.** `FUN_00521520(3)` (mode bit 1) calls `map_elevation_project` 0x0045ED20, which also fixes
  flags over the play area: off cliffs it clears ramp 0x400 and 0x800000; on cliffs (0x200) it clears meadow 0x800,
  scrub 0x80 and tree 0x1. On the sandbox this removes the tree bit of 12 cliff tiles (126..131, 179..186 and
  (126, 207)).
- **Oracle check** (re/oracle/runs/open-play-events and 1H-god, tick 0, against the map file): terrain = the map's
  grid with those 12 tree bits cleared (applying the rule to the map gives the dump exactly, 0 tiles differ); the
  draw, piece, random, 0x00C8E9D8, meadow, regrowth (all 255), scrub, elevation and projected-elevation grids are
  byte-equal to the map's; building, desirability, wall-damage, ruin, bridge (0x00CB4B08), 0x00CC1618,
  0x00B90C98, 0x00B84188 and 0x00B1E8F8 grids are all zero. Only the figure grid (sav 19) has content: figure ids on
  51 tiles, the start figures (herds, fishing spots; 1J's comparison).
- Ours: `sim/world.py` `start_terrain` (the cliff clean-up) and `World.road` from bit 0x40 at load, then
  `Game.__init__` labels the road networks (`systems.roads.rebuild`). The 0x40 bits stay in `World.flags` (the
  exe's grid); `World.road` is what the sim and play mode read (sim/terrain_view.py masks stale 0x40 bits).
  Old saves are not changed: worlds pickled before 1K have no map road (the user's a save has a city
  built over its line); a player can lay it with the road tool.

## Cross-references
- RNG ownership: time-core. Route grid `0x0105FE40`, route distance `0x01079460`, BFS
  `0x005883E0`/`0x0058D500`/`0x00588B20`: walkers.
- Grazing `0x004F8770`, farms/miners use of meadow/rock bits: economy (`0x0048CFB0`).
- Terrain events (lava, earthquake, flood) `terrain_events_update` 0x00446A70, `0x00506330`,
  `0x00506D80`: disasters (unassigned; noted for the coordinator).
- `multi_tile_buildings_update` and buildings: [buildings.md](buildings.md).

## Open questions
- Scale of `0x004A8C90`/`0x004A8E10` (tree depth) and of the scrub tool value (`__ftol` paths).
- Exact meaning of 0x8000, 0x1000000, 0x80000000, `0x00CC1618`, `0x00C8E9D8`, `0x00B1E8F8`.
- Where the map ranks 18–32 (elevation etc.) are filled for GOG maps (terrain.md open item).
- x87 precision-control state during `0x004A4900` (53 vs 64 bit) — confirm by a save diff.
