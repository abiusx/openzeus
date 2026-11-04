"""Compare walker-window figure crops (tools/walker_crop_check.mjs output) with the map and with an oracle shot.

    python3 tools/walker_crop_compare.py OUTDIR [SHOT.bmp BOX_X,BOX_Y] [--tol 8] [--sprite PNG]

1. crop = map: the box's 48x48 interior against the map read at the crop's origin at the same scale (both with the
   test figure; other figures are left out of the crop, so pixels where the map shows another figure differ).
2. figure: the pixels the test figure changes in the box (box vs boxbare) against the oracle's box at BOX_X,BOX_Y
   (the exe's 52x52 RIMS box; its crop at +2,+2): the figure's own pixels at the same place in its crop.
   --sprite PNG (extracted/sprites/...: the figure's own picture, whose top-left is the crop's origin): only its
   opaque pixels (not the pure-red shadow) are scored, e.g. the pusher of a cart without the cart.
3. frame: the box's 2-px RIMS ring against the oracle's.
Prints counts of pixels differing by more than --tol in any channel."""
import argparse, json, os
import numpy as np
from PIL import Image
import oracle  # noqa: E402  (shot paths: .bmp -> .png, tools/oracle.py)


def ppm(path):
    return np.array(Image.open(oracle.shot(path)).convert("RGB")).astype(int)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir"); ap.add_argument("shot", nargs="?"); ap.add_argument("at", nargs="?")
    ap.add_argument("--tol", type=int, default=8)
    ap.add_argument("--sprite")
    a = ap.parse_args()
    box, bare, mp, mbare = (ppm(os.path.join(a.dir, f + ".ppm")) for f in ("box", "boxbare", "map", "mapbare"))
    info = json.load(open(os.path.join(a.dir, "info.json")))
    bad = lambda x, y: np.abs(x - y).max(2) > a.tol
    inner = box[2:50, 2:50]
    d1 = bad(inner, mp)
    fig = bad(box, bare)                                # the test figure's pixels in the box
    figmap = bad(mp, mbare)                             # and on the map
    print(f"crop vs map: {int(d1.sum())} of 2304 px differ (figure px: crop {int(fig[2:50, 2:50].sum())}, map {int(figmap.sum())}); "
          f"origin {info['origin']} anchor {info['anchor'][:2]}")
    if a.shot:
        bx, by = map(int, a.at.split(","))
        ex = np.array(Image.open(oracle.shot(a.shot)).convert("RGB")).astype(int)[by:by + 52, bx:bx + 52]
        d2 = bad(box, ex) & fig
        print(f"figure vs oracle: {int(d2.sum())} of {int(fig.sum())} figure px differ")
        if a.sprite:
            sp = np.array(Image.open(a.sprite).convert("RGBA")).astype(int)[:48, :48]
            m = np.zeros((52, 52), bool)
            h, w = sp.shape[:2]
            m[2:2 + h, 2:2 + w] = (sp[..., 3] > 200) & ~((sp[..., 0] > 200) & (sp[..., 1] < 40) & (sp[..., 2] < 40))
            d4 = bad(box, ex) & m & fig
            print(f"sprite px vs oracle: {int(d4.sum())} of {int((m & fig).sum())} differ (its opaque px drawn on top)")
        ring = np.ones((52, 52), bool); ring[2:50, 2:50] = False
        d3 = bad(box, ex) & ring
        print(f"RIMS ring vs oracle: {int(d3.sum())} of {int(ring.sum())} px differ")
        out = np.concatenate([box, ex, np.where(fig[..., None], box, 0), np.where(fig[..., None], ex, 0)], 1)
        Image.fromarray(np.kron(out, np.ones((4, 4, 1))).astype("uint8")).save(os.path.join(a.dir, "compare.png"))


if __name__ == "__main__":
    main()
