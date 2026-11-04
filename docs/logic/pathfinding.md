# Pathfinding (routes for walkers)

Status: **verified** from the exe unless marked **hypothesis**. Addresses: GOG `Zeus.exe`.
How walkers use routes: [walkers.md](walkers.md) §3–§5.

## Summary

A walker that needs to go somewhere gets a **route**: a list of directions (0..7) from its tile
to `dest` (+0x24/+0x26), stored in one of 999 route slots. The route is computed by a
breadth-first flood from the walker's tile over a passability grid (which grid and which bits
depend on the walker's `route_mode` +0x72), writing distances in a shared distance grid; then
the path is traced back from the destination by always stepping to a neighbour with a smaller
distance. All searches share one distance grid and one queue, so only one route exists in the
grid at a time. There is no A*; the cost of a search is the area flooded before the
destination is dequeued.

## 1. State

| Address | Type | Name | Meaning |
|---|---|---|---|
| `0x0105FE40` | u16[51984] | grid_route | passability bits per tile (§2), rebuilt by `0x005876F0` |
| `0x01079460` | i32[51984] | grid_distance | 0 = not reached, 1 = source, n = BFS depth (or weighted cost) |
| `0x010AC0A0` | i32[51984] | route_queue | ring of tile indices; head `0x0102D1FC`, tail `0x0102D1F8`, wraps after 51983 |
| `0x0102D1F4` | i32 | route_src_tile | last source (or destination in the tracer) |
| `0x0102D1C4` | i32 | route_searches | +1 per search (statistics) |
| `0x010DF2C0` | i32 | distance_grid_dirty | 1 after a plain BFS: invalidates the `route_search` cache |
| `0x010DF2C8..D4` | i32×4 | route_cache_src_x/y, dst_x/y | last `route_search` request |
| `0x010DF0C8` | u8[500] | route_trace_buf | directions while tracing back |
| `0x00E7AEC8` | u8[1000][500] | routes | route directions per slot (saved rank 30) |
| `0x00EF4FE8` | u16[1000] | route_owner | figure owning each slot (saved rank 29) |
| `0x01046820` | i8[51984] | grid_military | military/enemy passability (§5) |
| `0x01039D10` | u8[51984] | grid_walls | wall walkers (mode 4) |
| `0x01053330` | u8[51984] | grid_ship | ship passability (`0x00587B90`, §7): 0 open, 0xFB shore, 0xFE edge, 0xFF blocked |

Indices are `0x00DA2F80 + 228*y + x`; the searches do no bounds test (the map border is never
passable). **verified**

## 2. Route grid bits (`0x005876F0(x0, y0, x1, y1)`, over a clamped rectangle)

Called for the whole map by `0x00587B30` (after clearing) from many places (building placement,
road changes, cycle steps 21, 39, 40, 43, 44, month change…), and for small rectangles by ten
others. For each tile with terrain `T` (`0x00CCE128`):
```
if T & 0x80000 or T & 0x10004 == 0x10004:            |= 0x02  (blocked)
elif T & 0x400 and T & 0x40 and not T & 0x800000:    = 0x100  (road on a ramp; replaces)
elif T & 0x40 (road):                                 |= 0x04
    if T & 0x8008: b = building at tile
        b == 0: stale building bit: clear terrain 8, reset ground image (counter 0x010DF2DC)
        b is race track (199): 0x0056F3B0(tile, b) ? |= 0x200 : |= 0x02
elif T & 0x400 or T & 0x20 (garden):                  |= 0x10
elif T & 0x200 (cliff):                               |= 0x02
elif T & 0x20000 and regrowth[tile] != 0xFF:          |= 0x80  (resource regrowing)
elif T & 0x10000000:                                  |= 0x20
elif T & 0x8008: b = building at tile
    b == 0: stale building bit cleared (as above), nothing set
    0x7B roadblock: |= 0x04;  0xA4: |= 0x20;  0x86 horse corral: |= 0x40
    0x23, 0x24, 0xD9 (orchards), 0x76, 0x7E (avenue, boulevard): |= 0x10
    composite or pyramid piece (100..114): 0x00546530(b) ? |= 0x20 : |= 0x02
    199 race track: as above;  anything else: |= 0x02
elif tile object (0x00666930) with +0x18 == 0: v = ground image − base:
    0 ≤ v < 6: |= 0x10;  v in (6, 8, 10, 12): |= 0x01;  else |= 0x02
elif T & 0x10000 and not water: |= 0x10
elif T & 0x61001 (tree, rubble, 0x20000, reeds) and not water: |= 0x10
elif T & 0x2DFFD66F: |= 0x02
else: |= 0x10                                         (open land)
```
Bit meanings (names are hypotheses from the cases above): 0x01 decor object, 0x02 blocked,
0x04 road (and roadblock), 0x08 no writer found, 0x10 open land, 0x20 walkable building part,
0x40 corral, 0x80 regrowing resource, 0x100 ramp road, 0x200 race track special. **verified**
(cases), meanings **hypothesis**.

A ramp (0x400) is open land even on a cliff tile (0x200): its case comes before the cliff's (ours: walkable(),
11-01, bugs.md 369). Trees (0x1), rubble, marble and reeds are open land (0x10) here, so every land route crosses forest; only
roaming (road tiles, §6), grazing (`0x00587FB0`, tree bit in its mask) and route mode 1 (roads only) avoid it.
Ours (sim/systems/walkers.py `walkable`, 2026-10-28): immigrants, emigrants, homeless, gatherers (woodcutters,
quarrymen, miners, growers, hunters, herders, ranchers), caravans and firefighters walk through forest; grazers keep
`open_walkable` (no trees).

Masks used by the searches: `0x11D` land (open land, roads, ramps, decor), `0x11C` land
without decor, `0x10C` roads only, `0x12C` roads + building parts, `0x13C`/`0x13D` land +
building parts, `0x15C` + corral, `0x19C` + regrowing, `0x0C` roads only (no ramps), `0x200`
race track.

## 3. Breadth-first search (template: `route_distance` `0x00588920(sx, sy, dx, dy)`)
```
clear grid_distance (51984 ints); distance_grid_dirty = 1; route_searches += 1
src = tile(sx,sy); dst = tile(dx,dy)
grid_distance[src] = 1; queue = [src]; head = 0; tail = 1
loop:
    t = queue[head]
    if t == dst: break
    d = grid_distance[t] + 1
    for off in (-228, +1, +228, -1):                  # N, E, S, W, in this order
        n = t + off
        if grid_distance[n] == 0 and grid_route[n] & MASK: grid_distance[n] = d; queue[tail++] = n (wrap)
    head += 1 (wrap)
    if head == tail: break
return dst >= 0 and grid_distance[dst] != 0
```
Variants (same shape; the passability test changes; all set `distance_grid_dirty`):

| Function | Passable neighbour test |
|---|---|
| `route_distance` `0x00588920` | route & 0x11D |
| `0x005894F0` | route & 0x11C |
| `0x0058A6C0` | route & 0x10C (roads only) |
| `0x0058A0D0` | route & 0x12C |
| `0x00589ED0` | route & 0x13C |
| `route_distance_buildings` `0x00588D30` | route & 0x13D, and a tile with terrain 0x10000000 only if `0x004A96E0(building)` |
| `0x005896F0` | route & 0x15C |
| `0x0058A2D0`, `route_search_area` `0x0058A4D0` | route & 0x19C |
| `0x0058AD90` | route & 0x0C |
| `0x00589AE0` | route & 0x200 |
| `0x0058B560` | route & 0x3C, or (route & 2 and terrain & 0x10004 and no building) |
| `0x00587FB0` | terrain & 0x1D7FDC0F == 0x800 (meadow only; grazing animals) |
| `0x0058B7D0` | grid_walls value in 0..2 (wall walkers) |
| `0x0058B170(sx,sy,dx,dy,allow_m2,allow_1)` | grid_military ≠ −1, and ≠ 1 unless allow_1, and ≠ −2 unless allow_m2 |
| `route_find_listed_tile` `0x00588B20` | route & 0x11D, stops at the first tile of a list (terrain §8.3) |
**verified**

## 4. From search to route (`0x004D8220(f)`, called by the route walker when `route_id < 1`)
```
route_id = route_step = route_len = 0
slot = alloc_route(f) (0x004CC650); if none: return            # walker then becomes "lost" (10)
if water_route_mode != 0: ship searches (0x0058D320/0x0058D790/0x0058D500 on grid_ship) and
    tracers 0x0058DCE0 / 0x0058DA50 (triremes); skip the table below
switch route_mode:                                              # found -> tracer
 0:  dest must have route & 0x11C, else return; route_distance              -> trace8
 1:  0x0058A6C0 (roads)                                                     -> trace4 then trace8
 2:  route_search (weighted, limit 100000); if 0: route_search_ship         -> trace8
 3:  dest & 0x11C required; 0x0058A6C0 -> trace4/8; else route_distance     -> trace8
 4:  0x0058B7D0 (walls)                                                     -> trace4/8
 5:  0x005894F0                                                             -> trace8
 6:  0x0058B560; else route_distance                                        -> trace8
 7:  0x0058A0D0                                                             -> trace4/8
 8:  0x0058B170(…, 1, 1)                                                    -> trace8
 9:  0x005896F0                                                             -> trace8
 10: 0x0058B170(…, 0, 0)                                                    -> trace8
 11: 0x0058A6C0 -> trace4/8; else 0x0058A2D0                                -> trace8
 12: 0x0058B170(…, 1, 0)                                                    -> trace8
 13: 0x0058A0D0 -> trace4/8; else 0x00589ED0                                -> trace8
 14: 0x0058AD90                                                             -> trace8
 15: 0x00587FB0 (meadow)                                                    -> trace8
 16: 0x005894F0; else 0x0058B170(…, 0, 1)                                   -> trace8
 17: dest & 0x13C required; route_distance_buildings                       -> trace8
 18: 0x00589AE0                                                             -> trace8
 other: return
if search failed: return
"trace4/8": len = trace(4, slot); if len <= 0: len = trace(8, slot)
"trace8":   len = trace(8, slot)
if len == 0: return
route_id = slot; route_len = len; route_owner[slot] = f; tile_progress = 15
```
Route modes set by handlers: 1 for service/culture/roamers' return trips, carts, storehouse
men, deliverymen; 0 for migrants, soldiers, herders; 3 caravans, hunters, woodcutters; 4 wall
sentries/towers; 15 grazing animals; 13 override walk home; see `figure_handlers.json`
(`route_modes_set`). **verified**

### 4.1 Route slot allocation `0x004CC650(f, &slot)`
```
if f.route_id != 0:
    if route_owner[f.route_id] == f: slot = f.route_id; route_owner[slot] = 0; f.route_id = 0; return 1
    f.route_id = 0
for slot = 1..999:
    o = route_owner[slot]
    if o == 0: return 1
    if o < 0 or o > 1999: route_owner[slot] = 0; return 1
    if figures[o].route_id != slot: route_owner[slot] = 0; return 1      # stale
    if figures[o].state != 1: figures[o].route_id = 0; route_owner[slot] = 0; return 1
return 0 (slot = 0)
```
Freeing (`0x004D8990`): if `route_owner[route_id] == f` it is set to 0; `route_id = 0`.
**verified**

### 4.2 Tracer `0x0058BC80(mode, slot, sx, sy, dx, dy)`
Walks from the destination back to the source over `grid_distance`:
```
cur = tile(dx,dy); if grid_distance[cur] < 1: return 0
step = 1 if mode == 8 else 2                       # 8 directions or 0,2,4,6 only
came = -1; n = 0; best = grid_distance[cur]
while best > 1:
    want = dir_to(cur → source)                    # 0x0058CFF0(dx,dy,sx,sy) at the current point
    choice = -1; best = grid_distance[cur]
    for d in 0, step, 2*step, … < 8:
        if d == came: continue
        v = grid_distance[cur + offset[d]]
        if v == 0: continue
        if v < best: choice = d; best = v
        elif v == best and (d == want or choice == -1): choice = d
    if choice == -1: return 0
    cur += offset[choice]
    came = (choice + 4) & 7                        # the direction pointing back where we were
    buf[n++] = came; if n > 499: return 0
routes[slot][i] = buf[n-1-i] for i in 0..n-1       # reversed: source -> destination
return n
```
`came` stores the opposite of the move, i.e. the direction a walker uses from the source side;
excluding it forbids stepping back. In 8-direction mode a diagonal neighbour two BFS levels
lower is taken, so routes cut corners (no test of the two orthogonal tiles beside the diagonal).
Routes longer than 499 steps fail. **verified**
Ours: walkers.route0 (route mode 0 = route_distance + trace8), used by soldiers marching to and from an expedition
(bugs.md 369; oracle 1L5-troopsmarch equal); walkers.route11 (route mode 0xB: roads 0x0058A6C0 -> trace4 / trace8,
else 0x0058A2D0 mask 0x19C -> trace8; walkers.bfs4 + walkers.trace), used by stonecutters (11-02, bugs.md 417: oracle
schools-A, both quarries' stonecutters on every 25-tick sample of their walk to the marble); most other land walkers
still take a 4-way BFS path (walkers.land_path). walkers.land_tree (the "first reached" resource / target choice)
expands N, E, S, W as section 3 (was N, S, W, E: ties went to the wrong tile).

## 5. Weighted search `route_search` `0x00502EE0(sx, sy, dx, dy, mode, limit)` (route mode 2)
Line by line (11-02; ours `sim/military/routes.Search`, `route2`):
```
clear grid_distance; distance[src] = 1; queue = [src]; head = 0; last = 0 (local_4); pops = 0
loop:
    v = distance[queue[head]]; i = head
    if last < v:                                   # the head is above the level popped last: scan the queue
        best = v
        for j in head+1 .. tail-1:                 # (a wrapped ring scans to the end, then 0..tail-1; it never
            if distance[queue[j]] < best:          #  wraps: a tile is queued once and 0xCB10 = the map)
                best = distance[queue[j]]; i = j
                if best <= last: break             # the first tile of the level popped last
        last = best
    t = queue[i]; if i != head: queue[i] = queue[head]
    if t == dst: break
    pops += 1; if pops > limit: break              # limit 100000 > the map's 51984 tiles: never
    for n in N, E, S, W (-228, +1, +228, -1):      # 4-way; a distance is set once, never relaxed
        if distance[n] == 0 and 0 <= military[n] < 6:
            distance[n] = distance[t] + 1 + cost(military[n]); queue.append(n)
    head += 1; if head == tail: break
return distance[dst] != 0
```
cost: 1 → 10, 3 → 40, 4 → 60, 5 → 2, else 0 (`((v != 5) - 1) & 2`). So the pop is: the head if it has the level
popped last, else the first queued tile of that level after it, else the smallest distance queued (the head if it
has it, else its first tile in queue order). Pops never go down a level, so ours keeps per-distance buckets of
queue positions instead of the scan, and keeps a search per start tile and resumes it for the next goal (the pop
order does not depend on the goal; tiles reached after the goal's pop are farther than it and never on its trace).
figure_find_route case 2 then traces with route_trace(8) (section 4). On failure it tries `route_search_ship`
0x00503A60, which is a 4-way BFS over `grid_military >= 0` (misnamed): the grid holds no value >= 6, so it reaches
the same tiles and fails too (ours does not run it).
Cache: if `distance_grid_dirty == 0` (no plain BFS since: every other search sets it) and the same source/destination
was asked last time and `0x010DF2D8 == 0` (set to 1 by every `enemy_company_ai_update` 0x004FFFD0 and never cleared
in the exe), both reached: it returns at once with the old field; with `0x010DF2C4 == 1` (`FUN_00502840`, the
invaders' formation spot) when the source is reached. Settled 11-02 (not ported, by decision): `0x010DF2D8` is
written only with 1 (eight stores, all in enemy_company_ai_update) and is in no save block, so after the first enemy
company AI pass of the session the plain reuse never happens again; before it, only monsters in route mode 2 and
FUN_00502840 search with route_search. The plain reuse needs the same start and goal as the last call, both
reached, and no BFS of any figure since (`route_distance_dirty`: set by every other search of 0x00588xxx-0x0058Bxxx
and route_search_ship): its old field differs from a new one only when grid_military changed in between, i.e. a
mode-2 monster blocked (9) by a tile that turned negative and asking again from the same tile with the same dest
on a map where no other figure searched since. The 0x010DF2C4 reuse (FUN_00502840 and the lead's full search
(-2, -2) in enemy_company_ai_update) takes any old field that reaches the source. Both depend on
`route_distance_dirty`, i.e. on every walker's searches in the exe's pass order; ours' core walkers cache their
routes and do not search one to one, so the flag cannot be told and ours searches again. Oracle 1B-inv-walk (every
tick, no city walkers): the muster spots of days 1..4 equal ours' fresh 600-pop fields (military.md "Invaders'
walking per figure").
**verified**: tools/oracle_route2.py rebuilds grid_military from each oracle dump and compares every stored
mode-2 route (monsters and invaders): 1,397 routes in 21 runs equal (11-02), the 1I-missile ones across a plot's
cost 10; tests/test_terrain.py test_route_search_port compares the bucket pop with the literal scan on random weighted
grids.

`grid_military` (`military_grid_build_rect` `0x00502BA0` over a rectangle), the first test that matches: terrain
0x80000 or water + beach (0x10004) −1; 0x8000 (tower / gatehouse tile) 4; road + water (0x44) with a bridge piece
(`0x00CB4B08` != 0) 5; water −2; road 0; ramp 0x400 2; cliff 0x200 −1; building (8) by type: 0x3A, 0x3D, 0x3E,
0x75 (palace) 1, 0x83 gatehouse 4, 0xA9 burning ruins −1, orchard trees 0x23 / 0x24 / 0xD9 and avenues 0x76 / 0x7E 0,
pyramids 100..114 1, other composites by piece (not started `0x00546530` 0, attackable `0x005463B0` 1, else −1),
0xA4 −1, else 1; wall 0x4000 3; tree / marble / reeds (0x60001), rubble 0x1000, garden 0x20 0; terrain &
0x2DFED66F −1 (rock, ore kinds 0x100000..0x800000, 0x1000000, 0x8000000, 0x20000000); else 0. **verified**
(decompile; ours `sim/military/routes.grid` equals the exe's grid of the sandbox at tick 0). Before 11-02 ours had
burning ruins 0, orchard trees 1 and bridges −1.

## 6. Road-only movement vs free movement
- Roaming is road-only by construction: only neighbours with terrain road (0x40) are open
  (walkers.md §5.4); roadblocks (0x7B, and 0xA4) close a side except for plague walker, god,
  hero, disgruntled citizen, mugger.
- Route walking follows the route's mask; roadblocks have route bit 0x04 (a road), so walkers
  on routes pass them. The only roadblock/gatehouse check while route walking is during a
  roamer's pre-roam route (`0x00DBB830 = 1`, walkers.md §3.5).
- Gatehouse 0x83: closes roaming sides and pre-roam routes; for the military grid it costs 60.
**verified**

## 7. Ships and bridges (verified unless marked)
### 7.1 `grid_ship` `0x01053330` — `ship_grid_build_rect` `0x00587B90(x0,y0,x1,y1)`
Full rebuild `0x00587E20` (fill 0xFF, then the whole map); called e.g. after a bridge is placed
(`0x0041D910`). Per tile t (T = terrain `0x00CCE128`, piece = `0x00CB4B08[t]`):
```
if not (T[t] & 4) or T[t] & 0x80000 or any of the 8 neighbours lacks water bit 4
   or piece in (13, 14):                         0xFF  blocked
elif piece in (4, 10) and poseidon_game(0):      0xFF  blocked
elif any of the 8 neighbours lacks 0x4080000:    0xFB  (near shore / not deep)
elif t on the outer ring (x<1, y<1, x>W-2, y>H-2): 0xFE  map edge
else:                                            0     open water
```
Ours (10-30, bugs.md 238): sim/systems/walkers.ship_grid (numpy, cached per map version and bridge set), the same
values from World.flags; checked against the exe's own terrain in oracle dumps by tools/oracle_ships.py.
### 7.2 Searches (`figure_find_route` 0x004D8220, figure `+0x76` water_mode)
| water_mode | set by | search | passable |
|---|---|---|---|
| 1 | trade ship 0x14 (`0x004B5021`), fishing boat 0x19 (`0x004B5F57`), trireme 0x39 (`0x004BF684`), shipwreck, enemy ships, sea invasions | `0x0058D500(x,y)`: full-map 4-dir BFS, ≤ 50000 pops | `grid_ship != 0xFF`; a 0xFE tile is re-queued up to 4 times (costs ~5) |
| 2 | flotsam, monsters | `0x0058D790(x,y)`: 8-dir BFS | `!= 0xFF` |
| 3 | urchin collector | `0x0058D320(sx,sy,dx,dy)`: 4-dir BFS | `== 0xFB` only (shore band) |
Then tracer `0x0058DCE0` (trireme in attack: `0x0058DA50` first). No shore-distance cost: 0 and 0xFB tiles cost
the same, so ships take a shortest path and may run along the shore band (checked 11-04, bugs.md 462:
`tools/oracle_ships.py RUN --routes --kind trade` on 1F-ox, 1F-palacefire, 1H-bless, 1H-curse3, 1H-follower,
schools-A: 181 trade-ship moves, all on ours' route). In the decompile the
neighbour tests appear as `grid_military[i+0xCA2C]` / `[i+0xCB0F]`: aliasing of
`grid_ship[i-228]` / `grid_ship[i-1]` (0x01046820+0xCA2C = 0x01053330−0xE4).

### 7.3 Bridges
A bridge is not a building on the tiles: the bridge tool (`0x0041D910` → `0x0041D8B0`) sets
terrain `|= 0x40` (road) on water tiles, keeps the water bit, and writes the piece number
`0x0041D720(i, len, dir)` into `0x00CB4B08`:
```
len < 4:              14 if dir in (0,4) else 13                 # short bridge, every tile
len >= 4, dir 0/4:    i=0: 7, i=1: 8, middle: 9 (i even) / 10 (i odd), i=len-2: 11, i=len-1: 12
len >= 4, dir 2/6:    i=0: 1, i=1: 2, middle: 4 (i even) / 3 (i odd), i=len-2: 5, i=len-1: 6
(end pieces swap with dir 4/6: i=0 gets the len-1 piece and so on)
tool 0xC9 (road over the race track, hypothesis): pieces 15..20
```
Effect for boats (all three types use water_mode 1):
- **Short bridges (< 4 tiles): ships cannot pass** (13/14 → 0xFF).
- **Long bridges, Zeus game: ships pass under** every middle tile (pieces 3/4/9/10 are not
  blocked); the end tiles are blocked only by the "8 water neighbours" rule.
- **Long bridges, Poseidon game** (`poseidon_game(0)`; hypothesis: the expansion is active):
  every other middle tile (10 or 4) is blocked; the others stay open, so ships still cross the
  bridge line through the open middle tiles (hypothesis: pillar tiles in the art).
Land walkers: the bridge is road (route bit 0x04); `grid_military` value 5 marks road over
water with a piece (cost 2).

## 8. Cost control (summary; details in time-core.md §9.4)
- Roamers never search. Routes are searched once per trip (`route_id < 1`), traced into a direction list and followed.
- Every plain BFS clears all 51,984 distance ints, has no radius and no per-tick cap; it exits when the destination is dequeued. Failure leaves `route_id = 0`, `direction = 10` (lost); handlers usually delete the walker. **verified**
- "Nearest by road" = one flood with a candidate set: `route_find_listed_tile` `0x00588B20` (candidate tiles marked in a second grid `0x00FFA580`), used through `0x004D7D10` by `find_storehouse_bay` `0x00488E20`. Candidates are first filtered by road network id (`b+0x14`, daily flood fill `road_networks_update` `0x00491FE0`) so unreachable ones are never searched. **verified**
- `grid_route` is rebuilt by rectangle on changes (plus a full rebuild at some cycle steps and after any house evolved, flag `0x0091EA08`), never during a search. **verified**

## Open questions
- Who sets route bit 0x08 (masks include it; no writer found in the decompile).
- Tracers `0x0058DCE0`/`0x0058DA50`: military agent. (`route_search`'s pop order and `route_search_ship`: done 11-02.)
- `0x004CC5A0(mode)`: which modes may enter terrain 0x10000000 building tiles.
