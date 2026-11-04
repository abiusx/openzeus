"""The other gods' help (docs/logic/religion.md "Help and prayers", "Help actions"): the per-god functions of god_help
0x004E6630 and their figure actions in figure_god_handler 0x004C5D40.

Zeus (zeus_help 0x004E6B80, prayed only): the strongest enemy army's city (FUN_005687A0, not the player's), its
formation with the largest count x weight (1; 2 for types 0xC / 0x29; 3 for 0xD / 0x2A); none -> the prayer is queued
(pending, 2 months). Zeus is put at his sanctuary (god_figure_spawn(sanctuary x, y)), action 0x0F:
  0x0F  the vanish group; at its last frame: dest = FUN_004C43C0(zeus, the formation's first figure, 10), placed there;
        FUN_004C4090(city, 15) (the city's soldiers within 15 steps of their route's end stop: action 7, timer 50)
  0x10  the appear group (FUN_004C4090(city, 15) each tick); then 0x11, 5 shots, dest = that figure's tile
  0x11  per attack cycle a bolt 0x2D at dest (shot_frame); FUN_004C4090(city, 1000) each tick (all stop); after the 5th,
        when that bolt is gone: 0x13
  0x13  the cast group (FUN_004C4090(city, 15)); at its last frame the formation's first figure falls
        (formation_member_lost) and every enemy soldier and ship (types 0x28..0x2A, 0x3F, 0x40) gets action 4; Zeus 4.
Aphrodite (aphrodite_help 0x004E77E0): need (automatic): g_house_room_total >= g_house_capacity_total / 2; dest 9 tiles
from her sanctuary's reference point, facing the tile 8 out (FUN_00547890 by the orientation +0x9C); spawned at the
sanctuary, action 0x19 walk there, 0x1A wait 100 ticks, then FUN_004C56F0: every house with room gets min(room, 4)
people (a vacant one turns into type 2 first); 0x14 home.
Hades (hades_help 0x004E81A0; needs a palace): need (automatic) treasury < 1, then for the first friendly world city
(in use, class 0 / 3, attitude >= 50, not extorted) a 50 % draw (rng_a & 1 -> no help), none -> help. 0x2C
(FUN_004C4BC0): 8 miners (figure 0x3E, chained) to the spots FUN_00546E80 gives, Hades to his; 0x2D walk, 0x2E 100
ticks, 0x2F every 30 ticks: no miner digging (FUN_004C4D20: none in 10 / 11) -> the palace's road access (0x30), there
treasury + 3200; 0x14 home. A miner (figure_miner 0x004C1310 for a composite): 10 walk to its spot, 0xB dig 408 ticks
(0x198) facing the god's face tile, 0xC follow the one ahead while Hades is in 0x2E / 0x2F, then walk to his dest
and vanish there; Hades gone -> deleted.
Athena (athena_help 0x004E7C50): need (automatic) city olives + oil < 400 (city +0x18A4 + +0x1934; ours: the stock)
and a house of type 7..14; room for 1600 of olives and of oil each (FUN_00488A60); 0x25 (FUN_004C4D50): 8 growers
(figure 5, waits (5 - k) * 10 ticks) to the grove spots of FUN_00547250, Athena to hers; 0x26 walk, 0x27 100 ticks,
0x28 every 30 ticks: no grower out (FUN_004C4EF0: none in 0xE / 0xF) -> the storehouse with the most room for both
(FUN_004C46D0, orders accept / get, 1600 each), 0x29 walk there and put 1600 olives + 1600 oil in; 0x14 home. A grower
(0x004AECF0): 0x11 wait, 0xE walk, 0xF 100 ticks facing its tile, 0x10 follow the one ahead while Athena is in
0x27..0x29, else gone.
The spots are offsets from the composite's reference point (composite_offset_rotate_b 0x005466A0 = monuments.origin),
turned by the orientation as FUN_005471B0 turns a 1x1 offset: o1 (dy, -dx), o2 (-dx, -dy), o3 (-dy, dx).
"""
from . import T, rec, sanctuary, NAMES
from .month import log

BUSY = frozenset(("strike", "precinct", "hades", "athena", "wine", "hera"))


def _W():
    from ..systems import walkers
    return walkers


def frames(i, k):
    from .attack import frames as f
    return f(i, k)


def tpf(i, k):
    from .attack import tpf as f
    return f(i, k)


def dur(i, k):
    """A rate-100 look's length (attack.dur, bug 393): 0x0F vanish, 0x10 appear, 0x11 attack, 0x13 cast."""
    from .attack import dur as d
    return d(i, k)


ENEMY_LAND = ("enemy_infantry", "enemy_archer", "enemy_cavalry")
ENEMY_SHIPS = ("enemy_warship", "enemy_transport")
WEIGHT = {"infantry": 1, "missile": 2, "cavalry": 3}


# --- Zeus ----------------------------------------------------------------------------------------------------------

def _army_target(g):
    """zeus_help's choice: (invasion id, company) or None."""
    try:
        from ..military import invaders
    except ImportError:
        return None
    best_inv, bs = None, 0
    for inv_id, inv in sorted(invaders.invasions(g).items()):
        s = 0
        for cid in inv.get("companies", []):
            comp = invaders.ecomps(g).get(cid)
            if comp is not None:
                s += len(invaders.alive_members(g, comp)) * WEIGHT.get(comp.get("cls"), 1)
        if s > bs:
            best_inv, bs = inv_id, s
    if best_inv is None:
        return None
    best, bv = None, 0
    for cid in invaders.invasions(g)[best_inv].get("companies", []):
        comp = invaders.ecomps(g).get(cid)
        if comp is None:
            continue
        v = len(invaders.alive_members(g, comp)) * WEIGHT.get(comp.get("cls"), 1)
        if v > bv:
            best, bv = comp, v
    return (best_inv, best) if best is not None else None


def _leader(g, comp):
    from ..military import invaders
    ms = invaders.alive_members(g, comp)
    return ms[0] if ms else None


def _halt(g, inv_id, n):
    """FUN_004C4090(city, n): the city's soldiers within n steps of their route's end stop (action 7, timer 50)."""
    from ..military import invaders
    inv = invaders.invasions(g).get(inv_id)
    if inv is None:
        return
    W = _W()
    for cid in inv.get("companies", []):
        comp = invaders.ecomps(g).get(cid)
        if comp is None:
            continue
        for m in invaders.alive_members(g, comp):
            if m.path and len(m.path) < n:
                m.path, m.task = [], "wait"
                W.schedule(g, m, 50)


def zeus(g, i, prayed):
    from .help import busy, _queue, _granted
    if busy(g, i) or not prayed:
        return
    tgt = _army_target(g)
    if tgt is None:
        return _queue(g, i, prayed)
    b = sanctuary(g, i)
    from . import figures
    w = figures.figure(g, i)
    if w is None:
        w = figures._spawn(g, i, b.x, b.y, "strike", home=b.id)
    w.task, w.st, w.inv, w.comp = "strike", "vanish", tgt[0], tgt[1]["id"]
    w.anim_t0, w.anim_kind, w.path, w.state = g.tick, "vanish", [], "held"
    _W().schedule(g, w, dur(i, 1))
    ld = _leader(g, tgt[1])
    _granted(g, i, prayed, tile=(ld.x, ld.y) if ld else None)


def _strike(g, w):
    from ..military import invaders, units
    from . import bolts
    from .fight import _intercept
    W = _W()
    comp = invaders.ecomps(g).get(w.comp)
    ld = _leader(g, comp) if comp is not None else None
    if w.st == "vanish":                                     # 0x0F
        if ld is None:
            return _end(g, w)
        x, y = _intercept_n(g, ld, 10)
        w.prev, (w.x, w.y), w.arrived = None, (x, y), g.tick
        _W().listed(g, w)
        _halt(g, w.inv, 15)
        w.st, w.anim_t0, w.anim_kind = "appear", g.tick, "appear"
        return W.schedule(g, w, dur(w.god, 3))
    if w.st == "appear":                                     # 0x10 (the halt each tick: once at its start, ours)
        _halt(g, w.inv, 15)
        if ld is None:
            return _end(g, w)
        w.st, w.shots, w.aim, w.state = "shoot", 5, (ld.x, ld.y), ""
        w.face = (ld.x - w.x, ld.y - w.y)
        w.cyc_t0 = None
    if w.st == "shoot":                                      # 0x11
        _halt(g, w.inv, 1000)
        n, p = frames(w.god, 2), tpf(w.god, 2)               # rate 100: frame f at f * p ticks (bug 393)
        sf = min(T()["shot_frame"][w.god], n - 1)
        if w.shots > 0:
            if w.cyc_t0 is None:
                w.cyc_t0, w.anim_t0, w.anim_kind, w.shot = g.tick, g.tick, "attack", False
            k = g.tick - w.cyc_t0
            if not w.shot and k >= sf * p:
                w.shot = True
                bolts.shoot(g, w, w.aim, 0x2D)
            if k >= n * p - 1:
                w.cyc_t0 = None
                w.shots -= 1
            return W.schedule(g, w, 1)
        if bolts.alive(g, w):
            return W.schedule(g, w, 1)
        w.st, w.anim_t0, w.anim_kind = "cast", g.tick, "cast"
        return W.schedule(g, w, dur(w.god, 4))
    if w.st == "cast":                                       # 0x13
        _halt(g, w.inv, 15)
        if ld is not None:
            units.kill(g, ld, w)
        for o in sorted(g.walkers.values(), key=lambda o: o.id):
            if o.role in ENEMY_LAND + ENEMY_SHIPS and units.alive(o):
                if o.role in ENEMY_SHIPS:
                    from ..military import navy
                    try:
                        navy.sink(g, o)
                        continue
                    except Exception:                        # noqa: BLE001  (navy's own end; a kill otherwise)
                        pass
                units.kill(g, o, w)
        log(g, f"{NAMES[w.god]} strikes down the invaders")
        return _end(g, w, gated=True)                        # Zeus action 4
    return _end(g, w)


def _intercept_n(g, t, n):
    """FUN_004C43C0(fig, target, n): n steps ahead on its route, or free_tile_near(that, n) when within 1."""
    from .fight import free_tile_near
    p = getattr(t, "path", None) or []
    if p:
        x, y = p[min(n - 1, len(p) - 1)]
        if (x - t.x) ** 2 + (y - t.y) ** 2 > 1:
            return (x, y)
    else:
        x, y = t.x, t.y
    return free_tile_near(g, x, y, n)


def _end(g, w, gated=False):
    from .figures import _leave
    w.anim_kind = ""
    return _leave(g, w, gated)


# --- Aphrodite -------------------------------------------------------------------------------------------------------

def spot(b, dx, dy):
    """A tile at offset (dx, dy) of orientation 0 from the sanctuary's reference point, turned (FUN_005471B0, size 1)."""
    from ..systems import monuments
    ox, oy = monuments.origin(b)
    o = b.misc.get("orient", 0) & 3
    dx, dy = ((dx, dy), (dy, -dx), (-dx, -dy), (-dy, dx))[o]
    return (ox + dx, oy + dy)


def house_totals(g):
    """g_house_capacity_total / g_house_room_total (houses_capacity step 22, population.md)."""
    from ..systems import index, housing
    cap = room = 0
    for h in index.of(g, "house"):
        c = housing.capacity(g, h)
        cap += c
        room += max(0, c - h.occupants)
    return cap, room


def aphrodite(g, i, prayed):
    from .help import busy, _queue, _granted
    if busy(g, i):
        return _queue(g, i, prayed) if prayed else None
    cap, room = house_totals(g)
    if not prayed and room < cap // 2:
        return
    b = sanctuary(g, i)
    from . import figures
    w = figures.figure(g, i)
    if w is None:
        w = figures._spawn(g, i, b.x, b.y, "precinct", home=b.id)
    W = _W()
    w.task, w.st, w.state = "precinct", "walk", ""
    w.dest, w.face_tile = spot(b, 1, 9), spot(b, 1, 8)          # FUN_00547890
    w.path = _inner_path(g, b, (w.x, w.y), w.dest)
    W.schedule(g, w, 1)
    _granted(g, i, prayed, tile=w.face_tile)


def _inner_path(g, b, a, goal):
    """A walk from the sanctuary's tile to its inner spot: open land or the sanctuary's own tiles (the god walks in
    the precinct; ours: 8-neighbour breadth-first, 64 tiles at most). [] when unreachable (she helps where she is)."""
    from collections import deque
    W = _W()
    ok, occ, n = W.walkable(g), g.world.occ, 228
    prev, q = {a: None}, deque([a])
    while q:
        c = q.popleft()
        if c == goal:
            out = []
            while c != a:
                out.append(c)
                c = prev[c]
            return out[::-1]
        if len(prev) > 4096:
            break
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                t = (c[0] + dx, c[1] + dy)
                if t in prev or not (0 <= t[0] < n and 0 <= t[1] < n):
                    continue
                if max(abs(t[0] - a[0]), abs(t[1] - a[1])) > 32:
                    continue
                if int(occ[t[1], t[0]]) == b.id or ok[t[1] * n + t[0]]:
                    prev[t] = c
                    q.append(t)
    return []


def _aphro(g, w):
    """0x19 walk to the spot, 0x1A 100 ticks, then the effect (Apollo city_heal_plague, Aphrodite FUN_004C56F0)."""
    W = _W()
    from .figures import tile_ticks, _go_home
    if w.st == "walk":                                       # 0x19
        if w.path:
            W.step_to(g, w, w.path.pop(0))
            return W.schedule(g, w, tile_ticks(g, w))
        w.st, w.anim_t0, w.anim_kind = "wait", g.tick, "cast"
        w.face = (w.face_tile[0] - w.x, w.face_tile[1] - w.y)
        return W.schedule(g, w, 100)                         # 0x1A: +1 a tick, > 99
    if w.god == 3:
        n = heal_plague(g)
        log(g, f"{NAMES[w.god]} heals the city ({n} houses)")
    else:
        fill_houses(g)
        log(g, f"{NAMES[w.god]} fills the houses")
    w.anim_kind = ""
    return _go_home(g, w)                                   # 0x14


# --- Apollo -----------------------------------------------------------------------------------------------------------

def apollo(g, i, prayed):
    """apollo_help 0x004E71F0: an infected house (house +0x85; prayed with city health < 100: no house needed); the
    spot 6 out of the sanctuary facing the tile 4 out (FUN_005477A0); then as Aphrodite (0x19 / 0x1A) with
    city_heal_plague 0x004C5690."""
    from .help import busy, _queue, _granted
    from ..systems import index, health
    if busy(g, i):
        return _queue(g, i, prayed) if prayed else None
    if not (prayed and health._st(g)["health"] < 100):
        if not any(h.misc.get("infected") for h in index.of(g, "house")):
            return _queue(g, i, prayed) if prayed else None
    b = sanctuary(g, i)
    from . import figures
    w = figures.figure(g, i)
    if w is None:
        w = figures._spawn(g, i, b.x, b.y, "precinct", home=b.id)
    w.task, w.st, w.state = "precinct", "walk", ""
    w.dest, w.face_tile = spot(b, 1, 6), spot(b, 1, 4)
    w.path = _inner_path(g, b, (w.x, w.y), w.dest)
    _W().schedule(g, w, 1)
    _granted(g, i, prayed, tile=w.face_tile)


def heal_plague(g):
    """city_heal_plague 0x004C5690: every house's infection and its two counters cleared, the plague walkers (0x42)
    gone, city health + 50 (ours: at most 100)."""
    from ..systems import index, health
    W = _W()
    n = 0
    for h in index.of(g, "house"):
        if h.misc.get("infected"):
            n += 1
        h.misc["infected"] = 0
    for o in [o for o in g.walkers.values() if o.role == "plagued"]:
        W.remove(g, o)
    st = health._st(g)
    st["health"] = min(100, st["health"] + 50)
    return n


# --- Dionysus ---------------------------------------------------------------------------------------------------------

def dionysus(g, i, prayed):
    """dionysus_help 0x004E8010: need (automatic) city wine < 400 (+0x18A8 + +0x1938; ours: the stock) and a house of
    type 9..14 that wants wine (house_param col 11); room for 1600 wine (FUN_00488A60); 0x2A dionysus_satyrs_spawn
    0x004C51E0: the storehouse with the most room for wine (FUN_004C44E0(21, &room, 0)), gift min(room, 1600),
    ceil(gift / 400) satyrs behind (ours: not drawn, as the other food gods' carriers); 0x2B walk there, the wine in."""
    from .help import busy, _queue, _granted, room_for
    from ..systems import index
    if busy(g, i):
        return _queue(g, i, prayed) if prayed else None
    if not prayed:
        stock = sum(s.goods.get("wine", 0) for s in index.of(g, "storage"))
        if stock >= 400 or not any(h.level >= 7 and g.cat.houses[h.level].get("wine") for h in index.of(g, "house")
                                   if h.level < len(g.cat.houses)):
            return
    if "wine" not in g.cat.resources or room_for(g, "wine") < GIFT:
        return _queue(g, i, prayed) if prayed else None
    to = _store_for(g, ("wine",))
    if to is None:
        return _queue(g, i, prayed) if prayed else None
    from ..systems import economy
    from .help import gift_leftover                          # dionysus_satyrs_spawn: 1600 - min(room, 1600)
    gift_leftover(g, i, GIFT - min(GIFT, economy.storage_room(g, to, "wine")), 0)
    from . import figures
    b = sanctuary(g, i)
    w = figures.figure(g, i)
    if w is None:
        w = figures._spawn(g, i, b.x, b.y, "wine", home=b.id)
    W = _W()
    w.task, w.st, w.state, w.to = "wine", "deliver", "", to.id
    w.dest = tuple(to.access) if to.access else (to.x, to.y)
    w.path = W.land_path(g, (w.x, w.y), {w.dest}, max_dist=W.ROUTE_MAX) or []
    W.schedule(g, w, 1)
    _granted(g, i, prayed)


def _store_for(g, goods):
    """The storehouse (type 0x3A) with the most room for the goods (up to 1600 each), orders accept / get."""
    from ..systems import economy, index
    best, br = None, 0
    for s in sorted(index.of(g, "storage"), key=lambda b: b.id):
        if s.key != "storehouse" or s.access is None or not s.employees:
            continue
        r = 0
        for good in goods:
            if good in g.cat.resources and economy.order(g, s, good) in ("accept", "get"):
                r += min(GIFT, economy.storage_room(g, s, good))
        if r > br:
            best, br = s, r
    return best


def _wine(g, w):
    W = _W()
    from .figures import tile_ticks, _go_home
    if w.path:
        W.step_to(g, w, w.path.pop(0))
        return W.schedule(g, w, tile_ticks(g, w))
    to = g.buildings.get(w.to)
    if to is not None:
        from ..systems import economy
        n = min(GIFT, economy.storage_room(g, to, "wine"))
        to.goods["wine"] = to.goods.get("wine", 0) + n
        log(g, f"{NAMES[w.god]} brings {n} wine to the {g.cat.spec(to.key)['name']} at ({to.x},{to.y})")
    return _go_home(g, w)


def fill_houses(g):
    """FUN_004C56F0: every house with room takes min(room, 4) people (a vacant one becomes type 2 first; ours: a
    vacant elite lot keeps its level)."""
    from ..systems import index, housing
    n = 0
    for h in sorted(index.of(g, "house"), key=lambda b: b.id):
        room = housing.capacity(g, h) - h.occupants
        if room <= 0:
            continue
        if h.occupants < 1 and h.level != housing.ELITE_LOT:
            h.level = 0
        k = min(room, 4)
        h.occupants += k
        g.city.population += k
        n += k
    return n


# --- the handler ---------------------------------------------------------------------------------------------------

# --- Hades and Athena: the god at a spot of the precinct, 8 helpers, then a delivery ---------------------------------

HADES_MINERS = [(8, 15), (9, 15), (9, 16), (6, 17), (9, 17), (6, 18), (7, 18), (8, 18)]       # FUN_00546E80
HADES_GOD, HADES_FACE = (9, 18), (8, 17)
ATHENA_GROWERS = [(-4, 12), (-3, 12), (-2, 12), (-1, 12), (4, 12), (5, 12), (6, 12), (7, 12)]  # FUN_00547250
ATHENA_GOD, ATHENA_FACE = (0, 12), (-1, 11)
GIFT = 1600                                          # 0x640 of olives and of oil (Athena)
SILVER = 3200                                        # 0xC80 drachmas (Hades)


def _friendly_city_draw(g):
    """hades_help's world-city loop: True = help. The first city in use, class 0 / 3 (ours: ally / vassal), attitude
    >= 50 and not extorted -> a 50 % draw (rng_a & 1 set = no help); none -> help."""
    e = getattr(g, "empire", None)
    cities = getattr(e, "cities", None) if e is not None else None
    for c in (cities.values() if isinstance(cities, dict) else cities or []):
        rel = getattr(c, "relation", None) if not isinstance(c, dict) else c.get("relation")
        att = getattr(c, "attitude", None) if not isinstance(c, dict) else c.get("attitude")
        if rel in ("ally", "vassal") and (att or 0) >= 50:
            from . import rng
            return rng(g).randrange(2) == 0
    return True


def hades(g, i, prayed):
    from .help import busy, _queue, _granted
    palace = next((b for b in g.buildings.values() if b.key == "palace"), None)
    if busy(g, i) or palace is None:
        return _queue(g, i, prayed) if prayed else None
    if not prayed:
        if g.city.treasury >= 1 or not _friendly_city_draw(g):
            return
    _start_spot(g, i, "hades", HADES_GOD, HADES_FACE, HADES_MINERS, "miner")
    _granted(g, i, prayed)


def athena(g, i, prayed):
    from .help import busy, _queue, _granted, room_for
    from ..systems import index
    if busy(g, i):
        return _queue(g, i, prayed) if prayed else None
    if not prayed:
        stock = sum(s.goods.get("olives", 0) + s.goods.get("olive_oil", 0) for s in index.of(g, "storage"))
        if stock >= 400 or not any(h.level >= 5 for h in index.of(g, "house")):
            return
    for good in ("olive_oil", "olives"):
        if good in g.cat.resources and room_for(g, good) < GIFT:
            return _queue(g, i, prayed) if prayed else None
    _start_spot(g, i, "athena", ATHENA_GOD, ATHENA_FACE, ATHENA_GROWERS, "grower")
    _granted(g, i, prayed)


def _start_spot(g, i, task, god_at, face_at, helpers, kind):
    """god_figure_spawn at the sanctuary + the god's 0x2C / 0x25: the helpers out, the god to its spot."""
    from . import figures
    b = sanctuary(g, i)
    w = figures.figure(g, i)
    if w is None:
        w = figures._spawn(g, i, b.x, b.y, task, home=b.id)
    W = _W()
    w.task, w.st, w.state, w.anim_kind = task, "walk", "", ""
    w.dest, w.face_tile = spot(b, *god_at), spot(b, *face_at)
    w.path = _inner_path(g, b, (w.x, w.y), w.dest)
    w.helpers, lead = [], w.id
    for k, (dx, dy) in enumerate(helpers):
        h = W.new_walker(g, role="god_helper", home=0, x=w.x, y=w.y, good=kind)
        h.god, h.leader, h.sanct = i, lead, b.id
        h.dest, h.face_tile = spot(b, dx, dy), spot(b, *(face_at if kind == "miner" else (dx, dy - 1)))
        h.st, h.t0 = ("wait", g.tick) if kind == "grower" else ("walk", g.tick)
        h.path = _inner_path(g, b, (h.x, h.y), h.dest) if kind == "miner" else []
        W.add(g, h, max(1, (5 - k) * 10) if kind == "grower" else 1)  # 0x11: (5 - k) * 10 ticks (< 1: at once)
        w.helpers.append(h.id)
        lead = h.id
    W.schedule(g, w, 1)


def _helpers_out(g, w):
    """FUN_004C4D20 / FUN_004C4EF0: a helper still walking to its spot or working."""
    return any(h.st in ("wait", "walk", "work") for h in (g.walkers.get(k) for k in w.helpers)
               if h is not None and h.role == "god_helper")


def _spot_god(g, w):
    """Hades 0x2D..0x30 / Athena 0x26..0x29."""
    W = _W()
    from .figures import tile_ticks, _go_home
    if w.st == "walk":                                       # 0x2D / 0x26
        if w.path:
            W.step_to(g, w, w.path.pop(0))
            return W.schedule(g, w, tile_ticks(g, w))
        w.st, w.anim_t0, w.anim_kind = "wait", g.tick, "cast"
        w.face = (w.face_tile[0] - w.x, w.face_tile[1] - w.y)
        return W.schedule(g, w, 100)                         # 0x2E / 0x27: +1 a tick, > 99
    if w.st == "wait":                                       # 0x2F / 0x28: every 30 ticks
        w.st = "check"
        return W.schedule(g, w, 31)
    if w.st == "check":
        if _helpers_out(g, w):
            return W.schedule(g, w, 31)
        w.anim_kind = ""
        if w.task == "hades":
            to = next((b for b in sorted(g.buildings.values(), key=lambda b: b.id) if b.key == "palace"), None)
        else:
            to = _olive_store(g)
        if to is None:
            return _go_home(g, w)
        w.to, w.st = to.id, "deliver"
        goal = tuple(to.access) if to.access else (to.x, to.y)
        w.dest = goal
        w.path = W.land_path(g, (w.x, w.y), {goal}, max_dist=W.ROUTE_MAX) or []
        return W.schedule(g, w, 1)
    if w.st == "deliver":                                    # 0x30 / 0x29
        if w.path:
            W.step_to(g, w, w.path.pop(0))
            return W.schedule(g, w, tile_ticks(g, w))
        to = g.buildings.get(w.to)
        if w.task == "hades":
            g.city.treasury += SILVER                         # treasury and the year's god income (0x00FEAEB0)
            g.city.__dict__["god_income"] = g.city.__dict__.get("god_income", 0) + SILVER
            log(g, f"{NAMES[w.god]} brings {SILVER} drachmas of silver")
        elif to is not None:
            from ..systems import economy
            got, left = [], []
            for good in ("olive_oil", "olives"):
                n = 0
                if good in g.cat.resources:
                    n = min(GIFT, economy.storage_room(g, to, good))
                    to.goods[good] = to.goods.get(good, 0) + n
                    got.append(f"{n} {good}")
                left.append(GIFT - n)
            from .help import gift_leftover                  # 0x29: the rest through god_gifts_deliver
            gift_leftover(g, w.god, *left)
            log(g, f"{NAMES[w.god]} brings {', '.join(got)} to the {g.cat.spec(to.key)['name']} at ({to.x},{to.y})")
        return _go_home(g, w)                                # 0x14
    return _go_home(g, w)


def _olive_store(g):
    """FUN_004C46D0(olives, 1600, oil, 1600): the storehouse (type 0x3A) with the most room for both."""
    return _store_for(g, ("olives", "olive_oil"))


def helper_act(g, h):
    """A miner (figure_miner, composite) or a grower (0x004AECF0) of a helping god."""
    W = _W()
    from ..military.units import tile_ticks
    from . import figures
    god = figures.figure(g, h.god)
    if god is None or god.task not in ("hades", "athena"):
        return W.remove(g, h)
    speed = 7 if h.good == "grower" else 6                  # the grower walks at the god's speed (+0x59)
    if h.st == "wait":                                       # grower 0x11
        b = g.buildings.get(h.sanct)
        h.st, h.path = "walk", _inner_path(g, b, (h.x, h.y), h.dest) if b else []
        return W.schedule(g, h, 1)
    if h.st == "walk":                                       # 10 / 0xE
        if h.path:
            W.step_to(g, h, h.path.pop(0))
            return W.schedule(g, h, tile_ticks(g, h, speed))
        h.st, h.t0 = "work", g.tick
        h.face = (h.face_tile[0] - h.x, h.face_tile[1] - h.y)
        return W.schedule(g, h, 408 if h.good == "miner" else 100)   # 0xB 0x198 ticks / 0xF 100
    if h.st == "work":
        h.st = "follow"
    if h.st == "follow":                                     # 0xC / 0x10
        if god.st in ("wait", "check", "walk"):
            lead = g.walkers.get(h.leader)
            if lead is not None and max(abs(lead.x - h.x), abs(lead.y - h.y)) > 1:
                b = g.buildings.get(h.sanct)
                p = _inner_path(g, b, (h.x, h.y), (lead.x, lead.y)) if b else []
                if p and len(p) > 1:
                    W.step_to(g, h, p[0])
                    return W.schedule(g, h, tile_ticks(g, h, speed))
            return W.schedule(g, h, 8)
        if h.good == "grower" or god.st != "deliver":        # a grower: gone once Athena leaves 0x27..0x29
            return W.remove(g, h)
        if not h.path or h.path[-1] != tuple(god.dest):      # a miner: after Hades to the palace, gone there
            h.path = W.land_path(g, (h.x, h.y), {tuple(god.dest)}, max_dist=W.ROUTE_MAX) or []
            if not h.path:
                return W.remove(g, h)
        W.step_to(g, h, h.path.pop(0))
        if not h.path:
            return W.remove(g, h)
        return W.schedule(g, h, tile_ticks(g, h, 6))
    return W.remove(g, h)


def helper_look(g, h):
    if getattr(h, "st", "") != "work":
        return None
    f = getattr(h, "face", None) or (0, 1)
    f = ((f[0] > 0) - (f[0] < 0), (f[1] > 0) - (f[1] < 0))
    blk = "mine_silver" if h.good == "miner" else "tend_olives"
    return ["work", h.t0, h.t0 + (408 if h.good == "miner" else 100), f[0], f[1], 0, 0, 0, blk, False]


def act(g, w):
    if w.task == "strike":
        return _strike(g, w)
    if w.task == "precinct":
        return _aphro(g, w)
    if w.task in ("hades", "athena"):
        return _spot_god(g, w)
    if w.task == "wine":
        return _wine(g, w)
    if w.task == "hera":
        return _hera(g, w)
    from .figures import _leave
    return _leave(g, w)


def look(g, w):
    f = getattr(w, "face", None) or (0, 1)
    f = ((f[0] > 0) - (f[0] < 0), (f[1] > 0) - (f[1] < 0))
    k = getattr(w, "anim_kind", "")
    i = w.god
    # every help look is rate 100 (0x0F vanish, 0x10 appear, 0x11 attack, 0x13 / 0x1A / 0x24 / 0x27 / 0x2E cast)
    blk = {"vanish": (1, "vanish_gated"), "appear": (3, "appear"), "attack": (2, "attack"), "cast": (4, "cast")}.get(k)
    if blk is None or w.path:
        return None
    return ["work", w.anim_t0, w.anim_t0 + dur(i, blk[0]), f[0], f[1], 0, 0, 0, blk[1], False]


# --- Hephaestus -------------------------------------------------------------------------------------------------------

def _strengths(g):
    """FUN_005687A0 (ours): (the strongest enemy army's count x weight, the city's soldiers' count x weight)."""
    best = 0
    t = _army_target(g)
    if t is not None:
        from ..military import invaders
        inv = invaders.invasions(g)[t[0]]
        for cid in inv.get("companies", []):
            comp = invaders.ecomps(g).get(cid)
            if comp is not None:
                best += len(invaders.alive_members(g, comp)) * WEIGHT.get(comp.get("cls"), 1)
    mine = sum({"hoplite": 1, "horseman": 3, "rabble": 1}.get(w.role, 0) for w in g.walkers.values())
    return best, mine


def hephaestus(g, i, prayed):
    """hephaestus_help 0x004E7E70 (no god figure): need (automatic) an enemy army at least as strong as the city's;
    his monster (god_monster: Talos) when it is not on the map: monster_spawn at the sanctuary (sim/heroes guardian),
    actions 0x14 / 0x10; else a prayer is queued."""
    from .help import _queue, _granted
    if not prayed:
        enemy, mine = _strengths(g)
        if enemy <= 0 or enemy < mine:
            return
    try:
        from .. import heroes
    except ImportError:
        return
    b = sanctuary(g, i)
    w = heroes.guardian(g, i, b) if b is not None else None
    if w is None:
        return _queue(g, i, prayed) if prayed else None
    _granted(g, i, prayed)
    from .. import alerts                        # FUN_0040FF80(5, 0, tile): the god alert's tile = Talos
    alerts.set_first(g, (w.x, w.y))
    log(g, f"{NAMES[i]} sends Talos")


# --- Hera -------------------------------------------------------------------------------------------------------------

def _vendor_good(g, s):
    """The vendor's agora stock slot as hera_help / FUN_004C59A0 map it (g_vendor_goods_table +0x10 -> resource):
    the food vendor's slot 0 is wheat (7); the others their good."""
    good = g.cat.spec(s.key).get("goods")
    return "wheat" if good == "food" else good


def hera_need(g):
    """hera_help's need (automatic): of every vendor (stall) in use, the ones whose agora wants more of their good
    (agora_wants 0x0040CA40 with flag 1: food < 400, armour / horses / chariots < 300, else < 200) and whose last
    buyer call found no supply (+0xE0 != 0: no supply / too distant / stockpiled; ours: the stall's reason) make
    at least half."""
    from ..systems import index, agora
    n = k = 0
    for s in sorted(index.of(g, "stall"), key=lambda b: b.id):
        if s.key == "empty_stall":
            continue
        a = agora.agora_of(g, s)
        if a is None:
            continue
        n += 1
        good = g.cat.spec(s.key).get("goods")
        want = agora.food_total(g, a) < 400 if good == "food" else agora.wants(g, a, good)
        if want and s.reason:
            k += 1
    return n > 0 and k * 100 // n >= 50


def hera(g, i, prayed):
    """hera_help 0x004E8430: need (automatic) hera_need; Hera out of her sanctuary, action 0x31 (FUN_004C58A0): the
    agora nearest to her (FUN_004C57C0 over the agoras, FUN_004D7D10), a tile of it (FUN_0040BEE0); 0x32 walk there;
    0x24 100 ticks (the bless effect at the attack frame, presentation), then FUN_004C59A0 (hera_bless); 0x0B home.
    The help message at the agora's tile (none: -1)."""
    from .help import busy, _queue, _granted
    from ..systems import index
    if busy(g, i):
        return _queue(g, i, prayed) if prayed else None
    if not prayed and not hera_need(g):
        return
    b = sanctuary(g, i)
    from . import figures
    w = figures.figure(g, i)
    if w is None:
        w = figures._spawn(g, i, b.x, b.y, "hera", home=b.id)
    ags = sorted(index.of(g, "agora"), key=lambda a: (max(abs(a.x - w.x), abs(a.y - w.y)), a.id))
    to = ags[0] if ags else None
    W = _W()
    w.task, w.st, w.state = "hera", "walk", ""
    w.to = to.id if to is not None else 0
    w.dest = tuple(to.access) if to is not None and to.access else (w.x, w.y)
    w.path = (W.land_path(g, (w.x, w.y), {w.dest}, max_dist=W.ROUTE_MAX) or []) if to is not None else []
    W.schedule(g, w, 1)
    _granted(g, i, prayed, tile=(to.x, to.y) if to is not None else (w.x, w.y))


def hera_bless(g):
    """FUN_004C59A0: every vendor in use with workers (+0x40) adds to its agora's stock of its good: 800 with 1..3
    such vendors, 600 with 4, 500 with 5, 400 with 6..7, 300 with 8..10, 200 with 11..15, 100 with 16+; the stock at
    most 1100 for a food, 800 for the others. Returns the vendors served."""
    from ..systems import index, agora
    vs = [s for s in sorted(index.of(g, "stall"), key=lambda b: b.id)
          if s.key != "empty_stall" and s.employees and agora.agora_of(g, s) is not None]
    n = len(vs)
    add = 800 if n < 4 else 600 if n < 5 else 500 if n < 6 else 400 if n < 8 else 300 if n < 11 else \
        (200 if n < 16 else 100)
    for s in vs:
        a, good = agora.agora_of(g, s), _vendor_good(g, s)
        cap = 1100 if g.cat.is_food(good) else 800
        a.goods[good] = min(cap, a.goods.get(good, 0) + add)
    return n


def _hera(g, w):
    W = _W()
    from .figures import tile_ticks, _go_home
    if w.st == "walk":                                       # 0x32
        if w.path:
            W.step_to(g, w, w.path.pop(0))
            return W.schedule(g, w, tile_ticks(g, w))
        w.st, w.anim_t0, w.anim_kind = "wait", g.tick, "cast"
        return W.schedule(g, w, 100)                         # 0x24: +1 a tick, > 99
    n = hera_bless(g)
    log(g, f"{NAMES[w.god]} fills {n} vendors' stock")
    w.anim_kind = ""
    return _go_home(g, w)


HELPERS = {0: zeus, 3: apollo, 6: aphrodite, 8: athena, 9: hephaestus, 10: dionysus, 11: hades, 12: hera}

__all__ = ["HELPERS", "act", "look", "BUSY", "rec"]
