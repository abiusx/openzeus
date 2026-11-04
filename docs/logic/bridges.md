# Bridges

Status: **verified** from the decompile (2026-10-28) and an oracle run (runs/bridge, scenarios/bridge.txt: the
exe's piece grid and cost match ours, the picture matches play mode).
Tool 0x78 (BRIDGE, model type 120, cost 15 per tile on Normal); tool 0xC9 is the race-track crossing (same
code, other branch, pieces 15..20). Drawing and ships: pathfinding.md §7.3.

## Placement `FUN_0041C450` (the tool's hover/validate; non race-track branch)
The player points at ONE tile, A; the span follows from the terrain:
```
A must be water (0x4), no road/building (0x48), and none of its 4 neighbours beach (0x10000, FUN_004A36B0)
direction: the first of A's 4 neighbours that is NOT water, tested N, E, S, W; the bridge runs the other way
   (N land -> step +228 "dir 4"; E land -> step -1 "dir 6"; S land -> step -228 "dir 0"; W land -> step +1 "dir 2");
   all 4 water -> invalid
len = 1; if the next tile is water, up to 15 times:
   advance; len += 1; next = tile + step
   next has a tree (0x1)                     -> invalid
   this tile deep (0x4000000) and road (0x40) -> invalid (crossing a bridge)
   next not water                            -> stop (far shore reached)
   next road/building (0x48)                 -> invalid
   this tile's 4 diagonals not all water (FUN_004A36F0 != 4) -> invalid
end tile E (the last water tile):
   a bridge piece (0x00CB4B08) beside E (E+-1 for N-S bridges, E+-228 for E-W) -> invalid
   len < 2: valid if no beach beside E
   len >= 2: valid if E has exactly 3 water 4-neighbours (land ahead) and no beach beside it
```
So a span is 1..16 water tiles, needs open water on both sides of every inner tile (no pond or 1-tile-wide
creek crossings except a 1-tile span), and lands on the shore straight ahead. The land tiles at either end are
NOT part of the bridge: roads must be built to them.

## Commit (build_commit 0x00498910, tool 0x78 -> `FUN_0041D910` -> `FUN_0041D8B0`)
Each of the `len` tiles from A: terrain |= 0x40 (road; the water bit stays), piece number `FUN_0041D720(i, len,
dir)` in `0x00CB4B08` (pathfinding.md §7.3). Then `0x00587E20` (ship grid) and `route_grid_rebuild`.
Cost: `g_build_cost = len x model cost`. An invalid site: warning 19:23 "Find a good site along the water".

## Pieces `FUN_0041D720(i, len, dir)` (i = 0 at A; dir 0 = step -228, 2 = +1, 4 = +228, 6 = -1)
```
len < 4:          14 if dir in (0,4) else 13                       (short: ships can't pass, pathfinding.md §7.3)
len >= 4, dir 0:  i=0: 7, i=1: 8, i=len-2: 11, i=len-1: 12, middle 9 (i even) / 10 (i odd)
len >= 4, dir 4:  i=0: 12, i=1: 11, i=len-2: 8, i=len-1: 7, middle 9 / 10
len >= 4, dir 2:  i=0: 1, i=1: 2, i=len-2: 5, i=len-1: 6, middle 4 (i even) / 3 (i odd)
len >= 4, dir 6:  i=0: 6, i=1: 5, i=len-2: 2, i=len-1: 1, middle 4 / 3
```
Ours: sim/game.py `bridge_piece`, stored per tile in `g.bridge_pieces` at build (older saves: derived from the
straight runs of `g.bridges`, `Game.bridge_spans`).

## Drawing (`city_draw` -> `FUN_0041D150`)
In the object pass, a tile with terrain & 0x44 == 0x44 (water + road) and a piece draws Zeus_General SPR_BRIDGE
(packed 0x85A; Poseidon game: 0x6802 for long pieces) + image k, k by piece: 2->0, 3->1, 4->2, 5->3, 8->4, 10->5,
9->6, 11->7, 13->8, 14->9; pieces 1/6/7/12 (the two end tiles of a long span) draw nothing: the 119x100 ramp
pictures of pieces 2/5/8/11 (one tile in) cover them. Position: the tile's screen box + (-31, -47) for the
119x100 pictures, + (0, 0) for the 58x34 short ones. Views 2 and 6 first turn the piece (`FUN_0041E410`: 1<->12,
2<->11, 3<->9, 4<->10, 5<->8, 6<->7, 13<->14). The ground under it stays water. Play mode: viewer/play/bridges.js
(terrain.json `bridges` = [[tile, piece]]; the road picture is not drawn on water tiles).
Boats: in the Zeus game the exe draws figures in tile order only, so a boat on a bridge tile is drawn over that
tile's deck; the Poseidon game redraws an overlay (SPR_BRIDGE_OVERLAY via `water_life_draw` 0x0041D3D0, offsets
tables in it) over figures on water near a bridge. Ours (deviation, to show boats under long bridges without the
Poseidon art): a boat on a bridge tile sorts at the cell two rows up (viewer/play/order.js), under that tile's piece
and the ones behind; people on a bridge tile are drawn two rows later, as the exe (docs/play/draw-order.md).

## Clearing (`FUN_0041DA20`)
Clearing any tile of a bridge removes the whole span: it walks to one end along the bridge's axis, then clears the
road bit and the piece along it. Ours: `Game.remove_bridge` (clear), 2 dr per tile as other roads (cost of the
exe's clear for bridges not checked). Undo restores the bridge sets.

## Oracle (2026-10-28, re/oracle/scenarios/bridge.txt)
Open Play Sandbox, Easy: the tool at tile (78,108) builds (78,108)..(78,114); block 21 (0x00CB4B08) then holds
12 11 9 10 9 8 7 (= `bridge_piece(i, 7, 4)`), the treasury drops 84 = 7 x 12 (Easy bridge cost). The exe's ghost
draws the pieces tinted green: FUN_0041C8E0 sets the blitters' mask DAT_0078C570 = 0x1FE3 and every pixel is ANDed
with it (the oracle draws RGB555: red keeps 3 low bits, green whole, blue 2); an invalid spot: the tile diamond
ANDed with 0xF863. Ours since 10-29 (bugs.md 212): the pieces opaque through gl.js's mask (alpha < 0), no diamonds. Play mode at the same
view (zoom 1 device px, devicePixelRatio 1.25): in the span's box (240x130 px) every pixel is within 23 per
channel of the exe shot, 78 % within 7 (RGB565 rounding; the rest is the water animation phase).
Ghost composition (10-30, bugs.md 212; FUN_0041C8E0): not the built bridge tinted. From the hovered tile A, in the
screen direction sd = (dir - view) & 7, piece i is FUN_0041D720(i, n, sd) (no view turn, no mirror) at A's point +
i * (+-29, +-15) (half the 58-px tile, so the ghost drifts 1 px a tile against the built pieces); spans of 4+ tiles
draw i = 1..n-1 shifted (-32, -47), shorter ones i = 0..n-1 unshifted; for sd 0 / 6 the list is drawn again reversed.
A refused span: the start diamond green (2+ tiles scanned) or red, and a red diamond at the last scanned tile, reached
in the same steps. Ours: bridges.js `Bridges.ghost` (live.py footprint gives `dir`). Oracle bridge-views (4 views,
re/oracle/scenarios/bridge-views.txt): 97..99.5 % of the exe's tinted ghost pixels within 8 in every view.

## Ours
`bridge X Y` (Game.bridge_site / Game.bridge, sim/game.py); the old `bridge X1 Y1 X2 Y2` is read as a click
on the tile after (X1, Y1) toward (X2, Y2). The sandbox has 36 valid start tiles for spans of 3+ tiles (most crossings work from either shore),
the longest 11 tiles at (95,98)..(95,108). `g.bridges` holds the water tiles (drawing); spans under 4 tiles also go in `g.bridge_short`, which boats
cannot enter (walkers._water). Not modelled: the Poseidon-game pillar tiles (pieces 4/10) blocking ships.
Play mode: the Water Crossing tool is a single click (`bridge X Y`); the ghost comes from /footprint.json?key=bridge
(`Game.bridge_scan`: the span's tiles green with its pieces, or the scanned tiles red with the reason). The
race-track crossing (0xC9) is not in (Poseidon).
