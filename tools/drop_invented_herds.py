"""Remove the boar/deer herds an older sim invented on maps without herd points (bugs.md 435).

Before e97e734, sim/systems/wild.prey_points generated herd points at forest edges when the map's own list was
empty, and cached them in the save (g._prey_points). The exe creates herds only at the map's points
(FUN_004E0160), so such a save keeps refilling herds the original never has. This drops every cached point that
is not one of the map's, the animals of those herds (walker origin), and their refill timers / counts.

  python3 tools/drop_invented_herds.py SAVE.pkl [SAVE2.pkl ...]     # rewrites each save in place
  python3 tools/drop_invented_herds.py --dry SAVE.pkl                # report only
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sim.game import Game               # noqa: E402
from sim.systems import walkers, wild   # noqa: E402


def drop(g):
    """Returns (points dropped, animals removed)."""
    own = getattr(g.world, "boar_points", None)
    cached = g.__dict__.get("_prey_points")
    if own is None or cached is None:
        return [], 0
    keep = {tuple(p) for p in own}
    bad = [tuple(p) for p in cached if tuple(p) not in keep]
    if not bad:
        return [], 0
    badset = set(bad)
    gone = [w for w in list(g.walkers.values()) if w.role in wild.PREY and w.origin and tuple(w.origin) in badset]
    for w in gone:
        walkers.remove(g, w)
    for k in ("herd_timers", "herd_count"):
        d = g.sd(k, {})
        for p in bad:
            d.pop(p, None)
    g._prey_points = [tuple(p) for p in own]
    return bad, len(gone)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("saves", nargs="+")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    for path in a.saves:
        g = Game.load(path)
        bad, n = drop(g)
        print(f"{path}: {len(bad)} invented herd points, {n} animals removed")
        if bad and not a.dry:
            g.save(path)


if __name__ == "__main__":
    main()
