# Panhellenic games (Zeus)

Status: RE from the decompile (verified by reading, not yet against the oracle); ported in `sim/systems/games.py`
(10-29). Tests: `tests/test_housing.py::test_games`. Message texts: `Model/Zeus eventmsg.txt` by phrase id
(`refs/zeus-poseidon-arm64/tools/eventmsg.py`; phrase id = position in the exe's name table 0x005FBC38).

## What happens
Every year in June the city is called to the games of that year. The year type is `t = Y & 3` with
`Y = year (+1 from month 8 on)` (two's complement on the signed year, e.g. 1000 BC = -1000, t 0):

| t | games | disciplines (buildings, table `0x00641E80`) | monument when won |
|---|---|---|---|
| 0 | Olympian | college 77, gymnasium 79, stadium 80, drama school 78 | 4 Athlete |
| 1 | Isthmian | college 77 (philosophy) | 9 Scholar |
| 2 | Nemean | gymnasium 79, stadium 80 (athletics) | 4 Athlete |
| 3 | Pythian | drama school 78 (drama) | 9 Scholar |

An Olympian win makes the city the **host** of the next Olympian Games (home games).

## Schedule (exe)
- `month_advance`: `scenario_events_monthly` (all events, with the old month), then `month += 1`, then
  `FUN_00565950` (ECX = games record) when the new month is 5 (June).
- `FUN_00565950`: Zeus games only (`poseidon_game() == 0`), scenario games offset `0x00902C50 != -1` and
  `year >= scenario_start_year + offset`. **Open-play sandbox: 0** (oracle dumps rotation-walls, rotation-cliffs;
  the working-city tutorial has -1 = no games). Then:
  - `FUN_00565A80` qualifies → allocates event type **35** (month 5) and dispatches it at once, and event **37**
    (month 7: it fires at the end of August, in the monthly pass before month becomes 8);
  - else event **36** (month 5), dispatched at once.
  Events are ordinary scenario events (`month_events_dispatch` 0x0046DFD0; `events_date_check` 0x00471F00: the
  event's year and month, not yet done (`+0x28 & 0x20005`)); each handler sets `+0x28 |= 4` (done).

## Games record `0x00FE6908`
| off | meaning |
|---|---|
| +0 u8 | host: won the last Olympian Games, this Olympian year is played at home (cleared by event 36, an Olympian non-win, a new map: `city_init_from_map` 0x00511E30) |
| +4 i32 | result: 0 lost, 1 second, 2 won (`FUN_00565E90`) |
| +8 u8 | games season (begin → conclude); read only by UI (stadium draw `0x0044CD10`, an info text) |
`0x00FEB418` = 1 after any win (event 37 with result 2): Hercules' requirement 6 (heroes-monsters.md).

## Qualify `FUN_00565A80`
Counts `0x00782888[type]` = alive buildings of the type with workers > 0 (`0x00491820`, cycle).
Home games (t 0 and host): a staffed stadium. Else: t 0 any of college + drama school + gymnasium + stadium;
t 1 a college; t 2 gymnasium + stadium; t 3 a drama school.

## Event 35 begin `0x0046E1A0`
Message 0xE0: home games 0x4C4 "Home Games begin" (at the first staffed stadium's road access), else
t 0 0x4B0 Olympian / 1 0x488 Isthmian / 2 0x474 Nemean / 3 0x49C Pythian "... Games begin" (at the land exit);
stinger S_games (`FUN_005A1210(7)`). Then:
- `FUN_00565B30`: `+8 = 1`; home games → `FUN_00566290`; else every alive, staffed building whose type is in the
  year's row gets **one contestant** (figure 0x38) at its road access: action 6, timer `(rng & 0x1F) * 2`,
  `building_id` = the building, `resource` = its type.
- `FUN_00565E90` result: `c = FUN_00565E30(FUN_00565D40(t))`; `rng_15 % 100 < c` → 2 won; else `c < 30` → 0 lost;
  else 1 second.

### Chance `FUN_00565D40(t)`
Coverage `0x0091EA74/78/7C` (`FUN_00566A90`, cycle step 33): % of the house population whose house has
philosophy (+0x6D) / athletics (+0x6F) / drama (+0x71) coverage. With staffed counts n[type]:
- S1 philosophy = cov_phil/4 + n[college 77] + n[podium 81]
- S2 athletics = cov_ath/4 + 5·n[stadium 80] + n[gymnasium 79]
- S3 drama = cov_drama/4 + n[drama school 78] + n[theatre 82]
- A = 20 when Apollo's sanctuary is active (`god_sanctuary_active` 0x004E9440 on god record 3 = 0x00EF5E74)
- t 0: A + (S3 + S2 + S1)/3 + 4·n[80]; t 1: S1 + A; t 2: S2 + A; t 3: S3 + A (integer division).
`FUN_00565E30(c)`: if Hercules' Hall stands (hero record 1, 0x00F0E504), he was not sent for, requirement 6
(a games win) is not met and c ≠ 0: `c = ftol(c² · 0.16)` (double at 0x005E4800).

## Event 36 cannot participate `0x0046E400`
Message 0xE0: home games 0x4CA "City Games cancelled" (no working stadium), else 0x4B6 / 0x48E / 0x47A / 0x4A2
"<name> Games" (no contestants). Host = 0, result = 0.

## Event 37 conclude `0x0046E5A0`
Message 0xE0 by result (won / second / lost): home 0x4D1..0x4D3 (title 0x4D0 "City Games End"), else
0x4BD.. (0x4BC Olympian), 0x495.. (0x494 Isthmian), 0x481.. (0x480 Nemean), 0x4A9.. (0x4A8 Pythian) "... conclude".
Result 2 → `0x00FEB418 = 1`. `+0x28 |= 4`. Then `FUN_00565FC0`:
- `+8 = 0`; hosting = t 0 and host (as it was).
- Won: t 0: if host → `games_victory_rewards` 0x005666D0 (every in-use, active city of class 0..4 attitude +20,
  history 0xD81 "your city hosted the games"; **city sentiment +15**, not clamped); host = 1. Grant
  (`FUN_00402B00`) 4 for t 0, 2; 9 for t 1, 3. `FUN_00566760(t == 0)`: every in-use, active, visible city: class
  0 ally / 2 rival +5, 1 vassal / 3 parent / 4 colony +10, +10 more in an Olympian year; history 0xD80 / 0xD7E /
  0xD7D / 0xD7F (won the olympian / isthmian / nemean / pythian games).
- Not won, t 0: host = 0.
- Hosting → `FUN_005664F0`; else every alive, staffed building of the row gets a contestant at the **land exit**
  (`g_land_exit`), action 8, timer `(rng & 0x1F) * 2`: they walk home.
Text note: the home-games "second" / "lost" messages say popularity rose; the code rewards only a win.

## Home games
- Begin `FUN_00566290`: local contestants (one per staffed building of row 0) action 10 timer 0 (to the stadium);
  visitors: for each type k of row 0 (77, 79, 80, 78), 10 contestants at the map entry or the land exit
  (`rng & 1`), action 10, timer `49 i + 11 k`, resource = the type.
- Conclude `FUN_005664F0` (only with a staffed stadium, `FUN_00568700(1, &b, 0x50, 0xB)` = first alive staffed
  stadium): locals at the stadium's road access, action 8, timer `79 · (index in row 0)`; visitors there, action 6,
  timer `29 k + 50 i`.

## Contestant figure 0x38 `fig_handler_contestant` 0x004C30D0
Speed code 6 (`Figure_model` col 8: 15 ticks a tile), route mode 0 (people over land). Each tick: anim frame +1
(0..11). Actions: 6 / 8 / 10 = wait `timer` ticks hidden (`+0x65`), then dest = 6: map entry or land exit
(`rng & 1` = 0 → entry), 8: the home building's road access, 10: the first staffed stadium's road access (none:
removed); walk (7 / 9 / 11); arrived (direction 8) or gone (10) → removed; no route (9) → route freed, try again.
4 dying, 5 fighting (generic). Sprite by resource: 77 / 81 group 0x66F1, 79 group 0x66D7, 80 group 0x66D9,
else (78) 0x6603; frame = direction (minus view) + 8 · anim frame.

## Ours (sim/systems/games.py)
All of the above except: the hero hall factor (no heroes yet: later, heroes wave), the stinger, the UI uses of
+8, contestant fighting/dying (they are never attacked here), event-record bookkeeping (one pending conclude
year instead of the scenario event list). Contestants: role `contestant`, `task` = discipline building key,
state `wait<action>` (hidden: `export.walker_anim` → "hidden") then `go`; no route → retry every 51 ticks.
Messages: the exe's own (title + announcement by the phrase ids above, data/messages.json from
tools/build_messages.py, sim/messages.py; [player_name] = "Ruler"); the grant adds none. World-city attitude goes through `sim/empire`
(`relations.attitude_add`, history line); none without an empire. `OFFSET = 0` (the sandbox value); scenarios
with their own offset: later. Poseidon games (hippodrome) are not part of this.
Play mode: drawn as the exe (bugs.md 198): walkers.json `contestant` resolves by `good` (= w.task, export) to
`contestant_philosopher` (0x66F1, SprMain 12128), `_athlete` (0x66D7, 10588), `_competitor` (0x66D9, 10692), `_actor`
(0x6603, 105), written by tools/play_contestants.py; waiting ones hidden. Check: tools/contestants_check.mjs.

## Open questions
- Oracle check of a whole games year in the sandbox (timing of the messages, contestants' routes) not done.
- Whether a stadium's second half (type 0x50, parent_part != 0) counts in `0x00782888[0x50]` (it has no workers:
  assumed not).
