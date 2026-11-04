"""Play-mode check of the commemorative monuments (docs/play/monuments.md 9): every variant 1..65 drawn in the 4 views.

    python3 tools/commemorative_check.py prep SRC.pkl COPY.pkl LAYOUT.json
        a copy of SRC with every variant granted (`grant_monument V`) and placed (`build commemorative_monument X Y V O`,
        O = V % 4) on free land, 6 tiles apart along x and 12 along y (no statue covers another in any view);
        LAYOUT.json lists [v, x, y, size, o]
    python3 -m sim live COPY.pkl --port PORT --speed 0 &            (your own port, not a game in play)
    node tools/commemorative_check.mjs http://127.0.0.1:PORT/play.html LAYOUT.json DIR
        one screenshot per monument and view (original sprites, zoom 1/dpr: one world px = one device px)
    re/venv/bin/python tools/commemorative_check.py check LAYOUT.json DIR
        per shot: the picture the exe's rule predicts (variants 1..9: SPR_B_COMMEM_MONU + v - 1; statues: tools/
        play_buildings.py "statues", facing rule of FUN_00496CA0) found where it belongs (score, the best of the
        candidate facings, the statue minus the tile ring centre as in tools/oracle_commemorative.py: small
        (+30, 15 - h), large (-30 / 0 / +30, ...) from the oracle runs commem-*), and the pixels just outside the
        picture's box (1 px ring) compared with the shot without the monument's own pixels: a seam line would show as
        a row/column of identical dark pixels along an edge
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def prep(src, dst, out):
    from sim.game import Game, CommandError
    g = Game.load(src)
    g.city.treasury = max(g.city.treasury, 100000)
    w = g.world
    n = w.flags.shape[0]
    placed = []
    spots = [(x, y) for y in range(10, n - 10, 12) for x in range(10, n - 10, 6)]
    taken = []
    for v in range(1, 66):
        g.command(f"grant_monument {v}")
        o = v % 4
        for x, y in spots:
            if any(abs(x - a) < 6 and abs(y - b) < 12 for a, b in taken):
                continue
            try:
                g.command(f"build commemorative_monument {x} {y} {v} {o}")
            except CommandError:
                continue
            if True:
                b = next(b for b in g.buildings.values() if b.key == "commemorative_monument" and (b.x, b.y) == (x, y))
                placed.append([v, x, y, b.size, o])
                taken.append((x, y))
                break
        else:
            raise SystemExit(f"no spot for variant {v}")
    g.save(dst)
    json.dump(placed, open(out, "w"))
    print(f"{len(placed)} monuments placed in {dst}; layout {out}")


def expected(v, o, view):
    """[(file, index)] candidates (the predicted one first) and whether the picture is mirrored."""
    B = json.load(open(os.path.join(ROOT, "data", "play", "buildings.json")))["commemorative_monument"]
    mir = view in (2, 6)
    if v < 10:
        return [(B["file"], B["base"] + v)], mir, None
    S = B["statues"]
    god, large = S["god"][str(v)], v in S["large_variants"]
    f = ((((2 * o - view) if large else (view + 2 * o)) & 7) ^ (6 if mir else 0)) >> 1 & 3
    if large:
        file, first = S["large"][god]
    else:
        s = S["sculpture"][god]
        file, first = S["small_special"].get(str(s), [S["small"][0], S["small"][1] + 4 * s])
    order = [f] + [k for k in range(4) if k != f]
    return [(file, first + k) for k in order], mir, large


def check(layout, d):
    import numpy as np
    from PIL import Image
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    from oracle_rotation import best, sprite
    from oracle_commemorative import all_matches, TILE
    bad = 0
    for v, x, y, size, o in json.load(open(layout)):
        for view in (0, 2, 4, 6):
            p = os.path.join(d, f"v{v:02d}_view{view}.png")
            if not os.path.exists(p):
                print(f"{v:2d} view {view}: no shot")
                bad += 1
                continue
            img = np.asarray(Image.open(p).convert("RGB")).astype(int)
            cands, mir, large = expected(v, o, view)
            res = []
            for file, idx in cands:
                t = sprite(file, idx)
                t = t[:, ::-1] if mir else t
                s, pos = best(img, t)
                res.append((s, file, idx, pos, t))
            want = res[0]
            top = max(res, key=lambda r: r[0])
            ok = want[0] >= 0.9 and top is want      # < 1: covered in part by a neighbour (walkers, horses)
            line = f"{v:2d} o{o} view {view}: {want[1]}:{want[2]}{' mirrored' if mir else ''} score {want[0]:.3f} at {want[3]}"
            if top is not want:
                line += f"  BEST IS {top[1]}:{top[2]} {top[0]:.3f}"
            if want[3] and large is not None:
                tile = sprite(*TILE)
                tiles = all_matches(img, tile[:, ::-1] if mir else tile)
                if tiles:
                    cx = (min(t[0] for t in tiles) + max(t[0] for t in tiles)) / 2
                    cy = (min(t[1] for t in tiles) + max(t[1] for t in tiles)) / 2
                    line += f"  tiles {len(tiles)}, statue - ring centre ({want[3][0] - cx:+.0f}, {want[3][1] - cy:+.0f})"
            if want[3]:                                   # seam: the 1-px ring outside the picture's opaque edge
                X, Y = want[3]
                t = want[4]
                a = t[:, :, 3] > 200
                edge = np.zeros_like(a)
                edge[:, :-1] |= a[:, 1:] & ~a[:, :-1]
                edge[:, 1:] |= a[:, :-1] & ~a[:, 1:]
                edge[:-1, :] |= a[1:, :] & ~a[:-1, :]
                edge[1:, :] |= a[:-1, :] & ~a[1:, :]
                ys, xs = np.nonzero(edge)
                inside = (ys + Y < img.shape[0]) & (xs + X < img.shape[1])
                px = img[ys[inside] + Y, xs[inside] + X]
                blk = (px <= 8).all(axis=1)
                # a seam is a straight run of black pixels along the edge (outlines of other pictures are not)
                pts = set(zip(ys[inside][blk].tolist(), xs[inside][blk].tolist()))
                run = 0
                for yy, xx in pts:
                    for dy, dx in ((0, 1), (1, 0)):
                        k = 1
                        while (yy + k * dy, xx + k * dx) in pts:
                            k += 1
                        run = max(run, k)
                line += f"  edge px {len(px)}, black {int(blk.sum())}, longest black run {run}"
                if run >= 6:
                    ok = False
            print(("   " if ok else "!! ") + line)
            bad += not ok
    print("all ok" if not bad else f"{bad} shots not as predicted")
    return bad


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "prep":
        prep(*a[1:4])
    elif a and a[0] == "check":
        sys.exit(1 if check(*a[1:3]) else 0)
    else:
        print(__doc__)
