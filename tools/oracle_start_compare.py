"""Compare a new game's start grids: the oracle's first dump (the exe after loading the map) against the map file
and against ours (sim/world.py World). docs/logic/map-terrain.md 11 "Start state of a new game".

    python3 tools/oracle_start_compare.py [DUMP] [MAP]
    default DUMP re/oracle/runs/open-play-events/dump/tick_000000.bin, MAP sandbox (data/maps.json name or file)

Map blocks and save blocks of the same variable (map rank -> sav rank, refs formats/map.md, table 0x0063CDC0):
5 draw -> 15, 6 terrain -> 17, 7 piece -> 20, 8 random -> 22, 9 0x00C8E9D8 -> 24, 15 meadow -> 99,
19 regrowth -> 102, 22 scrub -> 109, 23 elevation -> 111, 24 projected elevation -> 112.
"""
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)
import mapfile  # noqa: E402
from oracle import Dump  # noqa: E402

PAIRS = {5: 15, 6: 17, 7: 20, 8: 22, 9: 24, 15: 99, 19: 102, 22: 109, 23: 111, 24: 112}
GRID = 228 * 228


def bits(x):
    return {hex(1 << b): int(((x >> b) & 1).sum()) for b in range(32) if ((x >> b) & 1).any()}


def main(argv):
    dump = argv[0] if argv else os.path.join(ROOT, "re/oracle/runs/open-play-events/dump/tick_000000.bin")
    name = argv[1] if len(argv) > 1 else "sandbox"
    from sim.world import MAPS, World
    d = Dump(dump)
    blocks = {b["rank"]: b["data"] for b in mapfile.read_file(MAPS.get(name, name))[0][1]}
    print(f"{dump} vs map {name}")
    for m, s in PAIRS.items():
        a, b = blocks[m], d.block(s)
        dt = "<u4" if len(a) == 4 * GRID else "u1"
        x, y = np.frombuffer(a, dt), np.frombuffer(b, dt)
        n = int((x != y).sum())
        print(f"  map {m:2d} = sav {s:3d}: {n} tiles differ" + (f", bits {bits(x ^ y)}" if n and dt == "<u4" else ""))
    for b, a, s, o in d.zones:                       # the other grids of the dump: zero at the start?
        if s in (GRID, 2 * GRID, 4 * GRID) and b not in PAIRS.values():
            nz = int((np.frombuffer(d.block(b), np.uint8) != 0).sum())
            print(f"  sav {b:3d} @{a:#010x}: {'all zero' if not nz else f'{nz} bytes non-zero'}")
    w = World(name)
    ex = np.frombuffer(d.block(17), "<u4").reshape(228, 228)
    n = int((w.flags != ex).sum())
    print(f"  ours World.flags vs exe terrain: {n} tiles differ" + (f", bits {bits(w.flags ^ ex)}" if n else ""))
    road = (ex & 0x40) != 0
    print(f"  ours World.road vs exe road (terrain 0x40): {int((w.road != road).sum())} tiles differ "
          f"({int(road.sum())} road tiles)")
    print(f"  ours elevation vs exe: {int((w.elev != np.frombuffer(d.block(111), np.uint8).reshape(228, 228)).sum())} "
          f"tiles differ; ours occupancy: {int((w.occ != 0).sum())} tiles")


if __name__ == "__main__":
    main(sys.argv[1:])
