# Play mode: the military (10-28)

What play mode draws of `sim/military` (docs/logic/military.md) and how the player gives orders.

## Data
- `data/play/military.json` from `tools/play_military.py` (`re/venv/bin/python tools/play_military.py`; reads
  Zeus.exe tables with pefile and `extracted/sprites/*/atlas.json`):
  - `roles`: invaders `enemy_{archer,infantry,cavalry}_{0..10}` from the exe's per-army sprite tables (missile
    0x006381AC, infantry 0x0063825C, cavalry 0x0063830C: walk, die, fight, wall attack) and by-good roles
    `enemy_*` (the walker's good is `army<N>`, set by sim/military/invaders.py); `tower_sentry`, `wall_sentry`.
  - `overrides` over walkers.json: rabble fight = 6945 (12 x 8, the stone throw; the knife group 7041 is never
    referenced), fight-frame rules (`fight_rule`: hoplite = attack_timer < 8, direction 0; enemy =
    (attack_timer - 10)/2 from 12; tick = +1 a tick), `die_rate` 1 (wolf, hoplite), wolf `work.stand` / `work.lie`.
  - `arrow` (SprAmbient group 79, 32 directions, shadow 78), `enemy_arrows` (army 0 group 51, army 1 group 71).
- Army atlases: `python3 tools/play_atlas.py Zeus_Greek Zeus_trojan Zeus_persian Zeus_centaur Zeus_amazon
  Poseidon_Egyptian Poseidon_Mayan Poseidon_Phoenician Poseidon_Oceanid Poseidon_Atlantean Zeus_AresWarriors`
  (viewer/play/atlas, git-ignored). military.js loads one when an invasion of that army is on the map.
- `/military.json` (sim/live.py -> `sim/military` export): companies (slot, type, members, mob, away, dest, home,
  mode, morale, status, banner), invasions (nation, target, bribe).

## Drawing (viewer/play/military.js, scene.js)
- Soldiers, invaders, wolves: the walker pass, with the frame rules above. Look records (sim/export walker_anim)
  `"work"` blocks: rabble `throw`, invader `siege` / `shoot`, wolf `stand` / `lie`, sentries `idle` / `shoot` /
  `post`; `"walk"` = a wall sentry walking the wall.
- Sentries: lifted by slope_offset (tower 98, wall 18, look extra [10][0]) and drawn after the building of their
  tile (exe +0x1D; ours: the building's foot depth + 0.05). Tower idle: frames 0 and 6 held 13 ticks; tower shot:
  timer/2; wall shot: min(4, timer/2) (table 0x005F61E8); wall post: anim/3, frames 0..3.
- Arrows (`"arrow"` look, extra [src x, y, aim x, y, height, army]): along the line at 4 fine units a tick, drawn
  at y - 10 - height; a tower arrow's height falls 3 a tick (ours: floor 0); 32-direction index from the screen
  angle (image 30 points up, 6 right, clockwise: seen in the sprites).
- Standards (fig_handler_standard 0x004B3E00, walker_draw 0x0044FEF0 type 0xE): pole SPR_STD_POLES 20 - morale/5,
  flag SPR_FLAG_COMPANIES banner*7 + anim/2, top icon SPR_FLAG_TOP_MISS/INF/CAV by class; with P = the tile's box
  top-left: pole P + (16, -33), flag P + (25, -69), icon P + (15, -84) (oracle, docs/play/monuments.md). At the
  company's spot when mobilized, else on its palace class-5 piece (slot k = the k-th); none abroad. Only a selected
  company's flag waves.

## Orders
- Control panel, military page (0x0051B060): with the module on, companies in three lists (FUN_0051AA40):
  forces in city (mobilized), abroad, standing down; icons 24 x 17 in rows of 5. A click selects a company
  (ours: the exe opens a company panel instead); the three lines then become Mobilize / Send home, Stance
  (hold -> attack -> special), Rotate. With none selected the first line is 'call all' / 'all called'
  (FUN_0051AD60) and sends `mobilize all` / `return all`.
- A left click on the map (not a drag) with a company selected sends `move SLOT X Y`.
- Advisor 2: the status column is sim/military's (FUN_00591610 over FUN_00525120): 18 at home, 19 still,
  20 marching, 21 going home, 23 fighting (buttons), 22 fleeing, 24 abroad (plain text); "enemies approaching"
  while an army is on the map.

## Test scenario (10-29, track 1B)
`scripts/military.txt` = scripts/full.txt (20 companies: 15 rabble, 5 horsemen; a tower and wall west, a gatehouse,
the trireme wharf) moved onto the test world data/world/wartest.json (`tools/make_world_wartest.py`: partners' 8
allies + the invented rivals Sparta (land, Greek) and Troy (sea, Trojan)), with: the wharf staffed and supplied (a
road joining the west shore to the city, a storehouse by the wharf with Get orders for wood and armor), a second
tower, then Sparta's land army and Troy's fleet announced (both arrive 2 months later) and Sardis asked for troops.
```
python3 -m sim run scripts/military.txt --save saves/military.pkl     # ~35 s (checkpoints make reruns fast)
cp saves/military.pkl saves/military-play.pkl
python3 -m sim live saves/military-play.pkl --port 8792               # http://127.0.0.1:8792/play.html
```
What to try (CLI equivalents in parentheses; docs/play.md "Armies"):
- The Sardis offer (message window: Accept / Decline; `offers`, `offer ID accept`): 32 soldiers appear at the map
  entry as companies 21..24 (loan flags), hold there, leave 4 months after the last enemy.
- Sparta's army at a land invasion point: mobilize companies (military page, or `mobilize all X Y`), Options > Auto
  Defend before it arrives, the bribe (`bribe`). Losing the palace = defeat -> tribute to Sparta (world map).
- Troy's fleet (warships + transports from the sea point (34,80)): the trireme anchored at the wharf fights them;
  transports land at (104,101) by the Corinth dock. `navy`, `trireme ID X Y`, `trireme ID crew`; the military
  advisor's navy row shows Anchored / Fighting / Repairing ... and its button sends the crew home.
- Expeditions from the world map: raid / conquer Sparta (land) or Troy (sea, triremes go too): the soldiers march
  to the map exit (216,105) and come back; `raid Sparta companies 16,17 ships none`.
- Being invaded with no defence: let Sparta's army reach the palace.

## The exe's military screens (decoded 10-29, track 1B; decompile + disassembly)
Conventions: panelX = W - 186 (838 at 1024); dialog origin (ox, oy) = ((W-640)/2, (H-480)/2) = (192, 144). "Iface N"
= Zeus_Interface atlas id N (packed group 0x2NN -> NN; font_group_entry(k) -> k+1). Font rank k = text.md rank k
(DAT_012afbec + 8k). Widget pictures: +0 normal, +1 hover (+0x1A), +2 pressed (+0x19), +3 disabled (state +0x18 = 0;
2 = hidden). 40-byte tables have rects (x, y, w, h); 28-byte tables (x1, y1, x2, y2).
Oracle shots of the company panel: re/oracle/runs/mil-a/b.bmp..i.bmp (1024x768, scenario military-mobilize.txt): the
six buttons, magnifier, panel edges and the flag match the sprites pixel for pixel. No shots of the army dialog or the
trireme panel.

### Company panel: screen 0x48 ("military command")
Opens: a company icon on the military page (0x00516A50: centres the view on the standard (0x0044A7D0), F+0x92 = 1,
0xDB7B38 = id, g_selected_companies[0] = id, count 0x782884 = 1, screen 0x48; earlier +0x92 flags are not cleared); a
soldier or standard clicked on the map from screen 1 or 0x48 (FUN_00409150 -> FUN_004DCC60: a figure 0xB..0xE on the
tile; abroad companies refused; no Shift: that company alone; Shift (0xF9C10C = VK_SHIFT) in 0x48: toggle (FUN_00524930
add, FUN_005248D0 remove; max 20)); the advisor's rows (below).
Drawn by panel_overlay_draw 0x00525280 (background, status box, texts; full redraw) and sidebar_draw_48 0x00525630
(buttons, info box; every frame).
| element | position (1024) | picture / text | font |
|---|---|---|---|
| background | (panelX, 0) | Iface 58 SPR_SIDE_MAIN_PANEL, then Iface 101 SPR_SIDE_MIL_PANEL (186x476) | |
| minimap | (panelX+25, 28) 142x109; FUN_00454980(x, 28, 71, 109) | radar | |
| map rotate | (panelX+45, 565) | FUN_00517A20 | |
| status box | (panelX+23, 147) | Iface 98 SPR_LAND_STATUS image 0 (144x47) | |
| hover line | centred in 140 at (panelX+23, 156) | 51:FUN_005251C0(hover id) | rank 13 9DKBU |
| status line | centred in 140 at (panelX+23, 179) | 51: 18 At home, 19 Still, 20 Marching, 21 Going Home, 22 Fleeing, 23 Fighting, 24 Abroad (FUN_00591610 over FUN_00525120, company 0xDB7B38) | rank 3 11C2 |
| button 0 centre | (panelX+23, 203) 69x47 | Iface 92 SPR_LAND_CENTER | |
| button 1 rotate | (panelX+23, 255) | Iface 89 SPR_LAND_ROTATE1 if F+0x77 == 0 else Iface 74 SPR_LAND_ROTATE2 | |
| button 2 muster/home | (panelX+23, 307) | Iface 85 SPR_LAND_MUSTER if mobilized <= home, else Iface 81 SPR_TAG_SEND_HOME | |
| button 3 defensive | (panelX+98, 203) | mode sprites below | |
| button 4 offensive | (panelX+98, 255) | | |
| button 5 special | (panelX+98, 307) | | |
| bottom buttons | table 0x0063DF80 at (panelX, 22) | alerts, messages, goals, world map: as the normal panel | |
| info frame | (panelX+14, 360) 10x7 cells = 160x112 | window_frame_draw 0x0059F2A0 | |
| magnifier | (panelX+157, 455) 18x18 | Iface 12 SPR_MAG_GLASS (table 0x0063DEE8 at (panelX, 0xCD)) | |
Mode sprites (FUN_00525530) when the selection has < 2 classes: rabble DEF_ROCK 70 / OFF_ROCK 69 / SPEC_ROCK 68;
hoplite 73 / 72 / 71; else (horse) 80 / 77 / 75; mixed DEF_GEN 35 / OFF_GEN 34 / SPEC_GEN 109. The button of
g_selected_companies[0]'s mode (F+0x91) is drawn pressed (+2). Button 0 enabled only when count < 2; 1..5 never
disabled; only the hovered button shows +1; a click sets +0x19 = 0x14 (brief pressed look; decay not traced).
Info box, one company (FUN_00524CA0; x0 = panelX+28, y0 = 360, width 142; font rank 5 11CB): name 138:display_index
centred at y0+10 (e.g. "The Wolves", quotes included); "@N " at (x0-6, y0+25) then 138:34 Rabble / 35 Hoplites / 36
Horsemen (138:70 Archers for slots 31/32; Poseidon 78/80) at x0 + pen - 12 ("@" = a one-space blank: "8 Rabble");
138:37 "Morale" at (x0, y0+40) then 138:(38 + morale/5) "Horrified".."Fearless"; the flag at (x0+47, y0+60) = (913,
420) top-left: the standard bearer's sprite_extra (+0x180: Zeus_General SPR_FLAG_COMPANIES + display_index*7 + anim/2;
SPR_FLAG_LOAN event troops; SPR_FLAG_GOD1 31/32; SPR_FLAG_GOD2 33/34; animated only while selected). Pixel-matched.
With auto-defend on: paragraph 138:68 instead.
Several companies: rows table 0x00640480 (hit origin (panelX, 30)): hit (18, 335+20i)-(160, 355+20i), i = 0..4; names
138:display_index of g_selected_companies[scroll+i] centred in 142 at (panelX+18, 373+20i); all rows when count <= 5,
3 when > 5 with "Prev" 138:66 at (panelX+26, 433) when scroll > 0 and "Next" 138:67 at (panelX+26, 453) when scroll !=
count-3 (scroll 0xFE231C); font 11C2 hovered else 11CB. Click 0x00524BB0: row -> select only it (0x00524AD0); Shift+row
-> remove (0x00524A30); Prev/Next page by 3 (quirk: with exactly 5, rows 3/4 act as Prev/Next; not seen).
Hover ids (FUN_00431C00 base 0x14, text FUN_005251C0, group 51): 0x14 centre 70 "Go to Company" (count 1); 0x15 rotate
71 / 76 (plural); 0x16 muster 72 / 77 / 78 "Send soldiers home" (home < mobilized); 0x17 73 defensive; 0x18 74
offensive; 0x19 75 special; 200 magnifier 85 "Show All Forces".
Buttons, handler 0x00405F70 (disassembly, jump table 0x0040626C, param = widget 0..5): not paused (0xF2A768), count >
0, auto-defend (0xF2A990) off; for each selected company passing FUN_00405EB0 (in the city +0x82 < 0, not a recalled
event company, ready +0x93); before the switch F+0x8C target = -1. 0 centre (count 1: on the standard's tile); 1 rotate
(2 -> 1 -> 0x10 -> 0x11 -> 2, wedges 0xC -> 0xD -> 0xE -> 0xF -> 0xC; toggle +0x77; wavs\cohort1.wav); 2 muster/home
(FUN_00405F00 counts): event companies -> formation_move to the first eligible company's dest; mobilized <= home: each
not mobilized: +0x90 = 1, formation_move(dest of the first, c, k, 0), on success the mode function (0x004E2100 /
0x004E2210 / 0x004E2320 by +0x91), on failure +0x90 = 0; else formation_return_home 0x004DD8D0 for the mobilized; 3/4/5:
+0x91 = 0/1/2 then the mode function. Any button: redraw 0xF2A6CE; sound 3 (FUN_005A3D00(3)).
Map input in 0x48 (screen_input 0x00514C10 case 'H'): minimap click scrolls; left press on a company selects it (on a
trireme -> 0x20); elsewhere a drag box (0xF2A6D9 = 'M', FUN_00433380; drawn by FUN_00433400). Release: a box past
FUN_00433A60's size threshold (not read) -> FUN_00433700 selects every company with a soldier or standard inside; else
a move order FUN_00406290 (not paused, no Shift; refused within 3 tiles of the play-area edge; each selected company
at home-able with +0x64 == 0 and not event-locked; an enemy on the tile -> +0x91 = 1, target = its company;
formation_move(x, y, c, k, 0); wavs\cohort5.wav).
Closing: a right click anywhere (tested before any widget): screen 1, selection cleared (100 ints), count 0, every
+0x92 cleared (so the buttons' right-click help 104/105/106 is unreachable here: read from the code order). Also on
screen change: magnifier -> advisor 2 (0x00408C00, 0x0063DF04 = 2), world map, messages, goals. fig_handler_standard
0x004B3E00 deselects any company while the screen is not 0x48 or 5. Space: nothing; P pauses; Ctrl+1..5 stores the
selection as group 0..4 (FUN_00433AB0), Alt+1..5 recalls it (FUN_00433B60, enters 0x48 or 0x20).

### Army dialog: screen 0x21 ("Enlist Forces")
Entry: Raid / Conquer on the world map -> expedition_event_create 0x0047FA60 (type 1, item 0x18, kind 9, flags 0x100
(+0x4000 raid), deadline travel+1) -> FUN_005BD950 -> build FUN_005BBB60 (object 0x01608BE8). Also a city's request
for troops (world-map widget 4's list 0x004642D0; the message's action button 0x00475AB0) and god quests (type 4).
| section | listed | toggle allowed when |
|---|---|---|
| horsemen (+0x30), hoplites (+0x80) | palace companies 1..20 in use with members, type 0xD / 0xC; never rabble; mobilized ones too | FUN_005BB900: companies allowed, F+0x64 == 0 (unknown; no writer found), +0x82 < 0, event type != 4 |
| triremes (+0xD0) | each wharf's (0x88, state 1, workers, a trireme) | the city's route is by sea (+0x140 == 2, FUN_0046ED20) and the ship's +0x132 < 0; else 283:17 "Destination not accessible by sea" |
| heroes (+0xE8) | up to 3 present | +0x132 < 0 |
| sanctuary companies (+0xF4) | slots 31..34 with members | as companies, plus +0x162 |
| allies (+0x104) | strike request code 3 (city_can_request(0x1B)) | one only (+0x2C) |
(1I, 10-30) A quest (type 4): milpanel.js `openArmy(city, "quest", route, [], [], quest)`; rules and the dispatch
checks in heroes-monsters.md "Quests".
Flags +0x164 companies, +0x163 allies, +0x160 triremes, +0x161 heroes, +0x162 sanctuary; type 4: no companies,
allies or triremes; kind 7: no companies or triremes; a type-1 neither raid nor player expedition: no allies. No total
strength is drawn; rows show member counts (triremes: hull state).
Geometry: fx, fy = ox-30, oy-30 = (162, 114); titled frame (fx, fy) 37x34 cells = 592x544 (0x005BD910). Left column x =
ox+4 = 196, w 272; right x = ox+290 = 482, w 240. Horsemen box top fy+84 = 198, height round16(18n+33) (n = horse
companies, 1 when 0 and < 20 hoplite companies); hoplite box height floor16(393-18n), top fy+502 - height. Right: navy
fy+84 h 144; heroes fy+258 h 80; mythical fy+340 h 96; allies fy+438 h 64 (when allowed). Plain frames (17 / 15 cells).
| text | position | font |
|---|---|---|
| 283:0 "Enlist Forces" | (196, fy+16) | 22C |
| 283:1 attack / 2 raid / 3 defend / 4 help-attack / 25 god quest (tokens FUN_00466B50) | (196, fy+51) | 11C |
| 283:5 "Citizen Army" / 6 "Navy" / 8 "Other Forces" | centred over the column, box top - 18 | 11C |
| 283:7 Horsemen Troops (Poseidon 26), 14 Hoplite Phalanxes (27), 9 Heroes, 10 Mythical Warriors, 24 Support from allies and subjects | (column x+9, box top+11) | 9DKBU |
| 283:11 "Troops" | left x+166; right x+136 (mythical) | 9DKBU |
| 283:12 "None" | (x+9, box top+29) | 9DKBU |
| 283:17 "Destination not accessible by sea" | (x+9, navy top+126) | 9DKBU |
Rows (28-byte table 0x0065BE90 from index 5, relative to (ox, oy), 17 px): companies (196, top+18+18i)-(465, ..): flag
Iface 27 SPR_MIL_ADVISOR_FLAGS + display_index at (+2, +1); type icon Iface 23 SPR_MIL_SM_ADVISOR_TYPES + (horse 0,
hoplite 1) at (+32, 0); name 138:id at (+60, +5); "@N" at (+173, +5); status at (+201, +5); Iface 11 SPR_ENLIST_GLOBE at
(+257, 0) when enlisted. Triremes (navy top + 18i, no header offset; as read): icon TYPES+3 at (+8, 0); hull 51:49..53
at (+34, +5); status (+163, +5) 51:33..40 (FUN_00591680) or 283:15 "Unavailable" when hull < 26 %; globe (+223, 0).
Heroes 185:hero at (+34, +5), status +163, globe +223. Mythical: icon (+4, 0), name +34, members +144, status +163,
globe +223. Allies (2 visible): name +34, "Enlisted" + globe; more than 2: arrows Iface 127 / 16 at (ox+532, fy+459) /
(ox+532, fy+480), hold-repeat (0x005BB840). Fonts: rank 8 9B normal; 13 9DKBU enlisted (283:13 "Enlisted"); 14 9DKYEL
abroad (283:16 "Abroad"). A hovered toggleable row gets window_highlight_draw 0x0059F6E0 (style arg not decoded).
Click (0x005BB880) toggles +0x165+idx; an ally row sets/clears the single ally.
Buttons (relative to (ox, oy); outline window_highlight_draw; label centred at (x1+6, y1+6), rank 10 9LTBK): 0 Cancel
(5,480)-(125,500) 283:18 (0x005BB7B0: a player expedition -> FUN_00475BE0, state 10; back); 1 Enlist All (153,480)-
(273,500) 283:19 (every eligible row + the first ally); 2 Clear All (290,480)-(410,500) 283:20; 3 Dispatch (409,480)-
(529,500) 283:21 (0x005BB7E0); 4 Plunder (raid only) (346,5)-(486,25): good 23:good or 283:23 "Any", caption 283:22
"Select Plunder" centred at (x1+6, y1-20) 11C; popup list (screen 0x0F FUN_005BEFE0) of city_can_be_asked goods ->
event+0x70. A right click cancels (FUN_005BD970).
Dispatch confirm (screen 0x3F, titled frame 30x10 at (ox+80, oy+80), title 5:id, body 5:id+1): expedition 0xAF ("Attack
city!" / "Do you wish to send the troops?"); help-attack request (kind 2) 0x4C; other requests 0xE; nothing selected
0xC ("Assign some companies first!"); type 4 / kind 7 hero checks (FUN_005BDAD0 / FUN_005BDC70; 0xA5/0xA9/0xB5/0xC1/
0xC3/0xC5). On OK FUN_005BE0E0: F+0x67 (company) / figure +0x02 (trireme, hero) for enlisted rows; an ally:
expedition_ally_join 0x00483790; then event_pay_tribute_or_gift -> expedition_send_forces 0x004DEB30 (formations 1..99
with +0x67, home (+0x82 < 0), members: sent mobilized or not; members at home teleported to a house; action 0xD); type 4
FUN_0046DA70; FUN_00483040; back to the previous screen. Figure +0x132 is the away-event of triremes and heroes.

### Military advisor rows and the trireme panel (screen 0x20)
Advisor rows (input FUN_00593470; tables 0x006438C0 / 0x00643D20 / 0x00644180 per type, 0x006445E0 navy + other
forces; 16 px rows): name area x 0..170 -> 0x005910D0 go to company (centre, select alone, screen 0x48, advisor closed);
status button x 188..262 -> 0x00591180: Marching/Still -> formation_return_home; At home/Fighting/Going Home -> +0x90 = 1
and formation_move to its dest; Fleeing/Abroad nothing. Other-forces rows -> 0x00591210: navy: a trireme -> screen 0x20;
none or enlisted -> scroll to the wharf; event 21..30 and sanctuary 31..34 -> 0x48. Navy status button 0x00591540 (not
read; navy.md: 0x591400 crew home / aboard).
Trireme panel 0x20: opens from the military-page ship icon (0x00516A50) or a click on a trireme (FUN_004092A0; Shift
toggles); 0xEF57F4 = the figure. sidebar_draw_20 0x00525C10 + panel_overlay_draw; table 0x00640390 at the same six
positions: left Iface 67 NAVAL_CENTER, 66 NAVAL_REPAIR, muster (64 NAVAL_SEND_HOME; 65 NAVAL_MUSTER when action
0x17/0x18; 85 LAND_MUSTER when the crew is home or auto-defend is on); right 63 NAVAL_DEFEND, 62 NAVAL_ATTACK_ALL, 61
NAVAL_PATROL. Status box Iface 95 SPR_NAVAL_STATUS + FUN_00525820 (0..3). Hover (rank 13 9DKBU): 184:48 go to ship, 49
repairs, 53/54 send crew home / call crew, 50 defend location, 51 attack all, 52 patrol; magnifier 58. Status text
(rank 3 11C2, FUN_005708D0): 6 -> 184:36; 0x14 -> 39; 0x15 -> 42; 0x16/0x1A/0x1B -> 43; 0x17 -> 40; 0x18 -> 41; 0x19 ->
44; 0x1C -> 45; 0x1D -> 46; 0x13 -> 47 (wharf under 50 % staffed), 37 (idle at its destination), else 38. Rules: the
current order's button pressed; crew home (0x18): only centre and muster enabled; auto-defend, or 0x13 with hull < 16 %:
only centre; wharf under 50 %: all disabled except repair and muster when it has workers. Exactly (10-30): state =
action, or +0x34 while sailing (0x19); auto-defend, or 0x13 with hull < 16 %: only centre, muster picture 0x255 (85
LAND_MUSTER); 0x18 (crew home): centre and muster, 0x255; else all enabled, centre only with one trireme selected,
pressed: 0x13 repair, 0x14 defend, 0x1A attack all (not 0x1B), 0x15 patrol (not 0x16); muster picture 0x240 (64
SEND_HOME), 0x241 (65 NAVAL_MUSTER) for 0x17. Then, unless the action is 0x18: a wharf under construction or with
workers * 100 / model value 5 < 50 -> all disabled, repair and muster enabled when it has workers. Info box
(FUN_005258D0(panelX+0x1C, 0x168)): one trireme: its name (figure_name_group: type 0x39 -> text group 269 "Revenge",
"Charybdis", ... 16 names; figure_name_from_group 0x004DD040: a saved counter per group, mod 16) centred in 0x8C at
y0+7 rank 5 11CB; 184:2 "hull condition:" at y0+20 11CB; 184:3..7 at y0+38 (rank 3 11C2; rank 4 11C3 barely afloat);
several: the names in the rows of 0x00640480 as the company panel (below the 0x48 table); auto-defend: 138:68 as a
paragraph at y0+10. Orders 0x00406400
(jump table 0x004065E4): centre; repair (0x004D0800); crew home / call (0x17 or 0x18 <-> 0x14); defend (0x14 +
0x004D1E00); attack all (0x004D1DD0); patrol toggle (0x15 via 0x004D8990). Map click FUN_004093E0: move (0x19) or attack
an enemy on the tile (0x1B). Right click on a button -> help 103 "Trireme" (checked before the exit test); elsewhere ->
screen 1; Space -> screen 1.
Selection box (screens 0x48 and 0x20; FUN_00433380 start on the button press, FUN_00433400 each frame, FUN_00433700 on
release): the corners are the screen points of the tiles under the mouse (FUN_0056BF20, y minus elevation x 30), so
the box steps by half tiles and stays on the map when the view scrolls (the start cell is kept); drawn as a 1 px white
(0xFFFF) rectangle only while valid (FUN_00433A60: top > 29, inside the city view, wider and taller than 2 px). On
release: 0x48 -> every company 1..34 with a soldier (types 0xB..0xE, not the standard) on a tile under the box,
except an event company that is recalled (+0x94 and +0x78 != -1 and +0x98); 0x20 -> every trireme (0x39) in it.
Groups: Ctrl+1..5 (FUN_00433AB0, in 0x48 / 0x20) store the selection list and the screen; Alt+1..5 (FUN_00433B60,
from any screen) recall it: a trireme group drops dead ships (state != 1); none left -> the previous selection, none
-> screen 1. Ours: viewer/play/milpanel.js (box, groups); our pixel spot of a tile is its diamond's centre (the exe's
FUN_0056BF20 point is (a - b) * 30, (a + b - 1) * 15 from the view origin: not compared, not certain which point).
Not certain: F+0x64; window_highlight_draw's style; FUN_00433A60's threshold; trireme rows at the box top; the count ==
5 paging quirk; a selected company freed while 0x48 is open; names of sanctuary/Poseidon companies in the type line.

## Checks (10-28, a copy of the baseline save, own port, muted tab, dpr 1.25)
- Standards on the palace match the oracle (runs/mil-a/i.bmp, runs/palace/c.bmp): fist, flag right of the pole,
  ball by morale. Pole pixels read back with gl.readPixels at the computed spot.
- Persian and Greek invaders, rabble fights, wolves standing / fighting a boar, tower sentries on the tower tops,
  wall sentries on the walls, enemy missiles (in the draw list: a 6 x 5 stone for army 0).
- Panel edge at panelX read back: map | 66,16,0 | 222,66,57 at every row: the panel's own frame, unchanged by
  this work.

## Open
- (10-29) The company panel (0x48), the trireme panel (0x20) and the army dialog (0x21) are drawn by
  viewer/play/milpanel.js from the layouts above ("The exe's military screens"); a company icon on the military page,
  a soldier/standard or a trireme clicked on the map opens them; a map click gives the move order.
  Checks (headless Chrome, muted, dpr 1.25, interface 80 %: tools/screens_check.mjs --size 820x615 = 1025x768
  interface px, gl.readPixels; tools/screens_compare.py tol 30):
  - army dialog vs re/oracle/runs/army-dialog/army.bmp (new scenario re/oracle/scenarios/army-dialog.txt: sandbox,
    world map, Sparta, Raid) at (162,114) 592x544: **0 px** (fixes: button labels centred in w from x1+6, "Select
    Plunder" in 142, horsemen box round16(51) = 48);
  - plunder popup vs plunder.bmp: **0 px** with the hovered plunder button masked (374,33,146,24): a titled frame 13 x
    (n+2) cells at (ox+135, oy), rows of 20 from y+14, the city's goods, Drachmas, Any, centred in 206 (11C);
  - company panel vs re/oracle/runs/mil-a/c.bmp (838,0) 186x476 with the minimap (20,24,152,118) and the waving flag
    (70,410,50,40) masked: 6 px, all at column 0 rows 4..15 (ours 16,148,189 vs exe 72,168,208): the same in our normal
    panel (not milpanel's; the top bar's join, 1D's panel edge);
  - trireme panel vs re/oracle/runs/trireme-panel/panel.bmp and panel_hover.bmp (scenario trireme-panel.txt: the
    working city's trireme "Revenge", crew home, screen 0x20 by pokes) at (838,0) 186x768, minimap and the date's
    last glyph (column 0, rows 0..23: the date differs) masked, ours the military test save's trireme with its crew
    sent home (`trireme ID crewpanel`), UIX.godMap off: **0 px** idle and **0 px** with the mouse on the disabled
    defend button (fixes 10-30: the name from group 269, not 184:1 "Trireme"; centred in 140; LAND_MUSTER and only
    centre + muster with the crew home; the button rules above).
- The army dialog's other rows (10-29): heroes present (/heroes.json, up to 3; `heroes H,H` on raid/conquer: +10
  strength each; expedition_send_forces 0x004DEB30: an enlisted hero gets +0x132 = the event and action 14, walks to
  the land exit and waits hidden there (16); expedition_forces_home 0x004DEE60: action 15, back to his hall; ours the
  same through sim/heroes hero_ai, 10-30), mythical warriors = companies
  31..34 (none exist in ours yet: "None"), allies with a strike code 3 (`with ALLY`; arrows past 2).
- Ships (navy.md "Pictures"): trireme hull, enemy warships (army 0 Zeus_Greek, others SprMain), transports; the
  trireme's crew overlay (PoseidonImps 133 standing/moving, 135 shooting, 134 sinking; none when the crew is home)
  and its selection flag (131 moving / 132 standing, while selected) are drawn by scene.js shipLayers (looked at:
  crew and flag on the anchored trireme). Oceanid transports (Poseidon) are not drawn.
- Drag box and Ctrl/Alt groups: ported 10-30 (above); checked by tools/milbox_check.mjs (headless, muted, dpr 1.25:
  real mouse drag over two mobilized companies selects both, the box edges read back 255,255,255, Ctrl+1 / Alt+1).
- The tower sentry's slow turn (every ~53 ticks) is not drawn (the sim's facing is used).
- Texture units: all 12 are in use once the city's atlases load; an army atlas packs into the last shared sheet
  (loadAtlases now keeps filling it across calls). Two large armies at once may not fit.
