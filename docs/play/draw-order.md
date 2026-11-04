# Draw order: the exe's rule and the play-mode port

Why: play mode kept drawing things in the wrong layer (bugs.md 26, 84, 98, 105, 111, 134, 161, 167, 176). Each fix added a
depth constant (+0.25 walkers, +0.3 beside a building, +0.35 storehouse pieces, +0.45 gate arches, -6 corral, +0.05
sentries). This page is the exe's actual order, read from the decompile, and the one rule play mode now follows.
Sources: `city_draw` 0x00458170 (re/decomp/zeus.c, `python3 tools/fn.py 00458170`), refs/zeus-poseidon-arm64
docs/engine/rendering.md §10-11 (its native rewrite of the same function), their names (re/names/.upstream/00-arm64.tsv, fetched by tools/upstream_names.py).

Note: the names `city_draw_tiles` 0x0047499F, `city_draw_tile_footprint` 0x004743EA and `city_draw_tile_top`
0x0047A880 in the upstream names (re/names/.upstream/00-arm64.tsv) are wrong for this build (the first two decompile to unrelated code, the third
is not a function start). The city is drawn by `city_draw` 0x00458170 alone.

## 1. The grid (exe)
- The view is a staggered grid of 457 rows x 231 cells (`0x007D3BEC`, rotation.md "Screen grid per view"). In
  turned tile coordinates (a, b) (play.js `viewXY`): row = a + b (+1), column order = a - b (screen x).
  Cell (r - 2, c) is the tile straight above on screen = turned (a - 1, b - 1).
- `city_draw` walks the visible cells row by row (top to bottom), each row left to right, three times.
- A multi-tile object is drawn at ONE cell, its **anchor**: the footprint's left corner on screen (draw bit 0x40,
  `building_footprint_place` 0x004A04B0; (0, h-1) in view 0, (0, 0) v2, (w-1, 0) v4, (w-1, h-1) v6). That is the
  footprint's middle row, not its front tile.

## 2. Pass 1: ground (0x0045826C..0x00458653)
Every cell's ground picture (`ground_tile_draw` 0x00457900), back to front, except pictures with a "top" (image
entry +0x35: the compressed part above the isometric base) that are not simple vegetation, i.e. not
(piece size 0, terrain & 0x881 tree/scrub/meadow, not & 0x1000C208): those wait for pass 2, unless the tile two
rows behind is higher (then pass 1 draws them). Roadblock 0x7B, corral 0x86 and types 2, 9 are drawn here as
ground too. Water animation steps here. `ground_tile_draw` draws the isometric BASE of a picture only; the top of
every anchored picture (trees and rocks included, Zeus_Terrain: SPR_TREES*, SPR_ROCK_*, SPR_E1/E2/EH*, grass and
meadow tufts have +0x35 set; tools/sg3.py `has_top`) comes in pass 2 step 4.
A cell is whatever the picture grid `0x00D4CFC8` holds: on a building's tiles that is the building's picture, so the
map's ground picture (scrub, meadow) is not drawn there at all, in any pass.

## 3. Pass 2: per cell, in this order (0x00458792..0x00459FF0)
1. **Ground again** (`ground_tile_draw`): for
   - pictures with a top that pass 1 left (cliff blocks, rocks, building bases): at their anchor cell, unless a tile
     two rows ahead is higher, or four rows ahead higher by 2 (0x00458A19);
   - other tiles when raised: higher than the tile two rows behind (-> same test as above), or, with elevation
     e > 0, some tile k = 1..e steps behind (2k rows) has elevation <= e - k (0x004589A0 loop);
   - tiles with terrain bit 0x40000000, set by `walker_draw` on neighbours higher than a walker's tile and cleared
     when redrawn (a frame-to-frame effect; not ported).
   So the BASE of flat-ground trees, scrub and meadow stays ground unless raised; their tops come at step 4.
2. Ambient sound counters (nothing drawn).
3. **Bridge piece** (terrain & 0x44 = water + road, piece byte `0x00CB4B08` != 0; or 0x48 + race track 199):
   `0x0041D150`, and the tile's byte in `0x0083AD6C` is set to 1 (its people are drawn 2 rows later, below).
4. **Object top** when the cell is an anchor (draw bit 0x40), terrain anchors too (a tree's crown, a rock's
   boulders, the tufts of scrub; call at 0x004592A3): `building_top_draw` 0x005ADF00 (mirrored
   0x005AE1B0 in views 2/6) or `sloped_top_draw` 0x0045A690 for pieces with a slope size (it only moves the
   position to the block's left corner, then calls `building_top_draw`); walls and gardens (flags
   0x4020) the same way. `building_top_draw` draws the image's compressed top (data + base length) and nothing
   else: by image width (+0x14) 58 / 118 / 178 / 238 / 298 / 358 (n = 1..6 tiles) at x - 30(n-1),
   y - h + 30 + 30(n-1), h - (15n + 1) rows (h = image +0x16), i.e. every row above the footprint diamond's middle
   row; the lower half of the diamond is only the base's (pass 1 or step 1); then `composite_draw_extras` 0x0053E5F0 (sanctuary/monument parts), the column connectors
   0x809 / 0x80F. Special (0x00459192..0x004591F8): a 1x1 anchor whose terrain has none of 0x2DFED66F (plain
   grass, scrub 0x80, meadow 0x800; never a building: every building tile has 0x8) gets no top at all this frame
   when a figure of type 1, 4, 0xD, 0x1C, 0x2A, 0x43-0x45 (immigrant, cart, horseman, ox team, enemy cavalry,
   god, monster, hero; `figure_type_on_tile` 0x0045DAF0, only on a tile whose 0x0083AD6C byte is 0, not hidden)
   stands on one of the two cells above it, (r - 1, c) and (r - 1, c + 1) of the staggered grid (c - 1 and c on
   odd rows): the tufts never cover those wide figures.
5. **Building extras** at the anchor: vendor goods, the per-type switch (stall vendors, fish pond, wharves, quay,
   storehouse worker 0x0044BE90, pier, dock house, trading post, stadium, theatre, ...), the image animation
   (`animation_frame_step` 0x00413380 + `animation_draw` 0x0045D140), granary piles 0x004574C0, the gatehouse's
   `0x004E5730` (below), then `building_extra_draw` 0x0044F320 (stock pictures).
6. View-mode overlay of the building (overlay views only).
7. **Walkers**, three lists, each sorted by `tile_walkers_sort` 0x00449B30:
   - cell (r - 4, c) if the 5-row ring `0x0084787C` has bit 2 for it: its walkers not on water, layer 1;
   - cell (r - 2, c): its walkers of layer 2 (figure +0x1D set), or all of them (layers 3) when the ring has bit 1
     for that row; on a water-life/bridge tile only those not on water;
   - this cell (`tile_walkers_draw` 0x0045A5A0, layer 1): all its walkers, or only those on water when the tile's
     `0x0083AD6C` byte is set (that byte is ORed into the ring for this row, so the others come 2 or 4 rows later);
   - then `water_life_draw` 0x0041D3D0 (Poseidon bridge overlay; nothing in a Zeus game).
   A walker belongs to the tile in its record (the per-tile list `0x00D0D878` / +0x08 next_on_tile): it moves to the next tile after 8 of its 15 sub-steps
   (walkers.md "Position"), i.e. at the middle of a step.
   `walker_draw` 0x0044FEF0 draws a walker only when the call's `layers` has bit 1 (figure +0x1D == 0) or bit 2
   (+0x1D != 0). +0x1D is set by `fig_handler_wallguy` 0x004B9230 (wall sentries), `fig_handler_ballista`
   0x004BB7B0 (tower) and the shipwreck, cleared by `figure_fine_step` 0x004D94F0 and 0x004D7340/0x004D7580: the
   **lifted** figures, drawn after the objects of the cell below them.
   Sort inside a tile (`0x00449B30`, qsort by (rank, walker id)): rank -100 for figures not on the map (state
   +0x0E != 1 or action +0x38 == 4), -50 for type 6 kind 0x0D (the fishing-spot effect), else the walker's vertical offset in
   the tile (fine-position tables 0x005F06D8 / 0x005F0358 / 0x005F0558): back to front.

## 4. Pass 3 (0x0045A0B0..)
Anchors with terrain 0x08: the view object's overlay once more (overlay columns drawn over everything; city view:
nothing).

## 5. The "walkers drawn later" grid `0x0083AD6C` (`FUN_00448990`)
Recomputed on every turn (`FUN_004A1B70`) and after building or clearing (for the changed area). Per tile, in
turned coordinates (the per-view tables `0x005F84E0 / 8520 / 8560 / 85A0` and the local pairs all turn into the
same turned offsets; "ahead" = (+1, +1), the tile straight below on screen):
- **open(t)**: inside the map, not (terrain 0x10000000 without a building), not wall 0x4000, not deep water + road
  (0x4000040 both), and no building or a building of type roadblock 0x7B, corral 0x86 or race track 199.
- **higher_ahead(t)**: walking k = 0..15 tiles straight ahead from t (stop outside the play area or once
  elev(t) + k > 16): elev(t + (k+1)(1,1)) > elev(t) + k; or, for k = 0, t is not a cliff (0x200), the next tile
  is a cliff and elev(t) <= its elevation.
- value(t) = 0 (walkers drawn on their own cell) when t is not open or higher_ahead(t); otherwise:
  - a corral tile starts at 1 if the tile ahead is the same corral, else 0; a race-track tile is 2 or 0 by its
    route bit and stops there;
  - if any of the 3 tiles in front, turned (0,+1) (+1,0) (+1,+1), is not open: keep (0, or the corral's 1);
  - else if any of the 3 tiles of the second ring (+1,+2) (+2,+2) (+2,+1) is not open or higher_ahead: **1**;
  - else **2**.
- A bridge tile is forced to 1 while drawn (step 3 above). The map's edge lines are reset to 0 / capped at 1 at
  the end of the function (not ported).
Effect: a walker with nothing built in front of it is drawn 2 or 4 rows later than its tile, i.e. over the low
things just in front of it (roadblocks, corral fences, other walkers' tiles, raised-tile redraws); a walker with a
building or wall right in front is drawn on its own cell, so that building covers it.

## 6. Edge cases (exe)
- **Multi-tile buildings**: one picture at the left-corner cell; a walker on a tile behind the back edges
  (rows < anchor row) is covered, one on the same row to the right or in front is drawn over it.
- **Pieces**: what the exe builds as several anchors draws at each piece's own anchor: storehouse / trading post
  (1x1 root + bays), elite houses (four 2x2), stadium halves (5x5), gatehouse (2x2 towers + 1x1 passage pieces),
  dock (pier 2x2 + dock house), sanctuaries and monuments (parts, `composite_draw_extras`).
- **Gatehouse** `0x004E5730`, called at every anchor of the gatehouse after its top: draws slot 2 =
  SPR_GATE_OVERLAY (Zeus_General group 101, 775 + alt) at the slot-2 piece's tile point + (0, -0x48) or (7, -0x52)
  ((0x3A, -0x48) / (0x33, -0x52) mirrored in views 2/6) and slot 3 = the tower again (group 138 + alt). Since the
  last call wins, these two are drawn after the gatehouse's front-most anchor: a walker in the passage (a building
  tile, value 0, drawn on its own cell) is hidden under the arch; one on the road in front is drawn over it.
- **Walls, towers**: wall tiles are 1x1 objects at their cell (flags 0x4000 path of step 4); a wall tile is not
  open, so walkers in front of a wall are drawn on their own cell. Sentries (+0x1D) are drawn at row + 2.
- **Roadblock** (0x7B): pure ground. Its picture (Zeus_General 1150) is a 58x30 diamond with image +0x35 = 0, so
  pass 1 draws it whole, pass 2 step 1 treats type 0x7B like flat ground (redrawn only when raised) and step 4's
  `building_top_draw` returns at +0x35 = 0: every walker is drawn over it, whatever its 0x0083AD6C value (bugs.md
  203; oracle re/oracle/runs/roadblock-cart). Play mode: `Order.pass1` (a negative key, under every sorted picture).
- **Types 2, 9, 0x7B, 0x86 with a top**: base in pass 1, top at the anchor (step 4). The corral (0x86, picture
  with fences) is drawn that way (scene.js `placeSplit`); types 2 / 9 are not mapped in play mode yet.
- **Corral** (0x86): open; horses on it are deferred like any walker on open ground (the corral's own value rule
  above), so they stand over its fences in front of them.
- **Bridges**: piece at its cell (step 3); people on a bridge tile 2 rows later (over the deck pieces in front);
  boats (figure_on_water: types 0x14, 0x19, 0x23, 0x2C, 0x39, 0x3F, 0x40; type 6 kind 0x0D; 0x43-0x45 by cargo /
  tile) on their own cell, after the piece: over it (rendering in the Zeus game; Poseidon adds an overlay).
- **Raised terrain / cliffs**: rows ignore elevation (the picture is raised 30 px a step); raised ground is drawn
  again in pass 2 at its own cell (section 3.1), covering what stands behind it.
- **Docks / piers**: the pier (0x3C) and dock house (0x3D) are separate buildings with their own anchors.
- **Flying / lifted figures**: +0x1D figures (wall sentries, tower ballista) at row + 2; missiles are figures on
  their tile (drawn at their raised height).
- **Rotation**: everything above is in turned coordinates; the anchor corner, the grid `0x0083AD6C` (recomputed
  on a turn) and the ahead direction all turn with the view.

## 7. Play mode (viewer/play/order.js, 10-29)
One sort key per picture, `Order` in viewer/play/order.js; play.js sorts the frame's list by it alone
(`list.sort((a, b) => a[0] - b[0])`, stable, so pictures with the same key keep their push order, which is the
exe's order inside one step: a building's picture, then its loops, stock pictures, vendor, granary piles; a cart
under or over its pusher; a shadow before its arrow).
- key = ((a + b) * 512 + (a - b) + 256) * 8 + phase + sub, (a, b) = `viewXY` of the cell's tile: row, then column,
  then the step inside the cell: GROUND 0, OBJECT 1, DEFER4 2, DEFER2 3, WALKER 4 (section 3).
- `Order.obj(x, y, w, h)`: an object's footprint -> its left-corner cell (`viewFoot().lx/ly`), OBJECT. `place()`
  (scene.js) uses it by default, so every piece drawn with place() (house, building, storehouse bay, elite quadrant,
  stadium half, gatehouse piece, pier, corral, wall, garden stamp, avenue strip, roadblock) sorts at its own
  anchor; extras pass their building's key. monuments.js asks `ctx.order` (scene.js MCTX) per piece (flat pieces:
  GROUND of their cell); bridges.js `Order.cell(x, y, OBJECT)`; overlays.js columns at their building's key, the
  third-pass ones at `Order.LAST`; build.js ghost diamonds at `Order.LAST`.
- `Order.walker(fx, fy, {lifted, water, rank})` (scene.js `walkerSpot` passes it on): the tile is the rounded
  position; `Order.defer` is section 5 (computed lazily per tile, memo reset when T, S or the view changes);
  value 1 or a lifted figure -> cell (a+1, b+1) DEFER2; value 2 (not on water) -> (a+2, b+2) DEFER4; else own
  cell WALKER; sub = 0.5 + (offset below the tile centre) / 64. Lifted: wall sentries walking (look "walk" with a
  lift) and tower / wall sentries in their work anims (fight anim with a lift). Water: ships, boats, triremes;
  fishing / urchin spots rank -50. Followers (agora assistants), ox-train parts, company standards (military.js)
  and arrows each sort by their own spot.
- Gatehouse: pieces at their own anchors, then SPR_GATE_OVERLAY and the slot-3 tower again at the largest
  piece key (0x004E5730). Overlay offset checked on the oracle (re/oracle/runs/gate-walk/keep/v0_017.bmp: front
  passage 770 at (300,143), overlay 775 at (307,143) = +7, 0 as the formula; template scores 0.76 / 0.69, both
  partly covered).
- Ground (`Order.terrain` / `Order.terrainTop`, play.js buildTerrain; road and avenue tiles too, play.js flatGround:
  their picture is the tile's ground picture in the exe, bugs.md 427), in the exe's two parts: the BASE (the
  picture's lower 15n + 1 rows) in the terrain batch, or at GROUND of its cell when `Order.groundPass2` says pass 2
  step 1 draws it again (raised); the TOP of a picture with one (taller than its diamond, the proxy for +0x35: the
  upper h - (15n + 1) rows, `building_top_draw`'s) at OBJECT of its anchor cell. Both are cut from the one atlas
  picture (`subSprite`); since the top's rows include the diamond's upper half, the base pixels there are drawn
  with the top (at step 4, not in pass 1): the one deviation, invisible unless a walker of the tile behind reaches
  below that tile's middle line. On a building's tile (play.js `OCC`) no ground picture is sorted: only its
  diamond is drawn, first of all (key -2 - N*N, under the pass-1 keys; roadblock tiles the same), so a gap in a building picture shows ground, not black. A 1x1 top with
  none of terrain 0x2DFED66F is skipped while an immigrant, cart or horseman stands on one of the two tiles behind
  it (cells (r - 1, c -/+ 1), 0x00459192; the walker's tile must have 0x0083AD6C = 0; `Order.topHidden`, the
  walkers' tiles in `Order.big`, set by `Order.walker` with opts.big from scene.js; ox teams, enemy cavalry, gods,
  monsters and heroes are not marked yet). Both batches use the same texel tie bias (gl.js, 1/512) so the cut
  shows no seam at dpr 1.25. (10-29 first version: tops only when the ground redraw rule said so, which left trees
  in the batch and let rocks and raised ground behind them cut their crowns, bugs.md 177; second version: the whole
  picture sorted, also on building tiles, which painted the tufts under a building over it, bugs.md 185.)
- Overlay footprints (overlays.js, bugs.md 428): a flattened building's footprint pieces (0x0044B050) and, in See
  appeal, its slab tiles (0x0044B830 base + top) are drawn by ground_tile_draw from the building's anchor cell in pass 2
  step 1: GROUND of the anchor cell, the pieces back to front; See security's elite pad the same at its quadrant.
  Overlay tiles without a building (appeal slabs, wall and roadblock fills) are pass 1: the batch, back to front in
  the view. A building the overlay shows gets no slab or footprint at all (0x0044B050 returns when the overlay's +0x08 test
  shows it; ground_tile_draw draws nothing on a garden tile, terrain 0x20): bugs.md 443, the slabs of single gardens
  covered the front half of a garden stamp.
- Boats on a bridge tile: kept under the bridge (key of cell (a-1, b-1)), the deviation documented in
  docs/logic/bridges.md; the exe draws them over the deck.
- Replaced: walker +0.25 and the +0.3 bump beside a building behind (`walkerSpot`/`pieceBottom`), storehouse and
  trading-post pieces +0.35, gatehouse `archDepth` +0.45 / `gatePassage` -0.05, the corral at -6, sentries'
  `liftDepth` (+0.05 over the tile's building), roadblocks -0.4, agora strip -0.5, bridges +0.1, boats -1.5, stadium
  shows +0.01, monument ambient figures +0.1, standards +0.01/+0.02, arrows +0.5, overlay columns +0.01 / 1e6,
  ghost diamonds +1000, terrain -0.6, the x tiebreak of the sort.
- Not ported: the 0x40000000 redraw flag (frame-to-frame), the map-edge reset at the end of FUN_00448990, race
  track 199 and types 2 / 9, the walker rank -100
  (figures not on the map are not exported). Hypotheses: gardens count as terrain (not buildings) in the open
  test; agora stalls and avenues as buildings (avenues.md: building grid set on every avenue tile).

Frame time (drawFrame, CPU, headless Chrome 1280x800 at dpr 1.25, view 0, the default camera over the city, 960
frames each): before 1.15 ms median / 1.3 ms p90 (baseline copy); with the trees back in the sorted list (bugs.md
177) 1.1 ms / 1.3 ms (save H copy, the same city).

### Lifted figures and towers (bugs.md 178)
A +0x1D figure is drawn after the objects 2 rows down with no exception: confirmed on the exe's pixels by
re/oracle/scenarios/gate-walk-lifted.txt (every figure's +0x1D poked via tools/oracle_poke_lifted.py: the immigrant
cart that the plain run hides under the gatehouse arch is drawn over the arch and the front tower, 4 of 10 shots
differ, the rest are equal). So a wall sentry on the wall tile right behind a tower's back edge (save H (157,159)
behind tower (157,160) in view 0: its row + 2 = the tower's anchor row, one column to the right) is drawn over the
tower's front face in the exe too, as ours. The exe lets sentries stand only on wall tiles whose three tiles in front
(this view) are wall or tower (`grid_walls` 0x00587E50, rebuilt on a turn; 0x004CFEE0 moves sentries off the others);
our sim computes that grid for view 0 only (it never sees the view), so in views 2/4/6 our sentries can stand on
tiles the exe would have cleared (a sim deviation, not a draw-order one).

## 8. Check (tools/draw_order_check.mjs)
```
python3 -m sim live COPY.pkl --port 8797 --speed 30 &      # a COPY of a save, not a game in play
node tools/draw_order_check.mjs http://127.0.0.1:8797/play.html [--views 0,2,4,6] [--perf] [--shots DIR]
```
Node >= 22 (built-in WebSocket) and Google Chrome (or `CHROME=path`); tools/play_cdp.mjs starts its own headless,
muted Chrome with a temporary profile. The page is paused (togglePlay), then for each view: one frame of the city
and the whole map with every ground picture, and, for every roadblock, gatehouse, storehouse, trading post,
granary, tower, horse ranch and dock (up to 6 of each), test carts (wheat; every third a marble ox train) on every road step next to it, at 0, 1/4, 1/2 and 3/4 of
the step, both directions, and lifted wall sentries on every wall-top step next to each tower and gatehouse. For
every pair of placed pictures (walkers, ground bases and tops, buildings, pieces) whose screen boxes overlap, the captured
order must equal an independent reference: the exe's per-view grid formulas, the left-corner table, and a literal
port of FUN_00448990 with its per-view world tables (not order.js's turned offsets); every ground picture left in the
flat batch must be one the exe does not sort (no top, not raised); no ground picture may be sorted on a building's
tile; no 1x1 grass / scrub / meadow top may be drawn while an immigrant, cart or horseman stands on one of the two
tiles behind it (the reference takes those from FUN_00448990's per-view front tables). Plus: a non-lifted walker on a gatehouse tile
must be under the arch overlay; a walker overlapping a roadblock must be over it (counted). `--live S` then lets the
city run S seconds per view and checks every sampled whole-map frame with the city's own walkers at their real
positions (`--live-out DIR` keeps the walker/roadblock overlaps as JSON). Exit 1 on
any difference (the count = out-of-order pairs of the city frames + scenario frames with any). It catches the bug
families above: with `Order.defer` forced to 0 it reports 49 problems in view 0; with objects keyed at their
bottom tile (the old rule), 62; with trees' tops left to the ground rule (bugs.md 177), 6117 ground pictures
wrongly flat in view 0 of a new sandbox; with the building-tile rule removed (bugs.md 185), 25 (city) / 76 (whole
map) ground pictures on building tiles in view 0 of save H; with the cart rule removed, 4 tops over carts.
Results 10-29 (baseline copy, all 4 views): 0 out of order in every frame (city and 96 scenario frames per view,
~400-900 overlapping pairs each); gatehouse arch 116-122/116-122 per view; carts over a roadblock 610-711,
under it 44-126 per view (all on tiles with a building in front, e.g. (143,55) beside a boulevard; called "as the
exe" then, wrong: the exe draws no walker under a roadblock, bugs.md 203). a save copy: the same, 0 out of order in 420 frames (roadblocks, gatehouses,
storehouses, trading posts, granaries, towers, ranch, dock), carts over roadblocks 552-658, under 46-100 per view
(a bug, see bugs.md 203: since then 0 under, and the check counts any as a problem).
Real walkers (bugs.md 203, `--live 40`, save H copy): old code 197-270 walker/roadblock overlaps per view with the
walker under the roadblock, now 0 (1437-2160 over), every sampled frame of the whole map otherwise in order.

Looked at (screenshots of a copy, old code from a worktree on another port vs new, dpr 1.25, 100 %, 4 views): a
single cart through roadblock (137,167) both ways and (148,119): old drew the roadblock post over the pusher's leg
as it stepped off toward the back, new draws the cart over it in every frame; palace with company standards
(standards behind the palace building now covered by it, as in oracle runs/palace/c.bmp and rotation-palace/p2.bmp
where only the front ones show over it; old drew the back ones over the roof); both gatehouses (arch over walkers in
the passage, as gate-walk keep shots); storehouse (145,108) beside the granary (its root arch, in front of the
granary, now drawn over it; old hid it); granary; towers with sentries; horse ranch and corral (horses over the
fences in front of them); Apollo and Athena sanctuaries; villa; agora; avenue and boulevard; theatre; cliffs at
(101,168) and the marble quarry; the dock (save H). Not checked: stadium and bridges (none in either save; the
bridge key path is covered by the reference only), zoom 200 %, pixel seams (the change moves no picture, only
the order). Trees (bugs.md 177): oracle runs/rotation-cliffs/c0.bmp (sandbox, trees among rocks) vs play mode on a new
sandbox at the same camera, map area within 8 per channel: 89.4 % now, 85.6 % with the first 10-29 rule, 88.9 % with
the old -0.6 rule; trees in front of rocks are whole as in the shot. save H copy, rocks by the forest at (120,185),
(109,200), (147,42), 4 views: the crowns the first rule cut are whole. Check on save H with ground pairs and sentries:
0 out of order in all 4 views (~21,000 ground pairs per view on the whole map).
Buildings on scrub (bugs.md 185): re/oracle/scenarios/scrub-granary.txt (a granary built on a scrub plain of the
sandbox) vs play mode on a new sandbox with the same granary (`tools/oracle_view_compare.py`): map area 97.2 % within
8 per channel, granary box (200,340)-(460,440) 99.7 %; the 177 rule (whole tops, also on building tiles) 94.5 % /
71.4 %. rotation-cliffs c0a with this rule: 89.5 %. Check on a save H copy, every pair: 0 problems in all 4 views
(~5,700-6,200 pairs per city frame, ~19,600-19,900 on the whole map). drawFrame 1.4 ms median / 1.7 ms p90 (save H
copy, view 0). Looked at, 4 views: granary (144,116) and its storehouse/farm/house neighbours, storehouse bays at
(136,147) and the armory/storehouse area (138,180) at 200 %; palace, Athena and Apollo sanctuaries, gatehouse and
towers, villas, grand agora, avenues, dock and wharves, horse ranch, stadium, cliffs and rocks (101,168) at 100 %.
Not checked: bridges (none in save H).
