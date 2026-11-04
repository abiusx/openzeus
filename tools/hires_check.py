"""Artefact checks of the hi-res sets against the original's pixels (docs/play/hires.md "Checks").

    python3 tools/hires_check.py halo [--tol T] [SET[:FILE]...]
        Per set and file: opaque texels of the 2x copy play mode loads whose colour lies outside the range of the
        original pixel's 3x3 opaque neighbourhood by more than T (default 32) in some channel. Counted per 1000
        texels on the outline band (original pixels with a non-opaque 4-neighbour) and inside. The class of
        artefact of bugs.md 171: light/dark dots the model paints along edges that touch other pictures.
    python3 tools/hires_check.py shimmer [--variant V ...] [ROLE...]
        Walk cycles (data/play/walkers.json, figures set): mean |dRGB| between consecutive frames of a direction
        (aligned on the anchor, texels opaque in both), at 2x, as a ratio to the same for the nearest-neighbour
        upscale (= the real motion). Variants are applied to the 4x masters before the 2x shrink:
        raw (the masters), current (the 2x copy on disk), nearest, bicubic, clamp:T (hires_derive.clamp_local),
        own:T (own original pixel +- T), blend:A / cblend:A (A * model + (1 - A) * bicubic, c: clamp first),
        steady[:A] (hires_derive.steady, what play mode gets), consist:R[:T] (same-neighbourhood averaging).
        Also: mean |dRGB| from the raw Remacri 2x (how much of the model's picture a variant keeps) and from
        nearest (how far it is from the blocky original).
    python3 tools/hires_check.py compressed [--originals] [SET...]      (needs texture2ddecoder: pip, re/venv)
        Level 0 of each .astc.bin / .bc7.bin of tools/hires_compress.py decoded and compared with its PNG: mean
        |dRGB| over opaque texels, and alpha: texels off by more than 63 (the shader snaps smaller errors to 0 / 128 / 255, gl.js).
"""
import argparse
import functools
import json
import os
import sys

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hires_derive import shrink, clamp_local, local_range, consistent, steady  # noqa: E402

MASTERS = os.path.join(ROOT, "extracted", "hires")
PLAY = os.path.join(ROOT, "viewer", "play", "atlas", "hires")
METHOD = "remacri"


@functools.lru_cache(maxsize=6)
def sheet(path):
    return np.array(Image.open(path).convert("RGBA"))


@functools.lru_cache(maxsize=None)
def index(base, s, f):
    return json.load(open(os.path.join(base, s, METHOD, f + ".json")))


@functools.lru_cache(maxsize=None)
def orig_atlas(f):
    return {e["index"]: e for e in json.load(open(os.path.join(ROOT, "extracted", "sprites", f, "atlas.json")))["images"]}


def orig(f, i):
    """The original's picture as play mode draws it: pure red = shadow, black at alpha 128."""
    e = orig_atlas(f).get(i)
    if not e or not e.get("png"):
        return None
    a = np.array(Image.open(os.path.join(ROOT, "extracted", "sprites", f, e["png"])).convert("RGBA"))
    m = (a[..., 0] == 255) & (a[..., 1] == 0) & (a[..., 2] == 0) & (a[..., 3] == 255)
    a[m] = (0, 0, 0, 128)
    return a


def crop(base, s, f, i):
    j = index(base, s, f)
    e = j["images"].get(str(i))
    if not e or e[7] is not None:
        return None, None
    q, x, y, w, h = e[:5]
    return sheet(os.path.join(base, s, METHOD, j["sheets"][q]))[y:y + h, x:x + w], e


def two_x(s, f, i, variant):
    """Sprite i at 2x texels per original pixel for a variant, + its anchor in texels."""
    o = orig(f, i)
    if o is None:
        return None
    if variant == "nearest":
        return np.kron(o, np.ones((2, 2, 1), np.uint8)), (orig_atlas(f)[i]["anchor_x"] * 2, orig_atlas(f)[i]["anchor_y"] * 2)
    if variant == "current":
        c, e = crop(PLAY, s, f, i)
        return (None if c is None else c.copy(), None if e is None else (e[5], e[6]))
    m, e = crop(MASTERS, s, f, i)
    if m is None or m.shape[0] != o.shape[0] * 4:
        return None
    m = m.copy()
    if variant.startswith("clamp:"):
        clamp_local(m, o, int(variant[6:]))
    elif variant.startswith("own:"):                               # own original pixel +- T
        t = int(variant[4:])
        up = np.kron(o, np.ones((4, 4, 1), np.uint8)).astype(np.int16)
        sel = (m[..., 3] == 255) & (up[..., 3] == 255)
        rgb = m[..., :3].astype(np.int16)
        m[..., :3] = np.where(sel[..., None], np.clip(rgb, up[..., :3] - t, up[..., :3] + t), rgb).astype(np.uint8)
    elif variant.startswith("steady"):                              # what hires_derive does to figures
        steady(m, o, float(variant[7:]) if ":" in variant else 0.7)
    elif variant.startswith("blend:") or variant.startswith("cblend:"):   # a * model + (1 - a) * bicubic
        if variant.startswith("c"):
            clamp_local(m, o, 0)
        a = float(variant.split(":")[1])
        c = np.array(Image.fromarray(o).resize((o.shape[1] * 4, o.shape[0] * 4), Image.BICUBIC)).astype(np.float32)
        mix = (a * m[..., :3] + (1 - a) * c[..., :3] + 0.5).clip(0, 255).astype(np.uint8)
        m[..., :3] = np.where((m[..., 3] == 255)[..., None], mix, m[..., :3])
    elif variant == "bicubic":                                     # a smooth scaler that invents nothing
        c = np.array(Image.fromarray(o).resize((o.shape[1] * 4, o.shape[0] * 4), Image.BICUBIC))
        m[..., :3] = np.where((m[..., 3] == 255)[..., None], c[..., :3], m[..., :3])
    return shrink(m, 2), (e[5] / 2, e[6] / 2)


# --- halo -----------------------------------------------------------------------------------------------
def halo(targets, tol):
    ix = json.load(open(os.path.join(PLAY, "index.json")))
    tot = {}
    for t in targets or list(ix["sets"]):
        s, _, only = t.partition(":")
        for f in ix["sets"][s]["files"]:
            if only and f != only:
                continue
            j = index(PLAY, s, f)
            nb = ni = ob = oi = 0
            worst = []
            for i, e in j["images"].items():
                if e[7] is not None:
                    continue
                o = orig(f, int(i))
                c, _ = crop(PLAY, s, f, int(i))
                if o is None or c is None or c.shape[0] != o.shape[0] * 2 or c.shape[1] != o.shape[1] * 2:
                    continue
                lo, hi, has = local_range(o)
                op = o[..., 3] == 255
                p = np.pad(op, 1)
                band = op & ~(p[:-2, 1:-1] & p[2:, 1:-1] & p[1:-1, :-2] & p[1:-1, 2:])
                k = np.ones((2, 2), bool)
                L, H = (np.kron(v, np.ones((2, 2, 1), np.int16)) for v in (lo, hi))
                ok = (c[..., 3] == 255) & np.kron(op & has, k)
                rgb = c[..., :3].astype(np.int16)
                ex = np.maximum(np.maximum(L - rgb, rgb - H), 0).max(2)
                out = (ex > tol) & ok
                B = np.kron(band, k)
                nb += int((ok & B).sum()); ni += int((ok & ~B).sum())
                ob += int((out & B).sum()); oi += int((out & ~B).sum())
                n = int(out.sum())
                if n:
                    worst.append((n, int(i)))
            worst.sort(reverse=True)
            per = lambda a, b: 1000 * a / max(b, 1)
            print(f"{s}/{f}: band {per(ob, nb):.2f} / inside {per(oi, ni):.2f} per 1000 (texels {nb}, {ni}); "
                  f"worst {worst[:5]}", flush=True)
            T = tot.setdefault(s, [0, 0, 0, 0])
            T[0] += ob; T[1] += nb; T[2] += oi; T[3] += ni
    for s, (ob, nb, oi, ni) in tot.items():
        print(f"== {s}: band {1000 * ob / max(nb, 1):.2f} / inside {1000 * oi / max(ni, 1):.2f} per 1000 (tol {tol})")


# --- shimmer --------------------------------------------------------------------------------------------
def pair_diff(A, B):
    """Mean |dRGB| over texels opaque in both frames, anchors aligned. A, B = (rgba, (ax, ay))."""
    (a, (ax, ay)), (b, (bx, by)) = A, B
    dx, dy = int(round(ax - bx)), int(round(ay - by))           # b's texel (u, v) sits on a's (u + dx, v + dy)
    x0, y0 = max(0, dx), max(0, dy)
    x1, y1 = min(a.shape[1], b.shape[1] + dx), min(a.shape[0], b.shape[0] + dy)
    if x1 <= x0 or y1 <= y0:
        return 0.0, 0
    pa, pb = a[y0:y1, x0:x1], b[y0 - dy:y1 - dy, x0 - dx:x1 - dx]
    m = (pa[..., 3] == 255) & (pb[..., 3] == 255)
    d = np.abs(pa[..., :3].astype(np.int16) - pb[..., :3]).mean(2)[m]
    return float(d.sum()), int(m.sum())


def shimmer(variants, roles, sheet=None):
    sheet_out = {} if sheet else None
    W = json.load(open(os.path.join(ROOT, "data", "play", "walkers.json")))["roles"]
    figs = set(json.load(open(os.path.join(PLAY, "index.json")))["sets"]["figures"]["files"])
    roles = roles or [r for r, v in W.items() if v.get("file") in figs and "walk" in v][:12]
    res = {v: [0.0, 0] for v in variants + ["nearest"]}
    dev = {v: [0.0, 0.0, 0] for v in variants}
    for r in roles:
        f, wk = W[r]["file"], W[r]["walk"]
        pooled = {}                                        # consist:R / consist+clamp:R:T over the role's frames
        for v in variants:
            if v.startswith("consist"):
                idx = [wk["start"] + k for k in range(wk["dirs"] * wk["frames"])]
                got = [(i, crop(MASTERS, "figures", f, i)) for i in idx]
                pairs, keep = [], []
                for i, (m, e) in got:
                    o = orig(f, i)
                    if m is not None and o is not None and m.shape[0] == o.shape[0] * 4:
                        pairs.append((m.copy(), o)); keep.append((i, e))
                parts = v.split(":")
                consistent(pairs, int(parts[1]))
                if len(parts) > 2:
                    for m, o in pairs:
                        clamp_local(m, o, int(parts[2]))
                pooled[v] = {i: (shrink(m, 2), (e[5] / 2, e[6] / 2)) for (i, e), (m, o) in zip(keep, pairs)}
        for d in range(wk["dirs"]):
            frames = {}
            for v in variants + ["nearest", "raw"]:
                fr = []
                for k in range(wk["frames"]):
                    i = wk["start"] + k * wk["dirs"] + d
                    fr.append(pooled[v].get(i) if v in pooled else two_x("figures", f, i, v))
                frames[v] = fr
            if any(x is None for x in frames["raw"]):
                continue                                   # mirrored direction (drawn flipped)
            if sheet_out is not None and r == roles[0] and d == 3:
                sheet_out["rows"] = [(v, frames[v][:6]) for v in ["nearest", "raw"] + variants]
            for v in variants + ["nearest"]:
                fr = frames[v]
                for k in range(len(fr)):
                    s_, n_ = pair_diff(fr[k], fr[(k + 1) % len(fr)])
                    res[v][0] += s_; res[v][1] += n_
            for v in variants:
                for k in range(len(frames[v])):
                    a, r_, n_ = frames[v][k][0], frames["raw"][k][0], frames["nearest"][k][0]
                    if a.shape != r_.shape or a.shape != n_.shape:
                        continue
                    m = (a[..., 3] == 255) & (r_[..., 3] == 255) & (n_[..., 3] == 255)
                    dev[v][0] += float(np.abs(a[..., :3].astype(np.int16) - r_[..., :3]).mean(2)[m].sum())
                    dev[v][1] += float(np.abs(a[..., :3].astype(np.int16) - n_[..., :3]).mean(2)[m].sum())
                    dev[v][2] += int(m.sum())
        print(f"{r} done", file=sys.stderr, flush=True)
    if sheet and sheet_out.get("rows"):                   # contact sheet: 6 frames facing S per variant, x2
        rows = sheet_out["rows"]
        cw = max(f[0].shape[1] for _, fr in rows for f in fr) + 8
        ch = max(f[0].shape[0] for _, fr in rows for f in fr) + 8
        img = Image.new("RGBA", (cw * 6, ch * len(rows)), (120, 140, 90, 255))
        for y, (v, fr) in enumerate(rows):
            for x, (a, _) in enumerate(fr):
                img.alpha_composite(Image.fromarray(a), (x * cw + 4, y * ch + 4))
        img = img.resize((img.width * 2, img.height * 2), Image.NEAREST)
        img.save(sheet)
        print(f"sheet: {sheet} (rows: {', '.join(v for v, _ in rows)})")
    base = res["nearest"][0] / max(res["nearest"][1], 1)
    print(f"roles: {' '.join(roles)}")
    print(f"nearest: mean |dRGB| between frames {base:.2f}")
    for v in variants:
        m = res[v][0] / max(res[v][1], 1)
        print(f"{v}: between frames {m:.2f} = x{m / base:.3f} nearest; |d| from raw Remacri {dev[v][0] / max(dev[v][2], 1):.2f}, "
              f"from nearest {dev[v][1] / max(dev[v][2], 1):.2f}")


TOL_A = 63      # the shader snaps alpha to 0 / 128 / 255 (gl.js): an error up to 63 is drawn exactly


def compressed(originals, sets):
    import texture2ddecoder as T
    if originals:
        d = os.path.join(ROOT, "viewer", "play", "atlas")
        c = json.load(open(os.path.join(d, "compressed.json")))
        items = [(os.path.join(d, s_), w, h) for s_, (w, h) in c["sheets"].items()]
    else:
        ix = json.load(open(os.path.join(PLAY, "index.json")))
        items = []
        for st in sets or list(ix["sets"]):
            for n in range(ix["sets"][st]["sheets"]):
                items.append((os.path.join(PLAY, st, METHOD, f"{st}_{n}.png"), 4096, 4096))
    tot = {}
    for png, w, h in items:
        a = np.zeros((h, w, 4), np.uint8)
        im = np.array(Image.open(png).convert("RGBA"))
        a[:im.shape[0], :im.shape[1]] = im
        for fmt in ("astc", "bc7"):
            b = png[:-4] + f".{fmt}.bin"
            if not os.path.exists(b):
                continue
            raw = open(b, "rb").read()[:w * h]
            dec = T.decode_astc(raw, w, h, 4, 4) if fmt == "astc" else T.decode_bc7(raw, w, h)
            dec = np.frombuffer(dec, np.uint8).reshape(h, w, 4)[..., [2, 1, 0, 3]]
            op = a[..., 3] == 255
            e = np.abs(dec[..., :3].astype(np.int16) - a[..., :3]).mean(2)[op]
            ae = np.abs(dec[..., 3].astype(np.int16) - a[..., 3]) > TOL_A
            inside = ae & (a[..., 3] > 0)                       # covered texels drawn wrong (0 = gap/padding)
            t = tot.setdefault(fmt, [0.0, 0, 0, 0, 0])
            t[0] += float(e.sum()); t[1] += e.size; t[2] += int(ae.sum()); t[3] += int(inside.sum()); t[4] += w * h
            print(f"{os.path.basename(b)}: opaque mean |dRGB| {e.mean():.2f}, alpha off > {TOL_A}: {int(ae.sum())} "
                  f"({int(inside.sum())} on covered texels)", flush=True)
    for fmt, (es, en, ae, ai, n) in tot.items():
        print(f"== {fmt}: opaque mean |dRGB| {es / max(en, 1):.2f}; alpha off > {TOL_A}: {ae} of {n} texels "
              f"({1e6 * ae / n:.1f} per million; {ai} on covered texels)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    h = sp.add_parser("halo"); h.add_argument("--tol", type=int, default=32); h.add_argument("targets", nargs="*")
    s = sp.add_parser("shimmer"); s.add_argument("--variant", action="append"); s.add_argument("--sheet")
    s.add_argument("roles", nargs="*")
    c = sp.add_parser("compressed"); c.add_argument("--originals", action="store_true"); c.add_argument("sets", nargs="*")
    a = ap.parse_args()
    if a.cmd == "compressed":
        compressed(a.originals, a.sets)
    elif a.cmd == "halo":
        halo(a.targets, a.tol)
    else:
        shimmer(a.variant or ["raw", "current"], a.roles, a.sheet)


if __name__ == "__main__":
    main()
