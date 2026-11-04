# In-game screens: inventory (Zeus, play mode)

Every screen of Zeus.exe's screen dispatch (screen_draw 0x00514020 by the screen byte 0xF2A6DD) and the in-game
windows inside them, against play mode. Poseidon-only screens are out of scope. "0 px" = pixel compare with an
oracle shot (tools/screens_check.mjs at dpr 1.25 + tools/screens_compare.py, tol 30; docs/re/oracle.md), "seen" =
compared by eye, "exe" = ported from the code without a shot. Sweep of 10-29 (TODO.md plan item 2).

## Checks (how)
- Own server on a COPY of a save (`python3 -m sim live COPY.pkl --port 8781 --speed 0`, not a game in play), headless Chrome
  muted at dpr 1.25 with the interface at 80 % (one interface px = one device px): `node tools/screens_check.mjs
  http://127.0.0.1:8781/play.html OUT.ppm --size 640x480 --rect X,Y,W,H --open "JS" --each "JS"`; the read back is
  gl.readPixels after the frame (window frames included in every rect).
- `python3 tools/screens_compare.py OUT.ppm re/oracle/runs/RUN/SHOT.bmp X,Y [--diff PNG]`.
- Oracle scenarios: re/oracle/scenarios/*.txt (each names its shots).

## Screens
| Screen | Exe | Ours | Status | Evidence |
|---|---|---|---|---|
| 1 city | 0x0051CAB0 + panel 0x00517BF0 | play.js / ui.js | done earlier (ui.md, pages.md) | ui.md |
| 3 top-menu dropdown | 0x00431210 | options.js / filemenu.js | done: File (6 items), Options (7), Help (4); frame under the bar edge | options-menus, help menu, file-dialogs: 0 px |
| 5 message / help window | 0x004F2D80 | help.js, msgwin.js | help pages done (links, Back, scrollbar, wheel); event-message window (layout 2) done: date / To line, type lines, the three button sets, help / go-to / close, pop-up of new messages by category ("Event-message window" below) | help-pages 1-3 0 px (help.md); messages-window* 0 px (below) |
| 6 build submenu | 0x0058F650 | ui.js drawSubmenu | done earlier | ui.md |
| 7 advisors | 0x00589xxx (per advisor) | advisors.js | all 11 Zeus advisors (labor, military, trade, population, hygiene, husbandry, culture, mythology, finance, overview, aesthetics); help button -> the page tab help; trade 'More'; population society; overview culture 4th coverage | advisors.md (0 px per advisor; society 0 px; More: exe-read, not seen) |
| 9 info window | 0x005720E0 dispatch | info.js | every building type mapped to its exe panel (info.md "Panels"); sanctuary under construction; land window; walls; help button -> the type's record | info.md (Apollo, Ares building, land 0 px; others 0 px or seen) |
| 9 walker window | 0x005740A0, FUN_005ABB90 | info.js drawFigure | phrases (danger, actions, moods), type lines (carts, peddler, vendors, miners, animals, traders, gods, monsters, heroes, priests: 10-31), portraits, Tell me more | exe + seen; figure crops (FUN_00572FE0) done 10-30: crop = map 0 px, pusher 0 px vs oracle 1D-walker (info.md) |
| 0x0A display options | 0x0059AF60 | options.js | done (full screen = browser's; resolutions only close) | 0 px |
| 0x0B sound options | 0x0059B5E0 | options.js | done (music/effects/ambient drive audio.js; speech, 3D kept) | 0 px |
| 0x0C speed options | 0x0059B330 | options.js | done (game speed -> live tick rate as simulation_due; scroll speed -> key scrolling) | 0 px |
| 0x0D file dialogs | 0x0059BCD0 | filemenu.js | Load / Save / Delete done; New adventure -> the new-game screens (newgame.js, below); Replay / Exit: ours | 0 px (empty list) |
| 0x0F list popup | 0x005BF1E0 | advisors.js (trade More) | done | exe-read |
| 0x11 messages list | 0x00522340 / 0x00522620 | lists.js | done; rows are our message lines (oldest first, as exe); a row opens the message window | 0 px (one message, empty, 12 with scrollbar, hovered row / boxes / arrow; lists.md) |
| 0x14 world map | world.js | world map agent | help button -> 88 World View (help.js) | world-map docs |
| 0x1D messages options | 0x0059BBE0 | options.js | done; Full / Condensed / Off decide the pop-up of new messages by category (msgwin.js), also sent to the sim (`msglevel`) | 0 px |
| 0x23 balloon help | 0x004F6110 / 0x004F6BA0 | balloon.js | city, info window, messages list targets; at once / 150 ms; OFF also stops overlay tips | Options-title balloon 0 px (box) |
| 0x3B goals | 0x0052C070 | lists.js | done: open play (records from the map's .pak) and campaign goals with live status and the Set aside button (1L-4, docs/play/campaign.md) | 0 px (tutorial texts fed; its buttons excluded); campaign goals 1L4-goals 0 px |
| 0x33 defeat, 0x34 colony choice, 0x35 briefing, 0x42 victory, 0x43 adventure complete, 0x3F set-aside confirm | 0x00422270 + 0x00422AB0, 0x00421C70, 0x0052E520, 0x0052D590, 0x0052D7C0, 0x00529CC0 | campaign.js, newgame.js, world.js, lists.js | done (1L-4) | 0 px each (docs/play/campaign.md "Screens") |
| 0x45 difficulty | 0x0059B200 | options.js | done; the sim takes a new difficulty only at tick 0 | 0 px |
| 0x48/0x20 military command, 0x57, 0x27, 0x10, editor screens | | | out of this sweep (military module, editor) | |

## Event-message window (screen 5, layout 2): viewer/play/msgwin.js
The exe shows every city message in help_page_draw 0x004F2D80 with a layout-2 record of Zeus_MM.eng (220..228,
the record's +2 = message type: 220/222 type 1, 221 type 7, 223/225 type 2, 224 type 0, 226 type 5, 227 type 6,
228 type 8); the texts are the message's eventmsg phrases (queue entry 0x00FD3838 + 0x3C*i: +0x10 announcement,
+0x12 title), the date its month/year, the buttons its flags (+0x26).
- Geometry (first pass, no picture/caption): the city view of map_view_set_size 0x00449E50 (right = 60*cols-2,
  bottom = 15*(rows-1)+30: 800x600 -> 598 x 600, 1024x768 -> 838 x 765; other sizes, ours: as many 60-px columns
  as fit left of the panel, 15-px rows below 30): W = view width rounded down to 16, X = the remainder / 2, H = 400
  at first; the body is measured at 16*(cols-4)-16; when it fits H = (lines + 5 + extra)*16 + 80 (extra 3 for types
  1/2/5/6/7/8), inner width cols-2, and the button rects are spread over W (FUN_004F2790: gap = (W - 516)/3, first
  at gap/2); else a scrollbar (wheel 3 lines). Y = view bottom - H. The control panel is drawn over it (FUN_004F2880).
- Titled frame; title 22C centred in W+20 from X+8 at Y+14; inner plain frame (X+16, T = Y+48) C x R.
- Date line (type != 4), 11C2 at T+6: month 25:m at X+26, year (year_text_draw) 12 px after the month's pen, then
  "To" 63:5 at X+16+0x50 + the year's pen and the ruler's name after it (type 1 with a building: its name at X+0xF0).
- Type lines: 1/7/8 "Go to site of event" 12:1 at (X+100, T+0x2C) (no buttons only) and the go-to button
  SPR_EXCLAIM_BUTTON 264 (+1 hovered, +2 held) at (X+0x40, T+0x24) -> centres the view on the message's tile and
  returns to the city (wm_sub_522E30); 3: 12:3..7 (the sentiment's worst cause) at (X+0x40, T+0x2C); 5: good icon at
  (X+24, T+0x28) + 23:good at X+0x30; 6: icon at (X+0x40, T+0x28) + amount "Dr" at X+100; body (text_layout, 11C2,
  links 11C4) at T+0x38 (types 0, 2), T+0x56 (1, 3, 5, 6, 7, 8), T+6 (4). Type 2 (requests) after the body: good
  icon, amount + 23/98 goods name, "n Months" 8:4/5 + "to comply" 12:2 at X+16+0xDC (exe-read, not seen).
- No buttons (flags 0): help 533 at (X+16, Y+H-40) (hit Y+H-36, 18x27) -> help record 87; close 537 at
  (X+W-38, Y+H-36); a right click closes (back to the screen it came from: the city or the Messages list).
- Buttons (FUN_004F28C0), at view bottom - 35, RIMS box (x1-x0) x 25 (hovered: the highlight's second look), label
  centred from x0+6 at +6. Set A (flags & 7, font 11C): Accept 44:209 (4), Postpone 44:211 (2), Decline 44:210 (1).
  Set B (flags & 0x38, 9LTBK): Surrender 44:282 (0x10), "Bribe [bribe_amount] drachmas" 44:281 (8), "Fight to defend
  city" 44:283 (0x20). Set C (flags & 0x1C0, 9LTBK): Dispatch now 44:275 (0x40), Postpone 44:211 (0x80), Refuse
  44:212 (0x100). With buttons there is no help/close/go-to and a right click does nothing (0x004F4CF0).
- Pop-up (message_queue_poll 0x00521D30, filter FUN_00521970): a new message the sim marks `popup` opens on the city
  screen (nothing else open), one at a time, and counts as read; its category (Model/Zeus event message
  categories.txt, by the announcement phrase, unnamed phrases inherit the previous id's category; data/messages.json
  `categories` from tools/build_messages.py) set to Full (2) pops it, Condensed (1) / Off (0) do not; 19 always pops.
- Message strip on the control panel (FUN_005170A0 -> FUN_00430D80; widget 0x007815A0 reset by FUN_00430FB0 on
  every new message): the queue newest first (FUN_005221B0 inserts at index 0), the messages whose category is not
  Off (FUN_00521970) and whose announcement has a condensed phrase (FUN_00477D60: jump table 0x0047AB70, announcement
  -> PHRASE_CONDENSED_*; `re/venv/bin/python tools/build_messages_condensed.py` -> data/messages_condensed.json,
  1462 announcements; sim/messages.py `post` puts the filled text in the message meta `condensed`). One shown (the
  scroll-th), DKMESSAGE paragraph at (panelX+13, 517) wrapped in 155; more than one: SPR_SM_BUTTON_UP / _DOWN (table
  0x005ED1A8) at (panelX+162, 514 / 543) step it (0x00430D20); a click on (panelX+8, 512) 155x50 opens that message
  (0x00430ED0 -> FUN_00522BD0). msgwin.js `drawStrip`. Checks (tol 30): 186x70 at (598,500) vs working-city/end.bmp
  ("The city needs more workers.") 0 px; with 12 messages vs messages-list12/end.bmp (arrows) 0 px; 1024 wide at
  (838,500) vs worldmap/city.bmp (three lines) 0 px. The sim's own message lines (not eventmsg phrases) have no
  condensed text and never enter the strip. The text (FUN_00466AD0, 0x00916DF1 set): the condensed phrase with
  [reason_phrase] = the reason's CONDENSED phrase too (wm_sub_465EF0 -> FUN_00466AD0(+0x10); "" if it has none),
  e.g. "Knossos thinks less of you since you sent 10 skeins of fleece late." (the window: the full reason "because
  you took too long to respond to my anxious petition ..."); buffer 200 chars (FUN_00505690 stops there);
  paragraph_draw has no clip and no line limit (a text longer than 4 lines runs over the buttons in the exe too).
  Hero / monster / quest messages (sim/heroes/events.py post) enter the strip like the others. Bug 461.
- Pause: simulation_due 0x005168A0 gives no ticks while screen_pauses_sim 0x0063D8B8[screen] is set: every screen but
  the city 1, build submenu 6, 0x12, 0x1E, 0x20 / 0x48 (military command), 0x23 (balloon, unless over the city),
  0x27, 0x49, 0x56, 0x58, 0x59. So the message window (5), help, info windows (9), advisors (7), top menus (3), the
  dialogs, lists and the world map (0x14) stop the city. Ours: play.js `screenPauses()` holds the playhead, and the
  synced live server ticks only up to the playhead (checked: Messages window open 2 s, playhead and city tick held).
- Ours: the sim's own message lines (not from eventmsg) open as type 0 with their first sentence as the title and
  the line as the body; a "(x,y)" in the line makes it type 1 with the go-to button. Their category: none (19).

API (for other modules; 1B's gifts / invasions / requests):
```
MsgWin.open({
  title, body,                 // strings (body: help text markup allowed, links open help records)
  type: 0..8,                  // the record's message type (default 0)
  month: 0..11, year: -1340,   // or tick: N (converted with the city's date); default now
  to: "name", site: "text",    // "To" line name (default the ruler); type 1: building text at X+0xF0 instead
  goto: [x, y],                // types 1/7/8: tile the go-to button centres on
  reason: 3..7,                // type 3: 12:reason
  good: "wheat", goodName: "Wheat", amount: 4, months: 6,   // types 2/5/6
  buttons: {accept, postpone, decline} | {surrender, bribe, fight, bribeAmount} | {dispatch, postpone, refuse},
                               // callbacks; a key present (truthy) shows its slot; a click closes, then calls it
  onClose: fn })
MsgWin.fromMessage(stateMessage)   // a state.json message {tick, text, title?, body?, type?, at?}
MsgWin.close(); MsgWin.isOpen(); MsgWin.state()
```
Sim side: `sim/messages.py` `post(g, title_id, body_id, popup=True)` stores a `Msg` (a str with `.meta`: title, body,
phrase, category, popup); export.py adds the meta to each state.json message.

Checks (oracle at 800x600; ours tools/screens_check.mjs --size 640x480 at dpr 1.25, interface 80 %; tol 30):
re/oracle/scenarios/messages-window.txt (the working city's one message, "Employees needed", opened from the list)
and messages-window-buttons.txt (the same with a poke of the queue entry's flags or record: 4 runs).
| Shot | Ours | Differing px |
|---|---|---|
| messages-window/window.bmp (type 0, no buttons) | `MsgWin.open({title, body, month: 4, year: -1340, to: 'N'})`, rect (3,408) 592x192 | 0 |
| messages-window/list-after.bmp (back in the list, row read) | row clicked, window closed | 0 (592x384 at (5,92)) |
| messages-window-b7/window.bmp, hover.bmp (Accept/Postpone/Decline, Postpone hovered) | `buttons: {accept, postpone, decline}` | 0, 0 |
| messages-window-b38/hover.bmp (Surrender / Bribe 0 drachmas / Fight) | `buttons: {surrender, bribe, fight, bribeAmount: 0}` | 0 |
| messages-window-b1c0/hover.bmp (Dispatch now / Postpone / Refuse) | `buttons: {dispatch, postpone, refuse}` | 0 |
| messages-window-goto/window.bmp (record 220, type 1: go-to button + "Go to site of event") | `type: 1, goto: [x, y]`, rect (3,360) 592x240 | 0 |
Not compared: the hovered go-to button, types 2/3/5/6 (no shot), the scrollbar case.

## New game (File > New adventure): viewer/play/newgame.js
The exe's way into an open-play city (oracle re/oracle/scenarios/newgame-flow.txt, newgame-adventures.txt,
newgame-openplay.txt at 800x600): Play Zeus, leader name, the family menu, Adventures (a list of all adventures, the
open-play ones among them; the chosen one's picture and description), Begin Adventure, then the episode start screen
(title, episode, "Open Play, no episode goals", the briefing, "Difficulty Level" with up/down arrows, "To the city").
Since 11-01 the main menu (screen 0), the leader name (0x36), the family menu (0x30) and the tutorials (2) are read
from the exe (docs/play/campaign.md "Front end"); the adventure list window below is still laid out from the shots
(**ours**, measured; texts and sprites the exe's):
- Adventures window: titled frame (ox-72, oy+32) 22x24; 293:9 (22C) centred in 336 from X+8 at Y+16; 287:5 (9LTBK)
  at (X+24, Y+50); plain list (X+24, Y+60) 17x13, rows 16 px from Y+66 at X+38, 11CB, the chosen one 11C2; arrows
  332/336 at (X+298, Y+60/242), track plain (X+300, Y+92) 2x9; cancel 328 (X+18, Y+340); 287:6 "Begin Adventure"
  (11C) at (X+156, Y+346), proceed 268 at (X+296, Y+340). Rows: the maps of data/maps.json (GET /maps.json:
  sim/live.py maps_info), named by their adventure record (the .pak header +0x8B40, as goals_info) or a custom
  adventure's .txt (Adventure_Title / _Introduction / Parent_Episode_1_*).
- Description window (ox+284, oy+290) 416x232: the titled ring and a plain inset (X+11, Y+12) 396x212 drawn with the
  last column/row pulled back, dark inside; name 11C3 centred in 400 from X+10 at Y+35; description 11C2 lines (wrap
  384) at (X+20, Y+58); since 11-01 its ring at (ox+284, oy+291) 419x232 (b1). The picture window above it and the
  screens' backgrounds: docs/play/campaign.md "Backdrops", "Adventure picture".
- Episode start: titled frame (ox, oy) 40x29; title 22C centred in 640; episode title 11C (X+16, Y+42); marble bar
  39 tiles at (X+8, Y+54); 44:276 at (X+51, Y+64); goals box plain (X+16, Y+76) 38x3 with 44:280 centred in 608
  from X+9 at Y+90; briefing plain (X+16, Y+152) 38x16, text 11C2 at (X+24, T+6); SPR_SM_BUTTON_UP 576 / DOWN 578
  (+1 held) at (X+111 / X+127, Y+422); 44:219 + 153:(d+1) (11C) at (X+150, Y+427); 62:5 at (X+466, Y+427); proceed
  268 at (X+564, Y+420) -> POST /control {new, map, difficulty}. The difficulty starts at the map's default
  (data/maps.json; the exe keeps the player's last choice). Right click: back a step (ours).
- Checks (ours vs the shots, tol 30, dpr 1.25): Adventures window 352x384 at (8,92) with the exe's ten adventure names
  fed: 0 px; description window: its text 0 px, the frame ring and inset edges differ (about 10k px: measured, not
  the exe's drawer); episode start 640x464 at (80,60): 140 px, all in the up arrow (16x16; same image by eye).
- 1L-4 (10-31): the family menu, the lists from /adventures.json (the adventures, custom adventures, tutorials) and
  the briefing with goals: docs/play/campaign.md (Adventures window vs 1L-europa1 s32 with the real list: 0 px; the
  episode start 0 px after the arrow fix, bugs.md 345).

## Not checked / not ported (10-29)
- Balloons: alert slots done 10-30 with the slots (docs/play/alerts.md: 68:(178 + type) at once, oracle 1D-alerts-bal
  box 0 px). Houses' 68:131 is
  dead in the exe (screen 9 wants 0x00781844, the house window's widget 0x005EE5C8 sets 0x00781840): none.
  Done 10-30: world map; Distribution rows, Military page buttons and company tips; advisors (military rows, overview
  requests; trade and finance none as the exe): options.md "Balloon help". RE so far (FUN_004F6110 select,
  FUN_004F5F00 by hover id 0x00781834): ids 10..13 alert slots -> 68:(178 + alert type, FUN_004103A0); 0xE/0xF/0x10
  messages / goals / world map 11 / 9 / 17; 1100..1115 -> FUN_005183F0 + 168 (Distribution rows); 0x640..0x642 and
  0x6A4..0x6AB -> FUN_005B6EB0 + 193 (overview request rows); 0x708.. / 0x76C.. / 2000.. / 0x834.. / 0x898.. /
  0x8FC.. -> build submenu rows (FUN_004F5BB0: even half 196/197/199/200, odd half the item's 207+); screen 7 by
  advisor 0x00665E34: 6 trade hover 1 -> 68:108, 2 -> 42, 3 -> a tip window (kind 3), else 109; 3 hover 0x13 -> 151;
  0xC with 0x0078182C -> 130; 2 and 0xD -> the id table. Which widgets set the ids: not traced.
- Held arrows of the file dialogs: done 10-30 for an empty list (0 px vs runs/1D-filearrows, options.md); a scrolling
  list (more saves than rows) not shot. Done 10-30: dialog bar hover, held speed / difficulty arrows (0 px,
  options.md); FUN_00512D80's RIMS highlight is a layout-edit mode, never drawn in play.
- Overlays: the security tooltip's lines (0x005638A0, counts as FUN_00563180); done 10-30: the elite-house soldiers
  pads (pages.md "16 security", oracle 1D-security 0 px figures).
- Auto-defend in the sim (the menu toggle and its rule only); autosave is ours (POST save_as "autosave" in Jan/Jul).
- Big-things list (CLAUDE.md rendering rule): this sweep changed windows and menus only, no map drawing; palace,
  sanctuaries, walls, villas, stadium, agoras, avenues, docks, bridges and raised terrain: not checked (no map
  rendering touched).
- Track 1D (10-29): message window, new-game screens, Aesthetics page, Messages list: windows and panel only, no map
  drawing; the big-things list: not checked (no map rendering touched).
