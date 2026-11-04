# Population: occupants, migration, births/deaths, evictions

Status: **verified** unless marked. Addresses: GOG `Zeus.exe`. See [housing.md](housing.md) for
capacity and goods, [labor.md](labor.md) for the workforce.

## Summary
The city keeps a population counter `g_population 0x00FE6A7C` (city record +0x24) separately
from the houses' occupants `b+0x1C`; every change goes through two helpers that also update the
record maximum. Each 51-tick cycle: step 22 recomputes every house's free room from its level's
capacity, step 23 decides migration from city sentiment (immigrants walk from the map entry to
houses with room; emigrants leave from the lowest-level houses), runs yearly births/deaths and
computes the labor pool, and step 24 evicts the surplus of overcrowded houses (homeless walkers
that look for a new house). Twice a month the counter is clamped down to the sum of occupants.

## 1. Global state
| addr | name | meaning |
|---|---|---|
| `0x00FE6A7C` | g_population | city population (city+0x24) |
| `0x00FEB0EC` | g_population_max | highest population (`population_record 0x00566930`, step 11 and on each change) |
| `0x00FE6A68` | g_city_sentiment | 0..100, init 60 (city+0x10); updated by military-sentiment |
| `0x00FE6A6C` | g_health_target | 0..100, init 80 (city+0x14), monthly `0x00566C00` (hypothesis: health) |
| `0x00FE6A70` | g_health | 0..100, init 80 (city+0x18), moves 1 per cycle toward target `0x00566B90` |
| `0x00FE6A8C` | g_house_capacity_total | sum of capacities (step 22) |
| `0x00FE6A90` | g_house_room_total | sum of capacity−occupants (step 22) |
| `0x00FE9184` | g_migration_rate | −25..100 (step 23) |
| `0x00FE9140`/`0x00FE9144` | g_immigrants_due / g_emigrants_due | this cycle |
| `0x00FE914C`/`0x00FE9148` | pending immigrants / emigrants (< 4 accumulate) | |
| `0x00FE918C`/`0x00FE9190` | emigration / immigration cooldown (2 cycles) | |
| `0x00FE9178`,`0x00FE917C`,`0x00FE9180` | settled, emigrated, turned away (this cycle) | |
| `0x00FE9194` → `0x00FEB1AC` | immigrants this month → last month | monthly copy in `month_advance` |
| `0x00FE9150` | g_homeless | evicted people walking (eviction +, rehoused −) |
| `0x00FE9154` | last change passed to `0x005675B0` | |
| `0x00FE916C` | g_year_end_flag | set at year end by `0x00566D30` |
| `0x00FE915C`/`0x00FE9168`/`0x00FE9158` | yearly pop sum / years / average | `0x00566E30` |
| `0x00FE6A94` | g_population_history i32[2400] | monthly sample, index `0x00FE9014`, count `0x00FE9018` (`0x005676D0`) |
| `0x00FE9170`/`0x00FE9174` | rotating building cursors for births / deaths | |
| `0x0091F5B8` | g_house_list u16[4000], count `0x0091EC7C` | rank 73; rebuilt by `house_list_build 0x00486050` |
| `0x00FEB0DB` | population ever > 349 (enables crime, negative sentiment terms) | set in `0x005671A0` |

Population helpers: `population_add 0x00567650(n)` (clamp ≥ 0, then record max),
`population_sub 0x00567620(n)` (same), `population_change 0x005675B0(n)` (stores n in
`0x00FE9154`, adds), `population_evict 0x00567600(n)` (`homeless += n`, sub),
`population_rehouse 0x005675E0(n)` (`homeless -= n`, add), `0x005675D0` = sub.

`house_list_build 0x00486050`: for i in 1..`0x0091EBF8` (highest building): state == 1 and
`b+0x05` (is_house) ≠ 0 → append. Order = building index.

## 2. Step 22 — `house_room_update` `0x004860A0` (was `cycle_houses_pass_22`)
```
g_house_capacity_total = g_house_room_total = 0     # 0x00566D20
house_list_build()
for b in house_list:
    b.room(+0x1E) = 0
    if b.road_access(+0x20) > 0:
        cap = house_param(b.level + (1 if b.type == 9 else 0), 17)
        if b.plague(+0x85): cap = b.occupants
        g_house_capacity_total += cap
        b.room = cap - b.occupants;  g_house_room_total += b.room
        b.occupants_max(+0x22) = max(b.occupants_max, b.occupants)
```
Also called by the debug "fill houses" cheat `0x004C56F0`.

## 3. Step 23 — `city_population_update` `0x00486190` (was `cycle_city_pass_23`)
Order: (a) migration rate, (b) immigrants, (c) emigrants, (d) yearly births/deaths, (e) labor
pool (labor.md), (f) milestone messages.

### (a) `migration_rate_update` `0x00567450`
```
s = g_city_sentiment
rate = 100 if s>=71 else 75 if s>=61 else 50 if s>=50 else 0 if s>=36
       else -8 if s>=26 else -17 if s>=16 else -25
due_in = due_out = 0
if g_population >= 200000: rate = 0; return
if 0x00FEB084 < 4:                                    # hypothesis: enemy threat level
    if rate > 0:
        if imm_cooldown(0x00FE9190): imm_cooldown -= 1; return
        due_in = ceil(rate*12/100); emig_cooldown(0x00FE918C) = 2; goto msg
elif rate > 0: rate = 0; return
if rate < 0:
    if emig_cooldown: emig_cooldown -= 1; return
    if g_population <= 100: return
    due_out = ceil(-rate*12/100); imm_cooldown = 2
msg: if rate changed: 0x00523770(0)                  # advisor refresh (not traced)
```
So per cycle: 12/9/6 immigrants at rate 100/75/50; 3/3/1 emigrants at −25/−17/−8.

### (b) immigrants
```
settled = emigrated = turned_away = 0
n = due_in
if 0 < n < 4: pending_in += n; if pending_in >= 4: send_immigrants(pending_in); pending_in = 0
elif n >= 4: send_immigrants(n)
```
`send_immigrants(n)` `0x00486860`:
```
for b in house_list: if b.immigrant(+0x2E) and figures[b.immigrant].state != 1: b.immigrant = 0
left = n
pass A: for b in house_list while left > 0:
    if b.road_access > 0 and b.occupants == 0 and b.room != 0 and b.immigrant == 0
       and (b.type not in (9,10) or b.culture >= house_param(9,2)):
        k = min(left, 4); spawn_immigrant(b, k); left -= k
pass B: same list, condition road_access > 0 and room > 7 and immigrant == 0: k = min(left,4)
pass C: condition road_access > 0 and room > 0 and immigrant == 0: k = min(left, room)
settled += n - left;  0x00FE9194 += settled
if left != 0 and left == n: turned_away += left
```
This month's newcomers (0x00FE9194, read by the population panel 0x00518B20, the overview 0x005B5FA0 and the
migration advisor message) count people when they **set out** from the entry, not when they move in; ours too
(sim/systems/population.py, 10-30, bugs.md 282; before, ours counted on arrival). People still walking are in no
other count: the population and the house grow on arrival. The CLI (`status`, `report population`) adds an "on the
way" line (ours; a 70-tile walk takes ~1000 ticks, more than a month).
`spawn_immigrant(b, k)` `0x00486C50`: `figure_create(1, type 1, entry_x 0x00902CB4,
entry_y 0x00902CB6, 0, 1)`; if created: action 6, `fig+0x5C` = house, `b.immigrant` = fig,
`fig+0x36` = (`b+0x4D` & 0x7F) + 10, `fig+0x64` = k, `fig+0x41` = bit 6 of tile flags
`0x00CCE128`; then **two inline random_next draws** (history `0x00F13628`/`0x00F13624`, registers
`0x00F137E0`/`0x00F137E4`, 31 steps each, derived values refreshed after the 2nd), then
`0x00412DC0(entry_x, entry_y, r & 0x7F01, r & 1)` (r = `0x00F137E4`); its result `+0x68` = fig
(hypothesis: the immigrant's cart). `figure_create` itself also writes an RNG history entry.

Arrival (immigrant handler `0x004AC810`, table `0x0063969C` + 1·0x28; movement = walkers agent):
```
cap  = house_param(9 if b.type == 9 else b.level, 17)
k    = min(fig.count, max(0, cap - b.occupants)); fig.count = k
if b.occupants == 0 and 2 <= b.type <= 14 and not 0x00B1E8BC:
    house_set_type(b, 2 if b.type <= 8 else 11)
if not b.plague: b.occupants += k; b.room = cap - b.occupants; population_change(+k)
b.immigrant = 0
```

### (c) emigrants
Same accumulation with `pending_out 0x00FE9148`, calling `send_emigrants(n)` `0x00486AB0`:
```
if Aphrodite sanctuary built 100% (god record 0x00EF5F10, 0x004EA710): return  # game text: emigration ceases
left = n
for level in 0..13 while left > 0:
    for b in house_list while left > 0:
        if b.occupants > 0 and b.level == level:
            k = min(b.occupants, 4, left); house_emigrate(b, k); left -= k
emigrated += n - left
```
`house_emigrate(b,k)` `0x00486E40`: `population_change(-k)`; occupants −= k (if k ≥ occupants:
0 and, for common houses, `house_reset_to_lot`); `figure_create(1, type 2, b.x, b.y, 0, 1)` with
action 6, `+0x36` = 0, `+0x64` = k. Then `due_in = due_out = 0`.
Emigrant handler `fig_handler_emmigrant` `0x004ACD50` (verified, disassembly 0x004ACEDB/0x004ACEF8): action 6
waits 5 ticks hidden, line-moves to a road tile near the house (road_tile_near_building, radius 5; none:
removed), then action 8 walks to the map **entry** `0x00902CB4/6` (the immigrants' spawn point), not the exit.
Only the homeless handler `0x004AD090` uses the exit `0x00902CB8/A` (0x004AD1DA/0x004AD1FA).

### (d) yearly births and deaths (only when `g_year_end_flag`)
`month_advance` at the year rollover calls `0x00566D30` (flag = 1, then `0x00487110` = sum of
occupants of houses in states other than 0,2,5,6). Next step 23 runs `0x00566D40`:
```
h = g_health
p = 6 if h>90 else 4 if h>80 else 3 if h>70 else 2 if h>60 else 1 if h>50 else 0 if h>40
    else (-1 if g_health_target > 30            # quirk: tests 0x00FE6A6C, not h
          else -2 if h>20 else -3 if h>10 else -5 if h>0 else 0)
if Hera sanctuary finished (god record 0x00EF6048): p += 3       # text: "more fertile"
if p > 0: population_add(house_births(g_population*p/100))       # trunc
if p < 0: population_sub(house_deaths(trunc(g_population*(-p)/100)))
```
`house_births(n)` `0x00486EF0(n, elite=0)`: from cursor `0x00FE9170`+1 (wrap 3999→1), at most
3999 buildings: state 1, is_house, road_access > 0, occupants > 0, common type (< 9 or > 14):
cursor = i; add min(n, cap−occ) (cap = col 17 of level), update room, n −= added. Returns total.
`house_deaths(n)` `0x00487020(n, 0)`: cursor `0x00FE9174` (i16), at most 15999 steps, state 1,
is_house, common type (no occupancy test): remove min(n, occ), update room.
Then `0x00566E30`: yearly sum += population, years += 1, average = sum/years, flag = 0,
`population_record()`.

### (f) milestones
Population > 99, 499, 999, 1999, 2999, 4999, 9999, 14999, 19999, 24999: one-time message
(text pairs 0x4DA/0x4DB … 0x510/0x511, flags `0x00FD37C4`..`0x00FD37CD`, `0x00521A70(0xE0,…)`).

## 4. Step 24 — `house_evict_overcrowded` `0x004871B0` (was `cycle_houses_pass_24`)
```
for b in house_list (list from step 22):
    if b.room < 0:
        k = -b.room
        spawn_homeless(b.x, b.y, k)        # 0x00487160: figure type 3, action 6, +0x36=0,
                                           #   +0x64=k (u8); if created: population_evict(k)
        b.occupants = 0 if k >= b.occupants else b.occupants - k
```
Note: the population is decreased only if the figure was created; occupants always. A house
that devolves (housing.md) gets negative room at the next step 22 and loses the surplus here.
Homeless (type 3, handler `0x004AD090`) choose the nearest house (Chebyshev, first lowest index
wins; `0x00486B80`) with state 1, is_house, road_access > 0, room > 0, no immigrant en route.
On arrival: same as an immigrant but type 2 for 2..8, type 11 for elite ≤ 11, and
`population_rehouse(k)`. With no house they walk to the exit (action 9) and look again every 31 ticks
(`timer` +1 a tick, `>= 0x1F`): a house found (with road access) turns them round (action 7). Sim: the same
(10-29, `walkers.homeless_house`).

## 5. Other population writers
- `city_sentiment_update 0x005671A0` (month cycles 0 and 8): if sum of occupants
  (`0x00487110`) < population → `population_sub(difference)`; sets `0x00FEB0DB` when pop > 349.
- `0x00566C00` (monthly): `g_health_target` = Σ occupants·(50·[`b+0x78`≠0] + 50·[`b+0x7F`≠0])
  / Σ occupants + bonus from table `0x00641ED0` (pairs: population threshold, bonus), clamped
  0..100 (services agent; `b+0x78` hypothesis: healer access timer).
- plague `0x00447F70` (services): occupants −= float part, `population_sub`, `b+0x85` = 2,
  `b+0x100` = 32 (countdown in step 6 `buildings_timer_countdown`, clears `b+0x85` at 0).
- `0x004DA250` (3 calls of `house_deaths`), `0x004E8D80` (`population_add`) — not traced.
- `0x004C56F0`: debug fill (adds up to 4 per house, `population_change`).

## 6. Military manpower — `city_military_manpower` `0x00567910` (was `houses_capacity_totals`)
Step 13, only when `0x00FEB084` == 0 and `0x00FEB3EC` == 0; ECX = city record `0x00FE6A58`.
For each house in the list, `h = ceil(occupants·col5/100)`:
- types 4..8 (not 2, 3): `rabble(city+0x49CC) += h`;
- types 12, 13: `hoplites(+0x49D0) += min(h, min(arms, col13))`;
- type 14: `a = min(arms,col13)`, `hs = min(horses,col6)`, `cav = min(h, a, hs)`;
  `hoplites += min(h−cav, a−cav)`; `horsemen(+0x49D4) += cav`;
- types 9, 10, 11: nothing.
Then rabble = ceil(rabble/6); companies `+0x49F4..+0x49FC` = ceil(manpower/8) each; if
`city+0x49E4` ≥ 20 the three are capped to 20 in total, horsemen first. Finally if
`city+0x4486` == 0: `city+0x4448` += 1 and if ≥ 5 everything is zeroed; else if `0x004A3D40()`
== 0 everything is zeroed. Interpretation is the military-sentiment agent's.

## Open questions
- `0x00FEB084` (blocks immigration when ≥ 4; zero needed for step 13/14) — hypothesis: enemy threat.
- `0x00412DC0` object created with each immigrant; `fig+0x36` meaning.
- Identity of `g_health` (`0x00FE6A70`) — consistent with health (plague odds, births) but not proven.
