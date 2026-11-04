# Advisor screens (play mode)

Code: `viewer/play/advisors.js` (hooks in ui.js); data: `data/play/advisors.json` from
`re/venv/bin/python tools/play_advisors.py`; server: `/advisor.json?a=N` (sim/live.py `advisor`).
Oracle: `re/oracle/scenarios/labor-advisor.txt` -> `re/oracle/runs/labor-advisor/{a..f}.bmp` (1024x768,
"See a working city" tutorial).

## Screen 7 (exe)
- Open: the control panel's magnifier (`SPR_MAG_GLASS`, table 0x0063DEE8, handler
  `advisor_screen_open_refresh` 0x00408C00) opens advisor `0x0063E488[page]`:
  Population 7, Husbandry 9, Industry 1 (labor), Distribution 6 (trade), Hygiene/Safety 8, Administration 12
  (finance), Culture 10, Mythology 11, Military 2, Aesthetics 15, Overview 13. No magnifier on Aesthetics
  outside a Poseidon game (FUN_00517580). Opening runs `city_totals_refresh` (labor_allocate + assign).
- While open (`screen_input` 0x00514C10, case 7): only the page buttons (0x0063DC40) and the
  lower panel buttons (0x0063DF80: alerts, messages, goals, world map) take clicks; a page button switches to
  that page's advisor (FUN_00516D50); the map takes nothing; a right click (0x00F2A6FC) returns to screen 1.
  The panel stays drawn (page info box, build buttons) but inert. **exe, seen** (e.bmp: Distribution -> trade).
- Frame: titled frame at `((W-640)/2 + dx, (H-480)/2 + dy)`, per advisor (FUN_005904F0 dispatch):

| advisor | draw | dx, dy | cols x rows | title |
|---|---|---|---|---|
| 1 labor | 0x005906C0 / 0x00590920 / 0x00590C30 | -58, -10 | 35 x 33 | 50:0 Workforce Allocation |
| 2 military | 0x00591C30 | -75, -28 | 37 x 35 | 51:0 |
| 6 trade | 0x005BAD80 | -80, 0 | 37 x 29 | 54:0 |
| 7 population | 0x00593740 | -55, 50 | 35 x 22 | 55:0 |
| 8 hygiene | 0x00594080 | -80, 50 | 36 x 25 | 56:0 |
| 9 husbandry | 0x00597720 | -30, 0 | 32 x 24 | 57:0 |
| 10 culture | 0x00594B70 | -40, 50 | 32 x 13 (18 when games are scheduled, 0x00902C50 != -1) | 58:0 |
| 11 mythology | 0x00596FB0 | -30, 0 | 33 x (list) | 59:0 |
| 12 finance | 0x005951F0 | -30, 0 | 33 x 27 | 60:0 |
| 13 overview | 0x005B7760 | -75, -28 | 37 x 35 | 61:0 |
| 15 aesthetics | 0x00596180 | -30, 0 | 33 x 27 | 133:0 |

- Help (SPR_PANEL_ICONS +0, 0x005169F0) and exit (+4, 0x004066D0) buttons: draw table 0x005EF758 at
  (x+11, y+(rows-2)*16-7); the exit's x is set to cols*16-36 every frame.

## Labor advisor (advisor 1)
| element | position (from the frame) | font | evidence |
|---|---|---|---|
| title 50:0 | (15, 12) | 22C | exe 0x005906C0 |
| headers Priority / Sector / Need / Have (50:18/19/10/11) | (70/172/376/426, 46) | 9LTBK | exe |
| rows inset | plain frame (25, 60) 28 x 11 | | exe 0x00590920 |
| arrows (down x 0, up x 17; row step 20) | (40, 68) + table 0x006434D0 | SPR_SM_BUTTON_DOWN / _UP, +1 pressed | exe |
| priority text 50:(24+p) | (78, 74 + 20c) | p 0: 9B, 1..3: 9DKBU, 4..5: 9DKYEL | exe, seen |
| category 50:(1+c) | (160, 70 + 20c) | 11C2 (Poseidon: row 5 = 50:9 Science) | exe, seen |
| need / have (number_text_draw, '@' sign slot = one space) | (372 / 422, 70 + 20c) | 11C2; have != need: 11C3 orange | exe, seen |
| Industry Status 50:22 / hint 50:23 | (15, 244) / (15, 270) | 22C / 9LTBK | exe |
| industry inset | plain frame (25, 282) 32 x 13 | | exe 0x00590C30 |
| industry rows: 2 columns x 10, 245 x 19, step 20 | (28, 284) + hit table 0x00643690 | | exe |
| row: goods icon (dy 5), name 50:(33+i) (dx 26, dy 8), status 50:30 / 50:31 (dx 115) | | name 9DKBU; status 9DKBU / shut down 9DKYEL | exe, seen |
| no industry: 50:32 centred in 512 at (28, 294) | | 9DKYEL | exe |

- Priority arrows (0x00590580): up = +1 up to 5, down = -1 down to 0, then labor_allocate 0x00487750 and
  labor_assign_buildings 0x00487BA0 run at once. Ours: `priority CATEGORY N` (the command re-runs
  `labor.allocate`). Oracle note: one scripted click (down 0.3 s, up 0.3 s) moved the priority two steps in
  c.bmp (5 -> 1 after two clicks); the asm has one step per call, so the emulator's click probably reached the
  handler twice (held-button repeat, FUN_00431C80 countdown). Not reproduced in ours: one step per click.
- Industry list: resources in the order of 0x00643470 (armor, sculpture, olive oil, wine, urchins, fish, ...),
  shown while the city has a producer of it (`0x0091EB58[res] > 0`, buildings_count_by_type 0x00491820;
  grapes/olives/oranges/black marble/orichalc need the god's resource too, FUN_005905D0), at most 20.
  Click toggles `g_industry_halted[res]` (FUN_00590660). Ours: `industry GOOD on|off`; `labor.halted` keeps
  the producers of a shut-down good out of the labor allocation (building_industry_halted 0x004873F0, for
  categories 0/1/7 as in labor_eligible), so they get no workers and stop.
- Icons: SPR_GOODS_ICONS + FUN_0040FD80(res); silver = SPR_REQUEST_CASH_ICON, Poseidon goods own groups.

Verified 2026-10-28 (dpr 1.25, interface 80 % = 1 device px per UI px): with the oracle's numbers put into the
page, the whole 560 x 528 window read back with gl.readPixels equals a.bmp's crop pixel for pixel (0 pixels
differ > 30). Clicks in Chrome: up arrow (Industry 0 -> 1), industry row (armor shut down, 9DKYEL), page
button with the advisor open (Distribution -> trade stub), right click closes, magnifier opens.

## Hygiene (8), culture (10), finance (12)
Layouts (positions from the frame, fonts, text refs, word rules) are in advisors.json `hygiene` / `culture` /
`finance` (tools/play_advisors.py, each entry with its exe evidence); numbers from `/advisor.json?a=N`
(sim/live.py `_adv_hygiene`, `_adv_culture`, `_adv_finance`). The exe draws from the 640x480 origin; the json
gives frame-relative points. "number + noun" rows chain at the pen (number_text_draw, then the noun at
DAT_00F13A70).
- Hygiene (FUN_00594080): 56:(24 + health/10) (font 9LTYEL under 30, else 9LTBK); healer line 56:(35 + pct/10),
  pct = people with a healer x 100 / population (0x00FE6A84); food line 56:46 when nobody ate, else
  46 + clamp(pct/10, 1, 10) (0x00FE6A80); outbreaks this month 0x00FEB528 and crimes this month by
  FUN_00594000 / FUN_00594040 (0: "No", <3, <6, <9, else); maintenance offices / watchposts counts (singular at 1).
  Ours: crimes this month = sim totals minus the totals stored with the last closed month (finance.month_end);
  vandalism counts villa destructions (crime.py).
- Culture (FUN_00594B70, non-Poseidon branch): podiums / gymnasiums / theatres / stadium counts, coverage words
  58:55..66 from FUN_00566A90's percent (people in reached houses / people in houses): philosophy, athletics,
  drama. The games block (next games, odds paragraph, 5 more rows) is not drawn: no Pan-Hellenic games.
  Poseidon games use FUN_00594810 (not built).
- Finance (0x005951F0): last year / so far this year; rows taxes, exports, gifts, mined silver, tribute received,
  hippodrome (only when allowed, 0x00902D88; ours: in a Poseidon game), totals with 1-px rules (FUN_00509700);
  expenses imports, wages, construction, bribes/tribute paid, gifts and aid; net flow, balance. Ours: the sim's
  monthly ledgers summed per calendar year (history keeps each closed month's ledger and month index since
  10-28; older saves show 0 for earlier months); gifts, tribute and aid are not simulated (0).
- Verified 2026-10-28 (dpr 1.25, interface 80 %): with the oracle's numbers (re/oracle/scenarios/advisors.txt,
  p4/p6/p5.bmp) the windows read back with gl.readPixels equal the exe crops pixel for pixel.

## Husbandry (9), mythology (11), population (7), aesthetics (15), trade (6), overview (13), military (2)
Layouts in advisors.json `husbandry` / `mythology` / `population` / `aesthetics` / `trade` / `overview` / `military`
(tools/play_advisors.py, exe evidence per entry), data from `/advisor.json?a=N` (sim/live.py `_adv_*`).
Verified 2026-10-28 (dpr 1.25, interface 80 %): fed the oracle's numbers, every window read back with gl.readPixels
equals its exe crop pixel for pixel (0 px differ > 30): p1 husbandry, p7 mythology, p0 population history (scale 3200), p9 aesthetics, p3 trade,
p10 overview, p8 military (with two mythical-warrior rows fed); a changed number gives 452 px.
Population history input: the bar heights of p0.bmp read back (column x = graph + 2i, black run height h ->
v = 16h; 124 months, the first two 0).
- Husbandry (FUN_00597720): the exe's table 0x00F9FA58 is an *estimate* (FUN_00518FF0: fisheries x average catch,
  farms by crop growth, goats/cattle counts, imports FUN_00518E40 = min(partner quota*100/12, the post's limit));
  people = (100 / 25) x loads x 100 (food_consumption_rate 0x004E5EF0 = 25). Ours: the measured average of the
  closed months (up to 12): the sim's history rows carry `food_src` (units the carts of each producer type took
  away, economy.dispatch) and `food_imp` (food units traders brought, trade.import_one) since 10-28; older saves
  use produced_hist per good. Rows: resources 1..8 (urchin quays .. tenders' lodges) with a working producer, corrals
  after hunting lodges, then 'Imported <food>', total; none: 57:44.
- Mythology (FUN_00596FB0): sanctuaries (first per god, at most 4) with FUN_004F0130's long texts: building ->
  needs <material> / needs artisans (from the monument's reason) or 'Sanctuary is N % complete'; complete without
  staff -> 'needs priests'; complete and staffed -> 59:25 'is willing to help.' (**ours**: gods, sacrifices and the
  god's mood FUN_004F00A0 are not simulated; a monuments agent owns the construction states). Other gods: every god
  without a sanctuary counts (FUN_00595F20; none named: god_is_friendly needs a scenario slot), which is why the
  frame is tall (height = the exe's formula). Unfriendly gods, heroes: none.
- Population (FUN_00593740): history (FUN_00593A80: last 20/40/100/200/400 months, bar width 20/10/4/2/1, scale
  FUN_00593EE0, labels FUN_00567750) or society (FUN_00593D20: people per house level, 13 bars of 30 px); the text
  button (rims FUN_00593A30, hit 0x005EE5A8 -> wm_sub_408d70) toggles. Bars: 0xF800 fill + black outline; at width
  1-2 the outline covers the fill (as the shot). The red: 0xF800 shows as (240, 0, 0) (the exe runs 15-bit: seen
  in the society bars and the minimap view rectangle; ours was 248 / 255 before 10-29). Society view **seen**
  (re/oracle/runs/population-society/society.bmp: the toggle 0x00665E30 poked to 1, tutorial levels 6: ~2280 and
  12: ~120 read from the bars): 0 px differ. The scale's maximum is over 20 levels (0x00FE90E4..), bars for 13.
  view (no oracle shot): ours (248, 0, 0).
- Aesthetics (FUN_00596180): Poseidon pyramids list (none in a sandbox) and commemorative monuments by variant
  (sim/systems/commemorative.py `variant`; exe order FUN_0051BD00/BDD0, names wm_sub_4663b0, god statues by
  FUN_0051B9D0), 8 a column; none: 133:2.
- Trade (FUN_005BAD80 + FUN_005BAEF0): at most 17 goods (rebuild_goods_lists 0x005BAAF0; ours: a partner trades it,
  a building makes it or the city holds it; the exe's list is also sticky), price, state: a post imports from a
  trading partner (54:1) / exports (54:2) with the cities (first at 0x154, second at 0x1C6, 'More' rims when 3+),
  else 'Available for import / export / both' (a trading partner sells / buys it with quota left: FUN_00460E30 /
  FUN_00460F10). Clicking a city name centres the map on its post and closes (0x005BA720). 'More' (0x005BA7D0, 3+
  cities): screen 0x0F's list object 0x0160A808 (FUN_005BF1E0) with the row's cities after the first: titled frame
  at (frame + 300, frame + 55), 13 x floor((n*21 + 24)/16) cells, names 21:id centred in x 5..201 at y 14 + 20k, font
  11C, hovered 11LTBLUE, not a trading partner 11LTYEL; a pick centres on that city's post and closes (0x005BA780).
  Built 10-29 (exe-read; not seen: no oracle city has 3 partners for one good); checked in Chrome with 3 injected
  cities (the list covers the rows' text: ui.js uiFlushText).
- Overview (FUN_005B7760): eleven status lines by the exe's rules (popularity_advisor_text, migration 0x005B5FA0,
  food production 0x005B6260 vs eaten = population x 25 / 100, food level 0x005B5E10, employment 0x005B6350,
  hygiene 0x005B65C0, unrest 0x00FEB544 from house unrest (0x00519880: >= 81 / 71..80), finances 0x005B6730 vs the
  treasury at the year start, culture 0x005B6830 (average of FUN_00566A90's 4 coverages: philosophy, athletics, drama and 0x0091EA70 =
  house +0x6C, the competitor / curator coverage: ours `competition`; identified 10-29), mythology 0xB5, security 0xB6 / 0xB7 when the empire has an invasion coming) and city
  requests (rows as 0x005B7760's second branch). **Ours**: the sentiment 'cause' = the most negative sentiment part
  (the exe keeps g_sentiment_worst_cause; its 'past' flags FUN_00518A10.. are not kept; with no negative part the
  migration line uses 0x3A 'unpopularity'); migration state
  0x00FE9198 has no writer found by an immediate scan: treated as 0.
- Military (FUN_00591C30): companies by type (palace slots, military.companies; banner = misc 'banner', else slot-1;
  ours never mobilize: 'At home' in the thin button FUN_005917A0, drawn 1 px lower than its rect: seen), navy per
  trireme wharf (no workers 51:81 / under construction 51:69 / hull 51:49.. + crew button 'Unmanned'),
  mercenaries / mythical warriors (none: 58:55), and the three report lines (count_noun_draw resets the pen and
  text_ref_draw adds to it: seen). A military agent is building armies: its data may grow (status per company,
  trireme hull and crew actions FUN_00591680).
- Overview requests: the list 0x00916E08 of `request_list_rebuild` 0x00483040 (open city requests and tribute
  claims sorted by months, then open quests; docs/logic/events.md "Request list"). Ours since 10-30:
  scenario.request_rows (sim/live.py), quest rows drawn by advisors.js: 0 px vs the exe (oracle lo-overview-quest,
  bug 255); request rows: bullet and fonts by FUN_004713E0 (row `can`), city name or short name within 0x50 px
  (FUN_0042E2D0), stock column (+0x148: treasury / loads in the city + 61:0xCC), no oracle shot. Culture line: the next
  games' rating (FUN_005B6830 -> FUN_00565D40, bug 260). Panel bar under the magnifier: FUN_00517210 (bug 259). The panel's Overview page
  draws the first 3 rows (pages.js, 0x005B6F00; bug 258).
- Help button (0x005169F0): the current panel page's tab help (76..85, 75), help.js (docs/play/help.md).
