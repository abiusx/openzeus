"""A large statue's carving figure in oracle shots against the rule ours draws (the stage plan 1F "Statue carver offset";
docs/play/monuments.md 8; viewer/play/monuments.js conan).

    python3 tools/statue_carver_check.py [RUN] [--piece 402] [--col 107 --row 176]

RUN = an oracle run of re/oracle/scenarios/e1-statue.txt with dumps on the shots' ticks (default re/oracle/runs/1F-statue;
run.log has "shot PATH ticks K" lines, docs/re/oracle.md). The exe hides the artisan and the piece's +0x48 (0x005407A0 ->
FUN_00430490) draws the carver: t = the piece's counter +0x60 (0..99), the phase row of data/play/monuments.json
anims.conan whose distances cover t, at (x0, y0) + (x1 - x0, y1 - y0) * t' / distance from the piece's draw point,
image look first + base + dir * stride / 8 + (t' % frames) * stride. The draw point here: the 2x2 piece's left-corner
tile in view 0 (x, y + 1), its tile box top-left ((x - y) 30, (x + y) 15 - 30 grid elevation) - camera (60 COL - 6870,
15 ROW - 30), the grid elevation from the dump (block 111: terrain + the sanctuary's raise, as ours' terrain + layout
height). Prints, per shot, the picture scored at the rule (share of opaque pixels within 10 a channel) and the best
spot within 20 px."""
import argparse, json, os, sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from oracle import Dump  # noqa: E402
from oracle_match import screen, find, meta, score_at  # noqa: E402
from e1_figure_check import tmpl  # noqa: E402

N, B, R = 228, 0x0092E658, 0x118


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run", nargs="?", default=os.path.join(ROOT, "re/oracle/runs/1F-statue"))
    ap.add_argument("--piece", type=int, default=402)
    ap.add_argument("--col", type=int, default=107)
    ap.add_argument("--row", type=int, default=176)
    a = ap.parse_args()
    C = json.load(open(os.path.join(ROOT, "data/play/monuments.json")))["anims"]["conan"]
    shots = []
    for line in open(os.path.join(a.run, "run.log")):
        if line.startswith("shot "):
            p = line.split()
            f = os.path.join(a.run, "dump", f"tick_{int(p[3]):06d}.bin")
            if (os.path.exists(f) or os.path.exists(f + ".zst")) and os.path.exists(p[1]):
                shots.append((p[1], f))
    seen, ok = set(), 0
    for shot, f in shots:
        if f in seen:
            continue
        seen.add(f)
        d = Dump(f)
        t = d.at(B + a.piece * R + 0x60, "<h")
        stage = d.at(B + a.piece * R + 0x58, "<i")
        x, y = d.at(B + a.piece * R + 6, "<h") + 44, d.at(B + a.piece * R + 8, "<h") + 45     # left corner, raw
        row, tt = None, t
        for r in C["phases"][stage] if stage < len(C["phases"]) else []:
            if tt < r[5]:
                row = r
                break
            tt -= r[5]
        if row is None:
            continue
        k = C["looks"][str(row[4])]
        idx = k["first"] + k["base"] + row[6] * (k["stride"] >> 3) + (tt % k["frames"]) * k["stride"]
        el = int(np.frombuffer(d.block(111), "i1")[y * N + x])
        bx = (x - y) * 30 - (60 * a.col - 6870)
        by = (x + y) * 15 - 30 * el - (15 * a.row - 30)
        m = meta(C["file"], idx)
        px = bx + row[0] + int((row[2] - row[0]) * tt / row[5]) - m["anchor_x"]
        py = by + row[1] + int((row[3] - row[1]) * tt / row[5]) - m["anchor_y"]
        S, T = screen(shot), tmpl(C["file"], idx)
        s = score_at(S, T, px, py)[0]
        best = find(S, T, tol=10, thr=0.6, region=(px - 20, py - 20, px + 20, py + 20))[:1]
        ok += s >= 0.9
        print(f"{os.path.basename(shot)} {os.path.basename(f)} counter {t} {C['file']}:{idx} at ({px}, {py}) score "
              f"{s:.3f}" + (f" best ({best[0][0]}, {best[0][1] - px}, {best[0][2] - py})" if best else ""))
    print(f"{ok} of {len(seen)} shots at the rule (>= 0.9)")


if __name__ == "__main__":
    main()
