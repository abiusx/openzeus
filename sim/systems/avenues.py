"""Avenues (Zeus type 118) and boulevards (126), as the original builds them (docs/logic/avenues.md).

They are not buildings with a footprint: a drag along an existing road turns each road tile into a
cross-section ("segment") of 2 tiles (avenue: the road + one side strip) or 3 tiles (boulevard: a side
strip on both sides of the road). The road tile stays a road; side strips are walkable land that is
not road, unless they sit between two roads (then they are road too). Every tile of a segment is a
size-1 desirability source (step 37b). Houses next to a side strip reach the road through it.

State: world.avenue[y, x] (int16) = kind << 8 | the exe's draw byte for the tile:
  kind 1 avenue, 2 boulevard; draw byte: low 3 bits = position across an x-oriented segment (1..3),
  bits 3..5 = position across a y-oriented one, 0x80 = side strip (no 0x80 = the road tile).
"""
import numpy as np

KIND = {"avenue": 1, "boulevard": 2}
KEY = {1: "avenue", 2: "boulevard"}
SIDE = 0x80
BLOCK = 0x3DFFD407          # terrain bits that stop a segment tile (0x00419F90 / 0x0041B250)

# 0x005E92B8: 47 records, 8-neighbour pattern N NE E SE S SW W NW (1 road/avenue, 0 not, 2 any) ->
# image index for view orientation 0. First match wins (FUN_004A6920); the last one matches anything.
PATTERNS = [
    ("10101010", 0), ("11101010", 1), ("10111010", 2), ("10101110", 3), ("10101011", 4),
    ("11111010", 7), ("10111110", 8), ("10101111", 5), ("11101011", 6), ("11101011", 9),
    ("10111011", 10), ("11111110", 14), ("10111111", 12), ("11101111", 11), ("11111011", 13),
    ("11111111", 15), ("02111112", 23), ("02101012", 26), ("02101112", 24), ("02111012", 25),
    ("12021111", 27), ("12021010", 30), ("12021011", 28), ("12021110", 29), ("11120211", 31),
    ("10120210", 34), ("11120210", 32), ("10120211", 33), ("11111202", 19), ("10101202", 22),
    ("10111202", 20), ("11101202", 21), ("02021112", 39), ("02021012", 40), ("12020211", 41),
    ("12020210", 42), ("11120202", 35), ("10120202", 36), ("02111202", 37), ("02101202", 38),
    ("12021202", 43), ("02120212", 44), ("02020212", 48), ("12020202", 45), ("02120202", 46),
    ("02021202", 47), ("22222222", 15),
]
_PAT = [([(i, c == "1") for i, c in enumerate(p) if c != "2"], k) for p, k in PATTERNS]
# the same records' picture index per view orientation 0, 2, 4, 6 (column view/2 of 0x005E92B8, FUN_004A6920);
# presentation only (docs/play/rotation.md): the sim's road bits use view 0
VIEW_K = [(0, 0, 0, 0), (1, 4, 3, 2), (2, 1, 4, 3), (3, 2, 1, 4), (4, 3, 2, 1), (7, 6, 5, 8), (8, 7, 6, 5), (5, 8, 7, 6),
          (6, 5, 8, 7), (9, 10, 9, 10), (10, 9, 10, 9), (14, 13, 11, 12), (12, 14, 13, 11), (11, 12, 14, 13),
          (13, 11, 12, 14), (15, 15, 15, 15), (23, 19, 31, 27), (26, 22, 34, 30), (24, 20, 32, 28), (25, 21, 33, 29),
          (27, 23, 19, 31), (30, 26, 22, 34), (28, 24, 20, 32), (29, 25, 21, 33), (31, 27, 23, 19), (34, 30, 26, 22),
          (32, 28, 24, 20), (33, 29, 25, 21), (19, 31, 27, 23), (22, 34, 30, 26), (20, 32, 28, 24), (21, 33, 29, 25),
          (39, 37, 35, 41), (40, 38, 36, 42), (41, 39, 37, 35), (42, 40, 38, 36), (35, 41, 39, 37), (36, 42, 40, 38),
          (37, 35, 41, 39), (38, 36, 42, 40), (43, 44, 43, 44), (44, 43, 44, 43), (48, 47, 46, 45), (45, 48, 47, 46),
          (46, 45, 48, 47), (47, 46, 45, 48), (15, 15, 15, 15)]
assert [k[0] for k in VIEW_K] == [k for _, k in PATTERNS]
# views 2 and 6: road picture = SPR_BOUL_ROAD + ROAD_MIRROR[idx + variant] (0x005E9674, FUN_004193A0)
ROAD_MIRROR = [0, 3, 2, 1, 4, 6, 5, 8, 7, 9, 10, 11, 13, 12, 14, 15, 16, 17, 18, 23, 25, 24, 26, 19, 21, 20, 22, 31,
               33, 32, 34, 27, 29, 28, 30, 39, 40, 37, 38, 35, 36, 41, 42, 44, 43, 48, 47, 46, 45]
# side-strip run direction flag per (view/2, side group 0..3) (0x005E9664, read by FUN_00418CF0): 1 = the run's
# start/end pictures (5/3) swap
RUN_FLIP = [0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0]


def side_turn(k, view):
    """FUN_00418980: in views 2 and 6 a side picture k turns: 0..17 <-> 18..35, 37 <-> 38, 40 <-> 42."""
    if view not in (2, 6) or k < 0:
        return k
    if k < 0x12:
        return k + 0x12
    if k < 0x24:
        return k - 0x12
    return {0x25: 0x26, 0x26: 0x25, 0x28: 0x2A, 0x2A: 0x28}.get(k, k)
NB = ((0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1))
# 0x00418A20: road-pattern index -> side-strip picture offset from SPR_BOUL_SIDE_SOUTH (others: the tile
# is drawn and used as road). 0 SOUTH, 9 NORTH, 18 EAST, 27 WEST (9 pictures each), 36.. 3/2 corners.
SIDE_OF = {11: 36, 12: 37, 13: 38, 14: 39, 19: 27, 23: 9, 27: 18, 31: 0, 35: 40, 37: 41, 39: 42, 41: 43}
ROAD_FIRST, SIDE_FIRST = 239, 288    # Zeus_General SPR_BOUL_ROAD (49), SPR_BOUL_SIDE_SOUTH (.. 2_CORNERS)


def grid(w):
    if getattr(w, "avenue", None) is None:
        w.avenue = np.zeros(w.flags.shape, np.int16)
    return w.avenue


# --- placement ----------------------------------------------------------------------------------
def segment(kind, o, x, y):
    """Tiles [(x, y, draw byte)] of one segment anchored at (x, y) (0x00419C90 avenue, 0x0041AFB0
    boulevard). Avenue o: 0 road (x,y) + side west, 1 road + side north, 2 side (x,y) + road west,
    3 side + road north. Boulevard o: 0 side/road/side along x, 1 along y."""
    if kind == 1:
        return [[(x, y, 0x42), (x - 1, y, 0xC1)], [(x, y, 0x50), (x, y - 1, 0xC8)],
                [(x, y, 0xC2), (x - 1, y, 0x41)], [(x, y, 0xD0), (x, y - 1, 0x48)]][o]
    if o == 0:
        return [(x - 1, y, 0xC1), (x, y, 0x42), (x + 1, y, 0xC3)]
    return [(x, y - 1, 0xC8), (x, y, 0x50), (x, y + 1, 0xD8)]


def segment_ok(g, tiles):
    """The drag's test per segment (0x00419F90 / 0x0041B250): every tile free of buildings and of the
    BLOCK terrain bits, the road tile a road, and no parallel segment right across either end."""
    w = g.world
    av = grid(w)
    blocks = getattr(g, "roadblocks", ())
    for x, y, d in tiles:
        if not (0 <= x < w.flags.shape[1] and 0 <= y < w.flags.shape[0]):
            return False
        if w.occ[y, x] or av[y, x] or int(w.flags[y, x]) & BLOCK:
            return False
        if not d & SIDE and (not w.road[y, x] or (x, y) in blocks):
            return False
    xs, ys = [t[0] for t in tiles], [t[1] for t in tiles]
    if len(set(ys)) == 1:                       # across x: no x-oriented segment at either end
        ends, bits = [(min(xs) - 1, ys[0]), (max(xs) + 1, ys[0])], 0x07
    else:
        ends, bits = [(xs[0], min(ys) - 1), (xs[0], max(ys) + 1)], 0x38
    for x, y in ends:
        if 0 <= x < av.shape[1] and 0 <= y < av.shape[0] and av[y, x] and av[y, x] & bits:
            return False
    return True


def _road(w, x, y):
    return 0 <= x < w.road.shape[1] and 0 <= y < w.road.shape[0] and bool(w.road[y, x])


def avenue_pick(w, x, y):
    """Avenue start tile -> (orientation, x, y) or None (0x0041AEA0): beside a road, the strip goes on
    the clicked tile; on a road, the strip goes west of a north-south road, north of an east-west one."""
    if not _road(w, x, y):
        if _road(w, x - 1, y): return 2, x, y
        if _road(w, x, y - 1): return 3, x, y
        if _road(w, x + 1, y): return 0, x + 1, y
        if _road(w, x, y + 1): return 1, x, y + 1
        return None
    e, wst, s, n = _road(w, x + 1, y), _road(w, x - 1, y), _road(w, x, y + 1), _road(w, x, y - 1)
    if e and wst: return 1, x, y
    if s and n: return 0, x, y
    if e or wst: return 1, x, y
    if s or n: return 0, x, y
    return None


def plan(g, key, x1, y1, x2, y2):
    """The segments a drag from (x1, y1) to (x2, y2) would try, as [(tiles, ok)], before the isolated
    ones are dropped. Straight along the longer axis of the drag (x if dx > dy) from the start."""
    kind = KIND[key]
    w = g.world
    n = w.flags.shape[0]
    clamp = lambda v: max(0, min(n - 1, v))
    x2, y2 = clamp(x2), clamp(y2)
    if abs(x2 - x1) < 1 and abs(y2 - y1) < 1:
        return []
    along_x = abs(y2 - y1) < abs(x2 - x1)
    if kind == 1:
        p = avenue_pick(w, x1, y1)
        if p is None:                           # no road at the start: the drag direction decides (hyp)
            o = (3 if y1 <= y2 else 1) if along_x else (2 if x1 <= x2 else 0)
        else:
            o, x1, y1 = p
        if along_x and o % 2 == 0: o += 1
        if not along_x and o % 2 == 1: o -= 1
    else:
        o = 1 if along_x else 0
    if along_x:
        spots = [(x, y1) for x in range(min(x1, x2), max(x1, x2) + 1)]
    else:
        spots = [(x1, y) for y in range(min(y1, y2), max(y1, y2) + 1)]
    out = []
    av = grid(w)
    for x, y in spots:
        tiles = segment(kind, o, x, y)
        ok = segment_ok(g, tiles)
        if ok:                                  # the drag writes as it goes: later segments see it
            for tx, ty, d in tiles:
                av[ty, tx] = kind << 8 | d
        out.append((tiles, ok))
    for tiles, ok in out:                        # plan only: undo
        if ok:
            for tx, ty, d in tiles:
                av[ty, tx] = 0
    return out


def preview(g, key, x1, y1, x2, y2):
    """Play-mode ghost: [(x, y, ok, is_road_tile)] for the drag (or the single start segment while
    hovering). ok = this segment would be built: its tiles pass the test and it is not left alone
    (0x004195D0 drops a segment with no avenue/boulevard before or after it along the run)."""
    w = g.world
    av = grid(w)
    kind = KIND[key]
    segs = plan(g, key, x1, y1, x2, y2)
    if not segs:                                # hover: the segment a drag starting here would begin with
        if kind == 1:
            p = avenue_pick(w, x1, y1)
            o, x, y = p if p else (0, x1, y1)
        else:
            o = 1 if _road(w, x1 - 1, y1) or _road(w, x1 + 1, y1) else 0
            x, y = x1, y1
        tiles = segment(kind, o, x, y)
        return [(tx, ty, segment_ok(g, tiles), not d & SIDE) for tx, ty, d in tiles]
    out = []
    n = av.shape[0]
    for i, (tiles, ok) in enumerate(segs):
        if ok:
            along_y = len({t[1] for t in tiles}) == 1
            dx, dy = (0, 1) if along_y else (1, 0)
            near = (i > 0 and segs[i - 1][1]) or (i + 1 < len(segs) and segs[i + 1][1])
            if not near:                        # an existing avenue just before/after it counts too
                near = any(0 <= tx + s * dx < n and 0 <= ty + s * dy < n and av[ty + s * dy, tx + s * dx]
                           for tx, ty, _ in tiles for s in (-1, 1))
            ok = bool(near)
        out += [(tx, ty, ok, not d & SIDE) for tx, ty, d in tiles]
    return out


def origin(av, x, y):
    """Position 1 tile of the segment holding (x, y), and its step across (0x0041A6D0)."""
    d = int(av[y, x]) & 0xFF
    px, py = d & 7, (d >> 3) & 7
    if px:
        return x - (px - 1), y, (1, 0)
    return x, y - max(py - 1, 0), (0, 1)


def segment_at(av, x, y):
    kind = int(av[y, x]) >> 8
    ox, oy, (dx, dy) = origin(av, x, y)
    return [(ox + i * dx, oy + i * dy) for i in range(2 if kind == 1 else 3)]


def remove_segment(g, x, y):
    """0x0041A490: the segment's tiles become plain land again; a tile that has road keeps it."""
    av = grid(g.world)
    for tx, ty in segment_at(av, x, y):
        av[ty, tx] = 0


def anchor(w, x, y):
    """tile_step_to_anchor 0x00418B00: a side-strip tile -> the road tile of its segment."""
    if w.road[y, x]:
        return x, y
    d = int(w.avenue[y, x]) & 0xFF
    if d & 7:
        return (x + 1, y) if d & 7 == 1 else (x - 1, y)
    return (x, y + 1) if d & 0x38 == 8 else (x, y - 1)


def drop_isolated(g, kind):
    """0x004195D0: a segment with no avenue/boulevard tile before or after it along the run is removed.
    Returns how many."""
    av = grid(g.world)
    n = av.shape[0]
    removed = 0
    ys, xs = np.nonzero((av >> 8) == kind)
    for x, y in zip(xs.tolist(), ys.tolist()):
        if (int(av[y, x]) >> 8) != kind:
            continue
        if int(av[y, x]) & 0x38 == 0:
            a, b = (x, y - 1), (x, y + 1)
        else:
            a, b = (x - 1, y), (x + 1, y)
        if not any(0 <= p[0] < n and 0 <= p[1] < n and av[p[1], p[0]] for p in (a, b)):
            remove_segment(g, x, y)
            removed += 1
    return removed


def build(g, key, x1, y1, x2, y2):
    """`avenue X1 Y1 X2 Y2` / `boulevard ...`: one segment per road tile of the straight drag; cost per
    segment kept (build_commit 0x00498910: count x model cost)."""
    from ..game import CommandError
    from . import roads
    w = g.world
    av = grid(w)
    segs = plan(g, key, x1, y1, x2, y2)
    if not segs:
        raise CommandError(f"{key}: drag along a road (at least 2 tiles)")
    before = av.copy()
    kind = KIND[key]
    placed = 0
    for tiles, _ in segs:
        if segment_ok(g, tiles):
            for tx, ty, d in tiles:
                av[ty, tx] = kind << 8 | d
            placed += 1
    placed -= drop_isolated(g, kind)
    if placed <= 0:
        av[:] = before
        raise CommandError(f"{key}: nothing to build (needs 2+ road tiles in a row with free land beside them)")
    cost = placed * g.cat.spec(key)["cost"]
    try:
        g.spend(cost, "construction")
    except CommandError:
        av[:] = before
        raise
    g.map_version = getattr(g, "map_version", 0) + 1
    refresh(g)
    roads.rebuild(g)
    return f"{key} {placed} segments, cost {cost}"


# --- road bits and pictures ---------------------------------------------------------------------
def pattern(av, road, x, y, view=0):
    """Road-pattern index of (x, y): neighbours that are road or avenue/boulevard (0x00419190); column view/2."""
    n = av.shape[0]
    nb = [0 <= x + dx < n and 0 <= y + dy < n and bool(road[y + dy, x + dx] or av[y + dy, x + dx]) for dx, dy in NB]
    for j, (req, k) in enumerate(_PAT):
        if all(nb[i] == v for i, v in req):
            return VIEW_K[j][view >> 1]
    return 15


def recompute(av, road, rand=None, view=0):
    """0x00418BD0 + 0x004193A0 for boulevards, then avenues: side strips lose their road bit, then in
    row order each tile gets its pattern; a side strip whose pattern is not a side picture, or that lies
    between two roads (N+S or E+W), becomes road. `road` is changed in place. With `rand` (the map's
    random grid) also returns the pictures {(x, y): Zeus_General index} (presentation). `view` (0, 2, 4, 6;
    presentation only, with a copy of the road grid): the exe's run of the same rule after a turn
    (docs/play/rotation.md): pattern column view/2, run flags, mirrored pictures in views 2 and 6."""
    n = av.shape[0]
    R = lambda x, y: 0 <= x < n and 0 <= y < n and bool(road[y, x])
    imgs = {}
    for kind in (2, 1):
        ys, xs = np.nonzero((av >> 8) == kind)
        pts = list(zip(xs.tolist(), ys.tolist()))
        for x, y in pts:
            if av[y, x] & SIDE:
                road[y, x] = False
        for x, y in pts:
            idx = pattern(av, road, x, y, view)
            lc = -1
            if av[y, x] & SIDE:
                lc = SIDE_OF.get(idx, -1)
                if (R(x, y - 1) and R(x, y + 1)) or (R(x + 1, y) and R(x - 1, y)):
                    lc = -1
            if lc == -1:
                road[y, x] = True
                if rand is not None:
                    k = idx + (int(rand[y, x]) & 3 if idx == 15 else 0)
                    imgs[(x, y)] = ROAD_FIRST + (ROAD_MIRROR[k] if view in (2, 6) else k)
            elif rand is not None:
                if lc in (0, 9, 18, 27):
                    lc = _side_variant(av, road, rand, imgs, x, y, lc, view)
                imgs[(x, y)] = SIDE_FIRST + side_turn(lc, view)
    return imgs


def _side_base(av, road, x, y, view=0):
    n = av.shape[0]
    if not (0 <= x < n and 0 <= y < n) or not av[y, x] or road[y, x]:
        return -1
    return SIDE_OF.get(pattern(av, road, x, y, view), -1)


def _side_variant(av, road, rand, imgs, x, y, base, view=0):
    """0x00418CF0: picture 0..8 of a straight side strip from the tile before it along the run
    (already drawn) and after it: 5 starts a group, 4/6/7 continue it, 3 ends it; else 0/1/2/8. Where the
    run flag (RUN_FLIP, by view and side) is set, 3 starts and 5 ends."""
    if RUN_FLIP[(view >> 1) * 4 + base // 9]:
        return _side_variant_flip(av, road, rand, imgs, x, y, base, view)
    r = int(rand[y, x])
    if int(av[y, x]) & 0x38 == 0:
        prev, nxt = (x, y - 1), (x, y + 1)
    else:
        prev, nxt = (x - 1, y), (x + 1, y)
    pb, nb = _side_base(av, road, *prev, view), _side_base(av, road, *nxt, view)
    plain = base + (0, 1, 2, 8)[r & 3]
    if pb == base:
        lv = side_turn(imgs.get(prev, 0) - SIDE_FIRST, view) - base
        if lv in (4, 5, 6, 7):
            if nb == base:
                s = r & 7
                if s == 0: return base + 4
                if s in (1, 7): return base + 6
                if s == 2: return base + 7
            return base + 3
        if r % 9 not in (3, 4, 5, 6, 7):
            return plain
        return plain if nb != base else base + 5
    return plain if nb != base else base + 5


def _side_variant_flip(av, road, rand, imgs, x, y, base, view):
    """FUN_00418CF0 with its run flag set (byte 0x11 = 0x005E9664[view/2*4 + base/9] != 0)."""
    r = int(rand[y, x])
    if int(av[y, x]) & 0x38 == 0:
        prev, nxt = (x, y - 1), (x, y + 1)
    else:
        prev, nxt = (x - 1, y), (x + 1, y)
    pb, nb = _side_base(av, road, *prev, view), _side_base(av, road, *nxt, view)
    plain = base + (0, 1, 2, 8)[r & 3]
    if pb == base:
        lv = side_turn(imgs.get(prev, 0) - SIDE_FIRST, view) - base
        if lv in (3, 4, 6, 7):
            if nb == base:
                s = r & 7
                if s == 0: return base + 4
                if s in (1, 7): return base + 6
                if s == 2: return base + 7
            return base + 5
        if r % 9 not in (3, 4, 5, 6, 7):
            return plain
        return plain if nb != base else base + 3
    return plain if nb != base else base + 3


def refresh(g):
    """Recompute which side-strip tiles are road (after any road or avenue change)."""
    w = g.world
    av = grid(w)
    if av.any():
        recompute(av, w.road)


def tiles(g):
    """[(x, y, key, is_road_tile)] of every avenue/boulevard tile (row order)."""
    av = grid(g.world)
    ys, xs = np.nonzero(av)
    return [(x, y, KEY[int(av[y, x]) >> 8], not av[y, x] & SIDE) for x, y in zip(xs.tolist(), ys.tolist())]


def desirability(g, acc, spec_of):
    """Step 37b (0x00493C80): every avenue/boulevard tile is a size-1 source with its type's values."""
    av = grid(g.world)
    if not av.any():
        return
    n = av.shape[0]
    for kind, key in KEY.items():
        m = ((av >> 8) == kind).astype(np.int32)
        if not m.any():
            continue
        d = spec_of(key)["desirability"]
        val, step, size_, rng = d["value"], d["step"], d["step_size"], min(d["range"], 6)
        if not val or rng <= 0:
            continue
        vals = [val + (size_ * ((r - 1) // step) if step > 0 else size_ * (r - 1)) for r in range(1, rng + 1)]
        ii = np.zeros((n + 1, n + 1), np.int32)          # integral image of the sources
        ii[1:, 1:] = m.cumsum(0).cumsum(1)
        for r in range(1, rng + 1):
            delta = vals[r - 1] - (vals[r] if r < rng else 0)
            if not delta:
                continue
            y0 = np.clip(np.arange(n) - r, 0, n); y1 = np.clip(np.arange(n) + r + 1, 0, n)
            box = ii[y1][:, y1] - ii[y0][:, y1] - ii[y1][:, y0] + ii[y0][:, y0]
            acc += delta * box
        acc -= vals[0] * m
