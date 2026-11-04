# Feature inventory: Zeus + Poseidon sandbox vs our engine

Goal (user, 2026-10-27): every **mechanic** of the base game's sandbox in our engine.
Source: `extracted/model/model_Normal.json` building table (Zeus type ids) + docs/logic/*.
Status: **done** = implemented and physically simulated; **part** = simplified/missing pieces; **todo**.

## Excluded (user, 2026-10-27)
Only one-off scripted events, heroes and gods are left out:
- **Scripted events**: requests/tributes from other cities, price-change events, disasters
  (earthquake, flood, ...), invasions, trade disruptions, city-status changes.
- **Heroes**: heroes' halls, hero quests, monsters (they come with gods and heroes).
- **Gods**: god visits, blessings, curses, god quests. Sanctuaries are still built as buildings (wave 5).
Everything else is in, including the mechanics that hurt: fires spreading, collapse, plague, crime.
**Military buildings are built** (wave 7) and **armies exist** (companies recruited from housing at the
palace, as the original: there are no barracks in Zeus), but nothing fights: no invasions (user).

## Wave plan
1. **Elite housing (villas)**: elite lots/houses, horses (horse ranch + corral), bronze (foundry on copper
   rock) → armory → arms vendor, horse trainer; wine chain already exists.
2. **Raw materials & food**: hunting lodge + prey (boar/deer), fishing wharf + boats, urchin collector,
   mint (silver), sculpture studio, artisans' guild; Poseidon: cattle + corral/slaughter, fruit trees +
   lodge, black marble, orichalc.
3. **Culture & science**: college/drama school (performer training), stadium, race track, Poseidon
   science (bibliotheke, university, observatory, laboratory, inventor's workshop, museum).
4. **Distribution & infrastructure**: agora (small/large), storehouse bays, bridges, walls, gatehouse,
   tower, crosswalk; fire spreading + ruins; plague; crime/thieves.
5. **Religion (buildings)**: sanctuaries built by artisans from materials, oracle/altar,
   commemorative monuments, Poseidon pyramids. God events excluded.
6. **Trade** (user 2026-10-27): emulate a set of trading partner cities, each with a capacity per good
   (what it buys / sells per year), hard-coded and active from the start (dynamic later). Their traders
   walk in from the entry (or sail to a dock), take exports / bring imports at the trading post, leave.
7. **Military buildings**: armory (wave 1), horse ranch (wave 1), warship wharf, walls/gatehouse/tower,
   chariot workshop/vendor; built and staffed, idle (no invasions).
Order agreed 2026-10-27: 6 trade -> 4 -> 5 -> 7 -> rules-based player agent.

## Status
- Wave 1 done (2026-10-27): scripts/full.txt (boom block + worker district + 10-villa district)
  holds 62 Townhouses + 10 Estates stable, treasury +5k/yr. Lessons in docs/play.md.
- Wave 2 done: fishing, urchins, hunting, corral/cattle, goats, fruit, mint, sculpture in full.txt
  (east-shore cluster + a western colony on a 184-tile road); still 62 Townhouses + 10 Estates.
  Fishing points and prey points are generated (deep water / forest edges): the map's own point
  arrays (scenario block 0x32C.., 0x394..) are not decoded yet.
- Wave 3 done (90 Townhouses + 10 Estates, all top level): schools/trainees and shows, stadium/race track, Poseidon science, per-service spawn
  delays (services.md ladders), in a north quarter of full.txt. `trainee_shows` = 32 per trainee is
  our guess (the original's show counter is not decoded). Lesson: a quarter far from every granary
  starves (buyers walk ~50 tiles at 15 ticks/tile); give it its own granary.

- Wave 7 done: trireme wharf, chariot workshop/vendor, towers staffed first. Lesson: a 100-worker wharf
  staffed before everything else costs the city a dip; full.txt builds it late and sends its workers
  home after the trireme is launched.
- Wave 5 done: Artisans' Guild, 15 sanctuaries + 15 pyramids from the original layouts, materials by cart
  (pooled per monument: ours), completion %, staff after completion. full.txt builds Hermes + Pyramid 01 with
  marble from a quarry and Sardis, wood from a timber mill, orichalc from Susa; still 90 + 10.
- Wave 4 done: fire spreading/ruins/rubble + fire fighting, health/plague (+ infirmaries in the scripts),
  criminals, agoras, storehouse bays + orders, bridges, walls/gatehouse/tower. full.txt: still 90 + 10.
- Wave 6 done (trade): docs/logic/trade.md mechanics with our partners (below). full.txt has 4 trading
  posts + 2 docks; 90 Townhouses + 10 Estates stay; treasury 38.5k vs 28.7k without trade.

## Trade partners (ours, data/trade.json from tools/build_data.py TRADE)
8 partners (the original allows up to 10 docks/posts per map), each bound to one trading post (land) or
dock (sea), active from the start. Quota = loads per year (12/24/36 like the editor's levels); a load
is 100 units (sculpture 400) at one price per good (Open Play Sandbox prices; oranges 40, black marble
150, orichalc 200, chariot 250 are ours). Every tradeable good has at least one buyer and one seller, except
oranges: no partner trades them since 2026-10-30 (a Poseidon good, off while `poseidon` is off: the decision log;
before, Babylon bought them and Tyre and Memphis sold them, 12 loads each). Horses and silver are not traded.
Quotas (loads/year) are in data/trade.json (lowered 2026-10-27: 24 -> 12, 36 -> 24; `trade` lists them).
| city | route | buys (you export) | sells (you import) |
|---|---|---|---|
| Sardis | land | wine, olive oil, armor, sculpture | bronze, marble, wood |
| Babylon | land | fleece, olive oil, wine | wheat, onions, carrots, black marble |
| Susa | land | sculpture, armor, chariot, olives | fleece, cheese, meat, orichalc |
| Ecbatana | land | wheat, marble, wood, bronze, grapes | chariot, armor, olive oil |
| Tyre | sea | fish, urchin, meat, cheese, black marble | wine, sculpture, grapes |
| Miletus | sea | onions, carrots, fleece, orichalc, wine | fish, urchin, olives |
| Memphis | sea | wood, bronze, chariot, grapes, olives | wheat, marble |
| Corinth | sea | armor, sculpture, olive oil, black marble | wood, bronze, fleece |

As the original (storage-distribution.md §8): producer carts treat an exporting post like a
storehouse (nearest wins); the post's storehousemen fetch export goods from the nearest storage (not
from one with a Get order for that good) and push imports out; the post's per-good limit (default
6000) caps only its own stock. Nothing protects home supply but the player's orders: export only real
surplus, keep goods with a storehouse Get order, or `stockpile GOOD on` (no export, no distribution).
Ours: the dock is one 4x4 building touching open water (original: 2x2 pier + 4x4 dock house).

## Buildings
| id | building | status | wave |
|---:|---|---|---|
| 2–8 | common houses (Hut..Townhouse) | done | – |
| 9–14 | elite houses (lot, devolved, Residence, Mansion, Manor, Estate) | done | 1 |
| 15–25, 118, 126–129, 145–152 | beautification (gardens..baths, avenue, boulevard, columns) | done (desirability only; avenue/boulevard along roads: logic/avenues.md) | – |
| 28 | road | done | – |
| 29 | dig = the clear-land tool (buildings.md §5), not a building | done (`clear`) | – |
| 31–33 | wheat/onion/carrot farm | done | – |
| 35–37 | grapevine, olive tree, growers' lodge | done | – |
| 39–42 | goat, sheep, sheep farm, goat farm | done | – |
| 44 | fishing wharf (boat sails to a fishing point, 204..1020 ticks) | done | 2 |
| 45 | urchin quay (diver) | done | 2 |
| 46 | hunting lodge (hunters chase deer) | done | 2 |
| 48 | mint (miners on silver rock; 200 silver → 100 dr) | done | 1 |
| 49 | marble quarry | done | – |
| 50 | foundry (miners on copper rock → bronze) | done | 1 |
| 51 | timber mill | done | – |
| 53–54 | winery, olive press | done | – |
| 55 | sculpture studio (400 bronze → 400 sculpture) | done (no consumer until wave 5) | 2 |
| 56 | artisans' guild (one artisan at a time) | done | 5 |
| 57 | granary | done | – |
| 58–59 | storehouse: 8 bays x 400, one good per bay (trade buildings 15); granary any food to 3200; orders accept/refuse/get/empty + limit | done (bays are packed, not placed tiles) | 4 |
| 60–62 | dock, trading post (caravans with donkeys, trade ships) | done | 6 |
| 63–65 | agora (6x3, 3 stalls) / grand agora (6x5, 6 stalls), agora road strip; stock in the agora, one peddler | done | 4 |
| 66, 68–71 | empty stall; food/fleece/oil/wine vendor: built on an agora stall only (as the original; the chariot vendor stays standalone) | done | 4 |
| 72 | arms vendor | done | 1 |
| 73 | horse trainer (buys horses straight from ranches) | done | 1 |
| 74 | fountain | done | – |
| 76 | infirmary (healer coverage -> city health) | done | 4 |
| 77–78 | college, drama school (trainees walk to the venue with the fewest shows) | done | 3 |
| 79, 81, 82 | gymnasium, podium, theatre (podium/theatre need shows from trainees) | done | 3 |
| 80 | stadium (+10 culture while it has shows: unique venue) | done | 3 |
| 84–98 | sanctuaries (15 layouts from Model/Sanctuary_*.txt): pieces with stages and materials, artisans, carts; staffed when complete; no god effects (excluded) | done | 5 |
| 100–114 | Poseidon pyramids (Poseidon_Pyramid_*.txt; stages by elevation; plain marble only) | done | 5 |
| 115–116 | oracle, altar | n/a: model cost 0 and no staff; the altar is a sanctuary piece (component 2), the oracle is a god feature (religion.md) — our reading, not verified | 5 |
| 117 | palace (6x9 from Model/palace.txt, complete on placement): tax offices need one, towers are only staffed with one; it holds the military companies (systems/military.py) | done | 4 |
| 119 | commemorative monument (desirability +30; granted by events as the original: population milestones, 60 happy months; `grant_monument V` in the sandbox; placed at once; docs/logic/monuments.md) | done | 5 |
| 120 | bridge: `bridge X1 Y1 X2 Y2`, straight road over water; boats pass under (ours, not decoded) | done | 4 |
| 121 | maintenance office | done | – |
| 122 | tax office | done | – |
| 123 | roadblock | done | – |
| 124 | guardpost | done | – |
| 125 | heroes' hall | excluded | – |
| 130–132 | wall (terrain 0x4000, blocks walkers; `wall X1 Y1 X2 Y2`), gatehouse (road through a wall), tower (on 2x2 walls, staffed, idle) | done (no sentries/defence: no invasions) | 4/7 |
| 133–134 | horse ranch (horses graze around it; corral not modelled) | done | 1 |
| 135 | armory | done | 1 |
| 136 | trireme wharf: 100 staff (category 8, staffed first), one trireme from 200 wood + 200 armor, moored; `staff X Y off` sends workers home | done (idle: no invasions) | 7 |
| 199 | race track (buys horses from ranches; monthly income by horses) | done | 3 |
| 201 | crosswalk ("must be placed over a Hippodrome") | n/a: our race track is one building that never cuts a road | 4 |
| 202–207 | bibliotheke, observatory, university, laboratory, inventor's workshop, museum (fill culture slots: museum=competition, observatory=philosophy, bibliotheke=athletics, laboratory=drama; university/inventors train) | done | 3 |
| 211 | orichalc refinery | done (no orichalc on this map; untested) | 2 |
| 212, 215 | chariot workshop (wood -> chariots; the original's horse buying is unused in decoded code), chariot vendor (stocks chariots; peddlers never deliver them) | done (idle) | 7 |
| 213 | black marble shop | done (no black marble on this map; untested) | 2 |
| 214, 217 | fruit growers' lodge, fruit tree (oranges never rot) | done | 2 |
| 216, 220 | corral, cattle (ranchers lead cows in; 200 meat per cow; calves) | done | 2 |
| – | endless warehouse (ours: surplus sink) | done | – |

## Systems
| system | status | wave |
|---|---|---|
| walkers at real pace, scheduler, land paths | done | – |
| immigrants (entry) / emigrants (exit) on foot | done | – |
| services, coverage, roaming memory, roadblocks | done; roam length per role from the original's budgets, turn home without a pause, early return (walkers.md §5.5) | – |
| labor + priorities | done | – |
| desirability | done | – |
| taxes, wages, sentiment, migration | done | – |
| fire/collapse risk | done: burning 1..32 days, ruins after 16, spread downwind (yearly wind), rubble (-2 des.); superintendents already out roaming find fires within 25 tiles, the nearest runs there cross-country (services.md §4.1) | 4 |
| crime | done: unrest twice a month; vandal/thief/mugger/disgruntled walkers (1/200 a day per house over 100/90/80/70); thieves rob villas, vandals destroy them, muggers kill walkers; criminals die in melee on a tile shared with a watchman/hunter/woodcutter (services.md §6.1) | 4 |
| health / plague | done: health target from healer coverage + food, daily outbreak roll below 75, deaths by difficulty (Normal 1/2), plagued walkers cosmetic | 4 |
| storage/distribution (carts, buyers, peddlers) | done | – |
| trade | done | 6 |
| monuments (sanctuaries, pyramids) built by artisans | done | 5 |
| gods, heroes, monsters, scripted events (invasions, disasters, requests) | excluded | – |
| military buildings (built, idle) | done: towers/wharves staffed first (labor category 8), trireme, chariots; no combat | 7 |
| armies (military.md "Recruitment") | done: rabble from common houses (/6), hoplites from Mansions/Manors with armor, horsemen from Estates with horses+armor; up to 20 palace companies of 8, standing at the palace; never called to arms | 7 |
