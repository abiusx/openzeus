# City sentiment (popularity), unrest/crime, migration gate

Status: **verified** from the exe unless marked. Addresses refer to GOG `Zeus.exe`.
Building fields: [../re/structs.md](../re/structs.md) plus `re/structs/military-sentiment.tsv`.

## Summary
The city has one sentiment value, 0..100 (`g_city_sentiment` `0x00FE6A68`, city record `0x00FE6A58`
+0x10; 60 at a new game). Twice a month it moves by the sum of six signed components: taxes,
wages, unemployment, food in houses, the city's debt, and soldiers kept under arms in peacetime.
A pull toward the 41–60 band only damps a move; it never reverses one. The sentiment then:
- sets the **migration rate** (immigrants or emigrants per population pass);
- pushes up the **crime/unrest value of each common house** (`b+0xF4`). That value is what the
  house info panel calls the residents' mood. Above 70/80/90/100 the house can spawn a
  disgruntled citizen, mugger, thief or vandal.
- Below 350 inhabitants, before the city has first reached 350, the negative tax, wage,
  unemployment and food components count as 0 and house crime does not rise.

"Per-house sentiment" is the crime value `b+0xF4`. There is no other per-house mood.
Festivals do not change sentiment (no write found). Winning the Games does (+15, `0x005666D0`).
A working Hippodrome adds a bonus by track length after every update.

## When it runs
| What | Where | Frequency |
|---|---|---|
| `sentiment_update` `0x005671A0` | `month_advance` `0x00483C10`, when `month_tick` (`0x0091EC0C`) is 0 or 8 after its increment/reset | twice a month (every 8 × 51 ticks) — verified (disasm 0x00483F15..0x00483F2F) |
| `migration_rate_update` `0x00567450` | first call of `cycle_city_pass_23` `0x00486190` (cycle step 23) | every cycle (16× a month) |
| `crime_spawn_pass` `0x005BFDE0` | cycle step 45 | every cycle |
| health target `0x00566C00` | `month_advance` at month change | monthly |
| health step `0x00566B90` | `month_advance` first call | every cycle |
| births/deaths `0x00566D40` | `cycle_city_pass_23` when `0x00FE916C` set (set at new year by `0x00566D30`) | yearly |

`month_advance` is called at the end of every 51-step cycle (so 16 times a month, despite its
name). `month_tick` counts 1..15 and on 16 is reset to 0 together with the month change.

## Components (each a function returning a signed int)

Common rule **"small-city clip"**: `if v < 0 and population (0x00FE6A7C) < 350 and
!g_sentiment_latch (0x00FEB0DB): v = 0`. The latch byte is set at the top of `sentiment_update`
when population ≥ 350 and only cleared by the city reset `0x00566950`.

### 1. Taxes `sentiment_taxes` `0x00567120` — verified
```
idx = nearest_index(g_tax_rate_levels 0x00641F50 = [0,3,7,9,11,15,20], city tax rate 0x00FE6A60)
      # 0x005697F0: smallest |rate - level|, ties -> lower index; returns -1 if count < 1 (never)
if g_tax_coverage_pct (0x00FE9690) < 11: idx = 0          # "very low coverage uses first row"
v = g_tax_sentiment[idx*5 + difficulty]                    # 0x00FE695C, 7x5 i32 from Tax_Sentiment_Model.txt
small-city clip
```
`difficulty` = `0x00F2A988` (0 VeryEasy … 4 Impossible). Table (`extracted/model/tax_sentiment.json`):

| rate % | 0 | 3 | 7 | 9 | 11 | 15 | 20 |
|---|---|---|---|---|---|---|---|
| VeryEasy | 7 | 5 | 3 | 2 | 0 | −1 | −2 |
| Easy | 4 | 3 | 1 | 0 | 0 | −2 | −4 |
| Normal | 3 | 2 | 1 | 0 | −1 | −3 | −5 |
| Hard | 2 | 1 | 0 | 0 | −2 | −4 | −6 |
| Impossible | 1 | 1 | 0 | 0 | −3 | −5 | −7 |

Tax coverage `0x00FE9690` = `(0x00FE967C + 0x00FE9678) * 100 / (sum of 0x00FE9678..0x00FE9684)`,
computed at the end of the monthly tax function `0x00488250` (time-core-finance).
Names for the 7 levels: text group 286 (`0x11E`). The level table pointer/count/current-value
pointer are installed by `0x005697C0` (`0x00FE6918`=`0x00641F50`, `0x00FE691C`=7,
`0x00FE6920`=0x11E, `0x00FE6924`=`0x00FE6A60`).

### 2. Wages `sentiment_wages` `0x00567170` — verified
```
idx = nearest_index([0,20,26,30,34,40] at 0x00641F38, wage 0x00FE9660)    # 0x00569610
v = [-10,-5,-2,0,2,4][idx]                                                  # 0x00641F20
small-city clip
```
Installed by `0x005695E0` (`0x00FE6928`=`0x00641F38`, count 6, text group 285, value `0x00FE9660`).
Wage at new game: 30 (`0x00566950`).

### 3. Unemployment `sentiment_unemployment` `0x005670D0` — verified
```
u = g_unemployment_pct 0x00FE9654      # unemployed*100/workforce, set in 0x00487750 (labour)
if u < 5:  return 1                     # returned before the clip
if u < 11: return 0
v = -1 if u < 18 else -2 if u < 26 else -3
if population < 350 and !latch: v = 0
```
Added to the total like the others (disasm 0x00567222 `add ecx, ebp`). Oracle check (10-30, bugs.md 312;
`tools/oracle_unemployment.py`, runs 1F-unemp0 / 1F-unemp30): "See a working city" (VeryEasy, sentiment 100) with the
tax poked to 20 % (-2) and g_unemployment_pct poked every tick: at 30 % the sentiment falls 100, 97, 94, 91, 88, 85
(-3 a half month; 0x00FEAF84 = 30), at 0 % it stays 100 (+1 damped to 0 above 90). So unemployment does lower
sentiment in the original (besides crime and the immigration stop that a low sentiment brings).

### 4. Food in houses, and house crime `sentiment_houses` `0x00566F20` — verified
Loops over buildings 1..`buildings_last` (`0x0091EBF8`) with `state == 1` and `is_house`
(`b+0x05`). It updates crime and the hunger counter in the same pass:
```
k = 40 - sentiment                       # sentiment before this update
sum = 0; n = 0
for each such house b:
    if b.population (+0x1C, i16) == 0: b.crime (+0xF4, i32) = 0; continue
    if not (9 <= b.type <= 14):          # common houses only (elite types 9..14 have no crime)
        if population >= 350 or latch:
            if god_sanctuary_finished(god record 10 @0x00EF5FE0):  # Dionysus (hypothesis, see housing doc)
                b.crime -= 20
            else:
                b.crime += house_param(L, 14) + k / 2      # C division, truncates toward 0
        b.crime = max(b.crime, house_param(L, 15))          # crime base
        b.crime = min(b.crime, 100)
    if b.food_types_eaten (+0x7F, u8) != 0:   # set by the monthly food consumption 0x0048B8D0
        f = 2; b.hunger_months (+0xCC, u8) = 0
    else:
        b.hunger_months = min(b.hunger_months + 1, 3)
        f = -1 if hunger_months == 1 else -2 if == 2 else -3
    n += 1; sum += f
v = 0
if n != 0:
    v = trunc(sum / n)
    if abs(sum % n) > trunc(n / 2): v += -1 if sum < 0 else +1     # round half away (strict >)
small-city clip (only when buildings_last > 0; the whole tail is inside that test)
```
`house_param(L, 14)` already returns 0 when Dionysus' sanctuary is finished, but that path is not
reached then. Crime is therefore raised twice a month. Watchmen (figure `0x3D`) lower it by
`model_building_value(0x7C, 9)` (risk reducer) in a 5×5 square (`0x004A5F70`, called from the
walker service dispatch `0x004DFB70`). The same clamps apply there. That code belongs to services.
At creation (`0x00493E70`) common houses get `crime = house_param(L,15)` and elite houses get 0.

### 5. Debt `sentiment_debt` `0x00566EF0` — verified
```
y = g_debt_years 0x00FEB280
v = (-4 if y > 2) + (-3 if y > 1) + (-2 if y > 0) + (-2 if treasury 0x00FE6A64 < 0)
```
`g_debt_years` is incremented by `0x00483B20` (monthly, from `month_advance`) each time the
months-in-debt counter `0x00FEB27C` reaches a multiple of 12. Both are reset to 0 when the
treasury is ≥ 0. Not clipped.

### 6. Military service `sentiment_military` `0x00566E70` — verified
```
s = g_mobilized_hoplite_cos (0x00FEB440) + horse (0x00FEB444) + archer/rabble (0x00FEB448)
if g_months_since_enemy 0x00FE9578 < 2 or g_months_to_next_invasion 0x00FE957C < 2
   or g_enemy_units_alive 0x00FEB084 != 0 or g_enemy_warships 0x00FEB3EC != 0: return 0
v = 0 if s <= 0 else -1 if s < 3 else -2 if s < 6 else -3 if s < 9 else -4 if s <= 12 else -5
```
The counts are made by `formations_count` `0x004DDD70` (step 5/29). They count companies
(figure_groups) of type 0xB, 0xC, 0xD whose byte +0x90 is set (the company has been called to
arms). Reason text: "because you call them to arms too much". So the penalty applies only in
peacetime. There must be no enemy unit or warship on the map. The last enemy must have left at
least 2 months ago: `0x00FE9578` counts months, at month_tick 0, without an enemy. And no invasion
can be due within 2 months: `0x00FE957C` is the minimum months-until-arrival over pending
invasion events, 1000000 if none. See military.md. Not clipped.
Ours (10-29): sim/military/alarm.py `sentiment` (palace companies 1..20 with "mob"), part "military" of
finance.sentiment_parts; 0 when the military module is off.

## The update `sentiment_update` `0x005671A0` — verified (C and disasm)
```
cap = houses_population_sum()               # 0x00487110: sum of b+0x1C over house buildings in state not 0/2/5/6
if cap < population: population_remove(population - cap)   # 0x00567620
if population >= 350: latch = 1
tax = c1(); wage = c2(); unemp = c3(); 0x00FEAF84 = unemployment_pct
food = c4(); mil = c6(); debt = c5()          # this call order (c4 mutates houses)
total = mil + debt + food + wage + unemp + tax
s = sentiment
r = 4 if s<11 else 3 if s<21 else 2 if s<31 else 1 if s<41 else 0 if s<61
    else -1 if s<71 else -2 if s<81 else -3 if s<91 else -4
if s < 41:
    if total < 0: total = min(total + r, 0)      # damped, never above 0
elif s >= 61:
    if total >= 0: total = max(total + r, 0)     # damped, never below 0
s = clamp(s + total, 0, 100); sentiment = s
# worst cause, for the advisor (0x00FEAF90); left unchanged when nothing is negative
worst = 0
if food  < worst: cause=1, worst=food
if unemp < worst: cause=2, worst=unemp
if tax   < worst: cause=3, worst=tax
if wage  < worst: cause=4, worst=wage
if debt  < worst: cause=5, worst=debt
if mil   < worst: cause=6
if 0x00F2A7B0 < 2 and 0x00F2A7C4 == 0: sentiment_change_message()   # 0x00524580, UI only
if month_tick == 0:
    if sentiment <= 80: g_high_sentiment_months (0x00FE9414) = 0
    else:
        g_high_sentiment_months += 1
        if g_high_sentiment_months > 59:        # 60 months in a row above 80
            post message 0xE0 (texts 0x517/0x516); 0x00402B00(6); g_high_sentiment_months = 0
hippodrome_sentiment(0x00FF80D0)               # 0x0056FDC0, after the clamp
0x00FEAF88 = sentiment                         # previous value for change messages
```
Cause codes 1..6 = text 61:39..44 (eat, jobs, taxes, wages, cannot pay workers, called to arms).
The advisor shows "past …" texts (61:45..50) when the recorded cause's component is now ≥ 0
(`0x00518A10`.. `0x00518A70`). For food the test is `population <= 0x00FE96E8`.

### Hippodrome bonus `0x0056FDC0` (ECX = hippodrome object `0x00FF80D0`) — verified
If `obj+5` (working) and track length `0x00782F18` ≥ 4:
row = 0 (<12), 1 (<24), 2 (<36), 3 (<60), 4 (<100), 5 (<200), 6 (≥200);
`sentiment += table[row].c2` where `table` = `0x006429E8`, 5 × i32 per row:

| row | c0 | c1 | c2 sentiment | c3 drachmas/month | c4 |
|---|---|---|---|---|---|
| 0 | 0 | 0 | 1 | 10 | 4 |
| 1 | 0 | 0 | 1 | 20 | 4 |
| 2 | 1 | 0 | 1 | 40 | 8 |
| 3 | 1 | 0 | 1 | 60 | 8 |
| 4 | 1 | 1 | 1 | 100 | 12 |
| 5 | 2 | 1 | 2 | 200 | 12 |
| 6 | 3 | 3 | −5 | 500 | 24 |

This is added **after** the 0..100 clamp, so the stored sentiment can be 101/102 or as low as −5
until the next update. c3 is the monthly income (`0x0056FD30`, treasury and `0x00FE968C`); c0/c1
are relation changes with other cities (`0x0056FC60`, January and July). c4 is not read here.
Text 167:10 confirms the −5 ("your own citizens are not pleased").

### Games victory `0x005666D0` — verified (write); trigger hypothesis
Adds 20 to relations with each city of kind 0..4 that has `+0x170` set, posts message
`0xD81`, then `sentiment += 15` (not clamped). It is called from the games update `0x00565FC0`
in the year phase `(year & 3) == 0` when the games flag byte is set. The win condition was not
traced.

## Migration rate `migration_rate_update` `0x00567450` — verified
```
old = g_migration_pct (0x00FE9184)
s = sentiment
g_migration_pct = 100 if s>=71 else 75 if s>=61 else 50 if s>=50 else 0 if s>=36
                  else -8 if s>=26 else -17 if s>=16 else -25
g_immigrants_due (0x00FE9140) = 0; g_emigrants_due (0x00FE9144) = 0
if population >= 200000: g_migration_pct = 0; return
if g_enemy_units_alive (0x00FEB084) >= 4:   # live enemy soldiers/ships
    if g_migration_pct > 0: g_migration_pct = 0; return         # "War prevents immigration"
elif g_migration_pct > 0:
    if g_imm_cooldown (0x00FE9190) != 0: g_imm_cooldown -= 1; return
    t = g_migration_pct * 12; g_immigrants_due = t/100 + (1 if t%100 else 0)
    g_emi_cooldown (0x00FE918C) = 2
    goto done
if g_migration_pct < 0:
    if g_emi_cooldown != 0: g_emi_cooldown -= 1; return
    if population < 101: return   (both dues 0)
    t = -g_migration_pct * 12; g_emigrants_due = t/100 + (1 if t%100 else 0)
    g_imm_cooldown = 2
done: if old != g_migration_pct: migration_advisor_message(0)    # 0x00523770, UI
```
Per pass: immigrants 12 / 9 / 6 at 100 / 75 / 50 %, emigrants 1 / 3 / 3 at −8 / −17 / −25 %.
`cycle_city_pass_23` then batches them: a due of 1..3 is added to an accumulator
(`0x00FE914C` immigrants, `0x00FE9148` emigrants), and a group is sent out
(`0x00486860` immigrate / `0x00486AB0` emigrate) only when the accumulator reaches ≥ 4 (the whole
accumulator is sent, then reset). A due ≥ 4 is sent at once. Those two functions belong to
population-housing.

## Crime spawns `crime_spawn_pass` `0x005BFDE0` (cycle step 45) — verified
```
for b in buildings 1..buildings_last:
    if state==1 and is_house and not (9 <= type <= 14) and population (+0x1C) != 0:
        for (thr, fig) in [(100, 0x1D vandal), (90, 0x17 thief), (80, 0x1B mugger), (70, 0x16 disgruntled)]:
            # table 0x0065E898: 4 × {i32 threshold, i32 figure type}, walked from the last entry down
            if b.crime >= thr:
                random_next()                               # one full draw (history push + 31 steps of both LFSRs)
                if (g_rand15_a 0x00F137D0) % 200 == 127:   # 0x00F137D0 = state 0x00F137E4 & 0x7FFF
                    spawn_from_house(b, fig)               # 0x005BFF90
```
`spawn_from_house` (`0x005BFF90`): only if the house has no walker (`b+0x2A` == 0). It creates the
figure at the house's road tile (`b+0x26`, `b+0x28`), stores it in `b+0x2A`, sets the figure's
action to 6 and `building_id` to the house, `+0x36 = (b+0x4D & 0xF) + 10`, then calls `0x004D6630`
and clears `+0x44`. One RNG draw is made for every threshold the house meets, whether or not a
figure is created. A house at crime 100 makes four draws per pass.

## City health (adjacent: feeds births/deaths and the labour force) — verified
- Target `0x00FE6A6C`, monthly (`0x00566C00`): over all 4000 building slots with state 1, is_house
  and population p ≠ 0: `score = 50*(b+0x78 healer access ≠ 0) + 50*(b+0x7F food eaten ≠ 0)`;
  `t = (Σ p*score * 100) / (Σ p * 100)` (0 if no people) plus a small-city bonus from `0x00641ED0`
  {(100,80),(200,80),(300,70),(400,60),(500,50),(600,40),(700,30),(800,20),(900,10),(1000,0)}:
  the first pair with population < threshold, else 0; clamp 0..100. It also sets
  `0x00FE6A84` = Σ p over houses with healer access and `0x00FE6A80` = Σ p of fed houses.
- Health `0x00FE6A70` (`0x00566B90`, every cycle) moves 1 toward the target, clamp 0..100
  (message `0x005246B0` on change).
- Yearly births/deaths `0x00566D40`: rate = 6 (>90), 4 (>80), 3 (>70), 2 (>60), 1 (>50),
  0 (>40); otherwise −1 if the **target** `0x00FE6A6C` > 30 (exe quirk: it tests the target, not
  health), else −2 (>20), −3 (>10), −5 (>0), 0 (0). Plus 3 if the sanctuary of god record 12
  (`0x00EF6048`) is finished. rate > 0: `population_add(houses_add_people(pop*rate/100, 0))`
  (`0x00486EF0`, `0x00567650`); rate < 0: `population_remove(houses_remove_people(trunc(pop*|rate|/100),0))`
  (`0x00487020`, `0x00567620`).
- New game: target = health = 80.

## State
| Address | Name | Type | Notes |
|---|---|---|---|
| `0x00FE6A58` | city record (rank 4) | 19184 B | base |
| `0x00FE6A60` | `g_tax_rate` (+0x08) | i32 | percent, 9 at new game |
| `0x00FE6A64` | `g_treasury` (+0x0C) | i32 | |
| `0x00FE6A68` | `g_city_sentiment` (+0x10) | i32 | 0..100 (hippodrome can push outside) |
| `0x00FE6A6C` | `g_health_target` (+0x14) | i32 | |
| `0x00FE6A70` | `g_city_health` (+0x18) | i32 | |
| `0x00FE6A7C` | `g_population` (+0x24) | i32 | |
| `0x00FE9184` | `g_migration_pct` | i32 | −25..100 |
| `0x00FE9140/44` | immigrants / emigrants due this pass | i32 | |
| `0x00FE9148/4C` | emigrant / immigrant accumulators | i32 | |
| `0x00FE918C/90` | emigration / immigration cooldown | i32 | 2 passes |
| `0x00FE9414` | months in a row with sentiment > 80 | i32 | |
| `0x00FE9660` | `g_wages` | i32 | 30 at new game |
| `0x00FE9654` | `g_unemployment_pct` | i32 | labour |
| `0x00FE9690` | `g_tax_coverage_pct` | i32 | finance |
| `0x00FEB0DB` | `g_sentiment_latch` | u8 | pop reached 350 |
| `0x00FEB27C/80` | months in debt / years in debt | i32 | finance |
| `0x00FEAF90` | `g_sentiment_worst_cause` | i32 | 1..6 |
| `0x00FEAE68` | cause copy for advisor (≤7) | i32 | `0x00567680`, step 1 |
| `0x00FEAF88` | sentiment after last update | i32 | |
| Building +0xF4 | crime (house mood) | i32 | 0..100 |
| Building +0xCC | hunger months | u8 | 0..3 |
| Building +0x7F | food types eaten this month | u8 | economy |
| Building +0x78 | healer access countdown | u8 | 0x60 when a healer passes |
| Building +0x2A | current walker figure id | i16 | |

## Cross-references (other subsystems)
- time-core-finance: tax coverage `0x00FE9690` (end of `0x00488250`), `0x00483B20` debt counters,
  `treasury_debt_check` `0x00461520`.
- labour (population-housing/economy): unemployment % `0x00FE9654` (`0x00487750`).
- population-housing: `0x00486860`/`0x00486AB0` (send immigrants/emigrants), `0x00486EF0`/
  `0x00487020` (add/remove people in houses), labour force `0x004865A0` (uses health tier
  `0x006335F0`, wage index `0x006335D8`, difficulty `0x006335C4`, minus 6 × `0x00FEB458`).
- services: watchman crime reduction `0x004A5F70`; healer access `b+0x78` (`0x004A66B0`).
- economy: `b+0x7F` food eaten (`0x0048B8D0`).
- religion: god records 10 (crime) and 12 (births). Their identities are hypotheses.
- UI: `0x00524580` (change messages), `0x00523770` (migration advisor), `0x00519910` (unrest summary
  `0x00FEB544`/`0x00FEB520`: share of houses with crime ≥ 81 and 71..80), `0x005B5AF0` (advisor text).

## Open questions
- God records 10 and 12: which gods? The crime one matches Dionysus. Record 12's +3 % births
  could be Hera or Aphrodite. This needs the record → god id mapping (religion).
- `0x00FE96E8`: compared to population for the "past hunger" text. Its meaning is unknown.
- Games victory trigger (`0x00565FC0`) was not traced.
- `0x00F2A7B0`, `0x00F2A7C4`: gates for the change messages (UI or tutorial).
- Does anything other than the evolve and crime code read `b+0xCC`? No other write was found.
