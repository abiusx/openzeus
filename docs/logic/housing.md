# Housing: applying evolution, goods, capacity

Status: **verified** unless marked. Addresses: GOG `Zeus.exe`. Builds on
[housing-evolution.md](housing-evolution.md) (the requirement check). Field names:
[../re/structs.md](../re/structs.md) + `re/structs/population-housing.tsv`.

## Summary
Once per 51-tick cycle (cycle step 39) every house runs a per-type handler. It asks the
desirability gate and the requirement check; a pass ("+1") changes the house type by one level at
once; a failure ("-1") must repeat 3 times in a row (common houses) or 10 times (elite) before the
house drops one level. Changing type only changes `type`, `house_level` (= type−2) and the sprite;
capacity is read from the model each time it is needed, so a house that drops a level becomes
overcrowded and the surplus is evicted at cycle step 24 (see [population.md](population.md)).
There is no merging of houses: a common house is one building whose size is `b+0x03`; an elite
house is 4×4 drawn as four 2×2 sprites. Houses eat food once a month and wine/oil/fleece twice a
month; horses eat one unit of food a month.

## 1. Which function really applies evolution
- `0x00564560` (`building_problem_flags_update`) and `0x00570B20` (`building_info_panel_prepare`)
  call `house_evolve_check 0x00484660` only to show the reason code / problem overlay; they do
  **not** change the house. **verified**.
  - `0x00564560` writes `b+0x110` problem bits. Houses: 1 = check says devolve, 2 = no occupants
    (returns), 4 = crime `b+0xF4` > 80, 8 = plague `b+0x85`, 0x10/0x20 = `b+0x48`/`b+0x46` > 800.
    Other buildings: 0x100 industry halted (`0x004873F0`), 0x40 no labor access (`b+0x18`<1) or no
    employees, 0x80 employees < model col 5, 0x200 (raw material, types 0x37/0x88), 0x400 sanctuary
    stage < 5. Caller: tile tooltip `0x00565360` (UI).
- The simulation uses `houses_evolve 0x004FE290` (cycle step 39, i.e. once per 51 ticks, 16 times
  per month) with the requirement check **`house_requirements_met 0x004843D0`**, not `0x00484660`.

## 2. `houses_evolve` `0x004FE290` — cycle step 39
```
0x00FEAD80 = 0; g_house_food_fail_count(0x00FEAD8C) = 0          # 0x00484D10
0x0091EA08 = 0
for i in 1..3999:                         # global loop index 0x0091EC78
    b = buildings[i]
    if b.state == 1 and 2 <= b.type <= 14:
        building_validate_position(i)     # 0x00494D40: if tile/x/y disagree with grid 0x00D26E98,
                                          #   rescan grid; not found -> state = 4
        g_house_evolve_result(0x0091EC28) = 0
        HANDLER[b.type]()                 # table 0x0063B91C (index = type)
        if month_tick(0x0091EC0C) in (0, 7):
            house_consume_luxuries(i)     # 0x00484C50, uses the level AFTER the handler
if 0x0091EA08: 0x00587B30(); 0x00502EB0()  # redraw/route refresh (not traced)
```

### Handler table `0x0063B91C`
| type | house | handler | on +1 | on -1 (counter `b+0x82`) |
|---|---|---|---|---|
| 2 | Hut | `0x004FE360` | → type 3 | nothing (no counter) |
| 3..7 | Shack..Apartment | `0x004FE3F0` … `0x004FE750` | → type+1 | 3rd consecutive → type−1 |
| 8 | Townhouse | `0x004FE820` | none (top) | 3rd consecutive → 7 |
| 9 | Elite vacant lot | `0x004FE8E0` | — | — (calls `0x004843D0(b,2)`, result discarded) |
| 10 | Elite devolved | `0x004FE900` | → type 11 | counter wraps 11→0, never devolves |
| 11..13 | Residence..Manor | `0x004FE9C0` … `0x004FEB60` | → type+1 | 10th consecutive → type−1 (11 → 10) |
| 14 | Estate | `0x004FEC30` | none (top) | 10th consecutive → 13 |

Common handler (types 3..14 except 9, 10), exact:
```
if house_editor_freeze(): return            # 0x00484250: if 0x00B1E8BC != 0 { if b+0x04 == 0:
                                            #   house_set_type(b, b.type) }; return 1
r = house_desirability_gate(b)              # 0x00484360: -1 / 0 / +1
if not house_requirements_met(b, 0): r = -1 # current level
elif r == 1: r = house_requirements_met(b, 1)   # next level, 0 or 1
if r == -1:
    if b.devolve_counter <= T: b.devolve_counter += 1; return      # T = 1 common, 8 elite
    b.devolve_counter = 0; house_set_type(b, type-1)
else:
    b.devolve_counter = 0
    if r == 1 and type not in (8, 14): house_set_type(b, type+1)
```
- Types 2 and 3 first require `b.occupants (+0x1C) > 0`, else return (no evaluation).
- Type 2 (Hut): `r == -1` → return (no counter, no change); `r == 1` → type 3.
- Type 10: `r` starts at **1 without the desirability gate**; `requirements(b,0)` (row 8, all zero)
  false → counter++ (if counter > 10: counter = 0); else `r = requirements(b,1)` (row 9); r == 1 →
  type 11. So an elite lot becomes a Residence as soon as level-9 goods/services are met, whatever
  the desirability; the Residence then devolves back after 10 gated failures if desirability is
  too low.
- So: evolution is immediate on the first passing check; devolution needs 3 (common) / 10 (elite)
  consecutive failing checks = 3 or 10 cycles (≈ 153 / 510 ticks). **verified** (disassembly).

### `house_requirements_met(b, step)` `0x004843D0` → bool
`L = b.house_level + step`; reads cols 3,2,4,8,7,12,9,10,11 of row L, then fails if:
water (col3≠0 and `b+0x35`==0); culture `b+0x80` < col2; education (col4≠0 and `b+0x6C`==0);
food types held < col8 (also `0x00FEAD8C += 1`); arms `b+0x6A` < col12; wine `b+0x64` < col11;
fleece `b+0x68` < col9; oil `b+0x66` < col10; horses `b+0x72` < col7. Food types held = number
of entries of the city food list (§4) whose house slot is non-zero.
Difference with the UI check `0x00484660`: education is tested as "non-zero" (the model only has
0/1, so same result); no reason code is written.

### `house_set_type(b, new_type)` `0x00494EA0`
```
old_common = 2 <= old.type <= 8; old_elite = 9 <= old.type <= 14
b.type = new_type; b.house_level = new_type - 2
if new_type in 2..8:
    if not old_common: restore old type/level; return   # common<->elite never switches
    image = house_level_image(level) (0x00494E40 via 0x00494E70) + (tile_random 0x00CA7FF8 & 1)
    0x004A04B0(b, x, y, size=b+0x03, size, image, 8, 1)  # place sprite / footprint
else:
    if old_elite: elite_house_place_sprites(b)           # 0x004FECF0
    else: restore old type/level
```
`elite_house_place_sprites 0x004FECF0`: image base from `0x0063B934[type]` (Zeus) or
`0x0063B94C[type]` (Poseidon); four 2×2 pieces placed at offsets `0x0063B988` chosen by view
orientation `0x00DA2F88`. Pure graphics. Occupants, goods and counters are untouched by a type
change. **verified**.

### Empty houses revert to lots `house_reset_to_lot` `0x00495000`
Common house (2..8) → type 2, level 0, special "vacant lot" image (+0x10000). Elite (9..14) →
type 10, level 8 + elite sprites. Called when emigration empties a common house
(`0x00486E40`) and from placement `0x00496CA0`. Elite houses emptied by emigration are **not**
reset. An immigrant/homeless arriving at an empty house sets type 2 (common) or type 11
(elite lot type 9/10/11) — see population.md.

## 3. Goods consumption
### Luxuries — `house_consume_luxuries(b)` `0x00484C50`, twice a month
Runs inside `houses_evolve` when `month_tick 0x0091EC0C` is 0 or 7 (16 cycles per month), only if
`b.occupants != 0`. For current level L (after this pass' type change):
```
for (good, col) in [(wine,11), (fleece,9), (oil,10)]:   # this order
    n = house_param(L, col); if n > 0: b.good = max(0, b.good - n)
```
Arms and horses are never consumed here.

### Food — `houses_eat_food` `0x0048B8D0`, monthly
Called from `month_advance` in the month-end block (after `0x00566C00`, `0x00488250`,
`0x00488740`, `0x00483B20`, `0x00462110`). First calls `cycle_city_buildings_17 0x0048B0D0`
(city food totals). Then for each building `1..max` with state 1 and `is_house (b+0x05)`:
```
nf    = house_param(L, 8)                    # food types needed
amt   = b.occupants * 25 / 100               # 25 = food_rate 0x004E5EF0 (constant)
if nf > 1: amt = amt / nf
horse = 1 if b.horses != 0 else 0
b.food_types_eaten(+0x7F) = 0
if cheat 0x00902C0C:  b.goods_0(+0x54) = amt; b.food_types_eaten = 1; continue
if nf > 0 or horse:
    for res in city_food_list (0x010DFDAC, count 0x010DFDA8), skipping 0 entries:
        s = slot(res)
        if b.slot[s] >= amt: b.slot[s] -= amt; total += amt; eaten += 1
        elif b.slot[s] != 0:  b.slot[s] = 0;   total += amt; eaten += 1   # counts full amt
        if eaten >= nf: break                 # tested after every non-zero list entry
    if horse:
        for res in city_food_list: take 1 unit from the first slot holding >= 1 (partial: a
            non-zero slot smaller than the rest is emptied and the rest carried on)
        if still owed: b.horses -= owed      # horses starve
0x00FEB02C = total     (food eaten this month); then 0x00523710(0)
```
Notes: amt may be 0 (occupants < 4) and still "eats" a held type. With nf == 0 and horses the
first non-empty food still loses `amt` (literal behaviour). `b+0x7F` (food types eaten) feeds health
(`0x00566C00`) and sentiment (`0x00566F20`).

### Slot layout (resource id → house slot, `b+0x54 + 2*slot`) — from `0x004843D0` switch
| res id (text group 23) | good | slot | offset |
|---|---|---|---|
| 7 | wheat | 0 | +0x54 |
| 6 | onions | 1 | +0x56 |
| 5 | carrots | 2 | +0x58 |
| 4 | cheese | 3 | +0x5A |
| 3 | meat | 4 | +0x5C |
| 1 | urchin | 5 | +0x5E |
| 2 | fish | 6 | +0x60 |
| 8 | oranges | 7 | +0x62 |
| 21 | wine | 8 | +0x64 |
| 20 | olive oil | 9 | +0x66 |
| 14 | fleece | 10 | +0x68 |
| 18 | armor | 11 | +0x6A |
| 15 | horses | 15 | +0x72 |
| 22 | chariot | 19 | +0x7A |

City food list `0x010DFDAC`: built by `0x005BAAF0` (economy) — food resource ids 1..8 in
ascending id order that the city produces, imports, stores or is allowed (criteria not traced:
hypothesis). It decides which foods count for "food types held" and the order of eating.

### Inventory caps — goods delivered by the agora vendor `0x0040D160` (walkers/economy own the walk)
Houses within x±2, y±2 of the vendor's position that are houses with occupants > 0 or elite
(type 9..14):
- Food: `held = sum of food-list slots (0x004FF7B0)`; cap = 2·occupants (80 if empty); per food
  type batch = max(1, occupants/2) (20 if empty); give min(batch, cap−held, vendor stock), only for
  res 1..8.
- Non-food, records 1..5 of table `0x005E8578` (stride 0x34; Poseidon record 5 at `0x005E86B0`):
  fleece (col 9), oil (col 10), wine (col 11), arms (col 12), horses (col 7). Target =
  col of the **next** level (L+1; L itself for 6 and 12) ×4 if `b+0x03` > 1, ×2 if elite; empty
  house and fleece/oil: target 10. If the vendor holds that good: target ×2, then capped by col 6
  (horses) / col 13 (armor) of the current level; give min(target−held, stock/unit) with unit = 100
  for arms and horses (vendor stores ×100), else 1. Vendor field `+0x9E+2*rec[7]` = 10 every visit.

## 4. Capacity
`capacity(b) = house_param(level, 17)` (Hut 8, Shack 16, Hovel 24, Homestead 32, Tenement 40,
Apartment 48, Townhouse 60; Residence 6, Mansion 10, Manor 16, Estate 20 in Normal). Exceptions:
type 9 (vacant elite lot) uses row level+1 = 8 in step 22, row 9 on arrival of settlers; a house
with plague (`b+0x85` ≠ 0) has capacity = its current occupants (step 22). Recomputed every cycle
at step 22 (population.md §2).

## 5. Crime counter per house (`b+0xF4`, i32) — `0x00566F20`, twice a month
Called by `city_sentiment_update 0x005671A0` (month cycles 0 and 8). For each house (state 1,
is_house): if occupants == 0 → crime = 0. Else, common houses only (type < 9 or > 14):
```
if population > 349 or 0x00FEB0DB:
    if Dionysus sanctuary finished (god record 0x00EF5FE0): crime -= 20
    else: crime += house_param(L,14) + (40 - sentiment(0x00FE6A68)) / 2
crime = max(crime, house_param(L,15)); crime = min(crime, 100)
```
The same loop maintains a hunger counter `b+0xCC` (u8): if `b+0x7F` == 0 → +1 (max 3), sentiment
term −1/−2/−3; else term +2 and counter 0; the rounded average is a sentiment component
(military-sentiment agent). Col 20 (disease) and col 16/19: **no read found** (no `house_param`
call with these columns, scanned all call sites) — disease must come from another mechanism.

## Open questions
- `0x00B1E8BC` (freezes evolution; hypothesis: map editor). `0x0091EA08` setter.
- Exact criteria of the city food list `0x005BAAF0` (economy).
- `b+0x03` value for common houses (2 expected): set from `0x005F6368[type*8]` at creation.
