"""Grazed meadow pictures against the exe (the stage plan 1F "Grazed meadow regrowth"; docs/play/terrain.md 3).

    python3 tools/meadow_check.py [RUN] [SHOT] [--tick N]

RUN = an oracle run of re/oracle/scenarios/meadow-regrowth.txt with dumps around the shot (default
re/oracle/runs/1F-meadow2, ZEUS_STATE_DUMP_FROM=1975 TO=1979: dumps 1975..1978, regrowth equal in all), SHOT its
800x600 view-0 end.bmp. From the dump (sav ranks: 17 terrain flags, 111 elevation, 22 random, 109 scrub, 99 meadow,
102 regrowth, 20 piece) every tile's picture as ours (tools/terrain_images.py images_full = terrain_resource_image,
meadow branch e1 = int((meadow - 1) / 99 * regrowth / 85)), and again with every regrowth byte 255 (an ungrazed
meadow). For each meadow tile on screen whose picture depends on its regrowth byte, both pictures are scored in the
shot at the tile's place (view cell 0x00DA2F64 / 0x00DA2F68 of the dump: tile left (x - y) 30 - (60 COL - 6870), top
(x + y) 15 - (15 ROW - 30) - 30 elevation + 30 - picture height) as the share of the picture's opaque pixels within 10
per channel (tools/oracle_match.py). A tile at regrowth 0 was eaten since the last daily regrow (figure_graze
0x004F8770 sets the byte without terrain_resource_image): its picture is still the old one, taken as the grown meadow
(sim/systems/walkers.py picture_regrowth), and the bare one is the other. A tile counts for ours when ours scores
higher; tiles under figures or buildings score low for both (left out under 0.5)."""
import argparse
import glob
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import oracle  # noqa: E402
from oracle import Dump  # noqa: E402
from oracle_match import screen, tmpl, meta, score_at  # noqa: E402
import terrain_images as ti  # noqa: E402

N = 228


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run", nargs="?", default=os.path.join(ROOT, "re", "oracle", "runs", "1F-meadow2"))
    ap.add_argument("shot", nargs="?")
    ap.add_argument("--tick", type=int)
    a = ap.parse_args()
    fs = oracle.dump_files(os.path.join(a.run, "dump"))
    f = [x for x in fs if a.tick is None or x.endswith(f"_{a.tick:06d}.bin")][-1]
    D = Dump(f)
    g = lambda r, dt: np.frombuffer(D.block(r), dt)[:N * N].reshape(N, N)
    fl, el, reg, me = g(17, "<u4"), g(111, "i1"), g(102, "u1"), g(99, "u1")
    kw = dict(scrub=g(109, "u1"), meadow=me, piece=g(20, "u1"))
    ours = ti.images_full(fl, el, g(22, "u1"), regrowth=reg, **kw)[0]
    full = ti.images_full(fl, el, g(22, "u1"), regrowth=np.full((N, N), 255, np.uint8), **kw)[0]
    col, row = D.at(0xDA2F64), D.at(0xDA2F68)
    S = screen(a.shot or os.path.join(a.run, "end.bmp"))
    H, W = S.shape[:2]
    print(f"dump {os.path.basename(f)}: view cell ({col}, {row}); meadow tiles {int(((fl & ti.MEADOW) != 0).sum())}, "
          f"grazed (regrowth < 255) {int((((fl & ti.MEADOW) != 0) & (reg < 255)).sum())}")
    won = lost = hidden = same = 0
    rows, allsc = [], []
    for y in range(N):
        for x in range(N):
            if not fl[y, x] & ti.MEADOW or fl[y, x] & ti.SKIP_TILE:
                continue
            L = (x - y) * 30 - (60 * col - 6870)
            T0 = (x + y) * 15 - (15 * row - 30) - 30 * int(el[y, x])
            if L < -60 or L > W or T0 < -60 or T0 > H:
                continue
            pid = int(full[y, x] if reg[y, x] == 0 else ours[y, x])
            idx = (pid & 0x3FFF) + 201
            s0, _ = score_at(S, tmpl("Zeus_Terrain", idx), L, T0 + 30 - meta("Zeus_Terrain", idx)["height"])
            allsc.append(float(s0))
            if ours[y, x] == full[y, x]:
                same += 1
                continue
            sc = []
            pair = (int(ours[y, x]), int(full[y, x]))
            if reg[y, x] == 0:                                # eaten since the last regrow step: the picture lags
                pair = pair[::-1]                             # (figure_graze writes no picture): ours = the old one
            for pid in pair:
                idx = (pid & 0x3FFF) + 201                   # play.js: atlas index n + 201
                m = meta("Zeus_Terrain", idx)
                s, n = score_at(S, tmpl("Zeus_Terrain", idx), L, T0 + 30 - m["height"])
                sc.append(float(s))
            if max(sc) < 0.5:
                hidden += 1
                continue
            if sc[0] > sc[1]:
                won += 1
            else:
                lost += 1
            rows.append((x, y, int(reg[y, x]), int(me[y, x]), pair[0] & 0x3FFF, pair[1] & 0x3FFF,
                         round(sc[0], 3), round(sc[1], 3)))
    for r in rows:
        print("tile (%d, %d) regrowth %d meadow %d: ours %d scores %.3f, the other %d %.3f" % (r[0], r[1], r[2], r[3], r[4], r[6], r[5], r[7]))
    print(f"grazed meadow tiles on screen: ours better {won}, the other better {lost}, hidden {hidden}; "
          f"tiles whose picture does not depend on regrowth: {same}")
    print(f"every meadow tile on screen: {len(allsc)}, ours at the rule >= 0.9: {sum(v >= 0.9 for v in allsc)}, "
          f">= 0.5: {sum(v >= 0.5 for v in allsc)} (the rest under sheep, trees or the panel)")
    return 0 if won and not lost else 1


if __name__ == "__main__":
    sys.exit(main())
