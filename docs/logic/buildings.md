# Buildings: records, types, placement, lifecycle, road access, fire and collapse

Status: **verified** from the exe unless marked. Addresses refer to GOG `Zeus.exe`.
Names: `re/names/map-buildings.tsv`; fields: `re/structs/map-buildings.tsv`; per-type static
data: `extracted/model/building_sizes.json`. Desirability: [desirability.md](desirability.md);
grids and terrain bits: [map-terrain.md](map-terrain.md).

## Summary
Buildings live in `g_buildings[4000]` (`0x0092E658`, 280 bytes, id 0 unused, sav rank 35). The
type id (`+0x10`) is the BUILD_* row of the model file (0..220); a static per-type table gives
the footprint size. Players place buildings with the build tool (cost = model column 0); the
record is created in state 3 and becomes active (1) at cycle step 40. Every 51 ticks the game
checks road access (step 21), adds collapse ("damage") and fire risk (step 44), and burns
buildings already on fire (step 43). Risk above 999 / ≥ 1000 triggers a fire or a collapse.

## 1. Record fields (this subsystem; others in docs/re/structs.md)
| Off | Type | Name | Evidence | Status |
|---|---|---|---|---|
| +0x00 | u8 | state: 0 free, 1 active, 2 removed (no road / evicted), 3 just created, 4 destroyed (collapse, burnt, blocked path), 5 removed without footprint clear, 6 demolished by player | creation, step 40 `0x00484030`, `0x0049A460`, step 43/44 | verified |
| +0x01 | u8 | 1 at creation; passed as first arg of `figure_create` by miners | `0x00493E70`, `0x0048CFB0` | verified (write) |
| +0x03 | u8 | size (type table +0) | `0x00493E70` | verified |
| +0x05 | u8 | is_house (types 2..14) | `0x00493E70` | verified |
| +0x06/+0x08 | i16 | x, y (anchor = min corner) | | verified |
| +0x0C | i32 | tile index | | verified |
| +0x14 | u8 | road network id of the access tile | step 21 | verified |
| +0x1C | i16 | house population (hypothesis: passed to eviction `0x00487160`, fire risk 0 when < 1) | step 21/44 | hypothesis |
| +0x20 | i16 | route distance at the access tile (0 = not connected to the city entry) | step 21 | verified (write); meaning hypothesis |
| +0x24 | i16 | no-road / not-connected counter | step 21 | verified |
| +0x26/+0x28 | i16 | road access tile x, y | step 21 | verified |
| +0x34 | u8 | random grid byte & 6 | creation | verified |
| +0x38 | i16 | parent part id (0 = root) | `building_root` 0x0049B920 | verified |
| +0x3A | i16 | next part id | `0x00492F90` | verified |
| +0x40 | i16 | workers (hypothesis; timber mill needs ≠0; zeroed on ignition) | `0x004A7D30`, `0x004950B0` | hypothesis |
| +0x42 | u8 | labor category (type table +0x10), written by step 25 | `0x00487240` | verified (write) |
| +0x43 | u8 | per-type code set at creation (table in building_sizes.json) | `0x00493E70` | verified |
| +0x45 | u8 | type low byte (kept when the building becomes a ruin; copied to ruin grid) | creation, `0x004A07C0` | verified |
| +0x46 | i16 | damage (collapse) risk | step 44 | verified |
| +0x48 | i16 | fire risk | step 44 | verified |
| +0x4A | i16 | fire counter (0 = not burning) | steps 43/44 | verified |
| +0x4C | u8 | fireproof (type table +4; set to 1 when ignited) | creation, `0x004950B0` | verified |
| +0x4D | u8 | random grid byte & 0x7F | creation | verified |
| +0xAC | u8 | orientation (gatehouse, dock, horse ranch, commemorative) | creation/placement | verified |
| +0xCD | u8 | fire cause (0 = ordinary; non-zero fires are not listed and do not spread) | `0x004950B0`, step 43 | verified |
| +0xCE | i8 | desirability | step 38 | verified |
| +0xCF | u8 | 0 at creation, 1 when demolished | | verified (writes) |
| +0xD0 | u8 | adjacent to water (edge neighbours) → +10 desirability | `0x004A4500` | verified |
| +0xD1 | u8 | storage slot (sav rank 81) | `0x00494690` | verified |
| +0xD2 | u8 | 50 at creation | | verified (write) |
| +0xD8 | i16 | linked building (demolition redirects to it) | `0x0049A460` | verified (use) |
| +0xDA | u8 | monument unfinished (1 at creation for composites/pyramids except palace 117; cleared by step 32 `0x00495860`) | | verified |

## 2. Type table `g_building_type_info` `0x005F6368` (221 × 32 bytes, verified)
i32 columns: +0 size, +4 fireproof, +8 image group, +0xC image offset, +0x10 labor category
(−1 none, 0 husbandry … 7 military, 8 defense; names from text group 50, hypothesis), +0x14 info
panel, +0x18 sound, +0x1C help id. Full dump with names: `extracted/model/building_sizes.json`.
Sizes (examples): houses 2..8 → 2, elite 9..14 → 4, farms 3, granary 4, storehouse 1 (but
placed as 3), trading post 1 (placed 4), stadium 5, theatre 5, museum 6, sanctuaries/pyramids 1/3
(placed as composites), road/wall/gardens 1.
Type predicates (verified): composite = 84..98 or 117 (`0x005344A0`); agora = 63, 64
(`0x0040BCF0`); pyramid pieces 100..114; flammable `0x00493040` = not (119, 164..167, 15..24,
127, 148..152, 100..114, 199).

## 3. Creation — `building_create(type, x, y, parts, id)` `0x00493E70` (verified)
```
0x00DB68B8 = 1
if id == 0:
    for id in 1..3999:
        if b[id].state == 0 and not undo_id_reserved(id):
            if parts < 2: break
            if all b[id+1 .. id+parts-1].state == 0 and none undo-reserved: break
    else: message 6 (too many buildings); return 0
elif b[id].state != 0 or undo_id_reserved(id): message 6; return 0
b.state = 3; b.created_flag = 1; b.type = type; b.type_byte = type
b.size = type_info[type].size; b.serial = buildings_created++ (0x0091EBFC)
b.monument_unfinished = 0 if (not composite and type not in 100..114) or type == 117 else 1
b.init_50 = 50; b.road_distance = 0; b.demolished_flag = 0
if type in 2..14: is_house = 1; house_level = type-2
                  +0xF4 = house_param(level, 15) for 2..8 else 0; +0xF8 = +0x10C = 0
                  types 9..14 also call 0x004FF610 (elite)
else: house_level = 0; is_house = 0; +0xF4 = 0
+0xDE = 0
type 131: +0xAC = 0x00DA23C4 (gatehouse orientation)
type 119: if 0x00665DB0 in the "big" list: size += 1; +0xAC = 0x00DA23C4
+0x43 / house_level special cases per type (see building_sizes.json "type_code_0x43";
   53/54/55 set house_level 4/5/3, 60/61/62/119 house_level = 0x00665DB0, 133 house_level 1,
   135 → 3, 136 → 2 (+0xDE = 7), 212 → 2, 207 → global flags)
type 57: +0x56 = 3200
b.x, b.y, b.tile = base + 228*y + x
rnd = random_grid[tile]; +0x4D = rnd & 0x7F; +0x34 = rnd & 6
+0x4C = type_info[type].fireproof
+0xD0 = building_adjacent_to_water(x, y, size)
types 80/81/82: +0x9E..+0xA4 = 0, +0xA9..+0xAB = 0
types 46, 51, 56, 37, 214 or 0x004A96B0(id): +0xA8 = 0
buildings_last (0x0091EBF8) = max(buildings_last, id)
return id
```
The creation does **not** touch the grids; the caller places the footprint with
`building_footprint_place` `0x004A04B0(id, x, y, w, h, image, bits=8)`:
terrain = `(t & 0x93872F90) | 8`, building grid = id, piece low bits = size−1 (2→1 … 6→5),
ground image, draw flags; anchor flag 0x40 on the corner chosen by `0x00FA05E8`
(0: (0,h−1), 2: (0,0), 4: (w−1,0), else (w−1,h−1)).

**Undo and ids (verified):** after every build `undo_arm` `0x004A6FD0` opens a 500-tick undo
window (`0x00DA2368`, decremented by `undo_expire` `0x004A7A50` every tick). While it is open
(`0x00DA236C == 1 && 0x00DA2374 == 1`), ids listed in `0x00D7FC08` (the buildings of the last
action) are skipped by creation. The window closes early when any listed building changes state
to 2/4/5, moves, or changes type; collapses and fires also clear `0x00DA2374`.
A faithful port must reproduce this or ids diverge.

`buildings_clear_all` `0x00493E50` zeroes all records (new game); single removal is
`building_free` `0x00494620` (below).

## 4. Lifecycle — cycle step 40 `0x00484030` (verified)
For id = 1..buildings_last:
```
if state == 3: state = 1
if state == 1 and is_house: continue
if state in (2, 6):
    type 131: 0x004E5400(id), building_free(id)          # gatehouse
    type 9..14: 0x004FEEC0(id)                            # elite house removal (housing)
    agora 63/64: nothing extra
    other: (119: piece-flag fix; 100..114: pyramid flag) building_footprint_clear(id, x, y)
    then building_free(id)
elif state == 4: if is_house: 0x005675D0(+0x1C) (population lost); building_free(id)
elif state == 5: building_free(id)                         # no footprint clear
```
After the loop: tower/gatehouse removed → `0x0049FD70`; any removal → `0x00587B30` +
`0x00502EB0` (route rebuild, walkers); last tool was clear-land → `undo_arm`.
`building_free`: `building_on_remove` `0x00494690` (per-type cleanup: storage slot, palace globals,
horse ranch figures → state 2, warship count, …) then zero the record (kept for some
`0x0040AA20` types when `0x0040ACE0` says so).
`building_footprint_clear` `0x004A09F0`: tiles owned by the building: building grid 0, piece low
nibble cleared, wall-damage 0, draw = 0x40, `0x00CC1618` = `0x00CB4B08` = 0, ruin-type grid =
type byte; terrain `& 0x93872F94` (water tiles keep only 0x4). Elite houses clear 4×4.

## 5. Placement — build tool
Mouse release `build_tool_release` `0x00405700` → `build_commit(orientation 0x00DA2F88, x1, y1,
x2, y2, tool 0x00665DCC)` `0x00498910`. Single clicks (`build_tool_click` `0x00404CD0`) only
start road (28) / wall (130) drags and handle editor point tools. Tool flags are set when a tool
is selected (`build_tool_select` `0x00404330`). **verified (control flow).**

`build_commit` order:
1. tool 0: return; tool 147 (lightning): special.
2. **Treasury:** if treasury `0x00FE6A64` < −1999 → message 0x13, nothing built.
3. Unless tool 29: if `enemies_near_rect` `0x004DCF60` (an active figure of type 0x28, 0x29,
   0x2A, 0x3F or 0x40 within 12 tiles in both axes of either drag corner) → message 0x21, abort.
4. `cost = model col0(tool)`.
5. Drag tools (cost = col0 × items, counted in `0x00DA23CC`): 29 clear land
   (`0x0049A120`), 130 wall (`walls_drag` 0x0049AF50), 28 road (`roads_drag_place` 0x0049ACB0,
   counted per new road tile in `road_set_tile`), 126 boulevard, 118 avenue, 25 (water park?)
   `0x0041BE40`, 199 race track, 128 gardens, 129/145/146 columns, 120 bridge, 201 crosswalk,
   2 house plots (`houses_drag_place` 0x00499E20), 35/36/217 orchard trees (`0x0049B210`).
6. Animals 39 goat, 40 sheep, 220 cattle: the tile must have no building and
   `(terrain & 0x1000CA60) == 0x800` (bare meadow) and no walker other than type 24;
   `0x004F92A0(figtype, 1)` limit; creates the figure; charged col0.
7. Single buildings:
   - size s = type_info.size; 58 → 3; 61, 62 → 4; 119 big variants → 4; composites/pyramids → 1.
   - map reserved points (`map_area_has_marker` 0x00496B50) → message 0x16.
   - orientation shift of the anchor (view orientation o): o=6: y += 1−s; o=4: x,y += 1−s;
     o=2: x += 1−s (not for 131).
   - per type: 44/45 wharves need coast (`0x004A10C0`), 131 gatehouse `0x004E5480`,
     136 warship wharf coast `0x004A14B0` + reachable water (`0x00485670`) + at most 6,
     60 dock: at most 10 (`0x00782CEC`), coast `0x00453450`, reachable water;
     63/64 agoras on a road segment (`0x0040D7B0`/`0x0040D7E0` + `0x0040BF40`): layout tables
     0x005E8790 (common, 4 variants x 18 tiles: road strip col 2 / row 0 / col 0 / row 2) and 0x005E8C10
     (grand, 2 x 30: col 2 / row 2); road tiles need terrain 0x40 and no building, land tiles
     `terrain & 0x1537526F == 0` and no blocking figure. Search (ghost and click): every variant at the
     cursor tile in table order; else anchors y' = y..y-5 (outer), x' = x..x-5 (inner), each variant whose
     tiles include the cursor tile; first fit wins and its variant is remembered (0x00665E44). Ours:
     sim/systems/agora.py `snap` (verified 2026-10-28, bugs.md 30);
     composites via `composite_bounds` + `0x0053D9A0` (religion);
     133 horse ranch: extra 4×4 `map_area_buildable` at an orientation offset (`0x00637E60`);
     9 elite: `0x004FF430`.
   - generic: `map_area_buildable(x, y, s, s, mask, 0, allow_beach, ignore_walkers, 0)` with
     mask −1 (131: `0xFFFFFFBF` = may cover road; 132 tower: `0xFFFFBFFF` = may cover wall;
     123 roadblock: mask 8, ignore walkers) and allow_beach for tools 28, 29, 123 only.
     What `map_area_buildable` 0x004A0DC0 refuses, per footprint tile (read 10-28, ours since 10-28):
     the play-area-local x < 3 or y < 3 or beyond width/height − 3, and `map_near_play_edge(x, y, 3)`
     0x00496080: within 3 tiles of the play area's diamond edge (x+y or x−y against the edge line of the
     tile's quadrant, `map_in_play_area` 0x00496010) — ours `World.near_play_edge` (the tile 3 steps along
     x or y is off the map; the same away from the 4 corners) in `World.area_ok`; any figure on the tile
     (grid_figure 0x00D0D878) except FIG_AMBIENT 6 and FIG_ZGUY 0x18, unless ignore_walkers (only the
     roadblock tool and tool 0x7B) — ours `Game.walker_on` in the generic build, the ranch and the ghost
     (`/footprint.json`, red tile); **scripts are exempt** (script.apply: walkers wander differently after
     every sim change, so a benchmark build would fail at random; decision 10-28); a mix of beach (0x10000)
     and non-beach tiles — but the masks refuse 0x10000 anyway except with allow_beach (roads, clear,
     roadblock: 1x1 or per tile), so the mix rule never decides anything: nothing to port; a tile object
     (0x00666930) whose +0x18 is 0 (not identified). It has no level test (param 6 compares grid 0x00D4CFC8
     with param 6 − 1, and only terrain drawing passes it: FUN_0049BF00, map_tile_plain_ground 0x0051FBA0);
     neither has the sanctuary test 0x0053D9A0. Ours: no level test either since 10-29 (it was "ground is not
     level" in World.area_ok and Game._monument). On the shipped maps two adjacent buildable tiles differ in
     height in 2 places over 16 maps (none on the sandboxes).
     **Animals under the build cursor** (11-03, oracle re/oracle/runs/sheep-build-r1/-r3/-r4, scenario
     re/oracle/scenarios/sheep-build.txt, tools/oracle_sheep_build.py; bugs.md 431): every frame with a build tool
     over the city view (game_turn 0x00513580 / screen_input -> FUN_004059C0) the exe takes the tool's footprint at
     the hovered tile (side g_building_type_info[tool].size, 0x3A -> 3, 0x3E -> 4; view 0: [x, x + s) x [y, y + s),
     views 2/4/6 shifted so the cursor tile stays the visual top), sets 0x00F0E4C8 = 1 with that rect at
     0x00F0E4CC and calls FUN_004F9380 (ECX = 0x00F0E4C8) on each footprint tile's figure list: a sheep 0x31, goat
     0x32 or cattle 0x4C grazing / waiting (actions 6, 0x10) gets animal_pick_dest(7, radius s), failing that
     (7, 2 s); one wandering (0x11) the same with action 8; a bull (0x4C, resource 2) 6/9/0x10 -> 0x11, 8 -> 10.
     While the flag is set every animal_pick_dest (all callers pass ECX = 0x00F0E4C8) refuses a spot inside the
     rect (PtInRect). Animals already walking are left alone. The build (map_area_buildable above) is still refused
     while one stands on a footprint tile. Oracle: the house-plot ghost over sheep 288 at (132,130): dump 38 action
     16 -> 7, destination 2 tiles off the plot, walking from tick 38 (r1 without the tool: grazes on); a click at
     tick ~41 (still on its tile) is refused, nothing placed (r3); a click at tick ~50 places the plot (-10 dr; r4).
     The ghost's red tile turns green as it leaves. The user's memory ("they move along") is this. Ours since 11-03:
     walkers.shoo (applied between ticks while g.hover is set: play mode's ghost posts /control {hover}, the CLI
     `hover KEY X Y`), _hop skips the rect while hovering; the footprint is play mode's ghost anchor (anchorFor).
     Ramps (0x400, on cliff tiles) carry roads (route grid 0x10 / 0x100, pathfinding.md §2): ours since
     10-28 (World.free_land); buildings refuse them (mask has 0x400 and 0x200).
   - farms/orchards (31,32,33,35,36,217 and animal tools): at least one tile of the 3×3 at
     (x,y) with terrain 0x800 or 0x10000 (`terrain_area_any`) else message 0xD0.
   - tower 132: all 2×2 tiles walls (0x4000) else 0x25. Roadblock 123: tile is road, not
     0x600, `0x00CB4B08` = 0, else 0x2A / 0x12.
   - stadium 80: `0x005B03A0` (see §5.1). 122 tax office? (`0x7A`): needs palace (`0x00FEAEDE`) else 0xDD.
   - tutorial/advisor hooks (`0x00523640`…`0x00524520`), then `building_create`, record undo,
     `0x00496CA0(type, id, x, y, size, 1, 0)` = place footprint, images, sub-parts (storehouse
     bays 59, dock house 61, granary storage slot …).
8. **Cost deduction:** `treasury_spend_construction(cost)` `0x005676A0`: treasury −= cost;
   `0x00FE96E4` (construction spending) += cost; nothing in editor mode. `0x00DA23C8` is always 0.
   Then route rebuild (`0x00587B30`…), `undo_arm` (not after clear land), `0x00448990` over the map.

**Gatehouse 131 (0x83)** (`FUN_004E5480(x, y, orientation 0x00DA23C4)`, verified 2026-10-28): four pieces
from table `0x0063A848` (16 bytes: road_ok, size, a, b; piece at (x+b, y+a) for orientation 0, (x+a, y+b)
for orientation 1, (x, y) otherwise): (0,2,0,0) tower, (1,1,2,0) and (1,1,2,1) passage, (0,2,3,0) tower.
So orientation 0 = 2x5 along y (towers at rows y..y+1 and y+3..y+4, passage row y+2, road east-west),
1 = 5x2 along x (passage column x+2, road north-south). A tower tile must pass
`map_area_buildable(…, mask −1)` (no road, no wall, no building, no tree…); a passage tile passes if it is
a road (`map_area_buildable(mask 0x40)` fails), else as a tower tile. No anchor shift for the view
orientation. **No wall or road is required** (checked 2026-10-28: build_commit 0x00498910 runs only this
check for 0x83, after the generic map_area_buildable with mask 0xFFFFFFBF, and neither looks for walls; a
passage tile on a wall is refused, so a wall must end beside the towers). `map_area_buildable` has no level
test unless its param 6 (elevation + 1) is given, which the gatehouse doesn't. Selecting the tool sets orientation 1 (`build_tool_select` 0x00404330); the key that toggles it was not traced (the
stadium uses `& 1` on the same variable). Placement (`FUN_004E4FA0`): footprint bits 0x8008 on the towers, 0x8048 (= road) on the
passage, images Zeus_General groups 138 SPR_STONE_GATEHOUSE (towers), 107 SPR_B_GATE_BACK and 112
SPR_B_GATE_FRONT (passage), each + 0/1 by `(orientation + view) in {0,3,4,7}` (inverted for views 2/6),
piece order per view from `0x0063A7C8`. Creation stores `+0xAC` = orientation.
Tables (dumped 10-28): draw slot k = 0..3 has the packed image `0x0063A780[k]` = 0x88A, 0x86B, 0x870, 0x88A
(collection 4: group 138 tower, 107 passage back, 112 passage front, 138 tower) and is placed on piece
`0x0063A7C8[(orientation + view) & 7][k]`: rows 0,1 = (0,1,2,3), 2 = (0,2,1,3), 3 = (3,1,2,0), 4,5 = (3,2,1,0),
6 = (3,1,2,0), 7 = (0,2,1,3). Pieces (`0x0063A848`, 16 bytes: road_ok, size, a, b): (0,2,0,0), (1,1,2,0),
(1,1,2,1), (0,2,3,0). Image = group first + 1 when orientation + view is 0, 3, 4 or 7 (inverted in views 2
and 6). Play mode draws view 0 (viewer/play/scene.js drawGatehouse).
**Tower 132 (0x84):** size 2 (type table), `map_area_buildable` mask `0xFFFFBFFF` (wall allowed, all else
as usual), then `terrain_area_all(x, y, 2, 0, 0x4000)`: every one of the 4 tiles must be wall, else message
0x25. Walls are dragged 1 or 2 thick (military.md "Walls"), so a tower needs a 2-thick stretch.

No ore-adjacency or ground-water test exists at placement (miners just walk to rock tiles of
their kind: foundry→copper 0x100002, mint→silver 0x200002, quarry→0x20000, black-marble shop
→0x120000, refinery→0x300000, see map-terrain.md).

House plots (`houses_drag_place`): with orientation correction, for every tile (x,y) of the
dragged rectangle in row-major order, if `map_area_buildable(x, y, 2, 2, −1, 0, 0, 0, 0)` then
create type 2, record undo, place footprint 2×2 (bits 8); if `house_find_road_access` fails,
message 0x1A at the end. Cost = 20 × count (Normal).

**Demolition** (tool 29, `clear_land_commit` `0x0049A460`): each building in the rectangle
(redirected through `+0xD8`, root via `+0x38`), unless it is type 164..167, burning
(`+0x4A ≠ 0`) or already state 6, gets state 6 (and all its parts), houses evict their
population (`0x00487160`), counted once each; terrain features (trees, rubble, reeds, rock with
piece 0x80 on road …) are cleared and counted. Cost = col0(29) × count = 2 × count (Normal).
The records are freed at the next step 40.

### 5.1 Stadium (type 80): two 5x5 parts (verified, 2026-10-28)
- Orientation `0x00DA23C4` (0 at start, `R` toggles `& 1` in the ghost `0x005AFD80`): 0 = second part
  at (x, y+5) → 5x10; 1 = at (x+5, y) → 10x5. Size `0x005F6D68` = 5.
- Layout table `0x005E4958`: 0xE0 per orientation, 0x38 per camera view (`view/2`, `0x00DA2F88`); i32s:
  +0/+4 part A offset, +8/+0xC part B offset, +0x10/+0x14 ghost B draw offset, +0x18/+0x1C create
  offset, +0x20/+0x24 rectangle w/h, +0x28/+0x2C built images A/B, +0x30/+0x34 ghost images A/B
  (collection<<9 | group). View 0: orientation 0: A at (0,0) = `SPR_B_STADIUM_S` (442), B at (0,5) =
  `SPR_B_STADIUM_N` (441); orientation 1: A = `SPR_B_STADIUM_E` (443), B at (5,0) = `SPR_B_STADIUM_W`
  (444). The ghost draws the same two images; invalid → red tiles over the w x h rectangle.
- Placement `0x005B03A0`: refused (19:44 "You may only have one Stadium") while
  `g_unique_venue_exists` `0x00FEAED0` is 1; else `map_area_buildable` on each 5x5 part separately.
  The flag is set by the stadium (`0x005AFAE0`) **and the museum** (type 0xCF), cleared on demolish,
  recomputed on load (`0x005B0360`, stadium only); the museum's own check gives 0x14 when it is set.
- Create `0x005AFAE0` → `building_create(0x50)`; `0x005AFB40` creates part B as another type-80
  building (`next_part`/`parent_part`) and places both 5x5 footprints with their images.
- Road access `0x005B04F0` → `0x005B0600`: a road next to the part's own 5x5, else next to the
  5x5 after it (orientation 0: y+5, 1: x+5). Desirability rectangle `0x005B02E0` = root + table
  rect (view 0).
- Ours (sim/systems/stadium.py): one Building, size 5, misc w/h/orient; `build stadium X Y [v|h]`
  (v = orientation 0, default). The museum's shared flag is applied to the stadium check only
  (museums are not limited yet).

## 6. Road access — cycle step 21 `buildings_road_access` `0x004856A0` (verified)
First a BFS from the city entry point (`0x00902CB4/6`) fills route distances (`0x005883E0`,
walkers). Then for each state-1 building (not type 199: `+0x26 = +0x28 = 0`):
- **Houses** (`is_house`): `house_find_road_access(x, y, size)` `0x004A3B40` looks at the
  edge-adjacent tiles (table `0x005F1680`, no corners; clockwise from the top-left: top left to right, right
  top to bottom, bottom right to left, left bottom to top; ours roads.update_access since 11-01, bugs.md 369). A tile qualifies if it is a road
  (0x40) and not water; tiles with terrain 0x8 are skipped if they hold a roadblock (123) and
  are mapped to their anchor for avenue/boulevard tiles. Among qualifying tiles, the one whose
  road network has the best rank in the top-10 list wins (rank 11 if not listed; strict `<`, so
  the first such tile wins ties).
  - none: `+0x20 = 0`; `+0x24 += 1`; if `+0x24 > 4`: if population: evict (`0x00487160`),
    population = 0, `+0x24 = 0`; **state = 2** (the house disappears on the 5th check).
  - found, `route_distance[tile] == 0`: `+0x20 = 0`; `empty_hut = (type == 2 and pop == 0)`;
    if `+0x24 == 0` and (empty_hut or nothing noted yet): note this tile (message later);
    `+0x24 += 1`; if `+0x24 > 8`: `+0x24 = 0`, and if empty_hut: **state = 2**.
  - found, connected: `+0x20 = route_distance[tile]`, `+0x24 = 0`. Always `+0x26/+0x28` = tile.
- **Other buildings** (default): `building_find_road_access(x, y, size)` `0x004A4560`: same
  candidates and ranking but also requires `route_distance > 0`; if none, fallback = any
  adjacent tile with the smallest positive route distance. Sets `+0x14` (network id),
  `+0x20` (distance), `+0x26/+0x28`. No penalty when missing (`+0x20` stays 0).
  Special: 58 → size 3, 62 → size 4; dock 60 uses the house search, else its partner `+0x3A`;
  palace 117 `0x004A3D40`; composites/pyramids `0x0053F640` (only x,y); parts 59/61/134 copy the
  root's values; horse ranch 133 `0x004A4780`; stadium 80 `0x005B04F0`; race track 199 special.
- What a disconnected road means (verified 2026-10-28, bugs.md 85): the entry BFS `0x005883E0` uses
  route mask **0x17D** (open land, roads, decor, building parts, corral; trees, rubble, marble and reeds
  are open land in the route grid), so `route_distance > 0` = "reachable overland from the entry", not
  "joined to the main road". A non-house building beside any such road: `+0x26/+0x28` = that road tile,
  step 12 `cycle_buildings_pass_12` 0x00484FE0 sets labor access `+0x18 = 100` (terrain at `+0x26/+0x28`
  has 0x40) → it gets workers from the city-wide pool (labor.md). Service walkers spawn on any adjacent
  road (`house_find_road_access`, no distance test, services.md §3) and roam that road. Carts only reach
  buildings with the same road network id `+0x14` (storage-distribution.md), so goods stay on that road
  piece. Only the fallback (no reachable road, a reachable land tile) leaves `+0x18 = 0`: no workers.
- After the loop, if the exit point (`0x00902CB8/A`) is unreachable, up to 15 attempts: re-run the
  BFS; when still blocked, `0x00485E70` destroys the **most recently created** building (highest
  `+0x16` among states 1/3, its root): state 4, message 0xDE. Otherwise, a noted unconnected
  house tile raises messages 0x1B/0x1C.

## 7. Collapse and fire risk — cycle step 44 `buildings_fire_collapse_risk` `0x00492260` (verified)
Skipped entirely when `0x00B1E8BC == 1`.
```
draw()                                  # one RNG draw at the start
k = e4 & 7
for id in 1..buildings_last:
    b = buildings[id]
    if b.state != 1 or b.type == 169 or b.fire_counter != 0 or b.type == 59
       or building_root(id) != id: continue
    rnd = random_grid[b.tile]
    b.damage += col7(type)                               # i16 arithmetic
    (dead code: if fire_counter != 0: damage += 10*col7)
    if (b.is_house and b.house_level < 2) or b.type == 9: b.damage = 0
    if terrain[b.tile] & 0x10000: b.damage = 0           # beach
    if b.damage < 1000:
        draw(); s = (e4 & 0x7FFF) % 5 + 1                # drawn for every such building
        if ((rnd + id) & 7) == k:                        # 1 building in 8 per cycle, on average
            if not b.is_house:
                if climate(0x00902D00) == 2 and col6 != 0: b.fire += 3
                b.fire += col6 * s;  if col6 == 0: b.fire = 0
            elif b.population(+0x1C) < 1: b.fire = 0
            else: b.fire += col6 * s
            if b.fire > 999:   # FIRE
                b.fire_counter = 1; message 0xDC (texts 0xB3A..0xB3C); fires_count (0x00FD3778) += 1
                building_ignite(id, 0, 0); building_parts_destroy_or_ignite(id, 1)
    else:                                                # COLLAPSE
        message 0xDC (texts 0xB40..0xB42); collapses_count (0x00FD377C) += 1
        b.state = 4; undo invalidated (0x00DA2374 = 0)
        if type == 131: 0x004E5B60(id) else building_footprint_to_rubble(id, x, y, size, size)
        collapse_debris_spawn 0x004CCD40(x, y, size, 1, 4, 0)
        building_parts_destroy_or_ignite(id, 0)
if any collapse: 0x00587B30(); 0x00502EB0()
```
col6 = fire-risk increment, col7 = damage-risk increment (model, difficulty-dependent).
Message throttling uses the real-time clock `0x00F9C0F4` (15 s) — UI only.
Climate `g_scenario_climate` 0x00902D00 = byte 0x3D8 of the map's scenario block (rank 14): 0 on all 111 shipped
maps (read 10-29), so the arid rules (+3 fire, spread every 4 days) never fire in the original's maps.
Sim (10-29, `risk.update` / `risk.burn`): climate read from the map, arid +3 and the 4-day spread; beach
(0x10000) under the building's tile and house level 7 (type 9, vacant elite lot) never collapse.
Risk is lowered by walkers (services): `0x004A5D90` subtracts col9 of type 121 (maintenance
office, "risk reducer" 50 on Normal) from both `+0x46` and `+0x48` (clamped at 0) of buildings in
its range and from the wall damage grid; type 124 col9 is used by `0x004DFB70`.
`building_footprint_to_rubble` `0x004A07C0`: like the demolition clear, but land tiles become
`(t & 0x93873F90) | 0x1000` (rubble, −2 desirability) and the ruin-type grid gets the type byte.

`building_ignite(id, cause, to_ruins)` `0x004950B0`:
```
if type == 131: 0x004E5C30(id); return          # gatehouse
if type in (126, 118): return
b.fire = b.damage = b.road_distance = 0
n = 4/9/16/25/36 for size 2..6, else 0; types 58, 59, 61, 62: n = 1
if agora (63/64): if to_ruins: state 5 else: fire_counter = (+0x4D & 7)+1, +0x30 = 0,
                  fireproof = 1, fire_cause = cause, workers = 0; return
if (terrain[b.tile] & 4 or to_ruins) and type != 60: state = 5
for each of the first n footprint tiles (dx,dy table 0x005F19B0) that is not water:
    t = id, or if to_ruins a new ruin building_create(169, ...) with its footprint
    buildings[t]: fire_counter = (+0x4D & 7)+1, +0x30 = 0, fireproof = 1, fire_cause = cause,
                  workers = 0;  fire_figure_spawn(t, tx, ty, 1, 1)   # figure type 10
```
So a size-1 building keeps fire_counter = 1 from step 44; larger ones restart at 1..8.

## 8. Burning — cycle step 43 `buildings_fire_burn` `0x00493140` (verified)
```
0x0091EC40 = 0; list_len (0x0091EC3C) = 0; burning_count (0x0091EC44) = 0
for id in 1..buildings_last:
    b = buildings[id]
    if b.state != 1 or b.parent_part != 0: continue
    if b.fire_counter < 0: b.fire_counter = 0
    if b.fire_counter == 0: continue
    b.fire_counter += 1
    if b.fire_counter < 33:
        if b.fire_counter > 16 and b.type != 169:
            building_parts_to_burning_ruins(id)     # 0x00492F30 -> 0x00492BE0 per part
        if b.fire_cause == 0:
            burning_count += 1; list[list_len] = id; list_len = min(list_len+1, 499)
            mask = 3 if climate == 2 else 7
            if (b.fire_counter & 0xFF & mask) == 0:
                draw()
                if (b.random_7f & 3) == (e4 & 3):            # spread
                    w = wind (0x0091EC48); for dir in (w, w-1 mod 8, w+1 mod 8):
                        n = building_grid[b.tile + dir8[dir]]
                        if n and buildings[n].fireproof == 0 and building_type_flammable(n):
                            building_ignite(n, 0, 0); building_parts_destroy_or_ignite(n, 1)
                            sound 7; break
    else:                                            # burnt out
        b.state = 4; undo invalidated
        building_footprint_to_rubble(id, x, y, size, size); building_parts_destroy_or_ignite(id, 0)
        if type != 169: collapse_debris_spawn(x, y, size (58→3, 62→4), 1, 4, 0)
if anything burnt out or spread: 0x00587B30(); 0x00502EB0()
```
`building_to_burning_ruins` `0x00492BE0`: removes the building (`building_on_remove`,
footprint clear, debris spawn unless 169, houses lose population, agora → state 5); if its tile
is land it becomes type 169, size 1, state 1, fireproof, cause 0, ruin image, flames, and its fire
counter **starts again at (+0x4D & 7) + 1** (disassembly 0x00492D58..0x00492D67; corrected 10-30, the
note said "keeps the counter"); else state 5. Every other land tile of the old footprint (n−1 tiles from
`0x005F19BC`) gets a new ruin building (state 3) with that same counter. Links +0x38/+0x3A are
cleared. Wind: one draw a year (`wind_direction_draw` `0x00484F10` from `month_advance`).
Burn time: the building from c0 (1..8, or 1 for size 1) to 17, then its ruins from (seed & 7) + 1 (1..8; for a
size ≥ 2 building the same c0, since building_ignite used the same seed) to 33: 16 − c0 + 33 − c0' cycles of 51 ticks.
A ruin's counter is ≤ 16 for most of its life, so a superintendent puts it out (+0x4A = 0, services.md §4.1) and the
ruin stays: type 169, not burning, until the player clears it. Verified by oracle 1F-palacefire (below).

### 8.1 Palace fire and collapse (bug 268, verified 10-30)
The palace is a composite of 24 building records, all type 0x75 (the composite placement calls `building_create` with
the root's type for every part): the root = layout piece 0 (class 4, the 4x4 back), part 1 (class 3, the 4x4 front) and
22 1x1 parts (classes 5 / 6); `+0x12` = the piece index. Only the root takes part in steps 43 / 44 (`building_root(id)
== id` / `+0x38 == 0`), with the model row 0x75: fire / damage risk 0 / 5 / 5 / 10 / 15 (VeryEasy .. Impossible).
- Ignition: `building_ignite(root)` + `building_parts_destroy_or_ignite(root, 1)`: root and part 1 (size 4) get
  (seed & 7) + 1 and fireproof, 16 flame figures each (the root twice: 48 type-10 figures); the 1x1 parts get
  nothing (n = 0 for size 1: counter 0, fireproof stays 0). The palace keeps working while it burns (g_palace_exists
  stays 1; text 103:14 "Fire! The Palace won't function properly until the fire is extinguished!").
- No superintendent comes: road access for the palace (`0x004A3D40`) sets only the entry x / y, never `+0x20`, and
  fire_find_target needs `+0x20 != 0` (dump: root `+0x20` = 0).
- Spread: from the root's tile (piece 0's corner), whose 8 neighbours are all palace tiles; a 1x1 part there is not
  fireproof, so spreading "to" it lights the palace again (root back to (seed & 7) + 1). Fire from outside reaches the
  palace through any part tile not yet fireproof.
- Root counter 17: `building_parts_to_burning_ruins(root)`: every part to burning ruins, each part's tiles at its own
  (seed & 7) + 1; the parts' own records (ids after the root's) are counted again in the same step-43 pass (one
  ahead). `building_on_remove` on the root clears g_palace_exists / g_palace_building: no palace (no tax clerks,
  towers unmanned, home companies disband: military.md).
- Collapse (damage ≥ 1000): root state 4 + `building_footprint_to_rubble`, every part to rubble: the whole 6x9 box.
  Zeus' palace strike (god_special_hit 0x004EDFC0 -> building_destroyed_by_attack at the palace tile) does the same.
- Rebuilding: a new palace on the cleared site at the model cost (Normal 250); one palace at a time (build_commit
  0x00498910: type 0x75 while g_palace_exists -> message 0x14, 19:20 "Only one of this building allowed").
- Oracle 1F-palacefire (tools/oracle_palace_fire.py; "See a working city" at VeryEasy with the palace's model fire
  risk poked to 15 and the root's fire risk held at 990): ignition between ticks 867 and 918 (root seed 5 -> counter
  6, part 352 seed 101 -> 6, the 1x1 parts 0, 48 flames); the root counts 6..16 a day, at tick 1479 54 ruins (root's
  tiles 6, part 352's 7 = 6 + 1, part 355 seed 121 -> 3); superintendents put out ruins by the roads (counter 0, they
  stay ruins to the end of the run, tick 4488); one ruin reached at 17 was set to 32 and burnt out to rubble.
- Ours (sim/systems/risk.py): the palace is one Building; update() takes its risks, ignite() keeps the draw as
  misc fire_c0, ruin_tiles() gives the root's tiles fire_c0 and every other piece its own draw (+1 on the piece's
  first tile), fire_dispatch() skips it, can_catch_fire() lets fire reach it (and light it again through a 1x1
  piece), to_rubble() for collapse and Zeus. Old saves: a palace placed before 10-30 starts at risk 0 (it never
  accumulated).

### 8.2 Buildings with parts, Hephaestus, spread immunity (bugs 290-295, verified 10-30)
- **Fireproof is about spread only.** `+0x4C` (no_fire_spread) = type table +4 at `building_create`; step 44 has no
  fireproof test, so a fireproof type with a model fire risk still ignites from its own risk: the horse ranch 0x85
  (fireproof 1, fire 5 / 10 / 10 / 10 / 20). `building_ignite` sets `+0x4C` = 1 and nothing ever clears it
  (writers: 0x00492BE0, 0x004950B0, building_create, 0x004E5C30): a building once lit and put out never catches
  fire from a neighbour again.
- **Fire risk increment** = `model_building_value(type, 6)` (0x00433D50), which returns 0 while Hephaestus'
  sanctuary is active (`god_sanctuary_active` 0x004E9440 on god record 9, `mov ecx, 0x00EF5FAC`). For a non-house
  a 0 increment (the model's 0 or Hephaestus) resets the fire risk to 0 on its 1-in-8 day; a house keeps its value
  (+0). Houses use the row of their current type 2 + level: manor (13) 5 / 10 / 10 / 12 / 15 and estate (14)
  2 / 5 / 5 / 8 / 10, the other houses 8 / 12 / 15 / 18 / 20.
- **Horse ranch** (house 0x85 3x3 + corral 0x86 4x4, `next_part` chain): ignition lights the house twice and the
  corral (9 + 9 + 16 = 34 flame figures; the corral's own counter (seed & 7) + 1, never counted: parent_part != 0);
  the ranch stops (workers 0), the horses stay in the corral; a superintendent can put it out (the chain's counters
  to 0). Past 16: the house's 9 tiles ruins at its restart counter, the corral's 16 at the corral's, its own record
  (first tile) one more; `building_on_remove` case 0x85: the 6 horse figures state 2 (gone). Oracle
  re/oracle/runs/1F-ranchfire (put out at counter 9) and 1F-ranchburn (counter poked to 15 at tick 770: at tick
  867 25 ruins, house 5, corral 8, (79, 59) 9; horses gone); tools/oracle_fire_parts.py.
- **Agora** 0x3F / 0x40 (model fire 6 / 12 / 12 / 12 / 20; ours skipped it): the agora record is the root (its id on
  the road strip tiles in g_grid_building), the stall parts (2x2, the vendor's type) its chain; the vendors' own
  records (same tiles, parent 0, not in the grid) are not touched. Ignition: the agora root's counter only (no
  tiles, no flames: the agora branch of building_ignite), every stall part its own counter, 4 flames, workers 0.
  A fire reaching a stall tile or a strip tile lights the whole agora (building_parts_destroy_or_ignite from the
  root). Past 16: the agora state 5 (FUN_0040BE50 takes its id off the strip, which stays road), each stall part
  4 ruins at its counter (+1 on its first tile). Oracle 1F-agorafire (put out at 11: every counter 0, `+0x4C`
  stays 1) and 1F-agoraburn (tick 1377: 12 ruins 9/8, 4/3, 5/4 = stall counters 8, 3, 4; vendors 498..500 still
  state 1 off the grid). Maintenance lowers the agora's risk per strip and stall tile in reach (building_root).
- Ours (sim/systems/risk.py): `fire_inc` (Hephaestus, house rows from data/houses.json fire_risk), `boxes` /
  `remove` / `ruin_tiles` / `target` (stall or strip -> agora) / `on_fire` (a stall of a burning agora: labor,
  export), misc no_spread / fire_parts; agora.remove / strip_near; play mode draws the corral's and the stalls'
  flames (scene.js buildingFlames). Old saves: a ranch's fire risk (gathered but never lit before 10-30) starts at
  0 (Game.load, fire_v). The exe's leftover vendor records have no counterpart (ours: the stall is the vendor).

## 9. `multi_tile_buildings_update` `0x00534F60` (every tick, verified)
For each state-1 composite/pyramid root: pyramid pieces (100..114) run
`pyramid_parts_animate` `0x00534D60` (a 5-state animation counter on +0xB6..+0xBF of each part,
no RNG; uses vtable calls of the layout object); then skip the `composite_parts_count` records of
that composite. No other state changes. Called from `simulation_tick` `0x00513A30` after the
cycle step and terrain events, before `walkers_update`.

## 10. Order within a tick (verified, `simulation_tick`)
RNG draw → `tick_period_counters` → `undo_expire` → `simulation_cycle_step` (one of 51 steps;
editor: none) → `terrain_events_update` → `multi_tile_buildings_update` → `walkers_update`.
Steps of this subsystem: 7 road networks, 20 regrowth, 21 road access, 37/38 desirability,
40 lifecycle, 43 burning, 44 risk.

## Cross-references
- Services: watchmen/maintenance walkers `0x004A5D90`, `0x004DFB70`, fire figures (type 10).
- Walkers: route BFS `0x005883E0`, `0x005885E0`, `0x0058D500`, route rebuild `0x00587B30`,
  `0x00502EB0`, debris `0x004CCD40`, `figure_create` (draws RNG).
- Population-housing: eviction `0x00487160`, population lost `0x005675D0`, elite removal
  `0x004FEEC0`, `houses_evolve`.
- Religion: composites `0x0053CF30`, `0x0053D9A0`, `0x0053F640`, `0x00495860` (monument done).
- Military: `0x004928C0`, `wall_damage_add` `0x00492830`, gatehouse `0x004E5B60/0x004E5C30`.
- Finance: `0x00FE96E4` construction spending, treasury.
- Messages `0x00521A70` / `0x005231E0`.

## Open questions
- Exact role of `+0x20` (route distance vs. "has access" flag) for consumers.
- `0x00496CA0` per-type footprint/image placement is only skimmed (sub-parts of storehouse,
  dock, granary, agora; stadium done in §5.1); sub-part ids follow creation order there.
- Tool 25 (`0x0041BE40`) identity; type 119 "big" variant list `0x00665DB0`.
- `0x00B1E8BC` setter (no write found in the decompile: probably a scenario/cheat flag).
- Who writes `+0x1C`; confirm it is the house population (population-housing agent).
