"""Priests and sacrifices (sanctuary_priests_update 0x004E97D0, priest figure 0x41 handler 0x004CA350 and its
helpers 0x004E9930 / 0x004E99F0 / 0x004EA1A0). docs/logic/religion.md.

Spawn (daily, from sanctuary_update, staffed sanctuaries only): activity < 20, the altar not in a sacrifice, fewer
priests out than the god's count (0x004EA330: Zeus, Poseidon, Hades, Hera 3; Demeter, Apollo, Artemis, Athena,
Atlas 2; the others 1), full staff (0x004E9770): a priest at the temple's road tile.
A priest looks for an offering (0x004E9930): a sheep, goat or bull (the lowest figure id, alive, not taken by
another priest), else a cow; he walks to it; a sheep or goat is killed and carried,
cattle follow him. With no animal: the first granary (or storehouse / trading post) holding 400 food (foods not
stockpiled), 400 taken out (a cart follows him). Nothing found: the priest is deleted. Then to the altar's road
tile: the sacrifice (0x004EA1A0) sets the activity to 24; the priest and the offering are gone. Ours: every
arriving priest sacrifices (the exe waits until all priests sent have arrived; religion.md "Priest").
"""
from . import T, state, GODS
from .month import log

LOAD = 400
SEARCH_EVERY = 10                     # action 6: timer counts up from 10 at spawn; the search runs past 10


def _pieces(g, b):
    from ..systems import monuments
    ps = b.misc.get("pieces") or []
    temple = next((p for p in ps if p["c"] in monuments.TEMPLES), None)
    altar = next((p for p in ps if p["c"] == 2), None)
    return temple, altar


def _tile(g, b, p):
    from ..systems import monuments
    if p is None:
        return monuments.road_entry(g, b)
    return monuments.work_tile(g, b, p) or monuments.road_entry(g, b)


def update(g, b, i):
    m = b.misc
    if m.get("activity", 0) >= 20:
        return
    if m.get("sacrificing"):
        return
    out = [w for w in b.walkers if w in g.walkers and g.walkers[w].role == "priest"]
    if len(out) >= T()["priests"][i]:
        return
    if b.employees < g.cat.spec(b.key)["employees"]:
        return
    temple, _ = _pieces(g, b)
    t = _tile(g, b, temple)
    if t is None:
        return
    from ..systems import walkers
    w = walkers.new_walker(g, role="priest", home=b.id, x=t[0], y=t[1], state="search")
    b.walkers.append(w.id)
    walkers.add(g, w, 2)


def _offering_animal(g):
    """priest_find_animal 0x004E9D90: the first figure (id order) alive and not taken by a priest that is a sheep,
    a goat or a bull (cattle subtype 2); else the first cow (subtype 3)."""
    taken = {w.target for w in g.walkers.values() if w.role == "priest" and w.state == "animal"}
    cow = None
    for a in sorted(g.walkers.values(), key=lambda a: a.id):
        if a.id in taken or a.anim == "die" or a.state in ("carcass", "struck", "held", "led"):
            continue
        if a.role in ("sheep", "goat") or (a.role == "cattle" and getattr(a, "bull", False)):
            return a
        if a.role == "cattle" and cow is None:
            cow = a
    return cow


def _offering_store(g):
    """0x004EA060: the first granary (by building id) with >= 400 food, else a storehouse / trading post holding
    >= 400 of foods (stockpiled foods do not count)."""
    from ..systems import economy
    for s in sorted(g.buildings.values(), key=lambda s: s.id):
        if s.kind not in ("storage", "trade") or s.access is None:
            continue
        n = sum(v for k, v in s.goods.items() if g.cat.is_food(k) and not economy.stockpiled(g, k))
        if n >= LOAD:
            return s
    return None


def _take(g, s):
    """0x004E9E50: 400 food out of the store (foods in order); the good taken most names the load."""
    from ..systems import economy
    left, best, most = LOAD, None, 0
    for k in g.cat.foods:
        if economy.stockpiled(g, k):
            continue
        n = min(left, s.goods.get(k, 0))
        if n > 0:
            s.goods[k] -= n
            if not s.goods[k]:
                del s.goods[k]
            left -= n
            if n > most:
                best, most = k, n
        if not left:
            break
    return best if left == 0 else None


def _walk(g, w, goal):
    from ..systems import walkers
    if (w.x, w.y) == goal:
        w.path = []
        return True
    from ..systems import monuments
    p = monuments.route(g, (w.x, w.y), tuple(goal))     # route mode 13: roads, sanctuary ground, then land
    if p is None:
        return False
    w.path = p
    return True


def act(g, w):
    from ..systems import walkers
    b = g.buildings.get(w.home)
    if b is None:
        return _gone(g, w)
    if w.state == "search":
        a = _offering_animal(g)
        if a is not None and _walk(g, w, (a.x, a.y)):
            w.state, w.target, w.target_tile = "animal", a.id, (a.x, a.y)
            return walkers.schedule(g, w, 1)
        s = _offering_store(g)
        if s is not None and _walk(g, w, tuple(s.access)):
            w.state, w.target = "store", s.id
            return walkers.schedule(g, w, 1)
        return _gone(g, w)                           # nothing to offer: the priest is deleted at once
    if w.state == "animal":
        a = g.walkers.get(w.target)
        if a is None or a.anim == "die":
            w.state, w.path = "search", []
            return walkers.schedule(g, w, 1)
        if (a.x, a.y) == (w.x, w.y):
            if a.role == "cattle":                    # led to the altar (cattle action 0x14 / 0x15)
                a.state, a.led_by = "held", w.id
                w.good = "cattle"
            else:                                     # killed and carried
                w.good = a.role
                walkers.remove(g, a)
            return _to_altar(g, w, b)
        if (a.x, a.y) != w.target_tile:               # it moved: walk to where it is now
            w.target_tile = (a.x, a.y)
            if not _walk(g, w, w.target_tile):
                return _gone(g, w)                   # a lost route deletes the priest
        return _step(g, w)
    if w.state == "store":
        s = g.buildings.get(w.target)
        if s is None:
            w.state, w.path = "search", []
            return walkers.schedule(g, w, 1)
        if not w.path:
            good = _take(g, s)
            if good is None:
                w.state = "search"
                return walkers.schedule(g, w, 1)
            w.good, w.amount = good, LOAD
            return _to_altar(g, w, b)
        return _step(g, w)
    if w.state == "altar":
        if not w.path:
            return _sacrifice(g, w, b)
        return _step(g, w)
    if w.state == "home":
        if not w.path:
            return _gone(g, w)
        return _step(g, w)
    return _gone(g, w)


def _step(g, w):
    from ..systems import walkers
    old = (w.x, w.y)
    walkers.step_to(g, w, w.path.pop(0))
    led = g.walkers.get(getattr(w, "leads", 0) or 0)
    if led is not None:
        led.prev, (led.x, led.y), led.arrived = (led.x, led.y), old, g.tick
        walkers.listed(g, led)
    return walkers.schedule(g, w, walkers.tile_delay(g, w))


def _to_altar(g, w, b):
    from ..systems import walkers
    _, altar = _pieces(g, b)
    if w.good == "cattle":
        w.leads = w.target
    w.state = "altar"
    if not _walk(g, w, _tile(g, b, altar)):
        return _gone(g, w)
    return walkers.schedule(g, w, 1)


def _sacrifice(g, w, b):
    """priest_sacrifice_done 0x004EA1A0: the sanctuary's activity = 24."""
    from ..systems import walkers
    b.misc["activity"] = 24
    led = g.walkers.get(getattr(w, "leads", 0) or 0)
    if led is not None:
        walkers.remove(g, led)
    log(g, f"sacrifice ({w.good}) at the sanctuary of {GODS[_god(b)]}")
    w.good, w.amount, w.leads = "", 0, 0
    return _gone(g, w)                               # the priest is deleted with the offering (never walks home)


def _god(b):
    from . import god_of
    return god_of(b)


def _gone(g, w):
    from ..systems import walkers
    led = g.walkers.get(getattr(w, "leads", 0) or 0)
    if led is not None and getattr(led, "led_by", 0) == w.id:
        led.state, led.led_by = "idle", 0
    walkers.remove(g, w)


def look(g, w):
    return None


__all__ = ["update", "act", "state"]
