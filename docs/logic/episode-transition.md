# Episode transitions: what the exe sets, resets, keeps and rebuilds (audit 11-04)

User request 11-04 (after bug 472): "make sure on continuation everything that can change is checked". This is
the inventory of every piece of state the exe touches when an episode ends and the next one starts, and after
every load, against ours. Exe paths:

- `episode_start_load` 0x00420390, by the episode record's +0x58: kind 0 new city, 1 colony, 2 continue.
- `episode_end_save_parent` 0x0052D2B0 (the victory screen's Proceed), in a parent episode or a colony.
- `game_file_load` 0x0050E610 (every saved-game load; the colony and continue starts load parent.dat with it):
  the blocks, `FUN_00510ED0` (the load fix-ups: one gated fix-up per save version 0xCB..0x140, none of which runs
  on a current save, then the ungated part listed in F), `FUN_00494BE0` (storage ids), `FUN_00512590` (hippodrome
  root). The map load 0x00511C90 runs FUN_00510ED0 too.
- `FUN_0051D5F0` (new city and colony): treasury, year, the time-limit year, `FUN_004612E0`, trade ledgers.

Ours: `sim/episode.py` (new_city, colony, resume = continue, back_from_colony, carry), `sim/campaign/flow.py`
(proceed, end_save_parent, _begin), `Game.load` (sim/game.py) with `empire.loaded`, `sim/empire` (new_game,
episode_reset), `sim/military` (episode_reset).

Verdicts: **same** (ours does what the exe does), **derived** (the exe rebuilds a cache that ours computes when
read, so it always equals the rebuild), **fixed** (a mismatch fixed in this pass; commits in docs/play/bugs.md
474..479), **deviation** (documented elsewhere, reason given), **n/a** (UI, sound, editor, or Poseidon only),
**open** (not ported, reason given).

Summary (83 rows, by the row's main verdict): 38 same, 11 derived, 19 fixed, 10 n/a, 2 deviation (F18 the pause
kept in the save; A5's random amounts and D6's walk home are deviations inside rows counted as same / fixed), 2 open
(flotsam, the entry / exit markers: start-of-map features, not carry-over).

## A. Every start (kinds 0, 1, 2)

| # | exe | ours | verdict |
|---|---|---|---|
| A1 | adventure re-read, episode record, the live record copy 0x00902F6C (89 dwords) | flow.episode_rec, g.episode, g.campaign | same |
| A2 | music streams faded and closed (FUN_005C85C0 / FUN_005C86A0) | play mode audio | n/a |
| A3 | games year 0x00902C50 = scenario +0x328 | episode.switches `games_year` | same |
| A4 | god block (24 slots, monster +0x60, may-be-jealous +0xC4, max sanctuaries +0xDC) -> g_scenario_gods; scenario_gods_apply 0x00586F70 | scenario.from_episode; gods state (new games), gods.reapply -> roles.apply (continue) | same |
| A5 | 150 event records copied over g_events, each `event_resolve_at_start` 0x00467660, reindexed | scenario.from_episode (resolve_at_start) | same (oracle chains: type / month / flags 0 differences); the resolved random amounts come from ours' own scenario RNG (events.md "rng15"): deviation, documented |
| A6 | event scratch cleared (FUN_00467630, type 2) | no scratch record | n/a |
| A7 | message list emptied (FUN_00522230: 1000 records, count, selection) | new City (kinds 0, 1); resume: `g.city.messages = []` | **fixed** (continue kept the last episode's 200; oracle 1L-europa-colony dumps 300 / 310: the slot-1 record replaced at the slot-2 start) |
| A8 | `event_rebase_month` 0x00467930 (kinds 1, 2) | scenario.rebase | same |
| A9 | request_list_rebuild 0x00483040 | scenario.request_list_rebuild | same |
| A10 | player city: resources +0xA8 (20 bytes); kinds 0 / 2 also quota table +0x60 (23), buy / sell lists, wealth, military, attitude | empire.set_player_city | same |
| A11 | FUN_0050D6C0: the sticky marks of the goods list (0x00FE93EC) and food list (0x00FEB0D2..DA) cleared | new game (kinds 0, 1); resume: episode.marks_clear | **fixed** (continue kept them) |
| A12 | rebuild_goods_lists 0x005BAAF0 (the marks set again from what the city has) | episode.switches -> allowed.mark; foods by agora.city_foods when read | same |
| A13 | every city's army_months (+0x01) = 0: an invasion on the map is over | new game (kinds 0, 1); resume: military.episode_reset(armies) clears the invasion and enemy-company records | **fixed** (continue) |
| A14 | allowed table 0x00902D30 (+0x408) | switches `g.allowed` | same |
| A15 | goals_load_episode 0x0052DE20 (+ set-aside expansion) | campaign _begin, goals.records | same |
| A16 | tutorial switches 0x00FEAE06[11], world map button 0x00FE6A5A | switches `g.tutorial` | same |
| A17 | goals_status_update 0x0052B7D0 | flow.status / texts.rows when shown | derived |
| A18 | scenario_start_year 0x00902928 (kind 0: the episode's; 1, 2: the current year) | switches `scenario_year` | same |

## B. New city (kind 0)

| # | exe | ours | verdict |
|---|---|---|---|
| B1 | FUN_005B0990: city_record_reset, buildings, figures, formations cleared, the map's blocks read | `Game(map)` | same |
| B2 | scenario_start_funds; FUN_0051D5F0: treasury = funds x start_funds_pct[difficulty] (after the briefing) | episode.apply, set_difficulty | same |
| B3 | _DAT_00fe971c (the treasury at the year's start) = the treasury | `g.year_treasury` (new 11-04) | **fixed** (ours derived it from last year's snapshots or the rules' funds: wrong in an episode's first year; the Overview's finances line, FUN_005B6730) |
| B4 | the time-limit / survival year 0x0091EC00 | goals.year_reached from scenario_year | derived |
| B5 | FUN_004612E0: cities in use from the world objects, FUN_00461360(1): goods flags, traded loads +0x84 and trader fields reset | scenario.from_data, relations.goods_flags_rebuild, a fresh trade_state | same |
| B6 | trade_ledgers_clear | fresh trade_totals | same |
| B7 | the world-history count 0x007796D0 = 0 | new Empire (City.history empty) | same |
| B8 | goods prices = the map's (block 21 = save rank 8, goods_remap_all for old maps) | empire.map_prices: g.prices when the map's table differs from data/trade.json | **fixed**: ours used data/trade.json everywhere; 34 of the 44 Zeus .pak maps have that table, Hercules Labors' parent map (bronze 105, marble 72, armor 195), The Peloponnesian War's (wheat 40) and some colony maps (not used: prices are carried) do not (oracle 1L5-chain-hercules_labors dump 0: = the map's) |
| B9 | world map picture 0x0090311C (rank 114 / map block 26), months count 0x00903114 (scenario block +0x7EC; 0 in every Zeus map, FUN_0042B230 zeroes it in slot 0) | Empire.picture from the map, months 0 | same |
| B10 | flotsam: FUN_004E0DE0 deletes figures 0x23 and creates 20 at the sea entry (resource, timer table) when 0x00902D01 and sea entry / exit exist | not modeled | **open** (an ambient river feature not ported yet; TODO "Next, smaller") |
| B11 | ship grid, wall grid, route grid (FUN_00587E20 / 0x00587E50, route_grid_rebuild) | World grids, roads.rebuild | derived |
| B12 | world map scroll (FUN_00460920), build menus (FUN_00516D50, FUN_00403DF0), buildings_availability | play mode; allowed.unavailable | n/a / derived |
| B13 | cattle count FUN_00510B90 | counted when read | derived |

## C. Colony (kind 1)

| # | exe | ours | verdict |
|---|---|---|---|
| C1 | parent.dat loaded (game_file_load), then kept through the colony map's load: g_cities (all 22 records: kinds, relations, attitude, quotas, traded loads, fatigue, troops away, tribute), the world objects (markers), the routes 0x009034F8 (path arrays recomputed from the waypoints), the history table 0x007796D4 + count, goods prices, treasury, year, month, the record name | episode.carry: the Empire (cities with their markers and histories, routes), prices, treasury, date | **fixed** (prices were not carried) |
| C2 | what the colony map brings: world map picture, months count 0x00903114, a new city record (peak military strength 0x00FE6A78, gifts / tribute totals 0x00FEAEB0..), g_events = the episode's | episode.colony: picture and months from the colony map, peak strength, totals and events new | **fixed** (ours carried all five; oracle 1L-europa-colony dump 620: picture 6 -> 1, months 2 -> 0; now in tools/campaign_flow_check.py compare_start) |
| C3 | parent city kind 3, active, relationship 0; colony city kind 0, active; markers | episode.colony | same |
| C4 | the colony's resources only (20 bytes) | set_player_city(resources_only) | same |
| C5 | FUN_0051D5F0 -> FUN_00461360(1): traded loads and trader countdowns reset; goods flags rebuilt | a fresh trade_state, goods_flags_rebuild | same |
| C6 | treasury = scenario_start_funds = _DAT_00fe971c = the carried treasury | apply: treasury, start_funds, year_treasury | **fixed** (year_treasury) |
| C7 | expedition_forces_home(_, 1) | a new map has no companies | same |
| C8 | the day of the month: the map's (0) | tick 0, months0 | same |
| C9 | army_months zeroed, messages emptied, marks cleared (A7, A11, A13) | a new game | same |

## D. Continue (kind 2)

| # | exe | ours | verdict |
|---|---|---|---|
| D1 | parent.dat loaded whole: every building, figure, storage, house, god, hero, monster, timer as saved | Game.load(parent) | same |
| D2 | the god records' +0xEC bit 0x40 rule (a monument slot made placeable again only if it was) | Poseidon monument slots | n/a (Poseidon, stage 3) |
| D3 | g_events replaced (A5): every run-time record of the last episode is gone: a city's request, a gift or delivery on its way, tribute in / out, an ally strike, an expedition (and its loot), a world-map invasion, an offer | empire.episode_reset: `e.events = []` | **fixed** (ours kept them: at slot 6 of the user's campaign an expedition in state 7 was still live) |
| D4 | messages, marks, army_months (A7, A11, A13) | resume | **fixed** |
| D5 | treasury and date kept; scenario_start_funds = _DAT_00fe971c = the treasury; scenario_start_year = the year | resume: start_funds, year_treasury; switches | **fixed** (year_treasury) |
| D6 | expedition_forces_home(_, 1) after the records are gone: every formation with +0x9C != -1 and trireme with +0x132 != -1 goes home, its mark cleared; heroes away get action 0xF; nothing about allies or loot | episode.armies_home: march_home + navy_return per away mark, marks cleared; no ally troops returned, no loot | **fixed** (ours ran the whole expedition end through war.forces_home: ally troops given back); the walk in from the map exit instead of the exe's placing them at their buildings: **deviation** (no teleports, user rule 10-27) |
| D7 | heroes' halls (0x7D) freed (building_footprint_clear, building_free, route_grid_rebuild): no message | demolish without a reason | **fixed** (ours posted "Hero's Hall at (x,y) episode") |
| D8 | FUN_00511DE0 hero records (needed, text, sent, paid, announced); hero figures (0x45) state 2 | heroes.episode_reset | same (bugs.md 397) |
| D9 | monsters (0x44) not guardians with an event: hero announced again | episode.monsters_announce | same |
| D10 | FUN_004FFB50 (sprite-set loaded flags) | | n/a |
| D11 | FUN_0042C4E0: every figure of types 0x28, 0x29, 0x2A (enemy soldiers), 0x3F (transport), 0x40 (warship) in use deleted | military.episode_reset(figures) | **fixed** (ours kept them, with no invasion record after A13) |
| D12 | tutorial switches, buildings_availability, FUN_00403DF0 | switches | same |
| D13 | 0x00FEB16C = 0, autosave_if_due: autosave_replay.sav | flow: SAVE.replay.pkl by the caller | same |
| D14 | the hero / colony monument on entering after a colony (FUN_0041FE40: message 0x51A / 0x51B, commemorative kind 3) | flow.proceed | same (oracle 1L3-europa-return) |
| D15 | kept as saved (not touched by the start): god moods, curses, blessings, jealousy countdowns, sanctuaries; storage and house goods; walkers (carts, traders, immigrants, animals); companies at home; disasters' objects; last year's production 0x00FE9724; months since enemy / to the next invasion; the world cities' counters (troops away, fatigue, attitude streaks) | kept by Game.load | same |
| D16 | the yearly profit, production and housing counters of the goals | kept, measure.start keeps year_stats | same |

## E. End of an episode (Proceed)

| # | exe | ours | verdict |
|---|---|---|---|
| E1 | wm_sub_471E90: the end-of-episode events | scenario.episode_end | same (1L-5) |
| E2 | in a parent episode: 0x00FEB168 = 0, 0x00902C04 = 0, game_file_save(parent.dat) | flow.end_save_parent | same |
| E3 | in a colony: the colony's g_cities, world objects, goods prices, history table, treasury, year, month put into parent.dat's state after loading it; colony kind 1, active, tribute mode 1; parent kind 0; FUN_00461360; 0x00902C04 = 1, 0x00902C52 = the colony | episode.back_from_colony: the cities (their traded loads +0x84 and trader countdowns +0x0A = ours trade_state used / countdown), prices, treasury, date | **fixed**: ours replaced the parent's whole Empire with the colony's (routes, months count, peak strength, totals, events) and dropped the prices and traded loads; oracle 1L3-europa-return dump 920: picture 6, months 3 (the parent's 2 + a month), now in compare_start |
| E4 | game_file_save in a colony slot (> 9) appends parent.dat to the save; game_file_load of such a save writes it back | campaign["parent_dat"] (set at the colony start), written back by end_save_parent | **fixed** (ours used whatever SAVE.parent.pkl held: a colony save loaded after another playthrough's Proceed got the wrong parent) |
| E5 | the next episode's start (B, C, D) | flow.proceed | as above |

## F. Every load (FUN_00510ED0's ungated part, game_file_load)

| # | exe | ours | verdict |
|---|---|---|---|
| F1 | figure free list, highest ids, figure pictures, building pointers | Walkers / dict ids | n/a |
| F2 | the per-difficulty models reloaded (figure, building, house, tax / sentiment, monster behaviour, sanctuary model FUN_00510E80) | Catalog(difficulty) re-read from data/ | same |
| F3 | FUN_004E1230 clamps scenario +0x24 (0x0090294C) to 9 | no reader known (difficulty.md) | n/a |
| F4 | init_god_ids (god, monster, hero record ids) | | n/a |
| F5 | scenario_gods_apply (listed / unfriendly / may-be-jealous from the god block; its only writer) | gods state as saved (written only by roles.apply) | same |
| F6 | labor priorities > 5 -> 3 (FUN_00568690) | priorities 0..5 | same |
| F7 | FUN_00461360(0): every city's goods flags rebuilt | empire.loaded | same (bug 472) |
| F8 | cattle count, crime level 0x00FEB520, the food-ratio values FUN_00519590, buildings_count_by_type, cycle_totals_33, granary supply list, storage city totals, the enemy ship counts, the wharf count 0x00DB7B34, granary free space (FUN_00512300) | computed when read | derived |
| F9 | invasion points (16) and disaster points (8) outside the play area (map_in_play_area 0x00496010) -> -1 | world.scenario_points clears them | **fixed** (no shipped map has one; checked over every .pak map) |
| F10 | disasters_create_objects(0): the objects re-made from the points (an existing one of the same kind kept) | the objects kept in the save, built at the first dispatch | same (events.md: built at the first record) |
| F11 | FUN_004A7BF0 building footprints and figure tile chains; FUN_0051D760 the building grid cleaned; the terrain images | World.occ, the walker index | derived |
| F12 | FUN_004A1D30 (in FUN_0051D760): the map entry / exit markers: the first tile with terrain 0 in rings 1..9 around each point gets bit 2 and the sign picture | not modeled | **open** (a map-start feature, not carry-over: the sign is not drawn and its tile stays buildable; TODO "Next, smaller") |
| F13 | route owners cleaned (FUN_004D8A00), road networks, road access, route grid, wall / ship grids | roads.rebuild / per-walker routes | derived |
| F14 | pending carts per building recounted from the live carts (FUN_004E1250; monthly too) | economy._incoming_all from the walkers | derived |
| F15 | rebuild_goods_lists | Game.load: allowed.mark | **fixed** (not called on load: a good listed at the load and gone before the month change lost its mark) |
| F16 | request_list_rebuild, goals_status_update | g.request_list as saved (rebuilt at the same passes), the goal rows when shown | same / derived |
| F17 | the player's city: active (+0x170) = 1, flags +0x174 &= ~4 (visible) | empire.loaded | **fixed** |
| F18 | game unpaused | play mode keeps the pause and speed in the save | deviation (bugs.md 40, user-facing) |
| F19 | 0x00FEB168 (victory shown) = 0 unless "continue building" | the victory screen is not part of an exe save; ours keeps the campaign result | n/a |
| F20 | view orientation clamp, camera bounds, selected companies, sound set, edge elevations, the panel's menus | play mode | n/a |
| F21 | FUN_0056F270 (hippodrome), FUN_00512590 | | n/a (Poseidon) |
| F22 | FUN_00494BE0 storage ids rebuilt | storages are buildings | derived |

## Ours only

- `episode.carry` / `back_from_colony` keep `Game.months0` (the calendar moved while the city was not played).
- Military "defeats": the second sack is decided by the city's tribute mode, as city_conquers_player 0x00482200
  (tribute mode 2 = already conquered us), which the world cities carry into a colony and back; city_army_sent_home
  0x00481E80 sets mode 2 back to 0. Ours kept its own per-city mark that never cleared (**fixed**; an invasion with
  no world city, the test command or a god's army, keeps the mark).

## Checks

- tests/test_campaign.py `test_episode_continue_resets`, `test_episode_colony_carry` (and the existing
  test_episode_rebase_and_carry, test_campaign_flow).
- `python3 tools/campaign_flow_check.py return re/oracle/runs/1L3-europa-return` and `python3 tools/campaign_chain.py
  check ID` (every adventure): compare_start now also compares the world map picture, the months count, the treasury
  at the year's start and the goods prices (a price an event moved in both, its random amount from ours' own RNG,
  is printed, not counted). 0 differences in all 14 chains after the fixes (Hercules Labors' prices = its map's).
- The user's chain (copies): a save -> Proceed -> slot 6: no message from the
  last episode, no run-time event (the slot-5 expedition record gone), the companies home, no hall message, the
  goods marks rebuilt from what the city holds.
