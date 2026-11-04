# Scenario events, and what open play runs

Status: **verified** from the exe unless marked. Addresses refer to GOG `Zeus.exe`. Written 2026-10-29 (track 1A).
Tool: `python3 tools/scenario_events.py` (`list FILE`, `openplay`, `oracle RUN`). Names: `re/names/events.tsv`.
Companion docs: [world-map.md](world-map.md) 6 and 9 (city events, record fields), [military.md](military.md)
"Events" (invasions), [heroes-monsters.md](heroes-monsters.md) (monster events, heroes), [religion.md](religion.md)
(god attacks, jealousy), [games.md](games.md) (events 35..37).

## Summary
- Open play is an ordinary adventure (`.pak`) with one episode and no goals. Its scheduled events and its god
  roles come from the **`.pak` episode**, not from the map: at the episode start the exe copies the episode's
  events and god block over the map's. The map's own event block (rank 16) is an editor leftover.
- There is **no open-play switch** that skips events, gods or monsters. `scenario_events_monthly` runs every
  month unconditionally (only `editor_mode` `0x00665E2C` skips invasions).
- **`}Open Play Sandbox.pak`** (the "Open Play Sandbox" of the adventure list, the map our `sandbox` uses) has 4
  events: a Zeus quest (Golden Fleece) in year +3..4, a Maenads attack in year +11, a Talos attack in year +20..21,
  and a god attack (Poseidon, Hermes or Apollo) in year +5..8 that **recurs every 5..8 years**. Its friendly gods
  (Zeus, Hades, Aphrodite, Artemis, Demeter, Athena) are all "may be jealous": until 4 sanctuaries stand, a
  jealous god attacks the city every 6..12 months.
- Oracle run (empty city, Jan 1000 to Jun 981 BC): jealous gods came 25 times (Artemis 11, Aphrodite 7,
  Demeter 3, Zeus 3, Athena 1), Apollo's scheduled attack came in Dec 995 BC and again in Dec 988 BC, the Zeus quest
  opened in Apr 996 BC and stayed open, the Maenads arrived in Aug 989 BC and stayed (section "Oracle check").
- So gods, monsters and heroes are part of open play. None of it is in our sim yet (section "Ours").

## Where the events come from
`screen_start_game` `0x004214F0` (state `0x00F2A6DD == '5'`) → `episode_start_load` `0x00420390`:
```
adventure_read(.pak header)                          # 0x0042B3E0 -> adventure_read 0x00425D00 (+ 0x0052DF50)
scenario (2032 B) <- adventure +0x1BE4 + ep*0x7F0    # adventure_episode_scenario 0x0042B460: start year, funds, ...
g_scenario_gods (0x00FFA450) <- adventure +0x8B98 + ep*300     # adventure_episode_gods 0x0042B4D0; scenario_gods_apply 0x00586F70
g_events (0x009173F4, 150 x 124 B) <- adventure +0x9C00 + ep*18600   # adventure_episode_events 0x0042B710
g_events_count (0x009173F0) <- adventure +0xC366C[ep]                 # adventure_episode_event_count 0x0042B760
for each event: event_resolve_at_start 0x00467660
then the episode's map is loaded (hypothesis: FUN_00516D50, not traced)
```
Colonies are episodes 10..13 (events +0x37290, counts +0xC3694). Every open-play file is `.set` version 5:
episodes' god blocks are 224 bytes in the file (300 in memory) and the events start at file offset 0x97D8
(`refs/zeus-poseidon-arm64/formats/set.md`). Fix-ups in `adventure_read` for old versions: v < 25: requests of kind 7
get item 24 (troops); v < 26: byte +0x7A of type-4 (quest) events is zeroed (so every open-play quest is the god's
first quest).

Evidence that the episode wins: `}Open Play Sandbox.pak`'s two maps have 0 events in block 16, but the oracle's
sandbox saves (`re/oracle/runs/rotation-sandbox`, `gate-walk`) hold exactly the episode's 4 events (types 4, 26, 26,
27, months 3, 6, 0, 11) and its god block. `Open Play Sandbox 2P.map`'s 16 block-16 events (types 23, 2, 1, 21, 4, 19,
which empire.md quoted) are byte-for-byte the colony events of `}Open Play Military.pak`: an editor copy.

Goods in events use the old (pre-Poseidon) numbers in these files; `goods_remap_all` `0x0050F7E0` renumbers each
event's item (`event_goods_remap` `0x0050F3C0`, only for types that carry a good, `event_has_goods_item`
`0x00468DA0`) when the map is older than version 303 (old 19 = drachmas, 20 troops, 21 food; e.g. a 5000-drachma
gift is item 19). Settled 10-31 (1L-1, docs/campaign-format.md): `adventure_read` renumbers every episode's events
once at read time for .set versions < 22 (FUN_00425260 -> event_goods_remap); the map's goods_remap_all runs at the
map load, before the episode's events are copied in, so they are renumbered exactly once (oracle: Zeus and Europa).

## The record (124 bytes, struct `ScenarioEvent`, world-map.md 9)
Fields used by open-play events: `+2` type, `+3` month (0..11), `+0x24` chained event (−1 none), `+0x28` flags,
`+0x2C` lead/warning months, `+0x2E` countdown, `+0x30` state, `+0x32` active, `+0x36`/`+0x38`/`+0x3A`/`+0x3C`/`+0x3E`
type-specific bytes, `+0x60` kind/god/variant byte, `+0x7A` quest number.

Value groups (`event_value_resolve` `0x004673C0`), 4 × i16 `(value, a, b, c)`, resolved once at the start (and again
when a recurring event re-arms): `a >= 0, b < 0` → `a`; `a >= 0, b >= 0` → one of `a, b` (and `c` if `>= 0`), one
`random_next`; `a < 0` → random in `[b, c]` (`rng_15 % (c−b+1) + b`). Quirk: `a < 0` and `b == c >= 0` gives
`value = a` (negative). Groups: `+0x04` item / subject (god, monster slot), `+0x0C` amount, `+0x14` year offset
(from the scenario start year `(i16)0x00902928`), `+0x1C` city / point, `+0x58` second city (the invader for type 2).
`event_resolve_at_start` also clears flags `0x40EC4`, sets `+0x2E = month + year offset`, `+0x30 = 0`, `+0x32 = 0`,
`+0x61 = rng_15 % 5 + 4`, `+0x62 = rng & 1`; type 2: landing point `+0x78`; type 3: earthquake points.

Flags: `1` template (skipped by the monthly pass; fired only as another event's chain), `2` **recurring** (the editor
default, `event_init_defaults` `0x00467590`), `4` done, `0x40` warn before (god attacks), `0x80` warned,
`0x100` dynamic (created at run time), `0x20000` disabled (`invasion_event_pending` and the quest handler skip
`flags & 0x20001`).

## Monthly pass
`month_advance` `0x00483C10`, month change (day 15): `invasions_month_update` `0x00504A30` (type 2 only, military.md),
then `scenario_events_monthly` `0x0046D380`:
```
for each event i < g_events_count with (flags & 1) == 0: month_events_dispatch(ev)     # 0x0046DFD0
FUN_00483040()
events_rearm_recurring()                                                              # 0x0046D660
```
`events_rearm_recurring` `0x0046D660`: every event with `flags & 4` (done), `+0x32 == 0` and `flags & 2`
(recurring): clear 4, `event_resolve_at_start`, then `year offset = max(1, resolved) + (year − start year)`, i.e.
it comes again `resolved` years later, at the same month. **verified** in the oracle (Apollo's attack, year group
5..8: Dec 995 BC, re-armed to +12 → Dec 988 BC, re-armed to +20).

`event_chain_trigger` `0x0046DE00(ev, ...)`: copies event `+0x24`'s record into a new dynamic record
(`events_alloc` `0x00467A40`), resolves it, flags `0x108`, dated now; keeps the parent's city / item when they fit the
child's range. Used for rewards: a quest or a killed monster triggers its gift.

## Event types (`month_events_dispatch` `0x0046DFD0`; names = text group 156, the editor's list)
| type | editor name | handler | effect | in open play |
|---|---|---|---|---|
| 0 | Free Event | – | none | – |
| 1 | Request | `event_request` `0x00470800`; troops (item 24) `event_troops_request_update` `0x0046ED70` | a city asks for goods/money/troops (world-map.md 6.5; kinds 0 general, 1 defend an ally, 2 attack a rival, 3 festival, 4 building, 5 famine, 6 financial, 7 quest); ours sim/empire/requests.py (1L-5, section "Requests and invasions") | Economic, Military |
| 2 | Invasion | not dispatched here: `invasions_month_update` `0x00504A30` → `invasion_event_month` `0x00476E20` | rival army lands (military.md); ours sim/empire/invasion_events.py (1L-5) | Military |
| 3 | Earthquake | `event_terrain_disaster` `0x0046D6D0` | terrain disaster (FUN_00446AE0 picks one of the map's 8 disaster points, FUN_004474E0 starts its object; earthquake spread 0x00506330): **not ported** (the on-map disasters are a subsystem of their own) | – |
| 4 | Quest | `event_quest` `0x00482820` | a god's quest: needs a hero (below) | **Sandbox**, Sandbox 2, Economic, Military |
| 5 | Landslide | `event_landslide` `0x004732B0` | terrain change at a scenario point (FUN_00506BB0 object, message 0xDE 0xC79/0xC7A): **not ported** (as 3) | Economic 2 colony |
| 6, 7 | Sea / Land trade problem | `event_mark_done_and_chain` `0x00472EC0` | **nothing** but done + chain (Pharaoh leftovers) | – |
| 8, 9 | Wage increase / decrease | `event_wage_increase` `0x00472F00` / `_decrease` `0x004730A0` | the wage expectation 0x00FE9664 (read by nothing else: Pharaoh) ± amount within 5..45, messages; ours sim/empire/city_events.py (1L-5) | Economic |
| 10, 11 | Contaminated water / Copper mine collapse | `0x00472EC0` | nothing but done + chain | – |
| 12 | Clay pit flood | `event_clay_pit_flood` `0x004733F0` | done, nothing else; ours city_events.py | – |
| 13, 14 | Demand increase / decrease | `event_demand_increase` 0x00472540 / `_decrease` 0x004727C0 | a city's quota of a good it buys, one step on 0/12/24/36 (ours: sim/empire/quota_events.py, 1L-5) | Economic 2 |
| 15, 16 | Price increase / decrease | `event_price_increase` `0x00472B20` / `_decrease` `0x00472D00` | goods_price[item] ± amount (2 at the floor); ours city_events.py + trade.set_price (g.prices) | Economic |
| 17, 18 | Favor increase / decrease | `event_favor_increase` `0x0046E840` / `_decrease` `0x0046E970` | a city's attitude ± amount; ours city_events.py | – |
| 19 | City status change | `event_city_status_change` `0x00473680` | subtype `+0x60` = text group 35 (empire.md "City events"); ours sim/empire/status_events.py: every subtype, messages, warning, follow-ups 0->1 / 6->0x17 / 13->0x16, subtype 24 conquest (FUN_0046EAC0) (1L-5) | Economic 2, Military |
| 20 | Rival army away | `event_rival_army_away` `0x00474160` | 3/5 of a rival's army away for 12 months (city_army_away_12 0x0042E230); ours city_events.py | – |
| 21, 22 | Supply increase / decrease | `event_supply_increase` 0x00472030 / `_decrease` 0x004722B0 | a city's selling quota, the same steps (quota_events.py, 1L-5) | Economic 2 |
| 23 | Gift | `event_gift` `0x00474A80` | goods/money from a city (world-map.md 6.3) | Sandbox 2 (quest rewards), Economic, Military |
| 24, 25 | Lava flow / Tidal wave | `event_terrain_disaster` `0x0046D6D0` | terrain disaster: **not ported** (as 3) | Economic 2 colonies |
| 26 | Monster invasion | `monster_event_update` `0x00481430` | a monster comes (heroes-monsters.md) | **Sandbox**, all |
| 27 | God invasion | `event_god_attack` `0x00482B10` | an unfriendly god attacks (religion.md) | **Sandbox**, Economic 2, Military |
| 28 | Sink land | `event_sink_land` `0x0046D790` | Poseidon (Atlantis): not ported (Poseidon is off) | – |
| 0x1D..0x22 | internal | `0x00474F60` tribute in, `0x004715C0` tribute out, `0x004742A0` relationship letter, `0x004752A0` granted delivery, `0x004756B0` refused demand, `0x00480A00` ally strike | world-map.md 6, 9 | created at run time (tribute in every January in the sandbox) |
| 0x23..0x25 | internal | `0x0046E1A0` / `0x0046E400` / `0x0046E5A0` | Panhellenic games (games.md) | yes (yearly) |
| 0x26 | internal | `0x00481A30` | not traced | ? |
| 0x27 | internal | `hero_arrival_event_update` | hero arrives after "send for" (heroes-monsters.md) | with heroes |

### Quest (type 4, `event_quest` `0x00482820`)
Fields: `+0x60` god (0..13), `+0x7A` quest 0/1 (0 in all open-play files), `+0x36` monster slot whose hero is
needed (`scenario_hero_of_monster_slot` `0x00586C40`: slot 0/1 → hero of the monster of unfriendly god slot 0/1,
2 → hero of the independent monster), `+0x38` statue variant selector (`quest_statue_variant` `0x004825C0`:
commemorative variant 10..65), `+0x24` reward event.
```
state 10 or 5: return
state 0: if active (+0x32) or flags & 0x20001 or not this year/month: return
         countdown = 0; active = 1; message 0xE0 (quest_title_text 0x00482360: PHRASE_<god>_quest_title ..),
         sound (0x005A1050 god, 5); if the hero is needed: hero_needed_message(quest_hero_text 0x004FDA40(god, quest))
state 6 (the hero is away on the quest): countdown −1; when event_months_until_due < 1: state 7, countdown = 0x0046D950()
state 7 (returning): countdown −1; at 0: message 0xDE, 0x004DEE60, grant the commemorative statue (0x00402B00),
         chain the reward (+0x24), state 10, active 0
```
Without the hero the quest stays open (active) for ever (oracle: open from Apr 996 BC to the end of the run).

### Monster invasion (type 26) and god invasion (type 27)
See heroes-monsters.md "Monster events" and religion.md "Scenario god attack". Open-play specifics: every
open-play monster event has aggressiveness `+0x3E = 0` (rest 10 000 days: the monster stays at its lair and only
attacks what is built near it) and targets `+0x38..0x3C` = 0 (`}` files) or 10. Observed: the `}` sandbox's
Maenads event (lead 1 month) was in state 4 (warning countdown) from the first month; the Talos event (lead 2) stayed
in state 0 (heroes-monsters.md open question "status 4").

## Open-play adventures the game ships
`Adventures\` holds `}Open Play Sandbox.pak`, `}Open Play Economic.pak`, `}Open Play Military.pak` (kind 0) and the
folders `Open Play Sandbox 2`, `Open Play Economic 2`, `Open Play Military 2` (kind 1: `.pak` + `.set` + `.txt` +
editor `.map` files). The oracle's "Adventures → Open Play Sandbox" (`re/oracle/scenarios/sandbox-start.txt`) loads
the `}` file. I'm not certain whether the adventure list also shows the "2" folders. Only the sandboxes have a single
episode; Economic and Military have 2..3 episodes plus colonies (they are short campaigns without goals).

### `}Open Play Sandbox.pak` (our `sandbox`; 1 episode, start 1000 BC)
| # | type | when | what |
|---|---|---|---|
| 0 | Quest | Apr, year +3..4 (oracle: +4) | Zeus, "The Golden Fleece"; hero of monster slot 0 (Hermes → Minotaur → Theseus); statue variant 2; not recurring |
| 1 | Monster invasion | Jul, year +11, lead 1 month | slot 2 = independent monster Maenads; not recurring |
| 2 | Monster invasion | Jan, year +20..21, lead 2 | slot 1 = monster of Hephaestus = Talos; not recurring |
| 3 | God invasion | Dec, year +5..8 | Poseidon, Hermes or Apollo (oracle: Apollo); no warning; **recurring** every 5..8 years |
Gods: unfriendly slots 0..3 Hermes, Hephaestus, Poseidon, Apollo; 4..11 Ares; friendly 12..17 Zeus, Hades,
Aphrodite, Artemis, Demeter, Athena, all "may be jealous"; independent monster Maenads; max sanctuaries 4.

### `Open Play Sandbox 2.pak` (our `sandbox2` map; 1 episode)
3 quests, each with a reward gift (templates, flag 1): Hephaestus year +5 (→ 32 marble), Dionysus +10 (→ 32 wine),
Aphrodite +15 (→ fish, wheat or cheese ×32); 3 monster invasions with rewards: independent monster Hector year +8..10
(lead 6, → 32 wine), slot 1 (Hermes → Minotaur) +16..18 (→ 5000 drachmas), slot 0 (Athena → Hydra) +23..25
(→ 16 sculpture, armor or meat). Gods: unfriendly Athena, Hermes; friendly Zeus, Demeter, Hades, Hephaestus,
Artemis, Aphrodite (jealous) + Dionysus (slot 18, not jealous). Reward gifts name city 0 (the player's own city
record); I'm not certain how the gift message reads then.

### Economic and Military (for stage 2)
`python3 tools/scenario_events.py openplay` lists them in full. `}Open Play Economic`: requests, price
changes, wage increase, a quest (Demeter) and monster invasions. `Open Play Economic 2`: also demand/supply changes,
status changes, a recurring god invasion, colony disasters (tidal wave, lava flow, landslides). Military: requests for
troops, invasions, god invasions (Athena, Zeus), monster invasions, status changes.

## Oracle check (2026-10-29)
Run: `re/oracle/scenarios/open-play-events.txt` (`}Open Play Sandbox`, Mortal, nothing built; a right click every
20 s; dumps every 816 ticks; run as docs/re/oracle.md with `ZEUS_STATE_DUMP_EVERY=816 --seconds 44010`, `DIR` in the
script replaced by the run directory, 7 min). Timeline: `python3 tools/scenario_events.py oracle re/oracle/runs/open-play-events`.
- Jealousy countdown (`0x00FE6A58+1`) 99 at the start, then 12, 11, … 1, then an attack and a new 6..12.
- Jealous attacks (god figure on the map, attack slot set; dump dates, BC): 999/2 Artemis, 999/9 Artemis, 998/6
  Artemis, 997/1 Aphrodite, 997/10 Artemis, 996/5 Aphrodite, 995/1 Demeter, 995/8 Artemis, 994/4 Aphrodite, 994/12 Zeus,
  993/11 Aphrodite, 992/8 Demeter, 991/2 Athena, 991/11 Zeus, 990/9 Aphrodite, 989/9 Zeus, 988/6, 987/4, 986/2,
  986/11, 985/8, 984/5 Artemis, 983/1 Aphrodite, 983/12 Aphrodite, 982/11 Demeter: 25 in 19.5 years, 6..12 months
  apart. Hades (friendly, may be jealous) never came. (The counts do not obviously follow religion.md's weights
  `0x0063B01C`, Aphrodite 3, Artemis 2, Athena 2, others 1; 25 draws are few: not checked further.)
- Scenario god attack: Apollo on the map in the Jan 994 dump (event date Dec 995), not using an attack slot; the
  event re-armed to year +12 and came again (Jan 987 dump), re-armed to +20.
- Quest: active from the May 996 dump (date Apr, year +4) to the end; no hero, so nothing else happens.
- Maenads: event state 1 and the monster figure on the map from the Sep 989 dump (date Jul, year +11, lead 1), still
  there at the end (nothing built near it). The Talos event (Jan 980) is after the end of the run.
- Tribute (type 0x1D) every January; games events (0x23..0x25) every year.

## Ours (sim/, 2026-10-29)

### The scenario event engine `sim/scenario/` (track 1G; the API other tracks plug into)
The episode's events, god block and scenario block live in `g.scenario` (a `sim.scenario.model.Scenario`, or
`None`: old saves, maps without an episode). Data: `data/scenario/<map>.json` from
`python3 tools/build_scenario.py` (section "Data file"). It is its own module next to `sim/empire` (which keeps
its queue for the world-map events it creates at run time: gifts out, deliveries, requests, tribute, strikes,
expeditions, city invasions); the core calls only `scenario.new_game(g)` and `scenario.month(g)`.

**When.** `systems.run_day` calls `scenario.month(g)` at our month change (day 0 of a month, after
`empire.day`, i.e. after the empire's invasions), as `month_advance` calls `invasions_month_update` then
`scenario_events_monthly`. The exe runs the pass **before** `month += 1`, so the date a handler sees is the month
that just ended: `scenario.today(g)` = `(year offset from the start, month 0..11)` of that month. An event dated
April year +4 fires at the change to May (oracle: the quest is active in the May dump).

**Handlers: one per event type.**
```python
from sim import scenario

def quest(g, ev):            # called once per monthly pass for every live record of type 4 (not templates)
    if ev["state"] == 0 and not scenario.due(g, ev):
        return
    ...

scenario.register(4, quest, owner="1I heroes")     # at import time of your module
```
Add your module to `PLUGINS` in `sim/scenario/__init__.py` (one line) so it is imported, and so registered,
before the first pass. A type has one handler (a second `register` of the same type raises, unless
`replace=True`). Unregistered types do nothing; the pass logs `event #i type T (name): no handler` once per
record in `g.scenario.log` (not the player's messages). Owners: 23 gift = 1G (`sim/scenario/gift.py`),
27 god invasion = 1H, 4 quest and 26 monster invasion = 1I. Type 2 (invasion) is not dispatched by this pass
(the exe runs it in `invasions_month_update`; `register(2, ...)` handlers run in `scenario.invasions(g)`,
called just before the pass).

**Helpers** (all take `g` first; `ev` is the record dict):
| call | exe | what |
|---|---|---|
| `today(g)` | `year − start`, `month` | (year offset, month) the pass sees (the month that just ended) |
| `due(g, ev, any_flags=False)` | `events_date_check` `0x00471F00` | today is the event's date; False when `flags & 0x20005` (template, done, disabled) unless `any_flags` |
| `months_until_due(g, ev)` | `event_months_until_due` `0x00472000` | `lead + (year − today year)*12 + month − today month` |
| `done(g, ev)` | `flags \|= 4` | mark done (a recurring one re-arms at the end of the pass if `active == 0`) |
| `chain(g, ev, src=-1)` | `event_chain_trigger` `0x0046DE00` | fire `ev["chain"]` (a template) as a new dynamic record, `year` of the template = delay in months; delay 0 → dispatched now |
| `mark_done_and_chain(g, ev)` | `0x00472EC0` | on its date: done + chain |
| `events(g, type_=None)` / `get(g, i)` | `g_events` | the records (index = `ev["id"]`) |
| `alloc(g, rec=None)` | `events_alloc` `0x00467A40` | a new record at run time (reuses a finished dynamic one; max 140), fields from `rec` |
| `gods(g)` | `g_scenario_gods` `0x00FFA450` | the episode's god block (dict below) or None |
| `rng15(g)` | `rng_15` | 0..32767 from the scenario's own RNG (`g.scenario.rng`, seeded from the game seed; ours, so the other systems' random streams don't shift) |
| `post(g, title, body, ev=None, city=None, **vars)` | `FUN_00521A70` | a message by phrase ids (data/messages.json); fills `[amount] [item] [itemshort]` etc. from `vars` |
| `log(g, text)` | – | a line in `g.scenario.log` (CLI `scenario log`) |

**The record** (a dict; exe offsets of `ScenarioEvent`): `id` (+0 index), `type` (+2), `month` (+3, 0..11),
`year` (+0x14 resolved, offset from the start year), `item` (+4), `amount` (+0xC), `city` (+0x1C), `city2`
(+0x58), `groups` (`{"item"|"amount"|"year"|"city"|"city2": [value, a, b, c]}`, as in the file, for re-resolving),
`chain` (+0x24, −1 none), `flags` (+0x28), `lead` (+0x2C), `countdown` (+0x2E), `state` (+0x30), `active`
(+0x32), `parent` (+0x34), `b36 b38 b3a b3c b3e` (i16 at +0x36..+0x3E, type-specific: quest monster slot /
statue selector; monster targets / aggressiveness), `kind` (+0x60 byte: request kind, quest god, status change,
monster "god sent" text), `b61` (`rng % 5 + 4`), `b62` (`rng & 1`), `b63` (parent's city), `src` (+0x64),
`pitem` (+0x66), `pamount` (+0x68), `b70` (+0x70 byte, goods-remapped when flags & 0x4000), `b74` (+0x74, the gift's chosen food), `quest` (+0x7A), `raw` (the 124 file
bytes, hex, before resolution and the goods remap). Handlers may add their own keys (prefix them with the type,
e.g. `quest_hero`). Items are in the new (Poseidon) goods numbering (`sim/empire/model.py GOOD_IDS`: 23 drachmas,
24 troops, 25 food); `scenario.good(ev)` gives our good key.

**Flags** (as the exe): 1 template, 2 recurring, 4 done, 8 chained, 0x40 warn, 0x80 warned, 0x100 dynamic,
0x20000 disabled. The pass: for every record with `flags & 1 == 0`, its type's handler; then
`events_rearm_recurring` (flags 4 and 2, `active == 0`: clear 4, re-resolve, `year = max(1, resolved) + today
year`).

**God block** (`gods(g)`, from the episode, 224 bytes in v5 files): `slots` (24 god ids or −1; 0..3 unfriendly
bringing their monster for 0/1, 4..11 unfriendly, 12..23 friendly), `jealous` (24 bools), `independent_monster`
(text group 190 index), `max_sanctuaries` (+0xDC), `raw` (hex, the rest for 1H).

**CLI**: `scenario` (status and the records), `scenario log`, `scenario on|off` (on: load the map's episode into a
game that has none, dated from the game's start; off: drop it).

### Request list (`request_list_rebuild` 0x00483040, ported 10-30)
The list 0x00916E08 the Overview advisor draws (FUN_005B7760, 8 rows, "more" text 61:0xC4 past 8). Rebuilt after the
monthly dispatch (before the re-arm), at the game start (`episode_start_load`, `city_init_from_map`), after a
request is paid (0x00475AB0 / 0x00475B50, `hermes_help`) and after an army dispatch (`army_dialog_dispatch`):
1. open requests (`request_is_open` 0x004714F0: type 1 or 0x1E, active, not flag 0x40000, state 0 while
   `request_outstanding` 0x0047F630 (announced: countdown <= lead) or state 1), each with its countdown +0x2E
   at the rebuild (the row's months come from this cache), sorted by it (qsort, compare 0x00483020);
2. quests (type 4, `FUN_0046D3E0`) with `FUN_00471560`: active and state 0 or 0xB, in record order.
A quest row: bullet entry 12 + font 3 when the hero is in the city and free (`FUN_005BDDD0`), else entry 18 + font 5;
the god's quest icon (packed group 0x807 + god, SPR_GOD_QUEST_ICON; 0x6837 for gods 12/13), hero name 185:hero at
+0x4C, the quest title (`FUN_004836B0` = `quest_title_text` with [hero_needed]) at +0xA6, god name 157:god at +0x1A7.
Oracle (bugs.md 255, run lo-overview-quest, scenarios/overview-quest.txt): the advisor's quest row and the panel
page's (0x005B6F00, first 3 rows) match ours pixel for pixel. Ours: `scenario.request_list_rebuild(g)` -> `g.request_list` (empire requests and tribute claims from sim/empire,
quests from g.scenario), `scenario.request_rows(g)` for the Overview (sim/live.py advisor 0; viewer/play/advisors.js),
called at the same points (diplomacy.fulfil, hero_ai.dispatch, new game; old saves: built on first use). Fixed on the
way: the Overview listed every not-done request (also unannounced and already paid ones) with its live countdown.
The viewer export (`sim/export.py` snapshot `events`) carries `scenario.export(g)` (the records: id, type, date,
state, active, flags); the exe shows the records to the player only through this list and their messages.

### Data file (`data/scenario/<map>.json`, reproducible)
`python3 tools/build_scenario.py` (`--check` compares) reads the episode straight from the GOG install:
| map | input | episode | sha256 |
|---|---|---|---|
| `sandbox` | `zeus-original/app/Adventures/}Open Play Sandbox.pak` | 1 | `72d0411e9b944e9b9ce2e784ecfd39eae3c163364ccbba7607bfd1213380ca65` |
| `sandbox2` | `zeus-original/app/Adventures/Open Play Sandbox 2/Open Play Sandbox 2.pak` | 1 | `ac0d6a718a418078938238562289f8321f3a961cefa6cd1beaf9824ac65a92d8` |

Keys: `source`, `sha256`, `episode`, `set_version`; `scenario` (the 2032-byte block: `start_year` +0, `funds` +0x20,
`raw`); `gods` (the god block, above); `events` (one record per line: `index`, `type`, `name`, `month` 0..11,
`flags`, `chain`, `lead`, `groups` {item, amount, year, city, city2: [value, a, b, c]}, `b36..b3e`, `kind`,
`quest`, `raw` = the 124 file bytes). Already applied (what the exe does between the file and the game): the
`adventure_read` fix-ups (v < 26: quest byte +0x7A = 0; v < 25: kind-7 requests item 24) and the goods remap of
the item group (`event_goods_remap` `0x0050F3C0`, ported with its list compaction: a range `a < 0, b..c` of
old goods turns into the choice `b|c`) for the types that carry a good (exe table `0x00632700`: 1, 4, 13..16,
21..23, 29, 30, 32, 33). Not applied: the value groups (the sim resolves them at the game start with its RNG).

### Requests and invasions (types 1, 2; 1L-5, 2026-10-31)
**Requests** (`sim/empire/requests.py`; the module docstring has the state machines). Goods, money, food: `event_request`
`0x00470800`; troops (item 24, kinds 1 defend, 2 join an attack, 7 slay a monster): `event_troops_request_update`
`0x0046ED70`. Activation a year before the date (year offset > 0: countdown = lead + 12; year 0: at once, countdown =
month + lead), +0x33 set when the stock already covers it; the announcement when the countdown reaches the lead,
the reminder at 6, overdue below 1 (state 1, the grace months by kind, three rng_7 draws), refused at the end of the
grace (state 5). Paid (`fulfil CITY N`, event_pay_tribute_or_gift `0x0046DAA0`: state 2 early / 3 on time / 4 late,
the verdict 1..4 months later): `request_resolve_attitude` `0x0046FFA0` (tables 0x00632F60..0x006331A0 = ours
diplomacy.REQ_ATT, checked against the exe 10-31; kinds 1/7: 0x0063322C / 0x00633254 = (70, 40), (40, 15), (-30, -10),
(-20, -10), (-80, -40)), history rows, message 0x386 / 0x38C with the outcome's reason (FUN_00476130 early,
00476400 comply, 00476940 late, 004766D0 refuse, 00476BB0 lost: the family + 6 + outcome for goods kinds, + 5 for
troops; kind 6 has none). Chains: +0x24 success, +0x26 refused, +0x52 late, +0x54 lost battle. Troops: the player
sends companies (`fulfil CITY N [SLOTS]`; an empire-queue record "request_forces" carries them, so sim/military's
march, navy and heroes code is reused); they wait at the city until the due month; then refused (never sent), late
(more than 2 months away) or `distant_battle_resolve` `0x00461540` (war.tier tables, war.casualties). Unanswered or
lost: +0x56 = 1 the city is destroyed (FUN_00477AB0, status_events.destroyed: the parent city while in a colony ->
lost 0xB93 / 0xB94), 2 conquered by +0x6F (FUN_0046EAC0). Listed on the Overview (request_list_rebuild: empire and
scenario requests sorted together by countdown) and in the world map's "requests by" rows (`empire.export`). Play mode
(10-31): the message buttons 0x1C0, the world map rows and confirm, the army dialog, the forces' marker
(docs/play/world.md "Requests"; `answer ID dispatch|refuse`).
Troops record end (10-31): state 10 at the due month also clears +0x32 (active); oracle 1L5-troops (Hercules ep 0)
0 differences (tools/oracle_requests.py with ORQ_AID / ORQ_NAME, bugs.md 364). Dispatch / battle not yet compared
with the exe (no foreign-capable company in that episode).
**Tribute claims** (record 0x1E, event_tribute_out 0x004715C0, ours diplomacy.tribute_out_month, 10-31): the
tribute_due phrases and outcomes (bugs.md 355).

**Invasions** (`sim/empire/invasion_events.py`, `invasion_event_month` `0x00476E20`): pending while dated and no more
than lead months old; the announcement on the date (0x2D4, unless a reminder month), reminders at 24 / 12 / 6 / 1
months (once each, +0x57 bits), the "last chance" family (+0xA73) when the city holds the player to tribute (+0xE0 = 2);
at 0 months the army appears (sim/military, quiet), message 0xDD 0x2D9 with the bribe (invasion_bribe_cost
0x00476CF0), done, chain; active until the city's forces are gone. sim/military's alarm (auto-defend, sentiment) sees
them through empire.next_invasion.

**Oracle** (`python3 tools/oracle_requests.py run|check`, run re/oracle/runs/1L5-requests: @Athens through the Ages
episode 0, Mortal, menus as tools/campaign_chain.py, a right click every 15 s with a shot before it, Bribe 7 s
later; dumps every 2 days): the type-1 and type-2 records' state, countdown, active, flags, +0x33 and +0x57 at the
first dump of every month against ours (ours takes the exe's RNG-resolved year and amount): invasion #0 (Knossos,
Jun 800 BC, lead 1): the 1-month warning at the change to July and the army at the change to August, in both, the
same texts (shots m015 "Knossos out to destroy us! ... In one month, because they want more land to call their own,
an army of rival Greeks from Knossos will arrive here", m019 "... is upon us, determined to conquer the city!"),
bribe 525 drachmas in both (Mortal x3); request #13 (Knossos, 100 drachmas, resolved Aug 798 BC, lead 1): active in
the Aug 799 pass, countdown 13, +0x33 = 1 in both. Over the whole run (Jan 800 to Apr 793
BC, 701 dumps, 87 months; records 0, 3, 4, 12, 13 each month): **0 differences**, with the run's own clicks
mirrored (its Decline click hit the refuse button of Knossos' request message in Sep 798 BC: flag 0x40000, refused at
the next pass, state 5, then re-armed; ours `refuse CITY N`, requests.refuse = wm_sub_475B50) and the exe's RNG
draws taken over (the grace months of #4: exe 23 / 7, ours drew 10 / 15; #12's re-armed strength 6, ours 4: the
army's strength decides how long it stays in an empty city). Seen on the way and fixed: the exe clears +0x57 when a
record re-arms (event_resolve_at_start), and a sea invasion's first landing posts 0xDD 0x2DC once (FUN_00461AB0, bit
0x40; subtype +0x04 1 or 2 only). Texts compared by shot: the invasion warnings above, Thermopylai's food reminder
(m089 "You must be very busy, N. What else could be the reason that you have yet to send 6 crates of food ...") =
ours, same month. Not compared: ours never fulfils in the check (the run cannot click the request rows), so the
paid path rests on the unit test.
A city's own invasion (10-31): city_event_invasion 0x00477830 (displeased streak, flags 0x120) /
city_invasion_event_create 0x0047F1C0 (spontaneous, flags 0x110: the "weakness" reason) create a type-2 record dated
that month (lead 2, subtype 1, point (rng & 7) + 1 / + 9 by sea, target 10; the city and strength are set after
month_events_dispatch, so nothing is posted at once) that invasion_event_month runs like a scheduled one; ours
war.invasion_create does the same (sim/empire's own queue only without the scenario module). Before, ours used its
own queue with English messages and its army came one month early (spawned at the start of the due month; the exe at
the due month's pass). Oracle: the exe's #18 (Knossos, Apr 799 BC) against ours: the same record states month by
month (announcement, warning, spawn at the due pass, disembarked 0x40, inactive when its soldiers are gone), one month
earlier in ours: the streak pass (cities_streak_pick 0x0047ECD0, day 7) picks one random city by each game's own RNG
(the displeased streak itself is equal: 50 from Feb 799 in both). `check` lists these rows apart.

### Terrain disasters (types 3, 5, 24, 25) (10-31; earthquake, lava flow, tidal wave ported, `sim/disasters`)
Names: re/names/events.tsv (disaster_*, quake_*, lava_*, tidal_*).
- `event_terrain_disaster` 0x0046D6D0 (3 earthquake, 24 lava flow, 25 tidal wave): on its date (not active,
  events_date_check), the point range from +0x1E alone (when +0x20 < 0) or +0x20..+0x22 (when +0x1E < 0) (ours:
  `groups["city"][1..3]`); `disaster_pick_point` 0x00446AE0 picks random untried slots (rng_15 % n, at most 10000
  retries) whose object is enabled (+0x2C) and of the event's type (vtable +8) and starts it with `disaster_start`
  0x004474E0 (not already started; started +0x18 and the event +0x10 in the table 0x0078C578; message 0xDE at the
  point: title = vtable +0x28 phrase base, announcement base + 2, or base + 1 with [god] = parent +6 when the parent
  record is a god's (FUN_004693D0: type 1 kind 3, type 19 kind 13 / 22) or a god invasion (0x1B); alert vtable +0xC
  (earthquake 1, tidal wave 2, lava 4); music FUN_005A1210(3 / 6), sound by kind). The record: +0x38 = the point,
  active, state 1, DONE. No point found: state 2, never retried. Later passes: once the object is idle or done (table
  state 0 / 7), active 0 and state 2.
- Objects (`disasters_create_objects` 0x004467A0 at the map start, from the terrain at the 8 points 0x00902CBC /
  0x00902CCC): 0x2000000 -> earthquake (`quake_ctor` 0x0056DB50, vtable 0x005E4898), 0x10 -> lava (0x00507370,
  0x005D94D0), 0x100 -> tidal wave (0x004E4640, 0x005D93A0). Methods (vtable offset): +4 kind (quake 3, lava 1, tidal 2),
  +8 type (3 / 24 / 25), +0xC alert, +0x18 current segment, +0x1C ring pre-pass, +0x20 bits a node sets, +0x24 the
  region bit, +0x28 phrase base (0x52E / 0x522 / 0x528, Poseidon's flood 0x1022), +0x2C node, +0x30 crack list,
  +0x34 segments, +0x38 update, +0x3C post step (`disaster_post_step` 0x00447790: random visual calls), +0x40 20,
  +0x44 set state.
- Region (`disaster_region_build` 0x00447470, `disaster_region_add` 0x00447A50, `disaster_rings` 0x00447B70): every
  tile with the region bit 8-connected to the point (neighbour table 0x005D90B8: N NE E SE S SW W NW), one node each
  (ring 1 at once when the tile is within 1 of the play edge, map_near_play_edge d = 1; then the object's +0x2D is set
  and the point itself is not ring 1); the point ring 1; ring r + 1 = nodes with an 8-neighbour of ring r. An edge
  node (fewer than 4 N/E/S/W region neighbours) goes to the crack list, the others to segment ring - 1; each list
  sorted by g_grid_random (`sorted_list_insert` 0x00447E50). Athens (point 1, raw (109, 190)): 145 tiles, 21 rings,
  144 of them edge nodes.
- Run (`terrain_events_update` 0x00446A70, every tick after the cycle step: started objects' vtable +0x38 then +0x3C).
  Earthquake (`quake_update` 0x0056DD40): state 0 -> 2; every 20 calls segment [+0] advances (`disaster_list_advance`
  0x00447230 with (1, 0, 1): every node of the list), +0 ++, then the crack list (its nodes apply only on the ring
  +0 now names); +0 >= rings -> state 7. Node (`quake_node_crack` 0x0056D300): a building on the tile (terrain 8, not
  a ruin 0xA9, not state 6) -> building_destroyed_by_attack; terrain & 0xFACFA710 | 0x300002 (cracked rock; the fault
  and 0x10 bits stay), piece |= 0x80, route / ship grids, images +-2; collapse_debris_spawn(x, y, 1, 0, (rng & 1) + 1,
  0) (dust clouds); figures on the tile die (FUN_004E1AE0: state 2) but types 6, 0xE, 0x22 and the hero 0x45 (own
  handler FUN_004C8EB0). Drawn by FUN_00520580's piece-0x80 branch: SPR_CRACKS by T_CRACKS (0x00636BE0).
  Before the quake the fault tiles are drawn as plain land (oracle m093; the map file stores the editor's cracks).
- Lava (`lava_update` 0x00507560): state 2 as the quake (a ring every 20 calls) then 3, the cooling: table +0x8 + 1
  a call, every 3rd call +0xC + 1; at +0xC = 100 (300 calls) state 7. Its ring pre-pass `lava_seed_rings` 0x005076D0
  (vtable +0x1C, at the map start): no node near the play edge (+0x2D) and no fault (+0x2E): 100 passes over the
  node list, each node with (rng_a & 7) == 0 (one draw per node) becomes ring 1 when all 8 neighbours are nodes of the
  region and exactly one of its N/E/S/W neighbours is ring 1 (a branch grows from the point); the passes stop after
  the one in which such picks reached 10 (a node already ring 1 counts again). With a fault: ring 1 = the fault nodes
  only (`lava_make_node` 0x005073A0 sets +0x2E and ring 1 on a 0x2000000 tile; the pass clears the others' ring 1
  and +0x2D). The lava node takes the tile's owner byte 0x0078C658 and the tile grid 0x00799168 even when set
  (vtable +0x20 = 1; the quake's / tidal wave's 0). Node `lava_node_burn` 0x00506D80: as the quake's without debris:
  terrain & 0xFBCFA710 | 0x1000000, draw |= 0x40, piece &= 0x70, the byte 0x00CB4B08 0. Edge pictures: object vtable
  +0x14 0x00507920 = +0xC (cooling %), +0x10 0x00507950 = the 16-bit colour v | v << 6 | 0xF863 (v = % * 15 / 100).
  Drawing: `FUN_00520820` (tile painter, lava tiles with a node): T_LAVA 0x00634FC0 (48 records) on the inverted
  0x1000000 bits; index 0 (lava all round): the picture SPR_LAVA + rand % 6; else the index goes to the node (+0x24)
  and the next painters give the tile its ground. `ground_tile_draw` 0x00457900 -> `FUN_00507980`: an edge tile =
  its ground, then SPR_LAVA + index with the blitters' AND mask DAT_0078C570 = the object's colour; a centre tile =
  its picture, + 1 per drawn frame while the object is in state 2 / 3 (back to the first at + 5; in state 3 only when
  the byte table 0x006668EC[c3 / 10] is set: all 255 in the file), masked the same; after state 7 unmasked, still.
  Post step (`disaster_post_step` 0x00447790, every tick in states 2..5, all classes): effect figures (type 6, made
  only on screen, FUN_004104D0) on random nodes: lava `FUN_00506F40` / node 0x00506D00 -> FUN_00411920 (subtype 1,
  the orange splashes along the edge in oracle 1L5-dis-europa4-shots), 0x00411BE0 (2), 0x00411DD0; the quake
  `quake_segment_dust` 0x0056D5A0 / 0x0056D7D0 / 0x0056D990; the tidal wave 0x004E4480 -> 0x00412080. Each draws
  the RNG (the exe's state; ours none). Effect handler 0x00410E50, jump table 0x004117E8 (subtype 1: group 0x220B,
  frames 0x11..0x13 by variant). The collapse dust (collapse_debris_spawn) is drawn by play mode (docs/play/walkers.md
  "Effect figures"); the post step's splashes, drops and spray too since 11-01 (the quake's segment call makes
  nothing: its node method 0x0056D2F0 only calls a getter; bugs.md 362, docs/play/walkers.md).
- Tidal wave (`tidal_update` 0x004E4890): 2: a ring every 5 calls (node apply 1) -> 4: 10 calls (+0x8, +0xC) ->
  ring index - 1, then 5, or 7 at once when the event's +0x79 (Poseidon's flood: the water stays, phrase 0x1022) ->
  5: every 5 calls segment [ring index] goes back (apply 0), index - 1, and the crack list (its edge nodes apply on
  every step in state 5) -> index < 0: 7; `tidal_set_state` 0x004E4E40 then resets the table entry (FUN_00447DD0:
  not started, state 0) unless the flood, so a later record can start it again. Pre-pass `tidal_terrain_pass`
  0x004E4B40 (before the first start, +0x18 = 0): a water tile of the region next to a region land tile gets
  terrain 0x2000; then a deep-water node (0x4000000) leaves the region (owner byte 0; its freed node stays in the
  tile grid, so it still counts as a neighbour for the rings), a shallow one on 0x2000 or next to deep water is a
  seed: ring 1 and skipped (+0x21). Node class vtable 0x005D9360, apply `FUN_004E3EC0` (Ghidra DecompAt): skipped
  nodes never; an edge node on its ring only while flooding. Apply 1: terrain & 0xFFCFEFDD | 4 (water; rock 2, 0x20,
  rubble 0x1000, 0x300000 cleared, trees stay); a road 0x40 becomes 0x8000000; the building of the tile (terrain 8,
  not a ruin / state 6) or a 0x4000 tile: building_destroyed_by_attack; figures on it die but types 6 and 0xE.
  Apply 0 on a water tile: & 0xFBFFFFFB (water and deep gone; a sea tile of the region that was not a seed becomes
  land), 0x8000000 -> the road again; boats (0x14 trade ship, 0x19 fishing boat, 0x39 trireme) on it pushed 2
  tiles (ported 10-31, `_push_boats`): towards the middle of the longest arc of water neighbours (FUN_004A1FF0(4), N
  NE E SE S SW W NW, 16 steps round; the exe's scan keeps a run broken by land unless it was the longest so far, so
  water N NE E + SE pushes W; no water: NW); ours clears the boat's path. The tile's farm (building_is_crop, its 3x3
  without water: FUN_004AA600) gets its crop pieces back (piece 2, terrain 8, crop_redraw): pictures; ours draws a
  farm's crops from its state, nothing to port (terrain 8 is our World.occ). No oracle run has a boat on a
  retreating tile; test_tidal_push_boats checks the scan.
- Landslide (type 5, `event_landslide` 0x004732B0; ported 10-31, `sim/disasters/landslide.py`): a cliff face slides
  into the plain below it (elevation, not a figure). At the map start (city_init_from_map -> FUN_00506BC0)
  `landslide_candidates` 0x00505D90 scans the play area row-major for sites of size 5, then 4, 3, 2 until a size has
  any: FUN_00505FF0(tile, size) scores the 4 directions N E S W with `landslide_spread` 0x00506330 (dry run) and keeps
  the best (a tie: rng_15 % ties == 0 takes the later one, so the first tie always does); FUN_00506A20 lists a site
  unless its box overlaps a listed one with a score >= its own (lower ones are dropped; new sites at the head); the 10
  best are kept (0x00F13480, 0x24 each: tile, dir, size, score, box; count 0x00F135E8) and FUN_00506C50 marks their
  plateau tiles with terrain 0x80000000 (saved; recomputed only for old saves). The spread (tile, base elevation e,
  dir, size p): rows r = -p..p along dir, columns across; r <= 0 a half disc (half width trunc(sqrt(p^2 - r^2))) of
  tiles at e that pass FUN_00505F30 (no terrain 0x17370116 on it or its 8 neighbours, none lower than its elevation
  - 1) = the plateau, raised to e + 1; r >= 1 each column walks out to the first higher tile (lower or off-map 0x80000:
  fail; level tiles join the plateau); every column must find one. Then pass after pass, one row further each, each
  column's tile is cut to its level - 1 (FUN_00505F90: none of its neighbours higher than it + 1) or matches it, until
  as many tiles were lowered as raised. Score = trunc((top - e) * balance * 3.0 / depth), x 10 with a building in the
  area, x 3 with a road (the x87 part read from the disassembly at 0x00506908). Applying: FUN_00505B50 per tile (road
  bit off, building_destroyed_by_attack, collapse_debris_spawn(x, y, 1, 1, 1, 0) dust, the elevation).
  The record: on its date DONE; point +0x1C (1..3, 0x00902F4C / 0x00902F58) -> `wm_sub_505bf0` 0x00505BF0 (vtable +0
  of 0x00F13478): every listed site re-scored now (FUN_00505FF0 picks the direction again); among the valid ones the
  nearest to the point (103969 - dx^2 - dy^2) slides (FUN_005061A0); then map_tiles_update_images(box +- 3, 3) twice,
  FUN_0045F7E0 (= FUN_0045EF40, the cliff pass on the whole map) and FUN_0051D760 (FUN_00521520(3)), the first three
  followed by FUN_005061E0 on the box (a building on a cliff tile 0x200 not rubble falls; cliff tiles & 0xFFCFE738).
  A former ramp tile needs 3 cliff passes to end as the exe's plain cliff 0x20400200. Message 0xDE: title 0xC79,
  body 0xC7A, reason 0xC7B (empty), at the site (the exe's "Go to site of event"), no alert; then the chain +0x24.
  Ours: the sites at a new game (scenario.new_game, only for episodes with a type-5 record; tie draws from a Random
  seeded by the game's seed), the cliff passes with tools/terrain_cliffs.py (flags and its FUN_0045FA20 elevation),
  play mode (sim/terrain_view.py `slid`): the box repainted and the cliff pictures of every view recomputed.
  Oracle 1L5-dis-econ2-taenarum-lava / -slide (Open Play Economic 2's Taenarum colony): one site (119, 134) N size 4
  score 243, the 42 marked tiles equal; the Aug 937 BC record slides it (46 tiles +1, 35 -1): the whole map's
  elevation and terrain (but 0x8 / 0x80000000) equal the exe's right after and at Mar 936 BC; the May record (point 2)
  finds no valid site in both. Pictures (-slide2 m276, camera (102, 234), dpr 1.25): 99.0 % of the box within 8, the
  cliffs equal; the ground left of the slide too since 11-01 (bugs.md 366: the repaint rect grown by FUN_0051F210). The dust: play mode (docs/play/walkers.md "Effect figures").
- Ours (`sim/disasters`): the objects are built when the first record of types 3/24/25 is dispatched (the map's terrain
  until then; the lava's seeds from our RNG); two points in one region share the object (the point's tile already
  owned by an object of that kind: disasters_create_objects' use count +0x34); `Game.step` calls `disasters.tick`
  after the day's run, as the exe's tick. Earthquake, lava flow and tidal wave as above (play mode: the cracks; the
  lava's pictures, terrain.json `lava` + the frames' `lava` [slot, state, cooling], play.js drawLava, the AND mask in
  gl.js (alpha >= 65536); flooded tiles are water tiles to the terrain painter). Not ported: the effect figures of
  the post step (bugs.md 362; the collapse dust is drawn, docs/play/walkers.md "Effect figures").
- Oracle (`tools/oracle_quake.py`, run re/oracle/runs/1L5-quake: Athens episode 0 won by force, episode 1 left alone,
  dumps every 10 ticks 19400..21600): the quake starts at the change to Mar 798 BC (ours the same month), 21 rings,
  ring r at tick start + 20 r, 145 tiles: `check` compares the cracked tiles every 10 ticks from the start: 0
  differences; the terrain values of the 145 tiles at the end: equal. Shots m089 (before), m120 (dust), m196 (after).
  Its camera was poked at an odd ROW (281): the exe then draws the tiles of odd x + y 60 px right of those of even
  x + y (bugs.md 363: our crack pictures are the exe's), so its crack lines look broken; the tools poke even rows now.
- Oracle (`tools/oracle_disaster.py`: the adventure's chain of forced wins to the target slot, then left alone; `run
  NAME` dumps every 204 ticks, `run NAME FROM TO EVERY [X,Y]` dense dumps, `check NAME CLASS` ours against the exe at
  the same call count from the object's start, the RNG's point pick forced to the exe's): lava, Zeus and Europa slot 4
  (1L5-dis-europa4, point 1, 578 tiles, 53 rings, near the play edge: no seeds): the lava tiles every 20 ticks from
  the start through the cooling (state 3, +0xC 35 at +1165) to state 7: 0 differences, the 578 terrain values at the
  end equal. Tidal wave: The Odyssey slot 3 (1L5-dis-odyssey3, point 6, 167 tiles, 12 rings) and Open Play Economic
  2's Marathon (1L5-dis-econ2-marathon, one region for points 1..5, 325 tiles, 6 rings): the water tiles every 4
  ticks from the start through the flood, the wait and the retreat: 0 differences in both, terrain values equal at the
  end. Lava drawing (1L5-dis-europa4-shots m060..m064, camera on the point, even row; ours at +300 calls): our lava
  pictures cover 87..89 % of the exe's lava pixels, the masked colour's mean (100, 12, 11) exe, (98, 12, 12) ours;
  the exe's orange splashes (effect figures) are missing in ours.

### Gift (type 23, `sim/scenario/gift.py`)
`event_gift` `0x00474A80` as a scheduled or chained record: on its date (state 0, not active, `flags & 0x20001 == 0`)
it turns active and offers the goods/money from city `city` (`city_exists`, else nothing ever happens: also when
the empire module is off). The offer is `sim/empire/offers.py`'s (`offers.create(g, "gift", ...)`, the exe's
accept / postpone / decline dialog, track 1B; messages title 0x25A, bodies 0x25B.. by room); the record stays
active until that offer is answered or forfeited, then state 10 + done. Before offers.py exists it falls back to
`diplomacy.city_gift` (auto-accepted). Food (item 25) picks one of the city's foods once into `b74`
(`city_pick_food` `0x0042D140`; ours: from the city's sells list, wheat when none; no sandbox gift is food).
The sandbox-2 rewards name city 0, which is the player's own city record in our empire data
(`data/empire/sandbox2.json` id 0 Troezan): the offer reads "Gift of marble from Troezan". I'm not certain the exe
shows the same (not checked in the oracle).

### Timeline check (ours vs oracle, 2026-10-29)
`python3 tools/scenario_events.py oracle-events re/oracle/runs/open-play-events` and
`python3 tools/scenario_events.py ours sandbox 20` (new sandbox, nothing built, seed 1):
| record | oracle (dump after the pass) | ours |
|---|---|---|
| #0 quest, Apr year +3..4 | resolved +4; active from the May 996 BC dump | resolved +4; due at the change to May 996 BC (handler: 1I) |
| #1 Maenads, Jul +11, lead 1 | state 4 from the Feb 1000 dump; state 1 (on the map) in the Sep 989 dump | due at the change to Aug 989 (handler: 1I) |
| #2 Talos, Jan +20..21 | resolved +20 (after the run's end) | resolved +20; due at the change to Feb 980 |
| #3 god invasion, Dec +5..8, recurring | resolved +5: fired Dec 995, re-armed +12 (Jan 994 dump), fired Dec 988, re-armed +20 | resolved +6 (RNG): due at the change to Jan 993 (handler: 1H); with a stand-in handler that marks it done (tests/test_events.py `test_scenario_events`) it re-arms 5..8 years later, same month |
The dates agree where the RNG does not decide; the ranges are the file's. The handlers' own behaviour (states,
warnings, figures) is 1H's and 1I's to compare.

### The rest
| exe | ours |
|---|---|
| Episode events and god block from the `.pak` | `tools/build_scenario.py` → `data/scenario/{sandbox,sandbox2}.json` → `g.scenario` at a new game |
| Monthly dispatch, templates, chains, recurring re-arm | `sim/scenario` (above). `sim/empire/events.py` keeps the empire's own run-time queue |
| Quest (4), monster invasion (26), god invasion (27) | handler slots: 4 and 26 track 1I; 27 `sim/gods/invasion.py` (1H, religion.md "Ours") |
| Gifts (23) as scheduled/chained events | `sim/scenario/gift.py` (below) |
| Requests (1) as scheduled events | sim/empire/requests.py (1L-5): goods, money, food and troops, the attitude results, the consequences (+0x56), paying (`fulfil CITY N [SLOTS]`, the Overview); section "Requests and invasions" |
| Invasions (2) as scheduled events | sim/empire/invasion_events.py (1L-5): warnings, the army on the map (sim/military), bribe; oracle checked (section "Requests and invasions") |
| Wages (8/9), clay pit (12), prices (15/16), favour (17/18), rival army away (20) | sim/empire/city_events.py (1L-5) |
| Earthquake (3) | sim/disasters (1L-5): the point objects, rings, cracks, damage, message, alert; oracle 1L5-quake 0 differences (section "Terrain disasters") |
| Lava flow (24), tidal wave (25) | sim/disasters (1L-5): spread, damage, terrain, lava pictures; oracle 1L5-dis-europa4 / -odyssey3 / -econ2-marathon: 0 differences (section "Terrain disasters"); effect figures not ported (bugs.md 362) |
| Landslide (5) | sim/disasters/landslide.py (1L-5): sites at the map start, the slide, cliff passes, message; oracle 1L5-dis-econ2-taenarum: elevation and terrain equal (section "Terrain disasters") |
| Demand / supply (13, 14, 21, 22), city status (19) | sim/empire/quota_events.py, status_events.py (1L-5) |
| City destroyed by a rival / monster (FUN_00477AB0) | sim/empire/status_events.destroyed: message, history, kind 6; the parent city in a colony episode -> lost 0xB93 / 0xB94 (g.episode_lost, sim/campaign/goals.day); called by an unanswered call for troops (requests.py, +0x56 = 1) |
| Games (0x23..0x25) | yes (`sim/systems/games.py`) |
| Tribute in (0x1D), streak consequences, spontaneous events | yes (`sim/empire`) |
| Jealousy, god visits, blessings, prayers, curses, attacking gods | `sim/gods` (1H, religion.md "Ours"); sanctuary effects use "active" (sacrifices) |
| Scenario god roles (friendly / unfriendly / jealous / max sanctuaries) | `sim/gods/roles.py` (from `scenario.gods(g)`, else data/gods/<map>.json); Mythology menu and limit; the advisor's god lists |
| Monsters, heroes, hero halls | none (wolves only) |

## Open questions
- Does the adventure list show the "2" folders (kind 1) next to the `}` files?
- Load order of the goods remap vs the episode copy (above). `build_scenario.py` applies it (hypothesis).
- (resolved 10-30) `Open Play Sandbox 2`'s scenario block says start year 1750 BC (`data/scenario/sandbox2.json`):
  a new game now starts in its episode's year (`Game.year0` from `scenario.info["start_year"]`, as
  `episode_start_load` copies it to `scenario_start_year` 0x00902928; `Game.start_year` is read by the calendar,
  games.py, the advisors and the world map's city history). Games without an episode and saves from before 10-30
  keep `data/rules.json`'s 1000 BC.
- Which sanctuaries the build menu offers in a scenario (hypothesis: only gods in friendly slots 12..23; the
  placement limit is `sanctuaries_at_limit` `0x004E5F60`, min(+0xDC, 4)).
- Type 0x26 (`0x00481A30`) not traced. `FUN_00483040` = `request_list_rebuild` (10-30, ported:
  `scenario.request_list_rebuild`, section "Request list").
- Why the Maenads event entered state 4 in the first month (heroes-monsters.md).
