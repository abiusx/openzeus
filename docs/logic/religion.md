# Religion: gods, prayers, blessings, wrath

Status: **verified** from the exe unless marked. Addresses refer to GOG `Zeus.exe`.
Companion docs: [monuments.md](monuments.md) (sanctuary construction), [heroes-monsters.md](heroes-monsters.md).
Per-god numbers in machine-readable form: `extracted/model/gods.json`.

## Summary

The city has 14 god records, one per god. The scenario puts each god in one of three roles:
*friendly* (the player may build its sanctuary), *unfriendly* (it attacks through scenario
events and its monster threatens the city), or *absent*. A sanctuary, once **built** (construction
100 %) and **active** (a sacrifice was made in the last ~24 months), gives the god's permanent
effects (Aphrodite lowers house desirability limits, Hephaestus removes fire risk, ...), lets the
god visit the city (walking around and sanctifying buildings), and lets the player **pray**.
Each god has a *prayer counter*: every blessing adds a cost to it, it falls by 1 per month, and
the god only helps while it is at or below a threshold. Besides prayers, once a month one random
god with a built sanctuary is chosen to help **automatically** if the city needs what it gives
(food, wine, cure, ...). Friendly gods whose sanctuary is not built may get **jealous** (every 6..12 months, while
fewer than 4 sanctuaries exist): the god appears with its wooing / jealousy message and roams the roads for 0xF00
units (548 ticks), then vanishes; it does no harm (0x56 / 0x57, corrected 10-30 from the oracle, "Oracle shots").
Gods attack through the scenario's god-invasion event (type 0x1B). An attacking god is a figure that
curses buildings of the types it cares about (they stop working for 1..9 months by difficulty),
destroys or harms things, and leaves after a time budget; other gods (Zeus, Aphrodite, Hera) may
come out to fight it.

## Open play (2026-10-29, track 1A; events.md)
Gods are fully active in open play: the open-play adventures carry a scenario god block like any episode
(`.pak` episode +0x8B98, copied by `episode_start_load` `0x00420390`), and nothing in `gods_month_update`,
`jealousy_update`, `sanctuary_update` or the god-attack event checks for open play. Per open-play adventure
(`python3 tools/scenario_events.py openplay`):
| adventure | unfriendly 0..3 (+4..11) | friendly 12..17 (+18..23), all "may be jealous" in 12..17 | independent monster | god attack events |
|---|---|---|---|---|
| `}Open Play Sandbox` (ours `sandbox`) | Hermes, Hephaestus, Poseidon, Apollo (+ Ares) | Zeus, Hades, Aphrodite, Artemis, Demeter, Athena | Maenads | Poseidon/Hermes/Apollo, year +5..8, recurring |
| `Open Play Sandbox 2` (ours `sandbox2`) | Athena, Hermes | Zeus, Demeter, Hades, Hephaestus, Artemis, Aphrodite (+ Dionysus) | Hector | none |
| `}Open Play Economic` | Apollo, Aphrodite, Artemis | Hades, Demeter, Hephaestus, Athena, Dionysus, Hermes | Medusa | none |
| `Open Play Economic 2` | Poseidon, Ares, Artemis, Hephaestus | Demeter, Hermes, Aphrodite, Athena, Dionysus, Hades | Minotaur | episode 3 |
| `}Open Play Military` | Hermes, Zeus, Athena, Demeter | Ares, Artemis, Hades, Hephaestus, Poseidon, Apollo | Maenads | episodes 1, 2 |
| `Open Play Military 2` | Athena, Demeter, Apollo, Artemis | Ares, Poseidon, Hephaestus, Zeus, Hades | Hector | episode 2 |
Max sanctuaries (+0xDC) is 4 in all of them. Consequences in the `}` sandbox: until 4 sanctuaries stand, a jealous
friendly god comes (and only roams, see above) every 6..12 months (oracle: 25 attacks in 19.5 years on an empty city, events.md "Oracle
check"); the friendly gods with built and active sanctuaries visit, bless, help and answer prayers; Poseidon,
Hermes or Apollo attack through the recurring scenario event. Ours: none of it (events.md "Ours").

## Data

### God record — `g_gods[14]` at `0x00EF5DD8`, 52 (0x34) bytes (sav rank 120)
Record `i` is god id `i` (`init_god_ids` `0x00587280` writes `+0x14 = i`). God order (verified:
`god_sanctuary_type` maps id → sanctuary type 84+id, model rows 84..97 are
`BUILD_LARGE_SANC_<GOD>`, text group 157 lists the same order):
0 Zeus, 1 Poseidon, 2 Demeter, 3 Apollo, 4 Artemis, 5 Ares, 6 **Aphrodite**, 7 Hermes, 8 Athena,
9 Hephaestus, 10 **Dionysus**, 11 Hades, 12 Hera, 13 Atlas. (So record 6 = Aphrodite and record 10
= Dionysus: **verified**.) Poseidon's sanctuary is type 98 (`POSEIDON2`) in a Poseidon game.

| Off | Type | Name | Meaning | Status |
|---|---|---|---|---|
| +0x00 | u8 | unfriendly | 1 if the god is in scenario slots 0..11, 0 if in 12..23, 2 = not in the scenario | verified (`0x00587110`) |
| +0x01 | u8 | listed | 1 for slots 0..3 and 12..17, 0 for 4..11 and 18..23, 2 = absent | verified (`0x00587080`); meaning of "listed" hypothesis |
| +0x04 | i32 | mood | set to 50 at start (`0x004F1A30`), no reader found | verified write; use unknown |
| +0x08 | i32 | sanctuary_building | building index of the sanctuary's main record; written by `0x004E8C40` when a sanctuary is placed (`b - b.house_level`, the multi-part back-offset) | verified |
| +0x0C | i32 | prayer_counter | +cost per blessing, −1 per month (floor 0) | verified |
| +0x10 | i32 | oracle_counter | Zeus/Apollo oracle, same mechanism | verified |
| +0x14 | i32 | god_id | = record index | verified |
| +0x18 | i32 | god_figure | figure index of the god walker (type 0x43); `god_figure_get` `0x004EA490` validates it | verified |
| +0x1C | i32 | timer_1c | set to 0xC0 by god action 0x54 (`0x004EB9A0`); no reader found | verified write |
| +0x20 | u8 | prayer_pending | a prayer was accepted but could not be fulfilled yet | verified |
| +0x21 | u8 | may_be_jealous | scenario flag (scenario+0xC4+slot), only for slots 12..17 | verified |
| +0x24 | i32 | attack_slot | 0..3 on-screen "god attacking" slot, −1 none; reset when the figure dies | verified |
| +0x28 | i32 | gift_amount_1 | remainder of a goods gift (3200 − carried) | verified write; see open questions |
| +0x2C | i32 | gift_amount_2 | second good (Athena: olives) | verified |
| +0x30 | u8 | gift_active | read by `god_gifts_deliver` `0x004E6780`; **no writer found** | verified (static) |
| +0x31 | i8 | pending_months | months left for `prayer_pending` | verified |

Struct names are in `re/structs/religion.tsv`.

### Scenario god block — `0x00FFA450` (sav rank 122, 300 bytes; "scenario_gods")
`+0x00 int[24]` god id per slot (−1 empty), `+0x60 int` independent monster, `+0xC4 u8[24]`
"may be jealous" per slot, `+0xDC u8` max sanctuaries (hypothesis, used with `min(.,4)`).
Slots (text 59:41/59:50, 84:x and the role functions): 0..3 unfriendly gods (0,1 bring their
monster: monster list entries 0,1), 4..11 other unfriendly, 12..17 friendly gods (their good
monsters are monster list entries 3..8), 18..23 other friendly. `scenario_gods_apply`
`0x00586F70` copies roles into the god records at load.

### City-wide variables
| Address | Name | Meaning |
|---|---|---|
| `0x0063A888` (sav 131) | g_god_help_candidate | god chosen this month for automatic help, −1 none |
| city `0x00FE6A58`+0x01 (u8) | jealousy_countdown | months to the next jealousy check |
| `0x00EF60B0[221]` (sav 126) | g_type_curse | per building type: curse countdown in month_advance calls (16 per month) |
| `0x00EF6163` (= `g_type_curse[179]`, an unused type) | g_production_stop | global block: all buildings stop spawning walkers while non-zero |
| `0x00EF618D` | g_god_on_map | set to 1 whenever a god figure is put on the map (UI/sound) |
| `0x00FEAED8`, `0x00FEAEDA` (i16) | trade_block_a/b | set to 0xC0 by Zeus (both), Poseidon (a), Hermes (b) attacks; a blocks the sea trader spawn in `cities_trade_update` (hypothesis: a = sea, b = land) |
| `0x00F2A988` | difficulty | 0..4, index of the curse length table (hypothesis: difficulty) |

### Constant tables (read from the exe)
- `god_help_threshold` `0x004E6040`: Zeus 26, Dionysus 26, Ares 122, Aphrodite/Athena/Hades/Hera 20,
  Hermes/Hephaestus 32, others 14.
- `god_help_cost(flag)` `0x004E60B0` (auto / prayer): Zeus, Dionysus 24/36; Poseidon, Demeter,
  Apollo, Artemis, Atlas 12/18; Ares 120/180; Aphrodite, Athena, Hades, Hera 18/27; Hermes,
  Hephaestus 30/45. (Default 12.)
- Jealousy weights `0x0063B01C[14]` = 0,3,0,0,1,3,2,0,1,0,2,0,5,0 (+1 when used).
- Curse length `0x0063AEAC[id*5+difficulty]` (months): Apollo 1,1,2,2,3; Ares, Aphrodite, Hermes 0;
  all others 1,2,4,6,9. Stored `<< 4` (`god_curse_length` `0x004ED1E0`).
- God fight rank `god_power` `0x004EE710`: Zeus 14, Poseidon 13, Hades 12, Hera 11, Demeter 10,
  Athena 9, Artemis 8, Apollo 7, Atlas 6, Ares 5, Hephaestus 4, Aphrodite 3, Hermes 2, Dionysus 1.
- Visit bless chance `0x004E9290`: Zeus, Aphrodite 10; Poseidon, Hephaestus, Dionysus 25;
  Demeter, Hades, Hera, Atlas 33; Apollo, Artemis, Athena 50; Ares, Hermes 0.
- God → monster (`0x00586C90`), friendly god → good monster (`0x00586D50`), monster → hero
  (`0x00586DB0`): see gods.json and heroes-monsters.md.

### Random numbers
Every draw below is the game's inline step (same as `simulation_tick` step 1):
```
rng_step():
    history[hidx] = d4; hidx += 1; if hidx > 99: hidx = 0        # 0x00F13628 / 0x00F13624
    repeat 31: for r in (e4, e0): b = ((r >> 4) ^ r) & 1; r >>= 1; if b: r |= 0x40000000
    d0 = e4 & 0x7FFF; d8 = e4 & 7; d4 = e4 & 0x7F                # 0x00F137D0/D8/D4
    c4 = e0 & 0x7FFF; c8 = e0 & 0x7F; cc = e0 & 7                # 0x00F137C4/C8/CC
```
(`e4` = `0x00F137E4`, `e0` = `0x00F137E0`.)

## When it runs
- `month_advance` `0x00483C10` runs after each 51-tick cycle; its counter `month_tick`
  `0x0091EC0C` goes 0..15, so 16 calls make a month.
  - `month_tick == 5`: `gods_month_update` `0x004E69A0` (once a month).
  - every call (16×/month): `gods_help_update` `0x004E6B10`, then `curse_timers_decay` `0x004E5EB0`.
- Cycle step 31 (`buildings_spawn_walkers`): each sanctuary type 84..98 → `sanctuary_update`
  `0x004E94C0` (god visits, priests).
- God figures: `walkers_update`, handler of figure type 0x43 at `0x004C5D40` (not a Ghidra
  function; 88-case switch on figure+0x38 at jump table `0x004C854C`).
- Scenario events: type 0x1B god attack (`event_god_attack` `0x00482B10`), 0x1A monster attack
  (`0x00481430`, see heroes-monsters.md), 0x18 military request (Ares), others for requests (Hermes).

## Rules

### "Sanctuary built" vs "sanctuary active"
```
god_sanctuary_building(g)  0x004E8BF0: b = g.sanctuary_building; return b if b and buildings[b].type
                                       == god_sanctuary_type(g) and buildings[b].state != 0 else 0
god_sanctuary_built(g)     0x004E65F0 (= god_sanctuary_complete 0x004EA710): b != 0 and construction_percent(b) > 99
                           (construction_percent = FUN_0053ECA0(b,0), see monuments.md)
god_sanctuary_active(g)    0x004E9440 (housing.tsv: god_sanctuary_finished): b != 0 and buildings[b].byte[0x32] != 0
```
**Correction to docs/re/structs.md / housing-evolution.md:** Building+0x32 on a sanctuary is not
a "finished" flag but the **months of activity left after a sacrifice**: a completed sacrifice
sets it to 24 (`0x004EA1A0`), it falls by 1 each month (`0x004E97D0`, when `month_tick == 0`),
priests look for a new sacrifice when it is below 20, and `0x004E9750` sets it to 22 when it is
above 24 and Building+0x64 (byte) is set. All permanent god effects (house_param, fire risk,
Hermes, Atlas, Hera, Athena...) test `god_sanctuary_active`, i.e. they stop if sacrifices stop.
(verified; the same byte is used as a production counter by other building types.)

### Monthly god update `gods_month_update` 0x004E69A0 (month_tick 5)
```
for g in gods: god_month_tick(g)                         # 0x004E6160
jealousy_update()                                         # 0x004F0B50
cands = [scenario.slot[s] for s in 12..23 if scenario.slot[s] >= 0 and god_sanctuary_built(god)]
if cands:
    rng_step(); g = cands[d4 % len(cands)]
    if g.prayer_counter <= god_help_threshold(g) and not god_figure_busy(g):
        g_god_help_candidate = g.id; return
g_god_help_candidate = -1
```
`god_figure_busy` `0x004E75E0`: the god figure exists and its action is in 0x0F..0x35.

`god_month_tick(g)` 0x004E6160:
```
g.prayer_counter = max(0, g.prayer_counter - 1)
g.oracle_counter = max(0, g.oracle_counter - 1)
if not g.prayer_pending: g.pending_months = 0
else:
    if g.pending_months > 2: g.pending_months = 1
    g.pending_months -= 1
    if g.pending_months < 1: g.prayer_pending = 0
if god_sanctuary_built(g):   # passive monthly effects
    Zeus:     for each of the 22 world cities with byte+0 != 0: if +0x164 < 100: +0x164 += 1   # 0x004E6230
    Poseidon: if sanctuary flag (+0xC4 & 8) clear and no city monster: spawn monster 1 (Kraken),
              action 0x15/0x0F                                                             # 0x004E6260
    Hades:    same with monster 2 (Cerberus), action 0x0E/0x0F                              # 0x004E62D0
    Athena:   if an invasion is on (FUN_004AC7C0(0)): put Athena on the map (or send her) to
              fight it (action 10 -> 0x51)                                                  # 0x004E6340
    Apollo:   if a monster is near the sanctuary (FUN_004F1B50): Apollo goes to fight it   # 0x004E6440
```

### Help and prayers
`gods_help_update` 0x004E6B10, every `month_advance` call:
```
if g_god_help_candidate != -1 and god_sanctuary_built(cand): god_help(cand, prayed=0, force=0)
for g in gods (0..13):
    god_gifts_deliver(g)                        # 0x004E6780, no-op while gift_active == 0
    if g.prayer_pending: god_help(g, prayed=1, force=1)
```
`god_help(g, prayed, force)` 0x004E6630: `if force or god_can_help(g)` → per-god function below.
`god_can_help` 0x004E6610: `g.prayer_counter <= god_help_threshold(g) and not god_figure_busy(g)`.

Pray button (sanctuary window, `0x00408DA0`):
```
if building+0x32 == 0: result = 3 (refused: "Sanctuary needs sacrifice")
else:
    ok = god_can_help(g); result = 2 if ok else 3
    god_help(g, prayed=1, force=0)
    if result == 2 and g.prayer_pending: result = 1      # "heard, will do later"
```
Texts: result 2 → 132:24+id (granted), 1 → 132:38+id, 3 → 132:52+id.

Common shape of every per-god function (`prayed` = flag, verified for all 14):
```
if not prayed and not <need>: return
if god_figure_busy(g): -> queue
if <target/space not available>: -> queue
put the god figure on the map at its sanctuary (god_figure_spawn 0x004E8A30) if absent;
if that fails: -> queue (only when prayed)
figure.action = <blessing action>
g.prayer_counter += god_help_cost(g, prayed)
god_message(g, tile)          # 0x00480590
g.prayer_pending = 0
if g_god_help_candidate == g.id: g_god_help_candidate = -1
queue (only when prayed and not already pending):
    g.prayer_counter += god_help_cost(g, prayed); g.prayer_pending = 1; g.pending_months = 1
```
(Zeus queues with `pending_months = 2`. Poseidon does not charge again when re-trying a pending
prayer.) So a queued prayer is retried 16 times a month until the next monthly update clears it.

Per-god need and effect (all verified unless marked; resource ids: 1 urchin, 2 fish, 3 meat,
5 carrots, 6 onions, 7 wheat, 13 olives, 20 oil, 21 wine; `free(r)` = `FUN_00488A60(r)`, the
storage space for r, summed over the city's food list `0x010DFE40[0x010DFE3C]`):

| God | fn | Need (auto only) | Precondition | Figure action / effect |
|---|---|---|---|---|
| Zeus | 0x004E6B80 | — (never automatic) | an enemy army (formations 0x00DB7B40, not the city's) with strength > 0: picks the largest `count × (1, or 2 for type 0xC/0x29, 3 for 0xD/0x2A)` | 0x0F: Zeus strikes the army |
| Poseidon | 0x004E6DE0 | `FUN_00569310` (food need) | free(1)+free(2) ≥ 3200 | 0x15 → `0x004C4910`: emptiest granary for urchin or fish; gift = min(free,3200); ceil(gift/400) carriers (fig 0x2F) |
| Demeter | 0x004E6FF0 | food need | free(7)+free(5)+free(6) ≥ 3200 | 0x17 → `0x004C4F20`: same with wheat/carrot/onion |
| Apollo | 0x004E71F0 | a house with b+0x05 and b+0x85 (plague) | prayer with city+0x18 < 100 skips the house test; a target tile (`FUN_005477A0`) | 0x19: cures |
| Artemis | 0x004E73F0 | food need | free(3) ≥ 2400 | 0x1B (→ 0x20 `0x004C5420`): meat |
| Ares | 0x004E7610 | an event of item troops (+4 = 0x18) in state 6 (forces away) with `event_months_until_due` ≥ 2 whose battle is close: \|sent − E\| · 100 / max(sent, E) < 20 (sent = `event_sent_forces_strength`, no heroes; E = the target city's army); corrected 10-30 (was "gap ≥ 20 %") | same event (prayer: any such event) | 0x22 (written directly, no sound): the vanish group, then hidden (+0x65) in 0x23; event flag 0x1000 (distant_battle_resolve: E × 50/100 for a player expedition; the enemy's loss on the full E); after that battle `FUN_004C5780`: action 10 (still hidden) → 0x14 (hidden cleared, walk to the sanctuary's road) → 0x0B. Also called by `event_pay_tribute_or_gift` (troops sent, e.g. the army dialog's dispatch) when Ares is the help candidate or has a pending prayer |
| Aphrodite | 0x004E77E0 | city+0x38 ≥ city+0x34 / 2 (vacancy, hypothesis) | a tile (`FUN_00547890`) | 0x19: fills houses |
| Hermes | 0x004E7980 | an open request (`FUN_004714f0`: type 1 / 0x1E, active, state 0 and announced or state 1; not troops; ≤ 20 collected) | — | exactly one: state 3 (on time), countdown rng % 4 + 1, nothing taken, help message (`FUN_00483040` only rebuilds the request list); several: message 0xE0 (title 0x734, body 0xB8E "Hermes will fulfill an outstanding request ... at no cost to you!") and the prayer goes pending (cost, 1 month); while Hermes is the help candidate or pending, the player's next request (type 1, kind ≠ 9) needs no stock and costs nothing (`hermes_request_auto` 0x004E7C00 in `FUN_004713E0`, `FUN_00471D50`, `event_pay_tribute_or_gift`; then `hermes_pending_clear` 0x004E7C30) |
| Athena | 0x004E7C50 | city+0x18A4 + city+0x1934 < 400 and a house of type 7..14 | free(20) and free(13) ≥ 1600 | 0x25 → `0x004C4D50`: 8 grower figures (type 5) |
| Hephaestus | 0x004E7E70 | strongest enemy army stronger than the city (`FUN_005687A0`) | no city monster | creates monster 8 (Talos), action 0x14/0x10 |
| Dionysus | 0x004E8010 | city+0x18A8 + city+0x1938 < 400 and a house needing wine (house_param col 11) | free(21) ≥ 1600 | 0x2A → `0x004C51E0`: wine |
| Hades | 0x004E81A0 | treasury (city+0x0C) < 1; if a friendly active world city with relation ≥ 50 exists, a 50 % draw (`rng_step`, `e4 & 1` must be 0) | city treasury flag `0x00FEAEDE` != 0 | 0x2C → `0x004C4BC0`: 8 miners (fig 0x3E) dig silver |
| Hera | 0x004E8430 | agora low on goods | — | restocks agoras |
| Atlas | 0x004E8710 | a monument under construction missing materials (Atlas's own sanctuary excluded) | — | supplies it |

### What each god's help does (audit 11-01; the user's reference)
Every god helps in two ways: **automatically** (once a month the help candidate, drawn by gods_month_update, helps
when its sanctuary is built and the city has the god's need) and **by prayer** (the Pray button of a staffed
sanctuary that has had a sacrifice: answered now, or queued for later; each help adds to the god's prayer counter,
and the god will not help again until it falls back under the god's threshold). A help is announced by the god's
help message and an alert at the place it happens. Amounts are game units (100 = one load). "Checked" says how ours
was compared with the exe: **decompile** = ported line by line from the function named, with a unit test; no help
has been compared with an oracle run (none of the oracle runs makes a god help).

| God | When it helps by itself | What it does | Ours | Checked |
|---|---|---|---|---|
| Zeus | never (prayer only); needs an enemy army on the map | appears beside the strongest invading army's biggest company, stops the army, throws 5 bolts, then that company's leader falls and every enemy soldier and warship on the map dies | ported (gifts.py zeus) | decompile 0x004E6B80, test_gods_help_zeus_aphrodite |
| Poseidon | the city is short of food (no food in the granaries, or under half the people fed) and there is room for 3200 urchins / fish | walks to the granary with the most room for urchins or fish and puts min(room, 3200) there (carriers behind him); the rest of the 3200 goes into any storage the next day | ported; the rest of the gift since 11-01 | decompile 0x004E6DE0 / 0x004C4910 / 0x004E6780 |
| Demeter | the same food shortage, room for 3200 wheat / carrots / onions | the same with wheat, carrots or onions | ported; rest of the gift 11-01 | decompile 0x004E6FF0 / 0x004C4F20 |
| Apollo | a house has the plague (a prayer works whenever city health is under 100) | walks to a spot of his precinct, waits 100 ticks, cures the city: every infection cleared, the plague walkers gone, health + 50 | ported | decompile 0x004E71F0 / 0x004C5690, test_gods_help_apollo_dionysus |
| Artemis | the food shortage, room for 2400 meat | exe: hunts the nearest wild animal, shoots it, carriers take min(room, 2400) meat to the granary with the most room (rest the next day); no animal: the 2400 go straight into storage | **partial**: ours walks the meat from her sanctuary to that granary (no hunt); amount 2400 and the rest fixed 11-01 | decompile 0x004E73F0 / 0x004C5420; the hunt (actions 0x1B..0x21) read, not ported |
| Ares | an army of ours abroad whose battle is close (strengths within 20 %) | vanishes and joins that expedition: the enemy counts at half strength in its battle; he comes home after it | ported (aid.py) | decompile 0x004E7610, test_gods_help_ares_hermes |
| Aphrodite | at least half the city's housing is empty | walks to her precinct, 100 ticks, then every house with room gets up to 4 new people | ported | decompile 0x004E77E0 / 0x004C56F0, test_gods_help_zeus_aphrodite |
| Hermes | an open request from a world city (not troops) | one request: fulfilled at no cost; several: the next request you answer costs nothing | ported (aid.py) | decompile 0x004E7980 / 0x004E7C00, test_gods_help_ares_hermes |
| Athena | olives + olive oil in the city under 400 and a house of type 7+; room for 1600 of each | 8 growers tend her grove, then she brings 1600 olives and 1600 oil to the storehouse with the most room (what does not fit goes into storage the next day) | ported; rest of the gift 11-01 | decompile 0x004E7C50 / 0x004C4D50, test_gods_help_hades_athena |
| Hephaestus | an invading army at least as strong as the city's soldiers | sends his guardian Talos (if not already on the map) | ported (via sim/heroes guardian) | decompile 0x004E7E70 |
| Dionysus | wine in the city under 400 and a house that wants wine; room for 1600 | brings min(room, 1600) wine to the storehouse with the most room (satyrs carry it; ours does not draw them); the rest into storage the next day | ported; rest 11-01 | decompile 0x004E8010 / 0x004C51E0, test_gods_help_apollo_dionysus |
| Hades | the treasury is empty (if a friendly city could help, only half the time); needs a palace | 8 miners dig silver at his precinct, then he walks to the palace: treasury + 3200 | ported | decompile 0x004E81A0 / 0x004C4BC0, test_gods_help_hades_athena |
| Hera | at least half the agora vendors are short of their good (their agora wants more and their buyer found no supply) | walks to the nearest agora, 100 ticks, then every staffed vendor's good + 800 (fewer with more vendors: 600 for 4, 500, 400, 300, 200, 100 for 16+; food as wheat; at most 1100 food / 800 other) | ported 11-01 (gifts.py hera); the walker window's phrase for her help is not mapped | decompile 0x004E8430 / 0x004C58A0 / 0x004C59A0, test_gods_help_hera_gifts |
| Atlas (Poseidon) | a monument under construction lacks materials | supplies it | not ported (Poseidon, stage 3): prayers queue and lapse | read 0x004E8710 |

Sanctuary effects that are not "help" (the permanent ones while the sanctuary is active, the goods a sanctuary
makes available, the sanctuary troops of Artemis and Ares) are in "Permanent effects of an active sanctuary" above
and docs/logic/military.md (companies 31..34).

### Oracle `oracle_consult` 0x004EA630 (Zeus and Apollo only)
Table `{god, cost_auto, cost_consult, threshold}` = `{0,10,18,14}`, `{3,8,16,12}`.
Available iff `oracle_counter < threshold`. Consulting adds `cost_consult`; an automatic oracle
(`FUN_0047F6C0` returned non-zero) adds `cost_auto`. Button 1 of the sanctuary window.
Read 10-29 (ours: `sim/gods/oracle.py`, command `oracle GOD`, the window's button): the button (wm_sub_408EB0)
checks availability, adds cost_consult, then `FUN_0047F6C0(1)`: among the events `FUN_0047F4C0` accepts (not flags
0x40 / 0x01 / 0x20000; type 0x13 with kind (+0x60) 2 / 3 / 0xD / 0x16 and type 0x1B with 0 < m < 13, m =
(year − start − ev year)·12 − month + ev month as written; type 0x1A in state 4 with lead < months until due <= lead
+ 12; type 1 by fields not mapped in ours), one at `rng_7 % count` gets flag 0x40 and `month_events_dispatch` runs
(its handler posts the oracle prediction); no message → pick again; none → PHRASE_oracle_nothing (title 0xB88,
announcement 0xB89, reason 0xB8A). The prayer result (sanctuary_pray_click 0x00408DA0, DAT_00FFA184, reset when a
window opens) is drawn in the window at (L+20, T+0x127): 132:god+0x18 granted, +0x26 heard (11C), +0x34 refused
(11LTYEL); Consult Oracle 132:109, or 132:110 without hover when unavailable.

### Permanent effects of an active sanctuary
Every caller of `god_sanctuary_active` 0x004E9440 (checked 10-30, the god from the `mov ecx, 0x00EF5DD8 + 52 * god`
before the call). Ours: what sim/ does (bugs.md 291, 296).
| God | Where | Rule | Ours |
|---|---|---|---|
| Aphrodite | `house_param` 0x00433D80 | cols 0 and 1 (devolve/evolve desirability) − 10 | housing.des_gate (10-30) |
| Aphrodite | `send_emigrants` 0x00486AB0 | no people leave | population.py |
| Dionysus | `house_param` | col 14 (crime increment) → 0 | (the crime update below replaces it) |
| Dionysus | `houses_crime_update` 0x00566F20 | per house: `crime -= 20` instead of `+= col14 + (40 − city+0x10)/2`, then clamp to [col15, 100] | risk.crime |
| Hephaestus | `model_building_value` 0x00433D50 | building model col 6 (fire risk) → 0: non-houses reset to 0, houses stay (buildings.md §8.2) | risk.fire_inc (10-30) |
| Hera | `population_births_deaths` 0x00566D40 | birth points + 3 (rate = points% of city+0x24) | health.year_start |
| Apollo | `0x00565D40` | +20 to all four values (hypothesis: games victory chances) | games.py |
| Athena | `figure_type_value` 0x004E1B20 | figure types 0xB rabble/archer, 0xC hoplite, 0xD horseman, 0x45 hero: col 4 (missile armour) + 4 before the cap at 19; col 0x12 too, but nothing reads col 0x12 | military/units.col (10-30) |
| Hermes | `figure_type_value` | col 8 (speed) × 133/100 for figure types 4 cart, 9 storehouseman, 0x1C ox cart, 0x24 deliveryman (unless led by a 0x41 priest / 0x3E miner); × 150/100 for 0x13 caravan, 0x14 trade ship, 0x15 donkey | walkers.speed (10-30; ours: role cart, trader, ship, donkey) |
| Hermes | `cities_trade_update` 0x005B9EE0 | trader countdown (4 land, 30 sea cycles) × 66/100 | trade.update (10-30) |
| Atlas | `artisans_guild_max_artisans` 0x0048CAF0 | 2 instead of 1 (0 while the guild's type is cursed) | monuments.update (10-30) |
| Atlas | `buildings_spawn_walkers` | marble (49) and black marble (213) quarry period × 66/100 | economy.gather_day |
| Atlas | `figure_miner` 0x004C1310 | the stonecutter's work at the rock (0x31, 0xD5) 0x660 → 0x435 ticks | walkers.reach_target (10-30) |
| Poseidon | `figure_fishing_boat` 0x004B5F10 | the fishing time (0x198..0x7F8 by staffing) × 66/100 | walkers.boat (10-30) |
| Apollo | `FUN_004D4910` | a god figure of Apollo with unit class 9: the only god figure_tile_contact lets meet a monster (heroes-monsters.md "Gods and monsters") | sim/military/contact.py apollo_fights (11-03) |
| Athena, Dionysus, Hephaestus, Hera | `god_resource_available` 0x005BA890 (sanctuary present, b+0xDA == 0; not "active") | olives/oil, grapes/wine, bronze, oranges count as available (goods lists, the growers' lodge halted test) | allowed.god_provides (11-01): goods_list (storage windows, trade, advisor, Distribution page) and labor.halted (growers' lodge: each crop out when shut down or neither makeable nor god-given) |
| Zeus | monthly | world cities' relation +1 | gods/month.py |
| Poseidon, Hades, Ares | monthly / visit | Kraken, Cerberus, Dragon as city monsters | gods/month.py, sim/heroes |
| all | `god_walk_interrupt`, `god_encounter_check`, `god_fight_wins`, `monster_god_engages`, `FUN_004F0130` | visits, fights | sim/gods |

### God visits `sanctuary_update` 0x004E94C0 (cycle step 31, per sanctuary)
```
if main building and construction_percent >= 100:
    if b+0xC4 & 8: b+0xC8 = max(0, b+0xC8 - 1); if b+0xC8 < 1: clear bit 8
    if byte(b+0x64) != 0 and b+0x32 > 24: b+0x32 = 22
    if b+0x40 (workers) != 0:
        priests_update(b)                         # 0x004E97D0 (sacrifices)
        if god figure of this sanctuary is on the map: b+0x33 = 16; return
        if b+0x32 == 0: b+0x33 = 1; return        # inactive: no visits
        b+0x33 = min(b+0x33, 16); if b+0x33: b+0x33 -= 1; return
        spawn the god (Hermes at the land entry 0x00902CB4/6, others at a free tile around the
        sanctuary from FUN_004A39D0(x,y,20,20)); figure+0x42 = 6528 (Zeus) or 3840 (visit length),
        action 10 -> 8 (wander)
        Ares: also creates monster 7 (Dragon), action 0x12, if no city monster and +0xC4&8 clear
```
While wandering (action 9) the god calls `god_visit_bless_try` `0x004C3CD0`:
```
rng_step(); dir = (d0 & 7)        # start direction (signed % 8)
for 8 directions: b = building at the neighbour tile (main record), not already sanctified (b+0xDB == 0)
    if god_building_affected(god, b) (0x004E9310: g_type_curse[type] == 0, b+0x4A == 0 and the
       god's type list below):
        chance = god_visit_bless_chance(god) / building_size(type)      # 0x005F6368[type*32]
        rng_step(); if d0 % 100 < chance: b+0xDB = 1 (sanctified), action 0x0C; stop
```
Apollo and Athena (and Hera during an invasion) leave the walk to fight monsters/enemies
(`0x004EBA10`).

God building type lists (`0x004E8F20` … `0x004E9260`, used for both sanctification and curses):
Poseidon 44, 45, 133; Demeter 31, 32, 33; Apollo 79, 80, 81, 82, 202, 203, 205, 207; Artemis 46;
Ares none; Aphrodite houses (2..14) with residents and b+0x85 == 0; Hermes none; Athena 41, 54;
Hephaestus 55, 135; Dionysus 53; Hades 48, 50, 122; Hera 214, 216; Atlas 51, 211; Zeus all of the
above in this order. (Type names: extracted/model buildings.)

### Jealousy `jealousy_update` 0x004F0B50 (monthly)
```
c = city.jealousy_countdown (u8)
if c < 13: c -= 1 (wraps 0 -> 255)
else: rng_step(); c = d0 % 7 + 6
if c == 0 and count(gods with sanctuary_building > 0) <= 3:
    w[g] = jealousy_weight[g] + 1 for g with listed == 1, unfriendly == 0, no sanctuary,
           may_be_jealous   (god_can_be_jealous 0x004E6010); else 0
    if sum(w) > 0:
        rng_step(); r = d4 % sum(w) + 1; pick the first g with r -= w[g] <= 0
        if god_attack_slot_assign(g):           # 0x00587390 (max 4 attacking gods on screen)
            god_attack_start(g)                 # 0x004F0EA0
            rng_step(); c = d0 % 7 + 6
```
`god_attack_start`: target = position of the last composite building (or the map centre),
moved to a valid land tile (Poseidon: water tile); god figure created there, action 10 → 0x56,
message (`0x004F1110`: text varies with 0, 1–2, ≥ 3 sanctuaries built).

### Scenario god attack `event_god_attack` 0x00482B10 (event type 0x1B)
```
if the date has not come: only a warning message (once, flag 0x80)
else: arrival tile = god_attack_arrival(god) (0x004EBBD0): Zeus, Aphrodite, Athena, Hades, Hera
      -> the palace, else a type-21 or type-5 building; Poseidon -> sea entry; others -> land
      entry 0x00902CB4/6.  Hermes spawns at the land entry and walks to the arrival tile.
      god figure created, action 10 -> 0x36, figure+0x120 = 3
defenders (each only if its sanctuary is built): Zeus vs any god; Aphrodite vs Ares, Hephaestus,
Hermes, Dionysus; Hera vs Zeus. The defender is put on the map (or reused if
god_can_fight 0x004EE270) and sent at the attacker (action 0x4A/0x4B).
```

### Attacking god behaviour (figure type 0x43)
On arrival (action 0x36, `god_attack_init` `0x004ECA10`) each god sets its budgets
(figure fields, all verified):

| God | init | +0x120 A (0x3A) | +0x132 B (0x38 curse) | +0x12C C (0x43) | +0x13C kind | extra |
|---|---|---|---|---|---|---|
| Zeus | 0x004EC090 | 3 | 10 | 10 | 10 | trade a+b blocked 0xC0; goes to the palace |
| Poseidon | 0x004EC180 | 3 | 10 | 0 | 1 | trade a blocked |
| Demeter | 0x004EC310 | 3 | 10 | 10 | 0 | kills every second sheep/goat (fig 0x31/0x32) |
| Apollo | 0x004EC4A0 | 2 | 10 | 7 | 6 | target palace or highest house |
| Artemis | 0x004EC410 | 2 | 10 | 10 | 0 | `FUN_00504650(4,…)` at the land entry |
| Ares | 0x004EC560 | 4 | 0 | 10 | 5 | `FUN_00504650(10,…)` |
| Aphrodite | 0x004EC650 | 0 | 0 | 0 | – | action 0x3F/0x40 |
| Hermes | 0x004EC6A0 | 0 | 0 | 10 | 19 | trade b blocked; action 0x45 |
| Athena | 0x004EC3B0 | 3 | 10 | 7 | 3 | |
| Hephaestus | 0x004EC5F0 | 2 | 10 | 5 | 2 | |
| Dionysus | 0x004EC710 | 0 | 0 | 0 | – | 3 monster figures (0x44) beside him; 0x3F/0x40 |
| Hades | 0x004EC240 | 3 | 10 | 10 | 4 | target palace or highest house |
| Hera | 0x004EC850 | 3 | 10 | 10 | 9 | kills every second cattle (0x4C); world message |
| Atlas | 0x004EC950 | 2 | 10 | 10 | 2 | target palace or highest house |

All: figure+0x108 = 0x60 (time budget in month_advance calls = 6 months), +0x104 = month_tick.
The handler decrements +0x108 whenever month_tick changed since +0x104.

Main loop `god_attack_wander` 0x004ECB70 (action 0x37):
```
if t108 < 1 or (A < 1 and B < 1 and C < 1): leave (action 0x49 -> 0x0B)
clamp A, B, C to 0 if outside 0..100
if A > 0: action 0x3A/0x3B ; elif B > 0: action 0x38/0x39 ; elif C > 0: action 0x43/0x44
elif not (flags & 0x1000):
    rng_step(); if d0 % 100 < 21: kind = 10; action 0x43/0x44 (leave if no target)
    elif figure+0x39 == 0 or > 14: flags |= 0x1000; roam (FUN_004F1C90)
else keep walking (action 0x37)
```
Curse (`god_curse_building` 0x004ED2A0, action 0x39 at the attack frame `0x0063A8FC[god]`):
`B -= 1; g_type_curse[type] = curse_months(god) << 4`. `curse_timers_decay` 0x004E5EB0 lowers
every non-zero entry by 1 per month_advance call. A cursed type: no walkers/production in
`buildings_spawn_walkers`, no artisans (Atlas), no sanctification. Special hits
`0x004EDFC0`: Zeus on the palace → `FUN_004928C0`; Hera → `0x004EDE80`; Hades → `0x004EDF50` and
`g_production_stop = 4`; Athena → walls (130) and towers (132) cursed; Apollo → `FUN_004481B0(0)`.

God fights (`god_fight_wins` 0x004EE5B0): Aphrodite (active sanctuary) beats Ares, Hephaestus,
Hermes, Dionysus; Hera (active) beats Zeus; else the higher `god_power` wins.

## Ours: `sim/gods` (track 1H, 2026-10-29)
An encapsulated, switchable module (`gods on|off`; off = sanctuary effects follow "complete", nothing comes, every
sanctuary may be built). Core hooks: `systems.run_day` → `gods.day` (after `services.spawn`), `walkers.act` for roles
`god` / `priest`, `export.walker_anim` → `gods.look`, `Game.command` → `gods.command`, `Game.build` → `gods.can_build`,
`gods.cursed(g, b)` in `economy.produce` / `services.spawn`, `health.sanctuary_done` → `gods.active`, a blessed
building's next cart ×4 (crops ×1.5) in `economy.send_cart`. Scenario hook: `sim.gods.invasion` in `sim/scenario`'s
PLUGINS (type 27). Data: `data/gods.json` (exe tables) and `data/gods/<map>.json` (the adventure's god block, used
when the game has no `g.scenario`; old saves) from `python3 tools/build_gods.py`; play mode `data/play/gods.json`
(`python3 tools/play_gods.py`) and the god atlases (`python3 tools/play_atlas.py Zeus_Zeus ... Poseidon_Atlas`).
CLI: `gods`, `gods log`, `pray GOD`, `jealous [N]`, `godattack GOD [scenario]`, `godvisit GOD`.

| exe | ours |
|---|---|
| roles `scenario_gods_apply` 0x00586F70 | `roles.py` from `scenario.gods(g)` or data/gods/<map>.json |
| Mythology menu (FUN_00402B80: +0xDC != 0 and god_can_be_jealous), limit `sanctuaries_at_limit` | `menu`, `can_build`; play mode hides the other sanctuaries (frame `sanct`, build.js) |
| activity byte (u8, 0 wraps to 255), priests (count 3/2/1, full staff, search: sheep/goat/bull, cow, then 400 food from the first granary/storehouse; delete on failure), sacrifice = 24 | `sanct.py`, `priests.py`; ours: every arriving priest sacrifices (the exe waits for all priests sent); a led cow / bull follows the priest step by step |
| visits: road tile within 20 of the sanctuary (Hermes from the entry), roam 0xF00/speed 7 = 548 ticks, a blessing restarts the clock, then walk back and vanish; `god_visit_bless_try` | `figures.visit_start`, `_visit_act`, `bless_try`; blessing = `b.misc["blessed"]` (x4 cart) |
| monthly: counters, pending prayers, help candidate, Zeus +1 attitude, jealousy | `month.py` |
| help: `gods_help_update` / `god_help` / prayers (queue, pending months) | `help.py`; effects ported for Poseidon, Demeter, Artemis (the god walks to the granary with the most room, min(room, 3200)); `gifts.py`: Zeus (prayer only: the strongest army's largest formation; vanish at the sanctuary, appear by it via FUN_004C43C0(…, 10), the army halted (FUN_004C4090), 5 bolts, then every enemy soldier and ship falls), Aphrodite (need: room >= capacity / 2; walks to a spot of her precinct, 100 ticks, each house with room + min(room, 4), FUN_004C56F0), Apollo (an infected house, or a prayer with health < 100: the same walk, then city_heal_plague: infections cleared, plague walkers gone, health + 50), Hades (8 miners dig 408 ticks at his precinct, then he walks to the palace: treasury + 3200), Athena (8 growers tend her grove, then 1600 olives + 1600 oil to the storehouse with the most room), Dionysus (1600 wine to the storehouse with the most room; his satyr carriers not drawn), Hephaestus (Talos through sim/heroes `guardian`); `aid.py`: Ares (joins an expedition: hidden until its battle, the enemy at 50 %; sim/empire war.attack / war.battle call `gods.expedition_sent` / `expedition_battle`), Hermes (fulfils a request; diplomacy.fulfil asks `gods.hermes_pays`). Spots = offsets from `monuments.origin` (composite_offset_rotate_b) turned as FUN_005471B0; the god and helpers walk the precinct breadth-first (ours). Hera (11-01, gifts.py) and the gift leftovers (god_gifts_deliver, help.py) ported; not ported: Atlas (Poseidon), Artemis' hunt (see "What each god's help does"). An expedition called off before its battle leaves Ares hidden at 0x23 (as the exe: only the battle brings him back) |
| attacking gods: init budgets and first actions, A destroy (nearest building of `g_target_buildings[cat]`, 5 bolts, the first landing destroys it), B curse (`g_god_curse_types`, nearest root, curse at the attack frame, special hits), C kill (first figure in id order within 15, class 1/2/7; 3 bolts + 1 cycle), Hermes caravans + treasury, Aphrodite/Dionysus charm (production stop, 400 ticks, followers), aura (Poseidon boats, Hephaestus fire risk), leave by the arrival tile + vanish, 6-month clock for hostile gods only; Artemis/Ares armies of 8 (FUN_00504650) | `attack.py` (+ `bolts.py`: bolts 0x2D/0x34 as figures, role `god_bolt`; followers role `entranced`, walking the god's last tiles; the armies through sim/military invaders, sent away at god_leave_release); Hera's "go home" only for roamers |
| god vs god: defenders of event_god_attack (0x4A/0x4B/0x50), `god_encounter_check` + 0x3C duel | `fight.py` `defend`, `encounter_check` (each walk cycle), `duel` |
| Athena vs invasions, Apollo vs monsters, Artemis vs wolves (0x51..0x54, 0x4A/0x4B/0x50) | `fight.py` `athena_month`, `apollo_month`, `walk_interrupt`, `send_against_monster` (sim/heroes `apollo_sent`), `summon_artemis` (sim/military wolves); `heroes.monster_god_engages` reads the god's `target_fig` |
| guardian monsters | sim/heroes `guardian` (1I) |
| timing | walk, 0x0B vanish, 0x22, the duel 0x3C: one frame a tick (rate 0); appear, cast, attack and the fights' / help vanish: rate 100, one frame per `frame_ticks` ticks (data/gods.json, = the group's image speed at the default game speed; "Animation" below, bug 393); frame counts from the sprites |

### Oracle shots (1H, 10-30): re/oracle/runs/1H-god (re/oracle/scenarios/god-attack.txt, tools/oracle_gods.py)
Open Play Sandbox, the jealousy countdown poked to 1: Athena (jealous) appears at logical (166, 166) = raw (167, 167)
on the map's entry road (god_attack_start: the road tile nearest the map centre, FUN_004D31E0) at tick 255, action 10
-> 0x57, and walks the road north (logical (166, 158) at tick 374), still roaming at tick 816: no attack. Ours before:
the scenario attack's budgets (she would have destroyed / cursed / killed), at (114, 114) because our sandbox has no
entry road (bugs.md). Ours now, with that road laid by hand: spawn raw (167, 167) at 255, raw (167, 159) at 375 (the
exe's tile at 374), 548 ticks of roaming. Picture: the shots g_0083..g_0087 show her red glow (soft halo, the same
size as ours at dpr 1.25 zoom 1/dpr through tools/oracle_view_compare.py); a pixel match is not possible (the exe's
view moved between shots and the frame / tick of a shot is not known). Not in an oracle shot yet: a blessing, a curse,
a bolt, a follower, the prayer-result text (they need a built, staffed sanctuary or a scenario invasion in the oracle).

Prayer result and followers (10-30): re/oracle/runs/1H-pray (scenarios/god-pray.txt: the result text 132:41 under
Apollo's window, ours 0 px differ, bugs.md 244); re/oracle/runs/1H-follower (scenarios/god-follower.txt,
`tools/oracle_gods.py --follower-poke`: Ares' visiting figure 1848 turned into Dionysus in 0x36 at tick 470: three 0x47
followers beside him at once, then 0x3F along x = 57 south; Ares' Dragon walks with him). The exe draws a god as two
pictures (walker_draw 0x0044FEF0 type 0x43: the frame, then Figure+0x150 at +0x6C / +0x6D), bugs.md 245.

Jealous visits on a built city (bug 232 check, 10-30): re/oracle/runs/1H-jealous (re/oracle/scenarios/god-jealous.txt,
`tools/oracle_gods.py --jealous-poke` / `--jealous-report`): "See a working city" (628 buildings: 35 townhouses, 6
estates, sheep / goat farms, wineries, oil presses, sculpture studio, armory, tax offices, gymnasia, stadium, theatres,
fishing wharves; 2 sanctuaries, Apollo and Ares) with the sandbox's six jealous gods made eligible one a month (god
record + scenario slot 14 + countdown poked). Each came at day 5 (first in the dumps at ticks 561 Athena, 1377 Demeter, 2193 Artemis,
3009 Aphrodite, 3825 Hades, 4641 Zeus) by the Ares sanctuary's road (57, 48), roamed the city's roads (to
(67, 31) and (64, 87)) and left: actions seen only 10 -> 0x57 -> 0x0B (dumps every 51 ticks); the alive building
count stayed 628 in every dump, the curse table (zone 126, g_type_curse) kept one hash over all 6026 ticks, no bolt
figure (0x2D / 0x34) came from them (the one 0x2D at tick 2856 is Apollo's, fighting the city's monster). The code
agrees: action 0x57 is `FUN_004F1300` (visit_elapsed >= visit_length -> 0x0B, else figure_roam_tick; no target
search), and these gods are friendly, so `god_figure_hostile` is false (no aura). The working city has no farm
(Demeter's types 31..33) and no hunting lodge (Artemis' 46); the handler searches no targets, so this does not
matter. Verdict: a jealous god never destroys, curses or kills; ours (0ef0978) stands.

Oracle compare (jealousy, empty sandbox, 19.5 years; `test_gods_jealousy_attack`): ours 23 / 24 / 25 attacks for seeds
1 / 2 / 3, gaps 6..12 months, first in month 9..12; the oracle (re/oracle/runs/open-play-events) 25, gaps 6..12, first
in month 13. Per god the oracle had Artemis 11, Aphrodite 7, Demeter 3, Zeus 3, Athena 1, Hades 0 (+5 unnamed); ours
(seed 1) Aphrodite 11, Athena 6, Artemis 4, Zeus 2, Demeter 1, Hades 1, i.e. the table weights
(Aphrodite 3, Artemis 2, Athena 2, others 1). The oracle's Artemis share is unlikely under independent draws with
those weights; I'm not certain why (the exe's RNG stream cannot be reproduced; not checked further).

## Open questions
- Exact effect of actions 0x3A (budget A), 0x43 (C: `FUN_004EFA50`) and the special kinds
  (+0x13C) — they run in the undecompiled handler `0x004C5D40`; budgets and order are verified,
  the per-tick effect (fire? collapse? killing walkers?) is not.
- `gift_active` (+0x30) has no static writer: the 3200 − carried remainder may never be delivered.
- +0x04 (init 50) and +0x1C (0xC0) have no reader in the decompile.
- Need tests: `FUN_00569310` (food), city+0x18, city+0x34/+0x38, city+0x18A4.. — fields owned by
  population/economy.
- Scenario +0xDC (max sanctuaries) and `0x004E5F60` (placement limit) — hypothesis.

## Cross-references
- population-housing: `house_param`, `0x00566F20` crime, `0x00566D40` births, `0x00486AB0` emigration.
- economy / trade-empire: `FUN_00488A60` storage space, `cities_trade_update` (Hermes),
  `FUN_005BA890` resources, world city +0x164 (Zeus), request events (Hermes, Ares).
- walkers: figure type table `0x0063969C` (40-byte rows; the name pointer of type t is the last
  dword of row t−1); 0x41 PRIEST, 0x42 PLAGUE_DUDE, 0x43 GOD, 0x44 MONSTER, 0x45 HERO.
  `figure_type_value` (Athena/Hermes).
- military-sentiment: formations `0x00DB7B40` (Zeus, Hephaestus), invasions `FUN_004AC7C0`.
- map-buildings: Building+0x32 (sanctuary activity), +0x33 visit timer, +0xDB sanctified,
  +0xC4 bit 8 / +0xC8, `g_type_curse`.

## Naming notes
- Names are in `re/names/religion.tsv`; addresses already named by other subsystems keep their
  names there: `curse_timers_decay` 0x004E5EB0, `g_type_curse` 0x00EF60B0, `g_production_stop`
  0x00EF6163 (economy); `god_sanctuary_complete` 0x004EA710, `send_emigrants` 0x00486AB0,
  `houses_crime_update` 0x00566F20, `population_births_deaths` 0x00566D40 (population-housing).
- `re/names/religion.tsv` renames `0x004E9440` from `god_sanctuary_finished` (housing.tsv) to
  `god_sanctuary_active`, and `re/structs/religion.tsv` renames Building+0x32 to
  `sanctuary_activity` (corrections, see "Sanctuary built vs active").
- Figure fields used by god figures (`re/structs/religion.tsv`): +0x0B god id (named `resource`
  by another agent: a per-type union), +0x42/+0x44 visit length/elapsed, +0x104/+0x108 time
  budget stamp/days (shared with monsters), +0x120 budget A (monsters: attacking hero),
  +0x12C budget C, +0x132 budget B (curses), +0x13C attack kind.

## God and priest figure handlers (RE, 2026-10-29)
Read from the disassembly of the two handlers Ghidra could not decompile (`figure_god_handler`
`0x004C5D40`, `fig_handler_priest` `0x004CA350`) plus their (decompiled) helpers. Tag: **[v]** read in
the code, **[h]** hypothesis. Notation: `f` = the figure, `b(i)` = building i, `speed` =
`figure_type_value(f, 8)` (figure model row 0x43 "God", col 8), `frames(g)` = number of frames of the
god's sprite group g (from the loaded sprite file, see "Animation" below), `atk_frame` =
`0x0063A8FC[god]` = 19,17,19,13,12,11,17,15,10,10,18,10,20,19, `shot_frame` = `0x0063A8C4[god]` =
16,17,19,13,15,11,17,15,10,10,18,10,20,19 (god order 0..13). Tools: `re/venv/bin/python
tools/disasm.py`; the jump table of the god handler is indexed by `action − 4` (88 entries).

### God figure: the C++ "behaviour" objects
`figure_set_action(f, a, next)` `0x004ABAF0` (ECX = behaviour object) stores `saved_action = action`,
`f+0x34 = next` (the action taken on arrival), `action = a`, plays a sound (`0x004ABA30`), then calls the
object's vtable slot 1 = an **enter-action callback**. `figure_walk_then(f, speed, a_lost, keep)`
`0x004ABB60`: one move step; direction 8 (arrived) → `figure_set_action(f, f+0x34)`; 9 → re-route;
10 (lost) → if `keep == 0`: `set_action(a_lost)` (or delete if 0), else nothing (the caller handles it). [v]

| object | vtable | enter callback | used for |
|---|---|---|---|
| `0x00EF5DC8` | `0x005D93F8` | `0x004EBD50` (switch on action 0x1D..0x49) | attacking god |
| `0x00EF5DD0` | `0x005D93E8` | `0x004EA750` (not decompiled, not read) | actions 0x4A/0x4B/0x50 (fight a monster/army) |
| `0x00EF5DD4` | `0x005D93F0` | `0x004EAF30` (not read) | help walks 0x51..0x54, 0x58 |
| `0x00EF5DC0` | `0x005D9400` | `0x004F0FD0` (read 10-30: 0x0B -> sound 10; 0x56 -> 0x004F1030: action 10, next 0x57; 0x57 -> 0x004F10D0: +0x44 = 0, +0x42 = 0xF00, next 0x0B) | jealous arrival 0x56/0x57 |

Enter callbacks of `0x00EF5DC8` (each also sets `anim_frame = 0`) [v]: 0x37 none; 0x38 `0x004ED080`;
0x39 `0x004ED160`; 0x3A `0x004ED400`; 0x3B `0x004ED510`; 0x3C `0x004EE570`; 0x3F `0x004EF330`;
0x40 `0x004EF3F0`; 0x42 `0x004EF850`; 0x43 `0x004EF890`; 0x44 `0x004EF9B0`; 0x45 `0x004EFDE0`;
0x46 `0x004EFE80`; 0x47 `0x004EFF20`; 0x48 `0x004EFFD0`; 0x49 `0x004EC000`; 0x1D `0x004F2060`;
0x1E `0x004F21F0`.

### God figure: every tick, before the switch [v]
```
f+0x0C = 0; f+0x42 = 0xF00 (overwrites the 6528 that sanctuary_update gives Zeus: every visit is 0xF00)
home = f.building_id; route_mode = 3                        # friendly gods: mode 3 stays
if god_figure_hostile(f) (0x004EDE40: god.unfriendly == 1 and god.listed == 1):
    if f+0x104 != month_tick: f+0x108 -= 1; f+0x104 = month_tick     # 96 -> 6 months
if god_figure_is_poseidon(f) (0x004F1720): water_mode = 1; route_mode = 6
elif hostile: water_mode = 0; route_mode = 8 if flags & 0x100 else 10
              # 10 = route_bfs_military(..,0,0); 8 = (..,1,1) = may cross the blocked marks (pathfinding.md §4)
if hostile and anim_frame == 1: god_hostile_aura(f)       # 0x004EE0C0, below
if anim_frame == 1: god_encounter_check(f)                 # 0x004EE2B0, god-vs-god duel start
if not Poseidon and tile is water (terrain & 4) and not (terrain & 0x44 == 0x44 and byte 0x00CB4B08[tile])
   and not flags & 4: saved_action = action; action = 0x59; flags |= 4; anim_frame = 0
missile_target: cleared if it is a hero (0x45) with flags & 0x10
switch action (below); then the sprite/animation tail (below)
```
`god_hostile_aura` (once per animation cycle of a hostile god) [v]:
- Poseidon: every figure within Chebyshev distance < 6 whose type is in `0x0063AFC4` = {0x19 fishing
  boat, 0x14 trade ship, 0x39 trireme, 0x2C urchin collector} gets `action = 4` (dies).
- Hephaestus: up to 10 buildings within radius 4 of a type in `0x0063AFD8` = {3..14} (houses; helper
  `0x004AC420` not decompiled, so "radius 4" and "up to 10" are its arguments **[h]**): per building
  `rng_step(); if d0 % 100 <= 5: b.fire_risk (+0x48) = 1000` (catches fire at the next fire check).

### Attacking god (A): action by action
Arrival and init (`event_god_attack` / `god_attack_start` put the god on the map with action 10 → 0x36).
0x36 → `god_attack_init` `0x004ECA10` per god [v]:

| God | first action / target | A,B,C | other |
|---|---|---|---|
| Zeus `0x004EC090` | 0x3A at the palace (first alive root palace; direct write, no enter callback); no palace → `set_action(0x3A,0x3B)` (enter picks) | 3,10,10 | trade block a+b 0xC0 |
| Poseidon `0x004EC180` | `set_action(0x37)` | 3,10,0 | trade block a |
| Demeter `0x004EC310` | `set_action(0x38,0x39)` (enter picks); also kills every second sheep/goat | 3,10,10 | |
| Apollo `0x004EC4A0` | 0x38 → 0x39 at the palace, else `highest_house_building` `0x004EC1F0` (max `house_level` among alive buildings) | 2,10,7 | |
| Artemis `0x004EC410` | `set_action(0x43,0x44)` | 2,10,10 | army `FUN_00504650(4,…)` |
| Ares `0x004EC560` | `set_action(0x43,0x44)` | 4,0,10 | army `FUN_00504650(10,…)` |
| Aphrodite `0x004EC650` | `set_action(0x3F,0x40)` | 0,0,0 | |
| Hermes `0x004EC6A0` | `set_action(0x45,0x46)`, kind +0x13C = 0x13 | 0,0,10 | trade block b |
| Athena `0x004EC3B0` | `set_action(0x38,0x39)` | 3,10,7 | |
| Hephaestus `0x004EC5F0` | `set_action(0x38,0x39)` | 2,10,5 | |
| Dionysus `0x004EC710` | `set_action(0x3F,0x40)` + 3 followers (`god_follower_create(f, 0x44)`) | 0,0,0 | |
| Hades `0x004EC240` | 0x38 → 0x39 at the palace / highest house | 3,10,10 | |
| Hera `0x004EC850` | same as Hades (+ cattle kill `0x004EC7C0`) | 3,10,10 | |
| Atlas `0x004EC950` | same as Hades | 2,10,10 | |
All set `+0x108 = 0x60`, `+0x104 = month_tick`. **Correction:** `+0x13C` ("kind") is read only by
Hermes' 0x45 (a figure type to hunt); for every other god it has no effect (only reader in the exe:
`0x004EFDE0`).

`god_attack_should_leave` `0x004ECB00` (checked at the start of 0x38, 0x39, 0x43, 0x44, 0x45, 0x46; not
in 0x3A/0x3B): `if hostile and (t108 < 1 or (A < 1 and B < 1 and C < 1)): flags &= ~0x1000;
set_action(0x49, 0x0B)` and the tick ends. [v]

**0x37 wander** (`god_attack_wander` 0x004ECB70) [v]:
```
if t108 < 1 or (A < 1 and B < 1 and C < 1): flags &= ~0x1000; set_action(0x49, 0x0B); return
if A > 100 or A < 0: A = 0;   same for B, C
if A > 0: set_action(0x3A, 0x3B); return
if B > 0: set_action(0x38, 0x39); return
if C > 0: set_action(0x43, 0x44); return
# only reachable when a budget was > 100 (clamped to 0 above), i.e. never in normal play:
if not flags & 0x1000:
    rng_step(); if d0 % 100 < 21: set_action(0x43, 0x44); if f.missile_target == 0: set_action(0x49, 0x0B); return
    if tile_progress in (0, 15): flags = flags & ~0x100 | 0x1000; f+0x30,+0x32 = x,y; route_free;
        god_roam_pick (0x004F1C90): dest = (x + rnd%15 - 8, y + rnd%15 - 8) if in the play area,
        snapped by route_tile_check (Poseidon: 0x00461C20, water); return
figure_walk_then(f, speed, 0x37, keep=1); on direction 8/9/10: flags &= ~0x1000; set_action(0x37, 0x37)
```
So in practice the god does **all A, then all B, then all C, then leaves** (or leaves earlier when the
6 months run out at a should_leave check). Every failure to find a target costs one unit of the budget.

**A = destroy a building (0x3A walk → 0x3B bolt)** [v]:
```
enter 0x3A (0x004ED400): cat = god_destroy_category(god) (0x004ED200):
        Zeus, Ares 10 (= random cat rng%11; cat 10 is empty -> nothing found); Poseidon 1;
        Demeter, Artemis 0; Apollo, Dionysus 6; Aphrodite 7; Hermes, Hephaestus, Atlas 2; Athena 3;
        Hades 4; Hera 9
    b = nearest_building_in_category(f, cat) (0x004ABBF0): alive (state 1) buildings whose type is in
        g_target_buildings[cat] (0x006383E0, 50 ints per category, list below) and whose type is not
        cursed; smallest |dx|+|dy| from the god to b.x,b.y; first index wins ties; any record (not only roots)
    none: set_action(0x37, 0x38); A -= 1
    else: f+0x5E = b; dest = free_tile_near(b.road_access, radius 1) (0x004C41B0: first empty, non-building,
          non-edge land tile, scored by distance from the map edge); Poseidon: building_water_exit(b);
          f+0x34 = 0x3B; route_free
tick 0x3A: figure_walk_then(f, speed, 0x37, keep=1)       # arrival -> 0x3B
    if f+0x5E == 0 or b.state != 1: f+0x5E = 0; hostile ? set_action(0x37,0x37) : action = 8
    elif direction == 10 (lost): route_free; A -= 1; if A <= 0: -> 0x37 as above
        elif Poseidon: -> 0x37 (gives up)   else: dest = b.road_access; action = 0x3A (no callback);
        flags |= 0x100; route_mode = 8; route_free          # retry, allowed through blocked tiles
enter 0x3B (0x004ED510): +0x92 = 5 (shots); face b; timer = frames(2); flags &= ~0x1C000
    if b gone: god_target_reset (0x004F1FA0: clear target/+0x5E/+0x100; hostile -> set_action(0x37,0x37), else 8)
    else dest = (b.x + rnd%size, b.y + rnd%size)            # two rng_steps
tick 0x3B (0x004ED800): timer -= 1; n = frames(Athena ? 4 : 2)
    if b invalid (0, type 0, size 0, state != 1): +0x92 = 0; A -= 1; set_action(0x37, 0); return
    (a check "previous bolt f+0x138 aims off b -> A -= 1" exists but is always false as called:
     god_missile_alive 0x004ED790 is passed (bolt, god) and requires its first argument to be a god)
    each animation cycle: frame 0 (once, flag 0x4000): new random tile of b as dest, face it
        frame == shot_frame (once, flag 0x8000): bolt = figure 0x34 (enemy missile) from the god to dest
            (0x004D9D70: line move, building_id = god); f+0x138 = bolt
        frame == n-2 (once, flag 0x10000): +0x92 -= 1
    when +0x92 == 0 and no bolt of the god is alive (god_missile_alive(god, f+0x138): the bolt's
        building_id == god and type 0x34 (friendly god: 0x2D); [h] a deleted bolt slot no longer matches):
        building_destroyed_by_attack(b) (0x004928C0);
        A -= 1; set_action(0x37, 0)
```
The bolt (handler `fig_handler_enemy_missile` 0x004BD970, owner type 0x43) [v]: moves 4 fine units a
tick along a line, life 0x79 sub-steps. On a figure on its way (`0x004DCE20`, not read **[h]**: a
figure on its tile) → `figure_hit(god, victim, 1)` (missile damage with the god's model stats). At the end
of its line: if a building is there (`0x004DCF20` **[h]**: building at the tile) →
`wall_damage_add(b.tile, 10, 100)` = damage 100 > threshold 10 → **the building is destroyed by the
first bolt that lands on it**; else, if the god is in 0x3B, the god's `+0x5E` is cleared (target lost →
A −1 next tick). So A = "destroy the nearest building of the god's category, one per unit".

`g_target_buildings` (0x006383E0) per category [v]: 0 granary, wheat/onion/carrot farms, agoras, goat
farm, hunting lodge, fishing wharf, urchin quay, corral, fruit lodge; 1 fishing wharf, urchin quay,
warship wharf, dock; 2 timber mill, marble quarry, foundry, mint, sheep farm, sculpture studio, oil press,
winery, armory, storehouse, orichalc refinery, chariot workshop, black marble; 3 armory, horse ranch,
wall, tower, gatehouse, warship wharf, foundry, chariot workshop, guardpost; 4 tax office, elite houses
(9..14), mint, dock, trading post, race track; 5 tower, warship wharf; 6 houses 2..8, guardpost,
infirmary, super office, agoras, fountain, bibliotheke, gymnasium; 7 columns, bench, the decorations
15..25, 148..152, commemorative; 8 the sanctuaries 84..98, heroes' hall, artisans' guild, marble quarry;
9 palace, stadium, theatre, heroes' hall, sanctuaries, race track, museum, observatory, elite houses;
10 empty. (Type ids: `extracted/model/model_*.json`.)

**B = curse (0x38 walk → 0x39 curse)** [v]:
```
enter 0x38 (0x004ED080): b = god_curse_target_find(f) (0x004ECE60):
        list = g_god_curse_types[god] (0x0063AA4C, 20 ints per god, 0-terminated, below);
        Zeus: rng_step(); god = d0 % 14 + 1 (1..14; row 14 is past the table = the curse-length bytes,
        read as types 2, 4, 6, 9 = hut, hovel, tenement, elite vacant: an exe quirk)
        nearest (|dx|+|dy| < 1000) alive root building whose type is in the list and not cursed
    none: B -= 1; set_action(0x37, 0x3A)
    else: f+0x5E = b; dest = b.road_access (Poseidon: water exit); f+0x34 = 0x39
tick 0x38: should_leave; figure_walk_then(f, speed, 0x37, keep=1); lost/target-gone handling as 0x3A (B -= 1)
enter 0x39 (0x004ED160): +0x92 = frames(4); face b
tick 0x39 (god_curse_building 0x004ED2A0): should_leave; +0x92 -= 1
    if anim_frame == atk_frame: curse_effects_spawn(b, f) (0x00412980); B -= 1; set_action(0x37, 0);
        g_type_curse[b.type] = god_curse_length(god) (months << 4)
```
`g_god_curse_types` [v]: Zeus (unused, see above) fishing wharf, urchin quay, warship wharf, 3 farms,
infirmary, podium, college, theatre, drama school, stadium, gymnasium, olive tree, grapevine, foundry,
mint; Poseidon 44, 45, 136; Demeter 31, 32, 33; Apollo 76, 81, 77, 82, 78, 80, 79, 202, 203, 205, 207,
206, 204; Artemis 46; Ares, Aphrodite, Hermes none; Athena 117 palace, 132 tower, 36 olive tree;
Hephaestus 135, 55; Dionysus 35; Hades 117 palace, 50, 48; Hera 216, 217; Atlas 49, 213, 56.
(These differ from the sanctification lists `0x004E8F20..` documented above.)

Special hits [v]: the curse spawns 4 effect figures (type 6 "ambient", effect kind 0xF, created even off
screen: kind flag 4 in `0x005D8448`; limit 750 effects). When effect number 0 reaches the building
(effect updater `0x00410600`, call at `0x00410AE0`), `god_curse_effect_hit(god, type)` `0x004ED350`: for
every building of that type (palace: only some parts) a visual effect plus `0x004EE070` (fishing wharf,
urchin quay, type 0x88: their boat dies), then `god_special_hit(god, type)` `0x004EDFC0`, which acts only
if `type` is a house (2..14) or the palace (117):
- type 117 and Zeus: `building_destroyed_by_attack(palace)` (Zeus reaches the palace through his random
  row: Athena's or Hades' list).
- Hera: `figures_flag_go_home` `0x004EDE80`: every ordinary walker (`figure_is_ordinary_walker`
  0x004EF430: not effect/fire/soldier/animal/god/monster/ship/missile…) gets flag 0x80000, action 2, dest =
  its home's road access (all walkers return home); jockeys of race tracks too.
- Hades: `0x004EDF50` kills (action 4) every ordinary walker and the race-track jockeys;
  `g_production_stop = 4` (4 month_advance calls).
- Athena: towers (132) and walls (130) cursed for `god_curse_length(Athena)`.
- Apollo: `plague_outbreak(0)`.
So Apollo, Hades, Hera and Atlas start by cursing the palace (or the best house) and trigger these; Athena
can hit the palace through her list.

**C = kill a walker (0x43 walk → 0x44 bolts)** [v]:
```
enter 0x43 (0x004EF890): t = next_figure_in_radius(f, None, 15, after=1) (0x004AC270: slot order, alive,
        action != 4, type not in {6, 0x18, 10, 0x0E, 0x47, 0x2F}, not hidden, Chebyshev distance < 15;
        the FIRST match in slot order, not the nearest)
    loop until unit_type(t) (model col 0) in {1 helpless, 2 good guy (soldiers, hero, sentries…),
        7 good monster} and (Poseidon ? t on water : t not on water)
    none: set_action(0x37, 0); C -= 1
    else: figure_set_target(f, t); dest = free_tile_near(t.x, t.y, radius 4)
tick 0x43: should_leave; figure_walk_then(f, speed, 0x44, keep=1)        # arrival -> 0x44
    if direction == 10: (hostile only) route_free; Poseidon -> 0x37;
        elif target == 0: C -= 1; -> 0x37; else dest = t.x,t.y; flags |= 0x100; route_mode 8; action 0x43
    elif target == 0: C -= 1; -> 0x37
enter 0x44 (0x004EF9B0): timer = frames(2); +0x92 = 3; face t; f+0x138 = 0; anim 0; flags &= ~0x4000
tick 0x44 (god_kill_tick 0x004EFA50): should_leave; timer -= 1; n = frames(Athena ? 4 : 2)
    if t gone/dying/type 6: set_action(0x37, 0); C -= 1; return
    if C < 1: target = 0; set_action(0x37, 0); return
    while +0x92 > 0: per cycle frame 0 face t, dest = t pos; frame shot_frame: bolt (0x34) at t;
        frame n-2: +0x92 -= 1
    then one more cycle (bolt at dest at shot_frame); wait while the god's bolt is alive;
    if t.action == 0x50 or t is a god (0x43): wait (no kill)
    if t is a hero (0x45) with a hall: hero action 9 back to the hall, hall +0xC4 |= 4, target = 0,
        0x004E3310(god, hero); return              # heroes are sent home, not killed, no C cost
    else: t.action = 4 (dies; heroes without a hall too); t.flags |= 0x10; set_action(0x37, 0); C -= 1
```
(The bolts also damage what they touch, see A.) So C = "kill the first eligible walker within 15
tiles, one per unit, after 3 bolts".

**Hermes (0x45 → 0x46, then 0x47 → 0x48)** [v]: enter 0x45 (0x004EFDE0): first figure (slot order) alive,
not dying, not hidden, of type `+0x13C` = 0x13 (caravan merchant); none → `set_action(0x47, 0x48)`;
else target it, dest = Hermes' own tile (he does not walk to it). 0x46: `timer = frames(2)`; tick
(0x004EFEC0): `timer -= 1; if < 1: caravan.action = 4 (dies), flags |= 0x10; set_action(0x47, 0x48)`.
(C is never decremented here, so Hermes keeps killing caravans while any exist; he leaves when the
6 months end.) 0x47 enter (0x004EFF20): target = palace (alive root type 117) else the first alive
root building with +0x44 != 0 (the type argument 0x7A/0x30 is ignored: flag 8 missing in 0x15), else
the first alive root building; dest = its road access. 0x48: `timer = frames(4)`; tick
`figure_drain_treasury` 0x004F0010: at timer < 1: `treasury -= max(1000, treasury/10)` if treasury >
1000, else treasury = 0 if > 0; `set_action(0x37, 0)`.

**Aphrodite / Dionysus (0x3F → 0x40/0x41 → 0x42)** [v]: enter 0x3F (0x004EF330): target = palace,
else first alive root building with +0x44 != 0, else first alive root building; none → leave (0x49).
dest = its road access. 0x3F tick: walk; lost → retry with route mode 8. enter 0x40 (0x004EF3F0):
`+0x42 = 0x960 (2400), +0x44 = 0`, roam init. 0x40 tick (0x004EF6F0) / 0x41 tick (0x004EF550): every
tick `g_production_stop = max(1, g_production_stop)` (no building spawns walkers while she roams),
`figure_roam_steps(f,1,1)`, `+0x44 += 6`; at `+0x44 >= +0x42` (400 ticks) → `set_action(0x42, 0x0B)`.
In 0x40, at even tile_progress, every ordinary walker within radius 8 is **entranced**
(`0x004EF2F0`): deleted and replaced by a follower figure 0x47 "Entranced" of the same subtype, chained
behind the god (`god_follower_create` 0x004EF150, chain via +0x5C/+0x68), then action 0x41 (a
frames(4) pose, back to 0x40). Every anim frame 1 of 0x41 spawns a visual. 0x42: walk to the land
entry (0x004EF850) → 0x0B. Followers are released by `god_leave_release` `0x004EF770` →
`0x004EF0F0` (not read).

**Leaving (0x49 → 0x0B)** [v]: enter 0x49 (0x004EC000): route_free; dest = `god_attack_arrival(god)`
(Zeus, Aphrodite, Athena, Hades, Hera → the palace's road access (or another building), Poseidon → the sea
entry / an invasion point, others → the land entry snapped by `free_tile_near(.,2)`); then
`god_leave_release` (Ares: every enemy infantry 0x29 of army 10 retreats (action 3, formation reset);
Artemis: army 4; Aphrodite/Dionysus: followers). Tick 0x49: `figure_walk_then(f, speed (Hermes ×3),
0x0B, keep=0)` → 0x0B on arrival or when lost. **0x0B (also 0x04)**: `flags &= ~0x10`; Hermes without
flag 0x20000: action 0x49 again with dest = his creation tile (+0x2C), and when he arrives flag 0x20000 →
deleted at once; others: play group 1 (vanish) and when `anim_frame >= frames(1) − 1`: `god_leave_release`,
`state = 2` (deleted). The god walks out to that tile; he does not vanish on the spot (except Hermes'
second step). Lost → vanishes where it stands. Actions 0x35, 0x4C..0x4F, 0x55 (no case) → 0x0B.

**Water (0x59)**: `god_water_hop` 0x004F18C0: a non-Poseidon god on water plays vanish (group 1), then
`0x004F1750` (not read; **[h]** moves it to land), appear (group 3), back to `saved_action`. Hermes skips
the animations.

**God vs god duel (0x3C)** [v]: `god_encounter_check` 0x004EE2B0 (each anim frame 1, if
`god_can_fight(f)`): scan the 14 god figures; a visible, alive god figure of opposite hostility within
Chebyshev 15 (no distance limit when f is Zeus with an active sanctuary, Hera (active) vs Zeus,
Aphrodite (active) vs Ares/Hephaestus/Hermes/Dionysus) that `god_can_fight` → both `set_action(0x3C,
f+0x34)` targeting each other. 0x3C (enter 0x004EE570: +0x92 = 5, timer = frames(2); tick 0x004EE850):
walk to within 8 tiles, then 5 bolts (0x34 if hostile else 0x2D) at shot_frame; when +0x92 == 0 and the
last bolt is gone: `god_fight_wins(f, other)` decides; the loser `set_action(0x3D, 0x0B)`, the winner 0x3E
(resume `saved_action`; Zeus hostile re-inits). 0x3D (0x004EEF30): friendly loser walks back to its
sanctuary (action 9, flags 0x10 = no blessing) then 0x0B; hostile loser leaves (0x49).
Actions 0x4A/0x4B/0x50 (object `0x00EF5DD0`) [v for 0x4A/0x4B]: 0x4A = appear (`set_action(10, 0x4B)`,
timer = frames(4)); 0x4B shoots player bolts (0x2D) at its target and forces the target to fight back
(a god target → 0x44, a monster → 9); at timer end → 0x50 (`0x004EAD00`, not read) or 0x0B if the target
is gone. These are the defender / monster-fight walks (`event_god_attack`, Athena, Apollo); the
caller-side choice of 0x4A vs 0x3C was not traced.

### Gods fighting (0x4A..0x54) and bolts (RE + ours, 2026-10-29) [v]
Behaviour objects `0x00EF5DD0` (0x4A/0x4B/0x50: shoot one target from where the god stands, drive it off) and
`0x00EF5DD4` (0x51..0x54: hunt invaders or a monster across the map). Who sends a god:
- **Athena** `athena_month_defend` 0x004E6340 (monthly, sanctuary built): an invasion on (`FUN_004AC7C0(0)`: enemy
  units alive besides transports / warships) → Athena out of her sanctuary (on the map: `set_action(0x51)`).
- **Apollo** `apollo_month_fight_monster` 0x004E6440 (monthly, sanctuary built): not on the map → the bad monster
  (class 8) nearest the sanctuary's road access (`FUN_004F1B50`, any distance) → 0x51 with flag 0x400 (keep this
  target); on the map (not in 10, 0x51..0x54, 0x0B, 4) → the bad monster nearest him: 0x4A/0x4B.
- **Visits** `god_walk_interrupt` 0x004EBA10 (a friendly god in actions 8/9): Apollo (active sanctuary): the nearest
  bad monster → 0x51 (0x400); Athena or Hera (active): an invasion on → 0x51.
- **Artemis** the wolf chase 0x0056AF80: a wolf at its prey (after `figure_tile_contact`) or in a fight (5) whose
  target fell → Artemis (sanctuary complete; spawned at its road access if absent) `set_target(wolf)`, 0x4A/0x4B,
  unless she is in 0x4A/0x4B or has `+0x34 == 0x4B`.
- **Defenders** of `event_god_attack` (Zeus / Aphrodite / Hera): 0x4A/0x4B at the attacking god.
- **Monsters** `monster_event_update`'s tail: Apollo (sanctuary complete) at the new monster, 0x4A.

0x4A (0x004EA8F0) = `set_action(10, 0x4B)`, timer = frames(4), flag 0x2000 on both. 0x4B (0x004EAA60): timer −1 a
tick; the target turns on the god (a god → 0x44 at it, a monster → 9); a bolt 0x2D at `shot_frame`; timer < 1: target
gone → 0x0B, else 0x50 (timer = frames(2)). **0x50** (0x004EAD00): a hostile god target's trade block is lifted
(`trade_block_set`: Demeter 2, Hermes 1, Poseidon 0); a bolt each cycle; after 5 cycles of frames(2) the target
gets action 4 wherever it is (a god vanishes, a monster / wolf dies; no distance test), `FUN_004E3310(god, target)`
(the fight message), the god 0x0B. 0x51 enter (0x004EAF90): flag 0x400 → keep the target, else `FUN_004AC570(fig, 0)`
(the enemy-company member nearest, Chebyshev, not on a building tile); none → 0x0B. dest = 4 steps ahead on the
target's route or its tile, `free_tile_near(4)` (`FUN_004C43C0`); farther than 5 → vanish (frames(1)) and reappear
there (frames(3)) (flags 4/8). 0x51 tick (0x004EB180): walk; arrived: within 6 → 0x52, else 0x53; every 50 ticks at a
tile centre re-aim. 0x52 (0x004EB4A0/0x004EB5F0): farther than 5 → 0x53; else stand and shoot a bolt per cycle of
frames(Athena 4, else 2). 0x53 (0x004EB740/0x004EB7A0): chase; within 16 → 0x52; lost → placed on the target's tile,
appear. 0x54: walk to the creation tile, 0x0B, record +0x1C = 0xC0.

**Bolts** (created by `0x004D9D70`, a line move from the god to the target tile, `building_id` = the god):
0x2D (friendly, `walker_player_missile` 0x004BACE0): 4 fine units a tick, deleted past 120 ticks or when its god is
gone; on each tile it hits the first non-dying visible invader, wolf, enemy ship, hostile god (class 10) or bad monster
(class 8). 0x34 (hostile, `fig_handler_enemy_missile` 0x004BD970): hits any non-dying figure but invaders, missiles,
enemy ships, friendly gods (class 9) and good monsters (class 7); at the end of its line a building there takes
`wall_damage_add(tile, 10, 100)` (destroyed). The hit is `figure_hit(god, victim, 1)`: a god against anything but a
god, monster or hero has attack 9999 (a sure kill). Picture (both handlers, by the god figure's resource): packed
`destruction` groups (rank − 1 = atlas group) Zeus 0x2230, Poseidon 0x223A, Demeter 0x2234, Apollo 0x2229, Artemis
0x2232, Aphrodite 0x223B, Hermes / Hera 0x2239, Athena 0x2233, Dionysus / Atlas 0x2235, else (Ares, Hephaestus, Hades)
0x2231; 8 frames x 8 directions (frame-major), the direction = the 32-way flight angle / 4.

**Intercept** (`FUN_004C43C0(fig, target, 4)`): dest = 4 steps ahead on the target's route; when that is within 1 of
the target (or it has no route: its tile), `free_tile_near` 0x004C41B0 (tile, 4): rings radius 5..12 (ring table
0x005F07EA, ring k = radius k + 1, from index 4 + 5), the first in-play tile with no building, no figure and clear or
wooded terrain, scored by `map_near_play_edge` (within 3 → 2, 7 → 3, 12 → 4, else 5; the first 5 wins); none → the tile.

**Voices** (`FUN_005A1050(god, kind)`): Audio/Voice/Walker/<god table + 0x28·kind> (data/gods.json `voices`):
kind 0 / 1 / 2 the jealous attack message with 3+ / 1..2 / no sanctuaries placed (god_attack_message 0x004F1110),
3 a god invasion (event_god_attack), 4 a god-sent monster (monster_event_update, kind byte != 0), 5 / 6 a quest given /
fulfilled (event_quest), 7 a god's help (god_message 0x00480590); Apollo kind 1 in a Poseidon game → entry 8
(apo_ev_2_at.mp3). Played on the voice stream when voices are on (`DAT_00F2A76D`).

**Followers (0x47, `god_follower_create` 0x004EF150)**: a walker within 8 of a charming Aphrodite / Dionysus
(0x004EF2F0, at even tile progress) is deleted and a follower figure (resource = its type) is chained behind the god;
Dionysus brings 3 of his own (0x44). `god_leave_release` 0x004EF770 at the god's 0x0B / leave: the followers are
deleted (0x004EF0F0); Artemis' army 4 / Ares' army 10 retreat (action 3).

**Armies** (`god_attack_init`): Artemis and Ares call `FUN_00504650` = `enemy_army_spawn_land(type 4 | 10,
0 archers, 8 infantry, 0 horsemen, the map entry, 10, 0x8C)`.

### Visiting god (B) [v]
```
spawn (sanctuary_update): action 10, f+0x34 = 8, +0x44 = 0       (+0x42 is forced to 0xF00 each tick)
0x0A appear: timer += 1; nothing is drawn while timer < 10;
    Hermes: walks (speed ×3) to dest (from the land entry), arrival -> f+0x34; lost -> teleport (0x004E3220) -> f+0x34
    others: wait until anim_frame >= frames(3) - 1, then action = f+0x34 (= 8)
0x08 roam: if god_walk_interrupt(f) (0x004EBA10: Apollo/Athena/Hera fight): stop
    if +0x44 >= +0x42 (3840): t = road_tile_near_building(home, radius 20) (0x004A39D0)
        none: action 0x0B (vanish here); else action 9, dest = t
    figure_roam_tick(f, speed) (0x004D6790: +0x44 += speed; roads, as other roamers)
    if not flags & 0x10: god_visit_bless_try(f)
0x09 walk home: god_walk_interrupt; figure_move(f, speed); on 8/9/10 -> action 0x0B (vanish);
    if not flags & 0x10: god_visit_bless_try(f)
0x0C bless (set by god_visit_bless_try: +0x5E = b, b.blessed = 1):
    if b.blessed: at anim_frame == atk_frame: bless_effect_spawn(f, b) (0x004127E0, visual) and frame += 1;
        stays until anim_frame == frames(4) - 1
    -> action 8, roam_init, +0x44 = 0 (a blessing restarts the visit clock), +0x5E = 0
0x0B vanish: frames(1) animation, then deleted (state 2)
0x06/0x07 (hidden wait at the sanctuary, line-walk out, enter the building -> deleted): present in the
    handler, no setter found in this pass
```
So a visit lasts `3840 / speed` ticks of roaming after the last blessing, then the god walks to a road
tile next to its sanctuary and vanishes. Roaming uses the generic road roamer (`figure_roam_tick`), so
roads only (route mode 3 for the walk home).

### Help actions (C, brief) [v unless marked]
- 0x0F..0x13 Zeus (read 10-29, gifts.py): 0x0F vanish group, then dest = `FUN_004C43C0(zeus, formation leader, 10)`,
  placed; `FUN_004C4090(city, n)` = every member of the city's formations within n steps of its route's end stops
  (action 7, timer 50): n = 15 in 0x0F/0x10/0x13, 1000 in 0x11. 0x10 appear group, then ready_level 5, dest = the
  leader's tile; 0x11 a bolt 0x2D per cycle at shot_frame, then (the last bolt gone) 0x13; 0x13 cast group: the leader
  action 4 + `formation_member_lost`, every figure of type 0x28..0x2A, 0x3F, 0x40 action 4, Zeus action 4.
- Athena (ported, sim/gods/gifts.py): 0x25 `FUN_004C4D50`: 8 grower figures (type 5, action 0x11 -> 0xE, timers 50..-20)
  to the grove spots of `FUN_00547250`; Athena 0x26 walks to her spot, 0x27 100 ticks, 0x28 every 30 ticks
  `FUN_004C4EF0` (growers done?), then the storage with room for 1600 oil (20) and 1600 olives (13)
  (`FUN_004C46D0`), 0x29 walk there and `granary_add_food` / `storehouse_add_goods`, the rest as gift amounts.
- 0x14 = "go home": dest = `route_tile_check(sanctuary x,y)`, action 9 (walk), then 0x0B.
- 0x0F..0x13 Zeus strike (helpers `0x004C43C0`, `0x004C4090`, `0x004E2A60`) **[h]** (only the call
  list was read): appears near the army, throws bolts (`0x004D9D70`), soldiers get action 4 and
  `formation_member_lost` in 0x13; ends in 4 / 0x14.
- 0x15 Poseidon `0x004C4910`, 0x17 Demeter `0x004C4F20`, 0x2A Dionysus `dionysus_satyrs_spawn`, 0x25
  Athena `0x004C4D50`, 0x2C Hades `0x004C4BC0`: one call each that spawns the carriers/growers/miners
  documented in "Help and prayers"; 0x16/0x18/0x2B walk to dest, arrival → Poseidon: 0x1A at the
  target, others 0x0B; each tick sets the god's `gift_active` (`g_gods+0x30`, `0x00EF5E08 + 52·god`) to 1:
  **this is the missing writer of +0x30** (see open questions).
- 0x19 (Apollo, Aphrodite, Atlas): walk to dest; on 8/9/10 → 0x1A; 0x1A waits 100 ticks (`f+0x60` counter),
  then Apollo `city_heal_plague` 0x004C5690 → 0x14, Aphrodite `0x004C56F0` → 0x14, Atlas
  `god_help_build_monument` → 0x0B.
- 0x1B..0x21 Artemis hunt (`0x004C5420` at 0x20), 0x26..0x29 Athena's olive/oil delivery
  (`granary_add_food` / `storehouse_add_goods` at 0x29), 0x2D..0x30 Hades' silver, 0x22/0x23 Ares,
  0x24/0x32 (bless effect + `0x004C59A0`), 0x31 `0x004C58A0`, 0x33 `0x004C5C20`: not detailed in this pass.

### Animation (needed for timing) [v]
After the switch the handler picks a sprite group per action (byte table `0x004C8704` → `0x004C86D0`):
group 0 = walk (actions 6..9, 0x37, 0x38, 0x3A, 0x3F..0x43, 0x45, 0x47, 0x49 (Hermes: 3), …), group 1 =
vanish (0x0B), group 2 = attack (0x3B, 0x44, 0x46, 0x3C; Athena 4), group 3 = appear (0x0A), group 4 = cast /
bless (0x0C, 0x39, 0x48, 0x15, 0x17, …; gods without their own group 4 reuse 2: table `0x0063A934`
god×5+group, flag 0x800 = not directional). `anim_frame` advances with `0x005AF8C0`: **walk frames
advance every tick; the other groups advance only when the wall-clock gate `0x006668EC[speed]` is set**
(`0x00413330`: once per `20·speed` ms of real time, speed = byte +0x3A of the sprite header). So attack,
curse and bless durations are in real time in the original, not in ticks. Frame counts come from the
god sprite file (`frames(g)` = `FUN_004EA4E0(g)` = header +0x1E of the group's sprite); not extracted yet.
For a port: count one frame per tick (or per `20·speed` ms at the original speed) and take the counts
from the sprites.

**Rate per action (read 11-02, bug 393)** [v]: the tail's switch (after `LAB_004c6ce2`) sets the group and two
flags; `sprite_anim_step(group, &anim_frame, dir, -flag & 100)`: rate 100 unless the case clears the flag.
- rate 0 (one frame a tick): the walk-group actions (6..9, 0x14, 0x16, 0x18, 0x19, 0x1B, 0x1C, 0x1F, 0x21..0x23,
  0x26, 0x29, 0x2B, 0x2D, 0x30, 0x32, 0x34, 0x37, 0x38, 0x3A, 0x3F..0x43, 0x45, 0x47, 0x4A, 0x4C, 0x4D, 0x53, 0x54,
  0x57), 0x0B (vanish), 0x3C (duel: attack group, or walk), 0x49 (walk; Hermes appear).
- rate 100: 4 and 0x0F (vanish group), 0x0A and 0x10 (appear), 0x0C, 0x13, 0x15, 0x17, 0x1A, 0x20, 0x24, 0x25, 0x27,
  0x28, 0x2A, 0x2C, 0x2E, 0x2F, 0x39, 0x48, 0x56 (cast), 5, 0x0D, 0x0E, 0x5B and 0x11, 0x1D, 0x3B, 0x44, 0x46,
  0x4B, 0x4E..0x50, 0x52, 0x58 (attack; Athena: cast in the second list), 0x51 (flag 4 vanish, 8 appear, else
  walk), 0x55, 0x59, and any action with direction 0xB (attack group).
- The gate: index = image speed (+0x3A of the group's first image) x 100 / rate; `0x00413330` (every game turn)
  sets entry i once `20·i` ms of `timeGetTime` passed since it last fired. At the default game speed 90
  `simulation_due` 0x005168A0 runs a tick every `speed_delay_ms[1] + 2` = 22 ms (time-core.md §1), so with one turn
  per tick a rate-100 frame lasts `ceil(20·speed / 22)` ticks = speed (1..6 for the gods' groups).
  `data/gods.json` `image_speed` / `frame_ticks` [god][group] (tools/build_gods.py, `rate100_ticks` in
  tools/play_buildings.py). Zeus [walk, vanish, attack, appear, cast] = [3, 3, 2, 3, 4] ticks a frame; Hermes'
  vanish / appear 1.
- Ours (sim/gods, `attack.tpf` / `dur`): a look that ends on its group's last frame lasts frames x frame_ticks
  (0x0A appear: 10 hidden + that; 0x0C bless; 0x0F / 0x10 / 0x13 Zeus' strike; action 4; 0x51's vanish / appear);
  frame events land at frame x frame_ticks into the cycle (0x39 curse at atk_frame; the bolts of 0x3B / 0x44 / 0x11 /
  0x4B / 0x50 / 0x52 at shot_frame; 0x3B's +0x92 at n - 2). Tick timers stay ticks: 0x4A's timer (frames(4), +1 a
  tick in 0x0A, -1 in 0x4B), 0x50's 5 x frames(2), Hermes' 0x46 / 0x48 (timer = frames(2) / frames(4), so only
  frames / frame_ticks of the group show), the 100-tick waits. 0x50 then runs on until anim_frame >= frames(2) - 1.
  Not modelled: the gate's phase (ours: from the look's start; the exe's is wall-clock, shared by all figures of
  one speed); a gate firing in a turn without a tick (lost in the exe, so its real rate is a little lower when the
  frame loop outruns the ticks); the handlers' ungated `anim_frame + 1` at shot_frame (0x11, 0x4B, 0x50, 0x52) /
  atk_frame (0x0C), which skips one frame and makes such a cycle (n - 1) x frame_ticks; 0x0A ending without
  resetting anim_frame (0x4B starts at the appear's last frame when the attack group is longer).

### Priest (figure 0x41, `fig_handler_priest` 0x004CA350) [v]
Spawn (`sanctuary_priests_update` 0x004E97D0, from `sanctuary_update` while the sanctuary is complete and
has workers, i.e. once per 51-tick cycle):
```
if month_tick == 0: home.activity (+0x32) -= 1
if home.activity < 20:
    altar = sanctuary_altar_part(home) (0x004EA390: first composite part whose part-object says "altar")
    spawn = sanctuary_spawn_part(home) (0x004EA3F0)
    if altar and altar+0x50 == 0 and home+0x9E (priests alive, byte) < max_priests(god)
       (0x004EA330: Zeus, Poseidon, Hades, Hera 3; Demeter, Apollo, Artemis, Athena, Atlas 2; others 1)
       and fully staffed (0x004E9770: workers >= model col 5; while under construction workers >= 0):
        p = figure_create(home+0x01, 0x41, spawn.road_access); p.action = 6; p.building_id = home;
        p.timer = 10; p+0x15C = home+0x9E; home+0x9E += 1; altar+0xA1 (byte, priests en route) += 1
        if home+0x9E == max: altar+0x9F (offering shown) = 0
```
Handler, every tick: `route_mode = 7; f+0x0C = 0; hidden = 0; +0x42 = 0xF00`; home not alive → deleted;
`anim_frame += 1` (wraps at 12, or the action's frame count). Speed 6 is passed explicitly to every
`figure_move` (route mode 13 while walking).
```
6 search:  hidden = 1; timer += 1; if timer > 10: timer = 0; if not priest_find_offering(f): deleted
   priest_find_offering (0x004E9930):
     a = priest_find_animal (0x004E9D90): first figure (slot order) alive, not dying, sheep 0x31, goat 0x32
         or cattle 0x4C with subtype 2 (bull), not already bound (+0x138) to a priest;
         else the first cattle with subtype 3 not bound
     a: action 7, target = a, a+0x138 = f (bull: animal_unbind 0x004F8300 first)
     else s = priest_find_storage (0x004EA060): walks a building list at 0x00921608 (stride 0x10C; [h] the
         storage list) and takes the first granary (57) with >= 400 food stored (3200 - free space) or
         storehouse-like type 58/61/62 with >= 400 of the 8 food goods (not set to "don't accept")
         s: action 8, f+0x5E = s, dest = s.road_access
7 go to animal (0x004E99F0 then figure_move(f,6)): re-route when the animal moved (at tile centres);
   sheep/goat on the priest's tile: action 9, +0x164 = animal type, animal deleted (state 2)
   cattle on the tile: cattle.leader = f;
     bull: cattle.action 0x15, cattle+0x138 = f; priest action 0x0E, dest = altar.road_access, route_len = 1
     cow (3): cattle.action 0x14; priest action 0x0A, dest = altar.road_access
   animal invalid/stolen: back to 6 (timer 0)
8 go to storage: figure_move(f,6); on arrival: storage_take_400_food (0x004E9E50) removes 400 food (largest
   share decides the resource); success: cart = figure_create(.., 4 cart pusher, f.x, f.y), cart.action
   0x12, amount 400, leader = f, resource = food; f+0x128 = cart; action 0x0B, dest = altar road access
   failure: back to 6
9 slaughter: face the camera; anim 18 frames (goat) or 9 (sheep); then dest = altar road access, action 0x0A
0x0A carry to altar: figure_move(f,6); arrival -> priest_arrive_altar (0x004EA140): action 0x0C,
   altar+0xA1 -= 1; route trouble (9/10): new dest and move (speed 12 when not sheep/goat [v, odd])
0x0B walk with the cart: same as 0x0A (dest refreshed if 0,0)
0x0E lead the bull: move; after 3 route steps: action 0x0D (wait, face the bull, the bull faces back);
   the rest is in the cattle handler 0x004CB350 (not read)
0x0C sacrifice, every tick: priest_sacrifice_done (0x004EA1A0), anim 0, face the altar
   priest_sacrifice_done:
     if altar+0x9F == 0 and home+0x50 != 0: home+0x50 = 0
     if altar+0xA1 < 1 (no priest still on the way) and home+0x50 == 0:
        kind = 2 if a cart (cart deleted) else 3 if the target is cattle else 1 (carcass)
        priest deleted; home+0x50 = 1; altar+0x9F = kind; altar+0xA1 -= 1
        home.activity (+0x32) = 24                                  # the sanctuary is active again
        if altar+0xA1 == -max_priests: altar+0xA1 = 0
```
On deletion (`priest_deleted` 0x004EA2B0 from `figure_delete`): if not in 0x0C, `altar+0xA1 -= 1` (floor 0);
`home+0x9E -= 1`. A route failure (direction 10) deletes the priest (handler tail).
So: priests leave the sanctuary when activity < 20 (about 4 months after a sacrifice), go to the first
sheep/goat/bull (or cow) in figure order or else to a granary/storehouse for 400 food, bring the animal or
the cart to the altar's road access, and the sacrifice completes once every priest sent has arrived:
the first one sets activity = 24 and disappears with its offering; the others stay in 0x0C until the altar
display (+0x9F) is reset. The meat is not stored anywhere (the animal is deleted; the 400 food is removed
from storage).
Open: `home+0x50` (sacrifice) vs `altar+0x50` (spawn check) are different records unless the altar is the
main record; `altar+0x9F` is reset only when the max-th priest is sent, so with max > 1 the waiting
priests may stay in 0x0C until the next round **[h]**; the bull's walk (cattle actions 0x14/0x15) is in the
cattle handler.

### Not determined in this pass
`0x004DCE20` / `0x004DCF20` (what the bolt hits), `0x004F1750` (water hop), `0x004EF0F0` (follower release),
`0x004E3310` (fight/hero outcome, called with (winner, loser)), the 0x00EF5DD0/DD4/DC0 enter callbacks
(`0x004EA750`, `0x004EAF30`, `0x004F0FD0`), help actions 0x1B..0x33 in detail, `FUN_00504650` armies,
and the sprite frame counts.
