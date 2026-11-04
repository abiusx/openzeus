"""Smaller hi-res sets for play mode from the 4x masters of tools/upscale_sprites.py (docs/play/hires.md).

    python3 tools/hires_derive.py [--src extracted/hires] [--out viewer/play/atlas/hires] [--scale 2] [SET...]

The model runs once, at 4x (the masters, git-ignored in extracted/hires/); play mode loads a box-filtered copy:
2 texels per world pixel is already finer than the screen at 100-200 % zoom and a quarter of the memory.
Per texel of the result (k = 4 / scale), from its k x k master texels: opaque if at least half are opaque
(colour: the mean of those), else shadow if at least half are covered, else transparent (colour: the plain
mean, i.e. the bled colour); outlines stay crisp (shrink). Master sheets are 4096 wide and cells 4-aligned, so k x k shrunk sheets tile one
4096 sheet of the result: master sheet q goes to block (q % k, q // k) of result sheet q // (k * k).
"""
import argparse
import json
import os

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHEET = 4096


def shrink(a, k):
    """k x k master texels -> 1. Alpha by counts, not by mean: a block on an outline that is half opaque and
    half transparent has mean ~128, which is the shadow value (painted black): a dotted black outline on every
    staircase edge (bugs.md 77). So: at least half opaque -> opaque, coloured from its opaque texels only;
    else at least half covered (opaque or shadow) -> shadow (black, 128); else transparent (bled colour)."""
    h, w = a.shape[0] // k, a.shape[1] // k
    b = a[:h * k, :w * k].astype(np.float32).reshape(h, k, w, k, 4)
    al = b[..., 3]
    op = (al == 255).astype(np.float32)
    n_op, n_sh, half = op.sum((1, 3)), (al == 128).sum((1, 3)), k * k / 2
    rgb_op = (b[..., :3] * op[..., None]).sum((1, 3)) / np.maximum(n_op, 1)[..., None]
    plain = b[..., :3].mean((1, 3))
    rgb = np.where((n_op > 0)[..., None], rgb_op, plain)
    alpha = np.where(n_op >= half, 255, np.where(n_op + n_sh >= half, 128, 0))
    out = np.dstack([(rgb + 0.5).clip(0, 255), alpha]).astype(np.uint8)
    out[alpha == 128, :3] = 0                          # shadow texels: black
    return out


def local_range(o):
    """Per original pixel: min and max colour (int16 h x w x 3) of the opaque pixels in its 3x3 neighbourhood,
    and whether it has any (h x w bool)."""
    rgb, op = o[..., :3].astype(np.int16), o[..., 3] == 255
    p, q = np.pad(rgb, ((1, 1), (1, 1), (0, 0))), np.pad(op, 1)
    h, w = op.shape
    lo, hi = np.full((h, w, 3), 999, np.int16), np.full((h, w, 3), -999, np.int16)
    for dy in (0, 1, 2):
        for dx in (0, 1, 2):
            m = q[dy:dy + h, dx:dx + w, None]
            v = p[dy:dy + h, dx:dx + w]
            lo = np.where(m, np.minimum(lo, v), lo)
            hi = np.where(m, np.maximum(hi, v), hi)
    return lo, hi, lo[..., 0] <= hi[..., 0]


def clamp_local(m, o, tol):
    """Master crop m (4x the original o, RGBA, changed in place): every opaque texel's colour is clamped into the
    range of its original pixel's 3x3 opaque neighbourhood, widened by tol per channel. The model may smooth
    between neighbouring colours (edges, diagonals) but not invent highlights or holes beyond them, which is what
    changes from frame to frame of an animation (shimmer) and what dots seams. Returns the texels changed."""
    s = m.shape[0] // o.shape[0]
    lo, hi, has = local_range(o)
    k = np.ones((s, s), bool)
    L, H = (np.kron(v, np.ones((s, s, 1), np.int16)) for v in (lo - tol, hi + tol))
    sel = (m[..., 3] == 255) & np.kron(has, k)
    rgb = m[..., :3].astype(np.int16)
    fixed = np.clip(rgb, L, H)
    ch = sel & (fixed != rgb).any(2)
    m[..., :3] = np.where(sel[..., None], fixed, rgb).astype(np.uint8)
    return int(ch.sum())


def pattern_keys(o, r=1):
    """Per original pixel: its (2r+1)^2 neighbourhood of RGBA as one key (h x w array of void)."""
    h, w = o.shape[:2]
    p = np.pad(o, ((r, r), (r, r), (0, 0)))
    n = np.stack([p[dy:dy + h, dx:dx + w] for dy in range(2 * r + 1) for dx in range(2 * r + 1)], 2)
    n = np.ascontiguousarray(n.reshape(h, w, -1))
    return n.view(np.dtype((np.void, n.shape[2]))).reshape(h, w)


def consistent(pairs, r=1):
    """Same input, same output: the model's output for an original pixel depends on a wide neighbourhood, so a
    body part that moves by a pixel between animation frames comes out with other folds and highlights each
    frame (shimmer). Here every original pixel's 4x4 master block becomes the mean of the blocks of all pixels
    (over every picture in `pairs`) with the same (2r+1)^2 neighbourhood; unique neighbourhoods keep theirs.
    pairs: [(master crop RGBA 4x, original RGBA)], masters changed in place (colour of opaque texels)."""
    keys, blocks, opq, where = [], [], [], []
    for n, (m, o) in enumerate(pairs):
        s = m.shape[0] // o.shape[0]
        h, w = o.shape[:2]
        sel = o[..., 3] > 0
        keys.append(pattern_keys(o, r)[sel])
        b = m.reshape(h, s, w, s, 4).transpose(0, 2, 1, 3, 4)[sel]          # (k, s, s, 4)
        blocks.append(b[..., :3].astype(np.float32)); opq.append(b[..., 3] == 255)
        where.append((n, sel))
    if not keys:
        return 0
    K, B, O = np.concatenate(keys), np.concatenate(blocks), np.concatenate(opq)
    _, inv, cnt = np.unique(K, return_inverse=True, return_counts=True)
    inv = inv.ravel()
    S = np.zeros((len(cnt),) + B.shape[1:], np.float32)
    C = np.zeros((len(cnt),) + O.shape[1:], np.float32)
    np.add.at(S, inv, B * O[..., None])
    np.add.at(C, inv, O.astype(np.float32))
    mean = S / np.maximum(C, 1)[..., None]
    newB = np.where((O & (C[inv] > 0))[..., None], mean[inv], B)
    off = 0
    for (n, sel), k in zip(where, (len(x) for x in keys)):
        m, o = pairs[n]
        s = m.shape[0] // o.shape[0]
        h, w = o.shape[:2]
        v = m.reshape(h, s, w, s, 4).transpose(0, 2, 1, 3, 4).copy()
        v[sel, ..., :3] = (newB[off:off + k] + 0.5).clip(0, 255).astype(np.uint8)
        m[...] = v.transpose(0, 2, 1, 3, 4).reshape(m.shape)
        off += k
    return int((cnt[inv] > 1).sum())


# Per file, what is done to its master sprites before the shrink (refine): "edges" = ground tiles, outline band
# clamped to the original (bugs.md 171); "steady" = animated figures, clamp_local + a share of a plain bicubic
# upscale against frame-to-frame shimmer (docs/play/hires.md "Shimmer").
REFINE = {"Zeus_Terrain": "edges", "SprMain": "steady", "PoseidonImps": "steady", "SprAmbient": "steady"}
EDGE_BAND, EDGE_TOL = 4, 12                        # master texels (1 original pixel), per channel
STEADY_MIX = 0.7                                   # share of the model in "steady" (the rest: bicubic)


def original(f, o):
    """An original sprite as play mode draws it (pure red = shadow: black at alpha 128)."""
    a = np.array(Image.open(os.path.join(ROOT, "extracted", "sprites", f, o["png"])).convert("RGBA"))
    a[(a[..., 0] == 255) & (a[..., 1] == 0) & (a[..., 2] == 0) & (a[..., 3] == 255)] = (0, 0, 0, 128)
    return a


def fix_edge(t, orig):
    """Ground tiles tessellate edge to edge, so their outline texels sit on a seam. The model, fed a ring of
    random neighbours (upscale_sprites.py --context) or nothing (tall tiles), paints halos there: light or dark
    single texels along every diamond edge (bugs.md 171; tile 714: 93 of 2192 band texels off the original by
    > 60, 1 of 12208 inside). Each opaque master texel within EDGE_BAND texels of the outline is clamped to its
    original pixel's colour +- EDGE_TOL per channel. Every Zeus_Terrain picture (10-29: tall ones too, trees and
    rocks: their band had 18.6 outliers per 1000 vs 10.4 inside, tools/hires_check.py halo)."""
    sc = t.shape[0] // orig.shape[0]
    up = np.kron(orig.astype(np.int16), np.ones((sc, sc, 1), np.int16))
    op = t[..., 3] == 255
    inner = np.pad(op, EDGE_BAND)
    for _ in range(EDGE_BAND):
        inner = inner & np.roll(inner, 1, 0) & np.roll(inner, -1, 0) & np.roll(inner, 1, 1) & np.roll(inner, -1, 1)
    band = op & ~inner[EDGE_BAND:-EDGE_BAND, EDGE_BAND:-EDGE_BAND] & (up[..., 3] == 255)
    rgb = t[..., :3].astype(np.int16)
    fixed = np.clip(rgb, up[..., :3] - EDGE_TOL, up[..., :3] + EDGE_TOL)
    t[..., :3] = np.where(band[..., None], fixed, rgb).astype(np.uint8)
    return int((fixed != rgb).any(2)[band].sum())


def steady(t, orig, mix=STEADY_MIX):
    """Walk cycles shimmer: the original's frames are separate renders whose pixels differ a little frame to
    frame, and the model sharpens those differences into folds and highlights that jump (frame-to-frame change
    x1.18 the nearest upscale's over 12 walker roles). Each opaque master texel is clamped into its original
    pixel's 3x3 range (clamp_local, tol 0), then mixed: mix * model + (1 - mix) * bicubic of the original
    (colour bled under the transparent pixels first, so no dark edge). Measured with tools/hires_check.py
    shimmer: x0.995, i.e. as steady as the original; mean |dRGB| 6.5 from the plain model."""
    from upscale_sprites import bleed
    n = clamp_local(t, orig, 0)
    h, w = orig.shape[:2]
    rgb = bleed(orig[..., :3].astype(np.float32), orig[..., 3] > 0, 3)
    bic = np.array(Image.fromarray((rgb + 0.5).clip(0, 255).astype(np.uint8)).resize((t.shape[1], t.shape[0]), Image.BICUBIC))
    mixed = (mix * t[..., :3].astype(np.float32) + (1 - mix) * bic + 0.5).clip(0, 255).astype(np.uint8)
    t[..., :3] = np.where((t[..., 3] == 255)[..., None], mixed, t[..., :3])
    return n


def refine(sheets, d, files):
    """REFINE per file on the master sheets in `sheets` (index -> array, changed in place); texels changed."""
    n = 0
    for f in files:
        rule = REFINE.get(f)
        if not rule:
            continue
        j = json.load(open(os.path.join(d, f + ".json")))
        A = json.load(open(os.path.join(ROOT, "extracted", "sprites", f, "atlas.json")))["images"]
        by_index = {str(e["index"]): e for e in A}
        sc = j["scale"]
        for i, e in j["images"].items():
            o = by_index.get(i)
            if not o or not o.get("png") or e[0] not in sheets or e[7] is not None:
                continue
            q, x, y, w, h = e[0], e[1], e[2], e[3], e[4]
            orig = original(f, o)
            if orig.shape[0] * sc != h or orig.shape[1] * sc != w:
                continue
            t = sheets[q][y:y + h, x:x + w]
            n += fix_edge(t, orig) if rule == "edges" else steady(t, orig)
    return n


def derive(src, out, set_name, method, scale):
    d, o = os.path.join(src, set_name, method), os.path.join(out, set_name, method)
    files = sorted(f[:-5] for f in os.listdir(d) if f.endswith(".json"))
    j0 = json.load(open(os.path.join(d, files[0] + ".json")))
    k = j0["scale"] // scale                           # 1: the masters as they are (copied)
    per = k * k
    os.makedirs(o, exist_ok=True)
    masters = j0["sheets"]
    names = []
    for n in range((len(masters) + per - 1) // per):
        group = masters[n * per:(n + 1) * per]
        arrs = {n * per + q: np.array(Image.open(os.path.join(d, m)).convert("RGBA")) for q, m in enumerate(group)}
        fixed = refine(arrs, d, files)
        if fixed:
            print(f"{set_name}/{method}: {fixed} texels changed by refine ({', '.join(sorted({REFINE[f] for f in files if f in REFINE}))})", flush=True)
        parts = [shrink(arrs[n * per + q], k) for q in range(len(group))]
        side = SHEET // k
        hgt = max(((q // k) * side + p.shape[0]) for q, p in enumerate(parts))
        sheet = np.zeros((1 << max(0, (hgt - 1).bit_length()), SHEET, 4), np.uint8)
        for q, p in enumerate(parts):
            x0, y0 = (q % k) * side, (q // k) * side
            sheet[y0:y0 + p.shape[0], x0:x0 + p.shape[1]] = p
        fn = f"{set_name}_{n}.png"
        Image.fromarray(sheet, "RGBA").save(os.path.join(o, fn), compress_level=3)
        names.append(fn)
        print(f"{set_name}/{method}: sheet {n} from {len(group)} masters", flush=True)
    for f in files:
        j = json.load(open(os.path.join(d, f + ".json")))
        imgs = {}
        for i, e in j["images"].items():
            q = e[0]
            side = SHEET // k
            imgs[i] = [q // per, (q % per % k) * side + e[1] // k, (q % per // k) * side + e[2] // k,
                       e[3] // k, e[4] // k, e[5] / k, e[6] / k] + e[7:]
        with open(os.path.join(o, f + ".json"), "w") as fh:
            json.dump({"scale": scale, "sheets": names, "images": imgs}, fh, separators=(",", ":"))
    return files, len(names)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", default=os.path.join(ROOT, "extracted", "hires"))
    ap.add_argument("--out", default=os.path.join(ROOT, "viewer", "play", "atlas", "hires"))
    ap.add_argument("--scale", type=int, default=2, choices=(1, 2, 4))
    ap.add_argument("sets", nargs="*")
    a = ap.parse_args()
    six = json.load(open(os.path.join(a.src, "index.json")))
    try:
        oix = json.load(open(os.path.join(a.out, "index.json")))
    except (OSError, ValueError):
        oix = {"labels": six["labels"], "sets": {}}
    for s in a.sets or list(six["sets"]):
        S = dict(six["sets"][s])
        for m in S["methods"]:
            S["files"], n = derive(a.src, a.out, s, m, a.scale)
        S["scale"] = a.scale
        S["sheets"] = n                               # play mode's overall loading bar weighs sets by it
        oix["sets"][s] = S
    oix["labels"] = six["labels"]
    from hires_compress import content_version, sheet_files
    oix["version"] = content_version(sheet_files(a.out, oix))   # play mode appends ?v= to sheet urls (from the bytes, not the clock)
    with open(os.path.join(a.out, "index.json"), "w") as f:
        json.dump(oix, f, indent=1)


if __name__ == "__main__":
    main()
