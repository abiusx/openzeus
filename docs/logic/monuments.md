# Monuments: sanctuaries, Poseidon pyramids, palace — construction

Status: **verified** from the exe unless marked. Addresses refer to GOG `Zeus.exe`.
Building fields: [../re/structs.md](../re/structs.md); new overlay names in `re/structs/religion.tsv`
(struct `MonumentPart`). God records, sanctuary operation (priests, sacrifices, god arrival):
[religion.md](religion.md).

## Summary

A sanctuary (types 0x54…0x62), a Poseidon pyramid/monument (types 100…114) or the palace (0x75)
is a *composite* building: one **Building record per piece** of its layout file
(`Model/Sanctuary_*.txt`, `Poseidon_Pyramid_*.txt`, `Palace.txt`), allocated at consecutive
indices. The first record is the **root**; each piece record stores its index in the layout at
`+0x12` (the field houses use as level). Every piece has a *component id* (layout field 3) that
selects a C++ class object (164 classes + 7 "extras" classes ≥ 1000) whose virtual methods give
the piece's number of build **stages**, the **materials** needed per stage and its role in the
build order.

Construction loop:
1. The Artisans' Guild (type 56) spawns **artisans** (figure type 0x3A); each one is assigned
   to the first piece that accepts it, scanning composites by building index and pieces in a
   fixed category order (tiles → temple → statues/sculptures → rest).
2. The artisan walks onto the monument to the piece's **work tile** (the nearest road or sanctuary-ground tile).
   A piece whose current stage needs materials calls **carts** (figure type 4 with an ox team, from a storage
   building) for wood, marble, black marble, sculpture, orichalc: one cart per request, **one monument cart per
   day in the whole city**; each cart drives to the monument's road entry and is unloaded there into its piece;
   small marble needs (tiles: 50) share a cart between sibling pieces. Amounts are in hundredths of a unit
   (100 = 1 slab / 1 statue).
3. Once all materials for the stage are on site, the artisan works a fixed time (51 ticks, or
   the summed "distance" column of the `*_conan.txt` phase for that stage), then the stage
   advances, held materials are cleared, and the artisan takes the next job where it stands; with none left
   it vanishes on the spot (it does not walk home).
4. Every 51 ticks (cycle step 32) each composite's weighted completion percentage is computed;
   at ≥ 100 % the monument is marked complete once, a message is posted, sanctuaries get their
   god-specific completion effects.

## Data: piece classes (verified)

`composite_part_class` `0x0053C1B0`: component id 0…163 → object `*(0x00640E08 + 4·id)`;
id 1000…1006 → `*(0x00641098 + 4·(id−1000))`. The objects are 16-byte statics in BSS
(`0x00FE4638…0x00FE50C8`), each with its own vtable (`0x005D99B0…0x005E42F0`, set by tiny static
constructors, e.g. `0x00535D50` for class 0). `composite_part_object(b)` `0x0053C200` returns the
class object for building `b` with `obj+4 = b`.

Virtual methods used by the simulation (offset in vtable → meaning; same function for all
classes unless noted):

| vt | function | meaning |
|---|---|---|
| +0x04 | `0x0053E210` | current stage = `b+0x58` (i32) |
| +0x08 | per class | number of stages `n` (see below) |
| +0x0C | `0x00535600` | `at_height`: always true for sanctuaries/palace; pyramids: `elev + b+0x6C ≤ grid_8e01fa[tile]` |
| +0x10 | `0x00535760` | `level_reached`: `min(elev, (stage/4)·2) + b+0x6C (+1 for the 0x62 topper) ≤ grid_8e01fa[tile]` |
| +0x18 | `0x005358E0` | base stages `E` = `(elev/2)·4` for pyramid pieces (and the 0x62 piece 0x7A with elev−1), **0 for sanctuaries/palace** |
| +0x1C | `0x0053E250` | conan phase index = `stage − E` (0 if `stage < E`) |
| +0x38 | `0x005435B0` | `set_stage(s, raise)` (below) |
| +0x40 | per class | weight of stage `s` in the completion % (1, 2 or 4) |
| +0x50 | `0x00541ED0` | try to assign an artisan |
| +0x58 | `0x00535240` | artisan work tick |
| +0x5C | `0x0053E530` | default work time = **50** |
| +0x60 | `0x00541670` | complete: `stage ≥ n − 1` |
| +0x64 | per class | conan file: `Model\sanctuary_conan.txt` (classes 0, 110, 158), `Model\statue_conan.txt` (60 statue classes), none (others) |
| +0x78 | per class | marble needed for stage s (double) |
| +0x7C | per class | black marble needed |
| +0x80 | per class | wood needed |
| +0x84 | per class | sculpture needed |
| +0x88 | per class | orichalc needed |
| +0x90 | `0x00556020` (126 classes) | damage: `b+0x69=1`, `b+0x9D=1`, `set_stage(0,0)` |
| +0xA0…+0xC8 | `0x00565940` (true) / `0x00565930` (false) | category predicates, below |
| +0xD8 | `0x005442F0` | request materials (send carts) |
| +0xDC | `0x00544FC0` | unload arrived carts; true when nothing more is needed |
| +0xE8 | `0x0055BF30` (117–122), `0x0055E4F0` (160–163), `0x0053A3D0` (124), else false | "black-marble variant": bit `elev/2` of `b+0xB5` |
| +0xF4 | `0x00544AA0` | god-supplied materials (below) |

Category predicates (class ids for which the method returns true):

| vt | ids | name used here |
|---|---|---|
| +0xA0 | 55–60, 109, 111–116, 152–157, 160–163 | tile (sanctuary tiles, flag poles, fire-pot tiles, auto-colour tiles) |
| +0xA4 | 61–108, 125–132, 145–148 | statue |
| +0xA8 | 7–54, 133–144 | sculpture |
| +0xAC | 2 | altar |
| +0xB0 | 0, 110, 158 | temple front (110 = one-piece small temple) |
| +0xB4 | 1, 159 | temple back (never takes an artisan) |
| +0xB8 | 110 | small temple |
| +0xBC | 117–121, 124 | pyramid step / lift |
| +0xC0 | 123, 1006 | access pad |
| +0xC4 | 124 | lift |
| +0xC8 | 151 | Grand Poseidon statue |

Component names come from the legend at the top of the layout files (hypothesis for ids not in a
legend: 110 small temple, 152–157 unnamed tiles).

## Stages and materials per piece (verified by executing the class methods)

Values were obtained by running each class's vtable methods in an x86 emulator on the exe's own
code (script kept in the agent scratchpad; re-derivable). Amounts are in hundredths: 100 = 1 unit.
Only stages `0 … n−2` consume materials (stage `n−1` = finished). Weight = `vt+0x40(s)` for
`s = 1 … n−1`.

| ids | n | weights | stage 0 | stage 1 | stage 2 |
|---|---|---|---|---|---|
| 0 temple front | 4 | 4,4,4 | marble 800, wood 800 | marble 800, wood 800 | marble 1600 |
| 1, 159 temple back | 4 | 4,4,4 | – | – | – (advanced together with the front) |
| 2 altar | 2 | 2 | marble 400 | | |
| 3–6 palace parts | 1 | – | (built on placement) | | |
| 7–54, 133–144 sculptures | 2 | 1 | sculpture 400 | | |
| 55–60, 109, 111–116, 152–157 tiles | 2 | 1 | marble 50 | | |
| 61–108, 125–132 statues | 3 | 2,2 | marble 800 | wood 400 | |
| 110 small temple | 4 | 4,4,4 | marble 400, wood 400 | marble 400, wood 400 | marble 800 |
| 123, 1000–1006 | 1 | – | – | | |
| 145–148 custom statue | 3 | 2,2 | marble 800, wood 400 | marble 800, wood 400 | |
| 149 observatory | 2 | 1 | marble 1200, wood 800, orichalc 800 | | |
| 150 museum | 2 | 1 | marble 3200, wood 1600, orichalc 2400 | | |
| 151 Grand Poseidon statue | 4 | 1,1,1 | marble 1600, wood 400 | marble 2000, wood 1200 | marble 800, orichalc 800 |
| 158 grand temple front | 4 | 4,4,4 | marble 800, wood 400 | same | same |

Pyramid pieces (ids 117–122, 124, 160–163) have `n = E + base` stages, `E = (elev/2)·4`
(elevation = layout field 4): steps/topper `n = E+2`, lift `n = E+3`, auto-colour tiles `n = E+2`.
All weights 1. Per stage:
- `s < E` (raising the base, one level per 4 stages): **50** marble, or **50** black marble when
  `pyramid_level_majority` `0x00535070(part, level)` is true (more pieces of that level use the
  black-marble variant `+0xE8` than not). `level = min(elev, (s/4)·2)` (`0x005356B0`).
- top stage `s = E`: steps 117–121: marble 200 (or black marble 200 if `+0xE8`), + orichalc 50;
  topper 122: marble 400 (or black marble 400) + orichalc 400; tiles 160–163: marble 50 (or black
  marble 50); lift 124: marble/black marble 50 + orichalc 200, then stage `E+1`: wood 800.

Constants: doubles at `0x005D98A8`=50, `0x005D9090`=200, `0x005D9220`=400, `0x005D9BB0`=800,
`0x005D9BB8`=1600, `0x005D85B0`=100, `0x005D9238`=0.

Totals per layout (sum over pieces, units; pyramids assume all plain marble), computed from the
table above and the shipped layout files:

| layout | pieces | marble | wood | sculpture | orichalc |
|---|---|---|---|---|---|
| Zeus | 197 | 137 | 24 | 88 | – |
| Zeus (Poseidon install, `_Pos`) | 197 | 135 | 24 | 104 | – |
| Poseidon | 134 | 103 | 20 | 48 | – |
| Poseidon grand | 192 | 226.5 | 52 | 8 | 16 |
| Hades | 169 | 132 | 24 | 16 | – |
| Demeter | 132 | 110 | 20 | 40 | – |
| Hera | 98 | 88 | 20 | 24 | – |
| Apollo | 90 | 76 | 16 | 24 | – |
| Atlas | 72 | 76 | 20 | 16 | – |
| Artemis | 48 | 63 | 20 | 24 | – |
| Athena | 50 | 55 | 16 | 32 | – |
| Hephaistos | 41 | 44 | 12 | 24 | – |
| Ares | 29 | 40 | 12 | 8 | – |
| Aphrodite | 27 | 37 | 12 | 24 | – |
| Hermes | 19 | 35 | 12 | 8 | – |
| Dionysus | 11 | 31 | 12 | 8 | – |
| Pyramids 01…15 | 9…99 | 16…327.5 | 0…24 | 0…56 | 4…48.5 |

(Hypothesis on how this compares with in-game numbers: not checked against a running game.)
`.5` totals come from 50-unit tiles; see material pooling below.

## Completion percentage `monument_progress(b, info)` `0x0053ECA0` (verified)

`__thiscall`, ECX = layout manager `0x00FE5100`. Returns an int; `info` may be NULL.
```
root = b - b.part_index
total = done = 0
for each piece p of root (index order):
    cls = class(p); n = cls.n()
    for s in 1 .. n-1:
        total += cls.weight(s)
        if s <= cls.stage(): done += cls.weight(s)
return 100 if total == 0 else (done*100) / total        # idiv, truncation
```
(Ghidra drops the return value: read at `0x0053F567`.) With `info` non-NULL it also fills a
70-int report (materials still needed per resource, held, carts on the way, rounding of
remainders up to whole units `100 − x%100`) used by the info panel; not needed for simulation.

Callers test `> 99` as "complete": `god_sanctuary_ready` `0x004E65F0`, cycle step 32, and
others in religion/sanctuary code.

## Monument completion — cycle step 32 `cycle_buildings_pass_32` `0x00495860` (verified)

Every 51 ticks:
```
for b in 1 .. buildings_last (skipping the other pieces of each composite):
    if b.state != 1 or b.type == 0x75 (palace): continue
    if not composite(b.type) and not 100 <= b.type <= 114: continue
    if monument_progress(b, NULL) > 99:
        if b+0x68 (u8 complete) == 0:
            b+0x68 = 1
            if pyramid: message 0xE0 with text id pyramid_name_text(type) (0x004957B0)
            else:       message 0xE0 with text id sanctuary_god_name_text(god_id(type)) (0x004956E0)
                        sanctuary_spawn_guardians(b) 0x005695A0   # Artemis (0x58) / Ares (0x59) only
                        b+0x32 = 22                                 # 0x004E9750, see religion.md
            b+0xBC (i16) = year; b+0xA3 (u8) = month
            monument_apply_extras(b) 0x0053C9F0
        elif b+0x64 & 0x200:            # a piece was damaged and rebuilt
            b+0x64 &= ~0x200
            monument_apply_extras(b)
        b+0xDA = 0
if anything newly completed: FUN_00402B80()     # build-menu availability refresh (below)
```
Corrections (RE 10-28): `b+0xDA` (under construction) is cleared only inside the `> 99` branch, so a monument
employs nobody until it is complete; labour then gives it its model employees at its next pass (oracle: the Ares
root had 0 employees from the reset to tick ~6650, then 48). `FUN_00402B80` refreshes the build-menu enable table
`0x00787178[menu*0x4B + item]` (menu 0x16 commemorative monuments: `g_commemorative_available[v] != 0`; menus
0x14/0x26 sanctuaries: `g_scenario_gods[0xDC]`, `sanctuary_type_to_god`, `god_can_be_jealous`), not the god record.
Message: `DAT_00FD36EC = 1; FUN_00521A70(0xE0, -1, 0, {id+1, id}, -1)` with `sanctuary_god_name_text`: Zeus 0xCC5,
Poseidon 0xCCB (+0x153 in the Poseidon game), Demeter 0xCD7, Hades 0xCE3 (+0x357), Artemis 0xCE9, Ares 0xCEF,
Aphrodite 0xCFB, Hermes 0xD01, Athena 0xCDD, Hephaistos 0xCF5, Dionysus 0xD07, default 0xCD1, Hera 0xE18,
Atlas 0xE24 (what the id / id+1 pair selects: hypothesis, title and body of a message-file entry).
`monument_apply_extras` `0x0053C9F0`: clears `b+0xB6` on lift pieces; for every piece of the
second list (ids ≥ 1000) and every tile it covers, sets terrain bit `0x10000000` (clearing
`0x881`) and calls class method `+0xE0(tile, flag)`: ids 1001 silver ore, 1002 olive trees,
1003 copper ore, 1004 grape vines, 1005 fruit trees put the corresponding terrain resource on
the tile (names from the layout legends; the per-class code at `0x0053BB90…0x0053C040` was not
read: hypothesis). Demeter (type 0x56) also calls `FUN_0053CFA0(b, 0)`. Then route/terrain
refresh (`0x0051D760`, `0x00587B30`, `0x00502EB0`).

`sanctuary_spawn_guardians` `0x00569360`: Artemis (god 4) creates figures of type 0x0B with
formation ids 0x1F/0x20; Ares (god 5) type 0x0C with 0x21/0x22, at the sanctuary's road entry
(military subsystem; hypothesis: Amazons / Ares's warriors).

## Artisans

### Spawning: Artisans' Guild, `buildings_spawn_walkers` case 0x38 → `artisans_guild_spawn` `0x0048CB30` (verified)
Runs in cycle step 31, only when `0x00EF6163 == 0` (set while a god figure is in actions
0x40/0x41, religion.md).
```
if disabled_type_timer[type] (0x00EF60B0[type]) != 0: return       # god curse, religion.md
if b+0x18 (i16) < 1: b+0xD3 = 2
if not road_access(b) or b+0xDA != 0: return
if employees(b+0x40)*100 / model[type].employees (col 5) <= 0: return
max = artisans_guild_max(b) 0x0048CAF0 = 0 if timer else 1 + (god record 13 (Atlas, 0xEF607C) sanctuary finished)
if b+0xA8 (u8, artisans out) < max:
    b+0x32 = 0
    f = figure_create(type 0x3A, at road entry 0xF13944/0xF13940)
    f.action = 6; f.building = b; f+0x36 = 0; b+0xA8 += 1
    if artisan_find_job(f) == 0: f+0x65 = 1; f.action = 4      # hidden, dying (not "go home", see below)
    else: f.action = 7; ...; b+0x3C -= 100 (min 0)
```
`b+0xA8` of the guild is recounted each cycle from the live artisans (`buildings_spawn_walkers`
`0x0048CFB0`, around line 89524 of zeus.c).

### Job search `monuments_find_artisan_job` `0x0053EC10` → `monument_pick_part` `0x0053E740` (verified)
Scan buildings 1…3999; for each composite root (palace 0x75 skipped) call
`monument_pick_part(root, f)`; return the first non-zero piece. In `monument_pick_part`:
```
if root+0x64 & 0x100: return 0                       # meaning unknown (see Open)
if pyramid (type 100..114) or (type 0x62 and no tiles/temples/statues left):
    candidates = pieces with (!at_height) or (step/lift and !complete)
    first try them in index order, then sorted by layout build order (+0x14 of the layout
    piece, qsort 0x005CC22F with comparator 0x0053E720), calling cls.assign(f, 1, order)
    if some candidate exists but none accepted: return 0
phase 1: tiles (+0xA0) not complete         -> try each; if any exists and none accepted: return 0
phase 2: temple front/back (+0xB0/+0xB4)    -> same
phase 3: statues/sculptures (+0xA4/+0xA8)   -> same
phase 4 (0x62 only): non-Grand-statue pieces not complete
phase 5: any incomplete piece in index order
```
`assign` (`+0x50`, `0x00541ED0`) accepts when: the piece is not complete, the figure is an artisan,
the piece is not a temple back; for lifts at phase 1 no other step of the same elevation is
incomplete; `pyramid_piece_ready` `0x00541690` is true; and the piece has no live working
artisan (`b+0x5C`, checked by `0x00541610`). On acceptance: `f.action = 7` (walk), destination =
the piece's work tile (`+0x54`), `f+0x5E = piece`, `f+0x44 = f+0x36 = 0`, `piece+0x5C = f`.

### Artisan handler `0x004C0060` (verified from the disassembly, 10-28)
Every tick first: `f+0x01` anim = (anim+1) % 12; speed = `figure_type_value(f, 8)`; route mode `f+0x72 = 1`;
`f+0x42` visit length = 0xC00; if the home guild is not active, not type 0x38 or has no workers: removed (state 2).
Then by action (jump table `0x004C0B98`):
- **4 dying**: `figure_dying_tick` `0x004D60B0` counts `+0x36` to 127, then state 2 and `home+0xA8 -= 1`. A guild
  whose new artisan found no job therefore sends nobody for ~128 ticks.
- **5** fight (`0x004D5F10`).
- **6 idle**: hidden (`+0x65`) for 10 ticks, else roams (`figure_roam_tick` `0x004D6790`) and every
  `rng % 30 + 30` ticks, at a tile centre, tries `artisan_find_job` (→ action 7); after the visit length (~512 ticks)
  it walks home (action 11) or dies (4). Reached only after action 11 / a lost route.
- **7 walk to the piece**: route mode 13 when the destination piece is a composite/pyramid; every 31 ticks
  (`+0x36 > 30`) it calls the piece's `request_materials` (vt+0xD8) unless god-supplied (`root+0xDB`).
  `figure_move`: arrived → action 8; lost → retry via the monument's road entry (`building_road_entry`
  `0x0053FB60`), else action 6.
  Route mode 13: BFS `0x0058A0D0` over route bits 0x12C (road 0x04, ramp road 0x100, monument ground 0x20, 0x08),
  else `0x00589ED0` over 0x13C (open land too). Bit 0x20: tiles with terrain 0x10000000 (sanctuary ground, the
  1000-class extras, set at placement by `FUN_0053C390`) or holding a piece whose vt+0x9C `0x0053E5D0` is true
  (phase index 0: a piece not started; tile classes `0x00565940` always; palace parts never).
- **8 work**: if the piece is not ready (vt+0xDC unload false) the artisan stands, turning ±1 direction at random
  (rng & 3 == 0, each time `+0x36` is 0); `monument_part_work(piece, f, 9)` (below); on action 9 (stage done)
  `artisan_find_job` at once → action 7 to the next piece, **on site**.
- **9 done**: `figure_move` to its own tile → state 2, `home+0xA8 -= 1`: **the artisan vanishes at the monument**.
- **11** walk home after roaming: arrived → action 6 hidden in the guild.
Sprite (`+0x04`, SprMain): action 4 the die group (23, 8 frames, `+0x36/2`); action 8 with materials: **group 24
"build"**, `first + (anim/2)*8 + dir`, frames 0..5, 2 ticks each, sound 0x3E when anim == 8; action 8 waiting:
the walk group's frame 3 (`first + 0x18 + dir`), standing; otherwise walk (group 22, 12 frames). Group 25
("build_standing") is not used by this handler. During a statue's conan phase `monument_part_work` hides the
figure (`+0x65 = 1`; the piece's `+0x48` conan rows presumably draw it: hypothesis).
Direction drawn = `+0x11` (or `+0x12` when `+0x11 >= 8`) minus the view rotation.

### Work tile vt+0x54 `0x00541E50` (verified, same for all classes)
Hermes (type 0x5B): the piece's `+0x26/+0x28` (its road entry). Otherwise from the piece's min tile,
`find_work_tile` `0x00541960`: the tile itself if acceptable, else rings r = 1..227 (top row, bottom row, left
column, right column, clamped to the map), keeping the strictly smallest `dx² + dy²` (start 0xCB10), taken as
soon as `best <= r²`. Acceptable: road (terrain 0x40) or sanctuary ground (0x10000000). (The code also tests
`vt+0x9C` of the building-grid value at the tile, passing a building id to a type check: in practice never true.)
`assign` copies it to the figure's destination `f+0x24/+0x26`, `f+0x28 = piece.tile`, `f+0x5E = piece`.

### Work tick: artisan action 8 → `monument_part_work(piece, f, 9)` `0x00535240` (verified)
Called from the artisan handler `0x004C0060` (table `0x0063969C`, type 58; not a Ghidra
function) every tick while the artisan is in action 8; after the call, action 9 means "stage
done" and the handler calls `artisan_find_job` again.
```
cls = class(piece)
if cls.stage() >= cls.n() - 1: f.action = next(9); return
anim = None
if cls.at_height():                          # always for sanctuary pieces
    anim = conan_phase(cls, cls.phase_index())  # 0x00534500: obj+8 table, NULL if no rows
    if anim: f+0x65 = 1; piece+0x60 += 1; if piece+0x60 >= conan_duration(anim): piece+0x60 = 0
root = piece - piece.part_index
if root+0x64 & 0x100 and piece has no cart slot in use and !cls.unload() and piece+0xA4 == 0 and piece+0xB0 == 0:
    f.action = next; return
if !cls.god_supply() and !cls.unload():      # materials missing
    f+0x36 += 1
    if f+0x36 > 30: cls.request_materials(); f+0x36 = 0
    return
piece+0xA8 += 1
if anim == None:
    if piece+0xA8 <= 50: return              # vt+0x5C
    f.action = next
else:
    if piece+0xA8 < conan_duration(anim): return
    f.action = next; f+0x65 = 0
piece+0x60 = 0; piece+0xA8 = 0
if cls.stage() < cls.n() - 1:
    cls.set_stage(cls.stage() + 1, 0); refresh_piece_image(piece) 0x0053D300
if cls.is_temple_front():                    # advance the matching temple back(s) to the same stage
    for q in pieces of root: if 0x00546590(q) and 0x005351D0(piece, q): class(q).set_stage(stage, 0); refresh(q)
if (cls.is_step() and cls.complete()) or not cls.at_height():
    pyramid_raise_level(root) 0x00534750
```
So a sanctuary piece needs 51 work ticks per stage with an artisan present (counter goes 1…51),
unless its class has a conan phase with rows.

`conan_duration` `0x00430A10` = sum of column 6 ("distance") over the rows of the phase.
`monument_class_load_conan` `0x00534540` allocates `n` phases per class and parses the file
named by `vt+0x64`. Shipped files: `sanctuary_conan.txt` 4 empty phases → temples use the
default 51 ticks; `statue_conan.txt` phase 1 has 2 rows of distance 50 → a statue's stage 1
takes **100** ticks; phases 0 and 2 are empty → default. The other columns (start/finish tile,
look, rotation flags) probably drive the artisan's movement on the piece (hypothesis).

### `set_stage(s, raise)` `0x005435B0` (verified)
```
if 0 <= s <= n:
    if b+0x58 < s and b+0x69: b+0x69 = 0          # vt+0x98 / +0x94: "damaged" flag cleared on progress
    b+0x58 = s
    if raise: (pyramids) write elevation layout[+0x10] + b+0x6C into grid_8e01fa over the piece's tiles and into b+0x6C/+0x6D
    b+0x70 = b+0x74 = b+0xAC = b+0x78 = b+0xC0 = 0   # materials held for the stage
    b+0xA4 = b+0xB0 = 0; (u16) b+0xC4 = 0
    if lift and complete and b+0xB6 == 0: b+0xB6 = 1
```

## Materials

Resource ids (text group 23): 9 wood, 11 marble, 16 black marble, 17 orichalc, 19 sculpture.
Mapping (verified in `0x005442F0`, `0x00544FC0`, `0x0053ECA0`):

| resource | need method | held field |
|---|---|---|
| wood (9) | vt+0x80 | `+0x70` |
| marble (11) | vt+0x78 | `+0x74` |
| sculpture (19) | vt+0x84 | `+0x78` |
| black marble (16) | vt+0x7C | `+0xAC` |
| orichalc (17) | vt+0x88 | `+0xC0` |

`remaining(r) = ceil(need_r(stage)) − held_r` (ceil = CRT `0x005CCF57`, verified on −1.5 → −1).

### Request `monument_part_request_materials` (vt+0xD8) `0x005442F0` (verified, outline)
Called by the working artisan every 31 ticks of waiting.
1. If complete → return.
2. For each of the 8 cart slots `+0x7C…+0x98` (figure ids): drop the slot unless the figure is a
   cart pusher (type 4) carrying one of the five resources whose remaining is > 0 (subtracting
   its load `f+0x74` from that remaining).
3. If nothing remains → done. Otherwise, try `vt+0xE4(piece, r)` for marble/black
   marble/orichalc (sharing a load already heading to a sibling piece; `0x005456F0`, not read).
4. Dispatch at most one new cart, into the first free slot, in this order: **wood** (amount
   `clamp(trunc(remaining), 100, 400)`), **marble**, **black marble** (amount 400 if
   `remaining + loads already reserved by siblings at the same stage (0x00542900 mode 2) > 399`,
   else 100; extra 100-unit shares are then reserved on sibling pieces with `0x00542900` mode 1),
   **sculpture** (`min(trunc(remaining), 400)`), **orichalc** (like marble).
`monument_dispatch_cart(piece, res, amount)` `0x00543DE0` (verified 10-28):
```
if day_of_month (0x0091EC0C, 0..15) == (u8)city[0] (0x00FE6A58) or root+0x64 & 0x100: return 0
src = storage_find_source(piece, res, 0, 1, min(amount, 400))
if !src or !building_road_entry(piece, &ex, &ey): shortage(piece, res, 1); return 0
cart = figure_create(4 at src's road access); ox = figure_create(0x1C, action 6, leader cart)
sled = figure_create(0x1C, action 7, resource res, leader ox)            # FIG_OXCART team
short = storehouse_remove_goods(src, res, amount); if short == amount: cart removed, return 0
cart: load = amount - short, action 0x13, home src, destination (ex, ey), +0x5E = piece, route mode 7
city[0] = day_of_month                                                    # one monument cart per day, city-wide
```
Road entry `composite_road_entry` `0x0053F810`: an access pad (class 123/1006: pyramids) if any; else a road tile
(0x40, not terrain bit 4) on the ring just outside the layout box (rows y = miny−1, maxy+1, then columns x = minx−1,
maxx+1; avenues redirect to their anchor), best road-network rank among the 10 largest networks, then the smallest
squared distance to the root. Cart pusher (`0x004AE160`, roads only): 0x13 walking (removed when vt+0xD0
`cart_valid` is false; lost → shortage, removed), 0x14 at the entry → sanctuaries go hidden to **0x17**, where every
tick the piece's unload (vt+0xDC) takes the load; pyramids may go 0x15/0x16 via a lift to the piece.
`cart_valid` vt+0xD0 `0x005438A0`: false when the piece is complete; walks the 8 slots with the remaining needs
(clearing slots whose resource is no longer needed, except marble/orichalc/black marble needs < 100) and puts an
unslotted cart into a free slot while its resource is still needed. (Black marble counts as marble there: quirk.)
Shortage flags `0x00543C30(piece, res, set)`: bits of `root+0x64`: wood 0x01, marble 0x02, sculpture 0x04, black
marble 0x08, orichalc 0x10; set by a failed dispatch or a lost cart, cleared while a cart walks normally (their use
by the info texts 59:9..14: hypothesis).

### Sibling sharing (verified 10-28; the stale-reservation path partly hypothesis)
Before dispatching, `vt+0xE4` `covered_by_sibling` `0x005456F0` is tried for marble/black marble/orichalc: only
for needs ≤ 50 (`trunc(100/need) > 1`); true when the piece's reservation `s` (`+0xA4` marble, `+0xB0` black
marble, i16 `+0xC4` orichalc) has the same type, stage and need and a valid cart of that resource → no dispatch.
Marble/black marble/orichalc amount: `s = share_load(mode 2)`; `400 if s + trunc(rem) >= 400 else 100`; after a
dispatch `share_load(mode 1)` runs `trunc(load/need) − 1` times. Wood `clamp(trunc(rem), 100, 400)`, sculpture
`min(trunc(rem), 400)`.
`monument_share_load(piece, r, &out, mode)` `0x00542900` over the siblings q of the same root at the same stage
(mode 2 skips q reserved by another piece), eligible (`0x00542670`) when `need_r(q) == need_r(piece)`,
`q.held_r == 0`, no cart in q's slots, and in mode 1 q's reservation free or stale: mode 2 sums `trunc(need)` (≤ 400);
mode 1 reserves the nearest eligible (`chosen.reservation_r = piece`); mode 0 gives it `held_r = ceil(need)`.
(Pyramids sort candidates by layout build order with `pyramid_piece_ready`.)

### Unload `monument_part_unload_carts` (vt+0xDC) `0x00544FC0` (verified, outline)
For each cart slot whose cart is in action 0x17 (arrived): wood and sculpture: `held += load`; marble (and,
by the same pattern, black marble / orichalc: hypothesis on the details) with need < 400: `k = trunc(load/need)`;
if nothing is held, `held = ceil(need)`, else `k += 1`; then `share_load(mode 0)` k − 1 times (each nearest
eligible sibling gets its need); else `held += load`. Then `f+0x74 = 0`, `f.state = 2` (the cart is removed at
the road entry; it never drives home). Returns true when every remaining ≤ 0 and no slot is
in use → the artisan may work.

### God-supplied materials (vt+0xF4) `0x00544AA0` (verified)
If `root+0xDB != 0` (set to 100 with `root+0xA2 = 8` by `0x004C5D00`, called from a god figure —
religion.md; which god: hypothesis Hephaestus/Athena), and no cart slot other than the first is
in use, the stage's materials are granted instantly: wood +100, marble +400 (or the exact need if
< 400, sharing the rest), black marble likewise, sculpture +400, orichalc likewise; then
`root+0xA2 -= 1`, and when it reaches 0 `root+0xDB = 0`.

## Pyramid level mechanics (Poseidon)
- `grid_8e01fa` (sav rank 111, i8 per tile) holds the built height of monument tiles.
  `pyramid_raise_level` `0x00534750`: when every piece of the root is either at height and (not a
  step, or a complete step), or has its stage a multiple of 4 (a level just finished), adds 2 to
  `grid_8e01fa` (and to `b+0x6D`) on all tiles of pieces not yet at height, calls
  `refresh_piece_image`, then redraws the area (`map_tiles_update_images`). (verified; that this
  is "raise all pieces one level" is the reading of the code.)
- `pyramid_lift_update` `0x00534D60`, every tick from `multi_tile_buildings_update` `0x00534F60`
  (tick step 6) for pieces of types 100…114: lift pieces (vt+0xC4, complete) run a state machine
  on `b+0xB6`: 2 = going up (`b+0xBE` frame +1 mod 12, `b+0xB7` +1; at 59 → state 3, wait
  `b+0xBF = 2`, remember the payload `b+0xB8` for level `min(elev/2+1, 5)`), 3 = wait, 4 = going
  down (frame −1 mod 12, counter −1; 0 → state 1), 0/1 = idle (clears `b+0xB8…`). Then every
  idle lift whose level has a pending payload starts (state 2, counter 0). Requests come from
  `pyramid_lift_request` `0x00534B50` (artisans needing to reach a level, hypothesis).
- `pyramid_figure_height` `0x00534A70`: draw offset −15·(((stage−1) & 3)+1) for a figure on a
  rising piece (rendering).

## Palace
Type 0x75 is composite (`building_type_composite` `0x005344A0`: 0x54…0x62 and 0x75) but its
pieces (classes 3–6) have 1 stage, so it is complete on placement; artisan search and step 32
skip it. `Palace.txt`: 24 pieces.

## Monument types in Zeus (scope, verified from the exe unless marked)
| kind | types | built how | unlocked how | effect |
|---|---|---|---|---|
| Sanctuaries (14 gods + grand Poseidon) | 0x54..0x62 | piece by piece by artisans (this doc) | scenario's gods (sandbox: all) | staff + god (religion.md); desirability row (+20) |
| Commemorative monuments | 0x77 (119), variant 1..65 | placed at once, cost 0, no artisans | granted by events (below) | desirability only (+30, step 2, -5, range 6) |
| Poseidon pyramids / great monuments | 100..114 | piece by piece by artisans, as sanctuaries | scenario slots only (Poseidon) | desirability only |
| Palace | 0x75 | composite, complete on placement | — | — |
No other building is treated as a monument: gardens, statues and columns are ordinary decor. Text group 68 has "Monument
rating" (68:146) and "Overseer of Monuments" (68:83); no simulation reads were found (hypothesis: unused strings).

## Commemorative monuments (type 119 = 0x77)
Not composite and not artisan-built. The variant is `+0x12` = `DAT_00665DB0` at placement (`building_create`
`0x00493E70`), 1..65 (the "0x16" of an earlier note is the submenu id 22, not a variant). Oracle: the working city's
three monuments have `+0x12` = 1, 6, 1 (`g_commemorative_placed[1] = 2`, `[6] = 1`). Names text `198:v`, descriptions `90:v`.

Every caller of the grant `FUN_00402B00(v)` (9 functions, verified 10-29; the exe posts no message of its own for a
grant: the event's message says "you can now build a Commemorative Monument"). Messages are `FUN_00521A70(type, …,
record)` with a record of phrase ids (+0 announcement, +2 title, +0x10 reason); the ids resolve through the name table
`0x005FBC38` to texts in `Model/Zeus eventmsg.txt` (not Zeus_MM.eng). Ours: `data/messages.json`
(tools/build_messages.py), posted by `sim/messages.py` as one line "Title. Announcement":

| v | name (198:v) | granted by | sandbox | ours |
|---|---|---|---|---|
| 1 | Population Monument | `city_population_update` `0x00486190` (daily): population ≥ 1000, 2000, 5000, 10000, 15000, 20000, 25000, once each (flags `0x00FD37C6..CD`); 100, 500 and 3000 only post their message (flags `..C4`, `..C5`, `..C8`); messages 0xE0 with phrases 0x4DA/0x4DB .. 0x510/0x511 ("Population milestone: N people") | yes | `commemorative.day` |
| 2 | Victory Monument | `army_withdraws` `0x00481E80(city, bribed, 0)` from `cities_relations_update` `0x00568C20` (every invader gone, military.md "End of an invasion") and from the bribe `0x00475910` (bribed = 1); message 0xDE 0x442/0x445 ("Invasion force defeated!") or 0xE0 0xD75/0xD78 ("Invaders paid off!"). `FUN_0046ED30` (a city status change) calls it with the third argument 1: no grant | yes (invasions) | sim/military/invaders.py `withdraw` |
| 3 | Colony Monument | `FUN_0041FE40` (from `screen_input` / `FUN_005148F0`): once after the next adventure episode is loaded with the old city turned into a colony (`DAT_00902C04` set by the episode swap at `0x0052D2B0`..); 0x51A/0x51B | no (campaign) | later |
| 4 / 9 | Athlete / Scholar Monument | `FUN_00565FC0` at the end of the Panhellenic games (event 37, `0x0046E5A0`) when the city's contestants won: 4 in Olympian and Nemean years, 9 in Isthmian and Pythian ones ([games.md](games.md)) | **yes**: the open-play sandbox schedules games from its first year (`0x00902C50` = 0 in the sandbox dumps; −1 in the working city) | sim/systems/games.py |
| 5 | Conquest Monument | `FUN_00480240` (the player's conquest expedition won, from `FUN_0046ED70`): `city_class` 0 (ally) or 2 (rival) conquered, message 0x3BC/0x3BD; a rebelling vassal (0x358) or colony (0x3E0) brought back: no monument | yes (world map) | sim/empire/war.py `conquer` |
| 6 | Happiness Monument | `city_sentiment_update` `0x005671A0`: at day_of_month 0, `g_high_sentiment_months` (`0x00FE9414`) += 1 if sentiment ≥ 81 else 0; at ≥ 60 grant and reset (message 0xE0, 0x516/0x517) | yes | `commemorative.month` |
| 7 | Heroic Figure Monument | `monster_event_update` `0x00481430` (a hero killed the scenario's monster, event flag 0x100) | no (scenario monsters) | later (heroes) |
| 8 | Diplomacy Monument | `event_city_status_change` `0x00473680` (scenario event type 0x13) subtype 9 applied to a rival (relationship 1 → 0, ally); message 0xE0 0x39E/0x39F ("[city_name] becomes ally") | only through scenario events (none in the sandbox) | sim/empire/relations.py `status_change` (also `citystatus CITY 9`) |
| 10..65 | Small / Large *god* Statue | `FUN_00482820` (god quest event, month_events_dispatch): when the hero quest ends (state 7 → done) the reward `FUN_004825C0(god, quest 0/1, size 1/2)`: 10..21, 34, 35 (small) and 22..33, 36, 37 (large) for a god's first quest, 38..63 likewise for the second | no (scenario god quests) | later (gods/heroes wave); `grant_monument V` places them for testing |

Counters: grant `FUN_00402B00(v)`: `g_commemorative_available[v]` (`0x00665CC8`, u8[75]) += 1 only while it is ≤ 9
(10 waiting at most), then the menus are refreshed (`0x00402B80`, `0x00403DF0`). Placement (`FUN_00496CA0` case 0x77):
`g_commemorative_placed[v]` (`0x00665C7C`) += 1, `FUN_00402B40(v)` available −= 1; at 0 the build tool is cleared.
Removal (`building_on_remove` `0x00494690`): placed −= 1; the grant is not given back. Recount `FUN_0050E9F0`.
(`0x004029D0` is not the grant: it counts the enabled entries of a submenu.)

Size and picture (`building_create`, `FUN_00496CA0`): variants 1..9 are 3×3, one image Zeus_General
`SPR_B_COMMEM_MONU` + (v − 1) (images 225..233, 178×148). Small god statues are 3×3, large ones 4×4 (`size += 1`),
both with the orientation `+0xAC` = the R key's `DAT_00DA23C4`: sanctuary tiles round a 1×1 / 2×2 statue; pictures,
facing per view and the oracle check: [../play/monuments.md](../play/monuments.md) 9.

Cost: model column 0 = 0. Effect: **desirability only**, model row 119 `{0, 30, 2, −5, 6}`, spread with the plain
rule (size 3, or 4 for large statues); no sentiment, appeal or god code reads type 0x77 or the counters (their only
readers are UI: `FUN_0051BEE0`/`FUN_0051C330` the Aesthetics page, `FUN_00596180` an advisor list, `build_menu_draw`
`0x0058F650`). No employees (0x77 is in the zero-labour list of `labor_assign_buildings`).

Build menu: Aesthetics page (9), slot 2, submenu 22 "Monuments" (tool text 28:157, buttons Zeus_Interface 1597..1599),
order `0x005F41A0` = `0x005F27D8[22·75..]`: 1..21, 34, 35, 22..33, 36..49, 62, 63, 50..61, 64, 65; an entry is listed
only while `g_commemorative_available[v] != 0`; picking it sets `g_build_tool = 0x77`, `DAT_00665DB0 = v`. Preview
`build_cursor_preview` `0x00451C70` (variants 1..9: image base + v − 1; statues `FUN_00456E30`).

Placement (exe): granted monuments wait in the Monuments submenu; the player picks one and places it like any
building (generic `map_area_buildable` on 3×3 or 4×4, cost 0), complete at once; placing the last waiting one of a
variant clears the tool. Info window `0x00577C50`: title 90:0 "Commemorative Monument", text 90:v (one per variant).
Messages: see the table (the event's own message; the population ones that grant and 0x517 name the monument).

Ours (sim/systems/commemorative.py): the grants above (population daily with the message-only milestones 100, 500,
3000; happiness monthly; victory, conquest, diplomacy and games from their modules through `grant(g, v, why)`);
`grant_monument V` (ours, for testing); `build commemorative_monument X Y [V|auto] [O]` (O = the R key 0..3), refused
when none of that variant is waiting; `menu(g)` = the submenu's list in the exe's order (state.json
`monuments_available`). Play: Aesthetics > Monuments lists the waiting variants (ui.js submenu 22), R turns the
ghost, the tool clears with the last one; every variant drawn as the exe (play/monuments.md 9); info text 90:v.
Old saves: monuments placed when they were freely buildable become variant 1; a city past a population milestone is
granted it on the next day (the message-only ones are marked done without a message). One message per grant, as the
exe: `grant(g, v)` posts nothing; population, happiness, victory/bribe, conquest, diplomacy and games post the exe's
title + announcement (ids in the table; `[player_name]` = "Ruler" until the sandbox has a player name,
`[nationality]` = text 37:nationality (hypothesis: `wm_sub_465CA0` stores that slot), `[city_name]`/`[leader_name]`
from the empire city). The colony (0x51A/0x51B) text is in data/messages.json for later.
Later: colony (campaign), hero/monster and god-quest statues (scenario events), and the Aesthetics page's list of
placed monuments (`FUN_0051BEE0`, bugs.md 194).

## Poseidon great monuments (types 100..114)
| type | name (28:t) | model {cost, des, step, step size, range} | layout |
|---|---|---|---|
| 100 | Modest Pyramid | 0, 15, 1, −2, 4 | Poseidon_Pyramid_01 |
| 101 | Pyramid | 0, 20, 1, −2, 4 | _02 |
| 102 | Great Pyramid | 0, 25, 1, −2, 5 | _03 |
| 103 | Majestic Pyramid | 0, 30, 1, −2, 6 | _04 |
| 104 | Small Monument to the Sky | 0, 16, 1, −2, 4 | _05 |
| 105 | Monument to the Sky | 0, 20, 1, −2, 5 | _06 |
| 106 | Grand Monument to the Sky | 0, 25, 1, −2, 6 | _07 |
| 107 | Minor Shrine | 0, 20, 2, −2, 4 | _08 |
| 108 | Shrine | 0, 25, 2, −2, 5 | _09 |
| 109 | Major Shrine | 0, 30, 2, −2, 6 | _10 |
| 110 | Pyramid of the Pantheon | 0, 30, 1, −2, 6 | _11 |
| 111 | Altar of Olympus | 0, 25, 1, −2, 5 | _12 |
| 112 | Temple of Olympus | 0, 30, 1, −3, 6 | _13 |
| 113 | Observatory Kosmika | 0, 25, 1, −1, 6 | _14 |
| 114 | Museum Atlantika | 0, 25, 1, −1, 6 | _15 |
All: type-info `{size 3, fireproof, image 4097, labour category 6}`, info panels 153..160. Cost 0 (`build_commit` reads
`model_building_value(type, 0)`): paid in materials only. **Unlock: scenario only**: Aesthetics slot 3, submenu 21
(0x15), items 1000..1005 = scenario monument slots 0..5 (table `0x005F4070`), each a 12-byte record at
`g_scenario_gods (0x00FFA450) + 0xE4 + 12·slot`: `+0` building type (becomes the build tool), `+8` bit 0x40 = may be
placed (set again by `cycle_buildings_pass_40` → `FUN_005875A0` when a pyramid is removed), `+4` unknown (hypothesis: the
god of its statues); also requires `poseidon_game()`. Effect: desirability only, while `+0xDA == 0`; completion message
0xE0 with `pyramid_name_text`. Ours: buildable when `poseidon on` (no scenario slots yet).

## Oracle: a sanctuary being built (10-28)
Run: re/oracle/scenarios/sanctuary-build.txt ("See a working city", its Ares sanctuary, buildings 395..423, reset
to stage 0 through the runner's ZEUS_POKE, 6400 marble added to storehouse bays; docs/re/oracle.md "Pokes").
Timeline: `python3 tools/oracle_monument.py re/oracle/runs/sanctuary-build 395 423`. Observed:
- 4 guilds send 4 artisans at once; they walk the roads (action 7) and then the sanctuary ground; each works from a
  tile beside its piece (e.g. piece (52,54) from (52,56), (53,54) from (54,54)): the work-tile rule above.
- Order: tiles first (ticks 600..2200), then the temple (alone: the other artisans find no job and vanish at the
  monument, ~tick 2200), then the statue, sculptures and altar; complete at tick ~6650.
- Carts: one at a time from the nearest storehouse (83,56) to the road entry (57,54) (~500 ticks a trip); the first
  marble cart (400) for tile piece 4 left 50 in piece 4 and 50 in each of 7 other tiles (1, 2, 3, 5, 6, 8, 9) on
  arrival: the mode-0 sharing. Wood and marble carts for the temple (400 each) on different days.
- On completion: `+0x68 = 1`, `+0xBC` = year, `+0x32 = 22` then −1 a month, employees 0 → 48 at once.
- Screenshots (shot_420/460/500.bmp): artisans with hammers standing on the raised terrace tiles, one walking up.

## Ours (sim/systems/monuments.py, 10-28)
As above: per-piece stage, held materials, cart slots and reservations; the guild's one artisan with the 128-tick
pause when it finds no job; route mode 13 (roads + monument ground + unstarted pieces + tile pieces, else open land);
the work tile rule (Hermes: the road entry); requests every 31 ticks (walking and waiting); one dispatch per call and
one monument cart a day city-wide; amounts and the three sharing modes; carts unloaded and removed at the road entry
(the piece's waiting artisan acts the next tick); 51 / 100 work ticks; set_stage clears held materials and
reservations; temple backs follow the front; the artisan takes the next job where it stands or vanishes; completion
once (> 99): message, date, `activity` 22 for sanctuaries, staff from then on (palace: complete, no message).
Extras on completion (10-29, monument_apply_extras 0x0053C9F0; class objects 0x00641098[c - 1000], method +0xE0):
every extras tile loses tree/scrub/meadow (& ~0x881) and has 0x10000000; 1001 silver ore (| 0x200002), 1003 copper
ore (| 0x100002), 1002 / 1004 / 1005 an olive tree / grapevine / orange tree building on the tile (building_create
types 0x24 / 0x23 / 0xD9, +0xD8 = the sanctuary): Athena 16 olive trees, Dionysus 8 vines, Hades 8 silver, Hephaistos
4 copper, Hera 18 orange trees; Demeter (0x56, FUN_0053CFA0) a meadow ring 2 tiles wide round the layout box on tiles
with terrain & 0x1FFF0F17 == 0 (recorded; removal takes back only those). Removal (FUN_00546A60 from
building_on_remove): 0x10000000 and the ore bits cleared, the trees removed. Ours: monuments.extras_complete /
extras_removed (game.demolish); saves with a sanctuary completed before get them on load (adopt). Oracle (10-30,
re/oracle/scenarios/e1-sanct.txt, tools/oracle_sanct_complete.sh + tools/e1_sanct_check.py; pieces completed by pokes on
Open Play Sandbox): every piece record where ours puts it, and the extras equal tile for tile: Athena 16 olive trees in
orientations 0, 1, 2 and 3, Demeter's meadow ring 136 tiles in 0 and 1, Hades 8 silver tiles in 0 and 1; the new
trees' growth (+0x54) 0 as ours; the trees' pixels (orientation 0, done.bmp) 95.6 % within 8 of play mode's. The exe
places the box with the layout origin under the cursor in every orientation (raw (67,68) for the same hover) = ours'
`origin`. Hephaistos (copper), Dionysus (vines), Hera (orange trees) are not on the sandbox's god list: not run.
The exe sets 0x10000000 on the whole layout box at placement (FUN_0053C390: every tile of every layout record, 192 for
Athena; it feeds draw order's "nb" class, the walkers' ramp mask 0x10000400 and terrain_regrow's skip), cleared at
removal; ours since 10-30 the same for sanctuaries (monuments.mark_ground from game build; adopt marks older saves;
extras_removed clears it, complete or not; the palace and pyramids are not marked: not checked whether they go through
FUN_0053C390). The raised pieces' elevation that FUN_0053C390 also writes there is not ported. The road entry (composite_road_entry 0x0053F810, 10-29): the
ring tiles with terrain & 0x44 == 0x40 ranked by their road network's place among the 10 largest (0x00491FE0), then
by distance to the layout file's (0, 0) (`origin` in data/monuments.json, tools/monuments.py); first found wins a tie;
roadblocks count. Orientations 1..3 of the origin: our reading.
Not done / ours: pyramid order (`pyramid_piece_ready`,
lifts, lockstep levels, black-marble variants); god-supplied materials, Artemis/Ares guardians and the god (gods
wave); the idle roaming (action 6/11) of an artisan
that lost its route; the artisan's facing while working (ours: toward the piece; exe: its last walking direction);
the statue conan phase draws the artisan building (exe: hidden, drawn by the piece's conan rows: not mapped).
Old saves: pooled materials go to the unfinished pieces' current stages in layout order (the rest is dropped);
artisans and carts out find their piece again.

## State touched
Building records of all pieces (`MonumentPart` overlay), figures (artisans type 0x3A, carts
type 4, helpers 0x1C), storages (reservations), `grid_8e01fa`, terrain flags `0x00CCE128`
(extras), messages, god record via `0x00402B80`.

## When it runs
- tick step 6: `multi_tile_buildings_update` (lifts).
- tick walkers: artisan handler (work, job search), carts.
- cycle step 31: guild spawns artisans.
- cycle step 32: completion check.

## Open questions
- `root+0x64 & 0x100`: who sets it (no direct writer found by text search). It stops artisan
  assignment and cart requests (a "construction halted" toggle? hypothesis).
- `pyramid_piece_ready` `0x00541690` and `pyramid_lift_request` `0x00534B50`: rules for which
  pyramid piece may be worked at which height.
- The stale-reservation path of `0x00542670`; the black marble / orichalc branches of unload.
- How the sanctuary status texts 59:9…14 pick a line (the shortage bits of `root+0x64`: hypothesis).
- Placement cost and creation of the piece records (map-buildings subsystem).

## Cross-references
- play/monuments.md: how each piece is drawn per stage (class method `vt+0x4C`), sanctuary terrace heights, pyramid step images.
- religion.md: `b+0x32` on a sanctuary root is a monthly counter (22 on completion, 24 after a
  sacrifice), not a plain flag; `god_sanctuary_finished` `0x004E9440` tests it non-zero; god
  record +0x08 = sanctuary root (`0x004E8C40`); `0x00EF60B0[type]` disable timers; Atlas doubles
  artisans; `0x004C5D00` god help.
- military-sentiment: Artemis/Ares guardians `0x00569360`.
- economy/walkers: carts `0x00543DE0`, `storage_select`, `0x0048A140`; artisan handler.
- map-buildings: composite layout loading `0x0053E2E0`/`0x00540110`, piece placement.
