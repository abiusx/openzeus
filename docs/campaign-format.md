# Campaign data (track 1L-1): the adventure .pak reader and data/campaign/*.json

Written 2026-10-31 (track 1L-1). Everything here comes from the exe's loaders (GOG `Zeus.exe`, addresses below; names
in `re/names/campaign.tsv`) and is checked against the oracle where noted. 1L-2 (core switches) and 1L-3 (episode
flow) build on it; the list of what they need is at the end.

## Reproduce
```
python3 tools/build_campaign.py            # data/campaign/<id>.json for every .pak in zeus-original/app/Adventures
                                           # (sub-folders too) + data/campaign/index.json; ~3 s, pure Python
python3 tools/build_campaign.py --check    # rebuild in memory, compare with the files
python3 tools/build_campaign.py --show ID  # one adventure, readable: order, goals, gods, disallowed buildings
python3 tools/campaign_oracle_check.py ID SLOT DUMP   # an episode's start state vs an oracle dump (below)
python3 tools/campaign_flow_check.py MODE RUN         # 1L-3: our flow / goal judging vs an oracle run ("The campaign
                                                      # module": goal-met, time-limit, debt, return)
```
Inputs: the GOG 2.1.0.10 install (innoextract, see CLAUDE.md): `Adventures/**/*.pak`, `Adventures/tutorialNN.sav`
(hashed here; converted at run time by sim/savimport.py), `Zeus_MM.eng`; `extracted/text/zeus_text.json` from `tools/engtext.py`. Reuses `tools/mapfile.py`
(`pak_map_offsets`, `pak_map`), `tools/build_empire.py` (`build(path, container)`), `tools/build_scenario.py`
(`record`, `gods`). `id` = the file name without its sort prefix (`#`, `@`, `[` ...), lower case, `_` for blanks.

## What the shipped adventures contain
`kind` = adventure object byte +0x49530 (0 Zeus campaign list, 1/4 own folder, 2 tutorial, 3 Poseidon list); `game`
= .set version 5 (Zeus editor) or 26 (Poseidon). Episodes = parent-city episodes played + colonies with a map.
| Adventure | kind | game | episodes | colonies (choice) | start year, funds | events | goal types used |
|---|---|---|---|---|---|---|---|
| #Zeus and Europa | zeus_campaign | zeus v5 | 7+1 | Cydonia | -1150, 5000 | 88 | Housing, Population, Rule, Sanctuary, Set aside goods, Slay, Trading partners, Yearly production, Yearly profit |
| &Perseus and Medusa | zeus_campaign | zeus v5 | 4+2 | Calydon, Miletos | -3000, 10000 | 97 | Housing, Population, Quest, Rule, Sanctuary, Set aside goods, Slay, Support, Treasury, Yearly production, Yearly profit |
| @Athens through the Ages | zeus_campaign | zeus v5 | 6+2 | Laurion, Amphipolis | -800, 15000 | 194 | the same set |
| [The Voyages of Jason | zeus_campaign | zeus v5 | 4+2 | Corcyra, Corinth | -1409, 5000 | 98 | Housing, Population, Quest, Sanctuary, Set aside goods, Slay, Support, Trading partners, Treasury, Yearly production |
| ]Hercules Labors | zeus_campaign | zeus v5 | 4+3 | Ephesus, Lerna, Lemnos | -500, 9500 | 114 | Housing, Population, Quest, Rule, Sanctuary, Set aside goods, Slay, Support, Treasury, Yearly production |
| ^The Peloponnesian War | zeus_campaign | zeus v5 | 4+2 | Taras, Ithaca | -500, 7500 | 99 | Housing, Quest, Rule, Sanctuary, Set aside goods, Slay, Support |
| {The Trojan War | zeus_campaign | zeus v5 | 4+2 | Tenedos, Pergamum | -1239, 4000 | 139 | Housing, Population, Quest, Rule, Sanctuary, Set aside goods, Slay, Support, Treasury, Yearly production |
| }Open Play Economic / Military / Sandbox | zeus_campaign | zeus v5 | 3+2 / 2+1 / 1 | Smyrna, Naxos / Orchomenos / - | -1200 / -1000 / -1000 | 28 / 41 / 4 | Set aside goods / Set aside goods / none |
| Open Play Economic 2 / Military 2 / Sandbox 2 (folders) | folder | zeus v5 | 3+2 / 2+1 / 1 | Marathon, Taenarum / Salamis / - | -939 / -591 / -1750 | 31 / 72 / 12 | Set aside goods / Set aside goods / none |
| The Odyssey (folder, has voice mp3s) | folder | zeus v5 | 5+2 | Corcyra, Thrinacia | -1200, 8000 | 47 | Zeus: the bonus adventure of the free Zeus Enhancement Pack (Impressions, April 2001, before Poseidon in June 2001; neoseeker.com/zeus, Impressions fandom wiki); mp3s dated Feb 2001 |
| 16 tutorials | tutorial | zeus v5 | housing, food, agora, culture, hygiene, goods, oliveoil, firstcity, interface, trade: 1; palace, warrior, peacewar, bigcity: 2; sanctuary: 3; colony: 2+1 (Halicarnassos) | | | 0..9 | Housing, Set aside goods, Support, Rule, Sanctuary, Yearly profit |
| Poseidon: #The Birth of Atlantis, &Enlightenment in the West, @Life in the Mediterranean, [Atlantis Reborn, ]Proetus and Bellerophon, ^Two Worlds Collide (kind 3) + The Founding of Troy, The Mayan Revolution, The Sinking of Atlantis, The Youngest Twins (folders) | | poseidon v26 | 2..7 + 0..4 | (city names past text group 21: not resolved) | | | + Pyramid, Hippodrome |

The 7 Zeus campaigns are the kind-0 v5 files that are not "Open Play". Poseidon files (v26) are converted too but
not checked (stage 3). The adventure list text ("consists of eight episodes" for Zeus and Europa) = parent + colony
episodes, as our `order`.

## The format (data/campaign/<id>.json)
Top level:
- `id`, `name`, `source`, `sha256`, `set_version`, `kind` (+`kind_raw`), `game`.
- `header`: object +0x8 `episodes`, +0xC `b0c` (unknown, not read in play code found), +0x10 `colonies` (the editor's
  count of inactive colony cities, FUN_0042A1B0), `picture` (+0xCC29C: index into the table 0x005EBBD8 of adventure
  pictures).
- `brief`, `complete`: the adventure's texts (+0x8B40, +0x8B44): `{id, title, subtitle}` of the Zeus_MM.eng record
  (title FUN_0042B950, subtitle FUN_0042B560, body FUN_0042B980 = data/play/help.json `records[id][15]`).
- `order`: the play order (below), slots and the word "colony" where the colony choice comes.
- `colonies`: `[{n, slot, city, name, active, map}]`: the n-th in-use kind-1 city of the parent map's empire
  (colony_index_nth 0x00462280), its map slot 9+n and its map container (null: no map, cannot be chosen).
- `tutorial`: tutorials only: `{index, menu, start_save, start_save_sha256}` (see "Tutorials").
- `maps`: per map container present (map_offsets +0x49538, slots: index 0 parent, 1..4 colony n):
  `{index, slot, offset, version, sha256, origin, map_picture, cities: [{id, name, kind, relation, active, visible}]}`.
  The full empire of a container: `build_empire.build(path, mapfile.pak_map(path, index))`.
- `episodes`: one per slot used (parent slots up to the one with next = end, colony slots with a map):
  - `slot` (0..9 parent, 10..13 colony = 0x00F2A7B0), `role`, `number`.
  - `start`: record +0x58: `new_city` (0), `colony` (1), `continue` (2); `next`: record +0x54 (`parent`, `colony`, `end`;
    colonies always return to the parent).
  - `intro` (record +8: title, subtitle = the colony choice text, body = briefing), `victory` (record +0x14).
  - `start_year` (scenario +0), `funds` (+0x20): applied only by a `new_city` start.
  - `poseidon` (+0x288, 0x00902BB0; null in v5 files, see open questions), `games_year` (+0x328: Olympic games from
    start year + this, -1 none; FUN_00565950).
  - `allowed`: the 100 i16 at scenario +0x408 (-> 0x00902D30), named by what FUN_00402B80 gates with each index
    (0 and 5 are not read); `allowed_raw` all 100.
  - `player_city`: what the episode writes into the player's WorldCity: `resources` (+0x7A8 -> +0xA8: the raw goods
    the city can produce), `buys` (+0x7BC -> buy_list), `sells` (+0x7C2 -> sell_list), `table_60` (+0x7C8 -> +0x60,
    per good), `wealth` / `military` / `attitude` (object +0x8B70 / +0x8B48 / +0xCB264 [slot]). Colonies: resources
    only (the rest is the colony city's own record in the carried empire).
  - `gods`: the god block (+0x8B98 + slot*300 -> g_scenario_gods 0x00FFA450): `slots`/`names` (0..3 hostile, 12..17
    friendly ...), `independent_monster`, `jealous` (+0xC4, also "sanctuary may be built"), `max_sanctuaries`
    (+0xDC), `b64` (+0x64, 24 ints, copied, not decoded), `monument_count`/`monuments` (Poseidon), `raw`.
  - `goals_stored` (as in the file) and `goals` (as played: type-11 goals expanded, FUN_00526430), `goal_count`.
    Each goal `{type, name, v: [v1..v4], <decoded fields>, raw}`; see "Goals".
  - `events`: the episode's event records exactly like data/scenario/*.json (tools/build_scenario.py `record`; goods
    renumbered for v < 22 files).
  - `tutorial`: tutorials only: `build_categories` (11 bytes, object +0xCC2A0 + slot*11 -> 0x00FEAE06: build menu
    categories enabled) and `world_map_button` (+0xCC37C + slot -> 0x00FE6A5A). Other adventures: all 1.
  - `record`: the rest of the 356-byte episode record (`b00`, `map` = slot+1, `b10`, `b18`: 14 ints not read in play
    code found, `name`: overwritten at run time with the adventure's file name).

## How the exe plays an adventure
**Reading** (`adventure_load_current` 0x0042B3E0 -> `adventure_read` 0x00425D00 + `goals_read` 0x0052DF50): the
object 0x006AA750 field by field (`tools/build_campaign.py` `_fields`; set.md has the file offsets), then the goal
tables (4 globals). Fix-ups by .set version: v < 22 `adventure_remap_old_goods` 0x00425260 renumbers old goods in
each scenario block and in every event (this settles events.md's open point: the remap happens at read, once);
v < 23 god blocks are 224 bytes (+0xE0 = 0); v < 24 scenario +0x288 = value_O; v < 25 requests of kind 7 -> item 24;
v < 26 quest byte +0x7A = 0; goals v < 22: types 6 and 14 renumbered (`goal_remap_old_good` 0x00526500).

**Order** (`episode_next_slot` 0x00422FC0, `episode_won_advance` 0x00421920): start at slot 0. After a won parent
episode: next 3 = adventure won; next 1 = the colony choice screen (0x34): the world map with "Select a colony
location", the player clicks a colony city not yet active and confirms (`colony_choice_click` 0x00421AF0; oracle
shots); choice n plays slot 9+n; after a won colony the parent continues at the slot after the one that led to the
colony (0x00F2A7B2 + 1). Any other next = slot + 1. Each colony can be founded once (it becomes active).

**Episode start** (`episode_start_load` 0x00420390, by the record's +0x58):
- `new_city` (0): load the parent map (FUN_005B0990); start year, funds (then the difficulty factor), gods, events
  (each resolved, event_resolve_at_start), goals, allowed table, player city fields, tutorial switches.
- `colony` (1): load parent.dat (the parent city saved at the end of the last episode), keep its empire (cities,
  world objects, routes 0x009034F8, the table 0x007796D4), goods prices, treasury, year and month; load the colony
  map (slot's container); restore those. The parent city becomes kind 3, the colony city (colony_index_nth(n)) kind
  0 (player), active. Funds = the carried treasury. Then gods, events (each rebased, below), goals (colony table),
  allowed table, resources only.
- `continue` (2): load parent.dat (the whole city as it was), then gods (with the per-slot +0x40 flag rule), events
  (rebased), goals, player city fields, allowed table; treasury and date kept; armies sent home; heroes' halls (type
  0x7D) removed, hero records cleared (FUN_00511DE0: needed, text, sent, paid, announced) and hero figures removed
  (state 2), then monsters re-announced (bugs.md 397).
- Everything each start, the end of an episode and every load set, reset, keep and rebuild, row by row against
  ours: [logic/episode-transition.md](logic/episode-transition.md) (audit 11-04).
- Event rebase for colony/continue (`event_rebase_month` 0x00467930): every record not template/disabled gets
  month += current month; above 11: year + 1 and month - 11 (sic: an exe quirk, 12 -> 1 instead of 0).

**End of an episode** (`episode_end_save_parent` 0x0052D2B0): in a colony: save the colony's empire, date and
treasury, load parent.dat, put them back, the colony city becomes kind 1 (colony) with tribute_mode 1, the parent
city kind 0, then save as parent.dat; in the parent city: save as parent.dat. So: **the parent city is kept as it
was; date, treasury and the empire flow through the colony and back**. Oracle: after the colony tutorial's colony
the parent Megara came back with the colony's treasury (22538) and date (Feb 1347 BC), Halicarnassos kind 1, active,
tribute_mode 1.

**Goals** (`goals_month_check` 0x0052B610 at every month change -> `scenario_goals_check` 0x00526990 on 0x00FE2768;
count +4, up to 6 records of 76 bytes): won when all goals are met (types 0..11, 14..16 AND together); type 12 (time
limit) sets the result to "not reached yet" (order quirk: the editor puts it first), and when its year comes the
episode is lost (message 0xB95); type 13 (survival time) wins when its year comes; 36 months in debt loses (0xB91).
`0x00F2A6DB` forces a win (used by the oracle runs). Goal types (text group 194, test `goal_met` 0x00526FC0):
| type | name | met when |
|---|---|---|
| 0 | Population | population >= v1 |
| 1 | Treasury | treasury >= v1 |
| 2 | Sanctuary | v1 != -1 -> count 1; count (v3) > 1: sanctuaries (v4, kept by the yearly counters) >= v3; else god v2's sanctuary finished |
| 3 | Support | FUN_004DE170(unit type v1) >= v2 (Zeus files use 12, 13 = horseman ("Support 4 Horsemen" shot), 57) |
| 4 | Quest | event v1's state == 10 |
| 5 | Slay | event v1's state == 5 |
| 6 | Yearly production | v3 (counter) >= v2 of good v1 |
| 7 | Rule | city v1's relationship == 2 (vassal) (out of range: met) |
| 8 | Yearly profit | v2 (counter) >= v1 |
| 9 | Housing | v3 (counter) >= v2 people in house level v1 or better |
| 10 | Trading partners | FUN_00525EC0() >= v1 |
| 11 | (old dispatch goods) | expanded into type 14 goals at the episode start |
| 12 | Time limit | lost when start year + v1 is reached |
| 13 | Survival time | won when start year + v1 is reached |
| 14 | Set aside goods | good byte +4 == 0, or v3 >= v2 (amount) |
| 15 | Pyramid | Poseidon (monument slot) |
| 16 | Hippodrome | hippodrome exists and its length >= v1 |
The counters (types 6, 8, 9, 2, 14) are updated by FUN_00525FB0 / 005260F0 / 005262A0 / 00526330 / 00526370 before
each check (1L-3 ports them).

**Allowed buildings** (`buildings_availability` 0x00402B80, called at every episode start, by the 'A' cheat key and
others): for each build menu page/slot the building type (table 0x005F27D8) is allowed when its scenario flag is
non-zero and its inputs exist (raw goods from the player city resources or trade, e.g. the armory needs bronze in
the goods list, the olive press olive oil, the horse ranch wheat; sanctuaries by the god block; monuments by
commemoratives; heroes' halls by heroes; Poseidon items only in Poseidon mode). Result: DAT_00787178 (0/1 per slot)
-> the panel hides unavailable buttons (FUN_00516D50, bugs.md 323).

**Caps**: there is **no house-level cap** in the scenario data (house evolution, houses_evolve 0x004FE290 and
0x004843D0, reads no scenario field). The caps are: allowed flags (index 43 = elite housing), max sanctuaries
(god block +0xDC), the tutorial build categories / world map button, the Olympic games year (+0x328).

**Tutorials**: the menu (FUN_005BE2F0) lists housing, food, agora, culture, hygiene, goods, oliveoil, firstcity
("Beginning") and interface, trade, palace, warrior, sanctuary, colony, peacewar, bigcity ("Advanced") (names at
0x0065C508, stride 0x104). A tutorial **starts from `Adventures/tutorialNN.sav`** (NN = that index; tutorial_load_save
0x005BEBD0 -> game_file_load 0x0050E610), a saved game made at its start; the .pak gives the later episodes and the
colony. For housing the save equals the .pak's episode 0 (oracle, below); for colony it is a grown city (Dec 1348 BC,
22629 dr, 978 people) and its player city differs from the .pak's episode 0.

## Oracle checks (2026-10-31)
Scripts: re/oracle/scenarios/1L-europa1.txt, 1L-europa-colony.txt (+ .poke), 1L-colony.txt (+ .poke),
1L-tutlist.txt (run as docs/re/oracle.md "Run" with ZEUS_POKE=the .poke; dumps/shots in re/oracle/runs/1L-*):
- `tutorial` (existing, "Housing and People"), tick 0 vs `housing` slot 0: **0 differences** (year, funds, allowed,
  record, events, gods, player city, build categories, world map button).
- `1L-europa1` (Zeus and Europa, Mortal): tick 0 vs slot 0: **0 differences**; briefing shot "Founding of Thebes /
  Population of 1000"; in the city 5000 dr, Jan 1150 BC.
- `1L-europa-colony`: wins poked (0x00F2A6DB = 1 and day 15 at ticks 20, 300, 600), Proceed (296,555), To the city
  (656,491), colony choice Cydonia (297,541) + confirm (777,380): slot 1 at tick 60, slot 2 at 310, colony slot 10 at
  620: **0 differences** each (events rebased by the current month); colony briefing goals "30 planks of wood /
  30 amphorae of wine for parent city" = ours.
- `1L-colony` (Colonies tutorial): colony slot 10 at tick 30 and the return to the parent (slot 1, kind continue) at
  tick 650: **0 differences**; empire kinds checked (Megara 0 -> 3 -> 0, Halicarnassos 1 -> 0 -> 1 with tribute
  mode 1); parent.dat written in the run's write dir.
The goal tables (0x00FE2768) are not in the dumps: goals were compared on the briefing shots.

## Open questions
- `poseidon` (+0x288) in v5 files: not in the file; the exe copies a stale object field (0 after the tutorial run, 1
  in the Europa run). Harmless in Zeus mode (poseidon_game also needs 0x006AA4E0). Ours: null.
- Record +0x18..+0x4F (four triples like 50, 50, 65535) and object +0xC: no reader found in play code.
- Goal type 3 unit ids: settled 10-31 (1L-2) through FUN_004DE170 and the company count at 0x004DE2xx: 11 every
  soldier (rabble + hoplites + horsemen), 12 hoplites + horsemen, 13 horsemen, 57 triremes (figures 0x39,
  figures_type39_count 0x004DF3C0). Type 15 fields and the god block +0x64 ints: not decoded.
- Goal type 14 (Set aside goods): settled 10-31 (1L-3): the counter's writer is the "Set aside" confirm 0x0052ECF0
  (a player action on the objectives screen, below).
- Open play and the episode's player city: settled 10-31, see "Open play" below.
- Episode starts (all three kinds) zero every world city's army_months byte (+0x01: an enemy army of that city is on
  the map, empire.md). Ours has no such byte: an invasion in progress is an open record in sim/military; a new city
  and a colony start on a fresh map (none), a continue start keeps the saved one (the exe would stop judging it:
  not ported). Expeditions home and monsters re-announced at continue starts: done 10-31 (1L-3, below).
- Type-11 goals would keep old goods numbers in v5 files (FUN_00526500 renumbers only 6 and 14); no shipped file
  has a type-11 goal (nor 12, 13), so this is moot.
- City names of the Poseidon maps (name id 255) are not resolved (stage 3).
- 1L-3 left, done 1L-5 (10-31): handlers 13/14 (demand) and 21/22 (supply) (sim/empire/quota_events.py), type 19
  complete (messages, the oracle's prediction, subtypes 8/13/22/24, follow-up records, chain; status_events.py), the
  parent-falls loss (FUN_00477AB0 -> 0xB93 / 0xB94: status_events.destroyed, taken by the campaign's day hook).
  Its caller (an ally's unanswered call for troops) and scenario invasions: done 1L-5 (type 1 sim/empire/requests.py,
  type 2 sim/empire/invasion_events.py, types 8/9/12/15..18/20 city_events.py; docs/logic/events.md "Requests and
  invasions"). Still without a handler: 3, 5, 24, 25 (terrain disasters) and 28 (Poseidon). The defeat screen's one-day deferral (0x00FEB164): done
  1L-4 (campaign["defeat_at"], flow.screen; every defeat, the exe only the first of a session).

## Tutorials: the .sav start (1L-5, 2026-10-31)
A tutorial starts from its saved game (`tutorial_load_save` 0x005BEBD0: menu list 0 -> tutorialNN.sav, list 1 ->
tutorial08+NN.sav; `game_file_load` 0x0050E610 reads every block, then `FUN_00510ED0` (per-version fix-ups, below),
`FUN_00494BE0`, `FUN_00512590`; 0x00F2A992 = the live record's name 0x00902FC9 -> `FUN_00426700` loads the adventure
.pak for the later episodes). The save's slot is 0x00902F78 - 1 (`0x00F2A7B0`): **palace, warrior, sanctuary,
peacewar and bigcity start in slot 1** (their second episode, a continue start); the others in slot 0. Every
tutorial save plays at VeryEasy (g_difficulty 0x00F2A988 = save rank 12 = 0).

**Ours** (`sim/savimport.py`; `Game.load(PATH.sav)`, `campaign start <tutorial>`): the .sav renumbered as a map
container (save rank -> map rank table `SAV_OF_MAP`, addresses matched; the terrain image grid is not in a save:
the adventure map's, TerrainView recomputes what the city changed), so World / TerrainView / the empire builder read
it as a map; then the save's date (year rank 5, month 6, day of month 38, cycle step 37 -> our tick in the month;
year0 = scenario_start_year), treasury / tax / wage / sentiment / months in debt (city +0x0C / +0x08 / +0x2C08 /
+0x10 / +0x4824), the scenario as it stands (events rank 13 with their resolved values and run-time fields, not
resolved again; god block rank 122; allowed +0x408, games year +0x328 (i16), tutorial switches city +0x43AE / +2),
the empire as saved (rank 7 through tools/build_empire.py), and **every building through our own builders** in exe
id order: the type's catalog key (houses 2..8 -> level 0..6, 9..14 elite 7..12), placed at candidate anchors /
orientations until our footprint equals the save's (building grid rank 16 over the root and its +0x3A part chain;
agoras without their road strip; monuments: anchor and orientation from the parts, part +0x12 = the n-th layout
piece of class < 1000, our layout box must contain the parts). Avenues / boulevards: their tiles (grid = the type's
one record) with the draw byte; roadblocks: the record's tile. State per building: houses level, occupants +0x1C,
goods +0x54.. (food slots, wine, oil, fleece, armor, horses), service counters (water +0x77, healer +0x78,
philosophy +0x6D, athletics +0x6F, drama +0x71, competition +0x6C), tax days +0x4E, unrest +0xF4, devolve counter
+0x82, hunger +0xCC, fed +0x7F, plague +0x85/+0x100; workers +0x40, risks +0x48 / +0x46; crops and workshops'
progress +0x54, workshop / ranch input and gatherers' stock +0x3C (lodges: grapes +0xDC); granary food +0x56 + 2
good; storehouse / post / dock bays (+0x12 good, +0x3C amount); stall vendors (agora parts); monument pieces' stages
+0x58, complete when +0xDA is clear (the extras planted as on completion; the exe's extras buildings, +0xD8 = the
sanctuary, are skipped). Sheep and goats (figures 49 / 50) at their tiles; the palace companies recomputed from the
houses (as daily); commemoratives waiting (rank 116), population milestones (rank 58), happy months (city +0x29BC).
The terrain grid is the save's at the end, without the exe's building bit 0x8 (ours: World.occ) and 0x80000000 (not
modeled; the exe's load clears most of them).

**Fix-ups of old saves** (the tutorials are versions 235, 238, 241; GOG writes 321): FUN_00510ED0 runs one fix-up
per version step (0xCB .. 0x140). The one that matters here: **goods_remap_all 0x0050F7E0 for versions < 0x12F**:
the saves keep the Zeus goods numbering (1..7 foods, 8 wood .. 14 horses, 15 armor .. 18 wine, 19 drachmas); the
load renumbers events, cities, storages, bays, prices (= tools/build_empire.py OLD). Ours: bay goods and event items
through OLD (`savimport.old_goods`), the empire through build_empire (map version < 303). Goal records (save ranks
128/129) also hold old numbers (colony tutorial: 530 = 0x212 = old wine) and are not in the oracle dumps: ours use
the episode's goals (data/campaign, new numbering: 533).

**Oracle check** (`python3 tools/tutorial_oracle.py scenarios` + `run` -> re/oracle/runs/1L5-tutNN, the menu clicks in
the tool; `python3 tools/tutorial_check.py`): every tutorial's tick-0 dump vs our import: date, treasury, rates,
difficulty, terrain grid, each building root (key, anchor, house level / occupants / goods, workers, granary,
storage bays, monument complete), avenue tiles, roadblocks, allowed table, games year, tutorial switches, god slots,
every event (type, month, flags, resolved values, countdown, state), empire cities (kind, active, visible), herd
animals (kind, tile), palace companies (type, members): **0 differences in all 16**, except one terrain tile in
tutorial00 (94,134: the exe adds the road bit 0x40 to a ramp tile at load; the fix-up that does it is not found).
Not converted (listed so nobody assumes it): walkers on their way (service walkers, carts, traders, immigrants,
ambient figures 6, plagued walkers 66: our buildings send their own), the message list, the yearly finance and
population history, storage orders and limits, the player's world-map military history, the exe's goal table
(ours from the episode). Each tutorial then runs a year headless without error (table below).

## Adventure x episode (1L-5, 2026-10-31)
Start state, ours vs the exe, at every episode the oracle chain reaches (`python3 tools/campaign_chain.py run|check ID`:
the menus, Mortal = our Easy, forced wins, the first unfounded colony at each colony choice; compared at each slot's
first dump: date, treasury, scenario start year, start kind, allowed table, every in-use city's kind / relationship /
active / tribute mode, the events' type / month / flags), and every episode started our way and played 12 months
headless (`tools/campaign_chain.py ours ID`: empty cities, so this catches crashes, not economy drift). Tutorials:
tools/tutorial_check.py (the .sav start, above) and `campaign start` + a year (populated cities).
| Adventure | episodes in play order (slot) | start state vs oracle | a year each |
|---|---|---|---|
| Zeus and Europa | 0, 1, 2, colony 10 Cydonia, 3, 4, 5, 6 | 0 differences (all 8) | ok |
| Perseus and Medusa | 0, 1, 10 Calydon, 2, 11 Miletos, 3 | 0 (all 6) | ok |
| Athens through the Ages | 0, 1, 10 Laurion, 2, 11 Amphipolis, 3, 4, 5 | 0 (all 8) | ok |
| The Voyages of Jason | 0, 1, 2, 10 Corcyra, 3 | 0 (5); colony 11 Corinth (the other choice) not run | ok |
| Hercules Labors | 0, 10 Ephesus, 1, 11 Lerna, 2, 12 Lemnos, 3 | 0 (all 7) | ok |
| The Peloponnesian War | 0, 1, 2, 10 Taras, 3 | 0 (5); colony 11 Ithaca not run | ok |
| The Trojan War | 0, 1, 10 Tenedos, 2, 11 Pergamum, 3 | 0 (all 6) | ok |
| The Odyssey (Custom Adventures) | 0, 1, 10 Corcyra, 2, 11 Thrinacia, 3, 4 | 0 (all 7) | ok (after the fix below) |
| Open Play Economic | 0, 10 Smyrna, 1, 11 Naxos, 2 | 0 (all 5) | ok |
| Open Play Military | 0, 10 Orchomenos, 1 | 0 (all 3) | ok |
| Open Play Sandbox | 0 | 0 | ok |
| Open Play Economic 2 / Military 2 / Sandbox 2 (custom) | 0, 10, 1, 11, 2 / 0, 10, 1 / 0 | 0 (all) | ok (after the fix) |
| 16 tutorials | the save's slot (0; palace, warrior, sanctuary, peacewar, bigcity: 1) | 0 (tutorial_check; 1 terrain bit in tutorial00) | ok (populated cities; population moves: housing..trade steady, hygiene / palace / sanctuary / colony / peacewar / bigcity lose 3..30 %: not compared with the oracle over a year) |
Fix found by the year runs: `flow.next_step` read the next episode's intro record, which custom adventures do not have
(their texts are .txt files): TypeError on Proceed in The Odyssey and the "2" open plays (bugs.md 1L-5).
Not covered: the later episodes' tutorial colonies other than the Colonies tutorial's (1L-colony), the unchosen
colonies above, the Poseidon adventures (stage 3). The chain runs' wins are forced, so the goals' own judging is
covered by tools/campaign_flow_check.py (1L-3), not here.

## The campaign module (1L-3, done 2026-10-31)
`sim/campaign/` (flow.py, goals.py, cli.py); the core never imports it (test_campaign_isolated). It reaches the game
through the 1L-2 switches, `scenario.episode_end` and one named hook: `sim/hooks.py` (`g.hooks = {"day":
["sim.campaign.goals:day"]}`, called at the end of `systems.run_day`; absent in open play). CLI: docs/play.md
"Campaigns". API (for the 1L-4 screens): `flow.index/playable/start/status/next_step/proceed/replay/briefing`, 1L-4's
`flow.screen/screens/briefed/continue_building/adventures` and sim/campaign/texts.py (docs/play/campaign.md),
`goals.set_aside/month_check`; state on the game: `g.campaign = {adventure, slot, prev, colony, won, goals, result,
lost, forced, stay, done}` (saved with it).

**Order and files.** `episode_won_advance` 0x00421920 / `episode_next_slot` 0x00422FC0 as above. Ours keeps the
exe's two per-player files next to the save SAVE: `SAVE.parent.pkl` = parent.dat, written by every Proceed
(`episode_end_save_parent` 0x0052D2B0), read by colony and continue starts; `SAVE.replay.pkl` = autosave_replay.sav
(`autosave_if_due` 0x005123D0 with 0x00FEB16C = 0 right after `episode_start_load`; text group 53:0), loaded by the
defeat screen's Replay episode (0x00421730).

**Proceed** (victory screen 0x42, button 0x0052DA50): (1) `wm_sub_471E90`: a type-19 record flagged DYNAMIC (0x100)
and not DONE gets flags 0x20000; every record flagged 0x20000 is dispatched with DAT_0091BCBB = 1, which makes
`events_date_check` call it due: the editor's **end-of-episode events** (Zeus and Europa: 2..10 per episode, e.g. the
colony makes Knossos and city 10 active for the parent's next episode). Core: `scenario.episode_end`, and the type-19
handler `sim/empire/status_events.py` (and since 1L-5 the other types' handlers, docs/logic/events.md). (2) `episode_end_save_parent`. (3) `FUN_00421900`: the current
record's next (0x00902FC0 = +0x54 of the live record copy 0x00902F6C) == 3 -> screen 0x43: Proceed (adventure won)
or **Continue building this city** (0x00567820: 0x00FEAF28 = 1, +24/+60 months to a counter 0x00FEAF2C that nothing
reads; goals no longer judged); else `episode_won_advance` (0x00F2A7C0 += 1; next 1 -> the colony choice screen
0x34; else the next record's `episode_start_load`). Back in a parent city after a colony (0x00902C04 = 1, set by
`episode_end_save_parent`), entering the city (FUN_0041FE40) posts PHRASE_colony_monument (0x51A/0x51B,
[last_colony] = the colony, 0x00902C52) and grants a commemorative monument of kind 3.

**Start fixes in the core (sim/episode.py).** Colony start: the parent city also gets active = 1 and relationship 0
(ally). Continue start (and colony, a no-op there): `expedition_forces_home(_, 1)` (every company, trireme and hero
away comes home; ours walk in from the map exit as from any expedition, the exe puts them at their buildings),
and every monster on the map that is not a guardian and belongs to an event gets its hero announced again
(`monster_hero`, `hero_monster_text`, `hero_needed_message` 0x004FA710, once per hero). Last year's production
(0x00FE9724, part of the save) is kept at a continue start (measure.start).

**Goals** (sim/campaign/goals.py; `goals_month_check` 0x0052B610 is the last call of the month block of
`month_advance` 0x00483C10, after the year rollover; ours: the day hook on the month's first day). The check, in
order, as above ("Goals"); the jump tables (byte table 0x00526D68: types 0..10, 14..16 -> AND of goal_met, 11 ->
skipped, 12 -> SET the result to "year not reached" and remember "reached", 13 -> SET result and survival to "year
reached"). Then: result or survival -> 1; time limit reached -> -1 PHRASE_lose_out_of_time 0xB95; 36 months in debt
-> -1 PHRASE_lose_economical 0xB91 (the title is PHRASE_lose_title 0xB90; phrases in data/messages.json). Per type
(goal record +4 v1, +8 v2, +0xC v3, +0x10 v4; measurements from sim/measure.py):
| type | met when | counter (before the check) |
|---|---|---|
| 0 Population | population >= v1 | |
| 1 Treasury | treasury >= v1 | |
| 2 Sanctuary | v1 != -1 forces v3 = 1; v3 > 1: v4 >= v3; else v2 != -1 and god v2's sanctuary finished (FUN_004F0B30) | FUN_00525FB0: v2 = -1, v4 = 0; a god goal takes god v1 (v2 = v1, v4 = 1; twice the same god: "ERR GOAL" log); then each any-god goal takes finished sanctuaries of gods not taken (v2 = the last, v4 += 1 until v3); +0x14 = 1 for every type-2 goal after the first when there are two or more ("any other god") |
| 3 Support | units(v1) >= v2 (11 soldiers, 12 hoplites + horsemen, 13 horsemen, 57 triremes) | |
| 4 Quest / 5 Slay | event v1 (0x8C = the scratch record) has state 10 / 5 | |
| 6 Yearly production | v3 >= v2 | FUN_00526370: v3 = max(v3, last year's g_produced[v1] / 100) |
| 7 Rule | v1 outside 0..21: met; else city v1 relationship 2 (vassal) | |
| 8 Yearly profit | v2 >= v1 | FUN_00526330 (the first type-8 goal only): v2 = max(v2, last year's profit 0x00FE9714) |
| 9 Housing | v3 >= v2 | FUN_005262A0: v3 = people in houses of building type >= v1 |
| 10 Trading partners | FUN_00525EC0 (in-use trading partners) >= v1 | |
| 12 / 13 | scenario_start_year + v1 <= year (0x00526F20) | |
| 14 Set aside goods | good byte v1 & 0xFF == 0, or v3 >= v2 | the player's Set aside (below) |
| 15 Pyramid, 16 Hippodrome | Poseidon: not ported (never met) | FUN_005260F0 (pyramids): not ported |

The objectives screen (goals_status_update 0x0052B7D0) shows the same tests on the counters of the last check.
**Set aside** (type 14): clicking the goal on the objectives screen (0x0052BC20 -> 0x00529D10) opens the dialog only
when need = v2 - v3 > 0 and the city's stock in loads ((granary [goods 1..8] + trading post + storehouse units) / 100,
sculpture / 400; good 0x19 = all foods) >= need; confirming (0x0052ECF0) removes need loads (city_goods_remove
0x00489B90 mode 3) and adds need to v3. So the goods must be in storage all at once; the editor manual adds that the
next episode gives them back only through a scripted Gift event. Ours: `campaign setaside SAVE N`.
**Result handling** (goals_month_check): a recorded loss (0x00FEB160 >= 0) stays lost; the forced-win flag 0x00F2A6DB
-> won (`campaign win`, a test command); 0x00FEAF28 (continue building) -> nothing. Victory: once (0x00FEB168), the
victory screen (pause). Defeat: the first one of a session sets 0x00FEB164 and the defeat screen ("Failure!", New
Adventure / Replay episode, FUN_00422CB0(3, 0x33)) opens at the next day's check (oracle 1L3-time-limit: lost at
tick 51, screen at tick 102); ours: decided at the month change, no screen yet. Losses outside the check: a second
sack by the same city (city_conquers_player 0x00482200 -> 0xB92; sim/military sets mil["game_lost"], the day hook
takes it at once); the parent city falls to a rival while in a colony (FUN_00477AB0 -> 0xB93 / 0xB94, from an
unanswered or lost call for troops with +0x56 = 1: sim/empire/requests.py, 1L-5).

**Oracle checks (10-31)** `python3 tools/campaign_flow_check.py MODE RUN` on re/oracle/scenarios/1L3-*.txt (+ .poke;
run as docs/re/oracle.md "Run"; the month change of episode 1 opens the Hydra message, closed by its check mark):
- `goal-met` (1L3-goal-met: goal 1 poked to Treasury 5001, then 5000): not won at the first month change (dump 51:
  0x00FEB168 = 0, 0x00FEB160 = -1), won at the second by the exe's own check (the clock stops at tick 102 on the
  Victory screen, "Treasury of 5000" ticked): = ours.
- `time-limit` (goal 1 -> Time limit 0): lost 0xB95 at tick 51 = ours; `debt` (treasury -100, 35 months): months
  36, lost 0xB91 = ours.
- `return` (1L-europa-colony's dumps 60 / 310 / 620 + 1L3-europa-return: the colony won by poke at tick 900, Proceed,
  To the city): slot 1, slot 2, colony Cydonia, back to Thebes (slot 3): date, treasury, scenario_start_year, start
  kind, allowed table, every in-use city's kind / relationship / active / tribute mode, the events' type / month /
  flags: **0 differences** (before the type-19 handler: Knossos and city 10 not active, the end-of-episode events);
  the colony monument message (shot r188) and grant.

## The core's switches (1L-2, done 2026-10-31)
Generic (they read an episode record in the format above; the core never imports the campaign module) and absent
in our unrestricted open play (`sandbox_open`: no new attributes, scripts/boom.txt and full.txt state hashes
unchanged). Since 10-31 the original's open plays (`sandbox`, `sandbox2`) start through switch 2 with their own
episode (data/maps.json `episode`, sim/episode.py `open_play`; see "Open play" below).
| # | switch | where | exe |
|---|---|---|---|
| 1 | a map container of a .pak: map name `PATH#N` (0 parent, 1..4 colony n) | sim/world.py `map_path`, `read_map` (every map read goes through it) | adventure +0x49538, FUN_0042B230 |
| 2 | new game from an episode: the container's empire (built at run time by tools/build_empire.py when data/empire has no file) + the episode's player city; start year, funds x difficulty, god block, events (resolved), games year | sim/episode.py `new_city`; `Game(..., start=)`; sim/empire `new_game(g, start)`, `set_player_city`; sim/scenario `from_episode`; sim/systems/games.py reads `g.games_year` / `g.scenario_year` | episode_start_load 0x00420390 kind 0, 0x0051D5F0, FUN_00565950 |
| 2b | colony / continue starts: events rebased (month + current month, > 11: year + 1, month - 11), scenario_start_year = the current year; continue: god block re-applied (scenario_gods_apply), heroes' halls removed | sim/scenario `rebase`; sim/episode.py `colony`, `resume`; sim/gods `reapply` (roles.apply) | event_rebase_month 0x00467930, scenario_gods_apply 0x00586F70 |
| 3 | allowed buildings: the 100 flags (`g.allowed`) and buildings_availability's derivation per building (raw goods, goods list, finished sanctuaries, palace / venue, Poseidon), rules in data/allowed.json; `build` / `wall` / `bridge` / `avenue` refuse; frames and state.json carry `episode.unavailable`; play mode's menus hide them | sim/allowed.py, data/allowed.json; viewer/play/build.js `buildable`, ui.js `pageButtonShown` | 0x00402B80 -> DAT_00787178, rebuild_goods_lists 0x005BAAF0, god_resource_available 0x005BA890 |
| 4 | max sanctuaries and the gods that may get one: the episode's god block through `scenario.gods(g)` (sim/gods `menu`, `at_limit` as before) | sim/gods (unchanged), sim/episode.py | god block +0xDC / +0xC4 |
| 5 | tutorial build categories (11 page buttons) and world map button: `g.tutorial`; play mode draws the pages disabled and refuses them, and the world map button | sim/episode.py, sim/export.py `episode_export`, viewer/play/ui.js, play.js `pageKey` | 0x00FEAE06 (FUN_00516F50), 0x00FE6A5A (panel_world_map_btn 0x00409110) |
| 6 | goal measurements, goal-agnostic: `goals` command / `sim.measure.values(g)` | sim/measure.py (+ `g.year_stats`, rolled at the year's start) | goal_met 0x00526FC0, FUN_004DE170, FUN_00525EC0, FUN_005262A0, FUN_00526330, FUN_00526370, yearly_stats_rollover 0x004888E0, ledger_totals_refresh 0x00488960 |
| 7 | parent.dat's partial merge: `carry(g)` (empire, treasury, date), `colony(parent, map, ep, city)` (parent kind 3, colony kind 0, active), `back_from_colony(parent, colony, city)` (colony kind 1, tribute mode 1, parent kind 0, the colony's treasury and date); whole saves are Game.save / load | sim/episode.py; `Game.months0` (the calendar moves on while a city is not played; Game.month_index) | episode_start_load kind 1, episode_end_save_parent 0x0052D2B0 |
House types in goal 9 are building types 2..14 = our house level + 2 (FUN_005262A0 compares Building +0x10).
Goods prices: a new city takes its map's table (block 21; ours g.prices when it differs from data/trade.json,
empire.map_prices), a colony and the return carry them (episode.carry; logic/episode-transition.md B8, C1, E3).
Tests: tests/test_campaign.py test_episode_new_city, test_allowed_buildings, test_episode_sanctuaries_tutorial,
test_episode_rebase_and_carry, test_goal_measurements. Play mode checked headless on our own server (Zeus and
Europa episode 1: Raw Materials lists the Masonry Shop only; the housing tutorial: Population and Hygiene pages on,
world map button off, = the oracle's `tutorial` end shot).

## Open play (10-31, user decision the decision log "Two open plays")
The sandbox's episode writes its player city's raw goods (fish, meat, cheese, wheat, wood, bronze, marble, grapes,
olives, fleece, horses) at its new-city start, and buildings_availability then leaves out the carrot and onion farms
and the urchin quay (no carrots, onions, urchins). Oracle (re/oracle/scenarios/sandbox-food.txt, run
re/oracle/runs/sandbox-food): a new Open Play Sandbox's Husbandry page: Farms = Wheat Farm only; Hunting/fishing =
Fishery, Hunting Lodge; Herding = Carding Shed, Sheep, Dairy, Goat; Orchards = Growers' Lodge, Grapevine, Olive
Tree. Open Play Sandbox 2 (Zeus > Custom Adventures; sandbox2-food.txt): Farms = Wheat Farm; Hunting/fishing =
Hunting Lodge only (its city lists no fish either). Both = sim/allowed.py on the episode (test_open_plays).
So `sandbox` / `sandbox2` (data/maps.json `episode`: `open_play_sandbox#0`, `open_play_sandbox_2#0`) start as
`episode.new_city` does: the player city's values (also wealth 2 and strength 2, the map record has 3), the allowed
table, the episode's events and god block (the same as data/scenario/<map>.json), scenario_year, games_year 0
(= the open-play default), year_stats. Ours: `sandbox_open` / `sandbox2_open` (data/maps.json `map`: the same map
and data, no episode) = the open play before 10-31, everything buildable; the benchmarks run on it and its state is
byte-identical to before (map name `sandbox`, tools/state_hash.py full 7740f1cf..., `script boom.txt` 63ce713a...).
Saves from before have no allowed table: unrestricted. Not in data/maps.json yet: Open Play Economic / Military
(.pak) and their "2" custom adventures.

## What 1L-2 / 1L-3 need from the core (the list for the next tracks)
Core switches (1L-2, generic, open play unchanged when unset):
1. **Map from a .pak container**: `mapfile.pak_map(path, index)` (by map_offsets). Note `mapfile.read_file(pak)[0]`
   is the header's map_buffer copy = the LAST map published: right for single-map files (the sandbox), wrong for
   every campaign (it gives the last colony). sim/world.py reads `read_file(...)[0]`.
2. **Empire of a container** (`build_empire.build(path, container)`) plus the episode's player-city overrides
   (`player_city`: resources, buy/sell lists, +0x60 table, wealth, military, attitude).
3. **Allowed buildings**: the 100-flag table and FUN_00402B80's derivation (raw goods from resources/trade, gods,
   commemoratives, heroes, Poseidon mode) gating build_commit and the panel (play mode hides by availability already,
   bugs.md 323, but from open-play rules).
4. **Sanctuaries**: max sanctuaries and which gods may get one (god block +0xDC/+0xC4): sim/gods reads them from
   `scenario.gods(g)` already; feed it the episode's block.
5. **Tutorial switches**: 11 build categories + world map button (0x00FEAE06, 0x00FE6A5A).
6. **Start conditions** for a new city: start year, funds (x difficulty factor), gods, events (resolved at start),
   Olympic games year (+0x328).
7. **Scenario events and gods from the campaign file** (sim/scenario loads data/scenario/<map>.json today): load an
   episode's `events` / `gods` the same way, plus the month rebase (FUN_00467930, with its -11 quirk) for
   colony/continue starts.
8. **Goal measurements** the core must expose: population, treasury, sanctuaries finished (per god, count), military
   units supported by type, quest / monster event states (10 / 5), yearly production per good, yearly profit, people
   per house level or better, trading partners, city relationship (vassal), goods set aside "for parent city / colony"
   (stock), hippodrome length, months in debt.
9. **Whole-game save/restore with partial merge** (parent.dat): save the city at an episode end; for a colony keep
   the empire (cities, routes, world objects), goods prices, treasury and date while loading another map; set city
   kinds (parent 3 / colony 0 during the colony; colony 1 + tribute mode 1 after).
10. **Tutorial starts are saved games** (`tutorialNN.sav`): done 1L-5, sim/savimport.py ("Tutorials: the .sav
    start").
Campaign module (1L-3): done, see "The campaign module" (the colony monument: FUN_0041FE40).
