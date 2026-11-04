"""Horse ranch = the 3x3 ranch house plus its 4x4 corral, as the exe (docs/logic/production.md "Horse ranch parts",
bugs.md 134): FUN_00496CA0 case 0x85 creates the corral 0x86 at the house anchor + 0x00637E60[orientation]; the
horses are created in it (0x0063365C) and only ever pick tiles of it (ranch_horse_pick_dest 0x004D0140).

Sim layout: one Building (the 3x3 house at (x, y), size 3) with misc["orient"] and misc["corral"] = [cx, cy]; the
corral's 16 tiles are in the occupancy grid too. Orientation (the exe's DAT_00DA23C4, 0 when the tool is picked,
the player turns it): 0 corral east (+x), 1 north (-y), 2 west (-x), 3 south (+y). Ranches of saves before this
have no corral: `adopt` gives them one (free) at the first orientation whose 4x4 is free land, else they keep the
old free-roaming horses."""
from collections import deque

CORRAL = ((3, -1), (-1, -4), (-4, 0), (0, 3))       # 0x00637E60 (view 0)
SLOTS = ((0, 0), (2, 0), (1, 1), (2, 1), (0, 2), (2, 2))   # 0x0063365C: horse n is created at corral + SLOTS[n]
NAMES = {"0": 0, "1": 1, "2": 2, "3": 3, "e": 0, "n": 1, "w": 2, "s": 3}
LETTER = "enws"


def orient_arg(d):
    if d in (None, ""):
        return 0                                      # build_tool_select 0x00404330: DAT_00DA23C4 = 0
    if str(d).lower() not in NAMES:
        raise ValueError(f"horse ranch orientation is 0..3 or e/n/w/s (where the corral goes), not '{d}'")
    return NAMES[str(d).lower()]


def corral_at(x, y, o):
    return x + CORRAL[o][0], y + CORRAL[o][1]


def corral_tiles(x, y, o):
    cx, cy = corral_at(x, y, o)
    return [(cx + i, cy + j) for j in range(4) for i in range(4)]


def has_corral(b):
    return b.key == "horse_ranch" and "corral" in b.misc


def in_corral(b, x, y):
    cx, cy = b.misc["corral"]
    return cx <= x < cx + 4 and cy <= y < cy + 4


def check(g, x, y, o):
    """(why or "", [[tx, ty, ok]...] for the 3x3 house + the 4x4 corral): the generic test on each part
    (build_commit: the 3x3, then map_area_buildable on the 4x4; 19:18 when it fails)."""
    w = g.world
    wt = {} if getattr(g, "script_mode", False) else g.walker_tiles()   # walkers refuse it too (0x004A0DC0)
    ok_h, why_h = w.area_ok(x, y, 3)
    if ok_h and g.walker_on(x, y, 3, 3, wt):
        ok_h, why_h = False, g.walker_on(x, y, 3, 3, wt)
    cx, cy = corral_at(x, y, o)
    ok_c, why_c = w.area_ok(cx, cy, 4)
    if ok_c and g.walker_on(cx, cy, 4, 4, wt):
        ok_c, why_c = False, g.walker_on(cx, cy, 4, 4, wt)
    land = getattr(w, "build_land", w.free_land)
    ok_t = lambda tx, ty: bool(land(tx, ty)) and not w.near_play_edge(tx, ty) and (tx, ty) not in wt
    tiles = [[x + i, y + j, ok_h or ok_t(x + i, y + j)] for j in range(3) for i in range(3)]
    tiles += [[tx, ty, ok_c or ok_t(tx, ty)] for tx, ty in corral_tiles(x, y, o)]
    why = "" if ok_h and ok_c else (f"ranch house: {why_h}" if not ok_h else f"corral ({cx},{cy}) 4x4: {why_c}")
    if why and all(t[2] for t in tiles):
        for t in tiles:
            t[2] = False
    return why, tiles


def attach(g, b, o):
    """Give ranch b its corral at orientation o (occupancy, misc)."""
    cx, cy = corral_at(b.x, b.y, o)
    b.misc.update(orient=o, corral=[cx, cy])
    for tx, ty in corral_tiles(b.x, b.y, o):
        g.world.occ[ty, tx] = b.id
    g.map_version = getattr(g, "map_version", 0) + 1


def adopt(g, b):
    """A ranch from an older save (no corral): attach one at the first orientation whose 4x4 is free, and put its
    horses in it. False when there is no room (it keeps the old behaviour)."""
    if has_corral(b) or b.misc.get("no_corral_room") == getattr(g, "map_version", 0):
        return has_corral(b)
    for o in range(4):
        cx, cy = corral_at(b.x, b.y, o)
        if g.world.area_ok(cx, cy, 4)[0]:
            attach(g, b, o)
            for i, h in enumerate(horses(g, b)):
                dx, dy = SLOTS[i % len(SLOTS)]
                h.x, h.y, h.path, h.origin = cx + dx, cy + dy, [], (cx + dx, cy + dy)
            g.message(f"Horse ranch at ({b.x},{b.y}): its corral is now at ({cx},{cy}) (4x4); the horses stay in it")
            return True
    b.misc["no_corral_room"] = getattr(g, "map_version", 0)      # retry once the map changes
    return False


def horses(g, b):
    return [g.walkers[i] for i in b.walkers if i in g.walkers and g.walkers[i].role == "horse"]


def spawn_tile(g, b, n):
    """Where the ranch's n-th horse appears (corral + 0x0063365C[n])."""
    cx, cy = b.misc["corral"]
    dx, dy = SLOTS[min(n, len(SLOTS) - 1)]
    return cx + dx, cy + dy


def _ok(g, b, w, x, y):
    # ranch_horse_pick_dest: the tile and its second tile (taken as (+1, +1), docs) in this corral, nobody on it
    if not (in_corral(b, x, y) and in_corral(b, x + 1, y + 1)):
        return False
    return not any(o.x == x and o.y == y and o.id != w.id for o in horses(g, b))


def hop(g, w, b):
    """ranch_horse_pick_dest 0x004D0140: up to 100 tries of (dx, dy) in -4..+3 from where the horse stands; the
    path there inside the corral (4-neighbour), or None (it stays)."""
    for _ in range(100):
        x, y = w.x + g.rng.randrange(8) - 4, w.y + g.rng.randrange(8) - 4
        if (x, y) != (w.x, w.y) and _ok(g, b, w, x, y):
            return _path(b, (w.x, w.y), (x, y))
    return None


def _path(b, a, z):
    prev, q = {a: None}, deque([a])
    while q:
        t = q.popleft()
        if t == z:
            out = []
            while prev[t] is not None:
                out.append(t)
                t = prev[t]
            return out[::-1]
        for n in ((t[0] + 1, t[1]), (t[0] - 1, t[1]), (t[0], t[1] + 1), (t[0], t[1] - 1)):
            if n not in prev and in_corral(b, *n):
                prev[n] = t
                q.append(n)
    return None
