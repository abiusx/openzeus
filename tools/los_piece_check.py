"""Line of fire's building test (0x004D9B80) against the original's own grids, per save.

The exe blocks a line on a tile with terrain & 0xC001 (wall, tower/gatehouse, tree), or on a building tile (terrain
& 8) whose piece byte (g_grid_piece 0x00D00D68, sav rank 20) has a low nibble != 0. building_footprint_place
0x004A04B0 writes that nibble on every tile of a footprint: its width - 1 (a footprint placed with width 1 gets 0, a
composite's pieces each their own width). This tool loads every original .sav (zeus-original/app/Adventures/*.sav)
into ours (sim/savimport.load) and compares, tile by tile, the exe's building test with ours (defences.piece_blocks).

    python3 tools/los_piece_check.py [SAV...]      prints per save: tiles compared, mismatches by our building key
"""
import glob
import os
import sys
from collections import Counter

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from sim import savimport  # noqa: E402
from sim.military import defences  # noqa: E402

N = 228
TERRAIN, PIECE, BGRID = 17, 20, 16       # sav ranks: g_grid_terrain, g_grid_piece, g_grid_building


def check(path):
    hdr, b = savimport.read(path)
    terr = np.frombuffer(b[TERRAIN], "<u4").reshape(N, N)
    piece = np.frombuffer(b[PIECE], np.uint8).reshape(N, N)
    exe = ((terr & 8) != 0) & ((piece & 0xF) != 0)
    g = savimport.load(path)
    bad, n = Counter(), 0
    for y in range(N):
        for x in range(N):
            if not (terr[y, x] & 8) and not g.world.occ[y, x]:
                continue
            n += 1
            o = defences.piece_blocks(g, x, y)
            if o != bool(exe[y, x]):
                bd = g.buildings.get(int(g.world.occ[y, x]))
                bad[(bd.key if bd else None, "exe" if exe[y, x] else "ours", int(piece[y, x]) & 0xF)] += 1
    return n, bad


def main(argv):
    paths = argv or sorted(glob.glob(os.path.join(ROOT, "zeus-original/app/Adventures/*.sav")))
    total = 0
    for p in paths:
        n, bad = check(p)
        total += sum(bad.values())
        print(f"{os.path.basename(p)}: {n} building tiles, {sum(bad.values())} differ"
              + "".join(f"\n  {k[0]}: blocks in {k[1]} only (exe nibble {k[2]}) x{v}" for k, v in sorted(bad.items(), key=str)))
    print("total differences", total)
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
