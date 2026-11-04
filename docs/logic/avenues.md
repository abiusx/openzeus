# Avenues and boulevards

Status: read from the exe (GOG `Zeus.exe`) unless marked. Evidence: **exe** = decompile/disassembly
(address given), **seen** = our play mode with the original's sprites, **hyp** = our guess.
Port: `sim/systems/avenues.py`; pictures: `sim/live.py avenue_images` -> `viewer/play/scene.js`.

## Model (exe)
- One drag-builder object per type, with a vtable: boulevard at `0x0069D980` (vtable `0x005D85C0`), avenue at
  `0x0069D968` (vtable `0x005D85E4`); fields +4 building id, +8 type (0x7E / 0x76), +0xC segment count,
  +0x10 orientation. Constructors `0x00418910` / `0x00418950`.
- **One building record per type for the whole map**, created at (0,0) on the first segment
  (`0x00418B40` -> `building_create(type,0,0,0,0)`), found again on load by `0x00418B90`, freed when the
  count drops to 0 (`0x0041A490` -> `0x00418B70`). Every avenue tile's `building_grid` points at it
  (`0x00418BD0` rebinds). The record's own desirability spreads around (0,0): see desirability.md quirk.
- Per tile: terrain bit 8 (building); the road tile also 0x40 (road). Draw byte: low 3 bits = position
  1..3 across an x-oriented segment, bits 3..5 = position across a y-oriented one, 0x80 = side strip.
  Pictures go into the ground image grid `0x00D4CFC8` (not a building picture).

## Placement (exe)
`build_commit` `0x00498910`: tool 0x7E -> `0x0041B250`, tool 0x76 -> `0x00419F90`; cost = segments x model
cost col 0 (avenue 20, boulevard 30 at Normal); then `0x00418BD0` + `0x004193A0` (road bits + pictures).
- A **segment** is a cross-section of a road: avenue = the road tile + 1 side strip (2 tiles,
  `0x00419C90`), boulevard = side + road + side (3 tiles, `0x0041AFB0`).
- The drag is a straight line along the longer axis of the drag (x if |dx| > |dy|, else y) from the start,
  one segment per tile; a drag of a single tile builds nothing.
- Segment test (each tile on its own; failing ones are skipped, not an error): road tile has road 0x40;
  every tile has no building and `terrain & 0x3DFFD407 == 0` (water, trees, rock, off-map, walls, rubble
  ... block; meadow and road do not, so a side strip may cover a crossing road); no tile object; and no
  parallel segment directly across either end (avenue: tiles x-2 and x+1 for an x-oriented one, by draw
  bits 0x07 / 0x38).
- Avenue side choice `0x0041AEA0` (start tile): on a non-road tile next to a road -> the strip is the
  clicked tile (road W: o2, N: o3, E: o0 with x+1, S: o1 with y+1); on a road tile -> strip west of a
  north-south road (o0) / north of an east-west one (o1) (E+W roads -> o1, N+S -> o0, then E or W -> o1,
  N or S -> o0). Then the drag axis forces the parity (o odd along x). When the start touches no road the
  side comes from the drag direction (decompile stack args garbled: **hyp**). Boulevards need no side
  choice (o = 1 along x, else 0).
- After the drag, `0x004195D0` removes every segment with no avenue/boulevard tile before or after it
  along the run (single segments die) and they are not charged.

## Road bits, walking, access (exe)
- `0x00418BD0` clears 0x40 on side strips; `0x004193A0` (row order, boulevards then avenues) sets it back
  on a side strip whose road pattern is not a side picture, or that has road N+S or E+W (a crossing road
  continues through the strip).
- Walkers: road tiles are road; avenue tiles with building bit are passable (`check_next_tile` 0x004D8BB0,
  route grid 0x10). Houses/buildings beside a side strip use the segment's road (`house_find_road_access`
  0x004A3B40 -> `tile_step_to_anchor` 0x00418B00).
- Clearing (`clear_land_commit` 0x0049A460) or destroying a tile removes its whole segment
  (`0x0041A6D0` -> `0x0041A490`): tiles lose the building bit, a tile that has road keeps it. The road stays.
- Desirability: every tile is a size-1 source with the type's model values (step 37b, desirability.md).

## Pictures (exe, view orientation 0)
Per tile in row order: 8-neighbour pattern (N NE E SE S SW W NW; neighbour = road 0x40 or avenue/boulevard
tile, `0x00419190`) matched against table `0x005E92B8` (47 records, `FUN_004A6920`) -> index k.
- Road (and side strips that became road): Zeus_General `SPR_BOUL_ROAD` first + k (+ rand & 3 when k = 15).
- Side strips: `0x00418A20` maps k -> offset from `SPR_BOUL_SIDE_SOUTH` (288): 31->0 SOUTH, 23->9 NORTH,
  27->18 EAST, 19->27 WEST, 11..14 -> 36..39 (3_CORNERS), 35/37/39/41 -> 40..43 (2_CORNERS).
  Straight sides get one of 9 pictures (`0x00418CF0`): 5 starts a group, then 4/6/7 by `rand & 7` while
  the next tile is the same side, 3 ends it; otherwise 0/1/2/8 by `rand & 3`, depending on the previous
  tile's picture and `rand % 9`. rand = the map's random grid. Seen: planters, cypress groups, end caps.

## Differences in our port
- Avenue tiles are a grid (`world.avenue`), not a building record; no (0,0) record and its quirk spread.
- Road bits and pictures are refreshed for both types after every road/avenue/clear change (the exe
  refreshes only the built type after an avenue drag). A run continuing from an avenue into a boulevard
  reads the other type's previous picture from the current pass (rare).
- Clear costs 2 dr per removed segment (hyp). Old saves: 2x2/3x3 avenue blocks are removed and refunded.
