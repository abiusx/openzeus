# Production: farms, orchards, herding, hunting, fishing, raw materials, workshops

Status: **verified** from the exe unless marked. Addresses refer to GOG `Zeus.exe`.
Building fields: [../re/structs.md](../re/structs.md) plus `re/structs/economy.tsv`.
Storage, carts and distribution: [storage-distribution.md](storage-distribution.md).
Machine-readable summary: `extracted/model/production.json`; resource ids: `extracted/model/resources.json`.

## Summary
Every producer keeps its output in its own building record and sends a **cart pusher** (figure 4)
carrying `Figure+0x74` units of resource `Figure+0x0B` when it has a full load. One load = **100 units**.
Production advances in two places, both once per 51-tick cycle (16 cycles = 1 month):

- **Cycle step 20** (`cycle_buildings_pass_20` `0x00485360`): crop growth (farms, trees) and
  workshop "progress" (`Building+0x54`).
- **Cycle step 31** (`buildings_spawn_walkers` `0x0048CFB0`): harvests, cart departures, and the
  gatherers (growers, herders, hunters, fishing boats, urchin divers, wood cutters, miners), which
  bring raw goods back into `Building+0x3C`. The gatherer walker handlers run every tick.
- **Cycle end** (`0x00483C10`, after step 50, called "month_advance" elsewhere but it runs every cycle):
  tree tending decays (`0x004AA640`), god curse timers decay (`0x004E5EB0`).

Almost every rate is a 5-step ladder on the **employment percentage**
`pct = Building+0x40 (employees, i16) * 100 / model_building_value(type, 5)` (integer division;
0 if `Building+0xDA` ≠ 0 or the model value ≤ 0). The ladder thresholds are always
`pct ≥ 100`, `≥ 75`, `≥ 50`, `≥ 25`, `≥ 1` (and `< 1` = nothing happens).

## Common building fields used here
| Off | Type | Meaning (economy) | Status |
|---|---|---|---|
| +0x12 | i16 | for workshops: **input material code** 1 wheat, 2 wood, 3 bronze, 4 grapes, 5 olives (0 = no input); set by `building_create` `0x00493E70` | verified |
| +0x18 | i16 | must be > 0 for step-20 progress (else icon `+0xD3` = 2); labor/road access, owned by population/labor passes | hypothesis |
| +0x2A, +0x2C | i16 | figure id of the building's current cart (second slot for the grower lodge) / buyer | verified |
| +0x32 | u8 | spawn/production **cycle counter** for producers (the same byte is `sanctuary_finished` for sanctuaries) | verified |
| +0x33 | u8 | quarry idle counter | verified |
| +0x3C | i16 | **stock**: raw goods gathered, or workshop input; capped by `stock_cap(type)` | verified |
| +0x40 | i16 | employees | verified |
| +0x43 | u8 | **output resource id** (`resources.json`); set per type by `building_create`, copied to the cart's `Figure+0x0B`, indexes `g_industry_halted`. Named `type_code` in re/structs/map-buildings.tsv; `re/structs/economy.tsv` corrects it to `output_resource` | verified |
| +0x54 | i16 | crops/trees: growth 0..1920; workshops: progress; fishery: boat-building progress | verified |
| +0x56..+0x9D | i16[36] | horse ranch: horse figure ids (first 6 used) | verified |
| +0x74 | i16 | chariot workshop: horses held (hypothesis from text 281:13) | hypothesis |
| +0xA8 | u8 | count of the building's live gatherers (recounted by `0x0048CED0` when > 5) | verified |
| +0xA9 | u8 | quarry: carts out; corral: processing counter; irrigation timer (farms) | verified (use) |
| +0xAA, +0xAB | u8 | farms: irrigation/growth-boost timers (+0xAB doubles crop growth); corral: cattle in pen / calf timer | verified (use), meaning hypothesis |
| +0xAF | u8 | farm/workshop pause counter (step 20 skips while > 0) | verified (use) |
| +0xB6 | u16 | trees: bit 0x8000 = harvest ready, low byte = tending level; farms: bit 0x8000 = harvest ready; fishery/urchin: boat figure id | verified |
| +0xDA | u8 | set at creation for composite buildings (sanctuaries etc.); forces pct = 0 | verified |
| +0xDB | u8 | **blessed**: next cart ×4 (×1.5 for crops), then cleared | verified |
| +0xDC | i16 | second stock: grower lodge grapes; chariot workshop finished chariots | verified |

Globals:
- `g_type_curse[221]` `0x00EF60B0` (sav rank 126): per building type, nonzero = cursed by a god
  (decremented each cycle by `0x004E5EB0`). Cursed producers zero their progress/stock.
- `0x00EF6163` (= `g_type_curse[179]`, set to 1 by `0x004E5EB0` when `0x004F19E0()` is true):
  when nonzero **no producer sends anything**. Meaning hypothesis (global production stop event).
- `g_industry_halted[24]` i16 at `0x00FE930E` (city record +0x28B6), indexed by resource id: player's
  "shut down industry" toggle. `industry_halted(b)` `0x004873F0` returns `halted[b+0x43]` except:
  grower lodge (0x25) = grapes **and** olives halted (also true if neither good is available,
  `0x00460F90`/`0x005BA890`), fishery `[2]`, urchin `[1]`, hunting `[3]`, mint `[23]`,
  fruit lodge `[8]`, corral `[24]`, trireme wharf `+0xC4 & 1`, `0x84` `0x00FEAF24 == 0`.
- `g_produced[res]` i32 at `0x00FE97B4` (city +0x2D5C): units produced, added when a cart leaves.
- Treasury `0x00FE6A64` (city +0x0C): the mint pays into it.

## stock_cap(type) (inlined table; also `building_stock_add` `0x004F8050`) — verified
| types | cap |
|---|---|
| 0x29 sheep farm, 0x2A goat farm, 0x32 foundry, 0xD3 orichalc refinery | 500 |
| 0x30 mint, 0x35 winery, 0x36 olive press, 0x51, 0x87 armory, 0x88 trireme wharf | 300 |
| 0x31 marble quarry, 0x85 horse ranch, 0xD5 black marble workshop | 800 |
| 0x37 sculpture studio, 0xD4 chariot workshop | 400 |
| 0xD8 corral | 600 |
| 0x7A (tax office) | 100000 (stored as 0x86A0 when clamping, i16 truncation) |
| everything else | 200 |

Some gatherers clamp to their own constants instead (lodges 500, urchin 500, see below).

## Standard cart departure (used by most producers) — verified (`0x0048CFB0`)
```
cart_ok(b): cart = b+0x2A
  if cart > 0 and fig[cart].state != 0 and fig[cart].type in (4, 0) and fig[cart].building == b:
      return False                      # previous cart still alive: wait
  b+0x2A = 0; return True
send_cart(b, res, amount_from_stock=100):
  amount = 100; if b+0xDB: amount = 400; b+0xDB = 0
  f = figure_create(b+0x01, 4, spawn_x, spawn_y, 4, 1)   # spawn tile from house_find_road_access 0x004A3B40
  if f: b+0x2A = f; b+0x3C -= 100; f.action = 6; f+0x0B = res; f.building = b
        f+0x36 = 30; f+0x74 = amount; g_produced[res] += amount
        if res in (9 wood, 11 marble, 16 black marble, 19 sculpture): f.action = 0x11
```
Every branch first requires `house_find_road_access(x, y, size)` `0x004A3B40` (an adjacent road tile;
sets the spawn tile `0x00F13944/0x00F13940`) and `0x00EF6163 == 0`.
Blessing (+0xDB) quadruples the cart but only 100 is taken from stock. The 0x11 action for
building materials is a different delivery route (storage-distribution.md).

## Farms: wheat 0x1F, onion 0x20, carrot 0x21 (output 7, 6, 5)
Growth, step 20 (`0x00485360` → `crop_grow` `0x004A97D0`) — verified:
```
skip unless b.state == 1 and b+0x43 != 0
if irrigated(b):                       # 0x004A96B0: any tile of the 3x3 has terrain bit 0x10000
    b+0x40 = 0 if (b+0xA8 == 0 or industry_halted(b)) else (model employees if b+0xDA == 0 else 0)
require (b+0x18 > 0 or irrigated(b)) and b+0x40 > 0
if b+0xAF: b+0xAF -= 1; stop
if b+0xAB: b+0xAB -= 1
g = pct * 10 / 100;  if b+0xAB: g *= 2           # 0x004A9720 (b+0xAB tested after the decrement)
b+0x54 = min(b+0x54 + g, 1920)
if g_type_curse[type]: b+0x54 = 0
```
So a fully staffed farm reaches 1920 in 192 cycles = 12 months.
**Land quality does not affect yield** (verified 2026-10-27, scan of every code reference to the
meadow grid `0x00C35C68`): readers are only drawing (`0x00454980` at 0x4558D8 / 0x456855,
`terrain_resource_image` 0x4A8455), the reset `map_grids_reset` 0x496159 and the writer
`meadows_update_rect` 0x4AA296. Growth is staffing only (`crop_growth_rate` 0x004A9720 above);
placement needs **at least one** tile of the 3x3 on meadow/floodplain (docs/logic/buildings.md §7).
The meadow value (8..99, lush vs sparse grass) is only the grass sprite.
Irrigated farms (Poseidon floodplain, bit 0x10000: hypothesis on meaning) need no workers: they
are given the full model staff while any of their timers +0xA9/+0xAA/+0xAB is running
(`+0xA8` = number of running timers, set at step 33 by `buildings_count_by_type` `0x00491820`,
which also decrements each timer). Who starts these timers: open.

Harvest flag — verified (`0x004A9AA0`, `0x004A9B00`, step 20): with `ECX = 0x00DB68AA` (6 flags),
`flag[k] = (month == harvest_month[k])` for the 6 crops; on the first cycle of the month
(`month_tick 0x0091EC0C == 0`) every active crop farm of kind k gets `b+0xB6 |= 0x8000`.
Harvest months, table `0x005D9288` (4 ints per crop, −1 terminated, only one used):
| k | crop | month |
|---|---|---|
| 0 | grapevine 0x23 | 9 (Oct) |
| 1 | olive tree 0x24 | 0 (Jan) |
| 2 | wheat 0x1F | 6 (Jul) |
| 3 | onion 0x20 | 3 (Apr) |
| 4 | carrot 0x21 | 3 (Apr) |
| 5 | orange tree 0xD9 | 10 (Nov) |
Irrigated farms show a different harvest month in the UI (`0x004AA350` returns `0x006998E0`),
but the flag logic above is the same (hypothesis: no other setter found).

Harvest cart, step 31 — verified (`0x0048CFB0` case 0x1F..0x21, `farm_harvest_amount` `0x004A9A30`):
```
if b+0x18 < 1: b+0xD3 = 2
if not house_find_road_access(b) or 0x00EF6163: skip
if not cart_ok(b): skip
if b+0xB6 & 0x8000:
    b+0xB6 &= 0x7FFF
    a = (b+0x54 * 100 / 1920) << 3            # 0..800
    if industry_halted(b): a = 0
    b+0x54 = 0; redraw farm (0x004AA150)
    amount = ceil(a / 100) * 100
    if amount and b+0xDB: amount = amount * 150 / 100; b+0xDB = 0
    cart of `amount` units of b+0x43 (one cart, up to 8 loads; stock +0x3C not used)
```
A harvest that finds a previous cart still alive waits for the next cycle (flag kept).

## Orchards: grapevine 0x23 (grapes 12), olive tree 0x24 (olives 13), orange tree 0xD9 (oranges 8)
Trees are 1-tile buildings with no workers. Growth, step 20, every cycle (no employment test):
```
g = 0 if tend == 0; 8 if 1 <= tend <= 80; 19 if tend >= 81    # tend = b+0xB6 & 0xFF; 0x004AA780
b+0x54 = min(b+0x54 + g, 1920);  cursed -> 0
```
Tending: a grower that finishes tending (`0x004AB6F0`) sets `tend = 160` (keeps bit 0x8000).
Each cycle end `tend -= 1` (min 0) for every tree (`0x004AA640`/`0x004AA690`).
Harvest flag: step 31 calls `0x004A98C0` (ECX = the step-20 flag array): on month_tick 0 of the
harvest month, `b+0xB6 |= 0x8000`.
Rot: at the end of month 2 (Mar) or 11 (Dec) (`0x00483C10` → `0x004AA6D0`): olive trees in month
2 and grapevines in month 11 lose growth and flag (`b+0x54 = 0`). The orange test is `month == 0`
inside a call made only in months 2 and 11, so **oranges never rot** (verified; likely a bug).
Picking (`0x004AB080`, grower at the tree): if flag set → clear it, `load = b+0x54 * 100 / 1920`
(0..100), `b+0x54 = 0`; the grower carries `load` (`Figure+0x6F`) home.

Passability of orchard tree tiles (verified in the decompile 2026-10-28; not yet seen in an oracle run):
- Route grid `0x005876F0`: a building tile (terrain `0x8`) of type 0x23, 0x24 or 0xD9 gets bit `0x10`
  (open land), like avenue/boulevard (0x76, 0x7E); every other building gets `0x02` (blocked) or `0x20`.
  So every land search whose mask has `0x10` (`0x11D`, `0x11C`, `0x13C`/`0x13D`, `0x15C`, `0x19C`:
  migrants, herders mode 0, hunters/woodcutters mode 3, override walks...) crosses orchard trees.
  Road-only modes (1, 14: masks `0x10C`, `0x0C`) do not (carts, roamers stay on roads anyway).
- `check_next_tile` `0x004D8BB0`: a building tile is passable if 0x23/0x24/0xD9 (walkers.md §3.5).
- Grower (figure 5, `figure_grower` `0x004AECF0`): route mode 17 → `route_distance_buildings`
  `0x00588D30` (mask `0x13D`; a tile with terrain `0x10000000`, a monument site, only if
  `building_is_tree` `0x004A96E0`: type 0x23..0x24 or 0xD9). `grower_next_ripe_tree` `0x004AB770` /
  `grower_next_tree_to_tend` `0x004AB640` set `dest` = the **tree's own tile**; on arrival (direction 8)
  action 0xC / 8 waits `timer = 0xCC` (204 ticks) on that tile, then `grower_pick_done` `0x004AB830`
  (`tree_pick`) / `grower_tend_done` `0x004AB6F0`. Tree choice (`0x004AA8A0` ripe, `0x004AAC20`
  tending) floods `route_distance_buildings` from the lodge's road access and keeps only trees whose
  own tile got a distance (`g_grid_route_distance[tree] != 0`), sorted by distance (tending: distance +
  `(tend >> 1) & 0x7F`). No radius and no distance cutoff (the flood covers the map; the walk itself is
  limited only by the route tracer's 499 steps). Sim: the same since 10-29 (`economy.send_growers`).
- Wild animals (`0x00569D90`): terrain `& 0x103AD02A` blocks, which has the building bit `0x8`, so
  orchard trees block them (as any building).
- Sheep, goats, cattle (mode 15, `0x00587FB0`): `terrain & 0x1D7FDC0F == 0x800`; the building bit
  is in the mask, so they never route over an orchard tile.
Sim (2026-10-28): `walkers.walkable()` treats orchard tree tiles as walkable for everyone on land;
`open_walkable()` (no buildings) is kept for grazers and ranch horses (horse rule unchecked);
`wild_walkable()` unchanged. Growers walk onto the tree's tile.

## Grower's lodge 0x25 (grapes + olives), fruit (orange) lodge 0xD6 (oranges)
Step 31, `0x0048CFB0` + `lodge_send_growers` `0x004AB210` — verified:
```
pct as usual (0 if +0xDA); lodge 0x25 only works if grapes or olives are not halted; 0xD6 if oranges not halted
b+0xA8 = count of live growers (figure 5) of b       # 0x0048CED0
interval, pickers, tenders by pct: >=100: 1,4,1  >=75: 4,3,1  >=50: 8,2,1  >=25: 16,1,1  else: 32,0,0
counter = b+0x32; b+0x32 += 1; if counter < interval: return False; b+0x32 = 0
pickers: for each ripe tree found by 0x004AA8A0 (up to `pickers`), of the right kind, not halted,
  not cursed, while the matching stock < 500: spawn grower (action 10) aimed at it
tenders: trees found by 0x004AAC20 (pickers... `tenders*4` trees): one grower (action 6) per 4 trees
growers are spawned only while b+0xA8 < pickers (resp. tenders); grower i gets Figure+0x36 = (i*5+15)*2
return True
```
Details (read 10-29, track 1C):
- Everything above runs only while `b+0xA8 < pickers` (0 below 25 %: nothing at all).
- Pickers (`0x004AA8A0`): ripe trees with a route distance; a ripe tree with growth 0 loses its flag there. A
  tree already claimed (`tree+0x2A` = grower) is taken only if that grower's remaining route
  (`route_len - route_step`) is longer than this tree's distance; the old grower then gets
  `grower_next_ripe_tree` `0x004AB770` (the first other tree, by building id, still claimed by it, walked to as a
  picker; none: home). Stock test per tree: `+0xDC` grapes / `+0x3C` olives, oranges `< 500` (carried loads not
  counted).
- Tender: after the pickers, only if `b+0xA8` is still 0 (no grower out, none just sent): one grower claims
  up to 4 unclaimed unripe trees (any tend level) by distance + tend/2; it visits them in building-id order
  (`grower_find_assigned_tree` `0x004AA7D0` from `trade_building + 1`); each visit: 204 ticks, tend = 160,
  claim dropped (`0x004AB6F0`).
- The `(i*5+15)*2` timer is written but `figure_grower` `0x004AECF0` actions 6 and 10 never read it (unlike the
  herders' action 6): growers leave at once. (open-questions.md had "growers leave after the delay": wrong.)

Delivery (`lodge_receive_fruit` `0x004AAF60`): olives → `+0x3C`, oranges → `+0x3C`, grapes → `+0xDC`,
each `+= load`, clamp 500; also `g_produced` (`0x00FE97E8` olives, `0x00FE97D4` oranges,
`0x00FE97E4` grapes) — note: these are counted on delivery to the lodge, not on cart departure.
Carts (only if `lodge_send_growers` returned True): lodge 0x25: grapes cart (slot +0x2A) when
`+0xDC ≥ 100`, then olives cart (slot +0x2C) when `+0x3C ≥ 100`; 0xD6: oranges cart when `+0x3C ≥ 100`.
Each cart takes exactly 100 from the stock (400 delivered if blessed).

## Herding: sheep farm "Carding shed" 0x29 (fleece 14), goat farm "Dairy" 0x2A (cheese 4)
Step 31, `herd_send_herders` `0x004F77A0` then `cart_ready` `0x004F7030` / `herd_send_cart` `0x004F70B0` — verified:
```
pct = 0 -> nothing
max_herders = 2 if pct>=100, 1 if pct>=50, else 0        # 0x004F7770
interval = 1 (>=100), 4 (>=75), 8 (>=50), 16 (>=25), 32 (else)
counter = b+0x32; b+0x32 += 1; if counter < interval: stop; b+0x32 = 0
animal = sheep (49) for 0x29, goat (50) for 0x2A; herder = shepherd (30) / goat herder (31)
if b+0xA8 < max_herders:
  if b+0x3C < 500: for each ready animal (0x004F7180: animal Figure+0x92 >= 100, reachable),
      spawn herder (action 0xB) and bind it (animal Figure+0x138 = herder) until b+0xA8 == max_herders
  tending herders: animals from 0x004F74A0, one herder (action 6) per 4 animals
cart: if b+0x3C >= 100 and no live cart: cart of 100 (400 blessed) of b+0x43
```
Herder at the animal (`0x004F7F60`): animal readiness `Figure+0x92 = 0`, herder carries 100
(`Figure+0x6F`); at the farm `building_stock_add` `0x004F8050`: `+0x3C += 100`, clamp `stock_cap` (500).
The shear test `+0x3C < 500` does not count loads on the way, so at 400 two shearers go out and one load is lost
at the clamp (ours counted the loads on the way and did not clamp, a farm held 600: fixed 10-31, bugs.md 332).
So **one shorn sheep / milked goat = 1 load**. `Figure+0x92` regrows +9 per month (`0x004F8D80`, see
"Wool / milk readiness" below; ready again 12 months after shearing; confirmed by oracle dumps).

### Herder trips and what is drawn (2026-10-28, verified in the exe; play-mode bug 41)
`figure_shepherd` `0x004B6CF0` / `figure_goat_herder` `0x004B72C0` (same machine), `herder_take_from_animal`
`0x004F7F60`, `figure_sheep` `0x004BC380`, `figure_goat` `0x004BCAF0`:
```
interval: the counter is compared before its increment, so a dispatch every interval+1 days
departure: the k-th herder of one dispatch waits in the farm, hidden, timer (k*5+15)*2 ticks (30, 40, ...)
shear / milk trip (action 0xB -> 0xC -> 0xD -> 0xE):
  0xC  walk to the bound animal's TILE; on arrival, if it moved, re-route to where it is now (no limit)
  0xD  herder_take_from_animal: animal ready = 0, herder carries 100, animal.saved_action = action,
       animal.action = 9 (hidden: Figure+0x65 = 1, so city_draw 0x00458170 skips it);
       timer 0x14 = 20 ticks; sprite = SprMain group 70 (shepherd, 12 frames, 1 per tick, one direction;
       the sheep is drawn inside this sprite) / group 39 (goat herder milking, 8 frames)
       then the animal's action is restored and the herder walks home (0xE, carry sprite group 71 / 40)
  0xE  at the farm: building_stock_add (+100, clamp 500)
tending trip (action 6 -> 7 -> 8 -> ... -> 9), sent after the shear trips when a slot is left:
  animals: 0x004F74A0 = unbound animals (bound_worker 0, any readiness, reachable), nearest first,
  at most max_herders of them; the first gets a new herder, the next 3 share it (so 1-2 in practice)
  6    hidden in the farm, (k*5+15)*2 ticks
  7    walk to the next animal bound to it (0x004F8370, by figure id) at its tile of that moment
  8    stand guard 0x78 = 120 ticks, sprite group 72 (shepherd) / 41 (goat herder), 10 frames, 1 per tick;
       on frames 1 and 6 looks for a wolf (type 0x3B) within 5 tiles (0x004F7E70): chases it (action 0xF)
  then the next animal, or home (action 9) and gone
  a shear dispatch may take a tended animal: its tending herder is sent home (0x004F7FF0, action 9)
sheep sprites: ready_level < 100 -> the shorn set (0x668E.., SprMain group 141 walk 7873), else fleece
  (group 64 walk 3183). Goats look the same either way.
```
Shorn look checked against the running exe (2026-10-28, play-mode bug 50): `cmp byte [fig+0x92], 0x64; jb`
at `0x004BC6BF` picks 0x668E.. (shorn) below 100. Sprite ids decode as file = id>>9, group = (id & 0x1FF) - 1,
0-based like `extracted/sprites/SprMain/group_N` (cross-check: the shepherd's shear sprite is table entry
0x230/8 = 70 = group_70, the shearing picture). Group 141 (images 7873..) is the nude sheep.
Oracle: "See a working city" (the designers' city, 24 sheep), 31,400 ticks (May 1340 BC to Aug 1337 BC),
dumps every 408 ticks: `Figure+0x04` (the drawn sprite) of every visible sheep with ready_level < 100 is
an image >= 7873 (nude set), and **92% of visible sheep samples are nude** (1,821 samples; at most
5 of 24 at 100 at any time, often 0). Readiness rises +9 at each month change (dumps), shearing at 100.
So in the original a sheep is nude about 11 months in 12 unless shearing stops (no workers, farm
stock 500). Our sim on the user's save (2 farms, 16 sheep, 60 months): 70% shorn (some sheep stay
woolly because ours only shears within the farm's radius / a 40-step path; the exe searches every
reachable sheep in the city, `herd_find_ready_animals` `0x004F7180` with no distance limit).
Pixel check (2026-10-28, bug 78 reopened): the running exe's "See a working city" meadow (minimap click 720,235; re/oracle/runs/sheep-78/*.bmp) shows almost every sheep pink/nude (group 141), 1-2 woolly; the user's memory of "mostly woolly" does not match the exe. Draw test is only `ready_level < 100` (figure_sheep 0x004BC380: 0x668E.. nude set else 0x6641.. fleece set), no readiness bands.
Targets are taken when the herder leaves the farm, not at dispatch (2026-10-28, play-mode bug 78):
`FUN_004f7ce0` (end of the 0xB wait) picks the lowest-id animal bound to this herder with ready >= 100 (none:
home, 0xE) and sets dest = its tile then; `FUN_004f7c40` (end of the 6 wait / of each guard) does the same
for the next tended animal (`FUN_004f8370`). The animal is NOT stopped while a herder walks to it: flag 2 set by
`FUN_004e3280` only marks "someone targets me" so `figure_clear_target_links` `0x004E32C0` can clear the
links when it dies; `figure_sheep` and `figure_graze` never read it or bound_worker (beyond clearing a dead
one). So the shearer chases (0xC re-routes on arrival until on the animal's tile) and shears ON it; the
tending herder does not follow: on arrival (or blocked) it guards 120 ticks wherever it stopped, so it
often stands on bare meadow a few tiles from a sheep that grazed on (ours: ~30% of guard stops end >= 3
tiles away, as the exe's rule implies; oracle, same city, dumps every 40 ticks for 1,800 ticks: of 64 samples of shepherds in action 8, 41 on their animal's tile (Figure+0x164), 4 at 1, 4 at 2, 15 at >= 3; all 4 action-0xD samples on the tile. Screenshot re/oracle/runs/sheep-78/guard_jul1340.bmp: a guard (staff, one direction) on bare grass next to a grazing sheep). Spawned sheep/goats (step 49) start at ready 0 (`figure_create`
zeroes the figure, then `ready_level = 0`), cattle at 1.
Ours (sim/systems/economy.py `send_herders`, walkers.py `depart_herder`/`reach_target`/`finish_work`, export.py
`herder_look`, viewer/play/scene.js): all of the above except the wolf chase (not modelled); animals searched
in the whole reachable city, nearest by walking distance (no radius; before bug 78 a 14-tile radius left
sheep that wandered off unshorn forever). After the fix on the user's save: 89% of sheep nude, at most 5 of
16 full at once (oracle: 92%, 5 of 24). Open: the sheep's own hidden action 6 at placement.

## Corral 0xD8 (Poseidon; cattle → meat 3)
Step 31: requires corral not halted (`0x00FE933E == 0`), road exit, pct > 0. Then
`corral_update` `0x004F9E90`, `corral_send_ranchers` `0x004F9960`, then the standard cart — verified:
```
corral_update (if not cursed):
  city_cattle 0x00FE91AC -= b+0xAA + (b+0xAB != 0)        # recounted at the end
  if b+0xAB: b+0xAB += 1; if b+0xAB > 15: release a calf (0x004F9CC0)
  if b+0xAA and (++b+0xA9) > 7 and b+0x54 == 0:
      b+0xA9 = 0; b+0xAA -= 1                              # one penned cow taken
      if b+0x3C < 600: b+0xAD = 1; b+0x54 = 1              # start slaughter
  if b+0x54: b+0x54 += 1
      if b+0x54 == 8 and b+0xAB == 0: b+0xAB = 1           # calf timer starts
      if b+0x54 > 15: b+0x54 = 0; b+0x3C = min(b+0x3C + 200, 600)   # 2 loads of meat per cow
  city_cattle += b+0xAA + (b+0xAB != 0)
corral_send_ranchers: same interval ladder as herding (1/4/8/16/32 cycles);
  if b+0xA8 < 2 and (b+0xAA + calf) < 3 and b+0xA8 + that < 3 and b+0x3C < 600:
     for cattle (76) found by 0x004F9630: spawn rancher (77), action 0xB, Figure+0x36 = 30, max 2
```
`0x004F9630(0, 0x4C, 3, 0, 1, out)`: live cattle with readiness (`Figure+0x92`) > 99 (the +9-a-month value of
the wool rule; calves are born with 1), a route distance from the corral's road access (no radius), not bound
to a rancher (type 0x4D) or 0x41, nearest first, **at most 1** per dispatch. `figure_rancher` `0x004CBB00`:
action 0xB hidden in the corral 30 ticks, then walks (route mode 0) to the cow's tile, re-routing to where it
is now on each arrival (no limit); on its tile the cow is led (action 0x14) home. Sim: the same (10-29).

## Animal movement (RE) — sheep, goats, cattle, ranch horses, boar, wolves
Read from the decompile (2026-10-27). All handlers run **once per tick** per figure (walkers_update).
Move speeds are model col 8 through the speed pattern (walkers.md §1.3); 15 sub-steps = 1 tile.
There is **no deer** figure in Zeus: figure types are 49 sheep, 50 goat, 51 boar, 59 wolf, 76 cattle,
43 horse/jockey (model names, `extracted/model/figure_handlers.json`). The only huntable prey is the boar
(`0x00569990` returns `type == 0x33`, used by `0x004D05F0`, the hunting lodge's prey search).

| kind | type | handler | speed code | ticks/tile | route mode |
|---|---|---|---|---|---|
| sheep | 49 | `figure_sheep` `0x004BC380` | 6 (1/tick) | 15 | 15 (meadow only) |
| goat | 50 | `figure_goat` `0x004BCAF0` | 5 (3/4) | 20 | 15 |
| cattle (calf/cow, resource 3) | 76 | `figure_cattle` `0x004CB350` | 5 | 20 | 15 |
| ranch horse | 43 | `figure_horse` `0x004BA080` | hard-coded 6 (`figure_move(f, 6)`) | 15 | 9 |
| boar | 51 | `fig_handler_boar` `0x004BD030` | 7 (5/4) | 12 | 5 |
| wolf | 59 | `fig_handler_wolf` `0x004BD4A0` | 7 | 12 | 16 |

### Sheep, goats, cattle: one shared "graze" machine — verified
Same state machine in all three (`figure_sheep`/`figure_goat`/`figure_cattle` switch on `action`), plus
`animal_month_tick` `0x004F8D80` (called first every tick). Actions: 6 = start, 7 = walk to grazing spot,
0x10 = graze (`figure_graze` `0x004F8770`), 0x11 = idle-wander (`0x004F8B90`), 8 = walk of the idle-wander,
9 = frozen/hidden (being sheared/milked), 0xF/other = reset to 6, 0x14/0x15 = led by a herder/rancher.
```
action 6 (also the fallback for unknown actions): hidden=1; timer -= 1; if timer < 1:
      if animal_pick_dest(f, action=7, radius=4): walk          # 0x004F83E0
      else: f+0x144 += 1; timer = 100; action = 0x10            # graze where it stands
action 7: figure_move(f, speed); on arrival (direction 8): action = 0x10, timer = 100
          on direction 10 (blocked): if tile has building or terrain&0x10000000: action 4 (die) else action 0x10
          on 9 (route lost): route_free (re-route)
action 0x10 graze (figure_graze):
  timer -= 1; if timer != 0: { if timer > 0x46: timer = 0x46 }; return          # so first graze = 71 ticks
  # timer reached 0:
  if tile has a building or terrain&0x10000000: action = 4 (animal dies)
  g = regrowth[tile]                       # meadow regrowth byte (map-terrain.md section 5)
  counter f+0x144: tile plain meadow(terrain&0x1000CA60==0x800): g>=250 -> 0; 100<=g<250 -> -1; g<50 -> +1; else unchanged
                   (counter is write-only in the decompile: purpose unknown)
  draw D1;  if (rng_a & 7) != 0 [7/8] and tile free of buildings and tile is plain meadow:
        draw D2;  timer = rng_15 % 50 + 20          # stays and keeps grazing 20..69 more ticks
  else [1/8, or tile not plain meadow]:
        regrowth[tile] = 0                          # the tile is eaten bare
        if animal_pick_dest(f, 7, 4): walk (action 7)
        else: draw D2; timer = rng_15 % 50 + 20
action 0x11 idle-wander (0x004F8B90; only entered from actions 8, 0x14, 0x15, i.e. after being led by a herder):
  timer -= 1; if timer < 1:
     draw -> timer = (rng_a & 0x1F) + 0x80 (128..159); draw -> direction = rng_a & 7; draw -> if (rng_a & 3) == 0 [1/4]:
     animal_pick_dest(f, action=8, radius=2)   # short walk, arrive -> back to 0x11
  (a plain sheep never returns from 0x11 to 0x10 in the code read: hypothesis that this state only
   follows herder contact)
```
`animal_pick_dest(f, act, r)` (`FUN_004F83E0`, thiscall; ECX = optional exclusion rect, ignored when `*ecx == 0`):
```
requires the animal's tile to be plain meadow (terrain & 0x1D7FD80F == 0x800), else returns false.
route_bfs_meadow(x, y)  # 0x00587FB0 flood-fills meadow tiles from the animal -> g_grid_route_distance
repeat up to 100 times:                      # 2 draws per attempt
    dx = (draw1.rng_15 % (2r+1)) - r ; dy = (draw2.rng_15 % (2r+1)) - r        # uniform square, includes (0,0)
    t = tile + dy*228 + dx
    valid = no building at t and terrain&0x1000CA60 == 0x800 (plain meadow) and regrowth[t] >= 0x32 (50)
            and route_distance[t] != 0 (reachable over meadow) and (t not in the exclusion rect)
    f.dest = (x+dx, y+dy)
    if valid: f.action = act; return true
if all 100 failed and the last dest is non-zero: use that last (invalid) dest anyway, action = act, return true  # quirk, verified in code
```
Consequences (verified from the code, rates derived): graze 20..69 ticks (first 71); each graze expiry
has a 1/8 chance of leaving (expected about 8 graze periods, roughly 350+ ticks, standing on a meadow
tile); the leave sets the current tile's regrowth to 0, and the new spot must have regrowth >= 50 (meadow
passes add +15/16 per step-20 pass, so a bare tile is eligible again after 4 passes, "grown" 255 after 16-17),
within a 9x9 square (radius 4), over meadow tiles only. The animal walks 15 ticks/tile (sheep) / 20 (goat, cattle).
Non-meadow or building tile under it -> it dies (action 4). Walking never leaves meadow (route mode 15).
RNG: every "draw" below is one `random_next` step (31 LFSR iterations of rng_a/rng_b, the shared game RNG,
rng_history updated). Per graze expiry: 2 draws (stay) or 1 + up to 200 (leave) + (1 if no spot found).
Per idle-wander expiry: 3 draws (+ up to 200). Per action-6 expiry: up to 200.

### Wool / milk readiness — verified (disassembly of `0x004F8D80`; not decompiled by Ghidra)
`animal_month_tick(f)`, once per tick per sheep/goat/cattle, compares `Figure+0x13C` (named `god_attack_kind` in
the struct file, reused: the month number stored at creation by `figure_create` callers, e.g. `build_commit` `0x00498910`)
with the global `month` `0x0091EC08`:
```
if f.+0x13C != month:
    f.+0x13C = month
    f.ready_level (+0x92) += 9
    if ready_level >= 100:                  # unsigned byte compare
        ready_level = 100; f.+0x168 = 0
        if type == 0x4C (cattle) and 0x004F94F0(f): f.resource(+0x0B) = 2 (becomes a bull), f.+0x13C = 0,
              f.action = 9 (frozen), f.flags &= ~0x40000      # 0x004F94F0 not decompiled: what it checks is unknown
    else: f.+0x168 = 0
```
So readiness grows **+9 per month** (every game month, 16 cycles = 816 ticks; first increment when the month
number first differs from the creation month). A sheep/goat shorn/milked (readiness 0, `herder_take_from_animal`)
is ready again (>= 100) after **12 months** (0, 9, ... 99, 108 -> 100); a farm-placed animal starts at 50
(`build_commit` `0x00498910` sets `ready_level = 0x32` for tool-placed animals 0x31/0x32/0x4C) and is ready
after **6 months** (50 -> 104). Spawned animals (`animals_spawn` step 49) for cattle get ready_level 1.
Closes open question 1.

### Animal count limits and spawning — verified
Tool placement (`FUN_004F92A0`): a new sheep/goat is allowed only while the city has fewer than
`8 x (sheep farms / goat farms)` of that animal (`DAT_0091EB90<<3` sheep, `DAT_0091EB68<<3` goat), cattle
`8 x corrals (DAT_0091EBB8) - g_city_cattle`. `animals_spawn` `0x004F8E30` (cycle step 49): per kind, if
1 < count < 8 x farms (verified 10-28: `1 < local_20`, a lone animal never breeds): one draw, `rng_15 % 100 == 0` (1 per 100 steps) creates a new sheep/goat/cattle at the
position of the last-found animal of that kind; if count > 8 x farms the last-found animal gets action 4
(dies, timer 0). (`FUN_004F7BA0` counts live figures of types 0x31/0x32/0x4C not in action 4.)

### Horse ranch parts, placement and drawing (decoded 10-28, bugs.md 134)
Two buildings: the **ranch house** 0x85 (type table size 3, image SPR_B_RANCH_HOUSE, Zeus_General group 103, 723)
and the **corral** (paddock) 0x86 (size 4, SPR_B_RANCH_CORRAL, group 104, 759: one 238x136 picture, the same for
every orientation), linked `ranch.next_part = corral`, `corral.parent_part = ranch`, `corral.type_byte = 0x85`,
both with `+0xAC` = orientation (`FUN_00496CA0` case 0x85).
- Orientation: `DAT_00DA23C4` (minus view/2), 0 when the tool is picked (`build_tool_select` 0x00404330), turned by
  the player (as the gatehouse's). Corral anchor = ranch anchor + table `0x00637E60` (view 0):
  **o0 (+3, −1), o1 (−1, −4), o2 (−4, 0), o3 (0, +3)**: east, north, west, south of the 3x3, sharing the house's
  edge (o0: x+3..x+6, y−1..y+2).
- Placement (`build_commit` 0x00498910): the generic 3x3 test for the house, then `map_area_buildable` on the 4x4 at
  that offset (fail: 19:18); preview `FUN_004964B0` case 0x85 → `FUN_004A19C0(3, …)` (3x3 only, the ghost of the
  corral drawn red/green by the same rule elsewhere).
- Horses are created at `corral (+0x3A) + 0x0063365C[slot]`: (0,0) (2,0) (1,1) (2,1) (0,2) (2,2) for slots 0..5.
- `ranch_horse_pick_dest` (below) only accepts a tile of that corral whose second tile (`DAT_00847D00 +0x20/+0x24`,
  a pointer table, probably the figure's (+1, +1) neighbour) is the same corral and no figure stands on it, so horses
  never leave the corral. Oracle (working city, tick-0..400 dumps, 28 horse samples): ranch (76,60) o0, corral (79,59);
  every horse on x 79..81, y 59..61 (the corral's top-left 3x3: consistent with the (+1, +1) second tile).
  Screenshot: re/oracle/runs/ranch/ranch.bmp (scenario re/oracle/scenarios/ranch.txt): the fenced corral east of
  the stable, horses inside.
- Ours (sim/systems/ranch.py, 10-28): `build horse_ranch X Y [0..3|e|n|w|s]` (play mode: R), the same offsets,
  both parts by our generic area test; the corral's tiles are the ranch Building's in the occupancy grid
  (misc["corral"], misc["orient"]); horses created at the slot tiles, each hop = 100 tries of -4..+3 from the horse,
  accepted when the tile and its (+1, +1) neighbour are in the corral and no other horse stands there, path inside
  the corral. Checked: full.txt, 3 ranches over 360 days, 6480 horse samples, none outside, 27 tiles used (3 x the
  3x3), as the exe's dumps. Ranches of older saves get a corral (free) at the first orientation whose 4x4 is free
  (`ranch.adopt`, monthly, with a city message); without room they keep the old free-roaming horses.

### Ranch horses (type 43, in the horse ranch paddock) — verified
Not a grazing animal: they pace inside the ranch's horse corral part (building type 0x86 linked from the
ranch `next_part`). Created with action 6, timer 30 (see "Horse ranch" above).
```
action 6: timer -= 1; if < 1: ranch_horse_pick_dest (0x004D0140)
action 8: figure_move(f, 6); arrive (8): action = 7, timer = 30, anim 0; blocked (10): action 6; 9: re-route
action 7 (rest, 0x004D03D0): timer -= 1; if timer == 0:
     draw; if (rng_a & 3) == 0 [1/4]: ranch_horse_pick_dest -> action 8
     else: draw; timer = rng_15 % 50 + 20          # rest another 20..69 ticks, then retest
ranch_horse_pick_dest: up to 100 attempts, 2 draws each: dx = (draw1.rng_a & 7) - 4, dy = (draw2.rng_a & 7) - 4
     (range -4..+3); accepted if the tile at (dx,dy) belongs to the same ranch's paddock (type 0x86 and id ==
     ranch.next_part), the second footprint tile (offsets at DAT_00847d00+0x20/+0x24: unclear) is the same
     building, and no figure stands on it; the last attempt's dest is used if all fail (action 8 regardless).
```
So a horse rests 30 ticks, then on every expiry moves with chance 1/4 (otherwise waits 20..69 ticks);
expected rest about 30 + 3 x 44.5 = 164 ticks, then walks to a random free paddock tile within a 8x8 window at 15 ticks/tile.

### Boar (type 51) — verified structure, rates derived
Boars live in herds (formations 35+, created at map load by `FUN_004E0160` from the scenario's herd points:
7 boars per point, wolves 7 per point, `DAT_00641F70/78`). Each boar has a herd `formation`; the herd point is
formation `+0x76/+0x78` (set at creation, static as far as seen: hypothesis). Handler `0x004BD030` dispatches
to `0x0056B5D0` (0x10), `0x0056B550` (0x11), `0x0056B6C0` (7); the action-entry hook is vtable method
`0x0056B360` (vtable `0x005E4810`, object `0x00FEB54C`, found by scanning the exe) which sets
timers via `rand_range(lo,hi)` `FUN_0056B240` = `lo + rng_a & 0x7FFF % (hi-lo+1)`, one draw:
```
on entering action 0x10 or 0x11: timer = rand(51, 153)        (0x0056B520)
on entering action 7 (0x0056B680): home = herd_point + (rand(-4,4), rand(-4,4)) re-rolled up to 1000 times until the
                                    terrain is passable (0x00569D90), dest = home         (0x0056B420)
per tick f.+0x5C (named home_link_flag, a drifting "restlessness" counter, i16):
   action 0x11: += rand(3,10)       when timer < 0: next = 0x11 if flag < 1800 else 0x10   (re-enter -> new timer)
   action 0x10: += rand(-3,3) + 2   when timer < 0: next = 0x11 if flag < 1201, 0x10 if flag < 2000, else 7;
                                    also dies (action 4) if the tile is not walkable
   action 7:    += rand(-10,-3) + 3 ; figure_move; on arrival (8/10): next = 0x10 if flag < 1800 else 7 (pick a new home)
every tick in 0x10/0x11 when anim_frame == 1: if a hunter (53) is within 4 tiles (0x0056B740) -> action 0xC (turn on it)
```
Each `rand()` above is one RNG draw, so a boar in 0x10/0x11/7 costs 1 draw per tick (the counter step) plus 1 per timer re-roll. Net effect: the
counter climbs while the boar is idle, and a walk to a new spot (always within +-4 of the herd point) starts when it
passes 2000; walking pulls it back down. A quick simulation of this machine with 4-tile walks gives roughly
one new destination every 130 ticks and the boar walking about 35-50% of the time (hypothesis; the walk length is assumed).
Actions 0xB, 0xC, 0xE, 0xF, 0x16 are the hunt/fight/flee behaviours: decoded in "Hunting lodge" below ("Boar reaction to hunters").

### Wolf (type 59) — superseded
Full decode (10-28): military.md "Wolves". It corrects this section: roam offset +4 - (rng & 7) (-3..+4), herders
are feared, not attacked; sheep, goats and cows are the prey; the search covers 7 rings.
Packs of 7 at herd points. Handler `0x004BD4A0`; `home_link_flag` is here a set of four 4-bit "need" nibbles
(`0x00569E10` add-with-clamp, `0x00569F10` nibble > 6, `0x00569F50` nibble < 5), not a scalar. Idle states 0x10/0x11
decide the next action from those nibbles (`0x0056A130`, `0x0056A3A0`); entering idle sets timer
`rand_mod50 + 100` (100..149, `0x0056A1F0`) and a random facing. The roaming pick (`0x0056A460`): if within Chebyshev
distance 6 of the herd point: dest = pos + (rng & 7) - 4 per axis, up to 99 tries until the terrain is passable
and has the same elevation; else head back toward the herd point. Targets: see "Wolves attacking" under Hunting lodge.

### Herd refill (boar, deer, wolf) — verified (2026-10-27, `formations_pass` `0x004DF570`)
Herds regrow. `formations_update(arg)` (`0x004DDD30`) runs at cycle step 5 (arg 0) and step 29 (arg 1), 2 calls per
cycle (51 ticks), and ends with `formations_pass`. For every formation in use whose kind byte (`F+0x69`, set at map start by
`0x004E0160`) is 1 (wolf) or 2 (boar/deer), with `F+0x42 == 0` and `F+0x94 == 0` (not mobilised/away), the pass:
```
F = formation base 0x00DB7B40 + id*0x9C
F+0x04 = figure type (59 wolf kind 1, 51 boar kind 2)  # rewritten every pass from DAT_00641FA0 / DAT_00641F70
F+0x29 = target size = 7        (DAT_00641FA8 wolves, DAT_00641F78 boar/deer; constants in the exe data)
F+0x28 = live members, recounted by formations_refresh 0x004DE210 at step 5 only (figures of type 51/59 with state 1
         and figure+0x56 == this formation; a boar carcass, action 10, still counts until the hunter removes it)
if F+0x28 < F+0x29:                          # wolves also need (DAT_00641FAC == 0 or F+0x28 != 0); the flag is 0, so no effect
    F+0x75 += 1                              # per-herd counter, only counts while under strength
    if F+0x75 > 26: F+0x75 = 0; spawn ONE animal
```
- **Timer**: one new animal per 27 passes while under strength = 13.5 cycles = about 690 ticks (about 0.84 month; 16 cycles = 1 month)
  per herd, deterministic (no chance roll). The counter is not reset when the herd becomes full or when an animal is
  killed, so the phase carries over. An empty herd refills 0 to 7 in about 5.9 months. Each herd refills independently.
  Ours (11-02, bugs.md 424): wild.update / wolves.day once per pass at steps 5 and 29, the live count taken at step 5
  (formations_refresh); before, one daily call added 2 and spawned at >= 27 (14 days, not 13.5).
- **Cap**: 7 per herd (per formation, i.e. per herd point: up to 4 boar points, 4 deer points, 4 wolf points). The
  "pass" never removes animals above 7. Herds are never freed when empty (only kind-0 company formations are, in
  `formations_refresh`), so a wiped-out herd still regrows. (An extinct-herd guard exists for wolves only via `DAT_00641FAC`, which is 0.)
- **Where**: next to the herd point stored in the formation (`F+0x36`, `F+0x38` = x, y given to `formation_alloc_other`
  `0x004DDB80`), not next to a surviving member. Start at ring index `rng_a & 15`, scan up to 16 offsets for a tile
  with `FUN_00569D90(terrain) != 0` and no building, create there with `figure_create(type, ...)`. Boar/deer use
  offsets table `0x005F2518`, whose first 8 entries are (-2,1) (-2,0) (-1,1) (-1,2) (-1,-1) (-2,2) (-1,2) (-2,1) and the rest (0,0),
  so a new boar appears within 2 tiles west-ish of the point. Wolves test with `0x005F2518` but create with `0x005F2418`
  (small ring around the point; looks like a quirk, hypothesis that it is a bug).
- **New animal**: action 0x13, `formation = id`, `timer = 10`. Wolves stay hidden for 10 ticks (wolf handler case 0x13), boars
  have no 0x13 case and fall into action 0x10 at once. Boar/deer get `resource = F+0x7A` (0 = boar, 1 = deer variant,
  from which scenario table the herd came) and `home_link_flag = 0x708` (1800: restlessness starts high, so it wanders
  soon). Map-start animals (`0x004E0160`) have flag 0. It then roams within +-4 of the herd point (see Boar above).
- Sim (10-29): the RING table above (wild.py), start index `rng & 15` for a refill, the member index for
  the map-start seven (`0x004E0160` starts member k at entry k); a refill boar starts with restlessness 1800,
  standing (action 0x10).
- Map start puts 7 in each herd (`0x004E0160`): so a refill never overshoots, and with one hunting lodge killing about
  1 boar per few cycles (see Hunting lodge) the herd holds roughly 7 minus (kills in the last ~0.84 month x n).
- Open: whether the sandbox scenario's herd formations have any state making `F+0x42`/`F+0x94` non-zero (not seen).

### Bulls (cattle with resource 2) — partial
`figure_cattle` hands `resource == 2` to a function at `0x004CAA60` that Ghidra did not create (disassembled:
jump table `0x004CB2DC`): it reuses the same graze logic (calls `0x004F83E0`, `0x004F7C40`, `0x004F7DB0`) with route walking
(`0x004D1170`) in action 0x11. Not analysed further.

## Hunting lodge 0x2E (meat 3)
Step 31 — verified:
```
interval, hunters by pct: >=100: 1,3  >=75: 4,2  >=50: 16,1  >=25: 32,1  >=1: 64,0
if not 0x00EF6163: b+0x32 += 1; if b+0x32 > interval:        # strict
  b+0x32 = 0
  if cursed: b+0x3C = 0; stop
  if cart_ok(b) and b+0x3C > 0: cart of 100 meat (400 blessed), b+0x3C -= 100
  n = hunters; if 500 - b+0x3C < n*100: n = (500 - b+0x3C) / 100
  if b+0xA8 > 5: b+0xA8 = count of live hunters (53)
  while b+0xA8 < n and prey = 0x004D05F0(x, y, 1000, -1, 0) and hunter created (53):
      hunter.action = 0xC; hunter+0x0B = prey+0x0B; RNG step; hunter+0x36 = rng_e4 & 0x1F; b+0xA8 += 1
```
Hunter returning (`0x004BE8CD`, handler `0x004BE260`): `b+0x3C += 100` (no clamp in the handler).

### Hunting range, chase and kill (RE 2026-10-27) — verified from `figure_hunter` `0x004BE260`, `0x004D05F0`, `0x00588B20`
**Prey search `0x004D05F0(x, y, maxdist, variant, steal)`**: scans all figures (max 300 candidates): state 1, type 51
(`0x00569990`), not dying (action 4) and not already a carcass (action 10), `variant == -1` or `figure.resource == variant`,
and unclaimed (`bound_worker == 0`, or claimed by the searching hunter's own lodge). Then `route_find_listed_tile`
(BFS over the land route grid, mask `0x11D`, from the given tile; a 4-neighbour flood) returns the **nearest candidate
by walking distance**, accepted if its route distance <= `maxdist`. So **no radius around the lodge**: the lodge's call (step 31)
uses maxdist **1000** steps (more than the 228x228 map can need), the hunter's own re-search after a failed/finished
kill (action 6) also 1000. Limits are reachability over land (water, cliffs, buildings and walls that block the route grid cut
a herd off) and "unclaimed". Each hunter gets a boar to itself: the boar's `bound_worker` is set to the lodge when the hunter leaves
for it; a second hunter never picks a claimed boar (fewer boar than hunters = the extra hunters go home empty).
The lodge spawns a hunter only if a prey exists (`while ... prey = 0x4D05F0(...)` in the step-31 code above).
The hunter copies the prey's variant (`resource` 0 boar / 1 deer, see Herd refill) and afterwards only hunts that variant.

**Hunter handler states** (type 53, speed model col 8, route mode 3; gives up if the lodge `state != 1`):
```
0xC  hidden in the lodge, timer = rng & 0x1F (0..31 ticks) counts down -> action 6
6    (timer<1) prey = search(maxdist 1000, same variant)
        none:  action 0xB, walk to the lodge's road access; vanish on arrival (an empty trip yields nothing)
        found: dest = prey position, prey.bound_worker = lodge, action 7 (walk, pathfinder route; missile_target = prey)
7    figure_move. On arrival (dir 8) at the old spot: if prey invalid (gone, dying, carcass, other variant): action 6.
        else if Chebyshev distance to the boar < 2: STRIKE (action 0xD): boar.saved_action=boar.action, boar.action=0x12,
             boar.timer=100, both turn to face; otherwise re-route to the boar's CURRENT x,y (chase = re-target on every
             arrival/route-lost; route lost (dir 9) does the same). Blocked (dir 10): the hunter is removed.
0xD  12-tick shot animation (timer 12 plays the attack sound/effect), then boar.action = 10 (dead, carcass), hunter action 9.
        Once the hunter is adjacent the boar cannot escape: it is killed after those 12 ticks unconditionally.
9    walk to the carcass tile; if the carcass is still action 10 there: carcass removed (state 2), action 8
        (13 ticks "butchering"), then action 10: walk home. If the carcass vanished: action 6, timer 20 (hunt another).
10   walk to road access; on arrival `b+0x3C += 100` (via bay_amount) and the hunter is removed.
0xB  (returning empty or after a fail) every 12th tick (anim_frame wrap) searches prey again with maxdist **100**; if found it
     turns around (action 7). So a returning hunter picks up a boar within 100 steps of where it is.
```
Meat per kill: **100** (one load; `b+0x3C += 100`, stock max 500 as above), whatever the boar variant. Carcass lifetime: the boar's action
10 counts `timer` up and dies at 500 ticks, so a hunter must pick up within 500 ticks of the shot. A hunter does one kill and goes home;
the lodge sends the next on its interval. No timeout on a chase other than the prey becoming invalid (a boar may keep fleeing:
see below, but once within 1 tile the shot lands).

**Boar reaction to hunters** (`0x004BD030` actions 0xB/0xC/0xE/0xF/0x16; hypothesis for the flee destination): while idle (0x10/0x11) on
anim_frame 1 the boar looks for the nearest hunter within Chebyshev distance < 4 (`0x0056B740`, `0x0056B820`) -> action 0xC, which
picks by its restlessness counter `m = f+0x5C`:
```
m < 501        -> 0xF  stand still (timer), then re-check
501..1200      -> 0xE  flee (walks to a destination; m -= 1 per tick; re-check on arrival)
1201..1799     -> 0xF  stand still
m >= 1800      -> boar variant (resource 0): 0xB charge the hunter, then 0x16 melee; deer variant (resource 1): 0xE flee
```
Melee `0x0056BC30` (boar adjacent to a hunter): after the timer, a coin flip (`rng_a & 1`, or always if the hunter has `leader_figure != 0`):
heads: **boar dies** (action 10, hunter then collects it, action 9); tails: **the hunter is killed** (action 4). So a hunting trip against a
riled boar costs a hunter half the time (hypothesis: the chance of m >= 1800 while the hunter arrives is not computed; map-start boars
begin at 0 and refilled ones at 1800, so refilled boars are the aggressive ones; deer never fight).

**Hunters per lodge / frequency**: already in the step-31 block above (at 100 % staffing: one trip each cycle (51 ticks) slot "interval 1",
up to 3 hunters out, stock limit 500 - 100 per hunter out; at 50 %: interval 16, 1 hunter). Sustained meat is then
bounded by the herd, not the lodge: one lodge at full staff can kill more than the 1 boar per 690 ticks a herd regrows, so a
herd is depleted by a busy lodge and then limited to the refill rate (about 1 boar per 0.84 month per herd).

### Wolves attacking (short, `fig_handler_wolf` `0x004BD4A0`, `0x0056A9F0`) — superseded by military.md "Wolves"
On anim_frame 1 a wolf scans its tile and neighbours for victims: **shepherd (type 30) and goat herder (31)**, or cattle (76) with
`resource == 2` (bull/rancher variant: unclear), not dying; if one is found it raises "aggression" nibble 3 of `home_link_flag` by 2
(`0x00569E10`, cap 15; "> 6" triggers action 0xF, `0x00569F10`) and later chases it (0xB, `0x0056AF80`) and fights through
`figure_tile_contact`, summoning a god figure (`god_figure_spawn(4, ...)`, which god is unverified) at the sanctuary if one is complete. Sheep, goats
and ordinary cattle are only recorded as candidates (second output, unused by the handler read). **Hunters (53) are not wolf targets**
(the wolf search never tests type 53); wolves are not hunted by lodge hunters either (prey filter is type 51 only).
Confidence: medium (call graph read, outcomes of `figure_tile_contact` not followed).


## Fishing wharf "Fishery" 0x2C (fish 2)
Step 31 — verified:
```
rate by pct: 10, 8, 6, 4, 2 (pct < 1 -> nothing)
if cursed: rate = 0; b+0x54 = 0
if b+0xB6 (boat) == 0:
   if no water exit (0x004A3FD0, >= 8 connected water tiles): b+0x54 = 0; stop
   b+0x54 += rate
   if b+0x54 > 199: create fishing boat (25) at the water tile: b+0xB6 = boat, b+0x54 = 0,
       boat.action = 6, boat+0x36 = 10, boat+0x128 = 100, boat+0x2C/+0x2E = home water tile
if road exit and cart_ok(b) and b+0x3C >= 100: cart of 100 fish (400 blessed); g 0x00FEB1D0 += amount
```
So a new boat takes ceil(200/rate) cycles (20 at full staff). Boat (`figure_fishing_boat` `0x004B5F10`,
water_mode 1, read 10-28): action 6 = idle at its mooring (`+0x2C/+0x2E`, the wharf's water exit tile, see
"Shore buildings"); every 51 ticks it asks `0x004A40E0` for the fishing point (the 8 map points `0x00902BC4`/`0x00902BD4`)
with the smallest ship-route distance from the boat (`0x0058D500`); found → action 7 (sail there). Action 8 (fishing):
`timer` counts up to 408 / 816 / 1224 / 1632 / 2040 ticks by the wharf's pct (≥100, ≥75, ≥50, ≥25, ≥1; × 66/100 when
`god_sanctuary_active`), then action 0xB = sail back to the mooring. Action 10 (moored, unloading): `timer` up to
204 / 408 / 612 / 816 / 1020 by pct, then the wharf stock `b+0x3C = 100` (assignment, not addition;
`0x004B63A8`) and back to action 6. So the stock is set **at the wharf**, after the unloading wait (open question 4).
One catch = 1 load. The boat dies (action 4) when the wharf is gone, its `+0xB6` no longer points to it, or `ship_hp < 1`.

## Urchin quay 0x2D (urchin 1)
Step 31 — verified (`0x0048CFB0`, figure helpers `0x00430200..0x00430400`):
```
requires b+0x18 > 0
interval, max divers by pct: >=100: 1,1  >=75: 4,1  >=50: 8,1  >=25: 16,1  else: 32,0
if b+0x54 > 1: b+0x54 = 0
if not cursed: b+0x32 += 1; if b+0x32 >= interval:
   if b+0x3C > 499: max = 0
   if water exit:
      if b+0xC4 & 0x10: b+0xC8 += 1; if b+0xC8 > 2: clear 0x10 (else no diver)
      if b+0xA8 < max: create urchin collector (44) (owner 1), action via 0x004ABAF0(f, 6, 7); b+0xA8 += 1
      cart: if cart_ok and b+0x3C >= 100 -> 100 urchins (400 blessed); 0x00FEB510 += amount
```
Collector: dives ≥ 408 ticks (`0x004302D0`: the timer counts every tick of actions 7/8/9 and is checked at each
action 9's start; once ≥ 408 the dive plays its 16 frames: 488 ticks at the mooring by our frame reading, sim
work_ticks 488 since 10-30, bugs.md 220), returns, then after 200 ticks (`0x00430390` sets
`Figure+0x36 = 200`, `b+0x54 = 1`) `0x00430400` adds `b+0x3C += 100` (clamp 500), removes the
diver (state 2) and clears `b+0x54`.

## Timber mill 0x33 (wood 9)
Step 31 — verified:
```
requires road exit, not halted (0x004873F0), pct >= 1
cutters by pct: >=100: 3, >=75: 2, >=50: 2, >=25: 1, >=1: 1
b+0x32 += 1; if b+0x32 > 4:                       # every 5 cycles
   if cart_ok(b) and b+0x3C >= 100: cart of 100 wood (400 blessed), action 0x11
   n = cutters; if 500 - b+0x3C < n*25: n = (500 - b+0x3C) / 25
   if b+0xA8 > 5: recount wood cutters (55)
   if b+0xA8 < n and trees_exist 0x00B1E8F0:
       b+0x32 = 0
       if resource_search(mask 1 = trees, spawn tile) (0x0048CDB0):
           repeat: create wood cutter (55), action 6; RNG step; f+0x36 = (rng_e4 & 0x7FFF) % 30
           until b+0xA8 >= n
```
Cutter (handler `0x004BF060`): chops 408 ticks (`0x198`), cuts the tree (`0x004A81F0`),
returns: `b+0x3C += 25` (`0x004BF352`, no clamp). 4 trips per load.

## Mines: mint 0x30 (silver → drachmas), foundry 0x32 (copper → bronze 10), orichalc refinery 0xD3 (17)
Step 31 shared branch — verified:
```
miners, rate by pct: >=100: 3,6  >=75: 2,4  >=50: 1,3  >=25: 1,1  >=1: 0,0
mint (0x30):
  if b+0x3C (silver) > 199:
     if b+0x54 < 100: b+0x54 = min(b+0x54 + rate, 100)
     else: d = 100 (400 blessed); b+0x54 = 0; b+0x3C -= 200; treasury 0x00FE6A64 += d; 0x00FEB200 += d
  if cursed: b+0x54 = 0
foundry / refinery: if cart_ok and b+0x3C >= 100: cart of 100 bronze / orichalc (400 blessed)
miner limit: room = stock_cap(type) - b+0x3C (300 mint, 500 foundry/refinery)
  n = 0 if room < 1 else min(miners, room / 25)
if b+0xA8 > 5: recount miners (62)
if b+0xA8 < n and not cursed and resource_search(mask, spawn tile):
   spawn miners (62), action 6, RNG step each, f+0x36 = rng_e4 & 0x1F, until b+0xA8 >= n
masks: foundry 0x100002 (copper rock), mint 0x200002 (silver rock), refinery 0x300000
```
Miner (handler `0x004C1310`): works 408 ticks at the rock, returns, `b+0x3C += 25`
(`0x004C1B14`; the amount may be changed through the out-parameter of `resource_tile_search_call`
`0x004A85B0`: hypothesis). The mint therefore needs 8 miner trips per 100 drachmas.

## Marble quarry "Masonry shop" 0x31 (marble 11), black marble workshop 0xD5 (16)
Step 31 shared branch — verified (float code at `0x0048F8CA`):
```
if cursed: b+0x3C = 0; b+0x54 = 0
cutters = 1 if pct >= 25 else 0 (pct < 1 -> nothing)
period = trunc(100.0 / pct * 16.0)                # 16 at 100 %, 64 at 25 %
if god record 13 (0x00EF607C, Atlas: hypothesis) has a finished sanctuary: period = period * 66 / 100
if b+0x3C == 0: b+0x32 = 0
b+0x32 += 1
spawn_ok = False
if b+0x32 > period and b+0xA9 == 0 and b+0x3C >= 100 and cart created:
    b+0x32 = 0; cart of 100 (400 blessed) marble/black marble, action 0x11; b+0xA9 += 1
    spawn_ok = (b+0x3C == 300)
if b+0x3C == 0: old = b+0x33; b+0x33 += 1; spawn_ok = old > period / 8
room = 800 - b+0x3C; if room < cutters*100: cutters = ceil(room / 100)
if b+0xA8 > 5: recount; if b+0xA8 < cutters and not cursed and resource_search(0x20000 / 0x120000)
   and spawn_ok: spawn stonecutter (62) as above
```
Stonecutter: works 1632 ticks (1077 with the god record 13 sanctuary), returns, `b+0x3C += 800`
(one block = 8 loads). `+0xA9` (quarry carts out) is decremented by `figure_delete` `0x004DA250` when a cart
(figure 4, 9 or 0x24) of a 0x31/0xD5 is deleted. `+0x33` is never reset (only this `+= 1`, u8): once the quarry
has been empty for more than period/8 days in total, it sends a stonecutter on every empty day.
Sim (10-29, `economy.gather_day`): this rule, the quarry's cart made here (not by the generic cart dispatch);
timber mill and mines as above (counter reset only when cutters go out; workers capped by `room / 25` of
the stock alone).
Details in "Quarrying and mining: terrain" below (the block travels as a cart following him; he
unloads only into an empty lodge).

## Quarrying and mining: terrain and work animation (verified 2026-10-28, bugs.md 101)
Handler `figure_miner` `0x004C1310` (figure 62) serves all four mines; the home building type picks the
variant: foundry 0x32 copper 0x100002, mint 0x30 silver 0x200002, refinery 0xD3 orichalc 0x300000 (all 408
ticks, +25), quarry 0x31 marble 0x20000 / black marble shop 0xD5 0x120000 (1632 ticks, 1077 with the
god-13 sanctuary `god_sanctuary_active`, +800, route mode 0xB). Actions:
- 6 wait 10 ticks, then search (marble: passes 0xFE, 99, 0, then 99 without the neighbour test; ores: one
  pass), dest = the found tile (marble: the marble tile itself, he stands on it; ores: a free tile beside
  the rock, `+0x5C/+0x5E` = the rock tile). Nothing found: removed.
- 7 walk. On arrival (direction 8): ores: if another miner already works that rock (`0x004A8650`) back to
  6; marble: if another stonecutter in action 8 stands on the tile, back to 6. Then action 8, timer 0,
  facing: ores toward the rock; marble toward the tile in the search globals `0x00F13944/40` (his own
  tile unless anything wrote those globals since: about 100 functions (road access, spawns, searches) do, so in a
  running city the facing is arbitrary; oracle working city: direction 2 for both stonecutters; same tile gives
  direction 0). Play mode faces him into the deposit instead (export.marble_facing, bugs.md 112).
- The search (resource_tile_search 0x004A86E0) skips a tile with a figure of the miner's type on it (the tile
  list: one standing or working there, the searcher itself), not one another miner is only walking to: two
  stonecutters may pick the same tile, the later one searches again on arrival (oracle schools-A: 1894 to (95, 70)
  behind 1951, then (96, 70)). Ours (11-02, bugs.md 417): economy.marble_search when the wait ends (was: at the
  dispatch, excluding every stonecutter's target), walkers.route11 for the walks out and home (dest the lodge's
  road access; was: the nearest edge tile by a 4-way BFS path).
- 8 work: timer +1 per tick until > 408 / 1632.
  - **Marble, end of work**: the tile's regrowth (= quarry depth) 255 -> 100; 100 -> 0 if all 8
    neighbours have regrowth <= 100 (`regrowth_neighbours_below` 0x0049F120, count 0x004A6CA0); 0 stays 0.
    Then `0x0049B9E0` recomputes the marble images of every marble tile in the 5x5 square around him
    (`0x0049F1B0`, same rule as the map pass 0x00520920). He creates a **cart** (figure 4) at his tile
    with 800 marble (`+0x74`; resource 11, black 16), action 0x11 then 0x12 with `leader_figure` = him, so
    the block follows him home; he walks back (action 9 to the lodge road access).
  - Ores: no terrain change at all; action 0xD: 24-tick pause (sprite frame = timer/2), then action 9.
- 9 walk home. On arrival: ores add 25 to `+0x3C` and are removed. Marble: if the lodge stock `+0x3C`
  is 0, add 800 and remove; otherwise he **waits at the lodge** (anim frame 0) until it is 0 (oracle:
  stonecutter 1951 stood at its lodge with timer 1633 from tick ~2000 to 2500 while the stock was 100).
- 10/0xB/0xC: god-related escort branch (not needed for the sandbox).

Terrain effect per resource:
| resource | tile changed | field | stages | exhausted | regrows |
|---|---|---|---|---|---|
| marble / black marble | the worked marble tile (images of the 5x5 around it recomputed) | regrowth byte (0x20000 stays) | 255 untouched -> 100 shallow -> 0 deep (deep only when 8 neighbours are pits) | never (shallow and surrounded deep pits stay minable) | no |
| copper / silver / orichalc | none | none | none | never | n/a |
| trees (wood cutter 0x004BF060) | the tree tile | regrowth = 0 (stump image), flag 0x1 kept | stump -> tree | no (the tile regrows) | yes: `terrain_regrow` +4/+5 per day (cycle step 20), 255 after 51-64 days (map-terrain.md 5) |

Images (docs/play/terrain.md §2): untouched marble SPR_QUARRY (Zeus_Terrain group 205, 34 images, table
`T_MARBLE` 0x006375B0); when the T_MARBLE pattern is the interior one (k = 0) and regrowth != 255:
SPR_QUARRY_SHALLOW (204, 60 images) from table **`T_PIT` 0x00637830 (48 records)** with arr = "neighbour
regrowth > 100"; if regrowth < 100 and that also gives k = 0 (all neighbours pits): SPR_QUARRY_DEEP (203,
60) from `T_PIT` with arr = "neighbour regrowth > 0". Black marble: Poseidon_Loaded groups 48/49/50
(SPR_BM_QUARRY, SPR_BM_SHALLOW, SPR_BM_QUARRY_DEEP) (image ids 0xACD/0xACC/0xACB, black +0x5D63/5/7).
Check: this rule with the oracle's regrowth reproduces all 36 stored image ids of the working city's
6x6 deposit (138..143, 113..118), whose screenshot shows the stepped pit (ladders on the shallow rim).

Work animation (sprite selection at the end of the handler, SprMain group table `0x0153AD78`, 8 bytes
per group): frame `anim_frame` +1 per tick, wraps at 10 in actions 8/0xB, 12 otherwise; image =
group first + anim_frame*8 + (direction - view orientation) & 7.
| variant | walk / wait (6, 7) | die | work (action 8) | walk home (9) | pause 0xD (frame timer/2) |
|---|---|---|---|---|---|
| marble / black marble | 222 (11044) | 223 (11140) | **224 (11148), 10 frames x 8 dirs** | 222 (walks empty; the cart carries the block) | — |
| copper (bronze) | 42 (2595) | 43 (2691) | 46 (2807) | 45 (2711, carrying) | 44 (2699, 12 frames) |
| silver | 75 (3741) | 76 | 79 | 78 | 77 |
| orichalc (PoseidonImps, `0x01554600`) | 32 | 33 | 34 | 36 | 35 |
(group = (table offset - 4) / 8; a group falls back to group 0 when the loaded file has fewer groups.)
Wood cutter: chop/carry sets in docs/play/walkers.md (chop 4433, carry 4529).


## Resource search `resource_search_from_spawn` `0x0048CDB0` → `resource_tile_search` `0x004A86E0` (verified 2026-10-28, bugs.md 82)
No radius: the scan covers the whole map (`resource_tile_search_call` 0x004A85B0 passes 0, 0, W, H).
Every tile with `terrain & kind_mask == mask` is listed (off-map 0x80000 skipped; a tile with a gatherer of
the same figure type on it is skipped: 0x37 wood cutter for trees, 0x3E for rock/marble), then a BFS from
the spawn tile takes the first listed tile reached (nearest by walking distance; trees and ores
`route_find_listed_tile` 0x00588B20, route mask 0x11D; marble `route_search_area` 0x0058A4D0, mask 0x19C,
which adds regrowing marble 0x80). Lists flush every 3999 entries (best route distance kept).
- Trees (mask 1): the tree tile itself (the woodcutter stands on it) with regrowth >= param_3: the building's
  check (`resource_search_from_spawn`) passes 0, so stumps count; the woodcutter's own search (action 6, from his
  tile) passes 0xFF: grown trees only. A failed tree search clears `trees_exist` 0x00B1E8F0; the daily tree pass
  (`terrain_regrow` 0x004A7D30, cycle step 20) sets it again when a timber mill (state 1, workers) reaches a grown
  tree from its road access (`route_find_listed_tile`, the list in chunks of 3999). A mill sends cutters only while
  it is set. Stumps keep the tree bit 0x1 (regrowth < 255), so they block building and grazing like trees.
- Ores (0x100002 copper, 0x200002 silver, 0x300000 orichalc; kind mask 0x300002): the listed tiles are
  the neighbours of the rock tile in the order of table 0x005D9240 (N, NE, E, SE, S, SW, W, NW) that
  FUN_004A85F0 accepts (route & 0x1C, no building, the rock's elevation) and whose tile list does not start with a
  0x3E figure, each with its rock (the miner stands beside the rock, +0x5C/+0x5E = the rock); a rock with a 0x3E
  in action 8 on a neighbour whose +0x5C/+0x5E is that rock (0x004A8650) is skipped. If none: flag 0x00B1E8F2 = 1.
- route_find_listed_tile 0x00588B20: a flood from the figure (N, E, S, W, route & 0x11D, no limit) that returns
  the first listed tile it pops (a tile listed twice: its first entry). resource_tile_search runs it on every 3999
  entries (a later chunk wins only with a smaller route distance) and on the rest; a list that ends exactly at a
  flush returns nothing (exe bug, kept).
- Figure type: the skip tests look at the type (0x37 woodcutter; 0x3E for stonecutters and ore miners alike).
- Ours (11-02, bugs.md 420): economy.resource_search / _listed_pick (walkers.listed_bfs), send_gatherers checks from
  the road access and sends the figures without a target; each searches when its wait ends (walkers.gatherer task
  "search") and walks by route mode 3 (walkers.route3: dest must be land, roads 0x0058A6C0 trace4/8, else
  route_distance trace8); woodcutters onto the tree, miners beside the rock; arrival: a woodcutter whose tile is no
  grown tree or has another woodcutter in action 8 searches again on its next call, a miner whose rock is worked
  (0x004A8650) after 11 calls; ore miners pause 25 ticks (action 0xD) before the walk home; both go home to the
  road access by route mode 3. Oracle: tools/oracle_gatherers.py (schools-A woodcutters: same trees),
  tools/oracle_miners.py (run 1M-miners: a foundry and a mint in a poked field): the same tiles and re-searches,
  the walks start late by the day's step (ours' spawns at step 50, the exe's at 31: TODO "Daily systems").
- Marble (0x20000, black 0x120000; kind mask 0x120000), four passes with minimum regrowth 0xFE, 99, 0,
  99 (last pass with param_11 = 1). An untouched tile (regrowth 255) qualifies only if all 8 neighbours
  are marble of the same kind (interior tiles); regrowth 100 (a shallow pit) only if the pit has 8+
  neighbours below 100 (`regrowth_neighbours_below` 0x004A6CA0, skipped in the 4th pass); regrowth 0
  (deep pit) if 8+ neighbours are 0. The sim keeps marble untouched, so only the interior rule applies.
- Placement does not test the resource (build_commit 0x00498910 has no branch for these types,
  buildings.md §5): a timber mill, quarry, mine or refinery can stand anywhere; it just sends no one
  while no tile is reachable.

## Workshops: winery 0x35 (grapes→wine 21), olive press 0x36 (olives→oil 20), sculpture studio 0x37 (bronze→sculpture 19), armory 0x87 (bronze→armor 18)
Input code `+0x12`: winery 4, press 5, sculpture 3, armory 3 (`0x00493E70`). Input stock `+0x3C`,
capped 300 (sculpture 400). Progress, step 20 — verified (`0x00485360`):
```
threshold = 320 if b+0x12 != 0 else 160                     # 0x004855D0
needs_input = b+0x12 != 0 and b+0x3C < (400 if type == 0x37 else 100)   # 0x00485310
require b.state == 1, b+0x43 != 0, b+0x18 > 0, b+0x40 > 0, not needs_input
if b+0xAF: b+0xAF -= 1; stop
if b+0xAB: b+0xAB -= 1
b+0x54 += pct / 10;  if b+0x54 > threshold: b+0x54 = threshold
```
Cart, step 31 (same branch as farms) — verified:
```
if cart_ok(b) and not cursed and b+0x54 >= threshold:
    amount = 400 if type == 0x37 else 100;  if b+0xDB: amount = max(amount*4, 400); b+0xDB = 0
    b+0x54 = 0; if b+0x12 and b+0x3C: b+0x3C -= (400 if type == 0x37 else 100)   # 0x00485610
    cart of `amount` of b+0x43  (action 0x11 for sculpture)
if cursed: b+0x54 = 0
```
At 100 % staff: 32 cycles (2 months) per load. The sculpture studio consumes 400 bronze and ships
400 sculpture units per piece. The step-20 progress also runs (harmlessly) for other non-excluded
producers with `+0x43 != 0` (timber, foundry, quarry, refinery, black marble, hunting, horse ranch,
lodges), capped at 160 (320 with input); only the four workshops above read it.

## Chariot workshop 0xD4 (chariots 22) — Poseidon
Step 31 — verified for the production part:
```
if chariots not halted (0x00FE933A == 0):
  rate by pct: 10, 8, 6, 4, 2 (pct < 1 -> none)
  if pct: chariot_workshop_buy_horses(b) 0x00495B20     # sends a buyer (figure 37) for horses when b+0x74 < 201
          if b+0xDC < 400 and b+0x3C (wood) >= 100:
              b+0x54 += rate; if b+0x54 > 319: b+0x54 = 0; b+0xDC += 100; b+0x3C -= 100; 0x00FE980C += 1
```
How finished chariots (+0xDC) and horses leave the workshop (verified 2026-10-29): **no cart**. Case 0xD4
spawns none (nor does the ranch 0x85), so neither good ever reaches a storehouse or post. Production does not
use horses up. Horses come in through the workshop's own buyer: `chariot_workshop_buy_horses` 0x00495B20 counts
+0x32 up to the 2/3/4/5/10 delay, and if +0x74 < 201 and no buyer (+0x2C, fig 0x25) is out, it sends one to
`vendor_find_source(ws, 2, .., slot 15)`, the nearest ranch within 40 tiles. That buyer takes
`buyer_horse_loads` 0x004CEB40: up to 4, room 400 - +0x74 - carried. Chariots leave only with the Poseidon
horse trainer's buyer (agora stall 73; `vendor_find_source` kind 2 lists chariot works with +0xDC > 0 and
+0x74 > 0, and then skips ranches). `buyer_chariot_loads` 0x004CE760 takes min(+0xDC, +0x74)/100 loads, up to 4;
for each load 0x004CE630 removes 100 chariots and 100 horses and spawns one assistant for slot 15 (horse) and one
for slot 19 (chariot). The assistants never add slot 19 (0x004BC05F), so the agora gets the horses only and the
chariots disappear. The chariot vendor (215) is not in the vendor table: we found no exe consumer for it, so
ours stays empty. Military use of chariots: none found. Ours: sim/systems/economy.py `chariot_workshop`,
`buy_horses`, and the buyer branch in `cart_arrived`.

## Horse ranch 0x85 (horses 15, eats wheat)
Step 31 — verified (`0x0048CFB0` case 0x85):
```
food = model_building_value(0x85, 8)                  # 10 (column resource_used)
max_horses = pct * 6 / 100
horses = live horse figures (43) in slots b+0x56[0..35]; dead slots cleared; b+0xA8 = horses
if horses > max_horses: first horse in slots 0..5 that isn't dying gets action 4 (leaves); 0x00FE97F0 -= 1
if month_tick == 15:                                    # last cycle of each month: feeding
   if b+0x3C < horses*food:
       if b+0x3C < 1: up to 2 horses get action 4 (leave)
       else: for each horse slot 0..5: if b+0x3C < food: that horse leaves, stop;
             else b+0x3C = max(b+0x3C - food, 0); 0x00FEB534 += 1
   else: b+0x3C -= horses*food; 0x00FEB534 += horses
   if pct > 0 and month is even and horses < max_horses:
       n = 1; if blessed: n = min(6 - b+0xA8, 4); if b+0x3C < n*50: b+0x3C += n*50
       if b+0x3C > 49 and (b+0xA8 + 1)*food*6 <= b+0x3C:
           for free slots (max 6), while n: create horse (43) at corral b+0x3A + offset table 0x0063365C,
             b+0xA8 += 1; b+0x3C -= 50; 0x00FE97F0 += 1; horse.action = 6, +0x36 = 30
```
So a ranch breeds at most one horse every 2 months, paying 50 wheat, and keeps ≥ 60×(horses+1)
wheat in stock. All of it needs road access (`+0x18 >= 1`). The excess test runs every day (one horse a day);
feeding and breeding on day 15, the month's last, with that month's number (Jan = 0: breeds at the end of
Jan, Mar, ...). Sim: `economy.ranch_day` (10-29; it was monthly at the next month's start, all excess and all
unfed horses at once, and its even-month test was one month off). Horse transfer to vendors: see storage-distribution.md.

## Shore buildings: fishing wharf 0x2C, urchin quay 0x2D, trireme wharf 0x88 (decoded 10-28, bugs.md 131)
The original builds them **half over water**; the dock (0x3C) is in trade.md "Dock placement".
**Placement** (`FUN_004964B0` preview, `build_commit` 0x00498910 commit). The anchor (x, y) is the cursor tile
(view 0; other views shift it, then the orientation index is turned back by view/2). The player never picks the
orientation: the test tries orientations 0, 1, 2, 3 in turn and **the first that fits wins** (`DAT_00DA23B8`, stored at
`Building+0xAC` by `FUN_00496CA0`).
- 2x2, wharf/quay (and the dock's pier) `FUN_004A10C0(x, y, 1, 0)`: tiles `0x005F1968` = (0,0) (1,0) (0,1) (1,1),
  per orientation a land(0)/water(1) flag each (`0x00637E84`), plus 6 tiles in front that must be water
  (`0x00637EC4`/`EE4`/`F04`, two per orientation each):

  | o | water half | front tiles (all water) | image |
  |---|---|---|---|
  | 0 | row y (north, −y) | (−1,−1) (0,−1) (1,−1) (2,−1) (−1,0) (2,0) | first + 0 |
  | 1 | column x+1 (east, +x) | (1,−1) (2,−1) (2,0) (2,1) (2,2) (1,2) | first + 1 |
  | 2 | row y+1 (south, +y) | (−1,1) (2,1) (−1,2) (0,2) (1,2) (2,2) | first + 2 |
  | 3 | column x (west, −x) | (0,−1) (−1,−1) (−1,0) (−1,1) (−1,2) (0,2) | first + 3 |

  Land tiles: not water or beach (`& 0x10004` → this orientation fails), and no road 0x40, nothing of `0x5361227`
  (trees, rocks, rubble, walls…), no building bit 8 (each counts as an obstacle → refused). Water tiles: water bit 4,
  no bridge/road 0x40 and no bit 1 on them. Result 0 = buildable; 1..4 = obstacles; 999 = no orientation fits.
  Refused: message 19:23 "Find a good site along the water". No sea-access test for the wharf and the quay.
- 3x3, trireme wharf `FUN_004A14B0(x, y, 1)` (tiles `0x005F198C`, flags `0x00637F24`, 2 front tiles `0x00637FB4`):
  o0 row y water, front (−1,0) (3,0); o1 column x+2, front (2,−1) (2,3); o2 row y+2, front (3,2) (−1,2); o3 column x,
  front (0,−1) (0,3). Same land/water tests (land also refuses `0x10000000`). Then `building_water_access_check`
  0x00485670: a tile of the size-3 edge ring (`g_adjacent_ring` 0x005F1680, no corners) is water reachable by ship from
  the sea entry (`0x0058D500` on grid_ship), else 19:25 "This lake has no access to the sea"; and at most 6 trireme
  wharves (`DAT_00DB7B34 > 5` → 19:29 "You have a full fleet of warships").
**Footprint** (`FUN_004A1350` 2x2, `FUN_004A1650` 3x3): every tile gets the building bit 8 and the building id; water
tiles keep their water bit (land tiles are masked `& 0x93872F98`). Image = group first + orientation (`FUN_00495390`,
view-adjusted): SPR_B_FISHERY (Zeus_General group 53, images 544..547), SPR_B_URCHIN_COLLECTOR (115, 548..551),
SPR_B_WARSHIP_WHARF (94, 719..722, 3x3); type table sizes 2, 2, 3.
**Mooring** (`building_water_exit` 0x004A3FD0(x, y, size)): the first tile of the size's edge ring, in the ring's order
(0,−1)…(size−1,−1), (size,0)…(size,size−1), (size−1,size)…(0,size), (−1,size−1)…(−1,0), that is water, has no
building bit 8 (so not the wharf's own water half) and whose **8 neighbours all have the water bit 4**
(`FUN_004A1FF0(4)` sets one flag per neighbour N, NE, E, SE, S, SW, W, NW; `FUN_004A6CA0` counts them; > 7 passes; the
wharf's own water half keeps bit 4, so it counts). The returned tile comes from a parallel table `0x005F1B38` with the
same offsets as the ring. A tile beside the water half touches the land half, so it never passes: the boat moors
straight out in front of the water half (2x2: o0 (0,−1), o1 (2,0), o2 (1,2), o3 (−1,1), the first one in ring order;
3x3 the same, e.g. the working city's o2 trireme wharf (114,66) → (116,69)). Corrected 10-29 (bugs.md 173): we had read
the test as ">= 8 connected water tiles", which put boats and triremes beside the wharf. Oracle: every fishing
boat home (Figure+0x2C/+0x2E) and the trireme of the working-city dump match (`python3 tools/oracle_moorings.py`:
10/10, the old rule 4/10). The boat is created there and that tile is its home
(`+0x2C/+0x2E`), so it moors in front of the pier; the quay's urchin collectors (figure 44, water_mode 3 = shore band
0xFB of grid_ship only) start from the same tile.
Ours (sim/systems/shore.py, 10-28): the same tests, tiles, orientation order, footprint (water tiles in the occupancy
grid), mooring and dock berth; the boat fishes 408..2040 and unloads 204..1020 ticks (sim/systems/walkers.boat), rests 51.
Land-placed wharves of saves from before 10-28 keep the old connected-water rule (`water_exit(..., connected=True)`);
saves from before 10-29 get their boats' homes and moored triremes moved to the exe mooring on load (`shore.remoor`).
Differences: a water tile already taken by another building is refused (the exe does not test bit 8 there); the sea
access test floods plain water from the sea entry (not grid_ship's 8-neighbour rule); the `god_sanctuary_active` x0.66
fishing time is not modelled; a dock whose exe berth tile is not open water uses its mooring. `build KEY X Y n|e|s|w`
(play mode: R) can ask for one orientation, which the exe never does. Saves from before keep their land-placed wharves
and docks with the old rules (no conversion; `shore.is_shore(b)` tells them apart).
Oracle: re/oracle/runs/shore/ (scenario re/oracle/scenarios/shore.txt): the working city's 9 wharves (dump: e.g.
(77,95) o1, (76,97) o2, (74,99) o1) and its trireme wharf (114,66) o2 all have exactly this land/water split.

## Artisans' guild 0x38 (no goods)
Step 20: if active, employees > 0 and (`+0x12 == 0` or `+0x3C > 0`): `+0x54 += pct/10`, cap 320.
Step 31 `0x0048CB30`: sends artisans (figure 58) to construction sites (map-buildings scope).

## Cross-references (other subsystems)
- `building_create` `0x00493E70` (map-buildings): sets +0x43/+0x12, granary +0x56 = 3200.
- `house_find_road_access` `0x004A3B40`, `building_water_exit` `0x004A3FD0`, `resource_tile_search_call`
  `0x004A85B0`, terrain bit 0x10000 (map-buildings/terrain).
- Labor `+0x40`, `+0x18` (population-housing). God blessing/curse `+0xDB`, `0x00EF60B0`, god records
  (religion). Gatherer movement and the handlers' state machines (walkers).
- Trireme wharf 0x88 (wood → triremes) and `0x84` are military; only the stock cap is listed here.

## Open questions
1. (answered) Sheep/goat readiness regrowth: +9 per month, see Animal movement (RE).
2. Who sets the farm timers `+0xA9/+0xAA/+0xAB` and `+0xAF` (irrigation/flood, Demeter?).
3. `0x00EF6163` (global stop) meaning; `0x004F19E0`.
4. (answered 10-28) Fishing boat: the `+0x3C = 100` assignment happens at the wharf, after the unloading wait (action 10).
5. Quarry `+0xA9` decrement and `+0x33` reset (probably the cart/miner handlers).
6. (answered 2026-10-29, "Chariot workshop" above) Chariot workshop: horses are not consumed by production, no cart ships chariots, and the horse trainer fetches chariot + horse together.
7. Walker handlers (`0x004AE160`, `0x004AECF0`, `0x004B5F10`, `0x004BE260`, `0x004BF060`,
   `0x004C1310`, ...) are not functions in the Ghidra project; they should be created so they decompile.
