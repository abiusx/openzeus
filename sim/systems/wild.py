"""Wildlife and fishing grounds: prey animals for hunters, fishing points for boats.

The map editor places them (map-terrain.md "Herd, predator and fishing points"; World.boar_points,
fishing_spots): the sandbox has 4 boar herds of 7 (FUN_004E0160 creates them at map start) and 6
fishing points. A map's own lists stand, empty ones too (no herds); only worlds without the lists (saves
from before the map points) fall back to our old rule: points generated at forest edges / on deep water,
deterministically from the terrain. Wolves: sim/military/wolves.py.
"""
WATER, DEEP, TREE = 0x4, 0x4000000, 0x1
PREY = ("boar", "deer")                  # "deer": saves from before the boar
PREY_PER_POINT = 7


def _spread(cands, min_dist, limit):
    out = []
    for x, y in cands:
        if all(abs(x - a) + abs(y - b) >= min_dist for a, b in out):
            out.append((x, y))
            if len(out) >= limit:
                break
    return out


def fishing_points(g):
    pts = getattr(g, "_fishing_points", None)
    if pts is None and getattr(g.world, "fishing_spots", None) is not None:
        pts = g._fishing_points = list(g.world.fishing_spots)
    if pts is None:
        w = g.world
        f = w.flags
        n = f.shape[0]
        cands = [(x, y) for y in range(2, n - 2, 3) for x in range(2, n - 2, 3)
                 if all(f[y + dy, x + dx] & DEEP and w.inside(x + dx, y + dy)
                        for dy in (-2, 0, 2) for dx in (-2, 0, 2))]
        pts = g._fishing_points = _spread(cands, 25, 8)
    return pts


def prey_points(g):
    pts = getattr(g, "_prey_points", None)
    if pts is None and getattr(g.world, "boar_points", None) is not None:    # the map's points, none included
        pts = g._prey_points = list(g.world.boar_points)
    if pts is None:
        w = g.world
        f = w.flags
        n = f.shape[0]
        cands = []
        for y in range(3, n - 3, 2):
            for x in range(3, n - 3, 2):
                if f[y, x] & (TREE | WATER | 0x2 | 0x200) or not all(
                        w.inside(x + dx, y + dy) for dx in (-6, 6) for dy in (-6, 6)):
                    continue
                trees = sum(1 for dy in range(-3, 4) for dx in range(-3, 4) if f[y + dy, x + dx] & TREE)
                if 12 <= trees <= 30:                      # a clearing at a forest edge
                    cands.append((x, y))
        pts = g._prey_points = _spread(cands, 30, 12)
    return pts


# the 16 offsets a herd animal is placed at around its herd point (0x005F2518, int pairs; read from the exe
# 10-29): 8 west-ish ones, then the point itself 8 times
RING = [(-2, 1), (-2, 0), (-1, 1), (-1, 2), (-1, -1), (-2, 2), (-1, 2), (-2, 1)] + [(0, 0)] * 8


def update(g, recount=True):
    """formations_pass 0x004DF570 (cycle steps 5 and 29; production.md "Herd refill"): FUN_004E0160 creates 7 at
    each herd point at map start; a herd below 7 counts + 1 a pass, past 26 one animal (every 13.5 days, no random
    roll). The live count is formations_refresh's, at step 5 only (recount)."""
    from . import walkers
    pts = prey_points(g)
    if not pts:
        return
    timers = g.sd("herd_timers", {})
    count = g.sd("herd_count", {})
    if recount or not count:
        count.clear()
        count[None] = 0                        # counted (the step-29 pass uses step 5's count)
        for a in g.walkers.values():
            if a.role in PREY and a.origin:
                count[a.origin] = count.get(a.origin, 0) + 1
    for p in pts:
        if p in timers and timers[p] is None:  # no herd formation (a loaded save's point without one): never
            continue
        if p not in timers:                    # map start: the whole herd
            timers[p] = 0
            for k in range(count.get(p, 0), PREY_PER_POINT):     # FUN_004E0160: member k starts at RING[k]
                _spawn(g, p, k, refill=False)
            continue
        if count.get(p, 0) >= PREY_PER_POINT:
            continue
        timers[p] += 1
        if timers[p] > 26:
            timers[p] = 0
            _spawn(g, p, g.rng.randrange(16))      # formations_pass 0x004DF570: start at rng_a & 15


def _spawn(g, p, start, refill=True):
    """One boar at the first of the 16 RING offsets (from `start`, wrapping) whose tile is wild-walkable.
    A refill boar starts restless (+0x5C = 1800) and standing (action 0x10); map-start ones at 0."""
    from . import walkers
    ok = walkers.wild_walkable(g)                # 0x00569D90: trees are passable
    n = g.world.flags.shape[0]
    for i in range(16):
        dx, dy = RING[(start + i) & 15]
        x, y = p[0] + dx, p[1] + dy
        if 0 <= x < n and 0 <= y < n and ok[y * n + x]:
            a = walkers.spawn_animal(g, "boar", x, y)
            a.origin = p                       # the herd point (the herd's identity)
            a.ready = 1800 if refill else 0
            if refill:
                a.task = "x10"
            return a
    return None
