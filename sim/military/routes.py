"""Route mode 2 (docs/logic/pathfinding.md section 5): the military grid and the exe's weighted route search.

grid(g)        grid_military 0x01046820 as military_grid_build_rect 0x00502BA0 builds it (flat list, raw y * N + x)
search(...)    route_search 0x00502EE0 (mode 0, limit 100000), line by line: the distance grid, the ring queue and
               its pop order
route2(g, a, b) figure_find_route 0x004D8220 case 2: route_search, then route_trace(8) 0x0058BC80

Used by the monsters (route mode 2: a bad monster resting, or with flag 0x100 in the rampage; sim/heroes) and the
invaders (enemy_figure_update 0x00500B70 writes +0x72 = 2 every tick, 0x00500BBF).
"""
import heapq

from ..systems import walkers

N = 228
NN = N * N
LIMIT = 100000                      # figure_find_route: route_search_call(x, y, dx, dy, 0, 100000)


# --- grid_military -------------------------------------------------------------------------------------------

def grid(g):
    """grid_military over the whole map, per military_grid_build_rect 0x00502BA0 (the first test that matches):

      terrain & 0x80000 (off-map) or & 0x10004 == 0x10004 (water + beach)     -1
      terrain & 0x8000 (ours: a tower or gatehouse tile)                      4
      road + water (0x44) with a bridge piece (0x00CB4B08 != 0)               5  (cost 2)
      water                                                                   -2
      road                                                                    0
      ramp 0x400                                                              2  (cost 0)
      cliff 0x200                                                             -1
      building (terrain & 8) by type: storehouse 0x3A, 0x3D, trading post 0x3E, palace 0x75: 1; gatehouse 0x83: 4;
        burning ruins 0xA9: -1; orchard trees 0x23 / 0x24 / 0xD9, avenue 0x76, boulevard 0x7E: 0; a composite not
        100..114 by its piece (not started 0 (0x00546530), attackable 1 (0x005463B0), else -1); 0xA4: -1; else 1
      wall 0x4000                                                             3
      tree / marble / reeds (0x60001), rubble 0x1000, garden 0x20             0
      terrain & 0x2DFED66F (rock, ore kinds, 0x1000000, 0x8000000, ...)       -1
      else                                                                    0
    Cached per building change, wall breach and composite piece change."""
    from ..systems.services import occ_version
    from . import contact, state
    from .. import heroes
    from ..systems import index
    c = contact.cache(g)
    mons = [m for m in index.of(g, "monument") if "pieces" in m.misc]
    ver = (occ_version(g), state(g).get("breaches", 0), heroes.pieces_version(g, mons),
           len(getattr(g, "bridges", None) or ()))
    gm = c.get("inv_grid")
    if gm is not None and gm[0] == ver:
        return gm[1]
    import numpy as np
    w = g.world
    f = w.flags.astype(np.int64) & ~0x40          # ours' road is World.road (flag 0x40 bits of cleared map roads stay)
    occ = w.occ
    road = w.road
    out = np.zeros((N, N), np.int8)
    done = np.zeros((N, N), bool)

    def put(mask, v):
        m = mask & ~done
        out[m] = v
        done[m] = True

    put(((f & 0x80000) != 0) | ((f & 0x10004) == 0x10004), -1)
    tg = np.zeros((N, N), bool)
    for b in index.of(g, "tower", "gatehouse"):
        tg |= occ == b.id
    put(((f & 0x8000) != 0) | tg, 4)
    br = np.zeros((N, N), bool)
    for x, y in (getattr(g, "bridges", None) or ()):
        br[y, x] = True
    water = (f & 0x4) != 0
    put(water & road & br, 5)
    put(water, -2)
    put(road, 0)
    put((f & 0x400) != 0, 2)
    put((f & 0x200) != 0, -1)
    bld = (occ != 0) & ~done
    if bld.any():
        lut = np.ones(int(occ.max()) + 1, np.int8)
        for b in g.buildings.values():
            if b.id < len(lut):
                lut[b.id] = _building_value(g, b)
        bv = lut[occ]
        for m in mons:                           # composite pieces (heroes.piece_grid): by piece
            if _zid(g, m) is not None and 100 <= _zid(g, m) <= 114:
                continue
            for tiles, v in heroes.piece_grid(g, m):
                for x, y in tiles:
                    if 0 <= x < N and 0 <= y < N and occ[y, x] == m.id:
                        bv[y, x] = v
        out[bld] = bv[bld]
        done |= bld
    put((f & 0x4000) != 0, 3)
    put(((f & 0x60001) != 0) | ((f & 0x1000) != 0) | ((f & 0x20) != 0), 0)
    put((f & 0x2DFED66F) != 0, -1)
    lst = out.ravel().tolist()
    c["inv_grid"] = (ver, lst)
    c.pop("inv_fields", None)
    return lst


def _zid(g, b):
    return g.cat.spec(b.key).get("zeus_id")


def _building_value(g, b):
    """The building branch of 0x00502BA0 for a plain building (composites: by piece, in grid)."""
    if b.kind == "road":
        return 0
    if b.kind == "ruin":                          # 0xA9 burning ruins
        return -1
    if b.kind == "orchard" or b.kind == "avenue":  # 0x23 / 0x24 / 0xD9 orchard trees, 0x76 / 0x7E
        return 0
    if b.key == "gardens":                        # garden terrain 0x20 (no building bit in the exe): 0
        return 0
    return 1


# --- route_search 0x00502EE0 ---------------------------------------------------------------------------------

def _cost(v):
    """Step cost by grid_military value: 3 wall 40, 4 tower / gatehouse 60, 1 building 10, 5 bridge 2, else 0."""
    return 40 if v == 3 else 60 if v == 4 else 10 if v == 1 else 2 if v == 5 else 0


class Search:
    """route_search's state from one start: g_grid_route_distance (0 = not reached, start 1), route_queue (a list:
    the exe's ring of 0xCB10 entries never wraps, a tile is queued once), head, the last popped distance (local_4)
    and the pop count. The pop order does not depend on the goal (it decides only where the search stops), so the
    search is kept and resumed for the next goal from the same start (the field and the trace are those of a fresh
    search: tiles reached after the goal was popped are farther than it and never on its trace).

    Pop (the exe's linear scan, done with buckets): the head when its distance equals the last popped one, else
    the first queued tile after the head with that distance, else the smallest distance queued (the head first
    if it has it, else its first tile in queue order) becomes the new level; the popped slot takes the head's
    tile (route_queue[i] = route_queue[head]), head + 1. Not the goal: pop count + 1 (past the limit the search
    stops), neighbours N, E, S, W not reached with grid value 0..5 get distance + 1 + cost and are queued."""

    __slots__ = ("gm", "dist", "q", "head", "local", "count", "popped", "pend", "buckets", "vals", "over")

    def __init__(self, gm, s):
        self.gm = gm
        self.dist = [0] * NN
        self.dist[s] = 1
        self.q = [s]
        self.head = 0
        self.local = 0
        self.count = 0
        self.popped = bytearray(NN)
        self.pend = None
        self.buckets = {1: [0]}
        self.vals = [1]
        self.over = False

    def _push_pos(self, p, v):
        b = self.buckets.get(v)
        if b is None:
            b = self.buckets[v] = []
            heapq.heappush(self.vals, v)
        heapq.heappush(b, p)

    def _first(self, v):
        """The first queue position after the head whose tile has distance v, or None."""
        b = self.buckets.get(v)
        if not b:
            return None
        q, dist, head = self.q, self.dist, self.head
        while b and (b[0] <= head or dist[q[b[0]]] != v):
            heapq.heappop(b)
        return b[0] if b else None

    def _min_after(self):
        """The smallest distance queued after the head (None if none)."""
        vals = self.vals
        while vals:
            v = vals[0]
            if self._first(v) is not None:
                return v
            heapq.heappop(vals)
            self.buckets.pop(v, None)
        return None

    def _expand(self, t):
        gm, dist, q = self.gm, self.dist, self.q
        d = dist[t] + 1
        x = t % N
        for n in (t - N, t + 1 if x < N - 1 else -1, t + N, t - 1 if x > 0 else -1):
            if 0 <= n < NN and dist[n] == 0:
                v = gm[n]
                if 0 <= v < 6:
                    nd = d + _cost(v)
                    dist[n] = nd
                    q.append(n)
                    self._push_pos(len(q) - 1, nd)
        self.head += 1
        if self.head >= len(q):
            self.over = True

    def run(self, e):
        """Search on until tile e is popped; True if it was (now or before)."""
        if self.popped[e]:
            return True
        if self.over:
            return False
        if self.pend is not None:               # the last goal: popped, not expanded (a fresh search goes on)
            t, self.pend = self.pend, None
            self.count += 1
            if self.count > LIMIT:
                self.over = True
                return False
            self._expand(t)
            if self.over:
                return False
        while True:
            t = self._pop()
            if t == e:
                self.pend = t
                return True
            self.count += 1
            if self.count > LIMIT:
                self.over = True
                return False
            self._expand(t)
            if self.over:
                return False

    def _pop(self):
        q, dist = self.q, self.dist
        head = self.head
        hv = dist[q[head]]
        if hv <= self.local:
            p = head
        else:
            p = self._first(self.local)
            if p is None:
                m = self._min_after()
                if m is None or hv <= m:
                    p, self.local = head, hv
                else:
                    p, self.local = self._first(m), m
        t = q[p]
        if p != head:
            q[p] = q[head]
            self._push_pos(p, dist[q[p]])
        self.popped[t] = 1
        return t

    def run_pops(self, limit):
        """route_search with no goal (dest -1 / -2: never popped): tiles are expanded until the pop count passes
        `limit` (the pop past it is not expanded) or the queue runs out. A fresh Search only."""
        while not self.over:
            t = self._pop()
            self.count += 1
            if self.count > limit:
                self.over = True
                return
            self._expand(t)


def trace8(dist, start, goal):
    """route_trace(8) 0x0058BC80 on a distance list (0 = not reached): from goal back to start, each step to the
    lowest distance among the 8 neighbours (g_dir8_offsets order, never straight back), a tie to the direction
    facing the start (direction_to 0x0058CFF0), else the first; past 499 steps it fails. The tiles after start up
    to goal, or None."""
    sx, sy = start
    x, y = goal
    best = dist[y * N + x]
    if best < 1:
        return None
    out, back = [], -1
    D8 = walkers.DIR8
    while best > 1:
        if sx < x:
            want = 7 if sy < y else 6 if sy == y else 5
        elif sx == x:
            want = 0 if sy < y else 4 if sy > y else 8
        else:
            want = 1 if sy < y else 2 if sy == y else 3
        choice, best = -1, dist[y * N + x]
        for k in range(8):
            if k == back:
                continue
            dx, dy = D8[k]
            nx, ny = x + dx, y + dy
            v = dist[ny * N + nx] if 0 <= nx < N and 0 <= ny < N else 0
            if v and (v < best or (v == best and (k == want or choice == -1))):
                choice, best = k, v
        if choice < 0 or len(out) >= 499:
            return None
        out.append((x, y))
        x, y = x + D8[choice][0], y + D8[choice][1]
        back = (choice + 4) & 7
    out.reverse()
    return out


_KEEP = 64                          # searches kept per grid (by start tile)


def search(g, start):
    """The Search from start over the current grid (kept per grid and start)."""
    from . import cache
    gm = grid(g)
    c = cache(g)
    s = c.get("route2")
    if s is None or s[0] is not gm or len(s[1]) > _KEEP:
        s = c["route2"] = (gm, {})
    k = start[1] * N + start[0]
    st = s[1].get(k)
    if st is None:
        st = s[1][k] = Search(gm, k)
    return st


def route2(g, start, goal):
    """figure_find_route case 2: route_search(start, goal, 0, 100000), then route_trace(8). When route_search fails
    the exe tries route_search_ship 0x00503A60 (a 4-way BFS over grid_military >= 0): the grid holds no value >= 6,
    so that BFS reaches the same tiles and fails as well. The tiles after start up to goal, or None."""
    if start == goal:
        return []
    gx, gy = goal
    if not (0 <= gx < N and 0 <= gy < N):
        return None
    st = search(g, start)
    if not st.run(gy * N + gx):
        return None
    return trace8(st.dist, start, goal)
