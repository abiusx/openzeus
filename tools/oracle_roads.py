"""Road drags in the original exe against ours (sim/roaddrag.py; docs/logic/map-terrain.md "Road drag").

    python3 tools/oracle_roads.py --scenario re/oracle/scenarios/1R-roads    # writes .txt (script) and .poke
    python3 tools/oracle_roads.py --calibrate DIR      # .ticks.json from a run's marker shots (then --scenario again)
    python3 tools/oracle_roads.py --run DIR [--no-dumps]  # zeus-run on the scenario (dumps every 2 ticks, log)
    python3 tools/oracle_roads.py DIR [--show N]     # compares every drag of the run with ours

Reproduce (11-02): --scenario, then (--run TMP --no-dumps, --calibrate TMP, --scenario) until the scene end ticks stop
moving (3 rounds; the camera windows change the emulated work, so the timeline), then --run re/oracle/runs/1R-roads,
the check (152/152), tools/oracle_compress.py 1R-roads and --shots 1R-roads.

Open Play Sandbox (sandbox-start.txt, 800x600), the Elis tribute message closed, the road tool picked (664,453).
Then scene after scene: the camera (0x00DA2F64 / 0x00DA2F68) and a test layout are poked in (terrain 0x00CCE128,
elevation and projected elevation 0, piece 0), and ~9 s later (a route grid rebuild, one day) the drags: mouse down on
the start tile, move to the end, shot (DIR/sh/dNNN.bmp: the ghost; its tick dates the drag), up. Houses and a
roadblock are placed with the exe's own tools in their scenes.

The comparison takes for each drag the last dump before it (pre), one while the mouse is down (mid: the preview's
road bits are in the terrain grid, roads_drag_place(1) leaves them until the next call), and one after the release
(post). Ours: sim/roaddrag.drag on the pre dump's grids (terrain, building types from g_grid_building /
g_buildings +0x10, the play edge); its tiles must equal the exe's new road bits of mid and post, the charge the
treasury change. The commit-only refusals (build_commit 0x00498910: herd points in the drag's rectangle
map_area_has_marker 0x00496B50) charge nothing but keep the preview's road (no restore of the terrain).
"""
import os
import re
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
import oracle  # noqa: E402
from sim import roaddrag  # noqa: E402

N = 228
TERRAIN, ELEV, PELEV, PIECE = 0x00CCE128, 0x008E01FA, 0x008ECD0A, 0x00D00D68
GRID_BUILDING, BUILDINGS, BSIZE = 0x00D26E98, 0x0092E658, 0x118
TREASURY = 0x00FE6A64
CAM_COL, CAM_ROW = 0x00DA2F64, 0x00DA2F68
START = ("5:key 27; 12:click 220,101; 17:char 78; 20:click 556,320; 27:click 590,256; 31:click 120,306; "
         "33:click 315,442; 38:click 656,491; 46:rclick 300,300; 53:rclick 300,300")
ROAD_TOOL, HOUSE_TOOL, ROADBLOCK_TOOL = (664, 453), (676, 345), (698, 453)

KINDS = [("tree", 0x1), ("rock", 0x2), ("water", 0x4), ("garden", 0x20), ("road", 0x40),
         ("scrub", 0x80), ("flood", 0x100), ("cliff", 0x200), ("ramp", 0x600), ("meadow", 0x800),
         ("rubble", 0x1000), ("wall", 0x4000), ("b8000", 0x8000), ("beach", 0x10000), ("marble", 0x20000),
         ("reeds", 0x40000), ("orichalc", 0x300000), ("b400000", 0x400000), ("b800000", 0x800000),
         ("fault", 0x2000000), ("deep", 0x4000004), ("b8000000", 0x8000000),
         ("sacred", 0x10000000), ("b20000000", 0x20000000), ("beachwater", 0x10004), ("bridge", 0x44),
         ("ramproad", 0x640), ("rubbleroad", 0x1040), ("beachroad", 0x10040), ("copper", 0x100002)]


class Scene:
    """A camera centre (cx, cy; cx + cy even), terrain pokes {(x, y): T} (each also gets elevation, projected
    elevation and piece 0), drags [(x1, y1, x2, y2)], and UI clicks before the drags [(tool, [(x, y), ...])]."""
    def __init__(self, name, cx, cy):
        self.name, self.cx, self.cy = name, cx, cy
        self.tiles, self.drags, self.clicks = {}, [], []

    def fill(self, x0, y0, x1, y1, t):
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                self.tiles[(x, y)] = t

    def cam(self):
        col = round(((self.cx - self.cy) * 30 + 29 + 6870 - 300) / 60)
        return col, self.cx + self.cy - 18

    def screen(self, x, y):
        col, row = self.cam()
        return (x - y) * 30 + 29 - (60 * col - 6870), (x + y) * 15 + 15 - (15 * row - 30)

    def visible(self, x, y):
        sx, sy = self.screen(x, y)
        return 8 <= sx <= 590 and 40 <= sy <= 585


def kind_scenes():
    """Every terrain kind in 1-wide corridors walled by rock: in the middle, at the end, at the start."""
    tests = [(k, t, where) for k, t in KINDS for where in ("mid", "end", "start")]
    out = []
    for s in range(0, len(tests), 9):
        cx, cy = 66 + 9 * (s // 9 % 6), 135 + 22 * (s // 54)
        cy += (cx + cy) & 1
        sc = Scene(f"kinds{s // 9}", cx, cy)
        sc.fill(cx - 3, cy - 9, cx + 3, cy + 9, 0x2)
        for j, (k, t, where) in enumerate(tests[s:s + 9]):
            y = cy - 8 + 2 * j
            sc.fill(cx - 1, y, cx + 1, y, 0)
            sc.tiles[(cx if where == "mid" else cx + 1 if where == "end" else cx - 1, y)] = t
            sc.drags.append((cx - 1, y, cx + 1, y))
        out.append(sc)
    return out


def field(name, cx, cy, r=11):
    sc = Scene(name, cx, cy)
    sc.fill(cx - r, cy - r, cx + r, cy + r, 0)
    return sc


def scenes():
    out = kind_scenes()
    # tie-breaks: an open field with rock blocks, drags in every direction
    sc = field("ties", 160, 130)
    cx, cy = sc.cx, sc.cy
    for x, y, w, h in ((-3, -3, 2, 3), (2, -1, 3, 1), (-1, 3, 4, 2), (3, 4, 1, 3), (-6, 1, 2, 2), (5, -5, 1, 4)):
        sc.fill(cx + x, cy + y, cx + x + w - 1, cy + y + h - 1, 0x2)
    rng = np.random.default_rng(7)
    pts = [(x, y) for x in range(cx - 9, cx + 10) for y in range(cy - 9, cy + 10)
           if sc.visible(x, y) and sc.tiles.get((x, y)) == 0]
    for _ in range(22):
        a, b = rng.choice(len(pts), 2, replace=False)
        sc.drags.append(pts[a] + pts[b])
    for d in ((cx - 5, cy, cx + 6, cy), (cx, cy - 6, cx, cy + 7), (cx - 6, cy - 6, cx + 5, cy + 5),
              (cx + 5, cy - 6, cx - 6, cy + 5), (cx - 7, cy + 1, cx + 7, cy - 1), (cx + 4, cy - 4, cx - 5, cy + 3),
              (cx - 4, cy + 4, cx + 3, cy - 5)):
        if sc.visible(*d[:2]) and sc.visible(*d[2:]):
            sc.drags.append(d)
    out.append(sc)
    # gardens (0x20): the flood crosses them, the trace stops there (partial road from the end)
    sc = field("gardens", 150, 166, 8)
    cx, cy = sc.cx, sc.cy
    sc.tiles[(cx, cy - 4)] = 0x20
    sc.drags.append((cx - 5, cy - 4, cx + 5, cy - 4))
    sc.fill(cx - 1, cy, cx + 1, cy + 2, 0x20)
    sc.drags.append((cx - 5, cy + 1, cx + 5, cy + 1))
    sc.drags.append((cx + 1, cy + 5, cx - 6, cy - 1))
    sc.tiles[(cx + 4, cy + 4)] = 0x20
    sc.drags.append((cx + 4, cy + 7, cx + 4, cy - 2))
    out.append(sc)
    # existing roads: crossing, reusing, ending on one
    sc = field("roads", 130, 150)
    cx, cy = sc.cx, sc.cy
    sc.fill(cx - 8, cy, cx + 8, cy, 0x40)
    sc.fill(cx + 2, cy - 7, cx + 2, cy + 7, 0x40)
    sc.drags += [(cx - 3, cy - 5, cx - 3, cy + 5), (cx - 6, cy - 3, cx + 6, cy + 3), (cx - 1, cy - 4, cx + 2, cy),
                 (cx + 2, cy - 7, cx + 2, cy + 7), (cx + 5, cy + 5, cx - 5, cy)]
    out.append(sc)
    # houses (the exe's own tool) and a roadblock on a poked road
    sc = field("buildings", 100, 180)
    cx, cy = sc.cx, sc.cy
    sc.fill(cx - 8, cy + 4, cx + 8, cy + 4, 0x40)
    sc.clicks = [(HOUSE_TOOL, [(cx - 1, cy - 1), (cx + 3, cy - 3)]), (ROADBLOCK_TOOL, [(cx, cy + 4)])]
    sc.drags += [(cx - 4, cy - 1, cx + 5, cy - 1), (cx - 1, cy - 5, cx - 1, cy + 3), (cx - 5, cy + 4, cx + 5, cy + 4),
                 (cx - 2, cy + 6, cx, cy + 4), (cx - 3, cy - 3, cx - 1, cy - 1), (cx - 1, cy - 1, cx - 4, cy - 4),
                 (cx, cy + 4, cx + 4, cy + 7)]
    out.append(sc)
    # herd points (map_area_has_marker): wolf raw (49, 157)
    sc = field("herd", 50, 158, 8)
    cx, cy = sc.cx, sc.cy
    sc.drags += [(45, 157, 53, 157), (45, 155, 53, 155), (46, 160, 49, 162), (52, 152, 49, 157), (48, 154, 50, 160)]
    out.append(sc)
    # the play edge (map_near_play_edge 3): the north tip (raw (113, 1)); tiles off the play area untouched
    sc = Scene("edge", 112, 8)
    for x in range(102, 125):
        for y in range(1, 28):
            sc.tiles[(x, y)] = 0
    sc.drags += [(113, 14, 113, 4), (113, 14, 113, 5), (113, 14, 113, 6), (108, 9, 118, 9), (107, 10, 119, 10),
                 (110, 6, 116, 6), (110, 6, 110, 12), (111, 5, 111, 14)]
    out.append(sc)
    out.append(sc)
    return out


def field(name, cx, cy, r=11):
    sc = Scene(name, cx, cy)
    sc.fill(cx - r, cy - r, cx + r, cy + r, 0)
    return sc


def scenes():
    out = kind_scenes()
    # tie-breaks: an open field with rock blocks, drags in every direction
    sc = field("ties", 160, 130)
    cx, cy = sc.cx, sc.cy
    for x, y, w, h in ((-3, -3, 2, 3), (2, -1, 3, 1), (-1, 3, 4, 2), (3, 4, 1, 3), (-6, 1, 2, 2), (5, -5, 1, 4)):
        sc.fill(cx + x, cy + y, cx + x + w - 1, cy + y + h - 1, 0x2)
    rng = np.random.default_rng(7)
    pts = [(x, y) for x in range(cx - 9, cx + 10) for y in range(cy - 9, cy + 10)
           if sc.visible(x, y) and sc.tiles.get((x, y)) == 0]
    for _ in range(22):
        a, b = rng.choice(len(pts), 2, replace=False)
        sc.drags.append(pts[a] + pts[b])
    for d in ((cx - 5, cy, cx + 6, cy), (cx, cy - 6, cx, cy + 7), (cx - 6, cy - 6, cx + 5, cy + 5),
              (cx + 5, cy - 6, cx - 6, cy + 5), (cx - 7, cy + 1, cx + 7, cy - 1), (cx + 4, cy - 4, cx - 5, cy + 3),
              (cx - 4, cy + 4, cx + 3, cy - 5)):
        if sc.visible(*d[:2]) and sc.visible(*d[2:]):
            sc.drags.append(d)
    out.append(sc)
    # gardens (0x20): the flood crosses them, the trace stops there (partial road from the end)
    sc = field("gardens", 150, 166, 8)
    cx, cy = sc.cx, sc.cy
    sc.tiles[(cx, cy - 4)] = 0x20
    sc.drags.append((cx - 5, cy - 4, cx + 5, cy - 4))
    sc.fill(cx - 1, cy, cx + 1, cy + 2, 0x20)
    sc.drags.append((cx - 5, cy + 1, cx + 5, cy + 1))
    sc.drags.append((cx + 1, cy + 5, cx - 6, cy - 1))
    sc.tiles[(cx + 4, cy + 4)] = 0x20
    sc.drags.append((cx + 4, cy + 7, cx + 4, cy - 2))
    out.append(sc)
    # existing roads: crossing, reusing, ending on one
    sc = field("roads", 130, 150)
    cx, cy = sc.cx, sc.cy
    sc.fill(cx - 8, cy, cx + 8, cy, 0x40)
    sc.fill(cx + 2, cy - 7, cx + 2, cy + 7, 0x40)
    sc.drags += [(cx - 3, cy - 5, cx - 3, cy + 5), (cx - 6, cy - 3, cx + 6, cy + 3), (cx - 1, cy - 4, cx + 2, cy),
                 (cx + 2, cy - 7, cx + 2, cy + 7), (cx + 5, cy + 5, cx - 5, cy)]
    out.append(sc)
    # houses (the exe's own tool) and a roadblock on a poked road
    sc = field("buildings", 100, 180)
    cx, cy = sc.cx, sc.cy
    sc.fill(cx - 8, cy + 4, cx + 8, cy + 4, 0x40)
    sc.clicks = [(HOUSE_TOOL, [(cx - 1, cy - 1), (cx + 3, cy - 3)]), (ROADBLOCK_TOOL, [(cx, cy + 4)])]
    sc.drags += [(cx - 4, cy - 1, cx + 5, cy - 1), (cx - 1, cy - 5, cx - 1, cy + 3), (cx - 5, cy + 4, cx + 5, cy + 4),
                 (cx - 2, cy + 6, cx, cy + 4), (cx - 3, cy - 3, cx - 1, cy - 1), (cx - 1, cy - 1, cx - 4, cy - 4),
                 (cx, cy + 4, cx + 4, cy + 7)]
    out.append(sc)
    # herd points (map_area_has_marker): wolf raw (49, 157)
    sc = field("herd", 50, 158, 8)
    cx, cy = sc.cx, sc.cy
    sc.drags += [(45, 157, 53, 157), (45, 155, 53, 155), (46, 160, 49, 162), (52, 152, 49, 157), (48, 154, 50, 160)]
    out.append(sc)
    # the play edge (map_near_play_edge 3): the north tip (raw (113, 1)); tiles off the play area untouched
    sc = Scene("edge", 112, 8)
    for x in range(102, 125):
        for y in range(1, 28):
            sc.tiles[(x, y)] = 0
    sc.drags += [(113, 14, 113, 4), (113, 14, 113, 5), (113, 14, 113, 6), (108, 9, 118, 9), (107, 10, 119, 10),
                 (110, 6, 116, 6), (110, 6, 110, 12), (111, 5, 111, 14)]
    out.append(sc)
    # long routes: serpentines of 398 / 399 and 400 / 401 tiles (LIMIT), on rows 114..122: the rows above cross the
    # map's central beach, whose tile objects (0x00666930, made at map load on and beside beach) stay under a poked
    # lane and steer the exe's route grid there (1R-roads 11-02: a lane over them got no route)
    sc = Scene("long", 16, 116)
    x0 = 14
    sc.fill(x0 - 1, 114, 216, 122, 0x2)
    sc.drags.append((x0, 114, x0 + 1, 114))                 # a press on rock first (refused by both)
    for j, (L, ends) in enumerate(((198, (1, 0)), (199, (1, 0)))):
        r0 = 114 + 4 * j
        sc.fill(x0, r0 + 1, x0 + L, r0 + 1, 0)
        sc.fill(x0, r0 + 3, x0 + L, r0 + 3, 0)
        sc.tiles[(x0 + L, r0 + 2)] = 0
        for e in ends:                                      # 2L+2 then 2L+3 tiles (the second over the first's road)
            sc.drags.append((x0, r0 + 1, x0 + e, r0 + 3))
    out.append(sc)
    return out


def build(base):
    """Write BASE.txt (script, DIR = the run dir) and BASE.poke. Every layout is poked once at tick 2 (the scenes do
    not overlap; the route grid takes them at the month change, tick 816: drags start after it); the camera is poked at every tick of its scene's window, from the previous scene's end marker
    shot (DIR/sh/eNN.bmp) to its own, as BASE.ticks.json gives them (`--calibrate RUN`: the ticks of a run of this
    script; the tick rate depends on the emulated work, ~4 to 8.5 per second, so the windows come from a run)."""
    import json
    pokes, script = [], [START, f"55:click {ROAD_TOOL[0]},{ROAD_TOOL[1]}"]
    t = 140.0                       # after the month change at tick 816: the whole route grid is rebuilt then
    n = 0
    manifest = []
    from sim.world import World, OFFMAP
    off = (World("sandbox").flags & OFFMAP) != 0          # the play area's outside stays as it is
    cal = json.load(open(base + ".ticks.json")) if os.path.exists(base + ".ticks.json") else None
    prev = 106
    # no scenario events (g_events_count 0x009173F0 = 0); the drags end before June (the Olympian Games message pauses)
    pokes.append("2 9173f0 4 0")
    for k, sc in enumerate(scenes()):
        sc.tiles = {kk: v for kk, v in sc.tiles.items() if not off[kk[1], kk[0]]}
        pokes.append(f"# scene {k} {sc.name}")
        for (x, y), v in sorted(sc.tiles.items()):
            i = y * N + x
            pokes += [f"2 {TERRAIN + 4 * i:x} 4 {v}", f"2 {ELEV + i:x} 1 0", f"2 {PELEV + i:x} 1 0",
                      f"2 {PIECE + i:x} 1 0"]
        script.append(f"{t:.1f}:shot DIR/sh/s{k:02d}.bmp")
        t0 = t
        t += 4.0                                           # layouts are in since tick 2: only the camera moves
        for tool, pts in sc.clicks:
            script.append(f"{t:.1f}:click {tool[0]},{tool[1]}")
            t += 1.0
            for x, y in pts:
                assert sc.visible(x, y), (sc.name, x, y)
                sx, sy = sc.screen(x, y)
                script.append(f"{t:.1f}:move {sx},{sy}; {t + 0.5:.1f}:click {sx},{sy}")
                t += 1.5
            script.append(f"{t:.1f}:rclick 300,300; {t + 0.8:.1f}:click {ROAD_TOOL[0]},{ROAD_TOOL[1]}")
            t += 2.0
        for x1, y1, x2, y2 in sc.drags:
            assert sc.visible(x1, y1) and sc.visible(x2, y2), (sc.name, x1, y1, x2, y2)
            a, b = sc.screen(x1, y1), sc.screen(x2, y2)
            script.append(f"{t:.1f}:down {a[0]},{a[1]}; {t + 1.2:.1f}:move {b[0]},{b[1]}; "
                          f"{t + 2.0:.1f}:shot DIR/sh/d{n:03d}.bmp; {t + 2.4:.1f}:up {b[0]},{b[1]}")
            manifest.append(f"# d{n:03d} {sc.name} {x1} {y1} {x2} {y2}")
            n += 1
            t += 4.0
        script.append(f"{t:.1f}:shot DIR/sh/e{k:02d}.bmp")
        end = cal["e"][k] if cal else int(prev + (t - t0) * 4.2)
        col, row = sc.cam()
        pokes.append(f"# camera of scene {k}: ticks {prev}..{end}")
        for tk in range(prev, end + 1):
            pokes += [f"{tk} {CAM_COL:x} 4 {col}", f"{tk} {CAM_ROW:x} 4 {row}"]
        prev = end + 1
        t += 1.0
    head = [f"# Road drags (tools/oracle_roads.py): {n} drags, generated; DIR = the run dir; --seconds {int(t) + 3}",
            "# Run: python3 tools/oracle_roads.py --run DIR; check: python3 tools/oracle_roads.py DIR"] + manifest
    open(base + ".txt", "w").write("\n".join(head) + "\n" + "; ".join(script) + "\n")
    open(base + ".poke", "w").write("\n".join(pokes) + "\n")
    print(f"{n} drags, {len(pokes)} poke lines, {int(t) + 3} s{'' if cal else ' (no BASE.ticks.json: estimated)'}")


def calibrate(d, base):
    """BASE.ticks.json from run d's log: the tick of every scene's end marker shot."""
    import json
    e = {}
    for line in open(os.path.join(d, "log.txt"), errors="replace"):
        m = re.search(r"shot \S*/e(\d\d)\.bmp ticks (\d+)", line)
        if m:
            e[int(m.group(1))] = int(m.group(2))
    json.dump(dict(e=[e[k] for k in sorted(e)]), open(base + ".ticks.json", "w"))
    print("scene end ticks", [e[k] for k in sorted(e)])


def run(d, base=os.path.join(ROOT, "re", "oracle", "scenarios", "1R-roads"), dumps=True, end_only=False):
    lines = open(base + ".txt").read().splitlines()
    secs = int(re.search(r"--seconds (\d+)", lines[0]).group(1))
    script = lines[-1].replace("DIR", d)
    os.makedirs(os.path.join(d, "sh"), exist_ok=True)
    os.makedirs(os.path.join(d, "dump"), exist_ok=True)
    os.makedirs(os.path.join(d, "write"), exist_ok=True)
    # every 2 ticks: terrain 17, building grid 16, city 4 (treasury), scenario 9 (points, size), grid base -1,
    # camera 44 (ZEUS_STATE_DUMP_ZONES, re/oracle/zeus-run-state-dump.patch); then the same run again (deterministic)
    # for one full dump at the end (dump_end/: building records 35, for the building types)
    exe = [os.path.join(ROOT, "refs", "zeus-poseidon-arm64", "build", "zeus-run"), "--run",
           os.path.join(ROOT, "zeus-original", "app", "Zeus.exe"), "--headless", "--deterministic",
           "--write-dir", os.path.join(d, "write"), "--seconds", str(secs), "--state-log", "/dev/null",
           "--script", script]
    env = dict(os.environ, ZEUS_STATE_DUMP=os.path.join(d, "dump"), ZEUS_STATE_DUMP_EVERY="2",
               ZEUS_STATE_DUMP_FROM="100", ZEUS_STATE_DUMP_ZONES="17,16,4,9,-1,44", ZEUS_POKE=base + ".poke")
    if not dumps:
        env = dict(os.environ, ZEUS_POKE=base + ".poke")
    if not end_only:
        with open(os.path.join(d, "log.txt"), "w") as log:
            subprocess.run(exe, env=env, stdout=log, stderr=subprocess.STDOUT, check=True, cwd=ROOT)
    if not dumps:
        return
    last = max(int(os.path.basename(f)[5:11]) for f in oracle.dump_files(os.path.join(d, "dump")))
    os.makedirs(os.path.join(d, "dump_end"), exist_ok=True)
    os.makedirs(os.path.join(d, "sh_end"), exist_ok=True)
    env = dict(os.environ, ZEUS_STATE_DUMP=os.path.join(d, "dump_end"), ZEUS_STATE_DUMP_FROM=str(last),
               ZEUS_STATE_DUMP_TO=str(last), ZEUS_POKE=base + ".poke")
    with open(os.path.join(d, "log_end.txt"), "w") as log:
        w2 = os.path.join(d, "write_end")                  # a fresh write dir: run 1's save changes the menus
        os.makedirs(w2, exist_ok=True)
        ex2 = [w2 if a == os.path.join(d, "write") else a for a in exe[:-2]]
        subprocess.run(ex2 + ["--script", script.replace(d + "/sh/", d + "/sh_end/")], env=env, stdout=log,
                       stderr=subprocess.STDOUT, check=True, cwd=ROOT)


class State:
    def __init__(self, path, types):
        self.d = d = oracle.Dump(path)
        z = lambda a, n, dt: np.frombuffer(d.data, dt, n, next(o + a - za for b, za, s, o in d.zones
                                                             if za <= a < za + s))
        self.T = z(TERRAIN, N * N, "<u4").copy()
        bg = z(GRID_BUILDING, N * N, "<i2")
        self.btype = np.where(bg > 0, types[np.clip(bg, 0, len(types) - 1)], 0)
        self.treasury = d.at(TREASURY)
        self.size = (d.at(0x00902954), d.at(0x00902958))


def herd_points(st):
    """map_area_has_marker 0x00496B50's points (logical): wolf 0x00902BB4 (h, 4), boar 0x00902D10 (i, 4), deer
    0x00902C54 (h, 4); x at the address, y 8 / 16 bytes on."""
    out = []
    for a, fmt, step, dy in ((0x00902BB4, "<h", 2, 8), (0x00902D10, "<i", 4, 16), (0x00902C54, "<h", 2, 8)):
        for k in range(4):
            out.append((st.d.at(a + k * step, fmt), st.d.at(a + k * step + dy, fmt)))
    return out


def compare(d, show=None):
    lines = open(os.path.join(ROOT, "re", "oracle", "scenarios", "1R-roads.txt")).read().splitlines()
    drags = [l.split()[1:] for l in lines if re.match(r"# d\d{3} ", l)]
    ticks = {}
    for l in open(os.path.join(d, "log.txt"), errors="replace"):
        m = re.search(r"shot \S*/d(\d{3})\.bmp ticks (\d+)", l)
        if m:
            ticks[int(m.group(1))] = int(m.group(2))
    have = sorted(int(os.path.basename(f)[5:11]) for f in oracle.dump_files(os.path.join(d, "dump")))
    path = lambda k: os.path.join(d, "dump", f"tick_{k:06d}.bin")
    at_most = lambda k: max(x for x in have if x <= k)
    at_least = lambda k: min(x for x in have if x >= k)
    bad = 0
    origin = None
    end = oracle.Dump(oracle.dump_files(os.path.join(d, "dump_end"))[-1])       # building types (records never move)
    types = np.frombuffer(end.block(35), np.uint8).reshape(-1, BSIZE)[:, 0x10:0x12].copy().view("<i2").ravel()
    for i, (dn, scene, *xy) in enumerate(drags):
        x1, y1, x2, y2 = map(int, xy)
        K = ticks.get(i)
        if K is None:
            print(f"d{i:03d} {scene}: no shot")
            bad += 1
            continue
        # pre: halfway from the previous drag's shot (its release is 0.9 s after it, this press 1.5 s before this
        # shot, 4 s apart); post: 30 % on to the next shot (the release is 0.9 s after this one, the next press 2.5)
        kp, kn = ticks.get(i - 1, K - 40), ticks.get(i + 1, K + 40)
        pre, mid, post = (State(path(at_most(max((kp + K) // 2, K - 9))), types), State(path(at_most(K)), types),
                          State(path(at_least(K + max(4, (kn - K) * 3 // 10))), types))
        if origin is None:
            base = pre.d.at(0x00DA2F80)
            origin = (base % N, base // N)
        G = roaddrag.Grids(pre.T.copy(), pre.btype, roaddrag.near_edge(pre.size))
        r = roaddrag.drag(G, x1, y1, x2, y2)
        ours = set(r["tiles"])
        new_bits = lambda s: {(int(j % N), int(j // N)) for j in np.nonzero((s.T & 0x40) & ~(pre.T & 0x40))[0]}
        exe_mid, exe_post = new_bits(mid), new_bits(post)
        lx, ly = sorted((x1 - origin[0], x2 - origin[0])), sorted((y1 - origin[1], y2 - origin[1]))
        marker = any(lx[0] <= px <= lx[1] and ly[0] <= py <= ly[1] for px, py in herd_points(pre))
        new_ours = {t for t in ours if not pre.T[t[1] * N + t[0]] & 0x40}
        spent = pre.treasury - post.treasury
        # mid: the preview's bits are in the terrain only between its call and the next frame's restore, so a
        # dump catches them about every other drag; when it does they must be ours (a failed trace's part too)
        # a herd point in the rectangle: build_commit refuses (message 0x16) but leaves the preview's tiles in the
        # terrain (no restore), uncharged
        ok = (not exe_mid or exe_mid == new_ours) and exe_post == new_ours
        ok = ok and spent == (0 if marker else 2 * r["new"])
        tag = "ok " if ok else "BAD"
        bad += not ok
        info = (f"d{i:03d} {tag} {scene:9s} ({x1},{y1})->({x2},{y2}) ours {'ok' if r['ok'] else 'refused' if r['refused'] else 'fail'}"
                f" {len(r['tiles'])} set/{r['new']} new{' MARKER' if marker else ''}; exe mid {len(exe_mid)} post "
                f"{len(exe_post)} spent {spent}")
        print(info)
        if not ok or show == i:
            print("   ours-exe(post):", sorted(new_ours - exe_post)[:12],
                  " exe-ours:", sorted(exe_post - new_ours)[:12])
            print("   mid  ours-exe:", sorted(new_ours - exe_mid)[:12], " exe-ours:", sorted(exe_mid - new_ours)[:12])
    print(f"{len(drags) - bad}/{len(drags)} drags equal")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["--scenario"]:
        build(a[1])
    elif a[:1] == ["--calibrate"]:
        calibrate(a[1], a[2] if len(a) > 2 else os.path.join(ROOT, "re", "oracle", "scenarios", "1R-roads"))
    elif a[:1] == ["--run"]:
        run(a[1], dumps="--no-dumps" not in a, end_only="--end-only" in a)
    else:
        compare(a[0], int(a[a.index("--show") + 1]) if "--show" in a else None)
