# Finance: treasury, taxes, wages, debt, yearly accounts

Status: **verified** from the exe unless marked. Addresses refer to GOG `Zeus.exe`.
`city.*` are fields of the city record at `0x00FE6A58` (rank 4, 19,184 bytes). Offsets are given
as `+0xNNNN` and absolute addresses in brackets; the full list is in `re/structs/city.tsv`.
`b+0xNN` is a building record field. When this runs: see [time-core.md](time-core.md) §5.

## Summary
- The treasury (`city.treasury` +0x0C [0x00FE6A64], i32, may go negative) is changed directly by every
  income and expense. Each change also adds to a "this year" ledger line, which the finance
  advisor shows next to "last year".
- **Taxes** are collected once a month, on the new-month branch, from houses whose
  tax-collector coverage timer is still running. That timer is set to 50 cycles when a tax
  collector walks past and loses 1 per cycle. Houses that are not covered pay nothing. Their
  potential tax only shows as "uncollected". There is no city-wide tax without collectors.
- **Wages** are paid once a month, right after taxes: `wage_rate × employed / 120`.
- **Debt**: a month that ends with treasury < 0 adds 1 to `months_in_debt`. Every 12 such months
  adds 1 to `years_in_debt` and posts a message. Any cycle with treasury ≥ 0 resets both. Debt
  lowers sentiment. 36 months in debt fails the scenario. **No interest** is charged: no
  treasury writer computes one.
- The **mint** turns silver ore into money directly: +100 dr per batch, or +400 when blessed.
- Difficulty affects taxes through the model's house column 18 (per difficulty file) and the
  tax-sentiment table. It also scales the starting funds. The code factor for taxes is a flat
  50 % at every difficulty.

## 1. Constants and tables
| what | address | value |
|---|---|---|
| tax levels (%) | `0x00641F50` [7] | 0, 3, 7, 9, 11, 15, 20 (names: text group 286 None…Outrageous); also overwritten from `Model/Tax_Sentiment_Model.txt` by `load_tax_sentiment_model` `0x005B10F0` (same values) |
| tax sentiment | `0x00FE695C` [7][5] (bss, loaded from the same file) | row = tax level, col = difficulty: None 7,4,3,2,1 · Very low 5,3,2,1,1 · Low 3,1,1,0,0 · Normal 2,0,0,0,0 · High 0,0,-1,-2,-3 · Very high -1,-2,-3,-4,-5 · Outrageous -2,-4,-5,-6,-7 |
| wage levels | `0x00641F38` [6] | 0, 20, 26, 30, 34, 40 (text group 285 None…Very High) |
| wage sentiment | `0x00641F20` [6] | -10, -5, -2, 0, 2, 4 |
| tax factor by difficulty | `0x005F7F1C` [5] | 50, 50, 50, 50, 50 (%) |
| starting funds by difficulty | `0x005F7F08` [5] | 150, 100, 100, 100, 80 (%) |
| hippodrome income | `0x006429F4` (stride 20 bytes, 7 rows) | 10, 20, 40, 60, 100, 200, 500 |
| house tax multiplier | `house_param(level, 18)` (model col 18) | Normal: levels 0–2 → 1, 3–6 → 2, 7–8 → 0, elite 9–12 → 16 (VeryEasy 22, Easy 18, Hard 14, Impossible 12) |

Sliders (static initializers): `tax_slider` `0x00FE6918` = {values `0x00641F50`, count 7, text 286,
current → `city.tax_rate`}, set up by `0x005697C0`. `wage_slider` `0x00FE6928` = {`0x00641F38`, 6,
285, → `city.wage_rate`}, set up by `0x005695E0`. `tax_level_index` `0x005697F0` and
`wage_level_index` `0x00569610` return the index of the table value **nearest** to the current
rate. Ties go to the first one: `|cur - v| < best`, scanning upward.

Sim (10-29): `tax N` / `wage N` set the nearest slider value (ties to the lower); old saves' rates are
snapped on load. The play-mode arrows step through the same tables (viewer/play/pages.js).

Defaults (`city_record_reset` `0x00566950`, zeroes the whole record then): `tax_rate = 9`,
`wage_rate = 30`, `standard_wage = 30`, `sentiment = 60`, `health_target = health = 80`.

Starting treasury: `scenario_start_funds` `0x00902948 × start_funds_pct[difficulty] / 100`
(`0x0051D5F0`, `0x005B0660`). `city.balance_last_year` (+0x2CC4) gets the same value.

## 2. Treasury writers (all writers of `0x00FE6A64` in the decompile)
| writer | effect | ledger line (this year) |
|---|---|---|
| `taxes_collect_monthly` `0x00488250` | + taxes | `taxes_common` +0x2C3C, `taxes_elite` +0x2C40 |
| `wages_pay_monthly` `0x00488740` | − wages | `wages_acc` +0x2C14 |
| `treasury_spend_construction` `0x005676A0(cost)` | − cost (not in editor) | `construction_this_year` +0x2C8C, then `ledger_totals_refresh` |
| `trade_export_sell` `0x005B9810` | + `goods_price[g]` (`0x0065B9B0`, rank 8) per batch sold | `exports_this_year` +0x2C64 |
| `trade_import_pay` `0x005B9DA0` | − `goods_price[g]` | `imports_this_year` +0x2C6C |
| `buildings_spawn_walkers`, case mint (type 48) | + 100 or 400 | `silver_this_year` +0x47A8 |
| `hippodrome_income_monthly` `0x0056FD30` | + table value | `hippodrome_this_year` +0x2C34 |
| `0x0046DAA0` (event: pay tribute / give gift) | − amount | `tribute_paid_this_year` +0x44E0 if `ev+2 == 0x1E`, else `gifts_given_this_year` +0x4750 |
| `events_cities_random` `0x00474A80`, `0x004752A0` | + gift | `gifts_received_this_year` +0x4458 |
| `0x00474F60` (event type 29) | + tribute | `tribute_received_this_year` +0x4AA8 |
| `0x004F0010` (figure action) | if treasury > 1000: − max(treasury/10, 1000); elif > 0: set 0 | none (theft-like; owner: walkers) |
| `0x00470800`, `0x004715C0`, `0x0047EE20` | request handlers | see trade-empire |
| `0x00420390` | loading or starting: treasury = funds | – |

## 3. Taxes
### 3.1 Coverage (walkers + cycle)
- `tax_collector_visit_area` `0x004A67C0(x, y, blessed)`, called by the tax collector
  (figure type 7) through `0x004DFB70`. For every house tile in the range with `b+0x1C`
  (population) > 0, it sets `b+0x4E = 50` and `b+0x84 = (blessed != 0)`. `blessed` is
  `b+0xDB` of the collector's home building. It also records the largest col 18 seen in
  `0x00B51544` (copied to the figure at `+0x66`).
- Cycle step 48 (`cycle_buildings_pass_48` `0x00488220`) decrements `b+0x4E` once per cycle while
  it is non-zero. Coverage therefore lasts 50 cycles = 3.1 months after the last visit.

### 3.2 Monthly collection `taxes_collect_monthly` `0x00488250` (new-month branch)
```
pop_taxed_common = pop_taxed_elite = pop_untaxed_common = pop_untaxed_elite = 0     # +0x2C20..+0x2C2C
base_untaxed_common = base_taxed_common = base_untaxed_elite = base_taxed_elite = 0 # +0x2C54..+0x2C60
pop_by_level[0..19] = 0                                                              # +0x268C
r = city.tax_rate                                                                    # percent
for i in 1..buildings_last (0x0091EBF8):
    b = buildings[i]
    if b.state != 1 or b+0x05 (is_house) == 0: continue
    L = b.house_level ; elite = not (L < 9)
    m = house_param(L, 18)
    if b+0x86 != 0: m = m * 110 / 100      # no store to b+0x86 found in the exe (10-29 sweep of
                                           # [reg+0x86] / 0x0092E6DE): always 0, the x1.1 never applies
    p = b+0x1C (population, i16)
    pop_by_level[L] += p
    if b+0x4E == 0:                     # not covered
        if not elite: pop_untaxed_common += p ; base_untaxed_common += p*m
        else:         pop_untaxed_elite  += p ; base_untaxed_elite  += p*m
    else:
        if not elite: pop_taxed_common += p else pop_taxed_elite += p
        t = p*m*2
        if b+0x84 != 0: t = p*m*8 ; b+0x84 = 0          # blessed collector: x4, once (sim 10-29)
        # per-house "taxes paid" display accumulator (does not touch the treasury):
        d = desirability grid 0x00C9B4E8[b.tile] (i8)
        if r == 0: k = 0
        elif d > 80: k = 10r+30   elif d > 60: k = 10r+25   elif d > 40: k = 10r+20
        elif d > 20: k = 10r+15   elif d > 10: k = 10r+10   else: k = 10r
        b+0x88 (i32) += tax_pct[diff] * k * t / 10
        if not elite: base_taxed_common += t else base_taxed_elite += t
f = tax_pct[diff]                                   # 50
elite_tax  = ((r * base_taxed_elite)  / 100) * f / 100
common_tax = ((r * base_taxed_common) / 100) * f / 100
taxes_elite_this_year  += elite_tax                 # +0x2C40
taxes_common_this_year += common_tax                # +0x2C3C
uncollected_elite  += ((r * base_untaxed_elite)  / 100) * f / 100     # +0x2C48
uncollected_common += ((r * base_untaxed_common) / 100) * f / 100     # +0x2C44
treasury += elite_tax + common_tax
total = all four pop counters
tax_coverage_pct (+0x2C38) = 0 if total == 0 else (pop_taxed_common + pop_taxed_elite) * 100 / total
```
All divisions are C integer division with truncation toward zero. "Elite" means house level
≥ 9. Levels 7 and 8 (elite vacant/devolved) count as common.
Example (Normal, 9 %): 100 covered people in level-3 houses (m = 2) give t = 400 and pay
`(9*400/100)*50/100 = 18` dr a month.

`b+0x88` is read only by `house_taxes_paid_display` `0x004956A0`: `(b+0x88 + 5000) / 10000` (house
info panel). `taxes_year_rollover` clears it every year.

### 3.3 This-year figures `taxes_this_year_refresh` `0x004885B0` (cycle step 1 and advisor)
```
base_taxed_common = Σ covered houses (b+0x4E != 0), L<9: p * house_param(L,18)    # no x2, no 110 %, no x4
base_taxed_elite  = same for L>=9
taxes_this_year (+0x2C4C) = taxes_common_this_year + taxes_elite_this_year
taxes_projected (+0x45E4) = (((r*base_taxed_common)/100)*f/100 + ((r*base_taxed_elite)/100)*f/100)
                            * (12 - month) + taxes_common_this_year + taxes_elite_this_year
```
This function also **overwrites** the two `base_taxed_*` scratch fields, but nothing reads them
until the next collection recomputes them. The projection uses `p*m` without the ×2, so it
predicts half of the real monthly tax (**verified** as written; whether that is intended is
unknown).

### 3.4 Year rollover `taxes_year_rollover` `0x004886E0`
`taxes_last_year (+0x2C50) = taxes_common_this_year + taxes_elite_this_year`. Then the common and
elite taxes and the two uncollected sums are zeroed, and `b+0x88 = 0` for every active house.

## 4. Wages
- `city.employed` (+0x2BF4) comes from `labor_allocate_sectors` `0x00487750` (cycle step 1 and
  advisor). It is `min(workforce +0x2B28, Σ jobs needed)`. Owner: economy/population.
- `wages_pay_monthly` `0x00488740` (new month, right after taxes):
  ```
  w = wage_rate (+0x2C08) * employed / 120          # wage is "per 10 workers per year" (text 50:14 "Wage/10")
  treasury -= w ; wages_acc (+0x2C14) += w
  ```
- `wages_this_year_refresh` `0x00488900` (step 1): `wages_this_year (+0x2C18) = wages_acc`;
  `wages_projected (+0x4698) = (wage_rate*employed/120) * (12 - month) + wages_acc`.
- `wages_year_rollover` `0x00488790`: `wages_last_year (+0x2C1C) = wages_acc; wages_acc = 0`.
- `standard_wage` (+0x2C0C, default 30) changes only through scenario events 8/9: +amount if
  the result stays < 46; −amount if the result stays > 4. No simulation rule reads it (raw
  xref scan: the event handlers and the reset are its only users), so it is probably shown in
  the labour advisor only (**hypothesis**).

## 5. Other income
### 5.1 Mint (building type 48, `BUILD_MINT`), in `buildings_spawn_walkers` (cycle step 31)
The mint shares the case with types 0x31, 0x32, 0xD3, 0xD5 (extraction buildings):
```
if b+0x18 (i16) < 1: b+0xD3 = 2
if road/area check 0x004A3B40(x, y, b+0x03) and not 0x00EF6163 and not b+0xDA:
    need = model_building_value(type, 5)                  # employees, 15 for the mint
    pct  = b+0x40 (workers) * 100 / need
    step = 6 if pct >= 100 else 4 if pct >= 75 else 3 if pct >= 50 else 1 if pct >= 25 else 0
    if pct < 1: skip
    case mint:
      if b+0x3C (ore stock, i16) >= 200:
        if b+0x54 (progress) < 100: b+0x54 = min(b+0x54 + step, 100)
        else:
          amount = 400 if b+0xDB else 100 ; b+0xDB = 0
          b+0x54 = 0 ; b+0x3C -= 200
          treasury += amount ; silver_this_year (+0x47A8) += amount
      if building-type flag table 0x00EF60B0[type]: b+0x54 = 0
```
(**verified** reading of `zeus.c` lines 90135–90195. The exact use of `local_44` and the
whole extraction case belong to economy.) So one batch of 200 ore gives 100 dr after
100/`step` passes of step 31. At full staffing that is 17 cycles.

### 5.2 Hippodrome `hippodrome_income_monthly` `0x0056FD30(ECX = 0x00FF80D0)`
```
if obj+5 != 0 and n (0x00782F18) > 3:
    i = 0 if n<12, 1 if n<24, 2 if n<36, 3 if n<60, 4 if n<100, 5 if n<200, else 6
    treasury += income[i] ; hippodrome_this_year (+0x2C34) += income[i]     # 10,20,40,60,100,200,500
```
`0x00782F18` is probably the hippodrome's crowd/horse count (**hypothesis**). The line only
appears in the advisor when `0x00902D88` is set (Poseidon).

### 5.3 Trade, gifts, tribute
Owned by trade-empire. The ledger lines are listed in §2.

## 6. Yearly accounts (finance advisor `0x005951F0`, text group 60)
"Last year" and "so far this year" columns:
| row (text 60:n) | last year | this year |
|---|---|---|
| Taxes in (8) | `taxes_last_year` +0x2C50 | `taxes_this_year` +0x2C4C |
| Exports (9) | `exports_last_year` +0x2C68 | `exports_this_year` +0x2C64 |
| Gifts received (20) | +0x4454 | +0x4458 |
| Mined silver (24) | +0x47A4 | +0x47A8 |
| Tribute received (16) | +0x4AAC | +0x4AA8 |
| Hippodrome (27, only if `0x00902D88`) | +0x2C30 | +0x2C34 |
| **Total income (25)** | +0x2CAC | +0x2CB0 |
| Import costs (11) | +0x2C70 | +0x2C6C |
| Wages (12) | +0x2C1C | +0x2C18 |
| Construction (13) | +0x2C88 | +0x2C8C |
| Bribes/Tribute paid (21) | +0x44E4 | +0x44E0 |
| Gifts and aid given (22) | +0x474C | +0x4750 |
| **Total expenses (26)** | +0x2CB4 | +0x2CB8 |
| Net in/out flow (18) | +0x2CBC | +0x2CC0 |
| Balance (19) | +0x2CC4 | +0x2CC8 |

`ledger_totals_refresh` `0x00488960` (step 1, after construction, and at year end):
```
income_this   = tribute_rcv_this + hippodrome_this + silver_this + gifts_rcv_this + taxes_this + exports_this
expenses_this = tribute_paid_this + gifts_given_this + construction_this + wages_this + imports_this
net_this      = income_this - expenses_this
net_last      = income_last - expenses_last
balance_this  = balance_last + net_this
```
`ledger_year_rollover` `0x00488840` (year end, after the line rollovers):
```
silver_last = silver_this ; tribute_paid_last = tribute_paid_this ; hippodrome_last = hippodrome_this
tribute_rcv_last = tribute_rcv_this ; gifts_rcv_last = gifts_rcv_this ; (all five "this" = 0)
income_last   = taxes_last + exports_last + hippodrome_last + silver_last + gifts_rcv_last
                # NOTE: tribute received is NOT included in last year's income (verified)
expenses_last = construction_last + wages_last + imports_last + tribute_paid_last
                # NOTE: gifts given are NOT included in last year's expenses (verified)
balance_last  = treasury
```
Year-end order: `taxes_year_rollover`, `wages_year_rollover`, `trade_ledger_year_rollover`
`0x004887B0` (exports/imports), `construction_year_rollover` `0x004887E0`, `gifts_given_year_rollover`
`0x00488800`, `ledger_year_rollover`, `plagues_year_rollover` `0x00488820`,
`yearly_stats_rollover` `0x004888E0` (36 ints +0x2D5C → +0x2CCC, then zero). The this-year lines
of taxes/wages are refreshed later by step 1.

Note: `taxes_this_year` and `wages_this_year` are display copies, refreshed only at step 1.
So `ledger_totals_refresh` can see stale values when it runs from construction.

## 7. Debt
```
treasury_debt_check 0x00461520 (cycle step 4):   if treasury >= 0: months_in_debt = years_in_debt = 0
debt_months_update 0x00483B20 (new month, after wages):
    if treasury < 0:
        months_in_debt (+0x4824) += 1
        if months_in_debt % 12 == 0: years_in_debt (+0x4828) += 1 ; message 0xE0 (texts 0xB4C/0xB4D/0xB4E)
    else: months_in_debt = years_in_debt = 0
scenario_goals_check 0x00526990: if no goal decided and months_in_debt >= 36:
    city+0x4708 = city+0x45FC = 0xB91, city+0x45FE = 0xB90 ; return -1 (scenario lost)
```
Sentiment from debt: see §8. Text group 61 mentions that past debt blocks immigration; that rule
is in population (cross-ref, not verified here).

## 8. Sentiment inputs from finance (shared with military-sentiment)
`city_sentiment_update` `0x005671A0`, run on days 0 and 8 of every month:
```
hp = houses_population_sum 0x00487110        # Σ b+0x1C over houses with state not in {0,2,5,6}
if hp < city.population: population_decrease 0x00567620(city.population - hp)   # clamp >= 0, update peak
if city.population > 349: city.big_city_flag (+0x4683) = 1
small = city.population < 350 and not big_city_flag
tax   = tax_sentiment[ (0 if tax_coverage_pct < 11 else tax_level_index()) ][difficulty]   # 0x00567120
wage  = wage_sentiment[wage_level_index()]                                                # 0x00567170
unemp = u<5: +1 ; u<11: 0 ; u<18: -1 ; u<26: -2 ; else -3      (u = unemployment_pct +0x2BFC)  # 0x005670D0
for tax, wage and unemp: a negative value becomes 0 when small (unemp: only the negatives)
houses = sentiment_from_houses 0x00566F20    # also updates house crime b+0xF4 (cross-ref)
mil    = sentiment_from_military 0x00566E70  # from city+0x49E8..+0x49F0 (war), 0 unless at war
debt   = sentiment_from_debt 0x00566EF0:
         (-4 if years_in_debt > 2) + (-3 if > 1) + (-2 if > 0) + (-2 if treasury < 0)
D = mil + debt + houses + wage + unemp + tax
s = city.sentiment (+0x10)
drift = +4 if s<11, +3 <21, +2 <31, +1 <41, 0 <61, -1 <71, -2 <81, -3 <91, else -4
if s < 41 and D < 0:     D = D + drift ; if D > 0: D = 0
elif s >= 61 and D >= 0: D = D + drift ; if D < 0: D = 0
s = clamp(s + D, 0, 100)
worst-cause id (+0x4538), not reset when every component is >= 0:
   1 houses, 2 unemployment, 3 tax, 4 wages, 5 debt, 6 military   (strictly most negative, checked in that order)
on day 0: if s >= 81: high_sentiment_months (+0x29BC) += 1, and when > 59: message 0x516/0x517,
          0x00402B00(6), counter = 0 ; else counter = 0
0x0056FDC0() ; city+0x4530 = s
```
`city.unemployment_copy` (+0x452C) gets `unemployment_pct` before the house term.

## 9. City record fields used here
See `re/structs/city.tsv`. Most important: `tax_rate` +0x08, `treasury` +0x0C, `sentiment` +0x10,
`health_target` +0x14, `health` +0x18, `population` +0x24, `workforce` +0x2B28, `employed` +0x2BF4,
`unemployment_pct` +0x2BFC, `wage_rate` +0x2C08, `tax_coverage_pct` +0x2C38, `months_in_debt` +0x4824,
`years_in_debt` +0x4828.

## Cross-references
- `0x00487750` labour allocation, `0x00487BA0` worker assignment (economy).
- `0x005B9810` / `0x005B9DA0` trade sale / purchase (trade-empire). The export batch is 100 units
  (400 for good 19).
- `0x004F0010` figure that drains the treasury (walkers / religion?).
- `0x00566F20` house crime and food/feeding counter (services/population): `b+0xF4` crime,
  `b+0xCC` counter, `b+0x7F` flag.
- `0x00566E70` military unrest (military-sentiment).

## Open questions
- Who sets `b+0x86` (the 110 % tax multiplier)? No direct write was found (maybe via memcpy or a
  computed pointer).
- `b+0xDB` "blessed" flag (set by `0x004128C0` for buildings linked to types 63/64): which god or
  effect.
- Is `taxes_projected` meant to be half the real tax (×2 missing)?
- Event type 29/32 names. `0x0047EE20` (day 12) touches the treasury: request payments?
- `0x00782F18` meaning (hippodrome).
