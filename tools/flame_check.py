"""Where the flames of a burning building are drawn, in an oracle shot or a play-mode shot (bug 268/289,
docs/play/buildings.md "Fire").

    python3 tools/flame_check.py locate SHOT.png X0,Y0,X1,Y1 PICTURE.png [...]   # a building picture's top-left in SHOT
    python3 tools/flame_check.py flames SHOT.png OX,OY,N [...]                    # flames of an N-tile part at its draw point

`locate`: best match of the picture's opaque pixels (400 samples, within 8 per channel) for top-left positions in the
box. A part's draw point = (left, top + height - 15 * (N + 1)).
`flames`: for every offset of data/play/buildings.json ruin.flames (the exe's tables 0x005F5D08..), the best flame
frame (every loop, every frame) at draw point + (dx + 20 - anchor_x, dy + 20 - anchor_y), scored on its pixels with
alpha > 200 within 40 per channel (the exe blends these alpha pictures ~6 % darker), and the same frame shifted by
1-2 px: a peak at shift 0 = drawn at the table position. Oracle 1F-palacefire s_0960: back picture (1174) at (180, 100),
front (1163) at (60, 177) -> `flames s_0960.png 60,315,4 180,255,4` (the front piece peaks, the root shows none).
"""
import json
import os
import sys

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(p):
    return np.asarray(Image.open(p).convert("RGB")).astype(int)


def locate(shot, box, png):
    a = np.asarray(Image.open(png).convert("RGBA")).astype(int)
    ys, xs = np.nonzero(a[..., 3] > 200)
    sel = np.random.RandomState(0).choice(len(ys), min(400, len(ys)), replace=False)
    ys, xs = ys[sel], xs[sel]
    cols = a[ys, xs, :3]
    x0, y0, x1, y1 = box
    best = None
    for oy in range(y0, y1):
        for ox in range(x0, x1):
            yy, xx = ys + oy, xs + ox
            ok = (yy >= 0) & (yy < shot.shape[0]) & (xx >= 0) & (xx < shot.shape[1])
            if ok.sum() < 300:
                continue
            s = float((np.abs(shot[yy[ok], xx[ok]] - cols[ok]).max(axis=1) <= 8).mean())
            if best is None or s > best[0]:
                best = (s, ox, oy)
    return best


def frames():
    F = json.load(open(os.path.join(ROOT, "data", "play", "buildings.json")))["ruin"]["flames"]
    out = []
    for c in F["choices"]:
        if not c:
            continue
        A = json.load(open(os.path.join(ROOT, "extracted", "sprites", c["file"], "atlas.json")))
        I = {i["index"]: i for i in A["images"]}
        for k in range(c["frames"]):
            i = I[c["first"] + k]
            a = np.asarray(Image.open(os.path.join(ROOT, "extracted", "sprites", c["file"], i["png"])).convert("RGBA")).astype(int)
            out.append((c["file"], c["first"] + k, i["anchor_x"], i["anchor_y"], a))
    return F, out


def score(shot, a, x0, y0):
    ys, xs = np.nonzero(a[..., 3] > 200)
    yy, xx = ys + y0, xs + x0
    ok = (yy >= 0) & (yy < shot.shape[0]) & (xx >= 0) & (xx < shot.shape[1])
    if ok.sum() < 50:
        return 0.0
    return float((np.abs(shot[yy[ok], xx[ok]] - a[ys[ok], xs[ok], :3]).max(axis=1) <= 40).mean())


def flames(shot, points):
    F, fr = frames()
    for ox, oy, n in points:
        print("draw point", ox, oy, "size", n)
        for dx, dy in F["offsets"][str(n)]:
            s, f, idx, ax, ay, a = max(((score(shot, a, ox + dx + 20 - ax, oy + dy + 20 - ay), f, idx, ax, ay, a)
                                         for f, idx, ax, ay, a in fr), key=lambda t: t[0])
            sh = [round(score(shot, a, ox + dx + 20 - ax + sx, oy + dy + 20 - ay + sy), 2)
                  for sx, sy in ((1, 0), (-1, 0), (0, 1), (0, -1), (2, 0), (0, 2))] if s > 0.5 else []
            peak = "peak" if sh and s > max(sh) else ""
            print(f"  ({dx:4d},{dy:4d}) {s:.2f} {f}:{idx} shifted {sh} {peak}")


def main(a):
    if a[:1] == ["locate"]:
        shot = load(a[1])
        box = tuple(map(int, a[2].split(",")))
        for p in a[3:]:
            print(p, locate(shot, box, p))
    elif a[:1] == ["flames"]:
        flames(load(a[1]), [tuple(map(int, p.split(","))) for p in a[2:]])
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
