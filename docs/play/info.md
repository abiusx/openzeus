# Play mode: building info windows (research + implementation, 2026-10-27)

Right click on a building opens the original's info window for its type. Code: `viewer/play/info.js`
(`window.ZInfo`: `size(b)`, `draw(b, L, T, cols, rows)`, `target(b)`); ui.js owns the frame, placement (at the
cursor: our rule) and the help/close buttons. Data: `data/play/info_panels.json` from `python3 tools/play_info.py`
(panel kind per sim key, text group, exe address, positions, staffing ladders, goods icons, and the text groups
it uses). Sim side (presentation only): `sim/export.py` `info_extra` adds `info` to each building record,
plus `goods_list` at the top level. Companions: docs/play/ui.md (frames, window size), docs/play/text.md (fonts, pen).

Evidence: **exe** = read in `re/decomp/zeus.c` (address given); **seen** = matched pixel for pixel on an oracle
screenshot (docs/re/oracle.md); **hyp** = guess (string order, similar panels).

## Verification
Oracle: the "See a working city" tutorial at 800x600, then `69:move X,Y; 70:rclick X,Y; 76:shot` (right clicks
before ~65 s are ignored; arrow keys at 61-66 s scroll). Our panel was drawn with the same values over the
screenshot (node + `text.js`, sprites from extracted/sprites) and compared pixel by pixel (tolerance 24/255):

| Window | Glyph/sprite px | Mismatch |
|---|---|---|
| Townhouse (twice) | 9,190 / 9,187 | 0 / 0 |
| Storehouse (11 goods, orders, limits, workers box, deliverymen) | 22,664 | 3 |
| Common Agora (6 vendor boxes, RIMS, workers, peddler line) | 20,195 | 180 (the food amount: our input value was a guess) |
| Maintenance Office | 10,583 | 0 |
| Fountain | 6,684 | 0 |
| Gazebo (decoration) | 3,105 | 0 |
| Park (gardens) | 4,647 | 0 |
| Palace | 5,358 | 0 |
| Tax Office | 6,756 | 0 |
| Stadium (status + workers; no show lines) | 7,274 | 0 |
| Sanctuary (Oracle of Apollo) | 25,371 | 0 |

Scripts (scratchpad, not in the repo): `.../scratchpad/info/check.js` + `check.py` (comparison),
`harness.js` (renders every key of a state.json headless to catch errors); screenshots `.../scratchpad/info/or*/s.png`.
Also checked in the browser on a second server (copy of the save; new export): storehouse, granary, agora
(from a stall), olive press, wheat farm, growers' lodge; and on the user's server (old export, no `info`): the house
window falls back to our reason string, no errors.

## Common parts (every panel)
- Title: 22C, centred in C*16 at T+10 (group:0, or 28:type). **exe, seen**
- Status paragraph: 11C at (L+32, T+status_y), width (C-4)*16. Staffing ladder (order of 0x00577D20): on fire,
  no road (69:4), no labour pool (69:5), halted, no workers, cursed, blessed, then >=100/75/50/25/<25 % ->
  the panel's ladder entry (`ladder` in the JSON; standard pattern g:8,7,2..6,9,10; industry/farm g:5..10 with 69:6
  fire; fallback 69:15/14/13/9). **exe** (Infirmary, College, industry, farm, storage), others **hyp** (string order).
- Inset: plain frame at (L+16, T+inset_y), C-2 cells, n rows. Workers line 0x00577290 at y0: icon SPR_POP_MAN+1
  (Zeus_Interface 542) at (L+40, y0+6); `" n" Employee(s)` at L+60 then `"(m " needed)` at L+70 (pen cumulative),
  y0+16 when fully staffed else y0+10 and the reason 69:k at (L+70, y0+26) width 400 (k: 1 nobody in the city,
  2 no road, 3 shift labour). 11CB. **exe, seen**
- Description g:1 at (L+32, T+H*16+desc_y) where the panel has one. **exe**
- Help (L+14, T+H*16-40), close (L+C*16-36, T+H*16-37) (0x005724E0; 428 for 29 columns, 444 for storage's 30: seen by sprite match, sanctuary-window/b.bmp; was 424 before 10-29). **seen**
- Count nouns (0x00508DD0): index k when n = +-1 else k+1. Group 8 has "Drachmas"/"Drachma" in that order, so the
  house says "Generated 38 Drachma so far in tax": that is the original (**seen**).

## Panels
| Panel (keys) | Function | Drawn | Evidence | Missing (sim lacks) |
|---|---|---|---|---|
| house (house, elite_house) | 0x0057F4E0, 0x00576DA0, 0x00576F60, 0x00577060 | title 29:level; food icon+total at (L+32,T+110)/(L+64); goods slots (L+142/252/362, T+110), (L+32/142, T+130): common fleece, oil; elite + wine, armor, horses; inset (T+148, 10 rows): occupants icon (L+34,T+158) + "n occupants" (+ "n too many" / "Extra room for n") at (L+50,T+168); tax 127:18 or "Generated n Drachma so far in tax" at (L+36,T+194); unrest 127:21..27 at T+214 (thresholds 2/11/31/51/71/91); hut: 127:28 at (L+36,T+234); status (L+32,T+36): fire 111:1, no road 69:4, else 127:(36+code) | exe, seen | tax is our monthly share (`tax_month`), not the year-to-date sum; plague lines (127:29); "bad buildings nearby" code 11 |
| empty lot (common house, 0 people) | 0x0057FF00 | 128:0 title at T+8, walker-list inset (T+40, 12 rows) with 70:0, 128:1/128:2 at H*16-113 | exe | the walker list |
| storage (granary, storehouse, endless_warehouse) | 0x005B2880, 0x005B38C0, 0x005B3660, 0x005B2420, 0x005B1DE0 | window x 0 / y 32 in the original, 30 cols, rows ceil(4n/3)+13 (n = goods listed: city goods of that class, wheat also in storehouses, no horses/chariots); status at T+36; storehouse "Storing n loads." / "Space for n loads." (T+58; x 34 / 280); granary 130:38 when full; rules (1-px black) and headers Stock/Orders/Stock Limit (9LTBK, T+76); rows from T+93 step 20: icon (L+15,y-4) if stocked, loads at L+33, name 23:res at L+65, both in one font (0x005B3660): 11LTYEL (font 9) when the good can't be taken in, else 11C (font 1) at 0 stock, else 11LTBLUE (font 15); "can't be taken in" = 0x005B3540 false = stock >= limit (0x0092152C) or all 8 bays hold something and stock % 400 == 0; the order does not enter it (ours approximates bays as sum of ceil(amount/400)); order 130:0..3 at (L+293,y+1), font by order byte (0x005B38C0): Accept (0) and Get (2) 11LTBLUE, Don't Accept (1) and Empty (3) 11C; limit/100 at L+398 in the order's font, 11LTYEL when 0x005B3540 is false; workers box (L+45, T+H*16-96, C-5 cols, 5 rows); deliverymen 130:27..33 at (L+50, T+H*16-56); interactive (below) | exe, seen | deliverymen state is approximate (walker out or not) |
| agora (agora, grand_agora; stalls open it) | 0x0057AA10, 0x0040B5F0, rects 0x005E86E8 | 97:0/1 title; 6 boxes 120x80 at (20,40),(170,40),(320,40),(20,150),(170,150),(320,150) with RIMS outline (hover variant +8): name 23:res (food 23:43) at +10,+10, icon +10,+35, amount (11LTBLUE; armor/horses /100) at +30,+35, state 97:k at +10,+60 (No Vendor 10, Not Buying 11, No Labor 19, Buying 18, No Goods 12, No Supply 14, Distributing 17, No Demand 13); inset T+242 5 rows + workers (sum of stalls); line at T+282: fire 23, no stalls 4, no road 69:4, no staff 3, peddler out 21 / returning 22 at L+64, waiting 20 | exe, seen | "Distributing" vs "No Demand" uses "peddler out" (the exe reads a per-vendor flag); the peddler's goods icon is not drawn (blank in the seen shot) |
| farm (wheat/onion/carrot farms, trees) | 0x00584520 | crop icon (L+10,T+10); "Production is n% complete." (T+44); status ladder (T+70); inset/workers; description | exe; browser-checked | trees: no status (they have no staff); "Land is fertile", "next harvest in" lines |
| industry (sheds, dairy, mines, quarry, timber, workshops, ranch, armory...) | 0x00582920 | output icon; gatherers "Holds n raw" (T+44); workshops "Production is n% complete." + "Stored grapes: n Loads" (T+60); status (T+75; input missing g:11 at T+86); inset/workers; description | exe; browser-checked | the raw amount unit (exe divides quarries by 100); mine "no ore" texts (group 105) |
| lodge (growers_lodge, fruit_lodge) | 0x0057DB80, 0x0057E2B0 | stored olives/grapes (T+36/56) or oranges; ladder at T+76; "growers out" at T+143; inset T+184; workers T+186; description H*16-75 | exe (ladder strings hyp) | "no trees", "path blocked" |
| gatherer (hunting_lodge, corral, fishing_wharf, urchin_quay) | 0x0057EEA0, 0x00585880, 0x0057B220, 0x0057B760 | stored meat line, corral progress, status/walker-state, workers | positions exe; state strings hyp | boat states (fishery), breeding grounds |
| service (infirmary, college, drama school, gymnasium, Atlantean schools, guild, tax office) | 0x00577D20 etc. | status at T+56 (guild T+60, tax T+72), inset T+136, workers T+142 | exe; infirmary, tax seen | tax-rate line (60:1 + rate) |
| wharf (trireme_wharf, 0x88) | 0x00583C60 (+ button 0x005724E0 / 0x00572490) | see "Trireme wharf window" | exe, seen (re/oracle/runs/wharf-window/w2.bmp: 0 px differ) | "Production is n% complete" needs the crew-all flag (not in the sim); the button state not seen on the oracle |
| tower (0x84) | 0x0057A3E0 | 16 rows; one status paragraph at (L+0x20, T+0x2d), (C-4)*16, 11C: fire 170:5, towers ordered unmanned (0x00FEAF24 == 0; ours `towers off`) 170:10, no road 69:4, no labour 69:5, no palace 170:8, not on the palace's road network 170:9, no workers 170:2, cursed 170:6, blessed 170:7, else 170:3 with a wall sentry (+0x2A) / 170:4 without; inset (L+16, T+0x97, C-2, 4), workers T+0x9d; no description. Sim: defences.tower_window -> info.tower | exe (browser-checked: unmanned, manned with sentry; no oracle shot) | Poseidon orichalc lines (170:11..15); a "." (170:1) at T+0xdc drawn with an image id as its font argument (left out) |
| venue (stadium, podium, theatre; observatory...) | 0x005792A0, 0x00579800, 0x00578DE0 | status T+56 (staffed -> g:3, idle g:2 not used), inset T+136 6 rows, workers T+138 | exe, seen (stadium) | "Current shows run for another n days" (T+182) and the show name (T+202): the sim has no shows |
| walker (maintenance, guardpost) | 0x0057BE20, 0x00579CC0 | walker state g:2/3 at T+56, ladder at T+104 (maintenance) / T+72, inset/workers | exe, seen (maintenance) | |
| fountain | 0x0057D750 | 108:(workers+2) at H*16-183, inset T+104, workers T+110; 14 rows | exe, seen | |
| decor (17 decorations) | 0x00577A10 | 137:2k title, 137:2k+1 at T+56 | exe, seen (gazebo) | |
| locality (avenue, boulevard, gardens/Park) | 0x00577870, 0x00577790, 0x00573540 | title, walker-list inset (T+40, 12 rows), 70:0 when nobody stands on it, text at H*16-113 | exe, seen (Park) | the walker portraits list |
| simple (columns, roadblock, gatehouse, rubble, palace, commemorative) | 0x00577950, 0x0057A2F0, 0x0057A200, 0x0057DA10, 0x0057BB50, 0x00577C50 | title + description at the exe's y | exe, seen (palace) | palace salary / rank lines; rubble's former building name |
| monument (sanctuaries, pyramids) | 0x005813F0 | 31 rows; title 28:type centred from L+20 in C*16-30; staffing 132:0..5 at (L+32,T+50); the god's three texts 132:(g+66/80/94) joined by spaces at L+20; prayer button RIMS (L+75,T+340,301x31) with 132:(10+g); inset H*16-108 (4 rows), workers H*16-102. **Under construction** (progress < 100, the exe's first branch; sim monuments.window via info.build): title 178:2 (22C centred paragraph at T+10, width C*16-30); from T+66 at L+20 (11C, step 16): 69:4 no road / halted 132:129-130 / no guild 178:0 / no artisans at work 178:1 / per material needed now (order marble, black marble, wood, sculpture, orichalc): 178:3..7 none in storage (< 400), 8..12 stockpiled, 13..17 shortage bit; activity 178:18..22 at y+16 (then y+32+h); 178:23 percent; 178:25 + 178:26..35 loads, or 178:36; Halt/Resume button 132:112/113 RIMS (L+75, T+440, 301x31), label centred at +8; no god text, prayer or workers box | exe, seen (Oracle of Apollo; Ares under construction: re/oracle/runs/sanctuary-window/b.bmp, 0 px differ) | prayer (`pray`, result text at T+0x127) and Consult Oracle (`oracle`; 132:110 when unavailable) work (10-29, sim/gods); 0 px differ vs re/oracle/runs/info-apollo/s.bmp (Apollo, 58/60 staff, both buttons) at dpr 1.25; the result text not seen in an oracle shot; halted state not seen |
| trade (trading post, dock) | 0x005B2880 (trade branch), 0x005B38C0 | see "Trade window" | exe, seen (oracle: re/oracle/scenarios/trade-window.txt, trade-window2.txt: 0 px) | |
| generic (race track, bridge, animals) | - | title 28:type, fallback ladder, inset/workers at the service positions | ours | hippodrome |

Other military buildings (checked 10-31 in info_window_background_draw 0x005720E0's switch): gatehouse 0x83 =
0x0057A200 (title 168:0, 168:1 at H*16-0x9E: the simple panel, already as the exe); armory 0x85 and horse ranch 0x87 =
info_panel_industry 0x00582920 (the industry panel); walls = the land window kind 0x18 (FUN_005776A0). Trireme wharf
and tower: ported (rows above).

## Trireme wharf window (2026-10-31, bugs.md 319)
Exe: info_window_background_draw 0x005720E0 case 0x88 -> FUN_00583C60 (info_panel_trireme_wharf); 29 x 22 cells
(info_window_class 0). Group 175 (Poseidon's frigate wharf: + 0x15 = 175:21..41, not ported). Positions from the
window corner, font 11C (font entry 1) unless said; paragraphs advance the pen y DAT_00F13A6C by 16 a line
(paragraph_draw 0x005090A0: 5 + font height).
- Title 175:0 centred in C*16 at T+10, 22C.
- Top line at (0x20, 0x2d), width C*16: no palace -> 175:18; else by status +0xBA & 0xF000: 0x1000 (building a
  trireme) and the crew-all flag 0x00FEAF20 (the Military advisor's "crew all" toggle, 0x0040A380) -> 175:2
  "Production is", the number progress (+0x54) * 100 / 320 with "%" at y 0x2c, 175:3 "complete." (two paragraphs:
  pen +32); 0x2000 (repairing) -> 175:16; else nothing.
- At y 0x37 + pen: 175:12 "Stored wood:" at x 0x20 + count noun 8:54/55 (wood +0x3C / 100, >= 0), 175:13 "Stored
  armor:" at x 0xe1 + armor (+0xDC) / 100; pen += 10 + 16 (the armor paragraph's 16 is overwritten).
- Status at (0x20, 0x37 + pen), (C-4)*16: fire 69:6, no road 69:4, no labour 69:5, crew sent home (C4 & 1) 175:4,
  no workers 175:5, cursed 69:10, blessed 69:12, staffing >= 100 / 75 / 50 / 25 / less: 175:6..10; pen += 10 + h.
- Trireme line at (0x20, 0x37 + pen), (C-4)*16: no trireme (+0xB8 == 0) and status not 0x1000 -> 175:17 "needs a
  trireme"; a trireme on the wharf's water-exit tile (+0xB6) -> 175:14; a trireme elsewhere: nothing (175:15
  "sailing" is never drawn).
- Inset (0x10, 0xdf, C-2, 4) and the workers line at 0xdf; description 175:1 at (0x20, H*16-0x3f), (C-4)*16.
- Button (only without a trireme): table 0x00642B38 = rect (0, 0, 384, 20) at (0x28, (H-2)*16), drawn by
  info_window_draw 0x005724E0 with window_highlight_draw (RIMS; hover variant while hovered, DAT_00781844); label
  175:(20 - (C4 & 1)) centred in 384 at H*16-0x1a: 175:20 "Send Wharf workers home." / 175:19 "Staff this Trireme
  Wharf." (the label, not a tooltip). Click (info_window_click 0x005726E0 -> 0x00572490 on release): if +0xB8 == 0,
  C4 ^= 1 (and redraw); nothing else (no trireme to send home). With a trireme the crew is sent home from the
  Military advisor's navy row (0x591400, `trireme ID crew`).
Ours: info.js PANELS.wharf; sim navy.wharf_window -> info.wharf {palace, trireme, at_wharf, status build|repair,
progress, crew_all (always false: the flag is not modelled)}; the button sends `staff X Y off|on` (C4 & 1 = misc
"off"; the command refuses a wharf with a trireme), the picked label shows at once (PEND). "build" = no trireme,
palace, road and (progress > 0 or wood and armor >= 200) (the exe sets 0x1039 on those and keeps it until launch).
Check (dpr 1.25, interface 80 %, window at (68, 32) as the oracle's): re/oracle/scenarios/wharf-window.txt (working
city, the wharf at (114, 66) with its trireme, crew home; shot w2.bmp) vs ours on a copy of saves/military.pkl with
the same values (wood 300, armor 300, crew home, trireme at the wharf, 0 of 100 workers): 0 of 163,328 px differ
(tolerance 24). The button (no trireme; copy with the trireme removed): drawn, hover variant, click -> "Staff this
Trireme Wharf." and 175:4, the server's info.off true; not on an oracle shot (the tutorial's wharf has its trireme).

## Storage window controls (2026-10-28)
All exe; clicks send `storage X Y GOOD ORDER [LIMIT]` (sim/game.py) via `sendCommands(cmds, {sound: false})`; the
picked value shows at once and is kept until a snapshot at or after the server's tick has it (PEND, as pages.js).
Endless warehouse: drawn, not clickable (the sim rejects orders there).
- Goods listed: storage_goods_list 0x005B12C0 over g_goods_list (rebuild_goods_lists 0x005BAAF0, sim/allowed.py
  goods_list, 11-01: the player city's resources with finished goods through their raw material (FUN_00460F90), a
  city selling it, a gift event naming it (FUN_005BA980), a finished Athena / Dionysus / Hephaestus / Hera sanctuary
  (god_resource_available 0x005BA890), tribute, stock, or once listed (0x00FE93EC: allowed.mark at the month change,
  episode start and storage creation)). Granary ids 1..8; storehouse 9..22 except horses (15) and chariot (22), plus
  wheat; trading posts: the list's entries the partner sells / buys. Ours, sandbox_open (no allowed table): every good
  some building outputs, plus held ones (export.goods_list). Oracle re/oracle/scenarios/1L-storage-lists.txt (Open
  Play Sandbox): storehouse window store2.webp at (0,32) 0 px over its rows (ours adds the "All goods" row and is
  taller: masked from y 311), granary window granary.webp top 480x150 0 px, the Distribution page's list at
  (598,30) 0 px; no carrots, onions or urchins (tests test_goods_list_sandbox).
  Storehouse: 13 rows; granary: 8.
- Order button (table 0x0065B330, 0x1C bytes/row): 110x20 at (L+291, rowY-3), RIMS hover variant only while
  hovered (0x00509230 is called only for the hovered row). Click 0x005B1670 cycles order 0 Accept -> 2 Get ->
  3 Empty -> 1 Don't Accept -> 0 (trade types 0x3F/0x40: 0 -> 1).
- Stock-limit arrows (table 0x01607560, built by 0x005B1B20): 17x17 at (L+425, rowY-2), SPR_SM_BUTTON_DOWN then
  SPR_SM_BUTTON_UP at +17 (frame +1 on hover: ours). Click 0x005B1610/0x005B1630 -> 0x005B1500: step 0x005B14B0
  (sculpture 400; else 100 below 1200, at 1200 100 down / 400 up, 400 above), clamped to 0..3200 (capacity).
  Sculpture stock and limit display /400 (0x005B3660, 0x005B38C0).
- "X" button (0x0065B310): 20x20 at (L+(C-2)*16, T+(R-5)*16), RIMS (hover variant when hovered), 130:11 centred at
  T+R*16-76 in font 11C (font_group_entry(1): hyp). Click 0x005B1C90: every good Don't Accept.
- **Deviation (user 10-28): "All goods" row** after the last good (not in the exe; the window is one row
  taller): one order button (cycles accept -> get -> empty -> don't accept from the common order, accept when
  the goods differ) and one pair of limit arrows (same steps as a row; from the common limit, the highest when
  they differ; each good keeps its order). Shows the common order/limit or "-". One `storage` command per good,
  sent as one batch. Verified in Chrome: order click set all 13 goods to get, down arrow set all limits 2800.
- Verified in the browser (own server, copy of saves/live-full.pkl): order cycling, limit 3200 -> 1100 -> 1600
  (steps as above), X; the server's `info.orders`/`limits` matched after each click; no console errors.

## Trade window (2026-10-28, bugs.md 117)
Ours, pending clicks (11-03, bugs.md 440): a toggle or limit the player picked is drawn until the window's own
/trade_post.json data was asked at a snapshot seq >= the command's (`val(key, actual, dSeq)`), not until S.seq is:
the data is re-fetched only once S reaches the new seq, so the old limit showed for that fetch's round trip.
Exe: info_window_open 0x005715A0 gives types 0x3D/0x3E (dock, trading post) 32 x 25 cells (fixed). Drawn by
0x005B2880 (trade branch) and 0x005B38C0 (rows); clicks in info_window_click 0x005726E0. Oracle shot: the
sandbox's Trading Post: Tiryns (re/oracle/scenarios/trade-window.txt, 800x600, window at x 0, y 32). L, T = the
window's top left; `local` = status height (20).
- Title "%s: %s" (0x0065B838: 28:type, city name 331:name_id; trade_building_label 0x005B9480 makes the same
  label for the Trade submenu) centred at T+15, 11C. Status (staffing ladder) at (L+32, T+36).
- base = local+0x26. Rule at T+base-5; 130:5 "Storing n loads." at L+0x22 and 130:6 "Space for n" at L+0x138
  (capacity 15*400 = 6000); rule at T+base+15; headers in 9LTBK at T+base+0x1F: 130:8 Stock (L+0x17), 130:14
  Price (L+0xC0), 130:15 Limit (L+0x166); paragraph 130:16 "Traded so far this year" at (L+0x197, T+base+0x14),
  width 100; rule at T+base+0x2B.
- Y0 = T+0x70+local. 130:17 "Imports" in 11LTBLUE at (L+0x20, Y0-26), 130:19 "None" when empty. Rows step 20:
  stock and name as a storage row (0x005B3660), price (goods_price) at L+0xC4 with the coin (packed 0x804) at
  (L+0xB6, y-6); toggle 103x20 at (L+0xF2, y-4) with RIMS on every row, the hover variant on the hovered one
  (0x00509230), label centred at y+2: imports 130:12 Buying (11LTBLUE) / 130:20 Not Buying (11C), exports 130:13
  Selling / 130:21 Not Selling; limit/100 at L+0x157 (11LTYEL when the good can't be taken in); arrows
  SPR_SM_BUTTON_DOWN/UP at (L+0x175 (+17), y-5); "used 44:148 quota" at L+0x1AB.
- Rule after the imports; exports ("Exports" 130:18) from E0 = Y0+20*imports+40; final rule at
  T+(imports+exports)*20+0x98+local. A partner not trading adds 0x14 to the layout (not seen).
- Workers box and deliverymen line: the shared tail of 0x005B2880, as in storage (box at T+H*16-96). Correction
  (10-28, bugs.md 138): 0x005B2880 is the window *background* (info_window_background_draw) and the rows come
  after it (FUN_005B38C0 from info_window_draw), so in the exe rows that reach the box (from 4 imports + 3
  exports on, H = 25 fixed by 0x005715A0) are drawn over it, text and buttons on the box. Ours (deviation, user
  10-28): the window grows until the last row ends 4 px above the box (rows = max(25, ceil((last row y + 116) /
  16)); 4+4 -> 27), so no row touches it. Checked at dpr 1.25: Susa (4+4) all rows shown, the rule 4 px above the
  box is unbroken black and the marble row above the box edge has no glyph pixels.
- Clicks: toggles tables 0x0065B790 (imports) / 0x0065B720 (exports); orders byte storage+0xC4: 5 import on,
  6 off, 7 export on, 8 off. Limit arrows tables 0x016073A0 / 0x01607480 (built by 0x005B1B20), callbacks
  0x005B1650 / 0x005B1630 -> 0x005B1500 (step 0x005B14B0, clamp 0..6000). Ours sends
  `trade X Y GOOD import|export|off [LIMIT]` (sim/game.py), data from sim/live.py `/trade_post.json?id=B`
  (partner, sells/buys with yearly quotas, used, orders, limits, prices, goods, capacity, units).
- Next / previous trade building (10-30, bugs.md 20): image table 0x0065B800 drawn by 0x005B2880 when trading posts
  + docks (0x00782CF0 + 0x00782CF4) > 1: SPR_BUTTON_LEFT at (L+0x1BE, T+9) (arg 1, previous) and SPR_BUTTON_RIGHT at
  +24 (arg 0, next), 24 x 24, type 4: the pressed picture (+1) while held, no hover look; the press fires at once
  and repeats while held (FUN_00431C80, as the limit arrows). Click 0x005B1CE0: from this building's storage record
  index (building +0xD1) step +1 / -1 (wrapping 1..199) to the next record in use whose building is a dock (0x3D) or
  post (0x3E) and not this one; open its window (0x00570B20, 0x005715A0) and centre the view on it (0x0044A7D0).
  Ours (info.js `tradeCycle`): trade buildings by id (the exe's storage records are taken in build order: oracle
  1F-trade3 dump, posts 1 and 17 in records 1 and 2; a record freed by a demolition and reused would differ).
  Rules: 0x00509700 draws x1..x2 inclusive: the window's rules are cols*16 - 31 wide (were 1 px short; storage too).
  Checks (dpr 1.25, interface 80 %, ?tex=png, tools/screens_check.mjs --size 640x480 + screens_compare.py, window
  rect 512 x 400; oracle at (0, 34)): re/oracle/scenarios/trade-window2.txt run 1F-trade2: two.bmp (Tiryns, 2 posts)
  0 px; held.bmp (Aulis, right button held: `--each "UIX.mouse=[482,51]; UIX.down=true"`) 0 px. A click on next /
  previous switches the window (ours, CDP: ids 1 -> 2 -> 1 -> 2).

## Land window (2026-10-29)
Exe: a right click on a tile with no building opens info window kind 1 (FUN_005717D0 -> FUN_005731D0, 29 x 22). Its
kind 0x00FFA138 comes from the tile's terrain (FUN_005717D0's chain; ours sim/live.py `land_kind`, `/land.json`):
1 trees, 2 rock (0x10 copper, 0x11 silver, 0x1F orichalc), 3 water (0x1B fishing spot, 0x1A urchin spot within one
tile, table 0x00902BC4), 6 road (also the road through an agora), 7 marble quarry (0x1E black marble), 8 rubble
(the ruin panel 0x0057DA10), 0xA empty land, 0xB water crossing (bridge tiles: the exe has no building there, grid
0x00CB4B08), 0xE / 0xF the entry / exit road tile, 0x13 beach, 0x14 submerged beach, 0x15 marsh, 0x18 wall
(FUN_005776A0: title 166:0, text 166:1 at (L+0x20, T+H*16-0x9E), no figure row), 0x19 meadow, 0x1C/0x1D lava; 0xC
park terrain (FUN_005775B0, group 75) is our gardens building. Drawing: title 70:(k+10) in 22C centred at T+10 only
when no figure is listed; the figure row (FUN_00573540) with 70:0 centred at T+0x78 in 11CB when empty; the text
70:(k+41) at (L+0x24, T+H*16-0x71), width (C-4)*16, except kinds 0, 6 and 0xD. Ours: a right click on land always
opens it (before 10-29 only with walkers around); a bridge opens the land window (kind 0xB) with its walkers; a wall
building the wall panel. Not ported: cracks (5: earthquake pieces), the land sounds (wavs/empty_land.wav...).
Check: oracle re/oracle/runs/land-window/s.bmp (tutorial, right click at (30,80): "Empty land") vs ours on a save H
copy (tile 100,100) at the same place, read back at dpr 1.25: 0 px differ.

## Sim fields added (sim/export.py, presentation only)
`goods_list` (city goods); per building `info`: houses `code` (the exe's evolve_reason computed from our housing
rules without changing them), `road`, `taxed`, `unrest` (our crime), `room`, `food`, `food_types`, `tax_month`;
others `road` (false only), `labor` (false: no reachable workers), `off`, `out` (own walkers out), storage
`orders`/`limits`, workshop `progress` %, orchard `ripe`, agora `stalls` [{key, employees, need, buying, reason}],
`peddler`, `returning`, trireme wharf `wharf` (sim/military navy.wharf_window), tower `tower` (defences.tower_window). A running server must be restarted to send them; without them the panels fall back
(house status = our reason string; no tax/unrest rows; storage rows from the building's goods).

## Open
- Hippodrome, Poseidon/Atlantean panels in detail (frigate wharf 175:21..41, tower orichalc lines). Trade window: the next/previous trade building buttons.
- Trireme wharf: "Production is n% complete." needs the Military advisor's crew-all flag 0x00FEAF20 (not in the sim).
- Ladders marked hyp; exact strings for fishery/urchin states; venue show lines (sim has no shows).
- Farm/industry/lodge windows were not captured on the oracle (the tutorial view drifts; clicks landed elsewhere).

## Walker window (2026-10-28, bugs.md 80)
Exe: a right click opens the info window of the clicked tile (FUN_005717D0): the building's if there is one,
else the land window (kind 1, FUN_005731D0; 29 x 22 cells). Its figures: those on the tile, then on the 8
neighbours in the order of 0x00642AF8 ((0,0) (0,-1) (0,1) (1,0) (-1,0) (-1,-1) (1,-1) (-1,1) (1,1)), at most 7,
not types 0, 6, 10, 24, 34, 35, 45, 46, 52, 54 nor dying ones; each gets its phrase picked then (FUN_005ABB90).
With no figure: title 70:(kind+10) and 70:0 in the inset. Drawing (**exe**, positions from the window corner):
- figure row (0x00573540): inset (L+16, T+40, cols-2, 12 rows; 15 for types 4, 9, 36), RIMS boxes 52x52 at
  (L+25+60i, T+45), the selected one highlighted, each with a 48x48 crop of the map at the figure (FUN_00572FE0,
  below).
- selected figure (0x005740A0, default branch): RIMS box (L+24, T+102, (cols-3)*16, 122; 167 for carts),
  portrait at (L+28, T+112) = Zeus_Unloaded SPR_FIG_PORTRAIT first + type (FUN_00573880; special cases for
  soldiers, gods, carts with heavy goods...), name = name group (figure table +0x18, overrides in
  figure_name_group 0x004E34F0) entry name_index, 22C2 at (L+90, T+108); 64:type in 11CB at (L+92, T+139);
  thought = thought group (table +0x10, overrides 0x004E3750) entry phrase, 11CB at (L+90, T+160), width
  (cols-9)*16. Many types add lines (cart: origin building, cargo icon and loads; peddler: 129:3 "Sells" +
  goods; soldiers; traders...).
- phrase (FUN_005ABB90): flag byte 0 (table +0x14): danger nearby (FUN_005A97A0: enemies, monsters, angry
  gods) gives 0 (+7 with flag byte 1); else an action phrase (FUN_005A9C20) + 1 (+7); else with flag byte 1 the
  city's mood (FUN_005A96F0): weights (FUN_005A9550) health < 20/30/40 -> 8/6/4, food months in stock < 1/1 ->
  6/4, unemployed % >= 18/11/6 -> 8/6/4 (else 1 each), rebel/vassal city counts -> 8/6/5; no problem and
  sentiment >= 40 -> 6; else a random weighted pick, a weight-1 pick among the first three -> 5.
Ours: viewer/play/ui.js openWalkers (right click: the frontmost walker picture under the cursor first, unless it
stands on the clicked building's own tiles (horses in the corral, a boat at the pier: the building, as the exe's
tile rule; 10-28), then the building, then the land window with the walkers around), info.js ZInfo.drawWalkers /
drawFigure, sim/live.py `/walker_info.json` (walker_info, walker_phrase), data/play/walker_info.json
(tools/play_walker_info.py: role -> exe type, name / thought groups (also by home: miners 218/219/220/343, agora
vendors 222..227 and names 258/266/267/268, figure_name_group 0x004E34F0 / 0x004E3750), flags, texts). Right click
anywhere closes the window (info_window_click 0x005726E0, bugs.md 109).

Ported 10-29 (spec read from the exe: FUN_005ABB90, FUN_005A97A0, FUN_005A96F0/FUN_005A9550, FUN_005A9C20,
0x005740A0, 0x005ABE80):
- Phrase pick at open: danger (an invader within Chebyshev 5; soldiers only fear gods / monsters: none) -> d +
  7*flag_b; else the action phrase a + 7*flag_b + flag_a; else with flag_b the city's mood (weights health, food
  months 0x00FE9570, unemployment (0 for rural figures), vassal / rebel 0; r = rng & total as the exe; 6 when no
  problem and sentiment > 39). Action phrases map the sim's walker states to the exe's actions (ours: approximate
  where the sim has no such action): immigrant / vendor assistant cycle 3, emigrant and criminals by the worst
  sentiment cause, vagrant alternates, cart waiting with nowhere to go 1 / trip > 24 tiles 2, peddler going back
  cycles, superintendent at a fire cycles else 50 % 4, healer health < 40, agora vendor collecting / returning,
  watchman fighting 4 or the unrest of the houses around him (ours for +0x66), artisan walking / working (pyramids
  2 / 3), grower tend / pick by olive / vine, shepherd / goatherd / hunter / woodcutter / miner / boat / diver /
  rancher by out / work / back with the exe's 50 % draws. The exe draws its game RNG for the 50 % and mood rolls;
  ours a stable per-walker draw (no effect on the simulation).
- Types: a cart from a storage or post is the deliveryman 36, the agora stall's buyer is the agora vendor 37 (was
  36). Lines (positions from the window corner): carts (box 167): 28:home + 64:4 at (92,139), cargo icon (92,155) and
  "n load(s) of" / "block(s) of" + 23:good at (110,157), route "Going to <dest> from <home>" / "Returning to <home>
  from <dest>" (129:15/16/14) in 11C at (60,295), thought at (40,210) width (C-4)*16; peddler 64:26 + "Sells" + its
  agora's goods (icons step 32); agora vendor "Collecting" / "Returning with" + goods; vendor assistant "Carrying";
  hunter back "Returning with" + meat; miner 274:k (mint, foundry, refinery, quarry); animals 64:type (deer 129:23)
  at (92,118), no thought; traders (no portrait / name / thought): 64:type + city at (40,110), status 129:6..13 at
  (40,150), "Bought" / "Sold" with count + icon per good (ledger), else "Buys" / "Sells" with the city's goods with
  quota left, icons step 25. Portraits: carts 80 (heavy cargo) / 9, vendors by good 74..78, miners 72 / 73.
- 'Tell me more' (SPR_TELL_ME_MORE_BTN at (418,204)): for mood figures while another weight >= 2; the click as
  0x005ABE80 (its weight-vs-index compare kept).
- Checked in Chrome on a save H copy (dpr 1.25): cart, peddler, copper miner, caravan with a ledger, agora vendor,
  shepherd. Not compared with an oracle shot (the exe's walkers differ from ours; the layout follows the code).
- Figure crops (10-30, FUN_00572FE0, called by every window with a figure row, each frame): per figure FUN_00572F50
  finds its tile's view cell (FUN_00449F80 in grid 0x007D3BEC; view 0: row x + y + 1, column (230 + x - y) / 2,
  FUN_00449FF0), sets a 5 x 15 cell view at (0, 30) (map_view_set_size via 0x0051CC50, clip (0,30)-(298,240)) with
  camera column - 2, row (row - elevation - 6) & ~1, and city_draw draws it with walker_draw's param_4 = that
  figure (every other figure returns; the figure stores its picture's top-left in 0x007D3B3C/38); FUN_00413C50
  copies the 48x48 there (x >= 0, y >= 30, the top bar's height) and FUN_00573540 blits it to (L+27+60i, T+47).
  So the box shows the map at 100 % at the figure's own picture's top-left (a cart: the pusher), the figure alone;
  the clamp moves it only for tall figures or high ground (the figure's tile point sits at (90 / 120, 105 + 15 e +
  15 p) in the small view, p = row parity). Ours (play.js drawCrop / cropOrigin): the frame's draw list without
  other figures' entries (scene.js tags each entry with its walker id, ox pairs / trailers / assistants / company
  standards / statues as other figures), tall terrain over the box, drawn at the interface scale into the box with
  a GL scissor between the UI batch's pieces (ui.js UIX.cuts, gl.js Batch.draw(a, b)). Checks (dpr 1.25, 80 %,
  ?tex=png, tools/walker_crop_check.mjs + walker_crop_compare.py): oracle re/oracle/runs/1D-walker
  (scenarios/walker-window.txt): the exe's crop = its map b.bmp at (144,391), 100 %; the pusher picture at crop
  (0,0). Ours, a test fishery cart on a new sandbox: crop = map 0 of 2304 px, a second cart beside it left out (242
  px differ, all its own), pusher 0 of 241 px vs the exe's crop, RIMS ring 0 of 400; the cart picture differs by
  the exe's (+2, +10) (bugs.md 251). Baseline copy, a cart beside the palace, tower, gatehouse, Athena / Apollo
  sanctuaries, ranch, agora, elevation-4 hill: crop = map 0 px each; views 2 / 6 0 px, view 4 72 px = a company
  standard left out. Not shot: a clamped crop (tall figure, high ground).
- Not ported: the soldiers' company panel (FUN_00524CA0), enemy soldiers / trireme / Poseidon figures' lines,
  the entranced follower (case 0x47), the voice clips (0x0064BF94).

## Gods, monsters and heroes in the walker window (2026-10-31, bugs.md 325)
Exe (0x005740A0, after the RIMS box (L+0x18, T+0x66, (C-3)*16, 0x7a)); id = Figure+0x60 (the god, monster or hero):
- God (type 0x43): portrait (FUN_00573880) Zeus_Unloaded SPR_GOD_PORTRAITS + id (font_group_entry(10) + 0x8000; Hera /
  Atlas: Poseidon_Unloaded SPR_HERA / ATLAS_PORTRAIT, entries 0x10 / 0x11 + 0xC000) at (L+0x1c, T+0x70); 157:id in
  22C2 at (L+0x5a, T+0x6c); 158:id (title) in 11CB at (L+0x5a, T+0x8a); 83:(the god record's unfriendly byte) "Friendly
  God" / "Unfriendly God" at (L+0x5a, T+0x9e); the phrase (FUN_004F1C30: thought group by id from FUN_004E3750 300,
  301, 303.. 0x12C..0x137, 0x161/0x162; Figure+0x7D) at (L+0x5a, T+0xb2), width 0x15a.
- Monster (0x44): SPR_MONSTER_PORTRAITS + id (Sphinx, Chimera, Harpy, Echidna from Poseidon_Unloaded), 190:id in 22C2,
  the phrase at (L+0x5a, T+0xa0), width (C-9)*16. Hero (0x45): SPR_HERO_PORTRAITS + id (packed 0x40C; Atalanta /
  Bellerophon 0x61A / 0x619), 185:id in 22C2, 64:69 "Hero" at (L+0x5a, T+0x8b), the phrase at T+0xa0; Tell me more as
  other figures with the mood flag.
- Phrases (FUN_005ABB90 -> FUN_005A9C20): god (no flags): its action phrase only: action 8 / 0x0C (visit, bless) 0;
  per god (cases by id): Zeus hostile (god_figure_hostile: unfriendly and listed) 2, 0x3C / 0x50 1; Poseidon, Hades
  hostile 1; the others hostile 1, then their help actions 2 / 3 (Demeter's food, Apollo / Aphrodite 0x19 / 0x1A 2 and
  0x50 / 0x4A 3, Artemis 0x21 2 / 0x1B 3, Ares 0x22, Hermes 0x57, Athena 0x25 / 0x29 2 / 0x4C 3, Hephaestus 2 with a
  monster on the map, Dionysus 0x2B); else none (-1: no line). Monster: 0. Hero (both flags): danger (an enemy, an
  unfriendly god or a bad monster within 5: FUN_005A97A0) 7; a type-26 event active in state 4 (a monster on the way)
  0 + 7 + 1 = 8; else the city's mood.
- Priest (0x41, now listed: name group 254, thought 237, danger flag): to an offering (action 7) goat 0 / sheep 1 /
  cattle 4, leading or carrying it (10) goat 2 / sheep 3 / cattle 5, + 1; danger 0.
- The figure list excludes missiles (types 45 / 52: ours the "arrow" looks: arrows, god bolts).
Ours: sim/gods walker_window (the sim's task for the exe's action: an approximation where the exe's action is finer;
"jealous" = 0x57), sim/heroes walker_window, sim/live.py _figure_info / walker_info; data/play/walker_info.json
(tools/play_walker_info.py: roles god 67, monster 68, hero 69, priest 65; thought_by_res; portraits); info.js
drawFigure. A figure standing in a look (a god appearing / blessing / casting, fighters, herders at work) had no hit
rectangle (scene.js drawFight), so a right click on a god went to the tile under the cursor, whose walkers did not
include it (bugs.md 325); drawFight now adds its picture's rectangle. Checked headless (dpr 1.25, own server, copies
of saves/live-full.pkl and a new sandbox): Athena visiting (name, title, Friendly God, 304:0), the Maenad (326:0),
Achilles (Hero, 312:6 the city's mood). Not compared with an oracle shot (none of a god / monster / hero window).
- A figure gone on the server (11-04, user: Demeter's window drew only its list box while she glowed at her vanish;
  bugs.md 457): the tab draws its frames behind the sim (2-4 ticks at 30/s headless, more after a stall), and
  walker_info answered only walkers still alive, so a god asked about during her last vanish ticks came back empty
  (info.js drawWalkers draws the rest only with a record). The exe's window reads the figure slot, whose data stays
  after the figure is gone (0x005740A0 has no state test). Ours: sim/live.py Runner keeps the walkers removed in the
  last GONE_KEEP = 3000 ticks (gone_walkers, from record_frame's previous walker map) and walker_info answers from
  them (record flag `gone`). Checked headless (own server :8791, a save C copy at speed 30): Ares opened at
  P.t 321478 after the sim removed him at 321480: portrait, name, title, "Friendly God" drawn
  (test_walker_window_gone_figure).

