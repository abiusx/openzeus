# Trade: traders, trade ships, trading posts and docks

Status: **verified** from the exe unless marked. Addresses refer to GOG `Zeus.exe`.
World-city record (`city+0xNN`) and empire data: see [empire.md](empire.md) and
`re/structs/trade-empire.tsv` (struct `WorldCity`, 572 = 0x23C bytes, `g_cities[22]` at `0x008FBAC0`).
Goods are numbered 1..22 (text group 23: 1 urchin … 7 wheat, 8 oranges, 9 wood, 10 bronze,
11 marble, 12 grapes, 13 olives, 14 fleece, 15 horses, 16 black marble, 17 orichalc, 18 armor,
19 sculpture, 20 olive oil, 21 wine, 22 chariot; 23 = drachmas).

## Summary
Every partner city that trades with you has a **buys** list and a **sells** list and one yearly
**quota** byte per good. Each 51-tick cycle (step 32) the city may send one trader: a caravan
(merchant + 2 donkeys) by land or a trade ship by sea. A trader walks to *the* trading post
(or dock) that was built for its city, then every 11 ticks tries to take **one export load**
(you sell: a good the post exports and the city buys) and **one import load** (you buy: a good
the post imports and the city sells). Each load is 100 units (a sculpture = 400 units = 1 piece),
costs/earns `price[good]` drachmas (one price per good, same for buying and selling), and
consumes one unit of the city's yearly quota for that good. A caravan carries at most 8 loads
each way, a ship 12. When both attempts fail in the same round it leaves. Quotas reset every
January.

There is **no route-opening cost** in Zeus (hypothesis: no treasury debit is tied to the
`trade_open` flag `city+0x05`; it is set to 1 for every city at map start and only changed by
city events — see empire.md).

## Data
| What | Where | Notes |
|---|---|---|
| prices | `g_trade_price[36]` i32 at `0x0065B9B0` (sav rank 8; `.map` block 21) | one price per good per load; changed only by price events (below) |
| city buys g (player may export) | `city+0x18[g]` u8 flag | derived from `city+0xBC[4]` list, see empire.md |
| city sells g (player may import) | `city+0x3C[g]` u8 flag | derived from `city+0xC4[4]` list |
| yearly quota | `city+0x60[g]` u8 | 12 / 24 / 36 in shipped maps (editor "None/Low/Med/High"; default 12) |
| loads traded this year | `city+0x84[g]` u8 | both directions share it; reset yearly (`0x00461460`) |
| sea route | `city+0x10` u8 | 1 = trade ships, 0 = caravans |
| trader countdown | `city+0x0A` i16 | in cycles (51 ticks) |
| unknown gate | `city+0x0C` i16 | must be 0 to spawn; only ever written 0 (on trader removal) |
| trader slots | `city+0x12/+0x14/+0x16` i16 | figure ids of live traders (≤ 3) |
| trade building's city | `Building+0x12` (i16, same slot as `house_level`) | for types 0x3C dock / 0x3E trading post |
| per-good trade order of a post/dock | `storage[slot]+0xC4[g]` u8 (`0x009215BC + 268*slot + g`) | 5 import on, 6 import off, 7 export on, 8 export off, 9 not tradeable |
| per-good amount limit | `storage[slot]+0x2C[g]` i16 (`0x0092152C`) | see ledger check |
| cursors | `storage+0x2E` (import), `+0x2F` (import, 2nd loop), `+0x30` (export); ships use global `0x00FEAEEC` in the dock search | values 1..22, pre-incremented with wrap 22→1 |
| trader ledger | `g_trade_ledgers[100]` × 88 B at `0x008F9860` (sav rank 69), next index `0x008F9858` (rank 70) | assigned at `figure_create` (`0x005B9DF0`, ring of 100); figure `+0x7F` = ledger index |
| dock count / list | `0x00782CEC` (≤ 10) / i16[10] at `0x00FEAEB8` | filled by `buildings_count_by_type` |
| entry/exit points | land entry `0x00902CB4/6`, land exit `0x00902CB8/A`, sea entry & exit `0x00902CDC/E` (i16; −1 = none) | scenario data |
| trade disruption | sea `0x00FEAED8`, land `0x00FEAEDA` (i16, in cycles) | set by `0x005B8DC0(kind, n)`: kind 2 both, 1 land, 0 sea (callers are god code `0x004EAD00`, `0x004EC090/180/6A0`) |
| finance stats | exports income `0x00FE96BC`, import cost `0x00FE96C4` (city record +0x2C64/+0x2C6C) | owned by finance |

Ledger record (88 B): `+0` i32 export loads, `+4` i32 import loads, `+8` u8[≤35] exported
loads per good, `+0x2C` u8[] imported loads per good, `+0x50` i32 export value, `+0x54` i32
import value (`0x005B9E90` export, `0x005B9E40` import: count++, per-good++, value += price[g]).

Load unit: `unit(g) = 400 if g == 19 (sculpture) else 100` (written `(-(g != 0x13) & -300) + 400`).

## How goods get into a post / dock (exports)
Full detail: [storage-distribution.md](storage-distribution.md) §8. **verified**
- Producer carts treat an exporting post (trade_state[g] == 7, stock < limit[g], staffed ≥ 50 %)
  exactly like a storehouse bay: one pooled list, nearest by route, after workshops, before
  granaries. No priority either way.
- The post sends its own storehousemen (fig 9, up to 4, step 31, `0x005B5620`) to fetch an
  export good from the nearest storehouse/granary/non-exporting post that holds it (not from a
  storage on Get), while stock < limit[g] and the good is not stockpiled.
- Storehouses on Empty may unload into an exporting post. Importing posts (5/6) push their stock
  out the same way to workshops/storages.
- Limits: the post's `limit[g]` (default 6000 = full), the stockpile flag `0x00FE94E0[g]`, a
  source on Get; then the trader-side quota/ledger. No city reserve: storehouses are drained.

## Spawning traders — `cities_trade_update` `0x005B9EE0` (cycle step 32, every 51 ticks)
```
trade_sea_partners (0x00FEAED4, i16) = 0 ; trade_land_partners (0x00FEAED6) = 0
sea_ended = land_ended = False
if sea_block (0xFEAED8) < 1: sea_block = 0  else: sea_block -= 1; sea_ended = (sea_block == 0)
if land_block(0xFEAEDA) < 1: land_block = 0 else: land_block -= 1; land_ended = (land_block == 0)
if sea_ended or land_ended: post message 0xE0 (text ids 0xC9B.. both, 0xCA1.. sea, 0xCA7.. land)

for c in 0..21:
    if !city.in_use or !is_trading_partner(c): continue          # 0x0042C9F0, empire.md
    if city.sea_route == 1:
        if dock_count < 1 or (sea_entry_x == -1 and sea_entry_y == -1): continue
        trade_sea_partners += 1
    else:
        trade_land_partners += 1
    n = 0; s = 0
    for g in 1..22:
        if (city.buys[g] and city.quota[g] != 0) or (city.sells[g] and city.quota[g] != 0):
            n += 1; q = city.quota[g]
            s += 3 if q >= 25 else 2 if q >= 13 else 1 if q >= 1 else 0
    if n > 1: s = ceil(s / n)            # integer: s/n, +1 if remainder
    if s <= 0 or city+0x0C != 0: continue
    # first free trader slot among the first s slots
    slot = first i in 0..s-1 with city.trader[i] == 0, else continue (no free slot)
    if city.countdown > 0: city.countdown -= 1; continue
    t = 30 if city.sea_route == 1 else 4
    if god_sanctuary_finished(god record 7 at 0x00EF5F44): t = t*66/100     # -> 19 / 2
    city.countdown = t
    if city.sea_route == 1:
        if dock_count > 0 and sea entry set and sea_block == 0 and (b = trade_building_of_city(c)) != 0:
            f = figure_create(1, 0x14 ship, sea_entry_x, sea_entry_y, 0, 1); if f == 0: return
            f+0x74 = 0; f+0x6F = 0; f+0x6E = c; f+0x5E = b; f.action = 6; f+0x36 = 10
            city.trader[slot] = f; f+0x7A = 0
            return                     # at most ONE new trader per pass; later cities wait
    else if land_block == 0 and (b = trade_building_of_city(c)) != 0:
        f = figure_create(1, 0x13 merchant, land_entry_x, land_entry_y, 0, 1); if f == 0: return
        city.trader[slot] = f; f+0x6E = c; f.action = 6; f+0x5E = b; f+0x36 = 10
        d1 = figure_create(1, 0x15 donkey, land_entry...); if 0: return; d1.action = 6; d1+0x68 = f
        d2 = figure_create(1, 0x15 donkey, land_entry...); if 0: return; d2.action = 6; d2+0x68 = d1
        return
```
Verified details: the countdown is reset even when nothing spawns (no trade building, route
disrupted); the countdown is only decremented when a slot is free; the `return` after a spawn
means cities with a higher index are not processed (their countdown is not decremented) in that
pass. `trade_building_of_city(c)` `0x005B95C0`: the first building id 1..`buildings_last`
with state 1 or 3, type 0x3E or 0x3C, and `+0x12 == c` (it does not check the route kind).
God record 7 is **probably Hermes** (hypothesis: the trade-speed bonus matches Hermes' manual
description; record→god mapping not yet read).

When a trader/ship/donkey (types 0x13/0x14/0x15) is removed (`0x004DA250`):
`city[f+0x6E]+0x0C = 0` and the slot holding `f` is cleared.

## Partner and good predicates
- `city_buys(c, g)` `0x005B92E0` (player may export g): `is_trading_partner(c)` and `0 ≤ g ≤ 22`
  and `quota[g] > used[g]` and `buys[g] != 0` and `0x00FE94E0[g] == 0` (i32 per good in the
  city record; economy owns it — hypothesis: the "stockpile" flag).
- `city_sells(c, g)` `0x005B9930` (player may import g): treasury `0x00FE6A64 ≥ −1999` and
  `0 ≤ g ≤ 22` and `sells[g] != 0` and `used[g] < quota[g]`. (No partner test.)
- `staffed(B)` (inlined in `0x005B9610`, `0x005B9990`, `0x005B8F90`): if `B.type == 0x3D` (dock
  house): `P = B.parent_part (+0x38)`; fails if `P.workers (+0x40) == 0`, else
  `pct = need(P.type)*100 / P.workers` (**inverted ratio, as in the exe**); else: fails if
  `B+0xDA != 0`; `need = model col 5 (employees)`; fails if `need < 1`; `pct = B.workers*100/need`.
  Requires `pct ≥ 50`.
- `ledger_full(B, f, g, mode)` `0x005B8E00`: `B' = 0x0049B920(B)`; if `B'.type == 0x3C` (dock)
  `B' = B'.next_part`. If `B'.type ∈ {0x3D, 0x3E}`: `n = ledger[f+0x7F].imported[g]` if
  `mode == 7` else `.exported[g]`; returns 0 (not full) iff `n*unit(g) < storage[B'.slot].limit[g]`.
  Any other type returns 1.
- `import_ok(f, B, g, c)` `0x005B8EE0`: `order[g] != 6` and `!storage_find_goods(B, 0, g)` and
  `!storage_find_goods(B, unit(g), g)` and `!ledger_full(B, f, g, 7)` and `city_sells(c, g)`.
  (`storage_find_goods` is the economy agent's storage query.)

### What the post's per-good number caps (confirmed 2026-10-29)
The number on the post (`limit[g]`, panel arrows) applies **per trader visit**. It does not cap the city total.
`trade_ledger_full` 0x005B8E00 compares the visiting trader's own ledger (`loads[g] * unit(g)`, imported at
ledger +0x2C for mode 7, exported at +0x08 for mode 5) with `limit[g]`. `trade_ledger_alloc` 0x005B9DF0 gives
each new trader figure a zeroed ledger (a ring of 100). So each caravan or ship brings, or takes, up to the
number. The post's storeman then pushes imports out to storage (§8.1 of storage-distribution.md), and the next
trader may bring as much again. Imports also need the post's own stock + one load ≤ limit
(`storage_cannot_accept`). Over time the partner's yearly quota (`used[g] < quota[g]`) is the only cap. The
user confirmed this from playing the original: each trader brings or takes exactly the amount set on the post,
and the total is capped only by the partner's yearly amount. Ours: `trade._ledger_ok` (the trader's
`w.load["ledger_in"/"ledger_out"]`); test `test_trade_limit_per_visit`.

### Goods a post never trades
Horses (15) and chariots (22): `storage_goods_list` 0x005B12C0 leaves them out of the trade window for
0x3D/0x3E. Their trade state stays 9 (`storage_create` 0x00494960), so they can never be ordered for import or
export, although `city_sells` and `city_buys` accept 0..22 and a partner may list them (the entry does
nothing). Pre-Poseidon maps give chariots price 0 (`0x0050EE00`). Ours: `trade.NOT_TRADED`; `trade X Y chariot
...` is refused (bugs.md 179).

## Trading-post choice on arrival — `0x005B8F90(f, x, y, c, 0)` (merchant)
```
(side tables at 0x01607DDC/0x01607D4C are filled for g=1..22 with city_buys / city_sells,
 zeroed when f+0x6F > 7 / f+0x74 > 7; only the import count n_imp is used)
B = f+0x5E
fail if B.state != 1 or B+0x44 == 0 or B.road_distance(+0x20) < 1 or !staffed(B)
fail if !can_import(f, B, c) and !can_export(f, B, c)
k = #{g in 1..22 : import_ok(f, B, g, c)}
N = 15 if B.type in {0x3D,0x3E} else 8
bay = B
repeat N times:                                   # cursor side effects only
    bay = bay.next_part (+0x3A)
    if n_imp and k and storage[B.slot]+0x09 == 0:
        up to 22 times: storage.cursor_imp(+0x2E) = wrap(cursor+1); stop when import_ok(f, bay, cursor, c)
if B+0x44 == 1: target = B.road_access (+0x26,+0x28)  else target = 0x004A3B40(B.x, B.y, 4 if type in {0x3D,0x3E} else 3), fail if 0
return B
```
The merchant then walks to `(B+0x26, B+0x28)` (it always uses the road-access tile).
Ships use `0x005BA3A0` (same structure, see below).

## can_export `0x005B9610(f, B, c)` / can_import `0x005B9990(f, B, c)`
```
can_export: staffed(B) else 0
    merchant (0x13): B.type ∈ {0x3E,0x3D} and f+0x6F ≤ 7 ; ship: B.type == 0x3D and f+0x6F ≤ 11
    N = 15/8 ; bay = B
    for i in 0..N-1:
        bay = bay.next_part
        if bay > 0 and bay.amount(+0x3C) ≥ 1 and city_buys(c, bay.good(+0x12))
           and order[bay.good] != 8 and !ledger_full(bay, f, bay.good, 5)
           and total_in_post(B, bay.good) ≥ (400 if i == 19 else 100):     # sic: i, not the good -> always 100
            return 1
    return 0
can_import: staffed(B) else 0
    merchant: B.type ∈ {0x3E,0x3D} and f+0x74 (i16) ≤ 7 ; ship: B.type == 0x3D and f+0x74 ≤ 11
    k = #{g in 1..22 : import_ok(f, B, g, c)} ; if k == 0: return 0
    if !import_ok(f, B, cursor_imp, c):
        up to 22 times: cursor_imp = wrap(cursor_imp+1); stop at the first import_ok ; none -> return 0
    for i in 0..N-1: bay = bay.next_part
        if bay > 0 and bay.amount ≤ 399 and (bay.amount == 0 or import_ok(f, bay, bay.good, c)): return 1
    return 0
```
`total_in_post(B, g)` `0x0048AFA0`: sum of `amount` over the N bays whose good is g.

## One export load — `0x005B9810(B, c)` (player sells to the city)
```
if B.type ∉ {0x3E,0x3D} or B.state != 1: return 0
repeat 23 times:
    cur = storage.cursor_exp(+0x30) = wrap(cursor_exp + 1)          # wrap: >22 -> 1
    if order[cur] == 7 and city_buys(c, cur) and total_in_post(B, cur) ≥ unit(cur):
        storage_select(B, cur, unit(cur))           # removes the load (economy)
        treasury += price[cur] ; exports_income += price[cur]
        return cur
return 0
```

## One import load — `0x005B9BD0(B, c)` (player buys from the city)
```
if B.type ∉ {0x3E,0x3D} or B.state != 1: return 0
tries = 1
while not (order[cursor_imp] == 5 and city_sells(c, cursor_imp)):
    cursor_imp = wrap(cursor_imp+1); tries += 1; if tries > 22: return 0
g = cursor_imp ; cursor_imp = wrap(cursor_imp+1)
if storage_add(B, g, unit(g)) (0x004895B0) == unit(g): pay(g); return g
# second chance, separate cursor storage+0x2F
repeat 22 times:
    cursor2 = wrap(cursor2+1)
    if order[cursor2] == 5 and city_sells(c, cursor2):
        g = cursor2; cursor2 = wrap(cursor2+1)
        if storage_add(B, g, unit(g)) == unit(g): pay(g); return g
return 0
pay(g) 0x005B9DA0: treasury -= price[g]; import_cost += price[g]
```
Quirk (verified): `storage_add` adds unit by unit into bays and is **not rolled back** when it
cannot take the full load; the partial load is kept and not paid. In practice `import_ok` has
already required room.

## Merchant figure (type 0x13) — handler `0x004B49B0` (table `0x0063969C`, not in zeus.c)
Per tick: `f+0x65 = 0`, `f+0x72 = 3`, animation counter `f+0x01 = (f+0x01+1) % 12`, `f+0x180 = 0`.
```
action 6 (waiting at the land entry):
    f+0x36 += 1
    if f+0x36 > 20:
        B = 0x005B8F90(f, f.x, f.y, f+0x6E, 0)
        if B: f+0x5E = B; action = 7; f+0x36 = 0; dest = (B+0x26, B+0x28)
        else: action = 9; f+0x36 = 0; dest = land exit (0x902CB8, 0x902CBA)
    else: f+0x65 = 1 (hidden)
action 7 (walking to the post): r = figure_move (0x004D1170)
    r == 8 arrived -> action 8 ; r == 9 -> 0x004D8990(f,1) ;
    r == 10 -> f+0x154 += 1, if ≥ 100: state = 2, f+0x65 = 1 ; other r -> f+0x154 = 0
    then if dest building state != 1 or its workers (parent's for 0x3D) == 0:
        0x004D8990(f,1); action = 6; f+0x36 = 20          # re-search next tick
action 8 (trading):
    f+0x36 += 1 ; if f+0x36 > 10:
        f+0x36 = 0; fails = 0
        if can_export(f, B, c) and (g = export_one(B, c)): city.used[g] += 1; ledger_export(f, g); f+0x6F += 1
        else fails = 1
        if can_import(f, B, c) and (g = import_one(B, c)): city.used[g] += 1; ledger_import(f, g); f+0x74 += 1
        else fails += 1
        if fails == 2: action = 9; f+0x36 = 0; dest = land exit
action 9 (leaving): move; 8 -> state = 2 (removed); 9 -> reroute; 10 -> state = 2
actions 4, 5: generic handlers 0x004D60B0 / 0x004D5F10 (walkers agent)
```
So a caravan trades at most one load each way per 11 ticks, ≤ 8 loads each way per visit.
Donkeys (0x15, handler `0x004B5750`) follow `+0x68` (walkers agent).

## Trade ship (type 0x14) — handler `0x004B4F60`
Same skeleton with these differences (verified):
- Target is the **dock house** (`dock.next_part`, type 0x3D); per-visit cap 12 loads each way
  (`f+0x6F ≤ 11`, `f+0x74 ≤ 11`).
- Action 6 (wait > 20): `0x005BA3A0(f, x, y, c, 0)`: needs `dock_count ≥ 1`; advances the global
  cursor `0x00FEAEEC` once (wrap 22→1); dock house state 1, dock workers ≠ 0, can_import or
  can_export on the dock house; same cursor loop as the merchant but with `0x00FEAEEC`;
  berth tile from dock orientation `+0xAC`: 0 → (x+1, y−1), 1 → (x+3, y+1), 2 → (x+1, y+3),
  else (x−1, y+1). Found → action 7, dest = berth. Not found → action 11, dest = sea exit.
- Action 8: after a successful export, if `dock+0xE0 == 0` it sets `dock+0xEC = 0, dock+0xE0 = 2`;
  after an import `dock+0xE0 = 1` likewise (dock animation). When both fail: `dock+0xE0 = 0`,
  action 11, dest = sea exit. Wait/round timing identical (> 10).
- Action 7 result 10 (lost): removed, and the first time (`0x00FD3784 == 0`) a message 0xE0
  (texts 0xB46–0xB48) is posted, `0x00FD3784` += 1.
- Action 11: arrived → removed (`state = 2`).
- At the top of each tick, if `dock+0xB6 == f` it re-derives the berth (`0x004A3FD0`) and clears
  `dock+0xB6` when the ship's destination differs (berth reservation).

## Trading-post order defaults — `0x00570A40`
When the info panel of a post/dock (`0x00FFA158`) is opened, every good whose order is 9 becomes
6 (import off) if the post's city sells it (`0x00460BB0`) and quota ≠ 0, or 8 (export off) if
the city buys it (`0x00460B80`) and quota ≠ 0. Toggle `0x005B18D0(B, g, old)`: 5↔6, 7↔8,
other → 9, re-storing the post's goods around the change.

## Price events (scheduled events, `month_events_dispatch` cases 0x0F / 0x10)
- `0x00472B20` price rise: `price[g] += amount` (event `+4` good, `+0xC` amount).
- `0x00472D00` price drop: only if `price[g] > 0`: `price[g] = price[g] − amount` if
  `amount < price[g]`, else `price[g] = 2`.
Both post message 0xE3. Initial prices come from the map (block 21 = rank 8); pre-Poseidon maps
are remapped by `0x0050EE00` (new goods 8, 16, 17, 22 get price 0; see empire.md).

Sandbox example (`Open Play Sandbox 2P.map`, old numbering → new): urchin 36, fish 36, meat 45,
cheese 45, carrots 40, onions 40, wheat 30, wood 75, bronze 110, marble 84, grapes 42, olives 38,
fleece 60, horses 0, armor 200, sculpture 640, oil 145, wine 160.

## When it runs
- Spawning: cycle step 32 (`simulation_cycle_step` case 0x20), once per 51 ticks.
- Traders: every tick in `walkers_update`.
- Yearly quota reset: `month_advance` year roll-over → `0x00461460`: for every in-use city,
  bytes `+0x85..+0x9A` (used[1..22]) = 0.

## Cross-references
- `storage_select` `0x00488xxx`, `storage_find_goods`, `storage_goods_take/give`,
  `0x004895B0` storage_add, `0x0048AFA0`, `0x0049B920`, storage record layout: economy.
- `figure_create` `0x004D9FD0`, `figure_move` `0x004D1170`, `0x004D8990`, `0x004E1B20`,
  donkeys: walkers.
- `0x004A3B40`, `0x004A3FD0` tile helpers: map-buildings.
- Finance counters `0x00FE96BC`/`0x00FE96C4`: time-core-finance.

## Open questions
- `city+0x0C`: never set non-zero in zeus.c; maybe dead.
- Bay `+0xD1` storage slot: `import_ok` is called with a bay as `B`, so it reads the bay's slot;
  whether bays share the post's slot needs the economy agent's storage creation (`0x00494960`).
- `0x00FE94E0[g]` = `g_stockpile` (per-good stockpile toggle; blocks workshop/granary delivery,
  post fetchers and `city_buys`) — resolved, see storage-distribution.md §8.3.
- `B+0x44` values (1 = road access tile valid?) and `0x004A3B40` semantics.
- God record 7 identity.

## Build menu and placement (decoded 10-28, bugs.md 94)
- The Trade build submenu (id 11) has no fixed list: item n is the n-th other tradeable city
  (`0x005F34BC[n] - 1` -> `city_nth_other` 0x005B9350), shown when `FUN_005B9410`: trade on (`0x00902D44`), the
  city exists, it has no trade building yet (`trade_building_of_city`) and it buys or sells something with a
  quota (`city_trades_nothing` 0x005B93A0). Label "%s: %s" (format at 0x0065B838) = building name + city name
  (`trade_building_label` 0x005B9480; Poseidon swaps the names 0x49/0x88 for 0xD7/0xA4). Picking an item sets
  the tool to `trade_building_type_for_city` 0x005B9460 (sea route -> 0x3C dock, else 0x3E trading post) and
  `0x00665DB0` = that city, which the new building is bound to. Play mode: sim/live.py `/trade.json`, ui.js.
- Trading post 0x3E: size 4, the generic `map_area_buildable` (buildings.md §7). Dock 0x3C: see below.

## Dock placement, footprint and berth (decoded 10-28, bugs.md 131)
In game text the dock is the **Pier** (Trade submenu "Pier: Miletos", 19:30 "You may only have 10 active Piers").
It is two buildings: the **pier** 0x3C (type table size 2; holds the workers, `Building+0xAC` = orientation) half over
water, and the **dock house** 0x3D (`pier.next_part`, `parent_part` back), a 4x4 storage like the trading post (root
tile + 15 bays) on land behind it; ships trade with the dock house (`0x005BA3A0`).
- Commit (`build_commit` 0x00498910): `g_dock_count` (`0x00782CEC`) > 9 → 19:30; `FUN_00453450` ≠ 0 → 19:23 "Find a
  good site along the water"; `building_water_access_check` 0x00485670 (a water tile of the size-3 edge ring
  `g_adjacent_ring[3]` around the pier anchor reachable by ship from the sea entry, `0x0058D500`) fails → 19:25 "This
  lake has no access to the sea". Preview (`FUN_004964B0` case 0x3C) runs `FUN_00453450` only.
- `FUN_00453450`: `FUN_004A10C0(x, y, 1, 0)`, the 2x2 half-water test of production.md "Shore buildings" (first fitting
  orientation 0..3), then, if that passed, `FUN_004534D0`: the dock house 4x4 at the pier anchor + offset by orientation
  (stack table, view 0): **o0 (−1, +2), o1 (−4, −1), o2 (−1, −4), o3 (+2, −1)**, i.e. centred on the pier, on its land
  side; tile list `0x005F5AC8 + 0x90·(view/2)` (`0x005F599C` = 16 tiles; view 0: the 4x4 from the anchor). Each tile:
  no building, `terrain & 0x3DFED66F` = 0, beach all-in or all-out and only if the tool allows beach (the dock doesn't:
  `build_tool_allows_beach` 0x00496490), no figure but types 0x18 / 6.
- Footprint (`FUN_00496CA0` case 0x3C): the pier 2x2 like the wharves (bit 8 on all 4 tiles, water kept), image
  `SPR_B_DOCK` group (Zeus_General id 68) first + orientation: 463 SPR_B_DOCK (o0), 464 SPR_B_DOCK_E (o1),
  465 SPR_B_DOCK_S (o2), 466 SPR_B_DOCK_W (o3); each pier image has the small hut on it. Then the dock house
  (`building_create(0x3D, …)`, `g_dock_count += 1`), drawn as a storage: root SPR_B_DHOUSE (469, 1 tile) + bays.
- **Berth** (where the trade ship stops, `0x005BA3A0`, relative to the pier anchor): o0 (x+1, y−1), o1 (x+3, y+1),
  o2 (x+1, y+3), o3 (x−1, y+1). (o1/o2 are two tiles out, o0/o3 one: as decoded; the o1/o2 berth tile is not among the
  tiles the placement test requires to be water.) Ships route over grid_ship (pathfinding.md §7). The berth is
  re-derived each tick while the ship holds the dock's reservation `dock+0xB6`.
- Oracle (re/oracle/runs/shore/dock.bmp, scenario re/oracle/scenarios/shore.txt): the working city's dock, pier (108,65)
  o2 (water row y=66), dock house at (107,61) = pier + (−1, −4), image SPR_B_DOCK_S; checked in the tick-0 dump.
- Ours (sim/systems/shore.py since 10-28): the same tests and footprint; the sim's dock is one Building (the 4x4 house,
  storage + workers) plus `misc["pier"]`, `misc["orient"]` with the pier tiles in the occupancy grid.
