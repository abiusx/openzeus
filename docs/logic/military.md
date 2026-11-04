# Military: soldiers, companies, combat, defences, invasions

Status: **verified** from the exe unless marked. Oracle evidence for soldiers: re/oracle/scenarios/military-mobilize.txt
(run re/oracle/runs/mil-a, read with tools/oracle_military.py). Addresses refer to GOG `Zeus.exe`.
Struct fields: `re/structs/military-sentiment.tsv` (struct `Formation`, plus Building/Figure fields).
The military-service effect on sentiment is in [sentiment.md](sentiment.md) (component 6).

## Summary
Soldiers are not walkers born in houses. The houses set a **target** number of soldiers by type:
- common houses: rabble/archers;
- elite houses: hoplites, limited by the armor they hold;
- Estates: horsemen, limited by armor and horses.

Each cycle the Palace's soldier slots spawn or dismiss figures to meet the target, grouped in
**companies** (`figure_groups`, max 8 figures). The player mobilizes companies ("call to arms").
Mobilized companies in peacetime lower sentiment. One soldier figure away from home removes
6 people from the labour force.

Combat is deterministic except for the enemy "special tactic" roll. The melee hit rate is fixed
(one hit per 24 fight ticks). Damage per hit is `A − A*D/20` (A attack, D armor, armor capped at
19), summed in a damage counter until it exceeds the figure's HP. Morale is per company and drops
when members die. Below a model threshold an enemy company stops attacking and falls back.

## Data
- Figure model: `Figure_model_<difficulty>.txt`, 78 rows at `0x00786068`
  (`g_figure_model`) and 66 enemy rows at `0x007851F8` (`g_enemy_model`), 14 × i32 each
  (`extracted/model/model_*.json` "figures"/"enemies"). There are 11 enemy armies of 6 rows each,
  so the army stride is 0x150 bytes. Rows within an army: 0 infantry, 1 missile, 2 cavalry,
  3 warship, 4 transport, 5 unused.
- Player rows (Normal): 0xB rabble/archer hp 80 atk 4 arm 0 marm 1 matk 6 range 10 rate 80
  speed 8; 0xC hoplite 140/12/6/5; 0xD horseman 240/15/4/4 speed 12; 0x27 wall sentry
  100/5/0/4, matk 8 range 10 rate 60; 0x2E tower sentry 120/6/0/5, matk 60 range 13 rate 100;
  0x39 trireme 300/80/3/6, matk 15 range 8 rate 60; 0x3D watchman 20/6/1/1.

### Column accessor `figure_type_value(fig, col)` `0x004E1B20` — verified
Columns: 0 unit_type, 1 hp, 2 attack, 3 armor, 4 missile_armor, 5 missile_attack, 6 missile_range,
7 missile_rate, 8 speed, 9 frequency, 10 defensive_morale, 11 special_pct, 12 special_range, 13 unused.
```
grp = fig.formation (+0x60)
if grp and group[grp].herd_kind (+0x69) != 0: grp = 0
elif grp and group[grp].army (+0x6A) > 10: group[grp].army = 10
col 0: god 0x43 -> 10 - (god_record[fig+0x0B].byte0 != 1); monster 0x44 -> 8 or 7 (0x00586E70)
switch fig.type:
  0xB, 0xC, 0xD, 0x45 (hero): v = FIG[type][col]
      if col == 4 (and a second col id 0x12) and god record 8 (0x00EF5F78) sanctuary finished: v += 4
  0x13..0x15 (caravans): v = FIG[type][col]; if col == 8 and god record 7 (0x00EF5F44) finished: return v*150/100
  enemies (row = ENEMY[group.army]): 0x29 infantry -> row 0, 0x28 missile -> row 1,
      0x2A cavalry -> row 2, 0x40 warship -> row 3, 0x3F transport -> row 4
  0x2E tower sentry: v = FIG; if Poseidon and building(fig+0x5A)+0xC4 & 0x20 and col in {2,5}: v = v*150/100
  0x39 trireme: crew% = b.workers(+0x40)*100 / model_building_value(b.type, 5)
                (0 if b+0xDA set or workers <= 0); crew% -> 100 if 100, 75 if >= 76, 50 if >= 51, else 0
      col 2/5: v = crew%*v/100 (then the same Poseidon ×150/100 rule); col 8: v = max(3, crew%*v/100)
  0x4C cattle: col 2 and fig+0x0B == 2 (bull): v + 5
  default: v = FIG[type][col]; if col == 8 and god record 7 finished and type in {4,9,0x1C,0x24}
      (and the figure is not escorting a 0x41/0x3E figure): return FIG[type][8]*133/100
if col in {3, 4} and v > 18: v = 19          # armor cap
```
Figure init `0x0048CCF0`: `+0x128` = `+0x12C` = hp (ships), `+0x13C` = col8, `+0x140` = col10,
`+0x144` = col12, `+0x148` = col13, `+0x158` = attack*20/100.

## Recruitment

### Targets `houses_capacity_totals` `0x00567910` — verified
Runs at cycle step 13 only while no enemy unit and no enemy warship is alive
(`g_enemy_units_alive 0x00FEB084 == 0 and g_enemy_warships 0x00FEB3EC == 0`), on the house list
`0x0091F5B8`. The name `houses_capacity_totals` in `00-arm64.tsv` was a guess. It is renamed
`military_recruit_targets`.
```
rabble = hoplites = horsemen = 0
for each house b in list:
    s = ceil(b.population (+0x1C) * house_param(L, 5) / 100)
    type 2, 3, 9, 10, 11: nothing
    type 4..8 (common):  rabble += s
    type 12, 13:         hoplites += min(s, min(b.arms (+0x6A), house_param(L, 13)))
    type 14 (Estate):    a = min(b.arms, col13); h = min(b.horses (+0x72), col6)
                         horse = min(s, h, a)
                         hoplites += min(s - horse, a - horse); horsemen += horse
rabble = ceil(rabble / 6)
target soldiers: rabble -> 0x00FEB424, hoplites -> 0x00FEB428, horsemen -> 0x00FEB42C
target companies: ceil(n / 8) each -> 0x00FEB44C, 0x00FEB450, 0x00FEB454
if g_formations_total (0x00FEB43C) >= 20: budget of 20 companies spent from horsemen down to rabble
if no palace (0x00FEAEDE == 0): g_months_no_palace (0x00FEAEA0) += 1; at >= 5 all targets = 0
if palace but no road entry (0x004A3D40 fails): all targets = 0
```
House model col 5 = soldier %, col 6 = max horses, col 13 = max armor
(see [housing-evolution.md](housing-evolution.md)).

### Spawning / disbanding `cycle_formations_pass_14` `0x00567C70` — verified
Cycle step 14, same guards as above. It uses no RNG.
1. No palace (`0x00FE91E8 == 0`): disband all companies 1..20. Members get state 2, then
   `formation_free` `0x004DE980`.
2. Too many companies of a type (processed 0xD, 0xC, 0xB; counts `0x00FEB540/53C/538` vs targets):
   free the excess, each time the company with fewest members, ties to the higher index, among
   those with `+0x03 all_home` set.
3. Too few soldiers (counts `0x00FEB438/434/430` vs targets). Walk the palace parts that are
   soldier slots (`0x00542610`, part class 5 or 0x6D). First fill existing same-type companies
   that are in the city (`+0x82 < 0`) and have ≤ 7 members, one figure per part per pass,
   repeating while there is progress. New figures get `fig.formation = id`. If the company is home
   they also get `+0x63 = 1`, `+0x65 = 1`, action 6; otherwise they spawn at the company with
   action 9. Then create new companies (`formation_create_company` `0x004DDA00`, first free slot
   1..20) on free parts, up to 8 figures each.
4. Too many soldiers: walk the palace parts in reverse. A member in action 6 gets state 2; any
   other gets action 3 (go home).
5. At `month_tick == 2`: sanctuary companies 31..34 are created when the sanctuary is ≥ 100 %
   built (`0x0053ECA0`). Artemis (god id 4, building 0x58) gives type 0xB in 31/32; Ares (god
   id 5, building 0x59) gives type 0xC in 33/34. They then gain one figure per call up to 8.
   Detail (decompile 11-01): 31 / 33 stand on the sanctuary's first soldier-slot part, 32 / 34 on the second; the
   first figure is made at once; a company in use with fewer than 8 whose building (+0x06) is no longer a 100 %
   monument loses every member (state 2); a full one is not checked. formation_create_sanctuary 0x004E30F0: morale
   100, +0x93 ready, +0x94 = 1, +0x48 = 4 (Artemis) / 0 (Ares), banner +2 = slot - 1 (138:30..33). Ours:
   sim/systems/military.py sanctuary_companies (bugs.md 368).

### Counters `formations_count` `0x004DDD70`, `formations_refresh` `0x004DE210` — verified
`formations_update` `0x004DDD30` runs them at cycle step 5 (arg 0) and step 29 (arg 1).
For every in-use company 1..20:
- `0x00FEB538/53C/540` count companies of type 0xB/0xC/0xD;
- `0x00FEB440/444/448` count the same with `+0x90 mobilized` set. These feed the sentiment;
- `0x00FEB43C` counts all companies.

`formations_refresh` sums soldiers by type into `0x00FEB430/434/438`. Soldiers of companies with
`+0x03 == 0` (not all home) also go into `0x00FEB458/45C/460`. The labour force (`0x004865A0`)
loses `6 * 0x00FEB458`, i.e. 6 workers per rabble soldier away from home. Elite houses get
`b+0xE4` = their share of the absent hoplites + horsemen (`0x004FF8D0`, `0x004FFA60`), filled
house by house.

## Companies (`figure_groups`, struct `Formation`, 100 × 0x9C at `0x00DB7B40`)
Slots: 0 unused; 1..20 palace companies; 21..30 event troops (`0x004E2AC0`: mobilized at
creation, `+0x78` = scenario event, `+0x94` = 1; hypothesis: allies/reinforcements);
31..34 sanctuary troops (`0x004E30F0`); 35+ animal herds and enemy groups (`0x004DDB80`).
Enemy companies: `+0x42 == 0 and +0x94 == 0 and +0x69 == 0`. Full layout in the struct TSV.
Main fields: `+0x04` figure type, `+0x08` 8 member ids, `+0x28` count, `+0x2C` morale (i16 0..100;
50 for new palace companies, 100 otherwise), `+0x6A` army index (enemies), `+0x75` AI countdown,
`+0x82` abroad (−1 = in city), `+0x90` mobilized, `+0x91` mode, `+0x92` selected, `+0x93` ready.

### Mobilization — verified
- Player order: sets `+0x90 = 1` and gives a move order (`0x004DD250`). Send home (`0x004DD8D0`)
  clears `+0x90`; members get action 7. A soldier of a non-mobilized company is put back at the
  palace (`0x004B11C0`).
- Auto-defend `formations_auto_defend` `0x00568D20` (from `month_advance` when the option
  `0x00F2A990` is on and `months_to_next_invasion 0x00FE957C == 1`). It selects up to 20
  companies: first 31..34, then horsemen, hoplites, rabble. Each must have `+0x82 < 0`, `+0x93`
  set and `+0x92` clear. Each selected one gets `+0x90 = 1`, mode 0 (`0x004E2100`) and a move
  order. The selection list is `0x007818E4` (count `0x00782884`, max 20).

### Morale — verified
- `formation_morale_add` `0x004DE080`: clamp 0..100; skipped when `+0x94 != 0`.
- Member death (`formation_member_lost` 0x004DDFF0, from figure_hit and the other killers right after the hit):
  `formations_refresh` first, then morale += `[-30,-30,-30,-25,-18,-12,-8,-5][clamp(+0x28 - 1, 0, 7)]`, where
  +0x28 counts the company's figures with state 1: the one just hit and the dying ones (state 1 until removed,
  127 ticks) count, and a palace company's soldiers at home too (11-03, oracle 1B-inv-city company 1: 100 -> 95
  (death, 8) -> 90 (8: one dying) -> 74 (two deaths in one tick, 7 each: -8 -8) -> 49 (4) -> 24 (4) -> 0).
- Waver (`formations_morale_waver` 0x004DDF20, `formations_update(0)` = cycle step 5 only), formations 1..99 in
  index order, skipping herds (+0x69) and +0x94 companies: a palace company (+0x42 = 1) that is on the map
  (+0x03 all_home 0) and not away (+0x82 < 0), or any other company (+0x42 = 0: the invaders), with morale < 21:
  the first time (+0x73 and +0x66 both 0) its own side -3 and the other side +3 (FUN_004DE0E0: every in-use
  formation with +0x42 != 0; FUN_004DE120: +0x42 == 0 and +0x94 == 0; both through formation_morale_add), then
  +0x73 + 1 (morale < 11) or +0x66 + 1 (11..20) on every pass (u8). Oracle 1B-inv-city: company 1 at morale 0
  from dump 1128: companies 2..16 at home 100 -> 97 at 1159, +0x73 1, 2, 3 at 1159 / 1210 / 1261.
- Readers of +0x73 / +0x66: the invaders' AI only (enemy_company_ai_update: either nonzero -> every member not in
  action 3 / 4 / 5 gets action 3, route freed: the company leaves the map; morale_check / go_attack / special_roll
  touch members only while +0x73 == 0 and +0x66 < 2). Other writers: +0x66 = 1 when the AI found nothing to attack
  for 49 days (+0x68 > 0x30), god_leave_release; +0x73 = 3 in city_army_sent_home 0x00481E80 (bribe / withdraw).
  A palace company's counters are only cleared (fig_handler_standard's not-ready branch, 0x0050EB90).
- **A palace company never routs.** `+0x93` (ready) is written 1 only (formation_create_company / _event /
  _sanctuary, fig_handler_standard, 0x0050EB90; scan of every absolute write, 11-03); readers 0x00405EB0,
  0x004B1630, 0x004B1780, 0x004DD0F0, 0x00525120, military_recruit_pass. Oracle 1B-inv-city: company 1 stays
  mobilized and ready at morale 0 and fights to its last member (dump 1279). Ours before 11-03: below 21 the
  company routed home (no exe source).
- New palace companies start at 50 (formation_create_company 0x004DDA00: +0x2C = 0x32); a save's companies keep
  their saved morale, +0x93 and counters (sim/savimport.py `_companies`).
- Ours: sim/military/morale.py (add, member_lost, waver at step 5, refresh); forces.died and invaders.died.

### Soldier deaths cost the city (`figure_delete` 0x004DA250, types 0xB/0xC/0xD) — verified (decompile 10-28)
A member (figure flag 0x10, never cleared for soldiers) is freed from its company slot (a member in slots 0..3
is replaced by the first live one of 4..7). Then, only for a palace company (`Formation+0x94 == 0`; 1 is set by
`formation_create_event` 0x004E2AC0 and `formation_create_sanctuary` 0x004E30F0, so event and sanctuary troops
are free):
- rabble 0xB: `population_sub(house_deaths(6, 0))`: 6 people die from common houses, from the deaths cursor
  0x00FE9174 (as the yearly deaths, population.md);
- hoplite 0xC / horseman 0xD: `FUN_004CDC50` picks a house (the next one from the shared cursor 0x00FEB0E8 that
  could field that soldier type, the same picker that places mobilized soldiers and sends them home; **not** the
  soldier's own house): it loses 1 armor (+0x6A), a horseman also 1 horse (+0x72), and 1 resident (`population`),
  `population_sub(1)`. No such house: the palace's fields are decremented instead (exe quirk).
A soldier going home is not deleted (FUN_004B11C0: hidden at the home's road entry, action 6), so only a death
(action 4 -> state 2) or a soldier with nowhere to go (FUN_004B1330, picker -1) is charged.

House picker `FUN_004CDC50(fig) -> (road x, road y, building)`: houses in state 1, road access, residents > 0;
rabble: a common house (type < 9 or > 14) whose level has a soldier share (house_param col 5); horseman: type 0xE
with horses > 0 and armor > 0; hoplite: type > 0xB and armor > 0, but not a 0xE that could field a horseman
(horses >= 2 and armor >= 2, or horses == armor == 1, or horses >= 2 and armor >= 1); 3999 steps max.

Other readers/writers of house armor (+0x6A) and horses (+0x72) (`grep -n "\.arms\b\|\.horses" re/decomp/zeus.c`):
- 9501 `agora_order_set` 0x0040CE00: `arms = 0` is the per-good stock clear for good 0xE (armor) of the building
  whose order changes (the +0x6A slot holds armor for the storage/agora buildings that order it; hypothesis: same
  field reused, not a house write);
- 10087..10420 `buyer_goods_list` / `buyer_pick_goods_source`: a house buyer wants armor while arms == 0 / < 200;
- 53046..53199 `FUN_0044C4A0` / `FUN_0044C940` (city_draw 60861): elite-house extras, up to 4 horse pictures
  (horses) and arms/2 armor pictures, scaled by house_param cols 7 / 0xC; 60707 city_draw: neither -> none;
- 89205..89458 `house_requirements_met` / `house_evolve_reason_panel`: evolve needs (armor, horses);
- 136352..136369 `FUN_004CDC50` (above); 145111/145113 `figure_delete` (above);
- 170500..170571 `elite_hoplites_count` / `elite_horsemen_count`, 224153 `FUN_00563180` (a house's split into
  hoplites / horsemen by min(horses, armor) and its soldier share), 226978..227000 `city_military_manpower`:
  recruitment counts (sim/systems/military.py `targets`); 261498 debug panel.

Ours (10-28): sim/military forces.died -> `charge_death`: `health.house_deaths(g, 6)` (rabble) or
`housing.lose_soldier(g, b, horse)` on `forces.pick_house` (the same round robin as `house_tile`); no house: city
population - 1 only. Test: tests/test_military.py `test_military_deaths_cost_the_city`.
- Step 5 (`0x004DDF20`): see "Morale" above (11-03: its own side -3, the other +3; was written the other way).
- A move order at morale < 21 raises message 0x22.
- 0x0050EB90 (from FUN_00510ED0, a load-time fix-up): in peacetime every company gets `+0x93 = 1`, its counters
  reset and +80 morale.

## Combat

### Contact `0x004D4DA0` — verified
When a figure enters a tile it walks the tile chain (`+0x08`, ≤ 1000 steps). It fights the first
figure for which `g_hostility[my unit_type*11 + their unit_type]` (`0x00639430`, 11×11 u8) is set
and which has state 1, is not dying (action 4), and does not already have 2 opponents in action 5.
A horseman (0xD) in action 0x10 (charging) instead calls `horseman_charge_hit` and returns to
the action saved in `+0x140`.

### Fight `figure_fight_start` `0x004D4BA0`, `figure_fight_tick` `0x004D5F10` — verified
Start: `a.saved_action (+0x10) = a.action`; `a.action = 5`; `a.opponent (+0x90) = b`; set facing
`+0x13`. b enters action 5 with the opposite facing and records a as opponent 1/2 (`+0x8C`/`+0x8E`,
count `+0x8B`). Not started if b is a trireme whose building has `+0xC4 & 1`.
Tick (called by every fighting walker handler): `+0x6A += 1`. If `0x004D5BC0` (god/hero/monster
special) returns 0 and `(u8)+0x6A > 23`: `figure_hit(fig, fig.opponent, 0)` and `+0x6A = 0`.
When the opponent dies the figure switches to the other one. With none left, `0x004D61B0`
restores `action = +0x10`.
Per tick, in detail (11-02, bug 393) [v]: first `tile_progress < 6` -> +1 and a fine step (it closes in). Count 0 ->
fight_end. Count 1: the opponent must be state 1 **and in action 5** (fighting anyone; a hero 0x45 in action 7 or
flagged 0x10 ends it too), else fight_end. Count 2: an opponent that fails that test is replaced by the other recorded
one (`+0x8C` / `+0x8E`), count 1, if that one passes; else fight_end. Only then `+0x6A += 1` and the hit. So: the
check runs **every tick** (a foe killed by someone else ends the fight, or switches it, the next tick, not at the
next hit), the attack timer is **not** reset by a switch (the next hit stays on the fighter's own 24-tick cycle), and
the killer of its last foe ends the next tick with `+0x6A` = 0 (its hit reset it). fight_start resets `+0x6A` of
the mover and of b only if b was not fighting; `anim_frame` of the mover only (b's counter runs on). fight_end
(0x004D61B0) does not reset `+0x6A`. `FUN_004DB3D0(fig, 0)` called by fight_start and by handlers at fixed timer
values is the **attack sound** (by figure type; 0x28..0x2A per army via 0x004DC560), not the hit.
Ours (sim/military/units.py, 11-02): the hit at busy_until = start + 24 k (timer = (tick - start) % 24, the first
fight tick the tick after the start); `kill` / `end_fight` wake the figures fighting that one for the next tick
(`wake_attackers`); a switch keeps busy_until; after its killing hit a fighter resolves the next tick; hooks
`fight_started` / `melee_wake` / `melee_tail` give the owning module its handler's own action-5 rules. The figure
order within a tick and the closing-in: ported 11-02 ("In-tick order, closing-in, re-aim timer" below).

### Hit `figure_hit(att, tgt, from_missile)` `0x004D54D0` — verified
```
if att.type in {0xB, 0x27, 0x28, 0x2E}: A = val(att,5); D = val(tgt,4)   # missile attack vs missile armor
else:                                   A = val(att,2); D = val(tgt,3)
# overrides: criminals 0x17/0x1B/0x1D vs hero 0x45 -> A=D=0; wolf vs hero or bull -> 0;
#   god vs non god/hero/monster -> A=9999, D=0; hero vs wolf/criminal -> A=9999
if att and tgt both in groups:
    ma = group[att].mode (+0x91); mt = group[tgt].mode
    if ma==1 and mt==2: A = A*150/100
    if ma==0 and mt==2: D = D*150/100
    if ma==1 and mt==0: D = D*150/100
# monster 0x44 with col0 == 8: float path via __ftol (not decoded)
dmg = 0 if A == 0 else max(0, A - (D*A)/20)        # C truncation
if tgt.type in {0x19 fishing boat, 0x39 trireme, 0x3F, 0x40 enemy ships}:
    hp = tgt.ship_hp (+0x128) - dmg
    if hp < 1: +0x128 = 0; action 4; +0x36 = 0; die (0x004DAB30); group_member_lost
    else: +0x128 = hp
else:
    tgt.damage (+0x98) += dmg
    if tgt.damage > val(tgt,1) and figure_can_kill(att,tgt) (0x004D53D0):
        tgt+0x10C |= 0x10; action 4; die; group_member_lost
```
Note that rabble (0xB) uses its missile values even in melee. Damage is never healed during the
fight: the only reset of `+0x98` found is at `0x004C91EA`, a function whose role was not checked.
`figure_can_kill` blocks kills of gods and heroes. Monsters with col0 == 8 can be killed only
by 0xB/0xC/0xD/0x3D/0x27; other monsters only by enemies 0x28..0x2A.

### Horseman charge `horseman_charge_hit` `0x004E1080` — verified
```
if att != tgt and tgt+0x0F != 1:
    A = val(att,2); Arm = val(att,3)                     # the attacker's OWN armor (disasm-checked)
    if 5 < att.charge_tiles (+0x134) < 20: A <<= 2
    dmg = 0 if A == 0 else max(0, ((30 - Arm) / 20) * A)  # integer: (30-Arm)/20 is 1 for Arm<=10, 0 for 11..19
    tgt.damage += dmg; if > val(tgt,1): action 4, die, group_member_lost (no can_kill check)
```
Charge movement `0x004D0B30`: each new tile in the same direction does `+0x134 += 1`; a turn
resets it. Speed is `min(2*col8, 18)` while `+0x134 < col10`, then col8.

### Missiles — verified
- Archer/rabble `0x004B2F70`: `+0x6B += 1`; when `> col7` reset it, pick a target with
  `missile_target_search(fig, col6)` `0x00501940`, and set `+0x6A = 1`. While the target is
  within Chebyshev distance col6: at `+0x6A == 7` launch projectile 0x2D (`0x004D9D70`) and set
  `group+0x5C = 6`. `+0x6A` keeps counting and wraps after 100.
- Target search: figures 1..1999, state 1, not action 4, `+0x65 == 0`. If `group+0x8C > 0`
  (target company), only its members (transports exempt). Priority: enemies 0x28..0x2A and
  monsters (col0 8) 50, warship 30, transport 20 (40 if `+0x130`), wolf 10. A candidate replaces
  the best only if its priority is strictly higher **and** it is strictly nearer (the best
  distance starts at the range). Line of fire is required (`0x004D9B80`).
- Projectile 0x2D (`0x004BACE0`): `+0x5A` = shooter; `+0x39 += 1` (from 15: figure_create), marked gone past 120
  (106 calls). Moves 4 fine units a call (`0x004D9750`). On a figure (`0x004DCE00`): `figure_hit(shooter, it, 1)`,
  sets `group[tgt]+0x5E = 6` and `+0x60 = shooter's group`, then expires. The piercing variant under `0x00777286`
  (`+0x92` hit counter) is Poseidon's (off in ours). The enemy projectile 0x34 (`0x004BD970`): see "Missile flight"
  below (settled 11-02).

### Enemy company AI `0x004FFFD0` (cycle step 29 via `0x00500910`) — verified
`+0x75 -= 1`; when ≤ 0, by mode `+0x91`:
- mode 0 (defend/regroup): `special_roll`, else `go_attack`;
- mode 1 (attack): `morale_check`, else `special_roll`;
- mode 2 (special): `morale_check`, else `go_attack`;
- other: mode = 1.

The three helpers:
- `morale_check` `0x004FFC10`: if `morale < ENEMY[army].row1.col10`, mode 0, `+0x75 = 6`, and
  units 0x28..0x2A get action 7 (hold and regroup, not a retreat: see "Invaders on the map").
- `go_attack` `0x004FFD00`: if `morale >= threshold - 20`, mode 1, `+0x75 = 4`.
- `special_roll` `0x004FFE00`: one `random_next` (history push of `0x00F137D4`, 31 steps of both
  LFSRs). It succeeds if `(rand_b & 0x7FFF) % 100 < ENEMY[army].row1.col11`, then mode 2,
  `+0x75 = 6` and a new layout `+0x2A`.

The morale threshold and special % always come from the army's **missile row** (row 1).
`0x00501ED0(army)` returns col 9 (frequency) of rows 0..2, which is the army composition.
The only other RNG in combat is the CRT `rand()` in `0x004DB3D0`, which picks sounds only
(non-simulation).

## Defences (cycle step 31, `buildings_spawn_walkers` `0x0048CFB0`) — verified
- Tower (building 0x84): `staff% = b.workers*100/col5`. It needs the palace (or
  `g_months_no_palace > 3`) and its road access tile `+0x26/+0x28` on the palace's road network (same id in
  `g_grid_road_network` `0x00C4F288` as the palace's road access tile; labor.md §2). Ours: sim/systems/labor.py
  (`b.network == palace.network`; the no-palace grace compares with a freed palace record, read as "no workers").
  - staff > 50: keep a tower sentry (0x2E) in `b+0xB6`;
  - staff ≥ 100: also keep a wall sentry (0x27) in `b+0x2A`, created at (x, x). The exe pushes
    `b+0x06` twice; that is an exe bug, kept.
- Wall drag `walls_drag` `0x0049AF50` (verified 2026-10-28): a straight rectangle, the long axis from start to
  end, the short axis clamped to the start row/column plus at most one (drag sideways by one = a 2-thick
  wall). Each tile gets a wall if `terrain & 0x1537166F == 0` (no road 0x40, building 0x8, tree, rock,
  water, rubble, beach, marble, reeds, cliff…), no blocking tile object, inside the play area, no map
  marker and no walker other than types 24/6; other tiles are skipped silently (a road is never walled:
  that is what the gatehouse is for, buildings.md §5). Cost per wall tile.
  Axis (decoded 10-28): coordinates are clamped to the map; if |dx| > |dy| the rectangle runs along x and the
  end's y is clamped to start y ± 1, else (ties included) along y with the end's x clamped to start x ± 1;
  then x and y ranges are sorted and the rectangle walled row by row. Ours: `Game.wall_tiles` (the `wall`
  command and the play-mode ghost).
- Walls: tiles with terrain flag 0x4000 (`wall_set_tile` `0x0049F950`); tower and gatehouse tiles carry 0x8000.
  (Types 0x81/0x91/0x92 are columns, not towers: see "Towers, walls and their sentries".) Wall hit points and
  sieges: "Walls and gatehouses under attack".
- Warship wharf (0x88), status `b+0xBA`: 0x1039 building, set when there is no trireme and
  `b+0x3C ≥ 200` and `b+0xDC ≥ 200`; 0x2039 repairing, set when the trireme's action is 0x13.
  - Rate by staff: 100 → 10, 75..99 → 8, 50..74 → 6, 25..49 → 4, 1..24 → 2, 0 → 0.
  - Building: `b+0x54 += rate`; when it exceeds 319 a trireme (0x39) spawns (`b+0xB8`) and
    `b+0x3C`, `b+0xDC` each lose 200.
  - Repair: `fig.ship_hp += rate` up to `+0x12C`.

## Invasions

### Events (rank 13) — verified
`g_events` `0x009173F0` holds an i32 count, then 124-byte records from `0x009173F4`
(struct `ScenarioEvent`). Record `0x8C` (`0x0091B7C4`) is a scratch record used by god-summoned
armies and the UI. An invasion is an event with type byte `+0x02 == 2`; its invader city is
`cities[+0x58]` (rank 7, `0x008FBAC0`, 0x23C bytes per city, 22 cities).
- `events_alloc` `0x00467A40`: reuses a dynamic (`flags & 0x100`), done (`flags & 4`) record with
  `+0x0A == 0` that is not dated today. A type-2 record is reused only when no company
  (`+0x78 == i`) or transport (`fig+0x17C == i`) still refers to it. Otherwise it appends while
  count < 0x8C.
- Defaults (`0x00467590`): flags 2, warning months `+0x2C` = 2, `+0x10/12` = 5/10,
  `+0x18/1A` = 1/2, `+0x20/22` = 1/8, `+0x5C/5E` = 1/8, `+0x24 +0x26 +0x52 +0x54 +0x34` = −1.
- Date = (`+0x14` + start year `(i16)0x00902928`, month `+0x03`).
  - `invasion_event_pending` `0x00471F90`: false if `flags & 0x20001`, if the date is in the
    future (`0x00471F60`), or if `flags & 4`. Otherwise `elapsed = (year − date_year)*12 −
    date_month + month` and the result is `elapsed <= +0x2C`.
  - `event_months_until_due` `0x00472000`: `+0x2C + (date_year − year)*12 + date_month − month`.
  - So an invasion is announced on its date and arrives `+0x2C` months later (2 by default).

### Monthly pass `invasions_month_update` `0x00504A30` — verified
In `month_advance`'s month-change block, before the month increments, unless `0x00665E2C == 1`.
For each type-2 event (`0x0046D520`), `invasion_event_month` `0x00476E20`:
```
city = event_city(ev)                       # 0x0046E160
if ev.flags & 4:                            # already arrived
    if ev+0x32 and (no city or that city's forces on the map < 1): ev+0x32 = 0
    return
if not city or not invasion_event_pending(ev): return
if city+0x02 != 2 or city+0xD4 != 1 or (city+0x174 & 4) or city+0x170 == 0:
    ev.flags |= 4; return                   # invader must be an active rival
m = event_months_until_due(ev)
if m == 0:
    army = invasion_spawn(city+0xCC nation, ev+0x0C strength %, ev+0x1C entry point, ev+0x38, ev index)
    if army: bribe = invasion_bribe_cost(ev); message 0xDD (option 0x38 if bribe < treasury else 0x30)
    ev.flags |= 4; event_chain_trigger(ev+0x24)          # 0x0046DE00
    return
warnings, each sent once (bit in ev+0x57), message 0xE0:
    m == 24 -> bit 2, text 0x2D5;  m == 12 -> bit 4, 0x2D6;  m == 6 -> bit 8, 0x2D7
    m == 1 -> bit 0x10, 0x2D8 (0x2DD when auto-defend is on)
    m >= 2 and dated today -> bit 1, 0x2D4
    (+0xA73 to the text id when city+0xE0 == 2)
```

### Spawning — verified
`invasion_spawn` `0x00504600`: entry points 9..16 go to the sea spawner `0x00503FD0`, the others to
the land spawner `0x005044F0`. Both set `ev+0x32 = 1` and `city+0x01 = 1`.
```
s = min(strength, 256)
(inf, mis, cav) = col 9 ("frequency") of rows 0,1,2 of ENEMY[min(nation,10)]   # 0x00501ED0; scratch event uses nation 0
counts: infantry = inf*s/100, missile = mis*s/100, cavalry = cav*s/100
```
- Entry point `invasion_point_select` `0x00503E20(pt, sea)`, land case:
  - `n` = number of valid points among 8 (`x != -1` at `0x00902C10[i]`, y at `0x00902C30[i]`, i16).
  - `pt == 8` (random): index = `rnd & 1` if n ≤ 2, `rnd & 3` if n ≤ 4, else `rnd & 7`, where `rnd` =
    `0x00F137D4` (this tick's 7-bit value; no new draw).
  - Otherwise index = pt − 1. Then scan forward cyclically to the first valid point.
  - Sea: index pt − 1 within 8..15.
- Land `enemy_army_spawn_land` `0x00504650`:
  - `g_invasion_serial` `0x008F9828` += 1, wrapping above 32000 to 1.
  - Each class is capped at 256 and split into companies of 8. A remainder r alone makes one
    company of r. With full companies, the last two become `(r+8) − (r+8)/2` and `(r+8)/2`.
  - Point −1 → `0x00902CB8/0x00902CBA`.
  - Facing: y == 0 → 4, y ≥ h−1 → 0, x == 0 → 2, x ≥ w−1 → 6, else 4.
  - Abort if the tile has flags `0x300203`, or 4 without 0x40. Clear it if flags `0xC008`.
  - Types: infantry 0x29, missile 0x28, cavalry 0x2A.
  - Companies are allocated in slots 35..99 (`0x004DDB80`). Each soldier gets action 7, delay
    `fig+0x36 = (j+1 + company*20)*10`, `+0x60` group, `+0x62` rank, `+0x110` event.
  - Each company resets `g_months_since_enemy = 0`.
- Sea `0x00503FD0`:
  - Warships (0x40): `ev+0x36` of them (s/4 for the scratch event; none for nation 8), with
    delay `i*25 + 10`.
  - Transports (0x3F) carry up to 8 soldiers each, loaded missile, infantry, cavalry. The
    payload `fig+0x16C` is `class*1000 + n`. They land at
    `(0x00902E20[ev+0x78], 0x00902E2C[ev+0x78])`, i32, 3 landing points.

### Bribe `invasion_bribe_cost` `0x00476CF0` — verified
```
v = Σ over enemy companies of this event: count * (25 for 0x28/0x29, 50 for 0x2A)
  + 200 per live warship + 25*(p0 + p1 + 2*p2) per transport payload
cost = clamp(ftol(v * [1,3,4,5,7][difficulty]), 1, 60000)      # f64 table 0x00633280
```

### Counters — verified
- `military_counts_on_figure` `0x004E3420`, on every figure create/delete:
  - `g_enemy_units_alive` `0x00FEB084` = live 0x28, 0x29, 0x2A, 0x3F, 0x40;
  - `g_player_soldiers_alive` `0x00FEB0C8` = live 0xB, 0xC, 0xD, 0x39;
  - both floor at 0.
- `0x004E13C0` recounts `g_enemy_warships` `0x00FEB3EC` and transports `0x00FEB3E8`.
- `month_advance`, at month_tick 0:
  - `g_months_to_next_invasion` `0x00FE957C` = min `event_months_until_due` over pending
    invasions (1000000 if none);
  - `g_months_since_enemy` `0x00FE9578` += 1 if no enemy unit and no warship, else 0.
- Immigration stops while `g_enemy_units_alive >= 4` (sentiment.md).
- Recruitment (steps 13/14) is frozen while any enemy unit or warship is alive.
- Auto-defend option `0x00F2A990` (text 68:176):
  - when the next invasion is 1 month away, `auto_defend_mobilize` `0x00568D20`. It saves the
    labour priorities, sets category 7 to 5 and caps the others at 4, mobilizes up to 20
    companies, and sends them to the rally points `0x00DB68C0`/`0x00DB6940`;
  - otherwise, when `g_months_since_enemy == 1` and `0x00FEB4F9`, `auto_defend_dismiss`
    `0x00569010` restores the priorities and sends the troops home.

### Spontaneous rival invasions `0x0047EE20` (month_tick 12) — verified (float compares read from code)
- For each of the 22 cities, `city_relation` `0x0042CF10` gives 0 ally, 1 vassal, 2 rival,
  3 parent, 4 colony, 5 self, 6 distant (text 61:197..203).
- Gift candidate: an ally or parent, while treasury < 0 and `city+0x164 > 49` and
  `city+0x175 == 0`.
- Invasion candidate: a rival with `P1 < 0.4*R`, `R <= 0.75*peak` (R = `city+0x1E8*3/5`),
  `city+0x168 == 0`, no forces on the map and no invasion pending.
- If there is any candidate: one full `random_next`, then pick
  `candidates[(0x00F137E4 & 0x7FFF) % n]`.
- An invasion candidate becomes a dynamic type-2 event dated today (`0x0047F1C0`), so it arrives
  2 months later. Fields: `+0x0C = R`, `+0x58 = city`, `+0x38 = 10`. Entry point =
  `(rnd & 7) + 1` by land, or `+9` with a landing point when the trade route `+0x140 == 2` (sea).
  This draws the RNG a second time: landing `+0x78 = FUN_00503EC0()` = `rng_15 % n`, n = the map's landing points
  that exist (of 3; 0 when none), an index the spawn (0x503FD0) reads in the full table. The same at
  `event_resolve_at_start` for a scenario type-2 event with city/point `+0x1C > 8`. Ours (10-30): war.invasion_create
  draws it, auto-defend's rally point (alarm.rally_point) uses it; no shipped open-play episode has a type-2 event.
- Player strength `0x00568540` (companies at home, `+0x82 < 0`):
  - `P1 = rabble/2 + 2*(horse + slots 33,34) + 3*triremes + hoplites + slots 31,32`;
  - `P3 = P1 − rabble/2`;
  - `g_military_strength_peak` `0x00FE6A78 = max(P3)`, updated at month_tick 4.
- So a player who has never had an army (peak 0) is never invaded spontaneously.

### Military requests and distant battles — partly verified
- Type-1 "request" events with subtype 0x18 run the state machine `0x0046ED70`. That this subtype
  is the troops request is a hypothesis. `+0x30` holds the state:
  - 0: announced; reminders at months `+0x61` and `+0x62`;
  - 6: army away, countdown at `+0x2E`;
  - 7, 8, 9: return messages 0xDE;
  - 10: done.
- `distant_battle_resolve` `0x00461540`:
  - Player side: sent companies (cavalry ×2, others ×1) + triremes ×6 + allied `+0x76` +
    10 per hero (`0x00F0E4E8`).
  - Enemy side: `+0x0C`, or the city's `+0x1E8`.
  - Flag 0x400 with player > enemy/2 is an automatic win. Flag 0x200 multiplies the enemy by
    70/100.
  - Casualty percentages come from tiers on the ratio. Example: a loss without flag 0x4000 →
    player 80 %, enemy 50 %. The full tier tables are in the code and still to be transcribed.
  - The enemy city then loses `+0x1E8 * cas / 100`.
- God-summoned armies (religion): `0x004EC410` (nation 4) and `0x004EC560` (nation 10), 8
  infantry each, through the scratch event.

### Sandbox
Invasions need an active rival city in rank 7 (`kind 2`, relation 1, `+0x170 != 0`), from one of:
- a scheduled type-2 event;
- a spontaneous invasion, which also needs `g_military_strength_peak > 0`.

A city with no empire cities and no events can therefore never be invaded. Requests and gifts
also need cities. Monsters and god armies are separate (religion).

### Empire city fields read here (rank 7; owner: trade-empire; names hypothesis)
`+0x00` in use, `+0x01` attacking, `+0x02` kind, `+0x04` index, `+0xCC` army nation,
`+0xD4` relation, `+0xE0` message variant, `+0x140` trade route kind (2 = sea), `+0x164` attitude,
`+0x168` blocking flag, `+0x170` active, `+0x174` flags, `+0x175` gift flag,
`+0x1E8` military strength.

## Soldiers on the map (decoded 2026-10-28)
Handlers: rabble 0xB `0x004B31F0`, hoplite 0xC `0x004B26B0`, horseman 0xD `0x004B1840`. **verified** unless marked.
Idle soldiers are real figures, hidden at their palace part's road entry (oracle, "See a working city": 14
companies, every member action 6, hidden, on the palace road tile (47,79); re/oracle/runs/mil-a,
tools/oracle_military.py).

### Per-tick prologue (all three)
```
F = figure_groups[fig.formation]; route_mode 0
rabble, horseman: anim_frame += 1 (wraps 12; restored when standing); hoplite: advanced by the sprite code
if F.in_use != 1: action 4
speed = col8 (rabble 8 = 11.25 ticks/tile, hoplite 6 = 15, horseman 12 = 7.5; charge 2*col8 capped 18)
fig+0x63 = 0; hidden = F.all_home (+0x03)
home slot (+0x30/+0x32) = F.home (+0x36/+0x38, the palace part's road entry) + OFF[F.layout][slot] (layout 5: F.home)
hoplite, horseman: company abroad (+0x82 >= 0) and action not 0xD/0xF -> 0xF  (0x004E17A0; not rabble)
soldier_check_ready 0x004B17F0: action not 3/6 and F.ready (+0x93) == 0 -> action 3
```
(+0x93 is never written 0, "Morale": the action-3 branch is dead code.) Route mode 0 = figure_find_route case 0:
route_distance 0x00588920 (4-way BFS over route & 0x11D) + route_trace(8): diagonal steps (walkers.route0). Ours'
marches (forces._route, _go_home) used a plain 4-way BFS path until 11-03 (oracle 1B-inv-city: company 1 from the
houses at (44..58, 74) went west along y 73..74 and diagonally up to (19, 69); ours turned north at x 35 and went
along y 69..70). **Sub-steps (11-03, bugs.md 432):** every walk of a soldier (march 9, home 7, expedition 0xD,
charge 0x10, the engage chase) is figure_move 0x004D1170 -> figure_route_walk 0x004D7BD0 once a tick, as the
invaders' (imove): the sub-steps of the tick by speed code and speed_phase (+0x2B; rabble 8: 1, 1, 2, ...; hoplite 6:
1; horseman 12: 2; charge 2 x col8 capped 18: 3), tile progress +0x39 + 1 each; past 14 progress 15 and the route
decision (next direction, progress 0; route used up: 8 arrived; next tile blocked: 9, a new route); at progress 8
the tile changes (figure_change_tile 0x004D9330, the tile contact). A new route (figure_find_route) starts at
progress 15, so the first tile change comes 9 sub-steps after the order (rabble: 6 ticks). figure_fight_end keeps
the progress and the walk goes on from it. Ours: forces.advance (w.fprog, w.sph), forces._walk / _stand; before
11-03 ours changed the tile at the step's start (6..7 ticks early for rabble). Oracle 1B-inv-city-march (company 1
marching from the houses, dumps every tick 36..290; tools/oracle_soldier_walk.py): 250 of 250 dumps equal in tile
and tile progress for all 8 members.

### Actions
| action | meaning |
|---|---|
| 3 | walk to the home slot; arrived -> 6; lost -> delete |
| 4 / 5 | dying (0x004D60B0) / fighting (0x004D5F10) |
| 6 | idle (0x004B1630): not mobilized or not ready -> hidden at the home building's road entry (`soldier_put_home` 0x004B11C0); home gone -> delete. Mobilized and ready: stands |
| 7 | going home after "send home" (0x004B1330): walk to the road tile of a house of its class (`soldier_home_house` 0x004CDC50), then `soldier_put_home` (event troops walk to the map entry and vanish; sanctuary troops to their sanctuary) |
| 9 | march to the slot (0x004B08F0): dest = F.dest + OFF[layout][slot] (+ SPIRAL[fig+0x00]); arrived -> the mode action saved in +0x164 (10 / 0x11 / 0xB); lost (10) -> next spiral tile (168 tries: rings 1..6, table 0x005F11A6), then delete |
| 10 | hold (mode 0, 0x004B10A0; rabble archer_fire_update 0x004B2F70 hold=1): stand on the slot; off the slot and no melee/fire timers -> 9. Melee only by tile contact |
| 0xB | mode 2: hoplite engage (0x004B0B60); rabble skirmish (enemy within 5: step back one tile, else fire); horseman hit and run |
| 0x11 | mode 1 attack: engage (0x004B0B60); horseman own code |
| 0xD / 0xF | expedition: march to `g_land_exit`, then hidden there (abroad) |
| 0x10 / 0x12 | horseman charge / regroup |

**Rabble per tick (11-03, bugs.md 433; fig_handler_rabble 0x004B31F0):** the stone is thrown only in hold 10
(archer_fire_update 0x004B2F70 with hold = 1), skirmish 0xB and attack 0x11 (engage below), never on a march (9).
archer_fire_update: hold first runs FUN_004B10A0 (off its slot while the company's melee +0x50 and under-fire +0x5E
timers are 0: action 9 back to the slot, the mode saved in +0x164), then reload +0x6B + 1; past col7 it is 0 and
missile_target_search(col6): none -> attack_timer 0, target 0; else attack_timer 1 and the direction toward it
(FUN_0058D1F0, the slope rule). With a target (no alive check here: a stale record's tile) within col6 Chebyshev: it
stands (route freed), faces it, attack_timer 1 plays the sound, **7** throws the 0x2D and sets the company's firing
+0x5C = 6 (0x004B31AD), attack_timer + 1 (past 100: 0). So one stone 6 ticks after each search that finds a target,
a search every col7 + 1 ticks (70..80 by difficulty), the counter running only in these actions (from the tick after
the march arrives: FUN_004B08F0 switches the action without calling it). Skirmish 0xB: missile_target_search(5) finds
one -> dest one tile against the direction field (+0x11; after a walk's end 8..10, giving 4..6) and figure_move; else
archer_fire_update(hold = none within col6). Attack 0x11: engage with leash col6 + 4, then the same reload / stone at
attack_timer **8**; standing to throw only when the target is within col6, else it walks toward dest (the route found
then is walked to its end before a new one). FUN_004DF410 (step 29) counts the player companies' timers down too
(melee 6 while a member fights). Ours: forces._rabble / _fire / _chase / timers; nearest_enemy doubles the distance
after the range test when the candidate has an attacker (a soldier's target, +0x84). Oracle 1B-inv-city: the
rabble's stones at dumps 401, 435, 458, 472, 491, 506, 529, 543, 562 (and 633) in both, from the same shooters'
tiles (ours threw first at 346, per tile walked and every 12 ticks); inv-city 37 -> 33 of 39 AI days differ, the
first difference moved from day 418 to 571 (enemy companies' targets; the invaders' own AI, not the rabble).
**Engage `0x004B0B60`:** leash 6 tiles (rabble: missile range 10 + 4 = 14). Within the leash of its slot: keep
the target (+0x82) if alive and visible, else `nearest_enemy 0x005017A0(x, y, leash)`; dest = the target's tile
(else the slot). Farther than the leash from the slot: back to the slot. Rabble: reload +0x6B += 1; past col7 (80)
pick `missile_target_search(range 10)`; while one is in range: stand, face it, stone at attack_timer 8 (projectile
0x2D), F.firing (+0x5C) = 6. **nearest_enemy:** figures state 1, not dying, not hidden, of types 0x28..0x2A
(invaders), 0x3B (wolf), monster col0 8; hoplites/horsemen in 0xB/0x11 skip already-targeted ones (flags & 2);
only the target company's members when F+0x8C > 0; Chebyshev <= r, doubled when the candidate already has an
attacker; rabble need line of fire; strictly nearest.
**Horseman:** 0x11: enemy within 3 -> engage (melee); 4..6 -> `formation_charge 0x004DD6D0` (charge, action 0x10:
2*col8, one `horseman_charge_hit` on the first figure of a tile, then back to the saved action); none -> slot.
0xB (hit and run): as 0x11, but after 5 contacts the company regroups (0x12: the leader backs off ~9 tiles, the
others keep their slots around it, then mode 2 again). A charge always sets layout 1 (exe: the direction is
computed from a point to itself). Player horsemen never count charge tiles, so the x4 bonus never applies (hypothesis).
**Hoplites and horsemen per tick (11-03, bugs.md 434; fig_handler_hoplite 0x004B26B0, fig_handler_horseman
0x004B1840):** every tick, as the rabble. Hold 10 is FUN_004B10A0 alone: anim_frame 0; off its slot (F.dest +
OFF[layout][slot] + SPIRAL) while the company's melee +0x50 and under-fire +0x5E timers are both < 1: +0x164 = 10,
action 9, spiral 0 (the march runs from the next tick); else it stands, whatever enemy is near (ours before: back to
the slot only with no enemy within 20, acting every 12 / 51 ticks). Hoplite 0xB / 0x11: engage with leash 6 (above;
a new target through figure_set_target 0x004E3280, which also sets the target's flags |= 2, sticky until its
figure_delete; nearest_enemy skips such invaders / wolves for hoplites and horsemen in 0xB / 0x11, so a second
soldier does not pick an enemy someone already targeted, ever: figure_set_target callers are the soldiers' engage,
the rabble's stone, gods and heroes; towers and sentries do not). Horseman 0x11: nearest_enemy(its tile, 6) none ->
attack_timer 0, engage; one, but none within 3 -> timer 0 and formation_charge at it; within 3 -> engage. 0xB: none
within 6 -> engage, anim_frame 0; within 6, none within 3 -> charge; within 3 -> +0x13C (named god_attack_kind) + 1, below 5
engage, at 5 (and timer) 0 and FUN_004E2500: every member not dying / fighting of a ready company (FUN_004DD0F0)
spiral 0 and, rabble / horsemen, action 0x12. formation_charge refuses (returns 0, nothing else that tick) unless
mobilized, the tile is reached from the standard (route_distance) and is not the company's position (+0x2E); then
F.dest = the tile, layout 1, +0x80 = 0, all_home 0, and each ready member not dying / fighting: spiral 0, +0x13C 0,
+0x140 (saved_charge_action) = its action unless 0x10, action 0x10, route freed. 0x10: figure_move to F.dest + OFF at 2 x col8;
8 -> the saved action, anim_frame 0 (no act that tick); 9 -> route freed (a new one next tick; ours before: the
charge ended); 10 -> spiral + 1 (past 168 deleted). Regroup 0x12: the leader (FUN_004E24A0: the first member not
dying of a palace / sanctuary company, +0x69 == 0) times + 1; past 8 timer 0 and FUN_004E2320 (the mode-2 layout,
message 0x22 below morale 21, ready members not dying / fighting: spiral 0; rabble / hoplites / horsemen marching
keep 0xB saved, others take 0xB); else its dest one tile against its direction field (8..10 after a walk's end give
4..6: the first step backs away from where it faced, later ones go +y) and action 9 with 0x12 saved, spiral 0. The
others take the leader's action and anim_frame; off their spot (OFF[layout][slot] + the leader's tile) +0x164 = that
action (unless 9), action 9, spiral 0; FUN_004B08F0 with +0x164 == 0x12 marches to OFF + the leader's dest. Ours:
forces._stand / _engage / _horseman / _regroup / charge, set_target; not settled: a follower on its spot while the
leader fights gets action 5 without an opponent in the exe, whose figure_fight_end restores the follower's own last
saved action (ours keeps no such record: it stays in 0x12). Oracle 1B-inv-city-horse (horseman company 9 mobilized in
hold to (19, 69), dumps every tick 36..2404, tools/oracle_soldier_walk.py OSW_COMP=9): see bugs.md 434.

### Formations
Slot offsets `OFF[layout][slot]` at 0x005F2358 (i32 pairs); slot = index in F.members:
```
0  (0,0)(1,0)(0,1)(1,1)(-1,0)(-1,1)(0,-1)(1,-1)
1  (0,0)(-1,0)(-2,0)(-3,0)(0,1)(-1,1)(-2,1)(-3,1)          line along -x, second rank y+1
2  (0,0)(0,-1)(0,-2)(0,-3)(1,0)(1,-1)(1,-2)(1,-3)          column along -y, second rank x+1
3  (0,0)(0,-1)(1,0)(0,1)(-1,0)(1,-1)(1,1)(-1,1)
4  (0,0)(1,0)(0,1)(1,1)(2,0)(2,1)(1,2)(0,2)                (also 10, 11)
5  all (0,0) (also 8)
9  (0,0)(2,0)(0,2)(2,2)(-2,0)(-2,2)(0,-2)(2,-2)            open square
12 (0,0)(0,1)(1,1)(-1,1)(-1,2)(1,2)(-2,2)(2,2)             hoplite wedges 12..15
13 (0,0)(-1,0)(-1,-1)(-1,1)(-2,-1)(-2,1)(-2,-2)(-2,2)
14 (0,0)(0,-1)(1,-1)(-1,-1)(-1,-2)(1,-2)(-2,-2)(2,-2)
15 (0,0)(1,0)(1,-1)(1,1)(2,-1)(2,1)(2,-2)(2,2)
16 (0,0)(0,-1)(0,-2)(0,-3)(-1,0)(-1,-1)(-1,-2)(-1,-3)
17 (0,0)(-1,0)(-2,0)(-3,0)(0,-1)(-1,-1)(-2,-1)(-3,-1)
```
Layout by mode (0x004E2100 mode 0, 0x004E2210 mode 1, 0x004E2320 mode 2): `+0x77 == 0`: layout 1 (facing 0) else
0x11; `+0x77 != 0`: layout 2 (facing 2) else 0x10; hoplites in mode 2 use the wedges (0xF/0xD, or 0xC/0xE). The
rotate button cycles 2 -> 1 -> 0x10 -> 0x11 -> 2 (wedges 0xC -> 0xD -> 0xE -> 0xF) and toggles +0x77.
Facing (+0x6B, 0x004DE830): layouts 1, 0xD -> 0; 2, 0xC -> 2; 0xE, 0x10 -> 6; 0xF, 0x11 -> 4.

### Orders (UI 0x00405F70 on `g_selected_companies` 0x007818E4; companies in the city and ready)
- 0 centre the view on the standard; 1 rotate; 2 mobilize / send home (mobilize all when no more are mobilized
  than at home, else send all home); 3/4/5 mode 0/1/2 (hold, attack, special tactic: names hypothesis) with
  `F.target_company = -1`; each member gets the mode action (10 / 0x11 / 0xB), or keeps marching with it saved.
- Map click `0x00406290`: ignored within 3 tiles of the play-area edge; an enemy on the clicked tile -> mode 1
  and target company = its company; then `formation_move`; sound wavs/cohort5.wav. A non-mobilized company only
  gets its dest changed.
- Clicking a company icon on the military page (0x00516A50) selects it, centres the view and enters the
  move-order cursor mode 0x48.

**`formation_move` 0x004DD250(x, y, company, k, quiet):** origin = the standard's tile (or the home's road entry);
refuse unreachable tiles (4-way BFS 0x00589270) and blocked ones; candidate tiles (x, y) + SPREAD[k..19]
(0x006395D0: (0,0)(0,-3)(3,-3)(3,0)(3,3)(0,3)(-3,3)(-3,0)(-3,-3)(6,-3)(6,0)(6,3)(-6,3)(-6,0)(-6,-3)(-3,-6)(0,-6)
(3,-6)(3,6)(-3,6)): the first reachable with no building and no other standard; F.dest = it. Mobilized and not
quiet: morale < 21 -> message 0x22; each ready member not dying/fighting: at home (+0x63) -> **teleported to the
road tile of a house of its class** (round robin over the houses, shared cursor 0x00FEB0E8); action 9.
F.all_home = 0. So several selected companies spread on a 3-tile grid.

**Call to arms** (oracle-checked, run mil-a: company 1's 8 rabble, hidden at (47,79), appeared in one tick at
(44,74) (46,74) (52,74) (54,74) (56,74) (58,74) (45,79) (47,79), action 9, slots (48,81) (47,81) (46,81) (45,81)
(48,82) (47,82) (46,82) (45,82) = (48,81) + layout 1 while the company dest read (47,82): the one-tile shift
is unexplained): mobilized = 1, `formation_move(first company's dest, k)`, the mode function. The soldiers appear
at houses all over the city in one tick and march (type speed) to their slots around the target.
**Send home `formation_return_home` 0x004DD8D0:** mobilized = 0; each member (a fighter after its fight) action 7:
walk to a house of its class and vanish into the palace. F.dest is not reset: the standard keeps standing
where the company last was (hypothesis that this shows; confirm in the original).
**Recruits** (`0x00567C70`) are created on the palace road entry: hidden there when the company is home; for a
mobilized company teleported to a house and marching to the slot.
**Rally points** 0x00DB68C0 (land) / 0x00DB6940 (sea): computed by the game (`0x004E29B0` from month_advance when
dirty): the middle tile of the route from each invasion point (and landing point) to the palace (palace road
access when there is no route). `auto_defend_mobilize` sends companies there in mode 0.

### Company state
- Standard bearer, figure 0xE (`0x004B3E00`): created with the company; never walks: it stands on F.dest every
  tick (the company's position for the player). Picture Zeus_General: SPR_STD_POLES index 20 - morale/5 plus
  SPR_FLAG_COMPANIES + display_index*7 + anim_frame/2 (slots 31/32 SPR_FLAG_GOD1, 33/34 SPR_FLAG_GOD2, event
  troops SPR_FLAG_LOAN); only a selected company's flag waves. Deleted (company freed) when the count is 0.
- Timers (0x004DF410, step 29): +0x50 melee (6 while a member fights), +0x5C firing, +0x5E under fire; zeroed
  when no enemy is alive. The waver counters +0x73 / +0x66: "Morale" above (no rout for palace companies; the
  11-03 reading replaced "a member at a time is sent home and F.ready cleared", which had no code behind it).
- fig_handler_standard 0x004B3E00, every tick, a palace company's morale (11-03, ours forces.standards from
  Game.step after the cycle step): peace = g_months_since_enemy > 1, months to the next invasion > 1,
  g_enemy_units_alive == 0 (military_counts_on_figure 0x004E3420: types 0x28..0x2A, 0x3F, 0x40 from create to
  delete) and no enemy warship. Not ready (+0x93 == 0, never in practice): +0x90 = 0; in peace ready again, +80,
  counters cleared. Ready, in peace: not mobilized -> +80 every tick; mobilized -> the standard's +0x36 + 1, at 26
  back to 0 and +1. Ours before 11-03: daily at the step-50 point (+80 a day, +51 ticks' worth of the timer).
- formations_refresh 0x004DE210 rebuilds the member lists (+0x08) of formations above 20 on every call (cycle step
  5, every formation_member_lost), and of 1..20 too when no enemy unit or warship is alive: the figures with state 1
  in figure id order, +0x62 = the index. So an invader's slot is its id rank, not its creation order: after a load
  the free-id ring runs 1999 down (figures_rebuild_free_list 0x004D9F40), the spawn takes ids downwards (oracle
  1B-inv-city: 1883 slot 0 at creation, 1875 slot 0 after the first refresh) and the slots reverse. Ours (11-03):
  morale.refresh at step 5 and on every death of a soldier, invader or wolf, for the invaders and the aid
  companies 21..30 by Walker.fslot; savimport rebuilds the ring as the load does (`_figure_slots`). Not ported: the
  palace and sanctuary companies' lists (ours keeps their soldiers at home as a count, not as figures).
- `+0x2E/+0x30` (company position) follows the slot-0 member in the field (oracle run mil-a: (47,82) -> (44,74) when
  member 0 appeared at (44,74), then (43,75) .. (47,80) as it marched); the static scan found no writer.

### Expeditions on the map
`expedition_send_forces` 0x004DEB30 (writer of Formation+0x82): each selected company (+0x67): members at home are
teleported to a house; action 0xD: march to `g_land_exit` (the map exit) at type speed; there 0xF: hidden, held
on the exit tile (abroad). F.dest = the exit (the standard stands there). Triremes action 0xC, heroes 0xE.
Details (11-01, bugs.md 369): every live member not dying is teleported, only when F.all_home (+0x03) is set (then
cleared), one FUN_004CDC50 call each, so the members land on the houses' road tiles in round robin (4 a house in
the working city; two elite houses beside one avenue segment share a road tile: clumps of 8). The walk is route mode
0 (4-way flood + 8-way trace: diagonal steps) at col8 (horseman 12: ~6.7 ticks a tile here, the exe's own pace, not
the project's walker_pace); 0xD arrived/lost -> 0xF: hidden, put on the exit tile every tick. Ours: sim/military/
forces.march_out (walkers.route0); abroad = off the map, counted in the company. Oracle 1L5-troopsmarch
(tools/oracle_troops.py march): every 20-tick dump equal (11-02 again after bug 419: gardens are open land, 0x20 -> 0x10).
Return `0x004DEE60`: +0x82 = -1; members walk from the exit to a house of their class and into the palace
(`formation_return_home`); the standard goes home. Casualties abroad: strengths only (distant_battle_resolve).

### Soldier sprites (SprMain; first + frame*dirs + dir)
| figure | walk | die (8, no dir) | fight / throw |
|---|---|---|---|
| rabble 0xB | 6841 (12x8) | 6937 | **6945** (12x8, pick up a stone and throw: melee and missile) |
| hoplite 0xC | 7105 | 7201 | 7209 (8x8) |
| horseman 0xD | 7273 | 7369 | 7377 (12x8) |
- The knife group 7041 is never referenced (byte search): walkers.json had fight 7041 / fight2 6945 swapped.
- Hoplite fight frame = attack_timer if < 8 else 0, drawn **with direction 0** (disasm 0x004B2D82..0x004B2DAF:
  an exe bug, kept); die frame min(timer, 7). Horseman fight: attack_timer > 11 -> frame (attack_timer-12)/2,
  else 0; in 0x11 table [0,1,2,3,4,4,4,4,4,4,5,5,5,5,5,5][attack_timer >> 1]. Rabble throw: wall-clock rate
  (0x005AF8C0, rate 100).
- **Rabble throw picture (11-03, bugs.md 436; fig_handler_rabble 0x004B31F0 tail, sprite_anim_step 0x005AF8C0):** in
  10 / 0xB / 0x11 with a target (+0x82, a stale one too) the fight group 6945 by sprite_anim_step(.., anim_frame,
  rate 100), in 0xB / 0x11 only while cStack_9 == 0 (not walking this tick: a throw within col6, at its dest; hold
  always); else the walk group at anim_frame. The prologue's +1 is undone while it stands (anim_frame = the value
  before, cStack_9 == 0), so the throw frames are anim_frame + 1 on each gated tick (wrap at 12; sprite_anim_step first
  sets 0 when the frame is >= the group's count), from the frame its walk left (the prologue's +1 a tick while
  cStack_9 == 1). archer_fire_update sets anim_frame 0 every call and cStack_9 = 1 at its stone (attack_timer 7), so
  in hold / skirmish the stone's tick keeps that 0: the throw restarts at frame 1 (engage's stone at 8 does not set
  it). Oracle 1B-inv-city company 1 (p = 1 under the harness's clock): frame 5 frozen in hold, 6 at the search that
  found a target (395), +1 a tick, 11 -> 1 at the stone (401), 11 -> 0 at 412. Ours (sim forces._rabble / look,
  acount = the walk counter; play rabble work "throw" counter + offset 1, scene.js): (c0 + 1 + dt // p) % 12 from the
  tick it stood with a target or the stone (c0 0), the look re-sent each record (end: the next target search); before:
  frames 0..11 for 12 ticks after each stone. Checked: 1491 of 1859 member-dumps (380..1100) equal in frame and in
  whether it throws (the rest: ours' fights starting a tick early, 574 vs 575, then the deaths part); play mode (own
  :8851, headless dpr 1.25, tools/god_rate_check.mjs --roles rabble, rate 10): frames +1 every 4 ticks, wrapping,
  back to 1 at each stone. Not settled: the counter a throw leaves when the target goes and a new one comes while
  it stands (ours takes the walk counter again; the gated count is wall-clock in the exe).
- Melee frames per family (11-02, bug 393; "timer" = attack_timer after figure_fight_tick's +1: 1..23, 0 at a hit):
  rabble 0xB (0x004B31F0): the prologue steps anim_frame +1 a tick (wrap 12) and action 5 keeps it (cStack_9 = 1), then
  sprite_anim_step(6945, rate 100) adds +1 on the gated ticks: ours fr = dt + dt // p (p = 4, "rabble" rule; was +1 a
  tick); sanctuary Amazons (formation 0x1F/0x20, rabble type): frame = timer if < 12 else 0 on the Amazon archer
  fight group; hoplite 0xC (0x004B26B0): frame = timer if < n (8) else 0, direction 0, the attack sound at timer 1;
  Ares warriors (formation 0x21/0x22): the same on 0x6403 (n 20); horseman 0xD (0x004B1840): as above. Ours: rabble,
  hoplite, horseman as the exe; the sanctuary troops are drawn with the palace troops' art and rules (not ported).
- Sanctuary troops: Zeus_Amazon (31/32), Zeus_AresWarriors (33/34). Poseidon games: PoseidonImps groups.

### Open (soldiers)
Hoplite fight direction 0 (oracle shot to confirm); writers of +0x64, layout 4, actions
8/0xE; the charge bonus; the flag after send home; +0x67 writer; morale spread on rout (0x004DE0E0/0x004DE120).

## Invaders on the map (decoded 2026-10-28; disassembly of 0x00500B70 and 0x00501480)
Corrections: enemy action 7 is "hold and regroup", not a fall back; invaders never rout on low morale (the waver
code 0x004DDF20 needs +0x82 < 0 and enemy companies keep +0x82 = 0); the palace is always the first target; the
invasion ends on a daily check (below). `route_search_ship` 0x00503A60 is misnamed: a 4-way BFS over
`grid_military >= 0` (military reachability).

### Spawn (`enemy_army_spawn_land` 0x00504650, `formation_alloc_other` 0x004DDB80) — verified
Companies in slots 35..99: home = entry tile, morale 100, layout by facing (0 -> 1, 2 -> 2, 4 -> 0x11, 6 -> 0x10);
`+0x44` target class (event +0x38), `+0x6A` nation, `+0x78` event, `+0x88` invasion serial. Each soldier: action
7, `timer = (j+1 + company_seq*20)*10`, **hidden** (untargetable until it appears), `+0x110` event.

### Per-tick update `enemy_figure_update` 0x00500B70 (first thing in the 0x28/0x29/0x2A handlers) — verified
```
route_mode 2 (weighted military route); slot_dest = company target (+0x3A,+0x3C) + LAYOUT[layout][slot]
3  leave: walk to g_land_exit (0x00902CB8); arrived or lost -> deleted
4 dying; 5 fight tick
6  archer shooting (below)
7  hold/regroup: timer -= 1; at <= 0: timer = 30; the hidden soldier appears (slot 0 plays horn/drums);
      company engaged (+0x50) -> 10; else dest = slot_dest, not there -> 9
      archers try to shoot; cavalry in mode 2: a soldier within col12 -> charge it (13)
9  march to the slot: every 30 ticks re-aim at slot_dest (there -> 7); move; arrived/lost -> 7; archers shoot
10 attack: company not engaged -> 7, then (either way) as 13 the same tick (0x00500FE5; hidden ones too)
13 hunt: the target soldier (nearest_soldier 0x00501640 when none: figures 0xB..0xD and heroes, alive, visible,
      not already attacked; Chebyshev nearest; if all are attacked, the first live soldier); none -> 7 (timer 50);
      walk to it, re-aim on arrival; lost -> 7
11 cavalry disengage (0x00501480: after a fight tick > 11 in mode 2 it rides to a free tile col12 away; the y
      offset uses f.x, exe bug kept); 12 timer 0
```
Invaders do not seek citizens: those fights come from tile contact (hostility row 3 = [0,1,1,0,1,1,0,1,0,1,0]:
an invader fights helpless walkers, soldiers, criminals, wolves; a citizen walking into an invader fights it
too). Citizens do not flee (no walker handler reads g_enemy_units_alive: hypothesis by search). A fight on the
next tile makes invaders re-route.

### Company AI (`0x004FFFD0`, once a day at step 29 while an enemy company exists) — verified
Mode machine (`+0x75`, military.md "Enemy company AI"); `morale_check` at low morale sets mode 0 and action 7
(regroup), never a retreat. Then:
```
event gone -> every member dies, company freed
+0x73 or +0x66 set -> members leave (action 3)
mode != 0 and a member fights a soldier -> engaged (+0x50 = 6)
company position = slot 0's tile
the first company of an event each day is the lead: weighted route distances from it (grid_military);
   player troops (presence grid, mobilized companies, rebuilt every 5 days) within 16 tiles -> target = them
   else target_buildings(): the palace if reachable, else the class list; no reachable palace for > 48 days
   -> +0x66 (the army leaves)
all companies of the event share the target
archers firing (+0x5C) -> hold; under fire (+0x5E) -> target = the shooting company's position
first 32 days: muster in formation near the lead (find_formation_spot 0x00502840, >= 10 tiles from the edge)
then cycles of march (A days), gather (B) and halt (C), with lengths drawn from the RNG (3 draws):
   lead 0: g = 1..2, m = 10..13, h = 1..2; lead: g = 3..5, m = 6..9, h = 1..3 (layouts 6/10: fixed tables)
```
Target classes `TARGETS` (0x006383E0, i32[11][50]; class 10 = random 0..10, empty lists fall back to 9):
0 food (granaries, farms, agoras, herding, hunting, fishing), 1 sea, 2 industry (incl. storehouse), 3 military
(armory, ranch, walls, towers, gatehouse, wharves, foundry, guard post), 4 wealth (tax office, elite houses,
mint, dock, trading post), 5 defence (tower, warship wharf), 6 commons (houses, guard post, infirmary,
superintendent, agoras, fountain, gymnasium), 7 beauty, 8 gods, 9 prestige (palace, stadium, theatre,
sanctuaries, elite houses). The nearest building of the earliest type in the list wins.

### Siege (route mode 2, `figure_check_next_tile` 0x004D8BB0) — verified
Route costs: building +10, wall +40, gate/tower +60, so invaders cut through when a detour costs more. They
never step onto an obstacle: they stand in front of it (direction 11) and hit it on 13 of every 51 ticks
(`cycle_step & 3 == 0`): building past 10 (its 11th hit), wall past 200, gatehouse/tower tile past 400
(`wall_damage_add` 0x00492830). `building_destroyed_by_attack` 0x004928C0: a wall tile becomes rubble, an
avenue piece is removed, a gatehouse 0x004E5B60, a sanctuary loses one piece, any other building (the palace
too) collapses to rubble, **no fire**. `wall_damage_add(tile, limit, 1, who)`: `who` = the invader's city
(FUN_004E2A60, its event's city) for a building tile (grid 1), 0xFF for a wall / tower / gatehouse / off-ramp hit;
every hit writes `0x00FE6A5B = who` (the last hit) and, on a tile whose building root is the palace,
`0x00FEB4F8 = who` (any hit, the palace need not fall). Step 13 (`simulation_cycle_step` case 0xD) sets both to 0xFF
when no enemy unit or warship is alive. Ours (11-02): military state `last_hit` / `palace_hit` (invaders._siege,
marks_reset; before: marked only when the palace collapsed, and any wall hit counted as "hit").

### Enemy archers and their missile 0x34 — verified
`archer_try_shoot` 0x005009E0 (type 0x28): reload past col7, then `archer_target` 0x00501C50 within col6:
priority 50 soldiers, sentries, watchmen, heroes; 30 triremes; 10 anyone else (distance + 5) only while fewer
than 4 player soldiers are alive; strictly higher priority and nearer, line of fire. Action 6 shoots at frame
SHOT[army] = [8,3,14,11,14,11,7,8,4,10,3]. Missile 0x34 (0x004BD970): 4 fine units a tick, at 121 of +0x39 (from 15:
105 moves) it counts as arrived, hits the first hittable figure on its tile (citizens included; not other invaders,
ships, wolves' class is hittable), `figure_hit(shooter, victim, 1)`, the shooter's company is "under fire" from the
victim's (+0x5E/+0x60). An invader's never damages buildings (only a god's or monster's line end). "Missile flight".

### Oracle check: invasions (10-30, track 1B; tools/oracle_invasion.py, runs 1B-inv-land / 1B-inv-sea)
An invasion event poked into the sandbox (re/oracle/scenarios/invasion-land.txt / invasion-sea.txt: Sparta at land
point 1, Delos at sea point 9 with 2 warships and landing point 0, strength 50 %, spawned at the change to
February, tick 816). The exe's message (Surrender / Bribe / Fight) pauses the game until answered.
- Land: the same point (148, 190) logical, 8 companies (infantry 8, 8, 7, 7; archers 5, 5; cavalry 5, 5), layout
  17 (facing 4) in both, the same first soldiers at the same ticks. The release (bugs.md 239, fixed 10-30):
  `enemy_company_go_attack` 0x004FFD00 gives every member that is not dying, fighting or shooting action 10, hidden
  ones too; the member's next update (0x00500FE5) finds the company not engaged: action 7 and on as action 13; with
  no soldier to hunt, action 7 with timer 50 (0x00501122). So all hidden members of a company that goes to mode 1
  appear 51 ticks after that pass; companies that roll the special mode (2) keep their delays until their mode-2
  countdown (6 days) ends in go-attack. The pass runs at cycle step 29 (FUN_00500910), i.e. the tick after 30 steps
  of the day (simulation_tick runs a step, then month_advance after step 50): ours `military.step29` at tick % 51
  == 30. Exe: 6 companies (38 soldiers) at tick 896, the other 2 (12) at 1202 (hidden timers 46 at 850, 12 at 1190);
  ours (own RNG, other companies roll mode 2) 17 at 896, 22 at 1202, one company by its delays. Special roll: infantry companies take layouts 15/12/13/14 by facing (0/2/4/6), others
  and go-attack / morale the facing layout (ported).
- Sea: the exe places every ship on its own free water tile by the point (0x00461C20), transports wait visible,
  ships sail diagonally (tracer 0x0058DCE0); ours now the same (bugs.md 237); first soldiers ashore at tick 1921
  in both, on (103, 99). Landed companies (10-30, leftovers): each transport's unload is its own
  `enemy_army_spawn_land` call (company count restarts at 0, delays (j + 1) * 10); the step-29 go-attack then holds
  every still-hidden member 50 more ticks, as on land. Exe 1B-inv-sea archers visible 2/8 at 1870, 3/10 at 1887,
  4/10 at 1904, 10/10 at 1921; ours the same since 10-30 (before: all by 1904, because ours' hidden archers shot
  their own transport in the go-attack tick and the next act un-hid them). Fixed: archer_target 0x00501C50's skip
  list (types 0, 6, 0xA, 0xE, 0x22, 0x23, 0x28..0x2A, 0x2D, 0x30, 0x31, 0x33, 0x34, 0x3B, 0x3F, 0x40, 0x4C: enemy
  ships, missiles, sheep, boar, wolf, cattle; goats, trade ships and boats are fair game while fewer than 4
  soldiers live; hero 0x45 priority 50), and a hidden member appears only when its action-7 timer runs out (ours
  `appear`). Infantry later differs by the special-mode roll (own RNG). Ported 10-30 (leftovers 3): the exe's hidden
  archers try to shoot every tick of action 7 (0x00500DAB -> 0x005009E0), see below. Read 10-30 (leftovers 2):
  the invader handler 0x00500B70 (not in the decompile; jump table 0x00501404 for actions 3..13) runs action 7 at
  0x00500C9E: timer-- (+0x36); at 0 it is set to 30 and a hidden member appears; every tick, hidden or not, it then
  dispatches by type (0x00500DAB): archers (0x28) call archer_try_shoot (reload +0xEB counts per call, > col 7, then
  archer_target within col 6; a hit sets action 6, attack_timer 1). Action 6 (0x005011C0) only runs the shot (the
  missile 0x004D9D70 at frame SHOT[army]; frame 1 = the sound, corrected 11-02) while attack_timer != 0, counting it
  to 100 then 0, and never sets another action (the picture tail does, at the wrap: 11-02):
  a hidden archer that shot stays in action 6 (its action-7 timer no longer runs) until the company AI gives it a
  new action (go-attack 0x004FFD00 skips actions 4/5/6). The re-tasking is the regroup FUN_005027e0 (company AI,
  enemy_company_ai_update's B/C countdowns): every member not in action 4/5 gets action 7 with timer 0, so a hidden one
  appears in that tick's figure pass (timer - 1 < 1). Ours (10-30, leftovers 3): a hidden archer acts every tick
  (spawned with a 1-tick delay, `appear` kept as the action-7 timer; invaders._hidden_archer), `_try_shoot` each tick
  (its reload `next_shot` as before); a hit set `a6`: still hidden, the appear countdown stopped, skipped by
  go-attack, until `_regroup` cleared it (appear = now) [**wrong, replaced 11-02**: the shot ends at its wrap, hidden
  or not; "Invader melee ... settled" below]; test_military_hidden_archers_shoot. Re-checked:
  tools/oracle_invasion.py --ours sea (1853..2100) and land (850..1300) print the same lines as before the change
  (1B-inv-sea 2/8, 3/10, 4/10, 10/10 at 1870..1921; 1B-inv-land 896 / 1202 as above): in both exe runs no archer is
  ever in action 6 at a dump (nothing to shoot at in the sandbox while hidden), and ours' hidden archers find no
  target either. Ship passability (grid_ship) ported 10-30 (bugs.md 238, navy.md "Ours"): the exe's 8
  transports and 2 warships step only on ours' routes (tools/oracle_ships.py, 758 moves).
Archer's shot (11-02, bug 393) [v]: `fig_handler_enemy_archer` 0x004B99B0 runs the invader logic (0x00500B70), then
its picture: in action 6 `sprite_anim_step(fight group 0x006381B4[army], .., rate 100)`; when the frame wraps to 0
(after a non-0 frame) action = 7, attack_timer = 0. Rate 100: one frame per `ceil(20·speed / 22)` ticks at the default
game speed (religion.md "Animation"; speed = the group's image +0x3A: 4, Mayan / Oceanid / Atlantean / Ares' warriors
3), so a shot lasts frames x that (Greek 12 x 4 = 48 ticks). The reload (+1 a call only while attack_timer == 0,
archer_try_shoot 0x005009E0) counts from the wrap: the next shot at T + n·p + col 7. Ours (invaders._try_shoot,
data/military.json `armies[a].archer_shot` from tools/build_military.py): the arrow at frame 1 (T + p; at the
target's tile then, or where it stood if it died), the archer stands to T + n·p, next_shot = T + n·p + col 7 (before:
the arrow at T, 12 ticks standing, next_shot T + col 7 + 1); the play look "shoot" spans n·p (data/play/military.json
`ticks_per_frame`); the go-attack skip uses n·p. **Superseded 11-02** ("Invader melee ... settled" below): the arrow
leaves at frame SHOT[army] (T + SHOT·p + 1) to the tile the target stood on at T; frame 1 is the sound; the next shot
at T + n·p + col 7 + 1; the "a6" rule is gone (a hidden archer's shot ends at the wrap too).
### Invader melee (action 5) and the archer's action 6 settled (11-02, bug 393) [v]
Read: the handlers' picture tails (decompile), the invader logic 0x00500B70 (disassembly, jump table 0x00501404 for
actions 3..13: 3 0x500E61, 4 0x500C2A, 5 0x500C19, 6 0x5011C0, 7 0x500C9E, 8 0x500C96, 9 0x500EC0, 10 0x500FE5, 11
0x500C4C, 12 0x500C3B, 13 0x500FF2), archer_try_shoot 0x005009E0, 0x00501480, 0x00501640, figure_fight_tick.
- **Timing**: action 5 of all three runs figure_fight_tick (0x500C19), every tick, ungated: a hit each 24 ticks (above).
  Rate 100 is only in the pictures, and only for some: "invader melee is rate 100" (bug 393's first note) holds for
  archers only.
- **Infantry 0x29** (0x004B9C20): frame 0 while timer < 12, else (timer - 10) / 2 (frames 1..6 two ticks each: a
  12-tick stance, then the swing); `timer == 10` -> FUN_004DB3D0(f, 0) = the attack sound (not the hit). Ours "enemy".
- **Cavalry 0x2A** (0x004B9E20): the same frames, no sound; in a company in mode 2 (`+0x91`, the special roll) with
  timer > 11 (each tick 12..23) it calls 0x00501480(f, col 12): from a random direction (RNG & 7) the first of 8 points
  (±d, ±d) around it with no soldier within d (0x00501640 with a range) -> dest, action 11; the point's y is f.x + dy
  (both coordinates add +0x14: an exe bug, kept). Action 11: figure_move to it; arrived / 10 -> 7; lost (9) -> route
  freed, tried again next tick. It leaves action 5 without fight_end: its foes see it the next tick. In action 7
  (0x00500DD5) mode-2 cavalry charge: a soldier within col 12 -> dest its tile, action 13 (hidden ones too).
  Ours (11-02): invaders.melee_wake / melee_tail (the disengage), `_charge` in the hold, task "disengage" (was missing).
- **Archer 0x28** (0x004B99B0): action 5 draws sprite_anim_step(fight group, rate 100) on anim_frame (the mover's
  reset to 0 by fight_start, b's runs on: an archer attacked in its shot keeps the shot's counter). Ours "rate100"
  (ticks_per_frame, the look's [7] = the counter's origin: the fight start, or the shot's start for b in a shot).
- **0x00501640(x, y, range)** (the hunt's and the charge's soldier search): types 0xB..0xD and hero 0x45, state 1,
  not action 4, not hidden, `+0x84` attacked_by == 0; Chebyshev nearest, first in index order on a tie; with a range
  none past it; with range 0 and none: the first live 0xB..0xD in index order. attacked_by = the invader that took it
  in the hunt (0x005010CF: hunter +0x82 = it, it +0x84 = hunter), cleared by walkers_update 0x004CC8C0 when that one
  is not state 1 or targets another. Ours: a live invader whose target_id is it (heroes and the exclusivity were
  missing).
- **Action 6** (0x005011C0, logic, before the picture tail): nothing while attack_timer == 0; with 1: anim_frame 1 ->
  FUN_004D9D20 (the shot sound, face the target point); anim_frame == SHOT[army] -> the missile 0x34 (0x004D9D70) to
  line_tx / line_ty (+0x4E / +0x50: the target's tile **when the shot began**, archer_target's DAT_00F13944/40), then
  the company's "firing" `+0x5C = 6` if missile_target is 0 or of type 0xB..0xD, 0x27, 0x2E, 0x39, 0x3D, 0x45
  (byte table 0x00501438 -> 0x5013B6), else on (RNG & 7) == 0, and attack_timer 2; with 2..100: +1, past 100 -> 0.
  SHOT = [8,3,14,11,14,11,7,8,4,10,3] (stack table at 0x005011CE; data/military.json `archer_shot.shot_frame`,
  tools/build_military.py reads the instructions). The logic sees the frame the tail drew the tick before: the arrow
  at T + SHOT·p + 1 (T the try_shoot tick, p ticks a frame), not at frame 1 (bug 393's first port: wrong).
- **The wrap**: the picture tail (no hidden check anywhere in 0x00500B70 or 0x004B99B0) sets action 7 and
  attack_timer 0 when the frame wraps to 0: T + n·p. archer_try_shoot (only while attack_timer == 0: reload +0x6B +1 a
  call, past col 7 the target search) is called every tick of 7 (0x500FD8 via 0x500DAB), 9 (0x500FD8 after the move),
  10/13 (0x500FF2, before the hunt): next shot at T + n·p + col 7 + 1. **Hidden archers settled**: a hidden archer
  that shoots ends its shot at the wrap like any other and goes back to action 7; action 6 does not count the
  action-7 timer (+0x36), so it appears the shot's length later; it can shoot again while hidden. The "a6" rule (held
  in 6 until the regroup) is gone. No oracle was run: the disassembly has no branch on +0x65 in these paths, and the
  handler runs for hidden figures (their action-7 timer counts down to the appearance).
- **Archer jam (exe rule, kept)**: attack_timer is reset only by fight_start, the wrap, and try_shoot's own miss
  inside its `== 0` branch. So (1) the regroup FUN_005027E0 (every member not 4/5 -> 7, timer 0) during a shot leaves
  attack_timer 1 or 2.. in action 7: no missile, and no reload until a melee; (2) a fight that ends with attack_timer
  != 0 (any end but the tick after its own killing hit) leaves the archer unable to shoot until its next fight. A shot
  interrupted by a fight resumes after it (action 6 saved) to its next wrap (counter running through the fight); with
  attack_timer 1 then, the missile leaves at the next SHOT frame. Ours: `frozen` (reload_left kept), invaders.py
  fight_started / fight_over / _regroup. **Kept as exe (user 11-02)**: no data/fixes.json entry.
- Ours, the rest (11-02): visible archers act every tick while their reload is due (`step_due` = the next step or hold
  end; `_hold_wake`); a shot or a fight shifts the pending step / hold by its length (the exe's +0x36 does not run in
  6 / 5; ours does not model +0x36 in action 9, so after a shot in 9 the exe's extra wait in 7 is not modelled);
  the regroup now re-tasks members in the same figure pass (exe: action 7 timer 0 -> re-aim at once; ours used to
  wait for the next scheduled act). Ported 11-02 (section below): try_shoot right after a mover's contact in action
  9, the order within a tick, +0x36 in action 9, the combat sounds; the gate's wall-clock phase is ours by design.
- Oracle re-check (tools/oracle_invasion.py --ours, 11-02): the appearance counts are as before (sea archers 2/8,
  3/10, 4/10, 10/10 at 1870..1921 as the exe; land 896 / 1202); positions differ a tile here and there.

### In-tick order, closing-in, re-aim timer, frames, sanctuary troops, sounds (11-02, bug 393 leftovers) [v]
- **Figure order** (walkers_update 0x004CC8C0: slots 1..1999 every tick, after the cycle step; figure_create
  0x004D9FD0 takes the head of the FIFO ring of free ids, figure_delete gives the id back at the tail; walkers.md 2.1).
  Ours: `model.Walkers` (g.walkers) gives every walker a slot (`fslot`) from the same ring and takes it back when it
  leaves; `walkers.move_all` runs the walkers due in a tick in slot order; `walkers.wake_now` puts a walker into the
  running pass when its slot comes after the one acting (else the next tick). Effects on fights: in a fight a starts
  (contact in a's handler), b runs its first figure_fight_tick in the same tick when its slot is after a's: its
  attack_timer is one ahead (anim_t0 = start - 1) and it hits a tick earlier; a figure that leaves action 5 (dies,
  fight_end, disengage) is seen in the same tick by the fighters whose slot comes later (they switch or end at
  once), next tick by the others; two hits due in one tick land in slot order. The ring is saved with the game (the
  exe rebuilds it 1999 down to 1 at every load, sav_load 0x004D9F40: ours keeps the running order across a load,
  bugs.md 315; games from before get slots in id order, the rest free as after an exe load). **New figures (ported
  11-02)**: walkers_update tests every slot 1..1999 as it goes, so a figure created during the pass with a later slot
  runs its handler in that same pass, and one created before the pass (the cycle step: buildings_spawn_walkers,
  formations, events; terrain events; commands) in that tick's pass. Ours: `walkers.add` puts a new walker into the
  running pass (later slot) or the tick's queue (no pass running: ours' day / step-29 systems run before the tick's
  move_all); an earlier slot during the pass: the next tick. `delay` counts from that first call (d: d - 1 ticks
  after it). Every spawn acts one tick sooner than before (walkers, carts, missiles, invaders' arrows, gods' figures
  and bolts); explicitly scheduled first moves (the trainee's 9 ticks, invaders' step-29 releases) are unchanged.
  The tile list (`contact.order`): figure_tile_list 0x004DC860 appends a figure that enters a tile, so tile contacts
  and missile hits take the earliest arrival first (ours took the lowest id): ours by the tick it entered (its last
  step, or its creation) then slot. Settled 11-03 (walkers.md "Tile lists", bugs.md 438): within a tick by the
  order of the entries (walkers.listed); the exe's drawing re-sorts the lists of tiles on screen (not ported).
- **Closing-in** (figure_fight_tick: `tile_progress < 6` -> +1 and figure_fine_step, every fight tick, before the
  count check). Tile progress (+0x39): 15 sub-steps from tile centre to tile centre, the route decision at the centre
  (count 15 -> 0), the tile change and the contact at count 8 (figure_change_tile 0x004D9330). So the mover is at 8
  (no closing-in); b at its own count: ours `units.progress` from its step (ours' step = count 8, then its speed's
  sub-steps a tick; walking past the centre wraps to 0.., standing stops at 15). Below 6 it walks 6 - p fine units
  into its next tile's direction during the first fight ticks. Drawn: look [11] = [p, heading]; scene.js puts a
  fighter at (p + 1) / 15 of a step from its tile toward the heading for p < 8, (14 - p) / 15 back for 8..14 (the
  walk table is one count ahead), the centre at 15 (was 0.3 back for everyone). An invader's pending step after the
  fight comes that much sooner (`invaders._pause`: the step moves on by the fight's length less the closing-in's
  sub-steps at its speed). **Soldiers, wolves, core walkers (ported 11-02)**: figure_fight_end 0x004D61B0 keeps the
  tile progress, and the restored action's figure_move goes on from it the next tick: the first tile change comes
  after 8 - p sub-steps (p < 8) or 7 + 8 (p >= 8: to the centre, the route decision, on to count 8), p = the progress
  at the fight start plus the closing-in. So a mover (8) walks a whole tile (15 sub-steps) before its next step, the
  other one (closed in to 6) 2 sub-steps. Ours stepped on at once the tick after the fight: now `units.resume_ticks`
  (end_fight; crime.py's criminal / watchman fights the same) holds the next step of a walker that walks on (a path,
  or roaming) until then.
- **Invader movement and the +0x36 timer** (disassembly 0x00500C9E action 7, 0x00500EC0 action 9, 0x00500FF2 action
  13, 0x00500C4C action 11): action 7: timer - 1 every tick; at <= 0: 30 again, the hidden one appears, company
  engaged -> 10 (the hunt from the next tick), else dest = company target + layout offset (0x58CFF0 == 8: there) ->
  not there: action 9, figure_move from the next tick. Action 9: timer - 1; at <= 0: 30, dest re-aimed (changed ->
  figure_route_free 0x004D8990; on its own tile -> 7, it stops mid-step); figure_move; arrived (8) or lost (9 / 10)
  -> 7; archer_try_shoot after it (even after a contact: a fresh action 5 can become 6, ported:
  `_shoot_out_of_fight`). Action 13: the target (+0x82) is kept while state 1 and not dying (no re-aim to it while it
  moves); none -> 0x00501640, dest = its tile, route freed; none at all -> 7 timer 50; arrived -> dest = the target's
  tile now; lost -> 7, target 0. The timer does not run in 5 / 6 (fights, shots). Ours (invaders.py, 11-02): `aim_due`
  (+0x36), `_hold` (7), `_march` (9), `_hunt` (13), `_disengage_walk` (11), `_leave` (3) over `_move`: two phases a
  tile, "centre" (the route decision with the dest of that moment; at dest -> arrived; obstacle -> siege) and "step"
  (the tile change and the contact) 8 sub-steps later, the next centre 7 after (speed fractions with the remainder
  carried); a march from standing decides on its first sub-step (the tick after 7 -> 9: the first tile change 9
  sub-steps after it, was at once); an arrival is noticed at the tile centre, then it waits in 7 for the rest of its
  timer (was a fixed 30); a shot's wrap or a regroup stops a march (action 7) with the step it had left kept for the
  next one (`mv_left`). Hunters are woken when their target falls or leaves (`target_gone`). Siege (figure_check_next_
  tile 0x004D8BB0): it stands and tries every tick; the hit only when cycle_step & 3 == 0, cycle_step during the
  walker pass = ours' tick % 51 (simulation_tick 0x00513A30 runs the cycle step, then walkers_update; the step counts
  on after running) (was every 4 ticks from its first hit). Checked against oracle 1B-inv-land: the first released
  infantry and archers (896) are still on the point at 901 in action 9 and one tile off at 918, 3 at 935: steps at
  905 / 920 / 935 (ours now), not 896 / 911 / 926 (ours before).
- **Animation counter of the attacked figure** (figure_fight_start resets anim_frame of the mover only): look [12] =
  the tick whose walk frame the figure's counter equals (walk frames are drawn by the game tick): the start tick for a
  figure whose counter runs every tick (walking, rabble's prologue, wolves), the tick an invader stopped walking for
  one standing in 7 (its counter keeps that frame; drawn frame 0), none (0) after a shot's wrap or for a never-moved
  invader. scene.js adds it for the anim_frame rules (rate100 archers, rabble, wolves "tick"); timer-based rules
  (hoplite, horseman, infantry / cavalry) need nothing.
- **Sanctuary troops' art** (fig_handler_rabble 0x004B31F0, fig_handler_hoplite 0x004B26B0; FUN_004FFB70(army) loads
  an army's sprite set): Artemis' Amazons (formations 0x1F / 0x20) = army 4's archer table (0x006381EC walk, F0 die,
  F4 fight: Zeus_amazon), walk at anim_frame (wrapped at 12 by the rabble prologue: frames 0..11 of 15), melee frame
  attack_timer while < 12 else 0, throwing attack_timer 1..11 else 11, dying timer / 2; Ares' warriors (0x21 / 0x22) =
  0x6401 walk / 0x6402 die min(timer, n) / 0x6403 fight (attack_timer if < n (20) else 0), die and fight with
  direction 0, the attack sound at attack_timer 1 (kind 0x14). Ours: forces.SANCT_LOOK -> walker good "amazon" /
  "ares", data/play/military.json roles "rabble:amazon" / "hoplite:ares" (tools/play_military.py), scene.js rules.
- **Combat sounds**: docs/play/audio.md 4.1.
- **Deliberate deviation (ours), the rate-100 gate's wall-clock phase**: sprite_anim_step with rate 100 steps on a tick
  only when 0x006668EC[speed] fired that game turn (0x00413330, real time); ours counts from the game tick
  (data frame_ticks / ticks_per_frame, scene.js imageStep), so the sim and the view never depend on real time.

### Invaders' walking per figure, muster spot, first target (11-02, bugs.md 410, 411) [v]
Read: 0x00500B70 (disassembly, jump table 0x00501404), figure_move 0x004D1170 / figure_route_walk 0x004D7BD0 /
figure_find_route 0x004D8220 / figure_route_next_dir 0x004D8B10 / figure_check_next_tile 0x004D8BB0 (decompile),
FUN_00502840 and its caller in enemy_company_ai_update 0x004FFFD0. Ours: sim/military/invaders.py `imove`,
`formation_spot`.
- **Route per figure.** 0x00500BBF writes +0x72 = 2 every tick; figure_route_walk with route_id < 1 runs
  figure_find_route (route mode 2: route_search 0x00502EE0 + route_trace(8); sim/military/routes.route2) and, on
  success, sets the tile progress +0x39 = 15, so the figure takes its next route decision from the tile it is on at
  once (a step under way is dropped: < 8 the tile is started again, >= 8 the rest of it is skipped). No route:
  direction_to(here, dest), 8 on its own tile, else 10. Per sub-step (figure_move by speed code: infantry / archers
  6 = 1 a tick, cavalry 11 = 2, 2, 2, 1 with speed_phase +0x2B kept) progress + 1; past 14: next_dir (route used up:
  freed, 8) and check_next_tile (11 siege: it stands, the route kept; 9 blocked), else progress 0; at 8 the tile
  changes (figure_change_tile: the tile contact). Was: a weighted cost field per company target (rounded to 4 tiles)
  and an 8-way BFS near the goal, with the old step kept across stops.
- **Who frees the route** (figure_route_free 0x004D8990): action 7 every tick (0x00500CA1, so 7 -> 9 always starts
  with a new route); action 9's re-aim when the slot's spot changed (0x00500F8F, after +0x5E = company +0x3E; on the
  figure's own tile it goes to 7 instead), then figure_move in the same tick; action 13 when it takes a new target
  (0x005010FA, figure_move in the same tick) and on arrival (8: dest = the target's tile now, 0x0050119A); action 11
  on blocked (9, 0x00500C7A); figure_fight_end 0x004D61B0. Not freed: the cavalry disengage 0x00501480 (no
  fight_end): a horseman that walked into the fight walks out its old route first. Results: 9 -> 8 / 9 / 10 to 7
  (archer_try_shoot after, 0x00500FD8); 13 -> 9 / 10 to 7 with target 0; 11 -> 8 / 10 to 7 (was: 10 retried), 9
  re-routes; 3 (dest = g_land_exit every tick) -> 8 / 9 / 10 gone (state 2; was: 9 retried).
- **Fight ahead** (check_next_tile, types 0x28..0x2A, 0x3F, 0x40): the first figure on the next tile by
  FUN_004DCE40 (not dying; not types 0, 6, 0xA, 0xE, 0x22, 0x23, 0x28..0x2A, 0x2D, 0x34, 0x3F, 0x40; gods of class 9,
  monsters of class 7 only) in action 5 -> 9 (was: not modelled).
- **First target**: a new company's +0x3A / +0x3C is 0 (logical (0, 0)); a soldier released before the first company
  AI pass gets dest = (0, 0) + its offset, off the map: lost (direction 10), back to 7 (oracle: timer 22, d10 at 833).
  Ours had the entry tile, so the first soldiers marched at once. Slot spots are not clamped (were [1, 226]).
- **Hidden timer**: +0x36 counts from the figure's first update, in the spawn tick's pass when the pass is still to
  reach its slot: delay d runs out in update d (ours one tick late before; tm 22 vs 23 at 833).
- **Muster spot FUN_00502840(company, x, y, 1, days < 32)** (0x00500806): (x, y) = the event's lead position
  (+0x3C / +0x3E: the first company of the day's position) + LAYOUT[lead layout +0x40][g_current_figure's slot];
  the AI runs at step 29, outside walkers_update, which leaves g_current_figure = 2000, one past the array: its slot
  byte is routes[0][0x62], 0 in every 1B dump, so slot 0's offset. Then route_search(x, y, -1, -1, 0, 600) with
  0x010DF2C4 = 1 (pops past 600 stop; a tile is reached when its distance > 0), and squares of radius 0..13 around
  (x, y) clamped to the map, row by row; with the edge flag (the first 32 days; the gather branch passes
  days < 32 too) a spot with map_near_play_edge(x, y, 10) is skipped. A spot fits when each of the company's count
  (+0x28) layout tiles (offsets less slot 0's) has no water (4), no rubble / cliff (0x1200), is reached, and its
  tile-list head (ambient 6 / 0x18 skipped, but the head's company is the one tested) is of this company or absent.
  Buildings are allowed (reached at cost 10): a spot on a sanctuary makes the company hit it. None found: the
  target stays the event's target (set before; ours had: the muster point itself). Ours had: around = the lead's
  FIRST position (muster) or the company's own (gather), raw 10 tiles from the 228 grid's edge, grid value 0 only.
- **Range rolls**: the march / gather / halt lengths use the "troops near" result of the lead's search (local_c:
  FUN_00502250 within 16, else 32): with troops 6..9 / 3..5 / 1..3, else 10..13 / 1..2 / 1..2; a company that is not
  the lead has local_c 0 (ours keyed them by "is the lead").
- **Oracle** (tools/oracle_invasion.py --compare; ours after tick K against dump K since the tick order fix of 11-02,
  time-core.md "Ours"): 1B-inv-land (dumps every 17 ticks) 253 figure-dumps, 1B-inv-walk (re/oracle/scenarios/
  invasion-land.txt without shots, ZEUS_STATE_DUMP_EVERY=1 FROM 840 TO 1400, zones 28,31,19,17,16,35,21,37,30, 200 s:
  ticks 840..1111) 3994 figure-ticks (3822 before the fix: the dumps at cycle steps 29 and 50 were skipped): tile,
  action, progress, route present, +0x36 timer all equal for every company while its mode, layout and target equal
  ours' (the special roll is ours' RNG: companies part from day 5). Muster targets equal for days 1..4 ((143, 185),
  (142, 184), (140, 182)); the event's target (+0x42 / +0x44) equals ours' while the lead's mode does. 1B-inv-sea:
  433 figure-dumps, 0 differ (were 7: the transports' route counter, below); the transports' tiles, actions and tile
  progress in all 688 ship-dumps equal.

### Inv-city leftovers settled 11-03 (bugs.md 435) [v]
Oracle 1B-inv-city (rabble company 1) and 1B-inv-city-horse (horseman company 9), tools/oracle_invcity.py compare,
tools/oracle_soldier_walk.py; scratch comparisons of shots, timers and positions per dump.
- **The harness's clock and rate 100.** zeus-run --deterministic gives about 0.7 s of program time a tick, so the
  rate-100 gate (0x006668EC, sprite_anim_step 0x005AF8C0) fires every tick in every oracle run: Nemea's archers drew
  one frame a tick (figure 1845: frames 1..11 at dumps 376..386). Ours counts frame_ticks (4 at the default game
  speed, a deliberate deviation above). The oracle compare tools set `walkers.RATE100_TPF = 1` (the archers' shot,
  the gods' rate-100 looks); the game keeps the default-speed value.
- **The archer's shot phase.** archer_try_shoot 0x005009E0 sets anim_frame 0 and the picture tail steps it in the
  same tick: frame k at T + (k - 1) p, the wrap (action 7, attack_timer 0) at T + (n - 1) p, the arrow at frame SHOT
  seen the tick after it was drawn: T + (SHOT - 1) p + 1, the next shot at the wrap + col7 + 1 (ours before: frame 0
  at T, the wrap at T + n p, the arrow at T + SHOT p + 1: one tick a frame late under p = 1). Action 6 (no
  figure_move, no +0x36 timer) so lasts T + 1 .. the wrap: (n - 1) p ticks (invaders.shot_len). Play: archers' shoot
  block offset 1; the fight counter of an archer attacked mid-shot starts at shot_t0 - p.
- **The reload from the spawn.** +0x6B counts from the archer's first update (1 then), so its first search is col7
  updates later (dump 376 = 286 + 90); ours had next_shot 0 (a shot at the first target in range, 354).
  With these three, Nemea's 16 volleys in 280..1300 come at the exe's dumps (376, 478, 580, ...; ours were 354,
  493, 632, ...) and the companies' firing timers (+0x5C) match: the "4 vs 5" of day 571.
- **No boars on bigcity.** Ours made 4 herds of 7 boars at points of its own (systems/wild.py's forest-edge rule for
  maps without herd points) and one herd stood on the invaders' muster tiles: formation_spot (FUN_00502840) refused
  (20, 66) for a boar at the list head and chose (15, 65). The exe makes herds only at map start (FUN_004E0160)
  and refills only herd formations (formations_pass 0x004DF570: +0x69 == 1, point +0x36 / +0x38, count +0x75):
  tutorial15.sav has none, so no boar ever. Now a map's own point lists stand, empty ones too (the fallback only for
  worlds without the lists), and sav import takes the herd formations (systems.wild herd_timers; a point without
  one: None, never) and the boar figures (type 51, their herd by +0x60). Day 571 equal.
- **figure_hit's group modes** (0x004D54D0) are the formations' current combat modes (+0x91): ours read a soldier's
  mode as spawned and none for invaders, so Nemea's archers hit the holding horsemen for 5 (A 6, D 5) where the exe
  has 4 (mode 1 vs 0: D x 1.5) or 5 (mode 2); units.group_mode. Horse run: the horsemen's damage 40, 85, 130, ...
  as the exe (each one tick later in ours: the soldiers' pass slots, out of scope below).
- **Action 10's tick.** go_attack sets action 10; 0x00500FE5 runs it (not engaged: action 7 and the hunt step) and
  the +0x36 timer of action 7 does not count that tick (company 35's timers 50 at dumps 315 and 316): a hidden member
  appears a tick later than ours did (inv-city: invader positions equal through 635, were through 333).
- **The companies' facing** (+0x6B, FUN_004DE830 in formations_update, cycle steps 5 and 29 before the AI): from
  the layout (1, 0xD -> 0; 2, 0xC -> 2; 0xE, 0x10 -> 6; 0xF, 0x11 -> 4; 3 by the move), or the first member's
  direction while firing; 0 at the spawn. go_attack / morale_check / special_roll then pick the layout by +0x77 (never
  set for invaders) and that facing: 0 -> 1 / 0xF, else 0x11 / 0xD (ours used the landing facing: company 38 went
  from wedge 0xD to 0x11 where the exe took 1). invaders.facings, _layout. Horse run: invader positions equal through
  994 (were through 915).
- Left (not settled): inv-city dump 636: the exe's hunter in action 10 targets figure 52, a horseman at home at the
  palace road tile (nearest_soldier's fallback over hidden figures): ours keeps the soldiers at home as a count (the
  palace companies' member lists, "For contributors"); horse run day 979: the muster spot of company 35 (exe (13, 67),
  ours (12, 67)) reads the tile lists' heads: at (9, 66) and (11, 67) the exe's chain has company 38's newcomer
  before company 35's long-standing member (figure 1853 -> 1878 at dump 946, 1848 -> 1878 at 976). Settled 11-03
  (walkers.md "Tile lists", bugs.md 438): the drawing's tile_walkers_sort 0x00449B30 re-sorted those tiles (on
  screen in that run) by the figures' height in the tile; the simulation's rule is the append. Ours keeps the
  append everywhere (no view in the simulation), so this day stays different from the oracle by design.

### Company AI target choice (11-02, bugs.md 414) [v]
Read: enemy_company_ai_update 0x004FFFD0, FUN_00500910 (step 29), FUN_00501F20, FUN_005020F0, FUN_00502250,
FUN_00502370, route_search_ship 0x00503A60, FUN_004DD130. Ours: sim/military/invaders.py `presence_build`, `reach`,
`troops_spot`, `target_buildings`, `_ai`.
- **Presence grid** 0x00C5BD98 (u8 a tile, not saved: zeros after a load): FUN_00500910 counts 0x00EF57C4 (saved)
  + 1 on every company-AI day while enemy companies exist; past 4 it is 0 and FUN_00501F20 rebuilds the grid:
  cleared, then for every player company 1..34 in use, mobilized (+0x90) and not away (+0x82 < 0), around its lead
  (FUN_004DD130: the first member slot whose figure is not dying, action 4) squares of radius 7, 6, 5, 4, 3, 2, 1, 1
  for member counts (+0x28) > 0..7, each FUN_005020F0(x, y, r, 1): +1 a tile (clamped to the map), +2 more when the
  tile list's head is a player soldier (types 0xB..0xD; the exe tests the head even when its loop skips ambient
  figures 6 / 0x18 to a later one: kept); u8, wraps.
- **The lead's searches**: route_search(position, -2, -2, 0, 100000) with 0x010DF2C4 = 1 (the reach test), then
  FUN_00502250(x, y, 16), else (x, y, 32): over the square (clamped), row by row, the reached tile (distance > 0) with
  the highest presence (strictly higher replaces), found when > 0; local_c = 1 (16) / 2 (32) / 0. Ours runs one 4-way
  BFS over grid_military >= 0 for both (route_search's reached set is the same: values 0..5, limit past the map).
- **Target**: event +0x4A == 0 and local_c == 1 -> the event's target (+0x42 / +0x44) = that tile; else (+0x4A != 0
  zeroes local_c) FUN_00502370(company): class +0x44 (10 = rng_15 % 11), route_search_ship (4-way BFS, hops) from the
  company's position; the palace (type 0x75, state 1) when its main tile is reached -> its tile, returns 1; else over
  the building records, the class then class 9: state 1, presence 0 on its tile, reached, not the palace, its type
  in the list: the earliest index, then a strictly smaller hop count, ties to the first record; types 100..114 and
  composites only through their piece's vt+0x9C false / +0x8C true / +0x98 false; storehouse types 0x3A / 0x3D /
  0x3E: x + 1 (+0x7E = id + 1); nothing found: the company's +0x7A / +0x7C stay. Returns 0 -> +0x68 + 1, past 48
  +0x66 (leave). The event's target = the company's +0x7A / +0x7C. Then every company: +0x98 = event +0x48 (+ 1),
  days + 1, its target = the event's.
- **Lengths for layouts 6 / 10** (the lead's +0x40): no draws; by +0x98: 0, 1 -> march 4, halt 2; 2, 3 -> 5, 3; else
  6, 4; gather 2; local_c 0: march + 6, halt - 1, gather 1. Other layouts draw gather, march, halt in that order.
- Was (ours): troops = the first soldier within 16 / 32 (Chebyshev, no reach, no presence grid); buildings by a
  weighted 8-way field from the company; the palace by any of its tiles; nothing found -> the last event target;
  layouts 6 / 10 drew lengths; the position fell back to any member when slot 0 was gone (the exe keeps it).
- Oracle 1B-inv-city (11-02, tools/oracle_invcity.py; the working city tutorial15.sav, Nemea at land point 1, rabble
  company 1 mobilized at (19, 69); dumps 280..2288 every tick with the presence grid via the patch's
  ZEUS_STATE_DUMP_EXTRA): the troop branch seen (the event's target = the presence maximum, (18, 70) / (28, 71)),
  presence rings at the lead's tile equal in extent (225 cells; values differ where ours' soldiers stand on other
  tiles). Found and ported: (1) the palace target is g_palace_building 0x00FE91E8 = the palace's first 0x75 record,
  its 4x4 main part (layout piece 0: (48, 82) in tutorial15), not the composite's anchor (47, 81); (2) action 10
  (0x00500FE5) of a company not engaged (+0x50 == 0) sets action 7 and runs the hunt step (0x00500FF2: target, dest,
  one figure_move) once; the action stays 7 (the hold: timers and the hidden spawn delay run on); while engaged it
  stays 10 and hunts every tick; only the mode-2 cavalry charge sets 13 (0x00500E55). Ours hunted on in 13 (the
  hidden members walked out at once). nearest_soldier's fallback (any live soldier 0xB..0xD, hidden ones too, when
  every visible one is taken) picks a soldier at home on the palace's road tile (figure 52 at (47, 79)).
  Not settled yet (TODO): the muster spots of companies 36..38 on day 2 ((13, 67) / (12, 67) vs ours (11, 68)), the
  player's rabble march route from the palace (exe via y 72..74, ours via y 69..70) and ours' company 1 standing
  down at dump 775 (the exe's stays mobilized).
- Event +0x4A (settled 11-02): no code writes a non-zero value. A capstone scan of every instruction of .text that
  stores to [reg + 0x4A] (word / byte) or [reg + 0x48] (dword), and every operand at g_events + 0x4A (0x0091743E,
  none), leaves two event writers, both zeroing: FUN_00467630 (event_init_defaults' field reset: +0x3A..+0x46, +0x4A)
  and FUN_00500910 (while no enemy company exists); the other hits are figure / effect / UI structs and stack locals.
  So the value can only come with a record from a file: every invasion record (type 2, 33) of the shipped .pak / .set
  files has 0 (three type-3 records of Open Play Economic have -1). Ours keeps it 0, as the exe in practice.

### Under fire (+0x5E / +0x60) (11-02, bugs.md 415) [v]
Writers: walker_player_missile 0x004BACE0 (0x2D) on a hit: the victim's formation (+0x60), when not 0, gets +0x5E = 6
and +0x60 = the shooter's formation; fig_handler_enemy_missile 0x004BD970 (0x34) on a hit (not a 0x39 / 0x19 victim
of a dead shooter): the shooter's formation gets +0x5E = 6, +0x60 = the victim's (0 for a figure in no company).
Readers: the AI's timers (- 1 a day, all 0 when no player soldier is alive); the AI after the firing test (+0x5C):
+0x5E != 0 -> +0x60 < 1: the target is the event's; that company's member count 0: the target stays; else the
target = that company's position (+0x2E / +0x30: slot 0's tile). Return (no muster or march cycle that day).
FUN_004B10A0 (player soldiers) re-aims only with +0x50 and +0x5E < 1 (player companies never get +0x5E). Ours:
invaders.under_fire from defences.arrow_act; was: never set (and its test kept the target).

### Sea invasions — verified
Transport 0x3F (0x004C24F0): sails to its landing tile, destroys a building or wall there, unloads its payload
as land companies (`enemy_army_spawn_land`, same hidden/staggered rules), message 0xDD "disembarked", leaves for
the sea exit. Warships 0x40 (0x4C2980): navy.md "Warship 0x40" (decoded 10-29, ported line by line 11-02).
- **Route counter** 0x004D4790 (both ship handlers, every update before the action switch, also while waiting in
  action 6): +0x92 + 1, at 100 it is 0 and the route is freed. It counts from the creation tick's pass, so the 100th
  update frees: ours' rr0 = the tick before the first pass (was the first pass's: freed one tick late, every
  transport's tile progress one behind from the first reset on, 11-02, bugs.md 416).
- **Arrival** (FUN_004D3740, direction 8): route_tile_check 0x004D2C60 on the landing tile (the nearest tile with
  route bits 0x1C, no building, terrain & 0x300203 == 0); the result still with terrain 0x300203, or water without a
  road: timer 50, action 6; a wall / tower / building bit there: building_destroyed_by_attack. FUN_004D2B10 unloads
  (enemy_army_spawn_land) and sets action 6; the next update (FUN_004D29D0) turns to 0xE with the sea exit as dest
  once the timer is < 1 (the spent wait leaves 0), and figure_move starts one update later. Ours: unload, then the
  first sail 2 ticks on (51 when route_tile_check found nothing); was 50 always (oracle 1B-inv-sea: the transports
  left 2 tiles earlier than ours).

## End of an invasion (`cities_relations_update` 0x00568C20, daily, step 13) — verified
```
weights: invaders 1 archer, 2 infantry, 3 cavalry (+ loaded transports); player: companies in the city and
ready: rabble 1, hoplite 2, horseman 3
for each attacking city: E = its weight, P = the player's
  (no palace and 0x00FE6A5B == city) or (E > 3P and 0x00FEB4F8 == city)                -> enemy victorious
  (0x00FE6A5B: the last wall_damage_add hit, a building's; 0x00FEB4F8: the palace's last hit; "Siege" above)
  8E < P and (city+0x01 > 5 or E == 0)                                                     -> army withdraws
```
- **Enemy victorious** (0x00482200), first time: the player now pays it tribute (city +0xE0 = 2), message
  0xE0 "Defeat! ... forced to pay this brigand tribute", its companies leave. Second time: the game is lost.
  Nothing else is taken beyond what was destroyed on the map.
- **Army withdraws** (0x00481E80): its units leave (action 3), transports and warships turn back, a commemorative
  monument becomes available (0x00402B00(2)), message 0xDE "Invasion force defeated!" (0x445/0x442/0x444), +0xE0 back
  to 0. No writer of city +0x01 above 1 was found, so in practice the win needs every invader dead (E == 0) and
  P > 0 (hypothesis: killing them with towers alone gives no message).
- A lead company with no reachable palace for 48 days leaves; when the event record goes, the soldiers die.

## Bribe — verified
On arrival message 0xDD offers the bribe (button set 0x38) when bribe < treasury. Paying (`0x00475910`):
treasury -= bribe, "bribes paid" += bribe, then army_withdraws(bribed): units leave (still-hidden ones are moved
to the exit), the bribery message, the monument. Refusing: no handler (the army attacks; hypothesis).

## Enemy sprites — verified
`0x004FFB70(army)` loads the army's sg3 (0x0063B9F8) on first use. Tables 0x006381AC (missile), 0x0063825C
(infantry), 0x0063830C (cavalry), 16 bytes per army: walk, die, fight (, wall attack for archers). Group number n
= atlas group n-1. Unmarked groups 12x8 walk/fight, 8x1 die.

| army | file | missile w/d/f/wall | infantry w/d/f | cavalry w/d/f |
|---|---|---|---|---|
| 0 Greek | Zeus_Greek | 7 / 8 / 9 / 10(8x8) | 1 / 2 / 3(8x8) | 4 / 5 / 6 |
| 1 Trojan | Zeus_Trojan | 4 / 5 / 6(10x8) | 1 / 2 / 3(10x8) | 7 / 8 / 9 |
| 2 Persian | Zeus_persian | 4(15x8) / 6(11x1) / 5(18x8) | 1(15x8) / 3(16x1) / 2(15x8) | 7 / 9(15x1) / 8 |
| 3 Centaur | Zeus_centaur | 4(17x8) / 6(15x1) / 5(15x8) | 1(18x8) / 3(15x1) / 2(15x8) | - |
| 4 Amazon | Zeus_amazon | 4 / 6(15x1) / 5(18x8) | 1 / 3(20x1) / 2 | - |
| 5 Egyptian | Poseidon_Egyptian | 7 / 8 / 9 | 1 / 2 / 3 | 4 / 5(9x8) / 6 |
| 6 Mayan | Poseidon_Mayan | 4 / 5 / 6 | 1 / 2 / 3 | - |
| 7 Phoenician | Poseidon_Phoenician | 4 / 5 / 6 | - | 1 / 2 / 3 |
| 8 Oceanid | Poseidon_Oceanid | 1 / 2 / 3 | 4 / 5 / 6(8x8) | - |
| 9 Atlantean | Poseidon_Atlantean | 4 / 5 / 6(15x8) | 7 / 8 / 9(8x8) | 1 / 2(9x8) / 3 |
| 10 Ares | Zeus_AresWarriors | 1(11x8) / 2(19x8) / 3(20x8) | same | - |

Frames: walk +1 per tick (action 7: frame 0); infantry/cavalry fight `0 if attack_timer < 12 else
(attack_timer - 10)/2`; archer shooting **and in melee** at image rate 100 (wall clock); die `timer/2`, no direction
(cavalry of armies 5 and 9 have directions). Missile 0x34: SprAmbient group 51 (army 0, shadow 50), 71 (army 1, shadow 70),
else 79 (shadow 78), 32 directions.

## Distant battles vs sim/empire/war.py — verified
The casualty tables match. Input differences: raid with P = 0 (exe k = 0, 30 %), E = 0 (exe: a win), flags 0x400
(automatic win when P > E/2), 0x200 (E x 70/100), +10 per hero, triremes x 6. 0x1000 (Ares' help, E x 50/100 for the
comparison and the tiers, the enemy's loss on the unhalved E) is in since 10-30 (sim/gods/aid.py).

### Open (invaders)
Writers of event +0x4A and city +0x01 > 1; the muster's stale `g_current_figure` (exe bug); warships 0x40;
tribute_mode 2 effects; `0x005026B0`.

## Towers, walls and their sentries (decoded 2026-10-28)
Corrections to the "Defences" section above: types 0x81, 0x91, 0x92 are the Doric, Ionic and Corinthian
columns, not towers or gatehouses (`tile_has_tower_type` 0x0045A640 decides where a lintel joins two columns);
terrain flag 0x8000 marks tower and gatehouse tiles (map-terrain.md listed it as unknown); walls have hit
points (a per-tile damage grid, below).

### Tower sentry (figure 0x2E, `fig_handler_ballista` 0x004BB7B0) — verified
The exe's enum says "ballista"; the figure is an archer standing on top of the tower.
Spawn (`buildings_spawn_walkers` 0x0048CFB0, case 0x84):
```
staff = 0 if under construction else workers*100 / col5(0x84)          # col5 = 15 employees
if (palace exists or months_no_palace > 3) and road_network[tower.access] == road_network[palace.access]:
    if road access and staff > 50 and g_building_type_disabled[0x84] == 0:      # (a god-curse countdown)
        keep a tower sentry in b+0xB6 (figure 0x2E at (bx, by), direction 0, action 6)
        if staff >= 100:
            keep a wall sentry in b+0x2A (0x27 created at (bx, bx), owner = palace.created_flag; action 0x0B)
```
(x, x) and the palace's owner byte are exe bugs, kept.
Every tick:
```
route_mode 4; hidden 0; slope_timer 10; +0x1D = 1; slope_offset = 98 (drawn 98 px up)
delete (state 2) if b.state != 1 or b+0xB6 != me or b.workers < 1 or b+0x2A (wall sentry slot) < 1
                 or no palace or b.road_network != palace.road_network
position: the tower's back tile in the current view: view 0 (bx, by), 2 (bx+1, by), 4 (bx+1, by+1), 6 (bx, by+1)
action 4: delete (no death animation)
action 6 (watch): timer++; if timer > 20: timer = 0; if missile_target_search(me, col6 = 13): action 7, reload = col7
action 7 (fire): reload++; if reload > col7 (100):
      no target (search again) -> action 6
      else timer++; face the target (8-way, 0x0058D1F0)
           timer == 1: attack sound (0x004D9D20); timer == 10: arrow 0x2D (0x004D9D70)
           timer > 23: timer = 0; reload = 0
other: action 6
```
- So the sentry needs a wall sentry, i.e. **100 % staff**: at 51..99 % it is created by the daily pass and deleted
  on its next tick (play-mode bug 92). Firing period col7 + 24 = 124 ticks; arrow at timer 10.
- Model 0x2E: hp 120, missile attack 60 (Hard 50, Impossible 45), range 13, rate 100, speed 0.

### Missile target search `0x00501940` and line of fire `0x004D9B80` — verified
```
best_d = range; best_p = 0
for every figure f in index order, state 1, action != 4, not hidden:
    p = 50 enemy soldiers 0x28..0x2A and monsters (col0 8); 30 warship 0x40; 20 transport 0x3F
        (40 if f+0x130; skipped if f+0x6E == 8); 10 wolf 0x3B
    d = Chebyshev distance
    if p > best_p and d < best_d and line_of_fire(me, f): pick f, best_d = d, best_p = p
```
A figure of the same priority never replaces the pick, even when nearer. Line of fire walks the line in fine
units, one check per 8 sub-steps; from a wall/tower tile (0xC000) the first 6 checks are skipped (shooting over
its own wall). Blocking: terrain 0xC001 (wall, tower/gatehouse, tree) and tiles of buildings larger than 1x1.

### Missile flight (0x2D, 0x34, god bolts; 11-02, bug 393) — verified (decompile + oracle 1H-bolt)
- **Line move** (`figure_line_move_init` 0x004D9980, `figure_line_move` 0x004D9750): fine units, 15 a tile, a tile's
  fine origin = tile * 15 (`figure_create`: fine_x = 15 x). Init: line_tx/ty = target * 15, line_dx/dy = |delta|,
  err = 2 minor - major (0 if equal), major = 2 (y) if dx < dy else 1 (x). A sub-step: FUN_004D98E0 (err += 2 minor
  if err < 0 else 2 (minor - major); major delta - 1), the major axis +-1 toward the target (FUN_004D9B40 x /
  FUN_004D9B00 y), and when err >= 0 the minor delta - 1 and the minor axis +-1; line_counter - 1 (min 0) each.
  A call of n sub-steps stops at the first one that finds dx + dy < 1 and returns 1; so a line that ends on the 4th
  sub-step of a call reports it on the next call. Tile = fine // 15 (clamped to the map), relisted on its tile.
  Consequence: toward -x / -y the next tile is entered after 1 sub-step, toward +x / +y after 15.
- **Per call** (0x2D `walker_player_missile` 0x004BACE0): shooter (+0x5A) gone or state 2 -> deleted at once;
  +0x39 + 1 (from 15), past 120 marked gone but this call still moves and tests (106 calls at most); line move 4;
  hit test on its tile **every call** (the start tile too: a +x / +y shot tests the shooter's tile for 3 calls)
  0x004DCE00 -> 0x004DCD30 (the tile list's first figure not in action 4, not hidden, of type 0x28..0x2A, 0x3B,
  0x40, 0x3F unless +0x6E (nationality) == 8, a god of class 10, a monster of class 8); a hit: figure_hit(shooter,
  victim, 1), the victim's company +0x5E = 6 / +0x60 = the shooter's, gone; none and the line done: gone (a god's:
  G_miss, FUN_004DC180(god, 13)); a tower's arrow (shooter 0x2E) loses 3 of its slope_offset a call while flying.
  (0x34 `fig_handler_enemy_missile` 0x004BD970): no shooter check; +0x39 + 1, below 121 the line move, at 121 no move
  and it counts as arrived; hit test 0x004DCE20 -> 0x004DCE40 (first not in action 4, hidden ones too, not of type 0,
  6, 0xA, 0xE, 0x22, 0x23, 0x28..0x2A, 0x2D, 0x34, 0x3F, 0x40; a god only of class 9, a monster only of class 7); a
  hit: figure_hit(shooter, victim, 1) (a deleted shooter's record is zeroed: type 0, attack 0, no damage), the
  shooter's company +0x5E = 6 / +0x60 = the victim's, gone; none and arrived: gone, a god's (type 0x43) line end
  destroys a building on the tile (wall_damage_add(tile, 10, 100)) or plays G_miss, a monster's (0x44) damages it
  (wall_damage_add(tile, 4, 2)).
- **Oracle** (re/oracle/runs/1H-bolt, dumps every 2 ticks): two 0x34 bolts of a god (figures 1717, 1649), 11 dumps:
  fine x / y, line_dx / dy, err, major and tile reproduced exactly by ours (`defences.Flight`) from the start tile;
  +0x39 = 16 after the first call (start 15), line_counter 10 -> 6 after 4 sub-steps.
- **Line of fire** 0x004D9B80 (target search, archers) walks the same line on figure 0: a tile check after every 8
  sub-steps at fine // 15 (from a 0xC000 tile the first 6 checks skipped), done (clear) as soon as the line ends,
  even inside a chunk; blocked by 0xC001 or a building tile with piece & 0xF; past 999 checks blocked. Ours walked
  whole tiles (3 skipped): ported (`defences.line_of_fire`). The building test (11-02): the piece nibble is
  written by building_footprint_place 0x004A04B0 as width - 1 on every tile of a footprint (g_grid_piece 0x00D00D68,
  sav rank 20), so a tile blocks when its footprint was placed wider than 1: plain buildings by their width;
  storehouse and trading post are placed as 1x1 parts (clear); the dock's land 4x4 as parts (clear) and its 2x2
  water square by FUN_004A1350 (nibble 1, blocks); a composite (sanctuary, palace) per piece by refresh_piece_image
  0x0053D300: nibble cleared when the class's vt+0x4C flags & 1 (one picture per tile: a stage-0 rough base, pyramid
  blocks), else size - 1; the palace's pieces are complete on placement; extras 1x1. Ours: `defences.piece_blocks`
  (data/military.json "los_part_width" from tools/build_military.py, `monuments.footprint_width`). Check:
  `python3 tools/los_piece_check.py` (the exe's terrain & 8 and piece & 0xF grids of all 16 tutorial saves against
  ours after import): 0 differences.
- **First call** (walkers_update 0x004CC8C0: slots 1..1999 after the cycle step): a missile made in its shooter's
  handler with a later slot flies in the same pass; an earlier slot from the next tick (oracle 1H-bolt: both bolts
  had earlier slots than their god (1802) and one call by their first dump). Ours: walkers.add (all figures).
- Ours: `defences.Flight` (the line), `defences.fly` (one call), `defences.victim` (the two tests, the tile list in
  arrival order: `contact.order`), `arrow_act` (0x2D / 0x34 arrows of sentries, towers, archers, rabble stones,
  triremes, enemy ships) and `gods/bolts.act` (god bolts). Play mode (scene.js drawArrow): look [1] = t0 = the tick of
  the first call, position = src + (aim - src) * 4 dt / 15 L (within 0.67 fine unit of the Bresenham line).
- Monsters' missile attack (action 28, `monster_missile_attack` 0x00530ED0): ported 11-02, heroes-monsters.md
  "Ranged/special attack, action 28" (oracle 1I-missile equal).

### Arrow 0x2D (`walker_player_missile` 0x004BACE0) — verified
Created by 0x004D9D70 (owner 1, `line_counter` 10, `building_id` = the shooter, a line move to the target
tile, 32 directions). `slope_offset` = shooter's + 18 (116 tower, 36 wall), a tower arrow's falls by 3 per tick.
Moves 4 fine units per tick (`figure_line_move(f, 4)`: 3.75 ticks per tile); deleted past 120 of +0x39 (106 calls), or
at once when the shooter is gone ("Missile flight" above). On its tile after each move (`0x004DCE00` -> `0x004DCD30`)
it hits the **first** non-dying,
visible hostile there (0x28/29/2A, 0x3B wolf, 0x40, 0x3F unless +0x6E == 8, gods col0 10, monsters col0 8),
not necessarily the one aimed at: `figure_hit(shooter, victim, 1)` and the arrow is gone. Arriving with no hit,
it is deleted. Sprites: SprAmbient atlas group 79 (32 directions), shadow group 78; dir32 =
`((direction - 4*view) mod 32 - 13) & 31`; drawn at y - line_counter (10) - slope_offset.

**Pictures by shooter (settled 11-02, oracle 1D-arrows, bugs.md 405).** Both missile handlers pick the picture in
their tail every tick from the shooter's record as it is then; `direction` (+0x11) = `FUN_0058D050(from, to) << 1`
(0x004D9D70, ours `defences.dir16`), `i = ((direction - 4 view) mod 32 - 13) & 31`, image = group start + i, the
shadow (+0x180) the group before + i:
- 0x2D `walker_player_missile` 0x004BACE0: a wall sentry 0x27 / tower sentry 0x2E (`DAT_00777286` = 0) -> group 79 /
  78; rabble 0xB of the sanctuary companies 0x1F / 0x20 (Amazons) or in a Poseidon game -> 79 / 78, other rabble ->
  group 51 / 50, one picture; any other shooter (a trireme 0x39, ...) -> 51 / 50 (a tower of a Poseidon grand
  sanctuary, +0xC4 & 0x20: group 0x6A53 by 8 directions, Poseidon only, not in ours); a god / monster: their own.
- 0x34 `fig_handler_enemy_missile` 0x004BD970: an enemy archer 0x28 by its company's nation (+0x6A, `0x00DB7BAA`):
  0 -> 51 / 50 (one picture), 1 -> group 71 / 70, else 79 / 78; any other shooter, or a deleted one (record zeroed,
  type 0: the enemy warship's arrows too) -> 71 / 70.
Ours (until 11-02 the screen angle, calibrated by eye: about half a turn off): `defences.arrow_group` in the look,
scene.js drawArrow by that group and the formula. Check: `python3 tools/oracle_arrows.py` (run re/oracle/runs/1D-arrows,
scenario re/oracle/scenarios/arrows.txt: 128 arrows poked into the working city — 0x2D of a tower sentry, 0x34 of
archers of nations 1, 2, 0, every direction — the view poked to 0/2/4/6): 1024 of 1024 pictures and shadows equal.
The exe's image numbers (+0x04 & 0x3FFFF) are ours − 1 (the atlas counts from 1).

### Idle and firing animation of the tower sentry — verified
```
N = 12 (group 0x6654); k = anim_frame % N
if (k == 0 or k == N/2) and ready_level < N: ready_level++ else ready_level = 0
if ready_level == 0: anim_frame++
if anim_frame > N-1 and anim_frame % 12 == 5: direction = (direction + 1) & 7; anim_frame = 0
idle: sprite = group 0x6654, frame anim_frame % N;   firing (action 7): group 0x6653, frame timer/2
```
Frames 0 and 6 are held 13 ticks, the others 1 tick; after about 53 ticks it turns clockwise by 1/8.

### Wall sentry (figure 0x27, `fig_handler_wallguy` 0x004B9230) — verified
Walk grid `grid_walls` 0x01039D10 (built by 0x00587E50, rebuilt when an attack destroys something): 0xFF
everywhere; 0 on tower/gatehouse tiles (0x8000); 0 on a wall tile (0x4000) whose three neighbours toward the
back of the view are wall or tower (view 0: (x+1,y) (x,y+1) (x+1,y+1); view 2: (x-1,y) (x,y+1) (x-1,y+1);
view 4: (x-1,y) (x,y-1) (x-1,y-1); view 6: (x+1,y) (x,y-1) (x+1,y-1); corrected 10-29 from the disassembly:
the tile is at [edx+4], v4 reads [edx-0x38C] [edx-0x390] [edx], v6 [edx-0x38C] [edx-0x388] [edx+8]). The view is the
working copy 0x00FA05E8; rebuilt on every turn, sentries moved off by 0x004CFEE0 (docs/play/rotation.md "The view in the sim"). **Only the back corner of a 2x2 block of
wall/tower tiles is walkable: a 1-thick wall cannot be patrolled** (text 19:37 "Walls aren't thick enough to
support Towers"). Route mode 4 = BFS 0x0058B7D0 over that grid.
```
every tick: speed col8 (5); route_mode 4; hidden 0; +0x1D = 1
  delete if b.state != 1 or b+0x2A != me or (grid_walls[tile] not 0..2 and action != 0x0B)
            or b.workers < 1 or no palace or not on the palace's road network
  if +0x40: +0x40--; hidden = 1           # inside a tower/gatehouse and ~24 ticks around it (invisible, untargetable)
  if action != 0x0B: wall_sentry_scan()
  end: on a wall tile slope_offset = 18; on a tower/gate tile +0x40 = 24 (also set by 0x004D7580 on the step)
wall_sentry_scan 0x004D0080: only when enemy_companies (0x00EF57D4) > 0, not fighting/dying, +0x40 == 0;
  every 40 calls: missile_target_search(me, col6) with best distance <= 10 -> action 8 (shoot)
0x0B spawned: walk to the spawn tile (bx, bx), then to (bx, by) = home, action 6 (on route failure: deleted)
6 in the tower (hidden): timer++, at 41: timer 0; if patrol_target(): action 7
7 walk to the post: arrived -> 10; lost -> 6
10 stand at the post: timer++, at 41 -> 9 (dest home)
9 walk home: arrived -> 6; lost -> delete
8 shoot: reload++; if > col7 (60): no target -> 9; else face it, reload 0, sound, arrow 0x2D
```
Patrol target `0x004CFD80`: a per-tower round-robin heading `b+0x34` (0, 2, 4, 6 -> offsets (0,-8) (+8,0) (0,+8)
(-8,0)); p = anchor + 8*offset; the first tile with grid_walls == 0 in growing squares r = 1..6 around p (rows by
y then x) -> found: next heading; else up to 4 tries closer (anchor + 3*offset of each heading, size-2
squares); else stay and retry after 41 ticks. The target can be any tower or gatehouse tile, its own included.
Wall sentries ignore wolves: the enemy-company count excludes herds (+0x69). Model 0x27 (Normal): hp 100,
missile attack 8, range 10 (12/11/10/10/10 by difficulty), rate 60 (50/50/60/65/75), speed 5.

### Walls and gatehouses under attack — verified
`g_grid_wall_damage` 0x00C753B8 (u16 per tile, sav rank 25). `wall_damage_add(tile, threshold, amount)`
0x00492830: damage += amount; over the threshold `building_destroyed_by_attack` 0x004928C0. An attacker whose
next tile (`figure_check_next_tile` 0x004D8BB0, military grid `0x00502BA0`: wall 3 cost 40, tower/gate 4
cost 60) is an obstacle turns to direction 0x0B and adds, when `cycle_step & 3 == 0` (13 ticks in 51):

| attacker route mode | next tile | per hit | destroyed past |
|---|---|---|---|
| 2 (enemy soldiers, hypothesis) / 16 (wolves) | building | +1 | 10 |
| 2 / 16 | wall | +1 (+10 monster 0x44) | 200 |
| 2 / 16 | tower or gatehouse tile | +1 | 400 |
| 8/10 (god) | building / wall | +1 every call | 10 / 5 |

So one soldier breaks a wall tile in about 790 ticks and a tower tile in about 1570 (per-tile counters). A
destroyed wall tile becomes rubble (`0x004DDCB0`), a gatehouse `0x004E5B60`, other buildings their footprint to
rubble (state 4). The maintenance walker repairs bare wall tiles in its range by col9 of building 0x79 (50);
towers and gatehouses are never repaired. Ordinary walkers never step on 0xC000 tiles without road; gatehouse
passages are road (route walkers pass, roamers turn); only 0x27 and 0x2E use route mode 4.

### Defence sprites — verified
- Tower: Zeus_General `SPR_STONE_TOWERS` image 774: one static picture, no manned or firing variant. What
  shows a manned tower is the archer drawn 98 px above its back tile.
- Walls: `SPR_STONE_WALLS` (images 777..812) by the 8-neighbour pattern table 0x00636820 (`wall_set_tile`
  0x0049F950; play mode uses eZeus's equivalent rule, docs/play/buildings.md).
- Sentries (SprMain atlas groups = packed - 1): 80 archer walk (12x8, wall sentry walking, frame anim_frame),
  81 death (8, min(timer/2, 7), removed at 127), 82 drawing and shooting (12x8: tower firing frame timer/2;
  wall sentry shooting frame T[reload >> 1] with T at 0x005F61E8 = 0,1,2,3,4,4..4 (to index 15), then 0),
  83 standing and looking about (12x8: tower idle; wall sentry at its post frames 0..3, anim_frame/3).
- Screen y -= slope_offset (98 tower sentry, 18 wall sentry on a wall tile); +0x1D = 1: drawn in the walker
  pass after the tile's building (on top of the tower or wall: hypothesis).
- Sound: 0x004DB3D0 -> category 0, variant 3 or 4 (on screen only).

### Open (defences)
Which sample the sound table 0x010E0518 cat 0 var 3/4 holds; whether enemy soldiers use route mode 2; what the
"man/unman all towers" order (text 68:174..175) changes; `0x00DB7B30`, `0x00777286`; the remaining rows of the
wall picture table 0x00636820.

## Wolves (figure 0x3B = 59, decoded 2026-10-28)
Handler `fig_handler_wolf` 0x004BD4A0. Model row 59 (Normal): class 5 (predator), hp 20, attack 5, armor 0,
missile armor 0, speed 7 (12 ticks per tile). Route mode 0x10. Action-entry hook: vtable 0x005E4808 slot 1 =
`wolf_enter_action` 0x00569F90 (object 0x00FEB550): 7 -> 0x0056A460, 0xB -> 0x0056AEC0, 0xD -> 0x0056ADD0,
0xF -> 0x0056ABE0, 0x10 -> 0x0056A020, 0x11 -> 0x0056A1F0. All **verified** unless marked.
This replaces production.md "Wolf (partial)" and "Wolves attacking", which had: herders as victims (they are
what wolves fear), prey "unused" (sheep, goats and cattle are the prey), a 1-tile search (7 rings), the roam
offset sign reversed, and the god unnamed (Artemis).

### Pack and spawning
- Map start (`0x004E0160`): for each of the 4 wolf points (`0x00902BB4`, x i16[4], y 8 bytes on) with x > 0:
  `formation_alloc_other(59, .., x, y)`, `F+0x69 = 1` (herd kind wolf), `F+0x29 = 7`, home `F+0x36/+0x38`.
  For wolf i = 0..6: one RNG draw; the first of the 16 offsets of table 0x005F2418 starting at index **i** whose
  tile passes the wolf terrain test; a second draw: `figure_create(1, 59, point + off, dir = rng_a & 7)`;
  action 0x13, formation F, slot i; a third draw: `timer = (rng15 % 25) * 4` (hidden 0..96 ticks); needs 0.
  0x005F2418 = (0,0) (0,-1) (1,0) (0,1) (-1,0) (1,-1) (1,1) (-1,1) (0,0) (1,0) (0,1) (1,1) (2,0) (2,1) (1,2) (0,2);
  0x005F2518 = (-2,1) (-2,0) (-1,1) (-1,2) (-1,-1) (-2,2) (-1,2) (-2,1), then (0,0) x8.
- Wolf terrain test `0x00569D90(t, 0)`: blocked by `t & 0x103AD02A` (rock, building, garden, rubble, wall,
  0x8000, marble, off-map, rock kinds, 0x10000000), water 0x4, marsh 0x40000; trees, meadow, scrub, roads pass.
- Refill (`formations_pass` 0x004DF570): below 7, `F+0x75 += 1` per pass (2 per day); past 26 one wolf: start
  `rng_a & 15`, test `home + 0x5F2518[k]` (terrain, no building), create at `home + 0x5F2418[k]` (an untested tile:
  exe quirk, kept), second draw for the facing; action 0x13, timer 10. One wolf per ~690 ticks per pack.
- Action 0x13: hidden; timer -1; below 1: `+0x148 = 0`, `+0x144 = 8`, action 6 (raw); action 6 enters 0x11 on
  the next tick. Unknown actions (8, 9, 0xA, 0xC, 0xE, 0x12): `+0x144 = 1`, action 6.

### States and needs
`home_link_flag` (+0x5C, u16) = four 4-bit needs, add/sub clamp 0..15 (0x00569E10 / 0x00569E90);
`hi(k)` = nibble > 6 (0x00569F10), `lo(k)` = nibble < 5 (0x00569F50).

| nibble | meaning (ours) | rises | falls |
|---|---|---|---|
| n0 | fatigue | +2 entering 7, 0xD, 0xF | -4 entering 0x11 |
| n1 | restlessness | +2 entering 0x10, +1 entering 0x11 | -4 entering 7, -2 entering 0xD |
| n2 | hunger | +1 entering 0x10, +2 entering 0x11, +4 entering 7 | -4 entering 0xD, -2 entering 0xF |
| n3 | fear of herders | +2 per herder sighting | -4 entering 0xF |

Herder sighting: every tick, before the switch, if `anim_frame == 1` and the action is not 4/5: `wolf_scan`;
a herder found -> n3 += 2. `decide()` (fallback): hi3 -> 0xF, hi0 -> 0x11, hi1 -> 7, else 0x10.
```
enter 0x10 (stand, 0x0056A020): timer = rng15 % 50 + 100; n2 += 1; n1 += 2          # 1 draw
enter 0x11 (lie, 0x0056A1F0):   timer = rng15 % 50 + 100; dir = rng15 & 7 (2nd draw); n2 += 2; n1 += 1; n0 -= 4
tick 0x10: if --timer < 1: hi3 -> 0xF | hi0 -> 0x11 | hi2 -> 0xD | hi1 -> 7 | else 0x10 (re-enter)
tick 0x11: if --timer < 1: hi3 -> 0xF | n0 >= 5 -> 0x11 | hi1 -> 7 | hi2 -> 0xD | else 0x10
enter 7 (roam, 0x0056A460): home = F+0x36/+0x38
   if Chebyshev(pos, home) < 6: dest = (x + 4 - (rng_a & 7), y + 4 - (rng_a & 7))    # 2 draws, -3..+4
        redrawn up to 99 times until passable and at the wolf's own elevation
   else: random_next(); dest = home + 0x5F2518[k], k the first of 16 from rng15 & 15 that is reachable by
        land (route_bfs_land), has no figure (types 0x18/6 excepted) and passes the terrain test; else home
   n0 += 2; n2 += 4; n1 -= 4; dest impassable -> 0x10
tick 7: figure_move(col8); arrived/blocked (8/10): hi2 -> 0xD | hi3 -> 0xF | else 0x10; 9: route_free
enter 0xD (look for prey, 0x0056ADD0): n0 += 2; n2 -= 4; n1 -= 2; (herder, prey) = wolf_scan()
   prey and herder -> 0xF; prey only -> target = prey (+0x82), 0xB; nothing: one tick in 0xD
tick 0xD: decide()
enter 0xB (chase, 0x0056AEC0): target alive -> dest = its tile, else decide()
enter 0xF (flee, 0x0056ABE0): n3 -= 4; n2 -= 2; n0 += 2; herder = wolf_scan().herder
   if the herder is alive and flee_step() finds a tile: dest = it, else decide()
   flee_step 0x00569AF0: d = direction(herder -> wolf); try d, d+1 .. d+6: the adjacent tile that way with
   desirability < 20, inside the map, reachable by land
tick 0xF: figure_move; 8/10: hi3 -> 0xF | hi0 -> 0x11 | hi2 -> 0xD | else 0x10; 9: route_free
```
Hypothesis (a simulation of this machine without herders or prey, ~2.5-tile roams): a wolf stands ~64 % of the
time, lies ~32 %, walks ~4 %, and looks for prey about every 260 ticks.

### Hunting (`wolf_scan` 0x0056A9F0, disasm-checked)
Returns (herder, prey). Own tile, tile-chain order: the first live (state != 0, action != 4) **shepherd (30), goat
herder (31) or bull (cattle 76 with resource 2)** -> herder. Prey on the own tile is not recorded. Then rings
1..7 (Chebyshev, ring sizes 8d from table 0x005F07EA into the offsets 0x0078AD6C; square shape hypothesis): the
first live herder or bull -> return at once; else remember the first live **sheep (49), goat (50) or cow (76,
not a bull)** as prey. So wolves prey on flocks and keep away from herders and bulls.
Chase tick `0x0056AF80` (0xB):
```
figure_move(speed)                        # each new tile runs figure_tile_contact (may start a fight)
8 arrived: not on the prey's tile -> re-enter 0xB (re-aim, no limit)
           else figure_tile_contact(wolf, prey's tile chain); summon_artemis()
9: route_free;  10: hi3 -> 0xF | hi0 -> 0x11 | hi1 -> 7 | else 0x10
summon_artemis: if Artemis's sanctuary (god record 4, 0x00EF5EA8) is complete (0x004EA710): her god figure
    (spawned at the sanctuary's road access if absent) targets the wolf (actions 0x4A/0x4B) and shoots it
    (A = 9999 in figure_hit: a sure kill)
```
Fights by contact (`figure_tile_contact` 0x004D4DA0, hostility row 5 = `[0,0,1,1,1,0,1,1,1,0,0]`): a wolf fights
good guys (soldiers, watchmen, hunters, woodcutters, sentries), invaders, criminals, prey (sheep, goats, cattle,
boar), monsters; never helpless walkers (immigrants, carts, service walkers, **herders**), wolves or gods. Prey
stepping onto a wolf starts a fight too. One hit per 24 ticks each side (figure_fight_tick), damage
`max(0, A - D*A/20)`, death when damage > hp; wolf vs hero or bull: A = D = 0.

| opponent | wolf's hit | wolf hits to kill | its hit on the wolf | its hits to kill |
|---|---|---|---|---|
| sheep hp 3 | 5 | 1 | 0 | - |
| goat hp 6 | 5 | 2 | 0 | - |
| cattle hp 80 armor 5 | 4 | 21 | 0 | - |
| boar hp 9 | 5 | 2 | 1 | 21 |
| hunter 50/3/1 | 5 | 11 | 3 | 7 |
| watchman 20/6/1 | 5 | 5 | 6 | 4 |
| woodcutter 10/4 | 5 | 3 | 4 | 6 |
| hoplite 140/12/6 | 4 | 36 | 12 | 2 |
| horseman 240/15/4 | 4 | 61 | 15 | 2 |

After a kill the victim dies (action 4, 127 ticks); the wolf returns to 0xB on the carcass (contact skips a
dying chain head) until the corpse is deleted and its target link cleared, then `decide()`: it "eats" ~128 ticks
(chain verified, the visible effect hypothesis). Kills do not change the needs.

### Fighting back
- Shepherd / goat herder on guard (action 8, 0x004F7DB0): on frames 1 and 6 of 10, a live wolf within 5 rings
  (0x004F7E70) -> the herder walks to the wolf's tile (action 0xF) and forces the wolf (if not fighting/dying)
  into 0xF (one flee step). On arrival `timer = min(timer, 10)`, back to guard. No damage either way.
- Hunters never seek wolves (prey filter 0x00569990 = boar only); a hunter sharing a tile with a wolf fights it.
- Watchmen chase wolves within 9 tiles every 120 ticks (0x004CD5B0, services.md 6.1), gated by
  `enemy_formations_active` (hypothesis: herds do not count, so in practice they meet by chance).
- Soldiers: rabble, hoplites and horsemen auto-target (0x004B0B60 -> 0x005017A0) enemies, **wolves** and
  monsters within 6 tiles (missile units: range + 4) of their formation slot, nearest first.
- Towers: missile priority 10 (lowest); a tower arrow (60) kills a wolf (hp 20) in one hit. Wall sentries never
  look (no enemy company). Invaders never target wolves (0x00501C50 skips 0x3B).
- Death: action 4, corpse 128 ticks, counted in the pack until deleted; then the refill timer runs.

### Wolf sprites (end of the handler) — verified
`first(group) + frame*8 + dir`, SprMain atlas groups:

| action | group (first) | frames |
|---|---|---|
| 7, 0xB, 0xF walking | 230 (11524) | 12 x 8, +1 per tick |
| 6 | 230 | frame 0 |
| 4 dying / corpse | 231 (11620) | 8, no direction, min(timer, 7) |
| 5 fighting | 232 (11628) | 8 x 8, +1 per tick |
| 0x10 standing, head down | 233 (11692) | 8 x 8, +1 per tick |
| 0x11 lying | 234 (11756) | 8 x 8, +1 per tick |
| 0xD | keeps the last picture | |
| 0x13 | hidden | |

### Open (wolves)
Whether figure_move stays at direction 8 after arrival (the 128-tick meal); the herd's group mode +0x91 (x1.5
rules); whether herds count in 0x00EF57D4 for watchmen; Artemis action 0x50; ring shape at 0x0078AD6C; the hunter
spear handler 0x004BF040 (stub decompile).

## Our implementation: sim/military (10-28)
Play mode (sprites, standards, sentries, arrows, panel orders): docs/play/military.md.
A switchable module (`military on|off`), interface in `sim/military/__init__.py`: `day(g)` from run_day after
recruitment, `act(g, w)` for the walkers it drives, `entered(g, w)` (tile contact hook in walkers.step_to),
`look(g, w)` (play-mode picture), `command`, `export` (/military.json), and for the empire module `invade(g, ev)`,
`march_out` / `march_home`. Its own random generator (the core stream is unchanged; test_military_wolves).
Data: data/military.json (`re/venv/bin/python tools/build_military.py`: model rows per difficulty, armies, target
classes from the exe).
- units.py: classes and g_hostility, figure_hit (missile values for 0xB/0x27/0x28/0x2E, modes x1.5, armor cap),
  fights (a hit every 24 ticks, up to 2 attackers, dying 128 ticks), any walker can be driven (a hunter or sheep a
  wolf attacks) and handed back. contact.py: figure_tile_contact on every tile entered, by either side.
- wolves.py: packs, needs, roam/hunt/flee, refill, as decoded. Ours: idle wolves act at their timer's end (and every
  8 ticks while a herder is near); the herder's chase walk is not drawn (the wolf still flees); no Artemis.
- defences.py: tower/wall sentries, wall-walk grid, patrols, arrows (hit the first hostile figure on a tile).
- forces.py: mobilize (soldiers appear at houses, round robin), formation slots OFF/SPREAD, modes, engage, rabble
  stones, horseman charge, send home, morale and rout, expeditions to the map exit. Ours: standing soldiers act every
  12 ticks near enemies (else 51); at home soldiers are counts, not hidden figures; no auto-defend option.
- invaders.py: spawn at land points, hidden staggered arrival, company AI (mode machine, lead target, 32-day muster,
  march/gather/halt), siege of buildings and walls (thresholds 10/200/400, 13 hits per 51 ticks), archers, the
  daily end check (defeat -> tribute, a second -> city lost; withdrawal -> Victory Monument), the bribe. Ours: the
  weighted route is a shared Dijkstra field per target (4-tile grid) plus a short search near the goal; sea
  invasions land through navy.py; the defensive-aid army is forces.aid_arrive.
- Recruitment (systems/military.py) is frozen while invaders live; mobilized companies are never disbanded.
- alarm.py (10-29): the month counters g_months_since_enemy / g_months_to_next_invasion (day 0; the soonest
  invasion comes from `empire.next_invasion`), the military-service sentiment 0x00566E70 (finance.sentiment_parts
  "military", worst cause 6), auto-defend (`autodefend on|off`, the Options toggle 0x005692D0: refused while
  enemies are on the map): at 1 month before an invasion `auto_defend_mobilize` (labour category 7 -> 5, others
  capped at 4, saved; up to 20 companies, horsemen/hoplites/rabble, mode 0, moved to the rally point with spread
  k); one month after the last enemy `auto_defend_dismiss` (priorities back, every ready company home). Rally point
  (0x004E29B0 / 0x004E28D0 / 0x004E2580): the middle tile of the route from the invasion point to the palace; ours
  uses our land path to the palace's road tile. The exe tests auto-defend with last month's months-to-next and
  then updates it; ours updates first (same month, since our army arrives at 0 months left). The standards'
  peace rules (ready again +80 morale, +1 per 26 ticks while mobilized) now use these counters (daily).
  Test: test_military_auto_defend. Sea: the triremes go hunting when the soonest invasion comes by sea (navy.py
  auto_defend checks); our rally point for a sea invasion is the land one of point 8 (sea rally 0x00DB6940: not
  ported).
- Defensive aid (10-29, world-map.md 6.8): forces.aid_arrive / aid_recall: event companies 21..30 in the same
  companies dict ("event", "city"), the player's own soldier types, spawned at the map entry, mode hold, never rout,
  free deaths; leaving walk to the entry; the last one gone -> empire.aid_lost. Excluded from recruiting, the
  advisor's palace rows, player strength and expeditions. Test: test_military_aid.
- Navy and sea invasions (10-29): navy.py, docs/logic/navy.md "Ours".
- Tests: test_military_wolves, test_military_invasion (boom city), test_military_orders_and_defences (full city).

## Cross-references
- sentiment.md: military-service component (`0x00566E70`), `g_enemy_units_alive >= 4` gate on immigration.
- population-housing: labour force `0x004865A0` (−6 per absent rabble soldier).
- religion: sanctuary troops (Artemis/Ares), god records 7 (speed +50/+33 %) and 8 (+4 missile
  armor for soldiers): identities by record index are hypotheses.
- walkers: action/state machine, `figure_create` `0x004D9FD0`, movement `0x004D9750`.
- trade-empire: distant battles / `+0x82 abroad` writer.

## Open questions
Answered 10-28 (sections above): enemy targeting and siege, how an invasion ends, the bribe, who writes
Formation+0x82, soldier actions 3/6/7/9/0x10/0x11, distant-battle tiers (match war.py), wall HP.
Still open:
- The meaning of event `+0x38` beyond the target class; writers of event `+0x4A` and city `+0x01 > 1` (can an
  invasion be won while invaders live?).
- Monster float paths in `figure_hit`; the piercing missile mode (`0x00777286`); what `0x004C91EA` does.
- `special_range` (col 12) is the cavalry special distance and the enemy archers' special range; other uses.
- The charge formula uses the attacker's own armor, and player horsemen never count charge tiles: kept as in the exe.
- Per-section lists: "Open (soldiers)", "Open (invaders)", "Open (defences)", "Open (wolves)".
