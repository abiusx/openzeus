"""Compare a window read back from play mode (tools/screens_check.mjs, PPM) with the same window in an oracle
screenshot of the exe (docs/play/screens.md "Checks"). Usage:
  re/venv/bin/python tools/screens_compare.py OURS.ppm ORACLE.bmp X,Y [--tol 30] [--diff OUT.png] [--mask X,Y,W,H ...]
X,Y = the window's top-left in the oracle shot. Prints pixels compared, pixels differing by more than --tol in any
channel, and their bounding box; --diff writes oracle | ours | difference side by side. --mask rectangles (window
coordinates) are left out (e.g. a picture of the live map behind a transparent part). --only R,G,B (repeatable): only the
pixels where either side is within --tol of one of those colours (text over a live map, e.g. the campaign lines'
red 240,0,0 and black 0,0,0: docs/play/campaign.md "Checks").
"""
import sys
from PIL import Image, ImageChops
import oracle  # noqa: E402  (shot paths: .bmp -> .png, tools/oracle.py)


def main(a):
    ours, orc, at = a[0], a[1], tuple(map(int, a[2].split(",")))
    tol = int(a[a.index("--tol") + 1]) if "--tol" in a else 30
    masks = [tuple(map(int, a[i + 1].split(","))) for i, v in enumerate(a) if v == "--mask"]
    only = [tuple(map(int, a[i + 1].split(","))) for i, v in enumerate(a) if v == "--only"]
    near = lambda p: any(max(abs(c - d) for c, d in zip(p, o)) <= tol for o in only)  # noqa: E731
    A = Image.open(ours).convert("RGB")
    B = Image.open(oracle.shot(orc)).convert("RGB").crop((at[0], at[1], at[0] + A.width, at[1] + A.height))
    pa, pb = A.load(), B.load()
    bad, box = 0, None
    for y in range(A.height):
        for x in range(A.width):
            if any(mx <= x < mx + mw and my <= y < my + mh for mx, my, mw, mh in masks):
                continue
            if only and not (near(pa[x, y]) or near(pb[x, y])):
                continue
            if max(abs(c - d) for c, d in zip(pa[x, y], pb[x, y])) > tol:
                bad += 1
                box = (x, y, x, y) if box is None else (min(box[0], x), min(box[1], y), max(box[2], x), max(box[3], y))
    print(f"{A.width}x{A.height} px compared, {bad} differ > {tol}" + (f", box {box}" if box else ""))
    if "--diff" in a:
        out = Image.new("RGB", (A.width * 3, A.height))
        out.paste(B, (0, 0)); out.paste(A, (A.width, 0))
        out.paste(ImageChops.difference(A, B).point(lambda v: 255 if v > tol else 0), (2 * A.width, 0))
        out.save(a[a.index("--diff") + 1])
    return bad


if __name__ == "__main__":
    sys.exit(1 if main(sys.argv[1:]) else 0)
