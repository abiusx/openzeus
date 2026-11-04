"""Production, carts, storage, vendors (docs/logic/production.md, storage-distribution.md; simplified).

- harvest producers (farms): growth += staffing*10/100 per day up to farm_growth_max; in the
  harvest month the crop (up to 8 loads) goes to stock.
- herd/lodge/gather buildings send walkers out (walkers.py) who carry the goods back on foot.
- workshops: with >= 100 input, progress += staffing/10 per day; 320 -> 100 input becomes 100 output.
- a building with >= 100 of its output sends a cart to the nearest workshop that needs it, else the
  nearest storage with room (granary: food; storehouse: other goods).
- vendors send a buyer to the nearest storage holding their goods; their peddler hands goods to houses.
"""
import numpy as np

from . import index, labor, roads, shore


def _spec(g, b):
    return g.cat.spec(b.key)


def ladder(pct, values):
    """Pick by staffing: >=100, >=75, >=50, >=25, else (the original's 5-step ladders)."""
    return values[0 if pct >= 100 else 1 if pct >= 75 else 2 if pct >= 50 else 3 if pct >= 25 else 4]


def outputs(g, b):
    spec = _spec(g, b)
    if b.kind == "lodge":
        return [g.cat.spec(t)["output"] for t in spec["trees"]]
    if b.kind == "ranch" or spec.get("keeps_output"):     # horses stay; the mint coins its silver
        return []
    return [spec["output"]] if "output" in spec else []


# Building animation state (exe draw path; docs/play/buildings.md "Animations"). Read only, no graphics:
# the export passes it to the viewers. Stalled = staffed but the stock (exe Building+0x3C) is below the
# threshold: the exe then draws an idle worker figure instead of the work animation (0x0044EAB0).
STALL_BELOW = {0x35: 100, 0x36: 100, 0x37: 400,              # winery, olive press, sculpture studio
               0x30: 1, 0x32: 1, 0x33: 1, 0x85: 1, 0x87: 1}  # mint, foundry, timber mill, horse ranch, armory
VENUES = (0x50, 0x51, 0x52)                                   # stadium, podium, theatre: only with shows


def anim_state(g, b):
    """"work" (play the building's animation), "idle" (staffed but stalled: idle worker figure) or None
    (base image only). exe: animation_frame_step 0x00413380 (no frame without workers when the type needs
    labour; venues 0x50..0x52 also need shows), city_draw 0x00459BF5, animation_draw 0x0045D140 ->
    0x0044EAB0 (stall test on the stock)."""
    spec = _spec(g, b)
    zid = spec.get("zeus_id")
    if spec.get("employees", 0) > 0 and b.employees < 1:
        return None
    if zid in VENUES and b.misc.get("shows", 0) <= 0:
        return None
    if zid in STALL_BELOW:
        good = spec.get("input") if b.kind in ("workshop", "ranch") else spec.get("output")
        if b.goods.get(good, 0) < STALL_BELOW[zid]:
            return "idle"
    return "work"


def produce20(g):
    """Cycle step 20: cycle_production_progress_20 0x00485360 (crop growth of farms and trees, workshop progress),
    then terrain_regrow 0x004A7D30 (stumps, eaten meadows; the tree pass sets trees_exist 0x00B1E8F0)."""
    from . import walkers
    from ..gods import cursed, curse_free
    rules = g.rules
    free = curse_free(g)                          # nothing in the loop changes the gods' state
    for b in list(g.buildings.values()):
        k = b.kind
        if k not in ("producer", "orchard", "workshop"):
            continue
        if not free and cursed(g, b):                          # a god's curse on the type (g_type_curse; sim/gods)
            continue
        if k == "producer":                       # farms: crop grows with staffing
            pct = labor.staffing(g, b)
            b.progress = min(rules["farm_growth_max"], b.progress + pct * 10 // 100)
        elif k == "orchard":                      # trees grow faster while tended (the tend decay: tend_decay)
            b.progress = min(rules["farm_growth_max"], b.progress + (0 if b.tend == 0 else 8 if b.tend <= 80 else 19))
        else:
            spec = _spec(g, b)
            if spec.get("keeps_output"):          # the chariot workshop: step 31 (buildings_spawn_walkers 0xD4)
                continue
            inp, out = spec["input"], spec["output"]
            batch = spec.get("batch", 100)          # sculpture studio: 400 bronze -> 400 sculpture
            if b.goods.get(inp, 0) < batch:
                if b.employees:
                    b.reason = f"needs {inp}"
                continue
            if b.goods.get(out, 0) >= batch:
                # the exe has no workshop output stock: progress waits at 320 until the cart leaves (step 31,
                # 0x0048CFB0), so at most one finished load waits here besides the one in its cart
                continue
            b.progress += labor.staffing(g, b) // 10
            if b.progress >= rules["workshop_progress"]:
                b.progress = 0
                b.goods[inp] -= batch
                b.goods[out] = b.goods.get(out, 0) + batch
    walkers.meadow_day(g)                         # eaten meadow pictures follow their regrowth byte
    # stumps grow back (51-64 days after the cut, walkers.regrow_days); one cleared meanwhile (clear land / a road
    # path drop the tree bit) does not: terrain_regrow 0x004A7D30 only looks at tiles with the bit
    regrow = getattr(g, "regrow", [])
    if regrow:
        keep = []
        w = g.world
        for t, x, y in regrow:
            if t > g.tick:
                if w.flags[y, x] & 0x1:
                    keep.append((t, x, y))
            elif w.flags[y, x] & 0x1:
                walkers.tree_changed(g, x, y)
        g.regrow = keep
    g.trees_exist = trees_reachable(g)            # terrain_regrow's tree pass (0x00B1E8F0 = 0 first, then set)


def tend_decay(g):
    """month_advance 0x00483C10 -> 0x004AA640 / 0x004AA690 (after cycle step 50): every tree's tend - 1, min 0."""
    for b in list(g.buildings.values()):
        if b.kind == "orchard":
            b.tend = max(0, b.tend - 1)


def produce(g):
    """Cycle step 31, buildings_spawn_walkers 0x0048CFB0: the trireme wharf, the chariot workshop, herds, lodges,
    the ranch, gatherers, hunters and boats (step 20's part: produce20)."""
    from ..gods import cursed, curse_free
    free = curse_free(g)                          # nothing in the loop changes the gods' state
    for b in list(g.buildings.values()):
        spec = _spec(g, b)
        k = b.kind
        if not free and cursed(g, b):                          # a god's curse on the type (g_type_curse; sim/gods)
            continue
        if k == "shipyard" and b.employees:      # trireme wharf (military.md "Defences")
            if any(w in g.walkers and g.walkers[w].role == "trireme" for w in b.walkers):
                continue
            # buildings_spawn_walkers 0x0048CFB0 case 0x88: only with a palace and road access (navy.md "Launch")
            if b.access is None or next(iter(index.keyed(g, "palace")), None) is None:
                continue
            if b.goods.get("wood", 0) < 200 or b.goods.get("armor", 0) < 200:
                b.reason = "needs wood and armor for a trireme"
                continue
            b.progress += ladder(labor.staffing(g, b), [10, 8, 6, 4, 2])
            if b.progress > 319:
                b.progress = 0
                b.goods["wood"] -= 200
                b.goods["armor"] -= 200
                from . import walkers
                t = shore.mooring(g, b)
                if t:
                    tri = walkers.new_walker(g, role="trireme", home=b.id, x=t[0], y=t[1], state="moored")
                    b.walkers.append(tri.id)
                    walkers.add(g, tri, 10 ** 6)
                    g.message(f"a trireme was launched at the wharf at ({b.x},{b.y})")
        elif k == "workshop" and spec.get("keeps_output"):
            chariot_workshop(g, b, spec)
        elif k in ("herd", "lodge") and b.employees and b.access:
            pct = labor.staffing(g, b)
            interval = spec.get("interval_days") or ladder(pct, [1, 4, 8, 16, 32])
            b.spawn_timer += 1
            # herd_send_herders (0x004F77A0) and lodge_send_growers (0x004AB210) compare the counter before
            # its increment: every interval+1 days
            if b.spawn_timer < interval + 1:
                continue
            b.spawn_timer = 0
            if k == "herd":
                out_walkers = [g.walkers[w] for w in b.walkers if w in g.walkers]
                busy = len([w for w in out_walkers if w.role != "cart"])
                most = ladder(pct, [2, 1, 1, 0, 0])
                send_herders(g, b, spec, most - busy, most)
            else:
                send_growers(g, b, spec, pct)
        elif k == "ranch":
            ranch_day(g, b, spec)
        elif k == "gather" and b.employees and b.access:
            gather_day(g, b, spec, labor.staffing(g, b))
        elif k in ("hunt", "fishery", "urchin", "corral") and b.employees and b.access:
            WILD[k](g, b, spec, labor.staffing(g, b))


def chariot_workshop(g, b, spec):
    """Chariot workshop 0xD4, step 31 of buildings_spawn_walkers 0x0048CFB0 (production.md): it keeps its
    chariots (+0xDC) up to stock_cap 400 and stops when full; no cart. Rate 10/8/6/4/2 by staffing, a chariot
    (100) per 320 progress for 100 wood (+0x3C). Horses (+0x74) are not used up by production: the workshop
    buys them from ranches (chariot_workshop_buy_horses 0x00495B20) and they leave with the chariots when a
    horse trainer's buyer fetches them (buyer_chariot_loads 0x004CE760, 0x004CE630)."""
    if labor.halted(g, b):                     # 0x00FE933A = g_industry_halted[22]
        return
    pct = labor.staffing(g, b) if b.employees else 0
    if pct < 1:
        return
    buy_horses(g, b, pct)
    cap = spec.get("output_cap", 400)
    if b.goods.get("chariot", 0) >= cap:
        b.reason = "full of chariots"
        return
    if b.goods.get(spec["input"], 0) < 100:
        b.reason = f"needs {spec['input']}"
        return
    b.reason = ""
    b.progress += ladder(pct, [10, 8, 6, 4, 2])
    if b.progress > 319:
        b.progress = 0
        b.goods["chariot"] = b.goods.get("chariot", 0) + 100
        b.goods[spec["input"]] -= 100
        pm = g.sd("produced_month", {})
        pm["chariot"] = pm.get("chariot", 0) + 100


HORSE_SEARCH = 40          # vendor_find_source 0x0040EAD0: Chebyshev distance < 40


def buy_horses(g, b, pct):
    """chariot_workshop_buy_horses 0x00495B20: a counter (+0x32) runs up each day; past the delay (2/3/4/5/10 by
    staffing) and with no buyer of its own out (+0x2C fig 37), when it holds < 201 horses (+0x74) it sends a
    buyer to the nearest ranch with horses within 40 tiles (kind 2, slot 15). The buyer takes up to 4 horses,
    no more than 400 - held (buyer_horse_loads 0x004CEB40)."""
    from . import walkers
    if b.access is None:
        return
    t = b.misc["horse_timer"] = b.misc.get("horse_timer", 0) + 1
    if t <= ladder(pct, [2, 3, 4, 5, 10]):
        return
    if _out(g, b, "buyer"):
        return
    if b.goods.get("horses", 0) >= 201:
        return
    b.misc["horse_timer"] = 0
    has = [r for r in g.buildings.values() if r.kind == "ranch" and r.access and horses_of(g, r)
           and max(abs(r.x - b.x), abs(r.y - b.y)) < HORSE_SEARCH]
    dest, p = roads.nearest(g, b.access, has)
    if dest is None:
        return
    w = walkers.spawn(g, b, "buyer", target=dest.id, good="horses")
    w.path = p
    if not p:
        walkers.arrive(g, w)


def misc(b):
    return b.misc


def _tick_interval(b, n, strict=False):
    """Count days; True every n-th (urchin quay: `+0x32 += 1; >= n`), or every (n+1)-th when the exe tests
    strictly / before the increment (hunting lodge `> n`, 0x0048CFB0; corral 0x004F9960)."""
    b.spawn_timer += 1
    if b.spawn_timer < n + strict:
        return False
    b.spawn_timer = 0
    return True


def _out(g, b, role):
    return [g.walkers[w] for w in b.walkers if w in g.walkers and g.walkers[w].role == role]


def hunt(g, b, spec, pct):
    """Hunting lodge (production.md): hunters chase prey and bring back 100 meat each."""
    from . import walkers, wild
    if not _tick_interval(b, ladder(pct, spec["intervals"]), strict=True):
        return
    n = ladder(pct, spec["hunters"])
    n = min(n, max(0, (spec["cap"] - b.goods.get("meat", 0)) // 100)) - len(_out(g, b, "hunter"))
    if n <= 0:
        return
    # no radius (production.md "Hunting range"): the nearest unclaimed boar by walking distance, one
    # land search that stops at the first tile next to a boar (0x004D05F0, cutoff 1000 steps)
    taken = {w.target for w in g.walkers.values() if w.role == "hunter"}
    prey = [a for a in g.walkers.values() if a.role in wild.PREY and a.id not in taken
            and a.state not in ("struck", "carcass")]
    start = gather_start(g, b)
    if start is None:
        return
    for _ in range(n):
        goals = {}
        for a in prey:
            for t in walkers.neighbors4(a.x, a.y):
                goals.setdefault(t, a)
        if not goals:
            return
        p = walkers.land_path(g, start, set(goals), 1000)
        if p is None:
            return
        a = goals[p[-1] if p else start]
        walkers.spawn_gatherer(g, b, "hunter", (a.x, a.y), [start] + p, target=a.id, good="meat")
        prey.remove(a)


def fishery(g, b, spec, pct):
    """Fishing wharf: builds a boat (progress += 10/8/6/4/2 a day up to 200); the boat sails to a
    fishing point, fishes 204..1020 ticks, comes back and sets the stock to 100 (production.md)."""
    from . import walkers
    if _out(g, b, "boat"):
        return
    m = misc(b)
    tile = shore.mooring(g, b)
    if not tile:                          # no water exit (0x004A3FD0): the boat in progress is lost
        m["boat"] = 0
        return
    m["boat"] = m.get("boat", 0) + ladder(pct, spec["boat_rate"])
    if m["boat"] > 199:
        m["boat"] = 0
        walkers.spawn_boat(g, b, tile)


def urchin(g, b, spec, pct):
    """Urchin quay: one diver at a time; +100 urchins 200 ticks after each dive (production.md)."""
    from . import walkers
    if not _tick_interval(b, ladder(pct, spec["intervals"])):
        return
    if b.goods.get("urchin", 0) > 499 or len(_out(g, b, "diver")) >= ladder(pct, spec["divers"]):
        return
    tile = shore.mooring(g, b)
    start = gather_start(g, b)
    if tile and start:
        walkers.spawn_gatherer(g, b, "diver", tile, [start, tile], good="urchin")


def corral(g, b, spec, pct):
    """Poseidon corral (production.md "Corral"): ranchers bring cows in; a penned cow is slaughtered
    for 200 meat (stock cap 600) and a calf is released 15 days later."""
    from . import walkers
    m = misc(b)
    penned, slaughter, calf = m.get("penned", 0), m.get("slaughter", 0), m.get("calf", 0)
    if calf:
        calf += 1
        if calf > 15:
            calf = 0
            spot = next(iter(sorted(walkers.edge_tiles(g, b, walkers.open_walkable(g)))), None)     # animals: not on the road
            if spot:
                walkers.spawn_animal(g, spec["animal"], spot[0], spot[1])
    if penned:
        m["wait"] = m.get("wait", 0) + 1
        if m["wait"] > 7 and not slaughter:
            m["wait"] = 0
            penned -= 1
            if b.goods.get("meat", 0) < 600:
                slaughter = 1
    if slaughter:
        slaughter += 1
        if slaughter == 8 and not calf:
            calf = 1
        if slaughter > 15:
            slaughter = 0
            b.goods["meat"] = min(b.goods.get("meat", 0) + 200, 600)
    m.update(penned=penned, slaughter=slaughter, calf=calf)
    if not _tick_interval(b, ladder(pct, [1, 4, 8, 16, 32]), strict=True):
        return
    out = _out(g, b, spec["herder"])
    if len(out) >= 2 or penned + (calf > 0) + len(out) >= 3 or b.goods.get("meat", 0) >= 600:
        return
    # corral_send_ranchers 0x004F9960 -> 0x004F9630(cattle, ready only, at most 1): the nearest cow by route
    # distance from the road access with readiness >= 100 (+9 a month, born at 1), not bound to a rancher;
    # no radius. The rancher waits 30 ticks in the corral (action 0xB), then walks to the cow's tile.
    start = gather_start(g, b)
    if start is None:
        return
    taken = {w.target for w in g.walkers.values() if w.role == spec["herder"]}
    n_ = g.world.flags.shape[0]
    tree = walkers.land_tree(g, start, walkers.ROUTE_MAX)
    order = lambda a: (tree.get(a.y * n_ + a.x) or (1 << 30,))[0]
    cows = sorted((a for a in g.walkers.values() if a.role == spec["animal"] and a.id not in taken
                   and a.ready >= 100 and a.state not in ("led", "held") and (a.y * n_ + a.x) in tree),
                  key=lambda a: (order(a), a.id))
    for a in cows[:1]:
        p = walkers.tree_path(g, start, {(a.x, a.y)}, walkers.ROUTE_MAX)
        if p is None:
            p = walkers.tree_path(g, start, set(walkers.neighbors4(a.x, a.y)), walkers.ROUTE_MAX)
        if p is not None:
            walkers.spawn_gatherer(g, b, spec["herder"], (a.x, a.y), [start] + p, target=a.id, delay=30)


WILD = {"hunt": hunt, "fishery": fishery, "urchin": urchin, "corral": corral}


def send_herders(g, b, spec, n, most):
    """herd_send_herders 0x004F77A0 (production.md "Herding"): n = free herder slots, most = max herders.
    1) if the farm has room: one shearer per ready animal (nearest first), walking to the animal's tile;
    2) then one tending herder for up to `most` unattended animals (any readiness), who stands guard by
       each in turn. Each herder first waits in the farm (k*5+15)*2 ticks, k = its place in this batch."""
    from . import walkers
    if n <= 0:
        return
    role = spec["herder"]
    start = gather_start(g, b)
    if start is None:
        return
    herders = [w for w in g.walkers.values() if w.role == role]
    sheared = {w.target for w in herders if w.task != "tend"}
    bound = sheared | {a for w in herders if w.task == "tend" and w.state != "back"
                       for a in [w.target] + w.load.get("round", [])}
    # no radius: every animal reachable on foot from the farm's road access, nearest by walking distance
    # (herd_find_ready_animals 0x004F7180 / 0x004F74A0 sort by route_distance from road_access)
    n_ = g.world.flags.shape[0]
    tree = walkers.land_tree(g, start, 1000)
    order = lambda a: (tree.get(a.y * n_ + a.x) or (1 << 30,))[0]
    near = sorted((a for a in g.walkers.values() if a.role == spec["animal"] and a.state not in ("held", "led")
                   and (a.y * n_ + a.x) in tree), key=lambda a: (order(a), a.id))
    k = 0

    def path_to(a):
        p = walkers.tree_path(g, start, {(a.x, a.y)}, 1000)
        return p if p is not None else walkers.tree_path(g, start, set(walkers.neighbors4(a.x, a.y)), 1000)

    # shearers only while the farm's stock < 500 (b+0x3C), loads already on the way not counted; each load
    # arriving is clamped to 500 there (building_stock_add 0x004F8050), so a second shearer's load can be lost
    if b.goods.get(spec["output"], 0) < spec.get("cap", 500):
        for a in near:
            if n <= 0:
                return
            if a.ready < 100 or a.id in sheared:
                continue
            p = path_to(a)
            if p is None:
                continue
            for t in herders:                 # its tending herder is sent home (0x004F7FF0, action 9)
                if t.task == "tend" and t.state in ("go", "work") and (a.id == t.target or a.id in t.load.get("round", [])):
                    home = g.buildings.get(t.home)
                    if home is not None:
                        walkers.head_home(g, t, home)
            walkers.spawn_gatherer(g, b, role, (a.x, a.y), [start] + p, target=a.id, delay=(k * 5 + 15) * 2)
            bound.add(a.id)
            sheared.add(a.id)
            k, n = k + 1, n - 1
    if n <= 0:
        return
    flock, first = [], None
    for a in near:
        if len(flock) >= most:
            break
        if a.id in bound:
            continue
        p = path_to(a) if first is None else []
        if p is None:
            continue
        if first is None:
            first = p
        flock.append(a)
    if flock:
        a = flock[0]
        walkers.spawn_gatherer(g, b, role, (a.x, a.y), [start] + first, target=a.id, task="tend",
                               load={"round": [x.id for x in flock[1:]]}, delay=(k * 5 + 15) * 2)


def gather_start(g, b):
    """Where a gatherer (grower, herder, woodcutter...) leaves its building: the road access tile, in front,
    as the exe's spawners do (figure_create at road_access_x/y: lodge_send_growers 0x004AB210, herders
    0x004F77A0); without road access, an edge tile. (It was the first edge tile in sorted order, the back
    of the building: bugs.md 64.)"""
    from . import walkers
    if b.access is not None:
        return tuple(b.access)
    return next(iter(sorted(walkers.edge_tiles(g, b))), None)


def send_growers(g, b, spec, pct):
    """lodge_send_growers 0x004AB210 (production.md "Grower's lodge"). Growers out (b+0xA8) < pickers
    (4/3/2/1/0 by staffing), else nothing: one picker per ripe tree from 0x004AA8A0 (nearest by route
    distance from the road access, no radius; a tree claimed by a grower still farther away than this one is
    taken over), while that fruit's stock < 500; then, only if no grower is out at all, one tender for up to 4
    unclaimed unripe trees from 0x004AAC20 (any tend level; route distance + tend/2). Growers leave at once:
    the (k*5+15)*2 timer is set but figure_grower 0x004AECF0 actions 6 and 10 never read it."""
    from . import walkers, index
    pickers = ladder(pct, [4, 3, 2, 1, 0])
    out = [g.walkers[w] for w in b.walkers if w in g.walkers and g.walkers[w].role == "grower"]
    if len(out) >= pickers:
        return
    start = gather_start(g, b)
    if start is None:
        return
    n = g.world.flags.shape[0]
    tree = walkers.land_tree(g, start, walkers.ROUTE_MAX)
    s = start[1] * n + start[0]

    def dist(t):                          # g_grid_route_distance[tree]: steps from the road access (+1)
        i = t.y * n + t.x
        if i not in tree:
            return None
        d = 1
        while i != s:
            i, d = tree[i][1], d + 1
        return d

    trees = []
    for t in sorted(index.of(g, "orchard"), key=lambda t: t.id):
        if t.key in spec["trees"]:
            d = dist(t)
            if d is not None:
                trees.append((t, d))
    # pickers (0x004AA8A0): ripe trees (a ripe tree with no fruit loses its flag), nearest first
    ripe = []
    for t, d in trees:
        if not t.ripe:
            continue
        if not t.progress:
            t.ripe = False
            continue
        if t.claimed and claim_left(g, t.claimed) <= d:
            continue
        ripe.append((d, t))
    ripe = [(0, 0, t) for t in exe_sorted(ripe)]
    halted_goods = getattr(g, "industry_off", None) or ()
    for _, _, t in ripe[:pickers]:
        good = g.cat.spec(t.key)["output"]
        if good in halted_goods or b.goods.get(good, 0) >= spec.get("cap", 500):
            continue
        if len(out) >= pickers:
            return
        p = walkers.tree_path(g, start, {(t.x, t.y)}, walkers.ROUTE_MAX)
        if p is None:
            continue
        w = walkers.spawn_gatherer(g, b, "grower", (t.x, t.y), [start] + p, target=t.id, task="pick")
        out.append(w)
        old = g.walkers.get(t.claimed) if t.claimed else None
        t.claimed = w.id
        if old is not None:               # the grower it was claimed by goes on to its next tree, or home
            walkers.grower_next_ripe_tree(g, old)
    if pct < 25:
        return
    # the tender (0x004AAC20): unclaimed unripe trees by route distance + tend/2, up to 4, one grower
    due = [(0, 0, t) for t in exe_sorted([(d + (t.tend >> 1 & 0x7F), t) for t, d in trees if not t.claimed
                                          and not t.ripe and g.cat.spec(t.key)["output"] not in halted_goods])[:4]]
    if not due or out:
        return
    rnd = sorted(t.id for _, _, t in due)
    first = g.buildings[rnd[0]]           # walks the round in building-id order (grower_find_assigned_tree)
    p = walkers.tree_path(g, start, {(first.x, first.y)}, walkers.ROUTE_MAX)
    if p is None:
        return
    w = walkers.spawn_gatherer(g, b, "grower", (first.x, first.y), [start] + p, target=first.id, task="tend")
    w.load = {"round": rnd[1:]}           # the next trees of this tending round
    for _, _, t in due:
        t.claimed = w.id


MARBLE_PASSES = ((0xFE, False), (99, False), (0, False), (99, True))   # figure_miner 0x004C1310 action 6


def marble_targets(g, hits, match, taken):
    """The stonecutter's four searches (resource_tile_search 0x004A86E0, map-terrain.md 5b), in order; the
    first pass with a tile wins. Depth d = g.quarry.get(tile, 255): a tile qualifies if d >= the pass
    minimum and: d 255 -> its 8 neighbours are marble of the same kind (interior); d 100 -> its 8
    neighbours are pits (depth <= 100), except in the last pass; d 0 -> its 8 neighbours are deep (0).
    Yields lists of tile indices, one per pass."""
    q = getattr(g, "quarry", {})
    flat = g.world.flags.ravel()
    N = g.world.flags.shape[0]
    nb = (-N - 1, -N, -N + 1, -1, 1, N - 1, N, N + 1)
    dep = lambda i: q.get((i % N, i // N), 255)
    for lo, loose in MARBLE_PASSES:
        out = []
        for i in hits:
            if (i % N, i // N) in taken:
                continue
            d = dep(i)
            if d < lo:
                continue
            if d == 255:
                ok = all(int(flat[i + k]) & 0x120000 == match for k in nb)
            elif d == 100:
                ok = loose or all(dep(i + k) <= 100 for k in nb)
            else:
                ok = all(dep(i + k) <= 0 for k in nb)
            if ok:
                out.append(i)
        yield out


def gather_day(g, b, spec, pct):
    """Step 31 (0x0048CFB0) for the gatherers' buildings (production.md "Timber mill", "Mines", "Marble quarry").
    Workers by staffing, capped by the room in stock (stock only, carried loads not counted): miners and
    woodcutters `room // 25`, stonecutters `ceil(room / 100)`.
    - mines (foundry, mint, refinery): every day.
    - timber mill: u8 counter +1 a day; past 4 it tries: first its cart (stock >= 100, none out), then the cutters;
      the counter is reset only when cutters are short and the map has trees (so a mill whose cutters are all out
      sends the next one, and its next cart, the day a slot frees up).
    - quarry: the cart, not the stonecutter, is paced: period = trunc(100.0 / pct * 16.0) days; with stock 0
      the counter restarts. A cart of 100 leaves when the counter passes the period and no quarry cart is
      out; a stonecutter goes only when that cart left 300 behind, or the stock is 0 and the u8 idle
      counter (+0x33, never reset) was past period / 8."""
    if pct < 1:
        return
    if spec.get("mint_rate") and b.goods.get("silver", 0) > 199:
        # mint (case 0x30): progress climbs to 100; the coins come on the next day (still > 199 silver):
        # 200 silver -> 100 dr
        if b.progress < 100:
            b.progress = min(100, b.progress + ladder(pct, spec["mint_rate"]))
        else:
            b.progress = 0
            b.goods["silver"] -= 200
            d = 400 if b.misc.pop("blessed", 0) else 100     # case 0x30: a blessed mint pays 400
            g.city.treasury += d
            g.city.ledger["mint"] = g.city.ledger.get("mint", 0) + d
    out = spec["output"]
    stock = b.goods.get(out, 0)
    room = spec["cap"] - stock
    busy = len(_out(g, b, spec["worker"]))
    n = ladder(pct, spec["workers"])
    if spec["resource"] in ("marble", "black marble"):
        n = 1 if pct >= 25 else 0
        period = int(100.0 / pct * 16.0)
        from .. import gods
        if gods.active(g, 13):                  # Atlas's sanctuary (god record 13, 0x00EF607C; god_sanctuary_active
            period = period * 66 // 100         # 0x004E9440): the period x 66 / 100
        if stock == 0:
            b.spawn_timer = 0
        b.spawn_timer = (b.spawn_timer + 1) & 0xFF
        ok = False
        if b.spawn_timer > period and not _out(g, b, "cart") and stock >= 100:
            b.spawn_timer = 0
            # blessed: the cart takes 400 from the stock (cases 0x31 / 0xD5; it may go below 0, as the exe)
            send_cart(g, b, out, 400 if b.misc.pop("blessed", 0) else 100)
            stock = b.goods.get(out, 0)
            ok = stock == 300
        if stock == 0:
            m = misc(b)
            old = m.get("idle", 0)
            m["idle"] = (old + 1) & 0xFF
            ok = old > period // 8
        room = spec["cap"] - stock
        if room < n * 100:
            n = -(-room // 100)
        if ok:
            send_gatherers(g, b, spec, n - busy)
        return
    if spec["resource"] == "trees":
        b.spawn_timer = (b.spawn_timer + 1) & 0xFF
        if b.spawn_timer <= 4:
            return
        if stock >= 100 and not _live_cart(g, b, out):   # case 0x33: the cart only inside this gate, first
            send_cart(g, b, out, 100)                    # (a blessed one carries 400, stock - 100)
            stock = b.goods.get(out, 0)
            room = spec["cap"] - stock
        if room < n * 25:
            n = room // 25
        if busy < n and trees_exist(g):
            b.spawn_timer = 0
            send_gatherers(g, b, spec, n - busy)
        return
    n = 0 if room < 1 else min(n, room // 25)
    send_gatherers(g, b, spec, n - busy)


def exe_sorted(entries):
    """The growers' sorted lists (0x004AA8A0 pickers, 0x004AAC20 tender; nodes from FUN_004AB9A0): (key, item) in
    scan order (building id) go into a linked list from a cursor at the last inserted node: if the cursor's key is
    smaller, walk on to the first node with key >= the new one and insert before it (or at the tail); else walk
    back to the first node with key <= the new one and insert after it (or at the head). So ties do not keep scan
    order. Returns the items in list order."""
    lst, cur = [], -1
    for key, item in entries:
        if not lst:
            lst, cur = [(key, item)], 0
            continue
        if lst[cur][0] < key:
            i = cur
            while i < len(lst) and lst[i][0] < key:
                i += 1
        else:
            i = cur
            while i >= 0 and lst[i][0] > key:
                i -= 1
            i += 1
        lst.insert(i, (key, item))
        cur = i
    return [item for _, item in lst]


def claim_left(g, wid):
    """0x004AA8A0's test of a ripe tree's claim (+0x2A = a figure id): that figure's route_len - route_step,
    whatever it is now. A claim the exe never freed (a picker that found the tree no longer ripe, tree_pick
    0x004AB080 frees it only from a ripe tree) names a dead figure: remaining 0, so no picker takes the tree
    and the tender skips it (claimed) until the id is reused by a figure with a longer route. Ours: walker ids
    are not reused; a dead id counts as reused (remaining 10000, as a free slot reads) once 1999 newer walkers
    exist (the exe's ring of 1999 free ids, 0x00DBB84C: hypothesis for when the slot comes back)."""
    o = g.walkers.get(wid)
    if o is not None:
        return len(o.path)
    return 10000 if g.next_wid - wid > 1999 else 0


def resource_exists(g, spec):
    """The map still has the resource (0x00B1E8F0, trees: any tile with the flag)."""
    fl = g.world.flags
    return bool(np.any((fl & np.uint32(spec["mask"])) == spec["match"]))


def marble_search(g, spec, start):
    """figure_miner 0x004C1310 action 6 for marble (0x31 / 0xD5), when its timer passes 10: resource_tile_search
    0x004A86E0 from the figure's tile in the four depth passes (marble_targets); a tile with a figure of the
    stonecutter's type on it (0x3E, in the tile list: one standing or working there, the searcher itself too) is
    skipped, a tile another one is only walking to is not (both may pick it: the later one re-searches on arrival,
    walkers.reach_target). Of a pass's tiles the first reached by route_search_area 0x0058A4D0 (mask 0x19C) wins.
    The tile, or None (the exe deletes the figure)."""
    from . import walkers
    fl = g.world.flags
    N = fl.shape[0]
    hits = np.flatnonzero((fl & np.uint32(spec["mask"])).ravel() == spec["match"]).tolist()
    if not hits:
        return None
    taken = {(w.x, w.y) for w in g.walkers.values() if w.role in MINER_ROLES}   # type 0x3E
    t = walkers.land_tree(g, start, 1000, quarry=True)
    for hs in marble_targets(g, hits, spec["match"], taken):
        cands = [(t[i][0], i) for i in hs if i in t and t[i][0]]
        if cands:
            i = min(cands)[1]
            return (i % N, i // N)
    return None


MINER_ROLES = ("miner", "stonecutter")       # figure type 0x3E (figure_miner 0x004C1310 for all four mines + quarries)
LIST_CHUNK = 3999                              # resource_tile_search flushes its list at 3999 entries


def _heads(g):
    """The first figure of each tile's list (figure_tile_list: arrival order, contact.order): {(x, y): walker}."""
    from .walkers import tile_order
    out = {}
    for w in g.walkers.values():
        k = tile_order(w)
        o = out.get((w.x, w.y))
        if o is None or k < o[0]:
            out[(w.x, w.y)] = (k, w)
    return {t: v[1] for t, v in out.items()}


def _listed_pick(g, start, entries):
    """resource_tile_search 0x004A86E0's choice among its listed (tile, rock) entries (flat indices, scan order):
    every LIST_CHUNK entries route_find_listed_tile 0x00588B20 takes the first one its flood pops (a tile listed
    twice: its first entry); a later chunk wins only with a smaller route distance; the rest at the end of the scan
    likewise. Its bug kept: a list that ends exactly at a flush (nothing left) returns nothing even when an earlier
    chunk found a tile. (tile, rock) or None."""
    from . import walkers
    order = walkers.listed_bfs(g, start)
    best, bestd = None, 10000

    def first(chunk):
        r = None
        for e in chunk:
            o = order.get(e[0])
            if o is not None and (r is None or o[0] < r[0]):
                r = (o[0], o[1], e)
        return r
    k = 0
    while len(entries) - k >= LIST_CHUNK:
        r = first(entries[k:k + LIST_CHUNK])
        if r is not None and r[1] < bestd:
            best, bestd = r[2], r[1]
        k += LIST_CHUNK
    rest = entries[k:]
    if not rest:
        return None
    r = first(rest)
    if r is not None and r[1] < bestd:
        best = r[2]
    return best


def resource_search(g, spec, start, minimum):
    """resource_tile_search 0x004A86E0 for trees (mask 1) and ores (0x100002 copper, 0x200002 silver, 0x300000
    orichalc; kind mask 0x300002) from start over the whole map (resource_tile_search_call 0x004A85B0), in scan
    order (rows, then x); off-map tiles (0x80000) skipped, and a tile with a figure of the gatherer's type on it
    (woodcutter 0x37; miner 0x3E: stonecutters too).
    - Trees: the tile itself if its regrowth >= minimum (0xFF for the woodcutter's own search: grown trees only; 0
      for the building's check, resource_search_from_spawn 0x0048CDB0: stumps too). Ours: a stump is a tree-bit
      tile with a pending g.regrow entry (walkers.stumps).
    - Ores (regrowth >= 0: every rock): a rock worked by a miner (FUN_004A8650: a 0x3E figure in action 8 on one of
      its 8 neighbours whose +0x5C/+0x5E is this rock) is skipped; else each neighbour (table 0x005D9240: N, NE, E,
      SE, S, SW, W, NW; FUN_004A85F0: route & 0x1C, no building, the rock's elevation) whose first figure is not a
      0x3E is listed with the rock.
    Then _listed_pick. (dest tile, rock or None) as (x, y) pairs, or None. A failed tree search clears trees_exist
    (0x00B1E8F0)."""
    from . import walkers
    w = g.world
    fl = w.flags
    N = fl.shape[0]
    tree = spec["match"] == 1
    roles = ("woodcutter",) if tree else MINER_ROLES
    on = {(o.x, o.y) for o in g.walkers.values() if o.role in roles}
    entries = []
    if tree:
        st = walkers.stumps(g) if minimum > 0 else ()
        for i in np.flatnonzero(((fl & 0x80001) == 1).ravel()).tolist():
            t = (i % N, i // N)
            if t not in on and t not in st:
                entries.append((i, None))
    else:
        rocks = np.flatnonzero((((fl & 0x300002) == spec["match"]) & ((fl & 0x80000) == 0)).ravel()).tolist()
        if rocks:
            ok = walkers.walkable(g)
            heads = _heads(g)
            worked = {tuple(o.target_tile) for o in g.walkers.values()
                      if o.role in MINER_ROLES and o.state == "work" and o.target_tile is not None
                      and max(abs(o.x - o.target_tile[0]), abs(o.y - o.target_tile[1])) == 1}
            elev = w.elev
            for r in rocks:
                rx, ry = r % N, r // N
                if (rx, ry) in on or (rx, ry) in worked:
                    continue
                for dx, dy in walkers.DIR8:
                    x, y = rx + dx, ry + dy
                    j = y * N + x
                    if not ok[j] or (w.road[y, x] and fl[y, x] & 0x400 and not fl[y, x] & 0x800000):
                        continue                  # route & 0x1C: not 0x100 (ramp road), 0x20, 0x01, blocked
                    b = w.occ[y, x]
                    if b and g.buildings[b].key != "gardens":
                        continue
                    if elev[y, x] != elev[ry, rx]:
                        continue
                    h = heads.get((x, y))
                    if h is not None and h.role in MINER_ROLES:
                        continue
                    entries.append((j, r))
    best = _listed_pick(g, start, entries) if entries else None
    if best is None:
        if tree:
            g.trees_exist = False
        return None
    i, r = best
    return (i % N, i // N), (None if r is None else (r % N, r // N))


def trees_exist(g):
    """0x00B1E8F0, recomputed by the daily tree pass (terrain_regrow, cycle step 20): set when a timber mill (state 1,
    workers) reaches a grown tree from its road access (route_find_listed_tile 0x00588B20); cleared by a failed tree
    search. The mill sends cutters only while it is set (production.md "Timber mill")."""
    v = getattr(g, "trees_exist", None)
    if v is None:
        v = g.trees_exist = trees_reachable(g)
    return v


def trees_reachable(g):
    from . import walkers
    fl = g.world.flags
    N = fl.shape[0]
    st = walkers.stumps(g)
    trees = [i for i in np.flatnonzero(((fl & 0x80001) == 1).ravel()).tolist() if (i % N, i // N) not in st]
    if not trees:
        return False
    for b in g.buildings.values():
        if b.key == "timber_mill" and b.employees and b.access is not None:
            order = walkers.listed_bfs(g, tuple(b.access))
            if any(i in order for i in trees):
                return True
    return False


def send_gatherers(g, b, spec, n):
    """buildings_spawn_walkers 0x0048CFB0 for the gatherers: resource_search_from_spawn 0x0048CDB0 must find a tile
    from the road access (trees and ores: resource_search with regrowth >= 0; marble: the four passes of
    marble_search), then n figures leave in action 6, each with its wait (gatherer_wait), and search for themselves
    when it ends (walkers.gatherer task "search": woodcutters 0x004BF060, miners 0x004C1310), then walk by route
    mode 3 (stonecutters 0xB) onto the tree / the marble tile, or beside the rock (production.md "Resource
    search")."""
    from . import walkers
    if n <= 0:
        return
    start = gather_start(g, b)
    if start is None:
        return
    if spec["match"] in (0x20000, 0x120000):
        if marble_search(g, spec, start) is None:
            return
    elif resource_search(g, spec, start, 0) is None:
        return
    for _ in range(n):
        walkers.spawn_gatherer(g, b, spec["worker"], None, [start], delay=gatherer_wait(g, spec["worker"]),
                               task="search")


def gatherer_wait(g, role):
    """Ticks a new gatherer waits in action 6 before it walks (0x0048CFB0 sets its timer +0x36 with one RNG step):
    a woodcutter rng_15 % 30, counted down (0x004BF060: leaves when it drops below 1); a miner or stonecutter
    rng & 0x1F, counted up (0x004C1310: leaves once past 10)."""
    r = g.rng.randrange(32768)
    if role == "woodcutter":
        return max(1, r % 30)
    if role in ("miner", "stonecutter"):
        return max(1, 11 - (r & 0x1F))
    return 1


def harvest(g):
    """Called at the start of each month; farms harvest in their harvest month, orchard trees
    become ripe in theirs and lose their fruit at the END of their rot month (month_advance 0x00483C10 calls
    orchards_rot_unpicked 0x004AA6D0 before the month number changes: olives Jan..Mar, grapes Oct..Dec)."""
    mx = g.rules["farm_growth_max"]
    for b in g.buildings.values():
        spec = _spec(g, b)
        if b.kind == "orchard":
            if g.month == spec["harvest_month"]:
                b.ripe = True
            elif spec["rot_month"] is not None and (g.month - 1) % 12 == spec["rot_month"]:
                b.progress, b.ripe = 0, False
            continue
        if b.kind == "ranch":
            ranch_month(g, b, spec)
            continue
        if b.kind == "hippodrome" and b.employees is not None:
            # race income by the number of horses at the track (finance.md 5.2)
            n = b.goods.get("horses", 0) // 100
            pay = 0
            for need, amount in spec["income"]:
                if n >= need:
                    pay = amount
            if pay:
                g.city.treasury += pay
                g.city.ledger["races"] = g.city.ledger.get("races", 0) + pay
            continue
        if b.kind == "producer" and spec.get("mode") == "harvest" and g.month == spec["harvest_month"]:
            if b.progress > 0:
                loads = -(-b.progress * 8 // mx)          # ceil
                b.goods[spec["output"]] = b.goods.get(spec["output"], 0) + loads * 100
                g.message(f"{spec['name']} at ({b.x},{b.y}) harvested {loads * 100} {spec['output']}")
            b.progress = 0


def horses_of(g, b):
    return [g.walkers[w] for w in b.walkers if w in g.walkers and g.walkers[w].role == "horse"]


def ranch_month(g, b, spec):
    """Once a month: an old save's ranch gets its corral when there is room (bugs.md 134)."""
    from . import ranch
    ranch.adopt(g, b)


def ranch_day(g, b, spec):
    """Horse ranch, step 31 every day (0x0048CFB0 case 0x85, production.md "Horse ranch"), with road access:
    above pct * 6 / 100 horses one horse leaves a day. On the month's last day (day 15) the horses eat 10 wheat
    each: with no wheat at all at most 2 leave; with some, horse by horse, the first one it can't feed leaves
    and the rest go hungry. Then in even months (Jan, Mar, ...) a staffed ranch breeds one horse for 50 wheat
    if it has wheat for 6 months of the bigger herd."""
    from . import walkers, ranch
    if b.access is None:
        return
    pct = labor.staffing(g, b) if b.employees else 0
    food = spec["food_per_horse"]
    herd = horses_of(g, b)
    cap = pct * spec["max_horses"] // 100
    if len(herd) > cap:
        walkers.remove(g, herd.pop(0))
    if g.day % g.rules["days_per_month"] != g.rules["days_per_month"] - 1:
        return
    wheat = b.goods.get("wheat", 0)
    if wheat < len(herd) * food:
        if wheat < 1:
            for h in herd[:2]:
                walkers.remove(g, h)
            herd = herd[2:]
        else:
            for i, h in enumerate(herd):
                if wheat < food:
                    walkers.remove(g, h)
                    herd = herd[:i] + herd[i + 1:]
                    break
                wheat = max(0, wheat - food)
    else:
        wheat -= len(herd) * food
    b.goods["wheat"] = wheat
    if pct and g.month % 2 == 0 and len(herd) < cap and wheat >= 50 and (len(herd) + 1) * food * 6 <= wheat:
        if ranch.adopt(g, b):                 # in the corral, slot by slot (0x0063365C, bugs.md 134)
            spot = ranch.spawn_tile(g, b, len(herd))
        else:                                 # an old save's ranch with no room for a corral
            spot = next(iter(sorted(walkers.edge_tiles(g, b, walkers.open_walkable(g)))), None)  # animals: not on the road
        if spot:
            h = walkers.spawn_animal(g, "horse", spot[0], spot[1])
            h.home = b.id
            b.walkers.append(h.id)
            b.goods["wheat"] -= 50


BAY = 400


def bays(g, s):
    """Storehouse 8 bays, trading post / dock 15 (storage-distribution.md §3); granary: none."""
    return 15 if s.kind == "trade" else 8


def order(g, s, good):
    """Storage order for a good: accept | refuse | get | empty (text group 130). Storehouses list
    wheat (storage_goods_list 0x005B12C0) but start with food refused (storage_create 0x00494960)."""
    default = "refuse" if s.kind == "storage" and _spec(g, s)["accepts"] != "food" and g.cat.is_food(good) else "accept"
    return s.misc.get("orders", {}).get(good, default)


# Goods no storehouse or post ever holds: horses stay at the ranch / chariot workshop and chariots at the
# workshop until a buyer fetches them (vendor_find_source 0x0040EAD0 kind 2); no cart carries them (neither
# 0x85 nor 0xD4 spawns a cart in buildings_spawn_walkers 0x0048CFB0), the storehouse and trade windows leave
# them out (storage_goods_list 0x005B12C0), and posts never import them (trade.NOT_TRADED).
NOT_STORED = ("horses", "chariot")


def holds(g, s, good):
    """Can this storage hold the good at all: granary food 1..8; storehouse non-food plus wheat, never horses
    or chariots (storage_goods_list 0x005B12C0)."""
    if _spec(g, s)["accepts"] == "food":
        return g.cat.is_food(good)
    if good in NOT_STORED:
        return False
    return not g.cat.is_food(good) or good == "wheat"


def _incoming_all(g, s, by=None):
    if by is not None:
        return by.get(s.id, {})
    inc = {}
    for w in g.walkers.values():
        if w.role == "cart" and w.target == s.id:
            inc[w.good] = inc.get(w.good, 0) + w.amount
    return inc


def incoming_by_target(g):
    """{building id: {good: units}} of every cart on its way, in one pass over the walkers (the same sums, in the
    same order, as _incoming_all per building): for a search that checks many buildings while no walker moves."""
    by = {}
    for w in g.walkers.values():
        if w.role == "cart":
            d = by.get(w.target)
            if d is None:
                d = by[w.target] = {}
            d[w.good] = d.get(w.good, 0) + w.amount
    return by


def storage_room(g, s, good, arriving=False, by=None):
    """Units of good this storage can still take (counting carts on their way). Storehouses
    and trade buildings pack goods into 400-unit bays, one good per bay; the granary takes any food
    up to its capacity. Orders and per-good limits (storage command) apply. arriving: a cart at the door;
    a granary then refuses only Don't accept (granary_add_food 0x0048B680 takes food on Empty)."""
    spec = _spec(g, s)
    if spec.get("endless"):
        return 10 ** 9
    inc = _incoming_all(g, s, by)
    held = {k: v + inc.get(k, 0) for k, v in s.goods.items()}
    for k, v in inc.items():
        held.setdefault(k, v)
    if s.kind == "trade":             # trading post / dock: only goods with an export order
        from . import trade
        if trade.order(g, s, good) != "export":
            return 0
        lim = trade.limit(g, s, good)
    else:
        acc = spec["accepts"]
        shut = ("refuse",) if arriving and acc == "food" else ("refuse", "empty")
        if not holds(g, s, good) or order(g, s, good) in shut:
            return 0
        lim = s.misc.get("limits", {}).get(good, spec["capacity"])
    if s.kind == "storage" and spec["accepts"] == "food":
        room = spec["capacity"] - sum(held.values())
    else:
        used = sum(-(-v // BAY) for k, v in held.items() if k != good and v > 0)
        mine = held.get(good, 0)
        room = (bays(g, s) - used) * BAY - mine
    return max(0, min(room, lim - held.get(good, 0)))


def evict_unstorable(g):
    """Old saves (before 2026-10-29, bugs.md): horses and chariots reached storehouses and trading posts
    (imports from a partner that sells chariots, carts from chariot workshops), where the exe never puts
    them. Each such load goes back to the nearest chariot workshop that can hold it (chariots and horses
    up to 400 each, its stock_cap / buyer_horse_loads room), as if never shipped; the rest is dropped,
    because the exe has no other place for it (no storage takes it, a horse can't return to a ranch's
    corral as a stored good). Carts out with them are handled the same way, and post/storehouse orders
    for them are removed. Returns {good: dropped units}."""
    from . import walkers, trade
    shops = [b for b in g.buildings.values() if b.key == "chariot_workshop"]
    dropped = {}

    def home(good, n, x, y):
        for ws in sorted(shops, key=lambda b: abs(b.x - x) + abs(b.y - y)):
            k = min(n, max(0, 400 - ws.goods.get(good, 0)))
            if k:
                ws.goods[good] = ws.goods.get(good, 0) + k
                n -= k
            if not n:
                break
        if n:
            dropped[good] = dropped.get(good, 0) + n

    for s in g.buildings.values():
        if s.kind not in ("storage", "trade"):
            continue
        for good in NOT_STORED:
            n = s.goods.pop(good, 0)
            if n > 0 and not _spec(g, s).get("endless"):
                home(good, n, s.x, s.y)
            for m in ("orders", "limits"):
                s.misc.get(m, {}).pop(good, None)
    for w in list(g.walkers.values()):
        if w.role == "cart" and w.good in NOT_STORED:
            if w.amount > 0:
                home(w.good, w.amount, w.x, w.y)
            walkers.remove(g, w)
    return dropped


def good_on(g, good):
    """Ours (user 2026-10-30, the decision log): a Poseidon good (data/resources.json "poseidon": oranges) is off while
    Poseidon is off: no partner trades it (trade.city_buys/city_sells/set_order) and it is not on the city's food
    list (agora.city_foods)."""
    return good not in g.cat.poseidon_goods or getattr(g, "poseidon", False)


def purge_goods(g, goods, held=True):
    """Old saves (before 2026-10-30), Poseidon off: remove the goods (oranges) everywhere they can sit: storage,
    trading posts, houses, agoras and stalls, carts (removed with their load), buyers' loads, post/storehouse
    orders and limits, the city's food list, stockpile/industry flags, the partners' buys/sells (the save's copy
    of the world) and this year's trade quota use. Past totals and the monthly history are kept. held=False keeps
    what houses and agoras hold (eaten and peddled out over time): a house whose only food is oranges devolves at
    its next evolve check when they go (the user's save H: 34 houses, population 3488 -> 1540 in 2 months, all fed
    again from month 8). Returns {place: units removed} and the number of orders dropped."""
    from . import walkers
    goods = set(goods)
    out = {}

    def add(place, n):
        if n > 0:
            out[place] = out.get(place, 0) + n

    orders = 0
    for b in g.buildings.values():
        if not held and b.kind in ("house", "agora", "stall"):
            continue
        for k in goods:
            n = b.goods.pop(k, 0)
            if n and not _spec(g, b).get("endless"):
                add({"storage": "storage", "trade": "trade posts", "house": "houses",
                     "agora": "agoras", "stall": "agoras"}.get(b.kind, "other buildings"), n)
            for m in ("orders", "limits"):
                if b.misc.get(m, {}).pop(k, None) is not None and m == "orders":
                    orders += 1
    for w in list(g.walkers.values()):
        if w.role == "cart" and w.good in goods:
            add("carts", w.amount)
            walkers.remove(g, w)
            continue
        ld = getattr(w, "load", None)
        if ld:
            for k in goods:
                n = ld.pop(k, 0)
                if n:
                    w.amount = max(0, w.amount - n)
                    add("buyers", n)
    g.city.foods_listed.difference_update(goods)
    for attr in ("stockpile", "industry_off"):        # sets (game.py `stockpile`, `industry`)
        (getattr(g, attr, None) or set()).difference_update(goods)
    e = getattr(g, "empire", None)
    if e is not None:
        for c in e.cities.values():
            for d in (c.buys, c.sells, getattr(c, "request_fatigue", None)):
                for k in goods:
                    (d or {}).pop(k, None)
    for used in (getattr(g, "trade_state", None) or {}).get("used", []):
        for k in goods:
            used.pop(k, None)
    return out, orders


def inputs(g, u):
    spec = _spec(g, u)
    return spec.get("inputs") or ([spec["input"]] if "input" in spec else [])


def stockpiled(g, good):
    """City-wide stockpile flag (0x00FE94E0): kept in storage, not distributed or exported."""
    return good in getattr(g, "stockpile", ())


# --- goods in and out of the city as a whole (world map: gifts, tribute, deliveries; world-map.md 4.1) ---

def _stores(g):
    return [s for s in g.buildings.values() if s.kind in ("storage", "trade") and not _spec(g, s).get("endless")]


def city_stock(g, good):
    """Units of good in granaries, storehouses and trading posts (the exe's gift/request stock check)."""
    return sum(s.goods.get(good, 0) for s in _stores(g))


def goods_add(g, good, units):
    """city_goods_add 0x00489230: put units into storehouses/granaries that take the good (Get first,
    then Accept, within limits); returns what fit (the rest is lost, as in the exe)."""
    left = units
    stores = [s for s in _stores(g) if s.kind == "storage"]
    stores.sort(key=lambda s: order(g, s, good) != "get")
    for s in stores:
        n = min(left, storage_room(g, s, good))
        if n > 0:
            s.goods[good] = s.goods.get(good, 0) + n
            left -= n
        if not left:
            break
    return units - left


def goods_remove(g, good, units):
    """city_goods_remove 0x00489B90: take units out of storage (storehouses/granaries, then posts)."""
    left = units
    for s in sorted(_stores(g), key=lambda s: s.kind == "trade"):
        n = min(left, s.goods.get(good, 0))
        if n > 0:
            s.goods[good] -= n
            if not s.goods[good]:
                del s.goods[good]
            left -= n
        if not left:
            break
    return units - left


def can_take(g, s, good):
    """Goods may be taken out of storage (not when stockpiled); from a trading post only imports."""
    if stockpiled(g, good):
        return False
    if s.kind != "trade":
        return True
    from . import trade
    return trade.order(g, s, good) == "import"


PRODUCERS = ("producer", "workshop", "herd", "lodge", "gather", "hunt", "fishery", "urchin", "corral")
CART_SEARCH = 31          # a waiting cart searches again after 31 handler calls (0x004AE2A1: +0x36 > 30)


def _live_cart(g, b, good):
    """The building's cart for this good is still alive, out or waiting (cart_ok 0x0048CFB0: one cart per
    slot, +0x2A; the grower lodge has a second slot +0x2C for its second fruit)."""
    return any(w in g.walkers and g.walkers[w].role == "cart" and g.walkers[w].good == good for w in b.walkers)


def cart_destination(g, start, good, exclude=None):
    """cart_find_destination 0x004CCA50 (storage-distribution.md §6): a workshop that needs the good (not
    if stockpiled; find_workshop_for_input's ranking, storemen.find_workshop), else the nearest storage with room; the endless test sink only when every regular
    storage for the good is full. Returns (building, path) or (None, None)."""
    from . import storemen
    bs = g.buildings.values()
    by = incoming_by_target(g)              # no walker moves during the search
    dest, p = storemen.find_workshop(g, start, good)      # find_workshop_for_input 0x0048BC80 (its ranking)
    if dest is None:
        dest, p = roads.nearest(g, start, [s for s in bs if s.kind in ("storage", "trade") and s.access and s.employees
                                           and not s.burning and s is not exclude and not _spec(g, s).get("endless")
                                           and storage_room(g, s, good, by=by) >= 100])
    if dest is None and not any(storage_room(g, s, good, by=by) >= 100 for s in bs if s.kind == "storage" and s.access
                                and not _spec(g, s).get("endless")):
        # surplus: only when every regular storage for this good is full (or none exists)
        dest, p = roads.nearest(g, start, [s for s in bs if s.kind == "storage" and s.access and _spec(g, s).get("endless")])
    return dest, p


def cart_wait(g, w):
    """A cart standing with its load (action 6): search every 31 ticks (cart pusher 0x004AE160), so among
    producers waiting for the same room the first whose own timer comes round wins, not the oldest building."""
    from . import walkers
    home = g.buildings.get(w.home)
    if home is None:                                      # home.state != 1: the cart dies
        return walkers.remove(g, w)
    dest, p = cart_destination(g, (w.x, w.y), w.good, exclude=g.buildings.get(w.target) if w.target else None)
    if dest is None:
        home.reason = f"no place to deliver {w.good}"
        w.target = 0
        return walkers.schedule(g, w, CART_SEARCH)
    if home.reason.startswith("no place to deliver"):
        home.reason = ""
    w.state, w.target, w.path = "", dest.id, p
    walkers.schedule(g, w, walkers.tile_delay(g, w) if p else 1)    # at the door already: unloads next tick


def send_cart(g, b, out, n):
    """A producer's cart leaves with n of its stock and looks for a destination at once (step 31 send_cart)."""
    from . import walkers
    b.goods[out] -= n
    if b.misc.pop("blessed", 0):           # a god's blessing (b+0xDB, sim/gods): this cart x4 (min 400), crops x1.5
        n = n * 150 // 100 if b.kind == "producer" else max(400, n * 4)
    pm = g.sd("produced_month", {})       # for the reports (sim/reports.py); g_produced at departure
    pm[out] = pm.get(out, 0) + n
    if out in g.cat.foods:                 # per source building type, for the husbandry advisor (live.py)
        fs = g.sd("food_src_month", {})
        fs[b.key] = fs.get(b.key, 0) + n
    w = walkers.spawn(g, b, "cart", good=out, amount=n, target=0, state="wait")
    cart_wait(g, w)
    return w


def dispatch(g):
    from . import walkers
    bs = list(g.buildings.values())
    for b in bs:
        # step 31 send_cart (0x0048CFB0): one cart per slot; it takes 100 from stock at once (a farm's harvest
        # cart all its loads, up to 8) and searches for a destination on its first handler call (+0x36 = 30)
        if b.kind not in PRODUCERS or b.access is None:
            continue
        spec = _spec(g, b)
        if spec.get("resource") in ("marble", "black marble", "trees"):
            continue                              # the quarry and the timber mill send their carts in gather_day
        harvest = spec.get("mode") == "harvest"
        for out in outputs(g, b):
            if b.goods.get(out, 0) < 100 or _live_cart(g, b, out):
                continue
            send_cart(g, b, out, min(800, b.goods[out]) // 100 * 100 if harvest else 100)
    # storage walkers (storage_spawn_walkers 0x005B4B40; sim/systems/storemen.py): a storehouse's one deliveryman
    # carries a workshop's input; granaries' and storehouses' storehousemen run the Get and Empty orders
    from . import storemen, trade
    storemen.spawn(g)
    # trading posts' storehousemen (storage-distribution.md §8.1, trade_post_spawn_walkers 0x005B5620): one per
    # traded good (first 4, slots +0xBC + 2i), at >= 50 % staff: an exported good is fetched (up to 400) from the
    # nearest storage holding it, an imported good is pushed out to a workshop or storage that can take it
    for t in bs:
        if t.kind != "trade" or t.access is None or not trade.staffed(g, t):
            continue
        old = {g.walkers[w].good for w in t.walkers if w in g.walkers and g.walkers[w].role in ("buyer", "cart")
               and g.walkers[w].task not in storemen.TASKS}             # saves from before 11-04: their old walkers
        for good, mode in sorted(t.misc.get("orders", {}).items())[:4]:
            if good in old or storemen.post_slot(g, t, good) is not None or stockpiled(g, good):
                continue
            if mode == "export" and t.goods.get(good, 0) < trade.limit(g, t, good):   # storage_cannot_accept(post, 0, g)
                storemen.post_spawn(g, t, good, "export")
            elif mode == "import" and t.goods.get(good, 0) > 0:
                storemen.post_spawn(g, t, good, "import")
    # race tracks buy horses from ranches
    for t in bs:
        if t.kind != "hippodrome" or t.access is None or _out(g, t, "buyer"):
            continue
        if t.goods.get("horses", 0) // 100 >= _spec(g, t)["horses_cap"]:
            continue
        dest, p = roads.nearest(g, t.access, [r for r in bs if r.kind == "ranch" and r.access and horses_of(g, r)])
        if dest is not None:
            w = walkers.spawn(g, t, "buyer", target=dest.id, good="horses")
            w.path = p
            if not p:
                walkers.arrive(g, w)
    # (no restock for a vendor outside an agora: step 31 has no case for the chariot vendor 0xD7, and
    # vendor_update 0x0040A4C0 does nothing without a parent agora; ours had a 400-unit standalone restock)


def _wanted(g, want, good):
    return g.cat.is_food(good) if want == "food" else good == want


def cart_arrived(g, w):
    from . import walkers
    dest = g.buildings.get(w.target)
    if w.role == "cart":
        if dest is not None and dest.kind == "monument":
            from . import monuments
            return monuments.deliver(g, dest, w)     # unloaded at the road entry; the cart is gone (0x00544FC0)
        elif dest is not None:
            if dest.kind in ("storage", "trade"):
                # the storage checks its order on arrival. Storehouse (storehouse_add_goods 0x004895B0,
                # storage_cannot_accept 0x004894E0): nothing when unstaffed, burning, or the good is on Don't accept
                # or Empty (only accept and get take goods; posts only their traded goods). Granary
                # (granary_add_food 0x0048B680): refuses only Don't accept, no staff test. Else up to the limit and room
                w.target = 0                       # storage_room must not count this cart as still on its way
                food = _spec(g, dest).get("accepts") == "food"
                put = 0 if (not food and (not dest.employees or dest.burning) and not _spec(g, dest).get("endless")) \
                    else min(w.amount, storage_room(g, dest, w.good, arriving=True))
                w.target = dest.id
            elif dest.kind in ("workshop", "ranch", "shipyard"):   # workshop_add_input 0x0048C410: up to its cap
                put = max(0, min(w.amount, _spec(g, dest).get("input_cap", 300) - dest.goods.get(w.good, 0)))
            else:
                put = w.amount
            dest.goods[w.good] = dest.goods.get(w.good, 0) + put
            if _spec(g, dest).get("endless"):
                sur = g.sd("surplus", {})
                sur[w.good] = sur.get(w.good, 0) + put
            w.amount -= put
            if w.amount > 0 and reroute(g, w, dest):
                return
        walkers.go_home(g, w)              # leftover (if any) goes back home
    elif w.role == "buyer" and dest is not None and dest.kind == "ranch":
        home = g.buildings.get(w.home)
        n = 4
        if home is not None and home.key == "chariot_workshop":    # buyer_horse_loads 0x004CEB40: 400 - held
            n = min(4, max(1, (400 - home.goods.get("horses", 0)) // 100))
        elif home is not None and home.kind == "stall":             # 400 - the agora's horses - carried
            from . import agora
            a = agora.agora_of(g, home)
            n = agora.loads(len(horses_of(g, dest)) * 100, 400 - (a.goods.get("horses", 0) if a else 400) - w.amount, 4)
        for h in horses_of(g, dest)[:n]:      # up to 4 horses go with the trainer
            walkers.remove(g, h)
            w.amount += 100
            w.load["horses"] = w.load.get("horses", 0) + 100
        walkers.go_home(g, w)
    elif w.role == "buyer" and dest is not None and dest.key == "chariot_workshop":
        # Poseidon horse trainer at a chariot workshop (buyer_chariot_loads 0x004CE760 / 0x004CE630): up to 4
        # loads, each takes 100 chariots and 100 horses; per load one assistant brings a horse (slot 15) and one a
        # chariot (slot 19), but assistants never add slot 19 (0x004BC05F): the agora gets the horses only
        n = min(4, dest.goods.get("chariot", 0) // 100, dest.goods.get("horses", 0) // 100)
        for k in ("chariot", "horses"):
            dest.goods[k] = dest.goods.get(k, 0) - n * 100
            if not dest.goods[k]:
                del dest.goods[k]
        w.amount += n * 100
        if n:
            w.load["horses"] = w.load.get("horses", 0) + n * 100
        walkers.go_home(g, w)
    elif w.role == "buyer":
        home = g.buildings.get(w.home)
        if dest is not None and home is not None and home.kind == "stall":   # agora stall buyer (0x004CE9B0)
            from . import agora
            a = agora.agora_of(g, home)
            if a is not None:
                agora.buy_at(g, a, w, dest)
                if agora.next_storage(g, a, home, w):          # buyer_next_goods_storage 0x004CE300
                    return
            if not w.amount:                                   # buyer_go_home_or_die 0x004CE2D0: nothing
                return walkers.remove(g, w)                    # carried -> removed (state 2)
        elif dest is not None and home is not None and home.kind == "trade":   # post's storehouseman: <= 400
            from . import trade
            room = max(0, min(400, trade.limit(g, home, w.good) - home.goods.get(w.good, 0)))
            for k in sorted(dest.goods, key=lambda k: -dest.goods[k]):
                if room <= 0:
                    break
                if _wanted(g, w.good, k) and dest.goods[k] > 0 and can_take(g, dest, k):
                    take = min(room, dest.goods[k])
                    dest.goods[k] -= take
                    room -= take
                    w.amount += take
                    w.load[k] = w.load.get(k, 0) + take
        walkers.go_home(g, w)


def reroute(g, w, refused):
    """A cart a storage refused (all or part of its load) looks for another destination from where it stands
    (cart_after_unload 0x004CCAF0 -> cart_find_destination 0x004CCA50). A producer's cart with nowhere to go
    waits there (action 6) and searches again every 31 ticks; other carts (storages, posts) take the rest home.
    True when the cart stays out."""
    from . import walkers
    home = g.buildings.get(w.home)
    if home is not None and home.kind in PRODUCERS:
        w.state, w.target = "wait", refused.id
        cart_wait(g, w)
        return True
    from . import storemen
    bs = g.buildings.values()
    start = (w.x, w.y)
    w.target = 0                                          # its reservation is released (cart_after_unload)
    dest, p = storemen.find_workshop(g, start, w.good)
    if dest is None:
        dest, p = roads.nearest(g, start, [s for s in bs if s.kind in ("storage", "trade") and s is not refused
                                           and s.id != w.home and s.access and s.employees
                                           and not _spec(g, s).get("endless") and storage_room(g, s, w.good) > 0])
    if dest is None:
        return False
    w.target, w.path = dest.id, p
    if not p:
        walkers.arrive(g, w)
    else:
        walkers.schedule(g, w, walkers.tile_delay(g, w))
    return True


def cart_returned(g, w, home):
    if home.kind == "stall":                  # agora stall buyer: the stock goes to the agora
        from . import agora
        home = agora.agora_of(g, home) or home
    if w.role == "buyer":
        for k, n in w.load.items():
            home.goods[k] = home.goods.get(k, 0) + n
    else:
        home.goods[w.good] = home.goods.get(w.good, 0) + w.amount


def peddle(g, vendor, house):
    """Peddler gives goods to a house it passes (housing.md 'Inventory caps', simplified). An agora's
    peddler hands out food and the good of every open stall."""
    if vendor is None:
        return
    if vendor.kind == "agora":
        from . import agora
        kinds = ["food"] + [_spec(g, s)["goods"] for s in agora.stalls(g, vendor)
                            if s.key not in ("empty_stall", "food_vendor")]
        for k in kinds:
            _peddle(g, vendor, house, k)
        return
    _peddle(g, vendor, house, _spec(g, vendor)["goods"])


def _peddle(g, vendor, house, good):
    occ = house.occupants
    if good == "food":
        held = sum(house.goods.get(f, 0) for f in g.cat.foods)
        cap = 2 * occ if occ else 80
        batch = max(1, occ // 2) if occ else 20
        for f in g.cat.foods:
            have = vendor.goods.get(f, 0)
            if have <= 0 or held >= cap:
                continue
            give = min(batch, cap - held, have)
            vendor.goods[f] -= give
            house.goods[f] = house.goods.get(f, 0) + give
            held += give
    else:
        # peddler 0x0040D160: target = next level's need x4 (house size > 1) x2 (elite) x2 (the agora holds the
        # good): common x8, elite x16; armor and horses capped by the level's storage, in units of 100.
        # An empty (elite) house gets 10 x2 of vendor slots 1 and 2 (fleece, oil) whatever its level needs.
        col = {"wine": "wine", "fleece": "fleece", "olive_oil": "oil", "armor": "arms", "horses": "horses"}[good]
        hs = g.cat.houses
        top = 12 if is_elite(house) else 6
        cur, nxt = hs[house.level], hs[min(house.level + 1, top)]
        need = nxt.get(col, 0)                    # the next level's (top levels: their own)
        target = need * (4 if house.size > 1 else 1) * (2 if is_elite(house) else 1) * 2
        if not occ and good in ("fleece", "olive_oil"):
            target = need = 10 * 2
        unit = 1
        if good in ("armor", "horses"):
            unit = 100
            target = min(target, cur["max_armor" if good == "armor" else "max_horses"]) if need else 0
        have = vendor.goods.get(good, 0) // unit
        give = min(max(0, target - house.goods.get(good, 0)), have)
        if give > 0:
            vendor.goods[good] -= give * unit
            house.goods[good] = house.goods.get(good, 0) + give


from .housing import is_elite  # noqa: E402  (circular: imported last)
