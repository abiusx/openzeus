"""Monuments: sanctuaries and Poseidon pyramids built piece by piece (docs/logic/monuments.md).

A monument is one building over its whole layout box (data/monuments.json from tools/monuments.py); its pieces
(the original's one Building record per piece) are dicts in b.misc["pieces"], in layout order. This is the general
mechanism for any multi-piece big building.

Per piece (exe field in brackets): stage s [+0x58] of n, materials held for the current stage [+0x70 wood, +0x74
marble, +0x78 sculpture, +0xAC black marble, +0xC0 orichalc], up to 8 carts on their way [+0x7C..+0x98], sibling
reservations [+0xA4 / +0xB0 / +0xC4], the artisan working it [+0x5C].

- Artisans' Guild (artisans_guild_spawn 0x0048CB30, daily): one artisan out at a time (two with Atlas active); it is given a job at once
  (monuments_find_artisan_job 0x0053EC10 / monument_pick_part 0x0053E740: tiles, then the temple, then statues and
  sculptures, then the rest); with no job the exe makes it vanish in the guild (action 4, ~128 ticks), so the guild
  sends nobody for 128 ticks.
- The artisan walks (route mode 13: roads, the monument's ground tiles and pieces not started; else open land) to
  the piece's work tile (vt+0x54 0x00541E50: the nearest road or sanctuary-ground tile to the piece's min tile).
  There it waits for the stage's materials, asking for carts every 31 ticks (also while walking), then works 51
  ticks (a statue's second stage 100: statue_conan.txt), the stage advances (set_stage: held materials and
  reservations cleared), and it takes the next job where it stands; with none left it vanishes (action 9).
- Carts (monument_part_request_materials 0x005442F0 / monument_dispatch_cart 0x00543DE0): at most one cart per
  request, and one monument cart per day in the whole city; order wood, marble, black marble, sculpture, orichalc.
  A cart (an ox team: figure 4 + two 0x1C) drives from the storage to the monument's road entry
  (composite_road_entry 0x0053F810) and is unloaded there into the piece. Marble / black marble / orichalc for
  small needs (< 400: tiles, pyramid levels) are shared: a 400 cart serves 8 tiles of 50 (monument_share_load
  0x00542900, modes 0 give / 1 reserve / 2 count).
- Completion (cycle_buildings_pass_32 0x00495860, daily): progress > 99 -> complete, message, date, the sanctuary's
  activity counter (+0x32 = 22) and staff (under construction +0xDA employs nobody).

Ours / simplified: pyramid-specific order (pyramid_piece_ready, lifts, lockstep levels), the black-marble variants
of pyramid pieces (plain marble), god-supplied materials and god arrival (gods are out of scope), terrain extras
1001..1005 granted on completion (class code not read), the road entry's network ranking (nearest to the root).
"""
import json
import os
from collections import deque

import numpy as np

from . import walkers, roads

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data",
                    "monuments.json")
TILES = set(range(55, 61)) | {109} | set(range(111, 117)) | set(range(152, 158)) | set(range(160, 164))
STATUES = set(range(61, 109)) | set(range(125, 133)) | set(range(145, 149))
SCULPTURES = set(range(7, 55)) | set(range(133, 145))
TEMPLES = {0, 110, 158}
BACKS = {1, 159}
STEPS = set(range(117, 122))
GOODS = ("wood", "marble", "black_marble", "sculpture", "orichalc")     # request order (0x005442F0)
SHARED = ("marble", "black_marble", "orichalc")                        # shared between sibling pieces
WORK_TICKS = 51                 # vt+0x5C = 50: the counter goes 1..51
REQUEST_TICKS = 31              # f+0x36 > 30
GUILD_IDLE = 128                # figure_dying_tick: an artisan with no job vanishes in its guild after ~128 ticks
CART_SLOTS = 8
HERMES = "sanctuary_hermes"     # type 0x5B: its pieces are worked from the road entry (vt+0x54)


def layouts():
    global _LAYOUTS
    try:
        return _LAYOUTS
    except NameError:
        _LAYOUTS = json.load(open(DATA))
        return _LAYOUTS


def size(c):
    """Piece size (class method vt+0x00; docs/play/monuments.md table)."""
    if c in (0, 1, 3, 4, 110, 158, 159):
        return 4
    if c == 2 or c in STATUES:
        return 2
    return {149: 5, 150: 6, 151: 6}.get(c, 1)


def stages(c, elev):
    """[(materials {good: units}, weight, work ticks)] for each stage 0..n-2 of piece class c
    (monuments.md 'Stages and materials per piece'); the piece is complete at stage n-1."""
    if c in BACKS:                                # no work of its own: follows the temple front
        return [({}, 4, 51)] * 3
    if c in TEMPLES:
        if c == 0:
            return [(dict(marble=800, wood=800), 4, 51), (dict(marble=800, wood=800), 4, 51), (dict(marble=1600), 4, 51)]
        if c == 110:
            return [(dict(marble=400, wood=400), 4, 51), (dict(marble=400, wood=400), 4, 51), (dict(marble=800), 4, 51)]
        return [(dict(marble=800, wood=400), 4, 51)] * 3
    if c == 2:
        return [(dict(marble=400), 2, 51)]
    if c in SCULPTURES:
        return [(dict(sculpture=400), 1, 51)]
    if c in STATUES and c < 145:
        return [(dict(marble=800), 2, 51), (dict(wood=400), 2, 100)]
    if c in range(145, 149):
        return [(dict(marble=800, wood=400), 2, 51), (dict(marble=800, wood=400), 2, 100)]
    if c == 149:
        return [(dict(marble=1200, wood=800, orichalc=800), 1, 51)]
    if c == 150:
        return [(dict(marble=3200, wood=1600, orichalc=2400), 1, 51)]
    if c == 151:
        return [(dict(marble=1600, wood=400), 1, 51), (dict(marble=2000, wood=1200), 1, 51),
                (dict(marble=800, orichalc=800), 1, 51)]
    if c in STEPS or c in (122, 124) or c in range(160, 164):
        E = (elev // 2) * 4
        out = [(dict(marble=50), 1, 51)] * E
        if c in STEPS:
            out.append((dict(marble=200, orichalc=50), 1, 51))
        elif c == 122:
            out.append((dict(marble=400, orichalc=400), 1, 51))
        elif c == 124:
            out += [(dict(marble=50, orichalc=200), 1, 51), (dict(wood=800), 1, 51)]
        else:
            out.append((dict(marble=50), 1, 51))
        return out
    if c in TILES:
        return [(dict(marble=50), 1, 51)]
    return []                                     # 1, 159 (backs follow the front), 123, 1000+: nothing


def idx(b, p):
    """Index of piece dict p in b's pieces (by identity: two pieces may be equal dicts)."""
    return next(i for i, q in enumerate(b.misc["pieces"]) if q is p)


def new_piece(c, e, i):
    return dict(c=c, e=e, i=i, s=0, n=len(stages(c, e)), artisan=0, held={}, carts=[], resv={})


def create(g, b, orient=0):
    """Piece records for a new monument building b. orient 0..3 (b+0x9C): the layout turned by 90 degrees per step,
    the box w x h swapped for 1 and 3; the pieces keep their layout order and box-relative layout offsets (piece_xy
    turns them; the play client does the same, docs/play/monuments.md 'Orientation')."""
    lay = layouts()[b.key]
    pieces = [new_piece(c, e, i) for i, (dx, dy, c, e) in enumerate(lay["pieces"]) if stages(c, e) or c in BACKS]
    w, h = (lay["h"], lay["w"]) if orient % 2 else (lay["w"], lay["h"])
    b.misc.update(w=w, h=h, pieces=pieces, built=0, orient=orient)


def mark_ground(g, b, on=True):
    """FUN_0053C390 (placement): terrain 0x10000000 on every tile of every layout piece, i.e. the whole layout box
    (Athena 192 tiles); building_on_remove -> FUN_00546A60 clears it. It marks sanctuary ground for the walkers' ramp
    lift (walker_draw / FUN_004D7580 mask 0x10000400), the draw order and terrain_regrow (skips it)."""
    w = g.world
    x0, y0, bw, bh = b.x, b.y, b.misc["w"], b.misc["h"]
    box = w.flags[max(0, y0):max(0, y0 + bh), max(0, x0):max(0, x0 + bw)]
    if on:
        box |= np.uint32(0x10000000)
    else:
        box &= np.uint32(~0x10000000 & 0xFFFFFFFF)
    b.misc["ground"] = on
    g.map_version = getattr(g, "map_version", 0) + 1


def adopt(g):
    """Saves from before per-piece materials (2026-10-28): pieces get their layout index and empty holdings; the
    monument's pooled materials go to its unfinished pieces' current stages in layout order (the rest is dropped);
    artisans and carts already out keep going (their piece is found again)."""
    for b in list(g.buildings.values()):
        if b.kind != "monument" or "pieces" not in b.misc:
            continue
        lay = layouts().get(b.key)
        if lay is None:
            continue
        if b.misc["pieces"] and "i" not in b.misc["pieces"][0]:
            idx = [i for i, (dx, dy, c, e) in enumerate(lay["pieces"]) if stages(c, e) or c in BACKS]
            for p, i in zip(b.misc["pieces"], idx):
                p.update(i=i, held={}, carts=[], resv={})
                p.pop("work", None)
        pool = b.misc.pop("pool", None)
        if pool:
            for p in b.misc["pieces"]:
                if p["s"] >= p["n"] or p["c"] in BACKS:
                    continue
                for k, v in stages(p["c"], p["e"])[p["s"]][0].items():
                    give = min(v, pool.get(k, 0))
                    if give > 0:
                        p["held"][k] = give
                        pool[k] -= give
        b.misc.setdefault("orient", 0)
        if "ground" not in b.misc and b.key in layouts() and b.key.startswith("sanctuary_"):
            mark_ground(g, b)                     # saves from before 10-30: the flag came with the extras only
        if b.misc.get("built", 0) >= 100:
            b.misc.setdefault("complete", True)
        if b.misc.get("complete") and b.key.startswith("sanctuary_") and "extra_trees" not in b.misc:
            extras_complete(g, b)                 # saves from before the extras (10-29): as on completion


# --- geometry ------------------------------------------------------------------------------------------------

def piece_xy(b, p_or_i):
    """Min tile of a layout piece (index into the layout or a piece dict), with the placement orientation
    (composite_offset_rotate: o1 (dy, W-dx-n), o2 (W-dx-n, H-dy-n), o3 (H-dy-n, dx))."""
    lay = layouts()[b.key]
    i = p_or_i["i"] if isinstance(p_or_i, dict) else p_or_i
    dx, dy, c, _ = lay["pieces"][i]
    n, W, H, o = size(c), lay["w"], lay["h"], b.misc.get("orient", 0) & 3
    if o == 1:
        dx, dy = dy, W - dx - n
    elif o == 2:
        dx, dy = W - dx - n, H - dy - n
    elif o == 3:
        dx, dy = H - dy - n, dx
    return b.x + dx, b.y + dy


def piece_tiles(b, p):
    x, y = piece_xy(b, p)
    n = size(p["c"])
    return [(x + k, y + j) for j in range(n) for k in range(n)]


_PIECE_AT = {}


def piece_at(b, x, y):
    """The layout piece index covering tile (x, y) of composite b (extras: their index too), else None. Cached per
    placement (key, origin, orientation)."""
    k = (b.key, b.x, b.y, b.misc.get("orient", 0) & 3)
    m = _PIECE_AT.get(k)
    if m is None:
        if len(_PIECE_AT) > 256:
            _PIECE_AT.clear()
        m = {}
        lay = layouts().get(b.key)
        for i, p in enumerate(lay["pieces"] if lay else ()):
            px, py = piece_xy(b, i)
            n = size(p[2])
            for j in range(n):
                for q in range(n):
                    m.setdefault((px + q, py + j), i)
        _PIECE_AT[k] = m
    return m.get((x, y))


def footprint_width(b, x, y):
    """The width of the footprint that covers tile (x, y) of composite b in the exe's piece grid (low nibble + 1):
    refresh_piece_image 0x0053D300 places a piece's picture as one n-tile footprint (building_footprint_place: nibble
    n - 1) unless the class's vt+0x4C flags bit 1 asks for one picture per tile (the rough base of stage 0, pyramid
    blocks: nibble cleared). The palace's pieces are complete on placement (ours keeps no piece records for them)."""
    i = piece_at(b, x, y)
    if i is None:
        return 1
    c = layouts()[b.key]["pieces"][i][2]
    if c >= 1000:
        return 1
    if b.key != "palace":
        p = next((q for q in b.misc.get("pieces", ()) if q.get("i") == i), None)
        if p is None or p["s"] == 0:
            return 1
    return size(c)


def ground(b):
    """The monument's ground tiles: extras (classes >= 1000) get terrain 0x10000000 at placement (FUN_0053C390),
    the artisans' standing ground and route bit 0x20."""
    lay = layouts()[b.key]
    return [piece_xy(b, i) for i, p in enumerate(lay["pieces"]) if p[2] >= 1000]


def open_tiles(b):
    """Tiles an artisan may cross (route bit 0x20): the ground, tile-class pieces, and pieces at stage 0
    (vt+0x9C 0x0053E5D0: phase index 0)."""
    out = set(ground(b))
    for p in b.misc["pieces"]:
        if p["c"] in TILES or p["s"] == 0:
            out.update(piece_tiles(b, p))
    return out


def road_entry(g, b):
    """composite_road_entry 0x0053F810: a road tile (terrain & 0x44 == 0x40: not a bridge) on the ring just outside
    the layout box (pieces and extras: the rows above and below, then the columns left and right, corners excluded),
    ranked first by its road network's place among the 10 largest (g_road_networks_top10, road_networks_update
    0x00491FE0: by size, the earlier scanned first on a tie; 11 for any other network), then by the squared distance
    to the layout's origin (the file's (0, 0): root - rot(part 0's offset), composite_offset_rotate_b 0x005466A0);
    strictly better only, so the first found wins a tie. Roadblocks count (the exe tests the terrain only)."""
    bw, bh = b.misc["w"], b.misc["h"]
    ring = ([(b.x + i, b.y - 1) for i in range(bw)] + [(b.x + i, b.y + bh) for i in range(bw)] +
            [(b.x - 1, b.y + j) for j in range(bh)] + [(b.x + bw, b.y + j) for j in range(bh)])
    w = g.world
    road, n = walkers.road_list(g), w.road.shape[1]
    ox, oy = origin(b)
    rank = network_ranks(g)
    best = None
    for x, y in ring:
        if 0 <= x < n and 0 <= y < n and road[y * n + x] and not w.flags[y, x] & 0x4:
            key = (rank.get(int(w.road_net[y, x]), 11), (x - ox) ** 2 + (y - oy) ** 2)
            if best is None or key < best[0]:
                best = (key, (x, y))
    return best[1] if best else b.access


def origin(b):
    """The layout file's (0, 0) on the map (data/monuments.json `origin`, box coordinates), turned with the
    placement orientation like a 1x1 piece (piece_xy). Orientations 1..3 are our reading (not checked in the exe)."""
    lay = layouts()[b.key]
    dx, dy = lay.get("origin", (0, 0))
    W, H, o = lay["w"], lay["h"], b.misc.get("orient", 0) & 3
    if o == 1:
        dx, dy = dy, W - dx - 1
    elif o == 2:
        dx, dy = W - dx - 1, H - dy - 1
    elif o == 3:
        dx, dy = H - dy - 1, dx
    return b.x + dx, b.y + dy


def network_ranks(g):
    """{road network id: 0..9} for the 10 largest networks (road_networks_update 0x00491FE0: a network goes in front
    of the first strictly smaller one, so ties keep the scan order = our ids), cached per map version."""
    v = getattr(g, "map_version", 0)
    c = getattr(g, "_net_rank", None)
    if c is None or c[0] != v:
        import numpy as np
        ids, counts = np.unique(g.world.road_net[g.world.road_net > 0], return_counts=True)
        top = sorted(zip((-counts).tolist(), ids.tolist()))[:10]
        c = g._net_rank = (v, {nid: i for i, (_, nid) in enumerate(top)})
    return c[1]


def _ground_set(g):
    """Sanctuary ground of every monument (terrain 0x10000000 is a map flag in the exe)."""
    out = set()
    from . import index
    for m in index.of(g, "monument"):
        if "pieces" in m.misc and m.key in layouts():
            out.update(ground(m))
    return out


def work_tile(g, b, p):
    """vt+0x54 0x00541E50 / find_work_tile 0x00541960: from the piece's min tile, the nearest tile that is road or
    sanctuary ground: rings r = 1.. scanned, the smallest dx^2 + dy^2 kept, taken once it is <= r^2."""
    if b.key == HERMES:
        return road_entry(g, b)
    x0, y0 = piece_xy(b, p)
    road, n = walkers.road_list(g), g.world.road.shape[1]
    gs = _ground_set(g)
    ok = lambda x, y: 0 <= x < n and 0 <= y < n and (road[y * n + x] or (x, y) in gs)
    if ok(x0, y0):
        return x0, y0
    best, at = 0xCB10, None
    for r in range(1, 228):
        ring = [(x0 + k, y0 - r) for k in range(-r, r + 1)] + [(x0 + k, y0 + r) for k in range(-r, r + 1)] + \
               [(x0 - r, y0 + k) for k in range(-r + 1, r)] + [(x0 + r, y0 + k) for k in range(-r + 1, r)]
        for x, y in ring:
            if ok(x, y):
                d = (x - x0) ** 2 + (y - y0) ** 2
                if d < best:
                    best, at = d, (x, y)
        if at is not None and best <= r * r:
            return at
    return at


def route(g, start, goal):
    """Route mode 13 (0x0058A0D0 over bits 0x12C: road, ramps, monument ground and unstarted pieces), else
    0x00589ED0 over 0x13C (open land too)."""
    if start == goal:
        return []
    n = g.world.road.shape[1]
    ok = list(walkers.road_list(g))
    from . import index
    mons = [m for m in index.of(g, "monument") if "pieces" in m.misc and m.key in layouts()]
    extra = set()
    for m in mons:
        extra |= open_tiles(m)
    for x, y in extra:
        ok[y * n + x] = True
    p = walkers.land_path(g, start, {goal}, max_dist=walkers.ROUTE_MAX, ok=ok)
    if p is None:
        land = walkers.walkable(g)
        ok = [a or b for a, b in zip(ok, land)]
        p = walkers.land_path(g, start, {goal}, max_dist=walkers.ROUTE_MAX, ok=ok)
    return p


# --- stages, materials ----------------------------------------------------------------------------------------

def need(p, good):
    """Units of good the piece's current stage needs (ceil of the class method's double)."""
    if p["s"] >= p["n"]:
        return 0
    return stages(p["c"], p["e"])[p["s"]][0].get(good, 0)


def progress(b):
    """monument_progress 0x0053ECA0: weighted stages done, truncated percent."""
    total = done = 0
    for p in b.misc["pieces"]:
        for i, (_, wgt, _) in enumerate(stages(p["c"], p["e"])):
            total += wgt
            if i < p["s"]:
                done += wgt
    return 100 if total == 0 else done * 100 // total


def complete(b):
    return b.misc.get("built", 0) >= 100


def piece_done(p):
    return p["s"] >= p["n"]


def live_carts(g, b, p):
    """The piece's cart slots, dropping carts gone or no longer wanted (cart_valid vt+0xD0 0x005438A0: a cart is
    kept while its resource's remaining need, after the carts before it, is > 0, or for a small marble need)."""
    rem = {k: need(p, k) - p["held"].get(k, 0) for k in GOODS}
    keep = []
    for wid in p["carts"]:
        w = g.walkers.get(wid)
        if w is None or w.role != "cart" or w.good not in rem:
            continue
        if rem[w.good] > 0 or (w.good in SHARED and 0 < need(p, w.good) < 100):
            rem[w.good] -= w.amount
            keep.append(wid)
    p["carts"] = keep
    return keep


def remaining(g, b, p):
    """remaining(r) = ceil(need) - held - loads on the way."""
    rem = {k: need(p, k) - p["held"].get(k, 0) for k in GOODS}
    for wid in live_carts(g, b, p):
        w = g.walkers[wid]
        rem[w.good] -= w.amount
    return rem


def ready(g, b, p):
    """vt+0xDC unload: every remaining need <= 0 and no cart slot in use: the artisan may work."""
    if any(need(p, k) - p["held"].get(k, 0) > 0 for k in GOODS):
        return False
    return not live_carts(g, b, p)


def _eligible(b, p, q, good, nd, mode):
    """0x00542670: a sibling q at the same stage needing exactly as much, holding none, no carts coming."""
    if q is p or q["s"] != p["s"] or need(q, good) != nd or q["held"].get(good, 0) or q["carts"]:
        return False
    if mode == 1:
        r = q["resv"].get(good)
        if r is not None:
            pieces = b.misc["pieces"]
            o = pieces[r] if 0 <= r < len(pieces) else None
            if o is not None and o["s"] == q["s"] and o["carts"]:   # the reserving piece is still waiting on a cart
                return False
            q["resv"].pop(good, None)                                # stale reservation cleared
    return True


def _dist(b, p, q):
    (x0, y0), (x1, y1) = piece_xy(b, p), piece_xy(b, q)
    return (x0 - x1) ** 2 + (y0 - y1) ** 2


def share_load(b, p, good, mode):
    """monument_share_load 0x00542900. mode 2: the units the eligible siblings would take (<= 400); mode 1: reserve
    the nearest eligible sibling for p's cart; mode 0: give the nearest eligible sibling its stage's need."""
    if good not in SHARED:
        return 0
    nd = need(p, good)
    pieces = b.misc["pieces"]
    me = idx(b, p)
    out, best, chosen = 0, 9999, None
    for q in pieces:
        if q is p or q["s"] != p["s"]:
            continue
        if mode == 2 and q["resv"].get(good) not in (None, me):
            continue
        if _eligible(b, p, q, good, nd, mode):
            out += nd
            d = _dist(b, p, q)
            if d < best:
                best, chosen = d, q
    if mode == 2:
        return min(out, 400)
    if chosen is not None:
        if mode == 1:
            chosen["resv"][good] = me
        else:
            chosen["held"][good] = nd
    return chosen


def covered_by_sibling(g, b, p, good):
    """vt+0xE4 0x005456F0: a small need (<= 50) already on a sibling's cart that reserved this piece."""
    nd = need(p, good)
    if nd <= 0 or 100 // nd <= 1:
        return False
    r = p["resv"].get(good)
    pieces = b.misc["pieces"]
    if r is None or not 0 <= r < len(pieces):
        return False
    s = pieces[r]
    if s["s"] != p["s"] or need(s, good) != nd:
        return False
    return any(g.walkers[wid].good == good for wid in live_carts(g, b, s))


def request(g, b, p):
    """monument_part_request_materials 0x005442F0: at most one new cart, in the order wood, marble, black marble,
    sculpture, orichalc."""
    if piece_done(p) or p["c"] in BACKS:
        return
    rem = remaining(g, b, p)
    if all(v <= 0 for v in rem.values()):
        return
    for k in SHARED:
        if rem[k] != 0 and covered_by_sibling(g, b, p, k):
            return
    if len(p["carts"]) >= CART_SLOTS:
        return
    for k in GOODS:
        r = rem[k]
        if r <= 0:
            continue
        if k == "wood":
            amt = max(100, min(400, r))
        elif k == "sculpture":
            amt = min(r, 400)
        else:
            amt = 400 if share_load(b, p, k, 2) + r >= 400 else 100
        w = dispatch(g, b, p, k, amt)
        if w is None:
            continue
        if k in SHARED:
            for _ in range(w.amount // need(p, k) - 1):
                share_load(b, p, k, 1)
        return


def dispatch(g, b, p, good, amount):
    """monument_dispatch_cart 0x00543DE0: one monument cart per day city-wide (day_of_month vs the city byte
    0x00FE6A58); from the nearest storage with the good, to the monument's road entry."""
    day = g.sd("monument_cart_day", [-1])
    if day[0] == g.day or halted(b):             # halted (root+0x64 bit 0x100): no carts
        return None
    entry = road_entry(g, b)
    if entry is None:
        b.reason = "needs a road"
        short(b, good, True)
        return None
    # the source: storage_find_source(monument, good, 0, need_min 1, min(amount, 400)) 0x0048A140 = the nearest
    # storehouse / importing post (a storehouse on Get too) holding at least the load, on the entry's road network,
    # whatever its staff; no storage walker slot is used (the cart's +0x5A is the storage, no slot holds it)
    from . import storemen
    src = storemen.find_source(g, b, good, need_min=True, minimum=min(amount, 400), start=entry)
    if src is None:
        b.reason = f"needs {good.replace('_', ' ')} (none in storage)"      # root+0x64 shortage bits (0x00543C30)
        short(b, good, True)
        return None
    path = roads.path(g, src.access, {entry})
    if path is None:
        short(b, good, True)                      # the cart's route failed (action 10)
        return None
    load = min(amount, src.goods[good])            # storehouse_remove_goods(src, good, amount): the shortfall stays
    src.goods[good] -= load
    w = walkers.spawn(g, src, "cart", good=good, amount=load, target=b.id, piece=idx(b, p))
    w.path = path
    p["carts"].append(w.id)
    day[0] = g.day
    b.reason = ""
    if not path:
        walkers.arrive(g, w)
    return w


def deliver(g, m, w):
    """The cart at the road entry (action 0x17, hidden): unload into its piece (vt+0xDC 0x00544FC0). Small marble /
    black marble / orichalc needs share the load: the piece keeps its need and gives the next k - 1 nearest
    eligible siblings theirs (k = load / need). A cart no longer wanted is lost (cart_valid removes it)."""
    pieces = m.misc.get("pieces") or []
    p = pieces[w.piece] if 0 <= w.piece < len(pieces) else None
    if p is None:                                 # old saves: the first unfinished piece that needs the good
        p = next((q for q in pieces if need(q, w.good) - q["held"].get(w.good, 0) > 0), None)
    if p is not None and w.id in p["carts"]:
        p["carts"].remove(w.id)
    good, load = w.good, w.amount
    w.amount = 0
    walkers.remove(g, w)
    short(m, good, False)                         # the cart arrived: the shortage bit is cleared (0x004AE160)
    if p is None or piece_done(p):
        return
    nd = need(p, good)
    if nd - p["held"].get(good, 0) <= 0 and not (good in SHARED and 0 < nd < 100):
        return
    if good in SHARED and 0 < nd < 400:
        k = load // nd
        if not p["held"].get(good, 0):
            p["held"][good] = nd
        else:
            k += 1
        for _ in range(k - 1):
            q = share_load(m, p, good, 0)
            if q is not None:
                wake(g, m, q)
    else:
        p["held"][good] = p["held"].get(good, 0) + load
    wake(g, m, p)


def wake(g, m, p):
    """A waiting artisan sees its materials at its next tick (the exe's unload runs every tick)."""
    w = g.walkers.get(p["artisan"])
    if w is not None and w.role == "artisan" and w.task == "wait":
        walkers.schedule(g, w, 1)


def set_stage(m, p, s):
    """set_stage 0x005435B0: the stage, materials held and reservations cleared; progress clears the "damaged" flag
    (+0x69) a monster's attack set (sim/heroes monsters.piece_damage)."""
    if s > p["s"] and p.get("damaged"):
        p.pop("damaged")
    p["s"] = s
    p["held"], p["resv"] = {}, {}


def halted(b):
    """Construction halted (root+0x64 bit 0x100, toggled by the window's button 0x00408E40): no new jobs
    (monument_pick_part 0x0053E740), no carts (0x00543DE0); artisans at work finish their stage."""
    return bool(b.misc.get("halted"))


def short(b, good, on):
    """Shortage bits (root+0x64, FUN_00543C30): set when a cart for the good can't be sent (no storage with it, no
    road entry, no route), cleared when one arrives. The window says 'can't be delivered' (FUN_00543D10)."""
    s = set(b.misc.get("short", ()))
    (s.add if on else s.discard)(good)
    if s:
        b.misc["short"] = sorted(s)
    else:
        b.misc.pop("short", None)


def _part_kind(c):
    """The part's kind for the window's activity line (monument_progress, composite branch: vt+0xB0 temple 2, +0xA4
    statue 3, +0xA8 sculpture 4, +0xA0 tile 1, +0xC8 Grand Poseidon statue 5, else 0)."""
    if c in TEMPLES:
        return 2
    if c in STATUES:
        return 3
    if c in SCULPTURES:
        return 4
    if c in TILES:
        return 1
    return 5 if c == 151 else 0


def window(g, b):
    """What the info window of a monument under construction shows (0x005813F0, numbers from monument_progress
    0x0053ECA0 into 0x00FFA040): artisans at work, the current needs of the parts being worked (vt+0xD4), the
    activity kind, the materials still to bring in loads (ceil, sculpture / 400) with the small-piece padding
    (each stage level's tile needs rounded up to 100), shortage and halt flags."""
    from . import economy, index
    pieces = b.misc.get("pieces") or []
    working, now = 0, {k: 0 for k in GOODS}
    act, top = 0, 1
    left = {k: 0 for k in GOODS}
    for p in pieces:
        if p["c"] in BACKS:
            continue
        kind = _part_kind(p["c"])
        if not piece_done(p):
            top = max(top, kind)
        if _working(g, p):                         # monument_part_has_working_artisan: actions 7 / 8
            working += 1
            act = max(act, kind)
            for k, v in remaining(g, b, p).items():
                now[k] += max(0, v)
        st = stages(p["c"], p["e"])
        for i in range(p["s"], len(st)):
            for k, v in st[i][0].items():
                left[k] += v
        for k, v in p["held"].items():
            left[k] -= v
    pad = {k: 0 for k in SHARED}                  # 0x26 / 0x27 (+ orichalc): pad each stage level of small pieces
    levels = max((len(stages(p["c"], p["e"])) for p in pieces), default=0)
    for i in range(levels):
        tot = {k: 0 for k in SHARED}
        for p in pieces:
            if size(p["c"]) >= 2 or p["s"] > i:
                continue
            st = stages(p["c"], p["e"])
            if i < len(st):
                for k in SHARED:
                    tot[k] += st[i][0].get(k, 0)
        for k in SHARED:
            if tot[k] % 100:
                pad[k] += 100 - tot[k] % 100
    loads = {}
    for k in GOODS:
        u = max(0, left[k] + pad.get(k, 0))
        loads[k] = (u + 399) // 400 if k == "sculpture" else (u + 99) // 100
    stock = {k: 0 for k in GOODS}
    for s in g.buildings.values():
        if s.kind == "storage" and not g.cat.spec(s.key).get("endless"):
            for k in GOODS:
                stock[k] += s.goods.get(k, 0)
    return dict(pct=progress(b), road=road_entry(g, b) is not None, halted=halted(b),
                guilds=sum(1 for _ in index.keyed(g, "artisans_guild")), artisans=working, now=now,
                stock=stock, stockpiled=[k for k in GOODS if economy.stockpiled(g, k)],
                short=list(b.misc.get("short", ())), kind=act if working else top, loads=loads)


# --- jobs, artisans ------------------------------------------------------------------------------------------

def _phase(c):
    if c in TILES:
        return 0
    if c in TEMPLES:
        return 1
    if c in STATUES or c in SCULPTURES:
        return 2
    return 3


def pick_piece(g, b):
    """monument_pick_part 0x0053E740: the first free incomplete piece of the earliest unfinished phase; none when
    that phase's pieces are all taken (the other artisans wait for it). A piece is free with no live artisan."""
    if complete(b) or halted(b):                 # halted: no new jobs (root+0x64 & 0x100)
        return None
    ps = [p for p in b.misc["pieces"] if not piece_done(p) and p["c"] not in BACKS]
    if not ps:
        return None
    ph = min(_phase(p["c"]) for p in ps)
    free = [p for p in ps if _phase(p["c"]) == ph and not _working(g, p)]
    return free[0] if free else None


def _working(g, p):
    w = g.walkers.get(p["artisan"])
    return w is not None and w.role == "artisan" and w.piece >= 0 and w.target and \
        w.state in ("go", "work")


def find_job(g):
    """monuments_find_artisan_job 0x0053EC10: monuments in building order, the first piece one accepts."""
    from . import index
    for m in sorted(index.of(g, "monument"), key=lambda m: m.id):
        if m.key == "palace" or "pieces" not in m.misc or m.key not in layouts():
            continue
        p = pick_piece(g, m)
        if p is not None:
            return m, p
    return None, None


def assign(g, w, m, p):
    """vt+0x50 0x00541ED0: the piece takes the artisan; it walks to the piece's work tile (action 7)."""
    p["artisan"] = w.id
    w.target, w.piece, w.state, w.task, w.wait = m.id, idx(m, p), "go", "", 0
    t = work_tile(g, m, p)
    w.target_tile = t
    w.path = route(g, (w.x, w.y), t) if t else None
    if w.path is None:
        w.path = []
        w.target_tile = (w.x, w.y)


def update(g):
    artisans(g)
    complete_check(g)


def artisans(g):
    """Cycle step 31 (buildings_spawn_walkers 0x0048CFB0): artisans' guilds send artisans."""
    from . import index
    mons = list(index.of(g, "monument"))
    if not mons:
        return
    from .. import gods
    most = 2 if gods.active(g, 13) else 1      # artisans_guild_max_artisans 0x0048CAF0: Atlas (0x00EF607C) active: 2
    for gd in list(index.keyed(g, "artisans_guild")):
        if gd.access is None or not gd.employees or gd.misc.get("idle_until", 0) > g.tick or sum(
                1 for w in gd.walkers if w in g.walkers and g.walkers[w].role == "artisan") >= most:
            continue
        m, p = find_job(g)
        if m is None:
            gd.misc["idle_until"] = g.tick + GUILD_IDLE
            continue
        w = walkers.spawn(g, gd, "artisan")
        assign(g, w, m, p)


def complete_check(g):
    """Cycle step 32, cycle_buildings_pass_32 0x00495860: a monument's progress, completion and repair."""
    from . import index
    for m in list(index.of(g, "monument")):
        if "pieces" not in m.misc or m.key not in layouts():
            continue
        if not m.misc.get("complete"):
            m.misc["built"] = progress(m)
            if m.misc["built"] > 99:
                if m.key == "palace":                 # complete on placement; step 32 skips it (type 0x75)
                    m.misc["complete"] = True
                else:
                    completed(g, m)
        elif m.misc.get("damaged"):                   # a piece damaged by a monster (+0x64 & 0x200): the complete
            m.misc["built"] = progress(m)             # flag (+0x68) stays; rebuilt -> the extras again
            if m.misc["built"] > 99:
                m.misc.pop("damaged")
                if m.key.startswith("sanctuary_"):
                    extras_complete(g, m)
        else:
            m.misc["built"] = 100


def completed(g, m):
    """cycle_buildings_pass_32: the first time > 99%: the complete flag (+0x68), message 0xE0 (the god's / pyramid's
    name), the date (+0xBC year, +0xA3 month), a sanctuary's activity counter +0x32 = 22, +0xDA cleared (staff)."""
    m.misc.update(complete=True, built=100, completed=[g.year, g.month])
    if m.key.startswith("sanctuary_"):
        m.misc["activity"] = 22
        extras_complete(g, m)
    g.message(f"the {g.cat.spec(m.key)['name']} at ({m.x},{m.y}) is complete")


# --- extras (classes 1000..1006) on completion (monument_apply_extras 0x0053C9F0) -------------------------------
# class objects 0x00641098[c - 1000], method +0xE0: 1001 silver ore (terrain | 0x200002), 1003 copper ore (| 0x100002),
# 1002 olive tree (building 0x24), 1004 grapevine (0x23), 1005 orange tree (0xD9): a tree building on the tile
# (building_create, footprint 1x1, +0xD8 = the sanctuary root); 1000 nothing. Every extras tile first loses tree,
# scrub and meadow (& ~0x881) and keeps 0x10000000. Demeter (0x56) also turns a ring 2 tiles wide around the layout box
# into meadow (FUN_0053CFA0: tiles with terrain & 0x1FFF0F17 == 0, recorded so removal takes back only those).
# Removal (FUN_00546A60 from building_on_remove): ore bits cleared, trees removed, the ring's recorded tiles lose 0x800.
EXTRA_ORE = {1001: 0x200002, 1003: 0x100002}
EXTRA_TREE = {1002: "olive_tree", 1004: "grapevine", 1005: "fruit_tree"}


def extras_complete(g, m):
    from ..model import Building
    lay = layouts()[m.key]
    w = g.world
    trees = m.misc.setdefault("extra_trees", [])
    for i, (dx, dy, c, e) in enumerate(lay["pieces"]):
        if c < 1000:
            continue
        x, y = piece_xy(m, i)
        if not w.inside(x, y):
            continue
        w.flags[y, x] = (int(w.flags[y, x]) & ~0x881 & 0xFFFFFFFF) | 0x10000000
        if c in EXTRA_ORE:
            w.flags[y, x] |= EXTRA_ORE[c]
        elif c in EXTRA_TREE and w.occ[y, x] == m.id and EXTRA_TREE[c] in g.cat.buildings:
            spec = g.cat.spec(EXTRA_TREE[c])
            t = Building(id=g.next_bid, key=EXTRA_TREE[c], x=x, y=y, size=1, kind=spec["kind"])
            t.misc["sanctuary"] = m.id
            g.next_bid += 1
            g.buildings[t.id] = t
            w.occ[y, x] = t.id
            trees.append(t.id)
    if m.key == "sanctuary_demeter":
        ring = m.misc.setdefault("meadow_ring", [])
        bw, bh = m.misc["w"], m.misc["h"]
        x0, y0, x1, y1 = m.x, m.y, m.x + bw - 1, m.y + bh - 1
        tiles = [(x, y) for y in (y0 - 2, y0 - 1, y1 + 1, y1 + 2) for x in range(x0, x1 + 1)] + \
                [(x, y) for x in (x0 - 2, x0 - 1, x1 + 1, x1 + 2) for y in range(y0 - 2, y1 + 3)]
        for x, y in tiles:
            if w.inside(x, y) and not int(w.flags[y, x]) & 0x1FFF0F17 and (x, y) not in ring:
                w.flags[y, x] |= 0x800
                ring.append((x, y))
    g.map_version = getattr(g, "map_version", 0) + 1


def extras_removed(g, m):
    """building_on_remove -> FUN_00546A60 for a sanctuary: undo extras_complete (and the placement's ground flag)."""
    lay = layouts().get(m.key)
    if lay and m.misc.get("ground"):
        mark_ground(g, m, False)
    if not lay or not m.misc.get("complete"):
        return
    w = g.world
    for i, (dx, dy, c, e) in enumerate(lay["pieces"]):
        if c >= 1000:
            x, y = piece_xy(m, i)
            if w.inside(x, y):                    # clears 0x10000000 and the ore bits
                w.flags[y, x] &= ~(0x10000000 | EXTRA_ORE.get(c, 0)) & 0xFFFFFFFF
    for tid in m.misc.get("extra_trees", []):
        if tid in g.buildings:
            g.demolish(tid)
    for x, y in m.misc.get("meadow_ring", []):
        w.flags[y, x] &= ~0x800 & 0xFFFFFFFF


def artisan(g, w):
    """Artisan (figure 0x3A, handler 0x004C0060): walk (7), wait / work (8), next job or vanish (9)."""
    home = g.buildings.get(w.home)
    if home is None or not home.employees:          # guild gone or unstaffed: the artisan is removed
        return _leave(g, w)
    m = g.buildings.get(w.target)
    pieces = m.misc.get("pieces") if m is not None else None
    if not pieces or not 0 <= w.piece < len(pieces):
        return _next_job(g, w)                       # old saves / a monument cleared: look for work
    p = pieces[w.piece]
    if w.state == "go":
        if w.path:
            walkers.step_to(g, w, w.path.pop(0))
            d = walkers.tile_delay(g, w)
            w.wait += d
            if w.wait > REQUEST_TICKS - 1:           # asks for materials while walking too
                w.wait = 0
                request(g, m, p)
            return walkers.schedule(g, w, d)
        w.state, w.task, w.wait = "work", "wait", 0
    if piece_done(p):
        return _next_job(g, w)
    if w.task == "build":                            # the stage's work time is over
        set_stage(m, p, p["s"] + 1)
        if p["c"] in TEMPLES:                        # the temple back(s) follow the front
            for q in pieces:
                if q["c"] in BACKS:
                    set_stage(m, q, min(q["n"], p["s"]))
        w.task = ""
        return _next_job(g, w)
    if not ready(g, m, p):
        w.task = "wait"
        request(g, m, p)
        return walkers.schedule(g, w, REQUEST_TICKS)
    w.task, w.anim_t0 = "build", g.tick
    walkers.schedule(g, w, stages(p["c"], p["e"])[p["s"]][2])


def _next_job(g, w):
    """After a stage (action 9): the next job from where it stands, else it vanishes on the spot. In action 9 it is
    no longer the piece's working artisan (0x00541610), so it may take the same piece's next stage."""
    w.state = "done"
    m, p = find_job(g)
    if m is None:
        return _leave(g, w)
    assign(g, w, m, p)
    walkers.schedule(g, w, 1)


def _leave(g, w):
    m = g.buildings.get(w.target)
    if m is not None and m.misc.get("pieces") and 0 <= w.piece < len(m.misc["pieces"]):
        p = m.misc["pieces"][w.piece]
        if p["artisan"] == w.id:
            p["artisan"] = 0
    walkers.remove(g, w)


# large statues (2x2: classes 61..108, 125..132, 145..148) have a carving phase in statue_conan.txt (class +0x64
# 0x00554E60): while their stage is 1 (the marble block) the artisan at work is hidden (monument_part_work sets
# Figure+0x65 every work tick) and the piece draws the carving figure itself (+0x48 0x005407A0; play monuments.js)
CONAN = frozenset(list(range(61, 109)) + list(range(125, 133)) + list(range(145, 149)))


def carving(g, m, i):
    """The work start tick of the artisan carving piece i of monument m in its conan phase, else None."""
    p = m.misc["pieces"][i]
    if p["c"] not in CONAN or p["s"] != 1:
        return None
    for w in g.walkers.values():
        if w.role == "artisan" and w.state == "work" and w.task == "build" and w.target == m.id and w.piece == i:
            return w.anim_t0
    return None


def look(g, w):
    """Play-mode look of an artisan (walker_anim record): building = SprMain group 24 'build' frames 0..5, 2 ticks
    each; waiting for materials = the walk set's frame 3 standing still (handler 0x004C0060); carving a large
    statue: hidden (the piece draws it, CONAN)."""
    if w.role != "artisan" or w.state != "work":
        return None
    m0 = g.buildings.get(w.target)
    if w.task == "build" and m0 is not None and 0 <= w.piece < len(m0.misc.get("pieces", ())) and \
            carving(g, m0, w.piece) is not None:
        return ["hidden", 0, 0, 0, 0, 0, 0, 0, "", False]
    m = g.buildings.get(w.target)
    pieces = m.misc.get("pieces") if m is not None else None
    fx = fy = 0
    if pieces and 0 <= w.piece < len(pieces):        # face the piece (ours: the exe keeps its last walking direction)
        x, y = piece_xy(m, pieces[w.piece])
        n = size(pieces[w.piece]["c"])
        cx, cy = x + (n - 1) / 2, y + (n - 1) / 2
        fx, fy = (cx > w.x) - (cx < w.x), (cy > w.y) - (cy < w.y)
    if w.task == "build":
        return ["work", w.anim_t0, w.next_move, fx, fy, 0, 0, 0, "build", False]
    return ["work", g.tick, w.next_move, fx, fy, 0, 0, 0, "wait", False]


def staffed_ok(g, b):
    """Monuments under construction employ nobody (+0xDA, cleared on completion)."""
    return b.kind != "monument" or complete(b)
