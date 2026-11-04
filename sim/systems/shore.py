"""Shore buildings half over water, as the exe (docs/logic/production.md "Shore buildings", trade.md
"Dock placement"): fishing wharf 0x2C, urchin quay 0x2D, the dock's pier 0x3C (2x2, FUN_004A10C0) and the
trireme wharf 0x88 (3x3, FUN_004A14B0). Orientation o (Building+0xAC): 0 water to the north (-y), 1 east (+x),
2 south (+y), 3 west (-x). The exe takes the first orientation 0..3 that fits; `build KEY X Y n|e|s|w` (play
mode: R) asks for one.

Sim layout: the wharves are ordinary size x size buildings at the anchor (x, y) whose water tiles are in the
occupancy grid too (the exe sets the building bit 8 on all of them). The dock is one Building: the 4x4 dock
house (storage, workers) at (x, y), with misc["pier"] = [px, py] (the 2x2 pier, also in the occupancy grid) and
misc["orient"]. Buildings from saves before this (no misc["orient"]) keep their old land footprint and rules."""
from collections import deque

from ..world import WATER, BEACH, OFFMAP

KEYS = {"fishing_wharf": 2, "urchin_quay": 2, "dock": 2, "trireme_wharf": 3}
NAMES = {"n": 0, "e": 1, "s": 2, "w": 3, "0": 0, "1": 1, "2": 2, "3": 3}
LETTER = "nesw"

# 2x2: tiles 0x005F1968, land(0)/water(1) per orientation 0x00637E84, front tiles 0x00637EC4/EE4/F04
SQ2 = ((0, 0), (1, 0), (0, 1), (1, 1))
LW2 = ((1, 1, 0, 0), (0, 1, 0, 1), (0, 0, 1, 1), (1, 0, 1, 0))
FRONT2 = (((-1, 0), (2, 0), (-1, -1), (2, -1), (0, -1), (1, -1)),
          ((1, -1), (1, 2), (2, -1), (2, 2), (2, 0), (2, 1)),
          ((2, 1), (-1, 1), (2, 2), (-1, 2), (0, 2), (1, 2)),
          ((0, -1), (0, 2), (-1, -1), (-1, 2), (-1, 0), (-1, 1)))
# 3x3: tiles 0x005F198C, flags 0x00637F24, front 0x00637FB4
SQ3 = tuple((i, j) for j in range(3) for i in range(3))
LW3 = ((1, 1, 1, 0, 0, 0, 0, 0, 0), (0, 0, 1, 0, 0, 1, 0, 0, 1), (0, 0, 0, 0, 0, 0, 1, 1, 1), (1, 0, 0, 1, 0, 0, 1, 0, 0))
FRONT3 = (((-1, 0), (3, 0)), ((2, -1), (2, 3)), ((3, 2), (-1, 2)), ((0, -1), (0, 3)))
HOUSE = ((-1, 2), (-4, -1), (-1, -4), (2, -1))      # dock house 4x4 from the pier anchor (FUN_004534D0, view 0)
BERTH = ((1, -1), (3, 1), (1, 3), (-1, 1))          # trade ship stop from the pier anchor (0x005BA3A0)
LAND_BAD = 0x5361227                                # land tile obstacles (trees, rocks, rubble, walls...)
HOUSE_BAD = 0x3DFED66F                              # dock house tiles (map_area_buildable mask with beach apart)
MAX_DOCKS, MAX_TRIREME_WHARVES = 10, 6              # build_commit: g_dock_count > 9; DAT_00DB7B34 > 5


def is_shore(b):
    return b.key in KEYS and "orient" in b.misc


def orient_arg(d):
    """Orientation token (n/e/s/w or 0..3; None, '' or 'auto': the exe's first fit) -> int or None."""
    if d in (None, "", "auto", "a"):
        return None
    if str(d).lower() not in NAMES:
        raise ValueError(f"orientation is n, e, s, w (water side) or auto, not '{d}'")
    return NAMES[str(d).lower()]


def _land_ok(w, x, y, big):
    if not w.inside(x, y):
        return False
    f = int(w.flags[y, x])
    return not (f & (WATER | BEACH) or f & LAND_BAD or (big and f & 0x10000000)
                or w.occ[y, x] or w.road[y, x] or w.avenue[y, x])


def _water_ok(w, x, y):
    # the exe tests water bit 4, no road/bridge 0x40, no bit 1; ours also refuses a tile another building took
    # (the exe does not test bit 8 here, so two wharves could share water tiles: not reproduced)
    if not (0 <= x < w.flags.shape[1] and 0 <= y < w.flags.shape[0]):
        return False
    f = int(w.flags[y, x])
    return bool(f & WATER) and not (f & 0x1 or w.road[y, x] or w.occ[y, x])


def _front_ok(w, x, y):
    return 0 <= x < w.flags.shape[1] and 0 <= y < w.flags.shape[0] and bool(int(w.flags[y, x]) & WATER)


def pier_tiles(n, x, y, o):
    """[(tx, ty, water)] of the n x n half-water square at anchor (x, y), orientation o."""
    sq, lw = (SQ2, LW2) if n == 2 else (SQ3, LW3)
    return [(x + dx, y + dy, bool(lw[o][i])) for i, (dx, dy) in enumerate(sq)]


def front_tiles(n, x, y, o):
    return [(x + dx, y + dy) for dx, dy in (FRONT2 if n == 2 else FRONT3)[o]]


def house_tiles(x, y, o):
    hx, hy = x + HOUSE[o][0], y + HOUSE[o][1]
    return [(hx + i, hy + j) for j in range(4) for i in range(4)]


def _house_ok(w, x, y):
    if not w.inside(x, y):
        return False
    f = int(w.flags[y, x])
    return not (f & HOUSE_BAD or f & BEACH or w.occ[y, x] or w.road[y, x] or w.avenue[y, x])


def check(g, key, x, y, o):
    """Per-tile verdict of one orientation: (fits, [[tx, ty, ok], ...] for the footprint tiles)."""
    w, n = g.world, KEYS[key]
    tiles = [[tx, ty, _water_ok(w, tx, ty) if water else _land_ok(w, tx, ty, n == 3)]
             for tx, ty, water in pier_tiles(n, x, y, o)]
    fits = all(t[2] for t in tiles) and all(_front_ok(w, tx, ty) for tx, ty in front_tiles(n, x, y, o))
    if key == "dock":
        house = [[tx, ty, _house_ok(w, tx, ty)] for tx, ty in house_tiles(x, y, o)]
        fits = fits and all(t[2] for t in house)        # FUN_00453450: the house only after the pier passed
        tiles += house
    return fits, tiles


def fit(g, key, x, y, o=None):
    """The orientation the exe would take at anchor (x, y): the first of 0..3 that fits, or o if given and it fits;
    None when nothing fits."""
    for k in ((o,) if o is not None else range(4)):
        if check(g, key, x, y, k)[0]:
            return k
    return None


def sea_reachable(g, x, y):
    """building_water_access_check 0x00485670: a water tile of the size-3 edge ring around (x, y) reachable by ship
    from the sea entry (0x0058D500)."""
    w = g.world
    if getattr(w, "sea_entry", None) is None:
        return False
    v = getattr(g, "map_version", 0)
    c = getattr(g, "_sea_reach", None)
    if c is None or c[0] != v:
        seen = set()
        s = tuple(w.sea_entry)
        if 0 <= s[0] < w.flags.shape[1] and 0 <= s[1] < w.flags.shape[0] and w.flags[s[1], s[0]] & WATER:
            seen.add(s)
            q = deque([s])
            while q:
                cx, cy = q.popleft()
                for nx, ny in ((cx, cy - 1), (cx + 1, cy), (cx, cy + 1), (cx - 1, cy)):
                    if ((nx, ny) not in seen and 0 <= nx < w.flags.shape[1] and 0 <= ny < w.flags.shape[0]
                            and w.flags[ny, nx] & WATER and not w.flags[ny, nx] & OFFMAP):
                        seen.add((nx, ny))
                        q.append((nx, ny))
        c = g._sea_reach = (v, seen)
    ring = ([(x + i, y - 1) for i in range(3)] + [(x + 3, y + i) for i in range(3)] +
            [(x + i, y + 3) for i in range(2, -1, -1)] + [(x - 1, y + i) for i in range(2, -1, -1)])
    return any(t in c[1] for t in ring)


def site_error(g, key, x, y, o=None):
    """'' when `build KEY X Y [o]` may go there, else (message, warning ids of text group 19)."""
    if key == "dock" and sum(1 for b in g.buildings.values() if b.key == "dock") >= MAX_DOCKS:
        return "You may only have 10 active Piers", (30,)
    if key == "trireme_wharf" and sum(1 for b in g.buildings.values() if b.key == key) >= MAX_TRIREME_WHARVES:
        return "You have a full fleet of warships (6 trireme wharves)", (29,)
    k = fit(g, key, x, y, o)
    if k is None:
        side = f" facing {LETTER[o]}" if o is not None else ""
        return (f"{key} at ({x},{y}){side}: find a good site along the water (half the "
                f"{KEYS[key]}x{KEYS[key]} on land, not beach, the other half and the tiles in front on water"
                + (", the 4x4 dock house on free land behind it" if key == "dock" else "") + ")"), (23,)
    if key in ("dock", "trireme_wharf") and not sea_reachable(g, x, y):
        return "This lake has no access to the sea", (25,)
    return ""


def layout(key, x, y, o):
    """(building x, y, size, occupied tiles, misc) of a shore building with pier/square anchor (x, y)."""
    n = KEYS[key]
    sq = [(tx, ty) for tx, ty, _ in pier_tiles(n, x, y, o)]
    if key == "dock":
        hx, hy = x + HOUSE[o][0], y + HOUSE[o][1]
        return hx, hy, 4, sq + house_tiles(x, y, o), {"orient": o, "pier": [x, y]}
    return x, y, n, sq, {"orient": o}


def mooring(g, b):
    """The water tile a wharf's boat (or urchin collector) starts from and comes back to: building_water_exit
    0x004A3FD0 on the wharf's square (the dock: its pier)."""
    from . import walkers
    if b.key == "dock" and "pier" in b.misc:
        return walkers.water_exit(g, b.misc["pier"][0], b.misc["pier"][1], 2)
    return walkers.water_exit(g, b.x, b.y, b.size, connected=not is_shore(b))   # old land-placed: old rule


def remoor(g):
    """Saves from before 2026-10-29 (bugs.md 173) moored wharf boats, urchin divers' quays and triremes by the old
    water-exit rule (>= 8 connected water tiles: often the tile beside the water half). Boats get the exe's mooring
    as their home (they sail there on their next trip); a moored trireme (it never moves while waiting for
    orders) is put on it."""
    if getattr(g, "moor_v", 0):
        return
    for b in g.buildings.values():
        if not is_shore(b) or b.key == "dock":
            continue
        t = mooring(g, b)
        if t is None:
            continue
        for wid in b.walkers:
            w = g.walkers.get(wid)
            if w is None:
                continue
            if w.role == "boat" and tuple(w.origin or ()) != t:
                w.origin = t
            elif w.role == "trireme" and w.state == "moored" and (w.x, w.y) != t:
                w.x, w.y = t
                w.prev = t
                walkers.listed(g, w)
    g.moor_v = 1


def berth(g, b):
    """Where a trade ship stops at a dock (0x005BA3A0, from the pier anchor and orientation). Not in the exe: when
    that tile is not water ships can be on (grid_ship 0xFF: it is not among the tiles placement requires to be
    water) the pier's mooring is used, so the ship is not lost; old land docks use their water exit as before."""
    from . import walkers
    if "pier" in b.misc:
        px, py = b.misc["pier"]
        dx, dy = BERTH[b.misc.get("orient", 0)]
        t = (px + dx, py + dy)
        if walkers.ship_ok(g, *t):
            return t
    return mooring(g, b)


def sites(g, key, limit=40):
    """Anchors where `build KEY X Y` would pass the shore test now: [(x, y, orientation letter)]."""
    w, out = g.world, []
    n = w.flags.shape[0]
    water = (w.flags & WATER) != 0
    for y in range(1, n - 1):
        for x in range(1, n - 1):
            if not water[max(0, y - 2):y + 4, max(0, x - 2):x + 4].any():
                continue
            if not site_error(g, key, x, y):
                out.append((x, y, LETTER[fit(g, key, x, y)]))
                if len(out) >= limit:
                    return out
    return out
