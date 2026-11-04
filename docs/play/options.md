# Options and Help menus, option dialogs (play mode)

Code: `viewer/play/options.js` (menus, dialogs, settings), top-bar hooks in `viewer/play/ui.js`. Data:
`data/play/options.json` from `re/venv/bin/python tools/play_options.py` (Zeus.exe tables + text groups 1..3, 25,
42, 45, 46, 153, 174, 183 from `extracted/text/zeus_text.json`). Server: `GET /options.json` (difficulty index,
invaders alive). Settings live in the viewer's `localStorage` ("zeus-options"); the exe keeps them in Zeus.inf.

## Top bar and dropdowns (0x004310E0, 0x00431210)
- Titles File / Options / Help at x 10, then each at the pen after the previous title (+ one space) + 10; all drawn
  in 11C (the open one gets colour 0xFAC1, no visible effect).
- Dropdown: titled-frame middle tiles at (title x, 24), cols = widest string of the menu's whole text group / 16 + 2
  (0x005127C0), rows = (20n+20)/16; the bar's 6-px bottom edge stays drawn over the frame's top; items at
  (x+8, 36+20i), hovered 11LTYEL. A menu open: moving over another title switches menus.
- Options (0x005EFD20): Display 2:1, Sound 2:2, Speed 2:3, Difficulty 2:6, Autosave 2:9/10, Auto Defend 2:11/12,
  Messages 2:13. Help (0x005EFD90): Help 3:1, Balloon help 3:2/3/4, Warnings 3:5/6, About 3:7.

## Dialogs (positions from the 640x480 origin ox, oy; all close on a right click)
| Dialog | Exe | Ours |
|---|---|---|
| Display (0x0059AF60) | frame (96,80) 18x12, title 42:0; bars 14 cells at (128, 136+24i); Full screen/Windowed (by 0xF2A764), 800x600, 1024x768, Cancel | full screen toggles the browser's; the resolutions only close (the browser window sets the size) |
| Sound (0x0059B5E0) | frame (48,80) 24x20; rows music/speech/general/ambient toggle (46:1..8), 3D (46:13/14), volumes 0..100 step 5 (arrows at (320/344, 160+30k)), OK keeps, Cancel restores | music/effects/ambient drive audio.js gains (off = 0); speech and 3D are kept but have no sound in ours |
| Speed (0x0059B330) | frame (96,80) 18x14; game speed 10..100 and scroll speed 0..100, step 10; OK / Cancel (restores) | game speed sets the live tick rate as simulation_due: 1000/(speed_delay_ms[(100-s)/10]+2) ticks/s, 100 -> 60 (the exe: one per frame; hypothesis); scroll speed scales the key scrolling by the exe's step rate 1/((100-s)/10*12+2 ms) relative to 60 % (0 = none) |
| Difficulty (0x0059B200) | frame (48,80) 24x12; 153:(d+1) with arrows (up at (288,166), down (312,166)), clamp 0..4, "Right click to continue" | sends `difficulty NAME` on each click, silently (no toast), as the exe (0x00401EE0): at any time, the per-level tables swap and are read live; nothing else changes (treasury, built-up risk, curses, ship hp, requests made). Ours: at tick 0 with nothing built the start funds are re-scaled too (docs/logic/difficulty.md "Difficulty during play"; bug 376) |
| Messages (0x0059BBE0) | frame (0,0) 34x21, 17 categories (174:i) with Off/Condensed/Full (183) on RIMS boxes 92x25 | kept per viewer and sent to the sim (`msglevel CAT LEVEL`: offers answer by them, sim/empire/offers.py); they decide which new messages pop up (Full) in the message window (FUN_00521970; docs/play/screens.md "Event-message window"); every message still enters the list, as in the exe |
| Autosave (0x00402660) | flag 0xF2A7F4 = off; autosave_if_due saves in January and July | ours: POST /control save_as "autosave" when the date turns January or July (live, unless off) |
| Auto Defend (0x005692D0) | cannot be switched on while invaders exist | the toggle and the rule; the sim has no auto-defend (military module, TODO) |
| Balloon help (0x004025D0) | 2 ON -> 0 OFF -> 2 | balloon.js (below) |
| Warnings (0x00402620) | flag | the flag only |

## Pause switches (ours; the dev bar's Options ▾, play.js PAUSE, saved in the play prefs "polis-play")
The exe pauses the city under every screen but the city's own (screen_pauses_sim 0x0063D8B8). Ours lets these run:
| Switch | Default | On = the exe |
|---|---|---|
| Pause on info windows | off | right-click info windows pause (bugs.md 317) |
| Pause on message windows | off | event-message windows pause and are modal (bugs.md 317, 322) |
| Pause on the world map | off | the world map pauses (bugs.md 467; docs/play/world.md "Running city") |
| Close message windows after 10 s | on | (ours only: a non-pausing window closes itself; an offer that fits is accepted, a goods / money / food request the city can pay is dispatched ("Accepts in"), a troops request only closes; bugs.md 326, 474) |

Help, advisors, lists, file / option dialogs, new game and campaign screens always pause as the exe. A tab held by
a pausing screen tells the server (`hold=1` on its frames poll) so the stall watcher does not log it as slow.

## Checks (oracle runs/options-menus, re/oracle/scenarios/options-menus.txt; 800x600 vs ours at dpr 1.25)
| Shot | Rect | Differing px (tol 30) |
|---|---|---|
| display.bmp | (176,140) 288x192 | 0 |
| sound.bmp | (128,140) 384x320 | 0 |
| speed.bmp | (176,140) 288x224 | 0 |
| difficulty.bmp (Beginner) | (128,140) 384x192 | 0 |
| messages.bmp | (80,60) 544x336 | 0 |
| options.bmp (dropdown, title bar 0..200) | (0,0) 200x30 and (55,30)-(231,184) | 0 |
| helpmenu.bmp | (130,30)-(289,120) | 0 |
| display.bmp hovered item (ghost dropdown) | (56,32)-(230,52) | 0 |
Hover / held (10-30, re/oracle/scenarios/options-hover.txt): Display bar 1 hovered (style 1 of 0x0059FBA0) vs
dbar.bmp: 0 px but the label (the exe runs full screen: 42:2 'Windowed screen', ours 42:1 'Full screen', by the
state f2a764); the label's colour argument (0xFAC1 hovered / 0x02BF) leaves the 11C glyphs unchanged (seen). Held
arrows: speed (320,200) and difficulty (368,226) 0 px vs sheld.bmp / fheld.bmp (+1 image; the rest of the dialogs:
the values differ). The RIMS highlight in FUN_00512D80 needs 0xF9F970 == 3, which nothing sets (a layout-edit mode):
never drawn. The file dialogs' list arrows (10-30, re/oracle/scenarios/file-arrows.txt): with an empty list the exe
draws them plain whether hovered or held (uhov / uheld / dhov / dheld = none.bmp there); ours 0 px vs uheld / dheld
(mouse held on each). With more files than rows (the scrolling list, Help.scrollbar): not shot.
In the oracle, clicking a menu title right after start shows its balloon instead of opening; opening another menu
first and moving over the title works (scenario).

## Balloon help (FUN_004F6110 select, FUN_004F6BA0 draw; `viewer/play/balloon.js`)
Widgets register (rect, 68:index, at once?) while drawn; FUN_004F6110's rules: static texts need ON and 150 ms on
targets (the timer restarts on a frame without a target, not on mouse moves); "at once" texts show at SOME or ON;
OFF also turns off the overlay hover tips (0x004F6A10). Box: w 200 (text 180), more than 2 lines 300 (280);
(w+20) x (lines*16+10); x = mouse+20 if mouse x < ox+100+w else mouse-w-20; y = mouse+40 if mouse y < oy+200 else
mouse-62; outline (0,33,33), fill (16,107,148), 9DKBU at (x+5, y+7).
| Screen | Ported | Not ported |
|---|---|---|
| city (1) | menu titles 68:51..53, funds/population/date 61..63, rotate thirds 45/44/46, minimap 36, messages/goals/world map 11/9/17 (at once); Distribution rows 168 / 169 stockpiled (ids 1100 + row, FUN_005183F0; header rows none); Military page buttons 0x5DC..0x5DF (FUN_004F5DE0: soldiers 37 / 170 'all called' / 171, ships 38 / 173 (172 crews out), towers 39 / 174 manned / 175, helmet 177 / 176 auto-defend) at once; company icons: kind-4 tip FUN_0051C800 (150x20, 138:banner, x = mouse+20 below x 170 else mouse-170, y = mouse+10 below y 200 else mouse-32); alert slots 178 + type at once (10-30, docs/play/alerts.md) | Overview request rows 193/194; the exe's quirk of bug 242 (no at-once balloon on the Military page until a widget-less panel hover) |
| info window (9) | help 68:1, close 68:2 | houses 68:131 (which widget: unsure) |
| messages (0x11) | help 68:1, close 68:2 | |
| world map (0x14, group 44: FUN_004F6B60) | side-panel widgets (table 0x005EF488, hover ids 13..24) when enabled: attitude 333, request 308 (309 "demand": city_request_threshold(city, 0x19) == 1, ours for a rival, not seen), requests 310, gift 311, raid 312, conquer 313 (314 in rebellion), prev 331, next 332, history 335; back / help / orders none; a city under the mouse 334 (id 0x9C4). Static (ON, 150 ms). world.js | |
| advisors (7) | military (FUN_00593470, at once): per company row the name widget (0..170 x 16) 195/196/197 'go to company standard', the status widget (188..262) 201 + FUN_005918F0 (51:18 -> 0 'call to arms', marching/still 1 'send home', 21 -> 2, 22 -> 3, 23 -> 4, 24 -> 5); lists from (x+0x16, y+0x31), next list (count+3)*16 lower; navy (x+300, y+0x21) hull 200, crew 207 + FUN_00591950; mercenaries (y+0xB2) 199; mythical (y+0x183) 197 / 201+; overview request rows (x+0x23, y+0x152) 528x23: 193, 194 overdue (FUN_005B6EB0 state 1); box placement by advisor (balloon.js) | trade: the code gives 109 for the first city column (FUN_005BB5F0 id 0xA8C + row, static) but the oracle shows no box there (balloons-advisors t1/t0/t2: not traced, none in ours, as the exe); finance: 130 needs 0x0078182C, set only by the panel's arrows (FUN_00431E10), not in screen 7: none; labor and the rest: none |
| help window, dialogs, menus, goals | none (as exe) | |
Spec: an RE pass of FUN_004F6110 / FUN_004F5F00 (no balloon field in the widget tables: id = base + entry of
FUN_00431C00). Check: oracle options-menus2 o1.bmp (Options title, mouse (70,10)): box (90,50) 320x42, 0 px inside
the box.
World map check (oracle re/oracle/scenarios/balloons-worldmap.txt, 1024x768: Open Play Sandbox, the ally Tiryns
selected, the mouse on each widget and on a city): ours at dpr 1 / 100 % with the same mouse points, box rects
request 220x42, requests / gift / raid / conquer / prev / next / city 220x26, attitude 320x42: 0 px; history 320x42:
4 px (its top row at x 308..311); back, help, orders, the empty map: no box in both. Balloons needed options.json:
balloon.js now loads it (before, no balloon showed until a menu or dialog had loaded the texts).
Panel check (10-30, oracle re/oracle/scenarios/balloons-panel.txt and balloons-military.txt, 800x600; ours dpr 1.25,
80 %, same mouse points): Distribution row 68:168 box (480,154) 220x42 0 px (dist2.bmp); Military 'muster all'
(481,297) 220x42 0 px (b.bmp), helmet 68:177 (445,298) 320x58 0 px, company tip (481,111) 150x20 0 px (a.bmp).
Advisors (re/oracle/scenarios/balloons-advisors.txt): military advisor name row 68:197 at (151,24) 220x42 and status
68:201 at (300,24): 0 px (m1.bmp, m2.bmp; placement mouse+50, mouse-64).

## File menu and file dialogs (`viewer/play/filemenu.js`)
- Dropdown as Options/Help: 6 rows from table 0x005EFCC0: New adventure 1:1, Replay episode 1:2, Load 1:3, Save 1:4,
  Delete 1:6, Exit game 1:5. Ours: New = a new empty city, Replay = the same map again (both a confirm box of ours: the
  exe goes to its adventure screens), Exit = a note (the browser tab is closed by the player).
- Load / Save / Delete (screen 0x0D, 0x0059BCD0): titled frame (ox+128, oy+40) 24x21; plain insets (ox+144, oy+80)
  20x2 (name) and (ox+144, oy+120) 20x13 (list); title 43:1 / 43:0 / 43:6 (22C) centred in 304 at (ox+160, oy+50);
  43:2 "File does not exist" after a failed load (ours: 25 frames); "Proceed?" 43:5 at (ox+224, oy+342); 12 rows
  at (ox+160, oy+130+16i) (hovered 11C2, others 11CB; click = take the name); scrollbar (ox+464, oy+120) h 208, arrows
  and track always drawn; cancel SPR_BUTTONS6 328 at (ox+344, oy+335), proceed 324 at (ox+392, oy+335); the name
  (11C2) at (ox+160, oy+90), caret a 4x2 bar in 0xFFFF at (ox+160, oy+105) blinking 200 ms off / 400 ms on
  (FUN_0059FD60; the exe's I-beam variant when 0xF13A93 != 0: not seen). Keys: typing edits the name, Enter
  proceeds, PgUp/PgDn scroll by 12, Esc (ours) cancels; right click: not handled by the exe dialog (ours: none).
- Names: the server's named saves (saves/play/NAME.pkl), newest first (the exe lists *.sav of its save folder).
- Checks (oracle runs/file-dialogs, scenario file-dialogs.txt): load.bmp, save.bmp, delete.bmp at (208,100)
  384x336: 0 px each (empty list; caret forced on for load/delete, off for save, as in the shots); filemenu.bmp
  dropdown (11,24)-(185,144): 0 px.
