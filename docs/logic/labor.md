# Labor: workforce, categories, employment

Status: **verified** unless marked. Addresses: GOG `Zeus.exe`. Population side: [population.md](population.md).

## Summary
There are no labor-seeker walkers. Once per 51-tick cycle the game computes a workforce from the
occupants of common houses (elite houses give no workers) times a participation percentage
(difficulty + wage + health), removes 6 workers per rabble soldier, staffs towers and warship
wharves first (outside the priority system, §2.1), then splits the rest between 8 labor
categories by player priority (5 = very high … 1 = very low, then 0 = no priority). Inside a category, six "essential" building types are
staffed before the others. Each building then gets `employees = col5 × category fill %`, and the
remainder is handed out building by building. Buildings need labor access (road-connected) and
must not be halted. Production and walker generation read `employees/col5` (other agents).

## 1. Data
- `model_building_value(type, 5)` `0x00433D50` = employees needed (model col 5, JSON `employees`).
  A building with `b+0xDA` ≠ 0 (set on creation for composite types: sanctuaries, monuments,
  pyramid parts; hypothesis: under construction) counts as 0.
- Labor category = `0x005F6378[type*8]` (field +0x10 of the 32-byte building-type rows at `0x005F6368`),
  copied to `b+0x42` in step 25a. −1 = none. Names (text group 50): 0 Husbandry, 1 Industry,
  2 Storage & Distribution, 3 Hygiene & Safety, 4 Administration, 5 Culture (Poseidon label:
  Science), 6 Mythology, 7 Military, 8 = towers (0x84) and warship wharves (0x88), staffed apart.
- Essential types (counted twice: in the category and in its "essential" sub-need):
  0x4C infirmary, 0x79, 0x7C guardpost, 0x84 tower, 0x85 horse ranch, 0x88 warship wharf
  (names from `extracted/model`; 0x84/0x88 are category 8 and never reach the category code).
- Category record `g_labor_cat[10]` at `0x00FE9584`, 20 bytes each:
  `+0 need`, `+4 assigned`, `+8 need_ess`, `+0xC assigned_ess`, `+0x10 priority` (0..5).
- Totals: `0x00FE9580` workforce (pool), `0x00FE964C` employed, `0x00FE9650` unemployed,
  `0x00FE9654` unemployment %, `0x00FE9658` displayed unemployment %, `0x00FE965C` unfilled jobs.

### Eligibility `labor_eligible(b)` (steps 25a and 25c)
```
state == 1 and type != 0x86 (25a) / b+0x4A == 0 (25c)
and (0x0040AA20(type) or b+0x38 == 0)      # 0x0040AA20: type listed in 0x005E8578 table
                                           #   (agora vendors); else only the main part (+0x38 == 0)
and cat >= 0 and cat != 8
and (cat not in (0,1,7) or not building_industry_halted(b))   # 0x004873F0
and (not sanctuary(type 0x54..0x62) or construction progress 0x0053ECA0 >= 100)
and b.labor_access(+0x18) > 0              # 100 if the access tile +0x26/+0x28 chosen in step 21 is a road
                                           #   (step 12 0x00484FE0); step 21 only picks roads reachable
                                           #   overland from the entry (buildings.md §6); no road-network test
```
`b+0x4A` ≠ 0 excludes the building from 25c only (hypothesis: fire/ruin timer, set by
`0x004950B0`). `building_industry_halted 0x004873F0`: per type — industry shut down by the
player for its resource (`0x00FE930E[b+0x43]`, and specific flags for 0x25, 0x2C, 0x2D, 0x2E,
0x30, 0xD6, 0xD8), tower: `0x00FEAF24` == 0, wharf 0x88: `b+0xC4` bit 0.

## 2. Workforce — in step 23 (`labor_pool_compute 0x004865A0`)
```
d = difficulty 0x00F2A988;  w = 0x00569610()  (index of the int array *0x00FE6928, count
    0x00FE692C, closest to *0x00FE6934, first wins; -1 if empty) — hypothesis: wage level
h = g_health 0x00FE6A70;  u = 4 if h>=80 else 3 if h>=65 else 2 if h>=35 else 1 if h>=20 else 0
pct = T_diff[d] + T_wage[w] + T_health[u]
      T_diff   0x006335C4 = 50,45,40,37,35
      T_wage   0x006335D8 = -10,-6,-3,0,3,5   (w = -1 reads 0x006335D4 = 35)
      T_health 0x006335F0 = -2,-1,0,1,2
pool = (Σ occupants of houses in the house list with type < 9 or > 14) * pct / 100
formations_refresh()                       # 0x004DE210 (military)
pool -= 6 * 0x00FEB458                     # rabble soldier figures (type 0x0B) of
                                           #   common-housing formations (hypothesis)
for i in 1..highest building, state == 1:
    if type == 0x88:   b.employees = 0
        if not (b+0xC4 & 1) and 0x004A3B40(x, y, size): take(b)
    elif type == 0x84: b.employees = 0
        if 0x00FEAF24 and (0x00FEAEDE or 0x00FEAEA0 > 3)
           and region(0x00C4F288 at b's road entry +0x26/+0x28)
               == region(at road entry of building 0x00FE91E8): take(b)
    take(b): e = col5 (0 if b+0xDA); if pool < e: b.employees = pool; pool = 0
             else: b.employees = e; pool -= e
pool = max(pool, 0)
```

Ours (2026-10-28): sim/systems/labor.py `workforce_pct` with the tables in data/rules.json `workforce`;
difficulty index 0..4 = VeryEasy, Easy, Normal, Hard, Impossible (Model/*_<difficulty>.txt), Normal = 40.
The rabble deduction (6 per soldier away) stays out: our soldiers never leave home.

### 2.1 Towers and warship wharves are not in the Military priority (verified)
Category table `0x005F6378 + type*32`: 0x84 tower = 8, 0x88 warship wharf = 8; Military (7) =
0x83 gatehouse, 0x85 horse ranch, 0x86 corral, 0x87 armory, 0xD4 chariot workshop.
- Towers/wharves are staffed in **step 23** (`labor_pool_compute` 0x004865A0, building loop
  around `0x00486712`), straight from the pool, building by building in id order, *before*
  step 25 sees the pool. `labor_allocate` only reads the remaining pool.
- `labor_needs_collect` 0x00487240: `if cat >= 0 and cat != 8` → they add nothing to need[7].
- `labor_allocate` 0x00487750 and the advisor rows (`0x00590920`, loop `c < 8`, shows
  `need[c]` / `assigned[c]` of `g_labor_cat` 0x00FE9584) cover categories 0..7 only, so the
  Military priority does not touch them and the Military row does not count them.
- 25c (`0x00487BA0`) skips them (`cat != 8`), so the step-23 value stays.
The only ways to keep them from taking workers: tower switch `0x00FEAF24` (global, toggled by
`0x0040A4A0`; the Military tab's button, text 68:174 "Click to send tower guards home" /
68:175 "Click to man all towers", tower panel 170:10 "orders to remain unmanned"; 0 also makes the tower "halted" in
`0x004873F0`) or the wharf's own halt bit `b+0xC4 & 1`. Towers also need the palace (or < 4
months without one) and the palace's road network. A player who puts Military last therefore
does **not** make towers/wharves take only spare workers; they are filled first (a full
warship wharf = 100 workers, model col 5).

## 3. Step 25 — three functions in a row
### 25a `labor_needs_collect` `0x00487240`
Clears `need, assigned, need_ess, assigned_ess` of records 0..9 (priority kept). For each
`labor_eligible` building (25a variant): `b+0x42 = cat`; `need[cat] += col5'`; if essential type:
`need_ess[cat] += col5'` (col5' = 0 when `b+0xDA`).

### 25b `labor_unemployment_update` `0x00487630`
Calls `labor_allocate 0x00487750`, then smooths the shown rate:
`shown = actual if actual < shown or actual−5 < shown else shown + 5`; cap 100. If unfilled jobs
went from 0 to > 0, year (`0x0091EC04`) ≥ `0x00902928` and cooldown `0x00FD3744` < 1: cooldown = 6,
message 0xB52/0xB53/0xB54.

### `labor_allocate` `0x00487750`
```
for c in 0..7: assigned[c] = 0; if priority[c] > 5: priority[c] = 3
total_need = Σ need[0..7]  -> 0x00FE964C
if pool >= total_need:
    for c in 0..7: assigned[c] = need[c]; assigned_ess[c] = need_ess[c]
    unfilled = 0
else:
    avail = pool
    for p in 5,4,3,2,1,0:              # 0 handled by the copy at 0x00487984, same rules
        E = Σ need_ess[c], O = Σ (need[c]-need_ess[c])   over c with priority[c] == p
        if p != 0 and E < avail: fe = 100; fo = 0 if O == 0 else min(100, (avail-E)*100/O)
        elif p != 0 and E != 0:  fe = avail*100/E; fo = 0
        elif p == 0:             same as p != 0 when E < avail; else fe = fo = 0
        else:                    fe = fo = 0
        for c in 0..7 with priority[c] == p (in order):
            a = need_ess[c]*fe/100; assigned_ess[c] = a; E -= a
            o = (need[c]-need_ess[c])*fo/100; assigned[c] = a + o
            avail -= a + o; O -= o
            if avail < 1: break
        # rounding remainders, one worker at a time, categories in order 0..7
        while E > 0 and avail > 0:
            for c in 0..7 with priority p and assigned_ess[c] < need_ess[c]:
                assigned_ess[c] += 1; assigned[c] += 1; avail -= 1; E -= 1
                stop when E < 1 or avail < 1
        while O > 0 and avail > 0:
            for c in 0..7 with priority p and assigned[c] < need[c]:
                assigned[c] += 1; avail -= 1; O -= 1; stop when O < 1 or avail < 1
        if avail < 1: break (jump to the p = 0 pass, which then assigns 0s)
    employed (0x00FE964C) = pool
    unfilled (0x00FE965C) = Σ (need[c] - assigned[c]) over 0..7
    if unfilled < 10: 0x00633604 = 1
    elif 0x00633604: 0x00633604 = 0; 0x00523640(0)        # "workers needed" notice
unemployed = pool - employed  (0x00FE9650)
pct = 0 if pool == 0 else unemployed*100/pool  (0x00FE9654)
if pct > 9: if 0x00633605: 0x00633605 = 0; 0x005236A0(0)   # "unemployment" notice
else: 0x00633605 = 1
```
Note for p = 0 the decompiled loop enters with p = 0, sets fe = fo = 0 and zeroes the p = 0
categories, then the dedicated pass at `0x00487984` recomputes them with the formula above.
Categories of priorities skipped because the workforce ran out keep 0 (cleared by 25a).

### 25c `labor_assign_buildings` `0x00487BA0`
```
for c in 0..8:
    if assigned[c] < need[c]: ess_left[c] = assigned_ess[c]; oth_left[c] = assigned[c]-assigned_ess[c]
    else: ess_left[c] = oth_left[c] = 0
pass 1: for i in 1..highest, building passes the 25c eligibility (b+0x4A == 0 ...):
    b.employees = 0                     # done as soon as cat is valid, before halted/access tests
    (if still eligible:)
    if assigned[9] < need[9]:           # BUG: index is the loop leftover 9; record 9 is always
        b.employees = col5'             #   0/0 (cleared in 25a) -> branch never taken
    else:
        if essential: f = 0 if need_ess[c]==0 else assigned_ess[c]*100/need_ess[c]
        else: f = 0 if need[c]-need_ess[c]==0
                  else (assigned[c]-assigned_ess[c])*100/(need[c]-need_ess[c])
        e = min(col5' * f / 100, col5')        # trunc
        b.employees = e; (ess_left or oth_left)[c] -= e
pass 2: same order and eligibility, if b.employees < col5':
    pool_c = ess_left[c] or oth_left[c]
    if pool_c >= 1: b.employees += 1; pool_c -= 1
    else: b.employees += pool_c; pool_c = 0
if every ess_left[0..8] and oth_left[0..8] == 0: return
pass 3: same, if b.employees < col5': give min(col5' - b.employees, pool_c)
```
Effect of understaffing: `b+0x40/col5` drives production progress (`cycle_buildings_pass_20
0x00485360`: progress `b+0x54` += (employees·100/col5)/10 per cycle) and the info panel
(`0x00570B20`: `0x00FFA148` = employees·100/col5); walker spawning is the walkers agent's.
Problem bits (`0x00564560`): 0x40 no labor access or no employees, 0x80 understaffed.

## Open questions
- `0x00569610` array (wage table?) and `0x00F2A988` = difficulty (hypothesis, set at game start).
- `0x00FEB458` = count of type-0x0B figures in formations whose `-0x3F` byte is 0 (rabble?).
- Tower switch `0x00FEAF24` (UI meaning). `0x00FEAEDE`/`0x00FEAEA0`/`0x00FE91E8` = palace exists /
  months without palace / palace building (names in re/names/military-sentiment.tsv).
- Category 5 label "Science" in Poseidon (`0x00590920`) vs model category 8.
