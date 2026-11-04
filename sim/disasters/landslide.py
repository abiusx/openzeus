"""Landslide (scenario type 5): a cliff face slides into the plain below it. Track 1L-5, docs/logic/events.md
"Terrain disasters" (Landslide).

The exe (Zeus.exe GOG 2.1):
- At the map start (city_init_from_map -> FUN_00506BC0) `landslide_candidates` 0x00505D90 scans the play area row by
  row for slide sites of size 5, then 4, 3, 2 until one size has any: FUN_00505FF0(tile, size) tries the 4
  directions N E S W (landslide_spread 0x00506330 without applying) and keeps the best score (a tie: rng_15 %
  ties == 0 takes the later one); a site enters the list (FUN_00506A20) unless its box overlaps a listed site with a
  score >= its own (a lower one is dropped). The 10 best by score are kept (0x00F13480, 0x24 each: tile, dir, size,
  score, box; count 0x00F135E8). FUN_00506C50 then marks every site's plateau tiles with terrain bit 0x80000000.
- event_landslide 0x004732B0 (on its date, DONE at once): landslide point +0x1C (0x00902F4C / 0x00902F58, 1..3) ->
  the object 0x00F13478's vtable +0 `wm_sub_505bf0` 0x00505BF0: every listed site is re-scored now
  (FUN_00505FF0, which re-picks the direction); among the valid ones the nearest to the point wins (103969 - dx^2 -
  dy^2, logical); FUN_005061A0 applies it, then the cliff pass over the whole map (FUN_0045F7E0 / FUN_0051D760 ->
  FUN_00521520(3)) and FUN_005061E0 on the slide's box +-3 (a building on a cliff tile falls; cliff tiles lose
  trees, rocks, water, roads, scrub, meadow, rubble). Returns the tile: message 0xDE (title 0xC79, body 0xC7A,
  reason 0xC7B) located there, no alert; then the chain (+0x24).
- landslide_spread(tile, base elevation, dir, size): rows r = -size..size along dir, columns c = -size..size across;
  r <= 0: a half disc (half width trunc(sqrt(size^2 - r^2))) of free tiles (FUN_00505F30) at the base elevation ->
  the plateau, raised by 1; r >= 1: each column walks out until it meets a higher tile (the cliff; a lower one or a
  0x80000 tile fails), the tiles before it plateau as well. Every column must meet the cliff. Then column by
  column, one row further each pass, the cliff is cut down (a tile higher than the column's level - 1: lowered by
  1, FUN_00505F90 must allow it) until as many tiles were lowered as raised. Score trunc((top - base) * balance *
  3.0 / depth) x 10 with a building in the box, x 3 with a road (FUN_00505B50 on each changed tile: road bit off,
  building destroyed, debris dust, the new elevation).
Ours: g.landslide = {"sites": [...], "marks": set of tiles} made at a new game (scenario.new_game, only for an
episode with a type-5 record); the tie draws of the map-start scan use a Random seeded from the game's seed (the
exe's RNG state at the map start can't be ours), the event's re-scoring uses the scenario RNG.
"""
import math
import random

import numpy as np

from .. import scenario

N = 228
OFF = (-228, -227, 1, 229, 228, 227, -1, -229)       # 0x005D9418: N NE E SE S SW W NW
FREE = 0x17370116                                  # FUN_00505F30 / FUN_00505F90: none of these on the tile or around
OFFMAP = 0x80000
POINT_D = 0x19621                                  # wm_sub_505bf0: 103969 - dx^2 - dy^2


class Grid:
    """Flat lists of the terrain, elevation and building grids (the exe's flat index y * 228 + x); `apply` writes
    the elevation back to the world."""

    def __init__(self, g):
        w = g.world
        self.g = g
        self.F = w.flags.ravel().tolist()
        self.E = w.elev.astype(np.int16).ravel().tolist()
        self.R = w.road.ravel().tolist()
        self.B = (w.occ != 0).ravel().tolist()
        self.changed = []

    def ok30(self, t):
        """FUN_00505F30: free tile, its 8 neighbours free and none lower than elevation - 1."""
        F, E = self.F, self.E
        if F[t] & FREE:
            return False
        e = E[t] - 1
        for o in OFF:
            u = t + o
            if not 0 <= u < N * N or F[u] & FREE or E[u] < e:
                return False
        return True

    def ok90(self, t):
        """FUN_00505F90: free tile, its 8 neighbours free and none higher than elevation + 1."""
        F, E = self.F, self.E
        if F[t] & FREE:
            return False
        e = E[t] + 1
        for o in OFF:
            u = t + o
            if not 0 <= u < N * N or F[u] & FREE or E[u] > e:
                return False
        return True

    def set_elev(self, t, e):
        """FUN_00505B50: the road bit off, the building on the tile destroyed, debris (play mode), the elevation."""
        g, w = self.g, self.g.world
        x, y = t % N, t // N
        if self.F[t] & 0x40 or self.R[t]:
            self.F[t] &= ~0x40
            w.flags[y, x] = int(w.flags[y, x]) & ~0x40 & 0xFFFFFFFF
            if w.road[y, x]:
                w.road[y, x] = False
                self.R[t] = False
        if w.occ[y, x]:
            from . import _destroy
            _destroy(g, x, y)
            self.B[t] = bool(w.occ[y, x])
        debris(g, x, y)
        self.E[t] = e
        w.elev[y, x] = e
        self.changed.append((x, y))


def debris(g, x, y):
    """collapse_debris_spawn(x, y, 1, 1, 1, 0): dust (sim/effects.py, play mode)."""
    from .. import effects
    effects.debris(g, x, y, 1)


def spread(G, t, base, d, p, apply=False):
    """landslide_spread 0x00506330 -> (score, box [x0, y0, x1, y1], roads, buildings, plateau tiles)."""
    F, E = G.F, G.E
    D, P = OFF[d], OFF[(d + 2) & 7]
    box = [N + 1, N + 1, -1, -1]
    cnt = [0, 0]
    flat = []
    n = 2 * p + 1
    found = [0] * n
    want = [0] * n
    bal = level = 0

    def take(u, e_new):
        x, y = u % N, u // N
        box[0] = min(box[0], x)
        box[1] = min(box[1], y)
        box[2] = max(box[2], x)
        box[3] = max(box[3], y)
        if F[u] & 0x40 or G.R[u]:
            cnt[0] += 1
        if G.B[u]:
            cnt[1] += 1
        if apply:
            G.set_elev(u, e_new)

    for r in range(-p, p + 1):
        if r < 1:
            hw = math.isqrt(p * p - r * r)
            for c in range(-hw, hw + 1):
                u = t + r * D + c * P
                if not 0 <= u < N * N or F[u] & OFFMAP or E[u] != base or not G.ok30(u):
                    return 0, box, cnt[0], cnt[1], flat
                level += 1
                flat.append(u)
                take(u, E[u] + 1)
        else:
            for c in range(-p, p + 1):
                i = c + p
                if found[i]:
                    continue
                u = t + c * P + r * D
                if not 0 <= u < N * N or F[u] & OFFMAP:
                    return 0, box, cnt[0], cnt[1], flat
                e = E[u]
                if e < base:
                    return 0, box, cnt[0], cnt[1], flat
                if e > base:
                    want[i] = base + 1
                    bal += 1
                    found[i] = r
                else:
                    if not G.ok30(u):
                        return 0, box, cnt[0], cnt[1], flat
                    level += 1
                    flat.append(u)
                    take(u, e + 1)
    if not all(found):
        return 0, box, cnt[0], cnt[1], flat
    top, deep = base, 0
    while level >= 1:
        for c in range(-p, p + 1):
            i = c + p
            k = found[i]
            deep = max(deep, k)
            u = t + k * D + c * P
            found[i] = k + 1
            if not 0 <= u < N * N or F[u] & OFFMAP:
                return 0, box, cnt[0], cnt[1], flat
            e = E[u]
            top = max(top, e)
            if e < want[i]:
                return 0, box, cnt[0], cnt[1], flat
            if e == want[i]:
                bal -= 1
            else:
                if not G.ok90(u):
                    return 0, box, cnt[0], cnt[1], flat
                level -= 1
                bal += 1
                want[i] = e - 1
                take(u, e - 1)
        if bal < -n:
            return 0, box, cnt[0], cnt[1], flat
    s = int((top - base) * bal * 3.0 / deep)
    f = 10.0 if cnt[1] else 3.0 if cnt[0] else 1.0
    s = max(0, int(s * f + 0.5))
    return s, box, cnt[0], cnt[1], flat


def best_dir(G, t, p, rnd):
    """FUN_00505FF0: the best of the 4 directions -> (score, dir, box)."""
    base = G.E[t]
    best, dr, bx, ties = 0, 0, None, 0
    for d in (0, 2, 4, 6):
        s, box, _, _, _ = spread(G, t, base, d, p)
        if not s:
            continue
        if best < s:
            best, dr, bx, ties = s, d, list(box), 0
        elif s == best:
            ties += 1
            if rnd() % ties == 0:
                dr, bx = d, list(box)
    return best, dr, bx


def _quick(G, p):
    """Tiles that can hold a site of size p in some direction (a pre-filter, ours: a higher tile within p along one of
    N E S W and a free tile; landslide_spread fails on the others)."""
    w = G.g.world
    E = w.elev.astype(np.int16)
    free = ((w.flags & np.uint32(FREE | OFFMAP)) == 0)
    hi = np.zeros((N, N), bool)
    pad = np.pad(E, p, constant_values=-1)
    for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
        for r in range(1, p + 1):
            hi |= pad[p + dy * r:p + dy * r + N, p + dx * r:p + dx * r + N] > E
    return free & hi


def candidates(g, rnd=None):
    """landslide_candidates 0x00505D90 + FUN_00506C50: the sites and the marked plateau tiles."""
    if rnd is None:
        r = random.Random((getattr(g, "seed", 1) or 1) * 7919 + 5)
        rnd = lambda: r.randrange(32768)
    G = Grid(g)
    off = (g.world.flags & np.uint32(OFFMAP)) != 0
    nodes = []                                       # the linked list, head first
    for p in (5, 4, 3, 2):
        ok = _quick(G, p) & ~off
        for t in np.flatnonzero(ok.ravel()).tolist():
            s, d, bx = best_dir(G, t, p, rnd)
            if s:
                _add(nodes, dict(t=t, dir=d, size=p, score=s, box=bx))
        if nodes:
            break
    arr = []
    for nd in nodes:                                 # the 10 best: a later one replaces the first lowest when higher
        if len(arr) < 10:
            arr.append(nd)
            continue
        k = 0
        for i in range(1, len(arr)):
            if arr[i]["score"] < arr[k]["score"]:
                k = i
        if arr[k]["score"] < nd["score"]:
            arr[k] = nd
    marks = set()
    for a in arr:                                    # FUN_00506BE0: every direction that holds marks its plateau
        base = G.E[a["t"]]
        for d in (0, 2, 4, 6):
            s, _, _, _, flat = spread(G, a["t"], base, d, a["size"])
            if s:
                marks.update(flat)
    return [dict(x=a["t"] % N, y=a["t"] // N, dir=a["dir"], size=a["size"], score=a["score"], box=a["box"])
            for a in arr], sorted(marks)


def _add(nodes, nd):
    """FUN_00506A20: an overlapping site with a score >= the new one keeps it out; lower ones are dropped; the new
    site goes to the head."""
    x0, y0, x1, y1 = nd["box"]
    i = 0
    while i < len(nodes):
        o = nodes[i]
        a0, b0, a1, b1 = o["box"]
        if x1 < a0 or y1 < b0 or a1 < x0 or b1 < y0:
            i += 1
            continue
        if nd["score"] <= o["score"]:
            return
        del nodes[i]
        i = max(0, i - 1)
    nodes.insert(0, nd)


def new_game(g):
    """city_init_from_map's FUN_00506BC0, for episodes with a landslide record."""
    sc = getattr(g, "scenario", None)
    if sc is None or not any(ev["type"] == 5 for ev in sc.events):
        return
    pts = (getattr(g.world, "points", None) or {}).get("landslide") or []
    if not any(pts):
        return
    sites, marks = candidates(g)
    g.landslide = dict(sites=sites, marks=marks, slides=[])


def event(g, ev):
    """event_landslide 0x004732B0."""
    if not scenario.due(g, ev):
        return
    ev["flags"] |= scenario.DONE
    k = ev["city"] - 1
    pts = (getattr(g.world, "points", None) or {}).get("landslide") or []
    p = pts[k] if 0 <= k < len(pts) else None
    if p is not None:
        tile = slide(g, ev["city"])
        if tile is not None:
            from .. import messages
            messages.post(g, 0xC79, 0xC7A, meta=dict(at=[tile[0], tile[1]], kind=0xDE))   # FUN_00521A70(0xDE, 0, the slide's tile)
    t = scenario.get(g, ev.get("chain", -1))
    if t is not None and t["flags"] & scenario.TEMPLATE and t["id"] != ev["id"]:     # FUN_004694A0
        scenario.chain(g, ev)


def slide(g, point):
    """wm_sub_505bf0 0x00505BF0: the valid site nearest the point slides. -> its tile (x, y) or None."""
    st = g.__dict__.get("landslide")
    if st is None:
        if getattr(g, "scenario", None) is None:
            return None
        sites, marks = candidates(g)
        st = g.landslide = dict(sites=sites, marks=marks, slides=[])
    pts = g.world.points.get("landslide") or []
    k = min(2, max(0, point - 1))
    px, py = pts[k] if k < len(pts) and pts[k] else (-1, -1)
    G = Grid(g)
    rnd = lambda: scenario.rng15(g)
    best, bd, bdir = None, 0, 0
    for s in st["sites"]:
        t = s["y"] * N + s["x"]
        sc_, d, _ = best_dir(G, t, s["size"], rnd)
        dist = POINT_D - (s["y"] - py) ** 2 - (s["x"] - px) ** 2 if sc_ else 0
        if best is None or bd < dist:
            best, bd, bdir = s, dist, d
    if best is None or not bd:
        return None
    t = best["y"] * N + best["x"]
    _, box, _, _, _ = spread(G, t, G.E[t], bdir, best["size"], apply=True)
    box = [box[0] - 3, box[1] - 3, box[2] + 3, box[3] + 3]
    refresh(g, box)
    st["slides"].append(dict(x=best["x"], y=best["y"], dir=bdir, size=best["size"], tick=g.tick, tiles=G.changed,
                             box=box))           # map_tiles_update_images(box, 3): play mode's repaint (bugs.md 366)
    g.map_version = getattr(g, "map_version", 0) + 1
    from ..systems import roads
    roads.rebuild(g)
    return best["x"], best["y"]


def refresh(g, box):
    """The cliff passes after the slide: map_tiles_update_images(box +- 3, 3) twice, FUN_0045F7E0 and FUN_0051D760 on
    the whole map (tools/terrain_cliffs.py's pass 1/2 with map_elevation_project's clean-up; it also settles pits and
    steps, FUN_0045FA20; a former ramp needs 3 passes to become a plain cliff), the first three followed by
    FUN_005061E0 on the box: a building on a cliff tile (0x200, not rubble) falls, cliff tiles lose 0x003018C7."""
    import os
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                                    "tools"))
    import terrain_cliffs as tcl
    from . import _rand, _destroy
    w = g.world
    rand = _rand(g)
    x0, y0 = max(0, box[0]), max(0, box[1])
    x1, y1 = min(N - 1, box[2]), min(N - 1, box[3])
    for k in range(4):                         # rect, rect, FUN_0045F7E0, FUN_0051D760 (no FUN_005061E0 after it)
        f = w.flags & np.uint32(~0x40 & 0xFFFFFFFF)
        f[w.road] |= 0x40
        _, _, fl, extra = tcl.cliffs(f, w.elev, rand, 0, full=True)
        w.elev[:] = np.asarray(extra["elev"]).astype(np.int16).clip(0, 255).astype(np.uint8)
        w.flags[:] = fl
        if k == 3:
            break
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                v = int(w.flags[y, x])
                if v & 0x200 and w.occ[y, x] and not v & 0x1000:
                    _destroy(g, x, y)
        sub = w.flags[y0:y1 + 1, x0:x1 + 1]
        cl = (sub & 0x200) > 0
        sub[cl] &= np.uint32(0xFFCFE738)
        w.road[y0:y1 + 1, x0:x1 + 1] &= ~cl


def changed_tiles(g):
    """Every tile whose elevation a landslide changed (play mode: the terrain is re-sent with the new map_version)."""
    st = g.__dict__.get("landslide")
    return [t for s in (st or {}).get("slides", []) for t in s["tiles"]]


scenario.register(5, event, "sim.disasters.landslide")
