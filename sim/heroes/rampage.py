"""A bad monster's rampage (docs/logic/heroes-monsters.md "Rampage"), every tick like the exe:

  10  on-enter monster_pick_targets 0x00531320: for each of its 3 categories (+0x115..0x117) the nearest building of
      the category (nearest_building_in_category 0x004ABBF0: state 1, Manhattan, the first of equals; sea monsters:
      water at the origin or the far corner) -- a composite piece / monument type 100..114 that is damaged (vt+0x98)
      or not attackable (vt+0x8C) is dropped, not replaced -- and the nearest figure of the category
      (nearest_figure_in_category 0x004AC020: state 1, not dying / hidden / killed, not a god or monster; on water for
      a sea monster; Manhattan, the first of equals); the first category with either ends the search (category 10:
      a random one, rng % 11, drawn by each search)
      tick 0x00531550: -1 rampage day a day; none left or no target -> (6, 7) home, else (11, 6)
  11  on-enter 0x005315C0: route freed; targets checked; no building: no figure -> (10, 11), else dest = its tile;
      a building: dest = its first tile in ring order (FUN_004D2F10; a sea monster: the nearest sailable tile
      FUN_00461ED0)
      tick 0x005318B0 (below, `tick11`): walk_then(speed, lost 10) in route mode 3 (2 = bashing once flag 0x100 is
      set by a lost route; cleared by the re-target every 50 ticks); a ranged monster at Chebyshev 2..3 of the
      building -> 28; at dest: the building -> 25 (smash), a figure -> contact with the 8 neighbours / its tile, 28 at
      2..3, far or mid-step -> (11, 10), else 11 again (new dest)
  25  on-enter 0x005324D0: +0x36 = 2 x the attack group's frames; tick monster_smash_building 0x00532700: the
      rampage day, +0x36 - 1, at 0 building_destroyed_by_attack on the building's tile -> (10, 11); the bash sound
      every tick
Fields: tb (+0x5E building), txy (its piece's tile for a composite), tf (+0x82 figure), rampage (+0x108), rday
(+0x104), timer (+0x36), ret (+0x34), mflags 0x100 (route mode 2) / 0x200.
"""
from . import data, hrng
from ..systems import walkers
from ..military import units

N = 228
ACTS = (10, 11, 25)


def set_action(g, w, a, ret=0):
    """figure_set_action 0x004ABAF0 + monster_on_action_enter 0x0052F750."""
    from . import monsters as M
    if a not in ACTS:
        return M.set_action(g, w, a, ret)
    M._out_of_melee(g, w)
    w.saved, w.ret, w.act = M.cur_act(w), ret, a
    if a == 10:
        return pick(g, w)
    if a == 11:
        return enter11(g, w)
    if a == 25:
        w.timer = 2 * M.frames(w.mid, 2)       # monster_anim_info(m, 0x19): the attack group
        w.anim_t0 = g.tick
        return None
    return M.set_action(g, w, a, ret)          # 0 (-> (6, 7)), 6, 7, ...


def _days(g, w):
    if getattr(w, "rday", g.day) != g.day:
        w.rampage -= 1
        w.rday = g.day


def act(g, w):
    if w.act == 10:
        _days(g, w)                             # 0x00531550
        if w.rampage < 1 or (not w.tf and not w.tb):
            set_action(g, w, 6, 7)
        else:
            set_action(g, w, 11, 6)
    elif w.act == 11:
        tick11(g, w)
    elif w.act == 25:
        tick25(g, w)
    return _next(g, w)


def _next(g, w):
    if w.id not in g.walkers or w.anim or w.act == 28:
        return None
    walkers.schedule(g, w, 1)                   # 6 / 7: their own handlers from the next tick
    sd = w.__dict__.get("step_draw")
    if sd and sd[0] == w.arrived:                # play mode: the step drawn over its sub-steps (sim/live.py)
        w.step_end = sd[1]
    return None


# --- targets ----------------------------------------------------------------------------------------------------

def _water_ok(g, b, x, y):
    """nearest_building_in_category for a sea monster: water under the origin, or under the far corner (size > 1)."""
    fl = g.world.flags
    if fl[y, x] & 4:
        return True
    s = max(1, b.size)
    return s > 1 and 0 <= x + s - 1 < N and 0 <= y + s - 1 < N and bool(fl[y + s - 1, x + s - 1] & 4)


def _type(g, b):
    if b.kind == "house":
        return 2 + b.level
    return g.cat.spec(b.key).get("zeus_id")


def records(g, b):
    """The exe's Building records of b: [(x, y, piece index or None, attackable and not damaged)]."""
    from . import monsters as M
    if b.kind != "monument":
        t = _type(g, b)
        return [(b.x, b.y, None, not (t is not None and 100 <= t <= 114))]
    from ..systems import monuments as mon
    att, col = set(data().get("piece_attack", ())), set(data().get("piece_collapse", ()))
    if b.key == "palace":
        lay = mon.layouts().get(b.key)
        return [(*mon.piece_xy(b, i), i, pc[2] in col) for i, pc in enumerate(lay["pieces"])] if lay else []
    return [(*mon.piece_xy(b, p), i, p["c"] in att and not p.get("damaged"))
            for i, p in enumerate(b.misc.get("pieces", ()))]


def nearest_building(g, w, c):
    """nearest_building_in_category 0x004ABBF0 + monster_pick_targets' composite rule. (building, tile) or None."""
    if c == 10:
        c = hrng(g).randrange(1 << 15) % 11
    tl = units.data()["targets"]
    order = set(tl[c]) if c < len(tl) else set()
    if not order:
        return None
    sea = getattr(w, "mid", 0) in (1, 10)
    best, bd = None, 1000
    for b in sorted(g.buildings.values(), key=lambda b: b.id):
        if b.kind in ("road", "ruin") or _type(g, b) not in order:
            continue
        for x, y, i, ok in records(g, b):
            if sea and not _water_ok(g, b, x, y):
                continue
            d = abs(x - w.x) + abs(y - w.y)
            if d < bd:
                best, bd = (b, (x, y), i, ok), d
    if best is None or not best[3]:              # the nearest is a damaged / unattackable piece: none
        return None
    return best


def nearest_figure(g, w, c):
    """nearest_figure_in_category 0x004AC020."""
    if c == 10:
        c = hrng(g).randrange(1 << 15) % 11
    tf = data()["target_figures"]
    roles = set(tf[c]) if c < len(tf) else set()
    if not roles:
        return None
    water = w.mid in (1, 10)
    fl = g.world.flags
    best, bd = None, 1000
    for o in sorted(g.walkers.values(), key=lambda o: (getattr(o, "fslot", 0), o.id)):
        if o.role not in roles or o.role in ("god", "monster") or not units.alive(o) or getattr(o, "hidden", False):
            continue
        if water and not fl[o.y, o.x] & 4:
            continue
        d = abs(o.x - w.x) + abs(o.y - w.y)
        if d < bd:
            best, bd = o, d
    return best


def pick(g, w):
    """monster_pick_targets 0x00531320 (on-enter 10)."""
    w.tb, w.tf, w.txy = 0, 0, None
    for c in w.cats:
        r = nearest_building(g, w, c)
        if r is not None:
            w.tb, w.txy = r[0].id, r[1]
        else:
            w.tb, w.txy = 0, None
        o = nearest_figure(g, w, c)
        w.tf = o.id if o is not None else 0
        if w.tb or w.tf:
            return None
    return None


def building_ok(g, w):
    """The target building still valid: state 1 and (plain, or the piece attackable and not damaged)."""
    b = g.buildings.get(w.tb) if w.tb else None
    if b is None or b.kind in ("ruin", "road"):
        return None
    if getattr(w, "txy", None) is not None and b.kind == "monument":
        for x, y, i, ok in records(g, b):
            if (x, y) == tuple(w.txy):
                return b if ok else None
        return None
    t = _type(g, b)
    return None if t is not None and 100 <= t <= 114 else b


def figure_ok(g, w):
    o = g.walkers.get(w.tf) if w.tf else None
    if o is None or not units.alive(o) or getattr(o, "hidden", False):
        return None
    return o


def _target_xy(w, b):
    t = getattr(w, "txy", None)
    return tuple(t) if t is not None else (b.x, b.y)


def _ring_tile(g, x, y, ok):
    """The ring search of FUN_004D2F10 / FUN_00461ED0 / FUN_00461C20: (x, y) itself, then rings 1.. (top row, bottom
    row, left column, right column, clipped to the map): the first tile with ok(x, y)."""
    if 0 <= x < N and 0 <= y < N and ok(x, y):
        return (x, y)
    for r in range(1, N):
        x0, x1, y0, y1 = max(x - r, 0), min(x + r, N - 1), max(y - r, 0), min(y + r, N - 1)
        if y - r >= 0:
            for xx in range(x0, x1 + 1):
                if ok(xx, y - r):
                    return (xx, y - r)
        if y + r < N:
            for xx in range(x0, x1 + 1):
                if ok(xx, y + r):
                    return (xx, y + r)
        if x - r >= 0:
            for yy in range(y0, y1 + 1):
                if ok(x - r, yy):
                    return (x - r, yy)
        if x + r < N:
            for yy in range(y0, y1 + 1):
                if ok(x + r, yy):
                    return (x + r, yy)
    return None


def _sailable(g):
    sg = walkers.ship_grid(g)
    return lambda x, y: sg[y, x] < 0x80 or sg[y, x] == 0xFB        # FUN_00461EB0


def building_dest(g, w, b):
    """FUN_004D2F10 (land: the first tile of the building in ring order, not water) / FUN_00461ED0 (sea)."""
    x, y = _target_xy(w, b)
    if w.mid in (1, 10):
        return _ring_tile(g, x, y, _sailable(g)) or (x, y)
    occ, fl = g.world.occ, g.world.flags
    return _ring_tile(g, x, y, lambda a, c: occ[c, a] == b.id and not fl[c, a] & 4) or (x, y)


def enter11(g, w):
    """0x005315C0."""
    free_route(w)
    b = building_ok(g, w)
    if b is None:
        w.tb, w.txy = 0, None
    o = figure_ok(g, w)
    if o is None:
        w.tf = 0
    if b is None:
        if o is None:
            return set_action(g, w, 10, 11)
        w.dest = (o.x, o.y)
        w.timer = 0
    else:
        w.dest = building_dest(g, w, b)
    w.face = _toward(w, w.dest)
    return None


def _toward(w, t):
    return ((t[0] > w.x) - (t[0] < w.x), (t[1] > w.y) - (t[1] < w.y)) or (0, 1)


def _cheb(w, x, y):
    return max(abs(x - w.x), abs(y - w.y))


# --- figure_move ------------------------------------------------------------------------------------------------

def move(g, w):
    """figure_move 0x004D1170 / figure_route_walk 0x004D7BD0 tick by tick (as guardians.move): None moving, 8 arrived,
    9 blocked (route freed), 10 no route, 11 bashing (route mode 2: at a centre the next tile is a building / wall /
    tower: it stands, wall damage on ticks with cycle_step & 3 == 0)."""
    from . import monsters as M
    from ..military import navy
    mode = M.route_mode(w)
    sea = mode == "sea"
    mode2 = mode == 2
    route = getattr(w, "route", None)
    prog = getattr(w, "prog", 15)
    n = navy.substeps(w, M.SPEED)
    if route is None:
        if (w.x, w.y) == tuple(w.dest):
            return 8
        if sea:
            p = walkers.water_path(g, (w.x, w.y), {tuple(w.dest)})
        elif mode2:
            p = M.route2(g, (w.x, w.y), tuple(w.dest))
        elif mode == 6:                         # route_bfs_shore 0x0058B560, else route_distance (+ trace8)
            from .hero_ai import water_ok
            p = walkers.route0(g, (w.x, w.y), tuple(w.dest), water_ok(g)) \
                or walkers.route0(g, (w.x, w.y), tuple(w.dest), M.passable(g))
        else:                                   # mode 3: roads first, then land (guardians.route3)
            from .guardians import route3
            p = route3(g, (w.x, w.y), tuple(w.dest))
        if p is None:
            w.route, w.path = None, []
            return 10
        route, prog = list(p), 15
    w.bashing = 0
    for _ in range(n):
        prog += 1
        if prog > 14:
            prog = 15
            if not route:
                w.route, w.path, w.prog = None, [], 15
                return 8
            nxt = route[0]
            if sea:
                blocked = walkers.ship_grid(g)[nxt[1], nxt[0]] == 0xFF
            elif mode2:
                from ..military import invaders
                o = invaders.obstacle(g, *nxt)
                if o in (1, 3, 4):              # figure_check_next_tile: direction 11, stands at the centre
                    w.route, w.prog = route, 15
                    w.path = list(route)
                    _bash(g, w, nxt, o)
                    return 11
                blocked = o is None
            elif mode == 6:
                from .hero_ai import water_ok
                blocked = not water_ok(g)[nxt[1] * N + nxt[0]]
            else:
                blocked = not M.passable(g)[nxt[1] * N + nxt[0]]
            if blocked:
                w.route, w.path, w.prog = None, [], 15
                return 9
            route = route[1:]
            w.heading = nxt
            w.face = _toward(w, nxt)
            prog = 0
        if prog == 8:
            units.step(g, w, w.heading)
            num, den = walkers.SPEED[M.SPEED]
            w.step_draw = (g.tick, g.tick + max(1, round(15 * den / max(1, num))))
            if w.anim:
                break
    w.route, w.prog = route, prog
    w.path = ([w.heading] if prog < 8 else []) + list(route)
    return None


def free_route(w):
    w.route, w.path = None, []


def _bash(g, w, nxt, o):
    """Direction 11: the bash sound every tick (0x004C8C72); wall damage on cycle_step & 3 == 0 ticks: building +1
    over 10, wall +10 over 200, tower / gatehouse +1 over 400 -> building_destroyed_by_attack 0x004928C0."""
    from . import monsters as M
    from ..military import state as mstate
    w.face = _toward(w, nxt)
    if getattr(w, "bashing", 0) != g.tick - 1:
        w.bash_t0 = g.tick                       # play mode: the fight group from here (the tail: action 5)
    w.bashing = g.tick
    walkers.sfx(g, w, "bash", g.tick + 1)
    if (g.tick % 51) & 3:
        return
    dmg = mstate(g).setdefault("wall_damage", {})
    k = f"{nxt[0]},{nxt[1]}"
    dmg[k] = dmg.get(k, 0) + (10 if o == 3 else 1)
    if dmg[k] > {1: 10, 3: 200, 4: 400}[o]:
        dmg.pop(k, None)
        M.destroy_tile(g, w, *nxt)


def walk_then(g, w, lost):
    """figure_walk_then 0x004ABB60 (the behaviour's vtable[0])."""
    d = move(g, w)
    if d == 9:
        free_route(w)
    elif d == 10:
        set_action(g, w, lost, 0)
    elif d == 8:
        set_action(g, w, getattr(w, "ret", 0) or 0, 0)
    return d


# --- 11 and 25 --------------------------------------------------------------------------------------------------

def _shoot(g, w, aim):
    from . import monsters as M
    return M.go_shoot(g, w, aim, M.cur_act(w))


def tick11(g, w):
    """FUN_005318B0."""
    from . import monsters as M
    _days(g, w)
    w.timer += 1
    b = building_ok(g, w)
    if b is None:
        w.tb, w.txy = 0, None
    if figure_ok(g, w) is None:
        w.tf = 0
    if not w.tb and not w.tf:
        free_route(w)
        return set_action(g, w, 10, 10)
    if tuple(w.dest) == (w.x, w.y):
        return _arrived(g, w)
    d = walk_then(g, w, 10)
    if w.id not in g.walkers:
        return None
    # a tile contact on the step started a melee (action 5): the handler goes on with the exe's action 5 (item 3)
    b = building_ok(g, w)
    if b is not None:
        bx, by = _target_xy(w, b)
        if M.in_range(w, bx, by):
            w.dest = (bx, by)
            return _shoot(g, w, (bx, by))
    if d == 10:
        w.mflags |= 0x100
        free_route(w)
        return None
    if w.act in (0, 10):
        set_action(g, w, 10, 10)
        if d != 8 or tuple(w.dest) != (w.x, w.y):
            return None
        return _arrived(g, w)
    if d == 8:
        return _arrived(g, w)
    if d == 9:
        if not w.tb:
            w.tf = 0
        else:
            b = g.buildings.get(w.tb)
            t = None
            if b is not None:
                if w.mid in (1, 10):
                    x, y = _target_xy(w, b)
                    sg = walkers.ship_grid(g)
                    t = _ring_tile(g, x, y, lambda a, c: sg[c, a] < 0x80 and not _anyone(g, a, c))   # FUN_00461C20
                else:
                    occ, fl = g.world.occ, g.world.flags
                    t = _ring_tile(g, w.dest[0], w.dest[1], lambda a, c: occ[c, a] == b.id and not fl[c, a] & 4)
            if t is None:
                w.tb, w.txy = 0, None
            else:
                w.dest = t
        free_route(w)
        return _end(g, w)
    if tuple(w.dest) == (w.x, w.y):
        return _arrived(g, w)
    if not w.tb and not w.tf:
        return _end(g, w)
    if w.timer > 0x32 and getattr(w, "prog", 15) in (0, 15):     # tile progress 0 or past 14
        w.mflags &= ~0x100
        enter11(g, w)
        w.timer = 0
        return _end(g, w)
    if not w.tb:
        return _end(g, w)
    if not _sailable(g)(w.x, w.y):              # FUN_00461EB0 on its tile: land (0xFF) never, so only a sea monster
        return _end(g, w)                       # smashes / shoots from here; a land one bashes its way in (mode 2)
    b = g.buildings.get(w.tb)
    bx, by = _target_xy(w, b)
    dist = _cheb(w, bx, by)
    if not M.ranged(w):
        if dist > 1:
            return _end(g, w)
        return _smash(g, w, bx, by)
    if dist < 2:
        return _smash(g, w, bx, by)
    if dist > 3:
        return _end(g, w)
    w.dest = (bx, by)
    return _shoot(g, w, (bx, by))


def _anyone(g, x, y):
    from ..military import contact
    return bool(contact.at(g, (x, y), with_helpless=True))


def _end(g, w):
    """LAB_00531D99: action 0 -> (11, 10)."""
    if w.act == 0:
        set_action(g, w, 11, 10)
    return None


def _smash(g, w, bx, by):
    set_action(g, w, 25, 25)
    w.face = _toward(w, (bx, by))
    walkers.sfx(g, w, "bash", g.tick + w.timer)
    return _end(g, w)


def _arrived(g, w):
    """LAB_00531DF0."""
    from . import monsters as M
    from ..military import contact
    if not w.tb:
        if not w.tf:
            return _end(g, w)
        o = figure_ok(g, w)
        if o is None:
            return set_action(g, w, 10, 11)
        if o.role == "trireme" and getattr(o, "home", 0) and _crew_home(g, o):
            w.dest = (o.x, o.y)
            w.face = _toward(w, w.dest)
            return M.go_shoot(g, w, (o.x, o.y), M.cur_act(w))
        neighbours(g, w)
        if w.anim:
            return None
        if (o.x, o.y) == (w.x, w.y):
            contact.figure_contact(g, w, o)
            return _end(g, w)
        dist = _cheb(w, o.x, o.y)
        if M.in_range(w, o.x, o.y):
            w.dest = (o.x, o.y)
            w.face = _toward(w, w.dest)
            M.go_shoot(g, w, (o.x, o.y), M.cur_act(w))
            return None
        if dist > 9 or getattr(w, "prog", 15) not in (0, 15):     # far, or mid-tile
            set_action(g, w, 11, 10)
            return _end(g, w)
    else:
        b = g.buildings.get(w.tb)
        if b is None or building_ok(g, w) is None:
            return set_action(g, w, 10, 11)
        bx, by = _target_xy(w, b)
        if w.dest[0] == bx or w.dest[1] == by:
            return _smash(g, w, bx, by)
        dist = _cheb(w, bx, by)
        if M.in_range(w, bx, by):
            w.dest = (bx, by)
            w.face = _toward(w, w.dest)
            M.go_shoot(g, w, (bx, by), M.cur_act(w))
            return None
        if dist < 3:
            return _smash(g, w, bx, by)
        w.tb, w.txy = 0, None
        if not w.tf:
            return _end(g, w)
    M._out_of_melee(g, w)                       # action = 11 direct (no on-enter; from 5 its foes let go)
    w.act = 11
    enter11(g, w)
    return _end(g, w)


def _crew_home(g, o):
    """The trireme's wharf +0xC4 & 1 (crew home; ours: misc "off")."""
    b = g.buildings.get(getattr(o, "home", 0))
    return b is not None and bool(b.misc.get("off"))


def neighbours(g, w):
    """FUN_004D5330: figure_tile_contact with the first figure of each of the 8 neighbours, until a fight starts."""
    from ..military import contact
    for dx, dy in ((0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1)):
        if w.anim:
            return
        here = contact.at(g, (w.x + dx, w.y + dy), with_helpless=True)
        if here:
            contact.figure_contact(g, w, here[0])


def tick25(g, w):
    """monster_smash_building 0x00532700."""
    from . import monsters as M
    _days(g, w)
    w.timer -= 1
    if w.timer < 1:
        b = g.buildings.get(w.tb) if w.tb else None
        if b is not None:
            M.destroy_tile(g, w, *_target_xy(w, b))
        w.tb, w.txy = 0, None
        set_action(g, w, 10, 11)
    return None
