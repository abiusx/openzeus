# Services: what city service walkers do to houses and buildings

Status: **verified** from the exe unless marked **hypothesis**. Addresses: GOG `Zeus.exe`.
Field names: [../re/structs.md](../re/structs.md) plus `re/structs/services.tsv`.
Cycle steps: refs/zeus-poseidon-arm64/docs/engine/simulation.md §3 (51-step cycle, 16 cycles = 1 month;
`month_advance` 0x00483C10 runs after **every** cycle, its month-end block every 16th).

## Summary

Service buildings spawn walkers (cycle step 31). Every time a walker steps onto a new tile, one
function, `figure_provide_service` 0x004DFB70, applies that walker type's effect to every
building on the tiles of the 5×5 square centred on the walker's tile. Most effects set a
per-house **coverage counter** to 96 (`0x60`). Cycle step 35 decrements the counters by 1, so
coverage lasts 96 cycles (6 months). Other steps derive flags from the counters: water
(step 28), culture/appeal (step 36), health (month end). Maintenance and watchmen do not set
counters. They subtract a fixed amount from the risk accumulators (fire/damage risk, unrest).
Fire, collapse, plague and crime are driven by those accumulators and by the RNG.

## 1. Walker → effect table (`figure_provide_service` 0x004DFB70)

Called from the two movement step loops (roaming 0x004D69B0, route-following 0x004D7BD0)
each time the figure's sub-tile progress `fig+0x39` passes 14, i.e. **once per tile entered**.
Returns immediately for figure type 0x26 or when `fig+0x10C & 0x80000` (figure disabled).
`x,y` = figure tile. "Box" = tiles `x-2..x+2, y-2..y+2` clipped to the map
(`0x00DA2F78`/`0x00DA2F7C` = map width/height). Tiles are visited row by row (y outer, x inner)
through `grid_building` 0x00D26E98. **A building that covers several tiles of the box is
processed once per tile.** That changes nothing for setters but multiplies the subtractions.

| fig type (model name) | spawned by | function | effect on each matching building tile |
|---|---|---|---|
| 0x07 Clerk | Tax office 0x7A | 0x004A67C0 | houses with pop>0: `+0x4E = 50` (tax coverage), `+0x84 = (office +0xDB != 0)` |
| 0x08 Superintendent | Maintenance ("SUPER_OFFICE") 0x79 | 0x004A5D90 | any building: `+0x46 -= R`, `+0x48 -= R`, floor 0; tile without building but terrain bit `0x4000` (wall): `grid 0x00C753B8 -= R`, floor 0. R = `model_building_value(0x79, 9)` = 50 |
| 0x0F Competitor, 0x4B Curator | Stadium 0x50 / Museum 0xCF (roaming) | 0x004A60E0 | `+0x6C = 96` |
| 0x10 Philosopher, 0x49 Astronomer | Podium 0x51 / Observatory 0xCB | 0x004A6210 | `+0x6D = 96` |
| 0x11 Athlete, 0x48 Scholar | Gymnasium 0x4F / Bibliotheke 0xCA | 0x004A6340 | `+0x6F = 96` |
| 0x12 Actor, 0x4A Inventor | Theatre 0x52 / Laboratory 0xCD | 0x004A6470 | `+0x71 = 96` |
| 0x20 Healer | Infirmary 0x4C | 0x004A66B0 | houses with pop>0: `+0x78 = 96` |
| 0x3C Water bearer | Fountain 0x4A (and unused type 0x4B) | 0x004A65A0 | houses with pop>0: `+0x77 = 96` |
| 0x3D Watchman | Guard post 0x7C | 0x004A5F70 | houses with pop≠0: `+0xF4 (unrest) -= R`, then clamp to `[house_param(L,15), 100]`. R = `model_building_value(0x7C, 9)` = 50 |
| 0x1A Peddler | agora | 0x0040D160 | sells goods to houses: **economy** (cross-ref) |
| 0x42 Plagued walker | plague | `empty_function` | nothing |

"Culture" targets (0x6C/0x6D/0x6F/0x71) = `(is_house && (pop>0 || type in 9..14)) || type == 0x7D`
(so elite houses get covered even while empty, and so does the Hero's hall 0x7D). Water and healer
targets = `is_house && pop>0`. Here is_house = `+0x05`, pop = `+0x1C`.
The Competitor/Curator → `+0x6C` pairing is confirmed by the evolve reason text for 0x19
("No curator has passed this house", [127:61]) and reason 4 ("lost access to a Stadium", [127:40]).

After the switch (verified):
```
n = return value of the effect function (number of matching tiles), 0 for watchman/peddler-less cases
if fig.building_id != 0: B = buildings[fig.building_id]; B.+0x18 += n; if B.+0x18 > 300: B.+0x18 = 300
overlay_mark_service(figure_table[type].overlay_index, fig.tile)      # 0x004A3100, visual only
```
Figure table: `0x0063969C + type*0x28`, `+0` handler, `+8` overlay index (water 0, superintendent 1,
watchman 2, competitor/scholar 3, vandal 4, mugger 5, clerk 6, healer 8, philosopher/astronomer 9,
athlete/inventor 10, actor/curator 11). `0x004A3100` raises the 2-bit field i of
`grid 0x00B1E8F8[tile]` to 3. It ORs `7 << 2i`, so it also sets the low bit of field i+1 (a bug in
the exe; this grid only drives the coverage overlay; step 45 `0x004A3140` decays it).

`fig+0x66` side value (superintendent, watchman; verified):
- Superintendent: `0x004A5D90` initialises its maxima `0x00B5153C`, `0x00B51540` to **1000**
  (not 0), then raises them to the largest damage/fire risk seen *before* subtracting. Since
  `(u8)fig+0x66 < max(…) >= 1000` is always true, `fig+0x66 = (u8)max` (= 0xE8 when no risk
  ≥ 1000) and `n` is added to `+0x18`. This is a quirk, but the effect is exact.
- Watchman: max unrest seen (`0x00B51538`, init 0) before subtraction. If `fig+0x66 < max`, then
  `fig+0x66 = max`. Otherwise `fig+0x66 = 0 if fig+0x66 < 11 else fig+0x66 - 10`. In both cases n = 0.
- Clerk: `fig+0x66 = max house_param(L,18)` (tax multiplier) over the houses visited (`0x00B51544`).

## 2. Counter decay and derived flags

**Step 28 `houses_water_flags` 0x00484ED0** (verified): `0x0091EC30 = 0`; for every building with
`state == 1 && +0x05`: `+0x35 = 0; +0x3F = 0; if +0x77: +0x35 = 1`. `+0x3F` ("well_sup" in the
debug panel) is never set by anything. Wells don't exist.

**Step 35 `houses_coverage_decay` 0x00484D20** (verified): for `state == 1 && +0x05` (houses only,
so **the Hero's hall's counters never decay**), each of the u8 fields
`+0x6C, +0x6D, +0x6F, +0x71, +0x70, +0x77, +0x78`: `v = 0 if v < 2 else v - 1`.
`+0x70` is decayed but no setter was found (open question).
A visit leaves 96. After 95 decays the counter is 1, and the 96th decay zeroes it. Steps 28 and
36 read the counter before step 35 of the same cycle.

**Step 48 `buildings_tax_coverage_decay` 0x00488220** (verified): `state == 1 && +0x4E != 0` →
`+0x4E -= 1` (any building). Clerk coverage lasts 50 cycles. Month-end tax 0x00488250 counts a
house as taxed iff `+0x4E != 0` (finance agent).

**Step 36 `houses_culture_compute` 0x00484DE0** (verified). For buildings 1..last with
`state == 1 && (+0x05 || type == 0x7D)`:
```
c = 0
if not poseidon_game(0):            # Zeus
    if +0x6C: c += 20   # stadium (competitor)
    if +0x6D: c += 15   # philosopher
    if +0x6F: c += 20   # athlete (gymnasium)
    if +0x71: c += 25   # actor (theatre)
else:                               # Poseidon
    if +0x6C: c += 20   # curator (museum)
    if +0x6D: c += 20   # astronomer
    if +0x6F: c += 15   # scholar
    if +0x71: c += 25   # inventor
if g_unique_venue_exists (0x00FEAED0, i16) != 0 and g_unique_venue_shows (0x00FEAED2, i16) > 0: c += 10
+0x80 (i8 culture) = c
+0x81 = 1 if +0x78 != 0 else 0           # "healthy": healer coverage
```
`0x00FEAED0` is set when the Stadium (`0x005AFAE0`) or Museum (`building_create`) is built and
cleared when it is destroyed (0x00494690). `0x00FEAED2` = that building's `+0xA9` show counter,
copied in step 33 (`buildings_count_by_type` 0x00491820). For the stadium only the main part
(`+0x38 == 0`) is copied. Both the stadium and museum branches write it; the last one in
building order wins. The evolve check compares `+0x80` with house col 2 and `+0x6C` with col 4
([housing-evolution.md](housing-evolution.md)).

## 3. Walker spawning by service buildings (step 31, `buildings_spawn_walkers` 0x0048CFB0)

Common pattern (verified, per building with `state == 1`, once per cycle):
```
if +0x18 < 1: +0xD3 = 2                       # UI warning flag
if not road_access(x, y, size):  skip         # 0x004A3B40; stadium uses 0x005B0600
pct = (+0x40 employees * 100) / model(type,5) if +0xDA == 0 and model(type,5) > 0 else 0   (C division)
delay = D[0] if pct>=100, D[1] if >=75, D[2] if >=50, D[3] if >=25, D[4] if >=1; pct<1: skip
+0x32 += 1                                    # spawn timer (the same byte as sanctuary_finished)
if +0x32 > delay: +0x32 = 0; spawn
```
Global gate: `0x00EF6163 == 0`. Per-type gate: `0x00EF60B0[type] == 0`. Both are a per-type
countdown table, decremented monthly by 0x004E5EB0 (religion; hypothesis: god curses).
Walkers are created at the road tile left in `0x00F13944/0x00F13940` by the access check.

| Building | D (pct ≥100, ≥75, ≥50, ≥25, ≥1) | walker, action | extra conditions |
|---|---|---|---|
| Fountain 0x4A/0x4B | 1, 3, 7, 15, 29 | water bearer 0x3C, act 1 | previous walker (`+0x2A`) gone; **pct halved** (`/2`) if `grid_desirability 0x00C9B4E8[tile] < 30`; no per-type gate |
| Infirmary 0x4C | 3, 7, 15, 29, 44 | healer 0x20, act 1 | previous walker gone |
| Maintenance 0x79 | 0, 1, 3, 7, 15 | superintendent 0x08, act 6 | previous walker gone |
| Tax office 0x7A | 0, 1, 3, 7, 15 | clerk 0x07, act 6 | previous walker gone; `0x00FE91E8 > 0` |
| Guard post 0x7C | 0, 1, 3, 7, 15 | watchman 0x3D, act 6 | previous walker gone |
| College 0x4D | 8, 15, 30, 50, 100 | philosopher 0x10, act 6 (to a podium, §3.1) | `+0xA8 += 1`, never checked: no walkers-out limit |
| Drama school 0x4E | 8, 15, 30, 50, 100 | actor 0x12, act 6 (to a theatre) | `+0xA8 += 1` |
| Gymnasium 0x4F | 4, 5, 10, 17, 30 (code: `{8,10,20,35,60}/2 < timer`) | competitor 0x0F act 6 (to the stadium) **and**, if `+0xA8 < M`, athlete 0x11 act 10 (roams) | M = 2 if `+0xDB` (blessing) else 1; type gate only when not blessed |
| Podium 0x51 | 8, 15, 30, 50, 100 | philosopher 0x10, act 10 | `+0xA9 != 0`, `+0xA8 < M` |
| Theatre 0x52 | 3, 7, 15, 29, 44 | actor 0x12, act 10 | `+0xA9 != 0`, `+0xA8 < M` |
| Stadium 0x50 (main part) | 3, 7, 15, 29, 44 | competitor 0x0F, act 10 | `+0xA9 != 0`, `+0xA8 < M` |
| Bibliotheke 0xCA (0x00432960) | 4, 5, 10, 17, 30 (halved like the gymnasium) | scholar 0x48, act 10 | `+0xA8 < M` |
| Observatory 0xCB (0x00432B00) | 8, 15, 30, 50, 100 | astronomer 0x49, act 10 | `+0xA9 != 0`, `+0xA8 < M` |
| University 0xCC (0x00432CB0) | 8, 15, 30, 50, 100 | curator 0x4B act 6 **and** astronomer 0x49 act 6 | — |
| Laboratory 0xCD (0x00432E60) | 3, 7, 15, 29, 44 | inventor 0x4A, act 10 | `+0xA8 < M` |
| Inventor's workshop 0xCE (0x00433010) | 8, 15, 30, 50, 100 | inventor 0x4A, act 6 | — |
| Museum 0xCF (0x00433170) | 3, 7, 15, 29, 44 | curator 0x4B, act 10 | `+0xA9 != 0`, `+0xA8 < M` |

Act 10 = roam (`0x004D6630` initialises the roam). Act 6 = walk to a destination (trainees, §3.1).
`+0xA9` (venue_shows) is decremented by 1 per cycle in step 33 for types 0x50, 0x51, 0x52, 0xCB,
0xCD, 0xCF. Walker roam length and lifetime belong to the walkers subsystem.

### 3.1 Trainees: school → venue (verified 2026-10-28, disassembly)

The school sends the walker; the venue never sends anyone to a school. Example: the college
sends a philosopher (0x10, action 6) that walks to a podium, and the podium then sends its own
roaming philosophers (action 10).
- **Spawn** (`buildings_spawn_walkers` 0x0048CFB0, case 0x4D/0x4E; 0xCC 0x00432CB0, 0xCE
  0x00433010): on the staffing ladder only (college at 100%: delay 8, so one trainee every
  9 days). There is **no walkers-out check**: `+0xA8` is incremented but never compared, so a school keeps
  sending trainees while earlier ones are still walking. Gymnasium: the timer runs every day and
  a competitor (0x0F, action 6) goes out at each firing. The roaming athlete is sent only if
  `+0xA8 < M`.
- **Handler** `0x004B4370` (types 15-18, 72-75): action 6 waits `timer` ticks hidden in the
  school, then goes to the school's road tile (action 7). Once it is there, it calls the venue
  finder `0x00491630`. If no venue is found, the figure is deleted (state 2) and nothing happens.
  Otherwise it stores the venue id in `fig+0x54` and switches to action 8, travel. Travel uses
  `figure_move` 0x004D1170 → `figure_route_walk` 0x004D7BD0 → `figure_provide_service` on every
  tile it enters. The figure is visible, so a trainee **does give coverage on its way** (an
  en-route philosopher sets `+0x6D` like a roaming one). `visit_elapsed += 1` per tick; past
  0xC7F (3,200 ticks, about 213 tiles at speed 6 / 15 ticks per tile) the figure is deleted
  without arriving. When the route ends (direction 8), it calls `0x00491EF0` and is deleted.
- **Venue finder** `0x00491630`: maps the figure type to a venue type (0x0F→stadium 0x50,
  0x10→podium 0x51, 0x12→theatre 0x52, 0x49→observatory 0xCB, 0x4A→laboratory 0xCD,
  0x4B→museum 0xCF; athlete 0x11 and scholar 0x48 → none). Candidates are buildings with
  `state == 1`, of that type (the main part via 0x0049B920), with the type not disabled
  (`0x00EF60B0`), `+0x40` employees > 0, and `+0xA9 <= 24`. For each candidate it records the
  road tile `+0x26/+0x28` and the weight `2 * +0xA9`. It then calls the route chooser
  `0x004D7D10` (route mode 1) → `0x0058AAD0`: one road BFS from the trainee's tile that picks the
  candidate with the **lowest road distance + 2 × shows**. There is no distance cap in the
  search, and the venue must be on the same road network (the BFS only crosses road tiles).
  Nothing reserves the venue, so two trainees can head for the same venue.
- **Arrival** `0x00491EF0`: venue `+0xA9 = 32` (**set, not added**; for the competitor, on the
  stadium's main part). It also increments `+0xAB`, wrapping at 5 (purpose unknown; probably
  the visual slot of the performer).
  After it, the venue accepts no trainee for 8 days (32 → 24), and it stops performing
  32 days after the last visit.
- **Venue**: the podium (likewise theatre, stadium, observatory, museum) spawns roamers only
  while `+0xA9 != 0`. A type-disable sets it to 0. A podium that no school can reach never gets
  shows, so it never sends a philosopher and gives no coverage.
- Note: in action 7 the handler sets `dest` to the **school's** road tile. The route to the venue
  was already allocated by 0x004D7D10, so `dest` only matters if that route is lost
  (direction 9 → `figure_route_free`). A re-routed trainee would then head back to its school and
  still call 0x00491EF0 on arrival. This was not traced further and the sim does not model it.

Consequence for play ("one college, podiums everywhere"): this works, within limits. One college at
full staff sends 9-day trainees that each give a podium 32 days of shows. That keeps about 3-4
podiums performing without a break, and each performance's coverage lasts 96 days. Venues
nearer the school win, because the extra cost is only 2 per show day. Once a near podium is back
to 24 shows, it competes with any podium more than 48 road tiles farther away. Far podiums
therefore get trainees only when the near ones are above 24.

**Oracle check (11-02, `tools/oracle_schools.py`, runs re/oracle/runs/schools-A, -B, -A-tick1/2).** "See a
working city" (3 drama schools 54, 433, 567; theatres 38, 568; colleges 432, 569; podium 570; one road network),
4,600 ticks, dumps every 25 ticks; run B pokes theatre 568's shows to 32 so the schools have one theatre. Every school
keeps spawning on its ladder, but a trainee only goes out when its spawn day finds a venue at <= 24 shows; otherwise it
is deleted at the school's road tile. One venue takes about one trainee per 8 days + the walk, so with more schools
than that the rest lose their trainees, and **which** school wins is set by the phases of the 9-day timers against
the venue's 32-day counter: in run B school 433 sent 1 trainee in 4,600 ticks (its spawn days always fell on 25+
shows) while 54 and 567 sent 5 each; in run A (2 theatres) all 3 sent 5-6. Colleges likewise (569: 3 philosophers,
432: 6). So "1 theatre + many schools" does keep the theatre performing, but some schools may never send an actor:
as original (bugs.md 398).

Timing, per tick (schools-A-tick1/2, school 54 -> theatre 38, 21 road tiles): spawned in tick 368 (step 31); action
7 at 369 (the finder, before the day's decrement); walks from 370, starting at the centre of the school's road tile
(serves it); the shows decrement (step 33) is also in 370; tiles are entered at sub-step 8; arrival at the 21st
tile's centre in tick 685 = spawn + 2 + 15 x 21, i.e. 15 x len after the decrement and in the cycle step's tick
after it, so the venue holds 32 for the rest of that day.

Sim (sim/systems/services.py `spawn`/`send_trainee`, walkers.py `follow`/`arrive`): matches the above:
no walkers-out wait for schools or the gymnasium's trainee, pick = min(path length + 2 × shows)
over staffed venues with shows ≤ 24, arrival sets shows = `rules.trainee_shows` (32), trainees
walking longer than `rules.trainee_travel_ticks` (3,200) vanish. The venue is chosen when the
trainee leaves (the original chooses it a tick later, before the same day's decrement). Fixed 11-02: the shows
decrement now runs after every building's spawn (it ran inside the spawn loop, so a venue with a lower id than the
school was decremented first and accepted a day early; a cursed venue skipped it), and a trainee starts 9 ticks after
its spawn, waits 7 ticks on its last tile and arrives at spawn + 15 x len + 2 (it arrived 15 ticks early, before
the decrement it should follow). `tools/oracle_schools.py --sim RUN` replays the run's city (tutorial15.sav, the
exe's employees pinned): every trainee of runs A and B leaves from the same school on the same day for the same
venue as in the exe (before the fix: B gave 433 seven trips, 567 two). test_trainee_venue_timing.

## 4. Fire and collapse (maintenance side)

Risk accumulation (step 44, `0x00492260`; the map-buildings agent owns it, summarised here
because the superintendent and fires depend on it; verified). Skipped entirely when
`0x00B1E8BC == 1`. At pass start one RNG step; `w = rng_e4 & 7`. For each building b with
`state == 1`, `type != 0xA9 (RUIN)`, `+0x4A == 0` (not burning), `type != 0x3B`,
`main_part(b) == b` (0x0049B920):
```
dmg(+0x46) += model(type,7)                      # damage_risk col; (+= col7*10 if burning: dead code)
if (is_house and L < 2) or type == 9: dmg = 0    # huts, shacks, elite vacant never collapse
if terrain[tile] & 0x10000: dmg = 0
if dmg < 1000:
    RNG step; r = (rng_e4 & 0x7FFF) % 5 + 1
    if ((tile_random[+0x0C] + b) & 7) == w:
        if not is_house:
            if climate (0x00902D00) == 2 (arid) and model(type,6) != 0: fire(+0x48) += 3
            fire += model(type,6) * r;  if model(type,6) == 0: fire = 0
        elif pop < 1: fire = 0
        else: fire += model(type,6) * r
        if fire > 999: message 0xB3A..; +0x4A = 1; building_ignite(b,0,0); ignite all parts (0x00492F90(b,1))
else:  # collapse
    message 0xB40..; state = 4; clear footprint; rubble (0x004CCD40); parts destroyed (0x00492F90(b,0))
```
`model(type,6)` returns 0 when god record 9 (`0x00EF5FAC`, probably **Hephaestus**) has a
finished sanctuary (`model_building_value` 0x00433D50). Climate: 0 humid, 1 normal, 2 arid
(text [44:76..78]).

**Superintendent:** subtracts 50 from `+0x46` and `+0x48` per covered tile (§1). It also puts out
fires; see §4.1. `maintenance_walker_reduce_risk` 0x004A5D90: on a tile with no building but the wall bit
(0x4000) it subtracts the same 50 from the wall damage grid `0x00C753B8` (clamp 0). Sim (10-29):
`services.repair_walls` on the military module's wall damage (sim/military/invaders.py).

### 4.1 Superintendent fire fighting (handler `fig_handler_superintendent` 0x004AF930) — verified

There is no dedicated fire walker and the maintenance office dispatches nothing. Roaming
superintendents look for fires, and the **nearest idle superintendent in the whole city**
answers. Building `+0x30` (`fire_reset_30` in our structs; it is the assigned fighter's id)
makes it one fighter per fire.

Actions: 6 hidden in the office (timer) → 7 line move to the road tile → 8 roam (budget
`+0x42 = 0xF00`) → 9 return by road (route mode 1) → 7 line move in, removed. 10 = run to a fire,
11 = extinguishing. Direction 9/10 (blocked/lost) during 9 or 10 removes the walker (`state = 2`).

**Dispatch `0x004CD450(f)`**, called at the top of every handler tick (and once more at the end of
action 11):
```
if burning_count (0x0091EC44) < 1: return 0
if f.action in {4,5,6,7,10,11,12,13}: return 0           # only roaming (8) / returning (9) look
f.reload_timer(+0x6B) += 1; if < 20: return 0           # one search per 20 ticks per walker
b = fire_find_target(f.x, f.y)            # 0x00493510
if b < 1 or best_free_dist (0x0091EC38) > 25: return 0
f.reload_timer = 0
s = nearest_idle_superintendent(b.road_x, b.road_y)     # 0x004CD370; 0 → s = f
s.reload_timer = 0; s.action = 10; s.dest = (b+0x26, b+0x28); s.target(+0x5E) = b
free route (new search next move); b+0x30 = s; return 1
```
`fire_find_target` 0x00493510 scans the burning list 0x0091F1D0 (rebuilt in step 43; entries may be
stale, so it re-checks):
```
cand: state == 1, +0x38 == 0 (head part), +0x4A != 0, +0xCD == 0, +0x20 != 0 (road-connected, step 21)
d = Chebyshev(f.x - b.x, f.y - b.y)                     # b.x/b.y = anchor tile, not the road tile
if b+0x30 != 0 and (fig[b+0x30].type != 8 or its action not in {10, 11}): b+0x30 = 0   # stale claim
if b+0x30 == 0: keep the min d → best_free (strict <, list order wins ties); 0x0091EC38 = that d
else:           keep the min d → best_taken
return best_free, or best_taken if no free one and its d < 3
```
The `best_taken` fallback is dead for this caller: with no free fire, 0x0091EC38 stays 10000 and
0x004CD450 returns 0. So a fire is a candidate only if it is unclaimed, road-connected and within
Chebyshev 25 of a searching superintendent.
`nearest_idle_superintendent` 0x004CD370: all figures with `state == 1`, `type == 8`, action not in
{4,5,6,7,10,11,12,13}; min Chebyshev to the fire's road tile; first in figure order wins ties.
The searcher itself always qualifies, so `s` is never 0 in practice.

**Run (action 10):** `route_mode = 0` (cross-country route over the general walkable grid, not
road-only; pathfinding.md §4), normal speed (col 8). It does not check the fire while running.
On arrival (direction 8): action 11, free route, `timer(+0x36) = 50`, frame counter `+0x74 = 0`.

**Extinguish (action 11)**, every tick, `b = +0x5E`:
```
d = Chebyshev(f, b.x/b.y)
if b.state == 1 and b+0x4A != 0 and d < 10:
    if b+0x4A <= 16: +0x4A = 0 on root(b) and on each +0x3A chain part (≤ 500)   # fire out, at once
    else:            b+0x4A = 32; sound 0x9D        # step 43 then hits 33 → destroyed, rubble
else: timer = 1                                     # nothing left to do
face b; +0x74 += 1; timer -= 1
if timer < 1 and +0x74 >= frames(anim 0x660E):
    reload_timer = 20; dispatch(f) (always 0: action is 11); action 9 home (road tile, route mode 1)
```
So a fire with `+0x4A <= 16` is put out on the first tick of action 11. The fighter then stays
for 50 ticks (or the animation length), heads home, and since `reload_timer = 20`, the dispatch
at the top of its next tick (action 9) can send it to another fire at once.
Ruins (corrected 10-30, oracle 1F-palacefire, buildings.md §8): a building's ruins start again at (seed & 7) + 1,
so a fighter reaching a ruin usually finds `+0x4A <= 16` and puts it out: the ruin stays (type 169, not burning)
until the player clears it. The `> 16` branch (set 32: burnt out to rubble at the next step 43) hits ruins
that have burnt past 16 (seen once in the run). The palace never gets a fighter (its `+0x20` stays 0).

Other consumers of burning state: `fig_handler_fire` 0x004B0880 (fire sprite figure, removed when
`+0x4A == 0`, the type changes or the building is destroyed); `labor_assign_buildings` gives no
workers to burning buildings; `figure_delete` clears `+0x30` for type 0x2E. Nothing else in walker
code reads the burning list.
Also: the watchman's enemy search (§6.1) reuses 0x004CD370, which can send a superintendent.

**Ignite `building_ignite` 0x004950B0(b, src, collapse)** (verified): ignores types 0x7E and 0x76,
and 0x83 (gatehouse → 0x004E5C30). Sets `+0x48 = +0x46 = +0x20 = 0`. If 0x0040BCF0(type) (a type
class, hypothesis "burns in place"): `+0x4A = (+0x4D & 7) + 1, +0x30 = 0, +0x4C = 1,
+0xCD = src, +0x40 = 0` (state 5 instead if collapse). Otherwise the same values are set for each
footprint tile (size² entries of the 0x005F19B4 offset table, water tiles skipped). With
collapse ≠ 0 each tile becomes a new 1×1 RUIN building (type 0xA9).

**Burning, spread, ruins (step 43 `buildings_fire_burn_spread` 0x00493140)** (verified). Counters
`0x0091EC3C/40/44` are reset; `0x0091F1D0[]` lists the burning buildings (max 499).
For b with `state == 1 && +0x38 == 0` (head part):
```
if +0x4A < 0: +0x4A = 0
if +0x4A != 0:
    +0x4A += 1
    if +0x4A < 33:
        if +0x4A > 16 and type != 0xA9: burn_to_ruins on every linked part (0x00492F30 → 0x00492BE0)
        if +0xCD == 0:
            add to the burning list
            if (+0x4A & (3 if arid else 7)) == 0:
                RNG step
                if (+0x4D & 3) == (rng_e4 & 3):
                    d = 0x0091EC48 (spread direction 0..7; writer not identified)
                    try tiles: tile+off[d], then tile+off[d-1 mod 8], then tile+off[d+1 mod 8]   # off = 0x0064324C
                      (the third is tried only if the first two fail)
                    a target qualifies if grid_building≠0, target +0x4C == 0 and can_catch_fire(target) (0x00493040)
                    first qualifying: building_ignite(t,0,0); ignite parts; sound 7
    else:   # reached 33
        state = 4; clear footprint (0x004A07C0); parts destroyed; rubble (0x004CCD40, size 3 for 0x3A, 4 for 0x3E)
```
`burn_to_ruins` 0x00492BE0: removes the building (0x00494690), kills its residents
(`0x005675D0(pop)`, `pop = 0`, `+0x05 = 0`) and turns every footprint tile into a 1×1 **burning RUIN**
(type 0xA9, `+0x4A = (+0x4D & 7)+1` for the main tile, copied for the others). RUINs burn on until
33, then are destroyed and leave rubble. RUINs keep spreading fire. `can_catch_fire` is false for
type 0x77, types 0xA4..0xA7, 0x0F..0x18, 0x7F, 0x94..0x98, 100..0x72 and 199 (gardens, statues,
pyramid parts, race track). `+0x4C` is initialised from the type table `0x005F636C` (stride 0x20)
by `building_create` and set to 1 when the building ignites.

Status icons (`0x00564560`, verified): `+0x110 |= 0x20` if damage > 800, `|= 0x10` if fire risk > 800.

## 5. Health, hygiene and plague

Per-house health inputs: `+0x78` (healer counter, §1), `+0x81` (= `+0x78 != 0`, step 36) and
`+0x7F` (number of food types eaten this month, written at month end by 0x0048B8D0; economy).

**Hygiene target, month end (`city_health_target_compute` 0x00566C00)** (verified):
```
0x00FEB528 (outbreaks this month) = 0; 0x00FE6A80 = 0x00FE6A84 = 0
P = W = 0
for every building with state == 1, +0x05, pop (+0x1C) != 0:
    P += pop; w = 0
    if +0x78: 0x00FE6A84 += pop; w = 50
    if +0x7F: w += 50; 0x00FE6A80 += pop
    W += pop * w
h = (W*100) / (P*100) if P*100 != 0 else 0
bonus = second value of the first pair in 0x00641ED0 with city_pop (0x00FE6A7C) < first value:
        (100,80) (200,80) (300,70) (400,60) (500,50) (600,40) (700,30) (800,20) (900,10) (1000,0); none → 0
target (0x00FE6A6C) = clamp(h + bonus, 0, 100)
```
**Health step, every cycle (`city_health_step` 0x00566B90):** `health (0x00FE6A70)` moves 1
toward the target (no overshoot) and is clamped to 0..100. It is set to 80 for a new city
(0x00566950). 0x004C5690 (no direct caller; hypothesis: Apollo/Asclepius healing) clears
`+0x85, +0x10C..+0x10F, +0xF8..+0xFB` of every house, removes all plagued walkers and adds 50 to
health.
After a step `FUN_005246B0(old, up)` posts the short message (`FUN_005231E0`, text group 19, the banner line
also used for the view-turn names): down: nothing if (the tens digit `health/10` is unchanged or population
< 301) and health > 19, else 19:147 at health 0, 19:(147 + (health − 1)/10) otherwise ("Hygiene appalling, plague
imminent" .. "Hygiene is deteriorating"; below 20 it repeats on every step down); up: nothing if the tens digit
is unchanged, population < 301 or health < 10, else 19:(157 + (health − 1)/10) ("Hygiene is better, plague still
likely" .. "Hygiene is perfect!"). Sim (10-29): `health.health_message` (message meta `text19`). The advisor
texts (hygiene page 0x00519A50 / 0x00519820: 56:(h/10 + 2), 56:13..16 while moving; overview 0x005B65C0:
61:(127 + h/10)) are in viewer/play/pages.js.

**Plague check, every cycle (`plague_check` 0x00447FF0, from `month_advance`)** (verified):
```
table 0x005F84A8 (threshold, chance per 10000): (10,300) (20,250) (30,200) (45,100) (60,50) (75,25) (100,0)
i = first entry with threshold > health; none → no plague
chance = table[i].chance
cap  = ceil(chance*384/10000)                 # 384 = cycles in 2 years
if cap <= plagues_this_year (0x00FEAEF4) + plagues_last_year (0x00FEAEF0): no
if outbreaks_this_month (0x00FEB528) != 0: no
if ceil(cap/2) <= plagues_this_year: no
r = 0; repeat 4 times: RNG step; r = r*10 + (rng_e4 & 0x7FFF) % 10
plague iff r < chance
```
Year rollover (0x00488820): `last_year = this_year; this_year = 0`.

**Outbreak `plague_outbreak` 0x004481B0:** `n = (inhabited houses * 2) / 5`; both plague counters
+1; `plague_infect_houses(n)`; then messages (0x004482B0).

**`plague_infect_houses(n)` 0x00448490** (verified): builds a list sorted by ascending
`key = (+0x7F ? 20 : 0) + (u8)+0x78` over inhabited houses in building order (a node pool at
0x007CBDD4/D8/DC). Insertion starts from the last inserted node (or the head if that node was
dropped). Forward while `*node < key`, insert before the first node with key ≥ new key;
otherwise backward, insert after the first node with key ≤ new key. When the list has more than
n nodes, drop the tail (highest key). So it keeps the n least-covered houses. Then, with
`need = n/2`, it walks from the head: a house is infected if `remaining_candidates <= need`, or else
if `random_next()` makes `(rng_d0 & 1) == 0` (the RNG is drawn only in the second case). It
stops when need = 0. Each infected house: event marker 8 at its tile (first 0x00410030, others
0x004100C0), tile recorded in 0x007CFC6C[], `house_plague_start` 0x00448220:
```
deaths = trunc(pop * F[difficulty])   # double table 0x005F8480 = 0.25, 0.3333, 0.5, 0.6667, 1.0; difficulty 0x00F2A988 (0 Beginner..4 Olympian)
0x005675D0(deaths); pop -= deaths
+0x85 = 2 (infected); +0x100 = 32; +0x10C = 0; +0xF8 = 0; 0x00412D60(b)
3 × plagued walker 0x42 at the house: +0x36 = 600, action 6, roaming
```
**Infection countdown, step 6 (`houses_plague_countdown` 0x004483F0):** for houses with
`state == 1 && +0x85 && +0x100`: `+0x100 -= 1`; at 0, `+0x85 = 0`. `0x00FEB524` = number of
infected houses (shown by the advisor). An infection therefore lasts 32 cycles = 2 months.
Healers do **not** cure infected houses (their effect writes only `+0x78`).
Plagued walkers have no service effect. When one meets a figure of type 0x20 (healer), 0x26 or
0x3D (watchman), it is removed (0x00448450, via collision 0x004D4DA0). No house-to-house spread
was found (hypothesis: plagued walkers are cosmetic). The contact test runs in both directions on every tile
change (`figure_tile_contact` 0x004D4DA0 calls `plagued_walker_meet` 0x00448450 with either figure first).
Plagued walkers, disgruntled (0x16) and muggers (0x1B) ignore roadblocks (`roam_open_sides` 0x004A31E0:
roadblock types 0x7B/0xA4 close a side only for other figures).
**What the infected flag `+0x85` blocks** (every reader of `plague_state`, verified 10-28): house_room_update
0x004860A0 sets the capacity to the current population (room 0: no immigrants or homeless are sent, no
overcrowding eviction); an immigrant (0x004AC810) or homeless (0x004AD090) arriving at an infected house adds
nobody; placement 0x00496CA0 keeps an empty infected house's type instead of resetting it to a lot; status bit 8
(0x00564560, advisor/icon); the house info panel shows the plague text; gods skip infected houses (0x004E9100).
It does not block evolution, births (house_births has no plague test) or services.
**House col 20 ("disease_inc") is never read**: there is no `house_param(…,20)` call and no
direct table read (`house_param` is the only reader of 0x0078B24C).

## 6. Crime: unrest, watchmen, criminals

Per-house unrest `+0xF4` (i32, 0..100; the house panel shows it as satisfaction text [127:21..27]).
`building_create` 0x00493E70 initialises it to `house_param(L,15)` for common houses and 0 for elite.

**Unrest update (`houses_unrest_update` 0x00566F20, from 0x005671A0), twice a month** (month end
and when the cycle-in-month counter = 8) (verified):
```
k = (40 - sentiment(0x00FE6A68)) / 2                       # C division (toward 0)
for houses with state == 1 && +0x05:
    if pop == 0: +0xF4 = 0                                   # and nothing else for this house
    elif type not in 9..14:
        if city_pop (0x00FE6A7C) >= 350 or latch 0x00FEB0DB:
            if god record 10 (0x00EF5FE0, probably Dionysus) sanctuary finished: +0xF4 -= 20
            else: +0xF4 += house_param(L,14) + k
        +0xF4 = clamp(+0xF4, house_param(L,15), 100)
```
The latch 0x00FEB0DB is set once city_pop > 349 (in 0x005671A0, before this call) and cleared
for a new city. The same loop also computes a sentiment term from `+0x7F`/`+0xCC` (inhabited houses
only). That term belongs to military-sentiment.
**Watchman:** −50 per covered tile of each inhabited house, clamped to `[col15, 100]` (§1).

**Criminal spawn, step 45 (`houses_spawn_criminals` 0x005BFDE0)** (verified): for every common
house (type not 9..14) with `state == 1, +0x05, pop != 0`, check the table at 0x0065E898
in the order **(100, vandal 0x1D), (90, thief 0x17), (80, mugger 0x1B), (70, disgruntled 0x16)**.
For each entry with `+0xF4 >= threshold`: RNG step; if `(rng_e4 & 0x7FFF) % 200 == 127`, call
`house_spawn_criminal(b, type)` 0x005BFF90. That spawns only if `+0x2A == 0` (one walker per
house): action 6, roaming, at road tile `(+0x26,+0x28)`, lifetime `fig+0x36 = (+0x4D & 0xF) + 10`.

Criminal effects (handlers are walkers' scope; verified where the function is named):
- Thief/vandal target: `criminal_find_elite_target` 0x005C0630 chooses an inhabited-or-empty elite
  house (types 9..14) holding any of the goods in 0x0065E8E8 (vandals: any elite house) via
  route chooser 0x004D7D10. If there is no target the criminal is removed and the house tries to
  spawn a mugger (0x005C0030 thief, 0x005C02C0 vandal). Only the vandal path clears `+0x2A`
  first, so a thief without a target just disappears: `house_spawn_criminal` refuses while
  `+0x2A != 0`.
- Thief at target (0x005C00C0): `0x00FEAEE4 += 1` (thefts this month). It steals from 12 goods
  slots (0x0065E8B8): for slots 0..4, `max(2*col/4, held/4)` with cols 6, 13, 11, 10, 9
  (horses, armor, wine, oil, fleece); slots 5..11 share one food budget `2*col17/4` (or
  `total_food` if `2*col17 < total_food/4`; type 9 uses fixed 4,4,10,10,10,20). Each slot loses
  `min(held, amount)`. Message 0xA7.
- Vandal (0x005C0360): counts `fig+0x36` down at the target, then destroys it (0x004928C0),
  `0x00FEAEE6 += 1`, message 0xA8.
- Mugger (0x005C0440): when it collides with a figure that is not type 0x26 or 0x3D and not a
  criminal or god: RNG step; if `(rng_e4 & 3) == 0` the victim dies (action 4), the mugger takes
  action 8 for 20 ticks, `0x00FE96D8 += 1`.
- Advisor/icons: `+0x110 |= 4` when unrest > 80 (0x00564560). City crime level 0x00519910 counts
  houses with unrest > 80 and > 70.

### 6.1 Watchmen vs criminals — verified

**No chase, no arrest.** The watchman (61, 0x004C0CF0; actions 6/7/8/9 as the superintendent,
roam budget 0xF00) never looks for criminals. Criminals end in one of four ways: they finish their
job, roam out, are killed in melee by **any** "good guy" they share a tile with, or (thief/vandal)
cannot route.

**Melee on contact** (`figure_tile_contact` 0x004D4DA0, run by `figure_change_tile` whenever a
roaming or routed figure enters a tile; military.md "Combat"): the mover fights the first figure
on the tile with `hostility[mover.class][other.class]` set (class = figure col 0, table
0x00639430). Class 2 good_guy → class 4 criminal is 1, and 4 → 2 is 1, so it does not matter who
walks onto whom. Class-2 figures (col 0 == 2): watchman, nobleman (38), soldiers 11-13, wall/tower
sentries, hunter (53), woodcutter (55), hero. Helpless walkers (class 1) never fight
criminals (row 4 col 1 = 0, row 1 col 4 = 0).

Values (model figures, Normal; col 1 hp, 2 attack, 3 armor):

| figure | class | hp | attack | armor |
|---|---|---|---|---|
| watchman 61 | 2 | 20 | 6 | 1 |
| nobleman 38 | 2 | 25 | 6 | 2 |
| disgruntled 22 | 4 | 12 | 0 | 0 |
| thief 23, mugger 27, vandal 29 | 4 | 10 | 0 | 0 |

Fight (`figure_fight_start` 0x004D4BA0, `figure_fight_tick` 0x004D5F10, `figure_hit` 0x004D54D0,
`figure_fight_end` 0x004D61B0, `figure_dying_tick` 0x004D60B0; verified 2026-10-28):
- Start: **both** figures stop: each gets `saved_action = action, action = 5`, `attack_timer = 0`.
  The mover faces `direction_to(mover.prev, other.prev)` (other's own tile if it stands on its
  destination); the other faces the opposite way (+4). A figure already in action 5 keeps its facing
  and takes the newcomer as `opponent2` (at most 2 opponents). The mover plays its attack sound
  (`FUN_004DB3D0(mover, 0)`, slot 1 or 2 at random).
- Tick (both sides, from their handlers): while `tile_progress < 6` it keeps stepping into the tile
  (`figure_fine_step`), so the two stand short of the tile centre, each on its own side.
  `attack_timer += 1`; when > 23 → `figure_hit(self, opponent)`, timer = 0. So one blow per 24 ticks
  each. `dmg = A - (D*A)/20`; criminals have A = 0, so their blows do 0 damage, but each one still
  plays the defender's hit sound.
- Death when `damage(+0x98) > hp`: watchman (A 6) kills a thief/mugger/vandal (hp 10) in 2 blows =
  **48 ticks**, a disgruntled (hp 12) in 3 = 72. Hunter (A 3): 4 / 5 blows; woodcutter (A 4): 3 / 4
  (model figures, Normal). The victim: `action = 4, timer = 0`, death sound (`FUN_004DAB30`, slot 8).
  A non-lethal blow plays the victim's hit sound (`FUN_004DB7A0`, slot 7).
- The defender's next fight tick sees its opponent no longer in action 5 → `figure_fight_end`: switch
  to `opponent2` if it is still fighting, else `action = saved_action` (roaming) and the route is
  freed. So the watchman stands still for the whole fight + 1 tick, then walks on.
- Dying (action 4): `timer += 1` per tick; at 128 `state = 2` (removed). The sprite is the 8-frame
  death strip at `timer / 2` (clamped to the last frame), so the fall takes 16 ticks and the body lies
  there for the remaining ~112 ticks. No crime counter changes.
- Sprites (vandal handler 0x004B6A00, watchman 0x004C0CF0): criminals in action 5 (and a vandal at
  work, action 10) play the 8-frame fight strip one frame per tick, and each time the frame counter
  reaches 1 they play their attack sound again (every 8 ticks). The watchman shows fight frame 0 for
  `attack_timer` 0..11 and frame `(attack_timer-12)/2` for 12..23 (one swing per blow).
- Sounds (group table 0x010E0518, filled by FUN_005A5D00; played only for figures on screen):
  criminals 0x16/0x17/0x1B/0x1D → group 0x54: `Wavs/outlaw_attack.wav` (1/2), `outlaw_hit.wav` (7),
  **`outlaw_die.wav`** (8). Watchman 0x3D → group 0x66: `watchman_attack.wav`, `gen_hit8.wav`,
  `gen_die8.wav`. Hunter 0x35 (resource 0) → 0x41 `boar_hunter_*`; woodcutter 0x37 → 0x62
  `gen_hit5/gen_die5` (no attack sample). In data/play/audio.json `combat`.
- Our sim (sim/systems/crime.py `melee`): both walkers stand (`busy_until`), the criminal dies at
  `start + 24*hits` and lies dying 128 ticks; the defender walks on the tick after. The play client
  draws fight/die strips and plays the sounds from the frame field `anim` (sim/export.py
  `walker_anim`). Simplifications: no sub-tile step-in (the client offsets each 0.3 tile towards its
  previous tile); if the defender vanishes mid-fight the criminal walks on only at the fight's end.

**Mugger** (contact, checked before the hostility fight, whichever side moved):
```
mugger_attack(m, v):                                   # 0x005C0440
    if v.type in {0x26 nobleman, 0x3D watchman}: return 0           # immune → normal hostility check
    if v.type in {0x16, 0x17, 0x1B, 0x1D, 0x43 god}: return 0
    RNG step; if (rng_a & 3) != 0: return 0                          # 3/4: nothing (then hostility check)
    muggings(0x00FE96D8) += 1; v.action = 4 (dies, hp ignored)
    m.action = 8; m.timer = 20; m.target(+0x82) = v; v.flags |= 2; return 1   # no fight
mugger action 8 (0x004B68B0): timer -= 1; at < 1: corpse v.state = 2; m.action = 6 → roams on (1)
```
So a mugger meeting a watchman or nobleman just fights it and dies. Against other class-2 figures
(soldiers, hunters, woodcutters) it first rolls the 1/4 instant kill, otherwise they fight.

**Criminal lifetimes.** `house_spawn_criminal` sets `timer(+0x36) = (+0x4D & 0xF) + 10`, but no
criminal handler reads it before overwriting it: disgruntled and mugger go through
`figure_roamer_generic` 0x004CDEE0 (action 6 → 1, roam until `+0x44 >= 0x900` or the early-return
rule, then action 2 home by road, removed on arrival or when blocked). The thief's action 6 picks its
target at once. The vandal sets `timer = 51` on arrival and destroys the house when it runs out
(counts down while it stands there; it re-targets if the house is no longer an active elite
house). The thief steals on arrival and is removed. During routing, direction 10 (lost)
removes thieves and vandals.
The disgruntled citizen has no effect of its own: it roams and can be killed.
Sim (10-29): thieves and vandals have no roam budget (ours had 0x900/0xF00 of the superintendent's); a vandal
with no target is removed and the house's mugger comes out instead (fresh, mugger roam).

**What watchmen do chase** (`0x004CD5B0`, not a Ghidra function; called by the watchman handler
every 12 ticks):
```
if enemy_formations_active (0x00EF57D4) < 1: return      # hypothesis: count of live non-player formations
if w.action in {4,5,6,7,10,11,12,13}: return
w+0x80 += 1; if < 10: return                             # → one search per 120 ticks
w+0x80 = 0
t = 0x004CD710(w.x, w.y, 30): figures with state 1, +0x65 == 0, +0x84 (attacked_by) == 0 and
     type in {0x28, 0x29, 0x2A enemies}: 2*Chebyshev < 30   or   type 0x3B wolf: 3*Chebyshev < 30
     (≤ 100 candidates); pick by BFS from w's tile (route_find_listed_tile 0x00588B20, walkable mask 0x11D)
if none: return
s = nearest_idle_superintendent(t.x, t.y) (0x004CD370, type 8!); if 0: s = w
s.action = 12; s.dest = t.pos; s.target(+0x82) = t; t+0x84 = s; s+0x88 = t.serial(+0x86); free route
```
Watchman action 12 (route mode 0): while the target is valid (`0x004D9E70`: target > 0, state 1,
not dying, serial unchanged) it moves toward the target and re-aims at the target's current tile
on each arrival. The fight starts by contact (good_guy vs enemy class 3 / predator class 5).
Target invalid → action 9 home. Blocked or lost → removed.
Quirk (code verified, consequence is a hypothesis): because 0x004CD370 only returns
superintendents, when one exists the order goes to the nearest superintendent. Its handler has no
case 12, so it falls back to action 6 and walks back to its office, and the watchman keeps
roaming. The chase only works in a city with no idle superintendent.

## 7. Other services

- **Tax office / clerk:** coverage only (§1, §2). Tax amounts: finance agent (0x00488250 multiplies
  col 18 by 110/100 when byte `+0x86` is set; meaning open).
- **Palace (0x75), Hero's hall (0x7D):** neither spawns a service walker here. The Hero's hall
  receives the culture walkers' counters and gets `+0x80` computed (step 36), and its counters
  never decay (§2).
- **Horse trainer (0x49), chariot vendor, horse ranch:** goods delivered by agora/peddler. This is
  the economy subsystem, not a coverage counter.
- **Infirmary/guard post/maintenance `risk_reducer` (model col 9 = 50):** only 0x79 and 0x7C are read
  (`model_building_value(0x79,9)`, `(0x7C,9)`). **The infirmary's col 9 (50) is never read.**

## Constants (Normal model; Easy/Hard identical for col 9)
| Constant | Value | Source |
|---|---|---|
| coverage set value | 96 | immediates in 0x004A60E0…0x004A66B0 |
| tax coverage | 50 | 0x004A67C0 |
| service radius | 2 (5×5 square) | all effect functions |
| maintenance reduction | 50 | model row 0x79 col 9 |
| watchman reduction | 50 | model row 0x7C col 9 |
| acc counter cap | 300 | 0x004DFB70 |
| fire threshold / collapse threshold | >999 / ≥1000 | 0x00492260 |
| burn timeline | start 1..8, ruin at 17, gone at 33 | 0x00493140, 0x004950B0 |
| culture weights | see §2 | 0x00484DE0 |
| unique-venue bonus | +10 | 0x00484DE0 |

## Cross-references (other subsystems)
- walkers: movement loops 0x004D69B0 / 0x004D7BD0 / 0x004D1170, roam init 0x004D6630, handler table
  0x0063969C, handlers 0x004AF930 (superintendent), 0x004B4370 (culture), 0x004B78A0 (healer),
  0x004C0BC0 (water), 0x004C0CF0 (watchman), 0x004C2DA0 (plagued), 0x004B5A20/5B70/68B0/6A00
  (criminals), collisions 0x004D4DA0, venue finder 0x00491630, route chooser 0x004D7D10.
- map-buildings: risk accumulation 0x00492260 (§4 summary), `building_create` 0x00493E70,
  destroy 0x00494690, rubble 0x004CCD40, footprint clear 0x004A07C0, road access 0x004A3B40.
- population-housing: `+0x1C` pop, 0x005675D0 (pop removed), 0x00567650, 0x004E8D80 (blessing timer
  `+0xDB` growth for houses), evolve check reads `+0x35, +0x80, +0x6C`.
- economy: peddler 0x0040D160, food consumption 0x0048B8D0 (writes `+0x7F`).
- religion: god records 0x00EF5DD8 (record 9 Hephaestus → no fire risk; 10 Dionysus → unrest −20),
  type-disable countdown 0x00EF60B0 / 0x004E5EB0, blessing `+0xDB`.
- military-sentiment: sentiment 0x00FE6A68 and its update 0x005671A0 (calls the unrest update).
- time-core-finance: `month_advance` 0x00483C10, monthly tax 0x00488250.

## Open questions
1. Who sets `+0x70`? It is decayed in step 35 like the coverage counters, but no setter was found
   (perhaps a Poseidon-only or removed service).
2. (answered, §3.1) A trainee's arrival (0x00491EF0) sets the venue's `+0xA9` to 32; it does not add.
3. (answered, §3.1) Yes: action 8 travel uses figure_move → figure_route_walk → figure_provide_service.
4. (answered, §4.1/§6.1) Superintendent fire targeting; watchmen vs criminals.
5. `0x0091EC48` (fire spread direction): writer not found.
6. Plague effects beyond `+0x85`/countdown: what `+0xF8`, `+0x10C` (zeroed at infection) are. (Answered 10-28:
   infection blocks immigration and rehousing, not evolution; §5.)
7. Meaning of figure type 0x26 in the exe (model: "Nobleman"). It is exempt from service
   dispatch, immune to muggers, and removes plagued walkers.
8. `+0x84` (clerk from a blessed tax office) consumer; `0x00FE91E8` (tax office spawn gate).
9. Fountain rule: is grid 0x00C9B4E8 really the desirability grid here (terrain.md says so)? Then
   fountains in low-appeal areas spawn water bearers more slowly.
