# Desirability

Status: **verified** from the exe unless marked. Addresses refer to GOG `Zeus.exe`.
Grid and building names: [map-terrain.md](map-terrain.md), [buildings.md](buildings.md),
`re/names/map-buildings.tsv`, `re/structs/map-buildings.tsv`.

## Summary
Desirability is an `i8` per tile (`g_grid_desirability` `0x00C9B4E8`, sav rank 23), range −100…100.
It is rebuilt from scratch once every 51 ticks: cycle step 37 clears the grid, adds every
building's contribution (in building-id order), then every terrain source (row-major). Step 38
copies into each building the best value over its footprint (+10 if it touches water). Houses
read that byte (`Building+0xCE`) at step 39 (housing evolve, see housing-evolution.md).

A source has four model values (building model columns 1–4, read through
`model_building_value(type, k)` `0x00433D50` = `g_building_model[type*10 + k]`, `0x00782F70`):
`value`, `step`, `step_size`, `range`. They do not depend on difficulty.

## When it runs (verified, `simulation_cycle_step` `0x00483840`)
| cycle step | call |
|---|---|
| 37 (`0x25`) | `desirability_from_buildings` `0x00493830`, then `desirability_from_terrain` `0x00493C80` |
| 38 (`0x26`) | `buildings_update_desirability` `0x004842A0` |
| 39 (`0x27`) | `houses_evolve` (housing agent) reads `+0xCE` |

The step counter `0x0091EC14` (sav rank 37) runs 0..50, one step per simulation tick, only when
not in the editor (`0x00665E2C == 0`).

## Coordinates (verified)
Tile index = `base + 228*y + x` with `base = 0x00DA2F80` (=10076 = 44*229 in the tutorial, i.e.
logical (0,0) is raw (44,44)). Logical x = −1 or y = −1 are still inside the raw 228×228 array;
the exe writes there (see the avenue quirk below), so a port must keep the raw array and the base.
W = `0x00DA2F78`, H = `0x00DA2F7C` (map width/height).

## Ring geometry (verified)
"Ring r around a size-s footprint anchored at (x,y)" = the tiles at Chebyshev distance exactly r
from the rectangle [x, x+s−1] × [y, y+s−1]; count 8r + 4(s−1). Anchor = min-x/min-y corner.
- Size 1: dx/dy tables built at start-up by `rings_size1_build` `0x00495FB0` (r = 1..12, row-major
  scan of the square, border cells only); offsets built by `rings_offsets_build` `0x004A52F0`.
- Sizes 2..6: static dx/dy tables `0x005F0848`(s2 r1), `0x005F0860`(s2 r2) … `0x005F1120`(s6 r6);
  counts at `0x005F07B6 + 12*(s−2) + 2r`; offsets at `0x0078ABEC` (s2) … `0x0078A40C` (s6).
Order of tiles inside a ring is irrelevant (each tile is touched once per ring).

## `desirability_add_ring(x, y, s, r, v)` `0x004A4C60` (verified)
```
if s not in 1..6: return
n = ring_count(s, r)
if (H < s + y - 1 + r) or (W < x + s - 1 + r) or (y - r < -1) or (x - r < -1):
    for k in 0..n-1:                                   # slow path, per tile bounds test
        if ring_tile_off_map(x, y, s, r, k): continue  # 0x004A4E70
        add_clamped(tile_k)
else:
    for each tile of the ring: add_clamped(tile)       # fast path, no test
add_clamped(t): s = (int8)grid[t] + v
                grid[t] = 100 if s > 100 else (-100 if s < -100 else s)
```
`ring_tile_off_map` (verified): tile (x+dx, y+dy) is off when `x+dx < -1` or `y+dy < -1` or
`x+dx > W` or `y+dy > H` (so −1..W and −1..H are "on").
**Quirk (verified in the listing at `0x004A520C`):** for size 6 the test reads the dx/dy of the
wrong ring: ring r (1..4) uses ring r+1's table, rings 5 and 6 use ring 6's table. The index k
can therefore point at a different tile than the one written. Only a size-6 building (type 207
museum) within 7 tiles of the map edge is affected. Reproduce it literally.

## `desirability_spread(x, y, s, v, step, step_size, range)` `0x004A4BF0` (verified)
```
if s <= 0: return
range = min(range, 6)
c = 0
for r in 1..range:
    desirability_add_ring(x, y, s, r, v)
    c += 1
    if c >= step: v += step_size; c = 0
```
(If step ≤ 0 the value changes after every ring.)

## `desirability_spread_rect(x1, y1, x2, y2, v, step, step_size, range)` `0x004937B0` (verified via listing; decompiler argument names are wrong)
```
range = min(range, 6); c = 1                     # NOTE: counter starts at 1, unlike the square version
for k in 0..range-1:
    desirability_add_rect_border(x1-k, y1-k, x2+k, y2+k, v)
    c += 1
    if c >= step: v += step_size; c = 0
```
`desirability_add_rect_border(x1,y1,x2,y2,v)` `0x00493700`: adds v (same clamp) to every tile of
the border of the rectangle [x1−1, x2+1] × [y1−1, y2+1], no bounds test.
Consequence: with step = 2 the rect version changes the value after ring 1, the square version
after ring 2.

## Step 37a: `desirability_from_buildings` `0x00493830` (verified)
```
grid[all 51984] = 0
for id in 1..buildings_last (0x0091EBF8):
    b = buildings[id]
    if b.state != 1 or b.parent_part(+0x38) != 0: continue
    (v, st, ss, rg) = model cols 1..4 of b.type
    t = b.type
    if composite(t) [84..98, 117] or 100 <= t <= 114:
        if b.monument_unfinished(+0xDA) == 0 or t == 117:
            rect = composite_bounds 0x0053CF30(id, ..., 1); spread_rect(rect, v, st, ss, rg)
        continue
    if t in (63, 64):  rect = 0x0040C9B0(id); spread_rect(...)        # agoras
    elif t == 80:      rect = 0x005B02E0(id); spread_rect(...)        # stadium
    elif t == 58:      spread(x, y, 3, ...)                            # storehouse
    elif t == 62:      spread(x, y, 4, ...)                            # trading post
    elif t in (59, 61, 134): nothing
    elif t == 60:  # dock, orientation o = +0xAC
        (dx,dy) = [(-1,5),(-4,-1),(-1,-4),(5,-1)][o]; (ex,ey) = [(3,0),(5,3),(3,5),(0,2)][o]
        spread_rect(min(x,x+dx), min(y,y+dy), max(x,x+dx+ex), max(y,y+dy+ey), v, st, ss, rg)
    elif t == 133: # horse ranch, o = +0xAC
        spread_rect(x+a, y+b, x+c, y+d, v, st, ss, rg) with (a,b,c,d) =
        o=0:(0,-1,6,2)  o=1:(-1,-4,2,2)  o=2:(-4,0,2,3)  other:(0,0,3,6)
    else: spread(x, y, size(+0x03), v, st, ss, rg)
```
x = `+0x06`, y = `+0x08`. The `+0xAC` values beyond 3 index the stack table out of range for the
dock (not expected in play). Composite/agora/stadium rectangles come from other subsystems'
layout code (`0x0053CF30` religion, `0x0040C9B0` agora, `0x005B02E0` stadium): **cross-reference**.

**Avenue/boulevard quirk (verified):** types 118 (avenue) and 126 (boulevard) are a single
building record per drag, created at (0,0) (`0x00418B40` calls `building_create(type,0,0,0,0)`).
They fall in the default branch, so each such record also spreads a size-2 (avenue) or size-3
(boulevard) square around logical (0,0), whose ring 1 goes through the fast path into logical
x/y = −1. Their real contribution comes from the per-tile pass below.

## Step 37b: `desirability_from_terrain` `0x00493C80` (verified)
Over the playable rows y = 0..H−1, x from `0x00DA2BD0[y]` to `0x00DA2840[y]`−1 (tile index from
`0x00DA24B0[y]`), each tile a size-1 source at (x,y):
```
bid = building_grid[t]
if bid != 0 and buildings[bid].type in (118, 126):
    spread(x, y, 1, model cols 1..4 of that type)          # avenue 3/1/-1/3, boulevard 3/2/-2/4
elif piece_grid[t] & 0x80:
    if terrain[t] & 0x2: spread(x, y, 1, cols 1..4 of type 2)   # all zero in shipped models
    else: piece_grid[t] &= 0x7F
elif terrain[t] & 0x20: spread(x, y, 1, cols 1..4 of type 128 BUILD_GARDENS)  # 3/1/-1/3
elif terrain[t] & 0x1000: spread(x, y, 1, -2, 1, 1, 2)       # rubble: -2 ring 1, -1 ring 2
```
Note: avenue tiles get the avenue values on every tile (road tile and side strips; how they are
placed: [avenues.md](avenues.md); sim: `avenues.desirability`, before the clamp); garden tiles (terrain 0x20, painted by the
gardens tool, not buildings) get row 128.

## Step 38: `buildings_update_desirability` `0x004842A0` (verified)
```
for id in 1..buildings_last:
    b = buildings[id]; if b.state != 1: continue
    s = b.size(+0x03)
    if s == 1: d = grid[b.tile]
    else:
        d = -9999
        for r in 0..s-1, c in 0..s-1: d = max(d, (int8)grid[b.tile + r*228 + c])   # table 0x005F1560
    b.desirability(+0xCE) = (int8)d
    if b.adjacent_water(+0xD0): b.desirability = (int8)(d + 10)
```
Size 0 (no type with size 0 is a placed building in practice) would store (int8)−9999 = −15.
`+0xD0` is computed once at creation by `building_adjacent_to_water` `0x004A4500`: 1 when any
edge-adjacent tile (table `0x005F1680`, no corners) of the footprint has terrain `0x4`.
Houses therefore gain +10 when next to water (coast, river) — **verified**.

## Reading the result
House evolve uses `(int8)+0xCE` vs house model cols 0/1 (housing-evolution.md).

## Constants
- clamp ±100: immediates in `0x004A4C60`, `0x00493700`.
- max range 6: `0x004A4BF0`, `0x004937B0`.
- water bonus +10: `0x004842A0`.
- rubble source −2/1/+1/2: immediates in `0x00493C80`.

## Cross-references
- `composite_bounds` `0x0053CF30` (religion: sanctuary/palace/pyramid rectangles).
- `0x0040C9B0` agora rectangle, `0x005B02E0` stadium rectangle (buildings of other agents).
- `houses_evolve` step 39 (population-housing).

## Ours (sim/systems/desirability.py, 1F 10-30, bugs.md 266)
Steps 37a, 37b and 38 as above: sources in id order with the clamp on every add, range <= 6, the rectangle counter
from 1, composites only when finished (palace always), stalls skipped (parts of the agora in the exe), gardens
(type 128) moved to the terrain pass, rubble a size-1 source around its tile, houses + 10 next to water (step 38,
housing.update; ours from the current footprint, the exe's flag is set once by building_create). Rectangles:
`composite_bounds` `0x0053CD80` is the min/max over the parts and extras (extras class 1006 excluded: pyramids
only), ours the monument layout's box (tools/monuments.py: the bounding box of the same rows); agora and stadium
the building's w x h; dock = DOCK_RECT from the pier, horse ranch = RANCH_RECT, both by orientation (the dock's
orientation-3 rectangle is one row short of the house: kept). Not copied: the avenue record's square around
logical (0, 0) (off the play area).

## Open questions
- Exact rectangles returned by `0x0053CF30`, `0x0040C9B0`, `0x005B02E0` (not traced here; ours: see "Ours").
- Whether any map can have a building with orientation byte > 3 for docks.
