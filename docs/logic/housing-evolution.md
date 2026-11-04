# Housing: evolve / devolve check

Status: **verified** from the exe unless marked.

> **Correction (from the population-housing pass):** `0x00484660` documented below is the
> **info-panel** version of the check (it computes the "why can't this house evolve" reason).
> The simulation evolves houses in `houses_evolve` `0x004FE290` (per-type handlers, table
> `0x0063B91C`) through the requirements check `0x004843D0`, with a devolve counter
> (3 failures for common houses, 10 for elite, `b+0x82`). See [housing.md](housing.md). The
> house-table columns and `house_param` below are still correct. Addresses refer to GOG `Zeus.exe` (SHA-256 382bcd28…).
Building record fields: see [../re/structs.md](../re/structs.md).

## Data
House table: 13 rows × 21 ints, loaded from `Model/Zeus_Model_<difficulty>.txt` "ALL HOUSES" by
`load_zeus_model` `0x005B0C20` into `0x0078B24C` (row stride 84 bytes). Rows: 0..6 = Hut,
Shack, Hovel, Homestead, Tenement, Apartment, Townhouse; 7 = Elite vacant; 8 = Elite devolved;
9..12 = Residence, Mansion, Manor, Estate.

Columns follow the **letters** a..u in the file header (the `// n` comment numbers are stale):

| col | meaning | used by evolve check |
|---|---|---|
| 0 | devolve if desirability ≤ this | yes |
| 1 | may evolve if desirability ≥ this (of the *next* level, see below) | yes |
| 2 | culture/appeal needed (`b+0x80`, signed byte) | yes |
| 3 | water needed (flag): requires `b+0x35` ≠ 0 | yes |
| 4 | stadium/museum (education) needed: `b+0x6C` (u8) ≥ value | yes |
| 5 | % of population made soldiers | no (military) |
| 6 | max horse storage | no |
| 7 | horses needed: `b+0x72` (i16) ≥ value | yes |
| 8 | number of food types needed: count of held food goods ≥ value | yes |
| 9 | fleece needed: `b+0x68` (i16) | yes |
| 10 | olive oil needed: `b+0x66` (i16) | yes |
| 11 | wine needed: `b+0x64` (i16) | yes |
| 12 | arms needed: `b+0x6A` (i16) | yes |
| 13 | max armor storage | no |
| 14 | crime risk increment | no |
| 15 | crime risk base | no |
| 16 | unused (no read found) | – |
| 17 | population capacity | no |
| 18 | tax-rate multiplier | no |
| 19 | unused | – |
| 20 | disease risk increment | no |

## Accessor `house_param(level, col)` `0x00433D80`
Returns `table[level][col]`, except:
- col 0 or 1: if **Aphrodite** (god record 6, `0xEF5F10`) has an *active* sanctuary
  (`god_sanctuary_active` `0x004E9440`) → value − 10.
- col 14: if **Dionysus** (god record 10, `0xEF5FE0`) has an active sanctuary → 0.
God identities verified (religion pass). "Active" = sanctuary Building+0x32 (`sanctuary_activity`)
≠ 0: set to 22 on completion, 24 on a sacrifice, −1 per month — the effect lapses without
sacrifices. See [religion.md](religion.md).

## Desirability gate `0x00484360` (also inlined at the top of the evolve check)
```
d = (signed char) b+0xCE   # tile desirability at the house
if cheat_flag 0x00F0E60C: return +1
if d <= house_param(L,0): return -1        # devolve
evolve_des = house_param(L,1);  if L > 18: evolve_des = 1000
return 1 if d >= evolve_des else 0
```

## Evolve check `0x00484660(building)` → -1 devolve / 0 stay / +1 evolve
Writes a reason code to `b+0x83` (shown by the house info panel).
```
L = b+0x12 (house level)
gate = desirability gate (above, without the L>18 rule)
food_count = number of food goods held (b+0x54 slots, via map of resource id -> slot) for the
             food resource list at 0x010DFDAC (count 0x010DFDA8)
if gate == -1: reason 0; return -1
# current level's requirements must still hold, else devolve:
water    missing -> reason 1
culture  b+0x80 < col2 -> reason 2 (Poseidon: 0x18)
food     food_count < col8 -> reason 3
edu      b+0x6C < col4 -> reason 4 (Poseidon: 0x19)
wine     b+0x64 < col11 -> 5
fleece   b+0x68 < col9 -> 6
oil      b+0x66 < col10 -> 7
horses   b+0x72 < col7 -> 8 (Poseidon: 0x1C)
arms     b+0x6A < col12 -> 9
any failure -> return -1
if type == 8 (Townhouse) or 14 (Estate): reason 10; return 0     # top level
next = L+2 if type == 9 (elite vacant) else L+1
if gate == 0: reason 0x0C (or 0x0B if 0x00FFA0FC != 0); return 0
same checks against `next` (reasons 0x0D..0x15, Poseidon variants 0x1A, 0x1B, 0x1D); fail -> return 0
reason 0x16 (0x17 for elite vacant); return +1
```
Note: the order of checks matters only for the reason code; the result is the same.

## Open
- Callers `0x00564560`, `0x00570B20`: when the check runs and how the result is applied
  (evolution timing, merging of small houses into 2x2, elite house building).
- Food resource list at `0x010DFDAC`: which goods count as food.
- `0x00FFA0FC` meaning (reason 0x0B vs 0x0C).
