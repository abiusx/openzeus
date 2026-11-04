"""Desirability grid as the exe (docs/logic/desirability.md): cycle step 37a desirability_from_buildings 0x00493830,
37b desirability_from_terrain 0x00493C80, step 38 buildings_update_desirability 0x004842A0 (house_desirability).

Every add is clamped to [-100, 100] on the spot (desirability_add_ring 0x004A4C60, add_rect_border 0x00493700), so
the order of the sources matters once a tile saturates: buildings in id order, then the terrain pass row by row.
Square sources (desirability_spread 0x004A4BF0): ring r = the tiles at distance r from the size x size footprint,
the value changes after every `step` rings (counter from 0). Rectangle sources (desirability_spread_rect 0x004937B0:
agoras, sanctuaries and the palace, the stadium, the dock, the horse ranch) count from 1, so with step 2 the value
changes after ring 1. Range at most 6 (both)."""
import numpy as np

N = 228
# 0x004937B0 dock rectangle from the pier's anchor by orientation (Building+0xAC): (dx, dy), (ex, ey)
DOCK_RECT = (((-1, 5), (3, 0)), ((-4, -1), (5, 3)), ((-1, -4), (3, 5)), ((5, -1), (0, 2)))
# horse ranch 0x85 by orientation: (x + a, y + b) .. (x + c, y + d) (house and corral; o > 2: the last row)
RANCH_RECT = ((0, -1, 6, 2), (-1, -4, 2, 2), (-4, 0, 2, 3), (0, 0, 3, 6))
RUBBLE_SRC = (-2, 1, 1, 2)          # 0x00493C80 immediates: -2 ring 1, -1 ring 2
GARDENS = "gardens"                 # type 128: painted garden tiles (terrain 0x20) in the exe, a source in step 37b


def _border(acc, x0, y0, x1, y1, v):
    """Add v (clamped) to every tile of the border of [x0, x1] x [y0, y1] (inclusive), inside the grid."""
    if x1 < 0 or y1 < 0 or x0 >= N or y0 >= N:
        return
    cx0, cx1, cy0, cy1 = max(x0, 0), min(x1, N - 1), max(y0, 0), min(y1, N - 1)
    parts = []
    if y0 >= 0:
        parts.append(acc[y0, cx0:cx1 + 1])
    if y1 < N and y1 != y0:
        parts.append(acc[y1, cx0:cx1 + 1])
    ry0, ry1 = max(y0 + 1, 0), min(y1 - 1, N - 1)
    if ry1 >= ry0:
        if x0 >= 0:
            parts.append(acc[ry0:ry1 + 1, x0])
        if x1 < N and x1 != x0:
            parts.append(acc[ry0:ry1 + 1, x1])
    for p in parts:
        p += v
        np.clip(p, -100, 100, out=p)


def spread(acc, x, y, s, v, step, step_size, rng):
    """desirability_spread 0x004A4BF0: rings 1..min(range, 6) around the s x s footprint at (x, y)."""
    if s <= 0:
        return
    c = 0
    for r in range(1, min(rng, 6) + 1):
        if v:
            _border(acc, x - r, y - r, x + s - 1 + r, y + s - 1 + r, v)
        c += 1
        if c >= step:
            v += step_size
            c = 0


def spread_rect(acc, x1, y1, x2, y2, v, step, step_size, rng):
    """desirability_spread_rect 0x004937B0: the rings around [x1, x2] x [y1, y2]; the counter starts at 1."""
    c = 1
    for k in range(min(rng, 6)):
        if v:
            _border(acc, x1 - k - 1, y1 - k - 1, x2 + k + 1, y2 + k + 1, v)
        c += 1
        if c >= step:
            v += step_size
            c = 0


def update(g):
    w = g.world
    from .services import occ_version
    sig = occ_version(g)          # buildings, stall keys and rubble all change only with it
    if getattr(g, "_des_sig", None) == sig:        # nothing that moves desirability changed
        return
    g._des_sig = sig
    acc = np.zeros((N, N), np.int16)
    spec = g.cat.spec
    gardens = []
    # step 37a, buildings in id order (records with a parent part are skipped: our stalls; bays, the dock house's
    # pier part and the ranch's corral are not buildings in ours)
    for b in sorted(g.buildings.values(), key=lambda b: b.id):
        if b.kind in ("stall", "avenue"):
            continue
        if b.key == GARDENS:
            gardens.append(b)
            continue
        d = spec(b.key)["desirability"]
        val, step, ss, rng = d["value"], d["step"], d["step_size"], d["range"]
        if rng <= 0 or not (val or ss):
            continue
        bw, bh = b.misc.get("w", b.size), b.misc.get("h", b.size)
        if b.kind == "monument":
            # composites 84..98, 117, pyramids 100..114: only when finished (+0xDA == 0) or the palace (117);
            # the rectangle = composite_bounds 0x0053CF30 over the pieces and extras (ours: the layout's box)
            if b.key != "palace" and not b.misc.get("complete"):
                continue
            spread_rect(acc, b.x, b.y, b.x + bw - 1, b.y + bh - 1, val, step, ss, rng)
        elif b.kind == "agora" or b.key == "stadium":        # 0x0040C9B0 / 0x005B02E0 rectangles
            spread_rect(acc, b.x, b.y, b.x + bw - 1, b.y + bh - 1, val, step, ss, rng)
        elif b.key == "dock" and "orient" in b.misc and "pier" in b.misc:
            px, py = b.misc["pier"]
            (dx, dy), (ex, ey) = DOCK_RECT[b.misc["orient"] & 3]
            spread_rect(acc, min(px, px + dx), min(py, py + dy), max(px, px + dx + ex), max(py, py + dy + ey),
                        val, step, ss, rng)
        elif b.key == "horse_ranch" and "orient" in b.misc:
            a, c0, c, e = RANCH_RECT[min(b.misc["orient"], 3)]
            spread_rect(acc, b.x + a, b.y + c0, b.x + c, b.y + e, val, step, ss, rng)
        else:
            spread(acc, b.x, b.y, b.size, val, step, ss, rng)
    # step 37b, the play area row by row: avenue / boulevard tiles, garden tiles, rubble (an elif chain)
    from . import avenues
    av = avenues.grid(w) >> 8
    src = np.zeros((N, N), np.int8)                      # 1 avenue, 2 boulevard, 3 gardens, 4 rubble
    src[(w.flags & 0x1000) != 0] = 4
    for b in gardens:
        src[b.y:b.y + b.size, b.x:b.x + b.size] = 3
    src[av == 1] = 1
    src[av == 2] = 2
    keys = {1: avenues.KEY[1], 2: avenues.KEY[2], 3: GARDENS}
    vals = {k: tuple(spec(key)["desirability"][f] for f in ("value", "step", "step_size", "range"))
            for k, key in keys.items()}
    vals[4] = RUBBLE_SRC
    ys, xs = np.nonzero(src)                             # row-major, as the exe's scan
    for y, x in zip(ys.tolist(), xs.tolist()):
        spread(acc, x, y, 1, *vals[int(src[y, x])])
    w.des = acc
    g._desl = w.des.ravel().tolist()               # flat copy for per-house reads (housing.update)


# step 38 (0x004842A0): a building's desirability is the best tile of its footprint, + 10 when it was created next to
# water (building_adjacent_to_water 0x004A4500: any edge-neighbour of the footprint, no corners, table 0x005F1680, has
# terrain 0x4; set once by building_create, ours from the current footprint)
def next_to_water(g, b):
    f, s, x, y = g.world.flags, b.size, b.x, b.y
    for i in range(s):
        for tx, ty in ((x + i, y - 1), (x + s, y + i), (x + i, y + s), (x - 1, y + i)):
            if 0 <= tx < N and 0 <= ty < N and f[ty, tx] & 0x4:
                return True
    return False
