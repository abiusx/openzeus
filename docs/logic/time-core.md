# Time core: tick, 51-step cycle, day/month/year, RNG

Status: **verified** from the exe unless marked. Addresses refer to GOG `Zeus.exe`.
City record fields (`city.*`): see `re/structs/city.tsv` and [finance.md](finance.md).

## Summary
The simulation advances in **ticks**. `game_turn` runs one tick per pass of the main loop when
the speed timer says it is due. Every tick draws one random number, then runs **one step** of a
51-step cycle (`simulation_cycle_step`), then the terrain events, multi-tile buildings and all
walkers. Every 51 ticks the cycle wraps and `month_advance` runs. Despite its name it advances
one **day** (the game has 16 days per month that the player never sees). On day 16 it runs the
monthly accounting and month change, and on the 12th month the year change.

Time units:
| unit | ticks | counter |
|---|---|---|
| tick | 1 | – (no saved tick counter; `0x00F9F9A4` counts ticks but isn't saved) |
| cycle ("day") | 51 | `cycle_step` `0x0091EC14` (rank 37), 0..50 |
| month | 16 × 51 = 816 | `day_of_month` `0x0091EC0C` (rank 38), 0..15 |
| year | 12 × 816 = 9,792 | `month` `0x0091EC08` (rank 6), 0..11 |
| – | – | `year` `0x0091EC04` (rank 5), signed, negative = BC |
| – | – | `day_counter` `0x0091EC10` (rank 39): +1 per `month_advance` call |

## 1. When a tick runs: `game_turn` `0x00513580`, `simulation_due` `0x005168A0`
```
game_turn:
  0x00F2AAC0 += 1 ; 0x00F9C0F4 = timeGetTime()
  n = simulation_due()                    # 0 or 10000
  for i in 0..n-1:
      0x00F9F9A4 += 1                     # tick counter, not saved
      simulation_tick()
      if fast_forward 0x00F2AA9C == 0: n = 0        # normal case: exactly ONE tick
      elif a mouse button-up message is pending: flush input, fast_forward = 0, n = 0
      autosave_if_due 0x005123D0()        # after every tick (see §5)
  ... input, drawing, sound (not simulation)
```
So in normal play **one tick per frame** at most. `fast_forward` (`0x00F2AA9C`) runs up to 10,000
ticks in a row. `month_advance` clears it at each new year (a "skip to year end" mode,
**hypothesis** on purpose).

```
simulation_due:
  elapsed = timeGetTime() - last_tick_time 0x00F9F998 ; if elapsed < 0: elapsed = 10000
  k = (100 - game_speed 0x00F2A774) / 10            # C division
  if k >= 10 or paused 0x00F2A768: return 0
  if screen 0x00F2A6DD in (0x12, 0x23): if 0x00EF8174 != 1: return 0
  elif screen_pauses_sim 0x0063D8B8[screen] != 0: return 0
  if 0x00665DC8 != 0 or 0x00F2A6D0 != 0: return 0
  k = max(k, 0)
  if elapsed >= speed_delay_ms[k] + 2: last_tick_time = now; return 10000
  return 0
```
`speed_delay_ms` `0x0063DA1C` = `[0, 20, 35, 55, 80, 110, 160, 240, 350, 500, 700]`.
`game_speed` moves in steps of 10 between 10 and 100. Its default is 90 (`0x00F2A774 = 0x5A`
in `0x005C44C0`; the +/-10 keys are in `0x00402430`), which gives k = 1, a 22 ms minimum
interval, about 45 ticks/s.
At speed 100 the interval is 2 ms, so in practice one tick per frame.
For a port: the tick sequence does not depend on wall-clock time. Only the number of ticks per
second does.

## 2. The tick: `simulation_tick` `0x00513A30` (verified)
```
rng_draw()                                   # §6, exactly one draw
tick_period_counters()     0x00509DC0        # dead state, see below
undo_expire()              0x004A7A50        # UI undo buffer
if editor_mode 0x00665E2C == 0:
    simulation_cycle_step()                  # §3
    terrain_events_update() 0x00446A70
elif screen 0x00F2A6DD == 'X':
    terrain_events_update()
multi_tile_buildings_update() 0x00534F60
walkers_update()             0x004CC8C0      # tail-jump
```
**Ours** (sim/game.py `Game.step`, 11-02): `tick += 1`, then the cycle step's work (`systems.run_day` when
`tick % 51 == 0`: the day's systems and month_advance; `systems.run_step29` when `tick % 51 == 30`), then
`disasters.tick` (terrain_events_update), then `walkers.move_all` (walkers_update) with `g.tick` unchanged. So inside a
tick `tick % 51` is the exe's `cycle_step` after the step counted on (0 in month_advance, 30 after step 29, and during
walkers_update), and the state after N ticks is the oracle's dump N (taken at the entry of tick N). Before 11-02 the
figure pass ran first (`move_all`, then `tick += 1`, then the day): one figure pass ahead of the exe, so the oracle
tools compared ours after K + 1 with dump K (removed). Code between steps (commands, a test's set-up) acts before the
next tick's cycle step, as the exe's input between two simulation_tick calls: `walkers.now(g)` is the tick whose
pass comes next (`g.tick` inside a step, `g.tick + 1` between steps); `walkers.add` / `schedule` count from it.
Saves from before (no `tick_v`) still wait for the pass of their tick: `Game.load` runs it once. Play mode: a step
taken in tick v is in the frame recorded at v, so `sim/live.py` `_walker_step` dates it from v - 1 (drawn between the
frames v - 1 and v; `tools/walker_smooth_check.py`). Daily systems at their own steps (11-02, bugs.md 422 / 424): `systems.STEPS`
(Game.step runs step s in the tick with `tick % 51 == s + 1`): 5 formations_update(0) (wolf / herd passes with the
step-5 recount), 6 plague countdown, 13 cities_relations_update (an invasion's end; the hit marks reset), 14 recruits
(military.update), 20 production progress (farms, trees, workshops: economy.produce20) + terrain_regrow (stumps,
meadows, trees_exist), 21 houses' road check, 23 migration + population milestones, 24 overcrowding, 25 labour,
29 formations_update(1) (the company AI, wolf / herd passes), 31 buildings_spawn_walkers (producers' spawns, carts,
stall buyers, artisans, services, tower sentries, trireme repair), 32 trade + the monuments' completion, 35 coverage
decay, 37 desirability, 39 houses (luxuries on days 0 and 7), 43 burning, 44 fire / collapse risk, 45 criminals,
48 the tax collector's timer, 49 animals. At the step-50 point (`run_day`, month_advance): month start, gods,
health, the trees' tend decay, sentiment + unrest (days 0 / 8), empire and scenario events, heroes' month, the
alarm counters and `forces.day` (the mobilized companies' member sync, ours' own). The standard's peace / morale
(fig_handler_standard 0x004B3E00) runs every tick after the cycle step (`forces.standards` from Game.step, 11-03).
Step 5 also runs the morale waver and formations_refresh's id-order slots (sim/military/morale.py).
Ours runs a step's systems by system, not interleaved by building id as buildings_spawn_walkers does.

`editor_mode` (`0x00665E2C`) is 1 in the map editor: `game_turn` sets it to 1 when it loads a map
through `0x0051D530` and to 0 when it starts a scenario through `0x005B0660`. Construction
spending is also skipped while it is set (`0x005676A0`).

**`tick_period_counters` `0x00509DC0`**: ten counters at `0x00F1386C`…`0x00F13890`, each
incremented then wrapped. Their periods are 4 (`…890`), 8 (`…88C`), 16, 24, 32, 64, 128, 256,
384 and 768 (`…86C`). **No code reads them**: the only references to their addresses in the
binary are inside this function (raw xref scan). They are not saved. A port can drop them.

## 3. The 51-step cycle: `simulation_cycle_step` `0x00483840` (verified)
It runs `switch(cycle_step)`, then `cycle_step += 1`. If `cycle_step >= 51`, it sets
`cycle_step = 0` and calls `month_advance()`. So step 50 runs, then the day advances in the same
tick. Steps not listed do nothing.

| step | calls (in order) | subject / owner |
|---|---|---|
| 1 | `city_totals_refresh` `0x00408C90` (§4) | labour, finance and coverage totals |
| 3, 30 | `0x010DFFB8 = 1` | minimap redraw request, read by `0x0058EA90` (UI only) |
| 4 | `treasury_debt_check` `0x00461520`: if `city.treasury >= 0`: `city.months_in_debt = city.years_in_debt = 0` | finance |
| 5 | `formations_update(0)` `0x004DDD30` | military |
| 6 | `buildings_timer_countdown` `0x004483F0`: for houses (`b+0x05`) with `b+0x85 != 0` and `b+0x100 (i32) != 0`, it decrements `b+0x100` and clears `b+0x85` when that reaches 0. `city+0x4ACC` = number of such houses | services/population |
| 7 | `road_networks_update` `0x00491FE0` | map |
| 8 | `cycle_storages_pass` `0x0048B570` | economy |
| 9 | `figures_type39_count` `0x004DF3C0` | walkers |
| 10 | `buildings_update_highest` `0x004889F0` | map |
| 11 | `population_record` `0x00566930` | population |
| 12 | `cycle_buildings_pass_12` `0x00484FE0` | – |
| 13 | if `city.war_flag_a (+0x462C) == 0 and city.war_flag_b (+0x4994) == 0`: `city+0x4AA0 (u8) = 0xFF`, `city+0x03 (u8) = 0xFF`, `houses_capacity_totals` `0x00567910`. Always: `cities_relations_update` `0x00568C20` | population / empire |
| 14 | same condition: `cycle_formations_pass_14` `0x00567C70` | military |
| 16 | `cycle_storages_pass_16` `0x00488C30` | economy |
| 17 | `cycle_city_buildings_17` `0x0048B0D0` | – |
| 20 | `cycle_buildings_pass_20` `0x00485360`, `terrain_regrow` `0x004A7D30` | map |
| 21 | `buildings_road_access` `0x004856A0` | map |
| 22 | `cycle_houses_pass_22` `0x004860A0` | population |
| 23 | `cycle_city_pass_23` `0x00486190` | population |
| 24 | `cycle_houses_pass_24` `0x004871B0` | population |
| 25 | `cycle_labor_25a` `0x00487240`, `cycle_labor_25b` `0x00487630`, `cycle_labor_25c` `0x00487BA0` | labour (economy) |
| 28 | `houses_water_flags` `0x00484ED0` | services |
| 29 | `formations_update(1)` | military |
| 31 | `buildings_spawn_walkers` `0x0048CFB0` (also the **mint**, see finance.md) | walkers/economy |
| 32 | `cities_trade_update` `0x005B9EE0`, `cycle_buildings_pass_32` `0x00495860` | trade |
| 33 | `buildings_count_by_type` `0x00491820`, `cycle_totals_33` `0x00491EB0` | coverage totals |
| 35 | `cycle_buildings_pass_35` `0x00484D20` | – |
| 36 | `cycle_buildings_pass_36` `0x00484DE0` | – |
| 37 | `desirability_from_buildings` `0x00493830`, `desirability_from_terrain` `0x00493C80` | map |
| 38 | `buildings_update_desirability` `0x004842A0` | map |
| 39 | `houses_evolve` `0x004FE290` | housing |
| 40 | `cycle_buildings_pass_40` `0x00484030` | – |
| 43 | `buildings_random_pass_43` `0x00493140` | disasters |
| 44 | `buildings_random_pass_44` `0x00492260` | disasters |
| 45 | `buildings_random_pass_45` `0x005BFDE0`, `grid_b1e8f8_decay` `0x004A3140` | disasters |
| 46 | `empty_function` `0x00401000` | nothing |
| 47 | `houses_counters_reset` `0x004936A0` | – |
| 48 | `cycle_buildings_pass_48` `0x00488220`: for every building with `state == 1`, if `b+0x4E (u8) != 0`, decrement it. This is the **tax-collector coverage timer** (finance.md) | finance |
| 49 | `animals_spawn` `0x004F8E30` | map |
| 0, 2, 15, 18, 19, 26, 27, 34, 41, 42, 50 | nothing | |

This table matches `refs/.../simulation.md` §3 and adds the details of steps 4, 6, 13 and 48.

## 4. `city_totals_refresh` `0x00408C90` (verified)
It runs at cycle step 1 **and** whenever the player opens an advisor screen
(`0x00408C00` ← `0x00516D50`, screen 7). The advisor path therefore **changes simulation state
outside the tick**: it re-runs the labour allocation. A port that replays only ticks must also
replay advisor openings, or diffs will show differences there.
```
labor_allocate_sectors   0x00487750   # workforce -> 10 sector slots; city.employed, unemployed, unemployment_pct
cycle_labor_25c          0x00487BA0   # workers -> buildings (b+0x40)
taxes_this_year_refresh  0x004885B0   # finance.md §3
wages_this_year_refresh  0x00488900   # finance.md §4
ledger_totals_refresh    0x00488960   # finance.md §6
sentiment_reason_copy    0x00567680   # city+0x4410 = min(city+0x4538, 7)
cycle_totals_33          0x00491EB0   # coverage totals 0x0091EA70.. (0x00566A90, 0x005669F0)
cycle_city_buildings_17  0x0048B0D0
formations_refresh       0x004DE210
month_table_call         0x00432950   # ratings from coverage tables 0x005F00C8/0x007818A4
```

## 5. Day advance: `month_advance` `0x00483C10` (verified; called after cycle step 50)
Suggested name: `day_advance`. The function is kept under its old name because other docs use it.
```
day_counter += 1 ; day_of_month += 1
health_step_toward_target 0x00566B90          # city.health moves 1 toward city.health_target; clamp 0..100
if plague_roll 0x00447FF0():                   # may draw RNG 4 times (below)
    plague_start 0x004481B0(); 0x004482B0()
if day_of_month < 16:
    if 0x00F2A6DC and screen == 1: 0x0052B610()      # top buttons/UI refresh
else:  ### NEW MONTH ###
    0x00F2A6CE = 1
    if month in (2, 11): 0x004AA6D0()          # seasonal pass over buildings (hypothesis: e.g. crops)
    day_of_month = 15                          # (visible to the callees below)
    city+0x271C(feb1ac) = city+0x273C ; city+0x273C = 0
    city+0x448C (i16) = 0 ; city+0x2C80 = 0 ; city+0x448E (i16) = 0
    health_target_update     0x00566C00
    taxes_collect_monthly    0x00488250        # finance.md §3   (treasury +)
    wages_pay_monthly        0x00488740        # finance.md §4   (treasury -)
    debt_months_update       0x00483B20        # finance.md §7
    monthly_snapshot         0x00462110        # copies of military/trade counters (city+0x4764..+0x4AE0)
    0x0048B8D0()                               # houses pass (house_param), city+0x45D4
    0x00504A30()                               # invasions: scenario events of type 2 (0x00476E20)
    scenario_events_monthly  0x0046D380 (ECX = 0x009173F0)   # §7
    0x00567810()                               # if city+0x44D0: city+0x44D4 -= 1
    hippodrome_income_monthly 0x0056FD30 (ECX = 0x00FF80D0)  # finance.md §5
    0x00522320(), 0x004A0070(), 0x00587B30(), 0x00522110()  # messages / map passes (UI, terrain)
    day_of_month = 0
    month += 1
    if month == 5: 0x00565950 (ECX = 0x00FE6908)             # yearly scenario event spawn (Poseidon)
    0x004E1250()
    if month < 12:
        month_table_update(0) 0x00432810  (via thunk 0x00495640)
    else:  ### NEW YEAR ###
        month = 0 ; year += 1 ; fast_forward 0x00F2AA9C = 0 ; 0x00DA2374 = 0
        0x00566D30()                    # city+0x2714 = 1 ; houses_population_sum
        taxes_year_rollover        0x004886E0
        wages_year_rollover        0x00488790
        trade_ledger_year_rollover 0x004887B0
        construction_year_rollover 0x004887E0
        gifts_given_year_rollover  0x00488800
        ledger_year_rollover       0x00488840   # also writes the "last year" totals
        plagues_year_rollover      0x00488820
        yearly_stats_rollover      0x004888E0   # city+0x2D5C[36] -> city+0x2CCC[36], then zero
        0x00461460()                            # clears 5 ints + 1 short in each of the 22 cities (rank 7)
        year_random_draw           0x00484F10   # rng_draw(); 0x0091EC48 = rng_a & 7
        month_table_update(1)
        ledger_totals_refresh      0x00488960
    if month in (0, 6):
        0x0056FC60()                            # hippodrome / horse table 0x006429E8 (cross-ref)
        city+0x4714 (autosave_pending) = 2      # autosave_if_due 0x005123D0 saves after the tick
        0x00477270()                            # cities pass (rank 7)
    population_history_push 0x005676D0          # city+0x3C[2400] ring of population, idx city+0x25BC
    if fast_forward == 0 and option 0x00F2A7CA == 1: save "last.sav"
    if 0x00902FC4 != 1: 0x00903114 += 1
    0x0052B610()
    0x00902932 += 1                             # (scenario record: months played, hypothesis)
0x00519590()
if day_of_month == 0:                           # first day of a month (also right after rollover)
    over the scenario events of type 2 (0x0046D520): find the nearest invasion -> city+0x4408/+0x440C
    if no war flags: city+0x2B20 (months_at_peace) += 1 else = 0
    0x004E29B0()
    if 0x00F2A990: if city+0x2B24 == 1: 0x00568D20() elif city+0x2B20 == 1 and city+0x4AA1: 0x00569010()
    city+0x2B24 = nearest invasion time
if day_of_month in (0, 8):
    city_sentiment_update 0x005671A0           # finance.md §8 (twice a month)
    0x00B1E8CC = city+0x4AEC ; 0x00519910()
if month == 0 and day == 2: 0x004771E0()        # empire (rank 7)
if day == 7:  0x0047ECD0()                      # empire, draws RNG
if day == 2:  0x00477210()
if day == 3:  0x005247A0(0x00B1E8CC)
if day == 4:  0x00568540(&a,&b,&c); city+0x20 = max(city+0x20, c)
if day == 12: 0x0047EE20()                      # empire/requests, draws RNG, touches treasury
if day == 5:  0x004E69A0()                      # gods, draws RNG
0x004E6B10()                                    # gods, every day
if day == 6:  0x00524860()
if day % 4 == 0: 0x00477240()
empty_function(); 0x004E5EB0(); 0x004AA640()
```
Notes:
- The `if day == …` tests run after the month rollover, so on a new-month call the day value is 0.
- Order inside a new month matters for the treasury: taxes first, then wages, then the debt check.
- Plague roll `0x00447FF0` (cross-ref services; it consumes RNG, so its order is listed here):
  ```
  i = first i with city.health < thr[i] in table 0x005F84A8 = (10,300),(20,250),(30,200),(45,100),(60,50),(75,25),(100,0)
  if none or i > 6: return false
  chance = val[i] ; maxp = ceil(chance*384/10000)
  if plagues_this_year + plagues_last_year >= maxp: return false
  if plague_this_month (city+0x4AD0) != 0: return false
  if plagues_this_year >= ceil(maxp/2): return false
  r = 0 ; repeat 4: rng_draw(); r = r*10 + (rng_a & 0x7FFF) % 10
  return r < chance
  plague_start: plague_this_month += 1 ; plagues_this_year += 1 ; 0x00448490(houses_with_pop*2/5)
  ```

## 6. Random numbers
### 6.1 The simulation RNG (verified: `random_next` `0x004488C0`, inlined in ~90 functions)
Two 31-bit shift registers, `rng_a` `0x00F137E4` (rank 42) and `rng_b` `0x00F137E0` (rank 43),
both saved and both stored in `.map` files (ranks 10, 11). One **draw**:
```
rng_history[rng_history_idx] = rng_7          # 0x00F13628[100] (u8), idx 0x00F13624
rng_history_idx += 1 ; if rng_history_idx > 99: rng_history_idx = 0
repeat 31 times:
    for r in (rng_a, rng_b):
        fb = ((r >> 4) ^ r) & 1
        r = (r >> 1) | (fb << 30)            # u32, logical shift
rng_15  0x00F137D0 = rng_a & 0x7FFF
rng_7   0x00F137D4 = rng_a & 0x7F
rng_3   0x00F137D8 = rng_a & 7               # never read
0x00F137C4 = rng_b & 0x7FFF ; 0x00F137C8 = rng_b & 0x7F ; 0x00F137CC = rng_b & 7   # never read
```
- Consumers read `rng_15` (73 sites), `rng_7` (186 sites) or `rng_a` directly with their own
  mask (`& 1`, `& 3`, `& 7`, `& 0x1F`, `& 0x7F01`, `% n` …). **Nothing reads `rng_b` or its three
  outputs** (verified: all `0x00F137E0` reads are inside the stepping code). `rng_b` still has to
  be stepped so that saves stay byte-identical.
- `rng_history` is write-only and not saved. Only the stepping matters, and `rng_7` must equal
  `rng_a & 0x7F` of the previous draw.
- Some inlined copies keep the registers in locals and write them back after the loop
  (`0x00411920`, `0x00412080`, `buildings_random_pass_43`, `figure_wander`, `0x004E0160`,
  `0x004F83E0`, `buildings_random_pass_45`). The result is identical.
- A draw happens at the start of **every tick** (in `simulation_tick`) plus wherever a
  rule needs one. Between draws, every reader in the same tick sees **the same value**. Many rules
  read `rng_7`/`rng_15` without drawing, so a port must reproduce every draw site and its order exactly.
- **Seed**: at program start `0x0050B980` sets `rng_a = 0x54657687`, `rng_b = 0x72641663`
  (and `0x00F137DC = 0x34518632`, never read). Loading a map or a save overwrites both
  registers.
- Monthly/day RNG consumers found in this subsystem: `plague_roll` (4 draws, conditional),
  `year_random_draw` `0x00484F10` (1 draw per year, keeps `rng_a & 7` in `0x0091EC48`),
  `0x0047ECD0` (day 7), `0x0047EE20` (day 12), `0x004E69A0` (day 5), several event handlers
  (§7) and `0x0046DAA0`.

### 6.2 C library `rand` `0x005CC7A2` (not simulation)
`seed 0x00662E30 = seed*0x343FD + 0x269EC3; return (seed >> 16) & 0x7FFF` (MSVC LCG). Used only by
`game_turn` for ambient sounds. Not saved and not part of the simulation.

### 6.3 Per-tile random grid (rank 22, `0x00CA7FF8`, 228×228 u8) (verified)
`random_grid_fill` `0x00496330` (called by `map_grids_reset` `0x00496120` from `0x0042B230`,
`0x0050E610`, `0x0051D010`, `0x0051D530`) fills it in index order 0..51983. Each tile takes one
draw: `grid[i] = (u8)(rng_a & 0x7FFF)` (low byte of `rng_15`). The grid is saved (uncompressed)
and is also in `.map` files (rank 8). A loaded game therefore uses the stored grid; the fill
only happens on a fresh reset. Readers use it as a fixed per-tile variation, for example
`% 3`/`& 7` image variants, `% 100 + 1` for buildings, `& 6` into `b+0x34`, and `& 0x7F` into `b+0x4D`.

## 7. Scenario events: `scenario_events_monthly` `0x0046D380`, `month_events_dispatch` `0x0046DFD0`
Once a month (new-month branch above), `0x0046D380` walks the event table at `0x009173F0`
(`count` i32, then 150 records of 124 bytes = rank 13). For each record whose flag
`rec+0x28 & 1` is clear, it sets `0x00632708 = index` and calls `month_events_dispatch` with
ECX = the record. The dispatcher switches on the type byte `rec+0x02`. Each handler first checks
the event date (`events_date_check` `0x00471F00` and others) and fires only on its date.
The type numbers match text group 156 ("Free Event", "Request", …).
`0x0046DE00` re-dispatches child events when it spawns them.

| type | text 156 | handler | what it does (high level) |
|---|---|---|---|
| 0 | Free event | – (default: nothing) | |
| 1 | Request | `0x00470800` (`events_random_month`, rename suggested `event_request`) | a city requests goods/money; messages 0xDF; reads treasury and city+0x4630/+0x4854/+0x48E4 request slots; draws RNG |
| 2 | Invasion | not here: `0x00504A30`/`0x0046DE00` → `0x00476E20` | |
| 3 | Earthquake | `0x0046D6D0` | arms a terrain event (rank 115 `0x0078C578`) |
| 4 | Quest | `0x00482820` | god quest (heroes), messages 0xE0/0xDE |
| 5 | Landslide (?) | `0x004732B0` | uses `0x00902F4C/58`; **hypothesis** |
| 6, 7, 10, 11 | Sea/land trade problem, contaminated water, copper-mine collapse | `0x00472EC0` | generic: date check + announce (`0x00476CA0`) |
| 8 | Wage increase | `0x00472F00` | raises `city.standard_wage` (+0x2C0C) |
| 9 | Wage decrease | `0x004730A0` | lowers `city.standard_wage` |
| 12 | Clay pit flood | `0x004733F0` | date check only (24 bytes) |
| 13 / 14 | Demand increase / decrease | `0x00472540` / `0x004727C0` | city trade table (rank 7, `0x008FBACE`) |
| 15 / 16 | Price increase / decrease | `0x00472B20` / `0x00472D00` | goods price table `0x0065B9B0` (rank 8) |
| 17 / 18 | Favor increase / decrease | `0x0046E840` / `0x0046E970` | city relation (`0x0042CED0`) |
| 19 | City status change | `0x00473680` (`events_cities_month`) | city becomes ally/vassal/rival… (rank 7) |
| 20 | Rival army away | `0x00474160` | |
| 21 / 22 | Supply increase / decrease | `0x00472030` / `0x004722B0` | rank 7 |
| 23 | Gift | `0x00474A80` (`events_cities_random`) | gift to the city: money → treasury + `city.gifts_received_this_year`; draws RNG |
| 24, 25 | Lava flow, Tidal wave | `0x0046D6D0` (same as 3) | terrain event |
| 26 | Monster invasion | `0x00481430` | |
| 27 | God invasion | `0x00482B10` | |
| 28 | Sink land | `0x0046D790` | |
| 29 | (no text) | `0x00474F60` | tribute received: treasury + `city.tribute_received_this_year` (+0x4AA8) (**hypothesis** on name) |
| 30 | (no text) | `0x004715C0` | request variant (same slots as type 1) |
| 31 | – | `0x004742A0` | announce-type event |
| 32 | – | `0x004752A0` | resources/money received after a raid → treasury + gifts_received (hypothesis) |
| 33 | – | `0x004756B0` | announce-type event |
| 34 | – | `0x00480A00` | empire/city event (rank 7) |
| 35, 36, 37 | – | `0x0046E1A0`, `0x0046E400`, `0x0046E5A0` | Poseidon-era map events using `0x00FE6908` (rank 118), map positions |
| 38 | – | `0x00481A30` | calls `0x004AC7C0`, `0x004E8B00` |
| 39 | – | `0x00481A80` | map position event, message 0xDE |

That makes 33 distinct handlers. Details belong to the trade-empire, religion and military docs.

## 8. Other globals of the time core
| address | name | meaning |
|---|---|---|
| `0x00F2A988` | `difficulty` | 0 = very easy … 4 = very hard (rank 12; the index of every difficulty table) |
| `0x00902928` | `scenario_start_year` | i16; `year` is set from it at scenario start (`0x0051D5F0`) |
| `0x00902948` | `scenario_start_funds` | initial treasury before the difficulty factor |
| `0x00665E2C` | `editor_mode` | cycle skipped when set |
| `0x00F2A774` | `game_speed` | 10..100, default 90 |
| `0x00F2A768` | `game_paused` | toggled by the pause key |

## 9. Scheduling and performance (RE)

Question asked: how does the original spread work over time, and which tricks could a Python
port copy? Short answer (**verified** from the code read below): the original has **almost no
scheduling tricks**. It is brute force in C: every walker slot is visited every tick, every
daily building pass loops over the whole building array. The only things that look like
"distribution" are (a) the 51-step cycle puts each daily pass on its own tick, (b) state is kept
as small counters/timers measured in days, so most work is "decrement a byte", (c) cached lists
and grids rebuilt once per day, (d) route searches are rare (once per trip). Addresses are GOG
`Zeus.exe`.

### 9.1 Frequency of each system (per building)
Everything below is **once per cycle ("day", 51 ticks)** over *all* buildings, unless noted.
The loops are `for i in 1..buildings_last` (`DAT_0091EBF8`, recomputed at step 10 by
`buildings_update_highest` `0x004889F0` = highest slot with `state != 0`; it also runs
`g_storages_high`). There is **no slicing** (no "building i on tick i mod N", no per-step
subset): the 51 steps are 51 different *kinds* of pass, not 51 slices of one pass. **verified**
(read `0x00484FE0`, `0x00485360`, `0x004860A0`, `0x004871B0`, `0x00484D20`, `0x00484DE0`,
`0x004842A0`, `0x004FE290`, `0x0048CFB0`, `0x00493140`, `0x00492260`, `0x005BFDE0`).

| step | pass (name) | per-building work |
|---|---|---|
| 12 | `cycle_buildings_pass_12` `0x00484FE0` | `access_mode` flag (Building field `access_mode`) for service/industry buildings, via `house_find_road_access` (ring scan) |
| 20 | `cycle_production_progress_20` `0x00485360` | farm/industry/tree growth and production progress, 1 add per day |
| 21 | `buildings_road_access` `0x004856A0` | recompute each building's road tile and road network id (`b+0x14`) |
| 22 | `house_room_update` `0x004860A0` | builds `g_house_list` (`house_list_build` `0x00486050`: ids of active houses), room = capacity - population |
| 23 | `city_population_update` `0x00486190` | immigration/emigration waves (batched: `<4` per day are accumulated in `g_immigrants_pending`, sent when >= 4), labour pool |
| 24 | `house_evict_overcrowded` `0x004871B0` | iterates `g_house_list` only |
| 25 | labour (a/b/c) | sector allocation, then workers to buildings; no walkers |
| 31 | `buildings_spawn_walkers` `0x0048CFB0` | per building: spawn timer `+1` per day; walker spawns when timer > delay (delay from staffing %, e.g. fountain 1/3/7/15/29 days) and the previous walker (`b+0x2A`) is gone |
| 33 | `buildings_count_by_type` `0x00491820` | per-type counts and timer decrements (`+0xA9..AB`) |
| 35 | `houses_coverage_decay` `0x00484D20` | per house: 7 service-coverage bytes (the `edu_access` group in the Building struct; the ones the walkers set to 0x60) `-1` if > 1 |
| 36 | `houses_culture_compute` `0x00484DE0` | culture score from the four coverage bytes (+20/+15/+20/+25, Poseidon 20/20/15/25, +10 unique venue) |
| 37/38 | desirability | whole-map grid rebuild, then per-building lookup `0x004842A0` (max over footprint, +10 if flag) |
| 39 | `houses_evolve` `0x004FE290` | **loops slots 1..3999** (not `buildings_last`); per house type handler; luxuries `house_consume_luxuries` only on `day_of_month` 0 and 7 (twice a month); sets `DAT_0091EA08` when a house changed |
| 40 | `cycle_buildings_pass_40` `0x00484030` | state 3 -> 1, ruins cleanup |
| 43 | `buildings_fire_burn_spread` `0x00493140` | burning counters; burning list capped at 499 entries |
| 44 | `buildings_fire_collapse_risk` `0x00492260` | fire/collapse risk accumulation and rolls (RNG kept in locals inside loops) |
| 45 | `houses_spawn_criminals` `0x005BFDE0` | per house, per unrest table row: roll `rng_15 % 200 == 0x7F` |
| 48 | `0x00488220` | tax-collector coverage timer `-1` |

Per **tick** over all buildings: only `multi_tile_buildings_update` `0x00534F60` (pyramid/composite
animation; skips the other parts of a composite by jumping `i += part_count`). Per **month**
(16 days): finance (taxes, wages), `house_consume_luxuries` twice, god timers, scenario events.
Per **year**: births/deaths flag `_g_year_end_flag` in `city_population_update`.
Nothing runs "every N ticks" other than via the cycle step; the ten `tick_period_counters` are
dead (§2). **verified**

So a house is evaluated for evolution **once per day** (16 times a month); devolution needs
several failed days in a row (counter `b+0x82`: 3 common, 10 elite; housing.md), so the daily
check is cheap state-machine work, not a heavy computation.

### 9.2 Cached results used instead of queries (the real "trick")
- **Service coverage is a timer on the house, not a query.** A service walker, at every tile
  center, scans the 5x5 square and writes `0x60` (96) into the matching coverage byte of each
  house tile it sees (`tile_service` `0x004DFB70` and `0x004A60E0`..`0x004A66B0`, walkers.md §6).
  Houses never ask "which fountain is near me": they read the byte. The byte falls by 1 per day
  at step 35 (`0x00484D20`). Coverage therefore lasts 96 days (6 months) after the last walker
  passed. **verified**
- **Per-tile "walker memory" grid** `grid_b1e8f8` `0x00B1E8F8` (walkers.md §6): 16 two-bit
  channels per tile; roamers pick the neighbouring road with the lowest memory (spreads them),
  decay every 8th day (step 45, `0x004A3140`). It replaces any global planning of patrol routes.
- **House list** `g_house_list` (u16 ids, `0x00486050`), built at step 22 and reused at step 24
  (and by `city_military_manpower`). Burning list (<= 499). Storage list `g_storages_high`.
- **`buildings_last` high-water mark** (step 10) bounds the daily loops (the 4,000-slot
  array is mostly empty); `houses_evolve` ignores it and scans 3,999 slots.
- **Road network ids**: `road_networks_update` `0x00491FE0` (step 7, daily) flood-fills every road
  tile into a network id (`g_grid_road_network`, 1 byte/tile; keeps a top-10 table by size
  `0x00FEB100`). Buildings copy the id of their access tile into `b+0x14` at step 21. Cart
  destination candidates are filtered by `b+0x14 == cart network` *before* any path search
  (storage-distribution.md), so unreachable targets cost nothing. **verified**
- **Playable-area row bounds** `0x00DA24B0` (row start index), `0x00DA2BD0`/`0x00DA2840`
  (first/last column), count `0x00DA2F7C`: the map is a 228x228 array but the playable area is a
  diamond/rectangle in iso space; whole-map passes (desirability from terrain `0x00493C80`,
  road networks `0x00491FE0`, memory decay `0x004A3140`) loop row by row inside these bounds and skip
  the corners. **verified** (use); the exact shape is a **hypothesis**.
- **Live counters** by figure type `0x004E3420(id, +-1)` maintained on create/delete
  (soldiers, enemies), per-building walker counters `b+0xA8/+0xA9`, `b+0x2A` = the one service
  walker alive. Spawners test the pointer instead of scanning the figure array.
- **Route grid** `grid_route` `0x0105FE40`: passability bits per tile are **not** recomputed per
  search. They are rebuilt for a rectangle (`0x005876F0`) when a building/road changes, and for
  the whole map at certain steps (21, 39, 40, 43, 44, month change). `houses_evolve` sets a dirty
  flag `DAT_0091EA08` and rebuilds the route grid once at the end if any house changed.
  So route search itself never inspects terrain flags. **verified**
- **Ring tables for road access**: `0x005F1680 + 0x60*size`, the pre-ordered edge tiles of a
  building footprint (walkers.md §7).
- **Random per-tile grid** `0x00CA7FF8` (u8 per tile) is used as a deterministic tie-break
  (`(grid_random[tile] + roam_tiles) & 6` at junctions) instead of drawing RNG per junction: one
  fewer RNG call and no dependence on call order. **verified**

### 9.3 Walkers
- **Array**: 2,000 slots x 388 bytes (`0x00DBD788`). `walkers_update` `0x004CC8C0` loops `cur = 1..1999`
  every tick and calls `figure_type_table[type].handler` for every `state != 0` slot. There is
  no active list, no skip, no per-walker "next update tick". A free list (ring buffer of ids,
  `0x00DBB84C`) only serves allocation; `highest_live` is tracked but the update loop does **not**
  use it (always 1999 iterations; cheap when `state == 0`). **verified**
- **Hard cap**: 2,000 figures (create fails with 0 when the free list is empty), 999 route slots,
  routes <= 499 steps, 100 formation groups, 3,999 buildings. The caps bound worst-case cost.
- **No frame divider**: all walkers run every tick. Speed is expressed only as sub-steps per
  tick (15 sub-steps per tile, `tile_progress`; patterns in walkers.md §1.3, state `speed_phase`
  +0x160). `speed_code 6` = 1 sub-step/tick = **15 ticks/tile** (our value is right); code 12 = 2
  sub-steps = 7.5 ticks/tile; code 3 = 1,0,1,0 = 30 ticks/tile; the patterns give the stated
  averages, e.g. code 5 = 1,1,1,0 = 20 ticks/tile, code 7 = 1,1,1,2 = 12 ticks/tile (15 / avg).
  Sub-step movement is only for animation smoothness: **all decisions happen at tile centers**
  (`tile_progress > 14`) and the tile occupied changes at sub-step 8 (`figure_change_tile`
  `0x004D9330`). A port that moves a walker one tile every `15 / avg` ticks (accumulator per
  walker) is equivalent for the sim state **except** the instant of the tile change (halfway
  through the tile) and the position at which interactions with other figures happen.
- **Per-tile figure lists** `grid_figure` `0x00D0D878` (u16 head per tile, `next_on_tile` chain):
  maintained on every tile change. Used for encounters (combat, `0x004D4DA0`) and not for
  service coverage (which reads the building grid). Cleaned when the month changes
  (`0x004CC850`). Not needed by an economy-only port.
- **Cost of a tick per walker** is small: roamers do 1 sub-step -> 1 comparison; once per 15
  sub-steps they read 4 neighbour terrains, maybe the memory grid, and scan 25 cells (coverage).
- **Spawning is rate-limited by design**: one service walker per building (`b+0x2A`), spawn timers
  in days, and `blocked_types` countdown (`0x00EF60B0`, monthly).
- **Roam budget** `roam_len += speed code` per tick; ends at `max_roam` (0x900/0xC00/0xF00),
  i.e. walkers have a bounded lifetime (<= 3,200 ticks for culture, 512 for generic), so no
  walker lives forever (walkers.md §5.5).

### 9.4 Pathfinding cost control (see also pathfinding.md §8)
- Roaming walkers use **no pathfinding at all** (local rule at each center, §5.4).
- A **route** (BFS over `grid_route`, 4-neighbour, FIFO ring queue of 51,984 entries) is requested
  only when `route_id < 1` at the start of a trip or after a blocked/redirected trip
  (`figure_route_walk` `0x004D7BD0` -> `figure_find_route` `0x004D8220`). After the search the
  path is traced back and stored as a direction list in a route slot, then followed with no
  further search. **No route cache across walkers, no search radius, no per-tick cap, no
  A\*.** Early exit as soon as the destination is dequeued. Each plain BFS clears the full
  51,984-int distance grid first (`0x00588920`); a "lost" walker (dest unreachable) gets
  direction 10 and is usually deleted, so failures do not retry every tick. A failed search on a
  *blocked* route (direction 9) frees the route and searches again at the next opportunity.
- **Multi-target search for "nearest X"**: `route_find_listed_tile` `0x00588B20` floods once from the
  walker and stops at the first tile of a candidate list (list marked in a second grid
  `0x00FFA580`). `find_storehouse_bay` `0x00488E20` collects *all* eligible bays by a linear scan of the
  building array, then calls `0x004D7D10` (find_route variant taking the candidate tile list) with
  one flood. So "which warehouse is nearest by road" costs one BFS, not one per candidate, and
  the road network id filter removes unreachable ones first.
- **Reservations instead of re-search**: carts reserve the destination (`b+0x114/0x116`, `+0xC4 |=
  0x40`) so later carts pick elsewhere without a conflict-resolution search.
- Weighted search (`route_search` `0x00502EE0`, military) has a result cache keyed on
  (src,dst) plus a `limit` of pops (100000). Only military uses it.
- Ship searches: full-map BFS limited to 50,000 pops (pathfinding.md §7).

### 9.5 Game speed -> ticks per frame
`simulation_due` `0x005168A0` (§1): `k = (100 - game_speed)/10`, delay table
`speed_delay_ms = [0,20,35,55,80,110,160,240,350,500,700]` (+2 ms); `game_speed` 10..100, default
90 (k=1, 22 ms). `game_turn` runs **at most one tick per main-loop pass** (the `n = 10000` is only
a "due" flag; the loop clears `n` after the first tick unless `fast_forward` is set). There is
no catch-up: if a frame takes longer than the delay, the game simply runs slower. Hence the
game never runs more than one tick per rendered frame, ~45 ticks/s max at default speed
(one day = 51 ticks ~ 1.1 s, a month ~ 18 s), a few hundred ticks/s at speed 100 only if the
frame loop allows (**hypothesis**, depends on frame rate). `fast_forward` (`0x00F2AA9C`) = up to 10,000 ticks per pass (cleared on mouse
up or at new year). Per-speed delay (ms): speed 100:0+2, 90:22, 80:37, 70:57, 60:82, 50:112,
40:162, 30:242, 20:352, 10:502 (700 for k=10 is unreachable because `k >= 10` returns 0).
**verified**

### 9.6 What is worth copying (our assessment, partly opinion)
See the reply summary; short list:
1. Keep daily passes as dense loops; use `buildings_last` and typed lists (houses, producers,
   spawners) built once per day, as the original does (`g_house_list`).
2. Coverage as decaying per-house timers (96 days) fed by walkers, not distance queries.
3. Network id per road tile (one flood a day) and per building; reject unreachable cart/trade
   targets before searching; multi-target BFS for "nearest by road".
4. Routes: search once per trip, store directions, never per tick; roamers use local rules and
   the per-tile memory grid, no searching; roam budget bounds lifetime.
5. Walkers in Python: keep an *active list* (original scans 1999 slots because it is C);
   a per-walker accumulator or a wake-up tick queue replaces per-tick sub-step arithmetic; waiting
   states (timers `action_timer`, spawn-in-building, rest) should sleep in a heap keyed by tick.
6. Incremental route-grid rebuild by rectangle + dirty flag; desirability could be dirty-flagged
   too (the original recomputes the whole grid daily; **not** an original trick).

## Cross-references
- `0x00566C00`/`0x00566B90` health target/value (`city.health_target` +0x14, `city.health` +0x18):
  target = population-weighted average over houses with population of (50 if `b+0x78` + 50 if
  `b+0x7F`), plus a small-city bonus from table `0x00641ED0` (pop < 100 → +80, < 200 → +80,
  < 300 → +70, … < 1000 → +10, else 0), clamped 0..100. Owner: services.
- `0x00487750` labour allocation, `0x00487BA0` worker assignment: economy/population.
- `0x00566930` `population_record`, `0x00567620` emigration: population.
- `0x004E69A0`, `0x004E6B10`, `0x004E5EB0`: gods (religion).
- `0x0047ECD0`, `0x0047EE20`, `0x00477210`, `0x00477240`, `0x004771E0`, `0x00477270`: empire (trade-empire).
- `0x00568D20`, `0x00569010`: military (invasion arrival).

## Open questions
- `0x004AA6D0` (months 2 and 11) and `0x004AA640` (every day): which seasonal rule.
- `0x00519590`, `0x00519910`, `0x005247A0`, `0x00524860`: most likely UI/messages; check that they write no sim state.
- `fast_forward` `0x00F2AA9C`: which key sets it.
- `city+0x3C` population history: is it the source of the population graph only?
- Event types 29–39: confirm the names (Poseidon editor text group?).
