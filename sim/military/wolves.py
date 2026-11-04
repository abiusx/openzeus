"""Wolves (docs/logic/military.md "Wolves"): packs of 7 at the map's wolf points (0x004E0160), refilled one wolf per
27 formation passes (0x004DF570); each wolf runs fig_handler_wolf 0x004BD4A0: four needs (fatigue, restlessness,
hunger, fear) pick between standing (0x10), lying (0x11), roaming near the pack (7), looking for prey (0xD),
chasing it (0xB) and stepping away from a herder (0xF). Prey: sheep, goats, cows within 7 rings; herders and
bulls make wolves flee. Fights by contact (units.py).

Walker fields: origin = pack point, task = action ("x10", "x11", "x7", "xD", "xB", "xF", "x13"), needs = [n0..n3],
timer_end = tick the idle timer runs out, prey = target walker id.
Ours vs the exe: idle wolves act at their timer's end, and every 8 ticks (the exe's anim_frame == 1 check) only
while a herder or bull is within 8 tiles; the herder's walk toward the wolf (its action 0xF) is not drawn, only
its effect (the wolf flees a step); Artemis (a complete sanctuary) shoots a wolf that reaches its prey (sim/gods fight.py).
"""
from ..systems import walkers
from . import units

PACK = 7
REFILL_PASSES = 27      # F+0x75 > 26
SPAWN_RING = [(0, 0), (0, -1), (1, 0), (0, 1), (-1, 0), (1, -1), (1, 1), (-1, 1), (0, 0), (1, 0), (0, 1), (1, 1),
              (2, 0), (2, 1), (1, 2), (0, 2)]                                          # 0x005F2418
TEST_RING = [(-2, 1), (-2, 0), (-1, 1), (-1, 2), (-1, -1), (-2, 2), (-1, 2), (-2, 1)] + [(0, 0)] * 8    # 0x005F2518
BLOCK = 0x103AD02A | 0x4 | 0x40000      # 0x00569D90(t, 0) + water, marsh
HERDERS = ("shepherd", "goatherd")
PREY = ("sheep", "goat", "cattle")
WATCH = HERDERS + PREY
SPEED = 7               # Figure_model col 8: 12 ticks a tile


def rng(g):
    from . import mrng
    return mrng(g)


def passable(g):
    """Flat list: the wolf terrain test (trees, meadow, roads pass; buildings, water, rock, walls do not)."""
    from ..systems.services import occ_version
    v = occ_version(g)
    c = getattr(g, "_wolf_ok", None)
    if c is None or c[0] != v:
        w = g.world
        ok = ((((w.flags & BLOCK) == 0) & (w.occ == 0)) | w.road).ravel().tolist()
        c = g._wolf_ok = (v, ok)
    return c[1]


def points(g):
    """The map's wolf points (World.wolf_points, map-terrain.md) and test packs (`wolves X Y`)."""
    from . import state
    return [tuple(p) for p in (getattr(g.world, "wolf_points", None) or [])] + \
        [tuple(p) for p in state(g).get("extra_packs", [])]


def packs(g):
    from . import state
    return state(g).setdefault("packs", {})


def pack_members(g, p):
    return [w for w in g.walkers.values() if w.role == "wolf" and w.origin == p]


def day(g, recount=True):
    """formations_pass 0x004DF570 at the end of formations_update (cycle steps 5 and 29): map start 7 per point; then
    an under-strength pack counts F+0x75 + 1 a pass, past 26 one wolf. The live count F+0x28 is recounted by
    formations_refresh 0x004DE210 at step 5 only (recount)."""
    for p in points(g):
        day_point(g, tuple(p), recount)


def day_point(g, p, recount=True):
    n = g.world.flags.shape[0]
    ok = passable(g)
    pk = packs(g)
    if p not in pk:
        pk[p] = 0
        for i in range(PACK):
            for k in range(16):
                dx, dy = SPAWN_RING[(i + k) % 16]
                x, y = p[0] + dx, p[1] + dy
                if 0 <= x < n and 0 <= y < n and ok[y * n + x]:
                    _spawn(g, p, x, y, timer=rng(g).randrange(25) * 4)
                    break
        return
    from . import state
    cnt = state(g).setdefault("pack_n", {})
    if recount or p not in cnt:
        cnt[p] = len([w for w in pack_members(g, p) if w.anim != "die"])
    if cnt[p] >= PACK:
        return
    pk[p] += 1
    if pk[p] > REFILL_PASSES - 1:
        pk[p] = 0
        start = rng(g).randrange(16)
        for k in range(16):
            j = (start + k) % 16
            tx, ty = p[0] + TEST_RING[j][0], p[1] + TEST_RING[j][1]
            if 0 <= tx < n and 0 <= ty < n and ok[ty * n + tx]:
                x, y = p[0] + SPAWN_RING[j][0], p[1] + SPAWN_RING[j][1]     # sic: an untested tile
                if 0 <= x < n and 0 <= y < n:
                    _spawn(g, p, x, y, timer=10)
                break


def _spawn(g, p, x, y, timer):
    return units.spawn(g, "wolf", x, y, delay=max(1, timer + 1), origin=p, task="x13", needs=[0, 0, 0, 0],
                       prey=0, hidden=True, face=(0, -1), timer_end=0)


# --- needs --------------------------------------------------------------------------------------

def _add(w, k, v):
    w.needs[k] = max(0, min(15, w.needs[k] + v))


def hi(w, k):
    return w.needs[k] > 6


def decide(g, w):
    if hi(w, 3):
        return enter(g, w, "xF")
    if hi(w, 0):
        return enter(g, w, "x11")
    if hi(w, 1):
        return enter(g, w, "x7")
    return enter(g, w, "x10")


# --- the scan (wolf_scan 0x0056A9F0) --------------------------------------------------------------

def _watch_list(g):
    """Ids of herders, flocks and cattle, refreshed daily (walkers spawned since are seen the next day)."""
    from . import state
    st = state(g)
    day = g.tick // 51
    c = st.get("_watch")
    if c is None or c[0] != day:
        c = st["_watch"] = (day, [w.id for w in g.walkers.values() if w.role in WATCH])
    return c[1]


def scan(g, w):
    """(herder, prey): the nearest herder or bull within 7 rings (own tile included), and the nearest live sheep,
    goat or cow in rings 1..7 not farther than that herder."""
    herder = prey = None
    hd = pd = 99
    for i in _watch_list(g):
        o = g.walkers.get(i)
        if o is None or o.anim == "die" or o.state == "held":
            continue
        d = max(abs(o.x - w.x), abs(o.y - w.y))
        if d > 7:
            continue
        if o.role in HERDERS or (o.role == "cattle" and getattr(o, "bull", False)):
            if d < hd:
                herder, hd = o, d
        elif d >= 1 and d < pd:
            prey, pd = o, d
    if herder is not None and prey is not None and pd > hd:
        prey = None
    return herder, prey


def threat_near(g, w):
    for i in _watch_list(g):
        o = g.walkers.get(i)
        if o is not None and (o.role in HERDERS or getattr(o, "bull", False)) and \
                max(abs(o.x - w.x), abs(o.y - w.y)) <= 8:
            return True
    return False


# --- actions --------------------------------------------------------------------------------------

def enter(g, w, task):
    """wolf_enter_action 0x00569F90."""
    r = rng(g)
    w.task = task
    w.hidden = False
    w.path = []
    if task == "x10":
        w.timer_end = g.tick + r.randrange(50) + 100
        _add(w, 2, 1)
        _add(w, 1, 2)
        return _wait(g, w)
    if task == "x11":
        w.timer_end = g.tick + r.randrange(50) + 100
        w.face = walkers_dir(r.randrange(8))
        _add(w, 2, 2)
        _add(w, 1, 1)
        _add(w, 0, -4)
        return _wait(g, w)
    if task == "x7":
        _add(w, 0, 2)
        _add(w, 2, 4)
        _add(w, 1, -4)
        dest = _roam_dest(g, w)
        if dest is None:
            return enter(g, w, "x10")
        return _go(g, w, dest, "x7")
    if task == "xD":
        _add(w, 0, 2)
        _add(w, 2, -4)
        _add(w, 1, -2)
        herder, prey = scan(g, w)
        if prey is not None:
            if herder is not None:
                return enter(g, w, "xF")
            w.prey = prey.id
            return enter(g, w, "xB")
        return walkers.schedule(g, w, 1)            # one tick in 0xD, then decide()
    if task == "xB":
        p = g.walkers.get(w.prey)
        if not units.alive(p):
            return decide(g, w)
        return _go(g, w, (p.x, p.y), "xB")
    if task == "xF":
        _add(w, 3, -4)
        _add(w, 2, -2)
        _add(w, 0, 2)
        herder, _ = scan(g, w)
        t = _flee_step(g, w, herder) if herder is not None else None
        if t is None:
            return decide(g, w)
        return _go(g, w, t, "xF")
    return enter(g, w, "x10")


DIRS = [(0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1)]


def walkers_dir(d):
    return DIRS[d & 7]


def _dir_of(dx, dy):
    sx, sy = (dx > 0) - (dx < 0), (dy > 0) - (dy < 0)
    return DIRS.index((sx, sy)) if (sx, sy) in DIRS else 0


def _flee_step(g, w, herder):
    """0x00569AF0: the adjacent tile away from the herder (d, d+1, ..., d+6) with desirability < 20, reachable."""
    n = g.world.flags.shape[0]
    ok = passable(g)
    d = _dir_of(w.x - herder.x, w.y - herder.y)
    for k in range(7):
        dx, dy = DIRS[(d + k) & 7]
        x, y = w.x + dx, w.y + dy
        if 0 <= x < n and 0 <= y < n and ok[y * n + x] and g.world.des[y, x] < 20:
            return (x, y)
    return None


def _roam_dest(g, w):
    """0x0056A460: near home (Chebyshev < 6) a tile -3..+4 around the wolf at its own elevation (99 tries);
    farther, a tile by the pack point (table 0x005F2518)."""
    r = rng(g)
    n = g.world.flags.shape[0]
    ok = passable(g)
    hx, hy = w.origin
    el = g.world.elev
    if max(abs(w.x - hx), abs(w.y - hy)) < 6:
        for _ in range(100):
            x, y = w.x + 4 - r.randrange(8), w.y + 4 - r.randrange(8)
            if 0 <= x < n and 0 <= y < n and ok[y * n + x] and el[y, x] == el[w.y, w.x]:
                return (x, y)
        return None
    start = r.randrange(16)
    for k in range(16):
        dx, dy = TEST_RING[(start + k) % 16]
        x, y = hx + dx, hy + dy
        if 0 <= x < n and 0 <= y < n and ok[y * n + x]:
            return (x, y)
    return (hx, hy)


def _go(g, w, dest, task):
    if dest == (w.x, w.y):
        w.path = []
        return walkers.schedule(g, w, 1)
    p = walkers.land_path(g, (w.x, w.y), {dest}, walkers.ROUTE_MAX, passable(g))
    if not p:
        return arrived(g, w, blocked=True)
    w.path = p
    walkers.schedule(g, w, 1)


def _wait(g, w):
    """Idle: act at the timer's end, or every 8 ticks while a herder is near (herder sightings)."""
    end = w.timer_end + 1
    if threat_near(g, w):
        end = min(end, g.tick + 8)
    walkers.schedule(g, w, max(1, end - g.tick))


def act(g, w):
    if w.anim == "die":
        return units.act_dying(g, w)
    if w.anim == "fight":
        return units.fight_tick(g, w)
    t = w.task
    if t == "x13":                                  # hidden at spawn, then 6 -> 0x11
        w.hidden = False
        return enter(g, w, "x11")
    if t in ("x10", "x11"):
        if threat_near(g, w):
            herder, _ = scan(g, w)
            if herder is not None:
                _add(w, 3, 2)
                if herder.state == "work" and max(abs(herder.x - w.x), abs(herder.y - w.y)) <= 5:
                    return enter(g, w, "xF")         # a guarding herder (0x004F7E70) drives it off
        if g.tick < w.timer_end + 1:
            return _wait(g, w)
        if t == "x10":
            if hi(w, 3): return enter(g, w, "xF")
            if hi(w, 0): return enter(g, w, "x11")
            if hi(w, 2): return enter(g, w, "xD")
            if hi(w, 1): return enter(g, w, "x7")
            return enter(g, w, "x10")
        if hi(w, 3): return enter(g, w, "xF")
        if w.needs[0] >= 5: return enter(g, w, "x11")
        if hi(w, 1): return enter(g, w, "x7")
        if hi(w, 2): return enter(g, w, "xD")
        return enter(g, w, "x10")
    if t == "xD":
        return decide(g, w)
    if t == "xB" and w.prey and not w.path:
        p = g.walkers.get(w.prey)
        if p is not None and p.anim == "die":          # eating: until the carcass is gone
            return walkers.schedule(g, w, max(1, p.anim_t0 + units.DYING - g.tick))
    if w.path:
        nxt = w.path[0]
        if not passable(g)[nxt[1] * g.world.flags.shape[0] + nxt[0]]:
            w.path = []
            return arrived(g, w, blocked=True)
        w.path.pop(0)
        units.step(g, w, nxt)
        from . import contact
        if contact.on_enter(g, w):
            return None
        return walkers.schedule(g, w, units.tile_ticks(g, w, SPEED))   # arrival is handled when the step ends
    return arrived(g, w)


def arrived(g, w, blocked=False):
    t = w.task
    if t == "x7":
        if hi(w, 2): return enter(g, w, "xD")
        if hi(w, 3): return enter(g, w, "xF")
        return enter(g, w, "x10")
    if t == "xF":
        if hi(w, 3): return enter(g, w, "xF")
        if hi(w, 0): return enter(g, w, "x11")
        if hi(w, 2): return enter(g, w, "xD")
        return enter(g, w, "x10")
    if t == "xB":
        p = g.walkers.get(w.prey)
        if blocked:
            if hi(w, 3): return enter(g, w, "xF")
            if hi(w, 0): return enter(g, w, "x11")
            if hi(w, 1): return enter(g, w, "x7")
            return enter(g, w, "x10")
        if not units.alive(p) or p.id not in g.walkers:
            if p is not None and p.anim == "die" and p.id in g.walkers:
                _artemis(g, w)                          # 0x0056AF80: in a fight (5) whose target fell
                return walkers.schedule(g, w, max(1, p.anim_t0 + units.DYING - g.tick))
            w.prey = 0
            return decide(g, w)
        if (p.x, p.y) != (w.x, w.y):
            return enter(g, w, "xB")                    # re-aim at the prey's tile of now
        fights = units.can_engage(g, p)
        if fights:                                      # figure_tile_contact, then Artemis (0x0056AF80)
            units.start_fight(g, w, p)
        _artemis(g, w)
        return None if fights else walkers.schedule(g, w, 12)
    return enter(g, w, "x10")


def _artemis(g, w):
    """The chase handler 0x0056AF80: a wolf at its prey (after figure_tile_contact) or in a fight whose target fell
    calls Artemis (sanctuary complete): she comes out at her sanctuary and shoots it, 0x4A/0x4B (sim/gods)."""
    try:
        from .. import gods
    except ImportError:
        return
    f = getattr(gods, "summon_artemis", None)
    if f is not None:
        f(g, w)


def fight_over(g, w):
    """figure_fight_end: back to the saved action (0xB on the carcass, or what it was doing)."""
    if w.task == "xB":
        return arrived(g, w)
    return decide(g, w)


def look(g, w):
    """Play mode: the wolf's picture block per action (walkers.json wolf: stand 233, lie 234)."""
    if getattr(w, "hidden", False):
        return ["hidden", 0, 0, 0, 0, 0, 0, 0, "", False]
    if w.anim:
        return None
    if w.task in ("x10", "x11") or (w.task == "xB" and not w.path):
        blk = "lie" if w.task == "x11" else "stand"
        f = w.face or (0, 1)
        return ["work", getattr(w, "anim_t0", 0), getattr(w, "timer_end", g.tick + 100), f[0], f[1], 0, 0, 0, blk, False]
    return None


def died(g, w, by):
    if by is not None and by.role not in ("boar", "sheep", "goat", "cattle"):
        from .hooks import an
        g.message(f"{an(by.role)} killed a wolf at ({w.x},{w.y})")      # ours: the exe logs no message
