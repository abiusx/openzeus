# View rotation (4 orientations): exe facts and the play-mode view transform

> **Note to everyone drawing in play mode (10-28):** the map can now be turned (PgUp / PgDn / Home, the
> rotate button). Never compute screen positions or draw order from `x - y` / `x + y` yourself. Use the
> helpers in `viewer/play/play.js`:
> - `tileX(x, y)`, `tileY(x, y)`: world tile -> screen box (already turned);
>   - draw order: never a depth of your own. Use `Order` (viewer/play/order.js, docs/play/draw-order.md):
>   `Order.obj(x, y, w, h)` for a picture of a footprint (scene.js `place()` does it), `Order.walker(fx, fy, opts)`
>   for a figure (scene.js `walkerSpot`), the same key for extras pushed after their picture;
> - `viewFoot(x, y, w, h)` -> `{ax, ay}` top-corner tile (the `place()` anchor), `{lx, ly}` left-corner tile
>   (the exe's anchor), turned `w, h`, `depth`;
> - `screenTile(sx, sy)` / `pixelWorld(px, py)` for input; `viewDir(d)` for a walker's world heading 0..7;
> - `viewMirror()` / `mirrored(sp)`: building pictures are drawn mirrored in views 2 and 6;
>   `scene.js place()` and `overlayAt()` already do it.
> `VIEW` is 0, 2, 4, 6 (the exe's values). The sim sees it for one rule only ("The view in the sim" below).

## Exe facts
- View orientation `0x00DA2F88` in {0, 2, 4, 6}, not saved (0 at start); `0x00FA05E8` is the working copy
  during a turn.
- Turn: `FUN_00408930` reads `0x00F135F8`: 2 -> `FUN_0044A620` (+2, wraps 6 -> 0), 1 -> `FUN_0044A6E0` (-2),
  0 -> `FUN_00408A60` (back to 0 by turning). Keys (window_proc, screen 1): PgUp 0x21 -> 2, PgDn 0x22 -> 1,
  Home 0x24 -> 0. The turn keeps the tile at the centre of the view in the centre (`FUN_00449F80` finds its
  cell in the new grid; col +1 / row +2 corrections for views 0 and 4), then `FUN_004A1B70` refreshes images
  (anchor bits, entry/exit flags, ...), `FUN_0051CD60` clamps the camera, `FUN_005231E0(10..13)` posts a message.
- Rotate button (`FUN_00517940`, entry `0x0063E098`): the click's x in thirds of the button: left = 1 (PgDn),
  middle = 0 (Home), right = 2 (PgUp). Picture (`FUN_00517A20`): first + (view/2)*8 + (part + 1 hovered |
  part + 4 pressed), part = 1 / 0 / 2 as above.
- Screen grid per view (`FUN_00449FF0`, 457 rows x 231 cells, staggered): row/col2 of world (x, y):
  v0 row 1+x+y, col2 230+x-y; v2 row 230-x+y, col2 1+x+y; v4 row 455-x-y, col2 230-x+y; v6 row 230+x-y,
  col2 455-x-y. Equivalently the plain view-0 projection of the turned tile
  `v2 (y, N-1-x)`, `v4 (N-1-x, N-1-y)`, `v6 (N-1-y, x)` (N = 228). Draw order = row order of that grid.
- Anchor tile of a multi-tile object (`building_footprint_place 0x004A04B0`, ground blocks `FUN_004A1BE0`):
  the footprint's left corner on screen: (0, h-1) v0, (0, 0) v2, (w-1, 0) v4, (w-1, h-1) v6.
- Mirroring: in views 2 and 6 every building picture is drawn mirrored (`building_mirrored 0x0045DC10`,
  city_draw `0x00458170` -> `FUN_005AE1B0` / `FUN_0045A790`); wall/garden pieces (flags 0x4020) too; the
  connectors between neighbouring columns (types 0x81/0x91/0x92) swap images 0x809 / 0x80F.
- Walkers: picture direction = (direction - view) & 7 (`walker_draw 0x0044FEF0`).
- Terrain pattern tables (water, shore, roads, cracks, marble): the record holds one picture index per view,
  column view/2 (`FUN_004A6920`); the neighbour pattern itself is in world directions.
- Turn message: `FUN_005231E0(10 + view/2)` = text group 19 [10..13]: North, East, South, West (oracle banners:
  PgUp from north shows East, then South, West). Ours: not shown (the button picture shows the view).

### Per-building pictures (decompile; "seen" = checked on an oracle shot, see Verification)
Every building picture is mirrored in views 2 and 6 (none is exempt); roads, terrain, cliffs, water are not.
`F(r)` = `r ^ 3` in views 2/6, else `r` (`0x00495390` + `0x0045DC50`). Building orientation `o` = +0xAC.

| Kind | Rule | Where |
|---|---|---|
| houses, every 1-picture building | same picture, mirrored in 2/6 (**seen**: houses plain in v0/v4, mirrored in v2/v6) | city_draw `0x00458170` |
| fishing wharf 0x2C, urchin quay 0x2D, dock pier 0x3C, trireme wharf 0x88 | first + F((o - view/2) & 3) | create `0x00496CA0`, turn `0x004953C0`; anims `0x0045AB70`, `0x0045ADE0`, `0x0044C0B0`, `0x0045B060` |
| dock house 0x3D | fixed pictures, position = pier + offset[o] | `0x00496CA0` |
| gatehouse 0x83 | +1 when (o+view)&7 in {0,3,4,7}, inverted in 2/6; piece order `0x0063A7C8[(o+view)&7]` | `0x004E4FA0` (buildings.md) |
| elite houses 0x09-0x0E | quadrant k: image `[2, rand&1, 3, 4][k']` at `Q[(k + view/2) & 3]`, Q = (2,2) (0,2) (0,0) (2,0); k' = k, 1<->3 swapped in 2/6 | `elite_house_place_sprites 0x004FECF0`, tables `0x0063B9E8`, `0x0063B988` |
| stadium 0x50 | v (o0): root S / part N in views 0, 2, swapped in 4, 6; h (o1): root E / part W in 0, 6, swapped in 2, 4 (**seen**: v0 S plain, v2 S mirrored, v4 N + S plain, v6 N mirrored) | `0x005AFB40`, table `0x005E4958` + (view/2 + 4o)*0x38 |
| sanctuaries, pyramids, palace | piece pictures: vt+0x4C reads the view `0x00DA2F88` itself; emulated per view and orientation (tools/re_monument_images.py -> monuments.json `view_phases`; a simple (o + view/2) rule is wrong: **seen**, the palace shows 1163/1174 in v0, the same mirrored in v2, plain in v4, mirrored in v6); positions by o; pieces mirrored in 2/6. Steps (`0x00545940`): neighbour i = `0x005D9888[(view + i) & 7]`; in 2/6 a pyramid's full shape is remapped (8 - s) & 7 (param_3); sanctuary ground steps (extras) drawn unmirrored (**seen**) | `0x0053D300`, `0x00545940` (monuments.md) |
| avenue 0x76 / boulevard 0x7E | pattern column view/2 (`0x005E92B8`); road tiles in 2/6 via `0x005E9674`; side strips: run flag `0x005E9664[view/2*4 + side/9]` swaps the run's start/end pictures (5/3), then `FUN_00418980` turns the picture in 2/6 (0..17 <-> 18..35, 37<->38, 40<->42) | `0x004193A0`, `0x00418CF0`, `0x00418A20` |
| walls 0x82 (ported 10-28, scene.js wallImage; rechecked 10-29: tools/oracle_walls.py 40/40 in all 4 views) | neighbours N, NE, E, SE, S, SW, W, NW (world) count with 0x4000 or 0x8000 (`0x004A1FF0` + `0x0049F6F0`, inverted `0x004A6C60`); pattern table `0x00636820` (48 records) column view/2; tower beside the tile, per view (`0x0049F7D0`: v0 N->2, W->1; v2 E->2, N->1; v4 S->2, E->1; v6 W->2, S->1) adjusts the offset (`0x0049F8A0`); views 2/6 swap pairs (`0x0049F560`) and draw the picture mirrored; picture = SPR_STONE_WALLS + offset (**seen**: 40/40 tiles in each view) | `0x0049FD70` (on every turn via `0x004A1B70` -> `0x0051D760`) |
| column connectors 0x81/0x91/0x92 | 0x809 left / 0x80F right of a neighbour column; in 2/6 swapped and mirrored | city_draw |
| commemorative 0x77 | big: F((o - view/2)&3); small: F((o + view/2)&3) | `0x00496CA0` case 0x77 |
| horse ranch 0x85 / corral 0x86, tower 0x84, water park, farms | fixed pictures (only mirrored) | |
| bridges 0x78 | view-relative pieces renumbered per turn (`0x0041DF90`), mirrored map `0x0041E410` | bridges agent |
| race track 0xC7 | L in {1,5} (v0/4) or {3,7} (v2/6): L + view, else L - view, mod 8 | `0x0056E880` |

Other refreshers on a turn (`FUN_004A1B70`): entry/exit markers (`0x004A1D30`: picture by (side + view)&7 / 2),
walkable wall tops (`0x00587E50`: neighbours per view), sentries moved off them (`0x004CFEE0`), scroll limits
(`0x0051CC70`), "draw walkers again" grid (`0x00448990`). Walkers: `(direction - view) & 7`; missiles
`(dir - 4*view) & 31`; per-view fine-position tables `0x005F0258`.. (`walker_draw 0x0044FEF0`).

Cliffs: a turn redraws every ground picture (`FUN_00521520(3)` = map_tiles_update_images on the whole map):
`map_elevation_project 0x0045ED20` (projected altitude grid 0x008ECD0A, step (-1,-1) v0 / (+1,-1) v2 / (+1,+1) v4 /
(-1,+1) v6; read only by the cursor pick `FUN_0045FB00`, ported in play.js screenTile / projectedElev, bugs.md 389; it also cleans flags 0x400/0x800000/0x800/0x80/0x1), then
cliff pieces pass 1 `FUN_0051FEC0` (matcher `FUN_0045E110`, table `0x005F8F28`: 152 records of 16 int32, neighbour
elevation pattern in world directions, picture code column view/2) and pass 2 `FUN_005200B0` (2x2 pieces through
building_footprint_place, anchor per view). Ported in tools/terrain_cliffs.py (its docstring has the tables and
steps): view 0 = the sandbox map's own cliff ids and draw bytes 426/426; all Adventures maps 99.87 % of 64,593 cliff
tiles at the view each was saved in, and the two maps saved in views 4 and 6 match 100 % there (0 % at the other
views). No map was saved in view 2. Play mode: sim/terrain_view.py computes views 2/4/6 once (cliffs are static),
terrain.json `cliffs2/4/6` = [[tile, id, draw]], play.js buildTerrain uses them in that view.

## Play mode (viewer/play)
- One transform (play.js): `VIEW`, `viewXY`/`worldXY`, `tileX`/`tileY`/`tileDepth`/`footDepth`/`viewFoot`,
  `screenTile`, `pixelWorld`, `viewDir`, `viewMirror`/`mirrored`. Draw order = turned x+y (the exe's row order).
  `rotateView(d)`: keys PgUp (+2), PgDn (-2), Home (0), the rotate button by thirds; keeps the centre tile.
  Camera saves and bookmarks are stored in view-0 pixels (`camView`/`setCamView`). The view is not saved
  (the exe's isn't either): a reload starts north.
- Terrain (play.js buildTerrain): drawn in the turned row order; multi-tile ground blocks from their view
  anchor (`blockAnchor`, draw byte r*8+c); pattern-table tiles (water edges, shore, cracks, marble, roads of
  the terrain pass) take terrain.json `alt` deltas (terrain_images `images_full(alt=)`, sim/terrain_view.py);
  play-mode roads use the road tables' 4 columns (data/play/buildings.json road tab17/tab48 [pattern, off, offs]).
- scene.js: `place()` takes a footprint's min tile and anchors it at the view's top corner, mirrors in 2/6;
  `overlayAt()` mirrors pictures drawn inside a building (anims, crops, stock, vendors, granary piles);
  `viewOrient(o)` for shore buildings and piers; elite houses, stadium, gatehouse per the table above;
  walkers' headings through `viewDir`; walls by the exe's table (scene.js `wallImage`: WALL_T, WALL_TOWER, WALL_SWAP).
  monuments.js: ctx.viewFoot/mirror, pictures `phasesOf(.., o, view)` (view_phases), steps by turned neighbours; the
  priestess/guard/firepot ambient figures in every view and orientation from the piece's left-corner tile
  (docs/play/monuments.md 6a; guard and priestesses in views 0-6 at the oracle's offsets from their piece picture).
- Avenues: sim/systems/avenues.py `recompute(..., view)` (presentation only, on a copy of the road grid;
  the sim's road bits stay view 0), terrain.json `avenues2/4/6`.
- Minimap (ui.js): the same projection on the turned tile; clicks go through `worldXY`.
- Build tools (build.js): the ghost box is centred on the cursor in turned tiles (`anchorFor`), then sent in
  world tiles.

## The view in the sim (10-29, bugs.md 178)
The one simulation rule that depends on the view: the wall-walk grid (`grid_walls`, `0x00587E50`). A wall tile
(0x4000) is walkable when its three neighbours toward the view's back corner hold a wall or tower (0xC000):
v0 (x+1,y) (x,y+1) (x+1,y+1); v2 (x-1,y) (x,y+1) (x-1,y+1); v4 (x-1,y) (x,y-1) (x-1,y-1); v6 (x+1,y) (x,y-1)
(x+1,y-1); tower tiles (0x8000) always. On a turn `0x004A1B70` rebuilds it and `0x004CFEE0` takes every wall
sentry (0x27) standing on a closed tile to the first open tile in the squares 1, then 2 around it (`0x004A3A20` /
`0x004A3A70`, rows top-down, columns left-right), else back onto its tower (action 6). It then sets the walk-home
action and frees the route on `g_current_figure` instead of the sentry (an exe slip); ours sends the sentry home.
Ours also re-routes a sentry whose remaining walk crosses a tile the turn closed (the exe's route handling there
is not read).
- Interface: the sim command `view 0|2|4|6` (Game.command; `view` alone prints it). It sets `g.view` (pickled
  with the game, so a save and its command log carry it; new games 0) and calls `military.view_changed(g)`, which
  rebuilds the grid (sim/military/defences.py `wall_grid`, cached per occupancy version and view) and moves the
  sentries. Nothing else in the sim reads `g.view`.
- Play mode: `/frames.json` meta carries `view`; a live tab sends `view N` (POST /cmd without a tick: accepted at
  any time) after each turn and whenever the meta shows another view than its own (a fresh page starts at 0, as
  the exe after a load). Two live tabs in different views would take turns setting it; the last one wins.
- Check: tests/test_terrain.py `test_wall_grid_per_view`; headless Chrome (tools/play_cdp.mjs) on a copy of
  save H: the sim's view follows the page through PgUp x4 and PgDn; save H's grid has 76 / 75 / 74 / 75 tiles in
  views 0 / 2 / 4 / 6, and its 3 sentries were moved on turns as the rule says.

## Verification (10-28)
Oracle runs (re/oracle/runs/, git-ignored; scenarios in re/oracle/scenarios/):
- `rotation-sandbox.txt` (Open Play Sandbox, 800x600, views 0/2/4/6 via PgUp): the exe's camera at start is cell
  (94, 160) (dump 0x00DA2F64/68); the camera of each turned view follows from the turn rule (centre cell kept, col
  +1 in views 0/4, row even): v0 (94,160), v2 (84,242), v4 (126,258), v6 (133,178). In play-mode pixels
  (zoom 1/devicePixelRatio, dpr 1.25) that is cam = (60c - 6870, 15r - 30) in views 0/4 and (60c - 6810, 15r - 60)
  in 2/6. Play mode on a new sandbox game, read back with gl.readPixels and compared with the shot (each channel
  within 8, map area x 10..590, y 80..580): v0 94.9 %, v2 98.9 %, v4 95.0 %, v6 94.0 %, best offset (0, 0) in
  all four (searched +-600 px); the rest is water animation phase and a few sheep. So the transform, the turn
  direction (PgUp = view +2), the centre rule and the per-view terrain pictures match the exe. (That area has no
  cliffs.)
  An odd ROW (only by a poke; a turn keeps it even) shears the exe's screen rows: tiles of even x + y 30 px left of
  this rule, odd x + y 30 px right (bugs.md 363).
- `rotation.txt` / runs rotation2 (working city tutorial, 1024x768) and rotation-shore (its dock),
  `python3 tools/oracle_rotation.py SHOTS -s FILE:INDEX`: houses (1018, 1019) plain in views 0/4, mirrored in 2/6;
  stadium 442 plain (v0), 442 mirrored (v2), 441 + 442 plain swapped (v4), 441 mirrored (v6); dock pier
  (o 2): 465, 465 mirrored, 463, 463 mirrored (= F((o - view/2)&3)); rotate button picture
  1235 + 8*(view/2) exact in all four views. Turn banners: East, South, West after PgUp from north.
- Input: in every view, screenTile(tile centre) returns the tile (395 flat tiles per view); building by mouse
  events in each view: the ghost spot = the built spot (fountain 2x2, storehouse 3x3).
- Readback at dpr 1.25, zooms 0.8 / 1 / 1.6, views 0-6: no gap lines along tile or sprite seams (the near-black
  pixels are inside sprites: doorways, tree shade).
- Composites (rotation-palace.txt, rotation-sanctuary.txt: the working city's palace and Apollo sanctuary in the
  4 views; in-browser match of the baseline save's palace / Apollo, its own pictures placed at the best offset,
  share of its pixels equal in the shot): palace 96 / 83 / 81 / 91 %, Apollo 85 / 87 / 92 / 65 % (views 0/2/4/6).
  The rest is what covers them in the shot (walkers, the panel edge in v6, statues the baseline's Apollo lacks).
- Walls (rotation-walls.txt: Open Play Sandbox with a 9x9 test layout of walls and tower tiles poked in;
  `python3 tools/oracle_walls.py DUMP w0 0 w2 2 w4 4 w6 6`): the predicted picture of every wall tile is the
  best-matching one of the 36 at its spot in all 4 views (40/40 each; pixels covered by nearer walls left out).
- Cliffs (rotation-cliffs.txt: the sandbox's cliffs near (110, 190), camera poked; play mode on a sandbox save, the
  exe's camera cell per view through the turn rule, the map area read back and compared as in rotation-sandbox):
  89 / 88 / 88 / 89 % (views 0/2/4/6). The rest is the same in every view (a patch of ground the save differs in,
  and a few small triangles at cliff tops), so the turned views add no error. The report of black holes by the
  quarries (bugs.md 156) came from a server started before the per-view terrain existed; play.js now warns.
- Map edge: the exe's scroll limits (`0x0051CC70`, from the play-area cells along the view grid's middle lines,
  recomputed on a turn) never show the black past the grid. Play mode now clamps the camera to the play area
  (tiles without 0x80000) of the current view, inset by half a tile (play.js `clampCam`).
