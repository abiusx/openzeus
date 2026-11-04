"""Where a commemorative god statue is drawn relative to its ring of sanctuary tiles, in an oracle screenshot or a
play-mode readback (docs/play/monuments.md 9, the check of the statue pictures and placement).

    re/venv/bin/python tools/oracle_commemorative.py SHOT.png|bmp FILE:INDEX [FILE:INDEX ...]
    python3 tools/oracle_commemorative.py --poke VARIANT ORIENTATION > POKE.txt

--poke writes the ZEUS_POKE file of re/oracle/scenarios/commemorative.txt: "See a working city" building 435 (its
Population Monument at map (63, 34), grid +44) becomes VARIANT (Building+0x12) with ORIENTATION (+0xAC), size 4
(+0x03) for a large statue, and the camera (0x00DA2F64/68) is centred on it, at the first tick; the exe re-places
the pictures on every view turn (0x004953C0 -> FUN_00496CA0), so the scenario turns four times.

FILE:INDEX are the candidate statue pictures (atlas index, extracted/sprites); the tool prints the best one, plain
or mirrored, with its score (share of opaque pixels equal within 8 per channel, tools/oracle_rotation.py), every
occurrence of the tile picture Zeus_General 1447 (SPR_SANCTUARY_TILE, plain or mirrored, score >= 0.85) and the
statue's top-left minus the centre of the tiles' bounding box. Two shots that agree on the picture and on that
offset draw the monument the same way (the tiles of a ring: 8 for 3x3, 12 for 4x4; covered ones are missing).
"""
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from oracle_rotation import best, sprite  # noqa: E402

TILE = ("Zeus_General", 1447)


def all_matches(img, tpl, floor=0.85, tol=8):
    """Every position where tpl (RGBA) matches with score >= floor (exhaustive over candidate windows)."""
    H, W = img.shape[:2]
    h, w = tpl.shape[:2]
    ys, xs = np.nonzero(tpl[:, :, 3] > 200)
    rng = np.random.default_rng(1)
    pick = rng.choice(len(ys), min(48, len(ys)), replace=False)
    cnt = np.zeros((H - h + 1, W - w + 1), np.int16)
    for k in pick:
        y, x = ys[k], xs[k]
        cnt += (np.abs(img[y:y + H - h + 1, x:x + W - w + 1, :3] - tpl[y, x, :3]) <= tol).all(axis=2)
    out = []
    for y0, x0 in zip(*np.nonzero(cnt >= len(pick) - 16)):
        eq = (np.abs(img[y0:y0 + h, x0:x0 + w, :3] - tpl[:, :, :3]) <= tol).all(axis=2)[ys, xs].mean()
        if eq >= floor:
            out.append((int(x0), int(y0), float(eq)))
    return out


BUILDINGS, BREC, MONUMENT = 0x0092E658, 0x118, 435
LARGE = set(range(22, 34)) | {36, 37, 64, 65} | set(range(50, 62))


def poke(v, o):
    a = BUILDINGS + MONUMENT * BREC
    out = [f"# working city: building {MONUMENT} -> commemorative variant {v}, orientation {o} "
           "(tools/oracle_commemorative.py --poke)", "5 da2f64 4 124", "5 da2f68 4 170",
           f"5 {a + 0x12:x} 2 {v}", f"5 {a + 0xAC:x} 1 {o}"]
    if v in LARGE:
        out.append(f"5 {a + 0x03:x} 1 4")
    print("\n".join(out))


def main(argv):
    if argv[0] == "--poke":
        return poke(int(argv[1]), int(argv[2]))
    img = np.asarray(Image.open(argv[0]).convert("RGB")).astype(int)
    found = []
    for spec in argv[1:]:
        f, i = spec.split(":")
        t = sprite(f, int(i))
        for mir, tt in ((False, t), (True, t[:, ::-1])):
            s, p = best(img, tt)
            if p:
                found.append((s, spec, mir, p, tt.shape[1], tt.shape[0]))
    tile = sprite(*TILE)
    tiles = all_matches(img, tile) + all_matches(img, tile[:, ::-1])
    print(os.path.basename(argv[0]))
    if not found:
        print("  no statue picture found")
        return
    s, spec, mir, (x, y), w, h = max(found)
    print(f"  statue {spec}{' mirrored' if mir else ''} score {s:.3f} at ({x}, {y}) size {w}x{h}")
    print(f"  tiles: {len(tiles)} at {sorted((tx, ty) for tx, ty, _ in tiles)}")
    if tiles:
        cx = (min(t[0] for t in tiles) + max(t[0] for t in tiles)) / 2
        cy = (min(t[1] for t in tiles) + max(t[1] for t in tiles)) / 2
        print(f"  statue - tile ring centre: ({x - cx:+.1f}, {y - cy:+.1f})")


if __name__ == "__main__":
    main(sys.argv[1:])
