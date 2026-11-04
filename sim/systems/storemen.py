"""Storage walkers (docs/logic/storage-distribution.md §7, §8.1): the storehouse's deliveryman and the storehousemen.

- Deliveryman (figure 0x24, handler figure_deliveryman 0x004B87C0): ONE per storehouse (slot Building+0xB6). Only
  while that slot is empty does the storehouse (storage_spawn_walkers 0x005B4B40, daily step 31) pick a good:
  storehouse_pick_for_workshop 0x0048AAC0 = the first workshop in building order with workers, not halted, on the
  storehouse's road network, whose input the storehouse holds (not stockpiled) and that accepts it now
  (workshop_accepts_input 0x0048A880). The man leaves with min(stock, 400) of it (taken out at once), searches on
  his 3rd call (find_workshop_for_input 0x0048BC80: the ranking below, then nearest by road; it reserves), unloads on
  the 5th call at the workshop (workshop_add_input 0x0048C410: up to its cap), and with a rest searches again (3
  calls); with nothing to do he goes home, puts the rest back (storehouse_add_goods 0x004895B0) and is gone; when
  the storehouse refuses it he stands at home and searches every few ticks, still holding the slot.
- Storehousemen (figure 9, handler figure_storehouseman 0x004B0080): granaries and storehouses at >= 50 % staff, at
  most two (slots +0x2A, +0xB8). Get: storage_get_targets 0x00489E60 (the two Get goods lowest in stock/limit % that
  have a source) and storage_get_worker_plan 0x0048CA00 decide one or two; each walks out empty, picks the nearest
  source (storage_find_source 0x0048A140), takes up to 400 there on the 5th call, brings it home. Empty (only when no
  Get target): one man in +0x2A carries min(stock, 400) of the first Empty good to a workshop, granary or storehouse
  (storage_walker_find_destination 0x004CDAC0), unloading on the 5th call. A rest goes on by cart_find_destination
  (walker_after_unload 0x004CD870).
- Trading posts' storehousemen (0x005B5620, one per traded good, slots +0xBC + 2i) are the same figure: an export
  good's man fetches (Get, his good fixed), an import good's man pushes out (Empty).

Ours: the walkers are role "cart" with task deliver / get / empty (the play client draws them as carts; fig_type
in sim/live.py names 36 for any cart from a storage). Bays are not modelled: "the first bay" is the first good in
the storage's goods dict. FUN_0048BFE0 (the last fallback of both destination searches: any workshop of the input's
type) routes to the building's own tile (+6 / +8), not its road tile; a road route never ends there: never taken
(oracle sanctuary-build tick 1580: a deliveryman with 300 grapes, every winery full, went home).
"""
from . import economy, labor, roads

TASKS = ("deliver", "get", "empty")
STATES = ("search", "dest", "fetch", "take", "go", "unload", "back", "home")
SEARCH = 3          # action 6: timer > 2, the 3rd handler call searches
UNLOAD = 5          # action 8 / 0xC: timer > 4, the 5th call unloads (takes)
LOAD = 400
WORKSHOPS = ("workshop", "ranch", "shipyard")


def _spec(g, b):
    return g.cat.spec(b.key)


def granary(g, s):
    return s.kind == "storage" and _spec(g, s).get("accepts") == "food"


def storehouse(g, s):
    return s.kind == "storage" and _spec(g, s).get("accepts") != "food" and not _spec(g, s).get("endless")


def staff_pct(g, b):
    """workers * 100 / model employees (0 without a model value)."""
    need = _spec(g, b).get("employees") or 0
    return b.employees * 100 // need if need > 0 else 0


def _net(g, tile):
    return int(g.world.road_net[tile[1], tile[0]])


def limit(g, s, good):
    return s.misc.get("limits", {}).get(good, _spec(g, s)["capacity"])


# --- workshops ---------------------------------------------------------------------------------------------------

def pending(g):
    """{building id: {good: [carts, amount]}}: Building+0x114 / +0x116 (0x88 armor: +0xF0 / +0xF2), the reservations
    find_workshop_for_input / find_granary make and the unload releases; ours counts the carts on their way."""
    out = {}
    for w in g.walkers.values():
        if w.role == "cart" and w.target and w.amount > 0:
            d = out.setdefault(w.target, {}).setdefault(w.good, [0, 0])
            d[0] += 1
            d[1] += w.amount
    return out


def cap(g, u):
    return _spec(g, u).get("input_cap", 300)


def accepts(g, u, good, pend):
    """workshop_accepts_input 0x0048A880: its input, stock < cap, and with carts on their way room after them."""
    if good not in economy.inputs(g, u):
        return False
    c, have = cap(g, u), u.goods.get(good, 0)
    if have >= c:
        return False
    n, amt = pend.get(u.id, {}).get(good, (0, 0))
    return not (n > 0 and c - amt - have < 1)


def find_workshop(g, start, good, pend=None):
    """find_workshop_for_input 0x0048BC80: not if stockpiled; workshops (any staff) not halted, with access, on the
    road network of start, that accept the good. Ranking (the exe's quirk): keys k1 = carts on their way, k2 = stock;
    a workshop is kept only if k1 <= best1 and k2 <= best2; a lower k2 clears the list and sets both bests, an equal
    k2 appends it. Then the nearest by road among the list. Returns (building, path) or (None, None)."""
    if economy.stockpiled(g, good) or start is None:
        return None, None
    pend = pending(g) if pend is None else pend
    net = _net(g, start)
    best1 = best2 = 10000
    keep = []
    for u in sorted(g.buildings.values(), key=lambda b: b.id):
        if u.kind not in WORKSHOPS or u.access is None or u.network != net or good not in economy.inputs(g, u):
            continue
        if labor.halted(g, u) or not accepts(g, u, good, pend):
            continue
        k1, k2 = pend.get(u.id, {}).get(good, (0, 0))[0], u.goods.get(good, 0)
        if k1 <= best1 and k2 <= best2:
            if k2 < best2:
                keep, best1, best2 = [], k1, k2
            keep.append(u)
    return roads.nearest(g, start, keep)


def pick_for_workshop(g, s, pend):
    """storehouse_pick_for_workshop 0x0048AAC0: any staff; workshops in building order with workers (+0x40), not
    halted, on the storehouse's network; the first stored good (stock > 0, not stockpiled) the workshop accepts."""
    if staff_pct(g, s) == 0 or s.access is None:
        return None
    for u in sorted(g.buildings.values(), key=lambda b: b.id):
        if u.kind not in WORKSHOPS or u.employees <= 0 or labor.halted(g, u) or u.network != s.network:
            continue
        for good, n in s.goods.items():
            if n > 0 and not economy.stockpiled(g, good) and accepts(g, u, good, pend):
                return good
    return None


# --- sources and destinations --------------------------------------------------------------------------------------

def find_source(g, b, good, first_only=False, need_min=False, minimum=LOAD, start=None):
    """storage_find_source 0x0048A140(b, good, first_only, need_min, min) -> storage building or None. Not if stockpiled
    unless b's own order is Get; same road network unless b is a storage on Get. Storehouses and posts (posts: only
    imports; exporting and untraded posts are no source): stock >= 1 (sculpture >= 400, need_min: >= min), a
    storehouse on Get only when need_min; granaries: food, >= 400, not on Get. first_only: the first in record order;
    else the nearest by road (b on Get: by land when no road reaches one). No staff test."""
    from . import trade
    get = b.kind == "storage" and economy.order(g, b, good) == "get"
    if not get and economy.stockpiled(g, good):
        return None
    start = start or b.access
    if start is None:
        return None
    net = _net(g, start)
    food = g.cat.is_food(good)
    cands = []
    for s in sorted(g.buildings.values(), key=lambda x: x.id):
        if s.kind not in ("storage", "trade") or s is b or s.access is None or _spec(g, s).get("endless"):
            continue
        if not get and s.network != net:
            continue
        n = s.goods.get(good, 0)
        if granary(g, s):
            if not food or n < LOAD or economy.order(g, s, good) == "get":
                continue
        else:
            if s.kind == "trade" and trade.order(g, s, good) != "import":
                continue
            if (good == "sculpture" and n < 400) or (need_min and n < minimum) or n < 1:
                continue
            if s.kind == "storage" and economy.order(g, s, good) == "get" and not need_min:
                continue
        cands.append(s)
    if first_only or not cands:
        return cands[0] if cands else None
    src, _ = roads.nearest(g, start, cands)
    if src is None and get:                       # route_find_listed_tile: over land
        from . import walkers
        best = None
        for s in cands:
            p = walkers.route3(g, start, s.access)
            if p is not None and (best is None or len(p) < best[0]):
                best = (len(p), s)
        src = best[1] if best else None
    return src


def has_room(g, s, good):
    """storehouse_has_room 0x005B4670: not full, and not (the good's stock a whole number of bays with every bay used)."""
    held = {k: v for k, v in s.goods.items() if v > 0}
    if sum(held.values()) >= _spec(g, s)["capacity"]:
        return False
    used = sum(-(-v // economy.BAY) for v in held.values())
    return not (held.get(good, 0) % economy.BAY == 0 and used >= economy.bays(g, s))


def goods_list(g, s):
    """storage_goods_list 0x005B12C0 order (resource id order), the goods this storage handles."""
    return [k for k in g.cat.resources if economy.holds(g, s, k)]


def get_pct(g, s, good):
    """storage_get_targets: stock * 100 / limit of a Get good, 100 when full (storehouse: no room) or at the limit."""
    lim, n = limit(g, s, good), s.goods.get(good, 0)
    if granary(g, s):
        free = _spec(g, s)["capacity"] - sum(v for v in s.goods.values() if v > 0)
        return n * 100 // lim if free != 0 and n < lim and lim > 0 else 100
    if not has_room(g, s, good):
        return 100
    return n * 100 // lim if n < lim and lim > 0 else 100


def get_targets(g, s):
    """storage_get_targets 0x00489E60 -> (g1, g2, pct1, pct2, src1, src2): the two Get goods with the lowest % (< 100)
    that have a source (storage_find_source first_only), in goods-list order on ties."""
    g1 = g2 = src1 = src2 = None
    p1 = p2 = 100
    for good in goods_list(g, s):
        if economy.order(g, s, good) != "get":
            continue
        pct = get_pct(g, s, good)
        if pct >= p2:
            continue
        src = find_source(g, s, good, first_only=True)
        if src is None:
            continue
        if pct < p1:
            p2, g2, src2 = p1, g1, src1
            p1, g1, src1 = pct, good, src
        else:
            p2, g2, src2 = pct, good, src
    return g1, g2, p1, p2, src1, src2


def worker_plan(p1, p2, n):
    """storage_get_worker_plan 0x0048CA00 -> (two, second_same, workers)."""
    two = same = workers = 0
    if n == 1:
        same = 1
        if p1 < 50:
            two, workers = 1, 2
        elif p1 < 100:
            workers = 1
    elif n == 2:
        if p1 > 100 and p2 > 100:
            two = same = workers = 0
        if p1 < 50 and p2 > 100:
            two, same, workers = 1, 1, 2
        if p1 < 100:
            if p2 > 100:
                two, same, workers = 0, 1, 1
            if p2 < 100:
                two, same, workers = 1, 0, 2
    return two, same, workers


def empty_target(g, s, g1):
    """granary_empty_target 0x0048AEB0 / storehouse_empty_target 0x0048A580: None (-1) under 50 % staff; 0 when a Get
    target exists (Get first); else the first Empty good held (storehouse: bay order, sculpture < 400 skipped;
    granary: food order); else None."""
    if staff_pct(g, s) < 50:
        return None
    if g1 is not None:
        for good in goods_list(g, s):
            if economy.order(g, s, good) == "get" and (granary(g, s) or s.goods.get(good, 0) <= limit(g, s, good)):
                return 0
    if granary(g, s):
        for good in goods_list(g, s):
            if economy.order(g, s, good) == "empty" and s.goods.get(good, 0) != 0:
                return good
        return None
    for good, n in s.goods.items():
        if n >= 1 and not (good == "sculpture" and n < 400) and economy.order(g, s, good) == "empty":
            return good
    return None


def can_dispose(g, s, good, amount):
    """0x005B4440: a workshop accepting it (0x005B4480: workers, not halted, same network) or a storage that can take
    the amount (0x005B4780: granary / storehouse / exporting post, staffed >= 50 %, same network, order and limit)."""
    pend = pending(g)
    for u in g.buildings.values():
        if u.kind in WORKSHOPS and u is not s and u.access is not None and u.network == s.network \
                and u.employees and not labor.halted(g, u) and accepts(g, u, good, pend):
            return True
    for t in g.buildings.values():
        if t.kind not in ("storage", "trade") or t is s or t.access is None or t.network != s.network \
                or _spec(g, t).get("endless"):
            continue
        from . import trade
        ok = trade.staffed(g, t) if t.kind == "trade" else staff_pct(g, t) >= 50
        if ok and economy.storage_room(g, t, good) > 0 and t.goods.get(good, 0) + amount <= \
                (trade.limit(g, t, good) if t.kind == "trade" else limit(g, t, good)):
            return True
    return False


def empty_destination(g, w, home):
    """storage_walker_find_destination 0x004CDAC0: workshop (find_workshop_for_input), granary (find_granary;
    stockpile ignored for a granary's own man, flag 0x100000), storehouse bay or exporting post (find_storehouse_bay,
    not home unless home is on Get); FUN_0048BFE0 never routes (module doc). (building, path) or (None, None)."""
    start = (w.x, w.y)
    dest, p = find_workshop(g, start, w.good)
    if dest is not None:
        return dest, p
    net = _net(g, start)
    by = economy.incoming_by_target(g)
    if g.cat.is_food(w.good) and (not economy.stockpiled(g, w.good) or (home is not None and granary(g, home))):
        gs = [s for s in g.buildings.values() if granary(g, s) and s.access is not None and s.network == net
              and staff_pct(g, s) >= 50 and economy.storage_room(g, s, w.good, by=by) >= 100]
        dest, p = roads.nearest(g, start, gs)
        if dest is not None:
            return dest, p
    from . import trade
    ss = [s for s in g.buildings.values() if (storehouse(g, s) or s.kind == "trade") and s.access is not None
          and s.network == net and (s is not home or economy.order(g, home, w.good) == "get")
          and (trade.staffed(g, s) if s.kind == "trade" else staff_pct(g, s) >= 50)
          and economy.storage_room(g, s, w.good, by=by) > 0]
    return roads.nearest(g, start, ss)


# --- spawning (storage_spawn_walkers 0x005B4B40, trade_post_spawn_walkers 0x005B5620) -------------------------------

def _slot(g, s, name):
    """The walker in a slot, if alive and still this building's (else the slot is cleared, as the exe's checks)."""
    wid = s.misc.get(name)
    w = g.walkers.get(wid) if wid else None
    if w is None or w.home != s.id or w.role != "cart" or w.task not in TASKS:
        s.misc.pop(name, None)
        return None
    return w


def _spawn(g, s, name, task, good, amount, delay=SEARCH):
    from . import walkers
    w = walkers.new_walker(g, role="cart", home=s.id, x=s.access[0], y=s.access[1], good=good, amount=amount,
                           task=task, state="search")
    s.walkers.append(w.id)
    walkers.add(g, w, delay)
    if name:
        s.misc[name] = w.id
    return w


def _take(s, good, n):
    s.goods[good] = s.goods.get(good, 0) - n
    if s.goods[good] <= 0:
        del s.goods[good]


def spawn(g):
    """Daily (step 31): every granary and storehouse."""
    pend = None
    for s in g.buildings.values():
        if s.kind != "storage" or s.access is None or _spec(g, s).get("endless"):
            continue
        if storehouse(g, s) and _slot(g, s, "dman") is None:
            pend = pending(g) if pend is None else pend     # a new man reserves nothing before his search
            good = pick_for_workshop(g, s, pend)
            if good is not None:
                n = min(s.goods[good], LOAD)
                _take(s, good, n)
                _spawn(g, s, "dman", "deliver", good, n)
        storehousemen(g, s)


def storehousemen(g, s):
    w1, w2 = _slot(g, s, "sman"), _slot(g, s, "sman2")
    if staff_pct(g, s) < 50 or (w1 and w2):
        return
    g1, g2, p1, p2, src1, src2 = get_targets(g, s)
    k = empty_target(g, s, g1)
    if s.reason.startswith("nowhere to empty") and (k is None or k == 0):
        s.reason = ""
    if k is None:
        return
    if k == 0:
        two, same, workers = worker_plan(p1, p2, (g1 is not None) + (g2 is not None))
        if not workers:
            return
        if two and w1:
            if w2 or (src1 if same else src2) is None:
                return
            _spawn(g, s, "sman2", "get", g1 if same else g2, 0)
            return
        if w1 or src1 is None:
            return
        _spawn(g, s, "sman", "get", g1, 0)
        return
    if w1:
        return
    n = min(s.goods.get(k, 0), LOAD)
    if not can_dispose(g, s, k, n):
        s.reason = f"nowhere to empty {k} to"
        return
    if s.reason.startswith("nowhere to empty"):
        s.reason = ""
    _take(s, k, n)
    _spawn(g, s, "sman", "empty", k, n)                 # a granary's: flags |= 0x100000 (empty_destination)


def post_spawn(g, t, good, mode):
    """A trading post's man for one traded good (0x005B5620, slot +0xBC + 2i): export -> fetch it (Get, good fixed);
    import -> push the stock out (Empty). The caller checks staff, stockpile and the slot."""
    slots = t.misc.setdefault("smen", {})
    if mode == "export":
        if find_source(g, t, good, first_only=True) is None:
            return None
        w = _spawn(g, t, None, "get", good, 0)
    else:
        n = min(t.goods.get(good, 0), LOAD)
        if n <= 0 or not can_dispose(g, t, good, n):
            return None
        _take(t, good, n)
        w = _spawn(g, t, None, "empty", good, n)
    slots[good] = w.id
    return w


def post_slot(g, t, good):
    wid = t.misc.get("smen", {}).get(good)
    w = g.walkers.get(wid) if wid else None
    if w is None or w.home != t.id:
        t.misc.get("smen", {}).pop(good, None)
        return None
    return w


# --- the walkers -------------------------------------------------------------------------------------------------

def _mine(g, w, home):
    """The home still has this walker in a slot (figure state 2 otherwise)."""
    if home is None:
        return False
    if w.task == "deliver":
        return home.misc.get("dman") == w.id
    if home.kind == "trade":
        return w.id in home.misc.get("smen", {}).values()
    return w.id in (home.misc.get("sman"), home.misc.get("sman2"))


def _gone(g, w):
    from . import walkers
    home = g.buildings.get(w.home)
    if home is not None:
        for k in ("dman", "sman", "sman2"):
            if home.misc.get(k) == w.id:
                home.misc.pop(k)
        for k, v in list(home.misc.get("smen", {}).items()):
            if v == w.id:
                home.misc["smen"].pop(k)
    walkers.remove(g, w)


def _route(g, w, goal):
    """Deliverymen walk the roads (route mode 1), storehousemen roads then land (mode 3)."""
    from . import walkers
    if w.task == "deliver":
        return roads.path(g, (w.x, w.y), {goal})
    return walkers.route3(g, (w.x, w.y), goal)


def _go(g, w, state, target, goal):
    """Set out for goal (the first step on the next tile time); True when on the way or already there."""
    from . import walkers
    p = _route(g, w, goal)
    if p is None:
        return False
    w.state, w.target, w.path = state, target, p
    w.returning = state in ("back", "home")
    walkers.schedule(g, w, walkers.tile_delay(g, w) if p else 1)
    return True


def _home(g, w, home):
    """Action 9 / 10: walk home (with or without a load)."""
    from . import walkers
    if home is None or home.access is None or not _go(g, w, "back" if w.amount else "home", 0, home.access):
        if w.amount and home is not None:
            w.state, w.target, w.path = "search", 0, []       # no way home: stand and search again
            return walkers.schedule(g, w, SEARCH)
        return _gone(g, w)


def act(g, w):
    from . import walkers
    home = g.buildings.get(w.home)
    if w.task != "deliver" and not _mine(g, w, home):      # 0x004B0080: home alive and the walker in its slots
        return _gone(g, w)
    st = w.state
    if st in ("fetch", "go", "back", "home") and w.path:
        if w.task == "deliver":                             # route mode 1: off the road -> gone
            road = walkers.road_list(g)
            nxt = w.path[0]
            if not road[w.y * 228 + w.x] or not road[nxt[1] * 228 + nxt[0]]:
                return _gone(g, w)
        walkers.step_to(g, w, w.path.pop(0))
        if w.path:
            return walkers.schedule(g, w, walkers.tile_delay(g, w))
    if st == "search":
        return search(g, w, home)
    if st == "dest":                                        # action 0xD (the call after action 6 for a loaded man)
        return destination(g, w, home)
    if st == "fetch":                                       # action 0xB arrived -> 0xC
        w.state = "take"
        return walkers.schedule(g, w, UNLOAD)
    if st == "go":                                          # action 7 arrived -> 8
        w.state = "unload"
        return walkers.schedule(g, w, UNLOAD)
    if st == "take":
        return take(g, w, home)
    if st == "unload":
        return unload(g, w, home)
    if st == "back":                                        # action 9 / 10 arrival with a load
        return at_home(g, w, home)
    return _gone(g, w)                                      # "home": back empty (state 2)


def search(g, w, home):
    """Action 6 (and 0xD for a loaded storehouseman)."""
    from . import walkers
    if w.task == "deliver":
        if home is None or home.misc.get("dman") != w.id:
            return _gone(g, w)
        dest, p = find_workshop(g, (w.x, w.y), w.good)
        if dest is None:
            return _home(g, w, home)
        w.state, w.target, w.path, w.returning = "go", dest.id, p, False
        return walkers.schedule(g, w, walkers.tile_delay(g, w) if p else 1)
    if w.amount <= 0:                                       # Get: the good and its nearest source now
        good = w.good
        if home.kind == "storage":
            g1, g2, *_ = get_targets(g, home)
            good = g2 if home.misc.get("sman2") == w.id and g2 is not None else g1
        src = find_source(g, home, good) if good else None
        if src is None:
            return _gone(g, w)
        w.good = good
        if not _go(g, w, "fetch", src.id, src.access):
            w.state = "search"
            return walkers.schedule(g, w, SEARCH)
        return
    w.state = "dest"                                        # loaded (Empty, or a rest): action 0xD next call
    walkers.schedule(g, w, 1)


def destination(g, w, home):
    dest, _ = empty_destination(g, w, home)
    if dest is None or not _go(g, w, "go", dest.id, dest.access):
        return _home(g, w, home)


def take(g, w, home):
    """Action 0xC: up to 400 from the source (storehouse_remove_goods / granary_remove_food, no order test)."""
    from . import walkers
    src = g.buildings.get(w.target)
    n = min(LOAD, src.goods.get(w.good, 0)) if src is not None else 0
    w.target = 0
    if n <= 0:
        w.state = "search"                                  # timer is 5: the next call searches
        return walkers.schedule(g, w, 1)
    _take(src, w.good, n)
    w.amount = n
    _home(g, w, home)


def put(g, dest, good, n):
    """Unload n of good into dest (storehouseman action 8 / deliveryman action 8 / either at home). Granary:
    granary_add_food 0x0048B680 (no staff test; refuses Don't accept only); storehouse / post: storehouse_add_goods
    0x004895B0 (nothing unstaffed or burning; order and limit); workshop: workshop_add_input 0x0048C410 (up to cap)."""
    if dest is None:
        return 0
    if dest.kind in WORKSHOPS:
        k = max(0, min(n, cap(g, dest) - dest.goods.get(good, 0))) if good in economy.inputs(g, dest) else 0
    elif dest.kind in ("storage", "trade"):
        food = granary(g, dest)
        if not food and (not dest.employees or dest.burning) and not _spec(g, dest).get("endless"):
            k = 0
        else:
            k = min(n, economy.storage_room(g, dest, good, arriving=True))
    else:
        k = 0
    if k > 0:
        dest.goods[good] = dest.goods.get(good, 0) + k
        if _spec(g, dest).get("endless"):
            sur = g.sd("surplus", {})
            sur[good] = sur.get(good, 0) + k
    return k


def unload(g, w, home):
    from . import walkers
    dest = g.buildings.get(w.target)
    w.target = 0                                            # the reservation is released
    if w.task == "deliver":
        k = put(g, dest, w.good, w.amount) if dest is not None and dest.kind in WORKSHOPS else 0
        if k == w.amount:
            w.amount = 0
            return _home(g, w, home)
        w.amount -= k
        w.state = "search"
        return walkers.schedule(g, w, SEARCH)
    k = put(g, dest, w.good, w.amount)
    after_unload(g, w, home, k, False)


def at_home(g, w, home):
    from . import walkers
    w.returning = False
    if w.task == "deliver":
        k = put(g, home, w.good, w.amount)
        if k == w.amount:
            return _gone(g, w)
        w.amount -= k
        w.state = "search"
        return walkers.schedule(g, w, SEARCH)
    k = put(g, home, w.good, w.amount)
    after_unload(g, w, home, k, True)


def after_unload(g, w, home, k, at_home_):
    """walker_after_unload 0x004CD870: all unloaded -> at home gone, else home empty (action 9); a rest -> the cart
    rule chain (cart_find_destination) from here, none -> action 6 (searching as an Empty man)."""
    from . import walkers
    if k == w.amount:
        w.amount = 0
        if at_home_:
            return _gone(g, w)
        return _home(g, w, home)
    w.amount -= k
    dest, _ = economy.cart_destination(g, (w.x, w.y), w.good, exclude=home)
    if dest is not None and _go(g, w, "go", dest.id, dest.access):
        return
    w.state, w.target, w.path = "search", 0, []
    walkers.schedule(g, w, SEARCH)
