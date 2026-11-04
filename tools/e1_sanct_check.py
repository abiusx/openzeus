"""Sanctuary completion extras, ours against the exe (bugs.md 214, docs/logic/monuments.md "Extras on completion").

    python3 tools/e1_sanct_check.py RUN KEY [--map sandbox]

RUN = an oracle run of re/oracle/scenarios/e1-sanct.txt (a sanctuary placed on Open Play Sandbox, its pieces poked to
their last stage by tools/oracle_monument.py --complete, the completion pass applies the extras). Reads the last dump:
the sanctuary's piece records (type of building 1, +0x12 = index among the layout's pieces of class < 1000, x/y
logical), the orientation (+0x9C = the R key count DAT_00DA23C4, not the view: FUN_0053DE20), the trees created (types 0x24 olive, 0x23 vine, 0xD9 orange, +0xD8 = the root) and
their growth (+0x54), and the terrain (block 17) bits gained since the last dump before completion (0x200002 silver,
0x100002 copper, 0x800 meadow) and the tiles holding 0x10000000 at the end (the exe sets it on the whole box
at placement, ours on the extras tiles at completion: printed as a subset). Ours: a new game on the same map, the monument created at the box origin that puts
every piece where the exe has it (sim/systems/monuments.py piece_xy), then extras_complete. Prints each set's size and
whether ours equals the exe's (raw = logical + World.origin)."""
import glob
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import oracle  # noqa: E402
from oracle import Dump  # noqa: E402

B, R, N = 0x0092E658, 0x118, 228
TREES = {0x24: "olive_tree", 0x23: "grapevine", 0xD9: "fruit_tree"}


ORG = (0, 0)


def exe_side(run):
    fs = oracle.dump_files(os.path.join(run, "dump"))
    d = Dump(fs[-1])
    d0 = Dump(fs[0])                    # the last dump before the completion pass (root +0x68 still 0)
    for f in fs:
        df = Dump(f)
        if df.at(B + R, "<B") and df.at(B + R + 0x10, "<h") == d.at(B + R + 0x10, "<h") and not df.at(B + R + 0x68, "<B"):
            d0 = df
    at = lambda i, o, f="<h": d.at(B + i * R + o, f)  # noqa: E731
    typ = at(1, 0x10)
    pieces, trees = {}, {}
    for i in range(1, 2000):
        if not at(i, 0, "<B"):
            continue
        if at(i, 0x10) == typ:
            pieces[at(i, 0x12)] = (at(i, 6), at(i, 8))
        elif at(i, 0x10) in TREES:
            trees[(at(i, 6), at(i, 8))] = (TREES[at(i, 0x10)], at(i, 0x54), at(i, 0xD8))
    t0 = np.frombuffer(d0.block(17), "<u4").reshape(N, N)
    t1 = np.frombuffer(d.block(17), "<u4").reshape(N, N)
    gained = lambda m: {(int(x) - ORG[0], int(y) - ORG[1]) for y, x in zip(*np.nonzero((t1 & m == m) & (t0 & m != m)))}  # noqa: E731
    has = lambda m: {(int(x) - ORG[0], int(y) - ORG[1]) for y, x in zip(*np.nonzero(t1 & m == m))}  # noqa: E731
    bits = {"0x10000000 (set)": has(0x10000000), "silver 0x200002": gained(0x200002),
            "copper 0x100002": gained(0x100002), "meadow 0x800": gained(0x800)}
    return pieces, at(1, 0x9C, "<B"), trees, bits, at(1, 0x68, "<B")


def ours_side(key, map_name, pieces, orient):
    from sim.game import Game
    from sim.model import Building
    from sim.systems import monuments as M
    g = Game(map_name, 1)
    ox, oy = g.world.origin
    b = Building(id=g.next_bid, key=key, x=0, y=0, size=0, kind="monument")
    g.next_bid += 1
    M.create(g, b, orient)
    real = [p for p in M.layouts()[key]["pieces"] if p[2] < 1000]
    idx = [i for i, p in enumerate(M.layouts()[key]["pieces"]) if p[2] < 1000]
    j0 = min(pieces)
    px, py = M.piece_xy(b, idx[j0])
    b.x, b.y = pieces[j0][0] + ox - px, pieces[j0][1] + oy - py
    bad = sum(M.piece_xy(b, idx[j]) != (x + ox, y + oy) for j, (x, y) in pieces.items())
    g.buildings[b.id] = b
    g.world.occ[b.y:b.y + b.misc["h"], b.x:b.x + b.misc["w"]] = b.id
    f0 = g.world.flags.copy()
    M.extras_complete(g, b)
    f1 = g.world.flags
    gained = lambda m: {(int(x) - ox, int(y) - oy) for y, x in zip(*np.nonzero((f1 & m == m) & (f0 & m != m)))}  # noqa: E731
    has = lambda m: {(int(x) - ox, int(y) - oy) for y, x in zip(*np.nonzero(f1 & m == m))}  # noqa: E731
    bits = {"0x10000000 (set)": has(0x10000000), "silver 0x200002": gained(0x200002),
            "copper 0x100002": gained(0x100002), "meadow 0x800": gained(0x800)}
    trees = {(t.x - ox, t.y - oy): (t.key, t.misc.get("growth", 0)) for t in g.buildings.values()
             if t.misc.get("sanctuary") == b.id}
    return (b.x, b.y), bad, len(real), trees, bits, M.origin(b), (ox, oy)


def main():
    run, key = sys.argv[1], sys.argv[2]
    map_name = sys.argv[sys.argv.index("--map") + 1] if "--map" in sys.argv else "sandbox"
    global ORG
    from sim.game import Game
    ORG = tuple(Game(map_name, 1).world.origin)
    pieces, orient, etrees, ebits, done = exe_side(run)
    box, bad, n, otrees, obits, org, origin = ours_side(key, map_name, pieces, orient)
    print(f"{key} orientation {orient}, exe complete flag {done}: {len(pieces)} piece records (ours {n}); ours box at "
          f"raw {box} puts {len(pieces) - bad} of {len(pieces)} pieces where the exe has them; layout origin raw {org}")
    for k in ebits:
        e, o = ebits[k], obits[k]
        print(f"  {k}: exe {len(e)} tiles, ours {len(o)}, equal {e == o}, ours within the exe's {o <= e}" + ("" if e == o else
              f" (exe only {sorted(e - o)[:6]}, ours only {sorted(o - e)[:6]})"))
    et = {p: v[0] for p, v in etrees.items()}
    ot = {p: v[0] for p, v in otrees.items()}
    print(f"  trees: exe {len(et)} ({', '.join(sorted(set(et.values())))}), ours {len(ot)}, same tiles and kinds {et == ot}; "
          f"exe growth (+0x54) {sorted({v[1] for v in etrees.values()})}, ours {sorted({v[1] for v in otrees.values()})}")


if __name__ == "__main__":
    main()
