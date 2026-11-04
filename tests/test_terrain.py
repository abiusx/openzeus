"""Terrain, placement, roads and bridges, route grids and searches.
Run: python3 tests/test_sim.py terrain (or a test by name: python3 tests/test_sim.py test_NAME)."""
import os

from helpers import Game, _route_search_literal


def test_meadow_picture_lag():
    """figure_graze 0x004F8770 zeroes the regrowth byte without redrawing: the eaten tile keeps its picture until the
    next daily regrow (oracle 1F-meadow2 tile (129, 124), tools/meadow_check.py); then the byte is 15/16."""
    from sim.systems import walkers
    g = Game("sandbox_open", 1)
    x, y = 10, 10
    g.sd("grass_bare", {})[(x, y)] = g.day
    g.sd("grass_held", {})[(x, y)] = (g.day, 255)
    assert walkers.meadow_regrowth(g, x, y) == 0 and walkers.picture_regrowth(g, x, y) == 255
    assert walkers.picture_regrowth(g, x, y, g.day + 1) in (15, 16)
    g.grass_bare[(x, y)] = g.day - 1                                     # eaten again yesterday from 15/16:
    g.grass_held[(x, y)] = (g.day - 1, 16)                               # yesterday's picture held, today's follows
    assert walkers.picture_regrowth(g, x, y, g.day - 1) == 16 and walkers.picture_regrowth(g, x, y) in (15, 16)


def test_shore_buildings():
    """Wharves/quay/pier half over water, first fitting orientation; dock = pier + 4x4 house behind it; berth
    (production.md "Shore buildings", trade.md "Dock placement", bugs.md 131)."""
    from sim.game import CommandError
    from sim.model import Building, Walker
    from sim.systems import shore, walkers
    g = Game("sandbox_open", 1)
    w = g.world
    for bad in ("build fishing_wharf 140 100", "build fishing_wharf 114 105", "build dock 114 104 n"):
        try:
            g.command(bad)                       # inland / all water / the north side is land
            raise AssertionError(bad)
        except CommandError as e:
            assert e.warn == (23,) or "orientation" in str(e), (bad, e.warn)
    out = g.command("build fishing_wharf 114 104")
    b = g.buildings[w.occ[104, 114]]
    assert "facing s" in out and b.misc["orient"] == 2 and (b.x, b.y, b.size) == (114, 104, 2)
    assert w.occ[105, 114] == b.id and w.flags[105, 114] & 0x4                  # the water half is the building's
    # boat mooring (0x004A3FD0): the first ring tile whose 8 neighbours are all water, i.e. straight out in front
    # of the water half (exe working city: o1 wharves (2,0), the o2 one (1,2)); the old rule took (116,105) beside it
    assert shore.mooring(g, b) == (115, 106)
    assert walkers.water_exit(g, 114, 104, 2, connected=True) == (116, 105)
    g.walkers[10 ** 6] = Walker(id=10 ** 6, role="boat", home=b.id, x=116, y=105, origin=(116, 105), state="rest")
    b.walkers.append(10 ** 6)
    g.moor_v = 0
    shore.remoor(g)                              # old saves: the boat's home becomes the exe mooring
    assert g.walkers[10 ** 6].origin == (115, 106) and (g.walkers[10 ** 6].x, g.walkers[10 ** 6].y) == (116, 105)
    g.walkers.pop(10 ** 6)
    b.walkers.remove(10 ** 6)
    out = g.command("build dock 112 104")
    d = next(x for x in g.buildings.values() if x.key == "dock")
    assert (d.x, d.y, d.size, d.misc["pier"], d.misc["orient"]) == (111, 100, 4, [112, 104], 2), out
    assert w.occ[100, 111] == w.occ[105, 113] == d.id and shore.berth(g, d) == (113, 107)
    g.command("undo")
    assert not any(x.key == "dock" for x in g.buildings.values()) and w.occ[105, 113] == 0
    # an old save's land dock (no orientation) keeps its water exit as the berth
    old = Building(id=10 ** 6, key="dock", x=116, y=100, size=4, kind="trade")
    assert not shore.is_shore(old) and shore.berth(g, old) == walkers.water_exit(g, 116, 100, 4, connected=True)


def test_build_tool_shoos_animals():
    """A build tool over the map shoos sheep / goats / cattle off its footprint (FUN_004059C0 -> FUN_004F9380 every
    frame; oracle sheep-build-r3/-r4: the house-plot ghost over a grazing sheep, action 16 -> 7 and a new spot outside
    the footprint at the next tick; the click while it is still on the tile is refused, later it builds). bugs.md 431."""
    from sim.systems import walkers
    from sim.game import CommandError
    g = Game("sandbox_open", 1)
    g.command("road 140 110 140 116")
    g.command("build sheep_farm 141 112")
    a = walkers.spawn_animal(g, "sheep", 132, 112)
    for _ in range(400):
        g.step()
        if g.tick > 100 and a.state == "idle" and not a.path and a.next_move > g.tick + 30:
            break
    x, y = a.x, a.y
    try:
        g.command(f"build house {x} {y}")
        assert False, "built on a sheep"
    except CommandError as e:
        assert "walker" in str(e)
    assert g.command(f"hover house {x} {y}").startswith("hover house")
    g.step()
    assert a.state == "walk" and a.path and not (x <= a.path[-1][0] < x + 2 and y <= a.path[-1][1] < y + 2)
    for _ in range(80):
        g.step()
    assert not (x <= a.x < x + 2 and y <= a.y < y + 2)
    assert "built house" in g.command(f"build house {x} {y}")
    g.command("hover off")
    assert g.hover is None


def test_bridge():
    """The exe's bridge tool (FUN_0041C450, docs/logic/bridges.md): point at a water tile beside a shore."""
    from sim.game import CommandError
    g = Game("sandbox_open", 1)
    g.city.treasury = 10 ** 6
    tiles, d = g.bridge_site(95, 108)
    assert len(tiles) == 11 and d == (0, -1) and tiles[-1] == (95, 98)
    out = g.command("bridge 95 108")
    assert "11 tiles" in out and "cost 165" in out and g.world.road[98, 95] and g.world.road[108, 95]
    assert "narrow" in g.bridge_site(96, 108)[1]                    # land diagonally beside the span
    for bad in ("bridge 116 143", "bridge 100 100"):                # a pond / land
        try:
            g.command(bad)
            raise AssertionError(bad)
        except CommandError as e:
            assert e.warn == (23,)
    # pieces as the exe's grid (oracle runs/bridge: (78,108) -> 12 11 9 10 9 8 7), whole-span clear, undo
    g.command("bridge 78 108")
    assert [g.bridge_pieces[(78, y)] for y in range(108, 115)] == [12, 11, 9, 10, 9, 8, 7]
    assert [g.bridge_pieces[(95, y)] for y in range(108, 97, -1)] == [7, 8, 9, 10, 9, 10, 9, 10, 9, 11, 12]
    g.bridge_pieces = {}                                            # older saves: derived from the runs
    assert g.bridge_spans()[(78, 108)] == 12 and g.bridge_spans()[(95, 108)] == 7
    g.action_begin(); g.command("clear 78 111"); g.action_end()
    assert not any((78, y) in g.bridges for y in range(108, 115)) and not g.world.road[108, 78]
    g.command("undo")
    assert g.bridge_pieces[(78, 114)] == 7 and g.world.road[114, 78]


def test_placement_rules():
    """map_area_buildable 0x004A0DC0 (docs/logic/buildings.md §5): not within 3 of the map edge, not on a walker
    (script lines exempt); ramps carry roads."""
    from sim.game import CommandError
    from sim.model import Walker
    from sim import script
    g = Game("sandbox_open", 1)
    g.city.treasury = 10 ** 6
    assert g.world.near_play_edge(133, 205) and not g.world.near_play_edge(132, 205)    # x+y edge, margin 3
    for bad in ("build house 115 4", "build house 113 1"):
        try:
            g.command(bad)
            raise AssertionError(bad)
        except CommandError as e:
            assert "map edge" in str(e) and e.warn == (18,)
    g.walkers[999] = Walker(id=999, role="boar", home=0, x=140, y=140)
    try:
        g.command("build doric_column 140 140")
        raise AssertionError("built on a walker")
    except CommandError as e:
        assert "walker" in str(e)
    assert "built" in script.apply(g, "build doric_column 140 140")                    # scripts: exempt
    assert "7 tiles" in g.command("road 131 174 131 180")                             # over the ramp (131,177..178)


def test_map_start_roads():
    """The map's own roads (terrain 0x40) are ordinary roads at the start (bugs.md 233, map-terrain.md 11): the
    sandbox's 119 tiles from the land entry north along x = 167 and east along y = 106 to the exit, one network;
    the clear tool removes them (2 dr a tile). The exe's start clean-up leaves no tree, scrub or meadow on a cliff."""
    import numpy as np
    from sim.world import CLIFF, TREE, SCRUB, MEADOW, OFFMAP
    g = Game("sandbox_open", 1)
    w = g.world
    assert w.road.sum() == 119 and w.road[w.entry[1], w.entry[0]] and w.road[w.exit[1], w.exit[0]]
    assert set(np.unique(w.road_net[w.road])) == {1}
    f = w.flags[(w.flags & OFFMAP) == 0]
    assert not ((f & CLIFF > 0) & (f & (TREE | SCRUB | MEADOW) > 0)).any()
    t = g.city.treasury
    g.command("clear 167 120 167 121")
    assert not w.road[120, 167] and g.city.treasury == t - 4 and len(np.unique(w.road_net[w.road])) == 2
    g.command("road 167 120 167 121")
    assert w.road[120, 167] and set(np.unique(w.road_net[w.road])) == {1}


def test_scenario_points_raw():
    """Scenario points are logical in the map (as in the exe); World keeps them raw = logical + origin (1, 1 on the
    sandbox; map-terrain.md "Logical and raw coordinates"). The herds spawn on the exe's tiles: oracle
    open-play-events tick 0, figures 51 / 59 + (1, 1). A world pickled with logical points is migrated on load."""
    import collections, tempfile
    g = Game("sandbox_open", 1)
    w = g.world
    assert (w.origin, w.size, w.entry, w.exit, w.sea_entry, w.sea_exit) == \
        ((1, 1), (226, 226), (167, 170), (217, 106), (34, 83), (35, 81))
    assert w.points["land_invasion"][:4] == [(149, 191), (167, 173), (218, 106), (95, 20)]
    assert w.points["landing"][0] == (105, 102) and w.monster_points[2] == (122, 201)
    assert w.fishing_spots[1] == (71, 102) and w.boar_points[0] == (106, 19) and w.wolf_points[0] == (116, 15)
    g.step(g.rules["ticks_per_day"])
    exe = {("boar", (106, 19)): [(104, 19), (104, 20), (105, 20), (105, 21), (105, 18), (104, 21), (105, 21)],
           ("wolf", (116, 15)): [(116, 15), (116, 14), (117, 15), (116, 16), (115, 15), (117, 14), (117, 16)]}
    for (role, p), tiles in exe.items():
        mine = [(a.x, a.y) for a in g.walkers.values() if a.role == role and a.origin == p]
        assert collections.Counter(mine) == collections.Counter(tiles), (role, mine)
    # an old world: points logical, herd timers / packs / animal origins keyed by them
    o = w.origin
    back = lambda p: (p[0] - o[0], p[1] - o[1])
    for k in ("boar_points", "wolf_points", "fishing_spots", "urchin_spots"):
        setattr(w, k, [back(p) for p in getattr(w, k)])
    w.entry, w.exit, w.sea_entry, w.sea_exit = (back(p) for p in (w.entry, w.exit, w.sea_entry, w.sea_exit))
    for k in ("points", "points_v", "size", "origin", "monster_points"):
        delattr(w, k)
    g._fishing_points, g._prey_points = list(w.fishing_spots), list(w.boar_points)
    g.herd_timers = {back(p): v for p, v in g.herd_timers.items()}
    g.mil["packs"] = {back(p): v for p, v in g.mil["packs"].items()}
    for a in g.walkers.values():
        if a.role in ("boar", "wolf"):
            a.origin = back(a.origin)
    with tempfile.TemporaryDirectory() as d:
        g.save(os.path.join(d, "old.pkl"))
        h = Game.load(os.path.join(d, "old.pkl"))
    assert h.world.entry == (167, 170) and h.world.points_v == 1 and h.world.size == (226, 226)
    assert h._prey_points == h.world.boar_points and h._fishing_points == h.world.fishing_spots
    assert set(h.herd_timers) == set(h.world.boar_points) and set(h.mil["packs"]) == set(h.world.wolf_points)
    assert {a.origin for a in h.walkers.values() if a.role in ("boar", "wolf")} == \
        set(h.world.boar_points) | set(h.world.wolf_points)


def test_rubble_ruin_type():
    """g_grid_ruin_type: a collapsed building's tiles remember its type for the rubble window (0x0057DA10,
    28:type; land kind 8, /land.json `ruin`), and a burning ruin keeps the type of the building that burned."""
    from sim.systems import risk
    from sim.live import land_kind
    g = Game("sandbox_open", 1)
    g.city.treasury = 10 ** 6
    g.command("road 60 71 80 71")
    g.command("build granary 70 67")
    b = next(b for b in g.buildings.values() if b.key == "granary")
    risk.collapse(g, b)
    assert land_kind(g, 70, 67) == 8 and g.ruin_type[(73, 70)] == "granary"
    risk.mark_ruin(g, 73, 70, "ruin")
    assert g.ruin_type[(73, 70)] == "granary"


def test_wall_grid_per_view():
    """grid_walls 0x00587E50 per view: a wall tile is walkable when its three neighbours toward the view's back
    corner are walls; on a turn (`view N`) a sentry on a closed tile goes to the first open one around it
    (0x004CFEE0, docs/play/rotation.md "The view in the sim")."""
    from sim.military import defences, units
    g = Game("sandbox_open", 1)
    for y in range(100, 103):
        for x in range(100, 103):
            g.world.flags[y, x] |= 0x4000
    ok0, _ = defences.wall_grid(g)
    assert ok0 == {(100, 100), (101, 100), (100, 101), (101, 101)}
    w = units.spawn(g, "wall_sentry", 100, 100, task="post", path=[], timer_end=g.tick + 41)
    assert g.command("view 4") == "view 4"
    assert defences.wall_grid(g)[0] == {(101, 101), (102, 101), (101, 102), (102, 102)}
    assert (w.x, w.y) == (101, 101) and w.task == "back"
    g.command("view 0")
    assert (w.x, w.y) == (101, 101) and g.view == 0


def test_cooled_lava_blocks():
    """Cooled lava (terrain 0x1000000, set for good by lava_node_burn 0x00506D80) refuses buildings
    (map_area_buildable 0x3DFFD66F), roads (drag ends 0x5361227, scripts' road), walls (0x1537166F) and people (route
    grid 0x005876F0: & 0x2DFFD66F blocked); wild animals' 0x103AD02A leaves it open (bug 448)."""
    from sim.systems import walkers
    from sim.game import CommandError
    g = Game("sandbox_open", 1)
    g.city.treasury = 100000
    n = g.world.flags.shape[0]
    x, y = 100, 60
    g.world.flags[y, x] |= 0x1000010
    g.map_version = getattr(g, "map_version", 0) + 1
    for cmd in (f"build house {x} {y}", f"build gardens {x} {y}", f"road {x - 1} {y} {x + 1} {y}", f"wall {x} {y} {x} {y}"):
        try:
            g.command(cmd)
            assert False, cmd
        except CommandError as e:
            assert "lava" in str(e), (cmd, str(e))
    assert not g.road_drag(x, y, x + 2, y)["ok"]                  # an end on lava: refused
    r = g.road_drag(x - 1, y, x + 1, y)                            # across: around it (route grid: blocked)
    assert [x, y] not in [list(t[:2]) for t in r.get("tiles", [])]
    assert not walkers.walkable(g)[y * n + x] and walkers.wild_walkable(g)[y * n + x]
    assert "built" in g.command(f"build house {x + 2} {y}")


def test_roadblock_not_on_agora():
    """Roadblock tool 0x7B: road (0x40) without 0x8 (an agora's strip is the agora's), bridge piece or ramp (bugs.md 381)."""
    from sim.game import CommandError
    g = Game("sandbox_open", 1)
    g.city.treasury = 10 ** 6
    e = g.world.entry
    for c in (f"road {e[0]} {e[1] - 40} {e[0]} {e[1]}", f"build agora {e[0]} {e[1] - 18} right"):
        g.command(c)
    a = next(x for x in g.buildings.values() if x.kind == "agora")
    tx, ty = a.misc["strip"][0]
    assert not g.roadblock_ok(tx, ty)
    try:
        g.command(f"build roadblock {tx} {ty}")
        raise AssertionError("roadblock on an agora strip")
    except CommandError:
        pass
    g.command(f"build roadblock {e[0]} {e[1] - 2}")
    assert (e[0], e[1] - 2) in g.roadblocks


def test_quarry_pit_blocks_land_routes():
    """Route grid 0x005876F0: a marble tile whose regrowth byte is not 0xFF (a quarry pit) is bit 0x80, outside
    the land masks (0x11D ...): land walkers and monsters route around it; stonecutters (mask 0x19C, route mode
    0xB, the marble search route_search_area 0x0058A4D0) cross it."""
    from sim.systems import walkers
    from sim.heroes import monsters
    g = Game("sandbox_open", 1)
    w = g.world
    n = 228
    ys, xs = (w.flags & 0x20000).nonzero()
    x, y = int(xs[len(xs) // 2]), int(ys[len(ys) // 2])
    i = y * n + x
    assert walkers.walkable(g)[i] and monsters.passable(g)[i]
    walkers.quarry_dig(g, x, y)
    assert g.quarry[(x, y)] == 100
    assert not walkers.walkable(g)[i] and not monsters.passable(g)[i] and walkers.quarry_walkable(g)[i]
    t = walkers.land_tree(g, (x - 1, y), 3, quarry=True)
    assert t[i][1] == y * n + x - 1


def test_route_search_port():
    """sim/military/routes.Search (route_search 0x00502EE0 with buckets) pops in the decompile's order: on random
    weighted grids the distance field at the goal's pop and the trace equal the literal scan's, also when the search
    is resumed for later goals from the same start; oracle routes in tools/oracle_route2.py."""
    import random
    from sim.military import routes
    N = 228
    rng = random.Random(7)
    for trial in range(6):
        gm = [-1] * (N * N)
        for y in range(60, 100):
            for x in range(60, 100):
                gm[y * N + x] = rng.choice((0, 0, 0, 0, 1, 2, 3, 4, 5, -1, -2))
        st = None
        s = 80 * N + 80
        gm[s] = 0
        for k in range(8):
            e = rng.randrange(62, 98) * N + rng.randrange(62, 98)
            ok, dist = _route_search_literal(gm, s, e)
            st = st or routes.Search(gm, s)
            assert st.run(e) == ok, (trial, k)
            if ok:
                a = routes.trace8(dist, (s % N, s // N), (e % N, e // N))
                b = routes.trace8(st.dist, (s % N, s // N), (e % N, e // N))
                assert a == b, (trial, k)
                assert all(st.dist[i] == dist[i] for i in range(N * N) if dist[i] and st.dist[i] <= dist[e])


def test_road_drag_as_exe():
    """roads_drag_place 0x0049ACB0 (sim/roaddrag.py, oracle tools/oracle_roads.py 1R-roads): ends refuse rubble but
    not beach, the middle crosses both; a garden (0x20) stops the trace and the part from the end stays (charged);
    399 tiles at most (the 400th never set); the play edge band; herd points in the drag's rectangle; across an
    avenue's side strip; not through a gatehouse."""
    import numpy as np
    from sim import roaddrag as R
    from sim.game import CommandError
    N = R.N
    T = np.full((N, N), 0x2, np.uint32)                     # rock everywhere, lanes carved below
    edge = np.zeros((N, N), bool)
    T[10, 10:21] = 0
    T[10, 12], T[10, 14] = 0x1000, 0x10000                  # rubble and beach in the middle
    G = R.Grids(T, np.zeros((N, N), int), edge)
    r = R.drag(G, 10, 10, 20, 10)
    assert r["ok"] and r["new"] == 11 and r["tiles"][0] == (20, 10) and r["tiles"][-1] == (10, 10)
    T[10, 20] = 0x1000                                      # rubble end: refused, nothing set
    assert R.drag(R.Grids(T, np.zeros((N, N), int), edge), 10, 10, 20, 10)["refused"]
    T[10, 20] = 0x10000                                     # beach end: fine
    assert R.drag(R.Grids(T, np.zeros((N, N), int), edge), 10, 10, 20, 10)["ok"]
    T[10, 15] = 0x20                                        # garden: crossed by the flood, the trace stops there
    r = R.drag(R.Grids(T, np.zeros((N, N), int), edge), 10, 10, 20, 10)
    assert not r["ok"] and r["tiles"] == [(20, 10), (19, 10), (18, 10), (17, 10), (16, 10)]
    edge[10, 17] = True                                     # the play edge band blocks the flood
    assert not R.drag(R.Grids(T, np.zeros((N, N), int), edge), 10, 10, 20, 10)["tiles"]
    for L, ok in ((399, True), (400, False)):               # a lane of L tiles: 399 at most
        T2 = np.full((N, N), 0x2, np.uint32)
        T2[20, 5:5 + 200], T2[22, 5:5 + 200], T2[21, 5 + 199] = 0, 0, 0
        x2 = 5 + (401 - L)                                  # 2 * 200 + 1 = 401 tiles from (5, 20) to (5, 22)
        r = R.drag(R.Grids(T2, np.zeros((N, N), int), np.zeros((N, N), bool)), 5, 20, x2, 22)
        assert r["ok"] == ok and len(r["tiles"]) == min(L, 399), (L, r["ok"], len(r["tiles"]))
    g = Game("sandbox_open", 1)                             # the glue: our state as the exe's grids
    g.command("road 150 140 165 140")
    g.command("avenue 151 140 163 140")                     # strip north of the road (row 139)
    out = g.command("path 157 136 157 143")                 # across the strip: the strip becomes road
    w = g.world
    assert w.road[136:144, 157].all() and w.avenue[139, 157], out
    g.command("build gardens 170 130")
    out = g.command("path 166 130 174 130")                 # the garden stops it: road from the end to it
    assert w.road[130, 171:175].all() and not w.road[130, 168:171].any(), out   # (167, 130): the map's road
    try:                                                    # wolf point (raw 49, 157) inside the rectangle
        g.command("path 45 157 53 157")
        assert False
    except CommandError as e:
        assert e.warn == (0x16,)


def test_gardens_open_land():
    """Garden terrain 0x20 is open land in the route grid (0x005876F0: |= 0x10 before the building bit) and 0 in
    grid_military (0x00502BA0): soldiers and walkers cross gardens (oracle 1L5-troopsmarch; bugs.md 369)."""
    from sim.systems import walkers
    from sim.military import routes
    g = Game("sandbox_open", 1)
    g.command("build gardens 170 130")
    n = g.world.flags.shape[0]
    assert g.world.occ[130, 170] and walkers.walkable(g)[130 * n + 170]
    assert routes.grid(g)[130 * n + 170] == 0


def test_road_tool_preview():
    """bugs.md 464 (oracle slope-road): the road cursor (FUN_00452B80) is red on a ramp, a road and near the play edge,
    else green with SPR_ROADS (+1 for a road E / W only); a drag's preview tests it on the terrain with the route
    (a placed end is red) and gives the route's ramp tiles their road pictures (sim/terrain_view.py ramp_preview)."""
    import numpy as np
    from sim import roaddrag as R
    from sim.live import footprint
    from sim.terrain_view import TerrainView
    N = R.N
    T = np.zeros((N, N), np.uint32)
    edge = np.zeros((N, N), bool)
    T[50, 51], T[60, 60] = 0x40, 0x600
    edge[5, 5] = True
    G = R.Grids(T, np.zeros((N, N), int), edge)
    assert R.cursor(G, 50, 50) == (True, ("SPR_ROADS", 1))      # road E only
    assert R.cursor(G, 50, 49) == (True, ("SPR_ROADS", 0))
    assert R.cursor(G, 50, 50, piece=0x80) == (True, ("SPR_PAVED_ROADS", 1))
    assert R.cursor(G, 51, 50)[0] is False and R.cursor(G, 60, 60)[0] is False and R.cursor(G, 5, 5)[0] is False
    g = Game("sandbox", 1)                                  # the map's long ramp at (131, 177..178), elevation 0 -> 1
    tv = TerrainView(g)
    assert footprint(g, "road", 131, 175, tv=tv)["cursor"][2] is True
    assert footprint(g, "road", 131, 177, tv=tv)["cursor"][2] is False
    r = footprint(g, "road", 131, 175, None, 131, 180, tv=tv, view=0)
    assert r["ok"] and [t[:2] for t in r["tiles"]] == [[131, y] for y in range(175, 181)] and r["cursor"][2] is False
    ramps = {i: (pid, d) for i, pid, d in r["ramps"]}
    assert set(ramps) == {177 * N + 131, 178 * N + 131}
    g.command("path 131 175 131 180")                       # built: the same pictures
    tv.update(g)
    assert all(int(tv.ids[i // N, i % N]) == pid for i, (pid, d) in ramps.items())
    r2 = footprint(g, "road", 131, 175, None, 131, 180, tv=tv, view=2)
    assert not r2.get("ramps")                               # roads there already: nothing to change


if __name__ == "__main__":
    import test_sim
    test_sim.main([__file__])
