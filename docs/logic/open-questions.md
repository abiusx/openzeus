# Open questions (aggregated from docs/logic/*.md)

Generated from each doc's "Open" section. Wave 2 works through these.
1F sweep (10-30): every item carries a **1F:** status: answered (where), RE only (no sandbox effect found), Poseidon /
stage 2 (outside the Zeus sandbox), or open. Open with a possible sandbox effect: the storehouse partial-fill quirk
(storage-distribution.md). The rest of the open ones are RE only.

## buildings.md
- Exact role of `+0x20` (route distance vs. "has access" flag) for consumers. **1F:** RE only: ours uses road access + staffing for every destination test; no sandbox difference found.
- `0x00496CA0` per-type footprint/image placement is only skimmed (sub-parts of storehouse, **1F:** answered for every sandbox type with parts (dock, ranch, stadium, gatehouse, agora, storehouse bays; rotation.md, shore.py, ranch.py, stadium.py).
  dock, granary, agora, stadium); sub-part ids follow creation order there.
- Tool 25 (`0x0041BE40`) identity; type 119 "big" variant list `0x00665DB0`. **1F:** type 119 = god-statue commemoratives, answered (bugs.md 193); tool 25: RE only.
- `0x00B1E8BC` setter (no write found in the decompile: probably a scenario/cheat flag). **1F:** RE only: no writer, 0 in every oracle run (editor/cheat flag).
- Who writes `+0x1C`; confirm it is the house population (population-housing agent). **1F:** answered: house occupants (housing.md: types 2/3 need +0x1C > 0; ours b.occupants).

## desirability.md
- Exact rectangles returned by `0x0053CF30`, `0x0040C9B0`, `0x005B02E0` (not traced here). **1F:** answered for the sandbox types (desirability.md "Ours", bugs.md 266, 1F).
- Whether any map can have a building with orientation byte > 3 for docks. **1F:** RE only (no shipped map; ours 0..3).

## empire.md
A `.map` (each map of a `.pak`) carries the empire: block 25 = cities (476 B × 22 in version 247
maps), block 21 = prices (rank 8), block 17 = world objects (40 B × 200 in v247). On a new map
`city_init_from_map` `0x00511E30`:
1. `0x0042E1B0`: for every in-use city `0x0042E130`: `army = army_target(c)`, `+0xCA = +0xCB = 0`, **1F:** description, not a question (ported: sim/empire).
   `+0x175 = 0`, `gift_fatigue[] = request_fatigue[] = 0`, `+1 = 0`; distant → `relationship = 0`;
   colony with relationship 3 and `tribute_mode != 1` → `tribute_mode = 1`.
2. `trade_open = 1` for all 22 records. **1F:** description (ported).
3. Version fix-ups by file version `0x00F9D940`: < 302 `0x0050EDE0`; < 303 `0x0050F7E0` **1F:** description (ported: build_scenario / build_empire old-goods renumbering).
   (pre-Poseidon goods renumbering of `buys/sells/quota/used`, `+0xA8`, `+0xBC`, `+0xC4`,
   `+0xEC/+0xEE`, the price table and the city record's per-good arrays); < 313 `0x00510BE0`.
   Then player city `active = 1`, `flags &= ~4`.
4. Records of an older file are first zero-extended and converted by `0x0050C7E0` (converter **1F:** description (ported).
   list `0x0063C2A8`, applies to version < 302): bytes < 0xF0 unchanged; the two i32 per-good
   arrays are renumbered; old `+0x150,+0x154,+0x15C,+0x160` → `+0x160,+0x164,+0x16C,+0x170`;
   old bytes `+0x164/+0x165` → `+0x174/+0x175`; old `+0x1C8..+0x1D8` → `+0x1E8..+0x1F8`; old
   `+0x1D9`/`+0x1F9` (32 B each) → `+0x1F9`/`+0x219`.

Goods renumbering Zeus → Poseidon (`0x0050EF70` bytes, `0x0050EE00` i32; new ← old):
1..7 ← 1..7; 8 (oranges) ← none; 9..15 ← 8..14; 16, 17 (black marble, orichalc) ← none;
18..21 ← 15..18; 22 (chariot) ← none (new entries get 0). For the 28-entry arrays also
23..27 ← 19..23.

On a new adventure (`0x00420390`, case "first episode"): the player city gets `resources[0..19]`
from scenario `+0x7A8` and `quota[0..22]` from `+0x7C8`; `+0xBC/+0xC4[0..3]` from scenario
`+0x7BC`/`+0x7C2`; `+0xD8`, `+0xDC` and `+0x164` from `0x0042B790/780/7A0`; `+1 = 0` for all.
Next episodes keep the cities, prices and world objects across the map load.

### Open Play Sandbox (`Open Play Sandbox 2P.map`, v247, old good numbers)
| # | kind | rel (+0xD4) | route | buys (old #) | sells (old #) | tribute | att |
|---|---|---|---|---|---|---|---|
| 0 | 0 player | 1 | land | – | – | – | 50 |
| 1 | colony | 3 | land | 16 sculpture | 3 meat, 11 grapes, 13 fleece | mode 1: 16 × good 13 (fleece) | 100 |
| 2 | colony | 3 | sea | 3, 11 | 10 marble, 18 wine | mode 1: 1000 × good 19 (old drachmas) | 100 |
| 4 | foreign | 2 vassal | land | 15 armor | 7 wheat, 11, 12 olives | mode 1: 16 × wheat | 75 |
| 5, 6, 7, 8 | foreign | 0 ally | land/sea/land/land | 2 items | 2–3 items | none | 75 |
| 9, 10, 11 | foreign | 1 rival | sea/land/sea | 1–2 items | 2–3 items | claim (+0xE4) 500 / 250 / 750 | 75 |
| 12, 13 | distant | 0 | sea | 2 items | 2 items | none | 50 |
| 14, 15 | enchanted (5) | 0 | – | – | – | – | 0 |
Quotas are 12 except the listed goods, which have 24 or 36. `+0xCC` = 0 for Greek cities and
1..4 for the others (hypothesis: nationality, text group 37: 0 Greek, 1 Trojan, 2 Persian,
3 Centaur, 4 Amazon; 9 = Atlantean matches the Poseidon default of `0x0042CA10`).
(Decoded from `.map` block 25 with `refs/zeus-poseidon-arm64/tools/mapfile.py`; good numbers are
the old pre-Poseidon ones, e.g. 16 = sculpture, before `0x0050F7E0` renumbers them.)
The sandbox also has 16 scheduled events (types 23, 2, 1, 21, 4, 19). **Resolved 10-29 (events.md):** these are an
editor copy in the `.map`, never played; the played events and gods come from the `.pak` episode.

## finance.md
- Who sets `b+0x86` (the 110 % tax multiplier)? No direct write was found (maybe via memcpy or a **1F:** answered (1C): no writer, never x1.1.
  computed pointer).
- `b+0xDB` "blessed" flag (set by `0x004128C0` for buildings linked to types 63/64): which god or **1F:** answered (1C/1H): a blessed building (gods), x4 tax collection.
  effect.
- Is `taxes_projected` meant to be half the real tax (×2 missing)? **1F:** RE only: display value of the finance advisor (ours as the exe's formula).
- Event type 29/32 names. `0x0047EE20` (day 12) touches the treasury: request payments? **1F:** answered: 0x0047EE20 = spontaneous rival invasions (military.md); event names: stage 2.
- `0x00782F18` meaning (hippodrome). **1F:** Poseidon only (stage 3).

## heroes-monsters.md
- Hero handler `0x004C8F50` and the monster fight states 9/14/15/18/19/22/23 are only partly **1F:** answered for open play (1I: heroes-monsters.md "Roaming and bashing", oracle 1I-*).
  read (disassembly only). Damage itself is the generic combat code (`0x004D4DA0`, military).
- Exact animation frame counts (sprite data) drive smash/missile timing. **1F:** answered: frame counts from the sprite data (play mode, 1I).
- Requirement types 4, 9, 10, 17 meanings (city record fields `0x00FE6A70`, `0x00FE9690`, **1F:** open, stage 2: the sandbox quests use other types (Golden Fleece: Theseus' hall; heroes-monsters.md 529).
  `0x007828B4..C0`, `0x00FEB544`).
- `0x00665DF0 == 1` skips paying requirements (cheat or tutorial?). **1F:** RE only (0 in play).
- Monster 16 (Black Warrior): who spawns it. **1F:** not in the open-play episodes (stage 2).
- Status 4 warnings: which event flag selects the warning path (set at event creation). **1F:** stage 2 (no sandbox event uses it, events.md).

## housing-evolution.md
- Callers `0x00564560`, `0x00570B20`: when the check runs and how the result is applied **1F:** answered: 0x00564560 = status icons (services.md); evolution = houses_evolve 0x004FE290 (ported).
  (evolution timing, merging of small houses into 2x2, elite house building).
- Food resource list at `0x010DFDAC`: which goods count as food. **1F:** answered 10-30: the city food list 0x005BAAF0 (agora food order; not in the dumps).
- `0x00FFA0FC` meaning (reason 0x0B vs 0x0C). **1F:** RE only (info text reason).

## housing.md
- `0x00B1E8BC` (freezes evolution; hypothesis: map editor). `0x0091EA08` setter. **1F:** RE only (see buildings.md); 0x0091EA08 = route grid rebuild flag (pathfinding.md).
- Exact criteria of the city food list `0x005BAAF0` (economy). **1F:** answered 10-30 (ported, rebuild_goods_lists 0x005BAAF0).
- `b+0x03` value for common houses (2 expected): set from `0x005F6368[type*8]` at creation. **1F:** answered: the type table 0x005F6368 (buildings.md §2).

## labor.md
- `0x00569610` array (wage table?) and `0x00F2A988` = difficulty (hypothesis, set at game start). **1F:** answered: difficulty.md (verified), labor_pool_compute (bugs.md 103).
- `0x00FEB458` = count of type-0x0B figures in formations whose `-0x3F` byte is 0 (rabble?). **1F:** answered: rabble soldiers, 6 workers each off the labour pool (labor.md, military.md).
- Tower staffing condition globals `0x00FEAF24`, `0x00FEAEDE`, `0x00FEAEA0`, `0x00FE91E8` (palace?). **1F:** answered: tower switch 0x00FEAF24 (Manning button), 0x00FE91E8 palace exists (labor.md, military.md).
- Category 5 label "Science" in Poseidon (`0x00590920`) vs model category 8. **1F:** Poseidon only.

## map-terrain.md
- Scale of `0x004A8C90`/`0x004A8E10` (tree depth) and of the scrub tool value (`__ftol` paths). **1F:** RE only (editor tools).
- Exact meaning of 0x8000, 0x1000000, 0x80000000, `0x00CC1618`, `0x00C8E9D8`, `0x00B1E8F8`. **1F:** partly answered (0x10000000 sanctuary ground); the rest RE only, no sandbox reader found.
- Where the map ranks 18–32 (elevation etc.) are filled for GOG maps (terrain.md open item). **1F:** answered for our maps: the .map carries the grids, sim/world.py loads elevation and the rest (who fills them in the GOG maps: the editor, RE only).
- x87 precision-control state during `0x004A4900` (53 vs 64 bit) — confirm by a save diff. **1F:** open, RE only: no sandbox difference traced to it (ours Python float64).

## military.md
- Enemy targeting, siege of walls, and how an invasion ends (city sacked vs. army destroyed): the **1F:** answered 10-28/1B (military.md "Open questions": targeting, siege, end, wall HP).
  enemy movement AI `0x00500B70` was not decompiled by Ghidra. Use disassembly.
- What happens when the bribe is paid (handler of message 0xDD); meaning of event `+0x38` (→ group `+0x44`). **1F:** answered (military.md); event +0x38 beyond the class: stage 2.
- Request subtypes and `0x00FEB4F9`; full casualty tiers of `0x00461540`. **1F:** 0x00FEB4F9 answered (auto-defend mobilized, alarm.py); request subtypes: stage 2 (no requests in the open-play episodes).
- Who writes `Formation+0x82` (abroad)? Probably the distant-battle code. **1F:** answered (military.md, distant battles).
- Monster float paths in `figure_hit`; the piercing missile mode (`0x00777286`). **1F:** open (military.md); fights ported by 1I with the exe's x1.5 / missile rules.
- What `0x004C91EA` does (the only reset of `+0x98`). **1F:** open, RE only.
- Exact walker actions 3/6/7/9/0x10/0x11 (walkers subsystem). **1F:** answered 10-28 (military.md).
- `special_range` (col 12, `+0x144`): where it is used. **1F:** answered: cavalry special distance and the enemy archers' range (military.md).
- The charge formula uses the attacker's own armor, which looks like a bug. Kept as in the exe. **1F:** as original (kept).
- Wall HP and enemy siege behaviour were not traced. **1F:** answered (military.md, wall damage grid 0x00C753B8).

## monuments.md
- `root+0x64 & 0x100`: who sets it (no direct writer found by text search). It stops artisan **1F:** RE only (no writer found; 0 in every oracle run).
  assignment and cart requests (a "construction halted" toggle? hypothesis).
- `vt+0xE4` `0x005456F0` and the sibling-sharing code `0x00542900`/`0x00542670`: exact **1F:** answered (bugs.md 148: 0x00542900 one cart / 400 marble shared by 8 tiles).
  arithmetic not transcribed (needed for exact cart counts with 50-unit tiles).
- `pyramid_piece_ready` `0x00541690` and `pyramid_lift_request` `0x00534B50`: rules for which **1F:** pyramids: Poseidon / stage 2-3.
  pyramid piece may be worked at which height.
- The artisan handler `0x004C0060` (≈0xA60 bytes, not a Ghidra function): walking, action **1F:** answered (monuments.md, verified 10-28).
  numbers other than 4/6/7/8/9, random draws (it steps the RNG at `0x004C07FB`).
- Extras classes 1001–1005 `+0xE0` and Demeter's `0x0053CFA0`. **1F:** answered (bugs.md 214, monuments.md "Ours").
- `0x00543C30` (material shortage flag) and the sanctuary status texts 59:9…14. **1F:** answered (bugs.md 183, sanctuary window texts).
- Placement cost and creation of the piece records (map-buildings subsystem). **1F:** answered (monuments.md, sim/systems/monuments.py).

## pathfinding.md
- Who sets route bit 0x08 (masks include it; no writer found in the decompile). **1F:** RE only (no writer).
- `route_search` pop order (exact), `route_search_ship` and the trireme tracers: military agent. **1F:** answered (perf round 3: same pop order; 1B ship tracers).
- `0x004CC5A0(mode)`: which modes may enter terrain 0x10000000 building tiles. **1F:** open, RE only (ours: sanctuary ground 0x10000000 blocks building only).

## population.md
- `0x00FEB084` (blocks immigration when ≥ 4; zero needed for step 13/14) — hypothesis: enemy threat. **1F:** answered: g_enemy_units_alive (military.md).
- `0x00412DC0` object created with each immigrant; `fig+0x36` meaning. **1F:** RE only (immigrant's cart helper).
- Identity of `g_health` (`0x00FE6A70`) — consistent with health (plague odds, births) but not proven. **1F:** answered: city health (health advisor, 0x005246B0 messages, 1C).

## production.md
1. (answered, production.md "Animal movement (RE)") Sheep/goat readiness regrowth: +9 per month. Still open: what `0x004F94F0` checks (calf becoming bull), bull behaviour `0x004CAA60`, wolf hunting, boar action 0xB..0x16. **1F:** 1F: 0x004F94F0 (calf -> bull) needs bulls < staffed corrals 0xD8 (0x0091EB28, counted in step 21): corrals are Poseidon, so no bulls in Zeus (ours none); bull behaviour 0x004CAA60: stage 3; wolves: 1B; boar: walkers.boar_idle.
2. Who sets the farm timers `+0xA9/+0xAA/+0xAB` and `+0xAF` (irrigation/flood, Demeter?). **1F:** answered with 1H (gods: Demeter's blessing / help).
3. `0x00EF6163` (global stop) meaning; `0x004F19E0`. **1F:** answered: g_production_stop (gods, sim/gods/roles.py).
4. Fishing boat: whether the `+0x3C = 100` assignment happens at the fishing ground or at the wharf. **1F:** answered 10-28 (production.md: at the wharf).
5. Quarry `+0xA9` decrement and `+0x33` reset (probably the cart/miner handlers). **1F:** answered (1C marble quarry, open-questions table).
6. (answered 2026-10-29, production.md "Chariot workshop") Chariot workshop: horses are not consumed by production, no cart ships chariots, and the horse trainer fetches chariot + horse together.
7. Walker handlers (`0x004AE160`, `0x004AECF0`, `0x004B5F10`, `0x004BE260`, `0x004BF060`, **1F:** answered: read in the disassembly by the tracks (production.md, storage-distribution.md, services.md).
   `0x004C1310`, ...) are not functions in the Ghidra project; they should be created so they decompile.

## religion.md
- Exact effect of actions 0x3A (budget A), 0x43 (C: `FUN_004EFA50`) and the special kinds **1F:** answered (1H, religion.md).
  (+0x13C) — they run in the undecompiled handler `0x004C5D40`; budgets and order are verified,
  the per-tick effect (fire? collapse? killing walkers?) is not.
- `gift_active` (+0x30) has no static writer: the 3200 − carried remainder may never be delivered. **1F:** RE only: no writer, so the remainder is never delivered in the exe either (ours the same, religion.md).
- +0x04 (init 50) and +0x1C (0xC0) have no reader in the decompile. **1F:** RE only (no reader).
- Need tests: `FUN_00569310` (food), city+0x18, city+0x34/+0x38, city+0x18A4.. — fields owned by **1F:** answered by the population / economy ports (health, food).
  population/economy.
- `FUN_00504650(4|10, …)` (Artemis/Ares attacks): which invaders. **1F:** answered (1H: Artemis / Ares help).
- Scenario +0xDC (max sanctuaries) and `0x004E5F60` (placement limit) — hypothesis. **1F:** answered: sanctuaries_at_limit 0x004E5F60 = min(+0xDC, 4) (events.md).

## sentiment.md
- God records 10 and 12: which gods? The crime one matches Dionysus. Record 12's +3 % births **1F:** answered: 10 Dionysus, 12 Hera (religion.md).
  could be Hera or Aphrodite. This needs the record → god id mapping (religion).
- `0x00FE96E8`: compared to population for the "past hunger" text. Its meaning is unknown. **1F:** RE only (advisor text).
- Games victory trigger (`0x00565FC0`) was not traced. **1F:** answered (games.md / sim/systems/games.py, bugs.md 198, 260).
- `0x00F2A7B0`, `0x00F2A7C4`: gates for the change messages (UI or tutorial). **1F:** RE only (UI / tutorial gates).
- Does anything other than the evolve and crime code read `b+0xCC`? No other write was found. **1F:** RE only.

## services.md
1. Who sets `+0x70`? It is decayed in step 35 like the coverage counters, but no setter was found **1F:** RE only (no setter; decayed only).
   (perhaps a Poseidon-only or removed service).
2. (answered, services.md §3.1) Trainee arrival 0x00491EF0 sets `+0xA9 = 32` (set, not add).
3. (answered, services.md §3.1) Yes, trainees serve on their way (figure_move → figure_route_walk).
4. How the superintendent finds a burning building (target selection in 0x004AF930). **1F:** answered (services.md 4.1, verified).
5. (answered 10-28) `0x0091EC48` (fire spread direction) is written by `wind_direction_draw` 0x00484F10,
   once a year.
6. Plague effects beyond `+0x85`/countdown: what `+0xF8`, `+0x10C` (zeroed at infection) are. (Infection **1F:** RE only: +0xF8 / +0x10C are zeroed at creation and infection, no sandbox reader found.
   blocks immigration and rehousing, not evolution: services.md §5, answered 10-28.)
7. Meaning of figure type 0x26 in the exe (model: "Nobleman"). It is exempt from service **1F:** RE only (no building creates it in Zeus open play).
   dispatch, immune to muggers, and removes plagued walkers.
8. `+0x84` (clerk from a blessed tax office) consumer; `0x00FE91E8` (tax office spawn gate). **1F:** answered (1C taxes x4; 0x00FE91E8 = palace exists).
9. Fountain rule: is grid 0x00C9B4E8 really the desirability grid here (terrain.md says so)? Then **1F:** answered (map-terrain.md: 0x00C9B4E8 = desirability, verified).
   fountains in low-appeal areas spawn water bearers more slowly. (Ours since 10-28: the desirability at the
   fountain's tile, `world.des`; before, a field only houses set, so every fountain ran at half rate.)

## storage-distribution.md
- Handlers not decompiled (ask coordinator to define functions): cart pusher `0x004AE160`, **1F:** answered: read in the disassembly (storage-distribution.md, production.md).
  storehouseman `0x004B0080`, deliveryman `0x004B87C0`, also `0x004AE100`, `0x004ADBA0`.
- `Building+0x20` (i16, must be > 0 for every destination) and `+0x18`: meaning (workers present / **1F:** RE only (see buildings.md).
  labour access?) — population/labour subsystem.
- `Building+0x4A` (non-zero blocks storehouse_add_goods): fire/curse? `0x00902C0C` (blocks all **1F:** answered: burning (ours b.burning); 0x00902C0C = a cheat flag (housing.md), 0 in play.
  granary deliveries): scenario flag?
- `0x0048BFE0` last-resort destination of emptying storehousemen; `0x005B4780`. **1F:** answered (storage-distribution.md §7).
- `storage+0x7C` second limit array and `+0x09` flag; storage_create's caller (where `+0xD1` is set). **1F:** RE only.
- Deliveryman (fig 36) path to workshops and its unload; agora "get food" uses list 0x0091ED14 (distribution fork). **1F:** answered: agora buyers ported (1C; storage-distribution.md).
- Whether the `storehouse_add_goods` partial-fill returning 0 really loses goods (units stored but cart keeps full amount → duplication). **1F:** open (1F): ours never splits a load over a full bay; the exe's partial store returning 0 (duplication) is not copied. Low impact (only when the last bay fills mid-load).

## time-core.md
- `0x004AA6D0` (months 2 and 11) and `0x004AA640` (every day): which seasonal rule. **1F:** answered: orchards_rot_unpicked; 0x004AA640 = tree tend decay (production.md, ported).
- `0x00519590`, `0x00519910`, `0x005247A0`, `0x00524860`: most likely UI/messages; check that they write no sim state. **1F:** RE only (UI / messages).
- `fast_forward` `0x00F2AA9C`: which key sets it. **1F:** RE only (UI).
- `city+0x3C` population history: is it the source of the population graph only? **1F:** answered: the population graph (advisors, sim history).
- Event types 29–39: confirm the names (Poseidon editor text group?). **1F:** stage 2.

## trade.md
- `city+0x0C`: never set non-zero in zeus.c; maybe dead. **1F:** RE only (dead field).
- Bay `+0xD1` storage slot: `import_ok` is called with a bay as `B`, so it reads the bay's slot; **1F:** RE only.
  whether bays share the post's slot needs the economy agent's storage creation (`0x00494960`).
- `0x00FE94E0[g]`: meaning (stockpile?) to be confirmed by economy. **1F:** answered: the per-good stockpile flag (storage-distribution.md, ours stockpiled()).
- `B+0x44` values (1 = road access tile valid?) and `0x004A3B40` semantics. **1F:** RE only.
- God record 7 identity. **1F:** answered (religion.md god record list).

## walkers.md
- Exact meaning of `owner` (+0x0F, from building +0x01), `+0x0C`, `hidden` (+0x65), `+0x5C`. **1F:** RE only.
- Per-type spawn thresholds and initial actions for all other buildings (services agent). **1F:** answered by the service / production ports (services.md, production.md).
- `b+0x18` (incremented by houses served, capped 300; set to 0/100 by `0x005B0590` in cycle step **1F:** RE only.
  12): what reads it besides the spawn status `b+0xD3`.
- The 41 handlers are not decompiled (Ghidra did not create functions at table targets); only **1F:** answered: read in the disassembly per handler (walkers.md and the tracks).
  their callees and stores were read by disassembly. Making them functions in Ghidra would help.
- Who sets `0x007CBDC8` (tile-list deletion check). **1F:** RE only.
- Flags +0x14 of the type table (two bytes) and text id +0x10: confirm their use. **1F:** RE only.


## Sim constants vs the exe (sweep 2026-10-28)
Numeric rules in sim/ checked against Zeus.exe (TODO "Bulk cross-check"). Method: grep sim/ for numbers with
no exe address nearby, then read the exe function. "Fixed" = the sim now uses the exe value (commit).

**Fixed 10-28**
| rule | was | exe | address | commit |
|---|---|---|---|---|
| producer carts | 2 out, dispatched daily in building-id order | 1 per slot, waits at the producer, searches every 31 ticks | 0x0048CFB0, 0x004AE160 | ff50b4b |
| watchman | floor 0, any house | inhabited houses, clamp [col15, 100] | 0x004A5F70 | a12c00f |
| emigrants | to the exit, most occupants first | to the entry, lowest level first, 4 per house | 0x004ACD50, 0x00486AB0 | 6c142af |
| yearly births/deaths | none | 6/4/3/2/1/0/-1..-5 % by health, Hera +3 | 0x00566D40 | 3d2d1ed |
| taxes | float sum | integer per class (common, elite) | 0x00488250 | d5cde83 |
| tax sentiment | nearest level | row 0 when tax coverage < 11 % | 0x00567120 | d5cde83 |
| food sentiment | Python round (half to even) | trunc, then round half away when remainder > n/2 | 0x00566F20 | d5cde83 |
| fountain half rate | `b.desirability` (0 for fountains: always half) | desirability at its tile < 30 | 0x0048CFB0 | d4c7c18 |
| clerk | any house | inhabited houses | 0x004A67C0 | d4c7c18 |
| fire search | +15 per step always | +1 per tick only while something burns, >= 20 | 0x004CD450 | d4c7c18 |
| route limits | 30 (herder), 120 (fire run), 200 (boats), 600 (ships) | no radius; tracer fails past 499 steps (`walkers.ROUTE_MAX`) | 0x0058BC80, 0x0058DCE0 | d4c7c18 |
| animal waits | placed: 71/30/51..153 then 20..69 rolls | placed grazer walks at once; 71 (grazer) / 30 (horse) after each walk, then the 1/8, 1/4 rolls | 0x004BC380, 0x004F8770, 0x004BA080 | d4c7c18 |
| animal breeding | 0 < count | 1 < count | 0x004F8E30 | d4c7c18 |
| workshop input caps | sculpture 500, wharf 400, chariot 300 | 400, 300, 400 | stock_cap in 0x0048A880 | d4c7c18 |
| spawn intervals | hunt, corral, growers' lodge every n days | every n+1 (`> n` / test before increment) | 0x0048CFB0, 0x004F9960, 0x004AB210 | 2f73130 |
| peddler goods target | elite x4 | need x4 (size > 1) x2 (elite) x2: common x8, elite x16 | 0x0040D160 | 3e2250c |
| migration | every pass, 4 per house, empty first then most room | cooldown 2 passes on a direction flip, dues < 4 accumulate, passes A/B/C | 0x00567450, 0x00486860 | 7c1d435 |
| workshop output | buffered up to 800 | no output stock: progress waits until the cart leaves | 0x0048CFB0 | 584e6e2 |

**Fixed 10-29 (track 1C, the stage plan 1C)**
| rule | was | exe | address |
|---|---|---|---|
| growers | radius 12, path cap 40; pickers up to 4/3/2/1 minus pickers out; tender round only trees with tend <= 80, cheapest tend first | no radius or cutoff; nothing unless growers out < 4/3/2/1; a nearer picker takes over a claimed ripe tree (old grower to its next tree); tender only when no grower is out, up to 4 unripe trees by distance + tend/2, visited by building id; they leave at once (the (k*5+15)*2 timer is never read) | 0x004AB210, 0x004AA8A0, 0x004AAC20, 0x004AECF0 |
| corral ranchers | up to 2 cows within 16 tiles, path cap 40, any readiness, leave at once | 1 cow, readiness >= 100, nearest by route, no radius; waits 30 ticks; walks onto the cow's tile, re-routing without limit | 0x004F9960, 0x004F9630, 0x004CBB00 |
| timber mill | counter reset every 5 days | reset only when cutters are short and the map has trees | 0x0048CFB0 case 0x33 |
| gatherers' room | sent while room (minus carried) >= one load, ladder count | count capped by `(cap - stock) / 25` (stonecutters `ceil(room / 100)`) | 0x0048CFB0 |
| marble quarry | stonecutter every 16 days when empty; generic carts | period trunc(100.0 / pct * 16.0) paces one cart at a time; stonecutter when a cart leaves 300 or the stock is 0 (u8 idle counter > period / 8, never reset) | 0x0048CFB0 case 0x31 / 0xD5, 0x004DA250 |
| fishery | boat progress kept without a water exit | reset to 0 | 0x0048CFB0 case 0x2C |
| mint | pays the day progress reaches 100 | progress capped at 100, pays the next day (silver still > 199) | 0x0048CFB0 case 0x30 |
| horse ranch | monthly at the next month's start: all excess and all unfed horses go; breeds when the new month is even | daily: one excess horse a day; day 15: no wheat -> at most 2 leave, else the first unfed one; breeds in even months (Jan = 0) | 0x0048CFB0 case 0x85 |
| agora stall buyers | food room min(800, 1100 - carried - agora food); every day past the delay; horse trainer: 4 horses from any ranch | food: per food while carried < 800, room 1100 - carried - agora food, <= 8 loads; goods/horses room 400 - stock - carried, <= 4 loads; ranches within 40; a buyer only on days with day % 4 == the vendor's call count % 4 | 0x004CE9B0, 0x004CED40, 0x004CEB40, 0x0040A4C0 |
| standalone vendors | restocked 400 units from storage | nothing: vendor_update needs a parent agora, the chariot vendor 0xD7 has no step-31 case | 0x0040A4C0, 0x0048CFB0 |
| peddler | every house; empty house as its level | inhabited or elite houses; an empty one gets 10 x2 of fleece and oil; goods want = the next level's need | 0x0040D160 |
| homeless | walk to the exit once nothing has room | look again every 31 ticks on the way out | 0x004AD090 action 9 |
| herd refill | our ring of 16 offsets | table 0x005F2518 (8 west-ish offsets, then the point x8), start rng & 15 (map start: member k); refill boar restlessness 1800 | 0x004DF570, 0x004E0160 |
| risk | no climate; beach and vacant elite lots collapse | arid (+3 fire for non-houses, spread every 4 days; climate 0 on every shipped map); beach tile or house type 9: damage 0; maintenance repairs wall damage 50 per tile | 0x00492260, 0x00493140, 0x004A5D90 |
| taxes | no blessing | a blessed office's collector marks houses: x4 once (needs gods); b+0x86 (x1.1) has no writer: never | 0x004A67C0, 0x00488250 |
| tax / wage | any integer 0..25 / 0..60 | slider levels 0,3,7,9,11,15,20 / 0,20,26,30,34,40, nearest (ties lower); old saves snapped | 0x00641F50, 0x00641F38, 0x005697F0 |
| thief / vandal | roam budget 0x900/0xF00 of the superintendent's; vandal with no target turns mugger | no budget (they route to the target); a vandal with no target is removed and the house sends a new mugger | 0x005C0030, 0x005C02C0 |
| placement level test | "ground is not level" for every footprint and monument | none (map_area_buildable's param 6 is passed only by terrain drawing; sanctuary test 0x0053D9A0 has none) | 0x004A0DC0, 0x0053D9A0 |
| health messages | none | text 19:147.. down / 19:157.. up when the tens digit changes (301+ people; below 20 every step down) | 0x005246B0 |

**Fixed 10-30 (sim leftovers, the stage plan 1C "Left by 1C")**
| rule | was | exe | address |
|---|---|---|---|
| agora goods buyer | one storage, then home | up to 3 storages: after a visit, while visits < 3 and 400 - agora stock - carried >= 100, the nearest storage within 40 tiles holding any; nothing carried at a storage -> removed | 0x004CE300, 0x0040E2A0, 0x004CE2D0 |
| agora food order | the storage's foods, most first | the first 5 of the city food list (goods order urchin .. oranges; listed if an existing city sells it or a storage holds it): a 6th food is never bought. Ours since 10-30: exe bug fixed (every listed food; data/fixes.json agora_all_foods, bugs.md 297) | 0x0040D840, 0x005BAAF0 |
| timber cart | any day with stock >= 100 | only on the days the mill's counter passes 4, before the cutters | 0x0048CFB0 case 0x33 |
| gatherer start | walks at once | waits in action 6: woodcutter rng_15 % 30 ticks (counted down), miner / stonecutter rng & 31 counted up past 10 | 0x0048CFB0, 0x004BF060, 0x004C1310 |
| quarry period | trunc(1600 / pct) | x 66 / 100 with Atlas's sanctuary active (god record 13) | 0x0048CFB0 case 0x31 |
| blessed quarry / mint | quarry cart x4 from a 100 stock draw; mint 100 | quarry cart 400 drawn from the stock (may go below 0); mint pays 400 | 0x0048CFB0 cases 0x31, 0x30 |
| growers' list ties | (key, building id) | linked-list insertion from a cursor at the last inserted node (forward: before the first key >= new; backward: after the first key <= new), trees scanned in id order (economy.exe_sorted) | 0x004AA8A0, 0x004AAC20, FUN_004AB9A0 |
| request list ties | stable | CRT qsort: up to 8 items its shortsort (the first of the largest to the end; scenario.qsort) | 0x005CC22F |
| grower claim | freed when the grower ends its trip | freed only by a ripe pick, a finished tend or a nearer picker; a picker at a tree no longer ripe keeps it, the claim names a dead figure (remaining route 0): the tree is skipped until the id is reused (ours: after 1999 newer walkers, hypothesis) | 0x004AB080, 0x004AB6F0, 0x004AA8A0 |

**Matches the exe (checked)**: risk 50 per tile (superintendent, watchman), fire 25-tile search radius,
burning 32/16/33, spread every 8 days 1/4 downwind, mugger pause 20, homeless wait 52, urchin +100 cap 500,
trade staffing > 49 %, city_sells treasury >= -1999, demand levels 25/13, workshop rate pct/10 to 320,
trireme wharf 10/8/6/4/2 to 320, mint 200 silver -> 100 dr, orchard growth 0/8/19 by tend, tend 160, herd
ladder 1/4/8/16/32, fishery boat > 199, corral 15/15/600/+200, herder delay (k*5+15)*2, grower tender
ladder, ranch feeding (even months, wheat 50, (h+1)*food*6), peddler food caps (2*occ / 80, batch occ/2 / 20,
top 12/6), agora food < 1000, goods 300/200, storages within 40, producer stock caps, hunter search 1000.

**Differs, not changed yet** (gameplay impact, highest first)
- (resolved 2026-10-29, bugs.md 179) Chariot workshop: rate ladder 10/8/6/4/2 and output held in +0xDC up to 400. Ours now does the same: chariots stay in the workshop with no cart.
- (done, 1F check 10-30) Grazer destinations need tile regrowth >= 50 (0x004F83E0): walkers.py (animal_pick_dest,
  g.grass_bare / meadow_regrowth); boar restlessness (+0x5C, 0x0056B5D0): walkers.boar_idle.
- (done, 1F check 10-30) Sentiment: the military component (0x00566E70): sim/military/alarm.py (mobilized companies).
- Maps without herd/fishing points: generated points (wild.py fallback) are ours (allowed: not the sandbox, which
  has its own).
- (1F 10-30) Desirability was simplified (unfinished sanctuaries, rectangle counter, rubble, clamp order, water
  +10): fixed as the exe, bugs.md 266.
