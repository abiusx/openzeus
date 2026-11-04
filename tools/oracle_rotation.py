"""Which sprite pictures (plain or mirrored) an oracle screenshot shows: the view-rotation check of
docs/play/rotation.md "Verification".

    python3 tools/oracle_rotation.py SHOT.bmp [SHOT.bmp ...] -s FILE:INDEX [-s FILE:INDEX ...]

FILE is a collection under extracted/sprites (e.g. Zeus_General), INDEX the atlas index (atlas.json 'index').
For every shot and sprite, prints the best position of the picture and of its mirror image, with the share
of the picture's opaque pixels that are equal (each channel within 8) there. A picture that is drawn
whole and uncovered scores near 1; anything under ~0.5 is not on the screen (or mostly covered).
Search: 48 opaque sample pixels must agree (all but 16), then the full picture is compared.
"""
import json
import os
import sys

import numpy as np
from PIL import Image
import oracle  # noqa: E402  (shot paths: .bmp -> .png, tools/oracle.py)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def sprite(file, index):
    a = json.load(open(os.path.join(ROOT, "extracted", "sprites", file, "atlas.json")))
    e = next(i for i in a["images"] if i["index"] == index)
    im = np.asarray(Image.open(os.path.join(ROOT, "extracted", "sprites", file, e["png"])).convert("RGBA")).astype(int)
    return im


def best(shot, tpl, samples=48, slack=16, tol=8):
    H, W = shot.shape[:2]
    h, w = tpl.shape[:2]
    if h > H or w > W:
        return 0.0, None
    ys, xs = np.nonzero(tpl[:, :, 3] > 200)
    if not len(ys):
        return 0.0, None
    rng = np.random.default_rng(1)
    pick = rng.choice(len(ys), min(samples, len(ys)), replace=False)
    cnt = np.zeros((H - h + 1, W - w + 1), np.int16)
    for k in pick:
        y, x = ys[k], xs[k]
        c = tpl[y, x, :3]
        win = shot[y:y + H - h + 1, x:x + W - w + 1, :3]
        cnt += (np.abs(win - c) <= tol).all(axis=2)
    out = (0.0, None)
    for y0, x0 in zip(*np.nonzero(cnt >= len(pick) - slack)):
        win = shot[y0:y0 + h, x0:x0 + w, :3]
        eq = (np.abs(win - tpl[:, :, :3]) <= tol).all(axis=2)[ys, xs].mean()
        if eq > out[0]:
            out = (float(eq), (int(x0), int(y0)))
    return out


def main(argv):
    shots = [a for a in argv if not a.startswith("-") and argv[argv.index(a) - 1] != "-s"]
    sprites = [argv[i + 1] for i, a in enumerate(argv) if a == "-s"]
    for s in shots:
        img = np.asarray(Image.open(oracle.shot(s)).convert("RGB")).astype(int)
        print(os.path.basename(s))
        for spec in sprites:
            f, i = spec.split(":")
            t = sprite(f, int(i))
            p, pp = best(img, t)
            m, mp = best(img, t[:, ::-1])
            print(f"  {spec:24s} plain {p:.3f} at {pp}   mirrored {m:.3f} at {mp}")


if __name__ == "__main__":
    main(sys.argv[1:])
