"""Sheep under the build cursor (bugs.md 431, docs/logic/buildings.md 5 "Animals under the build cursor"): compare the
oracle runs re/oracle/runs/sheep-build-r1 (no tool) and sheep-build-r3 / -r4 (house-plot ghost over sheep 288 at tick
37/38; scenario re/oracle/scenarios/sheep-build.txt). Prints, per dump, sheep 288's tile, action (+0x38), destination
(+0x24/+0x26, logical: raw = + (44, 44) on this map) and tile progress in each run.

    python3 tools/oracle_sheep_build.py [FIG] [FROM TO]
"""
import os, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from oracle import Dump  # noqa: E402

N = 228
RUNS = [os.path.join(ROOT, "re/oracle/runs", f"sheep-build-{r}") for r in ("r1", "r3", "r4")]


def fig(path, k):
    F = Dump(path).block(28)
    o = k * 0x184
    tile = struct.unpack_from("<i", F, o + 0x20)[0]
    dx, dy = struct.unpack_from("<hh", F, o + 0x24)
    return f"({tile % N},{tile // N}) a{F[o + 0x38]} dest ({dx},{dy}) p{F[o + 0x39] & 0xF}"


def main():
    k = int(sys.argv[1]) if len(sys.argv) > 1 else 288
    a, b = (int(sys.argv[2]), int(sys.argv[3])) if len(sys.argv) > 3 else (34, 52)
    print("tick  " + "  |  ".join(os.path.basename(r) for r in RUNS))
    for t in range(a, b):
        cells = []
        for r in RUNS:
            p = os.path.join(r, "dump", f"tick_{t:06d}.bin")
            try:
                cells.append(fig(p, k))
            except FileNotFoundError:
                cells.append("-")
        print(f"{t:4d}  " + "  |  ".join(cells))


if __name__ == "__main__":
    main()
