"""Road networks, building road access, and road pathfinding (BFS)."""
from collections import deque

import numpy as np


def rebuild(g):
    """Label connected road networks (4-neighbour) and refresh every building's access."""
    from . import avenues
    avenues.refresh(g)                      # side strips between two roads are road too
    w = g.world
    net = np.zeros_like(w.road_net)
    nid = 0
    ys, xs = np.nonzero(w.road)
    for y0, x0 in zip(ys.tolist(), xs.tolist()):
        if net[y0, x0]:
            continue
        nid += 1
        net[y0, x0] = nid
        q = deque([(x0, y0)])
        while q:
            x, y = q.popleft()
            for nx, ny in w.road_neighbors(x, y):
                if not net[ny, nx]:
                    net[ny, nx] = nid
                    q.append((nx, ny))
    w.road_net = net
    for b in g.buildings.values():
        update_access(g, b)


def update_access(g, b):
    """Entrance = first road tile edge-adjacent to the footprint (corners excluded), in the exe's ring order
    (g_adjacent_ring 0x005F1680, house_find_road_access 0x004A3B40 / building_find_road_access 0x004A4560):
    clockwise from the top-left, so the bottom edge right to left and the left edge bottom to top (bugs.md 369:
    an elite house left of an avenue takes the segment road of its bottom row)."""
    w = g.world
    b.access, b.network = None, 0
    if b.kind == "agora":                     # its own road strip
        x, y = b.misc["strip"][0]
        b.access, b.network = (x, y), int(w.road_net[y, x])
        return
    bw, bh = b.misc.get("w", b.size), b.misc.get("h", b.size)       # monuments are rectangles
    cand = ([(b.x + i, b.y - 1) for i in range(bw)] + [(b.x + bw, b.y + i) for i in range(bh)] +
            [(b.x + i, b.y + bh) for i in range(bw - 1, -1, -1)] + [(b.x - 1, b.y + i) for i in range(bh - 1, -1, -1)])
    blocked = getattr(g, "roadblocks", ())
    av = w.avenue
    for x, y in cand:
        if not (0 <= x < w.road.shape[1] and 0 <= y < w.road.shape[0]):
            continue
        if not w.road[y, x]:
            if not av[y, x]:
                continue
            from .avenues import anchor     # an avenue side strip: its segment's road (0x004A3B40)
            x, y = anchor(w, x, y)
        if w.road[y, x] and (x, y) not in blocked:
            b.access, b.network = (x, y), int(w.road_net[y, x])
            return


def tree(g, start):
    """The road BFS from start run to the end: tile index -> (order reached, previous index).
    Cached per occupancy version (roads only change with it); path() reads its answers here."""
    from .services import occ_version
    ver = occ_version(g)
    cache = getattr(g, "_rtrees", None)
    if cache is None or cache[0] != ver or len(cache[1]) > 5000:
        w = g.world
        cache = g._rtrees = (ver, {}, w.road.ravel().tolist())
    t = cache[1].get(start)
    if t is not None:
        return t
    road = cache[2]
    n = g.world.road.shape[1]
    s = start[1] * n + start[0]
    t = {s: (0, -1)}
    k = 1
    q = deque([s])
    while q:
        i = q.popleft()
        x = i % n
        for j in (i - n, i + 1 if x < n - 1 else -1, i + n, i - 1 if x > 0 else -1):  # road_neighbors order
            if 0 <= j < n * n and road[j] and j not in t:
                t[j] = (k, i)
                k += 1
                q.append(j)
    cache[1][start] = t
    return t


def path(g, start, goals):
    """Shortest road path from start tile to any tile in goals (set). List excludes start.
    Same answer as a BFS from start that stops at the first goal it reaches."""
    if start in goals:
        return []
    n = g.world.road.shape[1]
    t = tree(g, start)
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
    return [(i % n, i // n) for i in reversed(out)]


def nearest(g, start, candidates):
    """Among candidate buildings (with access), the one with the shortest road path.
    Returns (building, path) or (None, None)."""
    goals = {}
    for b in candidates:
        if b.access is not None:
            goals.setdefault(b.access, b)
    if not goals or start is None:
        return None, None
    p = path(g, start, set(goals))
    if p is None:
        return None, None
    end = p[-1] if p else start
    return goals[end], p
