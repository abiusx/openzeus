# Heroes and monsters

Status: **verified** from the exe unless marked. Addresses refer to GOG `Zeus.exe`.
Figure/building fields: see [../re/structs.md](../re/structs.md); new names in `re/structs/religion.tsv`.

## Summary
- Monsters are figures of type **0x44** (`FIG_MONSTER`), heroes **0x45** (`FIG_HERO`), gods 0x43,
  Medusa's victims become **0x46** (`FIG_TURNED_TO_STONE`). Figure `+0x0B` holds the monster id
  (0..17) or hero id (0..7).
- A monster is created by a scenario event of type **0x1A** (monster attack), by god wrath (the
  event's monster slot points at a hostile god's monster), or as a *guardian* monster of a
  friendly god (Poseidon→Kraken, Ares→Dragon, Hephaistos→Talos, Hades→Cerberus).
- A hostile monster cycles: rest near its lair for a random number of "days" → rampage for
  `rampage_months × 16` days destroying buildings/killing walkers of up to three target categories
  → walk home → rest again. Until a hero kills it.
- Each monster has exactly one hero who can kill it. A hero is summoned from his Hero's Hall
  (building 125) when all 5 requirements are met (some are consumed). The hero walks to his
  monster and, once in melee, kills it after a 300-tick duel (150 vs a god).
- `monster_behavior_<level>.txt` gives per monster 9 bytes: three (min,max) rest-time ranges for
  aggressiveness 1..3, the rampage duration, an unused byte, and the aggro radius.

## Ids
Monster id (figure `+0x0B`, text group 190, `Zeus_<name>` sprites at `0x00640A4C`):
0 Hydra, 1 Kraken, 2 Cerberus, 3 Cyclops, 4 Minotaur, 5 Medusa, 6 Calydonian Boar, 7 Dragon,
8 Talos, 9 Hector, 10 Scylla, 11 Maenads, 12 Sphinx, 13 Chimera, 14 Harpy, 15 Echidna,
16 Black Warrior, 17 Satyr (17 = Dionysus' wine-carrying satyrs, spawned by `0x004C51E0`; 16:
hypothesis, a god helper of the same kind; neither is in the behaviour file).

Hero id (text group 185 0..7): 0 Achilles, 1 Hercules, 2 Jason, 3 Odysseus, 4 Perseus,
5 Theseus, 6 Atalanta, 7 Bellerophon.

| function | mapping | addr |
|---|---|---|
| god → its monster | 0 Zeus→3 Cyclops, 1 Poseidon→1 Kraken, 2 Demeter→5 Medusa, 3 Apollo→10 Scylla, 4 Artemis→6 Boar, 5 Ares→7 Dragon, 6 Aphrodite→9 Hector, 7 Hermes→4 Minotaur, 8 Athena→0 Hydra, 9 Hephaistos→8 Talos, 10 Dionysus→11 Maenads, 11 Hades→2 Cerberus, 12 Hera→12 Sphinx, 13 Atlas→13 Chimera | `0x00586C90` |
| friendly god → guardian monster | 1→1, 5→7, 9→8, 11→2, else −1 | `0x00586D50` |
| monster → hero | 0,2→1 Hercules; 1,5→4 Perseus; 3,10→3 Odysseus; 4,6→5 Theseus; 7,8→2 Jason; 9,11→0 Achilles; 12,14→6 Atalanta; 13,15→7 Bellerophon | `0x00586DB0` |
| hero → its monsters (target search) | same pairs, inverse | `0x004FCD60`, `0x004FCBE0..0x004FCD30` |
| sea monster (lives on water, `fig+0x76=2`) | 1 Kraken, 10 Scylla | `0x0052F120`; `0x0052F190` = "not 1/10" (walks on land) |
| `0x0052F150` true for 1, 10, 16 | used as "can fight ships": checks enemy ships (`0x004AC7C0(1)`) | |
| no special ranged attack (`0x0052FA00` false) | 5 Medusa, 16 | |

## Scenario monster list `0x00FFA450` (sav rank 122) — `monster_of_slot(k)` `0x00586B40`
ECX = `0x00FFA450`. k = 0,1: monster of the god in int slot 0 / 1 (hostile gods) via `0x00586C90`;
k = 2: int at `+0x60` (independent monster); k = 3..8: guardian of friendly-god slots 12..17
via `0x00586D50`; else −1. `monster_slot_of(monster)` `0x00586E70` returns the first k (0..8)
with that monster, or −1. `monster_is_guardian(m)` `0x00587020` = slot in 3..8.

Unit type (figure model col 0) of a monster, `figure_type_value(f,0)` `0x004E1B20`:
slot 0,1,2 → **8** (bad monster); slot −1 → 8, or 7 if `fig+0x10C & 0x80` (Satyrs set 0x80);
slot 3..8 → **7** (good monster). Gods: 10 (bad god) if god record `+0x00 == 1`, else 9.
Other stats come from the figure model row 68 "Monster" (hp 500, attack 50, armor 10, missile
armor 10, speed 7 in Normal) — **no per-monster hp**; the behaviour file does not change them.

## Monster records `0x00FE43F0` (sav rank 123), 18 × 32 bytes
| off | type | meaning |
|---|---|---|
| +0x00 | i32 | monster id (= index, set by `0x00587280`) |
| +0x04 | i32 | current monster figure (validated by `monster_record_figure` `0x0052F1D0`: state 1, type 0x44, `+0x0B` = id) |
| +0x08 | i32 | scenario event index that spawned it (0x8C = the special event at `0x0091B7C4`) |
| +0x0C | i32 | count of extra figures (≤4) |
| +0x10 | i32[4] | extra figures of the same monster (`0x0052F370` pushes the old current one here) |
`0x0052F1D0(n)`: compacts the list, drops dead/duplicate figures, promotes the last extra if
`+4` is 0; returns `+4` for n=0 else extra n-1.

## monster_behavior_<level>.txt → `0x00FE42F0`, 16 × 12 bytes
Loader `0x0052F460` reads **all nine** numbers of a row (model.md says eight; its "ninth"
is actually read): slot byte i = file value i+1. Only reader: the monster handler, which every
tick calls `monster_params_load` `0x00532290` (ECX = `0x00FE43B0`, the monster behaviour object;
not decompiled by Ghidra) for monster ids < 16:
```
lvl = fig+0x7B                       # aggressiveness 0..3, from the spawning event byte +0x3E
if lvl == 0:  obj.rest_base = obj.rest_span = 10000
elif lvl == 1: obj.rest_base = b[0]; obj.rest_span = b[1]-b[0]
elif lvl == 2: obj.rest_base = b[2]; obj.rest_span = b[3]-b[2]
else:          obj.rest_base = b[4]; obj.rest_span = b[5]-b[4]
obj.aggro_rings = b[8]               # obj+0x04
obj.rampage_months = b[6]            # obj+0x10
obj.target_cat[0..2] = fig+0x115, +0x116, +0x117   # obj+0x14..0x1C
```
| byte | file col | meaning | evidence |
|---|---|---|---|
| 0,1 | 1,2 | rest days min, max at aggressiveness 1 | verified `0x00532290`, `0x0052FA80` |
| 2,3 | 3,4 | same, aggressiveness 2 | verified |
| 4,5 | 5,6 | same, aggressiveness 3 | verified |
| 6 | 7 | rampage duration in months (`×16` days) | verified `0x005304B0` |
| 7 | 8 | **never read** (3 in all files) | verified (only reader is `0x00532290`) |
| 8 | 9 | target-search radius in rings around the monster (rings from table `0x005F07EA`/`0x0078AD6C`) | verified `0x0052FD30` |
The "day" is one `month_advance` call (16 per month, 51 ticks each). Level 0 = 10000..19999
days, i.e. never attacks. The `NEVER` word in the file is not read. Rest days drawn:
`rest = rest_base + (rng15 % rest_span)` → range [min, max−1]; if min == max the exe divides by
zero (no shipped file does that).

## Monster per-tick handler `0x004C8760` (figure type 0x44; not decompiled — disassembly)
Header, every tick, before the action switch:
```
ut = figure_type_value(f,0); spd = figure_type_value(f,8)
monster_record[f.monster].note_figure(f)            # 0x0052F370
if is_1_10_16(m) and walks_land(m):  f+0x76=0; f+0x72=6
elif walks_land(m): f+0x76=0; f+0x72=3; if ut==8 and (f+0x10C&0x100 or f.action==7): f+0x72=2
else: f+0x76=2                                        # sea monster
f+0x65=0; f+0x180=0
if m < 16: monster_params_load(f, &behaviour[m])
if f+0x82 (target) is a hero (0x45) with flag 0x10: f+0x82 = 0
switch f.action (0x38), jump table 0x004C8E2C:
```
| action | per tick | on enter (vtable `0x005D9880`+4 → `0x0052F750`) |
|---|---|---|
| 0 | `state = 2` (remove) | not good monster: flag 0x200, → 6 |
| 1,2,3,20,21 | → 6 (next 7) | — |
| 4 | dying `0x004D60B0` | — |
| 5 | fight anim `0x004D5F10` | — |
| 6 | walk home: `+0x36` −1 per day; on arrival → 24 | `0x0052FA30`: dest = spawn tile `+0x2C/+0x2E` |
| 7 | **rest/roam** `0x005304B0` | `0x0052FA80`: unless flag 0x200 (then clear it): `+0x36 = rest_base + rng15 % rest_span`, `+0x92 = day`; home `+0x30/+0x32 = dest` |
| 8 | walk → 7 | `0x00530AE0` |
| 9 | `0x00531050` fight figure | `0x00531000` dest = target figure |
| 10 | `0x00531550` choose next target | `0x00531320` pick targets (below) |
| 11 | `0x005318B0` go to target | `0x005315C0` |
| 12 | `0x00532670` | — |
| 13,17 | walk, on arrival remove (`state 2`) | 17: `0x00533600` dest = spawn tile (leave map) |
| 14 | `0x00533070` | `0x00532F10` |
| 15 | `0x00533340` chase enemy; at Chebyshev 2..3 → 28 | `0x00533220` |
| 16 | → 15 | `0x00533580` |
| 18 | `0x00533670` | `0x00533640` (`+0x42=800`) |
| 19 | `0x00533A80` | `0x005339E0` |
| 22 | `0x00533890` | `0x0056E070` |
| 23 | `0x00534150` (duel with hero) | — |
| 24 | → 7 (day countdown continues) | `0x00534430` |
| 25 | `0x00532700` smash building | `0x005324D0`: `+0x36 = 2 × frames(attack anim)` |
| 26 | `0x005327A0` walk to target building; ≤2 tiles → 27 | `0x00532520` |
| 27 | `0x00532C70` smash building | `0x00532620`: `+0x114 = 2 × frames` |
| 28 | `0x00530ED0` missile/special attack | `0x00530EA0` |
| 29 | walk; rampage timer; at 0 → 17 | `0x00530CD0` |
After the switch: direction/animation frame computation (`0x00533B60`), not simulation.

### Rest / roam, action 7 `0x005304B0` (verified)
```
if ut == 7 and no current record figure: → 0x11 (leave)
if f+0x36 < 0: goto timer_done
if f+0x92 != day: f+0x36 -= 1; f+0x92 = day; if f+0x36 < 1: goto timer_done
f+0x114 = max(f+0x114 - 1, 0)
if f+0x114 == 0 or f+0x114 > 60:
    draw main RNG (31 steps); f+0x114 = rng15 % 30 + 30          # 30..59 ticks
    if god_engages(f) (0x0052FBA0)       : flag 0x200; → 9      # Apollo/Zeus god figure targeting f within Chebyshev < 12
    elif seek_enemy(f) (0x005300D0)      : flag 0x200; → 9      # good monster: enemy armies -> 15; else ring search 0x0052FD30
    elif ut == 8 and (b = nearest_building(f, (msrand()*4 >> 15) + 2)): f+0x5E = b; flag 0x200; → 26
else: figure_move, then on arrival (direction 8) wander around home (+0x30/+0x32), tile search 0x005301E0 radius 4
timer_done:
    if ut == 8: f+0x108 = rampage_months << 4; f+0x104 = day; → 10 (next 11)
    elif enemies (ships for 1/10/16, land otherwise): → 15
    else → 0x11 (go back to spawn tile and vanish)
```
So the scan tick does not move the figure: a step under way lasts one tick longer per scan, and a new
route starts on the tick after the arrival. Ours (sim/heroes/monsters.py rest / move2, `step_due`): mid-step
nothing but the scan runs; an action change waits for the step under way to end (bugs.md 395: our step was cut at
the scan and the next one taken at once, a monster crossed two tiles in one step's time).

`nearest_building(f, d)` `0x004ABE80`: lowest Manhattan distance ≤ d among active buildings whose
type has `0x00EF60B0[type] == 0`, not composite (sanctuary/monument, unless `0x00546530` etc.)
and not 100..114; for sea monsters only buildings with a water tile (`grid_terrain & 4`) under
or beside (offsets 0, 229, 458, 687, 916, 1145 by size). `msrand` = MSVC `rand()` `0x005CC7A2`
(seed `0x00662E30`, `seed = seed*214013+2531011; return seed>>16 & 0x7fff`) — **a second RNG**,
so d = 2..5.

`seek_enemy` ring search `0x0052FD30`: own tile then `aggro_rings` rings (offset lists
`0x005F07EA` → `0x0078AD6C`); first figure that is active, not dying, not 0x43/0x44/0x46/0x47,
`+0x65 == 0`, and hostile per the 11×11 table `0x00639430[ut_self*11 + ut_other]` → combat
target (`0x004E3280`). Sea monsters need a shore tile and a ship path.

### Rampage (bad monsters)
- Enter 10 `0x00531320`: clear `+0x5E`, `+0x82`; for cat in (obj+0x14, +0x18, +0x1C):
  `+0x5E = nearest_building_of_category(f, cat)` `0x004ABBF0` (reject composite/pyramid);
  `+0x82 = nearest_figure_of_category(f, cat)` `0x004AC020`; stop at the first category that
  yields something. Category 10 = main-RNG `% 11` (10 → empty list).
- Tick 10 `0x00531550`: rampage timer `+0x108 −1` per day; if ≤ 0 or no target → 6 (go home,
  then rest) else → 11.
- 11 `0x005318B0`: walk to target, then 25 (building) / fight (figure) / 28 (ranged).
- 25 `0x00532700`: `+0x36` counts down per tick from 2×frames; at < 1 the building is destroyed
  (`building_destroy` `0x004928C0`), → 10. 27 does the same via `+0x114`.

#### Rampage in detail (ported 11-02, sim/heroes/rampage.py; oracle 1I-missile)
- `monster_pick_targets` `0x00531320` (on-enter 10), per category in order: `+0x5E` = `nearest_building_in_category`
  `0x004ABBF0` (state 1, type not disabled by a curse `0x00EF60B0`, type in the list `0x006383E0`, Manhattan to the
  record's x/y, the first of equals by id; a sea monster (`+0x76 != 0`) only buildings with water under the origin or
  the far corner); the nearest is then **dropped, not replaced**, when it is a composite piece or a type 100..114
  that is damaged (vt+0x98, `0x00546510`) or not attackable (vt+0x8C, `0x005463B0`); `+0x82` =
  `nearest_figure_in_category` `0x004AC020` (every figure: state 1, not dying, not hidden, flag 0x10 clear, type in
  the list `0x00638C78`, for a monster not 0x43 / 0x44 and, if it is a sea monster, on a water tile; Manhattan,
  strict `<` from 1000: the first of equals in slot order) — written even when 0. A building or a figure ends the
  search. Category 10: `rng15 % 11`, drawn separately by each of the two searches.
- `0x00531550` (tick 10): a rampage day (`+0x104` stamp, `+0x108 − 1`); `+0x108 < 1` or neither target →
  `set_action(6, 7)`, else `set_action(11, 6)`.
- `0x005315C0` (on-enter 11): route freed; the building checked (state 1 and the composite rule above) and the
  figure (not dying / state 1 / not hidden), each cleared if not; no building: no figure → `set_action(10, 11)`,
  else dest = the figure's tile, `+0x36 = 0`; a building: dest = `FUN_004D2F10` (land, route mode 2/3: the first tile
  of the building's own records in ring order — origin, then rings: top row, bottom row, left column, right column —
  that is not water) or `FUN_00461ED0` (sea: the first sailable tile, `FUN_00461EB0`: grid_ship ≥ 0 or 0xFB).
- `0x005318B0` (tick 11): the day; `+0x36 += 1`; targets re-checked; none → route freed, `set_action(10, 10)`. At dest
  already → *arrived* (below). Else `figure_walk_then(speed, lost 10)` (the behaviour's vtable[0] at `0x005D9884`:
  arrival → `set_action(+0x34)`: 6 after 10's (11, 6), 0 after a shot (→ on-enter 0: flag 0x200, (6, 7)), 10 after
  (11, 10)); then a ranged monster at Chebyshev 2..3 of the building's x/y shoots (28, back to the current action);
  lost → flag 0x100 (route mode 2 from now: it bashes, see "Track 1I reading"), route freed; action 0 / 10 →
  `set_action(10, 10)` and on to *arrived* only if at dest; 8 → *arrived*; 9 → a building: dest =
  `FUN_004D2F10` again (sea: `FUN_00461C20`, the first open water tile without a figure), none → building dropped;
  a figure: dropped; route freed. Every 50 ticks (`+0x36 > 0x32`, tile progress 0 or 15): flag 0x100 cleared,
  0x005315C0 again, `+0x36 = 0`. A building target and `FUN_00461EB0(own tile)` (only on sailable water: a land
  monster never) → Chebyshev ≤ 1 (ranged: < 2) → 25, ranged 2..3 → 28.
  *Arrived* (`LAB_00531DF0`): a building — gone → `set_action(10, 11)`; dest x == its x **or** dest y == its y → 25
  facing it; ranged 2..3 → 28; < 3 → 25; else dropped. A figure — gone → (10, 11); a trireme whose wharf has its
  crew home (`+0xC4 & 1`) → 28 at it (any monster); else `FUN_004D5330` (figure_tile_contact with the first figure of
  each of the 8 neighbours, until a fight starts), on its tile → figure_tile_contact; ranged 2..3 → 28; > 9 tiles or
  mid-tile → `set_action(11, 10)`; else action = 11 directly and 0x005315C0 (a new dest). End: action 0 →
  `set_action(11, 10)`.
  So a land monster takes a building by bashing its way onto its tile (mode 2 after the first, lost, mode-3 route);
  25 follows only for a sea monster or when it arrives where the building still stands.
- 25: `0x005324D0` on-enter `+0x36 = 2 × frames(monster_anim_info(m, 0x19))` (the attack group); `0x00532700` each
  tick: the day, `+0x36 − 1`, at < 1 `building_destroyed_by_attack(b.x, b.y)` (no state check), `set_action(10, 11)`;
  the bash sound FUN_004DB3D0(f, 0) every tick.
- Movement: figure_move / figure_route_walk tick by tick (sub-steps by the speed code, tile change at progress 8,
  the route decision at 15; figure_find_route puts the progress at 15) as the guardians' (below). Route mode 3:
  figure_find_route `0x004D8220` case 3: the dest must have route bits & 0x11C; a roads-only search (0x0058A6C0, mask
  0x10C) traced 4-way (route_trace 0x0058BC80 mode 4), else 8-way; no road route: route_distance (0x11D) traced
  8-way (`guardians.route3`).
- Ours: the 28 → 11 / 10 return through `rampage.set_action`; the oracle comparison (tools/oracle_monster_missile.py)
  equal, and the Maenad's tile progress per tick equal over the 11 phases. Her mode-2 route (route_search
  0x00502EE0, then route_trace(8)) is ported line by line since 11-02 (`sim/military/routes.py`, pathfinding.md
  section 5): her first step is the exe's (0771 from (121, 200) to (120, 196), around the plot's cost 10); before,
  an 8-way Dijkstra (`monsters.route2`) went diagonally first.
- Victims: Hydra/Kraken (`id < 2`) → `0x00532340` (figure eaten: `+0x178=0x7C00`, action 4,
  flag 0x10); Medusa → `0x005323A0` creates a `0x46` statue; others: `0x004DAB30` kill, action 4.

Target categories (building list `0x006383E0`, 50 ints per cat; figure list `0x00638C78`,
15 ints per cat; 0-terminated):
| cat | buildings | figure types |
|---|---|---|
| 0 food | granary, farms, agoras, goat farm, hunting lodge, fishing/urchin wharf, corral, orchard | hunter, fishing boat, sheep/goat/boar, shepherd, goatherd, urchin, cart, horse, wolf, cattle, rancher |
| 1 sea | fishing wharf, urchin quay, warship wharf, dock | fishing boat, urchin, trireme, trade ship |
| 2 industry | timber, marble, foundry, mint, sheep farm, sculpture studio, oil press, winery, armory, storehouse, orichalc, chariot workshop, black marble | cart, storehouseman, deliveryman, water bubbles?, shepherd, goatherd, sheep, goat, miner, woodcutter, grower |
| 3 military | armory, horse ranch, wall, tower, gatehouse, warship wharf, foundry, chariot workshop, guardpost | miner?, watchman, hoplite, horseman, rabble, trireme |
| 4 wealth | tax office, elite houses, mint, dock, trading post, race track | miner?, clerk |
| 5 defences | tower, warship wharf | hoplite, horseman, trireme, watchman, rabble |
| 6 residential | houses 2..8, guardpost, infirmary, … | water bearer, superintendent, immigrant, healer, scholar, philosopher, watchman |
| 7 beauty | columns, bench, gardens, … 119 commemorative, 25 | none |
| 8 religion | sanctuaries 84..98, hall 125, sculpture studio, marble quarry | hero, artisan, priest |
| 9 culture | palace, stadium, theatre, hall, sanctuaries, race track, museum, observatory, elite houses | nobleman |
| 10 | random 0..10 | random |
(Names from the model JSON row = type id; figure type ids = figure model rows.)

### Ranged/special attack, action 28 `0x00530ED0` (ported 11-02, oracle 1I-missile)
Entry: from 9 (`0x00531050`, chase a figure), 11 (`0x005318B0`, rampage: a building or figure target) and 15
(`0x00533340`, guardian chase) when `monster_has_ranged` `0x0052FA00` (every monster but Medusa 5 and 16) and the
Chebyshev distance to the target tile is 2..3; tested every tick after that tick's walk (the step into range shoots in
the same call). `figure_set_action(this, f, 28, ret)` keeps the action to return to in +0x34; on-enter `0x00530EA0`:
anim frame 0, flag 0x4000 cleared (0x8000 is not). The handler tail `0x004C8D4B` steps the frame +1 every tick
(wrapping at the group's count). Per tick:
```
frame 1 and !(flags & 0x4000): sound FUN_004D9D20 -> FUN_004DB3D0(f, 1): atk3 or atk4 (crt_rand * 2 >> 15);
                               face the target; flags |= 0x4000, &= ~0x8000
frame == 0x006409F0[monster] and !(flags & 0x8000):        (u32: 14,15,10,10,17,11,7,12,15,8,19,7,30,12,13,12,0,15)
    FUN_004D9D70: a missile 0x34 (unit class 8, bad monster) else 0x2D toward the target tile; flags |= 0x8000
frame == n - 1 (n = frames of the special group 0x?04, monster_anim_info 0x00533B60 with 0x1C):
    tile progress = 15; figure_set_action(+0x34)    (back to 9 / 11 / 15, which retest the range at once)
```
So a shot lasts n ticks (Maenads 13) and repeats while in range. At the end of a shot from 11 the rampage picks its
next target first when the building is gone (ours: 10 with the pick, as the exe's dump shows 10 there).
The missile: 0x34 handler `0x004BD970` / 0x2D `0x004BACE0`, flown on the shared fine line (military.md "Missile
flight"). A bad monster's 0x34 landing with no figure hit on a tile of an active building (`0x004DCF20`): the hit sound
FUN_004DB7A0, `wall_damage_add(building tile, 4, 2)` `0x00492830` (+2; past 4 building_destroyed_by_attack: the third
missile destroys it), the monster's target +0x5E cleared once it is no longer active; arrival or hit:
collapse_debris_spawn(x, y, 1, 1, 4, 0). A figure hit: figure_hit with the monster as attacker (attack col 2 vs armor
col 3, x1.5 for a bad monster, x2 more against a trireme). Picture: both handlers' 0x44 branch switch on the
missile's own +0x0B, which figure_create zeroes and 0x004D9D70 never sets (disassembly 0x004BDC44 / 0x004BB575), so
every monster's missile is group 0x222F (destruction group 46, 8 frames x 8 directions), sprite_anim_step rate 100,
direction `((dir32 - 4 view) & 31) >> 2` with dir32 = +0x11 = `FUN_0058D050(from, to) << 1` (16-way map direction,
0 = -y, clockwise; ours `defences.dir16`).
Ours: `monsters.go_shoot` / `shoot` (sim/heroes/monsters.py), `defences.shoot(.., aim)` / `_missile_end`; play mode
scene.js drawArrow ("monster_missile"), heroes.js sounds, data/play/heroes.json "missile" (tools/play_heroes.py).
Check: `python3 tools/oracle_monster_missile.py` (run re/oracle/runs/1I-missile, scenario
re/oracle/scenarios/monster-missile.txt, pokes `tools/oracle_heroes.py --missile-poke`): shot starts 0/13/26/39,
launches 7/20/33/46, the flights' tile sequences, the plot destroyed at 44 and the action sequence equal to ours;
the oracle shot m_368 (tick 1694) shows image 1243 = frame 3, direction 7 for dir32 30, as ours at the same camera.
The oracle advances the missile's frame every tick (its rate-100 gate fires every tick when the emulator runs slower
than real time); ours uses the default-speed rate (4 ticks a frame, bug 393).
The entry from 15 (guardians' chase) and 11's figure targets: ported 11-02 ("Guardians" below, "Rampage in detail").

### Monster actions as the exe (ported 11-02, TODO items 2..4; sim/heroes/monsters.py)
figure_monster_update `0x004C8760` runs every monster's handler every tick; ours schedules them every tick too
(`monsters._next`) and all of them move with figure_move's sub-steps (`rampage.move`: tile progress +0x39 0..15, the
tile change and its contact at 8, the next route step at a centre; the speed phase +0x160). Before 11-02 the
actions 6 / 7 / 9 / 26 / 0x17 stepped whole tiles on an 8-way BFS (7: mode 2 with a bash every 4th tick).
- Route mode, set by the header every tick (`monsters.route_mode`): the Kraken / Scylla water_mode 2; the Black Warrior
  (16, a land walker of `monster_is_1_10_16`) mode 6 (route_bfs_shore 0x0058B560, else route_distance); else mode 3
  (roads first: 0x0058A6C0 traced 4-way, else route_distance traced 8-way; `guardians.route3`), and a bad monster
  (class 8) with flag 0x100 or in action 7 mode 2 (`sim/military/routes.route2`). Mode 3's land is the route grid in
  mask 0x11D (`monsters.passable`, pathfinding.md section 2, ordered as 0x005876F0: orchard trees and roadblocks open,
  0x10000000 ground and race-track tiles blocked; not modelled: a marble tile being quarried, decor tile objects).
- Direction (+0x11) after figure_move: 8 arrived, 9 blocked, 10 lost, 11 standing at a building / wall / tower tile in
  mode 2 (`figure_check_next_tile`: the bash sound every tick (tail 0x004C8C72), the attack group drawn (the tail
  uses action 5's group), wall damage on ticks whose cycle_step & 3 == 0: building +1 over 10, wall +10 over 200,
  tower / gatehouse +1 over 400, then building_destroyed_by_attack).
- Spawn: `monster_spawn_and_act(m, ev, 6, 7)`: set_action(6, 7), so home at its first tick and then 7 (the rest timer
  is drawn then, not at the spawn).
- 6 (case 6): the rest day count, `walk_then(spd, lost 24)`; action 0 → (7, 0); a good monster then: enemies of its
  kind → (15, 16). On-enter 6 (0x0052FA30): route freed, +0x82 and +0x5E = 0, dest = home +0x2C.
- 24 (on-enter 0x00534430: home = here; tick): the day count, set_action(7, 0), direction ≥ 9 → route freed.
- 7 (`monster_rest_update` 0x005304B0): a good monster without its sanctuary → 0x11; +0x36 < 0, or counted below 1 on
  a new day → the rest ends (bad: rampage_months × 16 days, (10, 11); good: enemies → (15, 16), else 0x11); the scan
  byte +0x114 - 1 (not below 0; kept across actions: 27 uses it too): at 0 or past 60 one main-RNG draw (next scan in
  30..59) and the scan (god / enemy → (9, 9), building → (26, 26), flag 0x200); else figure_move: 8 → a building /
  wall tile within 4 rings other than dest becomes dest (route freed, flag 0x100 cleared), else at the roam centre
  `monster_wander_dest(-1, -1)` (home + two draws), else dest = the roam centre; 9 / 10 → the building search, else
  wander around here, snapped by route_tile_check (on water FUN_00461C20), else the roam centre. On-enter 7
  (0x0052FA80): flag 0x200 → cleared, timer kept; else a new timer (one draw); the roam centre = dest. The route is
  not freed on entering 7.
- 9 (0x00531050): the day count, +0x100 + 1, `walk_then(spd, lost 6)`; target gone / dying / hidden → (6, 7); ranged at
  Chebyshev 2..3 → 28 (+0x34 = the action now); arrived: Chebyshev < 2 → tile contact, else within the aggro rings of
  home → (9, 6), else (6, 7); 9 / 10 → target dropped, route freed; +0x100 > 50 at progress 0 or 15 → re-aim.
- 26 (on-enter 0x00532520; tick `monster_walk_to_building` 0x005327A0): mode 3 to a building tile is lost at once, so
  walk_then's set_action(7, 0) uses the flag 0x200 (timer kept); then within Chebyshev 2 of the origin the attack (dest
  on its row / column → 27; ranged and ≤ 3 → 28; < 3 → 27), else route freed and **set_action(7, 7): a new rest
  timer** (the flag was used up). 27 (on-enter 0x00532620: +0x114 = 2 × the attack group's frames; tick 0x00532C70):
  at 0 building_destroyed_by_attack at the record's origin and (7, 7): a new rest timer as well.
- 0x17 (0x00534150, held by a hero): FUN_004D5330 contacts, figure_move to him (re-aim every 16 ticks at a centre, or
  when 4+ away); the hero in 0xE / 0x10 or beaten → (6, 7); **exe bug kept**: the hero dying / gone / hidden →
  figure_set_action(HERO, 6, 7) (0x0053441D: the hero's slot gets action 6 and the monster stays in 0x17).
- Item 3 (11, 15 and 9 alike): a tile contact during the handler's walk starts a melee (action 5) and the handler goes
  on in the same call. A ranged monster whose target is at Chebyshev 2..3 then enters 28 with +0x34 = 5 (saved 5),
  leaving the fight without figure_fight_end (its opponent's next fight tick sees it gone and ends its own). At the
  shot's last frame set_action(5, 0): one tick in action 5; figure_fight_tick finds the old opponent not fighting →
  figure_fight_end puts back the saved action 28 (the tail steps the fight group's count, then the special group's),
  and the shot's frames run on (flags 0x4000 / 0x8000 still set: no sound, no missile) to the last one, where
  +0x34 = 0: on-enter 0 → (6, 7) for a bad monster, state 2 for a good one. Ours: `monsters._out_of_melee`,
  `_back_to_melee` (an opponent still fighting someone: the fight goes on with the old attack timer).
Checks: tests/test_heroes.py test_monster_rest_moves_as_exe, test_monster_shoots_out_of_contact; oracle 1I-missile
(tools/oracle_monster_missile.py: shots, launches, flights, destruction and the action sequence equal, the walk home
and the first rest ticks as the exe's: home at +65, a wander dest at the first rest tick); 1I-bash (both plots gone by
tick 1836 as the exe's, ours' detours out of the gully from tick 4896 as the exe's) and 1I-roam (the same roaming
pattern; positions differ by the RNG).

### Guardians (good monsters; ported 11-02, sim/heroes/guardians.py; oracle 1I-dragon)
A guardian is the monster of a friendly god (`0x00586D50`: Poseidon Kraken 1, Ares Dragon 7, Hephaestus Talos 8, Hades
Cerberus 2), unit class 7 when it is in a scenario guardian slot 3..8. Made by `monster_spawn(m, -1, sanctuary)`
`0x0052EEF0` (no event bytes; land monsters at the sanctuary's altar access, sea monsters at the sea entry; dest and
home = that tile) and given the god's entry action:
| god | caller | entry | then |
|---|---|---|---|
| Poseidon | `poseidon_month_kraken` 0x004E6260 (monthly, sanctuary +0xC4 & 8 clear, no figure) | (0x15, 0xF) | 0x005331E0: flags = 0, 0 days → 14 |
| Hades | `hades_month_cerberus` 0x004E62D0 (the same) | (0xE, 0xF) | 14 |
| Hephaestus | `hephaestus_help` 0x004E7E70 (his help, sim/gods/gifts.py) | (0x14, 0x10) | 0x005331A0: flags = 1, `+0x108` = 64 days → 14 |
| Ares | `sanctuary_update` 0x004E94C0 (his visit, sanctuary complete, no figure, +0xC4 & 8 clear) | (0x12, 0), +0x68 = Ares' figure, flags \|= 0x80 | 0x00533640: +0x42 = 800, +0x44 = 0 |
Actions (figure_monster_update 0x004C8760; on-enter `monster_on_action_enter` 0x0052F750):
- **14 patrol**: on-enter `0x00532F10`: `+0x36 += 1`, past 14 → 0x11; route freed; a land walker: `FUN_00532D80`:
  `building_find_first(rng15 % buildings_last + 1 + last building (+0x5E), flags 5: state 1, root record)` → dest =
  its road access; none: flag 1 clear → 0x11, set → the first from 0. The Kraken: `FUN_00532EB0`: dest = the sea exit
  (0x00902CE0) and +0x5E = 1, then the sea entry and 0, by turns. Tick `0x00533070`: FUN_0052F3D0 (the god's
  sanctuary of monster 1/2/7/8, class 7) gone → 0x11; flag 1: −1 a day (`+0x104` stamp), at 0 → 0x11; figure_move:
  arrived / lost → 14 again, blocked → route freed; then enemies (`FUN_004AC7C0`: monsters 1/10/16 ships —
  warships, else transports; land walkers g_enemy_units_alive − transports − warships > 0) → (15, 16).
  So with few buildings (a start past buildings_last) Cerberus leaves after one or two.
- **15 chase**: on-enter `0x00533220`: ships (1/10/16 with ships) or land soldiers: `FUN_004AC570` → the nearest by
  Chebyshev, the first of equals (ships: figures 0x40 / 0x3F (nationality +0x6E ≠ 8) in slot order, state 1, not
  dying / hidden / flag 0x10; land: the members of enemy companies 35..98 (in use, +0x42 = 0, +0x69 = 0) in order,
  state 1, not dying, not on a building tile or a 0x10000000 tile — hidden ones count) → target (+0x82), dest = its
  tile, +0x100 = 0, +0x34 = 0x10, route freed. None: flag 1 clear and no enemies of that kind (`local_4`: the ship
  test only when the ship branch was taken) → 0x11, else → 14. Tick: `figure_walk_then(speed, 0xF)` (arrived →
  +0x34 = 16, lost → 15) then `0x00533340`: sanctuary gone → 0x11; target gone / dying / hidden → (15, 0x11);
  ranged at Chebyshev 2..3 → dest = its tile, facing it, (28, 15); +0x100 += 1, past 14 at tile progress 0/1 with
  dest off the target's tile → dest = its tile, route freed; direction 9 → (15, 0x11); 10 → (0x1D, 0xF).
- **16**: on-enter `0x00533580`: figure_tile_contact with the target on its own tile, else `FUN_004D5330` (each of the
  8 neighbours' first figure, until action 5); the attack group (monster_anim_info case 0x10) for that tick; tick
  `0x005335E0` → (15, 16).
- **0x11 leave**: on-enter `0x00533600`: dest = home (+0x2C); `figure_walk_then(speed, 0)`: arrived → action 0
  (+0x34 = 0; on-enter 0 does nothing for class 7) → removed (state 2) the next tick; lost → removed.
- **0x12 follow** (`0x00533670`): +0x44 += 1; once it was ≥ 800 → land enemies ? (15, 16) : (0x13, 0x11). The leader
  gone / hidden / dying / in 0xB (his vanish) / not state 1 → removed. Route mode 3, speed = the leader's
  (figure_type_value col 8) + 1 when Chebyshev > 1; +0x100 += 1; figure_move: 8 or 9 → +0x100 = 0, route freed,
  dest = the leader's tile; 10 → removed; else at +0x100 ≥ 21: 0, dest = its own tile, route freed (so it stops at
  the next centre and re-aims). Its first call (the tick it is made) finds dest = its own tile: arrived at once.
- **0x13 wolves** (`0x005339E0` / `0x00533A80`): the first wolf (0x3B, state 1, not dying / hidden) in slot order,
  none → 0x11; follows its tile (re-routed when it moved); arrived → figure_tile_contact; it dies or lost → 0x11.
- **0x1D**: on-enter: dest = home + (rng15 % 15 − 8, rng15 % 15 − 8) if in the play area (`FUN_00530CD0`);
  `figure_walk_then(speed, 0xF)` (arrived → +0x34 = 15); flag 1: the day count, at 0 → 0x11.
- **6** (a good monster): after the walk, enemies → (15, 16). A hit (`0x00533FB0`) outside actions 0, 4, 5, 9, 12, 16,
  22, 23, 25..28 → (15, 16). figure_fight_end: the saved action, route freed (no on-enter).
- Killed (figure_hit `0x004D54D0`, the 0x44 branch): FUN_0052F3D0's sanctuary +0xC4 |= 8, +0xC8 = 0xC0;
  sanctuary_update (daily, cycle step 31) counts +0xC8 down and clears the bit at 0: no new guardian for 192 days.
- A guardian meets ships only through figure_tile_contact's monster rule: a class-7 monster fights the enemy
  transport / warship that is its target (+0x82), a class-8 one the fishing boat / trireme that is its target; the
  generic loop skips 0x19 / 0x39 / 0x3F / 0x40. A ship in action 5 does nothing (its handlers' case 5); figure_hit
  takes its hull (+0x128) with debris `collapse_debris_spawn(x, y, 0, 0, 4, 0)` (size 0: corners offset −1), sinks
  it at < 1.
- Movement (figure_move 0x004D1170 → figure_route_walk 0x004D7BD0): the speed phase advances every call; no route
  (route_id < 1): at dest → direction 8 with the progress kept, else figure_find_route (progress 15); per sub-step
  +1, past 14 a centre (15): the next route tile (none: 8; not passable: 9, route freed), progress 0; at 8 the tile
  changes (figure_change_tile: the contact). Route mode 3 = roads first (see "Rampage in detail").
Ours: `guardians.py` (`move` the sub-step walker, `route3`); spawned by `heroes.guardian(g, god, sanctuary, leader)`
from sim/gods (month.py Kraken / Cerberus, gifts.py Talos, figures.visit_start the Dragon with Ares as leader).
Not ported (TODO): the exe goes on with 0x00533340 / 0x005318B0's tests after a tile contact started a fight in the
same call (action 5), so a target at 2..3 could put the monster in 28 with +0x34 = 5; ours keeps the fight.
Check: `python3 tools/oracle_guardians.py` (run re/oracle/runs/1I-dragon, scenario re/oracle/scenarios/dragon.txt:
the working city's Ares visit, dumps every tick 410..1010): ours' 0x12 driven by Ares' tiles from the dumps — the
Dragon's 51 tiles, the tick of every tile change, +0x44 and the tile progress +0x39 in all 580 dumps equal.

### Animation lengths `0x00533B60`
Durations of attack/smash states are `2 × frames` of the monster's sprite group
(`0x005AF5F0(image)`; groups 0x4A01.. per monster), i.e. data from the sprite files —
**hypothesis**: needs the frame counts from `extracted/sprites` to be exact.

Open play (10-29, events.md): the open-play adventures schedule monster invasions and god quests (type 4,
`event_quest` `0x00482820`, needs a hero), so monsters and heroes are part of open play. `}Open Play Sandbox`: Zeus's
Golden Fleece quest (hero Theseus) in year +3..4, Maenads in year +11, Talos in year +20..21.

## Monster events (scenario event type 0x1A) — `monster_event_update` `0x00481430`
Event records 124 bytes at `0x009173F4` (sav rank 13), count `0x009173F0`; handler dispatched
monthly by `0x0046D380` (month start, every event without flag bit 0) and directly on a kill.
Fields used: +0x04 i16 monster slot k; +0x14 i16 year (relative to `0x00902928`), +0x03 u8 month;
+0x28 u32 flags (0x40 warn, 0x80 warned, 0x100 hero, 4 done); +0x2C i16 lead months; +0x30 i16
status; +0x32 u8; +0x36 u8 god id (written = hostile god of slot 0/1 or −1); +0x38/+0x3A/+0x3C
target categories → `fig+0x115..0x117`; +0x3E aggressiveness → `fig+0x7B` (copied by
`monster_spawn` `0x0052EEF0` and `0x005321F0`); +0x60 u8 "god-sent" message variant.
```
status 1 or 5: return
m = monster_of_slot(k); if m < 0: error
status 0: if not events_date_check: return
          message (normal or god-sent text group); monster_spawn_and_act(m, ev, 6, 7); status = 1
status 2 (monster killed): status = 5; victory message (text 0xCAD+m, Poseidon 12..15: 0xFA2..)
status 4 (warning countdown):
    left = ev.month + (ev.year - year + base_year)*12 - month + ev.lead
    left < 1  -> spawn (as status 0), status = 1
    left == lead (unless flag 0x80), 24, 12, 6, 1 (if lead larger) -> warning message
after a spawn: hero = monster_hero(m); if hero >= 0: hero_record[hero].needed(text)  # 0x004FA710
               if Apollo (record 3) available: send/spawn Apollo to fight it (0x004E8A30, 0x004E3280)
```
`monster_spawn` `0x0052EEF0(m, ev, tile)`: position = for slot 0..2 the scenario lair point
(`0x00902E08[k]`, `0x00902E14[k]`, fallback land entry `0x00902CB4/6`); other monsters: land
entry (via `route_tile_check`) or sea entry `0x00902CDC/E` for sea monsters; `figure_create(1,
0x44, x, y, 0, 1)`; for non-guardians copies the event bytes to `+0x115..0x117`, `+0x7B`;
`+0x0B = m`; record `+4 = fig`.

Monster death (walkers_update `0x004CC8C0`): a type-0x44 figure reaching state 2 without flag 0x80
and not a guardian → `0x004812F0` finds the active (status 1) type-0x1A event of that monster
→ status 2 → `0x00481430`; if none, `0x00481350` posts the generic "monster slain" message.

## Heroes
Hero records `0x00F0E4E8` (sav rank 124), 8 × 28 bytes:
| off | type | meaning |
|---|---|---|
| +0x00 | i32 | hero figure (validated by `0x004FAA00`) |
| +0x04 | i32 | Hero's Hall building (type 125 `0x7D`, hall `+0x12` = hero id, `0x004FA5D0`) |
| +0x08 | i32 | hero id |
| +0x0C | u8 | hero needed (set by `0x004FA710` when his monster appears) |
| +0x0D | u8[5] | requirement i met (`0x004FBAD0`) |
| +0x12 | u8 | all met and hall `+0x18` ≠ 0 |
| +0x14 | i32 | text id of the "needed" message |
| +0x18 | u8 | sent for |
| +0x19 | u8 | requirements already paid |
| +0x1A | u8 | "you may now call" announced |
Hall building: `+0x2A` = hero figure.

### Requirements table `0x0063B3D0`: 8 heroes × 5 × {type, v1..v5} (verified dump)
| hero | requirements |
|---|---|
| Achilles | (0,3200,18) (2,3,1,12,2,13) (3,1,9,8,−1,−1) (4,70) (0,1600,21) |
| Hercules | (5,89,−1) (6) (5,89,0) (7,1500) (0,3200,21) |
| Jason | (1,3,57) (2,2,2,13) (0,6400,25) (1,8,43,1) (0,1600,21) |
| Odysseus | (8,89) (9,80) (10,8,16) (0,3200,20) (0,1600,21) |
| Perseus | (3,1,8,7,11) (3,2,8,7,11) (11,3000,1) (0,1600,14) (0,2400,19) |
| Theseus | (12,4) (13,60) (14) (0,3200,11) (0,1600,21) |
| Atalanta | (3,1,4,−1,−1,−1) (18,1,207,80) (0,3200,3) (0,3200,9) (2,8,1,12,2,13) |
| Bellerophon | (1,15,43) (17,89) (11,10000,0) (0,2400,17,10) (0,2400,21) |

Evaluator `hero_requirement_met(i)` `0x004FBC20` (true at once if the hero is present, or `+0x18`/`+0x19` set):
| type | test (verified) | meaning (text 185:48..58, 116..131; hypothesis where noted) |
|---|---|---|
| 0 | stock(res) ≥ v1, res = v2 if v2 is a food in either list (`0x010DFDAC`/`0x010DFE40`) else v3 (when v3 ≠ 0); res 0x19 = sum of all foods | goods in storage (`0x0040F810`, hundredths); shown /100 (/400 for res 0x13) |
| 1 | v2 == 0x2B: horses `0x0040F780(0)` ≥ v1; v2 == 0x39: triremes `0x00FEB0B8` ≥ v1 | horses / triremes |
| 2 | Jason: `cnt[v2]` ≥ v1; Atalanta: cnt0+cnt1+cnt2 ≥ v1; else `cnt[v4]+cnt[v2]` ≥ v1; cnt = `0x00FEB538[]` | soldier companies (hypothesis: per company type) |
| 3 | v1 (1 or 2) of the gods v2..v5 that are in the scenario (`0x005871A0`) have a sanctuary with progress `0x0053ECA0 == 100` | finished sanctuary to a listed god |
| 4 | `0x00FEB544` ∈ {0x8E, 0x8F} | "No unrest" (hypothesis: city mood message id) |
| 5 | v2 == 0: city culture `0x0091EA78` (Poseidon `0x0091EA74`) > 89; else hall `+0x80` culture > 89 | excellent culture access |
| 6 | Zeus: `0x00FEB418` ≠ 0; Poseidon: `0x0056F270()` | won a pan-Hellenic game / working hippodrome |
| 7 | population `0x00FE6A7C` ≥ v1 | people in the city |
| 8 | `0x00FE6A68` > 89 | city-wide gymnasium access |
| 9 | `0x00FE6A70` > 79 | hypothesis: popularity/food |
| 10 | `0x007828B4+…+0x007828C0` (4 ints) ≥ v1 | hypothesis |
| 11 | treasury `0x00FE6A64` ≥ v1 | drachmas |
| 12 | `0x00FEAEDE` ≠ 0 and palace (type 0x75) within 5 of the hall (`0x004FBB20`) | hall near the palace |
| 13 | hall desirability `+0xCE` > 60 | good appeal around the hall |
| 14 | no path from the map entry/exit points to the hall (`0x0058DF40`) | hall protected by walls |
| 17 | `0x00FE9690` > 88 | hypothesis: excellent observatory/health coverage |
| 18 | building count `0x00782888[Zeus: v3 / Poseidon: v2]` ≠ 0 and `0x00FEAED2` > 0 | working stadium/museum with shows |
Values written in the table for types 5, 8, 13, 17 are not used (thresholds are immediates).

Monthly (month_tick 6, `0x00524860`): for each hero with `+0x0C` set and `+0x18` clear:
re-evaluate (`0x004FBAD0`); if all met and not announced → messages `0xEA+hero`, `0xF2`,
`+0x1A = 1`; if not all met → `+0x1A = 0`.

### Send for `hero_send_for` `0x004FC2B0` (ECX = record; caller `0x004FC270` = UI button)
```
queue_hero_arrival(hero)          # 0x004808D0: new scenario event type 0x27, +0x36 = hero,
                                  # +0x28 = 0x100, status 1, countdown +0x2E = rng15 % 3 + 1 months
rec+0x18 = 1
if rec+0x19 == 0 and 0x00665DF0 != 1:
    rec+0x19 = 1                  # pay once
    for each requirement:
      type 0  : remove v1 of the resolved resource (0x00489B90(res, v1, 3)); 0x19: take from
                each food in list order until v1 is paid
      type 1, v2 == 0x2B, v3 == 1: kill v1 horses from horse ranches (type 0x85; their figure
                slots and count byte +0xA8)
      type 11, v2 == 1: treasury -= v1; 0x00FEB1A8 += v1
```
Arrival (event 0x27 handler `0x00481A80`, monthly): countdown −1; at < 1: message, hero created at
the land entry (`0x00902CB4/6`) by `0x004FA4F0`: `figure_create(1, 0x45, x, y, 0, 1)`, action 6,
`building_id` = hall, hall `+0x2A` = figure, `+0x0B` = hero id; event flag 4, status 0.

### Hero behaviour (handler `0x004C8F50`, not decompiled; key helpers verified)
- Target search `0x004FCF90`: hero finds one of his two monsters (`0x004FCEE0`→`0x004FCA60`/`0x004FCA00`),
  sets `+0x72 = 6` if the target is a sea monster (1/10) or a god in water, combat target
  (`0x004E3280`), monster `+0x120 = hero`, action 10, `+0x36 = 0`.
- Combat `0x004FD2B0` (per tick): `+0x36 += 1`; when within Chebyshev < 4 of a monster, the
  monster is forced into action 0x17 (`0x00534060`, its other attackers of unit type 0/1
  released); a god into 0x58. In melee (hero action 5) the hero sets `+0x68 = 300` (monster)
  or 150 (god); each tick `+0x68 −= 1`; at < 1 the target gets action 4 (dies), `+0x36 = 0`.
  Re-paths every 16 ticks while chasing.
- No target / target gone (`0x004FD060`): go back to the hall (action 12/13) or, on a road
  (`grid_terrain & 0x40`), action 8.
- Hero stats: figure model row 69 (hp 300, attack 50, armor 10); +4 to col 4 and col 0x12
  when Athena's sanctuary (record 8, `0xEF5F78`) is finished (`0x004E1B20`) — same for
  rabble/hoplite/horseman (types 0x0B..0x0D); cols 3/4 capped at 19.

## Constants
| value | meaning | where |
|---|---|---|
| 10000 | rest days at aggressiveness 0 | `0x00532290` |
| 16 | days per month of rampage | `0x005304B0` (`<< 4`) |
| 30 + rng%30 | ticks between target scans while resting | `0x005304B0` |
| 12 | god engagement radius (Chebyshev) | `0x0052FBA0` |
| 2..5 | building search radius (Manhattan) when resting | `0x00530180` |
| 300 / 150 | hero duel ticks vs monster / god | `0x004FD2B0` |
| 4 | hero engage radius | `0x004FD2B0` |
| 1..3 months | hero travel time | `0x004808D0` |

## State touched
Figures (`+0x0B, +0x24/26, +0x2C/2E, +0x30/32, +0x36, +0x5E, +0x68, +0x72, +0x76, +0x7B, +0x82,
+0x92, +0x104, +0x108, +0x10C flags 0x10/0x80/0x100/0x200/0x4000/0x8000, +0x114, +0x115..0x117,
+0x120`), monster records `0x00FE43F0`, hero records `0x00F0E4E8`, scenario events, treasury,
storage, buildings destroyed. RNG: main generator (rest days, scan timer, category 10, hero
travel) and MSVC `rand()` `0x005CC7A2` (resting building-search radius).

## Track 1I reading (2026-10-29): monster actions, the hero handler, halls (verified unless "hyp")

### Monster: rest/roam terrain and the building attack
- `figure_set_action(f, a, next)` 0x004ABAF0 stores `next` in +0x34; the behaviour object's vtable[0] is
  `figure_walk_then` 0x004ABB60 (move; result 9 re-route, 10 lost → `lost_action`, 8 arrived → +0x34).
- Route mode (per-tick header): land monster **3** (open land: trees, rubble, roads; building tiles block except
  orchards 0x23/0x24/0xD9, avenues 0x76/0x7E, race track; walls 0xC000 block; sanctuary ground 0x10000000 blocked for
  0x44); a bad monster in action 7 (or flag 0x100, rampage 11) uses **mode 2**: `route_search` over grid_military,
  cost 1 + (building 10, wall 40, gate/tower 60, bridge 2), impassable −1 / −2 (water, cliffs, edge, burning
  ruins), traced 8-way (pathfinding.md section 5; ours `sim/military/routes.py`, oracle routes all equal:
  tools/oracle_route2.py). On an obstacle it
  stands (direction 11) and every `cycle_step & 3 == 0` tick (13 of 51) adds wall damage to the tile: building
  threshold 10 (+1), wall 200 (**+10 for a monster**), tower/gatehouse 400 (+1); past it
  `building_destroyed_by_attack` 0x004928C0. So an aggressiveness-0 monster still **bashes through every building
  and wall in its roaming area**.
- Roam centre +0x30/+0x32 = dest at **every** entry to 7 (from spawn: the lair). Home +0x2C/+0x2E = the spawn tile
  (changed only by on-enter 24 0x00534430). Arrived (dir 8): `FUN_005301E0(f,x,y,4)` (bad monsters): own tile, then
  rings 1..3 (top row, bottom row, left column, right column) → the first building/wall tile ≠ dest becomes dest;
  else at the roam centre → `FUN_00530AE0(−1,−1)`: dest = **home** + (rng15 % 15 − 8, rng15 % 15 − 8) (two main-RNG
  draws, −8..+6) if in the play area; else dest = roam centre. Route failure (9/10): the building search, else
  `FUN_00530AE0` around the current tile, snapped with `route_tile_check` (fallback roam centre).
- `monster_seek_building` 0x00530180: d = 2 + (crt_rand()·4 >> 15); `nearest_attackable_building` 0x004ABE80:
  smallest Manhattan distance to the building **origin** (b.x, b.y) ≤ d, ties to the lowest id; state 1 and the
  god-curse countdown 0x00EF60B0[type] == 0 (sav rank 126, all zero in normal play: not static data); composite
  (84..98 sanctuaries, 117 palace) and pyramid pieces only when started, not damaged and of a damageable class;
  100..114 never. Sea monsters: water under the origin or the far corner `tile + {0,229,458,687,916,1145}[size−1]`.
- 26 / 27: see "Monster actions as the exe" above (11-02: the second set_action(7, 7) draws a new rest timer; before,
  ours kept it).
- `building_destroyed_by_attack` 0x004928C0: no message, no fire; empty tile with a wall → 0x004DDCB0; sanctuary /
  pyramid piece → `monument_piece_damage` 0x005463D0 (damaged, not removed); anything else → rubble, state 4,
  collapse debris, parts destroyed; then the grids are rebuilt. 0x004DB3D0 (combat sound) draws `crt_rand()` every
  bash/attack tick (the same MSVC stream as the seek radius).

### Monster fights and death
- 9 (on-enter 0x00531000, tick 0x00531050): mode 3 to the target; target gone/dying/hidden → 6 (home) → 7; ranged
  (not Medusa/16) at Chebyshev 2..3 → 28; adjacent → `figure_tile_contact` → the **generic fight** (hit every 24
  ticks). Re-chase while within aggro rings of home, else 6. Victims: Hydra/Kraken devour, Medusa petrify (0x46),
  others killed (0x004DAB30).
- `figure_hit` with monsters (constant 0x005D9358 = 1.5): a bad-monster target has armor ×1.5 and hp 500 × 1.5 =
  750; a bad-monster attacker attack ×1.5 (×2 more vs a trireme); missile hits on a bad monster from 0xB / 0x27 /
  0x28 / 0x2E do **0** (towers shoot at monsters to no effect); a good monster hitting a monster does 0. Every hit
  calls 0x00533FB0: unless busy (actions 0,4,5,9,12,16,22,23,25..28) a bad monster turns on the attacker (→ 9).
- `figure_can_kill` 0x004D53D0: god only by a god; hero by a god, or by a monster that is not his quarry; monster by
  gods/heroes/monsters, a bad one also by 0xB/0xC/0xD/0x3D/0x27, a good one by 0x28..0x2A. The horseman charge
  0x004E1080 bypasses can_kill and the ×1.5.
- Ring search 0x0052FD30: own tile, then rings 1..aggro (ring r has 8r tiles, row-major dy outer; offsets built at
  run time 0x00495FB0/0x004A52F0, starts i16 0x005F07F4). Row 8 of the hostility table: unit types 1, 2, 4, 5, 6, 7, 9.
- Action 6 = `walk_then(spd, lost 24)`, arrival → +0x34 (7). Death: action 4 → state 2 → (not a guardian, no flag
  0x80) `monster_event_killed`; leaving via 17 counts as killed too (quirk).
- Gods and monsters (settled 11-03, bug 439): `figure_tile_contact` 0x004D4DA0 ends the whole contact when a god
  (0x43) and a monster (0x44) meet, either one the mover or the tile figure, unless the god passes `FUN_004D4910`:
  unit class 9 (friendly), record byte 0x00DBD793 = 3 (Apollo), `god_sanctuary_building` 0x004E8BF0 (record
  0x00EF5E74) > 0 and `god_sanctuary_active` 0x004E9440. Two gods (0x43 with 0x43) never start a tile fight (their
  duel is 0x3C), and a god in 0x56 / 0x57 / 0x0A / 0x0B is skipped. `figure_fight_start` 0x004D4BA0 has no other
  caller and `figure_hit` is called only by `figure_fight_tick` and the two missile handlers, and Ares' own handler
  (figure_god_handler 0x004C5D40) calls neither: so a visiting Ares (or Artemis, Zeus...) never fights a monster;
  only Apollo does (melee and bolts), plus the bolt-throwing gods sent by sim/gods/fight.py (Athena at invaders,
  Artemis at a wolf, the event defenders at a god). g_hostility (0x00639430, read from the exe: equal to
  units.HOSTILE) has 7 → 8 and 8 → 7 set, so a guardian and a bad monster do fight: the guardian's hits do 0
  (figure_hit) and `figure_can_kill` lets a monster kill a monster, so Talos killing Ares' Dragon is the exe's.
  Ours before 11-03: contact used the table alone, so in the user's Zeus-and-Europa ep. 4 Ares (25 a hit) and
  Artemis beat Talos to death after he killed the Dragon (`contact.god_monster_off`, test_god_meets_monster_only_apollo).
- Duel: the hero within Chebyshev < 4 → `monster_engage_hero` 0x00534060 → action 23 (0x00534150: follows the
  hero, contact fight). In melee 0x004D5BC0 replaces `figure_hit` for a hero and his quarry: **no damage either
  way**; the hero's +0x68 counts 300 → the monster gets flag 0x10, action 4.
  Settled 11-04 (TODO "Achilles fought the Maenad for minutes"): the duel is not a separate action, it is the shared
  fight (`figure_fight_start` 0x004D4BA0, action 5) whoever starts the contact: the hero arriving
  (hero_combat_update 0x004FD2B0 direction 8: face it, `FUN_004D5330` neighbour contact, on its tile
  `figure_tile_contact`) or the held monster's own 0x17 contact (0x00534150 → FUN_004D5330). `figure_hero_update`
  0x004C8F50's head, every tick of action 5: +0x82 (target) a monster and +0x68 == 0 → +0x68 = 300 (0x96 vs a god);
  hero_combat_update sets it too right after his own contact. `figure_fight_tick` 0x004D5F10 calls
  `hero_duel_hit` every fight tick before `figure_hit`: hero vs a monster that `hero_can_fight` 0x004FCD60 (his two
  quarry ids): facing it, the attack timer > 23 → the monster's hit sound (FUN_004DB7A0) and timer 0; +0x68 − 1;
  at ≤ 1 the monster flag 0x10, action 4, hero +0x82 = +0x68 = 0, FUN_004DAB30 (its death sound); returns 1 (no
  figure_hit). The monster side (its opponent a hero who can fight it): the hero's hit sound every 24, no damage.
  So the monster falls 299 ticks after the contact tick (the counter set there or on his first fight tick, then
  decremented from that tick); with +0x82 = 0 (no target) +0x68 stays 0 and she falls on his first fight tick; a
  partial count (a duel broken off) stays in +0x68, and action 7 counts it down before he leaves the hall.
  Walking (direction other than 8/9/10): +0x36 > 16 at a tile centre (progress 0 or > 14) with the target not in
  action 5 → re-routed to its tile; Chebyshev < 4 and the monster not yet (+0x82 = him, action 0x17) → engage; else
  +0x36 > 16 → `hero_find_target` 0x004FCF90 again (sets action 10, +0x36 = 0, dest, and frees the TARGET's route).
  Ours before 11-04: a separate act-5 duel only when the hero reached her; a contact she began was a plain melee
  with damage both ways (the user's Achilles fought for ~600 ticks until she died of damage). Ours now:
  sim/heroes/combat.py duel_tick (units.fight_tick → MYTH.duel_tick), fight_started (duel_end = anim_t0 + 1 +
  max(0, n − 2)), hero_ai.chase (test_hero_duel_either_side). Not ported: the hero vs a god (+0x68 = 150, the
  hero beaten home): ours' find_target never picks a god (not checked whether FUN_004FCEE0 can).

### Monster animation (`monster_anim_info` 0x00533B60)
(bug 386, 11-02) Heroes the same (figure_hero_update 0x004C9C86..0x004C9EAB): group by action (4 die, 5 fight, 0x13
swim when on deep water outside a bridge, else walk: hero_sprite_group 0x004FA860), the frame +0x01 +1 every tick
wrapped at the group's count (walking or standing), image = first + frame·8 + view dir; dying: min(timer +0x36,
frames−1) (not /2 as monsters). Play mode: roles' frame_rule "tick" (was the generic tick % 12 while moving).
Group g1 walk/idle (all other actions), g2 die (action 4), g3 attack (5, 12, 16, 25, 27), g4 special (28);
frames = the group's first image's `anim_frames` (sprite data); 8 directions (Kraken, Scylla death: 1).
Image = group first + frame·8 + dir, frame +1 every tick (also standing); dying frame = min(timer/2, frames−1).
Frames g1/g2/g3/g4: Hydra 15/21/20/20, Kraken 21/31/35/31, Cerberus 23/22/15/19, Cyclops 15/21/17/16, Minotaur
20/20/20/20, Medusa 17×4, Boar 12/13/16/16, Dragon 20/31/18/18, Talos 18/16/16/18, Hector 15/10/16/17, Scylla
20/31/30/31, Maenads 16/20/21/13, Sphinx 17/23/26/33, Chimera 15/21/25/19, Harpie 40/37/20/19, Echidna 19/24/20/18,
Satyr 16/20/16/18 (data/play/heroes.json, tools/play_heroes.py).

### Hero handler `figure_hero_update` 0x004C8F50 (disassembly; switch on action−4, table 0x004C9EB4)
| action | |
|---|---|
| 6 | hidden; +0x36 −1; ≤ 0 → 9 to the hall's road access |
| 7 | in the hall: hidden, healed, flag 0x10 cleared; if hall +0xC4 bit 4 (came home beaten): +0x68 = 800 (rest); else when +0x68 ≤ 0 and hall +0x18 (road access) → out at the road access, action 8 |
| 8 | patrol the roads (roam, budget +0x42 = 0xF00 units) → 9 home; **hero_find_target every tick** |
| 9 | walk to the hall road access → enter (7) |
| 10 | hero_combat_update |
| 12/13 | cross-country back to a road (13 → 8) |
| 14 | to the land exit (quest/expedition) → 16 (hidden there) |
| 15 | back from the expedition → hall (6 → 9 → 7) |
| 17 | hall gone: removed, sent_for = 0 |
- `hero_create` (from 0x004FA450) at the **map entry**, action 6, linked to the hall.
- `hero_find_target` 0x004FCF90: nearest live visible bad monster of his two ids (no radius), not claimed by another
  hero; else another aggressive monster within 16, a hostile god within 15, an invader 0x28..0x2A anywhere →
  action 10, the monster's +0x120 = hero.
- `hero_combat_update` 0x004FD2B0: re-path every 16 ticks; within Chebyshev < 4 engage (monster → 23, god → 0x58);
  melee timer 300 (monster) / 150 (god; **the hero loses** to a god: flag 0x10, home).
- Generic fights: a hero hits criminals and wolves for 9999 and takes nothing from them; beaten (damage > hp and
  can_kill) with a hall → not killed: flag 0x10, home, rest 800 ticks; without a hall he dies.
- `hero_return_to_hall` 0x004FD060: on a road → patrol (8, route mode 1); else road_tile_near_building(x, y, 1, r)
  0x004A39D0 with r = Chebyshev distance to the hall (squares radius 0..r, row-major, terrain & 0x44 == 0x40: no
  bridge, best of g_road_networks_top10 first) → 13 (mode 0) to it; none → 12 (mode 6) to the hall's road access
  (line move when the hall's +service_acc ≠ 0, else route_tile_check). Action 12 (0x004C948E) frees a lost route
  (direction 9/10) and searches again each tick. A lost route in hero_combat_update (direction 10) puts the hero on
  the target's tile (figure_place_on_tile 0x004E3220): the exe's own jump (bug 386 was ours: bridges blocked).

### Quests
A quest is answered from the army dispatch dialog (army_dialog_build 0x005BBB60 lists the present heroes of the
3 monster slots; 0x005BE0E0 → 0x0046DA70: **state 6**, countdown = travel months (< 1 → 12),
expedition_send_forces 0x004DEB30). Only the hero of slot +0x36 goes when the quest needs a hero (0x00469400): his
+0x132 = event, action 14 (to the land exit, hidden). event_quest state 7 → `expedition_forces_home` 0x004DEE60:
the hero comes back (action 15). Text 185:66 "away on a quest".
- (1I, 10-30) The open-play quest (sandbox event #0: Zeus, +0x04 item 0x1A "Hero" (23:26), +0x1C city 7 Thasus,
  +0x2C lead 2, +0x36 slot 0 = Theseus). event_travel_months 0x0046D950 for type 4: the event-type table 0x00632710
  row 4 says "has a city" (FUN_004681C0), so route_between(city, player) → route_travel_months (Thasus: 3); ours had 0
  (→ 12) and now takes the empire route (sim/heroes/events.py travel_months). State 6 ends when
  event_months_until_due (lead + date − today) < 1, then state 7 with countdown = travel months (−1 a month; at 0:
  message 0xDE, the hero home, the statue, state 10).
- Dialog for a quest (army_dialog_build / draw 0x005BC400 with type 4): +0x164 (companies and mythical warriors:
  listed, not toggleable, FUN_005BB900), +0x163 (allies: box and title not drawn) and +0x160 (navy: 283:17
  "Destination not accessible by sea") cleared; title 283:25 "Choose Forces for [god] Quest" ([god] = 157:god of
  +0x60); heroes toggle unless away (+0x132 ≥ 0: 283:16 "Abroad", 9DKYEL). Dispatch (0x005BDE70 → FUN_005BDAD0(0)):
  the quest needs a hero (0x1A among +6/+8/+0xA, FUN_004691E0); > 1 hero enlisted → 5:0xB5, its hero not in the
  city → 0xA5, its hero not enlisted → 0xA9 (each one OK popup); else army_dialog_dispatch at once (no confirm).
- **How the exe opens it for a quest (found 11-01):** the Goals screen's lit quest row (0x0052BC20, goal type 4):
  FUN_0052D240 returns the object 0x00FE2590 (vtable 0x005D97E0, +8 = 0x0052CF90: army_dialog_open(the goal's
  event)) when FUN_005BDDD0 (the quest's hero home and idle, if an item choice is 0x1A) and FUN_00471560 hold, else
  0x00FE2588 (vtable 0x005D9800: the screen's child window 0x0052D010 with the quest title and text; right click
  closes). Ours: campaign.js rowClick, lists.js questWindow. Earlier note: army_dialog_open 0x005BD950 has three callers: the world map's
  city request list (wm_sub_4642D0: events of that city with type 1 / 0x1E and item 0x18 only), the message
  window's action button (wm_sub_475AB0: item 0x18 only; the quest message 0xE0 is record 224, type 0, no buttons)
  and expedition_event_create (raid / conquer); no indirect reference to it (exe scan) and no other writer of the
  dialog's event index 0x01608BF0. Quests (state 0 open, or 0xB) are in the open-requests list 0x00916E10
  (request_list_rebuild 0x00483040, second loop), which the Overview advisor shows. Ours (play mode): the quest is
  listed with its city's requests on the world map (world.js; row "Hero: <god>") and opens the dialog there.

### Quest round trip (oracle 1I-quest, 10-30)
`re/oracle/scenarios/quest-trip.txt` = monster-hero.txt (Achilles' hall with the cheat, Send For) with
`tools/oracle_heroes.py --quest-poke`: the quest moved to Feb of year 0 with slot 2 (Achilles), and at tick 4284 the
dispatch emulated by pokes as army_dialog_dispatch leaves it (event state 6; Achilles +0x02 enlisted, +0x132 = 0,
action 14), since the dialog cannot be reached (above) and the sim is paused while the world map is open. Ours:
`tools/sim_monster_track.py --quest` (`dispatch achilles` at 4284). Read with `tools/oracle_heroes.py --quest`:
| tick | exe (raw = logical + 1) | ours |
|---|---|---|
| 1632 | quest active (state 0; the month change Feb → Mar runs the events with the old month) | same |
| 4284 | state 6, hero action 14 at (146, 190) | same |
| 4896 | state 7, countdown 3 (route months to Thasus), hero (184, 139) | same (was 12 before the travel fix) |
| 5304 | hero action 16 hidden at the exit (217, 106) | same |
| 5712 / 6528 | countdown 2 / 1 | same |
| 7344 | state 10, hero action 15 (217, 106) | same |
| 7548..8160 | walking home (212, 123) (195, 140) (178, 157) (161, 174) | the same tiles |
| 8364.. | patrol (8) by the hall | patrol (8), tiles ±2 (route choice) |

### Hero's Hall (type 125)
- Build menu 0x17 items (table 0x005F42C8): shown by 0x004FA620 when the hero belongs to one of the scenario's 3
  monster slots, is **needed** (+0x0C) and has no hall: one hall per hero, only once needed (cheat 0x00665DF0
  skips it). Off when the scenario disallows type 0x7D (0x00902D64).
- Size 4, **cost 0**, no employees, desirability 15/2/−2/6. Removal: record.hall = 0, the hero leaves (17);
  paid (+0x19) stays.
- +0x18 = road access (0x00484FE0: 100 when the access tile is a road): gates "all met", the hero leaving the hall
  and the window's warning. +0x80 culture (houses_culture_compute 0x00484DE0 counts type 0x7D), +0xCE desirability
  (step 38).
- Drawing: per-hero overlay (Zeus group + hero id; Atalanta/Bellerophon Poseidon) at (0x2B, −0x48); animates
  (set 0x2045) only while the hero's figure exists.
- Info window FUN_0057C720: title 185:8+h; status line (0x0057C630): 63 not worthy / 64 may now call / 65 travelling /
  66 away on a quest / 67 doing battle / 68 in the city / 69 resting / 70 abroad; no road → 69:4 / 185:123;
  "Requires" (59) / "Status" (60); 5 rows with tick/cross and the current value; "Send For" (62) when not present,
  not sent, all met → 0x004FC270 → hero_send_for; bottom: 185:+0x14 (the needed text).
- Requirement fields corrected: 5 (v2 = 0) = **city athletics coverage** 0x0091EA78 (Poseidon philosophy 0x0091EA74),
  label 51; 5 (v2 ≠ 0) hall culture +0x80 > 89; 8 = popularity (g_city_sentiment) > 89; 9 = city health > 79;
  10 = occupied elite houses (types 11..14) ≥ v1; 17 = tax coverage 0x00FE9690 > 88; 4 = 0x00FEB544 (city_crime_level
  0x00519910) ∈ {0x8E, 0x8F}: 0x8F no house with unrest ≥ 51; 0x8E fewer than 11 % of houses at ≥ 81 (and not more
  than half at 71..80).
- Messages: needed → `hero_needed_message` (+0x0C, +0x14 = 185 text: 71..86 monsters, 87..114 quests; phrases
  PHRASE_<hero>_hall_available_* 0x9FA + 6h, 6/7: 0xFAA/0xFB0); all met → ticker 19:234+hero "Your city is now
  worthy of X's presence" and 19:242; arrival phrases 0xA1E + 6h (6/7: 0xFB6/0xFBC).
- Panhellenic games (0x00565E30): Hercules' hall built, not sent for, type-6 unmet → chance = int(chance² × 0.16).

### Quest statues
`quest_statue_variant(god, quest, sel)`: sel 1 small, 2 large: quest 0 gods 0..11 → 10..21 / 22..33, Hera, Atlas →
34, 35 / 36, 37; quest 1 → 38..49 / 50..61, 62, 63 / 64, 65; sel 0 none. Grant 0x00402B00: one more placeable
commemorative of that variant (at most 10 waiting).

## Ours (sim/heroes, track 1I, 2026-10-29)
Module `sim/heroes/` (interface in its `__init__.py`; switch `heroes on|off`): `monsters.py` (figure 0x44),
`hero_ai.py` (figure 0x45), `heroes.py` (records, halls, requirements, Send For), `events.py` (handlers of scenario
types 4, 26, 0x27 registered with track 1G's `sim/scenario`), `combat.py` (the monster/hero rules in the shared fight
engine `sim/military/units.py`, via `units.MYTH`), `commands.py` (CLI + `/heroes` export). Data:
`data/heroes.json` from `re/venv/bin/python tools/build_heroes.py` (behaviour rows per difficulty, requirements
0x0063B3D0, target figure lists 0x00638C78, missile frames 0x006409F0, animation frames from the sprite atlases,
texts 185/190/19); figure rows 67..69 in `data/military.json` (tools/build_military.py); lairs = `World.monster_points`
(scenario block +0x4E0); Hero's Hall = building `heroes_hall` (tools/build_data.py role 125, misc["hero"]).
CLI: `heroes`, `monsters`, `monster SLOT|NAME [X Y] [aggr N] [lead N]`, `quest GOD [SLOT] [SEL]`, `hero NAME`,
`sendfor NAME`, `dispatch NAME` (the army dialog's quest dispatch), `heroes cheat` (0x00665DF0),
`build heroes_hall X Y HERO`.

| exe | ours |
|---|---|
| main RNG (rest days, scans, wander), MSVC rand (seek radius) | the module's own generator; an MSVC-rand clone seeded from it |
| route modes 0 / 2 / 3 / 6 | the hero: figure_hero_update sets +0x72 every tick: 6 while chasing (action 10), going back to a road / the hall (12, 13) or standing on water outside a bridge (0x0058B560: route & 0x3C or water / beach 0x10004 without a building; else route_distance), 0 otherwise (hero_ai._route, water_ok; bug 392: on deep water 0x4000000 he swims, action 0x13 look = g4 + the raft SprAmbient rank 87 as his extra picture, scene.js); mode 0 (hero_find_target / hero_return_to_hall): walkers.route0 over monsters.passable, 4-way search + trace8, <= 499 steps (10-29..11-02 an 8-way BFS, bug 386); bridges (road over water) are land for modes 0/3 (route grid 0x005876F0: road 0x04 before water); mode 2: Dijkstra over grid_military over the whole map (route_search's limit is 100000 pops; sim/military/invaders.grid, ramps open as 0x00502BA0); mode 3/0: 8-way BFS over open land incl. trees and ramps, whole map; a failed rest route wanders around the monster's tile snapped by route_tile_check 0x004D2C60 (`monsters.snap`); the hero's lost route puts him on the target tile (FUN_004E3220) as the exe |
| `building_destroyed_by_attack` on sanctuary / pyramid pieces (piece damaged) | as exe (10-29): composites are targeted per piece (`monsters.pieces`: class with vt+0x8C true, started (vt+0x9C), not damaged (vt+0x98); classes from the vtables, data/heroes.json `piece_attack` / `piece_collapse`, tools/build_heroes.py); `piece_damage` = monument_piece_damage 0x005463D0: vt+0x90 0x00556020 -> damaged + stage 0 (the temple front/back partner too; ours: the nearest one), 0x00536D00 (palace classes 3..6) -> the whole palace to rubble; root +0x64 0x200 -> progress recounted, rebuilt by artisans, extras again (sim/systems/monuments.py). grid_military per piece: not started 0, attackable 1, else -1 (`heroes.piece_grid`, sim/military/invaders.grid) |
| ring tile order (row-major per ring) | square rings, clockwise from north |
| guardian monsters (Kraken, Cerberus, Talos, Ares' Dragon) | as exe (11-02): sim/heroes/guardians.py ("Guardians" above): entries 0x15 / 0xE / 0x14 / 0x12, patrol 14, chase 15 / 16 (+28), leave 0x11, follow 0x12, wolves 0x13, 0x1D; killed -> `guardian_killed` with `guardian_days` 0xC0 counted down by sim/gods/sanct.py |
| god engagement (Apollo/Zeus), Athena's +4 | hooks for track 1H: `heroes.monsters_near(g, x, y, r)` (FUN_004F1B50), `monsters.god_engages` (a god walker with `target_fig`), `monsters.apollo_sent` (`sim.gods.send_against_monster` if present); 1H's Apollo/Athena fights are stubs |
| horseman charge bypassing can_kill | not separate (sim/military's charge is an ordinary hit) |
| hero hall culture +0x80 | the hall takes service coverage like a house (services.apply / decay) and `housing.culture` |
| hero patrol (figure_roam_tick budget 0xF00) | a roamer step to the least recently walked road neighbour, 256 tiles |
| Devour / petrify victims (Hydra, Kraken, Medusa) | monster_hit_victim 0x00532CF0 via sim/military/hooks.died (10-29): Hydra/Kraken: the victim dies with draw colour 0x7C00 (red, +0x168; `w.tint`); Medusa: the victim is removed at once and a 0x46 statue (fig_handler_turned_to_stone 0x004C9EF0: grey 0x6318, 10 000 ticks) kept as a record (`monsters.statues`, /heroes.json `statues`, with the victim's fight look and tick: the 0x46 figure copies the victim's picture +0x04). Play mode (10-30, bugs.md 247): the frames carry `tint` and `statues` (`heroes.frame`); the colour blit FUN_005B86A0 in gl.js (alpha >= 2), the statues drawn by heroes.js `statues` as walkers (walkerSpot). Not ported: action 12 (0x00532670, timed devour of the held target) and Hades' petrifying (0x43 god with resource 0xD) |
| Requirement type 1 paid (v3 == 1: horses leave the ranches), 18 (count[80] and the unique venue's shows) | as the exe (`take_horses`, `venue_shows`) |
Checked: `tests/test_heroes.py test_heroes_monsters` (lair, smash, hall, Send For, duel, the event's end, a quest
and its statue); oracle comparison in "Oracle check (1I)" below.
Play mode: `data/play/heroes.json` (tools/play_heroes.py: sprite blocks per monster/hero, the hall statue),
`viewer/play/heroes.js` (roles by good "m<id>"/"h<id>", atlases on demand from tools/play_atlas.py, the statue, the
hall window), `/heroes.json` (sim/live.py). 10-29: the hall window as the exe (0 px, "Hero summoned and dueling");
the hall's fire pot while the hero exists (city_draw case 0x7D -> 0x0045C580: SprAmbient rank 69 at the draw point +
(0x7D - ax, 0x3C - ay); oracle h_0900.bmp: the stand 98 % within 8, the flame differs by phase); fight sounds of
monsters and heroes (sound groups 0x15..0x1C heroes, 0x1D..0x2C monsters, FUN_005A5D00: atk1..4 / hit / die,
data/play/audio.json combat roles "monster:m<id>" / "hero:h<id>" from tools/play_audio.py, play.js fightSounds by the
walker's good). 10-30 (bugs.md 246..248): the monster's other sounds (audio.json combat rules.monster): atk1/atk2
(FUN_004DB3D0(f, 0) -> FUN_004DC2E0; never atk3/4, those are its missile calls) every tick it stands blocked
(direction 11, 0x004C8C72) and every tick of a rampage smash (action 25, 0x00532700; the rest smash 27 is silent), as
walkers.sfx "bash" with an end tick, looped by heroes.js while sound_play_sample refuses a playing sample; in melee
(action 5) at fight-animation frame 1 (0x004C8D22, play.js); the Kraken's slot 9 "appear" at its spawn (0x0052F726).
Minimap: a tile whose first figure is a god / monster / hero shows SPR_R_GOD / MONSTER / HERO (ui.js minimapFigures,
0x00454980). The devour tint and the statues are drawn (above). Hercules' games boost (FUN_00565E30): `games_chance`
(sim/systems/games.py begin): his hall built, not sent for, type 6 unmet, c != 0 -> ftol(c^2 x 0.16) (0.16 at
0x005E4800). Check: tools/heroes_check.mjs (statues / devoured / minimap pixels, dpr 1.25). Quest dispatch (10-30):
milpanel.js `openArmy(..., "quest", ..., quest)` draws the type-4 dialog and runs FUN_005BDAD0's checks, then
`dispatch HERO`; opened from the quest city's requests on the world map (ours: "Quests" below).

### Chase bound (fixed 10-29; 1H traced the full.txt drop to it)
Action 9 (0x00531050) chases in route mode 3 and gives up (6: home, then rest) when the target is gone, when the
route fails, or on reaching its old tile while Chebyshev(home +0x2C) >= aggro rings; a fight's end also leads to 6.
The roam centre is reset at every entry to 7 (dest), so after a chase it is the lair again. Before the fix ours chased
without the bound and rested where the victim fell, so the sandbox Maenads (year +11) walked down the ramps into the
city (full.txt 71/98 Townhouses); now they stay on their plateau (85/100, as without them). With the whole-map
routes (below) they roam as far as the exe's (up to ~30 tiles out of the gully) and still give up chases at the
bound: full.txt 85/100 (10-29).

### Oracle check (1I, 2026-10-29)
Run `re/oracle/scenarios/monster-lair.txt` (re/oracle/runs/monster-lair; Open Play Sandbox, camera and the Maenads
event poked to year 0 / January, dumps every 408 ticks, shots m_*.bmp). Ours: the same poke on a new sandbox
(`g.scenario.events[1]` year 0 month 0), dumps of the same ticks:
| tick | oracle | ours |
|---|---|---|
| 816 | event state 4 (warning) | state 4, message PHRASE_independent_maenads_invades (initial announcement) |
| 1632 | state 1, figure 0x44 id 11 at (121, 200), action 7, rest timer 18195 | state 1, monster 11 at (121, 200), act 7, rest 14699 (10000 + rng % 10000: other RNG) |
| 2040, 2448 | timer −8 per 408 ticks (a day each 51), dest (121, 200) / (120, 199) | timer −8 per 408 ticks, roaming within the plateau |
Shot m_580.bmp: the Maenad with her pink aura; play mode draws the same picture (zeus_maenads g1). The 19.5-year
run open-play-events: Maenads due at the change to Sep 989 BC, spawned at (121, 200), roaming (dest field +0x24/26)
around the lair: ours spawns at the change to Sep 989 BC too (a new sandbox, nothing built).
Not checked against the oracle: a hero (needs his hall and requirements, or the cheat key), the duel, bashing
buildings, quests (no oracle run with them yet); the Hero's Hall picture, statue and window.

### Hero summoned and dueling (oracle 1I-hero, 10-29)
`re/oracle/scenarios/monster-hero.txt` (cheat flag 0x00665DF0 = 1 poked, so the hall is buildable and Send For free;
the Maenads event at year 0 / January): Achilles' hall at logical (141, 188) with 3 road tiles, Send For between
ticks 204 and 306 (arrival event 0x27, countdown 3 months). Dumps every 102 ticks, ours `tools/sim_monster_track.py
--hero` (Send For at 250; positions raw = logical + 1):
| tick | exe (logical) | ours (raw) |
|---|---|---|
| 2448 | hero at the entry (166, 169), action 9 | (167, 170), action 6 (9 at its first act) |
| 2754 | (141, 186) action 10: the Maenads found before reaching the hall (hero_find_target in 9) | (142, 186) action 10 |
| 2856 / 2958 | (133, 178) / (127, 183) | (134, 178) / (129, 183) |
| 3162..3366 | hero and monster in melee (both action 5) | melee (hero 5, monster 0x17 with the fight look) |
| 3468 | monster dying (action 4): the 300-tick duel | the monster gone by 3570 |
| 3570..3774 | 12 -> 13 back to the road | 12 -> 13 |
| 3876.. | patrol (8) on the hall's road | patrol (8) from 3978 |
So arrival, search, duel length and the return match; the walk differs by a tile or two (route ties) and the duel
spot by where the Maenad roamed (RNG). The hero now spawns at the raw entry (logical + origin), as the oracle shows.
Hall window (hall.bmp, the third right click on the hall): 40 x 29 cells at (0, 0x2D) for type 0x7D (info window
setup: 0x00FFA170/74/78/7C), not the mouse rule; "<hero> Requires", unmet rows in font rank 4 (11C3, orange), met
in rank 5 (11CB), the companies row "3 Hoplite Companies or better" (64:v3, 8:0x31, 185:0x73), one god when the
requirement needs one ("A Sanctuary to Athena": the first listed god the scenario has friendly-jealous, value
"N% complete"), unrest value 61:(city_crime_level + 6) ("none"), the status text keeps its trailing space, Send For
= RIMS highlight 544 x 20 (0x0063B370) with an 11C label. Play mode now: **0 px** differ (tol 30) over the whole
640 x 464 window at dpr 1.25 (tools/screens_check.mjs + screens_compare.py, a copy save with the same hall). The hall
picture on the map (h_0100.bmp, camera cell (86, 318), tools/oracle_view_compare.py --box 210,180,480,345): 100 %
within 8.

### Logical vs raw coordinates (1I, 10-29, verified)
The exe's figure, building and scenario-point coordinates are **logical**: route_search, route_tile_check and the
grids index `base + 228 y + x` with base `0x00DA2F80` = scenario block +0x34 (+0x2C/+0x30 = W, H); the play-area
tests add `0x00DA2F90/94`. On the sandbox maps base = 229 (W = H = 226), so logical (x, y) = raw (x + 1, y + 1).
Our grids (World.flags etc., the play mode) are raw; the dump's terrain at raw index y*228+x equals ours (12 tiles
differ in 0x603). Proof: the exe Maenads' 66-step route (dump route table 0x00E7AEC8, route_id +0x3A) crosses rock
and cliff tiles when read raw, and only open land, trees and ramps (0x800600) when read logical. So the lairs are
converted (`heroes.origin`, `World.origin`): the sandbox Maenads live at raw (122, 201). Oracle positions printed by
tools/oracle_heroes.py are logical (+1, +1 for ours). Since 1J (10-29) every scenario point is converted once in
sim/world.py (World.points, entry/exit, sea entry, herds, fishing, monster points, invasion and landing points;
map-terrain.md "Logical and raw coordinates"); sim/heroes uses them as they are.

### Roaming and bashing (oracle 1I-roam, 1I-bash; 10-29)
`re/oracle/scenarios/monster-bash.txt` (as monster-lair, camera cell (70, 290)), dumps every 204 ticks:
- 1I-roam (the scenario's plots without roads, removed at tick ~400 by the no-road check, so the Maenads alone):
  resting (action 7, timer 10 2xx) the Maenad walks 66-tile mode-2 detours out of her gully (dest (112, 194) via
  (128, 181), (117, 172), (107, 181)) and back: the route has no length bound, and a failed route's wander tile is
  snapped to open land by route_tile_check. Ours before: route_search limited to 24 tiles and ramps blocked in
  grid_military, so the gully was a closed 219-tile pocket. Now ours finds the exe's 66-step route and makes the
  same detours (tools/sim_monster_track.py: (124, 171), (107, 185), (128, 183) ...).
- 1I-bash (the two plots kept by poking their no-road counters, tools/oracle_heroes.py --bash-poke): the Maenad
  spawns at tick 1632 and both plots (logical (120, 196), (122, 201), 2 and 4 Manhattan from the lair) are gone by
  tick 1836; ours (`--bash`): gone by 1683 / 1785 (10-29); 1683 / 1836 since the per-tick actions (11-02). Then she roams around the smashed plots (roam centre = the
  building's origin, as 26 -> 7 with flag 0x200).

## Open questions
- Hero handler `0x004C8F50` and the monster fight states 9/14/15/18/19/22/23 are only partly
  read (disassembly only). Damage itself is the generic combat code (`0x004D4DA0`, military).
- Exact animation frame counts (sprite data) drive smash/missile timing.
- Requirement types 4, 9, 10, 17 meanings (city record fields `0x00FE6A70`, `0x00FE9690`,
  `0x007828B4..C0`, `0x00FEB544`).
- `0x00665DF0 == 1` skips paying requirements (cheat or tutorial?).
- Monster 16 (Black Warrior): who spawns it.
- Status 4 warnings: which event flag selects the warning path (set at event creation).

## Cross-references
- Gods (parent religion doc): god records `0x00EF5DD8` — `+0x00==1` hostile (unit type 10),
  Apollo record 3 is sent against new monsters (`0x004E8A30`, `0x004E3280`), Apollo/Zeus god
  figures engage monsters (`0x0052FBA0`); per-type cooldown bytes `0x00EF60B0[221]` (decremented
  every month_advance call by `0x004E5EB0`) exclude building types from monster/god targeting.
- Hermes record 7: speed ×150/100 for figure types 0x13..0x15 and ×133/100 for cart types
  (`0x004E1B20`) — economy/walkers.
- `building_destroy` `0x004928C0` (map-buildings), `figure_create` `0x004D9FD0`, combat
  `0x004D4DA0`/`0x004E3280` (military), events `0x0046D380` (time-core).
