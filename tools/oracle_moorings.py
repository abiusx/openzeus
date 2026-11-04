"""Check sim water_exit (wharf boat / trireme mooring, building_water_exit 0x004A3FD0) against an oracle dump:
every fishing boat's home tile (Figure+0x2C/+0x2E) and every trireme's position vs the tile our rule picks on the
dump's own terrain (bugs.md 173).

    python3 tools/oracle_moorings.py [re/oracle/runs/working-city/dump/tick_000000.bin]

The working-city map is smaller than the 228 grid: building x/y are map coordinates, the terrain grid index is
(y + 44) * 228 + (x + 44) (Building+0x0C). Prints exe vs new rule vs the old (>= 8 connected water) rule.
"""
import os
import sys
import types

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from oracle import Dump  # noqa: E402
from sim.systems import walkers  # noqa: E402

BLD, BREC, FIG, FREC, N = 0x0092E658, 0x118, 0x00DBD788, 388, 228


def main(path):
    d = Dump(path)
    T = np.frombuffer(d.block(17), "<u4").reshape(N, N)
    b1 = BLD + BREC                                  # offset of the map in the grid, from building 1's tile index
    x1, y1, tile = d.at(b1 + 6, "<h"), d.at(b1 + 8, "<h"), d.at(b1 + 0x0C, "<i")
    off = tile // N - y1
    assert tile % N - x1 == off
    flags = np.zeros((N, N), np.int64)
    occ = np.zeros((N, N), np.int32)
    flags[:N - off, :N - off] = T[off:, off:] & 0x4
    occ[:N - off, :N - off] = (T[off:, off:] & 0x8) != 0
    g = types.SimpleNamespace(world=types.SimpleNamespace(flags=flags, occ=occ, inside=lambda x, y: True))
    bad = 0
    for k in range(1, 2000):
        a = FIG + k * FREC
        if not d.at(a + 0x0E, "<B"):
            continue
        t = d.at(a + 0x0A, "<B")
        if t not in (0x19, 0x39):                    # fishing boat, trireme
            continue
        bid = d.at(a + 0x5A, "<h")
        ba = BLD + bid * BREC
        bx, by, size, o = d.at(ba + 6, "<h"), d.at(ba + 8, "<h"), d.at(ba + 3, "<B"), d.at(ba + 0xAC, "<B")
        exe = (d.at(a + 0x2C, "<h"), d.at(a + 0x2E, "<h")) if t == 0x19 else (d.at(a + 0x14, "<h"), d.at(a + 0x16, "<h"))
        new, old = walkers.water_exit(g, bx, by, size), walkers.water_exit(g, bx, by, size, connected=True)
        bad += new != exe
        print(f"{'boat' if t == 0x19 else 'trireme':7} building {bid} ({bx},{by}) size {size} o{o}: exe {exe} "
              f"new {new} old {old} {'OK' if new == exe else 'MISMATCH'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else
                  os.path.join(ROOT, "re/oracle/runs/working-city/dump/tick_000000.bin")))
