# Difficulty

Status: **verified** from the exe (2026-10-28). `g_difficulty` `0x00F2A988` (i32, 0 VeryEasy, 1 Easy, 2 Normal,
3 Hard, 4 Impossible; text 153:1..5; config default 1 at `0x005C44C0`). It is chosen when a game starts; every
reader below indexes a table by it. Ours: `Game.difficulty`, the map's default unless set (`difficulty NAME` at
any time, see "Difficulty during play"; `python3 -m sim new SAVE --difficulty Hard`, play-mode POST /control {"new": true,
"difficulty": D}). Saves from before 2026-10-28 load as Normal.

## Per map (setup, 2026-10-28)
In the exe the difficulty is a player setting, not map data: both map/scenario loaders (`0x0042B230`,
`0x00511C90`) copy `g_difficulty` before reading the file and write it back after, so a .map/.pak never sets it;
the value comes from the setup screen / config (initial config value 1 = Easy, `0x005C44C0`). Ours (decision 10-28):
each map carries a default in `data/maps.json` (`{"sandbox": {"file": ..., "difficulty": "Normal"}}`, hand-edited;
both sandboxes Normal so the benchmarks keep their numbers). `Game(map)` without a difficulty takes it
(sim/world.py `map_difficulty`); `python3 -m sim new|run|live`, and play mode's File > New (POST /control
{"new": true} without "difficulty") use it; `new --difficulty D` and /control {"new": true, "difficulty": D}
override it. A map file not in maps.json starts Normal. No chooser UI yet (the UI comes later).

## Oracle runs and check (10-30, 1F)
The oracle runs do not play at our sandbox default (Normal): `tools/difficulty_check.py` reads g_difficulty (dump zone
12) from every run's last dump: the Open Play Sandbox runs are at **Easy** (1: the config default 0x005C44C0, the
oracle's --write-dir starts empty; e.g. a trading post costs 160 there, Zeus_Model_Easy.txt row 62), the runs started
from the "See a working city" tutorial at **VeryEasy** (0; the tutorial's own value, the code path that sets it is
not traced). Compare costs, risks, house rules and empire numbers of an oracle run with ours at that level
(`new --difficulty Easy` / VeryEasy).
The same tool compares our tables per level with the exe: model file table 0x0065AF78 (VeryEasy, Easy, Normal, Hard,
Impossible by g_difficulty), every building's cost / fire / damage risk by zeus_id and the whole house table (Catalog
vs Model/Zeus_Model_<L>.txt): equal at every level (the palace's risks since 10-30, below); start funds 0x005F7F08,
workforce 0x006335C4, army factor 0x005EC670 and the tax sentiment columns: equal.
- Palace fire / damage risk (found 10-30, bugs.md 268, fixed 10-30): the exe's model rows give type 0x75 5 / 5 (VeryEasy
  0 / 0, Hard 10 / 10, Impossible 15 / 15) and buildings_fire_collapse_risk 0x00492260 skips only types 0xA9 and 0x3B
  and non-roots, so the palace's root accumulates both risks. tools/build_data.py now takes every monument's risks
  from the model and fireproof from the type table (sanctuaries and pyramids 0 / 0 and fireproof in every model file;
  the palace not fireproof); sim/systems/risk.py burns / collapses it as the exe (buildings.md §8.1).
- House fire / damage risk per level (10-30, bugs.md 293): step 44 reads the building model row of the house's current
  type (2 + level), so manors (13) and estates (14) have their own (Normal 10 / 5). tools/build_data.py puts each
  level's fire_risk / damage_risk into the house table (data/houses.json, data/difficulty.json `houses`).
  The horse ranch's and agoras' model risks were in our data all along; ours just never lit them (bugs 290, 292).

## Where each table lives
| what | exe | ours |
|---|---|---|
| building cost, fire risk, damage risk | `load_zeus_model` 0x005B0C20 reads `Model/Zeus_Model_<difficulty>.txt` | data/difficulty.json `buildings` (only the fields that differ from Normal and that our role overlay does not override) |
| house table (evolve/devolve desirability, culture, tax multiplier, crime, soldiers, disease col 20 (never read)) | same file, house section | data/difficulty.json `houses` (whole table) |
| figure stats (hp, attack, armor, missiles) | `0x005B0E60` reads `Model/Figure_model_<difficulty>.txt` | not used yet: only soldiers, wolves and cattle differ (criminals, watchmen, hunters are the same at every level); extracted/model/model_<d>.json `figures` |
| monster behaviour | `monster_behavior_load` 0x0052F460, `Model/monster_behavior_<d>.txt` | not used (no monsters) |
| tax sentiment | `sentiment_from_taxes` 0x00567120, `Model/Tax_Sentiment_Model.txt` column | data/difficulty.json `tax_sentiment` -> rules.tax_levels[].sentiment |
| tax factor | 0x005F7F1C: 50 % at every level | (constant) |
| start funds | 0x0051D5F0 / 0x005B0660: treasury x `0x005F7F08` [150, 100, 100, 100, 80] / 100 | data/difficulty.json `start_funds_pct` |
| workforce base | `labor_pool_compute` 0x004865A0, 0x006335C4 [50, 45, 40, 37, 35] | rules.workforce.by_difficulty (labor.py) |
| plague deaths | `house_infect_plague` 0x00447F70, doubles 0x005F8480 [1/4, 1/3, 1/2, 2/3, 1] | health.DEATHS |
| empire: attitude changes, army target, requests (money 0x00633340, goods 0x00633318), aid share 0x005EC4E8 | 0x0042D5E0, 0x0042D980, 0x0042CFA0, 0x0047FF80 | sim/empire (relations.diff) |
| god curse months | `god_curse_length` 0x004ED1E0 | not used (no gods) |

All are built by `python3 tools/build_data.py` (data/difficulty.json from extracted/model/model_<d>.json and
tax_sentiment.json; those come from tools/model.py). The base data/*.json stays Normal and hand-editable;
sim/data.py `Catalog(difficulty=...)` applies the overlay at load.

## Difficulty during play (11-01, static reading + oracle dumps)
Status: **verified** from the exe for the handler and the record (oracle check below); the per-value live/once
column is from reading each reader, not from a mid-game oracle change.

### What the arrows do (0x00401EE0)
Options > Difficulty (screen 0x45, draw 0x0059B200) and the episode briefing (screen 0x35) share one arrow
handler, `0x00401EE0` (tables 0x005EFC68 and 0x005EF988, both entries -> 0x00401EE0, arg 0 up / 1 down). Each click,
at once (not when the dialog closes):
1. `g_difficulty` += 1 or -= 1, clamped 0..4.
2. Reloads the per-level files: `load_zeus_model` 0x005B0C20 (g_building_model 10 cols x 0xEA rows, g_house_model 21
   cols), `0x005B0E60` (g_figure_model 0x00786068, 14 cols), `load_tax_sentiment_model` 0x005B10F0 (one file for
   every level: no change), `monster_behavior_load` 0x0052F460, and `0x004E1230` (clamps scenario +0x24 `0x0090294C`
   to <= 9; no other reader by address found, meaning not traced; also run on every map and save load).
3. Only on the briefing screen (0x35): `g_treasury = scenario_start_funds 0x00902948 x start_funds_pct[d] / 100`
   (0x005F7F08). Mid-game (screen 0x45) the treasury is **not** touched.
Closing the Options dialog (right click, screen_input 0x00514C10 case 'E') lowers the least-difficult record (below).
Nothing else is re-applied: no building, house, walker or empire record is rewritten. A value changes mid-game
only if its reader looks the table up when it runs. The save keeps `g_difficulty` (sav rank 12). Loading a .sav restores
it, and FUN_00510ED0 reloads the four model files at that level. Loading a map or campaign .pak keeps the player's
current level (0x0042B230, 0x00511C90).

### Every value that depends on g_difficulty
All 42 code references to `0x00F2A988` in .text are listed below (a byte search of the exe, which also finds the
x87 table reads the decompiler hides). Live = looked up each time it is used, so a change applies at the next use.
Once = computed when something is created and stored, so existing things keep the old value.

| value | exe (reader; table) | live / once | after a mid-game change |
|---|---|---|---|
| building cost | build_commit via model_building_value 0x00433D50 (g_building_model col 0) | live | next placement costs the new price |
| fire / damage risk per building | buildings_fire_collapse_risk 0x00492260 (cols 6/7) | live (adds each step 44) | risk already built up stays; it then grows at the new rate |
| house table: evolve / devolve desirability, culture needed, soldier %, crime base/inc, tax multiplier, disease col (never read) | house_param callers (houses_evolve, taxes_collect_monthly, houses_crime_update, city_military_manpower, ...) | live | houses may evolve / devolve at the next check, tax and crime change next month |
| soldiers', wolves', cattle's hp (death threshold), attack, armour, missile armour; wall/tower sentry missile range/rate/attack; trireme armour/rate | figure_type_value 0x004E1B20 from figure_hit, archer_fire_update, fig_handler_wallguy, fig_handler_ballista, horseman_charge_hit | live | a hoplite already damaged dies earlier if its hp drops (damage is compared with the current model hp) |
| figure +0x128/+0x12C (ship_hp / max), +0x13C speed, +0x140 morale, +0x144/+0x148, +0x158 = attack x 20 / 100 | figure_combat_init 0x0048CCF0 at spawn | once per figure | existing ships keep their hp (trireme hp is the same at every level); the +0x158 use is not traced |
| monster behaviour (aggro rings, rest, rampage months) | monster_behavior_load 0x0052F460 -> 0x00FE42F0 / obj 0x00FE43B0; figure_monster_update | live (table rebuilt by the click) | next monster decision |
| workforce % [50,45,40,37,35] | labor_pool_compute 0x004865A0 (0x006335C4) | live | next labour pass |
| tax factor 50 % | taxes_collect_monthly 0x00488250, taxes_this_year_refresh (0x005F7F1C) | live | none (same at every level) |
| tax sentiment column | sentiment_from_taxes 0x00567120 | live | next sentiment update |
| plague deaths [1/4..1] | house_infect_plague 0x00447F70 (0x005F8480) | live | next infection |
| god curse length | god_curse_length 0x004ED1E0 | once per curse | a running curse keeps its length |
| invasion bribe x [1,3,4,5,7] | invasion_bribe_cost 0x00476CF0 (0x00633280) | live | next bribe offer |
| empire: attitude change | city_attitude_update 0x0042D5E0 (0x005EC528) | live | next event |
| empire: tribute claim, money gift, aid share, request size, army target | 0x0042CDD0 (0x005EC4C0), 0x0042D870 (0x005EC648), city_pick_aid_good 0x0042CFA0 (0x005EC4E8), city_request_choose 0x0042D380 (0x005EC500), 0x0047FF80 (money 0x00633340, goods), city_army_target 0x0042D980 (0x005EC670) | live when computed | requests already made keep their amount |
| start funds x [150,100,100,100,80] % | 0x0051D5F0 (new map), 0x005B0660, the briefing click | once | none mid-game |
| text 153:(d+1) | 0x0059B200, fullscreen_background_d 0x0042F783, 0x0052EC12 (file/briefing text) | draw | |

### "Least-difficult level" record (text 148:8)
`0x00FEB1F8` (i32, inside the city block g_city 0x00FE6A58, sav rank 4, so saved with the game).
- Writers: `0x005B0660` (start of a game from a map file; its callers are 0x004215E0, 0x00427B10, 0x0042FBF0, and
  game_turn's command-line start): record = g_difficulty. Screen 0x45 right-click close: record = min(record,
  g_difficulty). So only the level at the moment the dialog closes counts, not the levels clicked through. The briefing's arrows
  never touch it. `city_record_reset` 0x00566950 (run by 0x005B0990, so by every new city including
  episode_start_load's) zeroes the block, so the record becomes 0 = Very Easy.
- Oracle: every run in re/oracle/runs (campaign, open-play adventures, tutorials; g_difficulty 0 or 1) has the record **0**
  in its first and last dumps. A game started through the normal menus records "Very Easy" whatever the
  player chose, and the min can never raise it.
- Readers: the stats window of screen 0x33 (fullscreen_background_b 0x00422270 when 0x00F2A6DC == 1: text 148:8 then
  153:(record+1)). The per-episode high-score table at 0x00EF61B8 (0x4C per episode index 0x00F2A7B0: score
  +0, name +8, used +0x48, months +0x3C, population +0x34, funds +0x38, record +0x40) is written by 0x004F23C0 from
  the episode-end check 0x004F2460, called by episode_end_save_parent 0x0052D4E1. 0x004230E0 writes a second
  table at 0x006A7EE0. The score is `FUN_005A3D00(months)`, a stub that returns 0, so every comparison is a tie.
  Not found: a path through the normal UI to screen 0x33 with 0x00F2A6DC == 1 (goals_month_check sends a win to
  screen 0x42 and a loss to 0x33 with 0x00F2A6DC <= 0).
  So in this build the record has no visible effect in normal play.

### Ours (11-01)
Every reader in sim/ takes the level from `g.rules["difficulty"]` / `g.cat` when it runs (labor.py, health.py,
military/units.py `stats`, navy.py, invaders.py, forces.py, heroes/monsters.py, gods/month.py, empire/relations.py),
and nothing stores a catalog object on a building or walker. Swapping the catalog (as `episode.set_difficulty` does)
therefore gives the exe's live behaviour for every row above. The exceptions match the exe: our trireme / enemy ship hp
is set at spawn (navy.py), and the curse length is fixed when the curse starts (gods/month.py).
Ported 11-01 (bug 376): `difficulty NAME` (Game.set_difficulty, sim/game.py) works at any time and swaps the
catalog; Options > Difficulty sends it on each arrow click, silently (viewer/play/options.js). It re-scales the
treasury only on a city still at tick 0 with nothing built (ours: the exe re-scales only on the briefing; its
open-play level is chosen before the city exists, and ours has no chooser). A save keeps the level and Game.load
rebuilds the catalog for it (as the exe's FUN_00510ED0); saves from before 10-28 load as Normal.
test_difficulty_mid_game; benchmark hashes unchanged (full 7740f1cf, boom 63ce713a).
Not ported (user 11-01): the least-difficult record, which has no visible effect in this build (above).

### Port plan (done 11-01, step 2 skipped by the user's decision)
1. sim/game.py `difficulty NAME`: allow at any time. Swap the catalog (`episode.set_difficulty` logic: `g.cat`,
   `g.rules`). Re-scale the treasury only at tick 0 with nothing built (ours, as now; mark it "ours" in options.md),
   never later. No other state is touched, as in the exe.
2. Record: `g.least_difficulty`, read with getattr (default = the start level) so old saves and the benchmark
   hashes don't change. Lower it (min) when the Options difficulty dialog closes:
   viewer/play/options.js sends one command on the right-click close (e.g. `difficulty_closed`), not on each arrow.
   Faithful start values: 0 for every start through episode_start_load / the menus (the oracle value). Drawing it
   needs the 0x33 stats window, which the exe never shows in normal play. So: record only, no UI, unless the user
   wants the stats window.
3. Tests: change Hard -> Easy mid-game: next build cost, house evolve threshold, workforce %, hoplite hp threshold
   and request size use the new level; treasury, damage and risk already built up, and ship hp unchanged.
Risks for the benchmark hashes: none expected. scripts/boom.txt and full.txt never send `difficulty`, and the
record is written only by the dialog close and read with getattr. Check with
`python3 tools/state_hash.py full` before and after. The live game (a save) is
not affected until the user opens the dialog. After the change, the first click applies the new level at once.
