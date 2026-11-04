# Logic docs (mechanics of Zeus.exe)

Written from the decompiled exe (wave 1: 2026-10-27). Each rule is tagged **verified** (address) or **hypothesis**.
Method: [../re/method.md](../re/method.md). Structures: [../re/structs-generated.md](../re/structs-generated.md).

| Doc | Covers |
|---|---|
| [buildings.md](buildings.md) | Buildings: records, types, placement, lifecycle, road access, fire and collapse |
| [desirability.md](desirability.md) | Desirability |
| [avenues.md](avenues.md) | Avenues and boulevards: placement along roads, road bits, pictures |
| [empire.md](empire.md) | Empire: world cities, relations, tribute, gifts and requests |
| [episode-transition.md](episode-transition.md) | Episode ends and starts (new city, colony, continue, the return from a colony) and every load: what the exe sets, resets, keeps and rebuilds, against ours (audit 11-04) |
| [events.md](events.md) | Scenario events: where they come from (the `.pak` episode), types and handlers, recurring/chained events, what each open-play adventure schedules; oracle check |
| [finance.md](finance.md) | Finance: treasury, taxes, wages, debt, yearly accounts |
| [games.md](games.md) | Panhellenic games: yearly games, contestants, Athlete / Scholar monuments |
| [heroes-monsters.md](heroes-monsters.md) | Heroes and monsters |
| [housing-evolution.md](housing-evolution.md) | Housing: evolve / devolve check |
| [housing.md](housing.md) | Housing: applying evolution, goods, capacity |
| [labor.md](labor.md) | Labor: workforce, categories, employment |
| [map-terrain.md](map-terrain.md) | Map: grids, terrain flags, regrowth, meadows, road networks |
| [military.md](military.md) | Military: soldiers, companies, combat, defences, invasions |
| [navy.md](navy.md) | Navy: triremes, enemy warships and transports, sea invasions |
| [monuments.md](monuments.md) | Monuments: sanctuaries, Poseidon pyramids, palace — construction |
| [pathfinding.md](pathfinding.md) | Pathfinding (routes for walkers) |
| [population.md](population.md) | Population: occupants, migration, births/deaths, evictions |
| [production.md](production.md) | Production: farms, orchards, herding, hunting, fishing, raw materials, workshops |
| [religion.md](religion.md) | Religion: gods, prayers, blessings, wrath |
| [bridges.md](bridges.md) | Bridge tool: placement rule, commit, cost |
| [difficulty.md](difficulty.md) | Difficulty: which tables each level changes, where ours keeps them; changing it during play (live vs once, least-difficult record) |
| [sentiment.md](sentiment.md) | City sentiment (popularity), unrest/crime, migration gate |
| [services.md](services.md) | Services: what city service walkers do to houses and buildings |
| [storage-distribution.md](storage-distribution.md) | Storage and distribution: storages, cart delivery, agoras, vendors, house goods |
| [time-core.md](time-core.md) | Time core: tick, 51-step cycle, day/month/year, RNG |
| [trade.md](trade.md) | Trade: traders, trade ships, trading posts and docks |
| [world-map.md](world-map.md) | World map: screen, cities, routes, player diplomacy (gifts, requests, raids, conquest), city events; checklist vs our sim |
| [walkers.md](walkers.md) | Walkers (figures): generic machinery |
