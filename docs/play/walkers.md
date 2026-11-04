# Walker sprites in play mode (research 2026-10-27)

Data: `data/play/walkers.json` (generated; 51 roles). Sprite refs = atlas index of `file`
(`extracted/sprites/<file>/atlas.json`). Almost everything is in `SprMain`; Poseidon figures in
`PoseidonImps`, the donkey in `SprAmbient`.

## How the original picks the sprite
Sources: `walker_draw` 0x0044FEF0, the per-type handlers (image code at their end), the figure type
table 0x00639698 (+0x1C walk group, +0x20 second group, +0x24 die group; value = `collection*512 +
group number`, collection 51 = SprMain, 53 = PoseidonImps, 16 = SprAmbient, group number n = atlas
group id n-1), eZeus `echaractertextures*.cpp` (starts agree with the exe).

- **Direction**: `d = direction (0..7); if direction >= 8 use prev_direction` (so a standing walker
  keeps its last heading), minus the camera rotation, mod 8. Codes: 0 = tile (0,-1), 1 = (+1,-1),
  2 = (+1,0), 3 = (+1,+1), 4 = (0,+1), 5 = (-1,+1), 6 = (-1,0), 7 = (-1,-1). With our projection
  ((x-y)*30, (x+y)*15) these are screen NE, E, SE, S, SW, W, NW, N. The sprite order inside a group
  is the same, so `dir` indexes the sprites directly. Verified on the peddler (cart ahead of the pusher).
- **Frame**: `sprite = group_first + anim_frame*8 + d` (frame-major). `anim_frame` is +1 per sim tick
  in the handler, wraps at 12 (walk groups = 96 images = 12 frames), whether or not the walker moved
  that tick (speed codes only change sub-steps, not animation). Standing/waiting handlers set it to 0.
  Work groups (chop, mine, ...) count frames the same way with their own length (80 = 10 frames,
  320 = 40 frames); groups with 8 or 12 images and `dirs:1` are direction-less sequences.
  Play mode (bug 393, 11-02): a moving walker's frame is +1 a tick wrapped at the drawn block's own `frames` (= the
  group's first image's anim_frames, the .sg3 +0x1E that sprite_anim_step 0x005AF8C0 / FUN_005AF5F0 wrap at): 12 for
  SprMain walkers, 15 / 17 / 18 / 11 for Persian, Amazon, Centaur, Ares-warrior invaders, 17..28 for gods (was tick
  % 12 for all). Dying: min(timer (or timer / 2), frames - 1) for every role (was capped at 7 but for monsters /
  heroes). Kept as the exe has them though the group is longer: growers' tend / pick wrap at 10 (figure_grower
  0x004AECF0, orange groups hold 12), the diver's dive chain. `python3 tools/walker_frames_audit.py` lists every
  block whose frames differ from the sprite data (left: those 4 as the exe, the trireme crew's still layer).
- **Mirroring**: the original stores only dirs 0-3 and 7 and mirrors 4,5,6 (= 2,1,0). The extracted
  PNGs of mirrored indices are already flipped (atlas `mirror_of` is informational), so no flip logic.
- **Die**: direction-less 8-image group, `frame = min(timer, n-1)`, timer +1 per tick, walker removed at
  127. **Fight**: second group (e.g. hoplite 7209, 8 frames x 8 dirs), `frame = attack_timer`.
- **Position**: fine position inside the tile: `tile_progress` p (0..14 = steps in the tile, 15 = on the
  centre). Screen offset from the diamond centre of the walker's *current* tile (the tile changes after
  8 sub-steps): `off = T[d][p]` (pixels; table dumped from 0x005F0658/0x005F06D8). For p<=7 the walker is
  still on the old tile and offset points towards the new one: orthogonal-on-screen dirs (E, W) move 4 px
  per step in x; NE/SE/SW/NW move (+-2, +-1) per step; S/N move (0, +-2). p=8..14 offset starts at minus
  the remainder. Equivalent and simpler: interpolate linearly from the old tile centre to the new tile
  centre over 15 sub-steps (the tables are exactly that, with the 2 px rounding of tile width 60 vs 58).
  Elevation: y -= 30*altitude. Sprite top-left = position - (anchor_x, anchor_y).
  **Picture point** (10-30, bugs.md 251; walker_draw 0x0044FEF0): the tile's draw point + (29, 15) (map_view_set_size
  0x00449E50: half the 58 x 30 tile) + the walk table [view dir][tile progress] + (2, rise) - slope_offset, rise 10
  except: types 1, 0xB, 0xC, 0xD, 0x28, 0x29, 0x2A, 0x37, 0x3B (immigrant, rabble, hoplite, horseman, enemy archer /
  infantry / cavalry, woodcutter, wolf): the previous tile's road bit (terrain 0x40) against +0x41 (the current
  tile's, set on entering it by FUN_004D7580): both road 17, both not 5, else ROAD_T[p] + 10 coming from a field tile,
  ROAD_T[15 - p] + 10 from a road (ROAD_T = 1 2 3 3 4 5 6 7 -5 -5 -4 -3 -2 -1 -1 0: a smooth 12 px change over one
  step); a quarried marble tile (0x20000) adds 8 (regrowth 0, deep) or 4 (100, shallow); types 6 (effect subtypes
  0x12 / 0x0D) and 0x3A (artisan) the monument height (pyramid_figure_height) + 10. Line moves (+0x0C: ships, arrows)
  use the fine-position tables 0x005F0258.. per view, + (2, 10) - line_counter (a missile's starts at 10, -1 a fine
  unit). Extra pictures (sprite_extra) hang from the plain point (the picture point - (2, 10)): carts 4/9/0x1C/0x24
  (and 0x43/0x45) + (+0x6C, +0x6D) (the light table), under the figure except facing S; types 1/2/0xD/0x2A at the main
  picture's top-left + (+0x6C, +0x6D) (no anchor); 0x2D/0x34/0x36 (missiles) the extra first at the main's top-left
  + (0, 10); a trireme (0x39) its +0x150 picture (the crew, PoseidonImps group_133 = packed 0x6A86) at the plain point
  + (1, 0). Ours: scene.js figureSpot (walkerSpot = the plain point) and roadRise (the previous tile from the walker's
  own step history). Checked: tools/e1_figure_check.py on oracle run 1E-figs (re/oracle/scenarios/1E-figs.txt: 5
  camera spots, dumps every tick; the shot's tick = the dump whose figures match best) and 1D-walker: every figure
  found in the shots (sheep, goats, shepherds, milkers, growers, horses, carts and cargo, ox pairs, woodcutters at rise
  7 / 11 / 17, miners, artisans' fronts) has its picture at the rule, none elsewhere within 16 px; play mode: the
  walker-window crop of a cart = the exe's pusher 0 of 240 px (tools/walker_crop_check.mjs, WALKER_EXE now [0, 0]).
  Not ported: the walk table is one count ahead of linear interpolation (4(p + 1) px for p <= 13: ours draws the
  step linearly over the sim's step time).
- **Lift on ramps** (10-29/30, bugs.md 211): figure +0x77/+0x78/+0x79 slope timer/offset/target, set on entering a
  tile (FUN_004D7580), stepped by figure_fine_step 0x004D94F0 (1 px a fine step, 1 more on a ramp tile 0x10000400;
  the step that ends the timer changes nothing; with the timer at 0 the offset drops 1 a step), drawn y - slope_offset
  (walker_draw). The tile changes at step count 8 of 15 (+0x39). Movers: figure_route_walk 0x004D7BD0 changes the
  tile, then steps (one slope step done on entry); figure_roam_steps 0x004D69B0 / FUN_004D7110 (roamers, wanderers,
  most vendor assistants) step, then change (none); FUN_004D7340 (followers: ox pairs, trailers) changes, then moves
  the offset 1 px a tick. The "next" tile is the route's next step (route[route_step]); a roamer's or an ended
  route's: its own direction. Single ramp (timer 15): up 2 min(n, 14), down 30 - 2 min(n, 14) (n = steps since
  entry); long ramp (0x400 + 0x800000, two low tiles, timer 30, decided on the pair's first tile by the tile 2 ahead):
  up min(35, 2 min(K, 29)), down max(0, 35 - 2 min(K, 29)); any other tile 0. scene.js `rampLift(fx, fy, dir, mode,
  next)`: mode 1 for a roaming walker, next from the route's next tile (frame step record [4..6], sim/live.py).
  Checked: tools/e1_ramp_check.py on re/oracle/runs/e1-ramps (scenarios/e1-ramps.txt, every tick): drawn lift
  (elevation * 30 + offset) equal for 743 of 743 samples that kept their heading (types 4, 8, 9, 30, 37, 47, 65);
  168 of 236 after a turn within 30 ticks with the straight-walk formula; 10-30: route walkers and roamers replay the
  exe's state machine over their own last 6 tiles (scene.js rampPath / rampReplay: FUN_004D7580 on each entry with the
  real previous tile, figure_fine_step per count, a long-ramp run's pairs counted from its start): 743 / 743 straight,
  217 of 236 after turns (left: 12 samples 2 px off where a route walker turns on a ramp, 7 of a buyer on (119, 105)). Exe pixels (scenarios/e1-ramp-shots.txt): a cart on the long ramp at (115,116) moves 2 px right and
  1 px up a tick for 9 ticks (flat: 1 down), its offset +2 a tick. Ox pairs (mode 2, oracle 1F-ox,
  scenarios/ox-ramp.txt): up the long ramp (134..133, 113) 1 px a count from the pair's first tile, group_5 while the
  timer 30 runs, also after a turn on the second tile (the run counts on: scene.js followerRun along the trail walked;
  bugs.md 284); e1_ramp_check: lifts 49/49, slope pictures 28/28; the shots 1.000 at the rule.
- **Draw order**: docs/play/draw-order.md (exe city_draw: a walker's cell, or 2 / 4 rows later by the
  0x0083AD6C grid; lifted figures 2 rows later; back to front inside a tile). Two-sprite walkers: see carts.
- **Shadow**: pure red (255,0,0) pixels in the PNGs. Not verified in the exe blitter; draw as ~40% black.
- **Carts** (types 4, 9, 28, 36): pusher group 4729 as `sprite`; `sprite_extra` = cart overlay of the
  carried good, `cart_group_first + level*8 + d`, drawn at position + `offsets[d]`
  (light table 0x006380AC: (19,4) (30,15) (22,26) (2,28) (-16,24) (-26,15) (-18,5) (4,-3), anchors applied
  like any sprite). Order: cart under the pusher for every dir except S (3), where it is over. Empty
  (amount 0) = group 8428. Level from units: <=200 -> 0, <=400 -> 1, else 2 (1 load = 100 units).
  Heavy goods (wood, marble, sculpture, black marble): in the exe separate figures follow the cart one
  tile apart (cart_spawn_helpers 0x004ADF30): the cart = driver in front, then 1-4 FIG_OXCART (28) ox pairs
  (loads - 1 clamped 0..3, + 1; marble with >= 4 loads: 1; figure_oxcart 0x004C3680 action 6: packed 0x6605
  = SprMain atlas group_4, start 209; slopes 0x6606/0x6607 = group_5 305 / group_6 401 (0x6606 when
  slope_target != 0); dying 0x6608 = group_7 497, 8 frames), then a FIG_OXCART trailer (action 7, cargo picture).
  Slope state (0x004D7580, on entering a tile; shown while slope_timer runs, ~1 tile): on a tile with 0x400 (ramp)
  or 0x10000000, current elevation < previous tile's -> down (target 0, group_6), < next tile's -> up (group_5);
  with 0x400 + 0x800000 the "next" tile is 2 ahead (0x004D78ED) and a lower neighbour also turns it on. Ours:
  scene.js oxSlope per ox pair from T.flags/T.elev and its heading on the trail (walkers.json `slopes`).
  The follow (0x004D7340) keeps a follower 12/15 of a tile (oxen) or 13/15 (trailer) behind its leader
  along the leader's path; the trailer is the figure's extra picture at (0, +17) from the plain position
  (a walker's picture is at (+2, +10)), level by load (FUN_004AD760: <= 200 units 0, <= 400 1, else 2).
  Ours draws them on the cart's trail at those distances (scene.js trailOf/trailSpot), each sorted by its
  own spot (a trail seen shorter than that, after a reload or before the cart moved: straight back past its
  oldest point, ours; bugs.md 387). The stonecutter's marble cart (sim state follow) steps when he does: the frame
  gives it his step's ticks (sim/live.py _walker_step), else it crossed a tile in one tick and its followers
  swung back and forth every tick (bugs.md 387). Trailer at figureSpot + (-2, +7) = the plain point + (0, 17); ox pairs at 1E-figs' rule (0.995); driver
  1337 (FUN_004ADBA0: the leader figure draws packed 0x6613 = atlas group_18, `first + anim_frame*8 + dir`,
  and 0x6614 = group_19, the 8-frame fall, when dying: packed n = atlas group n-1 as for every figure), trailer 2999/3015/3031 (Poseidon
  1027) level 0. The heavy offset table 0x0063809C is computed for the cart but its sprite_extra is cleared
  for heavy goods (bugs.md 105, 111).
- **Ships**: 16 headings per frame; exe uses `group_first + 1 + 2*(d + 8*(anim_frame/3))`.

## Followers: the agora buyer's assistants (2026-10-28)
Original: at the storage the buyer (FIG_AGORAVENDOR 37) spawns one FIG_VENDOR_ASSISTANT (47) per load
taken (`buyer_take_food` 0x004CF570, up to 8 food / 4 goods), chained by leader `+0x68` (each follows
the one ahead); they walk home behind her and each adds 100 to the agora on arrival (handler 0x004BBD60).
So she walks out alone and comes back with a file of children carrying sacks. Sprites (figure table
0x00639698 row 47; handler image code): SprMain group 17 (start 1233, walk 12x8; die 1329) for every
good except horses (slot 15: group 96 = the horse walk 5001, role `horse`); chariots (slot 19) other code, not mapped.
Ours: the sim keeps the loads on the buyer (no figures). The live frame's walker entry has a 7th field,
the follower count (`sim/export.followers`: stall buyers only, amount/100, max 8). `walkers.json`
`buyer.followers` names the follower role; `scene.js drawFollowers` remembers the tiles the buyer walked
since she picked up the loads and draws follower j on the tile j steps back (stacked at the storage until
the path is long enough), interpolated with her step. Presentation only.

## Growers (FIG_GROWER 5, 2026-10-28, play-mode bug 63)
Exe: `figure_grower` 0x004AECF0 (image code at its end; group = table offset / 8, 0-based like `group_N`).
The set is chosen by the grower's tree (`Figure+0x40`, trade_building), not by what it carries:
orange tree 0xD9 -> PoseidonImps; olive tree 0x24 (and composite / types 100..114) -> the olive groups; else grapes.
| action | what | SprMain group (start) | oranges (PoseidonImps) |
|---|---|---|---|
| 7 / 9 / 0xB / 0xD (walk out, back, home with the fruit) | walk, 12 frames x 8 dirs | 103 (5505) | 28 (1211) |
| 8 tend, timer 0xCC = 204 ticks (`grower_tend_done` 0x004AB6F0) | 10 frames x 8 dirs | 105 grapes (5609), 106 olives (5689) | 30 (1315; 96 images, 10 used) |
| 0xC pick, timer 0xCC (`grower_pick_done` 0x004AB830) | 10 frames x 8 dirs | 107 grapes (5769), 108 olives (5849) | 31 (1411) |
| 4 die | 8 frames | 104 (5601) | 29 (1307) |
Frame = `anim_frame`, +1 per tick, wraps at 10 (work) / 12 (walk); sprite = start + frame*8 + dir.
There is **no carry sprite**: walking home (0xD) uses the walk group. The pick sprite has the pole and the
fruit/leaf bits on the ground drawn into it (no separate effect sprite). Position: the destination is the
tree tile itself (`grower_next_ripe_tree` 0x004AB770 / `grower_next_tree_to_tend` 0x004AB640 set dest =
tree x,y; the work starts on arrival, direction code 8), so the grower stands on the tree tile centre,
heading = prev_direction (its last step). Actions 6 / 10 (choosing the next tree) are hidden, one tick.
Bug 63: walkers.json had 107/108 as `carry`, so a grower walking home with olives was drawn picking
(the leaf bits around walking growers), with walk frame timing; working growers were drawn as walk frame 0.
Ours: `sim/export.grower_look` puts in walker [7] either `["work", t0, end, face dx, dy, 0,0,0, "tend_olives"|"pick_grapes"|..., false]`
(face = towards the target tree, 0 when on it, so the client keeps the last step's heading) or
`["tree", 0,..., fruit, false]`; scene.js uses `trees[fruit]` (oranges: walk/die from PoseidonImps) and
draws "work" through drawFight's work branch (1 frame per tick). The grower is drawn on its own sim tile:
ours may stand next to the tree rather than on it (sim passability, not graphics). Sim `work_ticks` is 100
vs the exe's 204 (sim number, left alone).

## Water life: fishing and urchin spots (2026-10-29, play-mode bug 170)
- Exe: at map start (FUN_004E0D80, editor_mode == 0; again by FUN_00510DC0) each fishing point of the scenario
  block (docs/logic/map-terrain.md, 8 slots; 6 on the sandbox) gets an effect figure: FUN_00412B60 ->
  FUN_004104D0(0x0D, x, y, 8, 8) = figure_create(1, type 6, x, y, 0, 0) with effect subtype 0x0D; urchin points
  (FUN_00412C60) subtype 0x13. Figure +1 = rng & 0x1F (start counter).
- Type 6 handler 0x004AF530 -> 0x00410670 -> 0x00410E50 (every tick, walkers_update): switch on the subtype
  (jump table 0x004117E8, cases 0x0D and 0x13 at 0x0041144D): picture group 0x2010 (fish, SprAmbient group_15,
  index 453, 40 frames) or 0x205C (urchins, index 3035, 16 frames); counter +1 a tick, back to 0 at 3 * frames,
  frame = counter / 3. walker_draw 0x0044FEF0: never mirrored (flag from +0x16E, 0 here).
- Position (oracle re/oracle/scenarios/water.txt, new sandbox, views 0/2/4/6 via PgUp; the exe camera as
  rotation.md): the fish at logical (70,101) = raw (71,102) draws at the walker spot of raw (x + 8/15, y + 8/15)
  + (2, -20) px (fitted as logical + 23/15 before 1J converted the points to raw; the same pixels) in all
  four views (v0 (331,236), v2 (213,295), v4 (271,354), v6 (449,325)). Read back in play mode at the exe camera
  (dpr 1.25, frame forced to the shot's): 51 of 51 sampled fish pixels equal (each channel within 8).
- Ours: data/play/walkers.json `water_life` (tools/play_water_life.py), points from the map (sim world
  `fishing_spots`, `urchin_spots` -> /terrain.json `fishing`, `urchins`), scene.js sceneWaterLife; frame from the
  game tick (P.t) + tileRand(x, y) % 32, so it stops when the game is paused (as the exe's figure).
  Not ported: anything that removes or moves them (FUN_00510DC0's callers not read). Saves made before 10-29
  have no `urchin_spots` (none on the sandbox maps).

## Games contestants (FIG 0x38, 2026-10-29, play-mode bug 198)
`re/venv/bin/python tools/play_contestants.py` writes the `contestant` role (by good = the sending building's key,
w.task) and `contestant_philosopher/athlete/competitor/actor` (fig_handler_contestant 0x004C30D0: 0x66F1 college and
podium, 0x66D7 gymnasium, 0x66D9 stadium, else 0x6603; die = group + 1). Waiting ones are hidden (export "hidden").
Check: `node tools/contestants_check.mjs http://127.0.0.1:PORT/play.html DIR` on a live COPY with contestants out.

## Ore miner's pause (2026-11-02)
figure_miner 0x004C1310: after mining (action 8) an ore miner stands 25 ticks in action 0xD (timer 0 at the change,
+1 a tick, past 0x18 action 9 home). Picture: group first + timer / 2, no direction: copper SprMain group 44 (2699),
silver group 77 (3845), orichalc PoseidonImps group 35 (not in ours: no orichalc miner art yet). Frames 0..12; the
groups hold 12 pictures, so timer 24 shows the next group's first (the carry set's): kept. Ours: data/play/walkers.json
roles.miner.work.pause / pause_silver (tools/play_miner_pause.py; "clamp" 12, 2 ticks a frame); the sim's look
["work", start, end, 0, 0, ..., "pause"] (sim/export.gatherer_look; was the walk set standing).

## Role table
| role | original figure | file / start (walk) |
|---|---|---|
| immigrant | FIG_IMMIGRANT 1 (family with cart; eZeus also randomly 505) | SprMain 1793 |
| emigrant | FIG_EMMIGRANT 2 | SprMain 505 |
| cart | FIG_CART 4 / storehouseman 9 / deliveryman 36 | SprMain 4729 + overlays 8428.. |
| buyer | FIG_AGORAVENDOR 37, vendor by good | 2887 food, 1897 fleece, 5297 oil, 5401 wine, 2105 arms, 1129 horses; else cart |
| peddler | FIG_PEDDLER 26 | 1 |
| water | FIG_WATERBEARER 60 | 6737 |
| healer | FIG_HEALER 32 | 7473 |
| philosophy / athletics / drama / competition | types 16 / 17 / 18 / 15 | 12128 / 10588 / 105 / 10692 |
| maintenance | FIG_SUPERINTENDENT 8 (eZeus firefighter) | 609 (fire work 809) |
| watchman | FIG_WATCHMAN 61 | 2209 (fight 2313) |
| tax | FIG_CLERK 7 | 4625 |
| trainee | the venue's own figure (no separate sprite) | by `good` |
| artisan | FIG_ARTISAN 58 | 1545 (build 1649) |
| woodcutter | FIG_WOODCUTTER 55 | 4329 (chop 4433, carry 4529) |
| stonecutter | marble miner | 11044 (cut 11148) |
| miner | FIG_MINER 62 | bronze 2595, silver 3741 |
| shepherd / goatherd | FIG_SHEARER 30 / FIG_MILKER 31 | 3415 / 2377 |
| grower | FIG_GROWER 5 | 5505 (tend 5609/5689, pick 5769/5849; oranges PoseidonImps 1211, see Growers) |
| hunter | FIG_HUNTER 53 | 11820 (shoot 11924 group 237, butcher 12020 group 238 frame = tick, carry 12032; boar: walk 10124, die/carcass 10220 group 207, passive "stand" 10292 group 209; bugs.md 132) |
| rancher | FIG_RANCHER 77 | PoseidonImps 2186 |
| diver | FIG_URCHIN_COLLECTOR 44 | 9508 (at the mooring: 7 group_200 9604, 8 x5 group_201 9700, 9 group_202 9796 to frame 8, looped; tools/play_diver.py) |
| trader / donkey | FIG_CARAVAN 19 / FIG_VAN_FOLLOWER 21 | 5929 / SprAmbient 529 |
| ship / boat / trireme | types 20 / 25 / 57 | 10420 / 10796 / 6569 |
| sheep, goat, cattle, horse, boar, deer, wolf | 49, 50, 76, 43, 51, -, 59 | 3183 (shorn 7873), 11228, P 2290/2490/2690, 5001, 10124, P 531, 11524 |
| thief, vandal, mugger, disgruntled | 23, 29, 27, 22 (one shared set) | 6033 |
| plagued | FIG_PLAGUE_DUDE 66 | 12232 |
| rabble / hoplite / horseman | 11 / 12 / 13 | 6841 / 7105 / 7273 |

## Verified / uncertain
Verified visually (frame 0, 8 dirs, contact sheets): every walk group above except ships (checked the
16-heading ring) and the fire/work groups. Uncertain: the walk group of `rancher` (inferred from the
die group), the ox position of heavy trains, which carried
sprite eZeus names "carry" vs "collect" for grower/hunter/maintenance (names from eZeus, not
checked frame by frame), the fishing-boat swim frame rate, sheep/goat fight and lay-down groups, and
the shadow colour treatment. `deer` and `bull` are Poseidon-only and come from eZeus, not the exe table.

## Effect figures: dust, splashes, spray (2026-10-31, bug 362)
- Exe: type-6 figures made by FUN_004104D0 only when their spot is on screen, deleted off screen every 16 ticks
  (FUN_004106A0's tail), so they are pictures, not game state. Tick: fig_handler_ambient 0x004AF530 -> FUN_004106A0
  (motion: fine x/y 0..0x77 a tile with velocities +8/+9, height +6 with vertical speed +0xA, gravity -4 with flag 8;
  subtype 0 figure_line_move(fig, +0x59)) -> FUN_00410E50 (picture: packed group + variant byte, frame = counter /
  ticks per frame, dead at ticks * frames). Groups (packed 0x22NN = "destruction" atlas group NN - 1):
  0 debris 0x220A / 0x2201..0x2204 by +0x15C = rng % 5, 9 frames, +0x59 = (rng & 3) + 1 ticks; 1 lava splash
  0x220B + rng % 6 (18 18 17 19 17 19 frames, 1 tick); 2 0x2211 + rng & 3 (12 13 15 15); 5 0x2215 + v; 7
  0x2205..0x2209 (8 frames); 0x0D / 0x13 fish / urchins ("Water life").
- collapse_debris_spawn 0x004CCD40 (debris): size 1: each corner (0,0) (1,0) (1,1) (0,1) of the tile x the
  directions (0,1) (1,0) (1,1) (tables 0x00639110 / 0x00639118): a figure on the tile moving to tile + sign * dir *
  (rng & 3); size > 1: each tile of the area with rng & 3 == 0 gets the size-1 spawn, none -> one random tile.
  Called by building_destroyed_by_attack (size = the building's), the earthquake's node, the landslide's
  FUN_00505B50 per changed tile, figure subtype 0x15's landing, ...
- Ours: the sim reports the call (sim/effects.py `debris`, frame `fx` [tick, kind, x, y, size], live only: no state,
  no RNG; hashes unchanged) from disasters._destroy, quake_crack and the landslide; viewer/play/effects.js makes
  the figures with Math.random and the exe's tables, data/play/walkers.json `effects` (tools/play_effects.py).
  Movement: +0x59 sub-steps (of 15) a tick towards dest (hypothesis; the line mover's step table not read).
  Checked against oracle 1L5-dis-econ2-taenarum-slide m275 / m277 / m279 (camera (102, 234), dpr 1.25, ours 5, 9,
  22 ticks after the slide): the same clouds, sizes, colours and fading; ours reaches 1..2 tiles further up-right
  over the higher plateau (bugs.md 362).
- The disasters' post step (11-01, bugs.md 362; disaster_post_step 0x00447790 every tick in states 2..5, segment /
  node vtables read from the exe, the rest by Ghidra DecompAt; full notes in sim/disasters `post_step`): p = count *
  100 / calls-per-ring (20; tidal 5), in state 5 max(0, 99 - p). Lava: the current ring's FUN_00506F40 visits
  max(n, (rng & 7) + 15) nodes from a random one (wrapping), each not an edge node or on lava -> FUN_00411920
  (subtype 1 "lava": 0x220B + rng % 6, 17..19 frames of 1 tick, standing, height 10, fine spot from p along the
  node's direction: base / range by DIRS8 0x005D8408, v = (rng % range + base) * 0.14); a random lower ring ->
  FUN_00411BE0 (subtype 2 "drops": 0x2211 + rng & 3, 12/13/15/15 frames, from the middle, height 4, drifting by
  the sin/cos tables of FUN_00410430 at speed 0 / 1); ring 0 -> FUN_00411DD0 (subtype 3, a ballistic blob the effect
  handler deletes on its first update: case 3 has 0 frames, flags 9 without 0x20; never seen, not reported); the
  edge list with p = 110. Tidal wave: FUN_004E4480 visits (rng & 3) + 4 nodes (n if fewer; all n at count 1 in state
  2 when the first is a seed), each not an edge node or on water -> FUN_00412080 (subtype 4 "spray": standing,
  height 10, counter 1..9 in 0x2236, 10..19 in 0x2238). Earthquake: quake_segment_dust's node call 0x0056D2F0 only
  reads the getter 0x0056DE80 and the other two call no-ops: the quake shows only the crack dust (as original).
  FUN_004104D0 makes an effect only within 200 px of the view and while fewer than 750 live; FUN_004106A0 drops
  those that left the view (every 16 ticks). Ours: the sim reports each call (`fx` [tick, kind, x, y, a, b, c]) with
  a local generator (tick, object), play mode draws them (effects.js: spawned when the shown time reaches them,
  screen test and the 750 cap, the dead pruned first), line_counter = height / 8 + 30 px up (so 10 / 4 px above the
  debris). Checks: `python3 tools/oracle_disaster.py effects odyssey3 25` (live type-6 figures per 4-tick dump vs
  ours: within ~10 % through flood and retreat; econ2-marathon ours ~30 % more: its region is wider than the
  exe's screen and the count has no screen test); lava oracle run 1L5-dis-europa4-fx (camera on the point, dumps
  every 4 ticks 4560..4700): the exe holds ~705 effect figures (the cap), counters 1..18 evenly, on 75 tiles; ours'
  splash tiles over the same 18 ticks: 64 of 68 the exe's; play mode (tools/effects_check.mjs, dpr 1.25) vs shot
  m060: the same bright clusters along the front.
- Dust for attacks (11-01): building_destroyed_by_attack 0x004928C0's collapse_debris_spawn is reported for
  invaders (military/invaders.destroy: the building, or (x, y, 1) for a wall tile), monsters (destroy_tile, a
  monument piece's own spot and size) and gods (a bolt's building, Zeus' palace). Not ported: a ship hit (figure_hit
  size 0), the 0x43 missile (walker_player_missile), a wall hit by figure_check_next_tile at the attacker's tile.
  Fire: buildings burning down have no debris call in the exe (as original).
