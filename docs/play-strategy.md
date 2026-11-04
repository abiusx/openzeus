# Playing well: a strategy primer (for agent players and new humans)

Advice, not rules: the rules are in [play.md](play.md) (commands) and docs/logic/ (mechanics, from the original).
Written 2026-10-30 after the first Haiku playtest starved its city (docs/playtests/2026-10-30-haiku-1.md); agoras,
storage, unemployment and decor added after the second (2026-10-30-haiku-2.md, triage bugs.md 299..315); harvest
timing, trade quotas, footprints, culture reach and farm carts after the third (2026-10-31-haiku-3.md).
A working example city: `scripts/boom.txt` (34 Townhouses) and `scripts/full.txt` (+ elite housing, trade);
read them for layout ideas, but play your own game.

## Before you build
- Look first: `status`, `map`, `look X Y`, `catalog`. Find the land entry road (the map has one), meadow (farms),
  water (fishing), trees, rock/marble. Plan blocks near the entry: immigrants walk from it.
- Learn what a house needs to climb: `info` on a house shows its next need ("needs food types 0/1",
  "needs desirability 30 (has 25)"); docs/logic/housing-evolution.md has the table. Common houses go Hut → ... →
  Townhouse; each step needs more desirability, culture coverage, water, food *types*, fleece, olive oil, wine, arms.

## Food is the first wall
- Crops are harvested **once a year**, each in its own month (from the original's table): onions and carrots in
  **April**, wheat in **July**, grapes October, olives January. A farm's single harvest cart carries up to 800.
  A city fed only by wheat starves from spring until July. Mix crops so a harvest comes every few months, and add
  food that comes all year: fishing wharves (fish), hunting lodges (meat), goat farms (cheese), urchin quays.
- **Store before you need it**: build granaries early; check `status` storage each month; a winter with less than
  ~4 months of food in the granaries is a famine.
- Houses need several **food types** to climb (the "food types" need counts different foods held). Feed them a mix.
- Food reaches houses only through an **agora**: its food stall's buyer fetches from granaries/storehouses, and
  the agora's peddler walks the roads to the houses. `info` on a stall shows the agora's stock. Put an agora in every
  housing block and a granary near it. Watch `problems:` in `status`.
- `report husbandry` "food stored" counts granaries only (as the original): food already in agoras is not in it.
- **The first year**: nothing is carted from a crop farm before its harvest month (the whole year's crop goes in
  one cart then), so a city started in January gets its first vegetables in April and its first wheat in July, and
  the agoras need a few weeks more to fetch them. Houses that arrive in the first months go hungry and devolve
  (8 people walk out per step). Bridge it: fishing wharves / hunting lodges from the start, or food by request
  (`request CITY food`: only a city that sells a food grants it, the error lists them) or by trade. Never start a
  winter with empty granaries: the first full granary comes with the July wheat.
- Farms are easy to overbuild: a farm harvests up to 800 a year and people eat 1/4 of a unit a month each
  (100 people: 25 a month, 300 a year). Count before adding farms; surplus only fills granaries.

## Agoras and their reach (from the original's code)
- **One vendor per good per agora**: a second fleece stall in the same agora is refused. An agora has 3 stalls
  (grand agora 6): pick the 3 goods that block needs there.
- **One peddler per agora** walks out at a time and roams about 43 road tiles before turning home; it hands goods
  to houses within 2 tiles of its path. Houses far along the road from every agora get served rarely or never:
  give each block its own agora rather than relying on one.
- A stall's buyer fetches only from storage **within 40 tiles** of the agora (both axes, measured between the
  buildings' corners). An agora with no storehouse holding oil/fleece within 40 tiles stays empty of them however
  much the city has elsewhere. Keep a storehouse that accepts fleece and oil near every agora.
- `clear` on a vendor leaves an empty stall in the agora (as the original); `build VENDOR X Y` on it reopens it.

## Carts and distance
- A farm, herd or workshop sends **one cart of 100 at a time** to the nearest storage with room (by road) and the
  next only when it is back. A sheep farm 55 road tiles from its storehouse moves 100 fleece every ~2 months; its own
  stock stops at 500 and then shearing stops. `info` on the farm shows its stock and where its cart is going: put a
  storehouse on the producers' road.

## Workers are the second wall
- Only about 40 % of common residents work (Normal). Every farm (10), granary (18), sanctuary (60) takes many. Grow
  housing before industry; check `status` workforce vs jobs every month.
- **Unemployment hurts sentiment** (the original's rule): twice a month it adds +1 below 5 % unemployed, 0 below
  11 %, -1 / -2 / -3 below 18 % / 26 % / above. A city with 26 %+ unemployed and fed houses (+2) slides to 40 and
  stays there; at 36..49 no one immigrates. Add jobs, or offset it: wages 34 (+2), tax 7 % (+1). `status` prints
  the parts ("sentiment change per half-month").
- Use `priority CATEGORY 0..5` so food, storage, hygiene/safety get workers first; raise culture when houses need it.

## Storage: avoid deadlocks
- A storehouse has 8 bays of 400, one good a bay, and accepts **every** good by default. A good nobody uses
  (wine: no common house needs it, only Manors and Estates) or a big surplus (fleece) fills every bay; then
  workshops and farms stop ("no place to deliver olive_oil" in `problems:`) and houses lose the goods they need.
- Set orders early: `storage X Y GOOD refuse` for surplus goods on the storehouses near agoras, `accept` (or a
  limit) for the goods those agoras sell. `empty` only works when a workshop or another storage takes the good.
- Don't build a winery without elite housing or an export partner. Clearing a full storehouse destroys its goods.
- Watch `status` `problems:` for "no place to deliver" and act before the houses run out.

## Keep the city standing
- **Fire and collapse**: every building gains risk daily; maintenance offices' walkers reset it (fire *and*
  collapse). Build one early and one per district, on roads that loop through everything (`risk` view). A granary
  without maintenance can collapse within months. Clear rubble with `clear` before rebuilding there.
- Water (fountains), health (infirmaries), safety (guard posts) cover houses by walkers on roads: check `coverage`.

## Climbing to the top
- Desirability: gardens, statues, avenues raise it; industry, storage, tax offices lower it nearby. Keep houses
  away from noisy buildings. Decor needs **no road**: gardens, stone circles and statues work in a block's
  interior. Gates (`info` on a house shows the next one): Hovel and Homestead need desirability 10, Tenement 20,
  Apartment 30; culture 15 / 15 / 35 / 35, Townhouse 45. Granaries (-12) and storehouses (-2) lower it nearby;
  agoras raise it (+12 next to them, less farther out).
- Culture: podium, gymnasium, theatre/drama, college; venues need trained performers from their schools.
  A house's culture is the sum of the venues whose walker passed it lately: philosophy (podium) 15, athletics
  (gymnasium) 20, drama (theatre) 25, competition (stadium) 20, plus 10 for every house while the stadium has shows.
  **Townhouse needs 45, Tenement and Apartment 35**: e.g. drama + athletics, or philosophy + athletics + the stadium
  bonus. Culture walkers roam only **34 road tiles** from their venue: every housing district needs its own venues on
  its own roads. A theatre on a farm road reaches no house (`status` problems says so; check `coverage drama`).
  `info` on a venue shows its shows (a performer from the school brings 32, -1 a day).
- Goods: fleece, olive oil, wine, arms reach houses through the agora's stalls (fleece/oil/wine/arms vendors),
  from workshops (oil press, winery, armory) and storehouses; or trade (trading posts, docks).
- Taxes: only houses a tax collector's walker visits pay; one tax office per district. With no palace (it can
  collapse: keep a maintenance office near it) no clerk goes out and taxes are 0 (`status` problems: "no palace").

## Footprints
- `build KEY X Y` takes (X, Y) as the **top-left** tile; the building covers size x size tiles from there (`catalog`
  size column): granary 4x4, theatre 5x5, colleges and schools 3x3, farms 3x3, sheep farm 2x2, palace 6x9. A refused
  build names its footprint and the tile in the way.
- `clear` on **any one tile** of a building removes the whole building (as the original): check with `info X Y`
  first; the result names every building it removed.

## Building on busy tiles
- A tile with a walker on it can't be built on (as the original). Clearing a house puts its people on that tile as a
  homeless group for about a day: build there a day later, or on another tile.
- Sheep and goats go on free meadow (',' in `look`), not on plain land, roads or buildings.

## Gods, monsters, events
- An angry god's attack can be worse than its curse text suggests: Apollo's brings a plague (whatever the health)
  and stops culture and hygiene for a while. Read the "... invades" messages in `status`.
- Fewer than 4 sanctuaries: jealous friendly gods visit (harmless). Scheduled events can bring a god's attack,
  monsters near their lairs and a quest needing a hero. Sanctuaries need priests (staff) and sacrifices (animals or
  food) to stay *active*; active ones bless and help (`pray GOD`).

## Trade
- Each partner sells and buys every good up to a **yearly quota in loads** (`trade`: "olive_oil 4/12" = 4 of 12
  loads this year); at the quota its traders bring no more until January, whatever the post's order says. The
  number in `trade X Y GOOD import N` is only how much the post may hold. A city that needs 2,000 oil a year can't
  live on one partner's 12 loads: build olive trees + grower's lodge + oil press early, and import **olives** (more
  loads, e.g. Aulis 24) for the press as well as oil.

## Trade by request
- `request CITY GOOD` (or `food`): allies grant it as an offer within 1-2 months (`offers`, `offer ID accept`); it costs
  attitude. A rival grants it only if your army impresses it, else it refuses with a message.

## Habits
- Play in short batches (`do` a few commands, then advance a month, then read `status`). A failing line in `do`
  drops the whole batch: the error says so.
- Every month: food stock vs consumption, workforce vs jobs, `problems:`, houses devolving and why (`houses`).
- When something looks broken, check with `info` first; record the exact command and output if it still looks
  wrong.
