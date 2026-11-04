"""Guardian monsters: the good monsters (unit class 7) of friendly gods (docs/logic/heroes-monsters.md "Guardians").
Their actions in figure_monster_update 0x004C8760, run every tick like the exe (one figure per god):

  entries   Poseidon 0x004E6260 Kraken: set_action(0x15, 0xF); Hades 0x004E62D0 Cerberus: (0xE, 0xF);
            Hephaestus' help 0x004E7E70 Talos: (0x14, 0x10); Ares' visit (sanctuary_update 0x004E94C0) Dragon:
            (0x12, 0), +0x68 = Ares' figure, flags |= 0x80
  0x15      0x005331E0: flags = 0, days 0 -> 14            0x14  0x005331A0: flags = 1, 64 days -> 14
  14        on-enter 0x00532F10: +0x36 += 1, past 14 -> 0x11 (leave); a land walker: the next building
            (building_find_first(rng % buildings_last + 1 + last, state 1 + root)) -> dest = its road access, none ->
            leave (flag 1: the first one from 0); the Kraken: the sea exit / the sea entry by turns (0x00532EB0)
            tick 0x00533070: sanctuary gone -> 0x11; flag 1: -1 a day, 0 -> 0x11; figure_move: arrived / lost -> 14
            again, blocked -> re-route; then enemies (ships for 1/10/16, land soldiers for land walkers) -> (15, 16)
  15        on-enter 0x00533220: the nearest enemy (FUN_004AC570: Chebyshev, the first of equals; ships: 0x40 /
            0x3F; land: the members of enemy companies, slots 35.., not on a building or 0x10000000 tile) -> target,
            dest = its tile, +0x100 = 0, +0x34 = 0x10; none: 14, or 0x11 when flag 1 is clear and no enemy is left
            tick: walk_then(speed, 0xF) (arrived -> +0x34 = 16, lost -> 15) then 0x00533340: sanctuary gone -> 0x11;
            target gone / dying / hidden -> (15, 0x11); ranged at Chebyshev 2..3 -> 28 (back to 15); +0x100 += 1,
            past 14 at tile progress 0/1 with dest off the target's tile -> dest = its tile, re-route; blocked (9) ->
            (15, 0x11); lost (10) -> (0x1D, 0xF)
  16        on-enter 0x00533580: tile contact with the target on its tile, else with the first figure of each of the 8
            neighbours (FUN_004D5330); tick 0x005335E0: (15, 16)
  0x11      on-enter 0x00533600: dest = home (+0x2C); walk_then(speed, 0): arrived -> action 0 (removed the next
            tick), lost -> removed
  0x12      on-enter 0x00533640: +0x42 = 800, +0x44 = 0; tick 0x00533670: past 800 ticks -> (15, 16) with land
            enemies, else (0x13, 0x11); the leader gone / hidden / dying / vanishing (0xB) -> removed; else follows
            him (route mode 3, his speed, +1 when 2+ tiles away): arrived / blocked -> dest = his tile; lost ->
            removed; every 21 ticks dest = its own tile (route freed)
  0x13      on-enter 0x005339E0: the first wolf (figure 0x3B) on the map, none -> 0x11; tick 0x00533A80: follows it,
            arrived -> tile contact; it dies -> 0x11
  0x1D      on-enter: dest = home + (rng % 15 - 8, rng % 15 - 8) (0x00530CD0); walk_then(speed, 0xF) (arrived -> 15);
            flag 1: -1 a day, 0 -> 0x11
  6         (good monster) after the walk: enemies -> (15, 16)
A hit on a good monster outside the busy actions -> (15, 16) (0x00533FB0); figure_fight_end restores the saved
action with the route freed. Killed: the sanctuary's +0xC4 |= 8, +0xC8 = 0xC0 (figure_hit 0x004D54D0), counted down
daily by sanctuary_update (sim/gods/sanct.py): no new guardian for 192 days.
"""
from collections import deque

from . import data, hrng
from ..systems import walkers
from ..military import units

ACTS = frozenset((0, 0x0E, 0x0F, 0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x1D))
GOD_OF = {1: 1, 2: 11, 7: 5, 8: 9}            # FUN_0052F3D0: monsters 1, 2, 7, 8 -> their god's sanctuary
SHIPS = ("enemy_warship", "enemy_transport")  # 0x40, 0x3F
FOLLOW_TICKS = 800                            # 0x00533640: +0x42


def walks_land(w):
    """monster_walks_land 0x0052F190: not the Kraken (1) or Scylla (10)."""
    return w.mid not in (1, 10)


def sea_fighter(w):
    """monster_is_1_10_16 0x0052F150."""
    return w.mid in (1, 10, 16)


def land_enemies(g):
    """FUN_004AC7C0(0): g_enemy_units_alive - transports - warships > 0 (live 0x28..0x2A figures, dying included)."""
    from ..military import invaders
    return any(o.role in invaders.TYPES for o in g.walkers.values())


def sea_enemies(g):
    """FUN_004AC7C0(1): enemy warships, else transports (enemy_ships_recount 0x004E13C0: state 1)."""
    return any(o.role in SHIPS for o in g.walkers.values())


def wants_fight(g, w):
    return (sea_fighter(w) and sea_enemies(g)) or (walks_land(w) and land_enemies(g))


def sanctuary(g, w):
    """FUN_0052F3D0: the god's sanctuary of a good monster 1, 2, 7 or 8 (else 0: it leaves)."""
    god = GOD_OF.get(w.mid)
    if god is None or w.uclass != 7:
        return None
    try:
        from .. import gods
    except ImportError:
        return g.buildings.get(getattr(w, "sanctuary", 0))
    return gods.sanctuary(g, god)


def _order(o):
    return (getattr(o, "fslot", 0), o.id)


def nearest_enemy(g, w, sea):
    """FUN_004AC570: the nearest (Chebyshev) enemy, the first of equals in the exe's order."""
    best, bd = None, 9999
    if sea:
        for o in sorted((o for o in g.walkers.values() if o.role in SHIPS), key=_order):
            if not units.alive(o) or getattr(o, "hidden", False):
                continue
            d = max(abs(o.x - w.x), abs(o.y - w.y))
            if best is None or d < bd:
                best, bd = o, d
        return best
    from ..military import invaders
    occ, fl = g.world.occ, g.world.flags
    for cid in sorted(invaders.ecomps(g)):
        for i in invaders.ecomps(g)[cid]["ids"]:
            o = g.walkers.get(i)
            if o is None or not units.alive(o):
                continue
            if occ[o.y, o.x] > 0 or int(fl[o.y, o.x]) & 0x10000000:
                continue
            d = max(abs(o.x - w.x), abs(o.y - w.y))
            if best is None or d < bd:
                best, bd = o, d
    return best


# --- actions -------------------------------------------------------------------------------------------------

def set_action(g, w, a, ret=0):
    """figure_set_action 0x004ABAF0: saved = action, +0x34 = ret, action = a, then the on-enter handler. From a
    melee its walk started this tick (action 5) it leaves the fight without figure_fight_end."""
    from . import monsters as M
    if a == 7:
        return M.set_action(g, w, 7, ret)
    M._out_of_melee(g, w)
    w.saved = M.cur_act(w)
    w.ret = ret
    w.act = a
    enter(g, w, a)


def enter(g, w, a):
    """monster_on_action_enter 0x0052F750 for the guardian actions."""
    from . import monsters as M
    if a == 0x0E:
        return _enter14(g, w)
    if a == 0x0F:
        return _enter15(g, w)
    if a == 0x10:
        return _enter16(g, w)
    if a == 0x11:
        w.dest = tuple(w.spawn); free_route(w)
    elif a == 0x12:
        w.follow_t0, w.cnt = g.tick, 0
    elif a == 0x13:
        return _enter19(g, w)
    elif a == 0x14:
        w.gday, w.gdays, w.gflag = g.day, 64, 1
        set_action(g, w, 0x0E, 0)
    elif a == 0x15:
        w.gday, w.gdays, w.gflag = g.day, 0, 0
        set_action(g, w, 0x0E, 0)
    elif a == 0x1D:
        free_route(w)
        w.dest = M.wander_tile(g, w, tuple(w.spawn))
    elif a == 6:                                 # 0x0052FA30: route freed, targets dropped, dest = home
        free_route(w)
        w.tf = w.tb = 0
        w.dest = tuple(w.spawn)
    elif a == 7:
        M.set_action(g, w, 7, getattr(w, "ret", 0))


def _enter14(g, w):
    w.timer = getattr(w, "timer", 0) + 1
    if w.timer > 14:
        return set_action(g, w, 0x11, 0)
    free_route(w)
    if walks_land(w):
        b = _next_building(g, w.tb)
        if b is None:
            if not getattr(w, "gflag", 0):
                return set_action(g, w, 0x11, 0)
            b = _next_building(g, 0)
        w.tb = b.id if b is not None else 0
        if b is not None:
            w.dest = tuple(getattr(b, "access", None) or (b.x, b.y))
        return None
    if sea_fighter(w):                           # 0x00532EB0: the sea exit, then the sea entry, by turns
        wd = g.world
        if not w.tb:
            w.dest, w.tb = tuple(wd.sea_exit or wd.sea_entry or wd.entry), 1
        else:
            w.dest, w.tb = tuple(wd.sea_entry or wd.entry), 0
    return None


def _next_building(g, last):
    """FUN_00532D80: building_find_first(rng15 % buildings_last + 1 + last, flags 5: state 1 and the root record)."""
    ids = [i for i, b in g.buildings.items() if b.kind != "road"]
    if not ids:
        return None
    top = max(g.buildings)
    start = hrng(g).randrange(1 << 15) % top + 1 + last
    for i in sorted(ids):
        if i >= start:
            return g.buildings[i]
    return None


def _enter15(g, w):
    sea = 0
    t = None
    if sea_fighter(w) and sea_enemies(g):
        sea = 1
        t = nearest_enemy(g, w, True)
    elif walks_land(w) and land_enemies(g):
        t = nearest_enemy(g, w, False)
    if t is not None:
        w.tf = t.id
        w.dest = (t.x, t.y)
        w.cnt = 0
        w.ret = 0x10
        free_route(w)
        return None
    if not getattr(w, "gflag", 0) and not (sea_enemies(g) if sea else land_enemies(g)):
        return set_action(g, w, 0x11, 0)
    return set_action(g, w, 0x0E, 0)


def _enter16(g, w):
    """0x00533580: contact with the target on its own tile, else FUN_004D5330 with each neighbour's first figure."""
    from ..military import contact
    w.a16 = g.tick
    o = g.walkers.get(w.tf)
    if o is not None and (o.x, o.y) == (w.x, w.y):
        return contact.figure_contact(g, w, o)
    for dx, dy in ((0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1)):
        if w.anim == "fight":
            return None
        here = contact.at(g, (w.x + dx, w.y + dy), with_helpless=True)
        if here:
            contact.figure_contact(g, w, here[0])
    return None


def _enter19(g, w):
    for o in sorted((o for o in g.walkers.values() if o.role == "wolf"), key=_order):
        if units.alive(o) and not getattr(o, "hidden", False):
            w.tf, w.dest = o.id, (o.x, o.y); free_route(w)
            return None
    return set_action(g, w, 0x11, 0)


def _route(g, w, goal):
    if not walks_land(w):
        return walkers.water_path(g, (w.x, w.y), {goal})
    return route3(g, (w.x, w.y), goal)


N = 228
DIR8 = ((0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1))


def _bfs(ok, start, goal):
    """The route_distance template 0x00588920: grid_distance from start (= 1), 4-way (N, E, S, W), until goal is
    popped. {tile index: distance}."""
    s, e = start[1] * N + start[0], goal[1] * N + goal[0]
    dist = {s: 1}
    q = deque([s])
    while q:
        t = q.popleft()
        if t == e:
            break
        d = dist[t] + 1
        x = t % N
        for j in (t - N, t + 1 if x < N - 1 else -1, t + N, t - 1 if x > 0 else -1):
            if 0 <= j < N * N and j not in dist and ok[j]:
                dist[j] = d
                q.append(j)
    return dist


def _trace(dist, start, goal, step):
    """route_trace 0x0058BC80 (mode 8: step 1, mode 4: step 2): from goal back to start, each step to the lowest
    distance, a tie to the direction facing the start, never straight back; past 499 steps it fails."""
    sx, sy = start
    x, y = goal
    best = dist.get(y * N + x, 0)
    if best < 1:
        return None
    out, back = [], -1
    while best > 1:
        if sx < x:
            want = 7 if sy < y else 6 if sy == y else 5
        elif sx == x:
            want = 0 if sy < y else 4 if sy > y else 8
        else:
            want = 1 if sy < y else 2 if sy == y else 3
        choice, best = -1, dist[y * N + x]
        for k in range(0, 8, step):
            if k == back:
                continue
            dx, dy = DIR8[k]
            v = dist.get((y + dy) * N + x + dx, 0)
            if v and (v < best or (v == best and (k == want or choice == -1))):
                choice, best = k, v
        if choice < 0 or len(out) >= 499:
            return None
        out.append((x, y))
        x, y = x + DIR8[choice][0], y + DIR8[choice][1]
        back = (choice + 4) & 7
    out.reverse()
    return out


def route3(g, start, goal):
    """Route mode 3 (figure_find_route 0x004D8220): the dest must be land (route & 0x11C); a roads-only search
    (0x0058A6C0, mask 0x10C) traced 4-way, else 8-way; no road route: route_distance (land, 0x11D) traced 8-way.
    The tiles after start, or None."""
    from . import monsters as M
    if start == goal:
        return []
    land = M.passable(g)
    if not land[goal[1] * N + goal[0]]:
        return None
    road = _road_ok(g)
    dist = _bfs(road, start, goal)
    if goal[1] * N + goal[0] in dist:
        return _trace(dist, start, goal, 2) or _trace(dist, start, goal, 1)
    return _trace(_bfs(land, start, goal), start, goal, 1)


def _road_ok(g):
    from ..systems.services import occ_version
    v = (occ_version(g), getattr(g, "map_version", 0))
    c = getattr(g, "_guard_road", None)
    if c is None or c[0] != v:
        c = g._guard_road = (v, g.world.road.ravel().tolist())
    return c[1]


def _passable(g, w, t):
    from . import monsters as M
    if not walks_land(w):
        return walkers.ship_grid(g)[t[1], t[0]] != 0xFF
    return M.passable(g)[t[1] * M.N + t[0]]


def move(g, w, speed):
    """figure_move 0x004D1170, tick by tick as the exe (the enemy ships' navy.sail_fine): sub-steps this tick by the
    speed code (navy.substeps); tile progress +0x39 0..14, 15 at a centre; at a centre the next route tile (none
    left: 8 arrived; not passable: 9, the route freed), the tile changes at progress 8 (figure_change_tile: the
    contact); figure_find_route (route freed: w.route None) puts the progress at 15, so a re-route mid-tile skips the
    rest of it. Returns None (moving), 8, 9 or 10 (no route)."""
    from ..military import navy
    route = getattr(w, "route", None)
    prog = getattr(w, "prog", 15)
    n = navy.substeps(w, speed)                  # the speed phase counts whatever figure_route_walk then does
    if route is None:                            # figure_route_walk 0x004D7BD0: route_id < 1 -> figure_find_route
        if (w.x, w.y) == tuple(w.dest):          # at dest: direction 8 before any sub-step (progress kept)
            return 8
        p = _route(g, w, tuple(w.dest))
        if p is None:
            w.route, w.path = None, []
            return 10
        route, prog = list(p), 15
    for _ in range(n):
        prog += 1
        if prog > 14:
            prog = 15
            if not route:
                w.route, w.path, w.prog = None, [], 15
                return 8
            nxt = route[0]
            if not _passable(g, w, nxt):
                w.route, w.path, w.prog = None, [], 15
                return 9
            route = route[1:]
            w.heading = nxt
            w.face = ((nxt[0] > w.x) - (nxt[0] < w.x), (nxt[1] > w.y) - (nxt[1] < w.y))
            prog = 0
        if prog == 8:
            units.step(g, w, w.heading)          # tile contact (sim/military/contact.on_enter)
            num, den = walkers.SPEED[max(0, min(18, speed))]
            w.step_draw = (g.tick, g.tick + max(1, round(15 * den / max(1, num))))   # play mode: the step drawn
            if w.anim:
                w.route, w.prog = route, prog
                return None
    w.route, w.prog = route, prog
    w.path = ([w.heading] if prog < 8 else []) + list(route)
    return None


def free_route(w):
    """figure_route_free."""
    w.route, w.path = None, []


def walk_then(g, w, speed, lost):
    """figure_walk_then 0x004ABB60: arrived -> set_action(+0x34); lost -> `lost` (0: removed); blocked -> re-route."""
    d = move(g, w, speed)
    if d == 9:
        free_route(w)
    elif d == 10:
        if lost == 0:
            _remove(g, w)
        else:
            set_action(g, w, lost, 0)
    elif d == 8:
        set_action(g, w, getattr(w, "ret", 0), 0)
    return d


def _remove(g, w):
    """state 2: the figure is gone (no death, no message)."""
    from . import monsters as M
    r = M.records(g).get(w.mid)
    if r is not None and r["fig"] == w.id:
        r["fig"] = 0
    w.gone = True
    units.remove(g, w)


def _spd(w):
    """figure_type_value(f, 8): the monster row's speed (older saves' guardians have no speed_code)."""
    from . import monsters as M
    return getattr(w, "speed_code", M.SPEED)


def _days(g, w):
    """+0x108 / +0x10E with flag 1: -1 a day; True when it reached 0."""
    if getattr(w, "gflag", 0) and g.day != getattr(w, "gday", g.day) and getattr(w, "gdays", 0) > 0:
        w.gday = g.day
        w.gdays -= 1
        return w.gdays == 0
    return False


def act(g, w):
    a = w.act
    if a == 0:                                   # figure_monster_update case 0: state 2
        return _remove(g, w)
    if a == 0x0E:
        _tick14(g, w)
    elif a == 0x0F:
        _tick15(g, w)
    elif a == 0x10:
        set_action(g, w, 0x0F, 0x10)
    elif a == 0x11:
        walk_then(g, w, _spd(w), 0)
    elif a == 0x12:
        _tick18(g, w)
    elif a == 0x13:
        _tick19(g, w)
    elif a == 0x1D:
        walk_then(g, w, _spd(w), 0x0F)
        if w.act == 0x1D and _days(g, w):
            set_action(g, w, 0x11, 0)
    else:                                        # 0x14 / 0x15 only pass through their on-enter
        set_action(g, w, 6, 7)
    return _next(g, w)


def _next(g, w):
    if w.id not in g.walkers or getattr(w, "gone", False) or w.anim:
        return None
    if w.act == 28:
        return None                              # monsters.go_shoot scheduled it
    walkers.schedule(g, w, 1)
    sd = w.__dict__.get("step_draw")
    if sd and sd[0] == w.arrived:                # play mode: the step drawn over its sub-steps (sim/live.py)
        w.step_end = sd[1]
    return None


def _tick14(g, w):
    if sanctuary(g, w) is None:
        return set_action(g, w, 0x11, 0)
    if _days(g, w):
        return set_action(g, w, 0x11, 0)
    d = move(g, w, _spd(w))
    if d in (8, 10):
        set_action(g, w, 0x0E, 0)
    elif d == 9:
        free_route(w)
    if w.anim:
        return None
    if wants_fight(g, w):
        set_action(g, w, 0x0F, 0x10)


def _tick15(g, w):
    from . import monsters as M
    d = walk_then(g, w, _spd(w), 0x0F)
    if w.id not in g.walkers:
        return None
    # a tile contact on the step started a melee (action 5): 0x00533340 goes on with the exe's action 5 (item 3)
    if sanctuary(g, w) is None:
        return set_action(g, w, 0x11, 0)
    o = g.walkers.get(w.tf)
    if o is None or not units.alive(o) or getattr(o, "hidden", False):
        w.tf = 0
        return set_action(g, w, 0x0F, 0x11)
    if M.in_range(w, o.x, o.y):
        return M.go_shoot(g, w, (o.x, o.y), M.cur_act(w))
    w.cnt = getattr(w, "cnt", 0) + 1
    if w.cnt > 14 and getattr(w, "prog", 15) in (0, 1) and tuple(w.dest) != (o.x, o.y):
        w.cnt = 0
        w.dest = (o.x, o.y)
        free_route(w)
        return None
    if d == 9:
        return set_action(g, w, 0x0F, 0x11)
    if d == 10:
        return set_action(g, w, 0x1D, 0x0F)


def _tick18(g, w):
    """0x00533670: follow the leader (Ares) for 800 ticks."""
    el = g.tick - w.follow_t0
    if el >= FOLLOW_TICKS:
        if land_enemies(g):
            return set_action(g, w, 0x0F, 0x10)
        return set_action(g, w, 0x13, 0x11)
    L = g.walkers.get(getattr(w, "leader", 0))
    if L is None or not units.alive(L) or getattr(L, "hidden", False) or getattr(L, "task", "") == "leave":
        return _remove(g, w)
    from ..systems import walkers as W
    sp = W.speed(g, L) if L.role != "god" else units.col(g, L, "speed")
    if max(abs(L.x - w.x), abs(L.y - w.y)) > 1:
        sp += 1
    w.cnt = getattr(w, "cnt", 0) + 1
    d = move(g, w, sp)                           # dest from figure_create: its own tile (arrived at once)
    if d in (8, 9):
        w.cnt = 0
        free_route(w)
        w.dest = (L.x, L.y)
    elif d == 10:
        return _remove(g, w)
    elif w.cnt >= 21:                            # dest = its own tile (the exe's x/y of itself), route freed
        w.cnt = 0
        w.dest = (w.x, w.y); free_route(w)


def _tick19(g, w):
    """0x00533A80: chase the wolf."""
    from ..military import contact
    o = g.walkers.get(w.tf)
    if o is None or not units.alive(o):
        return set_action(g, w, 0x11, 0)
    if (o.x, o.y) != tuple(w.dest):
        w.dest = (o.x, o.y); free_route(w)
    d = move(g, w, _spd(w))
    if d == 8:
        return contact.figure_contact(g, w, o)
    if d == 9:
        free_route(w)
    elif d == 10:
        return set_action(g, w, 0x11, 0)


def fight_over(g, w):
    """figure_fight_end 0x004D61B0: the saved action again (no on-enter), the route freed."""
    free_route(w)
    walkers.schedule(g, w, 1)


def hit(g, w):
    """0x00533FB0 for a good monster: (15, 16) unless busy."""
    from .combat import BUSY
    if w.anim == "fight" or w.act in BUSY:
        return
    set_action(g, w, 0x0F, 0x10)
    _next(g, w)


def spawn(g, m, god, b, leader=None):
    """The guardian of `god` at its sanctuary b (monster_spawn 0x0052EEF0 with the building: the altar access; sea
    monsters the sea entry), unit class 7, then the god's entry action."""
    from . import monsters as M
    x, y = b.access if getattr(b, "access", None) else (b.x, b.y)
    if m in (1, 10) and g.world.sea_entry:
        x, y = g.world.sea_entry
    w = units.spawn(g, "monster", x, y, delay=1, mid=m, slot=-1, ev=-1, uclass=7, spawn=(x, y), homexy=(x, y),
                    act=0, timer=0, tday=g.day, scan_t=0, tb=0, tf=0, rampage=0, dest=(x, y), aggr=0, cats=(0, 0, 0),
                    mflags=0, good=f"m{m}", sanctuary=b.id, gflag=0, gdays=0, gday=g.day, cnt=0, ret=0, prog=15,
                    speed_code=M.SPEED)
    w.face = (0, 1)
    M.records(g)[m] = dict(fig=w.id, ev=-1)
    if god == 1:
        set_action(g, w, 0x15, 0x0F)
    elif god == 11:
        set_action(g, w, 0x0E, 0x0F)
    elif god == 9:
        set_action(g, w, 0x14, 0x10)
    elif god == 5:
        w.leader = leader.id if leader is not None else 0
        w.mflags |= 0x80
        set_action(g, w, 0x12, 0)
    return w
