# Walkers (figures): generic machinery

Status: **verified** from the exe unless marked **hypothesis**. Addresses refer to GOG `Zeus.exe`.
Scope: the figure record, creation/deletion, the per-tick loop and handler table, movement
(speed codes, sub-tile steps, directions, per-tile lists), roaming, destination walking,
service coverage (generic part), spawning (generic part), formations (generic level only).
Route search (BFS, distance grid, route grid bits) is in [pathfinding.md](pathfinding.md).
Per-type tables: `extracted/model/figure_handlers.json`.

## Summary

There are 2,000 figure slots (`figures` `0x00DBD788`, 388 bytes each, slot 0 is a scratch
record). Every simulation tick `walkers_update` calls the handler of each live figure's type
once, in slot order 1..1999. A handler is a small state machine on `action` (+0x38). Walkers
move in 15 sub-steps per tile (`tile_progress` +0x39); the speed code (model column 8) says how
many sub-steps happen per tick, by a repeating pattern held in `speed_phase` (+0x160). A walker
either follows a precomputed route (array of 8-way directions, up to 499 steps, 999 route slots),
or roams the road network choosing a direction at each tile center. Each time a walker reaches a
tile center it "serves" the 5×5 square around it (type-specific effect) and marks its
coverage channel on the tile in a 16-channel memory grid; roaming walkers prefer neighbours whose
memory is lowest, which spreads walkers over the network. Service buildings spawn a walker at
cycle step 31 (once per 51 ticks) after a delay that depends on the employment percentage.

## 1. Data

### 1.1 Figure record (`figures[2000]` at `0x00DBD788`, 0x184 bytes)

Fields already in `re/structs/figure.tsv` are marked (=). New names are in `re/structs/walkers.tsv`.

| Off | Type | Name | Meaning / evidence | Status |
|---|---|---|---|---|
| +0x01 | u8 | anim_frame | walking frame 0..11 (`+1`, wraps at 12) in handlers; 0..31 while fighting | verified (writes) |
| +0x04 | u32 | sprite | image id computed by the handler each tick | verified |
| +0x08 | u16 | next_on_tile (=) | per-tile chain, head in `grid_figure` `0x00D0D878` | verified |
| +0x0A | u8 | type (=) | figure type 0..77 = Figure_model row | verified |
| +0x0B | u8 | subtype | per type: produced resource of a cart (`b+0x43`), god record index (type 0x43), monster id (0x44)… | verified (uses) |
| +0x0C | u8 | in_line_move | 0 each tick in roamer handlers, 1 while leaving a building in a straight line (action 7) | hypothesis |
| +0x0D | u8 | init_1 | set to 1 at creation, no reader found | verified (write) |
| +0x0E | u8 | state (=) | 0 free, 1 alive, 2 delete after this tick's handler | verified |
| +0x0F | u8 | owner | 1st arg of `figure_create`; spawners pass building `+0x01` | verified (write); meaning hypothesis |
| +0x11 | i8 | direction | 0..7 (see §3.3); 8 = at destination, 9 = must re-route, 10 = lost, 11 = attacking an obstacle | verified |
| +0x12 | i8 | prev_direction | direction of the last completed tile step (used to forbid U-turns and for drawing when `direction` ≥ 8) | verified |
| +0x13 | i8 | saved_direction | direction kept while `direction` = 11 | verified (writes) |
| +0x14,+0x16 | i16 | x, y (=) | tile | verified |
| +0x18,+0x1A | i16 | prev_x, prev_y | tile before the last tile change (also set at creation) | verified |
| +0x1C | u8 | line_counter | decremented by the line mover `0x004D9750` | verified (write) |
| +0x20 | i32 | tile (=) | `0x00DA2F80 + 228*y + x` | verified |
| +0x24,+0x26 | i16 | dest_x, dest_y | destination tile for route search | verified |
| +0x2C,+0x2E | i16 | origin_x, origin_y | creation tile copy | verified (write) |
| +0x36 | i16 | action_timer | wait countdown (action 6), dying counter (action 4, deletes at 127) | verified |
| +0x38 | u8 | action (=) | handler state; generic values below | verified |
| +0x39 | i8 | tile_progress | 0..14 sub-step inside a tile, 15 = standing at a tile center | verified |
| +0x3A | i16 | route_id | 1..999 slot in the route table, 0 = none | verified |
| +0x3C | i16 | route_step | next index into the route | verified |
| +0x3E | i16 | route_len | number of directions in the route | verified |
| +0x40 | u8 | field_40 | cleared by the line mover | verified (write) |
| +0x41 | u8 | field_41 | cleared by `0x004D7580` when off road | verified (write) |
| +0x42 | i16 | max_roam | roam budget, rewritten every tick by the handler (e.g. 0x900, 0xC00, 0xF00) | verified |
| +0x44 | i16 | roam_len | roam budget used: `+= speed code` per tick of roaming | verified |
| +0x46 | u8 | roam_started | 0 = still walking a route to `dest` before roaming | verified |
| +0x47 | u8 | roam_tiles | +1 per tile reached while roaming; feeds the pseudo-random turn | verified |
| +0x48 | i8 | turn_step | +2 or −2: rotation used when the preferred direction is closed | verified |
| +0x49 | i8 | turn_countdown | −1 (0xFF) = choose a new turn rule at once; 5 after a choice; 100 after a route walk | verified |
| +0x4A,+0x4C | i16 | fine_x, fine_y (=) | 15 × tile at a tile center | verified |
| +0x4E,+0x50 | i16 | line_tx, line_ty | line move target (fine) | verified |
| +0x52,+0x54 | i16 | line_dx, line_dy | remaining |Δ| (fine) | verified |
| +0x56 | i16 | line_err | Bresenham error term | verified |
| +0x58 | u8 | line_major | 1 = x major, 2 = y major | verified |
| +0x5A | i16 | building_id (=) | home building | verified |
| +0x5C | i16 | linked_flag | if nonzero at deletion, clears home `b+0x2E` | verified (use); meaning hypothesis |
| +0x5E | i16 | dest_building | target building (venue, delivery, house…) | verified (writes) |
| +0x60 | i16 | formation_id | index in `figure_groups` (0x9C records) | verified |
| +0x62 | u8 | formation_slot | slot 0..7 in its formation | verified |
| +0x65 | u8 | hidden | 1 while inside a building / not interacting; `0x004D4DA0` skips figures with it | hypothesis (name) |
| +0x66 | u8 | service_scratch | per-type value kept by the tile service (e.g. clerk tax, superintendent risk) | verified (writes) |
| +0x68 | i16 | escort_id | figure this one is attached to (checked for types 0x41/0x3E in the speed bonus) | hypothesis |
| +0x70 | i16 | name_index | name number in the type's name group (`0x004DD040`) | verified |
| +0x72 | u8 | route_mode | which route search to use, see pathfinding.md §4 | verified |
| +0x74 | i16 | cargo_amount | amount carried (carts); subtracted from storages at deletion | verified (uses) |
| +0x76 | u8 | water_route_mode | nonzero = ship routing (1..3) | verified (dispatch) |
| +0x77,+0x78,+0x79 | u8 | slope_timer, slope_offset, slope_target | elevation draw offset on ramps (`0x004D7580`, `0x004D94F0`) | verified (writes) |
| +0x7A | u8 | cargo_resource | resource carried (checked 9/0xB/0x10/0x13 at spawn) | hypothesis |
| +0x7C,+0x7E | u8 | rand_a, rand_b | `random & 3` at creation | verified |
| +0x82 | i16 | target_id | figure this one attacks/targets | verified |
| +0x84 | i16 | attacker_id | cleared each tick unless `figures[attacker_id]` is alive and targets this figure | verified |
| +0x86 | i16 | serial (=) | creation number (`figures_created` `0x00EF57F0`) | verified |
| +0x8B | u8 | fight_mode | combat helper state (0x004D5F10) | verified (uses) |
| +0x8C,+0x8E,+0x90 | i16 | fight_a, fight_b, opponent_id | combat partners | verified (uses) |
| +0x92 | u8 | group_index | 0 at creation; enemy ships use it as group index | verified (uses) |
| +0x10C | u32 | flags | 0x2 = targeted by someone (cleared with all `target_id` links on deletion); 0x10 = in formation; 0x80000 = override: run `0x004CC160` (go home) instead of the type handler | verified |
| +0x11C | i32 | prev_tile | tile index of `prev_x, prev_y` | verified |
| +0x132 | u16 | field_132 | 0xFFFF at creation | verified (write) |
| +0x14C,+0x14E | i16 | roam_start_x, roam_start_y | tile where roaming began (`0x004D6630`) | verified |
| +0x160 | u8 | speed_phase | sub-tick counter of the speed pattern | verified |
| +0x180 | u32 | sprite_extra | cleared with `sprite` | verified (write) |

Names already given by other agents in `re/structs/*.tsv` take precedence in the struct files:
+0x0B `resource`, +0x10 `saved_action`, +0x13 `fight_direction`, +0x2C/+0x2E `home_x/home_y`,
+0x36 `timer`, +0x42/+0x44 `visit_length/visit_elapsed` (this doc: `max_roam/roam_len`; a
correction is proposed in `re/structs/walkers.tsv` because every roamer uses them),
+0x66 `service_max_seen`, +0x68 `leader_figure`, +0x74 `amount`, +0x76 `water_mode`,
+0x7A `cargo_ref`, +0x82 `missile_target`, +0x84 `attacked_by`, +0x8B–+0x90 opponents,
+0x92 `ready_level`, +0x10C `flags`. Only the other rows are added by `re/structs/walkers.tsv`.

Generic `action` values (shared by most handlers; per-type meanings differ above 6):
4 = dying (`0x004D60B0`: `action_timer` +1 per tick, delete at 127), 5 = fighting (`0x004D5F10`),
1/2 in the generic roamer (roam / return), 6..0x0B in the culture handler (§5.3). **verified**

### 1.2 Figure type table (`0x00639698`, 78 rows × 0x28)

`walkers_update` calls `*(0x0063969C + type*0x28)`, i.e. column +0x04 of a row that starts at
`0x00639698`. Columns: +0x00 enum string (`FIG_IMMIGRANT`…), +0x04 handler, +0x08 image
refresher (`0x004CC3D0`, or `0x004CC3F0` for type 1), +0x0C **coverage_channel** (−1 or 0..11),
+0x10 text id (hypothesis), +0x14 flags (two bytes read by `0x005ABB90`, drawing/selection),
+0x18 name group (used by `0x004E34F0`/`0x004DD040`), +0x1C/+0x20/+0x24 sprite groups.
Row t's name is at `0x00639698 + 40t` (the arm64 notes read it 4 bytes late, which shifted every
name by one type). Type numbers = Figure_model row numbers (`extracted/model/model_*.json`
"figures"); e.g. 11 rabble/archer, 12 hoplite, 13 horseman (deletion takes `horses` for 13,
`arms` for 12 and 13: `0x004DA250`). The full list with handlers is in `figure_handlers.json`.
**verified**

Handler families (from callees; per-type behaviour belongs to other subsystems):

| Family | Types (handler) |
|---|---|
| generic roamer `0x004CDEE0` (§5.2) | 22 disgruntled (`0x004B5A20`), 26 peddler (`0x004B6720`), 27 mugger (`0x004B68B0`), 32 healer (`0x004B78A0`), 38 nobleman (`0x004B90F0`), 60 water bearer (`0x004C0BC0`) |
| own roamers using `0x004D6630`/`0x004D6790` | 7 clerk/tax (`0x004AF550`), 8 superintendent (`0x004AF930`), 61 watchman (`0x004C0CF0`), 58 artisan, 66 plague walker, 67 god, 69 hero |
| culture: roam, then venue (§5.3) | 15–18 and 72–75 share `0x004B4370` |
| route walkers (`0x004D1170` only) | 1–3 migrants, 4 cart, 9 storehouseman, 36 deliveryman, 19–21 trade, herders, hunters, woodcutter, miner… |
| soldiers / formations | 11, 12, 13 (`0x004B31F0`, `0x004B26B0`, `0x004B1840`), 14 standard |
| stubs (no movement) | 0 (`empty_function`), 6, 10 fire, 24, 33 worker (validates home only), 54, 70 |

### 1.3 Speed (model column 8)

`speed = figure_type_value(f, 8)` (`0x004E1B20`): model value `0x00786068[type*14 + 8]`, except:
- types 4 cart, 9 storehouseman, 0x1C (28), 0x24 deliveryman: if god record 7 (`0x00EF5F44`,
  probably **Hermes**, hypothesis from god order) has a finished sanctuary and `escort_id` is 0
  or not of type 0x41/0x3E → `model_speed * 133 / 100` (6 → 7).
- types 0x13–0x15 (trade): same sanctuary → `model_speed * 150 / 100`.
- type 0x39 trireme: scaled by employment (≥ 3).
**verified** (sanctuary record from the `mov ecx, 0x00EF5F44` before `0x004E9440`)

Speed code → sub-steps per tick (`0x004D1170` route walking, `0x004D6790` roaming; identical
patterns; `c` = `speed_phase`):

| code | per tick | pattern | avg |
|---|---|---|---|
| 0 | 0 | — (still runs route set-up) | 0 |
| 1 | `c>2 ? (1, c=0) : (0, c++)` | 0,0,0,1 | 1/4 |
| 2 | `c<2 ? (0, c++) : (1, c=0)` | 0,0,1 | 1/3 |
| 3 | `c==0 ? (1, c=1) : (0, c=0)` | 1,0 | 1/2 |
| 4 | `c<2 ? (1, c++) : (0, c=0)` | 1,1,0 | 2/3 |
| 5 | `c<3 ? (1, c++) : (0, c=0)` | 1,1,1,0 | 3/4 |
| 6 | 1 | 1 | 1 |
| 7 | `c<3 ? (1, c++) : (2, c=0)` | 1,1,1,2 | 5/4 |
| 8 | `c<2 ? 1 : 2` | 1,1,2 | 4/3 |
| 9 | `c==0 ? 1 : 2` | 1,2 | 3/2 |
| 10 | `c<2 ? 2 : 1` | 2,2,1 | 5/3 |
| 11 | `c<3 ? 2 : 1` | 2,2,2,1 | 7/4 |
| 12 | 2 | 2 | 2 |
| 13 | `c<3 ? 2 : 3` | 2,2,2,3 | 9/4 |
| 14 | `c<2 ? 2 : 3` | 2,2,3 | 7/3 |
| 15 | `c==0 ? 3 : 2` | 3,2 | 5/2 |
| 16 | `c<2 ? 3 : 2` | 3,3,2 | 8/3 |
| 17 | `c<3 ? 3 : 2` | 3,3,3,2 | 11/4 |
| ≥18 | 3 | 3 | 3 |

Each branch that takes the first alternative increments `c`; the other resets it to 0 (exactly
as in the column "pattern"). **verified**

## 2. Lifecycle

### 2.1 Free list (not saved)

Ring buffer of 1,999 ids at `0x00DBB84C` (`free_ids`), read index `0x00DBB840`, write index
`0x00DBB844`, count `0x00DBB848`; indices wrap after 1998 (`> 0x7CE → 0`). Also
`0x00DBB838` = highest id ever used, `0x00DBB83C` = highest live id.
- New city `0x004D9ED0`: zero all records; push 1, 2, …, 1999.
- After loading `0x004D9F40`: push every free slot from **1999 down to 1**; for live records call
  the counter hook `0x004E3420(id, +1)` (and `0x00410490` for type 6).
So after a load, new figures get the **highest** free ids first; in a new city the lowest.
Freed ids go to the tail (FIFO reuse). **verified**

### 2.2 `figure_create(owner, type, x, y, direction, place)` `0x004D9FD0`
```
if count == 0: return 0
id = free_ids[read]; read = (read+1) wrapped; count -= 1
if id <= 0 or figures[id].state != 0: return 0          # slot consumed anyway
zero 388 bytes
state=1; owner=owner; type=type; +0x0C=0; +0x0D=1; +0x132=0xFFFF
serial = figures_created++ (0x00EF57F0)
direction = direction arg
x,y = prev_x,prev_y = dest_x,dest_y = origin_x,origin_y = (x,y); tile = base+228y+x
fine_x = 15x; fine_y = 15y; tile_progress = 15; +0x92 = 0
random_next()        # inline: history[0x00F13624] = rand7; idx (wrap 100); both LFSRs 31 steps
rand_a = rand_b = (0x00F137E4 & 0x7FFF) & 3
name assignment 0x004DD0B0 (not for types 6, 10, 14): group g = row+0x18 (or overrides in
   0x004E34F0); if size[g] (0x00F27F34 + 8g) == 0: name_index = 0 else name_index = counter[g] % size[g];
   counter[g] (0x00EF5800, saved rank 113) += 1
if place: figure_tile_list(id)
if type in (0x13, 0x14): 0x005B9DF0(id)                 # trade
update 0x00DBB838 / 0x00DBB83C maxima
0x004E3420(id, +1): soldiers 0xB–0xD and 0x39 → 0x00FEB0C8 += 1; enemies 0x28–0x2A, 0x3F, 0x40 → 0x00FEB084 += 1
return id
```
**verified**
First handler call: walkers_update 0x004CC8C0 tests each slot as it reaches it, so a figure created before the pass
(cycle step, terrain events) or during it with a later slot than the acting figure runs in that same tick; an earlier
slot from the next tick. Ours: `walkers.add` (military.md "In-tick order").

### 2.3 Deletion `0x004DA250(id)`
Called by `walkers_update` when a handler left `state == 2` (and by four other functions).
Type-specific cleanup first (cross-references: formation slot hand-over and arms/horses refund
for 0xB–0xD; building walker counters `b+0xA8`/`b+0xA9`; trade slots `0x008FBACC`; storage
reservations `b+0x114/+0x116`; building links `b+0x2A`, `b+0xB8`, `b+0x2C`, `b+0xBC[4]` for
docks/trading posts; monster/god hooks). Then, for every type:
```
if +0x5C != 0: b(home).+0x2E = 0
free route (0x004D8990)        # route_owner[route_id] = 0 if it was us; route_id = 0
remove from tile list (0x004DCA70)
if flags & 2: clear flag; every figure with target_id == id gets target_id = 0   (0x004E32C0)
0x004E3420(id, -1)             # counters, clamped at 0
zero 388 bytes
if id >= highest_live: walk highest_live down past free records
free_ids[write] = id; write wrapped; count += 1
```
**verified**

### 2.4 `walkers_update` `0x004CC8C0` (tick part 7, every tick)
```
processed = 0                                  # 0x00EF57E8
for cur = 1..1999:                             # cur = 0x00EF57EC (global "current figure")
  f = figures[cur]; if f.state == 0: continue
  if f.attacker_id: if figures[a].state != 1 or figures[a].target_id != cur: f.attacker_id = 0
  processed += 1
  if (f.flags & 0x80000) == 0 or f.type == 0x2B: handler[f.type]()   else: 0x004CC160()
  if f.state == 2:
     if type == 0x44 and !(flags & 0x80) and !0x00587020(f.subtype) and !0x004812F0(f.subtype): 0x00481350(f.subtype)
     if type != 0: delete(cur)
if month (0x0091EC08) changed: 0x004CC850 — every grid_figure head pointing at a free record is
   replaced by that record's next_on_tile
```
Handlers take no argument: they read `0x00EF57EC`. Handlers run for state 2 records too.
The profiling timers `0x004CC730`/`0x004CC760` only measure. **verified**

Override handler `0x004CC160` (flag 0x80000, set for all eligible live walkers by
`0x004EDE80`, a religion/event function, which also sets action 2 and `dest` = home road tile):
route mode 0x0D; delete if home building state ≠ 1; action 2 → move; on direction 8 or 10
delete (8 also sets `hidden`), on 9 free the route; action 4 → dying. **verified**

## 3. Movement

### 3.1 Sub-tile stepping
A tile is crossed in 15 sub-steps. `fine_x/fine_y` change by ±1 per sub-step along the direction
(both for diagonals; `0x004D94F0`), so a center is at `15*tile`. `tile_progress` counts
sub-steps. Route walking, one tick (`0x004D7BD0(f, n)`, n = sub-steps from §1.3):
```
if route_id < 1:                                       # no route yet (or freed for re-route)
    find_route(f) (0x004D8220); next_dir(f) (0x004D8B10); check_next_tile(f) (0x004D8BB0)
    if direction > 7: return
repeat n times:
    tile_progress += 1
    if tile_progress > 14:                             # reached a tile center
        tile_service(f) (0x004DFB70, §6)
        tile_progress = 15
        if route_id < 1: find_route(f)
        next_dir(f); check_next_tile(f)
        if direction > 7: return                       # stays at the center (progress 15)
        route_step += 1; prev_direction = direction; tile_progress = 0
    if tile_progress == 8: change_tile(f) (0x004D9330)
    fine_step(f) (0x004D94F0)
0x00DBB830 = 0 on exit
```
`next_dir` (`0x004D8B10`): without a route, `direction = dir_to(x,y → dest)`, and if that is
not 8 (already there) it becomes 10 (lost). With a route: if `route_step >= route_len`: free
the route, `direction = 8`; else `direction = routes[route_id*500 + route_step]`. **verified**

`change_tile` (`0x004D9330`, only if direction < 8): remove from the tile list, move x/y/tile by
the direction, append to the new tile list, `prev_x/prev_y/prev_tile` = old tile, slope update
`0x004D7580`, then encounters with figures already on the tile `0x004D4DA0(f, head)` (combat;
military agent). So the tile changes after 8 sub-steps, before the 9th fine step. **verified**

### 3.1a Tile lists (settled 11-03, bugs.md 438) **verified (disassembly + oracle)**
- Storage: `grid_figure` `0x00D0D878` (u16 head per tile, 228 x 228, cleared with the grids; not in the save zones,
  dumped with ZEUS_STATE_DUMP_EXTRA), each figure's `next_on_tile` +0x08 (record base `0x00DBD788`, 0x184 a figure).
- Insert, `figure_tile_list` `0x004DC860`: walks the chain from the head; the figures whose tile +0x20 is this tile
  are relinked in their order (the first one becomes the head), the stale ones (tile changed without an unlink) into
  a side chain; then the figure is **appended** after the last kept one (head when none), unless it is already in
  the chain; its own +0x08 is not written (the caller's unlink zeroed it, figure_create zeroes the record). Callers:
  figure_create `0x004D9FD0` (when placed, param 6), figure_change_tile `0x004D9330` (unlink, move, list), the line
  move `0x004D9750`, and every jump (unlink, set x / y / tile, list: soldiers to their slot `0x004B1290`, home
  `0x004B11C0`, formation deploy `0x004DD250`, figure_place_on_tile `0x004E3220`, effects, ...).
- Remove, `figure_tile_unlink` `0x004DCA70`: head -> head = its next; else the predecessor's next = its next; its
  own next = 0. figure_delete unlinks. Monthly `0x004CC850` skips heads pointing at free records.
- Readers walk head first (fight contacts, missile hits `0x004DCE00` / `0x004DCE20`, the presence grid, the
  muster spot, `0x004A41C0`, ...): the earliest arrival first.
- **Drawing rewrites it**: city_draw `0x00458170` and tile_walkers_draw `0x0045A5A0` call `tile_walkers_sort`
  `0x00449B30` on every tile they draw: qsort (comparator `0x00449B10`) by rank, then id, and the chain is relinked
  in that order (lists of more than 49 figures are left alone). Rank: -100 when state != 1 or action 4, -50 for
  type 6 kind 13, else the figure's height in its tile: `0x005F06D8[(dir - view) * 16 + tile_progress]` (dir 8+ ->
  prev_direction, 8+ -> 0), or for a line move `0x005F0358` / `0x005F0558` by fine position and view. So in the exe
  a tile on screen is in draw order after each frame (a newcomer walking south-east, rank -12 at progress 8, goes
  before a standing figure, 0), a tile off screen stays in arrival order: the simulation depends on the camera.
- Oracle (tools/oracle_tile_order.py, "See a working city", dumps of grid_figure and the figures every tick 20..320):
  1B-tile-order (camera on the city): every list of 2+ figures in arrival order or draw order, 82 only in draw
  order, all on the tiles on screen; 1B-tile-order-away (camera poked to logical (110, 10) from tick 30): dumps
  32..320, 4,919 lists, 0 not in arrival order, newly created figures last (15). 1B-inv-city-horse (no grid dump,
  heads from the links): 1853 -> 1878 at dump 946 is draw order (1853 entered at progress 8 heading SE, rank -12).
- Ours (`walkers.listed` / `walkers.tile_order`, contact.order): the arrival rule, everywhere: a stamp `tl` = tick x
  2^20 + the entry's number in that tick, set at creation (walkers.add), each step (step_to) and each jump. The
  draw sort is not ported (ours, by design: the simulation must not depend on a view; the exe's order is the
  arrival order wherever the player is not looking). Walkers from older saves: tick entered, then slot.

### 3.2 Line movement (leaving/entering buildings)
`0x004D9980(f, fx0, fy0, fx1, fy1, flag)` sets up a Bresenham walk between fine points; the
direction is `dir_to`, snapped to orthogonal when one axis is less than half the other;
`0x004D9750(f, n)` advances n fine steps, then recomputes `x = fine_x/15`, `y = fine_y/15`
(clamped to the map), tile, and re-inserts the figure in the tile list; returns 1 when done.
**verified**

### 3.3 Directions
`0` = y−1, `1` = x+1,y−1, `2` = x+1, `3` = x+1,y+1, `4` = y+1, `5` = x−1,y+1, `6` = x−1,
`7` = x−1,y−1 (tile offsets `0x0064324C` = −228, −227, +1, +229, +228, +227, −1, −229; same
table at `0x006394AC` and `0x00637FD4`). `dir_to(x0,y0,x1,y1)` `0x0058CFF0` returns the octant
of the target, 8 if equal. Opposite = `(d+4) & 7`. **verified**

### 3.4 Per-tile figure list (`grid_figure` `0x00D0D878`, u16 head per tile)
`figure_tile_list(id)` `0x004DC860`: walks the chain at the figure's tile (type 6 uses a turned
tile `tile_turn_offset`); entries whose tile differs are unlinked from the chain; `id` is
appended at the **tail** if absent. `0x004DCA70` unlinks. `0x004DC800` breaks a cycle
("Corrected a circular figure list"). If `0x007CBDC8` is set, a figure (except types 6, 0xE,
0x14, 0x15, 0x18, 0x19, 0x1C, 0x22, 0x23, 0x2C, 0x2D, 0x2F, 0x30, 0x34, 0x36, 0x39, 0x3F,
0x40, 0x43–0x45) placed on terrain `0x1000000` or on water (`0x4`) without `0x00CB4B08` gets
`state = 2`. **verified**

### 3.5 Obstacles on the way (`check_next_tile` `0x004D8BB0`, route walking only)
For a land walker in an ordinary mode, the tile ahead `t` (terrain `T`, building `b`):
- `T` has road (0x40) or ramp (0x400): passable. But while `0x00DBB830 = 1` (a roamer walking its
  pre-roam route), a gatehouse (0x83) → 9 and a roadblock (0x7B) or type 0xA4 → 9 unless the
  walker is type 0x45.
- else wall bits `0xC000` → 9; building (8): passable if orchard/vine/fruit tree
  (0x23, 0x24, 0xD9), avenue/boulevard (0x76, 0x7E), race track (199), or a composite part that
  `0x00546530` allows; terrain `0x10000000` asks `0x004CC5A0(mode)`; anything else → 9.
- water (4) without building: allowed only for modes 0, 3, 0xD when route bit 0x10 is set.
Military modes (2, 8, 10, 12, 16), wall mode 4, ships (`water_route_mode`) use other grids and
may set 11 (attack wall/gate: `0x00492830`), see the military agent. **verified**

## 4. Destination walkers (route following)

Handler pattern (`0x004CDEE0` return leg, culture action 8/0xB, carts…): set `dest`, free the
route, then each tick `0x004D1170(f, speed)`; react to `direction`: 8 = arrived, 9 = free the
route (a new one is searched on the next call), 10 = lost (usually delete). The route itself
is searched at the first sub-step without a route (pathfinding.md). **verified**

## 5. Roaming

### 5.1 Start `0x004D6630(f)` (called right after spawning)
```
tile_progress = 15; roam_started = 0; turn_countdown = -1; turn_step = 2
roam_start = (x, y)
repeat up to 4 times: d = first_roam_dir(f) (0x004D6210); if d != -1: break
if all 4 failed: roam_started = 1; return
b(home).+0x34 = d (0 if > 6)            # only read by wall sentries (0x004CFD80)
dest = home road tile (b+0x26, b+0x28; agora/special types 0x3F/0x40 via 0x0040D7B0/0x0040D7E0), clamped to the map
roam_started = 1
```
`first_roam_dir` is the same choice as §5.4 with three differences: neighbours count if
terrain & `0x440` (road or ramp); a gatehouse (0x83) always closes a side, 0x7B/0xA4 unless the
walker is type 0x42; coverage filtering applies as soon as 2 sides are open. **verified**

### 5.2 Generic roaming service walker `0x004CDEE0` (used by 6 types)
The type stub first sets `route_mode = 1`, `max_roam` (0x900 healer/water bearer/disgruntled/
mugger, 0x960 nobleman, 0xF00 peddler), clears `+0x0C`, deletes the walker when its home
building is not active or `b+0x2A` (the building's walker) is not this figure, and advances
`anim_frame`. Then:
```
speed = figure_type_value(f, 8)
action 5: fight; return.     action 4: dying; return
action 1 (roam):
   hidden = 0
   if roam_len < max_roam and not early_return(f): roam_tick(f, speed); return
   find road near home: 0x004A39D0(b.x, b.y, b.size, 2)  (agora types 0x3F/0x40 use their own point)
   if none: state = 2; roam_tick(f, speed); return
   action = 2; dest = that road tile; free route; roam_len = 0
action 2 (return): move(f, speed); if direction in (8, 9, 10): state = 2
other: action = 1
```
`early_return` `0x004CDE80`: types 0x43–0x45 never; otherwise true when
`roam_len >= max_roam / 2` and the walker stands on `roam_start`. **verified**

Return path search uses route mode 1 (road only, see pathfinding.md). Road near home
`0x004A39D0` tries radius 0, 1, 2 with `0x004A37D0`: the rectangle `[x−r, x+size−1+r] ×
[y−r, y+size−1+r]` (clamped), scanned row by row; a tile counts if terrain & 0x44 == 0x40
(avenue/boulevard building tiles are first moved to their anchor by `tile_step_to_anchor`); the
best is the one whose road network has the lowest rank among the first **5** entries of the
large-network table `0x00FEB0FC` (rank 11 otherwise), first found wins ties. Result in
`0x00F13944` (x), `0x00F13940` (y), `0x00DA2418` (tile). **verified**

### 5.3 Culture walkers `0x004B4370` (types 15–18, 72–75; generic part)
Each tick: `route_mode = 1`, `+0x0C = 0`, `max_roam = 0xC00`; home not active → state 2.
Actions: 6 wait in the building (`action_timer` −1; at 0 find road near home with radius 2 →
action 7 and line move to `b+0x26/+0x28`; none → delete); 7 line move (`0x004D9750(f,1)`), when
done look for a venue `0x00491630` (none → delete) → `dest_building`, action 8; 8 travel
(`roam_len += 1`, delete at 0xC80 = 3,200 ticks; arrival 8 → `0x00491EF0` then delete; 9 →
free route; 10 → delete); 0x0A roam (§5.4; at `roam_len >= max_roam` find home road → action
0x0B); 0x0B return (delete on 8/9/10). Any other action → 6. Spawned with action 6 (college)
or 1/0x0A via the spawner. **verified** (venue logic: services agent)

### 5.4 Roam tick `0x004D6790(f, speed)` and step `0x004D69B0(f, n, special)`
```
roam_len += speed                                        # the speed CODE, every tick
n = sub-steps from the speed pattern (§1.3, with speed_phase)
if roam_started == 0:                                    # walk the route to dest first
    0x00DBB830 = 1; route_walk(f, n)                     # §3.1 (n is not consumed for later)
    if direction in (9, 10): roam_started = 1
    elif direction == 8: roam_started = 1; roam_len = 0
    if roam_started == 0: return
    turn_countdown = 100; direction = prev_direction
repeat n times:
    tile_progress += 1
    if tile_progress > 14:
        tile_progress = 15
        back = (prev_direction + 4) & 7
        roam_tiles += 1
        tile_service(f)                                  # §6
        k = open_road_sides(tile, f)                     # 0x004A31E0, below
        if k < 1:                                        # dead end with no road at all
            if special and 0x004EDE40(f) and !0x004F1720(f) and !(flags & 0x100): flags |= 0x100
            else: roam_len = max_roam (of the current figure)
            return
        elif k == 1: direction = first open of 0, 2, 4, 6           # may be a U-turn
        elif k == 2:
            if turn_countdown == -1: wander(f); back = -1
            if turn_step == 0: turn_step = 2
            rotate(direction)                                       # see below
        else:
            direction = (grid_random[tile] + roam_tiles) & 6        # grid 0x00CA7FF8
            if side closed or direction == back:
                turn_countdown -= 1
                if turn_countdown < 1: wander(f); back = -1
                rotate(direction)
        route_step += 1; prev_direction = direction; tile_progress = 0
    fine_step(f)
    if tile_progress == 8: change_tile(f)                # after the fine step (unlike §3.1)
rotate: up to 4 times: if side[direction] open and direction != back: stop;
        direction += turn_step; if > 6: 0; if < 0: 6
```
In the `k == 2` branch the loop starts from the current `direction` (still the previous one).
If the 4 tries fail, `direction` has gone full circle back to its start value. In the `k < 1`
branch both cases return at once. **verified**

`open_road_sides(tile, f)` `0x004A31E0`: for the four orthogonal neighbours (0, 2, 4, 6), a
side is open if its terrain has road `0x40` (type 0x43 god: `0x440`, plus `0x10000000` when the
current tile has it). A neighbour with a building (terrain 8) is closed for: pyramid pieces
(100–114) if the walker is type 0x43/0x45; gatehouse 0x83 unless 0x43/0x45; roadblock 0x7B and
type 0xA4 unless the walker is 0x42, 0x43, 0x45, 0x16 or 0x1B (plague walker, god, hero,
disgruntled, mugger). If more than 2 sides are open, each open side's coverage memory
`mem(channel, neighbour)` is read and every side with a value above the minimum is closed. The
returned count is after that filtering. **verified**

`wander(f)` `figure_wander` `0x004D6C90` (new turn rule):
- coverage_channel ≥ 0: over sides 0, 2, 4, 6 with road (terrain & 0x40) keep the lowest memory;
  on a tie, draw `random_next` and replace when `rand7 % ties == 0` (ties counted from 1,
  reset when a lower value appears). `direction` = choice (0 if no road). Then `turn_step = 2`,
  draw `random_next` again: if `0x00F137E4 & 1` → `turn_step = −2`. `turn_countdown = 5`.
- channel −1 (heads for `dest`): `d = dir_to(here → dest)` (0 if 8). Search clockwise from `d`
  for the first even direction with road (`cw`, steps `i`), and counter-clockwise (`ccw`, steps
  `j`; default 4 if none). If `j < i`: ccw; if `i < j`: cw, `turn_step = 2`; if equal: draw,
  bit 0 clear → cw with `turn_step = 2`, set → ccw. Choosing ccw sets `turn_step = −2`.
  `turn_countdown = 5`.
**verified** (RNG: inline copy of `random_next` — history push of `rand7`, 31 LFSR steps on both
registers, derived values refreshed; terrain.md §5)

### 5.5 Roam budget
`roam_len` grows by the **speed code** each tick, so `max_roam / speed` ticks of roaming
(0xC00 at speed 6: 512 ticks ≈ 34 tiles; 0x900: 384 ticks ≈ 25 tiles). The generic roamer may
turn back earlier (`early_return`). At the end it searches a route home (mode 1, road only).
**verified** (arithmetic from the code; tile figures are derived)

Budgets (`max_roam` written by each handler every tick; model speed column 8 is 6 for all of
them, so 1 sub-step per tick and 15 per tile). Tiles entered = `(max_roam/6 + 6) // 15`: the walker
starts at a tile center (its first sub-step picks a direction), reaches a new center every 15
sub-steps, and the tile it is walking into counts once it has passed progress 8 (`change_tile`),
because the return walk serves `(x, y)` at its first center (`figure_route_walk` 0x004D7BD0).

| max_roam | ticks | tiles | figures (handler) |
|---|---|---|---|
| 0x900 | 384 | 26 | healer 32 (0x004B78A0), water bearer 60 (0x004C0BC0), mugger 27 (0x004B68B0), disgruntled 22 (0x004B5A20), worker 33 (0x004B79D0, does not roam) |
| 0x960 | 400 | 27 | nobleman 38 (0x004B90F0) |
| 0xC00 | 512 | 34 | clerk/tax 7 (0x004AF550), culture 15–18, 72–75 (0x004B4370), artisan 58 (0x004C0060) |
| 0xF00 | 640 | 43 | superintendent 8 (0x004AF930), watchman 61 (0x004C0CF0), peddler 26 (0x004B6720), priest 65, god, hero |
| 0x12C0 | – | – | agora vendor/buyer 37 (0x004B8D90) and wall sentry 0x004B9230: set but not used for roaming (37 walks a route to storage and back) |

The food/fleece/... vendor's walker that serves houses is the agora's **peddler** (26, 0xF00 →
43 tiles), not the vendor figure 37. Thief/vandal handlers write no budget.

**End of the roam** (`figure_roamer_generic` 0x004CDEE0; culture 0x004B4370 action 0x0A → 0x0B
is the same): the check is per tick, not per tile, so the walker is usually mid-tile. That tick
it sets action 2, `dest` = a road tile next to its home (`road_tile_near_building` 0x004A39D0,
radius 2) and frees the route; from the next tick `figure_move` finds the **shortest road route**
(mode 1) from its current tile and walks it at once, from where it stands (no wait; it does not
retrace its roam). It serves on the way back (`figure_provide_service` at every center).
`early_return` (generic roamer only: peddler, healer, water bearer, mugger, disgruntled,
nobleman): once half the budget is used, standing on `roam_start` (its spawn tile, `0x004D6630`)
sends it home. **verified**

Sim (sim/systems/walkers.py): `rules.walker_roam` (role → tiles, tools/build_data.py
`ROAM_BUDGET`); at `roam_left == 0` the walker plans the path home and steps onto its first tile
in the same tick (serving it), so it turns without standing a tile time; `EARLY_RETURN` roles end
their roam when back on their home's access tile with half their tiles left or fewer.

## 6. Service coverage (generic part)

`tile_service(f)` `0x004DFB70` runs at every tile center reached (route walking and roaming),
except for type 0x26 nobleman and figures with flag 0x80000:
```
served = per-type effect(x, y)          # 0 for types without one
if home != 0: b(home).+0x18 = min(300, b+0x18 + served)
mark(coverage_channel[type], tile)      # 0x004A3100
```
Per-type effects (each scans the **5×5 square** `[x−2, x+2] × [y−2, y+2]` clamped to the map,
over the building-id grid `0x00D26E98`, i.e. once **per building tile**, so a 2×2 house counts
4 times; returns the count):

| Types | Function | Condition on building b | Write (services/economy agents) |
|---|---|---|---|
| 7 clerk | `0x004A67C0` | (see function; uses home `b+0xDB`) | `b+0x4E = 0x32`; scratch → `+0x66` |
| 8 superintendent | `0x004A5D90` | | `b+0x46`, `b+0x48` decreased (risks) |
| 15, 75 | `0x004A60E0` | `b+0x05 != 0` and (`b+0x1C > 0` or house types 9–14), or type 0x7D | `b+0x6C = 0x60` |
| 16, 73 | `0x004A6210` | `b+0x05 != 0`, `b+0x1C > 0` (as healer) | `b+0x6D = 0x60` |
| 17, 72 | `0x004A6340` | idem | `b+0x6F = 0x60` |
| 18, 74 | `0x004A6470` | idem | `b+0x71 = 0x60` |
| 26 peddler | `0x0040D160` (home id passed) | | goods sold (economy) |
| 32 healer | `0x004A66B0` | `b+0x05 != 0` and `b+0x1C > 0` | `b+0x78 = 0x60` |
| 60 water bearer | `0x004A65A0` | idem | `b+0x77 = 0x60` |
| 61 watchman | `0x004A5F70(x, y, model(0x7C, 9))` | | `b+0xF4` |
| 0x42 | `empty_function` | | — |
**verified** (radius, per-tile counting, the 0x60 writes); the meaning of `b+0x05` (is a house?)
and `b+0x1C` (people?) is a **hypothesis** for the population agent.

Coverage memory (`grid_b1e8f8` `0x00B1E8F8`, u32 per tile = sixteen 2-bit fields):
- `mem(ch, tile)` `0x004A30E0` = `(v >> 2ch) & 3`, 0 for ch < 0.
- `mark(ch, tile)` `0x004A3100`: if ch ≥ 0 and `mem < 3`: `v = (v & ~(3 << 2ch)) | (7 << 2ch)`.
  **Quirk**: the `7` also sets the low bit of channel ch+1 (32-bit truncation for ch 15).
- decay `0x004A3140` (cycle step 45, every 8th call → every 8 cycles = 408 ticks): for every
  playable row segment (`0x00DA24B0` start index, `0x00DA2BD0`/`0x00DA2840` bounds), every
  nonzero tile: channels **0..11** decrease by 1 if nonzero (12..15 never decay).
Channels in use (table column +0x0C): 0 water bearer, 1 superintendent, 2 nobleman & watchman,
3 competitor & scholar, 4 vandal, 5 mugger/priest/god, 6 clerk, 7 peddler, 8 healer, 9
philosopher & astronomer, 10 athlete & inventor, 11 actor & curator (also listed: 69 hero 1).
**verified**

## 7. Spawning (generic part of `buildings_spawn_walkers` `0x0048CFB0`)

Runs at cycle step 31, i.e. once per 51 ticks, in tick part 4 (before `walkers_update`, part 7,
of the same tick). For every building `1..buildings_last` with
`state == 1`, by type. The pattern of a roaming-service building (fountain 0x4A/0x4B,
infirmary 0x4C, college 0x4D, podium, gymnasium…):
```
if b+0x18 < 1: b+0xD3 = 2                                   # status shown in the info panel (hypothesis)
w = b+0x2A; if w > 0:
    if figures[w].state != 0 and figures[w].type in (T, 0) and figures[w].building_id == b: skip building
    b+0x2A = 0
if !road_access(b.x, b.y, b.size) (0x004A3B40): skip
pct = (b+0xDA == 0 and model(type,5) > 0) ? b+0x40 * 100 / model(type, 5) : 0     # workers / needed
(fountain: if desirability(b.tile) < 30: pct /= 2)
delay = pct >= 100 ? D1 : >= 75 ? D2 : >= 50 ? D3 : >= 25 ? D4 : >= 1 ? D5 : no spawn
if blocked_types[type] (0x00EF60B0) == 0 and 0x00EF6163 == 0:
    b+0x32 += 1                                             # spawn timer (same byte as sanctuary_finished)
    if delay < b+0x32:
        b+0x32 = 0
        id = figure_create(b+0x01, T, road_x, road_y, 0, 1)
        if id: b+0x2A = id; action = 1 (or 6); building_id = b; roam_start (0x004D6630)
```
D1..D5: fountain 1, 3, 7, 15, 29; infirmary 3, 7, 15, 29, 44; college 8, 15, 30, 50, 100
(other types: services agent). So at full staff a fountain sends a walker every 2nd spawn pass
when the previous one is gone. `0x00EF60B0` (saved rank 126, 221 bytes) is a per-building-type
countdown decremented monthly by `0x004E5EB0`; entry 179 (`0x00EF6163`) acts as a global stop.
**verified** (pattern for 0x4A–0x4D; thresholds read in the code), meaning of the flags hypothesis.

`road_access` `0x004A3B40(x, y, size)`: walks the ring of the building (table `0x005F1680 +
0x60*size`, up to 24 offsets, 0-terminated): the edge tiles adjacent to the sides, no corners,
order top row left→right, right column top→bottom, bottom row right→left, left column
bottom→top. A ring tile qualifies if road (0x40) and not water (4); a roadblock tile (0x7B) is
skipped; an avenue/boulevard building tile without road is replaced by its anchor. The best is
the lowest large-network rank among the 10 entries of `0x00FEB0FC` (network id grid
`0x00C4F288`), first wins ties. Result in `0x00F13944`/`0x00F13940`. **verified**

## 8. Formations (generic level)

`figure_groups` `0x00DB7B40`, 100 records × 0x9C: +0x00 u8 in use, +0x04 i16 member type
(0xB/0xC/0xD for player companies), +0x08 i16[8] member ids (slots 0–3 front, 4–7 reserve
moved forward when a front member dies, `0x004DA250`), +0x2E/+0x30 i16 position (first live
member when +0x90 is set and +0x5E < 1), +0x69 u8 (if nonzero the group is ignored by
`figure_type_value`), +0x6A u8 (enemy kind, clamped to 10), +0x78 i16 building, +0x82 i16
(negative = counted in `0x00FEB4F4`), +0x90 u8, +0x94 i32. `formations_update(p)` `0x004DDD30`
(cycle steps 5 with p=0 and 29 with p=1): p=0 → counts `0x004DDD70` and `formations_refresh`;
always `0x004DE830`, `0x004DDEE0` (soldiers in action 6 count down `+0x9C`), p=0 →
`0x004DDF20`; `0x004DE770`, `0x004DF410`; p=1 → `0x00500910`; `formations_pass`. Details:
military agent. **verified** (call order, listed offsets); field names hypothesis.

## Scheduling notes
All live walkers are updated every tick in slot order (no active list, no frame divider; `walkers_update` loops slots 1..1999). Ours (11-02): sim/model.Walkers keeps the exe's slot ring (2.1 / 2.2) as `fslot`, systems/walkers.move_all runs the walkers due in a tick in slot order, wake_now lets a later slot act in the running pass (military.md "In-tick order"). Speed codes only change sub-steps per tick; decisions happen at tile centers every 15 sub-steps. Coverage is written as 0x60 timers on houses which decay 1/day. Details and what to copy: time-core.md §9.

## Cross-references (other subsystems)
- Services: venue search `0x00491630`, venue arrival `0x00491EF0`, per-service effects (§6).
- Economy: carts `0x004AD760`, `0x004ADBA0`, `0x004ADF30`; storage `storage_select`, `0x004895B0`;
  peddler `0x0040D160`, agora `0x0040AA20`/`0x0040ACE0`.
- Population: immigrant/emigrant/homeless handlers (types 1–3), house selection `0x00494EA0`.
- Military: combat `0x004D4DA0`, `0x004D5F10`, `0x004D54D0`; soldiers `0x004B1630`; attack on
  walls/gates `0x00492830`; route mode 2/8/10/12/16 grids.
- Religion: gods/heroes/monsters handlers, override flag set by `0x004EDE80`, sanctuary bonus
  via `god_sanctuary_finished` `0x004E9440`.
- Map: building road tile `b+0x26/+0x28` (`buildings_road_access` step 21), route grid builder
  `0x005876F0`, building grid `0x00D26E98`.

## Open questions
- Exact meaning of `owner` (+0x0F, from building +0x01), `+0x0C`, `hidden` (+0x65), `+0x5C`.
- Per-type spawn thresholds and initial actions for all other buildings (services agent).
- `b+0x18` (incremented by houses served, capped 300; set to 0/100 by `0x005B0590` in cycle step
  12): what reads it besides the spawn status `b+0xD3`.
- The 41 handlers are not decompiled (Ghidra did not create functions at table targets); only
  their callees and stores were read by disassembly. Making them functions in Ghidra would help.
- Who sets `0x007CBDC8` (tile-list deletion check).
- Flags +0x14 of the type table (two bytes) and text id +0x10: confirm their use.
