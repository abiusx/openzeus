"""The 228x228 tile map: terrain from a Zeus .map/.pak, plus occupancy, roads and desirability."""
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import mapfile  # noqa: E402

N = 228
# Terrain bits (docs/logic/map-terrain.md)
TREE, ROCK, WATER, SCRUB, CLIFF, MEADOW = 0x1, 0x2, 0x4, 0x80, 0x200, 0x800
MARBLE, BEACH, OFFMAP, DEEP = 0x20000, 0x10000, 0x80000, 0x4000000
RAMP = 0x400             # ramp up a cliff (map-terrain.md): roads may cross it, buildings not
RUBBLE = 0x1000          # left by fires and collapses (buildings.md: -2 desirability; clear it to build)
WALL = 0x4000            # city wall tiles (military.md)
REEDS = 0x40000           # marsh (map-terrain.md)
ROAD = 0x40              # road (road_set_tile 0x0049FF10); ours keeps roads in World.road, see start_terrain
# free_land (the scripts' L-shaped `road`, `path ... clear`) refuses these. The game's drag is sim/roaddrag.py (the exe's
# masks: flood 0x10060001 + route grid, ends 0x5361227; map-terrain.md "Road drag"): rubble and beach are crossed.
# cooled lava (0x1000000: lava_node_burn 0x00506D80 sets it for good; clear land keeps it, & 0x93B72F92) is refused
# by all of them as by the exe: map_area_buildable 0x3DFFD66F, the road drag's ends 0x5361227 and its flood (route
# grid 0x005876F0: & 0x2DFFD66F = blocked), walls_drag 0x1537166F (bug 448: ours built houses and corrals on it)
LAVA = 0x1000000
BLOCKING = TREE | ROCK | WATER | CLIFF | OFFMAP | WALL | MARBLE | REEDS | LAVA
# buildings refuse these as well (map_area_buildable 0x004A0DC0 mask 0x3DFFD66F; allow_beach only for the road,
# clear and roadblock tools, build_tool_allows_beach 0x00496490), and so do walls (walls_drag mask 0x1537166F):
# rubble must be cleared first (clear land, 2 dr), beach is never built on. Scrub 0x80, meadow, flood plain are
# buildable (bugs.md 83)
BUILD_BLOCKING = BLOCKING | RUBBLE | BEACH

# maps a new game can start on, with each map's default difficulty: data/maps.json (hand-edited)
import json  # noqa: E402
MAP_INFO = {k: v for k, v in json.load(open(os.path.join(ROOT, "data", "maps.json"))).items() if not k.startswith("_")}
MAPS = {k: os.path.join(ROOT, MAP_INFO.get(v.get("map"), v)["file"]) for k, v in MAP_INFO.items()}


def play(map_name):
    """(map, episode) of a new game on map_name. A data/maps.json entry may play another entry's map and data
    ("map": sandbox_open -> sandbox: same map, empire and scenario files) and may name the open play's episode
    ("episode": "CAMPAIGN#SLOT" of data/campaign, applied as the exe starts it: sim/episode.py open_play). Other
    names: (map_name, None)."""
    v = MAP_INFO.get(map_name)
    if v is None:
        return map_name, None
    return v.get("map", map_name), v.get("episode")


def map_path(map_name):
    """(file, container) of a map name: a data/maps.json key or a file path, `PATH#N` = map container N of a .pak
    (0 the parent city, 1..4 colony n: the adventure's map_offsets, mapfile.pak_map); container None = the file's
    first MAPS container (mapfile.read_file(...)[0]: right for single-map files only, a multi-map .pak's first
    container is its LAST map, docs/campaign-format.md)."""
    base, sep, idx = map_name.rpartition("#")
    if sep and idx.isdigit():
        return MAPS.get(base, base), int(idx)
    return MAPS.get(map_name, map_name), None


_READ = {}


def read_map(map_name):
    """(hdr, blocks) of a map name (map_path), read once per process (the blocks are read-only bytes)."""
    m = _READ.get(map_name)
    if m is None:
        path, idx = map_path(map_name)
        if path.lower().endswith(".sav"):           # an original saved game (sim/savimport.py, 1L-5)
            from . import savimport
            m = savimport.map_container(path if os.path.isabs(path) else os.path.join(ROOT, path))
        else:
            m = mapfile.read_file(path)[0] if idx is None else mapfile.pak_map(path, idx)
        if m is None:
            raise ValueError(f"{path}: no map container {idx}")
        _READ[map_name] = m
    return m


def map_difficulty(map_name):
    """The map's default difficulty (data/maps.json); Normal for a map file not listed there. The exe keeps the
    player's setting across a map load (0x0042B230 / 0x00511C90 save and restore g_difficulty around the read)."""
    return MAP_INFO.get(map_name, {}).get("difficulty", "Normal")


# Scenario points (docs/logic/map-terrain.md "Logical and raw coordinates"): the map stores them logical, as the exe
# uses them (figure_create(x, y) and the grids index 0x00DA2F80 + 228 y + x; the editor draws each marker there,
# FUN_004040D0). World keeps them raw = logical + origin, converted here and nowhere else.
POINTS_V = 1          # World.points_v: 0/missing = a world pickled with logical points (Game.load migrates)


def _shift(p, o):
    return None if p is None else (p[0] + o[0], p[1] + o[1])


def in_play_area(x, y, size):
    """map_in_play_area 0x00496010 for a logical point: the play area's diamond on the 228 grid (FUN_00495E90 from
    the map's W, H: x0 = (228 - W) / 2 .. x0 + W - 1, its centre column; the same for y)."""
    W, H = size
    x0, y0 = (228 - W) // 2, (228 - H) // 2
    x1, y1 = x0 - 1 + W, y0 - 1 + H
    cx, cy = (x1 + x0) // 2, (y1 + y0) // 2
    x, y = x0 + x, y0 + y
    if cx < x:
        return x + y <= x1 + 1 + cy if cy < y else x - y <= x1 - cy
    return cx - y1 <= x - y if cy < y else x0 + cy <= x + y


AREA_CHECKED = ("land_invasion", "sea_invasion", "disaster")   # FUN_00510ED0's two loops (every load, map or save)


def scenario_points(blocks):
    """{table: [raw (x, y) or None per slot]} of every point table of the map (tools/mapfile.py _POINT_TABLES). The
    invasion points (g_invasion_points, 16) and disaster points (0x00902CBC / 0x00902CCC, 8) outside the play area
    are cleared to -1, as FUN_00510ED0 does after every map or save load (no shipped map has one)."""
    o = mapfile.scenario_origin(blocks)
    size = _size(blocks)
    out = {}
    for k in mapfile._POINT_TABLES:
        pts = mapfile.scenario_slots(blocks, k)
        if k in AREA_CHECKED:
            pts = [p if p is None or in_play_area(p[0], p[1], size) else None for p in pts]
        out[k] = [_shift(p, o) for p in pts]
    return out


def map_points(map_name):
    """scenario_points of a map file (raw)."""
    hdr, blocks = read_map(map_name)
    return scenario_points(blocks)


def map_origin(map_name):
    """The raw tile of a map file's logical (0, 0) (mapfile.scenario_origin; for worlds pickled before World.origin)."""
    hdr, blocks = read_map(map_name)
    return mapfile.scenario_origin(blocks)


def monster_points(map_name):
    """The raw monster points of a map file (for worlds pickled before World.monster_points)."""
    return [p or (-1, -1) for p in map_points(map_name)["monster"]]


def _size(blocks):
    """The play area's (W, H): scenario block +0x2C / +0x30 (0x00902954 / 0x00902958; 226 on the sandbox maps)."""
    d = [b for b in blocks if b["rank"] == 14][0]["data"]
    return tuple(int(v) for v in np.frombuffer(d[0x2C:0x34], "<i4"))


def set_points(w, pts, origin):
    """The World's point attributes from scenario_points (raw)."""
    w.origin = origin                                         # raw tile of logical (0, 0)
    w.points = pts                                            # every table, per slot (None = empty)
    w.entry = pts["entry"][0] or (-1, -1)
    w.exit = pts["exit"][0] or (-1, -1)
    w.sea_entry = pts["sea_entry"][0]                         # sea entry/exit (trade.md: 0x00902CDC)
    w.sea_exit = pts["sea_exit"][0] or w.sea_entry
    # wildlife and fishing points placed with the map editor (map-terrain.md "Herd, predator and fishing points"):
    # boar herds (the "deer" table spawns boar too), wolf packs, fishing spots; the spawner skips x <= 0 (logical)
    used = lambda k: [p for p in pts[k] if p and p[0] - origin[0] > 0]
    w.boar_points = used("boar") + used("deer")
    w.wolf_points = used("wolf")
    w.fishing_spots = used("fishing")
    w.urchin_spots = used("urchin")                           # urchin quays; drawn in play mode (walkers.md "Water life")
    w.monster_points = [p or (-1, -1) for p in pts["monster"]]   # monster lairs (sim/heroes, heroes-monsters.md)
    w.points_v = POINTS_V


def migrate_points(g):
    """Game.load: a world pickled before POINTS_V kept the map's points logical (and used them as raw, one tile off on
    the sandbox). Takes the raw points from the map file and moves what was keyed by the old points: the herd timers
    and boar origins (systems/wild.py), the wolf packs and wolf origins (military/wolves.py), the cached point lists.
    Figures already walking stay where they are (they are on the raw grid)."""
    w = g.world
    if getattr(w, "points_v", 0) >= POINTS_V:
        return
    hdr, blocks = read_map(g.map_name)
    o = mapfile.scenario_origin(blocks)
    old = {tuple(p): k for k in ("boar_points", "wolf_points", "fishing_spots", "urchin_spots")
           for p in (getattr(w, k, None) or [])}
    old_fish = [tuple(p) for p in (getattr(w, "fishing_spots", None) or [])]
    old_prey = [tuple(p) for p in (getattr(w, "boar_points", None) or [])]
    set_points(w, scenario_points(blocks), o)
    w.size = _size(blocks)
    move = {p: _shift(p, o) for p in old}
    if [tuple(p) for p in (getattr(g, "_fishing_points", None) or [])] == old_fish:
        g._fishing_points = list(w.fishing_spots)            # else: generated on the raw grid (maps without points)
    if [tuple(p) for p in (getattr(g, "_prey_points", None) or [])] == old_prey:
        g._prey_points = list(w.boar_points)
    for d in (getattr(g, "herd_timers", None), (getattr(g, "mil", None) or {}).get("packs")):
        for p in list(d or {}):
            if p in move:
                d[move[p]] = d.pop(p)
    for a in getattr(g, "walkers", {}).values():
        if a.role in ("boar", "deer", "wolf") and getattr(a, "origin", None) is not None and tuple(a.origin) in move:
            a.origin = move[tuple(a.origin)]


def start_terrain(flags):
    """The terrain fixes the exe applies to a map at a new game (docs/logic/map-terrain.md "Start state"):
    FUN_0051D2B0 -> FUN_0051D760 -> FUN_00521520(3) -> map_elevation_project 0x0045ED20 walks the play area and
    clears ramp 0x400 and 0x800000 off cliffs, and meadow 0x800, scrub 0x80 and tree 0x1 on cliffs 0x200. On the
    sandbox that removes the tree bit of 12 cliff tiles (oracle open-play-events / 1H-god tick 0: the terrain grid
    is the map's otherwise, every other grid equal to the map's). In place."""
    play = (flags & OFFMAP) == 0
    cliff = (flags & CLIFF) != 0
    flags[play & ~cliff] &= np.uint32(~(RAMP | 0x800000) & 0xFFFFFFFF)
    flags[play & cliff] &= np.uint32(~(MEADOW | SCRUB | TREE) & 0xFFFFFFFF)


class World:
    def __init__(self, map_name="sandbox"):
        hdr, blocks = read_map(map_name)
        b = {x["rank"]: x["data"] for x in blocks}
        self.flags = np.frombuffer(b[6], "<u4").reshape(N, N).copy()     # [y][x]
        start_terrain(self.flags)
        self.elev = np.frombuffer(b[23], np.uint8).reshape(N, N).copy()
        # the map's own terrain images (play mode; docs/play-mode.md): image id per tile
        # (collection*0x4000 + n) and draw flags (0x40: an image is drawn at this tile)
        self.image_ids = np.frombuffer(b[4], "<u4").reshape(N, N).copy()
        self.draw_flags = np.frombuffer(b[5], np.uint8).reshape(N, N).copy()
        self.file_version = hdr["version"]
        self.size = _size(blocks)
        set_points(self, scenario_points(blocks), mapfile.scenario_origin(blocks))
        self.occ = np.zeros((N, N), np.int32)       # building id per tile (roads are not buildings)
        # the map's own roads (terrain 0x40, e.g. the sandbox's entry-to-exit road; bugs.md 233): the exe keeps
        # them in the terrain grid it loads (oracle tick 0 = the map's grid); they are ordinary roads. The 0x40
        # bits stay in flags (the exe's grid); World.road is ours (terrain_view masks stale flag bits)
        self.road = (self.flags & ROAD) != 0
        self.des = np.zeros((N, N), np.int16)
        self.road_net = np.zeros((N, N), np.int32)  # road network id per road tile
        self.avenue = np.zeros((N, N), np.int16)    # avenue/boulevard tiles (systems/avenues.py)

    # --- queries ----------------------------------------------------------------------
    def inside(self, x, y):
        return 0 <= x < N and 0 <= y < N and not self.flags[y, x] & OFFMAP

    def free_land(self, x, y):
        """Land a road may be laid on (BLOCKING): no building, road or avenue on it. A ramp (0x400, on cliff
        tiles) carries roads: the route grid marks it passable (0x10) and a road on it 0x100 (pathfinding.md §2)."""
        f = self.flags[y, x] if 0 <= x < N and 0 <= y < N else 0
        block = BLOCKING & ~CLIFF if f & RAMP else BLOCKING
        return (self.inside(x, y) and not f & block
                and self.occ[y, x] == 0 and not self.road[y, x] and not self.avenue[y, x])

    def build_land(self, x, y):
        """free_land that a building or wall may also take (BUILD_BLOCKING: no rubble, no beach, no ramp/cliff:
        map_area_buildable mask 0x3DFFD66F has 0x400 and 0x200)."""
        return self.free_land(x, y) and not self.flags[y, x] & (RUBBLE | BEACH | CLIFF | RAMP)

    def kind(self, x, y):
        f = self.flags[y, x]
        if f & OFFMAP: return "offmap"
        if f & WATER: return "water"
        if f & CLIFF: return "cliff"
        if f & WALL: return "wall"
        if f & ROCK:
            if f & MARBLE: return "marble"
            kind = f & 0x300000                 # map-terrain.md: 0x100002 copper, 0x200002 silver
            return "copper" if kind == 0x100000 else "silver" if kind == 0x200000 else "rock"
        if f & TREE: return "tree"
        if f & RUBBLE: return "rubble"
        if f & (MEADOW | BEACH): return "meadow"
        return "land"

    def blocked_kind(self, x, y):
        """kind() for messages, naming marble/marsh tiles (kind() keeps its codes: sim/export.py)."""
        f = self.flags[y, x]
        if f & LAVA:
            return "lava"
        return ("marble" if f & MARBLE else "marsh" if f & REEDS and not f & WATER
                else "beach" if f & BEACH and not f & (WATER | ROCK | CLIFF | TREE) else self.kind(x, y))

    def near_play_edge(self, x, y):
        """map_near_play_edge(x, y, 3) 0x00496080 as map_area_buildable 0x004A0DC0 uses it: a play-area tile within 3
        tiles of the play area's diamond edge (the tile 3 steps along x or y is off the map; the exe compares x+y or
        x-y with the edge line of the tile's quadrant, which is the same test away from the 4 corners), or within 3
        of the grid's border (x < 3, y < 3, x > 224, y > 224). Buildings never stand there."""
        edge = getattr(self, "_edge", None)
        if edge is None:
            off = np.pad((self.flags & OFFMAP) != 0, 3, constant_values=True)
            edge = off[3:-3, 6:] | off[3:-3, :-6] | off[6:, 3:-3] | off[:-6, 3:-3]
            edge[:3, :] = edge[-3:, :] = edge[:, :3] = edge[:, -3:] = True
            self._edge = edge
        return bool(edge[y, x])

    def area_ok(self, x, y, size):
        """(ok, reason) for placing a size x size footprint with top-left (x, y). No level test: map_area_buildable
        0x004A0DC0 has one only through its param 6, which no placement caller passes (10-29); on the shipped
        maps two adjacent buildable tiles almost never differ in height (2 pairs in 16 maps), cliffs and
        ramps between levels being blocked anyway."""
        for yy in range(y, y + size):
            for xx in range(x, x + size):
                if not self.inside(xx, yy): return False, f"({xx},{yy}) is off the map"
                if self.near_play_edge(xx, yy): return False, f"({xx},{yy}) is within 3 tiles of the map edge"
                if self.occ[yy, xx] or self.road[yy, xx] or self.avenue[yy, xx]: return False, f"({xx},{yy}) is occupied"
                if self.flags[yy, xx] & BUILD_BLOCKING: return False, f"({xx},{yy}) is {self.blocked_kind(xx, yy)}"
        return True, ""

    def ring(self, x, y, size, r):
        """Tiles at Chebyshev distance exactly r from a footprint."""
        x0, y0, x1, y1 = x - r, y - r, x + size - 1 + r, y + size - 1 + r
        for xx in range(x0, x1 + 1):
            yield xx, y0
            yield xx, y1
        for yy in range(y0 + 1, y1):
            yield x0, yy
            yield x1, yy

    def around(self, x, y, size, kind_test):
        """True if any tile in ring 1 satisfies kind_test(flags)."""
        for xx, yy in self.ring(x, y, size, 1):
            if 0 <= xx < N and 0 <= yy < N and kind_test(int(self.flags[yy, xx])):
                return True
        return False

    def road_neighbors(self, x, y):
        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < N and 0 <= ny < N and self.road[ny, nx]:
                yield nx, ny
