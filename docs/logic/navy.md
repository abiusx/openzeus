# Navy and sea invasions: triremes, enemy warships and transports

Status: decoded from re/decomp/zeus.c and disassembly (jump table 0x4BFFF4, stub 0x4D4790, victim finders
0x4DCE00/0x4DCE20, the 0x34 missile's shooter dispatch), 10-29 (track 1B). Not yet checked on the oracle.
Scenario offsets were checked on .pak maps ("The Birth of Atlantis": sea entry (11,79), exit (123,83), sea points
(10,77)/(125,81), 3 landing points). Our implementation: sim/military/navy.py (see the end).

Notation: F a figure (stride 0x184, base 0xDBD788), B a building, dist = Chebyshev, val(F,c) = figure_type_value
0x4E1B20. "moving" = the handler-local flag that picks the walk or idle picture. dir 8 = arrived, 9 = route lost
(recompute), 10 = no route.

## Fields
Figure: +0x02 enlisted for an expedition (army dialog); +0x10 saved_action; +0x30/+0x32 transport landing x,y
(trireme: last tile); +0x34 next action after 0x19 (0x14 in practice); +0x36 timer; +0x5E destination building;
+0x68 number of enemy warships targeting it; +0x6A attack_timer (1 = fire this tick, then +1 a tick in the sprite
code until it wraps); +0x6B reload; +0x6E nationality (0x3F/0x40); +0x76 water_mode = 1 (every tick); +0x80 warship
spawn month; +0x82 target; +0x84 attacked_by; +0x92 re-route counter (+1 a tick, at 100 -> 0 and route_free: stub
0x4D4790, ships 0x3F/0x40); +0x108 retarget countdown (-1 a tick at the top of the trireme handler); +0x110 event
(0x40); +0x118 selected on the map; +0x128/+0x12C ship hp / max; +0x130 u8 loaded (transport); +0x131 attack
animation frame; +0x132 i16 expedition event (-1 home; figure_create sets -1; named god_budget_curse in our tsv);
+0x150 crew overlay picture; +0x15C sub-state; +0x164 ram cooldown (dead, see 0x7); +0x16C payload class*1000+n;
+0x170 invasion serial; +0x174 nation; +0x178 target class (ev+0x38); +0x17C event.
Warship wharf 0x88: +0x3C wood, +0x40 workers, +0x54 progress, +0xB6 the ship on the water-exit tile, +0xB8 trireme
id, +0xBA status, +0xC4 bit 1 crew sent home, +0xDA under construction, +0xDC armor.
Globals: wharf count DAT_00DB7B34; player triremes 0xFEB0B8, at home 0xFEB0B9 (recounted at cycle step 9,
figures_type39_count 0x4DF3C0).

## Map points (scenario block rank 14 at 0x902928; block offset = address - 0x902928)
| what | address | offset | type |
|---|---|---|---|
| map w, h | 0x902954 / 0x902958 | +0x2C / +0x30 | |
| invasion points x | 0x902C10 | +0x2E8 | i16[16]: 0..7 land, 8..15 sea |
| invasion points y | 0x902C30 | +0x308 | i16[16] |
| land exit | 0x902CB8 | +0x390 | |
| sea entry | g_sea_entry 0x902CDC/CDE | +0x3B4 | i16 x,y |
| sea exit | 0x902CE0/CE2 | +0x3B8 | i16 x,y |
| landing points x | 0x902E20 | +0x4F8 | i32[3] |
| landing points y | 0x902E2C | +0x504 | i32[3] |
Empty = -1. Correction for trade.md: the sea exit is its own point at 0x902CE0 (CDC/CDE are the entry's x, y).
Sandbox: land points (148,190) (166,172) (217,105) (94,19); sea point 9 = (34,80); landing point 0 = (104,101).

## Helpers
- `snap_ship(x,y)` 0x461C20: keep t if grid_ship[t] is 0..0x7F and no figure stands on t (grid 0xD0D878); else
  scan rings 1..227 (top row, bottom row, left column, right column) for the first such tile.
- `route_tile_check` 0x4D2C60: the same ring search for a tile with grid_route & 0x1C, no building, no terrain
  bit in 0x300203.
- `building_water_exit(x,y,size)` 0x4A3FD0: the first tile of g_adjacent_ring[size] (24 entries) with water bit 4,
  without bit 8, whose flood (0x4A1FF0(4) then 0x4A6CA0) is > 7 -> 0xF13944/0xF13940.
- `water_line_point(x0,y0,x1,y1)` 0x409640: along the line, the farthest tile (squared distance from the start)
  whose own and N/S/E/W tiles are water (bit 4), grid_ship != 0xFF and g_grid_route_distance > 0 (left over from
  the last BFS: not certain which).
- `flee_point` 0x4D0910: 3 candidate offsets (+-10 or 0 per axis) chosen by direction_to(threat -> self), tables
  in 0x4D1C00, 0x4D3970, 0x4D3DA0 (copy literally); water_line_point(self, self+offset) for each; the best snapped.
- `ships_near(F, 18, kind)` 0x4D0A10: nearest by squared distance in the box x-9..x+8, y-9..y+8; kind 0 enemy ship
  (0x40, or 0x3F with nationality != 8; 0x4D0DF0); kind 1 a trireme 0x39 or fishing boat 0x19 (0x4D0D90).
- Movement: figure_move(F, speed) with water_mode 1 uses the ship BFS (pathfinding.md 7). `charge_move(F,0)`
  0x4D0B30: nothing when already at dest with dir 8; speed = val(F,8), 18 if > 17, at least 3. `charge_move(F,1)`:
  charge tiles +0x134 reset on a turn, speed col8 once charge_tiles >= col10 else 2*col8 capped 18 (trireme col10
  = 0: col8).

## Combat
**trireme_target(F, thr)** 0x4E1410 -> 0x4E1440: figures with state 1, not action 4, not hidden; weight w: 0x28..0x2A
15 only if dist <= val(current figure, 6); 0x3F (nationality != 8) 10, or 25 when loaded, no limit; 0x40 17, no
limit. bestW = 0, bestD = thr; a candidate replaces the best when bestW - bestD < w - d. Returns the id (x,y in
0xF13944/40). thr = 228 (whole map) or the range col6.
**warship_target(F, thr)** 0x4E1800 -> 0x4E1830: the same rule, skips figures abroad (0x4E17A0), needs line of sight
(los 0x4D9B80: blocked by 0xC001 tiles or a building piece & 0xF; the first 6 tiles free when shooting from a
wall/tower). Weights: 0xB/0xC/0xD 100 if dist <= the warship's col6; trade ship 0x14 and fishing boat 0x19 10;
trireme 1000 - 10*(+0x68) if its target is a loaded-able transport (0x3F nat != 8), else 500 - 10*(+0x68).
**nearest_warship(x,y,5)** 0x4E16A0: a 0x40 with dist < 5 and line of sight.
**fire(F, tx, ty, type)** 0x4D9D70: missile at F's tile (owner 1), +0x5A shooter, dest = target tile, line_move_init
to target * 15, direction = dir16*2, slope_offset = shooter's + 18 (0x4D9D20 first: 0x4DB3D0(F,1), sound/visual).
- Trireme fires 0x2D (walker_player_missile 0x4BACE0): 4 fine units a tick (15 = a tile), dies at age > 120; hits
  the first figure on its tile per 0x4DCD30: 0x28, 0x29, 0x2A, 0x3B, 0x40, 0x3F (nat != 8), god 0x43 col0 10,
  monster 0x44 col0 8; not action 4, not hidden. figure_hit(shooter, victim, 1), then the missile dies. A dead
  (state 2) trireme's missile does no damage.
- Warship fires 0x34 (0x4BD970): age < 121, same movement; hits anything on its tile except types 0, 6, 10, 0xE,
  0x22, 0x23, 0x28..0x2A, 0x2D, 0x34, 0x3F, 0x40, god col0 != 9, monster col0 != 7 (0x4DCE40): triremes, fishing
  boats, trade ships, citizens. Victim 0x39/0x19 and shooter state 2: no damage. Never damages buildings.
- Damage (figure_hit 0x4D54D0): shooters 0x39 / 0x40 are not in {0xB, 0x27, 0x28, 0x2E}: melee columns A = val(att,2),
  D = val(tgt,3) (armor cap 19); dmg = max(0, A - A*D/20). Trireme col2 is scaled by crew% (col5, missile attack
  15, is not used by triremes). Ship victims (0x19, 0x39, 0x3F, 0x40): hp -= dmg; dmg > 0 -> a splash
  (collapse_debris_spawn(x,y,0,0,4,0)); hp < 1 -> hp 0, action 4, timer 0, 0x4DAB30. Examples (Normal, full crew):
  trireme vs Greek warship 80 - 16 = 64 a hit; warship vs trireme 90 - 13 = 77. Enemy archers 0x28 hit triremes with
  col5 against trireme col4 = 6.
- Dying (0x4D60B0): timer +1 a tick, removed at 128.
**Crew%** (figure_type_value case 0x39): p = B.workers*100 / model_building_value(type, 5) (0 if B+0xDA); crew = 100 if
p == 100, 75 if p >= 76, 50 if p >= 51, else 0. Columns 2 and 5 x crew/100 (x1.5 under Poseidon with B+0xC4&0x20);
col8 = max(3, crew*v/100); hp not scaled (300). Trireme row (Normal): hp 300, atk 80, armor 3, missile armor 6,
range 8, rate 60, speed 7, col10 0.
**Enemy ship stats** (cases 0x3F/0x40): g_enemy_model[army*84 + 56 + col] (transport, row 4) or +42 (warship, row 3),
army = formation[F.formation].army; ships have formation 0, record 0, no writer found: **not certain**, effectively
army 0 (Greek) for every nation: warship 300/90/4/5, range 9, rate 80, speed 8; transport hp 100, armor 3, speed 6.
Nationality only picks the pictures.

## Trireme 0x39 (fig_handler_trireme 0x4BF4C0; init figure_combat_init 0x48CCF0)
Every tick, before the switch:
```
b = F.building; F+0x108 -= 1
if F+0x132 >= 0 and action != 4:                 # abroad
    if action == 0xD: (b == 0 -> state 2); hidden = 1; return
    if action != 0xC: route_free; +0x44 = 0; +0x39 = 0; action = 0xC
if target and (target.state != 1 or target.hidden): target = 0
if b == 0: action -> 4 (timer -1 if new)
elif B.trireme == F: dock = water_exit(B); B+0xB6 = F if F on that tile else 0
elif B.trireme is a live 0x39 of b: F.building = 0; state 2                       # duplicate
else: B.trireme = F
hidden 0; water_mode 1; sprite_extra 0
if B.state != 1 or hp < 1: action -> 4
hp% = hp*100/max
if action not in (0x13, 4) and 0 < hp% < 16: return_to_wharf(F)                   # repair
if b:
  if B.workers < 1:
     if action not in (0x18, 4, 0x1C, 0x1D) and not (abroad and action == 0xD): return_to_wharf(F); action = 0x1C
  elif auto_defend and enemy_ships() and action != 0x1A and hp% >= 100 and +0x132 == -1: go_hunt(F)
```
enemy_ships() = 0x4AC7C0(1): g_enemy_warships > 0 or g_enemy_transports > 0. go_hunt = 0x4D1DD0: action 0x1A,
target 0, +0x15C = 0xB, +0x108 = 0. **return_to_wharf** 0x4D0800: b > 0 -> action 0x13, home = pos, direction =
prev_direction, +0x5E = b, dest = water exit, route_free; else auto_defend -> go_hunt, otherwise 0x14 + hold_here
(0x4D1E00: dest = roam_start = pos, route_free).

Actions (jump table verified; anything unlisted or > 0x1D -> 4, sinking, timer -1):
| action | function | behaviour |
|---|---|---|
| 4 | 0x4D24C0 | dying |
| 6 | 0x4D0C60 + 0x4D24D0 | at the dock after launch or repair: moving 0; timer +1, > 49 -> 0: with b: action 0x19, +0x34 = 0x14, B+0xB6 = F, dest = water exit, home = pos, route_free, auto_defend -> go_hunt; without b: auto_defend -> go_hunt else 0x14 + hold_here. Fire (0x4D24D0): reload +1, > col7 -> 0, t = trireme_target(F, col6), attack_timer = t ? 1 : 0, fire 0x2D at t when 1 (no further range check) |
| 7 | 0x4D16A0 | charge-move to dest (no writer; used inside 0x12/0x16/0x1A/0x1B): charge_move(F,1); target within 3 -> dest = pos, route_free, moving 0. The ram probe (0x4D0E50) result is discarded: no ramming. dir 8 -> moving 0; 9/10 -> route_free |
| 9 | 0x4D1C00 | evade (no writer): sub 8 move (0x4D1B20) -> sub 0xB; sub 0xB: moving 0, timer to 75, then threat = ships_near(F,18,0) -> dest = flee_point, sub 8 |
| 0xC | | sail abroad: dest = g_sea_entry, figure_move(val(F,8)); dir 8 -> 0xD + route_free; 9 -> route_free; 10 -> 4 |
| 0xD | | hidden (abroad, parked on the sea-entry tile) |
| 0xE | | back from abroad: hidden 0, timer 0, charge_move(F,0); 8 -> 6; 9 -> route_free; 10 -> 4 |
| 0xF | 0x4D1B20 + 0x4D2550 + 0x4D2690 | go to dest and hold (no writer) |
| 0x12, 0x1A | 0x4D1860 | hunt (0x1A = auto-defend), below |
| 0x13 | 0x4D23F0 | to the wharf for repair: charge_move(F,0); dir 8: timer 0, moving 0; hp >= max: no auto_defend -> 0x14 + hold_here; auto_defend, no enemy ships, b -> 0x18 and B+0xC4 \|= 1 (crew home); else go_hunt. hp < max: wait (the wharf repairs). 9 -> route_free; 10 -> 4 |
| 0x14 | 0x4D22E0 + 0x4D2550 + 0x4D2690 | hold position (anchored), below |
| 0x15 | 0x4D1F70 + 0x4D2260 | patrol (no writer) |
| 0x16 | 0x4D2840 | chase (from 0x15 only) |
| 0x17, 0x1C | 0x4D2350 | to the wharf: dir 8: timer 0, moving 0; 0x1C -> 0x1D; 0x17 -> 0x18 and B+0xC4 \|= 1; 9 -> route_free; 10 -> 4 |
| 0x18 | | moored, unmanned (moving 0) |
| 0x19 | 0x4D1E70 | ordered sail: charge_move(F,0); 9/10 -> route_free; 8: action = +0x34 (0x14), UI refresh, hold_here |
| 0x1B | 0x4D2700 | attack an ordered target: target invalid -> t = trireme_target(F,228); none -> 0x14 + hold_here; else target (dest unchanged). Valid: in range -> reload/fire; then 0x4D16A0 toward the order's dest |
| 0x1D | | unmanned, waiting at the wharf: moving 0; hp% < 100 and b and workers > 0 -> return_to_wharf (repair) |

Hunt (0x12/0x1A, 0x4D1860): sub 0xB: no target -> t = trireme_target(F,228); target and +0x108 > 0 -> +0x108 = 0,
charge_move(F,0), moving 0 if dir >= 8; otherwise t = trireme_target(F,228), +0x108 = 50. With t: sub 7, direction =
prev_direction, dest = t.pos, target = t (t.flags |= 2), t+0x84 = F, route_free, +0x108 = 50; dist < 3 -> dest = pos,
moving 0. No t: +0x108 = 0, route_free, idle. Sub 7: +0x108 < 1 -> drop the target, sub 0xB, +0x108 = 50; else dist <
col6 -> reload +1, > col7 -> 0 and attack_timer 1; fire (0x4D17D0) at the target's tile; then 0x4D16A0 (dest is not
updated while the target moves); dir 8 -> route_free.
Hold (0x14): move 0x4D22E0 (charge_move(F,0); 8 -> timer 0, moving 0; 9 -> route_free, moving 0; 10 -> moving 0).
Fire 0x4D2550: reload +1, > col7 -> 0; t = trireme_target(F, col6) when there is no target or +0x108 < 1 (then +0x108
= 50), else the current target; t and dist < col6 -> attack_timer 1, target, fire; else attack_timer 0, target 0.
Facing 0x4D2690: timer +1, > 19 -> 0 and prev_direction toward nearest_warship(F,5) (none: figure 0's x,y, scratch).
0x4D22E0 resets the timer every tick while parked, so in 0x14 this never fires (it does in 0xF).
Patrol 0x15 (0x4D1F70, unreachable): charge_move only without a target; waypoints by +0x15C: 1 sea exit -> 2 the wharf
-> 3 sea entry -> 1 (snapped); sub 0: the nearest (Manhattan) of entry (3), exit (1), B (2); 9/10 -> sub 0. 0x4D2260:
no target -> t = trireme_target(F,col6) -> target, dest, action 0x16. Chase 0x16 (0x4D2840): target gone -> 0x15, sub 0;
in range -> reload/fire; dist < 4 or <= col6 - 2 -> dest = pos; else at dir 8 dest = target.pos; route_free; 0x4D16A0.

**Launch and repair** (buildings_spawn_walkers 0x48CFB0 case 0x88, cycle step 31 = once a day). Needs the palace and
road access. Clear B+0xB6 unless a live 0x39. If status & 0xF000 == 0: B+0xB6 set and that ship in 0x13 -> status
0x2039; else no live 0x39 of B (building_second_walker_alive(B,0x39,0)) and wood >= 200 and armor >= 200 -> 0x1039
(acted on from the next day). rate: p = workers*100/needed -> 10 (>= 100), 8 (>= 75), 6 (>= 50), 4 (>= 25), 2 (>= 1),
0; 0 when under construction or the type is disabled (then progress = 0 too).
- 0x1039: wood < 200 and DAT_00665DF0 == 0 -> rate 0; progress += rate; > 319 -> progress 0; with a water exit:
  figure_create(B+0x01, 0x39, exit, dir 0), B.trireme = F, status 0, F.building = B, wood -200, armor -200, action 6,
  combat init. No water exit: the progress is lost, the status stays.
- 0x2039: B+0xB6 empty or dead -> status 0; else hp += rate, >= max -> hp = max, status 0, ship action 6. So repair
  needs the ship on the water-exit tile in action 0x13 (no re-check during the repair).
- Wharf removed: DAT_00DB7B34 -1; the trireme sinks (B.state != 1).

**Player orders.** Click a trireme (0x4092A0, 0x4DCCB0: a 0x39 on the tile or its 8 neighbours with +0x132 < 1):
selected (+0x118, g_selected_companies; with DAT_00F9C10C, probably Shift, toggles; max 20). The order click
(0x4093E0 from 0x5148F0), only with auto-defend off, per selected trireme: skipped in 0x18, in 0x13 with hp% <= 15, or
crew <= 49 % (50 % passes but its crew factor is 0: attack 0). An enemy (0x4DCD30) on the tile: +0x10 = action,
action 0x1B, target, dest = its tile. Else, if not on the tile: dest = roam_start = water_line_point(pos, click),
route_free, +0x34 = (action if +0x34 == 0x1A else 0x14), action 0x19.
Military advisor navy row (0x591400(i), the i-th live wharf with a trireme and (workers > 0 or C4&1)): actions {6, 7,
0xE, 0xF, 0x14, 0x15, 0x19, 0x1B, 0x1D} -> return_to_wharf then 0x17 (send the crew home); {0x17, 0x18} -> 0x14 +
hold_here, clear C4&1 (crew back aboard). Toggle "crew all / stand down" (0x40A380, flips 0xFEAF20; 51:2..5): stand
down: every trireme with F+0x02 == 0 -> return_to_wharf, 0x17; crew all: clear C4&1, return_to_wharf.
C4 bit 1: set by 0x4D2350/0x4D23F0, cleared by these orders and by mobilize; makes building_industry_halted 0x4873F0
true for 0x88 (no workers); figure_fight_start refuses a fight with such a trireme; an attacker aiming at it walks to
it (0x531DF0: action 0x1C).

**Auto-defend** (month_advance day 0, option on): mobilize 0x568D20 at months_to_next_invasion == 1: sea = the
soonest invasion's point index (0xFEAE60) > 7; companies are mobilized; only if at least one company was selected and
sea: every wharf clears C4&1 and its trireme with +0x132 == -1 goes hunting (go_hunt). Dismiss 0x569010 at
months_since_enemy == 1 and 0xFEB4F9: every trireme at home (+0x132 == -1) -> return_to_wharf (on arrival with full hp:
0x18, crew home).

**Advisor label** 0x591680(wharf) -> group 51 (and clickable):
| trireme | text | clickable |
|---|---|---|
| none | -1 (no label) | |
| 6, 0xF, 0x14, 0x1A, 0x1D | 34 Anchored | yes |
| 7, 0xE, 0x15, 0x19 | 35 Sailing | yes |
| 0x17 | 36 disembarking | yes |
| 0x13 not yet arrived (dir != 8) / 0x1C | 37 returning | no |
| 0x13 arrived | 38 repairing | no |
| 0x18 | 33 Unmanned | yes |
| 0x1B | 39 fighting | yes |
| 0xC, 0xD | 40 abroad | no |
| else (4, 9, 0x12, 0x16) | -1 | |
Hull (0x591C30): hp% < 26 -> 51:53 barely afloat; < 50 -> 52 mangled; < 75 -> 51 damaged; < 100 -> 50 leaky; else 49
undamaged. Tooltips 51:41..48. (Corrects bugs.md 175: 0x1A is Anchored; 0x24..0x28 were text indexes.)

**Wharf info window** (FUN_00583C60, 10-31; layout in docs/play/info.md "Trireme wharf window"). Its button (table
0x00642B38, 384 x 20 at (L+0x28, T+(H-2)*16)) exists only while +0xB8 (trireme) == 0; its click 0x00572490 flips
C4 & 1 (the "crew sent home" bit: the mask is 1, called "bit 1" above) and nothing else: 175:20 "Send Wharf workers
home." while clear, 175:19 "Staff this Trireme Wharf." while set; with the bit set the wharf gets no workers
(building_industry_halted). The window reads: the palace (175:18), status +0xBA (0x1000 building: "Production is
n% complete" from +0x54 * 100 / 320, drawn only while the crew-all flag 0xFEAF20 is set; 0x2000: 175:16 repairing),
+0xB6 (the trireme on the water-exit tile: 175:14), +0xB8 == 0 and not 0x1000: 175:17. 175:15 ("sailing") is never
drawn. Seen: re/oracle/runs/wharf-window/w2.bmp (crew home, the trireme at the wharf, 3 + 3 loads).

## Expeditions (triremes)
- Send 0x4DEB30: only if 0x46ED20 (event type != 4, the city exists, city+0x140 == 2: sea route, not certain). Every
  0x39 with state != 0, owner 1, +0x02 set and +0x132 < 0: +0x132 = event, action 0xC: sails (visible) to g_sea_entry
  at crew speed, hides there (0xD). Strength 6 per trireme (0x4DEA00); plunder capacity 600 per trireme.
- Casualties 0x4DF120(pct, ev): tier = 200 if pct >= 80, 150 if >= 60, 100 if >= 40, 50 if >= 20, else 0. In index
  order: while sunk < floor(n*pct/100), or hp <= tier: hp 0, action 4, +0x132 = -1, flags |= 0x10 (sinks at the sea
  entry); else hp -= tier.
- Return 0x4DEE60(ev, all): state 1 and +0x132 == ev: home = pos, dest = B's water exit, +0x132 = -1, +0x02 = 0;
  action not 0x13/4: 0 < hp% < 100 -> return_to_wharf; else action 0xE (-> 6).

## Sea invasions
Spawn: invasion_spawn 0x504600 sends points 9..16 to invasion_spawn_sea 0x503FD0(nation, strength, pt, target, ev):
ev active, city+1 = 1, strength <= 256, serial +1. Point: pt - 1, then the first valid of 8..15 cyclically (0x503E20);
none -> the land exit. Facing as on land (y 0 -> 4, y >= h-1 -> 0, x 0 -> 2, x >= w-1 -> 6, else 4).
- Warships: ev+0x36 of them (strength/4 for the scratch event 0x8C; 0 for nation 8). For i: months_since_enemy = 0;
  figure_create(0, 0x40, snap_ship(point), facing); +0x0D 0, action 6, timer 25i + 10, hidden, water_mode 1; 0x504B20
  hp = max = col1, speed, +0x130 0; g_enemy_warships +1; +0x6E nationality, +0x80 = month, +0x110 = ev.
- Transports: per class counts = col9 (row 1 missile, row 0 infantry, row 2 cavalry) x strength / 100, classes in the
  order missile (0), infantry (1), cavalry (2); up to 8 soldiers each: figure_create(0, 0x3F, snap_ship(point),
  facing); landing (+0x30/+0x32) = landing_points[ev+0x78] (-1: snap_ship(route_tile_check(spawn))); action 6, timer
  40k + 10 (k = transport ordinal), hidden; 0x504AB0 hp, speed; g_enemy_transports +1; +0x130 = 1, +0x110 = ev,
  +0x16C = class*1000 + n, +0x170 serial, +0x174 nation, +0x178 target class, +0x17C ev.
**Transport 0x3F** (0x4C24F0). Pre: water_mode; hp < 1 -> 4; action not 5/4, unloaded, 0 < hp% < 16, action != 0xE ->
action 8, sub 0xD, timer 100 (every tick); re-route stub.
- 6 (0x4D29D0): unhide, moving 0, timer -1; < 1: loaded -> home = pos, dest = landing, action 0xB, reload 0,
  route_free; else dest = sea exit, action 0xE.
- 0xB (0x4D3740): figure_move(col8). Arrived: moving 0; (x,y) = route_tile_check(landing); terrain & 0x300203 ->
  timer 50, unloaded, action 6. No water bit and 0xC008 -> building_destroyed_by_attack(x, y, t, 0). Water without
  0x40 -> timer 50, unloaded, action 6. Then unload (0x4D2B10): (nation 8 only: wait for the Destruction group 54
  frames) class = P/1000, n = P%1000; enemy_army_spawn_land(+0x174, missile, infantry, cavalry, x, y, +0x178, +0x17C)
  with n in its class; unloaded; nation 8 -> state 2, else action 6; message 0xDD "disembarked" once per event
  (0x461AB0, ev+0x57 |= 0x40). dir 9 -> route_free; 10 -> 4.
- 0xE (0x4D3870): figure_move(col8); arrived at the sea entry -> dest = sea exit; at the sea exit: unloaded -> state 2
  (gone), loaded -> action 6; elsewhere -> dest = sea entry. 9 -> route_free; 10 -> 4.
- 8 flee (0x4D3970): sub 7 move (dir 10 -> 4), dir 8 -> sub 0xD; sub 0xD: moving 0, timer to 75, threat =
  ships_near(F,18,1): none -> dest = sea exit, 0xE; found -> flee_point, sub 7. The pre-switch resets sub 0xD and
  timer 100 every tick, so a damaged transport never moves while a trireme or fishing boat is in the box (literal
  reading).
- 7 move only; 10 nothing; other -> 0xE.
**Warship 0x40** (0x4C2980). Pre: hp < 1 -> 4; not 4/5: 0 < hp% < 16 -> action 10, sub 0xD (every tick); (+0x80 + 4) %
12 == month -> action 0xF, dest = sea exit (every tick of that month); re-route stub.
- Opportunistic fire (0x4D47D0, actions 6, 7, 9, 10, 0xE, even hidden in 6): reload +1, > col7 -> 0, t =
  warship_target(F, col6): attack_timer 1 and face t, else 0. attack_timer 1 -> fire 0x34 at t; the old target's
  +0x68 -1 (>= 0); target = t; t+0x68 +1. attack_timer +1, > 100 -> 0.
- 6 (0x4D3B70): timer -1; < 1: unhide, home = pos, dest = sea entry, action 0xE.
- 0xE patrol (0x4D4500): charge_move(F,0), moving 1; **one RNG step every tick** (31 LFSR steps); timer +1, >= rng_15 %
  30 + 75 -> timer 0, action 8, sub 0xD. Arrived: L = the first valid landing point (snapped): at the sea entry ->
  dest L (none: sea exit); at L -> sea exit; elsewhere -> sea entry. 9/10 -> route_free.
- 8 hunt (0x4D3F90), r = col6: target with state != 1 -> sub 0xD, target 0. Sub 0xD: t = target, or
  warship_target(F,228); dist >= r -> release and re-pick (228); none -> 0xE. t a soldier (0xB..0xD) or trireme: RNG
  step, rng_a & 1 -> +0x80 = (month + 1) % 12 (delays leaving). Soldier: dest = pos (shoot from here). Ship: dist < 3
  -> moving 0, else dest = t.pos, moving 1. Sub 7, direction = prev, release the old target, target = t, t+0x68 +1,
  route_free. Sub 7: dist < r -> reload, > col7 -> attack_timer 1 (with a target); fire 0x34; attack_timer +1 (wraps
  100). Soldier target: no move (out of range: timer +1). Else 0x4D3C40: charge_move(F,1), moving 1, dist < 3 -> stop
  (ram probe dead); 8 -> action 8 sub 0xD; 9 -> route_free; **10 -> action 4**. Then dir 8 or timer > 24: timer 0, sub
  0xD, route_free.
- 7: 0x4D3C40 + fire. 9 (0x4D3BF0): move, unhide (no writer). 10 flee (0x4D3DA0): sub 9 move, 8 -> sub 0xD; sub 0xD:
  timer to 75, ships_near(F,18,1): none -> 0xE, found -> flee_point, sub 9; plus fire. The pre-switch keeps a damaged
  warship in 10/sub 0xD, so it stays put (except in its leaving month) and keeps firing.
- 0xF leave (0x4D4730): charge_move(F,0); 9 -> route_free; 8 or 10 -> state 2. 5 nothing; other -> 0xE.
- Warships never target buildings, never ram, never melee.
**Counters and the end.** 0x504B20/0x504AB0 count up; figure_delete counts down (a 0x3F also clears +0x92 of its
slot); enemy_ships_recount 0x4E13C0 only after a load. While warships or enemy units live: months_since_enemy resets,
steps 13/14 frozen, auto-defend can't be toggled. cities_relations_update 0x568C20 (weights 0x5687A0): warships and
unloaded transports weigh 0; a loaded transport of a city with flags & 3 == 0 adds weight from P = +0x16C taken whole
(class*1000 + n), split by the army's col9 ratios (missile P*col9(row1)/100, cavalry P*col9(row2)/100, infantry the
rest), weights 2/1/3: a loaded class-1/2 transport weighs ~1000-2000 (exe bug, kept; not certain it's intended).
Army withdraws (0x481E80): the city's transports -> sea exit, action 0xE (unless 4), unloaded; warships (by +0x110's
city) -> sea exit, action 0xF.

## Pictures
id = collection*512 + group + 1; collections 16 SprAmbient, 17 Destruction, 18 Zeus_Greek, 51 SprMain, 53
PoseidonImps; groups below are 0-based atlas groups, "first" = the exe image index. Image = first + frame*dirs + dir
(frame/dir clamped, 0x5AF770); animation 0x5AF8C0 advances when DAT_006668EC[speed] is set (a clock every speed*20
ms, not certain about the unit). d = (dir if <= 7 else prev_direction) - view, mod 8; 16-direction groups use 2d + 1.
Trireme (Zeus): base = hull; overlays = selection flag (+0x180, only when +0x118) and crew (+0x150). walker_draw
0x0044FEF0: with P = the hull's point (the hull at P - its offsets), the crew at P + (-1, -10), the flag at P + (-1 +
F+0x6C, +4 + F+0x6D) (0 for a trireme); the crew is drawn whole (oracle run 1B-trireme-frames, scenarios/trireme-frames.txt: shots
every 0.1 s: at tick 28 PoseidonImps 8309 at P + (-1, -10), all 2365 non-shadow pixels equal, the 734 shadow pixels
0x7C00 darkened). Which picture (the handler's tail, zeus.c ~128060): moving -> crew 133 by frame; standing -> crew 133
frame 0 unless the wharf's +0xC4 bit 1 (crew home) is set, whatever the action; attacking 135; dying 134. The diamond
patch in 1B-trireme t_83.bmp is stale screen memory, not a clip: the exe never repaints the moored ship's tile diamond
(frame 003 after the camera poke shows the old view's pixels there, frames after tick 28 the crew of tick 28, while the
dumps have +0x150 = 0 from tick 29: action 0x1D with the bit left over from 0x18). As original, not copied (bugs.md 236).
| state | base | overlays |
|---|---|---|
| moving | SprMain 120 (first 6569, 4 x 16, speed 5), index 2d+1 | flag PoseidonImps 131 (8228, 4 x 16) frame anim, 2d+1; crew PoseidonImps 133 (8300, 4 x 8) frame anim, d |
| still | SprMain 122 (6729, 1 x 8), d | flag 132 (8292, 1 x 8); crew 133 frame 0 |
| still, crew home (C4&1) | SprMain 122 + d | flag 132 only, no crew |
| attacking | SprMain 120 frame +0x131 (0 at attack_timer 2, +1 a tick), 2d+1 | flag 131 frame +0x131; crew PoseidonImps 135 (8428, 12 x 8) frame +0x131/3 |
| dying | SprMain 121 (6633, 12 x 8) to the last frame, then SprAmbient 20 (633, 23 frames, no dir) frame timer % 23 | crew PoseidonImps 134 (8332, 12 x 8) until the last frame |
Enemy warship: nationality 0 Zeus_Greek groups 10 (moving 4 x 16), 11 (dying 12 x 8), 12 (idle 1 x 8); any other
SprMain 92 (4833), 93 (4897), 94 (4993) (table 0x6383BC/0x6383C8). Moving: anim +1 a tick, wraps at 4: first + anim*16
+ 2d + 1. Idle (moving 0 or +0x154 == 2): first + d. Dying as the trireme with 11/93 then SprAmbient 20.
Transport (nationality != 8): SprMain 196 (9340, 4 x 16) moving, 198 (9500, 1 x 8) idle, 197 (9404, 12 x 8) dying then
SprAmbient 20. Oceanid (8): Destruction 54 (1670, 6 frames) moving/dying, 55 (1676, 10 frames) unloading frame = reload
% 10. Missiles 0x2D / 0x34: SprAmbient group 71 + ((dir32 - 13) & 31), shadow group 70 + the same; dir32 = direction -
view*4, mod 32.

## Not certain
1. Enemy ship stats from formation record 0 (probably Greek for every nation): oracle check needed.
2. The animation clock unit (ms?).
3. No writer found for trireme actions 7, 9, 0xF, 0x12, 0x15, 0x16 (dead code or a path not found); warship action 9
   and +0x154 = 2.
4. city+0x140 == 2 in 0x46ED20 (naval expedition eligibility); DAT_00F9C10C (Shift?), DAT_00F2A708.
5. 0x4DB3D0, 0x4DAB30, 0x4DB7A0, 0x4DC150 (sound, visual or death handling).
6. Which BFS last filled g_grid_route_distance for the order line test; the facing fallback reading figure 0.
7. Literal readings not seen at runtime: damaged ships stuck in place, a warship's route failure sinks it, the
   transport payload weight, triremes mobilized only when a company was selected; a transport reaching a land landing
   tile depends on the ship BFS passing shore tiles (grid_ship 0xFB).

## Ours: sim/military/navy.py (10-29)
- Triremes: launched by the wharf as before (sim/systems/economy.py; since 10-31 only with a palace and road access,
  as case 0x88 of 0x48CFB0; the daily repair too), then driven by navy.py with the exe's action
  numbers (`w.act`): 6 -> 0x19 -> 0x14 anchored in front of the wharf (shore.mooring = the water exit), firing at
  trireme_target's pick within range; 0x1A hunting under auto-defend while enemy ships live; 0x1B / 0x19 player orders
  (`trireme ID X Y`); 0x13 repair (hull < 16 %; the wharf adds 10/8/6/4/2 a day by staffing, wharf_day), 0x1C/0x1D
  unmanned when the wharf has no workers, 0x17/0x18 crew home (`trireme ID crew`, the advisor's navy button; the
  wharf's `off`), 0xC/0xD/0xE expeditions. Not ported: patrol/chase (0x15/0x16, no writer found), evade (9), the
  facing timer, multi-selection.
- Expeditions: the army dialog's ship rows (`raid|conquer CITY ... ships ID,ID|none`; default all at home when the
  route is by sea): strength +6 each, plunder +600 each, casualties by tier (0x4DF120), back to the wharf (0x4DEE60).
- Sea invasions: `invasion_create` picks (rnd & 7) + 9 for a city with a sea route; invaders.invade(sea_pt) ->
  navy.invade_sea. Warships patrol entry -> landing -> exit, hunt after 75..104 ticks (our own RNG), fire at
  warship_target's pick, leave in month (spawn + 4) % 12; damaged (< 16 %) ones stay and fire (see below). Transports sail to the
  landing point, break the building on it, unload (invaders.land_companies) and sail out.
  Warships (11-02, bugs.md 421): navy.warship_act is 0x4C2980 action by action, every tick: the pre-switch (hull
  < 16 % -> 10 / sub 0xD, the leaving month -> 0xF), 6, 7 (0x4D3C40), 8 (0x4D3F90: sub 0xD pick, sub 7 reload /
  attack_timer / soldier timer / chase, dir 8 or timer > 24 back to 0xD), 9, 10 (0x4D3DA0: timer to 75,
  ships_near 0x4D0A10, flee_point 0x4D0910 with its offset table), 0xE (0x4D4500: one draw a tick, timer counter,
  navy.hunt_due), 0xF; the fire 0x4D47D0 with the reload (+0x6B) and attack_timer (+0x6A) counters (was a tick
  stamp), and the target count +0x68 (0x4D3F60). Was: a tick-stamp timer, hunts acting every 6 ticks, no flee, a
  failed patrol route retried every 10 ticks. Oracle: tools/oracle_warships.py (1B-inv-sea, the hunt triggers
  replayed from the exe's timers: the draws are the exe's RNG): 86 of 86 dumps equal (tile, action, hidden, timer).
  water_line_point does not test g_grid_route_distance > 0 (left over from whichever BFS ran last: not portable).
  The end check counts loaded transports with the exe's P = class*1000 + n weight. Withdrawal sends the ships out.
- Missiles: the trireme's 0x2D is the towers' "arrow" (it now also hits enemy ships), the warship's 0x34 the archers'
  "enemy_arrow" (it now also hits triremes, fishing boats and trade ships). Ship hits go through navy.hit (hull).
- Movement: walkers.water_path = the exe's 0x0058D500 BFS over grid_ship (walkers.ship_grid, pathfinding.md 7.1:
  water with 8 water neighbours; 0xFE edge cost 5) and the 0x0058DCE0 tracer (diagonals), for every ship (trade,
  fishing, triremes, enemy ships; bugs.md 238, 10-30). snap_ship takes grid value 0 only (open deep water), the
  transport sails onto the landing point itself (ours: snapped when ships can't be on it). Oracle: tools/oracle_ships.py
  (1B-inv-sea 758 moves, sanctuary-build 908, e1-ramps 46: every exe step on ours' route; all-water passability: 282
  and 92 off). Trade ships, fishing boats and triremes: one tile per step at the model speed. Enemy transports and warships
  move tick by tick as the exe (navy.sail_fine: tile_progress, speed_phase, tile change at progress 8) with the
  exe's route free every 100 updates (0x004D4790), which skips the rest of a tile (bugs.md 243: ~14.3 ticks a tile
  for a transport, not 15); standing ships act every 6..25 ticks. Ships never fight by tile contact (as the exe: no ramming, no melee), except
  with a monster that targets them (figure_tile_contact's monster rule, 11-02: a guardian vs an enemy transport /
  warship, a bad monster vs a fishing boat / trireme): the ship stands in action 5 (its handlers' case 5 does
  nothing: it never hits back, and stays so if the monster dies first), the monster's blows take its hull, each
  hit with debris (figure_hit: collapse_debris_spawn(x, y, 0, 0, 4, 0), missiles too), sunk below 1.
- (10-29, second round) The trireme panel's buttons (handler 0x00406400, disassembly): `trireme ID repair` (0x4D0800),
  `crewpanel` (0x17 -> 0x14; 0x18 -> 0x14 and the wharf's crew back; else back to the wharf, 0x17), `hold` (0x14 +
  0x4D1E00), `hunt` (0x1A, again -> 0x14), `patrol` (0x15 with sub 0 and no target, again -> 0x14); guards: none with
  auto-defend (except centre), none for a ship back for repairs under 16 %, none abroad. Patrol (0x15) and chase
  (0x16) are ported from 0x4D1F70 / 0x4D2260 / 0x4D2840 (their only writer is this panel button).
- Sea rally points (0x00DB6940): auto-defend against a sea invasion musters at the rally point of the landing point
  (alarm.rally_point, pt > 8) and sends every trireme at home hunting, with the wharves' crews back; dismissal sends
  them back to their wharves (0x4D0800).
- Enemy ship stats per nation, checked: figure_type_value 0x004E1B20 reads g_enemy_model[army*84 + 42/56 + col] with
  army = formation[F.formation].army; the sea spawner 0x503FD0 never sets a ship's formation (0) and no code writes
  formation record 0's +0x6A except the clamp at 10 (zeus.c 124455, 124549, 124631): every nation's ships use army
  0's rows (warship 300/90/4/5, transport 100/0/3/7), as ours. Not seen on the oracle.
- Tests: test_military_navy. CLI: `navy`, `trireme ID X Y`, `trireme ID crew`, `trireme ID repair|crewpanel|hold|
  hunt|patrol`, `invade [N] [ARMY] sea`.
