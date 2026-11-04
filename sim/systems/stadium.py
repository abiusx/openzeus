"""Stadium (type 80): two 5x5 halves, one building in the sim (docs/logic/buildings.md "Stadium").

The exe places a root part at (x, y) and a second part 5 tiles further along y (orientation 0, the
default; 5x10) or along x (orientation 1, R toggles; 10x5): FUN_005AFB40 over the layout table
0x005E4958 (0xE0 per orientation, 0x38 per camera view). Each half must be buildable on its own
(FUN_005B03A0: map_area_buildable per 5x5), and only one stadium may exist (g_unique_venue_exists,
shared with the museum; warning 19:44). Road access: either half (FUN_005B04F0 -> FUN_005B0600).
Ours: one Building, size 5, misc w/h = the whole rectangle and misc orient 0|1; the service, shows
and walkers are the root's (the exe's second part is only a footprint).
"""
from ..model import Building
from . import roads

HALF = 5


def orient_of(d):
    """Command/viewer token -> exe orientation: v (default) = 0 (5x10), h = 1 (10x5)."""
    if d in (None, "", "v", "0", "y"):
        return 0
    if d in ("h", "1", "x"):
        return 1
    raise ValueError(f"stadium orientation is v (5x10, default) or h (10x5), not '{d}'")


def layout(x, y, d=None):
    """(w, h, [half top-left corners]) for a stadium with its root at (x, y)."""
    if orient_of(d) == 0:
        return HALF, 2 * HALF, [(x, y), (x, y + HALF)]
    return 2 * HALF, HALF, [(x, y), (x + HALF, y)]


def exists(g):
    """The exe's g_unique_venue_exists: a stadium or a museum stands (FUN_005B0360 + museum create)."""
    return any(g.cat.spec(b.key).get("unique_venue") for b in g.buildings.values() if b.key in g.cat.buildings)


def check(g, x, y, d=None):
    """Raise CommandError if a stadium can't go at (x, y) [d]; returns (w, h, halves)."""
    from ..game import CommandError
    try:
        bw, bh, halves = layout(x, y, d)
    except ValueError as e:
        raise CommandError(str(e))
    if exists(g):
        raise CommandError("you may only have one stadium (or museum) in a city", (44,))
    for hx, hy in halves:
        ok, why = g.world.area_ok(hx, hy, HALF)      # each half level on its own, as the exe
        if not ok:
            raise CommandError(f"can't build stadium at ({x},{y}): {why}", (18,))
    return bw, bh, halves


def build(g, x, y, d=None):
    import numpy as np
    bw, bh, _ = check(g, x, y, d)
    spec = g.cat.spec("stadium")
    g.spend(spec["cost"], "construction")
    b = Building(id=g.next_bid, key="stadium", x=x, y=y, size=HALF, kind=spec["kind"])
    b.misc.update(w=bw, h=bh, orient=orient_of(d))
    g.next_bid += 1
    g.buildings[b.id] = b
    w = g.world
    w.occ[y:y + bh, x:x + bw] = b.id
    w.flags[y:y + bh, x:x + bw] &= np.uint32(~0x1000 & 0xFFFFFFFF)
    g.map_version = getattr(g, "map_version", 0) + 1
    roads.update_access(g, b)
    warn = "" if b.access else "  WARNING: no road access (needs a road touching one side)"
    return f"built stadium #{b.id} at ({x},{y}) {bw}x{bh}, cost {spec['cost']}{warn}"


def upgrade(g):
    """Saves from before 2026-10-28 have 5x5 stadiums. Grow each into its second half where that 5x5
    is buildable (v first, the exe default, then h); otherwise it stays a 5x5 (drawn as one half)."""
    import numpy as np
    w = g.world
    for b in g.buildings.values():
        if b.key != "stadium" or "w" in getattr(b, "misc", {"w": 0}):     # (very old saves: no misc)
            continue
        for o, (hx, hy) in ((0, (b.x, b.y + HALF)), (1, (b.x + HALF, b.y))):
            if w.area_ok(hx, hy, HALF)[0]:
                bw, bh, _ = layout(b.x, b.y, "hv"[1 - o])
                b.misc.update(w=bw, h=bh, orient=o)
                w.occ[hy:hy + HALF, hx:hx + HALF] = b.id
                w.flags[hy:hy + HALF, hx:hx + HALF] &= np.uint32(~0x1000 & 0xFFFFFFFF)
                g.map_version = getattr(g, "map_version", 0) + 1
                roads.update_access(g, b)
                break
