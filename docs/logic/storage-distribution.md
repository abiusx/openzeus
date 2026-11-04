# Storage and distribution: storages, cart delivery, agoras, vendors, house goods

Status: **verified** from the exe unless tagged **hypothesis**. Addresses refer to GOG `Zeus.exe`.
Units: 100 = one load. Resource ids: `extracted/model/resources.json` (game text group 23).
Production (what fills the carts): [production.md](production.md). Struct fields: `re/structs/economy.tsv`.

## Overview
1. A producer's **cart pusher** (figure 4) picks a destination by fixed priority: Poseidon orichalc
   consumer → workshop needing the good as input → storehouse bay → granary (honouring stockpile) →
   any granary; nearest by route within a class; partial unloads re-search (Part A §6).
2. **Storages** (rank 81 records, 268 bytes × 200 at `0x009214F8`) hold the per-good orders
   (accept / refuse / get / empty) and limits. Granary food is kept in the granary building
   (`+0x58 + 2*(res-1)`, i.e. `+0x56 + 2*res`, with `+0x56` = free space); storehouse goods in its 8
   bays (400 each) (Part A).
3. **Agoras** keep the stock (`agora+0x56 + 2*slot`); vendor stalls send buyers (figure 37) to
   storages ≤ 40 tiles away; each fetched load is carried home by a vendor assistant (figure 47,
   +100). The agora's **peddler** (figure 26) tops houses in a 5×5 square up to 2× the next level's
   needs (Part B).
4. Houses eat pop×25/100 per required food type each month (`0x0048B8D0`) (Part B).

## Part A — Storage and cart delivery
Status: read from the GOG exe (zeus.c decompile + disassembly) unless tagged **hypothesis**.
Units: goods amounts are in 1/100 load (100 = 1 load, the "loads" of the UI). Resource ids are
the game-text group 23 ids (1 urchin … 22 chariot, see resources.json).

### Summary
- Every storage-like building (granary 57 = 0x39, storehouse 58 = 0x3A, dock-house 61 = 0x3D,
  trading post 62 = 0x3E, agoras 63/64 = 0x3F/0x40) owns one **storage record** (sav rank 81) that
  holds the player's per-good orders (accept / refuse / get / empty) and per-good stock limits.
- **Granary** stock lives in the granary building itself: `+0x56` = free space (starts 3200),
  `+0x56 + 2*good` = stock of food good 1..8.
- **Storehouse** stock lives in its **bays** (type 59 = 0x3B), a chain hanging off the storehouse
  through `+0x3A` (next). 8 bays (15 for 0x3D/0x3E). A bay holds one good (`+0x12`) up to 400
  (`+0x3C`). Storehouse capacity therefore 8 × 400 = 3200.
- A producer's **cart pusher** (figure 4) looks for a destination every 31 ticks while waiting,
  in this fixed priority: (1) Poseidon orichalc consumers, (2) a workshop that needs this good as
  input, (3) a storehouse bay, (4) a granary honouring "stockpile", (5) any granary. Among
  candidates of one class, the nearest by route wins (`FUN_004d7d10`, walkers subsystem).
- Partial unloads re-search for another destination with the remainder.
- Storehouses/granaries send **storehousemen** (figure 9) to *get* goods from other storages
  (orders = Get) or to push out goods with orders = Empty, and storehouses send **deliverymen**
  (figure 0x24 = 36) to carry inputs to workshops.

### 1. Storage record — `storages[200]` at `0x009214F8`, 0x10C bytes, index 0 unused
Created by `storage_create` `0x00494960(building)`: finds the first record ≥1 whose `+0x08`==0,
zeroes 0x43 dwords, sets `+0x08`=1, `+0x04`=building, updates high-water `0x0091EBF0`.
The building stores the record index in `Building+0xD1` (u8) (**verified**: read by
`FUN_0040cd60`, `storage_find_goods`, …; the write is in the caller — not traced).

| Off | Type | Name | Evidence |
|---|---|---|---|
| +0x04 | i16 | building | `0x00494960` |
| +0x08 | u8 | in_use | `0x00494960`, loops of `0x0048B570`, `0x00488C30` |
| +0x09 | u8 | ? flag | one read at zeus.c:255045 (not analysed) |
| +0x0A | u8[23] | order[good]: 0 accept, 1 refuse, 2 get, 3 empty, 4 agora | text group 130 (0 Accept, 1 Don't Accept, 2 Get, 3 Empty); semantics read in `storage_find_goods`, `FUN_0048b680`, `FUN_0048aeb0`, `FUN_0048a580` |
| +0x34 | i16[23] | stock_limit[good] | init = capacity; compared with stock in `storage_find_goods`, `FUN_0048b680`, `FUN_00488e20`, `FUN_0048b330` |
| +0x7C | i16[23] | limit2[good] (init = capacity; purpose unknown, probably trade) | `0x00494960` |
| +0xC4 | u8[23] | trade_state[good] (init 9 for 0x3A/0x3D/0x3E) | read in `storage_find` (7, 9 = not counted as storage) and `storage_find_goods` (5, 7 = accepts) — trade-empire subsystem |

Capacity per type (inlined everywhere, e.g. `0x00494960`, `0x004895B0`, `0x005B4670`):
```
cap(t) = 8*400 = 3200            if t == 0x3A (storehouse)
       = 15*400 = 6000           if t in (0x3D, 0x3E)
       = 0xC80 = 3200            otherwise (granary)
bays(t) = 15 if t in (0x3D,0x3E) else 8
```
Initial orders (`0x00494960`) **verified**:
```
granary 0x39:  order[g]=0 (accept) for g in 0..22; limits=3200; then order[f]=0 for each food f
               in the food list 0x010DFDAC (count 0x010DFDA8) (a no-op); building+0x56 = 3200 is
               set in building_create 0x00493E70.
0x3A,0x3D,0x3E: order[g]=1 (refuse), limits=cap, trade_state[g]=9; then for every good g in the
               scenario goods list 0x010DFE40 (count 0x010DFE3C): order[g]=0, except storehouse
               (0x3A) keeps food 1..8 refused.
agora 0x3F/0x40: order[0..22] = 4.
```

### 2. Granary stock (`Building` fields of type 0x39)
- `+0x56` i16 = free space (3200 at creation). `+0x56 + 2*g` i16 = stock of food g (1..8).
- **Add** `granary_add_food` `0x0048B680(b, g, unused, amount)` → accepted amount **verified**:
```
if b < 1: return 1;  if type != 0x39 or g not in 1..8 or free < 1: return 0
o = order[g]
if o == 1: return 0
if o in (0, 2) and limit[g] <= stock[g]: return 0
room = limit[g] - stock[g]          # also used when o is 3/4 (no limit check first)
if amount < free: add = room if room < amount else amount
else:             add = room if room < free else free     # = min(room, free)
stock[g] += add; free -= add; return add
```
- **Remove** `granary_remove_food` `0x0048B830(b, g, amount)` → returns shortfall **verified**:
  takes min(amount, stock) from `+0x56+2g`, gives it back to free space `+0x56`, and subtracts it
  from city total `0x00FEB088[g]`.

### 3. Storehouse bays
- `building_root` `0x0049B920(b)`: follows `+0x38` (parent) until ≤0 (max 500 steps) → the main
  building. `storage_find` & co. redirect type 0x3C (dock) through `+0x3A`.
- `storehouse_stock` `0x0048AFA0(b, g)`: sum of `+0x3C` over the first `bays(type)` links of
  the `+0x3A` chain whose `+0x12 == g`.
- **Accept test** `storage_find_goods` `0x004894E0(b, amount, g)` → 1 = cannot accept **verified**:
```
if type in (0x3D,0x3E): if trade_state[g] not in (5,7): return 1
elif order[g] not in (0, 2): return 1
lim = limit[g]; s = storehouse_stock(b,g)
if amount == 0: return s >= lim
return s + amount > lim
```
- **Add** `storehouse_add_goods` `0x004895B0(b, g, amount)` → accepted amount **verified**:
```
b = root(b) (dock -> +0x3A)
workers = (+0x40 of b)   [0x3D: +0x40 of b.+0x38]
if workers < 1 or b.+0x4A != 0 or storage_find_goods(b,0,g): return 0
lim = (order allows: limit[g]) else cap
excess = (s + amount - lim) if storage_find_goods(b,amount,g) else 0
n = amount - excess
repeat n times, one unit at a time:
    among the first bays(type) bays: those empty (+0x12==0) or holding g, with +0x3C < 400,
    pick the one with the largest +0x3C (strict >, so first of equals); none -> return 0
    city_stock_add(g, 1, b); bay.+0x12 = g; bay.+0x3C += 1; refresh bay image
return n
```
  Note: when the bays fill up mid-way the function returns 0 even though some units were stored
  (the caller then thinks nothing was accepted) — **verified** quirk (returns 0 at "none").
- **Remove** `storehouse_remove_goods` (named `storage_select`) `0x00489CC0(b, g, amount)` →
  shortfall **verified**: only for types 0x3A/0x3D/0x3E (else returns `amount`). Repeatedly takes
  from the bay holding g with the **smallest** positive amount (sculpture 0x13: bays < 400 are
  skipped). Emptied bays get `+0x12 = 0`. City totals updated through `city_stock_sub`.

### 4. City stock totals (cycle step 16) `cycle_storages_pass_16` `0x00488C30`
```
zero 0x00FEB2AC[23], 0x00FEB33C[23], 0x00FE9844[23]
for each storage record r (1..0x0091EBF0) in use with active building b:
  if b.type in (0x3A, 0x3E):
     b.+0x44 = 1 if road_adjacent(b.x,b.y,b.size) (0x004A3B40)
              else 2 if road_adjacent(b.x,b.y, 3 (0x3A) / 4) else 0
  elif b.type == 0x3D: root.+0x44 = b.+0x44 = (root.+0x18 != 0)
  else: continue
  if b.+0x44: for each bay in +0x3A chain (type 0x3B, active):
        bay.+0x44 = b.+0x44; if bay.+0x12: city_stock_add(bay.+0x12, bay.+0x3C, b)
```
`city_stock_add` (named `storage_goods_take`) `0x00488A80(g, n, b)` / `city_stock_sub`
(`storage_goods_give`) `0x00488B20`: if `storage_find(b,g)`==0 (trade building with trade_state
7 or 9) → `0x00FE9844[g]`; else if b is 0x3A → `0x00FEB33C[g]`; else → `0x00FEB2AC[g]`.
Granaries are **not** counted here.

### 5. Granary supply list (cycle step 8) `cycle_storages_pass` `0x0048B570`
```
zero 0x0091ED14 (i16 list, 100 entries) and 0x0091EC84[36]; count 0x0091EDE0 = 0
for each storage record in use whose building b is an active granary with b.+0x44 != 0 and b.+0x20 > 0:
   tot = 0
   for g in 1..8: if order[g] != 2: tot += food[g]; 0x0091EC84[g] += food[g]
   if tot > 100 and list not full (98 entries): append b
```
Consumers of this list (agora/vendors) belong to the distribution fork.

### 6. Cart pusher (figure 4) handler `0x004AE160` (not decompiled; disassembly)
Figure fields: `+0x0B` resource, `+0x74` amount, `+0x5A` home building, `+0x5E` destination
building, `+0x24/+0x26` destination tile, `+0x2C/+0x2E` home tile, `+0x36` wait counter,
`+0x38` action, `+0x11` move result (8 arrived, 9 no path, 10 ?), `+0x66` "why waiting"
(1 nothing accepts, 2 storages understaffed), `+0x7B` waiting flag, `+0x0E` state (2 = remove).
The network id of the cart is `grid_u8 0x00C4F288[figure tile]` (road network, hypothesis:
numbered by step 7) and only buildings with `Building+0x14 == network` are candidates.

Action dispatch (jump table `0x004AECA0`, actions 4..23):
```
6, 17 (0x11: heavy goods wood/marble/black marble/sculpture):   # waiting at producer
  if fig.+0x68 == 0 and route_grid[tile] & 0x0C == 0: die
  if home.state != 1: die
  fig.+0x36 += 1
  if fig.+0x36 > 30:                       # producers spawn carts with +0x36 = 30 -> first search immediately
     0x00EF57B8 = 0                         # counts candidates rejected for low staff
     dest = cart_find_destination(fig, network)       # 0x004CCA50
     fig.+0x36 = 0
     if dest: action = 8 if dest.type==0x39 else 7 if dest.type in (0x3A,0x3B) else 9
              fig.+0x24/26 = dest road tile; fig.+0x7B = 0
     else:    fig.+0x66 = 2 if 0x00EF57B8 else 1; fig.+0x7B = 1
  if action was 0x11 on entry: FUN_004ADF30(6)  # spawns n helper figures 0x1C, sets action 6
7, 8, 9: move (0x004D1170). On arrival (+0x11==8): if dest.state != 1 -> action 6 (re-search)
         else action 10 (storehouse) / 11 (granary) / 12 (workshop).
         On no path (+0x11==9): release route; if route_grid[tile] & 8 == 0: action 6; +0x36 = 0.
10 (at storehouse): +0x36 += 1; when > 10: n = storehouse_add_goods(root(dest), res, amount); after_unload(n)
         storehouse_add_goods 0x004895B0 returns 0 if the storehouse has no workers, burns (+0x4A), or
         storage_cannot_accept 0x004894E0 (order not 0 accept / 2 get; posts: trade state not 5/7); else up to
         the limit, unit by unit into the bays. So an order changed to Don't accept / Empty while the cart walks
         makes the storehouse refuse it on arrival, and after_unload sends it on to another destination.
11 (at granary):    +0x36 += 1; when > 5:  n = granary_add_food(dest, res, 1, amount); after_unload(n)
         granary_add_food 0x0048B680: 0 on order 1 (Don't accept); order 3 (Empty) still takes food (up to the
         free space +0x56 and the limit); no staff test.
12 (at workshop):   +0x36 += 1; when > 5:
         n = (res==0x11 and dest.+0xC4 & 0x40) ? orichalc_deliver 0x0048C3B0 : workshop_add_input 0x0048C410(dest, amount, res)
         after_unload(n)
13: walk home; on arrival the cart is removed (state 2). (If home is a crop farm on meadow
    (0x004A9680 && 0x004AA5D0) and 0x006998E4 in 1..3, the cart is removed at once — hypothesis on meaning.)
18..23: deliveries handled by the object at 0x00FE5100 (0x005465B0 / 0x00534B50 / 0x00543C30):
    hypothesis = construction sites (sanctuaries/monuments) — religion / map-buildings subsystem.
```
`cart_after_unload` `0x004CCAF0(n, fig, network)` **verified**:
```
release reservation on dest: orichalc flag 0x40 of dest.+0xC4, or
   trireme wharf (0x88) with armor: dest.+0xF0 -= 1, dest.+0xF2 -= fig.amount, or
   workshop types {0x35,0x36,0x37,0x85,0x87,0x88,0xD4} or granary: dest.+0x114 -= 1, dest.+0x116 -= fig.amount
if n == fig.amount: action 13 (return), +0x36 = 0, target = home tile, amount = 0
else: amount -= n; dest = cart_find_destination(); none -> action 6, +0x7B = 1
      else action 8/9/7 as above, target = dest tile
```

#### Destination search `cart_find_destination` `0x004CCA50(fig, network)` → fig.+0x5E
First non-zero of, in order (**verified**):
1. `0x0048C250` (Poseidon only, res 0x11 orichalc, not if `0x00FE9524`): active buildings type
   0x84 or 0x88 [+ conditions: not halted unless 0x84; `+0xC4 & 0x60 == 0`; for 0x88 `+0x44` and
   `+0xA8` non-zero; `+0x20 > 0`; same network]; nearest; sets `+0xC4 |= 0x40` (reservation).
2. `find_workshop_for_input` `0x0048BC80`: skipped if `stockpile[res]` (`0x00FE94E0[res]`) is set.
   res → input code: 7→1, 9→2, 10→3, 11→8, 12→4, 13→5, 14→6, 18→7, 19→9 (others: none).
   Candidates: active, `industry_halted` (0x004873F0) false, type in
   {0x35 winery, 0x36 olive press, 0x37 sculpture studio, 0x85 horse ranch, 0x87 armory,
   0x88 trireme wharf, 0xD4 chariot workshop}, `+0x44 != 0`, `+0x20 > 0`, same network,
   `workshop_accepts` `0x0048A880(b, code)`:
   ```
   cap = stock_cap(type)         # table below
   0x88 with armor: need b.+0xDE == code, b.+0xDC < cap, and if b.+0xF0 > 0: cap - b.+0xF2 - b.+0xDC >= 1
   else: need b.+0x12 == code, b.+0x3C < cap, and if b.+0x114 > 0: cap - b.+0x116 - b.+0x3C >= 1
   ```
   Ranking (exact quirk): keys k1 = pending carts `+0x114` (0x88/armor: `+0xF0`), k2 = stock
   `+0x3C` (0x88/armor: `+0xDC`); best1 = best2 = 10000. A building is kept only if
   k1 <= best1 and k2 <= best2; if k2 < best2 the list is cleared first and (best1,best2) = (k1,k2);
   if k2 == best2 it is appended without changing best1. Then nearest by route among the list.
   Chosen: `+0x114 += 1`, `+0x116 += fig.amount` (0x88/armor: `+0xF0`, `+0xF2`).
3. `find_storehouse_bay` `0x00488E20(exclude, fig, res, network)`: all active bays (0x3B) with
   `+0x44 != 0`, `+0x20 > 0`, same network; root = building_root(bay) (dock → +0x3A);
   skip if root == exclude unless order[res]==2;
   root 0x3A: order in (0,2) and stock < limit; root 0x3D/0x3E: trade_state==7 and stock < limit;
   staff% of root ≥ 50 (`workers*100/model_employees`; for 0x3D the code computes
   `model_employees*100/workers` of the parent — inverted, verified as written) else `0x00EF57B8++`;
   bay empty or (bay.+0x12==res and bay.+0x3C < 400).
   Target tile: root road tile `+0x26/+0x28` if root.+0x44 == 1, else a road found with size 3/4.
   Nearest by route among bays; returns the **bay** id. No reservation.
4. `find_granary` `0x0048B330(0, fig, res, network)`, 5. same with ignore_stockpile = 1:
   returns 0 if `0x00902C0C` (scenario flag, unknown) or res not food 1..8, or
   (`stockpile[res]` and not ignore). Candidates: active granary, `+0x44 != 0`, `+0x20 > 0`,
   same network, `+0xDA == 0`, staff% ≥ 50 (else `0x00EF57B8++`), order in (0,2),
   stock < limit, (`+0x114 < 1` or limit − `+0x116` − stock > 0), free space `+0x56` ≥ 100.
   Nearest; reserves `+0x114 += 1`, `+0x116 += amount`.

Note: since step 5 ignores stockpile, a stockpiled food still goes to a granary; stockpile only
stops delivery to workshops (step 2) and to granaries in step 4 — **verified** as coded.

#### Workshop input `workshop_add_input` `0x0048C410(b, amount, res)` → accepted
```
0x88 with armor (0x12): if b.+0xDE == 7 and b.+0xDC < 300: take min(amount, 300 - b.+0xDC)
else if b.+0x12 == input_code(res) and b.+0x3C < cap: take min(amount, cap - b.+0x3C)
```
`stock_cap(type)` (inlined in `0x0048A880`, `0x0048C410`, buildings_spawn_walkers):
500: 0x29, 0x2A, 0x32, 0xD3; 300: 0x30, 0x35, 0x36, 0x51, 0x87, 0x88; 800: 0x31, 0x85, 0xD5;
400: 0x37, 0xD4; 100000: 0x7A; 600: 0xD8; default 200.

### 7. Storage walkers (step 31, `buildings_spawn_walkers` case 0x39/0x3A → `0x005B4B40`)
Per call (once per 51 ticks), for granary or storehouse b (**verified** unless noted):
```
w1 = b.+0x2A (storehouseman fig 9, valid if alive/same home); w2 = b.+0xB8 (second, 0x0048CF10)
d  = b.+0xB6 (deliveryman fig 0x24)
staff = workers*100/model_employees (0 if +0xDA)
granary: need a road tile (0x004A3FB0) else return
storehouse: copy +0xD3 to bays; need road (size, else 3) else return
   if no d: g = storehouse_pick_for_workshop 0x0048AAC0(b) (first workshop in building order that
      has workers, not halted, same network, and accepts the good of the first suitable bay
      (stock > 0, not stockpiled)); if g >= 0: create fig 0x24 at road tile, action 6, res g,
      amount = min(stock(g), 400), remove it at once (storehouse_remove_goods); heavy goods -> action 10
if staff < 50: return
if w1 and w2: return
compute get-orders: 0x00489E60 -> (g1, g2, pct1, pct2, src1, src2): over goods handled by b
   (0x005B12C0: granary: foods in scenario list; storehouse: scenario goods except food 1..8,
   horses 15, chariots 22, but wheat 7 included), for goods with order==2: pct = stock*100/limit
   (100 if full or, storehouse, no room 0x005B4670); keep the two lowest pct that have a source
   (`storage_find_source` 0x0048A140(b, g, 1, 0, 400): see §8.2; with these args = the
   *first* storage record (not the nearest) holding >= 1 of g, not on Get; any network since
   b's order is Get).
k = empty_target: granary 0x0048AEB0 / storehouse 0x0048A580 (returns 0 if some Get order is
   pending and fillable, else first good with order 3 (Empty) and stock > 0, else -1)
if k > 0 and not w1: amount = min(stock(k), 400); if a destination exists (0x005B4440:   # verified 10-28:
   # one Empty walker at a time: it goes into the +0x2A slot (the same slot Get workers use); the
   # deliveryman +0xB6 and carts of other buildings don't count
   workshop or other storage): create fig 9 with res k, amount; remove now
   (granary: 0x0048B830 and flag fig.+0x10C |= 0x100000; storehouse: storehouse_remove_goods)
if k == 0: n = number of get goods found (0..2); (two, second_same, workers) = 0x0048CA00(pct1, pct2, n):
   n==1: pct1 < 50 -> 2 workers; pct1 < 100 -> 1; else 0
   n==2: pct1 < 100 and pct2 < 100 -> 2 workers (one per good); otherwise per the table in code
   spawn fig 9 (action 6, +0x7A = good, amount 0) into +0x2A, and when two are wanted and +0x2A is
   already out, the second into +0xB8.
```
Storehouseman (fig 9) handler `0x004B0080` (disassembly, **verified** for the get path):
action 6 every 3rd tick: if carrying → action 13; else recompute 0x00489E60, take its good
(g2 if it is the +0xB8 worker and g2 set), source = 0x0048A140(home, g, 0, 0, 400) (any stock);
go there (action 11). At source after 5 ticks: take up to 400 (storehouse_remove_goods /
granary_remove_food); carried = 400 − shortfall; 0 → action 6 else action 10 back home; at home
unload with storehouse_add_goods / granary_add_food, remainder handled by `0x004CD870`
(like cart_after_unload, re-searches with `cart_find_destination`).
Empty mode: destination by `0x004CDAC0`: workshop (0x0048BC80) → granary (0x0048B330, ignore
stockpile if fig flag 0x100000) → storehouse bay (0x00488E20, excluding home; **includes the bays
of exporting trading posts/docks**, §8) → `0x0048BFE0` (any workshop of the input's type on the
network, nearest, ignoring stock/accept tests; 0 if stockpiled).
Spawn test for Empty (`0x005B4440`): `0x005B4480` (a non-halted workshop accepting the good) or
`0x005B4780` (a granary/storehouse/**exporting post** that can take it: staffed ≥ 50 %, same
network, `storage_cannot_accept` false, room).

#### 7.1 The deliveryman (fig 0x24) — verified 11-04 (decompile + oracle)
Spawn (storage_spawn_walkers 0x005B4B40, storehouses only; a granary never sends one, so it never supplies the
horse ranch's wheat): slot `+0xB6` (valid while the figure is alive, type 0x24, `+0x5A` = this storehouse). With the
slot empty, `storehouse_pick_for_workshop 0x0048AAC0(b)`:
```
if staff% of b == 0 (any worker; no 50 % test) or under construction: -1
for every building u in building order: alive, workers +0x40 != 0 (0x84 tower: any), type in
    {0x35, 0x36, 0x37, 0x85, 0x87, 0x88, 0xD4} (+ 0x84 in Poseidon), not industry_halted
  for each of b's 8 bays (chain +0x3A): bay amount > 0, stockpile[bay good] == 0, u.+0x14 == network(b road tile)
     orichalc 0x11 to 0x84 / 0x88 (Poseidon): u.+0xC4 & 0x60 == 0 (0x88: +0x44, +0xA8) -> that good
     else code = input_code(bay good); workshop_accepts_input 0x0048A880(u, code) -> that good
-> the good, or -1 (no order test: a storehouse sends goods on Accept, Get, Refuse alike)
```
then the man: figure_create(0x24) at the road tile, action 6, `+0x0B` = good, `+0x74` = min(stock(good), 400),
removed from the bays at once (storehouse_remove_goods), heavy goods (9, 11, 16, 19) action 10 = with ox helpers.
Handler `figure_deliveryman 0x004B87C0` (route mode 1, roads):
```
6, 10: if home.state != 1 or home.+0xB6 != me: state 2 (gone, the goods with him)
       timer++; > 2 (the 3rd call): dest = find_orichalc_consumer, else find_workshop_for_input 0x0048BC80 (§6
       ranking; reserves +0x114 / +0x116), else FUN_0048BFE0; timer 0
       found: action 7 to dest's road tile.  none: action 9 home (trade_building = home)
7: move; arrived -> 8; no route -> route freed, retried
8: timer++; > 4 (the 5th call): n = workshop_add_input(dest, amount, good) (orichalc: orichalc_deliver);
   release the reservation (+0x114 -= 1, +0x116 -= amount; 0x88 armor +0xF0 / +0xF2)
   n == amount: action 9 home, amount 0.   else: amount -= n, action 6, timer 0 (searches again on the 3rd call)
9: move home; arrived: amount 0 -> state 2. Else n = storehouse_add_goods(home, good, amount): all -> state 2;
   else amount -= n, action 6, timer 0: he stands at home with the rest, still in +0xB6, and searches every few
   ticks; the storehouse sends nobody else meanwhile
```
`FUN_0048BFE0` (any workshop of the input's type, network, +0x44, +0x20; no reservation) lists the buildings' own
tiles (`+0x06 / +0x08`), not their road tiles, and a road route (mode 1) never ends there: it never finds one. Oracle
(sanctuary-build, tick 1550..3360, below): every winery full, the man with 300 grapes went home (action 9, dest =
home) and stood there in action 6 / 9 for 1600 ticks while his storehouse's 8 bays were full of grapes.

#### 7.2 Storehousemen of granaries and storehouses (fig 9) — verified 11-04
After the deliveryman part, `0x005B4B40` goes on only with staff >= 50 % and not both of `+0x2A` (walker_id) and
`+0xB8` alive (building_second_walker_alive 0x0048CF10):
- `storage_get_targets 0x00489E60` over storage_goods_list: pct[g] = 100, for a Get good: storehouse:
  `storehouse_has_room 0x005B4670` false -> 100 (full, or the good's stock whole bays with all 8 bays used), else
  stock*100/limit if stock < limit else 100; granary: free space != 0 and stock < limit -> stock*100/limit, else
  100. Goods with a source (`storage_find_source(b, g, 1, 0, 400)`: the first in record order) and pct < 100 rank:
  lowest -> g1 (the old g1 moves to g2), second lowest -> g2 (strict <: the earlier good wins a tie).
- `granary_empty_target 0x0048AEB0` / `storehouse_empty_target 0x0048A580` (both < 50 % -> -1): 0 when g1 is set
  and some Get good is below its limit (granary: any Get food); else the first Empty good held (storehouse: bay
  order, a sculpture bay < 400 skipped; granary: food 1..8); else -1 -> nothing.
- 0 (Get): n = (g1 set) + (g2 set); `storage_get_worker_plan 0x0048CA00(pct1, pct2, n)` -> (two, same, workers):
  n 1: pct1 < 50 -> (1, 1, 2), pct1 < 100 -> (0, 1, 1); n 2: both < 100 -> (1, 0, 2). workers 0 -> nothing.
  One wanted: +0x2A empty -> a man for g1. Two: +0x2A out -> the second into +0xB8 (for g1 if same, else g2), else
  the first into +0x2A. A Get man leaves empty (`+0x0B` 0, `+0x7A` = good). One spawn a day.
- an Empty good k: only with +0x2A empty; amount = min(stock(k), 400); `0x005B4440` must find a taker (0x005B4480: a
  workshop with workers, not halted, same network, accepting; 0x005B4780: a granary / storehouse / exporting post,
  staffed >= 50 %, same network, order and limit allow the amount, room); fig 9 into +0x2A with good and amount,
  removed at once (a granary's: flag 0x100000 = find_granary ignores the stockpile).
Handler `figure_storehouseman 0x004B0080` (route mode 3 for the trips: roads, then land):
```
every call: home 0x39/0x3A: state != 1 or me not in +0x2A / +0x2C / +0xB8 -> state 2; a post: me not in its 4 slots
6, 0xE: timer++; > 2: timer 0; carrying nothing (Get): home 0x39/0x3A recomputes storage_get_targets, good = g2 if
        I am the +0xB8 man and g2 set, else g1 (a post: its slot's good); source = storage_find_source(home, good,
        0, 0, 400) = the nearest; none -> state 2; else action 0xB to it.  carrying (Empty, or a rest): action 0xD
0xB: move; arrived -> 0xC.   0xC: timer++; > 4: take 400 (storehouse_remove_goods / granary_remove_food, no order
     or stockpile test); carried = 400 - shortfall; 0 -> action 6 (timer 5: the next call searches again);
     else action 10 home
0xD: dest = storage_walker_find_destination 0x004CDAC0: find_workshop_for_input, find_granary (ignore stockpile
     with flag 0x100000), find_storehouse_bay (not home unless home is on Get; exporting posts too), FUN_0048BFE0;
     none -> action 10 home; else action 7
7 -> 8: timer++; > 4: unload by dest type (granary_add_food / storehouse_add_goods / workshop_add_input);
     walker_after_unload 0x004CD870(n, fig, net, 0)
10: move home; arrived: granary_add_food / storehouse_add_goods; walker_after_unload(n, fig, net, 1)
9: move home; arrived -> state 2
walker_after_unload: release the dest's reservation; n == amount: at home state 2, else action 9 (home empty);
     a rest: amount -= n, cart_find_destination (§6) -> action 7, none -> action 6 (then 0xD: the loop above)
```
Trading posts / docks (`0x005B5620`, §8.1) send the same figure: an export good's man is a Get man with his good
fixed, an import good's man an Empty man.

#### 7.3 Monument carts — verified 11-04
`monument_dispatch_cart 0x00543DE0` (the request: monuments.md): once a day city-wide (day_of_month vs `0x00FE6A58`
byte), not when the monument is halted; source = `storage_find_source(monument, good, 0, need_min 1, min(amount,
400))` = the nearest storage on the monument's network holding at least that much (sculpture >= 400; a storehouse on
Get counts, need_min; importing posts; no staff test); the cart (fig 4 + two 0x1C) is created at the source's road
tile with `+0x5A` = the source, amount = amount - shortfall. **No storage slot holds it**: a storehouse with its
deliveryman out still sends monument carts, and several of its carts can be on the road at once (oracle below:
storehouse 60 had two marble carts out at tick 4200). The convoy on a long road is the exe's: one cart a day, ~3.4
tiles a day each (15 ticks a tile).

#### 7.4 Oracle (11-04): `python3 tools/oracle_storemen.py re/oracle/runs/sanctuary-build`
The working city (tutorial15.sav) with its sanctuary reset, 10-tick dumps to 3790. Exe: 11 storehouses, 3 sent
deliverymen; at most **one per storehouse** at any dump (545 grapes, 579 wheat, 341 bronze). Trips: 579 -> horse
ranch 572: out at 270 with 400, unload at 600 (60 taken: ranch at 740 of 800), home at 610 with 340, put back;
545 -> winery 187 at 1550 (400), 100 unloaded, the rest kept (all wineries at 300 = cap), home, refused (its bays
full), stood at home until 3180, then 188 (100) and 186 (100). The dock's and the trading post's storehousemen (fig
9): a fleece / wine fetcher (action 0xB empty -> 0xC take 400 -> 10 home), an olive / wheat pusher (7 -> 8 -> 10 with
the rest home when no press takes it). Monument carts in flight: <= 2 (sanctuary-build), <= 4
(sanctuary-build-long), two at once from storehouse 60 and from 332.
Ours seeded from dump 0 (stocks, orders, limits, trade states; employees pinned): one deliveryman per storehouse, the
same trips: 579 -> 572 out at 270 with 400, unload at 600, home at 610 (ours 350: our ranch ate 10 less); 545 ->
wineries at 1550 and 3180..3300 (ours to 188 then 186 / 185: our wineries' stocks differ); 341 bronze at 780 (exe
1290); the post's fetchers and pushers and the dock's wheat pusher with the exe's shapes (a granary full -> a
storehouse bay). Days differ where our producers and consumption do (their carts, the ranch's eating); the rules
compare equal on every trip seen.

#### 7.5 Ours (sim/systems/storemen.py, 11-04)
All of 7.1..7.3, as role "cart" walkers with task deliver / get / empty and the slots in Building.misc (dman =
+0xB6, sman = +0x2A, sman2 = +0xB8; posts: smen[good]). Producer carts use the same find_workshop_for_input (its
ranking, not halted; was: nearest workshop with room). Before (ours to 11-03): every workshop pulled 100 a day from
the nearest storage (granaries too), any number at once; Get sent 100 a day per good from the nearest storage, no
staff test, no limit; Empty one at a time. Not modelled: bay order (ours: the goods dict's order), the ox helpers of
a heavy load (drawn by the good), the deliveryman's off-road removal only checked per step.

### 8. Trading posts (0x3E) and dock houses (0x3D) as storage — how exports get in
**verified** unless marked. A post/dock owns a storage record like a storehouse (cap 6000/good,
15 bays 0x3B). Per good it has `trade_state` = storage `+0xC4[g]` (`0x009215BC`): 5 import,
6 import off, 7 export, 8 export off, 9 not traded (toggle `trade_post_order_toggle` 0x005B18D0),
and `limit[g]` = storage `+0x34[g]` (`0x0092152C`), default = cap 6000, changed by the panel
arrows (`0x005B1510`, steps from `0x005B14B0`: 100 below 1200, else 400; clamped to 0..cap).
The `order[g]` byte (+0x0A) of a post is ignored by the tests below.

#### 8.1 Goods arrive by three paths
1. **Producer carts** (cart pusher, §6), step 3 of `cart_find_destination`:
   `find_storehouse_bay` 0x00488E20 puts the bays of storehouses **and** posts/docks in one list:
   ```
   root = building_root(bay) (dock 0x3C -> its 0x3D part)
   root 0x3A: order[g] in (0 accept, 2 get) and stock < limit[g]
   root 0x3D/0x3E: trade_state[g] == 7 (export) and stock < limit[g]
   both: staffed >= 50 % (else 0x00EF57B8++), bay empty or (same good and bay < 400), same network
   -> nearest by route among all candidate bays (0x004D7D10); no priority, no reservation
   ```
   So an exporting post competes with storehouses **on route distance only**, and only after
   orichalc users, workshops (step 2) — and before granaries (steps 4/5). No stockpile test in
   step 3: a stockpiled good still goes to an exporting post (the trader then refuses it,
   `city_buys` tests `0x00FE94E0`).
2. **The post fetches it itself** (`0x005B5620`, our name trade_post_spawn_walkers, cycle step 31,
   `buildings_spawn_walkers` case 0x3D/0x3E). For each traded good slot i (< 4, list
   `storage_goods_list` 0x005B12C0) with no live storehouseman in `Building+0xBC+2i` (i16 ×4):
   ```
   if staffed(post) < 50 %: return;  need road access
   ts = trade_state[g]
   if ts in (5, 6):   # importing: push stock out
       if stock > 0 and not stockpile[g] and 0x005B4440(g, 400, network, post) (workshop or storage
          that can take it): fig 9 leaves carrying min(stock, 400), removed from the post now
   elif ts == 7:      # exporting: go and get it
       if not storage_cannot_accept(post, 0, g)      # 0x004894E0: ts in (5,7) and stock < limit[g]
          and storage_find_source(post, g, 1, 0, 400) != 0 and not stockpile[g]:
           fig 9 empty, action 6, +0x7A = g
   ```
   The storehouseman (handler `0x004B0080`, branch for home not 0x39/0x3A at `0x004B0220`) picks
   `storage_find_source(home, g, 0, 0, 400)` = **nearest** source, walks there, takes up to 400,
   brings it back (`storehouse_add_goods`).
3. **Storehouses on "Empty"** (§7): their storehouseman's destination search includes exporting
   posts (via `find_storehouse_bay`).
Storehouses never send to a post because of a Get order: a post is never a Get *requester*
(only 0x39/0x3A run §7), and an exporting post is never a Get *source* (§8.2).

#### 8.2 `storage_find_source` `0x0048A140(b, g, first_only, need_min, min)` → storage building
```
if order_b[g] != 2 and stockpile[g]: return 0
same_net = not (b in {0x39,0x3A,0x3D,0x3E} and order_b[g] == 2)
for each storage record r (in record order), building s = r.building, s.state == 1, s != b,
        (not same_net or network(s) == network(b)):
    s 0x3D/0x3E: skip if trade_state_s[g] in (7, 9)          # exporting posts are not sources
    s 0x3A/0x3D/0x3E: n = stock(s, g)
        skip if (g == 19 sculpture and n < 400) or (need_min and n < min) or n < 1
             or (order_s[g] == 2 and not need_min)          # a storehouse on Get is not drained
    s 0x39: only food 1..8; skip unless granary stock[g] >= 400 and order_s[g] != 2
    other types: skip
first_only: return first candidate; else nearest by route (0x0058A8C0; if b's order is Get and
   none, route_find_listed_tile)
```
#### 8.3 What stops exports from emptying the city
- `limit[g]` of the post (+0x34): carts and the post's own fetchers stop when stock ≥ limit. The
  default is the full 6000, so by default an exporting post pulls every unit it can reach.
- `stockpile[g]` (`0x00FE94E0`, i32 per good; hypothesis: the player's per-good "stockpile"
  toggle — a UI list at zeus.c:184227 picks text 0x82/0x19 vs 0x1A from it): blocks the post's fetchers (both tests above) and
  `city_buys`, but not producer carts going to the post's bays.
- A source storehouse whose order[g] is Get is skipped as a source. Accept / Don't accept /
  Empty storehouses are all drained down to 0 (no reserve kept).
- Trader side (trade.md): `city_buys` (quota[g] > used[g], yearly) and `ledger_full`
  (per trader, loads*unit < limit[g]).
Nothing else: no city-wide reserve, no "keep N" rule.

#### 8.4 Cart destination rule chain (summary, in order)
1. orichalc → tower/warship wharf (Poseidon) `0x0048C250`
2. workshop needing it (not if stockpiled) `0x0048BC80` — fewest pending carts/lowest stock, then nearest
3. storage bay `0x00488E20`: storehouse (Accept/Get, below limit) **or exporting post/dock**
   (below limit), staffed ≥ 50 %; nearest by route; returns the bay
4. granary `0x0048B330` (not if stockpiled), 5. granary ignoring stockpile
6. none → wait (+0x66 = 2 if only understaffed storages were found, else 1), retry every 30 calls

### Constants
| value | meaning | source |
|---|---|---|
| 400 | bay capacity / max load of storage walkers | `0x004895B0`, `0x005B4B40` |
| 3200 | granary & storehouse capacity per good default, granary free space | `0x00494960`, `0x00493E70` |
| 6000 | dock-house / trading post capacity | `0x00494960` |
| 30 | cart re-search period (handler calls) | `0x004AE2A1` |
| 10 / 5 / 5 | unload delays storehouse / granary / workshop | `0x004AE67D`, `0x004AE700`, `0x004AE753` |
| 50 % | minimum staffing of storage to receive carts / send storehousemen | `0x00488E20`, `0x0048B330`, `0x005B4B40` |
| 100 | granary counted in supply list if food total > 100; min free space for carts | `0x0048B570`, `0x0048B330` |

### Open questions
- Handlers not decompiled: cart pusher `0x004AE160`, also `0x004AE100`, `0x004ADBA0` (storehouseman `0x004B0080`
  and deliveryman `0x004B87C0` read 11-04, §7.1, §7.2).
- `Building+0x20` (i16, must be > 0 for every destination) and `+0x18`: meaning (workers present /
  labour access?) — population/labour subsystem.
- `Building+0x4A` (non-zero blocks storehouse_add_goods): fire/curse? `0x00902C0C` (blocks all
  granary deliveries): scenario flag?
- `0x0048BFE0`: analysed in §7 (last resort of emptying storehousemen).
- `storage+0x7C` second limit array and `+0x09` flag; storage_create's caller (where `+0xD1` is set).
- Agora "get food" uses list 0x0091ED14 (distribution fork). (Deliveryman: §7.1.)
- Whether the `storehouse_add_goods` partial-fill returning 0 really loses goods (units stored but cart keeps full amount → duplication).

## Part B — Distribution: agoras, vendors, peddlers, house goods, food consumption
Status: **verified** from the exe unless marked. Addresses: GOG `Zeus.exe`. Building/Figure fields: docs/re/structs.md.

### Summary
An agora (type 63 common / 64 grand) is a parent building; its vendor stalls (68 food, 69 fleece,
70 oil, 71 wine, 72 arms, 73 horse trainer; 66 = empty stall) are child buildings chained through
`+0x3A`. **The stock lives in the agora** (`agora+0x56 + 2*slot`), not in the stalls. Each stall, when
staffed, periodically sends a buyer (figure 37 "Agora Vendors") to the nearest storage within 40 tiles;
at the storage the buyer takes up to 8 (food) / 4 (goods, horses, chariots) loads, and for every load
spawns one follower (figure 47 "Vendor Assistant"). Each follower adds **100** to the agora's stock
when the leader is gone (i.e. when the leader reaches home and is removed). The agora sends one
peddler (figure 26) at a time; on every tile it reaches the peddler serves all houses in the 5×5
square around it (`0x0040D160`). Houses consume food once a month (`0x0048B8D0`).

### Placement (verified 2026-10-28)
`build_commit` checks agoras with `0x0040BF40` over per-type layout tables (16-byte entries dx, dy, kind):
common 0x005E8790 (4 variants x 18 tiles), grand 0x005E8C10 (2 variants x 30). Kind 0 (the 6-tile road
strip): the tile must already be **road** (terrain 0x40) with no building. Kind 1 (stall plots): terrain
& 0x1537526F == 0 (the mask includes road 0x40) and no entry in grid 0x00666930 whose +0x18 is 0 (hypothesis: a figure/object standing there). Variant order (anchor top-left): common 0 =
road column x+2 / stalls left, 1 = road row y / stalls below, 2 = road column x / stalls right, 3 = road
row y+2 / stalls above; grand 0 = road column x+2, 1 = road row y+2 (stalls both sides). With the snap
flag the exe tries anchors x-5..x, y-5..y and every variant, keeping the first that fits and covers the
cursor tile (auto-orientation; not done by us: our `build agora X Y d` takes the variant).
Ours (sim/systems/agora.py `strip_ok`, preview sim/live.py footprint): the same, plus no avenue/bridge tile.

### Units and slots
Resource ids: game text group 23 (1 urchin, 2 fish, 3 meat, 4 cheese, 5 carrots, 6 onions, 7 wheat,
8 oranges, 14 fleece, 15 horses, 18 armor, 20 olive oil, 21 wine, 22 chariot). Food = ids 1..8
(`resource_is_food` `0x0057B190`: `1 <= r <= 8`).

Resource → goods slot (inlined switch, identical in `0x0040CAC0`, `0x0040CC10`, `0x0040D160`,
`0x00484660`, `0x0048B8D0`, …): 7→0, 6→1, 5→2, 4→3, 3→4, 1→5, 2→6, 8→7, 21→8, 20→9, 14→10,
18→11, 15→15, 22→19 (0x13); others → −1. Inverse (slot→resource) in `0x004CF950` etc.

**Two different array bases (conflict resolved, no game bug):**
- **Houses**: goods at `house+0x54 + 2*slot` (i16). Written by the peddler (`0x0040D160`, disasm
  `add word [ecx*2+0x92E6AC]` at 0x0040D3B1 and 0x0040D52E), read by `house_evolve_check`
  (0x004847DA), consumed by `0x0048B8D0` (0x0048BB26). So house wine = +0x64 (slot 8), oil +0x66,
  fleece +0x68, armor +0x6A, horses +0x72, chariots +0x7A — the housing doc's offsets are right.
- **Agoras**: goods at `agora+0x56 + 2*slot` (i16) (`0x0040CAC0`, `0x0040CC10`, disasm
  `[edx*2+0x92E6AE]`; peddler takes from it at 0x0040D3B9 / 0x0040D53B). Ghidra's struct names
  `wine/oil/fleece/arms/edu_access` at 0x64..0x6C are therefore **off by one slot when the building is an
  agora** (agora +0x66 = wine, +0x68 = oil, +0x6A = fleece, +0x6C = armor, +0x74 = horses, +0x7C = chariots).
- Agora units: 100 = one load for every good. House units: food, fleece, oil, wine 1:1 with agora
  units; **arms and horses: 1 house unit = 100 agora units** (peddler divides by 100, `0x0040D515`).
- (Storage fork) The granary keeps its stock indexed by **resource id**, `granary+0x56+2*res`
  (`0x004CEEB0`), not by slot.

### Vendor descriptor table `0x005E8578` (6 × 13 ints; index 5 replaced by `0x005E86B0` in Poseidon)
Lookup loop "for i = 5 downto 0, desc = (i==5 && poseidon_game(0)) ? 0x5E86B0 : 0x5E8578+i*0x34;
match desc[1] == building type". Values read from the exe:

| i | [1] type | [3] resource | [4] slot | [6] source kind | [7] UI flag idx | [11] house col |
|---|---|---|---|---|---|---|
| 0 | 68 food | 7 (any food) | 0 | 0 granary/storehouse food | 0 | 8 (food types) – unused |
| 1 | 69 fleece | 14 | 10 | 1 storehouse goods | 2 | 9 fleece |
| 2 | 70 oil | 20 | 9 | 1 | 1 | 10 oil |
| 3 | 71 wine | 21 | 8 | 1 | 3 | 11 wine |
| 4 | 72 arms | 18 | 11 | 1 | 0 | 12 arms |
| 5 | 73 horses | 15 | 15 | 2 ranch / chariot works | 4 | 7 horses |
(Poseidon row 5: same type/resource/slot, other art ids.) [2],[5],[8] image/text ids, [9],[10] sprite
offsets, [12] passed to `0x004DD040` for the buyer (0x102, 0x10A, 0xFE, 0x10B, 0xFE, 0x10C).
Chariot vendor type 215 is **not** in this table (see Open).

### Agora orders (special orders)
The agora owns a storage record (rank 81, index `agora+0xD1`); per-resource order byte at
`0x00921502 + rec*0x10C + res` (= storage record +0x0A+res). `0x0040CD60(agora,res)`: for food
returns the byte of the first entry of the "goods present" list `0x010DFE40` that is a food (else byte of `res`).
Values seen: 0 = buy (set when a stall is built, `0x0040BD10`), 1 = not buying, 4 = stall removed
(`0x0040BD30` → `0x0040CE00` also zeroes the agora stock of that good; for food, all 8 foods).
`0x0040AB10` (vendor active) = order ∉ {1,4}.

### Vendor stall step — `vendor_update 0x0040A4C0(stall, &counter)`, cycle step 31
Called from `buildings_spawn_walkers` (0x0048CFB0) for types 68..73, skipped when `0x00EF6163` ≠ 0.
`counter` is local to the pass, starts at 0, so the k-th stall processed in the pass sees k.
```
counter += 1
if stall+0x18 < 1: stall+0xD3 = 2                    # "no road/labour access" display flag
if no road tile (0x004A3B40) or stall+0xDA or model emp==0: return
pct = stall+0x40 * 100 / model[type][5]
delay = 2 if pct>=100 / 3 if >=75 / 4 if >=50 / 5 if >=25 / 10 if >=1 ; pct<1: return
agora = parent(stall) if parent type in {63,64} else 0   (0x0040ACE0 → 0x0049B920)
if agora==0: return
stall+0x32 += 1 (u8);  if not (stall+0x32 > delay): return
desc = descriptor(type)
if order(agora, desc[3]) == 1: return
b = stall+0x2C (buyer figure)
if b != 0:
    if fig[b].state != 1 or fig[b].type != 37: stall+0x2C = 0    # (no dispatch this pass)
    return
if (counter % 4) != (month_tick 0x0091EC0C % 4): return
if not agora_wants(agora, desc[3], 0): return        # 0x0040CA40
stall+0x32 = 0
src = find_source(stall, kind=desc[6], list, &flag, slot=desc[4])   # 0x0040EAD0
if src < 1:
    stall+0xE0 = 2 if 0x0040F700(desc[0]) else (1 if 0x0040F680(desc[0])==0 else 3)
    return                       # UI: 1 "No Supply", 2 "Too distant", 3 "Stockpiled"
stall+0xE0 = 0
f = figure_create(.., 37, road x,y); f.action=6; stall+0x2C=f; f.building_id=stall
f+0x5E = src; f+0x9C..0xAC = list (5 slots, -1 = none); f+0xB0..,+0xC4.. = 0
destination = road tile next to src (dock-house special case 0x3D; Zeus horse vendor uses 0x004A3C90)
```
`agora_wants(agora,res,flag)` `0x0040CA40`: food → `food_total(agora) < (flag ? 400 : 1000)`;
res ∈ {15,22,18} → `stock < 300`; else `stock < 200`. `food_total` `0x0040CAC0` = Σ agora stock over
the food list `0x010DFDAC`.

### Source search `find_source 0x0040EAD0` (verified structure; walker distances: walkers agent)
Scans storage records 1..`0x0091EBF0` (occupied byte `0x00921500+rec*0x10C`, building `0x009214FC`).
Candidate storage must be active (state 1), `+0x44` ≠ 0, `+0x20` > 0, and within **Chebyshev distance
< 40** (|dx|,|dy| of building x,y).
- kind 0 (food): granary (57) additionally needs `0x00902C0C`==0 and same `+0x14` as the stall
  (hypothesis: road network id); for each food res 1..8 with `0x00FE94E0[res]==0` and stock ≠ 0 one
  entry is added. Storehouses (58) and trade buildings (61, 62): food res with `0x0048AFA0(st,res)>0`,
  order byte ≠ 9, (storehouse or byte `+0xC4+res` ≠ 7), and `0x01607EC4[res*0x18]==5`. That last one is the
  city's trade status of the food (5 importing, 7 exporting, 9 none; rebuilt by FUN_005BB490 from the posts:
  each post in record order with the good on export, or on import with a trading partner, writes its state, so
  the last one wins): **a storehouse full of wheat is a food source only while wheat is imported** (bug 460).
  Same in `buyer_research_sources 0x0040E2A0`. `+0x44` is road access only (cycle_storage_city_totals
  0x00488C30: 1 road beside, 2 road within the 3/4 ring), so no staff test anywhere in the search; at the
  storage (FUN_004CF950 / FUN_004CFAC0) only the stockpile flag is checked, no trade state.
- kind 1 (goods): same tests for the vendor's own resource; agora stock < 20000.
- kind 2: horse ranches (133) with `building_fields_test` > 0, order(agora,15) ≠ 1 → slot-15 list;
  in Poseidon, for type 73, chariot workshops (212) with `+0xDC`>0 and `+0x74`>0, order(agora,22)≠1
  → slot-19 list (and then ranches are not scanned).
Then per list the candidate with the smallest positive value of the distance grid `0x01079460`
(filled by `0x0058B3C0` from the stall's road entry) wins; granary parts resolved to the parent.
The wanted list (`0x0040D840` food / `0x0040DAE0` goods / `0x0040DC50` horses) and the chosen good
(`0x0040DD00` / `0x0040E090` / `0x0040E210`, which also write `agora+0xAE` = slot being fetched) decide the target.
Food list = first ≤5 food slots of `0x010DFDAC`. Goods priority (`0x0040E090`): first good with agora
stock 0 among wine, armor, fleece, oil; else the lowest relative stock (armor counted at half).

### Buyer at the storage — `0x004CE9B0(fig, home, storage)` (from handler 0x004B8D90, action 6 arrival)
For each of the 5 list slots:
- food slot: if `fig+0xC4 < 800`: `n = loads_food(...)` (`0x004CED40` storehouse, `0x004CEEB0` granary):
  `room = 1100 - fig+0xC4 - food_total(agora)`; if room<1: n=0; `maxl = max(1, room/100)`;
  `have = stock(storage,res)` ; `b = 8 if have>=800 else have/100, but 1 if 1<=have<100`;
  `n = min(maxl, b)`. All food carried is pooled in `fig+0xC4` (slot-0 counter).
- goods (slot 8..11): `0x004CEC80`: `room = 400 - agora[slot] - carried[slot]`, same bucket capped at 4.
- horses (15): `0x004CEB40`: cap 400 (hippodrome target uses a table), bucket = `building_fields_test(ranch)` capped 4.
- chariots (19): `0x004CE760`: cap 400, bucket = min(ws+0xDC/100, ws+0x74/100) capped 4.
- skip if `0x00FE94E0[res]` ≠ 0. On n>0: remove `n*100` from the storage (`storage_select` /
  granary `0x0048B830`; horses/chariots via `0x004CF300`/`0x004CE630`), spawn n followers (fig 47,
  `+0x7A` = slot, chained by `+0x68`), carried += n*100.
Then visited storage appended at `fig+0xB0[fig+0x93]`, `fig+0x93 += 1`.
- food buyer: always returns home after one storage (`0x004CE410` sees `+0x93 != 0`).
- goods buyer (`0x004CE300`): while visits < 3, re-search (`0x0040E2A0`) and go to the source of the
  slot with largest `(400 - agora[slot] - carried)/100`; otherwise home.
- nothing carried → buyer removed (state 2).
Buyer reaching home: removed (state 2) — it delivers nothing itself (handler 0x004B8FB6..0x004B8FEB).

Stall timer (`vendor_update` 0x0040A4C0, step 31): does nothing without a parent agora (`vendor_parent_agora`);
a call counter (`*param_2`, +1 for every vendor building in id order) gates the buyer: the timer `+0x32` runs while
staffed, and past its delay a buyer leaves only on a day with `day_of_month % 4 == counter % 4`, if the stall's
buyer slot `+0x2C` is free and the agora wants the good (`0x0040CA40`); the timer is reset before the source search.
Sim (10-29, track 1C, `agora.update`, `agora.buy_at`): the counter gate, the food rule above (1100 room, < 800
carried, up to 8 loads per food), 400 room / 4 loads for other goods and horses, ranches within 40 tiles for the
horse trainer. Since 10-30 (sim leftovers): the goods buyer's up to 3 storages (`agora.next_storage`: after a
visit, while visits < 3 and 400 - agora stock - carried >= 100, the nearest storage within 40 tiles of the stall that
holds any; ours: nearest by road from the stall, the exe's distance grid at that moment is not traced); a buyer with
nothing carried is removed at the storage (`buyer_go_home_or_die` 0x004CE2D0); the food order is the first 5 of the
city's food list (`agora.city_foods`: rebuild_goods_lists 0x005BAAF0 in goods order urchin .. oranges; a food is
listed when the city's world-map object lists it (the sandbox lists none), an existing city sells it with a quota, or
some storage holds it; with the empire module off only the stock). A 6th food is never bought by agoras
(buyer_food_list 0x0040D840 stops at 5). The list is sticky: a food once listed stays (0x00FEB0D2[res], in the saved
city record, cleared only by FUN_0050d6c0 at a new game / episode start; ours `City.foods_listed` since 10-30, bug 297).
So a city that ever held all 8 foods sells only urchin, fish, meat, cheese and carrots at its agoras, forever; and
since the source search takes the nearest storage with **any** food (all 8, `vendor_find_source` kind 0), a stall
whose nearest granary holds only unlisted foods (wheat, onions, oranges) sends its buyer there for nothing every
time and its agora starves. Oracle 1F-agorafood5 vs 1F-agorafood (tools/oracle_agora_foods.py, working city, granary
32's fish and cheese held at 0, 7 foods listed by poking the sticky flags): agora 494's buyer never takes the last
100 wheat of granary 32 (control: taken at tick ~1100), agoras 494 and 33 run out of food by tick ~3700-4080 while
the control's are restocked from the next granary. g_city_food_list 0x010DFDAC itself is not in the dumps.
Sim (11-04, bug 460, `agora.sources`, `trade.city_status`): the food source rule above (storehouse / post food
only when imported, a post not exporting it), stock > 0 (was >= 100), no staff test (was: staffed storages only),
and at the storage only the stockpile flag (was: a post's import order). The status is computed when asked; the
exe's is rebuilt when an advisor screen opens (advisor_screen_open_refresh 0x00408C00, trade advisor 0x00517E30)
and reset by trade_status_recheck 0x005BAD20 when the last partner goes: ours does not depend on screens.
**Ours: exe bug fixed** (user 2026-10-30, the decision log; bugs.md 297): the food buyer takes every food on the city's
list (`agora.food_list`) and its source search takes the nearest storage holding a food it takes (`agora.sources`),
so a city with 6+ foods no longer starves beside full granaries. Switch: data/fixes.json `agora_all_foods`
(`"fixed": false` = the exe's 5 and any-food search above, for oracle comparisons; `Catalog.fixed`). Also ours: a
Poseidon good (oranges) is not on the city's list while Poseidon is off (`economy.good_on`). Our standalone vendor restock (400 units, buyer loads 400/200) is removed:
the exe has no vendor outside an agora (step 31 calls vendor_update only for 0x44..0x49, which needs the agora;
the chariot vendor 0xD7 has no step-31 case at all), so a standalone vendor of an old save or the chariot vendor
gets nothing.

### Delivery — Vendor Assistant handler `0x004BBD60` (disasm; not in zeus.c)
When its leader `fig+0x68` is no longer a live follower target, the assistant arrives at its
`building_id`: if that is an agora/stall, `agora+0x56+2*slot += 100` for slot ≠ 19 (**chariot loads
are not added here**), no clamp (0x004BC05F); then state 2. (If home is a monument / pyramid part,
400 goes into the storage instead — not distribution.)

### Peddler spawn — `agora_update 0x0040D620` (ECX = agora wrapper; +4 = agora id), step 31
Called for types 63/64 (wrappers `0x0040D7B0`/`0x0040D7E0`), skipped when `0x00EF6163` ≠ 0.
```
if agora+0x18 < 1: agora+0xD3 = 2
need = Σ model[stall.type][5] over stalls in chain (0x0040C8C0); if need==0: return
have = Σ stall+0x40 (0x0040C7D0(agora,-1))
pct = have*100/need; delay = 2/3/4/5/10 as for stalls; pct<1: return
stock = food_total + Σ agora[slot] for stalls 1..5 (0x0040CD00)
p = agora+0x2A: if p>0 and fig alive and type 26 (or 0) and building==agora: return; else agora+0x2A=0
if stock != 0 and ++agora+0x32 > delay:          # timer only advances while stock != 0
    position via 0x0040BEE0; agora+0x32 = 0
    f = figure_create(.., 26 peddler, ..); f.action = 1; agora+0x2A = f; f.building_id = agora
    0x004D6630(f)                                 # roaming setup (walkers)
```

### Peddler service — `peddler_serve 0x0040D160(agora, x, y)` → houses served
Called from the generic service hook `0x004DFB70` (case figure 26) each time the walker reaches a
tile centre (`0x004D69B0`: sub-step counter `+0x39` hits 15). The return value is added to
`agora+0x18` (cap 300). Area: tiles x−2..x+2, y−2..y+2 clipped to the map, row-major from (x−2,y−2).
For each tile whose building id `h>0` has `h+0x05` (is-house) and (`h+0x1C` pop > 0 or type 9..14; sim
10-29: the same, and the empty-house 10 x2 of fleece and oil; goods want = the next level's need only);
a multi-tile house is visited once per covered tile in the square:
```
served += 1
L = h+0x12;  N = L if L in (6,12) else L+1        # next level (top levels keep their own)
if pop==0: per=20; cap=80 else: per=max(1,pop/2); cap=pop*2
held = house_food_total(h)  (0x004FF7B0: Σ h slots over food list)
if held < cap:
  for res in food list 0x010DFDAC (in order):
    s=slot(res); st=agora[s]
    if st>0: g=min(per, cap-held); if g>0: g=min(g,st); h[s]+=g; agora[s]-=g; held+=g
for k in 1..5 (fleece, oil, wine, arms, horses):
  if pop==0 and k in (1,2): want=10
  else:
    want = house_param(N, desc[k][11]); if h.size(+0x03)>1: want*=4; if type 9..14: want*=2
    if want==0: continue
  agora+0x9E+2*desc[7] = 10                         # UI "Distributing" timer
  s=desc[4]; if agora[s] > 0:
    want *= 2
    if k==5: want=min(want, house_param(L,6))      # max horses (current level)
    if k==4: want=min(want, house_param(L,13))     # max armor
    need = want - h[s]
    if need>0: div = 100 if k in (4,5) else 1
               g = min(need, agora[s]/div); h[s]+=g; agora[s]-=div*g
```
So a house is topped up to **2× the next level's requirement** (food: up to 2×pop total, ≤pop/2 per food per visit).

### Monthly consumption — `houses_consume_food 0x0048B8D0`, called by `month_advance`
Runs `cycle_city_buildings_17` first. rate = `0x004E5EF0()` = **25** (constant).
For every building with state 1 and `+0x05` (house):
```
n = house_param(L,8)                       # food types required
per = pop(+0x1C) * 25 / 100 ; if n>1: per = per / n
horse = (h+0x72 != 0)
h+0x7F = 0                                 # food types eaten this month
if 0x00902C0C != 0: h+0x54 = per; h+0x7F = 1; continue     # scenario flag (hypothesis: food not required)
if n>0 or horse:
  for res in food list: s=slot(res); v=h[s]
     if v >= per: h[s]=v-per; eaten += per; h+0x7F += 1
     elif v != 0: h[s]=0;    eaten += per; h+0x7F += 1      # partial still counts (and adds full per)
  if horse: r=1
     for res in food list: v=h[slot]; if v>=r: h[slot]-=r; r=0; break
                           elif v!=0: h[slot]=0; r-=v
     if r: h+0x72 -= r                     # a horse is lost if no food is left
0x00FEB02C = Σ eaten (city food eaten this month)
```
Note: the per-type ration is computed even when n==0 (only horses then matter... and still loops the foods
with per = pop/4 when n==0 && horse — verified: the first loop runs whenever `n>0 || horse`).

### Food / goods lists — `rebuild_goods_lists 0x005BAAF0`
Called from building creation of storages (`0x00494960`), `0x004574C0`, `0x00420390`, `0x00496CA0`,
`0x00510ED0`, `0x00517E30`, `0x005717D0`, `0x005BAD80` (load/setup paths: hypothesis).
- `0x010DFE40` (count `0x010DFE3C`, ≤23): resources 1..22 "available to the city": locally allowed
  (`0x00460F90`: city record / workshops' raw material), imported from a trade city (`0x005BAA40`),
  named by an adventure event of kind 0x17 (`0x005BA980`), given by a god's sanctuary (`0x005BA890`),
  paid as tribute (`0x005BAA90`), sticky flag `0x00FE93EC[r]`, or nonzero counters
  `0x00FEB088[r]+0x00FEB2AC[r]+0x00FEB33C[r]` (hypothesis: stored/produced amounts). Marks `0x00FE93EC[r]=1`.
- `0x010DFDAC` (count `0x010DFDA8`): the same test restricted to foods 1..8, with sticky flag
  `0x00FEB0D2[r]` instead; marks it. **This is the food list of `house_evolve_check`.** Order = ascending
  resource id (urchin, fish, meat, cheese, carrots, onions, wheat, oranges) filtered.
Not saved (no sav block) — rebuilt.
Ported 11-01 (sim/allowed.py goods_list / mark): the flags 0x00FE93EC are kept as g.goods_listed (set at the month
change, episode start, storage creation), in games with an allowed table only. The Distribution page (FUN_00517E30)
groups the list into imports / exports / the rest (reports.distribution "state", pages.js).

### Constants
| value | meaning | source |
|---|---|---|
| 2/3/4/5/10 | stall / agora spawn delay (cycles of step 31) at ≥100/75/50/25/1 % staff | 0x0040A4C0, 0x0040D620 |
| 1000 / 300 / 200 | agora "wants more" thresholds (food total / horses, arms, chariots / other) | 0x0040CA40 |
| 1100, 800, 400 | buyer load room: food (pooled), food-routine non-food, goods/horses/chariots | 0x004CED40, 0x004CEC80 |
| 8 / 4 | max loads per storage stop: food / others | same |
| 40 | max Chebyshev distance stall→storage | 0x0040EAD0 |
| 3 | max storages a goods buyer visits | 0x004CE300 |
| 100 | units per load delivered by each assistant | 0x004BC05F |
| 5×5 | peddler service square | 0x0040D160 |
| 25 % | monthly food ration per person | 0x004E5EF0 |

### Open questions
- Walker handlers 0x004B6720 (peddler 26), 0x004B8D90 (buyer 37), 0x004BBD60 (assistant 47) are not
  functions in zeus.c: please define them for the next decompile. Chariot delivery path (slot 19 is
  skipped by assistants; `0x004CE630` may add directly) unverified.
- Chariot vendor (type 215): no descriptor. In Poseidon the buyer of type 73 fetches from chariot works.
  Settled 2026-10-29: each load takes 100 chariots and 100 horses (0x004CE630), and only the horse (slot 15)
  reaches the agora, so Poseidon horses do reach houses. See production.md "Chariot workshop".
- Horses (15) and chariots (22) never enter storehouses or posts (verified 2026-10-29, bugs.md 179):
  `storage_goods_list` 0x005B12C0 leaves them out for 0x3A/0x3D/0x3E, no cart carries them, and the trade
  state of a post stays 9. One possible exception, unverified: `city_goods_add` 0x00489230 (goods received
  from world cities) checks only the storehouse order byte. That byte is 0 for every good in `g_goods_list`
  (storage_create), which could include 15, so requested horses might land in a storehouse. Ours drops them.
- Answered 11-04 (bug 460): `0x00FE94E0[res]` = stockpile flag, `0x01607EC4[res*0x18]` = city trade status
  (5 importing), `+0xC4+res` == 7 = the post exports it; order value 9 never occurs (orders are 0..4).
- `0x00902C0C` scenario flag (no food needed?) and `0x00EF6163` (global stop; = curse table entry 179).
- `+0x14` equality between granary and stall (road network?). `+0x44` = road access (0x00488C30), `+0x20` > 0.
- `0x0040F700`/`0x0040F680` (status: too distant / no supply / stockpiled) not read.
- Agora `+0x9E` index `desc[7]` is 0 for both food and arms (UI only).
