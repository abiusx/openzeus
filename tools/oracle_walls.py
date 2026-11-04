"""Wall pictures per view against oracle screenshots: the check of the wall rule in docs/play/rotation.md "Walls".

    python3 tools/oracle_walls.py --poke > POKE.txt        (the test layout below, for re/oracle/scenarios/rotation-walls.txt)
    python3 tools/oracle_walls.py DUMP.bin SHOT.bmp VIEW [SHOT.bmp VIEW ...]

DUMP.bin is an oracle state dump (re/oracle/runs/working-city/dump/tick_000000.bin, zones.txt beside it) of the
city in the shots. For every wall tile (terrain 0x4000, not a building tile 8) the rule of the exe's wall pass
0x0049FD70 (the same port as viewer/play/scene.js wallImage) predicts a picture (Zeus_General 777 + k). The
tiles' screen positions follow from the view transform up to one offset, found by search; at that offset the
tool prints, per tile, the share of the predicted picture's opaque pixels equal in the shot (each channel within
8) and the best of the 36 wall pictures there. Tiles covered by something drawn later score low for every
picture; a tile whose best picture is another one with a clearly higher score is a rule mismatch.
"""
import json
import os
import sys

import numpy as np
from PIL import Image
import oracle  # noqa: E402  (shot paths: .bmp -> .png, tools/oracle.py)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
N = 228
FIRST = 777            # Zeus_General SPR_STONE_WALLS (data/play/buildings.json wall.first)

# exe 0x00636820: pattern over neighbours N, NE, E, SE, S, SW, W, NW (1: no wall, 0: wall, 2: any), offsets per view
T = [("12121212", 26, 26, 26, 26), ("12121202", 15, 10, 5, 16), ("02121212", 16, 15, 10, 5), ("12021212", 5, 16, 15, 10),
     ("12120212", 10, 5, 16, 15), ("12021202", 1, 4, 1, 4), ("02120212", 4, 1, 4, 1), ("12120002", 10, 7, 5, 12),
     ("02121200", 12, 10, 7, 5), ("00021212", 5, 12, 10, 7), ("12000212", 7, 5, 12, 10), ("12120102", 10, 22, 5, 12),
     ("02121201", 12, 10, 22, 5), ("01021212", 5, 12, 10, 22), ("12010212", 22, 5, 12, 10), ("12000002", 3, 2, 1, 4),
     ("02120000", 4, 3, 2, 1), ("00021200", 1, 4, 3, 2), ("00000212", 2, 1, 4, 3), ("12010002", 22, 24, 1, 4),
     ("02120100", 4, 22, 24, 1), ("00021201", 1, 4, 22, 24), ("01000212", 24, 1, 4, 22), ("12000102", 25, 22, 1, 4),
     ("02120001", 4, 25, 22, 1), ("01021200", 1, 4, 25, 22), ("00010212", 22, 1, 4, 25), ("12010102", 22, 22, 1, 4),
     ("02120101", 4, 22, 22, 1), ("01021201", 1, 4, 22, 22), ("01010212", 22, 1, 4, 22), ("01010101", 22, 22, 22, 22),
     ("01010100", 22, 22, 23, 22), ("00010101", 22, 22, 22, 23), ("01000101", 23, 22, 22, 22), ("01010001", 22, 23, 22, 22),
     ("01000100", 17, 18, 17, 18), ("00010001", 18, 17, 18, 17), ("01010000", 22, 21, 19, 22), ("00010100", 22, 22, 21, 19),
     ("00000101", 19, 22, 22, 21), ("01000001", 21, 19, 22, 22), ("01000000", 21, 20, 19, 22), ("00010000", 22, 21, 20, 19),
     ("00000100", 19, 22, 21, 20), ("00000001", 20, 19, 22, 21), ("00000000", 0, 0, 0, 0)]
NB = [(0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1)]
TOWER = {0: ((0, -1), (-1, 0)), 2: ((1, 0), (0, -1)), 4: ((0, 1), (1, 0)), 6: ((-1, 0), (0, 1))}   # 0x0049F7D0
SWAP = [0, 4, 3, 2, 1, 10, 6, 7, 9, 8, 5, 11, 12, 14, 13, 16, 15, 17, 18, 21, 20, 19, 22, 23, 25, 24, 26, 28, 27,
        30, 29, 32, 31, 33, 35, 34]                                                                 # 0x0049F560


def tower_adjust(k, t):                                                                             # 0x0049F8A0
    if k in (0, 20): return 33 if t else k
    if k == 1: return 32 if t == 1 else 1
    if k in (2, 9, 19): return 29 if t == 2 else k
    if k in (3, 8, 21): return 30 if t == 1 else k
    if k == 4: return 31 if t == 2 else 4
    if k == 22: return 34 if t == 2 else 35 if t == 1 else 22
    return k


def wall_image(F, x, y, view):
    def f(xx, yy): return int(F[yy, xx]) if 0 <= xx < N and 0 <= yy < N else 0
    free = [not (f(x + dx, y + dy) & 0xC000) for dx, dy in NB]
    k = 0
    for r in T:
        if all(p == "2" or (p == "1") == a for p, a in zip(r[0], free)):
            k = r[1 + view // 2]
            break
    (a, b), (c, d) = TOWER[view]
    t = 2 if f(x + a, y + b) & 0x8000 else 1 if f(x + c, y + d) & 0x8000 else 0
    if t: k = tower_adjust(k, t)
    if view in (2, 6): k = SWAP[k]
    return k


def turned(x, y, v):
    return {0: (x, y), 2: (y, N - 1 - x), 4: (N - 1 - x, N - 1 - y), 6: (N - 1 - y, x)}[v]


def terrain(dump):
    zones = [l.split() for l in open(os.path.join(os.path.dirname(dump), "zones.txt"))]
    z = next(z for z in zones if int(z[1], 16) == 0x00CCE128)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from oracle import read_dump                  # plain or .zst (tools/oracle_compress.py)
    raw = read_dump(dump)[int(z[3]):int(z[3]) + int(z[2])]
    return np.frombuffer(raw, "<u4").reshape(N, N)


def sprites():
    a = json.load(open(os.path.join(ROOT, "extracted", "sprites", "Zeus_General", "atlas.json")))
    by = {i["index"]: i for i in a["images"]}
    return [np.asarray(Image.open(os.path.join(ROOT, "extracted", "sprites", "Zeus_General", by[FIRST + k]["png"]))
                       .convert("RGBA")).astype(int) for k in range(36)]


def share(img, sp, left, top):
    h, w = sp.shape[:2]
    H, W = img.shape[:2]
    if left < 0 or top < 0 or left + w > W or top + h > H:
        return None
    m = sp[:, :, 3] > 200
    d = np.abs(img[top:top + h, left:left + w] - sp[:, :, :3]).max(axis=2) <= 8
    return float(d[m].mean()) if m.any() else None


# test layout poked into the Open Play Sandbox at tiles (68..76, 100..108) (the middle of the start view): '#' wall
# (terrain 0x4000), 'T' tower tile (0xC008: wall + tower/gatehouse 0x8000 + building 8; no tower record, so the exe
# draws no tower there, only the walls beside it react), '.' plain ground; every tile gets elevation 0
LAYOUT = """
####TT#.#
#...TT#..
#.#...###
#.###...#
TT.#.#..#
TT.####..
#...#.##.
##.####.#
.#..#..##
"""
X0, Y0 = 68, 100


def poke(tick=10):
    rows = LAYOUT.split()
    for dy, r in enumerate(rows):
        for dx, c in enumerate(r):
            i = (Y0 + dy) * N + X0 + dx
            print(tick, f"{0x00CCE128 + 4 * i:x}", 4, {"#": 0x4000, "T": 0xC008, ".": 0}[c])
            print(tick, f"{0x008E01FA + i:x}", 1, 0)


def main(argv):
    if argv[:1] == ["--poke"]:
        return poke()
    F = terrain(argv[0])
    S0 = sprites()
    tiles = [(x, y) for y in range(N) for x in range(N) if F[y, x] & 0x4000 and not F[y, x] & 8]
    for shot, v in zip(argv[1::2], argv[2::2]):
        v = int(v)
        S = [sp[:, ::-1] for sp in S0] if v in (2, 6) else S0     # views 2 and 6 draw them mirrored (as buildings)
        img = np.asarray(Image.open(oracle.shot(shot)).convert("RGB")).astype(int)
        pred = {t: wall_image(F, *t, v) for t in tiles}
        pos = {}
        for (x, y) in tiles:
            a, b = turned(x, y, v)
            pos[(x, y)] = ((a - b) * 30, (a + b) * 15)
        # offset: every wall picture's sure positions in the shot vote for (position - tile position) of each tile
        H, W = img.shape[:2]
        votes = {}
        for k, sp in enumerate(S):
            if k in (0, 6, 11, 33):                  # flat or ground-only pictures: too ambiguous
                continue
            ys, xs = np.nonzero(sp[:, :, 3] > 200)
            h, w = sp.shape[:2]
            pick = np.random.default_rng(1).choice(len(ys), min(24, len(ys)), replace=False)
            cnt = np.zeros((H - h + 1, W - w + 1), np.int16)
            for i in pick:
                cnt += (np.abs(img[ys[i]:ys[i] + H - h + 1, xs[i]:xs[i] + W - w + 1] - sp[ys[i], xs[i], :3]).max(axis=2) <= 8)
            for oy, ox in zip(*np.nonzero(cnt >= 23)):
                for t in tiles:
                    o = (int(ox - pos[t][0]), int(oy + h - 30 - pos[t][1]))
                    votes[o] = votes.get(o, 0) + 1
        if not votes:
            print(f"{os.path.basename(shot)} view {v}: no wall picture found")
            continue
        cx, cy = max(votes, key=votes.get)
        print(f"{os.path.basename(shot)} view {v}: offset ({cx}, {cy}), {votes[(cx, cy)]} votes")
        # our composite in draw order (turned a + b, then a): each pixel belongs to the last tile drawn there
        order = sorted(tiles, key=lambda t: (sum(turned(*t, v)), turned(*t, v)[0]))
        owner = -np.ones((H, W), int)
        for n_, t in enumerate(order):
            sp = S[pred[t]]
            h, w = sp.shape[:2]
            L, Tp = pos[t][0] + cx, pos[t][1] + 30 - h + cy
            for yy, xx in zip(*np.nonzero(sp[:, :, 3] > 200)):
                if 0 <= Tp + yy < H and 0 <= L + xx < W:
                    owner[Tp + yy, L + xx] = n_
        good = n = 0
        for n_, t in enumerate(order):
            def sc(k):
                sp = S[k]
                h, w = sp.shape[:2]
                L, Tp = pos[t][0] + cx, pos[t][1] + 30 - h + cy
                e = q = 0
                for yy, xx in zip(*np.nonzero(sp[:, :, 3] > 200)):
                    Y, X = Tp + yy, L + xx
                    if 0 <= Y < H and 0 <= X < W and owner[Y, X] in (n_, -1):
                        q += 1
                        e += np.abs(img[Y, X] - sp[yy, xx, :3]).max() <= 8
                return e / q if q > 20 else None
            k = pred[t]
            s0 = sc(k)
            if s0 is None:
                continue
            bs, bj = max(((sc(j) or 0), j) for j in range(36))
            n += 1
            ok = bj == k or bs - s0 < 0.05
            good += ok
            if not ok or s0 < 0.8:
                print(f"  tile {t}: predicted {k} {s0:.2f}, best {bj} {bs:.2f}{'' if ok else '  MISMATCH'}")
        print(f"  {good}/{n} tiles agree")

if __name__ == "__main__":
    main(sys.argv[1:])
