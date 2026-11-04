"""Ship passability and routes against an oracle run (bugs.md 238; docs/logic/pathfinding.md 7.1).

    python3 tools/oracle_ships.py RUN_DIR [--routes] [--kind trade|fishing|trireme|transport|warship]

For every dump of the run: grid_ship rebuilt from the dump's own terrain (0x00CCE128) and bridge pieces
(0x00CB4B08) by ours (sim/systems/walkers.ship_grid), then every ship figure (0x14 trade ship, 0x19
fishing boat, 0x39 trireme, 0x3F transport, 0x40 warship; Figure +0x14/+0x16 logical x y) looked up in it:
a ship on a tile ours blocks (0xFF) is an error. --routes: for a ship whose destination (+0x24/+0x26) is the same
in two dumps in a row, its tile in the later dump must lie on ours' route (walkers.water_path) from its tile in the
earlier one (or be that tile). --kind: only that kind of ship. Prints the counts (moves per kind) and the first
misses. Trade ships (bugs.md 462): 1H-bless, 1F-palacefire, schools-A carry one sailing to / from its dock.
"""
import glob
import os
import sys
from types import SimpleNamespace

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)
import oracle  # noqa: E402

FIG, FSZ = 0x00DBD788, 0x184
SHIPS = {0x14: "trade", 0x19: "fishing", 0x39: "trireme", 0x3F: "transport", 0x40: "warship"}


def span(d, address, size):
    for b, a, s, o in d.zones:
        if a <= address and address + size <= a + s:
            return d.data[o + address - a:o + address - a + size]
    raise KeyError(hex(address))


def fake_game(d):
    from sim.systems import walkers
    t = np.frombuffer(span(d, 0x00CCE128, 228 * 228 * 4), "<u4").reshape(228, 228).copy()
    pc = np.frombuffer(span(d, 0x00CB4B08, 228 * 228), "u1").reshape(228, 228)
    base = d.at(0x00902928 + 0x34)                      # scenario block: grid base, play area W, H
    w, h = d.at(0x00902928 + 0x2C), d.at(0x00902928 + 0x30)
    ys, xs = np.nonzero(pc & (t & 0x44 == 0x44))
    pieces = {(int(x), int(y)): int(pc[y, x]) for y, x in zip(ys, xs)}
    g = SimpleNamespace(world=SimpleNamespace(flags=t, origin=(base % 228, base // 228), size=(w, h)),
                        bridges=set(pieces), bridge_short={p for p, v in pieces.items() if v in (13, 14)},
                        bridge_pieces=pieces, poseidon=False, map_version=0)
    walkers.ship_grid(g)
    return g


def ships(d):
    out = []
    for i in range(1, 2000):
        a = FIG + i * FSZ
        try:
            st, ty = d.at(a + 0x0E, "<B"), d.at(a + 0x0A, "<B")
        except KeyError:
            break
        if st == 1 and ty in SHIPS:
            out.append((i, SHIPS[ty], d.at(a + 0x14, "<h"), d.at(a + 0x16, "<h"), d.at(a + 0x24, "<h"),
                        d.at(a + 0x26, "<h")))
    return out


def main(argv):
    from oracle import Dump
    from sim.systems import walkers
    run = argv[0]
    routes = "--routes" in argv
    only = argv[argv.index("--kind") + 1] if "--kind" in argv else None
    kinds = {}
    paths = oracle.dump_files(os.path.join(run, "dump")) or oracle.dump_files(run)
    n = bad = 0
    rn = rbad = 0
    misses = []
    prev = {}
    g = None
    for p in paths:
        d = Dump(p)
        if g is None:
            g = fake_game(d)
        ox, oy = g.world.origin
        sg = walkers.ship_grid(g)
        cur = {}
        for i, kind, x, y, dx, dy in ships(d):
            if only and kind != only:
                continue
            n += 1
            if sg[y + oy, x + ox] == 0xFF:
                bad += 1
                misses.append((os.path.basename(p), kind, i, (x, y), "on 0xFF"))
            cur[i] = (kind, (x + ox, y + oy), (dx + ox, dy + oy))
            if routes and i in prev and prev[i][2] == cur[i][2] and prev[i][1] != cur[i][1]:
                rn += 1
                kinds[kind] = kinds.get(kind, 0) + 1
                r = walkers.water_path(g, prev[i][1], {prev[i][2]})
                if r is None or cur[i][1] not in r:
                    rbad += 1
                    misses.append((os.path.basename(p), kind, i, (x, y), f"off ours' route from "
                                   f"{(prev[i][1][0] - ox, prev[i][1][1] - oy)} to {(dx, dy)}"))
        prev = cur
    print(f"{run}: {len(paths)} dumps, {n} ship positions, {bad} on tiles ours blocks"
          + (f"; {rn} moves {kinds}, {rbad} off ours' route" if routes else ""))
    for m in misses[:20]:
        print("  ", *m)
    return 1 if bad or rbad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
