"""Workforce and employment (docs/logic/labor.md, simplified: no towers/military; inside a
category every building gets the same fill %, essential types first)."""
from . import index, walkers, risk

CATEGORIES = ["husbandry", "industry", "storage", "hygiene", "admin", "culture", "mythology", "military"]
ESSENTIAL = {"infirmary", "guardpost"}


def category(name):
    """Category index from a name prefix or number."""
    if name.isdigit() and int(name) < len(CATEGORIES):
        return int(name)
    hits = [i for i, c in enumerate(CATEGORIES) if c.startswith(name.lower())]
    if len(hits) != 1:
        raise ValueError(f"unknown labor category '{name}' ({', '.join(CATEGORIES)})")
    return hits[0]


def priorities(g):
    return g.sd("labor_priority", [3] * len(CATEGORIES))       # new game: all moderate (oracle dumps, 0x00FE9594)


def halted(g, b):
    """The player's per-resource industry shut-down (labor advisor; building_industry_halted 0x004873F0 reads
    g_industry_halted 0x00FE930E[output resource]; growers' lodge: grapes and olives both off; corral: beef)."""
    off = getattr(g, "industry_off", None) or ()
    if b.key == "growers_lodge":
        # case 0x25: each crop is out when shut down, or when the city can't make it (FUN_00460F90) and no finished
        # sanctuary provides it (god_resource_available 0x005BA890); halted when both are out. Ours: in a game
        # without an allowed table (sandbox_open) every crop can be made
        from .. import allowed
        def out(k):
            return k in off or (allowed.table(g) is not None and not allowed.produces(g, k)
                                and not allowed.god_provides(g, k))
        return out("grapes") and out("olives")
    if not off:
        return False
    if b.key == "fruit_lodge":
        return "oranges" in off
    if b.key == "corral":
        return "meat_beef" in off
    return g.cat.spec(b.key).get("output") in off


def entry_reach(g):
    """Flat list: tile reachable from the map entry by the exe's step-21 BFS (0x005883E0, route mask 0x17D):
    roads and open land, where trees, rubble, marble and reeds count as open land (route grid 0x005876F0,
    pathfinding.md §2); rock, water, cliffs, walls and buildings (but orchards) block. Cached per version."""
    from collections import deque
    ver = walkers._ver(g)
    c = getattr(g, "_entry_reach", None)
    if c is not None and c[0] == ver:
        return c[1]
    w = g.world
    n = w.flags.shape[0]
    ok = walkers.wild_walkable(g)              # land incl. trees, roads; no building
    orch = set()
    for t in index.of(g, "orchard"):
        orch.update((t.y + dy) * n + t.x + dx for dy in range(t.size) for dx in range(t.size))
    seen = [False] * (n * n)
    ex, ey = w.entry
    s = ey * n + ex
    seen[s] = True
    q = deque([s])
    while q:
        i = q.popleft()
        x = i % n
        for j in (i - n, i + n, i - 1 if x > 0 else -1, i + 1 if x < n - 1 else -1):
            if 0 <= j < n * n and not seen[j] and (ok[j] or j in orch):
                seen[j] = True
                q.append(j)
    g._entry_reach = (ver, seen)
    return seen


DIFFICULTIES = ["VeryEasy", "Easy", "Normal", "Hard", "Impossible"]       # 0x00F2A988 order (Model/*_<diff>.txt)


def workforce_pct(g):
    """Share of common residents who work (labor_pool_compute 0x004865A0): difficulty + wage level + health."""
    r = g.rules["workforce"]
    d = DIFFICULTIES.index(g.rules.get("difficulty", "Normal")) if g.rules.get("difficulty") in DIFFICULTIES else 2
    lv = r["wage_levels"]
    wage = g.city.wage_rate
    w = min(range(len(lv)), key=lambda i: (abs(wage - lv[i]), i))     # nearest level, first on ties (0x00569610)
    from . import health
    h = health._st(g)["health"]
    u = sum(1 for t in r["health_steps"] if h >= t)                     # 4 if >= 80 .. 0 if < 20
    return r["by_difficulty"][d] + r["by_wage"][w] + r["by_health"][u]


def allocate(g):
    c = g.city
    pct = workforce_pct(g)
    # elite residents don't work (labor.md)
    hs = index.of(g, "house")
    c.workforce = sum(b.occupants for b in hs if b.level < 7) * pct // 100
    # no road-network test: a building on a road not joined to the main road still gets workers, as long
    # as that road can be walked to from the map entry (buildings_road_access 0x004856A0: route BFS
    # 0x005883E0 over land and roads, mask 0x17D; labor.md "Eligibility")
    field = entry_reach(g)
    n = g.world.flags.shape[0]
    palace = next(iter(index.keyed(g, "palace")), None)
    jobs = []
    cat = {}                                 # building id -> labor category (looked up once a day)
    spec = g.cat.spec
    for b in sorted(g.buildings.values(), key=lambda b: b.id):
        sp = spec(b.key)
        need = sp["employees"]
        if not need:
            continue
        if b.access is None:
            b.employees, b.reason = 0, "no road access"
            continue
        if b.burning or (b.kind == "stall" and risk.on_fire(g, b)):     # a stall of a burning agora too
            b.employees, b.reason = 0, "on fire"
            continue
        # towers: staffed in step 23 (labor_pool_compute 0x004865A0) only when the palace exists and the
        # tower's road access tile (+0x26/+0x28) has the same road network id (g_grid_road_network
        # 0x00C4F288) as the palace's road access tile (labor.md 2, military.md "Defences")
        if b.key == "tower" and palace is None:
            b.employees, b.reason = 0, "needs a palace (military.md)"
            continue
        if b.key == "tower" and (palace.access is None or b.network != palace.network):
            b.employees, b.reason = 0, "not on the palace's road network"
            continue
        if b.key == "tower" and getattr(g, "towers_off", None):
            b.employees, b.reason = 0, "towers ordered unmanned (`towers on`)"
            continue
        if b.misc.get("off"):
            b.employees, b.reason = 0, "workers sent home (`staff X Y on`)"
            continue
        if sp["labor_category"] in (0, 1, 7) and halted(g, b):     # labor_eligible (labor.md 1)
            b.employees, b.reason = 0, "industry shut down (labor advisor)"
            continue
        if b.kind == "monument" and b.misc.get("built", 0) < 100:
            b.employees, b.reason = 0, f"under construction ({b.misc.get('built', 0)}%)"
            continue
        x, y = b.access                      # labor access +0x18 (step 12 0x00484FE0): the road tile
        if not field[y * n + x]:              # step 21 found must be reachable from the entry overland
            b.employees, b.reason = 0, "its road can't be reached from the city entry"
            continue
        jobs.append((b, need))
        cat[b.id] = sp["labor_category"]
    # priority 5 (very high) .. 1 (very low) are filled first, then 0 (no priority); inside a
    # level, essential types (infirmary, guardpost) first, then everyone at the same fill %
    prio = priorities(g)
    avail = c.workforce
    given = 0
    for b, _ in jobs:
        b.employees = 0
    # category 8 (towers, warship wharves) is staffed first, apart from the 8 categories (labor.md)
    for b, n in jobs:
        if cat[b.id] >= len(CATEGORIES):
            b.employees = min(n, avail)
            avail -= b.employees
            given += b.employees
    jobs8 = [(b, n) for b, n in jobs if cat[b.id] >= len(CATEGORIES)]
    jobs = [(b, n) for b, n in jobs if cat[b.id] < len(CATEGORIES)]
    groups = {}                              # (priority, essential) -> jobs in id order
    for b, n in jobs:
        groups.setdefault((prio[max(0, cat[b.id])], b.key in ESSENTIAL), []).append((b, n))
    for p in (5, 4, 3, 2, 1, 0):
        for ess in (True, False):
            group = groups.get((p, ess), ())
            need = sum(n for _, n in group)
            if not need or avail <= 0:
                continue
            take = min(need, avail)
            for b, n in group:
                b.employees = n * take // need
            got = sum(b.employees for b, _ in group)
            for b, n in group:                # rounding remainder in id order
                if got >= take:
                    break
                extra = min(n - b.employees, take - got)
                b.employees += extra
                got += extra
            avail -= got
            given += got
    for b, need in jobs + jobs8:
        b.reason = "" if b.employees >= need else f"needs workers ({b.employees}/{need})"
    c.employed = given
    c.unemployed = c.workforce - given
    # jobs per category (the labor advisor's rows): {category: [jobs, filled]}; "towers/wharves" = cat 8
    cats = {}
    for b, need in jobs + jobs8:
        ci = cat[b.id]
        r = cats.setdefault(CATEGORIES[ci] if 0 <= ci < len(CATEGORIES) else "towers/wharves", [0, 0])
        r[0] += need
        r[1] += b.employees
    g.labor_jobs = cats


def staffing(g, b):
    """Percent of the building's required staff (100 for buildings that need none)."""
    need = g.cat.spec(b.key)["employees"]
    return 100 if not need else b.employees * 100 // need
