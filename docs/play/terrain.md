# Terrain images in play: how Zeus picks them and how they change (2026-10-27)

Source of truth: `Zeus.exe` (GOG 2.1) decompile, checked against the map files. Implementation:
`tools/terrain_images.py` (`images`, `images_full`, `expand_rect`, `animate_water`; self-check:
`python3 tools/terrain_images.py`). Result: **99.85 %** of the sandbox's own rank-4 grid (25,338 non-cliff
tiles), **~98.5 %** over all v321 campaign maps. The remaining misses are explained below.

## 0. Image id convention: the renderer is off by one (important)
`id = collection*0x4000 + n`, collection 3 -> 5 for v247 maps. **n is 0-based**: `n = 0` is `SPR_SPACE`, the
first image after the 200 system images. In `atlas.json`, `images[i]['index']` is 1-based, so
**atlas `index` = n + 201** (list position n + 200). `groups[].first` is also an `index`: group first n =
`first - 201`.

Evidence: every rule below only matches the map with this convention (grass image = `scrub/8 - 1` under the
old convention but exactly `int(scrub/8)` under the new one; trees `first + 8*ring + rand%8` land exactly on
group boundaries; flag-0x1 tiles get SPR_TREES, not the last 8 SPR_LAVA frames). The 211 tiles with id 50130
(n = 978) are **tree tiles** (flags 0x1 / 0x81) and their image is `SPR_TREES[0]` (atlas index 1179, a forest
floor tile with trees, 58x62), not the tiny SPR_LAVA frame 1178. Nothing is remapped, skipped or chosen at load
time; the +2 collection mapping for v247 is right. Fix: use index n + 201.

## 1. Who computes images, and when
`map_tiles_update_images` `0x0051F450(x0, y0, x1, y1, mode)`:
1. mode bit 1: `map_elevation_project` `0x0045ED20`; bit 2: grow the rect with `0x0051F210` (see 4); bit 4: `0x004A8FF0`.
2. Pass 1 (tiles inside the play diamond with `flags & 0x8C008 == 0`; 0x8C008 = off-map | 0x8000 | wall 0x4000 |
   building 0x8): clear the image to 0 (unless cliff 0x200) and compute cliff pieces (`0x0051FEC0`).
3. Pass 2, row-major (y outer, x inner), per tile with image still 0 (multi-tile stamps fill later tiles first!):
   cliff piece (`0x005200B0`) -> water (`0x00520CA0`) -> tree (flag 1: `terrain_resource_image` `0x004A81F0`) ->
   rock/ore (`0x00520580`) -> marble (`0x00520920`) -> 0x1000000 (`0x00520820`) -> rubble (`0x005214B0`) ->
   road (flag 0x40: `0x004A0190`) else beach (`0x00520B80`) -> marsh (`0x00521150`) -> garden 0x20 (`0x00521200`)
   -> meadow (`0x00521460`) -> scrub grass (`0x0051F860`) -> plain ground (`0x0051FBA0`).
Callers: map load, editor, `building_footprint_to_rubble` `0x004A07C0`, `building_footprint_clear` `0x004A09F0`
(footprint rect +1 right/bottom, mode 2), woodcutter (`terrain_resource_image` on one tile), `terrain_regrow`
`0x004A7D30`, road placement.

Grids used (map ranks): flags 6, random 8 (`rand`), piece 7 (bit 0x20 = IN_FILL2 land, 0x80 = rock "cracks",
low nibble size-1), **scrub 22** (value 8*ring depth, only meaningful with flag 0x80), **meadow 15** (8..99),
**regrowth 19** (255 = grown), elevation 23, desirability (not in the map; sim has it). Sandbox: regrowth is 255
everywhere. Terrain image never depends on elevation except cliffs (4).

Image selection by pattern table (`FUN_004A6920` 0x004A6920): 8 neighbours N NE E SE S SW W NW (offsets -228,
-227, +1, +229, +228, +227, -1, -229) give booleans `arr[i]`; a 20-byte record (8 pattern bytes: 1 = arr true,
0 = arr false, 2 = ignore; 4 group-index bytes, one per view orientation; flags; variant count) matches when all
pattern bytes agree; first matching record wins (deep water: last). Result: `k = record.index[orient/2]`,
`variant = rand % count`. We use orientation 0 (the game's default north view). Tables are embedded in
`tools/terrain_images.py` (`T_WATER` 0x00634C00 x48, `T_EDGE` 0x00636D38 x26, `T_CRACKS` 0x00636BE0 x17,
`T_MARBLE` 0x006375B0 x32, `T_ROAD_A` 0x006371F0 x48, `T_ROAD_B` 0x00637098 x17).

## 2. Rules per class (group ids = atlas `groups[].id`; image = group first + offset)
| Flags | Group (id) | Offset |
|---|---|---|
| plain land (`flags & 0x2CFED66F == 0`, e.g. 0x0, 0x10, 0x100) | SPR_IN_FILL1 (10), or SPR_IN_FILL2 (7) if piece & 0x20 | see "plain" below |
| scrub 0x80 (no 0x10801), g = `int(min(scrub,100)/8)` | SPR_GRASS (36) | g if g < 11 |
| same, g >= 11 | SPR_THICK_GRASS (16) if any neighbour has flags & 0x2DFED66F (unless tile has 0x10000000); else SPR_THICK_GRASS_NOHAT (15) when all 8 neighbours also have g == 11, no 0x10801 and clean surroundings, else SPR_THICK_GRASS_RIM (38) | 0 |
| scrub with a beach neighbour | SPR_BEACH (18) | `T_EDGE` index + 6 |
| tree 0x1 (and `flags & 0xC064 == 0`), grown (regrowth 255), lvl = `min(scrub,100)//34` | SPR_TREES (4) for lvl 0, then the next two groups SOME_GRASS (30), LOTS_GRASS (29) (contiguous in the atlas) | `lvl*32 + ring*8 + rand&7`; ring = largest r in 0..3 such that the Chebyshev ring r around the tile holds only trees or rock (0x300002) (tiles outside the array count as ok; off-diamond tiles are normal tiles) |
| tree, regrowth != 255 (just cut / regrowing) | SPR_STUMPS (12) / STUMPS_SOME_GRASS (14) / STUMPS_LOTS_GRASS (25) for lvl 0 / 1 / 2 | `rand & 7` |
| meadow 0x800 | e1 = `int((meadow-1)/99*regrowth/85)`, e2 = `int((min(scrub,100)-1)/96*12)`: (e1=0,e2=0) SPR_MEADOW_LIGHT_GRASS (28); (e1=2,e2=0) MEADOW_DESERT (19); (e1=2,e2=11) MEADOW_GRASSY (9) -> `rand&7`; else SPR_MEADOW (37) | `e2 + 12*e1` |
| water 0x4, from `T_WATER` with arr = neighbour NOT water (k, var) | SPR_BEACH_COAST (35) if the tile or any neighbour is beach 0x10000 (tile beach: only when k >= 8), or if k == 0 (all-water interior); else SPR_WATER (5) | `var + k` |
| deep 0x4000004, arr = neighbour NOT deep, `T_EDGE` searched from the end | SPR_WATER_ANIMS (20) | `15*var + k` (6 phases x 15 shapes) |
| beach 0x10000 on land (no 0x48) | SPR_BEACH (18) | `rand % 6` |
| marsh 0x40000: `T_WATER` on neighbour-not-marsh; if all 8 neighbours marsh: grown SPR_REED_GROWN (27), else SPR_MARSH (26) | | `var + k`, or `rand&7` |
| rock 0x2: plain IMPASSABLE (8); 0x100002 COPPER (40); 0x200002 SILVER (32); 0x300002 ROCK_CLIFF (22) | 14 images: 3x3 block if all 9 tiles have the same kind and no image yet: `12 + rand&1`; else 2x2: `8 + rand&3`; else `rand&7`. One image id for the whole block, drawn at the anchor (bottom-left tile) |
| rock with piece bit 0x80, or earthquake fault 0x2000000 | SPR_CRACKS (6) | `T_CRACKS` k + var |
| marble 0x20000 (0x120000 black) | SPR_QUARRY (205) by `T_MARBLE`; if that k = 0 (interior) and regrowth != 255 (quarried, map-terrain.md 5b): SPR_QUARRY_SHALLOW (204) by `T_PIT` 0x00637830 on "neighbour regrowth > 100"; if regrowth < 100 and that k = 0 too: SPR_QUARRY_DEEP (203) by `T_PIT` on "neighbour regrowth > 0". Black: Poseidon_Loaded SPR_BM_QUARRY / BM_SHALLOW / BM_QUARRY_DEEP (collection 52). (The sandbox file has editor pits: editor_mode uses 2x2/3x3 block tests instead.) | k + var |
| rubble 0x1000 | SPR_RUBBLE (21), 8 images | `rand & 7` |
| road 0x40 (not beach) | tier from desirability d: d < 0 SPR_RUTTED_ROAD (43, `T_ROAD_A`); 0..15 SPR_ROADS (33, `T_ROAD_B`); 16..29 SPR_PAVED_ROADS (39, `T_ROAD_A`); >= 30 a Zeus_General group (47, not ported). arr = neighbour has 0x8000040 | k |
| cliffs 0x200, ramps 0x400, lava 0x1000000, garden 0x20, orichalc 0x300000 | not computed: keep the stored image / not ported | |
| 0x10000000 (monument extras, special tiles) | ground as any tile unless the step rule 0x00546380 gives a step image: then the step picture is the tile's image and no ground is drawn (FUN_00521520 writes it, map_tiles_update_images 0x0051F450 skips the tile); ours the same since 11-02 (scene.js stepGround, bugs.md 400) | |

**Plain land** (`map_tile_plain_ground` `0x0051FBA0`) is a sequential stamp. Group G = IN_FILL2 if piece&0x20
else IN_FILL1 (58 images each: 1x1 x8 at 0, 2x2 4 variants x4 at 8, 3x3 2 x9 at 24, 4x4 x16 at 42; each tile of
a block gets its own consecutive slice image, all tiles drawn). If `rand & 0xF0 != 0` (15/16 of tiles): 1x1 with
`rand & 7`. Otherwise try a 4x4 block at this tile (all tiles `flags & 0x3DFFDEEF == 0`, image still 0, not
within 3 of the play-diamond edge) -> offset 42; else 3x3 -> `24 + 9*(rand&1)`; else 2x2 -> `8 + 4*(rand&3)`; else
1x1. Because tiles are visited in row-major order and later tiles of a stamp are skipped, **the result depends on
visit order**: compute the whole map (or a rect expanded with `expand_rect`) in one pass, never tile by tile.

## 3. What changes during play (answers to Q1, Q5)
* **Woodcutter**: trees are never removed. After 0x198 (408) ticks of work, `figure_wood_cutter` sets
  `regrowth[t] = 0` and calls `terrain_resource_image(t)`: the tile becomes a **stump**: STUMPS group by scrub
  level, index `rand&7`. `terrain_regrow` (docs/logic/map-terrain.md 5) raises regrowth each pass and re-calls
  `terrain_resource_image`; the stump image does not change while growing; at 255 the tile becomes a grown tree again
  (ring/level rule above). Flag 0x1 never changes.
* **Clear/demolish without rubble** (`building_footprint_clear`): tile flags `& 0x93872F94` (clears tree 0x1,
  rock, building, road, garden; keeps scrub 0x80, meadow 0x800, beach, marsh, cliff...), image set to IN_FILL1 `rand&7`,
  then the rect (footprint, +1 right/bottom, grown by `expand_rect`) is recomputed. So a cleared tree tile 0x81
  becomes grass (`SPR_GRASS[int(scrub/8)]`, thick/rim variants for scrub >= 88), 0x1 becomes plain land
  (IN_FILL, blocks possible), a meadow stays meadow (new `e1,e2`), beach stays beach, etc.
* **Building destroyed (fire/collapse)** `building_footprint_to_rubble`: per footprint tile that is not water:
  `flags = flags & 0x93873F90 | 0x1000`, image `SPR_RUBBLE[rand&7]`, draw 0x40, piece &= 0xE0, `ruin_type`
  recorded; water tiles just lose the building bits. Then the rect is recomputed (rubble tiles keep rubble). Rubble
  stays until something clears the tile: building placement / clear land use masks without 0x1000 and reassign the image.
  (No timed decay was found.)
* **Building placed**: tiles get 0x8; they are skipped by the image pass (building sprites draw them); on the
  footprint's removal the tile reverts as above.
* **Road placed**: tile flag 0x40 (clears 0x20 garden); image from the road table (tier by desirability, so
  roads can change appearance when desirability changes). Recompute footprint +1 ring: neighbours' patterns change.
* **Regrowth of meadow** (grazing resets regrowth to 0): `e1` uses regrowth/85, so a grazed meadow shows
  a lower-grass image (e1 0..3) while it recovers (16-17 regrow passes). Ported 10-29 (bugs.md 210): a tile a grazer
  leaves gets regrowth 0 (sim `g.grass_bare` day), + 15 + a bit per day (terrain_regrow 0x004A7D30; ours a stable
  bit per tile and day, not the exe's RNG), 255 on overflow (sim/systems/walkers.py `meadow_regrowth`); terrain_view
  feeds it to the meadow rule; `meadow_day` (daily) bumps map_version when a tile's e1 changes.
  10-30 (1F, oracle 1F-meadow2 = re/oracle/scenarios/meadow-regrowth.txt with dumps 1975..1978, `python3
  tools/meadow_check.py`): every grazed meadow tile on the shot with a regrowth-dependent picture matches ours (4 of
  4: regrowth 138 / 15 / 155 at 0.93..1.0 against 0.0..0.1 for the grown picture), and 50 of the 53 meadow tiles on
  screen score >= 0.5 at the rule (30 >= 0.9; the rest under sheep / trees). Found: figure_graze 0x004F8770 sets the
  byte to 0 without terrain_resource_image, so an eaten tile keeps its old picture until the next daily regrow
  (tile (129, 124) at regrowth 0 shows the grown meadow, 0.98); ours now too (walkers.picture_regrowth: the picture
  held from the eating day, g.grass_held; bugs.md 269).
* **Road on a ramp** (ported 10-29, bugs.md 211): the cliff matcher FUN_0045E110 gives a ramp tile (0x400) with road
  0x40 its road picture: code + 8 (SPR_E1_xROAD2 / EH_xROAD2) when FUN_004A0480 (not beach, desirability > 4), else
  + 4 (E1_xROAD1 / EH_xROAD1); the long ramp's partner tile image + 1; 0x00460290 re-stamps on road drag / clear.
  sim/terrain_view.py `ramp_roads`: the cliff tiles around a ramp road (or one that had one) take
  tools/terrain_cliffs.py's answer in every view. Checked on the baseline save: (131,178) EH_NPASS1 1234 -> EH_NROAD1
  1242, partner 1235 -> 1243; views 2/4/6 the turned ROAD1 pictures; back to 1234/1235 without the road.
  It runs (the whole map, 4 views, ~0.6 s) only when the ramp-road set changed, a ramp road's desirability crossed
  > 4, or a changed tile lies within 4 of one (11-03, bugs.md 442: every terrain update ran it, and the daily meadow
  regrowth redraw held the live server's lock long enough to stop every tab's walkers; the result is the same as a
  fresh TerrainView).
* **Quarrying marble**: after each block (1632 ticks) the stonecutter's tile goes 255 -> 100 (shallow) -> 0 (deep,
  only when all 8 neighbours are pits) and the marble images of the 5x5 around him are recomputed (`0x0049B9E0`).
  Ported 2026-10-28 (bugs.md 101): sim `g.quarry`, `terrain_images.marble` with `T_PIT`; checked on the working
  city's 6x6 deposit (36/36 ids with the oracle's regrowth).

## 4. Recomputing a region
`images(flags, elev, rand, orig_ids=..., rect=expand_rect(flags, (x0, y0, x1, y1)), scrub=, meadow=, regrowth=,
piece=, desirability=)`: tiles inside rect are cleared and recomputed in row-major order, everything else
(and cliffs) keeps `orig_ids`. `expand_rect` is the game's `FUN_0051F210`. Recomputing rects reproduces the stored
grid for 93 % of tiles; the rest differ only in plain-land stamp alignment (blocks cut at the rect), which the
original shows too. Simplest renderer strategy: keep the id grid in a typed array, recompute the rect on every
terrain-flag change (tree/stump/rubble/clear/road/building footprints) and re-upload the changed tiles; recompute
the whole map only on load.

## 5. Water animation (Q3)
`ground_tile_draw` `0x00457900` (called for each visible tile). Every time more than 60 ms of `timeGetTime`
have passed since the last step (checked once per displayed frame, so ~15 steps/s at 30 fps; exact cadence
depends on the frame rate, uncertain) the flag `DAT_007D3B1C` is set for that frame; for tiles with flag 0x4,
draw bit 0x40 and piece low nibble 0 (single-tile images), **the grid image itself is advanced**:
* shallow (no 0x4000000): if image is in SPR_BEACH_COAST[0..5] (all-water interior tiles): +1, wrap after 6;
* deep (0x4000004): if image is in SPR_WATER_ANIMS[0..89]: +15, wrap after 90 (the 6 phases of each of the 15 shapes).
Edge tiles of shallow water (SPR_WATER) and tiles with a beach neighbour do not animate. Only tiles drawn that frame
advance (ground_tile_draw runs for visible tiles); play mode advances all (play.js drawWater). Initial phase is
`rand % 6`, so neighbours are out of phase. `animate_water(ids, flags, draw)` does one step.
Oracle check (10-29, bugs.md 170; re/oracle/scenarios/water.txt, new sandbox, 40 shots 50 ms apart): the exe
changes the deep water (every SPR_WATER_ANIMS tile; all 113 changing tiles of the shot are in play mode's WATER
list) about every 117 ms in the headless run (6 steps a 0.7 s cycle; its frame pacing, the rule is > 60 ms), and
the change is faint: per step 44 % of the animated pixels change, by 1.5 levels per channel on average (p90 2.7).
Play mode at dpr 1.25: 38 % change by 1.2 on average, a step every ~67 ms at 60 fps. So it is as the original:
a shimmer, not a visible wave. The visible life on the water is the fishing spots (walkers.md "Water life").

## 6. SPR_SPACE, "editor markers" (Q4), tiles not to draw
There are **no editor-marker images in the sandbox grid**: no tile has n = 0 (SPR_SPACE). The black diamonds with
symbols seen in the browser are most likely the same off-by-one (hypothesis: not checked pixel by pixel). Genuine
SPR_SPACE: `0x0051FEC0` gives n = 0 to non-cliff tiles lower than a neighbour (hidden behind a plateau), and flags
them 0x200 (the arm64 notes cite `0x0047CCE4` for the same black tiles; not read). In the sandbox the cliff tiles have their real cliff images.
Skip rule for the renderer: draw only tiles with draw bit 0x40 and image id != 0 (350 sandbox tiles have bit 0x40 and
id 0: these are the 0x80005 / 0x80080 off-diamond tiles). Herd/fishing points are scenario data (rank 14), not terrain.
Editor-only: ground_tile_draw tints tiles flagged 0x10 / 0x100 / 0x80000000 in editor mode (0xF863 etc.); piece bit
0x10 draws SPR_PRE_BUILD (13) instead of the stored image (construction-site ground).

## 7. Uncertainties / not ported
* Orientation: stored maps mix pieces computed under different view orientations (edits recompute only a rect with the
  current orientation). Most mismatches in campaign maps are tiles whose pattern index is column 3 of the same record.
* Beach/water tiles with "tile objects" (pointer grids 0x00666930; quays/bridges?) use SPR_BEACH_ROAD-like frames
  (`0x00520CA0` local_8 branch): not ported (2 sandbox tiles, flags 0x84).
* Marble pits drawn by the editor rule (sandbox file); earthquake fault variant counter (`FUN_004A6920` with rand -1 uses a
  per-record running counter, so variants are history dependent); roads on beaches; tier 3 roads.
* Gardens (0x20, `0x00521200`: row-major on unset tiles; 3x3 block -> image 7, else 2x2 (rand&3 0/1 -> 6, 2 -> 5, 3 -> 4), else 1x1 `(x&1) + 2(y&1)`; play mode: scene.js gardenStamps), lava/damage tiles (0x1000000) keep the stored image; 0x10000000 tiles get ground unless the step rule `0x00545940` applies (then only the step picture; ours too since 11-02, bugs.md 400). Gardens of an original .sav become our 1x1 gardens buildings (savimport `_gardens`).
* Scrub > 100 (not seen); stump rule is from the code only (no map has regrowth < 255).
* Cliff/elevation images are not computed (static in play): `0x0051FEC0` + `0x0045E070..`.
* Check numbers: sandbox 99.85 % (misses: 36 marble pit tiles saved by the editor, 2 beach-object water tiles);
  draw bit 0x40 matches 100 %; v321 campaign maps ~98.5 % (misses: orientation patchwork, marble pits, faults, 0x40 roads
  of higher desirability tiers).
