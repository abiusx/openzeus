"""Gatherers vs the exe: woodcutters (figure 0x37, figure_wood_cutter 0x004BF060) and stonecutters / miners (0x3E,
figure_miner 0x004C1310) of a working-city run, sample by sample (docs/logic/production.md "Resource search").

    python3 tools/oracle_gatherers.py RUN [ROLE ...]       # RUN = re/oracle/runs/schools-A (25-tick dumps)
    ROLE: woodcutter (default), stonecutter

Ours: Adventures/tutorial15.sav loaded by sim/savimport.py (the same city; ids and origin (44, 44)), every staffed
building's employees pinned to the run's dumps (Building +0x40; our labour allocation differs a little), the gatherers'
buildings given the dump-0 stock (+0x3C) and counters (+0x32, +0x33), and the dump-0 figures of the ROLE seeded as
ours: action 6 (waiting, timer +0x36), 7 (walking to +0x24/+0x26: route mode 3 / 0xB from their tile), 8 (working,
timer), 9 (walking home), 0xD (pause). The figures' sub-tile progress at dump 0 is not seeded, so a seeded walk may
be a tick or two off; every figure the buildings send after dump 0 is the port's own.

Per dump: the exe's figures of the type as (x, y, action) and ours (state go 7, work 8, back 9, pause 0xD,
waiting 6), both in logical tiles. Prints each differing sample and the count of equal ones. Stumps regrow when the
exe's do (regrow_as_exe: the regrowth steps are random draws).
"""
import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)
import oracle  # noqa: E402
from oracle import Dump  # noqa: E402

FIG, FSZ = 0x00DBD788, 0x184
BLD, BSZ = 0x0092E658, 0x118
TYPES = {"woodcutter": 0x37, "stonecutter": 0x3E}
HOMES = {"woodcutter": (0x33,), "stonecutter": (0x31, 0xD5)}


def exe_figs(d, typ):
    out = []
    for i in range(1, 2000):
        a = FIG + i * FSZ
        try:
            st = d.at(a + 0x0E, '<B')
        except KeyError:
            break
        if st != 1 or d.at(a + 0x0A, '<B') != typ:
            continue
        out.append(dict(id=i, x=d.at(a + 0x14, '<h'), y=d.at(a + 0x16, '<h'), action=d.at(a + 0x38, '<B'),
                        timer=d.at(a + 0x36, '<h'), dest=(d.at(a + 0x24, '<h'), d.at(a + 0x26, '<h')),
                        bld=d.at(a + 0x5A, '<h'), rock=(d.at(a + 0x5C, '<h'), d.at(a + 0x5E, '<h'))))
    return out


def regrow_as_exe(g, d, ox, oy):
    """The stumps' regrowth is drawn by each game's own RNG (terrain_regrow: 4 + a random bit a day), so ours takes
    the exe's: a stump of ours grows in the interval up to dump d when the exe's tile is a grown tree (regrowth 255)
    in d, else not yet."""
    base = d.at(0x00DA2F80, '<i')
    keep = []
    for tk, x, y in getattr(g, "regrow", None) or ():
        grown = d.at(0x00C1C648 + base + (y - oy) * 228 + (x - ox), '<B') == 255
        keep.append((g.tick if grown else 10 ** 9, x, y))
    g.regrow = keep


def ours_state(w):
    if w.task == "search":
        return 6
    return {"go": 7, "work": 8, "back": 9, "pause": 0xD, "unload": 9}.get(w.state, -1)


def compare(run, role):
    from sim import savimport
    from sim.systems import labor, walkers, economy
    files = oracle.dump_files(os.path.join(run, "dump"))
    g = savimport.load(os.path.join(ROOT, "zeus-original/app/Adventures/tutorial15.sav"))
    ox, oy = g.world.origin
    by_xy = {(b.x - ox, b.y - oy): b for b in g.buildings.values()}
    d0 = Dump(files[0])
    emap = {}
    for e in range(1, 2000):
        a = BLD + e * BSZ
        try:
            if d0.at(a, '<B') != 1:
                continue
        except KeyError:
            break
        b = by_xy.get((d0.at(a + 6, '<h'), d0.at(a + 8, '<h')))
        if b is not None and d0.at(a + 0x10, '<h') == b.misc.get("zeus_type", g.cat.spec(b.key).get("zeus_id")):
            emap[e] = b
    emp = {}
    for f in files:
        d = Dump(f)
        emp[int(os.path.basename(f)[5:11])] = {e: d.at(BLD + e * BSZ + 0x40, '<B') for e in emap}
    typ = TYPES[role]
    homes = {e: b for e, b in emap.items() if d0.at(BLD + e * BSZ + 0x10, '<h') in HOMES[role]}
    for e, b in homes.items():
        a = BLD + e * BSZ
        spec = g.cat.spec(b.key)
        b.goods[spec["output"]] = d0.at(a + 0x3C, '<h')
        b.spawn_timer = d0.at(a + 0x32, '<B')
        if role == "stonecutter":
            economy.misc(b)["idle"] = d0.at(a + 0x33, '<B')
    for f in exe_figs(d0, typ):
        b = homes.get(f["bld"])
        if b is None:
            continue
        x, y = f["x"] + ox, f["y"] + oy
        dest = (f["dest"][0] + ox, f["dest"][1] + oy)
        w = walkers.new_walker(g, role=role, home=b.id, x=x, y=y, path=[], target_tile=None, state="go")
        b.walkers.append(w.id)
        spec = g.cat.spec(b.key)
        if f["action"] == 6:
            w.task = "search"
            delay = max(1, f["timer"]) if role == "woodcutter" else max(1, 11 - f["timer"])
        elif f["action"] == 7:
            w.target_tile = dest
            w.path = (walkers.route3 if role == "woodcutter" else walkers.route11)(g, (x, y), dest) or []
            delay = walkers.tile_delay(g, w)
        elif f["action"] == 8:
            w.target_tile, w.state, w.anim_t0 = (x, y), "work", g.tick
            delay = max(1, spec["work_ticks"] - f["timer"])
        else:
            w.state, w.amount = "back", spec["yield"]
            w.path = (walkers.route3 if role == "woodcutter" else walkers.route11)(g, (x, y), tuple(b.access)) or []
            delay = walkers.tile_delay(g, w)
        walkers.add(g, w, delay)
    t0 = g.tick
    orig_alloc = labor.allocate

    def alloc(g):
        orig_alloc(g)
        for e, n in emp[min(max(emp), (g.tick - t0) // 25 * 25)].items():
            emap[e].employees = n
    labor.allocate = alloc
    alloc(g)
    same = n = 0
    for f in files:
        t = int(os.path.basename(f)[5:11])
        regrow_as_exe(g, Dump(f), ox, oy)
        g.step(t - (g.tick - t0))
        exe = Counter((x["x"], x["y"], x["action"]) for x in exe_figs(Dump(f), typ) if x["bld"] in homes)
        ours = Counter((w.x - ox, w.y - oy, ours_state(w)) for w in g.walkers.values()
                       if w.role == role and w.home in {b.id for b in homes.values()})
        n += 1
        if exe == ours:
            same += 1
        else:
            print(t, "exe ", sorted(exe.elements()))
            print(" " * len(str(t)), "ours", sorted(ours.elements()))
    labor.allocate = orig_alloc
    print(f"{role}: {same} of {n} samples equal")
    return same, n


if __name__ == "__main__":
    run = sys.argv[1]
    for r in sys.argv[2:] or ["woodcutter"]:
        compare(run, r)
