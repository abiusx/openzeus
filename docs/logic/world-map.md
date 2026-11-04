# World map (empire map): every feature of the base game

Status: phase 1 inventory, 2026-10-28. Read from `Zeus.exe` (GOG, see CLAUDE.md) through `re/decomp/zeus.c`,
disassembly (`tools/disasm.py`), the shipped `.map` files (`tools/mapfile.py`) and oracle screenshots of the
running exe (`re/oracle/scenarios/worldmap.txt`, shots in `re/oracle/runs/worldmap/`). Each rule is tagged
**verified** (read in the code; address given), **seen** (oracle screenshot) or **hypothesis**.
Zeus only; Poseidon parts are named and marked "Poseidon" but not built (the decision log).

Related docs: [empire.md](empire.md) (the 572-byte `WorldCity` record, attitude drift/table, gift formula,
tribute, city status events, `can_request`), [trade.md](trade.md) (traders, posts, quotas, prices),
[military.md](military.md) (invasions, companies). This doc does not repeat their content; it adds the screen,
the map data, the player actions and the event flows, and lists what our sim has.

Names: `re/names/world-map.tsv` (screen, provisional `wm_sub_*` entry points recovered for this work),
`re/names/world-map-diplomacy.tsv`, `re/names/world-map-military.tsv`.
Message phrase ids (0xNNN below) index the exe's phrase-name table `0x005FBC38`; the texts are in
`zeus-original/app/Model/Zeus eventmsg.txt` (resolver: `refs/zeus-poseidon-arm64/tools/eventmsg.py`).
Text group:index ids ([47:8]) are `extracted/text/zeus_text.txt`.

## 1. Summary
The world map is a separate screen (screen id `0x14`) opened from the control panel's globe button. It shows
a painted map of Greece (one of 10 pictures, chosen by the scenario), the cities of the empire as icons with
their names, the trade routes between the player's city and its trading partners as dotted lines (red by
land, blue by sea), and armies moving along routes. A side panel on the right describes the selected city
(kind and relationship, name, leader, attitude word, goods it buys/sells with this year's quota use, tribute)
and holds the player's diplomatic actions: request, gift, fulfil the city's requests, raid, conquer, history,
and "Orders" (jump to the trading post bound to that city).

Everything a city does by itself is driven from `month_advance` (attitude, streaks, tribute, gifts, rebellions,
invasions) and from scheduled scenario events. The open-play sandbox has **no scheduled city events**: in it the
only city-initiated actions are the monthly ones (sections 6.1-6.4). (Correction 10-29: it does schedule a quest,
monster invasions and a god invasion, which do not involve world cities: events.md.)

## 2. Data

### 2.1 Cities — `g_cities[22]` `0x008FBAC0`, 572 B each (sav rank 7, `.map` block 25): see empire.md.
Fields the screen reads besides empire.md's: `+0x03` name id (text group 21; group 331 short name when the
name is wider than the box; `0xFF` = custom name at `+0x1F9`; `FUN_0042E2D0`) **verified**;
`+0xD0` leader id (text group 139; `0xFF` = custom name at `+0x219`; `FUN_0042E3A0`) **verified**
(resolves empire.md's "unk_d0").

### 2.2 World objects — `g_world_objects[200]` `0x008FEBE8`, 72 B (sav rank 10; `.map` block 17, 40 B in v247)
| Off | Type | Meaning | Evidence |
|---|---|---|---|
| +0x00 | u8 | kind: 1 city, 2 text label, 0/3 decoration; > 3 not drawn | verified (`world_map_draw`, `world_object_city` `0x004621B0`) |
| +0x01 | u8 | in use (the list ends at the first 0) | verified |
| +0x02 | u8 | animation frame of the base icon (`FUN_00599460`, ping-pong when the sprite flags it) | verified |
| +0x03 | u8 | animation frame of the rebellion icon | verified |
| +0x04, +0x06 | i16 | x, y of the icon centre on the map picture (px) | verified |
| +0x08, +0x0A | i16 | width, height of the icon (hit box) | verified (`FUN_00407360`) |
| +0x0C | u32 | base icon image id (`collection << 14 | index`); for cities the kind's marker (`city_marker_image` `0x0042CB30`), refreshed on status change | verified |
| +0x13 | u8 | city name label position: 0 left of the icon, 1 above, 2 right, other below | verified |
| +0x18 | i16 | city index (kind 1) | verified |
Image id -> extracted atlas: Zeus_Interface atlas index = exe index + 201 (checked on 4 icons: 837 -> 1038
`SPR_EMP_CITY` 33x38, 838 -> 1039 colony, 840 -> 1041 non-player city, 855 -> 1056 distant city, sizes equal).

### 2.3 Routes — `0x009034F8`, 232 records of 324 B (sav rank 101; `.map` block 18)
One record per city pair (22·21/2 = 231 + 1). Read by `world_map_draw`, `route_between` `0x00462910`,
`FUN_005118c0` (map load) **verified**:
| Off | Type | Meaning |
|---|---|---|
| +0x00 | u8 | dot spacing in px (5 in every shipped record; also the travel-time factor) |
| +0x04 | ptr | expanded dot list (6 B: x, y, segment), built at load |
| +0x08 | 6 B × ≤ 50 | control points (x, y, 0) from the editor |
| +0x130 | i32 | capacity of the expanded list |
| +0x134 | i32 | number of expanded dots |
| +0x13C, +0x13E | i16 | the two city indices |
| +0x140 | u8 | 1 land, 2 sea (army sprites, invasion landing, sea-strength comparison) |
| +0x141 | u8 | number of control points (< 2 disables the route) |
| +0x142 | u8 | enabled |
| +0x143 | u8 | percent drawn with the first dot sprite (always 100 in the sandbox; editor feature, hypothesis) |
Expansion (`FUN_004622F0` per segment): from control point i−1 to i, one dot every `+0x00` px along the
segment (`t = 0, s, 2s, … ≤ length`, position by linear interpolation; x87 rounding not checked, hypothesis).
Travel time `route_travel_months` `0x004625A0` = `max(2, dots * spacing / 200)` months (~ 1 month per 200 px).

### 2.4 Map picture — `0x0090311C` (sav rank 114; `.map` block 26 in v247), 1..14
`FUN_00460580` clamps it to 1..14 and loads `0x005FB770[n]`: 1..10 = `Zeus_MapOfGreece01..10`, 11..14 =
`Poseidon_map01..04` (Poseidon). All 838 × 738 JPEGs; the sprite header is always `Zeus_MapOfGreece01.sg3`
(`FUN_005AC7C0`). **verified**. The sandbox uses 1.
Scroll: `0x008F9838` (x), `0x008F9834` (y) (sav ranks 48/49), clamped to the picture; at 1024 × 768 the whole
picture shows (838 = 1024 − 186, 738 = 768 − 30).

### 2.5 Other state
`0x00903120` selected world object + 1 (0 = none; sav rank 50); `0x005FB7D0` hovered/selected army marker;
`0x00903440` dialog mode (0 favour advice, 1 request list, 2 gift list, 3 gift size, 5 city's requests, 6 history;
`0x00903444`.. rows; drawn by `FUN_00464C00`, docs/play/world.md "Dialogs").
Trade on/off for the scenario: `0x00902D44` (trade build menu hidden when 0). World map disabled for the
episode: `0x0091EC68` (button shows warning [19:31] "Not available in this episode!") **verified**.

## 3. The screen

### 3.1 Opening and closing — verified
- Control panel button "Go to World Map" [88:23] at panel (115,565), `SPR_MAIN_WORLD_MAP`, handler
  `panel_world_map_btn` `0x00409110`: in the city (screen 1) → `world_map_open` `0x00408AF0` (screen `0x14`;
  editor `0x15`), else → `screen_back_to_city` `0x00408BB0`. Tooltip [68:42] "Go to the map of the world".
- "Back to City" [47:8] button on the world map → `0x00408BB0`.
- The world map has no keyboard shortcut of its own in the code read (hypothesis; not searched exhaustively).

### 3.2 Layout (1024 × 768) — verified + seen
- Top bar as in the city (menus, funds, population, date) `FUN_0058EB20(1)`.
- Map viewport: x 0..panelX+16 (clipped to the picture width), y 30..H; picture drawn at (−scrollX, 30−scrollY).
- Side panel `SPR_WORLD_SIDE_INT` (Zeus_Interface 1600, 186 × 768) at x = panelX + 16 − (16 if W > 800)
  = 838 at 1024 (`FUN_00597E20`); at W > 800 two 128-px fillers are drawn at both screen edges first.
- Widgets: draw table `0x005EF488`, 12 × 40 B (format of `widget_table_draw` `0x004316F0`: x, y, w, h,
  packed group, image offset, handler at +0x10, state byte +0x18: 0 disabled (image +3), 1 enabled,
  2 hidden). Positions relative to the side panel. Images `SPR_WORLD_SIDE_BUTTONS` (Zeus_Interface 1601 +
  offset; +1 hover, +2 pressed, +3 disabled):

| # | Rect | Image | Handler | What | Tooltip |
|---|---|---|---|---|---|
| 0 | (39,570) 139×25 | +0 | `0x004081E0` | Back to City [47:8] | |
| 1 | (13,572) 27×27 | `SPR_PANEL_ICONS` 533 | `0x004081D0` | help page 0x58 | [68:1] |
| 2 | (9,131) 173×30 | +4 | `0x004068F0` | attitude word; click opens the attitude/advice window (screen `0x1A`, texts group 92) | [68:4] |
| 3 | (13,460) 51×51 | +8 hands | `0x00406A20` | Request ([41:1] "Request of [city]") | [68:5] |
| 4 | (70,460) 51×51 | +12 donkey | `0x00406B00` | the city's requests to fulfil ([41:2]) | [68:8] |
| 5 | (127,460) 51×51 | +16 amphorae | `0x00406A50` | Give a gift ([41:0]) | [68:6] |
| 6 | (13,518) 79×45 | +20 helmet | `0x00406A80` | Raid | [44:312] |
| 7 | (98,518) 80×45 | +24 army | `0x00406AC0` | Conquer | [44:313] |
| 8 | (11,97) 56×32 | +28 | `0x00406B30` | previous city | |
| 9 | (119,97) 62×32 | +32 | `0x00406BB0` | next city | |
| 10 | (69,89) 48×40 | +36 scroll | `0x00406930` | history of the city ([44:284] "History of [city_name]") | |
| 11 | (29,202) 139×25 | +0 | `0x00406940` | "Orders" [47:7]: open the info window of the trading post/dock bound to the city; none → message 0xB7 (land) / 0xB9 (sea) | |
Tooltip wording for 3/4/5/6/7 in the help text is [68:5..8]; [44:308..313] are the editor's.

Enable rules (`world_map_screen` `0x00597E60`) **verified**:
- nothing selected: only 0, 1, 8, 9 enabled, 11 hidden;
- the player's own city: all disabled, 11 hidden;
- `!city_exists` (distant, enchanted, destroyed): 2..7 disabled;
- not a trading partner or trades nothing with a quota: 11 hidden;
- `!city_can_be_attacked` `0x0042E1E0`: 6, 7 disabled (allowed: ally, rival; vassal/colony only while rebelling);
- rebelling: 3 (request) disabled.
Seen: colony Elis: request/requests/gift enabled, raid/conquer disabled; ally/rival/vassal as the rule; distant
Thasus: all 2..7 disabled, Orders shown.

### 3.3 Side panel text (`FUN_005981B0`, positions from the panel origin) — verified, seen
- Player city: [47:0] "Our city!" centred at y 46, name at y 65 (box x 16, width 151). Panel body empty.
- Other city: kind line at y 34: parent → [39:3] "Parent City", else group 253 by relationship (Ally, Rival,
  Vassal, Colony); distant/enchanted/destroyed cities show no kind line (seen: Thasus). Name at y 50, "Leader:"
  [44:328] + leader name in the small font at y 69 (city_exists only).
- Attitude word centred in widget 2 (y 139): group 65 index `city_attitude_code` `0x0042D8A0` (empire.md);
  rebelling → [44:329] "Rebelling!". Words seen: Loyal (colony/vassal), Sympathetic (ally), Displeased and
  Apathetic (rivals). No word for non-existing cities.
- [47:6] "Goods" at y 184; Orders button (widget 11).
- Two lists (each only if non-empty): title at y 247: trading partner → [47:1] "Buys" / [47:2] "Sells";
  otherwise [47:3] "Needs" / [47:4] "Produces" (rivals). Box `SPR_COMMOD_BOXES` (1641 + rows−1, 148 × 24·rows)
  at (24, title+16); rows every 20 px: good icon at (29, row−6), good name (group 23) at (54, row), and for
  partners "used/quota" centred at x 129 width 37 (seen "0/12", "0/36"). Only buy/sell-list goods with
  quota ≠ 0 are listed.
- Tribute box at y 412 (multi-line, width 170, `FUN_00509060`): kind 4 distant → [44:325]; ally → [44:323];
  rival without claim → [44:324]; rival claiming (`tribute_mode == 2`) → [44:321] "Claiming Tribute" + icon +
  claim amount (×difficulty, `city_tribute_claim_amount`) + good + [44:322] "yearly"; vassal/colony → [44:320]
  "Paying Tribute" + good icon + amount + good + "yearly"; and when `tribute_mode == 0`: line at y 444
  [44:326] "Suspended" ([44:327] "Suspended by rebellion"). Seen: Elis "Paying Tribute / 4 Wine yearly";
  Miletos "Paying Tribute / 4 Bronze yearly / Suspended".
- A debug block (`0x010DFFC0`) prints favor/benevolence/hostility/army: not shown in normal play.
- No city selected: [47:5] "Click on a city to get information on it" in the big box (seen).

### 3.4 Markers on the map (`world_map_draw` `0x00599DA0`) — verified, seen
For every world object of kind ≤ 3, in list order, if visible (`FUN_00599D30`: not `flags & 4`, not an
inactive colony; the editor shows all):
1. Base icon `+0x0C` centred at (x, y) (animated if the sprite has frames).
2. City name (`FUN_0042E2D0`) in the mask font SPR_FONTS, colour 0x7F39 (565: 0xFE59), no shadow, placed by `+0x13`
   (left: x - width, centred y; top: y - 10; right: x + icon w; else below: y + icon h + 5). Everything but the
   picture is drawn at scroll x - 1 when the picture is not wider than the view (1024 x 768: 1 px right; play/world.md).
3. If the city is active (`+0x170`): a standard at the icon's top-right: player `SPR_EMP_PLAYER_STANDARD`;
   colony/parent and vassal `SPR_EMP_COLONY_STANDARD`; ally `SPR_EMP_ALLY_BANNER` (5-frame animation);
   rival none. Foreign cities (kind 2) also get `SPR_EMP_MILITARY_STRENGTH` + (clamp(army/20, 1, 5) − 1) at
   the icon's top-centre and `SPR_EMP_ECONOMIC_STRENGTH` + (clamp(wealth, 1, 5) − 1). Rebelling:
   `SPR_EMP_REBELLING` animation.
Base icons (`city_marker_image` `0x0042CB30`, Zeus branch): player `SPR_EMP_CITY`; colony
`SPR_EMP_ACTIVE_COLONY` / `SPR_EMP_INACTIVE_COLONY`; foreign `SPR_EMP_NONPLAYER_CITY` + nationality (0..4) or
`SPR_EMP_INACTIVE_CITY` when inactive; parent `SPR_EMP_CITY`; distant `SPR_EMP_DISTANT_CITY` + nationality
(inactive: `SPR_EMP_INACTIVE_CITY` + nationality); enchanted place / destroyed `SPR_EMP_MONSTER_LAIR` +0/+1.
Kind-2 world objects are free text labels (`FUN_005C29B0`, 90 px wide, shadowed).

### 3.5 Routes on the map — verified, seen
Drawn first, for every enabled record (`+0x142`; `+0x141 < 2` clears it) linking the player's city with a
**trading partner** (`is_trading_partner`) that has dots: one dot sprite per expanded point,
`SPR_LAND_ROUTE` (land) or `SPR_SEA_ROUTE` (sea), 3 × 3 px. Seen: red dotted land routes, blue dotted sea
routes; routes to rivals are not drawn (Sparta, Delos have none).

### 3.6 Armies on the map — verified (fork B)
`world_map_draw` then draws, for pending invasions (type 2), player/ally expeditions and requested troops
(type 1 item 0x18/0x1A) and ally strikes (type 0x22), a sprite at a point of the route record between the two
cities (`event_world_map_position` `0x004694E0`, `0x00599740`):
```
rem = months left on the leg; T = route_travel_months(route) (>= 1); drawn if 0 <= rem <= T
pct = 100 if rem < 1 else 0 if rem == T else
      (cycle_step + ((T-rem-1)*16 + day_of_month)*51) * 100 / (T*816 - 816)       # smooth within months
pct = clamp(pct, 0, 100); reversed when the route's first city is not the origin
dot = route.dots * pct / 100 (capped at dots-1)
```
Sprite (`0x00599590`): size 0/1/2 by strength (≤ 32, ≤ 66, more); player land `SPR_EMP_ARMY_GREEK_P`, sea
`SPR_EMP_NAVY_PLAYER`; others land by nationality (`SPR_EMP_ARMY_GREEK_NP`, TROJAN, PERSIAN, CENTAUR, AMAZON;
5..9 Poseidon), sea `SPR_EMP_NAVY_NP`. Heroes drawn beside (`world_map_draw_army` 0x00599740, 11-01): the
scenario's hero slots 0..2 (slot 2 skipped when it repeats 0 or 1) whose figure is away on this event (+0x132), each
`SPR_EMP_HEROES` + hero at the army picture's top-left + table `0x00644E68` [(0,0), (10,10), (-10,-10), (10,-10)],
from entry 1 when the picture is drawn, entry 0 when the army is hidden (+0x77 = 0: a quest's army is only its hero);
heroes 6/7 (Poseidon's) come from another file. Ours: sim/empire/war.py `army_heroes`, viewer/play/world.js
drawArmies; oracle re/oracle/scenarios/1L-quest-worldmap.txt wm1 (Achilles on his quest at Thasus, tick 5469) vs
ours (`tools/sim_monster_track.py --quest --every 51 --ticks 5468 --save Q.pkl`, map at 1:1): 0 px in 60 x 60
around Thasus. Hover tooltips use
[47:9..26] (exact selection not traced; hypothesis: marching/sailing pairs for help, conquer, raid, home,
ally strike, ally joins, ally home, enemy toward you).

### 3.7 Input — verified
- Left click on the map: `FUN_00407360` picks the visible city whose icon rectangle grown by 8 px contains
  the mouse and whose centre is nearest (Chebyshev distance < 30) → selected (`0x00903120`). Armies are
  picked the same way (`0x005FB7D0`). Right click: deselect.
- Hover over a city: tooltip 0x9C4 ("Click for information", seen).
- Previous / next (widgets 8, 9): cycle through in-use, visible, active cities (`+0x174 & 4 == 0`,
  `+0x170 != 0`) by index, wrapping over 22.
- Scrolling the picture when it is larger than the viewport (800 × 600): `FUN_00599D70` / edge scroll
  (not read in detail).

## 4. Player actions

### 4.1 Request goods, money, food, troops, a strike — verified (fork A, B)
Dialog (`0x00465070`, screen `0x1A` mode 1): one row per item 9..21, 23 drachmas, 24 defensive aid, 25 food,
27 military strike (`item_requestable` `0x00462500`; individual foods 1..8 and the chariot are never listed),
shown when `can_request` (empire.md) gives threshold ≥ 0 or code ≥ 0; clickable only when threshold ≥ 0 and
code 3; otherwise a disabled reason line [41:9..18]. Title "Request/Demand/Order/Requisition [item]"
[41:3..6] by class (empire.md). Strike first asks for a target rival (`0x00464D50` → `0x004067B0`, check
`0x0042DB70`, confirm 0x4A).

`city_player_request_create` `0x0047FF80(obj, item, target)`:
```
food 25 -> the food 1..8 in sell_list with the largest quota and request_fatigue < 21 (none -> nothing)
if request_fatigue[item] >= 21: nothing
amount: troops 24 / strike 27 -> army*2/5 (0x0042D9F0)
        drachmas -> {1000,800,600,500,400}[difficulty] * wealth            (0x00633340)
        goods    -> ftol(quota[g] * {1.0,0.75,0.66667,0.5,0.33333}[diff]) loads (0x00633318)
if amount == 0: nothing
strike: event type 0x22 (+0x58 = +0x6F = target), dated now
else:   event type 0x20 "granted", dated now + 1..2 months ((rng_15 & 1) + 1, one random_next)
        rival "demand" (threshold class 1) and player strength (land; sea when the route is by sea)
        < max(1, city army) -> type 0x21 "refused" instead (message 0x3F2/0x3F3 on its date)
if not refused: request_fatigue[item] += 15
attitude cost now, even if refused later (0x0047FD90; self / others of the same class):
              ally       rival        vassal     colony     parent
   goods     -10/-2     -20/-5       -15/-5     -10/-5     -10
   troops    -40/-5     -100/-100    -30/-5     -25/-5     -25
   strike    -50/-5     -100/-100    -35/-10    -30/-5     -30
```
Delivery (type 0x20, `0x004752A0` via `incoming_goods_dialog` `0x004745E0`): on its date a dialog offers
accept / refuse / postpone by the room in storage (granted 0x279, money 0x27A, half room 0x27B, little room
0x27C, after a postpone 0x27D, then forfeited 0x27E). Accept: money → treasury and "gifts received"
`0x00FEAEB0`; goods → `city_goods_add` into storehouses on Get/Accept within limits and granaries, the
overflow is lost. Refuse 0x282; postpone 0x281 (one more month). Troops (24): an allied army appears on the
city map (`0x004E2C10`) and stays ≥ 4 months, leaving when no enemy remains (on-map military).

### 4.2 Gift — verified (fork A)
Dialog (`0x00464EE0`, mode 2): goods 1..14, 16..21 and drachmas (`item_giftable` `0x004624C0`; no horses,
no chariots) when stock (granaries + storehouses + posts) ≥ 400 units, drachmas when treasury ≥ 500.
Size dialog `0x00463E40`: small/medium/large [41:22..24] = 400/800/1600 units (sculpture 1/2/4 pieces) or
500/1000/2500 dr; offered as far as the stock covers. Confirm `0x00406890` → `player_gift_send` `0x0047FBB0`:
- `gift_fatigue[g] > 39` → letter "[city] refuses your gift" (0x3F8/0x3F9); nothing spent.
- else a type-1 event kind 9 (deadline 48), paid at once by `event_pay_tribute_or_gift` `0x0046DAA0`: goods
  removed from storage (`city_goods_remove` `0x00489B90`) or treasury debited ("gifts given" `0x00FEB1A8`);
  travel 1..4 months (`(rng_a & 3) + 1`); on arrival `city_receive_gift` `0x0046FC00` (formula in empire.md)
  and a letter by result: money 0xB1A, needed 0xB22, not needed 0xB2A, produced by the city 0xB32.

### 4.3 Fulfil a city's request — verified (fork A)
Widget 4 lists this city's outstanding type-1 requests and its tribute claim (type 0x1E). Fulfil =
`event_pay_tribute_or_gift`: state 2 early / 3 on time / 4 late; goods/money leave at once, travel 1..4
months, then the attitude result (section 6.5). Hermes' help may fulfil one for free
(`hermes_request_auto` `0x004E7C00`; religion, out of our scope).

### 4.4 Raid and conquer — verified (fork B)
Allowed on allies and rivals, and on rebelling vassals/colonies ("quell rebellion"). `expedition_event_create`
`0x0047FA60(obj, raid)`: type 1, item 0x18, kind 9, flags 0x100 (+0x4000 raid), deadline = travel + 1. Army
dialog (`0x005BBB60`, screen 0x21): horsemen and hoplite companies at home (never rabble), triremes (sea
routes only), heroes, sanctuary companies, at most one ally willing to strike (joins with 2/5 of its army).
Raid: choose the plunder good (default drachmas). Dispatch → companies leave (`expedition_send_forces`
`0x004DEB30`), travel = route months, battle on arrival (`distant_battle_resolve` `0x00461540`):
```
P = members of sent companies (horsemen and companies 33,34 x2) + 6 per trireme + ally troops + 10 per hero
E = target army (+0x1E8)  (x70/100 with flag 0x200; x50/100 with god help 0x1000)
if late-arrival flag 0x400 and E/2 < P: win, no casualties
loss (P < E):  d = (E-P)*100/E ; T = d<10:70 <25:50 <33:33 <50:25 <66:20 <=74:10 else 0
   conquer: player 80 %, enemy T %, ally 50 %
   raid:    k = ((E-P)*100/P)/100 ; player = k<1:30 <3:40 <5:50 <7:60 <9:70 <=10:85 else 100 %
            enemy = d<10:25 <25:18 <33:12 <50:9 <66:6 <=74:3 else 0 % ; ally 25 %
win:  d = (P-E)*100/P
   conquer: (player, enemy, ally) = d<10:(70,50,70) <25:(50,50,50) <33:(33,50,33) <50:(25,50,25) <66:(20,50,20) else (d<=74?10:0, 50, same)
   raid:    d<10:(25,25,25) <25:(18,25,18) <33:(12,25,12) <50:(9,25,9) <66:(6,25,6) else (d<=74?3:0, 25, same)
casualties: each company loses members*pct/100 (all dead = wiped); triremes damaged/sunk; ally troops
target army -= enemy_pct * E / 100 ; target military_strength 6 = invincible (always a loss)
```
Results: conquer win → the city becomes your vassal (colony if kind 1): relationship 2 (3), tribute_mode 1,
trade_open 1, attitude 31, displeased streak 0, Conquest monument award (`0x00402B00(5)`, hypothesis),
message 0x3BC. Raid win → loot (`0x0042D380`): drachmas `(wealth+1)*{5,4,3,2.5,2}[diff]*200`, goods
`min(quota[g]/{0.5,0.66,0.75,1,1.5}[diff], capacity)` with capacity 50 per hoplite, 100 per horseman, 600 per
trireme; arrives home as a type-0x20 delivery. Attitude: the target −100 (conquer loss/ally) / −35 / −20 …,
and every other active visible city by its class (tables `0x00633354..0x00633434`: attacking an ally costs
−100 with every ally; rivals +10/+20 when you win against a rival). Return trip = travel months, message 0xDE.
State machine `0x0046ED70` (states 6 away, 7 won, 8 late, 9 lost, 10 done) and all details: section 9 (fork B).

### 4.5 Orders, history, attitude window, prev/next — verified
- Orders (widget 11): opens the bound post's info window (trade orders per good; trade.md).
- History (widget 10, `0x00406920`): list of the relationship history entries of the city (`0x0042EE90`
  count, entries written by `0x0042EEC0`, sav ranks 133/134), scrolled.
- Attitude (widget 2): "Favor Advice" window (mode 0, `FUN_00465330`): text group 92, base by class (ally 0, rival
  9, vassal 18, colony 27, parent 36) + 5 if the pleased streak (+0x168) is 50, + 6 if > 20, + 8 if the displeased
  streak (+0x16C) is 50, + 7 if > 20, else by attitude (> 80: 0, > 60: 1, >= 40: 2, >= 20: 3, else 4) **verified**,
  seen (oracle 1F-wmdlg1/2). Dialog layouts: docs/play/world.md "Dialogs".

### 4.6 Not in Zeus (checked)
- **No route opening and no route cost**: there is no widget, dialog or command to open or close trade
  with a city, and no treasury debit tied to `trade_open` (verified: the 12 widgets above are all the
  world-map actions; `trade_open` is written only by map start, city status events, the streak
  consequence "trade suspended", conquest and the strike). Caesar III / Pharaoh have route opening; Zeus does not.
- No colonies founded from the sandbox (colony episodes are adventure structure).

## 5. Trading posts and the world map
- Trade build submenu (trade.md "Build menu"): one item per `city_tradeable` city (not the player, kind not
  0/5/6, active, visible, **relationship not rival**) that buys or sells something with a quota and has no
  post/dock yet; `trade_open` is **not** required (`FUN_005B9410`, `city_nth_other` `0x005B9350`) **verified**.
- Traders come only from `is_trading_partner` cities (`city_tradeable` and `trade_open`) (`cities_trade_update`
  `0x005B9EE0`). A post bound to a city that becomes rival, rebels, is suspended or disappears stays standing
  but no trader comes; it still holds goods and its storehousemen still work. **verified**

## 6. City-initiated events

### 6.1 Monthly city code (sandbox: yes) — empire.md + fork A
| When (month_advance) | Function | Effect |
|---|---|---|
| Jan/Jul roll-over | `city_attitude_drift` `0x0042D850` | attitude 1 toward 50 |
| day 0, 4, 8, 12 | `city_attitude_update` `0x0042D5E0` | streaks; crossing 40 → relationship letter (type 0x1F, `0x004742A0`, message only) |
| day 2 | `city_monthly_update` `0x0042D540` | fatigue decay, troops return, army regrowth |
| day 2 of January | `cities_tribute_yearly` `0x004771E0` | tribute in (type 0x1D) / out (type 0x1E) |
| day 7 | `cities_streak_pick` `0x0047ECD0` → `city_streak_consequence` `0x00477430` | 6.2 |
| day 12 | `cities_spontaneous_events` `0x0047EE20` | debt gift, rival invasion (military.md) |
| Jan | `cities_reset_yearly_trade` `0x00461460` | quota use reset |

### 6.2 Streak consequences (day 7) — verified (fork A)
One random city among in-use, active, visible colonies/foreign/parent cities (`random_next`,
`rng_15 % n`). Row by streak: pleased ≥ 50 → 0; pleased 21..49 → 1; both 0 → 2; displeased 21..49 → 3;
displeased ≥ 50 → 4.
| Row | Ally | Rival | Vassal | Colony | Parent | Δattitude |
|---|---|---|---|---|---|---|
| 0 | aid (gift) | – | aid | aid | aid | −30 |
| 4 | trade suspended | invasion | rebellion | rebellion | trade suspended | +30 |
Rows 1–3 do nothing. On an action: both streaks 0 and attitude += Δ (not clamped here, sic).
Aid = type 0x17 (`city_schedule_aid` `0x00477610`, good and amount `city_pick_aid_good` `0x0042CFA0`);
trade suspended = type 0x13 subtype 0; invasion = type 2 (`0x00477830`, sea landing on sea routes);
rebellion = type 0x13 subtype 6 (deadline 12).

### 6.3 Gifts from cities (type 0x17, `event_gift` `0x00474A80`) — verified (fork A)
Incoming dialog (title 0x25A): accept / refuse 0x264 / postpone 0x263 / forfeit 0x260. Money → treasury,
"gifts received"; goods → `city_goods_add`. Debt rescue (flag 0x10, from day 12: ally or parent, treasury < 0,
attitude > 49, once per city `+0x175`): amount `(wealth+1)*{5,4,3,2.5,2}[diff]*200`, attitude −10 on accept.

### 6.4 Tribute — verified (fork A, empire.md)
- In (type 0x1D, `0x00474F60`): vassals/colonies with `tribute_mode == 1` and good/amount set, every January;
  same dialog (title 0x296) — seen in the sandbox: "Tribute paid by Elis … unable to accept my tribute of
  4 amphorae of wine … taking the 4 amphorae of wine with me" when no storage had room ("forfeited due to
  lack of space").
- Out (type 0x1E, `0x004715C0`): only after a rival conquered the player (`tribute_mode == 2`): drachmas
  `claim × {1,1.5,2,2.5,3}[diff]`, due in 2 months (announcement 0x1C2, reminder 0x1C3, overdue 0x1C4 → 12
  more months → attitude −70, 0x1C9). Paying: early +10, on time +5, late −35.

### 6.5 Requests by cities (type 1) — verified (fork A); scenario events only (none in the sandbox)
Kinds: 0 general, 1 send troops to defend an ally, 2 forces for an attack on a rival, 3 festival, 4 building,
5 famine, 6 financial, 7 monster/hero quest (heroes: out of scope). Tone by class: ally "needs", rival
"demands", vassal/colony "begs", parent "requisitions". Activation, reminders (countdown = deadline,
6 months left), overdue → grace period (per kind, random), then refused. Attitude results (requester self,
same-class others) per kind and outcome: tables `0x00632F60..0x006331A0` (e.g. general: early +25/+3,
on time +18/+2, late −10/−1, refused −20/−2 for an ally). "You can now fulfil" letter when stock suffices.

### 6.6 City status changes (type 0x13), price changes, invasions
Empire.md (status subtypes), trade.md (price events), military.md (invasions). Status changes and price
events come from scenario events (sandbox: none) except "trade suspended" and "rebellion" (6.2).

### 6.7 Military by cities — verified (fork B)
- Rival invasions: military.md (scheduled type 2; spontaneous at day 12 when the player has had an army;
  streak row 4).
- Rival army away (type 0x14, scenario): 3/5 of the army away for 12 months.
- Being conquered (`0x00482200`): tribute_mode 2 (claims tribute); conquered again → episode lost.
- Ally strike for the player (type 0x22, `0x00480A00`): abstract battle ally vs target rival; win → the target
  becomes **your vassal**; loss → ally loses 75 %.
- Cities never fight each other on their own (hypothesis: no other writer found).

### 6.8 Incoming offers, defensive aid on the map, trade gated by relations — verified (decompile, track 1B 10-29)
Phrase ids = index into the name table 0x005FBC38 (Model/Zeus eventmsg.txt names). Message param block (short[]):
[0] body, [1] title, [8] reason, [0xB] button bits. Event fields: +0x02 type, +0x04 item, +0x0C amount, +0x28 flags,
+0x2E countdown, +0x30 state, +0x32 shown.

**Defensive aid (request item 24 = troops, delivery type 0x20).** can_request troops 0x0042DC80: city exists, not
rebelling, ally/vassal/parent/colony, army at home >= total/5, army*2/5 >= 1 (no invasion condition: aid comes in
peacetime too); amount army*2/5 soldiers (0x0042D9F0). Delivery 0x004752A0 -> incoming_goods_dialog 0x004745E0: item
0x18 takes an early path: title 0x462 "Forces arrive from [city_name]", body 0x463, reason 0x464, buttons 5 (Accept +
Decline), message kind 0xE1, category 0 (City News); the event stays in state 0 until answered. Decline: state 7,
message 0x282 (raid variant +0x930), state 10 (the attitude cost and request fatigue were paid when asking).
Accept (state 6): state 9, countdown 4; city_lend 0x0042DAD0 (via 0x00481CE0): away_c (+0x1F4) += n, army (+0x1E8) -=
n; aid_army_spawn 0x004E2C10(n, ev); FUN_00410030(0xE, entry tile) (hypothesis: the go-to list); no further message.
Spawn 0x004E2C10: n = min(n, 150); serial +1; (inf, mis, cav) % = col 9 of rows 0..2 of ENEMY[min(city nationality
+0xCC, 10)]; rabble (0xB) = mis*n/100, horsemen (0xD) = cav*n/100, hoplites (0xC) = n - both (inf% unused). Each count
c > 0 -> companies: c < 9: one of c; 9..16: (c - c/2, c/2); >= 17: (c - 2*(c/3), c/3, c/3); created hoplites, rabble,
horsemen. Entry = the map entry moved by route_tile_check 0x004D2C60 to the nearest route tile without a building;
facing by edge as invaders. Per company: formation_create_event 0x004E2AC0 (first free slot 21..30, none -> silently
not created): in_use 1, +0x01 1, +0x94 1 (non-palace), type, home -1, layout 1, morale 100, +0x03 0, +0x82 -1, +0x48
nationality (no reader), +0x78 event, display slot-1, pos/dest/home = entry, standard bearer 0xE, mobilized 1, mode 0,
selected 0, recalled (+0x98) 0, ready 1; +0x71 facing, +0x88 serial; FUN_00502840 -> dest = a free spot near the
entry; members created on the entry, action 10 (hold), visible; FUN_004E2100 (mode 0 layout).
On the map they are the player's own soldier types; they hold near the entry (fight by contact, rabble throw in
range), go nowhere by themselves; auto-defend takes them (slots 1..30, +0x94 == 0 or +0x98 == 0); the player commands
them like palace companies (click 0x00409150, drag-select unless recalled, advisor other-forces rows 21..30).
formation_morale_add skips +0x94 companies (morale 100, never rout); figure_delete charges no house or population.
Standard: SPR_FLAG_LOAN (general set group +0x470); recalled -> the standard snaps to the map entry.
Stay/leave (monthly, state 9): countdown -1; > 0 -> return; enemy units or warships alive -> return (re-checked
monthly); 0x00481D10: away_c -= n, army += 0 (the sender never gets them back); 0x004E3060(city): every slot 21..30 of
that city: +0x98 = 1, deselected, members action 7 (walk to the map entry, deleted); message 0xE0 0x468 "Forces return
to [city_name]" / 0x469 / 0x46A; state 10, +0x32 0, flags |= 4. All aid companies of that city leave together.
Wiped out (0x00481D40, disassembly): the standard handler, when a company reaches 0 members, it is the city's last
in-use event company and +0x98 == 0: away_c -= n; message 0xE0 0x46E/0x46F "The mercenaries on loan to us ... have
been defeated!"; state 10. The player's own send-home (formation_return_home allows event troops: they walk to the
entry) also ends in this message (per code). Casualties are not fed back: the sender loses all n and regrows +1 a
month toward its target (0x0042D540).
Not certain: whether 0xE1 pauses the game; type shares > 24 (companies n/3 have no cap of 8, member loops run over 8,
members 8+ land in +0x18..+0x26 unmanaged; > 48 overwrites +0x28): needs a sender army ~100+.

**Incoming goods dialog** (gift 0x17, tribute 0x1D, granted request 0x20, raid plunder 0x20 flags 0x4000).
Sources: granted 0x0047FF80 (dated now + 1..2 months); plunder FUN_0047F930 (type 0x20 flags 0x4100, dated now,
dispatched at once; amount +0x72, good +0x70); city gift / aid event_gift 0x00474A80; debt rescue type 0x17 item 23
flags 0x110 (0x0047F100); tribute in 0x00474F60 (only when tribute_mode 1).
Room: money = amount; goods = 0x00488A60 = city_goods_add 0x00489230 dry run / 100 (sculpture / 400). half = (amount
+ 1)/2 (tribute 1). Buttons (+0x16): 4 Accept 44:209, 1 Decline 44:210, 2 Postpone 44:211 (5 = A+D, 7 = all, 3 = P+D,
0 = notice). Texts (title T, body base B = T+1: B granted, B+1 cash granted, B+2 partial, B+3 insufficient, B+4 last
chance, B+5 forfeited, B+6 accepted, B+7 cash accepted, B+9 refused; postponed B+8 is never used):
gift T 0x25A; debt rescue 0x2B4 (cash accepted text literal 700); granted 0x278; plunder 0xBA8 (body = gift + 0x94E);
tribute 0x296.
```
b5 = state in (4, 5) or tribute (tribute: state 0..3 forced to 4: never Postpone)
room >= amount:          granted / cash granted, buttons 5
half <= room < amount:   b5 ? last chance, 5 : partial space, 7
room < half:             b5 ? forfeited, 0 : insufficient space, 3
state 0/1 -> 1 (2 if no buttons), 2/3 -> 3 (4), 4/5 -> 5 (8)
```
Accept 0x004757F0: state 6, dispatched now. Money: treasury += amount; gift/granted/plunder add to "gifts received"
0x00FEAEB0, tribute to 0x00FEB500 (drachmas only). Goods: 0x00489230(g, amount*100 (*400), getFirst, real): pass 1
storehouses / granaries (foods) with Get, pass 2 Accept or Get; per building min(order limit - stock, free bay space
or granary room +0x56); the rest is lost; the "accepted" message only when fewer loads fit than offered. Debt rescue
accept: attitude -10, a history entry (0xBF5), city+0x175 = 1 (only on accept: a refused rescue can come again).
Decline 0x00475850: state 7, the refused message, state 10; no attitude effect. Postpone 0x004758A0: state 1 -> 2 or
3 -> 4, countdown 1 (offered again at the next month rollover, scenario_events_monthly); any other state -> 8
(forfeited notice, state 10). So at most two postpones. An unanswered dialog is offered again every month without
advancing; message_window_open 0x004F2600 re-runs 0x004745E0 with the current storage when a queued message opens.
No auto-accept toggle exists. Options > Messages [2:13] per category [174:n] Off/Condensed/Full [183:0..2]
(defaults Full, Model/Zeus event message categories.txt; Zeus.inf 0x00F2A7FC + category). 0x00521970: a dialog whose
category is not Full is answered by the game: tribute with Accept -> accepted (state 6 in 0x00474F60); every other
incoming dialog, troops included, -> postponed (1 -> 2, 3 -> 4, else 8): so goods that fit are forfeited after three
months (per code, not seen). Categories: gift / granted / rescue 5 "Gifts and Tribute"; plunder, support troops 0
"City News"; tribute 16 "Tribute payments".

**Trade gated by relations.** city_tradeable 0x0042C9C0: kind not in {0 player, 5, 6}, active (+0x170), visible
(!(+0x174 & 4)), relation (+0xD4) != 1 (rival). is_trading_partner 0x0042C9F0: tradeable and trade_open (+0x05).
Build menu (FUN_005B9410 -> city_nth_other 0x005B9350): scenario trade on (0x00902D44), tradeable, no post yet, trades
something (trade_open not needed: a suspended ally is still listed). Traders (cities_trade_update 0x005B9EE0): trading
partners with a quota good, trade_gate == 0, no god land/sea block (trade_block_set 0x005B8DC0), sea partners need a
dock and a sea entry. Nothing opens a route: trade_open = 1 for every city at map start, no cost, no attitude gate.
Cleared only by status events (type 0x13) 0 suspended, 2 shut down, 6 rebellion, 10/12 becomes rival, 13 god
disaster; set by 1, 3, 7, 9, 11, 0x16, 0x17, conquest (0x00480240) and an ally strike making a vassal (0x00480A00). In
the sandbox the only way trade closes is the day-7 streak consequence (0x00477430): displeased streak >= 50 suspends an
ally/parent's trade (0x004776F0, no resumption) or makes a vassal/colony rebel (0x00477A00); the streak grows only at
attitude <= 30 (<= 20 / <= 10 on easier levels).
The user's recollection (10-28): "trade only after relations allow it" — refuted (no attitude gate; every non-rival
trades from the start; rivals never, and aren't listed); "a post stops when relations drop" — partly right: a long
displeased streak suspends trade (or a vassal rebels), and becoming a rival does too: the post stays, no traders come.
event_city_status_change 0x00473680: when a change applies, buys[] (+0x18) and sells[] (+0x3C) flags are rebuilt for
trading partners and zeroed for the rest; city_sells 0x005B9930 reads sells[], city_buys needs partner status: traders
already on the map can neither buy nor sell (not recalled). Conquest and strike-to-vassal set trade_open = 1 without
rebuilding the flags.
Every writer of the flags (11-04, bug 472; decompile + a disassembly scan for the addresses 0x008FBAD8..0x008FBB13):
- FUN_00461360: every city with a world object: kind 0 (player) sells = its resources (+0xA8), no buys; any other
  sells = city_in_sell_list, buys = city_in_buy_list. **No trading-partner gate.** (With arg 1 also the +0x84 bytes of
  traded goods and the trader fields +0x08..+0x16 reset: only from FUN_004612E0, a new world.) Called by
  FUN_00510ED0, the fix-ups after **every saved-game load** (game_file_load 0x0050E610, and the map load 0x00511C90);
  episode_start_load 0x00420390 (colony start at 0x004210E6; continue start through game_file_load; new city through
  FUN_0051D5F0 -> FUN_004612E0); episode_end_save_parent 0x0052D2B0 after the colony's empire is merged (0x0052D45F);
  FUN_004612E0 (city table rebuilt from the world objects: new game, the editor 0x00406CA0 / 0x005B0A18 / 0x005C15EC).
- event_city_status_change 0x00473680 (above): gated by is_trading_partner.
- expedition_attitude_effects 0x00483110, Poseidon only: attacking an Atlantean ally (nationality 9) turns the other
  Atlantean allies into rivals with trade closed (message 0x101D) and rebuilds their flags the same gated way. Not
  ported (Poseidon off; TODO "Stage 3").
- goods_remap_all 0x0050F7E0 (saves older than version 0x12F: the goods' indices remapped), game_file_load (the table
  as saved) and episode_end_save_parent's save/restore of the whole table. Nothing monthly; conquest 0x00480240,
  the ally strike 0x00480A00, rebellion end 0x17 and FUN_0046EAC0 (taken by a rival: subtype 24 skips the status
  change's rebuild) write none; the streak's suspension / rebellion (0x004776F0 / 0x00477A00) go through a type-0x13
  record, so through 0x00473680.
So zeroed flags last until the next load or episode change: then every city has its flags again (a rival too; it
sends nothing because cities_trade_update 0x005B9EE0 counts only trading partners). cities_trade_update spawns a
trader only for a good with a flag and a quota, whatever trade_open says.
Oracle (tools/oracle_trade_flags.py, runs re/oracle/runs/1F-tradeflags-*): Open Play Sandbox with a post for Tiryns:
as is, traders fill its slots by tick 400 (56, 59); with the flags poked to 0 at tick 5 (trade open), no trader in
1,300 ticks and the flags stay 0; poked, then File > Save and File > Load: the flags are back (buys [20], sells [14])
at the first dump after the load (tick 300).
Ours (10-29): see section 11 "Offers, aid, trade".

## 7. Messages and strings
- Text groups: 21 city names (331 short), 139 leaders, 39 city kinds, 253 relationship, 65 attitude words,
  92 attitude advice, 41 request/gift dialogs, 47 world-map panel and army tooltips, 44:308..329 panel/editor
  strings, 61:195..207 overview requests list, 35 city status changes, 165 tribute modes (debug), 37 nations.
- Phrases (eventmsg): letters 0xDF, announcements 0xE0, incoming goods dialogs 0xE1 (hypothesis on the
  kinds). Ids per action are given in sections 4 and 6.

## 8. The user's recollection (2026-10-28), checked
| # | Claim | Verdict | Evidence |
|---|---|---|---|
| 1 | A list of all trade partners with their status | **partly right** | No list widget on the world map: the panel shows one city at a time; prev/next buttons (`0x00406B30`/`0x00406BB0`) cycle through all cities. Every city is on the map with its relationship standard. The overview advisor has a "Requests" list by city ([61:195..207]; code not traced). |
| 2 | Send gifts | **confirmed** | 4.2, `0x0047FBB0` |
| 3 | Raid / attack a city | **confirmed** | 4.4: raid and conquer (`0x0047FA60`), allies, rivals and rebelling vassals/colonies |
| 4 | Establish trade with a city and break it off again | **wrong for Zeus** | 4.6: no player action and no cost. Trade with a city is on from the start (`trade_open = 1` for all, `city_init_from_map`); it is broken only by the city (trade suspended when displeased ≥ 50 streak, rebellion, becoming a rival) and restored by events/conquest. The player only sets per-good import/export at the post. |
| 5 | Per partner: capacity (quota) and goods in/out, over a map of the region | **confirmed** | 3.3 (Buys/Sells with used/quota, e.g. 0/12; Needs/Produces for non-partners), seen |
| 6 | A trading post only for a city you trade with, and only after good relations | **partly right** | 5: the city must not be a rival and must exist, be active and visible and trade something with a quota; there is no attitude condition and `trade_open` is not required. |
| 7 | If relations drop, the city's post stops working | **partly right** | 5, 6.2: the post keeps standing, but traders stop when the city suspends trade (displeased streak ≥ 50, allies/parent), rebels (vassal/colony), turns rival, or goes inactive/invisible. Attitude by itself does not stop trade. |

## 9. Details: expedition event and battle (fork B), request/gift events (fork A)
Event record (124 B `0x009173F4`, military.md "Events"): `+2` type (1 request, 2 invasion, 0x13 status,
0x14 army away, 0x17 city gift, 0x1D tribute in, 0x1E tribute out, 0x1F relationship letter, 0x20 granted
delivery, 0x21 refused demand, 0x22 ally strike), `+3` month, `+4` item (1..22 goods, 23 drachmas, 24 troops,
25 food, 27 strike), `+0xC` amount (loads for goods: units = amount·100, sculpture ·400), `+0x14` year
offset, `+0x1C/+0x1E` city id, `+0x24/+0x26/+0x52` chained events, `+0x28` flags (0x4 done, 0x10 debt
rescue, 0x100 dynamic, 0x200 enemy ×70 %, 0x400 late forces, 0x800 won early / attack averted, 0x1000 god
help, 0x4000 raid, 0x8000 ally joined, 0x10000 waiting at the target), `+0x2C` deadline months, `+0x2E`
countdown, `+0x30` state (0 waiting, 1 overdue, 2 early, 3 on time, 4 late, 5 failed, 6 accepted/away,
7 refused/won, 8 postponed/late, 9 troops present/lost, 10 done), `+0x32` active, `+0x58` target city,
`+0x60` kind (9 = player-initiated), `+0x6F` second city, `+0x70/+0x72` plunder good/amount, `+0x75/+0x76`
ally city/troops, `+0x77` sent strength.

Expedition (kind 9) monthly: invalid target (vassal/colony not rebelling, invisible, inactive) → forces home;
state 6: countdown −1 per month, at 0 wait at the target (flag 0x10000); on the due month: if > 2 months
late → state 8 (late, no battle); else battle → state 7 (won/raided: loot delivery on return) or 9 (lost);
return trip = travel months; then companies home, state 10. Messages 0xDE (0xD6F.. won, 0xD69.. lost,
0xB5E.. late).

## 10. Checklist: base game vs our sim (2026-10-28, before phase 2)
Sandbox relevance: **S** = happens in open play without scenario events, **M** = needs scenario/mission
events (we keep the mechanism, the sandbox has no such events).
| Feature | S/M | Ours before | Phase 2 (done 2026-10-28 unless noted) |
|---|---|---|---|
| Empire from the scenario (cities, kinds, relationships, goods, quotas, positions, routes, map picture) | S | no: 8 invented partners (data/trade.json), all simple partners | loader `sim/empire` from the `.map` (data/empire/*.json via tools/build_empire.py) |
| Trade partners = tradeable cities with `trade_open` | S | every partner trades | yes |
| Trade menu only for `city_tradeable` (gap 6) | S | any partner that trades | yes |
| Traders only from `is_trading_partner` (gap 7) | S | always | yes |
| Quota use per year, prices | S | yes | kept |
| Attitude drift, table, streaks, relationship letters | S | no | yes |
| Fatigues, army regrowth, monthly update | S | no | yes |
| Streak consequences: aid gift, trade suspension, rebellion, invasion | S | no | yes (invasion: event + announcement; the enemy army on the city map needs the military wave) |
| Tribute in (January) with room check | S | no | yes (goods into storage, overflow lost; no dialog: auto-accept) |
| Tribute out (after being conquered) | S | no | yes (needs being conquered: military wave) |
| Debt rescue gift | S | no | yes |
| Player gift (sizes, fatigue, refusal, delay, attitude formula) | S | no | yes |
| Player request (goods, money, food; fatigue; delay; rival demand vs strength; attitude cost) | S | no | yes |
| Request defensive aid (allied army on the city map) | S | no | event + bookkeeping; the army on the map needs the military wave |
| Request strike (ally vs rival, abstract) | S | no | yes |
| Raid / conquer (abstract battle, casualties, loot, conquest) | S | no | yes, with our company counts (soldiers do not walk out: military wave) |
| City → player requests (kinds 0..7), fulfil list | M | no | mechanism yes (CLI to schedule one), sandbox has none |
| City status changes (type 0x13) | M (+S via 6.2) | no | yes |
| Price change events | M | no | mechanism only |
| Relationship history | S | no | yes |
| World map screen, markers, routes, panel, buttons, dialogs | S | no | phase 3 (viewer/play/world.js) |
| Armies moving on the world map | S | no | yes (positions exported) |
| Hermes / gods / heroes in requests | S/M | no | out (gods and heroes excluded) |
| Colonies as adventure episodes, editor | M | no | out |

## 11. Our implementation: the empire module (phase 2, 2026-10-28)
Code: `sim/empire/` (self-contained; can be kept, replaced or dropped).
| File | What |
|---|---|
| `model.py` | `City` (one generic record per world city: kind, relation, attitude, streaks, buys/sells with yearly quotas, route, army, tribute, fatigues, history, map position), `Empire` (cities, routes, events, totals), predicates `exists/tradeable/trading/cls` |
| `scenario.py` | the one loader `load_scenario(map)`: `data/empire/<map>.json` -> records + the exe's map-start setup. A later loader can fill the same records from a simulated or saved city. |
| `world.py` | world files: `load_world(name)` (`data/world/<name>.json` -> the same records, validated field by field) and `migrate(g, empire)` (re-binds existing posts by partner name). Format: docs/world-format.md |
| `relations.py` | attitude drift/table/streak letters, army regrowth, status changes (type 0x13), attitude words, player strength |
| `diplomacy.py` | gifts, requests (player -> city), deliveries, city requests and tribute claims (fulfil), tribute in, city gifts (aid, debt rescue), streak consequences, spontaneous events |
| `war.py` | raids/conquests (abstract battle), ally strikes, defensive aid, rival invasions (announced; the battle in the city is the military wave), army positions on the map |
| `events.py` | the event queue (dicts) and the monthly dispatch |
Data: `tools/build_empire.py` -> `data/empire/sandbox.json`, `sandbox2.json` (cities with names from text
groups 21/139, goods renumbered for pre-Poseidon maps, world-object positions, routes with control points
and expanded dots; the sandbox's dot counts equal the map's own `+0x134` counts).

Interface to the core (the only calls in either direction):
- `empire.new_game(g)` from `Game.__init__`; `Game.load` sets `g.empire = None` (off) for older saves.
- `empire.day(g)` from `systems.run_day` once a day: day 0 month change (Jan/Jul drift, event dispatch),
  days 0/4/8/12 attitude table, day 2 monthly update (+ January tribute), day 4 strength peak, day 7 streak
  consequences, day 12 spontaneous events.
- `empire.command(g, op, args)` from `Game.command` (verbs in docs/play.md "World map").
- `empire.export(g)` for `GET /world.json` (sim/live.py).
- `empire.partners/trading/tradeable` for `sim/systems/trade.py` (partner list by city id, traders only from
  trading partners, posts only for tradeable cities) and `sim/live.py` `trade_menu`.
- The module calls `economy.goods_add/goods_remove/city_stock` (storage in/out, overflow lost as in the exe),
  `military.companies` (a company on an expedition carries `"away": event id`; `military.update` keeps it out of
  recruiting), `g.message`, `g.rng`, `g.city.treasury`.
- Switch: `empire off|on [WORLD] [--migrate]` (on/off only before any post/dock exists, unless `--migrate`,
  which re-binds posts by partner name; resets or carries the trade state). WORLD: docs/world-format.md.

Deviations from the exe (all deliberate or pending; keep this list current):
- (10-29) Incoming goods, money and troops are offers (`offers.py`, 6.8): `offers`, `offer [ID]
  accept|postpone|decline`; state.json "offers" + viewer/play/offers.js open them in the message window. A monthly
  re-offer with unchanged text is not logged again (ours). Category levels: `msglevel CAT 0|1|2` (the sim's copy of
  Options > Messages; play mode does not send it yet).
- (10-29) Expeditions take the picked companies and triremes (`companies ..`, `ships ..`; play mode: the army
  dialog 0x21); no heroes, sanctuary troops or allies' rows in the dialog yet; company casualties only lower
  company counts, which the daily recruiting refills from the houses once the companies are home.
- Rival invasions arrive on the city map (sim/military invaders.py; entry point drawn at the event's creation);
  defeat -> tribute out (mode 2), a second -> the city is lost. Accepted defensive aid appears at the map entry as
  event companies 21..30 (sim/military forces.aid_arrive), leaves after 4 months with no enemy (the sender loses
  them), "defeated" when its last company is gone (war.aid_lost). `cityinvade CITY [N]` stands in for scenario
  invasion events.
- Trade gating (6.8): a status change zeroes the buys/sells of a city that no longer trades (City.goods_flags,
  empire.partners); conquest reopens trade but not the flags, as the exe; Game.load (empire.loaded), every
  episode start (empire.new_game, the continue start's Game.load) and the colony's return (episode.back_from_colony)
  rebuild them for every city (relations.goods_flags_rebuild = FUN_00461360; bug 472). Not modelled: the gods' land/sea trade
  blocks and Hermes' countdown (gods), the scenario trade flag 0x00902D44.
- RNG: Python `random` on `g.rng`, not the exe's generator (fidelity is not bit-level, the decision log).
- City requests to the player exist as a mechanism (`cityrequest` stands in for scenario events); the sandbox
  has none, as in the exe. Hermes/heroes/god help are out of scope.
- The overview advisor's requests list, the attitude advice window and the history window are data in
  `/world.json` (play mode shows them in its own panels).

## 12. Open questions
- Exact x87 rounding of route dot interpolation (`FUN_004622F0`); exact dialog button sets of
  `incoming_goods_dialog` (fork A).
- Raid with a loss but survivors may still get loot (decompiled condition; check in disassembly) (fork B).
- Missing attitude clamp in `0x00477430` (sic?) (fork A).
- How scheduled-event ranges (+0x10.. min/max) are resolved at map start (`0x00467660`?).
- Tooltip text per army marker; message table ids → texts for the sim's message log.
- Overview advisor requests list (61:195..207): code not traced.
- Interface section: 11.
