# Empire: world cities, relations, tribute, gifts and requests

Status: **verified** from the exe unless marked. Addresses refer to GOG `Zeus.exe`.
Trade itself (traders, posts, docks, prices) is in [trade.md](trade.md).
Struct rows: `re/structs/trade-empire.tsv` (struct `WorldCity`), names: `re/names/trade-empire.tsv`.

## Summary
The empire is 22 `WorldCity` records of 572 bytes (`g_cities` `0x008FBAC0`, sav rank 7, `.map`
block 25) plus 200 world-map objects of 72 bytes (`g_world_objects` `0x008FEBE8`, sav rank 10,
`.map` block 17) that place cities and markers on the map. One record (kind 0) is the player's
own city. Each other city has a kind (colony, foreign, parent, distant…), a relationship
(ally / rival / vassal), an attitude 0..100 toward the player, two streak counters (long-term
pleased / displeased), wealth 1..5, military strength 1..6, an army, tribute settings, a
4-good buy list, a 4-good sell list and a quota per good. Attitude drifts back to 50 twice a
year, moves by a difficulty-dependent table four times a month, and is raised by the player's
gifts. Streaks above 40 trigger relationship events (gifts from the city, trade/tribute
suspension…). Yearly tribute is paid by vassals/colonies and claimed by rivals that conquered
the player.

## WorldCity record (0x23C bytes)
Offsets are for the current (version ≥ 302) layout. "init" = value set by the editor's new-city
routine `0x0042CA10` (useful defaults).

| Off | Type | Name | Meaning / evidence |
|---|---|---|---|
| +0x00 | u8 | in_use | record used (all loops test it) |
| +0x01 | u8 | army_months | army-in-progress counter: +1 per call of `0x0042D5E0` while ≠ 0, capped 12; cleared by `0x00482200`/`0x00481E80`; tested in `cities_relations_update` (military) |
| +0x02 | u8 | kind | 0 player's city ("Parent City" in [39]), 1 colony, 2 foreign, 3 parent city, 4 distant, 5 enchanted place, 6 destroyed (text group 39; checks in `0x0042C9C0`, `0x0042CF10`) |
| +0x03 | u8 | name_id | city name string index (label `0x005B9480`; values 13..74 in maps) |
| +0x04 | u8 | city_id | own index, used in event records; `0x004614F0` finds a city by it |
| +0x05 | u8 | trade_open | 1 = trade allowed; set to 1 for all at map start (`city_init_from_map`); city events 0/2/6 clear, 1/3/7/0x17 set |
| +0x08 | i16 | unk_08 | 10 in all shipped maps |
| +0x0A | i16 | trader_countdown | trade.md |
| +0x0C | i16 | trade_gate | must be 0 to spawn traders; only written 0 |
| +0x0E | i16 | world_object | index into `g_world_objects` (map marker of this city) |
| +0x10 | u8 | sea_route | 1 = ships |
| +0x12 | i16[3] | trader | live trader figure ids |
| +0x18 | u8[23] | buys | flag per good: city buys g (player exports) |
| +0x3C | u8[23] | sells | flag per good: city sells g (player imports) |
| +0x60 | u8[23] | quota | yearly loads per good (init 12) and request size base |
| +0x84 | u8[23] | used | loads traded this year |
| +0xA8 | u8[20] | resources | player's city only: goods it may produce (14 used, `0x00460B40`); copied from scenario `+0x7A8` on a new adventure |
| +0xBC | u8[4] | buy_list | goods the city buys (source of `buys[]`, `0x00460B80`/`0x0042E270`) |
| +0xC4 | u8[4] | sell_list | goods the city sells (source of `sells[]`, `0x00460BB0`/`0x0042E2A0`); also what it can give |
| +0xCA | u8 | troops_return_timer | months until `+0xCB` troops return (`0x0042D540`) |
| +0xCB | u8 | troops_returning | |
| +0xCC | i32 | nationality | hypothesis (see sandbox table); init 9 if `0x00902BB0` else 0 |
| +0xD0 | i32 | unk_d0 | init 0; 4..76 in maps (leader name index? hypothesis) |
| +0xD4 | i32 | relationship | 0 ally, 1 rival, 2 vassal, 3 (colony that pays tribute); foreign cities only use 0..2 (`0x0042CF10` forces other values to 1); distant forced to 0 |
| +0xD8 | i32 | wealth | clamped 1..5 (`0x0042D5E0`); economic prosperity/decline events; init 3 |
| +0xDC | i32 | military_strength | clamped 1..6; military buildup/decline events; init 3 |
| +0xE0 | i32 | tribute_mode | 0 none, 1 city pays the player, 2 player pays the city (rival conquered us) |
| +0xE4 | i32 | tribute_claim | base drachmas the player pays when mode 2 (init 100) |
| +0xE8 | i32 | tribute_amount | amount the city pays when mode 1 (init 100) |
| +0xEC | i16 | tribute_good | good the city pays (init 23 = drachmas) |
| +0xEE | i16 | unk_ee | init 23 (second good, unused by the code read) |
| +0xF0 | i32[28] | request_fatigue | +15 per item taken from the city; −1 per month (floor 0); an item can be given while < 21 |
| +0x160 | i32 | unk_160 | 0 in maps |
| +0x164 | i32 | attitude | 0..100, init 50 |
| +0x168 | i32 | pleased_streak | 0..50 |
| +0x16C | i32 | displeased_streak | 0..50 |
| +0x170 | i32 | active | 0 = inactive (city events 0x12/0x13); 1 in maps |
| +0x174 | u8 | flags | bit0 rebellion, bit2 invisible (city events 0x14/0x15) |
| +0x175 | u8 | extorted | set to 1 when the city gave money on demand (`events_cities_random`) |
| +0x178 | i32[28] | gift_fatigue | +12 per player gift of that good (cap 48); −1 per month |
| +0x1E8 | i32 | army | soldiers at home (military) |
| +0x1EC, +0x1F0, +0x1F4 | i32 | army_away_a/b/c | soldiers away (`0x0042DA10` sums them) |
| +0x1F8 | u8 | unk_1f8 | init 1 |

Good-indexed i32 arrays have 28 entries (0..27, 23 = drachmas, 24 troops, 25 food, 27 strike).

### Kind/relationship class — `city_class` `0x0042CF10`
`kind 0 → 5 (self)`, `kind 1 → 2 if relationship == 1 else 4 (colony)`, `kind 3 → 3 (parent)`,
`kind 4 → 6 (distant)`, `kind ≥ 5 → 7`, `kind 2: rel 0 → 0 (ally), rel 2 → 1 (vassal),
rel 1 → 2 (rival), other → rel := 1, 2`. Matches text [61:197..203] (Ally, Vassal, Rival,
Parent, Colony, Self, Distant).

### Predicates
- `city_exists` `0x0042CAE0`: kind ∉ {4,5,6}, `active != 0`, `!(flags & 4)`.
- `city_tradeable` `0x0042C9C0`: kind ∉ {0,5,6}, `active != 0`, `!(flags & 4)`, `relationship != 1`.
- `is_trading_partner` `0x0042C9F0`: `city_tradeable` and `trade_open != 0`.
- `player_city_index` `0x004621E0`: cached in `0x00903128`; first in-use record with kind 0.

## Map / scenario data (what an open-play map defines) — verified on the shipped files
A `.map` (each map of a `.pak`) carries the empire: block 25 = cities (476 B × 22 in version 247
maps), block 21 = prices (rank 8), block 17 = world objects (40 B × 200 in v247). On a new map
`city_init_from_map` `0x00511E30`:
1. `0x0042E1B0`: for every in-use city `0x0042E130`: `army = army_target(c)`, `+0xCA = +0xCB = 0`,
   `+0x175 = 0`, `gift_fatigue[] = request_fatigue[] = 0`, `+1 = 0`; distant → `relationship = 0`;
   colony with relationship 3 and `tribute_mode != 1` → `tribute_mode = 1`.
2. `trade_open = 1` for all 22 records.
3. Version fix-ups by file version `0x00F9D940`: < 302 `0x0050EDE0`; < 303 `0x0050F7E0`
   (pre-Poseidon goods renumbering of `buys/sells/quota/used`, `+0xA8`, `+0xBC`, `+0xC4`,
   `+0xEC/+0xEE`, the price table and the city record's per-good arrays); < 313 `0x00510BE0`.
   Then player city `active = 1`, `flags &= ~4`.
4. Records of an older file are first zero-extended and converted by `0x0050C7E0` (converter
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
Correction (10-29, events.md): the 16 events in this `.map`'s block 16 (types 23, 2, 1, 21, 4, 19) are an editor
copy of `}Open Play Military`'s colony events and are never played: the game takes the events and gods from the
`.pak` episode. `Open Play Sandbox 2.pak` has 12 (3 quests, 3 monster invasions, 6 reward gifts); our `sandbox`
(`}Open Play Sandbox.pak`) has 4 (a quest, 2 monster invasions, a recurring god invasion).

## Periodic updates (all from `month_advance` `0x00483C10`, which runs at the end of each 51-tick
cycle; `month_tick` = `0x0091EC0C` 0..15)
| When | Function | Effect |
|---|---|---|
| month roll-over to January (year) | `0x00461460` | `used[1..22] = 0` for in-use cities |
| roll-over to January or July | `0x0056FC60` (ECX `0x00FF80D0`), then `0x00477270` | hippodrome bonus (below); attitude drift |
| month_tick 2 of January | `0x004771E0` | tribute |
| month_tick 2 | `0x00477210` → `0x0042D540` | fatigue decay, troops return, army regrowth |
| month_tick 0, 4, 8, 12 | `0x00477240` → `0x0042D5E0` | attitude table / streaks / relationship events |
Order inside one `month_advance` call: roll-over block first, then tick-2/7/… blocks in the order
above (see time-core.md).

### Attitude drift `0x0042D850`
`if att > 50: att -= 1 elif att < 50: att += 1` (twice a year, every in-use city).

### Monthly `0x0042D540(c)`
```
if city_exists(c):
    for i in 0..26: request_fatigue[i] = max(0, request_fatigue[i]-1); gift_fatigue[i] = max(0, gift_fatigue[i]-1)
    if +0xCA != 0: +0xCA -= 1; if it reaches 0: away_b(+0x1F0) -= +0xCB; army += +0xCB; +0xCB = 0
target = army_target(c); away = +0x1EC + +0x1F0 + +0x1F4
if army < target - away: army += 1
army_target(c) 0x0042D980 = ftol( sqrt(min(months_0x903114 / 12.0, 30.0)) * k[diff] * military_strength )
    k = {3.0, 4.0, 4.5, 5.0, 6.0}[difficulty 0x00F2A988] (table 0x005EC670); months_0x903114 counts
    months while 0x00902FC4 != 1
```

### Attitude table `0x0042D5E0(c)` (4×/month)
```
if army_months != 0: army_months = min(army_months+1, 12)
if kind == 4: relationship = 0
if !city_exists(c): return
wealth = clamp(wealth, 1, 5); military_strength = clamp(military_strength, 1, 6)
row = first row of T (0x005EC528, 9 × {lo, hi, mode, d[5]}) with lo ≤ att ≤ hi ; none -> return
old_p = pleased_streak; old_d = displeased_streak; d = row.d[difficulty]
mode 0: pleased = min(pleased + d, 50); displeased = 0
mode 1: pleased = 0; displeased = min(displeased + d, 50)
mode 2: pleased = 0; displeased = 0
cls = city_class(c)
if old_d ≤ 40 < displeased: schedule relationship event code {0:0, 1:2, 2:1, 3:4, 4:3}[cls]
elif old_p ≤ 40 < pleased and !(flags & 1): schedule code {0:5, 1:7, 2:6, 3:9, 4:8}[cls]
```
T rows (lo, hi, mode, d for difficulty 0..4):
(91,100,0, 6,4,2,1,1) (81,90,0, 3,2,1,1,0) (71,80,0, 2,1,0,0,0) (61,70,0, 0,0,0,0,0)
(41,60,2) (31,40,1, 0,0,0,0,0) (21,30,1, 0,0,0,1,2) (11,20,1, 0,1,1,2,3) (0,10,1, 1,1,2,4,5).
Scheduling (`0x0047F420`): a scenario event of type 0x1F, `+0x60 = code`, city id at `+0x1C`/`+0x1E`,
dispatched immediately; handled by `0x004742A0` (not yet read: gifts from the city, anger).

### Attitude descriptor `0x0042D8A0`
`pleased > 20` → 15 (ally, vassal, parent, colony) or 17 (rival);
`displeased > 20` → 16 (ally, parent), 19 (vassal, colony), 18 (rival); else level
`att > 80 → 0, 61..80 → 1, 40..60 → 2, 21..39 → 3, ≤ 20 → 4`, plus 0 (ally), 5 (rival), 10 (others).

### Hippodrome bonus `0x0056FC60` (hypothesis on the identity: Poseidon hippodrome)
If `0x00FF80D5 != 0` and `n = 0x00782F18 ≥ 4`: row = tier of n (<12:0, <24:1, <36:2, <60:3, <100:4,
<200:5, else 6) of table `0x006429E8` (7 × 5 i32: (0,0,1,10,4) (0,0,1,20,4) (1,0,1,40,8) (1,0,1,60,8)
(1,1,1,100,12) (2,1,2,200,12) (3,3,−5,500,24)); every in-use city gets `att += row[0]` for
classes 0, 1, 4 and `row[1]` for class 2 (others: the previous value of the local, initially 0),
through `attitude_add` (clamped 0..100). (Also documented by sentiment.md.)

## Attitude changes — `attitude_add(c, d)` `0x0042CED0`: `att = clamp(att + d, 0, 100)`
Callers: scenario events 0x11/0x12 (`0x0046E840` +amount, `0x0046E970` −amount, `+0xC` of the
event), `0x004715C0` (gift/aid event, 4 calls), `events_cities_random`, `0x004EC7C0` (−15 to every
existing visible city of class 0..4: a god event), `0x005666D0` (+20 to every active city of
class 0..4), `0x00566760` (+5/+10, doubled-ish when the argument is set: classes 0,2: 5 or 15;
classes 1,3,4: 10 or 20; message chosen by year/month), `0x0056FC60`.
Each change is logged in the relationship history (`0x0042EEC0`, ECX `0x007796D0`, sav ranks
133/134).

## Player gift to a city — `0x0046FC00(gift_event, *result)`
`g = event+4`, `amt = event+0xC` (i16), `price = max(price[g], 1)` (x87, then `ftol` = truncation):
```
if g == 23 (drachmas):
    V = sqrt(amt)
    B = 1.0 if wealth == 0 else 1.0 / wealth
    t = 0 if treasury < 5000 else 1 if treasury ≤ 10000 else 2 if treasury ≤ 20000 else 3
    a = 0 if amt ≤ 500 else 1 if amt ≤ 1000 else 2
    A = R[t][a], R = (0.5,0.66,1.0 | 0.33,0.5,0.8 | 0.2,0.33,0.6 | 0.15,0.25,0.4)   (0x00632F00)
    message 0xBF1, *result = 0
else:
    V = sqrt(price) * (amt*400*0.01 if g == 19 else amt*100*0.01)
    A = 0.3
    B = 0.075 if g in sell_list (msg 0xBF4, result 3) else 0.4 if g in buy_list (0xBF2, 1) else 0.15 (0xBF3, 2)
k = gift_fatigue[g]
D = 1 if k < 16 else 2 if k < 24 else 4 if k < 32 else 8 if k < 40 else 10
gain = min(ftol(A * B * V / D), 100)            # x87 order: ((A*B)*V)/D
gift_fatigue[g] = min(k + 12, 48)
att = clamp(att + gain, 0, 100) ; history entry
for every other city o (in use, visible, active, same class as c):
    class 0 ally: att_o += ftol(gain*0.15); class 1 vassal: ftol(gain*0.2); class 4 colony: ftol(gain*0.25)
    (rival and parent: nothing); each clamped 0..100, history entry when ≠ 0
```

## Tribute (January, month_tick 2) — `0x004771E0`
For each in-use city with kind ≠ 0:
- `0x0042CD50`: if `city_exists` and `tribute_mode == 1`: if relationship ∉ {2, 3} → `tribute_mode = 0`;
  else `0x004772A0`: if `tribute_good > 0` and `tribute_amount > 0` → scenario event type 0x1D
  (good, amount, city) dispatched now (handler `0x00474F60`, not yet read).
- `0x0042CDA0`: kind ≠ 3, `city_exists`, `tribute_mode == 2` → `0x00477370`: amount
  `ftol(tribute_claim * m[diff])`, m = {1.0, 1.5, 2.0, 2.5, 3.0} (`0x005EC4C0`); if > 0 → event
  type 0x1E (drachmas) dispatched (handler `0x004715C0`).

## City events (scenario event type 0x13, `events_cities_month` `0x00473680`)
Subtype `event+0x60` (text group 35) and the fields it sets when the condition holds:
0 trade suspended / 2 shuts down → `trade_open = 0`; 1 resumed / 3 opens → `trade_open = 1`;
4 tribute suspended / 5 resumed (rel 2 or 3) → `tribute_mode = 0 / 1`;
6 rebellion (rel 2/3) → `trade_open = 0, flags |= 1, tribute_mode = 0`; 7 quelled (rel 2/3) →
`trade_open = 1, tribute_mode = 1`; 0x17 rebellion over (rel 2/3) → `trade_open = 1, flags &= ~1,
tribute_mode = 1`; 8 colony liberated (rel 3, message only here);
9 rival becomes ally (rel 1) → `relationship = 0, trade_open = 1, flags &= ~1`;
10/12 becomes rival (rel 0 or 2) → `relationship = 1, trade_open = 0, flags &= ~1, tribute_mode = 0`;
11 becomes vassal (rel 0 or 1) → `relationship = 2, trade_open = 1, flags &= ~1, tribute_mode = 1`;
13/0x16 god disaster / ends (messages via `0x00473550`…; 13 clears `trade_open`, 0x16 sets it);
14 military buildup: `military_strength = min(ms + event.amount(+0xC), 5)`; 15 decline:
`ms − amount`, values < 2 become 1; 16/17 prosperity/decline: same on `wealth`;
18/19 → `active = 1 / 0`; 20/21 appears/disappears → `flags` bit2 clear/set.
The new values are written only if something differs and the city is not destroyed (kind 6),
not an inactive colony, and visible and active (unless the event changes visibility/active).
If anything changed: fields written, `0x0046ED30`, map marker image refreshed, then for g = 1..22
`buys[g] = sells[g] = 0` and, for the player city: `sells[g] = g ∈ resources`,
`buys[g] = g ∈ buy_list`; for others only if `is_trading_partner`: `sells[g] = g ∈ sell_list`,
`buys[g] = g ∈ buy_list`; global trade status `0x01607EC4 + 0x60*g` (5 importing / 7 exporting)
falls back to 9 when no partner remains (`0x005BAD20`).

## Requests from the player — `can_request(c, g, *code)` `0x0042DF90`
Not possible if `!city_exists` or rebellion. `code = 3`. g = 23 drachmas → thresholds;
24 troops → `0x0042DC80` (army capacity); 25 food → best food 1..8 in `sell_list` with
quota > 0 and `request_fatigue < 21` (none but some food listed → code 0, true; else −1, false);
27 strike → `0x0042DB70` and no pending type-0x18 event; other goods must be in `sell_list` with
quota ≠ 0. Thresholds `0x0042DD50` (goods 9..22 count as goods, 1..8 as food 25):
| class | goods/drachmas | troops 24 | food 25 | strike 27 | returns |
|---|---|---|---|---|---|
| ally | att ≥ 50 | ≥ 81 | ≥ 41 | ≥ 90 | 0 |
| vassal, colony | ≥ 31 | ≥ 41 | ≥ 21 | ≥ 50 | 2 |
| parent | ≥ 31 | ≥ 41 | ≥ 21 | ≥ 50 | 3 |
| rival | att > 89 → 0; att ≥ 81 and food → 0; goods/food/drachmas → 1; else −1 | | | | |
Below threshold → −2 → `code = 2` ("not regarded highly enough", [41:9..12]); a goods request with
`request_fatigue[g] > 20` gives `code = 0` ("no surplus"). Return codes 0..3 select Request /
Demand / Order / Requisition (text [41:3..6]) — hypothesis on the mapping.

Amount a city gives (`0x0042CFA0`, used by `0x00477610` which schedules event type 0x17):
random pick (one `random_next` step, `0x00F137D0 % n`) among `sell_list` goods with
`request_fatigue < 21` and quota ≠ 0; `amount = quota[g] * p[diff] / 100`, p = {100, 75, 67, 50, 33}
(`0x005EC4E8`); then `request_fatigue[last nonzero sell_list entry] += 15` (**sic**: the index is the
last scanned list entry, not the chosen good). Drachmas amount (`0x0042D870`):
`ftol((wealth+1) * q[diff] * 200)`, q = {5, 4, 3, 2.5, 2} (`0x005EC648`).

## `cities_relations_update` `0x00568C20` (cycle step 13; mostly military)
`0x005687A0` fills 22 × {strength, count, extra, flags=4} from the formations (rank 31) and
army figures (type 0x3F) by target city. For every in-use city u ≠ player with `army_months != 0`:
if (`city_state+0x4486 == 0` and `city_state+0x03 == u`) or (`3*own_home < s[u]` and
`city_state+0x4AA0 == u`) → `0x00482200(u)` (city conquers the player: `tribute_mode = 2`,
message 0xB9C…, `army_months = 0`); else if `8*s[u] < own_home` and (`army_months > 5` or
`s[u] == 0`) → `0x00481E80(u,0,0)` (army sent home, `tribute_mode 2 → 0`). Details: military agent.

## Cross-references
- Scenario events (`0x009173F4`, rank 13), `month_events_dispatch` `0x0046DFD0`, handlers
  `0x004742A0`, `0x00474F60`, `0x004715C0`, `0x0046D6D0` (requests 3/0x18/0x19): time-core /
  military-sentiment.
- Army fields `+0x1E8..+0x1F4`, `0x0042DB70`, `0x0042DC80`, invasions: military-sentiment.
- `0x0056FC60`, `0x005666D0`, `0x00566760`: also in sentiment.md.

## Open questions
- Handlers of event types 0x17 (city gift / aid, partly read: drachmas gift adds to treasury and
  `0x00FEAEB0` gifts-received), 0x1D, 0x1E, 0x1F and the request event 0x18: how goods arrive
  (storage) and what the player's refusal costs in attitude.
- `+0xD0`, `+0xCC`, `+0xEE`, `+0x160`, `+0x08`, `+0x1F8` meanings.
- How the empire map editor writes quotas (None/Low/Med/High → 0/12/24/36 is a hypothesis from
  the shipped data).
- World objects (rank 10, 72 B): only `+0` kind (1 = city), `+1` used, `+0x0C` image,
  `+0x18` city index are known.
