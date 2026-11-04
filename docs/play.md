# Playing the sim (for humans and agent players)

Strategy primer (advice, not rules): [play-strategy.md](play-strategy.md).

Everything goes through the CLI; the game lives in a save file, so every call is independent.
Save files (sim/savefile.py, 10-31): ours are a versioned header + zstd-compressed pickle (~200 KB for a big city;
older bare-pickle saves still load). `Game.load` / every command also accepts an original Zeus `.map` or adventure
`.pak` (a new game on that map); an original `.sav` is converted (sim/savimport.py, docs/campaign-format.md "Tutorials: the .sav start").
Run from the project root. The game's files (maps, text, sprites, sounds) must be built or installed first:
`python3 tools/assets.py build --game PATH` or `install PACK.zip` (docs/assets.md).

```
python3 -m sim new saves/me.pkl                    # new sandbox game (Zeus "Open Play Sandbox", as the original)
python3 -m sim new saves/me.pkl --map sandbox_open # the same map, every building allowed (ours)
python3 -m sim new saves/me.pkl --difficulty Hard  # VeryEasy Easy Normal Hard Impossible (default: the map's, data/maps.json)
python3 -m sim map saves/me.pkl                    # whole-map overview (find meadow, water, trees)
python3 -m sim look saves/me.pkl X Y [W H]         # ASCII view, top-left (X,Y), default 60x30
python3 -m sim catalog saves/me.pkl                # what you can build: size, cost, workers, role (Poseidon-only marked)
python3 -m sim do saves/me.pkl "CMD" "CMD" ...     # run commands (saved after; all-or-nothing, see below)
python3 -m sim status saves/me.pkl                 # date, money, people, jobs, problems
python3 -m sim info saves/me.pkl X Y               # tile / building detail (why a house won't evolve)
python3 -m sim history saves/me.pkl                # monthly numbers
```

## Maps (data/maps.json; user decision 2026-10-31, the decision log "Two open plays")
| `--map` | new-game screen | what it is |
|---|---|---|
| `sandbox` (default of `new`, `live`, File > New) | Open Play Sandbox | the original's `}Open Play Sandbox.pak`, started as the exe starts it: its episode's player city (raw goods fish, meat, cheese, wheat, wood, bronze, marble, grapes, olives, fleece, horses) and allowed table, so the build menus have **no carrot farm, onion farm or urchin quay** (oracle runs sandbox-food: Farms = Wheat Farm only, no urchin quay) |
| `sandbox_open` (default of `run SCRIPT`, `live --script`) | Sandbox (ours) | ours: the same map, empire and events without the episode: every building can be built. The benchmarks (scripts/*.txt, tools/state_hash.py, tests) run on it; its game state is the old sandbox's (map name `sandbox`, no allowed table) |
| `sandbox2` | Open Play Sandbox 2 | the original's custom adventure `Open Play Sandbox 2` (Zeus > Custom Adventures), as the exe starts it: no carrot or onion farm, **no fishery** and no urchin quay (oracle sandbox2-food: Hunting Lodge only) |
| `sandbox2_open` | Sandbox 2 (ours) | ours: the same map, everything buildable |

Saves made before 10-31 (e.g. a sandbox city started then) keep today's unrestricted rules: they have no allowed
table, and a game without one allows everything. Open Play Economic / Military (and their "2" versions) are not
playable maps yet (not in data/maps.json). How it works: a data/maps.json entry's `episode` (`CAMPAIGN#SLOT` of
data/campaign) is applied at a new game (sim/episode.py `open_play`, the 1L-2 new-city switch); `map` plays another
entry's map without it (sim/world.py `play`).

## Campaigns (track 1L-3 CLI, 1L-4 screens)
In the browser: File > New adventure > Adventures (or Custom Adventures) > pick > Begin Adventure > To the city; the
Goals button, the victory / defeat / colony choice screens and the next briefings follow (docs/play/campaign.md). The
CLI on a save:
The original adventures (data/campaign/*.json) through the campaign module (sim/campaign; docs/campaign-format.md
"The campaign module"):
```
python3 -m sim campaign list                                  # adventures; playable here or why not
python3 -m sim campaign start zeus_and_europa saves/eu.pkl [--episode SLOT] [--difficulty Easy] [--seed N]
python3 -m sim campaign status saves/eu.pkl                   # episode, goals with current values, result, next step
python3 -m sim campaign brief saves/eu.pkl [victory]          # the briefing (or victory) text
python3 -m sim do saves/eu.pkl "months 3" ...                 # play as usual; goals are judged at each month change
python3 -m sim campaign setaside saves/eu.pkl 1               # "Set aside" on goal 1 (Set aside goods goals)
python3 -m sim campaign next saves/eu.pkl [--colony Cydonia] [--stay]   # Proceed after a victory
python3 -m sim campaign replay saves/eu.pkl                   # the episode again from its start (after a defeat)
python3 -m sim campaign win saves/eu.pkl                      # TEST COMMAND: win at the next month change
```
- Difficulty: ours are VeryEasy .. Impossible (default Normal); the oracle runs' "Mortal" plays as our Easy (same
  start funds, 5000 dr in Zeus and Europa).
- A victory or defeat is decided at a month change (as the exe). The game keeps running until `campaign next` (the
  exe pauses on its victory screen). `next` on the episode before a colony asks for the colony (`--colony N|NAME`);
  after the last episode `next` ends the adventure, `next --stay` keeps building the city (no more goals).
- Next to SAVE: `SAVE.parent.pkl` (the exe's parent.dat: the parent city at the end of each won episode; colony and
  continue starts load it) and `SAVE.replay.pkl` (the exe's autosave_replay.sav: the episode's start).
- Tutorials: `campaign start housing SAVE` (any of the 16) starts from the tutorial's own Adventures/tutorialNN.sav
  (converted; its slot). Not playable: the Poseidon adventures.
- `--episode SLOT` starts a later episode only when it is a new-city episode; continue and colony episodes need the
  city of the episode before (play through, or use `campaign win` while testing).

## Watching (viewer)
- Animated: `python3 -m sim live saves/me.pkl [--script S] [--speed TICKS/S] [--port P] [--host H]`, open http://127.0.0.1:8765/ (the game, play.html; the developer map viewer is /index.html). `--host 0.0.0.0` serves other machines too (default 127.0.0.1: this machine only). `--shared`: one city for every visitor, e.g. a public server: every address opens the city directly (no main menu, the visitor's leader name is not sent; /server.json says so), and the city stands still once no tab has polled for 10 s (SHARED_IDLE; a hidden tab still counts). Tabs can't replace or delete the city: New, Load, Delete and campaign start / replay / proceed are refused. Sprite sheets (play/atlas/*.png, .bin) are served cacheable for a day, so a CDN in front of a remote server serves them.
  Runs the game itself; every walker (immigrants, carts, shepherds, woodcutters, sheep...) moves on the
  map. Works like a video: the timeline bar under the map shows what has been simulated (light part);
  click/drag to seek back, click past the light part to fast-forward (the server simulates at full
  speed up to there). Speed: presets or any ticks/s (1 = one game tick per second). 15 ticks/s
  looks like the original's normal speed (user's observation 2026-10-27, not measured). Space = pause;
  the simulation itself only runs ~1 s of playback ahead, so pausing pauses the city. Commands typed
  in the box apply at the newest simulated tick and the playhead jumps there. Buildings use the original sprites if `python3 tools/viewer_sprites.py` was run (toggle
  "sprites"); hover shows the building's name and state.
- Live: `python3 -m sim serve saves/me.pkl` then open http://127.0.0.1:8765/ . It re-reads the save
  every 1.5 s, so you can watch an agent or your own CLI session play. Drag to pan, wheel to zoom,
  hover for building details; red outline = building with a problem.
- Replay: `python3 -m sim run SCRIPT --record saves/rec-NAME` writes a monthly snapshot; then
  `python3 -m sim serve --record saves/rec-NAME` gives a slider + play button.

## Commands (inside `do`, or one per line in a script for `run`)
A `do` batch is all-or-nothing: if any command fails, nothing of the batch is saved, including the commands before it that printed `built ...`; the error line says how many were dropped. Fix the command and run the whole batch again (a script for `run` instead skips the failing line and goes on).
- `build KEY X Y`: place a building with its top-left corner at (X,Y). It occupies size×size tiles (see catalog).
- Shore buildings (fishing wharf, urchin quay, dock, trireme wharf) stand half over water as in the original:
  `build fishing_wharf X Y [n|e|s|w]` puts the 2x2 (trireme wharf 3x3) at (X,Y), one half on land (no beach),
  the other half and the tiles in front of it on water; the side is the water side, by default the first that
  fits (n, e, s, w). `build dock X Y [PARTNER][,n|e|s|w]`: (X,Y) is the 2x2 pier; the 4x4 dock house goes on the
  land behind it. `shore KEY [N]` lists the spots where one fits now. Rules: docs/logic/production.md "Shore
  buildings", trade.md "Dock placement". Docks and wharves of saves before 10-28 stay where they are (land).
- `build horse_ranch X Y [0|1|2|3]`: the 3x3 ranch house at (X,Y) and its 4x4 corral east (0, default), north (1),
  west (2) or south (3) of it (also e/n/w/s); the horses stay in the corral (production.md "Horse ranch parts").
- `road X1 Y1 X2 Y2`: L-shaped road, first along x at Y1, then along y at X2. Costs 3/tile.
- `clear X1 Y1 [X2 Y2]`: demolish buildings and roads, and cut trees in a rectangle.
- `hover KEY X Y` / `hover off`: hold a build tool over the map with its footprint's top-left at (X, Y), as the
  exe's cursor: sheep, goats and cattle grazing there walk off (a build is refused while any figure stands on its
  footprint); play mode sends it from the ghost (bugs.md 431, docs/logic/buildings.md 5).
- `tax N` (0..25, default 9) and `wage N` (default 30).
- `difficulty [NAME]`: show it, or set it at any time (as Options > Difficulty; the start funds are re-scaled
  only at tick 0 with nothing built): VeryEasy, Easy, Normal, Hard, Impossible. A new game starts at its map's default (`difficulty` in data/maps.json; every sandbox
  Normal), used by `new`, `run`, `live` and play mode's File > New; `new --difficulty D` and POST /control
  {"new": true, "difficulty": "Hard"} override it. It changes building costs and risks, the house table, tax
  sentiment, start funds, workforce share, plague deaths and the empire's moods (docs/logic/difficulty.md).
  No chooser in play mode (decision 10-28: the UI comes later).
- `priority CATEGORY N`: labor priority 0..5 (5 first; 0 = none, the default) for husbandry,
  industry, storage, hygiene, admin, culture. Higher categories are fully staffed first.
- `undo`: take back the last build/road/wall/clear action (one command, or one play-mode drag) within
  500 ticks, with a full refund (docs/play/undo.md).
- `industry GOOD on|off`: the labor advisor's industry shut-down: producers of GOOD get no workers
  while it is off (wood, marble, wheat, armor...).
- `build elite_house X Y`: a 4×4 villa lot. Elite residents don't work. Levels: Residence,
  Mansion, Manor, Estate; they need food, fleece, oil, culture 50..80, desirability 60..100, then
  wine (Manor), armor (Mansion+, from foundry → armory → arms vendor) and horses (Estate, from a
  horse ranch fed with wheat → horse trainer). A villa devolves only after 10 failed checks.
- `path X1 Y1 X2 Y2 [clear]`: road along the game's drag route (a shortest route over free land and
  roads, bending toward the start first; play mode's road tool); with `clear`, the cheapest route where
  trees on the way are cut (2 dr each).
- `include FILE` (scripts only): run another script's lines here (path relative to this file).
- `build roadblock X Y` (on a road tile): roaming walkers (services, peddlers) turn back there;
  carts, buyers and immigrants pass. Keeps service walkers inside a housing block.
- `until STAT N [MONTHS]`: let days pass until a city stat (population, unemployed, workforce,
  treasury...) reaches N, at most MONTHS (default 24). For scripts that build in phases.
- `build sheep X Y` / `build goat X Y`: place an animal on meadow; it grazes nearby. A sheep/goat
  farm's herders walk out to ready animals within 14 tiles.
- `build endless_warehouse X Y`: test sink (a test command, see below). Takes goods only when no
  workshop/storage has room; `status` shows the surplus delivered to it.
- `build trading_post X Y [CITY]` (4x4) / `build dock X Y [CITY]` (4x4, touching open water):
  bound to a partner city (default: the first free one of that route). `trade` lists partners,
  quotas used this year, orders and totals.
- `trade X Y GOOD export [LIMIT]`: carts bring GOOD to the post and its storehousemen fetch it
  from storage (post stock up to LIMIT, default 6000); caravans/ships buy it up to the partner's
  yearly quota. Nothing else protects home supply: `stockpile GOOD on|off` (city-wide: no export,
  no distribution) or a storehouse `get` order (posts never take from it).
  `trade X Y GOOD import [LIMIT]`: traders bring GOOD while the post holds < LIMIT; vendors and
  workshops fetch it from the post. `trade X Y GOOD off`. Exports earn, imports cost (`status`).
- World map (sim/empire, docs/logic/world-map.md): a new game has the map's own empire (sandbox: Olympia and
  7 cities: colony Elis, allies Tiryns/Aulis, rivals Sparta/Delos, vassal Miletos, distant Thasus). Posts and
  docks only for non-rival cities; traders only from cities that trade with you. `cities`, `city NAME`
  (panel: attitude, goods with this year's use/quota, tribute, what you may request, history).
  `gift CITY GOOD|drachmas [small|medium|large]` (400/800/1600 units or 500/1000/2500 dr, arrives in 1-4
  months), `request CITY GOOD|drachmas|food|troops|strike [TARGET]` (costs attitude; arrives in 1-2 months),
  `fulfill CITY [N] [SLOTS...]` (a city's request or tribute claim; a scenario request for troops sends the companies SLOTS, default all at home), `refuse CITY [N]` (a scenario request's refuse button), `raid CITY [GOOD] [with ALLY]` / `conquer CITY
  [with ALLY]` (all horsemen and hoplite companies at home go unless picked: see Armies below; abstract battle on
  arrival).
  Scenario-event stand-ins: `cityrequest CITY ITEM AMOUNT [KIND] [DEADLINE]`, `citystatus CITY SUBTYPE`,
  `cityinvade CITY [STRENGTH]` (a rival's army, announced, arrives in 2 months).
  Cheats for tests: `empire attitude CITY N`, `empire army CITY N` (these five are test commands, see below). `empire off` = the old partners of
  data/trade.json and no diplomacy (scripts/full.txt uses it); `empire on` before any post is built.
  `empire on WORLD` loads a world file (data/world/WORLD.json; `empire worlds` lists them); with posts already
  built, `empire on [WORLD] --migrate` re-binds them by partner name (docs/world-format.md).
- `build agora X Y [down|up|left|right]` (6x3: a road strip + 3 empty 2x2 stalls on that side) /
  `build grand_agora X Y [h|v]` (6x5, stalls on both sides of the strip). Without a side, the original's
  search (0x0040BF40) from tile X Y: each side at X Y (left, down, right, up / v, h), else anchors up to
  5 tiles up and left whose footprint covers X Y; the first that fits is built. Then `build food_vendor X Y`
  (or any vendor) on an empty stall opens it. The agora holds the stock (`info` on a stall or on the strip shows it); stall buyers fetch from
  storage within 40 tiles; one agora peddler hands out every good. One vendor per good per agora (as the original:
  a second fleece stall is refused); `clear` on a vendor leaves its stall empty in the agora. Vendors can't be built standalone
  (as the original), except the chariot vendor. Tip: lay the strip on an existing straight road.
- `build stadium X Y [v|h]`: two 5x5 halves, v = 5x10 (default), h = 10x5; each half must be level on
  its own; only one stadium per city (also not while a museum stands, as the exe).
- `storage X Y GOOD accept|refuse|get|empty [LIMIT]`: a granary/storehouse's order for one good.
  A storehouse has 8 bays of 400, one good per bay: without limits one good (fleece) fills it.
  `get` fetches the good from other storages, `empty` sends it to workshops/other storages.
- `avenue X1 Y1 X2 Y2` / `boulevard X1 Y1 X2 Y2`: drag along an existing road (straight, along the longer
  axis); each road tile gets a side strip (avenue: one side, boulevard: both); the road stays. 20 / 30 dr
  per segment; single segments are dropped. `clear` on it removes the segment, not the road
  (docs/logic/avenues.md).
- `bridge X Y`: the original's bridge tool at water tile (X, Y) beside a shore: the span runs straight across to
  the opposite shore (1..16 water tiles, open water beside it; docs/logic/bridges.md), 15 dr per tile. The old
  `bridge X1 Y1 X2 Y2` still works (X1 Y1 = the land end).
- `wall X1 Y1 X2 Y2`: L-shaped wall (5 dr/tile); walls block walkers and roads; road and other blocked
  tiles are skipped (as the original). `build gatehouse X Y [h|v]`: h (default) 5x2, road runs north-south
  through column X+2; v 2x5, road runs east-west through row Y+2. Its two 2x2 towers need free land, the
  2-tile passage is road or free land and becomes road. `build tower X Y` stands on 2x2 wall tiles (draw
  the wall 2 thick).
- `build sanctuary_GOD X Y` (hermes, dionysus, ... zeus; box w x h from `catalog`) / `build pyramid_NN X Y`:
  needs an `artisans_guild` on the road network and marble, wood, sculpture (pyramids: orichalc) in
  storage or import. Artisans build piece by piece; the info shows construction %.
- `staff X Y on|off`: send a tower's or trireme wharf's workers home (they are staffed before every
  other building, labor.md) or call them back. A wharf with a trireme refuses it (the original's wharf
  window has the button only without one): `trireme ID crew` (the Military advisor's navy row).
- Snapshots: `run` saves the full game state once a game year (.cache/ckpt) and resumes from the
  longest unchanged script prefix; a code change starts over unless `--stale` (continue an older
  code's state: fast for late-game work, rerun without it before trusting the result). Any game can
  also be saved/loaded whole: `run --save F`, `do F ...`, `live F`.
- Replay: every save keeps its command log; `python3 tools/replay_log.py COPY.pkl --save-at TICK --out DIR` rebuilds
  the game from a new one and writes it at any tick (bugs: look at the moment something went wrong).
- `report [TAB]`: the original's 11 control-panel tabs (population husbandry industry distribution
  hygiene administration culture mythology military aesthetics overview; `!` = a problem, the
  original's yellow text). Husbandry's "food stored" counts granaries with road access only, as the original
  (food in agoras is not in it). The viewer shows them as tabs next to Summary (sim/reports.py).
- `status` shows jobs per labor category and the open ones (viewer: "jobs" row).
- `towers on|off`: the Military tab's "man all towers" button: every tower at once (wharves keep
  their own `staff` switch).
- `build palace X Y` (6x9): needed before any tax office, and for towers to get workers.
- Armies (sim/military, docs/logic/military.md; `military off` switches the module off): `companies` lists the
  palace companies; `mobilize SLOT|all [X Y]` (soldiers appear at houses of their class and march to the spot),
  `move SLOT X Y`, `attack SLOT X Y` (onto an enemy there), `mode SLOT hold|attack|special`, `rotate SLOT`,
  `return SLOT|all` (each walks to a house and vanishes into the palace). Invasions from rival cities now arrive
  on the map (`invasion` shows them and the bribe, `bribe` pays it). Wolves roam at the map's wolf points.
  Tests (test commands, see below): `invade [X Y] [N] [ARMY]` (an army of strength N at X Y, default a land invasion point),
  `wolves X Y` (a new pack). Towers at full staff keep an archer and a wall patrol (2-thick walls).
  Navy (docs/logic/navy.md): `navy` lists the triremes; `trireme ID X Y` sails there or attacks an enemy on that
  tile; `trireme ID crew` sends the crew home / calls it back. `invade [N] [ARMY] sea` tests a sea invasion
  (warships + transports from the map's sea point, landing at its landing point).
  Expeditions: `raid CITY [GOOD] [with ALLY] [companies 1,2|none] [ships ID,ID|none]` / `conquer CITY ...` (the
  army dialog's picks; default: every horseman/hoplite company at home and, for a sea route, every trireme).
  Offers (gifts, tribute, granted requests, plunder, defensive aid): `offers`, `offer [ID] accept|postpone|decline`
  (play mode opens them in the message window).
  `autodefend on|off` (Options > Auto Defend): one month before an invasion every ready company musters at the
  rally point (mid-way from the invasion point to the palace) and military labour goes to top priority; a month
  after the last invader they go home.
- `days N`, `months N`, `step N` (ticks): let time pass. 1 day = 51 ticks, 16 days = 1 month.
- Episodes (campaigns, track 1L-2; docs/campaign-format.md "The core's switches"): `goals` prints what the goal
  checker measures (population, treasury, finished sanctuaries, units by the exe's unit ids 11/12/13/57, event
  states, last year's production and profit, people per house type, trading partners, relations, stock, debt
  months; sim/measure.py), read only, in any game. `allowed` lists the buildings the episode leaves out (open play:
  every building). In an episode game `build` (and `wall`, `bridge`, `avenue`, `boulevard`) refuses a building the
  episode does not allow: "X is not available in this episode". Starting an episode is the campaign module's
  (1L-3); from Python: `sim.episode.new_city(MAP, EPISODE)`, `colony(...)`, `resume(...)`.
Coordinates are grid tiles (x right, y down) on a 228×228 map; the playable land is a diamond.
`E` in `look` marks the entry point, where immigrants arrive.

## Test commands (decision 2026-10-31, the decision log)
Commands the original has no player action for (they inject an event, set a hidden value or give something free)
are test commands. The one list is `COMMANDS` in sim/testcmds.py:
`wolves`, `invade`, `cityinvade`, `cityrequest`, `citystatus`, `empire attitude`, `empire army`, `jealous`,
`godattack`, `godvisit`, `monster`, `quest`, `heroes cheat` (`heroes cheat off` is not), `alert raise`, `funds`,
`grant_monument`, and `build KEY` for buildings marked `"test": true` in data/buildings.json (`endless_warehouse`).
Settings and module switches (`gods|military|heroes|empire|scenario on|off`, `poseidon`, `difficulty`), views and
`until`/`days` are not test commands.
- They work, but the output starts with `TEST COMMAND (NAME, use N; not a player action, counted in the save): ...`
  and the save counts the uses per command (`test_uses`; refused or failing commands are not counted). `status`
  shows them on its second line: `test commands on; used: funds 2, wolves 1` (old saves: `used: none`).
- `testcmds [on|off]`: the game's switch, stored in the save. Default on (new games, old saves, `do`, `run`
  scripts, tests). While off, a test command is refused (`'wolves' is a test command and test commands are off in
  this game`); `testcmds on` switches them back and is itself counted (`testcmds on 1`). Effects already applied
  stay (a hero cheat stays on until `heroes cheat off`).
- Live server: `python3 -m sim live SAVE --no-test-commands` refuses them for the server's whole run, whatever
  the save says (also after File > New / Load), and refuses `testcmds on`. Without the flag the save's switch
  decides (default on), so agents' test servers and tools (tools/gods_pose_check.mjs, `live --script` with test
  lines) keep working. Start a server for real play with `--no-test-commands`.
- Play mode never offers a test command: the build menus skip `"test": true` buildings (viewer/play/build.js
  `buildable`) and no button sends one. Only the sim viewer's typed command box (viewer/index.html) can, subject
  to the switches above.
- `catalog` marks test buildings `TEST ONLY (counted)`.

## How the city works (short)
- **Housing**: `build house` places an empty 2×2 lot. Immigrants come if city sentiment is
  good and there are vacancies. Houses evolve Hut → Shack → Hovel → Homestead → Tenement →
  Apartment → Townhouse when their needs are met: food (from a food vendor), water (fountain),
  culture (podium/gymnasium/theatre/stadium walkers), fleece/oil/wine (vendors), and enough
  **desirability** (gardens, statues, parks raise it; industry and farms lower it). `info` on a house
  tells you what it lacks.
- **Every building needs road access**: a road tile touching one of its sides. Buildings with
  workers also need housing on the same road network.
- **Workers**: about 40% of the population works. Jobs go to higher-priority categories first,
  then are shared evenly. A building with fewer workers works slower. Every building wears out
  and can burn from the day it is placed, staffed or not, so grow gradually: build what your
  workforce can staff (and maintain), then more as unemployment rises.
- **Production is physical**: farms grow crops and harvest once a year; woodcutters and
  stonecutters walk to trees/marble; shepherds walk to sheep; growers tend and pick olive trees and
  grapevines placed near their lodge. Carts carry goods on roads to workshops, then storage.
- **Walkers** leave service buildings and roam the roads: water carriers and healers 26 tiles,
  culture walkers and tax collectors 34, maintenance, watchmen and peddlers 43. Every building within
  2 tiles of the road they walk gets served: water, culture, maintenance (stops fires/collapse),
  watchmen (crime), tax collector (houses only pay taxes if visited).
- **Food**: farms must be built on meadow (`,`) and harvest once a year (July), more with full
  staff. Carts take the crop to a granary; a food vendor's buyer fetches from the granary and its
  peddler hands food to houses. Houses eat monthly. Hungry houses lower sentiment.
- **Goods**: sheep farm (meadow) → fleece; growers' lodge → olives → oil press → olive oil.
  Raw goods go to a storehouse; vendors fetch from there.
- **Risk**: buildings slowly build up fire and collapse risk; maintenance walkers reset it.
  Without them, buildings burn or collapse after a few months.
- **Money**: start 15000 dr. Building costs money; taxes come in monthly from houses the tax
  collector visited; wages go out monthly. Below −2000 you can't build.
- **Sentiment** (0..100, starts 60): taxes, wages, unemployment, food, debt. Above 50 people
  come; below 36 they leave. Unemployment counts: 11 %+ unemployed costs 1..3 points twice a month
  (docs/logic/sentiment.md 3); `status` prints the parts.

## Lessons from building the full city (scripts/full.txt)
- Walkers roam 26 to 43 tiles (culture 34): on a big ring, put every needed service on each long side.
- A venue without shows sends nobody: build enough schools (the north-east villa needed a 4th drama school).
- Corner houses have fewer decorations in range; put decor (stone circles) on the corners.
- Negative-desirability services (tax office -4, guardpost -2, storage, industry) go mid-side,
  more than their range (2..4) away from the houses that need high desirability.
- Orchards: each lodge sends at most 4 pickers, and a trip takes days at walking pace; fruit rots
  2 months after ripening. Plan ~1 lodge per 10-12 trees.
- Villas need many workers elsewhere: build a common-housing worker district.
- Horse ranches hoard up to 800 wheat each; plan farms for them.
- A long road out of a district gives its service walkers somewhere to wander off to: put a
  roadblock where it leaves (carts still pass), and give the far end its own maintenance.
- Fishing boats need fishing grounds connected by water; hunters need prey near their lodge.
- Agoras sell every food the city holds (ours since 10-30, an exe bug fixed: the exe's buyers take only the first 5
  of the city's food list and can come back empty from a granary of wheat and onions; bugs.md 297, data/fixes.json).
  Oranges are a Poseidon good: off (not traded, not stored) unless `poseidon on`.
- Podium/theatre/stadium only work with shows: build a college/drama school on the same road
  network; trainees walk to the venue with the fewest shows, so put schools near the venues.
- A quarter far from every granary starves (its vendors' buyers walk ~50 tiles each way): give it
  its own granary. Olives piling up in storehouses means too few oil presses.
- Trade: export only real surplus. Without a reserve the posts empty the storehouses and houses
  devolve; quotas are large (12..36 loads/year per good per partner).
- A building with damage risk (sculpture studio) collapses within a few years without a
  maintenance walker passing; check `risk`.
- Build infirmaries: city health = share of residents with healer coverage (+ fed). Below 75 a
  plague can kill half of an infected house. One infirmary walker covers ~26 tiles of road.
- Fires: a superintendent already out roaming within 25 tiles runs to the fire; it saves the
  building if it arrives within ~16 days, so keep maintenance walkers everywhere. Rubble (r in `look`) costs 2 desirability; nothing can be built on it (as the exe: map_area_buildable's mask has the rubble bit), so `clear` it first (2 dr a tile).
- Ideal layout = no house devolves after the layout is final (`run` prints `stability`; the tests
  require 0 after the last build + 24 months). Check every chain's yearly supply against demand:
  oil 1 per house per half month (a press makes 100 per 2 months), fleece likewise (a sheep gives
  ~400 a year), and give each important good its own storehouse bays (8 bays of 400 per storehouse).
- Exports drain the city unless only real surplus is exported (the endless warehouse shows it).
- A grower's lodge picks trees within 12 tiles of its corner only; trees farther away are never
  picked. Ripe olives rot in month 2, so pickers that fall behind lose the harvest.
- Agoras: one per straight road segment of 6 tiles. Every agora's peddler hands out everything the
  agora holds, so give a district one agora with all the goods its houses need (a top road with
  food + fleece but no oil left two houses short of oil).

## Baseline save (user, 10-28)
`the baseline save` (git-ignored like all saves): the user's played sandbox city as a frozen
test baseline: pop 3,250, 326 buildings (54 houses, 10 villas, 23 storehouses, 4 trading posts on the `partners`
world, colleges/theatre/podium, quarries, foundries, gatehouses, towers, sanctuaries of Athena and Apollo, 54 building types). Use a COPY for every check
(load, run, browser); never write to it. Agents: re-run your change on it as a regression check besides the tests.
It carries legacy states from older code (wharves/dock placed on land, a ranch that adopts its corral, posts
migrated to `partners`, digging done before quarry depths were recorded): a load/migration test, not a picture of
correct play. The user plays fresh games on Hard from 10-28.

## README pictures (11-04)
`release/public/media/` (exported to the public repo's `media/`): `gameplay.gif` and the hi-res examples.
- GIF: a copy of the baseline save served on its own port (`python3 -m sim live COPY --port 8797 --speed 30`), then
  `node tools/readme_gif.mjs http://127.0.0.1:8797/play.html FRAMEDIR --at 145,150 --frames 60 --every 100 --rate 60`
  (headless Chrome 1280x800 at dpr 1, every hi-res set on, the city at 60 ticks/s, the dev bar cropped; frames come
  ~150 ms apart) and `python3 tools/readme_gif.py FRAMEDIR release/public/media/gameplay.gif --width 960 --ms 150`
  (one shared 256-colour palette, no dither): 60 frames, 960x548, 1.8 MB.
- Hi-res examples: `python3 tools/readme_media.py release/public/media` (needs extracted/hires, the 4x masters).
