"""Walkers (docs/logic/walkers.md, production.md). Everything physical moves:

- roamers (service walkers, peddlers) roam roads, serve a 5x5 square on every tile they reach,
  then walk home;
- carts, buyers and deliverymen follow road paths between buildings;
- immigrants / emigrants walk across land between the map entry and their house;
- gatherers (woodcutters, stonecutters, shepherds, growers) walk across land to a resource,
  work there, and carry the result back;
- animals (sheep, goats) wander on meadow.

Pace: Zeus moves a figure 15 sub-steps per tile and the speed code (Figure_model col 8) gives
sub-steps per tick (code 6 = 1 => 15 ticks per tile). rules.walker_pace = sub-steps per tile
(15 = Zeus, 1 = fast mode). Each walker is scheduled for the tick it next acts, so idle ticks
cost nothing.
"""
from collections import deque

from ..model import Walker
from .. import fastrand
from . import roads, services, economy, index

# speed code -> average sub-steps per tick as (num, den)   (walkers.md §speed)
SPEED = [(0, 1), (1, 4), (1, 3), (1, 2), (2, 3), (3, 4), (1, 1), (5, 4), (4, 3), (3, 2), (5, 3),
         (7, 4), (2, 1), (9, 4), (7, 3), (5, 2), (8, 3), (11, 4), (3, 1)]
ROLE_SPEED = {"sheep": 6, "goat": 5, "hunter": 8, "boar": 7, "deer": 7, "cattle": 5, "ship": 11}   # Figure_model; else 6
WALK_BLOCK = 0x1 | 0x2 | 0x4 | 0x200 | 0x80000 | 0x4000 | 0x1000000  # tree, rock, water, cliff, off-map, wall, lava
# (cooled lava 0x1000000: the route grid 0x005876F0 blocks it, & 0x2DFFD66F; grazers' 0x1D7FDC0F too; wild animals'
# 0x00569D90 mask 0x103AD02A does not: wild_walkable leaves it open; bug 448)
# people on land routes cross trees: the route grid 0x005876F0 marks tree, rubble, marble and reeds tiles as open
# land (bit 0x10), and every land route mask has that bit: 0x11D (mode 0: immigrants, emigrants, herders,
# ranchers, maintenance, soldiers), 0x10C roads then 0x11D (mode 3: homeless, caravans, hunters, woodcutters,
# storehouse men), 0x13D (mode 17: growers), 0x19C / 0x13C (modes 11, 13: miners/quarrymen); pathfinding.md §2, §4
PEOPLE_BLOCK = WALK_BLOCK & ~0x1
GATHERERS = ("woodcutter", "stonecutter", "miner", "shepherd", "goatherd", "grower", "hunter", "diver",
             "rancher")
ANIMALS = ("sheep", "goat", "horse", "boar", "deer", "cattle")
# The rate-100 gate (sprite_anim_step 0x005AF8C0 steps a frame only when 0x006668EC[image speed] fired that game
# turn, a wall-clock table): ours counts frame_ticks ticks a frame, measured at the default game speed (data/*.json).
# The oracle harness's virtual clock (zeus-run --deterministic: about 0.7 s of program time a tick) fires it every
# tick, so the oracle compare tools set 1 here (the archers' shot, the gods' rate-100 looks).
RATE100_TPF = None
ROUTE_MAX = 499     # the exe's searches have no radius; the route tracer 0x0058BC80 fails past 499 steps
ROADBLOCK_FREE = ("plagued", "disgruntled", "mugger")
EARLY_RETURN = ("peddler", "healer", "water", "mugger", "disgruntled")   # generic roamer 0x004CDEE0
CHASERS = {"shepherd", "goatherd", "hunter", "rancher"}      # walk to an animal that may move
HERDERS = ("shepherd", "goatherd")
TEND_TICKS = 120
# figure_hunter 0x004BE260 (production.md "Hunter handler states"): shot 12 ticks (action 0xD), butchering 13
# (action 8, timer 0..12) on the carcass tile; the carcass (boar action 10) lasts 500 ticks
STRIKE_TICKS, BUTCHER_TICKS, CARCASS_TICKS = 12, 13, 500                    # a tending herder's guard by each animal (figure_shepherd action 8, 0x78)


# --- scheduling -----------------------------------------------------------------------------

def now(g):
    """The tick whose figure pass comes next: g.tick inside Game.step (the cycle step and the pass run at the counted
    tick), g.tick + 1 between steps (a command acts before the next tick's cycle step, as the exe's input between two
    simulation_tick calls)."""
    return g.tick if g.__dict__.get("_in_tick") else g.tick + 1


def schedule(g, w, delay):
    q = getattr(g, "queue", None)
    if q is None:
        q = g.sd("queue", {})
    t = now(g) + max(1, delay)
    w.next_move = t
    if w.arrived == g.tick:          # it stepped this tick: the step lasts until its next move (display)
        w.step_end = t
    q.setdefault(t, []).append(w.id)


STORE_TASKS = ("deliver", "get", "empty")              # storemen.TASKS / STATES (sim/systems/storemen.py)
STORE_STATES = ("search", "dest", "fetch", "take", "go", "unload", "back", "home")
HERMES_133 = ("cart",)                  # figure types 4 cart, 9 storehouseman, 36 deliveryman (0x1C ox cart): ours "cart"
HERMES_150 = ("trader", "donkey", "ship")   # 0x13 caravan merchant, 0x15 its donkey, 0x14 trade ship


def speed(g, w):
    """The speed code (figure_type_value(f, 8) 0x004E1B20): Figure_model col 8; while Hermes' sanctuary is active
    (god record 7, ecx 0x00EF5F44) carts x 133 / 100 (unless led by a priest 0x41 / miner 0x3E: ours has no led
    carts), traders, donkeys and trade ships x 150 / 100 (C division: 6 -> 7, 6 -> 9, 11 -> 16)."""
    s = ROLE_SPEED.get(w.role, 6)
    if w.role in HERMES_133 or w.role in HERMES_150:
        from .. import gods
        if gods.active_now(g, 7):
            s = s * (133 if w.role in HERMES_133 else 150) // 100
    return s


def tile_delay(g, w):
    """Ticks until the walker reaches the next tile (fractional remainder carried)."""
    pace = g.rules.get("walker_pace", 15)
    num, den = SPEED[min(18, speed(g, w))]
    if num == 0:
        return 10 ** 9
    total = pace * den + w.rem
    w.rem = total % num
    return max(1, total // num)


TL_TICK = 1 << 20      # tile-list stamp: tick * TL_TICK + the entry's number in that tick


def listed(g, w):
    """figure_tile_list 0x004DC860: w goes last on its tile's list (figure_create, figure_change_tile and every jump
    unlink it from the old list and append it). Stamps w.tl = tick * TL_TICK + n, n = the tick's tile-list entries so
    far, so contact.order sorts a tile's figures in the order they entered, within a tick too (a figure made before
    the walker pass before the movers, one made in the pass at its maker's turn). Readers walk the list head first."""
    c = g.__dict__.get("_tlseq")
    if c is None or c[0] != g.tick:
        c = g.__dict__["_tlseq"] = [g.tick, 0]
    c[1] += 1
    w.tl = g.tick * TL_TICK + c[1]
    g._moves = g.__dict__.get("_moves", 0) + 1         # tile lists changed (military contact.everyone_at)


def tile_order(w):
    """The sort key of w in its tile's list (grid_figure 0x00D0D878 + next_on_tile +0x08, read head first): its stamp
    `tl` (listed). Walkers from before the stamp (older saves): the tick it entered (`arrived` / `listed`), then its
    slot. The exe's drawing re-sorts the lists of the tiles on screen (tile_walkers_sort 0x00449B30, by the figure's
    height in its tile, then id): not ported, the simulation does not depend on the view (walkers.md "Tile lists")."""
    tl = w.__dict__.get("tl")
    t = max(w.arrived, w.__dict__.get("listed", 0))
    if tl is not None and tl // TL_TICK >= t:
        return tl
    return t * TL_TICK + TL_TICK // 2 + w.fslot


def add(g, w, delay=1):
    """A new figure (figure_create 0x004D9FD0) takes its slot; its handler's first call is in the creation tick when
    the tick's walker pass (walkers_update 0x004CC8C0, slots 1..1999 after the cycle step) is still to reach that slot:
    always for a figure made before the pass (cycle step, terrain events, commands), and during the pass when its slot
    comes after the one acting. Else from the next tick. `delay` counts from that first call: 1 = the first call,
    d = d - 1 ticks after it (the handler's own timer)."""
    g.walkers[w.id] = w
    w.listed = g.tick
    listed(g, w)                                 # figure_tile_list at creation: last on its tile (contact.order)
    p = g.__dict__.get("_pass")
    if p is not None and w.fslot <= p[1]:
        schedule(g, w, delay)                    # an earlier slot: its first call is in the next tick's pass
    elif delay <= 1:
        w.next_move = now(g)                     # this tick's pass reaches it (move_all pops queue[g.tick] / the heap)
        if p is not None:
            import heapq
            heapq.heappush(p[0], (w.fslot, w.id))
        else:
            q = getattr(g, "queue", None)
            if q is None:
                q = g.sd("queue", {})
            q.setdefault(w.next_move, []).append(w.id)
    else:
        schedule(g, w, delay - 1)
    return w


def new_walker(g, **kw):
    w = Walker(id=g.next_wid, **kw)
    g.next_wid += 1
    return w


def spawn(g, b, role, **kw):
    w = new_walker(g, role=role, home=b.id, x=b.access[0], y=b.access[1], **kw)
    b.walkers.append(w.id)
    return add(g, w)


def roam_tiles(g, role):
    """Tiles a roamer walks before it turns home (rules.walker_roam, from the original's budgets)."""
    return g.rules.get("walker_roam", {}).get(role, g.rules["walker_roam_max"])


def spawn_roamer(g, b, role):
    return spawn(g, b, role, roam_left=roam_tiles(g, role))


def note_gone(g, w):
    """Live recorder only (sim/live.py): where a walker went in, so play mode draws its last step."""
    gone = g.__dict__.get("gone")
    if gone is not None:
        gone.append((w.id, w.x, w.y))


def sfx(g, w, kind, until=0):
    """Live recorder only (sim/live.py): a figure's one-shot sound for play mode, where the frame's looks cannot tell
    it (a god's bolt that hit nothing, a god hit, a god's melee attack): [tick, id, x, y, role, god, kind, until]."""
    out = g.__dict__.get("sfx")
    if out is not None:
        out.append([g.tick, w.id, w.x, w.y, w.role, getattr(w, "god", -1), kind, until])


def remove(g, w):
    g.walkers.pop(w.id, None)
    note_gone(g, w)
    home = g.buildings.get(w.home)
    if home and w.id in home.walkers:
        home.walkers.remove(w.id)


def move_all(g):
    """Called every tick: run the walkers due now, in slot order (walkers_update 0x004CC8C0 runs figures 1..1999;
    model.Walkers). A walker woken for this tick by one that acts before it (wake_now) still acts in it when its
    slot comes later, as in the exe."""
    import heapq
    q = getattr(g, "queue", None)
    if q is None:
        q = g.sd("queue", {})
    due = q.pop(g.tick, None)
    if not due:
        return
    ws = g.walkers
    heap = []
    for wid in due:
        w = ws.get(wid)
        if w is not None and w.next_move == g.tick:
            heap.append((w.fslot, wid))
    heapq.heapify(heap)
    g.__dict__["_pass"] = [heap, 0]
    try:
        while heap:
            s, wid = heapq.heappop(heap)
            w = ws.get(wid)
            if w is None or w.next_move != g.tick or w.fslot != s:
                continue
            g._pass[1] = s
            act(g, w)
    except BaseException:
        # a walker's code failed: the tick's bucket is already popped, so the walkers after it would never act again
        # (bugs.md 484: 84 froze on the shared server). They act on the next tick; the error goes on up.
        for _s, wid in heap:
            w = ws.get(wid)
            if w is not None and w.next_move == g.tick:
                w.next_move = g.tick + 1
                q.setdefault(g.tick + 1, []).append(wid)
        raise
    finally:
        g.__dict__.pop("_pass", None)


def reschedule_lost(g):
    """Walkers that would never act again: due in the past, or not in the bucket of their next_move (a walker pass
    that failed before 11-04, bugs.md 484), are due on the next tick. Returns how many. Game.load runs it."""
    q = getattr(g, "queue", None)
    if q is None:
        q = g.sd("queue", {})
    n = 0
    for w in g.walkers.values():
        # due only from the bucket of its own next_move (move_all skips an id whose next_move is another tick)
        if w.next_move <= g.tick or w.id not in q.get(w.next_move, ()):
            w.next_move = g.tick + 1
            q.setdefault(g.tick + 1, []).append(w.id)
            n += 1
    return n


def wake_now(g, w):
    """w must act on what just happened: in this tick's walker pass if its slot comes after the one acting now (the
    exe's handler for it runs later in the same walkers_update), else on the next tick. Returns True for this tick."""
    p = g.__dict__.get("_pass")
    if p is not None and w.fslot > p[1] and w.next_move != g.tick:
        import heapq
        w.next_move = g.tick
        heapq.heappush(p[0], (w.fslot, w.id))
        return True
    t = now(g)
    if w.next_move > t + 1 or w.next_move <= t:
        schedule(g, w, 1)
    return False


def acted_this_tick(g, w):
    """True when w's turn in this tick's walker pass has come (its slot is at or before the one acting now), or no pass
    runs: what it sees of a change made now is one tick late."""
    p = g.__dict__.get("_pass")
    return p is None or w.fslot <= p[1]


# --- land paths (off-road) -------------------------------------------------------------------

def _ver(g):
    return services.occ_version(g)


def road_list(g):
    """world.road as a flat list (index y*228+x), cached per occ_version: plain list reads are far
    cheaper than numpy element reads, above all under PyPy."""
    c = getattr(g, "_roadl", None)
    v = _ver(g)
    if c is None or c[0] != v:
        c = g._roadl = (v, g.world.road.ravel().tolist())
    return c[1]


def flags_list(g):
    """world.flags as a flat list of ints, cached per occ_version (tree_changed patches it)."""
    c = getattr(g, "_flagl", None)
    v = _ver(g)
    if c is None or c[0] != v:
        c = g._flagl = (v, g.world.flags.ravel().tolist())
    return c[1]


def tree_changed(g, x, y):
    """A tree was cut or grew back at (x, y): patch the walking caches for that one tile instead
    of dropping them all (they are keyed by occ_version, which a tree does not change)."""
    g.map_version = getattr(g, "map_version", 0) + 1          # the viewer redraws the terrain
    g.tree_changes = getattr(g, "tree_changes", 0) + 1
    n = g.world.flags.shape[0]
    i = y * n + x
    w = g.world
    c = getattr(g, "_flagl", None)
    if c is not None:
        c[1][i] = int(w.flags[y, x])
    c = getattr(g, "_walk", None)
    if c is not None:                         # a natural tree tile never holds a building; people's grid
        c[2][i] = bool((not w.flags[y, x] & WALK_BLOCK and not w.occ[y, x]) or w.road[y, x])   # ignores trees


def _walk_cache(g):
    ver = (_ver(g), len(g.__dict__.get("quarry") or ()))     # a pit never fills again: the count is a version
    cache = getattr(g, "_walk", None)
    if cache is not None and cache[0] == ver:
        return cache
    w = g.world
    n = w.flags.shape[0]
    base = (((w.flags & WALK_BLOCK) == 0) & (w.occ == 0)) | w.road      # bridges, gatehouses: road
    base = base.ravel().tolist()
    ramp = ((w.flags & 0x400) != 0) & ((w.flags & (PEOPLE_BLOCK & ~0x200)) == 0)   # route grid 0x005876F0: a
    ok = (((((w.flags & PEOPLE_BLOCK) == 0) | ramp) & (w.occ == 0)) | w.road).ravel().tolist()   # ramp (0x400) on a
    # cliff is open land (0x10), tested before the cliff bit (pathfinding.md §2; bugs.md 369); trees are open
    from . import index
    for t in index.of(g, "orchard"):          # orchard trees are open land (production.md "Orchards")
        for dy in range(t.size):
            for dx in range(t.size):
                ok[(t.y + dy) * n + t.x + dx] = True
    for t in index.of(g, "decor"):            # garden terrain 0x20 (ours: 1x1 "gardens" buildings) is open land
        if t.key == "gardens":                # 0x10, tested before the building bit (0x005876F0; bugs.md 369)
            ok[t.y * n + t.x] = True
    quarry = ok
    pits = g.__dict__.get("quarry")
    if pits:                                  # route grid 0x005876F0: marble (0x20000) whose regrowth byte is not
        quarry = list(ok)                     # 0xFF (a pit: quarry_dig) is bit 0x80, before the tree / marble open-land
        road = w.road                         # case; only mask 0x19C (stonecutters, route mode 0xB) has that bit
        for (x, y), d in pits.items():
            if d != 255 and not road[y, x] and w.flags[y, x] & 0x20000:
                ok[y * n + x] = False
    cache = g._walk = (ver, ok, base, quarry)
    return cache


def walkable(g):
    """Flat list: True where a person can walk (land incl. forest, road, or an orchard tree tile; no other
    building). The original's route grid 0x005876F0 marks trees and grapevine/olive/orange tree tiles (0x23,
    0x24, 0xD9) as open land (bit 0x10), and check_next_tile 0x004D8BB0 lets land walkers onto them.
    Roamers never use it (road-only, roam_open_sides 0x004A31E0)."""
    return _walk_cache(g)[1]


def quarry_walkable(g):
    """walkable() with the quarried marble tiles open: route mask 0x19C (route_search_area 0x0058A4D0, the marble
    search; the stonecutters' route mode 0xB)."""
    return _walk_cache(g)[3]


def open_walkable(g):
    """No building at all and no forest. Grazers (meadow route 0x00587FB0 rejects the building bit and
    trees, mask 0x1D7FDC0F) and ranch horses use it."""
    return _walk_cache(g)[2]


def wild_walkable(g):
    """Flat list for wild animals (boar, deer): the original's passability test 0x00569D90 has no tree
    bit, so they roam through forest; otherwise as open_walkable() (its block mask 0x103AD02A has the
    building bit 0x8, so orchard tree tiles block them too). Trees never change this grid."""
    ver = _ver(g)
    cache = getattr(g, "_wild", None)
    if cache is not None and cache[0] == ver:
        return cache[1]
    w = g.world
    ok = ((((w.flags & (WALK_BLOCK & ~0x1 & ~0x1000000)) == 0) & (w.occ == 0)) | w.road).ravel().tolist()
    g._wild = (ver, ok)
    return ok


def land_tree(g, start, max_dist, quarry=False):
    """The BFS of land_path from start, run to the end: tile -> (order first reached, previous
    tile). Cached per occ_version and quarry pits (trees don't change walkable()), so many searches from one door
    cost one BFS. quarry: over quarry_walkable() (mask 0x19C)."""
    ver = (_ver(g), len(g.__dict__.get("quarry") or ()))
    cache = getattr(g, "_trees", None)
    if cache is None or cache[0] != ver:
        cache = g._trees = (ver, {})
    key = (start, max_dist, quarry)
    t = cache[1].get(key)
    if t is not None:
        return t
    n = g.world.flags.shape[0]
    nn = n * n
    ok = quarry_walkable(g) if quarry else walkable(g)
    s = start[1] * n + start[0]
    touch = {s: (0, -1)}
    k = 1
    front, d = [s], 0                         # level by level: the FIFO order of a queue of (tile, depth)
    while front and d < max_dist:
        nxt = []
        for i in front:
            x = i % n
            for j in (i - n, i + 1 if x < n - 1 else -1, i + n, i - 1 if x > 0 else -1):   # N, E, S, W (pathfinding.md 3)
                if j < 0 or j >= nn or j in touch:
                    continue
                touch[j] = (k, i)
                k += 1
                if ok[j]:
                    nxt.append(j)
        front, d = nxt, d + 1
    cache[1][key] = touch
    return touch


def tree_path(g, start, goals, max_dist):
    """land_path's answer from the cached tree: the goal the BFS reaches first."""
    if start in goals:
        return []
    n = g.world.flags.shape[0]
    t = land_tree(g, start, max_dist)
    best = None
    for x, y in goals:
        e = t.get(y * n + x)
        if e is not None and e[0] and (best is None or e[0] < best[0]):
            best = (e[0], y * n + x)
    if best is None:
        return None
    s = start[1] * n + start[0]
    out = [best[1]]
    while t[out[-1]][1] != s:
        out.append(t[out[-1]][1])
    return [(k % n, k // n) for k in reversed(out)]


def land_path(g, start, goals, max_dist=60, ok=None):
    """BFS over walkable land (or the given passability list) from start to any tile in goals.
    Returns tile list (excl. start)."""
    if start in goals:
        return []
    n = g.world.flags.shape[0]
    nn = n * n
    ok = ok or walkable(g)
    s = start[1] * n + start[0]
    goal_idx = {y * n + x for x, y in goals}
    prev = {s: -1}
    front, d = [s], 0                         # level by level: the FIFO order of a queue of (tile, depth)
    while front and d < max_dist:
        nxt = []
        for i in front:
            x = i % n
            for j in (i - n, i + n, i - 1 if x > 0 else -1, i + 1 if x < n - 1 else -1):
                if j < 0 or j >= nn or j in prev:
                    continue
                if j in goal_idx:
                    prev[j] = i
                    out = [j]
                    while prev[out[-1]] != s:
                        out.append(prev[out[-1]])
                    return [(k % n, k // n) for k in reversed(out)]
                if ok[j]:
                    prev[j] = i
                    nxt.append(j)
        front, d = nxt, d + 1
    return None


def edge_tiles(g, b, ok=None):
    """Walkable tiles (or tiles open in the given list) edge-adjacent to building b."""
    bw, bh = b.misc.get("w", b.size), b.misc.get("h", b.size)
    cand = ([(b.x + i, b.y - 1) for i in range(bw)] + [(b.x + bw, b.y + i) for i in range(bh)] +
            [(b.x + i, b.y + bh) for i in range(bw)] + [(b.x - 1, b.y + i) for i in range(bh)])
    n = g.world.flags.shape[0]
    ok = ok or walkable(g)
    road = road_list(g)
    return {(x, y) for x, y in cand if 0 <= x < n and 0 <= y < n and (ok[y * n + x] or road[y * n + x])}


def entry_field(g, point="entry"):
    """BFS distance from the map entry (or exit) over walkable land (cached per occ_version)."""
    ver = _ver(g)
    cache = getattr(g, "_fields", {}).get(point)
    if cache is not None and cache[0] == ver:
        return cache[1]
    n = g.world.flags.shape[0]
    ok = walkable(g)
    dist = [-1] * (n * n)
    ex, ey = getattr(g.world, point)
    start = ey * n + ex
    dist[start] = 0
    q = deque([start])
    while q:
        i = q.popleft()
        d = dist[i] + 1
        x = i % n
        for j in (i - n, i + n, i - 1 if x > 0 else -1, i + 1 if x < n - 1 else -1):
            if 0 <= j < n * n and dist[j] < 0 and ok[j]:
                dist[j] = d
                q.append(j)
    g.sd("_fields", {})[point] = (ver, dist)
    return dist


def path_from_entry(g, b, point="entry"):
    """Land path from the map entry (or exit) to building b; ends next to b."""
    dist = entry_field(g, point)
    n = g.world.flags.shape[0]
    cands = [y * n + x for x, y in edge_tiles(g, b) if dist[y * n + x] >= 0]
    if not cands:
        return None
    out = [min(cands, key=lambda i: dist[i])]
    while dist[out[-1]] > 0:
        i = out[-1]
        x = i % n
        for j in (i - n, i + n, i - 1 if x > 0 else -1, i + 1 if x < n - 1 else -1):
            if 0 <= j < n * n and dist[j] == dist[i] - 1:
                out.append(j)
                break
        else:
            return None
    return [(i % n, i // n) for i in reversed(out)]


# --- spawning special walkers --------------------------------------------------------------------

def spawn_immigrant(g, house, k):
    """Immigrants walk from the map entry to the house. Unreachable houses get nobody."""
    p = path_from_entry(g, house)
    if p is None:
        house.reason = "immigrants can't walk here from the map entry"
        return False
    ex, ey = g.world.entry
    add(g, new_walker(g, role="immigrant", home=house.id, x=ex, y=ey, amount=k, path=p[1:], state="go"))
    house.pending += k
    return True


def spawn_emigrant(g, house, k):
    """People leaving walk from the house back to the map ENTRY, where immigrants come in (emigrant handler
    0x004ACD50 action 7 -> 8: dest = 0x00902CB4/6). Only homeless with no house left use the exit
    (0x004AD090: 0x00902CB8/A)."""
    p = path_from_entry(g, house) or path_from_entry(g, house, "exit")
    if not p:
        return
    add(g, new_walker(g, role="emigrant", home=0, x=p[-1][0], y=p[-1][1], amount=k, path=p[::-1][1:], state="go"))


def spawn_homeless(g, b, k):
    """People put out of house b (demolished, or overcrowded after a devolve) as one homeless walker
    (spawn_homeless 0x00487160); fig_handler_vagrant 0x004AD090: stands 52 ticks, then walks to the
    nearest house with room (homeless_go) or, with none, out of the city."""
    ok = walkable(g)
    n = g.world.flags.shape[0]
    at = (b.x, b.y) if ok[b.y * n + b.x] else b.access or min(edge_tiles(g, b), default=None)
    if at is None:
        return
    add(g, new_walker(g, role="homeless", home=0, x=at[0], y=at[1], amount=k, state="wait"), 52)


def homeless_house(g, w):
    """0x00486B80: the nearest house (Chebyshev, lowest id first) with road access, room and nobody on the way;
    sends the homeless there (True)."""
    from . import housing
    best = None
    for h in housing.houses(g):
        if h.access is None or h.pending or h.misc.get("infected") or housing.capacity(g, h) - h.occupants <= 0:
            continue
        d = max(abs(h.x - w.x), abs(h.y - w.y))
        if best is None or d < best[0]:
            best = (d, h)
    if best:
        h = best[1]
        p = land_path(g, (w.x, w.y), edge_tiles(g, h), max_dist=500)
        if p is not None:
            w.home, w.path, w.state = h.id, p, "go"
            h.pending += w.amount
            schedule(g, w, 1)
            return True
    return False


def homeless_go(g, w):
    """After the wait: a house with room (homeless_house) gets them; else they walk to the map exit, looking
    again every 31 ticks on the way (fig_handler_vagrant 0x004AD090 action 9)."""
    if homeless_house(g, w):
        return
    dist, n = entry_field(g, "exit"), g.world.flags.shape[0]
    i = w.y * n + w.x
    if dist[i] < 0:
        return remove(g, w)
    out = []
    while dist[i] > 0:
        x = i % n
        i = next(j for j in (i - n, i + n, i - 1 if x > 0 else -1, i + 1 if x < n - 1 else -1)
                 if 0 <= j < n * n and dist[j] == dist[i] - 1)
        out.append((i % n, i // n))
    w.path, w.state, w.wait = out, "leave", g.tick
    return schedule(g, w, 1)


def spawn_animal(g, role, x, y):
    w = new_walker(g, role=role, home=0, x=x, y=y, origin=(x, y), ready=50)
    return add(g, w, 1)         # figure_create: action 0 -> 6 on the first tick (figure_sheep 0x004BC380)


def spawn_gatherer(g, b, role, target_tile, path, delay=1, **kw):
    """A gatherer leaves building b on foot (from an edge tile) towards target_tile, after `delay` ticks
    (herders wait in the farm first; the play client hides a gatherer that has not stepped yet)."""
    w = new_walker(g, role=role, home=b.id, x=path[0][0] if path else b.x, y=path[0][1] if path else b.y,
                   path=path[1:], target_tile=target_tile, state="go", **kw)
    b.walkers.append(w.id)
    return add(g, w, delay)


# --- per-walker behaviour --------------------------------------------------------------------------

_OWN_HANDLER = frozenset(ANIMALS + GATHERERS + ("boat", "trireme", "trader", "ship", "donkey", "contestant", "artisan",
                                                "emigrant", "homeless", "immigrant"))

def blocked_sides(g):
    """Road tiles roaming walkers may not enter: roadblocks and gatehouse passages (pathfinding.md 6: the gatehouse,
    type 0x83, closes roaming sides like a roadblock; walkers on routes pass both). Cached per occupancy version."""
    v = (services.occ_version(g), len(getattr(g, "roadblocks", ())))
    c = getattr(g, "_blocked_sides", None)
    if c is None or c[0] != v:
        out = set(getattr(g, "roadblocks", ()))
        for b in index.of(g, "gatehouse"):
            ys, xs = (g.world.occ == b.id).nonzero()
            out.update((x, y) for x, y in zip(xs.tolist(), ys.tolist()) if g.world.road[y, x])
        c = g._blocked_sides = (v, out)
    return c[1]


# the military module (sim/military): walkers it drives, and the tile-contact hook (figure_tile_contact 0x004D4DA0)
MIL_ROLES = frozenset(("wolf", "tower_sentry", "wall_sentry", "arrow", "rabble", "hoplite", "horseman",
                       "enemy_infantry", "enemy_archer", "enemy_cavalry", "enemy_arrow",
                       "trireme", "enemy_warship", "enemy_transport"))     # ships: sim/military/navy.py
CONTACT = None          # set by sim/military: f(g, walker) -> True when the walker now fights
GOD_ROLES = frozenset(("god", "priest", "god_bolt", "entranced", "god_helper"))      # the gods module (sim/gods)
MINER_TYPE = ("miner", "stonecutter")     # figure type 0x3E (figure_miner 0x004C1310)


def step_to(g, w, nxt):
    w.prev, (w.x, w.y) = (w.x, w.y), nxt
    w.arrived = g.tick
    listed(g, w)
    c = CONTACT or _contact_hook()
    if w.role not in MIL_ROLES:
        c(g, w)


def _contact_hook():
    """The military module's hook, set on the first step of a process. It used to be set by the first military day,
    so each CLI call (load, step, save) skipped tile contacts until its first day boundary and a game played call by
    call differed from one run in one process (playtest haiku-2 triage, bugs.md 315)."""
    from .. import military
    military._register()
    return CONTACT


def act(g, w):
    r = w.role
    if r in MIL_ROLES or w.__dict__.get("mil"):
        from .. import military
        return military.act(g, w)
    if r in GOD_ROLES:                       # gods and priests (sim/gods)
        from .. import gods
        return gods.act(g, w)
    if r in ("monster", "hero"):             # sim/heroes
        from .. import heroes
        return heroes.act(g, w)
    if w.state == "dying":                   # saves from before 2026-10-28 (old melee)
        return remove(g, w)
    if w.anim:                               # melee (crime.melee): stand still until the fight ends
        if w.anim == "die":
            return remove(g, w)
        if w.busy_until > g.tick:
            return schedule(g, w, w.busy_until - g.tick)
        if crime.fight_over(g, w):
            return
    if r in _OWN_HANDLER:                    # roles with their own branch (disjoint role tests; carts and
                                             # superintendents fall through to the road walkers)
        if r in ANIMALS:
            return animal(g, w)
        if r == "boat":
            return boat(g, w)
        if r == "trireme":                      # at the wharf, waiting for orders
            return schedule(g, w, 10 ** 6)
        if r in ("trader", "ship"):
            return trade.trader(g, w)
        if r == "donkey":
            return trade.donkey(g, w)
        if r == "contestant":                    # Panhellenic games contestant (systems/games.py, 0x004C30D0)
            from . import games
            return games.contestant(g, w)
        if r == "artisan":                       # walks over the monument, works its pieces (systems/monuments.py)
            return monuments.artisan(g, w)
        if r == "emigrant":
            if w.path:
                step_to(g, w, w.path.pop(0))
                return schedule(g, w, tile_delay(g, w))
            note_gone(g, w)
            return g.walkers.pop(w.id, None)
        if r == "homeless":
            if w.state == "wait":
                return homeless_go(g, w)
            if w.state == "leave" and g.tick - w.wait >= 31:      # action 9: re-check every 31 ticks
                w.wait = g.tick
                if homeless_house(g, w):
                    return
            if w.path:
                step_to(g, w, w.path.pop(0))
                return schedule(g, w, tile_delay(g, w))
            if w.state == "leave":
                note_gone(g, w)
                return g.walkers.pop(w.id, None)
            return immigrant_arrive(g, w, rehouse=True)
        if r == "immigrant":
            if w.path:
                step_to(g, w, w.path.pop(0))
                return schedule(g, w, tile_delay(g, w))
            return immigrant_arrive(g, w)
        if r in GATHERERS:
            return gatherer(g, w)
    if r == "maintenance":
        if w.state in ("fire", "ext"):
            return risk.fire_fight(g, w)
        if risk.fire_dispatch(g, w):
            return risk.fire_fight(g, w)
    if r == "cart" and w.state == "follow":  # a stonecutter's marble cart: he moves it; gone with him
        if w.link not in g.walkers:
            return remove(g, w)
        return schedule(g, w, 51)
    if r == "cart" and w.task in STORE_TASKS and w.state in STORE_STATES:   # deliverymen, storehousemen
        from . import storemen
        return storemen.act(g, w)
    # road walkers
    road = road_list(g)
    if not road[w.y * 228 + w.x]:
        return remove(g, w)
    if r == "cart" and w.state == "wait":   # a producer's cart standing with its load (0x004AE160 action 6)
        return economy.cart_wait(g, w)
    if w.path:
        return follow(g, w, road)
    if w.returning or (r in ("cart", "buyer") and w.target) or r == "trainee":
        return arrive(g, w)                  # (a cart spawned on its target's road tile has arrived)
    # roaming
    # roam_open_sides 0x004A31E0: plagued (0x42), disgruntled (0x16) and muggers (0x1B) walk through roadblocks
    blocked = () if r in ROADBLOCK_FREE else blocked_sides(g)
    x, y = w.x, w.y                          # road neighbours: up, right, down, left (world.road_neighbors)
    near = [t for t in ((x, y - 1), (x + 1, y), (x, y + 1), (x - 1, y))
            if 0 <= t[0] < 228 and 0 <= t[1] < 228 and road[t[1] * 228 + t[0]] and t not in blocked]
    opts = [t for t in near if t != w.prev] or near
    if r in EARLY_RETURN and home_tile(g, w) == (x, y) and 2 * w.roam_left <= roam_tiles(g, r):
        w.roam_left = 0                      # back at its start after half its roam: done (walkers.md §5.2)
    if not opts or w.roam_left <= 0:         # turn and take the first step home at once (walkers.md §5.2)
        go_home(g, w)
        if w.path and w.id in g.walkers:
            return follow(g, w, road)
        return
    mem = g.sd("visits", {}).setdefault(memory_key(g, w), {})
    if len(opts) > 1:            # prefer the road least recently walked by this service
        oldest = min(mem.get(t, -1) for t in opts)
        opts = [t for t in opts if mem.get(t, -1) == oldest]
    nxt = opts[g.rng.randrange(len(opts))] if len(opts) > 1 else opts[0]
    mem[nxt] = g.tick
    step_to(g, w, nxt)
    w.roam_left -= 1
    if r in ("mugger", "disgruntled"):
        if crime.melee(g, w):
            return
        if r == "mugger" and crime.mug(g, w):
            return schedule(g, w, 20)
    services.apply(g, w)
    schedule(g, w, tile_delay(g, w))


def home_tile(g, w):
    home = g.buildings.get(w.home)
    return home.access if home else None


def follow(g, w, road):
    """One step along w.path (road walkers): serve or fight on the new tile, then wait a tile time."""
    r = w.role
    nxt = w.path.pop(0)
    if not road[nxt[1] * 228 + nxt[0]]:
        return remove(g, w)
    step_to(g, w, nxt)
    if r in ("peddler", "trainee") or r in services.SERVICES:
        services.apply(g, w)
    else:
        if r in crime.ROLES and crime.melee(g, w):
            return
        if r == "mugger":
            crime.mug(g, w)
    if w.path:
        return schedule(g, w, tile_delay(g, w))
    if r == "trainee" and not w.returning:   # arrives at the last tile's centre, 7 sub-steps on (services.send_trainee)
        return schedule(g, w, 7)
    return arrive(g, w)


def memory_key(g, w):
    """Roaming memory channel: one per building, so each building's walkers alternate their own
    routes. (A shared per-service memory let one vendor's walker, ending its roam next to another
    vendor, steer that vendor's walkers away from its own street for good.)"""
    return w.home


def go_home(g, w):
    home = g.buildings.get(w.home)
    if not home or home.access is None:
        return remove(g, w)
    p = roads.path(g, (w.x, w.y), {home.access})
    if p is None:
        return remove(g, w)
    w.returning, w.path = True, p
    schedule(g, w, tile_delay(g, w) if p else 1)


def arrive(g, w):
    if w.role == "artisan" and not w.returning:
        w.state = "work"
        return monuments.artisan(g, w)
    if w.role in ("thief", "vandal") and not w.returning:
        return crime.arrive(g, w)
    if w.role == "trainee" and not w.returning:          # a trainee joins the venue: shows = 32 (0x00491EF0)
        v = g.buildings.get(w.target)
        if v is not None:
            v.misc["shows"] = g.rules.get("trainee_shows", 32)
        return remove(g, w)
    if w.returning:
        home = g.buildings.get(w.home)
        if home and w.role in ("cart", "buyer") and (w.amount or w.load):
            economy.cart_returned(g, w, home)
        return remove(g, w)
    economy.cart_arrived(g, w)          # sets up the way back (go_home) or removes


def immigrant_arrive(g, w, rehouse=False):
    from . import housing
    h = g.buildings.get(w.home)
    if h:
        h.pending -= w.amount
        # an infected house takes nobody: immigrants (0x004AC810) and homeless (0x004AD090) arriving there are lost
        got = 0 if h.misc.get("infected") else max(0, min(housing.capacity(g, h) - h.occupants, w.amount))
        h.occupants += got
        g.city.population += got              # immigrants were counted when sent (send_immigrants 0x00486860)
    g.walkers.pop(w.id, None)
    note_gone(g, w)


# --- animals -----------------------------------------------------------------------------------------

GRAZERS = ("sheep", "goat", "cattle")


def _wait_until_move(g, first, chance, lo, span):
    """Ticks until an animal that waits `first` ticks, then moves with `chance` (1/N) or re-waits
    lo..lo+span-1 ticks and rolls again, actually moves: the re-rolls drawn at once (same distribution,
    one act instead of ~N)."""
    t = first
    while g.rng.randrange(chance):
        t += lo + g.rng.randrange(span)
    return t


def _hop(g, w, cx, cy, lo, hi, meadow):
    """Random reachable spot at offset lo..hi (each axis) from (cx, cy), 100 tries; the land path
    there, or None. Grazers only walk and stop on meadow (production.md "Animal movement (RE)");
    boar and deer cross forest (wild_walkable). While a build tool hovers over the map (g.hover, shoo below) a
    grazer's new spot is never inside the tool's footprint (animal_pick_dest 0x004F83E0: PtInRect on the rect at
    0x00F0E4CC while the flag 0x00F0E4C8 is set; the path may cross it)."""
    n = g.world.flags.shape[0]
    hv = g.__dict__.get("hover") if meadow else None
    ok = wild_walkable(g) if w.role in ("boar", "deer") else open_walkable(g)
    fl = flags_list(g)
    bare = g.__dict__.get("grass_bare", {}) if meadow else {}
    day = g.day
    # animal_pick_dest 0x004F83E0: a grazer's new spot needs meadow regrowth >= 50; a tile eaten bare (regrowth 0)
    # regrows +15/16 a day (terrain_regrow 0x004A7D30), so it is eligible again 4 days later
    occ_free = lambda x, y: ok[y * n + x] and (not meadow or (fl[y * n + x] & (0x800 | 0x10000)
                                                              and day - bare.get((x, y), -9) >= 4))
    for _ in range(100):
        x, y = cx + lo + g.rng.randrange(hi - lo + 1), cy + lo + g.rng.randrange(hi - lo + 1)
        if (x, y) == (w.x, w.y) or not (0 <= x < n and 0 <= y < n) or not occ_free(x, y):
            continue
        if hv and hv[0] <= x < hv[2] and hv[1] <= y < hv[3]:
            continue
        p = land_path(g, (w.x, w.y), {(x, y)}, 12, ok)
        if p is not None and all(occ_free(a, b) for a, b in p):
            return p
    return None


def animal(g, w):
    """Animals (docs/logic/production.md "Animal movement (RE)"):
    - sheep, goats, cattle: a new one walks at once; after each walk it grazes 71 ticks (timer 100 capped
      to 0x46, 0x004F8770), then every 20..69 ticks moves on with chance 1/8 to a random meadow tile
      within 4 (reachable over meadow, no leash to where it was placed), else it grazes on;
    - ranch horses: 30 ticks after creation and after each walk (0x004BA080), then every 20..69 ticks
      pace with chance 1/4 to a spot -4..+3 from where they stand, inside the ranch's corral (systems/ranch.py);
    - boar: the exe's restlessness machine (boar_idle).
    Wool/milk readiness grows once a month (month_ready). Grass: a grazer leaving eats its tile bare; bare tiles
    are not picked as a new spot for 4 days (g.grass_bare; the exe's meadow regrowth >= 50).
    The meadow picture follows the regrowth byte a day late (picture_regrowth). Not modelled: the write-only
    counter +0x144."""
    if w.state == "carcass":                  # figure_boar 0x004BD030 action 10: gone 500 ticks after the shot
        left = w.anim_t0 + CARCASS_TICKS - g.tick
        return remove(g, w) if left <= 0 else schedule(g, w, left)
    if w.state in ("held", "led", "struck"):  # being shorn / milked / led to the corral / shot: stay put
        return schedule(g, w, g.rules["ticks_per_day"] // 3)
    if w.path:
        step_to(g, w, w.path.pop(0))
        return schedule(g, w, tile_delay(g, w))
    r = w.role
    if r in ("boar", "deer"):
        return boar_idle(g, w)
    if w.state != "idle":
        arrived = w.state == "walk"
        w.state = "idle"
        if not arrived:                       # just placed (or let go by a herder)
            if r == "horse":
                return schedule(g, w, _wait_until_move(g, 30, 4, 20, 50))
            if r not in GRAZERS:
                return schedule(g, w, 51 + g.rng.randrange(103))
        else:
            return _rest(g, w)
    if r in GRAZERS:
        p = _hop(g, w, w.x, w.y, -4, 4, True)
        if p:                                 # figure_graze: leaving eats the tile bare (regrowth 0); its picture
            bare = g.sd("grass_bare", {})     # stays until the next daily regrow (picture_regrowth, meadow_day)
            held = g.sd("grass_held", {})
            held[(w.x, w.y)] = (g.day, picture_regrowth(g, w.x, w.y))
            bare[(w.x, w.y)] = g.day
            if len(bare) > 2000:
                g.grass_bare = {t: d for t, d in bare.items() if g.day - d < MEADOW_DAYS}
            if len(held) > 2000:
                g.grass_held = {t: v for t, v in held.items() if g.day - v[0] < 2}
    elif r == "horse":
        from . import ranch
        home = g.buildings.get(w.home)
        if home is not None and ranch.has_corral(home):   # inside its corral only (0x004D0140, bugs.md 134)
            p = ranch.hop(g, w, home)
        else:                                 # a ranch of an old save without room for a corral
            p = _hop(g, w, w.origin[0], w.origin[1], -4, 3, False)
    else:
        p = _hop(g, w, w.origin[0], w.origin[1], -4, 4, False)
    if p:
        w.path, w.state = p, "walk"
        return schedule(g, w, 1)
    _rest(g, w)


def shoo(g):
    """Animals under the build cursor (docs/logic/buildings.md 5 "Animals under the build cursor"; oracle
    sheep-build-r3, tools/oracle_sheep_build.py). Every frame with a build tool over the city view (game_turn /
    screen_input -> FUN_004059C0) the exe takes the tool's footprint at the hovered tile (size from the type table,
    turned by the view), sets the flag 0x00F0E4C8 and, for each figure on each footprint tile, FUN_004F9380: a sheep,
    goat or cattle grazing / resting (actions 6, 0x10) gets animal_pick_dest(walk 7, radius = the footprint's side),
    else (radius x 2); one wandering (0x11) the same with action 8. Animals already walking are left alone. The
    build itself is still refused while one stands on a tile (map_area_buildable 0x004A0DC0): the player waits for
    them to walk off. Ours: g.hover = (x0, y0, x1, y1) (raw, x1 / y1 exclusive), set by play mode's ghost (/control
    hover) or the `hover` command, applied between ticks as the exe's frames; a shooed animal walks in the next
    tick's pass (dump 38 action 7, moving from tick 38 in the exe)."""
    hv = g.__dict__.get("hover")
    if not hv:
        return
    x0, y0, x1, y1 = hv
    r = max(x1 - x0, y1 - y0)
    hit = sorted((w for w in g.walkers.values()
                  if w.role in GRAZERS and x0 <= w.x < x1 and y0 <= w.y < y1 and w.state in ("", "idle") and not w.path),
                 key=lambda w: (w.y, w.x, getattr(w, "listed", 0), w.id))
    for w in hit:
        p = _hop(g, w, w.x, w.y, -r, r, True) or _hop(g, w, w.x, w.y, -2 * r, 2 * r, True)
        if not p:
            continue
        w.path, w.state = p, "walk"
        w.next_move = now(g)
        q = getattr(g, "queue", None)
        if q is None:
            q = g.sd("queue", {})
        q.setdefault(w.next_move, []).append(w.id)


def hover_rect(g, key, x, y):
    """(x0, y0, x1, y1) of a tool's footprint with top-left (x, y): the type's size (FUN_004059C0 reads
    g_building_type_info[tool].size; roads, walls, clearing: 1)."""
    spec = g.cat.spec(key) if key in g.cat.buildings else {}
    s = spec.get("size") or 1
    w, h = (s, s) if isinstance(s, int) else (s[0], s[1])
    return (x, y, x + w, y + h)


# --- meadow regrowth (presentation of the grazing above) ----------------------------------------------------
# terrain_regrow 0x004A7D30 (cycle step 20, daily): a meadow tile's regrowth byte g < 255 gets + 15 + a random bit,
# 255 when it overflows; terrain_resource_image then redraws it: e1 = int((meadow - 1) / 99 * g / 85) picks the
# picture (docs/play/terrain.md 3; tools/terrain_images.py meadow). The byte after d days from an eaten tile:
# 15 or 16 a day (ours: a stable bit per tile and day, not the exe's RNG), 255 after 16..17 days.
MEADOW_DAYS = 18
_MEADOW = {}


def meadow_regrowth(g, x, y, day=None):
    """The original's regrowth byte of meadow tile (x, y) on `day` (default today); 255 = grown."""
    d0 = g.__dict__.get("grass_bare", {}).get((x, y))
    if d0 is None:
        return 255
    v = 0
    for k in range(1, (g.day if day is None else day) - d0 + 1):
        v += 15 + ((x * 31 + y * 17 + d0 * 7 + k * 13) >> 2 & 1)
        if v > 255:
            return 255
    return v


def picture_regrowth(g, x, y, day=None):
    """The regrowth byte the tile's meadow picture was last drawn with: figure_graze 0x004F8770 writes regrowth 0
    without terrain_resource_image, so a tile eaten today keeps the picture it had (oracle 1F-meadow2: tile
    (129, 124) at regrowth 0 shows the grown meadow, tools/meadow_check.py); the next daily regrow redraws it."""
    day = g.day if day is None else day
    h = g.__dict__.get("grass_held", {}).get((x, y))
    if h is not None and h[0] == day:
        return h[1]
    return meadow_regrowth(g, x, y, day)


def _meadow_grid(g):
    """The map's meadow grid (rank 15, 8..99 on meadow tiles), read once per map."""
    if g.map_name not in _MEADOW:
        from .. import world as wmod
        hdr, blocks = wmod.read_map(g.map_name)
        n = g.world.flags.shape[0]
        _MEADOW[g.map_name] = [b["data"] for b in blocks if b["rank"] == 15][0][:n * n]
    return _MEADOW[g.map_name]


def ground_changed(g):
    """The ground pictures changed without a building / road change: the play client refetches the terrain
    (map_version) while the walking caches keyed by occ_version stay (tree_changes moves with it)."""
    g.map_version = getattr(g, "map_version", 0) + 1
    g.tree_changes = getattr(g, "tree_changes", 0) + 1


def meadow_day(g):
    """Daily (economy.produce): when an eaten meadow tile's picture index e1 changes with its regrowth, redraw."""
    bare = g.__dict__.get("grass_bare")
    if not bare:
        return
    m, n = _meadow_grid(g), g.world.flags.shape[0]
    e1 = lambda x, y, v: int((m[y * n + x] - 1) * 0.010101010101010102 * v * 0.011764705882352941)
    for (x, y), d0 in bare.items():
        if 0 < g.day - d0 <= MEADOW_DAYS and \
                e1(x, y, picture_regrowth(g, x, y)) != e1(x, y, picture_regrowth(g, x, y, g.day - 1)):
            return ground_changed(g)


def _drift(g, ticks, lo, hi, add):
    """The per-tick restlessness step (one rand(lo, hi) + add a tick), summed over `ticks`."""
    return fastrand.below_sum(g.rng, hi - lo + 1, ticks) + lo * max(0, ticks) + add * ticks


def boar_idle(g, w):
    """figure_boar 0x004BD030 (production.md "Boar"), idle side. w.ready = restlessness (+0x5C), w.task = action,
    w.wait = the timer just run (or the tick a walk began). Timers rand(51, 153) (0x0056B520).
    - 0x11 (rest): +rand(3, 10) a tick; at the end: 0x11 again while < 1800, else 0x10;
    - 0x10 (stand, boar_passive_tick 0x0056B5D0): +rand(-3, 3) + 2 a tick; at the end: 0x11 if < 1201,
      0x10 if < 2000, else 7;
    - 7 (walk, 0x0056B680 / 0x0056B420): to herd point + rand(-4..4, -4..4) (re-rolled up to 1000 times until
      passable, 0x00569D90); +rand(-10, -3) + 3 a tick; on arrival 0x10 if < 1800, else 7 again.
    The per-tick draws are summed when the timer ends (same distribution, one act). Hunters: walkers.hunt code."""
    if w.state == "walk":                       # arrived
        w.ready += _drift(g, g.tick - w.wait, -10, -3, 3)
        nxt = "x10" if w.ready < 1800 else "x7"
    elif w.task in ("x10", "x11"):
        if w.task == "x11":
            w.ready += _drift(g, w.wait, 3, 10, 0)
            nxt = "x11" if w.ready < 1800 else "x10"
        else:
            w.ready += _drift(g, w.wait, -3, 3, 2)
            nxt = "x11" if w.ready < 1201 else "x10" if w.ready < 2000 else "x7"
    else:                                       # new boar (or back from a hunt reaction)
        nxt = "x11"
    w.state = "idle"
    if nxt == "x7":
        ok = wild_walkable(g)
        n = g.world.flags.shape[0]
        ox, oy = w.origin or (w.x, w.y)
        for _ in range(1000):
            x, y = ox + g.rng.randrange(9) - 4, oy + g.rng.randrange(9) - 4
            if 0 <= x < n and 0 <= y < n and ok[y * n + x]:
                p = land_path(g, (w.x, w.y), {(x, y)}, ROUTE_MAX, ok) if (x, y) != (w.x, w.y) else []
                if p:
                    w.path, w.state, w.task, w.wait = p, "walk", "x7", g.tick
                    return schedule(g, w, 1)
                break
        nxt = "x10"
    w.task, w.wait = nxt, 51 + g.rng.randrange(103)
    schedule(g, w, w.wait + 1)                  # the timer runs out when it drops below 0


def _rest(g, w):
    """After a walk (or a failed hop): grazers 71 ticks, horses 30, then the 1/N re-rolls of 20..69."""
    if w.role in GRAZERS:
        return schedule(g, w, _wait_until_move(g, 71, 8, 20, 50))
    if w.role == "horse":
        return schedule(g, w, _wait_until_move(g, 30, 4, 20, 50))
    return schedule(g, w, 51 + g.rng.randrange(103))


def animal_count(g, role):
    """(live animals of this kind, the cap: 8 x farms of that kind) (production.md "Animal count
    limits and spawning")."""
    from . import index
    farms = sum(1 for b in index.of(g, "herd", "corral") if g.cat.spec(b.key).get("animal") == role)
    return sum(1 for w in g.walkers.values() if w.role == role), 8 * farms


def animals_spawn(g):
    """Daily (animals_spawn 0x004F8E30, cycle step 49): per kind, with 1 < count < 8 x farms, chance
    1/100 of a new animal where the last-found one stands; above the cap the last-found one dies."""
    for role in GRAZERS:
        herd = [w for w in g.walkers.values() if w.role == role]
        if not herd:
            continue
        _, cap = animal_count(g, role)
        last = max(herd, key=lambda w: w.id)
        if len(herd) > cap:
            remove(g, last)
        elif 1 < len(herd) < cap and g.rng.randrange(100) == 0:
            a = spawn_animal(g, role, last.x, last.y)
            a.ready = 1 if role == "cattle" else 0     # figure_create zeroes ready_level; cattle get 1


def month_ready(g):
    """Monthly: wool/milk readiness of sheep, goats and cattle (+rules.animal_ready_per_month, 0..100;
    the original: +9, production.md)."""
    k = g.rules.get("animal_ready_per_month", 9)
    for w in g.walkers.values():
        if w.role in GRAZERS:
            w.ready = min(100, w.ready + k)


# --- gatherers -----------------------------------------------------------------------------------------
# states: go (walk to target) -> work (wait there) -> back (walk home) -> deliver

def gatherer(g, w):
    home = g.buildings.get(w.home)
    if home is None:
        release(g, w)
        return remove(g, w)
    if w.state == "go" and (w.role in HERDERS or w.role == "rancher") and not w.arrived:
        depart_herder(g, w, home)
    if w.task == "search":                    # action 6 ends: its own search from its tile, then its route mode
        w.task = ""
        spec = economy._spec(g, home)
        if w.role == "stonecutter":           # figure_miner 0x004C1310, marble: route mode 0xB onto the tile
            t = economy.marble_search(g, spec, (w.x, w.y))
            dest = t
            p = route11(g, (w.x, w.y), t) if t is not None else None
        else:                                 # woodcutter 0x004BF060 (grown trees: regrowth 0xFF), ore miner (0):
            r = economy.resource_search(g, spec, (w.x, w.y), 0xFF if w.role == "woodcutter" else 0)
            dest, t = r if r is not None else (None, None)
            t = t or dest                     # a woodcutter stands on the tree; a miner beside his rock
            p = route3(g, (w.x, w.y), dest) if dest is not None else None
        if p is None:                         # nothing found (state 2), or no route (lost: deleted)
            release(g, w)
            return remove(g, w)
        w.target_tile, w.path, w.state = t, p, "go"
    if w.state in ("go", "back"):
        if w.path:
            here = (w.x, w.y)
            step_to(g, w, w.path.pop(0))
            if w.role == "rancher" and w.state == "back":       # the cow follows one tile behind
                cow = g.walkers.get(w.target)
                if cow is not None and cow.state == "led":
                    cow.prev, (cow.x, cow.y) = (cow.x, cow.y), here
                    cow.arrived = g.tick
                    listed(g, cow)
            elif w.role == "stonecutter" and w.state == "back":  # so does the marble cart
                c = g.walkers.get(w.link)
                if c is not None:
                    c.prev, (c.x, c.y) = (c.x, c.y), here
                    c.arrived = g.tick
                    listed(g, c)
            return schedule(g, w, tile_delay(g, w))
        if w.state == "go":
            return reach_target(g, w, home)
        return deliver_gathered(g, w, home)
    if w.state in ("work", "pause"):
        return finish_work(g, w, home)
    if w.state == "unload":                   # stonecutter at the lodge with his cart: waits for stock 0
        return deliver_gathered(g, w, home)
    if w.state == "rest":                     # urchin diver: the catch is counted 200 ticks later
        home.goods["urchin"] = min(home.goods.get("urchin", 0) + 100, 500)
    remove(g, w)


def depart_herder(g, w, home):
    """A herder leaving the farm after its wait heads for its animal's tile of this moment, not of the
    dispatch (FUN_004f7ce0 shear / FUN_004f7c40 tend set dest = the animal's x, y when the wait ends)."""
    a = g.walkers.get(w.target)
    if a is None or w.target_tile == (a.x, a.y) or a.state in ("held", "led"):
        return
    start = (w.x, w.y)
    p = tree_path(g, start, {(a.x, a.y)}, 1000)
    if p is None:
        p = tree_path(g, start, set(neighbors4(a.x, a.y)), 1000)
    if p is not None:
        w.path, w.target_tile = p, (a.x, a.y)


def sgn(v):
    return (v > 0) - (v < 0)


def reach_target(g, w, home):
    spec = g.cat.spec(home.key)
    if w.role == "hunter" and w.task == "butcher":   # action 9 arrival: the carcass is removed, 13 ticks of work
        a = g.walkers.get(w.target)
        if a is None or a.state != "carcass" or (a.x, a.y) != (w.x, w.y):
            return head_home(g, w, home)      # (the exe hunts again after 20 ticks; ours goes home empty)
        remove(g, a)
        w.state, w.anim_t0 = "work", g.tick
        return schedule(g, w, BUTCHER_TICKS)
    if w.task == "tend" and w.role in HERDERS:   # tending herder: guard by the animal (action 8, 120 ticks)
        w.state, w.anim_t0 = "work", g.tick
        return schedule(g, w, TEND_TICKS)
    if w.role in CHASERS:
        a = g.walkers.get(w.target)
        # the shearer / milker and the rancher (figure_rancher 0x004CBB00 action 0xC) walk onto the animal's tile
        herder = w.role in HERDERS or w.role == "rancher"
        near = (max(abs(a.x - w.x), abs(a.y - w.y)) < 2 if w.role == "hunter"     # hunter: Chebyshev < 2
                else abs(a.x - w.x) + abs(a.y - w.y) <= (0 if herder else 1)) if a is not None else False
        if a is not None and a.state == "carcass":
            a = None
        if a is None or not near:             # it wandered off: chase
            # herders re-route without limit (figure_shepherd 0x004B6CF0 action 0xC); hunters 12 times
            if a is not None and (herder or w.wait < 12):
                w.wait += 1
                goals = {(a.x, a.y)} if herder else set(neighbors4(a.x, a.y))
                p = land_path(g, (w.x, w.y), goals, ROUTE_MAX)
                if p is None and herder:
                    p = land_path(g, (w.x, w.y), set(neighbors4(a.x, a.y)), ROUTE_MAX)
                if p is not None and (p or not herder):
                    w.path = p
                    return schedule(g, w, tile_delay(g, w) if p else 1)
            if not (herder and a is not None and abs(a.x - w.x) + abs(a.y - w.y) <= 1):
                return head_home(g, w, home)      # (a herder settles for the next tile if it cannot step on)
        if w.role == "hunter":                # action 0xD: the shot; the boar stops and both turn to face
            a.state, a.path, a.anim_t0 = "struck", [], g.tick
            w.face = (sgn(a.x - w.x), sgn(a.y - w.y))
            a.face = (-w.face[0], -w.face[1])
            w.state, w.task, w.anim_t0 = "work", "strike", g.tick
            return schedule(g, w, STRIKE_TICKS)
        a.state = "held"
        if w.role == "rancher":               # lead the cow home: no work at the spot
            a.state = "led"
            return head_home(g, w, home)
        if herder and a.ready >= 100:         # herder_take_from_animal 0x004F7F60: shorn at the start
            w.amount, a.ready = spec["yield"], 0
    if w.role in ("stonecutter", "woodcutter") and any(
            o is not w and (o.role in MINER_TYPE if w.role == "stonecutter" else o.role == w.role) and
            o.state == "work" and (o.x, o.y) == (w.x, w.y) for o in g.walkers.values()) \
            or (w.role == "woodcutter" and not grown_tree(g, w.x, w.y)):
        # action 7 arrival (direction 8): one of its type works on this tile (action 8), or (woodcutter) the tile's
        # regrowth is not 0xFF (cut meanwhile) -> action 6 with timer 0: figure_miner searches again once past 10,
        # figure_wood_cutter on its next call (timer - 1 < 1)
        w.task = "search"
        return schedule(g, w, 11 if w.role == "stonecutter" else 1)
    if w.role == "miner" and w.target_tile is not None and any(
            o.role in MINER_TYPE and o.state == "work" and tuple(o.target_tile or ()) == tuple(w.target_tile)
            and max(abs(o.x - w.target_tile[0]), abs(o.y - w.target_tile[1])) == 1 for o in g.walkers.values()):
        w.task = "search"                     # ores: FUN_004A8650, a miner works that rock -> action 6, timer 0
        return schedule(g, w, 11)
    w.state, w.anim_t0 = "work", g.tick
    t = spec.get("work_ticks", 200)
    if home.key in ("marble_quarry", "black_marble_shop"):   # figure_miner 0x004C1310 (0x31 / 0xD5): 0x660 ticks,
        from .. import gods                                  # 0x435 while Atlas' sanctuary is active (ecx 0x00EF607C)
        if gods.active_now(g, 13):
            t = 0x435
    schedule(g, w, t)


def stumps(g):
    """Cut trees not grown back: terrain 0x1 with regrowth < 255 in the exe (ours: the g.regrow entries; the tree
    bit stays, so a stump blocks building and grazing as a tree does)."""
    rg = getattr(g, "regrow", None)
    if not rg:
        return ()
    c = getattr(g, "_stumps", None)
    if c is None or c[0] is not rg or c[1] != len(rg):
        c = g._stumps = (rg, len(rg), {(x, y) for _, x, y in rg})
    return c[2]


def grown_tree(g, x, y):
    """A tree a woodcutter takes (regrowth 0xFF): the tree bit and not a stump."""
    return bool(g.world.flags[y, x] & 0x1) and (x, y) not in stumps(g)


def regrow_days(g, r):
    """Days until a stump with regrowth byte r is a tree again: terrain_regrow (the daily tree pass, cycle step 20;
    map-terrain.md 5) adds 4 + a random bit a day, u8; a sum that wraps or reaches 255 is 255 (grown): 51-64 days
    from 0 (bugs.md 108)."""
    days = 0
    while r < 255:
        r += 4 + g.rng.randrange(2)
        days += 1
    return days


def quarry_dig(g, x, y):
    """A stonecutter's block is cut at marble tile (x, y) (figure_miner 0x004C1310 action 8; map-terrain.md 5b):
    its depth g.quarry[(x, y)] (the exe's regrowth byte, 255 untouched) goes 255 -> 100 (shallow pit) and
    100 -> 0 (deep) once all 8 neighbours are pits; 0 stays 0. The marble flag stays: a deposit never runs out."""
    if not g.world.flags[y, x] & 0x20000:
        return
    q = g.sd("quarry", {})
    d0 = q.get((x, y), 255)
    d = d0
    if d == 255:
        d = 100
    elif d == 100 and all(q.get((x + dx, y + dy), 255) <= 100
                          for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy):
        d = 0
    if d != d0:
        q[(x, y)] = d
        g.map_version = getattr(g, "map_version", 0) + 1   # the play client redraws the ground (a new pit: route
                                                            # bit 0x80, land routes avoid it: walkable's version)


def finish_work(g, w, home):
    spec = g.cat.spec(home.key)
    world = g.world
    tx, ty = w.target_tile or (w.x, w.y)
    if w.role == "woodcutter":                # 0x004BF060 action 8 end: regrowth of his tile = 0 (a stump: the tree
        if (tx, ty) in stumps(g):             # bit stays), terrain_resource_image; he brings 25 whatever the tile
            g.regrow = [r for r in g.regrow if (r[1], r[2]) != (tx, ty)]
        if world.flags[ty, tx] & 0x1:         # (a regrowth byte without the bit is never regrown)
            g.sd("regrow", []).append((g.tick + regrow_days(g, 0) * g.rules["ticks_per_day"], tx, ty))
            tree_changed(g, tx, ty)
        w.amount = spec["yield"]
    elif w.role == "stonecutter":
        # figure_miner 0x004C1310 end of work: a cart (figure 4) with 800 marble is created at his tile and
        # follows him home (action 0x11/0x12, leader = him); he walks back empty-handed
        quarry_dig(g, tx, ty)
        c = add(g, new_walker(g, role="cart", home=home.id, x=w.x, y=w.y, good=spec["output"],
                              amount=spec["yield"], state="follow", link=w.id), 51)
        w.link = c.id
    elif w.role == "miner":                   # ores: the rock does not change; action 0xD: a pause (timer + 1 a
        w.amount = spec["yield"]              # tick, action 9 once past 0x18), then home
        if w.state != "pause":
            w.state = "pause"
            return schedule(g, w, 25)
    elif w.role == "hunter":
        a = g.walkers.get(w.target)
        if w.task == "strike":                # the boar falls (action 10, a carcass); the hunter steps onto it
            if a is not None:
                a.state, a.anim_t0, a.path = "carcass", g.tick, []
                w.task, w.state, w.target_tile = "butcher", "go", (a.x, a.y)
                w.path = [] if (a.x, a.y) == (w.x, w.y) else [(a.x, a.y)]
                return schedule(g, w, tile_delay(g, w) if w.path else 1)
        elif w.task == "butcher":             # 100 meat (one load), whatever the prey
            w.amount, w.good = 100, "meat"
    elif w.role == "diver":
        w.amount = 0                          # counted after the rest at the quay
    elif w.role in HERDERS and w.task == "tend":
        rnd = w.load.get("round", [])
        others = {x.target for x in g.walkers.values() if x.role == w.role and x.task != "tend"}
        while rnd:                            # on to the next animal of its flock (0x004F7C40)
            a = g.walkers.get(rnd.pop(0))
            if a is None or a.id in others or a.state in ("held", "led"):
                continue
            p = land_path(g, (w.x, w.y), {(a.x, a.y)}, 30)
            if p is None:
                continue
            w.target, w.target_tile, w.path, w.state = a.id, (a.x, a.y), p, "go"
            return schedule(g, w, tile_delay(g, w) if p else 1)
    elif w.role in HERDERS:
        a = g.walkers.get(w.target)
        if a is not None:                     # let go after the 20 ticks (action restored)
            a.state = ""
    elif w.role == "grower":
        t = g.buildings.get(w.target)
        if t is not None:
            if w.task == "pick" and t.ripe:       # tree_pick 0x004AB080: frees the claim only here (ripe)
                w.amount = t.progress * 100 // g.rules["farm_growth_max"]
                w.good = g.cat.spec(t.key)["output"]
                t.progress, t.ripe = 0, False
                if t.claimed == w.id:
                    t.claimed = 0
            elif w.task == "tend":                # grower_tend_done 0x004AB6F0: tend 160, claim dropped
                t.tend = 160
                if t.claimed == w.id:
                    t.claimed = 0
                # grower_next_tree_to_tend 0x004AB640: the next tree claimed by it, by building id
                rnd = w.load.get("round", [])
                while rnd:
                    nxt = g.buildings.get(rnd.pop(0))
                    if nxt is None or nxt.claimed != w.id:
                        continue
                    p = land_path(g, (w.x, w.y), {(nxt.x, nxt.y)}, ROUTE_MAX)     # onto the tree
                    if p is None:
                        nxt.claimed = 0
                        continue
                    w.target, w.target_tile, w.path, w.state = nxt.id, (nxt.x, nxt.y), p, "go"
                    return schedule(g, w, tile_delay(g, w) if p else 1)
            # a picker at a tree that is no longer ripe keeps its claim (+0x2A): the exe never frees it
    head_home(g, w, home)


def grower_next_ripe_tree(g, w):
    """grower_next_ripe_tree 0x004AB770, called by lodge_send_growers 0x004AB210 when a nearer picker takes over
    a tree this grower claimed: it walks to the first other tree (by building id) still claimed by it, as a
    picker (a tender too: it picks there if the tree is ripe, else comes home empty), or home."""
    home = g.buildings.get(w.home)
    if home is None:
        return
    ids = sorted(i for i in [w.target] + list(w.load.get("round", []))
                 if i in g.buildings and g.buildings[i].claimed == w.id)
    for i in ids:
        t = g.buildings[i]
        p = land_path(g, (w.x, w.y), {(t.x, t.y)}, ROUTE_MAX)
        if p is None:
            continue
        w.load = {"round": [j for j in ids if j != i]}
        w.target, w.target_tile, w.path, w.state, w.task = t.id, (t.x, t.y), p, "go", "pick"
        return schedule(g, w, tile_delay(g, w) if p else 1)
    head_home(g, w, home)


def head_home(g, w, home):
    if w.role != "rancher":
        release(g, w)
    # as far as any trip out can go: the hunt search reaches 1000 steps (0x004D05F0, production.md), and a
    # gatherer that cannot route home is removed with its load (bugs.md 106: 80 dropped every far hunter's meat)
    if w.role == "stonecutter":               # figure_miner action 9: dest = the lodge's road access, route mode 0xB
        p = route11(g, (w.x, w.y), tuple(home.access)) if home.access is not None else None
    elif w.role in ("woodcutter", "miner"):   # action 9: dest = the road access, route mode 3
        p = route3(g, (w.x, w.y), tuple(home.access)) if home.access is not None else None
    else:
        p = land_path(g, (w.x, w.y), edge_tiles(g, home), 1000)
    if p is None:
        release(g, w)
        return remove(g, w)
    w.state, w.path = "back", p
    schedule(g, w, tile_delay(g, w) if p else 1)


def deliver_gathered(g, w, home):
    if w.role == "diver":
        w.state = "rest"
        return schedule(g, w, g.cat.spec(home.key)["after_ticks"])
    if w.role == "rancher":
        cow = g.walkers.get(w.target)
        if cow is not None and cow.state == "led":
            g.walkers.pop(cow.id, None)
            m = home.misc
            m["penned"] = m.get("penned", 0) + 1
        return remove(g, w)
    c = g.walkers.get(w.link) if w.role == "stonecutter" else None
    if c is not None:
        # action 9 arrival (0x004C1310): only into an empty lodge (+0x3C == 0) the 800 go in; else he and the
        # cart wait at the lodge, checking every tick
        if home.goods.get(c.good, 0) > 0:
            w.state = "unload"
            return schedule(g, w, 1)
        home.goods[c.good] = c.amount
        remove(g, c)
        return remove(g, w)
    if w.amount:
        good = w.good or g.cat.spec(home.key)["output"]
        n = home.goods.get(good, 0) + w.amount
        if home.kind in ("lodge", "herd"):   # lodge_receive_fruit 0x004AAF60, building_stock_add 0x004F8050
            n = min(n, g.cat.spec(home.key).get("cap", 500))   # (sheep/goat farm): += load, clamp 500, the rest lost
        home.goods[good] = n
    remove(g, w)


def release(g, w):
    if w.role in CHASERS and w.task != "tend":
        a = g.walkers.get(w.target)
        if a is not None and a.state in ("held", "led", "struck"):
            a.state = ""
    if w.role == "grower":
        for tid in [w.target] + list(w.load.get("round", [])):
            t = g.buildings.get(tid)
            if t is not None and t.claimed == w.id:
                t.claimed = 0


def neighbors4(x, y):
    return [(x, y - 1), (x + 1, y), (x, y + 1), (x - 1, y)]


# --- water: wharves and boats ---------------------------------------------------------------------

def _water(g, x, y):
    """Water a boat can be on: not under a short (< 4 tiles) bridge (pathfinding.md §7.3)."""
    return (g.world.inside(x, y) and g.world.flags[y, x] & 0x4 and g.world.occ[y, x] == 0
            and (x, y) not in g.__dict__.get("bridge_short", ()))


def water_exit(g, x, y, size, connected=False):
    """The first tile of the footprint's edge ring (g_adjacent_ring 0x005F1680: clockwise from the top-left,
    production.md "Shore buildings") that is water without a building and whose 8 neighbours all have the water
    bit (building_water_exit 0x004A3FD0: FUN_004A1FF0(4) + FUN_004A6CA0 > 7; a wharf's own water half counts as
    water). For a wharf that is the tile straight out in front of its water half (bugs.md 173).
    connected=True: the old rule (part of >= 8 connected water tiles), kept for land-placed wharves of old saves."""
    ring = ([(x + i, y - 1) for i in range(size)] + [(x + size, y + i) for i in range(size)] +
            [(x + i, y + size) for i in range(size - 1, -1, -1)] + [(x - 1, y + i) for i in range(size - 1, -1, -1)])
    w = g.world
    for t in ring:
        if not _water(g, *t):
            continue
        if not connected:
            n = w.flags.shape[0]
            if all(0 <= t[0] + dx < n and 0 <= t[1] + dy < n and w.flags[t[1] + dy, t[0] + dx] & 0x4
                   for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dx or dy):
                return t
            continue
        seen, q = {t}, deque([t])
        while q and len(seen) < 8:
            cx, cy = q.popleft()
            for nb in neighbors4(cx, cy):
                if nb not in seen and _water(g, *nb):
                    seen.add(nb)
                    q.append(nb)
        if len(seen) >= 8:
            return t
    return None


def bfs4(ok, start, goal, n=228):
    """The plain route BFS (route_distance 0x00588920 and its variants, pathfinding.md section 3): from start (= 1)
    over the tiles open in `ok`, neighbours N, E, S, W, until the goal is popped. {tile index: distance}."""
    s, e = start[1] * n + start[0], goal[1] * n + goal[0]
    dist = {s: 1}
    q = deque([s])
    while q:
        t = q.popleft()
        if t == e:
            break
        d = dist[t] + 1
        x = t % n
        for j in (t - n, t + 1 if x < n - 1 else -1, t + n, t - 1 if x > 0 else -1):
            if 0 <= j < n * n and j not in dist and ok[j]:
                dist[j] = d
                q.append(j)
    return dist


def trace(dist, start, goal, step=1, n=228):
    """route_trace 0x0058BC80 (mode 8: step 1 over the 8 directions, mode 4: step 2, the 4 straight ones): from the
    goal back to the start, each step to the lowest reached distance among the neighbours (g_dir8_offsets order,
    never straight back); a tie goes to the direction facing the start (direction_to 0x0058CFF0), else to the first
    in order. A diagonal two levels lower wins, so 8-way routes cut corners. Fails past 499 steps. The tiles after
    start up to the goal, or None (pathfinding.md section 4.2)."""
    sx, sy = start
    x, y = goal
    best = dist.get(y * n + x, 0)
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
        choice, best = -1, dist[y * n + x]
        for k in range(0, 8, step):
            if k == back:
                continue
            dx, dy = DIR8[k]
            v = dist.get((y + dy) * n + x + dx, 0)
            if v and (v < best or (v == best and (k == want or choice == -1))):
                choice, best = k, v
        if choice < 0 or len(out) >= 499:
            return None
        out.append((x, y))
        x, y = x + DIR8[choice][0], y + DIR8[choice][1]
        back = (choice + 4) & 7
    out.reverse()
    return out


def route0(g, start, goal, ok=None):
    """Route mode 0 (figure_find_route 0x004D8220: route_distance 0x00588920 + route_trace(8) 0x0058BC80), used by
    soldiers: bfs4 over walkable land, then trace(8). The tiles after start up to the goal, or None (pathfinding.md
    sections 3, 4.2)."""
    if start == goal:
        return []
    n = g.world.flags.shape[0]
    ok = ok or walkable(g)
    if not ok[goal[1] * n + goal[0]]:             # a closed goal is never reached: the flood would only fill the map
        return None
    return trace(bfs4(ok, start, goal, n), start, goal, 1, n)


def route11(g, start, goal):
    """Route mode 0xB (figure_find_route 0x004D8220 case 11; stonecutters, figure_miner 0x004C1310 for the marble
    quarry 0x31 and the black marble shop 0xD5): the roads-only search 0x0058A6C0 (route & 0x10C: roads, roadblocks,
    ramp roads) reaching the goal -> route_trace(4), else route_trace(8); no road route: 0x0058A2D0 (route & 0x19C:
    land, roads and the quarried pits) -> route_trace(8). The tiles after start up to the goal, or None."""
    if start == goal:
        return []
    n = g.world.flags.shape[0]
    d = bfs4(road_list(g), start, goal, n)
    if goal[1] * n + goal[0] in d:
        return trace(d, start, goal, 2, n) or trace(d, start, goal, 1, n)
    return trace(bfs4(quarry_walkable(g), start, goal, n), start, goal, 1, n)


def route3(g, start, goal):
    """Route mode 3 (figure_find_route 0x004D8220 case 3; woodcutters 0x004BF060, ore miners 0x004C1310, caravans,
    hunters): the dest must be land (route & 0x11C), else no route; the roads-only search 0x0058A6C0 (route & 0x10C)
    reaching the goal -> route_trace(4), else route_trace(8); no road route: route_distance 0x00588920 (route &
    0x11D, walkable()) -> route_trace(8). The tiles after start up to the goal, or None."""
    if start == goal:
        return []
    n = g.world.flags.shape[0]
    ok = walkable(g)
    if not ok[goal[1] * n + goal[0]]:
        return None
    d = bfs4(road_list(g), start, goal, n)
    if goal[1] * n + goal[0] in d:
        return trace(d, start, goal, 2, n) or trace(d, start, goal, 1, n)
    return trace(bfs4(ok, start, goal, n), start, goal, 1, n)


def listed_bfs(g, start):
    """route_find_listed_tile 0x00588B20's flood from start, run to the end: {tile: (pop order, distance)} for the
    tiles it pops: the start (distance 1, whatever its route bits) and every tile reached 4-way (N, E, S, W) over
    route & 0x11D (walkable()). The search returns the listed tile popped first. Cached per occupancy version."""
    ver = (_ver(g), len(g.__dict__.get("quarry") or ()))
    cache = getattr(g, "_listed", None)
    if cache is None or cache[0] != ver:
        cache = g._listed = (ver, {})
    t = cache[1].get(start)
    if t is not None:
        return t
    n = g.world.flags.shape[0]
    nn = n * n
    ok = walkable(g)
    s = start[1] * n + start[0]
    out = {s: (0, 1)}
    q = deque([s])
    k = 1
    while q:
        i = q.popleft()
        d = out[i][1] + 1
        x = i % n
        for j in (i - n, i + 1 if x < n - 1 else -1, i + n, i - 1 if x > 0 else -1):
            if 0 <= j < nn and j not in out and ok[j]:
                out[j] = (k, d)
                k += 1
                q.append(j)
    cache[1][start] = out
    return out


DIR8 = ((0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1))   # g_dir8_offsets: -0xE4, -0xE3, +1, ...


def ship_grid(g):
    """grid_ship 0x01053330 (ship_grid_build_rect 0x00587B90, full rebuild 0x00587E20), [y][x] raw: 0xFF blocked =
    not water (terrain bit 4), off the map (0x80000), any of the 8 neighbours without the water bit, a short
    bridge's piece (13/14; Poseidon games also the long bridge pieces 4/10); 0xFB = a neighbour without deep water or
    off-map (0x4080000); 0xFE = the play area's outer ring (logical x or y < 1 or > size - 2); 0 = open water.
    Tiles outside the play rectangle stay 0xFF. Buildings are not looked at (a wharf's water half has its land half
    for a neighbour). Cached per map version and bridge set."""
    import numpy as np
    w = g.world
    shorts = getattr(g, "bridge_short", None) or ()
    pos = bool(getattr(g, "poseidon", False))
    key = (getattr(g, "map_version", 0), len(getattr(g, "bridges", None) or ()), len(shorts), pos)
    c = getattr(g, "_shipgrid", None)
    if c is not None and c[0] == key:
        return c[1]
    f = w.flags
    n = f.shape[0]
    water = (f & 0x4) != 0
    deep = (f & 0x4080000) != 0
    pw = np.pad(water, 1, constant_values=False)
    pd = np.pad(deep, 1, constant_values=False)
    all_w = np.ones((n, n), bool)
    all_d = np.ones((n, n), bool)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx or dy:
                all_w &= pw[1 + dy:n + 1 + dy, 1 + dx:n + 1 + dx]
                all_d &= pd[1 + dy:n + 1 + dy, 1 + dx:n + 1 + dx]
    ok = water & ((f & 0x80000) == 0) & all_w
    for x, y in shorts:
        ok[y, x] = False
    if pos:
        for (x, y), pc in (getattr(g, "bridge_pieces", None) or {}).items():
            if pc in (4, 10):
                ok[y, x] = False
    grid = np.full((n, n), 0xFF, np.uint8)
    grid[ok & ~all_d] = 0xFB
    grid[ok & all_d] = 0
    (ox, oy), (W, H) = w.origin, w.size
    edge = np.zeros((n, n), bool)
    edge[oy, :] = edge[oy + H - 1, :] = edge[:, ox] = edge[:, ox + W - 1] = True
    grid[edge & (grid == 0)] = 0xFE
    inside = np.zeros((n, n), bool)
    inside[oy:oy + H, ox:ox + W] = True
    grid[~inside] = 0xFF
    g._shipgrid = (key, grid)
    return grid


def ship_ok(g, x, y):
    """A tile ships can be on (grid_ship != 0xFF)."""
    sg = ship_grid(g)
    return 0 <= x < sg.shape[1] and 0 <= y < sg.shape[0] and sg[y, x] != 0xFF


def water_path(g, start, goals, max_dist=ROUTE_MAX):
    """A ship's route (figure_find_route 0x004D8220, water_mode 1: trade ships, fishing boats, triremes, enemy
    ships). The distance field is 0x0058D500: a 4-way BFS (N, E, S, W) over grid_ship != 0xFF from the ship (start =
    1; a start on 0xFF fails); entering a 0xFE edge tile costs 5 and a popped 0xFE tile goes back to the queue up to 4
    times first. The tracer 0x0058DCE0 walks back from the destination over the 8 neighbours (g_dir8_offsets order
    N, NE, E, SE, S, SW, W, NW; never straight back), each step to the lowest reached distance, so ships sail
    diagonally; a tie goes to the later neighbour (param 0; the exe's water_mode 2 figures break ties by
    grid_random & 3 == the call's rng & 3: not ported). Fails past 499 steps. Returns the tiles after start up to the
    nearest goal. Ours: the exe fills the whole field (<= 50000 pops); we stop once a goal is reached, which gives
    the same field below the goal's distance unless a 0xFE tile was queued (then the search runs to the end)."""
    if start in goals:
        return []
    sg = ship_grid(g)
    n = sg.shape[0]
    if sg[start[1], start[0]] == 0xFF:
        return None
    dist = {start: 1}
    q = deque([start])
    goal = None
    requeue = {}
    edge = False
    pops = 0
    while q:
        t = q.popleft()
        pops += 1
        if pops > 50000:
            break
        if sg[t[1], t[0]] == 0xFE:
            k = requeue.get(t, 0)
            requeue[t] = k + 1
            if k < 4:
                q.append(t)
                continue
        d = dist[t]
        if d > max_dist:
            continue
        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            nb = (t[0] + dx, t[1] + dy)
            if nb in dist or not (0 <= nb[0] < n and 0 <= nb[1] < n):
                continue
            v = sg[nb[1], nb[0]]
            if v == 0xFF:
                continue
            if v == 0xFE:
                edge = True
                dist[nb] = d + 5
            else:
                dist[nb] = d + 1
            if goal is None and nb in goals:
                goal = nb
            q.append(nb)
        if goal is not None and not edge:
            break
    if goal is None:
        return None
    out, t, back = [], goal, -1
    while dist[t] >= 2:
        best, bd = -1, dist[t]
        for i, (dx, dy) in enumerate(DIR8):
            if i == back:
                continue
            v = dist.get((t[0] + dx, t[1] + dy), 0)
            if v and v <= bd:
                best, bd = i, v
        if best < 0:
            return None
        out.append(t)
        if len(out) > 499:
            return None
        t = (t[0] + DIR8[best][0], t[1] + DIR8[best][1])
        back = (best + 4) & 7
    return out[::-1]


def spawn_boat(g, b, tile):
    w = new_walker(g, role="boat", home=b.id, x=tile[0], y=tile[1], origin=tile, state="rest")
    b.walkers.append(w.id)
    return add(g, w, 1)


def boat(g, w):
    """Fishing boat (figure_fishing_boat 0x004B5F10): rest at the mooring -> sail to a fishing point -> fish
    408..2040 ticks -> sail back to the mooring -> unload 204..1020 ticks -> stock 100 -> rest 51 ticks."""
    from . import economy, labor, wild
    home = g.buildings.get(w.home)
    if home is None:
        return g.walkers.pop(w.id, None)
    if w.path:
        step_to(g, w, w.path.pop(0))
        return schedule(g, w, tile_delay(g, w))
    spec = g.cat.spec(home.key)
    if w.state == "rest":
        goals = set(wild.fishing_points(g))
        p = water_path(g, (w.x, w.y), goals) if goals else None
        if p is None:
            home.reason = "no fishing grounds reachable by water"
            return schedule(g, w, g.rules["ticks_per_day"] * 4)
        w.state, w.path = "go", p
        return schedule(g, w, tile_delay(g, w) if p else 1)
    if w.state == "go":
        w.state = "fish"
        t = economy.ladder(labor.staffing(g, home), spec["catch_ticks"])
        from .. import gods
        if gods.active_now(g, 1):             # Poseidon's sanctuary active (ecx 0x00EF5E0C): x 66 / 100
            t = t * 66 // 100
        return schedule(g, w, t)
    if w.state == "fish":
        p = water_path(g, (w.x, w.y), {w.origin})
        if p is None:
            return remove(g, w)
        w.state, w.path, w.amount, w.good = "back", p, 100, "fish"
        return schedule(g, w, tile_delay(g, w) if p else 1)
    if w.state == "back":                     # moored again (action 10): unloading wait by staffing
        w.state = "unload"
        return schedule(g, w, economy.ladder(labor.staffing(g, home), spec.get("unload_ticks") or [1] * 5))
    # unloaded: the catch sets the stock (assignment, production.md); then idle 51 ticks (action 6)
    home.goods["fish"] = max(home.goods.get("fish", 0), 100)
    w.state, w.amount = "rest", 0
    schedule(g, w, 51)


from . import crime, risk, trade, monuments  # noqa: E402  (circular: imported last)
