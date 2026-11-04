"""Dragging a road, as the exe does it (docs/logic/map-terrain.md "Road drag"; oracle tools/oracle_roads.py).

roads_drag_place 0x0049ACB0(commit, x1, y1, x2, y2), on the exe's grids:
1. Each drag end in turn (start, then end): unless it is a building tile (terrain 8) of a type other than roadblock
   0x7B, boulevard 0x7E, avenue 0x76: terrain & 0x5361227 (tree, rock, water, garden 0x20, cliff, rubble, marble,
   reeds, ore kinds, 0x1000000, deep water) refuses the drag, except a crossable crack (FUN_0058CAD0) and a ramp
   (0x400: FUN_00460290 re-stamps its pictures); a wall (0x4000) refuses it. Beach is allowed.
2. FUN_0058C3E0: breadth-first flood of the whole map from the start (N, E, S, W; a ring queue that never fills).
   A tile is entered when: not within 3 of the play area's edge (map_near_play_edge 0x00496080), route grid & 0x88
   clear, terrain & 0x10060001 clear (tree, marble, reeds, 0x10000000), and either a building tile of type 0x7B /
   0x7E / 0x76, or a non-building tile whose route grid (0x005876F0) has no "blocked" bit 2 (or a crossable crack).
   Route-grid decor bit 1 (tile objects 0x00666930, FUN_0058CB90): none in ours (pathfinding.md section 2).
3. FUN_0058CE40: from the end back to the start, at each tile first the sides facing the start (table 0x006432AC by
   direction_to 0x0058CFF0), stepping to the first side with 0 < distance < this tile's. Each tile is made road
   (road_set_tile 0x0049FF10: counted when it had no road; clears garden 0x20) BEFORE the step, so a trace that
   fails leaves the tiles it set: a tile with distance < 1 (unless roadblock 0x7B / type 0xA4), a garden tile
   (0x20) or an uncrossable crack stops it, and after 399 tiles it stops (the 400th is never set).
4. On success the pictures are updated (and, committing, the route grid); a failed commit keeps the tiles set and
   they are charged (build_commit 0x00498910: cost = count x col0).
"""
import numpy as np

N = 228
STEP = ((0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1))    # 0x0064326C, by direction 0..7
PREF = ((0, 2, 6, 4), (0, 2, 6, 4), (2, 4, 0, 6), (2, 4, 0, 6),                   # 0x006432AC: sides tried per
        (4, 6, 2, 0), (4, 6, 2, 0), (6, 0, 4, 2), (6, 0, 4, 2))                   # direction to the start
ON_ROAD = (0x7B, 0x7E, 0x76)        # building types a road may be dragged over: roadblock, boulevard, avenue
TRACE_OK = (0x7B, 0xA4)             # end tiles the trace takes at distance < 1
END_MASK = 0x5361227                # roads_drag_place: terrain refused at a drag end
FLOOD_MASK = 0x10060001             # FUN_0058C3E0: terrain refused anywhere
LIMIT = 400                         # FUN_0058CE40: local_8 > 399 stops the trace


def direction_to(x, y, tx, ty):
    """direction_to 0x0058CFF0: 0 N, 1 NE, ..., 7 NW from (x, y) toward (tx, ty); 8 = same tile."""
    if tx < x:
        return 7 if ty < y else 6 if ty == y else 5
    if tx == x:
        return 0 if ty < y else 4 if ty > y else 8
    return 1 if ty < y else 2 if ty == y else 3


def near_edge(size, d=3):
    """map_near_play_edge(x, y, d) 0x00496080 for every raw tile (False off the play area, map_in_play_area
    0x00496010), with the play area's corners from FUN_00495E90 (W x H centred in the 228 grid)."""
    W, H = size
    x0, y0 = (N - W) // 2, (N - H) // 2
    x1, y1 = x0 - 1 + W, y0 - 1 + H
    cx, cy = (x1 + x0) // 2, (y1 + y0) // 2
    y, x = np.mgrid[0:N, 0:N]
    e, s = x > cx, y > cy
    inside = np.where(e, np.where(s, x + y <= x1 + 1 + cy, x - y <= x1 - cy),
                      np.where(s, cx - y1 <= x - y, x0 + cy <= x + y))
    near = np.where(e, np.where(s, x1 + 1 + cy < x + y + d, x1 - cy < x - y + d),
                    np.where(s, x - y - d < cx - y1, x - d + y < x0 + cy))
    return inside & near


def route_blocked(T):
    """Bit 2 ("blocked") of the route grid 0x005876F0 for tiles WITHOUT a building (terrain 8), by its case order
    (pathfinding.md section 2): off-map or water + beach; road (incl. bridges, ramp roads) open; ramp / garden open;
    cliff blocked; quarried marble (0x80) and 0x10000000 not blocked here (the flood's terrain mask refuses both);
    a stale building bit 0x8000 without a building: nothing set; beach, tree, rubble, marble, reeds on dry land
    open; else terrain & 0x2DFFD66F blocked."""
    T = T.astype(np.int64)
    out = np.zeros(T.shape, bool)
    done = np.zeros(T.shape, bool)

    def put(m, v):
        m = m & ~done
        out[m] = v
        done[m] = True
    put(((T & 0x80000) != 0) | ((T & 0x10004) == 0x10004), True)
    put((T & 0x40) != 0, False)
    put((T & 0x420) != 0, False)
    put((T & 0x200) != 0, True)
    put((T & 0x20000) != 0, False)              # 0x80 (regrowing) or on: refused by FLOOD_MASK anyway
    put((T & 0x10000000) != 0, False)           # 0x20: refused by FLOOD_MASK anyway
    put((T & 0x8000) != 0, False)
    dry = (T & 0x4) == 0
    put(dry & ((T & 0x71001) != 0), False)
    put((T & 0x2DFFD66F) != 0, True)
    return out


class Grids:
    """The exe's view of the map for one drag. T: terrain (u32, flat, exe bits incl. 8 building and 0x40 road);
    btype: building type per tile (0 none); edge: near_edge(); crack(i, T): FUN_0058CAD0 for a cracked rock tile
    (rock 2 with piece 0x80) or None if the map has no cracks; cracked: set of such tile indices."""
    def __init__(self, T, btype, edge, cracked=(), crack=None):
        self.T = np.asarray(T, np.uint32).ravel()
        self.btype = np.asarray(btype).ravel()
        self.edge = np.asarray(edge, bool).ravel()
        self.cracked = set(cracked)
        self.crack = crack

    def passable(self):
        """Flat bytes: 1 where FUN_0058C3E0 enters a tile (crack tiles by the T before the drag)."""
        T = self.T
        bld = (T & 8) != 0
        ok = ~self.edge & ((T & FLOOD_MASK) == 0)
        ok &= np.where(bld, np.isin(self.btype, ON_ROAD), ~route_blocked(T))
        for i in self.cracked:                      # rock is blocked; a crossable crack is not
            if not T[i] & 8 and not self.edge[i] and not T[i] & FLOOD_MASK and self.crack(i, T):
                ok[i] = True
        return ok.astype(np.uint8).tobytes()


def flood(mask, a):
    """FUN_0058C3E0 from flat tile a over mask (bytes): distances (1 = start, 0 = not reached). The play area is
    inside the edge band, so no neighbour index leaves the grid."""
    dist = [0] * len(mask)
    dist[a] = 1
    q = [a]
    for p in q:
        d = dist[p] + 1
        for t in (p - N, p + 1, p + N, p - 1):
            if mask[t] and not dist[t]:
                dist[t] = d
                q.append(t)
    return dist


def ends_ok(G, x1, y1, x2, y2):
    """roads_drag_place's two end tests. (ok, ramp ends) - ramp ends: tiles FUN_00460290 re-stamps."""
    ramps = []
    for x, y in ((x1, y1), (x2, y2)):
        i = y * N + x
        t = int(G.T[i])
        if not t & 8 or int(G.btype[i]) in ON_ROAD:
            if t & END_MASK and not (t & 2 and i in G.cracked and G.crack(i, G.T)):
                if not t & 0x400:
                    return False, ramps
                ramps.append((x, y))
            if t & 0x4000:
                return False, ramps
    return True, ramps


def trace(G, dist, x1, y1, x2, y2):
    """FUN_0058CE40 (param_6 0: set road). Returns (ok, tiles set in order, of which new). Updates G.T."""
    T, bt = G.T, G.btype
    x, y = x2, y2
    cur = y * N + x
    placed, new = [], 0
    k = 1
    while True:
        d = dist[cur]
        if d < 1 and int(bt[cur]) not in TRACE_OK:
            return False, placed, new
        if cur in G.cracked and T[cur] & 2 and not G.crack(cur, T):
            return False, placed, new
        if T[cur] & 0x20:
            return False, placed, new
        if not T[cur] & 0x40:                       # road_set_tile: counted, garden bit cleared
            new += 1
        T[cur] = (int(T[cur]) & ~0x20 & 0xFFFFFFFF) | 0x40
        placed.append((x, y))
        dr = direction_to(x, y, x1, y1)
        if dr == 8:
            return True, placed, new
        for s in PREF[dr]:
            dx, dy = STEP[s]
            n = cur + dy * N + dx
            if 0 < dist[n] < d and not (n in G.cracked and T[n] & 2 and not G.crack(n, T)):
                break
        else:
            return False, placed, new
        x, y, cur = x + dx, y + dy, n
        k += 1
        if k > LIMIT - 1:
            return False, placed, new


def drag(G, x1, y1, x2, y2, dist=None):
    """roads_drag_place on G (G.T is changed as the exe changes its terrain grid). Returns dict(ok: the trace
    reached the start, refused: an end test failed (nothing set), tiles: every tile set in trace order (end first),
    new: how many had no road (the charge), ramps: ramp ends re-stamped). dist: a flood from (x1, y1) to reuse."""
    ok, ramps = ends_ok(G, x1, y1, x2, y2)
    if not ok:
        return dict(ok=False, refused=True, tiles=[], new=0, ramps=ramps)
    a = y1 * N + x1
    if dist is None:
        mask = G.passable()
        if not mask[a]:
            return dict(ok=False, refused=False, tiles=[], new=0, ramps=ramps)
        dist = flood(mask, a)
    elif not dist[a]:
        return dict(ok=False, refused=False, tiles=[], new=0, ramps=ramps)
    ok, placed, new = trace(G, dist, x1, y1, x2, y2)
    return dict(ok=ok, refused=False, tiles=placed, new=new, ramps=ramps)


CURSOR_MASK = 0x2DFED66F            # FUN_00452B80: terrain that turns the road cursor red (road 0x40, ramp, cliff...)


def cursor(G, x, y, piece=0):
    """The road tool's cursor tile (FUN_00452B80, drawn every frame by FUN_00451820, during a drag on the terrain with
    the preview's road): (ok, picture). ok: green, the road picture tinted (AND 0x1FE3); else the red SPR_BUILD_CURSOR
    diamond. Red: within 3 of the play edge, terrain & 0x2DFED66F (a road, a ramp, cliff, tree, rock, water...)
    except a crossable crack (rock 2 + piece 0x80: its crack-road picture), treasury < -1999 (the caller's test).
    picture: (group, k) in Zeus_Terrain, font_group_entry(0x20) = SPR_ROADS (0x26 = SPR_PAVED_ROADS when piece &
    0x80) + 1 when no road N or S but one E or W (FUN_004A3760 / FUN_004A3730 with 0x40)."""
    i = y * N + x
    if not (0 <= x < N and 0 <= y < N) or G.edge[i]:
        return False, None
    t = int(G.T[i])
    if t & 2 and i in G.cracked:                    # a crack: its own road picture when crossable (FUN_0058C9C0)
        return bool(G.crack and G.crack(i, G.T)), None
    if t & CURSOR_MASK:
        return False, None
    road = lambda j: 0 <= j < N * N and bool(int(G.T[j]) & 0x40)
    k = 1 if not (road(i - N) or road(i + N)) and (road(i + 1) or road(i - 1)) else 0
    return True, ("SPR_PAVED_ROADS" if piece & 0x80 else "SPR_ROADS", k)
