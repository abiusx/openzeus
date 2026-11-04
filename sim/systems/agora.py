"""Agoras (docs/logic/storage-distribution.md part B). An agora is a road strip with 2x2 stall
plots beside it: common agora 6x3 (3 stalls on one side), grand agora 6x5 (3 + 3 stalls). Build
a vendor (food_vendor, fleece_vendor, ...) on an empty stall to open that stall. The road strip must
lie on an existing road (all 6 tiles road, 0x0040BF40); the stall plots must be free land.

The stock lives in the agora. A staffed stall sends a buyer (delay 2/3/4/5/10 days by staffing)
when the agora wants its good (food below 1000, armor/horses below 300, others below 200) to the
nearest storage within 40 tiles: it brings up to 8 loads of food / 4 loads of its good back to the
agora. The agora sends one peddler at a time while it holds stock; the peddler hands out every good
the agora has (economy.peddle).

Ours: the original's vendor assistants (figure 47, one follower per load, spawned at the storage and
walking home in a chain behind the buyer) are folded into the buyer, who carries the loads himself;
the play client draws the followers from the buyer's exported load count (presentation only). Vendors are built only on stalls (game.py rejects standalone ones,
except the chariot vendor).
"""
from . import walkers, roads, labor
from ..model import Building

DELAYS = [2, 3, 4, 5, 10]


def layout(key, x, y, d):
    """(strip tiles, stall top-left corners, (w, h)) for an agora at (x, y). d: for the common
    agora the side the stalls are on (down/up/right/left); for the grand agora h or v."""
    grand = key == "grand_agora"
    horiz = d in ("down", "up", "h", None)
    if grand:
        if horiz:
            return [(x + i, y + 2) for i in range(6)], [(x + i, y + j) for j in (0, 3) for i in (0, 2, 4)], (6, 5)
        return [(x + 2, y + i) for i in range(6)], [(x + j, y + i) for j in (0, 3) for i in (0, 2, 4)], (5, 6)
    if horiz:
        sy, ry = (y, y + 1) if d in ("down", None, "h") else (y + 2, y)
        return [(x + i, sy) for i in range(6)], [(x + i, ry) for i in (0, 2, 4)], (6, 3)
    sx, rx = (x, x + 1) if d == "right" else (x + 2, x)
    return [(sx, y + i) for i in range(6)], [(rx, y + i) for i in (0, 2, 4)], (3, 6)


def strip_ok(w, tx, ty):
    """The original's agora placement (0x0040BF40 over the layout tables 0x005E8790 common / 0x005E8C10
    grand): every road-strip tile must already be road (terrain 0x40) with no building on it; the stall
    tiles must be buildable land (no road). Ours also refuses avenue/boulevard tiles and bridges."""
    return bool(w.inside(tx, ty) and w.road[ty, tx] and not w.occ[ty, tx] and not w.avenue[ty, tx]
                and not w.flags[ty, tx] & 0x80000)


# the exe's variant order (layout tables 0x005E8790: 4 x 18 entries, 0x005E8C10: 2 x 30; road = kind 0, land = 1)
EXE_ORDER = {"agora": ("left", "down", "right", "up"), "grand_agora": ("v", "h")}


def fits(g, key, x, y, d):
    """The build rule for one layout: road strip on plain road, stalls on free level land."""
    w = g.world
    strip, stalls, _ = layout(key, x, y, d)
    return all(strip_ok(w, tx, ty) for tx, ty in strip) and all(w.area_ok(sx, sy, 2)[0] for sx, sy in stalls)


def snap(g, key, x, y):
    """The original's placement search (FUN_0040BF40 with search on, objects FUN_0040D7B0 / FUN_0040D7E0): every
    variant at the cursor tile, in table order; else anchors (x', y') for y' = y .. y-5, x' = x .. x-5 (rows
    first), each variant whose footprint covers the cursor tile; the first that fits. (x, y, d) or None."""
    order = EXE_ORDER[key]
    for d in order:
        if fits(g, key, x, y, d):
            return x, y, d
    for ay in range(y, y - 6, -1):
        for ax in range(x, x - 6, -1):
            for d in order:
                _, _, (bw, bh) = layout(key, ax, ay, d)
                if ax <= x < ax + bw and ay <= y < ay + bh and fits(g, key, ax, ay, d):
                    return ax, ay, d
    return None


def build(g, key, x, y, d=None):
    from ..game import CommandError
    w = g.world
    if d is None:                         # no side given: the original's search from the cursor tile (snap)
        found = snap(g, key, x, y)
        if found:
            x, y, d = found
    strip, stalls, (bw, bh) = layout(key, x, y, d)
    for tx, ty in strip:
        if not strip_ok(w, tx, ty):
            raise CommandError(f"can't build {key}: strip tile ({tx},{ty}) is not a plain road tile "
                               f"(an agora is laid on an existing straight road)", (45,))
    for sx, sy in stalls:
        ok, why = w.area_ok(sx, sy, 2)
        if not ok:
            raise CommandError(f"can't build {key}: stall at ({sx},{sy}): {why}", (18,))
    spec = g.cat.spec(key)
    g.spend(spec["cost"], "construction")
    a = Building(id=g.next_bid, key=key, x=x, y=y, size=0, kind="agora")
    g.next_bid += 1
    a.misc.update(w=bw, h=bh, strip=strip, stalls=[])
    g.buildings[a.id] = a
    for tx, ty in strip:
        w.road[ty, tx] = True
    for sx, sy in stalls:
        s = Building(id=g.next_bid, key="empty_stall", x=sx, y=sy, size=2, kind="stall")
        g.next_bid += 1
        s.misc["agora"] = a.id
        g.buildings[s.id] = s
        w.occ[sy:sy + 2, sx:sx + 2] = s.id
        a.misc["stalls"].append(s.id)
    g.map_version = getattr(g, "map_version", 0) + 1
    roads.rebuild(g)
    return f"built {key} #{a.id} at ({x},{y}) {d or 'down'} {bw}x{bh}, {len(stalls)} empty stalls at {stalls}, cost {spec['cost']}"


def stall_corners(g, a):
    """The agora's stall plots (top-left corners), in stall order: the layout whose road strip matches."""
    for d in ("down", "up", "left", "right", "h", "v"):
        strip, stalls, _ = layout(a.key, a.x, a.y, d)
        if [tuple(t) for t in strip] == [tuple(t) for t in a.misc.get("strip", [])]:
            return stalls
    return []


def empty_stall(g, s):
    """A vendor removed (clear, fire, collapse): its plot goes back to an empty stall of the agora."""
    s.key, s.goods, s.employees, s.reason = "empty_stall", {}, 0, ""
    s.misc = {"agora": s.misc["agora"]}


def repair(g):
    """Saves from before 2026-10-28: clearing a vendor deleted its stall, and the agora kept a dangling
    id (no vendor could be built there again). Rebuild missing stalls on free plots."""
    from ..model import Building
    w = g.world
    for a in [b for b in g.buildings.values() if b.kind == "agora"]:
        ids = a.misc.get("stalls", [])
        for k, (sx, sy) in enumerate(stall_corners(g, a)):
            if k < len(ids) and ids[k] in g.buildings:
                continue
            if (w.occ[sy:sy + 2, sx:sx + 2] != 0).any():
                continue
            s = Building(id=g.next_bid, key="empty_stall", x=sx, y=sy, size=2, kind="stall")
            g.next_bid += 1
            s.misc["agora"] = a.id
            g.buildings[s.id] = s
            w.occ[sy:sy + 2, sx:sx + 2] = s.id
            if k < len(ids):
                ids[k] = s.id
            else:
                ids.append(s.id)
            g.map_version = getattr(g, "map_version", 0) + 1


def remove(g, a, reason=None):
    """The agora gone (fire, collapse): building_on_remove 0x00494690 case 0x3F/0x40 (FUN_0040BE50: its id off the
    road strip, which stays road) and every stall part with it (building_parts_to_burning_ruins / _destroy_or_ignite
    walk the chain from the root)."""
    w = g.world
    for s in stalls(g, a):
        for wid in list(s.walkers):
            g.walkers.pop(wid, None)
        g.buildings.pop(s.id, None)
        w.occ[s.y:s.y + 2, s.x:s.x + 2][w.occ[s.y:s.y + 2, s.x:s.x + 2] == s.id] = 0
    g.demolish(a.id, reason)


def strip_near(g, x, y, r):
    """{agora id: road-strip tiles within the (2r+1)^2 square around (x, y)} (g_grid_building holds the agora's id
    on its strip: maintenance_walker_reduce_risk 0x004A5D90 lowers the agora's risk per strip tile)."""
    from . import index
    out = {}
    for a in index.of(g, "agora"):
        n = sum(1 for tx, ty in a.misc.get("strip", []) if abs(tx - x) <= r and abs(ty - y) <= r)
        if n:
            out[a.id] = n
    return out


def stall_at(g, x, y):
    s = g.buildings.get(int(g.world.occ[y, x])) if g.world.inside(x, y) else None
    return s if s is not None and s.kind == "stall" else None


def open_stall(g, key, x, y):
    """build VENDOR X Y on an empty stall: the stall becomes that vendor."""
    from ..game import CommandError
    s = stall_at(g, x, y)
    if s.key != "empty_stall":
        raise CommandError(f"the stall at ({s.x},{s.y}) is already a {s.key}")
    a = g.buildings[s.misc["agora"]]
    if any(g.buildings[i].key == key for i in a.misc["stalls"] if i in g.buildings):
        raise CommandError(f"this agora already has a {key}")
    spec = g.cat.spec(key)
    g.spend(spec["cost"], "construction")
    s.key = key
    g.map_version = getattr(g, "map_version", 0) + 1
    return f"opened {key} #{s.id} in {a.key} #{a.id} at ({s.x},{s.y}), cost {spec['cost']}"


def agora_of(g, s):
    return g.buildings.get(s.misc.get("agora"))


def stalls(g, a):
    return [g.buildings[i] for i in a.misc.get("stalls", []) if i in g.buildings]


def food_total(g, a):
    return sum(a.goods.get(f, 0) for f in g.cat.foods)


def wants(g, a, good):
    if good == "food":
        return food_total(g, a) < 1000
    return a.goods.get(good, 0) < (300 if good in ("armor", "horses", "chariot") else 200)


def loads(have, room, most):
    """Loads a stall buyer takes of one good at a storage (buyer_food_loads 0x004CED40, buyer_goods_loads
    0x004CEC80, buyer_horse_loads 0x004CEB40): 0 if room < 1, else min(max(1, room / 100), the storage's
    bucket: have / 100 capped at `most`, but 1 for 1..99)."""
    if room < 1 or have < 1:
        return 0
    return min(max(1, room // 100), min(most, have // 100) if have >= 100 else 1)


def city_foods(g):
    """g_city_food_list 0x010DFDAC as rebuild_goods_lists 0x005BAAF0 fills it: the foods (goods 1..8, urchin ..
    oranges, in that order) the city can have: its world-map city object lists it (FUN_00460B40, +0xA8; the
    sandbox's player city lists none), a partner sells it (city_any_sells_listed), or granaries, storehouses and
    trade buildings hold some. Ours: the empire's existing cities' sells (city_any_sells_listed: city_exists or
    trading partner, with a quota) and the stock now (the exe rebuilds the list at its own times: not traced);
    with the empire module off (data/trade.json's stand-in partners, not the exe's world) only the stock.
    A food once listed stays listed (flag 0x00FEB0D2[res], set by rebuild_goods_lists, in the saved city record,
    cleared at every episode start by FUN_0050d6c0: sim/episode.py marks_clear): a food that runs out keeps its place in the agora buyers' 5.
    Ours: a Poseidon good (oranges) is not listed while Poseidon is off (economy.good_on, user 10-30)."""
    from .economy import good_on
    sold = set()
    e = getattr(g, "empire", None)
    if e is not None:
        for c in e.cities.values():
            if c.kind != "player" and (c.exists() or c.trading()):
                sold.update(k for k, v in (c.sells or {}).items() if v)
    held = set()
    for b in g.buildings.values():
        if b.kind in ("storage", "trade") and not g.cat.spec(b.key).get("endless"):
            held.update(k for k, v in b.goods.items() if v)
    listed = g.city.foods_listed
    listed.update(f for f in g.cat.foods if (f in sold or f in held) and good_on(g, f))
    return [f for f in g.cat.foods if f in listed and good_on(g, f)]


def food_list(g):
    """The foods a food buyer takes (buyer_food_list 0x0040D840): the exe's is the first 5 of the city's food list
    (city_foods), so a 6th food is never bought. Ours (exe bug fixed, data/fixes.json agora_all_foods, bugs.md 297):
    every food on the list."""
    foods = city_foods(g)
    return foods if g.cat.fixed("agora_all_foods") else foods[:5]


def buy_at(g, a, w, dest):
    """A stall buyer at a storage (0x004CE9B0): food is pooled, each food of the list while the buyer carries
    < 800, room 1100 - carried - the agora's food, up to 8 loads per food; another good: room 400 - the
    agora's stock of it - carried, up to 4 loads. The foods in goods order: food_list (the exe: the first 5 of
    the city's food list; ours: all of it)."""
    from . import economy
    food = w.good == "food"
    order = food_list(g) if food else sorted(dest.goods, key=lambda k: -dest.goods[k])
    for k in order:
        if k not in dest.goods:
            continue
        # FUN_004CF950 / FUN_004CFAC0: only the stockpile flag; no trade-state test at the storage
        if not economy._wanted(g, w.good, k) or dest.goods[k] <= 0 or economy.stockpiled(g, k):
            continue
        if food:
            if w.amount >= 800:
                break
            n = loads(dest.goods[k], 1100 - w.amount - food_total(g, a), 8)
        else:
            n = loads(dest.goods[k], 400 - a.goods.get(k, 0) - w.load.get(k, 0), 4)
        take = min(n * 100, dest.goods[k])
        if take <= 0:
            continue
        dest.goods[k] -= take
        w.amount += take
        w.load[k] = w.load.get(k, 0) + take


def sources(g, s, good, least=1):
    """Storages (storehouses, granaries, trade posts) within 40 tiles of the stall (Chebyshev, building x/y)
    with road access (+0x44 / +0x20; no staff test) holding the good (stock > 0; vendor_find_source 0x0040EAD0 /
    buyer_research_sources 0x0040E2A0), not stockpiled (0x00FE94E0). Food (kind 0): a granary with any food; a
    storehouse or post only with a food the city imports (city trade status 0x01607EC4[res] == 5,
    trade.city_status), a post also not exporting it itself (+0xC4[res] != 7): a storehouse full of wheat is no
    food source unless wheat is imported (bug 460). The exe takes a storage holding any of the 8 foods, also one
    the buyer won't take (not in its 5); ours (exe bug fixed, data/fixes.json agora_all_foods, bugs.md 297): a
    storage holding a food of food_list. Other goods: a post only with the good not on export there (+0xC4)."""
    from . import economy, index, trade
    if good == "food" and g.cat.fixed("agora_all_foods"):
        takes = set(food_list(g))
        wanted = lambda k: k in takes
    else:
        wanted = lambda k: economy._wanted(g, good, k)
    food = good == "food"
    def ok(t, k):
        if economy.stockpiled(g, k):
            return False
        if t.kind == "trade" and trade.order(g, t, k) == "export":
            return False
        if food and _spec_accepts(g, t) != "food":
            return trade.city_status(g, k) == "import"
        return True
    return [t for t in index.of(g, "storage", "trade") if t.access
            and not g.cat.spec(t.key).get("endless") and max(abs(t.x - s.x), abs(t.y - s.y)) < 40
            and any(wanted(k) and n >= least and ok(t, k) for k, n in t.goods.items())]


def _spec_accepts(g, t):
    return g.cat.spec(t.key).get("accepts")


def next_storage(g, a, s, w):
    """buyer_next_goods_storage 0x004CE300, after a storage visit (0x004CE9B0 counts it in +0x93): a goods buyer
    (the food buyer always goes home, 0x004CE410) that has visited fewer than 3 storages and still has room for a
    load (400 - the agora's stock - carried, / 100 > 0; FUN_004CE290 picks the slot with the most) searches again
    (buyer_research_sources 0x0040E2A0: every storage within 40 tiles of the stall whose stock of the good is not
    0, nearest by the distance grid; ours: the route from the stall's road tile, as the first search) and walks
    there (FUN_004CE0E0). True when it was sent."""
    w.visits = getattr(w, "visits", 0) + 1
    if w.good == "food" or w.good == "horses" or w.visits >= 3 or s.access is None:
        return False
    if (400 - a.goods.get(w.good, 0) - w.load.get(w.good, 0)) // 100 < 1:
        return False
    dest, _ = roads.nearest(g, s.access, sources(g, s, w.good, least=1))
    if dest is None:
        return False
    p = roads.path(g, (w.x, w.y), {dest.access})
    if p is None:
        return False
    w.target, w.path = dest.id, p
    walkers.schedule(g, w, walkers.tile_delay(g, w) if p else 1)
    return True


def update(g):
    """Daily: stall buyers, agora staffing, agora peddler (services.spawn sends it)."""
    from . import economy
    storages = None
    from . import index
    for a in list(index.of(g, "agora")):
        ss = stalls(g, a)
        a.employees = sum(s.employees for s in ss)
        a.access = a.misc["strip"][0]
        a.network = int(g.world.road_net[a.access[1], a.access[0]])
    # vendor_update 0x0040A4C0, step 31 over the buildings in id order: a call counter k (1, 2, ...) counts
    # every vendor; a stall's timer counts while staffed; past its delay (2/3/4/5/10 days by staffing) it
    # sends a buyer on a day whose number in the month matches k mod 4, if none is out and the agora wants
    dom = g.day % g.rules["days_per_month"]
    calls = 0
    for s in sorted(index.of(g, "stall"), key=lambda s: s.id):
        if s.key == "empty_stall":
            continue
        calls += 1
        a = agora_of(g, s)
        if a is None or s.access is None or not s.employees:
            continue
        pct = labor.staffing(g, s)
        if pct < 1:
            continue
        s.spawn_timer = (s.spawn_timer + 1) & 0xFF
        if s.spawn_timer <= economy.ladder(pct, DELAYS):
            continue
        if any(w in g.walkers and g.walkers[w].role == "buyer" for w in s.walkers):
            continue
        good = g.cat.spec(s.key)["goods"]
        if dom % 4 != calls % 4 or not wants(g, a, good):
            continue
        s.spawn_timer = 0
        if good == "horses":
            # vendor_find_source 0x0040EAD0 kind 2: in Poseidon the horse trainer (73) fetches from chariot
            # workshops (212) holding chariots (+0xDC) and horses (+0x74), and then ranches are not scanned
            near = lambda r: max(abs(r.x - s.x), abs(r.y - s.y)) < 40
            has = [r for r in index.of(g, "workshop") if getattr(g, "poseidon", False) and r.key == "chariot_workshop"
                   and r.access and r.goods.get("chariot", 0) > 0 and r.goods.get("horses", 0) > 0 and near(r)]
            if not has:               # ranches within 40 tiles too (vendor_find_source)
                has = [r for r in index.of(g, "ranch") if r.access and economy.horses_of(g, r) and near(r)]
        else:
            has = sources(g, s, good)
        dest, p = roads.nearest(g, s.access, has)
        if dest is None:
            s.reason = f"no storage with {good} within 40 tiles"
            continue
        s.reason = ""
        w = walkers.spawn(g, s, "buyer", target=dest.id, good=good)
        w.path = p
        if not p:
            walkers.arrive(g, w)
