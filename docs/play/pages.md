# Play mode: control-panel pages (info boxes) and map overlays (2026-10-27)

Code: `viewer/play/overlays.js` (map overlays), `viewer/play/pages.js` (info box of each page); hooks: ui.js
`drawPage` calls `ZPages.draw`, scene.js asks `Overlays.hidden/walkerHidden/terrainHidden`, play.js calls
`Overlays.drawGround` (after the terrain) and `Overlays.scene` (columns, panels).
Data: `data/play/overlays.json` (`re/venv/bin/python tools/play_overlays.py`: exe tables + an emulator run of
the view objects), `data/play/pages.json` (`re/venv/bin/python tools/play_pages.py`: text groups, tax/wage
level tables). Per-draw-call RE notes of the 11 page functions: `docs/play/pages_re/*.json` (positions,
fonts, string ids, exe variables, our matching field, evidence). Sim side: `sim/export.py overlay_extra`
(per building `ov`: risk, unrest, tax days, culture points, fed, infected; presentation only).

Evidence: **exe** = read in the code / run in the emulator; **seen** = our render compared by eye with the
original's art (no oracle screenshot of an overlay was taken yet); **hyp** = guess.

## 1. How the original draws an overlay (exe)
Current overlay `0x00FA05F0`; view object `0x00641C10[id]` (constructors 0x0055E990..0x0055EBF0 set the vtables
0x005E43F0..0x005E47CC). Methods: `+0x08(b)` building drawn as is, else `0x0044B050` draws its **footprint**
flat in the ground pass; `+0x10(f)` walker drawn; `+0x18(flags)` terrain tile drawn (else footprint image):
walls 0x4000 and gardens 0x20 go flat (security keeps walls, appeal keeps gardens); `+0x0C(b, tile)` the
building gets an overlay on this tile, `+0x00(x, y, b, tile)` draws it at the anchor tile's draw point (left
tile (x, y+h-1), raised by elevation); `+0x20` true = drawn in the third pass over everything (supplies,
distribution, husbandry, industry, problems), else right after the building; `+0x14/+0x04` walker icon (cart
waiting); `+0x24..+0x30` minimap colours; `+0x1C` hover tooltip.
- Building type lists and walker type lists per overlay: overlays.json `modes[id].buildings/walkers`
  (emulated for every type; the exe's own answers). Always drawn: agoras, avenue, boulevard, pyramids
  (0x0055EE70); roads mode: only roadblocks, agoras and avenue/boulevard on road tiles; supplies, appeal,
  roads, problems: no walkers.
- Footprints: size 1 `SPR_FOOT_PRINT1[0]`, houses `SPR_FOOT_PRINT2[0]`; bigger: edge/corner pieces of
  `SPR_FOOT_PRINT1_NW` (`..2_NW` for houses) by position, `[1]` inside (tables 0x005F5D08/0x005F87BC, rule
  checked against all sizes 2..6).
- Column `0x0055EC00(n, x, y, style)`: `SPR_OV_PILLARS`, n <= 10, colour 12 (water), 0, or by n (>=9 red, >=7,
  >=5, else white) for risk/unrest; base at (x+9, y-8), top at (x+5, y-10n-h+15), n-1 middles at (x+17, y-5-10k).

| Overlay | Shows (exe) | Ours |
|---|---|---|
| 1 Supplies, 4 Distribution | houses: panel `SPR_OVERLAY_SLOT3`/`SLOT6` at (x+11, y-16), per needed good (now or next level) `SPR_SUPPLY_OK` or blinking `SPR_SUPPLY_LOW_ON/OFF` (stock <= table 0x00641C78/0x00641CCC) | same; food = sum of the house's food goods |
| 2 Husbandry, 3 Industry | their buildings + walkers; problem panel on those with problems | same |
| 5 water | houses: column water/10 (elite 10) | coverage.water |
| 6 hygiene | column healer/10, `SPR_HOUSE_ATE_FOOD` at (x+20, y) when the house ate | coverage.healer, ov.fed |
| 7 hazards | buildings with risk >= 100 or burning, maintenance; column max(fire, damage)/100, colour ramp | ov.risk (same 1000 scale) |
| 8 unrest | column unrest/10, ramp | ov.unrest (b.crime) |
| 9 taxes | column tax coverage/5 | ov.tax (tax_days, 50 when visited) |
| 10 all culture, 11-14 | column culture points/10 or the coverage/10 | ov.culture, coverage.* |
| 15 immortals | sanctuaries; column activity/2 on the altar part | done 10-30: column n = info.activity >> 1, style 0, at the altar piece's draw point (Monuments.piecePoint); oracle 1D-immortals: column 0 of 2571 px |
| 16 security | military buildings, soldiers/enemies/gods; elite houses (types 9..14) get the soldiers pad instead of a footprint (below) | done 10-30 (overlays.js securityPad); oracle 1D-security/2: figures 0 px |
| 17 appeal | ground tiles `SPR_DES_HOUSE`/`SPR_DES_NOHOUSE` [d<=-11: 0, d<70: d/10+2, else 9] (0x0044B830), walls `SPR_IN_FILL1`; aesthetic buildings stay | T.des (terrain.json); oracle 1D-appeal (sandbox granary): 99.9 % of rows 200-500 within 8 (the rest: the exe's message banners and tooltip) |
| 18 problems | buildings with a problem bit stay, panel (`SLOT4` houses, `SLOT3` producers/workshops, `SLOT1` others) with `SPR_PROBLEM_ICONS[bit]` | bits from our state, see below |
| 19 roads | everything flat but roads, roadblocks, agoras | same |

Overlay ground and tall terrain (bugs.md 139): terrain pictures taller than their tile (play.js TALL, e.g. 31-px
scrub/meadow variants) are drawn with the objects; on tiles the overlay ground covers (appeal tiles, footprints)
they are skipped (`Overlays.covers`), as the exe's overlay tile replaces the tile's own image.

Problem bits (`building_status_flags` 0x00564560): 0 house devolving, 1 empty, 2 unrest > 80, 3 plague,
4 fire risk > 800, 5 collapse risk > 800, 6 no workers / no labour access, 7 short of workers, 8 halted,
9 raw material < 100, 10 sanctuary idle, 11 (walker) cart waiting. Shown per class (lists 0x00641D8C..):
houses 0-5, producers 4-8, workshops 4-9, sanctuaries 10, others 4-5. Ours: 0 from info.code < 10, 3 from
`infected`, 6-8 from employees/info, 9 from the input good; 10 and 11 never (not simulated).

### Minimap colours and tooltips under an overlay (exe)
Data: overlays.json `modes[id].minimap`, `modes[id].tooltip`, top-level `minimap` (palette, appeal, figures) and
`tooltip` (trigger, box, `texts` for every `{group:index}` token). Generated by tools/play_overlays.py: the colour
and tooltip methods run in the emulator for every building type while the field is swept over its range, so the
bands are the exe's own answers (**exe**); g_building_model (risk columns) is filled from extracted/model so the
hazards test works. Oracle: re/oracle/scenarios/overlays-minimap.txt -> re/oracle/runs/overlays-minimap.

**Minimap** (minimap_draw 0x00454980). With an overlay on, a building's draw tile takes its image from `+0x24`
(0x0055F250, shared by all overlays) instead of the per-type group, with no burning tint:
avenue 118 / boulevard 126 / agoras 63, 64 -> `SPR_R_ROAD`; else `+0x28` -> red (`SPR_R_FIRST_BUILD`+10);
else `+0x30` -> green (+5); else `+0x2C` -> purple (+20); else black (+60, the walls' image). Piece size picks
image + n as on the normal minimap. Colours (first two pixels, sg3 555 expanded): red (198,0,0)/(173,0,0), green
(123,198,0)/(107,181,0), purple (99,0,198), black (0,0,0), road (222,206,189)/(206,198,181).
- 1, 4, 16, 19: drawn-as-is types purple. 2, 3: their types purple, red with a problem panel. 18: red with a
  problem bit of its class, everything else black.
- 5 water: common houses water < 40 red, else green; elite houses always green; fountain 74 purple.
- 6 hygiene: all houses healer < 40 red. 8 unrest: houses unrest >= 70 red, else green. 9 taxes: tax coverage
  < 20 red. 10-14: houses culture / coverage < 40 red, else green; the venues purple.
- 7 hazards: buildings whose type has a fire or collapse risk: max(fire, damage) < 100 black, 100..399 **red**,
  >= 400 **green** (sic, the exe's +0x28 is the "<= 3" test); 121 purple below 100.
- 15 immortals: sanctuaries 84..98 activity (b+0x32) 0..7 red, else green. Column (10-30, +0x00 0x00562E70, +0x0C
  0x00562E10): on a complete sanctuary (0x0053ECA0 >= 100) at its altar part's tile (sanctuary_altar_part
  0x004EA390, the first piece answering vt+0xAC; ours class 2), n = root +0x32 >> 1, style 0, at that part's draw
  point (left corner tile, raised). Oracle scenarios/immortals-appeal.txt: Ares (activity 20) column at the altar
  (99,96)'s point; ours (baseline Athena, activity 21, its altar point placed there, dpr 1.25): 0 of 2571 column px.
- 17 appeal: before buildings and figures, every tile with flag 8 (buildings) or desirability != 0 gets
  `SPR_R_LAVA`+8+5k, k = 0x0044BCF0 (the main view's SPR_DES index), from dark brown (57,24,0) to gold (239,189,57).
- Figures: dotted only if the overlay's walker test (+0x10, `modes[id].walkers`) passes (0x00454920).

**Tooltips** (`+0x1C(tile, buf)`, called by 0x004F6A10 from game_turn every frame, **no delay**): needs mouse
help on (0x00F2A7B4, default 2), no widget under the mouse, right button up, city screen, an overlay on and a
tile under the mouse (0x0044A270 maps the ground diamond; the panel area also maps to a tile, **seen**). The
building on that tile must carry the overlay there (`+0x0C`: any tile of a common house; elite houses only the
picture tile, not emulated). Texts are group 66; `@L` ends a line:
- 5 water: 0 -> 18, 1..16 -> 21, 17..79 -> 20, >= 80 -> 19; elite 17. 6 hygiene: healer 0 -> 22, 1..31 -> 23,
  32..63 -> 24, >= 64 -> 25, then `@L` + ate ? 26 : 27.
- 7 hazards: any building, root part; burning -> 34; v = max(fire, damage), k = <=100:0, <=200:1, <=400:2,
  <=600:3, <=800:4, else 5; fire > damage -> 28+k, else 35+k.
- 8 unrest: 0 -> 41, 1..20 -> 42, 21..40 -> 43, 41..60 -> 44, 61..79 -> 45, >= 80 -> 46.
- 9 taxes: paid this year N = (b+0x88 + 5000)/10000 > 0 -> "N" + 49; else tax coverage 0 -> 47, else 48.
- 10 culture: <= 0 -> 50, then 51..60 by tens (90+ -> 60). 11/12/13/14 competitor/philosopher/athlete/actor:
  0 -> 61/65/73/69, 1..19 -> +2 ("has access"), 20..79 -> +3 ("about to lose"), >= 80 -> +1 ("recently passed")
  (sic: the order differs from water).
- 15 immortals: column part of a complete sanctuary; activity 0 -> 80, 1..7 -> 79, >= 8 -> 77.
- 17 appeal: any tile, desirability < -10 -> 100, < 0 -> 101, <= 15 -> 102, <= 40 -> 103, <= 70 -> 104, else 105.
- 2, 3, 18 problems: 4 + `@L` + for each set bit of its class 5+bit + `@L`; no bit -> no tooltip; 2/3 also a
  waiting cart: 16. 1, 4 supplies: 1 + `@L` + the low needed goods (23:43 Food, 14 Fleece, 20 Olive oil,
  18 Armor, 21 Wine, 15 Horses, each + " "), or just 3 "Nothing". 16 security: elite-house soldiers / spare
  armour and horses, 66:81..99 (counts 0x00563180 decoded below). The tooltip 0x005638A0 (disassembled 10-30) gives
  ONE line, chosen by the elite house's quadrant under the mouse (its picture offset in the picture grid
  0x00D4CFC8: quadrant k shows [2, random bit, 3, 4][k']): offset 1 and spare armour: 66:83 'This house has ' N
  86/87; offset 4 and spare horses: 83 N 84/85 (Poseidon: chariots 92/93); offset 3 and warriors lacking armour: N
  81/82; offset 2 (tile_ground_image_test 0x00565760): H 88/89 [66:2 ' and' ' '] P 91/90 + 98 (H + P > 1) / 99
  (Poseidon: 94..97); else none. overlays.js securityTip; oracle runs/lo2-security-tip (scenarios/security-tip.txt):
  the 8 quadrant shots give the same strings as ours for the same counts (aN '4 warriors in this house lack armor.',
  aE 'This house has 3 spare horses.', bS '1 horseman and 3 hoplites live here.', bW 'This house has 2 spare suits
  of armor.', the other 4 none); the box itself not pixel-compared. 19 roads: none.
- **16 security, elite houses (10-30)**: FUN_0044B050 (a building's footprint in the ground pass) calls the overlay's
  +0x00 = FUN_00563240 instead, for every tile of house types 9..14 (+0x0C 0x00563150), and draws no footprint;
  FUN_00563240 draws on the quadrant whose picture is image 2 of its group (0x820..0x823, 0x86C, 0x86D = elite levels
  0A..4), at that quadrant's draw point (x, y) = its left tile, raised by elevation: Zeus_Terrain SPR_ELITE_OVERLAY
  (packed 0xACA = bank 5 group 201) image 0, the iso-4 pad, at (x+0x1E, y-0x4B) (drawn as iso: left - 90, top + 120 -
  125), then rows of n = min(count, 4) figures, h = n / 2, each next one 15 px left and 2 px down, i = x + 0x12 +
  29 * (piece & 0xF) (= x + 47, the quadrant's piece nibble 1): unarmed (image 2) from (i + 15h, y - 0x4E - 2h - 10);
  spare armour (1) from (i - 0x3C + 15h, y - 0x30 + 2(6 - h)); spare horses (5) from (i + 0x3C + 15h - 15, y - 0x30
  - 2h - 5) (the +-0x3C swapped in views 2 / 6); chariots (4) from (i - 5 + 15h, y - 0x20 - 2h), hoplites (3) from
  (i - 5 + 15h, y - 0x20 - 2h); with both, chariots from (i - 10 + 15h, y - 0x26 - 2h) and hoplites y - 0x1A - 2h.
  Counts FUN_00563180: s = ceil(pop * house_param(level, 5) / 100); chariots c = min(s, arms, horses) on type 0xE
  (Estate) only; hoplites = min(s - c, arms - c); spare armour = arms - c - hoplites; spare horses = horses - c;
  unarmed = s - c - hoplites. Ours (overlays.js soldierCounts / securityPad; arms / horses = the house's goods
  armor / horses, already exported; soldier_pct = data/houses.json): pads drawn in the ground batch back to front
  after the other footprints. Oracle (scenarios/security.txt): runs/1D-security (6 Estates, 4 chariots each) and
  1D-security2 (arms / horses poked: 6/1 -> 2 armour, 3 hoplites, 1 chariot; 0/3 -> 4 unarmed, 3 horses; 2/0 -> 2
  unarmed, 2 hoplites). Ours, a test Estate on a new sandbox at the shot's place (dpr 1.25, ?tex=png): figure pixels
  0 of 2948 / 3789 / 2183 / 3751 differ, pad 26 of 15500 (its lower-right rim under a 31-px terrain picture of the
  test map's neighbour tile). On the baseline the pads' rims and figures sticking out above them are covered by
  avenue planters / trees of neighbour tiles (object pass, as the exe's sorted pass). Views 2 / 6: by the code, not
  shot. Poseidon pictures (font group 8 + 0xD0000/1, 0x6809 + 2): not ported (Poseidon off).
- Box (tooltip_draw 0x004F6E40): w 220, text width 190 (9DKBU); more than 2 lines: w 300, width 270;
  h = 16*lines + 10; outline (x, y, w+20, h) rgb(0,33,33), fill inside rgb(16,107,148); text at (x+5, y+7);
  x = mouse_x + 20 if mouse_x < w+20 else mouse_x - w - 20; y = mouse_y + 50, or mouse_y - 72 if mouse_y >= 200.
  text.md's "box w 210/290, at mouse+(20,50)" does not match this function; this one is **seen**: mouse (120,460)
  -> box (140,388) 240x42 (2-line water text) or 240x26 (1 line); mouse (300,12) -> (60,62) 240x26.

**Oracle (seen, 800x600, "See a working city")**: minimap on the radar tab (664,165) 128x110, on the Overview
page (664,318). mm_water: black, road colours, green (120,192,0)/(104,176,0) for every house, 16 px purple
(96,0,192) (fountains), no red; mm_unrest: houses all green; mm_hazards: black, road, purple, red (192,0,0)/
(168,0,0) 66 px, no green (no risk >= 400 at that time); mm_problems / mm_roads: black + road only (no problems,
no roadblocks). These are the 565 screen values of the palette above. Tooltips seen: 66:20, 66:19 (water), 66:28
"No risk of fire or collapse" (hazards), 66:42 "Unrest very low"; no tooltip on a house without problems
(problems) or under roads. **Open**: appeal. In the kept run (mm_appeal, tip_appeal) the Aesthetics page is up
but the map, the minimap and the tooltip are the normal ones. In an earlier probe run (not kept) the
"Somewhat appealing" (66:103) tooltip appeared but the map still did not change. Cause not found. Clicking the
radar tab turns the overlay off.

**Play mode (10-29)**: overlays.js `minimapColour(b)` / `minimapAppeal(i, b)` (ui.js buildMinimap: every tile of
the footprint, as our normal minimap; the exe colours the draw tile by piece size) and `tooltipAt(x, y)` (ui.js
drawOverlayTip: tile = screenTile of the mouse, box and text per the rule above, every frame). Deviations: walls are
black in every overlay (terrain in the exe); figure dots since 10-29 (bugs.md 209: the overlay's walker test); taxes never print the
"N drachmas paid" line (paid per house not exported: the coverage bands are used); sanctuary activity is 0 (no gods),
so immortals shows red / 66:80; elite houses answer the tooltip on every tile (exe: the picture tile); security
(16) has no tooltip. Checks (copy of the baseline save, dpr 1.25, own port): the water tooltip text at mouse
(120,460) in a 1024x768 window at dpr 1 is 100 % equal (each channel within 8) to the oracle's tip_water box
(140,388) 240x42 (text, outline, fill, position); at dpr 1.25 the readback across all four box edges is
map | (0,33,33) | (16,107,148), zoom 100 and 200 %; the minimap under overlays 5, 6, 7, 8, 12, 17, 18, 19 shows only
the palette colours (green houses under water as the oracle's mm_water; red / green / purple under hazards) in
views 0 and 2, and its four borders read panel | map pixel with no gap.

## 2. Info boxes (exe page functions; details in docs/play/pages_re)
Frame (all pages, 0x00517480): plain frame 8 cells at (X+50, 300-H), u = (11-n)*20, H = u+32-(u&15); y below
is relative to n*20 (n = overlay buttons). Fonts by rank: 3 11C2 numbers, 8 9B labels, 13 9DKBU, 14 9DKYEL warn.

| Page | Function | Shows | Ours / approximations |
|---|---|---|---|
| 0 Population | 0x00518B20 | "Housing for N More people"; migration headline; arrivals count / "Immigration Limited By" cause | vacancies; arrivals from the report trend; cause = worst negative sentiment part (exe: g_sentiment_cause_ui) |
| 1 Husbandry | 0x005195B0 | food supports N people, surplus..far too little, population trend, stored food months | husbandry report |
| 2 Industry | 0x00518750 | wage level (arrows 0x0063DF48 step the 6 levels 0x00641F38), projected payroll, employed, workers needed / unemployed | arrows send `wage N`; payroll from report |
| 3 Distribution | 0x00517F50 | goods list (loads, name), click toggles stockpiling | `stockpile GOOD on/off`; no import/export headers (no trade state in the export) |
| 4 Hygiene/Safety | 0x00519A50 | health word + trend; unrest message (0x00519910 rule over houses); deviation (user 10-28): the health word is followed by the number in brackets, e.g. "Perfect (100)", and "> target" while they differ | report health/target; ov.unrest |
| 5 Administration | 0x00518420 | tax level (arrows 0x0063DF10, 7 levels 0x00641F50), estimate, % visited by clerk, uncollected, expenses/income | arrows send `tax N`; estimate = 12x the houses' monthly tax; uncollected = 12x what unregistered houses would pay (ours); expenses/income = last month (exe: year to date) |
| 6 Culture | 0x00519FA0 | Philosophy/Athletics/Drama rating by population share covered, Competitions yes/no | from house coverage; no Panhellenic games layout |
| 7 Mythology | 0x0051A5D0 | sanctuaries with status, gods/monsters attacking | sanctuary rows "working"/"N % complete"; "None" twice; row clicks not wired |
| 8 Military | 0x0051B060 | company icon grids (in city / abroad / standing down), soldiers / ships / towers buttons | all companies "standing down"; towers button sends `towers on/off`; others toast (armies idle) |
| 9 Aesthetics | 0x0051BEE0 | the placed commemoratives by kind (g_commemorative_placed[v] = buildings with that variant): kinds 1..8 (not 4) one 12-px row each (133:3 / 133:4 "name (n)", names 133:5..13 by wm_sub_4663B0), god statues per god (FUN_0051B9D0, 157:god), Scholar, Athlete; 9B centred in 140 from panelX+0x2B, from y 0x60; past 15 rows Scholar+Athlete merge into 133:15 (count = kinds placed) or else the statues into 133:14 "Gods" (total); after the Scholar row as the 8th the column moves to panelX+0xC1 | oracle aesthetics-a..d (re/oracle/scenarios/aesthetics-page.txt, pokes of 0x00665C7C): 0 px in the list box (136x230 at (646,72) in the shot; ours 16 px right: our panelX at 800 wide is W-186 = 614, the exe's 598) |
| 10 Overview | 0x005B6F00 | popularity, food level, employment, hygiene, unrest, finances, threats; Requests; minimap | thresholds per exe; no requests/threats |

## 3. Missing / inert
- Advisor magnifier: opens the page's advisor (docs/play/advisors.md).
- (done 10-29, bugs.md 208: the cart-waiting '?' and its tooltip 66:16, See problems only), immortals
  column, Space key toggling the overlay, mythology/aesthetics/military
  row clicks (centre the view), Overview request rows.
- Not compared with an oracle screenshot yet: positions follow the exe; colours/art are the original's.
