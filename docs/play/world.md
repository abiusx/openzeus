# Play mode: the world map screen

The exe's world map (screen 0x14, docs/logic/world-map.md section 3) in play mode: `viewer/play/world.js`
(`window.WorldMap`), data `data/play/world.json`, server export `GET /world.json` (sim/empire `export`).

## Reproduce
```
re/venv/bin/python tools/play_world.py   # needs pefile; reads zeus-original/app/Zeus.exe
python3 tools/build_empire.py            # data/empire/sandbox*.json (cities, routes, map picture number)
```
Inputs: `zeus-original/app/Zeus.exe` (GOG build, SHA-256 382bcd28…75e90a57), `zeus-original/app/DATA/Zeus_MapOfGreece01..10.JPG`,
`extracted/text/zeus_text.json`, the play-mode atlas (tools/play_ui.py). Outputs: `data/play/world.json`
(widgets from the draw table 0x005EF488 with handlers, panel layout from FUN_005981B0, fonts, icons, text groups)
and `viewer/play/atlas/world/*.jpg` (copies of the original pictures, git-ignored).

## Hooks (kept small; the rest is in world.js)
- `viewer/play/ui.js`: the control panel's world-map button calls `WorldMap.toggle()`; while open, `uiDraw` calls
  `WorldMap.draw(R)` instead of panel/submenu/info, `uiDown` forwards to `WorldMap.down`, `inUI` returns true.
- `viewer/play.html`: loads `play/world.js` after ui.js.

## Decisions
- The picture uses the minimap's texture unit (all 12 sheets are taken): world.js binds its own texture there while
  open and restores the minimap's on close.
- City labels (bugs.md 118): as world_map_draw 0x00599DA0: the mask font SPR_FONTS (font group 0) in RGB555 0x7F39
  (0xFE59 in 565 mode: the same colour), no shadow, measured with that font for the left / centred placements. gl.js
  draws a sprite pushed with alpha -(2 + colour) as that solid colour (the glyph-mask blitter 0x00416C30; the oracle
  shows each 5-bit channel << 3: 248, 200, 200).
- Marker origin (bugs.md 118): the exe clamps its scroll x to picture w - view w - 1 when it reaches it, draws the
  picture at the clamp to 0 and everything else (routes, icons, names, armies, the click test) at the -1: with the
  whole width shown (1024 x 768: picture 838 = view 838) every marker is 1 px right of the picture. world.js
  `view().mx` (ours: whenever the scaled picture is not wider than the map area).
- Dialogs (bugs.md 122): see "Dialogs" below. They send the sim's CLI verbs (docs/play.md).
- Text: every panel and dialog text goes through world.js `box()`: wrapped to its box (exe widths), fixed rows one
  line; `WorldMap.overflow` lists any text still wider than its box (empty in the checks; bugs.md 124).
- Module off (`empire off`, old saves): the scenario's picture, no markers, a centred frame listing data/trade.json's
  partners (they have no map position; none is invented) (bugs.md 125).
- Orders button: closes the map, centres on the city's trading post and opens its window.
- Zoom (ours, a screen-size adaptation, the decision log 10-29; bugs.md 205): the exe shows its 838 x 738 picture whole
  beside the panel at 1024 x 768 (its edge scroll only matters at 800 x 600). Ours opens the map at "fit": the whole
  picture centred in the map area, scaled by k = min(vw / 838, vh / 738), so no city is ever under the panel at any
  window size or UI scale. Zoom in from there with the wheel (about the cursor), E/Q and the bar's -/+ (play.js
  zoomAt forwards to `WorldMap.zoomBy` while the map is open), up to 4 picture px per UI px; zooming out stops at fit.
  While zoomed, the edge scroll and WASD/arrows (bugs.md 197) scroll it. Picture, routes, markers, flags, armies and
  names scale together (names are drawn as sprites after the markers); clicks map back through k.
- Side panel goods lists (bugs.md 204): the exe's layout (FUN_005981B0: title, one SPR_COMMOD_BOXES bar per list,
  rows every 20 px with the good's icon, name and "used/quota" with the quota raised to used) for every city with at
  most 4 + 4 goods and 5 in all (every Zeus city). World files may have up to 10 (partners: 7..9); the exe's pitch would
  run into the tribute box, so ours keeps the same pieces at a tighter pitch: each list's bar stretched from the 1-row
  picture, icons scaled to the row, names in one column after the widest icon. "Leader:" is drawn for every existing
  city as the exe does, also when the world file gives no leader (partners' are empty).
- Running city (ours, user 11-04; bugs.md 467): the exe pauses the city while the world map is open (screen 0x14:
  screen_pauses_sim 0x0063D8B8 non-zero, simulation_due 0x005168A0). Ours keeps it running by default: the dev bar's
  Options ▾ "Pause on the world map" (off by default; on = the exe's pause; play.js PAUSE.world, saved in the play
  prefs with the other pause switches) decides whether `screenPauses()` counts the map. While it runs: the playhead
  and the top bar's date advance as over the city; `/world.json` (+ heroes.json quests) is fetched every 400 ms
  instead of every second (armies, cities, trade, requests follow the sim); commands from the map's dialogs go
  through the same POST /cmd as before (the tab stays live); a message window or offer pops up over the map
  (`WorldMap.holdsPopups()`: held while the map pauses, or one of its dialogs, the colony choice or the army dialog
  is up) and its go-to button closes the map. Checked headless on a save C copy (:8791, dpr 1.25, speed 30):
  switch off, map open 30 s: tick 363723 -> 364619, the raid army (322,321) -> (216,329); switch on: tick frozen at
  364687, army unchanged; no "slow" stall either way; a gift sent from the open map was accepted; a message window
  drew over the map and its close button closed it with the map still open.

## Dialogs (screen 0x1A, FUN_00464C00 by the mode at 0x00903440)
Each centred on the map area (FUN_00597E20: w = panel x + 16, - 16 above 800 wide; x = (w - W) / 2) and the screen
height (y = (H - h) / 2); rows are the builders' rects relative to the dialog; a right click goes back one level
(gift size -> gift list, strike list / confirm -> request) or to the map; no close button.
| mode | dialog | builder | frame | texts |
|---|---|---|---|---|
| 0 | favour advice (widget 2) | FUN_004652C0 | titled 30 x 23 at ((w-480)/2, (H-368)/2); plain 28 x 18 at (+16, +64) | 44:290 22C centred in 448 at y+16; 92:k paragraph 11C2 at inner (+8, +8), width 432 |
| 1 | request (widget 3) | 0x00465070 | 520 x (max(1,n)*28 + 60) | 41:1 9LTBK centred at y+16; rows (20, 40+28i, 480 x 27): offered = RIMS box + icon (+5, +3) + 41:3..8 at (+30, +10); not offered = the reason 41:9..18 at (+0, +10); none 41:19 at (20, 50) |
| 2 | gift (widget 5) | FUN_00464EE0 | 200 x (n*28 + 60) | 41:0 centred; rows (20, 40+28i, 160 x 27): box, icon, 23:item at (+30, +10); none 41:20 |
| 3 | gift size | gift_size_dialog 0x00463E40 | 300 x 144, frame (300 + 0x41) >> 4 = 22 columns | 41:0; rows 0x005FB900 (20, 40+28k, 310 x 24): box, icon, 41:22..24 ([amount] = units / 100, sculpture / 400, drachmas as is; [item] group 98) at (+44, +10) |
| 5 | requests by the city (widget 4) | world_map_btn4 0x00406B00 | 496 x 416; plain 26 x 19 at (+32, +90) | 41:2 11C centred; 7 rows 0x005FB958 (38, 96+42k, 400 x 40) with a scrollbar (x+0x1C6, y+0x60, h 0x126) past 7; row: SPR_REQUEST_COMPLETE / _INCOMPLETE (FUN_004713E0: enough stock or Hermes) at (x+46, ry = y+102+42k), icon at +20, amount + name (98 when > 1 or marble, else 23; troops: name only at +50) at +40, the stock count at (+40, ry+18), "overdue" 61:205 or the months + SPR_MOON at +0x11C / +0x13C; font 11C2 when it can be paid, 11C3 for a rival, else 11CB; none: 41:21 11CB centred at y + h/2 |
| 6 | history (widget 10) | wm_sub_4651D0, FUN_00463270 | 592 x 368; plain (x+16, y+64) (w-80 [+48 without scrollbar]) x (h-80) | 44:284 22C centred in the inner width; rows of 16 from inner y + 8: SPR_THUMBS + mood (change < -65: 5, < -33: 4, < 0: 3, 1..32: 0, 33..65: 1, > 65: 2) at (+5, -4), 25:month at +0x19, the year at +0x28, the text at +0x7D, 9DKBU; 17 rows, scrollbar past that; none: 44:83 centred |
- Request rows: an item is listed when city_can_request 0x0042DF90 returns true (code >= 0); code 3 with threshold
  0..3 = offered (41:3 + threshold, troops 41:7, strike 41:8); else the reason by code (0: 13 troops / 14 strike / 16
  food / 15; 1: 17 troops / 18; 2: 9 / 10 / 12 food / 11; else 12). [item] is the group-98 name ("skeins of fleece").
  sim/empire/diplomacy.py `can_request` follows 0x0042DF90 (10-30): troops / strike "can't spare" is code 1 (also
  while the city's own troops request is open, 0x0042DF40), not 0; no strike-target check there.
- Advice index: group 92, base by city_class (ally 0, rival 9, vassal 18, colony 27, parent 36) + 5 when the pleased
  streak (+0x168) is 50, + 6 above 20, + 8 when the displeased streak (+0x16C) is 50, + 7 above 20, else by attitude
  (> 80 + 0, > 60 + 1, >= 40 + 2, >= 20 + 3, else + 4) (FUN_00465330).
- Strike target (10-30, as the exe; world.js strikeOpen / strikeList / strikeConfirm): the strike row (wm_sub_4066F0,
  item 0x1B) -> wm_sub_464D50: the cities FUN_0042DB70 accepts as targets (existing rivals, g_cities order) in screen
  0x0F's list (FUN_005BEFE0 / FUN_005BF1E0, flags 10): titled frame at the absolute point (150, 50), 13 cells wide,
  (n*21 + 24) >> 4 high, names (21:name) centred in 196 at (155, 64 + 20k), 11C, hovered 11LTBLUE; a click elsewhere
  goes back. None: screen 0x3F 5:0x48/0x49 with one button. A pick (wm_sub_4067B0) -> screen 0x3F (FUN_00432380 at the
  640 x 480 origin + 0x50; FUN_00431370): titled 30 x 10, title 5:0x4A 22C centred in 480 at y + 0x14, 5:0x4B "Ask
  [city_nameA] to attack [city_nameB] ?" 11C at y + 0x3C (a paragraph 0x1A4 wide at x + 0x1E when wider than 0x1A3),
  buttons table 0x005EF938 (OK SPR_BUTTONS6 324 at (256, 100), cancel 328 at (192, 100), 34 x 34, + 1 hovered); OK
  (wm_sub_406740) = city_player_request_create(city, 0x1B, target), then the request dialog again (redrawn). The
  popups draw over the screen as it was: the request dialog under them keeps the clicked strike row lit, the list
  under the confirm keeps the picked city lit.
- History rows (10-30, as the exe): records of FUN_0042EEC0 (list 0x007796D0, 2000 x 16 bytes: +0 year, +4 month,
  +5 the city whose history it is, +6 attitude change (thumbs; 0x91 when unset), +7 relation byte, +8 phrase id, +10
  item, +12 the city concerned, +13 importance), newest first (FUN_0042EE40). Text (FUN_004669E0): the eventmsg
  `*_history` phrase with [city_affected] = 91:relation (wm_sub_466780: 0 "this city", 1 "an ally", 2 "a rival",
  3 "a vassal", 4 "a colony", 5 "your parent city") and [itemshort] = 23:item (wm_sub_465E00). Writers ported
  (sim: relations.note / attitude_add with the phrase): city_receive_gift 0xBF1..0xBF4 (own record always, others of
  the class when the share is not 0), city_request_attitude_effects 0xC75 goods / 0xC76 troops / 0xC77 strike (also
  an ally joining an attack, 0x00483790), request_resolve_attitude (kind base 0xC36 / 0xC46 / 0xC06 / 0xC16 / 0xC26 +
  outcome + 4 x tone block D/P/R/S), event_tribute_out 0xC56..0xC59, event_gift rescue 0xBF5, event_city_status_change
  (STATUS_HISTORY by subtype, change 0), expedition_attitude_effects 0xC72 attack / 0xC73 raid / 0xC74 an ally's
  strike, expedition_conquer_success 0xBE8 (rebels 0xBDC; a loyal colony 0x3E2, whose text is "N/A"), the ally
  strike's success 0xD94, games 0xD7D..0xD81. Not written by the exe (dropped from ours): "repelled your attack",
  "raided by you", "sent an army against you".
- Not seen (no state for it in the sandbox): mode 5 with rows, the history scrollbar.
Check: `python3 tools/world_dialog_check.py http://127.0.0.1:PORT OUTDIR` (a NEW sandbox game on your own port) vs
oracle runs 1F-wmdlg1 / 1F-wmdlg2 (re/oracle/scenarios/worldmap-dialogs1.txt / -2.txt): every shot 0 px at tol 30
(advice x4, request x5 incl. hover, gift x3, gift size x2, requests (empty), history (empty)); history2 (one row,
"You requested drachmas from this city"): 0 px (10-30, with the exe's history texts). Strike (oracle 1F-strike,
re/oracle/scenarios/worldmap-strike.txt + .poke: Tiryns' army 20 and attitude 100 poked; a NEW sandbox server of its
own): req_strike, strike_list, strike_hover, strike_hover2, strike_confirm, strike_confirm_hover, after_strike,
history3 ("You relied on this city for a military strike"): all 0 px at dpr 1.25.

## Requests (1L-5, 10-31)
- The request message (msgwin.js `request`): record 0xDF = type 2 (icon, amount, 23/98 name, "n Months to comply" while
  the record is in state 0; troops: none), the buttons 0x1C0 as posted and kept while request_can_fulfil; Dispatch now
  pays (`answer ID dispatch`) or opens the army dialog for troops (army_dialog_open), Postpone closes, Refuse
  (`answer ID refuse`).
- 'Requests by' rows: the request list's order; a click -> the army dialog (troops) or the 0x3F popups 5:6 / 5:8; OK
  pays and the dialog is drawn again. The army dialog for a request: title 283:3 / 283:4, no allies box, kind 7 like a
  quest; Dispatch -> 0xE / 0x4C / 0xC popups (milpanel.js popup3F), OK = `answer ID dispatch companies .. ships ..
  heroes ..`. The army dialog also draws over the city screen (opened from a message).
- The forces on their way: player army markers from war._scenario_positions.
- Troops request check (10-31): `ORQ_AID=hercules_labors ORQ_NAME=1L5-troops python3 tools/oracle_requests.py run|check`
  (records 2 and 5 left alone: 0 differences, bugs.md 364); `ORQ_AID=hercules_labors ORQ_NAME=1L5-troops ORQ_TREASURY=9500
  python3 tools/oracle_requests.py save OUT 1632` = ours at the troops button run (`... troops`: 1L5-troopsbtn, world map,
  Cyme, its requests, the row, the army dialog, Dispatch hovered / clicked). Army dialog and the 5:0xC popup 0 px.
  Not reached there: a dispatch with companies (Hercules ep 0 has rabble only).
- Troops abroad end to end (10-31): `python3 tools/oracle_troops.py run 2` (re/oracle/runs/1L5-troopsgo): "See a
  working city" (tutorial15.sav, VeryEasy, 3 horseman companies) with Hercules' call-for-troops record poked in as
  a call by Mantineia (ally) attacked by Nemea, due June, lead 1, active, countdown 2; the call pauses the game at
  tick ~31 (Jun), its Dispatch now -> the army dialog (800 x 600: horsemen rows at y 140 + 18 i; Ares' Sparti /
  Ares' Guard under Mythical Warriors; no hoplite phalanx) -> 3 rows -> Dispatch -> the confirm "Request / Dispatch
  forces?" (its tick at (433, 251)) -> the companies go (+0x82 = 3, the city). The day is poked to 15 to run the
  months fast. Exe vs ours (`tools/oracle_troops.py exe` / `ours`, tests/test_empire.py test_troops_abroad): record
  state 6 cd 2 flags 0x200 -> the June pass wins (state 7 cd 2, "Mantineia regards you more highly", dated Jun) ->
  cd 1 -> Aug pass state 10, active 0, "Victorious warriors return!" (dated Aug), companies home with 8 each, then
  flags 0x204: equal month by month, and the messages the same. The march (OTR_FAST=0 OTR_NAME=1L5-troopsmarch,
  real months): both send the soldiers from the houses down x = 57 and east along y 54..60 to the land exit
  (logical (129, 61)); since 11-01 the same tiles every 20 ticks (`python3 tools/oracle_troops.py march`, bugs.md 369). Mythical warriors: bugs.md 368 (fixed
  11-01: the army dialog 0 px).
- Check: `python3 tools/oracle_requests.py buttons` (run re/oracle/runs/1L5-reqbtn: Athens ep 0 up to Knossos' 100-drachma
  request, the message, Dispatch hovered, Postpone, the world map, Knossos, its requests, the row, the confirm, OK) and
  `python3 tools/oracle_requests.py save OUT.pkl` (ours at that moment, records synced to the exe's, player "N"); serve
  a copy (`python3 -m sim live COPY --port P --speed 0`) and read back with tools/campaign_check.mjs at --size 640x480
  (800 x 600 interface): rq_msg / rq_hover 10 px, wm_requests / row_hover / confirm / confirm_ok / after 10..20 px
  inside the dialog (the drachma icons), the popup 0 px (bugs.md 350..357).

## Checked
dpr 1.25, UI 80% sharp vs re/oracle/runs/worldmap/*.bmp: panel 98.0% equal pixels, map 97.6% (labels, tooltip,
animations differ), picture edges 100%. 10-30 (labels + marker origin, `?tex=png`): wm0.bmp map area 838 x 738:
256 px differ > 30 of 618,444: an army marker near Elis in the oracle (state), the ally banner's frame, and route
dots at two places of the sea route (dot interpolation rounding, world-map.md 12); every label 0 px. No city leakage (bugs.md 123). Not pixel-checked: the dialogs.
Map layer cut to the viewport (bugs.md 180): `node tools/world_map_check.mjs http://127.0.0.1:PORT/play.html` (own server on a
save copy) reads back each frame with and without the map layer at 4 window sizes x UI 100/175/200 % x zoom 1/2/4 x 4 scroll
corners and requires the panel and top bar unchanged, the whole picture inside the map area at fit, and a click on every visible
city's centre to select it.
Panel vs the exe (bugs.md 204): `node tools/world_panel_shots.mjs URL DIR` on a new sandbox game (the oracle's cities), then
`python3 tools/world_panel_compare.py DIR`: title, attitude, goods and tribute 97.2-100 % within 8/channel for all 8 shots
(player, 2 allies, 2 rivals, vassal, colony, distant); the rest is goods icons (compressed sprites) and the Back to City
button, which the oracle shots show in its hover picture (the mouse opened the map there).
