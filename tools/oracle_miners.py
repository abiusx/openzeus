"""Ore miners (figure 0x3E, figure_miner 0x004C1310) in the exe against ours: a foundry (copper 0x100002) and a mint
(silver 0x200002) in a poked field of the Open Play Sandbox, their workers poked full, every miner figure compared
dump by dump (docs/logic/production.md "Resource search", "Quarrying and mining").

    python3 tools/oracle_miners.py --scenario        # writes re/oracle/scenarios/1M-miners.txt / .poke
    python3 tools/oracle_miners.py --run DIR          # zeus-run on it: figure, building, terrain dumps every 5 ticks
    python3 tools/oracle_miners.py DIR                # ours from tick 0, the same pokes and buildings: compare

Reproduce (11-02): --scenario, --run re/oracle/runs/1M-miners, the check, tools/oracle_compress.py 1M-miners.

The run: Open Play Sandbox (as tools/oracle_roads.py START), scenario events off (g_events_count 0x009173F0 = 0), a
23x23 field of plain land (terrain 0, elevation, projected elevation and piece 0) around raw (160, 130) poked at tick
2 with the ore rocks of ROCKS, the camera held on it (0x00DA2F64 / 0x00DA2F68), then the road tool drags the road
y = 130, x 152..168 and the Industry page's Raw Materials list places the foundry and the mint (clicks at their
north tiles; the shots sh/*.bmp show them). Buildings 1 and 2 get workers +0x40 = 15 at every tick (no houses).

Ours: Game("sandbox", difficulty Easy), the same field (flags 0, elevation 0) and rocks, the road and the two buildings placed at
the dump's building records' tiles on the tick they first appear there, employees 15, scenario events off; each
dump's miners (type 0x3E: x, y, action) against ours (role miner: state go 7, work 8, pause 0xD, back 9, waiting 6).
"""
import os
import re
import subprocess
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
import oracle  # noqa: E402
from oracle import Dump  # noqa: E402
from oracle_roads import Scene, START, ROAD_TOOL, TERRAIN, ELEV, PELEV, PIECE, CAM_COL, CAM_ROW  # noqa: E402

N = 228
BASE = os.path.join(ROOT, "re", "oracle", "scenarios", "1M-miners")
FIG, FSZ = 0x00DBD788, 0x184
BLD, BSZ = 0x0092E658, 0x118
CX, CY, R = 160, 130, 11
INDUSTRY, RAW = (622, 123), (676, 345)
MINT, FOUNDRY = (415, 423), (415, 447)          # the Raw Materials list (800x600)
COPPER, SILVER = 0x100002, 0x200002
# rock tiles relative to the centre: copper west, silver east; pairs side by side (shared neighbours), single rocks
ROCKS = {COPPER: [(-8, -6), (-7, -6), (-8, -5), (-4, 5), (-3, 5), (-9, 3)],
         SILVER: [(6, -7), (7, -7), (5, 5), (8, 3), (9, 3)]}
SITES = {"foundry": (CX - 3, CY - 2), "mint": (CX + 3, CY - 2)}     # the click tile (north corner) of each 2x2
ROAD = (CX - 8, CY, CX + 8, CY)
SECS, EVERY = 700, 5


def scene():
    sc = Scene("miners", CX, CY)
    sc.fill(CX - R, CY - R, CX + R, CY + R, 0)
    for kind, pts in ROCKS.items():
        for dx, dy in pts:
            sc.tiles[(CX + dx, CY + dy)] = kind
    return sc


def scenario():
    sc = scene()
    col, row = sc.cam()
    pokes = ["2 9173f0 4 0"]
    for (x, y), v in sorted(sc.tiles.items()):
        i = y * N + x
        pokes += [f"2 {TERRAIN + 4 * i:x} 4 {v}", f"2 {ELEV + i:x} 1 0", f"2 {PELEV + i:x} 1 0",
                  f"2 {PIECE + i:x} 1 0"]
    ticks = SECS * 9
    for tk in range(100, ticks):
        pokes += [f"{tk} {CAM_COL:x} 4 {col}", f"{tk} {CAM_ROW:x} 4 {row}"]
    for tk in range(2, ticks):
        for b in (1, 2):
            pokes.append(f"{tk} {BLD + b * BSZ + 0x40:x} 1 15")
    a, b = sc.screen(*ROAD[:2]), sc.screen(*ROAD[2:])
    s = [START, "56:shot DIR/sh/a.bmp", f"57:click {ROAD_TOOL[0]},{ROAD_TOOL[1]}",
         f"59:down {a[0]},{a[1]}; 60.2:move {b[0]},{b[1]}; 61:up {b[0]},{b[1]}", "62:rclick 300,300"]
    t = 64
    for name, item in (("foundry", FOUNDRY), ("mint", MINT)):
        x, y = sc.screen(*SITES[name])
        s.append(f"{t}:move {INDUSTRY[0]},{INDUSTRY[1]}; {t + .5}:click {INDUSTRY[0]},{INDUSTRY[1]}; "
                 f"{t + 2}:move {RAW[0]},{RAW[1]}; {t + 2.5}:click {RAW[0]},{RAW[1]}; "
                 f"{t + 4}:move {item[0]},{item[1]}; {t + 4.5}:click {item[0]},{item[1]}; "
                 f"{t + 6}:move {x},{y}; {t + 6.5}:click {x},{y}; {t + 8}:rclick 300,300")
        t += 10
    s.append(f"{t}:shot DIR/sh/b.bmp; {SECS - 2}:shot DIR/sh/end.bmp")
    head = [f"# Ore miners (tools/oracle_miners.py), generated; DIR = the run dir; --seconds {SECS}",
            "# Run: python3 tools/oracle_miners.py --run DIR; check: python3 tools/oracle_miners.py DIR"]
    open(BASE + ".txt", "w").write("\n".join(head) + "\n" + "; ".join(s) + "\n")
    open(BASE + ".poke", "w").write("\n".join(pokes) + "\n")
    print(f"{len(pokes)} poke lines, {SECS} s")


def run(d):
    script = open(BASE + ".txt").read().splitlines()[-1].replace("DIR", d)
    for sub in ("sh", "dump", "write"):
        os.makedirs(os.path.join(d, sub), exist_ok=True)
    exe = [os.path.join(ROOT, "refs", "zeus-poseidon-arm64", "build", "zeus-run"), "--run",
           os.path.join(ROOT, "zeus-original", "app", "Zeus.exe"), "--headless", "--deterministic",
           "--write-dir", os.path.join(d, "write"), "--seconds", str(SECS), "--state-log", "/dev/null",
           "--script", script]
    env = dict(os.environ, ZEUS_STATE_DUMP=os.path.join(d, "dump"), ZEUS_STATE_DUMP_EVERY=str(EVERY),
               ZEUS_STATE_DUMP_ZONES="28,35,37,17,16,-1", ZEUS_POKE=BASE + ".poke")
    with open(os.path.join(d, "log.txt"), "w") as log:
        subprocess.run(exe, env=env, stdout=log, stderr=subprocess.STDOUT, check=True, cwd=ROOT)


def exe_miners(d):
    out = []
    for i in range(1, 2000):
        a = FIG + i * FSZ
        try:
            st = d.at(a + 0x0E, '<B')
        except KeyError:
            break
        if st == 1 and d.at(a + 0x0A, '<B') == 0x3E:
            out.append((d.at(a + 0x14, '<h'), d.at(a + 0x16, '<h'), d.at(a + 0x38, '<B')))
    return out


def exe_buildings(d):
    out = {}
    for b in (1, 2):
        a = BLD + b * BSZ
        if d.at(a, '<B') == 1:
            out[b] = (d.at(a + 0x10, '<h'), d.at(a + 6, '<h'), d.at(a + 8, '<h'))
    return out


def compare(dr, show=True):
    from sim.game import Game
    from sim.systems import labor
    files = oracle.dump_files(os.path.join(dr, "dump"))
    d0 = Dump(files[0])
    base = d0.at(0x00DA2F80, '<i')
    ox, oy = base % N, base // N                      # logical -> raw
    g = Game("sandbox", 1, difficulty="Easy")     # open play runs at Easy (docs/re/oracle.md "Difficulty")
    g.scenario.events = []
    w = g.world
    for (x, y), v in scene().tiles.items():
        w.flags[y, x] = v
        w.elev[y, x] = 0
    g.map_version = getattr(g, "map_version", 0) + 1
    orig = labor.allocate

    def alloc(g):
        orig(g)
        for b in g.buildings.values():
            if b.key in ("foundry", "mint"):
                b.employees = 15
    labor.allocate = alloc
    placed = set()
    road = False
    kinds = {0x32: "foundry", 0x30: "mint"}
    same = n = 0
    for f in files:
        t = int(os.path.basename(f)[5:11])
        d = Dump(f)
        if not road and d.at(TERRAIN + 4 * (ROAD[1] * N + CX), '<I') & 0x40:
            g.step(t - 1 - g.tick)                    # the drag lands in the interval: before this dump's tick
            g.command(f"road {ROAD[0]} {ROAD[1]} {ROAD[2]} {ROAD[3]}")
            road = True
        for b, (typ, x, y) in exe_buildings(d).items():
            if b not in placed and typ in kinds:
                g.step(t - 1 - g.tick)
                g.command(f"build {kinds[typ]} {x + ox} {y + oy}")
                alloc(g)
                placed.add(b)
        g.step(t - g.tick)
        exe = Counter((x + ox, y + oy, a) for x, y, a in exe_miners(d))
        ours = Counter((m.x, m.y, 6 if m.task == "search" else {"go": 7, "work": 8, "pause": 0xD,
                                                                  "back": 9}.get(m.state, -1))
                       for m in g.walkers.values() if m.role == "miner")
        if not exe and not ours:
            continue
        n += 1
        if exe == ours:
            same += 1
        elif show:
            print(t, "exe ", sorted(exe.elements()))
            print(" " * len(str(t)), "ours", sorted(ours.elements()))
    labor.allocate = orig
    print(f"miners: {same} of {n} samples equal")
    return same, n


if __name__ == "__main__":
    if sys.argv[1] == "--scenario":
        scenario()
    elif sys.argv[1] == "--run":
        run(sys.argv[2])
    else:
        compare(sys.argv[1])
