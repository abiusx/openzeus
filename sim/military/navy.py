"""The navy and sea invasions (docs/logic/navy.md): the player's triremes (figure 0x39, fig_handler_trireme
0x4BF4C0), enemy warships (0x40, 0x4C2980) and transports (0x3F, 0x4C24F0).

Triremes are launched by the warship wharf (sim/systems/economy.py, buildings_spawn_walkers case 0x88); from then on
this module drives them by the exe's action numbers (`w.act`): 6 at the dock, 0x14 holding (anchored), 0x19 ordered
sail, 0x1A hunting (auto-defend), 0x1B attacking an ordered target, 0x13 back to the wharf for repairs (the wharf
repairs it daily, navy.day), 0x17/0x1C back to the wharf, 0x18/0x1D unmanned at the wharf, 0xC/0xD/0xE sailing
abroad / abroad / home (expeditions), 4 sinking. Crew % = the wharf's staffing (100/75/50/0): attack x crew/100, speed
max(3, crew*7/100). A trireme fires a missile (0x2D, defences "arrow") at trireme_target 0x4E1410's pick; ships take
damage A - A*D/20 on their hull (+0x128) and sink below 1.

Sea invasions (invasion_spawn_sea 0x503FD0): warships (event strength / 4 for our stand-in) and transports of up to 8
soldiers per class wait hidden at the sea invasion point, then: warships patrol sea entry -> landing point -> sea exit
and hunt (warship_target 0x4E1800: soldiers in range 100, triremes 500/1000, trade ships and fishing boats 10), firing
missiles (0x34, defences "enemy_arrow") that hit triremes, boats, ships and people; they leave in the month
(spawn month + 4) % 12. Transports sail to the landing point, break the building there, unload their soldiers as land
companies (enemy_army_spawn_land) with message 0xDD, then sail out through the sea exit.

Ours: ships act per tile sailed (4-way water routes, walkers.water_path) and, standing, every few ticks; reload counts
are tick stamps; enemy ships use army 0's model rows (the exe reads formation record 0: navy.md "Not certain" 1).
"""
from ..systems import walkers
from . import units, state, mrng

SHIPS = ("trireme", "enemy_warship", "enemy_transport")
HIDDEN_WAIT = 51
N = 228
ANCHORED, SAILING, DISEMBARKING, RETURNING, REPAIRING, UNMANNED, FIGHTING, ABROAD = 34, 35, 36, 37, 38, 33, 39, 40


# --- shared ----------------------------------------------------------------------------------------------

def wharf(g, w):
    b = g.buildings.get(getattr(w, "home", 0))
    return b if b is not None and b.key == "trireme_wharf" else None


def crew(g, w):
    """figure_type_value case 0x39: wharf staffing -> 100 / 75 / 50 / 0 %."""
    b = wharf(g, w)
    if b is None or not b.employees:
        return 0
    need = g.cat.spec(b.key).get("employees", 1) or 1
    p = b.employees * 100 // need
    return 100 if p >= 100 else 75 if p >= 76 else 50 if p >= 51 else 0


def staff(g, b):
    """sidebar_draw_20 0x00525C10: the wharf's workers * 100 / model value 5 (0 while under construction)."""
    if b is None or getattr(b, "under_construction", False):
        return 0
    need = g.cat.spec(b.key).get("employees", 0)
    return b.employees * 100 // need if need > 0 else 0


def col(g, w, name):
    if w.role == "trireme":
        v = units.data()["difficulty"][g.rules.get("difficulty", "Normal")]["figures"]["trireme"][name]
        if name in ("attack", "missile_attack"):
            return crew(g, w) * v // 100
        if name == "speed":
            return max(3, crew(g, w) * v // 100)
        return min(v, 19) if name in ("armor", "missile_armor") else v
    return units.col(g, w, name)


def hp_pct(w):
    return w.hp * 100 // max(1, w.hpmax)


def dist(a, b):
    return max(abs(a.x - b.x), abs(a.y - b.y))


def hit(g, att, tgt):
    """figure_hit 0x4D54D0 for a ship's missile: attack vs armor (triremes' attack by crew); a ship loses hull,
    anyone else adds damage against its model hp."""
    if tgt.anim == "die":
        return
    if att.role in units.MISSILE_HITTERS:          # towers, wall sentries, rabble, enemy archers: col5 vs col4
        A = units.col(g, att, "missile_attack")
        D = col(g, tgt, "missile_armor") if tgt.role in SHIPS else units.col(g, tgt, "missile_armor")
    else:
        A = col(g, att, "attack")
        D = col(g, tgt, "armor") if tgt.role in SHIPS else units.col(g, tgt, "armor")
    if units.MYTH is not None and att.role in units.MYTH.ROLES:   # a monster's missile: x1.5, x2 more vs a trireme
        A, D = units.MYTH.adjust(g, att, tgt, A, D)
    dmg = 0 if A == 0 else max(0, A - int(D * A / 20))
    if tgt.role in SHIPS:
        if dmg > 0 and att is not tgt:             # figure_hit: collapse_debris_spawn(x, y, 0, 0, 4, 0) on the ship
            from .. import effects
            effects.debris(g, tgt.x, tgt.y, 0)
        tgt.hp -= dmg
        if tgt.hp < 1:
            tgt.hp = 0
            sink(g, tgt, att)
        else:
            walkers.sfx(g, tgt, "hit")             # figure_hit: FUN_004DB7A0 (ship_hit; play mode only)
        return
    tgt.dmg = getattr(tgt, "dmg", 0) + dmg
    if tgt.dmg > units.col(g, tgt, "hp"):
        units.kill(g, tgt, att)
    else:
        walkers.sfx(g, tgt, "hit")


def sink(g, w, by=None):
    """Action 4: the ship sinks (dying picture, removed after 128 ticks)."""
    w.act = 4
    w.anim, w.anim_t0, w.busy_until, w.mil = "die", g.tick, g.tick + units.DYING, True
    w.path = []
    walkers.schedule(g, w, units.DYING)
    if w.role == "trireme":
        g.message(f"A trireme has been sunk at ({w.x},{w.y})!")
    elif by is not None:
        g.message(f"An enemy {'warship' if w.role == 'enemy_warship' else 'transport'} has been sunk at ({w.x},{w.y}).")


# figure_move 0x004D1170: sub-steps this tick by speed code, (limit, a, b): a and speed_phase + 1 while
# speed_phase < limit, else b and speed_phase = 0 (walkers.md 1.3); codes 6, 12 and >= 18 are 1, 2, 3 every tick
PATTERN = {1: (3, 0, 1), 2: (2, 0, 1), 3: (1, 1, 0), 4: (2, 1, 0), 5: (3, 1, 0), 7: (3, 1, 2), 8: (2, 1, 2),
           9: (1, 1, 2), 10: (2, 2, 1), 11: (3, 2, 1), 13: (3, 2, 3), 14: (2, 2, 3), 15: (1, 3, 2), 16: (2, 3, 2),
           17: (3, 3, 2)}


def substeps(w, code):
    if code <= 0:
        return 0
    if code in (6, 12) or code >= 18:
        return {6: 1, 12: 2}.get(code, 3)
    lim, a, b = PATTERN[code]
    ph = getattr(w, "phase", 0)
    if ph < lim:
        w.phase = ph + 1
        return a
    w.phase = 0
    return b


def sail_fine(g, w, dest, speed):
    """The enemy ships' move, tick by tick as the exe (bugs.md 243): figure_route_walk 0x004D7BD0 with the
    sub-steps of figure_move 0x004D1170; tile_progress (+0x39) 0..14, 15 at a centre; the tile changes at
    progress 8 (figure_change_tile 0x004D9330), the next route step is taken at the centre. Their handlers
    (0x004C24F0 transport, 0x004C2980 warship) first call 0x004D4790: +0x92 counts every update and at 100 frees
    the route (figure_route_free 0x004D8990); figure_find_route 0x004D8220 then sets the progress to 15, so the
    ship takes its next step at once (the rest of the tile is skipped from progress >= 8, the tile is started
    again from < 8). Every 100 ticks the steady state gains 5 sub-steps (progress 9): transport 14.3 ticks a
    tile, not 15 (oracle 1B-inv-sea: progress and fine x of transport 58 at ticks 901..1020). Any other route
    free (arrival, a blocked next tile, the hunt's 24-tick timer: w.path = []) also restarts at the centre.
    Called every tick while moving; returns 8 arrived, 9 moving (scheduled for the next tick), 10 no route."""
    t = g.tick
    last = getattr(w, "mv_last", t - 1)
    t0 = getattr(w, "rr0", 0)
    route = getattr(w, "route", None)               # the exe's route (None: route_id < 1); w.path = what is left
    if route is not None and not w.path:            # incl. the tile being sailed (play mode), [] = freed by others
        route = None
    if (t - t0) // 100 > (last - t0) // 100:        # 0x004D4790 fired since the last call
        route = None
    w.mv_last = t
    prog = getattr(w, "prog", 15)
    if route is None:                               # figure_find_route: progress 15 when a route is found
        p = walkers.water_path(g, (w.x, w.y), {tuple(dest)}) if (w.x, w.y) != tuple(dest) else []
        if p is None:
            w.route, w.path, w.prog = None, [], prog
            return 10
        route, prog = p, 15
    for _ in range(substeps(w, speed)):
        prog += 1
        if prog > 14:                               # at a centre: the next route step
            prog = 15
            if not route:                           # route_step >= route_len: freed, direction 8
                w.route, w.path, w.prog = None, [], 15
                return 8
            nxt = route[0]
            if not walkers.ship_ok(g, *nxt):        # figure_check_next_tile: direction 9, the route is freed
                w.route, w.path, w.prog = None, [], 15
                walkers.schedule(g, w, 1)
                return 9
            route = route[1:]
            w.heading = nxt
            w.face = ((nxt[0] > w.x) - (nxt[0] < w.x), (nxt[1] > w.y) - (nxt[1] < w.y))
            prog = 0
        if prog == 8:
            units.step(g, w, w.heading)
    w.route, w.prog = route, prog
    w.path = ([w.heading] if prog < 8 else []) + list(route) or [w.heading]
    walkers.schedule(g, w, 1)
    return 9


def sail(g, w, dest, speed):
    """One tile toward dest over water. Returns 8 arrived, 9 moving, 10 no route (the exe's dir codes)."""
    if (w.x, w.y) == tuple(dest):
        w.path = []
        return 8
    if not w.path or w.path[-1] != tuple(dest):
        p = walkers.water_path(g, (w.x, w.y), {tuple(dest)})
        if p is None:
            return 10
        w.path = p
    nxt = w.path.pop(0)
    if not walkers.ship_ok(g, *nxt):
        w.path = []
        walkers.schedule(g, w, 15)
        return 9
    w.face = ((nxt[0] > w.x) - (nxt[0] < w.x), (nxt[1] > w.y) - (nxt[1] < w.y))
    units.step(g, w, nxt)
    walkers.schedule(g, w, units.tile_ticks(g, w, speed))
    return 9


def fire(g, w, t, role):
    from .defences import shoot
    w.face = ((t.x > w.x) - (t.x < w.x), (t.y > w.y) - (t.y < w.y))
    w.shot_t0 = g.tick
    shoot(g, w, t, role=role)


def reloaded(g, w):
    """Reload +1 a tick, fire past col7 (missile_rate): a tick stamp here."""
    if g.tick >= getattr(w, "next_shot", 0):
        w.next_shot = g.tick + col(g, w, "missile_rate") + 1
        return True
    return False


def figures(g, roles):
    from . import contact
    for ids in list(contact.tiles(g).values()):
        for i in ids:
            f = g.walkers.get(i)
            if f is not None and f.role in roles and f.anim != "die" and not getattr(f, "hidden", False):
                yield f


# --- the player's triremes --------------------------------------------------------------------------------

def trireme_target(g, w, thr):
    """0x4E1410: invaders 15 within col6, transports 10 (25 loaded), warships 17; bestW - bestD < w - d."""
    best, bw, bd = None, 0, thr
    rng = col(g, w, "missile_range")
    for f in sorted(figures(g, ("enemy_infantry", "enemy_archer", "enemy_cavalry", "enemy_warship",
                                "enemy_transport")), key=lambda f: f.id):
        d = dist(w, f)
        if f.role == "enemy_warship":
            k = 17
        elif f.role == "enemy_transport":
            k = 25 if getattr(f, "loaded", False) else 10
        elif d <= rng:
            k = 15
        else:
            continue
        if bw - bd < k - d:
            best, bw, bd = f, k, d
    return best


def enemy_ships(g):
    return any(True for _ in figures(g, ("enemy_warship", "enemy_transport")))


def dock(g, w):
    b = wharf(g, w)
    if b is None:
        return None
    from ..systems import shore
    return shore.mooring(g, b)


def return_to_wharf(g, w):
    """0x4D0800."""
    if wharf(g, w) is not None:
        w.act, w.dest, w.path = 0x13, dock(g, w), []
    elif auto_defend(g):
        go_hunt(g, w)
    else:
        w.act, w.dest = 0x14, (w.x, w.y)


def go_hunt(g, w):
    w.act, w.target, w.retarget = 0x1A, 0, 0


def auto_defend(g):
    return bool(state(g).get("auto_defend"))


def init(g, w):
    if getattr(w, "act", None) is None:
        w.act, w.hp, w.hpmax, w.timer, w.target, w.away = 6, 300, 300, g.tick, 0, -1
        w.hpmax = w.hp = units.data()["difficulty"][g.rules.get("difficulty", "Normal")]["figures"]["trireme"]["hp"]
        w.state = "navy"
    if getattr(w, "name", None) is None:
        name(g, w)


NAME_GROUP, NAMES = 269, 16    # figure_name_group 0x004E34F0 for type 0x39: text group 269 (16 names: Revenge, ...)


def name(g, w):
    """figure_assign_name 0x004DD0B0 -> figure_name_from_group 0x004DD040: the group's counter (saved, +1 per figure)
    mod the group's size. Ours: the counters start at 0 in a new game (not certain: the exe's come with the save)."""
    c = g.sd("name_counters", {})
    w.name = c.get(NAME_GROUP, 0) % NAMES
    c[NAME_GROUP] = c.get(NAME_GROUP, 0) + 1


def trireme_act(g, w):
    init(g, w)
    if w.anim == "die":
        return units.act_dying(g, w)
    b = wharf(g, w)
    if w.away >= 0 and w.act not in (4, 0xD, 0xC):
        w.act, w.path = 0xC, []
    if w.act == 0xD:
        w.hidden = True
        return walkers.schedule(g, w, 10 ** 6)
    w.hidden = False
    if b is None:
        return sink(g, w)
    if w.target and (w.target not in g.walkers or g.walkers[w.target].anim == "die"
                     or getattr(g.walkers[w.target], "hidden", False)):
        w.target = 0
    if w.act not in (0x13, 4) and 0 < hp_pct(w) < 16:
        return_to_wharf(g, w)
    if b.employees < 1:
        if w.act not in (0x18, 4, 0x1C, 0x1D, 0xC, 0xD, 0xE):
            return_to_wharf(g, w)
            w.act = 0x1C
    elif auto_defend(g) and w.act != 0x1A and hp_pct(w) >= 100 and w.away < 0 and enemy_ships(g):
        go_hunt(g, w)
    a, sp = w.act, col(g, w, "speed")
    if a == 6:                                    # at the dock (0x4D0C60): after 50 ticks hold in front of the wharf
        _fire_hold(g, w, keep=False)
        if g.tick - w.timer > 49:
            w.timer = g.tick
            if auto_defend(g):
                go_hunt(g, w)
            else:
                w.act, w.dest, w.next_act = 0x19, dock(g, w) or (w.x, w.y), 0x14
        return walkers.schedule(g, w, 10)
    if a == 0x19:                                 # ordered sail (0x4D1E70)
        if sail(g, w, w.dest, sp) == 8:
            w.act = getattr(w, "next_act", 0x14) or 0x14
            w.dest = (w.x, w.y)
            return walkers.schedule(g, w, 1)
        return
    if a == 0x14:                                 # hold (0x4D22E0 + 0x4D2550)
        _fire_hold(g, w, keep=True)
        return walkers.schedule(g, w, 6)
    if a == 0x1A:                                 # hunt (0x4D1860)
        return _hunt(g, w, sp)
    if a == 0x1B:                                 # attack the ordered target (0x4D2700)
        t = g.walkers.get(w.target)
        if t is None or t.anim == "die":
            t = trireme_target(g, w, N)
            if t is None:
                w.act, w.target, w.dest = 0x14, 0, (w.x, w.y)
                return walkers.schedule(g, w, 1)
            w.target = t.id
        if dist(w, t) < col(g, w, "missile_range") and reloaded(g, w):
            fire(g, w, t, "arrow")
        if dist(w, t) < 3 or sail(g, w, w.dest, sp) != 9:
            return walkers.schedule(g, w, 6)
        return
    if a in (0x13, 0x17, 0x1C):                   # back to the wharf (0x4D23F0 / 0x4D2350)
        r = sail(g, w, w.dest or dock(g, w), sp)
        if r == 10:
            return sink(g, w)
        if r != 8:
            return
        if a == 0x1C:
            w.act = 0x1D
        elif a == 0x17:
            w.act = 0x18
            b.misc["off"] = True                  # C4 bit 1: the crew goes home (the wharf gets no workers)
        elif w.hp >= w.hpmax:
            if not auto_defend(g):
                w.act, w.dest = 0x14, (w.x, w.y)
            elif not enemy_ships(g):
                w.act = 0x18
                b.misc["off"] = True
            else:
                go_hunt(g, w)
        return walkers.schedule(g, w, 25)        # repairing: the wharf adds hull daily (navy.day)
    if a == 0x15:                                 # patrol (0x4D1F70 + 0x4D2260)
        return _patrol(g, w, b, sp)
    if a == 0x16:                                 # chase (0x4D2840)
        return _chase(g, w, sp)
    if a == 0x1D:                                 # unmanned at the wharf: repair when it has workers again
        if hp_pct(w) < 100 and b.employees > 0:
            return_to_wharf(g, w)
        return walkers.schedule(g, w, 51)
    if a == 0x18:                                 # moored, unmanned
        return walkers.schedule(g, w, 51)
    if a == 0xC:                                  # sail abroad: to the sea entry, then hidden there
        se = g.world.sea_entry
        if se is None or sail(g, w, se, sp) == 8:
            w.act, w.hidden = 0xD, True
            return walkers.schedule(g, w, 1)
        return
    if a == 0xE:                                  # home from abroad
        r = sail(g, w, w.dest or dock(g, w), sp)
        if r == 8:
            w.act, w.timer = 6, g.tick
            return walkers.schedule(g, w, 1)
        if r == 10:
            return sink(g, w)
        return
    w.act = 0x14                                  # unknown (old saves: "moored")
    walkers.schedule(g, w, 1)


def _fire_hold(g, w, keep):
    """0x4D24D0 / 0x4D2550: fire at trireme_target(col6) when reloaded."""
    if not reloaded(g, w):
        return
    rng = col(g, w, "missile_range")
    t = g.walkers.get(w.target) if keep and w.target else None
    if t is None or t.anim == "die" or g.tick >= getattr(w, "retarget", 0):
        t = trireme_target(g, w, rng)
        w.retarget = g.tick + 50
    if t is not None and dist(w, t) < rng and col(g, w, "attack") > 0:
        w.target = t.id
        fire(g, w, t, "arrow")
    else:
        w.target = 0


def _hunt(g, w, sp):
    t = g.walkers.get(w.target) if w.target else None
    if t is None or g.tick >= getattr(w, "retarget", 0):
        t = trireme_target(g, w, N)
        w.retarget = g.tick + 50
        w.target = t.id if t else 0
        w.path = []
    if t is None:
        return walkers.schedule(g, w, 25)
    if dist(w, t) < col(g, w, "missile_range") and reloaded(g, w) and col(g, w, "attack") > 0:
        fire(g, w, t, "arrow")
    if dist(w, t) < 3:
        return walkers.schedule(g, w, 6)
    if sail(g, w, (t.x, t.y), sp) == 10:
        w.target = 0
        return walkers.schedule(g, w, 25)


def _waypoint(g, w, b, k):
    """Patrol waypoints (+0x15C): 1 the sea exit, 2 the wharf, 3 the sea entry (snapped to open water)."""
    t = {1: g.world.sea_exit or g.world.sea_entry, 2: dock(g, w) or (b.x, b.y), 3: g.world.sea_entry}.get(k)
    return snap_ship(g, t) if t else None


def _patrol(g, w, b, sp):
    """0x4D2260: no target -> trireme_target(col6): found -> chase it (0x16). 0x4D1F70: sail the waypoint cycle
    1 -> 2 -> 3 -> 1; sub 0 = the nearest (Manhattan) of entry (3), exit (1), wharf (2); no route -> sub 0."""
    t = trireme_target(g, w, col(g, w, "missile_range"))
    if t is not None:
        w.target, w.dest, w.act, w.path = t.id, (t.x, t.y), 0x16, []
        return walkers.schedule(g, w, 1)
    if not getattr(w, "sub", 0):
        cand = [(abs(p[0] - w.x) + abs(p[1] - w.y), k, p) for k in (3, 1, 2) for p in [_waypoint(g, w, b, k)] if p]
        if not cand:
            w.act = 0x14
            return walkers.schedule(g, w, 25)
        w.sub = min(cand)[1]
    dest = _waypoint(g, w, b, w.sub)
    r = sail(g, w, dest, sp) if dest else 10
    if r == 8:
        w.sub = {1: 2, 2: 3, 3: 1}[w.sub]
        return walkers.schedule(g, w, 1)
    if r == 10:
        w.sub = 0
        return walkers.schedule(g, w, 25)


def _chase(g, w, sp):
    """0x4D2840: the target gone -> patrol (sub 0); in range -> fire; within 4 or col6 - 2 -> stop, else follow."""
    t = g.walkers.get(w.target)
    if t is None or t.anim == "die" or getattr(t, "hidden", False):
        w.act, w.sub, w.target, w.path = 0x15, 0, 0, []
        return walkers.schedule(g, w, 1)
    rng = col(g, w, "missile_range")
    d = dist(w, t)
    if d < rng and reloaded(g, w) and col(g, w, "attack") > 0:
        fire(g, w, t, "arrow")
    if d < 4 or d <= rng - 2:
        w.path = []
        return walkers.schedule(g, w, 6)
    if sail(g, w, (t.x, t.y), sp) == 10:
        w.act, w.sub, w.target = 0x15, 0, 0
        return walkers.schedule(g, w, 25)


def panel_order(g, w, k):
    """The trireme panel's buttons (handler 0x00406400, disassembly; guards: not with auto-defend for 1..5, a
    ship back for repairs under 16 % takes none, a ship abroad none): 1 repair (return_to_wharf 0x4D0800); 2 crew
    (0x17 -> 0x14, 0x18 -> 0x14 and the wharf's crew back, else back to the wharf and 0x17); 3 defend (0x14 here,
    0x4D1E00); 4 attack all (0x1A, or back to 0x14 when already); 5 patrol (0x15 with sub 0 and no target, or back
    to 0x14 when already patrolling)."""
    init(g, w)
    if k and auto_defend(g):
        return "auto-defend is on: the navy takes no orders"
    if w.away >= 0 or (k and w.act == 0x13 and hp_pct(w) <= 15):
        return "that trireme can't take orders now"
    b = wharf(g, w)
    hold = lambda: (setattr(w, "act", 0x14), setattr(w, "dest", (w.x, w.y)), setattr(w, "path", []))
    if k == 1:
        return_to_wharf(g, w)
    elif k == 2:
        if w.act == 0x17:
            hold()
        elif w.act == 0x18:
            hold()
            if b is not None:
                b.misc.pop("off", None)
        else:
            return_to_wharf(g, w)
            w.act = 0x17
    elif k == 3:
        hold()
    elif k == 4:
        hold() if w.act == 0x1A else go_hunt(g, w)
    elif k == 5:
        if w.act == 0x15:
            hold()
        else:
            w.act, w.sub, w.target, w.path = 0x15, 0, 0, []
    walkers.schedule(g, w, 1)
    return None


def label(g, b):
    """0x591680: the advisor's text 51:N for a wharf's trireme (None: no label) and whether it is clickable."""
    tri = next((w for w in g.walkers.values() if w.role == "trireme" and getattr(w, "home", 0) == b.id), None)
    if tri is None:
        return None, False
    a = getattr(tri, "act", 0x18)
    if a in (6, 0xF, 0x14, 0x1A, 0x1D):
        return ANCHORED, True
    if a in (7, 0xE, 0x15, 0x19):
        return SAILING, True
    if a == 0x17:
        return DISEMBARKING, True
    if a == 0x13:
        return (REPAIRING if (tri.x, tri.y) == tuple(tri.dest or ()) else RETURNING), False
    if a == 0x1C:
        return RETURNING, False
    if a == 0x18:
        return UNMANNED, True
    if a == 0x1B:
        return FIGHTING, True
    if a in (0xC, 0xD):
        return ABROAD, False
    return None, False


def hull_text(w):
    """0x591C30: 51:49 undamaged, 50 leaky, 51 damaged, 52 mangled, 53 barely afloat."""
    p = hp_pct(w)
    return 53 if p < 26 else 52 if p < 50 else 51 if p < 75 else 50 if p < 100 else 49


def triremes(g):
    return sorted((w for w in g.walkers.values() if w.role == "trireme"), key=lambda w: w.id)


def order(g, w, x, y):
    """The order click 0x4093E0: an enemy on the tile -> attack it (0x1B); else sail there (0x19 -> hold)."""
    init(g, w)
    b = wharf(g, w)
    if auto_defend(g):
        return "auto-defend is on: the navy takes no orders"
    if w.act == 0x18 or (w.act == 0x13 and hp_pct(w) <= 15) or crew(g, w) < 50:
        return "that trireme can't take orders now (unmanned, repairing or under 50 % crew)"
    from . import contact
    t = next((f for f in contact.at(g, (x, y)) if f.role in ("enemy_infantry", "enemy_archer", "enemy_cavalry",
                                                              "enemy_warship", "enemy_transport", "wolf")
              and f.anim != "die"), None)
    if t is not None:
        w.act, w.target, w.dest = 0x1B, t.id, (t.x, t.y)
    else:
        d = water_line_point(g, (w.x, w.y), (x, y))
        if d is None:
            return f"({x},{y}) is not open water"
        w.next_act = 0x14 if getattr(w, "next_act", 0x14) != 0x1A else 0x1A
        w.act, w.dest, w.path = 0x19, d, []
    del b
    walkers.schedule(g, w, 1)
    return None


def water_line_point(g, a, b):
    """0x409640: along the line a -> b, the farthest tile whose own and N/S/E/W tiles are water and that ships can
    be on (grid_ship != 0xFF; the exe also wants it reached by the ship's route field: not checked)."""
    from .defences import line
    best = None
    for t in [a] + line(a, b):
        if walkers.ship_ok(g, *t) and all(
                g.world.flags[t[1] + dy, t[0] + dx] & 0x4 for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1))):
            best = t
    return best


def crew_home(g, w):
    """Advisor navy row (0x591400): anchored/sailing/fighting -> back to the wharf and the crew goes home (0x17);
    unmanned (0x17/0x18) -> the crew comes back aboard (0x14, the wharf's C4 bit cleared)."""
    init(g, w)
    b = wharf(g, w)
    if b is None:
        return
    if w.act in (6, 7, 0xE, 0xF, 0x14, 0x15, 0x19, 0x1B, 0x1D):
        return_to_wharf(g, w)
        w.act = 0x17
    elif w.act in (0x17, 0x18):
        w.act, w.dest = 0x14, (w.x, w.y)
        b.misc.pop("off", None)
    walkers.schedule(g, w, 1)


def crew_all_toggle(g):
    """wm_sub_40A380, the Military page's "crew all" / "stand down" button: flips 0x00FEAF20 (off at a new game).
    On: every working wharf's C4 bit 1 (crew home) is cleared and its trireme, if at home (figure +0x02 == 0: ours
    w.away < 0), returns to the wharf (0x4D0800). Off (stand down): every such trireme returns to its wharf with
    action 0x17 (the crew goes home; it sets the C4 bit there). bugs.md 329."""
    from ..systems import index
    st = state(g)
    st["crew_all"] = not st.get("crew_all")
    for b in index.keyed(g, "trireme_wharf"):
        if getattr(b, "under_construction", False):
            continue
        if st["crew_all"]:
            b.misc.pop("off", None)
        t = wharf_trireme(g, b)
        if t is None:
            continue
        init(g, t)
        if t.away >= 0:
            continue
        return_to_wharf(g, t)
        if not st["crew_all"]:
            t.act = 0x17
        walkers.schedule(g, t, 1)
    return st["crew_all"]


def crew_all_label(g):
    """FUN_0051AE00: the button's label 51:n: no wharf 83 'no ships'; flag off 5 'crew all'; on: 3 'crewing all'
    while a working wharf is under construction or below full staff, else 4 'all crewed'. Balloon (FUN_004F5DE0,
    hover 0x5DD): no wharf 38, else 173 off / 172 on."""
    from ..systems import index, labor
    ws = list(index.keyed(g, "trireme_wharf"))
    if not ws:
        return 83
    if not state(g).get("crew_all"):
        return 5
    short = any(getattr(b, "under_construction", False) or labor.staffing(g, b) < 100 for b in ws)
    return 3 if short else 4


def has_palace(g):
    from ..systems import index
    return next(iter(index.keyed(g, "palace")), None) is not None


def wharf_trireme(g, b):
    """The wharf's trireme (Building +0xB8), None without one."""
    return next((w for w in triremes(g) if getattr(w, "home", None) == b.id), None)


def wharf_window(g, b):
    """The wharf's info window (FUN_00583C60; docs/play/info.md "Trireme wharf"), presentation only: palace
    (g_palace_exists: 175:18 when missing), trireme (+0xB8: the staff button and 175:17 only without one),
    at_wharf (+0xB6, the trireme on the wharf's water-exit tile: 175:14), status (+0xBA & 0xF000: "build" 0x1000,
    building a trireme from 200 wood + 200 armor; "repair" 0x2000: 175:16), progress % (+0x54 * 100 / 320),
    crew_all (0x00FEAF20, the Military page's "crew all" toggle, crew_all_toggle)."""
    t = wharf_trireme(g, b)
    ok = has_palace(g) and b.access is not None
    st = ""
    if ok and t is not None and getattr(t, "act", None) == 0x13 and (t.x, t.y) == tuple(dock(g, t) or ()):
        st = "repair"
    elif ok and t is None and (b.progress > 0 or (b.goods.get("wood", 0) >= 200 and b.goods.get("armor", 0) >= 200)):
        st = "build"
    return dict(palace=has_palace(g), trireme=t is not None,
                at_wharf=t is not None and (t.x, t.y) == tuple(dock(g, t) or ()),
                status=st, progress=b.progress * 100 // 320, crew_all=bool(state(g).get("crew_all")))


def wharf_day(g):
    """buildings_spawn_walkers 0x48CFB0 case 0x88, repair (status 0x2039): a trireme in 0x13 on the wharf's water
    exit gains hull at the staffing rate (10/8/6/4/2) a day; full -> action 6."""
    from ..systems import labor
    for w in triremes(g):
        if getattr(w, "act", None) is None:       # just launched (economy.py) or an old save's moored trireme
            init(g, w)
            walkers.schedule(g, w, 1)
        b = wharf(g, w)
        if b is None or w.act != 0x13 or (w.x, w.y) != tuple(dock(g, w) or ()):
            continue
        if b.access is None or not has_palace(g):  # case 0x88 runs only with a palace and road access
            continue
        p = labor.staffing(g, b)
        rate = 10 if p >= 100 else 8 if p >= 75 else 6 if p >= 50 else 4 if p >= 25 else 2 if p >= 1 else 0
        w.hp = min(w.hpmax, w.hp + rate)
        if w.hp >= w.hpmax:
            w.act, w.timer = 6, g.tick
            walkers.schedule(g, w, 1)


# --- expeditions (0x4DEB30 / 0x4DEE60 / 0x4DF120) ----------------------------------------------------------

def send(g, ev_id, ids):
    for w in triremes(g):
        if w.id in ids and w.away < 0 and w.anim != "die":
            init(g, w)
            w.away, w.act, w.path = ev_id, 0xC, []
            walkers.schedule(g, w, 1)


def casualties(g, ev_id, pct):
    """0x4DF120: tier by pct; in index order a ship sinks while fewer than n*pct/100 sank or its hull <= tier."""
    tier = 200 if pct >= 80 else 150 if pct >= 60 else 100 if pct >= 40 else 50 if pct >= 20 else 0
    mine = [w for w in triremes(g) if getattr(w, "away", -1) == ev_id and w.anim != "die"]
    want, sunk = len(mine) * pct // 100, 0
    for w in mine:
        if sunk < want or w.hp <= tier:
            w.hp, w.away = 0, -1
            w.hidden = False
            sink(g, w)
            sunk += 1
        else:
            w.hp -= tier


def come_home(g, ev_id):
    for w in triremes(g):
        if getattr(w, "away", -1) == ev_id and w.anim != "die":
            w.away, w.hidden = -1, False
            w.dest, w.path = dock(g, w), []
            if 0 < hp_pct(w) < 100:
                return_to_wharf(g, w)
            else:
                w.act = 0xE
            walkers.schedule(g, w, 1)


def away_ids(g, ev_id):
    return [w.id for w in triremes(g) if getattr(w, "away", -1) == ev_id]


# --- enemy ships (invasion_spawn_sea 0x503FD0) --------------------------------------------------------------

def sea_points(g):
    """The map's sea invasion points (slots 8..15 of g_invasion_points 0x00902C10/30) and landing points (3,
    g_landing_points 0x00902E20/2C), raw (World.points)."""
    return g.world.points["sea_invasion"], g.world.points["landing"]


def has_sea_invasions(g):
    pts, lands = sea_points(g)
    return any(pts) and g.world.sea_entry is not None


def snap_ship(g, t, taken=None):
    """0x461C20: the tile if it is open water (grid_ship signed >= 0: 0, not the 0xFB shore band or the 0xFE edge)
    with no figure on it, else the first such tile in square rings around it, each ring scanned as the exe: top row
    (x - r .. x + r), bottom row, left column (y - r .. y + r), right column. taken: tiles with a figure (None:
    figures not checked)."""
    sg = walkers.ship_grid(g)
    n = sg.shape[0]

    def ok(x, y):
        return 0 <= x < n and 0 <= y < n and sg[y, x] == 0 and (taken is None or (x, y) not in taken)
    if ok(t[0], t[1]):
        return tuple(t)
    for r in range(1, 0xE4):
        x0, x1, y0, y1 = t[0] - r, t[0] + r, t[1] - r, t[1] + r
        ring = [(x, y0) for x in range(x0, x1 + 1)] + [(x, y1) for x in range(x0, x1 + 1)]
        ring += [(x0, y) for y in range(y0, y1 + 1)] + [(x1, y) for y in range(y0, y1 + 1)]
        for x, y in ring:
            if ok(x, y):
                return (x, y)
    return tuple(t)


def invade_sea(g, inv_id, nation, strength, pt, landing=0, ships=None):
    """invasion_spawn_sea 0x503FD0: warships (ships = the event's +0x36; None: strength / 4, the scratch event's
    rule (record 0x8C); none for nation 8) and transports of up to 8 soldiers per class (missile, infantry, cavalry),
    each on the free water tile nearest the sea point (0x461C20), with staggered timers (warships 25i + 10, hidden
    until then; transports 40k + 10, waiting visible). Checked against oracle run 1B-inv-sea (10-30)."""
    from .invaders import invasions
    pts, lands = sea_points(g)
    i = max(0, pt - 9) if pt >= 9 else 0
    p = next((pts[(i + k) % 8] for k in range(8) if pts[(i + k) % 8] is not None), None)
    if p is None:
        return False
    taken = {(f.x, f.y) for f in g.walkers.values()}     # DAT_00D0D878: a figure on the tile
    land = lands[landing] if 0 <= landing < 3 and lands[landing] else next((x for x in lands if x), None)
    inv = invasions(g)[inv_id]
    inv["sea"] = True
    d = units.data()["difficulty"][g.rules.get("difficulty", "Normal")]
    rows = d["armies"][max(0, min(10, nation))]
    s = min(strength, 256)
    nwar = 0 if nation == 8 else s // 4 if ships is None else ships
    st = state(g)
    st["months_since_enemy"] = 0
    for k in range(nwar):
        at = snap_ship(g, p, taken)                     # each ship on its own free tile by the point
        taken.add(at)
        w = units.spawn(g, "enemy_warship", at[0], at[1], delay=25 * k + 10, act=6, hidden=True, army=0,
                        nation=nation, good=f"army{nation}", inv=inv_id, month0=g.month, hp=d["armies"][0]["warship"]["hp"],
                        hpmax=d["armies"][0]["warship"]["hp"], target=0, next_shot=0, face=(0, 1), timer=0,
                        rr0=walkers.now(g) - 1)    # 0x004D4790: +0x92 + 1 every update from the creation tick's
                                                   # pass (also while it waits), the route freed at the 100th
        w.patrol = 0
    k = 0
    for cls in ("missile", "infantry", "cavalry"):
        n = rows[cls]["frequency"] * s // 100
        while n > 0:
            m = min(8, n)
            n -= m
            at = snap_ship(g, p, taken)
            taken.add(at)
            # visible while it waits: its action 6 (0x004D29D0) clears +0x65 on every update
            w = units.spawn(g, "enemy_transport", at[0], at[1], delay=40 * k + 10, act=6, hidden=False, army=0,
                            nation=nation, inv=inv_id, loaded=True, payload=(cls, m), landing=land,
                            hp=d["armies"][0]["transport"]["hp"], hpmax=d["armies"][0]["transport"]["hp"],
                            target=0, face=(0, 1), timer=0, rr0=walkers.now(g) - 1)
            k += 1
    return True


def warship_target(g, w, thr):
    """0x4E1800: soldiers 100 within col6, trade ships and fishing boats 10, triremes 500 (1000 when it targets a
    transport) - 10 per warship already on it; bestW - bestD < w - d; line of fire."""
    from .defences import line_of_fire
    best, bw, bd = None, 0, thr
    rng = units.col(g, w, "missile_range")
    cand = list(figures(g, ("rabble", "hoplite", "horseman", "trireme")))
    cand += [f for f in g.walkers.values() if f.role in ("ship", "boat") and f.anim != "die"]
    for f in sorted(cand, key=lambda f: f.id):
        if getattr(f, "away", -1) is not None and getattr(f, "away", -1) >= 0 and f.role == "trireme":
            continue
        d = dist(w, f)
        if f.role == "trireme":
            tt = g.walkers.get(getattr(f, "target", 0))
            k = (1000 if tt is not None and tt.role == "enemy_transport" else 500) - 10 * getattr(f, "hunted", 0)
        elif f.role in ("ship", "boat"):
            k = 10
        elif d <= rng:
            k = 100
        else:
            continue
        if bw - bd < k - d and line_of_fire(g, (w.x, w.y), (f.x, f.y)):
            best, bw, bd = f, k, d
    return best


SOLDIERS = ("rabble", "hoplite", "horseman")       # figure types 0xB, 0xC, 0xD


def _release(g, t):
    """0x4D3F60: the target's +0x68 (warships on it) - 1, not below 0."""
    if t is not None:
        t.hunted = max(0, getattr(t, "hunted", 0) - 1)


def _warship_fire(g, w):
    """0x4D47D0 (actions 6, 7, 9, 10, 0xE): reload (+0x6B) + 1; past col7 it is 0 and warship_target(F, col6) picks:
    attack_timer (+0x6A) 1 and the warship faces it, else 0. attack_timer 1: a 0x34 missile at the pick's tile, the
    old target released, target (+0x82) = the pick, its +0x68 + 1. attack_timer + 1, past 100 -> 0."""
    w.reload = getattr(w, "reload", 0) + 1
    t = None
    if w.reload > units.col(g, w, "missile_rate"):
        w.reload = 0
        t = warship_target(g, w, units.col(g, w, "missile_range"))
        w.atk = 1 if t is not None else 0
    atk = getattr(w, "atk", 0)
    if atk:
        if atk == 1 and t is not None:
            fire(g, w, t, "enemy_arrow")
            _release(g, g.walkers.get(w.target))
            w.target = t.id
            t.hunted = getattr(t, "hunted", 0) + 1
        w.atk = 0 if atk + 1 > 100 else atk + 1


def ships_near(g, w, size=18):
    """0x4D0A10(F, 18, 1): the nearest (squared distance, the first of equals in the scan) of the figures found in
    the box x - 9 .. x + 8, y - 9 .. y + 8 (rows, then x) by 0x4D0D90: on each tile, the first figure of its list
    (not F) that is a trireme 0x39 or a fishing boat 0x19."""
    from . import contact
    best, bd = None, 500000
    x0, y0 = w.x - size // 2, w.y - size // 2
    for y in range(y0, y0 + size):
        for x in range(x0, x0 + size):
            for f in contact.at(g, (x, y)):
                if f is w:
                    continue
                if f.role in ("trireme", "boat"):
                    d = (f.x - w.x) ** 2 + (f.y - w.y) ** 2
                    if d < bd:
                        best, bd = f, d
                    break
    return best


# 0x4D3DA0's switch on direction_to(threat -> warship) 0x0058CFF0: three (dx, dy) offsets for 0x4D0910 (7 and 8: the
# default case)
FLEE_OFF = {0: ((0, -10), (10, -10), (-10, -10)), 1: ((0, -10), (10, -10), (10, 0)),
            2: ((10, -10), (10, 0), (10, 10)), 3: ((10, 0), (10, 10), (0, 10)), 4: ((10, 10), (0, 10), (-10, 10)),
            5: ((0, 10), (-10, 0), (-10, 10)), 6: ((-10, 0), (-10, 10), (-10, -10)),
            7: ((-10, 0), (-10, -10), (0, -10)), 8: ((-10, 0), (-10, -10), (0, -10))}


def flee_point(g, w, threat):
    """0x4D0910: for each offset water_line_point(warship, warship + offset) (0x409640: the farthest fit tile by
    squared distance, the start itself at 0 when none), a later candidate wins ties; the result snapped
    (0x461C20)."""
    from ..roaddrag import direction_to
    best, bd = (w.x, w.y), -1
    for dx, dy in FLEE_OFF[direction_to(threat.x, threat.y, w.x, w.y)]:
        p = water_line_point(g, (w.x, w.y), (w.x + dx, w.y + dy)) or (w.x, w.y)
        dd = (p[0] - w.x) ** 2 + (p[1] - w.y) ** 2
        if dd >= bd:
            best, bd = p, dd
    return snap_ship(g, best)


def hunt_due(g, w):
    """0x4D4500: one RNG step every patrol update (31 LFSR steps); the hunt starts when rng_15 % 30 + 75 <= timer.
    Ours draws its own numbers (tools/oracle_warships.py replays the exe's trigger ticks here)."""
    return mrng(g).randrange(30) + 75 <= w.timer


def _patrol_leg(g, w, se, sx, lands):
    """0x4D4500 on direction 8: L = the first valid landing point, snapped (0x4D44B0); at the sea entry -> L (none:
    the sea exit); at L -> the sea exit; elsewhere -> the sea entry."""
    land = next((snap_ship(g, x) for x in lands if x), None)
    here = (w.x, w.y)
    if here == tuple(se):
        w.patrol = land or sx
    elif land is not None and here == land:
        w.patrol = sx
    else:
        w.patrol = se


def warship_act(g, w):
    """fig_handler_enemy_warship 0x004C2980, every tick (navy.md "Warship 0x40"). w.act = +0x38, w.sub = +0x15C,
    w.timer = +0x36 (a counter), w.reload / w.atk = +0x6B / +0x6A, w.target = +0x82, w.patrol / w.dest = +0x24."""
    if w.anim == "die":
        return units.act_dying(g, w)
    walkers.schedule(g, w, 1)
    sp = units.col(g, w, "speed")
    pts, lands = sea_points(g)
    se, sx = g.world.sea_entry, g.world.sea_exit or g.world.sea_entry
    if w.act not in (4, 5):
        p = hp_pct(w)
        if 0 < p < 16:
            w.act, w.sub = 10, 0xD
        if (w.month0 + 4) % 12 == g.month:
            w.act, w.path, w.route = 0xF, [], None
    if not isinstance(getattr(w, "timer", 0), int) or w.timer > 10 ** 6:
        w.timer = 0                                 # saves before 11-02 kept a tick stamp here
    a = w.act
    if a == 5:
        return
    if a == 6:                                      # 0x4D3B70 (ours: the spawn delay was its timer)
        w.hidden = False
        w.act, w.patrol, w.timer, w.route, w.path = 0xE, se, 0, None, []
        return _warship_fire(g, w)
    if a == 7:                                      # 0x4D3C40 + fire
        _sail_target(g, w, sp)
        return _warship_fire(g, w)
    if a == 8:
        return _hunt(g, w, sp)
    if a == 9:                                      # 0x4D3BF0 (no writer found) + fire
        w.hidden = False
        if w.dest is not None:
            sail_fine(g, w, tuple(w.dest), sp)
        return _warship_fire(g, w)
    if a == 10:                                     # 0x4D3DA0 + fire
        _flee(g, w, sp)
        return _warship_fire(g, w)
    if a == 0xE:                                    # patrol 0x4D4500: charge_move(F, 0), one RNG step, timer + 1
        r = sail_fine(g, w, snap_ship(g, w.patrol or se), sp)
        w.timer += 1
        if hunt_due(g, w):
            w.timer, w.act, w.sub = 0, 8, 0xD
        if r == 8:                                  # arrived: the next leg; the action is 0xE again
            _patrol_leg(g, w, se, sx, lands)
            w.act = 0xE
        return _warship_fire(g, w)
    if a == 0xF:                                    # 0x4D4730: 8 or 10 -> gone
        if sx is None or sail_fine(g, w, sx, sp) in (8, 10):
            return units.remove(g, w)
        return
    w.act = 0xE


def _sail_target(g, w, sp):
    """0x4D3C40: charge_move(F, 1) (warship col10 0: its plain speed); a target within 2 tiles: dest = its own tile,
    route freed, no move; direction 8 -> action 8, sub 0xD; 10 (no route) -> action 4 (it sinks). Returns the
    direction (or None when it stayed)."""
    t = g.walkers.get(w.target) if w.target else None
    if t is not None and dist(w, t) < 3:
        w.dest, w.route, w.path = (w.x, w.y), None, []
        return None
    if w.dest is None:
        return None
    r = sail_fine(g, w, tuple(w.dest), sp)
    if r == 8:
        w.act, w.sub = 8, 0xD
    elif r == 10:
        sink(g, w)
    return r


def _hunt(g, w, sp):
    """0x4D3F90 (action 8), r = col6. A target not alive: sub 0xD, target 0. Sub 0xD: the target, or
    warship_target(F, 228); at r or farther: released and picked again (228); none -> 0xE. A soldier or trireme
    target: one RNG step, odd -> +0x80 = (month + 1) % 12 (leaves a month later). Soldier: dest = its own tile
    (shoots from here); ship: dest = its tile unless within 2. Sub 7, the old target released, target = t, its
    +0x68 + 1, route freed. Sub 7: within r: reload + 1, past col7 -> 0 and attack_timer 1; attack_timer 1 fires a
    0x34 (+1, wraps past 100). A soldier target: no move (out of range: timer + 1); else 0x4D3C40. Then direction 8
    or timer > 24: timer 0, sub 0xD, route freed."""
    rng_ = units.col(g, w, "missile_range")
    t = g.walkers.get(w.target) if w.target else None
    if w.target and (t is None or t.anim == "die"):
        w.sub, w.target = 0xD, 0
        return
    if getattr(w, "sub", 0xD) != 7:
        if t is None:
            t = warship_target(g, w, N)
        elif dist(w, t) >= rng_:
            _release(g, t)
            t = warship_target(g, w, N)
        if t is None:
            w.act = 0xE
            return
        if t.role in SOLDIERS + ("trireme",) and mrng(g).randrange(2):
            w.month0 = (g.month + 1) % 12
        if t.role in SOLDIERS:
            w.dest = (w.x, w.y)
        elif dist(w, t) >= 3:
            w.dest = (t.x, t.y)
        w.sub = 7
        _release(g, g.walkers.get(w.target))
        w.target = t.id
        t.hunted = getattr(t, "hunted", 0) + 1
        w.route, w.path = None, []
        return
    inr = dist(w, t) < rng_
    if inr:
        w.reload = getattr(w, "reload", 0) + 1
        if w.reload > units.col(g, w, "missile_rate"):
            w.reload, w.atk = 0, 1
    atk = getattr(w, "atk", 0)
    if atk:
        if atk == 1:
            fire(g, w, t, "enemy_arrow")
        w.atk = 0 if atk + 1 > 100 else atk + 1
    r = None
    if t.role in SOLDIERS:
        if not inr:
            w.timer += 1
    else:
        r = _sail_target(g, w, sp)
        if w.id not in g.walkers or w.anim == "die":
            return
    if r == 8 or w.timer > 24:
        w.timer, w.sub, w.route, w.path = 0, 0xD, None, []


def _flee(g, w, sp):
    """0x4D3DA0 (action 10): sub 9 sails to its dest, 8 -> sub 0xD; sub 0xD: timer + 1 up to 75, then 0 and
    ships_near(F, 18, 1): none -> action 0xE, found -> flee_point, route freed, sub 9. The pre-switch sets sub 0xD
    every tick while the hull is below 16 %, so a damaged warship stays (literal reading, navy.md)."""
    if getattr(w, "sub", 0xD) == 9:
        w.hidden = False
        if w.dest is not None and sail_fine(g, w, tuple(w.dest), sp) == 8:
            w.sub = 0xD
        return
    if w.sub != 0xD:
        return
    w.timer += 1
    if w.timer < 75:
        return
    w.timer = 0
    t = ships_near(g, w)
    if t is None:
        w.act = 0xE
        return
    w.dest = flee_point(g, w, t)
    w.route, w.path, w.sub = None, [], 9


def transport_act(g, w):
    if w.anim == "die":
        return units.act_dying(g, w)
    sp = units.col(g, w, "speed")
    sx = g.world.sea_exit or g.world.sea_entry
    if w.act == 6:                                  # hidden until its timer, then to the landing point / the sea exit
        w.hidden = False
        if w.loaded and w.landing is not None:
            w.act = 0xB
        else:
            w.act = 0xE
        return walkers.schedule(g, w, 1)
    if w.act == 0xB:
        dest = _landing_water(g, w.landing)
        r = sail_fine(g, w, dest, sp)
        if r == 10:
            return sink(g, w)
        if r == 8:
            return unload(g, w)
        return
    if w.act == 0xE:
        if sx is None or sail_fine(g, w, sx, sp) != 9:
            return units.remove(g, w)
        return
    w.act = 0xE
    walkers.schedule(g, w, 1)


def _landing_water(g, land):
    """The transport's destination: the landing point itself (0x503FD0 stores landing_points[ev+0x78] as is; the
    maps put it on water ships can reach). Ours, not the exe: a landing point ships can't be on (grid_ship 0xFF,
    where the exe's route would fail and the transport die) is snapped to the nearest open water."""
    if walkers.ship_ok(g, *land):
        return tuple(land)
    from . import contact
    c = contact.cache(g).setdefault("landing_water", {})
    if land not in c:
        c[land] = snap_ship(g, land)
    return c[land]


def unload(g, w):
    """0x4D2B10: break the building on the landing tile, unload the soldiers as land companies
    (enemy_army_spawn_land), message 0xDD "disembarked" once per invasion; then sail out."""
    from .invaders import invasions, land_companies
    from ..systems import index
    land = w.landing
    occ = int(g.world.occ[land[1], land[0]])
    if occ:
        b = g.buildings.get(occ)
        if b is not None:
            from .invaders import destroy
            destroy(g, land[0], land[1], w)
    inv = invasions(g).get(w.inv)
    cls, n = w.payload
    tile = _land_tile(g, land)
    # 0x004D3740 on arrival: route_tile_check found no land tile (its tile still has terrain 0x300203, or water
    # without a road) -> action 6 with timer 50; else the timer is the spent wait's 0. FUN_004D2B10 unloads and
    # sets action 6; its next update (0x004D29D0) turns to 0xE (dest the sea exit) once the timer is < 1, and
    # figure_move starts the update after that.
    bad = not walkers.walkable(g)[tile[1] * N + tile[0]]
    if inv is not None:
        land_companies(g, w.inv, inv, {cls: n}, tile)
        if not inv.get("disembarked"):
            inv["disembarked"] = True
            from .. import alerts                       # 0x461AB0: message 0xDD 0x2DC with alert 9 at the transport
            alerts.raise_alert(g, alerts.INVASION, (w.x, w.y))
            if inv.get("sev") is not None:              # a scenario invasion: the record's message (+0x57 bit 0x40)
                from ..empire import invasion_events
                invasion_events.disembarked(g, inv["sev"])
            else:
                g.message(f"The army from {inv['name']} has disembarked at ({tile[0]},{tile[1]})!")
    del index
    w.loaded, w.act = False, 0xE
    walkers.schedule(g, w, 51 if bad else 2)


def _land_tile(g, land):
    """route_tile_check 0x4D2C60 on the landing point: the nearest walkable land tile."""
    ok = walkers.walkable(g)
    for r in range(0, 20):
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                if max(abs(dx), abs(dy)) != r:
                    continue
                x, y = land[0] + dx, land[1] + dy
                if 0 <= x < N and 0 <= y < N and ok[y * N + x]:
                    return (x, y)
    return tuple(land)


def act(g, w):
    if w.anim == "fight":                          # action 5 (a monster's melee, figure_tile_contact): the ship
        return walkers.schedule(g, w, 10 ** 6)     # handlers' case 5 does nothing; it waits to sink or be woken
    if w.role == "trireme":
        return trireme_act(g, w)
    if w.role == "enemy_warship":
        return warship_act(g, w)
    return transport_act(g, w)


def day(g):
    wharf_day(g)


def look(g, w):
    """Play mode: ships draw with their walk group while moving, the idle picture standing, a shot frame."""
    if getattr(w, "hidden", False):
        return ["hidden", 0, 0, 0, 0, 0, 0, 0, "", False]
    if w.anim:
        return None
    f = w.face or (0, 1)
    if w.path:
        return None
    st = getattr(w, "shot_t0", None)
    if w.role != "enemy_transport" and st is not None and g.tick < st + 12:
        return ["work", st, st + 12, f[0], f[1], 0, 0, 0, "shoot", False]
    # the trireme handler's tail (zeus.c ~128060): standing, the crew picture (+0x150) only while the wharf's C4 bit 1
    # (crew home, ours misc "off") is clear, whatever the action (oracle 1B-trireme: 0x1D with the bit set, no crew)
    b = wharf(g, w) if w.role == "trireme" else None
    crewed = not (b is not None and b.misc.get("off"))
    return ["work", 0, g.tick + 10 ** 6, f[0], f[1], 0, 0, 0, "idle" if crewed else "idle_empty", False]
